// ============ keybinds.js 单测:默认键位 / 预设 / 改绑互换 / 存储回退 ============
// 模块是纯数据层,所有断言都走公开函数;localStorage 用假实现注入,不碰真实浏览器存储。
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  BIND_STORAGE_KEY,
  KEY_ACTIONS,
  MOVE_PRESETS,
  applyPreset,
  bindCode,
  codeToLabel,
  defaultBinds,
  isBindableCode,
  matchPreset,
  mirrorCode,
  readBinds,
  writeBinds,
} from '../scripts/keybinds.js';

/** 造一个只活在这条用例里的 localStorage 假实现 */
function fakeStorage(initial, { failGet = false, failSet = false } = {}) {
  const data = new Map(Object.entries(initial || {}));
  return {
    data,
    getItem: vi.fn((key) => {
      if (failGet) throw new Error('storage disabled');
      return data.has(key) ? data.get(key) : null;
    }),
    setItem: vi.fn((key, value) => {
      if (failSet) throw new Error('storage disabled');
      data.set(key, value);
    }),
  };
}

/** 把内容塞进存储并让 readBinds 读到 */
function storageWith(value) {
  return fakeStorage({ [BIND_STORAGE_KEY]: value });
}

const presetOf = (id) => MOVE_PRESETS.find((p) => p.id === id);

/** 键位表里不允许两个动作抢同一个键 */
function duplicateCodes(binds) {
  const all = Object.values(binds);
  return all.filter((code, i) => all.indexOf(code) !== i);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('默认键位', () => {
  it('每个可改键动作都有默认值,且与 KEY_ACTIONS 一致', () => {
    const binds = defaultBinds();
    expect(Object.keys(binds).sort()).toEqual(KEY_ACTIONS.map((a) => a.id).sort());
    KEY_ACTIONS.forEach((action) => expect(binds[action.id]).toBe(action.def));
  });

  it('每次返回新对象,改一份不影响另一份', () => {
    const first = defaultBinds();
    const second = defaultBinds();
    expect(first).not.toBe(second);
    first.moveForward = 'KeyQ';
    expect(second.moveForward).toBe('KeyW');
    expect(KEY_ACTIONS.find((a) => a.id === 'moveForward').def).toBe('KeyW');
  });

  it('默认键位互不重复', () => {
    expect(duplicateCodes(defaultBinds())).toEqual([]);
  });
});

describe('移动预设', () => {
  it('三套预设都在,id 稳定', () => {
    expect(MOVE_PRESETS.map((p) => p.id)).toEqual(['wasd', 'esdf', 'arrows']);
  });

  it('每套预设套用后完全命中自己', () => {
    MOVE_PRESETS.forEach((preset) => {
      const binds = defaultBinds();
      applyPreset(binds, preset);
      Object.entries(preset.keys).forEach(([id, code]) => expect(binds[id]).toBe(code));
      expect(matchPreset(binds)).toBe(preset.id);
      expect(duplicateCodes(binds)).toEqual([]);
    });
  });

  it('方向键预设只动移动键,交互仍是 E', () => {
    const binds = defaultBinds();
    applyPreset(binds, presetOf('arrows'));
    expect(binds.moveForward).toBe('ArrowUp');
    expect(binds.moveLeft).toBe('ArrowLeft');
    expect(binds.moveBack).toBe('ArrowDown');
    expect(binds.moveRight).toBe('ArrowRight');
    expect(binds.interact).toBe('KeyE');
  });

  it('ESDF 预设把交互键一起挪到 R,不和移动键撞车', () => {
    const binds = defaultBinds();
    applyPreset(binds, presetOf('esdf'));
    expect(binds.interact).toBe('KeyR');
    expect(binds.moveForward).toBe('KeyE');
    expect(duplicateCodes(binds)).toEqual([]);
  });

  it('重复套用同一套预设结果不变', () => {
    const binds = defaultBinds();
    applyPreset(binds, presetOf('esdf'));
    const once = { ...binds };
    applyPreset(binds, presetOf('esdf'));
    expect(binds).toEqual(once);
  });

  it('预设没提到的动作保持原样', () => {
    const binds = defaultBinds();
    binds.settings = 'KeyP';
    applyPreset(binds, presetOf('esdf'));
    expect(binds.settings).toBe('KeyP');
    expect(binds.run).toBe('ShiftLeft');
    expect(binds.lookPause).toBe('AltLeft');
    expect(binds.sound).toBe('KeyM');
  });

  it('三套预设轮流套用后仍无重复键,并能切回 WASD', () => {
    const binds = defaultBinds();
    ['esdf', 'arrows', 'wasd'].forEach((id) => {
      applyPreset(binds, presetOf(id));
      expect(duplicateCodes(binds)).toEqual([]);
    });
    expect(matchPreset(binds)).toBe('wasd');
  });

  it('混搭键位不命中任何预设', () => {
    const binds = defaultBinds();
    binds.moveForward = 'KeyQ';
    expect(matchPreset(binds)).toBeNull();
  });
});

describe('改绑与冲突互换', () => {
  it('撞到别人的键时两者互换,并返回被换掉的动作', () => {
    const binds = defaultBinds();
    const owner = bindCode(binds, 'moveForward', 'KeyS');
    expect(owner).toBe('moveBack');
    expect(binds.moveForward).toBe('KeyS');
    expect(binds.moveBack).toBe('KeyW');
    expect(duplicateCodes(binds)).toEqual([]);
  });

  it('改到空闲键时直接绑上,返回 null', () => {
    const binds = defaultBinds();
    expect(bindCode(binds, 'moveForward', 'KeyQ')).toBeNull();
    expect(binds.moveForward).toBe('KeyQ');
    expect(binds.moveBack).toBe('KeyS');
  });

  it('重绑同一个键不算冲突', () => {
    const binds = defaultBinds();
    expect(bindCode(binds, 'moveForward', 'KeyW')).toBeNull();
    expect(binds.moveForward).toBe('KeyW');
    expect(duplicateCodes(binds)).toEqual([]);
  });

  it('互换后两个动作都还绑着一个键(不会有动作悄悄失效)', () => {
    const binds = defaultBinds();
    bindCode(binds, 'moveForward', 'KeyE');
    expect(binds.moveForward).toBe('KeyE');
    expect(binds.interact).toBe('KeyW');
    expect(duplicateCodes(binds)).toEqual([]);
  });
});

describe('键码校验与键帽标签', () => {
  it('接受字母/数字/方向/修饰/常用标点与功能键', () => {
    [
      'KeyA',
      'Digit0',
      'Numpad9',
      'ArrowUp',
      'ShiftLeft',
      'AltRight',
      'ControlLeft',
      'Space',
      'Enter',
      'Tab',
      'Minus',
      'BracketLeft',
      'Backquote',
      'F12',
    ].forEach((code) => expect(isBindableCode(code)).toBe(true));
  });

  it('拒绝系统键、大小写错误与非字符串', () => {
    ['Escape', 'F13', 'keyA', 'MetaLeft', 'KeyWW', ''].forEach((code) =>
      expect(isBindableCode(code)).toBe(false),
    );
    expect(isBindableCode(null)).toBe(false);
    expect(isBindableCode(undefined)).toBe(false);
    expect(isBindableCode(42)).toBe(false);
  });

  it('左右修饰键互为镜像,普通键没有镜像', () => {
    expect(mirrorCode('ShiftLeft')).toBe('ShiftRight');
    expect(mirrorCode('ShiftRight')).toBe('ShiftLeft');
    expect(mirrorCode('AltLeft')).toBe('AltRight');
    expect(mirrorCode('ControlRight')).toBe('ControlLeft');
    expect(mirrorCode('KeyA')).toBeNull();
    expect(mirrorCode('Escape')).toBeNull();
  });

  it('常见键位有短标签', () => {
    expect(codeToLabel('KeyW')).toBe('W');
    expect(codeToLabel('Digit5')).toBe('5');
    expect(codeToLabel('Numpad7')).toBe('NUM7');
    expect(codeToLabel('ArrowUp')).toBe('↑');
    expect(codeToLabel('ShiftLeft')).toBe('SHIFT');
    expect(codeToLabel('Space')).toBe('SPACE');
    expect(codeToLabel('Backspace')).toBe('BKSP');
    expect(codeToLabel('Semicolon')).toBe(';');
  });

  it('空值给占位符,未知键码转大写兜底', () => {
    expect(codeToLabel(null)).toBe('—');
    expect(codeToLabel('unknownXyz')).toBe('UNKNOWNXYZ');
  });
});

describe('localStorage 读写与回退', () => {
  it('存储为空时就是默认键位', () => {
    vi.stubGlobal('localStorage', fakeStorage());
    expect(readBinds()).toEqual(defaultBinds());
  });

  it('getItem 抛异常时静默回默认(隐私模式)', () => {
    vi.stubGlobal('localStorage', fakeStorage({}, { failGet: true }));
    expect(() => readBinds()).not.toThrow();
    expect(readBinds()).toEqual(defaultBinds());
  });

  it('localStorage 整体不可用时也不炸', () => {
    vi.stubGlobal('localStorage', undefined);
    expect(readBinds()).toEqual(defaultBinds());
  });

  it('存储内容不是合法 JSON 时回默认', () => {
    vi.stubGlobal('localStorage', storageWith('{ 这不是 JSON'));
    expect(readBinds()).toEqual(defaultBinds());
  });

  it('读取合法的自定义键位', () => {
    vi.stubGlobal('localStorage', storageWith(JSON.stringify({ moveForward: 'KeyQ' })));
    const binds = readBinds();
    expect(binds.moveForward).toBe('KeyQ');
    expect(binds.moveBack).toBe('KeyS');
    expect(duplicateCodes(binds)).toEqual([]);
  });

  it('丢弃非法键码与重复键位,缺项补默认值', () => {
    const raw = { moveForward: 'Escape', moveBack: 42, moveLeft: 'KeyA', moveRight: 'KeyA' };
    vi.stubGlobal('localStorage', storageWith(JSON.stringify(raw)));
    const binds = readBinds();
    expect(binds.moveForward).toBe('KeyW');
    expect(binds.moveBack).toBe('KeyS');
    expect(binds.moveLeft).toBe('KeyA');
    expect(binds.moveRight).toBe('KeyD');
    expect(duplicateCodes(binds)).toEqual([]);
  });

  it('只存了一部分时,其余用默认值补齐', () => {
    vi.stubGlobal('localStorage', storageWith(JSON.stringify({ interact: 'KeyR' })));
    expect(readBinds()).toEqual({ ...defaultBinds(), interact: 'KeyR' });
  });

  it('写进去的键位能原样读回来', () => {
    const storage = fakeStorage();
    vi.stubGlobal('localStorage', storage);
    const binds = defaultBinds();
    binds.interact = 'KeyR';
    writeBinds(binds);
    expect(JSON.parse(storage.data.get(BIND_STORAGE_KEY))).toEqual(binds);
    expect(readBinds()).toEqual(binds);
  });

  it('setItem 抛异常时静默忽略,不影响这一局', () => {
    vi.stubGlobal('localStorage', fakeStorage({}, { failSet: true }));
    expect(() => writeBinds(defaultBinds())).not.toThrow();
  });
});
