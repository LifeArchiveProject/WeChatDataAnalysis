"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const {
  extractCodeSigningLeafCertificate,
} = require("./macos-codesign-certificates.cjs");

const ARTIFACT_NAME = "wechatdb-native-macos-arm64-production";
const WORKFLOW = ".github/workflows/macos-native-production.yml";
const BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const REVISION_PATTERN = /^[0-9a-f]{40}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const IDENTIFIER_PATTERN = /^[A-Za-z0-9.-]+$/;
const NON_PRODUCTION_BUILD_ID_PATTERN =
  /(^|[._-])(dev|debug|test|local|snapshot|staging)([._-]|$)/i;
const CHECKSUM_FILE_NAMES = Object.freeze([
  "Test-MacosNativeProductionArtifact.py",
  "libwechatdb_client.dylib",
  "macos_native_signing.json",
  "wda-macos-native-consumer-contract.json",
  "wechatdb_broker",
  "wechatdb_native_build.json",
]);
const ARTIFACT_FILE_NAMES = Object.freeze([
  ...CHECKSUM_FILE_NAMES,
  "SHA256SUMS.txt",
  "provenance.json",
]);
const RUNTIME_FILE_NAMES = Object.freeze([
  "libwechatdb_client.dylib",
  "wechatdb_broker",
  "wechatdb_native_build.json",
]);

function exactKeys(value, expected) {
  if (!value || Array.isArray(value) || typeof value !== "object") return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((name, index) => name === wanted[index]);
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function readJson(filePath, label, maximum = 128 * 1024) {
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
  if (!value || (pattern && !pattern.test(value))) throw new Error(`Missing or invalid ${name}`);
  return value;
}

function nonZeroPin(env, name) {
  const value = requiredEnv(env, name, SHA256_PATTERN);
  if (/^0{64}$/.test(value)) throw new Error(`${name} must be a non-zero lowercase SHA-256 digest`);
  return value;
}

function parseChecksums(filePath) {
  const records = new Map();
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    const match = /^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$/.exec(line);
    if (!match || records.has(match[2])) throw new Error("SHA256SUMS.txt has an invalid record");
    records.set(match[2], match[1]);
  }
  return records;
}

function macosNativeManifestErrors(manifest, { nowUnix = Math.floor(Date.now() / 1000) } = {}) {
  const errors = [];
  const fields = [
    "schemaVersion", "platform", "distributionMode", "buildId", "buildIssuedAtUnix",
    "buildExpiresAtUnix", "developmentBuild", "offlineBootstrapFeatureBits",
    "offlineExportSealFormat", "codeSignatureEnforced", "rootPublicKeyCompiled",
    "testHooksEnabled", "stagingPinnedSignerTrust", "macosSigningMode",
    "macosSignerTrustMode", "macosPrivatePkiLeafRevocation",
    "macosClientSigningIdentifier", "macosBrokerSigningIdentifier",
    "macosHostSigningIdentifier", "macosClientSignerSha256",
    "macosBrokerSignerSha256", "macosHostSignerSha256", "macosPrivateRootSha256",
    "securityNoticeId", "securityNoticeSha256", "securityCheckpointSetId",
    "securityCheckpointCount", "securityCheckpointSetSha256",
  ];
  if (!exactKeys(manifest, fields)) errors.push("manifest fields must match macOS schema v3 exactly");
  if (manifest?.schemaVersion !== 3) errors.push("schemaVersion must equal 3");
  if (manifest?.platform !== "macos") errors.push("platform must equal macos");
  if (manifest?.distributionMode !== "public") errors.push("distributionMode must equal public");
  if (!BUILD_ID_PATTERN.test(String(manifest?.buildId || "")) ||
      NON_PRODUCTION_BUILD_ID_PATTERN.test(String(manifest?.buildId || ""))) {
    errors.push("buildId must be an immutable production identity");
  }
  const issued = manifest?.buildIssuedAtUnix;
  const expires = manifest?.buildExpiresAtUnix;
  if (!Number.isSafeInteger(issued) || issued <= 0 || !Number.isSafeInteger(expires) ||
      expires !== issued + BUILD_LIFETIME_SECONDS) {
    errors.push("build validity window must equal exactly 45 days");
  } else if (!Number.isSafeInteger(nowUnix) || nowUnix < 0 || nowUnix >= expires) {
    errors.push("build has reached its fixed expiration time");
  }
  if (manifest?.developmentBuild !== false || manifest?.offlineBootstrapFeatureBits !== 3 ||
      manifest?.offlineExportSealFormat !== "WES2" || manifest?.codeSignatureEnforced !== true ||
      manifest?.rootPublicKeyCompiled !== true || manifest?.testHooksEnabled !== false ||
      manifest?.stagingPinnedSignerTrust !== false) {
    errors.push("native production security fields do not match policy");
  }
  if (manifest?.macosSigningMode !== "self-signed" ||
      manifest?.macosSignerTrustMode !== "private-pki" ||
      manifest?.macosPrivatePkiLeafRevocation !== "build-and-lease-only") {
    errors.push("macOS private-PKI policy mismatch");
  }
  const identifiers = [
    manifest?.macosClientSigningIdentifier,
    manifest?.macosBrokerSigningIdentifier,
    manifest?.macosHostSigningIdentifier,
  ];
  if (identifiers.some((value) => !IDENTIFIER_PATTERN.test(String(value || ""))) ||
      new Set(identifiers).size !== 3) {
    errors.push("macOS signing identifiers must be valid and distinct");
  }
  const pins = [
    manifest?.macosClientSignerSha256,
    manifest?.macosBrokerSignerSha256,
    manifest?.macosHostSignerSha256,
    manifest?.macosPrivateRootSha256,
  ];
  if (pins.some((value) => !SHA256_PATTERN.test(String(value || "")) || /^0{64}$/.test(value)) ||
      new Set(pins).size !== 4) {
    errors.push("macOS client, broker, host, and root pins must be non-zero and distinct");
  }
  if (manifest?.securityNoticeId !== "WCE-AUTOMATED-ANALYSIS-NOTICE-V2" ||
      !SHA256_PATTERN.test(String(manifest?.securityNoticeSha256 || "")) ||
      manifest?.securityCheckpointSetId !== "WCE-AI-CHECKPOINT-SET-V3" ||
      manifest?.securityCheckpointCount !== 7 ||
      !SHA256_PATTERN.test(String(manifest?.securityCheckpointSetSha256 || ""))) {
    errors.push("native security checkpoint contract mismatch");
  }
  return errors;
}

function defaultBinaryInspector(filePath) {
  if (process.platform !== "darwin") {
    throw new Error("macOS native-core signature inspection requires a macOS build host");
  }
  const verify = spawnSync("/usr/bin/codesign", ["--verify", "--strict", "--verbose=2", filePath], {
    encoding: "utf8",
  });
  if ((verify.status ?? 1) !== 0) throw new Error(`codesign verification failed: ${filePath}`);
  const details = spawnSync("/usr/bin/codesign", ["-d", "--verbose=4", filePath], {
    encoding: "utf8",
  });
  const detailText = `${details.stdout || ""}\n${details.stderr || ""}`;
  const identifier = /^Identifier=([^\r\n]+)$/m.exec(detailText)?.[1]?.trim();
  if ((details.status ?? 1) !== 0 || !identifier || !detailText.includes("Runtime Version=")) {
    throw new Error(`code-signing metadata inspection failed: ${filePath}`);
  }
  const certificate = new crypto.X509Certificate(extractCodeSigningLeafCertificate(filePath));
  const leafSha256 = certificate.fingerprint256.replaceAll(":", "").toLowerCase();
  const lipo = spawnSync("/usr/bin/lipo", ["-archs", filePath], { encoding: "utf8" });
  if ((lipo.status ?? 1) !== 0) throw new Error(`architecture inspection failed: ${filePath}`);
  return {
    identifier,
    leafSha256,
    architectures: String(lipo.stdout || "").trim().split(/\s+/).filter(Boolean),
  };
}

function resolveMacosNativeCoreArtifacts({
  env = process.env,
  platform = process.platform,
  nowUnix = Math.floor(Date.now() / 1000),
  binaryInspector = defaultBinaryInspector,
} = {}) {
  if (platform !== "darwin") {
    throw new Error(`macOS native-core artifacts cannot be resolved on platform: ${platform}`);
  }
  const artifactDir = path.resolve(requiredEnv(env, "WCE_NATIVE_CORE_ARTIFACT_DIR"));
  const stat = fs.statSync(artifactDir);
  if (!stat.isDirectory()) throw new Error(`WCE_NATIVE_CORE_ARTIFACT_DIR is not a directory: ${artifactDir}`);
  const entries = fs.readdirSync(artifactDir, { withFileTypes: true });
  const files = entries.filter((entry) => entry.isFile()).map((entry) => entry.name).sort();
  const wanted = [...ARTIFACT_FILE_NAMES].sort();
  if (entries.some((entry) => !entry.isFile()) || JSON.stringify(files) !== JSON.stringify(wanted)) {
    throw new Error("macOS native-core artifact file allowlist mismatch");
  }

  const repository = requiredEnv(
    env, "WCE_NATIVE_CORE_ARTIFACT_REPOSITORY", /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
  );
  const runId = Number(requiredEnv(env, "WCE_NATIVE_CORE_ARTIFACT_RUN_ID", /^[1-9][0-9]*$/));
  const sourceRevision = requiredEnv(env, "WCE_NATIVE_CORE_SOURCE_REVISION", REVISION_PATTERN);
  const buildId = requiredEnv(env, "WCE_NATIVE_CORE_BUILD_ID", BUILD_ID_PATTERN);
  const clientPin = nonZeroPin(env, "WCE_NATIVE_CORE_CLIENT_SIGNER_SHA256");
  const brokerPin = nonZeroPin(env, "WCE_NATIVE_CORE_BROKER_SIGNER_SHA256");
  const hostPin = nonZeroPin(env, "WCE_NATIVE_CORE_HOST_SIGNER_SHA256");
  const rootPin = nonZeroPin(env, "WCE_NATIVE_CORE_PRIVATE_ROOT_SHA256");
  if (new Set([clientPin, brokerPin, hostPin, rootPin]).size !== 4) {
    throw new Error("macOS native-core role and root pins must be distinct");
  }
  const clientIdentifier = requiredEnv(env, "WCE_NATIVE_CORE_CLIENT_SIGNING_IDENTIFIER", IDENTIFIER_PATTERN);
  const brokerIdentifier = requiredEnv(env, "WCE_NATIVE_CORE_BROKER_SIGNING_IDENTIFIER", IDENTIFIER_PATTERN);
  const hostIdentifier = requiredEnv(env, "WCE_NATIVE_CORE_HOST_SIGNING_IDENTIFIER", IDENTIFIER_PATTERN);
  if (new Set([clientIdentifier, brokerIdentifier, hostIdentifier]).size !== 3) {
    throw new Error("macOS native-core signing identifiers must be distinct");
  }

  const manifestPath = path.join(artifactDir, "wechatdb_native_build.json");
  const manifest = readJson(manifestPath, "macOS native-core manifest", 16 * 1024);
  const manifestErrors = macosNativeManifestErrors(manifest, { nowUnix });
  if (manifestErrors.length) throw new Error(`Refusing macOS native-core artifact: ${manifestErrors.join("; ")}`);
  if (manifest.buildId !== buildId || manifest.macosClientSignerSha256 !== clientPin ||
      manifest.macosBrokerSignerSha256 !== brokerPin || manifest.macosHostSignerSha256 !== hostPin ||
      manifest.macosPrivateRootSha256 !== rootPin ||
      manifest.macosClientSigningIdentifier !== clientIdentifier ||
      manifest.macosBrokerSigningIdentifier !== brokerIdentifier ||
      manifest.macosHostSigningIdentifier !== hostIdentifier) {
    throw new Error("macOS native-core manifest does not match protected environment pins");
  }

  const signingPath = path.join(artifactDir, "macos_native_signing.json");
  const signing = readJson(signingPath, "macOS native-core signing metadata");
  const roleKeys = ["identifier", "leafCertificateSha256", "designatedRequirement"];
  if (!exactKeys(signing, [
    "schemaVersion", "mode", "privateRootCertificateSha256", "client", "broker",
    "hardenedRuntime", "timestamped", "notarized",
  ]) || signing.schemaVersion !== 1 || signing.mode !== "self-signed" ||
      signing.privateRootCertificateSha256 !== rootPin || signing.hardenedRuntime !== true ||
      signing.timestamped !== false || signing.notarized !== false ||
      !exactKeys(signing.client, roleKeys) || !exactKeys(signing.broker, roleKeys) ||
      signing.client.identifier !== clientIdentifier || signing.client.leafCertificateSha256 !== clientPin ||
      signing.broker.identifier !== brokerIdentifier || signing.broker.leafCertificateSha256 !== brokerPin) {
    throw new Error("macOS native-core signing metadata does not match protected pins");
  }

  const checksumsPath = path.join(artifactDir, "SHA256SUMS.txt");
  const checksums = parseChecksums(checksumsPath);
  if (checksums.size !== CHECKSUM_FILE_NAMES.length ||
      CHECKSUM_FILE_NAMES.some((name) => checksums.get(name) !== sha256File(path.join(artifactDir, name)))) {
    throw new Error("macOS native-core checksum set does not match the artifact allowlist");
  }

  const provenance = readJson(path.join(artifactDir, "provenance.json"), "macOS native-core provenance");
  if (!exactKeys(provenance, [
    "schemaVersion", "artifactName", "producer", "workflow", "repository", "runId",
    "runAttempt", "sourceRevision", "build", "signers", "manifestSha256",
    "signingMetadataSha256", "checksumsSha256", "artifacts",
  ]) || provenance.schemaVersion !== 1 || provenance.artifactName !== ARTIFACT_NAME ||
      provenance.producer !== "github-actions" || provenance.workflow !== WORKFLOW ||
      provenance.repository !== repository || provenance.runId !== runId ||
      !Number.isSafeInteger(provenance.runAttempt) || provenance.runAttempt <= 0 ||
      provenance.sourceRevision !== sourceRevision || provenance.build?.id !== buildId ||
      provenance.build?.platform !== "macos" || provenance.build?.architecture !== "arm64" ||
      provenance.manifestSha256 !== sha256File(manifestPath) ||
      provenance.signingMetadataSha256 !== sha256File(signingPath) ||
      provenance.checksumsSha256 !== sha256File(checksumsPath) ||
      provenance.signers?.client?.identifier !== clientIdentifier ||
      provenance.signers?.client?.leafCertificateSha256 !== clientPin ||
      provenance.signers?.broker?.identifier !== brokerIdentifier ||
      provenance.signers?.broker?.leafCertificateSha256 !== brokerPin ||
      provenance.signers?.host?.identifier !== hostIdentifier ||
      provenance.signers?.host?.leafCertificateSha256 !== hostPin ||
      provenance.signers?.privateRootCertificateSha256 !== rootPin ||
      provenance.signers?.timestamped !== false || provenance.signers?.notarized !== false) {
    throw new Error("macOS native-core provenance does not match exact producer pins");
  }
  const expectedInventory = CHECKSUM_FILE_NAMES.map((name) => ({
    path: name,
    sha256: sha256File(path.join(artifactDir, name)),
    size: fs.statSync(path.join(artifactDir, name)).size,
  }));
  if (JSON.stringify(provenance.artifacts) !== JSON.stringify(expectedInventory)) {
    throw new Error("macOS native-core provenance artifact inventory mismatch");
  }

  const clientInspection = binaryInspector(path.join(artifactDir, "libwechatdb_client.dylib"));
  const brokerInspection = binaryInspector(path.join(artifactDir, "wechatdb_broker"));
  const clientArchitectures = clientInspection.architectures instanceof Set
    ? [...clientInspection.architectures]
    : [...(clientInspection.architectures || [])];
  const brokerArchitectures = brokerInspection.architectures instanceof Set
    ? [...brokerInspection.architectures]
    : [...(brokerInspection.architectures || [])];
  if (clientInspection.identifier !== clientIdentifier || clientInspection.leafSha256 !== clientPin ||
      JSON.stringify(clientArchitectures) !== JSON.stringify(["arm64"]) ||
      brokerInspection.identifier !== brokerIdentifier || brokerInspection.leafSha256 !== brokerPin ||
      JSON.stringify(brokerArchitectures) !== JSON.stringify(["arm64"])) {
    throw new Error("macOS native-core signatures or architectures do not match protected pins");
  }
  return {
    artifactDir,
    manifest,
    provenance,
    signing,
    repository,
    runId,
    sourceRevision,
    buildId,
    clientPin,
    brokerPin,
    hostPin,
    rootPin,
    names: [...RUNTIME_FILE_NAMES],
    required: true,
  };
}

module.exports = {
  ARTIFACT_FILE_NAMES,
  ARTIFACT_NAME,
  BUILD_LIFETIME_SECONDS,
  CHECKSUM_FILE_NAMES,
  RUNTIME_FILE_NAMES,
  defaultBinaryInspector,
  macosNativeManifestErrors,
  resolveMacosNativeCoreArtifacts,
};
