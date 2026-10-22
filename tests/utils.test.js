// ============ utils.js 单测:地形高度场与数学工具 ============
// 断言只针对可观察行为;固定数字(种子序列、代表点高度)都来自真实运行结果,方便以后改了地形立刻发现。
import { describe, expect, it } from 'vitest';
import {
  ISLAND_RADIUS,
  RUN_SPEED,
  WALK_SPEED,
  WATER_LEVEL,
  clamp,
  assetUrl,
  damp,
  heightAt,
  lerp,
  lerpAngle,
  rng,
} from '../scripts/utils.js';

const TWO_PI = Math.PI * 2;

/** 沿单轴从岛心往外扫,返回相邻采样点的最大高度跳变 */
function maxStepJump(axis, limit, step = 0.1) {
  let prev = null;
  let max = 0;
  for (let r = 0; r <= limit; r += step) {
    const h = axis === 'x' ? heightAt(r, 0) : heightAt(0, r);
    if (prev !== null) max = Math.max(max, Math.abs(h - prev));
    prev = h;
  }
  return max;
}

describe('常量', () => {
  it('速度档位与地形尺度互相自洽', () => {
    expect(ISLAND_RADIUS).toBe(40);
    expect(WATER_LEVEL).toBe(0);
    expect(WALK_SPEED).toBeGreaterThan(0);
    expect(RUN_SPEED).toBeGreaterThan(WALK_SPEED);
  });
});

describe('assetUrl', () => {
  it('把 public/ 下的相对路径拼到 BASE_URL 后面,不会拼出双斜杠', () => {
    const url = assetUrl('models/Soldier.glb');
    expect(url.endsWith('models/Soldier.glb')).toBe(true);
    expect(url).not.toContain('//');
  });
});

describe('clamp', () => {
  it('区间内的值原样返回', () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(0.25, 0, 1)).toBe(0.25);
  });

  it('越界时夹到最近的边界', () => {
    expect(clamp(-5, 0, 10)).toBe(0);
    expect(clamp(15, 0, 10)).toBe(10);
  });

  it('端点算作区间内', () => {
    expect(clamp(0, 0, 10)).toBe(0);
    expect(clamp(10, 0, 10)).toBe(10);
  });

  it('支持全负区间', () => {
    expect(clamp(-100, -10, -4)).toBe(-10);
    expect(clamp(-2, -10, -4)).toBe(-4);
    expect(clamp(-7, -10, -4)).toBe(-7);
  });
});

describe('lerp', () => {
  it('t=0 / t=1 分别落在两端', () => {
    expect(lerp(0, 10, 0)).toBe(0);
    expect(lerp(0, 10, 1)).toBe(10);
  });

  it('按比例插值', () => {
    expect(lerp(0, 10, 0.25)).toBe(2.5);
    expect(lerp(4, 20, 0.5)).toBe(12);
  });

  it('反向插值(从大值回落到小值)也成立', () => {
    expect(lerp(10, 0, 0.25)).toBe(7.5);
  });
});

describe('damp', () => {
  it('从 0 收敛到 10:单调递增,永不越过目标', () => {
    let v = 0;
    const samples = [];
    for (let i = 0; i < 200; i++) {
      v = damp(v, 10, 10, 1 / 60);
      samples.push(v);
    }
    samples.forEach((s, i) => {
      expect(s).toBeGreaterThan(i === 0 ? 0 : samples[i - 1]);
      expect(s).toBeLessThanOrEqual(10);
    });
    expect(samples[samples.length - 1]).toBeGreaterThan(9.99);
  });

  it('从 10 回落到 0:单调递减,永不越过目标', () => {
    let v = 10;
    const samples = [];
    for (let i = 0; i < 200; i++) {
      v = damp(v, 0, 10, 1 / 60);
      samples.push(v);
    }
    samples.forEach((s, i) => {
      expect(s).toBeLessThan(i === 0 ? 10 : samples[i - 1]);
      expect(s).toBeGreaterThanOrEqual(0);
    });
    expect(samples[samples.length - 1]).toBeLessThan(0.01);
  });

  it('足够多帧后基本贴住目标', () => {
    let v = 0;
    for (let i = 0; i < 100; i++) v = damp(v, 10, 10, 1 / 60);
    expect(v).toBeCloseTo(10, 4);
  });

  it('每帧走的距离与 dt 同向:dt 越大越接近目标', () => {
    expect(damp(0, 10, 10, 1 / 30)).toBeGreaterThan(damp(0, 10, 10, 1 / 60));
  });
});

describe('lerpAngle', () => {
  it('同向转动 0 → π/2 的中点是 π/4', () => {
    expect(lerpAngle(0, Math.PI / 2, 0.5)).toBeCloseTo(Math.PI / 4, 12);
  });

  it('0 → 3π/2 走短弧,中点在 -π/4 而不是 3π/4', () => {
    expect(lerpAngle(0, (3 * Math.PI) / 2, 0.5)).toBeCloseTo(-Math.PI / 4, 12);
  });

  it('0 → -3π/2 同理取 +π/4', () => {
    expect(lerpAngle(0, (-3 * Math.PI) / 2, 0.5)).toBeCloseTo(Math.PI / 4, 12);
  });

  it('跨越 ±π 接缝时从缺口穿过去,不绕远路', () => {
    const a = Math.PI - 0.1;
    const b = -Math.PI + 0.1;
    // 短弧是「越过 π」的那一段,中点正好落在 π 上
    expect(lerpAngle(a, b, 0.5)).toBeCloseTo(Math.PI, 10);
  });

  it('t=0 与 t=1 落在两端(终点可能等价偏移了整圈)', () => {
    expect(lerpAngle(0, Math.PI / 2, 0)).toBe(0);
    const end = lerpAngle(0, (3 * Math.PI) / 2, 1);
    expect(end).toBeCloseTo(-Math.PI / 2, 12);
    expect(end - 0).toBeGreaterThanOrEqual(-Math.PI);
  });

  it('任意目标下单帧转动量都不超过 π', () => {
    const from = 0.3;
    for (let i = -12; i <= 12; i++) {
      const to = (i / 12) * Math.PI;
      expect(Math.abs(lerpAngle(from, to, 1) - from)).toBeLessThanOrEqual(Math.PI + 1e-9);
    }
  });
});

describe('rng(20240521)', () => {
  it('前 6 个值与真实运行结果一致(场景布点依赖它)', () => {
    const next = rng(20240521);
    const got = [next(), next(), next(), next(), next(), next()];
    const expected = [
      0.10213249875232577, 0.15027883159928024, 0.943591229384765, 0.3221716075204313,
      0.9079722214955837, 0.6486258849035949,
    ];
    expect(got).toEqual(expected);
  });

  it('同种子的两个实例产生完全相同的序列', () => {
    const a = rng(20240521);
    const b = rng(20240521);
    for (let i = 0; i < 20; i++) expect(a()).toBe(b());
  });

  it('默认种子也是确定的(首值固定)', () => {
    expect(rng()()).toBe(0.1844118325971067);
    expect(rng()()).toBe(rng()());
  });

  it('输出落在 [0, 1) 且不重复', () => {
    const next = rng(20240521);
    const seen = new Set();
    let min = 1;
    let max = 0;
    for (let i = 0; i < 1000; i++) {
      const v = next();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
      min = Math.min(min, v);
      max = Math.max(max, v);
      seen.add(v);
    }
    expect(min).toBeLessThan(0.01);
    expect(max).toBeGreaterThan(0.99);
    expect(seen.size).toBe(1000);
  });

  it('换种子就换序列', () => {
    expect(rng(1)()).not.toBe(rng(2)());
  });
});

describe('heightAt', () => {
  const LIMIT = ISLAND_RADIUS * 0.98; // 39.2m:岸坡完全沉到 -1.8 的位置

  it('岛心是高地,远高于海平面', () => {
    expect(heightAt(0, 0)).toBeGreaterThan(WATER_LEVEL + 4);
    expect(heightAt(0, 0)).toBeCloseTo(5.4672, 3);
  });

  it('岛内半径 8m 的范围内处处高于海平面 3m', () => {
    for (let a = 0; a < TWO_PI; a += Math.PI / 16) {
      for (let r = 0; r <= 8; r += 0.5) {
        expect(heightAt(Math.cos(a) * r, Math.sin(a) * r)).toBeGreaterThan(WATER_LEVEL + 3);
      }
    }
  });

  it('从 8m 往岛外走高强单调下降(视线可及的下坡)', () => {
    let prev = heightAt(8, 0);
    for (let r = 8.05; r <= 39; r += 0.05) {
      const h = heightAt(r, 0);
      expect(h).toBeLessThan(prev);
      prev = h;
    }
  });

  it('海岸线落在 28~30m 之间(高度穿过海平面)', () => {
    expect(heightAt(28, 0)).toBeGreaterThan(WATER_LEVEL);
    expect(heightAt(30, 0)).toBeLessThan(WATER_LEVEL);
  });

  it('岛缘已在水下,但还没到海底常数', () => {
    const h = heightAt(39, 0);
    expect(h).toBeLessThan(WATER_LEVEL);
    expect(h).toBeGreaterThan(-2);
    expect(h).toBeCloseTo(-1.8, 2);
  });

  it('r >= ISLAND_RADIUS 一律返回海底高度 -4', () => {
    expect(heightAt(ISLAND_RADIUS, 0)).toBe(-4);
    expect(heightAt(60, 0)).toBe(-4);
    expect(heightAt(120.5, -33)).toBe(-4);
    expect(heightAt(1e6, 1e6)).toBe(-4);
  });

  it('岛内径向连续:0.1m 步长下相邻高度差 < 0.1m', () => {
    expect(maxStepJump('x', LIMIT)).toBeLessThan(0.1);
    expect(maxStepJump('z', LIMIT)).toBeLessThan(0.1);
  });

  it('岛界处存在 -1.8 → -4 的台阶(现状行为,已在报告里登记)', () => {
    expect(heightAt(ISLAND_RADIUS - 0.01, 0)).toBeGreaterThan(-2);
    expect(heightAt(ISLAND_RADIUS, 0)).toBe(-4);
  });
});
