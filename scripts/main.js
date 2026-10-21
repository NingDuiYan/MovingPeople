// ============ 主入口:渲染器 / 相机 / 输入 / 交互主循环 ============
import { ISLAND_RADIUS, WATER_LEVEL, heightAt, clamp, damp, lerpAngle, WALK_SPEED, RUN_SPEED } from './utils.js';
import { buildIsland } from './island.js';
import { buildPlayer } from './player.js';
import { createRadar, createStatus, createPrompt } from './ui/hud.js';
import { createDialog } from './ui/dialog.js';
import { createJoystick } from './ui/joystick.js';
import { createPostFX } from './postfx.js';
import { Sky } from '../libs/objects/Sky.js';
import { Water } from '../libs/objects/Water.js';
import { GLTFLoader } from '../libs/loaders/GLTFLoader.js';

const els = {
  canvas: document.getElementById('scene'),
  radar: document.getElementById('radar'),
  fps: document.getElementById('hud-fps'),
  pos: document.getElementById('hud-pos'),
  keys: document.getElementById('hud-keys'),
  prompt: document.getElementById('interact-prompt'),
  promptName: document.getElementById('interact-name'),
  touchInteract: document.getElementById('touch-interact'),
  dialog: document.getElementById('dialog'),
  dialogName: document.getElementById('dialog-name'),
  dialogText: document.getElementById('dialog-text'),
  dialogClose: document.getElementById('dialog-close'),
  joystick: document.getElementById('joystick'),
  joyKnob: document.getElementById('joy-knob'),
  loader: document.getElementById('loader'),
  fatal: document.getElementById('fatal'),
  fatalMsg: document.getElementById('fatal-msg'),
};

function fatal(msg) {
  els.fatalMsg.textContent = msg;
  els.fatal.hidden = false;
  els.loader.hidden = true;
}

const INTERACT_RADIUS = 3.2;

const dialogData = {
  npc: {
    name: '维修机器人 R-7',
    lines: [
      '嗡……信号接入完毕。欢迎来到霓虹孤岛,探索者。',
      '我是 R-7,负责维护这座岛的数据链。',
      '用 W A S D 到处走走(移动端拖动摇杆),Shift 疾跑。',
      '靠近发光装置会亮起提示,按 E 同步数据。',
      '岛上散落两枚能量核心,雷达上粉色圆标就是它们。',
      '小心别走出环形能量边界——外面是深水。',
    ],
  },
  terminal: {
    name: '数据终端 DL-07',
    lines: [
      '> 接入 DL-07 …… 握手成功。',
      '> 同步岛屿网格:实体 100% / 记忆体 47%。',
      '记忆体有缺损。能量核心是修复它的钥匙。',
      '两枚核心已标记在你的雷达上,去把它们带回来。',
    ],
  },
  core: {
    name: '能量核心',
    lines: [
      '能量核心已锁定。',
      '嗡——储存环充能 47%……81%……充能完成。',
      '这段数据将被送回主城。谢谢你,探索者。',
    ],
  },
};

async function boot() {
  let THREE;
  try {
    THREE = await import('three');
  } catch (err) {
    fatal('无法加载 Three.js(CDN 需联网): ' + err.message);
    return;
  }

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: els.canvas, antialias: true });
  } catch (err) {
    fatal('设备不支持 WebGL: ' + err.message);
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  // ACES 色调映射在 postfx 合成阶段执行(渲染到 RT 时 renderer 的 toneMapping 不生效)
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x12202c, 0.0015);

  const camera = new THREE.PerspectiveCamera(58, window.innerWidth / window.innerHeight, 0.1, 1200);

  // ---------- 写实光照:Sky 大气散射 + 黄昏太阳联动 ----------
  const sun = new THREE.Vector3();
  const sky = new Sky();
  sky.scale.setScalar(10000);
  scene.add(sky);
  const skyU = sky.material.uniforms;
  skyU.turbidity.value = 9.5;
  skyU.rayleigh.value = 2.45;
  skyU.mieCoefficient.value = 0.012;
  skyU.mieDirectionalG.value = 0.86;
  // 黄昏低角度太阳(偏暖,与霓虹夜景融合)
  const phi = THREE.MathUtils.degToRad(90 - 30);  // 太阳仰角 30°:地面获得有效照明,仍保留暖调
  const theta = THREE.MathUtils.degToRad(205);     // 方位角
  sun.setFromSphericalCoords(1, phi, theta);
  skyU.sunPosition.value.copy(sun);

  // 太阳主光(金橙暖色,投射阴影)
  const sunLight = new THREE.DirectionalLight(0xffd2a6, 3.6);
  sunLight.position.copy(sun).multiplyScalar(90);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(2048, 2048);
  sunLight.shadow.radius = 2.2;
  sunLight.shadow.camera.left = -56;
  sunLight.shadow.camera.right = 56;
  sunLight.shadow.camera.top = 56;
  sunLight.shadow.camera.bottom = -56;
  sunLight.shadow.camera.near = 20;
  sunLight.shadow.camera.far = 320;
  sunLight.shadow.bias = -0.0004;
  sunLight.shadow.normalBias = 0.02;
  scene.add(sunLight);

  // 天光环境(HI 半球冷暖)
  scene.add(new THREE.HemisphereLight(0x9fb8d2, 0x2b3038, 0.42));
  scene.add(new THREE.AmbientLight(0x3d4a5c, 0.20));

  // 品红霓虹补光(保留赛博主题染色)
  const rim = new THREE.DirectionalLight(0xff2d95, 0.35);
  rim.position.set(-46, 26, -38);
  scene.add(rim);

  // 青色补光
  const fill = new THREE.DirectionalLight(0x1d7f9c, 0.3);
  fill.position.set(-30, 14, 52);
  scene.add(fill);

  // ---------- 写实海面:Water 平面反射 ----------
  const waterNormals = await new THREE.TextureLoader().loadAsync('./libs/textures/waternormals.jpg');
  waterNormals.wrapS = waterNormals.wrapT = THREE.RepeatWrapping;
  const water = new Water(new THREE.PlaneGeometry(2200, 2200), {
    textureWidth: 256,
    textureHeight: 256,
    waterNormals,
    sunDirection: sun.clone(),
    sunColor: 0xffe2bd,
    waterColor: 0x041a26,
    distortionScale: 3.1,
    fog: true,
  });
  water.rotation.x = -Math.PI / 2;
  water.position.y = WATER_LEVEL;
  scene.add(water);

  // IBL:用 Sky 生成 PMREM 环境贴图 —— 金属与粗糙表面获得真实环境反射
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const skyEnvScene = new THREE.Scene();
  skyEnvScene.add(sky);                       // 临时移入环境场景
  const envRT = pmrem.fromScene(skyEnvScene);
  scene.add(sky);                             // 移回主场景
  scene.environment = envRT.texture;
  scene.environmentIntensity = 0.38;
  pmrem.dispose();

// ---------- 世界 ----------
  const island = buildIsland(THREE, scene);
  const player = buildPlayer(THREE, scene);
  const playerPos = player.group.position;

  playerPos.set(2, heightAt(2, 2), 2);
  player.group.rotation.y = Math.PI * 0.85;

  // ---------- 后期处理 ----------
  const postfx = createPostFX(THREE, renderer, scene, camera);
  const drawBuf = new THREE.Vector2();
  function syncPostSize() {
    renderer.getDrawingBufferSize(drawBuf);
    postfx.setSize(drawBuf.x, drawBuf.y);
  }
  syncPostSize();

  // ---------- HUD ----------
  const radar = createRadar(els.radar);
  const status = createStatus({ fpsEl: els.fps, posEl: els.pos });
  const prompt = createPrompt({ promptEl: els.prompt, nameEl: els.promptName });
  const dialog = createDialog({
    root: els.dialog, nameEl: els.dialogName, textEl: els.dialogText, closeBtn: els.dialogClose,
  });

  // ---------- 触屏模式 ----------
  let touchMode = window.matchMedia('(pointer: coarse)').matches;
  const applyTouchMode = () => document.body.classList.toggle('touch-mode', touchMode);
  applyTouchMode();
  const joy = createJoystick(els.joystick, els.joyKnob);
  window.addEventListener('touchstart', function onFirstTouch() {
    if (!touchMode) { touchMode = true; applyTouchMode(); }
    window.removeEventListener('touchstart', onFirstTouch);
  }, { passive: true });

  // ---------- 键盘输入 ----------
  const keys = new Set();
  window.addEventListener('keydown', (e) => {
    if (e.repeat) return;
    if (e.code === 'KeyE') {
      e.preventDefault();
      onInteract();
      return;
    }
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
      e.preventDefault();
    }
    keys.add(e.code);
  });
  window.addEventListener('keyup', (e) => keys.delete(e.code));
  window.addEventListener('blur', () => keys.clear());

  // ---------- 视角拖拽 ----------
  const cam = { yaw: Math.PI * 0.85, pitch: 0.28, dist: 6.6, distTarget: 6.6 };
  let drag = null;
  els.canvas.addEventListener('pointerdown', (e) => {
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY };
    els.canvas.setPointerCapture(e.pointerId);
  });
  els.canvas.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    cam.yaw -= (e.clientX - drag.x) * 0.0042;
    cam.pitch = clamp(cam.pitch + (e.clientY - drag.y) * 0.0032, -0.2, 1.15);
    drag.x = e.clientX;
    drag.y = e.clientY;
  });
  const endDrag = (e) => { if (drag && e.pointerId === drag.id) drag = null; };
  els.canvas.addEventListener('pointerup', endDrag);
  els.canvas.addEventListener('pointercancel', endDrag);
  els.canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    cam.distTarget = clamp(cam.distTarget + e.deltaY * 0.008, 3.2, 14);
  }, { passive: false });
  els.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

  // ---------- 交互 ----------
  let nearTarget = null;
  function onInteract() {
    if (dialog.isOpen()) {
      dialog.advance();
      return;
    }
    if (nearTarget) {
      const d = dialogData[nearTarget.kind];
      if (d) dialog.open(d.name, d.lines);
    }
  }
  els.touchInteract.addEventListener('click', onInteract);

  // ---------- 自适应 ----------
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    syncPostSize();
  });

  // ---------- 主循环 ----------
  const forward = new THREE.Vector3();
  const right = new THREE.Vector3();
  const move = new THREE.Vector3();
  const camTarget = new THREE.Vector3();
  const radarPoints = island.interactives.map((p) => ({ x: p.pos.x, z: p.pos.z, kind: p.kind }));

  const clock = new THREE.Clock();
  let elapsed = 0;
  let heading = player.group.rotation.y;
  let prevHeading = heading;
  let turnRate = 0;
  let started = false;

  function frame() {
    requestAnimationFrame(frame);
    const rawDt = clock.getDelta();
    const dt = Math.min(rawDt, 0.05);
    elapsed += dt;

    // 1) 输入向量(键盘 + 摇杆)
    let ix = (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0)
      - (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0) + joy.vec.x;
    let iy = (keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0)
      - (keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0) + joy.vec.y;
    const len = Math.hypot(ix, iy);
    if (len > 1) { ix /= len; iy /= len; }
    const active = len > 0.08;
    const run = keys.has('ShiftLeft') || keys.has('ShiftRight');

    // 2) 移动(以相机朝向为基准)
    forward.set(-Math.sin(cam.yaw), 0, -Math.cos(cam.yaw));
    right.set(Math.cos(cam.yaw), 0, -Math.sin(cam.yaw));
    if (active) {
      move.set(0, 0, 0).copy(forward).multiplyScalar(iy).addScaledVector(right, ix);
      const speed = run ? RUN_SPEED : WALK_SPEED;
      playerPos.x += move.x * speed * dt;
      playerPos.z += move.z * speed * dt;
      const pr = Math.hypot(playerPos.x, playerPos.z);
      const maxR = ISLAND_RADIUS * 0.955;
      if (pr > maxR) {
        playerPos.x *= maxR / pr;
        playerPos.z *= maxR / pr;
      }
      heading = lerpAngle(heading, Math.atan2(move.x, move.z), Math.min(1, dt * 12));
      player.group.rotation.y = heading;
      let dh = heading - prevHeading;
      if (dh > Math.PI) dh -= Math.PI * 2;
      if (dh < -Math.PI) dh += Math.PI * 2;
      turnRate = dt > 0 ? dh / dt : 0;
    }

    prevHeading = heading;

    // 3) 贴地
    const groundY = Math.max(heightAt(playerPos.x, playerPos.z), -0.22);
    playerPos.y = damp(playerPos.y, groundY, 14, dt);

    // 4) 行走动画:传真实速度(m/s)与转向速率,驱动步态与侧倾
    const curSpeed = active ? (run ? RUN_SPEED : WALK_SPEED) * Math.min(1, len) : 0;
    player.update(dt, curSpeed, elapsed, turnRate);

    // 5) 相机跟随
    cam.dist = damp(cam.dist, cam.distTarget, 8, dt);
    const cp = Math.cos(cam.pitch);
    const sp = Math.sin(cam.pitch);
    camTarget.set(
      playerPos.x + Math.sin(cam.yaw) * cam.dist * cp,
      playerPos.y + 1.5 + cam.dist * sp,
      playerPos.z + Math.cos(cam.yaw) * cam.dist * cp,
    );
    camTarget.y = Math.max(camTarget.y, heightAt(camTarget.x, camTarget.z) + 0.5);
    camera.position.lerp(camTarget, Math.min(1, dt * 9));
    camera.lookAt(playerPos.x, playerPos.y + 1.5, playerPos.z);

    // 6) 交互检测
    nearTarget = null;
    let bestD2 = INTERACT_RADIUS * INTERACT_RADIUS;
    for (const p of island.interactives) {
      const dx = p.pos.x - playerPos.x;
      const dz = p.pos.z - playerPos.z;
      const d2 = dx * dx + dz * dz;
      if (d2 < bestD2) { bestD2 = d2; nearTarget = p; }
    }
    if (nearTarget && !dialog.isOpen()) prompt.show(nearTarget.name);
    else prompt.hide();
    els.touchInteract.hidden = !(touchMode && (dialog.isOpen() || nearTarget));

    // 7) 世界与 HUD 更新
    island.update(dt, elapsed);
    radar.draw({ px: playerPos.x, pz: playerPos.z, heading, points: radarPoints, t: elapsed });
    status.tick(rawDt);
    status.setPos(playerPos.x, playerPos.z);

    water.material.uniforms.time.value += dt * 0.6;
    postfx.render(elapsed);

    // 8) 首帧揭幕 + 自动欢迎对白
    if (!started) {
      started = true;
      els.loader.classList.add('is-done');
      setTimeout(() => {
        if (!dialog.isOpen()) dialog.open(dialogData.npc.name, dialogData.npc.lines);
      }, 1400);
    }
  }
  // 调试句柄:浏览器控制台可用 __neon.scene 等排查场景
  window.__neon = { scene, camera, renderer, player, island, water, sun };

  frame();
}

boot().catch((err) => {
  fatal('启动失败: ' + (err && err.message ? err.message : String(err)));
});
