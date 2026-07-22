const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  cleanupOutputDirectoryBackup,
  getDefaultOutputDirPath,
  getEffectiveOutputDirPath,
  isPathInsideOrEqual,
  isPathLexicallyInsideOrEqual,
  migrateOutputDirectory,
  normalizeDirectoryPath,
  pathsReferToSameLocation,
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

test("migrateOutputDirectory switches empty source to a new directory", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(currentDir, { recursive: true });
    const result = await migrateOutputDirectory({ currentDir, nextDir });
    assert.equal(result.changed, true);
    assert.equal(result.sourceWasEmpty, true);
    assert.equal(result.backupDir, "");
    assert.ok(fs.existsSync(nextDir));
    assert.equal(fs.existsSync(currentDir), true);
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory blocks non-empty targets", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "logs"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "runtime_settings.json"), "{}");
    fs.mkdirSync(nextDir, { recursive: true });
    fs.writeFileSync(path.join(nextDir, "existing.txt"), "occupied");

    await assert.rejects(
      migrateOutputDirectory({ currentDir, nextDir }),
      /已有内容/
    );
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory blocks invalid current paths", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.writeFileSync(currentDir, "not-a-directory");
    await assert.rejects(
      migrateOutputDirectory({ currentDir, nextDir }),
      /不是目录/
    );
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory copies data and leaves the old directory as a backup", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "databases", "wxid_test"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "runtime_settings.json"), "{\"backend_port\":10392}");
    fs.writeFileSync(path.join(currentDir, "databases", "wxid_test", "session.db"), "session");
    fs.writeFileSync(path.join(currentDir, "databases", "wxid_test", "contact.db"), "contact");

    const progressEvents = [];
    const result = await migrateOutputDirectory({
      currentDir,
      nextDir,
      now: new Date("2026-03-30T08:00:00Z"),
      onProgress: (progress) => progressEvents.push(progress),
    });
    assert.equal(result.changed, true);
    assert.equal(result.sourceWasEmpty, false);
    assert.match(path.basename(result.backupDir), /^current-output\.backup-\d{14}$/);
    assert.ok(fs.existsSync(nextDir));
    assert.ok(fs.existsSync(path.join(nextDir, "runtime_settings.json")));
    assert.ok(fs.existsSync(path.join(nextDir, "databases", "wxid_test", "session.db")));
    assert.ok(fs.existsSync(result.backupDir));
    assert.equal(fs.existsSync(currentDir), false);
    assert.ok(progressEvents.some((event) => event.stage === "scanning"));
    assert.ok(progressEvents.some((event) => event.stage === "copying" && event.percent > 0));
    assert.ok(progressEvents.some((event) => event.stage === "complete" && event.percent === 100));
  } finally {
    cleanupDir(root);
  }
});

test("rollbackOutputDirectoryChange restores the previous directory", async () => {
  const root = makeTempDir();
  const previousDir = path.join(root, "current-output");
  const currentDir = path.join(root, "custom-output");
  const backupDir = path.join(root, "current-output.backup-20260330080100");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "restored");
    fs.mkdirSync(path.join(backupDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(backupDir, "databases", "session.db"), "restored");

    await rollbackOutputDirectoryChange({
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

test("isPathLexicallyInsideOrEqual detects install-directory targets without following junctions", () => {
  const root = path.join(path.parse(process.cwd()).root, "Apps", "WeChatDataAnalysis");
  assert.equal(isPathLexicallyInsideOrEqual(root, root), true);
  assert.equal(isPathLexicallyInsideOrEqual(root, path.join(root, "output")), true);
  assert.equal(
    isPathLexicallyInsideOrEqual(root, path.join(path.parse(process.cwd()).root, "ChatData", "output")),
    false
  );
});

test("progress callback failures do not interrupt a committed migration", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "session");

    const result = await migrateOutputDirectory({
      currentDir,
      nextDir,
      onProgress() {
        throw new Error("renderer closed");
      },
    });

    assert.equal(result.changed, true);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "session");
    assert.ok(fs.existsSync(result.backupDir));
  } finally {
    cleanupDir(root);
  }
});

test("rollbackOutputDirectoryChange preserves the new directory when the backup is missing", async () => {
  const root = makeTempDir();
  const previousDir = path.join(root, "current-output");
  const currentDir = path.join(root, "custom-output");
  const missingBackupDir = path.join(root, "current-output.backup-missing");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "new-copy");

    await assert.rejects(
      rollbackOutputDirectoryChange({
        previousDir,
        currentDir,
        backupDir: missingBackupDir,
        sourceWasEmpty: false,
      }),
      /备份不存在/
    );

    assert.equal(fs.readFileSync(path.join(currentDir, "databases", "session.db"), "utf8"), "new-copy");
    assert.equal(fs.existsSync(previousDir), false);
  } finally {
    cleanupDir(root);
  }
});

test("rollbackOutputDirectoryChange preserves the new directory when the backup is corrupt", async () => {
  const root = makeTempDir();
  const previousDir = path.join(root, "current-output");
  const currentDir = path.join(root, "custom-output");
  const backupDir = path.join(root, "current-output.backup-corrupt");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.mkdirSync(path.join(backupDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "GOOD-DATA");
    fs.writeFileSync(path.join(backupDir, "databases", "session.db"), "BAD--DATA");

    await assert.rejects(
      rollbackOutputDirectoryChange({
        previousDir,
        currentDir,
        backupDir,
        sourceWasEmpty: false,
      }),
      /备份校验失败/
    );

    assert.equal(fs.readFileSync(path.join(currentDir, "databases", "session.db"), "utf8"), "GOOD-DATA");
    assert.equal(fs.readFileSync(path.join(backupDir, "databases", "session.db"), "utf8"), "BAD--DATA");
    assert.equal(fs.existsSync(previousDir), false);
  } finally {
    cleanupDir(root);
  }
});

test("rollbackOutputDirectoryChange preserves unexpected data for an empty source", async () => {
  const root = makeTempDir();
  const previousDir = path.join(root, "current-output");
  const currentDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(currentDir, { recursive: true });
    fs.writeFileSync(path.join(currentDir, "created-after-migration.txt"), "keep-me");

    await assert.rejects(
      rollbackOutputDirectoryChange({
        previousDir,
        currentDir,
        backupDir: "",
        sourceWasEmpty: true,
      }),
      /出现了数据/
    );

    assert.equal(fs.readFileSync(path.join(currentDir, "created-after-migration.txt"), "utf8"), "keep-me");
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory rejects a same-size target with different contents", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.mkdirSync(path.join(nextDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "NEW-DATA");
    fs.writeFileSync(path.join(nextDir, "databases", "session.db"), "OLD-DATA");

    await assert.rejects(migrateOutputDirectory({ currentDir, nextDir }), /已有内容/);
    assert.equal(fs.readFileSync(path.join(currentDir, "databases", "session.db"), "utf8"), "NEW-DATA");
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "OLD-DATA");
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory rejects a same-size source change after copying", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  let changedSource = false;

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    const sourceFile = path.join(currentDir, "databases", "session.db");
    fs.writeFileSync(sourceFile, "OLD-DATA");

    await assert.rejects(
      migrateOutputDirectory({
        currentDir,
        nextDir,
        onProgress(progress) {
          if (!changedSource && progress.stage === "verifying") {
            changedSource = true;
            fs.writeFileSync(sourceFile, "NEW-DATA");
          }
        },
      }),
      /内容不一致/
    );

    assert.equal(changedSource, true);
    assert.equal(fs.readFileSync(sourceFile, "utf8"), "NEW-DATA");
    assert.equal(fs.existsSync(nextDir), false);
  } finally {
    cleanupDir(root);
  }
});

test("pathsReferToSameLocation resolves directory junction aliases", (t) => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const aliasDir = path.join(root, "output-alias");

  try {
    fs.mkdirSync(currentDir, { recursive: true });
    try {
      fs.symlinkSync(currentDir, aliasDir, process.platform === "win32" ? "junction" : "dir");
    } catch (err) {
      if (["EACCES", "EPERM", "ENOSYS"].includes(String(err?.code || ""))) {
        t.skip(`directory links unavailable: ${err.code}`);
        return;
      }
      throw err;
    }

    assert.equal(pathsReferToSameLocation(currentDir, aliasDir), true);
    assert.equal(isPathInsideOrEqual(currentDir, aliasDir), true);
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory migrates logs and arbitrary resource files", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "聊天记录", "out");

  try {
    fs.mkdirSync(path.join(currentDir, "logs", "2026", "07", "21"), { recursive: true });
    fs.mkdirSync(path.join(currentDir, "databases", "wxid_test", "resource", "image"), {
      recursive: true,
    });
    fs.writeFileSync(path.join(currentDir, "logs", "2026", "07", "21", "21_wechat_tool.log"), "log");
    fs.writeFileSync(
      path.join(currentDir, "databases", "wxid_test", "resource", "image", "avatar.dat"),
      "resource"
    );
    fs.writeFileSync(path.join(currentDir, "future-artifact.bin"), "future");

    const result = await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(result.changed, true);
    assert.equal(
      fs.readFileSync(path.join(nextDir, "logs", "2026", "07", "21", "21_wechat_tool.log"), "utf8"),
      "log"
    );
    assert.equal(
      fs.readFileSync(
        path.join(nextDir, "databases", "wxid_test", "resource", "image", "avatar.dat"),
        "utf8"
      ),
      "resource"
    );
    assert.equal(fs.readFileSync(path.join(nextDir, "future-artifact.bin"), "utf8"), "future");
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory replaces an incomplete stale migrating directory", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  const staleDir = `${nextDir}.migrating-20260721150812`;

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "complete-data");
    fs.mkdirSync(path.join(staleDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(staleDir, "databases", "session.db"), "partial");

    await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(fs.existsSync(staleDir), false);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "complete-data");
    assert.deepEqual(
      fs.readdirSync(root).filter((name) => name.startsWith("custom-output.migrating-")),
      []
    );
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory replaces a same-size stale copy with different contents", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  const staleDir = `${nextDir}.migrating-20260721150812`;

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.mkdirSync(path.join(staleDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "NEW-DATA");
    fs.writeFileSync(path.join(staleDir, "databases", "session.db"), "OLD-DATA");

    await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(fs.existsSync(staleDir), false);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "NEW-DATA");
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory resumes a fully copied stale migrating directory", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  const staleDir = `${nextDir}.migrating-20260721150812`;

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "session");
    fs.cpSync(currentDir, staleDir, { recursive: true });

    const result = await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(result.changed, true);
    assert.equal(fs.existsSync(staleDir), false);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "session");
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory completes an interrupted target promotion", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "session");
    fs.cpSync(currentDir, nextDir, { recursive: true });

    const result = await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(result.changed, true);
    assert.equal(fs.existsSync(currentDir), false);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "session");
    assert.ok(fs.existsSync(result.backupDir));
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory restores a source backup left by an interrupted commit", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  const interruptedBackup = `${currentDir}.backup-20260721150812`;
  const interruptedTarget = `${nextDir}.migrating-20260721150812`;

  try {
    fs.mkdirSync(path.join(interruptedBackup, "databases"), { recursive: true });
    fs.writeFileSync(path.join(interruptedBackup, "databases", "session.db"), "session");
    fs.cpSync(interruptedBackup, interruptedTarget, { recursive: true });

    const result = await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(result.changed, true);
    assert.equal(fs.existsSync(interruptedBackup), false);
    assert.equal(fs.existsSync(interruptedTarget), false);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "session");
    assert.ok(fs.existsSync(result.backupDir));
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory matches the promoted target to the correct interrupted backup", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  const matchingBackup = `${currentDir}.backup-20260101000000`;
  const staleBackup = `${currentDir}.backup-20270101000000`;

  try {
    fs.mkdirSync(path.join(matchingBackup, "databases"), { recursive: true });
    fs.mkdirSync(path.join(staleBackup, "databases"), { recursive: true });
    fs.writeFileSync(path.join(matchingBackup, "databases", "session.db"), "LATEST-DATA");
    fs.writeFileSync(path.join(staleBackup, "databases", "session.db"), "STALE--DATA");
    fs.cpSync(matchingBackup, nextDir, { recursive: true });

    const result = await migrateOutputDirectory({ currentDir, nextDir });

    assert.equal(result.changed, true);
    assert.equal(fs.existsSync(matchingBackup), false);
    assert.equal(fs.existsSync(staleBackup), true);
    assert.equal(fs.readFileSync(path.join(nextDir, "databases", "session.db"), "utf8"), "LATEST-DATA");
    assert.equal(
      fs.readFileSync(path.join(result.backupDir, "databases", "session.db"), "utf8"),
      "LATEST-DATA"
    );
  } finally {
    cleanupDir(root);
  }
});

test("migrateOutputDirectory removes the promoted target when source backup fails", async () => {
  const root = makeTempDir();
  const currentDir = path.join(root, "current-output");
  const nextDir = path.join(root, "custom-output");
  const originalRenameSync = fs.renameSync;

  try {
    fs.mkdirSync(path.join(currentDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(currentDir, "databases", "session.db"), "session");
    fs.renameSync = (sourcePath, targetPath) => {
      if (path.resolve(sourcePath) === path.resolve(currentDir)) {
        const error = new Error("simulated source rename failure");
        error.code = "EIO";
        throw error;
      }
      return originalRenameSync(sourcePath, targetPath);
    };

    await assert.rejects(migrateOutputDirectory({ currentDir, nextDir }), /simulated source rename failure/);

    assert.equal(fs.existsSync(currentDir), true);
    assert.equal(fs.existsSync(nextDir), false);
    assert.deepEqual(
      fs.readdirSync(root).filter((name) => name.startsWith("custom-output.migrating-")),
      []
    );
  } finally {
    fs.renameSync = originalRenameSync;
    cleanupDir(root);
  }
});

test("cleanupOutputDirectoryBackup removes a completed migration backup directory", () => {
  const root = makeTempDir();
  const backupDir = path.join(root, "current-output.backup-20260330080100");

  try {
    fs.mkdirSync(path.join(backupDir, "databases"), { recursive: true });
    fs.writeFileSync(path.join(backupDir, "databases", "session.db"), "restored");

    assert.equal(cleanupOutputDirectoryBackup(backupDir), true);
    assert.equal(fs.existsSync(backupDir), false);
  } finally {
    cleanupDir(root);
  }
});
