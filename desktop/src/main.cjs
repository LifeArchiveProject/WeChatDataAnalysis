const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  ipcMain,
  globalShortcut,
  dialog,
  shell,
} = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const BACKEND_HOST = process.env.WECHAT_TOOL_HOST || "127.0.0.1";
const BACKEND_PORT = Number(process.env.WECHAT_TOOL_PORT || "8000");
const BACKEND_HEALTH_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}/api/health`;

let backendProc = null;
let backendStdioStream = null;
let resolvedDataDir = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let desktopSettings = null;

function nowIso() {
  return new Date().toISOString();
}

function resolveDataDir() {
  if (resolvedDataDir) return resolvedDataDir;

  const fromEnv = String(process.env.WECHAT_TOOL_DATA_DIR || "").trim();
  const fallback = (() => {
    try {
      return app.getPath("userData");
    } catch {
      return null;
    }
  })();

  const chosen = fromEnv || fallback;
  if (!chosen) return null;

  try {
    fs.mkdirSync(chosen, { recursive: true });
  } catch {}

  resolvedDataDir = chosen;
  process.env.WECHAT_TOOL_DATA_DIR = chosen;
  return chosen;
}

function getUserDataDir() {
  // Backwards-compat: we historically used Electron's userData directory for runtime storage.
  // Keep this name but resolve to the effective data dir (can be overridden via env).
  return resolveDataDir();
}

function getExeDir() {
  try {
    return path.dirname(process.execPath);
  } catch {
    return null;
  }
}

function ensureOutputLink() {
  // Users often expect an `output/` folder near the installed exe. We keep the real data
  // in the per-user data dir, and (when possible) create a Windows junction next to the exe.
  if (!app.isPackaged) return;

  const exeDir = getExeDir();
  const dataDir = resolveDataDir();
  if (!exeDir || !dataDir) return;

  const target = path.join(dataDir, "output");
  const linkPath = path.join(exeDir, "output");

  // If the target doesn't exist yet, create it so the link points somewhere real.
  try {
    fs.mkdirSync(target, { recursive: true });
  } catch {}

  // If something already exists at linkPath, do not overwrite it.
  try {
    if (fs.existsSync(linkPath)) return;
  } catch {
    return;
  }

  try {
    fs.symlinkSync(target, linkPath, "junction");
    logMain(`[main] created output link: ${linkPath} -> ${target}`);
  } catch (err) {
    logMain(`[main] failed to create output link: ${err?.message || err}`);
  }
}

function getMainLogPath() {
  const dir = getUserDataDir();
  if (!dir) return null;
  return path.join(dir, "desktop-main.log");
}

function logMain(line) {
  const p = getMainLogPath();
  if (!p) return;
  try {
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.appendFileSync(p, `[${nowIso()}] ${line}\n`, { encoding: "utf8" });
  } catch {}
}

function getDesktopSettingsPath() {
  const dir = getUserDataDir();
  if (!dir) return null;
  return path.join(dir, "desktop-settings.json");
}

function loadDesktopSettings() {
  if (desktopSettings) return desktopSettings;

  const defaults = {
    // 'tray' (default): closing the window hides it to the system tray.
    // 'exit': closing the window quits the app.
    closeBehavior: "tray",
  };

  const p = getDesktopSettingsPath();
  if (!p) {
    desktopSettings = { ...defaults };
    return desktopSettings;
  }

  try {
    if (!fs.existsSync(p)) {
      desktopSettings = { ...defaults };
      return desktopSettings;
    }
    const raw = fs.readFileSync(p, { encoding: "utf8" });
    const parsed = JSON.parse(raw || "{}");
    desktopSettings = { ...defaults, ...(parsed && typeof parsed === "object" ? parsed : {}) };
  } catch (err) {
    desktopSettings = { ...defaults };
    logMain(`[main] failed to load settings: ${err?.message || err}`);
  }

  return desktopSettings;
}

function persistDesktopSettings() {
  const p = getDesktopSettingsPath();
  if (!p) return;
  if (!desktopSettings) return;

  try {
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(desktopSettings, null, 2), { encoding: "utf8" });
  } catch (err) {
    logMain(`[main] failed to persist settings: ${err?.message || err}`);
  }
}

function getCloseBehavior() {
  const v = String(loadDesktopSettings()?.closeBehavior || "").trim().toLowerCase();
  return v === "exit" ? "exit" : "tray";
}

function setCloseBehavior(next) {
  const v = String(next || "").trim().toLowerCase();
  loadDesktopSettings();
  desktopSettings.closeBehavior = v === "exit" ? "exit" : "tray";
  persistDesktopSettings();
  return desktopSettings.closeBehavior;
}

function getTrayIconPath() {
  // Prefer an icon shipped in `src/` so it works both in dev and packaged (asar) builds.
  const shipped = path.join(__dirname, "icon.ico");
  try {
    if (fs.existsSync(shipped)) return shipped;
  } catch {}

  // Dev fallback (not available in packaged builds).
  const dev = path.resolve(__dirname, "..", "build", "icon.ico");
  try {
    if (fs.existsSync(dev)) return dev;
  } catch {}

  return null;
}

function showMainWindow() {
  if (!mainWindow) return;
  try {
    mainWindow.setSkipTaskbar(false);
  } catch {}
  try {
    if (mainWindow.isMinimized()) mainWindow.restore();
  } catch {}
  try {
    mainWindow.show();
  } catch {}
  try {
    mainWindow.focus();
  } catch {}
}

function createTray() {
  if (tray) return tray;
  if (!app.isPackaged) return null;

  const iconPath = getTrayIconPath();
  if (!iconPath) {
    logMain("[main] tray icon not found; disabling tray behavior");
    return null;
  }

  try {
    tray = new Tray(iconPath);
  } catch (err) {
    tray = null;
    logMain(`[main] failed to create tray: ${err?.message || err}`);
    return null;
  }

  try {
    tray.setToolTip("WeChatDataAnalysis");
  } catch {}

  try {
    tray.setContextMenu(
      Menu.buildFromTemplate([
        {
          label: "显示",
          click: () => showMainWindow(),
        },
        {
          label: "退出",
          click: () => {
            isQuitting = true;
            app.quit();
          },
        },
      ])
    );
  } catch {}

  try {
    tray.on("click", () => showMainWindow());
    tray.on("double-click", () => showMainWindow());
  } catch {}

  return tray;
}

function destroyTray() {
  if (!tray) return;
  try {
    tray.destroy();
  } catch {}
  tray = null;
}

function ensureTrayForCloseBehavior() {
  const behavior = getCloseBehavior();
  if (behavior === "tray") createTray();
  else destroyTray();
}

function getBackendStdioLogPath(dataDir) {
  return path.join(dataDir, "backend-stdio.log");
}

function attachBackendStdio(proc, logPath) {
  // In packaged builds, stdout/stderr are often the only place we can see early crash
  // reasons (missing DLLs, import errors) before the Python logger initializes.
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
  } catch {}

  try {
    backendStdioStream = fs.createWriteStream(logPath, { flags: "a" });
    backendStdioStream.write(`[${nowIso()}] [main] backend stdio -> ${logPath}\n`);
  } catch {
    backendStdioStream = null;
    return;
  }

  const write = (prefix, chunk) => {
    if (!backendStdioStream) return;
    try {
      const text = Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk);
      backendStdioStream.write(`[${nowIso()}] ${prefix} ${text}`);
      if (!text.endsWith("\n")) backendStdioStream.write("\n");
    } catch {}
  };

  if (proc.stdout) proc.stdout.on("data", (d) => write("[backend:stdout]", d));
  if (proc.stderr) proc.stderr.on("data", (d) => write("[backend:stderr]", d));
  proc.on("error", (err) => write("[backend:error]", err?.stack || String(err)));
  proc.on("close", (code, signal) => {
    write("[backend:close]", `code=${code} signal=${signal}`);
    try {
      backendStdioStream?.end();
    } catch {}
    backendStdioStream = null;
  });
}

function repoRoot() {
  // desktop/src -> desktop -> repo root
  return path.resolve(__dirname, "..", "..");
}

function getPackagedBackendPath() {
  // Placeholder: in step 3 we will bundle a real backend exe into resources.
  return path.join(process.resourcesPath, "backend", "wechat-backend.exe");
}

function startBackend() {
  if (backendProc) return backendProc;

  const env = {
    ...process.env,
    WECHAT_TOOL_HOST: BACKEND_HOST,
    WECHAT_TOOL_PORT: String(BACKEND_PORT),
    // Make sure Python prints UTF-8 to stdout/stderr.
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
  };

  // In packaged mode we expect to provide the generated Nuxt output dir via env.
  if (app.isPackaged && !env.WECHAT_TOOL_UI_DIR) {
    env.WECHAT_TOOL_UI_DIR = path.join(process.resourcesPath, "ui");
  }

  if (app.isPackaged) {
    if (!env.WECHAT_TOOL_DATA_DIR) {
      env.WECHAT_TOOL_DATA_DIR = app.getPath("userData");
    }
    try {
      fs.mkdirSync(env.WECHAT_TOOL_DATA_DIR, { recursive: true });
    } catch {}

    const backendExe = getPackagedBackendPath();
    if (!fs.existsSync(backendExe)) {
      throw new Error(
        `Packaged backend not found: ${backendExe}. Build it into desktop/resources/backend/wechat-backend.exe`
      );
    }
    backendProc = spawn(backendExe, [], {
      cwd: env.WECHAT_TOOL_DATA_DIR,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    attachBackendStdio(backendProc, getBackendStdioLogPath(env.WECHAT_TOOL_DATA_DIR));
  } else {
    backendProc = spawn("uv", ["run", "main.py"], {
      cwd: repoRoot(),
      env,
      stdio: "inherit",
      windowsHide: true,
    });
  }

  backendProc.on("exit", (code, signal) => {
    backendProc = null;
    // eslint-disable-next-line no-console
    console.log(`[backend] exited code=${code} signal=${signal}`);
    logMain(`[backend] exited code=${code} signal=${signal}`);
  });

  return backendProc;
}

function stopBackend() {
  if (!backendProc) return;

  try {
    if (process.platform === "win32" && backendProc.pid) {
      // Ensure child tree is killed on Windows.
      spawn("taskkill", ["/pid", String(backendProc.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
      return;
    }
  } catch {}

  try {
    backendProc.kill();
  } catch {}
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      // Drain data so sockets can be reused.
      res.resume();
      resolve(res.statusCode || 0);
    });
    req.on("error", reject);
    req.setTimeout(1000, () => {
      req.destroy(new Error("timeout"));
    });
  });
}

async function waitForBackend({ timeoutMs }) {
  const startedAt = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const code = await httpGet(BACKEND_HEALTH_URL);
      if (code >= 200 && code < 500) return;
    } catch {}

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`Backend did not become ready in ${timeoutMs}ms: ${BACKEND_HEALTH_URL}`);
    }

    await new Promise((r) => setTimeout(r, 300));
  }
}

function debugEnabled() {
  // Enable debug helpers in dev by default; in packaged builds require explicit opt-in.
  if (!app.isPackaged) return true;
  if (process.env.WECHAT_DESKTOP_DEBUG === "1") return true;
  return process.argv.includes("--debug") || process.argv.includes("--devtools");
}

function registerDebugShortcuts() {
  const toggleDevTools = () => {
    const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
    if (!win) return;

    if (win.webContents.isDevToolsOpened()) win.webContents.closeDevTools();
    else win.webContents.openDevTools({ mode: "detach" });
  };

  // When we remove the app menu, Electron no longer provides the default DevTools accelerators.
  globalShortcut.register("CommandOrControl+Shift+I", toggleDevTools);
  globalShortcut.register("F12", toggleDevTools);
}

function getRendererConsoleLogPath() {
  try {
    const dir = app.getPath("userData");
    fs.mkdirSync(dir, { recursive: true });
    return path.join(dir, "renderer-console.log");
  } catch {
    return null;
  }
}

function setupRendererConsoleLogging(win) {
  if (!debugEnabled()) return;

  const logPath = getRendererConsoleLogPath();
  if (!logPath) return;

  const append = (line) => {
    try {
      fs.appendFileSync(logPath, line, { encoding: "utf8" });
    } catch {}
  };

  append(`[${new Date().toISOString()}] [main] renderer console -> ${logPath}\n`);

  win.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    append(
      `[${new Date().toISOString()}] [renderer] level=${level} ${message} (${sourceId}:${line})\n`
    );
  });
}

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 980,
    minHeight: 700,
    frame: false,
    backgroundColor: "#EDEDED",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      // Allow DevTools to be opened in packaged builds (F12 / Ctrl+Shift+I).
      // We still only auto-open it when debugEnabled() returns true.
      devTools: true,
    },
  });

  win.on("close", (event) => {
    // In packaged builds, we default to "close -> minimize to tray" unless the user opts out.
    if (!app.isPackaged) return;
    if (isQuitting) return;
    if (getCloseBehavior() !== "tray") return;
    if (!tray) return;

    try {
      event.preventDefault();
      win.setSkipTaskbar(true);
      win.hide();
      try {
        tray.displayBalloon({
          title: "WeChatDataAnalysis",
          content: "已最小化到托盘，可从托盘图标再次打开。",
        });
      } catch {}
    } catch {}
  });

  win.on("closed", () => {
    stopBackend();
  });

  setupRendererConsoleLogging(win);

  return win;
}

async function loadWithRetry(win, url) {
  const startedAt = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      await win.loadURL(url);
      return;
    } catch {
      if (Date.now() - startedAt > 60_000) throw new Error(`Failed to load URL in time: ${url}`);
      await new Promise((r) => setTimeout(r, 500));
    }
  }
}

function registerWindowIpc() {
  const getWin = (event) => BrowserWindow.fromWebContents(event.sender);

  ipcMain.handle("window:minimize", (event) => {
    const win = getWin(event);
    win?.minimize();
  });

  ipcMain.handle("window:toggleMaximize", (event) => {
    const win = getWin(event);
    if (!win) return;
    if (win.isMaximized()) win.unmaximize();
    else win.maximize();
  });

  ipcMain.handle("window:close", (event) => {
    const win = getWin(event);
    win?.close();
  });

  ipcMain.handle("window:isMaximized", (event) => {
    const win = getWin(event);
    return !!win?.isMaximized();
  });

  ipcMain.handle("app:getAutoLaunch", () => {
    try {
      const settings = app.getLoginItemSettings();
      return !!(settings?.openAtLogin || settings?.executableWillLaunchAtLogin);
    } catch (err) {
      logMain(`[main] getAutoLaunch failed: ${err?.message || err}`);
      return false;
    }
  });

  ipcMain.handle("app:setAutoLaunch", (_event, enabled) => {
    const on = !!enabled;
    try {
      app.setLoginItemSettings({ openAtLogin: on });
    } catch (err) {
      logMain(`[main] setAutoLaunch(${on}) failed: ${err?.message || err}`);
      return false;
    }

    try {
      const settings = app.getLoginItemSettings();
      return !!(settings?.openAtLogin || settings?.executableWillLaunchAtLogin);
    } catch {
      return on;
    }
  });

  ipcMain.handle("app:getCloseBehavior", () => {
    try {
      return getCloseBehavior();
    } catch (err) {
      logMain(`[main] getCloseBehavior failed: ${err?.message || err}`);
      return "tray";
    }
  });

  ipcMain.handle("app:setCloseBehavior", (_event, behavior) => {
    try {
      const next = setCloseBehavior(behavior);
      ensureTrayForCloseBehavior();
      return next;
    } catch (err) {
      logMain(`[main] setCloseBehavior failed: ${err?.message || err}`);
      return getCloseBehavior();
    }
  });
}

async function main() {
  await app.whenReady();
  Menu.setApplicationMenu(null);
  registerWindowIpc();
  registerDebugShortcuts();

  // Resolve/create the data dir early so we can log reliably and (optionally) place a link
  // next to the installed exe for easier access.
  resolveDataDir();
  ensureOutputLink();

  logMain(`[main] app.isPackaged=${app.isPackaged} argv=${JSON.stringify(process.argv)}`);

  startBackend();
  await waitForBackend({ timeoutMs: 30_000 });

  const win = createMainWindow();
  mainWindow = win;
  ensureTrayForCloseBehavior();

  const startUrl =
    process.env.ELECTRON_START_URL ||
    (app.isPackaged ? `http://${BACKEND_HOST}:${BACKEND_PORT}/` : "http://localhost:3000");

  await loadWithRetry(win, startUrl);

  // If debug mode is enabled, auto-open DevTools so the user doesn't need menu/shortcuts.
  if (debugEnabled()) {
    try {
      win.webContents.openDevTools({ mode: "detach" });
    } catch {}
  }
}

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", () => {
  try {
    globalShortcut.unregisterAll();
  } catch {}
});

app.on("before-quit", () => {
  isQuitting = true;
  destroyTray();
  stopBackend();
});

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  logMain(`[main] fatal: ${err?.stack || String(err)}`);
  stopBackend();
  try {
    const dir = getUserDataDir();
    if (dir) {
      dialog.showErrorBox(
        "WeChatDataAnalysis 启动失败",
        `启动失败：${err?.message || err}\n\n请查看日志目录：\n${dir}\n\n文件：desktop-main.log / backend-stdio.log / output\\\\logs\\\\...`
      );
      shell.openPath(dir);
    }
  } catch {}
  app.quit();
});
