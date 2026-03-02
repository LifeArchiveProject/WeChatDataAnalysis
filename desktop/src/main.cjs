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
let autoUpdater = null;
let autoUpdaterLoadError = null;
try {
  ({ autoUpdater } = require("electron-updater"));
} catch (err) {
  autoUpdaterLoadError = err;
}
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

const DEFAULT_BACKEND_HOST = String(process.env.WECHAT_TOOL_HOST || "127.0.0.1").trim() || "127.0.0.1";
const DEFAULT_BACKEND_PORT = parsePort(process.env.WECHAT_TOOL_PORT) ?? 10392;

let backendProc = null;
let resolvedDataDir = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let desktopSettings = null;
let backendPortChangeInProgress = false;

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  // If we allow a second instance to boot it will try to spawn another backend on the same port.
  // Quit early to avoid leaving orphan backend processes around.
  try {
    app.quit();
  } catch {}
} else {
  app.on("second-instance", () => {
    try {
      if (app.isReady()) showMainWindow();
      else app.whenReady().then(() => showMainWindow());
    } catch {}
  });
}

function nowIso() {
  return new Date().toISOString();
}

function parsePort(value) {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isInteger(n)) return null;
  if (n < 1 || n > 65535) return null;
  return n;
}

function formatHostForUrl(host) {
  const h = String(host || "").trim();
  if (!h) return "127.0.0.1";
  // IPv6 literals must be wrapped in brackets in URLs.
  if (h.includes(":") && !(h.startsWith("[") && h.endsWith("]"))) return `[${h}]`;
  return h;
}

function getBackendBindHost() {
  return DEFAULT_BACKEND_HOST;
}

function getBackendAccessHost() {
  // 0.0.0.0 / :: are fine bind hosts, but not a reachable client destination.
  const host = String(getBackendBindHost() || "").trim();
  if (host === "0.0.0.0" || host === "::") return "127.0.0.1";
  return host || "127.0.0.1";
}

function getBackendPort() {
  const settingsPort = parsePort(loadDesktopSettings()?.backendPort);
  return settingsPort ?? DEFAULT_BACKEND_PORT;
}

function setBackendPortSetting(nextPort) {
  const p = parsePort(nextPort);
  if (p == null) throw new Error("端口无效，请输入 1-65535 的整数");
  loadDesktopSettings();
  desktopSettings.backendPort = p;
  persistDesktopSettings();
  process.env.WECHAT_TOOL_PORT = String(p);
  return p;
}

function getBackendHealthUrl() {
  const host = formatHostForUrl(getBackendAccessHost());
  const port = getBackendPort();
  return `http://${host}:${port}/api/health`;
}

function getBackendUiUrl() {
  const host = formatHostForUrl(getBackendAccessHost());
  const port = getBackendPort();
  return `http://${host}:${port}/`;
}

function isPortAvailable(port, host) {
  return new Promise((resolve) => {
    try {
      const srv = net.createServer();
      srv.unref();
      srv.once("error", () => resolve(false));
      srv.listen({ port, host }, () => {
        srv.close(() => resolve(true));
      });
    } catch {
      resolve(false);
    }
  });
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
    // When set, suppress the auto-update prompt for this exact version.
    ignoredUpdateVersion: "",
    // Backend (FastAPI) listens on this port. Used in packaged builds.
    backendPort: DEFAULT_BACKEND_PORT,
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
    desktopSettings.backendPort = parsePort(desktopSettings.backendPort) ?? defaults.backendPort;
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

function getIgnoredUpdateVersion() {
  const v = String(loadDesktopSettings()?.ignoredUpdateVersion || "").trim();
  return v || "";
}

function setIgnoredUpdateVersion(version) {
  loadDesktopSettings();
  desktopSettings.ignoredUpdateVersion = String(version || "").trim();
  persistDesktopSettings();
  return desktopSettings.ignoredUpdateVersion;
}

function parseEnvBool(value) {
  if (value == null) return null;
  const v = String(value).trim().toLowerCase();
  if (!v) return null;
  if (v === "1" || v === "true" || v === "yes" || v === "y" || v === "on") return true;
  if (v === "0" || v === "false" || v === "no" || v === "n" || v === "off") return false;
  return null;
}

let autoUpdateEnabledCache = null;
function isAutoUpdateEnabled() {
  if (autoUpdateEnabledCache != null) return !!autoUpdateEnabledCache;

  const forced = parseEnvBool(process.env.AUTO_UPDATE_ENABLED);
  let enabled = forced != null ? forced : !!app.isPackaged;
  if (enabled && !autoUpdater) {
    enabled = false;
    logMain(
      `[main] auto-update disabled: electron-updater unavailable: ${autoUpdaterLoadError?.message || "unknown error"}`
    );
  }

  // In packaged builds electron-updater reads update config from app-update.yml.
  // If missing, treat auto-update as disabled to avoid noisy errors.
  if (enabled && app.isPackaged) {
    try {
      const updateConfigPath = path.join(process.resourcesPath, "app-update.yml");
      if (!fs.existsSync(updateConfigPath)) {
        enabled = false;
        logMain(`[main] auto-update disabled: missing ${updateConfigPath}`);
      }
    } catch (err) {
      enabled = false;
      logMain(`[main] auto-update disabled: failed to check app-update.yml: ${err?.message || err}`);
    }
  }

  autoUpdateEnabledCache = enabled;
  return enabled;
}

let autoUpdaterInitialized = false;
let updateDownloadInProgress = false;
let installOnDownload = false;
let updateDownloaded = false;
let lastUpdateInfo = null;

function sendToRenderer(channel, payload) {
  try {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.webContents.send(channel, payload);
  } catch (err) {
    logMain(`[main] failed to send ${channel}: ${err?.message || err}`);
  }
}

function setWindowProgressBar(value) {
  try {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.setProgressBar(value);
  } catch {}
}

function looksLikeHtml(input) {
  if (!input) return false;
  const s = String(input);
  if (!s.includes("<") || !s.includes(">")) return false;
  // Be conservative: only treat the note as HTML if it contains common tags we expect from GitHub-rendered bodies.
  return /<(p|div|br|ul|ol|li|a|strong|em|tt|code|pre|h[1-6])\b/i.test(s);
}

function htmlToPlainText(html) {
  if (!html) return "";

  let text = String(html);

  // Drop script/style blocks entirely.
  text = text.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "");
  text = text.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "");

  // Keep links readable after stripping tags.
  text = text.replace(
    /<a\s+[^>]*href=(["'])([^"']+)\1[^>]*>([\s\S]*?)<\/a>/gi,
    (_m, _q, href, inner) => {
      const innerText = String(inner).replace(/<[^>]*>/g, "").trim();
      const url = String(href || "").trim();
      if (!url) return innerText;
      if (!innerText) return url;
      return `${innerText} (${url})`;
    }
  );

  // Preserve line breaks / list structure before stripping remaining tags.
  text = text.replace(/<\s*br\s*\/?>/gi, "\n");
  text = text.replace(/<\/\s*(p|div|h1|h2|h3|h4|h5|h6)\s*>/gi, "\n");
  text = text.replace(/<\s*li[^>]*>/gi, "- ");
  text = text.replace(/<\/\s*li\s*>/gi, "\n");
  text = text.replace(/<\/\s*(ul|ol)\s*>/gi, "\n");

  // Strip remaining tags.
  text = text.replace(/<[^>]*>/g, "");

  // Decode the handful of entities we commonly see from GitHub-rendered HTML.
  const named = {
    nbsp: " ",
    amp: "&",
    lt: "<",
    gt: ">",
    quot: '"',
    apos: "'",
    "#39": "'",
  };
  text = text.replace(/&([a-z0-9#]+);/gi, (m, name) => {
    const key = String(name || "").toLowerCase();
    if (named[key] != null) return named[key];

    // Numeric entities (decimal / hex).
    const decMatch = key.match(/^#(\d+)$/);
    if (decMatch) {
      const n = Number(decMatch[1]);
      if (Number.isFinite(n) && n >= 0 && n <= 0x10ffff) {
        try {
          return String.fromCodePoint(n);
        } catch {
          return m;
        }
      }
      return m;
    }

    const hexMatch = key.match(/^#x([0-9a-f]+)$/i);
    if (hexMatch) {
      const n = Number.parseInt(hexMatch[1], 16);
      if (Number.isFinite(n) && n >= 0 && n <= 0x10ffff) {
        try {
          return String.fromCodePoint(n);
        } catch {
          return m;
        }
      }
      return m;
    }

    return m;
  });

  // Normalize whitespace/newlines.
  text = text.replace(/\r\n/g, "\n");
  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}

function normalizeReleaseNotes(releaseNotes) {
  if (!releaseNotes) return "";

  const normalizeText = (value) => {
    if (value == null) return "";
    const raw = typeof value === "string" ? value : String(value);
    const trimmed = raw.trim();
    if (!trimmed) return "";
    if (looksLikeHtml(trimmed)) return htmlToPlainText(trimmed);
    return trimmed;
  };

  if (typeof releaseNotes === "string") return normalizeText(releaseNotes);
  if (Array.isArray(releaseNotes)) {
    const parts = [];
    for (const item of releaseNotes) {
      const version = item?.version ? String(item.version) : "";
      const note = item?.note;
      const noteText =
        typeof note === "string" ? note : note != null ? JSON.stringify(note, null, 2) : "";
      const block = [version ? `v${version}` : "", normalizeText(noteText)]
        .filter(Boolean)
        .join("\n");
      if (block) parts.push(block);
    }
    return parts.join("\n\n");
  }
  try {
    return normalizeText(JSON.stringify(releaseNotes, null, 2));
  } catch {
    return normalizeText(releaseNotes);
  }
}

function initAutoUpdater() {
  if (autoUpdaterInitialized) return;
  autoUpdaterInitialized = true;

  // Configure auto-updater (align with WeFlow).
  autoUpdater.autoDownload = false;
  // Don't install automatically on quit; let the user choose when to restart/install.
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.disableDifferentialDownload = true;

  autoUpdater.on("download-progress", (progress) => {
    sendToRenderer("app:downloadProgress", progress);
    const percent = Number(progress?.percent || 0);
    if (Number.isFinite(percent) && percent > 0) {
      setWindowProgressBar(Math.max(0, Math.min(1, percent / 100)));
    }
  });

  autoUpdater.on("update-downloaded", () => {
    updateDownloadInProgress = false;
    updateDownloaded = true;
    installOnDownload = false;
    setWindowProgressBar(-1);

    const payload = {
      version: lastUpdateInfo?.version ? String(lastUpdateInfo.version) : "",
      releaseNotes: normalizeReleaseNotes(lastUpdateInfo?.releaseNotes),
    };
    sendToRenderer("app:updateDownloaded", payload);

    try {
      // If the window is hidden to tray, show a lightweight hint instead of forcing UI focus.
      tray?.displayBalloon?.({
        title: "更新已下载完成",
        content: "可在弹窗中选择“立即重启安装”，或稍后再安装。",
      });
    } catch {}
  });

  autoUpdater.on("error", (err) => {
    updateDownloadInProgress = false;
    installOnDownload = false;
    updateDownloaded = false;
    setWindowProgressBar(-1);
    const message = err?.message || String(err);
    logMain(`[main] autoUpdater error: ${message}`);
    sendToRenderer("app:updateError", { message });
  });
}

async function checkForUpdatesInternal() {
  const enabled = isAutoUpdateEnabled();
  if (!enabled) return { hasUpdate: false, enabled: false };

  initAutoUpdater();

  try {
    const result = await autoUpdater.checkForUpdates();
    const updateInfo = result?.updateInfo;
    lastUpdateInfo = updateInfo || null;
    const latestVersion = updateInfo?.version ? String(updateInfo.version) : "";
    const currentVersion = (() => {
      try {
        return app.getVersion();
      } catch {
        return "";
      }
    })();

    if (latestVersion && currentVersion && latestVersion !== currentVersion) {
      return {
        hasUpdate: true,
        enabled: true,
        version: latestVersion,
        releaseNotes: normalizeReleaseNotes(updateInfo?.releaseNotes),
      };
    }

    return { hasUpdate: false, enabled: true };
  } catch (err) {
    const message = err?.message || String(err);
    logMain(`[main] checkForUpdates failed: ${message}`);
    return { hasUpdate: false, enabled: true, error: message };
  }
}

async function downloadAndInstallInternal() {
  if (!isAutoUpdateEnabled()) {
    throw new Error("自动更新已禁用");
  }
  initAutoUpdater();

  if (updateDownloadInProgress) {
    throw new Error("正在下载更新中，请稍候…");
  }

  updateDownloadInProgress = true;
  installOnDownload = true;
  updateDownloaded = false;
  setWindowProgressBar(0);

  try {
    // Ensure update info is up-to-date (downloadUpdate relies on the last check).
    await autoUpdater.checkForUpdates();
    await autoUpdater.downloadUpdate();
    return { success: true };
  } catch (err) {
    updateDownloadInProgress = false;
    installOnDownload = false;
    setWindowProgressBar(-1);
    throw err;
  }
}

function checkForUpdatesOnStartup() {
  if (!isAutoUpdateEnabled()) return;
  if (!app.isPackaged) return; // keep dev noise-free by default

  setTimeout(async () => {
    const result = await checkForUpdatesInternal();
    if (!result?.hasUpdate) return;

    const ignored = getIgnoredUpdateVersion();
    if (ignored && ignored === result.version) return;

    sendToRenderer("app:updateAvailable", {
      version: result.version,
      releaseNotes: result.releaseNotes || "",
    });
  }, 3000);
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
          label: "检查更新...",
          click: async () => {
            try {
              if (!isAutoUpdateEnabled()) {
                await dialog.showMessageBox({
                  type: "info",
                  title: "检查更新",
                  message: "自动更新已禁用（仅打包版本可用）。",
                  buttons: ["确定"],
                  noLink: true,
                });
                return;
              }

              const result = await checkForUpdatesInternal();
              if (result?.error) {
                await dialog.showMessageBox({
                  type: "error",
                  title: "检查更新失败",
                  message: result.error,
                  buttons: ["确定"],
                  noLink: true,
                });
                return;
              }

              if (result?.hasUpdate && result?.version) {
                const { response } = await dialog.showMessageBox({
                  type: "info",
                  title: "发现新版本",
                  message: `发现新版本 ${result.version}，是否立即更新？`,
                  detail: result.releaseNotes ? `更新内容：\n${result.releaseNotes}` : undefined,
                  buttons: ["立即更新", "稍后", "忽略此版本"],
                  defaultId: 0,
                  cancelId: 1,
                  noLink: true,
                });

                if (response === 0) {
                  try {
                    await downloadAndInstallInternal();
                  } catch (err) {
                    const message = err?.message || String(err);
                    logMain(`[main] downloadAndInstall failed (tray): ${message}`);
                    await dialog.showMessageBox({
                      type: "error",
                      title: "更新失败",
                      message,
                      buttons: ["确定"],
                      noLink: true,
                    });
                  }
                } else if (response === 2) {
                  try {
                    setIgnoredUpdateVersion(result.version);
                  } catch {}
                }

                return;
              }

              await dialog.showMessageBox({
                type: "info",
                title: "检查更新",
                message: "当前已是最新版本。",
                buttons: ["确定"],
                noLink: true,
              });
            } catch (err) {
              const message = err?.message || String(err);
              logMain(`[main] tray check updates failed: ${message}`);
              await dialog.showMessageBox({
                type: "error",
                title: "检查更新失败",
                message,
                buttons: ["确定"],
                noLink: true,
              });
            }
          },
        },
        {
          type: "separator",
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

  let stream = null;
  try {
    stream = fs.createWriteStream(logPath, { flags: "a" });
    stream.write(`[${nowIso()}] [main] backend stdio -> ${logPath}\n`);
  } catch {
    return;
  }

  const write = (prefix, chunk) => {
    if (!stream) return;
    try {
      const text = Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk);
      stream.write(`[${nowIso()}] ${prefix} ${text}`);
      if (!text.endsWith("\n")) stream.write("\n");
    } catch {}
  };

  if (proc.stdout) proc.stdout.on("data", (d) => write("[backend:stdout]", d));
  if (proc.stderr) proc.stderr.on("data", (d) => write("[backend:stderr]", d));
  proc.on("error", (err) => write("[backend:error]", err?.stack || String(err)));
  proc.on("close", (code, signal) => {
    write("[backend:close]", `code=${code} signal=${signal}`);
    try {
      stream?.end();
    } catch {}
    stream = null;
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

function getPackagedWcdbDllPath() {
  return path.join(process.resourcesPath, "backend", "native", "wcdb_api.dll");
}

function startBackend() {
  if (backendProc) return backendProc;

  const env = {
    ...process.env,
    WECHAT_TOOL_HOST: getBackendBindHost(),
    WECHAT_TOOL_PORT: String(getBackendPort()),
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
    const packagedWcdbDll = getPackagedWcdbDllPath();
    if (fs.existsSync(packagedWcdbDll)) {
      env.WECHAT_TOOL_WCDB_API_DLL_PATH = packagedWcdbDll;
      logMain(`[main] using packaged wcdb_api.dll: ${packagedWcdbDll}`);
    } else {
      logMain(`[main] packaged wcdb_api.dll not found: ${packagedWcdbDll}`);
    }

    const backendCwd = path.dirname(backendExe);
    backendProc = spawn(backendExe, [], {
      cwd: backendCwd,
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

  const proc = backendProc;
  proc.on("exit", (code, signal) => {
    if (backendProc === proc) backendProc = null;
    // eslint-disable-next-line no-console
    console.log(`[backend] exited code=${code} signal=${signal}`);
    logMain(`[backend] exited code=${code} signal=${signal}`);
  });

  return backendProc;
}

function stopBackend() {
  if (!backendProc) return;

  const pid = backendProc.pid;
  logMain(`[main] stopBackend pid=${pid || "?"}`);

  // Best-effort: ensure process tree is gone on Windows. Use spawnSync so the kill
  // isn't aborted by the app quitting immediately after "before-quit".
  if (process.platform === "win32" && pid) {
    const systemRoot = process.env.SystemRoot || process.env.WINDIR || "C:\\Windows";
    const taskkillExe = path.join(systemRoot, "System32", "taskkill.exe");
    const args = ["/pid", String(pid), "/T", "/F"];

    try {
      const exe = fs.existsSync(taskkillExe) ? taskkillExe : "taskkill";
      const r = spawnSync(exe, args, { stdio: "ignore", windowsHide: true, timeout: 5000 });
      if (r?.error) logMain(`[main] taskkill failed: ${r.error?.message || r.error}`);
      else if (typeof r?.status === "number" && r.status !== 0)
        logMain(`[main] taskkill exit code=${r.status}`);
    } catch (err) {
      logMain(`[main] taskkill exception: ${err?.message || err}`);
    }
  }

  // Fallback: kill the direct process (taskkill might be missing from PATH in some envs).
  try {
    backendProc.kill();
  } catch {}
}

async function stopBackendAndWait({ timeoutMs = 10_000 } = {}) {
  if (!backendProc) return;
  const proc = backendProc;

  await new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };

    const timer = setTimeout(finish, timeoutMs);

    try {
      proc.once("exit", () => {
        clearTimeout(timer);
        finish();
      });
    } catch {}

    try {
      stopBackend();
    } catch {
      clearTimeout(timer);
      finish();
    }
  });
}

async function restartBackend({ timeoutMs = 30_000 } = {}) {
  await stopBackendAndWait({ timeoutMs: 10_000 });
  startBackend();
  await waitForBackend({ timeoutMs });
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

async function waitForBackend({ timeoutMs, healthUrl } = {}) {
  const url = String(healthUrl || getBackendHealthUrl()).trim();
  const startedAt = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const code = await httpGet(url);
      if (code >= 200 && code < 500) return;
    } catch {}

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`Backend did not become ready in ${timeoutMs}ms: ${url}`);
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

  ipcMain.handle("backend:getPort", () => {
    try {
      return getBackendPort();
    } catch (err) {
      logMain(`[main] backend:getPort failed: ${err?.message || err}`);
      return DEFAULT_BACKEND_PORT;
    }
  });

  ipcMain.handle("backend:setPort", async (_event, port) => {
    if (backendPortChangeInProgress) throw new Error("端口切换中，请稍后重试");
    if (!app.isPackaged) {
      throw new Error("开发模式不支持界面修改端口；请设置 WECHAT_TOOL_PORT 环境变量后重启");
    }

    const nextPort = parsePort(port);
    if (nextPort == null) throw new Error("端口无效，请输入 1-65535 的整数");

    const prevPort = getBackendPort();
    if (nextPort === prevPort) {
      return { success: true, changed: false, port: prevPort, uiUrl: getBackendUiUrl() };
    }

    const bindHost = getBackendBindHost();
    const ok = await isPortAvailable(nextPort, bindHost);
    if (!ok) throw new Error(`端口 ${nextPort} 已被占用，请换一个端口`);

    backendPortChangeInProgress = true;
    try {
      setBackendPortSetting(nextPort);
      try {
        await restartBackend({ timeoutMs: 30_000 });
      } catch (err) {
        // Roll back to the previous port so the UI can keep working.
        setBackendPortSetting(prevPort);
        try {
          await restartBackend({ timeoutMs: 30_000 });
        } catch {}
        throw err;
      }

      const uiUrl = getBackendUiUrl();
      setTimeout(() => {
        try {
          if (!mainWindow || mainWindow.isDestroyed()) return;
          void loadWithRetry(mainWindow, uiUrl);
        } catch (err) {
          logMain(`[main] failed to reload UI after backend port change: ${err?.message || err}`);
        }
      }, 50);

      return { success: true, changed: true, port: nextPort, uiUrl };
    } finally {
      backendPortChangeInProgress = false;
    }
  });

  ipcMain.handle("app:getVersion", () => {
    try {
      return app.getVersion();
    } catch (err) {
      logMain(`[main] getVersion failed: ${err?.message || err}`);
      return "";
    }
  });

  ipcMain.handle("app:checkForUpdates", async () => {
    return await checkForUpdatesInternal();
  });

  ipcMain.handle("app:downloadAndInstall", async () => {
    return await downloadAndInstallInternal();
  });

  ipcMain.handle("app:installUpdate", async () => {
    if (!isAutoUpdateEnabled()) {
      throw new Error("自动更新已禁用");
    }
    initAutoUpdater();
    if (!updateDownloaded) {
      throw new Error("更新尚未下载完成");
    }

    try {
      autoUpdater.quitAndInstall(false, true);
      return { success: true };
    } catch (err) {
      const message = err?.message || String(err);
      logMain(`[main] installUpdate failed: ${message}`);
      throw new Error(message);
    }
  });

  ipcMain.handle("app:ignoreUpdate", async (_event, version) => {
    setIgnoredUpdateVersion(version);
    return { success: true };
  });

  ipcMain.handle("dialog:chooseDirectory", async (_event, options) => {
    try {
      const result = await dialog.showOpenDialog({
        title: String(options?.title || "选择文件夹"),
        properties: ["openDirectory", "createDirectory"],
      });
      return {
        canceled: !!result?.canceled,
        filePaths: Array.isArray(result?.filePaths) ? result.filePaths : [],
      };
    } catch (err) {
      logMain(`[main] dialog:chooseDirectory failed: ${err?.message || err}`);
      return {
        canceled: true,
        filePaths: [],
      };
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
    (app.isPackaged ? getBackendUiUrl() : "http://localhost:3000");

  await loadWithRetry(win, startUrl);

  // Auto-check updates after the UI has loaded (packaged builds only).
  checkForUpdatesOnStartup();

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

if (gotSingleInstanceLock) {
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
}
