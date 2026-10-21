// ============ 程序化贴图工厂 ============
// 全部用 Canvas 现场生成,零外部资源依赖。
import { rng } from './utils.js';

/** 径向渐变辉光贴图:用于光晕 Sprite 与粒子 */
export function makeGlowTexture(THREE, color = 0x00f0ff) {
  const c = new THREE.Color(color);
  const rgb = Math.round(c.r * 255) + ',' + Math.round(c.g * 255) + ',' + Math.round(c.b * 255);
  const S = 128;
  const half = S / 2;
  const cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const ctx = cv.getContext('2d');
  const grd = ctx.createRadialGradient(half, half, 0, half, half, half);
  grd.addColorStop(0.0, 'rgba(' + rgb + ',1)');
  grd.addColorStop(0.22, 'rgba(' + rgb + ',0.62)');
  grd.addColorStop(0.52, 'rgba(' + rgb + ',0.18)');
  grd.addColorStop(1.0, 'rgba(' + rgb + ',0)');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, S, S);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** 建筑窗格贴图:暗底 + 随机点亮的窗,用作 emissiveMap */
export function makeWindowTexture(THREE, seed = 91) {
  const W = 128;
  const H = 256;
  const rand = rng(seed);
  const cv = document.createElement('canvas');
  cv.width = W;
  cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, W, H);
  const cols = 10;
  const rows = 30;
  const cw = W / cols;
  const ch = H / rows;
  const palette = ['#00f0ff', '#ff2d95', '#8affff', '#ffd08a', '#4a7dff'];
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      if (rand() > 0.44) continue;
      ctx.fillStyle = palette[(rand() * palette.length) | 0];
      ctx.globalAlpha = 0.25 + rand() * 0.75;
      const pad = 0.18 + rand() * 0.16;
      ctx.fillRect(x * cw + cw * pad, y * ch + ch * pad, cw * (1 - pad * 2), ch * (1 - pad * 2));
    }
  }
  ctx.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

/** 竖排霓虹字条贴图:用于近景灯牌 */
export function makeSignTexture(THREE, text, color) {
  const W = 64;
  const H = 256;
  const cv = document.createElement('canvas');
  cv.width = W;
  cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, W, H);
  ctx.font = 'bold 44px "Share Tech Mono", monospace';
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 18;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const chars = text.split('');
  const step = H / (chars.length + 1);
  chars.forEach((ch, i) => ctx.fillText(ch, W / 2, step * (i + 1)));
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** 圆形点精灵:给 Points 粒子用,避免 sizeAttenuation 放大后变成硬边方块 */
export function makeDotTexture(THREE) {
  const S = 64;
  const half = S / 2;
  const cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const ctx = cv.getContext('2d');
  const grd = ctx.createRadialGradient(half, half, 0, half, half, half);
  grd.addColorStop(0.0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.35, 'rgba(255,255,255,0.92)');
  grd.addColorStop(0.68, 'rgba(255,255,255,0.28)');
  grd.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, S, S);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
