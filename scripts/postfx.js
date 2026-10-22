// ============ 后期处理:HDR 泛光 / ACES 色调映射 / 电影级调色 ============
// 管线:场景 → HDR 缓冲 → 亮部提取 → 双层高斯泛光 → 合成(ACES + 分级 + 锐化 + 暗角 + 颗粒)
// 注意:three 只在渲染到画布时应用 renderer.toneMapping,渲染到 RT 时会跳过,
//      所以 ACES 必须在这里做,否则高光会直接硬切。

const VERT = [
  'varying vec2 vUv;',
  'void main() {',
  '  vUv = uv;',
  '  gl_Position = vec4(position.xy, 0.0, 1.0);',
  '}',
].join('\n');

const FRAG_BRIGHT = [
  'uniform sampler2D tDiffuse;',
  'uniform float uThreshold;',
  'uniform float uKnee;',
  'varying vec2 vUv;',
  'void main() {',
  '  vec3 c = texture2D(tDiffuse, vUv).rgb;',
  '  float l = max(c.r, max(c.g, c.b));',
  '  float s = smoothstep(uThreshold, uThreshold + uKnee, l);',
  '  gl_FragColor = vec4(c * s, 1.0);',
  '}',
].join('\n');

const FRAG_BLUR = [
  'uniform sampler2D tDiffuse;',
  'uniform vec2 uDir;',
  'varying vec2 vUv;',
  'void main() {',
  '  vec3 sum = texture2D(tDiffuse, vUv).rgb * 0.2270270270;',
  '  sum += texture2D(tDiffuse, vUv + uDir * 1.3846153846).rgb * 0.3162162162;',
  '  sum += texture2D(tDiffuse, vUv - uDir * 1.3846153846).rgb * 0.3162162162;',
  '  sum += texture2D(tDiffuse, vUv + uDir * 3.2307692308).rgb * 0.0702702703;',
  '  sum += texture2D(tDiffuse, vUv - uDir * 3.2307692308).rgb * 0.0702702703;',
  '  gl_FragColor = vec4(sum, 1.0);',
  '}',
].join('\n');

const FRAG_COMPOSITE = [
  'uniform sampler2D tScene;',
  'uniform sampler2D tBloomA;',
  'uniform sampler2D tBloomB;',
  'uniform vec2 uTexel;',
  'uniform float uStrength;',
  'uniform float uStrengthWide;',
  'uniform float uExposure;',
  'uniform float uTime;',
  'uniform float uVignette;',
  'uniform float uGrain;',
  'uniform float uAberration;',
  'uniform float uSharpen;',
  'uniform float uContrast;',
  'uniform float uSaturation;',
  'uniform float uTint;',
  'uniform float uBlackPoint;',
  'uniform float uWhitePoint;',
  'varying vec2 vUv;',

  // ACES filmic 近似(Karis 拟合),高光滚降自然、暗部不死黑
  'vec3 acesFilmic(vec3 x) {',
  '  const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;',
  '  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);',
  '}',
  'float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }',

  'void main() {',
  '  vec2 d = vUv - 0.5;',
  '  float r2 = dot(d, d);',
  // 轻微横向色散(仅在画面边缘,中间几乎无偏移)
  '  float ab = uAberration * r2;',
  '  vec3 c;',
  '  c.r = texture2D(tScene, vUv + d * ab).r;',
  '  c.g = texture2D(tScene, vUv).g;',
  '  c.b = texture2D(tScene, vUv - d * ab).b;',

  // 锐化:非锐化掩模(补偿 MSAA 解析后的轻微软化)
  '  vec3 n = texture2D(tScene, vUv + vec2(uTexel.x, 0.0)).rgb',
  '         + texture2D(tScene, vUv - vec2(uTexel.x, 0.0)).rgb',
  '         + texture2D(tScene, vUv + vec2(0.0, uTexel.y)).rgb',
  '         + texture2D(tScene, vUv - vec2(0.0, uTexel.y)).rgb;',
  '  n *= 0.25;',
  '  c += (c - n) * uSharpen;',

  // 双层泛光:近层收紧高光,远层铺柔和光雾
  '  vec3 bloom = texture2D(tBloomA, vUv).rgb * uStrength',
  '             + texture2D(tBloomB, vUv).rgb * uStrengthWide;',
  '  c += bloom;',

  // 曝光 + ACES 色调映射
  '  c *= uExposure;',
  '  c = acesFilmic(c);',

  // 线性 → sRGB
  '  c = pow(max(c, vec3(0.0)), vec3(1.0 / 2.2));',

  // ---------- 电影级分级(在 sRGB 空间做,接近 LUT 的观感)----------
  '  float l = luma(c);',
  // 分离色调:暗部偏青蓝、高光偏暖金
  '  vec3 shadowTint = vec3(0.82, 0.94, 1.12);',
  '  vec3 highTint   = vec3(1.08, 1.02, 0.90);',
  '  vec3 tintCol = mix(shadowTint, highTint, smoothstep(0.08, 0.72, l));',
  '  c = mix(c, c * tintCol, uTint);',
  // 对比 S 曲线(围绕中灰做柔和压缩)
  '  c = mix(c, smoothstep(0.0, 1.0, c), uContrast);',
  // 饱和度
  '  float l2 = luma(c);',
  '  c = mix(vec3(l2), c, uSaturation);',

  // 黑白场:去掉泛光垫底的灰雾,让暗部真正下去
  '  c = clamp((c - uBlackPoint) / max(0.0001, uWhitePoint - uBlackPoint), 0.0, 1.0);',

  // 暗角
  '  float vig = 1.0 - uVignette * smoothstep(0.18, 0.95, r2 * 1.35);',
  '  c *= vig;',

  // 胶片颗粒(轻微,避免死板)
  '  float g = fract(sin(dot(vUv * 913.0 + uTime * 0.37, vec2(12.9898, 78.233))) * 43758.5453);',
  '  c += (g - 0.5) * uGrain;',

  '  gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);',
  '}',
].join('\n');

export function createPostFX(THREE, renderer, scene, camera) {
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
  quad.frustumCulled = false;
  const quadScene = new THREE.Scene();
  quadScene.add(quad);
  const quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  const texel = new THREE.Vector2(1, 1);
  const maxSamples = renderer.capabilities.maxSamples || 0;

  const brightMat = new THREE.ShaderMaterial({
    uniforms: { tDiffuse: { value: null }, uThreshold: { value: 1.05 }, uKnee: { value: 0.65 } },
    vertexShader: VERT,
    fragmentShader: FRAG_BRIGHT,
    depthTest: false,
    depthWrite: false,
  });

  const blurMat = new THREE.ShaderMaterial({
    uniforms: { tDiffuse: { value: null }, uDir: { value: new THREE.Vector2() } },
    vertexShader: VERT,
    fragmentShader: FRAG_BLUR,
    depthTest: false,
    depthWrite: false,
  });

  const compositeMat = new THREE.ShaderMaterial({
    uniforms: {
      tScene: { value: null },
      tBloomA: { value: null },
      tBloomB: { value: null },
      uTexel: { value: new THREE.Vector2() },
      uStrength: { value: 0.26 },
      uStrengthWide: { value: 0.15 },
      uExposure: { value: 1.05 },
      uTime: { value: 0 },
      uVignette: { value: 0.34 },
      uGrain: { value: 0.01 },
      uAberration: { value: 0.0011 },
      uSharpen: { value: 0.32 },
      uContrast: { value: 0.24 },
      uSaturation: { value: 1.1 },
      uTint: { value: 0.55 },
      uBlackPoint: { value: 0.028 },
      uWhitePoint: { value: 0.985 },
    },
    vertexShader: VERT,
    fragmentShader: FRAG_COMPOSITE,
    depthTest: false,
    depthWrite: false,
  });

  let rtScene = null,
    rtA = null,
    rtB = null,
    rtC = null,
    rtD = null;

  const rtOpts = {
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    depthBuffer: false,
    stencilBuffer: false,
  };

  function setSize(w, h) {
    w = Math.max(1, Math.floor(w));
    h = Math.max(1, Math.floor(h));
    for (const rt of [rtScene, rtA, rtB, rtC, rtD]) if (rt) rt.dispose();
    rtScene = new THREE.WebGLRenderTarget(w, h, {
      type: THREE.HalfFloatType,
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      depthBuffer: true,
      stencilBuffer: false,
      samples: Math.min(2, maxSamples),
    });
    const hw = Math.max(1, Math.floor(w / 2)),
      hh = Math.max(1, Math.floor(h / 2));
    const qw = Math.max(1, Math.floor(w / 4)),
      qh = Math.max(1, Math.floor(h / 4));
    rtA = new THREE.WebGLRenderTarget(hw, hh, rtOpts);
    rtB = new THREE.WebGLRenderTarget(hw, hh, rtOpts);
    rtC = new THREE.WebGLRenderTarget(qw, qh, rtOpts);
    rtD = new THREE.WebGLRenderTarget(qw, qh, rtOpts);
    texel.set(1 / w, 1 / h);
    compositeMat.uniforms.uTexel.value.set(1 / w, 1 / h);
  }

  function pass(mat, target) {
    quad.material = mat;
    renderer.setRenderTarget(target);
    renderer.render(quadScene, quadCam);
  }

  function blur(src, dst, dirX, dirY) {
    blurMat.uniforms.tDiffuse.value = src.texture;
    blurMat.uniforms.uDir.value.set(dirX, dirY);
    pass(blurMat, dst);
  }

  function render(t) {
    if (!rtScene) return;
    // 1) 场景 → HDR 缓冲
    renderer.setRenderTarget(rtScene);
    renderer.render(scene, camera);

    // 2) 亮部提取(半分辨率)
    brightMat.uniforms.tDiffuse.value = rtScene.texture;
    pass(brightMat, rtA);

    // 3) 近层泛光:半分辨率两轮双向高斯
    const hx = 1 / rtA.width,
      hy = 1 / rtA.height;
    blur(rtA, rtB, hx * 1.0, 0);
    blur(rtB, rtA, 0, hy * 1.0);
    blur(rtA, rtB, hx * 2.2, 0);
    blur(rtB, rtA, 0, hy * 2.2);

    // 4) 远层泛光:降采样到 1/4 再模糊(方向传 0 退化为纯采样 = 降采样)
    blur(rtA, rtC, 0, 0);
    const qx = 1 / rtC.width,
      qy = 1 / rtC.height;
    blur(rtC, rtD, qx * 2.0, 0);
    blur(rtD, rtC, 0, qy * 2.0);
    blur(rtC, rtD, qx * 4.4, 0);
    blur(rtD, rtC, 0, qy * 4.4);

    // 5) 合成到画布
    compositeMat.uniforms.tScene.value = rtScene.texture;
    compositeMat.uniforms.tBloomA.value = rtA.texture;
    compositeMat.uniforms.tBloomB.value = rtC.texture;
    compositeMat.uniforms.uTime.value = t;
    pass(compositeMat, null);
  }

  return { setSize, render, uniforms: compositeMat.uniforms };
}
