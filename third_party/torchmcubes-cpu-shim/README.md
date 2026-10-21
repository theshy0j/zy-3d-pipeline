# torchmcubes-cpu-shim

Windows 无 MSVC / CUDA toolkit 环境下使用的 **CPU 版 torchmcubes**。

- 提供与 `tatsy/torchmcubes` 相同的 `marching_cubes(volume, threshold)` API；
- 后端优先用 PyMCubes，缺失时退回 scikit-image；
- 对 CUDA 张量刻意抛 `AttributeError`，借 TripoSR 官方预留的 CPU 回退分支工作
  （`third_party/TripoSR/tsr/models/isosurface.py` 第 45–49 行）；
- 性能：256³ 网格 CPU 抽取约 1–3 秒，对本管线（单张资产级重建）可接受。

安装：`pip install ./third_party/torchmcubes-cpu-shim`（bootstrap.ps1 会自动做）。

> ⚠️ **PyPI 包名陷阱**：后端依赖的 PyPI 包名是 **`PyMCubes`**（提供函数式
> `marching_cubes`），**不是** `mcubes`——后者是同导入名的另一个包，提供类式
> `MarchingCubes`，装错了会在运行时报 `module 'mcubes' has no attribute
> 'marching_cubes'`。`requirements.txt` 已锁 `PyMCubes==0.1.6`，装错时先卸载再装对。
