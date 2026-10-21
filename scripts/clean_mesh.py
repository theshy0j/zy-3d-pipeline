# 在 Blender 中运行（headless）：
#   blender -b --python scripts/clean_mesh.py -- --input samples/building/raw.glb --outdir samples/building
#   blender -b --python scripts/clean_mesh.py -- --input samples/building/raw.obj --texture samples/building/texture.png --outdir samples/building
#
# 输入：TripoSR 的原始产物（raw.glb 顶点色 / raw.obj + texture.png 烘焙贴图）
# 输出（写入 --outdir）：
#   clean.glb / clean.fbx   清理后的资产（FBX 供 3ds Max，GLB 供引擎）
#   clean.json              清理统计（面数前后对比、尺寸、UV/材质、水密性）
import bmesh
import bpy
import json
import math
import os
import sys
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_path(p):
    """相对路径一律按仓库根目录解析成绝对路径。

    为什么必须：Blender 无头模式下 bpy.data.images.load() 对相对路径的解析基准
    不是进程 CWD（未保存的 blend 没有目录基准），传相对路径会 No such file or directory；
    而 obj_import 却按 CWD 解析——同一个脚本里两种行为，最容易踩的半懂不懂坑。
    """
    if p and not os.path.isabs(p):
        return os.path.abspath(os.path.join(REPO, p))
    return p


def find_node(tree, node_type):
    """按类型找节点（中文语言环境下节点名会本地化，只能按 type 找）。"""
    for n in tree.nodes:
        if getattr(n, "type", None) == node_type:
            return n
    raise KeyError(f"node type {node_type} not found")


# ---------- 参数 ----------
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OPTS = {}
for i, a in enumerate(argv):
    if a.startswith("--"):
        OPTS[a[2:]] = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else True
IN_PATH = repo_path(OPTS.get("input"))
OUTDIR = repo_path(OPTS.get("outdir", "."))
TEXTURE = repo_path(OPTS.get("texture"))
TARGET_SIZE = float(OPTS.get("target-size", 1.0))
if not IN_PATH:
    print("ERROR: 需要 --input", file=sys.stderr)
    sys.exit(1)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_mesh(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"不支持的格式: {ext}")
    return [o for o in bpy.context.selected_objects if o.type == "MESH"]


def color_attr_name(me):
    """找到网格上的顶点色属性名（glTF 导入的 COLOR_0 在 Blender 里通常叫 Color）。"""
    for name in ("Color", "Col", "color", "Attribute"):
        if name in me.attributes:
            return name
    for attr in me.attributes:
        if attr.data_type == "BYTE_COLOR" or attr.domain == "POINT" and attr.data_type in ("FLOAT_COLOR", "BYTE_COLOR"):
            return attr.name
    return None


def build_vertex_color_material(me):
    """顶点色资产：自制材质，把顶点色节点接到 Base Color。"""
    attr = color_attr_name(me)
    if not attr:
        return None
    m = bpy.data.materials.new("VC_Material")
    m.use_nodes = True
    bsdf = find_node(m.node_tree, "BSDF_PRINCIPLED")
    vc = m.node_tree.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = attr
    m.node_tree.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def build_texture_material(me, texture_path):
    """烘焙资产：自制材质，接 image texture 节点。"""
    if not os.path.isfile(texture_path):
        return None
    img = bpy.data.images.load(texture_path)
    m = bpy.data.materials.new("Tex_Material")
    m.use_nodes = True
    bsdf = find_node(m.node_tree, "BSDF_PRINCIPLED")
    tex = m.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def clean_object(obj, merge_dist=1e-4):
    """bmesh 清理：合并重合顶点、删孤立顶点、重算法线。返回统计。"""
    me = obj.data
    before_v, before_f = len(me.vertices), len(me.polygons)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return {
        "verts_before": before_v,
        "verts_after": len(me.vertices),
        "faces_before": before_f,
        "faces_after": len(me.polygons),
        "boundary_edges": len(boundary_edges),
        "watertight": len(boundary_edges) == 0,
    }


def normalize_object(obj, target_size):
    """等比缩放到 target_size（最大边），并落到原点（xy 居中、z 贴地）。"""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bb = [Vector(c) for c in obj.bound_box]
    dims = Vector((
        max(c[0] for c in bb) - min(c[0] for c in bb),
        max(c[1] for c in bb) - min(c[1] for c in bb),
        max(c[2] for c in bb) - min(c[2] for c in bb),
    ))
    max_dim = max(dims)
    if max_dim <= 0:
        return dims
    scale = target_size / max_dim
    obj.scale = (scale, scale, scale)
    bpy.ops.object.transform_apply(scale=True)
    # 重新取包围盒并平移
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    center = Vector((
        (min(c[0] for c in bb) + max(c[0] for c in bb)) / 2,
        (min(c[1] for c in bb) + max(c[1] for c in bb)) / 2,
        min(c[2] for c in bb),
    ))
    obj.location = obj.location - center
    bpy.ops.object.transform_apply(location=True)
    bb2 = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return Vector((
        max(c[0] for c in bb2) - min(c[0] for c in bb2),
        max(c[1] for c in bb2) - min(c[1] for c in bb2),
        max(c[2] for c in bb2) - min(c[2] for c in bb2),
    ))


def _op_ready(module, name):
    """Blender 的算子属性是动态生成的：hasattr 对未注册算子也返回 True（调用时才炸），
    必须用 poll() 抛不抛异常来判断（实测 4.5.3：wm.fbx_export poll 抛 AttributeError，
    export_scene.fbx poll 返回 True）。"""
    try:
        return bool(getattr(module, name).poll())
    except Exception:
        return False


def export_fbx(path):
    """FBX 导出：优先新算子 wm.fbx_export（Blender 4.1+），没有则回退旧版 export_scene.fbx。

    注意：Blender 4.5.3 LTS 实测只有 wm.fbx_import、没有 wm.fbx_export，
    而 io_scene_fbx 插件（export_scene.fbx）是启用状态——所以必须两条路都留。
    """
    if _op_ready(bpy.ops.wm, "fbx_export"):
        bpy.ops.wm.fbx_export(filepath=path, path_mode="COPY")
    else:
        bpy.ops.export_scene.fbx(filepath=path, path_mode="COPY")


def main():
    reset()
    os.makedirs(OUTDIR, exist_ok=True)
    objs = import_mesh(IN_PATH)
    if not objs:
        print("ERROR: 没导入任何网格", file=sys.stderr)
        sys.exit(1)
    obj = objs[0]
    if len(objs) > 1:
        print(f"[clean_mesh] 警告：导入 {len(objs)} 个网格，只清理第一个")

    stats = clean_object(obj)

    me = obj.data
    uv_layers = [uv.name for uv in me.uv_layers]
    has_vc = color_attr_name(me) is not None

    # 顶点色资产：确保有材质接线（UV 用 smart_project 补一个通道）
    if TEXTURE:
        m = build_texture_material(me, TEXTURE)
        if m:
            me.materials.append(m)
    elif has_vc:
        m = build_vertex_color_material(me)
        if m:
            me.materials.append(m)
        if not uv_layers:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
            bpy.ops.object.mode_set(mode="OBJECT")
            uv_layers = [uv.name for uv in me.uv_layers]
            stats["uv_generated"] = "smart_project（顶点色资产的占位 UV，未烘焙贴图）"
        else:
            stats["uv_generated"] = "none（沿用导入 UV）"
    else:
        stats["uv_generated"] = "none（无顶点色也无贴图）"

    dims = normalize_object(obj, TARGET_SIZE)

    out_glb = os.path.join(OUTDIR, "clean.glb")
    out_fbx = os.path.join(OUTDIR, "clean.fbx")
    bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", export_apply=True)
    export_fbx(out_fbx)

    stats.update({
        "input": os.path.relpath(IN_PATH, os.path.dirname(OUTDIR) or "."),
        "dims_after_normalize_m": [round(d, 4) for d in dims],
        "target_size_m": TARGET_SIZE,
        "uv_layers": uv_layers,
        "has_vertex_colors": has_vc,
        "texture": os.path.relpath(TEXTURE, os.path.dirname(OUTDIR)) if TEXTURE else None,
        "outputs": ["clean.glb", "clean.fbx"],
    })
    with open(os.path.join(OUTDIR, "clean.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
