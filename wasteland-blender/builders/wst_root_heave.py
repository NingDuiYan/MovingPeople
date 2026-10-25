# -*- coding: utf-8 -*-
"""wst_root_heave.py — 树根把土顶起来的隆起 + 放射裂缝（幂等）。

为什么需要它：参考图里枯树不是"插在平地上"——根盘四周的土被 6 条主根顶起，
根与根之间的地面被拉开一条条放射状裂缝。改造前场景里根盘底面在 z=0，
而树基周围的沙地实测在 -0.01 ~ -0.04 m（wst_terrain_ground），
根盘整个悬空 1–4 cm，接缝是一条直棱。

做法：绕 BASE 建一圈极坐标网格（11 环 × 66 方位）
    z = 实测地面高度 + 隆起(r, θ) - 裂缝 - 埋边(r)
  · 隆起：峰值 75 mm 落在 r ≈ 0.62 m（刚好在根盘裙边 0.42 m 之外），向外高斯衰减
  · 沿 6 条主根方位再抬 30%：土是被根"顶"起来的，隆起要跟着根走
  · 裂缝：放在两条主根之间的**中间方位**，最深 35 mm，向内 0.30 m / 向外 1.25 m 淡出
  · 外环整体下沉 50 mm 埋进地面，不留硬边
地面高度用 scene.ray_cast 逐点实测（不用近似平面），所以起伏贴得住。

命名用 wst_rootmound_（**不能用 wst_tree 前缀**：wst_finalize.resize_tree()
会把所有以 wst_tree 开头的对象一起做等比缩放）。
材质沿用 wst_mat_sand：wst_ground.py 给它加的"大尺度灰褐板块"混色用的是
Object 坐标，换到新对象只改图案位置、不改尺度，和周围沙地接得上。
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

BUILDERS = os.path.dirname(os.path.abspath(__file__))
if BUILDERS not in sys.path:
    sys.path.insert(0, BUILDERS)

from wst_tree_spec import BASE, ROOTS, ROT_Z_DEG  # noqa: E402

PREFIX = "wst_rootmound"
OBJ_NAME = "wst_rootmound_soil"
COL = "collection_terrain"
MAT = "wst_mat_sand"          # 与周围沙地同材质，接缝才不会显

# 极坐标环半径（米，世界尺度：整树已按 0.8003 缩放过，根尖最远约 1.46 m）
RINGS = (0.00, 0.18, 0.32, 0.48, 0.66, 0.86, 1.08, 1.32, 1.58, 1.88, 2.25)
N_BASE = 48                   # 基础方位分割（7.5°）
CRACK_HALF_DEG = 3.2          # 每条裂缝在角度上占的半宽
CRACK_DEPTH = 0.055           # 裂缝最深（米）：太浅时在成片渲染里完全读不出来
HEAVE_PEAK = 0.105            # 隆起峰值（米）：要明显到能在沙面上看出"土被根顶起"
HEAVE_R = 0.70                # 隆起峰值半径
HEAVE_SIG = 0.72              # 向外衰减尺度
LOBE_DEG = 0.34               # 沿主根方向的抬升波及角（弧度）
BURY = 0.090                  # 外环下沉量：埋深不够时隆起和地形之间会露出一圈硬边
SMOOTH_ANGLE_DEG = 32.0

ROOT_AZ = tuple(math.radians(r["az"]) for r in ROOTS)


def _smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _ang_dist(a, b):
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)


def _crack_az():
    """裂缝方位 = 相邻两条主根方位的中间（土最先从那里被拉开）。"""
    az = sorted(ROOT_AZ)
    out = []
    for i, a0 in enumerate(az):
        a1 = az[(i + 1) % len(az)]
        if a1 <= a0:
            a1 += 2.0 * math.pi
        out.append(((a0 + a1) * 0.5) % (2.0 * math.pi))
    return tuple(out)


CRACK_AZ = _crack_az()
CRACK_W = math.radians(CRACK_HALF_DEG)


def _purge():
    dead = [o for o in bpy.data.objects if o.name.startswith(PREFIX)]
    for o in dead:
        bpy.data.objects.remove(o, do_unlink=True)
    return len(dead)


def _ground_z(x, y):
    """向下打射线取真实地面高度；碰到树/石头就往下让一点接着打。"""
    dg = bpy.context.evaluated_depsgraph_get()
    z0 = 20.0
    for _ in range(10):
        hit, loc, _n, _i, ob, _m = bpy.context.scene.ray_cast(
            dg, Vector((x, y, z0)), Vector((0.0, 0.0, -1.0)))
        if not hit:
            break
        if ob is not None and ob.name.startswith("wst_terrain"):
            return loc.z
        z0 = loc.z - 0.002
    return -0.020


def _height(r, th):
    """隆起剖面：基础高斯丘 + 沿根加抬 - 放射裂缝 - 外环埋边 + 轻微不规则。"""
    # 角度扰动：隆起边界不能是正圆，否则看着像井盖（原来"平顶 + 圆边"就是这样来的）
    wob = 1.0 + 0.16 * math.sin(3.0 * th + 0.7) + 0.10 * math.sin(7.0 * th + 2.1)
    rr = r / max(0.30, wob)
    # 单峰穹顶：中心最高、向外单调下落
    base = HEAVE_PEAK * math.exp(-(rr / HEAVE_SIG) ** 2)
    lobe = 0.0
    for a in ROOT_AZ:
        lobe = max(lobe, math.exp(-(_ang_dist(th, a) / LOBE_DEG) ** 2))
    base *= 0.80 + 0.30 * lobe

    cut = 0.0
    span = _smoothstep((r - 0.30) / 0.28) * (1.0 - _smoothstep((r - 1.25) / 0.55))
    if span > 0.0:
        for c in CRACK_AZ:
            d = _ang_dist(th, c)
            if d < CRACK_W:
                cut = max(cut, CRACK_DEPTH * (1.0 - d / CRACK_W) ** 0.7 * span)

    bury = BURY * _smoothstep((r - 1.45) / 0.80)
    jitter = 0.005 * math.sin(3.0 * th + 4.2 * r) * _smoothstep((r - 0.20) / 0.40)
    return base - cut - bury + jitter


def _smooth_by_angle(ob, angle_deg=SMOOTH_ANGLE_DEG):
    """土面整体 smooth，只有裂缝那种大夹角边留锐。"""
    limit = math.radians(angle_deg)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.normal_update()
    for e in bm.edges:
        e.smooth = (len(e.link_faces) == 2 and e.calc_face_angle(0.0) <= limit)
    for fc in bm.faces:
        fc.smooth = True
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def build():
    report = {"removed": _purge()}
    coll = bpy.data.collections.get(COL) or bpy.data.collections.get("collection_wasteland")
    mat = bpy.data.materials.get(MAT)
    rot = math.radians(ROT_Z_DEG)
    cr, sr = math.cos(rot), math.sin(rot)

    azs = {round(2.0 * math.pi * i / N_BASE, 6) for i in range(N_BASE)}
    for c in CRACK_AZ:
        for d in (-CRACK_W, 0.0, CRACK_W):
            azs.add(round((c + d) % (2.0 * math.pi), 6))
    azs = sorted(azs)

    def world(r, th):
        xl, yl = r * math.cos(th), r * math.sin(th)
        xw = BASE.x + xl * cr - yl * sr
        yw = BASE.y + xl * sr + yl * cr
        return (xl, yl, _ground_z(xw, yw) - BASE.z + _height(r, th))

    bm = bmesh.new()
    center = bm.verts.new(world(0.0, 0.0))
    rows = []
    for ri, r in enumerate(RINGS):
        if r <= 1e-9:
            rows.append([center])
            continue
        rows.append([bm.verts.new(world(r, th)) for th in azs])

    na = len(azs)
    for ri in range(1, len(RINGS)):
        inner, outer = rows[ri - 1], rows[ri]
        for j in range(na):
            k = (j + 1) % na
            if len(inner) == 1:
                bm.faces.new((inner[0], outer[j], outer[k]))
            else:
                bm.faces.new((inner[j], inner[k], outer[k], outer[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    me = bpy.data.meshes.new(OBJ_NAME)
    bm.to_mesh(me)
    bm.free()
    if mat is not None:
        me.materials.append(mat)
    ob = bpy.data.objects.new(OBJ_NAME, me)
    ob.location = BASE
    ob.rotation_euler = (0.0, 0.0, rot)
    (coll or bpy.context.scene.collection).objects.link(ob)
    _smooth_by_angle(ob)

    zs = [v.co.z for v in me.vertices]
    bpy.context.view_layer.update()
    report.update({
        "object": ob.name,
        "collection": (coll.name if coll else "Scene Collection"),
        "rings": len(RINGS),
        "azimuths": na,
        "verts": len(me.vertices),
        "tris": sum(len(p.vertices) - 2 for p in me.polygons),
        "crack_az_deg": [round(math.degrees(a) + ROT_Z_DEG, 1) for a in CRACK_AZ],
        "root_az_deg": [round(math.degrees(a) + ROT_Z_DEG, 1) for a in ROOT_AZ],
        "z_local": [round(min(zs), 4), round(max(zs), 4)],
    })
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False, default=str))
