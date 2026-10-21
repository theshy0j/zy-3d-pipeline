"""run_recon.py — 单张图 → 3D 网格（TripoSR 封装，输出结构化 JSON 报告）。

用法：
    .venv\\Scripts\\python.exe scripts\\run_recon.py --input samples/building/input.png --outdir samples/building
可选：
    --remove-bg           用 rembg 去背景（需 pip install rembg，首次会下载 u2net 权重）
    --bake-texture        烘焙 UV 贴图（需要 xatlas；产物为 raw.obj + texture.png）
    --device cuda:0       默认有 CUDA 用 CUDA，否则自动落 CPU
    --mc-resolution 256   marching cubes 网格分辨率
输出（写入 --outdir）：
    model_input.png  实际喂给模型的预处理图（复现用）
    raw.glb          顶点色网格（默认）或 raw.obj + texture.png（--bake-texture）
    recon.json       耗时 / 显存峰值 / 网格统计
"""
import argparse
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSR_DIR = os.path.join(REPO, "third_party", "TripoSR")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="输入图片路径")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--model", default="stabilityai/TripoSR", help="HF repo id 或本地权重目录")
    ap.add_argument("--mc-resolution", type=int, default=256)
    ap.add_argument("--chunk-size", type=int, default=8192, help="渲染分块，越小越省显存")
    ap.add_argument("--remove-bg", action="store_true", help="用 rembg 去背景（需额外安装）")
    ap.add_argument("--bake-texture", action="store_true", help="烘焙 UV 贴图（需 xatlas）")
    ap.add_argument("--texture-resolution", type=int, default=1024)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    sys.path.insert(0, TSR_DIR)

    import numpy as np
    import torch
    from PIL import Image

    device = args.device if torch.cuda.is_available() else "cpu"
    report = {
        "input": os.path.relpath(args.input, REPO),
        "device": device,
        "torch": torch.__version__,
        "bake_texture": bool(args.bake_texture),
        "remove_bg": bool(args.remove_bg),
    }

    t0 = time.time()
    from tsr.system import TSR

    model = TSR.from_pretrained(args.model, config_name="config.yaml", weight_name="model.ckpt")
    model.renderer.set_chunk_size(args.chunk_size)
    model.to(device)
    model.eval()
    report["init_seconds"] = round(time.time() - t0, 2)

    # ---- 输入预处理（与 TripoSR run.py 两条路径一致）----
    image = Image.open(args.input).convert("RGB")
    if args.remove_bg:
        import rembg
        from tsr.utils import remove_background, resize_foreground

        session = rembg.new_session()
        image = remove_background(image, session)
        image = resize_foreground(image, 0.85)
        image = np.array(image).astype(np.float32) / 255.0
        image = image[:, :, :3] * image[:, :, 3:4] + (1 - image[:, :, 3:4]) * 0.5
        image = Image.fromarray((image * 255.0).astype(np.uint8))
    else:
        image = np.array(image)
    Image.fromarray(np.array(image)).save(os.path.join(args.outdir, "model_input.png"))

    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    # ---- 重建 ----
    t0 = time.time()
    with torch.no_grad():
        scene_codes = model([image], device=device)
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    report["recon_seconds"] = round(time.time() - t0, 2)
    if device.startswith("cuda"):
        report["vram_peak_gb"] = round(torch.cuda.max_memory_allocated() / 1024**3, 2)

    # ---- 抽网格 ----
    t0 = time.time()
    meshes = model.extract_mesh(scene_codes, not args.bake_texture, resolution=args.mc_resolution)
    report["extract_seconds"] = round(time.time() - t0, 2)
    mesh = meshes[0]
    report["mesh"] = {"vertices": int(len(mesh.vertices)), "faces": int(len(mesh.faces))}

    # ---- 导出 ----
    if args.bake_texture:
        import xatlas
        from tsr.bake_texture import bake_texture

        t0 = time.time()
        bake_output = bake_texture(mesh, model, scene_codes[0], args.texture_resolution)
        report["bake_seconds"] = round(time.time() - t0, 2)
        out_obj = os.path.join(args.outdir, "raw.obj")
        out_tex = os.path.join(args.outdir, "texture.png")
        xatlas.export(
            out_obj,
            mesh.vertices[bake_output["vmapping"]],
            bake_output["indices"],
            bake_output["uvs"],
            mesh.vertex_normals[bake_output["vmapping"]],
        )
        Image.fromarray((bake_output["colors"] * 255.0).astype(np.uint8)).transpose(
            Image.FLIP_TOP_BOTTOM
        ).save(out_tex)
        report["outputs"] = ["raw.obj", "texture.png"]
    else:
        out_glb = os.path.join(args.outdir, "raw.glb")
        mesh.export(out_glb)
        report["outputs"] = ["raw.glb"]

    with open(os.path.join(args.outdir, "recon.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
