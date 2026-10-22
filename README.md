# 霓虹孤岛 NEON ISLE

Three.js 赛博朋克风格 3D 探索 Demo:控制小人在霓虹小岛上行走,与数据终端 / 机器人 NPC / 能量核心交互。

- **技术栈**:原生 ES Modules + Three.js **r160**(npm 依赖 `three@0.160.1`)+ Vite 7 构建
- **工具链**:Node >= 18、npm;ESLint 9(flat config)、Prettier 3、Vitest 3
- **零资源依赖**:场景几何、贴图、UI、音效全部程序化生成,`public/` 下只放士兵模型与两张 three.js 官方示例贴图
- **无后端**:纯静态站点,进度只写 `localStorage`

## 运行

需要 Node >= 18 与 npm,三步:

```bash
npm install   # 安装依赖(three / vite / eslint / prettier / vitest)
npm run dev   # 开发服务器,默认 http://localhost:5173(HMR)
npm run build # 生产构建,产物在 dist/
```

`npm run dev` 保存即热更新,不需要手动刷新;`npm run preview` 用来本地预览 `dist/` 产物、验证打包结果。

Three.js 走 npm 依赖,**离线可用**;只有 Google Fonts 需要联网,断网时字体降级为系统字体,不影响运行与操作。

## 命令

| 命令                   | 作用                                    |
| ---------------------- | --------------------------------------- |
| `npm run dev`          | 开发服务器 + HMR(http://localhost:5173) |
| `npm run build`        | 生产构建到 `dist/`,文件名带内容 hash    |
| `npm run preview`      | 本地预览 `dist/` 产物                   |
| `npm run lint`         | ESLint 检查(`eslint .`)                 |
| `npm run lint:fix`     | ESLint 自动修复                         |
| `npm run format`       | Prettier 写入                           |
| `npm run format:check` | Prettier 只校验                         |
| `npm run test`         | Vitest 跑一轮(`vitest run`)             |
| `npm run test:watch`   | Vitest watch 模式                       |
| `npm run check`        | `lint` + `format:check` + `test` 一把过 |

## 操作

| 动作     | 桌面                             | 移动端       |
| -------- | -------------------------------- | ------------ |
| 移动     | W A S D / 方向键(可在设置里改)   | 左下虚拟摇杆 |
| 疾跑     | Shift                            | —            |
| 视角     | 鼠标移动(自由视角)或按住左键拖拽 | 屏幕拖拽     |
| 缩放     | 滚轮(3.2 – 14 m)                 | —            |
| 交互     | E                                | 右下 E 按钮  |
| 打开设置 | O / 右下齿轮                     | —(仅桌面)    |
| 音效开关 | M                                | 右下喇叭按钮 |
| 释放光标 | Alt 按住 / Esc 退出全屏          | —            |

靠近发光物体会点亮交互提示,按 E 触发对话;对话框里按 E / 点触继续,正在打字时按一次直接出全句。

## 设置

右下齿轮或 `O` 打开,两个分类页:

- **操作方式**——视角方式(`鼠标自由转动`/`按住拖拽`)+ 鼠标灵敏度(0.30 – 2.00×,输入框 + 保存 / Enter)
- **键位**——WASD / ESDF / 方向键三套移动预设,以及逐项改绑;撞键的动作之间自动互换,Esc 取消;支持一键恢复默认

所有偏好(视角方式、灵敏度、键位、音效开关)都持久化在 `localStorage`,隐私模式下写入失败时静默退回默认值。

## 结构

```
index.html                         页面骨架 + HUD DOM + 模块入口(由 Vite 处理)
package.json                       npm 脚本与依赖(three / vite / eslint / prettier / vitest)
vite.config.js                     Vite:base './'、dev 端口 5173、build 输出 dist/
vitest.config.js                   Vitest:node 环境、tests/**/*.test.js
eslint.config.js                   ESLint 9 flat config(scripts 用 browser globals,tests/config 用 node)
.prettierrc.json                   Prettier 规则(单引号、分号、printWidth 100)
styles/hud.css                     赛博朋克 UI 主题:CSS 变量 token + 桌面/触屏两套布局
scripts/main.js                    入口:渲染器 / 光照 / 相机 / 输入 / 后期 / 主循环 / 交互
scripts/collision.js               纯函数碰撞:边界钳制 + "圆 vs 圆"障碍推出
scripts/island.js                  小岛场景生成(地形/岩层/晶簇/塔群/栈桥/灯牌/粒子/交互物)
scripts/player.js                  小人模型与骨骼动画(步频脉冲回调触发脚步声与尘土)
scripts/postfx.js                  HDR 泛光 + ACES + 电影级调色(自建着色器管线)
scripts/audio.js                   程序化音效:脚步(噪声摩擦 + 落地闷响),无音频资源
scripts/keybinds.js                键位数据层:默认值 / 本地存储 / 冲突互换 / 移动预设
scripts/assets.js                  程序化贴图工厂(辉光 / 窗格 / 灯牌 / 点精灵)
scripts/utils.js                   常量 + 地形高度函数 + assetUrl + 数学工具
scripts/ui/hud.js                  雷达小地图 / FPS / 坐标 / 交互提示
scripts/ui/dialog.js               打字机对话框
scripts/ui/settings.js             设置弹窗(视角方式 / 灵敏度 / 键位)
scripts/ui/toast.js                场景内消息条(队列 + 自动淡出)
scripts/ui/joystick.js             虚拟摇杆
public/models/Soldier.glb          角色模型(three.js 官方示例 GLB,含 Idle/Walk/Run)
public/textures/grasslight-big.jpg 地形草皮贴图
public/textures/waternormals.jpg   水面法线贴图
tests/                             Vitest 单测(utils / keybinds / collision)
docs/                              架构、渲染、场景、操作、开发文档
```

`public/` 下的静态资产原样拷到 `dist/` 根目录;源码统一用 `assetUrl('models/Soldier.glb')`(内部拼 `import.meta.env.BASE_URL`)引用,配合 `base: './'`,把 `dist/` 放到任意子路径都不会拼错 URL。

## 交互点

| 名称           | 位置 (x, z)            | 雷达标记 | 内容                                   |
| -------------- | ---------------------- | -------- | -------------------------------------- |
| 数据终端 DL-07 | (10, -4)               | 青色菱形 | 岛屿网格状态与任务引导                 |
| 维修机器人 R-7 | (-12, 8)               | 青色菱形 | 欢迎与操作教学(进入游戏 1.4s 自动触发) |
| 能量核心 ×2    | (22, -20) / (-26, -16) | 粉色圆点 | 充能剧情                               |

## 技术要点

- **渲染管线**:Sky 大气散射 + 黄昏太阳投影 + Water 平面反射 + Sky 转 PMREM 做 IBL;场景渲染到 HalfFloat 缓冲后走亮部提取 → 双层高斯泛光 → 合成(ACES + 分离色调 + 暗角 + 颗粒)。因为渲染到 RT 时 `renderer.toneMapping` 不生效,色调映射放在合成 pass 里。
- **地形一致性**:`utils.js` 的 `heightAt(x, z)` 是唯一高度来源,地形网格、角色贴地、相机防穿地、雷达海岸线共用同一函数,"所见即所走"。
- **碰撞**:`island.js` 把实心道具登记成圆柱体(`obstacles`),`scripts/collision.js` 的纯函数按"圆 vs 圆"沿法线推出,贴边会自然滑开;夹缝中收敛不了就退回上一帧位置。解算逻辑有 Vitest 单测覆盖。
- **零外部资源**:音效由 Web Audio 现场合成,贴图由 Canvas 绘制,发光全靠加法混合的 Sprite / 自发光材质。
- **工程化**:dev 走 Vite 原生 ESM + HMR,不需要任何缓存版本号;build 由 Rollup 打包,入口脚本与 CSS 文件名带内容 hash,CDN 缓存自然失效。

## 文档

- [docs/architecture.md](docs/architecture.md) — 启动流程、主循环、模块依赖与数据流
- [docs/rendering.md](docs/rendering.md) — 光照参数、Sky/Water/PMREM、后期处理管线
- [docs/scene.md](docs/scene.md) — 地形高度场、场景分层、碰撞体与交互物
- [docs/controls-ui.md](docs/controls-ui.md) — 键位、视角模式、触屏适配、HUD 与 CSS token
- [docs/development.md](docs/development.md) — 安装、命令表、自检清单、常见改动配方与提交约定
- [AGENTS.md](AGENTS.md) — 给 AI 协作者的工程约定

## 后续可扩展

- 音效扩充:海浪 / UI 反馈 + 音量滑块(脚步已程序化合成,按 M 或右下喇叭按钮静音)
- 画质档位:阴影 / 粒子 / 分辨率 / 泛光层数自动降级
- 移动端疾跑手势、双指缩放
- 任务系统 / 存档(交互点目前是纯展示对白)
