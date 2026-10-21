# 开发指南

## 环境

不需要安装任何东西(没有 `package.json`)。只要有 Python 或 Node 起一个静态服务器:

```bash
python -m http.server 5173
# 或
npx serve .
```

打开 http://localhost:5173 。改完源码刷新页面即可,没有构建步骤。

## 每次改动后的自检清单

1. **把 `index.html` 里的两个 `?v=` 一起 +1**(`styles/hud.css?v=N` 与 `scripts/main.js?v=N`)。这是本项目的"构建"替代品,忘了改就会出现"代码改了、行为没变"。
2. 控制台无报错;关注 `[player] Soldier.glb load failed`(模型路径)与 `fatal('无法加载 Three.js')`(importmap)。
3. `__neon.player.debug()` 应返回 `{ loaded: true, clips: ['Idle','Walk','Run'], skinned: >0, mode, action, height, bbox }`;若 `loaded: false` 说明 GLB 没加载,场景里只剩占位胶囊。
4. 走动验证:贴地无抖动、岩石/晶簇/塔/集装箱推开、能量边界拉住、E 交互、设置面板、音效开关、窗口缩放到移动端尺寸。
5. 触屏相关改动要用设备模拟(`pointer: coarse`)或真机验证摇杆与 E 按钮。

## 常见改动配方

### 加一个可交互物件

1. `scripts/island.js` 第 14 段(`island.js:666` 起)建几何,底部用 `addGlowDisc`、上方用 `addSprite` 光晕,动画塞进 `updaters`
2. `addObstacle(x, z, r, gy + h)` 登记碰撞(否则会走进模型里)
3. `interactives.push({ name: '显示名', kind: 'newKind', pos: new THREE.Vector3(x, gy, z) })`
4. `scripts/main.js` 的 `dialogData` 加同名 `newKind` 条目(`{ name, lines } `)
5. 雷达标记自动出现(kind 为 `core` 是粉圆,其余是青菱形);要新形状就改 `scripts/ui/hud.js:63`

### 加一种 HUD 元素

`index.html` 写 DOM(带 `aria-label`/`role`)→ `styles/hud.css` 用 `--c-*` token 写样式(桌面/触屏两套布局都过一遍)→ `scripts/ui/` 新建工厂函数 → `main.js` 的 `els` 里取元素并实例化,在主循环对应步骤里调用。

### 加音效

复用 `scripts/audio.js` 的 `burst(c, now, { peak, attack, decay, cutoffFrom, cutoffTo, rate, pan })`;注意保持 `ensure()` 懒初始化 + `ctx.state === 'running'` 检查,不要在启动阶段创建 AudioContext。

### 加键位动作

`keybinds.js` 的 `KEY_ACTIONS` 加 `{ id, label, def }` → `main.js` 的 `keydown` 分支里用 `e.code === binds.xxx` 处理 → 需要键帽提示就给元素加 `data-bind="xxx"`(见 `refreshBindLabels()`)。

### 调整画面

先动 `postfx.js` 的 uniforms(曝光、泛光强度、黑场、饱和),再动 `main.js` 的光照强度与太阳角度;确认没把 `renderer.toneMapping` 改回 ACES(会与合成里的 ACES 双重映射,高光死白)。

## 调试入口

```js
__neon.scene                 // 场景图,可用 .traverse 找物体
__neon.camera                // 透视相机
__neon.renderer.info         // draw calls / 三角形数
__neon.player.debug()        // GLB、骨骼、当前动作、包围盒
__neon.island.obstacles      // 碰撞体数组 { x, z, r, top }
__neon.water.material.uniforms
```

临时改参数也可以直接在控制台写 `__neon.camera.fov = 75` 之类,刷新即还原。

## 已知问题 / 待办

- 移动端没有疾跑与缩放入口(桌面才有 Shift 与滚轮)
- 交互点只有对白,没有任务状态机与存档
- 没有画质档位:低端机(阴影 + MSAA + 双层泛光)可能吃力,可考虑自动降级
- 没有自动化测试与 lint;回归靠上面的手工清单

## 提交约定

- `<type>(<scope>): <subject>`,type 取 feat / fix / docs / style / refactor / perf / chore,scope 用模块名(`island` / `player` / `postfx` / `ui` / `audio` / `keybinds`)
- 一次提交只做一件事;调整随机序列导致整岛重排、或修改 `heightAt` 这类影响面大的改动,必须在提交正文里写明影响范围
- 提交前确认没有 `console.log`、没有注释掉的实验代码、`?v=` 已递增
