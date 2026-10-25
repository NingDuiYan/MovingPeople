# -*- coding: utf-8 -*-
"""把废墟立面上的窗凹面染成"洞内暗部"。

原模型的窗只是立面脸上 0.1~0.3 m 的浅凹（_mask/_window_dress 在同一 mesh 里砌出来的），
材质仍是亮混凝土，远景读成"贴了几个灰方块"。这里不改几何，只把凹进去的那一面
（法线朝街、且比该处立面更深的面）换成近黑哑光材质 —— 视觉上就是一眼能看到底的黑窗洞。

立面 y 随 x 变化，深度判据用 wst_ruins_detail.SURF 的 front_y(x) 线性插值。
幂等：按材质槽检查，已经换过就跳过。
"""
import bpy

MAT_NAME = "wst_mat_opening"
FRONT = ((-15.0, 13.01), (-14.5, 11.00), (-14.0, 8.77), (-13.5, 7.15), (-13.0, 7.22),
         (-12.5, 7.34), (-12.0, 7.47), (-11.5, 7.60), (-11.0, 7.68), (-10.5, 7.85),
         (-10.0, 7.93), (-9.5, 8.09), (-9.0, 8.20), (-8.5, 8.34))
DEEPER_THAN = 0.09      # 比立面深 9 cm 以上才算"凹进去的面"


def _lerp(table, x):
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for (x0, v0), (x1, v1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def _material():
    mat = bpy.data.materials.get(MAT_NAME)
    if mat is None:
        mat = bpy.data.materials.new(MAT_NAME)
    if not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = (0.012, 0.011, 0.010, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.94
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build(obj_name="wst_build_wall_left"):
    ob = bpy.data.objects.get(obj_name)
    if ob is None:
        return {"error": "missing " + obj_name}
    mat = _material()
    if mat.name not in [s.material.name for s in ob.material_slots if s.material]:
        ob.data.materials.append(mat)
    slot = [i for i, s in enumerate(ob.material_slots) if s.material and s.material.name == MAT_NAME][0]
    mw = ob.matrix_world
    rot = mw.to_3x3()
    n = 0
    for p in ob.data.polygons:
        nrm = (rot @ p.normal).normalized()
        if nrm.y > -0.5:
            continue
        c = mw @ p.center
        if c.y > _lerp(FRONT, c.x) + DEEPER_THAN:
            p.material_index = slot
            n += 1
    ob.data.update()
    return {"recess_faces": n, "slot": slot}


if __name__ == "__main__":
    print(build())
