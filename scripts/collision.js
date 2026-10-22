// ============ 角色碰撞解算 ============
// 纯函数集合:只依赖传入的位置对象与障碍列表,不碰 three 的 Mesh、不碰 DOM。
// 这样可以在 Node 里直接单测,也方便换实现(比如以后换成胶囊体)。

import { ISLAND_RADIUS, heightAt } from './utils.js';

export const PLAYER_RADIUS = 0.36; // 角色碰撞半径(m):与 GLB 身形匹配
export const BOUNDARY_R = ISLAND_RADIUS * 0.955; // 环形能量边界半径
const PENETRATION_EPS = 1e-3; // 小于这个量级的残留穿透视为已解算干净
const MAX_PASSES = 3; // 逐圆推出的最多迭代轮数

/**
 * 环形能量边界:超出就把位置按半径缩回来。
 * 原地修改 p 并返回 p。
 */
export function clampToIsland(p, maxR = BOUNDARY_R) {
  const pr = Math.hypot(p.x, p.z);
  if (pr > maxR) {
    const k = maxR / pr;
    p.x *= k;
    p.z *= k;
  }
  return p;
}

/**
 * 实心障碍碰撞(圆 vs 圆):沿法线把位置推到障碍表面外。
 * 只削掉法向穿透量、保留切向位移 —— 贴着岩石走会自然滑开,不会卡死。
 * footY >= top 时跳过:矮于膝盖的碎石不挡路,站在高处也不会被脚下的石头拦住。
 */
export function resolveObstacles(p, footY, obstacles, heading = 0, playerRadius = PLAYER_RADIUS) {
  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let hit = false;
    for (const o of obstacles) {
      if (footY >= o.top) continue;
      const dx = p.x - o.x;
      const dz = p.z - o.z;
      const minD = o.r + playerRadius;
      const d2 = dx * dx + dz * dz;
      if (d2 >= minD * minD) continue;
      const d = Math.sqrt(d2);
      if (d > 1e-4) {
        const k = minD / d;
        p.x = o.x + dx * k;
        p.z = o.z + dz * k;
      } else {
        // 正好落在圆心上:沿当前朝向前方推出,避免除零
        p.x = o.x + Math.sin(heading) * minD;
        p.z = o.z + Math.cos(heading) * minD;
      }
      hit = true;
    }
    if (!hit) break; // 没有穿透就不用再迭代
  }
  return p;
}

/** 当前最深穿透量(> 0 说明位置仍陷在某个实心体内),用于校验推出是否真的干净 */
export function penetrationAt(p, footY, obstacles, playerRadius = PLAYER_RADIUS) {
  let worst = 0;
  for (const o of obstacles) {
    if (footY >= o.top) continue;
    const d = Math.hypot(p.x - o.x, p.z - o.z);
    const pen = o.r + playerRadius - d;
    if (pen > worst) worst = pen;
  }
  return worst;
}

/**
 * 走一步:位移 → 边界收束 → 障碍推出 → 再收束 → 残余穿透校验。
 * 夹在晶簇这种重叠小圆的缝隙里时,逐圆推出会互相打架、几帧内收敛不了,
 * 此时退回起点(起点由归纳法保证是合法的),绝不留在实心体内。
 * 原地修改 p;返回是否发生了回退。
 */
export function moveWithCollision(p, dx, dz, obstacles, heading = 0, playerRadius = PLAYER_RADIUS) {
  const prevX = p.x;
  const prevZ = p.z;
  p.x += dx;
  p.z += dz;
  clampToIsland(p);
  const footY = heightAt(p.x, p.z);
  resolveObstacles(p, footY, obstacles, heading, playerRadius);
  clampToIsland(p); // 被推出后仍需留在能量边界内
  if (penetrationAt(p, heightAt(p.x, p.z), obstacles, playerRadius) > PENETRATION_EPS) {
    p.x = prevX;
    p.z = prevZ;
    return true;
  }
  return false;
}
