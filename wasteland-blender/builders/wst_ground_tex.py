# -*- coding: utf-8 -*-
"""沙地裂纹贴图：把干裂板块做成真贴图（UV + Image Texture）导进 GLB。

为什么不用程序化节点：GLB 只认 baseColorTexture，节点链导出时会被丢成常数色，
网页里地面就是一块塑料橙。所以这里用 numpy 生成一张可无缝平铺的沙地贴图
（Voronoi 边＝裂纹 + 低频板块混色 + 浮沙 + 颗粒），UV 走世界坐标立方投影，
Blender 渲染与 Three.js 看到的是同一张图。
"""
import bpy, numpy as np

MAT = "wst_mat_sand"
IMG = "wst_sand_crack"
NODE_UV = "SandCrackUV"
NODE_TEX = "SandCrackTex"
UV_LAYER = "UVMap"

SIZE = 1024            # 贴图边长（4 m 一铺 → 3.9 mm/px，2 cm 裂纹约 5 px）
TILE = 4.0             # 一张贴图覆盖的实际尺寸（米）
SEED = 20261024
TARGET = (0.546, 0.390, 0.260)   # 与 wst_export.FLAT["wst_mat_sand"] 对齐的平均反照率

CELL_FINE = 160        # 细裂纹板块数（4 m 内 160 块 → 约 0.25 m 一块）
CELL_COARSE = 9        # 大板块（约 1.3 m）
CELL_MICRO = 460       # 龟裂纹的次级网（约 0.19 m）
CRACK_FINE = 0.0080    # 裂纹半宽（UV 单位）→ 约 3.2 cm
CRACK_COARSE = 0.016
CRACK_MICRO = 0.0045
DARK_FINE = 0.34
DARK_COARSE = 0.55
DARK_MICRO = 0.20
WARP = 0.012           # 域扭曲幅度：Voronoi 边是直线，扭一下才像自然开裂
GREY = np.array([0.360, 0.285, 0.215])   # 灰褐板块
SILT = np.array([0.650, 0.440, 0.255])   # 浮沙（更亮更饱和）


def _srgb(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92,
                    1.055 * np.power(lin, 1.0 / 2.4) - 0.055)


def _grid():
    ys, xs = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    return (xs + 0.5) / SIZE, (ys + 0.5) / SIZE


def _voronoi_edge(n, rng, warp=None):
    """周期 Voronoi 的 (次近距 − 最近距)：裂纹就长在这条脊线上。

    warp=(du, dv) 用来把直线边扭成自然裂纹（域扭曲）。
    """
    u, v = _grid()
    if warp is not None:
        u = u + warp[0]
        v = v + warp[1]
    seeds = rng.random((n, 2)).astype(np.float32)
    d1 = np.full((SIZE, SIZE), 9.0, np.float32)
    d2 = np.full((SIZE, SIZE), 9.0, np.float32)
    for sx, sy in seeds:
        dx = np.abs(u - sx)
        dx = np.minimum(dx, 1.0 - dx)
        dy = np.abs(v - sy)
        dy = np.minimum(dy, 1.0 - dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        d1 = np.where(closer, d, d1)
    return d2 - d1


def _value_noise(cells, rng):
    """周期值噪声：低分辨率随机格点双线性插值，比 Voronoi 便宜得多。"""
    lat = rng.random((cells, cells)).astype(np.float32)
    lat = np.pad(lat, ((0, 1), (0, 1)), mode="wrap")
    u, v = _grid()
    x = u * cells
    y = v * cells
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    a = lat[y0, x0] * (1 - fx) + lat[y0, x0 + 1] * fx
    b = lat[y0 + 1, x0] * (1 - fx) + lat[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def _smooth(lo, hi, t):
    t = np.clip((t - lo) / max(1e-6, hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _crack(edge, half):
    """1 = 裂纹中心，0 = 完整板块面。"""
    return 1.0 - _smooth(0.0, half, edge)


def _albedo():
    rng = np.random.default_rng(SEED)
    col = np.empty((SIZE, SIZE, 3), np.float32)
    col[:] = np.array(TARGET, np.float32)

    plate = _smooth(0.34, 0.68, _value_noise(3, rng))
    col = col * (1.0 - 0.30 * plate)[..., None] + GREY * (0.30 * plate)[..., None]

    silt = _smooth(0.52, 0.82, _value_noise(7, rng))
    col = col * (1.0 - 0.30 * silt)[..., None] + SILT * (0.30 * silt)[..., None]

    warm = np.array([1.0, 0.94, 0.86], np.float32)
    # 裂纹宽度也做低频扰动：同一条缝有粗有细，否则像画上去的网格
    width = _value_noise(6, rng) * 0.8 + 0.4
    warp_hi = ((_value_noise(5, rng) - 0.5) * WARP * 2.0,
               (_value_noise(5, rng) - 0.5) * WARP * 2.0)
    warp_lo = ((_value_noise(14, rng) - 0.5) * WARP * 0.7,
               (_value_noise(14, rng) - 0.5) * WARP * 0.7)
    coarse = _crack(_voronoi_edge(CELL_COARSE, rng, warp_hi), CRACK_COARSE * width)
    fine = _crack(_voronoi_edge(CELL_FINE, rng, warp_lo), CRACK_FINE * width)
    micro = _crack(_voronoi_edge(CELL_MICRO, rng, warp_lo), CRACK_MICRO * width)
    col *= (1.0 - DARK_COARSE * coarse)[..., None] * warm
    col *= (1.0 - DARK_FINE * fine * (1.0 - coarse))[..., None] * warm
    col *= (1.0 - DARK_MICRO * micro * (1.0 - fine) * (1.0 - coarse))[..., None]

    grain = _value_noise(256, rng) - 0.5
    col *= (1.0 + 0.16 * grain)[..., None]
    # 砂砾与小石子：高频噪声取顶端，压成深色小点（参考图地面到处是碎屑）
    grit = _smooth(0.86, 0.99, _value_noise(120, rng))
    col *= (1.0 - 0.34 * grit)[..., None]
    flake = _smooth(0.80, 0.97, _value_noise(48, rng))
    col *= (1.0 - 0.18 * flake)[..., None]

    # 均值拉回 TARGET：整体亮度与压平色一致，只增加层次
    mean = col.reshape(-1, 3).mean(axis=0)
    col *= (np.array(TARGET, np.float32) / np.maximum(mean, 1e-4))
    return np.clip(col, 0.0, 1.0)


def _image():
    img = bpy.data.images.get(IMG)
    if img is not None and img.size[0] == SIZE:
        return img
    if img is None:
        img = bpy.data.images.new(IMG, SIZE, SIZE, alpha=False)
    lin = _albedo()
    px = np.empty((SIZE, SIZE, 4), np.float32)
    px[:, :, :3] = _srgb(lin)          # Image.pixels 存 sRGB 值，节点 Mix 才走线性
    px[:, :, 3] = 1.0
    img.pixels.foreach_set(px.reshape(-1))
    img.update()
    try:
        img.pack()
    except RuntimeError:
        img.filepath_raw = bpy.path.abspath("//" + IMG + ".png")
        img.file_format = "PNG"
        img.save()
        img.pack()
    return img


def _cube_uv(ob):
    """世界坐标立方投影：相邻地块共享 UV 空间，裂纹跨物体也能接上。"""
    me = ob.data
    if UV_LAYER not in me.uv_layers:
        me.uv_layers.new(name=UV_LAYER)
    uv = me.uv_layers[UV_LAYER].data
    mw = ob.matrix_world
    rot = mw.to_3x3()
    verts = me.vertices
    for poly in me.polygons:
        n = rot @ poly.normal
        ax = int(np.argmax(np.abs((n.x, n.y, n.z))))
        for li in poly.loop_indices:
            co = mw @ verts[me.loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            uv[li].uv = (u / TILE, v / TILE)
    return len(uv)


def build():
    mat = bpy.data.materials[MAT]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    base = bsdf.inputs["Base Color"]

    uvn = nt.nodes.get(NODE_UV) or nt.nodes.new("ShaderNodeUVMap")
    uvn.name = NODE_UV
    uvn.uv_map = UV_LAYER
    uvn.location = (-900, 400)

    tex = nt.nodes.get(NODE_TEX) or nt.nodes.new("ShaderNodeTexImage")
    tex.name = NODE_TEX
    tex.image = _image()
    tex.extension = "REPEAT"
    tex.interpolation = "Linear"
    tex.location = (-680, 380)
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])

    for l in list(nt.links):
        if l.to_socket == base:
            nt.links.remove(l)
    nt.links.new(tex.outputs["Color"], base)

    n_uv = 0
    for ob in bpy.data.objects:
        if ob.type == "MESH" and any(m and m.name == MAT for m in ob.data.materials):
            n_uv += _cube_uv(ob)
    return {"mat": MAT, "image": tex.image.name, "size": SIZE, "tile_m": TILE,
            "uv_loops": n_uv}


if __name__ == "__main__":
    print(build())
