// ============ 虚拟摇杆(移动端) ============
// 约定: vec.x 向右为正,vec.y 向前(上推)为正,均为 -1~1。

const MAX_RADIUS = 46; // px,遥感能达到的最大偏移

export function createJoystick(root, knob) {
  const vec = { x: 0, y: 0 };
  let pid = null;
  let originX = 0;
  let originY = 0;

  function reset() {
    vec.x = 0; vec.y = 0;
    pid = null;
    knob.style.transform = '';

  }

  root.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    if (pid !== null) return;
    pid = e.pointerId;
    root.setPointerCapture(pid);
    const rect = root.getBoundingClientRect();
    originX = rect.left + rect.width / 2;
    originY = rect.top + rect.height / 2;
    move(e);
  });

  function move(e) {
    const dx = e.clientX - originX;
    const dy = e.clientY - originY;
    const dist = Math.hypot(dx, dy);
    const clamped = dist > MAX_RADIUS ? MAX_RADIUS / dist : 1;
    vec.x = (dx * clamped) / MAX_RADIUS;
    vec.y = (-dy * clamped) / MAX_RADIUS;
    knob.style.transform = `translate(${vec.x * MAX_RADIUS}px, ${-vec.y * MAX_RADIUS}px)`;
  }

  root.addEventListener('pointermove', (e) => {
    if (e.pointerId !== pid) return;
    move(e);
  });

  const end = (e) => {
    if (e.pointerId !== pid) return;
    reset();
  };
  root.addEventListener('pointerup', end);
  root.addEventListener('pointercancel', end);

  return { vec, isDragged: () => pid !== null };
}
