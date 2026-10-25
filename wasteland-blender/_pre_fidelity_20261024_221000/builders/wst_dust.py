# -*- coding: utf-8 -*-
"""参考图里废墟后方那根竖直沙尘羽流：锥形体积 + 噪声密度 + 随高度变淡。

另外把现有雾盒在 y 方向拉长，让 190m 处的远山也被雾吞掉（否则露出生硬的棕色剪影）。
"""
import bpy, bmesh, math, random

NAME = "wst_volume_dust"
MAT = "wst_mat_dust"
PREFIX = "wst_dust_"

# 尘柱开关：默认关闭。树高 5.1 m 时这根 30 m 高的锥形体积在 EEVEE 里被太阳
# 直射成一大块惨白的竖条（近处的雾密度还压不住它），观感比不加更差，
# 所以交付场景不建它；需要时把 PLUME 改回 True 重新 build()。
PLUME = False
RNG = random.Random(20240722)

BASE = (-3.4, 27.0, -0.6)       # 羽流根部（在废墟后方远处，参考图里位于中右）
TOP_Z = 34.0
DRIFT = (3.6, 3.0)              # 随高度向 +x/+y 飘
R_BASE, R_TOP = 1.8, 7.5
RINGS, SIDES = 16, 16
DENSITY = 0.065


def _mat():
    m = bpy.data.materials.get(MAT)
    if m is None:
        m = bpy.data.materials.new(MAT)
    if not m.use_nodes:
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.location = (320, 0)
    vol.inputs["Color"].default_value = (0.86, 0.70, 0.55, 1.0)
    vol.inputs["Anisotropy"].default_value = 0.32
    # 逆光沙尘要"发光"：纯散射会把它渲成比天空更暗的烟，参考图里是被夕阳照亮的亮尘
    if "Emission Color" in vol.inputs:
        vol.inputs["Emission Color"].default_value = (1.0, 0.74, 0.47, 1.0)
        vol.inputs["Emission Strength"].default_value = 0.02

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-900, 0)

    # 高度衰减：Generated.z 0(根) → 1(顶)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-700, 260)
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.location = (-520, 260)
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(sep.outputs["Z"], inv.inputs[1])
    fall = nt.nodes.new("ShaderNodeMath")
    fall.location = (-340, 260)
    fall.operation = "POWER"
    fall.inputs[1].default_value = 1.5
    nt.links.new(inv.outputs[0], fall.inputs[0])
    hgain = nt.nodes.new("ShaderNodeMapRange")
    hgain.location = (-160, 260)
    hgain.inputs["To Min"].default_value = 0.06
    hgain.inputs["To Max"].default_value = 1.60
    nt.links.new(fall.outputs[0], hgain.inputs["Value"])

    # 噪声团絮
    noi = nt.nodes.new("ShaderNodeTexNoise")
    noi.location = (-700, -160)
    noi.inputs["Scale"].default_value = 0.10
    noi.inputs["Detail"].default_value = 5.0
    noi.inputs["Roughness"].default_value = 0.62
    noi.inputs["Distortion"].default_value = 0.35
    nt.links.new(coord.outputs["Object"], noi.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-500, -160)
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.25, 0.25, 0.25, 1.0)
    ramp.color_ramp.elements[1].position = 0.58
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(noi.outputs["Fac"], ramp.inputs["Fac"])

    mul = nt.nodes.new("ShaderNodeMath")
    mul.location = (100, 60)
    mul.operation = "MULTIPLY"
    nt.links.new(hgain.outputs[0], mul.inputs[0])
    nt.links.new(ramp.outputs["Color"], mul.inputs[1])

    # 径向柔化：体积网格是有硬边界的锥筒，直接给密度会渲出"牛奶瀑布"。
    # Generated.xy 在包围盒里归一化，先算到轴线的距离，再用平滑阶跃把密度收到 0。
    def _m(op, x, y, a=None, b=None):    # 别叫 m —— 会盖掉上面的材质变量
        n = nt.nodes.new("ShaderNodeMath")
        n.location = (x, y)
        n.operation = op
        if a is not None:
            n.inputs[0].default_value = a
        if b is not None:
            n.inputs[1].default_value = b
        return n

    sx = _m("SUBTRACT", -520, -420, None, 0.5)
    sy = _m("SUBTRACT", -520, -560, None, 0.5)
    nt.links.new(sep.outputs["X"], sx.inputs[0])
    nt.links.new(sep.outputs["Y"], sy.inputs[0])
    px = _m("POWER", -360, -420, None, 2.0)
    py = _m("POWER", -360, -560, None, 2.0)
    nt.links.new(sx.outputs[0], px.inputs[0])
    nt.links.new(sy.outputs[0], py.inputs[0])
    add = _m("ADD", -200, -480)
    nt.links.new(px.outputs[0], add.inputs[0])
    nt.links.new(py.outputs[0], add.inputs[1])
    sq = _m("SQRT", -60, -480)
    nt.links.new(add.outputs[0], sq.inputs[0])
    x2 = _m("MULTIPLY", 60, -480, None, 2.0)
    nt.links.new(sq.outputs[0], x2.inputs[0])
    radial = nt.nodes.new("ShaderNodeMapRange")
    radial.location = (200, -480)
    radial.interpolation_type = "SMOOTHSTEP"
    radial.inputs["From Min"].default_value = 0.34
    radial.inputs["From Max"].default_value = 1.00
    radial.inputs["To Min"].default_value = 1.0
    radial.inputs["To Max"].default_value = 0.0
    radial.clamp = True
    nt.links.new(x2.outputs[0], radial.inputs["Value"])

    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.location = (360, -200)
    mul2.operation = "MULTIPLY"
    nt.links.new(mul.outputs[0], mul2.inputs[0])
    nt.links.new(radial.outputs[0], mul2.inputs[1])

    dens = nt.nodes.new("ShaderNodeMath")
    dens.location = (500, -200)
    dens.operation = "MULTIPLY"
    dens.inputs[1].default_value = DENSITY
    nt.links.new(mul2.outputs[0], dens.inputs[0])
    nt.links.new(dens.outputs[0], vol.inputs["Density"])

    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    return m


def _plume():
    for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        bpy.data.objects.remove(o, do_unlink=True)
    bm = bmesh.new()
    rings = []
    for i in range(RINGS):
        t = i / (RINGS - 1.0)
        z = BASE[2] + TOP_Z * t
        cx = BASE[0] + DRIFT[0] * (t ** 1.5) + RNG.uniform(-0.25, 0.25)
        cy = BASE[1] + DRIFT[1] * (t ** 1.5) + RNG.uniform(-0.25, 0.25)
        r = R_BASE + (R_TOP - R_BASE) * (t ** 0.85)
        ring = []
        for k in range(SIDES):
            a = math.tau * k / SIDES
            rr = r * (1.0 + RNG.uniform(-0.16, 0.22))
            ring.append(bm.verts.new((cx + math.cos(a) * rr, cy + math.sin(a) * rr,
                                      z + (RNG.uniform(-0.4, 0.4) if i else 0.0))))
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    for i in range(RINGS - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(SIDES):
            k2 = (k + 1) % SIDES
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    # 底盖 + 顶盖（体积需要一个封闭网格才稳定）
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        c = bm.verts.new((sum((v.co.x for v in ring)) / SIDES,
                          sum((v.co.y for v in ring)) / SIDES,
                          sum((v.co.z for v in ring)) / SIDES))
        for k in range(SIDES):
            k2 = (k + 1) % SIDES
            bm.faces.new((c, ring[k2], ring[k]) if flip else (c, ring[k], ring[k2]))
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(NAME)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(NAME, me)
    ob.data.materials.append(_mat())
    bpy.context.scene.collection.objects.link(ob)
    return ob


def extend_fog(factor=1.55):
    """雾盒沿 +y 拉长，覆盖 190m 处的远山。"""
    ob = bpy.data.objects.get("wst_volume_fog")
    if ob is None:
        return None
    ob.scale = (1.0, factor, 1.0)
    bpy.context.view_layer.update()
    return tuple(round(v, 1) for v in ob.dimensions)


def build():
    if PLUME:
        ob = _plume()
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    else:
        # 关掉时把历史上留下的残骸一并清掉，否则旧场景里的白条还在
        for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX)
                  or o.name == NAME]:
            bpy.data.objects.remove(o, do_unlink=True)
        tris = 0
    fog = extend_fog()
    return {"plume_tris": tris, "plume_enabled": PLUME, "fog_dim": fog}


if __name__ == "__main__":
    print(build())