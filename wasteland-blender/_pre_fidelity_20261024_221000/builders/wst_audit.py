# -*- coding: utf-8 -*-
"""交付前体检：面数预算 / 命名 / 材质 / 修改器 / 游离对象 / 原点位置。"""
import bpy, collections
from mathutils import Vector

BUDGET = {
    "terrain": 15000, "tree": 4000, "ruins": 25000, "car": 6000, "props": 5000,
}
TOTAL_BUDGET = 60000
VOLUMES = ("wst_volume_fog", "wst_volume_dust")


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def group_of(name):
    if name.startswith("wst_terrain"):
        return "terrain"
    if name.startswith("wst_bg_"):
        return "bg"
    if name.startswith("wst_tree"):
        return "tree"
    if name.startswith("wst_build") or name.startswith("wst_det") or name.startswith("wst_ruin"):
        return "ruins"
    if name.startswith("wst_car"):
        return "car"
    if name.startswith("wst_prop"):
        return "props"
    if name.startswith("wst_volume") or name.startswith("wst_dust"):
        return "volume"
    return "other"


def build(verbose=True):
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    g = collections.Counter()
    gn = collections.Counter()
    for o in meshes:
        g[group_of(o.name)] += tris(o)
        gn[group_of(o.name)] += 1
    total = sum(g.values())
    if verbose:
        print("=== 面数 ===")
        for k in sorted(g):
            bud = BUDGET.get(k)
            tag = "" if bud is None else (" OK" if g[k] <= bud else " 超预算 %d" % (g[k] - bud))
            print("  %-8s %6d tris  (%2d obj)%s" % (k, g[k], gn[k], tag))
        print("  %-8s %6d tris  %s" % ("total", total,
              "OK(<=%d)" % TOTAL_BUDGET if total <= TOTAL_BUDGET else "超预算 %d" % (total - TOTAL_BUDGET)))

        print("=== 材质 ===")
        nomat = [o.name for o in meshes if not o.data.materials]
        print("  无材质 mesh:", nomat if nomat else "无")
        ngon = [(o.name, p.index) for o in meshes for p in o.data.polygons if len(p.vertices) > 4]
        print("  N-gon:", "%d 个" % len(ngon) if ngon else "无")

        print("=== 修改器 ===")
        mods = [(o.name, [m.type for m in o.modifiers]) for o in meshes if o.modifiers]
        print("  待 Apply:", mods if mods else "无")

        print("=== 命名 / 层级 ===")
        bad = [o.name for o in meshes if not o.name.startswith("wst_")]
        print("  非 wst_ 前缀:", bad if bad else "无")
        loose = [o.name for o in meshes if not o.users_collection]
        print("  无集合:", loose if loose else "无")
        root = [o.name for o in bpy.context.scene.collection.objects if o.type == "MESH"]
        print("  根集合直接挂的 mesh:", root if root else "无")
        for c in bpy.data.collections:
            print("  coll %-22s %3d obj" % (c.name, len(c.objects)))

        print("=== 其他类型 ===")
        print("  灯光:", [o.name for o in bpy.data.objects if o.type == "LIGHT"])
        print("  相机:", [o.name for o in bpy.data.objects if o.type == "CAMERA"])
        print("  体积:", [o.name for o in meshes if o.name in VOLUMES])

        print("=== 世界包围盒 ===")
        vs = [o.matrix_world @ Vector(c) for o in meshes if o.name not in VOLUMES for c in o.bound_box]
        print("  x[%.1f,%.1f] y[%.1f,%.1f] z[%.1f,%.1f]" % (
            min(v.x for v in vs), max(v.x for v in vs), min(v.y for v in vs), max(v.y for v in vs),
            min(v.z for v in vs), max(v.z for v in vs)))
    return {"groups": dict(g), "total": total, "objects": len(meshes)}


if __name__ == "__main__":
    build()