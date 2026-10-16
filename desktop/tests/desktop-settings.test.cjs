const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  parseDesktopSettingsText,
  writeDesktopSettingsFileAtomic,
} = require("../src/desktop-settings.cjs");

test("parseDesktopSettingsText accepts installer JSON with a UTF-8 BOM", () => {
  assert.deepEqual(parseDesktopSettingsText('\uFEFF{"pendingOutputDir":"E:\\\\chat\\\\out"}'), {
    pendingOutputDir: "E:\\chat\\out",
  });
});

test("parseDesktopSettingsText normalizes non-object JSON to an empty settings object", () => {
  assert.deepEqual(parseDesktopSettingsText("null"), {});
  assert.deepEqual(parseDesktopSettingsText("[]"), {});
});

test("writeDesktopSettingsFileAtomic replaces settings without leaving a temp file", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-settings-"));
  const settingsPath = path.join(root, "desktop-settings.json");

  try {
    fs.writeFileSync(settingsPath, '{"outputDir":"old"}', "utf8");
    writeDesktopSettingsFileAtomic(settingsPath, {
      outputDir: "E:\\聊天记录\\out",
      pendingOutputDir: null,
    });

    assert.deepEqual(JSON.parse(fs.readFileSync(settingsPath, "utf8")), {
      outputDir: "E:\\聊天记录\\out",
      pendingOutputDir: null,
    });
    assert.deepEqual(fs.readdirSync(root), ["desktop-settings.json"]);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("writeDesktopSettingsFileAtomic preserves the old file when replacement fails", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-settings-"));
  const settingsPath = path.join(root, "desktop-settings.json");
  const originalRenameSync = fs.renameSync;

  try {
    fs.writeFileSync(settingsPath, '{"outputDir":"old"}', "utf8");
    fs.renameSync = (sourcePath, targetPath) => {
      if (path.resolve(targetPath) === path.resolve(settingsPath)) {
        const error = new Error("simulated replacement failure");
        error.code = "EACCES";
        throw error;
      }
      return originalRenameSync(sourcePath, targetPath);
    };

    assert.throws(
      () => writeDesktopSettingsFileAtomic(settingsPath, { outputDir: "new" }),
      /simulated replacement failure/
    );
    assert.deepEqual(JSON.parse(fs.readFileSync(settingsPath, "utf8")), { outputDir: "old" });
    assert.deepEqual(fs.readdirSync(root), ["desktop-settings.json"]);
  } finally {
    fs.renameSync = originalRenameSync;
    fs.rmSync(root, { recursive: true, force: true });
  }
});
