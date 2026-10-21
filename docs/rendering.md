# 渲染与画面

## 光源清单(`scripts/main.js:119-163`)

| 光源 | 类型 | 颜色 | 强度 | 说明 |
|---|---|---|---|---|
| 太阳 | `DirectionalLight` | `0xffd2a6` | 3.6 | 唯一投影光源,mapSize 2048,radius 2.2,正交范围 ±56,near 20 / far 320,bias `-0.0004`,normalBias `0.02` |
| 天光 | `HemisphereLight` | `0x9fb8d2` / `0x2b3038` | 0.42 | 冷天顶 + 暗地面反照 |
| 环境 | `AmbientLight` | `0x3d4a5c` | 0.20 | 只抬暗部,不压对比 |
| 品红轮廓 | `DirectionalLight` | `0xff2d95` | 0.35 | 位置 (-46, 26, -38),赛博主题染色 |
| 青色补光 | `DirectionalLight` | `0x1d7f9c` | 0.30 | 位置 (-30, 14, 52) |
| 角色随身光 | `PointLight` | `0xffd9a8` | 2.4(距离 7,decay 1.6) | 挂在 `player.group` 上 |
| 塔顶灯 ×4 | `PointLight` | 塔色 | 70(距离 32,decay 2) | 霓虹塔的光晕来源 |

Three r155+ 使用物理光照单位:`DirectionalLight` 是个位数,`PointLight` 是高数值 + `decay`,`scene.environmentIntensity` 单独调。照抄旧教程的 0.5 强度会让整个岛变黑。

## 天空 / 海 / 环境反射

- **Sky**(three 官方大气散射):`turbidity 9.5`、`rayleigh 2.45`、`mieCoefficient 0.012`、`mieDirectionalG 0.86`、`scale 10000`。太阳角度 `phi = degToRad(90 - 30)`(仰角 30°)、`theta = 205°`——黄昏低角度,地面仍有有效照明。
- **Water**(官方平面反射海面):`PlaneGeometry(2200, 2200)`、反射 RT 256²、法线贴图 `libs/textures/waternormals.jpg`(RepeatWrapping)、`waterColor 0x041a26`、`sunColor 0xffe2bd`、`distortionScale 3.1`,`position.y = WATER_LEVEL(0)`;每帧 `uniforms.time += dt * 0.6`。
- **IBL**:把 Sky 临时挪进一个空场景,用 `PMREMGenerator.fromScene` 烘成环境贴图(`scene.environment`,`environmentIntensity 0.38`),金属与光滑表面因此有真实环境反射。烘完立刻 `pmrem.dispose()`。

## 后期处理(`scripts/postfx.js`)

管线(每帧 5 步):

```
scene ──► rtScene (HalfFloat, depth, samples = min(2, maxSamples))
              │
              ├─ bright ──► rtA (1/2 分辨率)  ── 双向高斯 ×2 ──► 近层泛光
              └─ 降采样 ──► rtC (1/4 分辨率)  ── 双向高斯 ×2 ──► 远层泛光
              ▼
        composite → 画布(色散 / 锐化 / 泛光叠加 / 曝光 / ACES / sRGB / 分级 / 黑白场 / 暗角 / 颗粒)
```

**为什么要自己在合成里做 ACES**:three 只在渲染到画布时应用 `renderer.toneMapping`,渲染到 RenderTarget 时会跳过;所以主入口设的是 `NoToneMapping` + `outputColorSpace = SRGBColorSpace`,ACES 在 `FRAG_COMPOSITE` 里做(`acesFilmic`,Karis 拟合)。

合成 uniform 默认值(`scripts/postfx.js:152-171`),调画面时基本只动这张表:

| uniform | 默认 | 作用 |
|---|---|---|
| `uThreshold` / `uKnee` | 1.05 / 0.65 | 亮部提取阈值与软过渡宽度 |
| `uStrength` / `uStrengthWide` | 0.26 / 0.15 | 近层 / 远层泛光强度 |
| `uExposure` | 1.05 | ACES 前曝光 |
| `uSharpen` | 0.32 | 非锐化掩模(补偿 MSAA 解析后的软化) |
| `uAberration` | 0.0011 | 横向色散,只作用于画面边缘(`r²` 权重) |
| `uContrast` / `uSaturation` / `uTint` | 0.24 / 1.10 / 0.55 | sRGB 空间的 S 曲线、饱和度、分离色调(暗部偏青蓝 `0.82,0.94,1.12`,高光偏暖金 `1.08,1.02,0.90`) |
| `uBlackPoint` / `uWhitePoint` | 0.028 / 0.985 | 黑白场,去掉泛光垫底的灰雾 |
| `uVignette` / `uGrain` | 0.34 / 0.010 | 暗角 / 胶片颗粒 |

泛光模糊核是一维 5 taps(`0.2270 / 0.3162 ×2 / 0.0703 ×2`,偏移 `1.3846 / 3.2308` 像素),横竖各跑一次;`uDir` 传 `(0, 0)` 退化成纯采样,顺便当降采样用。

## 材质与"零资源"技巧

- 霓虹发光全靠 `MeshBasicMaterial` + `AdditiveBlending` + `depthWrite: false`(环、灯带、光柱、光晕 Sprite),不依赖 bloom 就有辉光感
- 光晕 = `Sprite` + Canvas 径向渐变贴图(`assets.js:makeGlowTexture`),统一 `fog: false` 让其穿透雾
- 建筑窗户 = `emissiveMap`(Canvas 随机窗格)+ `emissiveIntensity 0.85`
- 地形 = `grasslight-big.jpg` + 顶点色调制 + `onBeforeCompile` 注入沙/岩分层;`customProgramCacheKey = 'terrain-detail'` 防止和别的标准材质共用程序缓存
- HUD 全是 DOM + Canvas 2D:雷达是 `<canvas>`,`devicePixelRatio` 上限 2

## 性能预算

当前场景规模:远景楼 66 栋、岩石 55、晶簇 30 组、塔 4、灯牌 4、栈桥木板 22、集装箱 5 组、管道 2 条、灯笼 26、数据流粒子 320、萤火 80。

几个已经做好的取舍,改画质时不要随手破坏:

- `pixelRatio` 上限 2;后期主 RT 只开 `samples: min(2, maxSamples)` 的 MSAA
- 泛光在 1/2 与 1/4 分辨率上做,不在全分辨率做
- 阴影只有一盏平行光,near/far 收紧到 20–320、±56 的范围,避免精度浪费
- 远景楼群共用一份材质、塔群为每塔 4 段独立小盒(数量小,未做 instancing)
- 粒子在 `updaters` 里每帧直接改 `BufferAttribute.array` 并置 `needsUpdate`

## 常见画面问题

| 现象 | 大概率原因 |
|---|---|
| 整体发灰、暗部不黑 | `uBlackPoint` 偏低或泛光 `uStrengthWide` 偏大 |
| 高光死白 | `uExposure` 过大,或有人把 `renderer.toneMapping` 改回 ACES(会双重映射) |
| 地面像贴了塑料 | 地形 `vertexColors` 或 `onBeforeCompile` 的沙/岩分层被绕过 |
| 霓虹没有辉光 | sprite 贴图没走 `SRGBColorSpace`,`depthWrite` 被打开,或 `uThreshold` 高于自发光亮度 |
| 水面全黑 | `Water` 的 `sunDirection`/`sunColor` 没跟着 sun 走,或法线贴图加载失败 |
