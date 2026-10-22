"""TripoSREngine — TripoSR 引擎实现（默认）。

把原 run_recon.py 中对 TripoSR 的调用封装进来；run_recon.py 通过引擎抽象层调用，
不直接 import tsr。新增其它引擎时不影响本文件。
"""
import os
import sys
import time

import numpy as np

from .base import ReconEngine

# TripoSR 源码目录（由 bootstrap 下载，未随仓库分发）
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TSR_DIR = os.path.join(REPO, "third_party", "TripoSR")


class TripoSREngine(ReconEngine):
    name = "triposr"

    def load(self, model_id):
        sys.path.insert(0, TSR_DIR)
        import torch
        from tsr.system import TSR

        device = self._resolve_device(self.device)
        self.device = device

        t0 = self._now()
        model = TSR.from_pretrained(
            model_id, config_name="config.yaml", weight_name="model.ckpt"
        )
        model.renderer.set_chunk_size(self.chunk_size)
        model.to(device)
        model.eval()
        self.model = model
        self.init_seconds = round(time.time() - t0, 2)

    def process(
        self,
        input_path,
        outdir,
        remove_bg=False,
        bake_texture=False,
        texture_resolution=1024,
        mc_resolution=256,
        model_id="stabilityai/TripoSR",
    ):
        import torch
        from PIL import Image

        os.makedirs(outdir, exist_ok=True)
        model = self.model
        device = self.device
        report = {
            "input": input_path,
            "engine": self.name,
            "device": device,
            "torch": torch.__version__,
            "init_seconds": self.init_seconds,
            "bake_texture": bool(bake_texture),
            "remove_bg": bool(remove_bg),
        }

        # ---- 输入预处理（与 TripoSR run.py 两条路径一致）----
        image = Image.open(input_path).convert("RGB")
        if remove_bg:
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
        Image.fromarray(np.array(image)).save(os.path.join(outdir, "model_input.png"))

        if device.startswith("cuda"):
            torch.cuda.reset_peak_memory_stats()

        # ---- 重建 ----
        t0 = self._now()
        with torch.no_grad():
            scene_codes = model([image], device=device)
        if device.startswith("cuda"):
            torch.cuda.synchronize()
        report["recon_seconds"] = round(time.time() - t0, 2)
        if device.startswith("cuda"):
            report["vram_peak_gb"] = round(
                torch.cuda.max_memory_allocated() / 1024**3, 2
            )

        # ---- 抽网格 ----
        t0 = self._now()
        meshes = model.extract_mesh(
            scene_codes, not bake_texture, resolution=mc_resolution
        )
        report["extract_seconds"] = round(time.time() - t0, 2)
        mesh = meshes[0]
        report["mesh"] = {
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
        }

        # ---- 导出 ----
        if bake_texture:
            import xatlas
            from tsr.bake_texture import bake_texture

            t0 = self._now()
            bake_output = bake_texture(
                mesh, model, scene_codes[0], texture_resolution
            )
            report["bake_seconds"] = round(time.time() - t0, 2)
            out_obj = os.path.join(outdir, "raw.obj")
            out_tex = os.path.join(outdir, "texture.png")
            xatlas.export(
                out_obj,
                mesh.vertices[bake_output["vmapping"]],
                bake_output["indices"],
                bake_output["uvs"],
                mesh.vertex_normals[bake_output["vmapping"]],
            )
            Image.fromarray(
                (bake_output["colors"] * 255.0).astype(np.uint8)
            ).transpose(Image.FLIP_TOP_BOTTOM).save(out_tex)
            report["outputs"] = ["raw.obj", "texture.png"]
        else:
            out_glb = os.path.join(outdir, "raw.glb")
            mesh.export(out_glb)
            report["outputs"] = ["raw.glb"]

        return report
