"""wst_tree.py — SPEC v1 §3.4 枯树（双主干 + 裸根系），builder-tree 专用。

位置 (-4.0, -6.4, 0)，rot_z=+20°，总高 4.0 m，2.1 m 处双分叉，无叶，末端收尖。
只写 wst_tree_ 前缀对象 + collection_tree + wst_mat_wood 材质。
幂等：先删自己前缀对象再重建；确定性：固定随机种子。

v2（还原度升级）：截面 8→10 边；主干 18 环 + 3 个结节（半径膨胀 + 中轴横移）+ 纵向浅沟；
根系 5 条爪状（贴地摊平、末端埋地）；断枝残桩改为斜切断口；树皮改竖向拉长噪声条纹。

三角统计方式：sum(len(p.vertices) - 2 for p in mesh.polygons)
"""

import bpy
import bmesh
import json
import math
import random

from mathutils import Matrix, Quaternion, Vector

# ---------------------------------------------------------------- 常量（SPEC）
PREFIX = "wst_tree_"
COLLECTION = "collection_tree"
PARENT_COLLECTION = "collection_wasteland"

MAT_NAME = "wst_mat_wood"
MAT_HEX = "4a3525"          # SPEC §3.4 木色（sRGB，视口显示色）
MAT_HEX_DARK = "3a2a1c"     # 深浅条纹基色·深
MAT_HEX_LIGHT = "6a5442"    # 深浅条纹基色·浅
MAT_ROUGHNESS = 0.95

OBJ_TRUNK = PREFIX + "trunk_main"
OBJ_BRANCH_L = PREFIX + "branch_left"
OBJ_BRANCH_R = PREFIX + "branch_right"
OBJ_ROOT_L = PREFIX + "root_left"
OBJ_ROOT_R = PREFIX + "root_right"
OBJECTS = (OBJ_TRUNK, OBJ_BRANCH_L, OBJ_BRANCH_R, OBJ_ROOT_L, OBJ_ROOT_R)

BASE = Vector((-4.20, -4.90, 0.0))     # SPEC §1（构图：距相机 11.5 m，树干落在屏幕 16%，树冠完整在画幅内）
ROT_Z_DEG = 20.0                        # SPEC §1
TARGET_HEIGHT = 4.0                     # SPEC §3.4

SEED = 20240601
SIDES = 8                               # 截面边数（压面数：10→8，树干在 10 m 视距下无差别）
UP = Vector((0.0, 0.0, 1.0))

FORK_Z = 2.10                           # 双分叉高度（SPEC 1.5–2.5 m 区间内）
# 主干半径基准表（z, r），按下表线性插值后再叠结节膨胀
TRUNK_ZS_KEYS = (0.00, 0.09, 0.22, 0.40, 0.62, 0.86, 1.10, 1.34, 1.58, 1.80, 1.98, 2.10)
TRUNK_RS_KEYS = (0.335, 0.300, 0.274, 0.246, 0.236, 0.214, 0.210, 0.196, 0.184, 0.172, 0.162, 0.152)
# 采样环（刻意让 z 落在结节中心上，否则鼓包会被环距抹平）
TRUNK_ZS = (0.00, 0.09, 0.22, 0.33, 0.40, 0.47, 0.55, 0.70, 0.85, 0.88, 0.95,
            1.02, 1.10, 1.25, 1.34, 1.42, 1.50, 1.58, 1.66, 1.75, 1.85, 1.90, 1.95,
            2.00, 2.06, 2.10)
# 结节 (z, 半径倍率, 中轴 dx, 中轴 dy, 高斯宽度)：参考图树干粗细很不均、还带横向疙瘩
TRUNK_KNOTS = (
    (0.40, 1.10, 0.032, 0.019, 0.130),
    (0.95, 1.08, -0.027, 0.021, 0.125),
    (1.50, 1.12, 0.025, -0.023, 0.130),
    (1.90, 1.06, -0.019, 0.015, 0.115),
)
TRUNK_TWIST = 5.10                      # 主干自身旋进（约 0.8 圈）→ 麻花感
TRUNK_RIPPLE = 0.155                    # 截面 2 瓣（椭圆随高度转）→ 拧过的麻花
RIPPLE_N = 2
TRUNK_GROOVE = 0.050                    # 截面 3 瓣纵向浅沟（10 边下 5 瓣会走成碎面片）
GROOVE_N = 3

# 递归生长参数：depth → 每段数 / 子枝数 / 上偏 / 扰动 / 分叉角 / 收细率 / 子枝半径系数 / 子枝长度系数 / 出枝概率
# depth0 = 主枝（各分 4 根），depth1 = 细枝（各分 3 根），depth2 = 末端小杈，depth3 = 末末枝（按概率出，制造"碎"感）
GROW = {
    0: {"segs": 4, "kids": 4, "up": 0.12, "pert": 0.16, "spread": (0.46, 0.86),
        "taper": 0.55, "rad_fall": 0.560, "len_fall": (0.64, 0.80), "kid_p": 1.0},
    1: {"segs": 3, "kids": 4, "up": 0.13, "pert": 0.24, "spread": (0.46, 0.90),
        "taper": 0.58, "rad_fall": 0.560, "len_fall": (0.64, 0.80), "kid_p": 1.0},
    2: {"segs": 3, "kids": 2, "up": 0.05, "pert": 0.34, "spread": (0.55, 1.02),
        "taper": 0.80, "rad_fall": 0.600, "len_fall": (0.52, 0.68), "kid_p": 0.90},
    3: {"segs": 2, "kids": 0, "up": 0.10, "pert": 0.42, "spread": (0.0, 0.0),
        "taper": 0.55, "rad_fall": 0.620, "len_fall": (0.52, 0.68), "kid_p": 1.0},
}
MAX_DEPTH = 3
LEN_FALLOFF = (0.64, 0.80)
RAD_FALLOFF = 0.560   # 缺省收细率（GROW 每档都自带 rad_fall，这里只是兜底）

# 两条主枝（从分叉点出发的方向 / 长度 / 半径）：左右刻意不对称
MAIN_L = {"dir": Vector((-0.50, 0.30, 0.81)), "len": 1.15, "rad": 0.158}
MAIN_R = {"dir": Vector((0.62, -0.34, 0.70)), "len": 1.02, "rad": 0.152}

# 主干上的断枝残桩 (z, 方向, 长度, 半径)：末端斜切（不是平口）
STUBS = (
    {"z": 0.34, "dir": Vector((0.42, 0.80, 0.42)), "len": 0.21, "rad": 0.096},
    {"z": 0.72, "dir": Vector((-0.88, 0.30, 0.36)), "len": 0.26, "rad": 0.105},
    {"z": 1.24, "dir": Vector((0.80, -0.36, 0.48)), "len": 0.20, "rad": 0.088},
    {"z": 1.66, "dir": Vector((-0.66, -0.55, 0.50)), "len": 0.17, "rad": 0.072},
    {"z": 1.88, "dir": Vector((0.60, 0.62, 0.42)), "len": 0.15, "rad": 0.064},
)

# 根系：(方位角°, 伸展距离, 起始高度 z, 起始半径, 侧向摆动系数)
# 5 条朝外铺开，方位刻意不对称 → 爪状而非对称星形。
# 伸展距离刻意压短（原来的 1.30 m 在 5.3 m 树高下读成"贴地扁鳍"）：
# 参考图的根是短、厚、圆钝的板状根，只有根部隆起铺进裂土，不向外伸出长刀片。
ROOTS_LEFT = (
    (162.0, 0.62, 0.46, 0.215, -0.9),
    (205.0, 0.54, 0.42, 0.195, 0.7),
    (243.0, 0.44, 0.36, 0.170, -0.5),
)
ROOTS_RIGHT = (
    (-15.0, 0.60, 0.46, 0.210, 0.8),
    (35.0, 0.48, 0.40, 0.180, -0.6),
)


# ---------------------------------------------------------------- 颜色工具
def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hex_to_linear(hex_str):
    h = hex_str.lstrip("#")
    return tuple(_srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def _perp(direction):
    """给一个方向找正交基 (u, v)。"""
    ref = Vector((1.0, 0.0, 0.0)) if abs(direction.x) < 0.85 else Vector((0.0, 1.0, 0.0))
    u = ref - direction * ref.dot(direction)
    if u.length < 1e-6:
        u = Vector((0.0, 1.0, 0.0)) - direction * direction.y
    u.normalize()
    v = direction.cross(u).normalized()
    return u, v


def _frames(points):
    """沿路径做平行传输标架，避免 Frenet 在近直线段上翻滚。"""
    n = len(points)
    tangents = []
    for i in range(n):
        if i == 0:
            t = points[1] - points[0]
        elif i == n - 1:
            t = points[-1] - points[-2]
        else:
            t = points[i + 1] - points[i - 1]
        if t.length < 1e-9:
            t = Vector((0.0, 0.0, 1.0))
        tangents.append(t.normalized())

    ref = Vector((1.0, 0.0, 0.0)) if abs(tangents[0].x) < 0.85 else Vector((0.0, 1.0, 0.0))
    n0 = ref - tangents[0] * ref.dot(tangents[0])
    if n0.length < 1e-6:
        n0 = Vector((0.0, 1.0, 0.0))
    normals = [n0.normalized()]

    for i in range(1, n):
        prev_t, cur_t = tangents[i - 1], tangents[i]
        nrm = normals[-1]
        axis = prev_t.cross(cur_t)
        if axis.length > 1e-8:
            angle = math.atan2(axis.length, prev_t.dot(cur_t))
            nrm = Quaternion(axis.normalized(), angle) @ nrm
        nrm = nrm - cur_t * nrm.dot(cur_t)
        if nrm.length < 1e-6:
            ref = Vector((1.0, 0.0, 0.0)) if abs(cur_t.x) < 0.85 else Vector((0.0, 1.0, 0.0))
            nrm = ref - cur_t * ref.dot(cur_t)
        normals.append(nrm.normalized())

    binormals = [tangents[i].cross(normals[i]).normalized() for i in range(n)]
    return tangents, normals, binormals


# ---------------------------------------------------------------- 几何：路径 + 截面放样
def add_tube(bm, points, radii, sides=SIDES, twist=0.0, ripple=0.0, ripple_n=RIPPLE_N,
             groove=0.0, groove_n=GROOVE_N, squash=None,
             cap_start=True, tip=True, tip_scale=1.5, slant=0.0):
    """沿 points 放样一条锥形枝干。

    - 半径逐段渐变（基部粗、末端趋 0）
    - twist：截面绕轴渐进旋转 → 麻花/旋进感
    - ripple：半径按 sin(ripple_n * 角) 起伏 → 螺旋深沟（跟着截面一起转，所以是螺旋的）
    - groove：半径按 sin(groove_n * 角) 起伏 → 纵向浅沟（不随高度转）
    - squash：逐环 (u, v) 轴缩放 → 扁平截面（根系贴地摊平用）
    - tip：末端收成尖顶（新增一个锥顶顶点 + 三角扇形），不留平头
    - slant：末端沿轴按 cos(角) 错开 → 斜切断口（断枝残桩用，配合 tip=False）
    """
    n = len(points)
    tangents, normals, binormals = _frames(points)
    rings = []
    for i in range(n):
        p = points[i]
        tw = twist * (i / (n - 1)) if n > 1 else 0.0
        ct, st = math.cos(tw), math.sin(tw)
        u = normals[i] * ct + binormals[i] * st
        v = binormals[i] * ct - normals[i] * st
        su, sv = squash[i] if squash else (1.0, 1.0)
        cut = slant * radii[i] if (slant and i == n - 1) else 0.0
        ring = []
        for j in range(sides):
            a = 2.0 * math.pi * j / sides
            r = radii[i]
            if ripple:
                r *= (1.0 + ripple * math.sin(ripple_n * a + 0.7))
            if groove:
                r *= (1.0 + groove * math.sin(groove_n * a + 1.3))
            pt = p + u * (math.cos(a) * r * su) + v * (math.sin(a) * r * sv)
            if cut:
                pt = pt + tangents[i] * (cut * math.cos(a))
            ring.append(bm.verts.new(pt))
        rings.append(ring)

    for i in range(n - 1):
        for j in range(sides):
            k = (j + 1) % sides
            bm.faces.new((rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]))

    if cap_start:
        bm.faces.new(tuple(reversed(rings[0])))
    if tip:
        apex = bm.verts.new(points[-1] + tangents[-1] * (radii[-1] * tip_scale))
        for j in range(sides):
            k = (j + 1) % sides
            bm.faces.new((rings[-1][j], rings[-1][k], apex))
    else:
        bm.faces.new(tuple(rings[-1]))


# ---------------------------------------------------------------- 主干
def _trunk_center(z):
    """主干中心线：S 形侧弯（先鼓 +X 再回 -X），基部严格落在原点。"""
    x = 0.150 * math.sin(1.9 * z) - 0.020 * z
    y = 0.075 * math.sin(2.3 * z + 1.0) - 0.075 * math.sin(1.0) - 0.018 * z
    return Vector((x, y, z))


def _trunk_base_radius(z):
    """按基准表线性插值出半径。"""
    keys = TRUNK_ZS_KEYS
    if z <= keys[0]:
        return TRUNK_RS_KEYS[0]
    if z >= keys[-1]:
        return TRUNK_RS_KEYS[-1]
    for i in range(len(keys) - 1):
        if keys[i] <= z <= keys[i + 1]:
            t = (z - keys[i]) / (keys[i + 1] - keys[i])
            return TRUNK_RS_KEYS[i] * (1.0 - t) + TRUNK_RS_KEYS[i + 1] * t
    return TRUNK_RS_KEYS[-1]


def _trunk_at(z):
    """返回 (中心点, 半径)：结节处半径膨胀 + 中轴横移。"""
    c = _trunk_center(z)
    r = _trunk_base_radius(z)
    for kz, amp, dx, dy, width in TRUNK_KNOTS:
        w = (z - kz) / width
        g = math.exp(-w * w)
        r *= 1.0 + (amp - 1.0) * g
        c.x += dx * g
        c.y += dy * g
    return c, r


def _build_trunk(bm):
    pts = []
    rads = []
    for z in TRUNK_ZS:
        c, r = _trunk_at(z)
        pts.append(c)
        rads.append(r)
    add_tube(bm, pts, rads, SIDES, twist=TRUNK_TWIST, ripple=TRUNK_RIPPLE,
             groove=TRUNK_GROOVE, cap_start=True, tip=False)
    # 断枝残桩（从主干中心穿出，末端斜切，不是平口）
    for stub in STUBS:
        d = stub["dir"].normalized()
        start = _trunk_center(stub["z"])
        p1 = start + d * (stub["len"] * 0.45)
        p2 = start + d * (stub["len"] * 0.78)
        p3 = start + d * stub["len"] + UP * 0.015
        r0 = stub["rad"]
        add_tube(bm, [start, p1, p2, p3], [r0, r0 * 0.74, r0 * 0.60, r0 * 0.52],
                 SIDES, twist=0.9, ripple=0.10, cap_start=True, tip=False, slant=1.15)
    return pts[-1].copy()


# ---------------------------------------------------------------- 递归枝干
def _grow(bm, start, direction, length, radius, depth, rng):
    cfg = GROW[depth]
    segs = cfg["segs"]
    pts = [start.copy()]
    d = direction.normalized()
    cur = start.copy()
    step = length / segs
    for _ in range(segs):
        jitter = Vector((rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-0.35, 0.7)))
        if jitter.length < 1e-6:
            jitter = Vector((0.0, 0.0, 1.0))
        jitter.normalize()
        d = (d + UP * cfg["up"] + jitter * cfg["pert"]).normalized()
        cur = cur + d * step
        pts.append(cur.copy())

    n = len(pts)
    if depth == 0:
        # 分叉处做"鼓包"（knuckle）：主枝起始半径略小、第二环膨胀，
        # 两条主枝的并集把主干顶面那一圈完全包住，分叉处不会露出"断茬"棱边
        knuckle = (0.90, 1.16, 1.02, 0.90, 0.82)
        rads = [radius * (knuckle[i] if i < len(knuckle) else 0.80) for i in range(n)]
    else:
        # taper = 末环相对半径的收细比例：depth2 用 0.78 → 末梢 ≈1.1 cm
        taper = cfg["taper"]
        rads = [radius * (1.0 - taper * (i / (n - 1))) for i in range(n)]
    kids = cfg["kids"]
    # 无论有没有子枝都要封口：子枝起点环藏在父枝内部，但必须封闭，否则是非流形边界
    sides = SIDES if depth <= 0 else (6 if depth == 1 else 4)  # 深枝减边，压面数预算
    add_tube(bm, pts, rads, sides, twist=rng.uniform(0.7, 1.9), ripple=0.10,
             cap_start=True, tip=(kids <= 0), tip_scale=1.5)

    if kids <= 0 or depth >= MAX_DEPTH:
        return

    base = pts[-1] - d * (rads[-1] * 2.2)   # 子枝起点内缩，藏进父枝
    u, v = _perp(d)
    kid_p = cfg.get("kid_p", 1.0)
    for i in range(kids):
        # 出枝概率（depth2 的末末枝按概率出）：先抽签，保持随机序列确定性
        if rng.random() > kid_p:
            continue
        az = 2.0 * math.pi * i / kids + rng.uniform(-0.45, 0.45)
        spread = 0.18 if i == 0 else rng.uniform(*cfg["spread"])
        nd = (d * math.cos(spread)
              + (u * math.cos(az) + v * math.sin(az)) * math.sin(spread)).normalized()
        _grow(bm, base.copy(), nd,
              length * rng.uniform(*cfg.get("len_fall", LEN_FALLOFF)),
              radius * cfg.get("rad_fall", RAD_FALLOFF), depth + 1, rng)


# ---------------------------------------------------------------- 根系
def _root_path(az_deg, reach, z0, wobble):
    """粗根：从主干基部斜下钻出，短距离铺进地面，末端圆钝地没入裂土。

    返回 (points, squash)：squash 逐环把截面轻微压扁（v 轴 = 近似竖直方向）。
    只做很小的压扁（≤0.82），过度压扁会让根在侧视里变成一片薄刀片。
    """
    a = math.radians(az_deg)
    d = Vector((math.cos(a), math.sin(a), 0.0))
    side = Vector((-d.y, d.x, 0.0))
    fr = (0.18, 0.38, 0.58, 0.76, 0.90, 1.00)
    zs = (z0 * 0.62, z0 * 0.38, 0.150, 0.080, 0.010, -0.075)  # 末两环沉到地面以下，与裂土融合
    off = (0.0, 0.030 * wobble, -0.020 * wobble, 0.038 * wobble, 0.026 * wobble, 0.014 * wobble)
    pts = [Vector((0.0, 0.0, z0))]
    for fac, z, o in zip(fr, zs, off):
        pts.append(d * (reach * fac) + side * o + Vector((0.0, 0.0, z)))
    squash = ((1.00, 1.00), (1.00, 1.00), (1.02, 0.99), (1.04, 0.98), (1.06, 0.96), (1.08, 0.94), (1.10, 0.92))
    return pts, squash


def _build_roots(bm, spec):
    for az, reach, z0, r0, wobble in spec:
        pts, squash = _root_path(az, reach, z0, wobble)
        # 末端保持 r0 的 30%：钝头断根，不是尖锥
        rads = [r0, r0 * 0.90, r0 * 0.82, r0 * 0.70, r0 * 0.58, r0 * 0.44, r0 * 0.30]
        add_tube(bm, pts, rads, SIDES, twist=1.1, ripple=0.11, squash=squash,
                 cap_start=True, tip=True, tip_scale=0.75)


# ---------------------------------------------------------------- 材质
def _make_material():
    """树皮：竖向拉长的条纹（Wave·BANDS 两层 + 一层斜向打散）+ 深浅基色 + bump。"""
    mat = bpy.data.materials.get(MAT_NAME)
    if mat is None:
        mat = bpy.data.materials.new(MAT_NAME)
    if not mat.use_nodes:          # Blender 5.x 新建材质默认已开节点，避免弃用警告
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (380, 0)
    bsdf.inputs["Roughness"].default_value = MAT_ROUGHNESS

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-880, 0)
    # 坐标改用模型 UV（u=周向 0..1、v=沿轴弧长）：条纹沿 u 变化、沿 v 拉开，
    # 于是在主干上是竖纤维、在横躺的粗根上也是"顺根纤维"，不会出现一圈圈斑马环。
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-700, 0)
    mapping.inputs["Scale"].default_value = (1.0, 0.10, 1.0)

    # 竖向条纹（沿 X 的波带 = 与 Z 平行的条纹，被 Distortion 打乱成不规则树皮纤维）
    # 注：Blender 5.2 里 Noise Texture 的 Fac 在本场景中实测输出恒定（已用 debug 渲染确认），
    # 因此改用同语义的 Wave(BANDS/X)：条纹沿 Z 拉长，两级尺度分别对应粗沟与细纤维。
    n_big = nt.nodes.new("ShaderNodeTexWave")
    n_big.location = (-500, 200)
    n_big.wave_type = "BANDS"
    n_big.bands_direction = "DIAGONAL"
    n_big.wave_profile = "SIN"
    n_big.inputs["Scale"].default_value = 6.0
    n_big.inputs["Distortion"].default_value = 3.2
    n_big.inputs["Detail"].default_value = 6.0
    n_big.inputs["Detail Scale"].default_value = 1.6

    n_fine = nt.nodes.new("ShaderNodeTexWave")
    n_fine.location = (-500, -140)
    n_fine.wave_type = "BANDS"
    n_fine.bands_direction = "X"
    n_fine.wave_profile = "SIN"
    n_fine.inputs["Scale"].default_value = 17.0
    n_fine.inputs["Distortion"].default_value = 1.3
    n_fine.inputs["Detail"].default_value = 3.0
    n_fine.inputs["Detail Scale"].default_value = 1.2

    # 两层噪声按 0.72 / 0.28 混合成条纹强度
    m_big = nt.nodes.new("ShaderNodeMath")
    m_big.location = (-260, 220)
    m_big.operation = "MULTIPLY"
    m_big.inputs[1].default_value = 0.52
    m_fine = nt.nodes.new("ShaderNodeMath")
    m_fine.location = (-260, -120)
    m_fine.operation = "MULTIPLY"
    m_fine.inputs[1].default_value = 0.26
    m_alt = nt.nodes.new("ShaderNodeMath")
    m_alt.location = (-260, -420)
    m_alt.operation = "MULTIPLY"
    m_alt.inputs[1].default_value = 0.22
    comb = nt.nodes.new("ShaderNodeMath")
    comb.location = (-60, 60)
    comb.operation = "ADD"
    comb2 = nt.nodes.new("ShaderNodeMath")
    comb2.location = (30, 60)
    comb2.operation = "ADD"

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (120, 220)
    ramp.color_ramp.elements[0].position = 0.26
    ramp.color_ramp.elements[0].color = (*_hex_to_linear(MAT_HEX_DARK), 1.0)
    ramp.color_ramp.elements[1].position = 0.74
    ramp.color_ramp.elements[1].color = (*_hex_to_linear(MAT_HEX_LIGHT), 1.0)

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (150, -140)
    bump.inputs["Strength"].default_value = 0.70
    bump.inputs["Distance"].default_value = 0.05

    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], n_big.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], n_fine.inputs["Vector"])
    n_alt = nt.nodes.new("ShaderNodeTexWave")
    n_alt.location = (-500, -420)
    n_alt.wave_type = "BANDS"
    n_alt.bands_direction = "X"
    n_alt.wave_profile = "SIN"
    n_alt.inputs["Scale"].default_value = 3.0
    n_alt.inputs["Distortion"].default_value = 4.5
    n_alt.inputs["Detail"].default_value = 4.0
    n_alt.inputs["Detail Scale"].default_value = 1.4

    nt.links.new(n_big.outputs["Factor"], m_big.inputs[0])
    nt.links.new(n_fine.outputs["Factor"], m_fine.inputs[0])
    nt.links.new(n_alt.outputs["Factor"], m_alt.inputs[0])
    nt.links.new(mapping.outputs["Vector"], n_alt.inputs["Vector"])
    nt.links.new(m_big.outputs["Value"], comb.inputs[0])
    nt.links.new(m_fine.outputs["Value"], comb.inputs[1])
    nt.links.new(comb.outputs["Value"], comb2.inputs[0])
    nt.links.new(m_alt.outputs["Value"], comb2.inputs[1])
    nt.links.new(comb2.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(comb2.outputs["Value"], bump.inputs["Height"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # 视口显示色（Workbench 证据图用得到；不影响 Cycles 渲染）
    mat.diffuse_color = (*_hex_to_linear(MAT_HEX), 1.0)
    return mat


# ---------------------------------------------------------------- 场景装配
def _scene_root():
    return bpy.context.scene.collection


def _ensure_collections():
    parent = bpy.data.collections.get(PARENT_COLLECTION)
    if parent is None:
        parent = bpy.data.collections.new(PARENT_COLLECTION)
        _scene_root().children.link(parent)
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if coll.name not in parent.children:
        parent.children.link(coll)
    if coll.name in _scene_root().children:
        _scene_root().children.unlink(coll)
    return coll


def _purge_own():
    """幂等：删掉自己前缀的对象与网格（绝不动别的前缀 / 其它 collection）。"""
    removed = []
    for ob in list(bpy.data.objects):
        if ob.name.startswith(PREFIX):
            data = ob.data
            removed.append(ob.name)
            bpy.data.objects.remove(ob, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
    for me in list(bpy.data.meshes):
        if me.name.startswith(PREFIX) and me.users == 0:
            bpy.data.meshes.remove(me)
    return removed


def _finish_object(name, bm, coll, mat, scale):
    for v in bm.verts:
        v.co = v.co * scale
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = BASE
    ob.rotation_euler = (0.0, 0.0, math.radians(ROT_Z_DEG))
    coll.objects.link(ob)
    return ob


def _bbox_world(objs):
    mat = Matrix.Translation(BASE) @ Matrix.Rotation(math.radians(ROT_Z_DEG), 4, "Z")
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for ob in objs:
        for v in ob.data.vertices:
            w = mat @ v.co
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return {
        "min": [round(v, 4) for v in lo],
        "max": [round(v, 4) for v in hi],
        "size": [round(hi[i] - lo[i], 4) for i in range(3)],
    }


def _tris(objs):
    return sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in objs)


# ---------------------------------------------------------------- 入口
def build():
    """幂等构建枯树，返回对象名 list。"""
    removed = _purge_own()
    coll = _ensure_collections()
    mat = _make_material()

    rng = random.Random(SEED)

    bm_trunk = bmesh.new()
    bm_bl = bmesh.new()
    bm_br = bmesh.new()
    bm_rl = bmesh.new()
    bm_rr = bmesh.new()

    fork = _build_trunk(bm_trunk)

    # 主枝从主干内部更深处出发（完全藏进主干截面内，分叉处不出现"套环"）
    start_l = fork - MAIN_L["dir"].normalized() * 0.03
    start_r = fork - MAIN_R["dir"].normalized() * 0.03
    _grow(bm_bl, start_l, MAIN_L["dir"], MAIN_L["len"], MAIN_L["rad"], 0, rng)
    _grow(bm_br, start_r, MAIN_R["dir"], MAIN_R["len"], MAIN_R["rad"], 0, rng)

    _build_roots(bm_rl, ROOTS_LEFT)
    _build_roots(bm_rr, ROOTS_RIGHT)

    # 统一按"最高点 = 4.0 m"做等比缩放（保证 SPEC 总高，等比不破坏形态）
    top = -1e9
    for bm in (bm_trunk, bm_bl, bm_br, bm_rl, bm_rr):
        for v in bm.verts:
            top = max(top, v.co.z)
    scale = TARGET_HEIGHT / top if top > 1e-6 else 1.0

    objs = [
        _finish_object(OBJ_TRUNK, bm_trunk, coll, mat, scale),
        _finish_object(OBJ_BRANCH_L, bm_bl, coll, mat, scale),
        _finish_object(OBJ_BRANCH_R, bm_br, coll, mat, scale),
        _finish_object(OBJ_ROOT_L, bm_rl, coll, mat, scale),
        _finish_object(OBJ_ROOT_R, bm_rr, coll, mat, scale),
    ]

    bpy.context.view_layer.update()

    created = [ob.name for ob in objs]
    bbox = _bbox_world(objs)
    receipt = {
        "created": created,
        "removed": removed,
        "tris": _tris(objs),
        "per_object_tris": {ob.name: sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in objs},
        "verts": sum(len(ob.data.vertices) for ob in objs),
        "bbox": bbox,
        "height": bbox["size"][2],
        "materials": sorted({m.name for ob in objs for m in ob.data.materials if m}),
        "collection": coll.name,
        "scale_applied": round(scale, 5),
        "location": list(BASE),
        "rot_z_deg": ROT_Z_DEG,
        "seed": SEED,
        "sides": SIDES,
        "knots": len(TRUNK_KNOTS),
        "roots": len(ROOTS_LEFT) + len(ROOTS_RIGHT),
        "stubs": len(STUBS),
    }
    return receipt


if __name__ == "__main__":
    result = build()
    print("HEADLESS " + json.dumps(result, ensure_ascii=False))