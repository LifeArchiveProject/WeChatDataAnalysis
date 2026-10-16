const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const packageLock = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package-lock.json"), "utf8"));
const installerScript = fs.readFileSync(path.join(desktopRoot, "scripts", "installer-custom.nsh"), "utf8");
const installDirProbePath = path.join(desktopRoot, "scripts", "installer-install-dir.ps1");
const powershellPath = path.join(
  process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
  "System32",
  "WindowsPowerShell",
  "v1.0",
  "powershell.exe"
);

function runInstallDirHelper(args) {
  return spawnSync(
    powershellPath,
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      installDirProbePath,
      ...args,
    ],
    { encoding: "utf8", windowsHide: true }
  );
}

function runInstallDirProbe(installDir) {
  return runInstallDirHelper(["-Mode", "Validate", "-InstallDir", installDir]);
}

function createShortcut(shortcutPath, targetPath) {
  const quote = (value) => `'${value.replaceAll("'", "''")}'`;
  const result = spawnSync(
    powershellPath,
    [
      "-NoProfile",
      "-Command",
      "$shell = New-Object -ComObject WScript.Shell; " +
        `$link = $shell.CreateShortcut(${quote(shortcutPath)}); ` +
        `$link.TargetPath = ${quote(targetPath)}; $link.Save()`,
    ],
    { encoding: "utf8", windowsHide: true }
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

test("electron-builder is pinned to a System.dll-safe release", () => {
  const expectedVersion = "26.15.3";
  assert.equal(packageJson.devDependencies["electron-builder"], expectedVersion);
  assert.equal(packageLock.packages[""].devDependencies["electron-builder"], expectedVersion);
  assert.equal(packageLock.packages["node_modules/electron-builder"].version, expectedVersion);
  assert.equal(packageLock.packages["node_modules/app-builder-lib"].version, expectedVersion);

  const multiUserTemplate = fs.readFileSync(
    path.join(desktopRoot, "node_modules", "app-builder-lib", "templates", "nsis", "multiUser.nsh"),
    "utf8"
  );
  assert.match(multiUserTemplate, /KERNEL32::lstrcpynW/);
  assert.doesNotMatch(multiUserTemplate, /\*\$2\(&w\$\{NSIS_MAX_STRLEN\} \.s\)/);
});

test("installer validates the final install directory before GUI or silent installation", () => {
  const customInit = installerScript.match(/!macro customInit(?<body>[^]*?)!macroend/)?.groups?.body;
  const pageLeave = installerScript.match(
    /Function WDA_InstallDirPageLeave(?<body>[^]*?)FunctionEnd/
  )?.groups?.body;
  assert.ok(customInit);
  assert.ok(pageLeave);

  assert.match(installerScript, /File \/oname=\$PLUGINSDIR\\wda-install-dir\.ps1/);
  assert.match(installerScript, /Function WDA_ValidateInstallDir/);
  assert.match(customInit, /IfSilent/);
  assert.match(customInit, /\$installMode == "all"[^]*?\$\{UAC_IsAdmin\}/);
  assert.match(customInit, /Call WDA_EnsureAppSubDir[^]*?Call WDA_ValidateInstallDir/);
  assert.match(customInit, /SetErrorLevel 2[^]*?Quit/);
  assert.match(customInit, /WDA_CleanupGhostPerUserInstall/);
  assert.match(pageLeave, /Call WDA_ValidateInstallDir[^]*?MessageBox[^]*?Abort/);
  assert.match(pageLeave, /Call WDA_RemoveLegacyOutputLink/);
});

test("installer only repairs a coherent ghost per-user installation", () => {
  const cleanupMacro = installerScript.match(
    /!macro WDA_CleanupGhostPerUserInstall(?<body>[^]*?)!macroend/
  )?.groups?.body;
  assert.ok(cleanupMacro);
  assert.match(cleanupMacro, /ReadRegStr[^]*?HKCU[^]*?InstallLocation/);
  assert.match(cleanupMacro, /ReadRegStr[^]*?HKCU[^]*?UninstallString/);
  assert.match(cleanupMacro, /ReadRegStr[^]*?HKCU[^]*?QuietUninstallString/);
  assert.match(cleanupMacro, /\$R9 == '\"\$R8\\\$\{UNINSTALL_FILENAME\}\" \/currentuser'/);
  assert.match(cleanupMacro, /\$R7 == '\"\$R8\\\$\{UNINSTALL_FILENAME\}\" \/currentuser \/S'/);
  assert.match(cleanupMacro, /\$\{GetRoot\} "\$R8" \$R6/);
  assert.match(cleanupMacro, /\$\{FileExists\} "\$R6\\\."/);
  assert.match(cleanupMacro, /APP_EXECUTABLE_FILENAME/);
  assert.match(cleanupMacro, /UNINSTALL_FILENAME/);
  assert.match(cleanupMacro, /-Mode RemoveGhostShortcuts/);
  assert.match(cleanupMacro, /DeleteRegKey HKCU "\$\{UNINSTALL_REGISTRY_KEY\}"/);
  assert.match(cleanupMacro, /DeleteRegKey HKCU "\$\{INSTALL_REGISTRY_KEY\}"/);
  assert.doesNotMatch(cleanupMacro, /\bRMDir\b/);
});

test(
  "install directory probe verifies write access and removes all probe artifacts",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-probe-"));
    const newTarget = path.join(root, "new-parent", "\u5b89\u88c5-$folder-$(1+1)", "WeChatDataAnalysis");
    const existingTarget = path.join(root, "existing", "WeChatDataAnalysis");

    try {
      const newResult = runInstallDirProbe(newTarget);
      assert.equal(newResult.status, 0, newResult.stderr || newResult.stdout);
      assert.equal(fs.existsSync(newTarget), false);
      assert.equal(fs.existsSync(path.join(root, "new-parent")), false);

      fs.mkdirSync(existingTarget, { recursive: true });
      fs.writeFileSync(path.join(existingTarget, "keep.txt"), "keep", "utf8");
      const existingResult = runInstallDirProbe(existingTarget);
      assert.equal(existingResult.status, 0, existingResult.stderr || existingResult.stdout);
      assert.equal(fs.readFileSync(path.join(existingTarget, "keep.txt"), "utf8"), "keep");
      assert.deepEqual(
        fs.readdirSync(existingTarget).filter((name) => name.startsWith(".wda-install-write-test-")),
        []
      );
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "ghost repair removes only shortcuts that target the missing installation",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-ghost-"));
    const ghostExecutable = path.join(root, "missing-install", "WeChatDataAnalysis.exe");
    const otherExecutable = path.join(root, "other-install", "WeChatDataAnalysis.exe");
    const ghostShortcut = path.join(root, "ghost.lnk");
    const otherShortcut = path.join(root, "other.lnk");

    try {
      createShortcut(ghostShortcut, ghostExecutable);
      createShortcut(otherShortcut, otherExecutable);
      const result = runInstallDirHelper([
        "-Mode",
        "RemoveGhostShortcuts",
        "-InstallDir",
        path.dirname(ghostExecutable),
        "-ExpectedExecutablePath",
        ghostExecutable,
        "-ShortcutPath1",
        ghostShortcut,
        "-ShortcutPath2",
        otherShortcut,
      ]);

      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.equal(fs.existsSync(ghostShortcut), false);
      assert.equal(fs.existsSync(otherShortcut), true);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "install directory probe rejects an unusable path without changing its parent",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-probe-error-"));
    const blockingFile = path.join(root, "not-a-directory");
    fs.writeFileSync(blockingFile, "keep", "utf8");

    try {
      const result = runInstallDirProbe(path.join(blockingFile, "WeChatDataAnalysis"));
      assert.notEqual(result.status, 0);
      assert.equal(fs.readFileSync(blockingFile, "utf8"), "keep");
      assert.deepEqual(fs.readdirSync(root), ["not-a-directory"]);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);
