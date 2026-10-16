#!/usr/bin/env node
/* 官网「更新日志」页的数据：高级版每次发布的变化（版本、日期、平台、新增 / 优化 / 修复）。
   来源是高级版应用左侧「更新日志」用的那份已发布记录（只有已发布的版本，不含未归档的草稿），由下面两种方式之一取得：
     - 环境变量 CHANGELOG_URL：发布接口的地址（返回 { items: [...] }）。地址不写进仓库——官网部署流程从仓库机密 secrets.CHANGELOG_URL 传进来；
     - --file <路径>：一份本地的 release-notes.json（取其中的 releases；pending 草稿不会上官网）。
   写到 website/assets/data/changelog.json（{ items }，新的在前）与 changelog-latest.json（首页「最近更新」只要最新一条的版本与日期）。
   这两个文件也提交在仓库里当快照：部署时取不到新数据，就用快照上线，页面不会空。

   用法：
     CHANGELOG_URL=… node tools/dev/sync-site-changelog.mjs          取最新数据，校验后写快照
     node tools/dev/sync-site-changelog.mjs --file …/release-notes.json
     node tools/dev/sync-site-changelog.mjs --soft                   取不到或校验不过时只告警、保留现有快照，退出码 0（部署用）
     node tools/dev/sync-site-changelog.mjs --check                  只校验现有快照（不联网）

   校验：每条都要有版本号（数字点分）、日期（YYYY-MM-DD）、平台（windows / macos / linux 中的一个或几个）、至少一条变化；
   变化的类型只能是 feature / improve / fix，文字非空且不超过 600 字。 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = resolve(ROOT, "website/assets/data/changelog.json");
const OUT_LATEST = resolve(ROOT, "website/assets/data/changelog-latest.json");
const args = process.argv.slice(2);
const SOFT = args.includes("--soft"), CHECK = args.includes("--check");
const fileArg = (() => { const i = args.indexOf("--file"); return i >= 0 ? args[i + 1] : null; })();

const PLATFORMS = new Set(["windows", "macos", "linux"]), TYPES = new Set(["feature", "improve", "fix"]);

function normalize(raw) {
  const list = Array.isArray(raw) ? raw : raw && (raw.items || raw.releases);
  if (!Array.isArray(list) || !list.length) throw new Error("没有版本记录（期望 { items: [...] } 或 { releases: [...] }）");
  const items = list.map((r, i) => {
    const at = `第 ${i + 1} 条（${r && r.version}）`;
    if (!r || typeof r !== "object") throw new Error(`${at} 不是对象`);
    if (!/^\d+(\.\d+){1,3}$/.test(String(r.version || ""))) throw new Error(`${at} 版本号不对`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(r.date || ""))) throw new Error(`${at} 日期不对`);
    const platforms = Array.isArray(r.platforms) ? r.platforms.map(String) : [];
    if (!platforms.length || platforms.some((p) => !PLATFORMS.has(p))) throw new Error(`${at} 平台不对：${platforms.join(",")}`);
    const changes = Array.isArray(r.changes) ? r.changes : [];
    if (!changes.length) throw new Error(`${at} 没有变化条目`);
    return {
      version: String(r.version), date: r.date, platforms,
      changes: changes.map((c, j) => {
        const text = String((c && c.text) || "").trim();
        if (!TYPES.has(c && c.type)) throw new Error(`${at} 第 ${j + 1} 项类型不对：${c && c.type}`);
        if (!text || text.length > 600) throw new Error(`${at} 第 ${j + 1} 项文字为空或过长`);
        return { type: c.type, text };
      }),
    };
  });
  // 新的在前：先按日期，同一天的保持来源里的先后
  return items.map((it, i) => [it, i]).sort((a, b) => (a[0].date === b[0].date ? a[1] - b[1] : a[0].date < b[0].date ? 1 : -1)).map(([it]) => it);
}

function write(items) {
  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify({ items }, null, 1) + "\n");
  const [l] = items;
  writeFileSync(OUT_LATEST, JSON.stringify({ version: l.version, date: l.date, platforms: l.platforms, count: l.changes.length, releases: items.length }) + "\n");
}

async function fetchItems() {
  if (fileArg) {
    const raw = JSON.parse(readFileSync(resolve(fileArg), "utf8"));
    return normalize(raw.releases ? { releases: raw.releases } : raw);
  }
  const url = process.env.CHANGELOG_URL;
  if (!url) throw new Error("没有设置 CHANGELOG_URL（也没给 --file）");
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 20000);
  try {
    const r = await fetch(url, { headers: { Accept: "application/json" }, signal: ctl.signal });
    if (!r.ok) throw new Error(`接口返回 HTTP ${r.status}`);
    return normalize(await r.json());
  } finally { clearTimeout(t); }
}

if (CHECK) {
  try {
    const items = normalize(JSON.parse(readFileSync(OUT, "utf8")));
    const l = JSON.parse(readFileSync(OUT_LATEST, "utf8"));
    if (l.version !== items[0].version || l.date !== items[0].date) throw new Error("changelog-latest.json 与 changelog.json 的最新一条对不上");
    console.log(`✓ 更新日志快照：${items.length} 个版本，最新 ${items[0].version}（${items[0].date}）`);
  } catch (e) { console.error("✗ 更新日志快照不合格：" + e.message); process.exit(1); }
} else {
  try {
    const items = await fetchItems();
    write(items);
    console.log(`✓ 已写入更新日志：${items.length} 个版本，最新 ${items[0].version}（${items[0].date}）`);
  } catch (e) {
    if (!SOFT) { console.error("✗ 更新日志没取到：" + e.message); process.exit(1); }
    console.log(`::warning::更新日志没取到（${e.message}），沿用仓库里的快照`);
  }
}
