"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  collectInstallerResidue,
  installerArguments,
  resolveDetachedUninstallerPath,
  resolveInstallerIdentity,
  resolveInstalledPackageRoot,
  resolveInstalledUninstaller,
  resolveInstallerPath,
  resolvePackagedRuntime,
  resolveUnpackedRoot,
  smokeInstaller,
  uninstallerArguments,
} = require("../scripts/smoke-windows-package.cjs");

function makePackagedRuntime() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-win-smoke-test-"));
  const backendRoot = path.join(root, "resources", "backend");
  const nativeRoot = path.join(backendRoot, "native");
  fs.mkdirSync(nativeRoot, { recursive: true });
  for (const fileName of [
    "wechat-backend.exe",
    path.join("native", "wechatdb_client.dll"),
    path.join("native", "wechatdb_broker.exe"),
    path.join("native", "wechatdb_native_build.json"),
  ]) {
    fs.writeFileSync(path.join(backendRoot, fileName), "test");
  }
  fs.writeFileSync(path.join(root, "WeChatDataAnalysis.exe"), "test");
  return root;
}

test("Windows packaged smoke resolves the backend and complete native trio", (t) => {
  const root = makePackagedRuntime();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  const runtime = resolvePackagedRuntime(root);
  assert.equal(path.basename(runtime.application), "WeChatDataAnalysis.exe");
  assert.equal(path.basename(runtime.backend), "wechat-backend.exe");
  assert.equal(path.basename(runtime.client), "wechatdb_client.dll");
  assert.equal(path.basename(runtime.broker), "wechatdb_broker.exe");
  assert.equal(path.basename(runtime.manifest), "wechatdb_native_build.json");
});

test("Windows packaged smoke rejects a partial native trio", (t) => {
  const root = makePackagedRuntime();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.rmSync(path.join(root, "resources", "backend", "native", "wechatdb_broker.exe"));

  assert.throws(() => resolvePackagedRuntime(root), /wechatdb_broker\.exe/);
});

test("Windows packaged smoke honors the native consumer's explicit unpacked root", () => {
  const explicit = path.resolve(os.tmpdir(), "wda-explicit-unpacked");
  const fromEnvironment = path.resolve(os.tmpdir(), "wda-environment-unpacked");

  assert.equal(
    resolveUnpackedRoot({
      argv: [explicit],
      env: { WCE_WINDOWS_UNPACKED_ROOT: fromEnvironment },
    }),
    explicit
  );
  assert.equal(
    resolveUnpackedRoot({
      argv: [],
      env: { WCE_WINDOWS_UNPACKED_ROOT: fromEnvironment },
    }),
    fromEnvironment
  );
});

test("Windows installer smoke keeps the silent target isolated and last", () => {
  const root = path.resolve(os.tmpdir(), "wda-installer-contract", "installed");
  assert.deepEqual(installerArguments(root), ["/S", "/currentuser", `/D=${root}`]);
});

test("Windows installer smoke runs a detached synchronous uninstaller", () => {
  const tempRoot = path.resolve(os.tmpdir(), "wda-installer-contract");
  const packageRoot = path.join(tempRoot, "installed", "WeChatDataAnalysis");
  const detached = resolveDetachedUninstallerPath(packageRoot, tempRoot);
  const relative = path.relative(packageRoot, detached);
  assert.ok(relative.startsWith("..") && !path.isAbsolute(relative));

  const args = uninstallerArguments(packageRoot);
  assert.deepEqual(args, ["/S", "/currentuser", `_?=${packageRoot}`]);
  assert.equal(args.at(-1), `_?=${packageRoot}`);
});

test("Windows installer identity follows electron-builder app and shell paths", () => {
  const identity = resolveInstallerIdentity({
    config: {
      name: "wechat-data-analysis-desktop",
      build: {
        appId: "com.lifearchive.wechatdataanalysis",
        productName: "WeChatDataAnalysis",
        nsis: {},
      },
    },
    shellFolders: {
      desktop: "C:\\Users\\runner\\Desktop",
      programs: "C:\\Users\\runner\\Start Menu\\Programs",
    },
  });
  assert.equal(identity.guid, "89033aec-6cb5-5c17-b45d-43427d646d1b");
  assert.equal(identity.installRegistryKey, "HKCU\\Software\\89033aec-6cb5-5c17-b45d-43427d646d1b");
  assert.match(identity.uninstallRegistryKey, /CurrentVersion\\Uninstall\\89033aec/);
  assert.equal(
    identity.desktopShortcut,
    "C:\\Users\\runner\\Desktop\\WeChatDataAnalysis.lnk"
  );
  assert.equal(
    identity.startMenuShortcut,
    "C:\\Users\\runner\\Start Menu\\Programs\\WeChatDataAnalysis.lnk"
  );
});

test("Windows installer residue includes every incomplete uninstall surface", () => {
  const identity = {
    desktopShortcut: "desktop.lnk",
    startMenuShortcut: "start.lnk",
    installRegistryKey: "HKCU\\Software\\app",
    uninstallRegistryKey: "HKCU\\Software\\Uninstall\\app",
  };
  const files = new Set(["installed", "start.lnk"]);
  const keys = new Set([identity.uninstallRegistryKey]);
  assert.deepEqual(
    collectInstallerResidue({
      packageRoot: "installed",
      identity,
      fileExists: (candidate) => files.has(candidate),
      keyExists: (candidate) => keys.has(candidate),
      processPaths: ["installed\\Uninstall.exe"],
    }),
    [
      "install directory: installed",
      "shortcut: start.lnk",
      `registry: ${identity.uninstallRegistryKey}`,
      "process: installed\\Uninstall.exe",
    ]
  );
});

test("Windows installer smoke resolves the NSIS-created product subdirectory", (t) => {
  const installBase = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installed-base-"));
  t.after(() => fs.rmSync(installBase, { recursive: true, force: true }));
  const source = makePackagedRuntime();
  const packageRoot = path.join(installBase, "WeChatDataAnalysis");
  fs.renameSync(source, packageRoot);
  const uninstaller = path.join(packageRoot, "Uninstall WeChatDataAnalysis.exe");
  fs.writeFileSync(uninstaller, "fixture");

  assert.equal(resolveInstalledPackageRoot(installBase), packageRoot);
  assert.equal(resolveInstalledUninstaller(packageRoot), uninstaller);
});

test("Windows installer discovery requires one exact setup executable", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-find-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const installer = path.join(root, "WeChatDataAnalysis-1.0.0-Setup.exe");
  fs.writeFileSync(installer, "fixture");
  assert.equal(resolveInstallerPath("", root), installer);
  fs.writeFileSync(path.join(root, "Other-Setup.exe"), "fixture");
  assert.throws(() => resolveInstallerPath("", root), /Expected one Windows installer/);
});

test("Windows installer smoke is disabled outside a dedicated runner", async () => {
  await assert.rejects(
    () => smokeInstaller("missing.exe", path.join(os.tmpdir(), "wda-disabled-smoke"), {}),
    /WCE_WINDOWS_INSTALLER_SMOKE_ALLOWED=1/
  );
});
