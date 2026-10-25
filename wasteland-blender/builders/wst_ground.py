# -*- coding: utf-8 -*-
"""地面色块：在 wst_mat_sand 的最终 Base Color 前插入一层"大尺度板块"混色。

参考图的地面不是一个橙色，而是"灰褐干裂板块 + 暖色浮沙"交错，
所以用两个低频 Noise 合成 mask，把基色往灰褐拉，再由原有裂纹 mask 压暗缝隙。
"""
import bpy

MAT = "wst_mat_sand"
N_PLATE = "PlateNoise"
N_FINE = "PlateNoiseFine"
N_MIX = "MixPlate"
N_RAMP = "PlateRamp"
N_TINT = "SandTint"

# mask=1 → 灰褐板块；0 → 保留原暖色
GREY = (0.170, 0.138, 0.108, 1.0)
# 沙地整体亮度系数：参考图前景沙地实测 (128,83,54)、中景 (174,119,79)，
# 渲染实测只有 (99,63,36) → 沙地偏暗约 1.3×，在最终色上乘一个系数提回来。
SAND_GAIN = 1.85


def _source_of_base(nt, base):
    """沿自家补丁节点（MixPlate / SandTint）往上游回溯到原始 Base Color 来源。
    这样 build() 可以重复执行而不会把补丁套在自己身上。"""
    PATCH = {N_MIX: ("A_Color",), N_TINT: ("Vector",)}
    link = next((l for l in nt.links if l.to_socket == base), None)
    node = link.from_node if link else None
    while node is not None and node.name in PATCH:
        up = next((l for l in nt.links
                   if l.to_node.name == node.name and l.to_socket.identifier in PATCH[node.name]), None)
        node = up.from_node if up else None
    return node


def build():
    mat = bpy.data.materials[MAT]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    base = bsdf.inputs["Base Color"]

    # 找到原 Base Color 的来源（跳过自家补丁节点，保证可重复执行）
    src = _source_of_base(nt, base)
    if src is None:
        raise RuntimeError("找不到 Base Color 的来源节点")

    def get(name, bl):
        n = nt.nodes.get(name)
        if n is None:
            n = nt.nodes.new(bl)
            n.name = name
        return n

    coord = get("TexCoordG", "ShaderNodeTexCoord")
    coord.location = (-1500, -700)

    def noise(name, y, scale, detail, dist, ramp_lo, ramp_hi):
        n = get(name, "ShaderNodeTexNoise")
        n.location = (-1300, y)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = 0.55
        n.inputs["Distortion"].default_value = dist
        nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
        r = get(name + "Ramp", "ShaderNodeValToRGB")
        r.location = (-1100, y)
        r.color_ramp.elements[0].position = ramp_lo
        r.color_ramp.elements[1].position = ramp_hi
        nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
        return r

    r_big = noise(N_PLATE, 200, 0.055, 4.0, 0.45, 0.40, 0.66)
    r_fine = noise(N_FINE, -180, 0.28, 3.0, 0.20, 0.42, 0.72)

    mul = get("PlateMul", "ShaderNodeMath")
    mul.location = (-880, 0)
    mul.operation = "MULTIPLY"
    nt.links.new(r_big.outputs["Color"], mul.inputs[0])
    nt.links.new(r_fine.outputs["Color"], mul.inputs[1])

    gain = get("PlateGain", "ShaderNodeMath")
    gain.location = (-700, 0)
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 1.85      # 拉满，让板块明显
    nt.links.new(mul.outputs[0], gain.inputs[0])

    mix = get(N_MIX, "ShaderNodeMix")
    mix.location = (-480, 0)
    mix.data_type = "RGBA"
    mix.blend_type = "MIX"
    mix.inputs[7].default_value = GREY       # B_Color
    # ShaderNodeMix 的 outputs[0] 是 Float、[2] 才是 Color，接错会把颜色变成灰阶
    src_col = next(o for o in src.outputs if o.type == "RGBA")
    nt.links.new(src_col, mix.inputs[6])
    nt.links.new(gain.outputs[0], mix.inputs[0])

    # 亮度系数：乘在最终色上（>1，所以用 VectorMath 而不是 Mix）
    tint = get(N_TINT, "ShaderNodeVectorMath")
    tint.operation = "MULTIPLY"
    tint.location = (-300, 0)
    scale = get("SandGainXYZ", "ShaderNodeCombineXYZ")
    scale.location = (-300, -260)
    for i in range(3):
        scale.inputs[i].default_value = SAND_GAIN
    nt.links.new(mix.outputs[2], tint.inputs[0])
    nt.links.new(scale.outputs["Vector"], tint.inputs[1])

    for l in list(nt.links):
        if l.to_socket == base:
            nt.links.remove(l)
    nt.links.new(tint.outputs["Vector"], base)
    return {"patched": MAT, "from": src.name, "sand_gain": SAND_GAIN}


if __name__ == "__main__":
    print(build())