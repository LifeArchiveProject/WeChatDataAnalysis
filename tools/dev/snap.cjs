/* 用 desktop 里现成的 electron 给任意页面截图（Browser 面板隐藏时截不了图，这是唯一可靠办法）。
   用法：
     desktop/node_modules/.bin/electron tools/dev/snap.cjs --url=http://127.0.0.1:4321/ --out=/tmp/a.png [--w=1440 --h=900] [--wait=2500] [--js="..."] [--after=800] [--steps=steps.json] [--console] [--scheme=light|dark]
   steps.json 是一段顺序脚本：[{ "url": "...", "wait": 3000 }, { "js": "document.querySelector('x').click()", "wait": 1200, "shot": "/tmp/b.png" }, { "wait": 2000, "shot": "/tmp/c.png" }]
   每步可选 url / js / wait / shot；js 的返回值会打印到 stdout（[js] …）。最后总会再截一张到 --out。
   --scheme：把页面看到的系统外观（prefers-color-scheme）定成 light 或 dark（主进程设 nativeTheme.themeSource），用来测「跟随系统」；
   不传就跟这台机器当前的系统外观走（Mac 开着深色时，跟随系统的页面会截成深色——要固定浅色就传 --scheme=light）。
   每次运行用一个全新的 userData 目录，localStorage 总是空的：要模拟「手动选过」，在 steps 里先写 localStorage 再 location.reload()。
   注意：loadURL 遇到重定向会抛 ERR_ABORTED，这里已经吞掉；窗口尺寸必须 setContentSize 才生效。 */
const { app, BrowserWindow, nativeTheme } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");

const argv = process.argv.slice(2).filter((a) => a.startsWith("--"));
const args = Object.fromEntries(argv.map((a) => { const i = a.indexOf("="); return i < 0 ? [a.slice(2), true] : [a.slice(2, i), a.slice(i + 1)]; }));
const url = args.url;
const out = args.out || path.resolve("snap.png");
const W = Number(args.w) || 1440, H = Number(args.h) || 900;
const wait = Number(args.wait) || 2500;
const steps = args.steps ? JSON.parse(fs.readFileSync(args.steps, "utf8")) : (args.js ? [{ js: args.js, wait: Number(args.after) || 800 }] : []);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

if (!url) { console.error("需要 --url=..."); process.exit(1); }
app.setPath("userData", path.join(os.tmpdir(), "wda-snap-" + process.pid));

app.whenReady().then(async () => {
  // 系统外观：建窗口、载页面之前定好，首帧的 prefers-color-scheme 就是它
  if (args.scheme === "light" || args.scheme === "dark") nativeTheme.themeSource = args.scheme;
  else if (args.scheme) console.log("--scheme 只认 light / dark，已忽略：", args.scheme);
  // 默认隐藏窗口（不在用户桌面上闪）；backgroundThrottling:false 保证 rAF/GSAP 照常推进。--show=1 可强制显示。
  const win = new BrowserWindow({ width: W, height: H, show: !!args.show, backgroundColor: "#000000", webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  win.setContentSize(W, H);
  if (args.console) win.webContents.on("console-message", (_e, _lvl, msg) => console.log("[console]", msg));
  try { await win.loadURL(url); } catch (e) { console.log("loadURL:", e.message); }
  await sleep(wait);
  for (const st of steps) {
    if (st.url) { try { await win.loadURL(st.url); } catch (e) { console.log("loadURL:", e.message); } }
    if (st.js) {
      try { const r = await win.webContents.executeJavaScript(st.js, true); if (r !== undefined) console.log("[js]", typeof r === "string" ? r : JSON.stringify(r)); }
      catch (e) { console.log("[js error]", e.message); }
    }
    await sleep(st.wait ?? 800);
    if (st.shot) { const img = await win.webContents.capturePage(); fs.writeFileSync(st.shot, img.toPNG()); console.log("✓", st.shot); }
  }
  const img = await win.webContents.capturePage();
  fs.writeFileSync(out, img.toPNG());
  console.log("✓", out, "content size", win.getContentSize().join("x"));
  app.quit();
}).catch((e) => { console.error(e); app.exit(1); });
