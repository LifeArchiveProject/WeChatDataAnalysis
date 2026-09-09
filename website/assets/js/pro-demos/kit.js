/* ════════════════════════════════════════════════════════════
   pro-demos / kit.js — 骨架屏积木
   所有场景共用的最小 UI 元件：聊天窗、气泡、各类卡片、光标、菜单、
   表单、抽屉、朋友圈、会话列表、通知、印章，以及打字/乱码两种文字动画。
   场景只负责「摆积木 + 编时间轴」，不直接写样式。
   坐标系：场景根 .pd-screen 固定 640×400，外层用 transform 缩放。
   ════════════════════════════════════════════════════════════ */

export const SCREEN_W = 640;
export const SCREEN_H = 400;
export const SCRAMBLE_CN = "解密留痕数据档案01ABCDEF#<>/";

export function h(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text != null) el.textContent = text;
  return el;
}

export function svg(inner, vb = "0 0 24 24", cls = "") {
  const w = document.createElement("span");
  w.innerHTML = `<svg viewBox="${vb}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="${cls}">${inner}</svg>`;
  return w.firstElementChild;
}

const ICONS = {
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M3 17l5-5 4 4 3.5-3.5L21 18"/>',
  play: '<path d="M8 6.5v11l9-5.5z" fill="currentColor" stroke="none"/>',
  file: '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/>',
  voice: '<path d="M10.3 11.7l-1.8 1.8c.7.7 1.1 1.6 1.1 2.5s-.4 1.9-1.1 2.5l1.8 1.8c1.1-1.1 1.8-2.6 1.8-4.3s-.7-3.2-1.8-4.3z" fill="currentColor" stroke="none"/><path class="pd-wave-2" d="M15.2 6.7l-1.8 1.8c1.9 1.9 3 4.5 3 7.3s-1.2 5.4-3 7.3l1.8 1.8c2.3-2.3 3.8-5.5 3.8-9.1s-1.5-6.8-3.8-9.1z" fill="currentColor" stroke="none"/><path class="pd-wave-3" d="M20.1 1.8l-1.8 1.8c3.1 3.2 5 7.5 5 12.3s-1.9 9.1-5 12.3l1.8 1.8c3.6-3.6 5.9-8.5 5.9-14s-2.2-10.4-5.9-14z" fill="currentColor" stroke="none"/>',
  smile: '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.5c1 1.2 2.2 1.8 3.5 1.8s2.5-.6 3.5-1.8"/><circle cx="9" cy="10" r=".9" fill="currentColor"/><circle cx="15" cy="10" r=".9" fill="currentColor"/>',
  pin: '<path d="M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.2"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
  heart: '<path d="M12 20s-7-4.6-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.4-7 10-7 10z"/>',
  comment: '<path d="M4 5h16v11H9l-5 4z"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  hand: '<path d="M8 12V6a1.5 1.5 0 0 1 3 0v5V4.5a1.5 1.5 0 0 1 3 0V11V6a1.5 1.5 0 0 1 3 0v8.5a5.5 5.5 0 0 1-11 0V9.5a1.5 1.5 0 0 1 2-1.4"/>',
  at: '<circle cx="12" cy="12" r="4"/><path d="M16 12v1.5a2.5 2.5 0 0 0 5 0V12a9 9 0 1 0-3.5 7.1"/>',
  dots: '<circle cx="6" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="18" cy="12" r="1.4" fill="currentColor"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.6"/><path d="M15.5 14.5a5 5 0 0 1 6 5"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  chat: '<path d="M4 5h16v11h-8l-4 3v-3H4z"/>',
  code: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13 5l-2 14"/>',
  edit: '<path d="M4 20h4l10-10-4-4L4 16z"/><path d="M12.5 7.5l4 4"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  swap: '<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h9a7 7 0 0 1 0 14h-2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  mini: '<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.5 2.5 0 0 1 5 0v7a2.5 2.5 0 0 1-5 0"/>',
  send: '<path d="M4 4l16 8-16 8 3-8z"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  ai: '<rect x="5" y="5" width="14" height="14" rx="3"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/><path d="M9.5 15V9h1.6l1.4 3 1.4-3H15v6" stroke-width="1.3"/>',
  key: '<circle cx="8" cy="14" r="4"/><path d="M11 11l9-9M16 6l3 3M18 4l2 2"/>',
};

// 少数图标不是按 24×24 画的，单独登记 viewBox，否则会被裁掉（voice 曾被裁成一个小逗号）
const ICON_VB = { voice: "0 0 32 32" };
export const icon = (name, cls = "pd-ic") => svg(ICONS[name] || "", ICON_VB[name] || "0 0 24 24", cls);

/* ───────────────────────── 积木工厂 ───────────────────────── */

export function createKit(gsap, root, { reduced = false } = {}) {
  const K = {};
  K.gsap = gsap;
  K.root = root;
  K.reduced = reduced;
  K.h = h;
  K.icon = icon;

  // 场景根被外层 transform 缩放：把屏幕坐标换算回 640×400 内部坐标
  const scale = () => (root.getBoundingClientRect().width || SCREEN_W) / (root.offsetWidth || SCREEN_W);
  K.rect = (el) => {
    const s = scale() || 1;
    const b = root.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const x = (r.left - b.left) / s, y = (r.top - b.top) / s, w = r.width / s, hh = r.height / s;
    return { x, y, w, h: hh, cx: x + w / 2, cy: y + hh / 2, right: x + w, bottom: y + hh };
  };
  const pos = (target) => {
    if (typeof target === "function") target = target();
    if (target && target.nodeType === 1) { const r = K.rect(target); return { x: r.cx, y: r.cy }; }
    return target || { x: SCREEN_W / 2, y: SCREEN_H / 2 };
  };

  /* ── 挂载：默认挂到场景根，也可指定父节点 ── */
  const mount = (el, parent) => { (parent || root).appendChild(el); return el; };
  K.mount = mount;

  /* ── 光标：白点 + 琥珀环，to() 懒取目标位置，click() 打波纹 ── */
  K.cursor = ({ x = 560, y = 360 } = {}) => {
    const el = h("div", "pd-cursor");
    el.innerHTML = '<i class="pd-cursor__ring"></i><i class="pd-cursor__dot"></i>';
    mount(el);
    gsap.set(el, { x, y, opacity: 0 });
    const ring = el.firstElementChild;
    const api = {
      el,
      show(d = 0.25) { return gsap.to(el, { opacity: 1, duration: d }); },
      hide(d = 0.25) { return gsap.to(el, { opacity: 0, duration: d }); },
      to(target, { duration = 0.55, dx = 0, dy = 0, ease = "power3.inOut" } = {}) {
        return gsap.to(el, { duration, ease, x: () => pos(target).x + dx, y: () => pos(target).y + dy });
      },
      click(target, { press = true } = {}) {
        const t = gsap.timeline();
        t.fromTo(ring, { scale: 1, opacity: 0.9 }, { scale: 2.4, opacity: 0, duration: 0.45, ease: "power2.out" }, 0)
          .fromTo(el.lastElementChild, { scale: 0.6 }, { scale: 1, duration: 0.3, ease: "back.out(3)" }, 0);
        if (press && target && target.nodeType === 1) {
          t.call(() => target.classList.add("is-press"), [], 0)
            .call(() => target.classList.remove("is-press"), [], 0.22);
        }
        return t;
      },
      tap(target, opts) { const t = gsap.timeline(); t.add(this.to(target, opts)).add(this.click(target, opts)); return t; },
      dbl(target, opts) { const t = gsap.timeline(); t.add(this.to(target, opts)).add(this.click(target, opts)).add(this.click(target, opts), "-=0.3"); return t; },
    };
    return api;
  };

  /* ── 文本动画 ── */
  K.type = (el, text, { cps = 16, caret = true, delay = 0 } = {}) => {
    const chars = Array.from(text);
    const o = { n: 0 };
    return gsap.to(o, {
      n: chars.length, duration: reduced ? 0.01 : chars.length / cps, ease: "none", delay,
      snap: { n: 1 },
      onStart: () => { if (caret) el.classList.add("is-typing"); },
      onUpdate: () => { el.textContent = chars.slice(0, o.n).join(""); },
      onComplete: () => { el.textContent = text; if (caret) el.classList.remove("is-typing"); },
    });
  };
  K.scramble = (el, text, { duration = 0.55, chars = SCRAMBLE_CN, delay = 0 } = {}) => {
    const target = Array.from(text);
    const o = { p: 0 };
    return gsap.to(o, {
      p: 1, duration: reduced ? 0.01 : duration, ease: "none", delay,
      onUpdate: () => {
        const n = Math.floor(o.p * target.length);
        let s = target.slice(0, n).join("");
        for (let i = n; i < target.length; i++) s += target[i] === " " ? " " : chars[(Math.random() * chars.length) | 0];
        el.textContent = s;
      },
      onComplete: () => { el.textContent = text; },
    });
  };
  K.count = (el, to, { from = 0, duration = 0.8, fmt = (v) => String(Math.round(v)) } = {}) => {
    const o = { v: from };
    return gsap.to(o, { v: to, duration: reduced ? 0.01 : duration, ease: "power2.out", onUpdate: () => { el.textContent = fmt(o.v); } });
  };

  /* ── 通用入场/离场 ── */
  K.pop = (el, { duration = 0.42, y = 8, from = 0.92 } = {}) =>
    gsap.fromTo(el, { opacity: 0, y, scale: from }, { opacity: 1, y: 0, scale: 1, duration, ease: "back.out(1.8)", clearProps: "scale" });
  K.fade = (el, { duration = 0.3, to = 1 } = {}) => gsap.to(el, { opacity: to, duration });
  K.collapse = (el, { duration = 0.45 } = {}) => {
    const t = gsap.timeline();
    t.to(el, { opacity: 0, x: -10, duration: duration * 0.5, ease: "power2.in" })
      .to(el, { height: 0, marginTop: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, duration: duration * 0.5, ease: "power2.inOut" });
    return t;
  };
  K.flash = (el, { color = "amber", duration = 0.9 } = {}) => {
    const cls = `is-flash-${color}`;
    const t = gsap.timeline();
    t.call(() => el.classList.add(cls)).to({}, { duration }).call(() => el.classList.remove(cls));
    return t;
  };

  /* ── 骨架块 ── */
  K.skel = (w, hh = 8, cls = "") => { const e = h("i", "pd-skel " + cls); e.style.width = typeof w === "number" ? w + "px" : w; e.style.height = hh + "px"; return e; };
  K.lines = (widths, hh = 8, gap = 6) => { const w = h("div", "pd-lines"); w.style.gap = gap + "px"; widths.forEach((x) => w.appendChild(K.skel(x, hh))); return w; };

  /* ── 头像 ── */
  K.avatar = (label = "友", tone = "them", cls = "") => {
    const a = h("i", `pd-av pd-av--${tone} ${cls}`, label);
    return a;
  };
  K.avatarGrid = (labels = ["我", "友", "小", "王"]) => {
    const g = h("i", "pd-av pd-av--grid");
    labels.slice(0, 4).forEach((l) => g.appendChild(h("b", "", l)));
    return g;
  };

  /* ── 窗口：应用窗 / 微信窗 ── */
  K.window = ({ title = "WeChatDataAnalysis", kind = "app", cls = "" } = {}) => {
    const el = h("div", `pd-win pd-win--${kind} ${cls}`);
    const bar = h("div", "pd-win__bar");
    bar.innerHTML = '<i></i><i></i><i></i>';
    bar.appendChild(h("b", "pd-win__title", title));
    const body = h("div", "pd-win__body");
    el.append(bar, body);
    return { el, bar, body, title: bar.lastElementChild };
  };

  /* ── 聊天窗：可带左侧会话栏；list 里放行，input 是输入条 ── */
  K.chat = ({ title = "客户 · 王总", rail = true, group = false, cls = "", parent, railNames } = {}) => {
    const el = h("div", `pd-chat ${group ? "pd-chat--group" : ""} ${rail ? "" : "pd-chat--norail"} ${cls}`);
    let railEl = null;
    if (rail) {
      railEl = h("aside", "pd-chat__rail");
      const search = h("i", "pd-chat__search");
      railEl.appendChild(search);
      // 默认业务语境；本地存档类场景传 railNames 换成私人语境（家人群 / 室友 / 老同学）
      const names = railNames ? [title, ...railNames].slice(0, 4) : [title, "客户群", "李经理", "订单群"];
      names.forEach((n, i) => {
        const r = h("div", "pd-sess" + (i === 0 ? " is-active" : ""));
        r.appendChild(K.avatar(n[0], i % 2 ? "them" : "muted"));
        const t = h("div", "pd-sess__txt");
        t.append(h("b", "", n), K.skel(46 + ((i * 17) % 30), 5));
        r.appendChild(t);
        railEl.appendChild(r);
      });
      el.appendChild(railEl);
    }
    const main = h("div", "pd-chat__main");
    const head = h("header", "pd-chat__head");
    const titleEl = h("b", "pd-chat__title", title);
    head.append(titleEl, icon("dots", "pd-ic pd-chat__more"));
    const list = h("div", "pd-chat__list");
    const input = h("div", "pd-chat__input");
    const field = h("span", "pd-chat__field");
    const text = h("em", "pd-chat__text");
    field.append(text, h("i", "pd-caret"));
    const tools = h("div", "pd-chat__tools");
    tools.append(icon("smile"), icon("image"), icon("file"), icon("mic"));
    const send = h("b", "pd-chat__send", "发送");
    input.append(tools, field, send);
    main.append(head, list, input);
    el.appendChild(main);
    mount(el, parent);

    const api = {
      el, rail: railEl, main, head, title: titleEl, more: head.lastElementChild, list, input, field: text, tools, send,
      sessions: railEl ? [...railEl.querySelectorAll(".pd-sess")] : [],
      row(side, content, { name, label, av } = {}) {
        const r = h("div", `pd-row pd-row--${side}`);
        const a = K.avatar(av ?? label ?? (side === "r" ? "我" : "友"), side === "r" ? "me" : "them");
        const body = h("div", "pd-row__body");
        if (name) body.appendChild(h("i", "pd-row__name", name));
        if (typeof content === "string") content = K.bubble(content, side);
        body.appendChild(content);
        r.append(a, body);
        list.appendChild(r);
        return Object.assign(r, { av: a, body, content });
      },
      // 在 ref 行之后插入一行（补录场景用）；ref 为 null 则插到最前
      rowAt(ref, side, content, opts = {}) {
        const r = api.row(side, content, opts);
        const before = ref ? ref.nextSibling : list.firstChild;
        if (before) list.insertBefore(r, before);
        return r;
      },
      time(t = "昨天 21:47") { const e = h("p", "pd-time", t); list.appendChild(e); return e; },
      sys(t) { const e = h("p", "pd-sys", t); list.appendChild(e); return e; },
      seed(n = 3) {
        // 三条常规往来，作为所有场景的默认上下文（业务语境：客户问 → 我方答 → 客户确认）
        const rows = [];
        rows.push(api.time("今天 14:02"));
        rows.push(api.row("l", "这批还有现货吗？"));
        rows.push(api.row("r", "有的，现货充足"));
        if (n > 2) rows.push(api.row("l", "好，我这边下单了"));
        return rows;
      },
    };
    return api;
  };

  /* ── 气泡与卡片 ── */
  K.bubble = (text, side = "l", cls = "") => h("div", `pd-bub pd-bub--${side} ${cls}`, text);
  K.tag = (text, cls = "") => h("i", `pd-tag ${cls}`, text);

  const card = (kind, cls = "") => h("div", `pd-card pd-card--${kind} ${cls}`);
  K.card = {
    image({ w = 128, hh = 92 } = {}) { const c = card("img"); c.style.width = w + "px"; c.style.height = hh + "px"; c.appendChild(icon("image")); return c; },
    video({ dur = "0:12" } = {}) { const c = card("video"); c.appendChild(icon("play", "pd-ic pd-card__play")); c.appendChild(h("b", "pd-card__dur", dur)); return c; },
    file({ name = "报销明细.xlsx", size = "24.6 KB" } = {}) {
      const c = card("file");
      const t = h("div", "pd-card__txt"); t.append(h("b", "", name), h("i", "", size));
      const ic = h("i", "pd-card__fic"); ic.appendChild(icon("file"));
      c.append(t, ic);
      c.appendChild(h("p", "pd-card__foot", "微信电脑版"));
      return c;
    },
    voice({ sec = 6, side = "l" } = {}) {
      const c = h("div", `pd-bub pd-bub--${side} pd-voice`);
      c.append(icon("voice", "pd-ic pd-voice__ic"), h("span", "", `${sec}″`));
      return c;
    },
    emoji() { const c = card("emoji"); c.appendChild(icon("smile")); return c; },
    transfer({ amount = "¥520.00", note = "转账给你" } = {}) {
      const c = card("transfer");
      const m = h("div", "pd-card__main");
      const ic = h("i", "pd-card__cic", "¥");
      const t = h("div", ""); t.append(h("b", "", amount), h("i", "", note));
      m.append(ic, t); c.append(m, h("p", "pd-card__foot", "微信转账"));
      return c;
    },
    redpacket({ text = "恭喜发财，大吉大利" } = {}) {
      const c = card("rp");
      const m = h("div", "pd-card__main");
      const ic = h("i", "pd-card__cic pd-card__cic--rp"); ic.appendChild(svg('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M5 10h14"/><circle cx="12" cy="10" r="2" fill="currentColor"/>', "0 0 24 24", "pd-ic"));
      const t = h("div", ""); t.append(h("b", "", text), h("i", "", "领取红包"));
      m.append(ic, t); c.append(m, h("p", "pd-card__foot", "微信红包"));
      return c;
    },
    location({ name = "老地方咖啡", addr = "建国路 88 号 B1" } = {}) {
      const c = card("loc");
      const t = h("div", "pd-card__txt"); t.append(h("b", "", name), h("i", "", addr));
      const map = h("div", "pd-card__map"); map.appendChild(icon("pin"));
      c.append(t, map);
      return c;
    },
    link({ title = "这几年谢谢你，真的", desc = "一段被完整找回的对话" } = {}) {
      const c = card("link");
      const t = h("div", "pd-card__txt"); t.append(h("b", "", title), h("i", "", desc));
      const th = h("i", "pd-card__thumb"); th.appendChild(icon("link"));
      const row = h("div", "pd-card__row"); row.append(t, th);
      c.append(row, h("p", "pd-card__foot", "公众号 · 文章"));
      return c;
    },
    miniapp({ title = "点单小程序", app = "咖啡屋" } = {}) {
      const c = card("mini");
      const head = h("div", "pd-card__apphead"); head.append(icon("mini"), h("b", "", app));
      const big = h("div", "pd-card__big"); big.appendChild(h("b", "", title));
      const foot = h("p", "pd-card__foot"); foot.append(icon("mini"), h("span", "", "小程序"));
      c.append(head, big, foot);
      return c;
    },
    channels({ name = "城市漫游记" } = {}) {
      const c = card("channels");
      const v = h("div", "pd-card__portrait"); v.appendChild(icon("play", "pd-ic pd-card__play"));
      const t = h("div", "pd-card__txt"); t.append(h("b", "", name), h("i", "", "视频号"));
      c.append(v, t);
      return c;
    },
    quote({ text = "好，就这么定了", quote = "友：刚落地，还是老地方见", side = "r" } = {}) {
      const w = h("div", "pd-quotewrap");
      const b = K.bubble(text, side);
      const q = h("div", "pd-quote", quote);
      w.append(b, q);
      return Object.assign(w, { bubble: b, quote: q });
    },
    merged({ title = "我和友的聊天记录", lines = ["友：到了跟我说一声", "我：刚落地，还是老地方见", "友：好，就这么定了"] } = {}) {
      const c = card("merged");
      c.appendChild(h("b", "pd-card__title", title));
      const ul = h("div", "pd-card__lines");
      lines.forEach((l) => ul.appendChild(h("span", "", l)));
      c.append(ul, h("p", "pd-card__foot", "聊天记录"));
      return c;
    },
    call({ dur = "03:21", video = false, side = "l" } = {}) {
      const c = h("div", `pd-bub pd-bub--${side} pd-call`);
      c.append(icon(video ? "video" : "phone"), h("span", "", `通话时长 ${dur}`));
      return c;
    },
    sticker() { return K.card.emoji(); },
  };

  /* ── 系统行 / 拍一拍 ── */
  K.sys = (text, parent) => mount(h("p", "pd-sys", text), parent);
  K.pat = ({ from = "我", to = "友" } = {}, parent) => {
    const p = h("p", "pd-sys pd-pat");
    p.innerHTML = `「<b>${from}</b>」拍了拍「<b>${to}</b>」`;
    return mount(p, parent);
  };

  /* ── 右键菜单：贴着目标出现 ── */
  K.menu = (items, { at, dx = 8, dy = 8, parent } = {}) => {
    const el = h("div", "pd-menu");
    const its = items.map((label) => {
      const it = h("div", "pd-menu__it");
      if (typeof label === "object") { if (label.icon) it.appendChild(icon(label.icon)); it.appendChild(h("span", "", label.label)); if (label.danger) it.classList.add("is-danger"); }
      else it.appendChild(h("span", "", label));
      el.appendChild(it);
      return it;
    });
    mount(el, parent);
    gsap.set(el, { opacity: 0 });
    const place = () => {
      const p = at ? pos(at) : { x: 200, y: 200 };
      let x = p.x + dx, y = p.y + dy;
      const w = el.offsetWidth || 120, hh = el.offsetHeight || 100;
      // 右侧放不下就翻到锚点左边：偏移取绝对值，否则负 dx 会把菜单越推越靠右（群聊组实证）
      if (x + w > SCREEN_W - 8) x = p.x - w - Math.abs(dx);
      // 最后统一夹回屏内，四边各留 8px
      x = Math.max(8, Math.min(x, SCREEN_W - w - 8));
      y = Math.max(8, Math.min(y, SCREEN_H - hh - 8));
      gsap.set(el, { x, y });
    };
    const api = {
      el, items: its,
      open(d = 0.22) { const t = gsap.timeline(); t.call(place).fromTo(el, { opacity: 0, scale: 0.92, transformOrigin: "0 0" }, { opacity: 1, scale: 1, duration: d, ease: "power3.out" }); return t; },
      close(d = 0.18) { return gsap.to(el, { opacity: 0, duration: d }); },
      hover(i) { its.forEach((x, k) => x.classList.toggle("is-hover", k === i)); },
    };
    return api;
  };

  /* ── 抽屉 / 侧板：源码、字段编辑、群信息 ── */
  K.sheet = ({ title = "详情", parent, cls = "" } = {}) => {
    const el = h("div", `pd-sheet ${cls}`);
    const head = h("div", "pd-sheet__head");
    head.append(h("b", "", title), h("i", "pd-sheet__x", "×"));
    const body = h("div", "pd-sheet__body");
    const foot = h("div", "pd-sheet__foot");
    const cancel = h("b", "pd-btn pd-btn--ghost", "取消");
    const ok = h("b", "pd-btn pd-btn--amber", "保存");
    foot.append(cancel, ok);
    el.append(head, body, foot);
    mount(el, parent);
    gsap.set(el, { xPercent: 100 });
    return {
      el, head, body, foot, ok, cancel,
      open(d = 0.45) { return gsap.to(el, { xPercent: 0, duration: d, ease: "power3.out" }); },
      close(d = 0.35) { return gsap.to(el, { xPercent: 100, duration: d, ease: "power3.in" }); },
    };
  };

  /* ── 表单字段 ── */
  K.form = (rows, parent) => {
    const el = h("div", "pd-form");
    const out = rows.map(([label, value, mono]) => {
      const r = h("div", "pd-field");
      const l = h("i", "pd-field__l", label);
      const v = h("b", "pd-field__v" + (mono ? " mono" : ""), value);
      r.append(l, v);
      el.appendChild(r);
      return Object.assign(r, { label: l, value: v });
    });
    mount(el, parent);
    return { el, rows: out };
  };

  /* ── 代码块 ── */
  K.code = (lines, parent) => {
    const el = h("pre", "pd-code");
    const out = lines.map((l, i) => {
      const row = h("div", "pd-code__ln");
      row.append(h("i", "", String(i + 1).padStart(2, "0")), h("span", "", l));
      el.appendChild(row);
      return row;
    });
    mount(el, parent);
    return { el, lines: out };
  };

  /* ── 印章：右下角 ✓ 已写入 ── */
  K.stamp = (text = "已写入", { en = "WRITTEN", parent } = {}) => {
    const el = h("div", "pd-stamp");
    el.append(icon("check"), h("b", "", text), h("i", "", en));
    mount(el, parent);
    gsap.set(el, { opacity: 0 });
    return el;
  };
  K.ok = (text = "已写入", opts = {}) => {
    const el = K.stamp(text, opts);
    const t = gsap.timeline();
    t.fromTo(el, { opacity: 0, scale: 1.25, rotate: -6, transformOrigin: "100% 100%" }, { opacity: 1, scale: 1, rotate: -3, duration: 0.32, ease: "power4.out" })
      .to({}, { duration: opts.hold ?? 0.9 });
    return t;
  };

  /* ── 通知横幅 ── */
  K.toast = ({ title = "微信", body = "", app = "WeChatDataAnalysis", parent, width } = {}) => {
    const el = h("div", "pd-toast");
    if (width) el.style.width = width + "px";
    const ic = h("i", "pd-toast__ic"); ic.appendChild(icon("bell"));
    const t = h("div", "pd-toast__txt");
    t.append(h("b", "", title), h("span", "", body), h("i", "", app));
    el.append(ic, t);
    mount(el, parent);
    gsap.set(el, { x: 40, opacity: 0 });
    return {
      el, body: t.children[1], title: t.children[0],
      show(d = 0.5) { return gsap.to(el, { x: 0, opacity: 1, duration: d, ease: "power3.out" }); },
      hide(d = 0.35) { return gsap.to(el, { x: 40, opacity: 0, duration: d, ease: "power3.in" }); },
    };
  };

  /* ── 朋友圈信息流 ── */
  K.feed = ({ parent, cls = "" } = {}) => {
    const el = h("div", `pd-feed ${cls}`);
    const head = h("header", "pd-feed__head");
    head.append(h("b", "", "朋友圈"), icon("camera"));
    const list = h("div", "pd-feed__list");
    el.append(head, list);
    mount(el, parent);
    const api = {
      el, head, list, camera: head.lastElementChild,
      post({ name = "小王", text = "周末的山，云在脚下。", imgs = 3, time = "10 分钟前", likes = [], comments = [], top = false } = {}) {
        const p = h("article", "pd-post");
        const av = K.avatar(name[0], "them");
        const body = h("div", "pd-post__body");
        body.appendChild(h("b", "pd-post__name", name));
        const txt = h("p", "pd-post__text", text);
        body.appendChild(txt);
        const grid = h("div", `pd-post__grid pd-post__grid--${Math.min(imgs, 9)}`);
        const tiles = [];
        for (let i = 0; i < imgs; i++) { const ti = h("i", "pd-post__img"); ti.appendChild(icon("image")); grid.appendChild(ti); tiles.push(ti); }
        if (imgs) body.appendChild(grid);
        const meta = h("div", "pd-post__meta");
        const timeEl = h("i", "", time);
        const more = h("b", "pd-post__more"); more.appendChild(icon("dots"));
        meta.append(timeEl, more);
        body.appendChild(meta);
        const social = h("div", "pd-post__social");
        const likeRow = h("div", "pd-post__likes");
        likeRow.appendChild(icon("heart"));
        const likeNames = h("span", "", likes.join("，"));
        likeRow.appendChild(likeNames);
        const cmtBox = h("div", "pd-post__cmts");
        comments.forEach(([who, what]) => { const c = h("p", ""); c.innerHTML = `<b>${who}</b>：${what}`; cmtBox.appendChild(c); });
        social.append(likeRow, cmtBox);
        if (!likes.length) likeRow.style.display = "none";
        if (!comments.length && !likes.length) social.style.display = "none";
        body.appendChild(social);
        p.append(av, body);
        if (top && list.firstChild) list.insertBefore(p, list.firstChild); else list.appendChild(p);
        return Object.assign(p, { av, body, text: txt, grid, tiles, meta, time: timeEl, more, social, likeRow, likeNames, cmtBox });
      },
      seed(n = 2) {
        // 默认两条客户动态（业务语境：朋友圈这组的真实用户是做客户运营的人）
        const a = api.post({ name: "客户 · 王总", text: "新店下周开业，欢迎来坐。", imgs: 3, time: "10 分钟前" });
        const b = n > 1 ? api.post({ name: "客户 · 李姐", text: "这批货已经到店了。", imgs: 1, time: "1 小时前" }) : null;
        return [a, b].filter(Boolean);
      },
    };
    return api;
  };

  /* ── 会话列表（独立于 chat.rail 使用）── */
  K.sessions = (items = ["老地方", "家人群", "同事", "小王"], { parent, cls = "" } = {}) => {
    const el = h("div", `pd-sessions ${cls}`);
    const rows = [];
    const mk = (n, i) => {
      const r = h("div", "pd-sess");
      const o = typeof n === "object" ? n : { name: n };
      r.appendChild(o.grid ? K.avatarGrid(o.grid) : K.avatar(o.av ?? (o.name || "")[0], o.tone ?? (i % 2 ? "them" : "muted")));
      const t = h("div", "pd-sess__txt");
      const nameEl = h("b", "", n.name || n);
      t.append(nameEl, K.skel(46 + ((i * 17) % 30), 5));
      r.appendChild(t);
      return Object.assign(r, { name: nameEl });
    };
    items.forEach((n, i) => { const r = mk(n, i); el.appendChild(r); rows.push(r); });
    mount(el, parent);
    return {
      el, rows,
      add(n, { top = true, hidden = false } = {}) { const r = mk(n, rows.length); if (top && el.firstChild) el.insertBefore(r, el.firstChild); else el.appendChild(r); rows.push(r); if (hidden) gsap.set(r, { display: "none" }); return r; },
    };
  };

  /* ── 联系人勾选器（新建群聊）── */
  K.picker = (names = ["小王", "阿明", "老张", "同事李"], { parent, title = "选择联系人" } = {}) => {
    const el = h("div", "pd-picker");
    const head = h("div", "pd-picker__head");
    head.append(h("b", "", title));
    const list = h("div", "pd-picker__list");
    const rows = names.map((n, i) => {
      const r = h("div", "pd-picker__row");
      const box = h("i", "pd-check");
      box.appendChild(icon("check"));
      r.append(box, K.avatar(n[0], i % 2 ? "them" : "muted"), h("b", "", n));
      list.appendChild(r);
      return Object.assign(r, { box });
    });
    const foot = h("div", "pd-picker__foot");
    const done = h("b", "pd-btn pd-btn--amber", "完成");
    foot.appendChild(done);
    el.append(head, list, foot);
    mount(el, parent);
    return {
      el, rows, done,
      check(i, on = true) { rows[i].classList.toggle("is-on", on); rows[i].box.classList.toggle("is-on", on); const n = rows.filter((r) => r.classList.contains("is-on")).length; done.textContent = n ? `完成 (${n})` : "完成"; },
    };
  };

  /* ── 关键词芯片 ── */
  K.chips = (words = [], { parent } = {}) => {
    const el = h("div", "pd-chips");
    const rows = words.map((w) => { const c = h("i", "pd-chip", w); el.appendChild(c); return c; });
    mount(el, parent);
    return {
      el, rows,
      add(w, { hidden = false } = {}) { const c = h("i", "pd-chip", w); el.appendChild(c); rows.push(c); if (hidden) gsap.set(c, { display: "none" }); return c; },
    };
  };

  /* ── 补录插槽：两行之间的琥珀发丝线 + 「⊕ 补录」小药丸，插在 ref 行之后 ── */
  K.gap = (chat, ref, { label = "补录" } = {}) => {
    const el = h("div", "pd-gap");
    const pill = h("b", "pd-gap__pill");
    pill.append(icon("plus"), h("span", "", label));
    el.appendChild(pill);
    const before = ref ? ref.nextSibling : chat.list.firstChild;
    if (before) chat.list.insertBefore(el, before); else chat.list.appendChild(el);
    gsap.set(el, { opacity: 0 });
    return Object.assign(el, { pill });
  };

  /* ── 补录抽屉：类型 + 几个字段 + 预览区 + 保存；17 个补录场景共用同一张脸 ── */
  K.compose = ({ type = "文字", fields = [], title = "补录消息", parent } = {}) => {
    const sheet = K.sheet({ title: `${title} · ${type}`, parent });
    const typeRow = h("div", "pd-compose__type");
    const types = ["文字", "图片", "文件", "语音", "视频", "表情", "转账", "红包", "位置", "链接", "小程序", "视频号", "引用", "聊天记录", "通话", "系统", "拍一拍"];
    const chips = types.map((t) => { const c = h("i", "pd-chip pd-chip--dim" + (t === type ? " is-hit" : ""), t); typeRow.appendChild(c); return c; });
    sheet.body.appendChild(typeRow);
    const form = K.form([["发送方", "我"], ["时间", "昨天 21:52"], ...fields], sheet.body);
    const preview = h("div", "pd-compose__preview");
    preview.appendChild(h("i", "pd-compose__hint", "预览"));
    sheet.body.appendChild(preview);
    sheet.ok.textContent = "保存";
    return { ...sheet, sheet, chips, form, preview, ok: sheet.ok, cancel: sheet.cancel };
  };

  /* ── 双窗口：左「本应用」右「微信」，发送类场景用；fly() 让一粒琥珀光点从 A 飞到 B ── */
  K.twin = ({ title = "老地方", group = false } = {}) => {
    const app = K.window({ title: "WECHATDATAANALYSIS", kind: "app", cls: "pd-twin__app" });
    const wx = K.window({ title: "WECHAT · 微信", kind: "wechat", cls: "pd-twin__wx" });
    mount(app.el); mount(wx.el);
    const appChat = K.chat({ title, rail: false, group, parent: app.body });
    const wxChat = K.chat({ title, rail: false, group, parent: wx.body, cls: "pd-chat--wx" });
    const spark = h("i", "pd-spark");
    mount(spark);
    gsap.set(spark, { opacity: 0 });
    const fly = (from, to, { duration = 0.7 } = {}) => {
      const t = gsap.timeline();
      t.set(spark, { x: () => pos(from).x, y: () => pos(from).y, opacity: 1, scale: 0.6 })
        .to(spark, { duration, ease: "power2.inOut", x: () => pos(to).x, y: () => pos(to).y, scale: 1 })
        .to(spark, { opacity: 0, scale: 2.2, duration: 0.25 });
      return t;
    };
    return { app, wx, appChat, wxChat, spark, fly };
  };

  /* ── 补录流程：17 个补录场景共用的整段编排 ──
     insertFlow(chat, { after, side, type, fields, build(previewMode), beat({content, comp, cursor}), stamp, en, c })
     build 会被调两次：一次给抽屉预览（previewMode=true），一次给真正插入聊天的那行。
     beat 可选：在预览区里做一段动作（打字、数字滚表、地图落针…），返回 tween/timeline。 */
  K.insertFlow = (chat, { after = null, side = "r", type = "文字", fields = [], build, beat, stamp = "已写入", en = "WRITTEN", c, name, label } = {}) => {
    const cursor = c || K.cursor();
    const gap = K.gap(chat, after, label ? { label } : {});
    const comp = K.compose({ type, fields });
    const preview = build(true);
    comp.preview.appendChild(preview);
    gsap.set(preview, { opacity: 0, scale: 0.92, transformOrigin: "50% 50%" });
    const final = build(false);
    const row = side === "sys" ? null : chat.rowAt(after, side, final, name ? { name } : {});
    let node = row;
    if (!row) { node = final; const before = after ? after.nextSibling : chat.list.firstChild; if (before) chat.list.insertBefore(node, before); else chat.list.appendChild(node); }
    if (row) row.body.appendChild(K.tag("补录"));
    gsap.set(node, { display: "none" });
    const t = gsap.timeline();
    t.add(cursor.show(), 0.15)
      .add(cursor.to(gap.pill, { duration: 0.6 }), 0.25)
      .to(gap, { opacity: 1, duration: 0.3 }, "<+0.35")
      .add(cursor.click(gap.pill), ">")
      .add(comp.open(), ">-0.05")
      .add(cursor.to(comp.preview, { duration: 0.45, dy: 18 }), "<+0.2")
      .to(preview, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(1.6)" }, ">-0.1");
    const b = beat ? beat({ content: preview, comp, cursor, chat }) : null;
    if (b) t.add(b, ">"); else t.to({}, { duration: 0.55 });
    t.add(cursor.to(comp.ok, { duration: 0.45 }), ">+0.15")
      .add(cursor.click(comp.ok), ">")
      .add(comp.close(), ">")
      .set(gap, { display: "none" })
      .set(node, { display: row ? "flex" : "block" })
      .add(K.pop(node), "<")
      .add(K.flash(row ? row.content : node, { color: "amber", duration: 0.7 }), "<")
      .add(K.ok(stamp, { en }), ">-0.3")
      .add(cursor.hide(), "<");
    return Object.assign(t, { cursor, gap, comp, preview, row, node });
  };

  /* ── 发送流程：7 个微信动作场景共用 ──
     sendFlow(twin, { beat({ cursor, appChat, wxChat, twin }), build(where: "app"|"wx"), side, stamp, en, c })
     beat 是用户在左窗的操作（打字/选图/按住说话…）；随后点发送 → 光点飞到右窗 → 两边各出现一条 → 印章。 */
  K.sendFlow = (twin, { beat, build, side = "r", stamp = "已发送", en = "SENT · VIA WECHAT", c, name, noSendButton = false } = {}) => {
    const cursor = c || K.cursor({ x: 250, y: 372 });   // 默认起点落在左窗输入条附近，别压在右窗发送键上
    const { appChat, wxChat } = twin;
    const mk = (chat, where) => {
      const content = build(where);
      if (side === "sys") { chat.list.appendChild(content); gsap.set(content, { display: "none" }); return content; }
      const r = chat.row(side, content, name ? { name } : {});
      gsap.set(r, { display: "none" });
      return r;
    };
    const rowApp = mk(appChat, "app"), rowWx = mk(wxChat, "wx");
    const t = gsap.timeline();
    t.add(cursor.show(), 0.15);
    const b = beat ? beat({ cursor, appChat, wxChat, twin }) : null;
    if (b) t.add(b, 0.3);
    if (!noSendButton) t.add(cursor.to(appChat.send, { duration: 0.45 }), ">+0.15").add(cursor.click(appChat.send), ">");
    t.set(rowApp, { display: side === "sys" ? "block" : "flex" })
      .add(K.pop(rowApp), "<")
      .call(() => { appChat.field.textContent = ""; appChat.field.classList.remove("is-typing"); }, [], "<")
      .add(twin.fly(noSendButton ? rowApp : appChat.send, wxChat.list, { duration: 0.7 }), "<+0.1")
      .set(rowWx, { display: side === "sys" ? "block" : "flex" }, ">-0.1")
      .add(K.pop(rowWx), "<")
      .add(K.flash(side === "sys" ? rowWx : rowWx.content, { color: "neon", duration: 0.7 }), "<")
      .add(K.ok(stamp, { en }), ">-0.3")
      .add(cursor.hide(), "<");
    return Object.assign(t, { cursor, rowApp, rowWx });
  };

  /* ── 情境条：屏幕顶端一条，左边交代「此刻发生了什么」，结尾右边给出「结果」 ──
     每个场景都该有一条：光演操作观众不知道为什么要做，情境条先把场景立住。
     它会把已知的布局根（聊天窗/朋友圈/窗口/自定义 .pd-pushed）下推 22px，光标与菜单不受影响。 */
  K.scenario = (text, { parent, local = false } = {}) => {
    const el = h("div", "pd-strip");
    const t = h("span", "pd-strip__t", text);
    // 只写本地解密副本的能力（消息修改 / 消息补录 / 标记已读 / 免打扰）必须挂这枚标：
    // 画面演的是一场与客户的对话，不点明就会被读成「对方也看到了」
    if (local) t.appendChild(h("i", "pd-strip__local", "本地副本 · 不回写微信"));
    const r = h("b", "pd-strip__r");
    el.append(t, r);
    mount(el, parent);
    root.classList.add("has-strip");
    gsap.set(el, { opacity: 0, x: -12 });
    gsap.set(r, { opacity: 0 });
    return Object.assign(el, {
      text: t, out: r,
      in(d = 0.4) { return gsap.to(el, { opacity: 1, x: 0, duration: d, ease: "power3.out" }); },
      // 结尾的业务结果：与印章同一拍出现，回答「所以呢」
      result(txt, d = 0.4) {
        const tl = gsap.timeline();
        tl.call(() => { r.textContent = txt; })
          .fromTo(r, { opacity: 0, x: 10 }, { opacity: 1, x: 0, duration: d, ease: "power3.out" });
        return tl;
      },
      say(txt, d = 0.35) { const tl = gsap.timeline(); tl.call(() => { t.textContent = txt; }).fromTo(t, { opacity: 0.3 }, { opacity: 1, duration: d }); return tl; },
    });
  };

  /* ── 工作流轨：贴在屏幕底端，动作类能力统一用它表达「不是人在点，是工作流自动跑」──
     steps: [{ label, ai?, icon? }] 或纯字符串；step(i) 点亮第 i 步并返回 timeline。
     它会把布局根的下边收 24px（与情境条的上边 22px 对称），印章自动上移让位。 */
  K.workflow = (steps = [], { parent, title = "WORKFLOW" } = {}) => {
    const el = h("div", "pd-flow");
    el.appendChild(h("b", "pd-flow__tag", title));
    const nodes = steps.map((raw, i) => {
      const spec = typeof raw === "string" ? { label: raw } : raw;
      if (i) el.appendChild(h("i", "pd-flow__arrow", "›"));
      const n = h("span", "pd-flow__n" + (spec.ai ? " is-ai" : ""));
      n.appendChild(icon(spec.icon || (spec.ai ? "ai" : i === 0 ? "bolt" : "check"), "pd-ic pd-flow__ic"));
      if (spec.ai) n.appendChild(h("b", "pd-flow__ai", "AI"));
      n.appendChild(h("span", "", spec.label));
      el.appendChild(n);
      return n;
    });
    mount(el, parent);
    root.classList.add("has-flow");
    gsap.set(el, { opacity: 0, y: 10 });
    return Object.assign(el, {
      nodes,
      in(d = 0.4) { return gsap.to(el, { opacity: 1, y: 0, duration: d, ease: "power3.out" }); },
      // 点亮第 i 步：前面的收成已完成态，当前这步高亮并轻微弹一下
      step(i, d = 0.3) {
        const t = gsap.timeline();
        t.call(() => { nodes.forEach((n, k) => { n.classList.toggle("is-on", k === i); n.classList.toggle("is-done", k < i); }); })
          .fromTo(nodes[i], { scale: 0.94 }, { scale: 1, duration: d, ease: "back.out(2.4)" });
        return t;
      },
      done(d = 0.3) {
        const t = gsap.timeline();
        t.call(() => nodes.forEach((n) => { n.classList.remove("is-on"); n.classList.add("is-done"); }));
        return t.to({}, { duration: d });
      },
    });
  };

  /* ── 通用按钮 ── */
  K.btn = (text, tone = "amber", parent) => mount(h("b", `pd-btn pd-btn--${tone}`, text), parent);

  /* ── 屏幕右上角的场景注释：必要时给一行说明 ── */
  K.note = (text, parent) => { const n = h("p", "pd-note", text); mount(n, parent); gsap.set(n, { opacity: 0 }); return n; };

  return K;
}
