/* 权益对比 · 双卡对照（正常留白，表头吸顶）。
   版式全部交给 CSS（main.css「权益对比」一节）：固定、舒展的字号与行距，区块高度随内容自然增长，没有按视口压缩的求解。
   这里只做五件事：
   1. 把每组全部条目名（data.js 的 PRO_GROUPS，由 tools/dev/sync-site-catalog.mjs 从 frontend/lib/pro-demos/catalog.js 生成）
      填进高级版卡对应的 data-items 列表，一行一个；页面上写死的各组条数若和条目数对不上，以条目数为准改写。
   2. 卡顶的扭索纹圆环（canvas，照开场卡 card.js 的 46 圈公式与线宽比例），大小跟着 CSS 里的全息章直径走。
   3. 吸顶卡头：卡头正上方一个零高度哨兵判断卡头是否已经吸住（is-stuck，只改细线颜色）；表格末尾另一个零高度哨兵判断
      卡头下面是否只剩不到 120px 表格（is-gone，淡出上移到导航后面）——卡头的包含块是整张表格，子网格没法只给前几行套吸顶容器，
      不这样做的话，在 1440×900 这类视口里滚到底（点「免费试用」「获取」跳 #get 正好停在最大滚动位置）卡头会孤零零悬在获取区上方。
      两个都只切类，不改尺寸，不抖动。
   4. 「只看差异」：收起 / 展开「两版都有」那一段——在眼前就补间高度，不在眼前就直接切换并补偿滚动位置，眼前的内容不跳。
   5. 入场淡入与扫光、卡顶跟手转一点；以及截图脚本用的自检。
   滚动时不做任何事（没有滚动监听）。 */
import { PRO_GROUPS } from "./data.js";
const PRO_TOTAL = Object.values(PRO_GROUPS).reduce((n, g) => n + g.items.length, 0);

const d = document;
const $ = (s, r = d) => r.querySelector(s);
const $$ = (s, r = d) => [...r.querySelectorAll(s)];
const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const phone = matchMedia("(max-width: 1000px)"); // 单列明细（平板与手机），与 main.css 的断点一致
const GONE = 120; // 卡头下面剩不到这么多表格时，卡头离开
const navH = () => parseFloat(getComputedStyle(d.documentElement).getPropertyValue("--nav")) || 60;
const shown = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
const ease = "cubic-bezier(.2,.7,.2,1)";
/* 扭索纹：开场卡的 46 圈（半径 236 + 3.1k，叠 9 瓣与 23 瓣两道正弦），章的半径对应 168；整圈最外缘 ≈ 2.414 倍章半径（CSS 里画布边长 = 章直径 × 2.4137 + 6px） */
const RING = 405.5 / 168;

export function initCompare() {
  const sec = $("#compare");
  if (!sec) return;
  const tbl = $("#cmp-tbl", sec), bar = $("#cmp-bar", sec), duo = $("#cmp-duo", sec), pin = $(".cmp__pin", sec), end = $(".cmp__end", sec);
  const hero = $(".r--hero .r__p", duo), rose = $(".vc__rose", hero), seal = $(".vc__seal", hero), proFace = $(".vc--pro", duo);
  const both = $(".r--both", duo), sws = $$("[data-diff]", sec);

  /* ═════════ 1. 条目：一行一个，条数以 catalog 为准 ═════════ */
  $$("[data-items]", duo).forEach((ul) => {
    const g = PRO_GROUPS[ul.dataset.items];
    if (!g) return;
    const f = d.createDocumentFragment();
    g.items.forEach((it) => { const li = d.createElement("li"); li.textContent = it.name; f.appendChild(li); });
    ul.replaceChildren(f);
    ul.setAttribute("aria-label", `${g.label}：${g.items.length} 项`);
  });
  $$("[data-pro-count]", duo).forEach((c) => { const g = PRO_GROUPS[c.dataset.proCount]; if (g && c.textContent.trim() !== String(g.items.length)) c.textContent = String(g.items.length); });

  /* ═════════ 2. 扭索纹圆环：照开场卡的 46 圈公式，线宽与章的比例也照它（1.5 : 168），每 1° 一段；只在章的大小或像素比变了时重画 ═════════ */
  let roseKey = "";
  function drawRose() {
    const sd = seal.offsetWidth, size = rose.offsetWidth;
    if (!sd || !size) return;
    const dark = d.documentElement.dataset.theme === "dark";
    const dpr = Math.min(devicePixelRatio || 1, 2.5), key = `${sd}|${size}|${dpr}|${dark}`;
    if (key === roseKey) return;
    roseKey = key;
    const k = sd / 2 / 168;
    rose.width = Math.round(size * dpr); rose.height = Math.round(size * dpr);
    const x = rose.getContext("2d");
    x.setTransform(dpr * k, 0, 0, dpr * k, rose.width / 2, rose.height / 2);
    x.lineWidth = Math.max(1.5, .55 / (dpr * k));
    x.lineJoin = "round";
    // 深色卡面上换成提亮的同三色（冰蓝 · 薰衣草 · 蜜桃），透明度相当：浅色那组中间调压在深底上发灰
    const cols = dark ? ["rgba(110,180,255,.36)", "rgba(160,135,255,.36)", "rgba(255,170,130,.3)"] : ["rgba(140,190,240,.3)", "rgba(170,150,240,.29)", "rgba(240,170,120,.27)"];
    for (let i = 0; i < 46; i++) {
      x.beginPath();
      for (let s = 0; s <= 360; s++) {
        const a = s * Math.PI / 180, r = 236 + i * 3.1 + 22 * Math.sin(9 * a + i * .16) + 8 * Math.sin(23 * a - i * .3);
        s ? x.lineTo(r * Math.cos(a), r * Math.sin(a)) : x.moveTo(r, 0);
      }
      x.closePath(); x.strokeStyle = cols[i % 3]; x.stroke();
    }
  }
  drawRose();

  /* ═════════ 3. 吸顶卡头 ═════════
     is-stuck：卡头正上方的哨兵滑到导航下沿以上 = 卡头吸住了。
     is-gone：表格末尾的哨兵升过「导航下沿 + 卡头高 + 120px」这条线 = 卡头下面只剩不到 120px 表格，卡头淡出上移；哨兵回到线下就回来。
     卡头高度用 offsetHeight（is-gone 只动 transform，不影响它）；导航高或卡头高变了（断点切换、换行）才重建观察器。
     观察区的下沿往下放出 BELOW（远大于整页高）：观察区 = 「那条线以下的整片」，哨兵在线下就算相交、在线上就不相交。
     这样一次跳很远（点锚点、按 End、滚到底）也必然跨过观察区的边、触发回调——观察区若只到视口底，哨兵从视口下方直接跳到线上方时
     前后都是「不相交」，观察器不会通知，类就切不过来。 */
  const BELOW = 100000;
  let io = null, ioEnd = null, ioKey = "";
  function watchStuck() {
    const n = Math.round(navH()), line = n + Math.round(bar.offsetHeight) + GONE, key = `${n}|${line}`;
    if (io && key === ioKey) return;
    if (io) { io.disconnect(); ioEnd.disconnect(); }
    ioKey = key;
    io = new IntersectionObserver(([e]) => bar.classList.toggle("is-stuck", !e.isIntersecting && e.boundingClientRect.top < n + 1), { rootMargin: `-${n + 1}px 0px ${BELOW}px 0px`, threshold: 0 });
    io.observe(pin);
    ioEnd = new IntersectionObserver(([e]) => bar.classList.toggle("is-gone", !e.isIntersecting && e.boundingClientRect.top < line), { rootMargin: `-${line}px 0px ${BELOW}px 0px`, threshold: 0 });
    ioEnd.observe(end);
  }
  watchStuck();

  let rt = 0;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { drawRose(); watchStuck(); }, 120); });
  if (d.fonts) d.fonts.ready.then(() => { drawRose(); watchStuck(); });
  d.addEventListener("wda:theme", drawRose); // 换主题（main.js 第 6b 节派发）：圆环按新卡面重画

  /* ═════════ 4. 只看差异 ═════════ */
  let busy = false;
  // 卡头下面第一行还看得见的行（「两版都有」以外），切换前后让它停在原处
  const anchorRow = () => { const top = bar.getBoundingClientRect().bottom; return $$(".r", duo).find((r) => r !== both && r.getBoundingClientRect().bottom > top + 1); };
  async function setDiff(on) {
    if (busy || duo.classList.contains("is-diff") === on) return;
    busy = true;
    sws.forEach((b) => b.setAttribute("aria-checked", String(on)));
    const barB = bar.getBoundingClientRect().bottom;
    // 这一段（收起时是它本身，展开时是它将出现的位置 = 下一行的上沿）是不是已经滚过去了、或者还没滚到
    const ref = on ? both.getBoundingClientRect() : both.nextElementSibling.getBoundingClientRect();
    const passed = on ? ref.bottom <= barB + 1 : ref.top < barB, ahead = ref.top >= innerHeight;
    if (reduce.matches || passed || ahead) {
      const a = passed ? anchorRow() : null, t0 = a ? a.getBoundingClientRect().top : 0;
      duo.classList.toggle("is-diff", on);
      if (a) { const dy = a.getBoundingClientRect().top - t0; if (Math.abs(dy) > .5) scrollBy({ top: dy, behavior: "instant" }); }
      busy = false;
      return;
    }
    // 在眼前：先淡出再收拢高度（展开反过来），下面的行跟着平滑移动
    if (!on) duo.classList.remove("is-diff");
    const h = both.offsetHeight;
    both.classList.add("is-anim");
    const k = on
      ? [{ height: `${h}px`, opacity: 1 }, { opacity: 0, offset: .35 }, { height: "0px", opacity: 0 }]
      : [{ height: "0px", opacity: 0 }, { opacity: 0, offset: .45 }, { height: `${h}px`, opacity: 1 }];
    const an = both.animate(k, { duration: 460, easing: ease, fill: "forwards" });
    await an.finished.catch(() => {});
    if (on) duo.classList.add("is-diff");
    both.classList.remove("is-anim");
    an.cancel();
    busy = false;
  }
  sws.forEach((b) => b.addEventListener("click", () => setDiff(b.getAttribute("aria-checked") !== "true")));

  /* ═════════ 5. 入场：滚到眼前表格淡入、高级版卡上段扫过一道光（已在视口里就不演）；卡顶跟手：全息章与圆环转一点 ═════════ */
  if (sec.getBoundingClientRect().top > innerHeight && !reduce.matches) sec.classList.add("is-pre");
  new IntersectionObserver((es, o) => {
    if (!es[0].isIntersecting) return;
    o.disconnect();
    sec.classList.remove("is-pre");
    if (!reduce.matches) proFace.classList.add("is-shine");
  }, { rootMargin: "0px 0px -15% 0px" }).observe(tbl);
  let fr = 0, pe = null;
  hero.addEventListener("pointermove", (e) => {
    if (reduce.matches || e.pointerType !== "mouse") return;
    pe = e; if (fr) return;
    fr = requestAnimationFrame(() => {
      fr = 0;
      const r = hero.getBoundingClientRect(), x = (pe.clientX - r.left) / r.width - .5, y = (pe.clientY - r.top) / r.height - .5;
      hero.style.setProperty("--sr", `${(x * 70 - y * 30).toFixed(1)}deg`);
    });
  });
  hero.addEventListener("pointerleave", () => hero.style.setProperty("--sr", "0deg"));

  /* ═════════ 6. 自检（截图脚本调用） ═════════ */
  const glyphs = (root) => {
    const out = [], rg = d.createRange(), tw = d.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue.trim() && !n.parentElement.closest(".lab, .vh, [aria-hidden=true]") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT) });
    for (let n = tw.nextNode(); n; n = tw.nextNode()) { rg.selectNodeContents(n); for (const r of rg.getClientRects()) if (r.width > .5 && r.height > .5) out.push({ r, el: n.parentElement, t: n.nodeValue.trim() }); }
    return out;
  };
  const hit = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  window.__cmp = () => {
    const W = innerWidth, mob = phone.matches, sr = sec.getBoundingClientRect(), tr = tbl.getBoundingClientRect();
    const out = { viewport: `${W}x${innerHeight}`, 形态: mob ? "单列明细" : "双卡对照", hScroll: d.documentElement.scrollWidth > W, h1: $$("h1").length, errors: (window.__errs || []).slice() };
    out.区块总高 = `${Math.round(sr.height)}px（${(sr.height / innerHeight).toFixed(2)} 屏）`;
    out.表格高 = Math.round(tr.height);
    // 字号与行高
    const cs = (el) => getComputedStyle(el), lis = $$(".p__its li", duo);
    const li = lis[0], fs = (el) => parseFloat(cs(el).fontSize), lh = (el) => parseFloat(cs(el).lineHeight);
    out.条目 = `${lis.filter(shown).length}/${PRO_TOTAL} · ${fs(li)}px / 行高 ${lh(li).toFixed(1)}px（${(lh(li) / fs(li)).toFixed(2)}）`;
    out.组名 = `${fs($(".r--g .p__n", duo))}px`;
    out.条数大字 = `${fs($(".r--g .p__c", duo)).toFixed(1)}px`;
    let fmin = Infinity, fminAt = "", lmin = Infinity, lminAt = "";
    glyphs(sec).forEach(({ el, t }) => {
      const f = fs(el); if (f < fmin) { fmin = f; fminAt = t.slice(0, 8); }
      // 正文 = 会折行的文字：条目、两版说明、普通版说明、组说明与风险边界、体验与平台说明、卡脚
      const body = el.closest(".p__its li, .p__defs div, .f__d, .p__d, .r--foot p");
      const l = body ? lh(body) / fs(body) : NaN; if (!isNaN(l) && l < lmin) { lmin = l; lminAt = t.slice(0, 8); }
    });
    out.最小字号 = `${fmin}px（${fminAt}）`;
    out.正文最小行距 = `${lmin.toFixed(2)}（${lminAt}）`;
    // 各组条目栏数（按每个条目的左边位置去重）
    out.各组栏数 = $$(".p__its", duo).map((u) => `${u.dataset.items} ${new Set($$("li", u).map((x) => Math.round(x.getBoundingClientRect().left))).size}栏/${$$("li", u).length}`).join(" · ");
    // 条目全部直接可见：不截断、不出卡、没有被折叠
    const clipped = lis.filter((x) => x.scrollWidth > x.clientWidth + 1 || !shown(x));
    out.条目截断或隐藏 = clipped.length ? `FAIL ${clipped.map((x) => x.textContent).join("/")}` : "OK 0";
    // 没有浮层 / 弹框 / 抽屉 / 点击展开
    const pops = $$('[role="dialog"], details, [aria-expanded], [hidden]', sec);
    out.浮层与折叠 = pops.length ? `FAIL ${pops.length}` : "OK 无";
    // 两卡逐行对齐（桌面）
    if (!mob) {
      const rows = $$(".r", duo).filter(shown), bad = rows.filter((r) => { const a = $(":scope > .r__f", r).getBoundingClientRect(), b = $(":scope > .r__p", r).getBoundingClientRect(); return Math.abs(a.top - b.top) > .5 || Math.abs(a.height - b.height) > .5; });
      out.逐行对齐 = bad.length ? `FAIL ${bad.length}` : `OK ${rows.length} 行`;
      // 吸顶卡头两格与下面两卡同列宽
      const cf = $(".cb--free", bar).getBoundingClientRect(), cp = $(".cb--pro", bar).getBoundingClientRect(), vf = $(".vc--free", duo).getBoundingClientRect(), vp = proFace.getBoundingClientRect();
      const dx = Math.max(Math.abs(cf.left - vf.left), Math.abs(cf.right - vf.right), Math.abs(cp.left + 1 - vp.left), Math.abs(cp.right - 1 - vp.right));
      out.卡头列宽 = `${dx < 1 ? "OK" : "FAIL"} 偏差 ${dx.toFixed(1)}px`;
      // 卡头每一格的内容（名称、标签、图例、开关、按钮）都在格子的内边距以内
      const spill = $$(".cb", bar).map((c) => {
        const r = c.getBoundingClientRect(), s = cs(c), l = r.left + parseFloat(s.paddingLeft) + parseFloat(s.borderLeftWidth), rr = r.right - parseFloat(s.paddingRight) - parseFloat(s.borderRightWidth);
        const ks = [...c.children].filter((k) => shown(k) && cs(k).position !== "absolute").map((k) => k.getBoundingClientRect());
        return Math.max(0, ...ks.map((k) => Math.max(k.right - rr, l - k.left)));
      });
      out.卡头格内 = Math.max(...spill) > .5 ? `FAIL 普通版 ${spill[0].toFixed(1)} / 高级版 ${spill[1].toFixed(1)}px 挤进内边距` : "OK";
    }
    // 卡头里该有的都在
    // 手机上卡头只有两个按钮（按钮里写着普通版 / 高级版）+ 图例，「只看差异」在标题行
    const need = mob
      ? { 普通版免费下载: $(".cb--free .btn", bar), 高级版免费试用: $(".cb--pro .btn", bar), 图例: $(".cmp__legend", bar), 只看差异: $(".cmp__sw--m", sec) }
      : { 普通版: $(".cb--free .cb__n", bar), 免费下载: $(".cb--free .btn", bar), 高级版: $(".cb--pro .cb__n", bar), 免费试用: $(".cb--pro .btn", bar), 图例: $(".cmp__legend", bar), 只看差异: $(".cb .cmp__sw", bar) };
    out.卡头内容 = Object.entries(need).map(([k, el]) => `${k}${shown(el) ? "" : "×"}`).join(" ");
    const br = bar.getBoundingClientRect();
    out.卡头 = `top ${Math.round(br.top)}（导航 ${navH()}）高 ${Math.round(br.height)} ${bar.classList.contains("is-stuck") ? "吸住" : "未吸"}`;
    // 卡顶装饰：77、全息章、扭索纹圆环不压任何字，也不出卡顶这一行
    const hr = hero.getBoundingClientRect(), txt = glyphs(duo).filter(({ el }) => !el.closest(".vc__big"));
    const big = $(".vc__big b", hero).getBoundingClientRect(), bigHit = txt.filter(({ r }) => hit(r, big));
    if (!shown(seal)) {
      // 极窄屏（≤350）卡顶放不下扭索纹圆环与全息章，CSS 不显示它们；只核对 77 不压字
      out.卡顶装饰 = `${bigHit.length ? "FAIL 大字压字" : "OK"} 大字 ${Math.round(parseFloat(cs($(".vc__big b", hero)).fontSize))}px · 圆环与全息章本宽度不显示`;
    } else {
      const sd = seal.getBoundingClientRect(), ro = rose.getBoundingClientRect();
      const cx = (sd.left + sd.right) / 2, cy = (sd.top + sd.bottom) / 2, R = RING * sd.width / 2;
      const ringHit = txt.filter(({ r }) => Math.hypot(Math.max(r.left - cx, 0, cx - r.right), Math.max(r.top - cy, 0, cy - r.bottom)) < R + 4);
      const inHero = ro.width > 0 && cy - R >= hr.top - .5 && cy + R <= hr.bottom + .5 && cx + R <= hr.right + .5 && cx - R >= hr.left - .5;
      out.卡顶装饰 = `${!ringHit.length && !bigHit.length && inHero ? "OK" : "FAIL"} 大字 ${Math.round(parseFloat(cs($(".vc__big b", hero)).fontSize))}px · 章 ${Math.round(sd.width)}px · 圆环外径 ${Math.round(2 * R)}px 离最近的字 ${Math.round(Math.min(...txt.map(({ r }) => Math.hypot(Math.max(r.left - cx, 0, cx - r.right), Math.max(r.top - cy, 0, cy - r.bottom)))) - R)}px${ringHit.length ? " 压字:" + ringHit.map((x) => x.t.slice(0, 6)).join("/") : ""}${bigHit.length ? " 77压字" : ""}${inHero ? "" : " 出卡顶"}`;
    }
    // 卡头（含图例）不伸进页面左右槽宽：子元素都在 .wrap 的内容范围里
    const wr = tbl.getBoundingClientRect(), barKids = $$(".cb > *, .cmp__legend", bar).filter(shown).map((x) => x.getBoundingClientRect());
    const over = Math.max(0, ...barKids.map((r) => Math.max(r.right - wr.right, wr.left - r.left)));
    out.卡头不出槽 = over > .5 ? `FAIL 伸出 ${over.toFixed(1)}px` : "OK";
    out.只看差异 = sws[0].getAttribute("aria-checked") === "true" ? "开" : "关";
    out.全部通过 = !out.hScroll && !out.errors.length && out.h1 === 1 && lis.filter(shown).length === PRO_TOTAL && !clipped.length && !pops.length && (mob || (out.逐行对齐.startsWith("OK") && out.卡头列宽.startsWith("OK") && out.卡头格内.startsWith("OK"))) && out.卡顶装饰.startsWith("OK") && out.卡头不出槽 === "OK" && !out.卡头内容.includes("×");
    return out;
  };
  // 吸顶记录：从表格进入视口一直滚到页面最大滚动位置，按步长滚动（每步等两帧，让观察器的类先切好），记下卡头上沿相对导航下沿的位置。
  // 每一步都断言：卡头要么已离开（is-gone），要么下面至少还有 120px 表格；卡头不盖住获取区。最后在最大滚动位置再等过渡结束，确认卡头已经看不见。
  const frames2 = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  window.__cmpStick = async (step = 0) => {
    const y0 = scrollY, n = navH(), maxY = d.documentElement.scrollHeight - innerHeight, st = step || Math.round(tbl.offsetHeight / 14);
    const ys = [];
    for (let y = Math.max(0, Math.round(tr0() - innerHeight * .5)); y < maxY; y += st) ys.push(y);
    ys.push(maxY);
    const rows = [];
    let bad = 0;
    // 先停在起点等卡头的过渡走完（上一次停在页底时卡头是离开状态），记录的就只是滚动本身
    scrollTo({ top: ys[0], behavior: "instant" });
    await new Promise((r) => setTimeout(r, 320));
    for (const y of ys) {
      scrollTo({ top: y, behavior: "instant" });
      await frames2();
      const b = bar.getBoundingClientRect(), t = tbl.getBoundingClientRect(), g = $("#get").getBoundingClientRect(), gone = bar.classList.contains("is-gone"), below = t.bottom - b.bottom;
      const ok = (gone || below >= GONE - .5) && (gone || b.bottom <= g.top + .5);
      if (!ok) bad++;
      rows.push(`y=${Math.round(scrollY)}${scrollY >= maxY - .5 ? "（最大）" : ""} 卡头上沿-导航=${(b.top - n).toFixed(1)} 卡头下表格=${Math.round(below)} 表格底=${Math.round(t.bottom)} 获取区顶=${Math.round(g.top)} ${gone ? "已离开" : bar.classList.contains("is-stuck") ? "吸住" : "未吸"}${ok ? "" : " ✗"}`);
    }
    // 最大滚动位置：等过渡走完，卡头要么真的看不见了（opacity 0），要么下面还有 ≥120px 表格（高视口里滚到底也还在表格中段）
    await new Promise((r) => setTimeout(r, 320));
    const o = parseFloat(getComputedStyle(bar).opacity), bb = bar.getBoundingClientRect(), left = tbl.getBoundingClientRect().bottom - bb.bottom;
    const endOk = o < .01 || left >= GONE - .5;
    rows.push(`最大滚动位置：卡头${bar.classList.contains("is-gone") ? "已离开" : "仍在"} · opacity ${o} · 卡头下表格 ${Math.round(left)}px ${endOk ? "OK" : "✗"}`);
    rows.push(`断言：${bad || !endOk ? `FAIL ${bad} 处卡头下不足 ${GONE}px 表格却没离开${endOk ? "" : "；最大滚动位置卡头仍可见且下面不足 " + GONE + "px 表格"}` : `OK ${ys.length} 个位置`}`);
    scrollTo({ top: y0, behavior: "instant" });
    return rows;
  };
  const tr0 = () => tbl.getBoundingClientRect().top + scrollY;
  // 逐帧滚动往返：表格上方半屏 → 表格底下 → 回来，每帧滚 px，统计帧间隔（先跳到起点、等两帧再开始计，跳转本身不算逐帧滚动）
  window.__cmpFrames = (px = 36) => new Promise((res) => {
    const a = Math.max(0, Math.round(tr0() - innerHeight / 2)), b = Math.round(tr0() + tbl.offsetHeight + 200);
    let y = a, dir = 1, last = 0;
    const gaps = [], long = [];
    scrollTo({ top: a, behavior: "instant" });
    const step = (t) => {
      if (last) { gaps.push(t - last); if (t - last > 50) long.push(`y=${y} ${Math.round(t - last)}ms`); }
      last = t;
      y += dir * px;
      if (y >= b) { y = b; dir = -1; }
      if (dir < 0 && y <= a) { res({ 帧数: gaps.length, 长帧: long.length, 长帧位置: long, 最长: Math.round(Math.max(...gaps)), 平均: +(gaps.reduce((s, g) => s + g, 0) / gaps.length).toFixed(1) }); return; }
      scrollTo({ top: y, behavior: "instant" });
      requestAnimationFrame(step);
    };
    requestAnimationFrame(() => requestAnimationFrame(step));
  });
}
