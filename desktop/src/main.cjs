const { app, BrowserWindow, Menu, ipcMain, globalShortcut } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const BACKEND_HOST = process.env.WECHAT_TOOL_HOST || "127.0.0.1";
const BACKEND_PORT = Number(process.env.WECHAT_TOOL_PORT || "8000");
const BACKEND_HEALTH_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}/api/health`;

let backendProc = null;

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
      stdio: "ignore",
      windowsHide: true,
    });
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
  return !app.isPackaged || process.env.WECHAT_DESKTOP_DEBUG === "1";
}

function registerDebugShortcuts() {
  if (!debugEnabled()) return;

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
      devTools: debugEnabled(),
    },
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
}

async function main() {
  await app.whenReady();
  Menu.setApplicationMenu(null);
  registerWindowIpc();
  registerDebugShortcuts();

  startBackend();
  await waitForBackend({ timeoutMs: 30_000 });

  const win = createMainWindow();

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
  stopBackend();
});

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  stopBackend();
  app.quit();
});
