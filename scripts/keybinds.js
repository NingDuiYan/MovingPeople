// ============ 键位绑定:默认值 / 本地存储 / 冲突互换 ============
// 纯数据层,不碰 DOM:设置面板负责渲染,主循环负责读 binds 判断按键。

/** 可自定义的动作;数组顺序就是设置面板里的显示顺序 */
export const KEY_ACTIONS = [
  { id: 'moveForward', label: '前进',     def: 'KeyW' },
  { id: 'moveBack',    label: '后退',     def: 'KeyS' },
  { id: 'moveLeft',    label: '左移',     def: 'KeyA' },
  { id: 'moveRight',   label: '右移',     def: 'KeyD' },
  { id: 'run',         label: '疾跑',     def: 'ShiftLeft' },
  { id: 'interact',    label: '交互',     def: 'KeyE' },
  { id: 'settings',    label: '打开设置', def: 'KeyO' },
  { id: 'lookPause',   label: '自由光标', def: 'AltLeft' },
  { id: 'sound',       label: '音效开关', def: 'KeyM' },
];

/** 移动预设:除了四个移动键,交互键也一并挪开,免得跟 E 撞车 */
export const MOVE_PRESETS = [
  {
    id: 'wasd', name: 'WASD', desc: '左手主键区',
    keys: { moveForward: 'KeyW', moveLeft: 'KeyA', moveBack: 'KeyS', moveRight: 'KeyD', interact: 'KeyE' },
  },
  {
    id: 'esdf', name: 'ESDF', desc: '左手右移一格,交互改到 R',
    keys: { moveForward: 'KeyE', moveLeft: 'KeyS', moveBack: 'KeyD', moveRight: 'KeyF', interact: 'KeyR' },
  },
  {
    id: 'arrows', name: '方向键', desc: '右手方向键',
    keys: { moveForward: 'ArrowUp', moveLeft: 'ArrowLeft', moveBack: 'ArrowDown', moveRight: 'ArrowRight', interact: 'KeyE' },
  },
];

export const BIND_STORAGE_KEY = 'neon-isle:keybinds';

/** 允许绑定的 e.code;不在这里的键位一律拒绝(避免绑上 Escape 之类系统键) */
const VALID_CODE = /^(?:Key[A-Z]|Digit[0-9]|Numpad[0-9]|Arrow(?:Up|Down|Left|Right)|F(?:[1-9]|1[0-2])|Shift(?:Left|Right)|Alt(?:Left|Right)|Control(?:Left|Right)|Space|Enter|Tab|Backspace|CapsLock|Minus|Equal|BracketLeft|BracketRight|Backslash|Semicolon|Quote|Comma|Period|Slash|Backquote)$/;

export function isBindableCode(code) {
  return typeof code === 'string' && VALID_CODE.test(code);
}

/** 左右成对的修饰键:绑一边,另一边也当作同一个键 */
const MIRROR = {
  ShiftLeft: 'ShiftRight', ShiftRight: 'ShiftLeft',
  AltLeft: 'AltRight', AltRight: 'AltLeft',
  ControlLeft: 'ControlRight', ControlRight: 'ControlLeft',
};

/** 返回左右配对的那个键码;不是成对修饰键时返回 null */
export function mirrorCode(code) {
  return MIRROR[code] || null;
}

const LABELS = {
  ArrowUp: '↑', ArrowDown: '↓', ArrowLeft: '←', ArrowRight: '→',
  ShiftLeft: 'SHIFT', ShiftRight: 'SHIFT',
  AltLeft: 'ALT', AltRight: 'ALT',
  ControlLeft: 'CTRL', ControlRight: 'CTRL',
  Space: 'SPACE', Enter: 'ENTER', Tab: 'TAB', Backspace: 'BKSP', CapsLock: 'CAPS',
  Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Backslash: '\\',
  Semicolon: ';', Quote: "'", Comma: ',', Period: '.', Slash: '/', Backquote: '`',
};

/** e.code → 键帽上的短标签 */
export function codeToLabel(code) {
  if (!code) return '—';
  if (LABELS[code]) return LABELS[code];
  if (code.startsWith('Key')) return code.slice(3);
  if (code.startsWith('Digit')) return code.slice(5);
  if (code.startsWith('Numpad')) return 'NUM' + code.slice(6);
  return String(code).toUpperCase();
}

/** 默认键位表(每次返回新对象) */
export function defaultBinds() {
  const out = {};
  KEY_ACTIONS.forEach((a) => { out[a.id] = a.def; });
  return out;
}

/** 把存储里的值并进默认值:非法/重复的键位丢弃,缺项用默认值补齐 */
function normalize(raw) {
  const out = {};
  const used = new Set();
  const defs = defaultBinds();

  // 第一遍:采信合法的自定义键位,同一个键只留给先出现的动作
  KEY_ACTIONS.forEach((a) => {
    const code = raw && raw[a.id];
    if (isBindableCode(code) && !used.has(code)) {
      out[a.id] = code;
      used.add(code);
    }
  });
  // 第二遍:剩下的补默认值;默认键位被占了就找一个还没用上的默认键位
  KEY_ACTIONS.forEach((a) => {
    if (out[a.id]) return;
    let code = defs[a.id];
    if (used.has(code)) {
      const spare = KEY_ACTIONS.map((x) => x.def).find((c) => !used.has(c));
      if (spare) code = spare;
    }
    out[a.id] = code;
    used.add(code);
  });
  return out;
}

/** 读本地键位;存储不可用或内容损坏时退回默认 */
export function readBinds() {
  let raw = null;
  try {
    const text = localStorage.getItem(BIND_STORAGE_KEY);
    if (text) raw = JSON.parse(text);
  } catch (err) {
    raw = null;   // 隐私模式 / 存储被禁用 / JSON 损坏
  }
  return normalize(raw);
}

/** 写本地键位;失败不影响这一局的使用 */
export function writeBinds(binds) {
  try {
    localStorage.setItem(BIND_STORAGE_KEY, JSON.stringify(binds));
  } catch (err) { /* 存储失败忽略 */ }
}

/**
 * 把 code 绑给某个动作。该键已被别的动作占用时两者互换,
 * 这样改键永远不会有"悄悄失效"的动作。binds 原地修改。
 * @returns {string|null} 被换掉的动作 id;没有冲突时返回 null
 */
export function bindCode(binds, actionId, code) {
  const prev = binds[actionId];
  const owner = KEY_ACTIONS.find((a) => a.id !== actionId && binds[a.id] === code);
  binds[actionId] = code;
  if (!owner) return null;
  binds[owner.id] = prev;
  return owner.id;
}

/** 套用移动预设:预设没提到的动作保持原样 */
export function applyPreset(binds, preset) {
  Object.keys(preset.keys).forEach((id) => {
    const code = preset.keys[id];
    if (binds[id] !== code) bindCode(binds, id, code);
  });
}

/** 当前键位命中的预设 id;哪个都不完全命中时返回 null */
export function matchPreset(binds) {
  const hit = MOVE_PRESETS.find((p) => Object.keys(p.keys).every((id) => binds[id] === p.keys[id]));
  return hit ? hit.id : null;
}
