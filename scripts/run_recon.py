"""run_recon.py — 单张图 / 批量图 → 3D 网格（经引擎抽象层，结构化 JSON 报告）。

用法（单张，向后兼容）：
    .venv\\Scripts\\python.exe scripts\\run_recon.py --input samples/building/input.png --outdir samples/building
批量（共享一次模型初始化，省去重复加载开销）：
    .venv\\Scripts\\python.exe scripts\\run_recon.py --input a.png b.png c.png --outdir outbase
    （每个结果落在 outbase\\<文件名>/ 下，各含 recon.json + 产物；outbase 下另写 recon_summary.json）

可选：
    --engine triposr      重建引擎（默认 triposr；新增引擎见 scripts/engines/）
    --remove-bg           用 rembg 去背景（需 pip install rembg，首次会下载 u2net 权重）
    --bake-texture        烘焙 UV 贴图（需要 xatlas；产物为 raw.obj + texture.png）
    --device cuda:0       默认有 CUDA 用 CUDA，否则自动落 CPU
    --mc-resolution 256   marching cubes 网格分辨率
单张输出（写入 --outdir）：
    model_input.png  实际喂给模型的预处理图（复现用）
    raw.glb          顶点色网格（默认）或 raw.obj + texture.png（--bake-texture）
    recon.json       耗时 / 显存峰值 / 网格统计
"""
import argparse
import json
import os
import sys
import time

# 让 scripts/ 下的 engines 包可导入
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from engines import get_engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, nargs="+",
                    help="输入图片路径（可传多个以支持批量；批量时共享一次模型初始化）")
    ap.add_argument("--outdir", required=True,
                    help="单张：输出目录；批量：输出基目录（每图落到 <基目录>/<文件名>/）")
    ap.add_argument("--engine", default="triposr", help="重建引擎（默认 triposr）")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--model", default="stabilityai/TripoSR", help="HF repo id 或本地权重目录")
    ap.add_argument("--mc-resolution", type=int,
                    default=int(os.environ.get("MC_RESOLUTION", "256")),
                    help="marching cubes 网格分辨率（默认 256；可用环境变量 MC_RESOLUTION 覆盖）")
    ap.add_argument("--chunk-size", type=int, default=8192, help="渲染分块，越小越省显存")
    ap.add_argument("--remove-bg", action="store_true", help="用 rembg 去背景（需额外安装）")
    ap.add_argument("--bake-texture", action="store_true", help="烘焙 UV 贴图（需 xatlas）")
    ap.add_argument("--texture-resolution", type=int, default=1024)
    args = ap.parse_args()

    inputs = args.input
    batch = len(inputs) > 1

    engine_cls = get_engine(args.engine)
    engine = engine_cls(device=args.device, chunk_size=args.chunk_size)
    print(f"[load] engine={args.engine} model={args.model}")
    t_load = time.time()
    engine.load(args.model)
    print(f"[load] done in {engine.init_seconds}s")

    reports = []
    for i, inp in enumerate(inputs):
        if not os.path.isfile(inp):
            raise FileNotFoundError(f"输入图不存在：{inp}")
        if batch:
            stem = os.path.splitext(os.path.basename(inp))[0]
            outdir = os.path.join(args.outdir, stem)
        else:
            outdir = args.outdir
        os.makedirs(outdir, exist_ok=True)

        print(f"[recon {i+1}/{len(inputs)}] {inp} -> {outdir}")
        rep = engine.process(
            inp,
            outdir,
            remove_bg=args.remove_bg,
            bake_texture=args.bake_texture,
            texture_resolution=args.texture_resolution,
            mc_resolution=args.mc_resolution,
            model_id=args.model,
        )
        # 单张模式写 recon.json 到 outdir（向后兼容）；批量模式同样每图写一份
        with open(os.path.join(outdir, "recon.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        reports.append(rep)
        print(json.dumps(rep, ensure_ascii=False))

    if batch:
        summary = {
            "engine": args.engine,
            "model": args.model,
            "init_seconds": engine.init_seconds,
            "count": len(reports),
            "items": [os.path.relpath(r["input"], os.path.dirname(args.outdir) or ".") for r in reports],
        }
        with open(os.path.join(args.outdir, "recon_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"[summary] {len(reports)} 项，共享初始化 {engine.init_seconds}s -> "
              f"{os.path.join(args.outdir, 'recon_summary.json')}")


if __name__ == "__main__":
    main()
