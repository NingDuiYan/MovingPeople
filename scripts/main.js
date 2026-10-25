// ============ 废土场景查看器 ============
// 场景拆成四个 GLB 单独加载(树/废墟/轿车/地面),这是小游戏的取用方式:
// 树可交互、车是障碍、废墟是建筑、地面负责人物行走的碰撞与贴地。每个文件里只含一个
// 网格节点,节点名就是 tree / house / car / ground。光照方位与建模时的 Blender 场景
// (wasteland-blender/builders/wst_atmosphere.py)保持一致,GLB 里不含灯光与相机。
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { assetUrl } from './utils.js';
import { createCharacter } from './character.js';

const MODELS = [
  { key: 'tree', path: 'models/tree.glb' },
  { key: 'house', path: 'models/house.glb' },
  { key: 'car', path: 'models/car.glb' },
  { key: 'ground', path: 'models/ground.glb' },
  { key: 'character', path: 'models/character.glb' },
];

// 角色出生点:站在相机与轿车之间的沙地上,面朝废墟(-Z 方向)
const CHARACTER_SPAWN = new THREE.Vector3(0, 0, 6);
// 相机跟随的是角色胸口高度,不是脚底,否则视角会贴到地面
const CHARACTER_FOCUS_OFFSET = new THREE.Vector3(0, 1.35, 0);

const DRACO_DECODER_PATH = 'draco/';

// 地面裂纹贴图在 Blender 里按 4 m 一个 tile 写进 UV,近景重复感明显;
// 这里把 map.repeat 压到 0.62,世界周期变成约 6.5 m
const GROUND_TEXTURE_PERIOD_SCALE = 0.8;

// 触屏设备降一档开销:像素比与阴影贴图都是移动端最贵的地方
const IS_COARSE_POINTER = window.matchMedia('(pointer: coarse)').matches;

const DEG = THREE.MathUtils.degToRad;
const SUN_AZIMUTH = DEG(34);
const SUN_ELEVATION = DEG(8);
const FILL_AZIMUTH = DEG(-125);
const FILL_ELEVATION = DEG(26);

// 天空配色取自参考图的实测网格(2730x1536):天顶暗蓝灰(51,60,71 左侧 → 100,81,81 朝太阳侧),
// 低空被沙尘照暖(朝太阳一侧地平线到 234,156,95),所以天顶与地平线各配冷/暖两色按方位插值
const ZENITH_COOL = new THREE.Color(0x333c47);
const ZENITH_WARM = new THREE.Color(0x645151);
const HORIZON_COOL = new THREE.Color(0x5d4538);
const HORIZON_WARM = new THREE.Color(0xea9c5f);
const GLOW_COLOR = new THREE.Color(0xffb673);
const FOG_COLOR = new THREE.Color(0xb98a5e);

// 相机参数沿用 Blender wst_cam_main 的 28mm 镜头口径,但改成第三人称视角:
// 站在角色身后 5.4 m、略高于胸口,正好把 1.78 m 的角色框到画面 4 成高
const CAMERA_FOV = 40;
const CAMERA_POSITION = new THREE.Vector3(0, 2.0, 11.4);
const CAMERA_TARGET = new THREE.Vector3(0, 1.35, 6);

const els = {
  canvas: document.getElementById('scene'),
  loading: document.getElementById('loading'),
  loadingBar: document.getElementById('loading-bar-fill'),
  loadingText: document.querySelector('.loading-text'),
  loadingPct: document.getElementById('loading-pct'),
};

/**
 * 由方位角/仰角求单位方向向量。
 * Blender 是 Z-up、+Y 为前向,Three 是 Y-up,对应关系 (x, y, z) -> (x, z, -y)。
 */
function directionFromAngles(azimuth, elevation) {
  const horizontal = Math.cos(elevation);
  return new THREE.Vector3(
    horizontal * Math.cos(azimuth),
    Math.sin(elevation),
    -horizontal * Math.sin(azimuth),
  ).normalize();
}

const sunDirection = directionFromAngles(SUN_AZIMUTH, SUN_ELEVATION);

/** 渐变天穹 + 太阳辉光:GLB 里没有天空,没有它模型会浮在纯色虚空里 */
function createSky() {
  const geometry = new THREE.SphereGeometry(600, 32, 16);
  const material = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: {
      uHorizonCool: { value: HORIZON_COOL },
      uHorizonWarm: { value: HORIZON_WARM },
      uZenithCool: { value: ZENITH_COOL },
      uZenithWarm: { value: ZENITH_WARM },
      uSunDir: { value: sunDirection },
      uGlow: { value: GLOW_COLOR },
    },
    vertexShader: /* glsl */ `
      varying vec3 vDir;

      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uHorizonCool;
      uniform vec3 uHorizonWarm;
      uniform vec3 uZenithCool;
      uniform vec3 uZenithWarm;
      uniform vec3 uSunDir;
      uniform vec3 uGlow;
      varying vec3 vDir;

      void main() {
        vec3 dir = normalize(vDir);
        float h = clamp(dir.y, 0.0, 1.0);
        // 方位对齐度:1 = 正对太阳一侧,0 = 背向太阳。参考图的天空是一条水平渐变,
        // 冷蓝在上/左、暖橙在下/右,所以天顶与地平线各按这个系数插值。
        vec2 dxz = dir.xz + vec2(1e-5);
        vec2 sxz = normalize(uSunDir.xz);
        float az = dot(normalize(dxz), sxz) * 0.5 + 0.5;
        vec3 zenith = mix(uZenithCool, uZenithWarm, pow(az, 2.4));
        vec3 horizon = mix(uHorizonCool, uHorizonWarm, pow(az, 3.2));
        // 垂直过渡:参考图的天空在仰角 0°→17° 内就基本收到天顶色(实测 y=620 还 234,
        // 到 y=40 只剩 100),所以用窄带 smoothstep 而不是幂曲线
        float k = smoothstep(0.0, 0.16, h);
        vec3 color = mix(horizon, zenith, k);
        // 太阳被沙尘糊住:不画硬盘,只留一层宽辉光
        float facing = max(dot(dir, uSunDir), 0.0);
        color += uGlow * (pow(facing, 9.0) * 0.55 + pow(facing, 2.5) * 0.10);
        gl_FragColor = vec4(color, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  });

  const sky = new THREE.Mesh(geometry, material);
  sky.frustumCulled = false;
  sky.renderOrder = -1;
  return sky;
}

function createRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, IS_COARSE_POINTER ? 1.5 : 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // 场景在 Blender 里按 AgX 调色,浏览器侧用 ACES 近似
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.22;
  return renderer;
}

function createLights() {
  const group = new THREE.Group();

  // 主光:低角度暖色夕阳,唯一投影光源
  // 相比参考图,网页里物体投在沙地上的影子偏淡:8° 太阳对平地 N·L 只有 0.139,
  // 补光把它彻底洗平。所以抬高直射、压低补光与天光,让阴影区真正暗下去。
  const sun = new THREE.DirectionalLight(0xffa457, 3.15);
  sun.position.copy(sunDirection).multiplyScalar(120);
  sun.castShadow = true;
  sun.shadow.mapSize.setScalar(IS_COARSE_POINTER ? 1024 : 2048);
  sun.shadow.camera.left = -45;
  sun.shadow.camera.right = 45;
  sun.shadow.camera.top = 45;
  sun.shadow.camera.bottom = -45;
  sun.shadow.camera.near = 20;
  sun.shadow.camera.far = 260;
  // 8 度低角度下大块平地的自阴影容易出现条纹(shadow acne),靠 normalBias 顶掉
  sun.shadow.bias = -0.0002;
  sun.shadow.normalBias = 0.06;
  group.add(sun);

  // 填充:背光方向的暖白,避免背阴面死黑。参考图是逆光场景,物体朝向相机的一面
  // 全靠沙尘散射照亮,所以这一盏的强度直接决定"黑不黑"
  const fill = new THREE.DirectionalLight(0xffd9b8, 1.55);
  fill.position.copy(directionFromAngles(FILL_AZIMUTH, FILL_ELEVATION)).multiplyScalar(80);
  group.add(fill);

  // 半球光:替代 EEVEE 里没有的全局光照,给沙地与背阴面一点天光与地面反弹
  group.add(new THREE.HemisphereLight(0xd9c3a6, 0x9a6a3e, 0.62));

  return group;
}

/**
 * 材质已压扁成 baseColorFactor,这里只补投影/接收阴影需要的开关。
 * 地面贴图在 Blender 里按 4 m 一个 tile 烘进 UV,近景能看出重复;
 * 把 map.repeat 压到 0.62 相当于把周期拉到 6.5 m,再开满各向异性压掉斜向糊化。
 */
function prepareModel(root, renderer, key) {
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  root.traverse((object) => {
    if (!object.isMesh) return;
    object.castShadow = true;
    object.receiveShadow = true;
    if (key !== 'ground') return;
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      if (!material || !material.map) continue;
      material.map.wrapS = THREE.RepeatWrapping;
      material.map.wrapT = THREE.RepeatWrapping;
      material.map.repeat.setScalar(GROUND_TEXTURE_PERIOD_SCALE);
      material.map.anisotropy = maxAniso;
      material.map.needsUpdate = true;
    }
  });
  return root;
}

/** GLB 用 Draco 压缩过几何,解码器托管在 public/draco/,不走 CDN */
function createLoader() {
  const draco = new DRACOLoader().setDecoderPath(assetUrl(DRACO_DECODER_PATH));
  return new GLTFLoader().setDRACOLoader(draco);
}

/**
 * 并行加载四个模型,进度按字节累加。
 * 用 allSettled:单个文件失败不能连累其它模型,失败名单回传给调用方做提示。
 */
async function loadModels(loader, onProgress) {
  const bytes = MODELS.map(() => ({ loaded: 0, total: 0 }));
  const report = () => {
    const total = bytes.reduce((sum, b) => sum + b.total, 0);
    const loaded = bytes.reduce((sum, b) => sum + b.loaded, 0);
    onProgress(loaded, total);
  };

  const results = await Promise.allSettled(
    MODELS.map((model, i) =>
      loader.loadAsync(assetUrl(model.path), (event) => {
        bytes[i].loaded = event.loaded;
        bytes[i].total = event.total || event.loaded;
        report();
      }),
    ),
  );

  const loaded = [];
  const failed = [];
  results.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      // 角色要额外拿 animations 与骨骼,所以整个 gltf 一起带出去
      loaded.push({ key: MODELS[i].key, root: result.value.scene, gltf: result.value });
    } else {
      failed.push(MODELS[i].key);
      console.error('[viewer] 模型加载失败', MODELS[i].path, result.reason);
    }
  });

  return { loaded, failed };
}

function setLoadingProgress(loaded, total) {
  if (!total) {
    els.loadingPct.textContent = '…';
    return;
  }
  const pct = Math.min(100, Math.round((loaded / total) * 100));
  els.loadingPct.textContent = `${pct}%`;
  els.loadingBar.style.width = `${pct}%`;
}

function failLoading(reason) {
  els.loadingText.textContent = reason;
  els.loadingText.classList.add('is-error');
  els.loadingBar.style.width = '100%';
  els.loadingBar.style.background = '#ef8a72';
}

function finishLoading() {
  els.loading.classList.add('is-done');
  els.loading.addEventListener('transitionend', () => els.loading.remove(), { once: true });
}

function main() {
  const { canvas } = els;

  const renderer = createRenderer(canvas);
  const scene = new THREE.Scene();
  // 雾负责把 320m 的地面边缘吃掉,避免看到地形方角;
  // far 从 190 收到 155:远山原来边缘硬、还偏亮,雾近一点才和天空接得上
  scene.fog = new THREE.Fog(FOG_COLOR, 24, 132);

  const camera = new THREE.PerspectiveCamera(CAMERA_FOV, 1, 0.1, 2000);
  camera.position.copy(CAMERA_POSITION);

  const controls = new OrbitControls(camera, canvas);
  controls.target.copy(CAMERA_TARGET);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 2.6;
  controls.maxDistance = 34;
  // 右键改作格挡,平移关掉,免得和战斗输入抢同一个键
  controls.enablePan = false;
  // 不让相机钻到地面以下
  controls.maxPolarAngle = Math.PI / 2 - 0.02;
  controls.update();

  scene.add(createSky());
  scene.add(createLights());

  function resize() {
    const width = canvas.clientWidth || window.innerWidth;
    const height = canvas.clientHeight || window.innerHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  window.addEventListener('resize', resize);
  resize();

  const loader = createLoader();
  const clock = new THREE.Clock();
  const followDelta = new THREE.Vector3();
  const focusPoint = new THREE.Vector3();
  let character = null;

  loadModels(loader, setLoadingProgress).then(({ loaded, failed }) => {
    for (const model of loaded) {
      // 节点名保持 tree / house / car / ground / character,玩法代码按名字取模型
      scene.add(prepareModel(model.root, renderer, model.key));
    }

    if (failed.length > 0) {
      failLoading(
        `模型加载失败:${failed.join('、')}(public/models/ 下应有 tree/house/car/ground/character 五个 GLB)`,
      );
      return;
    }

    const characterModel = loaded.find((model) => model.key === 'character');
    character = createCharacter({
      root: characterModel.gltf.scene,
      animations: characterModel.gltf.animations,
      camera,
      canvas,
      spawn: CHARACTER_SPAWN,
    });

    finishLoading();
  });

  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.05);
    if (character) {
      character.update(dt, performance.now());
      // 相机跟随:target 与相机同步平移,阻尼用指数衰减保证不同帧率手感一致
      focusPoint.copy(character.model.position).add(CHARACTER_FOCUS_OFFSET);
      followDelta.subVectors(focusPoint, controls.target).multiplyScalar(1 - Math.exp(-7 * dt));
      controls.target.add(followDelta);
      camera.position.add(followDelta);
    }
    controls.update();
    renderer.render(scene, camera);
  });
}

main();
