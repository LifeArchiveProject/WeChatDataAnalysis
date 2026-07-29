"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

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
const REQUIRED_WCDB_API_EXPORTS = [
  "InitProtection",
  "wcdb_init",
  "wcdb_shutdown",
  "wcdb_open_account",
  "wcdb_close_account",
  "wcdb_set_my_wxid",
  "wcdb_get_sessions",
  "wcdb_get_messages",
  "wcdb_open_message_cursor",
  "wcdb_fetch_message_batch",
  "wcdb_close_message_cursor",
  "wcdb_get_contacts_compact",
  "wcdb_get_sns_timeline",
  "wcdb_list_media_dbs",
  "wcdb_scan_media_stream",
  "wcdb_exec_query",
  "wcdb_get_logs",
  "wcdb_free_string",
];

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

function verifyRequiredExports(filePath, requiredExports) {
  const symbols = new Set(
    run("nm", ["-gU", filePath])
      .split(/\r?\n/)
      .map((line) => line.trim().split(/\s+/).at(-1) || "")
      .filter((name) => name.startsWith("_"))
      .map((name) => name.slice(1))
  );
  const missing = requiredExports.filter((name) => !symbols.has(name));
  if (missing.length > 0) {
    fail(`${filePath} is missing required WCDB exports: ${missing.join(", ")}`);
  }
  return [...requiredExports];
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

  const wcdbApi = path.join(nativeRoot, targetArchitecture, "libwcdb_api.dylib");
  const wcdb = path.join(nativeRoot, "universal", "libWCDB.dylib");
  const imageLibrary = path.join(nativeRoot, "universal", "libwx_key.dylib");
  const imageHelper = path.join(nativeRoot, "universal", "image_scan_helper");
  verifyHelperManifest(imageHelper);
  const ffmpegRoot = path.join(desktopRoot, "node_modules", "ffmpeg-static");
  const ffmpeg = path.join(ffmpegRoot, "ffmpeg");
  const koffiNative = path.join(
    desktopRoot,
    "node_modules",
    "koffi",
    "build",
    "koffi",
    "darwin_arm64",
    "koffi.node"
  );
  const wcdbApiSummary = verifyBinary(wcdbApi, { requiredArchitectures: [targetArchitecture] });
  const wcdbApiExports = verifyRequiredExports(wcdbApi, REQUIRED_WCDB_API_EXPORTS);
  const summaries = [
    { ...wcdbApiSummary, requiredExports: wcdbApiExports },
    verifyBinary(wcdb, { requiredArchitectures: ["arm64", "x86_64"] }),
    verifyBinary(imageLibrary, { requiredArchitectures: ["arm64", "x86_64"] }),
    verifyBinary(imageHelper, { requiredArchitectures: ["arm64", "x86_64"], executable: true }),
    verifyBinary(ffmpeg, { requiredArchitectures: [targetArchitecture], executable: true }),
    verifyBinary(koffiNative, { requiredArchitectures: [targetArchitecture] }),
  ];

  const apiId = run("otool", ["-D", wcdbApi]);
  if (!apiId.includes("@loader_path/libwcdb_api.dylib")) {
    fail(`Unexpected libwcdb_api install ID:\n${apiId}`);
  }
  const apiDependencies = run("otool", ["-L", wcdbApi]);
  if (!apiDependencies.includes("@loader_path/../universal/libWCDB.dylib")) {
    fail(`libwcdb_api is not self-contained:\n${apiDependencies}`);
  }
  const dependencyEntries = apiDependencies.split(/\r?\n/).slice(1).join("\n");
  if (dependencyEntries.includes(repoRoot) || /(?:^|\/)WeFlow(?:-|\/)/m.test(dependencyEntries)) {
    fail(`libwcdb_api references a source checkout:\n${apiDependencies}`);
  }

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
