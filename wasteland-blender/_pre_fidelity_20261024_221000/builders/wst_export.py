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
BLEND_COPY = os.path.join(OUT_DIR, "wasteland_scene.blend")
EXCLUDE = ("wst_volume_fog", "wst_volume_dust")

# 材质名 → (baseColor linear, roughness, metallic)；None 表示沿用在用值
FLAT = {
    "wst_mat_sand":        ((0.420, 0.300, 0.200), 0.95, 0.0),
    "wst_mat_concrete":    ((0.260, 0.250, 0.235), 0.90, 0.0),
    "wst_mat_brick":       ((0.190, 0.140, 0.108), 0.92, 0.0),
    "wst_mat_rebar":       ((0.085, 0.040, 0.022), 0.88, 0.25),
    "wst_mat_wood":        ((0.135, 0.100, 0.072), 0.86, 0.0),
    "wst_mat_rock":        ((0.150, 0.140, 0.128), 0.92, 0.0),
    "wst_mat_ridge":       ((0.320, 0.220, 0.140), 0.95, 0.0),
    "wst_mat_rust":        ((0.180, 0.080, 0.040), 0.85, 0.2),
    "wst_mat_glass":       ((0.040, 0.050, 0.050), 0.20, 0.0),
    "wst_mat_car_paint":   ((0.260, 0.115, 0.070), 0.75, 0.15),
    "wst_mat_car_glass":   ((0.085, 0.092, 0.098), 0.42, 0.0),
    "wst_mat_car_cavity":  ((0.020, 0.017, 0.014), 0.96, 0.0),
    "wst_mat_car_chrome":  ((0.100, 0.085, 0.070), 0.72, 0.45),
    "wst_mat_car_hub":     ((0.165, 0.078, 0.040), 0.78, 0.12),
    "wst_mat_car_trim":    ((0.017, 0.015, 0.013), 0.80, 0.30),
    "wst_mat_car_flake":   ((0.105, 0.052, 0.030), 0.90, 0.10),   # 翘起的锈片
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
            "materials": len(js.get("materials", [])), "with_basecolor": flat,
            "nodes": len(js.get("nodes", [])), "tris": tris,
            "lights": "KHR_lights_punctual" in js.get("extensionsUsed", [])}


def build():
    os.makedirs(OUT_DIR, exist_ok=True)
    n = _select()
    saved = _flatten()
    try:
        bpy.ops.export_scene.gltf(
            filepath=OUT_GLB,
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
        )
    finally:
        _restore(saved)
    stats = _glb_stats(OUT_GLB)
    stats["selected_objects"] = n
    stats["restored_links"] = len(saved)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_COPY, copy=True)
    stats["blend"] = BLEND_COPY
    return stats


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))