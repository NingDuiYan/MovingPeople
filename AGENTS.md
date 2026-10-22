# AGENTS.md

给 AI 协作者 / 新贡献者的工程约定。**动手前先读本文**;本文与实际代码不符时,以代码为准并顺手修正本文。

## 项目速览

- 单页 3D 探索 Demo:`index.html` + 原生 ES Modules + Three.js **r160**(npm 依赖 `three@0.160.1`),Vite 7 构建
- 工程化工具链:Node >= 18、npm、Vite 7、ESLint 9(flat config)、Prettier 3、Vitest 3;配置见根目录 `vite.config.js` / `eslint.config.js` / `.prettierrc.json` / `vitest.config.js`
- 纯静态站点:没有后端;`npm run dev` 走 Vite HMR,`npm run build` 产出 `dist/`
- 全部 UI 文案为中文,代码注释也是中文;技术术语保留英文原文

## 运行与验证

```bash
npm install    # 首次安装
npm run dev    # 开发服务器,默认 http://localhost:5173(HMR)
npm run check  # lint + format:check + test
npm run build  # 生产构建,产物 dist/
```

不要用 `file://` 直接打开 `index.html`:裸模块 `three`、`import.meta.env` 与 `public/` 资产都依赖 Vite(dev)或打包产物(build)来解析。

验证方式(自动化只有 `tests/` 下的单测,画面与交互仍需手工过一遍):

1. `npm run dev`,确认加载遮罩消失、R-7 的欢迎对白 1.4s 后自动弹出
2. 控制台检查无 `[player] Soldier.glb load failed` 等错误;Google Fonts 拉取失败不算致命
3. 用调试句柄查场景状态:`__neon.scene` / `__neon.camera` / `__neon.player.debug()` / `__neon.island.obstacles.length`
4. 走动一圈验证:贴地、岩石/晶簇/塔/集装箱碰撞、能量边界、E 交互、设置面板、音效开关
5. 改了 `utils.js` / `keybinds.js` / `collision.js` 就补跑 `npm run test`;改了构建或资源路径再跑一次 `npm run build` + `npm run preview`

## 目录与模块职责

| 文件                   | 职责                                                                        | 不该放什么                          |
| ---------------------- | --------------------------------------------------------------------------- | ----------------------------------- |
| `scripts/main.js`      | 唯一的入口:渲染器/光照/相机/输入/主循环/对白数据                            | 场景几何、UI 细节实现、碰撞数学     |
| `scripts/collision.js` | 纯函数碰撞:入口 `moveWithCollision`(边界钳制 + "圆 vs 圆"推出),只依赖 utils | 主循环状态、场景内容                |
| `scripts/island.js`    | 世界生成,返回 `{ interactives, obstacles, update }`                         | 输入、相机、DOM                     |
| `scripts/player.js`    | 角色模型 + 骨骼动画 + 尘土,暴露 `update(dt, speed, t, turnRate, backpedal)` | 移动计算(位移由 main.js 算)         |
| `scripts/postfx.js`    | 后期处理管线,暴露 `{ setSize, render, uniforms }`                           | 场景内容                            |
| `scripts/audio.js`     | 程序化脚步音效(懒初始化 AudioContext)                                       | 播放策略 / 用户手势判断(在 main.js) |
| `scripts/keybinds.js`  | 键位纯数据层:默认值、存储、冲突互换、预设                                   | 任何 DOM 操作                       |
| `scripts/assets.js`    | Canvas 程序化贴图工厂                                                       | 场景布局                            |
| `scripts/utils.js`     | 常量、`heightAt`、`assetUrl`、数学工具                                      | 有状态的东西                        |
| `scripts/ui/*.js`      | 各 HUD 组件,均返回 `{ ... }` 方法对象,**不 import three**                   | 游戏逻辑                            |
| `tests/*.test.js`      | Vitest 单测:高度场/数学工具、键位数据层、碰撞解算                           | 依赖 WebGL 的渲染与交互             |

依赖方向单向:`main.js` → 各模块 → `utils.js` / `assets.js` / `keybinds.js`;碰撞解算单独在 `collision.js`(只依赖 `utils.js` 的常量与 `heightAt`),`main.js` 只调它的 `moveWithCollision`。模块之间不要互相 import(除 `player.js` 引 `utils.js` 的常量)。

## 硬性约定(踩过坑的)

1. **高度场只有一个来源**:任何"贴地"的坐标都必须用 `heightAt(x, z)`(`scripts/utils.js`)。地形网格、角色 Y、相机防穿地、雷达海岸线都共用它,自己另写一份高度公式会造成"看着在地上、实际穿模"。
2. **实心道具必须登记碰撞**:`island.js` 里凡是"看起来挡人"的物体,都要 `addObstacle(x, z, r, top)`。`top` 是顶面高度,主循环用 `footY >= top` 跳过矮物(膝盖以下的碎石不挡路)。
3. **交互物只登记不实现对白**:`interactives.push({ name, kind, pos })` 里的 `kind`(`terminal` / `npc` / `core`)是 `main.js` 里 `dialogData` 的 key。新增交互类型要同时改这两处,否则按 E 没反应。
4. **色调映射在合成 pass 里**:渲染到 RenderTarget 时 `renderer.toneMapping` 不生效,所以 `renderer.toneMapping = NoToneMapping` + ACES 写在 `postfx.js` 的合成着色器。改画质时不要在这里加回 `ACESFilmicToneMapping`。
5. **随机数要确定性**:场景散布用 `rng(20240521)` 的 mulberry32(`scripts/utils.js`)。往里插新的 `rand()` 调用会改变后续所有物体的位置(整岛重排),属于可接受但需在提交里说明的改动。注释里保留"先取值保持随机序列一致"这类说明(`scripts/island.js` 的晶簇段落)。
6. **光照单位**:Three r155+ 用物理光照单位,`DirectionalLight` 强度是个位数(太阳 3.6),`PointLight` 是高数值(塔顶灯 70,decay=2)。不要拿旧教程里的 0.5 往上套。
7. **存储键集中声明**:`neon-isle:sound` / `neon-isle:look-mode` / `neon-isle:look-sens` / `neon-isle:keybinds`。读写一律 `try/catch` 包裹(隐私模式下 `localStorage` 会抛),失败时静默用默认值。
8. **音频只在用户手势里解锁**:首帧不创建 `AudioContext`,用 `{ once: true }` 的 `keydown`/`pointerdown`/`touchstart` 触发 `unlock()`。别在启动阶段直接 `new AudioContext()`。
9. **触屏判定**:启动看 `matchMedia('(pointer: coarse)')`,首次 `touchstart` 也会切到触屏模式(`body.touch-mode`)。触屏专用元素默认 `hidden`,由 CSS/JS 控制显隐,不要靠媒体查询硬切 DOM。

## 代码风格

- 2 空格缩进、单引号、必写分号;函数式模块(工厂函数返回方法对象),不用 class
- 格式化与静态检查以 `.prettierrc.json` / `eslint.config.js` 为准:改完跑 `npm run format` 与 `npm run lint`,不要手工对表格、缩进或引号风格
- 注释用中文,块首用 `// ============ 标题 ============`;解释"为什么"而不是"做了什么"
- 事件监听成对出现(`addEventListener` / 对应的清理或 `once`),指针手势用 `setPointerCapture` + `pointercancel` 兜底
- DOM 查询集中在 `main.js` 的 `els` 对象里,组件只接收元素引用,不自己 `querySelector` 全局
- 生产代码不留 `console.log`(ESLint `no-console` 只放行 `warn` / `error`);确需诊断用 `__neon` 调试句柄或临时 `console.warn` + `TODO`

## 提交

- 提交前自检:`npm run check` 全绿(lint + format:check + test);动了构建、资源路径或 `index.html` 再跑一遍 `npm run build`
- 提交信息 `<type>(<scope>): <subject>`,type 取 feat/fix/docs/style/refactor/perf/chore,scope 用模块名(`island` / `player` / `postfx` / `ui` / `collision`)
- 一次提交只做一件事;依赖升级(如 `three` / `vite` 大版本)单独成提交,写清变更要点与回滚方式

## 常见改动指引

| 想做的事         | 改哪里                                                                                                     |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| 加一个可交互物件 | `island.js` 的交互物段落(`interactives.push` 处)→ `dialogData`(`main.js`)→ 必要时 `addObstacle`            |
| 调整小岛形态     | `utils.js` 的 `heightAt`(会同时影响地形网格、碰撞、雷达)                                                   |
| 改碰撞规则       | `scripts/collision.js`(纯函数)+ `tests/` 下对应的单测                                                      |
| 加一种 HUD 元素  | `index.html` 加 DOM + `styles/hud.css` 加样式(用 `--c-*` token)+ `scripts/ui/` 新组件 + `main.js` 的 `els` |
| 换 / 加静态资产  | 文件放 `public/`,源码里用 `assetUrl('models/xxx.glb')` 引用(不要写死 `/models/xxx.glb`)                    |
| 调画质 / 氛围    | `postfx.js` 的 uniforms 表、`main.js` 的曝光与光照参数                                                     |
| 加音效           | `audio.js` 复用 `burst()`,注意 `ensure()` 仍要懒初始化                                                     |
| 加键位动作       | `keybinds.js` 的 `KEY_ACTIONS` + `main.js` 的 `keydown` 分支 + 需要时补 `data-bind` 键帽                   |

详细说明见 [`docs/`](docs/README.md)。
