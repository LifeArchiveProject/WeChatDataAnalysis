"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const PROFILE = "windows-source-public";
const ASSET_NAME = "wechatdataanalysis-windows-source-runtime-x64-v1.tar.gz";
const MANIFEST_ASSET_NAME = "wechatdataanalysis-windows-source-runtime-x64-v1.manifest.json";
const CHECKSUMS_ASSET_NAME = "SHA256SUMS-windows-source-runtime.txt";
const LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const SHA40_PATTERN = /^[0-9a-f]{40}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const RELEASE_TAG_PATTERN = /^windows-source-runtime-[A-Za-z0-9._-]{8,96}$/;

const PAYLOAD_FILES = Object.freeze([
  ["native-core/wechatdb_client.dll", false],
  ["native-core/wechatdb_broker.exe", true],
  ["native-core/wechatdb_native_build.json", false],
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
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch {
    throw new Error(`${label} is missing.`);
  }
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`${label} is unsafe, empty, or oversized.`);
  }
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
  const value = JSON.parse(raw);
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

function requireRegularFile(file, label, maximum = 128 * 1024 * 1024) {
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch {
    throw new Error(`${label} is missing.`);
  }
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0 || stat.size > maximum) {
    throw new Error(`${label} is unsafe, empty, or oversized.`);
  }
  return stat;
}

function requireBuildWindow(issuedAt, expiresAt, nowUnix) {
  if (
    !Number.isSafeInteger(issuedAt) ||
    !Number.isSafeInteger(expiresAt) ||
    issuedAt <= 0 ||
    expiresAt !== issuedAt + LIFETIME_SECONDS ||
    nowUnix < issuedAt - 300 ||
    nowUnix >= expiresAt
  ) {
    throw new Error("Native-core does not have an active exact 45-day build window.");
  }
  return expiresAt;
}

function validateSourcePublicCore(coreDir, nowUnix) {
  const manifest = readJson(
    path.join(coreDir, "wechatdb_native_build.json"),
    "source-public native-core manifest",
    16 * 1024
  );
  const provenance = readJson(path.join(coreDir, "provenance.json"), "native-core provenance");
  if (
    manifest.schemaVersion !== 2 ||
    manifest.distributionMode !== "public" ||
    manifest.sourceRuntime !== true ||
    manifest.windowsHostVerification !== "same-user-direct-parent" ||
    manifest.developmentBuild !== false ||
    manifest.codeSignatureEnforced !== true ||
    manifest.rootPublicKeyCompiled !== true ||
    manifest.testHooksEnabled !== false ||
    manifest.stagingPinnedSignerTrust !== false ||
    manifest.offlineBootstrapFeatureBits !== 3 ||
    manifest.offlineExportSealFormat !== "WES2" ||
    manifest.securityCheckpointSetId !== "WCE-AI-CHECKPOINT-SET-V3" ||
    manifest.securityCheckpointCount !== 7 ||
    provenance.schemaVersion !== 1 ||
    provenance.artifactName !== "wechatdb-native-windows-x64-source-public" ||
    provenance.build?.sourceRuntime !== true ||
    provenance.build?.windowsHostVerification !== "same-user-direct-parent"
  ) {
    throw new Error("Native-core artifact is not the exact restricted source-public profile.");
  }
  const buildId = requireString(manifest.buildId, BUILD_ID_PATTERN, "native-core build ID");
  const sourceRevision = requireString(
    provenance.source?.revision,
    SHA40_PATTERN,
    "native-core source revision"
  );
  const producerRunId = Number(provenance.build?.workflowRunId);
  if (
    provenance.build?.id !== buildId ||
    !Number.isSafeInteger(producerRunId) ||
    producerRunId <= 0
  ) {
    throw new Error("Native-core manifest and provenance coordinates differ.");
  }
  const expiresAtUnix = requireBuildWindow(
    manifest.buildIssuedAtUnix,
    manifest.buildExpiresAtUnix,
    nowUnix
  );
  return {
    artifactName: provenance.artifactName,
    buildId,
    sourceRevision,
    producerRunId,
    expiresAtUnix,
  };
}

function copyRegular(source, destination) {
  const sourceStat = requireRegularFile(source, path.basename(source));
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(source, destination, fs.constants.COPYFILE_EXCL);
  if (
    fs.statSync(destination).size !== sourceStat.size ||
    sha256File(destination) !== sha256File(source)
  ) {
    throw new Error(`Source runtime copy verification failed: ${destination}`);
  }
}

function stageWindowsSourceRuntimeBundle({
  coreDir,
  stageDir,
  releaseTag,
  nowUnix = Math.floor(Date.now() / 1000),
}) {
  requireString(releaseTag, RELEASE_TAG_PATTERN, "Windows source-runtime release tag");
  if (!Number.isSafeInteger(nowUnix) || nowUnix <= 0) throw new Error("nowUnix is invalid.");
  const component = validateSourcePublicCore(coreDir, nowUnix);
  if (fs.existsSync(stageDir)) throw new Error("Source-runtime stage directory must not exist.");
  fs.mkdirSync(stageDir, { recursive: true });

  const sources = new Map([
    ["native-core/wechatdb_client.dll", path.join(coreDir, "wechatdb_client.dll")],
    ["native-core/wechatdb_broker.exe", path.join(coreDir, "wechatdb_broker.exe")],
    ["native-core/wechatdb_native_build.json", path.join(coreDir, "wechatdb_native_build.json")],
  ]);
  for (const [relative] of PAYLOAD_FILES) {
    copyRegular(sources.get(relative), path.join(stageDir, ...relative.split("/")));
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
  const manifest = {
    schemaVersion: 1,
    profile: PROFILE,
    platform: "win32",
    architecture: "x64",
    releaseTag,
    createdAtUnix: nowUnix,
    expiresAtUnix: component.expiresAtUnix,
    components: {
      nativeCore: { ...component, path: "native-core" },
    },
    files,
  };
  const manifestPath = path.join(stageDir, "runtime-manifest.json");
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });
  return { component, expiresAtUnix: component.expiresAtUnix, manifest, manifestPath };
}

function createArchive({ stageDir, outputDir, spawnSyncImpl = spawnSync }) {
  fs.mkdirSync(outputDir, { recursive: true });
  const archivePath = path.join(outputDir, ASSET_NAME);
  const result = spawnSyncImpl("tar.exe", ["-czf", archivePath, "-C", stageDir, "."], {
    encoding: "utf8",
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  if (result?.error || result?.status !== 0) {
    throw new Error(
      `Cannot create Windows source-runtime archive: ${result?.stderr || result?.error?.message || "tar failed"}`
    );
  }
  requireRegularFile(archivePath, ASSET_NAME);
  return archivePath;
}

function main(env = process.env) {
  const coreDir = path.resolve(String(env.WCE_SOURCE_PUBLIC_NATIVE_CORE_DIR || ""));
  const outputDir = path.resolve(String(env.WCE_SOURCE_RUNTIME_OUTPUT_DIR || ""));
  const releaseTag = String(env.WCE_SOURCE_RUNTIME_RELEASE_TAG || "").trim();
  const stageDir = path.join(outputDir, "bundle");
  if (fs.existsSync(outputDir)) throw new Error("Promotion output directory must not already exist.");
  fs.mkdirSync(outputDir, { recursive: true });
  const staged = stageWindowsSourceRuntimeBundle({ coreDir, stageDir, releaseTag });
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
  stageWindowsSourceRuntimeBundle,
  validateSourcePublicCore,
};
