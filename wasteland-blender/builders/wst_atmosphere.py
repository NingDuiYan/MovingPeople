# -*- coding: utf-8 -*-
"""Phase A: 黄昏大气 —— 天空渐变 + 太阳辉光 + 冷色补光 + 尘雾体积。
观感参数全部集中在 SPEC，改一处即可对比。GUI 内执行 build() 生效。"""
import bpy, math
from mathutils import Vector

SPEC = {
    "sun_az_deg": 34.0,
    "sun_elev_deg": 8.0,
    # 参考图亮度分布是双峰的（20-60 占 19.5%、120-160 占 17.5%），
    # 渲染一度被补光压成中间调一条（80-120 占 62%）→ 抬直射、收回补光，把两头拉开。
    "sun_energy": 8.5,
    # 参考图实测：沙地前景 (128,83,54)、天空右上 (102,83,83)，蓝通道并不低。
    # 原 (1.0,0.50,0.22) 的极暖日色把蓝压到个位数（渲染 sand_fg b≈8）→ 提蓝、降红。
    "sun_color": (1.0, 0.66, 0.46),
    "sun_angle_deg": 5.5,
    # 参考图背光面不是死黑（全图 std 只有 32.7，渲染是 44.1）→ 提高天空补光
    "fill_energy": 2.60,
    "fill_color": (0.70, 0.62, 0.58),
    "fill_elev_deg": 26.0,
    "fill_az_deg": -125.0,
    # 沙地反弹光：从相机这一侧低角度打亮背光面，否则背光面在 EEVEE 里接近全黑
    "bounce_energy": 2.60,
    "bounce_color": (0.88, 0.78, 0.70),
    "bounce_az_deg": -146.0,
    "bounce_elev_deg": 16.0,
    # 天空：按视线仰角 z 的渐变（z 归一化到 0..1）
    "sky_stops": [
        (0.00, "bf8455"),
        (0.08, "966c60"),
        (0.20, "6d6772"),
        (0.40, "4c5563"),
        (0.70, "333d4b"),
        (1.00, "232c3a"),
    ],
    "horizon_warm": "ef9b42",
    "warm_gain": 0.50,
    "glow_color": "ffab48",
    # sigma 单位是 (1-cos)：0.010≈8°, 0.055≈19°, 0.19≈36°
    # 参考图的天空右上角（离太阳约 25–30°）亮度只有 ~102/255，原参数在那一带仍有
    # halo 0.48 + haze 0.34 的叠加发射，整片天空被洗成奶白 → 收窄日核、压平辉光。
    "core_sigma": 0.0045,
    "core_gain": 0.8,
    "halo_sigma": 0.050,
    "halo_gain": 0.14,
    "haze_sigma": 0.17,
    "haze_gain": 0.07,
    "sky_strength": 1.25,
    # 参考图的天空有水平梯度：背离太阳一侧（左上）明显更暗(52 vs 中上 70)。
    # 原来只有垂直渐变，左上和中上一样亮 → 乘一个按太阳方位的系数。
    "sky_away_gain": 0.62,
    # 参考图的水平梯度是**低空**才有的：左地平线 74/56/46 比中上暗得多，而 20° 以上
    # 左右几乎一样亮。原来的方位系数对全天空一致 → 左上被压得过暗、左地平线过亮。
    # 用 lowmask 抬高指数，把这个系数收进 0..20° 的贴地带。
    "sky_away_low": 0.68,
    # 尘雾：参考图的雾只在远地平线附近起作用，中景沙地仍保留饱和色与细节；
    # 原 0.0042/15m 在 30 m 处就把地面洗成奶白，故降密度、压低雾顶、加深雾色。
    "fog_density": 0.0020,
    "fog_height": 9.0,
    "fog_falloff": 2.6,
    "fog_color": (0.78, 0.56, 0.40),
    "fog_aniso": 0.45,
    "view_look": "AgX - Punchy",
    "exposure": 0.18,
}


def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (_s2l(r), _s2l(g), _s2l(b), 1.0)


def _sun_dir():
    az, el = math.radians(SPEC["sun_az_deg"]), math.radians(SPEC["sun_elev_deg"])
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


def _clear_lights():
    for o in list(bpy.data.objects):
        if o.type == 'LIGHT':
            bpy.data.objects.remove(o, do_unlink=True)


def _sun(name, az, el, energy, color, angle, shadow=True):
    ld = bpy.data.lights.new(name, type='SUN')
    ld.energy, ld.color, ld.angle, ld.use_shadow = energy, color, math.radians(angle), shadow
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    a, e = math.radians(az), math.radians(el)
    v = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    ob.location = v * 150.0
    ob.rotation_euler = (-v).to_track_quat('-Z', 'Y').to_euler()
    return ob


def _node(nt, kind, loc=(0, 0)):
    n = nt.nodes.new(kind)
    n.location = loc
    return n


def _math(nt, op, a=None, b=None, clamp=False, loc=(0, 0)):
    n = _node(nt, "ShaderNodeMath", loc)
    n.operation = op
    n.use_clamp = clamp
    if isinstance(a, (int, float)):
        n.inputs[0].default_value = a
    elif a is not None:
        nt.links.new(a, n.inputs[0])
    if isinstance(b, (int, float)):
        n.inputs[1].default_value = b
    elif b is not None:
        nt.links.new(b, n.inputs[1])
    return n.outputs[0]


def _world():
    w = bpy.data.worlds.get("wst_world") or bpy.data.worlds.new("wst_world")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = _node(nt, "ShaderNodeOutputWorld", (1400, 0))

    # world 里 Incoming 在 EEVEE 恒为 0；方向向量必须取 TexCoord.Generated
    tc = _node(nt, "ShaderNodeTexCoord", (-1200, 0))
    sep = _node(nt, "ShaderNodeSeparateXYZ", (-1000, 0))
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    inc = tc.outputs["Generated"]

    # 仰角 0..1
    elev = _math(nt, 'ADD', sep.outputs["Z"], 0.02, loc=(-860, 120))
    elev = _math(nt, 'MULTIPLY', elev, 1.35, clamp=True, loc=(-720, 120))

    ramp = _node(nt, "ShaderNodeValToRGB", (-560, 200))
    els = ramp.color_ramp.elements
    stops = SPEC["sky_stops"]
    while len(els) > 1:
        els.remove(els[-1])
    els[0].position = stops[0][0]
    els[0].color = hex_lin(stops[0][1][:6])
    for pos, hx in stops[1:]:
        e = els.new(min(max(pos, 0.0), 1.0))
        e.color = hex_lin(hx[:6])
    nt.links.new(elev, ramp.inputs["Factor"])

    # 太阳方位的暖色（低空才明显）
    sun = _sun_dir()
    hz = Vector((sun.x, sun.y, 0.0)).normalized()
    dot = _node(nt, "ShaderNodeVectorMath", (-1000, -240))
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = hz
    nt.links.new(inc, dot.inputs[0])
    azf = _math(nt, 'MULTIPLY', dot.outputs["Value"], 0.5, loc=(-860, -240))
    azf = _math(nt, 'ADD', azf, 0.5, loc=(-720, -240))
    azf = _math(nt, 'POWER', azf, 2.2, loc=(-580, -240))
    lowmask = _math(nt, 'SUBTRACT', 1.0, _math(nt, 'MULTIPLY', elev, 3.2, clamp=True, loc=(-720, 340)), loc=(-560, 340))
    warmf = _math(nt, 'MULTIPLY', azf, lowmask, clamp=True, loc=(-420, -100))
    warmf = _math(nt, 'MULTIPLY', warmf, SPEC["warm_gain"], clamp=True, loc=(-280, -100))

    mix = _node(nt, "ShaderNodeMix", (-120, 120))
    mix.data_type = 'RGBA'
    nt.links.new(warmf, mix.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], mix.inputs[6])
    mix.inputs[7].default_value = hex_lin(SPEC["horizon_warm"])

    # 背离太阳一侧压暗：azf（0=背向 / 1=朝向太阳）→ 0.76..1.0
    azbase = _math(nt, 'MULTIPLY', azf, 1.0 - SPEC["sky_away_gain"], loc=(-420, 300))
    azbase = _math(nt, 'ADD', azbase, SPEC["sky_away_gain"], loc=(-300, 300))
    azk = _math(nt, 'MULTIPLY', lowmask, SPEC["sky_away_low"], loc=(-420, 380))
    azk = _math(nt, 'ADD', azk, 1.0, loc=(-300, 380))
    azdark = _math(nt, 'POWER', azbase, azk, loc=(-180, 300))
    dark3 = _node(nt, "ShaderNodeCombineXYZ", (60, 300))
    for i in range(3):
        nt.links.new(azdark, dark3.inputs[i])
    skycol = _node(nt, "ShaderNodeVectorMath", (-120, 300))
    skycol.operation = 'MULTIPLY'
    nt.links.new(mix.outputs[2], skycol.inputs[0])
    nt.links.new(dark3.outputs["Vector"], skycol.inputs[1])

    bg = _node(nt, "ShaderNodeBackground", (200, 200))
    bg.inputs["Strength"].default_value = SPEC["sky_strength"]
    nt.links.new(skycol.outputs["Vector"], bg.inputs["Color"])

    # 太阳辉光：cos → 角距 d=(1-cos) → exp(-(d/sigma)^2) 高斯衰减。
    # 用 cos^N 会在 20° 外仍有 0.2 强度，把整片天空洗成奶白，所以改成按角距衰减。
    sdot = _node(nt, "ShaderNodeVectorMath", (-1000, -460))
    sdot.operation = 'DOT_PRODUCT'
    sdot.inputs[1].default_value = sun
    nt.links.new(inc, sdot.inputs[0])
    pos = _math(nt, 'MAXIMUM', sdot.outputs["Value"], 0.0, loc=(-860, -460))
    ang = _math(nt, 'SUBTRACT', 1.0, pos, loc=(-720, -460))

    def _halo(key, y):
        t = _math(nt, 'DIVIDE', ang, SPEC[key + "_sigma"], loc=(-580, y))
        t = _math(nt, 'MULTIPLY', t, t, loc=(-440, y))
        t = _math(nt, 'MULTIPLY', t, -1.0, loc=(-300, y))
        t = _math(nt, 'EXPONENT', t, None, loc=(-160, y))
        return _math(nt, 'MULTIPLY', t, SPEC[key + "_gain"], loc=(-20, y))

    core = _halo("core", -380)
    halo = _halo("halo", -520)
    haze = _halo("haze", -660)
    glow = _math(nt, 'ADD', halo, haze, loc=(120, -560))
    total = _math(nt, 'ADD', glow, core, loc=(260, -460))
    emis = _node(nt, "ShaderNodeEmission", (-120, -540))
    emis.inputs["Color"].default_value = hex_lin(SPEC["glow_color"])
    nt.links.new(total, emis.inputs["Strength"])

    add = _node(nt, "ShaderNodeAddShader", (900, 0))
    nt.links.new(bg.outputs["Background"], add.inputs[0])
    nt.links.new(emis.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return w


def _fog():
    ob = bpy.data.objects.get("wst_volume_fog")
    if ob is None:
        me = bpy.data.meshes.new("wst_volume_fog_mesh")
        me.from_pydata([(-300, -60, -2), (300, -60, -2), (300, 180, -2), (-300, 180, -2),
                        (-300, -60, 26), (300, -60, 26), (300, 180, 26), (-300, 180, 26)],
                       [], [(3, 2, 1, 0), (4, 5, 6, 7), (1, 2, 6, 5), (2, 3, 7, 6),
                            (3, 0, 4, 7), (0, 1, 5, 4)])
        ob = bpy.data.objects.new("wst_volume_fog", me)
        bpy.context.scene.collection.objects.link(ob)
    ob.display_type = 'BOUNDS'
    ob.hide_render = False
    mat = bpy.data.materials.get("wst_mat_volume") or bpy.data.materials.new("wst_mat_volume")
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _node(nt, "ShaderNodeOutputMaterial", (800, 0))
    vol = _node(nt, "ShaderNodeVolumePrincipled", (400, 0))
    vol.inputs["Color"].default_value = (*SPEC["fog_color"], 1.0)
    vol.inputs["Anisotropy"].default_value = SPEC["fog_aniso"]
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])

    geo = _node(nt, "ShaderNodeNewGeometry", (-600, 0))
    sep = _node(nt, "ShaderNodeSeparateXYZ", (-420, 0))
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    mr = _node(nt, "ShaderNodeMapRange", (-240, 0))
    mr.inputs["From Min"].default_value = -1.0
    mr.inputs["From Max"].default_value = SPEC["fog_height"]
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.06
    mr.clamp = True
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    pw = _math(nt, 'POWER', mr.outputs["Result"], SPEC["fog_falloff"], loc=(-60, 0))
    mul = _math(nt, 'MULTIPLY', pw, SPEC["fog_density"], loc=(120, 0))
    nt.links.new(mul, vol.inputs["Density"])
    return ob


def _render_settings():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    for k, v in [("use_volumetric_lights", True), ("volumetric_end", 220.0),
                 ("volumetric_start", 0.5), ("volumetric_tile_size", "4"),
                 ("use_raytracing", True)]:
        try:
            setattr(sc.eevee, k, v)
        except Exception:
            pass
    vs = sc.view_settings
    vs.view_transform = 'AgX'
    try:
        vs.look = SPEC["view_look"]
    except Exception:
        pass
    vs.exposure = SPEC["exposure"]


def build():
    _clear_lights()
    _sun("wst_light_sun", SPEC["sun_az_deg"], SPEC["sun_elev_deg"],
         SPEC["sun_energy"], SPEC["sun_color"], SPEC["sun_angle_deg"])
    _sun("wst_light_fill", SPEC["fill_az_deg"], SPEC["fill_elev_deg"],
         SPEC["fill_energy"], SPEC["fill_color"], 50.0)
    _sun("wst_light_bounce", SPEC["bounce_az_deg"], SPEC["bounce_elev_deg"],
         SPEC["bounce_energy"], SPEC["bounce_color"], 60.0, shadow=False)
    _world()
    _fog()
    _render_settings()
    print("ATMO ok sun_az=%s" % SPEC["sun_az_deg"])


def render(path, samples=32, w=1280, h=720):
    import os
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.eevee.taa_render_samples = samples
    sc.render.image_settings.file_format = 'PNG'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("SHOT " + path)


SHOTS = r"C:\Users\ning\Desktop\MovingPeople\wasteland-blender\shots"