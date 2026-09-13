const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { writeDesktopSettingsFileAtomic, parseDesktopSettingsText } = require("../src/desktop-settings.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const helperPath = path.join(desktopRoot, "scripts", "installer-output-dir.ps1");
const installerSource = fs.readFileSync(path.join(desktopRoot, "scripts", "installer-custom.nsh"), "utf8");
const powershellPath = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");

function findCompiler() {
  if (process.env.NSIS_MAKENSIS) return process.env.NSIS_MAKENSIS;
  const cacheRoot = process.env.ELECTRON_BUILDER_CACHE || path.join(process.env.LOCALAPPDATA || "", "electron-builder", "Cache");
  const nsisRoot = path.join(cacheRoot, "nsis");
  if (!fs.existsSync(nsisRoot)) return null;
  return fs.readdirSync(nsisRoot).sort().reverse()
    .map((name) => path.join(nsisRoot, name, "makensis.exe"))
    .find((candidate) => fs.existsSync(candidate));
}

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", windowsHide: true, timeout: 30000 });
  assert.equal(result.status, 0, result.error?.message || result.stderr || result.stdout);
  return result;
}

// 测试只编译目录初始化和保存函数；所有配置与输出均位于独立临时目录。
test("compiled NSIS and PowerShell preserve Unicode paths through install and upgrade", {
  skip: process.platform !== "win32" ? "Windows integration test"
    : !findCompiler() && process.env.WDA_REQUIRE_NSIS_TEST !== "1" && "NSIS compiler unavailable; set NSIS_MAKENSIS",
}, () => {
  assert.ok(findCompiler(), "NSIS compiler is required; set NSIS_MAKENSIS or populate the electron-builder cache");
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-nsis-unicode-"));
  try {
    const configRoot = path.join(root, "中文配置 & 空格");
    fs.mkdirSync(configRoot);
    const settingsPath = path.join(configRoot, "desktop-settings.json");
    const legacyPath = path.join(configRoot, "legacy.json");
    const resultPath = path.join(root, "actual.txt");
    const defaultOutput = path.join(configRoot, "默认输出📁");
    const exePath = path.join(root, "probe.exe");
    const quote = (value) => `"${value.replaceAll("$", "$$")}"`;
    const functions = ["WDA_InitOutputDirSelection", "WDA_WritePendingOutputDirSetting"].map((name) => {
      const match = installerSource.match(new RegExp(`Function ${name}[^]*?FunctionEnd`));
      assert.ok(match, name);
      return match[0];
    });
    const script = [
      "Unicode true", "RequestExecutionLevel user", "SilentInstall silent", "!include LogicLib.nsh",
      `OutFile ${quote(exePath)}`, 'Name "Unicode path probe"', "Var WDA_SelectedOutputDir",
      `!define WDA_DEFAULT_SETTINGS_PATH ${quote(settingsPath)}`,
      `!define WDA_DEFAULT_OUTPUT_DIR ${quote(defaultOutput)}`,
      `!define WDA_PRODUCT_SETTINGS_PATH ${quote(legacyPath)}`,
      `!define WDA_FILENAME_SETTINGS_PATH ${quote(path.join(root, "missing.json"))}`,
      "Function WDA_UseCurrentUserAppData", "FunctionEnd",
      "Function WDA_RestoreInstallShellContext", "FunctionEnd",
      "Function WDA_PrepareOutputDirScript", "InitPluginsDir",
      `File /oname=$PLUGINSDIR\\wda-output-dir.ps1 ${quote(helperPath)}`, "FunctionEnd",
      ...functions,
      "Section", "Call WDA_InitOutputDirSelection", "Call WDA_WritePendingOutputDirSetting",
      `FileOpen $3 ${quote(resultPath)} w`, "FileWriteUTF16LE $3 $WDA_SelectedOutputDir", "FileClose $3",
      "SectionEnd",
    ].join("\n");
    const scriptPath = path.join(root, "probe.nsi");
    fs.writeFileSync(scriptPath, "\uFEFF" + script, "utf8");
    run(findCompiler(), ["/V2", scriptPath]);

    const chineseOutput = path.join(configRoot, "软件备份", "𠮷", "wechat-data-analysis");
    const pendingOutput = path.join(configRoot, "聊天记录 & 空格-$folder-$(1+1)-`tick", "输出📁");
    const cases = [
      { name: "首次安装", expected: defaultOutput },
      { name: "Electron 无 BOM 配置升级", settings: { outputDir: chineseOutput, label: "中文配置" }, expected: chineseOutput },
      { name: "已选择待迁移目录", settings: { outputDir: chineseOutput, pendingOutputDir: pendingOutput }, expected: pendingOutput },
      { name: "旧版有 BOM 配置", settings: { outputDir: chineseOutput }, bom: true, expected: chineseOutput },
      { name: "旧版配置迁移", legacy: { outputDir: pendingOutput, label: "保留设置" }, expected: pendingOutput },
      { name: "恢复默认目录", settings: { outputDir: chineseOutput, pendingOutputDir: "" }, expected: defaultOutput },
    ];
    for (const fixture of cases) {
      fs.rmSync(settingsPath, { force: true });
      fs.rmSync(legacyPath, { force: true });
      if (fixture.settings) {
        writeDesktopSettingsFileAtomic(settingsPath, fixture.settings);
        if (fixture.bom) fs.writeFileSync(settingsPath, "\uFEFF" + fs.readFileSync(settingsPath, "utf8"));
      }
      if (fixture.legacy) writeDesktopSettingsFileAtomic(legacyPath, fixture.legacy);
      // 连续运行两次，确认保存后再次回填不会二次转码。
      for (let attempt = 0; attempt < 2; attempt++) {
        fs.rmSync(resultPath, { force: true });
        run(exePath, []);
        assert.equal(fs.readFileSync(resultPath, "utf16le"), fixture.expected, fixture.name);
        const expectedSettings = { ...fixture.settings, ...fixture.legacy,
          pendingOutputDir: fixture.expected === defaultOutput ? "" : fixture.expected };
        assert.deepEqual(parseDesktopSettingsText(fs.readFileSync(settingsPath, "utf8")), expectedSettings, fixture.name);
      }
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("uninstall helper reads UTF-8 paths and preserves default and unrelated directories", {
  skip: process.platform !== "win32",
}, () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-uninstall-unicode-"));
  try {
    const defaultOutput = path.join(root, "默认输出");
    const customOutput = path.join(root, "聊天记录 & 备份📁");
    const unrelatedOutput = path.join(root, "其他文件");
    const pathFile = path.join(root, "output-location.path");
    for (const directory of [defaultOutput, customOutput, unrelatedOutput]) {
      // 先验证实际删除目标始终位于本测试的临时目录中。
      assert.ok(path.resolve(directory).startsWith(path.resolve(root) + path.sep));
      fs.mkdirSync(directory);
      fs.writeFileSync(path.join(directory, "keep.txt"), "测试文件", "utf8");
    }
    for (const target of [defaultOutput, customOutput]) {
      fs.writeFileSync(pathFile, target + "\n", "utf8");
      run(powershellPath, ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", helperPath,
        "-Mode", "DeleteCustom", "-DefaultOutputPath", defaultOutput, "-PathFile", pathFile]);
      assert.equal(fs.existsSync(target), target === defaultOutput);
      assert.equal(fs.readFileSync(path.join(defaultOutput, "keep.txt"), "utf8"), "测试文件");
      assert.equal(fs.readFileSync(path.join(unrelatedOutput, "keep.txt"), "utf8"), "测试文件");
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
