const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  getDefaultOutputDirPath,
  getEffectiveOutputDirPath,
  migrateOutputDirectory,
  normalizeDirectoryPath,
  rollbackOutputDirectoryChange,
} = require("../src/output-dir.cjs");

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "wda-output-"));
}

function cleanupDir(dirPath) {
  try {
    fs.rmSync(dirPath, { recursive: true, force: true });
  } catch {}
}

test("normalizeDirectoryPath requires absolute paths", () => {
  assert.throws(() => normalizeDirectoryPath("relative/path"), /绝对路径/);
});

test("getEffectiveOutputDirPath prefers env, then settings, then default", () => {
  const root = makeTempDir();
  const envDir = path.join(root, "env-output");
  const settingsDir = path.join(root, "settings-output");
  const defaultDir = path.join(root, "data", "output");

  try {
    assert.equal(
      getEffectiveOutputDirPath({
        dataDir: path.join(root, "data"),
        envOutputDir: envDir,
        settingsOutputDir: settingsDir,
      }),
      path.resolve(envDir)
    );
    assert.equal(
      getEffectiveOutputDirPath({
        dataDir: path.join(root, "data"),
        envOutputDir: "",
        settingsOutputDir: settingsDir,
      }),
      path.resolve(settingsDir)
    );
    assert.equal(getDefaultOutputDirPath(path.join(root, "data")), path.resolve(defaultDir));
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory switches empty source to a new directory", () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(currentDir, { recursive: true });
    const result = migrateOutputDirectory({ currentDir, nextDir });
    assert.equal(result.changed, true);
    assert.equal(result.sourceWasEmpty, true);
    assert.equal(result.backupDir, "");
    assert.ok(fs.existsSync(nextDir));
    assert.equal(fs.existsSync(currentDir), true);
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory blocks non-empty targets", () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "logs"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "runtime_settings.json"), "{}");
    fs.mkdirSync(nextDir, { recursive: true });
    fs.writeFileSync(path.join(nextDir, "existing.txt"), "occupied");

    assert.throws(
      () => migrateOutputDirectory({ currentDir, nextDir }),
      /已有内容/
    );
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory blocks invalid current paths", () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.writeFileSync(currentDir, "not-a-directory");
    assert.throws(
      () => migrateOutputDirectory({ currentDir, nextDir }),
      /不是目录/
    );
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory copies data and leaves the old directory as a backup", () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "databases", "wxid_test"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "runtime_settings.json"), "{\"backend_port\":10392}");
    fs.writeFileSync(path.join(currentDir, "databases", "wxid_test", "session.db"), "session");
    fs.writeFileSync(path.join(currentDir, "databases", "wxid_test", "contact.db"), "contact");

    const result = migrateOutputDirectory({ currentDir, nextDir, now: new Date("2026-03-30T08:00:00Z") });
    assert.equal(result.changed, true);
    assert.equal(result.sourceWasEmpty, false);
    assert.match(path.basename(result.backupDir), /^current-output\.backup-\d{14}$/);
    assert.ok(fs.existsSync(nextDir));
    assert.ok(fs.existsSync(path.join(nextDir, "runtime_settings.json")));
    assert.ok(fs.existsSync(path.join(nextDir, "databases", "wxid_test", "session.db")));
    assert.ok(fs.existsSync(result.backupDir));
    assert.equal(fs.existsSync(currentDir), false);
  } finally {
    cleanupDir(root);
  }
});

test("rollbackOutputDirectoryChange restores the previous directory", () => {
  const root = makeTempDir();
  const previousDir = path.join(root, "current-output");
  const currentDir = path.join(root, "custom-output");
  const backupDir = path.join(root, "current-output.backup-20260330080100");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "temp.db"), "temp");
    fs.mkdirSync(path.join(backupDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(backupDir, "databases", "session.db"), "restored");

    rollbackOutputDirectoryChange({
      previousDir,
      currentDir,
      backupDir,
      sourceWasEmpty: false,
    });

    assert.equal(fs.existsSync(currentDir), false);
    assert.ok(fs.existsSync(path.join(previousDir, "databases", "session.db")));
    assert.equal(fs.existsSync(backupDir), false);
  } finally {
    cleanupDir(root);
  }
});
