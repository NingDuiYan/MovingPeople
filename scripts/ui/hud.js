// ============ HUD:雷达小地图 / 状态读数 / 交互提示 ============
import { ISLAND_RADIUS, heightAt } from '../utils.js';

// ---------- 雷达 ----------
// 固定显示整岛概览:北 = -Z 朝上,青菱 = 终端/NPC,粉圆 = 能量核心
export function createRadar(canvas) {
  const LOGICAL = 150;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = LOGICAL * dpr;
  canvas.height = LOGICAL * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const HALF = LOGICAL / 2;
  const RANGE = 48;                                    // 雷达覆盖半径(m)
  const K = (HALF - 9) / RANGE;                        // 世界 → 米mapping 比例

  // 缓存一次岛岸多边形(Path2D)
  const coast = new Path2D();
  const STEPS = 72;
  for (let i = 0; i <= STEPS; i++) {
    const a = (i / STEPS) * Math.PI * 2;
    // 沿射线找 h=0 的穿越半径
    let rr = 44;
    for (let s = 44; s > 2; s -= 1) {
      if (heightAt(Math.cos(a) * s, Math.sin(a) * s) > 0) { rr = s; break; }
    }
    const px = HALF + Math.cos(a) * rr * K;
    const py = HALF + Math.sin(a) * rr * K;
    if (i === 0) coast.moveTo(px, py); else coast.lineTo(px, py);
  }
  coast.closePath();

  function draw({ px, pz, heading, points, t }) {
    ctx.clearRect(0, 0, LOGICAL, LOGICAL);

    // 水域底
    ctx.beginPath();
    ctx.arc(HALF, HALF, HALF - 6, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(6, 18, 30, 0.85)';
    ctx.fill();
    // 网格环 + 十字线
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.10)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(HALF, HALF, 28, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(HALF, HALF, 52, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(HALF, 6); ctx.lineTo(HALF, LOGICAL - 6);
    ctx.moveTo(6, HALF); ctx.lineTo(LOGICAL - 6, HALF);
    ctx.stroke();

    // 岛体
    ctx.fillStyle = 'rgba(16, 42, 56, 0.95)';
    ctx.fill(coast);
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.55)';
    ctx.lineWidth = 1.5;
    ctx.shadowColor = 'rgba(0, 240, 255, 0.7)';
    ctx.shadowBlur = 6;
    ctx.stroke(coast);
    ctx.shadowBlur = 0;

    // 交互物标记
    for (const p of points) {
      const mx = HALF + p.x * K;
      const my = HALF + p.z * K;
      const pulse = 0.55 + 0.45 * Math.sin(t * 3 + p.x * 0.31 + p.z * 0.17);
      if (p.kind === 'core') {
        ctx.fillStyle = 'rgba(255, 45, 149, 0.9)';
        ctx.shadowColor = '#ff2d95'; ctx.shadowBlur = 8 * pulse;
        ctx.beginPath(); ctx.arc(mx, my, 3.2, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.save();
        ctx.translate(mx, my);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = 'rgba(0, 240, 255, 0.9)';
        ctx.shadowColor = '#00f0ff'; ctx.shadowBlur = 8 * pulse;
        ctx.fillRect(-2.6, -2.6, 5.2, 5.2);
        ctx.restore();
      }
      ctx.shadowBlur = 0;
    }

    // 玩家三角(朝向 heading,角度约定见 main.js)
    const tx = HALF + px * K;
    const ty = HALF + pz * K;
    ctx.save();
    ctx.translate(Math.max(8, Math.min(LOGICAL - 8, tx)), Math.max(8, Math.min(LOGICAL - 8, ty)));
    ctx.rotate(Math.PI - heading);
    ctx.fillStyle = '#eaffff';
    ctx.shadowColor = '#00f0ff'; ctx.shadowBlur = 10;
    ctx.beginPath();
    ctx.moveTo(0, -5.5);
    ctx.lineTo(4.2, 4.5);
    ctx.lineTo(0, 2.2);
    ctx.lineTo(-4.2, 4.5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    ctx.shadowBlur = 0;

    // 北向 N
    ctx.fillStyle = 'rgba(215, 249, 255, 0.8)';
    ctx.font = '10px "Share Tech Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('N', HALF, 13);
  }

  return { draw };
}

// ---------- 状态读数 ----------
export function createStatus({ fpsEl, posEl }) {
  let frames = 0;
  let acc = 0;

  return {
    /** 每帧调用 */
    tick(dt) {
      frames++;
      acc += dt;
      if (acc >= 0.5) {
        fpsEl.textContent = String(Math.round(frames / acc)).padStart(2, '0');
        frames = 0; acc = 0;
      }
    },
    setPos(x, z) {
      posEl.textContent = `X ${x.toFixed(1).padStart(6, ' ')} · Z ${z.toFixed(1).padStart(6, ' ')}`;
    },
  };
}

// ---------- 交互提示 ----------
export function createPrompt({ promptEl, nameEl }) {
  function show(name) {
    if (!promptEl.hidden) nameEl.textContent = name;
    promptEl.hidden = false;
    nameEl.textContent = name;
  }
  function hide() { promptEl.hidden = true; }
  function isVisible() { return !promptEl.hidden; }
  return { show, hide, isVisible };
}
