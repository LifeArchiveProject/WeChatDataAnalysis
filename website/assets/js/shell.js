/* 官网各页共用的外壳：导航（滚动后实色底、手机菜单）、主题（浅 / 深）。
   首页（main.js）与更新日志页（changelog.js）都调 initShell()；首页自己的「当前区块下划线」（滚动监听）留在 main.js。 */

const d = document;
const $ = (s, r = d) => r.querySelector(s);
const $$ = (s, r = d) => [...r.querySelectorAll(s)];
const store = (s) => ({
  get(k) { try { return s().getItem(k); } catch (e) { return null; } },
  set(k, v) { try { s().setItem(k, v); } catch (e) { /* 隐私模式等情况下写不进去就算了 */ } },
});
const local = store(() => localStorage);

/* ═════════ 导航：滚动后实色底 + 细线，手机菜单（Esc、点菜单里的链接、窗口放宽到 900 以上都会收起） ═════════ */
function initNav() {
  const nav = $("#nav"), menu = $("#menu"), menuBtn = $(".nav__menu");
  if (!nav) return;
  let solid = null;
  const onScroll = () => { const s = scrollY > 4; if (s !== solid) { solid = s; nav.classList.toggle("is-solid", s); } };
  addEventListener("scroll", onScroll, { passive: true }); onScroll();
  const intro = $(".hero, .cl-head");
  if (intro) new IntersectionObserver(([entry]) => {
    nav.classList.toggle("has-contact", !entry.isIntersecting && entry.boundingClientRect.bottom <= 0);
  }).observe(intro);
  if (!menu || !menuBtn) return;
  let menuT = 0;
  function setMenu(open) {
    clearTimeout(menuT);
    menuBtn.setAttribute("aria-expanded", String(open));
    menuBtn.setAttribute("aria-label", open ? "关闭菜单" : "打开菜单");
    d.body.classList.toggle("is-locked", open);
    if (open) { menu.hidden = false; requestAnimationFrame(() => nav.classList.add("is-open")); }
    else { nav.classList.remove("is-open"); menuT = setTimeout(() => { menu.hidden = true; }, 300); }
  }
  menuBtn.addEventListener("click", () => setMenu(menuBtn.getAttribute("aria-expanded") !== "true"));
  menu.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
  addEventListener("resize", () => { if (innerWidth > 900 && nav.classList.contains("is-open")) setMenu(false); });
  d.addEventListener("keydown", (e) => { if (e.key === "Escape" && nav.classList.contains("is-open")) setMenu(false); });
}

/* ═════════ 主题：浅色 / 深色（样式见 main.css「深色模式：变量」） ═════════
   首帧前页面 <head> 的内联脚本已按「记住的选择 → 系统设置」定好 <html data-theme>，并同步了 meta theme-color / color-scheme。这里只管：
   - 点击：导航上的主题按钮（>900）与手机菜单里的「深色模式」开关（≤900），都带 data-theme-toggle；在浅 / 深之间切换并记住
     （localStorage 键 wda.theme：light | dark；没有值 = 跟随系统）。读写都走 local（包了 try/catch），读不到就跟随系统。
   - 跟随系统：没手动选过时，系统外观一变就跟着变；别的标签页改了选择（storage 事件）也跟着变。
   - 切换那一下给 <html> 挂 .is-theming（全站 transition: none），强制算一次样式、下一帧再摘掉：各处颜色直接到位，不一块块慢慢渐变。
   - 主题按钮的 aria-label（「切换到深色模式」/「切换到浅色模式」）、菜单开关的 aria-checked 随状态更新；图标由 CSS 按 data-theme 换。
   - 真的换了主题时在 document 上发 wda:theme 事件（detail = "light" | "dark"）：画在 canvas 上、颜色跟主题走的模块听它重画。 */
function initTheme() {
  const KEY = "wda.theme", root = d.documentElement, sys = matchMedia("(prefers-color-scheme: dark)");
  const META = { light: "#f4f4f7", dark: "#0c0e18" };
  const toggles = $$("[data-theme-toggle]");
  const saved = () => { const v = local.get(KEY); return v === "light" || v === "dark" ? v : null; };
  const want = () => saved() || (sys.matches ? "dark" : "light");
  const cur = () => (root.dataset.theme === "dark" ? "dark" : "light");
  let unfreeze = 0;
  const sync = () => {
    const t = cur(), dark = t === "dark";
    toggles.forEach((b) => {
      if (b.getAttribute("role") === "switch") b.setAttribute("aria-checked", String(dark));
      else b.setAttribute("aria-label", dark ? "切换到浅色模式" : "切换到深色模式");
    });
    const tc = $('meta[name="theme-color"]'), cs = $('meta[name="color-scheme"]');
    if (tc) tc.setAttribute("content", META[t]);
    if (cs) cs.setAttribute("content", t);
  };
  function apply(t) {
    if (root.dataset.theme === t) { sync(); return; }
    root.classList.add("is-theming");
    root.dataset.theme = t;
    void d.body.offsetHeight; // 在 transition 关掉的状态下把新颜色算完，摘掉 .is-theming 时就没有可补间的变化了
    cancelAnimationFrame(unfreeze);
    unfreeze = requestAnimationFrame(() => { unfreeze = 0; root.classList.remove("is-theming"); });
    sync();
    d.dispatchEvent(new CustomEvent("wda:theme", { detail: t }));
  }
  toggles.forEach((b) => b.addEventListener("click", () => { const t = cur() === "dark" ? "light" : "dark"; local.set(KEY, t); apply(t); }));
  sys.addEventListener("change", () => { if (!saved()) apply(want()); });
  addEventListener("storage", (e) => { if (e.key === KEY || e.key === null) apply(want()); });
  apply(want()); // 内联脚本跑成了（通常如此）这里只同步按钮状态与 meta；万一没跑成就在这里补上
}

export function initShell() {
  initNav();
  initTheme();
}
