# 在 Blender 中运行：blender -b --python scripts/gen_inputs.py -- --out <仓库根目录>
# 生成三张占位输入图（建筑/室内/家具），全部程序化建模，不含任何第三方资产（CC0）。
# 正式投产时把 samples/<case>/input.png 换成你自己的照片即可，其余脚本不用动。
import bpy
import math
import os
import sys
from mathutils import Vector


def find_node(tree, node_type):
    """按类型找节点（不能按名字：中文语言环境下节点名是本地化的，如'原理化 BSDF'）。"""
    for n in tree.nodes:
        if getattr(n, "type", None) == node_type:
            return n
    raise KeyError(f"node type {node_type} not found")


# ---------- 参数 ----------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = None
if "--out" in argv:
    OUT = argv[argv.index("--out") + 1]
if not OUT:
    OUT = REPO
elif not os.path.isabs(OUT):
    # 相对路径按仓库根目录解析（Blender 对相对路径的解析基准不可靠）
    OUT = os.path.abspath(os.path.join(REPO, OUT))
RES = 768


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, color, rough=0.8, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = find_node(m.node_tree, "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    return m


def cube(name, loc, scale, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    return o


def cyl(name, loc, radius, depth, material, rot=(0, 0, 0), verts=24):
    bpy.ops.mesh.primitive_cylinder_add(location=loc, rotation=rot, vertices=verts)
    o = bpy.context.object
    o.name = name
    o.scale = (radius, radius, depth)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    return o


def cone(name, loc, r1, r2, depth, material, verts=32, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(
        location=loc, rotation=rot, vertices=verts, radius1=r1, radius2=r2, depth=depth
    )
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    return o


def sphere(name, loc, radius, material, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(location=loc, segments=24, ring_count=16)
    o = bpy.context.object
    o.name = name
    o.scale = (radius * scale[0], radius * scale[1], radius * scale[2])
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    return o


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_scene(world_color, strength):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w")
    scene.world = world
    world.use_nodes = True
    bg = find_node(world.node_tree, "BACKGROUND")
    bg.inputs[0].default_value = (*world_color, 1.0)
    bg.inputs[1].default_value = strength
    return scene


def add_camera(scene, loc, target, lens=50):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.object
    cam.data.lens = lens
    look_at(cam, target)
    scene.camera = cam
    return cam


def add_area(scene, loc, target, energy, size, color=(1, 1, 1)):
    bpy.ops.object.light_add(type="AREA", location=loc)
    l = bpy.context.object
    l.data.energy = energy
    l.data.size = size
    l.data.color = color
    look_at(l, target)
    return l


def add_sun(scene, energy, rot, color=(1, 0.98, 0.92)):
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    l = bpy.context.object
    l.data.energy = energy
    l.data.color = color
    l.rotation_euler = rot
    return l


def ground(material, size=120, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    o = bpy.context.object
    o.name = "Ground"
    o.data.materials.append(material)
    return o


def render(scene, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[gen_inputs] written:", path)


# ---------- 场景 1：建筑（小院住宅，日光） ----------
def scene_building():
    reset()
    scene = setup_scene((0.62, 0.70, 0.78), 0.55)
    wall = mat("wall", (0.86, 0.84, 0.79), 0.9)
    wall2 = mat("wall2", (0.78, 0.72, 0.64), 0.9)
    roof = mat("roof", (0.35, 0.30, 0.28), 0.85)
    glass = mat("glass", (0.45, 0.62, 0.72), 0.15, 0.1)
    door = mat("door", (0.28, 0.20, 0.15), 0.7)
    grd = mat("ground", (0.42, 0.45, 0.40), 0.95)
    trunk = mat("trunk", (0.30, 0.22, 0.16), 0.9)
    leaf = mat("leaf", (0.25, 0.42, 0.22), 0.9)

    ground(grd)
    cube("main_block", (0, 0, 3), (4.5, 3.5, 3.0), wall)
    cube("wing_block", (5.2, 1.2, 1.6), (2.6, 2.4, 1.6), wall2)
    cone("roof_main", (0, 0, 6.2), 5.4, 0.0, 2.0, roof, verts=4, rot=(0, math.radians(45), 0))
    cube("door", (0, -3.55, 1.0), (0.5, 0.1, 1.0), door)
    cube("win1", (-2.4, -3.55, 3.2), (0.9, 0.1, 1.0), glass)
    cube("win2", (2.4, -3.55, 3.2), (0.9, 0.1, 1.0), glass)
    cube("win3", (4.5, 0.4, 1.7), (0.1, 0.8, 0.7), glass)
    cube("win4", (4.5, 2.0, 1.7), (0.1, 0.8, 0.7), glass)
    for i, x in enumerate((-7.5, 7.5)):
        cyl(f"trunk{i}", (x, 5.5, 1.2), 0.18, 1.2, trunk)
        sphere(f"leaf{i}", (x, 5.5, 2.8), 1.3, leaf, scale=(1, 1, 1.15))

    add_sun(scene, 3.2, (math.radians(50), math.radians(-15), math.radians(30)))
    add_area(scene, (10, -12, 14), (0, 0, 2), 900, 12, (1.0, 0.96, 0.88))
    add_camera(scene, (13, -14, 9.5), (0.5, 0, 2.2), lens=42)
    render(scene, os.path.join(OUT, "samples", "building", "input.png"))


# ---------- 场景 2：室内（客厅一角，暖光） ----------
def scene_interior():
    reset()
    scene = setup_scene((0.55, 0.52, 0.48), 0.35)
    floor_m = mat("floor", (0.55, 0.40, 0.28), 0.55)
    wall_m = mat("iwall", (0.83, 0.80, 0.74), 0.95)
    wood = mat("wood", (0.45, 0.32, 0.21), 0.6)
    fabric = mat("fabric", (0.55, 0.30, 0.24), 0.95)
    rug_m = mat("rug", (0.62, 0.55, 0.42), 1.0)
    metal = mat("metal", (0.65, 0.62, 0.55), 0.3, 0.9)
    shade = mat("shade", (0.95, 0.90, 0.78), 0.8)

    bpy.ops.mesh.primitive_plane_add(size=16, location=(0, 0, 0))
    fl = bpy.context.object
    fl.data.materials.append(floor_m)
    cube("wall_back", (0, 4, 2.5), (8, 0.15, 2.5), wall_m)
    cube("wall_left", (-4, 0, 2.5), (0.15, 4, 2.5), wall_m)
    cube("rug", (0, 0.5, 0.02), (3.2, 2.2, 0.02), rug_m)
    # 茶几
    cube("table_top", (0, 0, 0.45), (1.1, 0.6, 0.05), wood)
    for i, (x, y) in enumerate(((-0.9, -0.4), (0.9, -0.4), (-0.9, 0.4), (0.9, 0.4))):
        cyl(f"leg{i}", (x, y, 0.22), 0.04, 0.22, wood)
    # 沙发椅
    cube("sofa_base", (0, 2.2, 0.30), (1.5, 0.8, 0.25), fabric)
    cube("sofa_back", (0, 2.6, 0.68), (1.5, 0.2, 0.45), fabric)
    cube("sofa_arm_l", (-1.5, 2.2, 0.55), (0.15, 0.8, 0.5), fabric)
    cube("sofa_arm_r", (1.5, 2.2, 0.55), (0.15, 0.8, 0.5), fabric)
    # 落地灯
    cyl("lamp_pole", (-2.6, 1.6, 0.8), 0.03, 0.8, metal)
    cone("lamp_shade", (-2.6, 1.6, 1.65), 0.28, 0.05, 0.25, shade, verts=24)
    bpy.ops.object.light_add(type="POINT", location=(-2.6, 1.6, 1.55))
    lp = bpy.context.object
    lp.data.energy = 60
    lp.data.color = (1.0, 0.85, 0.65)
    # 挂画
    cube("frame", (0, 3.85, 1.8), (0.9, 0.05, 0.6), metal)
    # 绿植
    cyl("pot", (2.9, -1.2, 0.2), 0.22, 0.4, mat("pot", (0.7, 0.45, 0.35), 0.9))
    for i in range(5):
        sphere(f"plant{i}", (2.9 + 0.12 * math.cos(i), -1.2 + 0.12 * math.sin(i), 0.7 + 0.15 * i),
               0.16, mat(f"leafm{i}", (0.22, 0.40, 0.20), 0.9), scale=(1, 1, 1.6))

    add_area(scene, (6, -6, 7), (0, 0, 1), 1200, 10, (1.0, 0.92, 0.80))
    add_area(scene, (-6, 4, 6), (0, 1, 1), 500, 8, (0.85, 0.90, 1.0))
    add_camera(scene, (5.2, -6.5, 2.6), (0, 0.8, 0.6), lens=30)
    render(scene, os.path.join(OUT, "samples", "interior", "input.png"))


# ---------- 场景 3：家具（白模/黏土风格，摄影棚） ----------
def scene_furniture():
    reset()
    scene = setup_scene((0.75, 0.74, 0.71), 0.5)
    clay = mat("clay", (0.80, 0.79, 0.77), 0.95)
    grd = mat("studio_floor", (0.55, 0.54, 0.52), 0.9)

    ground(grd, size=60)
    # 单人沙发椅：底座 + 坐垫 + 靠背 + 扶手 + 短腿
    cube("chair_base", (0, 0, 0.32), (0.85, 0.80, 0.10), clay)
    cube("chair_seat", (0, 0, 0.47), (0.80, 0.75, 0.10), clay)
    cube("chair_back", (0, 0.38, 0.78), (0.80, 0.12, 0.38), clay, rot=(math.radians(-8), 0, 0))
    cube("chair_arm_l", (-0.44, 0, 0.62), (0.06, 0.70, 0.22), clay)
    cube("chair_arm_r", (0.44, 0, 0.62), (0.06, 0.70, 0.22), clay)
    for i, (x, y) in enumerate(((-0.35, -0.32), (0.35, -0.32), (-0.35, 0.32), (0.35, 0.32))):
        cyl(f"chair_leg{i}", (x, y, 0.08), 0.045, 0.08, clay)

    add_area(scene, (5, -6, 7), (0, 0, 0.4), 1500, 10)              # 主光
    add_area(scene, (-6, -3, 5), (0, 0, 0.4), 600, 8, (0.9, 0.93, 1.0))   # 补光
    add_area(scene, (0, 7, 6), (0, 0, 0.4), 800, 8, (1.0, 0.97, 0.9))     # 轮廓光
    add_camera(scene, (4.2, -5.6, 2.6), (0, 0, 0.5), lens=50)
    render(scene, os.path.join(OUT, "samples", "furniture", "input.png"))


if __name__ == "__main__":
    scene_building()
    scene_interior()
    scene_furniture()
    print("[gen_inputs] all done ->", os.path.join(OUT, "samples"))
