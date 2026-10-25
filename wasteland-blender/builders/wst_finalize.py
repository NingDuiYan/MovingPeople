# -*- coding: utf-8 -*-
"""一键把场景收敛到交付状态（幂等，可重复执行）。

顺序有讲究：
  1) 重建枯树 → 顶点级等比缩放到目标高度 → 三角化（重建会重新引入 N-gon）
     1b) 根盘四周的土隆起 / 放射裂缝（wst_root_heave，必须在缩放之后）
  1c) 沙地材质补丁 + 亮度系数（wst_ground，与参考图取色对齐）
     1d) 干裂板块贴图 + 世界坐标立方 UV（wst_ground_tex，GLB 里唯一的地面细节来源）
  2) 砖材褪色（wst_mat_brick 太红，远看像一堆红砖而非晒白的碎砖）
  3) 废墟窗凹改暗（见 wst_ruins_windows.py）
  3b) 废墟表面侵蚀（wst_ruins_erode：把"薄板 + 直角台阶"打成崩口）
  4) 清理（重复的体积尘、集合归位、远景地面抽面）
  5) 体检

为什么不直接改 .blend：所有几何都由 builders/ 下的脚本生成，脚本是唯一事实来源，
改完重新跑一遍就能得到同样的场景。
"""
import importlib
import sys

import bpy
from mathutils import Vector

BUILDERS = r"C:\Users\ning\Desktop\MovingPeople\wasteland-blender\builders"
if BUILDERS not in sys.path:
    sys.path.insert(0, BUILDERS)

import wst_cleanup
import wst_external
import wst_ground
import wst_ground_tex
import wst_root_heave
import wst_ruins_erode
import wst_ruins_windows
import wst_tree_spec

for _m in (wst_tree_spec, wst_root_heave, wst_ruins_windows, wst_ruins_erode,
           wst_ground, wst_ground_tex, wst_cleanup, wst_external):
    importlib.reload(_m)

TREE_HEIGHT = 5.10
TREE_PREFIX = "wst_tree"

# 砖：原来的 (0.205,0.087,0.063)/(0.332,0.147,0.102) 偏红，改成晒白的土坯砖
BRICK_RAMP = ((0.150, 0.108, 0.085, 1.0), (0.245, 0.180, 0.140, 1.0))


def resize_tree(target=TREE_HEIGHT):
    """顶点级等比缩放（不动对象变换：树由 5 个对象组成，各自原点不同）。"""
    objs = [o for o in bpy.data.objects if o.name.startswith(TREE_PREFIX)]
    pts = [(o.matrix_world @ Vector(c)) for o in objs for c in o.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    pivot = Vector(((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, 0.0))
    s = target / max(zs)
    for o in objs:
        m = o.matrix_world.copy()
        mi = m.inverted()
        for v in o.data.vertices:
            v.co = mi @ (pivot + (m @ v.co - pivot) * s)
        o.data.update()
    return round(max(zs) * s, 3)


def fade_brick():
    mat = bpy.data.materials.get("wst_mat_brick")
    if mat is None:
        return False
    ramp = next((n for n in mat.node_tree.nodes
                 if n.bl_idname == "ShaderNodeValToRGB"), None)
    if ramp is None:
        return False
    for el, col in zip(ramp.color_ramp.elements, BRICK_RAMP):
        el.color = col
    return True


def build(external=True):
    """external=True 时树 / 车 / 废墟来自 Tripo GLB（见 wst_external.py）。

    程序化版本（含 v2 树、废墟窗凹、侵蚀）保留在 external=False 分支里，
    作为没有外部资产时的退路，不再进入交付链路。
    """
    report = {}
    if external:
        # 外部资产自带的细节已足够，程序化的树 / 车 / 废墟被它取代并删除
        report["external"] = wst_external.build()
    else:
        # v2: 按"枯树_纯视觉描述.md"的规格表重建（v1 的递归生长已停用）
        report["tree"] = wst_tree_spec.build()
        bpy.context.view_layer.update()
        report["tree_height"] = resize_tree()
    # 根盘周围的"土被根顶起"隆起 + 放射裂缝：外部树的根盘在同一位置，
    # 射线取地面高度时不会被树干挡住；wst_cleanup 不会动它。
    report["root_heave"] = wst_root_heave.build()
    # 沙地材质补丁（灰褐板块 + 亮度系数），可重复执行
    report["ground"] = wst_ground.build()
    # 干裂板块贴图：必须在 wst_ground 之后（它接管 Base Color），否则被程序化补丁覆盖
    report["ground_tex"] = wst_ground_tex.build()
    wst_cleanup.triangulate_ngons()
    if not external:
        report["brick_faded"] = fade_brick()
        report["wall_windows"] = wst_ruins_windows.build("wst_build_wall_left")
        # 侵蚀必须排在窗凹之后（窗凹动的是面材质，侵蚀动的是顶点），且在 cleanup 之前
        report["ruin_erode"] = wst_ruins_erode.build()
    report["cleanup"] = wst_cleanup.build()
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False, default=str))
