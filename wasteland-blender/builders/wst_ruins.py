# -*- coding: utf-8 -*-
"""两层混凝土废墟残楼 —— SPEC v1 §3.2

前缀 wst_build_ / collection_ruins。不碰其它 collection / 相机 / 灯光 / 世界 / 渲染设置。
幂等：先按前缀清掉自己的对象与孤立数据块，再重建。确定性：固定种子，无随机系统源。
headless 友好：只用 bpy.data / bmesh，不依赖 screen 的 bpy.ops。

几何分层（每面墙都是"两层皮 + 楼板带"）：
  前皮 0..0.14 —— 开窗 = 0.14 深的内凹口袋（四个洞壁由格子边界自动生成），
  后皮 0.15..0.40 —— 只在"穿透洞"上开孔，于是窗口内是深色室内面，不是镂空看穿；
  楼板带 z∈[3.10,3.45] —— 两皮在这段各自外凸 0.09 m，形成连续的 0.58 m 厚水平箍。
"""

import bpy
import bmesh
import json
import math
import random
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree

# ---------------------------------------------------------------- 合同常量

PREFIX = "wst_build_"
COLLECTION = "collection_ruins"
ROOT_COLLECTION = "collection_wasteland"

LOC = Vector((-8.5, 12.5, 0.0))           # Lead 指定（退到 27.5 m，楼顶落在画面 y≈0.17）
ROT_Z = math.radians(14.0)                # SPEC §3.2 朝向

SEED = 20240521

# 建筑局部坐标：X 向右（+X），Y 向后（-Y 是正面/开窗面），Z 向上；原点在楼底中心
WALL_T = 0.40                             # 墙厚
FRONT_SKIN = 0.14                         # 前皮厚度 = 窗洞内凹深度（合同要求 0.12，取 0.14 好读）
REAR_Y0 = 0.12                            # 后皮前表面：压进前皮 2 cm（互锁 → 一面墙是一个连通体，
                                          #   且两面错开 2 cm，不会出现共面闪烁）
REAR_T = 0.25                             # 后皮厚度
BAND_Z0, BAND_Z1 = 3.10, 3.45             # 楼板带（厚 0.35）
BAND_OUT = 0.09                           # 楼板带每侧外凸量
BURY = 0.35                               # 墙脚埋入地下的深度（地形起伏 ±0.15，防悬空）
LEFT_X0, LEFT_X1 = -6.00, -1.10           # 左段完整两层残墙（含可见左端墙）
RIGHT_X0, RIGHT_X1 = 2.50, 6.00           # 右段半截残墙
FRONT_Y, BACK_Y = -4.00, 4.00             # 前/后墙外表面
LEFT_TOP = 6.85                           # 左段最高处
RIGHT_TOP = 3.50                          # 右段半截墙高度
SLAB_T = 0.22
CELL_FRONT = 0.26                         # 正面墙格子（= 崩口台阶步长 26 cm）
CELL_SIDE = 0.34                          # 侧/后墙格子
CELL_REAR = 0.55                          # 后皮格子（只提供室内面与墙厚）

CONCRETE_HEX = "8a7f70"
CONCRETE_DARK_HEX = "6f665a"
BRICK_HEX = "9c6b5a"
REBAR_HEX = "7a5a40"


# ---------------------------------------------------------------- 颜色 / 材质

def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hex(h):
    return (
        _srgb_to_linear(int(h[0:2], 16) / 255.0),
        _srgb_to_linear(int(h[2:4], 16) / 255.0),
        _srgb_to_linear(int(h[4:6], 16) / 255.0),
        1.0,
    )


def _ramp(nt, loc, p0, c0, p1, c1):
    n = nt.nodes.new("ShaderNodeValToRGB")
    n.location = loc
    n.color_ramp.elements[0].position = p0
    n.color_ramp.elements[0].color = c0
    n.color_ramp.elements[1].position = p1
    n.color_ramp.elements[1].color = c1
    return n


def _mat_concrete():
    """三层叠加：大尺度污渍 + 露骨料 Voronoi 密集点 + 竖向雨痕，bump 0.35。"""
    mat = bpy.data.materials.get("wst_mat_concrete")
    if mat is None:
        mat = bpy.data.materials.new("wst_mat_concrete")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (760, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (500, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.95
    bsdf.inputs["Metallic"].default_value = 0.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1160, 0)

    # 1) 大尺度污渍
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.location = (-960, 300)
    n1.inputs["Scale"].default_value = 2.5
    n1.inputs["Detail"].default_value = 7.0
    n1.inputs["Roughness"].default_value = 0.6
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    r1 = _ramp(nt, (-760, 320), 0.36, _hex("6d6357"), 0.63, _hex(CONCRETE_HEX))
    nt.links.new(n1.outputs["Fac"], r1.inputs["Fac"])

    # 2) 露骨料：Voronoi F1 密集小点
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.location = (-960, -40)
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 46.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    r2 = _ramp(nt, (-760, -20), 0.03, (0.0, 0.0, 0.0, 1.0), 0.15, (1.0, 1.0, 1.0, 1.0))
    nt.links.new(vor.outputs["Distance"], r2.inputs["Fac"])
    amp = nt.nodes.new("ShaderNodeMath")
    amp.location = (-560, -40)
    amp.operation = "MULTIPLY"
    amp.inputs[1].default_value = 0.55
    nt.links.new(r2.outputs["Color"], amp.inputs[0])

    # 3) 竖向雨痕（噪声沿 Z 拉长）
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.location = (-1000, -400)
    mp.inputs["Scale"].default_value = (7.0, 7.0, 0.34)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    n3 = nt.nodes.new("ShaderNodeTexNoise")
    n3.location = (-830, -400)
    n3.inputs["Scale"].default_value = 1.7
    n3.inputs["Detail"].default_value = 5.0
    nt.links.new(mp.outputs["Vector"], n3.inputs["Vector"])
    r3 = _ramp(nt, (-650, -400), 0.42, _hex("5f564b"), 0.58, (1.0, 1.0, 1.0, 1.0))
    nt.links.new(n3.outputs["Fac"], r3.inputs["Fac"])

    mix1 = nt.nodes.new("ShaderNodeMixRGB")
    mix1.location = (-360, 120)
    mix1.blend_type = "MULTIPLY"
    mix1.inputs["Fac"].default_value = 0.72
    nt.links.new(r1.outputs["Color"], mix1.inputs["Color1"])
    nt.links.new(r3.outputs["Color"], mix1.inputs["Color2"])

    mix2 = nt.nodes.new("ShaderNodeMixRGB")
    mix2.location = (-140, 60)
    mix2.blend_type = "MIX"
    mix2.inputs["Color2"].default_value = _hex("584f45")
    nt.links.new(amp.outputs["Value"], mix2.inputs["Fac"])
    nt.links.new(mix1.outputs["Color"], mix2.inputs["Color1"])
    nt.links.new(mix2.outputs["Color"], bsdf.inputs["Base Color"])

    hgt = nt.nodes.new("ShaderNodeMath")
    hgt.location = (-360, -300)
    hgt.operation = "ADD"
    nt.links.new(r2.outputs["Color"], hgt.inputs[0])
    nt.links.new(n3.outputs["Fac"], hgt.inputs[1])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (140, -320)
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.015
    nt.links.new(hgt.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _mat_brick():
    """碎砖：砖红底 + 暗红/砖红斑点。"""
    mat = bpy.data.materials.get("wst_mat_brick")
    if mat is None:
        mat = bpy.data.materials.new("wst_mat_brick")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (380, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.90
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, 0)

    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.location = (-700, 200)
    n1.inputs["Scale"].default_value = 6.5
    n1.inputs["Detail"].default_value = 8.0
    n1.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    r1 = _ramp(nt, (-500, 220), 0.35, _hex("7d5347"), 0.64, _hex(BRICK_HEX))
    nt.links.new(n1.outputs["Fac"], r1.inputs["Fac"])

    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.location = (-700, -140)
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 28.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    r2 = _ramp(nt, (-500, -120), 0.04, (0.0, 0.0, 0.0, 1.0), 0.22, (1.0, 1.0, 1.0, 1.0))
    nt.links.new(vor.outputs["Distance"], r2.inputs["Fac"])
    amp = nt.nodes.new("ShaderNodeMath")
    amp.location = (-300, -120)
    amp.operation = "MULTIPLY"
    amp.inputs[1].default_value = 0.6
    nt.links.new(r2.outputs["Color"], amp.inputs[0])

    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.location = (-100, 60)
    mix.blend_type = "MIX"
    mix.inputs["Color2"].default_value = _hex("7a3b30")
    nt.links.new(amp.outputs["Value"], mix.inputs["Fac"])
    nt.links.new(r1.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (140, -240)
    bump.inputs["Strength"].default_value = 0.42
    nt.links.new(n1.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _mat_rebar():
    mat = bpy.data.materials.get("wst_mat_rebar")
    if mat is None:
        mat = bpy.data.materials.new("wst_mat_rebar")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (520, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (280, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.70
    bsdf.inputs["Metallic"].default_value = 0.6
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-620, 0)
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.location = (-440, 0)
    n1.inputs["Scale"].default_value = 18.0
    n1.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    r1 = _ramp(nt, (-240, 40), 0.35, _hex("5d4431"), 0.66, _hex(REBAR_HEX))
    nt.links.new(n1.outputs["Fac"], r1.inputs["Fac"])
    nt.links.new(r1.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (60, -220)
    bump.inputs["Strength"].default_value = 0.30
    nt.links.new(n1.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _materials():
    return {
        "concrete": _mat_concrete(),
        "brick": _mat_brick(),
        "rebar": _mat_rebar(),
    }


# ---------------------------------------------------------------- 网格骨架

def _merge(dst, src, mat):
    """把 src bmesh 中的几何按 mat 变换后并入 dst。"""
    vmap = {}
    for v in src.verts:
        vmap[v] = dst.verts.new(mat @ v.co)
    for f in src.faces:
        try:
            dst.faces.new([vmap[v] for v in f.verts])
        except ValueError:
            pass
    src.free()


def _axis(w, cell):
    n = max(2, int(round(w / cell)))
    dx = w / n
    return [i * dx for i in range(n + 1)], dx


def _zaxis(h, cell, band=None):
    """z 轴：均匀网格；(band) 边界插一对相隔 4 cm 的行 → 楼板带台阶是硬棱不是斜面。"""
    n = max(2, int(round(h / cell)))
    dz = h / n
    zs = [i * dz for i in range(n + 1)]
    if band:
        extra = []
        for zb in band:
            if 0.0 < zb < h:
                extra += [zb - 0.02, zb + 0.02]
        if extra:
            zs = sorted(set([round(v, 5) for v in zs] + [round(v, 5) for v in extra]))
    return zs


def _top_profile(nx, nz, rng, jag, drop_left, drop_right, h):
    """墙顶轮廓（每列保留几格）：2–4 段宽平台 + 2–4 处大崩口 + 少量 1 格小齿。

    只允许"1 列宽的细高片"存在到 ±2 格：细高片在成片里就是一张发亮薄卡片。
    """
    dz = h / nz
    H = [nz] * nx
    nseg = max(2, min(4, nx // 4))
    if nx >= 8 and nseg > 1:
        cuts = sorted(rng.sample(range(3, nx - 2), nseg - 1))
        idx, cur = 0, nz
        for i in range(nx):
            while idx < len(cuts) and i == cuts[idx]:
                cur = min(nz, max(3, cur + rng.randint(-5, 5)))
                idx += 1
            H[i] = cur

    for _ in range(rng.randint(2, 4)):
        wd = rng.randint(2, max(2, nx // 4))
        dep = rng.randint(2, max(2, int(round(jag / dz)) + 2))
        x0 = rng.randint(0, max(0, nx - wd))
        for i in range(x0, min(nx, x0 + wd)):
            H[i] = max(3, H[i] - dep)

    # 一处深崩口（打到楼板带，露出楼板断面）
    wd = rng.randint(2, max(2, nx // 5))
    x0 = rng.randint(nx // 2, max(nx // 2, nx - wd))
    for i in range(x0, min(nx, x0 + wd)):
        H[i] = max(3, H[i] - int(round(nz * 0.55)))

    for i in range(nx):
        if rng.random() < 0.25:
            H[i] = min(nz, max(3, H[i] + rng.choice((-1, 1))))

    span = max(1.0, nx * 0.22)
    for i in range(nx):
        fl = max(0.0, 1.0 - i / span)
        fr = max(0.0, 1.0 - (nx - 1 - i) / span)
        H[i] -= int(round((drop_left * fl + drop_right * fr) / dz))
        H[i] = max(3, min(nz, H[i]))

    for _ in range(8):
        changed = False
        for i in range(nx):
            lo = H[i - 1] if i > 0 else H[i]
            hi = H[i + 1] if i < nx - 1 else H[i]
            lim = min(lo, hi) + 2
            if H[i] > lim:
                H[i] = lim
                changed = True
        if not changed:
            break
    return [H[i] * dz for i in range(nx)]


def _mask(xs, zs, tops, holes, rng, erode_side=0.0):
    nx, nz = len(xs) - 1, len(zs) - 1
    mask = [[False] * nx for _ in range(nz)]
    for j in range(nz):
        cz = 0.5 * (zs[j] + zs[j + 1])
        for i in range(nx):
            cx = 0.5 * (xs[i] + xs[i + 1])
            ok = cz <= tops[i]
            if ok and erode_side > 0.0 and (i == 0 or i == nx - 1):
                if rng.random() < erode_side:
                    ok = False
            if ok:
                for (ax, bx, az, bz) in holes:
                    if ax < cx < bx and az < cz < bz:
                        ok = False
                        break
            mask[j][i] = ok
    return mask


def _break_pinches(mask, nx, nz):
    """拆掉"只在一个角点上相接"的格子对（否则加厚后出现 4 面共边的非流形棱）。"""
    for _ in range(8):
        changed = False
        for j in range(1, nz):
            for i in range(1, nx):
                a, b = mask[j - 1][i - 1], mask[j - 1][i]
                c, d = mask[j][i - 1], mask[j][i]
                if a and d and not b and not c:
                    mask[j][i] = False
                    changed = True
                elif b and c and not a and not d:
                    mask[j - 1][i] = False
                    changed = True
        if not changed:
            return


def _keep_largest_island(mask, nx, nz):
    """只留最大的一块连通区域（拆夹点可能孤立出 1–2 格，加厚后就是浮碎片）。"""
    seen = [[False] * nx for _ in range(nz)]
    keep = set()
    for j0 in range(nz):
        for i0 in range(nx):
            if not mask[j0][i0] or seen[j0][i0]:
                continue
            seen[j0][i0] = True
            stack = [(j0, i0)]
            comp = []
            while stack:
                j, i = stack.pop()
                comp.append((j, i))
                for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    jj, ii = j + dj, i + di
                    if 0 <= jj < nz and 0 <= ii < nx and mask[jj][ii] and not seen[jj][ii]:
                        seen[jj][ii] = True
                        stack.append((jj, ii))
            if len(comp) > len(keep):
                keep = set(comp)
    for j in range(nz):
        for i in range(nx):
            if mask[j][i] and (j, i) not in keep:
                mask[j][i] = False


def _band_shift(zs, band, sign):
    """楼板带外凸量（按顶点 z）：只在带内、离边界 2 cm 以上的行外凸。"""
    if not band:
        return None
    b0, b1 = band
    return [sign * BAND_OUT if (b0 + 0.019 < z < b1 - 0.019) else 0.0 for z in zs]


def _skin(bm, xs, zs, mask, y0, thick, rng, jitter, shift=None, back_shift=None):
    """把 mask 的格子做成一块厚 thick 的闭合板：正面 y=y0(+shift)，背面 y=y0+thick(+back_shift)。"""
    nx, nz = len(xs) - 1, len(zs) - 1
    fv, bv = {}, {}

    def fvert(i, j):
        k = (i, j)
        v = fv.get(k)
        if v is None:
            dy = shift[j] if shift else 0.0
            v = bm.verts.new((xs[i] + rng.uniform(-jitter, jitter),
                              y0 + dy + rng.uniform(-jitter, jitter) * 0.9,
                              zs[j] + rng.uniform(-jitter, jitter)))
            fv[k] = v
        return v

    def bvert(i, j):
        k = (i, j)
        v = bv.get(k)
        if v is None:
            dy = back_shift[j] if back_shift else 0.0
            v = bm.verts.new((xs[i] + rng.uniform(-jitter, jitter),
                              y0 + thick + dy + rng.uniform(-jitter, jitter) * 0.9,
                              zs[j] + rng.uniform(-jitter, jitter)))
            bv[k] = v
        return v

    def solid(i, j):
        return 0 <= i < nx and 0 <= j < nz and mask[j][i]

    for j in range(nz):
        for i in range(nx):
            if not mask[j][i]:
                continue
            try:
                bm.faces.new((fvert(i, j), fvert(i, j + 1), fvert(i + 1, j + 1), fvert(i + 1, j)))
            except ValueError:
                pass
            try:
                bm.faces.new((bvert(i + 1, j), bvert(i + 1, j + 1), bvert(i, j + 1), bvert(i, j)))
            except ValueError:
                pass
            # 侧壁：只在与空格相邻的一侧补，保证闭合且法线可 recalc
            if not solid(i - 1, j):
                try:
                    bm.faces.new((fvert(i, j), bvert(i, j), bvert(i, j + 1), fvert(i, j + 1)))
                except ValueError:
                    pass
            if not solid(i + 1, j):
                try:
                    bm.faces.new((fvert(i + 1, j + 1), bvert(i + 1, j + 1), bvert(i + 1, j), fvert(i + 1, j)))
                except ValueError:
                    pass
            if not solid(i, j - 1):
                try:
                    bm.faces.new((fvert(i + 1, j), bvert(i + 1, j), bvert(i, j), fvert(i, j)))
                except ValueError:
                    pass
            if not solid(i, j + 1):
                try:
                    bm.faces.new((fvert(i, j + 1), bvert(i, j + 1), bvert(i + 1, j + 1), fvert(i + 1, j + 1)))
                except ValueError:
                    pass

    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")


# ---------------------------------------------------------------- 小构件

def _box(bm, center, size, rot=(0.0, 0.0, 0.0), rng=None, jitter=0.0, mat_idx=0):
    """一个随机旋转/顶点抖动的盒子（12 三角）。"""
    sx, sy, sz = size
    mat = Matrix.Translation(center) @ Euler(rot, "XYZ").to_matrix().to_4x4()
    corners = []
    for dz in (-0.5, 0.5):
        for dy in (-0.5, 0.5):
            for dx in (-0.5, 0.5):
                jx = rng.uniform(-jitter, jitter) if rng else 0.0
                jy = rng.uniform(-jitter, jitter) if rng else 0.0
                jz = rng.uniform(-jitter, jitter) if rng else 0.0
                corners.append(bm.verts.new(mat @ Vector((dx * sx + jx, dy * sy + jy, dz * sz + jz))))
    quads = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    for q in quads:
        f = bm.faces.new([corners[i] for i in q])
        f.material_index = mat_idx


def _tri_prism(bm, p0, p1, p2, nrm, t=0.012):
    """薄三角片（碎玻璃）：两点面 + 三条侧边，闭合 8 三角。"""
    a = [bm.verts.new(p + nrm * (t * 0.5)) for p in (p0, p1, p2)]
    b = [bm.verts.new(p - nrm * (t * 0.5)) for p in (p0, p1, p2)]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((a[i], b[i], b[j], a[j]))


def _tube(bm, pts, radius, sides=5):
    """沿折线扫掠的圆管（两端封盖）。"""
    up = Vector((0.0, 0.0, 1.0))
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            d = pts[1] - pts[0]
        elif i == len(pts) - 1:
            d = pts[-1] - pts[-2]
        else:
            d = pts[i + 1] - pts[i - 1]
        if d.length < 1e-6:
            d = Vector((0.0, 0.0, 1.0))
        d = d.normalized()
        ref = up if abs(d.dot(up)) < 0.9 else Vector((1.0, 0.0, 0.0))
        u = d.cross(ref).normalized()
        v = d.cross(u).normalized()
        ring = []
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            ring.append(bm.verts.new(p + u * (radius * math.cos(a)) + v * (radius * math.sin(a))))
        rings.append(ring)
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(sides):
            k2 = (k + 1) % sides
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def _rot_low(size, rot):
    m = Euler(rot, "XYZ").to_matrix()
    sx, sy, sz = size
    return 0.5 * (abs(m[2][0]) * sx + abs(m[2][1]) * sy + abs(m[2][2]) * sz)


def _lean(bm, kx, ky):
    """按高度剪切：造成 1–4° 倾角。"""
    for v in bm.verts:
        z = v.co.z
        if z > 0.0:
            v.co.x += kx * z
            v.co.y += ky * z


# ---------------------------------------------------------------- 出对象

def _ensure_collection():
    root = bpy.data.collections.get(ROOT_COLLECTION)
    if root is None:
        root = bpy.data.collections.new(ROOT_COLLECTION)
        bpy.context.scene.collection.children.link(root)
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
        root.children.link(coll)
    return coll


def _purge():
    for ob in list(bpy.data.objects):
        if ob.name.startswith(PREFIX):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for mat in list(bpy.data.materials):
        if mat.name.startswith("wst_mat_") and mat.users == 0:
            bpy.data.materials.remove(mat)


def _shell_signed_volume(faces):
    vol = 0.0
    for f in faces:
        vs = f.verts
        a = vs[0].co
        for k in range(1, len(vs) - 1):
            b, c = vs[k].co, vs[k + 1].co
            vol += a.dot(b.cross(c)) / 6.0
    return vol


def _fix_shell_normals(bm):
    """按连通分量校正法线：体积为负说明整片壳朝内（recalc 对薄壳会判反）。"""
    bm.faces.ensure_lookup_table()
    seen = set()
    for f0 in bm.faces:
        if f0 in seen:
            continue
        comp, stack = [], [f0]
        seen.add(f0)
        while stack:
            f = stack.pop()
            comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g not in seen:
                        seen.add(g)
                        stack.append(g)
        if _shell_signed_volume(comp) < 0.0:
            bmesh.ops.reverse_faces(bm, faces=comp)


def _to_object(name, bm, mats, coll):
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    _fix_shell_normals(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.location = LOC
    ob.rotation_euler = (0.0, 0.0, ROT_Z)
    coll.objects.link(ob)
    return ob


# ---------------------------------------------------------------- 墙（两层皮 + 楼板带）

def _hole_bounds(mask, xs, zs, hole):
    """取某窗口实际吃掉的格子范围 → 洞壁的真实平面坐标（附带格子索引）。"""
    ax, bx, az, bz = hole
    i0 = i1 = None
    j0 = j1 = None
    nx, nz = len(xs) - 1, len(zs) - 1
    for j in range(nz):
        cz = 0.5 * (zs[j] + zs[j + 1])
        for i in range(nx):
            cx = 0.5 * (xs[i] + xs[i + 1])
            if ax < cx < bx and az < cz < bz and not mask[j][i]:
                i0 = i if i0 is None else min(i0, i)
                i1 = i if i1 is None else max(i1, i)
                j0 = j if j0 is None else min(j0, j)
                j1 = j if j1 is None else max(j1, j)
    if i0 is None:
        return None
    return (xs[i0], xs[i1 + 1], zs[j0], zs[j1 + 1], i0, i1, j0, j1)


def _window_dress(bm, rng, bounds, mask):
    """残存窗框细条 + 歪斜碎玻璃（都长在 0.14 深的窗洞里，贴着洞壁）。

    只有洞的上下确实还有墙体时才装：否则窗框会孤零零挂在空中（"浮块"）。
    """
    x0, x1, z0, z1, i0, i1, j0, j1 = bounds
    w = x1 - x0
    h = z1 - z0
    if w < 0.55 or h < 0.55:
        return
    nz = len(mask)
    nx = len(mask[0])
    bottom_ok = j0 - 1 >= 0 and all(mask[j0 - 1][i] for i in range(i0, i1 + 1))
    top_ok = j1 + 1 < nz and all(mask[j1 + 1][i] for i in range(i0, i1 + 1))
    left_ok = i0 - 1 >= 0 and all(mask[j][i0 - 1] for j in range(j0, j1 + 1))
    right_ok = i1 + 1 < nx and all(mask[j][i1 + 1] for j in range(j0, j1 + 1))
    ymid = FRONT_SKIN * 0.45
    if not bottom_ok:
        return
    # 下槛（横向变形条）
    _box(bm, Vector((0.5 * (x0 + x1), ymid, z0 + 0.045)),
         (w, FRONT_SKIN * 0.7, 0.09), rot=(0.0, rng.uniform(-0.03, 0.03), 0.0))
    # 一根竖梃（一端压在下槛上）/ 一根上框残条
    if left_ok or right_ok:
        jx = x0 + w * rng.uniform(0.25, 0.7)
        _box(bm, Vector((jx, ymid, z0 + h * 0.42)),
             (0.055, FRONT_SKIN * 0.55, h * 0.62), rot=(rng.uniform(-0.05, 0.05), 0.0, 0.0))
    if top_ok:
        _box(bm, Vector((x0 + w * 0.5, ymid, z1 - 0.05)),
             (w * 0.55, FRONT_SKIN * 0.5, 0.055), rot=(0.0, rng.uniform(-0.06, 0.06), 0.0))
    # 碎玻璃：底边贴在下槛顶面（z0+0.09），三片歪斜三角形
    for _ in range(rng.randint(2, 3)):
        bx = x0 + w * rng.uniform(0.12, 0.78)
        by = 0.02 + rng.uniform(0.0, 0.06)
        bw = w * rng.uniform(0.12, 0.3)
        bh = h * rng.uniform(0.12, 0.34)
        p0 = Vector((bx, by, z0 + 0.09))
        p1 = Vector((bx + bw, by + rng.uniform(-0.02, 0.02), z0 + 0.09))
        p2 = Vector((bx + bw * rng.uniform(0.2, 0.8), by + rng.uniform(-0.01, 0.03),
                     z0 + 0.09 + bh))
        _tri_prism(bm, p0, p1, p2, Vector((0.0, 1.0, 0.0)), t=0.010)


def _wall(bm, mat, w, top, holes, rng, cell=CELL_FRONT, through=(),
          jag=1.1, drop_left=0.0, drop_right=0.0, erode_side=0.0,
          jitter=0.045, band=(BAND_Z0, BAND_Z1), dress=(), rear=True):
    """一面墙：前皮（开窗口袋）+ 后皮（只有穿透洞）+ 楼板带外凸。

    z 从 -BURY 到 top；y 从 0（外表面）到 WALL_T。hole 坐标是建筑局部 (x, z)。
    """
    h = top + BURY
    xs, dx = _axis(w, cell)
    nx = len(xs) - 1
    zs = _zaxis(h, cell, (band[0] + BURY, band[1] + BURY) if band else None)
    nz = len(zs) - 1
    tops = _top_profile(nx, nz, rng, jag, drop_left, drop_right, h)
    holes_p = [(a, b, c + BURY, d + BURY) for (a, b, c, d) in holes]
    through_p = [holes_p[i] for i in through if 0 <= i < len(holes_p)]

    m_f = _mask(xs, zs, tops, holes_p, rng, erode_side)
    _break_pinches(m_f, nx, nz)
    _keep_largest_island(m_f, nx, nz)
    _skin(bm, xs, zs, m_f, 0.0, FRONT_SKIN, rng, jitter,
          shift=_band_shift(zs, tuple(v + BURY for v in band) if band else None, -1.0))

    if rear:
        xs2, dx2 = _axis(w, CELL_REAR)
        nx2 = len(xs2) - 1
        zs2 = _zaxis(h, CELL_REAR, tuple(v + BURY for v in band) if band else None)
        nz2 = len(zs2) - 1
        tops2 = []
        for i in range(nx2):
            cx = 0.5 * (xs2[i] + xs2[i + 1])
            k = min(nx - 1, max(0, int(cx / dx)))
            tops2.append(tops[k] - 0.10)
        m_r = _mask(xs2, zs2, tops2, through_p, rng, 0.0)
        _break_pinches(m_r, nx2, nz2)
        _keep_largest_island(m_r, nx2, nz2)
        _skin(bm, xs2, zs2, m_r, REAR_Y0, REAR_T, rng, jitter * 1.5,
              back_shift=_band_shift(zs2, tuple(v + BURY for v in band) if band else None, 1.0))

    # 窗户配件（窗框残条 / 碎玻璃）
    for hi in dress:
        if 0 <= hi < len(holes_p):
            b = _hole_bounds(m_f, xs, zs, holes_p[hi])
            if b:
                _window_dress(bm, rng, b, m_f)

    _merge_into(bm, mat)


def _merge_into(bm, mat):
    """把 bm 里当前全部几何按 mat 变换（就地，用于把面板搬到墙位）。"""
    if mat is None:
        return
    for v in bm.verts:
        v.co = mat @ v.co


# ---------------------------------------------------------------- 各部件

def _left_block():
    """左段：正面开窗两层残墙 + 可见左端墙 + 后墙残段。"""
    bm = bmesh.new()
    rng = random.Random(SEED + 1)
    w = LEFT_X1 - LEFT_X0

    holes = [
        (0.38, 1.23, 1.00, 2.70),
        (1.78, 2.63, 0.95, 2.65),
        (3.18, 4.03, 1.10, 2.75),
        (0.50, 1.45, 4.05, 5.65),
        (1.95, 2.85, 4.00, 5.60),
        (3.25, 4.65, 4.15, 5.70),
    ]
    sub = bmesh.new()
    _wall(sub, None, w, LEFT_TOP, holes, rng, cell=CELL_FRONT,
          through=(1, 4), jag=1.15, drop_right=2.60, jitter=0.045, dress=(0, 2, 5))
    _merge(bm, sub, Matrix.Translation((LEFT_X0, FRONT_Y, 0.0)) @ Matrix.Translation((0.0, 0.0, -BURY)))

    # 左端墙（相机可见的侧脸）：local x = BACK_Y - y
    sub = bmesh.new()
    _wall(sub, None, 8.0, LEFT_TOP - 0.15,
          [(4.30, 5.50, 1.20, 2.60),
           (1.60, 2.80, 3.95, 5.35),
           (6.55, 7.45, 4.10, 5.55)],
          rng, cell=CELL_SIDE, through=(2,), jag=0.95,
          drop_left=0.55, drop_right=0.30, jitter=0.05, dress=(1,))
    _merge(bm, sub, Matrix.Translation((LEFT_X0, BACK_Y, 0.0)) @
           Matrix.Rotation(-math.pi / 2.0, 4, "Z") @ Matrix.Translation((0.0, 0.0, -BURY)))

    # 后墙残段（大半塌掉，只作背光剪影）
    sub = bmesh.new()
    _wall(sub, None, w, 5.40,
          [(0.55, 1.95, 0.60, 2.60), (2.60, 3.95, 1.30, 3.10)],
          rng, cell=CELL_SIDE, jag=2.30, drop_left=1.10, drop_right=0.60,
          erode_side=0.45, jitter=0.06)
    _merge(bm, sub, Matrix.Translation((LEFT_X0, BACK_Y - WALL_T, 0.0)) @
           Matrix.Translation((0.0, 0.0, -BURY)))

    _lean(bm, 0.030, 0.016)       # 约 1.7° / 0.9° 倾角
    return bm


def _right_block():
    """右段：只剩半截墙，屋顶与楼板全无（楼板带正好落在断口上）。"""
    bm = bmesh.new()
    rng = random.Random(SEED + 2)
    w = RIGHT_X1 - RIGHT_X0

    sub = bmesh.new()
    _wall(sub, None, w, RIGHT_TOP, [(1.30, 2.20, 0.90, 2.30)], rng,
          cell=CELL_FRONT, through=(0,), jag=1.30, drop_left=0.35,
          drop_right=0.55, jitter=0.055, dress=(0,))
    _merge(bm, sub, Matrix.Translation((RIGHT_X0, FRONT_Y, 0.0)) @ Matrix.Translation((0.0, 0.0, -BURY)))

    sub = bmesh.new()
    _wall(sub, None, 8.0, RIGHT_TOP - 0.55, [(1.20, 2.20, 0.90, 2.10)], rng,
          cell=CELL_SIDE, through=(0,), jag=1.55, drop_left=0.40,
          drop_right=1.05, jitter=0.065)
    _merge(bm, sub, Matrix.Translation((RIGHT_X1, BACK_Y, 0.0)) @
           Matrix.Rotation(-math.pi / 2.0, 4, "Z") @ Matrix.Translation((0.0, 0.0, -BURY)))

    # 朝向中央塌落区的断墙残根（local x = BACK_Y - y）
    sub = bmesh.new()
    _wall(sub, None, 3.40, 2.60, [], rng, cell=CELL_SIDE, jag=1.10,
          drop_left=0.30, drop_right=0.55, erode_side=0.55, jitter=0.06)
    _merge(bm, sub, Matrix.Translation((RIGHT_X0, BACK_Y, 0.0)) @
           Matrix.Rotation(-math.pi / 2.0, 4, "Z") @ Matrix.Translation((0.0, 0.0, -BURY)))

    # 后墙残根
    sub = bmesh.new()
    _wall(sub, None, 2.80, 2.35, [], rng, cell=CELL_SIDE, jag=1.25,
          drop_left=0.35, drop_right=0.30, jitter=0.06)
    _merge(bm, sub, Matrix.Translation((RIGHT_X0 + 0.70, BACK_Y - WALL_T, 0.0)) @
           Matrix.Translation((0.0, 0.0, -BURY)))

    _lean(bm, -0.022, -0.012)
    return bm


def _mound_h(x, y):
    """底坡高度场（散碎与尘土）：中段最高 ~2.55 m，碎块沉积在这层之上堆到 3.2 m 左右。"""
    xc, yc = 0.70, 0.30
    ax, ay = 3.45, 6.30
    t = 1.0 - ((x - xc) / ax) ** 2 - ((y - yc) / ay) ** 2
    if t <= 0.0:
        return 0.0
    return 2.55 * (t ** 0.85)


# 三档碎块（长边, 块数）：0.15 细碎 / 0.40 中块 / 0.90 大块
RUBBLE_CLASSES = ((0.15, 170), (0.40, 150), (0.90, 80))


def _rubble():
    """中段坍塌：坡状核心 + 三档碎块（大块半埋带倾角）+ 大残板 + 外围散砖。"""
    bm = bmesh.new()
    rng = random.Random(SEED + 3)

    nx, ny = 18, 28
    x0, x1 = -3.05, 4.45
    y0, y1 = -5.40, 6.00
    verts = {}
    for j in range(ny + 1):
        y = y0 + (y1 - y0) * j / ny
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            if i in (0, nx) or j in (0, ny):
                z = -0.45
            else:
                z = _mound_h(x, y) + rng.uniform(-0.26, 0.16)
                z = round(z / 0.09) * 0.09        # 量化成块面，避免读成光滑土丘
                z = max(z, -0.20)
            verts[(i, j)] = bm.verts.new((x, y, z))
    bm.verts.ensure_lookup_table()
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((verts[(i, j)], verts[(i + 1, j)],
                          verts[(i + 1, j + 1)], verts[(i, j + 1)]))
    rim = [verts[(i, 0)] for i in range(nx + 1)] + \
          [verts[(nx, j)] for j in range(1, ny + 1)] + \
          [verts[(i, ny)] for i in range(nx - 1, -1, -1)] + \
          [verts[(0, j)] for j in range(ny - 1, 0, -1)]
    bm.faces.new(rim)

    # 坡面几何建完之后再建 BVH，否则 ray_cast 全打空
    bvh = BVHTree.FromBMesh(bm)

    def surf_at(x, y):
        hit = bvh.ray_cast(Vector((x, y, 40.0)), Vector((0.0, 0.0, -1.0)))
        return None if hit[0] is None else hit[0].z

    def surf_max(x, y, r):
        best = None
        for k in range(6):
            a = 2.0 * math.pi * k / 6.0
            z = surf_at(x + r * math.cos(a), y + r * math.sin(a))
            if z is not None and (best is None or z > best):
                best = z
        return best

    # 三档碎块：逐块"沉积"——每块坐在当时的坡面上，每 25 块重建一次 BVH，
    # 于是后放的块会坐在先放的块上（互相支撑、有台阶感，不是光滑沙丘）。
    state = {"bvh": bvh, "n": 0}

    def pile_top(x, y, r):
        """足迹上 7 条竖射线命中的中值高度：只用最大值会让块在陡坡上"悬"出白缝。"""
        b = state["bvh"]
        lo = hi = None
        for k in range(7):
            if k == 0:
                px, py = x, y
            else:
                a = 2.0 * math.pi * (k - 1) / 6.0
                px, py = x + r * math.cos(a), y + r * math.sin(a)
            hit = b.ray_cast(Vector((px, py, 40.0)), Vector((0.0, 0.0, -1.0)))
            hz = hit[0].z if hit[0] is not None else None
            if hz is not None:
                lo = hz if lo is None else min(lo, hz)
                hi = hz if hi is None else max(hi, hz)
        if hi is None:
            return None
        return 0.5 * (lo + hi)

    for (long_edge, count) in RUBBLE_CLASSES:
        for _ in range(count):
            sx = long_edge * rng.uniform(0.55, 1.0)
            sy = long_edge * rng.uniform(0.45, 1.0)
            sz = long_edge * rng.uniform(0.25, 0.60)
            rot = (rng.uniform(-0.85, 0.85), rng.uniform(-0.85, 0.85), rng.uniform(0.0, 3.14))
            x = rng.uniform(-2.80, 4.15)
            y = rng.uniform(-5.10, 5.75)
            if state["n"] % 25 == 0:
                state["bvh"] = BVHTree.FromBMesh(bm)
            top = pile_top(x, y, 0.5 * max(sx, sy))
            if top is None or top < 0.12:
                continue
            size = (sx, sy, sz)
            zc = top - (0.24 if long_edge > 0.5 else 0.15) + _rot_low(size, rot)
            _box(bm, Vector((x, y, zc)), size, rot=rot, rng=rng, jitter=0.035,
                 mat_idx=1 if rng.random() < 0.28 else 0)
            state["n"] += 1

    # 5 块大残板（半埋进块堆、带倾角，压在下面的碎块上）
    state["bvh"] = BVHTree.FromBMesh(bm)
    for _ in range(5):
        sx = rng.uniform(1.10, 2.10)
        sy = rng.uniform(0.70, 1.30)
        sz = rng.uniform(0.16, 0.24)
        rot = (rng.uniform(-0.65, 0.65), rng.uniform(-0.45, 0.45), rng.uniform(0.0, 3.14))
        x = rng.uniform(-1.30, 2.90)
        y = rng.uniform(-3.40, 3.80)
        top = pile_top(x, y, 0.5 * max(sx, sy))
        if top is None or top < 0.55:
            continue
        size = (sx, sy, sz)
        zc = top - 0.22 + _rot_low(size, rot)
        _box(bm, Vector((x, y, zc)), size, rot=rot, rng=rng, jitter=0.05)

    # 坡脚散砖：坐在当时的坡面上、只露一角（整块埋进去既看不见，又会被连通门判成浮块）
    for _ in range(46):
        sx = rng.uniform(0.16, 0.34)
        sy = rng.uniform(0.12, 0.26)
        sz = rng.uniform(0.07, 0.14)
        rot = (rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), rng.uniform(0.0, 3.14))
        x = rng.uniform(-2.60, 3.90)
        y = rng.uniform(-5.30, 5.90)
        top = pile_top(x, y, 0.25)
        if top is None or top < 0.08:
            continue
        size = (sx, sy, sz)
        zc = top - 0.05 + _rot_low(size, rot)
        _box(bm, Vector((x, y, zc)), size, rot=rot, rng=rng, jitter=0.02,
             mat_idx=1 if rng.random() < 0.35 else 0)
    return bm


# ---------------------------------------------------------------- 楼板残段

def _slab_01():
    """二层楼板残段：从后墙塌下来，一头仍咬在后墙里，另一头落在楼底。"""
    bm = bmesh.new()
    rng = random.Random(SEED + 4)
    ang = math.radians(32.0)
    # 先把面板从 XZ 面翻成水平（R(-90°,X)），再整块向楼里倾斜 32°：
    # 低端落在楼底、高端咬进后墙残段（两端都有支撑，不是悬空板）。
    mat = (Matrix.Translation((-3.95, -0.30, 0.12))
           @ Matrix.Rotation(ang, 4, "X")
           @ Matrix.Rotation(-math.pi / 2.0, 4, "X"))
    w, ln = 3.90, 5.00
    cell = 0.40
    xs, dx = _axis(w, cell)
    ys, dy = _axis(ln, cell)
    nx, ny = len(xs) - 1, len(ys) - 1
    tops = []
    for i in range(nx):
        t = 1.0 - 0.35 * (i / max(1, nx - 1))
        tops.append(t)
    mask = [[False] * nx for _ in range(ny)]
    for j in range(ny):
        v = (j + 0.5) / ny
        for i in range(nx):
            lim = tops[i]
            ok = v <= lim
            if ok and 0.30 < v < 0.52 and rng.random() < 0.45:
                ok = False
            if ok and v > 0.72 and rng.random() < 0.30:
                ok = False
            mask[j][i] = ok
    _break_pinches(mask, nx, ny)
    _keep_largest_island(mask, nx, ny)
    _skin(bm, xs, ys, mask, 0.0, SLAB_T, rng, 0.05)
    _merge_into(bm, mat)
    return bm


def _slab_02():
    """斜插在坡脚的破损板。"""
    bm = bmesh.new()
    rng = random.Random(SEED + 5)
    w, h = 2.30, 2.70
    cell = 0.34
    xs, dx = _axis(w, cell)
    zs, dz = _axis(h, cell)
    nx, nz = len(xs) - 1, len(zs) - 1
    mask = [[False] * nx for _ in range(nz)]
    for j in range(nz):
        v = (j + 0.5) / nz
        for i in range(nx):
            lim = 1.0 - 0.45 * (i / max(1, nx - 1))
            ok = v <= lim
            if ok and rng.random() < 0.18:
                ok = False
            mask[j][i] = ok
    _break_pinches(mask, nx, nz)
    _keep_largest_island(mask, nx, nz)
    _skin(bm, xs, zs, mask, 0.0, 0.20, rng, 0.055)
    _merge_into(bm, Matrix.Translation((-1.55, -5.05, 0.10)) @ Matrix.Rotation(-0.62, 4, "X"))
    return bm


def _slab_03():
    """坡脚半埋的小残板（压在碎块堆里，只露一角）。"""
    bm = bmesh.new()
    rng = random.Random(SEED + 6)
    size = (1.15, 0.85, 0.18)
    rot = (0.26, -0.20, 0.55)
    zc = _mound_h(2.55, -3.95) - 0.26 + _rot_low(size, rot)
    _box(bm, Vector((2.55, -3.95, zc)), size, rot=rot, rng=rng, jitter=0.05)
    return bm


# ---------------------------------------------------------------- 钢筋

REBAR_BURY = 0.32          # 根部沿自身方向压进混凝土，自由端不会悬空
REBAR_R = 0.0075           # 直径 1.5 cm

REBARS = [
    # (起点(局部), 主方向, 弯曲方向, 长度)
    ((-5.35, -3.86, 6.35), (-0.25, -0.55, 0.80), (0.55, -0.35, 0.10), 0.62),
    ((-4.10, -3.86, 6.10), (0.20, -0.72, 0.66), (0.45, -0.25, 0.30), 0.70),
    ((-5.92, 0.55, 6.15), (-0.55, 0.55, 0.62), (-0.30, 0.15, 0.45), 0.66),
    ((-5.92, 2.30, 6.05), (-0.40, 0.70, 0.58), (0.10, 0.35, 0.55), 0.55),
    ((-3.05, -3.86, 3.32), (-0.20, -0.80, 0.55), (0.30, -0.30, -0.35), 0.72),
    ((-2.15, -3.86, 3.20), (0.30, -0.70, -0.62), (0.25, -0.20, 0.30), 0.58),
    ((3.25, -3.86, 3.30), (-0.10, -0.66, 0.74), (0.40, -0.25, 0.25), 0.60),
    ((5.15, -3.86, 3.10), (0.30, -0.60, 0.74), (0.20, -0.30, 0.35), 0.52),
    ((5.92, 1.35, 2.85), (0.55, 0.35, 0.76), (0.25, 0.30, 0.30), 0.60),
    ((2.55, 1.80, 3.28), (-0.55, 0.30, 0.78), (-0.30, 0.20, 0.25), 0.64),
]


def _rebar_pts(start, d, b, length, rng, hook=0.16):
    d = Vector(d).normalized()
    b = Vector(b).normalized()
    n = 7
    pts = [start]
    for i in range(1, n + 1):
        t = i / n
        p = start + d * (length * t) + b * (length * (t ** 1.9))
        p = p + Vector((rng.uniform(-0.015, 0.015), rng.uniform(-0.015, 0.015),
                        rng.uniform(-0.015, 0.015)))
        pts.append(p)
    tip = pts[-1]
    last = (pts[-1] - pts[-2]).normalized()
    side = last.cross(Vector((0.0, 0.0, 1.0)))
    if side.length < 1e-4:
        side = Vector((1.0, 0.0, 0.0))
    side.normalize()
    pts.append(tip + side * hook)
    pts.append(tip + side * hook - last * (hook * 0.6))
    return pts


def _rebar_obj(idx):
    bm = bmesh.new()
    rng = random.Random(SEED + 40 + idx)
    start, d, b, length = REBARS[idx]
    root = Vector(start) - Vector(d).normalized() * REBAR_BURY
    pts = [root] + _rebar_pts(Vector(start), d, b, length, rng)
    _tube(bm, pts, REBAR_R, sides=5)
    return bm


# ---------------------------------------------------------------- build

def build():
    coll = _ensure_collection()
    _purge()
    mats = _materials()
    concrete = [mats["concrete"]]
    brick = [mats["brick"], mats["concrete"]]
    rebar = [mats["rebar"]]

    made = []
    made.append(_to_object(PREFIX + "wall_left", _left_block(), concrete, coll))
    made.append(_to_object(PREFIX + "wall_right", _right_block(), concrete, coll))
    made.append(_to_object(PREFIX + "rubble", _rubble(), brick, coll))
    made.append(_to_object(PREFIX + "slab_01", _slab_01(), concrete, coll))
    made.append(_to_object(PREFIX + "slab_02", _slab_02(), concrete, coll))
    made.append(_to_object(PREFIX + "slab_03", _slab_03(), concrete, coll))
    for i in range(len(REBARS)):
        made.append(_to_object(PREFIX + "rebar_%02d" % (i + 1), _rebar_obj(i), rebar, coll))
    return made


def _tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def _report(made):
    tris = 0
    bmin = [1e9, 1e9, 1e9]
    bmax = [-1e9, -1e9, -1e9]
    names = []
    mats = []
    for ob in made:
        me = ob.data
        tris += _tris(me)
        names.append(ob.name)
        for ms in me.materials:
            if ms and ms.name not in mats:
                mats.append(ms.name)
        mw = ob.matrix_world
        for v in me.vertices:
            w = mw @ v.co
            for k in range(3):
                bmin[k] = min(bmin[k], w[k])
                bmax[k] = max(bmax[k], w[k])
    return {
        "created": names,
        "tris": tris,
        "bbox_min": [round(v, 3) for v in bmin],
        "bbox_max": [round(v, 3) for v in bmax],
        "bbox_size": [round(bmax[k] - bmin[k], 3) for k in range(3)],
        "materials": sorted(mats),
    }


if __name__ == "__main__":
    _made = build()
    print("HEADLESS " + json.dumps(_report(_made), ensure_ascii=False))
