"""角色交付流水线：建模 → 贴图 → 骨架蒙皮 → 合并网格 → 动作 → 导出 GLB。

按顺序跑一次即可复现 public/models/character.glb；分步调试时可以只调其中一段。
"""

import json

import wst_char
import wst_char_rig
import wst_char_anim
import wst_export


def build(export=True):
    rep = {}
    rep["char"] = wst_char.build()
    rep["rig"] = wst_char_rig.build()
    rep["body"] = wst_char_rig.join_body()
    rep["anim"] = wst_char_anim.build()
    if export:
        rep["glb"] = wst_export.build_character()
    return rep


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
