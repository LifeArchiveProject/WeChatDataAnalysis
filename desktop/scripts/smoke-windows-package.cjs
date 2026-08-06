"use strict";

const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { UUID } = require("builder-util-runtime");

const { isBackendHealthResponse } = require("../src/backend-startup.cjs");
const {
  ensurePrivatePkiIssuerCached,
} = require("../src/windows-private-pki-runtime.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const defaultPackageRoot = path.join(desktopRoot, "dist", "win-unpacked");
const defaultDistRoot = path.join(desktopRoot, "dist");
const packageConfig = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const electronBuilderNamespace = UUID.parse("50e065bc-3134-11e6-9bab-38c9862bdaf3");

function resolveUnpackedRoot({
  env = process.env,
  argv = process.argv.slice(2),
} = {}) {
  const explicitArgument = String(argv[0] || "").trim();
  const explicitEnvironment = String(env.WCE_WINDOWS_UNPACKED_ROOT || "").trim();
  return path.resolve(explicitArgument || explicitEnvironment || defaultPackageRoot);
}

function resolvePackagedRuntime(packageRoot = defaultPackageRoot) {
  const root = path.resolve(packageRoot);
  const backendRoot = path.join(root, "resources", "backend");
  const nativeRoot = path.join(backendRoot, "native");
  const paths = {
    root,
    application: path.join(root, "WeChatDataAnalysis.exe"),
    backend: path.join(backendRoot, "wechat-backend.exe"),
    client: path.join(nativeRoot, "wechatdb_client.dll"),
    broker: path.join(nativeRoot, "wechatdb_broker.exe"),
    manifest: path.join(nativeRoot, "wechatdb_native_build.json"),
  };
  for (const [name, filePath] of Object.entries(paths)) {
    if (name === "root") continue;
    assert.ok(fs.statSync(filePath).isFile(), `Missing packaged ${name}: ${filePath}`);
  }
  return paths;
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address && typeof address === "object" ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function requestHealth(port) {
  return new Promise((resolve, reject) => {
    const request = http.get(
      { host: "127.0.0.1", port, path: "/api/health", timeout: 2_000 },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          resolve({
            statusCode: response.statusCode || 0,
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
      }
    );
    request.once("error", reject);
    request.once("timeout", () => request.destroy(new Error("Health request timed out.")));
  });
}

async function waitForBackend(processHandle, port, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    if (processHandle.exitCode !== null) {
      throw new Error(`Packaged backend exited before health check (code=${processHandle.exitCode}).`);
    }
    try {
      const response = await requestHealth(port);
      if (isBackendHealthResponse(response)) return;
      lastError = new Error(`Unexpected health response: HTTP ${response.statusCode}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw lastError || new Error("Timed out waiting for packaged backend health.");
}

function stopProcessTree(processHandle) {
  if (!processHandle || processHandle.exitCode !== null) return;
  const result = spawnSync("taskkill.exe", ["/pid", String(processHandle.pid), "/t", "/f"], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error && result.error.code !== "ENOENT") throw result.error;
}

async function smokeRuntime(packageRoot, tempRoot) {
  fs.mkdirSync(tempRoot, { recursive: true });
  const runtime = resolvePackagedRuntime(packageRoot);
  ensurePrivatePkiIssuerCached({
    resourcesPath: path.join(runtime.root, "resources"),
  });
  const manifest = JSON.parse(fs.readFileSync(runtime.manifest, "utf8"));
  assert.equal(manifest.developmentBuild, false);
  assert.equal(manifest.codeSignatureEnforced, true);
  assert.equal(manifest.stagingPinnedSignerTrust, false);
  assert.equal(manifest.windowsSignerTrustMode, "private-pki");

  const stdoutPath = path.join(tempRoot, "backend.out.log");
  const stderrPath = path.join(tempRoot, "backend.err.log");
  const stdout = fs.openSync(stdoutPath, "w");
  const stderr = fs.openSync(stderrPath, "w");
  const port = await getFreePort();
  let backend = null;
  try {
    backend = spawn(runtime.backend, [], {
      cwd: path.dirname(runtime.backend),
      windowsHide: true,
      stdio: ["ignore", stdout, stderr],
      env: {
        ...process.env,
        WECHAT_TOOL_DATA_DIR: path.join(tempRoot, "data"),
        WECHAT_TOOL_OUTPUT_DIR: path.join(tempRoot, "output"),
        WECHAT_TOOL_HOST: "127.0.0.1",
        WECHAT_TOOL_PORT: String(port),
        WECHAT_TOOL_NATIVE_CORE_MODE: "required",
      },
    });
    await waitForBackend(backend, port);
    return manifest;
  } catch (error) {
    const stderrText = fs.existsSync(stderrPath) ? fs.readFileSync(stderrPath, "utf8").slice(-8_000) : "";
    throw new Error(`${error.message}${stderrText ? `\nBackend stderr:\n${stderrText}` : ""}`);
  } finally {
    stopProcessTree(backend);
    fs.closeSync(stdout);
    fs.closeSync(stderr);
  }
}

async function waitForLogText(logPath, pattern, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let text = "";
  while (Date.now() < deadline) {
    try {
      text = fs.readFileSync(logPath, "utf8");
      if (pattern.test(text)) return text;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for packaged Electron log ${pattern}: ${logPath}\n${text.slice(-8_000)}`);
}

async function waitForProcessesUnderRootRemoval(root, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let processPaths = [];
  while (Date.now() < deadline) {
    processPaths = processesUnderRoot(root);
    if (processPaths.length === 0) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Packaged process tree remained active:\n${processPaths.join("\n")}`);
}

async function smokeElectronApp(packageRoot, tempRoot) {
  const runtime = resolvePackagedRuntime(packageRoot);
  const profileRoot = path.join(tempRoot, "profile");
  const dataRoot = path.join(tempRoot, "data");
  const outputRoot = path.join(tempRoot, "output");
  fs.mkdirSync(profileRoot, { recursive: true });
  fs.mkdirSync(dataRoot, { recursive: true });
  fs.mkdirSync(outputRoot, { recursive: true });
  const stdoutPath = path.join(tempRoot, "electron.out.log");
  const stderrPath = path.join(tempRoot, "electron.err.log");
  const stdout = fs.openSync(stdoutPath, "w");
  const stderr = fs.openSync(stderrPath, "w");
  const port = await getFreePort();
  let electron = null;
  try {
    electron = spawn(
      runtime.application,
      [`--user-data-dir=${profileRoot}`, "--disable-gpu"],
      {
        cwd: runtime.root,
        windowsHide: true,
        stdio: ["ignore", stdout, stderr],
        env: {
          ...process.env,
          AUTO_UPDATE_ENABLED: "0",
          WECHAT_TOOL_DATA_DIR: dataRoot,
          WECHAT_TOOL_OUTPUT_DIR: outputRoot,
          WECHAT_TOOL_HOST: "127.0.0.1",
          WECHAT_TOOL_PORT: String(port),
          WECHAT_TOOL_NATIVE_CORE_MODE: "required",
        },
      }
    );
    await waitForBackend(electron, port);
    const mainLog = await waitForLogText(
      path.join(profileRoot, "desktop-main.log"),
      new RegExp(`startUrl=http://127\\.0\\.0\\.1:${port}/`)
    );
    assert.doesNotMatch(mainLog, /\[main\] fatal:/);
  } catch (error) {
    const stderrText = fs.existsSync(stderrPath) ? fs.readFileSync(stderrPath, "utf8").slice(-8_000) : "";
    throw new Error(`${error.message}${stderrText ? `\nElectron stderr:\n${stderrText}` : ""}`);
  } finally {
    stopProcessTree(electron);
    fs.closeSync(stdout);
    fs.closeSync(stderr);
  }
  await waitForProcessesUnderRootRemoval(runtime.root);
}

function resolveInstallerPath(explicitPath = "", distRoot = defaultDistRoot) {
  if (String(explicitPath || "").trim()) {
    const resolved = path.resolve(explicitPath);
    assert.ok(fs.statSync(resolved).isFile(), `Missing Windows installer: ${resolved}`);
    return resolved;
  }
  const installers = fs
    .readdirSync(distRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /Setup.*\.exe$/i.test(entry.name))
    .map((entry) => path.join(distRoot, entry.name));
  assert.equal(installers.length, 1, `Expected one Windows installer in ${distRoot}.`);
  return installers[0];
}

function installerArguments(installRoot) {
  const resolved = path.resolve(installRoot);
  if (/\r|\n/.test(resolved)) throw new Error("Installer path contains a line break.");
  return ["/S", "/currentuser", `/D=${resolved}`];
}

function uninstallerArguments(packageRoot) {
  const resolved = path.resolve(packageRoot);
  if (/\r|\n/.test(resolved)) throw new Error("Uninstaller path contains a line break.");
  return ["/S", "/currentuser", `_?=${resolved}`];
}

function resolveDetachedUninstallerPath(packageRoot, tempRoot) {
  const installedRoot = path.resolve(packageRoot);
  const detached = path.resolve(tempRoot, "uninstall-smoke.exe");
  const relative = path.relative(installedRoot, detached);
  assert.ok(
    relative.startsWith("..") && !path.isAbsolute(relative),
    "Detached uninstaller must be outside the installed package root."
  );
  return detached;
}

function resolveWindowsShellFolders() {
  const powershell = path.join(
    process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
    "System32",
    "WindowsPowerShell",
    "v1.0",
    "powershell.exe"
  );
  const result = spawnSync(
    powershell,
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "@{ desktop = [Environment]::GetFolderPath('Desktop'); programs = " +
        "[Environment]::GetFolderPath('Programs') } | ConvertTo-Json -Compress",
    ],
    { encoding: "utf8", windowsHide: true }
  );
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const folders = JSON.parse(String(result.stdout || "").trim());
  assert.ok(path.isAbsolute(folders.desktop), "Windows Desktop folder is not absolute.");
  assert.ok(path.isAbsolute(folders.programs), "Windows Programs folder is not absolute.");
  return folders;
}

function resolveInstallerIdentity({
  config = packageConfig,
  shellFolders = resolveWindowsShellFolders(),
} = {}) {
  const nsis = config?.build?.nsis || {};
  const appId = String(config?.build?.appId || "").trim();
  assert.ok(appId, "Windows installer appId is required.");
  const guid = String(nsis.guid || UUID.v5(appId, electronBuilderNamespace));
  const shortcutName = String(nsis.shortcutName || config?.build?.productName || "").trim();
  assert.ok(shortcutName, "Windows installer shortcut name is required.");
  const menuCategory = typeof nsis.menuCategory === "string" ? nsis.menuCategory.trim() : "";
  return {
    guid,
    installRegistryKey: `HKCU\\Software\\${guid}`,
    uninstallRegistryKey:
      `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\` +
      guid.replaceAll("\\", " - "),
    desktopShortcut: path.join(shellFolders.desktop, `${shortcutName}.lnk`),
    startMenuShortcut: path.join(
      shellFolders.programs,
      ...(menuCategory ? [menuCategory] : []),
      `${shortcutName}.lnk`
    ),
  };
}

function registryKeyExists(keyPath) {
  const result = spawnSync("reg.exe", ["query", keyPath], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status === 0) return true;
  if (result.status === 1) return false;
  throw new Error(`Unable to query installer registry key ${keyPath}: ${result.stderr || result.stdout}`);
}

function collectInstallerResidue({
  packageRoot = "",
  identity,
  fileExists = fs.existsSync,
  keyExists = registryKeyExists,
  processPaths = [],
}) {
  const residue = [];
  if (packageRoot && fileExists(packageRoot)) residue.push(`install directory: ${packageRoot}`);
  for (const shortcut of [identity.desktopShortcut, identity.startMenuShortcut]) {
    if (fileExists(shortcut)) residue.push(`shortcut: ${shortcut}`);
  }
  for (const key of [identity.installRegistryKey, identity.uninstallRegistryKey]) {
    if (keyExists(key)) residue.push(`registry: ${key}`);
  }
  for (const processPath of processPaths) residue.push(`process: ${processPath}`);
  return residue;
}

function processesUnderRoot(root) {
  const powershell = path.join(
    process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
    "System32",
    "WindowsPowerShell",
    "v1.0",
    "powershell.exe"
  );
  const result = spawnSync(
    powershell,
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "$root = [IO.Path]::GetFullPath($env:WCE_SMOKE_PROCESS_ROOT).TrimEnd('\\') + '\\'; " +
        "@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { " +
        "$_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath).StartsWith(" +
        "$root, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { $_.ExecutablePath }) " +
        "| ConvertTo-Json -Compress",
    ],
    {
      encoding: "utf8",
      windowsHide: true,
      env: { ...process.env, WCE_SMOKE_PROCESS_ROOT: path.resolve(root) },
    }
  );
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const text = String(result.stdout || "").trim();
  if (!text) return [];
  const parsed = JSON.parse(text);
  return Array.isArray(parsed) ? parsed : parsed == null ? [] : [parsed];
}

function captureFileState(filePath) {
  if (!fs.existsSync(filePath)) return { filePath, existed: false };
  const stat = fs.statSync(filePath);
  return {
    filePath,
    existed: true,
    bytes: fs.readFileSync(filePath),
    atime: stat.atime,
    mtime: stat.mtime,
    mode: stat.mode,
  };
}

function restoreFileState(snapshot) {
  const parent = path.dirname(snapshot.filePath);
  if (snapshot.existed) {
    fs.mkdirSync(parent, { recursive: true });
    fs.writeFileSync(snapshot.filePath, snapshot.bytes, { mode: snapshot.mode });
    fs.utimesSync(snapshot.filePath, snapshot.atime, snapshot.mtime);
    return;
  }
  fs.rmSync(snapshot.filePath, { force: true });
  try {
    if (fs.readdirSync(parent).length === 0) fs.rmdirSync(parent);
  } catch (error) {
    if (!new Set(["ENOENT", "ENOTEMPTY"]).has(error?.code)) throw error;
  }
}

function runInstaller(
  executable,
  args,
  label,
  { timeout = 240_000, windowsVerbatimArguments = false } = {}
) {
  const result = spawnSync(executable, args, {
    encoding: "utf8",
    timeout,
    windowsHide: true,
    windowsVerbatimArguments,
  });
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    throw new Error(
      `${label} failed with exit code ${result.status}: ${[result.stderr, result.stdout]
        .filter(Boolean)
        .join("\n")
        .slice(-8_000)}`
    );
  }
}

function resolveInstalledPackageRoot(installBase) {
  const base = path.resolve(installBase);
  const candidates = [base];
  for (const entry of fs.readdirSync(base, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      candidates.push(path.join(base, entry.name));
    }
  }
  const matches = candidates.filter((candidate) => {
    const relative = path.relative(base, candidate);
    if (relative.startsWith("..") || path.isAbsolute(relative)) return false;
    try {
      return fs
        .statSync(path.join(candidate, "resources", "backend", "wechat-backend.exe"))
        .isFile();
    } catch {
      return false;
    }
  });
  assert.equal(
    matches.length,
    1,
    `Expected one installed package root directly under ${base}.`
  );
  return matches[0];
}

function resolveInstalledUninstaller(packageRoot) {
  const uninstallers = fs
    .readdirSync(packageRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /^Uninstall.*\.exe$/i.test(entry.name));
  assert.equal(uninstallers.length, 1, "Expected exactly one installed uninstaller.");
  return path.join(packageRoot, uninstallers[0].name);
}

async function waitForInstallerRemoval(
  packageRoot,
  identity,
  processRoot,
  timeoutMs = 60_000
) {
  const deadline = Date.now() + timeoutMs;
  let residue = [];
  while (Date.now() < deadline) {
    const processPaths = processesUnderRoot(processRoot);
    residue = collectInstallerResidue({ packageRoot, identity, processPaths });
    if (residue.length === 0) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Windows uninstaller left state behind:\n${residue.join("\n")}`);
}

async function smokeInstaller(installerPath, tempRoot, env = process.env) {
  if (
    String(env.WCE_WINDOWS_INSTALLER_SMOKE_ALLOWED || "") !== "1" ||
    String(env.GITHUB_ACTIONS || "").toLowerCase() !== "true" ||
    String(env.RUNNER_OS || "").toLowerCase() !== "windows" ||
    String(env.RUNNER_ENVIRONMENT || "").toLowerCase() !== "github-hosted"
  ) {
    throw new Error(
      "Installer smoke requires a GitHub-hosted Windows Actions runner and " +
        "WCE_WINDOWS_INSTALLER_SMOKE_ALLOWED=1."
    );
  }
  const installRoot = path.join(tempRoot, "installed");
  fs.mkdirSync(tempRoot, { recursive: true });
  const resolvedTemp = path.resolve(tempRoot);
  const resolvedInstall = path.resolve(installRoot);
  if (path.dirname(resolvedInstall) !== resolvedTemp) {
    throw new Error("Installer smoke target escaped its temporary root.");
  }
  const identity = resolveInstallerIdentity();
  const preexisting = collectInstallerResidue({ identity });
  assert.deepEqual(
    preexisting,
    [],
    `Installer smoke refuses to overwrite existing product state:\n${preexisting.join("\n")}`
  );
  const appDataRoot = String(env.APPDATA || process.env.APPDATA || "").trim();
  assert.ok(appDataRoot, "APPDATA is required for installer smoke state isolation.");
  const settingsSnapshot = captureFileState(
    path.join(appDataRoot, packageConfig.name, "desktop-settings.json")
  );

  let packageRoot = null;
  let detachedUninstaller = null;
  let manifest = null;
  let smokeError = null;
  try {
    runInstaller(installerPath, installerArguments(resolvedInstall), "Windows installer");
    packageRoot = resolveInstalledPackageRoot(resolvedInstall);
    const uninstaller = resolveInstalledUninstaller(packageRoot);
    detachedUninstaller = resolveDetachedUninstallerPath(packageRoot, tempRoot);
    fs.copyFileSync(uninstaller, detachedUninstaller);

    for (const shortcut of [identity.desktopShortcut, identity.startMenuShortcut]) {
      assert.ok(fs.existsSync(shortcut), `Windows installer did not create shortcut: ${shortcut}`);
    }
    for (const key of [identity.installRegistryKey, identity.uninstallRegistryKey]) {
      assert.ok(registryKeyExists(key), `Windows installer did not create registry key: ${key}`);
    }

    manifest = await smokeRuntime(packageRoot, path.join(tempRoot, "installed-smoke"));
    await smokeElectronApp(packageRoot, path.join(tempRoot, "electron-smoke"));
  } catch (error) {
    smokeError = error;
  }

  let uninstallError = null;
  if (packageRoot && detachedUninstaller) {
    try {
      runInstaller(
        detachedUninstaller,
        uninstallerArguments(packageRoot),
        "Windows uninstaller",
        { windowsVerbatimArguments: true }
      );
      await waitForInstallerRemoval(packageRoot, identity, tempRoot);
    } catch (error) {
      uninstallError = error;
    }
  }

  let restoreError = null;
  try {
    restoreFileState(settingsSnapshot);
  } catch (error) {
    restoreError = error;
  }

  const errors = [smokeError, uninstallError, restoreError].filter(Boolean);
  if (errors.length > 1) {
    throw new AggregateError(errors, "Installer smoke, uninstall, or state restoration failed.");
  }
  if (errors.length === 1) throw errors[0];
  return manifest;
}

async function main() {
  if (process.platform !== "win32") {
    throw new Error("The packaged Windows smoke test must run on Windows.");
  }
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "wda-win-package-smoke-"));
  let completed = false;
  try {
    const unpackedRoot = resolveUnpackedRoot();
    const unpackedManifest = await smokeRuntime(
      unpackedRoot,
      path.join(tempRoot, "unpacked-smoke")
    );
    console.log(`Windows unpacked native-core smoke passed: build=${unpackedManifest.buildId}`);

    if (String(process.env.WCE_WINDOWS_INSTALLER_SMOKE_ALLOWED || "") === "1") {
      const installer = resolveInstallerPath(process.env.WCE_WINDOWS_INSTALLER_PATH);
      const installedManifest = await smokeInstaller(installer, path.join(tempRoot, "installer"));
      assert.equal(installedManifest.buildId, unpackedManifest.buildId);
      console.log(`Windows installer native-core smoke passed: build=${installedManifest.buildId}`);
    }
    completed = true;
  } finally {
    if (completed) {
      fs.rmSync(tempRoot, { recursive: true, force: true });
    } else {
      console.error(`Windows package smoke preserved failure evidence: ${tempRoot}`);
    }
  }
}

module.exports = {
  resolvePackagedRuntime,
  installerArguments,
  uninstallerArguments,
  resolveDetachedUninstallerPath,
  resolveInstallerIdentity,
  collectInstallerResidue,
  resolveInstalledPackageRoot,
  resolveInstalledUninstaller,
  resolveInstallerPath,
  smokeInstaller,
  smokeElectronApp,
  smokeRuntime,
  resolveUnpackedRoot,
  waitForBackend,
  waitForInstallerRemoval,
};

if (require.main === module) {
  main().catch((error) => {
    console.error(error?.stack || error);
    process.exit(1);
  });
}
