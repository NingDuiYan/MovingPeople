# 霓虹孤岛 NEON ISLE

Three.js 赛博朋克风格 3D 探索 Demo:控制小人在霓虹小岛上行走,与数据终端 / 机器人 NPC / 能量核心交互。

## 运行

项目使用 ES Modules 与 importmap,需要通过静态服务器打开(直接双击 index.html 会因 CORS 失败):

```bash
cd 项目目录
python -m http.server 5173
# 或
npx serve .
```

打开 http://localhost:5173。首次加载需联网获取 Three.js CDN 与 Google Fonts;离线时把 three.module.js 放到本地并替换 index.html 里的 importmap 即可。

## 操作

| 动作 | 桌面 | 移动端 |
|---|---|---|
| 移动 | W A S D / 方向键 | 左下虚拟摇杆 |
| 疾跑 | Shift | — |
| 视角 | 鼠标拖拽 | 屏幕拖拽 |
| 缩放 | 滚轮 | — |
| 交互 | E | 右下 E 按钮 |

靠近发光物体会点亮交互提示,按 E 触发对话。

## 结构

```
index.html             页面骨架 + HUD DOM + importmap
styles/hud.css         赛博朋克 UI 主题(CSS 变量 token)
scripts/main.js        渲染器 / 光照 / 输入 / 相机 / 主循环
scripts/island.js      小岛场景生成(地形/海水/霓虹/交互物)
scripts/player.js      小人模型与行走动画
scripts/utils.js       地形高度函数 + 数学工具(高度场共享给网格与角色)
scripts/ui/hud.js      雷达 / FPS / 坐标 / 交互提示
scripts/ui/dialog.js   打字机对话框
scripts/ui/joystick.js 虚拟摇杆
```

## 交互点

- **数据终端 DL-07**(青色菱标):岛屿网格状态与任务引导
- **维修机器人 R-7**(青色菱标):欢迎与操作教学(进入游戏自动触发)
- **能量核心 x2**(粉色圆标):充能剧情

## 后续可扩展

- Bloom 后处理(UnrealBloomPass)增强霓虹辉光
- 音效(脚步 / 海浪 / UI)与静音开关
- 画质档位(阴影 / 粒子 / 分辨率自动降级)
- 任务系统 / 存档
