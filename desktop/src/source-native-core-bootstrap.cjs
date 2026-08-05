"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const {
  resolveNativeCoreRuntimePolicy,
} = require("./native-core-runtime.cjs");
const {
  ENV_SOURCE_NATIVE_CORE_DIR,
} = require("./native-core-path.cjs");

const ENV_SOURCE_NATIVE_CORE_CACHE_DIR = "WCE_NATIVE_CORE_SOURCE_CACHE_DIR";
const ENV_MACOS_DB_KEY_BUNDLE = "WECHAT_TOOL_MACOS_DB_KEY_BUNDLE";
const ENV_INTEGRITY_NATIVE_PATH = "WCE_INTEGRITY_NATIVE_PATH";
const DEFAULT_CONFIG_PATH = path.resolve(
  __dirname,
  "..",
  "resources",
  "native-core-source-macos.json"
);
const PROFILE = "macos-source-public";
const PUBLISHER_REPOSITORY = "LifeArchiveProject/WeChatDataAnalysis";
const ASSET_NAME = "wechatdataanalysis-macos-source-runtime-arm64-v1.tar.gz";
const RUNTIME_MANIFEST_FILE = "runtime-manifest.json";
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const REVISION_PATTERN = /^[0-9a-f]{40}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const RELEASE_TAG_PATTERN = /^macos-source-runtime-[A-Za-z0-9._-]{8,96}$/;
const MAX_ARCHIVE_BYTES = 256 * 1024 * 1024;
const MAX_RUNTIME_FILE_BYTES = 192 * 1024 * 1024;

const PAYLOAD_FILES = Object.freeze(new Map([
  ["native-core/libwechatdb_client.dylib", true],
  ["native-core/wechatdb_broker", true],
  ["native-core/wechatdb_native_build.json", false],
  ["db-key/SHA256SUMS.txt", false],
  ["db-key/THIRD_PARTY_NOTICES/FRIDA-COPYING.txt", false],
  ["db-key/provenance.json", false],
  ["db-key/wda_xkey_build.json", false],
  ["db-key/wda_xkey_helper", true],
  ["db-key/wda_xkey_trust.json", false],
  ["integrity/libwce_integrity.dylib", true],
]));
const RUNTIME_FILES = new Set([...PAYLOAD_FILES.keys(), RUNTIME_MANIFEST_FILE]);
const RUNTIME_DIRECTORIES = new Set([
  "native-core",
  "db-key",
  "db-key/THIRD_PARTY_NOTICES",
  "integrity",
]);
const ARCHIVE_ENTRIES = new Map([
  ["", "directory"],
  ...[...RUNTIME_DIRECTORIES].map((name) => [name, "directory"]),
  ...[...RUNTIME_FILES].map((name) => [name, "file"]),
]);

function sha256File(file) {
  const digest = crypto.createHash("sha256");
  const handle = fs.openSync(file, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    for (;;) {
      const count = fs.readSync(handle, buffer, 0, buffer.length, null);
      if (count === 0) break;
      digest.update(buffer.subarray(0, count));
    }
  } finally {
    fs.closeSync(handle);
  }
  return digest.digest("hex");
}

function assertExactKeys(value, expected, label) {
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must be an object`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new Error(`${label} field allowlist mismatch`);
  }
  return value;
}

function readJsonObject(file, maximum = 128 * 1024) {
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch {
    throw new Error(`Missing JSON file: ${path.basename(file)}`);
  }
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`Invalid JSON file: ${path.basename(file)}`);
  }
  let value;
  try {
    value = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (err) {
    throw new Error(`Invalid JSON file ${path.basename(file)}: ${err?.message || err}`);
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`JSON root must be an object: ${path.basename(file)}`);
  }
  return value;
}

function validatePin(input) {
  const keys = [
    "schemaVersion",
    "platform",
    "architecture",
    "publisherRepository",
    "releaseTag",
    "assetName",
    "assetSha256",
    "runtimeManifestSha256",
    "expiresAtUnix",
  ];
  assertExactKeys(input, keys, "macOS public source-runtime pin");
  if (
    input.schemaVersion !== 2 ||
    input.platform !== "darwin" ||
    input.architecture !== "arm64" ||
    input.publisherRepository !== PUBLISHER_REPOSITORY ||
    !RELEASE_TAG_PATTERN.test(String(input.releaseTag || "")) ||
    input.assetName !== ASSET_NAME ||
    !SHA256_PATTERN.test(String(input.assetSha256 || "")) ||
    input.assetSha256 === "0".repeat(64) ||
    !SHA256_PATTERN.test(String(input.runtimeManifestSha256 || "")) ||
    input.runtimeManifestSha256 === "0".repeat(64) ||
    !Number.isSafeInteger(input.expiresAtUnix) ||
    input.expiresAtUnix <= 0
  ) {
    throw new Error("macOS public source-runtime pin is invalid");
  }
  return Object.freeze({ ...input });
}

function assertActivePin(pin, nowUnix) {
  if (!Number.isSafeInteger(nowUnix) || nowUnix <= 0) {
    throw new Error("Current Unix time is invalid");
  }
  if (nowUnix >= pin.expiresAtUnix) {
    throw new Error(
      "当前 WCDA 固定的 macOS 源码运行时已过期，请先拉取最新代码后再启动。"
    );
  }
}

function assertRegularFile(file, maximum = MAX_RUNTIME_FILE_BYTES) {
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch {
    throw new Error(`Missing source-runtime file: ${path.basename(file)}`);
  }
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`Invalid source-runtime file: ${path.basename(file)}`);
  }
  return stat;
}

function normalizeArchiveEntry(raw) {
  let value = String(raw || "").replace(/\r$/, "");
  if (!value || value.includes("\0") || value.includes("\\")) {
    throw new Error("Public source-runtime archive contains an invalid path");
  }
  while (value.startsWith("./")) value = value.slice(2);
  while (value.endsWith("/") && value) value = value.slice(0, -1);
  if (value === "") return "";
  if (value.startsWith("/") || /^[A-Za-z]:/.test(value)) {
    throw new Error("Public source-runtime archive contains an absolute path");
  }
  const parts = value.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error("Public source-runtime archive contains path traversal");
  }
  return parts.join("/");
}

function commandOutput(result) {
  return String(result?.stderr || result?.stdout || result?.error?.message || "")
    .trim()
    .slice(-2000);
}

function runTool(command, args, { env, label, spawnSyncImpl }) {
  const result = spawnSyncImpl(command, args, {
    encoding: "utf8",
    env,
    maxBuffer: 4 * 1024 * 1024,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  if (result?.error || result?.status !== 0) {
    const detail = commandOutput(result);
    throw new Error(`${label}失败。${detail ? `\n${detail}` : ""}`);
  }
  return result;
}

function publicDownloadEnvironment(env) {
  const clean = { ...(env || process.env) };
  for (const name of [
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GIT_ASKPASS",
    "SSH_ASKPASS",
    "GITHUB_ASKPASS",
  ]) {
    delete clean[name];
  }
  return clean;
}

function publicReleaseUrl(pin) {
  return (
    `https://github.com/${pin.publisherRepository}/releases/download/` +
    `${encodeURIComponent(pin.releaseTag)}/${encodeURIComponent(pin.assetName)}`
  );
}

function downloadPinnedRelease(archivePath, pin, { env, spawnSyncImpl }) {
  runTool(
    "/usr/bin/curl",
    [
      "--fail",
      "--location",
      "--silent",
      "--show-error",
      "--retry",
      "3",
      "--connect-timeout",
      "20",
      "--max-time",
      "600",
      "--output",
      archivePath,
      publicReleaseUrl(pin),
    ],
    {
      env: publicDownloadEnvironment(env),
      label: "下载 WCDA 公共 macOS 源码运行时",
      spawnSyncImpl,
    }
  );
  const stat = assertRegularFile(archivePath, MAX_ARCHIVE_BYTES);
  if (stat.size > MAX_ARCHIVE_BYTES || sha256File(archivePath) !== pin.assetSha256) {
    throw new Error("WCDA 公共 macOS 源码运行时的固定 SHA-256 校验失败");
  }
}

function inspectArchive(archivePath, { env, spawnSyncImpl }) {
  const toolEnv = publicDownloadEnvironment(env);
  const namesResult = runTool(
    "/usr/bin/tar",
    ["-tzf", archivePath],
    { env: toolEnv, label: "读取公共源码运行时归档目录", spawnSyncImpl }
  );
  const detailResult = runTool(
    "/usr/bin/tar",
    ["-tvzf", archivePath],
    { env: toolEnv, label: "读取公共源码运行时归档类型", spawnSyncImpl }
  );
  const names = String(namesResult.stdout || "").split(/\r?\n/).filter(Boolean);
  const details = String(detailResult.stdout || "").split(/\r?\n/).filter(Boolean);
  if (names.length !== details.length || names.length !== ARCHIVE_ENTRIES.size) {
    throw new Error("Public source-runtime archive entry count mismatch");
  }
  const actual = new Map();
  for (let index = 0; index < names.length; index += 1) {
    const name = normalizeArchiveEntry(names[index]);
    if (actual.has(name)) {
      throw new Error("Public source-runtime archive contains duplicate paths");
    }
    const typeMarker = String(details[index] || "").trimStart().charAt(0);
    const type = typeMarker === "d" ? "directory" : typeMarker === "-" ? "file" : "unsafe";
    actual.set(name, type);
  }
  for (const [name, expectedType] of ARCHIVE_ENTRIES) {
    if (actual.get(name) !== expectedType) {
      throw new Error(`Public source-runtime archive allowlist mismatch: ${name || "."}`);
    }
  }
}

function extractArchive(archivePath, destination, { env, spawnSyncImpl }) {
  inspectArchive(archivePath, { env, spawnSyncImpl });
  runTool(
    "/usr/bin/tar",
    ["-xzf", archivePath, "-C", destination],
    {
      env: publicDownloadEnvironment(env),
      label: "解压 WCDA 公共 macOS 源码运行时",
      spawnSyncImpl,
    }
  );
}

function walkRuntimeDirectory(root) {
  const files = new Set();
  const directories = new Set();
  function visit(current, relative) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const childRelative = relative ? `${relative}/${entry.name}` : entry.name;
      const child = path.join(current, entry.name);
      const stat = fs.lstatSync(child);
      if (stat.isSymbolicLink()) {
        throw new Error(`Source-runtime entry must not be a symbolic link: ${childRelative}`);
      }
      if (stat.isDirectory()) {
        directories.add(childRelative);
        visit(child, childRelative);
      } else if (stat.isFile()) {
        files.add(childRelative);
      } else {
        throw new Error(`Source-runtime entry type is unsafe: ${childRelative}`);
      }
    }
  }
  visit(root, "");
  return { directories, files };
}

function assertExactSet(actual, expected, label) {
  if (actual.size !== expected.size || [...expected].some((name) => !actual.has(name))) {
    throw new Error(`${label} allowlist mismatch`);
  }
}

function validateComponent(component, expected, runtimeExpiry) {
  assertExactKeys(
    component,
    ["artifactName", "buildId", "sourceRevision", "producerRunId", "expiresAtUnix", "path"],
    `${expected.label} component`
  );
  if (
    component.artifactName !== expected.artifactName ||
    component.path !== expected.path ||
    !BUILD_ID_PATTERN.test(String(component.buildId || "")) ||
    !REVISION_PATTERN.test(String(component.sourceRevision || "")) ||
    !Number.isSafeInteger(component.producerRunId) ||
    component.producerRunId <= 0 ||
    !Number.isSafeInteger(component.expiresAtUnix) ||
    component.expiresAtUnix < runtimeExpiry
  ) {
    throw new Error(`${expected.label} component coordinates are invalid`);
  }
}

function validateRuntimeManifest(manifest, pin, nowUnix) {
  assertExactKeys(
    manifest,
    [
      "schemaVersion",
      "profile",
      "platform",
      "architecture",
      "releaseTag",
      "createdAtUnix",
      "expiresAtUnix",
      "components",
      "files",
    ],
    "source-runtime manifest"
  );
  if (
    manifest.schemaVersion !== 1 ||
    manifest.profile !== PROFILE ||
    manifest.platform !== "darwin" ||
    manifest.architecture !== "arm64" ||
    manifest.releaseTag !== pin.releaseTag ||
    !Number.isSafeInteger(manifest.createdAtUnix) ||
    manifest.createdAtUnix <= 0 ||
    manifest.createdAtUnix > nowUnix + 300 ||
    manifest.expiresAtUnix !== pin.expiresAtUnix ||
    nowUnix >= manifest.expiresAtUnix
  ) {
    throw new Error("Source-runtime manifest identity or validity window mismatch");
  }
  const components = assertExactKeys(
    manifest.components,
    ["nativeCore", "databaseKey", "exportIntegrity"],
    "source-runtime components"
  );
  validateComponent(
    components.nativeCore,
    {
      label: "native-core",
      artifactName: "wechatdb-native-macos-arm64-source-public",
      path: "native-core",
    },
    manifest.expiresAtUnix
  );
  validateComponent(
    components.databaseKey,
    {
      label: "database-key",
      artifactName: "wda-xkey-macos-universal-source-public",
      path: "db-key",
    },
    manifest.expiresAtUnix
  );
  validateComponent(
    components.exportIntegrity,
    {
      label: "export-integrity",
      artifactName: "wce-integrity-macos-arm64-production",
      path: "integrity",
    },
    manifest.expiresAtUnix
  );
  assertExactKeys(manifest.files, PAYLOAD_FILES.keys(), "source-runtime files");
  return manifest;
}

function runtimePaths(directory) {
  return {
    runtimeDir: directory,
    nativeDir: path.join(directory, "native-core"),
    dbKeyBundleDir: path.join(directory, "db-key"),
    integrityNativePath: path.join(directory, "integrity", "libwce_integrity.dylib"),
  };
}

function validateSourceRuntimeDirectory(root, pinInput, { nowUnix = Math.floor(Date.now() / 1000) } = {}) {
  const pin = validatePin(pinInput);
  assertActivePin(pin, nowUnix);
  const directory = path.resolve(String(root || ""));
  let rootStat;
  try {
    rootStat = fs.lstatSync(directory);
  } catch {
    throw new Error(`Source-runtime directory does not exist: ${directory}`);
  }
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error("Source-runtime root must be a regular directory");
  }
  const tree = walkRuntimeDirectory(directory);
  assertExactSet(tree.directories, RUNTIME_DIRECTORIES, "Source-runtime directory");
  assertExactSet(tree.files, RUNTIME_FILES, "Source-runtime file");

  const manifestPath = path.join(directory, RUNTIME_MANIFEST_FILE);
  assertRegularFile(manifestPath, 128 * 1024);
  if (sha256File(manifestPath) !== pin.runtimeManifestSha256) {
    throw new Error("Pinned source-runtime manifest digest does not match");
  }
  const manifest = validateRuntimeManifest(readJsonObject(manifestPath), pin, nowUnix);
  for (const [relative, executable] of PAYLOAD_FILES) {
    const file = path.join(directory, ...relative.split("/"));
    const stat = assertRegularFile(file);
    const metadata = assertExactKeys(
      manifest.files[relative],
      ["sha256", "size", "executable"],
      `source-runtime file ${relative}`
    );
    if (
      !SHA256_PATTERN.test(String(metadata.sha256 || "")) ||
      metadata.sha256 === "0".repeat(64) ||
      !Number.isSafeInteger(metadata.size) ||
      metadata.size <= 0 ||
      metadata.size !== stat.size ||
      metadata.executable !== executable ||
      sha256File(file) !== metadata.sha256
    ) {
      throw new Error(`Source-runtime file digest or metadata mismatch: ${relative}`);
    }
  }
  const paths = runtimePaths(directory);
  const policy = resolveNativeCoreRuntimePolicy({
    env: {},
    isPackaged: false,
    nativeDir: paths.nativeDir,
    nowUnix,
    platform: "darwin",
  });
  if (policy.artifactState !== "source-public") {
    throw new Error("Source-runtime native-core is not the restricted source-public profile");
  }
  return { ...paths, manifest, pin, policy };
}

function ensureRuntimePermissions(directory) {
  for (const [relative, executable] of PAYLOAD_FILES) {
    fs.chmodSync(path.join(directory, ...relative.split("/")), executable ? 0o755 : 0o644);
  }
  fs.chmodSync(path.join(directory, RUNTIME_MANIFEST_FILE), 0o644);
}

function defaultCacheRoot() {
  return path.join(
    os.homedir(),
    "Library",
    "Caches",
    "WeChatDataAnalysis",
    "source-native-core"
  );
}

function isPathInside(parent, child) {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  return (
    relative !== "" &&
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

function removeCacheEntry(cacheRoot, target) {
  if (!isPathInside(cacheRoot, target)) {
    throw new Error("Refusing to remove a path outside the source-runtime cache");
  }
  fs.rmSync(target, { recursive: true, force: true });
}

function applySourceRuntimeEnvironment(env, result) {
  const target = env || process.env;
  if (!result?.nativeDir) return target;
  target[ENV_SOURCE_NATIVE_CORE_DIR] = result.nativeDir;
  target[ENV_MACOS_DB_KEY_BUNDLE] = result.dbKeyBundleDir;
  target[ENV_INTEGRITY_NATIVE_PATH] = result.integrityNativePath;
  return target;
}

function ensureSourceNativeCore({
  arch = process.arch,
  cacheRoot,
  configPath = DEFAULT_CONFIG_PATH,
  env = process.env,
  nowUnix = Math.floor(Date.now() / 1000),
  platform = process.platform,
  spawnSyncImpl = spawnSync,
} = {}) {
  if (platform !== "darwin") {
    return {
      runtimeDir: null,
      nativeDir: null,
      dbKeyBundleDir: null,
      integrityNativePath: null,
      reason: "non-macos",
    };
  }
  if (arch !== "arm64") {
    throw new Error(`macOS source runtime currently supports arm64 only; received ${arch}`);
  }

  const pin = validatePin(readJsonObject(configPath, 16 * 1024));
  assertActivePin(pin, nowUnix);
  const configuredCache = String(env?.[ENV_SOURCE_NATIVE_CORE_CACHE_DIR] || "").trim();
  const root = path.resolve(cacheRoot || configuredCache || defaultCacheRoot());
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const rootStat = fs.lstatSync(root);
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error("Source-runtime cache root must not be a symbolic link");
  }

  const cacheKey = `${pin.releaseTag}-${pin.assetSha256.slice(0, 12)}`;
  const runtimeDir = path.join(root, cacheKey);
  try {
    const cached = validateSourceRuntimeDirectory(runtimeDir, pin, { nowUnix });
    ensureRuntimePermissions(runtimeDir);
    return { ...cached, reason: "verified-cache" };
  } catch {
    // A missing or modified cache is repaired from the immutable public asset.
  }
  if (fs.existsSync(runtimeDir)) removeCacheEntry(root, runtimeDir);

  const nonce = `${process.pid}-${crypto.randomBytes(6).toString("hex")}`;
  const temporary = path.join(root, `.${cacheKey}.tmp-${nonce}`);
  const archivePath = path.join(root, `.${cacheKey}.download-${nonce}.tar.gz`);
  fs.mkdirSync(temporary, { mode: 0o700 });
  try {
    downloadPinnedRelease(archivePath, pin, { env, spawnSyncImpl });
    extractArchive(archivePath, temporary, { env, spawnSyncImpl });
    validateSourceRuntimeDirectory(temporary, pin, { nowUnix });
    ensureRuntimePermissions(temporary);
    if (fs.existsSync(runtimeDir)) removeCacheEntry(root, runtimeDir);
    fs.renameSync(temporary, runtimeDir);
    const installed = validateSourceRuntimeDirectory(runtimeDir, pin, { nowUnix });
    ensureRuntimePermissions(runtimeDir);
    removeCacheEntry(root, archivePath);
    return { ...installed, reason: "downloaded" };
  } catch (err) {
    if (fs.existsSync(temporary)) removeCacheEntry(root, temporary);
    if (fs.existsSync(archivePath)) removeCacheEntry(root, archivePath);
    throw err;
  }
}

module.exports = {
  ASSET_NAME,
  DEFAULT_CONFIG_PATH,
  ENV_INTEGRITY_NATIVE_PATH,
  ENV_MACOS_DB_KEY_BUNDLE,
  ENV_SOURCE_NATIVE_CORE_CACHE_DIR,
  ENV_SOURCE_NATIVE_CORE_DIR,
  PROFILE,
  applySourceRuntimeEnvironment,
  ensureSourceNativeCore,
  publicReleaseUrl,
  validateDownloadedSourceArtifact: validateSourceRuntimeDirectory,
  validatePin,
  validateSourceRuntimeDirectory,
};
