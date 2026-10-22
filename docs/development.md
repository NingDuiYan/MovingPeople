# 开发指南

## 环境与安装

需要 **Node >= 18**(见 `package.json` 的 `engines`)与 npm;没有其他系统依赖,也不需要全局安装 Vite。

```bash
npm install     # 按 package-lock.json 安装依赖(three / vite / vitest / eslint / prettier)
npm run dev     # Vite 开发服务器,默认 http://localhost:5173,带 HMR
```

改源码即时生效(HMR),不需要手动重启。裸模块 `three`、`import.meta.env` 与 `public/` 资产都由 Vite 解析,所以 `file://` 直接打开 `index.html` 会失败。

静态资产放在 `public/`(`models/Soldier.glb`、`textures/waternormals.jpg`、`textures/grasslight-big.jpg`),源码里一律用 `utils.js` 的 `assetUrl('textures/xxx.jpg')` 拼 URL,不要写死 `/textures/...`。

## 命令表

| 命令                   | 作用                                               |
| ---------------------- | -------------------------------------------------- |
| `npm run dev`          | 开发服务器 + HMR,默认端口 5173                     |
| `npm run build`        | 生产构建,产物在 `dist/`(文件名带内容 hash)         |
| `npm run preview`      | 本地预览 `dist/` 产物,上线前用它验证一遍           |
| `npm run lint`         | ESLint 9(flat config)检查 `scripts/` 与 `tests/`   |
| `npm run lint:fix`     | ESLint 自动修复                                    |
| `npm run format`       | Prettier 3 格式化整个仓库                          |
| `npm run format:check` | Prettier 只检查不写入(CI / 提交前用)               |
| `npm run test`         | Vitest 跑一遍单测(`tests/**/*.test.js`)            |
| `npm run test:watch`   | Vitest watch 模式                                  |
| `npm run check`        | `lint` + `format:check` + `test` 三连,提交前跑这个 |

## 每次改动后的自检清单

1. `npm run check` 全绿(lint + format:check + test);格式化交给 `npm run format`,不要手工调缩进与表格对齐。
2. 控制台无报错;关注 `[player] Soldier.glb load failed`(资产没放 `public/models/` 或 `assetUrl` 拼错)与 `fatal('设备不支持 WebGL')`(无 WebGL 的浏览器)。
3. `__neon.player.debug()` 应返回 `{ loaded: true, clips: ['Idle','Walk','Run'], skinned: >0, mode, action, height, bbox }`;若 `loaded: false` 说明 GLB 没加载,场景里只剩占位胶囊。
4. 走动验证:贴地无抖动、岩石/晶簇/塔/集装箱推开、能量边界拉住、E 交互、设置面板、音效开关、窗口缩放到移动端尺寸。
5. 触屏相关改动要用设备模拟(`pointer: coarse`)或真机验证摇杆与 E 按钮。
6. 动了 `index.html`、`vite.config.js`、`public/` 资产或任何资源路径,`npm run check` 之后补跑 `npm run build` + `npm run preview`,确认产物里资产能取到。
7. 改了 `utils.js` / `keybinds.js` / `collision.js` 这类纯函数模块,先在 `tests/` 补一条单测再动实现。

## 常见改动配方

### 加一个可交互物件

1. `scripts/island.js` 的交互物段落:建几何,底部用 `addGlowDisc`、上方用 `addSprite` 光晕,动画塞进 `updaters`
2. `addObstacle(x, z, r, gy + h)` 登记碰撞(否则会走进模型里)
3. `interactives.push({ name: '显示名', kind: 'newKind', pos: new THREE.Vector3(x, gy, z) })`
4. `scripts/main.js` 的 `dialogData` 加同名 `newKind` 条目(`{ name, lines }`)
5. 雷达标记自动出现(kind 为 `core` 是粉圆,其余是青菱形);要新形状就改 `scripts/ui/hud.js` 的 `createRadar`(雷达点绘制处)

### 改碰撞规则

钳制与"圆 vs 圆"推出都在 `scripts/collision.js` 的纯函数里,`main.js` 只调入口 `moveWithCollision`;改完在 `tests/` 补一组边界用例,不要在 `main.js` 里另写一份位移修正。

### 加一种 HUD 元素

`index.html` 写 DOM(带 `aria-label`/`role`)→ `styles/hud.css` 用 `--c-*` token 写样式(桌面/触屏两套布局都过一遍)→ `scripts/ui/` 新建工厂函数 → `main.js` 的 `els` 里取元素并实例化,在主循环对应步骤里调用。

### 加音效

复用 `scripts/audio.js` 的 `burst(c, now, { peak, attack, decay, cutoffFrom, cutoffTo, rate, pan })`;注意保持 `ensure()` 懒初始化 + `ctx.state === 'running'` 检查,不要在启动阶段创建 AudioContext。

### 加键位动作

`keybinds.js` 的 `KEY_ACTIONS` 加 `{ id, label, def }` → `main.js` 的 `keydown` 分支里用 `e.code === binds.xxx` 处理 → 需要键帽提示就给元素加 `data-bind="xxx"`(见 `refreshBindLabels()`)。

### 换 / 加静态资产

文件放 `public/`(构建时原样复制到 `dist/` 根),源码里用 `assetUrl('models/xxx.glb')` 引用;路径相对 `public/` 书写,不要带前导 `/`。

### 调整画面

先动 `postfx.js` 的 uniforms(曝光、泛光强度、黑场、饱和),再动 `main.js` 的光照强度与太阳角度;确认没把 `renderer.toneMapping` 改回 ACES(会与合成里的 ACES 双重映射,高光死白)。

## 调试入口

```js
__neon.scene; // 场景图,可用 .traverse 找物体
__neon.camera; // 透视相机
__neon.renderer.info; // draw calls / 三角形数
__neon.player.debug(); // GLB、骨骼、当前动作、包围盒
__neon.island.obstacles; // 碰撞体数组 { x, z, r, top }
__neon.water.material.uniforms;
```

临时改参数也可以直接在控制台写 `__neon.camera.fov = 75` 之类,HMR 或刷新即还原。

## 已知问题 / 待办

- 移动端没有疾跑与缩放入口(桌面才有 Shift 与滚轮)
- 交互点只有对白,没有任务状态机与存档
- 没有画质档位:低端机(阴影 + MSAA + 双层泛光)可能吃力,可考虑自动降级
- 单测只覆盖纯函数模块(高度场/数学工具、键位数据层、碰撞解算);渲染管线与交互仍靠上面的手工清单

## 提交约定

- `<type>(<scope>): <subject>`,type 取 feat / fix / docs / style / refactor / perf / chore,scope 用模块名(`island` / `player` / `postfx` / `ui` / `audio` / `keybinds` / `collision` / `build`)
- 一次提交只做一件事;调整随机序列导致整岛重排、或修改 `heightAt` 这类影响面大的改动,必须在提交正文里写明影响范围
- 依赖升级(`three` / `vite` / `vitest` 等)单独成提交,写清是否破坏 API 与回滚方式
- 提交前确认 `npm run check` 通过、没有 `console.log`、没有注释掉的实验代码
