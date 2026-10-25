// ============ 角色控制器 ============
// character.glb 里是一个蒙皮网格 + 21 根骨 + 12 个动作(idle / walk / run / jump /
// crouch_idle / crouch_walk / sneak / punch1-4 / block)。这里只做三件事:
//   1) 把键盘鼠标输入翻译成"想往哪走、要不要攻击";
//   2) 按位移速度与战斗状态切换动作(带 crossfade,避免动作硬切);
//   3) 把角色贴回地面、朝行进方向转身。
// 相机不在这里控制:main.js 的 OrbitControls 继续负责视角,本模块只读取相机朝向
// 把 WASD 转成世界方向。
import * as THREE from 'three';
import { createTouchControls } from './touch.js';

const GROUND_Y = 0.03; // 沙地表面高度(Blender 里地面 z≈0.05,导出 +Y up)
const GRAVITY = 18;
const JUMP_SPEED = 5.0;
const TURN_RATE = 12; // 转身角速度(rad/s)

// 各档位速度(m/s):动作是按真实步频做的,速度必须与动作匹配,否则脚下打滑
const SPEED = {
  walk: 1.9,
  run: 4.8,
  crouch: 0.95,
  sneak: 0.62,
  block: 0.55,
};

// 一段连招收招后仍可接下一段的时间窗(秒)
const COMBO_WINDOW = 0.55;

/**
 * 键盘输入:WASD 移动、Shift 奔跑、Space 跳、C 切下蹲、X 静步、
 * 鼠标左键单击出拳(拖动则交给 OrbitControls 转视角)、右键按住格挡。
 */
function createInput(canvas) {
  const keys = new Set();
  const state = {
    punchPressed: false,
    blockHeld: false,
    crouchToggle: 0,
    jumpPressed: false,
  };

  // 触屏摇杆的方向(-1..1);active 为假时退回键盘
  const axes = { x: 0, y: 0, active: false };
  let touchSneak = false;
  let touchRun = false;

  const onKeyDown = (event) => {
    const code = event.code;
    if (code === 'Space' || code.startsWith('Arrow')) {
      event.preventDefault();
    }
    if (keys.has(code)) return;
    keys.add(code);
    if (code === 'Space') state.jumpPressed = true;
    if (code === 'KeyC') state.crouchToggle += 1;
  };
  const onKeyUp = (event) => {
    keys.delete(event.code);
  };

  let downX = 0;
  let downY = 0;
  let downButton = -1;
  let dragged = false;

  const onPointerDown = (event) => {
    downButton = event.button;
    downX = event.clientX;
    downY = event.clientY;
    dragged = false;
    if (event.button === 2) state.blockHeld = true;
  };
  const onPointerMove = (event) => {
    if (downButton < 0) return;
    if (Math.hypot(event.clientX - downX, event.clientY - downY) > 5) dragged = true;
  };
  const onPointerUp = (event) => {
    if (event.button === 0 && !dragged) state.punchPressed = true;
    if (event.button === 2) state.blockHeld = false;
    downButton = -1;
    dragged = false;
  };
  const onContextMenu = (event) => event.preventDefault();
  const onBlur = () => {
    keys.clear();
    state.blockHeld = false;
    downButton = -1;
  };

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  canvas.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('contextmenu', onContextMenu);
  window.addEventListener('blur', onBlur);

  // 触屏设备才会真的挂载,非触屏返回 null
  createTouchControls({
    onMove(x, y) {
      axes.x = x;
      axes.y = y;
      axes.active = Math.hypot(x, y) > 0.12;
      // 摇杆推到底即奔跑,省掉一个按钮
      touchRun = Math.hypot(x, y) > 0.86;
    },
    onPunch() {
      state.punchPressed = true;
    },
    onJump() {
      state.jumpPressed = true;
    },
    onCrouch() {
      state.crouchToggle += 1;
    },
    onBlock(held) {
      state.blockHeld = held;
    },
    onSneak(on) {
      touchSneak = on;
    },
  });

  return {
    state,
    consume() {
      state.punchPressed = false;
      state.jumpPressed = false;
    },
    isDown(code) {
      if (keys.has(code)) return true;
      // 触屏把"静步开关"和"摇杆到底奔跑"映射到同样的按键查询上
      if (code === 'KeyX') return touchSneak;
      if (code === 'ShiftLeft') return touchRun;
      return false;
    },
    axes,
  };
}

/** 动作播放包装:同一时刻只有循环动作在跑,一次性动作用 LoopOnce 抢占 */
function createAnimator(mixer, clips) {
  const actions = new Map();
  for (const clip of clips) {
    const action = mixer.clipAction(clip);
    action.enabled = true;
    actions.set(clip.name, action);
  }

  let current = null;

  function play(name, { loop = true, fade = 0.16, timeScale = 1 } = {}) {
    const next = actions.get(name);
    if (!next) {
      console.error('[viewer] 缺动作', name);
      return null;
    }
    next.timeScale = timeScale;
    next.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, loop ? Infinity : 1);
    next.clampWhenFinished = !loop;
    if (current === next) {
      return next;
    }
    next.reset();
    if (current) {
      next.crossFadeFrom(current, fade, false);
    }
    next.play();
    current = next;
    return next;
  }

  return {
    play,
    actions,
    get current() {
      return current;
    },
  };
}

/**
 * 脚下一块贴地的软阴影。
 * GLB 只带几何不带灯,夕阳仰角又只有 8 度,地面接收的直射分量很小,
 * 单靠投影会把角色"浮"在沙地上;这里补一张固定的暗色贴片,视觉上把人压回地面。
 */
function createContactShadow() {
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createRadialGradient(
    size / 2,
    size / 2,
    size * 0.05,
    size / 2,
    size / 2,
    size / 2,
  );
  gradient.addColorStop(0, 'rgba(0, 0, 0, 0.58)');
  gradient.addColorStop(0.42, 'rgba(0, 0, 0, 0.3)');
  gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;

  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  });
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 2.1), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.renderOrder = 1;
  group.add(mesh);
  return { group, material };
}

/**
 * 创建角色控制器。
 * @param {object} options
 * @param {THREE.Object3D} options.root        glTF 场景根(角色面朝 +Z)
 * @param {Array} options.animations           glTF 动画片段
 * @param {THREE.Camera} options.camera
 * @param {HTMLElement} options.canvas
 * @param {THREE.Vector3} [options.spawn]      出生点
 */
export function createCharacter({ root, animations, camera, canvas, spawn }) {
  const input = createInput(canvas);
  const mixer = new THREE.AnimationMixer(root);
  const animator = createAnimator(mixer, animations);

  const position = spawn ? spawn.clone() : new THREE.Vector3(0, GROUND_Y, 6);
  position.y = GROUND_Y;
  root.position.copy(position);

  const contactShadow = createContactShadow();
  if (root.parent) root.parent.add(contactShadow.group);

  const model = {
    root,
    mixer,
    animator,
    position,
    // 初始背对相机:相机在 +Z 一侧,角色面朝 -Z 看向废墟
    yaw: Math.PI,
    velocityY: 0,
    grounded: true,
    crouched: false,
    mode: 'locomotion',
    punchStage: 0,
    sincePunch: COMBO_WINDOW + 1,
    bufferedPunch: false,
    punchEndsAt: 0,
    speed: 0,
  };
  root.rotation.y = model.yaw;

  const forward = new THREE.Vector3();
  const right = new THREE.Vector3();
  const wish = new THREE.Vector3();
  const UP = new THREE.Vector3(0, 1, 0);

  function readWish() {
    camera.getWorldDirection(forward);
    forward.y = 0;
    if (forward.lengthSq() < 1e-6) forward.set(0, 0, -1);
    forward.normalize();
    // 屏幕右 = forward × up;原来多取了一次反,导致 A/D 与方向相反
    right.crossVectors(forward, UP).normalize();

    wish.set(0, 0, 0);
    if (input.axes.active) {
      // 触屏摇杆:y 向上为正,与"前进"同向
      wish.addScaledVector(forward, input.axes.y).addScaledVector(right, input.axes.x);
    } else {
      if (input.isDown('KeyW') || input.isDown('ArrowUp')) wish.add(forward);
      if (input.isDown('KeyS') || input.isDown('ArrowDown')) wish.sub(forward);
      if (input.isDown('KeyD') || input.isDown('ArrowRight')) wish.add(right);
      if (input.isDown('KeyA') || input.isDown('ArrowLeft')) wish.sub(right);
    }
    const moving = wish.lengthSq() > 1e-6;
    if (moving) wish.normalize();
    return moving;
  }

  function startPunch(stage) {
    model.mode = 'punch';
    model.punchStage = stage;
    model.bufferedPunch = false;
    model.sincePunch = 0;
    const action = animator.play('punch' + stage, { loop: false, fade: 0.1 });
    if (!action) {
      model.mode = 'locomotion';
      return;
    }
    model.punchEndsAt =
      performance.now() + (action.getClip().duration * 1000) / Math.max(action.timeScale, 0.01);
  }

  function punchDone(now) {
    return now >= model.punchEndsAt;
  }

  function update(dt, now) {
    const moving = readWish();
    const events = input.state;

    // —— 下蹲是切换而不是按住:手机上只需要一次点击 ——
    if (events.crouchToggle > 0) {
      model.crouched = !model.crouched;
      events.crouchToggle = 0;
    }

    // —— 跳跃:下蹲与出拳时不能起跳 ——
    if (events.jumpPressed && model.grounded && model.mode !== 'punch' && !model.crouched) {
      model.velocityY = JUMP_SPEED;
      model.grounded = false;
      model.mode = 'jump';
      animator.play('jump', { loop: false, fade: 0.08 });
    }

    // —— 出拳:出拳中再按一次会把下一段排进缓冲,收招时立刻接上 ——
    if (events.punchPressed && !model.crouched) {
      if (model.mode === 'punch') {
        model.bufferedPunch = true;
      } else {
        startPunch(1);
      }
    }

    const blocking =
      events.blockHeld && model.grounded && model.mode !== 'punch' && model.mode !== 'jump';

    // —— 速度档位 ——
    const running = input.isDown('ShiftLeft') || input.isDown('ShiftRight');
    const sneaking = input.isDown('KeyX');
    let speed = 0;
    if (moving) {
      if (model.crouched) speed = SPEED.crouch;
      else if (sneaking) speed = SPEED.sneak;
      else if (running) speed = SPEED.run;
      else speed = SPEED.walk;
      if (blocking) speed = Math.min(speed, SPEED.block);
      if (model.mode === 'punch') speed = 0;
    }

    if (speed > 0) {
      position.addScaledVector(wish, speed * dt);
    }
    model.speed = speed;

    // —— 转身:朝行进方向插值 ——
    if (speed > 0) {
      const targetYaw = Math.atan2(wish.x, wish.z);
      let diff = targetYaw - model.yaw;
      while (diff > Math.PI) diff -= Math.PI * 2;
      while (diff < -Math.PI) diff += Math.PI * 2;
      model.yaw += diff * Math.min(1, TURN_RATE * dt);
    }

    // —— 重力 ——
    if (!model.grounded) {
      model.velocityY -= GRAVITY * dt;
      position.y += model.velocityY * dt;
      if (position.y <= GROUND_Y) {
        position.y = GROUND_Y;
        model.velocityY = 0;
        model.grounded = true;
        if (model.mode === 'jump') {
          model.mode = 'locomotion';
          animator.play('idle', { fade: 0.18 });
        }
      }
    }

    root.position.copy(position);
    root.rotation.y = model.yaw;

    // —— 接触阴影跟着脚走:跳起来时摊大、变淡,落地收回去 ——
    const height = position.y - GROUND_Y;
    const spread = 1 + height * 0.22;
    contactShadow.group.position.set(position.x, GROUND_Y + 0.006, position.z);
    contactShadow.group.rotation.y = model.yaw;
    contactShadow.group.scale.set(spread, 1, spread);
    contactShadow.material.opacity = THREE.MathUtils.clamp(1 - height * 0.4, 0.3, 1);

    // —— 动作选择 ——
    if (model.mode === 'punch') {
      if (punchDone(now)) {
        if (model.bufferedPunch && model.punchStage < 4) {
          startPunch(model.punchStage + 1);
        } else {
          model.punchStage = 0;
          model.mode = 'locomotion';
          model.sincePunch = 0;
        }
      }
    } else if (model.mode === 'jump') {
      // 空中保持 jump 动作,落地由上面的重力分支切回
    } else if (blocking) {
      model.mode = 'block';
      animator.play('block', { fade: 0.12 });
    } else {
      model.mode = 'locomotion';
      if (model.crouched) {
        animator.play(moving ? 'crouch_walk' : 'crouch_idle', { fade: 0.18 });
      } else if (sneaking) {
        animator.play('sneak', { fade: 0.2, timeScale: moving ? 1 : 0.6 });
      } else if (moving) {
        // 步频跟速度走,避免奔跑时变成滑步
        const base = running ? SPEED.run : SPEED.walk;
        animator.play(running ? 'run' : 'walk', {
          fade: 0.16,
          timeScale: THREE.MathUtils.clamp(speed / base, 0.75, 1.35),
        });
      } else {
        animator.play('idle', { fade: 0.2 });
      }
    }

    model.sincePunch += dt;
    mixer.update(dt);
    input.consume();
    return { speed: model.speed, mode: model.mode, yaw: model.yaw };
  }

  animator.play('idle', { fade: 0 });
  return { update, model, animator, input };
}
