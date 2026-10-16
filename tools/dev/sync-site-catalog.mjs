#!/usr/bin/env node
/* 官网里高级版 13 组 108 项的唯一来源是 frontend/lib/pro-demos/catalog.js（2026-10-20 上游新增「AI 与 MCP」一组，77 → 79；
   2026-10-21 末尾新增「macOS 取密钥」一组，79 → 80；2026-10-23 补上撤回、分组发送、群设置、直播 / 小程序 / 服务号搜索等，
   「红包」扩成「红包与转账」并挪到「微信动作」之后，另增「视频号与直播」「小程序」两组，80 → 108）。
   官网把这 108 项放在 website/assets/js/data.js 的 PRO_GROUPS 里，由本脚本生成，夹在成对的标记之间：
     /* pro-catalog:start … *\/ … /* pro-catalog:end *\/
   页面（website/assets/js/compare.js）读 PRO_GROUPS，把每组全部条目名一行一个填进权益对比高级版卡该组的条目列表。

   标记之外，页面上还有几处手写的数字与权益对比的行结构，--check 逐个核对（2026-10-20 权益对比改成「正常留白 + 表头吸顶」的双卡对照）：
     - website/index.html 里所有 data-pro-total 元素的文字 = 总数 108，且每个都带 data-pro-at 标明位置；
       下面 WANT_AT 里的每个位置都必须出现：开场卡（hero-card，卡下那行读屏文字；canvas 卡面上的大字就从它取）、开场副标题（hero-sub）、
       权益对比「高级版独有」分组标题（compare）、权益对比高级版卡顶的箔压大字（compare-big）
     - website/index.html 里所有 data-pro-groups 元素的文字 = 组数 13（开场卡的读屏文字、对比普通版卡的分组标题、对比卡顶大字下的「13 组」）
     - website/index.html 里 data-pro-count="<组 key>" 元素的文字 = 该组条数（按数值比，08 = 8），每组恰好一处：
       权益对比该组那一行的条数大字（data-pro-at="compare"）；
       另外，权益对比组说明里提到条数的地方（如「在任意位置补录 17 类消息」）写 data-pro-at="compare-d"，可有可无，有就核对数值
     - 权益对比区块（<section … id="compare">）的结构：.cmp__duo 里每一行 <div class="r r--…"> 同时含普通版一格（r__f）与高级版一格（r__p）；
       r--x 行的 data-i 依次是 catalog 的 13 个组 key 与 e0…e7；另有「两版都有」（data-i="both"）与平台、微信版本两行（v0、v1）；
       13 组每组一个条目列表（data-items="<组 key>"，compare.js 往里一行一个填条目名），顺序与 catalog 一致；各组条数大字之和 = 108；
       行总数 = 28；体验行（r--x r--e）数 = 8，且等于「体验与服务」分组标题（r--sec-e）里两处手写的 <b>N</b>；
       带 data-i 的每一行（两版都有、13 组、体验各项、平台两行），普通版一格都有一句非空短说明（<span class="f__d">）；
       区块里不得有浮层、弹框、抽屉或点击展开（role="dialog"、<details>、aria-expanded、hidden 都不该出现）

   用法：
     node tools/dev/sync-site-catalog.mjs          重新生成 PRO_GROUPS 并写回 data.js
     node tools/dev/sync-site-catalog.mjs --check  只比对：不一致、或数目不是下面的期望值时退出码 1（CI 用）

   断言：总数 108，各组 8 / 17 / 2 / 22 / 4 / 8 / 14 / 11 / 9 / 4 / 5 / 3 / 1。catalog.js 增删条目时这里会先报错——
   先把 index.html 里手写的数字改对，再改 WANT。 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const DATA = resolve(ROOT, "website/assets/js/data.js");
const HTML = resolve(ROOT, "website/index.html");
const CATALOG = resolve(ROOT, "frontend/lib/pro-demos/catalog.js");
const CHECK = process.argv.includes("--check");
const WANT_AT = ["hero-card", "hero-sub", "compare", "compare-big"];

const WANT_TOTAL = 108;
const WANT = { edit: 8, add: 17, "ai-mcp": 2, action: 22, "red-packet": 4, moments: 8, group: 14, contact: 11, search: 9, finder: 4, miniapp: 5, automation: 3, "mac-key": 1 };

// 名字相近、容易和普通版混淆的条目，补一句辨析（按 catalog 的 key；中间插了条目，全局 index 会变）
const AFTER = {
  "receive-messages": "和普通版的「实时同步」不是一回事：普通版读本机数据库；这一项登录后分页补齐消息，再继续接收新消息。",
  "sns-autorefresh": "和普通版的朋友圈浏览不同：这一项刷新最新动态，并沿时间线继续读取历史页。",
};
// 边界用橙色提示的条目（补录的资金类记录，不产生真实资金往来）
const WARN = new Set(["add-transfer", "add-redpacket"]);
// 红包与转账条目（catalog 的 money 字段）：页面给它们换上红包 / 转账的卡片色与图标，只认这两种
const MONEY = new Set(["red-packet", "transfer"]);

const fail = (msg) => { console.error("✗ " + msg); process.exit(1); };

const C = await import(pathToFileURL(CATALOG).href);
if (C.PRO_TOTAL !== WANT_TOTAL) fail(`catalog.js 共 ${C.PRO_TOTAL} 项，期望 ${WANT_TOTAL}`);
const keys = C.PRO_GROUPS.map((g) => g.key);
if (keys.join() !== Object.keys(WANT).join()) fail(`分组顺序 / 名称变了：${keys.join(" ")}`);
for (const g of C.PRO_GROUPS) if (g.items.length !== WANT[g.key]) fail(`分组 ${g.key} 有 ${g.items.length} 项，期望 ${WANT[g.key]}`);
for (const it of C.PRO_ITEMS) if (it.money && !MONEY.has(it.money)) fail(`条目 ${it.key} 的 money 是 ${it.money}，只能写 ${[...MONEY].join(" / ")}`);
for (const k of [...WARN, ...Object.keys(AFTER)]) if (!C.PRO_BY_KEY[k]) fail(`WARN / AFTER 里的 ${k} 不在 catalog 里`);

/* ── 生成 PRO_GROUPS ── */
const J = (v) => JSON.stringify(v);
function block() {
  let s = "/* pro-catalog:start —— 以下由 tools/dev/sync-site-catalog.mjs 生成，别手改 */\nexport const PRO_GROUPS = {\n";
  for (const g of C.PRO_GROUPS) {
    s += `  ${J(g.key)}: { label: ${J(g.label)}, items: [\n`;
    for (const it of g.items) {
      const o = { i: it.index, name: it.name, cap: it.caption };
      if (it.edge) o.edge = it.edge;
      if (WARN.has(it.key)) o.warn = true;
      if (it.money) o.money = it.money;
      if (AFTER[it.key]) o.note = AFTER[it.key];
      s += `    ${J(o).replace(/^\{"i":/, "{ i: ").replace(/,"(\w+)":/g, ", $1: ").replace(/\}$/, " }")},\n`;
    }
    s += "  ] },\n";
  }
  return s + "};\n/* pro-catalog:end */";
}

const src = readFileSync(DATA, "utf8");
const START = "/* pro-catalog:start", END = "/* pro-catalog:end */";
const a = src.indexOf(START), b = src.indexOf(END);
if (a < 0 || b < a || src.indexOf(START, a + 1) >= 0 || src.indexOf(END, b + 1) >= 0) fail("website/assets/js/data.js 里找不到唯一一对 pro-catalog 标记");
const cur = src.slice(a, b + END.length), next = block();
const stale = cur !== next;
const out = src.slice(0, a) + next + src.slice(b + END.length);

/* ── 手写数字核对 ── */
const html = readFileSync(HTML, "utf8");
const bad = [];
// 只认「开标签 + 纯文字 + 闭标签」的元素（SVG 的 <text> 也算），属性逐个解析
const els = [...html.matchAll(/<([a-z][a-z0-9]*)(\s[^>]*)>([^<]*)<\/\1>/g)].map((m) => ({
  attrs: Object.fromEntries([...m[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map((a) => [a[1], a[2] ?? ""])),
  text: m[3].trim(),
}));
const totals = els.filter((e) => "data-pro-total" in e.attrs), groups = els.filter((e) => "data-pro-groups" in e.attrs), counts = els.filter((e) => "data-pro-count" in e.attrs);
const at = new Map();
for (const t of totals) {
  const where = t.attrs["data-pro-at"] || "（没写 data-pro-at）";
  at.set(where, (at.get(where) || 0) + 1);
  if (t.text !== String(C.PRO_TOTAL)) bad.push(`index.html data-pro-total（${where}）写的是 ${t.text}，应为 ${C.PRO_TOTAL}`);
  if (!t.attrs["data-pro-at"]) bad.push(`index.html 有一处 data-pro-total 没写 data-pro-at，文字 ${t.text}`);
}
for (const w of WANT_AT) if (!at.has(w)) bad.push(`index.html 缺少 data-pro-at="${w}" 的总数`);
if (!groups.length) bad.push("index.html 里没有 data-pro-groups");
for (const t of groups) if (t.text !== String(C.PRO_GROUPS.length)) bad.push(`index.html data-pro-groups 写的是 ${t.text}，应为 ${C.PRO_GROUPS.length}`);
const seenAt = { compare: new Map(), "compare-d": new Map() };
for (const t of counts) {
  const k = t.attrs["data-pro-count"], g = C.PRO_GROUPS.find((x) => x.key === k);
  if (!g) { bad.push(`index.html data-pro-count="${k}" 不是 catalog 里的组`); continue; }
  const pa = t.attrs["data-pro-at"], where = pa === "compare" || pa === "compare-d" ? pa : null;
  if (!where) { bad.push(`index.html data-pro-count="${k}" 的 data-pro-at="${pa}" 不认识（只能写 compare / compare-d）`); continue; }
  seenAt[where].set(k, (seenAt[where].get(k) || 0) + 1);
  if (Number(t.text) !== g.items.length) bad.push(`index.html data-pro-count="${g.key}"（${where === "compare" ? "权益对比条数大字" : "权益对比组说明"}）写的是 ${t.text}，应为 ${g.items.length}`);
}
for (const [where, label, ks] of [["compare", "权益对比的条数大字", keys]]) {
  for (const k of ks) {
    const n = seenAt[where].get(k) || 0;
    if (n !== 1) bad.push(`index.html ${label}里 data-pro-count="${k}" 出现 ${n} 次，应为 1 次`);
  }
}
// 权益对比区块的结构
const WANT_ROWS = 28, WANT_E = 8;
let cmpRows = 0, cmpE = 0, cmpFd = 0;
{
  const a = html.search(/<section\b[^>]*\bid="compare"/), b = a < 0 ? -1 : html.indexOf("</section>", a);
  if (a < 0 || b < 0) bad.push("index.html 里找不到权益对比区块（<section … id=\"compare\">）");
  else {
    const cmp = html.slice(a, b);
    const d0 = cmp.indexOf('id="cmp-duo"');
    if (d0 < 0) bad.push("权益对比缺少双卡网格（id=\"cmp-duo\"）");
    if (!/class="cmp__bar"/.test(cmp)) bad.push("权益对比缺少吸顶卡头（class=\"cmp__bar\"）");
    // 逐行切开：每一行从 <div class="r r--…"> 起，到下一行起点为止
    const starts = [...cmp.matchAll(/<div class="r (r--[\w-]+(?: r--[\w-]+)*)"(?: data-i="([\w-]+)")?>/g)];
    const rows = starts.map((m, i) => ({ cls: m[1].split(" "), i: m[2] || "", body: cmp.slice(m.index, i + 1 < starts.length ? starts[i + 1].index : cmp.length) }));
    cmpRows = rows.length;
    for (const r of rows) {
      const f = (r.body.match(/class="r__f"/g) || []).length, p = (r.body.match(/class="r__p"/g) || []).length;
      if (f !== 1 || p !== 1) bad.push(`权益对比的行 ${r.i || r.cls.join(" ")} 应各有一格普通版（r__f）与高级版（r__p），实际 ${f} / ${p}`);
    }
    const wantX = [...keys, ...Array.from({ length: 8 }, (_, i) => `e${i}`)].join(" ");
    const gotX = rows.filter((r) => r.cls.includes("r--x")).map((r) => r.i).join(" ");
    if (gotX !== wantX) bad.push(`权益对比的组与体验行（${gotX || "没找到"}）应依次为 ${wantX}`);
    for (const want of ["both", "v0", "v1"]) if (!rows.some((r) => r.i === want)) bad.push(`权益对比缺少 data-i="${want}" 的行`);
    // 行总数：卡顶 1 + 两版都有 1 + 分组标题 2 + 13 组 + 体验 8 + 平台 2 + 卡脚 1 = 28
    if (rows.length !== WANT_ROWS) bad.push(`权益对比共 ${rows.length} 行，应为 ${WANT_ROWS} 行（卡顶 · 两版都有 · 2 个分组标题 · ${keys.length} 组 · 体验 8 项 · 平台 2 行 · 卡脚）`);
    // 「体验与服务 N 项」：分组标题里两格手写的 N 都要等于实际的体验行数（r--x r--e）
    cmpE = rows.filter((r) => r.cls.includes("r--x") && r.cls.includes("r--e")).length;
    if (cmpE !== WANT_E) bad.push(`权益对比体验与服务有 ${cmpE} 行，应为 ${WANT_E} 行`);
    {
      const sec = rows.filter((r) => r.cls.includes("r--sec-e"));
      if (sec.length !== 1 || !sec[0].body.includes("体验与服务")) bad.push(`权益对比应有且只有一行「体验与服务」分组标题（class 含 r--sec-e），实际 ${sec.length} 行`);
      else {
        const ns = [...sec[0].body.matchAll(/<b>(\d+)<\/b>/g)].map((m) => Number(m[1]));
        if (ns.length !== 2 || ns.some((x) => x !== cmpE)) bad.push(`权益对比「体验与服务」分组标题写的是 ${ns.join(" / ") || "（没找到 <b>数字</b>）"} 项，两格都应为实际体验行数 ${cmpE}`);
      }
    }
    // 两版都有、13 组、体验各项、平台两行：普通版一格都要有一句短说明（f__d，非空）
    for (const r of rows.filter((x) => x.i)) {
      const f = r.body.slice(r.body.indexOf('class="r__f"'), r.body.indexOf('class="r__p"'));
      const m = f.match(/<span class="f__d"[^>]*>([\s\S]*?)<\/span>/);
      if (!m || !m[1].replace(/<[^>]+>|&nbsp;/g, "").trim()) bad.push(`权益对比「${r.i}」那一行的普通版一格没有短说明（<span class="f__d">）`);
      else cmpFd++;
    }
    for (const k of keys) {
      const r = rows.find((x) => x.i === k);
      if (!r) continue;
      if (!r.body.includes(`data-items="${k}"`)) bad.push(`权益对比「${k}」那一行没有条目列表（data-items="${k}"）`);
      if (!new RegExp(`data-pro-count="${k}" data-pro-at="compare"`).test(r.body)) bad.push(`权益对比「${k}」那一行没有条数大字（data-pro-count="${k}" data-pro-at="compare"）`);
    }
    const order = [...cmp.matchAll(/data-pro-count="([\w-]+)" data-pro-at="compare"/g)].map((m) => m[1]).join(" ");
    if (order !== keys.join(" ")) bad.push(`权益对比的条数顺序（${order}）与 catalog 不一致`);
    const boxes = [...cmp.matchAll(/data-items="([\w-]+)"/g)].map((m) => m[1]).join(" ");
    if (boxes !== keys.join(" ")) bad.push(`权益对比的条目列表（data-items：${boxes || "没找到"}）应依次为 ${keys.join(" ")}`);
    const sum = [...cmp.matchAll(/data-pro-count="[\w-]+" data-pro-at="compare"[^>]*>(\d+)</g)].reduce((n, m) => n + Number(m[1]), 0);
    if (sum !== C.PRO_TOTAL) bad.push(`权益对比各组条数大字之和是 ${sum}，应为 ${C.PRO_TOTAL}`);
    const folds = [...cmp.matchAll(/role="dialog"|<details\b|aria-expanded|\shidden[\s>=]/g)].map((m) => m[0].trim());
    if (folds.length) bad.push(`权益对比里不该有浮层或折叠：${[...new Set(folds)].join("、")}`);
  }
}
if (bad.length) fail("手写数字与 catalog.js 不一致：\n  " + bad.join("\n  "));

if (CHECK) {
  if (stale) fail(`官网 ${C.PRO_TOTAL} 项（website/assets/js/data.js 的 PRO_GROUPS）与 catalog.js 不一致。运行 node tools/dev/sync-site-catalog.mjs 重新生成。`);
  console.log(`✓ 官网 ${C.PRO_TOTAL} 项与 catalog.js 一致（${C.PRO_GROUPS.map((g) => `${g.key} ${g.items.length}`).join(" · ")}）`);
  console.log(`✓ 页面上的 ${C.PRO_TOTAL}：${[...at].map(([w, n]) => `${w}×${n}`).join(" · ")}；${keys.length} 组 ×${groups.length}；分组条数 ${counts.length} 处（权益对比条数大字 ${seenAt.compare.size} 组 · 组说明 ${seenAt["compare-d"].size} 处）`);
  console.log(`✓ 权益对比：${cmpRows} 行，每行两格齐全；${C.PRO_GROUPS.length} 组顺序、条目列表与 catalog 一致，条数之和 ${C.PRO_TOTAL}；体验与服务 ${cmpE} 行 = 分组标题两处手写数；普通版短说明 ${cmpFd} 处齐全；无浮层与折叠`);
} else if (stale) {
  writeFileSync(DATA, out);
  console.log("✓ 已更新 website/assets/js/data.js 的 PRO_GROUPS");
} else {
  console.log("✓ 已是最新，无需改动");
}
