/* ════════════════════════════════════════════════════════════
   main.js — 滚动叙事总编排
   loader → hero → manifesto → decrypt → features → wrapped
   → privacy → stack → cta，一条时间轴讲完整个故事。
   ════════════════════════════════════════════════════════════ */
import { createStage } from "./particles.js";

const { gsap } = window;
gsap.registerPlugin(ScrollTrigger, ScrollToPlugin, SplitText, ScrambleTextPlugin, CustomEase, DrawSVGPlugin);

CustomEase.create("silk", "0.45,0.05,0.55,0.95");
CustomEase.create("flow", "0.33,0,0.2,1");
CustomEase.create("cine", "0.25,0.1,0.25,1");

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const TOUCH = matchMedia("(hover: none)").matches;
const SCRAMBLE_CN = "解密留痕数据档案01ABCDEF#<>/";
const $ = (s, c = document) => c.querySelector(s);
const $$ = (s, c = document) => [...c.querySelectorAll(s)];

/* ─────────────────────────── 十六进制字符墙 ─────────────────────────── */

class HexWall {
  constructor(canvas, { dim = 0.34 } = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext("2d");
    this.dim = dim;
    this.hexset = "0123456789ABCDEF";
    this.cnset = "周五晚上老地方见带上照片我都存着呢哈哈哈红包已领取晚安好梦明天见谢谢你一直都在刚落地就这么定了";
    this.reveal = 0;      // 0-1 扫描进度
    this.alpha = 1;       // 整体透明度
    this.last = 0;
    this.resize();
    addEventListener("resize", () => this.resize());
  }
  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 1.6);
    const { clientWidth: w, clientHeight: h } = this.cv;
    this.cv.width = w * dpr;
    this.cv.height = h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.cw = 19; this.ch = 24;
    this.cols = Math.ceil(w / this.cw);
    this.rows = Math.ceil(h / this.ch) + 1;
    this.cells = [];
    for (let i = 0; i < this.cols * this.rows; i++) {
      this.cells.push({
        ch: this.hexset[(Math.random() * 16) | 0],
        cn: this.cnset[(Math.random() * this.cnset.length) | 0],
        fl: Math.random(),                      // 闪烁相位
        th: Math.random() * 0.18 - 0.09,        // 解锁阈值抖动
      });
    }
    this.w = w; this.h = h;
  }
  draw(t) {
    if (this.alpha <= 0.01) { if (!this._cleared) { this.ctx.clearRect(0, 0, this.w, this.h); this._cleared = true; } return; }
    this._cleared = false;
    if (t - this.last < 1 / 22) return; // ~22fps 足矣
    this.last = t;
    const { ctx } = this;
    ctx.clearRect(0, 0, this.w, this.h);
    ctx.font = "13px 'JetBrains Mono', monospace";
    ctx.textBaseline = "top";
    const scanY = this.reveal * (this.rows + 2) - 1;
    for (let r = 0; r < this.rows; r++) {
      for (let c = 0; c < this.cols; c++) {
        const cell = this.cells[r * this.cols + c];
        const flick = 0.55 + 0.45 * Math.sin(t * (1.5 + cell.fl * 2.5) + cell.fl * 40);
        const unlocked = r + cell.th * this.rows < scanY;
        if ((t * (0.4 + cell.fl)) % 3 < 0.05) cell.ch = this.hexset[(Math.random() * 16) | 0];
        if (unlocked) {
          const heat = Math.max(0, 1 - (scanY - r) * 0.12);
          const rr = Math.round(61 + heat * 194), gg = Math.round(242 + heat * 13), bb = Math.round(141 + heat * 114);
          ctx.fillStyle = `rgba(${rr},${gg},${bb},${(0.16 + heat * 0.7) * this.alpha})`;
          ctx.fillText(cell.cn, c * this.cw, r * this.ch);
        } else {
          ctx.fillStyle = `rgba(90,140,110,${(0.05 + 0.13 * flick * cell.fl) * this.dim * 2.6 * this.alpha})`;
          ctx.fillText(cell.ch, c * this.cw, r * this.ch);
        }
      }
    }
  }
}

/* ─────────────────────────── 密文之墙（act 02） ─────────────────────────── */

// 加密锋线自上而下推进：锋线以上结成密文，指针经过能擦开巴掌大一块看见原文
class CipherWall {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext("2d");
    this.hexset = "0123456789ABCDEF";
    this.cnset = "多年的对话照片红包与告别都锁在一个你打不开的加密数据库里到了跟我说一声刚落地还是老地方见保重晚安明天回家生日快乐路上小心哈哈哈我都存着呢谢谢你一直都在";
    this.fill = 0;    // 锋线位置 0-1
    this.alpha = 0;
    this.crack = 0;   // 裂缝张开 0-1
    this.unlock = 0;  // 解密波自中线向两侧推开 0-1（第三幕用）
    this.visible = true; // 幕不在视口里就别画
    this.mx = -1e4; this.my = -1e4;
    this.last = 0;
    addEventListener("pointermove", (e) => {
      const r = this.cv.getBoundingClientRect();
      this.mx = e.clientX - r.left; this.my = e.clientY - r.top;
    }, { passive: true });
    addEventListener("resize", () => this.resize());
    this.resize();
  }
  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 1.6);
    const w = this.cv.clientWidth, h = this.cv.clientHeight;
    if (!w || !h) return;
    this.cv.width = w * dpr; this.cv.height = h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = w; this.h = h;
    this.cw = 19; this.ch = 24;
    this.cols = Math.ceil(w / this.cw);
    this.rows = Math.ceil(h / this.ch) + 1;
    this.cells = [];
    for (let i = 0; i < this.cols * this.rows; i++) {
      this.cells.push({
        hex: this.hexset[(Math.random() * 16) | 0],
        cn: this.cnset[(Math.random() * this.cnset.length) | 0],
        fl: Math.random(),
        th: Math.random() * 0.13 - 0.065, // 锋线锯齿，避免一条直线推过来
      });
    }
  }
  draw(t) {
    if (!this.cells) return;
    const { ctx } = this;
    if (this.alpha <= 0.005 || !this.visible) {
      if (!this._cleared) { ctx.clearRect(0, 0, this.w, this.h); this._cleared = true; }
      return;
    }
    if (t - this.last < 1 / 24) return;
    this.last = t; this._cleared = false;
    ctx.clearRect(0, 0, this.w, this.h);
    ctx.font = "13px 'JetBrains Mono', monospace";
    ctx.textBaseline = "top";
    const front = this.fill * (this.h + 80) - 40;
    const cx = this.w * 0.5;
    const half = this.crack * this.w * 0.23;
    for (let r = 0; r < this.rows; r++) {
      const y = r * this.ch;
      for (let c = 0; c < this.cols; c++) {
        const cell = this.cells[r * this.cols + c];
        const edge = front + cell.th * this.h;
        if (y > edge) continue;                       // 锋线还没到，仍是原文的地盘
        const x = c * this.cw;
        const dx = Math.abs(x + this.cw * 0.5 - cx);
        const uHalf = this.unlock * this.w * 0.62;
        const unlocked = uHalf > 0 && dx < uHalf + cell.th * 90; // 波前带锯齿
        if (half > 0 && dx < half && !unlocked) continue;        // 裂缝（解密波填进来之前）
        const near = Math.max(0, 1 - (edge - y) / 95); // 锋线附近最亮
        const d = Math.hypot(x - this.mx, y - this.my);
        const erase = d < 125 ? 1 - d / 125 : 0;
        if ((t * (0.4 + cell.fl)) % 3 < 0.05) cell.hex = this.hexset[(Math.random() * 16) | 0];
        if (unlocked) { // 已解开：变回原文，波前一线最亮
          const wave = Math.max(0, 1 - (uHalf - dx) / 120);
          ctx.fillStyle = `rgba(${(176 + 79 * wave) | 0},255,${(202 + 53 * wave) | 0},${((0.32 + wave * 0.62) * this.alpha).toFixed(3)})`;
          ctx.fillText(cell.cn, x, y);
        } else if (erase > 0.34) {
          ctx.fillStyle = `rgba(${(200 + 55 * erase) | 0},255,${(220 + 35 * erase) | 0},${((0.3 + erase * 0.6) * this.alpha).toFixed(3)})`;
          ctx.fillText(cell.cn, x, y);
        } else {
          const flick = 0.55 + 0.45 * Math.sin(t * (1.5 + cell.fl * 2.5) + cell.fl * 40);
          const a = (0.1 + 0.2 * flick * cell.fl + near * 0.7) * this.alpha;
          ctx.fillStyle = `rgba(${(61 + near * 160) | 0},242,${(141 + near * 95) | 0},${a.toFixed(3)})`;
          ctx.fillText(cell.hex, x, y);
        }
      }
    }
    if (half > 2 && this.unlock * this.w * 0.62 < half) { // 裂缝的两道亮边（解密波盖过就撤）
      const g = ctx.createLinearGradient(0, 0, 0, this.h);
      g.addColorStop(0, "rgba(61,242,141,0)");
      g.addColorStop(0.5, `rgba(61,242,141,${(0.9 * this.alpha).toFixed(3)})`);
      g.addColorStop(1, "rgba(61,242,141,0)");
      ctx.fillStyle = g;
      ctx.fillRect(cx - half - 1, 0, 2, this.h);
      ctx.fillRect(cx + half - 1, 0, 2, this.h);
    }
  }
}

/* ─────────────────────────── 启动 ─────────────────────────── */

let stage, lenis, hexwall, loaderWall, river, mwall, isoTick = null;
let scrollProgress = 0;
let __vt = 0;

function boot() {
  stage = createStage($("#gl"));

  lenis = new Lenis({ lerp: 0.09, wheelMultiplier: 1.0, smoothWheel: !REDUCED });
  lenis.stop();
  lenis.on("scroll", ScrollTrigger.update);
  lenis.on("scroll", (e) => {
    scrollProgress = e.limit ? e.animatedScroll / e.limit : 0;
    stage.setScroll(scrollProgress);
  });
  gsap.ticker.add((time) => {
    __vt = Math.max(__vt, time);
    lenis.raf(time * 1000);
    stage.update(time);
    if (loaderWall) loaderWall.draw(time);
    if (hexwall) hexwall.draw(time);
    if (mwall) mwall.draw(time);
    if (river) river.draw(time);
    if (isoTick) isoTick();
  });
  gsap.ticker.lagSmoothing(0);

  // 自动化/调试：手动推进帧（应对宿主环境 rAF 节流）
  window.__go = (y, frames = 150) => {
    lenis.resize();
    lenis.scrollTo(y, { immediate: true, force: true });
    return window.__step(frames);
  };
  window.__step = (frames = 60) => {
    __vt = Math.max(__vt, gsap.ticker.time);
    for (let i = 0; i < frames; i++) {
      __vt += 1 / 60;
      gsap.updateRoot(__vt);
      lenis.raf(__vt * 1000);
      stage.update(__vt);
      if (hexwall) hexwall.draw(__vt);
      if (mwall) mwall.draw(__vt);
      if (river) river.draw(__vt);
      if (isoTick) isoTick();
    }
    return Math.round(scrollY);
  };

  setupCursor();
  setupMagnetic();
  fetchStars();

  const minWait = new Promise((res) => setTimeout(res, REDUCED ? 300 : 2400));
  runLoader();
  Promise.all([document.fonts.ready, minWait]).then(() => {
    buildHero();
    buildManifesto();
    buildDecrypt();
    buildFeatures();
    buildWrapped();
    buildMachine();
    buildCTA();
    buildRail();
    exitLoader();
    addEventListener("load", () => ScrollTrigger.refresh());
  });
}

/* ─────────────────────────── 预加载解密序列 ─────────────────────────── */

function runLoader() {
  loaderWall = new HexWall($("#loader-hex"), { dim: 0.16 });
  const keyEl = $("#loader-key");
  const HEXC = "0123456789ABCDEF";
  const target = Array.from({ length: 64 }, () => HEXC[(Math.random() * 16) | 0]).join("");
  if (REDUCED) { keyEl.innerHTML = "<b>" + target + "</b>"; return; }

  const num = $("#loader-num");
  const fill = $("#loader-fill");
  const status = $("#loader-status");
  const steps = [
    "locating db_storage …",
    "scanning memory pages …",
    "aligning key pattern …",
    "verifying against message_0.db …",
    "key locked · decrypting …",
  ];
  const st = { v: 0 };
  gsap.to(st, {
    v: 100, duration: 2.7, ease: "expo.inOut",
    onUpdate() {
      if (!loaderWall) return;
      const resolved = Math.floor((st.v / 100) * 64);
      let tail = "";
      for (let i = resolved; i < 64; i++) tail += HEXC[(Math.random() * 16) | 0];
      keyEl.innerHTML = "<b>" + target.slice(0, resolved) + "</b>" + tail;
      num.textContent = String(Math.round(st.v)).padStart(3, "0");
      fill.style.width = st.v + "%";
      loaderWall.reveal = st.v / 100;
      const i = Math.min(steps.length - 1, Math.floor((st.v / 100) * steps.length));
      if (status.textContent !== steps[i]) status.textContent = steps[i];
    },
  });
}

function exitLoader() {
  const loader = $("#loader");
  document.body.classList.remove("is-loading");
  if (REDUCED) {
    loader.remove(); loaderWall = null; lenis.start();
    stage.setOpacity(0.5, 0.5); stage.setAmp(0.25, 0.5);
    return;
  }
  const tl = gsap.timeline();
  tl.call(() => { $("#loader-status").textContent = "✓ key accepted — welcome home"; })
    .fromTo("#loader-key", { filter: "brightness(2.6)" }, { filter: "brightness(1)", duration: 0.5, ease: "power2.out" }, 0)
    .to(".loader__center, .loader__corner, #loader-hex", { opacity: 0, y: -26, duration: 0.55, ease: "flow", stagger: 0.03 }, "+=0.32")
    .add("wipe")
    .to(".loader__panel.top", { scaleY: 0, transformOrigin: "top", duration: 1.05, ease: "cine" }, "wipe")
    .to(".loader__panel.bottom", { scaleY: 0, transformOrigin: "bottom", duration: 1.05, ease: "cine" }, "wipe")
    .add(() => { loader.remove(); loaderWall = null; lenis.start(); })
    .add(heroIntro(), "wipe-=0.15");
}

/* ─────────────────────────── act 01 · hero ─────────────────────────── */

/* ---------- 开屏解密装置：巨字以密文入场，光刃扫过逐字解开 ---------- */

const HEXC = "0123456789ABCDEF";
let heroChars = [], heroScan = null, heroTitle = null;

function heroSplit() {
  heroTitle = $(".hero__title");
  heroScan = $(".hero__decrypt");
  heroChars = $$(".hero__title .ht-mask").flatMap((m) => new SplitText(m, { type: "chars" }).chars);
  const box = heroTitle.getBoundingClientRect();
  heroChars.forEach((c) => {
    c.dataset.plain = c.textContent;
    // 阈值取字符在标题块内的横向位置 —— 光刃是空间上的扫过，两行会自然交错解开
    const r = c.getBoundingClientRect();
    c._t = box.width ? (r.left + r.width / 2 - box.left) / box.width : Math.random();
    c._state = -1;
  });
  heroReveal(-1);
}

// q = 光刃前缘的归一化位置（<0 全密文，>1 全明文）
function heroReveal(q) {
  for (const c of heroChars) {
    if (q >= c._t) {
      if (c._state !== 1) {
        c._state = 1;
        c.textContent = c.dataset.plain;
        c.classList.remove("is-cipher", "is-solved");
        void c.offsetWidth;                 // 强制回流以重启定格动画
        c.classList.add("hc", "is-solved");
      }
    } else {
      if (c._state !== 0) {
        c._state = 0;
        c.classList.remove("is-solved");
        c.classList.add("hc", "is-cipher");
        c.textContent = HEXC[(Math.random() * 16) | 0]; // 立刻碎掉，别等下一次随机抖动
      }
      if (Math.random() < 0.28) c.textContent = HEXC[(Math.random() * 16) | 0];
    }
  }
}

function buildHero() {
  gsap.set(".nav", { yPercent: -140, opacity: 0 });
  gsap.set(".rail", { opacity: 0 });
  gsap.set(".hero__sub", { opacity: 0 });
  gsap.set(".hero .ht-mask", { yPercent: 118 });
  gsap.set(".hero__vert", { clipPath: "inset(0 0 100% 0)" });
  gsap.set(".hero__coord", { opacity: 0, y: -14 });
  gsap.set(".hero__orb", { scale: 0.4, opacity: 0 });
  gsap.set(".hero__gh", { opacity: 0, y: 14 });
  gsap.set(".hero__plat", { opacity: 0, y: 14 });
  gsap.set(".hero__ticker", { yPercent: 110 });

  if (REDUCED) {
    gsap.set([".nav", ".rail", ".hero__sub", ".hero .ht-mask", ".hero__vert", ".hero__coord", ".hero__orb", ".hero__gh", ".hero__plat", ".hero__ticker"], { clearProps: "all" });
    return;
  }

  heroSplit();

  // 底部数据流
  gsap.to("#hero-ticker", { xPercent: -50, repeat: -1, duration: 30, ease: "none" });

  // 滚动离场：两行标题反向撕开
  gsap.to(".hero__title", {
    yPercent: -26, opacity: 0, ease: "none",
    scrollTrigger: { trigger: "#hero", start: "top top", end: "78% top", scrub: 0.6 },
  });
  gsap.to(".ht-line--1 .ht-mask", {
    xPercent: -9, ease: "none",
    scrollTrigger: { trigger: "#hero", start: "top top", end: "bottom top", scrub: 0.6 },
  });
  gsap.to(".ht-line--2 .ht-mask", {
    xPercent: 9, ease: "none",
    scrollTrigger: { trigger: "#hero", start: "top top", end: "bottom top", scrub: 0.6 },
  });
  gsap.to([".hero__sub", ".hero__cta", ".hero__coord", ".hero__vert", ".hero__ticker"], {
    opacity: 0, ease: "none",
    scrollTrigger: { trigger: "#hero", start: "6% top", end: "52% top", scrub: 0.6 },
  });
}

function heroIntro() {
  if (REDUCED) return gsap.timeline();
  stage.setOpacity(0.9, 2.2);

  const SCAN_AT = 1.5, SCAN_DUR = 1.45;
  const hc1 = $("#hc-1");
  const dec = { p: 0 };
  const decUpdate = () => {
    const W = heroTitle.offsetWidth || 1;
    const q = -0.12 + dec.p * 1.24;
    heroScan.style.transform = `translateX(${(q * W).toFixed(1)}px)`;
    heroReveal(q);
    hc1.textContent = "DECRYPT — " + (gsap.utils.clamp(0, 1, dec.p) * 100).toFixed(1) + "% · SCANNING";
  };

  const tl = gsap.timeline({ defaults: { ease: "flow" } });
  tl.to(".nav", { yPercent: 0, opacity: 1, duration: 0.9 }, 0.15)
    .to(".rail", { opacity: 1, duration: 0.8 }, 0.4)
    .to(".hero__vert", { clipPath: "inset(0 0 0% 0)", duration: 1.1, ease: "silk" }, 0.3)
    .to(".ht-line--1 .ht-mask", { yPercent: 0, duration: 1.15, ease: "cine" }, 0.36)
    .to(".ht-line--2 .ht-mask", { yPercent: 0, duration: 1.3, ease: "cine" }, 0.52)
    .to(".hero__coord", { opacity: 1, y: 0, duration: 0.8 }, 0.9)
    .to(".hero__sub", {
      opacity: 1, duration: 0.01,
      onComplete: () => gsap.to("#hero-scramble", {
        scrambleText: { text: "解密 · 浏览 · 搜索 · 导出 · 年度总结 —— 全部离线完成", chars: SCRAMBLE_CN, speed: 0.6 },
        duration: 1.6,
      }),
    }, 1.0)
    .to(".hero__orb", { scale: 1, opacity: 1, duration: 1.1, ease: "back.out(1.7)" }, 1.05)
    .to(".hero__gh", { opacity: 1, y: 0, duration: 0.7 }, 1.25)
    .to(".hero__plat", { opacity: 1, y: 0, duration: 0.7 }, 1.38)
    .to(".hero__ticker", { yPercent: 0, duration: 0.9, ease: "cine" }, 1.15)

    // ── 解密序列：密文抖动 → 光刃横扫逐字定格 → 粒子自散乱聚拢
    .call(() => hc1.classList.add("is-live"), [], 0.9)
    .to({}, { duration: SCAN_AT - 0.9, onUpdate: decUpdate }, 0.9)
    .set(heroScan, { opacity: 1 }, SCAN_AT)
    .call(() => {
      stage.setAmp(0.55, 0.01);
      gsap.fromTo(stage.uniforms.uAmp, { value: 3.4 }, { value: 0.55, duration: SCAN_DUR + 1.1, ease: "expo.out", overwrite: true });
    }, [], SCAN_AT)
    .to(dec, { p: 1, duration: SCAN_DUR, ease: "power1.inOut", onUpdate: decUpdate }, SCAN_AT)
    .to(heroScan, { opacity: 0, duration: 0.45 }, SCAN_AT + SCAN_DUR - 0.15)
    .call(() => {
      stage.pulse(1.7);
      hc1.classList.remove("is-live");
      gsap.to(hc1, {
        duration: 0.9,
        scrambleText: { text: "DB — AES-256 · SQLCIPHER COMPAT", chars: HEXC + " ·—", speed: 0.8 },
      });
      $$(".hero .ht-line").forEach((l) => (l.style.overflow = "visible")); // 交还霓虹辉光的外溢空间
      // 向下滚动时反向再加密：先解开的最后碎回去
      ScrollTrigger.create({
        trigger: "#hero", start: "top top", end: "42% top", scrub: 0.5,
        onUpdate(self) { heroReveal(1.12 - self.progress * 1.3); },
      });
    }, [], SCAN_AT + SCAN_DUR);
  return tl;
}

/* ─────────────────────────── act 02 · manifesto ─────────────────────────── */

/* 碎片一律用产品同款微信组件（.wc-row / .wc-avatar / .wc-bubble / .wc-voice /
   .wc-img / .wc-redpacket），与解密幕聊天窗同源，不另造简化气泡 */
const WC_VOICE_SVG = '<svg class="wc-voice-ic" viewBox="0 0 32 32" fill="currentColor"><path d="M10.3 11.7l-1.8 1.8c.7.7 1.1 1.6 1.1 2.5s-.4 1.9-1.1 2.5l1.8 1.8c1.1-1.1 1.8-2.6 1.8-4.3s-.7-3.2-1.8-4.3z"/><path class="voice-wave-2" d="M15.2 6.7l-1.8 1.8c1.9 1.9 3 4.5 3 7.3s-1.2 5.4-3 7.3l1.8 1.8c2.3-2.3 3.8-5.5 3.8-9.1s-1.5-6.8-3.8-9.1z"/><path class="voice-wave-3" d="M20.1 1.8l-1.8 1.8c3.1 3.2 5 7.5 5 12.3s-1.9 9.1-5 12.3l1.8 1.8c3.6-3.6 5.9-8.5 5.9-14s-2.2-10.4-5.9-14z"/></svg>';
const WC_IMG_SVG = '<div class="wc-img"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M3 17l5-5 4 4 3.5-3.5L21 18"/></svg></div>';
const WC_RP = '<div class="wc-redpacket"><div class="wc-rp-main"><span class="wc-rp-ic">🧧</span><div><b>恭喜发财，大吉大利</b><i>领取红包</i></div></div><div class="wc-rp-foot">微信红包</div></div>';

const MF_L = ["到了跟我说一声", "路上小心", "生日快乐！", "保重。", "我都存着呢", "记得吃饭", "那天的照片我还留着", "有空常联系", "早点睡", "在吗", "谢谢你一直都在", "嗯", "好的", "收到", "哈哈哈哈哈", "明天见", "注意身体", "这几年谢谢你，真的", "晚安", "想你了", "别太累了", "我先睡了"];
const MF_R = ["刚落地，还是老地方见", "妈，我明天回家", "好", "晚安", "马上到", "我到家了", "哈哈哈", "知道了", "这就出发", "别等我了先睡", "下周回来看你", "谢谢", "嗯嗯", "好想你们", "放心吧", "在忙，回头说", "收到啦", "都挺好的"];
const MF_SHORT = ["嗯", "好", "在", "好的", "收到", "晚安", "哈哈", "谢谢", "嗯嗯", "好呀", "在的", "明天见", "早", "行", "好累", "😂", "👍", "❤️"];
const HEXP = "0123456789ABCDEF";
const rnd = (n) => (Math.random() * n) | 0;
const hexStr = (n) => Array.from({ length: n }, () => HEXP[rnd(16)] + HEXP[rnd(16)]).join(" ");

// 一条真实微信消息（组件与解密幕聊天窗同源）。风暴里不带头像，与年度总结那版一致
function mfItem(short) {
  const r = short ? 1 : Math.random();
  const side = Math.random() < 0.5 ? "l" : "r";
  if (r < 0.03) return { html: WC_RP, w: 186, h: 62, hex: hexStr(3) };
  if (r < 0.085) return { html: WC_IMG_SVG, w: 96, h: 68, hex: hexStr(2) };
  if (r < 0.16) return { html: '<div class="wc-bubble wc-bubble--' + side + ' wc-voice">' + WC_VOICE_SVG + "<span>" + (2 + rnd(48)) + '″</span></div>', w: 88, h: 34, hex: hexStr(1) };
  const pool = short ? MF_SHORT : (side === "l" ? MF_L : MF_R);
  const t = pool[rnd(pool.length)];
  // 与年度总结 bubbleSizeForText 同款估算：中文 1 单位、西文 0.56
  const chars = Array.from(t);
  const raw = chars.reduce((a, ch) => a + (/[^\x00-\xff]/.test(ch) ? 13 : 8.5), 0);
  const units = chars.reduce((a, ch) => a + (/[^\x00-\xff]/.test(ch) ? 1 : 0.56), 0);
  const minW = units >= 26 ? 182 : units >= 14 ? 122 : 74;
  const w = Math.round(Math.min(300, Math.max(minW, raw + 22)));
  const lines = Math.max(1, Math.ceil(raw / Math.max(1, w - 22)));
  return {
    html: '<div class="wc-bubble wc-bubble--' + side + '">' + t + "</div>",
    w, h: Math.max(32, lines * 19 + 16), hex: hexStr(Math.min(4, Math.max(1, (units / 4) | 0))),
  };
}

/* 消息风暴（取自年度总结的 storm）：网格装箱把真实消息一条条铺满整屏，
   优先填空网格、填不下才允许最多三层叠放。这里改成滚动驱动 —— 手指往下滚，消息越涌越快。 */
function buildMFrags(host) {
  host.innerHTML = "";
  const vw = innerWidth || 1440, vh = innerHeight || 900;
  const CELL = 30, MAXL = 5;
  const cols = Math.ceil(vw / CELL), rows = Math.ceil(vh / CELL);
  const grid = new Map();
  const boxes = [];
  const key = (cx, cy) => cx * 4096 + cy;

  const hit = (a, b, m) => !(a.x - m > b.x + b.w || a.x + a.w + m < b.x || a.y - m > b.y + b.h || a.y + a.h + m < b.y);
  function canPlace(box, margin, overlap) {
    if (box.x < 0 || box.y < 0 || box.x + box.w > vw || box.y + box.h > vh) return false;
    const c0 = Math.floor(box.x / CELL) - 1, c1 = Math.floor((box.x + box.w) / CELL) + 1;
    const r0 = Math.floor(box.y / CELL) - 1, r1 = Math.floor((box.y + box.h) / CELL) + 1;
    for (let cx = c0; cx <= c1; cx++) {
      for (let cy = r0; cy <= r1; cy++) {
        const arr = grid.get(key(cx, cy));
        if (!arr) continue;
        if (!overlap) { for (const i of arr) if (hit(box, boxes[i], margin)) return false; }
        else if (arr.length >= MAXL) return false;
      }
    }
    return true;
  }
  function addGrid(i, box) {
    const c0 = Math.floor(box.x / CELL), c1 = Math.floor((box.x + box.w) / CELL);
    const r0 = Math.floor(box.y / CELL), r1 = Math.floor((box.y + box.h) / CELL);
    for (let cx = c0; cx <= c1; cx++) for (let cy = r0; cy <= r1; cy++) {
      const k = key(cx, cy);
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push(i);
    }
  }
  function emptyCells(avoid) {
    const out = [];
    for (let cy = 0; cy < rows; cy++) for (let cx = 0; cx < cols; cx++) {
      if (grid.has(key(cx, cy))) continue;
      if (avoid) {
        const x = cx * CELL, y = cy * CELL;
        if (x + CELL > avoid.x && x < avoid.x + avoid.w && y + CELL > avoid.y && y < avoid.y + avoid.h) continue;
      }
      out.push([cx, cy]);
    }
    return out;
  }
  function place(w, h, avoid) {
    const emp = emptyCells(avoid);
    for (let t = 0; t < Math.min(emp.length, 26); t++) {
      const [cx, cy] = emp[(Math.random() * emp.length) | 0];
      for (const box of [
        { x: Math.round(cx * CELL + (Math.random() - 0.3) * CELL * 0.5), y: Math.round(cy * CELL + (Math.random() - 0.3) * CELL * 0.5), w, h },
        { x: cx * CELL, y: cy * CELL, w, h },
      ]) {
        box.x = Math.max(0, Math.min(box.x, vw - w));
        box.y = Math.max(0, Math.min(box.y, vh - h));
        if (avoid && hit(box, avoid, 4)) continue;
        if (canPlace(box, 1, false)) return box;
      }
    }
    for (let i = 0; i < 60; i++) {                       // 兜底：允许叠层，制造层次
      const box = { x: ((Math.random() * (vw - w)) | 0), y: ((Math.random() * (vh - h)) | 0), w, h };
      if (avoid && hit(box, avoid, 4)) continue;
      if (canPlace(box, -8, true)) return box;
    }
    return null;
  }

  // 补缝：专门拿最短的消息往剩下的空网格里塞，铺到几乎不留缝
  function placeGap(w, h, avoid) {
    const emp = emptyCells(avoid);
    for (let i = 0; i < Math.min(70, emp.length); i++) {
      const [cx, cy] = emp[(Math.random() * emp.length) | 0];
      const box = {
        x: Math.max(0, Math.min(Math.round(cx * CELL + (CELL - w) / 2), vw - w)),
        y: Math.max(0, Math.min(Math.round(cy * CELL + (CELL - h) / 2), vh - h)),
        w, h,
      };
      if (avoid && hit(box, avoid, 4)) continue;
      if (canPlace(box, -4, true)) return box;
    }
    return null;
  }
  function coverage() {
    let c = 0;
    for (let cy = 0; cy < rows; cy++) for (let cx = 0; cx < cols; cx++) if (grid.has(key(cx, cy))) c++;
    return c / (cols * rows);
  }

  // 与年度总结同量级：area/1900
  const MAX = Math.max(260, Math.min(1150, Math.round((vw * vh) / 1900)));
  // 第一轮避开标题所在的横带（不能让消息压住大字），后半程解禁——标题说完就被消息一起淹掉
  const th = document.querySelector(".m-line--up");
  const tr = th ? th.getBoundingClientRect() : null;
  const avoid = tr ? { x: 0, y: Math.max(0, tr.top - 10), w: vw, h: tr.height + 20 } : null;
  const out = [];
  const frag = document.createDocumentFragment();
  let fails = 0;
  for (let n = 0; n < MAX; n++) {
    if (n > 60 && n % 24 === 0 && coverage() >= 0.995) break;
    const guard = n < MAX * 0.5 ? avoid : null;
    let it = mfItem(false);
    let box = place(it.w, it.h, guard);
    if (!box) { it = mfItem(true); box = place(it.w, it.h, guard) || placeGap(it.w, it.h, guard); }
    if (!box) { if (++fails > 90) break; continue; }
    fails = 0;
    const i = boxes.length;
    boxes.push(box);
    addGrid(i, box);
    const el = document.createElement("div");
    el.className = "mfrag";
    el.style.cssText = `left:${box.x}px;top:${box.y}px;width:${box.w}px;z-index:${100 + (i % 7)}`;
    el.innerHTML = '<div class="mfrag__real">' + it.html + '</div><i class="mfrag__cipher mono">' + it.hex + "</i>";
    frag.appendChild(el);
    out.push({
      el, real: el.querySelector(".mfrag__real"), cipher: el.querySelector(".mfrag__cipher"),
      yn: (box.y + box.h * 0.5) / vh, jit: (Math.random() - 0.5) * 0.05, st: -1,
    });
  }
  host.appendChild(frag);
  return out;
}

function buildManifesto() {
  const lines = $$("[data-mline]");
  mwall = new CipherWall($("#mwall"));
  mwall.visible = false;
  ScrollTrigger.create({
    trigger: "#manifesto", start: "top bottom", end: "bottom top",
    onToggle: (s) => { mwall.visible = s.isActive; },
  });
  const frags = buildMFrags($("#mfield"));
  if (REDUCED) { $("#mfield").style.display = "none"; return; }

  const cl = gsap.utils.clamp(0, 1);
  const clr = (m) => { m.el.style.opacity = ""; m.el.style.transform = ""; m.real.style.opacity = ""; m.cipher.style.opacity = ""; };
  // 涌来（加速曲线）→ 被锋线逐条吞成乱码。只有正处在吞没带里的那几条逐帧改样式
  function setFrags(p, fill) {
    const N = frags.length;
    const shown = (N * Math.pow(cl(p / 0.46), 1.7)) | 0;
    for (let i = 0; i < N; i++) {
      const m = frags[i];
      if (i >= shown) {
        if (m.st !== 0) { m.st = 0; m.el.classList.remove("is-in"); clr(m); }
        continue;
      }
      const eat = (fill + m.jit - m.yn) / 0.09;
      if (eat <= 0) {
        if (m.st !== 1) { m.st = 1; m.el.classList.add("is-in"); clr(m); }
      } else if (eat >= 1) {
        if (m.st !== 3) { m.st = 3; m.el.classList.add("is-in"); m.el.style.opacity = "0"; }
      } else {
        m.st = 2;
        m.el.classList.add("is-in");
        m.el.style.opacity = (1 - cl((eat - 0.58) / 0.42)).toFixed(3);
        m.el.style.transform = `scale(${(1 - eat * 0.12).toFixed(3)})`;
        m.real.style.opacity = (1 - cl(eat / 0.42)).toFixed(3);
        m.cipher.style.opacity = (eat < 0.42 ? eat / 0.42 : 1 - cl((eat - 0.5) / 0.5)).toFixed(3);
      }
    }
  }
  setFrags(0, -0.06);

  const splits = lines.map((l) => new SplitText(l, { type: "chars" }));
  splits.slice(0, 2).forEach((s) => gsap.set(s.chars, { opacity: 0.08 }));
  gsap.set(lines[1], { opacity: 0 });
  gsap.set(lines[2], { opacity: 0 });

  // 时间轴总长 10 == 进度 0-1，方便和装置的分幕对齐
  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: "#manifesto", pin: true, scrub: 0.7,
      start: "top top", end: "+=280%",
      onUpdate(self) {
        const p = self.progress;
        // 前半屏是消息风暴，后半屏加密锋线自上而下把它整个吞掉
        const fill = -0.06 + cl((p - 0.4) / 0.38) * 1.18;
        mwall.fill = fill;
        mwall.crack = cl((p - 0.82) / 0.18);
        mwall.alpha = cl((p - 0.4) / 0.09) * (1 - mwall.crack * 0.3);
        setFrags(p, fill);
        stage.setAmp(0.55 + p * 0.75, 0.3);
      },
      onEnter: () => stage.setOpacity(0.3, 0.9),      // 粒子退到背景，让消息与密文墙唱主角
      onEnterBack: () => stage.setOpacity(0.3, 0.9),
      onLeave: () => stage.setOpacity(0.75, 0.9),
      onLeaveBack: () => { mwall.alpha = 0; stage.setOpacity(0.9, 0.9); },
    },
  });

  // 第一句在风暴淹到它之前说完，第二句落在密文墙上，第三句落在裂缝里
  tl.to(splits[0].chars, { opacity: 1, stagger: 0.045, duration: 1.1, ease: "none" }, 0.2)
    .to(lines[0], { yPercent: -70, opacity: 0, scale: 0.94, duration: 0.8, ease: "silk" }, 3.1)
    .to(lines[1], { opacity: 1, duration: 0.01 }, 5.0)
    .to(splits[1].chars, { opacity: 1, stagger: 0.045, duration: 1.3, ease: "none" }, 5.0)
    .to(lines[1], { yPercent: -70, opacity: 0, scale: 0.94, duration: 0.8, ease: "silk" }, 8.0)
    .fromTo(lines[2], { opacity: 0, scale: 1.7 }, { opacity: 1, scale: 1, duration: 1.2, ease: "cine" }, 8.6)
    .call(() => stage.pulse(2.1), [], 8.8)
    .to({}, { duration: 0.1 }, 9.9);

  // 调试钩子：不滚动也能把第二幕摆到任意进度（内嵌预览深滚会黑屏）
  window.__mf = (p) => {
    mwall.visible = true;
    const fill = -0.06 + cl((p - 0.4) / 0.38) * 1.18;
    mwall.fill = fill;
    mwall.crack = cl((p - 0.82) / 0.18);
    mwall.alpha = cl((p - 0.4) / 0.09) * (1 - mwall.crack * 0.3);
    setFrags(p, fill);
    tl.progress(p);
    return window.__step(2);
  };
}

/* ─────────────────────────── act 03 · decrypt ─────────────────────────── */

/* 第三幕接住第二幕的墙：中线插进 64 位密钥 → 解密波向两侧推开 → 满屏还原成原文 */
function buildDecrypt() {
  hexwall = new CipherWall($("#hexwall"));
  // 开幕即满墙（承接第二幕），别从黑里淡入，否则两幕之间会闪一段黑
  hexwall.fill = 1.15; hexwall.crack = 1; hexwall.unlock = 0; hexwall.alpha = 1;
  hexwall.visible = false;
  ScrollTrigger.create({
    trigger: "#decrypt", start: "top bottom", end: "bottom top",
    onToggle: (s) => { hexwall.visible = s.isActive; },
  });
  const dbs = $$("#ddbs [data-db]");
  const bubbles = $$("[data-bub]");
  const stepNum = $("#dstep-num");
  const stepFile = $("#dstep-file");
  const dpct = $("#dpct");
  const dtitle = $("#dtitle");
  const dsub = $("#dsub");
  const dkey = $("#dkey");
  const KEY = Array.from({ length: 64 }, () => HEXC[(Math.random() * 16) | 0]).join("");
  const cl = gsap.utils.clamp(0, 1);

  if (REDUCED) { dkey.innerHTML = "<b>" + KEY + "</b>"; return; }

  // 墙被揭开：产品本体自下而上顶出来，不是一张卡片飞进来
  gsap.set("#dchat", { clipPath: "inset(100% 0 0 0)" });
  gsap.set(bubbles, { opacity: 0, scale: 0.55, y: 16 });
  gsap.set([dtitle, dsub], { opacity: 0, y: 22 });
  gsap.set(dbs, { opacity: 0, y: 12 });

  const STEPS = [
    { t: "获取密钥", s: "内存扫描自动定位 64 位数据库密钥", n: "STEP 01 / 03", f: "key_pattern @ WeChat.exe / WeChat.app" },
    { t: "解密数据库", s: "SQLCipher 兼容算法逐页解密，生成永久可读的副本", n: "STEP 02 / 03", f: "sqlcipher · page 4096 · aes-256-cbc" },
    { t: "离线浏览", s: "高仿微信界面，无需登录、永久可读。微信可以卸载，记忆不会", n: "STEP 03 / 03", f: "message_0.db — readonly · forever" },
  ];
  let step = -1;
  function setStep(i) {
    if (i === step) return;
    step = i;
    const S = STEPS[i];
    gsap.to(dtitle, { duration: 0.55, scrambleText: { text: S.t, chars: SCRAMBLE_CN, speed: 0.9 } });
    gsap.to(dsub, { duration: 0.7, scrambleText: { text: S.s, chars: SCRAMBLE_CN, speed: 0.8 } });
    gsap.to(stepNum, { duration: 0.5, scrambleText: { text: S.n, chars: "0123456789/STEP ", speed: 1 } });
    gsap.to(stepFile, { duration: 0.7, scrambleText: { text: S.f, chars: SCRAMBLE_CN, speed: 1 } });
  }

  function dcUpdate(p) {
        // 密钥逐位拼装，锁定后裂缝合上，解密波推开
        const kp = cl(p / 0.26);
        const solved = (kp * 64) | 0;
        let tail = "";
        for (let i = solved; i < 64; i++) tail += HEXC[(Math.random() * 16) | 0];
        dkey.innerHTML = "<b>" + KEY.slice(0, solved) + "</b>" + tail;
        hexwall.crack = 1 - cl((p - 0.26) / 0.06);
        const u = cl((p - 0.32) / 0.4);
        hexwall.unlock = u;
        dpct.textContent = (u * 100).toFixed(1) + "%";
        dbs.forEach((li, i) => li.classList.toggle("on", u > (i + 0.55) / dbs.length));
        setStep(p < 0.29 ? 0 : p < 0.75 ? 1 : 2);
        // 粒子形态状态机（双向安全）
        if (p > 0.04 && p < 0.5) stage.morphTo("key", { duration: 1.5 });
        else if (p >= 0.5) stage.morphTo("bubble", { duration: 1.6 });
        else if (p <= 0.04) stage.morphTo("halo", { duration: 1.4 });
  }

  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: "#decrypt", pin: true, scrub: 0.65,
      start: "top top", end: "+=380%",
      onUpdate(self) { dcUpdate(self.progress); },
      onEnter: () => stage.setOpacity(0.34, 0.9),
      onEnterBack: () => stage.setOpacity(0.34, 0.9),
      onLeave: () => stage.setOpacity(0.75, 0.9),
      onLeaveBack: () => stage.setOpacity(0.3, 0.9),
    },
  });

  // 时间轴总长 10 == 进度 0-1
  tl.to([dtitle, dsub], { opacity: 1, y: 0, duration: 0.5, ease: "flow" }, 0.1)
    .call(() => stage.pulse(2.2), [], 2.8)          // 密钥咬合
    .to(dbs, { opacity: 1, y: 0, stagger: 0.06, duration: 0.4, ease: "flow" }, 2.9)
    .to(dkey, { opacity: 0, duration: 0.4 }, 3.2)   // 钥匙被吞进墙里
    .to("#dchat", { clipPath: "inset(0% 0 0 0)", duration: 1.1, ease: "cine" }, 7.4)
    .to(bubbles, { opacity: 1, scale: 1, y: 0, duration: 0.5, stagger: 0.16, ease: "back.out(2.2)" }, 7.9)
    .to({}, { duration: 0.1 }, 9.9);

  window.__dc = (p) => { hexwall.visible = true; dcUpdate(p); tl.progress(p); return window.__step(2); };
}

/* ─────────────────────────── act 04 · features ─────────────────────────── */

function buildFeatures() {
  const cards = $$("[data-card]");
  const numEl = $("#deck-num");
  const nameEl = $("#deck-name");
  const metaEl = $("#deck-meta");
  const descEl = $("#deck-desc");
  const dots = $$("#deck-dots i");
  const N = cards.length;
  const META = [
    { name: "聊天记录 1:1 复刻", meta: "全消息类型 · 时间轴跳转 · 高仿界面", desc: "文本、图片、视频、语音、表情、引用、合并转发……逐一还原，样式尽可能与微信保持一致。" },
    { name: "实时消息同步", meta: "WCDB 直读 · 侧栏闪电 · 零轮询", desc: "直连微信 4.x 的 WCDB——微信开着，新消息、联系人与朋友圈也会实时流进来。" },
    { name: "修改消息 · 随时恢复", meta: "本地改写 · 一键恢复 · 原库零改动", desc: "本地改写任意一条消息，原文永远可以一键找回。" },
    { name: "朋友圈时光机", meta: "删除仍可见 · 历史背景图 · 缓存可调", desc: "看过的朋友圈本地留存：对方改成三天可见、甚至删除动态，你依然能翻回当年的背景图。" },
    { name: "全文搜索", meta: "毫秒级 · 跨会话 · 类型过滤", desc: "多年记录毫秒级跨会话检索，按联系人、消息类型、时间范围任意过滤，一步跳回现场。" },
    { name: "导出万物", meta: "10 类内容 × 4 种格式 · ZIP", desc: "10 类内容 × HTML / JSON / TXT / Excel，从聊天记录到转账红包、全量归档，连资源打包 ZIP。" },
    { name: "MCP · 接给 AI", meta: "MCP Server · Bearer 鉴权 · 一键接入", desc: "内置 MCP 服务，一键复制接入提示词，让 Claude 或任意 MCP 客户端直接查询你的聊天档案。" },
  ];

  const PEEK = 15; // 旧卡后方每层露出的边条像素
  const riseDist = () => Math.round(innerHeight * 0.72); // 待入场卡在屏下的距离

  // 连续堆叠：d=i-f。d<=0 当前/已过（叠在上方露边条），d>0 待入场（从屏下升起）
  function setStack(f) {
    const rd = riseDist();
    cards.forEach((c, i) => {
      const d = i - f;
      let ty, sc, z, br;
      if (d <= 0) {
        const ad = -d;
        ty = -ad * PEEK;
        sc = 1 - ad * 0.045;
        z = 200 - Math.round(ad * 12);
        br = 1 - Math.min(ad * 0.14, 0.62);
      } else {
        ty = d * rd;
        sc = 1;
        z = 200 - Math.round(d * 12);
        br = 1;
      }
      c.style.transform = `translate(-50%, -50%) translateY(${ty.toFixed(1)}px) scale(${sc.toFixed(3)})`;
      c.style.zIndex = String(z);
      c.style.filter = `brightness(${br.toFixed(3)})`;
    });
  }

  let cur = -1;
  function label(idx, animate) {
    if (idx === cur) return;
    const dir = idx > cur ? 1 : -1;
    cur = idx;
    dots.forEach((dd, i) => dd.classList.toggle("on", i === idx));
    numEl.textContent = String(idx + 1).padStart(2, "0");
    nameEl.textContent = META[idx].name;
    metaEl.textContent = META[idx].meta;
    descEl.textContent = META[idx].desc;
    if (animate) gsap.fromTo(".deck__capmain", { opacity: 0.2, y: dir * 12 }, { opacity: 1, y: 0, duration: 0.5, ease: "flow", overwrite: true });
  }

  setStack(0); label(0, false);
  isoTick = null;
  if (REDUCED) return;

  const pos = { f: 0 };
  gsap.timeline({
    scrollTrigger: {
      trigger: "#features", pin: true, scrub: 0.55,
      start: "top top",
      end: () => "+=" + Math.round(N * innerHeight * 0.72),
      invalidateOnRefresh: true,
      onUpdate(self) {
        pos.f = self.progress * (N - 1);
        setStack(pos.f);
        label(Math.round(pos.f), true);
      },
      onEnter: () => { stage.setOpacity(0.2, 0.8); stage.setAmp(0.3, 0.8); },
      onEnterBack: () => { stage.setOpacity(0.2, 0.8); },
      onLeaveBack: () => { stage.setOpacity(0.9, 0.8); stage.setAmp(0.55, 0.8); },
    },
  });

  gsap.from(".deck__stack", {
    opacity: 0, y: 40, duration: 0.9, ease: "flow",
    scrollTrigger: { trigger: "#features", start: "top 72%" },
  });
}

/* ─────────────────────────── act 05 · wrapped ─────────────────────────── */

function buildWrapped() {
  const slides = $$("#v-slides img");
  const N = slides.length;
  const idxEl = $("#v-idx");
  const ticks = $$("#v-ticks i");
  const scene = $("#viewer");
  let activeIdx = -1;

  // 放映室：固定取景框内定向擦除转场，当前帧被推走、下一帧从右侧扫入
  function setFlow(f) {
    const fc = Math.max(0, Math.min(N - 1, f));
    const c = Math.min(N - 2, Math.floor(fc));
    const t = Math.max(0, Math.min(1, fc - c));
    slides.forEach((img, i) => {
      if (i === c) {
        img.style.opacity = "1"; img.style.zIndex = "1";
        img.style.clipPath = "inset(0 0 0 0)";
        img.style.transform = `translateX(${(-t * 6).toFixed(2)}%) scale(1)`;
        img.style.filter = `brightness(${(1 - t * 0.3).toFixed(3)})`;
      } else if (i === c + 1) {
        img.style.opacity = "1"; img.style.zIndex = "2";
        img.style.clipPath = `inset(0 0 0 ${((1 - t) * 100).toFixed(2)}%)`;
        img.style.transform = `translateX(${((1 - t) * 3.5).toFixed(2)}%) scale(${(1.045 - t * 0.045).toFixed(4)})`;
        img.style.filter = "brightness(1)";
      } else {
        img.style.opacity = "0"; img.style.zIndex = "0";
        img.style.clipPath = i < c ? "inset(0 100% 0 0)" : "inset(0 0 0 100%)";
      }
    });
    const idx = Math.round(fc);
    if (idx !== activeIdx) {
      activeIdx = idx;
      idxEl.textContent = String(idx + 1).padStart(2, "0");
      ticks.forEach((tk, i) => tk.classList.toggle("on", i <= idx));
      gsap.fromTo(idxEl, { yPercent: 14, opacity: 0.4 }, { yPercent: 0, opacity: 1, duration: 0.45, ease: "flow", overwrite: true });
    }
  }
  setFlow(0);

  const flowPos = { f: 0 };
  if (REDUCED) { setFlow(0); return; }

  const introChars = new SplitText(".wrapped__title", { type: "chars" });
  gsap.set(introChars.chars, { opacity: 0, yPercent: 60 });
  gsap.set(".wrapped__stats .wstat", { opacity: 0, y: 44 });
  gsap.set(".wrapped__note", { opacity: 0 });
  gsap.set(scene, { opacity: 0, y: 40, scale: 0.94 });

  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: "#wrapped", pin: true, scrub: 0.7,
      start: "top top", end: "+=430%",
      onEnter: () => { stage.morphTo("year", { duration: 1.7 }); stage.setTint(0x6b4a12, 1.6); stage.setOpacity(0.4, 1); },
      onLeaveBack: () => { stage.morphTo("bubble", { duration: 1.4 }); stage.setTint(0x0b3d24, 1.4); stage.setOpacity(0.9, 1); },
    },
  });

  // 幕次：标题独占 → 标题退场 → 放映室逐帧走片 → 数字收束
  tl.to(introChars.chars, { opacity: 1, yPercent: 0, stagger: 0.03, duration: 0.9, ease: "flow" }, 0)
    .to({}, { duration: 0.45 })
    .to(".wrapped__intro", { yPercent: -46, opacity: 0, scale: 0.92, duration: 0.8, ease: "silk" }, ">")
    .to(scene, { opacity: 1, y: 0, scale: 1, duration: 0.7, ease: "cine" }, "<0.25")
    .to(flowPos, { f: N - 1, duration: 3.8, ease: "none", onUpdate: () => setFlow(flowPos.f) }, ">-0.1")
    .to(scene, { yPercent: -3.5, duration: 0.5, ease: "silk" }, ">")
    .to(".wrapped__stats .wstat", { opacity: 1, y: 0, stagger: 0.14, duration: 0.6, ease: "flow" }, "<")
    .call(runCounters, [], "<")
    .to(".wrapped__note", { opacity: 1, duration: 0.5 }, ">-0.2")
    .to({}, { duration: 0.5 });
}

let countersDone = false;
function runCounters() {
  if (countersDone) return;
  countersDone = true;
  $$("[data-count]").forEach((el) => {
    const target = +el.dataset.count;
    const suffix = el.dataset.suffix || "";
    const o = { v: 0 };
    gsap.to(o, {
      v: target, duration: 2.2, ease: "expo.out",
      onUpdate: () => { el.textContent = Math.round(o.v).toLocaleString("en-US") + suffix; },
    });
  });
  $$("[data-count-time]").forEach((el) => {
    const [hh, mm] = el.dataset.countTime.split(":").map(Number);
    const total = hh * 60 + mm;
    const o = { v: 0 };
    gsap.to(o, {
      v: total, duration: 2.2, ease: "expo.out",
      onUpdate: () => {
        const h = Math.floor(o.v / 60), m = Math.round(o.v % 60);
        el.textContent = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      },
    });
  });
}

/* ─────────────────────────── act 06 · privacy ─────────────────────────── */

/* 第六幕改为滚动叙事：三个动作在本机真的跑一遍，两个读数一路对照 ——
   本机处理飞涨，出网死死钉在 0，最后定格盖章。 */
const MAC_RUNS = [
  {
    name: "解密", gb: 41.6,
    trace: ["db_storage/message/message_0.db", "sqlcipher · page 4096 → plain", "db_storage/contact/contact.db", "db_storage/session/session.db", "sha256 verify · ok", "→ ./decrypted/*.db  (local)"],
  },
  {
    name: "浏览", gb: 12.4,
    trace: ["127.0.0.1:10391 · GET /session/list", "127.0.0.1:10391 · GET /message?page=1", "render 1,284 msgs · cache hit", "wcdb live read · no polling", "→ loopback only  (local)"],
  },
  {
    name: "导出", gb: 27.9,
    trace: ["export/HTML/2024-06.html", "export/JSON/messages.json", "export/XLSX/transfers.xlsx", "zip resources · 3.2 GB", "→ ~/Documents  (local)"],
  },
];

function buildMachine() {
  const zeroEl = $("#mac-zero");
  const passEl = $("#mac-pass");
  const actEl = $("#mac-act");
  const traceEl = $("#mac-trace");
  const localEl = $("#mac-local");
  const outEl = $("#mac-out");
  const guards = $$("[data-guard]");
  const cl = gsap.utils.clamp(0, 1);
  const fmt = (gb) => (gb < 1 ? (gb * 1024).toFixed(0) + " MB" : gb.toFixed(1) + " GB");

  if (REDUCED) { zeroEl.textContent = "0"; actEl.textContent = "解密"; return; }

  const titleSplit = new SplitText(".mac__title", { type: "chars" });
  gsap.set(titleSplit.chars, { opacity: 0, yPercent: 42 });
  gsap.set(guards, { opacity: 0, y: 22 });
  gsap.set([".mac__foot", ".mac__meters", "#mac-run"], { opacity: 0 });
  gsap.set("#mac-hero", { opacity: 0 });
  gsap.set(passEl, { opacity: 0 });

  const TOTAL = MAC_RUNS.reduce((a, r) => a + r.gb, 0);
  let curRun = -1, curLines = -1;

  function setRun(p) {
    // p 0-1 覆盖三个动作
    const f = cl(p) * MAC_RUNS.length;
    const i = Math.min(MAC_RUNS.length - 1, f | 0);
    const inner = f - i;
    const R = MAC_RUNS[i];
    if (i !== curRun) {
      curRun = i; curLines = -1;
      gsap.fromTo(actEl, { opacity: 0.15, yPercent: 26 }, { opacity: 1, yPercent: 0, duration: 0.45, ease: "flow", overwrite: true });
      actEl.textContent = R.name;
    }
    const n = Math.max(1, Math.ceil(inner * R.trace.length));
    if (n !== curLines) {
      curLines = n;
      traceEl.innerHTML = R.trace.slice(0, n).map((t) => "<li>" + t + "</li>").join("");
    }
    // 本机处理累加；出网永远 0
    let done = 0;
    for (let k = 0; k < i; k++) done += MAC_RUNS[k].gb;
    localEl.textContent = fmt(done + R.gb * inner);
    outEl.textContent = "0 B";
  }
  function mcUpdate(p) {
    if (p < 0.2) setRun(0);
    else if (p <= 0.74) setRun((p - 0.2) / 0.54);
    else { localEl.textContent = fmt(TOTAL); outEl.textContent = "0 B"; }
  }
  setRun(0);

  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: "#machine", pin: true, scrub: 0.7,
      start: "top top", end: "+=260%",
      onUpdate(self) { mcUpdate(self.progress); },
      onEnter: () => { stage.morphTo("lock", { duration: 1.7 }); stage.setTint(0x0b3d24, 1.4); stage.setOpacity(0.5, 1); stage.setAmp(0.32, 1); },
      onEnterBack: () => { stage.morphTo("lock", { duration: 1.5 }); stage.setOpacity(0.5, 1); },
      onLeaveBack: () => { stage.morphTo("year", { duration: 1.5 }); stage.setTint(0x6b4a12, 1.4); stage.setOpacity(0.65, 1); },
    },
  });

  // 时间轴总长 10 == 进度 0-1
  tl.to(titleSplit.chars, { opacity: 1, yPercent: 0, stagger: 0.012, duration: 0.5, ease: "flow" }, 0.1)
    .to(["#mac-run", ".mac__meters"], { opacity: 1, duration: 0.5, ease: "flow" }, 1.8)
    .to("#mac-run", { opacity: 0, duration: 0.5, ease: "silk" }, 7.5)
    .to("#mac-hero", { opacity: 1, duration: 0.5 }, 7.7)
    // 大 0：先滚乱数「审计中」→ 砰地定格 + 盖章
    .call(() => {
      gsap.to({}, {
        duration: 0.07, repeat: 16, overwrite: true,
        onRepeat: () => { zeroEl.textContent = ((Math.random() * 640) | 0) + " KB"; },
        onComplete: () => {
          zeroEl.textContent = "0";
          gsap.fromTo(zeroEl, { scale: 1.85 }, { scale: 1, duration: 0.7, ease: "back.out(2.4)" });
          gsap.to(passEl, { opacity: 1, duration: 0.4, delay: 0.15 });
          stage.pulse(1.9);
        },
      });
    }, [], 7.9)
    .to(guards, { opacity: 1, y: 0, stagger: 0.09, duration: 0.5, ease: "flow" }, 8.8)
    .to(".mac__foot", { opacity: 1, duration: 0.5 }, 9.4)
    .to({}, { duration: 0.1 }, 9.9);

  window.__mc = (p) => { mcUpdate(p); tl.progress(p); return window.__step(2); };
}

/* ─────────────────────────── act 07 · stack ─────────────────────────── */

/* ---------- 数据河：整条管线的粒子演算 ---------- */

class DataRiver {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext("2d");
    this.active = false;
    this.flow = 1;
    this.last = 0;
    this.pmx = -1e4; this.pmy = -1e4;
    this.HEX = "0123456789ABCDEF";
    this.CN = "周五晚上老地方见带上照片我都存着呢哈哈红包已领取晚安好梦明天见谢谢你一直都在";
    this.WORDS = ["Python", "FastAPI", "SQLite", "WCDB", "Nuxt 4", "Vue 3", "Electron", "Rust", "PyInstaller", "uv", "GSAP", "Tailwind"];
    this.G = [0.14, 0.36, 0.58, 0.76]; // 四道闸门（x 比例）
    this.flashes = [];
    addEventListener("pointermove", (e) => { this.pmx = e.clientX; this.pmy = e.clientY; }, { passive: true });
    addEventListener("resize", () => this.resize());
    this.resize();
  }
  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 1.6);
    this.W = this.cv.clientWidth; this.H = this.cv.clientHeight;
    this.cv.width = this.W * dpr; this.cv.height = this.H * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.xEnd = this.W - Math.min(170, this.W * 0.16);
    const n = Math.min(320, Math.max(140, Math.floor((this.W * this.H) / 3600)));
    this.parts = Array.from({ length: n }, () => this.spawn(Math.random()));
    this.words = this.WORDS.map((w, i) => ({
      w, t: i / this.WORDS.length, sp: 0.016 + Math.random() * 0.014,
      lane: (Math.random() * 2 - 1) * 0.8, size: 17 + Math.random() * 16,
    }));
    // 闸门标签对齐到画布坐标
    $$(".river-gates span").forEach((s, i) => {
      if (this.G[i] != null) s.style.left = ((this.G[i] * this.xEnd) / this.W) * 100 + "%";
    });
  }
  spawn(t = 0) {
    return {
      t, sp: 0.05 + Math.random() * 0.055,
      y0: Math.random() * 2 - 1, ex: (Math.random() * 3) | 0,
      g: this.HEX[(Math.random() * 16) | 0], stage: 0,
      a: 0.35 + Math.random() * 0.55, s: Math.random() < 0.12 ? 15 : 11 + Math.random() * 3,
    };
  }
  pos(p, time) {
    const { W, H, xEnd } = this;
    const cy = H * 0.5;
    const x = p.t * xEnd;
    const conv = Math.min(1, Math.max(0, p.t / this.G[1]));
    const spread = 1 - (conv * conv * (3 - 2 * conv)) * 0.9;
    let y = cy + p.y0 * H * 0.36 * spread + Math.sin(p.t * 34 + p.y0 * 9 + time * 1.8) * 3;
    if (p.t > this.G[3]) {
      const k = (p.t - this.G[3]) / (1 - this.G[3]);
      const kk = k * k * (3 - 2 * k);
      const ey = cy + (p.ex - 1) * H * 0.31;
      y = y * (1 - kk) + ey * kk;
    }
    return [x, y];
  }
  draw(time) {
    const { ctx, W, H } = this;
    if (!this.active) { if (!this._c) { ctx.clearRect(0, 0, W, H); this._c = 1; } return; }
    if (time - this.last < 1 / 30) return;
    const dt = Math.min(time - this.last, 0.06);
    this.last = time; this._c = 0;
    ctx.clearRect(0, 0, W, H);
    const cy = H * 0.5;
    const rect = this.cv.getBoundingClientRect();
    const mx = this.pmx - rect.left, my = this.pmy - rect.top;

    // 河床辉光
    const grd = ctx.createLinearGradient(0, 0, W, 0);
    grd.addColorStop(0, "rgba(61,242,141,0)");
    grd.addColorStop(0.5, "rgba(61,242,141,0.1)");
    grd.addColorStop(1, "rgba(61,242,141,0)");
    ctx.fillStyle = grd;
    ctx.fillRect(0, cy - 34, W, 68);

    // 底层：技术栈残影漂流
    ctx.textBaseline = "middle";
    for (const wd of this.words) {
      wd.t += wd.sp * dt * this.flow;
      if (wd.t > 1.08) { wd.t = -0.12; wd.lane = (Math.random() * 2 - 1) * 0.8; }
      ctx.font = `900 ${wd.size}px Unbounded, sans-serif`;
      ctx.fillStyle = "rgba(150, 190, 165, 0.075)";
      ctx.fillText(wd.w, wd.t * (W + 260) - 130, cy + wd.lane * H * 0.4);
    }

    // 闸门光幕 + 密钥环
    for (let i = 0; i < this.G.length; i++) {
      const gx = this.G[i] * this.xEnd;
      const gg = ctx.createLinearGradient(0, cy - H * 0.42, 0, cy + H * 0.42);
      gg.addColorStop(0, "rgba(61,242,141,0)");
      gg.addColorStop(0.5, i === 1 ? "rgba(61,242,141,0.5)" : "rgba(61,242,141,0.22)");
      gg.addColorStop(1, "rgba(61,242,141,0)");
      ctx.strokeStyle = gg;
      ctx.lineWidth = i === 1 ? 1.5 : 1;
      ctx.beginPath(); ctx.moveTo(gx, cy - H * 0.42); ctx.lineTo(gx, cy + H * 0.42); ctx.stroke();
      if (i === 1) { // 密钥环：旋转缺口双环
        ctx.strokeStyle = "rgba(61,242,141,0.85)";
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(gx, cy, 26, time * 1.4, time * 1.4 + Math.PI * 1.5); ctx.stroke();
        ctx.strokeStyle = "rgba(61,242,141,0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(gx, cy, 34, -time * 0.9, -time * 0.9 + Math.PI * 1.2); ctx.stroke();
      }
    }

    // 粒子（分层绘制：密文 → 明文 → 出港）
    for (const p of this.parts) {
      p.t += p.sp * dt * this.flow;
      if (p.t > 1) Object.assign(p, this.spawn(0), { sp: p.sp });
      const stage = p.t < this.G[1] ? 0 : p.t < this.G[3] ? 1 : 2;
      if (stage !== p.stage) {
        if (stage === 1) { // 过密钥闸：解密瞬间
          p.g = this.CN[(Math.random() * this.CN.length) | 0];
          const [fx, fy] = this.pos(p, time);
          if (this.flashes.length < 14) this.flashes.push({ x: fx, y: fy, age: 0 });
        }
        p.stage = stage;
      }
      let [x, y] = this.pos(p, time);
      const dxm = x - mx, dym = y - my;
      const md = Math.hypot(dxm, dym);
      if (md < 80) y += (dym / (md + 0.01)) * (80 - md) * 0.5;
      if (stage === 0) {
        ctx.font = `${p.s}px 'JetBrains Mono', monospace`;
        ctx.fillStyle = `rgba(132, 162, 142, ${(p.a * 0.42).toFixed(3)})`;
      } else if (stage === 1) {
        ctx.font = `${p.s + 1}px 'JetBrains Mono', monospace`;
        ctx.fillStyle = `rgba(61, 242, 141, ${(p.a * 0.85).toFixed(3)})`;
      } else {
        const cols = ["61, 242, 141", "234, 255, 242", "255, 194, 75"];
        ctx.font = `${p.s}px 'JetBrains Mono', monospace`;
        ctx.fillStyle = `rgba(${cols[p.ex]}, ${(p.a * 0.8).toFixed(3)})`;
      }
      ctx.fillText(p.g, x, y);
    }

    // 解密闪光
    this.flashes = this.flashes.filter((f) => (f.age += dt) < 0.5);
    for (const f of this.flashes) {
      const k = f.age / 0.5;
      ctx.strokeStyle = `rgba(61, 242, 141, ${(0.55 * (1 - k)).toFixed(3)})`;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(f.x, f.y, 4 + k * 42, 0, Math.PI * 2); ctx.stroke();
    }
  }
}

function buildStack() {
  river = new DataRiver($("#river"));
  if (REDUCED) { river.active = true; river.flow = 0.12; return; }

  ScrollTrigger.create({
    trigger: "#stack", start: "top 92%", end: "bottom 8%",
    onToggle(self) { river.active = self.isActive; },
  });
  ScrollTrigger.create({
    trigger: "#stack", start: "top 60%",
    onEnter: () => { stage.morphTo("halo", { duration: 1.8 }); stage.setOpacity(0.35, 1); },
  });

  gsap.from(".stack__head", {
    opacity: 0, y: 40, duration: 0.9, ease: "flow",
    scrollTrigger: { trigger: "#stack", start: "top 72%" },
  });
  gsap.from(".river-gates span", {
    opacity: 0, y: 14, stagger: 0.1, duration: 0.6, ease: "flow",
    scrollTrigger: { trigger: ".river-wrap", start: "top 78%" },
  });
  gsap.from(".river-exits span", {
    opacity: 0, x: 20, stagger: 0.12, duration: 0.6, ease: "flow",
    scrollTrigger: { trigger: ".river-wrap", start: "top 72%" },
  });
  gsap.from(".stack__hud li", {
    opacity: 0, y: 24, stagger: 0.08, duration: 0.6, ease: "flow",
    scrollTrigger: { trigger: ".stack__hud", start: "top 94%" },
  });
}

/* ─────────────────────────── act 07 · cta（终幕 · 归档落款）─────────────────────────── */

function buildCTA() {
  const gate = $("#cta-gate");

  // 下载闸内的指针光斑
  if (!TOUCH) {
    gate.addEventListener("pointermove", (e) => {
      const r = gate.getBoundingClientRect();
      gate.style.setProperty("--mx", (((e.clientX - r.left) / r.width) * 100).toFixed(1) + "%");
      gate.style.setProperty("--my", (((e.clientY - r.top) / r.height) * 100).toFixed(1) + "%");
    }, { passive: true });
  }
  if (REDUCED) return;

  const chars = new SplitText(".cta__title", { type: "chars" }).chars;
  gsap.set(chars, { opacity: 0, yPercent: 62, rotateX: -62, transformPerspective: 900, transformOrigin: "50% 100%" });
  gsap.set(".cta__slug-t", { opacity: 0 });
  gsap.set(".cta__leader", { clipPath: "inset(0 100% 0 0)" });
  gsap.set(gate, { clipPath: "inset(0 50% 0 50%)" });
  gsap.set(".gate__row", { opacity: 0, y: 26 });
  gsap.set(".ix", { opacity: 0, y: 24 });
  gsap.set(".ix__rule, .cta__colophon-rule", { scaleX: 0 });
  gsap.set(".cta__colophon-row span", { opacity: 0 });

  ScrollTrigger.create({
    trigger: "#cta", start: "top 58%", once: true,
    onEnter: () => {
      const tl = gsap.timeline();
      // 刊头 → 巨字立起 → 闸门自中线拉开 → 索引细线逐条抽出 → 版权落定
      tl.to(".cta__slug-t", { opacity: 1, duration: 0.5, stagger: 0.14 }, 0)
        .to(".cta__leader", { clipPath: "inset(0 0% 0 0)", duration: 0.9, ease: "cine" }, 0.08)
        .to(chars, { opacity: 1, yPercent: 0, rotateX: 0, duration: 0.95, stagger: 0.045, ease: "cine" }, 0.18)
        .to(gate, { clipPath: "inset(0 0% 0 0%)", duration: 1.05, ease: "cine" }, 0.62)
        .to(".gate__row", { opacity: 1, y: 0, duration: 0.75, ease: "flow" }, 0.86)
        .to("#gate-meta", {
          duration: 1.1,
          scrambleText: { text: "LATEST RELEASE · WINDOWS & macOS · OPEN SOURCE", chars: "ABCDEF0123456789·", speed: 0.8 },
        }, 1.0)
        .call(() => stage.pulse(1.9), [], 1.05)
        .set(gate, { clearProps: "clipPath" }, 1.72) // 交还 hover 辉光的外溢空间
        .to(".ix", { opacity: 1, y: 0, stagger: 0.09, duration: 0.6, ease: "flow" }, 1.1)
        .to(".ix__rule", { scaleX: 1, stagger: 0.09, duration: 0.75, ease: "cine" }, 1.14)
        .to(".cta__colophon-rule", { scaleX: 1, duration: 1.1, ease: "cine" }, 1.45)
        .to(".cta__colophon-row span", { opacity: 1, stagger: 0.12, duration: 0.5 }, 1.6);

      stage.morphTo("halo", { duration: 2 });
      stage.setTint(0x0b3d24, 1.6);
      stage.setOpacity(0.9, 1.2);
      stage.setAmp(0.8, 1.5);
    },
  });
}

/* ─────────────────────────── 侧栏 · 章节指示 ─────────────────────────── */

function buildRail() {
  const cur = $("#rail-cur");
  const fill = $("#rail-fill");
  gsap.ticker.add(() => { fill.style.transform = `scaleY(${scrollProgress})`; });
  $$(".act").forEach((act) => {
    // 被 pin 的幕外面套了一层 .pin-spacer，必须拿 spacer 当 trigger，
    // 否则区间塌成一屏，章节号会卡在上一幕不动
    const p = act.parentElement;
    const el = p && p.classList.contains("pin-spacer") ? p : act;
    ScrollTrigger.create({
      trigger: el, start: "top 52%", end: "bottom 52%",
      onToggle(self) {
        if (!self.isActive) return;
        if (window.__cursorAct) window.__cursorAct(act.dataset.act);
        if (cur.textContent !== act.dataset.act) {
          gsap.fromTo(cur, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.4 });
          cur.textContent = act.dataset.act;
        }
      },
    });
  });
}

/* ─────────────────────────── 光标 & 磁吸 ─────────────────────────── */

function setupCursor() {
  if (TOUCH || REDUCED) return;
  const ring = $(".cursor");
  const dot = $(".cursor-dot");
  const addr = $("#cursor-addr");
  gsap.set([ring, dot, addr], { opacity: 0 }); // 首次移动前隐藏，避免卡在左上角
  const rx = gsap.quickTo(ring, "x", { duration: 0.4, ease: "expo.out" });
  const ry = gsap.quickTo(ring, "y", { duration: 0.4, ease: "expo.out" });
  const dx = gsap.quickTo(dot, "x", { duration: 0.08 });
  const dy = gsap.quickTo(dot, "y", { duration: 0.08 });
  const ax = gsap.quickTo(addr, "x", { duration: 0.32, ease: "expo.out" });
  const ay = gsap.quickTo(addr, "y", { duration: 0.32, ease: "expo.out" });
  const hx = (v) => v.toString(16).toUpperCase().padStart(3, "0");
  // 读数随幕切换：每一幕光标都是那一幕正在用的那把「工具」
  const MODES = {
    "01": (x, y) => "0x" + hx(x) + "·" + hx(y),          // 内存扫描
    "02": () => hexStr(3),                                // 密文探针：乱码随手抖
    "03": (x, y) => "KEY 0x" + hx(x) + hx(y),             // 密钥
    "04": (x, y) => "0x" + hx(x) + "·" + hx(y),
    "05": () => "WRAPPED 2025",
    "06": () => "0 B · EGRESS",
    "07": () => "GET LATEST ↓",
  };
  let act = "01";
  window.__cursorAct = (id) => {
    if (!MODES[id] || id === act) return;
    act = id;
    ring.dataset.act = id; addr.dataset.act = id; dot.dataset.act = id;
  };

  let shown = false, lastAddr = "";
  addEventListener("pointermove", (e) => {
    if (!shown) { shown = true; gsap.set([ring, dot, addr], { x: e.clientX, y: e.clientY }); gsap.to([ring, dot, addr], { opacity: 1, duration: 0.3 }); }
    rx(e.clientX); ry(e.clientY); dx(e.clientX); dy(e.clientY); ax(e.clientX); ay(e.clientY);
    const s = MODES[act](e.clientX & ~3, e.clientY & ~3);
    if (s !== lastAddr) { lastAddr = s; addr.textContent = s; }
  }, { passive: true });
  document.addEventListener("pointerover", (e) => {
    const t = e.target.closest("[data-cursor], a, button");
    ring.classList.toggle("is-hover", !!t);
  });
}

function setupMagnetic() {
  if (TOUCH || REDUCED) return;
  $$("[data-magnetic]").forEach((el) => {
    const xTo = gsap.quickTo(el, "x", { duration: 0.9, ease: "elastic.out(1,0.4)" });
    const yTo = gsap.quickTo(el, "y", { duration: 0.9, ease: "elastic.out(1,0.4)" });
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      xTo((e.clientX - r.left - r.width / 2) * 0.34);
      yTo((e.clientY - r.top - r.height / 2) * 0.34);
    });
    el.addEventListener("pointerleave", () => { xTo(0); yTo(0); });
  });
}

/* ─────────────────────────── github stars ─────────────────────────── */

function fetchStars() {
  fetch("https://api.github.com/repos/LifeArchiveProject/WeChatDataAnalysis")
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      if (!d || !d.stargazers_count) return;
      const n = d.stargazers_count;
      $("#gh-stars").textContent = "★ " + (n >= 1000 ? (n / 1000).toFixed(1) + "k" : n);
    })
    .catch(() => {});
}

/* ─────────────────────────── go ─────────────────────────── */

if (document.readyState === "loading") addEventListener("DOMContentLoaded", boot);
else boot();
