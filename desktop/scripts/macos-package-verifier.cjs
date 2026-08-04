"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const {
  extractCodeSigningLeafCertificate,
} = require("./macos-codesign-certificates.cjs");
const { validatePackagedBackend } = require("./native-core-before-pack.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const productName = packageJson.build.productName;
const version = packageJson.version;
const packageMinimumMacos = packageJson.build.mac.minimumSystemVersion;
const { contract: macosXkeyContract } = require("./macos-xkey-packaging.cjs");

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

function codeSignIdentity(filePath) {
  const details = codeSignDetails(filePath);
  const identifier = details.match(/^Identifier=(.+)$/m)?.[1]?.trim() || "";
  assert.ok(identifier, `Missing codesign Identifier: ${filePath}`);
  const certificate = new crypto.X509Certificate(
    extractCodeSigningLeafCertificate(filePath)
  );
  return {
    details,
    identifier,
    leafSha256: certificate.fingerprint256.replaceAll(":", "").toLowerCase(),
    leafSha1: certificate.fingerprint.replaceAll(":", "").toLowerCase(),
  };
}

function requirePinnedDesignatedRequirement(filePath, identifier, leafSha1) {
  const requirement = run("codesign", ["-d", "-r-", filePath]);
  const designated = requirement
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^designated\s*=>/i.test(line));
  assert.equal(designated.length, 1, `${filePath} has an ambiguous designated requirement`);
  const normalized = designated[0].replace(/\s+/g, " ").replace(/;$/, "").toLowerCase();
  assert.doesNotMatch(normalized, /\b(?:anchor|trusted)\b/i, `${filePath} relies on mutable trust settings`);
  assert.equal(
    normalized,
    `designated => identifier "${identifier}" and certificate leaf = h"${leafSha1}"`.toLowerCase(),
    `${filePath} lacks the exact fixed identifier + leaf designated requirement`
  );
  run("codesign", [
    "--verify", "--strict", "--verbose=2",
    `-R=identifier "${identifier}" and certificate leaf = H"${leafSha1}"`,
    filePath,
  ]);
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
  const backendRoot = path.join(resources, "backend");
  const packagedNative = validatePackagedBackend({ backendDir: backendRoot, platform: "darwin" });
  const nativeRoot = packagedNative.nativeDir;
  const electronExecutable = path.join(contents, "MacOS", path.basename(appPath, ".app"));
  const backend = path.join(backendRoot, "wechat-backend");
  const nativeClient = path.join(nativeRoot, "libwechatdb_client.dylib");
  const nativeBroker = path.join(nativeRoot, "wechatdb_broker");
  const nativeManifest = path.join(nativeRoot, "wechatdb_native_build.json");
  const imageLibrary = path.join(nativeRoot, "macos", "universal", "libwx_key.dylib");
  const imageHelper = path.join(nativeRoot, "macos", "universal", "image_scan_helper");
  const xkeyRoot = path.join(nativeRoot, ...String(macosXkeyContract.bundleRelativePath).split("/"));
  const xkeyHelper = path.join(xkeyRoot, macosXkeyContract.helperFileName);
  const xkeyManifestPath = path.join(xkeyRoot, macosXkeyContract.manifestFileName);
  const xkeyTrustPath = path.join(xkeyRoot, macosXkeyContract.trustFileName);
  const integrity = path.join(nativeRoot, "libwce_integrity.dylib");
  const ffmpeg = path.join(resources, "ffmpeg", "ffmpeg");

  for (const filePath of [
    electronExecutable,
    backend,
    nativeClient,
    nativeBroker,
    nativeManifest,
    imageLibrary,
    imageHelper,
    xkeyHelper,
    integrity,
    ffmpeg,
  ]) {
    requireRegularFile(filePath, {
      executable: [electronExecutable, backend, nativeBroker, imageHelper, xkeyHelper, ffmpeg].includes(filePath),
    });
  }
  for (const filePath of [
    path.join(resources, "backend", "THIRD_PARTY_NOTICES.md"),
    path.join(nativeRoot, "macos", "WEFLOW_LICENSE.txt"),
    path.join(nativeRoot, "macos", "source", "image_scan_helper.c"),
    path.join(nativeRoot, "macos", "source", "image_scan_entitlements.plist"),
    path.join(resources, "ffmpeg", "LICENSE"),
    path.join(resources, "ffmpeg", "ffmpeg.LICENSE"),
    xkeyManifestPath,
    xkeyTrustPath,
    path.join(xkeyRoot, macosXkeyContract.checksumsFileName),
    path.join(xkeyRoot, macosXkeyContract.provenanceFileName),
    path.join(xkeyRoot, macosXkeyContract.thirdPartyNoticeFileName),
  ]) {
    requireRegularFile(filePath);
  }
  for (const retiredPath of [
    path.join(nativeRoot, "macos", "arm64", "libwcdb_api.dylib"),
    path.join(nativeRoot, "macos", "universal", "libWCDB.dylib"),
    path.join(resources, "wcdb-sidecar.cjs"),
    path.join(resources, "app.asar.unpacked", "node_modules", "koffi"),
  ]) {
    assert.equal(fs.existsSync(retiredPath), false, `Retired WCDB runtime was packaged: ${retiredPath}`);
  }

  const packagedVersion = run("plutil", ["-extract", "CFBundleShortVersionString", "raw", "-o", "-", path.join(contents, "Info.plist")]).trim();
  const packagedMinimum = run("plutil", ["-extract", "LSMinimumSystemVersion", "raw", "-o", "-", path.join(contents, "Info.plist")]).trim();
  assert.equal(packagedVersion, version, `${source} contains app version ${packagedVersion}, expected ${version}`);
  assert.equal(packagedMinimum, packageMinimumMacos, `${source} has unexpected LSMinimumSystemVersion`);

  requireArchitectures(electronExecutable, ["arm64"]);
  requireArchitectures(backend, ["arm64"]);
  requireArchitectures(nativeClient, ["arm64"]);
  requireArchitectures(nativeBroker, ["arm64"]);
  requireArchitectures(integrity, ["arm64"]);
  requireArchitectures(ffmpeg, ["arm64"]);
  requireArchitectures(imageLibrary, ["arm64", "x86_64"]);
  requireArchitectures(imageHelper, ["arm64", "x86_64"]);
  requireArchitectures(xkeyHelper, ["arm64", "x86_64"]);
  for (const filePath of [
    electronExecutable,
    backend,
    nativeClient,
    nativeBroker,
    imageLibrary,
    imageHelper,
    xkeyHelper,
    integrity,
    ffmpeg,
  ]) {
    requireCompatibleMinimumOs(filePath);
  }

  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  run("codesign", ["--verify", "--strict", "--verbose=2", nativeClient]);
  run("codesign", ["--verify", "--strict", "--verbose=2", nativeBroker]);
  run("codesign", ["--verify", "--strict", "--verbose=2", xkeyHelper]);
  const xkeyManifest = JSON.parse(fs.readFileSync(xkeyManifestPath, "utf8"));
  const xkeyTrust = JSON.parse(fs.readFileSync(xkeyTrustPath, "utf8"));
  for (const name of [
    macosXkeyContract.helperFileName,
    macosXkeyContract.thirdPartyNoticeFileName,
  ]) {
    const packagedFile = path.join(xkeyRoot, name);
    const bytes = fs.readFileSync(packagedFile);
    assert.equal(
      crypto.createHash("sha256").update(bytes).digest("hex"),
      xkeyManifest.files[name].sha256,
      `macOS database key resource hash differs from its manifest: ${name}`
    );
    assert.equal(bytes.length, xkeyManifest.files[name].size);
  }
  const xkeyBytes = fs.readFileSync(xkeyHelper);
  assert.equal(
    crypto.createHash("sha256").update(xkeyBytes).digest("hex"),
    xkeyManifest.files[macosXkeyContract.helperFileName].sha256,
    "macOS database key helper hash differs from its manifest"
  );
  assert.equal(xkeyBytes.length, xkeyManifest.files[macosXkeyContract.helperFileName].size);
  const xkeyIdentity = codeSignIdentity(xkeyHelper);
  const backendIdentity = codeSignIdentity(backend);
  const appIdentity = codeSignIdentity(appPath);
  const nativeClientIdentity = codeSignIdentity(nativeClient);
  const nativeBrokerIdentity = codeSignIdentity(nativeBroker);
  assert.equal(
    nativeClientIdentity.identifier,
    packagedNative.manifest.macosClientSigningIdentifier,
    "macOS native client signing identifier differs from its manifest"
  );
  assert.equal(
    nativeClientIdentity.leafSha256,
    packagedNative.manifest.macosClientSignerSha256,
    "macOS native client leaf differs from its manifest"
  );
  assert.equal(
    nativeBrokerIdentity.identifier,
    packagedNative.manifest.macosBrokerSigningIdentifier,
    "macOS native broker signing identifier differs from its manifest"
  );
  assert.equal(
    nativeBrokerIdentity.leafSha256,
    packagedNative.manifest.macosBrokerSignerSha256,
    "macOS native broker leaf differs from its manifest"
  );
  assert.equal(
    backendIdentity.identifier,
    packagedNative.manifest.macosHostSigningIdentifier,
    "macOS backend identifier differs from the native-core host pin"
  );
  assert.equal(
    backendIdentity.leafSha256,
    packagedNative.manifest.macosHostSignerSha256,
    "macOS backend leaf differs from the native-core host pin"
  );
  requirePinnedDesignatedRequirement(
    nativeClient,
    nativeClientIdentity.identifier,
    nativeClientIdentity.leafSha1
  );
  requirePinnedDesignatedRequirement(
    nativeBroker,
    nativeBrokerIdentity.identifier,
    nativeBrokerIdentity.leafSha1
  );
  assert.equal(xkeyIdentity.identifier, macosXkeyContract.bundleId);
  assert.equal(xkeyIdentity.leafSha256, xkeyTrust.helperLeafCertificateSha256);
  assert.equal(backendIdentity.identifier, macosXkeyContract.hostSigningIdentifier);
  assert.equal(backendIdentity.leafSha256, xkeyTrust.hostLeafCertificateSha256);
  const mainEntitlements = run("codesign", ["-d", "--entitlements", "-", electronExecutable]);
  const helperEntitlements = run("codesign", ["-d", "--entitlements", "-", imageHelper]);
  assert.match(mainEntitlements, /com\.apple\.security\.cs\.allow-jit/);
  assert.match(helperEntitlements, /com\.apple\.security\.cs\.debugger/);

  if (distribution) {
    assert.doesNotMatch(codeSignDetails(appPath), /^Signature=adhoc$/m, `${appPath} is ad-hoc signed`);
    assert.doesNotMatch(backendIdentity.details, /^Signature=adhoc$/m, `${backend} is ad-hoc signed`);
    if (xkeyManifest.signing.mode === "developer-id") {
      const expectedTeam = String(process.env.APPLE_TEAM_ID || "").trim();
      assert.ok(expectedTeam, "APPLE_TEAM_ID is required for Developer ID verification");
      for (const filePath of [appPath, backend]) {
        const details = codeSignDetails(filePath);
        assert.match(details, /^Authority=Developer ID Application:/m, `${filePath} lacks Developer ID Application authority`);
        assert.equal(teamIdentifier(details), expectedTeam, `${filePath} was signed by an unexpected Apple team`);
      }
      run("spctl", ["--assess", "--type", "execute", "--verbose=4", appPath]);
      run("syspolicy_check", ["distribution", appPath]);
      run("xcrun", ["stapler", "validate", "-v", appPath]);
    } else {
      assert.equal(xkeyManifest.signing.mode, "self-signed");
      assert.equal(backendIdentity.leafSha256, xkeyTrust.hostLeafCertificateSha256);
      assert.equal(appIdentity.identifier, packageJson.build.appId);
      assert.equal(appIdentity.leafSha256, xkeyTrust.hostLeafCertificateSha256);
      requirePinnedDesignatedRequirement(appPath, packageJson.build.appId, appIdentity.leafSha1);
      requirePinnedDesignatedRequirement(
        backend,
        macosXkeyContract.hostSigningIdentifier,
        backendIdentity.leafSha1
      );
    }
    assert.doesNotMatch(mainEntitlements, /com\.apple\.security\.get-task-allow/);
  }

  process.stdout.write(`Verified ${distribution ? `${xkeyManifest.signing.mode} distribution` : "packaged"} app from ${source}: ${appPath}\n`);
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
