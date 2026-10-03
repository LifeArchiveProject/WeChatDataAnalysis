"use strict";

// Linux 的 native core 消费校验。
//
// 与 macOS 那套（macos-native-core-packaging.cjs）对齐，但签名模型完全不同：
// Linux 没有代码签名，产物身份 = **内容哈希**（linuxIntegrityMode: content-hash-pin）。
// 所以这里把 manifest 里的 linuxClientSha256 / linuxBrokerSha256 当成身份声明，
// 逐字节比对实际文件，再用 SHA256SUMS.txt + provenance.json 把来源钉到某个 WCDB revision。
// 一旦内容被替换，哈希必然对不上，直接 fail closed。

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const CLIENT_NAME = "libwechatdb_client.so";
const BROKER_NAME = "wechatdb_broker";
const MANIFEST_NAME = "wechatdb_native_build.json";
const CHECKSUMS_NAME = "SHA256SUMS.txt";
const PROVENANCE_NAME = "provenance.json";
const ARTIFACT_TEST_NAME = "Test-LinuxNativeProductionArtifact.py";

const BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const REVISION_PATTERN = /^[0-9a-f]{40}$/;
const REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const NON_PRODUCTION_BUILD_ID_PATTERN =
  /(^|[._-])(dev|debug|test|local|snapshot|staging)([._-]|$)/i;

const INTEGRITY_MODE = "content-hash-pin";
// 产出这份产物的工作流路径。它也是身份的一部分：只有被审阅过的 producer 才允许
// 产出发布路径会接受的产物（artifact 内部的 Python 校验器断言同一个常量）。
const PRODUCER_WORKFLOW = ".github/workflows/linux-native-production.yml";
const PEER_VERIFICATION = "same-user-peer-credentials";
const HOST_VERIFICATION = Object.freeze({
  production: "content-hash-pin",
  sourceRuntime: "same-user-direct-parent",
});
const ARTIFACT_NAME_PATTERN = /^wechatdb-native-linux-x64-(production|source-public)$/;
const PRODUCERS = new Set(["github-actions", "manual"]);

// 校验集只覆盖「运行时真正要用的四个文件」；SHA256SUMS.txt / provenance.json 是自证材料。
const CHECKSUM_FILE_NAMES = Object.freeze([
  ARTIFACT_TEST_NAME,
  CLIENT_NAME,
  BROKER_NAME,
  MANIFEST_NAME,
]);
const ARTIFACT_FILE_NAMES = Object.freeze([
  ...CHECKSUM_FILE_NAMES,
  CHECKSUMS_NAME,
  PROVENANCE_NAME,
]);
const RUNTIME_FILE_NAMES = Object.freeze([CLIENT_NAME, BROKER_NAME, MANIFEST_NAME]);

const MANIFEST_REQUIRED_FIELDS = Object.freeze([
  "schemaVersion",
  "platform",
  "distributionMode",
  "buildId",
  "buildIssuedAtUnix",
  "buildExpiresAtUnix",
  "developmentBuild",
  "offlineBootstrapFeatureBits",
  "offlineExportSealFormat",
  "codeSignatureEnforced",
  "rootPublicKeyCompiled",
  "testHooksEnabled",
  "stagingPinnedSignerTrust",
  "linuxIntegrityMode",
  "linuxClientSha256",
  "linuxBrokerSha256",
  "linuxPeerVerification",
  "linuxHostVerification",
  "securityNoticeId",
  "securityNoticeSha256",
  "securityCheckpointSetId",
  "securityCheckpointCount",
  "securityCheckpointSetSha256",
]);
const MANIFEST_OPTIONAL_FIELDS = Object.freeze(["sourceRuntime"]);
const PROVENANCE_FIELDS = Object.freeze([
  "schemaVersion",
  "artifactName",
  "producer",
  "workflow",
  "repository",
  "runId",
  "runAttempt",
  "sourceRevision",
  "build",
  "manifestSha256",
  "checksumsSha256",
  "artifacts",
]);

function exactKeys(value, required, optional = []) {
  if (!value || Array.isArray(value) || typeof value !== "object") return false;
  const allowed = new Set([...required, ...optional]);
  const actual = Object.keys(value);
  if (actual.some((name) => !allowed.has(name))) return false;
  return required.every((name) => Object.prototype.hasOwnProperty.call(value, name));
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function isNonZeroSha256(value) {
  const text = String(value || "");
  return SHA256_PATTERN.test(text) && !/^0{64}$/.test(text);
}

function readJson(filePath, label, maximum = 64 * 1024) {
  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile() || stat.size <= 0 || stat.size > maximum) throw new Error("invalid size");
    const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!value || Array.isArray(value) || typeof value !== "object") {
      throw new Error("root must be an object");
    }
    return value;
  } catch (error) {
    throw new Error(`Invalid ${label} at ${filePath}: ${error.message}`);
  }
}

function requiredEnv(env, name, pattern) {
  const value = String(env[name] || "").trim();
  if (!value || (pattern && !pattern.test(value))) {
    throw new Error(`Missing or invalid ${name}`);
  }
  return value;
}

function optionalEnvPin(env, name) {
  const value = String(env[name] || "").trim();
  if (!value) return null;
  if (!isNonZeroSha256(value)) {
    throw new Error(`${name} must be a non-zero lowercase SHA-256 digest`);
  }
  return value;
}

function parseChecksums(filePath) {
  const records = new Map();
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    const match = /^([0-9a-f]{64}) {2}([A-Za-z0-9._-]+)$/.exec(line);
    if (!match || records.has(match[2])) throw new Error("SHA256SUMS.txt has an invalid record");
    records.set(match[2], match[1]);
  }
  return records;
}

function linuxNativeManifestErrors(manifest, { nowUnix = Math.floor(Date.now() / 1000) } = {}) {
  const errors = [];
  if (!exactKeys(manifest, MANIFEST_REQUIRED_FIELDS, MANIFEST_OPTIONAL_FIELDS)) {
    errors.push("manifest fields must match Linux schema v4 exactly");
    return errors;
  }
  if (manifest.schemaVersion !== 4) errors.push("schemaVersion must equal 4");
  if (manifest.platform !== "linux") errors.push("platform must equal linux");
  if (manifest.distributionMode !== "public") errors.push("distributionMode must equal public");
  if (
    !BUILD_ID_PATTERN.test(String(manifest.buildId || "")) ||
    NON_PRODUCTION_BUILD_ID_PATTERN.test(String(manifest.buildId || ""))
  ) {
    errors.push("buildId must be an immutable production identity");
  }
  const issued = manifest.buildIssuedAtUnix;
  const expires = manifest.buildExpiresAtUnix;
  if (
    !Number.isSafeInteger(issued) ||
    issued <= 0 ||
    !Number.isSafeInteger(expires) ||
    expires !== issued + BUILD_LIFETIME_SECONDS
  ) {
    errors.push("build validity window must equal exactly 45 days");
  } else if (!Number.isSafeInteger(nowUnix) || nowUnix < 0 || nowUnix >= expires) {
    errors.push("build has reached its fixed expiration time");
  }
  if (
    manifest.developmentBuild !== false ||
    manifest.offlineBootstrapFeatureBits !== 3 ||
    manifest.offlineExportSealFormat !== "WES2" ||
    manifest.codeSignatureEnforced !== true ||
    manifest.rootPublicKeyCompiled !== true ||
    manifest.testHooksEnabled !== false ||
    manifest.stagingPinnedSignerTrust !== false
  ) {
    errors.push("native production security fields do not match policy");
  }
  if (manifest.linuxIntegrityMode !== INTEGRITY_MODE) {
    errors.push(`linuxIntegrityMode must equal ${INTEGRITY_MODE}`);
  }
  if (manifest.linuxPeerVerification !== PEER_VERIFICATION) {
    errors.push(`linuxPeerVerification must equal ${PEER_VERIFICATION}`);
  }
  // 两个 profile 的 host 校验强度不同，必须自洽：源码分发用「直接父进程」，
  // 否则用「内容哈希 pin」。声明 sourceRuntime 就只能是前者。
  const sourceRuntime = manifest.sourceRuntime === true;
  if (
    Object.prototype.hasOwnProperty.call(manifest, "sourceRuntime") &&
    manifest.sourceRuntime !== true
  ) {
    errors.push("sourceRuntime must be true when present");
  }
  const expectedHostVerification = sourceRuntime
    ? HOST_VERIFICATION.sourceRuntime
    : HOST_VERIFICATION.production;
  if (manifest.linuxHostVerification !== expectedHostVerification) {
    errors.push(`linuxHostVerification must equal ${expectedHostVerification}`);
  }
  const pins = [manifest.linuxClientSha256, manifest.linuxBrokerSha256];
  if (pins.some((value) => !isNonZeroSha256(value))) {
    errors.push("linux client and broker content pins must be non-zero SHA-256 digests");
  } else if (pins[0] === pins[1]) {
    errors.push("linux client and broker content pins must be distinct");
  }
  if (
    manifest.securityNoticeId !== "WCE-AUTOMATED-ANALYSIS-NOTICE-V2" ||
    !SHA256_PATTERN.test(String(manifest.securityNoticeSha256 || "")) ||
    manifest.securityCheckpointSetId !== "WCE-AI-CHECKPOINT-SET-V3" ||
    manifest.securityCheckpointCount !== 7 ||
    !SHA256_PATTERN.test(String(manifest.securityCheckpointSetSha256 || ""))
  ) {
    errors.push("native security checkpoint contract mismatch");
  }
  return errors;
}

// 内容哈希就是 Linux 的身份。manifest 声明什么，盘上就必须是什么。
function linuxContentPinErrors({ directory, manifest }) {
  const errors = [];
  const expectations = [
    [CLIENT_NAME, manifest?.linuxClientSha256],
    [BROKER_NAME, manifest?.linuxBrokerSha256],
  ];
  for (const [name, expected] of expectations) {
    const filePath = path.join(directory, name);
    try {
      if (!fs.statSync(filePath).isFile()) throw new Error("not a regular file");
    } catch {
      errors.push(`missing native component ${name}`);
      continue;
    }
    const actual = sha256File(filePath);
    if (actual !== expected) {
      errors.push(`content hash mismatch for ${name}: expected ${expected}, received ${actual}`);
    }
  }
  return errors;
}

// 极简 ELF 头解析：不依赖 readelf/file，Linux 与 macOS 主机上都能跑。
// 只断言「身份声明」需要的部分：64 位、小端、x86-64、以及可执行类别。
function inspectElf(filePath) {
  const header = Buffer.alloc(20);
  const handle = fs.openSync(filePath, "r");
  try {
    fs.readSync(handle, header, 0, 20, 0);
  } finally {
    fs.closeSync(handle);
  }
  if (!header.subarray(0, 4).equals(Buffer.from([0x7f, 0x45, 0x4c, 0x46]))) {
    throw new Error(`not an ELF file: ${filePath}`);
  }
  const elfClass = header[4];
  const dataEncoding = header[5];
  if (elfClass !== 2) throw new Error(`ELF is not 64-bit: ${filePath}`);
  if (dataEncoding !== 1) throw new Error(`ELF is not little-endian: ${filePath}`);
  const type = header.readUInt16LE(16);
  const machine = header.readUInt16LE(18);
  if (machine !== 0x3e) throw new Error(`ELF is not x86-64: ${filePath}`);
  return { type, machine, isSharedObject: type === 3, isExecutable: type === 2 || type === 3 };
}

function resolveLinuxNativeCoreArtifacts({
  env = process.env,
  platform = process.platform,
  nowUnix = Math.floor(Date.now() / 1000),
} = {}) {
  if (platform !== "linux") {
    throw new Error(`Linux native-core artifacts cannot be resolved on platform: ${platform}`);
  }
  const artifactDirValue = String(env.WCE_NATIVE_CORE_ARTIFACT_DIR || "").trim();
  if (!artifactDirValue) {
    throw new Error(
      "Missing WCE_NATIVE_CORE_ARTIFACT_DIR. Expected a directory containing: " +
        RUNTIME_FILE_NAMES.join(", ")
    );
  }
  const artifactDir = path.resolve(artifactDirValue);
  let stat;
  try {
    stat = fs.statSync(artifactDir);
  } catch {
    throw new Error(`WCE_NATIVE_CORE_ARTIFACT_DIR is not readable: ${artifactDir}`);
  }
  if (!stat.isDirectory()) {
    throw new Error(`WCE_NATIVE_CORE_ARTIFACT_DIR is not a directory: ${artifactDir}`);
  }
  const entries = fs.readdirSync(artifactDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();
  const wanted = [...ARTIFACT_FILE_NAMES].sort();
  if (entries.some((entry) => !entry.isFile()) || files.join("\n") !== wanted.join("\n")) {
    throw new Error(
      `Linux native-core artifact allowlist mismatch. Expected ${wanted.join(", ")}, received ${files.join(", ")}`
    );
  }

  const repository = requiredEnv(env, "WCE_NATIVE_CORE_ARTIFACT_REPOSITORY", REPOSITORY_PATTERN);
  const sourceRevision = requiredEnv(env, "WCE_NATIVE_CORE_SOURCE_REVISION", REVISION_PATTERN);
  const buildId = requiredEnv(env, "WCE_NATIVE_CORE_BUILD_ID", BUILD_ID_PATTERN);
  const clientPin = optionalEnvPin(env, "WCE_NATIVE_CORE_CLIENT_SHA256");
  const brokerPin = optionalEnvPin(env, "WCE_NATIVE_CORE_BROKER_SHA256");

  const manifestPath = path.join(artifactDir, MANIFEST_NAME);
  const manifest = readJson(manifestPath, "Linux native-core manifest", 16 * 1024);
  const manifestErrors = linuxNativeManifestErrors(manifest, { nowUnix });
  if (manifestErrors.length > 0) {
    throw new Error(`Refusing Linux native-core artifact: ${manifestErrors.join("; ")}`);
  }
  if (manifest.buildId !== buildId) {
    throw new Error("Linux native-core manifest does not match the protected build id pin");
  }
  if (clientPin && manifest.linuxClientSha256 !== clientPin) {
    throw new Error("Linux native-core manifest does not match the protected client content pin");
  }
  if (brokerPin && manifest.linuxBrokerSha256 !== brokerPin) {
    throw new Error("Linux native-core manifest does not match the protected broker content pin");
  }

  const checksumsPath = path.join(artifactDir, CHECKSUMS_NAME);
  const checksums = parseChecksums(checksumsPath);
  if (
    checksums.size !== CHECKSUM_FILE_NAMES.length ||
    CHECKSUM_FILE_NAMES.some(
      (name) => checksums.get(name) !== sha256File(path.join(artifactDir, name))
    )
  ) {
    throw new Error("Linux native-core checksum set does not match the artifact allowlist");
  }

  const provenance = readJson(path.join(artifactDir, PROVENANCE_NAME), "Linux native-core provenance");
  if (!exactKeys(provenance, PROVENANCE_FIELDS)) {
    throw new Error("Linux native-core provenance fields do not match schema v1 exactly");
  }
  const producer = String(provenance.producer || "");
  if (!PRODUCERS.has(producer)) {
    throw new Error("Linux native-core provenance must come from github-actions or a manual producer");
  }
  if (provenance.schemaVersion !== 1) {
    throw new Error("Linux native-core provenance schemaVersion must equal 1");
  }
  if (!ARTIFACT_NAME_PATTERN.test(String(provenance.artifactName || ""))) {
    throw new Error("Linux native-core provenance artifactName is not a Linux x64 profile");
  }
  if (provenance.repository !== repository) {
    throw new Error("Linux native-core provenance repository does not match the protected pin");
  }
  if (provenance.sourceRevision !== sourceRevision) {
    throw new Error("Linux native-core provenance revision does not match the protected pin");
  }
  const expectedRunId = String(env.WCE_NATIVE_CORE_ARTIFACT_RUN_ID || "").trim();
  if (producer === "github-actions") {
    if (!/^[1-9][0-9]*$/.test(expectedRunId) || Number(provenance.runId) !== Number(expectedRunId)) {
      throw new Error("Linux native-core provenance run id does not match the protected pin");
    }
    if (!Number.isSafeInteger(provenance.runAttempt) || provenance.runAttempt <= 0) {
      throw new Error("Linux native-core provenance runAttempt must be a positive integer");
    }
    if (provenance.workflow !== PRODUCER_WORKFLOW) {
      throw new Error(
        `Linux native-core provenance must come from ${PRODUCER_WORKFLOW}`
      );
    }
  } else {
    if (expectedRunId !== "" || provenance.runId !== 0 || provenance.runAttempt !== 0) {
      throw new Error("Manual Linux native-core provenance must not claim a CI run");
    }
    if (String(provenance.workflow || "") !== "manual") {
      throw new Error("Manual Linux native-core provenance must declare workflow manual");
    }
  }
  if (provenance.manifestSha256 !== sha256File(manifestPath)) {
    throw new Error("Linux native-core provenance manifest hash mismatch");
  }
  if (provenance.checksumsSha256 !== sha256File(checksumsPath)) {
    throw new Error("Linux native-core provenance checksums hash mismatch");
  }
  const expectedInventory = CHECKSUM_FILE_NAMES.map((name) => ({
    path: name,
    sha256: sha256File(path.join(artifactDir, name)),
    size: fs.statSync(path.join(artifactDir, name)).size,
  }));
  if (JSON.stringify(provenance.artifacts) !== JSON.stringify(expectedInventory)) {
    throw new Error("Linux native-core provenance artifact inventory mismatch");
  }
  const build = provenance.build;
  // linuxHostVerification / sourceRuntime 只出现在源码分发（-sp）那份 provenance 里，
  // 所以它们是「可选的，但出现就必须与 manifest 一致」。
  if (
    !exactKeys(
      build,
      [
        "architecture",
        "distributionMode",
        "expiresAtUnix",
        "id",
        "integrityMode",
        "issuedAtUnix",
        "linuxBrokerSha256",
        "linuxClientSha256",
        "offlineBootstrapFeatureBits",
        "offlineExportSealFormat",
        "platform",
        "readOnlyBuild",
        "securityCheckpointCount",
        "securityCheckpointSetId",
        "securityCheckpointSetSha256",
        "securityNoticeId",
        "securityNoticeSha256",
      ],
      ["linuxHostVerification", "sourceRuntime"]
    ) ||
    build.id !== manifest.buildId ||
    build.platform !== "linux" ||
    build.architecture !== "x64" ||
    build.distributionMode !== manifest.distributionMode ||
    build.integrityMode !== manifest.linuxIntegrityMode ||
    build.readOnlyBuild !== true ||
    build.issuedAtUnix !== manifest.buildIssuedAtUnix ||
    build.expiresAtUnix !== manifest.buildExpiresAtUnix ||
    build.linuxClientSha256 !== manifest.linuxClientSha256 ||
    build.linuxBrokerSha256 !== manifest.linuxBrokerSha256 ||
    build.offlineBootstrapFeatureBits !== manifest.offlineBootstrapFeatureBits ||
    build.offlineExportSealFormat !== manifest.offlineExportSealFormat ||
    build.securityCheckpointCount !== manifest.securityCheckpointCount ||
    build.securityCheckpointSetId !== manifest.securityCheckpointSetId ||
    build.securityCheckpointSetSha256 !== manifest.securityCheckpointSetSha256 ||
    build.securityNoticeId !== manifest.securityNoticeId ||
    build.securityNoticeSha256 !== manifest.securityNoticeSha256
  ) {
    throw new Error("Linux native-core provenance build record does not match the manifest");
  }
  if (
    (Object.prototype.hasOwnProperty.call(build, "linuxHostVerification") &&
      build.linuxHostVerification !== manifest.linuxHostVerification) ||
    (Object.prototype.hasOwnProperty.call(build, "sourceRuntime") &&
      build.sourceRuntime !== manifest.sourceRuntime)
  ) {
    throw new Error("Linux native-core provenance build record does not match the manifest");
  }

  const pinErrors = linuxContentPinErrors({ directory: artifactDir, manifest });
  if (pinErrors.length > 0) {
    throw new Error(`Refusing Linux native-core artifact: ${pinErrors.join("; ")}`);
  }
  const clientElf = inspectElf(path.join(artifactDir, CLIENT_NAME));
  const brokerElf = inspectElf(path.join(artifactDir, BROKER_NAME));
  if (!clientElf.isSharedObject) {
    throw new Error("Linux native client must be an x86-64 ELF shared object");
  }
  if (!brokerElf.isExecutable) {
    throw new Error("Linux native broker must be an x86-64 ELF executable");
  }

  return {
    artifactDir,
    manifest,
    provenance,
    repository,
    sourceRevision,
    buildId,
    clientPin: manifest.linuxClientSha256,
    brokerPin: manifest.linuxBrokerSha256,
    names: [...RUNTIME_FILE_NAMES],
    required: true,
  };
}

module.exports = {
  ARTIFACT_FILE_NAMES,
  BROKER_NAME,
  CHECKSUM_FILE_NAMES,
  CLIENT_NAME,
  HOST_VERIFICATION,
  INTEGRITY_MODE,
  MANIFEST_NAME,
  PEER_VERIFICATION,
  PRODUCER_WORKFLOW,
  RUNTIME_FILE_NAMES,
  inspectElf,
  linuxContentPinErrors,
  linuxNativeManifestErrors,
  resolveLinuxNativeCoreArtifacts,
};
