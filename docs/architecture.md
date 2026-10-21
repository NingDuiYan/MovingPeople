# 架构

## 一句话

`index.html` 提供 DOM 骨架与 importmap → `scripts/main.js` 一个 `boot()` 建完渲染器、光照、世界、角色、后期、HUD,然后进入 `frame()` 主循环;其余模块都是无状态工厂函数,被 `main.js` 组装。

## 模块依赖

```
index.html (importmap: "three" → ./libs/three.module.js)
   └─ scripts/main.js                      ← 唯一入口
        ├─ utils.js        常量 / heightAt / 数学       (无依赖)
        ├─ assets.js       Canvas 程序化贴图            (→ utils.rng)
        ├─ island.js       世界生成                     (→ utils, assets)
        ├─ player.js       角色 + 骨骼动画              (→ utils 常量, libs/loaders/GLTFLoader)
        ├─ audio.js        程序化脚步音效               (无依赖)
        ├─ postfx.js       后期管线                     (无依赖)
        ├─ keybinds.js     键位数据层                   (无依赖, 不碰 DOM)
        └─ ui/{hud,dialog,settings,toast,joystick}.js   (→ hud.js 引 utils)
   └─ libs/{objects/Sky,objects/Water,loaders/GLTFLoader}.js
```

依赖严格单向,`scripts/ui/*` 不 import three:`main.js` 只通过元素引用与回调把 DOM 与游戏状态连起来(`createSettings({ getMode, onSelect, getSens, onSensChange, binds, onBindsChange, notify })`)。

## 启动流程(`scripts/main.js` 的 `boot()`,90-731)

| 顺序 | 动作 | 关键参数 |
|---|---|---|
| 1 | 动态 `import('three')`,失败进 `fatal()` | importmap 解析到本地 r160 |
| 2 | 创建 `WebGLRenderer` | `antialias`,`pixelRatio = min(dpr, 2)`,`shadowMap = PCFSoftShadowMap`,`toneMapping = NoToneMapping` |
| 3 | 场景与雾:`FogExp2(0x12202c, 0.0015)`;相机 58° / near 0.1 / far 1200 | — |
| 4 | `Sky` 大气散射 + 太阳主光 + 半球光 + 环境光 + 品红/青色补光 | 见 [rendering.md](rendering.md) |
| 5 | `Water` 平面反射海面 + `PMREMGenerator` 用 Sky 生成环境贴图 | `environmentIntensity = 0.38` |
| 6 | 音效:`createStepAudio()`,只读 `localStorage` 的开关,**不创建 AudioContext** | `neon-isle:sound` |
| 7 | `buildIsland(THREE, scene)` → `{ interactives, obstacles, update }` | 见 [scene.md](scene.md) |
| 8 | `buildPlayer(THREE, scene, stepAudio.footstep)`,出生点 (2, 2) | `heightAt(2, 2)` 贴地,朝向 `PI * 0.85` |
| 9 | `createPostFX(...)` + `syncPostSize()`(按 drawingBuffer 尺寸) | HalfFloat + MSAA `min(2, maxSamples)` |
| 10 | HUD:radar / status / prompt / dialog / toast / settings / joystick,读键位与偏好 | `readBinds()`、`readLookMode()`、`readSens()` |
| 11 | 一次性音频解锁:`keydown`/`pointerdown`/`touchstart` 各 `{ once: true }` | 浏览器自动播放策略 |
| 12 | 首帧揭幕:遮罩淡出 → 900ms 操作引导 → 1400ms 自动打开 R-7 对白 | `started` 标志保证只跑一次 |

任何阶段抛错都会落到 `boot().catch()` → `fatal('启动失败: ...')`,由 `#fatal` 面板显示。

## 主循环(`frame()`,618-726)

`dt = min(clock.getDelta(), 0.05)` 防止切标签页回来一帧穿模,然后固定八步:

1. **输入向量**——键盘(`isDown(action)`,按 `binds` 取键、修饰键左右等效)+ 摇杆 `joy.vec`;长度 > 1 时归一化,`len > 0.08` 才算在动
2. **移动**——以相机 `yaw` 构造 `forward`/`right` 基向量;速度取 `WALK_SPEED 2.4` / `RUN_SPEED 6.0`;朝向只取"往前"的分量,所以按 S 是倒退走(步行动作倒放,避免太空步);`turnRate` 限幅 ±3 rad/s 防止掉帧时侧倾一帧打满
3. **碰撞与边界**——`clampToIsland`(半径 `ISLAND_RADIUS * 0.955`)→ `resolveObstacles`(圆 vs 圆,最多 3 轮)→ 再 `clampToIsland` → `penetrationAt > 1e-3` 时退回上一帧位置
4. **贴地**——`groundY = max(heightAt(x, z), -0.22)`,`damp(y, groundY, 14, dt)`
5. **角色动画**——`player.update(dt, curSpeed, elapsed, turnRate, backpedal)`
6. **交互检测**——在 `INTERACT_RADIUS 3.2` 内取最近的一个,对话框打开时隐藏提示;触屏模式下同步 E 按钮显隐
7. **世界与 HUD**——`island.update(dt, elapsed)`、雷达每帧重绘、FPS 每 0.5s 结算、水面 `uniforms.time` 推进、`postfx.render(elapsed)`
8. **首帧揭幕**(仅一次,见上表第 12 步)

调试句柄:`window.__neon = { scene, camera, renderer, player, island, water, sun }`(`scripts/main.js:728`)。

## 关键不变量

- **高度唯一来源**:`heightAt(x, z)`(`scripts/utils.js:44`)。地形顶点、角色 Y、相机最低点(`camTarget.y >= heightAt(...) + 0.5`)、雷达海岸线全部调用它。
- **碰撞唯一登记处**:`island.obstacles` 是 `{ x, z, r, top }[]`,`top` 为顶面高度;`footY >= top` 的对象直接跳过。
- **交互唯一渲染处**:`island.interactives` 是 `{ name, kind, pos }[]`,`kind` 决定 `dialogData` 取哪段对白;雷达标记也读同一份数组(`radarPoints`)。
- **偏好单一存放处**:四个 `localStorage` 键全部带 `neon-isle:` 前缀,读失败一律回默认值。
- **一帧一帧的状态都在 `frame()` 里推进**,模块自身不持有主循环(只有 `island.update` 与 `player.update` 是被动调用)。

## 事件与生命周期

- 键盘:`keydown`/`keyup`/`blur`(失焦清空按键集合,防止"松手在窗口外"导致一直走)
- 指针:画布 `pointerdown/move/up/cancel`(拖拽模式与触屏用 `setPointerCapture`),`wheel` 缩放,`contextmenu` 屏蔽
- 右键(`button === 2`)当前不承载任何操作:在 `pointerdown`(`scripts/main.js:499`)与 `endDrag`(`scripts/main.js:519`)里直接忽略,既不锁指针也不起拖拽
- 面板:`settings.isOpen()` 为真时除 Esc/O 外全部按键让位;改键监听在 `window` 的**捕获阶段**(`scripts/ui/settings.js:205`)吃掉按键,不会漏到游戏逻辑
- 窗口:`resize` 同步相机 aspect、渲染器尺寸、后期 RT 尺寸;`fullscreenchange` 退出全屏时顺手解指针锁
