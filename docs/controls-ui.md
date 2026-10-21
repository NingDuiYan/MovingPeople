# 操作、输入与 UI

## 键位动作表(`scripts/keybinds.js:5`)

| 动作 id | 面板标签 | 默认 `e.code` | 备注 |
|---|---|---|---|
| `moveForward` | 前进 | `KeyW` | 摇杆上推等效 |
| `moveBack` | 后退 | `KeyS` | 倒退走,步行动作倒放 |
| `moveLeft` | 左移 | `KeyA` | — |
| `moveRight` | 右移 | `KeyD` | — |
| `run` | 疾跑 | `ShiftLeft` | 与 `ShiftRight` 等效 |
| `interact` | 交互 | `KeyE` | 也用于推进对话 |
| `settings` | 打开设置 | `KeyO` | 面板打开时同样可关 |
| `lookPause` | 自由光标 | `AltLeft` | 按住释放指针锁,松开自动锁回 |
| `sound` | 音效开关 | `KeyM` | 与右下喇叭按钮同一开关 |

- **可绑定范围**由正则白名单 `VALID_CODE`(`keybinds.js:36`)限定:字母/数字/方向键/F1–F12/修饰键/若干符号键。Escape、Tab 之外的系统键一律拒绝,避免把浏览器快捷键绑进游戏。
- **左右修饰键互为镜像**:`mirrorCode(code)` 让 `ShiftLeft` 与 `ShiftRight` 命中同一个动作。
- **改键永不"悄悄失效"**:`bindCode()` 发现目标键已被别的动作占用时,两者互换,并 toast 提示"××自动接走△△"。
- **读存储会做清洗**:`normalize()` 丢弃非法与重复键位,缺项用默认值补;默认键被占时找一个还没用上的默认键。

## 移动预设(`keybinds.js:18`)

| 预设 | 移动键 | 交互键 |
|---|---|---|
| WASD | W / A / S / D | E |
| ESDF | E / S / D / F | R(挪开避免与 E 撞车) |
| 方向键 | ↑ / ← / ↓ / → | E |

`matchPreset()` 完全命中某套时才高亮对应按钮,混合键位不高亮。

## 视角与指针锁

| 模式 | 桌面行为 | 触屏行为 |
|---|---|---|
| `free`(默认) | 点一下画面 → 先 `requestFullscreen` 再 `requestPointerLock`,之后靠 `movementX/Y` 转视角;Esc 退出全屏并解锁 | 不进入该模式(触屏直接走拖拽) |
| `drag` | 按住左键拖动才转,松开即停,指针始终可见 | 同左(单指拖动) |

- 灵敏度统一乘在 `LOOK_SENS_X 0.0042` / `LOOK_SENS_Y 0.0032`(rad/px)上,倍率范围 0.30–2.00,只影响转速、不改俯仰限位。
- 俯仰限位 `[-0.2, 1.15]`;滚轮缩放 `[3.2, 14]` m,带 `damp` 缓动。
- 先全屏再锁指针的原因:窗口化时 Chrome 会画"按 Esc 退出"的锁定气泡,全屏下不会。全屏被拒也照样锁,只是气泡留着。
- 释放路径统一走 `releaseLock()`:打开设置面板、切换到拖拽模式、退出全屏都会解指针锁,把光标还给用户。
- 锁失败不弹错:指针锁被拒时静默退回"按住拖拽",同时 toast 提示"点一下画面锁定鼠标"。

## 触屏适配

- 启动判定 `matchMedia('(pointer: coarse)')`;**首次 `touchstart` 也会补切到触屏模式**(`main.js:289`),覆盖鼠标型设备被模拟成触屏的情况
- 切换的落点是 `body.touch-mode` class,由 `styles/hud.css:618` 起的规则改变布局:摇杆出现、雷达移到左下、交互键出现、齿轮入口隐藏
- 摇杆(`scripts/ui/joystick.js`):最大位移 46 px,输出 `vec.x` 右为正、`vec.y` 前为正、范围 ±1;用 `setPointerCapture` 保证手指移出元素也跟手
- 触屏下唯一静音入口是右下喇叭按钮(没有 M 键)

## HUD 组件

| 组件 | 文件 | 行为 |
|---|---|---|
| 雷达 | `scripts/ui/hud.js:6` | 150 逻辑像素,覆盖半径 48 m;海岸线用射线扫描 `heightAt` 命中 `h = 0` 处生成 `Path2D` 并缓存;北 = -Z 朝上;青菱形 = 终端/NPC,粉圆点 = 能量核心,白色三角 = 玩家朝向 |
| 状态读数 | `hud.js:112` | FPS 每 0.5 s 结算一次,`POS` 显示 `X/Z` 保留 1 位 |
| 交互提示 | `hud.js:133` | 靠近时显示物件名,键帽文字随键位改绑刷新(`data-bind`) |
| 对话框 | `scripts/ui/dialog.js` | 20 ms/字,每 7 tick 多打一个字;按 E 时未打完则直接出全句,打完则下一句 / 关闭 |
| 消息条 | `scripts/ui/toast.js` | 一次一条、队列播放、240 ms 淡出;与 `.scene-msg` 的 CSS transition 时长对齐 |
| 设置面板 | `scripts/ui/settings.js` | 两个分类页(操作方式 / 键位),ARIA tablist 支持左右方向键切换;关闭时把焦点还给打开前的元素 |

## CSS 设计 token(`styles/hud.css:4`)

| token | 值 | 用途 |
|---|---|---|
| `--c-bg` | `#0b0f1a` | 深夜蓝主背景(也是 `theme-color`) |
| `--c-panel` | `rgba(11,15,26,.72)` | 玻璃面板底 |
| `--c-border` | `rgba(0,240,255,.38)` | 霓虹青描边 |
| `--c-neon` / `--c-neon-magenta` | `#00f0ff` / `#ff2d95` | 与场景里 `NEON_CYAN` / `NEON_MAGENTA` 同值,改霓虹色要两边一起改 |
| `--c-text` / `--c-dim` / `--c-dim-bright` | `#d7f9ff` / `#6d9aa6` / `#9dc3cf` | 正文 / 暗文 / 深色面板上的次级文字 |
| `--c-grid` | `rgba(0,240,255,.08)` | 网格线 |
| `--radius-panel` / `--gap` | 14px / 14px | 面板圆角与间距 |
| `--glow-soft` / `--glow-hard` | 0 0 12px / 0 0 22px 青色阴影 | 文字与面板辉光 |

新增 UI 一律用 token,不写魔法颜色值;字体走 Google Fonts 的 Orbitron / Rajdhani / Share Tech Mono,断网降级为系统字体。

## 可访问性

- 雷达、状态、对话、设置都有 `aria-label` / `role`;消息条 `role="status" aria-live="polite"`
- 设置面板 `role="dialog" aria-modal="true"`,打开时聚焦首个 tab,关闭时还原焦点;点遮罩空白处关闭
- 音效按钮用 `aria-pressed` 表达开关状态,并同步 `aria-label` / `title`
- 灵敏度输入框校验失败时设 `aria-invalid` + `.is-invalid` 并聚焦选中,不静默吞掉
- `styles/hud.css:627` 有 `prefers-reduced-motion` 分支,雷达扫描、呼吸等动效会关掉

## 持久化

| 键 | 值 | 读失败时 |
|---|---|---|
| `neon-isle:sound` | `'1'` / `'0'` | 默认开 |
| `neon-isle:look-mode` | `'free'` / `'drag'` | 默认 `free` |
| `neon-isle:look-sens` | 数字字符串,0.3–2 | 默认 1 |
| `neon-isle:keybinds` | 动作 → `e.code` 的 JSON | `normalize()` 清洗后补默认 |

全部读写包 `try/catch`:隐私模式下 `localStorage` 会抛,失败时静默使用内存值,不影响这一局游玩。
