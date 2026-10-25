"""角色贴图：给 wst_mat_char_* 各烘一张可平铺 PBR 贴图 + 局部立方投影 UV。

为什么不用节点乘色：glTF 导出器不认 Principled 上游的 Mix/Multiply 连线，乘色会丢，
BaseColor 只剩纯白。所以「颜色」必须烘进像素里，节点上只留 UVMap -> Image -> Base Color。

用法（在 wst_char.build() 末尾）：
    import wst_char_tex
    report["tex"] = wst_char_tex.build(SHADES)
"""

import bpy
import numpy as np

SIZE = 384          # 512 时 baseColor 每张 ~100 KB，14 个材质把 GLB 顶到 1.36 MB；
                    # 384 压到 ~55 KB，移动端首屏才和 4 件场景资产同量级
SEED = 20260801
UV_LAYER = "UVMap"
TEX_PREFIX = "wst_chartex_"

# key -> (tile 米, 程序化种类, 法线强度; 0 = 不出法线)
RECIPES = {
    # tile 是「一张贴图铺多少米」。原来 0.05~0.16 m，同一个斑点在角色身上重复 40+ 次，
    # 远看是一层「印花图案」（裤子上那圈三角形就是磨痕+斜纹的规则重复）。
    # 放大到 0.10~0.30 m 后每个 tile 覆盖更多表面，重复周期退到看不出规律。
    "skin": (0.30, "skin", 0.35),
    "leather": (0.30, "leather", 0.55),
    "leather_dark": (0.30, "leather", 0.55),
    "boot": (0.28, "leather", 0.60),
    "shirt": (0.18, "canvas", 0.85),
    "canvas": (0.18, "canvas", 0.85),
    "pants": (0.26, "twill", 0.70),
    "patch": (0.16, "canvas", 0.60),
    "scarf": (0.10, "knit", 0.90),
    "metal": (0.10, "metal", 0.45),
    "sole": (0.14, "sole", 0.60),
}

RUST = np.array([0.150, 0.055, 0.028], np.float32)


# ============ 噪声工具（周期化，平铺无缝）============

def _srgb(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92,
                    1.055 * np.power(lin, 1.0 / 2.4) - 0.055)


def _grid():
    ys, xs = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    return (xs + 0.5) / SIZE, (ys + 0.5) / SIZE


def _value_noise(cells, rng):
    lat = rng.random((cells, cells)).astype(np.float32)
    lat = np.pad(lat, ((0, 1), (0, 1)), mode="wrap")
    u, v = _grid()
    x, y = u * cells, v * cells
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    fx = x - x0
    fy = y - y0
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    a = lat[y0, x0] * (1 - fx) + lat[y0, x0 + 1] * fx
    b = lat[y0 + 1, x0] * (1 - fx) + lat[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def _fbm(rng, octaves):
    out = np.zeros((SIZE, SIZE), np.float32)
    amp, total = 1.0, 0.0
    for cells, w in octaves:
        out += _value_noise(cells, rng) * (amp * w)
        total += amp * w
        amp *= 0.55
    return out / max(total, 1e-6)


def _worley_edge(n, rng):
    """周期 Voronoi 的 (次近距 − 最近距)：皮革颗粒的沟就长在这条脊上。"""
    u, v = _grid()
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


def _smooth(lo, hi, t):
    t = np.clip((t - lo) / max(1e-6, hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _band(phase, cells):
    """0..1 的周期条纹（布纹/棱线/鞋底沟）。"""
    u, v = _grid()
    return 0.5 + 0.5 * np.sin(2.0 * np.pi * (phase(u, v) * cells))


# ============ 各材质配方：返回 (线性色, 高度)============

def _skin(rng, base):
    mott = _fbm(rng, ((5, 1.0), (11, 0.55), (23, 0.28)))
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col = col * (1.0 + 0.16 * (mott - 0.5))[..., None]
    col[..., 0] *= 1.0 + 0.14 * (mott - 0.5)          # 血色斑：只偏红不整体变亮
    pores = _value_noise(210, rng)
    pit = _smooth(0.60, 0.80, pores)
    col *= (1.0 - 0.09 * pit)[..., None]
    freckle = _smooth(0.93, 0.995, _value_noise(150, rng))
    col *= (1.0 - 0.22 * freckle)[..., None]
    return col, 0.55 * (pores - 0.5) + 0.45 * (mott - 0.5)


def _leather(rng, base):
    # 旧皮是「细颗粒 + 大皱纹」，不是均匀的球面凸包：颗粒压到很浅，皱纹用片状噪声
    edge = _worley_edge(70, rng)
    crease = 1.0 - _smooth(0.0, 0.055, edge)
    grain = _value_noise(230, rng) - 0.5
    wrinkle = _fbm(rng, ((7, 1.0), (17, 0.45)))
    cre = _smooth(0.42, 0.72, wrinkle)                 # 折痕/皱褶
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col *= (1.0 - 0.10 * crease)[..., None]            # 颗粒沟只在近处可见
    col *= (1.0 + 0.08 * grain)[..., None]
    col *= (1.0 - 0.15 * cre)[..., None]               # 皱褶里积灰变暗
    wear = _smooth(0.76, 0.96, _value_noise(9, rng))    # 磨亮露出底皮的地方
    col = col * (1.0 - 0.16 * wear)[..., None] + (base * 1.55) * (0.16 * wear)[..., None]
    return col, -0.30 * crease + 0.30 * grain - 0.85 * cre


def _canvas(rng, base):
    h = _band(lambda u, v: u, 150) * _band(lambda u, v: v, 150)
    dirt = _fbm(rng, ((4, 1.0), (12, 0.5), (40, 0.25)))
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col *= (0.90 + 0.20 * h)[..., None]
    col *= (1.0 - 0.18 * _smooth(0.55, 0.85, dirt))[..., None]
    stain = _smooth(0.78, 0.96, _value_noise(7, rng))
    col *= (1.0 - 0.20 * stain)[..., None]
    return col, h - 0.5


def _twill(rng, base):
    """斜纹布 + 磨损 + 浮土（参考图裤子上到处是沙尘）。"""
    tw = _band(lambda u, v: (u + v) * 0.5, 140)
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col *= (0.90 + 0.16 * tw)[..., None]
    scuff = _smooth(0.62, 0.92, _fbm(rng, ((6, 1.0), (18, 0.5))))
    col *= (1.0 - 0.16 * scuff)[..., None]
    dust = _smooth(0.52, 0.90, _value_noise(5, rng))
    dusty = base * np.array([1.9, 1.6, 1.25], np.float32)
    col = col * (1.0 - 0.22 * dust)[..., None] + dusty * (0.22 * dust)[..., None]
    return col, tw * 0.6 + scuff * 0.4 - 0.5


def _knit(rng, base):
    rib = _band(lambda u, v: v, 46)
    fine = _band(lambda u, v: u, 120)
    h = rib * 0.68 + fine * 0.32
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col *= (0.84 + 0.28 * h)[..., None]
    fuzz = _value_noise(200, rng) - 0.5
    col *= (1.0 + 0.10 * fuzz)[..., None]
    return col, h - 0.5


def _metal(rng, base):
    scr = _band(lambda u, v: u, 9)
    scratch = _smooth(0.90, 0.995, scr) * _smooth(0.35, 0.75, _value_noise(3, rng))
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col *= (0.95 + 0.22 * scratch)[..., None]
    rust = _smooth(0.66, 0.92, _fbm(rng, ((7, 1.0), (20, 0.6))))
    col = col * (1.0 - rust)[..., None] + RUST * rust[..., None]
    return col, scratch * 0.3 - rust * 0.5


def _sole(rng, base):
    groove = _band(lambda u, v: v, 26)
    grit = _value_noise(180, rng) - 0.5
    col = np.repeat(base[None, None, :], SIZE, 0).repeat(SIZE, 1).astype(np.float32)
    col *= (0.86 + 0.22 * groove)[..., None]
    col *= (1.0 + 0.12 * grit)[..., None]
    return col, groove - 0.5


KINDS = {
    "skin": _skin, "leather": _leather, "canvas": _canvas,
    "twill": _twill, "knit": _knit, "metal": _metal, "sole": _sole,
}


def _tint_to(col, base):
    """把贴图均值拉回 SHADES 基色：整体明度/色调仍由 SHADES 决定，贴图只加层次。"""
    mean = col.reshape(-1, 3).mean(axis=0)
    return np.clip(col * (np.array(base, np.float32) / np.maximum(mean, 1e-4)), 0.0, 1.0)


def _normals(h, strength):
    """高度场 -> 切线空间法线。梯度先按自身 95 分位归一，
    否则不同种类的噪声幅度差几十倍，法线强度失控（踩过：皮夹克渲成一粒粒爆米花）。"""
    dx = np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)
    dy = np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)
    k = 1.0 / max(float(np.percentile(np.abs(dx), 95)), 1e-6)
    dx = np.clip(dx * k, -1.0, 1.0) * strength
    dy = np.clip(dy * k, -1.0, 1.0) * strength
    n = np.stack([-dx, -dy, np.ones_like(dx)], axis=-1)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    return n * 0.5 + 0.5


# ============ 图像 ============

def _make_image(name, rgb, srgb_space):
    img = bpy.data.images.get(name)
    if img is not None and tuple(img.size) != (SIZE, SIZE):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, SIZE, SIZE, alpha=False)
    # colorspace 必须在写像素之前设：改 colorspace 会让 Blender 重新加载缓冲，
    # GENERATED 图会被清成纯黑（踩过：贴图全黑，角色渲成剪影）
    if srgb_space:
        img.colorspace_settings.name = "sRGB"
    else:
        img.colorspace_settings.name = "Non-Color"
    px = np.empty((SIZE, SIZE, 4), np.float32)
    px[:, :, :3] = _srgb(rgb) if srgb_space else np.clip(rgb, 0.0, 1.0)
    px[:, :, 3] = 1.0
    img.pixels.foreach_set(px.reshape(-1))
    img.update()
    try:
        img.pack()
    except RuntimeError:
        img.filepath_raw = bpy.path.abspath("//" + name + ".png")
        img.file_format = "PNG"
        img.save()
        img.pack()
    return img


def _images(key, base):
    """每个 key 两张：albedo（烘了基色）+ normal（可选）。返回 (tex, normal_tex)。"""
    tile, kind, nstr = RECIPES[key]
    rng = np.random.default_rng(SEED + abs(hash(kind + key)) % 9973)
    col, h = KINDS[kind](rng, np.array(base, np.float32))
    alb = _make_image(TEX_PREFIX + key, _tint_to(col, base), True)
    nrm = None
    if nstr > 0.0:
        nrm = _make_image(TEX_PREFIX + key + "_n", _normals(h, nstr), False)
    return alb, nrm


# ============ UV：逐面取主轴做立方投影，按材质各自的 tile 缩放============

def _uv(ob, key_of_slot):
    me = ob.data
    if UV_LAYER not in me.uv_layers:
        me.uv_layers.new(name=UV_LAYER)
    uv = me.uv_layers[UV_LAYER].data
    verts = me.vertices
    loops = me.loops
    for poly in me.polygons:
        key = key_of_slot.get(poly.material_index)
        if key is None:
            continue
        tile = RECIPES[key][0]
        n = poly.normal
        ax = int(np.argmax(np.abs((n.x, n.y, n.z))))
        for li in poly.loop_indices:
            co = verts[loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            uv[li].uv = (u / tile, v / tile)
    return len(uv)


# ============ 装配 ============

def _hook(mat, key, alb, nrm):
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    base = bsdf.inputs["Base Color"]

    uvn = nt.nodes.get("CharUV") or nt.nodes.new("ShaderNodeUVMap")
    uvn.name = "CharUV"
    uvn.uv_map = UV_LAYER
    uvn.location = (-820, 320)

    tex = nt.nodes.get("CharTex") or nt.nodes.new("ShaderNodeTexImage")
    tex.name = "CharTex"
    tex.image = alb
    tex.extension = "REPEAT"
    tex.location = (-600, 300)
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    for l in list(nt.links):
        if l.to_socket == base:
            nt.links.remove(l)
    nt.links.new(tex.outputs["Color"], base)

    if nrm is not None:
        ntex = nt.nodes.get("CharNrm") or nt.nodes.new("ShaderNodeTexImage")
        ntex.name = "CharNrm"
        ntex.image = nrm
        ntex.extension = "REPEAT"
        ntex.location = (-600, 40)
        nt.links.new(uvn.outputs["UV"], ntex.inputs["Vector"])
        nmap = nt.nodes.get("CharNMap") or nt.nodes.new("ShaderNodeNormalMap")
        nmap.name = "CharNMap"
        nmap.location = (-380, 40)
        nmap.inputs["Strength"].default_value = RECIPES[key][2]
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return key


def build(shades):
    """给每个有配方的材质挂贴图，并给用到的网格写 UV。返回统计。"""
    mats = {m.name: m for m in bpy.data.materials if m.name.startswith("wst_mat_char_")}
    key_by_matname = {}
    hooked = []
    for key, (base, _rough, _metal) in shades.items():
        if key not in RECIPES:
            continue
        mat = mats.get("wst_mat_char_" + key)
        if mat is None:
            continue
        alb, nrm = _images(key, base)
        _hook(mat, key, alb, nrm)
        key_by_matname[mat.name] = key
        hooked.append({"key": key, "tile_m": RECIPES[key][0],
                       "albedo": alb.name, "normal": nrm.name if nrm else None})

    loops = 0
    used = set()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.name.startswith("wst_char_"):
            continue
        me = ob.data
        key_of_slot = {}
        for i, slot_mat in enumerate(me.materials):
            if slot_mat is not None and slot_mat.name in key_by_matname:
                key_of_slot[i] = key_by_matname[slot_mat.name]
                used.add(slot_mat.name)
        if not key_of_slot:
            continue
        loops += _uv(ob, key_of_slot)
    return {"materials": hooked, "uv_loops": loops,
            "meshes_with_tex": len(used), "size": SIZE}
