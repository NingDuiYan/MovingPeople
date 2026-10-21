// ============ 小人:GLB 写实士兵 + 骨骼动画 ============
// 资产:libs/models/Soldier.glb(three.js 官方示例模型,含 Idle/Walk/Run 骨骼动画)
// 未加载完成前用简单占位胶囊,加载后无缝替换进同一 group,避免坐标/相机突变。

import * as THREE from 'three';
import { GLTFLoader } from '../libs/loaders/GLTFLoader.js';
import { WALK_SPEED, RUN_SPEED } from './utils.js';

/**
 * @param {(strength: number, running: boolean) => void} [onStep]
 *   落脚回调:每一步触发一次(尘土与脚步声共用同一拍)。走路 strength 0.62,跑动 1。
 */
export function buildPlayer(THREE, scene, onStep = null) {
  const group = new THREE.Group();
  scene.add(group);

  // ---------- 占位:加载完成前显示 ----------
  const placeholder = new THREE.Group();
  const phMat = new THREE.MeshStandardMaterial({ color: 0x3a4a5c, roughness: 0.6, metalness: 0.3 });
  const phBody = new THREE.Mesh(new THREE.CapsuleGeometry(0.28, 0.9, 4, 8), phMat);
  phBody.position.y = 1.0;
  const phHead = new THREE.Mesh(new THREE.SphereGeometry(0.2, 10, 8), phMat);
  phHead.position.y = 1.68;
  placeholder.add(phBody, phHead);
  group.add(placeholder);

  // 随身补光 + 脚下光环(跟模型无关,始终有效)
  const halo = new THREE.PointLight(0xffd9a8, 2.4, 7, 1.6);
  halo.position.set(0, 1.6, 0);
  group.add(halo);
  const groundGlow = new THREE.Mesh(
    new THREE.CircleGeometry(0.95, 22).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({
      color: 0x00f0ff, transparent: true, opacity: 0.12,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }),
  );
  groundGlow.position.y = 0.04;
  group.add(groundGlow);

  // ---------- GLB 加载与动画 ----------
  let mixer = null;
  let actions = {};
  let current = null;
  let model = null;
  let __clips = [];

  new GLTFLoader().load(
    './libs/models/Soldier.glb',
    (gltf) => {
      model = gltf.scene;
      model.scale.setScalar(1.05);   // 与场景比例匹配
      // Soldier.glb 正面朝 -Z(由脚尖几何判定),本场景约定局部 +Z 为前进方向
      model.rotation.y = Math.PI;
      model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
      group.add(model);

      mixer = new THREE.AnimationMixer(model);
      const A = (name) => {
        const clip = THREE.AnimationClip.findByName(gltf.animations, name);
        return clip ? mixer.clipAction(clip) : null;
      };
      actions.idle = A('Idle');
      actions.walk = A('Walk');
      actions.run  = A('Run');

      __clips = gltf.animations.map((c) => c.name);
      current = actions.idle;
      if (current) { current.play(); }
      // 加载成功,移除占位
      placeholder.visible = false;
    },
    undefined,
    (err) => { console.warn('[player] Soldier.glb load failed:', err?.message ?? err); },
  );

  // ---------- 脚步尘土:小环扩散淡出,粗略提示落脚 ----------
  const PUFF_N = 6;
  const puffs = [];
  for (let i = 0; i < PUFF_N; i++) {
    const m = new THREE.Mesh(
      new THREE.RingGeometry(0.08, 0.16, 12).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: 0xd8c9a8, transparent: true, opacity: 0,
        depthWrite: false, side: THREE.DoubleSide,
      }),
    );
    m.visible = false;
    scene.add(m);
    puffs.push({ mesh: m, life: 0, scaleFrom: 1, size: 1 });
  }
  let puffIdx = 0;
  function puff(strength, running) {
    const p = puffs[puffIdx = (puffIdx + 1) % PUFF_N];
    const yaw = group.rotation.y;
    const side = (puffIdx % 2 === 0 ? 1 : -1) * 0.12;
    p.mesh.position.set(
      group.position.x + Math.cos(yaw) * side,
      group.position.y + 0.05,
      group.position.z - Math.sin(yaw) * side,
    );
    p.mesh.rotation.y = yaw;
    p.life = 1;
    p.size = (running ? 2.0 : 1.5) * strength;
    p.mesh.visible = true;
  }
  function updatePuffs(dt) {
    for (const p of puffs) {
      if (p.life <= 0) continue;
      p.life -= dt * 2.6;
      if (p.life <= 0) { p.mesh.visible = false; p.mesh.material.opacity = 0; continue; }
      const k = 1 - p.life;
      p.mesh.scale.setScalar(p.size * (0.6 + k * 1.5));
      p.mesh.material.opacity = p.life * 0.30;
    }
  }

  // 动画切换:必须先 play() 才会进入 mixer 调度,否则淡入的动作永远不推进
  const FADE_IDLE = 0.22;
  const FADE_LOCO = 0.18;
  function switchTo(next, fade, timeScale) {
    if (!next) return;
    if (next === current) {
      next.setEffectiveTimeScale(timeScale);
      return;
    }
    next.reset();
    next.enabled = true;
    next.setEffectiveTimeScale(timeScale);
    next.setEffectiveWeight(1);
    next.play();
    if (current) next.crossFadeFrom(current, fade, true);
    current = next;
  }

  // 步态参考速度:动作本身对应的自然速度,用来算 timeScale,消除滑步
  const WALK_NOMINAL = 1.55;
  const RUN_NOMINAL = 4.6;

  const anim = { mode: 'idle', step: -1, lean: 0, turn: 0 };

  /**
   * @param {number} dt        帧间隔
   * @param {number} speed     当前水平速度(m/s)
   * @param {number} t         累计时间
   * @param {number} turnRate  转向角速度(rad/s)
   * @param {boolean} backpedal 是否倒着走:动作倒放,脚步方向与位移一致
   */
  function update(dt, speed, t = 0, turnRate = 0, backpedal = false) {
    // 光环呼吸
    groundGlow.material.opacity = 0.09 + 0.05 * (0.5 + 0.5 * Math.sin(t * 2.4));
    groundGlow.scale.setScalar(1 + Math.sin(t * 2.4) * 0.04);

    updatePuffs(dt);
    if (!mixer) return;
    mixer.update(dt);

    // 按真实速度决定步态;timeScale 与速度挂钩,避免脚底打滑
    const moving = speed > 0.15;
    const running = speed > (WALK_SPEED + RUN_SPEED) * 0.5;
    const mode = !moving ? 'idle' : (running ? 'run' : 'walk');

    // 倒着走时用负的 timeScale 让动作反向播放:脚往后退,和位移方向一致
    const dir = backpedal ? -1 : 1;
    if (mode === 'walk') {
      const ts = THREE.MathUtils.clamp(speed / WALK_NOMINAL, 0.7, 1.9) * dir;
      switchTo(actions.walk, FADE_LOCO, ts);
    } else if (mode === 'run') {
      const ts = THREE.MathUtils.clamp(speed / RUN_NOMINAL, 0.8, 1.7) * dir;
      switchTo(actions.run, FADE_LOCO, ts);
    } else {
      switchTo(actions.idle, FADE_IDLE, 1);
    }

    if (mode !== anim.mode) anim.mode = mode;

    // 转向侧倾:转弯时上身向内侧压,避免"平移滑行"感
    // 角速度先做平滑,避免单帧尖峰;站定(moving=false)时目标一律为 0,保证静止时永远站直
    anim.turn += (turnRate - anim.turn) * Math.min(1, dt * 10);
    const leanTarget = moving ? THREE.MathUtils.clamp(-anim.turn * 0.16, -0.22, 0.22) : 0;
    anim.lean += (leanTarget - anim.lean) * Math.min(1, dt * 8);
    if (model) model.rotation.z = anim.lean;

    // 步频脉冲驱动脚步尘土与脚步声(跑动更明显)
    if (current && moving) {
      const stride = current.time / (running ? 0.34 : 0.52);
      if (Math.floor(stride) !== anim.step) {
        anim.step = Math.floor(stride);
        const strength = running ? 1 : 0.62;
        puff(strength, running);
        if (onStep) onStep(strength, running);
      }
    }
  }

  // 调试信息:确认 GLB 与骨骼动画是否就绪
  function debug() {
    let skinned = 0, meshes = 0;
    group.traverse((o) => { if (o.isSkinnedMesh) skinned++; else if (o.isMesh) meshes++; });
    const box = new THREE.Box3().setFromObject(group);
    const size = box.getSize(new THREE.Vector3());
    const act = current ? {
      name: current.getClip().name,
      time: +current.time.toFixed(3),
      weight: +current.getEffectiveWeight().toFixed(3),
      timeScale: +current.getEffectiveTimeScale().toFixed(3),
      running: current.isRunning(),
    } : null;
    return {
      loaded: !!model, clips: __clips, skinned, meshes,
      mode: anim.mode, action: act,
      height: +size.y.toFixed(2),
      bbox: [+size.x.toFixed(2), +size.y.toFixed(2), +size.z.toFixed(2)],
    };
  }

  return { group, update, debug };
}
