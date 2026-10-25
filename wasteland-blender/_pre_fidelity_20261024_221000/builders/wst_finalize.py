# -*- coding: utf-8 -*-
"""一键把场景收敛到交付状态（幂等，可重复执行）。

顺序有讲究：
  1) 重建枯树 → 顶点级等比缩放到目标高度 → 三角化（重建会重新引入 N-gon）
  2) 砖材褪色（wst_mat_brick 太红，远看像一堆红砖而非晒白的碎砖）
  3) 废墟窗凹改暗（见 wst_ruins_windows.py）
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
import wst_ruins_windows
import wst_tree_spec

for _m in (wst_tree_spec, wst_ruins_windows, wst_cleanup):
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


def build():
    report = {}
    # v2: 按"枯树_纯视觉描述.md"的规格表重建（v1 的递归生长已停用）
    report["tree"] = wst_tree_spec.build()
    bpy.context.view_layer.update()
    report["tree_height"] = resize_tree()
    wst_cleanup.triangulate_ngons()
    report["brick_faded"] = fade_brick()
    report["wall_windows"] = wst_ruins_windows.build("wst_build_wall_left")
    report["cleanup"] = wst_cleanup.build()
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False, default=str))
