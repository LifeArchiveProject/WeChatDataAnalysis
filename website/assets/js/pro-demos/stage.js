/* ════════════════════════════════════════════════════════════
   pro-demos / stage.js — 舞台（右）、清单（左）、面板（合体）
   舞台：HUD 刊头 + 640×400 场景屏（等比缩放）+ 说明行 + 进度线。
   自动逐项播放，点清单即切换并从该项继续；页面隐藏/滚离时静默待机。
   gsap 由调用方注入（官网用 window.gsap，应用用 npm 包），本模块不 import 它。
   ════════════════════════════════════════════════════════════ */
import { createKit, SCREEN_W, SCREEN_H, SCRAMBLE_CN, h } from "./kit.js";

const pad2 = (n) => String(n).padStart(2, "0");

export function createProStage(host, {
  gsap, scenes = {}, items = [], reduced = false,
  hold = 0.9, autoplay = true, loopOne = false, start, autostart = true, onChange, onComplete, speed = 1, hudScramble = true,
} = {}) {
  if (!gsap) throw new Error("[pro-demos] createProStage 需要注入 gsap");
  const total = items.length;
  const byKey = Object.fromEntries(items.map((it) => [it.key, it]));

  const el = h("div", "pd-stage");
  // 颜色/字体令牌都挂在 .pd-root 上：只挂舞台（不经 createProPanel）时由舞台自己充当令牌根
  if (!host.closest || !host.closest(".pd-root")) el.classList.add("pd-root");
  el.innerHTML = `
    <div class="pd-hud pd-hud--top">
      <span class="pd-hud__op mono">OP 00 / ${pad2(total)}</span>
      <span class="pd-hud__grp mono"></span>
      <span class="pd-hud__pro mono">PRO · WRITE</span>
    </div>
    <div class="pd-screenbox">
      <div class="pd-screen__bg" aria-hidden="true"></div>
      <div class="pd-screen" aria-hidden="true"></div>
      <i class="pd-corner tl"></i><i class="pd-corner tr"></i><i class="pd-corner bl"></i><i class="pd-corner br"></i>
      <i class="pd-sweep" aria-hidden="true"></i>
      <div class="pd-screen__empty mono">SCENE PENDING</div>
    </div>
    <div class="pd-hud pd-hud--bottom">
      <b class="pd-hud__name"></b>
      <span class="pd-hud__cap"></span>
    </div>
    <div class="pd-progress" aria-hidden="true"><i></i></div>
  `;
  host.appendChild(el);

  const box = el.querySelector(".pd-screenbox");
  const screen = el.querySelector(".pd-screen");
  const sweep = el.querySelector(".pd-sweep");
  const empty = el.querySelector(".pd-screen__empty");
  const bar = el.querySelector(".pd-progress i");
  const hudOp = el.querySelector(".pd-hud__op");
  const hudGrp = el.querySelector(".pd-hud__grp");
  const hudName = el.querySelector(".pd-hud__name");
  const hudCap = el.querySelector(".pd-hud__cap");

  /* ── 等比缩放：场景屏固定 640×400，按容器宽度缩放 ── */
  const fit = () => {
    const w = box.clientWidth || SCREEN_W;
    const s = w / SCREEN_W;
    screen.style.transform = `scale(${s})`;
    box.style.setProperty("--pd-scale", s);
  };
  fit();
  let ro = null;
  if (typeof ResizeObserver !== "undefined") { ro = new ResizeObserver(fit); ro.observe(box); }
  else addEventListener("resize", fit);

  /* ── 播放状态 ── */
  let cur = null;          // 当前项
  let run = null;          // 当前场景的总时间轴（场景 tl + 进度线）
  let pending = null;      // 播完后的延时切换
  let token = 0;           // 切换令牌：异步过渡期间的旧回调作废
  let active = true;       // 在视口内且页面可见
  let userPaused = false;  // 外部显式 pause()
  let destroyed = false;
  let kit = null;

  const indexOf = (key) => items.findIndex((it) => it.key === key);

  const clearScene = () => {
    if (pending) { pending.kill(); pending = null; }
    if (run) { run.kill(); run = null; }
    gsap.killTweensOf(bar);
    screen.replaceChildren();
    kit = null;
  };

  const scheduleNext = () => {
    if (destroyed) return;
    if (onComplete && cur) onComplete(cur);
    if (!autoplay) return;
    if (pending) pending.kill();
    pending = gsap.delayedCall(hold, () => { pending = null; if (!destroyed) next(); });
    if (!active || userPaused) pending.pause();
  };

  const mountScene = (item, my) => {
    clearScene();
    cur = item;
    hudOp.textContent = `OP ${pad2(item.index)} / ${pad2(total)}`;
    hudGrp.textContent = `${item.groupLabel} · ${item.groupTag}`;
    hudCap.textContent = item.caption || "";
    const scene = scenes[item.key];
    if (onChange) onChange(item);

    // 刊头名称乱码落定（与官网执行读数同一手法）
    if (reduced || !hudScramble) hudName.textContent = item.name;
    else {
      const target = Array.from(item.name), o = { p: 0 };
      gsap.to(o, { p: 1, duration: 0.45, ease: "none", onUpdate() {
        const n = Math.floor(o.p * target.length);
        let s = target.slice(0, n).join("");
        for (let i = n; i < target.length; i++) s += SCRAMBLE_CN[(Math.random() * SCRAMBLE_CN.length) | 0];
        hudName.textContent = s;
      }, onComplete() { hudName.textContent = item.name; } });
    }

    // show() 的淡出补间（0.10→0.32s）比这里的 0.30s 晚收尾，不先掐掉会把新场景压回 opacity 0
    gsap.killTweensOf(screen, "opacity");
    // 先杀掉出场淡出补间再置回可见——否则淡出的末帧会在挂载后把新场景压回 opacity 0（多路审片实证）
    gsap.killTweensOf(screen);
    gsap.set(screen, { opacity: 1 });
    gsap.set(bar, { scaleX: 0 });

    if (typeof scene !== "function") {
      empty.style.display = "grid";
      run = gsap.timeline({ paused: true, onComplete: scheduleNext }).to({}, { duration: 2.5 });
      run.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: run.duration(), ease: "none" }, 0);
    } else {
      empty.style.display = "none";
      kit = createKit(gsap, screen, { reduced });
      const tl = gsap.timeline({ paused: true });
      let built = null;
      try { built = scene({ gsap, root: screen, kit, tl, reduced, item }); }
      catch (err) { console.error("[pro-demos] scene failed:", item.key, err); }
      const sceneTl = built && typeof built.play === "function" ? built : tl;
      run = gsap.timeline({ paused: true, onComplete: scheduleNext });
      run.add(sceneTl, 0);
      sceneTl.paused(false);
      const dur = Math.max(sceneTl.duration(), 0.5);
      run.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: dur, ease: "none" }, 0);
    }
    run.timeScale(speed);
    if (active && !userPaused) run.play(0);
  };

  const show = (key, { instant = false } = {}) => {
    const item = byKey[key];
    if (!item || destroyed) return;
    const my = ++token;
    if (pending) { pending.kill(); pending = null; }
    if (instant || reduced || !cur) { mountScene(item, my); return; }
    // 出场：扫描光横扫、旧场景压暗，再装新场景
    if (run) run.pause();
    const out = gsap.timeline();
    out.fromTo(sweep, { xPercent: -100, opacity: 1 }, { xPercent: 100, duration: 0.5, ease: "power2.inOut" }, 0)
      .to(screen, { opacity: 0, duration: 0.2, ease: "power1.in" }, 0.1)
      .set(sweep, { opacity: 0 })
      .call(() => { if (my === token) mountScene(item, my); }, [], 0.34);
  };

  const next = () => {
    if (!cur) return show(items[0]?.key);
    if (loopOne) return show(cur.key, { instant: true });
    const i = indexOf(cur.key);
    show(items[(i + 1) % total].key);
  };
  const prev = () => {
    if (!cur) return show(items[0]?.key);
    const i = indexOf(cur.key);
    show(items[(i - 1 + total) % total].key);
  };

  const syncPause = () => {
    const shouldRun = active && !userPaused && !destroyed;
    if (run) { if (shouldRun) run.play(); else run.pause(); }
    if (pending) { if (shouldRun) pending.play(); else pending.pause(); }
  };

  const onVis = () => { active = !document.hidden && api._inView; syncPause(); };
  document.addEventListener("visibilitychange", onVis);

  const api = {
    el, screen,
    _inView: true,
    get current() { return cur; },
    select(key) { show(key); },
    next, prev,
    start(key) { show(key || start || items[0]?.key, { instant: true }); },
    pause() { userPaused = true; syncPause(); },
    resume() { userPaused = false; syncPause(); },
    // 视口进出：官网用 ScrollTrigger 调用；页面隐藏由本模块自己监听
    setActive(v) { api._inView = !!v; active = !!v && !document.hidden; syncPause(); },
    setSpeed(v) { speed = v; if (run) run.timeScale(v); },
    // 调试/截图：定格到场景第 t 秒
    seek(t) { if (!run) return; userPaused = true; run.pause(); run.seek(Math.min(t, run.duration()), false); },
    duration() { return run ? run.duration() : 0; },
    destroy() {
      destroyed = true; token++;
      clearScene();
      document.removeEventListener("visibilitychange", onVis);
      if (ro) ro.disconnect(); else removeEventListener("resize", fit);
      el.remove();
    },
  };

  if (autostart && total) api.start();
  return api;
}

/* ───────────────────────── 清单（左栏）───────────────────────── */

export function createProList(host, { groups = [], onSelect } = {}) {
  const el = h("nav", "pd-list");
  el.setAttribute("aria-label", "高级功能清单");
  const buttons = new Map();
  for (const g of groups) {
    const block = h("section", "pd-group");
    block.dataset.group = g.key;
    const head = h("p", "pd-group__head mono");
    head.append(h("span", "", g.label), h("i", "", pad2(g.items.length)), h("em", "", g.tag || ""));
    const list = h("div", "pd-group__items");
    for (const it of g.items) {
      const b = h("button", "pd-item mono");
      b.type = "button";
      b.dataset.key = it.key;
      b.dataset.cursor = "hover";
      b.append(h("i", "", pad2(it.index ?? 0)), h("span", "", it.name));
      b.addEventListener("click", () => onSelect && onSelect(it.key));
      list.appendChild(b);
      buttons.set(it.key, b);
    }
    block.append(head, list);
    el.appendChild(block);
  }
  host.appendChild(el);

  let activeKey = null;
  return {
    el,
    setActive(key, { scroll = true } = {}) {
      if (activeKey && buttons.has(activeKey)) { const p = buttons.get(activeKey); p.classList.remove("is-active"); p.removeAttribute("aria-current"); }
      activeKey = key;
      const b = buttons.get(key);
      if (!b) return;
      b.classList.add("is-active");
      b.setAttribute("aria-current", "true");
      if (!scroll) return;
      // 只滚清单自己，绝不牵动页面；用几何差值算位置（多栏 columns 布局下 offsetTop 不可靠）
      if (el.scrollHeight <= el.clientHeight + 1) return;
      const br = b.getBoundingClientRect(), lr = el.getBoundingClientRect();
      const top = br.top - lr.top + el.scrollTop, bottom = top + br.height;
      const vt = el.scrollTop, vb = vt + el.clientHeight;
      if (top < vt + 24) el.scrollTo({ top: Math.max(0, top - 24), behavior: "smooth" });
      else if (bottom > vb - 24) el.scrollTo({ top: bottom - el.clientHeight + 24, behavior: "smooth" });
    },
    destroy() { el.remove(); },
  };
}

/* ───────────────────────── 面板：清单 + 舞台 ───────────────────────── */

export function createProPanel(host, { groups = [], items = [], onChange, ...opts } = {}) {
  const root = h("div", "pd-root");
  const panel = h("div", "pd-panel");
  const listHost = h("div", "pd-panel__list");
  const stageHost = h("div", "pd-panel__stage");
  panel.append(listHost, stageHost);
  root.appendChild(panel);
  host.appendChild(root);

  let stage = null;
  const list = createProList(listHost, { groups, onSelect: (key) => stage && stage.select(key) });
  stage = createProStage(stageHost, {
    ...opts, items,
    onChange: (item) => { list.setActive(item.key); if (onChange) onChange(item); },
  });

  return {
    el: root, list, stage,
    select: (key) => stage.select(key),
    setActive: (v) => stage.setActive(v),
    pause: () => stage.pause(),
    resume: () => stage.resume(),
    destroy() { stage.destroy(); list.destroy(); root.remove(); },
  };
}
