const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const {
  resolveNativeCoreRuntimePolicy,
} = require("./native-core-runtime.cjs");
const {
  ENV_SOURCE_NATIVE_CORE_DIR,
} = require("./native-core-path.cjs");

const ENV_SOURCE_NATIVE_CORE_CACHE_DIR = "WCE_NATIVE_CORE_SOURCE_CACHE_DIR";
const DEFAULT_CONFIG_PATH = path.resolve(
  __dirname,
  "..",
  "resources",
  "native-core-source-macos.json"
);
const ARTIFACT_NAME = "wechatdb-native-macos-arm64-development";
const PRODUCER_WORKFLOW = ".github/workflows/macos-native-production.yml";
const CORE_FILES = Object.freeze([
  "libwechatdb_client.dylib",
  "wechatdb_broker",
  "wechatdb_native_build.json",
]);
const PROVENANCE_FILE = "source_provenance.json";
const CHECKSUM_FILES = Object.freeze([...CORE_FILES, PROVENANCE_FILE].sort());
const DOWNLOADED_FILES = new Set([...CHECKSUM_FILES, "SHA256SUMS.txt"]);
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const REVISION_PATTERN = /^[0-9a-f]{40}$/;
const REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

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
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new Error(`${label} field allowlist mismatch`);
  }
}

function readJsonObject(file, maximum = 32 * 1024) {
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
  if (!input || Array.isArray(input) || typeof input !== "object") {
    throw new Error("macOS source native-core pin must be an object");
  }
  const keys = [
    "schemaVersion",
    "platform",
    "architecture",
    "artifactName",
    "producerRepository",
    "producerWorkflow",
    "producerWorkflowRunId",
    "producerWorkflowRunAttempt",
    "sourceRevision",
    "checksumsSha256",
  ];
  assertExactKeys(input, keys, "macOS source native-core pin");
  if (
    input.schemaVersion !== 1 ||
    input.platform !== "darwin" ||
    input.architecture !== "arm64" ||
    input.artifactName !== ARTIFACT_NAME ||
    input.producerWorkflow !== PRODUCER_WORKFLOW ||
    !REPOSITORY_PATTERN.test(String(input.producerRepository || "")) ||
    !Number.isSafeInteger(input.producerWorkflowRunId) ||
    input.producerWorkflowRunId <= 0 ||
    !Number.isSafeInteger(input.producerWorkflowRunAttempt) ||
    input.producerWorkflowRunAttempt <= 0 ||
    !REVISION_PATTERN.test(String(input.sourceRevision || "")) ||
    !SHA256_PATTERN.test(String(input.checksumsSha256 || "")) ||
    input.checksumsSha256 === "0".repeat(64)
  ) {
    throw new Error("macOS source native-core pin is invalid");
  }
  return Object.freeze({ ...input });
}

function assertRegularFile(file, maximum = 512 * 1024 * 1024) {
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch {
    throw new Error(`Missing source native-core file: ${path.basename(file)}`);
  }
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`Invalid source native-core file: ${path.basename(file)}`);
  }
}

function validateCoreTrio(directory) {
  for (const name of CORE_FILES) {
    assertRegularFile(path.join(directory, name), name.endsWith(".json") ? 32 * 1024 : undefined);
  }
  const policy = resolveNativeCoreRuntimePolicy({
    env: {},
    isPackaged: false,
    nativeDir: directory,
    platform: "darwin",
  });
  if (policy.artifactState !== "development" || policy.manifest?.buildId !== "dev-local") {
    throw new Error("Source native-core is not the exact macOS dev-local profile");
  }
  return policy;
}

function ensureRuntimePermissions(directory) {
  // actions/upload-artifact normalizes file modes. Restore the executable bit
  // only after content and provenance verification; chmod does not change the
  // pinned file digest.
  fs.chmodSync(path.join(directory, "wechatdb_broker"), 0o755);
  fs.chmodSync(path.join(directory, "libwechatdb_client.dylib"), 0o755);
}

function validateDownloadedSourceArtifact(root, pinInput) {
  const pin = validatePin(pinInput);
  const directory = path.resolve(String(root || ""));
  let rootStat;
  try {
    rootStat = fs.lstatSync(directory);
  } catch {
    throw new Error(`Source native-core artifact directory does not exist: ${directory}`);
  }
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error("Source native-core artifact root must be a regular directory");
  }
  const entries = fs.readdirSync(directory, { withFileTypes: true });
  const names = new Set(entries.map((entry) => entry.name));
  if (
    names.size !== DOWNLOADED_FILES.size ||
    [...DOWNLOADED_FILES].some((name) => !names.has(name))
  ) {
    throw new Error("Source native-core artifact file allowlist mismatch");
  }
  for (const entry of entries) {
    if (!entry.isFile() || entry.isSymbolicLink()) {
      throw new Error(`Source native-core artifact entry is not a regular file: ${entry.name}`);
    }
    assertRegularFile(path.join(directory, entry.name));
  }

  const checksumPath = path.join(directory, "SHA256SUMS.txt");
  if (sha256File(checksumPath) !== pin.checksumsSha256) {
    throw new Error("Pinned SHA256SUMS.txt digest does not match the source artifact");
  }
  let checksumLines;
  try {
    checksumLines = fs.readFileSync(checksumPath, "ascii").split(/\r?\n/);
  } catch (err) {
    throw new Error(`Invalid SHA256SUMS.txt: ${err?.message || err}`);
  }
  if (checksumLines.at(-1) === "") checksumLines.pop();
  const expectedChecksums = CHECKSUM_FILES.map(
    (name) => `${sha256File(path.join(directory, name))}  ${name}`
  );
  if (
    checksumLines.length !== expectedChecksums.length ||
    checksumLines.some((line, index) => line !== expectedChecksums[index])
  ) {
    throw new Error("SHA256SUMS.txt is non-canonical or does not match the source artifact");
  }

  const manifestPath = path.join(directory, "wechatdb_native_build.json");
  const provenance = readJsonObject(path.join(directory, PROVENANCE_FILE));
  const expectedProvenance = {
    architecture: "arm64",
    artifactName: pin.artifactName,
    buildId: "dev-local",
    manifestSha256: sha256File(manifestPath),
    platform: "macos",
    producerRepository: pin.producerRepository,
    producerWorkflow: pin.producerWorkflow,
    producerWorkflowRunAttempt: pin.producerWorkflowRunAttempt,
    producerWorkflowRunId: pin.producerWorkflowRunId,
    profile: "source-development",
    schemaVersion: 1,
    sourceRevision: pin.sourceRevision,
  };
  assertExactKeys(provenance, Object.keys(expectedProvenance), "source provenance");
  for (const [key, expected] of Object.entries(expectedProvenance)) {
    if (provenance[key] !== expected) {
      throw new Error(`Source provenance mismatch: ${key}`);
    }
  }
  if (!SHA256_PATTERN.test(String(provenance.manifestSha256 || ""))) {
    throw new Error("Source provenance manifest digest is invalid");
  }

  const policy = validateCoreTrio(directory);
  return { directory, pin, policy, provenance };
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
  return relative !== "" && !relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative);
}

function removeCacheEntry(cacheRoot, target) {
  if (!isPathInside(cacheRoot, target)) {
    throw new Error("Refusing to remove a path outside the source native-core cache");
  }
  fs.rmSync(target, { recursive: true, force: true });
}

function redactCommandOutput(value, env) {
  let text = String(value || "").trim();
  for (const name of ["GH_TOKEN", "GITHUB_TOKEN"]) {
    const secret = String(env?.[name] || "");
    if (secret) text = text.split(secret).join("[REDACTED]");
  }
  return text.slice(-2000);
}

function downloadPinnedArtifact(destination, pin, { env, spawnSyncImpl }) {
  const args = [
    "run",
    "download",
    String(pin.producerWorkflowRunId),
    "--repo",
    pin.producerRepository,
    "--name",
    pin.artifactName,
    "--dir",
    destination,
  ];
  const result = spawnSyncImpl("gh", args, {
    encoding: "utf8",
    env,
    maxBuffer: 4 * 1024 * 1024,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  if (result?.error?.code === "ENOENT") {
    throw new Error(
      "macOS 源码启动需要 GitHub CLI 取得私有 native-core；请安装 gh，执行 gh auth login，并确保账号可读取 " +
        `${pin.producerRepository}。也可显式设置 ${ENV_SOURCE_NATIVE_CORE_DIR}。`
    );
  }
  if (result?.error || result?.status !== 0) {
    const detail = redactCommandOutput(result?.stderr || result?.stdout || result?.error?.message, env);
    throw new Error(
      `无法取得 macOS 私有 native-core。请执行 gh auth login，并确保账号可读取 ${pin.producerRepository}。` +
        (detail ? `\ngh: ${detail}` : "")
    );
  }
}

function ensureSourceNativeCore({
  arch = process.arch,
  cacheRoot,
  configPath = DEFAULT_CONFIG_PATH,
  env = process.env,
  platform = process.platform,
  spawnSyncImpl = spawnSync,
} = {}) {
  if (platform !== "darwin") {
    return { nativeDir: null, reason: "non-macos" };
  }
  if (arch !== "arm64") {
    throw new Error(`macOS source native-core currently supports arm64 only; received ${arch}`);
  }

  const explicit = String(env?.[ENV_SOURCE_NATIVE_CORE_DIR] || "").trim();
  if (explicit) {
    const nativeDir = path.resolve(explicit);
    validateCoreTrio(nativeDir);
    ensureRuntimePermissions(nativeDir);
    return { nativeDir, reason: "explicit-directory" };
  }

  const pin = validatePin(readJsonObject(configPath, 16 * 1024));
  const configuredCache = String(env?.[ENV_SOURCE_NATIVE_CORE_CACHE_DIR] || "").trim();
  const root = path.resolve(cacheRoot || configuredCache || defaultCacheRoot());
  const cacheKey = `${pin.producerWorkflowRunId}-${pin.producerWorkflowRunAttempt}-${pin.sourceRevision.slice(0, 12)}`;
  const nativeDir = path.join(root, cacheKey);
  let cached = false;
  try {
    validateDownloadedSourceArtifact(nativeDir, pin);
    ensureRuntimePermissions(nativeDir);
    cached = true;
  } catch {
    cached = false;
  }
  if (cached) return { nativeDir, pin, reason: "verified-cache" };

  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  if (fs.existsSync(nativeDir) || fs.lstatSync(root).isSymbolicLink()) {
    if (fs.lstatSync(root).isSymbolicLink()) {
      throw new Error("Source native-core cache root must not be a symbolic link");
    }
    if (fs.existsSync(nativeDir)) removeCacheEntry(root, nativeDir);
  }
  const temporary = path.join(
    root,
    `.${cacheKey}.tmp-${process.pid}-${crypto.randomBytes(6).toString("hex")}`
  );
  fs.mkdirSync(temporary, { mode: 0o700 });
  try {
    downloadPinnedArtifact(temporary, pin, { env, spawnSyncImpl });
    validateDownloadedSourceArtifact(temporary, pin);
    if (fs.existsSync(nativeDir)) removeCacheEntry(root, nativeDir);
    fs.renameSync(temporary, nativeDir);
    validateDownloadedSourceArtifact(nativeDir, pin);
    ensureRuntimePermissions(nativeDir);
    return { nativeDir, pin, reason: "downloaded" };
  } catch (err) {
    if (fs.existsSync(temporary)) removeCacheEntry(root, temporary);
    throw err;
  }
}

module.exports = {
  ARTIFACT_NAME,
  DEFAULT_CONFIG_PATH,
  ENV_SOURCE_NATIVE_CORE_CACHE_DIR,
  ENV_SOURCE_NATIVE_CORE_DIR,
  ensureSourceNativeCore,
  validateDownloadedSourceArtifact,
  validatePin,
};
