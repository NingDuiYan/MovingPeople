# -*- coding: utf-8 -*-
"""废墟表面侵蚀（wst_ruins 的收尾补丁）。

wst_ruins 的墙体是"0.26 m 网格薄板"拼的：面板完全平整、断口是直角的矩形台阶，
渲出来是一块块白板叠成的楼梯（参考图里是被风沙啃过的混凝土，断口参差、面上有剥落）。
这里不改拓扑，只按世界坐标上的确定性噪声把顶点沿法线推一下：

    1) 低频大剥落（scale≈0.9, 3 cm）：把平板面打出手掌大的鼓凹；
    2) 高频风蚀（scale≈2.8, 1 cm）：面上的细致起伏；
    3) 顶部 1.2 m 内加崩口（最多 5 cm）：断口不再是整齐的直角台阶。

噪声取世界坐标，所以相邻的独立墙板会被同一场噪声推动、不会互相错开露缝。
"""

import math
import bpy

PREFIXES = ("wst_build_", "wst_det_")
AMP_COARSE = 0.030
AMP_FINE = 0.010
AMP_EDGE = 0.050
TOP_BAND = 1.20


def _noise(x, y, z, s):
    """三轴正弦乘积：足够平滑、无需纹理资源、结果可重复。"""
    return (math.sin(x * s * 1.7 + 1.3)
            * math.sin(y * s * 2.1 + 2.7)
            * math.sin(z * s * 1.3 + 0.4))


def _disp(p):
    return (AMP_COARSE * _noise(p.x, p.y, p.z, 0.9)
            + AMP_FINE * _noise(p.x + 3.1, p.y - 1.7, p.z + 0.9, 2.8))


def _smoothstep(t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


def erode(ob):
    # 幂等：wst_finalize 会被反复执行，而侵蚀是"就地推顶点"，跑两次就会累加。
    # 用对象自定义属性打标记；wst_ruins 重建后新对象没有标记，会正常侵蚀一次。
    if ob.get("wst_eroded"):
        return 0
    me = ob.data
    if not me.vertices:
        return 0
    mw = ob.matrix_world
    mi = mw.inverted()
    zs = [(mw @ v.co).z for v in me.vertices]
    z_top = max(zs)
    for v in me.vertices:
        wp = mw @ v.co
        wn = (mw.to_3x3() @ v.normal)
        if wn.length < 1e-6:
            continue
        wn.normalize()
        d = _disp(wp)
        edge = _smoothstep((wp.z - (z_top - TOP_BAND)) / TOP_BAND)
        d += AMP_EDGE * edge * _noise(wp.x * 1.9, wp.y * 1.9, wp.z * 1.9, 1.6)
        v.co = mi @ (wp + wn * d)
    me.update()
    ob["wst_eroded"] = True
    return len(me.vertices)




# ---------------------------------------------------------------- 断口崩块
CHIP_PREFIX = "wst_ruin_chip_"
CHIP_OBJ = "wst_ruin_chips"
CHIP_COL = "collection_ruins"
CHIP_MAT = "wst_mat_concrete"
CHIP_MIN_Z = 1.60          # 低于这个高度的顶边不崩（地面碎块已经够多了）
CHIP_STEP = 0.34           # 沿断口每 0.34 m 撒一块
CHIP_SIZE = (0.055, 0.150)  # 崩块尺寸范围


def _hash01(i, k):
    """整数哈希 → [0,1)，保证每次重建结果一致。"""
    x = (i * 374761393 + k * 668265263) & 0xFFFFFFFF
    x = (x ^ (x >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((x ^ (x >> 16)) & 0xFFFFFF) / float(0x1000000)


def _chip_bm(bm, center, size, rng_i):
    """一块歪斜的小立方体：立方体的 8 个角各自抖一下，就不是整齐的砖了。"""
    rot = ((_hash01(rng_i, 1) - 0.5) * 1.1,
           (_hash01(rng_i, 2) - 0.5) * 1.1,
           _hash01(rng_i, 3) * 6.28)
    sx = size * (0.7 + 0.9 * _hash01(rng_i, 4))
    sy = size * (0.6 + 0.8 * _hash01(rng_i, 5))
    sz = size * (0.5 + 0.7 * _hash01(rng_i, 6))
    verts = []
    for ix in (-1, 1):
        for iy in (-1, 1):
            for iz in (-1, 1):
                j = 0.16
                vx = ix * sx * 0.5 * (1.0 + j * (_hash01(rng_i, 7 + ix) - 0.5) * 2.0)
                vy = iy * sy * 0.5 * (1.0 + j * (_hash01(rng_i, 9 + iy) - 0.5) * 2.0)
                vz = iz * sz * 0.5 * (1.0 + j * (_hash01(rng_i, 11 + iz) - 0.5) * 2.0)
                verts.append((vx, vy, vz))
    from mathutils import Euler, Vector
    eu = Euler(rot, 'XYZ')
    vs = []
    for v in verts:
        w = Vector(v)
        w.rotate(eu)
        vs.append(bm.verts.new(Vector(center) + w))
    # 立方体面（verts 顺序：ix,iy,iz 全组合，index = ((ix+1)/2)*4 + ((iy+1)/2)*2 + ((iz+1)/2)）
    idx = {(ix, iy, iz): ((ix + 1) // 2) * 4 + ((iy + 1) // 2) * 2 + ((iz + 1) // 2)
           for ix in (-1, 1) for iy in (-1, 1) for iz in (-1, 1)}
    quads = (
        ((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1)),
        ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
        ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)),
        ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)),
        ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)),
        ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)),
    )
    for q in quads:
        bm.faces.new([vs[idx[c]] for c in q])


def crumble_crest():
    """沿每块墙的"最高一圈顶点"撒崩块，把 0.26 m 的直角台阶打成参差的断口。"""
    import bmesh
    from mathutils import Vector

    seeds = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.name.startswith(PREFIXES):
            continue
        mw = ob.matrix_world
        wv = [mw @ v.co for v in ob.data.vertices]
        if not wv:
            continue
        z_top = max(p.z for p in wv)
        if z_top < CHIP_MIN_Z:
            continue
        band = [p for p in wv if p.z > z_top - 0.42]
        # 按 0.34 m 网格去重，避免同一处堆一坨
        seen = set()
        for p in band:
            key = (int(p.x / CHIP_STEP), int(p.y / CHIP_STEP), int(p.z / 0.20))
            if key in seen:
                continue
            seen.add(key)
            seeds.append(p.copy())

    if not seeds:
        return {"chips": 0}

    bm = bmesh.new()
    for i, p in enumerate(seeds):
        size = CHIP_SIZE[0] + (CHIP_SIZE[1] - CHIP_SIZE[0]) * _hash01(i, 21)
        off = Vector(((_hash01(i, 22) - 0.5) * 0.05,
                      (_hash01(i, 23) - 0.5) * 0.05,
                      size * (0.1 + 0.5 * _hash01(i, 24))))
        _chip_bm(bm, p + off, size, i * 7 + 3)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    existing = bpy.data.objects.get(CHIP_OBJ)
    if existing is not None:            # 幂等：先删掉上一次的崩块
        me = existing.data
        bpy.data.objects.remove(existing, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(CHIP_OBJ)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(CHIP_OBJ, me)
    coll = bpy.data.collections.get(CHIP_COL) or bpy.context.scene.collection
    coll.objects.link(ob)
    mat = bpy.data.materials.get(CHIP_MAT)
    if mat is not None:
        me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = False
    return {"chips": len(seeds), "tris": sum(len(f.vertices) - 2 for f in me.polygons)}

def build():
    touched, verts = [], 0
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.name.startswith(PREFIXES):
            continue
        n = erode(ob)
        if n:
            touched.append(ob.name)
            verts += n
    chips = crumble_crest()
    return {"objects": len(touched), "verts": verts, "chips": chips,
            "amp": {"coarse": AMP_COARSE, "fine": AMP_FINE, "edge": AMP_EDGE},
            "names": touched}
