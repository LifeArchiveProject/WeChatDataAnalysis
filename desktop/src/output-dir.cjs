const fs = require("fs");
const path = require("path");
const { pipeline } = require("stream/promises");

const SENTINEL_NAMES = [
  "account_keys.json",
  "runtime_settings.json",
  "message_edits.db",
  "databases",
  "exports",
  "logs",
];

const PROGRESS_STAGE_MESSAGES = {
  preparing: "正在准备迁移 output 目录",
  scanning: "正在扫描 output 目录",
  copying: "正在复制 output 数据",
  verifying: "正在校验已复制的数据",
  switching: "正在切换 output 目录",
  "rolling-back": "迁移失败，正在回滚 output 目录",
  restarting: "正在重启后端并应用新的 output 目录",
  complete: "output 目录迁移完成",
};

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

function clampNonNegativeNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return n;
}

function computeProgressPercent(stage, bytesTransferred, bytesTotal, itemsTransferred, itemsTotal) {
  if (stage === "preparing") return 1;
  if (stage === "scanning") return 2;
  if (stage === "verifying") return 96;
  if (stage === "switching") return 99;
  if (stage === "complete") return 100;

  if (stage === "copying") {
    const ratio =
      bytesTotal > 0
        ? Math.min(1, bytesTransferred / bytesTotal)
        : itemsTotal > 0
          ? Math.min(1, itemsTransferred / itemsTotal)
          : 1;
    return Math.max(5, Math.min(94, Math.round(5 + ratio * 89)));
  }

  return 0;
}

function buildProgressSnapshot({
  stage = "preparing",
  bytesTransferred = 0,
  bytesTotal = 0,
  itemsTransferred = 0,
  itemsTotal = 0,
  currentFile = "",
}) {
  const normalizedStage = String(stage || "preparing");
  const safeBytesTransferred = clampNonNegativeNumber(bytesTransferred);
  const safeBytesTotal = clampNonNegativeNumber(bytesTotal);
  const safeItemsTransferred = clampNonNegativeNumber(itemsTransferred);
  const safeItemsTotal = clampNonNegativeNumber(itemsTotal);
  return {
    stage: normalizedStage,
    message: PROGRESS_STAGE_MESSAGES[normalizedStage] || "正在迁移 output 目录",
    percent: computeProgressPercent(
      normalizedStage,
      safeBytesTransferred,
      safeBytesTotal,
      safeItemsTransferred,
      safeItemsTotal
    ),
    bytesTransferred: safeBytesTransferred,
    bytesTotal: safeBytesTotal,
    itemsTransferred: safeItemsTransferred,
    itemsTotal: safeItemsTotal,
    currentFile: String(currentFile || ""),
  };
}

function emitProgress(onProgress, payload) {
  if (typeof onProgress !== "function") return;
  onProgress(buildProgressSnapshot(payload));
}

function sortDirectoryEntries(entries) {
  return entries.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
}

function depthOfRelativePath(relativePath) {
  const text = String(relativePath || "").trim();
  if (!text) return 0;
  return text.split(path.sep).length;
}

function collectCopyManifest(sourceDir) {
  const directories = [];
  const files = [];
  let totalBytes = 0;
  const stack = [""];

  while (stack.length > 0) {
    const relativeDir = stack.pop();
    const absoluteDir = relativeDir ? path.join(sourceDir, relativeDir) : sourceDir;
    const dirEntries = sortDirectoryEntries(fs.readdirSync(absoluteDir, { withFileTypes: true }));

    for (const dirent of dirEntries) {
      const relativePath = relativeDir ? path.join(relativeDir, dirent.name) : dirent.name;
      const absolutePath = path.join(sourceDir, relativePath);
      const stat = fs.lstatSync(absolutePath);

      if (dirent.isDirectory()) {
        directories.push({
          relativePath,
          mode: stat.mode,
          atime: stat.atime,
          mtime: stat.mtime,
        });
        stack.push(relativePath);
        continue;
      }

      if (dirent.isFile()) {
        files.push({
          relativePath,
          size: stat.size,
          mode: stat.mode,
          atime: stat.atime,
          mtime: stat.mtime,
        });
        totalBytes += stat.size;
        continue;
      }

      if (dirent.isSymbolicLink()) {
        throw new Error(`output 目录包含不支持的符号链接：${relativePath}`);
      }

      throw new Error(`output 目录包含不支持的文件类型：${relativePath}`);
    }
  }

  directories.sort((a, b) => depthOfRelativePath(a.relativePath) - depthOfRelativePath(b.relativePath));

  return {
    directories,
    files,
    totalBytes,
    totalItems: directories.length + files.length,
  };
}

function applyStatMetadata(targetPath, statLike) {
  try {
    if (Number.isInteger(statLike?.mode)) {
      fs.chmodSync(targetPath, statLike.mode);
    }
  } catch {}

  try {
    if (statLike?.atime && statLike?.mtime) {
      fs.utimesSync(targetPath, statLike.atime, statLike.mtime);
    }
  } catch {}
}

async function copyFileWithProgress({ sourcePath, targetPath, mode, onChunk }) {
  await fs.promises.mkdir(path.dirname(targetPath), { recursive: true });

  const readStream = fs.createReadStream(sourcePath);
  readStream.on("data", (chunk) => {
    if (typeof onChunk === "function") onChunk(chunk.length);
  });

  const writeStream = fs.createWriteStream(targetPath, {
    flags: "w",
    mode: Number.isInteger(mode) ? mode : undefined,
  });

  await pipeline(readStream, writeStream);
}

async function copyOutputTree({ sourceDir, targetDir, manifest, onProgress }) {
  fs.mkdirSync(targetDir, { recursive: true });

  let bytesTransferred = 0;
  let itemsTransferred = 0;

  emitProgress(onProgress, {
    stage: "copying",
    bytesTransferred,
    bytesTotal: manifest.totalBytes,
    itemsTransferred,
    itemsTotal: manifest.totalItems,
  });

  for (const dirEntry of manifest.directories) {
    const targetPath = path.join(targetDir, dirEntry.relativePath);
    fs.mkdirSync(targetPath, { recursive: true });
    itemsTransferred += 1;
    emitProgress(onProgress, {
      stage: "copying",
      bytesTransferred,
      bytesTotal: manifest.totalBytes,
      itemsTransferred,
      itemsTotal: manifest.totalItems,
      currentFile: dirEntry.relativePath,
    });
  }

  for (const fileEntry of manifest.files) {
    const sourcePath = path.join(sourceDir, fileEntry.relativePath);
    const targetPath = path.join(targetDir, fileEntry.relativePath);

    await copyFileWithProgress({
      sourcePath,
      targetPath,
      mode: fileEntry.mode,
      onChunk: (delta) => {
        bytesTransferred += clampNonNegativeNumber(delta);
        emitProgress(onProgress, {
          stage: "copying",
          bytesTransferred,
          bytesTotal: manifest.totalBytes,
          itemsTransferred,
          itemsTotal: manifest.totalItems,
          currentFile: fileEntry.relativePath,
        });
      },
    });

    applyStatMetadata(targetPath, fileEntry);
    itemsTransferred += 1;
    emitProgress(onProgress, {
      stage: "copying",
      bytesTransferred,
      bytesTotal: manifest.totalBytes,
      itemsTransferred,
      itemsTotal: manifest.totalItems,
      currentFile: fileEntry.relativePath,
    });
  }

  for (let i = manifest.directories.length - 1; i >= 0; i -= 1) {
    const dirEntry = manifest.directories[i];
    applyStatMetadata(path.join(targetDir, dirEntry.relativePath), dirEntry);
  }
}

async function migrateOutputDirectory({ currentDir, nextDir, now = new Date(), onProgress } = {}) {
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

  emitProgress(onProgress, { stage: "scanning" });
  ensureTargetIsUsable(targetPath);

  const sourceExists = pathExists(currentPath);
  if (sourceExists && !isDirectory(currentPath)) {
    throw new Error("当前 output 路径不是目录");
  }

  const sourceWasEmpty = !sourceExists || !hasDirectoryContents(currentPath);
  if (sourceWasEmpty) {
    emitProgress(onProgress, { stage: "switching" });
    fs.mkdirSync(targetPath, { recursive: true });
    emitProgress(onProgress, { stage: "complete", itemsTransferred: 1, itemsTotal: 1 });
    return {
      changed: true,
      currentDir: currentPath,
      targetDir: targetPath,
      sourceWasEmpty: true,
      backupDir: "",
    };
  }

  const manifest = collectCopyManifest(currentPath);
  const tempTarget = makeUniqueSiblingPath(targetPath, "migrating", now);
  const backupDir = makeUniqueSiblingPath(currentPath, "backup", now);

  try {
    await copyOutputTree({
      sourceDir: currentPath,
      targetDir: tempTarget,
      manifest,
      onProgress,
    });

    emitProgress(onProgress, {
      stage: "verifying",
      bytesTransferred: manifest.totalBytes,
      bytesTotal: manifest.totalBytes,
      itemsTransferred: manifest.totalItems,
      itemsTotal: manifest.totalItems,
    });
    verifyCopiedOutputTree(currentPath, tempTarget);

    emitProgress(onProgress, {
      stage: "switching",
      bytesTransferred: manifest.totalBytes,
      bytesTotal: manifest.totalBytes,
      itemsTransferred: manifest.totalItems,
      itemsTotal: manifest.totalItems,
    });
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

  emitProgress(onProgress, {
    stage: "complete",
    bytesTransferred: manifest.totalBytes,
    bytesTotal: manifest.totalBytes,
    itemsTransferred: manifest.totalItems,
    itemsTotal: manifest.totalItems,
  });
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

function cleanupOutputDirectoryBackup(backupDir) {
  const backupPath = normalizeDirectoryPath(backupDir);
  if (!backupPath || !pathExists(backupPath)) return false;
  fs.rmSync(backupPath, { recursive: true, force: true });
  return !pathExists(backupPath);
}

module.exports = {
  cleanupOutputDirectoryBackup,
  getDefaultOutputDirPath,
  getEffectiveOutputDirPath,
  hasDirectoryContents,
  migrateOutputDirectory,
  normalizeDirectoryPath,
  rollbackOutputDirectoryChange,
};
