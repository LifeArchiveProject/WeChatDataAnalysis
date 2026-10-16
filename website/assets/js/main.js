/* 官网首页脚本：开场卡面与主按钮光效、全部功能清单、当前区块下划线、按系统分发下载、「最近更新」小链接。
   导航外壳（实色底、手机菜单、浅 / 深主题、GitHub 星数）在 shell.js，权益对比（双卡对照）在 compare.js。不用任何框架与 WebGL；动画交给 CSS。 */
import { ALL } from "./data.js";
import { drawCard, drawMask, CW } from "./card.js";
import { initCompare } from "./compare.js";
import { initShell } from "./shell.js";

const d = document;
const $ = (s, r = d) => r.querySelector(s);
const $$ = (s, r = d) => [...r.querySelectorAll(s)];
const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const navH = () => parseFloat(getComputedStyle(d.documentElement).getPropertyValue("--nav")) || 60;

/* ═════════ 0. 开场卡面（照搬样张甲的 2D 全息卡，card.js 画在 canvas 上） ═════════
   卡上的 77 与 9 取自卡下那行读屏文字（data-pro-total / data-pro-groups），与 sync-site-catalog --check 核对的是同一处。
   画布分辨率 = 卡的布局宽 × 设备像素比 × 1.1（倾斜后近的一侧会放大一点），只在需要更清晰、或手机 / 桌面字号档切换时重画。
   卡上的拉丁字是 Geist（与甲一致）：先等它加载（已预加载，通常几十毫秒；最多等 1.5 秒）再画，卡本来就是画好才淡入，不会先露出一版回退字体。
   万一超时先用回退字体画了，Geist 一到就清掉缓存重画一次。

   交互（样式与各层见 main.css「开场」一节）：
   - 跟手倾斜：鼠标在卡上或卡外一圈（左右各 1/4 卡宽、上下各 3/10 卡高，越往外越弱）移动时，指针那一侧朝人翘起，上下 ±8°、左右 ±10°，并微微放大；
     离开就回正。弹簧跟随（接近临界阻尼，不过冲不抖），rAF 只在弹簧还在走时跑，停稳即停。
     滚轮滚动时浏览器不发 pointermove：滚动时按最后一次的指针位置重算，指针离开感应圈就回正，不会冻在旧姿态上。
   - 光泽、柔影、全息章的视差都由同一组变量推出来（CSS 里 calc），这里每帧只写几项数字。
     倾斜角按卡的布局框算；光斑、光带、条纹的位置（--hx / --hy）则按卡在屏幕上真实的样子（透视倾斜、--cx 平移之后）把指针反投影回卡面，正好落在指针下面。
   - 触摸：按下只记起点，横向拖过 7px 才接管倾斜、松手回正；竖向先动的交给浏览器滚动，卡一动不动。
     卡上 touch-action: pan-y pinch-zoom：竖向滚动与双指缩放照常（浏览器接管时发 pointercancel，卡随之回正）。
   - 空闲：没人碰时每 6–8 秒自己扫过一道彩色光（只动光泽层的一条光带，合成器上跑）；卡滚出视口、页面隐藏时一律停下并回正。
   - 点击：快扫一道光 + 轻轻一按一弹，不跳转。
   - 光泽层的遮罩（深色字挖空）由 card.js 的 drawMask 画，转成图片设成 mask-image；卡淡入后再画，不占首屏的时间。
   - 减少动态效果：不倾斜、不扫光，卡就是静止的海报。卡是装饰（整块 aria-hidden，读屏读下面那行文字），不进 Tab 顺序，所以没有键盘聚焦态。 */
{
  const card = $("#card"), tilt = $(".card__tilt", card), cap = $("figcaption", card), hero = $("#top"), gloss = $$(".card__shine, .card__glint", card);
  const cv = { base: $(".card__cv", card), seal: $(".card__seal", card), patch: $(".card__patch", card) };
  const total = $("[data-pro-total]", cap).textContent.trim(), groups = $("[data-pro-groups]", cap).textContent.trim();
  let key = "", maxS = 0, praf = 0, ready = false, drawn = false, maskT = 0, maskUrl = "";
  const queue = () => { if (!praf) praf = requestAnimationFrame(paint); };
  const paint = () => {
    praf = 0;
    if (!ready) return;
    const w = cv.base.offsetWidth; if (!w) return;
    const S = Math.min(1, Math.ceil(w * Math.min(devicePixelRatio || 1, 3) * 1.1 / CW * 20) / 20);
    const sub = innerWidth <= 640 ? 60 : 44; // 手机上卡只有 300 多像素宽：「9 组 · 注册送 1 天试用」放大一档，不让它缩到 9px 以下
    if (S <= maxS && key.endsWith(`|${sub}`)) return;
    maxS = Math.max(S, maxS); key = `${maxS}|${sub}`;
    try { drawCard(cv, maxS, { total, groups, sub }); tilt.classList.add("is-drawn"); } catch (e) { return; /* 画不出就留白 */ }
    clearTimeout(maskT); maskT = setTimeout(() => mask(maxS, sub), 700); // 遮罩不急：卡淡入完再画
    if (!drawn) { drawn = true; schedule(2600); } // 淡入后不久先自己扫一道光，提示它能动
  };
  /* 光泽遮罩：分辨率取底版的一半（遮罩放大后边缘自然柔一点，也省内存）；转成 blob 图片，旧的那张随即释放 */
  function mask(S, sub) {
    const c = d.createElement("canvas");
    try { drawMask(c, Math.max(.2, S / 2), { total, groups, sub }); } catch (e) { return; }
    if (!c.toBlob) return;
    c.toBlob((b) => {
      c.width = c.height = 0;
      if (!b || !URL.createObjectURL) return;
      const u = URL.createObjectURL(b), v = `url("${u}")`;
      for (const el of gloss) { el.style.setProperty("-webkit-mask-image", v); el.style.setProperty("mask-image", v); }
      if (maskUrl) URL.revokeObjectURL(maskUrl);
      maskUrl = u;
    });
  }
  const geist = d.fonts ? Promise.all([d.fonts.load("700 100px Geist"), d.fonts.load("600 100px Geist")]).then(() => d.fonts.check("700 100px Geist")) : Promise.resolve(false);
  Promise.race([geist.catch(() => false), new Promise((r) => setTimeout(() => r(null), 1500))]).then((ok) => {
    ready = true; queue();
    if (ok === null) geist.then((has) => { if (has) { maxS = 0; key = ""; queue(); } }, () => {});
  });
  // 不在模块求值时同步画（约 20ms）：ResizeObserver 首次回调在首帧之后，下一帧再画，文字先出来，卡随后淡入
  new ResizeObserver(queue).observe(cv.base);

  /* ── 弹簧：k 刚度、c 阻尼（倾斜、悬起、光泽位置接近临界阻尼；pop 是点击回弹，欠阻尼） ── */
  const RX = 8, RY = 10;
  const sp = { rx: [170, 25], ry: [170, 25], lift: [120, 21], hx: [240, 30], hy: [240, 30], pop: [520, 13] };
  const M = Object.fromEntries(Object.entries(sp).map(([k, [kk, c]]) => [k, { k: kk, c, x: 0, v: 0, t: 0 }])); // x 当前值、v 速度、t 目标
  M.hx.x = M.hx.t = M.hy.x = M.hy.t = .5;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  let raf = 0, last = 0, engaged = false, touchId = null, tdrag = false, tx0 = 0, ty0 = 0, geo = null, inView = true, sweepT = 0, anim = null;
  let px = 0, py = 0, hasPtr = false; // 鼠标最后一次在开场里的位置（滚轮滚动时用它重算）
  const ok = () => !reduce.matches && inView && !d.hidden && drawn;

  /* 卡的姿态矩阵：main.css 里 transform 串中跟姿态有关的那段（两个跟手旋转 + 甲的固定倾斜 + 缩放），DOMMatrix 的旋转与 CSS rotate3d 同一约定 */
  const pose = (rx, ry, s) => new DOMMatrix().rotateAxisAngleSelf(1, 0, 0, rx).rotateAxisAngleSelf(0, 1, 0, ry)
    .rotateAxisAngleSelf(1, 0, 0, 9).rotateAxisAngleSelf(0, 1, 0, -19).rotateAxisAngleSelf(0, 0, 1, -2.6).scaleSelf(s, s);
  const scaleOf = (lift, pop) => 1 + lift * .014 - pop * .03;
  /* 卡的布局框（未倾斜的那个，倾斜不改它，不会自激）与姿态前面那段矩阵（translateX(--cx) 与透视，跟姿态无关）= 现在的矩阵 × 现在姿态的逆。
     只在滚动 / 改尺寸后重新量 */
  const measure = () => {
    const r = card.getBoundingClientRect(), g = { l: r.left + tilt.offsetLeft, t: r.top + tilt.offsetTop, w: tilt.offsetWidth, h: tilt.offsetHeight, pre: null };
    try {
      const v = (n) => parseFloat(tilt.style.getPropertyValue(n)) || 0;
      g.pre = new DOMMatrix(getComputedStyle(tilt).transform).multiply(pose(v("--rx"), v("--ry"), scaleOf(v("--lift"), v("--pop"))).inverse());
    } catch (e) { /* 拿不到矩阵就按布局框换算 */ }
    return g;
  };
  addEventListener("scroll", () => { geo = null; if (hasPtr && !tdrag && ok()) track(); }, { passive: true });
  addEventListener("resize", () => { geo = null; });

  /* 屏幕上的点 → 卡面坐标（0…1）：按给定姿态的矩阵反投影回卡面所在的平面。
     卡面上的点 (x, y, 0)（相对变换原点 = 卡中心）投到屏幕是 ((m11 x + m21 y + m41), (m12 x + m22 y + m42)) / (m14 x + m24 y + m44)，解这个 2×2 线性方程 */
  function face(g, X, Y, rx, ry, s) {
    if (!g.pre) return [(X - g.l) / g.w, (Y - g.t) / g.h];
    const m = g.pre.multiply(pose(rx, ry, s)), ox = g.w / 2, oy = g.h / 2, a = X - g.l - ox, b = Y - g.t - oy;
    const A = m.m11 - a * m.m14, B = m.m21 - a * m.m24, C = a * m.m44 - m.m41;
    const D = m.m12 - b * m.m14, E = m.m22 - b * m.m24, F = b * m.m44 - m.m42;
    const det = A * E - B * D;
    return det ? [((C * E - B * F) / det + ox) / g.w, ((A * F - C * D) / det + oy) / g.h] : [.5, .5];
  }
  /* 指针 → 目标姿态。nx / ny 以卡的半宽 / 半高为单位；卡外一圈渐弱（smoothstep），出了这一圈目标就是回正，从文字那边移过来不会一下子跳。触摸不渐弱。
     光泽位置按目标姿态反投影（弹簧停稳时姿态就是目标姿态，光斑正落在指针下） */
  function aim(x, y, touch) {
    const g = geo || (geo = measure());
    const nx = (x - g.l - g.w / 2) / (g.w / 2), ny = (y - g.t - g.h / 2) / (g.h / 2);
    let f = touch ? 1 : clamp(1 - Math.max((Math.abs(nx) - 1) * 2, (Math.abs(ny) - 1) / .6), 0, 1);
    f = f * f * (3 - 2 * f);
    const cx = clamp(nx, -1, 1), cy = clamp(ny, -1, 1);
    M.rx.t = cy * RX * f; M.ry.t = -cx * RY * f; M.lift.t = f;
    const [u, v] = face(g, x, y, M.rx.t, M.ry.t, scaleOf(f, 0));
    M.hx.t = clamp(u, 0, 1); M.hy.t = clamp(v, 0, 1);
    return f > 0;
  }
  function track() { const on = aim(px, py, false); if (on || engaged) { engaged = on; kick(); } }
  function release() { engaged = false; M.rx.t = M.ry.t = M.lift.t = 0; kick(); }

  function write() {
    const st = tilt.style, m = Math.min(1, Math.hypot(M.rx.x / RX, M.ry.x / RY));
    st.setProperty("--rx", M.rx.x.toFixed(3));
    st.setProperty("--ry", M.ry.x.toFixed(3));
    st.setProperty("--lift", M.lift.x.toFixed(4));
    st.setProperty("--pop", M.pop.x.toFixed(4));
    st.setProperty("--hx", M.hx.x.toFixed(4));
    st.setProperty("--hy", M.hy.x.toFixed(4));
    st.setProperty("--hb", (M.hx.x + (M.hy.x - .5) * .255).toFixed(4)); // 斜 22° 的光带穿过指针：tan22° × 卡高 / 卡宽 ≈ .255
    st.setProperty("--hi", clamp(M.lift.x * .3 + m * .7, 0, 1).toFixed(4)); // 倾斜越大光泽越亮
  }
  function step(now) {
    raf = 0;
    const dt = Math.min(.05, last ? (now - last) / 1000 : 1 / 60); last = now;
    let moving = false;
    for (const s of Object.values(M)) {
      for (let n = Math.ceil(dt / .008), h = dt / n; n-- > 0;) { s.v += (s.k * (s.t - s.x) - s.c * s.v) * h; s.x += s.v * h; }
      if (Math.abs(s.t - s.x) > 1e-3 || Math.abs(s.v) > 1e-2) moving = true; else { s.x = s.t; s.v = 0; }
    }
    write();
    if (moving) { raf = requestAnimationFrame(step); return; }
    last = 0;
    if (!engaged) card.classList.remove("is-live"); // 回正停稳：光泽层收起，卡面就是原来那张 canvas
  }
  function kick() { if (!raf) { card.classList.add("is-live"); last = 0; raf = requestAnimationFrame(step); } }

  /* 一切停下并回正（滚出视口、页面隐藏、切到减少动态效果） */
  function rest() {
    clearTimeout(sweepT); sweepT = 0;
    if (anim) { anim.cancel(); anim = null; }
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    engaged = tdrag = false; touchId = null; last = 0;
    for (const s of Object.values(M)) { s.x = s.t = s.v = 0; }
    M.hx.x = M.hx.t = M.hy.x = M.hy.t = .5;
    ["--rx", "--ry", "--lift", "--pop", "--hx", "--hy", "--hb", "--hi"].forEach((p) => tilt.style.removeProperty(p));
    card.classList.remove("is-live", "is-sweep");
  }

  /* 扫光：光泽层里那条 .card__sweep 从左扫到右（Web Animations，只动 transform / opacity，在合成器上跑） */
  const band = $(".card__sweep", card);
  function sweep(ms) {
    if (!band.animate) return;
    if (anim) anim.cancel();
    card.classList.add("is-sweep");
    anim = band.animate([
      { transform: "translateX(-24cqw) rotate(22deg)", opacity: 0 },
      { opacity: 1, offset: .16 }, { opacity: 1, offset: .8 },
      { transform: "translateX(124cqw) rotate(22deg)", opacity: 0 },
    ], { duration: ms, easing: "cubic-bezier(.45, .05, .25, 1)" });
    const a = anim;
    a.onfinish = () => { if (anim !== a) return; anim = null; card.classList.remove("is-sweep"); schedule(); };
  }
  function schedule(ms = 6000 + Math.random() * 2000) {
    clearTimeout(sweepT); sweepT = 0;
    if (!ok()) return;
    sweepT = setTimeout(() => { sweepT = 0; if (!ok()) return; if (engaged || anim) schedule(); else sweep(1600); }, ms);
  }

  /* 鼠标 / 触控笔：在整个开场里听，按与卡的距离决定要不要接管 */
  hero.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    px = e.clientX; py = e.clientY; hasPtr = true;
    if (ok()) track();
  }, { passive: true });
  hero.addEventListener("pointerleave", (e) => { if (e.pointerType === "touch") return; hasPtr = false; if (engaged) release(); });
  /* 触摸：按下只记起点；拖过 7px 且横向为主才接管，竖向先动的不管（浏览器在滚页面） */
  tilt.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "touch" || !ok() || touchId !== null) return;
    touchId = e.pointerId; tx0 = e.clientX; ty0 = e.clientY;
  });
  tilt.addEventListener("pointermove", (e) => {
    if (e.pointerId !== touchId || !ok()) return;
    if (!tdrag) {
      const dx = e.clientX - tx0, dy = e.clientY - ty0;
      if (dx * dx + dy * dy < 49) return;
      if (Math.abs(dx) <= Math.abs(dy)) { touchId = null; return; }
      tdrag = engaged = true; geo = null;
    }
    aim(e.clientX, e.clientY, true); kick();
  });
  const up = (e) => { if (e.pointerId !== touchId) return; touchId = null; if (tdrag) { tdrag = false; release(); } };
  tilt.addEventListener("pointerup", up);
  tilt.addEventListener("pointercancel", up);
  /* 点击：快扫一道光 + 一按一弹 */
  tilt.addEventListener("click", () => { if (!ok()) return; M.pop.v = Math.min(M.pop.v + 12, 18); kick(); sweep(800); });

  new IntersectionObserver(([e]) => { inView = e.isIntersecting; if (inView) schedule(); else rest(); }).observe(card);
  d.addEventListener("visibilitychange", () => { if (d.hidden) rest(); else schedule(); });
  reduce.addEventListener("change", () => { if (reduce.matches) rest(); else schedule(); });
}

/* ═════════ 0b. 开场主按钮光效（样式与各层见 main.css「开场主按钮」） ═════════
   边框是静态渐变，底色平移与气焰是 CSS 关键帧（原有两束沿边框绕行的流光已删掉）。这里只管两件事：
   - 悬停（鼠标 / 触控笔；键盘聚焦同样）：挂 .is-hot，CSS 提亮外圈与气焰。鼠标离开时若按钮仍有键盘焦点、或失焦时鼠标仍在按钮上，保持提亮。
   - 拖尾：指针在按钮上移动时，一串光斑逐个追前一个（按经过的时间做指数平滑，帧率不同速度一样），按相邻两点的方向拉长成椭圆，像一缕气流。
     画在按钮面里的一块 canvas 上（第一次悬停才建；按钮尺寸 × 设备像素比）：逐帧改一串元素的 transform 会让整页每帧重新分层，CPU 慢的机器上悬停掉到 30fps。
     画布以加色（plus-lighter，退回 screen）叠在按钮面上，划过只会提亮、不会压暗——普通叠加时，渐变尾部极低的透明度在 8 位预乘下有取整噪点，会把底色压暗一两级。
     指针停下、尾巴收拢后停掉 rAF，离开后淡出、清空再停。
   滚出视口、页面隐藏时按钮挂 .is-off，让 CSS 动画（气焰、底色平移）停下。减少动态效果：不建拖尾。 */
{
  const btn = $("[data-fx]");
  const ICE = "96 176 255", LAV = "150 122 255", PEACH = "255 160 104", WHITE = "255 255 255", TAIL = [WHITE, ICE, LAV, PEACH];
  /* 拖尾光斑：白色的头，后面 9 个颜色依次换（白 → 冰蓝 → 薰衣草 → 蜜桃），半径 13→24、不透明度 .42→.04（加色叠加，透明度比普通叠加低一半） */
  const TRAIL = [{ r: 12, c: WHITE, o: .55 }, ...Array.from({ length: 9 }, (_, i) => {
    const t = (i + 1) / 9;
    return { r: 13 + 11 * t, c: TAIL[Math.min(TAIL.length - 1, Math.floor(t * TAIL.length * .999))], o: .42 - .38 * Math.pow(t, 1.15) };
  })];
  /* 光斑的衰减（近似高斯）：canvas 径向渐变的色标 */
  const FALLOFF = [[0, 1], [.16, .8], [.34, .5], [.54, .24], [.76, .08], [1, 0]];
  if (btn) {
    let vis = true;
    const sync = () => btn.classList.toggle("is-off", !(vis && !d.hidden));
    const hot = (h) => btn.classList.toggle("is-hot", h);
    btn.addEventListener("pointerenter", (e) => { if (e.pointerType !== "touch") hot(true); });
    btn.addEventListener("pointerleave", (e) => { if (e.pointerType !== "touch") hot(btn.matches(":focus-visible")); });
    btn.addEventListener("focus", () => { if (btn.matches(":focus-visible")) hot(true); });
    btn.addEventListener("blur", () => hot(btn.matches(":hover")));
    new IntersectionObserver(([e]) => { vis = e.isIntersecting; sync(); }, { rootMargin: "40px" }).observe(btn);
    d.addEventListener("visibilitychange", sync);

    /* 拖尾 */
    const layer = $(".fx__face > .fx__ref", btn), P = TRAIL.map(() => ({ x: 0, y: 0 }));
    let cv = null, g = null, grads = [], dpr = 1, tx = 0, ty = 0, on = false, m = 0, raf = 0, last = 0;
    const local = (e) => { const r = layer.getBoundingClientRect(); tx = e.clientX - r.left; ty = e.clientY - r.top; };
    const ok = (e) => e.pointerType !== "touch" && !reduce.matches;
    const fit = () => {
      if (!cv) return;
      const r = layer.getBoundingClientRect();
      dpr = Math.min(devicePixelRatio || 1, 3);
      cv.width = Math.max(1, Math.round(r.width * dpr)); cv.height = Math.max(1, Math.round(r.height * dpr)); /* 改尺寸会清空画布，下一帧重画 */
    };
    const wipe = () => { g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height); };
    const kick = () => {
      if (!cv) {
        cv = d.createElement("canvas"); cv.className = "fx__trail"; layer.append(cv); g = cv.getContext("2d");
        /* 每个光斑一条以原点为心的径向渐变，建一次反复用（画的时候平移、旋转、拉伸到位） */
        grads = TRAIL.map((s) => { const gr = g.createRadialGradient(0, 0, 0, 0, 0, s.r), c = s.c.split(" ").join(", "); FALLOFF.forEach(([at, a]) => gr.addColorStop(at, `rgba(${c}, ${a})`)); return gr; });
        fit();
      } else if (dpr !== Math.min(devicePixelRatio || 1, 3)) fit();
      if (!raf) { last = 0; raf = requestAnimationFrame(step); }
    };
    function step(now) {
      const dt = last ? Math.min(48, now - last) : 16.7; last = now;
      const f = (k) => 1 - Math.pow(1 - k, dt / 16.7);
      let spread = Math.abs(tx - P[0].x) + Math.abs(ty - P[0].y);
      P[0].x += (tx - P[0].x) * f(.36); P[0].y += (ty - P[0].y) * f(.36);
      for (let j = 1; j < P.length; j++) {
        P[j].x += (P[j - 1].x - P[j].x) * f(.25); P[j].y += (P[j - 1].y - P[j].y) * f(.25);
        spread += Math.abs(P[j - 1].x - P[j].x) + Math.abs(P[j - 1].y - P[j].y);
      }
      m += ((on ? 1 : 0) - m) * f(on ? .16 : .1);
      wipe();
      /* 从尾到头画，白色的头压在最上面；尾巴的光斑随它与前一个的间距淡出——指针停下、尾巴收拢时气流就散了，只剩指针处一团柔光，不会叠成一块白斑 */
      for (let j = P.length - 1; j >= 0; j--) {
        const a = P[j], b = j ? P[j - 1] : { x: tx, y: ty }, dx = b.x - a.x, dy = b.y - a.y, gap = Math.hypot(dx, dy), r = TRAIL[j].r, s = 1 + Math.min(gap / r, 2.6) * .8;
        g.setTransform(dpr, 0, 0, dpr, 0, 0); g.translate(a.x, a.y); g.rotate(Math.atan2(dy, dx)); g.scale(s, 1 / Math.sqrt(s));
        g.globalAlpha = TRAIL[j].o * m * (j ? Math.min(1, gap / 4) : 1); g.fillStyle = grads[j]; g.fillRect(-r, -r, 2 * r, 2 * r);
      }
      if (on ? spread > .3 || 1 - m > .005 : m > .005) raf = requestAnimationFrame(step);
      else { raf = 0; if (!on) wipe(); }
    }
    btn.addEventListener("pointerenter", (e) => { if (!ok(e)) return; local(e); if (m < .02) P.forEach((p) => { p.x = tx; p.y = ty; }); on = true; kick(); });
    btn.addEventListener("pointermove", (e) => { if (!ok(e)) return; local(e); on = true; kick(); });
    btn.addEventListener("pointerleave", () => { on = false; if (cv) kick(); });

    new ResizeObserver(fit).observe(btn);
  }
}

/* ═════════ 4. 权益对比（compare.js） ═════════ */
initCompare();

/* ═════════ 5. 全部高级版独有功能 ═════════
   第三格写了 money 的那条（领红包、收转账）名称画成和权益对比同款的红包 / 转账小牌 */
const ALL_MONEY_ICON = { "red-packet": "i-rp", transfer: "i-transfer" };
const allItem = ([n, t, m]) => m
  ? `<li class="it--money it--${m}"><b class="mny"><svg class="ic" aria-hidden="true"><use href="#${ALL_MONEY_ICON[m]}"/></svg>${n}</b>${t}</li>`
  : `<li><b>${n}</b>${t}</li>`;
$("#all-cols").innerHTML = ALL.map(([g, items]) => `<section class="all__grp"><h3>${g}</h3><ul>${items.map(allItem).join("")}</ul></section>`).join("");

/* ═════════ 6. 导航外壳（实色底、手机菜单、主题、GitHub 星数）见 shell.js，与更新日志页共用；这里只管首页的「当前区块」渐变下划线 ═════════ */
initShell();
{
  const spyLinks = $$("[data-nav]");
  const setOn = (id) => spyLinks.forEach((a) => { const on = a.dataset.nav === id; a.classList.toggle("on", on); on ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current"); });
  const io = new IntersectionObserver((es) => { for (const e of es) if (e.isIntersecting) setOn(e.target.id === "top" || e.target.id === "all" ? "" : e.target.id); }, { rootMargin: "-45% 0px -50% 0px" });
  ["top", "all", "compare", "get"].forEach((id) => { const el = d.getElementById(id); if (el) io.observe(el); });
}

/* ═════════ 7b. 普通版下载：按系统给出合适的字样与提示 ═════════
   链接一律保留 GitHub Releases 列表页（识别失败也能自己挑），只改按钮字样、在下面补一句提示。
   普通版只有 Windows 与 macOS 15+（Apple Silicon）安装包；Intel Mac、Linux、手机都要说清楚。 */
async function detectOS() {
  const ua = navigator.userAgent || "", uad = navigator.userAgentData;
  const ipad = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;
  if (ipad || /Android|iPhone|iPad|iPod|Mobile|HarmonyOS/i.test(ua) || (uad && uad.mobile)) return { os: "mobile" };
  const plat = `${(uad && uad.platform) || ""} ${navigator.platform || ""} ${ua}`;
  if (/Win/i.test(plat)) return { os: "win" };
  if (/Mac/i.test(plat)) {
    let arch = "";
    try { if (uad && uad.getHighEntropyValues) arch = (await uad.getHighEntropyValues(["architecture"])).architecture || ""; } catch (e) { arch = ""; }
    return { os: "mac", arch: /arm/i.test(arch) ? "arm" : /x86/i.test(arch) ? "intel" : "" };
  }
  if (/Linux|X11|CrOS/i.test(plat)) return { os: "linux" };
  return { os: "" };
}
const DL = {
  win: { hero: "下载普通版（Windows）", get: "在 GitHub 下载 Windows 版" },
  "mac-arm": { hero: "下载普通版（macOS）", get: "在 GitHub 下载 macOS 版", hint: "适用于 Apple Silicon（M 系列芯片）与 macOS 15 及以上。" },
  mac: { hero: "下载普通版（macOS）", get: "在 GitHub 下载 macOS 版", hint: "macOS 版需要 macOS 15 及以上，且只支持 Apple Silicon（M 系列芯片）的 Mac。" },
  "mac-intel": { hint: "普通版的 macOS 安装包只支持 Apple Silicon（M 系列芯片）与 macOS 15 及以上，这台 Intel Mac 装不上。" },
  linux: { hint: "普通版提供 Windows 与 macOS 15+（Apple Silicon）安装包，暂无 Linux 版。" },
  mobile: { hint: "普通版是电脑软件：支持 Windows 与 macOS 15+（Apple Silicon），请在电脑上下载。" },
  "": { hint: "普通版支持 Windows 与 macOS 15+（Apple Silicon）。" },
};
detectOS().then(({ os, arch }) => {
  const k = os === "mac" ? (arch === "arm" ? "mac-arm" : arch === "intel" ? "mac-intel" : "mac") : os;
  const t = DL[k] || DL[""];
  $$("[data-dl]").forEach((a) => { const label = t[a.dataset.dl]; if (label) $("[data-dl-t]", a).textContent = label; });
  $$("[data-dl-hint]").forEach((p) => { const h = t.hint; if (!h || (p.dataset.dlHint === "hero" && (k === "win" || k === "mac-arm"))) return; p.textContent = h; p.hidden = false; });
  d.documentElement.dataset.os = k || "unknown";
}).catch(() => {});

/* ═════════ 7c. 开场眉标后的「最近更新」：取更新日志快照里最新一条的日期填进小链接（取不到就一直藏着）；点了去更新日志页 ═════════ */
{
  const a = $("[data-latest]");
  if (a) fetch("assets/data/changelog-latest.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).then((j) => {
    if (!j || !/^\d{4}-\d{2}-\d{2}$/.test(j.date)) return;
    const [, mm, dd] = j.date.split("-").map(Number);
    $("b", a).textContent = `${mm} 月 ${dd} 日`;
    a.setAttribute("aria-label", `更新日志，最近一次更新在 ${mm} 月 ${dd} 日（${j.version}）`);
    a.hidden = false;
  }).catch(() => {});
}

/* ═════════ 8. 页面隐藏时给 <html> 挂 .is-hidden，开场主按钮的 CSS 动画跟着停（开场卡的倾斜与扫光在第 0 节自己管） ═════════ */
d.addEventListener("visibilitychange", () => d.documentElement.classList.toggle("is-hidden", d.hidden));

/* ═════════ 9. 截图脚本用的跳转：把某个区块顶到导航下面 ═════════ */
window.__go = (id) => { const el = d.getElementById(id); scrollTo({ top: Math.round(el.getBoundingClientRect().top + scrollY - navH()), behavior: "instant" }); return Math.round(el.getBoundingClientRect().top); };
