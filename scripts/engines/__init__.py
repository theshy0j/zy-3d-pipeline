"""引擎抽象层（插件式）。

设计目标：把“单图→3D 网格”的引擎调用收口成统一接口，
后续接入 Hunyuan3D-2.1 / SF3D / TRELLIS 等新引擎时，只需在 engines/ 下新增一个
实现文件并在 _ENGINES 注册，run_recon.py 与上层脚本无需改动默认路径。

默认引擎：triposr（TripoSR，已随仓库验证）。
新增引擎示例：engines/hunyuan3d.py 继承 ReconEngine，实现 load/process，
然后在下方 _ENGINES 注册 "hunyuan3d" 即可。
"""
from .base import ReconEngine
from .triposr import TripoSREngine

_ENGINES = {
    "triposr": TripoSREngine,
}


def get_engine(name):
    if name not in _ENGINES:
        raise ValueError(
            f"未知引擎 '{name}'。可用：{', '.join(_ENGINES.keys())}"
        )
    return _ENGINES[name]


__all__ = ["ReconEngine", "TripoSREngine", "get_engine"]
