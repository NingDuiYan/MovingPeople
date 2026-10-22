// ============ 赛博小岛场景生成 ============
// 分层:远城/地形/岩层/晶簇/塔群/栈桥/灯牌/粒子/交互物
// [写实化] 天穹与海面由 main.js 的 Sky(大气散射)/Water(平面反射)接管
// [写实化] 地形叠加真实草地 PBR 贴图
// [碰撞] 实心道具登记到 obstacles,由 main.js 把角色挡在体外
import { ISLAND_RADIUS, heightAt, rng, clamp, assetUrl } from './utils.js';
import { makeGlowTexture, makeWindowTexture, makeSignTexture, makeDotTexture } from './assets.js';

const NEON_CYAN = 0x00f0ff;
const NEON_MAGENTA = 0xff2d95;
const NEON_VIOLET = 0x7a4dff;

export function buildIsland(THREE, scene) {
  const R = ISLAND_RADIUS;
  const rand = rng(20240521);
  // 出生点(与 main.js 的 2,2 保持一致)周围留出净空,避免近景道具挡住镜头
  const SPAWN_X = 2,
    SPAWN_Z = 2,
    SPAWN_CLEAR = 9;
  const nearSpawn = (x, z) => Math.hypot(x - SPAWN_X, z - SPAWN_Z) < SPAWN_CLEAR;
  const interactives = [];
  const updaters = [];
  // 实心障碍:圆柱体近似(x/z 圆心 + 半径 + 顶面高度),供 main.js 做角色碰撞
  const obstacles = [];
  const addObstacle = (x, z, r, top) => obstacles.push({ x, z, r, top });

  const glowCyan = makeGlowTexture(THREE, NEON_CYAN);
  const glowMag = makeGlowTexture(THREE, NEON_MAGENTA);
  const glowViolet = makeGlowTexture(THREE, NEON_VIOLET);

  function addSprite(tex, x, y, z, size, opacity) {
    const sp = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: tex,
        transparent: true,
        opacity: opacity,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        fog: false,
      }),
    );
    sp.position.set(x, y, z);
    sp.scale.set(size, size, 1);
    scene.add(sp);
    return sp;
  }

  // ============================================================
  // 1. [写实化] 天穹/海面:改由 main.js 用 Sky+Water 接管
  // ============================================================

  // ============================================================
  // 2. 远景城市天际线
  // ============================================================
  const winTex = makeWindowTexture(THREE, 4471);
  const cityMat = new THREE.MeshStandardMaterial({
    color: 0x0a1120,
    roughness: 0.85,
    metalness: 0.3,
    emissive: 0xffffff,
    emissiveMap: winTex,
    emissiveIntensity: 0.85,
    fog: true,
  });
  const cityCapMat = new THREE.MeshBasicMaterial({
    color: NEON_CYAN,
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const cityCapMatM = new THREE.MeshBasicMaterial({
    color: NEON_MAGENTA,
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const cityGroup = new THREE.Group();
  const cityCount = 66;
  for (let i = 0; i < cityCount; i++) {
    const a = (i / cityCount) * Math.PI * 2 + rand() * 0.08;
    const rr = 196 + rand() * 132;
    const x = Math.cos(a) * rr;
    const z = Math.sin(a) * rr;
    const w = 6 + rand() * 13;
    const d = 6 + rand() * 13;
    const hh = 16 + Math.pow(rand(), 1.7) * 92;
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, hh, d), cityMat);
    b.position.set(x, hh * 0.5 - 3, z);
    b.rotation.y = rand() * Math.PI;
    cityGroup.add(b);
    // 顶部灯标
    if (rand() > 0.42) {
      const cap = new THREE.Mesh(
        new THREE.BoxGeometry(w * 0.55, 0.7, d * 0.55),
        rand() > 0.72 ? cityCapMatM : cityCapMat,
      );
      cap.position.set(x, hh - 2.6, z);
      cityGroup.add(cap);
    }
    // 天线
    if (hh > 62 && rand() > 0.4) {
      const ant = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 14, 5), cityCapMat);
      ant.position.set(x, hh + 4.4, z);
      cityGroup.add(ant);
      addSprite(rand() > 0.5 ? glowMag : glowCyan, x, hh + 11, z, 13, 0.55);
    }
  }
  scene.add(cityGroup);

  // 远处空中全息广告
  for (let i = 0; i < 4; i++) {
    const a = rand() * Math.PI * 2;
    const rr = 150 + rand() * 70;
    const mesh = new THREE.Mesh(
      new THREE.PlaneGeometry(46, 9),
      new THREE.MeshBasicMaterial({
        map: makeSignTexture(THREE, 'NEON', i % 2 ? '#ff2d95' : '#00f0ff'),
        transparent: true,
        opacity: 0.22,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
        fog: false,
      }),
    );
    mesh.position.set(Math.cos(a) * rr, 34 + rand() * 40, Math.sin(a) * rr);
    scene.add(mesh);
    updaters.push((dt, t) => {
      mesh.rotation.y = t * 0.09 + a;
    });
  }

  // 海岸浪花环
  const foam = new THREE.Mesh(
    new THREE.RingGeometry(R * 0.7, R * 0.99, 96, 1).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({
      color: 0x2fd8ff,
      transparent: true,
      opacity: 0.16,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );
  foam.position.y = 0.06;
  scene.add(foam);
  updaters.push((dt, t) => {
    foam.material.opacity = 0.1 + 0.09 * (0.5 + 0.5 * Math.sin(t * 1.5));
  });

  // ============================================================
  // 4. 地形
  // ============================================================
  const SEG = 176;
  const SIZE = 132;
  const geo = new THREE.PlaneGeometry(SIZE, SIZE, SEG, SEG);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  // 顶点色作为贴图的"调制系数"(接近白 = 让草地贴图原色显现),
  // 只在高度分区上做轻微色相偏移:湿滩偏暗冷 / 沙滩偏暖 / 草地偏亮 / 岩层偏灰
  const cWet = new THREE.Color('#b3a99a');
  const cSand = new THREE.Color('#eadfc6');
  const cGrass = new THREE.Color('#e4f2cc');
  const cMoss = new THREE.Color('#c6d8b4');
  const cRock = new THREE.Color('#cbd0d8');
  const cPeak = new THREE.Color('#eef1f7');
  const tmpC = new THREE.Color();
  const tmpC2 = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const h = heightAt(x, z);
    pos.setY(i, h);
    if (h < 0.05) tmpC.copy(cWet);
    else if (h < 0.9) tmpC.copy(cWet).lerp(cSand, (h - 0.05) / 0.85);
    else if (h < 2.6) tmpC.copy(cSand).lerp(cGrass, (h - 0.9) / 1.7);
    else if (h < 4.0) tmpC.copy(cGrass).lerp(cMoss, (h - 2.6) / 1.4);
    else if (h < 5.2) tmpC.copy(cMoss).lerp(cRock, (h - 4.0) / 1.2);
    else tmpC.copy(cRock).lerp(cPeak, clamp((h - 5.2) / 2.4, 0, 1));
    // 低频斑驳,避免大片纯色
    const mottle =
      0.94 + 0.12 * (0.5 + 0.5 * Math.sin(x * 0.62 + z * 0.41) * Math.cos(x * 0.21 - z * 0.53));
    tmpC2.copy(tmpC).multiplyScalar(mottle);
    colors[i * 3] = tmpC2.r;
    colors[i * 3 + 1] = tmpC2.g;
    colors[i * 3 + 2] = tmpC2.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  // 写实草地纹理(three.js 官方示例贴图),按顶点色调制以保留沙/岩/草分层
  const grassTex = new THREE.TextureLoader().load(assetUrl('textures/grasslight-big.jpg'));
  grassTex.wrapS = grassTex.wrapT = THREE.RepeatWrapping;
  grassTex.repeat.set(26, 26);
  grassTex.colorSpace = THREE.SRGBColorSpace;
  grassTex.anisotropy = 8;

  const terrainMat = new THREE.MeshStandardMaterial({
    map: grassTex,
    vertexColors: true,
    roughness: 0.92,
    metalness: 0.04,
  });
  // 地表细节:世界坐标网格 + 等高线 + 边缘菲涅尔辉光,注入标准材质着色器
  terrainMat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;',
      );
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace(
        '#include <emissivemap_fragment>',
        [
          '#include <emissivemap_fragment>',
          // 沙滩带:低海拔处把草地贴图压向暖沙色,保留贴图明暗细节
          'float sandW = 1.0 - smoothstep(0.35, 1.55, vWPos.y);',
          'float mLum = dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114));',
          'vec3 sandCol = vec3(0.66, 0.58, 0.43) * (0.55 + 1.05 * mLum);',
          'diffuseColor.rgb = mix(diffuseColor.rgb, sandCol, clamp(sandW, 0.0, 1.0));',
          // 岩石带:高海拔去饱和并压暗,形成裸岩质感
          'float rockW = smoothstep(4.0, 5.6, vWPos.y);',
          'diffuseColor.rgb = mix(diffuseColor.rgb, vec3(mLum) * vec3(0.92, 0.94, 1.0), rockW * 0.75);',
        ].join('\n'),
      );
  };
  terrainMat.customProgramCacheKey = () => 'terrain-detail';
  const terrain = new THREE.Mesh(geo, terrainMat);
  terrain.receiveShadow = true;
  scene.add(terrain);

  // 岸边发光描边
  const shoreLine = new THREE.Mesh(
    new THREE.TorusGeometry(R * 0.76, 0.055, 6, 120).rotateX(Math.PI / 2),
    new THREE.MeshBasicMaterial({
      color: NEON_CYAN,
      transparent: true,
      opacity: 0.24,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  shoreLine.position.y = 0.1;
  scene.add(shoreLine);

  // ============================================================
  // 5. 能量边界栅栏
  // ============================================================
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(R + 1.2, 0.09, 8, 160).rotateX(Math.PI / 2),
    new THREE.MeshBasicMaterial({
      color: NEON_CYAN,
      transparent: true,
      opacity: 0.4,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  ring.position.y = 0.15;
  scene.add(ring);
  updaters.push((dt, t) => {
    ring.material.opacity = 0.26 + 0.18 * (0.5 + 0.5 * Math.sin(t * 2.1));
  });

  // 栅栏立柱光点
  const postGeo = new THREE.CylinderGeometry(0.09, 0.09, 1.5, 5);
  const postMat = new THREE.MeshBasicMaterial({
    color: NEON_CYAN,
    transparent: true,
    opacity: 0.5,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const postCount = 56;
  for (let i = 0; i < postCount; i++) {
    const a = (i / postCount) * Math.PI * 2;
    const p = new THREE.Mesh(postGeo, postMat);
    p.position.set(Math.cos(a) * (R + 1.2), 0.75, Math.sin(a) * (R + 1.2));
    scene.add(p);
  }

  // ============================================================
  // 6. 岩层
  // ============================================================
  const rockGeo = new THREE.DodecahedronGeometry(1, 0);
  const rockMat = new THREE.MeshStandardMaterial({
    color: 0x121824,
    roughness: 0.96,
    flatShading: true,
  });
  const rockEdgeMat = new THREE.MeshStandardMaterial({
    color: 0x05070c,
    emissive: 0x1a4d63,
    emissiveIntensity: 0.7,
    roughness: 0.8,
    flatShading: true,
  });
  let placed = 0,
    guard = 0;
  while (placed < 55 && guard++ < 800) {
    const a = rand() * Math.PI * 2;
    const rr = 6 + rand() * (R * 0.78);
    const x = Math.cos(a) * rr,
      z = Math.sin(a) * rr;
    const h = heightAt(x, z);
    if (h < 0.5 || nearSpawn(x, z)) continue;
    const m = new THREE.Mesh(rockGeo, rand() > 0.72 ? rockEdgeMat : rockMat);
    m.position.set(x, h + 0.1, z);
    const sc = 0.45 + rand() * 1.55;
    const sy = sc * (0.5 + rand() * 0.8); // 先取值,保持随机序列与旧版一致
    m.scale.set(sc, sy, sc);
    m.rotation.set(rand() * Math.PI, rand() * Math.PI, rand() * Math.PI);
    m.castShadow = true;
    m.receiveShadow = true;
    scene.add(m);
    // 高于膝盖的岩石才挡人:半径按十二面体外接球的水平投影折算
    const rockTop = h + 0.1 + sy;
    if (rockTop - h > 0.55) addObstacle(x, z, sc * 0.86, rockTop);
    placed++;
  }

  // ============================================================
  // 7. 霓虹晶簇
  // ============================================================
  const crysCyan = new THREE.MeshStandardMaterial({
    color: 0x061c22,
    emissive: NEON_CYAN,
    emissiveIntensity: 1.7,
    roughness: 0.25,
    metalness: 0.2,
    flatShading: true,
  });
  const crysMag = new THREE.MeshStandardMaterial({
    color: 0x220a16,
    emissive: NEON_MAGENTA,
    emissiveIntensity: 1.5,
    roughness: 0.25,
    metalness: 0.2,
    flatShading: true,
  });
  const shardGeo = new THREE.CylinderGeometry(1, 0.35, 1, 6, 1);
  const tipGeo = new THREE.ConeGeometry(0.35, 1, 6, 1);
  placed = 0;
  guard = 0;
  while (placed < 30 && guard++ < 700) {
    const a = rand() * Math.PI * 2;
    const rr = 5 + rand() * (R * 0.72);
    const x = Math.cos(a) * rr,
      z = Math.sin(a) * rr;
    const h = heightAt(x, z);
    if (h < 0.7 || nearSpawn(x, z)) continue;
    const isCyan = rand() > 0.48;
    const mat = isCyan ? crysCyan : crysMag;
    const n = 2 + Math.floor(rand() * 4);
    for (let i = 0; i < n; i++) {
      const cw = 0.09 + rand() * 0.2;
      const ch = 0.5 + rand() * 2.1;
      const ox = (rand() - 0.5) * 1.4,
        oz = (rand() - 0.5) * 1.4;
      const tilt = (rand() - 0.5) * 0.42;
      const shard = new THREE.Mesh(shardGeo, mat);
      shard.scale.set(cw, ch, cw);
      shard.position.set(x + ox, h + ch * 0.46, z + oz);
      shard.rotation.set(tilt, rand() * Math.PI, (rand() - 0.5) * 0.42);
      shard.castShadow = true;
      scene.add(shard);
      addObstacle(x + ox, z + oz, Math.max(cw, 0.1), h + ch * 1.1);
      const tip = new THREE.Mesh(tipGeo, mat);
      tip.scale.set(cw, ch * 0.4, cw);
      tip.position.set(x + ox, h + ch * 0.92, z + oz);
      tip.rotation.copy(shard.rotation);
      scene.add(tip);
    }
    // 底部辉光
    const gl = new THREE.Mesh(
      new THREE.CircleGeometry(1.15, 20).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: isCyan ? NEON_CYAN : NEON_MAGENTA,
        transparent: true,
        opacity: 0.14,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    gl.position.set(x, h + 0.03, z);
    scene.add(gl);
    addSprite(isCyan ? glowCyan : glowMag, x, h + 0.9, z, 1.6, 0.2);
    placed++;
  }

  // ============================================================
  // 8. 数据塔群
  // ============================================================
  const towerMat = new THREE.MeshStandardMaterial({
    color: 0x0d1219,
    roughness: 0.5,
    metalness: 0.55,
  });
  const towerSpots = [
    { x: 18, z: -8, h: 12, c: NEON_CYAN },
    { x: -20, z: 4, h: 9.5, c: NEON_MAGENTA },
    { x: -4, z: 18, h: 10.5, c: NEON_CYAN },
    { x: 24, z: 14, h: 7.5, c: NEON_VIOLET },
  ];
  const towerTops = [];
  for (const sp of towerSpots) {
    const gy = heightAt(sp.x, sp.z);
    const grp = new THREE.Group();
    // 分段塔身
    const segs = 4;
    for (let i = 0; i < segs; i++) {
      const sh = sp.h / segs;
      const w = 0.85 - i * 0.1;
      const body = new THREE.Mesh(new THREE.BoxGeometry(w, sh * 0.94, w), towerMat);
      body.position.y = sh * (i + 0.5);
      body.castShadow = true;
      grp.add(body);
      // 段间发光带
      const band = new THREE.Mesh(
        new THREE.BoxGeometry(w * 1.06, 0.06, w * 1.06),
        new THREE.MeshBasicMaterial({
          color: sp.c,
          transparent: true,
          opacity: 0.7,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      band.position.y = sh * (i + 1);
      grp.add(band);
    }
    // 顶帽
    const cap = new THREE.Mesh(
      new THREE.BoxGeometry(1.25, 0.45, 1.25),
      new THREE.MeshStandardMaterial({
        color: 0x07080c,
        emissive: sp.c,
        emissiveIntensity: 2.6,
        roughness: 0.4,
      }),
    );
    cap.position.y = sp.h + 0.22;
    grp.add(cap);
    // 环绕全息环
    const holo = new THREE.Mesh(
      new THREE.TorusGeometry(2.0, 0.035, 6, 64),
      new THREE.MeshBasicMaterial({
        color: sp.c,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    holo.position.y = sp.h + 1.0;
    holo.rotation.x = Math.PI / 2;
    grp.add(holo);
    grp.position.set(sp.x, gy, sp.z);
    scene.add(grp);
    addObstacle(sp.x, sp.z, 0.62, gy + sp.h);

    const lamp = new THREE.PointLight(sp.c, 70, 32, 2);
    lamp.position.set(sp.x, gy + sp.h + 1.3, sp.z);
    scene.add(lamp);
    addSprite(
      sp.c === NEON_CYAN ? glowCyan : sp.c === NEON_MAGENTA ? glowMag : glowViolet,
      sp.x,
      gy + sp.h + 0.6,
      sp.z,
      7,
      0.55,
    );

    towerTops.push(new THREE.Vector3(sp.x, gy + sp.h + 1.0, sp.z));
    updaters.push((dt, t) => {
      holo.rotation.z = t * 1.5;
      holo.rotation.x = Math.PI / 2 + Math.sin(t * 0.8 + sp.x) * 0.16;
      cap.material.emissiveIntensity = 2.1 + 0.9 * (0.5 + 0.5 * Math.sin(t * 2.4 + sp.z));
    });
  }

  // 塔间悬空电缆
  const cableMat = new THREE.MeshBasicMaterial({
    color: NEON_CYAN,
    transparent: true,
    opacity: 0.32,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  for (let i = 0; i < towerTops.length; i++) {
    const a = towerTops[i];
    const b = towerTops[(i + 1) % towerTops.length];
    const mid = new THREE.Vector3((a.x + b.x) * 0.5, Math.min(a.y, b.y) - 2.4, (a.z + b.z) * 0.5);
    const curve = new THREE.CatmullRomCurve3([a, mid, b]);
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 26, 0.035, 4, false), cableMat);
    scene.add(tube);
  }

  // ============================================================
  // 9. 光柱
  // ============================================================
  for (const [px, pz, c, rad] of [
    [18, -8, NEON_CYAN, 3.0],
    [-20, 4, NEON_MAGENTA, 2.6],
    [-4, 18, NEON_VIOLET, 2.4],
  ]) {
    const gy = heightAt(px, pz);
    const pillar = new THREE.Mesh(
      new THREE.CylinderGeometry(rad * 0.55, rad, 78, 26, 1, true),
      new THREE.MeshBasicMaterial({
        color: c,
        transparent: true,
        opacity: 0.06,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
        fog: false,
      }),
    );
    pillar.position.set(px, gy + 39, pz);
    scene.add(pillar);
    updaters.push((dt, t) => {
      pillar.material.opacity = 0.04 + 0.035 * (0.5 + 0.5 * Math.sin(t * 1.1 + px + pz));
    });
  }

  // ============================================================
  // 10. 全息广告牌
  // ============================================================
  function makeBillboardTexture(text, color) {
    const cv = document.createElement('canvas');
    cv.width = 512;
    cv.height = 96;
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.font = 'bold 42px "Share Tech Mono", monospace';
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 18;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 256, 48);
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }
  const billboards = [
    { x: 10, z: -6, y: 7.0, txt: 'NEON ISLE // 数据链已接入', c: '#00f0ff' },
    { x: -14, z: 10, y: 6.0, txt: 'WASD > MOVE  ·  E > SYNC', c: '#ff2d95' },
    { x: 20, z: -18, y: 8.0, txt: 'ENERGY CORE x2 记忆体待修复', c: '#00f0ff' },
    { x: -26, z: -10, y: 5.5, txt: 'DL-07 ONLINE  ·  R-7 ACTIVE', c: '#7a4dff' },
  ];
  for (const b of billboards) {
    const mesh = new THREE.Mesh(
      new THREE.PlaneGeometry(9.5, 1.8),
      new THREE.MeshBasicMaterial({
        map: makeBillboardTexture(b.txt, b.c),
        transparent: true,
        opacity: 0.46,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
    );
    const baseY = heightAt(b.x, b.z) + b.y;
    mesh.position.set(b.x, baseY, b.z);
    scene.add(mesh);
    updaters.push((dt, t) => {
      mesh.rotation.y = t * 0.26 + b.x * 0.7;
      mesh.position.y = baseY + Math.sin(t * 0.8 + b.z) * 0.24;
      mesh.material.opacity = 0.4 + 0.09 * (0.5 + 0.5 * Math.sin(t * 1.7 + b.x));
    });
  }

  // ============================================================
  // 11. 栈桥与码头
  // ============================================================
  const plankMat = new THREE.MeshStandardMaterial({
    color: 0x141a26,
    roughness: 0.9,
    metalness: 0.15,
  });
  const bridgeA = Math.PI * 0.34;
  const bridgeGrp = new THREE.Group();
  const plankN = 22;
  for (let i = 0; i < plankN; i++) {
    const rr = 30 + i * 1.55;
    const x = Math.cos(bridgeA) * rr;
    const z = Math.sin(bridgeA) * rr;
    const plank = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.22, 1.3), plankMat);
    plank.position.set(x, Math.max(heightAt(x, z), 0.28) + 0.1, z);
    plank.rotation.y = -bridgeA + Math.PI / 2;
    plank.castShadow = true;
    plank.receiveShadow = true;
    bridgeGrp.add(plank);
    // 两侧灯带
    if (i % 2 === 0) {
      for (const sgn of [-1, 1]) {
        const rail = new THREE.Mesh(
          new THREE.BoxGeometry(0.1, 0.1, 0.32),
          new THREE.MeshBasicMaterial({
            color: NEON_CYAN,
            transparent: true,
            opacity: 0.85,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          }),
        );
        const off = 0.72 * sgn;
        rail.position.set(
          x + Math.cos(bridgeA + Math.PI / 2) * off,
          Math.max(heightAt(x, z), 0.28) + 0.62,
          z + Math.sin(bridgeA + Math.PI / 2) * off,
        );
        bridgeGrp.add(rail);
      }
    }
  }
  scene.add(bridgeGrp);
  updaters.push((dt, t) => {
    bridgeGrp.children.forEach((c, i) => {
      if (c.material && c.material.blending === THREE.AdditiveBlending) {
        c.material.opacity = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(t * 2.2 - i * 0.35));
      }
    });
  });

  // 码头集装箱
  const containerPalette = [0x0e2a33, 0x2a0e1c, 0x131a2a, 0x1a1420];
  const containerSpots = [
    [30, 26, 1],
    [33, 24, 2],
    [28, 30, 1],
    [-32, 20, 1],
    [-28, 24, 2],
  ];
  for (const [cx, cz, stack] of containerSpots) {
    const gy = Math.max(heightAt(cx, cz), 0.3);
    for (let s = 0; s < stack; s++) {
      const box = new THREE.Mesh(
        new THREE.BoxGeometry(4.4, 2.3, 2.3),
        new THREE.MeshStandardMaterial({
          color: containerPalette[Math.abs(s * 3 + cx) % containerPalette.length],
          roughness: 0.82,
          metalness: 0.25,
        }),
      );
      box.position.set(cx, gy + 1.15 + s * 2.35, cz);
      box.rotation.y = (cx * 0.7 + s) % Math.PI;
      box.castShadow = true;
      box.receiveShadow = true;
      scene.add(box);
      // 长方体箱体:沿长轴排 3 枚圆形碰撞体,近似矩形轮廓并保留圆角手感
      const bry = box.rotation.y;
      for (let k = -1; k <= 1; k++) {
        addObstacle(
          cx + Math.cos(bry) * k * 1.4,
          cz - Math.sin(bry) * k * 1.4,
          1.25,
          gy + 2.3 + s * 2.35,
        );
      }
      // 角标灯
      const strip = new THREE.Mesh(
        new THREE.BoxGeometry(4.5, 0.06, 2.4),
        new THREE.MeshBasicMaterial({
          color: (s + cx) % 2 ? NEON_MAGENTA : NEON_CYAN,
          transparent: true,
          opacity: 0.55,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      strip.position.set(cx, gy + 2.3 + s * 2.35, cz);
      strip.rotation.y = box.rotation.y;
      scene.add(strip);
    }
  }

  // 管道:贴地输能管线 + 支撑墩 + 节点阀
  const pipeMat = new THREE.MeshStandardMaterial({
    color: 0x18202c,
    roughness: 0.45,
    metalness: 0.7,
  });
  const pipeGlowMat = new THREE.MeshBasicMaterial({
    color: NEON_CYAN,
    transparent: true,
    opacity: 0.5,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const pipePaths = [
    [
      [16, -6, 0.95],
      [12, 2, 0.9],
      [4, 10, 0.85],
      [-4, 16, 0.8],
    ],
    [
      [22, 12, 0.8],
      [14, 18, 0.75],
      [6, 24, 0.7],
    ],
  ];
  for (const path of pipePaths) {
    const pts = path.map(([x, z, y]) => new THREE.Vector3(x, heightAt(x, z) + y, z));
    const curve = new THREE.CatmullRomCurve3(pts);
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 40, 0.32, 8, false), pipeMat);
    tube.castShadow = true;
    tube.receiveShadow = true;
    scene.add(tube);
    // 管顶发光条
    const glowTube = new THREE.Mesh(new THREE.TubeGeometry(curve, 40, 0.07, 5, false), pipeGlowMat);
    glowTube.position.y = 0.3;
    scene.add(glowTube);
    // 节点阀 + 支撑墩
    for (const p of pts) {
      const joint = new THREE.Mesh(new THREE.CylinderGeometry(0.48, 0.48, 0.62, 8), pipeMat);
      joint.position.copy(p);
      joint.castShadow = true;
      scene.add(joint);
      const cap = new THREE.Mesh(
        new THREE.CylinderGeometry(0.52, 0.52, 0.06, 8),
        new THREE.MeshBasicMaterial({
          color: NEON_CYAN,
          transparent: true,
          opacity: 0.75,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      cap.position.set(p.x, p.y + 0.32, p.z);
      scene.add(cap);
      const py = heightAt(p.x, p.z);
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.2, p.y - py + 0.2, 6), pipeMat);
      leg.position.set(p.x, py + (p.y - py) * 0.5, p.z);
      scene.add(leg);
    }
  }

  // ============================================================
  // 12. 悬浮灯笼 / 光球
  // ============================================================
  const lanternN = 26;
  for (let i = 0; i < lanternN; i++) {
    const a = rand() * Math.PI * 2;
    const rr = 6 + rand() * (R * 0.72);
    const x = Math.cos(a) * rr,
      z = Math.sin(a) * rr;
    const gy = heightAt(x, z);
    if (gy < 0.4) continue;
    const hgt = 2.2 + rand() * 5.5;
    const isMag = rand() > 0.6;
    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.16, 10, 8),
      new THREE.MeshBasicMaterial({
        color: isMag ? 0xffb0d8 : 0xbdf6ff,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    orb.position.set(x, gy + hgt, z);
    scene.add(orb);
    addSprite(isMag ? glowMag : glowCyan, x, gy + hgt, z, 1.1, 0.3);
    const ph = rand() * Math.PI * 2;
    const amp = 0.3 + rand() * 0.5;
    updaters.push((dt, t) => {
      orb.position.y = gy + hgt + Math.sin(t * 0.9 + ph) * amp;
      orb.position.x = x + Math.sin(t * 0.5 + ph) * 0.4;
    });
  }

  // ============================================================
  // 13. 数据流粒子
  // ============================================================
  const PN = 320;
  const pPos = new Float32Array(PN * 3);
  const pSpeed = new Float32Array(PN);
  for (let i = 0; i < PN; i++) {
    const a = rand() * Math.PI * 2,
      rr = rand() * 78;
    pPos[i * 3] = Math.cos(a) * rr;
    pPos[i * 3 + 1] = rand() * 30;
    pPos[i * 3 + 2] = Math.sin(a) * rr;
    pSpeed[i] = 0.5 + rand() * 1.9;
  }
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const points = new THREE.Points(
    pGeo,
    new THREE.PointsMaterial({
      map: makeDotTexture(THREE),
      color: 0x35e0ff,
      size: 0.3,
      transparent: true,
      opacity: 0.5,
      alphaTest: 0.01,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    }),
  );
  scene.add(points);
  updaters.push((dt) => {
    const arr = pGeo.attributes.position.array;
    for (let i = 0; i < PN; i++) {
      arr[i * 3 + 1] += pSpeed[i] * dt;
      if (arr[i * 3 + 1] > 32) arr[i * 3 + 1] = 0;
    }
    pGeo.attributes.position.needsUpdate = true;
  });

  // 萤火:缓慢漂浮的近景微粒
  const FN = 80;
  const fPos = new Float32Array(FN * 3);
  const fPhase = new Float32Array(FN);
  for (let i = 0; i < FN; i++) {
    const a = rand() * Math.PI * 2,
      rr = rand() * (R * 0.9);
    const x = Math.cos(a) * rr,
      z = Math.sin(a) * rr;
    fPos[i * 3] = x;
    fPos[i * 3 + 1] = Math.max(heightAt(x, z), 0) + 0.4 + rand() * 3.4;
    fPos[i * 3 + 2] = z;
    fPhase[i] = rand() * Math.PI * 2;
  }
  const fGeo = new THREE.BufferGeometry();
  fGeo.setAttribute('position', new THREE.BufferAttribute(fPos, 3));
  const flies = new THREE.Points(
    fGeo,
    new THREE.PointsMaterial({
      map: makeDotTexture(THREE),
      color: 0x7ef0ff,
      size: 0.26,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    }),
  );
  scene.add(flies);
  updaters.push((dt, t) => {
    const arr = fGeo.attributes.position.array;
    for (let i = 0; i < FN; i++) {
      arr[i * 3 + 1] += Math.sin(t * 1.1 + fPhase[i]) * 0.14 * dt;
      arr[i * 3] += Math.cos(t * 0.7 + fPhase[i]) * 0.16 * dt;
      arr[i * 3 + 2] += Math.sin(t * 0.6 + fPhase[i] * 1.7) * 0.16 * dt;
    }
    fGeo.attributes.position.needsUpdate = true;
  });

  // ============================================================
  // 14. 交互物
  // ============================================================
  function addGlowDisc(x, z, color, radius = 1.2) {
    const gy = Math.max(heightAt(x, z), -0.22) + 0.03;
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(radius, 26).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.22,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    disc.position.set(x, gy, z);
    scene.add(disc);
    updaters.push((dt, t) => {
      disc.material.opacity = 0.14 + 0.13 * (0.5 + 0.5 * Math.sin(t * 2.6 + x));
    });
    return disc;
  }

  // 1) 数据终端 DL-07
  {
    const x = 10,
      z = -4;
    const gy = heightAt(x, z);
    const grp = new THREE.Group();
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 1.15, 0.55, 8), towerMat);
    base.position.y = 0.27;
    base.castShadow = true;
    const column = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.2, 1.0, 8), pipeMat);
    column.position.y = 1.0;
    const consoleBox = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.95, 0.55), towerMat);
    consoleBox.position.set(0, 1.55, 0);
    consoleBox.rotation.x = -0.28;
    consoleBox.castShadow = true;
    const screen = new THREE.Mesh(
      new THREE.PlaneGeometry(1.02, 0.62),
      new THREE.MeshStandardMaterial({
        color: 0x03141c,
        emissive: NEON_CYAN,
        emissiveIntensity: 2.2,
      }),
    );
    screen.position.set(0, 1.62, 0.29);
    screen.rotation.x = -0.28;
    const holo = new THREE.Mesh(
      new THREE.ConeGeometry(0.95, 2.1, 4, 1, true),
      new THREE.MeshBasicMaterial({
        color: NEON_CYAN,
        transparent: true,
        opacity: 0.3,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
    );
    holo.position.y = 3.0;
    holo.rotation.y = Math.PI / 4;
    grp.add(base, column, consoleBox, screen, holo);
    grp.position.set(x, gy, z);
    scene.add(grp);
    addGlowDisc(x, z, NEON_CYAN, 1.6);
    addSprite(glowCyan, x, gy + 1.7, z, 5, 0.45);
    updaters.push((dt, t) => {
      holo.rotation.y = t * 1.6;
      holo.position.y = 3.0 + Math.sin(t * 2) * 0.12;
      screen.material.emissiveIntensity = 1.9 + 0.7 * (0.5 + 0.5 * Math.sin(t * 3.4));
    });
    addObstacle(x, z, 0.85, gy + 1.7);
    interactives.push({
      name: '数据终端 DL-07',
      kind: 'terminal',
      pos: new THREE.Vector3(x, gy, z),
    });
  }

  // 2) NPC 维修机器人 R-7
  {
    const x = -12,
      z = 8;
    const gy = heightAt(x, z);
    const grp = new THREE.Group();
    const botMat = new THREE.MeshStandardMaterial({
      color: 0x161d2a,
      roughness: 0.42,
      metalness: 0.65,
    });
    const botTrim = new THREE.MeshStandardMaterial({
      color: 0x0a2a33,
      emissive: NEON_CYAN,
      emissiveIntensity: 1.6,
      roughness: 0.4,
    });
    const eyeMat = new THREE.MeshStandardMaterial({
      color: 0x03141c,
      emissive: NEON_CYAN,
      emissiveIntensity: 3.0,
    });
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.46, 16, 12), botMat);
    body.scale.set(1, 0.8, 1);
    body.position.y = 0.62;
    const beltR = new THREE.Mesh(
      new THREE.TorusGeometry(0.44, 0.045, 6, 24).rotateX(Math.PI / 2),
      botTrim,
    );
    beltR.position.y = 0.62;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.29, 14, 10), botMat);
    head.position.y = 1.12;
    const eye = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.08, 0.04), eyeMat);
    eye.position.set(0, 1.15, 0.25);
    const dish = new THREE.Mesh(new THREE.ConeGeometry(0.24, 0.32, 6), botMat);
    dish.position.y = 1.46;
    dish.rotation.x = Math.PI;
    // 悬浮推进器
    const thr = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.16, 0.3, 8, 1, true), botTrim);
    thr.position.y = 0.14;
    // 侧面小臂
    for (const sgn of [-1, 1]) {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.42, 0.09), botMat);
      arm.position.set(0.44 * sgn, 0.72, 0);
      arm.rotation.z = 0.22 * sgn;
      grp.add(arm);
    }
    grp.add(body, beltR, head, eye, dish, thr);
    grp.position.set(x, gy + 0.42, z);
    grp.traverse((o) => {
      if (o.isMesh) o.castShadow = true;
    });
    scene.add(grp);
    addGlowDisc(x, z, NEON_CYAN, 1.3);
    addSprite(glowCyan, x, gy + 1.3, z, 3.2, 0.4);
    updaters.push((dt, t) => {
      grp.position.y = gy + 0.42 + Math.sin(t * 1.9) * 0.13;
      grp.rotation.y = Math.sin(t * 0.4) * 0.55;
      dish.rotation.z = Math.sin(t * 2.2) * 0.3;
      thr.scale.y = 0.85 + 0.3 * (0.5 + 0.5 * Math.sin(t * 9));
    });
    addObstacle(x, z, 0.62, gy + 1.6);
    interactives.push({ name: '维修机器人 R-7', kind: 'npc', pos: new THREE.Vector3(x, gy, z) });
  }

  // 3) 能量核心 x2
  const coreSpots = [
    [22, -20],
    [-26, -16],
  ];
  for (const [x, z] of coreSpots) {
    const gy = heightAt(x, z);
    const grp = new THREE.Group();
    const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.95, 0.45, 8), towerMat);
    pedestal.position.y = 0.22;
    pedestal.castShadow = true;
    const ringBase = new THREE.Mesh(
      new THREE.TorusGeometry(0.85, 0.04, 6, 28).rotateX(Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: NEON_MAGENTA,
        transparent: true,
        opacity: 0.7,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    ringBase.position.y = 0.5;
    const core = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.55, 0),
      new THREE.MeshStandardMaterial({
        color: 0x220a16,
        emissive: NEON_MAGENTA,
        emissiveIntensity: 2.4,
        roughness: 0.2,
        metalness: 0.3,
      }),
    );
    core.position.y = 1.25;
    core.castShadow = true;
    const inner = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.32, 0),
      new THREE.MeshBasicMaterial({
        color: 0xff8dc0,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    inner.position.y = 1.25;
    const cage = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.95, 0),
      new THREE.MeshBasicMaterial({
        color: NEON_MAGENTA,
        transparent: true,
        opacity: 0.16,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        wireframe: true,
      }),
    );
    cage.position.y = 1.25;
    grp.add(pedestal, ringBase, core, inner, cage);
    grp.position.set(x, gy, z);
    scene.add(grp);
    addGlowDisc(x, z, NEON_MAGENTA, 1.5);
    addSprite(glowMag, x, gy + 1.25, z, 6, 0.5);
    updaters.push((dt, t) => {
      core.rotation.y = t * 1.1;
      core.rotation.x = t * 0.45;
      inner.rotation.y = -t * 2.1;
      inner.rotation.z = t * 1.3;
      cage.rotation.y = -t * 0.6;
      cage.rotation.x = t * 0.25;
      core.material.emissiveIntensity = 1.9 + 0.9 * (0.5 + 0.5 * Math.sin(t * 3 + x));
      ringBase.rotation.z = t * 0.9;
    });
    addObstacle(x, z, 0.92, gy + 1.6);
    interactives.push({ name: '能量核心', kind: 'core', pos: new THREE.Vector3(x, gy, z) });
  }

  function update(dt, t) {
    for (const u of updaters) u(dt, t);
  }

  return { interactives, obstacles, update };
}
