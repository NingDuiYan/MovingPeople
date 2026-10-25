# -*- coding: utf-8 -*-
"""导出 Three.js 兼容 GLB（+Y Up、含材质/法线、不含灯光/相机/体积雾）。

glTF 无法表达程序化节点，Base Color 一旦接了节点图，导出器就不写 baseColorFactor，
模型在 Three.js 里会变成纯白。所以导出前把材质临时"压平"成 PBR 常数：
断开 Base Color / Roughness / Metallic 的输入连线，写入手工标定的代表色，
导出后原样恢复（场景外观不受影响）。
"""
import bpy, os, json, struct

OUT_DIR = r"C:\Users\ning\Desktop\MovingPeople\wasteland-blender\export"
OUT_GLB = os.path.join(OUT_DIR, "wasteland_scene.glb")
OUT_MODELS = os.path.join(OUT_DIR, "models")
BLEND_COPY = os.path.join(OUT_DIR, "wasteland_scene.blend")
EXCLUDE = ("wst_volume_fog", "wst_volume_dust")

# 单件交付：小游戏要按模型单独加载（树可交互、车是障碍、废墟是建筑、地面负责碰撞），
# 合并成一个 GLB 既不能按需加载，也让 145 个节点变成 145 次 draw call。
# 组内所有对象合并成一个网格（材质槽保留，导出后仍按材质拆 primitive）。
GROUPS = (
    ("tree", ("wst_ext_tree",)),
    ("house", ("wst_ext_house",)),
    ("car", ("wst_ext_car",)),
    ("ground", ("wst_terrain", "wst_bg", "wst_rootmound", "wst_prop")),
)

# 有真贴图的材质：Base Color 必须保留 Image Texture 连线（压平会让地面退回塑料色）
KEEP_BASE = {"wst_mat_sand"}

# 材质名 → (baseColor linear, roughness, metallic)；None 表示沿用在用值
FLAT = {
    # 沙地：与 wst_ground.SAND_GAIN=1.30 对应提亮，否则浏览器里比 Blender 暗一档
    "wst_mat_sand":        ((0.546, 0.390, 0.260), 0.95, 0.0),
    "wst_mat_concrete":    ((0.260, 0.250, 0.235), 0.90, 0.0),
    "wst_mat_brick":       ((0.190, 0.140, 0.108), 0.92, 0.0),
    "wst_mat_rebar":       ((0.085, 0.040, 0.022), 0.88, 0.25),
    "wst_mat_wood":        ((0.195, 0.148, 0.105), 0.86, 0.0),
    "wst_mat_rock":        ((0.150, 0.140, 0.128), 0.92, 0.0),
    "wst_mat_ridge":       ((0.320, 0.220, 0.140), 0.95, 0.0),
    "wst_mat_rust":        ((0.180, 0.080, 0.040), 0.85, 0.2),
    "wst_mat_glass":       ((0.040, 0.050, 0.050), 0.20, 0.0),
    "wst_mat_car_paint":   ((0.095, 0.044, 0.028), 0.75, 0.15),   # 与 wst_car._paint() 的主锈同步压暗
    "wst_mat_car_glass":   ((0.085, 0.092, 0.098), 0.42, 0.0),
    "wst_mat_car_cavity":  ((0.020, 0.017, 0.014), 0.96, 0.0),
    "wst_mat_car_chrome":  ((0.100, 0.085, 0.070), 0.72, 0.45),
    "wst_mat_car_hub":     ((0.085, 0.042, 0.026), 0.78, 0.12),
    "wst_mat_car_trim":    ((0.017, 0.015, 0.013), 0.80, 0.30),
    "wst_mat_car_flake":   ((0.058, 0.030, 0.020), 0.90, 0.10),   # 翘起的锈片
    "wst_mat_tire":        ((0.020, 0.019, 0.018), 0.92, 0.0),
    "wst_mat_opening":     ((0.012, 0.011, 0.010), 0.94, 0.0),   # 窗洞内暗部
}


def _bsdf(mat):
    if not mat.use_nodes:
        return None
    return next((n for n in mat.node_tree.nodes
                 if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)


def _flatten():
    """返回可用于恢复的连线快照。"""
    saved = []
    for name, spec in FLAT.items():
        mat = bpy.data.materials.get(name)
        if mat is None:
            continue
        bsdf = _bsdf(mat)
        if bsdf is None:
            continue
        col, rough, metal = spec
        for key, val in (("Base Color", col), ("Roughness", rough), ("Metallic", metal)):
            if key == "Base Color" and name in KEEP_BASE:
                continue
            sock = bsdf.inputs.get(key)
            if sock is None:
                continue
            for l in list(mat.node_tree.links):
                if l.to_socket == sock:
                    saved.append((l.from_socket, l.to_socket))
                    mat.node_tree.links.remove(l)
            if key == "Base Color":
                sock.default_value = (val[0], val[1], val[2], 1.0)
            else:
                sock.default_value = val
    return saved


def _restore(saved):
    for from_s, to_s in saved:
        to_s.node.id_data.links.new(from_s, to_s)


def _select():
    bpy.ops.object.select_all(action="DESELECT")
    n = 0
    for o in bpy.data.objects:
        if o.type != "MESH" or o.name in EXCLUDE:
            continue
        o.select_set(True)
        n += 1
    bpy.context.view_layer.objects.active = bpy.data.objects["wst_terrain_ground"]
    return n


def _match(ob, prefixes):
    if ob.type != "MESH" or ob.name in EXCLUDE:
        return False
    return any(ob.name == p or ob.name.startswith(p) for p in prefixes)


def _isolate(objs, name):
    """复制一组对象并合并成单个网格，原场景不受影响。

    先 duplicate 再 convert：join 不会应用非活动对象的修改器，直接合并会丢几何。
    """
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.duplicate()
    dups = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.select_all(action="DESELECT")
    for d in dups:
        d.select_set(True)
    bpy.context.view_layer.objects.active = dups[0]
    if len(dups) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


def _draco_kwargs():
    """Draco 让 7.8 万三角的几何压到 1/5，移动端首屏才吃得消。

    不同 Blender 版本参数名有差异，取不到就退回不压缩（宁可大也不要导出失败）。
    """
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    if "export_draco_mesh_compression_enable" not in props:
        return {}
    return {
        "export_draco_mesh_compression_enable": True,
        "export_draco_mesh_compression_level": 6,
    }


def _export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_normals=True,
        export_texcoords=True,
        export_lights=False,
        export_cameras=False,
        export_animations=False,
        export_extras=False,
        # 扫描资产的贴图在 Blender 里被重新编码成 PNG（单张 5 MB），
        # JPEG 才能把 2048² 压到几百 KB 量级；不用 WEBP 是为了免掉扩展依赖
        export_image_format="JPEG",
        export_image_quality=82,
        **_draco_kwargs(),
    )


def build_split():
    """按组导出单件 GLB（交付路径）。返回每个文件的统计。"""
    os.makedirs(OUT_MODELS, exist_ok=True)
    saved = _flatten()
    models = {}
    try:
        for name, prefixes in GROUPS:
            src = [o for o in bpy.data.objects if _match(o, prefixes)]
            if not src:
                raise RuntimeError("空模型组：" + name)
            tmp = _isolate(src, name)
            path = os.path.join(OUT_MODELS, name + ".glb")
            _export(path, [tmp])
            st = _glb_stats(path)
            st["source_objects"] = len(src)
            models[name] = st
            bpy.data.objects.remove(tmp, do_unlink=True)
    finally:
        _restore(saved)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_COPY, copy=True)
    return {"models": models, "blend": BLEND_COPY}


CHAR_GLB = os.path.join(OUT_MODELS, "character.glb")
CHAR_RIG = "wst_char_rig"
CHAR_BODY = "wst_char_body"


def _export_character(path):
    """角色是唯一带骨骼与动作的资产：不能压平材质（贴图要带上），
    也不能开 export_apply（会把 Armature 修改器烘掉、绑定失效）。"""
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = {
        "filepath": path,
        "export_format": "GLB",
        "use_selection": True,
        "export_apply": False,
        "export_yup": True,
        "export_materials": "EXPORT",
        "export_normals": True,
        "export_texcoords": True,
        "export_lights": False,
        "export_cameras": False,
        "export_skins": True,
        "export_animations": True,
        "export_image_format": "JPEG",
        "export_image_quality": 82,
        "export_extras": False,
    }
    # 动作要一个个导成独立 animation，ACTIONS 模式才会扫 NLA 里全部 action
    for key, val in (("export_animation_mode", "ACTIONS"),
                     ("export_bake_animation", False),
                     ("export_anim_single_armature", True),
                     ("export_optimize_animation_size", True),
                     ("export_anim_slide_to_zero", True),
                     ("export_frame_range", False)):
        if key in props:
            kw[key] = val
    kw.update(_draco_kwargs())
    bpy.ops.export_scene.gltf(**kw)


def build_character():
    """导出 character.glb（单网格 + 骨架 + 12 个动作）。"""
    os.makedirs(OUT_MODELS, exist_ok=True)
    rig = bpy.data.objects.get(CHAR_RIG)
    body = bpy.data.objects.get(CHAR_BODY)
    if rig is None or body is None:
        raise RuntimeError("缺 %s / %s，先跑 wst_char.build + wst_char_rig.build + join_body" % (CHAR_RIG, CHAR_BODY))
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = rig
    _export_character(CHAR_GLB)
    st = _glb_stats(CHAR_GLB)
    st["animations"] = _glb_anims(CHAR_GLB)
    st["skins"] = _glb_count(CHAR_GLB, "skins")
    return st


def _glb_json(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"glTF", "不是 GLB"
    ln = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + ln].decode("utf-8"))


def _glb_count(path, key):
    return len(_glb_json(path).get(key, []))


def _glb_anims(path):
    out = []
    for a in _glb_json(path).get("animations", []):
        out.append({"name": a.get("name", ""), "channels": len(a.get("channels", [])),
                    "samplers": len(a.get("samplers", []))})
    return out


def _glb_stats(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"glTF", "不是 GLB"
    ln = struct.unpack("<I", data[12:16])[0]
    js = json.loads(data[20:20 + ln].decode("utf-8"))
    tris = 0
    for m in js.get("meshes", []):
        for p in m.get("primitives", []):
            if "indices" in p:
                tris += js["accessors"][p["indices"]]["count"] // 3
    flat = sum(1 for m in js.get("materials", []) if "baseColorFactor" in m.get("pbrMetallicRoughness", {}))
    return {"bytes": len(data), "meshes": len(js.get("meshes", [])),
            "draco": "KHR_draco_mesh_compression" in js.get("extensionsUsed", []),
            "materials": len(js.get("materials", [])), "with_basecolor": flat,
            "nodes": len(js.get("nodes", [])), "tris": tris,
            "images": len(js.get("images", [])),
            "lights": "KHR_lights_punctual" in js.get("extensionsUsed", [])}


def build_merged():
    """整场景单文件版（仅存档/对照用，交付走 build_split）。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    n = _select()
    saved = _flatten()
    try:
        _export(OUT_GLB, [o for o in bpy.data.objects
                         if o.type == "MESH" and o.name not in EXCLUDE])
    finally:
        _restore(saved)
    stats = _glb_stats(OUT_GLB)
    stats["selected_objects"] = n
    stats["restored_links"] = len(saved)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_COPY, copy=True)
    stats["blend"] = BLEND_COPY
    return stats


if __name__ == "__main__":
    print(json.dumps(build_split(), ensure_ascii=False))