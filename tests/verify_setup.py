"""环境自检：新机器装完后跑一遍，确认管线依赖齐全。

用法：
    .venv\\Scripts\\python.exe tests\\verify_setup.py
输出：
    tests\\verify_report.json（同时打印到 stdout）
退出码：0 = 全部必需项通过；1 = 有必需项失败
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []


def check(name, ok, detail, required=True):
    results.append({"name": name, "ok": bool(ok), "detail": detail, "required": required})
    print(("PASS" if ok else ("FAIL" if required else "WARN")), "-", name, ":", detail)


def main():
    # 1. Python 版本
    v = sys.version_info
    check("python>=3.10", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}")

    # 2. torch + CUDA + 显存
    try:
        import torch
        cuda = torch.cuda.is_available()
        detail = f"torch {torch.__version__}, cuda {torch.version.cuda}, avail={cuda}"
        if cuda:
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            name = torch.cuda.get_device_name(0)
            detail += f", {name} {total:.1f}GB"
            check("torch.cuda>=10GB", total >= 10, detail)
        else:
            check("torch.cuda", False, detail + "（TripoSR 需要 CUDA）")
    except ImportError as e:
        check("torch import", False, str(e))

    # 3. 其余 Python 依赖
    for mod in ("PIL", "numpy", "trimesh", "transformers", "huggingface_hub"):
        try:
            __import__(mod)
            check(f"import {mod}", True, "ok")
        except ImportError:
            check(f"import {mod}", False, "未安装（见 requirements.txt）", required=mod in ("PIL", "numpy", "trimesh", "transformers", "huggingface_hub"))

    # 4. xatlas（bake-texture 用；缺失时 clean_mesh 走 Blender 投影烘焙兜底）
    try:
        import xatlas
        check("import xatlas", True, "ok（--bake-texture 可用）")
    except ImportError:
        check("import xatlas", False, "未安装：TripoSR --bake-texture 不可用，将走顶点色路径", required=False)

    # 5. Blender（优先 BLENDER_BIN 环境变量，其次 PATH）
    blender = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if blender:
        try:
            out = subprocess.run([blender, "--version"], capture_output=True, text=True, timeout=120)
            first = (out.stdout or "").splitlines()[0] if out.stdout else "?"
            check("blender --version", True, first)
        except Exception as e:
            check("blender --version", False, str(e))
    else:
        check("blender in PATH", False, "未找到 blender（可设置 BLENDER_BIN 环境变量指向 blender.exe；清理/渲染/导出阶段需要）")

    # 6. TripoSR 源码
    tsr = os.path.join(REPO, "third_party", "TripoSR", "run.py")
    check("third_party/TripoSR", os.path.isfile(tsr), "存在" if os.path.isfile(tsr) else "缺失：先跑 scripts/bootstrap.ps1")

    # 7. 模型权重缓存（缺失不算失败，首次推理会自动下载）
    cache = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    cached = os.path.isdir(os.path.join(cache, "models--stabilityai--TripoSR"))
    check("TripoSR weights cached", cached, "已缓存" if cached else "未缓存（首次推理自动下载约 1.6GB）", required=False)

    # 汇总
    failed_required = [r for r in results if r["required"] and not r["ok"]]
    report = {
        "repo": REPO,
        "passed": all(r["ok"] for r in results if r["required"]),
        "failed_required": [r["name"] for r in failed_required],
        "results": results,
    }
    out = os.path.join(REPO, "tests", "verify_report.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nverify_report.json ->", out)
    print("RESULT:", "PASS" if not failed_required else "FAIL")
    sys.exit(0 if not failed_required else 1)


if __name__ == "__main__":
    main()
