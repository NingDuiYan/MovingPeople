# -*- coding: utf-8 -*-
"""废墟细节补强：破损女儿墙 / 楼层腰线 / 斜靠的坍塌楼板 / 外敷瓦砾扇 / 斜梁。

关键：wst_build_wall_left 不是一个平面 —— 它的临街立面随 x 缓慢后退
（x=-13.5 时 y=7.15，x=-8.5 时 y=8.34），x<-13.5 处墙体折进巷道。
所以细节必须跟着实测的前表面走，否则会浮在空气里。
所有几何用 8 顶点盒（12 三角），禁止 N-gon。
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix

COLL_NAME = "collection_ruins"
PREFIX = "wst_det_"
SEED = 20240711

# (x, 前表面 y, 顶面 z) —— 由 wst_build_wall_left 顶点实测
SURF = (
    (-15.0, 13.01, 6.02), (-14.5, 11.00, 6.15), (-14.0, 8.77, 6.64),
    (-13.5, 7.15, 6.71), (-13.0, 7.22, 6.78), (-12.5, 7.34, 6.94),
    (-12.0, 7.47, 6.92), (-11.5, 7.60, 6.81), (-11.0, 7.68, 6.21),
    (-10.5, 7.85, 5.85), (-10.0, 7.93, 5.49), (-9.5, 8.09, 4.19),
    (-9.0, 8.20, 4.49), (-8.5, 8.34, 4.51),
)
X_LO, X_HI = -13.60, -8.35          # 有竖直立面的区间
rng = random.Random(SEED)


def _lerp(x, col):
    if x <= SURF[0][0]:
        return SURF[0][col]
    if x >= SURF[-1][0]:
        return SURF[-1][col]
    for i in range(len(SURF) - 1):
        x0, x1 = SURF[i][0], SURF[i + 1][0]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return SURF[i][col] * (1 - t) + SURF[i + 1][col] * t
    return SURF[-1][col]


def front_y(x):
    return _lerp(x, 1)


def top_z(x):
    return _lerp(x, 2)


def _coll():
    c = bpy.data.collections.get(COLL_NAME)
    if c is None:
        c = bpy.data.collections.new(COLL_NAME)
        bpy.context.scene.collection.children.link(c)
    return c


def _wipe():
    for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        bpy.data.objects.remove(o, do_unlink=True)


def _box(bm, M, sx, sy, sz, mat=0, jag=0.0, tilt=0.0):
    """单位盒 → 缩放/旋转/平移；jag>0 时随机抬起顶面顶点做断口。"""
    before = len(bm.faces)
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=M @ Matrix.Diagonal((sx, sy, sz, 1.0)))
    verts = res["verts"]
    if jag > 0.0:
        for v in verts:
            if v.co.z > 0.0:
                v.co.z += rng.uniform(0.0, jag)
                if tilt:
                    v.co.x += rng.uniform(-tilt, tilt)
    bm.faces.ensure_lookup_table()
    for f in bm.faces[before:]:
        f.material_index = mat
    return verts


def _finish(bm, name, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    for m in mats:
        ob.data.materials.append(bpy.data.materials[m])
    _coll().objects.link(ob)
    return ob


def _parapet():
    """沿实测顶面断口补一排不齐的混凝土残块，给立面上沿做出锯齿剪影。"""
    bm = bmesh.new()
    n = 16
    for i in range(n):
        x = X_LO + (X_HI - X_LO) * (i + 0.5) / n
        w = (X_HI - X_LO) / n * rng.uniform(0.8, 1.4)
        base = top_z(x) - rng.uniform(0.15, 0.55)
        h = rng.uniform(0.28, 1.15) * (1.4 if x < -12.4 else 1.0)
        depth = rng.uniform(0.30, 0.62)
        y = front_y(x) + depth * 0.5 - 0.10
        z = base + h * 0.5
        M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rng.uniform(-0.07, 0.07), 4, "Y")
        _box(bm, M, w, depth, h, mat=0, jag=h * 0.5, tilt=w * 0.14)
    _finish(bm, PREFIX + "parapet", ["wst_mat_concrete"])


def _floor_bands():
    """两道楼板腰线：只出现在顶面高于该高度的区间，带随机断口。"""
    bm = bmesh.new()
    for z in (2.24, 4.46):
        x = X_LO
        while x < X_HI - 0.5:
            seg = rng.uniform(0.8, 2.4)
            seg = min(seg, X_HI - x)
            if top_z(x + seg * 0.5) > z + 0.55 and rng.random() > 0.20:
                cx = x + seg * 0.5
                M = (Matrix.Translation((cx, front_y(cx) - 0.13, z))
                     @ Matrix.Rotation(rng.uniform(-0.05, 0.05), 4, "Y"))
                _box(bm, M, seg, 0.44, 0.22, mat=0)
                if rng.random() < 0.30:      # 板下挂着的碎块
                    M2 = Matrix.Translation((cx + rng.uniform(-0.4, 0.4),
                                             front_y(cx) - 0.20,
                                             z - rng.uniform(0.18, 0.45)))
                    _box(bm, M2, rng.uniform(0.16, 0.36), 0.18,
                         rng.uniform(0.18, 0.40), mat=0, jag=0.16)
            x += seg + rng.uniform(0.1, 0.55)
    _finish(bm, PREFIX + "floorband", ["wst_mat_concrete"])


def _collapse_slab():
    """从立面中段斜塌到地面的整块楼板 —— 参考图里最有辨识度的大斜块。"""
    bm = bmesh.new()
    base = Vector((-8.95, 4.35, 0.42))
    top = Vector((-10.75, front_y(-10.75) + 0.15, top_z(-10.75) - 0.75))
    d = top - base
    q = d.to_track_quat("Z", "Y")
    M = (Matrix.Translation(base + d * 0.5) @ q.to_matrix().to_4x4()
         @ Matrix.Rotation(math.radians(7.0), 4, "Z"))
    _box(bm, M, 3.30, 0.32, d.length, mat=0)
    for t, s in ((0.88, 0.95), (0.74, 0.62)):
        p = base + d * t + Vector((rng.uniform(-0.5, 0.5), -0.40, 0.10))
        M2 = (Matrix.Translation(p) @ q.to_matrix().to_4x4()
              @ Matrix.Rotation(rng.uniform(-0.55, 0.55), 4, "X"))
        _box(bm, M2, s, 0.24, s * 0.8, mat=0, jag=0.20)
    _finish(bm, PREFIX + "collapse_slab", ["wst_mat_concrete"])


def _beams():
    """斜靠的梁柱：一端戳进墙脚，一端落在地面瓦砾上。"""
    bm = bmesh.new()
    spec = (
        ((-12.90, 6.55, 1.75), 0.24, 4.60, (1.16, 0.0, 0.22)),
        ((-8.60, 7.30, 1.30), 0.26, 3.60, (1.28, 0.0, -0.30)),
        ((-13.90, 6.10, 0.75), 0.20, 3.20, (1.46, 0.4, 0.16)),
    )
    for (loc, th, ln, rot) in spec:
        M = (Matrix.Translation(loc) @ Matrix.Rotation(rot[0], 4, "X")
             @ Matrix.Rotation(rot[1], 4, "Y") @ Matrix.Rotation(rot[2], 4, "Z"))
        _box(bm, M, th, th, ln, mat=0)
    _finish(bm, PREFIX + "beams", ["wst_mat_concrete"])


def _rubble_fan():
    """从墙脚朝相机铺开的瓦砾扇：越靠近建筑越高越密。"""
    bm = bmesh.new()
    n = 96
    for i in range(n):
        u, v = rng.random(), rng.random()
        x = -14.30 + 8.00 * u
        y = 3.20 + 3.90 * v
        near = max(0.0, v - 0.15)
        h = 0.18 + 1.10 * near * (0.45 + rng.random() * 0.9)
        s = 0.22 + rng.uniform(0.0, 0.60) * (0.55 + near)
        z = max(0.04, h * 0.40)
        M = (Matrix.Translation((x, y, z))
             @ Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z")
             @ Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "X")
             @ Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "Y"))
        _box(bm, M, s, s * rng.uniform(0.55, 1.05), s * rng.uniform(0.28, 0.72),
             mat=0 if rng.random() < 0.80 else 1, jag=s * 0.22)
    _finish(bm, PREFIX + "rubble_fan", ["wst_mat_concrete", "wst_mat_brick"])


def build():
    _wipe()
    _parapet()
    _floor_bands()
    _collapse_slab()
    _beams()
    _rubble_fan()
    objs = [o for o in bpy.data.objects if o.name.startswith(PREFIX)]
    return {"objects": len(objs),
            "tris": sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)}


if __name__ == "__main__":
    print(build())
