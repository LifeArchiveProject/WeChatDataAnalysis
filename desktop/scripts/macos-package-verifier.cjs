"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const productName = packageJson.build.productName;
const version = packageJson.version;
const packageMinimumMacos = packageJson.build.mac.minimumSystemVersion;

function run(command, args, { capture = true } = {}) {
  const result = spawnSync(command, args, { encoding: "utf8", stdio: capture ? "pipe" : "inherit" });
  if (result.error) throw result.error;
  const output = `${result.stdout || ""}${result.stderr || ""}`;
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed (${result.status})${output ? `:\n${output}` : ""}`);
  }
  return output;
}

function requireRegularFile(filePath, { executable = false } = {}) {
  assert.ok(fs.existsSync(filePath), `Missing packaged resource: ${filePath}`);
  const stat = fs.lstatSync(filePath);
  assert.ok(stat.isFile() && !stat.isSymbolicLink(), `Packaged resource must be a regular file: ${filePath}`);
  if (executable) fs.accessSync(filePath, fs.constants.X_OK);
}

function architectures(filePath) {
  return run("lipo", ["-archs", filePath]).trim().split(/\s+/).filter(Boolean);
}

function requireArchitectures(filePath, expected) {
  const actual = architectures(filePath);
  for (const architecture of expected) {
    assert.ok(actual.includes(architecture), `${filePath} is missing ${architecture}; found ${actual.join(" ")}`);
  }
}

function minimumVersions(filePath) {
  const output = run("otool", ["-l", filePath]);
  return [...output.matchAll(/^\s*minos\s+([0-9.]+)\s*$/gm)].map((match) => match[1]);
}

function versionTuple(value) {
  return String(value).split(".").map((part) => Number.parseInt(part, 10) || 0);
}

function compareVersions(left, right) {
  const a = versionTuple(left);
  const b = versionTuple(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const delta = (a[index] || 0) - (b[index] || 0);
    if (delta !== 0) return delta;
  }
  return 0;
}

function requireCompatibleMinimumOs(filePath) {
  const values = minimumVersions(filePath);
  assert.ok(values.length > 0, `Missing LC_BUILD_VERSION minos: ${filePath}`);
  for (const value of values) {
    assert.ok(
      compareVersions(value, packageMinimumMacos) <= 0,
      `${filePath} requires macOS ${value}, above package minimum ${packageMinimumMacos}`
    );
  }
}

function codeSignDetails(filePath) {
  return run("codesign", ["-dv", "--verbose=4", filePath]);
}

function teamIdentifier(details) {
  return details.match(/^TeamIdentifier=(.+)$/m)?.[1]?.trim() || "";
}

function findSingleApp(root) {
  const apps = fs.readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.endsWith(".app"))
    .map((entry) => path.join(root, entry.name));
  assert.equal(apps.length, 1, `Expected one .app under ${root}, found ${apps.length}`);
  return apps[0];
}

function verifyAppBundle(appPath, { distribution = false, source = "package" } = {}) {
  const contents = path.join(appPath, "Contents");
  const resources = path.join(contents, "Resources");
  const nativeRoot = path.join(resources, "backend", "native");
  const electronExecutable = path.join(contents, "MacOS", path.basename(appPath, ".app"));
  const backend = path.join(resources, "backend", "wechat-backend");
  const wcdbApi = path.join(nativeRoot, "macos", "arm64", "libwcdb_api.dylib");
  const wcdb = path.join(nativeRoot, "macos", "universal", "libWCDB.dylib");
  const imageLibrary = path.join(nativeRoot, "macos", "universal", "libwx_key.dylib");
  const imageHelper = path.join(nativeRoot, "macos", "universal", "image_scan_helper");
  const integrity = path.join(nativeRoot, "libwce_integrity.dylib");
  const ffmpeg = path.join(resources, "ffmpeg", "ffmpeg");
  const koffi = path.join(resources, "app.asar.unpacked", "node_modules", "koffi", "build", "koffi", "darwin_arm64", "koffi.node");

  for (const filePath of [electronExecutable, backend, wcdbApi, wcdb, imageLibrary, imageHelper, integrity, ffmpeg, koffi]) {
    requireRegularFile(filePath, { executable: [electronExecutable, backend, imageHelper, ffmpeg].includes(filePath) });
  }
  for (const filePath of [
    path.join(resources, "wcdb-sidecar.cjs"),
    path.join(resources, "backend", "THIRD_PARTY_NOTICES.md"),
    path.join(nativeRoot, "macos", "WEFLOW_LICENSE.txt"),
    path.join(nativeRoot, "macos", "source", "image_scan_helper.c"),
    path.join(nativeRoot, "macos", "source", "image_scan_entitlements.plist"),
    path.join(resources, "ffmpeg", "LICENSE"),
    path.join(resources, "ffmpeg", "ffmpeg.LICENSE"),
  ]) {
    requireRegularFile(filePath);
  }

  const packagedVersion = run("plutil", ["-extract", "CFBundleShortVersionString", "raw", "-o", "-", path.join(contents, "Info.plist")]).trim();
  const packagedMinimum = run("plutil", ["-extract", "LSMinimumSystemVersion", "raw", "-o", "-", path.join(contents, "Info.plist")]).trim();
  assert.equal(packagedVersion, version, `${source} contains app version ${packagedVersion}, expected ${version}`);
  assert.equal(packagedMinimum, packageMinimumMacos, `${source} has unexpected LSMinimumSystemVersion`);

  requireArchitectures(electronExecutable, ["arm64"]);
  requireArchitectures(backend, ["arm64"]);
  requireArchitectures(wcdbApi, ["arm64"]);
  requireArchitectures(integrity, ["arm64"]);
  requireArchitectures(koffi, ["arm64"]);
  requireArchitectures(ffmpeg, ["arm64"]);
  requireArchitectures(wcdb, ["arm64", "x86_64"]);
  requireArchitectures(imageLibrary, ["arm64", "x86_64"]);
  requireArchitectures(imageHelper, ["arm64", "x86_64"]);
  for (const filePath of [electronExecutable, backend, wcdbApi, wcdb, imageLibrary, imageHelper, integrity, ffmpeg, koffi]) {
    requireCompatibleMinimumOs(filePath);
  }

  const dependencies = run("otool", ["-L", wcdbApi]);
  assert.match(dependencies, /@loader_path\/\.\.\/universal\/libWCDB\.dylib/);
  assert.doesNotMatch(dependencies, /(?:^|\/)WeFlow(?:-|\/)/m);

  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const mainEntitlements = run("codesign", ["-d", "--entitlements", "-", electronExecutable]);
  const helperEntitlements = run("codesign", ["-d", "--entitlements", "-", imageHelper]);
  assert.match(mainEntitlements, /com\.apple\.security\.cs\.allow-jit/);
  assert.match(helperEntitlements, /com\.apple\.security\.cs\.debugger/);

  if (distribution) {
    const expectedTeam = String(process.env.APPLE_TEAM_ID || "").trim();
    assert.ok(expectedTeam, "APPLE_TEAM_ID is required for distribution verification");
    for (const filePath of [appPath, imageHelper]) {
      const details = codeSignDetails(filePath);
      assert.match(details, /^Authority=Developer ID Application:/m, `${filePath} lacks Developer ID Application authority`);
      assert.doesNotMatch(details, /^Signature=adhoc$/m, `${filePath} is ad-hoc signed`);
      assert.equal(teamIdentifier(details), expectedTeam, `${filePath} was signed by an unexpected Apple team`);
    }
    assert.doesNotMatch(mainEntitlements, /com\.apple\.security\.get-task-allow/);
    run("spctl", ["--assess", "--type", "execute", "--verbose=4", appPath]);
    run("syspolicy_check", ["distribution", appPath]);
    run("xcrun", ["stapler", "validate", "-v", appPath]);
  }

  process.stdout.write(`Verified ${distribution ? "Developer ID distribution" : "packaged"} app from ${source}: ${appPath}\n`);
}

function detachMountedDmg(mountRoot, runCommand = run) {
  let detachError;
  try {
    runCommand("hdiutil", ["detach", mountRoot]);
    return;
  } catch (error) {
    detachError = error;
  }

  try {
    runCommand("hdiutil", ["detach", "-force", mountRoot]);
  } catch (forceError) {
    const details = [
      `Normal detach failed:\n${detachError?.stack || detachError}`,
      `Forced detach failed:\n${forceError?.stack || forceError}`,
    ].join("\n");
    throw new AggregateError(
      [detachError, forceError],
      `Failed to detach mounted DMG at ${mountRoot}; mount directory was preserved.\n${details}`
    );
  }
}

async function withMacosArtifacts({ distribution = false } = {}, callback = async () => undefined) {
  if (process.platform !== "darwin") throw new Error("macOS package verification must run on macOS");
  if (typeof callback !== "function") throw new TypeError("macOS artifact callback must be a function");
  const artifactBase = `${productName}-${version}-mac-arm64`;
  const zipPath = path.join(desktopRoot, "dist", `${artifactBase}.zip`);
  const dmgPath = path.join(desktopRoot, "dist", `${artifactBase}.dmg`);
  requireRegularFile(zipPath);
  requireRegularFile(dmgPath);

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "wda-macos-artifacts-"));
  const zipRoot = path.join(tempRoot, "zip");
  const mountRoot = path.join(tempRoot, "dmg");
  let mounted = false;
  let result;
  let operationError;
  try {
    fs.mkdirSync(zipRoot);
    run("ditto", ["-x", "-k", zipPath, zipRoot], { capture: false });
    const zipAppPath = findSingleApp(zipRoot);
    verifyAppBundle(zipAppPath, { distribution, source: path.basename(zipPath) });

    fs.mkdirSync(mountRoot);
    run("hdiutil", ["attach", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", mountRoot, dmgPath]);
    mounted = true;
    const dmgAppPath = findSingleApp(mountRoot);
    verifyAppBundle(dmgAppPath, { distribution, source: path.basename(dmgPath) });

    result = await callback({ zipAppPath, dmgAppPath, zipPath, dmgPath });
  } catch (error) {
    operationError = error;
  }

  let cleanupError;
  if (mounted) {
    try {
      detachMountedDmg(mountRoot);
    } catch (error) {
      cleanupError = error;
    }
  }

  if (!cleanupError) {
    try {
      fs.rmSync(tempRoot, { recursive: true, force: true });
    } catch (error) {
      cleanupError = error;
    }
  }

  if (operationError && cleanupError) {
    throw new AggregateError(
      [operationError, cleanupError],
      "macOS artifact verification and cleanup both failed"
    );
  }
  if (operationError) throw operationError;
  if (cleanupError) throw cleanupError;
  return result;
}

async function verifyMacosArtifacts(options = {}) {
  return withMacosArtifacts(options);
}

module.exports = { detachMountedDmg, verifyAppBundle, verifyMacosArtifacts, withMacosArtifacts };
