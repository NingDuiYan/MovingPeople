// ============ 主入口:渲染器 / 相机 / 输入 / 交互主循环 ============
import {
  ISLAND_RADIUS,
  WATER_LEVEL,
  heightAt,
  clamp,
  damp,
  lerpAngle,
  assetUrl,
  WALK_SPEED,
  RUN_SPEED,
} from './utils.js';
import { buildIsland } from './island.js';
import { buildPlayer } from './player.js';
import { createStepAudio } from './audio.js';
import { createRadar, createStatus, createPrompt } from './ui/hud.js';
import { createDialog } from './ui/dialog.js';
import { createJoystick } from './ui/joystick.js';
import { createSettings } from './ui/settings.js';
import { readBinds, codeToLabel, mirrorCode } from './keybinds.js';
import { createToast } from './ui/toast.js';
import { createPostFX } from './postfx.js';
import * as THREE from 'three';
import { Sky } from 'three/examples/jsm/objects/Sky.js';
import { Water } from 'three/examples/jsm/objects/Water.js';

const els = {
  canvas: document.getElementById('scene'),
  radar: document.getElementById('radar'),
  fps: document.getElementById('hud-fps'),
  pos: document.getElementById('hud-pos'),
  msg: document.getElementById('scene-msg'),
  msgText: document.getElementById('scene-msg-text'),
  prompt: document.getElementById('interact-prompt'),
  promptName: document.getElementById('interact-name'),
  touchInteract: document.getElementById('touch-interact'),
  dialog: document.getElementById('dialog'),
  dialogName: document.getElementById('dialog-name'),
  dialogText: document.getElementById('dialog-text'),
  dialogClose: document.getElementById('dialog-close'),
  settings: document.getElementById('settings'),
  settingsOpen: document.getElementById('settings-open'),
  settingsClose: document.getElementById('settings-close'),
  soundToggle: document.getElementById('sound-toggle'),
  lookRadios: Array.from(document.querySelectorAll('input[name="look-mode"]')),
  joystick: document.getElementById('joystick'),
  joyKnob: document.getElementById('joy-knob'),
  loader: document.getElementById('loader'),
  fatal: document.getElementById('fatal'),
  fatalMsg: document.getElementById('fatal-msg'),
  keyList: document.getElementById('keybind-list'),
  keyPresets: document.getElementById('key-presets'),
  keyReset: document.getElementById('keybind-reset'),
  keyHint: document.getElementById('keybind-hint'),
  sensInput: document.getElementById('look-sens'),
  sensSave: document.getElementById('look-sens-save'),
  bindCaps: Array.from(document.querySelectorAll('[data-bind]')),
};

function fatal(msg) {
  els.fatalMsg.textContent = msg;
  els.fatal.hidden = false;
  els.loader.hidden = true;
}

const INTERACT_RADIUS = 3.2;
const PLAYER_RADIUS = 0.36; // 角色碰撞半径(m):与 GLB 身形匹配

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
  const phi = THREE.MathUtils.degToRad(90 - 30); // 太阳仰角 30°:地面获得有效照明,仍保留暖调
  const theta = THREE.MathUtils.degToRad(205); // 方位角
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
  scene.add(new THREE.AmbientLight(0x3d4a5c, 0.2));

  // 品红霓虹补光(保留赛博主题染色)
  const rim = new THREE.DirectionalLight(0xff2d95, 0.35);
  rim.position.set(-46, 26, -38);
  scene.add(rim);

  // 青色补光
  const fill = new THREE.DirectionalLight(0x1d7f9c, 0.3);
  fill.position.set(-30, 14, 52);
  scene.add(fill);

  // ---------- 写实海面:Water 平面反射 ----------
  const waterNormals = await new THREE.TextureLoader().loadAsync(
    assetUrl('textures/waternormals.jpg'),
  );
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
  skyEnvScene.add(sky); // 临时移入环境场景
  const envRT = pmrem.fromScene(skyEnvScene);
  scene.add(sky); // 移回主场景
  scene.environment = envRT.texture;
  scene.environmentIntensity = 0.38;
  pmrem.dispose();

  // ---------- 音效:脚步 ----------
  // 浏览器只允许在用户手势之后出声:启动时只记开关状态,不创建 AudioContext,
  // 第一次按键/触屏时再解锁(见下方 unlockAudio)。
  const SOUND_KEY = 'neon-isle:sound';
  const stepAudio = createStepAudio();
  let soundOn = true;
  try {
    soundOn = localStorage.getItem(SOUND_KEY) !== '0';
  } catch (err) {
    soundOn = true; // 隐私模式 / 存储被禁用时用默认值
  }
  applySound(soundOn, false); // 只同步状态:不写存储、不创建 AudioContext(等首次手势再解锁)

  // ---------- 世界 ----------
  const island = buildIsland(THREE, scene);
  const player = buildPlayer(THREE, scene, stepAudio.footstep);
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
    root: els.dialog,
    nameEl: els.dialogName,
    textEl: els.dialogText,
    closeBtn: els.dialogClose,
  });
  const toast = createToast({ root: els.msg, textEl: els.msgText });

  els.soundToggle.addEventListener('click', () => applySound(!soundOn));

  /** 应用音效开关;persist=false 用于启动时同步状态,不回写存储也不弹提示 */
  function applySound(on, persist = true) {
    soundOn = !!on;
    stepAudio.setEnabled(soundOn);
    if (soundOn) stepAudio.unlock(); // 由按键/点触触发,正处在用户手势里
    const label = soundOn ? '静音 (M)' : '开启音效 (M)';
    els.soundToggle.setAttribute('aria-pressed', String(soundOn));
    els.soundToggle.setAttribute('aria-label', label);
    els.soundToggle.title = label;
    if (!persist) return;
    try {
      localStorage.setItem(SOUND_KEY, soundOn ? '1' : '0');
    } catch (err) {
      /* 存储失败不影响使用 */
    }
    toast.show(soundOn ? '音效:已开启' : '音效:已静音 · 按 M 恢复', 2400);
  }

  // 音频解锁:只认第一次真实手势;once 自动摘掉监听,之后不需要再管
  const unlockAudio = () => stepAudio.unlock();
  window.addEventListener('keydown', unlockAudio, { once: true });
  window.addEventListener('pointerdown', unlockAudio, { once: true });
  window.addEventListener('touchstart', unlockAudio, { once: true, passive: true });

  // ---------- 键位绑定:默认值来自 keybinds.js,改动后写进本地存储 ----------
  const binds = readBinds();

  /** 把当前键位同步到交互提示与对话提示的键帽上 */
  function refreshBindLabels() {
    for (const cap of els.bindCaps) {
      const action = cap.getAttribute('data-bind');
      if (action === 'move') {
        // 四个移动键拼成一个键帽:全是单字符时直接连写(WASD / ↑←↓→),否则用 / 分隔
        const parts = ['moveForward', 'moveLeft', 'moveBack', 'moveRight'].map((id) =>
          codeToLabel(binds[id]),
        );
        cap.textContent = parts.every((s) => s.length === 1) ? parts.join('') : parts.join('/');
      } else if (binds[action]) {
        cap.textContent = codeToLabel(binds[action]);
      }
    }
  }
  refreshBindLabels();

  /** 首屏操作引导:场景内消息逐条浮现,自动淡出 */
  function showIntroHints() {
    if (touchMode) {
      toast.show('拖动左下摇杆移动 · 点右下 E 键交互', 5200);
      return;
    }
    toast.show(
      lookMode === 'drag'
        ? '按住鼠标左键拖动转视角,滚轮缩放'
        : '点击画面进入全屏并锁定鼠标 · 移动鼠标环顾 · 按 Esc 显示鼠标',
      4600,
    );
    toast.show(
      codeToLabel(binds.moveForward) +
        ' ' +
        codeToLabel(binds.moveLeft) +
        ' ' +
        codeToLabel(binds.moveBack) +
        ' ' +
        codeToLabel(binds.moveRight) +
        ' 移动 · ' +
        codeToLabel(binds.run) +
        ' 疾跑 · ' +
        codeToLabel(binds.interact) +
        ' 交互 · ' +
        codeToLabel(binds.settings) +
        ' 设置 · ' +
        codeToLabel(binds.sound) +
        ' 静音 · Esc 显示鼠标',
      5200,
    );
  }

  // ---------- 触屏模式 ----------
  let touchMode = window.matchMedia('(pointer: coarse)').matches;
  const applyTouchMode = () => document.body.classList.toggle('touch-mode', touchMode);
  applyTouchMode();
  const joy = createJoystick(els.joystick, els.joyKnob);
  window.addEventListener(
    'touchstart',
    function onFirstTouch() {
      if (!touchMode) {
        touchMode = true;
        applyTouchMode();
      }
      window.removeEventListener('touchstart', onFirstTouch);
    },
    { passive: true },
  );

  // ---------- 键盘输入 ----------
  // 键位来自 binds(可在设置里改),这里只按动作名取键,不再写死具体键码
  const keys = new Set();

  /** 某个动作当前是否按住:命中绑定的键位,左右修饰键视为等效(AltLeft ↔ AltRight 等) */
  function isDown(action) {
    const code = binds[action];
    if (!code) return false;
    if (keys.has(code)) return true;
    const twin = mirrorCode(code);
    return twin ? keys.has(twin) : false;
  }

  window.addEventListener('keydown', (e) => {
    if (e.repeat) return;
    // 焦点在输入控件里时不抢键(数字框、单选框交给浏览器自己处理)
    const tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable)) {
      if (e.code === 'Escape' && settings.isOpen()) settings.close();
      return;
    }
    // 改键捕获在 settings.js 的捕获阶段处理,这里只兜底关面板
    if (e.code === 'Escape' && settings.isOpen()) {
      settings.close();
      return;
    }
    if (e.code === binds.lookPause || e.code === mirrorCode(binds.lookPause)) {
      e.preventDefault(); // 别让 Alt 把焦点交给浏览器菜单栏
      setLookPaused(true);
      return;
    }
    if (e.code === binds.settings) {
      e.preventDefault();
      toggleSettings();
      return;
    }
    if (settings.isOpen()) return; // 面板打开时其余按键归面板,不触发游戏操作
    if (e.code === binds.sound) {
      e.preventDefault();
      applySound(!soundOn);
      return;
    }
    if (e.code === binds.interact) {
      e.preventDefault();
      onInteract();
      return;
    }
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
      e.preventDefault();
    }
    keys.add(e.code);
  });
  window.addEventListener('keyup', (e) => {
    if (e.code === binds.lookPause || e.code === mirrorCode(binds.lookPause)) setLookPaused(false);
    keys.delete(e.code);
  });
  window.addEventListener('blur', () => {
    keys.clear();
    setLookPaused(false);
  });

  // ---------- 视角:桌面「鼠标自由转动」/ 触屏与拖拽模式「按住拖拽」 ----------
  // 自由视角用 Pointer Lock:点一下画面就把指针锁进画布,直接用移动量(movementX/Y)转视角。
  // 锁定后光标不会溜出窗口、也不会顶到屏幕边缘卡住,浏览器负责隐藏光标,画面上不画准星。
  // Esc 是浏览器原生的解锁方式,解锁后光标回到页面、可以正常点界面。
  const cam = { yaw: Math.PI * 0.85, pitch: 0.28, dist: 6.6, distTarget: 6.6 };
  const LOOK_SENS_X = 0.0042; // rad / px
  const LOOK_SENS_Y = 0.0032;

  // 鼠标灵敏度倍率:只影响转视角速度,不改变上下俯仰的限位
  const SENS_KEY = 'neon-isle:look-sens';
  function readSens() {
    try {
      const v = Number(localStorage.getItem(SENS_KEY));
      return v >= 0.3 && v <= 2 ? v : 1;
    } catch (err) {
      return 1; // 隐私模式 / 存储被禁用时用默认值
    }
  }

  let lookSens = readSens();

  /** 应用鼠标灵敏度;persist=false 只同步内存里的值,不写入本地存储 */
  function applySens(v, persist = true) {
    lookSens = clamp(Number(v) || 1, 0.3, 2);
    if (!persist) return;
    try {
      localStorage.setItem(SENS_KEY, String(lookSens));
    } catch (err) {
      /* 存储失败不影响使用 */
    }
  }

  function look(dx, dy) {
    cam.yaw -= dx * LOOK_SENS_X * lookSens;
    cam.pitch = clamp(cam.pitch + dy * LOOK_SENS_Y * lookSens, -0.2, 1.15);
  }

  let drag = null;
  function startDrag(e) {
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY };
    try {
      els.canvas.setPointerCapture(e.pointerId);
    } catch (err) {
      /* 指针已抬起 */
    }
  }

  // ---------- 指针锁定 + 全屏:自由视角下把鼠标关进画布 ----------
  let locked = false; // 指针当前是否锁在画布上

  function lockPointer() {
    try {
      const ret = els.canvas.requestPointerLock();
      // 浏览器拒绝时(刚按过 Esc、不处在用户手势里)静默退回按住拖拽,不弹错
      if (ret && typeof ret.catch === 'function') ret.catch(() => {});
    } catch (err) {
      /* 个别浏览器不合格时会直接抛,同样退回拖拽 */
    }
  }

  /**
   * 先全屏再锁定指针:窗口化页面上 Chrome 会画一条「按 Esc 退出」的鼠标锁定气泡,
   * 进了全屏这条浏览器提示就不再出现(换成的全屏提示会自己淡出)。
   * 全屏请求被拒也照样锁定,只是那条气泡留着。
   */
  function requestLock() {
    if (locked || lookMode !== 'free' || touchMode || settings.isOpen()) return; // 面板开着时别把光标藏起来
    const root = document.documentElement;
    if (document.fullscreenElement || !root.requestFullscreen) {
      lockPointer();
      return;
    }
    Promise.resolve()
      .then(() => root.requestFullscreen({ navigationUI: 'hide' }))
      .catch(() => {})
      .then(lockPointer);
  }

  /** 主动解锁:开面板、切模式时把光标还给用户(全屏留着,页面还是满屏的) */
  function releaseLock() {
    if (document.pointerLockElement) document.exitPointerLock();
  }

  document.addEventListener('pointerlockchange', () => {
    locked = document.pointerLockElement === els.canvas;
    if (!locked) drag = null;
  });
  // 退出全屏(按 Esc / F11)时顺手把指针也放开,免得回到桌面还看不见鼠标
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) releaseLock();
  });
  document.addEventListener('pointerlockerror', () => {
    toast.show('点一下画面锁定鼠标', 2200);
  });

  // 放开光标:Esc 是浏览器保留的退出键,一按就解锁 + 退出全屏,光标自然回到桌面;
  // 按住 Alt 是同效果的快捷键,松开自动锁回去。平时鼠标始终关在画面里,不会跑到屏幕外面
  let lookPaused = false;
  function setLookPaused(on) {
    if (lookPaused === on) return;
    lookPaused = on;
    document.body.classList.toggle('look-paused', on);
    if (on) {
      releaseLock();
      return;
    }
    // 松开 Alt 立刻锁回去;浏览器不给锁(不在手势里)时安静退回点画面锁定
    if (document.hasFocus()) requestLock();
  }

  // ---------- 视角模式:free(鼠标自由转动)/ drag(按住拖拽),桌面设置弹窗切换 ----------
  const LOOK_MODE_KEY = 'neon-isle:look-mode';
  function readLookMode() {
    try {
      return localStorage.getItem(LOOK_MODE_KEY) === 'drag' ? 'drag' : 'free';
    } catch (err) {
      return 'free'; // 隐私模式 / 存储被禁用时用默认值
    }
  }

  let lookMode = readLookMode();

  /** 应用视角模式;persist=false 用于启动时同步 UI,不回写存储 */
  function applyLookMode(mode, persist = true) {
    lookMode = mode === 'drag' ? 'drag' : 'free';
    document.body.classList.toggle('look-drag', lookMode === 'drag'); // 只用来切换光标样式
    if (lookMode !== 'free') releaseLock(); // 拖拽模式不需要锁定指针
    if (!persist) return; // 启动时只同步状态,不弹提示
    try {
      localStorage.setItem(LOOK_MODE_KEY, lookMode);
    } catch (err) {
      /* 存储失败不影响使用 */
    }
    toast.show(
      lookMode === 'drag'
        ? '视角方式:按住拖拽 · 转视角需按住左键'
        : '视角方式:鼠标自由转动 · 移动鼠标即可环顾',
      3200,
    );
  }

  const settings = createSettings({
    root: els.settings,
    openBtn: els.settingsOpen,
    closeBtn: els.settingsClose,
    radios: els.lookRadios,
    getMode: () => lookMode,
    onSelect: (mode) => applyLookMode(mode),
    sensInput: els.sensInput,
    sensSaveBtn: els.sensSave,
    getSens: () => lookSens,
    onSensChange: (v, persist) => applySens(v, persist),
    binds,
    onBindsChange: () => refreshBindLabels(),
    keyListEl: els.keyList,
    presetBoxEl: els.keyPresets,
    resetBtnEl: els.keyReset,
    hintEl: els.keyHint,
    notify: (text, ms) => toast.show(text, ms),
    onOpenChange: (open) => {
      if (open) {
        releaseLock();
        return;
      } // 面板要拿鼠标点,先把光标还给用户
      keys.clear(); // 面板关掉时清空按键集合,免得残留的按住状态继续带着人走
      setLookPaused(false);
    },
  });
  applyLookMode(lookMode, false);

  function toggleSettings() {
    settings.toggle();
  }

  els.canvas.addEventListener('pointerdown', (e) => {
    if (e.button === 2) return; // 右键暂不承载任何操作:不锁指针、不开始拖拽(系统菜单已由 contextmenu 屏蔽)
    if (lookMode === 'drag' || e.pointerType !== 'mouse') {
      startDrag(e);
      return;
    }
    // 自由视角:点一下画面就把指针锁进去,光标从此进不了页面、也甩不出窗口
    if (!locked && !lookPaused) {
      requestLock();
      startDrag(e);
    } // 锁定被拒时,按住拖拽照样能转视角
  });
  els.canvas.addEventListener('pointermove', (e) => {
    // 自由视角:吃浏览器给的移动量。锁定时和光标位置无关,没锁定时也一样转
    if (lookMode === 'free' && e.pointerType === 'mouse') {
      if (e.movementX === undefined) {
        startDrag(e);
        return;
      } // 老浏览器拿不到移动量,退回拖拽
      if (!lookPaused) look(e.movementX, e.movementY || 0);
      return;
    }
    // 拖拽模式 / 触屏:按住才转
    if (!drag || e.pointerId !== drag.id) return;
    if (e.buttons === 0) {
      drag = null;
      return;
    } // 兜底:漏掉 pointerup 时不让视角自己转
    look(e.clientX - drag.x, e.clientY - drag.y);
    drag.x = e.clientX;
    drag.y = e.clientY;
  });
  // 右键的抬起不参与收尾:否则「按住左键拖动时顺手点一下右键」会把正在进行的拖拽掐断
  const endDrag = (e) => {
    if (e.button === 2) return;
    if (drag && e.pointerId === drag.id) drag = null;
  };
  els.canvas.addEventListener('pointerup', endDrag);
  els.canvas.addEventListener('pointercancel', endDrag);
  els.canvas.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      cam.distTarget = clamp(cam.distTarget + e.deltaY * 0.008, 3.2, 14);
    },
    { passive: false },
  );
  els.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

  // ---------- 交互 ----------
  let nearTarget = null;
  function onInteract() {
    if (settings.isOpen()) return; // 设置面板打开时不触发交互
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
  const obstacles = island.obstacles;
  const MAX_R = ISLAND_RADIUS * 0.955;
  const radarPoints = island.interactives.map((p) => ({ x: p.pos.x, z: p.pos.z, kind: p.kind }));

  const clock = new THREE.Clock();
  let elapsed = 0;
  let heading = player.group.rotation.y;
  let prevHeading = heading;
  let turnRate = 0;
  let started = false;

  /** 环形能量边界:超出就把角色按半径缩回来 */
  function clampToIsland(p) {
    const pr = Math.hypot(p.x, p.z);
    if (pr > MAX_R) {
      const k = MAX_R / pr;
      p.x *= k;
      p.z *= k;
    }
  }

  /**
   * 实心障碍碰撞(圆 vs 圆):沿法线把角色推到障碍表面外。
   * 只削掉法向穿透量、保留切向位移 —— 贴着岩石走会自然滑开,不会卡死。
   * footY >= top 时跳过:矮于膝盖的碎石不挡路,站在高处也不会被脚下的石头拦住。
   */
  function resolveObstacles(p, footY) {
    for (let pass = 0; pass < 3; pass++) {
      let hit = false;
      for (const o of obstacles) {
        if (footY >= o.top) continue;
        const dx = p.x - o.x;
        const dz = p.z - o.z;
        const minD = o.r + PLAYER_RADIUS;
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
  }

  /** 当前最深穿透量(> 0 说明角色仍陷在某个实心体内),用于校验推出是否真的干净 */
  function penetrationAt(p, footY) {
    let worst = 0;
    for (const o of obstacles) {
      if (footY >= o.top) continue;
      const d = Math.hypot(p.x - o.x, p.z - o.z);
      const pen = o.r + PLAYER_RADIUS - d;
      if (pen > worst) worst = pen;
    }
    return worst;
  }

  function frame() {
    requestAnimationFrame(frame);
    const rawDt = clock.getDelta();
    const dt = Math.min(rawDt, 0.05);
    elapsed += dt;

    // 1) 输入向量(键盘 + 摇杆)
    let ix = (isDown('moveRight') ? 1 : 0) - (isDown('moveLeft') ? 1 : 0) + joy.vec.x;
    let iy = (isDown('moveForward') ? 1 : 0) - (isDown('moveBack') ? 1 : 0) + joy.vec.y;
    const len = Math.hypot(ix, iy);
    if (len > 1) {
      ix /= len;
      iy /= len;
    }
    const active = len > 0.08;
    const run = isDown('run');

    // 2) 移动(以相机朝向为基准)
    forward.set(-Math.sin(cam.yaw), 0, -Math.cos(cam.yaw));
    right.set(Math.cos(cam.yaw), 0, -Math.sin(cam.yaw));
    let backpedal = false;
    if (active) {
      move.set(0, 0, 0).copy(forward).multiplyScalar(iy).addScaledVector(right, ix);
      // 朝向只取「往前走的方向」:后退(S)时把前后分量取反,人物保持面朝前方倒着走,
      // 而不是原地掉头 180° 再迈步;左右分量(ix)照旧参与,横移仍会转过去
      const faceY = iy < 0 ? -iy : iy;
      const faceX = forward.x * faceY + right.x * ix;
      const faceZ = forward.z * faceY + right.z * ix;
      // 真实位移方向与朝向相反 → 在倒着走:步行动作倒放,避免脚底像打滑(太空步)
      backpedal = move.x * faceX + move.z * faceZ < 0;
      const speed = run ? RUN_SPEED : WALK_SPEED;
      const prevX = playerPos.x;
      const prevZ = playerPos.z;
      playerPos.x += move.x * speed * dt;
      playerPos.z += move.z * speed * dt;
      clampToIsland(playerPos);
      // 岩石/晶簇/塔/集装箱/装置挡人,否则会整个走进模型里
      resolveObstacles(playerPos, heightAt(playerPos.x, playerPos.z));
      clampToIsland(playerPos); // 被推出后仍需留在能量边界内
      // 夹在晶簇这种重叠小圆的缝隙里时,逐圆推出会互相打架、几帧内收敛不了,
      // 此时退回上一帧的位置(上一帧位置由归纳法保证是合法的),绝不留在实心体内
      if (penetrationAt(playerPos, heightAt(playerPos.x, playerPos.z)) > 1e-3) {
        playerPos.x = prevX;
        playerPos.z = prevZ;
      }
      heading = lerpAngle(heading, Math.atan2(faceX, faceZ), Math.min(1, dt * 12));
      player.group.rotation.y = heading;
      let dh = heading - prevHeading;
      if (dh > Math.PI) dh -= Math.PI * 2;
      if (dh < -Math.PI) dh += Math.PI * 2;
      // 限幅:掉帧时 dh/dt 会瞬间冲到几十 rad/s,会把侧倾一帧打满
      turnRate = dt > 0 ? clamp(dh / dt, -3, 3) : 0;
    } else {
      // 松键后角速度必须归零,否则侧倾会永远停在最后一帧的值 —— 站定后人物是歪的
      turnRate = damp(turnRate, 0, 12, dt);
    }

    prevHeading = heading;

    // 3) 贴地
    const groundY = Math.max(heightAt(playerPos.x, playerPos.z), -0.22);
    playerPos.y = damp(playerPos.y, groundY, 14, dt);

    // 4) 行走动画:传真实速度(m/s)与转向速率,驱动步态与侧倾
    const curSpeed = active ? (run ? RUN_SPEED : WALK_SPEED) * Math.min(1, len) : 0;
    player.update(dt, curSpeed, elapsed, turnRate, backpedal);

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
      if (d2 < bestD2) {
        bestD2 = d2;
        nearTarget = p;
      }
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
      setTimeout(showIntroHints, 900);
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
