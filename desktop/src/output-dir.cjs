const fs = require("fs");
const path = require("path");

const SENTINEL_NAMES = [
  "account_keys.json",
  "runtime_settings.json",
  "message_edits.db",
  "databases",
  "exports",
  "logs",
];

function normalizeDirectoryPath(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const expanded = text.replace(/^~(?=$|[\\/])/, process.env.USERPROFILE || process.env.HOME || "~");
  if (!path.isAbsolute(expanded)) {
    throw new Error("output 目录必须使用绝对路径");
  }
  return path.resolve(expanded);
}

function getDefaultOutputDirPath(dataDir) {
  const base = normalizeDirectoryPath(dataDir);
  if (!base) throw new Error("无法定位数据目录");
  return path.join(base, "output");
}

function getEffectiveOutputDirPath({ dataDir, envOutputDir, settingsOutputDir }) {
  const envPath = normalizeDirectoryPath(envOutputDir || "");
  if (envPath) return envPath;

  const settingsPath = normalizeDirectoryPath(settingsOutputDir || "");
  if (settingsPath) return settingsPath;

  return getDefaultOutputDirPath(dataDir);
}

function hasDirectoryContents(dirPath) {
  try {
    return fs.readdirSync(dirPath).length > 0;
  } catch (err) {
    if (err && err.code === "ENOENT") return false;
    throw err;
  }
}

function pathExists(dirPath) {
  try {
    fs.accessSync(dirPath);
    return true;
  } catch {
    return false;
  }
}

function isDirectory(dirPath) {
  try {
    return fs.statSync(dirPath).isDirectory();
  } catch {
    return false;
  }
}

function isPathInside(parentPath, candidatePath) {
  const parent = path.resolve(parentPath);
  const candidate = path.resolve(candidatePath);
  if (parent === candidate) return false;
  const relative = path.relative(parent, candidate);
  return !!relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function collectSentinels(sourceDir) {
  const sentinels = [];
  for (const name of SENTINEL_NAMES) {
    const sourcePath = path.join(sourceDir, name);
    if (!pathExists(sourcePath)) continue;
    sentinels.push({
      name,
      isDir: isDirectory(sourcePath),
      size: !isDirectory(sourcePath) ? fs.statSync(sourcePath).size : null,
    });
  }
  return sentinels;
}

function verifyCopiedOutputTree(sourceDir, copiedDir) {
  const sentinels = collectSentinels(sourceDir);
  for (const item of sentinels) {
    const copiedPath = path.join(copiedDir, item.name);
    if (!pathExists(copiedPath)) {
      throw new Error(`迁移校验失败：缺少 ${item.name}`);
    }
    if (item.isDir) {
      if (!isDirectory(copiedPath)) {
        throw new Error(`迁移校验失败：${item.name} 不是目录`);
      }
      continue;
    }
    const copiedStat = fs.statSync(copiedPath);
    if (copiedStat.size !== item.size) {
      throw new Error(`迁移校验失败：${item.name} 大小不一致`);
    }
  }
}

function makeTimestamp(now = new Date()) {
  const parts = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ];
  return parts.join("");
}

function makeUniqueSiblingPath(basePath, suffix, now = new Date()) {
  const stamp = makeTimestamp(now);
  let attempt = 0;
  while (true) {
    const candidate = `${basePath}.${suffix}-${stamp}${attempt ? `-${attempt}` : ""}`;
    if (!pathExists(candidate)) return candidate;
    attempt += 1;
  }
}

function ensureTargetIsUsable(targetDir) {
  if (!pathExists(targetDir)) return;
  if (!isDirectory(targetDir)) {
    throw new Error("目标 output 路径已存在且不是目录");
  }
  if (hasDirectoryContents(targetDir)) {
    throw new Error("目标 output 目录已有内容，请先清空后再重试");
  }
}

function migrateOutputDirectory({ currentDir, nextDir, now = new Date() }) {
  const currentPath = normalizeDirectoryPath(currentDir);
  const targetPath = normalizeDirectoryPath(nextDir);
  if (!currentPath || !targetPath) {
    throw new Error("output 路径不能为空");
  }
  if (currentPath === targetPath) {
    return {
      changed: false,
      currentDir: currentPath,
      targetDir: targetPath,
      sourceWasEmpty: !hasDirectoryContents(currentPath),
      backupDir: "",
    };
  }
  if (isPathInside(currentPath, targetPath) || isPathInside(targetPath, currentPath)) {
    throw new Error("新旧 output 路径不能互相包含");
  }

  ensureTargetIsUsable(targetPath);

  const sourceExists = pathExists(currentPath);
  if (sourceExists && !isDirectory(currentPath)) {
    throw new Error("当前 output 路径不是目录");
  }
  const sourceWasEmpty = !sourceExists || !hasDirectoryContents(currentPath);
  if (sourceWasEmpty) {
    fs.mkdirSync(targetPath, { recursive: true });
    return {
      changed: true,
      currentDir: currentPath,
      targetDir: targetPath,
      sourceWasEmpty: true,
      backupDir: "",
    };
  }

  const tempTarget = makeUniqueSiblingPath(targetPath, "migrating", now);
  const backupDir = makeUniqueSiblingPath(currentPath, "backup", now);

  fs.cpSync(currentPath, tempTarget, {
    recursive: true,
    force: false,
    errorOnExist: true,
    preserveTimestamps: true,
  });

  try {
    verifyCopiedOutputTree(currentPath, tempTarget);
    if (pathExists(targetPath)) {
      fs.rmSync(targetPath, { recursive: true, force: true });
    }

    fs.renameSync(currentPath, backupDir);
    try {
      fs.renameSync(tempTarget, targetPath);
    } catch (err) {
      try {
        if (!pathExists(currentPath) && pathExists(backupDir)) {
          fs.renameSync(backupDir, currentPath);
        }
      } catch {}
      throw err;
    }
  } catch (err) {
    try {
      if (pathExists(tempTarget)) {
        fs.rmSync(tempTarget, { recursive: true, force: true });
      }
    } catch {}
    throw err;
  }

  return {
    changed: true,
    currentDir: currentPath,
    targetDir: targetPath,
    sourceWasEmpty: false,
    backupDir,
  };
}

function rollbackOutputDirectoryChange({ previousDir, currentDir, backupDir, sourceWasEmpty }) {
  const previousPath = normalizeDirectoryPath(previousDir);
  const currentPath = normalizeDirectoryPath(currentDir);

  try {
    if (currentPath && pathExists(currentPath)) {
      fs.rmSync(currentPath, { recursive: true, force: true });
    }
  } catch {}

  if (sourceWasEmpty) {
    return;
  }

  const backupPath = normalizeDirectoryPath(backupDir);
  if (!backupPath || !pathExists(backupPath)) return;

  try {
    if (!pathExists(previousPath)) {
      fs.renameSync(backupPath, previousPath);
    }
  } catch {}
}

module.exports = {
  getDefaultOutputDirPath,
  getEffectiveOutputDirPath,
  hasDirectoryContents,
  migrateOutputDirectory,
  normalizeDirectoryPath,
  rollbackOutputDirectoryChange,
};
