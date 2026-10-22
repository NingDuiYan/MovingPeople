// ============ 设置弹窗:操作方式 / 键位 ============
// 键位的读写全在 keybinds.js 里,这里只管 DOM 与交互;binds 对象原地修改,
// 外部持有的引用会自动看到变化,不需要回传新对象。

import {
  KEY_ACTIONS,
  MOVE_PRESETS,
  codeToLabel,
  isBindableCode,
  bindCode,
  applyPreset,
  matchPreset,
  defaultBinds,
  writeBinds,
} from '../keybinds.js';

const HINT_IDLE = '点键帽后按下新键即可改绑,Esc 取消;撞键的会自动互换。';
const HINT_LISTEN = '正在改键:按下新的按键…(Esc 取消)';

/**
 * 设置面板:分类页(操作方式 / 键位)+ 打开关闭。
 * radios/getMode/onSelect 管视角方式,sens* 管鼠标灵敏度,其余管键位。
 */
export function createSettings({
  root,
  openBtn,
  closeBtn,
  radios,
  getMode,
  onSelect,
  sensInput,
  sensSaveBtn,
  getSens,
  onSensChange,
  binds,
  onBindsChange,
  keyListEl,
  presetBoxEl,
  resetBtnEl,
  hintEl,
  notify,
  onOpenChange,
}) {
  let listening = null; // 正在等按键的动作 id
  let lastFocus = null; // 打开前的焦点,关闭时还回去

  const say = (text) => {
    if (notify) notify(text);
  };

  const tabs = Array.from(root.querySelectorAll('.settings-tab'));
  const panels = tabs.map((t) => document.getElementById(t.getAttribute('aria-controls')));
  const presetBtns = presetBoxEl ? Array.from(presetBoxEl.querySelectorAll('[data-preset]')) : [];

  // ---------- 分类页 ----------
  function selectTab(tab) {
    tabs.forEach((t, i) => {
      const on = t === tab;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      if (panels[i]) panels[i].hidden = !on;
    });
    cancelListen();
  }

  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => selectTab(tab));
    // 左右方向键在分类页之间切换(ARIA tablist 的常规操作)
    tab.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      const step = e.key === 'ArrowRight' ? 1 : -1;
      const next = tabs[(i + step + tabs.length) % tabs.length];
      selectTab(next);
      next.focus();
    });
  });

  // ---------- 视角方式 ----------
  function syncRadios() {
    const mode = getMode();
    radios.forEach((r) => {
      r.checked = r.value === mode;
    });
  }

  radios.forEach((r) => {
    r.addEventListener('change', () => {
      if (!r.checked) return;
      onSelect(r.value);
    });
  });

  // ---------- 鼠标灵敏度 ----------
  // 直接填数字再保存:滑杆对精细数值不好使,而且拖动过程里会一直写存储
  function setSensInvalid(on) {
    if (!sensInput) return;
    sensInput.classList.toggle('is-invalid', on);
    sensInput.setAttribute('aria-invalid', String(on));
  }

  function syncSens() {
    if (!sensInput) return;
    sensInput.value = getSens().toFixed(2);
    setSensInvalid(false);
  }

  /** 读输入框的倍率,超出 0.30 – 2.00 或不是数字时返回 null */
  function readSensInput() {
    const raw = String(sensInput.value || '')
      .trim()
      .replace(',', '.');
    const v = Number(raw);
    if (!raw || !isFinite(v) || v < 0.3 || v > 2) return null;
    return Math.round(v * 100) / 100;
  }

  function saveSens() {
    if (!sensInput) return;
    const v = readSensInput();
    if (v === null) {
      setSensInvalid(true);
      sensInput.focus();
      sensInput.select();
      say('灵敏度请填 0.30 – 2.00 之间的数字');
      return;
    }
    sensInput.value = v.toFixed(2);
    setSensInvalid(false);
    onSensChange(v, true);
    say('鼠标灵敏度:' + v.toFixed(2) + '×');
  }

  if (sensInput) {
    sensInput.addEventListener('input', () => setSensInvalid(false));
    sensInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        saveSens();
        return;
      }
      // Esc 只在输入框里撤销这次编辑,不关整个面板
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        syncSens();
        sensInput.blur();
      }
    });
    // 失焦时只把能读的值整理成两位小数;读不出来就先留着,下次同步时再回退,
    // 这样点「保存」前的那次 blur 不会把用户的输入悄悄换掉
    sensInput.addEventListener('blur', () => {
      const v = readSensInput();
      if (v === null) return;
      sensInput.value = v.toFixed(2);
      setSensInvalid(false);
    });
  }
  if (sensSaveBtn) sensSaveBtn.addEventListener('click', saveSens);

  // ---------- 键位 ----------
  function renderKeys() {
    if (!keyListEl) return;
    keyListEl.textContent = '';
    KEY_ACTIONS.forEach((a) => {
      const row = document.createElement('li');
      row.className = 'keybind-row';

      const name = document.createElement('span');
      name.className = 'keybind-name';
      name.textContent = a.label;

      const cap = document.createElement('button');
      cap.className = 'keybind-cap';
      cap.type = 'button';
      cap.dataset.action = a.id;
      cap.textContent = listening === a.id ? '按键…' : codeToLabel(binds[a.id]);
      cap.title = '点击后按下新键即可改绑';
      cap.setAttribute('aria-label', a.label + ' 当前 ' + codeToLabel(binds[a.id]) + ',点击改绑');
      if (listening === a.id) cap.classList.add('is-listening');
      cap.addEventListener('click', () => startListen(a.id));

      row.append(name, cap);
      keyListEl.append(row);
    });
    syncPresets();
  }

  function syncPresets() {
    const active = matchPreset(binds);
    presetBtns.forEach((btn) => {
      const on = btn.dataset.preset === active;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-pressed', String(on));
    });
  }

  function startListen(actionId) {
    listening = actionId;
    if (hintEl) hintEl.textContent = HINT_LISTEN;
    renderKeys();
    const cap = keyListEl.querySelector('.keybind-cap[data-action="' + actionId + '"]');
    if (cap) cap.focus();
  }

  function cancelListen() {
    if (!listening) return;
    listening = null;
    if (hintEl) hintEl.textContent = HINT_IDLE;
    renderKeys();
  }

  /** 改键期间吃掉所有按键:先于主循环的 window keydown 触发,不会再触发游戏操作 */
  function onCaptureKey(e) {
    if (!listening) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.code === 'Escape') {
      cancelListen();
      say('已取消改键');
      return;
    }
    if (!isBindableCode(e.code)) {
      say('这个键不能绑定,换一个试试');
      return;
    }

    const actionId = listening;
    listening = null;
    const swapped = bindCode(binds, actionId, e.code);
    writeBinds(binds);
    if (hintEl) hintEl.textContent = HINT_IDLE;
    renderKeys();
    if (onBindsChange) onBindsChange(binds);

    const actionName = KEY_ACTIONS.find((a) => a.id === actionId).label;
    const label = codeToLabel(e.code);
    if (swapped) {
      const other = KEY_ACTIONS.find((a) => a.id === swapped).label;
      say(
        '「' +
          actionName +
          '」改为 ' +
          label +
          ',' +
          other +
          ' 自动接走 ' +
          codeToLabel(binds[swapped]),
      );
    } else {
      say('「' + actionName + '」改为 ' + label);
    }
  }
  window.addEventListener('keydown', onCaptureKey, true);

  presetBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const preset = MOVE_PRESETS.find((p) => p.id === btn.dataset.preset);
      if (!preset) return;
      listening = null;
      if (hintEl) hintEl.textContent = HINT_IDLE;
      applyPreset(binds, preset);
      writeBinds(binds);
      renderKeys();
      if (onBindsChange) onBindsChange(binds);
      say('移动方案:' + preset.name + ' · ' + preset.desc);
    });
  });

  if (resetBtnEl) {
    resetBtnEl.addEventListener('click', () => {
      const defs = defaultBinds();
      listening = null;
      if (hintEl) hintEl.textContent = HINT_IDLE;
      Object.keys(defs).forEach((id) => {
        binds[id] = defs[id];
      });
      writeBinds(binds);
      renderKeys();
      if (onBindsChange) onBindsChange(binds);
      say('键位已恢复默认');
    });
  }

  // ---------- 打开 / 关闭 ----------
  function sync() {
    syncRadios();
    syncSens();
    renderKeys();
  }

  function isOpen() {
    return !root.hidden;
  }

  function open() {
    lastFocus = document.activeElement;
    sync();
    root.hidden = false;
    if (tabs[0]) tabs[0].focus();
    if (onOpenChange) onOpenChange(true);
  }

  function close() {
    if (root.hidden) return;
    cancelListen();
    root.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
    if (onOpenChange) onOpenChange(false);
  }

  function toggle() {
    if (isOpen()) {
      close();
      return;
    }
    open();
  }

  openBtn.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  // 点遮罩空白处关闭,点面板内部不关闭
  root.addEventListener('pointerdown', (e) => {
    if (e.target === root) close();
  });

  sync();
  if (hintEl) hintEl.textContent = HINT_IDLE;

  return { open, close, toggle, isOpen, refresh: renderKeys };
}
