# 在 Blender 中运行（headless）：渲染清理后资产的 After 图
#   blender -b --python scripts/render_before_after.py -- --input samples/building/clean.glb --outdir samples/building
# 说明：相机用固定的 3/4 视角，与 gen_inputs.py 的取景逻辑一致，
#       保证 Before（输入图）与 After（重建资产）构图可比。
import bpy
import math
import os
import sys
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_path(p):
    """相对路径按仓库根目录解析成绝对路径（Blender 对相对路径的解析基准不可靠，见 clean_mesh.py 同款说明）。"""
    if p and not os.path.isabs(p):
        return os.path.abspath(os.path.join(REPO, p))
    return p


def find_node(tree, node_type):
    """按类型找节点（中文语言环境下节点名会本地化，只能按 type 找）。"""
    for n in tree.nodes:
        if getattr(n, "type", None) == node_type:
            return n
    raise KeyError(f"node type {node_type} not found")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OPTS = {}
for i, a in enumerate(argv):
    if a.startswith("--"):
        OPTS[a[2:]] = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else True
IN_PATH = repo_path(OPTS.get("input"))
OUTDIR = repo_path(OPTS.get("outdir", "."))
RES = int(OPTS.get("res", 768))
if not IN_PATH:
    print("ERROR: 需要 --input", file=sys.stderr)
    sys.exit(1)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, color, rough=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = find_node(m.node_tree, "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main():
    reset()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    world = bpy.data.worlds.new("w")
    scene.world = world
    world.use_nodes = True
    # 注意：不能按名字 nodes["Background"]——中文语言环境下显示名是「背景」，只能按类型找
    bg = find_node(world.node_tree, "BACKGROUND")
    bg.inputs[0].default_value = (0.93, 0.92, 0.90, 1.0)
    bg.inputs[1].default_value = 0.6

    bpy.ops.import_scene.gltf(filepath=IN_PATH)
    objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not objs:
        print("ERROR: 没导入网格", file=sys.stderr)
        sys.exit(1)
    obj = objs[0]

    # 世界包围盒
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    center = Vector((
        sum(c[0] for c in bb) / 8, sum(c[1] for c in bb) / 8, sum(c[2] for c in bb) / 8,
    ))
    dims = Vector((
        max(c[0] for c in bb) - min(c[0] for c in bb),
        max(c[1] for c in bb) - min(c[1] for c in bb),
        max(c[2] for c in bb) - min(c[2] for c in bb),
    ))
    max_dim = max(dims) or 1.0

    # 地台（接阴影，让资产不悬空）
    bpy.ops.mesh.primitive_plane_add(size=max_dim * 12, location=(center[0], center[1], min(c[2] for c in bb)))
    ground = bpy.context.object
    ground.data.materials.append(mat("stage", (0.75, 0.74, 0.72)))

    # 相机：与 gen_inputs 相同的 3/4 机位，距离按包围盒自适应
    fov = math.radians(39.6)  # 50mm 全画幅对应
    dist = (max_dim / 2.0) / math.tan(fov / 2.0) * 1.35
    cam_loc = center + Vector((0.75, -1.0, 0.62)).normalized() * dist
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.object
    cam.data.lens = 50
    look_at(cam, center)
    scene.camera = cam

    def area(loc, energy, size, color=(1, 1, 1)):
        bpy.ops.object.light_add(type="AREA", location=loc)
        l = bpy.context.object
        l.data.energy = energy
        l.data.size = size
        l.data.color = color
        look_at(l, center)

    area(cam_loc + Vector((1, 0, 1)) * max_dim, 1200, max_dim * 1.2)
    area(center + Vector((-1.4, -0.8, 1.6)) * max_dim, 500, max_dim, (0.92, 0.95, 1.0))
    area(center + Vector((0, 1.6, 1.2)) * max_dim, 700, max_dim, (1.0, 0.97, 0.9))

    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "after.png")
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[render_before_after] written:", out)


if __name__ == "__main__":
    main()
