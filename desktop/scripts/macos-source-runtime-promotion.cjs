"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const PROFILE = "macos-source-public";
const ASSET_NAME = "wechatdataanalysis-macos-source-runtime-arm64-v1.tar.gz";
const MANIFEST_ASSET_NAME = "wechatdataanalysis-macos-source-runtime-arm64-v1.manifest.json";
const CHECKSUMS_ASSET_NAME = "SHA256SUMS-macos-source-runtime.txt";
const LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const SHA40_PATTERN = /^[0-9a-f]{40}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const RELEASE_TAG_PATTERN = /^macos-source-runtime-[A-Za-z0-9._-]{8,96}$/;

const PAYLOAD_FILES = Object.freeze([
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

function readJson(file, label, maximum = 128 * 1024) {
  const stat = fs.lstatSync(file);
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`${label} is missing, unsafe, or oversized.`);
  }
  const value = JSON.parse(fs.readFileSync(file, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return value;
}

function requireString(value, pattern, label) {
  const text = String(value || "");
  if (!pattern.test(text)) throw new Error(`${label} is invalid.`);
  return text;
}

function requireBuildWindow(issuedAt, expiresAt, nowUnix, label) {
  if (
    !Number.isSafeInteger(issuedAt) ||
    !Number.isSafeInteger(expiresAt) ||
    issuedAt <= 0 ||
    expiresAt !== issuedAt + LIFETIME_SECONDS ||
    nowUnix < issuedAt - 300 ||
    nowUnix >= expiresAt
  ) {
    throw new Error(`${label} does not have an active exact 45-day build window.`);
  }
  return expiresAt;
}

function requireRegularFile(file, label, maximum = 1024 * 1024 * 1024) {
  const stat = fs.lstatSync(file);
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`${label} is missing, unsafe, empty, or oversized.`);
  }
  return stat;
}

function copyRegular(source, destination, executable) {
  const stat = requireRegularFile(source, path.basename(source));
  fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
  fs.copyFileSync(source, destination, fs.constants.COPYFILE_EXCL);
  fs.chmodSync(destination, executable ? 0o755 : 0o644);
  if (fs.statSync(destination).size !== stat.size || sha256File(destination) !== sha256File(source)) {
    throw new Error(`Source runtime copy verification failed: ${destination}`);
  }
}

function validateComponentProfiles({ coreDir, xkeyDir, integrityDir, nowUnix }) {
  const coreManifest = readJson(
    path.join(coreDir, "wechatdb_native_build.json"),
    "source-public native-core manifest",
    16 * 1024
  );
  const coreProvenance = readJson(path.join(coreDir, "provenance.json"), "native-core provenance");
  if (
    coreManifest.schemaVersion !== 3 ||
    coreManifest.platform !== "macos" ||
    coreManifest.sourceRuntime !== true ||
    coreManifest.macosHostVerification !== "same-user-direct-parent" ||
    coreManifest.developmentBuild !== false ||
    coreManifest.codeSignatureEnforced !== true ||
    coreManifest.rootPublicKeyCompiled !== true ||
    coreManifest.testHooksEnabled !== false ||
    coreManifest.offlineBootstrapFeatureBits !== 3 ||
    coreManifest.offlineExportSealFormat !== "WES2" ||
    coreManifest.securityCheckpointSetId !== "WCE-AI-CHECKPOINT-SET-V3" ||
    coreManifest.securityCheckpointCount !== 7 ||
    coreProvenance.artifactName !== "wechatdb-native-macos-arm64-source-public" ||
    coreProvenance.build?.sourceRuntime !== true ||
    coreProvenance.build?.macosHostVerification !== "same-user-direct-parent"
  ) {
    throw new Error("Native-core artifact is not the exact restricted source-public profile.");
  }
  const coreBuildId = requireString(coreManifest.buildId, BUILD_ID_PATTERN, "native-core build ID");
  const coreSourceRevision = requireString(
    coreProvenance.sourceRevision,
    SHA40_PATTERN,
    "native-core source revision"
  );
  if (coreProvenance.build?.id !== coreBuildId) {
    throw new Error("Native-core manifest and provenance build IDs differ.");
  }
  const coreExpiry = requireBuildWindow(
    coreManifest.buildIssuedAtUnix,
    coreManifest.buildExpiresAtUnix,
    nowUnix,
    "native-core"
  );

  const xkeyManifest = readJson(path.join(xkeyDir, "wda_xkey_build.json"), "source-public XKey manifest");
  const xkeyProvenance = readJson(path.join(xkeyDir, "provenance.json"), "XKey provenance");
  if (
    xkeyManifest.schemaVersion !== 1 ||
    xkeyManifest.artifactName !== "wda-xkey-macos-universal-source-public" ||
    xkeyManifest.sourceRuntime !== true ||
    xkeyManifest.hostVerification !== "same-user-direct-parent" ||
    xkeyManifest.build?.development !== false ||
    xkeyManifest.authorizationMode !== "embedded-private" ||
    xkeyManifest.onlineRequired !== true ||
    xkeyProvenance.artifactName !== xkeyManifest.artifactName
  ) {
    throw new Error("XKey artifact is not the exact restricted source-public profile.");
  }
  const xkeyBuildId = requireString(xkeyManifest.build?.id, BUILD_ID_PATTERN, "XKey build ID");
  const xkeySourceRevision = requireString(
    xkeyManifest.sourceRevision,
    SHA40_PATTERN,
    "XKey source revision"
  );
  if (xkeyProvenance.sourceRevision !== xkeySourceRevision || xkeyProvenance.buildId !== xkeyBuildId) {
    throw new Error("XKey manifest and provenance coordinates differ.");
  }
  const xkeyExpiry = requireBuildWindow(
    xkeyManifest.build?.issuedAtUnix,
    xkeyManifest.build?.expiresAtUnix,
    nowUnix,
    "XKey"
  );

  const integrityManifest = readJson(
    path.join(integrityDir, "wce_integrity_build.json"),
    "integrity manifest"
  );
  const integrityProvenance = readJson(path.join(integrityDir, "provenance.json"), "integrity provenance");
  if (
    integrityManifest.schemaVersion !== 1 ||
    integrityManifest.artifactName !== "wce-integrity-macos-arm64-production" ||
    integrityManifest.platform !== "macos" ||
    integrityManifest.architecture !== "arm64" ||
    integrityManifest.development !== false ||
    integrityManifest.distributionMode !== "public" ||
    integrityProvenance.artifactName !== integrityManifest.artifactName
  ) {
    throw new Error("Integrity artifact is not the exact production profile.");
  }
  const integrityBuildId = requireString(
    integrityManifest.buildId,
    BUILD_ID_PATTERN,
    "integrity build ID"
  );
  const integritySourceRevision = requireString(
    integrityManifest.sourceRevision,
    SHA40_PATTERN,
    "integrity source revision"
  );
  const integrityExpiry = requireBuildWindow(
    integrityManifest.buildIssuedAtUnix,
    integrityManifest.buildExpiresAtUnix,
    nowUnix,
    "integrity"
  );
  return {
    core: {
      artifactName: coreProvenance.artifactName,
      buildId: coreBuildId,
      sourceRevision: coreSourceRevision,
      producerRunId: coreProvenance.runId,
      expiresAtUnix: coreExpiry,
    },
    xkey: {
      artifactName: xkeyManifest.artifactName,
      buildId: xkeyBuildId,
      sourceRevision: xkeySourceRevision,
      producerRunId: xkeyProvenance.runId,
      expiresAtUnix: xkeyExpiry,
    },
    integrity: {
      artifactName: integrityManifest.artifactName,
      buildId: integrityBuildId,
      sourceRevision: integritySourceRevision,
      producerRunId: integrityProvenance.runId,
      expiresAtUnix: integrityExpiry,
    },
  };
}

function stageSourceRuntimeBundle({
  coreDir,
  xkeyDir,
  integrityDir,
  stageDir,
  releaseTag,
  nowUnix = Math.floor(Date.now() / 1000),
}) {
  requireString(releaseTag, RELEASE_TAG_PATTERN, "source-runtime release tag");
  if (!Number.isSafeInteger(nowUnix) || nowUnix <= 0) throw new Error("nowUnix is invalid.");
  const components = validateComponentProfiles({ coreDir, xkeyDir, integrityDir, nowUnix });
  if (fs.existsSync(stageDir)) throw new Error("Source-runtime stage directory must not exist.");
  fs.mkdirSync(stageDir, { recursive: true, mode: 0o700 });

  const sources = new Map([
    ["native-core/libwechatdb_client.dylib", path.join(coreDir, "libwechatdb_client.dylib")],
    ["native-core/wechatdb_broker", path.join(coreDir, "wechatdb_broker")],
    ["native-core/wechatdb_native_build.json", path.join(coreDir, "wechatdb_native_build.json")],
    ["db-key/SHA256SUMS.txt", path.join(xkeyDir, "SHA256SUMS.txt")],
    ["db-key/THIRD_PARTY_NOTICES/FRIDA-COPYING.txt", path.join(xkeyDir, "THIRD_PARTY_NOTICES", "FRIDA-COPYING.txt")],
    ["db-key/provenance.json", path.join(xkeyDir, "provenance.json")],
    ["db-key/wda_xkey_build.json", path.join(xkeyDir, "wda_xkey_build.json")],
    ["db-key/wda_xkey_helper", path.join(xkeyDir, "wda_xkey_helper")],
    ["db-key/wda_xkey_trust.json", path.join(xkeyDir, "wda_xkey_trust.json")],
    ["integrity/libwce_integrity.dylib", path.join(integrityDir, "libwce_integrity.dylib")],
  ]);
  for (const [relative, executable] of PAYLOAD_FILES) {
    copyRegular(sources.get(relative), path.join(stageDir, ...relative.split("/")), executable);
  }

  const files = {};
  for (const [relative, executable] of PAYLOAD_FILES) {
    const file = path.join(stageDir, ...relative.split("/"));
    files[relative] = {
      sha256: sha256File(file),
      size: fs.statSync(file).size,
      executable,
    };
  }
  const expiresAtUnix = Math.min(
    components.core.expiresAtUnix,
    components.xkey.expiresAtUnix,
    components.integrity.expiresAtUnix
  );
  const manifest = {
    schemaVersion: 1,
    profile: PROFILE,
    platform: "darwin",
    architecture: "arm64",
    releaseTag,
    createdAtUnix: nowUnix,
    expiresAtUnix,
    components: {
      nativeCore: { ...components.core, path: "native-core" },
      databaseKey: { ...components.xkey, path: "db-key" },
      exportIntegrity: { ...components.integrity, path: "integrity" },
    },
    files,
  };
  const manifestPath = path.join(stageDir, "runtime-manifest.json");
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o644,
    flag: "wx",
  });
  return { components, expiresAtUnix, manifest, manifestPath };
}

function createArchive({ stageDir, outputDir, spawnSyncImpl = spawnSync }) {
  fs.mkdirSync(outputDir, { recursive: true, mode: 0o700 });
  const archivePath = path.join(outputDir, ASSET_NAME);
  const result = spawnSyncImpl("/usr/bin/tar", ["-czf", archivePath, "-C", stageDir, "."], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result?.error || result?.status !== 0) {
    throw new Error(`Cannot create source-runtime archive: ${result?.stderr || result?.error?.message || "tar failed"}`);
  }
  requireRegularFile(archivePath, ASSET_NAME);
  return archivePath;
}

function main(env = process.env) {
  const coreDir = path.resolve(String(env.WCE_SOURCE_PUBLIC_NATIVE_CORE_DIR || ""));
  const xkeyDir = path.resolve(String(env.WCE_SOURCE_PUBLIC_XKEY_DIR || ""));
  const integrityDir = path.resolve(String(env.WCE_INTEGRITY_ARTIFACT_DIR || ""));
  const outputDir = path.resolve(String(env.WCE_SOURCE_RUNTIME_OUTPUT_DIR || ""));
  const releaseTag = String(env.WCE_SOURCE_RUNTIME_RELEASE_TAG || "").trim();
  const stageDir = path.join(outputDir, "bundle");
  if (fs.existsSync(outputDir)) throw new Error("Promotion output directory must not already exist.");
  fs.mkdirSync(outputDir, { recursive: true, mode: 0o700 });
  const staged = stageSourceRuntimeBundle({ coreDir, xkeyDir, integrityDir, stageDir, releaseTag });
  const archivePath = createArchive({ stageDir, outputDir });
  const manifestAssetPath = path.join(outputDir, MANIFEST_ASSET_NAME);
  fs.copyFileSync(staged.manifestPath, manifestAssetPath, fs.constants.COPYFILE_EXCL);
  const checksumsPath = path.join(outputDir, CHECKSUMS_ASSET_NAME);
  const checksumLines = [archivePath, manifestAssetPath]
    .map((file) => `${sha256File(file)}  ${path.basename(file)}`)
    .sort((left, right) => left.localeCompare(right));
  fs.writeFileSync(checksumsPath, `${checksumLines.join("\n")}\n`, "ascii");
  const output = {
    schemaVersion: 1,
    releaseTag,
    assetName: ASSET_NAME,
    assetSha256: sha256File(archivePath),
    runtimeManifestSha256: sha256File(manifestAssetPath),
    expiresAtUnix: staged.expiresAtUnix,
    archivePath,
    manifestAssetPath,
    checksumsPath,
  };
  fs.writeFileSync(
    path.join(outputDir, "promotion-output.json"),
    `${JSON.stringify(output, null, 2)}\n`,
    "utf8"
  );
  process.stdout.write(`${JSON.stringify(output)}\n`);
  return output;
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`${error?.stack || error}\n`);
    process.exit(1);
  }
}

module.exports = {
  ASSET_NAME,
  CHECKSUMS_ASSET_NAME,
  MANIFEST_ASSET_NAME,
  PAYLOAD_FILES,
  PROFILE,
  createArchive,
  sha256File,
  stageSourceRuntimeBundle,
  validateComponentProfiles,
};
