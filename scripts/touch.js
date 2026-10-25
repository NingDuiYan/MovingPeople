// ============ 移动端触屏操作 ============
// 只在粗指针设备上挂载:左下虚拟摇杆走位,右下四个按钮(拳 / 跳 / 蹲 / 挡)+ 静步开关。
// 这里只负责把手指位置翻译成"摇杆方向"和"按下事件",动作选择与速度仍由 character.js 决定,
// 所以触屏与键鼠共用同一套状态机,不会出现两套行为。
const STICK_RADIUS = 46; // 摇杆中心到可拖动的最大距离(px)

/**
 * 创建触屏控件。非触屏设备直接返回 null,调用方据此跳过挂载。
 * @param {{
 *   onMove: (x: number, y: number) => void,  // x 右为正、y 上为正,范围 -1..1
 *   onPunch: () => void,
 *   onJump: () => void,
 *   onCrouch: () => void,
 *   onBlock: (held: boolean) => void,
 *   onSneak: (on: boolean) => void,
 * }} handlers
 */
export function createTouchControls(handlers) {
  if (!window.matchMedia('(pointer: coarse)').matches) return null;

  const root = document.createElement('div');
  root.className = 'touch';
  root.innerHTML = `
    <div class="touch-stick" role="presentation">
      <span class="touch-stick-knob"></span>
    </div>
    <div class="touch-buttons">
      <button class="touch-btn" type="button" data-action="punch">拳</button>
      <button class="touch-btn" type="button" data-action="jump">跳</button>
      <button class="touch-btn" type="button" data-action="crouch">蹲</button>
      <button class="touch-btn" type="button" data-action="block">挡</button>
      <button class="touch-btn touch-btn--sub" type="button" data-action="sneak">静</button>
    </div>
  `;
  document.body.append(root);
  document.body.classList.add('is-touch');

  const stick = root.querySelector('.touch-stick');
  const knob = root.querySelector('.touch-stick-knob');
  const sneakBtn = root.querySelector('[data-action="sneak"]');

  // —— 摇杆:按下位置为圆心,拖动偏移归一化成方向向量 ——
  let stickId = null;
  let originX = 0;
  let originY = 0;

  const emitMove = (dx, dy) => {
    const len = Math.hypot(dx, dy);
    const scale = len > STICK_RADIUS ? STICK_RADIUS / len : 1;
    const kx = dx * scale;
    const ky = dy * scale;
    knob.style.transform = `translate(calc(-50% + ${kx}px), calc(-50% + ${ky}px))`;
    handlers.onMove(kx / STICK_RADIUS, -ky / STICK_RADIUS);
  };

  const onStickDown = (event) => {
    if (stickId !== null) return;
    stickId = event.pointerId;
    // 少数浏览器/合成事件会抛 NotFoundError,拿不到捕获也不影响拖动
    try {
      stick.setPointerCapture(stickId);
    } catch {
      /* 忽略 */
    }
    const box = stick.getBoundingClientRect();
    originX = box.left + box.width / 2;
    originY = box.top + box.height / 2;
    emitMove(event.clientX - originX, event.clientY - originY);
    stick.classList.add('is-active');
  };
  const onStickMove = (event) => {
    if (event.pointerId !== stickId) return;
    emitMove(event.clientX - originX, event.clientY - originY);
  };
  const onStickUp = (event) => {
    if (event.pointerId !== stickId) return;
    stickId = null;
    stick.classList.remove('is-active');
    knob.style.transform = 'translate(-50%, -50%)';
    handlers.onMove(0, 0);
  };

  stick.addEventListener('pointerdown', onStickDown);
  stick.addEventListener('pointermove', onStickMove);
  stick.addEventListener('pointerup', onStickUp);
  stick.addEventListener('pointercancel', onStickUp);

  // —— 按钮:按下即触发,挡与静步是持续状态 ——
  const onButtonDown = (event) => {
    const button = event.currentTarget;
    const action = button.dataset.action;
    button.classList.add('is-pressed');
    // 阻止事件冒泡到 canvas,否则会被当成"拖拽转视角"或"左键出拳"
    event.preventDefault();
    event.stopPropagation();
    if (action === 'punch') handlers.onPunch();
    if (action === 'jump') handlers.onJump();
    if (action === 'crouch') handlers.onCrouch();
    if (action === 'block') handlers.onBlock(true);
    if (action === 'sneak') {
      const on = !button.classList.contains('is-on');
      button.classList.toggle('is-on', on);
      handlers.onSneak(on);
    }
  };
  const onButtonUp = (event) => {
    const button = event.currentTarget;
    button.classList.remove('is-pressed');
    if (button.dataset.action === 'block') handlers.onBlock(false);
  };

  for (const button of root.querySelectorAll('.touch-btn')) {
    button.addEventListener('pointerdown', onButtonDown);
    button.addEventListener('pointerup', onButtonUp);
    button.addEventListener('pointercancel', onButtonUp);
    button.addEventListener('pointerleave', onButtonUp);
  }

  // 触屏上键位提示没意义,换成触屏操作说明
  const hint = document.querySelector('.hint');
  if (hint) hint.textContent = '左侧摇杆 移动(推到底奔跑) · 右侧 拳/跳/蹲/挡/静 · 拖拽 转视角';

  return {
    dispose() {
      handlers.onMove(0, 0);
      handlers.onBlock(false);
      handlers.onSneak(false);
      sneakBtn.classList.remove('is-on');
      root.remove();
      document.body.classList.remove('is-touch');
    },
  };
}
