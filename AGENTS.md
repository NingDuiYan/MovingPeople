# AGENTS.md

给 AI 协作者 / 新贡献者的工程约定。**动手前先读本文**;本文与实际代码不符时,以代码为准并顺手修正本文。

## 项目速览

- 单页静态 3D 预览:`index.html` + 原生 ES Modules + Three.js **r160**(npm 依赖 `three@0.160.1`),Vite 7 构建
- 按**单件**加载 `public/models/{tree,house,car,ground,character}.glb`(枯树 / 废墟 / 轿车 / 地面 / 幸存者角色,前四个文件里各只有一个网格节点,角色是带骨架与 12 段动作的单网格),配黄昏光照与尘雾,用 OrbitControls 自由查看
- 角色是第三人称可操作体:WASD 移动、Shift 跑、空格跳、C 下蹲、X 静步、左键四段拳击(第四段是高扫腿)、右键格挡;逻辑在 `scripts/character.js`,与 `main.js` 的相机跟随配合
- 触屏设备上换成左侧虚拟摇杆 + 右侧按钮(拳/跳/蹲/挡/静),由 `scripts/touch.js` 挂载;摇杆推到底即奔跑,两者共用同一套输入状态,不写第二套行为
- 目标形态是小游戏(树是核心可交互物、车是障碍、废墟是建筑、地面给人物行走做碰撞与贴地),所以模型拆开交付而不是一个整场景 GLB
- 工具链:Node >= 18、npm、Vite 7、ESLint 9(flat config)、Prettier 3、Vitest 3;配置见根目录 `vite.config.js` / `eslint.config.js` / `.prettierrc.json`
- 纯静态站点:没有后端;全部 UI 文案与代码注释为中文,技术术语保留英文原文
- 模型本体由 `wasteland-blender/` 下的 Blender 脚本生成,导出与踩坑说明见 `wasteland-blender/README.md`

## 运行与验证

```bash
npm install    # 首次安装
npm run dev    # 开发服务器,默认 http://localhost:5173(HMR)
npm run check  # lint + format:check + test
npm run build  # 生产构建,产物 dist/
```

不要用 `file://` 直接打开 `index.html`:裸模块 `three`、`import.meta.env` 与 `public/` 资产都依赖 Vite(dev)或打包产物(build)。

验证方式(自动化只有 `tests/` 下的单测,画面仍需手工过一眼):

1. `npm run dev`,加载遮罩消失,画面出现枯树 / 废墟 / 轿车的黄昏场景
2. 控制台无 `[viewer] 模型加载失败`;网络面板里 `models/{tree,house,car,ground,character}.glb` 与 `draco/draco_decoder.wasm` 全是 200
3. 拖拽旋转、滚轮缩放、右键平移可用;相机不会钻到地面以下
4. 角色能用 WASD / Shift / 空格 / C / X / 左键 / 右键走出全部状态;触屏(或 DevTools 手机模拟)下左侧摇杆与右侧按钮出现,摇杆推到底跑起来
5. 改了构建或资源路径再跑一次 `npm run build` + `npm run preview`

## 目录与模块职责

| 文件                   | 职责                                                                           | 不该放什么              |
| ---------------------- | ------------------------------------------------------------------------------ | ----------------------- |
| `index.html`           | 唯一的页面:canvas、加载遮罩、操作提示                                          | 业务逻辑、内联脚本      |
| `scripts/main.js`      | 全部 3D:渲染器、天穹、灯光、相机与控制器、GLB 加载、渲染循环                   | 与模型无关的业务状态    |
| `scripts/utils.js`     | `assetUrl(path)`:按 Vite `BASE_URL` 拼静态资产路径                             | 有状态的东西            |
| `styles/main.css`      | 页面与遮罩样式,颜色走 `--c-*` token                                            | 组件级 JS 逻辑          |
| `tests/utils.test.js`  | Vitest 单测:资产路径拼接                                                       | 依赖 WebGL 的渲染与交互 |
| `scripts/character.js` | 角色控制器:动作状态机、连招、跳跃/下蹲/静步、接触阴影、相机跟随输入            | 场景建模、灯光          |
| `scripts/touch.js`     | 触屏控件:虚拟摇杆与按钮,把触摸翻译成与键鼠相同的输入状态                       | 动作逻辑、速度档位      |
| `public/models/`       | 交付模型:`tree` / `house` / `car` / `ground` / `character` 五个 GLB            | 源码                    |
| `public/draco/`        | DRACOLoader 解码器(从 `node_modules/three/examples/jsm/libs/draco/gltf/` 拷来) | 手改                    |
| `wasteland-blender/`   | 建模脚本(builders/)、导出产物(export/)、渲染图(shots/)与说明                   | 前端代码                |

依赖方向单向:`main.js` → `utils.js`;不要出现循环 import。

## 硬性约定(踩过坑的)

1. **资产路径只走 `assetUrl`**:源码里写 `assetUrl('models/tree.glb')`,不要写死 `/models/...`。`vite.config.js` 用 `base: './'`,写死绝对路径在子目录部署时会 404。
2. **GLB 的颜色来源只有两条**:程序化材质(沙地 / 岩石 / 混凝土)靠 `wasteland-blender/builders/wst_export.py` 的 `FLAT` 表压成 `baseColorFactor`;三件扫描资产(tree / house / car)靠 `wst_external.py` 里 `ASSETS` 的 `tint` 烘进贴图像素。**材质节点上的乘色导不进 GLB**(导出器丢连线,只剩纯白),不要在节点上做颜色校正,也不要在浏览器里另改材质。
3. **光照方位与建模场景对齐**:太阳方位角 34°、仰角 8°;Blender(Z-up)到 Three(Y-up)的换算是 `(x, y, z) -> (x, z, -y)`。改灯之前先确认地面长影的方向仍与参考图一致。
4. **GLB 不含灯光/相机/体积雾**:天穹、雾、三盏灯都在 `scripts/main.js` 里重建;`wst_volume_fog` / `wst_volume_dust` 是渲染专用体积,导出时已被排除。
5. **相机不钻地**:`controls.maxPolarAngle = Math.PI / 2 - 0.02`;换成自定义轨道时要保留这条。
6. **不引入逐帧随机与自动漫游**:当前页面没有随机抖动,加了会破坏与 Blender 渲染图的一致性。
7. **五个模型单独加载**:清单唯一来源是 `scripts/main.js` 的 `MODELS`;增删或改名模型要同步 `wst_export.GROUPS` / `wst_export.CHAR_GLB`、`MODELS` 与本文档。GLB 用 Draco 压几何(解码器托管在 `public/draco/`,不引 CDN)。
8. **触屏控件只在粗指针设备挂载**:`createTouchControls()` 用 `(pointer: coarse)` 判定,不满足直接返回 `null`;按钮必须 `preventDefault` + `stopPropagation`,否则会冒泡成 canvas 的拖动/左键出拳。
9. **移动端预算**:触屏设备走 `IS_COARSE_POINTER` 分支(像素比压到 1.5、阴影贴图 1024);新增资产前先看三角数与贴图尺寸,当前合计 103,478 三角 / 2.25 MB 五个文件(角色单独 25,572 三角 / 1.04 MB,其中 22 张 384² 贴图占 620 KB)。
10. **角色导出不套场景那套参数**:`wst_export._export_character()` 用 `export_apply=False`(否则 Armature 修改器被烘掉、蒙皮丢失)、`export_animations=True` + `export_animation_mode="ACTIONS"`,材质**不压平**(贴图要跟着走);每个动作必须挂进同名 NLA 轨道并 mute,否则只导出最后一个动作。

## 代码风格

- 2 空格缩进、单引号、必写分号;函数式写法(小函数拼装),不用 class
- 格式化与静态检查以 `.prettierrc.json` / `eslint.config.js` 为准:改完跑 `npm run format` 与 `npm run lint`,不要手工对缩进或引号风格
- 注释用中文,块首用 `// ============ 标题 ============`;解释"为什么"而不是"做了什么"
- 事件监听成对出现(`addEventListener` / 对应的清理或 `once`);DOM 查询集中在 `main.js` 的 `els` 对象里
- 生产代码不留 `console.log`(ESLint `no-console` 只放行 `warn` / `error`)

## 提交

- 提交前自检:`npm run check` 全绿(lint + format:check + test);动了构建、资源路径或 `index.html` 再跑一遍 `npm run build`
- 提交信息 `<type>(<scope>): <subject>`,type 取 feat/fix/docs/style/refactor/perf/chore,scope 用 `viewer` / `scene` / `build`
- 一次提交只做一件事;依赖升级(如 `three` / `vite` 大版本)单独成提交,写清变更要点与回滚方式
- 重新导出模型时把 `wasteland-blender/export/models/*.glb` 与 `public/models/*.glb` 一起更新,并在提交里记下每个文件的三角数、字节数与 MD5
