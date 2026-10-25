# -*- coding: utf-8 -*-
"""wst_tree_spec.py — 按《枯树_纯视觉描述.md》重建枯树（规格驱动，幂等）。

和 v1（wst_tree_recovered.py）的根本区别：
  v1 是"随机递归生长"（GROW 表 + rng 分枝），形态像树但不保证规格；
  本版把文档里每一条硬数字都写成表，几何由表驱动，可逐条核对：
    根盘 Ø1.20 × 0.30 m → 6 条主根（长度 2.2–3.5 m，逐条给定端径 / 压扁 / 拱起 / 分叉）
    → 8 条细根（1 条主根没分叉的补 2 条从根盘出，见 SPEC_CONFLICTS）
    0.5 m 处双主干（左 3.0 m / 右 4.2 m，各自给定侧弯）→ 8 个大枝干（起点高度 / 方向 /
    长度 / 起末径 / 子枝数，子枝合计 15 条 = 文档的"15 条细枝"）
    细节：节疤 4 处、树皮剥落 3 处、树洞 1 处（Ø5 cm 深 10 cm 朝右前方）

坐标：局部 +X = 右、+Y = 后、+Z = 上；整树经 BASE + rot_z 20° 落到场景（与 v1 一致）。
文档里所有"径"按直径解释，几何里一律换成半径（d/2）。

SPEC_CONFLICTS（文档本身的两处不一致，已按下面口径处理，报告里也写明了）：
  1) "细根共 8 条" vs 逐根描述只有 6 条分叉（右远根/后根明确"无分叉"）→ 遵从逐根描述，
     另外 2 条从根盘裙边出（COLLAR_FINE_ROOTS），总数凑够 8。
  2) 双主干"0.5 m 处连成一个粗树墩" vs 参考图里两根在 1 m 以上还并在一起互相缠着 →
     0.5 m 是数学分叉点，截面继续重叠到约 0.9 m，得到参考图的"编织"感，不另建第三根柱子。

  3) 文档只写"大枝端分 N 细枝（合计 15 条）"vs 参考图大枝沿途都带短枝、树冠更厚 →
     15 条末端细枝照文档保留，另给每条大枝补 SPUR_PER_BRANCH 条沿途小侧枝
     （默认 1 条 = 8 条），设为 0 即严格照文档。

三角预算：README 给枯树 4,000 三角；纵沟需要 SIDES_TRUNK=24，实测见 receipt["tris"]。
"""

import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

BUILDERS = os.path.dirname(os.path.abspath(__file__))
if BUILDERS not in sys.path:
    sys.path.insert(0, BUILDERS)

# 放样核心与集合/材质工具复用 v1，不重复实现（DRY）
from wst_tree_recovered import (  # noqa: E402
    _ensure_collections,
    _frames,
    _make_material,
    _perp,
    _purge_own,
)

# ---------------------------------------------------------------- 常量
PREFIX = "wst_tree_"
COLLECTION = "collection_tree"
PARENT_COLLECTION = "collection_wasteland"

MAT_BARK = "wst_mat_wood"           # 树皮（沿用 v1 的程序化材质）
MAT_CORE = "wst_mat_wood_core"      # 剥落后露出的木质（文档第 4 层颜色）
MAT_DARK = "wst_mat_opening"        # 树洞内暗部（场景已有材质，复用）

BASE = Vector((-4.20, -4.90, 0.0))
ROT_Z_DEG = 20.0
SEED = 20260701

SIDES_COLLAR = 28     # 根盘要撑出 6 条板根隆起；16 边时光照下板顶会出现硬折痕
SIDES_TRUNK = 36      # 36 边 = 6 沟 × 6 点：沟底正好落在顶点上（28 边时沟底掉在两个顶点中间，
                      # 实测只挖到 82% 深度，而且左右不对称 → 读起来像"圆沟"而不是"锐缝"）
SIDES_ROOT = 12       # 根也要纵沟：12 边 / 4 沟 = 每沟 3 点
SIDES_SUBROOT = 6
SIDES_BRANCH = 8      # 大枝 8 边 / 3 沟；细枝仍是 4 边（太细看不出沟）
SIDES_TWIG = 4
SIDES_DETAIL = 8

# ---- 树皮纵沟（参考图的标志性特征：干上一条条又深又窄的纵向裂沟）----
# 沟是"窄"的：只有沟底线附近内凹，脊顶保持原半径、脊面几乎全宽 → 指数 >3。
# 沟随 twist 一起转（截面局部角度调制），所以是螺旋沟，不是直棱。
#
# 元组是 (沟数, 深度系数, 锐度[, 相位])；可以叠乘多组来"宽 V 里再陷一条针缝"。
# **相位是对齐用的**：sides 能被沟数整除时，把相位取成让 cos(n*a+phase)=-1 落在一个
# 顶点上，沟底才挖得动（否则最深顶点只到 30–80% 深度，沟看着是圆的）。
# 主干 36 边 / 6 沟 → phase=0；根 12 边 / 4 沟 → phase=60°（=1.0472）。
FLUTE_TRUNK = ((3, 0.10, 2.6, 0.0),      # 三大叶：让干的横断面不是圆而是三瓣
               (6, 0.30, 4.2, 0.0),      # 宽 V：脊面全宽，只有沟底那 2 个顶点内凹
               (6, 0.07, 16.0, 0.0))     # 细针缝：只加深沟底顶点 → "裂到木质层"的锐缝
FLUTE_ROOT = ((4, 0.20, 4.5, 1.0472),)
FLUTE_BRANCH = ((3, 0.18, 5.0, 0.7854),)

# 双主干在 0.5–1.2 m 互相缠绕（参考图里两根在分叉上方还交叉），再各自张开成 V
BRAID_R = 0.055

# 大枝中段的小侧枝：文档只写"端分 N 细枝"，但参考图的大枝沿途都会分叉，
# 树冠才不会显得稀（设为 0 即严格照文档）。
SPUR_PER_BRANCH = 2
SPUR_DIA = (0.020, 0.034)
SPUR_LEN = (0.26, 0.46)

UP = Vector((0.0, 0.0, 1.0))

# 根盘：直径 1.20 m、厚 0.30 m（文档第一段）。轮廓按 z 给直径，0.30 m 以上收进干基
COLLAR_DIA = 1.20
COLLAR_TH = 0.30
# 轮廓给的是"两板根之间"的直径；沿 6 条根方位再叠一圈隆起（COLLAR_FLARE），
# 隆起处最大直径正好到 1.20 m，也就是文档的根盘直径
# 底部多给一圈「埋进土里」的裙边：底板封口落在地面以下就看不见了，
# 省得低机位看见根盘底面像一张悬空的圆盘。
# 上部要收进双主干里（z=0.5 处干半径 ≈0.17 m），否则干根交界处会露出一圈平顶台阶
# —— 之前渲出来像「树站在一个台座上」。
COLLAR_PROFILE = (
    (-0.18, 0.50), (0.00, 0.52), (0.06, 0.48), (0.14, 0.42), (0.22, 0.34),
    (0.30, 0.31), (0.40, 0.27), (0.52, 0.25),
)
COLLAR_RIDGE_MAX = 0.52  # 板根脊在 z=0 处的半径（原 0.60 = 文档根盘 Ø1.20，会撑出一圈平台）
BUTTRESS_FIN = True      # 板根鳍：参考图的根基是连续张开的板根，不是"台座 + 辐条腿"
COLLAR_FLARE_Z = 0.42    # 脊的张开高度；配 h 的指数 2.2（陡降）才是一圈软喇叭口，不立板也不出平台
COLLAR_PLATE_W = 0.42    # 每条板根的角向半宽（弧度）≈ 24°，板之间留深 V 沟
COLLAR_RIPPLE = 0.055
COLLAR_RIPPLE_N = 3

# 主根长度系数。文档给 2.2–3.5 m（张开 6.4–7.0 m），参考图实测张开只有约
# 1.8–2.0 m（≈ 树高的 1/3），照文档做会读成"蜘蛛腿"、还会伸进轿车的占地里；
# 交付用 0.52 对齐参考图，想要严格照文档就把它改回 1.00（对照图见 shots/）。
ROOT_LEN_SCALE = 0.44
ROOT_TAPER_POW = 1.60

# 直径总增益。本地树高 6.5 m，而 wst_finalize.resize_tree() 会把整棵等比压到 5.10 m（×0.78），
# 直径也被一起压细 22%，渲出来是"细绳捆成的干"。参考图实测树干比"文档直径 × 0.78"粗一圈，
# 所以所有直径在这里先放大 1/0.78 ≈ 1.28 倍，缩放后的绝对直径才等于文档值。
DIA_GAIN = 1.28  # 直径随参数衰减的指数：>1 让前段几乎不收、外端才快速收尖

FORK_Z = 0.50      # 双主干分叉高度（文档）

# 双主干：控制点（局部坐标）+ 起末直径
# 左：反写 S —— 下 1 m 左弯、中 1 m 直、上 1 m 微右弯
TRUNK_L_CTRL = (
    (0.00, 0.00, 0.30), (0.00, 0.00, 0.50), (-0.13, 0.03, 0.85),
    (-0.30, 0.05, 1.30), (-0.27, 0.02, 1.75), (-0.13, -0.03, 2.10),
    (0.00, -0.03, 2.45), (0.11, 0.02, 2.75), (0.17, 0.04, 3.00),
)
# 右：更挺拔 —— 下 1.5 m 直、中 1.5 m 微右弯、上 1.2 m 微左弯
TRUNK_R_CTRL = (
    (0.00, 0.00, 0.30), (0.00, 0.00, 0.50), (0.03, -0.02, 0.90),
    (0.06, -0.03, 1.30), (0.09, -0.03, 1.80), (0.17, -0.01, 2.30),
    (0.23, 0.02, 2.80), (0.20, 0.04, 3.20), (0.12, 0.03, 3.70),
    (0.05, 0.01, 4.20),
)

TRUNKS = {
    "L": {"ctrl": TRUNK_L_CTRL, "dia": (0.42, 0.11), "twist": 2.40, "ripple": 0.150},
    "R": {"ctrl": TRUNK_R_CTRL, "dia": (0.39, 0.09), "twist": 2.90, "ripple": 0.150},
}
TRUNK_RIPPLE_N = 3      # 3 条螺旋纵棱（12 边 / 3 棱 = 每瓣 4 点，参考图的麻绳感）
TRUNK_TAPER_POW = 0.70  # 直径随高度衰减的指数：<1 让下段更粗、上段收得更快

# 6 条主根：长/起末直径/离地起始高度/拱起量/上下压扁/侧摆/分叉 [(沿根距离, 长度, 侧向)]
ROOTS = (
    dict(name="front",      az=-90.0, length=3.50, d0=0.21, d1=0.02, z0=0.26,
         arch=0.00, squash=0.78, wobble=0.030, belly=1.00,
         kids=((2.00, 0.50, -1), (2.80, 0.50, +1))),
    dict(name="back",       az=90.0,  length=2.20, d0=0.16, d1=0.03, z0=0.24,
         arch=0.00, squash=0.80, wobble=0.024, belly=1.00, kids=()),
    dict(name="left_far",   az=165.0, length=3.20, d0=0.28, d1=0.04, z0=0.27,
         arch=0.10, squash=0.70, wobble=0.040, belly=1.00,
         kids=((2.00, 0.80, -1),)),
    dict(name="left_near",  az=212.0, length=2.90, d0=0.22, d1=0.03, z0=0.25,
         arch=-0.01, squash=1.00, wobble=0.026, belly=1.00,
         kids=((1.50, 0.60, -1), (1.50, 0.60, +1))),
    dict(name="right_far",  az=26.0,  length=2.80, d0=0.24, d1=0.05, z0=0.28,
         arch=0.20, squash=0.75, wobble=0.030, belly=1.09, kids=()),
    dict(name="right_near", az=-36.0, length=2.30, d0=0.20, d1=0.04, z0=0.25,
         arch=0.00, squash=0.86, wobble=0.028, belly=1.00,
         kids=((1.00, 0.70, -1),)),
)

# 文档说细根共 8 条，逐根描述只数出 6 条 → 这 2 条从根盘裙边出，凑够 8（见 SPEC_CONFLICTS）
COLLAR_FINE_ROOTS = (
    dict(name="collar_a", az=118.0, length=0.62, d0=0.028, z0=0.10, squash=0.66, wobble=0.020),
    dict(name="collar_b", az=-142.0, length=0.48, d0=0.022, z0=0.11, squash=0.66, wobble=0.018),
)

# 8 个大枝干：从哪条主干、多高处起、方向、长度、起末直径、末端细枝数
BRANCHES = (
    # 参考图的大枝是"先横着甩出去、末端才翘头"的粗枝，占的横向幅度几乎是树高的一半；
    # 原来的方向偏竖直（z 分量 0.72–0.89）、长度也短，冠幅只有参考图的一半、读起来像扫帚。
    dict(name="L1", trunk="L", z=1.50, dir=(-0.80, 0.24, 0.46), length=2.40,
         d0=0.15, d1=0.06, kids=2, curl=0.42, bend=0.10),
    dict(name="L2", trunk="L", z=2.20, dir=(-0.72, 0.44, 0.44), length=2.50,
         d0=0.12, d1=0.05, kids=3, curl=0.38, bend=0.06),
    dict(name="L3", trunk="L", z=3.00, dir=(-0.60, -0.32, 0.62), length=1.50,
         d0=0.09, d1=0.04, kids=1, curl=0.46, bend=0.08),
    dict(name="L4", trunk="L", z=2.96, dir=(0.62, -0.50, 0.52), length=1.90,
         d0=0.08, d1=0.04, kids=2, curl=0.48, bend=0.05),
    dict(name="R1", trunk="R", z=2.00, dir=(0.82, -0.20, 0.44), length=2.40,
         d0=0.14, d1=0.05, kids=2, curl=0.38, bend=0.08),
    dict(name="R2", trunk="R", z=3.00, dir=(0.66, 0.36, 0.50), length=2.60,
         d0=0.11, d1=0.04, kids=2, curl=0.34, bend=0.22),
    dict(name="R3", trunk="R", z=4.20, dir=(0.52, -0.26, 0.72), length=1.70,
         d0=0.08, d1=0.03, kids=1, curl=0.40, bend=0.06),
    dict(name="R4", trunk="R", z=4.16, dir=(-0.40, 0.40, 0.76), length=1.90,
         d0=0.07, d1=0.03, kids=2, curl=0.36, bend=0.07),
)

# 细枝尺寸范围（文档：直径 0.015–0.05 m，长 0.3–0.9 m）
TWIG_DIA = (0.015, 0.050)
TWIG_LEN = (0.30, 0.90)

# 节疤：鼓包 Ø5–10 cm，顶部平/微凹
KNOTS = (
    dict(trunk="L", z=0.80, az=-15.0, dia=0.085),
    dict(trunk="R", z=1.50, az=20.0, dia=0.070),
    dict(trunk="R", z=2.80, az=-40.0, dia=0.060),
    dict(root="right_near", f=0.48, dia=0.060),
)

# 树皮剥落：左边那块巴掌大（约 20 × 15 cm）
PEELS = (
    dict(trunk="L", z0=1.10, z1=1.25, a0=-35.0, a1=35.0, lift=0.022),
    dict(trunk="R", z0=2.34, z1=2.50, a0=10.0, a1=42.0, lift=0.016),
    dict(trunk="R", z0=2.56, z1=2.68, a0=-28.0, a1=-6.0, lift=0.014),
)

# 树洞：左主干 1.80 m，Ø5 cm、深 10 cm、朝右前方
HOLLOW = dict(trunk="L", z=1.80, az=-40.0, hole_d=0.050, depth=0.100)

OBJ_BARK = PREFIX + "bark"
OBJ_CORE = PREFIX + "core"
OBJ_HOLLOW = PREFIX + "hollow"


# ---------------------------------------------------------------- 路径工具
def _catmull(ctrl, steps=3):
    """控制点 → 平滑路径（Catmull-Rom）。树干不是折线，直接放样会出棱。"""
    pts = [Vector(ctrl[0])] + [Vector(c) for c in ctrl] + [Vector(ctrl[-1])]
    out = []
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        for s in range(steps):
            t = s / steps
            out.append(0.5 * (
                2.0 * p1
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t
            ))
    out.append(Vector(ctrl[-1]))
    return out


def _dia_at(z, z_fork, z_top, dia_pair):
    """直径按高度插值：指数 <1 让干基粗得更久，接近参考图的圆柱感。"""
    d0, d1 = dia_pair
    t = 0.0 if z <= z_fork else (1.0 if z >= z_top else (z - z_fork) / (z_top - z_fork))
    return d0 + (d1 - d0) * (t ** TRUNK_TAPER_POW)


def _norm_flutes(flute):
    """把 flute 归一成元组列表：单组 (沟数, 深度, 锐度[, 相位]) 或多组并列。

    多组沟是叠乘的（同一半径上先挖主裂、再在主裂旁挖一条更细的次裂），
    相位错开才读得出"一条深缝旁边跟着一条浅缝"的树皮质感。
    """
    if not flute:
        return ()
    if isinstance(flute[0], (int, float)):
        flute = (flute,)
    out = []
    for spec in flute:
        count, depth, sharp = spec[0], spec[1], spec[2]
        phase = spec[3] if len(spec) > 3 else 0.9
        if count:
            out.append((count, depth, sharp, phase))
    return tuple(out)


def _tube(bm, points, radii, sides, twist=0.0, ripple=0.0, ripple_n=2,
          squash=None, cap_start=True, tip=True, tip_scale=1.5,
          flute=None, slant=0.0, dent=None):
    """放样一条枝干，比 v1 的 add_tube 多一项"窄纵沟"（flute）。

    纵沟不是 sin 波：sin 的脊谷等宽，读成"波纹"；参考图里干皮是"宽脊 + 窄深沟"，
    所以用 r *= 1 - depth * (1 - crest)**sharp，crest = (1 + cos(n*a))/2。
    sharp 取 3–4 时只有 crest 接近 0（沟底）那一小段内凹、脊面几乎全宽 —— 这才是
    文档里"深 2–3 cm、宽 0.1–1 cm"的纵向裂纹。沟在截面局部角度里调制、跟着 twist
    一起转，所以是螺旋沟；fade 让沟越往顶越浅（文档"越往顶部越浅越疏"）。
    flute 可以给一组，也可以给多组（见 _norm_flutes），多组在同一半径上叠乘。
    """
    n = len(points)
    tangents, normals, binormals = _frames(points)
    flutes = _norm_flutes(flute)
    rings = []
    for i in range(n):
        p = points[i]
        tw = twist * (i / (n - 1)) if n > 1 else 0.0
        ct, st = math.cos(tw), math.sin(tw)
        u = normals[i] * ct + binormals[i] * st
        v = binormals[i] * ct - normals[i] * st
        su, sv = squash[i] if squash else (1.0, 1.0)
        cut = slant * radii[i] if (slant and i == n - 1) else 0.0
        fade = 1.0 - 0.55 * (i / (n - 1)) if n > 1 else 1.0
        ring = []
        for j in range(sides):
            a = 2.0 * math.pi * j / sides
            r = radii[i]
            if ripple:
                r *= 1.0 + ripple * math.sin(ripple_n * a + 0.7)
            for fn, fdepth, fsharp, fphase in flutes:
                crest = 0.5 + 0.5 * math.cos(fn * a + fphase)
                r *= 1.0 - fdepth * fade * (1.0 - crest) ** fsharp
            if dent:
                r *= dent(a + tw, i, n)      # 世界方位角（截面已转了 twist）
            pt = p + u * (math.cos(a) * r * su) + v * (math.sin(a) * r * sv)
            if cut:
                pt = pt + tangents[i] * (cut * math.cos(a))
            ring.append(bm.verts.new(pt))
        rings.append(ring)

    # UV：u = 周向一圈（0→1），v = 沿轴弧长（米）。树皮条纹靠它顺着枝干轴向走，
    # 否则用 Object 坐标时，横躺的粗根上条纹会变成一圈圈"斑马环"。
    uv = bm.loops.layers.uv.verify()
    inv = 1.0 / sides
    vvals = [0.0] * n
    for i in range(1, n):
        vvals[i] = vvals[i - 1] + (points[i] - points[i - 1]).length

    def _uvset(face, uvs):
        for lp, co in zip(face.loops, uvs):
            lp[uv].uv = co

    for i in range(n - 1):
        for j in range(sides):
            k = (j + 1) % sides
            fo = bm.faces.new((rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]))
            _uvset(fo, ((j * inv, vvals[i]), ((j + 1) * inv, vvals[i]),
                        ((j + 1) * inv, vvals[i + 1]), (j * inv, vvals[i + 1])))

    if cap_start:
        fo = bm.faces.new(tuple(reversed(rings[0])))
        _uvset(fo, [((j * inv), 0.0) for j in range(sides)])
    if tip:
        apex = bm.verts.new(points[-1] + tangents[-1] * (radii[-1] * tip_scale))
        for j in range(sides):
            k = (j + 1) % sides
            fo = bm.faces.new((rings[-1][j], rings[-1][k], apex))
            _uvset(fo, ((j * inv, vvals[-1]), ((j + 1) * inv, vvals[-1]),
                        ((j + 0.5) * inv, vvals[-1] + 0.1)))
    else:
        fo = bm.faces.new(tuple(rings[-1]))
        _uvset(fo, [((j * inv), vvals[-1]) for j in range(sides)])


# ---------------------------------------------------------------- 根盘
def _collar_r(z):
    """两板根之间的半径（按轮廓表插值）。"""
    table = COLLAR_PROFILE
    if z <= table[0][0]:
        return table[0][1] * 0.5 * DIA_GAIN
    if z >= table[-1][0]:
        return table[-1][1] * 0.5 * DIA_GAIN
    for i in range(len(table) - 1):
        z0, d0 = table[i]
        z1, d1 = table[i + 1]
        if z0 <= z <= z1:
            fz = 0.0 if z1 - z0 < 1e-9 else (z - z0) / (z1 - z0)
            return (d0 + (d1 - d0) * fz) * 0.5 * DIA_GAIN
    return table[-1][1] * 0.5 * DIA_GAIN


def _wrap_pi(x):
    while x > math.pi:
        x -= 2.0 * math.pi
    while x < -math.pi:
        x += 2.0 * math.pi
    return x


def _collar_radius(z, a):
    """方位相关半径：谷底 + 6 条板根脊（脊是平台不是尖峰，脊之间挖深 V 沟）。

    参考图的根盘是"一圈放射状厚板"，板与板之间能看到很深的暗缝；用 cos^n
    尖峰或整体放宽都会读成光滑圆台，所以这里用"谷半径 → 脊半径"的插值，
    板宽 COLLAR_PLATE_W，脊只在 COLLAR_FLARE_Z 以下张开。
    """
    base = _collar_r(z)
    h = max(0.0, 1.0 - z / COLLAR_FLARE_Z) ** 2.2
    ridge = base + (COLLAR_RIDGE_MAX * DIA_GAIN - base) * h
    plate = 0.0
    for spec in ROOTS:
        d = abs(_wrap_pi(a - math.radians(spec["az"])))
        w = max(0.0, 1.0 - (d / COLLAR_PLATE_W) ** 2)
        plate = max(plate, w * w * (3.0 - 2.0 * w))   # smoothstep：板顶不留硬折痕
    r = base + (ridge - base) * plate
    r *= 1.0 + COLLAR_RIPPLE * math.sin(COLLAR_RIPPLE_N * a + 1.2 + z * 2.4)
    return r


def _build_collar(bm):
    """根盘：不是一个圆台，而是"中心墩 + 6 条板根隆起"的车削体。

    参考图里根和干是同一个连续体，圆台 + 六根细腿会读成"章鱼"。
    """
    sides = SIDES_COLLAR
    zs = [p[0] for p in COLLAR_PROFILE]
    rings = []
    for z in zs:
        ring = []
        for j in range(sides):
            a = 2.0 * math.pi * j / sides
            r = _collar_radius(z, a)
            ring.append(bm.verts.new(Vector((math.cos(a) * r, math.sin(a) * r, z))))
        rings.append(ring)
    uv = bm.loops.layers.uv.verify()
    inv = 1.0 / sides
    for i in range(len(rings) - 1):
        for j in range(sides):
            k = (j + 1) % sides
            fo = bm.faces.new((rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]))
            for lp, co in zip(fo.loops, ((j * inv, zs[i]), ((j + 1) * inv, zs[i]),
                                         ((j + 1) * inv, zs[i + 1]), (j * inv, zs[i + 1]))):
                lp[uv].uv = co
    fo = bm.faces.new(tuple(reversed(rings[0])))    # 底面封口（坐在裂土上）
    for lp, j in zip(fo.loops, range(sides)):
        lp[uv].uv = (j * inv, zs[0])
    fo = bm.faces.new(tuple(rings[-1]))             # 顶面封口（被双主干盖住）
    for lp, j in zip(fo.loops, range(sides)):
        lp[uv].uv = (j * inv, zs[-1])
    return [
        Vector((0.0, 0.0, z)) for z in zs
    ], [_collar_r(z) for z in zs]


# ---------------------------------------------------------------- 双主干
def _build_trunk(bm, key):
    spec = TRUNKS[key]
    ctrl = spec["ctrl"]
    z_fork = ctrl[1][2]
    z_top = ctrl[-1][2]
    path = _catmull(ctrl, steps=4)
    # 按高度重采样成等 z 的环，环数随高度增长（4.2 m 的右主干要更多环才不方）
    n = max(8, int(round((z_top - ctrl[0][2]) / 0.150)) + 1)
    pts, radii = [], []
    knot_zs = [k for k in KNOTS if k.get("trunk") == key]
    peel_zs = [p for p in PEELS if p["trunk"] == key]

    def _dent(a, i, nn):
        """剥落处把干面往里压一块：宽脊 + 平滑边缘，露出的木质板才"陷"在伤口里。"""
        z = ctrl[0][2] + (z_top - ctrl[0][2]) * (i / (nn - 1))
        s = 1.0
        for pp in peel_zs:
            if not (pp["z0"] <= z <= pp["z1"]):
                continue
            mid = (pp["a0"] + pp["a1"]) * 0.5
            span = max(1.0, abs(pp["a1"] - pp["a0"]) * 0.5)
            d = abs((math.degrees(a) - mid + 180.0) % 360.0 - 180.0)
            if d > span:
                continue
            half = max(1e-6, (pp["z1"] - pp["z0"]) * 0.5)
            fz = min(1.0, min(z - pp["z0"], pp["z1"] - z) / half)
            u = d / span
            s *= 1.0 - 0.15 * (1.0 - u * u) * fz
        return s
    for i in range(n):
        t = i / (n - 1)
        z = ctrl[0][2] + (z_top - ctrl[0][2]) * t
        # 在该 z 上取路径点：路径沿 z 单调，直接找最近的两点插值
        p = _path_at_z(path, z)
        # 中轴细碎摆动：参考图的干不是一根光滑锥，边缘一直在小幅进出
        wig = 0.012 * math.sin(z * 9.1 + 0.7) + 0.008 * math.sin(z * 21.0 + 2.1)
        p = p + Vector((wig, wig * 0.7, 0.0))
        r = _dia_at(z, z_fork, z_top, spec["dia"]) * 0.5 * DIA_GAIN
        # 节疤：半径局部膨胀（配合 _build_knot 的凸包，鼓包才有体量）
        for k in knot_zs:
            g = math.exp(-(((z - k["z"]) / 0.11) ** 2))
            r *= 1.0 + 0.16 * g
            p = p + Vector((0.0, 0.0, 0.0)) + Vector((0.010 * g, 0.0, 0.0))
        # 轮廓不规则：干不是光滑锥，半径随高度小幅进出（参考图的边一直在抖）
        r *= 1.0 + 0.040 * math.sin(z * 13.7 + 1.1) + 0.022 * math.sin(z * 29.3 + 0.4)
        # 双干缠绕：0.5–1.2 m 两根互相绕一圈再各张成 V（参考图里分叉上方还是交叉的）
        braid = BRAID_R * max(0.0, 1.0 - max(0.0, z - FORK_Z) / 1.20)
        if braid:
            ph = 0.0 if key == "L" else math.pi
            p = p + Vector((braid * math.cos(z * 1.7 + ph),
                            braid * math.sin(z * 1.7 + ph), 0.0))
        pts.append(p)
        radii.append(r)
    _tube(bm, pts, radii, SIDES_TRUNK, twist=spec["twist"],
          ripple=spec["ripple"], ripple_n=TRUNK_RIPPLE_N,
          flute=FLUTE_TRUNK, dent=_dent, cap_start=True, tip=False)
    return {"key": key, "pts": pts, "radii": radii, "z_fork": z_fork, "z_top": z_top,
            "dia": spec["dia"]}


def _path_at_z(path, z):
    """沿 z 找路径点（路径是 z 单调的，线性插值足够）。"""
    if z <= path[0].z:
        return path[0].copy()
    if z >= path[-1].z:
        return path[-1].copy()
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        if a.z <= z <= b.z:
            f = 0.0 if abs(b.z - a.z) < 1e-9 else (z - a.z) / (b.z - a.z)
            return a.lerp(b, f)
    return path[-1].copy()


def _trunk_at(trunk, z):
    """返回 (轴心点, 半径, 切线)。"""
    pts, radii = trunk["pts"], trunk["radii"]
    if z <= pts[0].z:
        i, f = 0, 0.0
    elif z >= pts[-1].z:
        i, f = len(pts) - 2, 1.0
    else:
        i = 0
        for k in range(len(pts) - 1):
            if pts[k].z <= z <= pts[k + 1].z:
                i = k
                span = pts[k + 1].z - pts[k].z
                f = 0.0 if span < 1e-9 else (z - pts[k].z) / span
                break
    p = pts[i].lerp(pts[i + 1], f)
    r = radii[i] + (radii[i + 1] - radii[i]) * f
    tan = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
    return p, r, tan


# ---------------------------------------------------------------- 根
def _rlen(spec):
    """主根实际长度 = 文档长度 × ROOT_LEN_SCALE（1.0 即照文档）。"""
    return spec["length"] * ROOT_LEN_SCALE


def _root_point(spec, f):
    """主根参数 f∈[0,1] 上的轴心点（不依赖 rng，便于分叉与细节定位）。

    起始高度按 (1-f)^1.6 快速落地，arch 是"小桥"拱起量（右远根 0.20 → 拱顶
    轴心 z≈0.25，扣掉压扁后的竖半径，底面离地约 0.15 m）。
    """
    az = math.radians(spec["az"])
    d = Vector((math.cos(az), math.sin(az), 0.0))
    side = Vector((-d.y, d.x, 0.0))
    z = spec["z0"] * (1.0 - f) ** 1.6 + 0.020 * f + spec["arch"] * math.sin(math.pi * f) ** 1.1
    # 贴地起伏：根不是笔直躺在沙地上，会轻微起伏、偶尔扎进裂土
    z += 0.012 * math.sin(f * 6.4 + spec["az"] * 0.03) + 0.006
    # 外端逐渐沉进裂土：参考图里根是一头扎进地里的，不是悬空的尖刺
    z -= 0.200 * f ** 2.0
    wob = (math.sin(f * 3.4 + spec["az"] * 0.017) * spec["wobble"]
           + math.sin(f * 7.1 + 1.3) * spec["wobble"] * 0.45)
    return d * (_rlen(spec) * f) + side * wob + Vector((0.0, 0.0, z))


def _root_frame(spec):
    az = math.radians(spec["az"])
    d = Vector((math.cos(az), math.sin(az), 0.0))
    return d, Vector((-d.y, d.x, 0.0))


def _root_section(spec, f):
    """主根在参数 f 处的 (水平半径, 横向缩放, 竖向缩放)。

    根是竖向立起来的板，不是圆管：根部 sv 往上拉（板根），0.35 之后才压成
    文档要求的"上下压扁 30%"扁带贴地；su 用来补偿"周长守恒"，避免压扁后变胖。
    """
    # 直径按"文档长度"归一化，不按当前长度：缩短根长（ROOT_LEN_SCALE）时
    # 只砍掉外段、不压缩整根的粗细曲线，于是末端是钝头不是针尖 ——
    # 这正是参考图里"短粗钝头根爪"的样子（见 README 已知差距第 1 条）。
    fd = min(1.0, f * ROOT_LEN_SCALE)
    r = (spec["d0"] + (spec["d1"] - spec["d0"]) * (fd ** ROOT_TAPER_POW)) * 0.5
    r *= 1.0 + (spec["belly"] - 1.0) * math.sin(math.pi * fd)
    sv = spec["squash"] + (1.18 - spec["squash"]) * max(0.0, 1.0 - f / 0.35) ** 2
    su = 1.0 / math.sqrt(max(sv, 0.35))
    # 根部横向再放宽：参考图的根是扁平板带，不是圆管；只在最前 0.5 m 内加宽
    su *= 1.0 + 0.55 * max(0.0, 1.0 - f / 0.20) ** 1.8
    return r, su, sv


def _build_root(bm, spec, rng):
    n = max(6, int(round(_rlen(spec) / 0.36)) + 2)
    pts, radii, squash = [], [], []
    for i in range(n):
        f = i / (n - 1)
        pts.append(_root_point(spec, f))
        r, su, sv = _root_section(spec, f)
        radii.append(r)
        squash.append((su, sv))
    _tube(bm, pts, radii, SIDES_ROOT, twist=rng.uniform(0.8, 1.4),
          ripple=0.075, ripple_n=2, squash=squash,
          flute=FLUTE_ROOT, cap_start=True, tip=True, tip_scale=0.55)
    return pts, radii


def _buttress_fin(bm, spec, samples=5, reach=0.62):
    """板根鳍：沿根的方位插一块竖直三角薄板，把根盘和主根连成一圈隆起裙。

    参考图里根系不是"台座 + 辐条腿"，而是树干向四面八方张开的连续板根；
    单靠加粗根管做不到（根是按文档长 2.2–3.5 m 的细带），所以用一块从干上
    0.6 m 处沿根顶面收到地面的薄板补上这段过渡，厚度 0.045→0.012 m 收尖。
    """
    d, side = _root_frame(spec)
    us = [max(0.04, reach * (i / (samples - 1)) ** 0.85) for i in range(samples)]
    top, bot, thick = [], [], []
    for u in us:
        f = min(0.98, u / _rlen(spec))
        p = _root_point(spec, f)
        lat = side.dot(p)                      # 根的侧向摆幅，鳍跟着一起偏
        r, _su, sv = _root_section(spec, f)
        z_lo = p.z + r * sv * 0.85             # 贴在根的上表面
        # 顶边压在根盘（COLLAR_FLARE_Z=0.46）之内，超出就会在根盘上方露出一片竖刀
        h = (0.45 - z_lo) * max(0.0, 1.0 - u / reach) ** 2.2
        top.append(d * u + side * lat + Vector((0.0, 0.0, z_lo + h + 0.004)))
        bot.append(d * u + side * lat + Vector((0.0, 0.0, z_lo - 0.010)))
        thick.append(0.050 + (0.014 - 0.050) * (u / reach))
    # 两块侧壁 + 顶/底边条 + 两端封口 = 闭合薄壳，避免露出边界边
    left, right = [], []
    for a, b, t in zip(top, bot, thick):
        left.append((bm.verts.new(a - side * (t * 0.5)), bm.verts.new(b - side * (t * 0.5))))
        right.append((bm.verts.new(a + side * (t * 0.5)), bm.verts.new(b + side * (t * 0.5))))
    for i in range(samples - 1):
        j = i + 1
        quads = (
            (left[i][0], left[i][1], left[j][1], left[j][0]),        # 左壁
            (right[i][1], right[i][0], right[j][0], right[j][1]),    # 右壁
            (left[i][0], right[i][0], right[j][0], left[j][0]),      # 顶边
            (left[j][1], right[j][1], right[i][1], left[i][1]),      # 底边
        )
        for q in quads:
            bm.faces.new(q)
    bm.faces.new((left[0][0], left[0][1], right[0][1], right[0][0]))
    bm.faces.new((right[-1][0], right[-1][1], left[-1][1], left[-1][0]))


def _build_subroot(bm, spec, at, length, sign, rng):
    """细根：从主根指定距离处分叉、更细更弯、贴地。"""
    f = min(0.95, at / _rlen(spec))
    d, side = _root_frame(spec)
    base = _root_point(spec, f)
    ang = math.radians(rng.uniform(28.0, 46.0)) * (1 if sign > 0 else -1)
    dirv = (d * math.cos(ang) + side * math.sin(ang)).normalized()
    dirv = (dirv + Vector((0.0, 0.0, -0.35))).normalized()   # 往地面扎
    dia = rng.uniform(0.015, 0.040)
    start = base - dirv * 0.04
    _limb(bm, start, dirv, length, dia, dia * 0.30, SIDES_SUBROOT, rng,
          curl=0.02, wobble=0.055, ripple=0.10, kink=0.40, tip=True)


def _build_collar_fine_root(bm, spec, rng):
    az = math.radians(spec["az"])
    d = Vector((math.cos(az), math.sin(az), 0.0))
    start = d * 0.30 + Vector((0.0, 0.0, spec["z0"]))
    dia = spec["d0"]
    _limb(bm, start, (d + Vector((0.0, 0.0, -0.30))).normalized(),
          spec["length"], dia, dia * 0.35, SIDES_SUBROOT, rng,
          curl=0.01, wobble=0.050, ripple=0.10, kink=0.40, tip=True)


# ---------------------------------------------------------------- 枝干
def _limb(bm, start, direction, length, dia0, dia1, sides, rng,
          curl=0.30, bend=0.0, n_rings=None, ripple=0.10, twist=None,
          wobble=0.035, kink=0.0, tip=True, flute=None):
    """一条枝干的通用放样：外扬 → 逐渐翘头（curl）+ 侧向 S 弯（bend）+ 折点（kink）。

    kink 是参考图的关键：枯枝不是平滑抛物线，每隔一两段就有一次明显的折向。
    """
    n = n_rings if n_rings else max(5, int(round(length / 0.21)) + 2)
    d0 = direction.normalized()
    u, v = _perp(d0)
    phase = rng.uniform(0.0, math.tau)
    pts, cur = [start.copy()], start.copy()
    step = length / (n - 1)
    for i in range(1, n):
        f = i / (n - 1)
        d = d0 * (1.0 - curl * f) + UP * (curl * f * 1.15)
        d += u * (math.sin(f * 5.2 + phase) * wobble)
        d += u * (math.sin(f * math.tau) * bend)
        if kink and i % 2 == 0:
            kd = u * rng.uniform(-1.0, 1.0) + v * rng.uniform(-1.0, 1.0) + UP * 0.25
            d += kd.normalized() * kink
        cur = cur + d.normalized() * step
        pts.append(cur.copy())
    radii = [(dia0 + (dia1 - dia0) * ((i / (n - 1)) ** 0.85)) * 0.5 * DIA_GAIN
             for i in range(n)]
    tw = twist if twist is not None else rng.uniform(0.5, 1.5)
    _tube(bm, pts, radii, sides, twist=tw, ripple=ripple, flute=flute,
          cap_start=True, tip=tip, tip_scale=1.4)
    return pts, radii


def _branch_start(trunk, z, direction):
    """枝干起点从主干截面内部出发（-0.85 r），分叉处不会露出"套环"。"""
    p, r, _tan = _trunk_at(trunk, z)
    return p - direction.normalized() * (r * 0.85), p, r


def _build_branch(bm, spec, trunks, rng):
    trunk = trunks[spec["trunk"]]
    start, surface, r = _branch_start(trunk, spec["z"], Vector(spec["dir"]))
    pts, radii = _limb(bm, start, Vector(spec["dir"]), spec["length"],
                       spec["d0"], spec["d1"], SIDES_BRANCH, rng,
                       curl=spec["curl"], bend=spec["bend"],
                       ripple=0.095, wobble=0.050, kink=0.34,
                       flute=FLUTE_BRANCH)
    # 末端的细枝：文档"端分 N 细枝"
    n = len(pts)
    for k in range(spec["kids"]):
        f = 0.58 + 0.34 * (k / max(1, spec["kids"] - 1)) if spec["kids"] > 1 else 0.86
        idx = min(n - 2, max(1, int(round(f * (n - 1)))))
        anchor = pts[idx]
        tan = (pts[min(idx + 1, n - 1)] - pts[max(idx - 1, 0)]).normalized()
        u, v = _perp(tan)
        az = rng.uniform(0.0, math.tau)
        spread = math.radians(rng.uniform(24.0, 50.0))
        kd = (tan * math.cos(spread)
              + (u * math.cos(az) + v * math.sin(az)) * math.sin(spread))
        kd = (kd + UP * 0.30).normalized()      # 细枝都往上翘，树冠才"抓天"
        dia = rng.uniform(*TWIG_DIA)
        ln = rng.uniform(*TWIG_LEN)
        _limb(bm, anchor - kd * (radii[idx] * 0.6), kd, ln,
              dia, dia * 0.18, SIDES_TWIG, rng,
              curl=rng.uniform(0.20, 0.50), wobble=0.075, ripple=0.085,
              kink=0.45)
    # 大枝沿途的小侧枝：参考图的大枝不是"光杆到顶再分叉"，沿途都带短枝，
    # 树冠才有厚度（文档只写端分细枝，见 SPEC_CONFLICTS 第 3 条）
    for s in range(SPUR_PER_BRANCH):
        fs = 0.42 if SPUR_PER_BRANCH == 1 else 0.34 + 0.26 * (s / (SPUR_PER_BRANCH - 1))
        idx = min(n - 2, max(1, int(round(fs * (n - 1)))))
        anchor = pts[idx]
        tan = (pts[min(idx + 1, n - 1)] - pts[max(idx - 1, 0)]).normalized()
        u, v = _perp(tan)
        az = rng.uniform(0.0, math.tau)
        spread = math.radians(rng.uniform(45.0, 70.0))
        sd = (tan * math.cos(spread)
              + (u * math.cos(az) + v * math.sin(az)) * math.sin(spread))
        sd = (sd + UP * 0.35).normalized()
        dia = rng.uniform(*SPUR_DIA)
        _limb(bm, anchor - sd * (radii[idx] * 0.5), sd, rng.uniform(*SPUR_LEN),
              dia, dia * 0.25, SIDES_TWIG, rng,
              curl=rng.uniform(0.25, 0.55), wobble=0.090, ripple=0.080,
              kink=0.50, flute=FLUTE_BRANCH)
    return pts, radii


# ---------------------------------------------------------------- 细节：节疤 / 剥落 / 树洞
def _build_knot(bm, spec, trunks, root_pts):
    if "root" in spec:
        spec_root = next(r for r in ROOTS if r["name"] == spec["root"])
        p = _root_point(spec_root, spec["f"])
        d, _side = _root_frame(spec_root)
        radial = (Vector((0.0, 0.0, 1.0)) - d * 0.0).normalized()   # 根上的鼓包朝上
        base = p + radial * 0.05
        out = radial
    else:
        trunk = trunks[spec["trunk"]]
        p, r, _tan = _trunk_at(trunk, spec["z"])
        a = math.radians(spec["az"])
        out = Vector((math.cos(a), math.sin(a), 0.0))
        base = p + out * (r * 0.88)
    dia = spec["dia"]
    pts = [base, base + out * (dia * 0.20), base + out * (dia * 0.36)]
    radii = [dia * 0.5 * 0.80, dia * 0.5, dia * 0.40]
    _tube(bm, pts, radii, SIDES_DETAIL, twist=0.0, ripple=0.06, ripple_n=3,
          cap_start=True, tip=False)     # tip=False → 平顶（文档"顶部平或微凹"）


def _build_peel(bm, spec, trunks):
    """剥落处的木质面：陷在 _dent 挖出的凹坑里（半径比树皮小 10%），
    边缘抖 1 cm 打破"贴纸"方边，底面贴死、四周留侧壁。"""
    trunk = trunks[spec["trunk"]]
    nu, nz = 5, 4
    lift, thick = spec["lift"], 0.012
    outer, inner = [], []
    for iz in range(nz):
        fz = iz / (nz - 1)
        z = spec["z0"] + (spec["z1"] - spec["z0"]) * fz
        p, r, _tan = _trunk_at(trunk, z)
        row_o, row_i = [], []
        for ia in range(nu):
            fa = ia / (nu - 1)
            a = math.radians(spec["a0"] + (spec["a1"] - spec["a0"]) * fa)
            radial = Vector((math.cos(a), math.sin(a), 0.0))
            # 木质面比树皮半径小 10%：陷进 _dent 的凹坑，不再是一块浮在表面上的亮片
            jit = (0.009 * math.sin(fa * 9.1 + fz * 5.7 + a)
                   + 0.005 * math.sin(fa * 21.0 + fz * 3.1))
            bulge = math.sin(math.pi * fa) * lift * 0.45   # 中间微微鼓起，有木质的弧形
            surface = r * 0.90 + jit + bulge
            row_o.append(p + radial * surface)
            row_i.append(p + radial * (surface - thick))
        outer.append(row_o)
        inner.append(row_i)

    def quad(a, b, c, d):
        bm.faces.new((a, b, c, d))

    vo = [[bm.verts.new(v) for v in row] for row in outer]
    vi = [[bm.verts.new(v) for v in row] for row in inner]
    for iz in range(nz - 1):
        for ia in range(nu - 1):
            quad(vo[iz][ia], vo[iz][ia + 1], vo[iz + 1][ia + 1], vo[iz + 1][ia])
            quad(vi[iz][ia], vi[iz + 1][ia], vi[iz + 1][ia + 1], vi[iz][ia + 1])
    for ia in range(nu - 1):     # 上沿、下沿
        quad(vo[0][ia], vi[0][ia], vi[0][ia + 1], vo[0][ia + 1])
        quad(vo[nz - 1][ia + 1], vi[nz - 1][ia + 1], vi[nz - 1][ia], vo[nz - 1][ia])
    for iz in range(nz - 1):     # 两侧
        quad(vo[iz][0], vo[iz + 1][0], vi[iz + 1][0], vi[iz][0])
        quad(vi[iz][nu - 1], vi[iz + 1][nu - 1], vo[iz + 1][nu - 1], vo[iz][nu - 1])


def _build_hollow(bm, spec, trunks):
    trunk = trunks[spec["trunk"]]
    p, r, _tan = _trunk_at(trunk, spec["z"])
    a = math.radians(spec["az"])
    radial = Vector((math.cos(a), math.sin(a), 0.0))
    inward = -radial
    r0 = spec["hole_d"] * 0.5
    d = spec["depth"]
    pts = [p + radial * (r * 1.02),
           p + radial * (r * 0.85) + inward * 0.0,
           p + radial * (r * 0.85) + inward * (d * 0.45),
           p + radial * (r * 0.85) + inward * d]
    radii = [r0 * 1.05, r0, r0 * 0.72, r0 * 0.42]
    _tube(bm, pts, radii, SIDES_DETAIL, twist=0.0, ripple=0.0,
          cap_start=True, tip=False)


# ---------------------------------------------------------------- 材质（剥落木质）
def _make_core_material():
    """剥落后露出的木质：浅棕偏黄，比树皮亮一档，用来区分"伤口"。

    独立材质是有意的：glTF 只认 baseColorFactor，程序化节点一律丢失，
    要让"剥落处更亮"活到 GLB 里，只能靠一张 FLAT 表 + 一个单独材质。
    """
    mat = bpy.data.materials.get(MAT_CORE)
    if mat is None:
        mat = bpy.data.materials.new(MAT_CORE)
    if not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    bsdf.inputs["Base Color"].default_value = (0.185, 0.138, 0.086, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.94
    # 木纹：沿 Z 拉长的一层波带 → bump（不接 Base Color，导出不受影响）
    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-600, -200)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = (-380, -200)
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 22.0
    wave.inputs["Distortion"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-120, -260)
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Factor"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (0.185, 0.138, 0.086, 1.0)
    return mat


# ---------------------------------------------------------------- 场景装配
def _finish_object(name, bm, coll, mat):
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


def _tris(objs):
    return sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in objs)


def _local_bbox(objs):
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for ob in objs:
        for v in ob.data.vertices:
            for i in range(3):
                lo[i] = min(lo[i], v.co[i])
                hi[i] = max(hi[i], v.co[i])
    return lo, hi


def build():
    """幂等构建：删掉 wst_tree_ 前缀 → 按规格重建 → 返回 receipt。"""
    removed = _purge_own()
    coll = _ensure_collections()
    mat_bark = _make_material()
    mat_core = _make_core_material()
    mat_dark = bpy.data.materials.get(MAT_DARK) or bpy.data.materials.new(MAT_DARK)

    rng = random.Random(SEED)
    bm_bark = bmesh.new()
    bm_core = bmesh.new()
    bm_dark = bmesh.new()

    _build_collar(bm_bark)
    trunks = {k: _build_trunk(bm_bark, k) for k in ("L", "R")}

    root_pts = {}
    for spec in ROOTS:
        if BUTTRESS_FIN:
            _buttress_fin(bm_bark, spec)
        root_pts[spec["name"]] = _build_root(bm_bark, spec, rng)
        for at, ln, sign in spec["kids"]:
            _build_subroot(bm_bark, spec, at, ln, sign, rng)
    for spec in COLLAR_FINE_ROOTS:
        _build_collar_fine_root(bm_bark, spec, rng)

    branch_info = []
    for spec in BRANCHES:
        pts, radii = _build_branch(bm_bark, spec, trunks, rng)
        branch_info.append((spec["name"], pts[-1], spec["kids"]))

    for spec in KNOTS:
        _build_knot(bm_bark, spec, trunks, root_pts)
    for spec in PEELS:
        _build_peel(bm_core, spec, trunks)
    _build_hollow(bm_dark, HOLLOW, trunks)

    objs = [
        _finish_object(OBJ_BARK, bm_bark, coll, mat_bark),
        _finish_object(OBJ_CORE, bm_core, coll, mat_core),
        _finish_object(OBJ_HOLLOW, bm_dark, coll, mat_dark),
    ]
    bpy.context.view_layer.update()

    lo, hi = _local_bbox(objs)
    sub_roots = sum(len(r["kids"]) for r in ROOTS) + len(COLLAR_FINE_ROOTS)
    twigs = sum(b["kids"] for b in BRANCHES)
    spurs = SPUR_PER_BRANCH * len(BRANCHES)
    receipt = {
        "created": [ob.name for ob in objs],
        "removed": removed,
        "tris": _tris(objs),
        "per_object_tris": {ob.name: sum(len(p.vertices) - 2 for p in ob.data.polygons)
                            for ob in objs},
        "verts": sum(len(ob.data.vertices) for ob in objs),
        "bbox_local": {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi],
                       "size": [round(hi[i] - lo[i], 4) for i in range(3)]},
        "height": round(hi[2] - lo[2], 3),
        "collar_dia": COLLAR_DIA,
        "fork_z": FORK_Z,
        "trunks": {k: {"top": TRUNKS[k]["ctrl"][-1][2], "dia": TRUNKS[k]["dia"]}
                   for k in TRUNKS},
        "main_roots": len(ROOTS),
        "sub_roots": sub_roots,
        "branches": len(BRANCHES),
        "twigs": twigs,
        "spurs": spurs,
        "knots": len(KNOTS),
        "peels": len(PEELS),
        "hollow": 1,
        "materials": sorted({m.name for ob in objs for m in ob.data.materials if m}),
        "collection": coll.name,
        "location": list(BASE),
        "rot_z_deg": ROT_Z_DEG,
        "seed": SEED,
        "branch_tips": [[n, [round(c, 3) for c in p]] for n, p, _k in branch_info],
    }
    return receipt


if __name__ == "__main__":
    print("HEADLESS " + json.dumps(build(), ensure_ascii=False))
