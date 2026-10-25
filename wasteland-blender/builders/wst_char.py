# -*- coding: utf-8 -*-
r"""wst_char.py — 废土幸存者角色（可绑定 / 可动画 / 导出 GLB）

规格来源: C:/Users/ning/Downloads/Wasteland Character.md
  35 岁男性，精瘦结实，身高 1.78 m，驼背微前倾；深古铜色皮肤；
  旧棕色皮夹克（拉到胸口、敞开）+ 脏灰衬衫（袖子卷到小臂）+ 暗枣红旧围巾；
  深卡其工装裤（左膝补丁、大腿侧袋）+ 高帮旧军靴；斜挎胸包、腰挂水壶与工具套；
  背后大帆布背包（侧面插睡垫、顶端小包袱）；额前推着护目镜。

朝向约定：角色面朝 -Y（Blender 前向），导出 +Y up 后在 three.js 里面朝 +Z。
"""
import bpy
import bmesh
import math
from mathutils import Vector, Matrix

PREFIX = "wst_char_"
COL = "collection_character"
MAT = {
    "skin": "wst_mat_char_skin",
    "leather": "wst_mat_char_leather",
    "leather_dark": "wst_mat_char_leather_dark",
    "shirt": "wst_mat_char_shirt",
    "canvas": "wst_mat_char_canvas",
    "pants": "wst_mat_char_pants",
    "patch": "wst_mat_char_patch",
    "metal": "wst_mat_char_metal",
    "lens": "wst_mat_char_lens",
    "scarf": "wst_mat_char_scarf",
    "hair": "wst_mat_char_hair",
    "eye": "wst_mat_char_eye",
    "iris": "wst_mat_char_iris",
    "sole": "wst_mat_char_sole",
    "boot": "wst_mat_char_boot",
}

# ---- 人体比例（米，脚底 z=0，面朝 -Y）----
H = 1.78
Z_ANKLE = 0.095
Z_KNEE = 0.495
Z_HIP = 0.920
Z_WAIST = 1.060
Z_CHEST = 1.285
Z_NECK = 1.452
Z_CHIN = 1.505
Z_HEAD = 1.635
Z_TOP = 1.772
X_HIP = 0.093
X_SHOULDER = 0.183
X_ELBOW = 0.243
X_WRIST = 0.283
Y_LEAN = -0.020          # 驼背：上身整体前移


# ============ 通用网格工具 ============

def _ensure_collection():
    col = bpy.data.collections.get(COL)
    if col is None:
        col = bpy.data.collections.new(COL)
        bpy.context.scene.collection.children.link(col)
    return col


def _superellipse(n, ex=2.0, ey=2.0, phase=0.0):
    out = []
    for j in range(n):
        a = 2.0 * math.pi * j / n + phase
        c, s = math.cos(a), math.sin(a)
        ux = math.copysign(abs(c) ** (2.0 / ex), c)
        uy = math.copysign(abs(s) ** (2.0 / ey), s)
        out.append((a, ux, uy))
    return out


def _ring_z(center, rx, ry, n, ex=2.0, ey=2.0, phase=0.0, warp=None):
    """水平椭圆环（用于躯干/头/裤腰这类沿 Z 堆叠的截面）"""
    cx, cy, cz = center
    pts = []
    for a, ux, uy in _superellipse(n, ex, ey, phase):
        x, y = cx + ux * rx, cy + uy * ry
        cz_local = cz
        if warp is not None:
            wt = warp(a, ux, uy)
            x += wt[0]
            y += wt[1]
            if len(wt) > 2:
                cz_local = cz + wt[2]
        pts.append(Vector((x, y, cz_local)))
    return pts


def _frames(points):
    """沿折线的平行传输标架，让管体不扭麻花"""
    tangents = []
    for i, p in enumerate(points):
        if i == 0:
            t = points[1] - points[0]
        elif i == len(points) - 1:
            t = points[-1] - points[-2]
        else:
            t = points[i + 1] - points[i - 1]
        tangents.append(t.normalized())
    ref = Vector((1.0, 0.0, 0.0))
    if abs(tangents[0].dot(ref)) > 0.9:
        ref = Vector((0.0, 1.0, 0.0))
    u = (ref - tangents[0] * ref.dot(tangents[0])).normalized()
    frames = []
    for i, t in enumerate(tangents):
        if i > 0:
            prev = tangents[i - 1]
            axis = prev.cross(t)
            if axis.length > 1e-7:
                ang = math.atan2(axis.length, prev.dot(t))
                u = (Matrix.Rotation(ang, 3, axis.normalized()) @ u)
        u = (u - t * u.dot(t)).normalized()
        v = t.cross(u).normalized()
        frames.append((points[i], u, v))
    return frames


def _loft(name, rings, mat, close_ring=True, cap_start=True, cap_end=True, smooth=True):
    """把一串同顶点数的环缝成管/壳。rings 顺序即面的走向。"""
    n = len(rings[0])
    verts = []
    for ring in rings:
        verts.extend(ring)
    faces = []
    span = len(rings) - 1
    for i in range(span):
        a, b = i * n, (i + 1) * n
        limit = n if close_ring else n - 1
        for j in range(limit):
            j2 = (j + 1) % n
            faces.append((a + j, a + j2, b + j2, b + j))
    if close_ring and cap_start:
        faces.append(tuple(range(n - 1, -1, -1)))
    if close_ring and cap_end:
        faces.append(tuple(range(len(verts) - n, len(verts))))
    return _mesh(name, verts, faces, mat, smooth)


def _mesh(name, verts, faces, mat, smooth=True):
    me = bpy.data.meshes.new(PREFIX + name)
    me.from_pydata([tuple(v) for v in verts], [], [list(f) for f in faces])
    me.validate(clean_customdata=False)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for poly in me.polygons:
            poly.use_smooth = True
    ob = bpy.data.objects.new(PREFIX + name, me)
    _ensure_collection().objects.link(ob)
    me.materials.append(_get_mat(mat))
    return ob


def _limb(name, points, radii, mat, n=14, ex=2.2, ey=2.2, cap_start=True,
          cap_end=True, squash=None, tip_round=0.0):
    """沿折线放样的肢体。radii: [(rx, ry), ...] 与 points 等长。"""
    frames = _frames(points)
    rings = []
    for i, (o, u, v) in enumerate(frames):
        rx, ry = radii[i]
        ring = []
        for a, ux, uy in _superellipse(n, ex, ey):
            p = o + u * (ux * rx) + v * (uy * ry)
            if squash is not None:
                p = squash(p, i, a)
            ring.append(p)
        rings.append(ring)
    if tip_round > 0.0:
        # 末端收成圆头，避免管体被硬切
        o, u, v = frames[-1]
        scale = tip_round
        extra = []
        for a, ux, uy in _superellipse(n, ex, ey):
            extra.append(o + (u * (ux * radii[-1][0]) + v * (uy * radii[-1][1])) * scale)
        rings.append(extra)
    return _loft(name, rings, mat, True, cap_start, cap_end)


def _ellipsoid(name, center, radii, mat, segs=16, rings=10, rot=None, squash=None):
    cx, cy, cz = center
    rx, ry, rz = radii
    verts = [Vector((cx, cy, cz + rz))]
    for i in range(1, rings):
        phi = math.pi * i / rings
        sz = math.cos(phi)
        sr = math.sin(phi)
        for j in range(segs):
            a = 2.0 * math.pi * j / segs
            p = Vector((cx + rx * sr * math.cos(a) * (1.0),
                        cy + ry * sr * math.sin(a),
                        cz + rz * sz))
            if squash is not None:
                p = squash(p, phi, a)
            verts.append(p)
    verts.append(Vector((cx, cy, cz - rz)))
    faces = []
    for j in range(segs):
        j2 = (j + 1) % segs
        faces.append((0, 1 + j2, 1 + j))
    for i in range(rings - 2):
        base = 1 + i * segs
        nxt = base + segs
        for j in range(segs):
            j2 = (j + 1) % segs
            faces.append((base + j, base + j2, nxt + j2, nxt + j))
    last = len(verts) - 1
    base = 1 + (rings - 2) * segs
    for j in range(segs):
        j2 = (j + 1) % segs
        faces.append((last, base + j, base + j2))
    if rot is not None:
        mat3 = Euler3(rot)
        verts = [mat3 @ (v - Vector(center)) + Vector(center) for v in verts]
    return _mesh(name, verts, faces, mat)


def Euler3(rot):
    from mathutils import Euler
    return Euler(rot, 'XYZ').to_matrix()


def _box(name, center, size, mat, rot=None, bevel=0.0, taper=1.0):
    """长方体；taper<1 时顶面收窄，bevel 用倒角算子做圆角"""
    cx, cy, cz = center
    sx, sy, sz = size
    verts = []
    for iz, tz in ((-1, 1.0), (1, taper)):
        for iy, ty in ((-1, 1.0), (1, 1.0)):
            for ix, tx in ((-1, 1.0), (1, 1.0)):
                verts.append(Vector((cx + ix * sx * 0.5 * tz,
                                     cy + iy * sy * 0.5 * ty,
                                     cz + iz * sz * 0.5)))
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    if rot is not None:
        m = Euler3(rot)
        verts = [m @ (v - Vector(center)) + Vector(center) for v in verts]
    ob = _mesh(name, verts, faces, mat, smooth=False)
    if bevel > 0.0:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=bevel,
                        segments=2, profile=0.6, affect='EDGES', clamp_overlap=True)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        for poly in ob.data.polygons:
            poly.use_smooth = True
        _mark_sharp(ob, 34.0)
    return ob


def _mark_sharp(ob, angle_deg=30.0):
    limit = math.radians(angle_deg)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    for e in bm.edges:
        e.smooth = len(e.link_faces) == 2 and e.calc_face_angle(0.0) <= limit
    bm.to_mesh(me)
    bm.free()
    me.update()


def _subdiv(ob, levels=1):
    md = ob.modifiers.new("Subdiv", 'SUBSURF')
    md.levels = levels
    md.render_levels = levels
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=md.name)
    ob.select_set(False)
    return ob


def _solidify(ob, thickness, offset=-1.0):
    md = ob.modifiers.new("Solid", 'SOLIDIFY')
    md.thickness = thickness
    md.offset = offset
    md.use_rim = True
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=md.name)
    ob.select_set(False)
    return ob


_MATS = {}


def _get_mat(key):
    name = MAT[key]
    if name in _MATS:
        return _MATS[name]
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    _MATS[name] = mat
    return mat


# ============ 服装 ============

def _arc_ring(center, rx, ry, n, a0, a1, ex=2.3, ey=2.2, warp=None):
    """不闭合的椭圆弧（夹克前襟敞开靠它做两片）"""
    cx, cy, cz = center
    pts = []
    for j in range(n):
        a = a0 + (a1 - a0) * j / (n - 1)
        c, s = math.cos(a), math.sin(a)
        ux = math.copysign(abs(c) ** (2.0 / ex), c)
        uy = math.copysign(abs(s) ** (2.0 / ey), s)
        x, y = cx + ux * rx, cy + uy * ry
        if warp is not None:
            dx, dy = warp(a, ux, uy)
            x += dx
            y += dy
        pts.append(Vector((x, y, cz)))
    return pts


JACKET_RINGS = [
    (0.940, 0.171, 0.117, 0.000),
    (0.990, 0.167, 0.114, 0.000),
    (1.045, 0.161, 0.112, 0.000),
    (1.100, 0.166, 0.115, 0.008),
    (1.160, 0.175, 0.121, 0.024),
    (1.220, 0.185, 0.127, 0.034),
    (1.280, 0.194, 0.132, 0.040),
    (1.340, 0.198, 0.129, 0.042),
    (1.390, 0.193, 0.120, 0.042),
    (1.418, 0.180, 0.114, 0.040),
    (1.442, 0.150, 0.104, 0.036),
    (1.462, 0.112, 0.092, 0.030),
]


def build_jacket():
    out = []
    for s in (1, -1):
        rings = []
        for z, rx, ry, gap in JACKET_RINGS:
            cx = 0.0
            cy = _torso_y(z) - 0.004
            if gap > 1e-6:
                d = math.asin(min(0.999, gap / rx))
                a0 = -math.pi / 2 + d
            else:
                a0 = -math.pi / 2
            a1 = math.pi / 2
            if s < 0:
                a0, a1 = math.pi - a1, math.pi - a0
            rings.append(_arc_ring((cx, cy, z), rx, ry, 26, a0, a1))
        ob = _loft("jacket_%d" % s, rings, "leather", close_ring=False, cap_start=False,
                   cap_end=False)
        _solidify(ob, 0.014, -1.0)
        _mark_sharp(ob, 42.0)
        out.append(_P(ob, True))
    # 立领：绕颈一圈但前开口
    collar = []
    for z, r in ((1.450, 0.100), (1.470, 0.106), (1.492, 0.102)):
        collar.append(_arc_ring((0.0, -0.030, z), r, r * 0.94, 22,
                                -math.pi / 2 + 0.85, math.pi * 1.5 - 0.85))
    ob = _loft("jacket_collar", collar, "leather", close_ring=False,
               cap_start=False, cap_end=False)
    _solidify(ob, 0.013, 0.0)
    _mark_sharp(ob, 45.0)
    out.append(_P(ob, True))
    # 翻领：前襟上端向两侧折出来的三角布片。没有它,正面就是一个"开着的筒",
    # 只会读成长开衫;参考图是翻开的大翻领。
    for s in (1, -1):
        lap = _box("lapel_%d" % s, (0.062 * s, -0.108, 1.372),
                   (0.096, 0.016, 0.150), "leather",
                   rot=(math.radians(-10), math.radians(8 * s), math.radians(-16 * s)),
                   bevel=0.010)
        _mark_sharp(lap, 40.0)
        out.append(_P(lap, True))
    # 袖子：肩→小臂中段，袖口卷边
    for s in (1, -1):
        sh = _m(SHOULDER, s)
        el = _m(ELBOW, s)
        mid = (el + _m(WRIST, s)) * 0.5
        pts = [sh + Vector((-0.012 * s, 0.0, 0.036)),
               sh + Vector((0.0, 0.0, -0.020)),
               (sh + el) * 0.5 + Vector((0.006 * s, 0.002, 0.0)),
               el + Vector((-0.004 * s, 0.0, 0.014)),
               el * 0.45 + mid * 0.55,
               mid + Vector((0.004 * s, -0.004, -0.020))]
        radii = [(0.068, 0.070), (0.064, 0.066), (0.059, 0.061),
                 (0.055, 0.057), (0.051, 0.052), (0.049, 0.050)]
        ob = _limb("sleeve_%d" % s, pts, radii, "leather", 16, 2.2, 2.2, False, False)
        out.append(_P(ob, True))
        cuff = _limb("cuff_%d" % s,
                     [mid + Vector((0.004 * s, -0.004, -0.016)),
                      mid + Vector((0.005 * s, -0.005, -0.030)),
                      mid + Vector((0.005 * s, -0.005, -0.040))],
                     [(0.054, 0.055), (0.056, 0.057), (0.050, 0.051)],
                     "leather_dark", 16, 2.2, 2.2, False, False)
        out.append(_P(cuff, True))
        # 肘部磨亮的补丁片
        out.append(_P(_box("elbow_patch_%d" % s, (0.238 * s, -0.026, 1.176),
                           (0.046, 0.034, 0.056), "leather_dark",
                           rot=(0.0, 0.0, math.radians(6 * s)), bevel=0.010), True))
    return out


SHIRT_RINGS = [
    (0.930, 0.158, 0.110),
    (0.990, 0.153, 0.107),
    (1.050, 0.148, 0.105),
    (1.120, 0.154, 0.109),
    (1.180, 0.164, 0.115),
    (1.240, 0.173, 0.120),
    (1.300, 0.181, 0.124),
    (1.360, 0.185, 0.120),
    (1.410, 0.179, 0.110),
    (1.444, 0.140, 0.094),
]


def build_shirt():
    out = []
    rings = []
    for z, rx, ry in SHIRT_RINGS:
        rings.append(_ring_z((0.0, _torso_y(z) - 0.002, z), rx, ry, 24, 2.3, 2.2))
    out.append(_P(_loft("shirt", rings, "shirt", True, True, True), True))
    for s in (1, -1):
        sh = _m(SHOULDER, s)
        el = _m(ELBOW, s)
        w = _m(WRIST, s)
        mid = (el + w) * 0.5
        pts = [sh + Vector((0.0, 0.0, -0.030)), (sh + el) * 0.5,
               el + Vector((-0.004 * s, 0.0, 0.010)), mid,
               mid + Vector((0.004 * s, -0.004, -0.032))]
        radii = [(0.058, 0.060), (0.053, 0.055), (0.047, 0.049), (0.043, 0.044),
                 (0.041, 0.042)]
        ob = _limb("shirt_sleeve_%d" % s, pts, radii, "shirt", 14, 2.2, 2.2, False, False)
        out.append(_P(ob, True))
        # 卷起的袖口：一圈更粗的布
        out.append(_P(_limb("shirt_cuff_%d" % s,
                            [mid + Vector((0.004 * s, -0.004, -0.026)),
                             mid + Vector((0.004 * s, -0.004, -0.040)),
                             mid + Vector((0.004 * s, -0.004, -0.050))],
                            [(0.044, 0.045), (0.046, 0.047), (0.041, 0.042)],
                            "shirt", 14, 2.2, 2.2, False, False), True))
    # 敞开的领口：两片翻领
    for s in (1, -1):
        pts = [Vector((0.010 * s, -0.098, 1.446)),
               Vector((0.048 * s, -0.096, 1.404)),
               Vector((0.062 * s, -0.086, 1.360))]
        rings = []
        for p in pts:
            rings.append([p + Vector((-0.020 * s, -0.004, 0.0)),
                          p + Vector((0.022 * s, -0.010, 0.006)),
                          p + Vector((0.020 * s, 0.008, -0.004))])
        out.append(_P(_loft("shirt_collar_%d" % s, rings, "shirt", True, True, True), True))
    return out


def build_scarf():
    out = []
    rings = []
    for z, r, dz in ((1.418, 0.086, 0.0), (1.436, 0.092, 0.0),
                     (1.456, 0.094, 0.0), (1.474, 0.090, 0.0),
                     (1.490, 0.082, 0.0)):
        def warp(a, ux, uy, z=z):
            bump = 0.006 * math.sin(a * 3.0 + z * 20.0)
            return (ux * bump, uy * bump)
        rings.append(_ring_z((0.0, -0.028, z), r, r * 0.96, 22, 2.1, 2.1, warp=warp))
    out.append(_P(_loft("scarf_band", rings, "scarf", True, False, False), True))
    # 胸前垂下来的一角
    tail = []
    for i in range(6):
        t = i / 5.0
        z = 1.470 - 0.250 * t
        y = -0.108 - 0.012 * t + 0.010 * math.sin(t * 5.0)
        x = -0.030 + 0.026 * t + 0.012 * math.sin(t * 3.4)
        w = 0.030 + 0.010 * math.sin(t * 3.0)
        tail.append([Vector((x - w, y - 0.004, z)),
                     Vector((x - w * 0.35, y - 0.014, z - 0.006)),
                     Vector((x + w * 0.55, y - 0.010, z - 0.004)),
                     Vector((x + w, y + 0.002, z))])
    ob = _loft("scarf_tail", tail, "scarf", True, True, True)
    out.append(_P(ob, True))
    # 前方打的那一团结：没有它只剩一圈布箍，读不出一条裹起来的围巾
    out.append(_P(_ellipsoid("scarf_knot", (-0.014, -0.098, 1.452),
                             (0.030, 0.024, 0.026), "scarf", 14, 10), True))
    out.append(_P(_ellipsoid("scarf_knot_b", (-0.030, -0.092, 1.436),
                             (0.020, 0.018, 0.018), "scarf", 12, 8), True))
    return out


def build_pants():
    out = []
    rings = []
    for z, rx, ry in ((1.010, 0.150, 0.107), (0.970, 0.155, 0.111),
                      (0.930, 0.159, 0.115), (0.890, 0.157, 0.115),
                      (0.850, 0.148, 0.112)):
        rings.append(_ring_z((0.0, -0.002, z), rx, ry, 22, 2.4, 2.2))
    out.append(_P(_loft("pants_hips", rings, "pants", True, True, True), True))
    for s in (1, -1):
        hp = _m(HIP_J, s)
        kn = _m(KNEE_J, s)
        an = _m(ANKLE_J, s)
        # 膝盖处加两段前鼓：原来从大腿到裤脚是一条直锥，侧面看是根筒子。
        pts = [hp + Vector((0.0, 0.0, 0.040)), hp,
               (hp + kn) * 0.5 + Vector((0.002 * s, 0.004, 0.0)),
               kn + Vector((0.0, -0.004, 0.062)),
               kn + Vector((0.0, -0.009, 0.022)),
               kn + Vector((0.0, -0.002, 0.0)),
               kn + Vector((0.0, 0.002, -0.040)),
               (kn + an) * 0.5 + Vector((0.0, 0.010, 0.0)),
               an + Vector((0.0, 0.004, 0.060)), an + Vector((0.0, 0.004, 0.020))]
        radii = [(0.093, 0.098), (0.090, 0.095), (0.085, 0.090), (0.081, 0.086),
                 (0.079, 0.085), (0.076, 0.080), (0.072, 0.076), (0.072, 0.074),
                 (0.066, 0.068), (0.064, 0.066)]
        ob = _limb("pants_leg_%d" % s, pts, radii, "pants", 16, 2.3, 2.2, True, True)
        out.append(_P(ob, True))
        # 大腿侧袋（鼓鼓囊囊）
        out.append(_P(_box("cargo_%d" % s, (0.152 * s, -0.028, 0.690),
                           (0.030, 0.105, 0.150), "pants",
                           rot=(0.0, math.radians(3 * s), 0.0), bevel=0.012), True))
        out.append(_P(_box("cargo_flap_%d" % s, (0.156 * s, -0.030, 0.762),
                           (0.026, 0.108, 0.030), "pants",
                           rot=(0.0, math.radians(3 * s), 0.0), bevel=0.010), True))
        # 裤脚的沙土皱褶
        out.append(_P(_limb("pants_hem_%d" % s,
                            [an + Vector((0.0, 0.006, 0.048)),
                             an + Vector((0.0, 0.004, 0.026)),
                             an + Vector((0.0, 0.002, 0.008))],
                            [(0.070, 0.072), (0.074, 0.076), (0.068, 0.070)],
                            "pants", 16, 2.3, 2.2, False, False), True))
    # 左膝补丁
    out.append(_P(_box("knee_patch", (-0.104, -0.086, 0.508),
                       (0.086, 0.026, 0.110), "patch",
                       rot=(math.radians(4), 0.0, 0.0), bevel=0.014), True))
    # 皮带
    belt_rings = []
    for z, r in ((0.984, 0.162), (1.000, 0.164), (1.012, 0.161)):
        belt_rings.append(_ring_z((0.0, -0.002, z), r, r * 0.72, 22, 2.5, 2.3))
    out.append(_P(_loft("belt", belt_rings, "leather_dark", True, False, False), True))
    out.append(_P(_box("buckle", (0.000, -0.122, 0.998), (0.044, 0.014, 0.030),
                       "metal", bevel=0.005), True))
    return out


def build_boots():
    out = []
    for s in (1, -1):
        an = _m(ANKLE_J, s)
        # 靴筒
        # 靴筒要比裤脚(半径 0.068)粗,才能在裤脚下露出靴口——
        # 之前 0.060 比裤脚还细,整只靴子只剩脚面,读成"平底鞋"(踩过)
        pts = [Vector((an.x, an.y - 0.006, 0.300)),
               Vector((an.x, an.y - 0.004, 0.230)),
               Vector((an.x, an.y, 0.150)),
               Vector((an.x, an.y + 0.004, 0.085))]
        radii = [(0.079, 0.081), (0.076, 0.078), (0.072, 0.076), (0.068, 0.074)]
        out.append(_P(_limb("boot_shaft_%d" % s, pts, radii, "boot",
                            16, 2.3, 2.2, True, False), True))
        # 脚面
        foot = _box("boot_foot_%d" % s, (an.x, -0.048, 0.074),
                    (0.102, 0.232, 0.078), "boot", bevel=0.024)
        out.append(_P(foot, True))
        # 鞋头（磨白）
        out.append(_P(_box("boot_toe_%d" % s, (an.x, -0.140, 0.052),
                           (0.086, 0.062, 0.050), "boot",
                           rot=(math.radians(-6), 0.0, 0.0), bevel=0.022), True))
        # 鞋底
        out.append(_P(_box("boot_sole_%d" % s, (an.x, -0.050, 0.015),
                           (0.106, 0.244, 0.030), "sole", bevel=0.010), True))
        out.append(_P(_box("boot_heel_%d" % s, (an.x, 0.048, 0.020),
                           (0.104, 0.070, 0.040), "sole", bevel=0.008), True))
        # 鞋带：几道横条
        for k in range(5):
            z = 0.120 + 0.042 * k
            out.append(_P(_box("lace_%d_%d" % (s, k), (an.x, -0.046 + 0.005 * k, z),
                               (0.044, 0.014, 0.007), "leather_dark", bevel=0.002), True))
    return out

# ============ 配件（刚性，挂到骨骼上）============

def build_shoulders():
    """三角肌：把躯干侧壁与袖子之间的台阶填掉，肩线才不是一块方板"""
    out = []
    for s in (1, -1):
        sh = _m(SHOULDER, s)
        # 略扁一点的椭球:0.072 半径在 x 方向上会把肩头撑成方肩(踩过)
        ob = _ellipsoid("deltoid_%d" % s, (sh.x - 0.020 * s, sh.y, sh.z - 0.002),
                        (0.062, 0.070, 0.066), "leather", 16, 12)
        out.append(_P(ob, True))
        # 肩线压出的背带印：贴着肩顶的窄条,不能浮在肩头变成肩章
        out.append(_P(_box("shoulder_seam_%d" % s, (sh.x * 0.70, sh.y - 0.004, sh.z + 0.030),
                           (0.012, 0.118, 0.009), "leather_dark",
                           rot=(0.0, 0.0, 0.0), bevel=0.003), True))
    return out


def _noise_displace(ob, amp=0.0018, scale=14.0, seed=0.0):
    """沿法线做低频扰动，给皮革/布料一点不平整（贴图形变之外的第二层细节）"""
    from mathutils import noise as mnoise
    me = ob.data
    off = float(seed) * 3.7
    for v in me.vertices:
        n = v.normal
        w = mnoise.noise(Vector((v.co.x * scale + off, v.co.y * scale + off,
                                 v.co.z * scale + off)))
        v.co += n * (w * amp)
    me.update()


def build_cap():
    out = []
    rings = []
    for z, rx, ry in ((1.717, 0.082, 0.090), (1.732, 0.087, 0.095),
                      (1.748, 0.082, 0.088), (1.762, 0.070, 0.076),
                      (1.775, 0.048, 0.052), (1.784, 0.020, 0.022)):
        rings.append(_ring_z((0.0, -0.030, z), rx, ry, 22, 2.3, 2.35))
    ob = _loft("cap", rings, "canvas", True, False, True)
    _subdiv(ob, 1)
    _mark_sharp(ob, 46.0)
    out.append(_P(ob, False))
    # 帽檐：前低后高的薄片
    brim = []
    for i in range(5):
        t = i / 4.0
        y = -0.092 - 0.046 * t
        z = 1.724 - 0.020 * t
        w = 0.070 - 0.020 * t
        brim.append([Vector((-w, y, z + 0.012)), Vector((-w * 0.98, y, z - 0.004)),
                     Vector((w * 0.98, y, z - 0.004)), Vector((w, y, z + 0.012))])
    out.append(_P(_loft("cap_brim", brim, "canvas", True, True, True), False))
    return out


def build_goggles():
    """护目镜推在额前、贴着头围扣住，而不是像护目镜一样挡在眼睛前面。
    参考图里是两片圆形镜片架在眉弓上方：镜带要贴头围，镜片得压在镜带外侧，
    否则整副镜子会陷进带子里只剩一条黑箍（踩过）。
    方框镜片会读成"面罩"，所以镜片用压扁的椭球做圆形。"""
    out = []
    band = []
    for z, r in ((1.692, 0.0785), (1.702, 0.0805), (1.712, 0.0775)):
        band.append(_ring_z((0.0, -0.030, z), r, r * 1.02, 20, 2.3, 2.3))
    out.append(_P(_loft("goggle_band", band, "leather_dark", True, False, False), False))
    for s in (1, -1):
        cx = 0.031 * s
        # 镜框(金属圈)在镜片后面一点,露出一圈边
        out.append(_P(_ellipsoid("goggle_frame_%d" % s, (cx, -0.0890, 1.7020),
                                 (0.0350, 0.0145, 0.0330), "metal", 18, 10,
                                 rot=(math.radians(-18), 0.0, 0.0)), False))
        out.append(_P(_ellipsoid("goggle_lens_%d" % s, (cx, -0.1005, 1.7050),
                                 (0.0290, 0.0088, 0.0270), "lens", 18, 10,
                                 rot=(math.radians(-18), 0.0, 0.0)), False))
        # 镜框到镜带的连接片
        out.append(_P(_box("goggle_arm_%d" % s, (0.0650 * s, -0.072, 1.7020),
                           (0.016, 0.026, 0.009), "metal",
                           bevel=0.003), False))
    # 两片之间的鼻梁连接
    out.append(_P(_box("goggle_bridge", (0.0, -0.0975, 1.7035), (0.020, 0.010, 0.008),
                       "metal", bevel=0.002), False))
    return out


def build_backpack():
    out = []
    # 主体：宽度收到比肩窄,高度落在背阔肌这一段。
    # 原来的 0.30x0.41 在 1.78 m 的人身上相当于 60 L 大包,背面整个糊成一块板。
    out.append(_P(_box("pack_main", (0.0, 0.146, 1.168), (0.255, 0.165, 0.330),
                       "canvas", bevel=0.032), False))
    # 顶盖
    out.append(_P(_box("pack_flap", (0.0, 0.144, 1.326), (0.262, 0.176, 0.050),
                       "canvas", rot=(math.radians(4), 0.0, 0.0), bevel=0.016), False))
    # 外袋 + 皮带扣
    out.append(_P(_box("pack_pocket", (0.0, 0.228, 1.132), (0.180, 0.055, 0.190),
                       "canvas", bevel=0.022), False))
    out.append(_P(_box("pack_strap_a", (0.0, 0.260, 1.186), (0.034, 0.012, 0.140),
                       "leather_dark", bevel=0.004), False))
    out.append(_P(_box("pack_buckle", (0.0, 0.266, 1.132), (0.028, 0.010, 0.026),
                       "metal", bevel=0.004), False))
    # 侧面小袋
    for s in (1, -1):
        out.append(_P(_box("pack_side_%d" % s, (0.140 * s, 0.146, 1.106),
                           (0.034, 0.142, 0.150), "canvas", bevel=0.016), False))
    # 睡垫：横放在背包顶上(位置跟着包顶下移,别顶到后脑)
    roll = _limb("pack_bedroll",
                 [Vector((-0.152, 0.146, 1.368)), Vector((0.0, 0.146, 1.368)),
                  Vector((0.152, 0.146, 1.368))],
                 [(0.042, 0.042), (0.046, 0.046), (0.042, 0.042)],
                 "canvas", 12, 2.0, 2.0, True, True)
    out.append(_P(roll, False))
    for s in (1, -1):
        out.append(_P(_box("bedroll_band_%d" % s, (0.076 * s, 0.146, 1.368),
                           (0.014, 0.094, 0.094), "leather_dark", bevel=0.003), False))
    # 肩带：从胸前绕过肩到背包
    for s in (1, -1):
        pts = [Vector((0.098 * s, -0.086, 1.310)),
               Vector((0.112 * s, -0.058, 1.400)),
               Vector((0.118 * s, 0.010, 1.436)),
               Vector((0.110 * s, 0.080, 1.400)),
               Vector((0.096 * s, 0.120, 1.320)),
               Vector((0.090 * s, 0.150, 1.220))]
        radii = [(0.030, 0.010), (0.032, 0.011), (0.034, 0.012),
                 (0.033, 0.012), (0.030, 0.011), (0.028, 0.010)]
        out.append(_P(_limb("pack_shoulder_%d" % s, pts, radii, "leather_dark",
                            10, 2.4, 2.0, True, True), False))
    return out


def build_gear():
    out = []
    # 斜挎胸包（右肩→左腰）
    out.append(_P(_box("chest_bag", (-0.085, -0.128, 1.140), (0.170, 0.062, 0.115),
                       "canvas", rot=(0.0, 0.0, math.radians(16)), bevel=0.018), False))
    out.append(_P(_box("chest_bag_flap", (-0.085, -0.140, 1.190), (0.174, 0.040, 0.040),
                       "leather_dark", rot=(0.0, 0.0, math.radians(16)), bevel=0.012), False))
    strap = [Vector((0.118, -0.052, 1.408)), Vector((0.060, -0.096, 1.330)),
             Vector((-0.020, -0.112, 1.235)), Vector((-0.086, -0.120, 1.150)),
             Vector((-0.130, -0.090, 1.080))]
    out.append(_P(_limb("chest_bag_strap", strap,
                        [(0.026, 0.008), (0.026, 0.008), (0.024, 0.008),
                         (0.022, 0.007), (0.020, 0.007)],
                        "leather_dark", 8, 2.4, 2.0, True, True), False))
    # 脖子上的小皮袋
    out.append(_P(_box("neck_pouch", (0.046, -0.112, 1.330), (0.052, 0.038, 0.062),
                       "leather", rot=(0.0, 0.0, math.radians(-10)), bevel=0.010), False))
    out.append(_P(_limb("neck_cord", [Vector((0.020, -0.086, 1.440)),
                                      Vector((0.040, -0.100, 1.386)),
                                      Vector((0.046, -0.106, 1.352))],
                        [(0.004, 0.004), (0.004, 0.004), (0.004, 0.004)],
                        "leather_dark", 6, 2.0, 2.0, True, True), False))
    # 军绿水壶（左侧腰）
    out.append(_P(_limb("canteen",
                        [Vector((0.168, 0.020, 0.890)), Vector((0.170, 0.020, 0.960)),
                         Vector((0.168, 0.020, 1.020))],
                        [(0.038, 0.026), (0.042, 0.029), (0.030, 0.022)],
                        "metal", 14, 2.0, 2.0, True, True), False))
    out.append(_P(_box("canteen_cap", (0.168, 0.020, 1.032), (0.030, 0.030, 0.022),
                       "metal", bevel=0.005), False))
    # 工具套（右侧腰）+ 折刀
    out.append(_P(_box("tool_pouch", (-0.158, 0.010, 0.930), (0.052, 0.078, 0.130),
                       "leather_dark", rot=(0.0, math.radians(-4), 0.0), bevel=0.014), False))
    out.append(_P(_box("tool_knife", (-0.166, -0.030, 0.985), (0.020, 0.026, 0.090),
                       "metal", rot=(math.radians(10), 0.0, 0.0), bevel=0.004), False))
    # 后腰小包
    out.append(_P(_box("hip_pouch", (0.0, 0.128, 0.960), (0.120, 0.060, 0.090),
                       "leather", bevel=0.014), False))
    # 水壶挂带 / 小铁壶（背包侧面）
    out.append(_P(_limb("pack_kettle",
                        [Vector((-0.186, 0.120, 1.100)), Vector((-0.188, 0.120, 1.160))],
                        [(0.030, 0.030), (0.026, 0.026)], "metal", 12, 2.0, 2.0,
                        True, True), False))
    return out

# ============ 材质 ============

# (基色, 粗糙度, 金属度, 自发光强度)
SHADES = {
    "skin": ((0.196, 0.112, 0.074), 0.62, 0.0),
    # 参考图是深红棕旧皮衣，原来 (0.074,0.040,0.023) 渲出来偏浅偏黄
    "leather": ((0.062, 0.031, 0.019), 0.72, 0.0),
    "leather_dark": ((0.036, 0.020, 0.012), 0.76, 0.0),
    # 军靴：比皮衣浅一档的翻毛皮，与裤脚拉开层次
    "boot": ((0.105, 0.072, 0.042), 0.86, 0.0),
    "shirt": ((0.118, 0.107, 0.094), 0.92, 0.0),
    "canvas": ((0.094, 0.079, 0.058), 0.94, 0.0),
    "pants": ((0.082, 0.066, 0.045), 0.95, 0.0),
    "patch": ((0.052, 0.038, 0.025), 0.94, 0.0),
    "metal": ((0.048, 0.045, 0.041), 0.52, 0.85),
    "lens": ((0.010, 0.012, 0.014), 0.18, 0.55),
    "scarf": ((0.104, 0.030, 0.026), 0.90, 0.0),
    "hair": ((0.028, 0.021, 0.016), 0.68, 0.0),
    "eye": ((0.150, 0.136, 0.122), 0.34, 0.0),
    "iris": ((0.032, 0.019, 0.013), 0.24, 0.0),
    "sole": ((0.028, 0.026, 0.024), 0.88, 0.0),
}


def setup_materials():
    """先给基础 PBR；贴图由 wst_char_tex.py 追加（GLB 里只认贴图/常量）"""
    for key, (col, rough, metal) in SHADES.items():
        mat = _get_mat(key)
        nt = mat.node_tree
        bsdf = None
        for n in nt.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                bsdf = n
                break
        if bsdf is None:
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        mat.roughness = rough
        mat.metallic = metal
        mat.diffuse_color = (col[0], col[1], col[2], 1.0)


# ============ 装配 ============

def _purge():
    global PARTS
    PARTS = []
    _MATS.clear()
    for ob in [o for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        me = ob.data if ob.type == 'MESH' else None
        bpy.data.objects.remove(ob, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    for mat in [m for m in bpy.data.materials if m.name.startswith("wst_mat_char_")]:
        bpy.data.materials.remove(mat, do_unlink=True)
    col = bpy.data.collections.get(COL)
    if col is not None:
        bpy.data.collections.remove(col)


def build(low=False):
    """建整套角色（A-pose / 面朝 -Y），返回统计"""
    _purge()
    _ensure_collection()
    setup_materials()

    build_torso()
    build_neck()
    build_head()
    build_face()
    build_hair()
    build_shoulders()
    build_arms()
    build_hands()
    build_shirt()
    build_jacket()
    build_scarf()
    build_pants()
    build_boots()
    build_cap()
    build_goggles()
    build_backpack()
    build_gear()

    # 布料/皮革的不平整：沿法线的低频扰动，避免一眼看去是光滑塑料壳
    for i, (ob, _deform) in enumerate(PARTS):
        mat = ob.data.materials[0].name if ob.data.materials else ""
        if mat.endswith(("_leather", "_leather_dark")):
            _noise_displace(ob, 0.0016, 16.0, seed=i)
        elif mat.endswith(("_pants", "_shirt", "_canvas", "_patch")):
            _noise_displace(ob, 0.0012, 20.0, seed=i * 1.3)

    # 贴图：颜色必须烘进像素（节点乘色导不进 GLB），UV 用逐面立方投影
    import wst_char_tex
    tex_rep = wst_char_tex.build(SHADES)

    tris = 0
    verts = 0
    for ob, _deform in PARTS:
        me = ob.data
        verts += len(me.vertices)
        tris += sum(max(0, len(p.vertices) - 2) for p in me.polygons)
    rep = {
        "objects": len(PARTS),
        "verts": verts,
        "tris": tris,
        "materials": len([m for m in bpy.data.materials if m.name.startswith("wst_mat_char_")]),
        "tex": tex_rep,
    }
    print("CHAR ok objects=%d verts=%d tris=%d tex=%d" % (
        rep["objects"], rep["verts"], rep["tris"], len(tex_rep["materials"])))
    return rep


def preview(out_dir, views=(("front", (0.0, -3.10, 1.05)), ("q34", (1.95, -2.45, 1.30)),
                            ("side", (3.05, -0.20, 1.05)), ("back", (0.10, 3.05, 1.10))),
            size=(560, 760), samples=24):
    """快速预览：中性灰世界 + 三点光，逐角度渲一张"""
    import os
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = samples
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Punchy'
    except Exception:
        pass
    scene.view_settings.exposure = 0.0

    if scene.world is None:
        scene.world = bpy.data.worlds.new("char_world")
    world = scene.world
    world.use_nodes = True
    nt = world.node_tree
    # 场景世界是大气节点树（输出接的是 AddShader），直接改它的 Background 没用；
    # 预览要一块干净的中性灰底：临时插一个 Background 直连 World Output，渲完还原。
    wout = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputWorld")
    prev_link = wout.inputs["Surface"].links[0].from_socket if wout.inputs["Surface"].links else None
    tmp_bg = nt.nodes.new("ShaderNodeBackground")
    tmp_bg.name = "CharPreviewBG"
    tmp_bg.inputs[0].default_value = (0.30, 0.29, 0.28, 1.0)
    tmp_bg.inputs[1].default_value = 0.85
    nt.links.new(tmp_bg.outputs["Background"], wout.inputs["Surface"])

    cam = bpy.data.objects.get(PREFIX + "cam")
    if cam is None:
        data = bpy.data.cameras.new(PREFIX + "cam")
        cam = bpy.data.objects.new(PREFIX + "cam", data)
        bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = 55.0
    scene.camera = cam

    for name, dirs in (("key", (1.6, -2.0, 2.4)), ("fill", (-2.2, -1.4, 1.6)),
                       ("rim", (0.4, 2.4, 2.2))):
        lamp = bpy.data.objects.get(PREFIX + "light_" + name)
        if lamp is None:
            ldata = bpy.data.lights.new(PREFIX + "light_" + name, 'AREA')
            ldata.size = 3.0
            lamp = bpy.data.objects.new(PREFIX + "light_" + name, ldata)
            bpy.context.scene.collection.objects.link(lamp)
        lamp.location = Vector(dirs)
        lamp.data.energy = {"key": 260.0, "fill": 70.0, "rim": 130.0}[name]
        lamp.rotation_euler = (Vector((0.0, 0.0, 1.05)) - lamp.location).to_track_quat('-Z', 'Y').to_euler()

    target = Vector((0.0, 0.0, 0.95))
    names = []
    for name, pos in views:
        cam.location = Vector(pos)
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        path = os.path.join(out_dir, PREFIX + "view_" + name + ".png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        names.append(path)

    if prev_link is not None:
        nt.links.new(prev_link, wout.inputs["Surface"])
    nt.nodes.remove(tmp_bg)
    return names




# ============ 关节位置（面朝 -Y，右侧 x>0）============
SHOULDER = Vector((X_SHOULDER, -0.008, 1.412))
ELBOW = Vector((X_ELBOW, 0.004, 1.168))
WRIST = Vector((X_WRIST, -0.018, 0.902))
HAND_END = Vector((0.296, -0.030, 0.782))
HIP_J = Vector((X_HIP, 0.000, Z_HIP))
KNEE_J = Vector((0.104, -0.014, Z_KNEE))
ANKLE_J = Vector((0.106, 0.014, Z_ANKLE))
TOE_J = Vector((0.106, -0.128, 0.036))

PARTS = []          # [(object, deform)]，deform=False 的走骨骼父子（刚性配件）


def _P(ob, deform=True):
    PARTS.append((ob, deform))
    return ob


def _m(v, s):
    """把右侧关节镜像到左侧"""
    return Vector((v.x * s, v.y, v.z))


# ============ 躯干 / 颈 / 头（皮肤）============

TORSO_RINGS = [
    (0.880, 0.150, 0.104),
    (0.940, 0.152, 0.106),
    (1.000, 0.146, 0.100),
    (1.060, 0.139, 0.097),
    (1.120, 0.146, 0.101),
    (1.180, 0.157, 0.108),
    (1.240, 0.166, 0.113),
    (1.300, 0.174, 0.117),
    (1.360, 0.178, 0.113),
    (1.410, 0.172, 0.104),
    (1.442, 0.132, 0.090),
    (1.462, 0.100, 0.076),
]


def _torso_y(z):
    """驼背：身高越往上越前移，胸口 -0.02 m"""
    return Y_LEAN * max(0.0, (z - 0.95) / 0.50) ** 0.9


def build_torso():
    rings = []
    for z, rx, ry in TORSO_RINGS:
        def warp(a, ux, uy, z=z):
            dy = 0.0
            dz = 0.0
            if z > 1.28 and uy < -0.2:      # 胸大肌前凸
                dy -= 0.008 * (-uy)
            if z > 1.38 and uy > 0.3:       # 背部略平
                dy -= 0.004 * uy
            return (0.0, dy, dz)
        rings.append(_ring_z((0.0, _torso_y(z), z), rx, ry, 24, 2.3, 2.2, warp=warp))
    ob = _loft("torso", rings, "skin", True, True, True)
    _P(ob)
    return ob


def build_neck():
    pts = [Vector((0.0, _torso_y(1.42) - 0.004, 1.408)),
           Vector((0.0, _torso_y(1.44) - 0.010, 1.452)),
           Vector((0.0, _torso_y(1.48) - 0.018, 1.500)),
           Vector((0.0, -0.030, 1.528))]
    radii = [(0.066, 0.060), (0.058, 0.055), (0.049, 0.049), (0.046, 0.047)]
    ob = _limb("neck", pts, radii, "skin", 16, 2.2, 2.1, False, False)
    _P(ob)
    return ob


# 下巴从 1.498 提到 1.529：原来「下巴—眉弓」有 0.154 m，比真人长 40%，
# 正面看是马脸（踩过）。现在下巴尖 1.529、眼位 1.631、眉弓 1.650、头顶 1.766。
HEAD_RINGS = [
    (1.529, 0.026, 0.036),   # 下巴尖
    (1.540, 0.046, 0.055),
    (1.552, 0.060, 0.068),   # 下颌前部
    (1.566, 0.070, 0.078),   # 下颌角
    (1.582, 0.077, 0.085),   # 面颊
    (1.600, 0.080, 0.088),
    (1.616, 0.081, 0.089),   # 颧骨
    (1.632, 0.079, 0.086),   # 眼位
    (1.650, 0.077, 0.083),   # 眉弓
    (1.668, 0.075, 0.080),
    (1.696, 0.072, 0.077),
    (1.726, 0.063, 0.068),
    (1.750, 0.048, 0.052),
    (1.766, 0.026, 0.028),
]


def build_head():
    rings = []
    for z, rx, ry in HEAD_RINGS:
        t = (z - 1.498) / 0.268

        def warp(a, ux, uy, z=z, t=t):
            dy = 0.0
            dx = 0.0
            if uy < -0.35:                     # 正面
                if 1.529 < z < 1.545:          # 下巴略前探
                    dy -= 0.005
                if 1.606 < z < 1.636:          # 眼窝内凹
                    dy += 0.0075 * (-uy - 0.35) / 0.65
                if 1.640 < z < 1.662:          # 眉弓前凸
                    dy -= 0.0060 * (-uy - 0.35) / 0.65
                if 1.566 < z < 1.604:          # 面颊内收（吃不饱）
                    dy += 0.0040 * (-uy - 0.35) / 0.65
            if uy > 0.35:                      # 后脑
                dy -= 0.003 * (uy - 0.35)
            if 1.598 < z < 1.628 and abs(ux) > 0.45:   # 颧骨外张
                dx += 0.0040 * ux * (abs(ux) - 0.45) / 0.55
            if 1.548 < z < 1.580:                      # 下颌角方一点（男性）
                dx += 0.0030 * ux * (1.0 - abs(uy))
            if z < 1.546 and uy < -0.2:                # 下巴前探
                dy -= 0.0060 * (-uy)
            return (dx, dy, 0.0)

        rings.append(_ring_z((0.0, -0.030, z), rx, ry, 26, 2.25, 2.35, warp=warp))
    ob = _loft("head", rings, "skin", True, True, True)
    _subdiv(ob, 1)
    _mark_sharp(ob, 44.0)
    _P(ob)
    return ob


def build_face():
    """五官全部贴在「脸壳表面」上：头部环 ry≈0.086、中心 y=-0.030，
    所以正面皮肤在 y≈-0.110。原先眼球放在 -0.079（陷在颅骨里、根本看不见）、
    嘴唇用两块方片（像栅栏）——这两处是第一次特写渲出来最扎眼的问题。"""
    out = []
    # 鼻子：鼻根→鼻梁→鼻头→鼻小柱
    # 鼻头缩到 -0.1165:原来 -0.1235 比脸壳凸出 27 mm,正面读成鹰钩鼻
    nose_pts = [Vector((0.0, -0.1010, 1.6450)),
                Vector((0.0, -0.1105, 1.6230)),
                Vector((0.0, -0.1165, 1.6040)),
                Vector((0.0, -0.1130, 1.5920)),
                Vector((0.0, -0.1025, 1.5860))]
    nose_radii = [(0.0095, 0.0100), (0.0122, 0.0132), (0.0155, 0.0165),
                  (0.0195, 0.0170), (0.0225, 0.0140)]
    out.append(_P(_limb("nose", nose_pts, nose_radii, "skin", 12, 2.4, 2.2, True, True, tip_round=0.6), True))
    # 鼻翼
    for s in (1, -1):
        out.append(_P(_ellipsoid("nostril_wing_%d" % s, (0.0185 * s, -0.1090, 1.5935),
                                 (0.0105, 0.0125, 0.0090), "skin", 12, 8), True))

    for s in (1, -1):
        # 耳朵
        out.append(_P(_ellipsoid("ear_%d" % s, (0.0805 * s, -0.020, 1.618),
                                 (0.010, 0.020, 0.029), "skin", 14, 10,
                                 rot=(0.0, math.radians(8 * s), math.radians(-12))), True))
        # 眼球（贴到正面皮肤外，只露出前半球）+ 虹膜 + 瞳孔
        # 眼睛略放大到 14 mm:12 mm 在 16 cm 宽的脸上正面看只剩两个黑点
        out.append(_P(_ellipsoid("eye_%d" % s, (0.0315 * s, -0.0955, 1.6300),
                                 (0.0142, 0.0140, 0.0130), "eye", 16, 10), True))
        out.append(_P(_ellipsoid("iris_%d" % s, (0.0315 * s, -0.1085, 1.6295),
                                 (0.0088, 0.0034, 0.0088), "iris", 14, 8), True))
        out.append(_P(_ellipsoid("pupil_%d" % s, (0.0315 * s, -0.1108, 1.6295),
                                 (0.0042, 0.0024, 0.0042), "hair", 12, 8), True))
        # 上下眼睑：把眼球上下缘压住，只留一条缝 → 才像眼睛而不是玻璃珠
        out.append(_P(_ellipsoid("lid_up_%d" % s, (0.031 * s, -0.0935, 1.6368),
                                 (0.0160, 0.0146, 0.0112), "skin", 16, 8), True))
        out.append(_P(_ellipsoid("lid_lo_%d" % s, (0.031 * s, -0.0940, 1.6242),
                                 (0.0146, 0.0136, 0.0082), "skin", 16, 8), True))
        # 眉毛：贴皮前凸一点，外端略下垂
        out.append(_P(_box("brow_%d" % s, (0.033 * s, -0.1052, 1.6438),
                           (0.043, 0.0075, 0.0068), "hair",
                           rot=(math.radians(-6), math.radians(4 * s), math.radians(-9 * s)),
                           bevel=0.0022), True))

    # 嘴唇：上唇两瓣 + 下唇一瓣（不用方片，避免"栅栏"感）
    for s in (1, -1):
        out.append(_P(_ellipsoid("lip_up_%d" % s, (0.0125 * s, -0.1022, 1.5745),
                                 (0.0135, 0.0095, 0.0052), "skin", 14, 8), True))
    out.append(_P(_ellipsoid("lip_low", (0.0, -0.1010, 1.5650),
                             (0.0215, 0.0105, 0.0068), "skin", 16, 10), True))
    out.append(_P(_box("mouth_line", (0.0, -0.1048, 1.5705), (0.034, 0.0045, 0.0022),
                       "iris", bevel=0.0010), True))

    # 鼻梁上的浅疤：一条比肤色浅的细片
    out.append(_P(_box("scar", (0.007, -0.1048, 1.6420), (0.008, 0.006, 0.019),
                       "patch", rot=(0.0, math.radians(9), 0.0)), True))
    return out


def build_hair():
    """帽子底下的头发：后脑一整片贴着头骨的发壳 + 两鬓。
    以前用一个椭球代替，结果在脑后鼓成一个深色包；现在按 HEAD_RINGS 的半径
    往外推 4 mm 直接放样出后半个头壳，发际线顺着后颈收下去。"""
    out = []
    # 做法：照头骨放样一圈壳（比皮肤外扩 6 mm），再把前半边顶点删掉。
    # 这样头发的轮廓天然是头形的椭圆弧,不会像"切出来的矩形/贴上去的椭圆"。
    # 试过椭球块:背面会变成两块浮在头皮上的深色椭圆(踩过)。
    rings = []
    for z, rx, ry in HEAD_RINGS:
        if z < 1.548 or z > 1.726:
            continue
        rings.append(_ring_z((0.0, 0.0, z), rx + 0.006, ry + 0.006, 24, 2.2, 2.2))
    ob = _loft("hair_shell", rings, "hair", True, False, False)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    front = [v for v in bm.verts if v.co.y < 0.004]
    bmesh.ops.delete(bm, geom=front, context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    _mark_sharp(ob, 40.0)
    out.append(_P(ob, True))
    # 耳后短鬓角:必须贴在后脑一侧,压到 y=0.01 会变成脸上一块黑斑(踩过)
    for s in (1, -1):
        out.append(_P(_ellipsoid("hair_temple_%d" % s, (0.0700 * s, 0.036, 1.648),
                                 (0.010, 0.022, 0.030), "hair", 14, 8), True))
    return out


def build_arms():
    """上臂+前臂皮肤：袖子只到小臂中段，下面这段必须是真的手臂"""
    out = []
    for s in (1, -1):
        sh = _m(SHOULDER, s)
        el = _m(ELBOW, s)
        wr = _m(WRIST, s)
        pts = [sh + Vector((-0.010 * s, -0.004, 0.030)),
               (sh + el) * 0.5 + Vector((0.004 * s, -0.002, 0.004)),
               el,
               (el + wr) * 0.5 + Vector((0.002 * s, -0.006, 0.0)),
               wr + Vector((0.0, -0.002, 0.012))]
        radii = [(0.052, 0.054), (0.047, 0.049), (0.040, 0.042),
                 (0.036, 0.037), (0.029, 0.031)]
        ob = _limb("arm_%d" % s, pts, radii, "skin", 14, 2.2, 2.2, True, True)
        out.append(_P(ob, True))
    return out


def build_hands():
    # 手长按真人比例：腕(0.902) → 指根(0.816) → 指尖(0.72 左右)。
    # 之前整只手只有 7 cm，还带 subdiv，读成一团"连指手套"，五指根本看不出来。
    out = []
    for s in (1, -1):
        w = _m(WRIST, s)
        # —— 手掌：扁而宽的板，往指根略放宽 ——
        palm = [w, w + Vector((0.004 * s, -0.004, -0.030)),
                w + Vector((0.008 * s, -0.008, -0.060)),
                w + Vector((0.010 * s, -0.010, -0.086))]
        palm_r = [(0.026, 0.022), (0.031, 0.025), (0.033, 0.026), (0.031, 0.024)]
        out.append(_P(_limb("hand_%d" % s, palm, palm_r, "skin", 16, 2.7, 2.2,
                            True, True, tip_round=0.25), True))
        # —— 四指：指根到指尖 5.2~6.8 cm，中指最长，指节向前兜 ——
        base = w + Vector((0.010 * s, -0.012, -0.092))
        # 指间距 17 mm、长度 44~58 mm：太张会读成「耙子」，太短又变回连指手套
        fingers = ((-0.0210, 0.052), (-0.0070, 0.058), (0.0070, 0.053), (0.0210, 0.044))
        for i, (dx, length) in enumerate(fingers):
            fx = base.x + dx * s
            out.append(_P(_limb("finger_%d_%d" % (s, i),
                                [Vector((fx, base.y + 0.002, base.z + 0.022)),
                                 Vector((fx, base.y, base.z - 0.014)),
                                 Vector((fx, base.y - 0.006, base.z - 0.040)),
                                 Vector((fx, base.y - 0.014, base.z - 0.040 - (length - 0.036)))],
                                [(0.0084, 0.0084), (0.0078, 0.0078),
                                 (0.0068, 0.0068), (0.0052, 0.0052)],
                                "skin", 8, 2.2, 2.2, True, True, tip_round=0.85), True))
        # —— 拇指：从掌侧往斜下方伸 ——
        th = _limb("thumb_%d" % s,
                   [w + Vector((-0.018 * s, -0.016, -0.026)),
                    w + Vector((-0.030 * s, -0.026, -0.044)),
                    w + Vector((-0.034 * s, -0.038, -0.062)),
                    w + Vector((-0.032 * s, -0.048, -0.078))],
                   [(0.0130, 0.0130), (0.0120, 0.0120), (0.0100, 0.0100),
                    (0.0080, 0.0080)],
                   "skin", 10, 2.2, 2.2, True, True, tip_round=0.85)
        out.append(_P(th, True))
        # —— 指根关节凸包：接住指与掌的转折，避免直接插进手掌 ——
        for i, (dx, _length) in enumerate(fingers):
            out.append(_P(_ellipsoid("knuckle_%d_%d" % (s, i),
                                     (w.x + (0.010 + dx) * s, w.y - 0.014, w.z - 0.080),
                                     (0.0072, 0.0064, 0.0066), "skin", 10, 8), True))
    return out

