# -*- coding: utf-8 -*-
"""外部 GLB 资产接入（Tripo 生成）：枯树 / 废墟 / 轿车。

为什么不再程序化生成：参考图里树皮的锐沟、满车身的斑驳锈色、墙体的碎裂断面，
都超出"手工脚本 + 程序化节点"的性价比区间。改用扫描级 GLB 承担细节，本场景只负责
大气、地面、光照与构图，才可能做到"与图片高度还原"。

导入后必须做的四件事（否则资产进不了本场景的验收口径）：
  1) 减面：三件资产原始合计 111 万三角，直接进 GLB 首屏会炸
  2) 贴图钳制：源贴图统一 4096²，按实际观看距离压到 1024 / 2048
  3) 材质归一：glTF 的 metallicFactor 缺省为 1，不显式归零会渲成金属壳
  4) 尺寸/摆放：沿用程序化版本已经对好参考图的屏幕构图（相机不动）

幂等：每次 build() 先删 wst_ext_* 与程序化的树/车/废墟，再重新导入。
"""
import os

import bpy
from mathutils import Vector

SRC_DIR = r"C:\Users\ning\Downloads"

# 参考图构图对应的摆放参数（与旧程序化版本的投影一致，相机不动）
ASSETS = (
    {
        "key": "tree",
        "file": "tree.glb",
        "obj": "wst_ext_tree",
        "mat": "wst_mat_ext_tree",
        "coll": "collection_tree",
        "decimate": 0.090,
        "tex": 1024,
        "axis": 2,          # 按 Z 轴（高度）对齐
        # 参考图里树基在画面 86% 高度处 → 距相机约 6.7 m；按该距离与树顶像素反算树高 4.3 m
        "size": 3.95,
        "loc": (-3.35, -8.30),
        "sink": 0.060,
        "rot_z": 0.349,
        # 扫描树偏"矮胖"：参考图的树冠细窄（冠幅仅约 1.6 m），横向压到 0.62
        "squash": 0.85,
        "tint": (1.12, 1.04, 0.97),
    },
    {
        "key": "car",
        "file": "car.glb",
        "obj": "wst_ext_car",
        "mat": "wst_mat_ext_car",
        "coll": "collection_car",
        "decimate": 0.038,
        "tex": 1024,
        "axis": 1,          # 车长沿模型本地 Y
        # 车轮着地像素 v=1063 → 距相机 12.3 m；侧向投影 895 px 对应车长 5.24 m
        "size": 5.24,
        "loc": (4.34, -3.00),
        "sink": 0.100,      # 参考图里轮胎陷进沙里约 1/3 轮径
        # 车头在模型本地 -Y；rot -1.742 rad 让车头指向世界 (-0.986,+0.168)：
        # 左侧面对相机、车头在画面左侧、右侧露出一点车尾面板（与参考图的后左 3/4 一致）
        "rot_z": -1.742,
        "tint": (0.97, 0.94, 0.91),
    },
    {
        "key": "house",
        "file": "house.glb",
        "obj": "wst_ext_house",
        "mat": "wst_mat_ext_house",
        "coll": "collection_ruins",
        "decimate": 0.055,
        "tex": 1024,
        "axis": 2,          # 按高度对齐
        # 参考图里废墟比树远一档：底面贴近地平线 → 约 29 m；按该距离与顶边像素反算高 6.6 m
        "size": 5.15,
        "loc": (-4.40, 6.00),
        "sink": 0.120,
        "rot_z": -0.35,     # 让受光的 +X 面转向相机，右侧端墙被夕照点亮
        # 扫描废墟比参考图更"横"：横向压到 0.80，才有一栋两层楼的竖向体量
        "squash": 0.74,
        # 网页实测废墟比参考图暗约 15%，tint 抬一档补回来
        "tint": (1.88, 1.74, 1.52),
    },
)

# 程序化版本留下的对象前缀：被外部资产取代，build() 时清掉
SUPERSEDED = ("wst_tree_", "wst_car_", "wst_build_", "wst_det_")
SUPERSEDED_EXACT = ("wst_ruin_chips",)


def _tris(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def _bbox(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def _purge_unused():
    for store, label in ((bpy.data.materials, "材质"), (bpy.data.meshes, "网格"),
                         (bpy.data.images, "贴图"), (bpy.data.objects, "对象")):
        for block in list(store):
            if block.users == 0:
                store.remove(block)


def remove_superseded():
    """删掉程序化版树 / 车 / 废墟，以及上次导入的 wst_ext_*。"""
    killed = []
    for ob in list(bpy.data.objects):
        n = ob.name
        if n.startswith("wst_ext_") or n in SUPERSEDED_EXACT or n.startswith(SUPERSEDED):
            killed.append(n)
            bpy.data.objects.remove(ob, do_unlink=True)
    _purge_unused()
    return len(killed)


def _import(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB 里没有网格：" + path)
    # 多网格资产先合并成一个对象，后面减面/摆放只按一个对象处理
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    main = meshes[0]
    bpy.context.view_layer.objects.active = main
    if len(meshes) > 1:
        bpy.ops.object.join()
    for o in new:
        if o is not main and o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    # glTF 导出的物体常带父级空物体，父级删掉后要把变换烘进物体自身
    main.parent = None
    return main


def _decimate(ob, ratio):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _prep_material(ob, name, tex_max, tint=None):
    """贴图钳制 + 金属度归零 + 亮度校正 + 材质改名。返回 (贴图尺寸, 原始尺寸)。"""
    mat = ob.material_slots[0].material if ob.material_slots else None
    if mat is None:
        return [], []
    bsdf = next((n for n in mat.node_tree.nodes
                 if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if bsdf is not None:
        # 扫描资产是哑光的锈铁 / 干木 / 水泥，金属度必须显式归零
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.92

    sizes, src_sizes = [], []
    for n in mat.node_tree.nodes:
        if n.bl_idname != "ShaderNodeTexImage" or n.image is None:
            continue
        img = n.image
        src_sizes.append(list(img.size))
        touched = False
        if max(img.size) > tex_max:
            img.scale(tex_max, tex_max)
            touched = True
        if tint is not None:
            _tint_image(img, tint)
            touched = True
        if touched:
            # 改过像素必须 pack 回 .blend，否则改动只活在内存里，导出拿到的还是原图
            img.pack()
        sizes.append(list(img.size))
    mat.name = name
    return sizes, src_sizes


def _tint_image(img, tint):
    """把亮度/色温校正**烘进贴图本身**。

    走材质节点（Mix MULTIPLY）时 glTF 导出器只会丢掉这条连线：实测导出的
    baseColorFactor 是纯白，网页里看到的比 Blender 里暗一档。所以校正必须落在像素上。
    tint 是"线性空间的目标倍率"，而 Image.pixels 存的是 sRGB 原值，故先做 1/2.2 幂补偿。
    """
    import numpy as np
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(-1, 4)
    f = np.array([t ** (1.0 / 2.2) for t in tint], dtype=np.float32)
    buf[:, :3] = np.clip(buf[:, :3] * f, 0.0, 1.0)
    img.pixels.foreach_set(buf.reshape(-1))
    img.update()


def _place(ob, spec):
    # 先按资产自身坐标轴定尺寸，再旋转：旋转后 bbox 的对角线会污染尺寸判断
    mn, mx = _bbox(ob)
    cur = (mx - mn)[spec["axis"]]
    s = spec["size"] / cur if cur > 1e-6 else 1.0
    sq = spec.get("squash", 1.0)
    ob.scale = (s * sq, s * sq, s)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # glTF 导入的物体是 QUATERNION 旋转模式，直接写 rotation_euler 会被静默忽略
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (0.0, 0.0, spec["rot_z"])
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    mn, mx = _bbox(ob)
    ob.location += Vector((spec["loc"][0] - (mn.x + mx.x) * 0.5,
                           spec["loc"][1] - (mn.y + mx.y) * 0.5,
                           -spec["sink"] - mn.z))
    bpy.context.view_layer.update()
    return [round(mx[i] - mn[i], 3) for i in range(3)]


def _link(ob, coll_name):
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return False
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    return True


def build(src_dir=SRC_DIR):
    report = {"removed": remove_superseded(), "assets": {}}
    for spec in ASSETS:
        path = os.path.join(src_dir, spec["file"])
        if not os.path.exists(path):
            report["assets"][spec["key"]] = {"error": "missing " + path}
            continue
        ob = _import(path)
        ob.name = spec["obj"]
        ob.data.name = spec["obj"]
        tri0 = _tris(ob)
        _decimate(ob, spec["decimate"])
        tex, tex0 = _prep_material(ob, spec["mat"], spec["tex"], spec.get("tint"))
        dims = _place(ob, spec)
        coll = _link(ob, spec["coll"])
        ob["wst_ext"] = spec["key"]
        report["assets"][spec["key"]] = {
            "obj": ob.name, "coll": coll, "tris": _tris(ob), "tris_src": tri0,
            "dims": dims, "tex": tex, "tex_src": tex0,
        }
    _purge_unused()
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False, default=str))
