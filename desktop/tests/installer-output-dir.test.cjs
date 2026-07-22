const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const desktopRoot = path.resolve(__dirname, "..");
const installerScript = fs.readFileSync(path.join(desktopRoot, "scripts", "installer-custom.nsh"), "utf8");
const settingsScriptPath = path.join(desktopRoot, "scripts", "installer-output-dir.ps1");
const settingsScript = fs.readFileSync(settingsScriptPath, "utf8");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const powershellPath = path.join(
  process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
  "System32",
  "WindowsPowerShell",
  "v1.0",
  "powershell.exe"
);

function runInstallerSettingsHelper(args) {
  return spawnSync(
    powershellPath,
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", settingsScriptPath, ...args],
    { encoding: "utf8", windowsHide: true }
  );
}

test("installer stores output settings under Electron's package-name userData directory", () => {
  assert.equal(packageJson.name, "wechat-data-analysis-desktop");
  assert.match(installerScript, /WDA_RUNTIME_APPDATA_NAME "\$\{APP_PACKAGE_NAME\}"/);
  assert.match(
    installerScript,
    /WDA_DEFAULT_SETTINGS_PATH "\$APPDATA\\\$\{WDA_RUNTIME_APPDATA_NAME\}\\desktop-settings\.json"/
  );
  assert.match(
    installerScript,
    /WDA_DEFAULT_OUTPUT_DIR "\$APPDATA\\\$\{WDA_RUNTIME_APPDATA_NAME\}\\output"/
  );
});

test("installer writes desktop settings as UTF-8 without a BOM", () => {
  assert.match(settingsScript, /UTF8Encoding\(\$false\)/);
  assert.match(settingsScript, /FileMode\]::CreateNew/);
  assert.match(settingsScript, /\.Flush\(\$true\)/);
  assert.match(settingsScript, /\[System\.IO\.File\]::Replace/);
  assert.match(settingsScript, /\[System\.IO\.File\]::Move/);
  assert.doesNotMatch(settingsScript, /Set-Content[^\r\n]+-Encoding UTF8/);
  assert.doesNotMatch(settingsScript, /\[System\.IO\.File\]::WriteAllText\(\$DefaultSettingsPath/);
});

test("installer keeps filename-based AppData as a legacy read and uninstall alias", () => {
  assert.match(installerScript, /WDA_FILENAME_SETTINGS_PATH/);
  assert.match(installerScript, /WDA_FILENAME_OUTPUT_DIR/);
  assert.match(settingsScript, /PSObject\.Properties\['pendingOutputDir'\]/);
  assert.match(settingsScript, /foreach \(\$candidate in Get-SettingsCandidates\)/);
});

test("installer uses a fixed PowerShell file and the interactive user's AppData", () => {
  assert.match(installerScript, /-File "\$PLUGINSDIR\\wda-output-dir\.ps1"/);
  assert.match(
    installerScript,
    /File \/oname=\$PLUGINSDIR\\wda-output-dir\.ps1 "\$\{__FILEDIR__\}\\installer-output-dir\.ps1"/
  );
  assert.doesNotMatch(installerScript, /-Command/);
  assert.match(installerScript, /Function WDA_UseCurrentUserAppData/);
  assert.match(installerScript, /SetShellVarContext current/);
  assert.match(installerScript, /\$0 != "0"/);
  assert.match(installerScript, /无法保存 output 目录设置[^]*?Abort/);
});

test("installer checks current settings before removing legacy output junctions", () => {
  const cleanupFunction = installerScript.match(
    /Function WDA_RemoveLegacyOutputLink(?<body>[^]*?)FunctionEnd/
  )?.groups?.body;
  assert.ok(cleanupFunction);
  assert.match(cleanupFunction, /Call WDA_UseCurrentUserAppData/);
  assert.match(cleanupFunction, /-Mode RemoveLegacyLinks/);
  assert.match(cleanupFunction, /-DefaultSettingsPath "\$\{WDA_DEFAULT_SETTINGS_PATH\}"/);
  assert.match(cleanupFunction, /-LegacySettingsPath1 "\$\{WDA_PRODUCT_SETTINGS_PATH\}"/);
  assert.match(cleanupFunction, /-LegacySettingsPath2 "\$\{WDA_FILENAME_SETTINGS_PATH\}"/);
  assert.doesNotMatch(cleanupFunction, /\bRMDir\b/);
  assert.match(settingsScript, /Get-InstallerOutputDirectory/);
  assert.match(settingsScript, /Test-PathsOverlap/);
});

test(
  "legacy output cleanup preserves lexical overlap but removes links to directly configured targets",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-junction-"));
    const defaultOutput = path.join(root, "default-output");
    const unrelatedOutput = path.join(root, "unrelated-output");

    const invokeCleanup = ({ name, canonical, legacy }) => {
      const caseRoot = path.join(root, name);
      const target = path.join(caseRoot, "real-output");
      const link = path.join(caseRoot, "install", "output");
      const settingsPath = path.join(caseRoot, "canonical", "desktop-settings.json");
      const legacyPath = path.join(caseRoot, "legacy", "desktop-settings.json");
      fs.mkdirSync(target, { recursive: true });
      fs.mkdirSync(path.dirname(link), { recursive: true });
      fs.writeFileSync(path.join(target, "keep.txt"), name, "utf8");
      fs.symlinkSync(target, link, "junction");
      if (canonical) {
        fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
        fs.writeFileSync(settingsPath, JSON.stringify(canonical({ link, target })), "utf8");
      }
      if (legacy) {
        fs.mkdirSync(path.dirname(legacyPath), { recursive: true });
        fs.writeFileSync(legacyPath, JSON.stringify(legacy({ link, target })), "utf8");
      }

      const result = runInstallerSettingsHelper([
        "-Mode",
        "RemoveLegacyLinks",
        "-DefaultSettingsPath",
        settingsPath,
        "-DefaultOutputPath",
        defaultOutput,
        "-LegacySettingsPath1",
        legacyPath,
        "-CandidateLinkPath1",
        link,
      ]);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      return { link, target };
    };

    try {
      const lexical = invokeCleanup({
        name: "canonical-lexical",
        canonical: ({ link }) => ({ outputDir: path.join(link, "..", "output", "account") }),
      });
      assert.ok(fs.existsSync(lexical.link));

      const pendingLexical = invokeCleanup({
        name: "canonical-pending-lexical",
        canonical: ({ link }) => ({ outputDir: unrelatedOutput, pendingOutputDir: link.toUpperCase() }),
      });
      assert.ok(fs.existsSync(pendingLexical.link));

      const legacyLexical = invokeCleanup({
        name: "legacy-lexical",
        legacy: ({ link }) => ({ outputDir: link }),
      });
      assert.ok(fs.existsSync(legacyLexical.link));

      const directTarget = invokeCleanup({
        name: "direct-target",
        canonical: ({ target }) => ({ outputDir: target }),
      });
      assert.equal(fs.existsSync(directTarget.link), false);
      assert.equal(fs.readFileSync(path.join(directTarget.target, "keep.txt"), "utf8"), "direct-target");
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "installer settings helper preserves PowerShell metacharacters in selected paths",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-settings-"));
    const specialRoot = path.join(root, "配置-$root-$(1+1)-`tick");
    const settingsPath = path.join(specialRoot, "desktop-settings.json");
    const defaultOutput = path.join(specialRoot, "default-$output");
    const selectedOutput = String.raw`E:\聊天记录\$folder\$(1+1)\back\`tick\out`;
    const powershell = path.join(
      process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
      "System32",
      "WindowsPowerShell",
      "v1.0",
      "powershell.exe"
    );

    try {
      const result = spawnSync(
        powershell,
        [
          "-NoProfile",
          "-ExecutionPolicy",
          "Bypass",
          "-File",
          settingsScriptPath,
          "-Mode",
          "Write",
          "-DefaultSettingsPath",
          settingsPath,
          "-DefaultOutputPath",
          defaultOutput,
          "-SelectedOutputPath",
          selectedOutput,
        ],
        { encoding: "utf8", windowsHide: true }
      );

      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.equal(JSON.parse(fs.readFileSync(settingsPath, "utf8")).pendingOutputDir, selectedOutput);

      const readResult = spawnSync(
        powershell,
        [
          "-NoProfile",
          "-ExecutionPolicy",
          "Bypass",
          "-File",
          settingsScriptPath,
          "-Mode",
          "Read",
          "-DefaultSettingsPath",
          settingsPath,
          "-DefaultOutputPath",
          defaultOutput,
        ],
        { encoding: "utf8", windowsHide: true }
      );
      assert.equal(readResult.status, 0, readResult.stderr || readResult.stdout);
      assert.equal(readResult.stdout, selectedOutput);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "legacy settings are read in order and migrated into the canonical settings file",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-legacy-"));
    const settingsPath = path.join(root, "canonical", "desktop-settings.json");
    const legacyPath1 = path.join(root, "legacy-product.json");
    const legacyPath2 = path.join(root, "legacy-filename.json");
    const defaultOutput = path.join(root, "default-output");
    const selectedOutput = path.join(root, "selected-output");
    const legacyOutput1 = path.join(root, "legacy-output-1");
    const legacyOutput2 = path.join(root, "legacy-output-2");
    const powershell = path.join(
      process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
      "System32",
      "WindowsPowerShell",
      "v1.0",
      "powershell.exe"
    );

    try {
      fs.writeFileSync(legacyPath1, JSON.stringify({ outputDir: legacyOutput1, marker: "first" }), "utf8");
      fs.writeFileSync(legacyPath2, JSON.stringify({ outputDir: legacyOutput2, marker: "second" }), "utf8");
      const commonArgs = [
        "-DefaultSettingsPath",
        settingsPath,
        "-DefaultOutputPath",
        defaultOutput,
        "-LegacySettingsPath1",
        legacyPath1,
        "-LegacySettingsPath2",
        legacyPath2,
      ];
      const readResult = spawnSync(
        powershell,
        ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", settingsScriptPath, "-Mode", "Read", ...commonArgs],
        { encoding: "utf8", windowsHide: true }
      );
      assert.equal(readResult.status, 0, readResult.stderr || readResult.stdout);
      assert.equal(readResult.stdout, legacyOutput1);

      const writeResult = spawnSync(
        powershell,
        [
          "-NoProfile",
          "-ExecutionPolicy",
          "Bypass",
          "-File",
          settingsScriptPath,
          "-Mode",
          "Write",
          ...commonArgs,
          "-SelectedOutputPath",
          selectedOutput,
        ],
        { encoding: "utf8", windowsHide: true }
      );
      assert.equal(writeResult.status, 0, writeResult.stderr || writeResult.stdout);
      const canonical = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
      assert.equal(canonical.marker, "first");
      assert.equal(canonical.pendingOutputDir, selectedOutput);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "settings helper exits nonzero when the canonical settings file cannot be written",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-write-error-"));
    const settingsPath = path.join(root, "desktop-settings.json");
    const powershell = path.join(
      process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
      "System32",
      "WindowsPowerShell",
      "v1.0",
      "powershell.exe"
    );

    try {
      fs.mkdirSync(settingsPath);
      const result = spawnSync(
        powershell,
        [
          "-NoProfile",
          "-ExecutionPolicy",
          "Bypass",
          "-File",
          settingsScriptPath,
          "-Mode",
          "Write",
          "-DefaultSettingsPath",
          settingsPath,
          "-DefaultOutputPath",
          path.join(root, "default-output"),
          "-SelectedOutputPath",
          path.join(root, "selected-output"),
        ],
        { encoding: "utf8", windowsHide: true }
      );
      assert.notEqual(result.status, 0);
      assert.ok(result.stderr.trim());
      assert.deepEqual(
        fs.readdirSync(root).filter((name) => name.startsWith(".desktop-settings.json.tmp-")),
        []
      );
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "failed atomic replacement preserves the previous settings and removes its temporary file",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-atomic-error-"));
    const settingsPath = path.join(root, "desktop-settings.json");
    const original = '{"outputDir":"E:\\\\existing","marker":"keep"}';

    try {
      fs.writeFileSync(settingsPath, original, "utf8");
      fs.chmodSync(settingsPath, 0o444);
      const result = runInstallerSettingsHelper(
        [
          "-Mode",
          "Write",
          "-DefaultSettingsPath",
          settingsPath,
          "-DefaultOutputPath",
          path.join(root, "default-output"),
          "-SelectedOutputPath",
          path.join(root, "new-output"),
        ]
      );

      assert.notEqual(result.status, 0);
      assert.equal(fs.readFileSync(settingsPath, "utf8"), original);
      assert.deepEqual(
        fs.readdirSync(root).filter((name) => name.startsWith(".desktop-settings.json.tmp-")),
        []
      );
    } finally {
      if (fs.existsSync(settingsPath)) fs.chmodSync(settingsPath, 0o666);
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);

test(
  "canonical default settings take precedence over stale legacy output settings",
  { skip: process.platform !== "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-installer-precedence-"));
    const settingsPath = path.join(root, "desktop-settings.json");
    const legacyPath = path.join(root, "legacy-settings.json");
    const defaultOutput = path.join(root, "default-output");
    const powershell = path.join(
      process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
      "System32",
      "WindowsPowerShell",
      "v1.0",
      "powershell.exe"
    );

    try {
      fs.writeFileSync(settingsPath, '{"outputDir":"","pendingOutputDir":null}', "utf8");
      fs.writeFileSync(legacyPath, JSON.stringify({ outputDir: "E:\\stale-output" }), "utf8");
      const result = spawnSync(
        powershell,
        [
          "-NoProfile",
          "-ExecutionPolicy",
          "Bypass",
          "-File",
          settingsScriptPath,
          "-Mode",
          "Read",
          "-DefaultSettingsPath",
          settingsPath,
          "-DefaultOutputPath",
          defaultOutput,
          "-LegacySettingsPath1",
          legacyPath,
        ],
        { encoding: "utf8", windowsHide: true }
      );

      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.equal(result.stdout.trim(), defaultOutput);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
);
