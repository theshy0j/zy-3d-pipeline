#!/usr/bin/env python
"""下载 AI 重建所需权重，并校验完整性。

模型清单（授权详见 LICENSE_LOG.md）：
  - stabilityai/TripoSR   config.yaml + model.ckpt（MIT，默认引擎）
  - facebook/dino-vitb16  视觉编码器（TripoSR 运行时由 transformers 自动加载，这里预热缓存）

用法：
  python scripts/download_models.py           # 下载（已缓存则跳过）
  python scripts/download_models.py --verify  # 只校验，不下载
  python scripts/download_models.py --endpoint https://huggingface.co   # 覆盖镜像

国内网络：默认走 hf-mirror.com 镜像；出网代理由环境变量 HTTP_PROXY/HTTPS_PROXY 决定。

为什么绕了一圈：huggingface_hub 的缓存用 symlink 把 snapshots/<commit>/ 指向 blobs/。
部分 Windows 环境（无开发者模式/被安全软件拦截）os.symlink 静默失效——调用返回成功但
磁盘上什么都没有，缓存里只剩 blobs、snapshot 指针全是空的，from_pretrained 直接 FileNotFound。
本脚本的对策：一律先下载成**真实文件**（local_dir 模式），再把文件**复制**进
snapshots/<commit>/（真实副本，不依赖 symlink）。symlink 正常的机器上这套同样无害。

缓存 seeding：若 .cache/staging/model.ckpt 存在且 sha256 与官方登记值一致，直接复用，跳过 1.6GB 重下。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / ".cache" / "staging"
MODELS = ROOT / ".cache" / "models"

TRIPOSR_REPO = "stabilityai/TripoSR"
DINO_REPO = "facebook/dino-vitb16"

# 官方登记值（huggingface.co API，2026-10-21 核实，hf-mirror 与官方一致）
# (repo, filename) -> (sha256, size)
EXPECTED: dict[tuple[str, str], tuple[str, int]] = {
    (TRIPOSR_REPO, "model.ckpt"): (
        "429e2c6b22a0923967459de24d67f05962b235f79cde6b032aa7ed2ffcd970ee",
        1_677_246_742,
    ),
}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def set_endpoint(endpoint: str) -> None:
    os.environ["HF_ENDPOINT"] = endpoint


def hf_cache_hub() -> Path:
    return Path(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))) / "hub"


def repo_storage(repo: str) -> Path:
    return hf_cache_hub() / f"models--{repo.replace('/', '--')}"


def commit_hash(repo: str) -> str:
    """仓库 main 分支的 commit hash（HfApi 一次轻量调用）。"""
    from huggingface_hub import HfApi

    return HfApi().model_info(repo).sha


def with_retry(fn, tries: int = 5, delay: float = 3.0, what: str = ""):
    """网络操作重试。hf-mirror 的 HEAD 解析请求偶尔被代理打断（LocalEntryNotFoundError），
    重跑一次通常就好——这不是代码问题，是链路问题。"""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[retry] {what} 第 {i + 1}/{tries} 次失败：{type(e).__name__}: {e}")
            if i < tries - 1:
                time.sleep(delay)
    raise last


def materialize_cache(repo: str, local_dir: Path) -> Path:
    """把 local_dir 里的真实文件复制进 HF 缓存的 snapshots/<commit>/，并写好 refs/main。

    之后 try_to_load_from_cache / from_pretrained 都能直接命中（真实文件，不依赖 symlink）。
    """
    snap = repo_storage(repo) / "snapshots" / with_retry(lambda: commit_hash(repo), what=f"commit_hash({repo})")
    snap.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(local_dir.rglob("*")):
        if not f.is_file():
            continue
        dst = snap / f.relative_to(local_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.is_file():
            shutil.copyfile(f, dst)
            n += 1
    ref = repo_storage(repo) / "refs" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(snap.name)
    print(f"[cache] 物化 {n} 个文件 → {snap}")
    return snap


def ensure_triposr_local() -> Path:
    """保证 .cache/models/TripoSR 里有 config.yaml + model.ckpt（真实文件）。"""
    local = MODELS / "TripoSR"
    local.mkdir(parents=True, exist_ok=True)
    ckpt = local / "model.ckpt"
    want_sha, want_size = EXPECTED[(TRIPOSR_REPO, "model.ckpt")]

    if ckpt.is_file() and ckpt.stat().st_size == want_size:
        print(f"[triposr] model.ckpt 已就绪（{ckpt}）")
    else:
        staged = STAGING / "model.ckpt"
        if staged.is_file() and staged.stat().st_size == want_size and sha256_file(staged) == want_sha:
            print("[triposr] 复用已校验的 staging model.ckpt")
            shutil.copyfile(staged, ckpt)
        else:
            from huggingface_hub import hf_hub_download

            print("[triposr] 下载 model.ckpt（约 1.6GB）…")
            with_retry(
                lambda: hf_hub_download(repo_id=TRIPOSR_REPO, filename="model.ckpt", local_dir=local),
                what="model.ckpt",
            )

    cfg = local / "config.yaml"
    if not cfg.is_file():
        from huggingface_hub import hf_hub_download

        print("[triposr] 下载 config.yaml …")
        with_retry(
            lambda: hf_hub_download(repo_id=TRIPOSR_REPO, filename="config.yaml", local_dir=local),
            what="config.yaml",
        )
    return local


def ensure_dino_local() -> Path:
    local = MODELS / "dino-vitb16"
    local.mkdir(parents=True, exist_ok=True)
    if any(local.iterdir()):
        print(f"[dino] 已就绪（{local}）")
        return local
    from huggingface_hub import snapshot_download

    print("[dino] 下载 facebook/dino-vitb16（约 330MB）…")
    with_retry(
        lambda: snapshot_download(
            DINO_REPO,
            local_dir=local,
            ignore_patterns=["*.msgpack", "*.h5", "*.ot", "flax_model*", "tf_model*"],
        ),
        what="dino-vitb16",
    )
    return local


def verify() -> int:
    from huggingface_hub import try_to_load_from_cache

    ok = True
    for (repo, filename), (want_sha, want_size) in EXPECTED.items():
        cached = try_to_load_from_cache(repo_id=repo, filename=filename)
        if not cached or not Path(str(cached)).is_file():
            print(f"[verify] ✗ {repo}/{filename} 未缓存（先跑本脚本无 --verify）")
            ok = False
            continue
        p = Path(str(cached))
        if p.stat().st_size != want_size or sha256_file(p) != want_sha:
            print(f"[verify] ✗ {repo}/{filename} 大小/sha256 不符")
            ok = False
            continue
        print(f"[verify] ✓ {repo}/{filename}  {want_size:,} B  sha256 一致")
    # DINO 抽查：config.json 能命中即可（权重文件大，交给 transformers 自己验）
    dino_cfg = try_to_load_from_cache(repo_id=DINO_REPO, filename="config.json")
    if dino_cfg and Path(str(dino_cfg)).is_file():
        print(f"[verify] ✓ {DINO_REPO}/config.json 已缓存")
    else:
        print(f"[verify] ✗ {DINO_REPO}/config.json 未缓存", file=sys.stderr)
        ok = False
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="只校验已缓存权重，不下载")
    ap.add_argument("--endpoint", default="https://hf-mirror.com", help="HF 端点（默认 hf-mirror 镜像）")
    ap.add_argument("--no-dino", action="store_true", help="跳过 DINO 预热")
    args = ap.parse_args()

    set_endpoint(args.endpoint)
    print(f"[env] HF_ENDPOINT={os.environ['HF_ENDPOINT']}")
    print(f"[env] HF_HOME={os.environ.get('HF_HOME', '(默认 ~/.cache/huggingface)')}")

    if args.verify:
        return verify()

    try:
        triposr_local = ensure_triposr_local()
        materialize_cache(TRIPOSR_REPO, triposr_local)
        if not args.no_dino:
            dino_local = ensure_dino_local()
            materialize_cache(DINO_REPO, dino_local)
    except Exception as e:  # noqa: BLE001
        print(f"[fail] {type(e).__name__}: {e}", file=sys.stderr)
        print("       排查：① 代理是否放行 hf-mirror.com；② 磁盘空间；③ 换 --endpoint 重试", file=sys.stderr)
        return 1

    rc = verify()
    if rc != 0:
        return rc

    print("\n全部权重就绪。可以跑：python scripts/run_recon.py --input <图片> --outdir samples/_demo")
    print("（--model 也可直接指向本地目录 .cache/models/TripoSR，不依赖 HF 缓存）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
