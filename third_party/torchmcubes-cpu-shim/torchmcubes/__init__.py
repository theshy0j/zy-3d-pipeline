"""CPU-only torchmcubes shim.

为什么存在：tatsy/torchmcubes 的 PyPI 上没有预编译轮子，源码安装需要
MSVC + CUDA toolkit。很多 Windows 装机两者皆无（本仓库的目标机器就是）。
TripoSR 的 tsr/models/isosurface.py 顶层 `from torchmcubes import marching_cubes`，
没有这个包连 import 都过不去。

实现：numpy + PyMCubes（无 PyMCubes 时退回 scikit-image）。
API 与 torchmcubes.marching_cubes 对齐：接收 CPU float 张量，返回
(vertices float32, faces int64)。

刻意设计：传入 CUDA 张量时抛 AttributeError —— TripoSR 的
MarchingCubeHelper.forward() 正好捕获 AttributeError 并用 CPU 张量重试
（见 third_party/TripoSR/tsr/models/isosurface.py 第 45-49 行），
于是走官方预留的 CPU 回退分支，无需改 TripoSR 一行代码。
"""

from ._cpu import marching_cubes

__version__ = "0.0.1+cpu-shim"
__all__ = ["marching_cubes"]
