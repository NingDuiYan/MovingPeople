# 废土场景 · Three.js 模型预览

一个最小静态页面:加载 `public/models/wasteland_scene.glb`(黄昏废土场景模型),配黄昏光照、天穹与尘雾,用轨道相机自由查看。原来的小岛探索 Demo 已移除,仓库只剩这一个查看器。

- **技术栈**:原生 ES Modules + Three.js **r160**(`three@0.160.1`)+ Vite 7 构建
- **工具链**:Node >= 18、npm;ESLint 9(flat config)、Prettier 3、Vitest 3
- **无后端**:纯静态站点,只有 `index.html` + 一个 JS 模块 + 一个 CSS 文件
- **模型来源**:`wasteland-blender/` 下的 Blender 脚本按参考图程序化生成,导出说明见 `wasteland-blender/README.md`

## 运行

需要 Node >= 18 与 npm:

```bash
npm install   # 安装依赖(three / vite / eslint / prettier / vitest)
npm run dev   # 开发服务器,默认 http://localhost:5173(HMR)
npm run build # 生产构建,产物在 dist/
```

`npm run preview` 用来本地预览 `dist/` 产物、验证打包结果。不要用 `file://` 直接打开 `index.html`:裸模块 `three`、`import.meta.env` 与 `public/` 资产都依赖 Vite 解析。

## 命令

| 命令                              | 作用                                    |
| --------------------------------- | --------------------------------------- |
| `npm run dev`                     | 开发服务器 + HMR(http://localhost:5173) |
| `npm run build`                   | 生产构建到 `dist/`,文件名带内容 hash    |
| `npm run preview`                 | 本地预览 `dist/` 产物                   |
| `npm run lint` / `lint:fix`       | ESLint 检查 / 自动修复                  |
| `npm run format` / `format:check` | Prettier 写入 / 只校验                  |
| `npm run test` / `test:watch`     | Vitest 跑一轮 / watch 模式              |
| `npm run check`                   | `lint` + `format:check` + `test` 一把过 |

## 操作

| 动作       | 操作           |
| ---------- | -------------- |
| 旋转视角   | 按住左键拖拽   |
| 缩放       | 滚轮(2 – 90 m) |
| 平移目标点 | 按住右键拖拽   |

相机默认对准建模时的取景位置(枯树在左、废墟在中左、轿车在右),`controls.maxPolarAngle` 限制了俯仰,不会钻到地面以下。

## 模型约定

- GLB 已按 Three.js 规范导出:+Y Up、Z-up 建模后转换、对象原点在底部中心、不含灯光 / 相机 / 动画 / 体积雾
- 材质是 **13 个 Principled BSDF 压扁后的 baseColorFactor**(程序化节点不进 GLB)。要改颜色改 `wasteland-blender/builders/wst_export.py` 的 `FLAT` 表再重新导出
- 三角面 32,834、212 个 mesh、1.3 MB,目标预算 60,000 以内
- 天穹、雾、三盏灯由 `scripts/main.js` 重建;太阳方位角 34°、仰角 8°,与建模场景一致

## 文件结构

```
index.html            页面:canvas + 加载遮罩 + 操作提示
scripts/main.js       渲染器 / 天穹 / 灯光 / 相机 / GLB 加载 / 渲染循环
scripts/utils.js      assetUrl(path) —— 按 BASE_URL 拼静态资产路径
styles/main.css       页面与遮罩样式
tests/utils.test.js   资产路径拼接单测
public/models/        交付模型 wasteland_scene.glb
wasteland-blender/    建模脚本(builders/)、导出产物(export/)、渲染图(shots/)
```
