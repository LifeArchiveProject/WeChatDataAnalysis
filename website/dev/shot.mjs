#!/usr/bin/env node
/* 高级版场景走片截图：无头 Chrome 打开 lab 的 strip 模式，一张图看一个场景的 N 个关键帧。
   用法：node website/dev/shot.mjs <scene-key|all|missing-free> [outDir] [--frames=6] [--port=4321]
   前提：python3 website/serve.py 4321 已在跑。输出 <outDir>/<scene-key>.png */
import { execFileSync } from "node:child_process";
import { mkdirSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { PRO_ITEMS } from "../assets/js/pro-demos/catalog.js";

const args = process.argv.slice(2);
const flags = Object.fromEntries(args.filter((a) => a.startsWith("--")).map((a) => a.slice(2).split("=")));
const pos = args.filter((a) => !a.startsWith("--"));
const which = pos[0] || "all";
const outDir = resolve(pos[1] || "./pro-shots");
const frames = flags.frames || 6;
const port = flags.port || 4321;
// 首选 Playwright 缓存里的 headless shell（截完即退），退而求其次用桌面 Chrome（截完偶尔挂住，靠 timeout 兜底）
import { homedir } from "node:os";
import { readdirSync } from "node:fs";
const pwDir = resolve(homedir(), "Library/Caches/ms-playwright");
const shells = existsSync(pwDir) ? readdirSync(pwDir).filter((d) => d.startsWith("chromium_headless_shell-")).sort().reverse() : [];
const shell = shells.map((d) => resolve(pwDir, d, "chrome-headless-shell-mac-arm64/chrome-headless-shell")).find((p) => existsSync(p));
const chrome = flags.chrome || shell || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
if (!existsSync(chrome)) { console.error("找不到可用的无头浏览器：" + chrome); process.exit(1); }
mkdirSync(outDir, { recursive: true });

const keys = which === "all" ? PRO_ITEMS.map((i) => i.key) : which.split(",");
for (const key of keys) {
  const url = `http://127.0.0.1:${port}/dev/pro-lab.html?scene=${encodeURIComponent(key)}&strip=1&frames=${frames}`;
  const out = resolve(outDir, `${key}.png`);
  execFileSync(chrome, [
    "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${resolve(outDir, ".chrome-profile")}`,
    `--window-size=1400,${120 + Math.ceil(Number(frames) / 3) * 350}`, "--virtual-time-budget=5000", "--force-device-scale-factor=1",
    `--screenshot=${out}`, url,
  ], { stdio: "ignore", timeout: 40000, killSignal: "SIGKILL" });
  console.log("✓", key, "→", out);
}
