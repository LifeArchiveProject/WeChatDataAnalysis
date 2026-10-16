/* 更新日志页：导航外壳（shell.js）+ 从 assets/data/changelog.json 渲染时间线、计数与筛选。
   数据由 tools/dev/sync-site-changelog.mjs 生成：部署时从高级版的发布接口取最新的，取不到就用仓库里的快照。
   - 每个版本：版本号（可点，带锚点）、日期、平台、条数；全部变化直接列出（不折叠、不弹层）。
   - 筛选：平台（全部 / Windows / macOS / Linux）× 类型（全部 / 新增 / 优化 / 修复）；选项后的数字跟着另一项条件变；
     条件记在地址栏（?pf=macos&t=fix），可直接分享；不符合的条目与没有剩余条目的版本隐藏。
   - 文字一律用 textContent 写入，不拼 HTML。 */
import { initShell } from "./shell.js";

initShell();

const d = document;
const $ = (s, r = d) => r.querySelector(s);
const $$ = (s, r = d) => [...r.querySelectorAll(s)];
const el = (tag, cls, text) => { const e = d.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

const TYPE = { feature: "新增", improve: "优化", fix: "修复" };
const PF = { windows: "Windows", macos: "macOS", linux: "Linux" };
const fmtDate = (s) => { const [y, m, dd] = s.split("-").map(Number); return { full: `${y} 年 ${m} 月 ${dd} 日`, short: `${m} 月 ${dd} 日` }; };

const list = $("#cl-list"), empty = $("#cl-empty"), bar = $("#cl-bar");
let items = [];
const state = { pf: "", t: "" };

function render() {
  list.textContent = "";
  items.forEach((r, i) => {
    const art = el("article", "rel" + (i === 0 ? " rel--latest" : ""));
    art.id = "v" + r.version;
    art.dataset.pf = r.platforms.join(" ");
    const h = el("header", "rel__h");
    const v = el("p", "rel__v"), a = el("a", "", r.version);
    a.href = "#" + art.id;
    v.append(a);
    if (i === 0) v.append(el("span", "rel__new", "最新"));
    const dt = fmtDate(r.date), time = el("time", "", dt.full);
    time.dateTime = r.date;
    const date = el("p", "rel__d"); date.append(time);
    const meta = el("p", "rel__meta");
    r.platforms.forEach((p) => meta.append(el("span", "pf", PF[p] || p)));
    const n = el("span", "rel__n"); meta.append(n);
    h.append(v, date, meta);
    const ul = el("ul", "rel__c");
    r.changes.forEach((c) => {
      const li = el("li");
      li.dataset.t = c.type;
      li.append(el("span", "ty ty--" + c.type, TYPE[c.type] || c.type), el("span", "", c.text));
      ul.append(li);
    });
    art.append(h, ul);
    list.append(art);
  });
}

/* 按当前条件显示 / 隐藏，更新每版的条数、筛选项后的数字和地址栏 */
function apply(push = true) {
  let shownRel = 0, shownChg = 0;
  $$(".rel", list).forEach((art) => {
    const pfOk = !state.pf || art.dataset.pf.split(" ").includes(state.pf);
    let n = 0;
    $$("li", art).forEach((li) => { const ok = pfOk && (!state.t || li.dataset.t === state.t); li.hidden = !ok; if (ok) n++; });
    art.hidden = !n;
    $(".rel__n", art).textContent = `${n} 项${state.t ? TYPE[state.t] : "变化"}`;
    if (n) { shownRel++; shownChg += n; }
  });
  empty.hidden = !!shownRel;
  // 选项后的数字：平台一栏按当前类型算，类型一栏按当前平台算
  const count = (pf, t) => items.reduce((s, r) => s + (!pf || r.platforms.includes(pf) ? r.changes.filter((c) => !t || c.type === t).length : 0), 0);
  $$('[data-filter="pf"] button').forEach((b) => { const k = count(b.dataset.v, state.t); $("i", b).textContent = k; b.disabled = !k && b.dataset.v !== state.pf; });
  $$('[data-filter="t"] button').forEach((b) => { const k = count(state.pf, b.dataset.v); $("i", b).textContent = k; b.disabled = !k && b.dataset.v !== state.t; });
  $$("[data-filter]").forEach((g) => $$("button", g).forEach((b) => b.setAttribute("aria-checked", String(b.dataset.v === state[g.dataset.filter]))));
  if (push) {
    const q = new URLSearchParams();
    if (state.pf) q.set("pf", state.pf);
    if (state.t) q.set("t", state.t);
    history.replaceState(null, "", location.pathname + (q.toString() ? "?" + q : "") + location.hash);
  }
  return { shownRel, shownChg };
}

function stats() {
  const total = items.reduce((s, r) => s + r.changes.length, 0), latest = fmtDate(items[0].date);
  const set = (k, v, small) => { const dd = $(`[data-stat="${k}"]`); dd.textContent = v; if (small) dd.append(el("small", "", small)); };
  set("releases", String(items.length), "个");
  set("changes", String(total), "项");
  set("latest", latest.short);
}

/* 筛选：点选；方向键在一组里移动（radiogroup 的键盘习惯） */
$$("[data-filter]").forEach((g) => {
  g.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b || b.disabled) return; state[g.dataset.filter] = b.dataset.v; apply(); });
  g.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const bs = $$("button:not([disabled])", g), i = bs.findIndex((b) => b.dataset.v === state[g.dataset.filter]);
    const nb = bs[(i + (e.key === "ArrowRight" ? 1 : -1) + bs.length) % bs.length];
    if (nb) { state[g.dataset.filter] = nb.dataset.v; apply(); nb.focus(); e.preventDefault(); }
  });
});

/* 版本头吸顶的位置要让开筛选条：把筛选条的实际高度写进 --bar（换行时会变高） */
const syncBar = () => d.documentElement.style.setProperty("--bar", bar.offsetHeight + "px");
new ResizeObserver(syncBar).observe(bar); syncBar();

(async () => {
  try {
    const r = await fetch("assets/data/changelog.json", { cache: "no-cache" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    items = (await r.json()).items || [];
    if (!items.length) throw new Error("空");
  } catch (e) {
    empty.textContent = "更新日志暂时没加载出来，请稍后刷新再试。";
    empty.hidden = false;
    return;
  }
  const q = new URLSearchParams(location.search);
  if (PF[q.get("pf")]) state.pf = q.get("pf");
  if (TYPE[q.get("t")]) state.t = q.get("t");
  render(); stats(); apply(false);
  if (location.hash) { const t = d.getElementById(decodeURIComponent(location.hash.slice(1))); if (t) t.scrollIntoView(); }
  window.__clReady = true;
})();

/* 自检（截图脚本调用）：渲染数、当前可见数、横向滚动、文字是否被截断 */
window.__cl = () => {
  const vis = $$(".rel:not([hidden])", list);
  const clipped = $$(".rel__c li:not([hidden]) span:last-child, .rel__v, .seg button").filter((e) => e.scrollWidth > e.clientWidth + 1).length;
  return { releases: items.length, changes: items.reduce((s, r) => s + r.changes.length, 0), shown: vis.length, shownChanges: $$(".rel__c li:not([hidden])", list).length,
    hScroll: d.documentElement.scrollWidth > innerWidth, clipped, errs: window.__errs };
};
