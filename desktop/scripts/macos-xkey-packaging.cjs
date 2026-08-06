"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const {
  extractCodeSigningLeafCertificate,
} = require("./macos-codesign-certificates.cjs");

const repoRoot = path.resolve(__dirname, "..", "..");
const contract = Object.freeze(JSON.parse(fs.readFileSync(path.join(
  repoRoot,
  "src",
  "wechat_decrypt_tool",
  "resources",
  "macos_db_key_contract.json"
), "utf8")));
const BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const REVISION_PATTERN = /^[0-9a-f]{40}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/;
const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["", "0", "false", "no", "off"]);
const ARTIFACT_FILE_NAMES = Object.freeze([
  contract.helperFileName,
  contract.manifestFileName,
  contract.trustFileName,
  contract.checksumsFileName,
  contract.provenanceFileName,
  contract.thirdPartyNoticeFileName,
]);

function parseBooleanEnv(env, name) {
  const value = String(env[name] || "").trim().toLowerCase();
  if (TRUE_VALUES.has(value)) return true;
  if (FALSE_VALUES.has(value)) return false;
  throw new Error(`${name} must be a boolean value, received: ${env[name]}`);
}

function isCiEnvironment(env) {
  const value = String(env.CI || "").trim().toLowerCase();
  return value !== "" && !FALSE_VALUES.has(value);
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function readJson(filePath, label) {
  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile() || stat.size <= 0 || stat.size > 64 * 1024) throw new Error("invalid size");
    const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!value || Array.isArray(value) || typeof value !== "object") {
      throw new Error("root must be an object");
    }
    return value;
  } catch (error) {
    throw new Error(`Invalid ${label} at ${filePath}: ${error.message}`);
  }
}

function exactKeys(value, expected) {
  if (!value || Array.isArray(value) || typeof value !== "object") return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((name, index) => name === wanted[index]);
}

function macosXkeyManifestErrors(manifest, { nowUnix = Math.floor(Date.now() / 1000) } = {}) {
  const errors = [];
  if (!exactKeys(manifest, [
    "schemaVersion", "artifactType", "artifactName", "distributionMode", "platform",
    "architecture", "architectures", "appId", "sourceRevision", "build",
    "authorizationMode", "onlineRequired", "signing", "files",
  ])) errors.push("manifest fields must match schema v2 exactly");
  if (manifest?.schemaVersion !== 2) errors.push("schemaVersion must equal 2");
  if (manifest?.artifactType !== "wda-xkey-macos-key-capture") {
    errors.push("artifactType must equal wda-xkey-macos-key-capture");
  }
  if (manifest?.artifactName !== contract.artifactName) errors.push("artifactName mismatch");
  if (manifest?.distributionMode !== "public") errors.push("distributionMode must equal public");
  if (manifest?.platform !== "macos") errors.push("platform must equal macos");
  if (manifest?.architecture !== "universal2") errors.push("architecture must equal universal2");
  if (JSON.stringify(manifest?.architectures) !== JSON.stringify(["arm64", "x86_64"])) {
    errors.push("architectures must equal [arm64, x86_64]");
  }
  if (manifest?.appId !== contract.appId) errors.push(`appId must equal ${contract.appId}`);
  if (!REVISION_PATTERN.test(String(manifest?.sourceRevision || ""))) {
    errors.push("sourceRevision must be a lowercase 40-hex revision");
  }
  if (manifest?.authorizationMode !== "local-process-policy") {
    errors.push("authorizationMode must equal local-process-policy");
  }
  if (manifest?.onlineRequired !== false) errors.push("onlineRequired must equal false");

  const build = manifest?.build;
  if (!exactKeys(build, ["id", "issuedAtUnix", "expiresAtUnix", "validitySeconds", "development"])) {
    errors.push("build fields must match schema v2 exactly");
  }
  if (!BUILD_ID_PATTERN.test(String(build?.id || ""))) errors.push("build.id is invalid");
  if (
    !Number.isSafeInteger(build?.issuedAtUnix) || build.issuedAtUnix <= 0 ||
    !Number.isSafeInteger(build?.expiresAtUnix) ||
    build.expiresAtUnix !== build.issuedAtUnix + BUILD_LIFETIME_SECONDS ||
    build?.validitySeconds !== BUILD_LIFETIME_SECONDS
  ) {
    errors.push("build validity window must equal exactly 45 days");
  } else if (nowUnix >= build.expiresAtUnix) {
    errors.push("build has reached its fixed expiration time");
  }
  if (build?.development !== false) errors.push("build.development must be false");

  const signing = manifest?.signing;
  if (!exactKeys(signing, [
    "mode", "helperLeafCertificateSha256", "hostLeafCertificateSha256", "teamId",
    "hardenedRuntime", "timestamped", "notarized",
  ])) errors.push("signing fields must match schema v1 exactly");
  if (!new Set(["self-signed", "developer-id"]).has(signing?.mode)) {
    errors.push("signing.mode must equal self-signed or developer-id");
  }
  for (const field of ["helperLeafCertificateSha256", "hostLeafCertificateSha256"]) {
    if (!SHA256_PATTERN.test(String(signing?.[field] || "")) || /^0{64}$/.test(signing?.[field])) {
      errors.push(`signing.${field} must be a non-zero lowercase SHA-256 digest`);
    }
  }
  if (signing?.helperLeafCertificateSha256 === signing?.hostLeafCertificateSha256) {
    errors.push("helper and host signer pins must differ");
  }
  if (signing?.hardenedRuntime !== true || typeof signing?.timestamped !== "boolean" ||
      typeof signing?.notarized !== "boolean") errors.push("signing runtime metadata mismatch");
  if (signing?.mode === "self-signed" &&
      (signing?.teamId !== "" || signing?.timestamped !== false || signing?.notarized !== false)) {
    errors.push("self-signed artifacts cannot claim team, timestamp, or notarization");
  }
  if (signing?.mode === "developer-id" &&
      (!String(signing?.teamId || "").trim() || signing?.timestamped !== true)) {
    errors.push("Developer ID artifacts require teamId and timestamping");
  }

  const requiredFiles = [contract.helperFileName, contract.thirdPartyNoticeFileName];
  if (!exactKeys(manifest?.files, requiredFiles)) errors.push("files allowlist mismatch");
  for (const name of requiredFiles) {
    const metadata = manifest?.files?.[name];
    if (!exactKeys(metadata, ["sha256", "size"]) ||
        !SHA256_PATTERN.test(String(metadata?.sha256 || "")) ||
        !Number.isSafeInteger(metadata?.size) || metadata.size <= 0) {
      errors.push(`file metadata is invalid: ${name}`);
    }
  }
  return errors;
}

function parseChecksums(filePath) {
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean);
  const records = new Map();
  for (const line of lines) {
    const match = /^([0-9a-f]{64})  ([A-Za-z0-9._/-]+)$/.exec(line);
    if (!match || records.has(match[2])) throw new Error("SHA256SUMS.txt has an invalid record");
    records.set(match[2], match[1]);
  }
  return records;
}

function defaultBinaryInspector(helperPath) {
  if (process.platform !== "darwin") {
    throw new Error("macOS helper signature inspection requires a macOS build host");
  }
  const verify = spawnSync(
    "/usr/bin/codesign",
    ["--verify", "--strict", "--verbose=2", helperPath],
    { stdio: "ignore" }
  );
  if ((verify.status ?? 1) !== 0) throw new Error("helper codesign verification failed");
  const details = spawnSync("/usr/bin/codesign", ["-d", "--verbose=4", helperPath], {
    encoding: "utf8",
  });
  const detailText = `${details.stdout || ""}\n${details.stderr || ""}`;
  const identifier = /^Identifier=([^\r\n]+)$/m.exec(detailText)?.[1]?.trim();
  if ((details.status ?? 1) !== 0 || !identifier) throw new Error("helper identifier inspection failed");
  const certificate = new crypto.X509Certificate(
    extractCodeSigningLeafCertificate(helperPath)
  );
  const leafSha256 = certificate.fingerprint256.replaceAll(":", "").toLowerCase();
  const lipo = spawnSync("/usr/bin/lipo", ["-archs", helperPath], { encoding: "utf8" });
  if ((lipo.status ?? 1) !== 0) throw new Error("helper architecture inspection failed");
  return {
    identifier,
    leafSha256,
    architectures: new Set(String(lipo.stdout || "").trim().split(/\s+/).filter(Boolean)),
  };
}

function requiredEnv(env, name, pattern) {
  const value = String(env[name] || "").trim();
  if (!value || (pattern && !pattern.test(value))) throw new Error(`Missing or invalid ${name}`);
  return value;
}

function resolveMacosXkeyArtifacts({
  env = process.env,
  platform = process.platform,
  nowUnix = Math.floor(Date.now() / 1000),
  binaryInspector = defaultBinaryInspector,
} = {}) {
  if (platform !== "darwin") {
    if (String(env.WCE_MACOS_XKEY_ARTIFACT_DIR || "").trim()) {
      throw new Error(`macOS Xkey artifacts cannot be staged on platform: ${platform}`);
    }
    return { artifactDir: null, manifest: null, required: false, names: [...ARTIFACT_FILE_NAMES] };
  }
  const artifactDir = path.resolve(requiredEnv(env, "WCE_MACOS_XKEY_ARTIFACT_DIR"));
  const allowDevelopment = parseBooleanEnv(env, "WCE_MACOS_XKEY_ALLOW_DEVELOPMENT_ARTIFACTS");
  if (allowDevelopment && isCiEnvironment(env)) {
    throw new Error("WCE_MACOS_XKEY_ALLOW_DEVELOPMENT_ARTIFACTS is forbidden in CI");
  }
  if (!fs.statSync(artifactDir).isDirectory()) {
    throw new Error(`WCE_MACOS_XKEY_ARTIFACT_DIR is not a directory: ${artifactDir}`);
  }
  const missing = ARTIFACT_FILE_NAMES.filter((name) => !fs.existsSync(path.join(artifactDir, name)));
  if (missing.length) throw new Error(`Incomplete macOS Xkey artifact: missing ${missing.join(", ")}`);

  const manifestPath = path.join(artifactDir, contract.manifestFileName);
  const manifest = readJson(manifestPath, "macOS Xkey manifest");
  const manifestErrors = macosXkeyManifestErrors(manifest, { nowUnix });
  if (manifestErrors.length && !allowDevelopment) {
    throw new Error(`Refusing non-production macOS Xkey artifact: ${manifestErrors.join("; ")}`);
  }
  const repository = requiredEnv(env, "WCE_MACOS_XKEY_ARTIFACT_REPOSITORY", /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/);
  const runId = Number(requiredEnv(env, "WCE_MACOS_XKEY_ARTIFACT_RUN_ID", /^[1-9][0-9]*$/));
  const sourceRevision = requiredEnv(env, "WCE_MACOS_XKEY_SOURCE_REVISION", REVISION_PATTERN);
  const buildId = requiredEnv(env, "WCE_MACOS_XKEY_BUILD_ID", BUILD_ID_PATTERN);
  const helperSigner = requiredEnv(env, "WCE_MACOS_KEY_HELPER_SIGNER_SHA256", SHA256_PATTERN);
  const hostSigner = requiredEnv(env, "WCE_MACOS_WCDA_HOST_SIGNER_SHA256", SHA256_PATTERN);
  if (/^0{64}$/.test(helperSigner) || /^0{64}$/.test(hostSigner) || helperSigner === hostSigner) {
    throw new Error("macOS signer pins must be distinct non-zero SHA-256 digests");
  }

  const trustPath = path.join(artifactDir, contract.trustFileName);
  const trust = readJson(trustPath, "macOS Xkey trust");
  if (!exactKeys(trust, [
    "schemaVersion", "artifactName", "sourceRevision", "buildId", "appId",
    "producerRepository", "producerWorkflowRunId", "helperIdentifier",
    "helperLeafCertificateSha256", "hostIdentifier", "hostLeafCertificateSha256",
    "signingMode", "manifestSha256",
  ]) || trust.schemaVersion !== 1 || trust.artifactName !== contract.artifactName ||
      trust.sourceRevision !== sourceRevision || trust.buildId !== buildId ||
      trust.appId !== contract.appId || trust.producerRepository !== repository ||
      trust.producerWorkflowRunId !== runId || trust.helperIdentifier !== contract.bundleId ||
      trust.helperLeafCertificateSha256 !== helperSigner ||
      trust.hostIdentifier !== contract.hostSigningIdentifier ||
      trust.hostLeafCertificateSha256 !== hostSigner ||
      trust.signingMode !== manifest.signing.mode ||
      trust.manifestSha256 !== sha256File(manifestPath)) {
    throw new Error("macOS Xkey trust does not match the exact producer and environment pins");
  }
  if (manifest.build.id !== buildId || manifest.sourceRevision !== sourceRevision ||
      manifest.signing.helperLeafCertificateSha256 !== helperSigner ||
      manifest.signing.hostLeafCertificateSha256 !== hostSigner) {
    throw new Error("macOS Xkey manifest does not match the protected environment pins");
  }

  const provenance = readJson(path.join(artifactDir, contract.provenanceFileName), "macOS Xkey provenance");
  if (!exactKeys(provenance, [
    "schemaVersion", "producer", "workflow", "repository", "runId", "runAttempt",
    "sourceRevision", "buildId", "artifactName", "manifestSha256", "trustSha256",
    "checksumsSha256",
  ]) || provenance.schemaVersion !== 1 || provenance.producer !== "github-actions" ||
      provenance.workflow !== ".github/workflows/macos-key-capture-production.yml" ||
      provenance.artifactName !== contract.artifactName || provenance.repository !== repository ||
      provenance.runId !== runId || !Number.isSafeInteger(provenance.runAttempt) ||
      provenance.runAttempt <= 0 || provenance.sourceRevision !== sourceRevision ||
      provenance.buildId !== buildId || provenance.manifestSha256 !== sha256File(manifestPath) ||
      provenance.trustSha256 !== sha256File(trustPath) ||
      provenance.checksumsSha256 !== sha256File(path.join(artifactDir, contract.checksumsFileName))) {
    throw new Error("macOS Xkey provenance does not match the exact producer pins");
  }

  const checksums = parseChecksums(path.join(artifactDir, contract.checksumsFileName));
  const checksumNames = [
    contract.helperFileName,
    contract.thirdPartyNoticeFileName,
    contract.manifestFileName,
    contract.trustFileName,
  ];
  if (checksums.size !== checksumNames.length ||
      checksumNames.some((name) => checksums.get(name) !== sha256File(path.join(artifactDir, name)))) {
    throw new Error("macOS Xkey checksum set does not match the artifact allowlist");
  }
  for (const name of [contract.helperFileName, contract.thirdPartyNoticeFileName]) {
    const metadata = manifest.files[name];
    const filePath = path.join(artifactDir, name);
    if (sha256File(filePath) !== metadata.sha256 || fs.statSync(filePath).size !== metadata.size) {
      throw new Error(`macOS Xkey hash/size does not match manifest: ${name}`);
    }
  }
  const helperPath = path.join(artifactDir, contract.helperFileName);
  const inspection = binaryInspector(helperPath);
  const architectures = inspection.architectures instanceof Set
    ? inspection.architectures
    : new Set(inspection.architectures || []);
  if (inspection.identifier !== contract.bundleId || inspection.leafSha256 !== helperSigner ||
      !contract.requiredArchitectures.every((arch) => architectures.has(arch))) {
    throw new Error("macOS Xkey helper signature or Universal2 architecture does not match pins");
  }
  return {
    artifactDir, allowDevelopment, manifest, manifestPath, trust, repository, runId,
    sourceRevision, buildId, helperSigner, hostSigner, names: [...ARTIFACT_FILE_NAMES], required: true,
  };
}

function stageMacosXkeyArtifacts({
  env = process.env,
  platform = process.platform,
  destinationNativeDir,
  logger = console,
  binaryInspector = defaultBinaryInspector,
  nowUnix,
} = {}) {
  const resolved = resolveMacosXkeyArtifacts({ env, platform, binaryInspector, nowUnix });
  if (!resolved.artifactDir) return { ...resolved, staged: false };
  if (!destinationNativeDir) throw new Error("destinationNativeDir is required");
  const destination = path.join(destinationNativeDir, ...String(contract.bundleRelativePath).split("/"));
  fs.rmSync(destination, { recursive: true, force: true });
  fs.mkdirSync(destination, { recursive: true });
  for (const name of resolved.names) {
    const target = path.join(destination, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(resolved.artifactDir, name), target);
  }
  fs.chmodSync(path.join(destination, contract.helperFileName), 0o755);
  logger.log(`Staged production macOS Xkey build: ${resolved.buildId}`);
  return { ...resolved, destination, staged: true };
}

module.exports = {
  ARTIFACT_FILE_NAMES,
  BUILD_LIFETIME_SECONDS,
  contract,
  defaultBinaryInspector,
  macosXkeyManifestErrors,
  resolveMacosXkeyArtifacts,
  stageMacosXkeyArtifacts,
};
