// ============ 程序化音效:脚步 ============
// 和贴图一样零外部资源:用 Web Audio 现场合成,不引入音频文件、不用预加载。
//
// 设计要点(上一版听着刺耳,重做过一次):
// - 不要「尖」:只用低通,不用带通。带通会把噪声削成又薄又涩的「呲」,而真实的
//   鞋底落地是「高频先没、低频先留」,所以中心频率要从高空快速滑下来。
// - 不要「嗡」:去掉原来的低频正弦。104Hz 正弦听起来像底鼓,戴耳机发闷、外放听不见;
//   改成同一段噪声再走一遍重低通,补出来的是「闷」而不是音高。
// - 要「短」:一次脚步只有 70~110ms,拉长就变成扫地的沙沙声。
// - 每一步都要不一样:音量、滑落终点、噪声起点全做随机,否则 0.5s 一次会像机关枪。
//
// 浏览器自动播放策略:AudioContext 必须由用户手势启动/恢复,所以这里全程懒初始化,
// 进游戏前不碰音频;主循环里的每次脚步都会顺手 unlock() 兜底。

const MASTER_GAIN = 0.55;     // 总线音量(脚步只是环境音的一部分,不该盖过画面)
const MIN_GAP = 0.08;         // 两次脚步的最小间隔(s):掉帧时步频脉冲可能连发,避免叠成爆音
const NOISE_SECONDS = 0.6;    // 复用噪声底的长度(s)

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

export function createStepAudio() {
  let ctx = null;
  let bus = null;             // 总线:开关只动它,已排队的节点不用逐个处理
  let noiseBuf = null;
  let lastTime = -1;
  let enabled = true;
  let foot = 0;               // 左右脚交替:音高/音色做微差,听感不机械

  /** 懒初始化音频上下文;不支持 Web Audio 的环境返回 null(游戏照常跑,只是没声音) */
  function ensure() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try {
      ctx = new AC();
    } catch (err) {
      ctx = null;
      return null;
    }

    bus = ctx.createGain();
    bus.gain.value = enabled ? MASTER_GAIN : 0;

    // 总线整形:掐掉 90Hz 以下的闷罐声,再削掉 5.2kHz 以上的「呲」
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 90;
    hp.Q.value = 0.6;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 5200;
    lp.Q.value = 0.5;
    // 连续疾跑时脚步会叠在一起,压限器兜底,不让总线削波(压得比之前柔)
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -18;
    limiter.knee.value = 12;
    limiter.ratio.value = 4;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.15;
    bus.connect(hp).connect(lp).connect(limiter).connect(ctx.destination);

    // 噪声底:一段白噪声反复复用,每次脚步声从随机位置截取,听感不重复
    const len = Math.floor(ctx.sampleRate * NOISE_SECONDS);
    noiseBuf = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    return ctx;
  }

  /** 在用户手势里调用:创建并恢复上下文。重复调用无害 */
  function unlock() {
    const c = ensure();
    if (!c) return;
    if (c.state === 'suspended') c.resume().catch(() => { /* 浏览器仍拒绝时等下一次手势 */ });
  }

  /** 从噪声底里截一段,接到 lowpass → gain →(可选声像)→ 总线 */
  function burst(c, now, opts) {
    const { peak, attack, decay, cutoffFrom, cutoffTo, rate, pan = 0 } = opts;
    const src = c.createBufferSource();
    src.buffer = noiseBuf;
    src.playbackRate.value = rate;

    const lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    lp.Q.value = 0.7;
    lp.frequency.setValueAtTime(cutoffFrom, now);
    lp.frequency.exponentialRampToValueAtTime(cutoffTo, now + decay);

    const gain = c.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    // 4~6ms 起音:够快才有「落点」,但不会像零起音那样「啪」一下
    gain.gain.exponentialRampToValueAtTime(peak, now + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + decay);

    // 左右脚做一点声像偏移,听起来是「两条腿」而不是同一个人在踩点
    let out = gain;
    if (pan && c.createStereoPanner) {
      const panner = c.createStereoPanner();
      panner.pan.value = pan;
      gain.connect(panner);
      out = panner;
    }
    src.connect(lp).connect(gain);
    out.connect(bus);
    const offset = Math.random() * Math.max(0, NOISE_SECONDS - decay - 0.08);
    src.start(now, offset, decay + 0.03);
  }

  /**
   * 单次脚步。
   * @param {number} strength 力度 0~1:走路轻、跑动重
   * @param {boolean} running 是否疾跑:决定亮度与时长
   */
  function footstep(strength = 1, running = false) {
    if (!enabled) return;
    const c = ensure();
    // 还没解锁(用户一次都没按键/触屏)时不出声:绝不把声音排队等解锁,否则一解锁会连响
    if (!c || c.state !== 'running') return;
    const now = c.currentTime;
    if (lastTime >= 0 && now - lastTime < MIN_GAP) return;
    lastTime = now;

    const s = clamp01(strength);
    foot = 1 - foot;
    const right = foot === 1;
    const jitter = 0.94 + Math.random() * 0.12;          // 每一步的音量微差
    const pitch = right ? 1.03 : 0.97;                   // 左右脚的音色微差
    const pan = right ? 0.16 : -0.16;                    // 左右脚的声像微差
    const dur = (running ? 0.075 : 0.1) * (0.85 + Math.random() * 0.3);

    // 1) 鞋底摩擦:噪声的高频在几十毫秒内滑掉,听感是「落」而不是「呲」
    burst(c, now, {
      peak: (running ? 0.4 : 0.24) * (0.7 + 0.5 * s) * jitter,
      attack: 0.004,
      decay: dur,
      cutoffFrom: (running ? 3000 : 2300) * pitch * jitter,
      cutoffTo: (running ? 620 : 520) * pitch,
      rate: pitch,
      pan: pan,
    });

    // 2) 落地重量:同一段噪声再走一遍重低通,给的不是音高而是「闷」和分量
    burst(c, now, {
      peak: (running ? 0.34 : 0.2) * (0.7 + 0.5 * s) * jitter,
      attack: 0.006,
      decay: dur * 1.1,
      cutoffFrom: 320 * pitch,
      cutoffTo: 180 * pitch,
      rate: 1,
      pan: pan * 0.6,
    });
  }

  /** 开关音效;已创建的上下文用极短斜坡过渡,不会有「咔」的爆音 */
  function setEnabled(on) {
    enabled = !!on;
    if (!enabled) lastTime = -1;   // 静音期间不要残留节流时间
    if (ctx && bus) bus.gain.setTargetAtTime(enabled ? MASTER_GAIN : 0, ctx.currentTime, 0.015);
  }

  function isEnabled() { return enabled; }

  return { unlock, footstep, setEnabled, isEnabled };
}
