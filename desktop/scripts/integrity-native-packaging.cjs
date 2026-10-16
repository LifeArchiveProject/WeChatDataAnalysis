"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const ARTIFACT_NAME = "wce-integrity-macos-arm64-production";
const BINARY_NAME = "libwce_integrity.dylib";
const MANIFEST_NAME = "wce_integrity_build.json";
const PROVENANCE_NAME = "provenance.json";
const CHECKSUMS_NAME = "SHA256SUMS.txt";
const ARTIFACT_FILE_NAMES = Object.freeze([
  BINARY_NAME,
  MANIFEST_NAME,
  PROVENANCE_NAME,
  CHECKSUMS_NAME,
]);
const CHECKSUM_FILE_NAMES = Object.freeze([BINARY_NAME, MANIFEST_NAME, PROVENANCE_NAME]);
const LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const SHA40_PATTERN = /^[0-9a-f]{40}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const NON_PRODUCTION_PATTERN = /(^|[._-])(dev|debug|test|local|snapshot|staging)([._-]|$)/i;

function exactKeys(value, keys) {
  return value && !Array.isArray(value) && typeof value === "object" &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort());
}

function requiredEnv(env, name, pattern) {
  const value = String(env[name] || "").trim();
  if (!value || (pattern && !pattern.test(value))) {
    throw new Error(`Missing or invalid ${name}.`);
  }
  return value;
}

function positiveSafeIntegerEnv(env, name) {
  const raw = requiredEnv(env, name, /^[1-9][0-9]*$/);
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error(`Invalid ${name}.`);
  return value;
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function readJson(filePath, label) {
  const stat = fs.statSync(filePath);
  if (!stat.isFile() || stat.size <= 0 || stat.size > 64 * 1024) {
    throw new Error(`${label} is missing or unexpectedly large.`);
  }
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return value;
}

function parseChecksums(filePath) {
  const records = new Map();
  const lines = fs.readFileSync(filePath, "ascii").trimEnd().split(/\r?\n/);
  for (const line of lines) {
    const match = /^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$/.exec(line);
    if (!match || records.has(match[2])) throw new Error("Integrity checksum manifest is malformed.");
    records.set(match[2], match[1]);
  }
  return records;
}

function artifactRecords(root, names) {
  return names.map((name) => {
    const filePath = path.join(root, name);
    return { path: name, sha256: sha256File(filePath), size: fs.statSync(filePath).size };
  });
}

function defaultBinaryInspector(filePath) {
  if (process.platform !== "darwin") {
    throw new Error("macOS integrity architecture inspection requires a macOS build host.");
  }
  const lipo = spawnSync("/usr/bin/lipo", ["-archs", filePath], { encoding: "utf8" });
  if ((lipo.status ?? 1) !== 0) throw new Error(`lipo inspection failed: ${filePath}`);
  const nm = spawnSync("/usr/bin/nm", ["-gU", filePath], { encoding: "utf8" });
  if ((nm.status ?? 1) !== 0) throw new Error(`symbol inspection failed: ${filePath}`);
  return {
    architectures: String(lipo.stdout || "").trim().split(/\s+/).filter(Boolean),
    hasPythonEntrypoint: String(nm.stdout || "").includes("_PyInit_wce_integrity"),
  };
}

function resolveIntegrityNativeArtifact({
  env = process.env,
  platform = process.platform,
  nowUnix = Math.floor(Date.now() / 1000),
  binaryInspector = defaultBinaryInspector,
} = {}) {
  if (platform !== "darwin") {
    throw new Error(`macOS integrity artifacts cannot be resolved on platform: ${platform}`);
  }
  const artifactDir = path.resolve(requiredEnv(env, "WCE_INTEGRITY_ARTIFACT_DIR"));
  const entries = fs.readdirSync(artifactDir, { withFileTypes: true });
  const actualNames = entries.filter((entry) => entry.isFile()).map((entry) => entry.name).sort();
  const expectedNames = [...ARTIFACT_FILE_NAMES].sort();
  if (entries.some((entry) => !entry.isFile()) ||
      JSON.stringify(actualNames) !== JSON.stringify(expectedNames)) {
    throw new Error("macOS integrity artifact file allowlist mismatch.");
  }

  const sourceRepository = requiredEnv(env, "WCE_INTEGRITY_ARTIFACT_REPOSITORY", REPOSITORY_PATTERN);
  const sourceRevision = requiredEnv(env, "WCE_INTEGRITY_SOURCE_REVISION", SHA40_PATTERN);
  const uiRepository = requiredEnv(env, "WCE_INTEGRITY_UI_SOURCE_REPOSITORY", REPOSITORY_PATTERN);
  const uiRevision = requiredEnv(env, "WCE_INTEGRITY_UI_SOURCE_REVISION", SHA40_PATTERN);
  const buildId = requiredEnv(env, "WCE_INTEGRITY_BUILD_ID", BUILD_ID_PATTERN);
  if (NON_PRODUCTION_PATTERN.test(buildId)) throw new Error("Integrity build ID is not production-grade.");
  const runId = positiveSafeIntegerEnv(env, "WCE_INTEGRITY_ARTIFACT_RUN_ID");
  const binaryPin = requiredEnv(env, "WCE_INTEGRITY_BINARY_SHA256", SHA256_PATTERN);
  if (/^0{64}$/.test(binaryPin)) throw new Error("Integrity binary hash pin must be non-zero.");

  const manifestPath = path.join(artifactDir, MANIFEST_NAME);
  const manifest = readJson(manifestPath, "Integrity manifest");
  const manifestKeys = [
    "schemaVersion", "artifactName", "platform", "architecture", "binaryFileName",
    "binarySha256", "binarySize", "pythonAbi", "buildId", "buildIssuedAtUnix",
    "buildExpiresAtUnix", "sourceRepository", "sourceRevision", "uiSourceRepository",
    "uiSourceRevision", "distributionMode", "development",
  ];
  const binaryPath = path.join(artifactDir, BINARY_NAME);
  const binaryHash = sha256File(binaryPath);
  const issuedAt = manifest.buildIssuedAtUnix;
  const expiresAt = manifest.buildExpiresAtUnix;
  if (!exactKeys(manifest, manifestKeys) || manifest.schemaVersion !== 1 ||
      manifest.artifactName !== ARTIFACT_NAME || manifest.platform !== "macos" ||
      manifest.architecture !== "arm64" || manifest.binaryFileName !== BINARY_NAME ||
      manifest.binarySha256 !== binaryHash || manifest.binarySha256 !== binaryPin ||
      manifest.binarySize !== fs.statSync(binaryPath).size || manifest.pythonAbi !== "abi3-py311" ||
      manifest.buildId !== buildId || !Number.isSafeInteger(issuedAt) ||
      !Number.isSafeInteger(expiresAt) || expiresAt - issuedAt !== LIFETIME_SECONDS ||
      issuedAt > nowUnix + 300 || expiresAt <= nowUnix ||
      manifest.sourceRepository !== sourceRepository || manifest.sourceRevision !== sourceRevision ||
      manifest.uiSourceRepository !== uiRepository || manifest.uiSourceRevision !== uiRevision ||
      manifest.distributionMode !== "public" || manifest.development !== false) {
    throw new Error("Integrity manifest does not match immutable production pins.");
  }

  const provenance = readJson(path.join(artifactDir, PROVENANCE_NAME), "Integrity provenance");
  const provenanceKeys = [
    "schemaVersion", "artifactName", "producer", "workflow", "repository", "ref",
    "runId", "runAttempt", "sourceRevision", "uiSource", "build", "manifestSha256",
    "artifacts",
  ];
  const expectedUiSource = { repository: uiRepository, revision: uiRevision };
  const expectedBuild = {
    id: buildId,
    issuedAtUnix: issuedAt,
    expiresAtUnix: expiresAt,
    platform: "macos",
    architecture: "arm64",
    pythonAbi: "abi3-py311",
    distributionMode: "public",
  };
  const expectedArtifacts = artifactRecords(artifactDir, [BINARY_NAME, MANIFEST_NAME]);
  if (!exactKeys(provenance, provenanceKeys) || provenance.schemaVersion !== 1 ||
      provenance.artifactName !== ARTIFACT_NAME || provenance.producer !== "github-actions" ||
      provenance.workflow !== "macos-integrity-production.yml" ||
      provenance.repository !== sourceRepository || provenance.ref !== "refs/heads/main" ||
      provenance.runId !== runId || !Number.isSafeInteger(provenance.runAttempt) ||
      provenance.runAttempt <= 0 || provenance.sourceRevision !== sourceRevision ||
      JSON.stringify(provenance.uiSource) !== JSON.stringify(expectedUiSource) ||
      JSON.stringify(provenance.build) !== JSON.stringify(expectedBuild) ||
      provenance.manifestSha256 !== sha256File(manifestPath) ||
      JSON.stringify(provenance.artifacts) !== JSON.stringify(expectedArtifacts)) {
    throw new Error("Integrity provenance does not match exact Producer pins.");
  }

  const checksums = parseChecksums(path.join(artifactDir, CHECKSUMS_NAME));
  if (checksums.size !== CHECKSUM_FILE_NAMES.length ||
      CHECKSUM_FILE_NAMES.some((name) => checksums.get(name) !== sha256File(path.join(artifactDir, name)))) {
    throw new Error("Integrity artifact checksum set does not match the allowlist.");
  }
  const inspection = binaryInspector(binaryPath);
  if (JSON.stringify([...(inspection.architectures || [])]) !== JSON.stringify(["arm64"]) ||
      inspection.hasPythonEntrypoint !== true) {
    throw new Error("Integrity binary architecture or Python entrypoint is invalid.");
  }
  return { artifactDir, binaryPath, manifest, provenance };
}

module.exports = {
  ARTIFACT_FILE_NAMES,
  ARTIFACT_NAME,
  BINARY_NAME,
  CHECKSUM_FILE_NAMES,
  resolveIntegrityNativeArtifact,
};
