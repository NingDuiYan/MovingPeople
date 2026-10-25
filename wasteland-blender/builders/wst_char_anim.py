"""角色动作库：给 wst_char_rig 的骨架生成 glTF 可导出的动作（Action）。

坐标约定（实测自 wst_char_rig，角色面朝 -Y）：
  · 四肢的 X 轴 = 前后摆动：负值向前、正值向后（左右同号）。
  · Z 轴是世界偏航方向：左臂 +Z 贴身、右臂 +Z 张开，所以左右要用相反符号。
  · chest / head 的 X 正值 = 前俯 / 低头。
  · hips 骨朝上，局部 Y = 世界 Z → hips 的 Y 旋转就是转身；
    hips 的 location.y 负值 = 整体下沉（下蹲）。

每个动作都推到一个 NLA 轨道上（muted），glTF 用 ACTIONS 模式导出时
才能把整套动作都带上；只靠 animation_data.action 只会导出最后一个。
"""

import bpy
import math

RIG_NAME = "wst_char_rig"
FPS = 24


def _rig():
    rig = bpy.data.objects.get(RIG_NAME)
    if rig is None:
        raise RuntimeError("没有 wst_char_rig，先跑 wst_char_rig.build()")
    return rig


def _clear_pose(rig):
    for pb in rig.pose.bones:
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def _key(rig, frame, pose):
    """pose = {bone: {"rot": (x,y,z) 度, "loc": (x,y,z) 米}}"""
    for pb in rig.pose.bones:
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
    for name, spec in pose.items():
        pb = rig.pose.bones.get(name)
        if pb is None:
            continue
        rot = spec.get("rot")
        if rot:
            pb.rotation_euler = tuple(math.radians(v) for v in rot)
        loc = spec.get("loc")
        if loc:
            pb.location = tuple(loc)
    for pb in rig.pose.bones:
        pb.keyframe_insert("rotation_euler", frame=frame)
        pb.keyframe_insert("location", frame=frame)


def _fcurves(act):
    """Blender 5 的 Action 是分层/分槽结构，fcurves 不再挂在 action 上。"""
    out = []
    fcs = getattr(act, "fcurves", None)
    if fcs is not None:
        return list(fcs)
    for layer in getattr(act, "layers", []):
        for strip in getattr(layer, "strips", []):
            for cbag in getattr(strip, "channelbags", []):
                out.extend(cbag.fcurves)
    return out


def _action(rig, name, keys, loop=True):
    """keys = [(frame, pose), ...]；返回 action。"""
    act = bpy.data.actions.get(name)
    if act is not None:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if rig.animation_data is None:
        rig.animation_data_create()
    rig.animation_data.action = act
    for frame, pose in keys:
        _key(rig, frame, pose)
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
    if loop and hasattr(act, "use_cyclic"):
        act.use_cyclic = True
    rig.animation_data.action = None
    return act


def _stash(rig, act):
    """推到 NLA（muted），否则 glTF 只会导出当前 action。"""
    ad = rig.animation_data or rig.animation_data_create()
    track = ad.nla_tracks.get(act.name)
    if track is None:
        track = ad.nla_tracks.new()
        track.name = act.name
    for st in list(track.strips):
        track.strips.remove(st)
    strip = track.strips.new(act.name, 1, act)
    strip.name = act.name
    track.mute = True
    return track


# ============ 姿势片段 ============

def _walk_contact(front, back, s):
    """front = "L"/"R"：哪条腿在前。s = 摆幅（弧度制的度数比例）。"""
    f, b = ("L", "R") if front == "L" else ("R", "L")
    sgn = 1.0 if front == "L" else -1.0
    return {
        "hips": {"rot": (0, 3.0 * sgn * s, 0), "loc": (0, -0.012 * s, 0)},
        "chest": {"rot": (2.0 * s, -2.0 * sgn * s, 0)},
        "thigh." + f: {"rot": (-24.0 * s, 0, 0)},
        "shin." + f: {"rot": (8.0 * s, 0, 0)},
        "foot." + f: {"rot": (-6.0 * s, 0, 0)},
        "thigh." + b: {"rot": (18.0 * s, 0, 0)},
        "shin." + b: {"rot": (22.0 * s, 0, 0)},
        "foot." + b: {"rot": (14.0 * s, 0, 0)},
        "toe." + b: {"rot": (-18.0 * s, 0, 0)},
        "upper_arm." + b: {"rot": (-22.0 * s, 0, 0)},
        "forearm." + b: {"rot": (-26.0 * s, 0, 0)},
        "upper_arm." + f: {"rot": (20.0 * s, 0, 0)},
        "forearm." + f: {"rot": (-10.0 * s, 0, 0)},
    }


def _walk_pass(up, down, s):
    """up = 抬起的腿；down = 支撑腿。"""
    u, d = up, down
    sgn = 1.0 if up == "L" else -1.0
    return {
        "hips": {"rot": (0, 0.5 * sgn * s, 0), "loc": (0, 0.010 * s, 0)},
        "thigh." + u: {"rot": (-6.0 * s, 0, 0)},
        "shin." + u: {"rot": (40.0 * s, 0, 0)},
        "foot." + u: {"rot": (10.0 * s, 0, 0)},
        "thigh." + d: {"rot": (2.0 * s, 0, 0)},
        "shin." + d: {"rot": (5.0 * s, 0, 0)},
        "upper_arm." + u: {"rot": (-4.0 * s, 0, 0)},
        "forearm." + u: {"rot": (-20.0 * s, 0, 0)},
        "upper_arm." + d: {"rot": (2.0 * s, 0, 0)},
        "forearm." + d: {"rot": (-16.0 * s, 0, 0)},
    }


def _crouch_base(depth=1.0):
    """下蹲的静态底：膝盖前屈 + 髋下沉 + 上身略前俯。"""
    return {
        "hips": {"rot": (4.0 * depth, 0, 0), "loc": (0, -0.185 * depth, 0)},
        "chest": {"rot": (12.0 * depth, 0, 0)},
        "head": {"rot": (-8.0 * depth, 0, 0)},
        "thigh.L": {"rot": (-52.0 * depth, 0, 4.0)},
        "thigh.R": {"rot": (-52.0 * depth, 0, -4.0)},
        "shin.L": {"rot": (74.0 * depth, 0, 0)},
        "shin.R": {"rot": (74.0 * depth, 0, 0)},
        "foot.L": {"rot": (-28.0 * depth, 0, 0)},
        "foot.R": {"rot": (-28.0 * depth, 0, 0)},
        "upper_arm.L": {"rot": (-16.0, 0, 6.0)},
        "upper_arm.R": {"rot": (-16.0, 0, -6.0)},
        "forearm.L": {"rot": (-42.0, 0, 0)},
        "forearm.R": {"rot": (-42.0, 0, 0)},
    }


def _merge(a, b):
    out = {k: dict(v) for k, v in a.items()}
    for k, v in b.items():
        out.setdefault(k, {}).update(v)
    return out


# ============ 各动作 ============

def _a_idle(rig):
    base = {
        "chest": {"rot": (2.0, 0, 0)},
        "upper_arm.L": {"rot": (-2.0, 0, 3.0)},
        "upper_arm.R": {"rot": (-2.0, 0, -3.0)},
        "forearm.L": {"rot": (-14.0, 0, 0)},
        "forearm.R": {"rot": (-14.0, 0, 0)},
    }
    breathe = _merge(base, {
        "chest": {"rot": (0.5, 0, 0)},
        "hips": {"rot": (0, 1.2, 0), "loc": (0, -0.008, 0)},
        "head": {"rot": (1.5, 2.0, 0)},
    })
    return _action(rig, "idle", [(1, base), (30, breathe), (60, base)])


def _a_walk(rig):
    keys = [
        (1, _walk_contact("L", "R", 1.0)),
        (9, _walk_pass("R", "L", 1.0)),
        (17, _walk_contact("R", "L", 1.0)),
        (25, _walk_pass("L", "R", 1.0)),
        (33, _walk_contact("L", "R", 1.0)),
    ]
    return _action(rig, "walk", keys)


def _a_run(rig):
    lean = {"chest": {"rot": (12.0, 0, 0)}, "head": {"rot": (-8.0, 0, 0)}}
    a = _merge(_walk_contact("L", "R", 1.9), lean)
    b = _merge(_walk_pass("R", "L", 1.9), lean)
    c = _merge(_walk_contact("R", "L", 1.9), lean)
    d = _merge(_walk_pass("L", "R", 1.9), lean)
    a["hips"]["loc"] = (0, -0.030, 0)
    c["hips"]["loc"] = (0, -0.030, 0)
    b["hips"]["loc"] = (0, 0.028, 0)
    d["hips"]["loc"] = (0, 0.028, 0)
    keys = [(1, a), (6, b), (11, c), (16, d), (21, a)]
    return _action(rig, "run", keys)


def _a_jump(rig):
    stand = {
        "upper_arm.L": {"rot": (-2.0, 0, 3.0)}, "upper_arm.R": {"rot": (-2.0, 0, -3.0)},
        "forearm.L": {"rot": (-14.0, 0, 0)}, "forearm.R": {"rot": (-14.0, 0, 0)},
    }
    load = {
        "hips": {"rot": (6.0, 0, 0), "loc": (0, -0.16, 0)},
        "chest": {"rot": (18.0, 0, 0)},
        "thigh.L": {"rot": (-46.0, 0, 3.0)}, "thigh.R": {"rot": (-46.0, 0, -3.0)},
        "shin.L": {"rot": (66.0, 0, 0)}, "shin.R": {"rot": (66.0, 0, 0)},
        "foot.L": {"rot": (-24.0, 0, 0)}, "foot.R": {"rot": (-24.0, 0, 0)},
        "upper_arm.L": {"rot": (34.0, 0, 8.0)}, "upper_arm.R": {"rot": (34.0, 0, -8.0)},
        "forearm.L": {"rot": (-24.0, 0, 0)}, "forearm.R": {"rot": (-24.0, 0, 0)},
    }
    launch = {
        "hips": {"rot": (-4.0, 0, 0), "loc": (0, 0.05, 0)},
        "chest": {"rot": (-6.0, 0, 0)},
        "thigh.L": {"rot": (10.0, 0, 3.0)}, "thigh.R": {"rot": (10.0, 0, -3.0)},
        "shin.L": {"rot": (4.0, 0, 0)}, "shin.R": {"rot": (4.0, 0, 0)},
        "foot.L": {"rot": (28.0, 0, 0)}, "foot.R": {"rot": (28.0, 0, 0)},
        "toe.L": {"rot": (-24.0, 0, 0)}, "toe.R": {"rot": (-24.0, 0, 0)},
        "upper_arm.L": {"rot": (-64.0, 0, 10.0)}, "upper_arm.R": {"rot": (-64.0, 0, -10.0)},
        "forearm.L": {"rot": (-20.0, 0, 0)}, "forearm.R": {"rot": (-20.0, 0, 0)},
    }
    air = {
        "hips": {"rot": (2.0, 0, 0), "loc": (0, 0.02, 0)},
        "chest": {"rot": (6.0, 0, 0)},
        "thigh.L": {"rot": (-34.0, 0, 4.0)}, "thigh.R": {"rot": (-14.0, 0, -4.0)},
        "shin.L": {"rot": (52.0, 0, 0)}, "shin.R": {"rot": (24.0, 0, 0)},
        "upper_arm.L": {"rot": (-36.0, 0, 14.0)}, "upper_arm.R": {"rot": (-36.0, 0, -14.0)},
        "forearm.L": {"rot": (-34.0, 0, 0)}, "forearm.R": {"rot": (-34.0, 0, 0)},
    }
    land = {
        "hips": {"rot": (8.0, 0, 0), "loc": (0, -0.20, 0)},
        "chest": {"rot": (22.0, 0, 0)},
        "thigh.L": {"rot": (-58.0, 0, 4.0)}, "thigh.R": {"rot": (-58.0, 0, -4.0)},
        "shin.L": {"rot": (80.0, 0, 0)}, "shin.R": {"rot": (80.0, 0, 0)},
        "foot.L": {"rot": (-30.0, 0, 0)}, "foot.R": {"rot": (-30.0, 0, 0)},
        "upper_arm.L": {"rot": (-26.0, 0, 18.0)}, "upper_arm.R": {"rot": (-26.0, 0, -18.0)},
        "forearm.L": {"rot": (-40.0, 0, 0)}, "forearm.R": {"rot": (-40.0, 0, 0)},
    }
    keys = [(1, stand), (7, load), (12, launch), (20, air), (27, land), (38, land), (46, stand)]
    return _action(rig, "jump", keys, loop=False)


def _a_crouch_idle(rig):
    base = _crouch_base(1.0)
    breath = _merge(base, {
        "hips": {"rot": (4.0, 0, 0), "loc": (0, -0.178, 0)},
        "chest": {"rot": (10.0, 0, 0)},
        "head": {"rot": (-6.0, 3.0, 0)},
    })
    return _action(rig, "crouch_idle", [(1, base), (30, breath), (60, base)])


def _a_crouch_walk(rig):
    def step(front):
        f, b = ("L", "R") if front == "L" else ("R", "L")
        sgn = 1.0 if front == "L" else -1.0
        return _merge(_crouch_base(1.0), {
            "hips": {"rot": (5.0, 3.0 * sgn, 0), "loc": (0, -0.185, 0)},
            "thigh." + f: {"rot": (-72.0, 0, 4.0)},
            "shin." + f: {"rot": (78.0, 0, 0)},
            "foot." + f: {"rot": (-20.0, 0, 0)},
            "thigh." + b: {"rot": (-36.0, 0, 4.0)},
            "shin." + b: {"rot": (70.0, 0, 0)},
            "foot." + b: {"rot": (-32.0, 0, 0)},
            "upper_arm." + f: {"rot": (-8.0, 0, 6.0)},
            "upper_arm." + b: {"rot": (-24.0, 0, 6.0)},
        })
    keys = [(1, step("L")), (15, step("R")), (29, step("L"))]
    return _action(rig, "crouch_walk", keys)


def _a_sneak(rig):
    def step(front):
        f, b = ("L", "R") if front == "L" else ("R", "L")
        return _merge(_crouch_base(1.15), {
            "hips": {"rot": (8.0, 0, 0), "loc": (0, -0.20, 0)},
            "chest": {"rot": (16.0, 0, 0)},
            "head": {"rot": (-12.0, 0, 0)},
            "thigh." + f: {"rot": (-84.0, 0, 3.0)},
            "shin." + f: {"rot": (84.0, 0, 0)},
            "thigh." + b: {"rot": (-44.0, 0, 3.0)},
            "shin." + b: {"rot": (76.0, 0, 0)},
            "upper_arm." + f: {"rot": (-30.0, 0, 8.0)},
            "forearm." + f: {"rot": (-58.0, 0, 0)},
            "upper_arm." + b: {"rot": (-46.0, 0, 8.0)},
            "forearm." + b: {"rot": (-64.0, 0, 0)},
        })
    keys = [(1, step("L")), (21, step("R")), (41, step("L"))]
    return _action(rig, "sneak", keys)


def _guard():
    return {
        "hips": {"rot": (2.0, 0, 0), "loc": (0, -0.03, 0)},
        "chest": {"rot": (6.0, -8.0, 0)},
        "head": {"rot": (-4.0, 8.0, 0)},
        "upper_arm.L": {"rot": (-34.0, 0, 16.0)},
        "forearm.L": {"rot": (-84.0, 0, 0)},
        "upper_arm.R": {"rot": (-40.0, 0, -18.0)},
        "forearm.R": {"rot": (-92.0, 0, 0)},
        "thigh.L": {"rot": (-14.0, 0, 4.0)},
        "thigh.R": {"rot": (-6.0, 0, -6.0)},
        "shin.L": {"rot": (18.0, 0, 0)},
        "shin.R": {"rot": (12.0, 0, 0)},
    }


def _a_punch1(rig):
    """左刺拳：快出快收。"""
    g = _guard()
    wind = _merge(g, {
        "chest": {"rot": (6.0, 6.0, 0)},
        "upper_arm.L": {"rot": (-16.0, 0, 12.0)},
        "forearm.L": {"rot": (-104.0, 0, 0)},
    })
    hit = _merge(g, {
        "hips": {"rot": (2.0, -10.0, 0), "loc": (0, -0.03, 0)},
        "chest": {"rot": (8.0, -18.0, 0)},
        "upper_arm.L": {"rot": (-88.0, 0, 6.0)},
        "forearm.L": {"rot": (-6.0, 0, 0)},
        "upper_arm.R": {"rot": (-30.0, 0, -20.0)},
        "forearm.R": {"rot": (-104.0, 0, 0)},
    })
    keys = [(1, g), (5, wind), (9, hit), (14, wind), (20, g)]
    return _action(rig, "punch1", keys, loop=False)


def _a_punch2(rig):
    """右直拳：转髋带动。"""
    g = _guard()
    wind = _merge(g, {
        "hips": {"rot": (2.0, -8.0, 0), "loc": (0, -0.03, 0)},
        "chest": {"rot": (6.0, -12.0, 0)},
        "upper_arm.R": {"rot": (-14.0, 0, -14.0)},
        "forearm.R": {"rot": (-110.0, 0, 0)},
    })
    hit = _merge(g, {
        "hips": {"rot": (2.0, 16.0, 0), "loc": (0, -0.04, 0)},
        "chest": {"rot": (10.0, 26.0, 0)},
        "head": {"rot": (-2.0, -10.0, 0)},
        "upper_arm.R": {"rot": (-94.0, 0, -4.0)},
        "forearm.R": {"rot": (-8.0, 0, 0)},
        "upper_arm.L": {"rot": (-20.0, 0, 14.0)},
        "forearm.L": {"rot": (-110.0, 0, 0)},
        "thigh.R": {"rot": (-2.0, 0, -6.0)},
        "shin.R": {"rot": (26.0, 0, 0)},
    })
    keys = [(1, g), (6, wind), (11, hit), (16, wind), (24, g)]
    return _action(rig, "punch2", keys, loop=False)


def _a_punch3(rig):
    """左勾拳：肘部抬起，走横向弧线。"""
    g = _guard()
    wind = _merge(g, {
        "hips": {"rot": (2.0, -14.0, 0)},
        "chest": {"rot": (6.0, -22.0, 0)},
        "upper_arm.L": {"rot": (-40.0, 0, -24.0)},
        "forearm.L": {"rot": (-96.0, 0, 0)},
    })
    hit = _merge(g, {
        "hips": {"rot": (2.0, 12.0, 0), "loc": (0, -0.04, 0)},
        "chest": {"rot": (8.0, 22.0, 0)},
        "upper_arm.L": {"rot": (-58.0, 0, 30.0)},
        "forearm.L": {"rot": (-28.0, 0, 0)},
        "upper_arm.R": {"rot": (-28.0, 0, -22.0)},
        "forearm.R": {"rot": (-102.0, 0, 0)},
    })
    keys = [(1, g), (7, wind), (12, hit), (18, wind), (26, g)]
    return _action(rig, "punch3", keys, loop=False)


def _a_punch4(rig):
    """第四段：转身右高扫腿（腿部重击）。"""
    g = _guard()
    load = _merge(g, {
        "hips": {"rot": (2.0, -26.0, 0), "loc": (0, -0.075, 0)},
        "chest": {"rot": (10.0, -18.0, 0)},
        "thigh.R": {"rot": (-32.0, 0, -12.0)},
        "shin.R": {"rot": (54.0, 0, 0)},
        "upper_arm.L": {"rot": (-40.0, 0, 24.0)},
        "forearm.L": {"rot": (-96.0, 0, 0)},
        "upper_arm.R": {"rot": (-46.0, 0, -26.0)},
        "forearm.R": {"rot": (-100.0, 0, 0)},
    })
    kick = {
        "hips": {"rot": (-4.0, 40.0, 0), "loc": (0, -0.02, 0)},
        "chest": {"rot": (2.0, 34.0, 0)},
        "head": {"rot": (-6.0, -16.0, 0)},
        "thigh.R": {"rot": (-72.0, 0, -46.0)},
        "shin.R": {"rot": (18.0, 0, 0)},
        "foot.R": {"rot": (16.0, 0, 0)},
        "thigh.L": {"rot": (-8.0, 0, 6.0)},
        "shin.L": {"rot": (14.0, 0, 0)},
        "upper_arm.L": {"rot": (-30.0, 0, 40.0)},
        "forearm.L": {"rot": (-64.0, 0, 0)},
        "upper_arm.R": {"rot": (14.0, 0, -34.0)},
        "forearm.R": {"rot": (-58.0, 0, 0)},
    }
    land = _merge(g, {
        "hips": {"rot": (4.0, 18.0, 0), "loc": (0, -0.09, 0)},
        "chest": {"rot": (10.0, 14.0, 0)},
        "thigh.R": {"rot": (-36.0, 0, -8.0)},
        "shin.R": {"rot": (40.0, 0, 0)},
    })
    keys = [(1, g), (8, load), (16, kick), (24, land), (34, g)]
    return _action(rig, "punch4", keys, loop=False)


def _a_block(rig):
    """双臂抬起护住头面。"""
    g = {
        "hips": {"rot": (4.0, 0, 0), "loc": (0, -0.06, 0)},
        "chest": {"rot": (14.0, 0, 0)},
        "head": {"rot": (6.0, 0, 0)},
        "thigh.L": {"rot": (-22.0, 0, 4.0)},
        "thigh.R": {"rot": (-16.0, 0, -6.0)},
        "shin.L": {"rot": (32.0, 0, 0)},
        "shin.R": {"rot": (26.0, 0, 0)},
        "foot.L": {"rot": (-12.0, 0, 0)},
        "foot.R": {"rot": (-10.0, 0, 0)},
        # 拳击护架：上臂基本垂下、只往前带一点，肘部折起来把小臂竖在胸前。
        # 之前 upper_arm X=-96 把两只上臂抬到肩高再往外张，正面看像"举手投降"。
        "upper_arm.L": {"rot": (-20.0, 0, 14.0)},
        "forearm.L": {"rot": (-100.0, 0, 6.0)},
        "upper_arm.R": {"rot": (-24.0, 0, -16.0)},
        "forearm.R": {"rot": (-104.0, 0, -6.0)},
        "shoulder.L": {"rot": (-6.0, 0, 4.0)},
        "shoulder.R": {"rot": (-6.0, 0, -4.0)},
    }
    tight = _merge(g, {
        "hips": {"rot": (5.0, 0, 0), "loc": (0, -0.072, 0)},
        "chest": {"rot": (17.0, 0, 0)},
        "forearm.L": {"rot": (-110.0, 0, 0)},
        "forearm.R": {"rot": (-110.0, 0, 0)},
    })
    return _action(rig, "block", [(1, g), (8, tight), (16, g)])


ACTIONS = ("idle", "walk", "run", "jump", "crouch_idle", "crouch_walk", "sneak",
           "punch1", "punch2", "punch3", "punch4", "block")


def build():
    rig = _rig()
    _clear_pose(rig)
    if rig.animation_data is None:
        rig.animation_data_create()
    for name in list(rig.animation_data.nla_tracks.keys()):
        rig.animation_data.nla_tracks.remove(rig.animation_data.nla_tracks[name])
    made = []
    for fn in (_a_idle, _a_walk, _a_run, _a_jump, _a_crouch_idle, _a_crouch_walk,
               _a_sneak, _a_punch1, _a_punch2, _a_punch3, _a_punch4, _a_block):
        act = fn(rig)
        _stash(rig, act)
        made.append((act.name, int(act.frame_range[0]), int(act.frame_range[1])))
    rig.animation_data.action = None
    _clear_pose(rig)
    bpy.context.view_layer.update()
    bpy.context.scene.render.fps = FPS
    return {"fps": FPS, "actions": made, "count": len(made)}


def play(name, frame=None):
    """把某个动作设为当前 action，便于渲图检查。"""
    rig = _rig()
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError("没有动作 " + name)
    if rig.animation_data is None:
        rig.animation_data_create()
    rig.animation_data.action = act
    if frame is not None:
        bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return True
