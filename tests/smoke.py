"""smoke.py — 管线冒烟测试（稳定性闸门）。

两种运行模式，自动按环境切换：
  1) 有 CUDA + TripoSR 权重已缓存 → 跑一次真实低分辨率重建（mc-resolution 128），
     断言：网格非退化（顶点/面数 > 阈值、无 NaN）、产物文件落盘、显存峰值已记录、
     水密性被实测并记录（TripoSR 不保证水密，故水密性为“软指标”，不导致失败；
     但网格若退化或产物缺失则判 FAIL）。
  2) 无 CUDA / 无权重 → 降级为 import 检查（依赖齐全性 + TripoSR 源码 + 权重路径），
     同样退出 0，并打印 “SKIP recon（无 GPU/权重）”。

用法：
    .venv\\Scripts\\python.exe tests\\smoke.py
    .venv\\Scripts\\python.exe tests\\smoke.py --mc-resolution 256   # 跑更高分辨率
    .venv\\Scripts\\python.exe tests\\smoke.py --no-gpu               # 强制只做 import 检查

产物：
    tests\\smoke_report.json
退出码：
    0 = 通过（或降级通过）
    1 = 必需项失败
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PY):
    PY = sys.executable  # 退路：用当前解释器（如已在 .venv 内）

results = []


def check(name, ok, detail, required=True, soft=False):
    results.append({
        "name": name, "ok": bool(ok), "detail": detail,
        "required": required, "soft": soft,
    })
    tag = "PASS" if ok else ("WARN" if soft else ("FAIL" if required else "WARN"))
    print(f"{tag} - {name} : {detail}")


def has_cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def weights_cached():
    cache = os.path.join(
        os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub"
    )
    return os.path.isdir(os.path.join(cache, "models--stabilityai--TripoSR"))


def import_checks():
    """无 GPU / 无权重时的降级检查：依赖齐全性。"""
    # 1. 核心 Python 依赖
    for mod in ("numpy", "torch", "trimesh", "transformers", "huggingface_hub", "PIL"):
        try:
            __import__(mod)
            check(f"import {mod}", True, "ok")
        except ImportError as e:
            check(f"import {mod}", False, str(e))

    # 2. TripoSR 源码存在（bootstrap 会下载并打补丁）
    tsr = os.path.join(REPO, "third_party", "TripoSR", "run.py")
    check("third_party/TripoSR 源码", os.path.isfile(tsr),
          "存在" if os.path.isfile(tsr) else "缺失：先跑 scripts/bootstrap.ps1")

    # 3. 引擎接口可加载（验证 TSR 类能被 import，不触发重建）
    if os.path.isfile(tsr):
        sys.path.insert(0, os.path.join(REPO, "third_party", "TripoSR"))
        try:
            from tsr.system import TSR  # noqa: F401
            check("import tsr.system.TSR", True, "ok")
        except Exception as e:
            check("import tsr.system.TSR", False, f"{type(e).__name__}: {e}")

    # 4. 权重是否已缓存（缺失仅 WARN，首次推理会自动下载）
    cached = weights_cached()
    check("TripoSR 权重缓存", cached,
          "已缓存" if cached else "未缓存（首次重建会自动下载约 1.6GB）", required=False)


def make_synthetic_input(path):
    """生成一张合成输入图（简单球体渐变 + 白底），让重建可独立运行，不依赖示例素材/Blender。"""
    try:
        import numpy as np
        from PIL import Image, ImageDraw
    except ImportError as e:
        check("生成合成输入图", False, f"{type(e).__name__}: {e}")
        return False

    s = 512
    img = Image.new("RGB", (s, s), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # 中心画一个实心圆，模拟前景物体轮廓
    r = 170
    d.ellipse([s // 2 - r, s // 2 - r, s // 2 + r, s // 2 + r], fill=(120, 140, 200))
    img.save(path)
    return True


def gpu_recon(mc_resolution):
    """有 CUDA 时跑一次真实重建，断言产物与网格质量。"""
    tmp = tempfile.mkdtemp(prefix="zy_smoke_")
    inp = os.path.join(tmp, "input.png")
    if not make_synthetic_input(inp):
        return

    check("合成输入图生成", os.path.isfile(inp), inp)

    # 直接复用已测过的 run_recon.py（避免重复引擎调用代码）
    cmd = [PY, os.path.join(REPO, "scripts", "run_recon.py"),
           "--input", inp, "--outdir", tmp, "--mc-resolution", str(mc_resolution)]
    print(f"\n>> 运行重建：{' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    if proc.returncode != 0:
        check("run_recon 退出码", False, f"rc={proc.returncode}\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
        return
    check("run_recon 退出码", True, "0")

    # 解析 recon.json
    rj = os.path.join(tmp, "recon.json")
    if not os.path.isfile(rj):
        check("recon.json 产物", False, "缺失")
        return
    with open(rj, encoding="utf-8") as f:
        rep = json.load(f)
    check("recon.json 产物", True, "存在")
    check("显存峰值已记录", "vram_peak_gb" in rep,
          rep.get("vram_peak_gb", "缺失"), required=False)

    # 网格规模断言（非退化）
    mesh = rep.get("mesh", {})
    v, fc = mesh.get("vertices", 0), mesh.get("faces", 0)
    check("网格顶点数 > 100", v > 100, f"vertices={v}")
    check("网格面数 > 100", fc > 100, f"faces={fc}")

    # 加载网格，检查 NaN / 水密性（软）
    out_files = rep.get("outputs", [])
    glb = os.path.join(tmp, "raw.glb")
    obj = os.path.join(tmp, "raw.obj")
    target = glb if os.path.isfile(glb) else (obj if os.path.isfile(obj) else None)
    if target:
        import numpy as np
        import trimesh
        m = trimesh.load(target, force="mesh")
        # 烘焙贴图路径导出的 .obj 是“顶点拆分”的（相邻面引用不同顶点索引），
        # 直接查边界会得到大量伪边界。先焊接顶点再判水密/边界，两种导出路径都准确。
        try:
            m2 = m.copy()
            m2.merge_vertices()
            mm = m2
        except Exception:
            mm = m
        verts = np.asarray(m.vertices, dtype=float)
        nan = bool(np.isnan(verts).any())
        check("网格无 NaN 顶点", not nan, "无 NaN" if not nan else "存在 NaN（退化！）")
        check("产物文件落盘", os.path.getsize(target) > 1024, f"{os.path.getsize(target)} bytes")
        # 水密性：TripoSR 不保证，记为软指标
        wt = bool(mm.is_watertight)
        # 边界边 = 仅被一个面引用的边。直接用 m.faces 推导，跨 trimesh 版本稳健（不依赖 edges_face/face_edges 等不稳定属性）。
        faces = np.asarray(mm.faces).reshape(-1, 3)
        fe = np.sort(
            np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]),
            axis=1,
        )
        _, inv = np.unique(fe, axis=0, return_inverse=True)
        counts = np.bincount(inv)
        n_bound = int(np.sum(counts == 1))
        check("水密性实测", True, f"watertight={wt}, boundary_edges={n_bound}",
              required=False, soft=True)
        if not wt:
            print(f"    ℹ️ 重建网格非水密（boundary_edges={n_bound}）—— 这是 TripoSR 的已知特性，"
                  f"真实资产请用 Blender 清理阶段缝合/补洞。")
    else:
        check("网格文件落盘", False, f"未找到 {out_files}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc-resolution", type=int, default=128,
                    help="冒烟重建分辨率（默认 128，快；可提到 256 更接近真实）")
    ap.add_argument("--no-gpu", action="store_true", help="强制只做 import 检查")
    args = ap.parse_args()

    print("== zy-3d-pipeline 冒烟测试 ==")
    cuda = has_cuda() and not args.no_gpu
    cached = weights_cached()

    if cuda and cached:
        print(f"模式：GPU 真实重建（mc-resolution={args.mc_resolution}）\n")
        gpu_recon(args.mc_resolution)
    else:
        reasons = []
        if not cuda:
            reasons.append("无 CUDA（torch.cuda.is_available()=False）")
        if not cached:
            reasons.append("TripoSR 权重未缓存")
        if args.no_gpu:
            reasons.append("--no-gpu 强制")
        print(f"模式：降级 import 检查（{'; '.join(reasons)}）\n")
        import_checks()

    failed = [r for r in results if r["required"] and not r["ok"]]
    soft_warn = [r for r in results if r.get("soft") and not r["ok"]]
    report = {
        "repo": REPO,
        "mode": "gpu_recon" if (cuda and cached) else "import_only",
        "passed": not failed,
        "failed_required": [r["name"] for r in failed],
        "soft_warnings": [r["name"] for r in soft_warn],
        "results": results,
    }
    out = os.path.join(REPO, "tests", "smoke_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nsmoke_report.json -> {out}")
    print("RESULT:", "PASS" if not failed else "FAIL")
    if soft_warn:
        print(f"（含 {len(soft_warn)} 条软告警，不影响通过）")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
