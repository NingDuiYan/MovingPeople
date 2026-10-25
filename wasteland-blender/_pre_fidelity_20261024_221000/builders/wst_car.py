# -*- coding: utf-8 -*-
"""Phase D: 锈蚀 70 年代长身四门轿车（5.2 m），按《废弃轿车_纯视觉描述.md》重建。

结构：侧面轮廓多边形沿 Y 挤出（宽度随高度收分）作为壳体，其余零件按"贴面装饰"叠上去：
门缝 / 门把手 / 锈片 / 流痕锈 / 锈穿孔 / 窗洞暗面 + 窗框 / 碎玻璃残留 / 瘪轮胎 / 保险杠 / 格栅 / 灯座。
原点在底部中心；X=车长(+X 朝前)，Y=车宽，Z=上。
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix

PARENT = "wst_car_parent"
COL = "collection_car"
L_HALF = 2.62          # 车长的一半 → 5.24 m
ROOF_Z = 1.40
WHEEL_R = 0.36
ARCH_R = 0.42
WHEEL_X = 1.45         # 轴距 ±1.45 → 2.9 m
WHEEL_HALF = 0.86
SEED = 20260702

# 门缝位置（按文档：前门距车头 1.5–2.8 m，后门 2.8–4.2 m）
DOOR_X = (1.12, -0.18, -1.58)
# 侧窗洞（前门窗 / 后门窗）
WIN = ((1.02, -0.16), (-0.24, -1.44))


def _f(z):
    """宽度收分：裙边窄、肩线最宽、车顶收进去。"""
    for z0, z1, w0, w1 in [(0.0, 0.50, 0.78, 0.925),
                           (0.50, 0.80, 0.925, 0.95),
                           (0.80, 1.00, 0.95, 0.905),
                           (1.00, 1.22, 0.905, 0.845),
                           (1.22, 1.50, 0.845, 0.775)]:
        if z <= z1:
            t = max(0.0, (z - z0) / (z1 - z0))
            return w0 + (w1 - w0) * t
    return 0.775


def _profile():
    """闭环侧面轮廓；从车头前缘沿顶部到车尾，再沿底边（含前后轮拱）回到车头。"""
    p = [
        (2.55, 0.86),    # 1 引擎盖前缘
        (2.20, 0.90),
        (1.55, 0.925),
        (1.05, 0.945),   # 4 前风档下沿(cowl)
        (0.72, 1.24),    # 5 风档上沿
        (0.30, 1.355),
        (-0.55, ROOF_Z),
        (-1.15, 1.355),
        (-1.80, 1.02),   # 9 后风档下沿 / 行李厢前
        (-2.30, 0.975),
        (-2.54, 0.925),
        (-2.62, 0.74),   # 12 尾板
        (-2.60, 0.52),
        (-2.44, 0.375),
        (-1.95, 0.335),
    ]
    for i in range(7):
        t = math.radians(180.0 - i * 30.0)
        p.append((-WHEEL_X + ARCH_R * math.cos(t), 0.335 + ARCH_R * math.sin(t)))
    p += [(1.02, 0.335)]
    for i in range(7):
        t = math.radians(180.0 - i * 30.0)
        p.append((WHEEL_X + ARCH_R * math.cos(t), 0.335 + ARCH_R * math.sin(t)))
    p += [(2.42, 0.345), (2.56, 0.42), (2.62, 0.62), (2.58, 0.75)]
    return p


# ============ 材质 ============

def _mat(name, color, metal, rough):
    """只在材质不存在时创建：wst_mat_opening 等场景共用材质不能被覆盖。"""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled"); p.location = (300, 0)
    p.inputs["Base Color"].default_value = (*color, 1.0)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    nt.links.new(p.outputs["BSDF"], out.inputs["Surface"])
    return m


def _paint():
    """六层锈色（噪声分层，不用 Voronoi 硬边）：
    褪色暗红底 → 主锈红棕 → 厚锈深褐（车顶/底部）→ 露底灰黄（凸棱麻点）。"""
    m = bpy.data.materials.get("wst_mat_car_paint")
    if m is None:
        m = bpy.data.materials.new("wst_mat_car_paint")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    out = N("ShaderNodeOutputMaterial"); out.location = (1200, 0)
    bsdf = N("ShaderNodeBsdfPrincipled"); bsdf.location = (920, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tc = N("ShaderNodeTexCoord"); tc.location = (-1200, 0)
    mp = N("ShaderNodeMapping"); mp.location = (-1020, 0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def noise(y, scale, detail, rough, distort=0.0):
        n = N("ShaderNodeTexNoise"); n.location = (-820, y)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = distort
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n

    def ramp(y, src, lo, hi):
        r = N("ShaderNodeValToRGB"); r.location = (-620, y)
        r.color_ramp.elements[0].position = lo
        r.color_ramp.elements[1].position = hi
        nt.links.new(src, r.inputs["Fac"])
        return r

    def mix(y, fac_socket, a, b, scale=1.0):
        k = N("ShaderNodeMath"); k.operation = 'MULTIPLY'; k.location = (y - 140, -160)
        k.inputs[1].default_value = scale
        nt.links.new(fac_socket, k.inputs[0])
        mx = N("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.location = (y, 200)
        nt.links.new(k.outputs[0], mx.inputs["Factor"])
        mx.inputs[6].default_value = (*a, 1.0)
        mx.inputs[7].default_value = (*b, 1.0)
        return mx

    # 大面积斑驳：褪色暗红 ↔ 主锈红棕
    n_big = noise(320, 2.4, 9.0, 0.62, 0.5)
    m_big = ramp(320, n_big.outputs["Fac"], 0.36, 0.68)
    # 厚锈斑块（车顶、门下半、底部）
    n_thick = noise(-160, 6.5, 7.0, 0.70, 0.9)
    m_thick = ramp(-160, n_thick.outputs["Fac"], 0.50, 0.74)
    # 细麻点 / 露底
    n_fine = noise(-460, 34.0, 5.0, 0.60, 1.2)
    m_fine = ramp(-460, n_fine.outputs["Fac"], 0.56, 0.70)

    # 门下半 / 底部锈得最深：按物体 Z 加一层高度权重
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (-1020, -560)
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    mz = N("ShaderNodeMapRange"); mz.location = (-820, -560)
    mz.inputs["From Min"].default_value = 0.42
    mz.inputs["From Max"].default_value = 0.95
    mz.inputs["To Min"].default_value = 1.0
    mz.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], mz.inputs["Value"])
    lowadd = N("ShaderNodeMath"); lowadd.operation = 'ADD'; lowadd.use_clamp = True
    lowadd.location = (-620, -560)
    nt.links.new(m_thick.outputs["Color"], lowadd.inputs[0])
    nt.links.new(mz.outputs["Result"], lowadd.inputs[1])

    c1 = mix(-380, m_big.outputs["Color"], (0.330, 0.122, 0.068), (0.185, 0.070, 0.032))
    c2 = mix(-120, lowadd.outputs[0], (0.185, 0.070, 0.032), (0.090, 0.042, 0.026), 0.75)
    # c2 的输入 A/B 由 c1 接过来
    nt.links.new(c1.outputs[2], c2.inputs[6])
    c3 = mix(120, m_fine.outputs["Color"], (0.090, 0.042, 0.026), (0.245, 0.200, 0.135), 0.55)
    nt.links.new(c2.outputs[2], c3.inputs[6])
    nt.links.new(c3.outputs[2], bsdf.inputs["Base Color"])

    rough = N("ShaderNodeMapRange"); rough.location = (620, -220)
    rough.inputs["To Min"].default_value = 0.62
    rough.inputs["To Max"].default_value = 0.95
    nt.links.new(m_thick.outputs["Color"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bsdf.inputs["Metallic"].default_value = 0.10

    # 凹凸：细麻点为主，厚锈区轻微起伏
    b1 = N("ShaderNodeBump"); b1.location = (620, -460)
    b1.inputs["Strength"].default_value = 0.30
    b1.inputs["Distance"].default_value = 0.004
    nt.links.new(n_fine.outputs["Fac"], b1.inputs["Height"])
    b2 = N("ShaderNodeBump"); b2.location = (800, -460)
    b2.inputs["Strength"].default_value = 0.22
    b2.inputs["Distance"].default_value = 0.008
    nt.links.new(n_thick.outputs["Fac"], b2.inputs["Height"])
    nt.links.new(b1.outputs["Normal"], b2.inputs["Normal"])
    nt.links.new(b2.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def _tire_mat():
    """轮胎：老化裂纹（横向一圈圈）+ 发乌哑光橡胶。"""
    m = bpy.data.materials.get("wst_mat_tire")
    if m is None:
        m = bpy.data.materials.new("wst_mat_tire")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    out = N("ShaderNodeOutputMaterial"); out.location = (700, 0)
    bsdf = N("ShaderNodeBsdfPrincipled"); bsdf.location = (420, 0)
    bsdf.inputs["Base Color"].default_value = (0.030, 0.026, 0.022, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.94
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    # 轮胎没有 UV：用 Object 坐标 + 拉长的噪声做老化裂纹（细碎、不规整）
    tc = N("ShaderNodeTexCoord"); tc.location = (-800, 0)
    mp = N("ShaderNodeMapping"); mp.location = (-620, 0)
    mp.inputs["Scale"].default_value = (3.0, 1.0, 9.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    w = N("ShaderNodeTexNoise"); w.location = (-420, 0)
    w.inputs["Scale"].default_value = 26.0
    w.inputs["Detail"].default_value = 8.0
    w.inputs["Roughness"].default_value = 0.7
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    bump = N("ShaderNodeBump"); bump.location = (240, -200)
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.012
    nt.links.new(w.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


# ============ 基础构件 ============

def _obj(name, verts, faces, mat, parent, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for f in me.polygons:
            f.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    col = bpy.data.collections.get(COL) or bpy.context.scene.collection
    col.objects.link(ob)
    me.materials.append(mat)
    ob.parent = parent
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.location = (0, 0, 0)
    return ob


def _merge_parts(parent):
    """把几十上百个小件按材质合成少数对象：GLB 的节点数与绘制调用能降一个量级。
    所有小件都以 identity 局部矩阵挂在 parent 下，顶点已在同一坐标系里，直接拼即可。"""
    parts = [o for o in bpy.data.objects
             if o.name.startswith("wst_car_") and o.type == 'MESH']
    if not parts:
        return 0
    order, buckets = [], {}
    # 小件的 matrix_local 实测已含父级变换（顶点取出来是世界坐标），先转回父级局部再拼
    inv = parent.matrix_world.inverted()
    for ob in parts:
        slots = [s.material for s in ob.material_slots] or [None]
        mw = ob.matrix_local
        for poly in ob.data.polygons:
            mi = poly.material_index if poly.material_index < len(slots) else 0
            mat = slots[mi]
            key = mat.name if mat else "-"
            if key not in buckets:
                buckets[key] = [mat, [], []]
                order.append(key)
            _, vs, fs = buckets[key]
            base = len(vs)
            for vi in poly.vertices:
                vs.append(tuple(inv @ (mw @ ob.data.vertices[vi].co)))
            fs.append(tuple(base + k for k in range(len(poly.vertices))))
    for ob in parts:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for key in order:
        mat, vs, fs = buckets[key]
        # 材质名本身已带类别前缀（wst_mat_car_paint），去掉 "wst_mat_" 后再去掉重复的 "car_"
        tag = key.replace("wst_mat_", "")
        if tag.startswith("car_"):
            tag = tag[4:]
        _obj("wst_car_" + tag, vs, fs, mat, parent)
    return len(order)


def _box(name, x0, x1, y0, y1, z0, z1, mat, par):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _obj(name, v, f, mat, par)


def _vstrip(x0, x1, z0, z1, side, off, seg=3):
    """车身侧面上的竖条带（贴面，宽度跟随收分曲线）。"""
    zs = [z0 + (z1 - z0) * i / seg for i in range(seg + 1)]
    v, f = [], []
    for z in zs:
        y = (_f(z) + off) * side
        v += [(x0, y, z), (x1, y, z)]
    for i in range(seg):
        a = i * 2
        q = (a, a + 2, a + 3, a + 1)
        f.append(q if side > 0 else tuple(reversed(q)))
    return v, f


def _top_z(x):
    """车身上轮廓在 x 处的高度（引擎盖 / 车顶 / 行李厢）。"""
    top = _profile()[:12]
    for i in range(len(top) - 1):
        x0, z0 = top[i]
        x1, z1 = top[i + 1]
        if min(x0, x1) - 1e-6 <= x <= max(x0, x1) + 1e-6:
            t = 0.0 if abs(x1 - x0) < 1e-9 else (x - x0) / (x1 - x0)
            return z0 + (z1 - z0) * t
    return top[-1][1]


def _hstrip(x0, x1, y0, y1, z):
    """顶面上的水平薄片（引擎盖 / 车顶 / 行李厢上的锈片）。"""
    v = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    return v, [(0, 1, 2, 3)]


def _flake_side(cx, cz, side, rng, thick=0.006):
    """侧面锈片：薄棱柱（贴面 → 抬起），有厚度才能读成"翘起的痂皮"。"""
    n = 5
    rad = rng.uniform(0.020, 0.058)
    ph = rng.uniform(0.0, 6.28)
    pts = []
    for i in range(n):
        a = ph + 2 * math.pi * i / n
        rr = rad * rng.uniform(0.55, 1.10)
        pts.append((cx + rr * math.cos(a) * 1.35, cz + rr * math.sin(a)))
    v = [(x, (_f(z) + 0.002) * side, z) for (x, z) in pts]
    v += [(x, (_f(z) + thick) * side, z) for (x, z) in pts]
    f = [tuple(range(n)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, j + n, i + n))
    return v, f


def _tube_path(pts, radii, sides, mat, name, par):
    """折线管（天线 / 排气）：平行传输标架放样。"""
    n = len(pts)
    P = [Vector(p) for p in pts]
    tans = []
    for i in range(n):
        a = P[max(0, i - 1)]
        b = P[min(n - 1, i + 1)]
        tans.append((b - a).normalized())
    verts, faces = [], []
    ref = Vector((0, 1, 0))
    for i in range(n):
        t = tans[i]
        u = ref.cross(t)
        if u.length < 1e-4:
            u = Vector((1, 0, 0)).cross(t)
        u.normalize()
        w = t.cross(u).normalized()
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(tuple(P[i] + u * (math.cos(a) * radii[i]) + w * (math.sin(a) * radii[i])))
    for i in range(n - 1):
        for k in range(sides):
            j = (k + 1) % sides
            faces.append((i * sides + k, i * sides + j,
                          (i + 1) * sides + j, (i + 1) * sides + k))
    faces.append(tuple(range(sides)))
    faces.append(tuple((n - 1) * sides + k for k in range(sides)))
    return _obj(name, verts, faces, mat, par, smooth=True)


# ============ 主构建 ============

def build():
    rng = random.Random(SEED)
    par = bpy.data.objects[PARENT]
    # 车身歪斜：右后方陷进沙里，整台车带着一点点 roll / pitch
    par.location = (6.55, 1.0, 0.0)
    par.rotation_euler = (math.radians(1.3), math.radians(-1.1), math.radians(195.0))
    for o in list(bpy.data.objects):
        if o.name.startswith("wst_car_") and o.type == 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    for o in list(bpy.data.objects):
        if o.name.startswith("wst_car_") and o.type == 'EMPTY' and o is not par:
            bpy.data.objects.remove(o, do_unlink=True)

    # 车专属材质每次重建都重新生成（_mat 只在不存在时创建，老 .blend 里改常量不生效）
    for mn in ("wst_mat_car_paint", "wst_mat_car_hub",
               "wst_mat_car_flake", "wst_mat_car_trim", "wst_mat_car_chrome",
               "wst_mat_car_cavity", "wst_mat_car_glass"):
        old = bpy.data.materials.get(mn)
        if old is not None:
            bpy.data.materials.remove(old)
    paint = _paint()
    tire = _tire_mat()
    hub = _mat("wst_mat_car_hub", (0.165, 0.078, 0.040), 0.12, 0.78)
    rust = _mat("wst_mat_rust", (0.180, 0.080, 0.040), 0.20, 0.88)
    flake = _mat("wst_mat_car_flake", (0.105, 0.052, 0.030), 0.15, 0.90)
    dark = _mat("wst_mat_car_trim", (0.017, 0.015, 0.013), 0.30, 0.80)
    chrome = _mat("wst_mat_car_chrome", (0.100, 0.085, 0.070), 0.45, 0.72)
    opening = _mat("wst_mat_opening", (0.012, 0.011, 0.010), 0.00, 0.94)
    # 车厢内腔：空窗框往里看是「暗但有体积」的深褐，不是纯黑洞
    cavity = _mat("wst_mat_car_cavity", (0.020, 0.017, 0.014), 0.00, 0.96)
    glass = bpy.data.materials.get("wst_mat_car_glass")
    if glass is None:
        glass = _mat("wst_mat_car_glass", (0.085, 0.092, 0.098), 0.0, 0.42)

    # ---------- 壳体 ----------
    prof = _profile()
    n = len(prof)
    verts, faces = [], []
    for (x, z) in prof:
        w = _f(z)
        verts.append((x, +w, z))
        verts.append((x, -w, z))
    for i in range(n):
        a, b = i * 2, ((i + 1) % n) * 2
        faces.append((a, b, b + 1, a + 1))
    faces.append(tuple(i * 2 for i in range(n)))
    faces.append(tuple(i * 2 + 1 for i in range(n)))
    car = _obj("wst_car_body", verts, faces, paint, par)
    bm = bmesh.new()
    bm.from_mesh(car.data)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(car.data)
    bm.free()

    # 风档 / 后风档：玻璃早没了 → 空窗洞（暗面），只在轮廓内留几块碎玻璃
    car.data.materials.append(cavity)
    oi = len(car.data.materials) - 1
    # 按几何判定而不是面索引：bmesh 三角化会重排面序
    for f in car.data.polygons:
        c, nz = f.center, f.normal
        if abs(nz.y) > 0.5:
            continue
        if 0.30 <= c.x <= 1.06 and c.z >= 0.95:
            f.material_index = oi          # 前风档
        elif -1.81 <= c.x <= -1.14 and c.z >= 1.00:
            f.material_index = oi          # 后窗

    # ---------- 车厢内芯 ----------
    # 空窗望进去若直接透到对面玻璃会读成一块平板，塞个暗内芯给出纵深
    _box("wst_car_interior", -1.45, 1.02, -0.72, 0.72, 0.32, 1.34, dark, par)

    # ---------- 门缝 / 把手 / B 柱 ----------
    for side in (1, -1):
        for k, x in enumerate(DOOR_X):
            v, f = _vstrip(x - 0.008, x + 0.008, 0.40, 1.335, side, 0.004, seg=4)
            _obj("wst_car_seam_%d%d" % (k, side), v, f, dark, par)
        # 门槛下沿的横向门缝
        v, f = _vstrip(DOOR_X[0], DOOR_X[2], 0.40, 0.42, side, 0.006, seg=1)
        _obj("wst_car_seam_bottom_%d" % side, v, f, dark, par)
        # 门把手（顶面磨亮 → chrome）
        for k, x in enumerate((0.52, -0.88)):
            v, f = _vstrip(x - 0.11, x + 0.11, 0.985, 1.02, side, 0.022, seg=1)
            _obj("wst_car_handle_%d%d" % (k, side), v, f, chrome, par)

    # ---------- 侧窗：空框 + 暗内腔 + 窗框 ----------
    for side in (1, -1):
        for k, (xa, xb) in enumerate(WIN):
            v, f = _vstrip(xb, xa, 1.055, 1.300, side, 0.002, seg=1)
            _obj("wst_car_win_%d%d" % (k, side), v, f, cavity, par)
            # 窗框：上 / 下 / 前 / 后
            v, f = _vstrip(xb, xa, 1.300, 1.335, side, 0.006, seg=1)
            _obj("wst_car_wintop_%d%d" % (k, side), v, f, paint, par)
            v, f = _vstrip(xb, xa, 1.015, 1.055, side, 0.006, seg=1)
            _obj("wst_car_winbot_%d%d" % (k, side), v, f, paint, par)
            v, f = _vstrip(xa - 0.035, xa, 1.015, 1.335, side, 0.006, seg=3)
            _obj("wst_car_winf_%d%d" % (k, side), v, f, paint, par)
            v, f = _vstrip(xb, xb + 0.035, 1.015, 1.335, side, 0.006, seg=3)
            _obj("wst_car_winr_%d%d" % (k, side), v, f, paint, par)

    # A/B/C 柱（压在窗框之间）
    for side in (1, -1):
        for k, (x0, x1, z0, z1) in enumerate(((1.02, 0.86, 1.00, 1.36),
                                             (-0.16, -0.24, 1.00, 1.36),
                                             (-1.44, -1.62, 1.00, 1.36))):
            v = [(x0, (_f(z0) + 0.007) * side, z0), (x1, (_f(z0) + 0.007) * side, z0),
                 (x1, (_f(z1) + 0.007) * side, z1), (x0, (_f(z1) + 0.007) * side, z1)]
            f = [(0, 1, 2, 3)] if side > 0 else [(3, 2, 1, 0)]
            _obj("wst_car_pillar_%d%d" % (k, side), v, f, paint, par)

    # 车顶滴水槽装饰条
    for side in (1, -1):
        v = [(-1.30, (_f(1.33) + 0.007) * side, 1.325), (0.92, (_f(1.33) + 0.007) * side, 1.325),
             (0.92, (_f(1.355) + 0.007) * side, 1.372), (-1.30, (_f(1.355) + 0.007) * side, 1.372)]
        f = [(0, 1, 2, 3)] if side > 0 else [(3, 2, 1, 0)]
        _obj("wst_car_rail_%d" % side, v, f, chrome, par)

    # ---------- 前风档碎玻璃（左下角蜘蛛网）+ 后窗碎玻璃 ----------
    def ws(t, y):
        """前风档平面参数点：t=0 风档下沿(x=1.05,z=0.945)，t=1 上沿(x=0.30,z=1.355)。"""
        x = 1.05 - 0.75 * t
        z = 0.945 + 0.41 * t
        return (x, y, z)

    rem = [ws(0.02, -0.62), ws(0.05, 0.06), ws(0.16, 0.44), ws(0.30, 0.30),
           ws(0.34, -0.10), ws(0.20, -0.55)]
    v = [(x + 0.010, y * 1.002, z + 0.008) for (x, y, z) in rem]
    _obj("wst_car_glass_ws", v, [tuple(range(len(v)))], glass, par)
    # 蛛网裂纹：一片细三角（玻璃断面亮）
    for k, (t0, y0, t1, y1) in enumerate(((0.06, -0.30, 0.26, 0.10),
                                          (0.10, 0.20, 0.30, 0.26),
                                          (0.04, 0.10, 0.22, -0.24))):
        a, b = ws(t0, y0), ws(t1, y1)
        c = ws((t0 + t1) * 0.5, (y0 + y1) * 0.5 + 0.05)
        vv = [(a[0] + 0.012, a[1] * 1.004, a[2] + 0.010), (b[0] + 0.012, b[1] * 1.004, b[2] + 0.010),
              (c[0] + 0.012, c[1] * 1.004, c[2] + 0.010)]
        _obj("wst_car_crack_%d" % k, vv, [(0, 1, 2)], glass, par)

    def rw(t, y):
        x = -1.15 - 0.65 * t
        z = 1.355 - 0.335 * t
        return (x, y, z)

    for k, (t0, t1, y0, y1) in enumerate(((0.05, 0.20, 0.30, 0.62),
                                          (0.10, 0.16, -0.55, -0.30),
                                          (0.30, 0.42, 0.18, 0.44))):
        p0, p1 = rw(t0, y0), rw(t0, y1)
        p2, p3 = rw(t1, y1 + rng.uniform(-0.04, 0.04)), rw(t1, y0 + rng.uniform(-0.03, 0.03))
        vv = [(p[0] - 0.010, p[1] * 1.004, p[2] - 0.006) for p in (p0, p1, p2, p3)]
        _obj("wst_car_glass_rw_%d" % k, vv, [(0, 1, 2, 3)], glass, par)

    # ---------- 锈片 / 流痕锈 / 锈穿孔 ----------
    for side in (1, -1):
        for k in range(11):
            x = rng.uniform(-2.35, 1.5)
            z = rng.uniform(0.44, 1.28)
            if 1.0 < z < 1.34 and (0.95 < x < 1.05 or -1.5 < x < -0.1):
                continue          # 别糊在窗洞上
            v, f = _flake_side(x, z, side, rng)
            _obj("wst_car_flake_%d%d" % (k, side), v, f, flake, par)
        # 车顶 / 引擎盖 / 行李厢上的锈片
        for k in range(8):
            x = rng.uniform(-2.3, 2.2)
            z = _top_z(x)
            if z < 0.9:
                continue
            w = _f(z) * 0.6
            cy0 = rng.uniform(-w, w)
            v, f = _hstrip(x - 0.05, x + 0.05, cy0, min(w, cy0 + 0.08), z + 0.006)
            _obj("wst_car_flaketop_%d" % k, v, f, flake, par)
        # 流痕锈：从车顶沿车门往下的一条条
        for k in range(5):
            x = rng.uniform(-1.4, 1.0)
            z1 = rng.uniform(0.55, 0.95)
            wdt = rng.uniform(0.012, 0.035)
            v, f = _vstrip(x, x + wdt, z1, 1.33, side, 0.005, seg=3)
            _obj("wst_car_drip_%d%d" % (k, side), v, f, rust, par)
        # 锈穿孔（车身底部 / 后门下半）
        for k in range(4):
            x = rng.uniform(-2.3, 1.6)
            z = rng.uniform(0.40, 0.56)
            s = rng.uniform(0.03, 0.075)
            v, f = _vstrip(x, x + s, z, z + s * 0.8, side, 0.007, seg=1)
            _obj("wst_car_hole_%d%d" % (k, side), v, f, opening, par)

    # ---------- 瘪轮胎 + 轮毂 ----------
    def tire_at(cx, cy, sink):
        R, hw, seg = WHEEL_R, 0.105, 24
        rings = ((cy - hw, 1.00), (cy, 1.06), (cy + hw, 1.00))
        v, f = [], []
        for (yy, bulge) in rings:
            for i in range(seg):
                a = 2 * math.pi * i / seg
                cz, sz = math.cos(a), math.sin(a)
                # 接地处压扁成饼：底部 z 抬到 0.075，同时向两侧鼓起
                zz = WHEEL_R + R * sz - sink
                xout = 1.0 + 0.10 * max(0.0, -sz) ** 2
                if zz < 0.072:
                    zz = 0.072
                    xout = 1.12
                v.append((cx + R * cz * xout * bulge, yy, zz))
        for r in range(2):
            base = r * seg
            for i in range(seg):
                j = (i + 1) % seg
                f.append((base + i, base + j, base + seg + j, base + seg + i))
        # 内外侧封盘
        inner = len(v)
        v.append((cx, rings[0][0], WHEEL_R - sink * 0.5))
        outer = len(v)
        v.append((cx, rings[2][0], WHEEL_R - sink * 0.5))
        for i in range(seg):
            j = (i + 1) % seg
            f.append((i, inner, j))
            f.append((seg * 2 + j, outer, seg * 2 + i))
        _obj("wst_car_tire", v, f, tire, par, smooth=True)
        # 轮毂：锈铁盘 + 5 个螺栓孔 + 中心小盖
        hv, hf = [], []
        sgn = 1.0 if cy > 0 else -1.0          # 轮毂朝车外
        hy = cy + sgn * (hw + 0.010)
        for i in range(14):
            a = 2 * math.pi * i / 14
            hv.append((cx + 0.62 * R * math.cos(a), hy, WHEEL_R + 0.62 * R * math.sin(a) - sink))
        hf.append(tuple(range(14)))
        _obj("wst_car_hub", hv, hf, hub, par)
        for i in range(5):
            a = 2 * math.pi * i / 5 + 0.3
            bx, bz = cx + 0.34 * R * math.cos(a), WHEEL_R + 0.34 * R * math.sin(a) - sink
            bv = [(bx + 0.022 * math.cos(t), hy + sgn * 0.004,
                   bz + 0.022 * math.sin(t)) for t in [2 * math.pi * k / 6 for k in range(6)]]
            _obj("wst_car_bolt", bv, [tuple(range(6))], opening, par)
        cv = [(cx + 0.15 * R * math.cos(t), hy + sgn * 0.006,
               WHEEL_R + 0.15 * R * math.sin(t) - sink) for t in [2 * math.pi * k / 12 for k in range(12)]]
        _obj("wst_car_hubcap", cv, [tuple(range(12))], chrome, par)

    for k, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)]):
        sink = 0.045 if (sx < 0 and sy < 0) else (0.018 if sx < 0 else 0.0)
        tire_at(WHEEL_X * sx, (WHEEL_HALF - 0.105) * sy, sink)

    # ---------- 保险杠（比车身窄、两端上翘）----------
    def bumper(name, x_face, sgn, z0, thick, half_y=0.855, curl=0.045):
        secs = 9
        v, f = [], []
        for i in range(secs):
            t = -1.0 + 2.0 * i / (secs - 1)
            y = t * half_y
            dx = curl * t * t
            dz = 0.018 * t * t
            for (ax, az) in ((-0.05, -thick * 0.5), (0.05, -thick * 0.5),
                             (0.05, thick * 0.5), (-0.05, thick * 0.5)):
                v.append((x_face + sgn * (dx + ax), y, z0 + dz + az))
        for i in range(secs - 1):
            a = i * 4
            for k in range(4):
                j = (k + 1) % 4
                f.append((a + k, a + j, a + 4 + j, a + 4 + k))
        f.append((0, 1, 2, 3))
        b = (secs - 1) * 4
        f.append((b + 3, b + 2, b + 1, b + 0))
        return _obj(name, v, f, rust, par)

    bumper("wst_car_bumper_f", 2.63, 1, 0.60, 0.135)
    bumper("wst_car_bumper_r", -2.66, -1, 0.64, 0.150)

    # 前保险杠上的灯位空洞（灯早没了）
    for sy in (1, -1):
        dv = [(2.672, 0.42 * sy + 0.055 * math.cos(t), 0.60 + 0.055 * math.sin(t))
              for t in [2 * math.pi * k / 8 for k in range(8)]]
        _obj("wst_car_bumphole_%d" % sy, dv, [tuple(range(8))], opening, par)

    # ---------- 格栅 / 大灯 / 尾灯 / 车牌框 ----------
    _box("wst_car_grille_frame", 2.55, 2.60, -0.58, 0.58, 0.70, 0.86, rust, par)
    for i in range(5):
        z = 0.705 + i * 0.032
        _box("wst_car_grille_%d" % i, 2.585, 2.605, -0.55, 0.55, z, z + 0.018, dark, par)

    for sy in (1, -1):
        cx, cz = 0.60 * sy, 0.79
        # 灯座：外圈锈环 + 内腔黑洞
        N = 16
        ang = [2 * math.pi * k / N for k in range(N)]
        ring = [(2.598, cx + 0.148 * math.cos(a), cz + 0.138 * math.sin(a)) for a in ang]
        ring += [(2.618, cx + 0.126 * math.cos(a), cz + 0.117 * math.sin(a)) for a in ang]
        rf = [(i, (i + 1) % N, N + (i + 1) % N, N + i) for i in range(N)]
        _obj("wst_car_lampring_%d" % sy, ring, rf, rust, par)
        cav = [(2.575, cx + 0.122 * math.cos(a), cz + 0.113 * math.sin(a)) for a in ang]
        _obj("wst_car_lamp_%d" % sy, cav, [tuple(range(N))], opening, par)

    for sy in (1, -1):
        y0, y1 = 0.42 * sy - 0.13, 0.42 * sy + 0.13
        _box("wst_car_tail_%d" % sy, -2.652, -2.640, y0, y1, 0.755, 0.855, opening, par)
        for k, (a0, a1, b0, b1) in enumerate(((y0 - 0.02, y1 + 0.02, 0.855, 0.875),
                                              (y0 - 0.02, y1 + 0.02, 0.735, 0.755),
                                              (y0 - 0.02, y0, 0.735, 0.875),
                                              (y1, y1 + 0.02, 0.735, 0.875))):
            _box("wst_car_tailring_%d_%d" % (sy, k), -2.658, -2.642, a0, a1, b0, b1, rust, par)
    # 尾箱盖缝（一条横向细缝）
    _box("wst_car_trunkseam", -1.90, -1.87, -0.80, 0.80, 0.968, 0.978, dark, par)
    # 车牌空框（车牌早没了，只剩四条锈边）
    _box("wst_car_plate_t", -2.68, -2.664, -0.245, 0.245, 0.648, 0.668, rust, par)
    _box("wst_car_plate_b", -2.68, -2.664, -0.245, 0.245, 0.498, 0.518, rust, par)
    _box("wst_car_plate_l", -2.68, -2.664, -0.245, -0.225, 0.518, 0.648, rust, par)
    _box("wst_car_plate_r", -2.68, -2.664, 0.225, 0.245, 0.518, 0.648, rust, par)
    # 后保险杠两端碎反光片
    for sy in (1, -1):
        _box("wst_car_reflect_%d" % sy, -2.735, -2.715, 0.72 * sy - 0.04, 0.72 * sy + 0.04,
             0.66, 0.71, glass, par)

    # ---------- 后视镜 / 排气 / 天线 / 门槛踏板 ----------
    _box("wst_car_mirror_arm", 0.86, 1.02, 0.90, 0.95, 1.03, 1.06, rust, par)
    _box("wst_car_mirror", 0.80, 0.98, 0.94, 1.02, 1.04, 1.14, paint, par)
    _tube_path([(-2.52, -0.44, 0.26), (-2.62, -0.45, 0.245), (-2.70, -0.46, 0.235)],
               [0.035, 0.032, 0.028], 6, hub, "wst_car_exhaust", par)
    # 车顶天线：歪掉、弯了
    _tube_path([(0.62, 0.55, 1.395), (0.60, 0.55, 1.55), (0.52, 0.56, 1.63), (0.44, 0.58, 1.66)],
               [0.011, 0.008, 0.006, 0.004], 6, rust, "wst_car_antenna", par)
    _box("wst_car_sill_l", -1.05, 1.0, 0.905, 0.945, 0.335, 0.40, rust, par)
    _box("wst_car_sill_r", -1.05, 1.0, -0.945, -0.905, 0.335, 0.40, rust, par)

    parts = len([o for o in bpy.data.objects
                 if o.name.startswith("wst_car_") and o.type == 'MESH'])
    merged = _merge_parts(par)
    # 合并后立刻刷新一次依赖图：同脚本内紧接着渲染时，父级变换才不会用到旧的单位矩阵
    bpy.context.view_layer.update()
    tris = sum(len(p.vertices) - 2 for o in bpy.data.objects
               if o.name.startswith("wst_car_") and o.type == 'MESH' and o.parent is par
               for p in o.data.polygons)
    print("CAR ok tris=%d objects=%d parts=%d merged=%d" % (
        tris, len([o for o in bpy.data.objects if o.name.startswith("wst_car_") and o.type == 'MESH']),
        parts, merged))


if __name__ == "__main__":
    build()
