# 废土场景 · Blender 建模与交付说明

参考图：`ref/wasteland_ref.jpg`（黄昏荒漠：枯树 + 塌楼 + 锈轿车 + 龟裂地面 + 沙尘雾）
提示词：`C:\Users\ning\Downloads\废土场景_超精细_Three.js兼容提示词.md`

## 产物

| 文件                            | 说明                                                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `export/models/*.glb`           | **交付用**：四件单件 GLB（tree / house / car / ground），各一个网格节点；Draco 压几何、+Y Up、无灯光相机。明细见「Three.js 接入要点」 |
| `export/wasteland_scene.glb`    | 整场景合并版（3.71 MB / 147 mesh / 77,906 三角），仅作存档与对照，不再交付                                                            |
| `export/wasteland_scene.blend`  | 导出瞬间的场景副本（含程序化材质、灯光、体积雾），用于回看与二次编辑                                                                  |
| `shots/cmp_final.png`           | 与参考图同分辨率（2730x1536）的定稿成图，取色 / 区域比对都以它为准                                                                    |
| `shots/cmp_final_side.png`      | 左参考 / 右渲染 的并排对照（各 1365x768），一眼看差距                                                                                 |
| `shots/wasteland_final.png`     | 主镜头成图（实际 1280x720，早期版本）                                                                                                 |
| `shots/wasteland_web.png`       | 浏览器实测：`npm run build` + `npm run preview` 后加载新 GLB 的截图（1280×760）                                                       |
| `shots/wst_ruin_facade.png`     | 立面细节检视图                                                                                                                        |
| `shots/wst_tree_v2_scene.png`   | 枯树 v2 主镜头（1280×720，EEVEE + 大气）                                                                                              |
| `shots/wst_tree_v2_closeup.png` | 枯树 v2 近景（900×1200，对齐参考图的竖裁切机位）                                                                                      |
| `shots/wst_tree_v2_roots.png`   | 枯树 v2 根部特写（1100×800，判贴地 / 板根过渡）                                                                                       |
| `shots/wst_car_front3q.png`     | 轿车车头 3/4（1100×760，读格栅/灯环/保险杠）                                                                                          |
| `shots/wst_car_rear3q.png`      | 轿车车尾 3/4（1100×760，读尾灯/车牌框/后杠）                                                                                          |
| `shots/wst_car_side.png`        | 轿车侧面（1100×760，读门缝/B 柱/瘪胎/锈片）                                                                                           |
| `枯树v2_规格比对.md`            | 规格 ↔ 参考图逐条比对、冲突处置、可调开关                                                                                             |
| `废弃轿车_规格比对.md`          | 轿车规格 ↔ 实现逐条比对、与文档的差异、可调开关                                                                                       |

## 骨架：builders/ 下每个脚本一个职责，都是幂等的

| 脚本                    | 职责                                                                                                                                                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wst_atmosphere.py`     | 世界天空（渐变 + 高斯日晕）、两盏 SUN、体积雾盒子、EEVEE/AgX 渲染设定；`render()` 出图                                                                                                                                  |
| `wst_tree_spec.py`      | 枯树 v2：按"枯树_纯视觉描述.md"的规格表放样；窄纵沟 `_tube(flute=)`、双干缠绕 braid、沿途侧枝 SPUR、剥落内凹 dent；3 个对象（树皮/剥落木质/树洞）                                                                       |
| `wst_tree_recovered.py` | 枯树 v1（递归生长，已停用）+ 放样核心 `add_tube`/`_frames`/`_make_material`，v2 复用                                                                                                                                    |
| `wst_car.py`            | 70 年代长身轿车：12 段闭环轮廓挤出 + 轮拱 + 空窗/内芯 + 瘪胎锈毂 + 锈片；末尾按材质合并成 10 个对象（`_merge_parts`）                                                                                                   |
| `wst_ruins.py`          | 塌楼主体：墙体、楼板、瓦砾堆、散砖、外露钢筋                                                                                                                                                                            |
| `wst_ruins_detail.py`   | 立面细节：破损女儿墙、腰线、斜靠楼板、斜梁、瓦砾扇（按实测立面表定位）                                                                                                                                                  |
| `wst_ruins_windows.py`  | 把窗凹面换成近黑哑光材质，远看就是能看穿的黑窗洞                                                                                                                                                                        |
| `wst_ruins_erode.py`    | 废墟表面侵蚀：沿世界法线推顶点（三轴正弦噪声）+ 顶口撒崩块 `wst_ruin_chips`；靠对象属性 `wst_eroded` 保证幂等                                                                                                           |
| `wst_root_heave.py`     | 树基“土被根顶起”的隆起 + 6 条放射裂缝（按 ray_cast 实测地形高度贴合），修掉根盘悬空                                                                                                                                     |
| `wst_ground.py`         | 在沙材质里插入"灰褐干裂板块"混色层 + 末端亮度系数 `SAND_GAIN`（沙地是材质级，几何无源码）                                                                                                                               |
| `wst_dust.py`           | 废墟后方竖直沙尘羽流（体积材质 + 径向柔化）；`PLUME=False` 默认关闭，只留 `extend_fog`                                                                                                                                  |
| `wst_cleanup.py`        | 去重复体积尘、集合归位、N-gon 三角化、远景地面抽面                                                                                                                                                                      |
| `wst_audit.py`          | 体检：面数预算、材质、N-gon、修改器、命名、集合                                                                                                                                                                         |
| `wst_finalize.py`       | 一键收敛：重建树→缩放到 5.10 m→根盘土隆起→沙地材质→三角化→砖褪色→窗洞变暗→废墟侵蚀→清理                                                                                                                                 |
| `wst_export.py`         | 导出 GLB：`build_split()` 按 `GROUPS` 逐件导出四件模型（导出前压平材质、导出后复原、Draco 压几何），`build_character()` 单独导角色（不压平、不 apply、带骨架与 ACTIONS 动画），`build_merged()` 导整场景；都自检 GLB 头 |
| `wst_char.py`           | 幸存者角色几何：放样躯干/头/四肢 + 还原度细节（护目镜、后脑发壳、背包、翻领、军靴）；`preview()` 出四视图                                                                                                               |
| `wst_char_tex.py`       | 角色贴图：按材质生成 384² 可平铺 albedo + 法线（皮肤/皮革/帆布/斜纹/针织/金属/鞋底），把颜色烘进像素，再按面主轴写 UV                                                                                                   |
| `wst_char_rig.py`       | 21 根骨 + 蒙皮：软质件走热力自动权重、硬质件（帽/镜/背包/挂件）走单骨权重；`join_body()` 合成单网格 `wst_char_body`                                                                                                     |
| `wst_char_anim.py`      | 12 段动作（idle/walk/run/jump/crouch_idle/crouch_walk/sneak/punch1-4/block），逐帧置零再套姿势关键帧，挂同名 NLA 轨道                                                                                                   |
| `wst_character.py`      | 角色一键复现：几何 → 骨架 → 合网格 → 动作 → 导出 `export/models/character.glb`                                                                                                                                          |
| `wst_external.py`       | 导入 `C:/Users/ning/Downloads` 下的三件 Triposr 扫描资产（tree / house / car）：删掉程序化树/车/废墟 → 减面 → 贴图钳制与 tint 烘像素 → 按相机反算的位姿摆放 → 归集合                                                    |

重跑一次（Blender 里，Python 控制台或 `rt_do`）：

```python
import sys; sys.path.insert(0, r"<...>\wasteland-blender\builders")
import wst_finalize, wst_audit, wst_export
wst_finalize.build()      # external=True：导入三件扫描资产替换树 / 车 / 废墟
wst_audit.build()
wst_export.build_split()  # 导出 export/models/{tree,house,car,ground}.glb
```

角色单独一条链（不依赖场景，会自己清掉旧的 `wst_char_*`）：

```python
import wst_character
wst_character.build(export=True)  # export/models/character.glb
```

注意：**不要再调 `wst_car.build()`**（会把程序化车加回来）；打开 `export/wasteland_scene.blend` 会丢大气，渲图前必须补跑 `wst_atmosphere.build()`。

`external=True` 分支里程序化的 `wst_tree_spec` / `wst_car` / `wst_ruins*` / `wst_ruins_erode` / `wst_ruins_windows` 全部跳过，只保留 `wst_ground` / `wst_root_heave` / `wst_cleanup`。这些脚本仍留着，用于重建扫描资产替换前的基线（`export/_backup_before_tree_v2.*`）或做对照。

## 硬规范对照（提示词要求 → 实测）

| 项                               | 要求                                     | 实测                                                                          |
| -------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------- |
| 总面数                           | ≤ 60,000 三角（场景四件）                | **77,906**（导出四件合计，体积雾 12 面不导出）+ 角色 25,572                   |
| 地面 / 枯树 / 废墟 / 轿车 / 碎石 | 15,000 / 4,000 / 25,000 / 6,000 / 5,000  | 14,820 / 15,064* / 27,670* / 16,845* / 2,080 + 界外 352                       |
| N-gon                            | 禁止                                     | 无（导出前按对象 bmesh 三角化）                                               |
| 材质                             | Principled BSDF；扫描资产允许 1024² 贴图 | 6 个材质：沙地/混凝土/岩石/界外山脊走 `FLAT` 压平色，三件扫描资产走 JPEG 贴图 |
| 命名                             | `wst_[类别]_[名字]`                      | 扫描资产为 `wst_ext_{tree,house,car}`，其余无例外                             |
| 集合                             | `collection_wasteland` 下 6 个子集合     | car / lighting / props / ruins / terrain / tree                               |
| 修改器                           | 导出前 Apply                             | 场景内已无残留修改器（减面已在导入阶段 apply）                                |
| 导出                             | GLB、+Y Up、无灯光相机动画、Draco        | 已确认（无 KHR_lights_punctual；带 KHR_draco_mesh_compression）               |

\* 三件扫描资产的原始三角数是 111 万（tree 167k / car 443k / house 503k），
按上面的预算减面到 15,064 / 16,845 / 27,670（`wst_external.ASSETS[].decimate` = 0.090 / 0.038 / 0.055）。
减面比例是"保住轮廓、贴图细节补细节"的折中：再往下压，树枝和车灯这类细结构会先塌。

## Three.js 接入要点

1. **按单件交付，不是整场景**：`wst_export.build_split()` 按 `GROUPS` 把场景切成四个 GLB，角色由
   `wst_export.build_character()` 单独导出（带骨架/动作，拖进任何 Three 场景用 `AnimationMixer` 就能播）；
   每个文件里只有一个网格节点（名字就是 `tree` / `house` / `car` / `ground`），摆放位姿在导出时已烘进顶点。
   这样树能单独挂交互（小游戏的核心物）、车能单独做障碍碰撞、地面能单独拿去 raycast 贴地。
2. **颜色有两条来源**：程序化材质（沙地 / 混凝土 / 岩石 / 界外山脊）由 `FLAT` 表在导出前压成
   `baseColorFactor`（`_flatten()` 压平、导出后 `_restore()` 复原）；三件扫描资产走 `baseColorTexture`
   （1024² JPEG，quality 82）；角色走自己的 384² PNG albedo + 法线贴图。**节点上挂的乘色导不进 GLB**
   （导出器丢连线，只剩纯白），扫描资产的颜色校正 `ASSETS[].tint` 必须烘进贴图像素（`_tint_image()`，见踩坑）。
   角色同理：颜色在 `wst_char_tex.py` 里烘进贴图像素，材质节点上只留 UVMap → Image Texture → Base Color。
3. **体积雾和沙尘羽流不导出**（`wst_volume_fog` / `wst_volume_dust` 在导出时被排除）。
   大气全部在 Three.js 侧重建：`scene.fog` + 天穹着色器 + 三盏灯（详见 `scripts/main.js`）。
   光照对齐参考图：低角度暖色主光（az≈34°, elev≈8°）+ 冷色补光 + 暖色反弹光，GLB 里没有灯。
4. **角色的动作与朝向约定**：12 段动作名与 `scripts/character.js` 一一对应（`idle` / `walk` / `run` /
   `jump` / `crouch_idle` / `crouch_walk` / `sneak` / `punch1`~`punch4` / `block`），除 `punch*` 与 `jump`
   是 `LoopOnce` 外都循环。Blender 里角色面朝 **-Y**，导出 +Y Up 后在 Three 里朝 **+Z**，
   所以转向写 `rotation.y = Math.atan2(dx, dz)`；腿脚在 `foot.L/R`/`toe.L/R`，手在 `hand.L/R`。
5. **几何用 Draco 压缩**（`KHR_draco_mesh_compression`，level 6）：77,906 三角从 3.6 MB 压到 1.08 MB，
   移动端首屏才吃得消。解码器**托管在本项目里**（`public/draco/draco_{wasm_wrapper.js,decoder.wasm}`，
   从 `node_modules/three/examples/jsm/libs/draco/gltf/` 拷来），不走 CDN——CDN 会多一次跨境请求，离线也挂。
6. 加载写法沿用项目约定：

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { assetUrl } from './utils.js';

const loader = new GLTFLoader().setDRACOLoader(
  new DRACOLoader().setDecoderPath(assetUrl('draco/')),
);
const [tree, house, car, ground] = await Promise.all(
  ['tree', 'house', 'car', 'ground'].map((n) => loader.loadAsync(assetUrl(`models/${n}.glb`))),
);
for (const g of [tree, house, car, ground]) {
  g.scene.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
    }
  });
  scene.add(g.scene); // 节点名即模型名：tree / house / car / ground
}
```

交付文件（`public/models/`，与 `export/models/` 同一份，MD5 已核对）：

| 文件            | 字节      | 三角   | 贴图                                  | MD5                                |
| --------------- | --------- | ------ | ------------------------------------- | ---------------------------------- |
| `tree.glb`      | 307,384   | 15,064 | 1024² JPEG                            | `819BE2A84D6C9EDF352D5B86B5E460E2` |
| `house.glb`     | 439,920   | 27,670 | 1024² JPEG                            | `8D64EAF133F190A82F2E68C5444245F2` |
| `car.glb`       | 282,392   | 16,845 | 1024² JPEG                            | `72ADEEACE60CEB71900A496836E53C9D` |
| `ground.glb`    | 175,576   | 18,327 | 1024² PNG 裂纹贴图（不平铺色）        | `080630367D16FEA4EA6FBADCF7CBBBC4` |
| `character.glb` | 1,041,628 | 25,572 | 22 张 384² PNG（11 组 albedo + 法线） | `1CFFE63FBF51594FF818FD95A54D3F5A` |

前四件合计 1.20 MB / 77,906 三角；角色单独 1.04 MB / 25,572 三角（1 蒙皮、22 骨、12 段动作，每段 63 条通道）。
改完 `ASSETS[].tint` / `decimate` 或角色几何要重新导出并重算 MD5。
引用时不要写死 `/models/...`，用 `assetUrl('models/tree.glb')`。

## 与参考图仍有差距的地方（已知，未处理）

全局亮度/色温已按参考图对齐（判据见下节「取色对标」）：全图 mean `[118,90,72]` vs 参考 `[111,82,67]`，lum_mean 94.4 vs 87.4（整体仍偏亮约 7%）。三件扫描资产替换掉程序化树 / 车 / 废墟之后，构图、天色、前景沙地都贴上了参考图，剩下的偏差集中在**扫描件自带的贴图色温**和**几何风格**上：

1. 废墟曾比参考图暗约 12%（区域 mean `82,63,53` vs `93,70,56`）：`ASSETS.house.tint` 从 `(1.62,1.50,1.32)` 提到 `(1.88,1.74,1.52)` 后网页实测差距已收窄；像素乘色在 0.8 以上会夹住，再想提亮得给 house 单独烘一张暖色 LUT 贴图。
2. 中景沙地与远山比参考图暗 15% 左右（`136,99,73` vs `161,111,76`；`119,84,59` vs `129,92,72`）：为了压掉地平线上那条奶白色带，雾密度定在 `fog_density 0.0020`，代价就是这一带偏暗——两头都要，只能折中。
3. 枯树树干比参考图亮约 10%（`87,66,53` vs `77,59,48`），树冠亮 12%：`tint` 已从 1.30 收到 1.12，再暗会把根部的浅色沙膜压成泥色。
4. 轿车比参考图亮约 13%（`96,67,49` vs `85,61,47`）：`carall` 区域含大片被太阳照亮的沙地，车漆本身已压到接近参考的锈色。
5. 车的朝向比参考图更"正面"：参考图是后左 3/4（近乎纯侧面，只露一点车尾面板），当前 `rot_z=-1.742` 是车头偏左、正面露得偏多。想完全对齐要把 `rot_z` 往 -1.95 调，代价是侧面轮廓的贴合度。
6. 远山（`wst_bg_*`）是一圈低多边形山脊，参考图那边是沙尘雾里糊掉的沙丘线。网页侧把 `scene.fog` 从 `(20,190)` 收到 `(24,132)` 后轮廓已明显柔化；Blender 渲染仍走 `fog_density 0.0020`，两边不完全一致。
7. 地面裂纹由 `wst_ground_tex.py` 生成（1024²、世界 `TILE = 4.0 m` 一张），是准 Voronoi 板块网，参考图是更大块的不规则板块 + 大片平滑区。网页侧用 `GROUND_TEXTURE_PERIOD_SCALE = 0.80` 把周期拉到约 5 m，重复感减弱但图案本身仍是多边形网。
8. 废墟破口形状由扫描件决定，比参考图"更碎"：参考图还能读出两层楼板与窗格的节奏，扫描件的二层已经塌掉大半。
9. 树根被扫描件自带的"沙膜"（一圈浅色薄片）包住，参考图的根是裸木直接插进裂土；模型上这块是几何不是贴图，只能靠把 `sink` 压深盖住一部分。

## 取色对标（判据，改完必须重跑）

单点 patch 太脆（`car_roof` 那个点正好落在阴影带上，怎么调都不动），**区域 mean / p90 才是可靠判据**。做法：PIL 读图 → 固定像素框 → `numpy` 求 `mean` 与 `p90`，参考图与渲染图用**同一套框**（渲染必须是 2730x1536 的 `cmp_final.png`，分辨率不同框会错位）。

| 区域（px）                   | 参考图 mean / p90           | 定稿渲染 mean / p90         |
| ---------------------------- | --------------------------- | --------------------------- |
| sky (1200-1800×100-300)      | 86.9,83.4,90.1              | 87.0,82.4,88.7 ✓            |
| fore (900-1400×1250-1450)    | 147.4,99.4,65.9             | 142.9,97.5,63.4 ✓           |
| sandmid (1000-1400×900-1000) | 160.6,111.0,76.1            | 136.0,99.0,73.0             |
| ridge (1100-1500×570-640)    | 128.5,92.3,72.3             | 119.0,84.0,59.0             |
| trunk (260-430×560-1000)     | 77.0,59.0,48.0 / 132,93,69  | 87.0,66.0,53.0 / 154,110,84 |
| crown (150-660×60-520)       | 68.0,64.0,66.0              | 81.0,74.0,77.0              |
| carall (1700-2560×760-1120)  | 85.0,61.0,47.0 / 178,126,92 | 96.0,67.0,49.0 / 170,124,95 |
| ruin (300-1400×360-960)      | 93.0,70.0,56.0 / 162,116,88 | 82.0,63.0,53.0 / 139,104,91 |

全图（整幅 2730x1536）：参考 `mean [111,82,67] / lum 87.4 / std 33.6 / p1 20 / p50 85 / p99 164`，渲染 `[118,90,72] / lum 94.4 / std 31.7 / p1 12 / p50 97 / p99 158`。

大气终值（`wst_atmosphere.SPEC`，已渲染验证）：`sun_energy 8.5 / sun_color (1.0,0.66,0.46) / sun_angle_deg 5.5`、`fill_energy 2.60 / fill_color (0.70,0.62,0.58)`、`bounce_energy 2.60`、`core_gain 0.8 / halo_gain 0.14 / haze_gain 0.07`（太阳盘原本过曝削顶，参考图 p99 只有 159）、`sky_strength 1.25 / sky_away_gain 0.62 / sky_away_low 0.68`（水平渐变：方位压暗只作用在低空带，否则左上会被压死）、`fog_density 0.0020 / fog_color (0.78,0.56,0.40)`、`exposure 0.18`。

`fill_energy` 从 1.05 提到 2.60 是因为**扫描资产的相机侧是背光的**（太阳 az 34° / elev 8° 在 +X+Y），
原参数下树和废墟渲成近黑；四档扫描（A 原值 / B / C / D 各渲 1365x768 比区域 mean）后采纳 C 档。

## 踩过的坑（改脚本前先读）

- `blender_rt_do(file=...)` 在本机静默不执行 —— 源码必须走 `code=`；且必须显式 `auto=False`，否则静默降级到无头 worker 操作另一个实例。
- 父级挂接：`ob.parent=p` 之后若写 `ob.matrix_parent_inverse = p.matrix_world.inverted()`，父级位移会被完全抵消；要 `Matrix.Identity(4)`。
- 对已成组的树枝直接改 `o.scale` 会把树拆散（对象原点各不相同，且属性写入后立刻读 `matrix_world` 还是旧值）；等比缩放要 **顶点级** 做。
- `ShaderNodeMix` 的 `outputs[0]` 是 Float、`outputs[2]` 才是 Color；接错会把颜色变灰阶。
  `ShaderNodeMath` 的幂运算枚举是 `'EXPONENT'`（不是 `'EXP'`）。
- 体积材质类名是 `ShaderNodeVolumePrincipled`（不是 `ShaderNodePrincipledVolume`）。
- EEVEE 的世界着色器里 `Geometry.Incoming` 恒为 0，方向只能取 `Texture Coordinate.Generated`。
- 用布尔给这面墙开洞会把 3428 面的壳体打成 556 面（薄壳 + EXACT 求解器），已放弃布尔，改走暗部材质。
- 根径必须按**文档长度**归一化，不能按当前长度（v2 的 `_root_section` 用 `fd = f * ROOT_LEN_SCALE`）：
  否则缩短根长会把整根压细、末端变成针尖，读成"蜘蛛腿"而不是钝头根爪。
- 板根脊用 cos^n 尖峰会读成光滑圆台，用"谷半径 → 脊半径"的平顶插值 + 深 V 沟才对（见 `_collar_radius`）。
- `audit_mesh` 的自交判定对"交叠管件拼装的生物形体"必然报 fail（v2 树 1,419 处）：
  它是按 3D 打印单体口径设计的，渲染用资产不必强行布尔合并。
- 改相机前先看 `wst_cam_main`：曾经把近景探针的变换留在主相机上并保存进 `.blend`，主镜头于是渲成贴脸特写。
  探针相机必须**新建对象**、渲完 `remove`，不要改 `wst_cam_main`。主镜头真值：`location=(0,-15,1.9)`、`rotation_euler=(1.552,0,0)`、`lens=28`。
- 树皮条纹用 `TexCoord.Object` 时，世界轴方向的条纹在主干上是竖纤维、在**横躺的粗根上就绕成一圈圈斑马环**（近看像轮胎纹）。
  正解是让几何自带 UV：`_tube()` 与 `_build_collar()` 写 `u=周向、v=沿轴累计弧长`，材质改用 `TexCoord.UV` 并把 Mapping Scale 写成 `(1.0, 0.10, 1.0)`。
- 根盘（板根脊）的 `COLLAR_FLARE_Z` 是两难参数：太高（0.46）会立成一片斜坡板、太低（0.22）会在地面摊出一圈平顶方板；
  最终 = `COLLAR_FLARE_Z=0.42` + `h = (1 - z/FLARE_Z) ** 2.2` + `SIDES_COLLAR=28`，才是"陡降的软喇叭口"。
  排查手法：逐件 `hide_render` 渲同机位，比对着色器/材质更省事。
- `_buttress_fin` 是根盘还是"圆台 + 辐条腿"那版留下的过渡件；根盘改成板根脊之后它反而在裙外戳出一片竖刀。
  本轮为了让根基读成"连续张开的板根"又把它打开（`BUTTRESS_FIN=True`）：前提是 `DIA_GAIN` 已把根径放粗、`ROOT_LEN_SCALE` 收到 0.44，
  短粗的鳍才贴在裙上；根又细又长时它就是戳出来的竖刀。
- `wst_dust` 的体积羽流在 EEVEE 低角度阳光下会读成一条惨白竖条（近处雾压不住），已用 `PLUME=False` 关掉；
  留着常量是为了将来换 Cycles 或改吸收/散射后能一键打开。
- `wst_car._mat()` 只在材质**不存在**时创建：老 `.blend` 里改常量后重跑毫无变化（本以为是几何错，查了三轮）。
  修法是 `build()` 开头先 `bpy.data.materials.remove()` 掉 7 个车专属材质（paint / hub / flake / trim / chrome / cavity / glass）再重建；
  **不要删**共享的 `wst_mat_rust` / `wst_mat_opening`。删完 `_paint()`/`_tire_mat()` 里的 `get()` 会拿到 None，要补 `new()` 分支。
- 新材质（或改颜色）必须同步 `wst_export.FLAT`：GLB 不认节点图，表里没有的材质就没有 `baseColorFactor`，
  Three.js 里显示为**纯白**。本轮 `wst_mat_car_cavity` / `_glass` / `_flake` 都是两边同步过的。
- 合并小件时 `ob.matrix_local` 实测返回的是**含父级变换的矩阵**（不是父级相对矩阵）：
  按它算出的顶点已是世界坐标，再挂回父级等于二次变换，整车会跑到原点。
  正解：`inv = parent.matrix_world.inverted()`，取顶点 `inv @ (mw @ v.co)`；合并后立刻 `bpy.context.view_layer.update()`，否则同脚本里紧接着渲染用的是旧矩阵。
- **重新 `open_mainfile` 会丢掉大气**：`export/wasteland_scene.blend` 里存的是导出瞬间的世界/灯光，而 `wst_atmosphere` 的 SPEC 改动只活在 Python 常量里。
  所以"打开基线 .blend → finalize → 导出"这条链路里，**渲图前必须补跑 `wst_atmosphere.build()`**，否则渲出来是旧的奶白过曝版（本轮踩过一次，凭渲染图的雾感才定位）。
- **`resize_tree(TREE_HEIGHT=5.10)` 会等比压细树干 22%**（本地造 6.5 m，强制缩到 5.10 → ×0.78，半径同乘）：
  参考图比对时"干/根/枝都比参考细 1.3–1.9 倍"的根因就在这。解法是 `wasteland-blender/builders/wst_tree_spec.py` 里的 `DIA_GAIN = 1.28`，
  必须接到**主干、`_limb` 的 radii、`_collar_r` 的三个 return、板根脊 ridge** 四处，漏一处就有一段特别细。
- 树皮条纹的 Wave `bands_direction` 必须用 `"X"`，不能用 `"DIAGONAL"`：后者让条纹 45° 螺旋，干径放大后整根读成"拧麻花的糖棍"。
- `wst_car.py` 的**空窗/风档材质判定只看面中心与高度**（`0.30<=c.x<=1.06 and c.z>=0.95`），三角化后车顶与后箱的面中心正好也落在这个盒子里，
  于是**整个车顶被刷成 `wst_mat_car_cavity`，渲成一大片死黑**（用"把 cavity 临时改成洋红再渲"的探针才定位到）。
  修法是追加法线判据 `if abs(f.normal.x) < 0.35: continue`（风档法线朝 ±X，车顶朝 +Z）。
- `wst_ruins_erode` 是**就地推顶点**，`wst_finalize` 反复跑会累加（实测第二次崩块从 431 掉到 363、顶点抖动叠加）。
  幂等靠对象自定义属性：`if ob.get("wst_eroded"): return 0` + 末尾 `ob["wst_eroded"] = True`；`wst_ruins` 重建后新对象没有标记，会正常侵蚀一次。
- `npm run build` 在本机可能报 `[vite:esbuild-transpile] remove C:\Users\ning\AppData\Local\Temp\esbuild-...: Access is denied.`：
  **是临时目录权限问题，不是代码问题**。把 `TEMP`/`TMP` 指到工作区内目录（如 `.tmp-build`）即可构建成功。
- 轿车父级 `rotation_euler.z = 195°`，车头指向世界 `(-0.966, -0.259)`：相机放 +X 侧看到的是**车尾**。
  车头 3/4 在 `(2.9,-2.5,1.5) → (4.9,0.45,0.78)`，车尾 3/4 在 `(11.2,2.6,1.5) → (8.5,1.4,0.8)`，侧面在 `(11.9,-3.9,1.7) → (6.6,1.0,0.85)`（lens 45–50）。

### 外部扫描资产（`wst_external.py`）的坑

- **glTF 导入的物体 `rotation_mode` 是 `'QUATERNION'`**：直接写 `ob.rotation_euler = (0,0,rz)` 会被静默忽略，
  物体一点都不转。症状是"改了 rot_z 渲出来一模一样"（连扫 8 次 360° 发现全同才定位到）。
  修法：先 `ob.rotation_mode = "XYZ"` 再赋 `rotation_euler`。
- `_place()` 的顺序必须是 **先按资产自身轴向定尺寸 → 再旋转 → 最后平移**。先旋转再量 bbox，量到的是旋转后的
  轴对齐包围盒（对角线进到尺寸里），车会被放大 1.87×（实测 dims 从 `[2.16,5.24,1.556]` 变成 `[10.59,5.24,3.09]`）。
- **材质节点上的乘色导不进 GLB**：`Mix(MULTIPLY)` 连到 Base Color 后，导出器丢连线、`baseColorFactor` 只剩纯白
  或 `(1,1,0.98)`，网页里整件比 Blender 暗一档。颜色校正必须**烘进贴图像素**（`_tint_image()`）。
- `_tint_image()` 用 numpy `img.pixels.foreach_get/foreach_set`，并且要做 **1/2.2 幂补偿**
  （`f = t ** (1.0/2.2)`）：`Image.pixels` 存的是 sRGB 原值，而 Blender 节点 Mix 走线性空间，不补偿会过曝。
  改完像素必须 `img.pack()`，否则像素改动不落盘、导出拿到的还是原图。
- 贴图体积：`img.scale()` 之后 Blender 会把 packed 图重编码成 **PNG**，单张 1024² 就要几 MB（曾导出 18.4 MB 的 GLB）。
  修法是 `export_scene.gltf` 加 `export_image_format="JPEG"` + `export_image_quality=82`（WEBP 更小但多一个扩展依赖）。
- **`join` 不应用非活动对象的修改器**：`_isolate()` 里必须先 `bpy.ops.object.convert(target="MESH")` 把修改器烘进网格、
  再 join，否则减面几何直接丢（症状是导出的三角数等于原始数）。
- Draco 开关要**探测而不是硬写**：`bpy.ops.export_scene.gltf.get_rna_type().properties.keys()` 里有
  `export_draco_mesh_compression_enable` 才传，否则整个导出直接报错（不同 Blender 版本 / 构建可能没有）。
- `export/models/` 与 `public/models/` 是两份物理文件，必须成对刷新；`public/draco/` 也要在（否则网页
  报 `DRACOLoader: failed to load draco_decoder.wasm`）。

### 构图定标

- 用**轴对齐 bbox 自动拟合**会发散（曾两次 hill-climb 得到 scale 0.64 / 0.76 / 2.55、距离 108 m 的荒谬解）：
  bbox 前角的投影比中心低得多，误差函数不单调。正解是按「**着地点像素 + 已知物理尺寸**」反算：
  相机 `location=(0,-15,1.9)` `rot=(1.552,0,0)` `lens=28` `sensor=36`、出图 2730x1536 → `f_px=2123`、地平线 `v≈728`，
  `v → 地面距离 d = 1.9 / tan(atan((v-768)/2123) + 1.08°)`、`u → x = (u-1365)/2123 · d`。
  参考图真值：树基 `u≈355 / v≈1326`（≈6.7 m，世界 `(-3.2,-8.3)`，高 4.3 m）、车着地 `v≈1063 / 中心 u≈2133`（≈12.3 m）。
- 定稿用「顶点逐个 `world_to_camera_view` 求投影包围盒」核对，不用 bbox：参考目标框 tree `[48,48,528,1408]` /
  car `[1679,751,2719,1103]` / house `[208,312,1423,960]`，实测 tree `[59,87,541,1404]` / car `[1660,805,2696,1119]` /
  house `[264,359,1447,969]`，三件都在 ±80 px 内。
