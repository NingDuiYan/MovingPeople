// ============ 对话框(打字机效果) ============

const TYPE_INTERVAL_MS = 20;

export function createDialog({ root, nameEl, textEl, closeBtn }) {
  let lines = [];
  let lineIdx = 0;
  let timer = null;
  let lineDone = false;

  function clearTimer() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function showLine(idx) {
    lineIdx = idx;
    lineDone = false;
    const full = lines[idx] ?? '';
    textEl.textContent = '';
    let i = 0;
    clearTimer();
    timer = setInterval(() => {
      // 每 tick 输出 1~2 个字符,略带速度变化感
      const step = 1 + (i % 7 === 6 ? 1 : 0);
      i = Math.min(full.length, i + step);
      textEl.textContent = full.slice(0, i);
      if (i >= full.length) {
        clearTimer();
        lineDone = true;
      }
    }, TYPE_INTERVAL_MS);
  }

  function open(name, contentLines) {
    lines = contentLines;
    nameEl.textContent = name;
    root.hidden = false;
    textEl.classList.remove('dialog-text-complete');
    showLine(0);
  }

  function close() {
    clearTimer();
    root.hidden = true;
    textEl.textContent = '';
    lines = [];
  }

  /** E / 点触 时调用:正在打字 → 直接出全句;已出完 → 下一句或关闭 */
  function advance() {
    if (root.hidden) return;
    if (!lineDone) {
      clearTimer();
      textEl.textContent = lines[lineIdx] ?? '';
      lineDone = true;
      return;
    }
    if (lineIdx < lines.length - 1) {
      showLine(lineIdx + 1);
    } else {
      close();
    }
  }

  function isOpen() {
    return !root.hidden;
  }

  closeBtn.addEventListener('click', close);

  return { open, close, advance, isOpen };
}
