"""patch_triposr.py — 对 vendored TripoSR 打补丁（幂等，可重复跑）。

补丁分三类：
  1. tsr/utils.py: rembg 顶层 import -> remove_background() 内惰性 import。
     （不去背景的路径因此不需要 onnxruntime + u2net 权重）
  2. run.py: rembg / xatlas 顶层 import -> 各自使用处惰性 import。
     （不烘焙贴图的路径因此不需要 xatlas）
  3. tsr/bake_texture.py: positions_to_colors 有两处 GPU 不兼容（上游 bug，
     TripoSR 官方 run.py --bake-texture 在 GPU 上同样会中招，这路径上游只在 CPU 上跑过）：
     a. torch.tensor(...) 造的是 CPU 张量，喂给 CUDA 上的 decoder 会 grid_sample 设备错位；
     b. queried_grid["color"].numpy() 对 CUDA 张量直接 .numpy() 会 TypeError。
     分别补 .to(scene_code.device) 和 .cpu()，两行，不改任何数学逻辑。

用法：.venv\\Scripts\\python.exe scripts\\patch_triposr.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSR = os.path.join(REPO, "third_party", "TripoSR")


def patch(path, replacements):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    changed = 0
    for old, new in replacements:
        if old in src:
            src = src.replace(old, new, 1)
            changed += 1
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    return changed


def main():
    if not os.path.isdir(TSR):
        print("ERROR: third_party/TripoSR 不存在，先跑 bootstrap.ps1", file=sys.stderr)
        sys.exit(1)

    utils_py = os.path.join(TSR, "tsr", "utils.py")
    run_py = os.path.join(TSR, "run.py")
    bake_py = os.path.join(TSR, "tsr", "bake_texture.py")

    n1 = patch(utils_py, [
        ("import imageio\nimport numpy as np\nimport PIL.Image\nimport rembg\nimport torch",
         "import imageio\nimport numpy as np\nimport PIL.Image\nimport torch"),
        ("    if do_remove:\n        image = rembg.remove(image, session=rembg_session, **rembg_kwargs)",
         "    if do_remove:\n        import rembg\n\n        image = rembg.remove(image, session=rembg_session, **rembg_kwargs)"),
    ])

    n2 = patch(run_py, [
        ("import numpy as np\nimport rembg\nimport torch\nimport xatlas\nfrom PIL import Image",
         "import numpy as np\nimport torch\nfrom PIL import Image"),
        ("else:\n    rembg_session = rembg.new_session()",
         "else:\n    import rembg\n\n    rembg_session = rembg.new_session()"),
        ('    if args.bake_texture:\n        out_texture_path = os.path.join(output_dir, str(i), "texture.png")',
         '    if args.bake_texture:\n        import xatlas\n\n        out_texture_path = os.path.join(output_dir, str(i), "texture.png")'),
    ])

    n3 = patch(bake_py, [
        # 幂等关键：old 串必须带行尾 \n——打完补丁后该行变成 "...[:-1]).to(...)\n"，
        # 不带 \n 的旧串仍是新行子串，会被重复替换（第一版就踩了这个坑）。
        # 先折叠可能的历史重复，再打补丁。
        ("[:, :-1]).to(scene_code.device).to(scene_code.device)\n",
         "[:, :-1]).to(scene_code.device)\n"),
        ("    positions = torch.tensor(positions_texture.reshape(-1, 4)[:, :-1])\n",
         "    positions = torch.tensor(positions_texture.reshape(-1, 4)[:, :-1]).to(scene_code.device)\n"),
        # 注意这行在 with 块外，是 4 空格缩进（不是 8）
        ('    rgb_f = queried_grid["color"].numpy().reshape(-1, 3)\n',
         '    rgb_f = queried_grid["color"].cpu().numpy().reshape(-1, 3)\n'),
    ])

    # 校验：顶层不应再出现裸 import rembg / import xatlas；补丁 3 必须生效
    with open(utils_py, encoding="utf-8") as f:
        u = f.read()
    with open(run_py, encoding="utf-8") as f:
        r = f.read()
    with open(bake_py, encoding="utf-8") as f:
        b = f.read()
    problems = []
    if "import rembg\n" in u and "import rembg\n\n        image" not in u:
        problems.append("utils.py 仍残留顶层 import rembg")
    for line in r.splitlines():
        if line in ("import rembg", "import xatlas"):
            problems.append(f"run.py 仍残留顶层 {line}")
    if ".to(scene_code.device)" not in b or ".to(scene_code.device).to(" in b:
        problems.append("bake_texture.py 设备补丁 a 未生效或重复应用")
    if '.cpu().numpy().reshape(-1, 3)' not in b:
        problems.append("bake_texture.py 设备补丁 b 未生效")
    if problems:
        print("ERROR:", "; ".join(problems), file=sys.stderr)
        sys.exit(1)

    print(f"[patch_triposr] utils.py 应用 {n1} 处，run.py 应用 {n2} 处，bake_texture.py 应用 {n3} 处（0 处表示此前已打过）")


if __name__ == "__main__":
    main()
