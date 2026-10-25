# -*- coding: utf-8 -*-
"""交付前清理：残留体积对象、集合归属、N-gon 三角化、远地面减面。

可重复执行（幂等）。
"""
import bpy, bmesh

FX_COLL = "collection_lighting"
TRI_COLL = "collection_terrain"
DUST_NAMES = ("wst_volume_dust", "wst_dust_")
FAR_GROUND = "wst_terrain_ground_far"
FAR_BUDGET = 900


def _mesh_objects():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def dedupe_dust():
    """_plume() 每跑一次都会新建对象，历史上留下了 .001/.002 之类的残骸。"""
    keep = None
    removed = []
    for o in list(_mesh_objects()):
        if any(o.name.startswith(p) for p in DUST_NAMES):
            if keep is None and o.name == "wst_volume_dust":
                keep = o
            else:
                removed.append(o.name)
                bpy.data.objects.remove(o, do_unlink=True)
    return {"kept": keep.name if keep else None, "removed": removed}


def fix_collections():
    moved = []
    fx = bpy.data.collections.get(FX_COLL)
    if fx is None:
        fx = bpy.data.collections.new(FX_COLL)
        bpy.context.scene.collection.children.link(fx)
    terr = bpy.data.collections.get(TRI_COLL)
    for name in ("wst_bg_ridge_01", "wst_bg_ridge_02"):
        o = bpy.data.objects.get(name)
        if o and terr and terr not in o.users_collection:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            terr.objects.link(o)
            moved.append(name)
    for name in ("wst_light_sun", "wst_light_fill", "wst_cam_main", "wst_volume_fog",
                 "wst_volume_dust"):
        o = bpy.data.objects.get(name)
        if o and fx not in o.users_collection:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            fx.objects.link(o)
            moved.append(name)
    return moved


def triangulate_ngons():
    report = []
    for o in _mesh_objects():
        ng = [p for p in o.data.polygons if len(p.vertices) > 4]
        if not ng:
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        faces = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=faces, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()
        report.append((o.name, len(faces)))
    return report


def decimate_far_ground():
    o = bpy.data.objects.get(FAR_GROUND)
    if o is None:
        return None
    before = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if before <= FAR_BUDGET:
        return {"obj": FAR_GROUND, "tris": before, "action": "skip"}
    mod = o.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = FAR_BUDGET / float(before)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=mod.name)
    after = sum(len(p.vertices) - 2 for p in o.data.polygons)
    return {"obj": FAR_GROUND, "before": before, "after": after}


def build():
    r = {}
    r["dust"] = dedupe_dust()
    r["moved"] = fix_collections()
    r["ngons"] = triangulate_ngons()
    r["far_ground"] = decimate_far_ground()
    return r


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False))