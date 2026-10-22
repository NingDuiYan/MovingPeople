// 碰撞解算是纯函数,可以脱离 three 与 DOM 直接测。
import { describe, it, expect } from 'vitest';
import {
  BOUNDARY_R,
  PLAYER_RADIUS,
  clampToIsland,
  penetrationAt,
  resolveObstacles,
  moveWithCollision,
} from '../scripts/collision.js';

const TALL = 1e3; // 顶面远高于脚底:一定挡人
const LOW = -1e3; // 顶面远低于脚底:一定不挡人
const box = (x, z, r, top = TALL) => ({ x, z, r, top });

describe('clampToIsland', () => {
  it('边界内不动', () => {
    const p = { x: 3, z: 4 };
    clampToIsland(p);
    expect(p).toEqual({ x: 3, z: 4 });
  });

  it('边界外按半径缩回,方向不变', () => {
    const p = { x: BOUNDARY_R * 2, z: 0 };
    clampToIsland(p);
    expect(p.x).toBeCloseTo(BOUNDARY_R, 6);
    expect(p.z).toBeCloseTo(0, 6);
  });

  it('斜向超界也落在边界圆上', () => {
    const p = { x: 100, z: 100 };
    clampToIsland(p);
    expect(Math.hypot(p.x, p.z)).toBeCloseTo(BOUNDARY_R, 6);
    // 方向仍沿 (1, 1)
    expect(p.x).toBeCloseTo(p.z, 6);
  });

  it('可传入自定义半径', () => {
    const p = { x: 10, z: 0 };
    clampToIsland(p, 5);
    expect(p.x).toBeCloseTo(5, 6);
  });

  it('正好在边界上不抖动', () => {
    const p = { x: BOUNDARY_R, z: 0 };
    clampToIsland(p);
    expect(p.x).toBeCloseTo(BOUNDARY_R, 6);
  });
});

describe('resolveObstacles', () => {
  it('没碰到就不动', () => {
    const p = { x: 10, z: 0 };
    resolveObstacles(p, 0, [box(0, 0, 1)]);
    expect(p).toEqual({ x: 10, z: 0 });
  });

  it('把位置推到障碍表面外,方向保持', () => {
    const p = { x: 0.5, z: 0 };
    resolveObstacles(p, 0, [box(0, 0, 1)]);
    expect(p.x).toBeCloseTo(1 + PLAYER_RADIUS, 6);
    expect(p.z).toBeCloseTo(0, 6);
  });

  it('已经贴边时不再推出去', () => {
    const p = { x: 1 + PLAYER_RADIUS, z: 0 };
    resolveObstacles(p, 0, [box(0, 0, 1)]);
    expect(p.x).toBeCloseTo(1 + PLAYER_RADIUS, 6);
  });

  it('脚底高于障碍顶面时直接跳过(矮碎石不挡路)', () => {
    const p = { x: 0.1, z: 0 };
    resolveObstacles(p, 0, [box(0, 0, 1, LOW)]);
    expect(p).toEqual({ x: 0.1, z: 0 });
  });

  it('正好落在圆心时沿朝向前方推出,不产生 NaN', () => {
    const p = { x: 0, z: 0 };
    resolveObstacles(p, 0, [box(0, 0, 1)], 0);
    expect(Number.isNaN(p.x)).toBe(false);
    expect(Number.isNaN(p.z)).toBe(false);
    expect(p.x).toBeCloseTo(0, 6);
    expect(p.z).toBeCloseTo(1 + PLAYER_RADIUS, 6); // heading = 0 → +Z
  });

  it('多个重叠障碍会被逐个推出到都不穿透', () => {
    const obstacles = [box(0, 0, 1), box(1.2, 0, 1)];
    const p = { x: 0.6, z: 0 };
    resolveObstacles(p, 0, obstacles);
    expect(penetrationAt(p, 0, obstacles)).toBeLessThanOrEqual(1e-6);
  });

  it('可用自定义角色半径', () => {
    const p = { x: 0.5, z: 0 };
    resolveObstacles(p, 0, [box(0, 0, 1)], 0, 0.5);
    expect(p.x).toBeCloseTo(1.5, 6);
  });
});

describe('penetrationAt', () => {
  it('体外返回 0', () => {
    expect(penetrationAt({ x: 5, z: 0 }, 0, [box(0, 0, 1)])).toBe(0);
  });

  it('体内返回最深穿透量', () => {
    const depth = penetrationAt({ x: 0, z: 0 }, 0, [box(0, 0, 1)]);
    expect(depth).toBeCloseTo(1 + PLAYER_RADIUS, 6);
  });

  it('低于障碍顶面的穿透不计入', () => {
    expect(penetrationAt({ x: 0, z: 0 }, 0, [box(0, 0, 1, LOW)])).toBe(0);
  });

  it('取所有障碍里最深的一个', () => {
    const obstacles = [box(0, 0, 1), box(0.2, 0, 1)];
    const depth = penetrationAt({ x: 0.1, z: 0 }, 0, obstacles);
    expect(depth).toBeCloseTo(1 + PLAYER_RADIUS - 0.1, 6);
  });
});

describe('moveWithCollision', () => {
  it('空旷处按位移前进', () => {
    const p = { x: 0, z: 0 };
    const rolledBack = moveWithCollision(p, 1, 0.5, []);
    expect(rolledBack).toBe(false);
    expect(p.x).toBeCloseTo(1, 6);
    expect(p.z).toBeCloseTo(0.5, 6);
  });

  it('走出岛外会被能量边界拉回', () => {
    const p = { x: BOUNDARY_R - 1, z: 0 };
    moveWithCollision(p, 50, 0, []);
    expect(Math.hypot(p.x, p.z)).toBeLessThanOrEqual(BOUNDARY_R + 1e-6);
  });

  it('撞上挡路障碍后停在表面外,不再穿透', () => {
    const obstacles = [box(0, 0, 1)];
    const p = { x: 3, z: 0 };
    // 从东侧往岛心方向走,依次穿过障碍
    for (let i = 0; i < 40; i++) moveWithCollision(p, -0.2, 0, obstacles);
    expect(penetrationAt(p, 0, obstacles)).toBeLessThanOrEqual(1e-3);
    expect(p.x).toBeGreaterThan(1);
  });

  it('连续多帧不会累积穿透', () => {
    const obstacles = [box(0, 0, 1), box(0.6, 0.6, 0.8), box(-0.6, 0.6, 0.8)];
    const p = { x: 4, z: 0.2 };
    for (let i = 0; i < 60; i++) moveWithCollision(p, -0.12, 0.02, obstacles);
    expect(penetrationAt(p, 0, obstacles)).toBeLessThanOrEqual(1e-3);
  });

  it('解算收敛不了时退回起点,绝不留在实心体内', () => {
    // 巨大障碍:推出圆外会跑到能量边界之外,再被边界拉回来又落进体内 —— 无解
    const obstacles = [box(0, 0, BOUNDARY_R - 0.1)];
    const start = { x: BOUNDARY_R * 0.99, z: 0 };
    const p = { ...start };
    const rolledBack = moveWithCollision(p, -1, 0, obstacles);
    expect(rolledBack).toBe(true);
    expect(p.x).toBeCloseTo(start.x, 6);
    expect(p.z).toBeCloseTo(start.z, 6);
  });
});
