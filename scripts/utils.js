// ============ 数学与地形工具 ============
// 场景网格与角色行走共用同一张高度函数 —— 保证「所见即所走」。

export const ISLAND_RADIUS = 40; // 小岛名义半径(m)
export const WATER_LEVEL = 0; // 海平面高度
export const WALK_SPEED = 2.4; // 常速 m/s(人类快步量级,配合骨骼步频)
export const RUN_SPEED = 6.0; // 疾跑 m/s

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

/**
 * 静态资产 URL:public/ 下的文件按 Vite 的 BASE_URL 拼接。
 * BASE_URL 以 '/' 结尾,dev 为 '/',build 为相对基址,子目录部署也不会拼错。
 */
export const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;
export const lerp = (a, b, t) => a + (b - a) * t;
/** 帧率无关阻尼插值 */
export const damp = (a, b, lambda, dt) => lerp(a, b, 1 - Math.exp(-lambda * dt));

/** 最短路径角度插值 */
export function lerpAngle(a, b, t) {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

/** 确定性伪随机(mulberry32),用于岛屿散布物 */
export function rng(seed = 1337) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 平滑阶梯,支持递减边缘(e0 > e1) */
function smoothstep(e0, e1, x) {
  const t = clamp((x - e0) / (e1 - e0), 0, 1);
  return t * t * (3 - 2 * t);
}

/**
 * 小岛高度场:同心衰减 + 多频正弦噪声(纯确定性,零依赖)
 * 岛心约 4~6m,滩涂向水下过渡;r >= ISLAND_RADIUS 时全水下。
 */
export function heightAt(x, z) {
  const r = Math.hypot(x, z);
  if (r >= ISLAND_RADIUS) return -4;
  const base = smoothstep(ISLAND_RADIUS * 0.92, ISLAND_RADIUS * 0.2, r);
  const noise =
    Math.sin(x * 0.28 + z * 0.11) * Math.cos(z * 0.19 + x * 0.07) * 0.8 +
    Math.sin(x * 0.09 - z * 0.23 + 1.3) * 0.9 +
    Math.cos(x * 0.45) * Math.sin(z * 0.41) * 0.35;
  const h = base * 5.2 + noise * (0.35 + 0.65 * base) - 0.6;
  // 海岸过渡:外侧压低到水下
  const shore = smoothstep(ISLAND_RADIUS * 0.98, ISLAND_RADIUS * 0.72, r);
  return h * shore + (1 - shore) * -1.8;
}
