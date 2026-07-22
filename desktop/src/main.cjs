const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  nativeImage,
  ipcMain,
  globalShortcut,
  dialog,
  shell,
  session,
} = require("electron");
let autoUpdater = null;
let autoUpdaterLoadError = null;
try {
  ({ autoUpdater } = require("electron-updater"));
} catch (err) {
  autoUpdaterLoadError = err;
}
const { spawn, spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const net = require("net");
const os = require("os");
const path = require("path");
const { Worker } = require("worker_threads");
const {
  cleanupOutputDirectoryBackup,
  getDefaultOutputDirPath,
  getEffectiveOutputDirPath,
  isPathInsideOrEqual,
  isPathLexicallyInsideOrEqual,
  normalizeDirectoryPath,
  pathsReferToSameLocation,
} = require("./output-dir.cjs");
const {
  parseDesktopSettingsText,
  writeDesktopSettingsFileAtomic,
} = require("./desktop-settings.cjs");
const {
  isBackendHealthResponse,
  isWcdbSidecarHealthResponse,
  resolveBackendStartupTimeoutMs,
  shouldRetryBackendOnDifferentPort,
  shouldWaitForBackendReplacement,
} = require("./backend-startup.cjs");

const DEFAULT_BACKEND_HOST = "127.0.0.1";
const LAN_BACKEND_HOST = "0.0.0.0";
const DEFAULT_BACKEND_PORT = parsePort(process.env.WECHAT_TOOL_PORT) ?? 10392;
const DESKTOP_TITLEBAR_HEIGHT = 32;

let backendProc = null;
let wcdbSidecarProc = null;
let wcdbSidecarPort = null;
let wcdbSidecarUrl = "";
let wcdbSidecarToken = "";
let wcdbSidecarRestartTimer = null;
let wcdbSidecarRestartInProgress = false;
let wcdbSidecarRestartHistory = [];
let wcdbSidecarHealthTimer = null;
let wcdbSidecarHealthInFlight = false;
let wcdbSidecarHealthFailures = 0;
let wcdbSidecarHealthGeneration = 0;
const WCDB_SIDECAR_HEALTH_FAILURE_LIMIT = 15;
let resolvedDataDir = null;
let mainWindow = null;
let mainWindowLaunchPromise = null;
let initialStartupPromise = null;
let tray = null;
let isQuitting = false;
let desktopSettings = null;
let backendPortChangeInProgress = false;
let outputDirChangeInProgress = false;
let accountDataChangeInProgress = false;
let outputDirChangeProgressState = null;

function normalizeTitleBarTheme(value) {
  return String(value || "").trim().toLowerCase() === "dark" ? "dark" : "light";
}

function getTitleBarOverlayOptions(theme) {
  const normalized = normalizeTitleBarTheme(theme);
  return {
    // Keep native window controls, but let the renderer/theme show through instead of
    // Electron painting the default gray title-bar strip behind the buttons.
    color: "rgba(0, 0, 0, 0)",
    symbolColor: normalized === "dark" ? "#d0d0d0" : "#111111",
    height: DESKTOP_TITLEBAR_HEIGHT,
  };
}

function setWindowTitleBarTheme(win, theme) {
  if (process.platform === "darwin") return false;
  if (!win || typeof win.setTitleBarOverlay !== "function") return false;
  try {
    win.setTitleBarOverlay(getTitleBarOverlayOptions(theme));
    return true;
  } catch (err) {
    logMain(`[main] setTitleBarOverlay failed: ${err?.message || err}`);
    return false;
  }
}

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
      if (app.isReady()) requestMainWindow("second-instance");
      else app.whenReady().then(() => requestMainWindow("second-instance"));
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
  const envHost = String(process.env.WECHAT_TOOL_HOST || "").trim();
  if (envHost === LAN_BACKEND_HOST || envHost === "::") return LAN_BACKEND_HOST;
  if (envHost === DEFAULT_BACKEND_HOST || envHost === "localhost" || envHost === "::1") return DEFAULT_BACKEND_HOST;
  if (!app.isPackaged) return DEFAULT_BACKEND_HOST;
  return loadDesktopSettings()?.mcpLanAccessEnabled ? LAN_BACKEND_HOST : DEFAULT_BACKEND_HOST;
}

function getBackendAccessHost() {
  // 0.0.0.0 / :: are fine bind hosts, but not a reachable client destination.
  const host = String(getBackendBindHost() || "").trim();
  if (host === "0.0.0.0" || host === "::") return "127.0.0.1";
  return host || "127.0.0.1";
}

function getInterfacePenalty(name) {
  const lower = String(name || "").toLowerCase();
  if (/(docker|hyper-v|loopback|npcap|tailscale|virtual|virtualbox|vmware|vethernet|wsl|zerotier)/i.test(lower)) {
    return 30;
  }
  if (/(ethernet|wi-fi|wifi|wireless|wlan|以太|无线)/i.test(lower)) {
    return 0;
  }
  return 10;
}

function isReachableClientIpv4(address) {
  const text = String(address || "").trim();
  const parts = text.split(".");
  if (parts.length !== 4) return false;
  const nums = parts.map((part) => Number(part));
  if (!nums.every((n) => Number.isInteger(n) && n >= 0 && n <= 255)) return false;
  if (nums[0] === 0 || nums[0] === 127 || nums[0] >= 224) return false;
  if (nums[0] === 169 && nums[1] === 254) return false;
  return true;
}

function isPrivateIpv4(address) {
  const nums = String(address || "").trim().split(".").map((part) => Number(part));
  if (nums.length !== 4 || !nums.every((n) => Number.isInteger(n))) return false;
  return (
    nums[0] === 10 ||
    (nums[0] === 172 && nums[1] >= 16 && nums[1] <= 31) ||
    (nums[0] === 192 && nums[1] === 168)
  );
}

function getLanAccessHost(defaultHost = DEFAULT_BACKEND_HOST) {
  const candidates = [];
  const seen = new Set();
  const addCandidate = (address, interfaceName = "", sourceOrder = 0) => {
    const value = String(address || "").trim();
    if (!isReachableClientIpv4(value) || seen.has(value)) return;
    seen.add(value);
    candidates.push([
      isPrivateIpv4(value) ? 0 : 1,
      getInterfacePenalty(interfaceName),
      sourceOrder,
      value,
    ]);
  };

  try {
    const interfaces = os.networkInterfaces();
    for (const [name, addresses] of Object.entries(interfaces || {})) {
      for (const item of addresses || []) {
        if (!item || (item.family !== "IPv4" && item.family !== 4) || item.internal) continue;
        addCandidate(item.address, name, 0);
      }
    }
  } catch {}

  candidates.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return candidates[0]?.[3] || defaultHost;
}

function getMcpAccessHost(bindHost = getBackendBindHost()) {
  const host = String(bindHost || "").trim();
  if (host === LAN_BACKEND_HOST || host === "::") return getLanAccessHost(DEFAULT_BACKEND_HOST);
  return host || DEFAULT_BACKEND_HOST;
}

function getMcpAccessInfo(bindHost = getBackendBindHost(), port = getBackendPort()) {
  const accessHost = getMcpAccessHost(bindHost);
  const origin = `http://${formatHostForUrl(accessHost)}:${port}`;
  return {
    accessHost,
    mcpEndpoint: `${origin}/mcp`,
    skillBundleUrl: `${origin}/mcp/skill/bundle`,
    skillMarkdownUrl: `${origin}/mcp/skill`,
  };
}

function getBackendPort() {
  const envPort = parsePort(process.env.WECHAT_TOOL_PORT);
  if (envPort != null) return envPort;
  // In dev we intentionally ignore persisted packaged-app settings so the
  // launcher can keep Electron, Nuxt devProxy and the backend child aligned.
  if (!app.isPackaged) return DEFAULT_BACKEND_PORT;
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

function getMcpLanAccessEnabled() {
  return getBackendBindHost() === LAN_BACKEND_HOST;
}

function setMcpLanAccessSetting(enabled) {
  loadDesktopSettings();
  desktopSettings.mcpLanAccessEnabled = !!enabled;
  persistDesktopSettings();
  process.env.WECHAT_TOOL_HOST = desktopSettings.mcpLanAccessEnabled ? LAN_BACKEND_HOST : DEFAULT_BACKEND_HOST;
  return desktopSettings.mcpLanAccessEnabled;
}

function getBackendHealthUrl() {
  const host = formatHostForUrl(getBackendAccessHost());
  const port = getBackendPort();
  return `http://${host}:${port}/api/health`;
}

function getBackendStartupTimeoutMs() {
  return resolveBackendStartupTimeoutMs({
    isPackaged: app.isPackaged,
    envValue: process.env.WECHAT_TOOL_BACKEND_STARTUP_TIMEOUT_MS,
  });
}

function getBackendUiUrl() {
  const host = formatHostForUrl(getBackendAccessHost());
  const port = getBackendPort();
  return `http://${host}:${port}/`;
}

function getDesktopUiUrl() {
  const explicit = String(process.env.ELECTRON_START_URL || "").trim();
  if (explicit) return explicit;
  return app.isPackaged ? getBackendUiUrl() : "http://localhost:3000";
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

function getEphemeralPort(host) {
  return new Promise((resolve) => {
    try {
      const srv = net.createServer();
      srv.unref();
      srv.once("error", () => resolve(null));
      srv.listen({ port: 0, host }, () => {
        const addr = srv.address();
        const p = addr && typeof addr === "object" ? Number(addr.port) : null;
        srv.close(() => resolve(Number.isInteger(p) ? p : null));
      });
    } catch {
      resolve(null);
    }
  });
}

async function chooseAvailablePort(preferredPort, host) {
  const preferred = parsePort(preferredPort);
  if (preferred != null && (await isPortAvailable(preferred, host))) return preferred;

  // Keep the port close to the user's expectation when possible.
  if (preferred != null) {
    for (let i = 1; i <= 50; i += 1) {
      const cand = preferred + i;
      if (cand > 65535) break;
      if (await isPortAvailable(cand, host)) return cand;
    }
  }

  // Fall back to an OS-chosen ephemeral port.
  const random = await getEphemeralPort(host);
  if (random != null && (await isPortAvailable(random, host))) return random;

  return null;
}

async function ensureBackendPortAvailableOnStartup() {
  // Avoid surprising behavior in dev: the frontend dev server expects a stable backend port.
  if (!app.isPackaged) return getBackendPort();

  const bindHost = getBackendBindHost();
  const currentPort = getBackendPort();
  const ok = await isPortAvailable(currentPort, bindHost);
  if (ok) return currentPort;

  const chosen = await chooseAvailablePort(currentPort, bindHost);
  if (chosen == null) {
    logMain(`[main] backend port unavailable: ${currentPort} host=${bindHost}; failed to find a free port`);
    return currentPort;
  }

  try {
    setBackendPortSetting(chosen);
    logMain(`[main] backend port ${currentPort} unavailable; switched to ${chosen}`);
  } catch (err) {
    logMain(`[main] failed to persist backend port ${chosen}: ${err?.message || err}`);
  }

  return getBackendPort();
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
  try {
    const dir = app.getPath("userData");
    if (!dir) return null;
    fs.mkdirSync(dir, { recursive: true });
    return dir;
  } catch {
    return null;
  }
}

function safeNormalizeDirectory(value) {
  try {
    return normalizeDirectoryPath(value || "");
  } catch {
    return "";
  }
}

function getDefaultOutputDir() {
  const dataDir = resolveDataDir();
  if (!dataDir) return null;
  try {
    return getDefaultOutputDirPath(dataDir);
  } catch {
    return null;
  }
}

function syncOutputDirEnv(nextDir) {
  const normalized = safeNormalizeDirectory(nextDir);
  if (normalized) process.env.WECHAT_TOOL_OUTPUT_DIR = normalized;
  else delete process.env.WECHAT_TOOL_OUTPUT_DIR;
}

function normalizePendingOutputDirValue(value) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text) return "";
  try {
    return normalizeDirectoryPath(text);
  } catch {
    return null;
  }
}

function resolveOutputDir({ ensureExists = true } = {}) {
  const dataDir = resolveDataDir();
  if (!dataDir) return null;

  const envOutputDir = safeNormalizeDirectory(process.env.WECHAT_TOOL_OUTPUT_DIR || "");
  // Allow dev-mode desktop runs to persist the chosen output directory too.
  // An explicit environment variable still wins so local launch overrides keep working.
  const settings = loadDesktopSettings();
  const settingsOutputDir = safeNormalizeDirectory(settings?.outputDir || "");

  let chosen = null;
  try {
    chosen = getEffectiveOutputDirPath({
      dataDir,
      envOutputDir,
      settingsOutputDir,
    });
  } catch {
    chosen = getDefaultOutputDir();
  }
  if (!chosen) return null;

  const transactionPending = settings?.pendingOutputDir !== null;
  if (ensureExists && !outputDirChangeInProgress && !transactionPending) {
    try {
      fs.mkdirSync(chosen, { recursive: true });
    } catch {}
  }

  syncOutputDirEnv(chosen);
  return chosen;
}

function sanitizeAccountName(account) {
  const name = String(account || "").trim();
  if (!name) throw new Error("缺少账号参数");
  if (name === "." || name === "..") throw new Error("账号参数非法");
  if (name.includes("/") || name.includes("\\")) throw new Error("账号参数非法");
  return name;
}

function listDecryptedAccountsOnDisk(databasesDir) {
  try {
    if (!fs.existsSync(databasesDir)) return [];
  } catch {
    return [];
  }

  let entries = [];
  try {
    entries = fs.readdirSync(databasesDir, { withFileTypes: true });
  } catch {
    return [];
  }

  const accounts = [];
  for (const entry of entries) {
    try {
      if (!entry || !entry.isDirectory()) continue;
      const accountDir = path.join(databasesDir, entry.name);
      const hasSession = fs.existsSync(path.join(accountDir, "session.db"));
      const hasContact = fs.existsSync(path.join(accountDir, "contact.db"));
      if (hasSession && hasContact) accounts.push(String(entry.name || ""));
    } catch {}
  }
  accounts.sort((a, b) => a.localeCompare(b));
  return accounts;
}

function resolveAccountDirInOutput(account) {
  const dataDir = resolveDataDir();
  if (!dataDir) throw new Error("无法定位数据目录");

  const outputDir = resolveOutputDir();
  if (!outputDir) throw new Error("无法定位 output 目录");
  const databasesDir = path.join(outputDir, "databases");
  const accountName = sanitizeAccountName(account);

  const base = path.resolve(databasesDir);
  const accountDir = path.resolve(path.join(databasesDir, accountName));
  if (accountDir !== base && !accountDir.startsWith(base + path.sep)) {
    throw new Error("账号路径非法");
  }

  return {
    dataDir,
    outputDir,
    databasesDir,
    accountName,
    accountDir,
  };
}

function getAccountInfoFromDisk(account) {
  const { accountName, accountDir } = resolveAccountDirInOutput(account);
  if (!fs.existsSync(accountDir) || !fs.statSync(accountDir).isDirectory()) {
    throw new Error("账号数据不存在");
  }

  let entries = [];
  try {
    entries = fs.readdirSync(accountDir, { withFileTypes: true });
  } catch {}
  const dbFiles = entries
    .filter((e) => !!e && e.isFile() && String(e.name || "").toLowerCase().endsWith(".db"))
    .map((e) => String(e.name || ""))
    .sort((a, b) => a.localeCompare(b));

  let sessionUpdatedAt = 0;
  try {
    const st = fs.statSync(path.join(accountDir, "session.db"));
    sessionUpdatedAt = Math.floor(Number(st?.mtimeMs || 0) / 1000);
  } catch {}

  return {
    status: "success",
    account: accountName,
    path: accountDir,
    database_count: dbFiles.length,
    databases: dbFiles,
    session_updated_at: sessionUpdatedAt,
  };
}

function removeAccountFromKeyStore(outputDir, accountName) {
  const keyStorePath = path.join(outputDir, "account_keys.json");
  try {
    if (!fs.existsSync(keyStorePath)) return false;
    const raw = fs.readFileSync(keyStorePath, { encoding: "utf8" });
    const parsed = JSON.parse(raw || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return false;
    if (!Object.prototype.hasOwnProperty.call(parsed, accountName)) return false;
    delete parsed[accountName];
    fs.writeFileSync(keyStorePath, JSON.stringify(parsed, null, 2), { encoding: "utf8" });
    return true;
  } catch {
    return false;
  }
}

async function deleteAccountDataFromDisk(account) {
  const { outputDir, databasesDir, accountName, accountDir } = resolveAccountDirInOutput(account);
  if (!fs.existsSync(accountDir) || !fs.statSync(accountDir).isDirectory()) {
    throw new Error("账号数据不存在");
  }

  const wasBackendRunning = !!backendProc;
  let restartError = null;
  let result = null;

  if (wasBackendRunning) {
    const stopped = await stopBackendAndWait({ timeoutMs: 10_000 });
    if (!stopped) {
      throw new Error("后端进程未能在 10 秒内停止，为避免删除仍在使用的数据，已取消操作");
    }
  }

  try {
    const exportsDir = path.join(outputDir, "exports", accountName);
    try {
      fs.rmSync(exportsDir, { recursive: true, force: true });
    } catch {}

    fs.rmSync(accountDir, { recursive: true, force: true });
    const removedKeyCache = removeAccountFromKeyStore(outputDir, accountName);
    const accounts = listDecryptedAccountsOnDisk(databasesDir);
    result = {
      status: "success",
      deleted_account: accountName,
      accounts,
      default_account: accounts.length ? accounts[0] : null,
      removed_key_cache: removedKeyCache,
    };
  } finally {
    if (wasBackendRunning) {
      try {
        startBackend();
        await waitForBackend({ timeoutMs: getBackendStartupTimeoutMs() });
      } catch (err) {
        restartError = err;
        logMain(`[main] failed to restart backend after deleteAccountData: ${err?.message || err}`);
      }
    }
  }

  if (restartError) {
    throw new Error(`删除完成，但后端重启失败：${restartError?.message || restartError}`);
  }
  if (!result) throw new Error("删除账号数据失败");
  return result;
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
  // in the per-user data dir.
  //
  // NOTE: We intentionally avoid creating a junction/symlink inside the install directory.
  // Some uninstall/update flows may traverse reparse points and delete the target directory,
  // causing data loss (the install dir is removed on every update/reinstall).
  // These helper files are Windows installer affordances. Writing beside the
  // executable on macOS would mutate Contents/MacOS and invalidate the app's
  // code signature after the first launch.
  if (!app.isPackaged || process.platform !== "win32") return;

  const exeDir = getExeDir();
  const target = resolveOutputDir();
  if (!exeDir || !target) return;
  const legacyLinkPath = path.join(exeDir, "output");
  const legacyPathOverlapsConfiguredOutput =
    isPathLexicallyInsideOrEqual(legacyLinkPath, target) ||
    isPathLexicallyInsideOrEqual(target, legacyLinkPath);

  // Ensure the real output dir exists.
  try {
    fs.mkdirSync(target, { recursive: true });
  } catch {}

  // Best-effort: remove a legacy junction/symlink at `exeDir/output` so uninstallers can't
  // accidentally traverse it and delete the real per-user output directory.
  if (legacyPathOverlapsConfiguredOutput) {
    logMain(`[main] preserving configured output path inside install directory: ${target}`);
  } else {
    try {
      const st = fs.lstatSync(legacyLinkPath);
      if (st.isSymbolicLink()) {
        try {
          fs.unlinkSync(legacyLinkPath);
          logMain(`[main] removed legacy output link: ${legacyLinkPath}`);
        } catch (err) {
          logMain(`[main] failed to remove legacy output link: ${err?.message || err}`);
        }
      } else if (st.isDirectory()) {
        const entries = fs.readdirSync(legacyLinkPath);
        if (Array.isArray(entries) && entries.length === 0) {
          // Remove an empty real directory to reduce confusion (it will be recreated by the backend if needed).
          fs.rmdirSync(legacyLinkPath);
        } else {
          // Do not overwrite non-empty directories to avoid data loss.
          // Note: data stored here will be wiped on update/reinstall.
          logMain(
            `[main] output dir exists in install dir (not a link): ${legacyLinkPath}. real data dir output: ${target}`
          );
        }
      } else {
        logMain(`[main] output path exists and is not a directory/link: ${legacyLinkPath}`);
      }
    } catch {
      // Doesn't exist yet.
    }
  }

  // Best-effort: drop a helper file next to the exe so users can find the real data.
  // This avoids the data-loss risks of using junctions/symlinks under the install directory.
  try {
    const p = path.join(exeDir, "output-location.txt");
    const text = `WeChatDataAnalysis data directory\n\nOutput folder:\n${target}\n`;
    fs.writeFileSync(p, text, { encoding: "utf8" });
  } catch {}

  try {
    const p = path.join(exeDir, "output-location.path");
    fs.writeFileSync(p, `${target}\n`, { encoding: "utf8" });
  } catch {}

  try {
    const p = path.join(exeDir, "open-output.cmd");
    const text = `@echo off\r\nexplorer \"${target}\"\r\n`;
    fs.writeFileSync(p, text, { encoding: "utf8" });
  } catch {}
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

function getPackagedUiDir() {
  if (!app.isPackaged) return null;
  try {
    return path.join(process.resourcesPath, "ui");
  } catch {
    return null;
  }
}

function readPackagedUiBuildId() {
  const uiDir = getPackagedUiDir();
  if (!uiDir) return "";

  try {
    const indexPath = path.join(uiDir, "index.html");
    if (!fs.existsSync(indexPath)) return "";
    const html = fs.readFileSync(indexPath, { encoding: "utf8" });
    const match =
      html.match(/buildId:"([^"]+)"/) ||
      html.match(/\/_payload\.json\?([^"'&<>\s]+)/) ||
      html.match(/data-src="\/_payload\.json\?([^"]+)"/);
    return String(match?.[1] || "").trim();
  } catch (err) {
    logMain(`[main] failed to read packaged UI build id: ${err?.message || err}`);
    return "";
  }
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
    // When enabled, the backend binds to 0.0.0.0 so phone clients can reach /mcp.
    mcpLanAccessEnabled: false,
    // Custom output dir; empty string means use the default dataDir/output.
    outputDir: "",
    // Pending output dir written before migration so interrupted transactions can resume.
    pendingOutputDir: null,
    // Last startup/apply failure when changing output dir.
    lastOutputDirError: "",
    // Tracks the packaged UI build so we can invalidate Chromium's HTTP cache
    // after upgrades without wiping user data/localStorage.
    lastSeenUiBuildId: "",
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
    const parsed = parseDesktopSettingsText(raw);
    desktopSettings = { ...defaults, ...(parsed && typeof parsed === "object" ? parsed : {}) };
    desktopSettings.backendPort = parsePort(desktopSettings.backendPort) ?? defaults.backendPort;
    desktopSettings.mcpLanAccessEnabled = !!desktopSettings.mcpLanAccessEnabled;
    desktopSettings.outputDir = safeNormalizeDirectory(desktopSettings.outputDir || "");
    desktopSettings.pendingOutputDir =
      parsed && typeof parsed === "object" && Object.prototype.hasOwnProperty.call(parsed, "pendingOutputDir")
        ? normalizePendingOutputDirValue(parsed.pendingOutputDir)
        : defaults.pendingOutputDir;
    desktopSettings.lastOutputDirError = String(desktopSettings.lastOutputDirError || "").trim();
  } catch (err) {
    desktopSettings = { ...defaults };
    logMain(`[main] failed to load settings: ${err?.message || err}`);
  }

  return desktopSettings;
}

function persistDesktopSettings({ throwOnError = false } = {}) {
  const p = getDesktopSettingsPath();
  if (!p || !desktopSettings) {
    if (throwOnError) throw new Error("无法定位桌面设置文件");
    return false;
  }

  try {
    writeDesktopSettingsFileAtomic(p, desktopSettings);
    return true;
  } catch (err) {
    logMain(`[main] failed to persist settings: ${err?.message || err}`);
    if (throwOnError) {
      const wrapped = new Error(`无法保存桌面设置：${err?.message || err}`);
      wrapped.code = err?.code;
      wrapped.cause = err;
      throw wrapped;
    }
    return false;
  }
}

function snapshotOutputDirSettings() {
  loadDesktopSettings();
  return {
    outputDir: desktopSettings.outputDir,
    pendingOutputDir: desktopSettings.pendingOutputDir,
    lastOutputDirError: desktopSettings.lastOutputDirError,
  };
}

function setPendingOutputDirSetting(nextDir, { throwOnError = false } = {}) {
  loadDesktopSettings();
  const previousValue = desktopSettings.pendingOutputDir;
  desktopSettings.pendingOutputDir = normalizePendingOutputDirValue(nextDir);
  try {
    persistDesktopSettings({ throwOnError });
  } catch (err) {
    desktopSettings.pendingOutputDir = previousValue;
    throw err;
  }
  return desktopSettings.pendingOutputDir;
}

function setOutputDirLastError(message) {
  loadDesktopSettings();
  desktopSettings.lastOutputDirError = String(message || "").trim();
  persistDesktopSettings();
  return desktopSettings.lastOutputDirError;
}

function commitOutputDirSettings(nextDir) {
  loadDesktopSettings();
  const previousSettings = snapshotOutputDirSettings();
  const defaultDir = getDefaultOutputDir();
  const normalized = safeNormalizeDirectory(nextDir || "");
  desktopSettings.outputDir =
    !normalized || (defaultDir && pathsReferToSameLocation(normalized, defaultDir)) ? "" : normalized;
  desktopSettings.pendingOutputDir = null;
  desktopSettings.lastOutputDirError = "";
  syncOutputDirEnv(desktopSettings.outputDir || defaultDir || "");

  try {
    persistDesktopSettings({ throwOnError: true });
  } catch (err) {
    desktopSettings.outputDir = previousSettings.outputDir;
    desktopSettings.pendingOutputDir = previousSettings.pendingOutputDir;
    desktopSettings.lastOutputDirError = previousSettings.lastOutputDirError;
    syncOutputDirEnv(desktopSettings.outputDir || defaultDir || "");
    throw err;
  }
}

function getOutputDirInfo() {
  loadDesktopSettings();
  const defaultPath = getDefaultOutputDir() || "";
  const currentPath = resolveOutputDir() || defaultPath;
  const hasPending = desktopSettings.pendingOutputDir !== null;
  const canChange = !!defaultPath && !!currentPath;
  const pendingPath =
    desktopSettings.pendingOutputDir === null
      ? ""
      : desktopSettings.pendingOutputDir === ""
        ? defaultPath
        : safeNormalizeDirectory(desktopSettings.pendingOutputDir);
  return {
    path: currentPath || "",
    defaultPath,
    isDefault:
      !!currentPath && !!defaultPath && pathsReferToSameLocation(currentPath, defaultPath),
    pendingPath,
    hasPending,
    lastError: String(desktopSettings.lastOutputDirError || "").trim(),
    canChange,
    changeUnavailableReason: canChange ? "" : "无法定位 output 目录",
  };
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

async function applyOutputDirChange(nextValue) {
  const defaultPath = getDefaultOutputDir();
  const currentPath = resolveOutputDir({ ensureExists: false });
  if (!defaultPath || !currentPath) {
    throw new Error("无法定位 output 目录");
  }

  const rawText = String(nextValue ?? "").trim();
  const nextPath = rawText ? normalizeDirectoryPath(rawText) : defaultPath;
  const exeDir = app.isPackaged ? getExeDir() : null;
  if (
    exeDir &&
    (isPathLexicallyInsideOrEqual(exeDir, nextPath) || isPathInsideOrEqual(exeDir, nextPath))
  ) {
    throw new Error("output 目录不能位于安装目录内，更新或卸载时可能导致数据丢失");
  }

  if (pathsReferToSameLocation(nextPath, currentPath)) {
    commitOutputDirSettings(nextPath);
    ensureOutputLink();
    const info = getOutputDirInfo();
    return {
      success: true,
      changed: false,
      path: info.path,
      defaultPath: info.defaultPath,
      isDefault: info.isDefault,
      pendingPath: info.pendingPath,
      backupPath: "",
      sourceWasEmpty: false,
      message: "output 目录未变化",
    };
  }

  let wasBackendRunning = false;
  let migration = null;
  let migrationAttempted = false;
  let settingsSwitched = false;
  let retainedBackupPath = "";
  let backupCleanupWarning = "";

  try {
    logMain(`[main] output dir change requested current=${currentPath} target=${nextPath}`);
    // Persist the target before touching either directory. A restart can then
    // replay or recover every interruption point in the filesystem commit.
    setPendingOutputDirSetting(nextPath, { throwOnError: true });
    await waitForWcdbRuntimeRestartToSettle();
    wasBackendRunning = !!backendProc;
    setOutputDirChangeProgressState({
      active: true,
      stage: "preparing",
      message: wasBackendRunning ? "正在暂停后端并准备迁移 output 目录" : "正在准备迁移 output 目录",
      percent: 1,
    });

    if (wasBackendRunning) {
      const stopped = await stopBackendAndWait({ timeoutMs: 10_000 });
      if (!stopped || backendProc) {
        throw new Error("后端进程未能在 10 秒内停止，为避免日志或数据文件被占用，已取消迁移");
      }
    }

    migrationAttempted = true;
    migration = await runOutputDirWorker(
      "migrate",
      {
        currentDir: currentPath,
        nextDir: nextPath,
      },
      (progress) => {
        setOutputDirChangeProgressState({
          active: true,
          ...progress,
        });
      }
    );

    setOutputDirChangeProgressState({
      active: true,
      stage: "switching",
      message: "正在应用新的 output 目录设置",
      percent: 99,
      currentFile: "",
    });

    commitOutputDirSettings(nextPath);
    settingsSwitched = true;
    ensureOutputLink();

    if (wasBackendRunning) {
      setOutputDirChangeProgressState({
        active: true,
        stage: "restarting",
        message: "正在重启后端并应用新的 output 目录",
        percent: 99,
      });
      startBackend();
      await waitForBackend({ timeoutMs: getBackendStartupTimeoutMs() });
    }

    retainedBackupPath = migration?.backupDir || "";
    if (retainedBackupPath) {
      try {
        cleanupOutputDirectoryBackup(retainedBackupPath);
        retainedBackupPath = "";
      } catch (cleanupErr) {
        backupCleanupWarning = `；旧 output 目录未能自动删除：${cleanupErr?.message || cleanupErr}`;
        logMain(
          `[main] failed to clean output dir backup ${retainedBackupPath}: ${cleanupErr?.message || cleanupErr}`
        );
      }
    }

    setOutputDirChangeProgressState({
      active: true,
      stage: "complete",
      message: migration?.sourceWasEmpty ? "output 目录已切换" : "output 目录已迁移并切换",
      percent: 100,
    });
    const info = getOutputDirInfo();
    const successMessage =
      (migration?.sourceWasEmpty ? "output 目录已切换" : "output 目录已迁移并切换") + backupCleanupWarning;
    const result = {
      success: true,
      changed: true,
      path: info.path,
      defaultPath: info.defaultPath,
      isDefault: info.isDefault,
      pendingPath: info.pendingPath,
      backupPath: retainedBackupPath,
      sourceWasEmpty: !!migration?.sourceWasEmpty,
      message: successMessage,
    };
    logMain(`[main] output dir change completed current=${currentPath} target=${info.path}`);
    return result;
  } catch (err) {
    const message = err?.message || String(err);
    let rollbackMessage = "";
    let rollbackCompleted = false;

    // Once settings are durably committed, keep the verified target and its
    // backup even if backend startup fails. Rolling it back under a live or
    // slow-starting process can delete the only good copy.
    if (migration?.changed && settingsSwitched) {
      retainedBackupPath = migration?.backupDir || "";
      const preservedMessage =
        `output 目录已迁移到 ${nextPath}，但后端重启失败：${message}` +
        (retainedBackupPath ? `；旧目录备份已保留：${retainedBackupPath}` : "");
      setOutputDirLastError(preservedMessage);
      ensureOutputLink();
      throw new Error(preservedMessage);
    }

    // A worker can terminate after promoting the target and renaming the old
    // source, but before its result message reaches this process. In that state
    // `migration` is still null. Never recreate the missing old directory or
    // restart the backend against it; the persisted pending target lets the
    // next startup deterministically resume the transaction.
    let currentDirectoryStillExists = false;
    try {
      currentDirectoryStillExists = fs.statSync(currentPath).isDirectory();
    } catch {}
    if (migrationAttempted && !migration && !currentDirectoryStillExists) {
      syncOutputDirEnv(currentPath);
      const recoveryError = new Error(
        `output 目录迁移状态尚未确认：${message}；为避免写入空旧目录，请重启应用以自动恢复`
      );
      recoveryError.outputDirRecoveryRequired = true;
      throw recoveryError;
    }

    if (migration?.changed) {
      try {
        setOutputDirChangeProgressState({
          active: true,
          stage: "rolling-back",
          message: "迁移失败，正在回滚 output 目录",
          percent: 99,
        });
        await runOutputDirWorker("rollback", {
          previousDir: currentPath,
          currentDir: nextPath,
          backupDir: migration.backupDir,
          sourceWasEmpty: migration.sourceWasEmpty,
        });
        rollbackCompleted = true;
      } catch (rollbackErr) {
        logMain(`[main] output dir rollback failed: ${rollbackErr?.message || rollbackErr}`);
        rollbackMessage = `；回滚失败：${rollbackErr?.message || rollbackErr}`;
        if (migration?.backupDir) {
          rollbackMessage += `；备份目录：${migration.backupDir}`;
        }
      }
    }

    syncOutputDirEnv(currentPath);
    if (!migration?.changed || rollbackCompleted) ensureOutputLink();

    if (rollbackMessage) {
      const recoveryError = new Error(`切换 output 目录失败：${message}${rollbackMessage}`);
      recoveryError.outputDirRecoveryRequired = true;
      throw recoveryError;
    }

    if (wasBackendRunning) {
      try {
        startBackend();
        await waitForBackend({ timeoutMs: getBackendStartupTimeoutMs() });
      } catch (restartErr) {
        throw new Error(
          `切换 output 目录失败：${message}${rollbackMessage}；且旧后端恢复失败：${restartErr?.message || restartErr}`
        );
      }
    }

    throw err;
  }
}

async function applyPendingOutputDirOnStartup() {
  loadDesktopSettings();
  if (desktopSettings.pendingOutputDir === null) return;

  outputDirChangeInProgress = true;
  try {
    logMain(`[main] applying pending output dir: ${desktopSettings.pendingOutputDir || "(default)"}`);
    await applyOutputDirChange(desktopSettings.pendingOutputDir);
  } catch (err) {
    setOutputDirLastError(`待处理的 output 目录未能应用：${err?.message || err}`);
    logMain(`[main] failed to apply pending output dir: ${err?.message || err}`);
    if (err?.outputDirRecoveryRequired) throw err;
  } finally {
    outputDirChangeInProgress = false;
  }
}

async function refreshRendererCacheForPackagedUi() {
  if (!app.isPackaged) return;

  const nextBuildId = readPackagedUiBuildId();
  if (!nextBuildId) return;

  const prevBuildId = String(loadDesktopSettings()?.lastSeenUiBuildId || "").trim();
  if (prevBuildId === nextBuildId) return;

  try {
    const ses = session?.defaultSession;
    if (ses) {
      await ses.clearCache();
      try {
        await ses.clearStorageData({ storages: ["serviceworkers"] });
      } catch {}
    }
    logMain(`[main] cleared renderer cache for UI build change: ${prevBuildId || "(none)"} -> ${nextBuildId}`);
  } catch (err) {
    logMain(`[main] failed to clear renderer cache for UI build change: ${err?.message || err}`);
  }

  loadDesktopSettings();
  desktopSettings.lastSeenUiBuildId = nextBuildId;
  persistDesktopSettings();
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

function makeIdleOutputDirChangeProgressState() {
  return {
    active: false,
    stage: "idle",
    message: "",
    percent: 0,
    bytesTransferred: 0,
    bytesTotal: 0,
    itemsTransferred: 0,
    itemsTotal: 0,
    currentFile: "",
    error: "",
  };
}

function clampOutputDirProgressNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return n;
}

function normalizeOutputDirChangeProgressState(next = {}) {
  const active = next?.active !== false;
  const percent = Math.max(0, Math.min(100, Math.round(Number(next?.percent || 0))));
  return {
    active,
    stage: String(next?.stage || (active ? "running" : "idle")),
    message: String(next?.message || ""),
    percent,
    bytesTransferred: clampOutputDirProgressNumber(next?.bytesTransferred),
    bytesTotal: clampOutputDirProgressNumber(next?.bytesTotal),
    itemsTransferred: clampOutputDirProgressNumber(next?.itemsTransferred),
    itemsTotal: clampOutputDirProgressNumber(next?.itemsTotal),
    currentFile: String(next?.currentFile || ""),
    error: String(next?.error || ""),
  };
}

function getOutputDirChangeProgressState() {
  if (!outputDirChangeProgressState) {
    outputDirChangeProgressState = makeIdleOutputDirChangeProgressState();
  }
  return outputDirChangeProgressState;
}

function setOutputDirChangeProgressState(next = {}) {
  outputDirChangeProgressState = normalizeOutputDirChangeProgressState(next);
  sendToRenderer("app:outputDirChangeProgress", outputDirChangeProgressState);

  if (!outputDirChangeProgressState.active) {
    setWindowProgressBar(-1);
    return outputDirChangeProgressState;
  }

  const ratio =
    outputDirChangeProgressState.percent > 0
      ? Math.max(0.02, Math.min(1, outputDirChangeProgressState.percent / 100))
      : 2;
  setWindowProgressBar(ratio);
  return outputDirChangeProgressState;
}

function clearOutputDirChangeProgressState() {
  return setOutputDirChangeProgressState({ active: false });
}

function getOutputDirWorkerScriptPath() {
  return path.join(__dirname, "output-dir-worker.cjs");
}

function runOutputDirWorker(action, payload, onProgress) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(getOutputDirWorkerScriptPath(), {
      workerData: {
        action: String(action || "migrate"),
        payload,
      },
    });

    let settled = false;
    const finish = (err, result) => {
      if (settled) return;
      settled = true;
      if (err) reject(err);
      else resolve(result);
    };

    worker.on("message", (message) => {
      if (!message || typeof message !== "object") return;
      if (message.type === "progress") {
        if (typeof onProgress === "function") onProgress(message.progress || {});
        return;
      }
      if (message.type === "result") {
        finish(null, message.result);
        return;
      }
      if (message.type === "error") {
        const workerError = new Error(message.error?.message || "output 目录迁移失败");
        if (message.error?.code) workerError.code = String(message.error.code);
        if (message.error?.path) workerError.path = String(message.error.path);
        finish(workerError);
      }
    });

    worker.once("error", (err) => {
      finish(err);
    });

    worker.once("exit", (code) => {
      if (settled || code === 0) return;
      finish(new Error(`output 目录任务异常退出（code=${code}）`));
    });
  });
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
  if (process.platform === "darwin") {
    const packaged = path.join(process.resourcesPath, "icon.png");
    try {
      if (app.isPackaged && fs.existsSync(packaged)) return packaged;
    } catch {}

    const devMac = path.resolve(__dirname, "..", "src", "icon.png");
    try {
      if (fs.existsSync(devMac)) return devMac;
    } catch {}
  }

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
  if (!mainWindow || mainWindow.isDestroyed()) return false;
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
  return true;
}

function requestMainWindow(reason = "request") {
  if (showMainWindow()) return;

  const startup = initialStartupPromise || Promise.resolve();
  void startup
    .then(() => ensureMainWindowReady())
    .catch((err) => {
      const message = err?.message || String(err);
      logMain(`[main] failed to open window reason=${reason}: ${err?.stack || message}`);
      try {
        dialog.showErrorBox("WeChatDataAnalysis", `无法打开主窗口：${message}`);
      } catch {}
    });
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
    let trayIcon = iconPath;
    if (process.platform === "darwin") {
      trayIcon = nativeImage.createFromPath(iconPath).resize({ width: 18, height: 18 });
      trayIcon.setTemplateImage(true);
    }
    tray = new Tray(trayIcon);
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
          click: () => requestMainWindow("tray-menu"),
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
    tray.on("click", () => requestMainWindow("tray-click"));
    tray.on("double-click", () => requestMainWindow("tray-double-click"));
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
  const attachedAt = Date.now();
  let outputChunks = 0;
  try {
    stream = fs.createWriteStream(logPath, { flags: "a" });
    stream.on("error", (err) => {
      logMain(`[main] child stdio log error path=${logPath}: ${err?.message || err}`);
      stream = null;
    });
    stream.write(`[${nowIso()}] [main] backend stdio -> ${logPath} pid=${proc?.pid || "?"}\n`);
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

  if (proc.stdout)
    proc.stdout.on("data", (d) => {
      outputChunks += 1;
      write("[backend:stdout]", d);
    });
  if (proc.stderr)
    proc.stderr.on("data", (d) => {
      outputChunks += 1;
      write("[backend:stderr]", d);
    });
  proc.on("error", (err) => write("[backend:error]", err?.stack || String(err)));
  proc.on("close", (code, signal) => {
    write(
      "[backend:close]",
      `code=${code} signal=${signal} elapsedMs=${Date.now() - attachedAt} outputChunks=${outputChunks}`
    );
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
  const executableName = process.platform === "win32" ? "wechat-backend.exe" : "wechat-backend";
  return path.join(process.resourcesPath, "backend", executableName);
}

function getFfmpegPath() {
  if (app.isPackaged) {
    const executableName = process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg";
    return path.join(process.resourcesPath, "ffmpeg", executableName);
  }

  try {
    return String(require("ffmpeg-static") || "").trim();
  } catch {
    return "";
  }
}

function getPackagedWcdbDllPath() {
  if (process.platform === "darwin") {
    const arch = process.arch === "arm64" ? "arm64" : "x64";
    return path.join(process.resourcesPath, "backend", "native", "macos", arch, "libwcdb_api.dylib");
  }
  return path.join(process.resourcesPath, "backend", "native", "wcdb_api.dll");
}

function getDevWcdbDllPath() {
  if (process.platform === "darwin") {
    const arch = process.arch === "arm64" ? "arm64" : "x64";
    return path.join(repoRoot(), "src", "wechat_decrypt_tool", "native", "macos", arch, "libwcdb_api.dylib");
  }
  return path.join(repoRoot(), "src", "wechat_decrypt_tool", "native", "wcdb_api.dll");
}

function getWcdbDllPath() {
  return app.isPackaged ? getPackagedWcdbDllPath() : getDevWcdbDllPath();
}

function getWcdbDllDir() {
  return path.dirname(getWcdbDllPath());
}

function getWcdbSidecarScriptPath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "wcdb-sidecar.cjs")
    : path.join(__dirname, "wcdb-sidecar.cjs");
}

function getKoffiDir() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "app.asar.unpacked", "node_modules", "koffi")
    : path.join(repoRoot(), "desktop", "node_modules", "koffi");
}

function getWcdbSidecarStdioLogPath(dataDir) {
  return path.join(dataDir, "wcdb-sidecar-stdio.log");
}

function getWcdbSidecarPort() {
  if (parsePort(wcdbSidecarPort) != null) return wcdbSidecarPort;
  const envPort = parsePort(process.env.WECHAT_TOOL_WCDB_SIDECAR_PORT);
  wcdbSidecarPort = envPort ?? Math.min(65535, getBackendPort() + 101);
  return wcdbSidecarPort;
}

async function prepareWcdbSidecarPort() {
  if (parsePort(wcdbSidecarPort) != null) return wcdbSidecarPort;
  const envPort = parsePort(process.env.WECHAT_TOOL_WCDB_SIDECAR_PORT);
  if (envPort != null) {
    wcdbSidecarPort = envPort;
    return wcdbSidecarPort;
  }
  const preferred = Math.min(65535, getBackendPort() + 101);
  wcdbSidecarPort = await chooseAvailablePort(preferred, "127.0.0.1");
  if (wcdbSidecarPort == null) wcdbSidecarPort = preferred;
  return wcdbSidecarPort;
}

function getWcdbResourcePaths() {
  const out = [];
  const seen = new Set();

  const add = (value) => {
    const raw = String(value || "").trim();
    if (!raw) return;
    const resolved = path.resolve(raw);
    const key = resolved.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(resolved);
  };

  const dllDir = getWcdbDllDir();
  add(dllDir);
  add(path.dirname(dllDir));
  add(repoRoot());
  add(path.join(repoRoot(), "resources"));
  const dataDir = resolveDataDir();
  if (dataDir) {
    add(dataDir);
    add(path.join(dataDir, "resources"));
  }
  return out;
}

function ensureWcdbSidecarEnv(env) {
  if (!wcdbSidecarUrl || !wcdbSidecarToken) return env;
  env.WECHAT_TOOL_WCDB_SIDECAR_URL = wcdbSidecarUrl;
  env.WECHAT_TOOL_WCDB_SIDECAR_TOKEN = wcdbSidecarToken;
  return env;
}

function stopWcdbSidecarHealthMonitor() {
  wcdbSidecarHealthGeneration += 1;
  if (wcdbSidecarHealthTimer) clearInterval(wcdbSidecarHealthTimer);
  wcdbSidecarHealthTimer = null;
  wcdbSidecarHealthInFlight = false;
  wcdbSidecarHealthFailures = 0;
}

async function probeWcdbSidecarHealth(proc) {
  if (!proc || proc.exitCode != null || !wcdbSidecarUrl) return false;
  try {
    const response = await httpGet(`${wcdbSidecarUrl}/health`);
    return isWcdbSidecarHealthResponse(response);
  } catch {
    return false;
  }
}

function startWcdbSidecarHealthMonitor(proc) {
  stopWcdbSidecarHealthMonitor();
  if (!proc) return;

  const generation = wcdbSidecarHealthGeneration;
  const startedAt = Date.now();
  wcdbSidecarHealthTimer = setInterval(() => {
    if (generation !== wcdbSidecarHealthGeneration || wcdbSidecarHealthInFlight) return;
    if (wcdbSidecarProc !== proc || proc.exitCode != null) {
      stopWcdbSidecarHealthMonitor();
      return;
    }

    wcdbSidecarHealthInFlight = true;
    void probeWcdbSidecarHealth(proc)
      .then((healthy) => {
        if (generation !== wcdbSidecarHealthGeneration) return;
        if (
          outputDirChangeInProgress ||
          backendPortChangeInProgress ||
          accountDataChangeInProgress
        ) {
          wcdbSidecarHealthFailures = 0;
          return;
        }
        if (healthy) {
          wcdbSidecarHealthFailures = 0;
          return;
        }
        if (Date.now() - startedAt < 4_000) return;

        wcdbSidecarHealthFailures += 1;
        logMain(`[wcdb-sidecar] health probe failed count=${wcdbSidecarHealthFailures}`);
        // Most sidecar calls allow up to 30 seconds. Recycle only after that
        // request window has elapsed, so a slow valid query is not interrupted.
        if (wcdbSidecarHealthFailures < WCDB_SIDECAR_HEALTH_FAILURE_LIMIT) return;

        logMain("[wcdb-sidecar] unresponsive; terminating runtime for clean restart");
        stopWcdbSidecarHealthMonitor();
        try {
          proc.kill();
        } catch (err) {
          logMain(`[wcdb-sidecar] watchdog kill failed: ${err?.message || err}`);
        }
      })
      .finally(() => {
        if (generation === wcdbSidecarHealthGeneration) wcdbSidecarHealthInFlight = false;
      });
  }, 2_000);
  wcdbSidecarHealthTimer.unref?.();
}

function cancelWcdbRuntimeRestart() {
  if (!wcdbSidecarRestartTimer) return;
  clearTimeout(wcdbSidecarRestartTimer);
  wcdbSidecarRestartTimer = null;
}

async function waitForWcdbRuntimeRestartToSettle({ timeoutMs } = {}) {
  cancelWcdbRuntimeRestart();
  const effectiveTimeoutMs =
    Number.isFinite(timeoutMs) && timeoutMs > 0
      ? timeoutMs
      : getBackendStartupTimeoutMs() + 15_000;
  const startedAt = Date.now();
  while (
    wcdbSidecarRestartInProgress ||
    (!!wcdbSidecarProc && wcdbSidecarProc.exitCode == null && wcdbSidecarProc.killed)
  ) {
    if (Date.now() - startedAt > effectiveTimeoutMs) {
      throw new Error("WCDB 运行时仍在重启，暂时无法安全执行后端维护");
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

function scheduleWcdbRuntimeRestart(code, signal) {
  if (
    isQuitting ||
    outputDirChangeInProgress ||
    backendPortChangeInProgress ||
    accountDataChangeInProgress ||
    !backendProc ||
    wcdbSidecarRestartTimer ||
    wcdbSidecarRestartInProgress
  )
    return;

  const now = Date.now();
  wcdbSidecarRestartHistory = wcdbSidecarRestartHistory.filter((timestamp) => now - timestamp < 60_000);
  if (wcdbSidecarRestartHistory.length >= 3) {
    logMain("[wcdb-sidecar] restart suppressed after 3 failures in 60s");
    return;
  }
  wcdbSidecarRestartHistory.push(now);
  const delayMs = Math.min(4_000, 500 * 2 ** (wcdbSidecarRestartHistory.length - 1));
  logMain(`[wcdb-sidecar] scheduling runtime restart in ${delayMs}ms code=${code} signal=${signal}`);

  wcdbSidecarRestartTimer = setTimeout(() => {
    wcdbSidecarRestartTimer = null;
    if (
      isQuitting ||
      outputDirChangeInProgress ||
      backendPortChangeInProgress ||
      accountDataChangeInProgress ||
      !backendProc ||
      wcdbSidecarRestartInProgress
    )
      return;
    wcdbSidecarRestartInProgress = true;

    void (async () => {
      try {
        // A restarted sidecar has no knowledge of the backend's cached native handles.
        // Restart both processes so the next request opens a fresh WCDB account.
        const stopped = await stopBackendAndWait({ timeoutMs: 10_000 });
        if (!stopped) {
          throw new Error("后端进程未能停止，无法安全恢复 WCDB 运行时");
        }
        if (isQuitting) return;
        startBackend();
        await waitForBackend({ timeoutMs: getBackendStartupTimeoutMs() });
        logMain("[wcdb-sidecar] runtime restart completed");
      } catch (err) {
        logMain(`[wcdb-sidecar] runtime restart failed: ${err?.stack || String(err)}`);
      } finally {
        wcdbSidecarRestartInProgress = false;
      }
    })();
  }, delayMs);
}

function startWcdbSidecar() {
  if (process.env.WECHAT_TOOL_WCDB_SIDECAR === "0") return null;
  if (wcdbSidecarProc && wcdbSidecarProc.exitCode == null) return wcdbSidecarProc;
  if (!["win32", "darwin"].includes(process.platform)) return null;

  const dllPath = getWcdbDllPath();
  const sidecarScript = getWcdbSidecarScriptPath();
  const koffiDir = getKoffiDir();
  if (!fs.existsSync(dllPath)) {
    logMain(`[wcdb-sidecar] skip: missing native library ${dllPath}`);
    return null;
  }
  if (!fs.existsSync(sidecarScript)) {
    logMain(`[wcdb-sidecar] skip: missing sidecar script ${sidecarScript}`);
    return null;
  }
  if (!fs.existsSync(koffiDir)) {
    logMain(`[wcdb-sidecar] skip: missing koffi runtime ${koffiDir}`);
    return null;
  }

  const port = getWcdbSidecarPort();
  const host = "127.0.0.1";
  wcdbSidecarUrl = `http://${host}:${port}`;
  wcdbSidecarToken = wcdbSidecarToken || crypto.randomBytes(24).toString("hex");

  const env = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: "1",
    WECHAT_TOOL_WCDB_SIDECAR_HOST: host,
    WECHAT_TOOL_WCDB_SIDECAR_PORT: String(port),
    WECHAT_TOOL_WCDB_SIDECAR_TOKEN: wcdbSidecarToken,
    WECHAT_TOOL_WCDB_API_DLL_PATH: dllPath,
    WECHAT_TOOL_WCDB_DLL_DIR: getWcdbDllDir(),
    WECHAT_TOOL_WCDB_RESOURCE_PATHS: JSON.stringify(getWcdbResourcePaths()),
    WECHAT_TOOL_KOFFI_DIR: koffiDir,
  };

  logMain(`[wcdb-sidecar] starting url=${wcdbSidecarUrl} dll=${dllPath}`);
  wcdbSidecarProc = spawn(process.execPath, [sidecarScript], {
    cwd: path.dirname(sidecarScript),
    env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  const dataDir = resolveDataDir() || getUserDataDir() || repoRoot();
  attachBackendStdio(wcdbSidecarProc, getWcdbSidecarStdioLogPath(dataDir));

  const proc = wcdbSidecarProc;
  proc.on("exit", (code, signal) => {
    const unexpected = wcdbSidecarProc === proc;
    if (unexpected) {
      wcdbSidecarProc = null;
      stopWcdbSidecarHealthMonitor();
    }
    logMain(`[wcdb-sidecar] exited code=${code} signal=${signal}`);
    if (unexpected) scheduleWcdbRuntimeRestart(code, signal);
  });
  startWcdbSidecarHealthMonitor(proc);

  process.env.WECHAT_TOOL_WCDB_SIDECAR_URL = wcdbSidecarUrl;
  process.env.WECHAT_TOOL_WCDB_SIDECAR_TOKEN = wcdbSidecarToken;
  return wcdbSidecarProc;
}

function stopWcdbSidecar() {
  cancelWcdbRuntimeRestart();
  stopWcdbSidecarHealthMonitor();
  if (!wcdbSidecarProc) return;
  const pid = wcdbSidecarProc.pid;
  logMain(`[wcdb-sidecar] stop pid=${pid || "?"}`);
  try {
    wcdbSidecarProc.kill();
  } catch {}
  wcdbSidecarProc = null;
}

function startBackend() {
  if (backendProc && backendProc.exitCode == null) return backendProc;
  backendProc = null;
  startWcdbSidecar();

  const resolvedDataPath = resolveDataDir() || getUserDataDir() || repoRoot();
  const resolvedOutputPath = resolveOutputDir() || getDefaultOutputDir() || path.join(resolvedDataPath, "output");
  const env = {
    ...process.env,
    WECHAT_TOOL_HOST: getBackendBindHost(),
    WECHAT_TOOL_PORT: String(getBackendPort()),
    WECHAT_TOOL_DATA_DIR: resolvedDataPath,
    WECHAT_TOOL_OUTPUT_DIR: resolvedOutputPath,
    // Make sure Python prints UTF-8 to stdout/stderr.
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
  };
  ensureWcdbSidecarEnv(env);
  logMain(
    `[main] startBackend packaged=${app.isPackaged} port=${env.WECHAT_TOOL_PORT} dataDir=${env.WECHAT_TOOL_DATA_DIR} outputDir=${env.WECHAT_TOOL_OUTPUT_DIR}`
  );

  // In packaged mode we expect to provide the generated Nuxt output dir via env.
  if (app.isPackaged && !env.WECHAT_TOOL_UI_DIR) {
    env.WECHAT_TOOL_UI_DIR = path.join(process.resourcesPath, "ui");
  }

  const ffmpegPath = getFfmpegPath();
  if (ffmpegPath && fs.existsSync(ffmpegPath)) {
    env.WECHAT_TOOL_FFMPEG = ffmpegPath;
    logMain(`[main] using bundled ffmpeg: ${ffmpegPath}`);
  }

  if (app.isPackaged) {
    try {
      fs.mkdirSync(env.WECHAT_TOOL_DATA_DIR, { recursive: true });
      fs.mkdirSync(env.WECHAT_TOOL_OUTPUT_DIR, { recursive: true });
    } catch {}

    const backendExe = getPackagedBackendPath();
    if (!fs.existsSync(backendExe)) {
      throw new Error(`Packaged backend not found: ${backendExe}. Run the platform backend build before packaging.`);
    }
    const packagedWcdbDll = getPackagedWcdbDllPath();
    if (fs.existsSync(packagedWcdbDll)) {
      env.WECHAT_TOOL_WCDB_API_DLL_PATH = packagedWcdbDll;
      logMain(`[main] using packaged WCDB native library: ${packagedWcdbDll}`);
    } else {
      logMain(`[main] packaged WCDB native library not found: ${packagedWcdbDll}`);
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
  let backendSpawnSucceeded = false;
  logMain(
    `[main] backend spawned pid=${proc?.pid || "?"} port=${env.WECHAT_TOOL_PORT} startupTimeoutMs=${getBackendStartupTimeoutMs()}`
  );
  proc.once("spawn", () => {
    backendSpawnSucceeded = true;
  });
  proc.on("error", (err) => {
    logMain(`[backend] process error: ${err?.stack || String(err)}`);
    if (!backendSpawnSucceeded && backendProc === proc) backendProc = null;
  });
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
  if (!backendProc) return true;
  const proc = backendProc;

  await new Promise((resolve) => {
    let done = false;
    let timer = null;
    const onExit = () => finish();
    const finish = () => {
      if (done) return;
      done = true;
      if (timer) clearTimeout(timer);
      try {
        proc.removeListener("exit", onExit);
      } catch {}
      resolve();
    };

    timer = setTimeout(finish, timeoutMs);

    try {
      proc.once("exit", onExit);
    } catch {}

    try {
      stopBackend();
    } catch {
      finish();
    }
  });
  return backendProc !== proc || proc.exitCode != null;
}

async function restartBackend({ timeoutMs = getBackendStartupTimeoutMs() } = {}) {
  const stopped = await stopBackendAndWait({ timeoutMs: 10_000 });
  if (!stopped) {
    throw new Error("后端进程未能在 10 秒内停止，已取消重启");
  }
  startBackend();
  await waitForBackend({ timeoutMs });
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      const chunks = [];
      let totalBytes = 0;
      let tooLarge = false;
      res.on("data", (chunk) => {
        const data = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        totalBytes += data.length;
        if (totalBytes <= 64 * 1024) chunks.push(data);
        else tooLarge = true;
      });
      res.on("error", reject);
      res.on("end", () => {
        if (tooLarge) {
          reject(new Error("health response too large"));
          return;
        }
        resolve({
          statusCode: res.statusCode || 0,
          body: Buffer.concat(chunks).toString("utf8"),
        });
      });
    });
    req.on("error", reject);
    req.setTimeout(1000, () => {
      req.destroy(new Error("timeout"));
    });
  });
}

async function waitForBackend({ timeoutMs, healthUrl, allowBackendReplacement = false } = {}) {
  const url = String(healthUrl || getBackendHealthUrl()).trim();
  const effectiveTimeoutMs =
    Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : getBackendStartupTimeoutMs();
  const startedAt = Date.now();
  let lastProgressLogAt = startedAt;
  logMain(
    `[main] waiting for backend pid=${backendProc?.pid || "?"} timeoutMs=${effectiveTimeoutMs} url=${url}`
  );
  // eslint-disable-next-line no-constant-condition
  while (true) {
    // If the backend process died, fail fast (otherwise we'd wait for the full timeout).
    if (!backendProc) {
      // A WCDB sidecar crash intentionally replaces the backend. Do not let the
      // short hand-off window abort another startup waiter in the main flow.
      if (
        shouldWaitForBackendReplacement({
          allowBackendReplacement,
          sidecarRestartInProgress: wcdbSidecarRestartInProgress,
        })
      ) {
        if (Date.now() - startedAt > effectiveTimeoutMs) {
          throw new Error(
            `Backend replacement did not start in ${effectiveTimeoutMs}ms: ${url}`
          );
        }
        await new Promise((r) => setTimeout(r, 300));
        continue;
      }
      throw new Error(`Backend process exited before becoming ready: ${url}`);
    }
    if (backendProc.exitCode != null) {
      throw new Error(
        `Backend process exited (code=${backendProc.exitCode} signal=${backendProc.signalCode || "null"}): ${url}`
      );
    }

    try {
      const procDuringRequest = backendProc;
      const response = await httpGet(url);
      if (
        isBackendHealthResponse(response) &&
        procDuringRequest &&
        backendProc === procDuringRequest &&
        procDuringRequest.exitCode == null
      ) {
        logMain(
          `[main] backend ready pid=${backendProc?.pid || "?"} elapsedMs=${Date.now() - startedAt} url=${url}`
        );
        return;
      }
    } catch {}

    const now = Date.now();
    const elapsedMs = now - startedAt;
    if (now - lastProgressLogAt >= 15_000) {
      lastProgressLogAt = now;
      logMain(
        `[main] backend still starting pid=${backendProc?.pid || "?"} elapsedMs=${elapsedMs} timeoutMs=${effectiveTimeoutMs} url=${url}`
      );
    }

    if (elapsedMs > effectiveTimeoutMs) {
      throw new Error(
        `Backend did not become ready in ${effectiveTimeoutMs}ms (pid=${backendProc?.pid || "?"}, process was still running at timeout): ${url}`
      );
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
  const devToolsShortcutOk = globalShortcut.register("CommandOrControl+Shift+I", toggleDevTools);
  const f12ShortcutOk = globalShortcut.register("F12", toggleDevTools);
  logMain(`[main] shortcut registration devTools=${devToolsShortcutOk} f12=${f12ShortcutOk}`);
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

function getRendererDebugLogPath() {
  try {
    const dir = app.getPath("userData");
    fs.mkdirSync(dir, { recursive: true });
    return path.join(dir, "renderer-debug.log");
  } catch {
    return null;
  }
}

function appendRendererDebugLog(line) {
  const logPath = getRendererDebugLogPath();
  if (!logPath) return;
  try {
    fs.appendFileSync(logPath, line, { encoding: "utf8" });
  } catch {}
}

function stringifyDebugDetails(details) {
  if (details == null) return "";
  if (typeof details === "string") return details;
  try {
    return JSON.stringify(details);
  } catch (err) {
    return `[unserializable:${err?.message || err}]`;
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

function setupRendererLifecycleLogging(win) {
  if (!debugEnabled()) return;

  const logRendererLifecycle = (message) => {
    logMain(`[renderer] ${message}`);
  };

  logRendererLifecycle(`window-created id=${win.id}`);

  win.webContents.on("did-start-loading", () => {
    logRendererLifecycle("did-start-loading");
  });

  win.webContents.on("dom-ready", () => {
    logRendererLifecycle(`dom-ready url=${win.webContents.getURL()}`);
  });

  win.webContents.on("did-stop-loading", () => {
    logRendererLifecycle("did-stop-loading");
  });

  win.webContents.on("did-finish-load", () => {
    logRendererLifecycle(`did-finish-load url=${win.webContents.getURL()}`);
  });

  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    logRendererLifecycle(
      `did-fail-load code=${errorCode} mainFrame=${!!isMainFrame} url=${validatedURL} error=${errorDescription}`
    );
  });

  win.webContents.on("did-navigate", (_event, url, httpResponseCode, httpStatusText) => {
    logRendererLifecycle(
      `did-navigate url=${url} code=${httpResponseCode || 0} status=${httpStatusText || ""}`
    );
  });

  win.webContents.on("did-navigate-in-page", (_event, url, isMainFrame) => {
    logRendererLifecycle(`did-navigate-in-page mainFrame=${!!isMainFrame} url=${url}`);
  });

  win.webContents.on("render-process-gone", (_event, details) => {
    logRendererLifecycle(
      `render-process-gone reason=${details?.reason || ""} exitCode=${details?.exitCode ?? ""}`
    );
  });

  win.on("unresponsive", () => {
    logRendererLifecycle("window-unresponsive");
  });

  win.on("responsive", () => {
    logRendererLifecycle("window-responsive");
  });
}

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 980,
    minHeight: 700,
    ...(process.platform === "darwin"
      ? { titleBarStyle: "hiddenInset", trafficLightPosition: { x: 12, y: 9 } }
      : { titleBarStyle: "hidden", titleBarOverlay: getTitleBarOverlayOptions("light") }),
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
    if (mainWindow === win) mainWindow = null;
  });

  setupRendererConsoleLogging(win);
  setupRendererLifecycleLogging(win);

  return win;
}

async function loadWithRetry(win, url) {
  const startedAt = Date.now();
  let attempt = 0;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    attempt += 1;
    logMain(`[main] loadWithRetry attempt=${attempt} url=${url}`);
    try {
      await win.loadURL(url);
      logMain(`[main] loadWithRetry success attempt=${attempt} elapsedMs=${Date.now() - startedAt} url=${url}`);
      return;
    } catch (err) {
      logMain(
        `[main] loadWithRetry failure attempt=${attempt} elapsedMs=${Date.now() - startedAt} url=${url} error=${err?.message || err}`
      );
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

  ipcMain.handle("window:setTitleBarTheme", (event, theme) => {
    const win = getWin(event);
    return setWindowTitleBarTheme(win, theme);
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

  ipcMain.handle("app:isDebugEnabled", () => {
    try {
      return debugEnabled();
    } catch (err) {
      logMain(`[main] app:isDebugEnabled failed: ${err?.message || err}`);
      return false;
    }
  });

  ipcMain.on("debug:log", (event, payload) => {
    const scope = String(payload?.scope || "renderer").trim() || "renderer";
    const message = String(payload?.message || "").trim() || "(empty)";
    const url = String(payload?.url || event?.sender?.getURL?.() || "").trim();
    const details = stringifyDebugDetails(payload?.details);
    const suffix = details ? ` details=${details}` : "";
    appendRendererDebugLog(`[${nowIso()}] [${scope}] ${message} url=${url}${suffix}\n`);
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
    if (outputDirChangeInProgress || accountDataChangeInProgress) {
      throw new Error("后端维护中，请稍后重试");
    }
    if (!app.isPackaged) {
      throw new Error("开发模式不支持界面修改端口；请设置 WECHAT_TOOL_PORT 环境变量后重启");
    }

    const nextPort = parsePort(port);
    if (nextPort == null) throw new Error("端口无效，请输入 1-65535 的整数");

    const prevPort = getBackendPort();
    if (nextPort === prevPort) {
      return { success: true, changed: false, port: prevPort, uiUrl: getDesktopUiUrl() };
    }

    backendPortChangeInProgress = true;
    try {
      await waitForWcdbRuntimeRestartToSettle();
      const bindHost = getBackendBindHost();
      const ok = await isPortAvailable(nextPort, bindHost);
      if (!ok) throw new Error(`端口 ${nextPort} 已被占用，请换一个端口`);

      setBackendPortSetting(nextPort);
      try {
        await restartBackend();
      } catch (err) {
        // Roll back to the previous port so the UI can keep working.
        setBackendPortSetting(prevPort);
        try {
          await restartBackend();
        } catch {}
        throw err;
      }

      const uiUrl = getDesktopUiUrl();
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

  ipcMain.handle("backend:getMcpLanAccess", () => {
    try {
      const host = getBackendBindHost();
      const port = getBackendPort();
      return {
        enabled: getMcpLanAccessEnabled(),
        host,
        port,
        uiUrl: getDesktopUiUrl(),
        ...getMcpAccessInfo(host, port),
      };
    } catch (err) {
      logMain(`[main] backend:getMcpLanAccess failed: ${err?.message || err}`);
      const port = DEFAULT_BACKEND_PORT;
      return {
        enabled: false,
        host: DEFAULT_BACKEND_HOST,
        port,
        uiUrl: getDesktopUiUrl(),
        ...getMcpAccessInfo(DEFAULT_BACKEND_HOST, port),
      };
    }
  });

  ipcMain.handle("backend:setMcpLanAccess", async (_event, enabled) => {
    if (backendPortChangeInProgress) throw new Error("后端切换中，请稍后重试");
    if (outputDirChangeInProgress || accountDataChangeInProgress) {
      throw new Error("后端维护中，请稍后重试");
    }

    const nextEnabled = !!enabled;
    const prevEnabled = getMcpLanAccessEnabled();
    if (nextEnabled === prevEnabled) {
      const host = getBackendBindHost();
      const port = getBackendPort();
      return {
        success: true,
        changed: false,
        enabled: prevEnabled,
        host,
        port,
        uiUrl: getDesktopUiUrl(),
        ...getMcpAccessInfo(host, port),
      };
    }

    backendPortChangeInProgress = true;
    try {
      await waitForWcdbRuntimeRestartToSettle();
      setMcpLanAccessSetting(nextEnabled);
      try {
        await restartBackend();
      } catch (err) {
        setMcpLanAccessSetting(prevEnabled);
        try {
          await restartBackend();
        } catch {}
        throw err;
      }

      const uiUrl = getDesktopUiUrl();
      logMain(`[main] MCP access changed enabled=${nextEnabled}; backend restarted without UI reload`);

      return {
        success: true,
        changed: true,
        enabled: nextEnabled,
        host: getBackendBindHost(),
        port: getBackendPort(),
        uiUrl,
        ...getMcpAccessInfo(),
      };
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

  ipcMain.handle("app:getOutputDirInfo", () => {
    try {
      return getOutputDirInfo();
    } catch (err) {
      logMain(`[main] app:getOutputDirInfo failed: ${err?.message || err}`);
      return {
        path: "",
        defaultPath: "",
        isDefault: true,
        pendingPath: "",
        hasPending: false,
        lastError: err?.message || String(err),
        canChange: false,
        changeUnavailableReason: "无法读取 output 目录信息",
      };
    }
  });

  ipcMain.handle("app:getOutputDir", () => {
    return resolveOutputDir() || "";
  });

  ipcMain.handle("app:getOutputDirChangeProgress", () => {
    return getOutputDirChangeProgressState();
  });

  ipcMain.handle("app:openOutputDir", async () => {
    const outputTransactionPending =
      outputDirChangeInProgress || loadDesktopSettings()?.pendingOutputDir !== null;
    const outDir = resolveOutputDir({ ensureExists: !outputTransactionPending });
    if (!outDir) throw new Error("无法定位 output 目录");
    if (outputTransactionPending && !fs.existsSync(outDir)) {
      throw new Error("output 目录迁移待恢复，暂时无法打开目录");
    }
    if (!outputTransactionPending) {
      try {
        fs.mkdirSync(outDir, { recursive: true });
      } catch {}
    }
    try {
      const err = await shell.openPath(outDir);
      if (err) throw new Error(err);
      return { success: true, path: outDir };
    } catch (e) {
      const message = e?.message || String(e);
      logMain(`[main] openOutputDir failed: ${message}`);
      throw new Error(message);
    }
  });

  ipcMain.handle("app:openExternalUrl", async (_event, rawUrl) => {
    const url = String(rawUrl || "").trim();
    if (!url) throw new Error("外部链接为空");
    let protocol = "";
    try {
      protocol = new URL(url).protocol.toLowerCase();
    } catch {
      throw new Error("外部链接格式无效");
    }
    if (!["http:", "https:", "weixin:"].includes(protocol)) {
      throw new Error(`不支持的外部链接协议：${protocol || "unknown"}`);
    }
    try {
      await shell.openExternal(url);
      return { success: true };
    } catch (e) {
      const message = e?.message || String(e);
      logMain(`[main] openExternalUrl failed: ${message}`);
      throw new Error(message);
    }
  });

  ipcMain.handle("app:setOutputDir", async (_event, nextDir) => {
    if (outputDirChangeInProgress || backendPortChangeInProgress || accountDataChangeInProgress) {
      return {
        success: false,
        error: "后端或 output 目录维护中，请稍后重试",
      };
    }
    outputDirChangeInProgress = true;
    try {
      return await applyOutputDirChange(nextDir);
    } catch (err) {
      const message = err?.message || String(err);
      logMain(`[main] app:setOutputDir failed: ${message}`);
      return {
        success: false,
        error: message,
      };
    } finally {
      outputDirChangeInProgress = false;
      clearOutputDirChangeProgressState();
    }
  });

  ipcMain.handle("app:getAccountInfo", async (_event, account) => {
    try {
      return getAccountInfoFromDisk(account);
    } catch (e) {
      throw new Error(e?.message || String(e));
    }
  });

  ipcMain.handle("app:deleteAccountData", async (_event, account) => {
    if (outputDirChangeInProgress || backendPortChangeInProgress || accountDataChangeInProgress) {
      throw new Error("后端或 output 目录维护中，请稍后重试");
    }
    accountDataChangeInProgress = true;
    try {
      await waitForWcdbRuntimeRestartToSettle();
      return await deleteAccountDataFromDisk(account);
    } catch (e) {
      throw new Error(e?.message || String(e));
    } finally {
      accountDataChangeInProgress = false;
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
      // Safety: remove legacy `output` junctions in the install dir before triggering the NSIS update/uninstall.
      // Some uninstall flows may traverse reparse points and delete the real per-user output directory.
      try {
        ensureOutputLink();
      } catch {}
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

  ipcMain.handle("dialog:chooseArchive", async (_event, options) => {
    try {
      return await dialog.showOpenDialog({
        title: String(options?.title || "请选择账号归档 ZIP"),
        defaultPath: String(options?.defaultPath || "") || undefined,
        properties: ["openFile"],
        filters: [
          { name: "微信账号归档", extensions: ["zip"] },
          { name: "所有文件", extensions: ["*"] },
        ],
      });
    } catch (err) {
      logMain(`[main] dialog:chooseArchive failed: ${err?.message || err}`);
      throw err;
    }
  });
}

async function ensureBackendReadyWithFallback() {
  startBackend();
  const startupTimeoutMs = getBackendStartupTimeoutMs();
  try {
    await waitForBackend({ timeoutMs: startupTimeoutMs, allowBackendReplacement: true });
  } catch (err) {
    // In some environments a specific port may be blocked/reserved (WSAEACCES) or taken.
    // Only change ports when the failed port cannot be bound. A PyInstaller onefile
    // cold start leaves it available while extracting and must be given more time,
    // not mistaken for a port conflict.
    if (app.isPackaged) {
      const prevPort = getBackendPort();
      const bindHost = getBackendBindHost();
      const portAvailableAfterFailure = await isPortAvailable(prevPort, bindHost);
      const backendProcessStillRunning = !!backendProc && backendProc.exitCode == null;
      const shouldRetryPort = shouldRetryBackendOnDifferentPort({
        isPackaged: app.isPackaged,
        portAvailableAfterFailure,
        backendProcessStillRunning,
      });
      if (!shouldRetryPort) {
        logMain(
          `[main] backend startup failed while port ${prevPort} remains available; not changing persisted port: ${err?.message || err}`
        );
        throw err;
      }

      const nextPort = await chooseAvailablePort(prevPort + 1, bindHost);
      if (nextPort != null && nextPort !== prevPort) {
        logMain(`[main] backend not ready on port ${prevPort}; retrying on ${nextPort}`);
        try {
          setBackendPortSetting(nextPort);
          await restartBackend({ timeoutMs: startupTimeoutMs });
          logMain(`[main] backend retry succeeded on port ${nextPort}`);
        } catch (retryErr) {
          logMain(`[main] backend retry failed: ${retryErr?.stack || String(retryErr)}`);
          try {
            setBackendPortSetting(prevPort);
            logMain(`[main] restored backend port setting to ${prevPort} after failed retry`);
          } catch (restoreErr) {
            logMain(
              `[main] failed to restore backend port ${prevPort}: ${restoreErr?.message || restoreErr}`
            );
          }
          throw retryErr;
        }
      } else {
        throw err;
      }
    } else {
      throw err;
    }
  }
}

async function ensureMainWindowReady() {
  if (showMainWindow()) return mainWindow;
  if (mainWindowLaunchPromise) return mainWindowLaunchPromise;

  mainWindowLaunchPromise = (async () => {
    await ensureBackendReadyWithFallback();

    if (showMainWindow()) return mainWindow;

    const win = createMainWindow();
    mainWindow = win;
    ensureTrayForCloseBehavior();

    const startUrl = getDesktopUiUrl();
    logMain(`[main] debugEnabled=${debugEnabled()} startUrl=${startUrl}`);
    await loadWithRetry(win, startUrl);

    if (debugEnabled()) {
      try {
        win.webContents.openDevTools({ mode: "detach" });
      } catch {}
    }

    return win;
  })();

  try {
    return await mainWindowLaunchPromise;
  } finally {
    mainWindowLaunchPromise = null;
  }
}

async function main() {
  await app.whenReady();
  await refreshRendererCacheForPackagedUi();
  Menu.setApplicationMenu(null);
  registerWindowIpc();
  registerDebugShortcuts();

  // Resolve/create the data dir early so we can log reliably and place helper files
  // next to the installed exe for easier access.
  resolveDataDir();
  loadDesktopSettings();
  await applyPendingOutputDirOnStartup();
  ensureOutputLink();
  await ensureBackendPortAvailableOnStartup();
  await prepareWcdbSidecarPort();

  logMain(`[main] app.isPackaged=${app.isPackaged} argv=${JSON.stringify(process.argv)}`);

  await ensureMainWindowReady();

  // Auto-check updates once after the first UI load (packaged builds only).
  checkForUpdatesOnStartup();
}

app.on("window-all-closed", () => {
  // Standard macOS lifecycle: keep the app runtime alive so clicking the Dock
  // icon can recreate a window. All child processes are stopped in before-quit.
  if (process.platform === "darwin" && getCloseBehavior() !== "exit") return;
  app.quit();
});

app.on("activate", () => {
  requestMainWindow("activate");
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
  stopWcdbSidecar();
});

if (gotSingleInstanceLock) {
  initialStartupPromise = main();
  initialStartupPromise.catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    logMain(`[main] fatal: ${err?.stack || String(err)}`);
    stopBackend();
    stopWcdbSidecar();
    try {
      const dir = getUserDataDir();
      const outputDir = resolveOutputDir({ ensureExists: false });
      if (dir) {
        const detailLines = [
          `启动失败：${err?.message || err}`,
          "",
          `桌面日志目录：${dir}`,
          "文件：desktop-main.log / backend-stdio.log",
        ];
        if (outputDir) {
          detailLines.push("", `当前 output 目录：${outputDir}`, `其中 output${path.sep}logs${path.sep}... 也在这里`);
        }
        dialog.showErrorBox(
          "WeChatDataAnalysis 启动失败",
          detailLines.join("\n")
        );
        shell.openPath(dir);
      }
    } catch {}
    app.quit();
  });
}
