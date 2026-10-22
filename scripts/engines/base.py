"""ReconEngine — 重建引擎抽象基类。

子类只需实现：
    load(self, model_id)      # 加载模型权重到 self.model（只做一次）
    process(self, input_path, outdir, **opts)  # 处理单张输入，返回 report dict

共享模型：run_recon.py 在批量模式下只对引擎调用一次 load()，
随后对每张图调用 process()，从而省去重复初始化开销。
"""
import os
import time


class ReconEngine:
    name = "base"

    def __init__(self, device="cuda:0", chunk_size=8192, **opts):
        self.device = device
        self.chunk_size = chunk_size
        self.opts = opts
        self.model = None
        self.init_seconds = None

    def load(self, model_id):
        raise NotImplementedError

    def process(self, input_path, outdir, **opts):
        raise NotImplementedError

    @staticmethod
    def _now():
        return time.time()

    @staticmethod
    def _resolve_device(preferred):
        """有 CUDA 用 CUDA，否则落 CPU。子类可在 load 前调用。"""
        try:
            import torch
            return preferred if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
