import numpy as np
import torch

_BACKEND = None


def _backend():
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    try:
        import mcubes  # PyMCubes fork，PyPI 有发行版

        _BACKEND = ("mcubes", mcubes)
        return _BACKEND
    except ImportError:
        pass
    from skimage import measure  # scikit-image 兜底

    _BACKEND = ("skimage", measure)
    return _BACKEND


def marching_cubes(level: torch.Tensor, threshold: float):
    """与 torchmcubes.marching_cubes 兼容的 CPU 实现。

    level: (R, R, R) 的 float 张量（必须已在 CPU 上）
    返回: (vertices (N,3) float32, faces (M,3) int64)
    """
    if level.is_cuda:
        # 触达 TripoSR 的 CPU 回退分支：它捕获 AttributeError 后会用 CPU 张量重试。
        raise AttributeError(
            "torchmcubes-cpu-shim: CUDA tensor not supported; "
            "caller is expected to retry on CPU (TripoSR does)."
        )
    vol = np.ascontiguousarray(level.detach().cpu().numpy(), dtype=np.float32)
    name, mod = _backend()
    if name == "mcubes":
        verts, faces = mod.marching_cubes(vol, threshold)
    else:
        verts, faces, _norms, _vals = mod.marching_cubes(vol, level=threshold)
    return (
        torch.from_numpy(np.ascontiguousarray(verts, dtype=np.float32)),
        torch.from_numpy(np.ascontiguousarray(faces, dtype=np.int64)),
    )
