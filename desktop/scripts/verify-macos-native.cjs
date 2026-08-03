"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { resolveNativeCoreArtifacts } = require("./build-backend.cjs");

const SUPPORTED_ARCHITECTURE = "arm64";
const MAXIMUM_NATIVE_MIN_OS = "15.0";
const repoRoot = path.resolve(__dirname, "..", "..");
const desktopRoot = path.join(repoRoot, "desktop");
const nativeRoot = path.join(repoRoot, "src", "wechat_decrypt_tool", "native", "macos");
const helperManifestPath = path.join(desktopRoot, "scripts", "macos-image-helper-manifest.json");
const requireHostArchitecture = process.argv.includes("--require-host-arch");
const architectureIndex = process.argv.indexOf("--arch");
const targetArchitecture = architectureIndex >= 0
  ? String(process.argv[architectureIndex + 1] || "").trim()
  : SUPPORTED_ARCHITECTURE;

function fail(message) {
  throw new Error(message);
}

function run(command, args) {
  const result = spawnSync(command, args, { cwd: repoRoot, encoding: "utf8", stdio: "pipe" });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    fail(`${command} ${args.join(" ")} failed (${result.status})${details ? `:\n${details}` : ""}`);
  }
  return `${result.stdout || ""}${result.stderr || ""}`.trim();
}

function requireRegularFile(filePath, { executable = false } = {}) {
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) fail(`Native resource must be a regular file: ${filePath}`);
  if (executable) fs.accessSync(filePath, fs.constants.X_OK);
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function verifyHelperManifest(imageHelper) {
  requireRegularFile(helperManifestPath);
  const manifest = JSON.parse(fs.readFileSync(helperManifestPath, "utf8"));
  if (manifest.schemaVersion !== 1) fail(`Unsupported image helper manifest schema: ${manifest.schemaVersion}`);
  if (manifest.deploymentTarget !== MAXIMUM_NATIVE_MIN_OS) {
    fail(`Image helper manifest deployment target must be ${MAXIMUM_NATIVE_MIN_OS}`);
  }
  if (JSON.stringify(manifest.architectures) !== JSON.stringify(["arm64", "x86_64"])) {
    fail("Image helper manifest must declare arm64 and x86_64");
  }

  const expectedInputs = [
    path.join(nativeRoot, "source", "image_scan_helper.c"),
    path.join(nativeRoot, "source", "image_scan_entitlements.plist"),
  ];
  const declaredInputs = Array.isArray(manifest.inputs) ? manifest.inputs : [];
  if (declaredInputs.length !== expectedInputs.length) fail("Image helper manifest input set is incomplete");
  for (const filePath of expectedInputs) {
    const relative = path.relative(repoRoot, filePath).split(path.sep).join("/");
    const entry = declaredInputs.find((candidate) => candidate?.path === relative);
    if (!entry) fail(`Image helper manifest is missing input: ${relative}`);
    requireRegularFile(filePath);
    if (entry.sha256 !== sha256(filePath)) fail(`Image helper input hash is stale: ${relative}`);
  }

  const artifactRelative = path.relative(repoRoot, imageHelper).split(path.sep).join("/");
  if (manifest.artifact?.path !== artifactRelative) fail(`Unexpected image helper artifact path: ${manifest.artifact?.path}`);
  if (manifest.artifact?.sha256 !== sha256(imageHelper)) {
    fail("Tracked image helper does not match its source-input manifest; rebuild it with npm run build:mac:image-helper");
  }
}

function versionTuple(value) {
  return String(value)
    .split(".")
    .map((part) => Number.parseInt(part, 10) || 0);
}

function compareVersions(left, right) {
  const a = versionTuple(left);
  const b = versionTuple(right);
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const delta = (a[index] || 0) - (b[index] || 0);
    if (delta !== 0) return delta;
  }
  return 0;
}

function architectures(filePath) {
  return run("lipo", ["-archs", filePath]).split(/\s+/).filter(Boolean);
}

function minimumVersions(filePath) {
  const output = run("otool", ["-l", filePath]);
  return [...output.matchAll(/^\s*minos\s+([0-9.]+)\s*$/gm)].map((match) => match[1]);
}

function verifyBinary(filePath, { requiredArchitectures, executable = false } = {}) {
  requireRegularFile(filePath, { executable });
  const fileArchitectures = architectures(filePath);
  for (const required of requiredArchitectures) {
    if (!fileArchitectures.includes(required)) {
      fail(`${filePath} is missing ${required}; found: ${fileArchitectures.join(" ")}`);
    }
  }

  const minOsValues = minimumVersions(filePath);
  if (minOsValues.length === 0) fail(`Unable to read LC_BUILD_VERSION minos from ${filePath}`);
  for (const minOs of minOsValues) {
    if (compareVersions(minOs, MAXIMUM_NATIVE_MIN_OS) > 0) {
      fail(`${filePath} requires macOS ${minOs}, above package minimum ${MAXIMUM_NATIVE_MIN_OS}`);
    }
  }
  run("codesign", ["--verify", "--strict", "--verbose=2", filePath]);
  return { path: path.relative(repoRoot, filePath), architectures: fileArchitectures, minOs: minOsValues };
}

function main() {
  if (process.platform !== "darwin") fail("macOS native resource verification must run on macOS");
  if (targetArchitecture !== SUPPORTED_ARCHITECTURE) {
    fail(`Unsupported macOS package architecture: ${targetArchitecture}; only arm64 is complete`);
  }
  if (requireHostArchitecture && process.arch !== targetArchitecture) {
    fail(
      `The ${targetArchitecture} package must be built on a ${targetArchitecture} host so PyInstaller and Rust outputs match; got ${process.arch}`
    );
  }

  const nativeCore = resolveNativeCoreArtifacts({ env: process.env, platform: "darwin" });
  const nativeClient = path.join(nativeCore.artifactDir, "libwechatdb_client.dylib");
  const nativeBroker = path.join(nativeCore.artifactDir, "wechatdb_broker");
  const nativeManifest = path.join(nativeCore.artifactDir, "wechatdb_native_build.json");
  const imageLibrary = path.join(nativeRoot, "universal", "libwx_key.dylib");
  const imageHelper = path.join(nativeRoot, "universal", "image_scan_helper");
  verifyHelperManifest(imageHelper);
  const ffmpegRoot = path.join(desktopRoot, "node_modules", "ffmpeg-static");
  const ffmpeg = path.join(ffmpegRoot, "ffmpeg");
  requireRegularFile(nativeManifest);
  const summaries = [
    verifyBinary(nativeClient, { requiredArchitectures: [targetArchitecture] }),
    // GitHub artifact extraction does not preserve executable bits. The
    // backend staging step restores the broker mode before PyInstaller runs.
    verifyBinary(nativeBroker, { requiredArchitectures: [targetArchitecture] }),
    {
      path: path.relative(repoRoot, nativeManifest),
      kind: "native-core-manifest",
      buildId: nativeCore.manifest.buildId,
    },
    verifyBinary(imageLibrary, { requiredArchitectures: ["arm64", "x86_64"] }),
    verifyBinary(imageHelper, { requiredArchitectures: ["arm64", "x86_64"], executable: true }),
    verifyBinary(ffmpeg, { requiredArchitectures: [targetArchitecture], executable: true }),
  ];

  for (const required of [
    path.join(nativeRoot, "WEFLOW_LICENSE.txt"),
    path.join(nativeRoot, "source", "image_scan_helper.c"),
    path.join(nativeRoot, "source", "image_scan_entitlements.plist"),
    path.join(repoRoot, "THIRD_PARTY_NOTICES.md"),
    path.join(ffmpegRoot, "LICENSE"),
    path.join(ffmpegRoot, "ffmpeg.LICENSE"),
    path.join(ffmpegRoot, "ffmpeg.README"),
  ]) {
    requireRegularFile(required);
  }

  process.stdout.write(
    `${JSON.stringify({ targetArchitecture, maximumNativeMinOS: MAXIMUM_NATIVE_MIN_OS, resources: summaries }, null, 2)}\n`
  );
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
}
