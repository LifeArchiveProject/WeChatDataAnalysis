const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { pipeline } = require("stream/promises");

const SENTINEL_NAMES = [
  "account_keys.json",
  "runtime_settings.json",
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

const RETRYABLE_FILESYSTEM_ERROR_CODES = new Set([
  "EACCES",
  "EBUSY",
  "EMFILE",
  "ENFILE",
  "ENOTEMPTY",
  "EPERM",
]);
const FILESYSTEM_RETRY_DELAYS_MS = [0, 80, 200, 500, 1_000];

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

function resolvePathForComparison(inputPath) {
  const absolutePath = path.resolve(inputPath);
  const missingSegments = [];
  let existingPath = absolutePath;

  while (true) {
    try {
      const realPath = fs.realpathSync.native
        ? fs.realpathSync.native(existingPath)
        : fs.realpathSync(existingPath);
      return path.resolve(realPath, ...missingSegments);
    } catch (err) {
      if (err?.code !== "ENOENT" && err?.code !== "ENOTDIR") break;
      const parentPath = path.dirname(existingPath);
      if (parentPath === existingPath) break;
      missingSegments.unshift(path.basename(existingPath));
      existingPath = parentPath;
    }
  }

  return absolutePath;
}

function pathsReferToSameLocation(leftPath, rightPath) {
  const left = resolvePathForComparison(leftPath);
  const right = resolvePathForComparison(rightPath);
  if (process.platform === "win32") {
    return left.toLowerCase() === right.toLowerCase();
  }
  return left === right;
}

function isPathLexicallyInsideOrEqual(parentPath, candidatePath) {
  const parent = path.resolve(parentPath);
  const candidate = path.resolve(candidatePath);
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function isDirectory(dirPath) {
  try {
    return fs.statSync(dirPath).isDirectory();
  } catch {
    return false;
  }
}

function isPathInside(parentPath, candidatePath) {
  const parent = resolvePathForComparison(parentPath);
  const candidate = resolvePathForComparison(candidatePath);
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

function isPathInsideOrEqual(parentPath, candidatePath) {
  return (
    pathsReferToSameLocation(parentPath, candidatePath) ||
    isPathInside(parentPath, candidatePath)
  );
}

function compareManifestPaths(leftEntries, rightEntries, kind) {
  if (leftEntries.length !== rightEntries.length) {
    throw new Error(`迁移校验失败：${kind}数量不一致`);
  }

  for (let i = 0; i < leftEntries.length; i += 1) {
    const left = leftEntries[i];
    const right = rightEntries[i];
    if (left.relativePath !== right.relativePath) {
      throw new Error(`迁移校验失败：${kind}列表不一致`);
    }
    if (kind.includes("文件") && left.size !== right.size) {
      throw new Error(`迁移校验失败：${left.relativePath} 大小不一致`);
    }
  }
}

function hashFileSha256(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(filePath);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

async function verifyCopiedOutputTree(sourceDir, copiedDir, sourceManifest = null) {
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

  const expected = sourceManifest || collectCopyManifest(sourceDir);
  const currentSource = collectCopyManifest(sourceDir);
  const actual = collectCopyManifest(copiedDir);
  compareManifestPaths(expected.directories, currentSource.directories, "源目录");
  compareManifestPaths(expected.files, currentSource.files, "源文件");
  compareManifestPaths(currentSource.directories, actual.directories, "目录");
  compareManifestPaths(currentSource.files, actual.files, "文件");

  for (const fileEntry of currentSource.files) {
    const sourcePath = path.join(sourceDir, fileEntry.relativePath);
    const copiedPath = path.join(copiedDir, fileEntry.relativePath);
    // Hash the source again after copying. The backend is normally stopped, but
    // another process may still update a log/database between scan and verify.
    // Reusing the copy-time hash would certify the stale copy instead.
    const sourceHash = await hashFileSha256(sourcePath);
    const copiedHash = await hashFileSha256(copiedPath);
    if (sourceHash !== copiedHash) {
      throw new Error(`迁移校验失败：${fileEntry.relativePath} 内容不一致`);
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

function listSiblingTransactionPaths(basePath, suffix) {
  const parentDir = path.dirname(basePath);
  const prefix = `${path.basename(basePath)}.${suffix}-`;
  let entries = [];
  try {
    entries = fs.readdirSync(parentDir, { withFileTypes: true });
  } catch (err) {
    if (err && err.code === "ENOENT") return [];
    throw err;
  }

  return entries
    .filter((entry) => String(entry?.name || "").startsWith(prefix))
    .map((entry) => path.join(parentDir, entry.name))
    .sort((a, b) => b.localeCompare(a));
}

function isRetryableFilesystemError(err) {
  return RETRYABLE_FILESYSTEM_ERROR_CODES.has(String(err?.code || "").toUpperCase());
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function retryFilesystemOperation(operation) {
  let lastError = null;
  for (let attempt = 0; attempt < FILESYSTEM_RETRY_DELAYS_MS.length; attempt += 1) {
    const delayMs = FILESYSTEM_RETRY_DELAYS_MS[attempt];
    if (delayMs > 0) await sleep(delayMs);
    try {
      return operation();
    } catch (err) {
      lastError = err;
      if (!isRetryableFilesystemError(err) || attempt === FILESYSTEM_RETRY_DELAYS_MS.length - 1) {
        throw err;
      }
    }
  }
  throw lastError || new Error("文件系统操作失败");
}

async function removePathWithRetry(targetPath) {
  if (!pathExists(targetPath)) return false;
  await retryFilesystemOperation(() => {
    fs.rmSync(targetPath, {
      recursive: true,
      force: true,
      maxRetries: 2,
      retryDelay: 100,
    });
  });
  if (pathExists(targetPath)) {
    throw new Error(`无法删除目录：${targetPath}`);
  }
  return true;
}

async function renamePathWithRetry(sourcePath, targetPath) {
  await retryFilesystemOperation(() => fs.renameSync(sourcePath, targetPath));
}

function withCleanupError(originalError, cleanupError, cleanupPath) {
  const originalMessage = originalError?.message || String(originalError);
  const cleanupMessage = cleanupError?.message || String(cleanupError);
  const combined = new Error(
    `${originalMessage}；临时目录未能自动清理：${cleanupPath}（${cleanupMessage}）`
  );
  combined.code = originalError?.code || cleanupError?.code;
  combined.cause = originalError;
  return combined;
}

async function cleanupTransactionPaths(paths, keepPath = "") {
  for (const transactionPath of paths) {
    if (keepPath && pathsReferToSameLocation(transactionPath, keepPath)) continue;
    await removePathWithRetry(transactionPath);
  }
}

async function restoreInterruptedSourceDirectory(currentPath, targetPath) {
  const backups = listSiblingTransactionPaths(currentPath, "backup");
  if (pathExists(currentPath)) {
    if (!isDirectory(currentPath) || hasDirectoryContents(currentPath) || backups.length === 0) {
      return "";
    }
  }

  const usableBackups = backups.filter((backupPath) => isDirectory(backupPath));
  if (usableBackups.length === 0) return "";

  let backupToRestore = usableBackups[0];
  let matchedPromotedTarget = false;
  if (targetPath && pathExists(targetPath)) {
    if (!isDirectory(targetPath)) {
      throw new Error("检测到中断的 output 迁移，但目标路径不是目录，已保留所有备份");
    }
    if (hasDirectoryContents(targetPath)) {
      backupToRestore = "";
      for (const candidate of usableBackups) {
        try {
          await verifyCopiedOutputTree(candidate, targetPath);
          backupToRestore = candidate;
          matchedPromotedTarget = true;
          break;
        } catch {}
      }
      if (!backupToRestore) {
        throw new Error("检测到中断的 output 迁移，但没有与目标内容匹配的旧目录备份，已保留所有副本");
      }
    }
  }
  if (usableBackups.length > 1 && !matchedPromotedTarget) {
    throw new Error("检测到多个中断的旧 output 备份且无法确认最新版本，已保留所有副本");
  }

  if (pathExists(currentPath)) {
    // Older builds could recreate an empty source directory before noticing a
    // backup from an interrupted commit. Remove only that empty directory.
    await removePathWithRetry(currentPath);
  }
  await renamePathWithRetry(backupToRestore, currentPath);
  return backupToRestore;
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
  try {
    onProgress(buildProgressSnapshot(payload));
  } catch {
    // Progress reporting is observational. A renderer/MessagePort failure must
    // never turn a completed filesystem commit into an ambiguous migration.
  }
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
  if (pathsReferToSameLocation(currentPath, targetPath)) {
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

  await restoreInterruptedSourceDirectory(currentPath, targetPath);

  const sourceExists = pathExists(currentPath);
  if (sourceExists && !isDirectory(currentPath)) {
    throw new Error("当前 output 路径不是目录");
  }

  const sourceWasEmpty = !sourceExists || !hasDirectoryContents(currentPath);
  if (sourceWasEmpty) {
    ensureTargetIsUsable(targetPath);
    await cleanupTransactionPaths(listSiblingTransactionPaths(targetPath, "migrating"));
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
  const staleTargets = listSiblingTransactionPaths(targetPath, "migrating");
  let tempTarget = "";
  let targetAlreadyPromoted = false;

  if (pathExists(targetPath)) {
    if (!isDirectory(targetPath)) {
      throw new Error("目标 output 路径已存在且不是目录");
    }
    if (hasDirectoryContents(targetPath)) {
      try {
        await verifyCopiedOutputTree(currentPath, targetPath, manifest);
        targetAlreadyPromoted = true;
      } catch {
        throw new Error("目标 output 目录已有内容，请先清空后再重试");
      }
    }
  }

  if (!targetAlreadyPromoted) {
    for (const candidate of staleTargets) {
      try {
        if (!isDirectory(candidate)) continue;
        await verifyCopiedOutputTree(currentPath, candidate, manifest);
        tempTarget = candidate;
        break;
      } catch {}
    }
    await cleanupTransactionPaths(staleTargets, tempTarget);
  } else {
    await cleanupTransactionPaths(staleTargets);
  }

  if (!targetAlreadyPromoted && !tempTarget) {
    tempTarget = makeUniqueSiblingPath(targetPath, "migrating", now);
  }
  const backupDir = makeUniqueSiblingPath(currentPath, "backup", now);
  let promotedThisRun = false;

  try {
    if (!targetAlreadyPromoted && !pathExists(tempTarget)) {
      await copyOutputTree({
        sourceDir: currentPath,
        targetDir: tempTarget,
        manifest,
        onProgress,
      });
    }

    emitProgress(onProgress, {
      stage: "verifying",
      bytesTransferred: manifest.totalBytes,
      bytesTotal: manifest.totalBytes,
      itemsTransferred: manifest.totalItems,
      itemsTotal: manifest.totalItems,
    });
    if (!targetAlreadyPromoted) {
      await verifyCopiedOutputTree(currentPath, tempTarget, manifest);
    }

    emitProgress(onProgress, {
      stage: "switching",
      bytesTransferred: manifest.totalBytes,
      bytesTotal: manifest.totalBytes,
      itemsTransferred: manifest.totalItems,
      itemsTotal: manifest.totalItems,
    });
    if (!targetAlreadyPromoted) {
      if (pathExists(targetPath)) {
        await removePathWithRetry(targetPath);
      }
      await renamePathWithRetry(tempTarget, targetPath);
      promotedThisRun = true;
    }

    try {
      await renamePathWithRetry(currentPath, backupDir);
    } catch (err) {
      if (promotedThisRun && pathExists(targetPath)) {
        try {
          await removePathWithRetry(targetPath);
        } catch (cleanupErr) {
          throw withCleanupError(err, cleanupErr, targetPath);
        }
      }
      throw err;
    }
  } catch (err) {
    if (tempTarget && pathExists(tempTarget)) {
      try {
        await removePathWithRetry(tempTarget);
      } catch (cleanupErr) {
        throw withCleanupError(err, cleanupErr, tempTarget);
      }
    }
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

async function rollbackOutputDirectoryChange({ previousDir, currentDir, backupDir, sourceWasEmpty }) {
  const previousPath = normalizeDirectoryPath(previousDir);
  const currentPath = normalizeDirectoryPath(currentDir);

  if (sourceWasEmpty) {
    if (currentPath && pathExists(currentPath)) {
      if (!isDirectory(currentPath) || hasDirectoryContents(currentPath)) {
        throw new Error(`新 output 目录出现了数据，已保留该目录：${currentPath}`);
      }
      await removePathWithRetry(currentPath);
    }
    return;
  }

  const backupPath = normalizeDirectoryPath(backupDir);
  if (!backupPath || !isDirectory(backupPath)) {
    throw new Error(`旧 output 备份不存在，已保留新目录：${currentPath}`);
  }

  if (currentPath && pathExists(currentPath)) {
    if (!isDirectory(currentPath)) {
      throw new Error(`新 output 路径不是目录，已保留新路径和备份：${currentPath}`);
    }
    try {
      await verifyCopiedOutputTree(backupPath, currentPath);
    } catch (err) {
      throw new Error(
        `旧 output 备份校验失败，已保留新目录和备份：${err?.message || err}`
      );
    }
  }

  if (pathExists(previousPath)) {
    if (!isDirectory(previousPath) || hasDirectoryContents(previousPath)) {
      throw new Error(`旧 output 路径已有内容，已保留新目录和备份：${previousPath}`);
    }
    await removePathWithRetry(previousPath);
  }

  let stagedCurrentPath = "";
  if (currentPath && pathExists(currentPath)) {
    stagedCurrentPath = makeUniqueSiblingPath(currentPath, "rollback");
    await renamePathWithRetry(currentPath, stagedCurrentPath);
  }

  try {
    await renamePathWithRetry(backupPath, previousPath);
  } catch (err) {
    if (stagedCurrentPath && pathExists(stagedCurrentPath) && !pathExists(currentPath)) {
      try {
        await renamePathWithRetry(stagedCurrentPath, currentPath);
      } catch (restoreErr) {
        throw withCleanupError(err, restoreErr, stagedCurrentPath);
      }
    }
    throw err;
  }

  if (stagedCurrentPath && pathExists(stagedCurrentPath)) {
    try {
      await removePathWithRetry(stagedCurrentPath);
    } catch (cleanupErr) {
      const warning = new Error(
        `旧 output 已恢复，但新目录副本未能自动清理：${stagedCurrentPath}（${cleanupErr?.message || cleanupErr}）`
      );
      warning.code = cleanupErr?.code;
      warning.retainedPath = stagedCurrentPath;
      throw warning;
    }
  }
}

function cleanupOutputDirectoryBackup(backupDir) {
  const backupPath = normalizeDirectoryPath(backupDir);
  if (!backupPath || !pathExists(backupPath)) return false;
  fs.rmSync(backupPath, {
    recursive: true,
    force: true,
    maxRetries: 5,
    retryDelay: 100,
  });
  return !pathExists(backupPath);
}

module.exports = {
  cleanupOutputDirectoryBackup,
  getDefaultOutputDirPath,
  getEffectiveOutputDirPath,
  hasDirectoryContents,
  isPathInsideOrEqual,
  migrateOutputDirectory,
  normalizeDirectoryPath,
  isPathLexicallyInsideOrEqual,
  pathsReferToSameLocation,
  rollbackOutputDirectoryChange,
};
