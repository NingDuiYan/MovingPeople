// ============ 场景内消息提示:一次一条,自动淡出 ============

const FADE_MS = 240;   // 与 .scene-msg 的 transition 时长一致

/**
 * 游戏内消息条:替代常驻键位栏,操作引导与状态变化都用一条会自动消失的提示告诉玩家。
 * 新消息不打断当前这条,排队依次播放;duration 控制单条停留时长。
 */
export function createToast({ root, textEl, defaultDuration = 3200 }) {
  const queue = [];
  let timer = null;
  let showing = false;

  /** 队列播完:淡出后再隐藏元素;淡出期间若来了新消息则不隐藏 */
  function settle() {
    showing = false;
    root.classList.remove('is-on');
    timer = setTimeout(() => {
      timer = null;
      if (!showing) root.hidden = true;
    }, FADE_MS);
  }

  function pump() {
    if (!queue.length) { settle(); return; }
    const item = queue.shift();
    showing = true;
    textEl.textContent = item.text;
    root.hidden = false;
    void root.offsetWidth;   // 强制回流:连续两条消息也能重放淡入
    root.classList.add('is-on');
    timer = setTimeout(() => { timer = null; pump(); }, item.duration);
  }

  /** 显示一条提示;正在显示时排队 */
  function show(text, duration = defaultDuration) {
    if (!text) return;
    queue.push({ text, duration });
    if (showing) return;
    if (timer) { clearTimeout(timer); timer = null; }
    pump();
  }

  /** 清空队列并立即收起 */
  function clear() {
    queue.length = 0;
    if (timer) { clearTimeout(timer); timer = null; }
    showing = false;
    root.classList.remove('is-on');
    root.hidden = true;
  }

  return { show, clear };
}
