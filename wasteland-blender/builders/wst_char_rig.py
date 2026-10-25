"""角色骨架 + 蒙皮：把 wst_char 的 123 个部件绑到一副人形骨架上。

约定与 wst_char.py 一致：角色面朝 -Y，+X 是角色左侧（所以 _1 → .L，_-1 → .R）。

两类蒙皮：
  soft —— 会弯曲的部件（躯干/头/手臂/衣裤/靴筒），走 Blender 骨骼热力自动权重；
  rigid —— 小配件（护目镜/背包/腰挂/眼睑/鞋带…），整体 100% 绑到单根骨骼，
           否则热力权重会把它们撕成两半。
热力权重对小而碎的网格经常报 "Bone Heat Weighting: failed"，自动回退到
「按到骨段距离反比」的手工权重。
"""

import bpy
import math
from mathutils import Vector

import wst_char as C

PREFIX = "wst_char_"
ARM_NAME = "wst_char_rig"
ARM_DATA = "wst_char_arm"
COL = "collection_character"

# 头部小件：整体跟着 head 走
HEAD_PARTS = ("cap", "cap_brim", "goggle", "hair_nape", "ear", "eye", "iris", "pupil",
              "lid_up", "lid_lo", "brow", "lip_up", "lip_low", "mouth_line", "nose",
              "nostril_wing", "scar")
# 背包/胸包/围巾等挂在上身的
CHEST_PARTS = ("pack_", "chest_bag", "neck_pouch", "neck_cord", "shirt_collar",
               "jacket_collar", "scarf_band")
# 腰带及腰挂
HIP_PARTS = ("belt", "buckle", "hip_pouch", "tool_pouch", "tool_knife",
             "canteen", "scarf_tail")
# 手上/脚上的小件
HAND_PARTS = ("knuckle", "thumb")
FOOT_PARTS = ("lace",)


def _side(name):
    """wst_char_xxx_-1 → ('xxx', '.R')；wst_char_xxx_1 → ('xxx', '.L')；无后缀 → ('xxx', '')"""
    body = name[len(PREFIX):]
    if body.endswith("_-1"):
        return body[:-3], ".R"
    if body.endswith("_1"):
        return body[:-2], ".L"
    return body, ""


def _bone_for(ob_name):
    """刚性部件该跟哪根骨；返回 None 表示走自动权重。"""
    base, side = _side(ob_name)
    if base.startswith(HEAD_PARTS):
        return "head"
    if base.startswith(CHEST_PARTS):
        return "chest"
    if base.startswith(HIP_PARTS):
        return "hips"
    if base.startswith(HAND_PARTS):
        return "hand" + side
    if base.startswith(FOOT_PARTS):
        return "foot" + side
    return None


# ============ 骨架 ============

def _bones():
    """(name, head, tail, parent, connected)"""
    L, R = 1, -1
    b = [
        ("hips", (0, 0, C.Z_HIP), (0, 0, C.Z_WAIST), None, False),
        ("spine", (0, 0, C.Z_WAIST), (0, -0.012, C.Z_CHEST), "hips", True),
        ("chest", (0, -0.012, C.Z_CHEST), (0, -0.020, C.Z_NECK), "spine", True),
        ("neck", (0, -0.020, C.Z_NECK), (0, -0.030, 1.500), "chest", True),
        ("head", (0, -0.030, 1.500), (0, -0.032, 1.700), "neck", True),
    ]
    for s, sfx in ((L, ".L"), (R, ".R")):
        sx = C.X_SHOULDER * s
        sh = Vector((C.SHOULDER.x * s, C.SHOULDER.y, C.SHOULDER.z))
        el = Vector((C.ELBOW.x * s, C.ELBOW.y, C.ELBOW.z))
        wr = Vector((C.WRIST.x * s, C.WRIST.y, C.WRIST.z))
        he = Vector((C.HAND_END.x * s, C.HAND_END.y, C.HAND_END.z))
        hip = Vector((C.HIP_J.x * s, C.HIP_J.y, C.HIP_J.z))
        kn = Vector((C.KNEE_J.x * s, C.KNEE_J.y, C.KNEE_J.z))
        an = Vector((C.ANKLE_J.x * s, C.ANKLE_J.y, C.ANKLE_J.z))
        toe = Vector((C.TOE_J.x * s, C.TOE_J.y, C.TOE_J.z))
        b += [
            ("shoulder" + sfx, (0.036 * s, -0.010, 1.396), tuple(sh), "chest", False),
            ("upper_arm" + sfx, tuple(sh), tuple(el), "shoulder" + sfx, True),
            ("forearm" + sfx, tuple(el), tuple(wr), "upper_arm" + sfx, True),
            ("hand" + sfx, tuple(wr), tuple(he), "forearm" + sfx, True),
            ("thigh" + sfx, tuple(hip), tuple(kn), "hips", False),
            ("shin" + sfx, tuple(kn), tuple(an), "thigh" + sfx, True),
            ("foot" + sfx, tuple(an), tuple(toe), "shin" + sfx, True),
            ("toe" + sfx, tuple(toe), (toe.x, toe.y - 0.052, toe.z - 0.006),
             "foot" + sfx, True),
        ]
    return b


def _make_armature():
    old = bpy.data.objects.get(ARM_NAME)
    if old is not None:
        data = old.data if old.type == 'ARMATURE' else None
        bpy.data.objects.remove(old, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.armatures.remove(data)
    arm = bpy.data.armatures.new(ARM_DATA)
    ob = bpy.data.objects.new(ARM_NAME, arm)
    col = bpy.data.collections.get(COL) or bpy.context.scene.collection
    col.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    made = {}
    for name, head, tail, parent, conn in _bones():
        eb = arm.edit_bones.new(name)
        eb.head = Vector(head)
        eb.tail = Vector(tail)
        eb.roll = 0.0
        made[name] = eb
        if parent:
            eb.parent = made[parent]
            eb.use_connect = bool(conn)
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'XYZ'
    return ob


# ============ 蒙皮 ============

def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (p - (a + ab * t)).length


def _manual_weights(ob, rig):
    """热力权重失败的兜底：按到骨段距离的 4 次方反比，取最近两根骨。"""
    segs = [(b.name, Vector(b.head_local), Vector(b.tail_local))
            for b in rig.data.bones if b.use_deform]
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    groups = {}
    mw = ob.matrix_world
    for v in ob.data.vertices:
        p = mw @ v.co
        cand = sorted(((_seg_dist(p, a, b), n) for n, a, b in segs))[:2]
        wsum = sum(1.0 / max(d, 1e-4) ** 4 for d, _n in cand)
        for d, n in cand:
            w = (1.0 / max(d, 1e-4) ** 4) / wsum
            if w < 0.02:
                continue
            g = groups.get(n)
            if g is None:
                g = groups[n] = ob.vertex_groups.new(name=n)
            g.add([v.index], w, 'REPLACE')


def _ensure_modifier(ob, rig):
    mod = next((m for m in ob.modifiers if m.type == 'ARMATURE'), None)
    if mod is None:
        mod = ob.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    mod.use_vertex_groups = True
    if ob.parent is None:
        ob.parent = rig
        ob.matrix_parent_inverse = rig.matrix_world.inverted()


def _rigid(ob, bone):
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    g = ob.vertex_groups.new(name=bone)
    g.add([v.index for v in ob.data.vertices], 1.0, 'REPLACE')


def build():
    """建骨架 + 蒙皮。必须在 wst_char.build() 之后调用（部件已存在）。"""
    meshes = [o for o in bpy.data.objects
              if o.type == 'MESH' and o.name.startswith(PREFIX)]
    if not meshes:
        raise RuntimeError("没有 wst_char_* 网格，先跑 wst_char.build()")
    rig = _make_armature()

    soft, rigid = [], []
    for ob in meshes:
        bone = _bone_for(ob.name)
        (rigid if bone else soft).append((ob, bone))

    for ob, bone in rigid:
        _rigid(ob, bone)
        _ensure_modifier(ob, rig)

    fails = []
    for ob, _b in soft:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        try:
            bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        except RuntimeError as e:
            fails.append((ob.name, str(e).splitlines()[0][:60]))
            _manual_weights(ob, rig)
            _ensure_modifier(ob, rig)
        else:
            _ensure_modifier(ob, rig)

    # 蒙皮后清一次父级变换偏移：部件位置原本就是世界坐标，父到骨架要保持原位
    for ob in meshes:
        if ob.parent is rig and ob.matrix_parent_inverse == rig.matrix_world.inverted():
            continue
    bpy.context.view_layer.update()
    return {
        "armature": rig.name,
        "bones": len(rig.data.bones),
        "deform_bones": len([b for b in rig.data.bones if b.use_deform]),
        "soft_parts": len(soft),
        "rigid_parts": len(rigid),
        "auto_failures": fails,
    }


BODY_NAME = "wst_char_body"


def join_body():
    """把 123 个部件合并成单网格：移动端每帧的 draw call 从 123 降到 10（按材质切）。"""
    rig = bpy.data.objects.get(ARM_NAME)
    parts = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(PREFIX)]
    if not parts:
        raise RuntimeError("没有可合并的 wst_char_* 网格")
    old = bpy.data.objects.get(BODY_NAME)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for ob in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    body = bpy.context.view_layer.objects.active
    body.name = BODY_NAME
    body.data.name = BODY_NAME
    if not any(m.type == 'ARMATURE' for m in body.modifiers):
        _ensure_modifier(body, rig)
    for m in body.modifiers:
        if m.type == 'ARMATURE':
            m.object = rig
    me = body.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    return {
        "mesh": body.name,
        "parts": len(parts),
        "verts": len(me.vertices),
        "tris": tris,
        "materials": len(me.materials),
        "vgroups": len(body.vertex_groups),
        "uv_layers": [l.name for l in me.uv_layers],
    }


def pose_test(bone_rot_deg, out_png=None):
    """临时摆个姿势验证权重：bone_rot_deg = {"upper_arm.L": (0, 0, -40), ...}"""
    rig = bpy.data.objects.get(ARM_NAME)
    if rig is None:
        raise RuntimeError("没有骨架")
    for pb in rig.pose.bones:
        pb.rotation_euler = (0.0, 0.0, 0.0)
    for name, rot in bone_rot_deg.items():
        pb = rig.pose.bones.get(name)
        if pb is None:
            continue
        pb.rotation_euler = tuple(math.radians(v) for v in rot)
    bpy.context.view_layer.update()
    if out_png:
        bpy.context.scene.render.filepath = out_png
        bpy.ops.render.render(write_still=True)
    return True


if __name__ == "__main__":
    print(build())
