const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { detachMountedDmg } = require("../scripts/macos-package-verifier.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));

test("desktop package excludes the retired Koffi and WCDB sidecar runtime", () => {
  const nodeModulesRule = packageJson.build.files.find(
    (item) => item && typeof item === "object" && item.from === "node_modules"
  );
  assert.ok(nodeModulesRule);
  assert.equal(packageJson.dependencies.koffi, undefined);
  assert.equal(nodeModulesRule.filter.includes("koffi/**/*"), false);
  assert.equal(packageJson.build.asarUnpack, undefined);
  assert.ok(packageJson.build.files.includes("!src/wcdb-sidecar.cjs"));
});

test("development launcher owns the Electron process tree directly", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "scripts", "dev.cjs"), "utf8");
  assert.match(source, /const electronCommand = require\("electron"\);/);
  assert.match(source, /shell: options\.shell \?\? \(process\.platform === "win32"\)/);
  assert.match(source, /windowsHide: false/);
  assert.doesNotMatch(source, /detached: true/);
  assert.doesNotMatch(source, /const electronCommand = "electron";/);
});

test("desktop package ships the platform ffmpeg binary and license", () => {
  const resource = packageJson.build.extraResources.find(
    (item) => item && item.from === "node_modules/ffmpeg-static"
  );
  assert.ok(resource);
  assert.equal(resource.to, "ffmpeg");
  assert.ok(resource.filter.includes("ffmpeg"));
  assert.ok(resource.filter.includes("ffmpeg.exe"));
  assert.ok(resource.filter.includes("LICENSE"));
});

test("macOS package keeps image scanning resources, removes retired WCDB, and stages the native core trio", () => {
  const nativeRoot = path.join(repoRoot, "src", "wechat_decrypt_tool", "native", "macos");
  const required = [
    path.join(nativeRoot, "universal", "libwx_key.dylib"),
    path.join(nativeRoot, "universal", "image_scan_helper"),
    path.join(nativeRoot, "source", "image_scan_helper.c"),
    path.join(nativeRoot, "source", "image_scan_entitlements.plist"),
    path.join(nativeRoot, "WEFLOW_LICENSE.txt"),
  ];
  for (const resource of required) assert.ok(fs.existsSync(resource), resource);
  for (const retiredResource of [
    path.join(nativeRoot, "arm64", "libwcdb_api.dylib"),
    path.join(nativeRoot, "universal", "libWCDB.dylib"),
  ]) {
    assert.equal(fs.existsSync(retiredResource), false, retiredResource);
  }
  fs.accessSync(path.join(nativeRoot, "universal", "image_scan_helper"), fs.constants.X_OK);

  const buildBackend = fs.readFileSync(
    path.join(desktopRoot, "scripts", "build-backend.cjs"),
    "utf8"
  );
  assert.match(buildBackend, /darwin:\s*\["libwechatdb_client\.dylib", "wechatdb_broker", NATIVE_CORE_MANIFEST\]/);
});

test("Windows package uses private-PKI signing while preserving producer signatures", () => {
  const signingResource = packageJson.build.extraResources.find(
    (item) => item && item.from === "resources/signing"
  );
  assert.ok(signingResource);
  assert.deepEqual([...signingResource.filter].sort(), [
    "macos-private-pki-root.cer",
    "windows-private-pki-root.cer",
    "windows-private-pki.ps1",
  ]);
  assert.equal(packageJson.build.win.forceCodeSigning, true);
  assert.ok(packageJson.build.win.signExts.includes("!wechatdb_broker.exe"));
  assert.ok(packageJson.build.win.signExts.includes("!wechatdb_client.dll"));
  assert.ok(packageJson.build.win.signExts.includes("wce_integrity.pyd"));
  assert.ok(packageJson.build.win.signExts.includes("img_helper.dll"));
  assert.equal(
    packageJson.build.win.signtoolOptions.sign,
    "./scripts/windows-private-pki-sign.cjs"
  );
  assert.deepEqual(packageJson.build.win.signtoolOptions.publisherName, ["WDA Private PKI"]);
  assert.deepEqual(packageJson.build.win.signtoolOptions.signingHashAlgorithms, ["sha256"]);
  assert.match(
    packageJson.build.win.signtoolOptions.rfc3161TimeStampServer,
    /^https?:\/\//
  );
});

test("Windows release uses protected cloud private-PKI signing and installer smoke", () => {
  const smokeScript = path.join(desktopRoot, "scripts", "smoke-windows-package.cjs");
  assert.equal(packageJson.scripts["smoke:win"], "node scripts/smoke-windows-package.cjs");
  assert.equal(
    packageJson.scripts["smoke:win:real"],
    "node scripts/smoke-windows-real-database.cjs"
  );
  assert.ok(fs.existsSync(smokeScript), smokeScript);
  const smokeSource = fs.readFileSync(smokeScript, "utf8");
  assert.match(smokeSource, /wechat-backend\.exe/);
  assert.match(smokeSource, /WeChatDataAnalysis\.exe/);
  assert.match(smokeSource, /wechatdb_client\.dll/);
  assert.match(smokeSource, /wechatdb_broker\.exe/);
  assert.match(smokeSource, /\/api\/health/);
  assert.match(smokeSource, /smokeElectronApp/);
  assert.match(smokeSource, /AUTO_UPDATE_ENABLED:\s*"0"/);

  const workflow = fs
    .readFileSync(path.join(repoRoot, ".github", "workflows", "release.yml"), "utf8")
    .replace(/\r\n/g, "\n");
  const windowsJob = workflow.match(
    /\n  build-windows:\n([\s\S]*?)(?=\n  [A-Za-z0-9_-]+:\n|$)/
  )?.[1] || "";
  assert.match(windowsJob, /runs-on:\s*windows-2022/);
  assert.match(windowsJob, /environment:\s*windows-private-pki-production/);
  assert.match(windowsJob, /fetch-depth:\s*0/);
  assert.match(windowsJob, /persist-credentials:\s*false/);
  assert.match(windowsJob, /\$tagCommit\s+-cne\s+\$head/);
  assert.match(windowsJob, /git merge-base --is-ancestor \$tagRef origin\/main/);
  assert.match(windowsJob, /WCE_WINDOWS_CLIENT_CERT_THUMBPRINT/);
  assert.match(
    windowsJob,
    /WCE_WINDOWS_CLIENT_SIGNING_PFX_BASE64:\s*\$\{\{ secrets\.WCE_WINDOWS_CLIENT_SIGNING_PFX_BASE64 \}\}/
  );
  assert.match(
    windowsJob,
    /WCE_WINDOWS_CLIENT_SIGNING_PFX_PASSWORD:\s*\$\{\{ secrets\.WCE_WINDOWS_CLIENT_SIGNING_PFX_PASSWORD \}\}/
  );
  assert.match(
    windowsJob,
    /WCE_WINDOWS_PRIVATE_ROOT_CERT_BASE64:\s*\$\{\{ secrets\.WCE_WINDOWS_PRIVATE_ROOT_CERT_BASE64 \}\}/
  );
  assert.match(windowsJob, /Import-WindowsCloudSigningIdentity\.ps1/);
  assert.match(windowsJob, /Remove-WindowsCloudSigningIdentity\.ps1/);
  assert.match(windowsJob, /if:\s*always\(\)/);
  assert.match(windowsJob, /steps\.cloud-signing\.outputs\.client-thumbprint/);
  assert.match(windowsJob, /steps\.cloud-signing\.outputs\.root-certificate-path/);
  assert.match(windowsJob, /WCE_WINDOWS_SIGNING_ASSURANCE/);
  assert.match(windowsJob, /Install Python dependencies/);
  assert.match(windowsJob, /Run focused Python release tests/);
  assert.match(windowsJob, /uv sync --frozen/);
  assert.match(windowsJob, /uv run pytest -q/);
  assert.match(windowsJob, /tests\/test_native_core_broker_lifecycle\.py/);
  assert.match(windowsJob, /tests\/test_native_core_device_credential\.py/);
  assert.match(windowsJob, /tests\/test_wcdb_realtime_native_core_required\.py/);
  assert.doesNotMatch(windowsJob, /Prepare signed ephemeral Python test host/);
  assert.doesNotMatch(windowsJob, /WCE_PYTHON_TEST_HOST/);
  assert.doesNotMatch(windowsJob, /WECHAT_TOOL_NATIVE_CORE_(?:LIBRARY|BROKER)/);
  assert.match(windowsJob, /WCE_NATIVE_CORE_SOURCE_REVISION/);
  assert.match(windowsJob, /WCE_NATIVE_CORE_BUILD_ID/);
  assert.match(windowsJob, /WCE_NATIVE_CORE_ARTIFACT_SHA256/);
  assert.match(windowsJob, /WCE_NATIVE_CORE_ARTIFACT_READ_TOKEN/);
  assert.match(windowsJob, /gh release download \$releaseTag/);
  assert.match(
    windowsJob,
    /wechatdb-native-windows-x64-production-\$env:NATIVE_BUILD_ID\.zip/
  );
  assert.match(windowsJob, /Get-FileHash -LiteralPath \$archivePath -Algorithm SHA256/);
  assert.match(windowsJob, /Expand-Archive -LiteralPath \$archivePath/);
  assert.match(windowsJob, /WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH/);
  assert.match(windowsJob, /WCE_WINDOWS_PRIVATE_ROOT_SHA256/);
  assert.match(windowsJob, /WCE_RFC3161_TIMESTAMP_URL/);
  assert.match(windowsJob, /windows-private-pki-sign\.cjs preflight/);
  assert.match(windowsJob, /provenance\.json/);
  assert.match(windowsJob, /SHA256SUMS\.txt/);
  assert.match(windowsJob, /GitHub releases must not contain a recipient-bound distribution capsule/);
  assert.match(windowsJob, /GitHub releases require the shared public native distribution mode/);
  assert.match(windowsJob, /\$manifestFields -notcontains 'distributionMode'/);
  assert.match(windowsJob, /\$provenance\.build\.distributionMode -cne 'public'/);
  assert.match(windowsJob, /distributionMode = 'public'/);
  assert.match(windowsJob, /offlineBootstrapFeatureBits -ne 3/);
  assert.match(windowsJob, /nativeAsrAuthorization -cne 'database-read'/);
  assert.match(windowsJob, /nativeAsrAuthorization = 'database-read'/);
  assert.match(windowsJob, /offlineExportSealFormat -cne 'WES2'/);
  assert.match(windowsJob, /WCE-AUTOMATED-ANALYSIS-NOTICE-V2/);
  assert.match(windowsJob, /WCE-AI-CHECKPOINT-SET-V3/);
  assert.match(windowsJob, /securityCheckpointCount -ne 7/);
  assert.match(windowsJob, /securityCheckpointSetSha256 -cnotmatch/);
  assert.match(
    windowsJob,
    /\$provenance\.build\.securityCheckpointSetSha256 -cne\s+\$manifest\.securityCheckpointSetSha256/
  );
  assert.match(windowsJob, /WCE_NATIVE_CORE_SECURITY_NOTICE_SHA256/);
  assert.match(windowsJob, /WCE_NATIVE_CORE_SECURITY_CHECKPOINT_SET_SHA256/);
  assert.match(windowsJob, /windowsPrivatePkiLeafRevocation = 'build-and-lease-only'/);
  assert.doesNotMatch(
    windowsJob,
    /WCE_WINDOWS_CLIENT_CSC_LINK|WIN_CSC_KEY_PASSWORD|runs-on:\s*\[self-hosted|wce-production-signing|WCE_SIGNTOOL_PATH|[A-Z]:\\abc\\/i
  );
  assert.match(windowsJob, /Verify signed unpacked Windows runtime/);
  assert.match(windowsJob, /WCE_WINDOWS_INSTALLER_SMOKE_ALLOWED:\s*"1"/);
  assert.match(windowsJob, /run:\s*npm run smoke:win/);
  assert.match(windowsJob, /Run focused desktop release tests/);
  assert.match(windowsJob, /tests\/package-config\.test\.cjs/);
  assert.match(windowsJob, /tests\/native-core-before-pack\.test\.cjs/);
  assert.match(windowsJob, /tests\/native-core-packaging\.test\.cjs/);
  assert.match(windowsJob, /tests\/windows-package-smoke\.test\.cjs/);
  assert.match(windowsJob, /tests\/windows-private-pki-runtime\.test\.cjs/);
  assert.match(windowsJob, /tests\/windows-private-pki-sign\.test\.cjs/);
  assert.doesNotMatch(windowsJob, /tests\/\*\.test\.cjs/);
  assert.match(windowsJob, /Generate Windows release checksums and provenance/);
  assert.match(windowsJob, /Get-FileHash -Algorithm SHA256/);
  assert.match(windowsJob, /\[System\.Text\.Encoding\]::ASCII/);
  assert.match(windowsJob, /release-provenance\.json/);
  assert.match(windowsJob, /WDA_REPOSITORY:\s*\$\{\{ github\.repository \}\}/);
  assert.match(windowsJob, /WDA_REVISION:\s*\$\{\{ github\.sha \}\}/);
  assert.match(windowsJob, /WDA_TAG:\s*\$\{\{ github\.ref_name \}\}/);
  assert.match(windowsJob, /NATIVE_REPOSITORY:/);
  assert.match(windowsJob, /NATIVE_RUN_ID:/);
  assert.match(windowsJob, /NATIVE_REVISION:/);
  assert.match(windowsJob, /NATIVE_BUILD_ID:/);
  assert.match(windowsJob, /NATIVE_CLIENT_SIGNER_SHA256:/);
  assert.match(windowsJob, /NATIVE_BROKER_SIGNER_SHA256:/);
  assert.match(windowsJob, /WINDOWS_PRIVATE_ROOT_SHA256:/);
  assert.match(windowsJob, /WORKFLOW_RUN_ID:\s*\$\{\{ github\.run_id \}\}/);
  assert.match(windowsJob, /WORKFLOW_RUN_ATTEMPT:\s*\$\{\{ github\.run_attempt \}\}/);

  const downloadIndex = windowsJob.indexOf("gh release download $releaseTag");
  const archiveHashIndex = windowsJob.indexOf("Get-FileHash -LiteralPath $archivePath");
  const expandIndex = windowsJob.indexOf("Expand-Archive -LiteralPath $archivePath");
  const importIndex = windowsJob.indexOf("Import-WindowsCloudSigningIdentity.ps1");
  const validateIndex = windowsJob.indexOf("Validate native production artifact");
  const pythonDependenciesIndex = windowsJob.indexOf("Install Python dependencies");
  const pythonTestsIndex = windowsJob.indexOf("Run focused Python release tests");
  const buildIndex = windowsJob.indexOf("Build Windows installer");
  const uploadIndex = windowsJob.indexOf("Upload Windows release files");
  const cleanupIndex = windowsJob.indexOf("Remove-WindowsCloudSigningIdentity.ps1");
  assert.ok(downloadIndex >= 0 && downloadIndex < archiveHashIndex);
  assert.ok(archiveHashIndex < expandIndex && expandIndex < importIndex);
  assert.ok(importIndex < validateIndex);
  assert.ok(
    validateIndex < pythonDependenciesIndex && pythonDependenciesIndex < pythonTestsIndex
  );
  assert.ok(pythonTestsIndex < buildIndex && buildIndex < uploadIndex);
  assert.ok(uploadIndex < cleanupIndex);

  const importScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "Import-WindowsCloudSigningIdentity.ps1"),
    "utf8"
  );
  const cleanupScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "Remove-WindowsCloudSigningIdentity.ps1"),
    "utf8"
  );
  assert.match(importScript, /Microsoft Software Key Storage Provider/);
  assert.match(importScript, /AllowExport\|AllowPlaintextExport/);
  assert.match(importScript, /Import-PfxCertificate/);
  assert.match(importScript, /\[IO\.File\]::Delete\(\$pfxPath\)/);
  assert.match(cleanupScript, /Remove-Item -LiteralPath \$certificatePath -DeleteKey -Force/);

  const upload = windowsJob.match(/- name: Upload Windows release files\n([\s\S]*?)$/)?.[1] || "";
  assert.match(upload, /desktop\/dist\/\*Setup\*\.exe/);
  assert.match(upload, /desktop\/dist\/\*Setup\*\.exe\.blockmap/);
  assert.match(upload, /desktop\/dist\/latest\.yml/);
  assert.match(upload, /desktop\/dist\/SHA256SUMS\.txt/);
  assert.match(upload, /desktop\/dist\/release-provenance\.json/);
  assert.doesNotMatch(upload, /builder-debug\.yml/);
});

test("release workflow pins every remote action to an approved commit", () => {
  const workflow = fs
    .readFileSync(path.join(repoRoot, ".github", "workflows", "release.yml"), "utf8")
    .replace(/\r\n/g, "\n");
  const approved = new Map([
    ["actions/checkout", "11d5960a326750d5838078e36cf38b85af677262"],
    ["actions/setup-node", "49933ea5288caeca8642d1e84afbd3f7d6820020"],
    ["actions/setup-python", "a26af69be951a213d495a4c3e4e4022e16d87065"],
    ["actions/cache", "0057852bfaa89a56745cba8c7296529d2fc39830"],
    ["actions/download-artifact", "d3f86a106a0bac45b974a628896c90dbdf5c8093"],
    ["actions/upload-artifact", "ea165f8d65b6e75b540449e92b4886f43607fa02"],
    ["dtolnay/rust-toolchain", "4cda84d5c5c54efe2404f9d843567869ab1699d4"],
    ["softprops/action-gh-release", "3bb12739c298aeb8a4eeaf626c5b8d85266b0e65"],
    ["H3CoF6/qq-notify-action", "50d180981e7c7b8552a3331b981e3f8cfcf40c44"],
  ]);
  const remoteUses = [...workflow.matchAll(/^\s*uses:\s*([^\s#]+)(?:\s+#.*)?$/gm)]
    .map((match) => match[1])
    .filter((use) => !use.startsWith("./"));

  assert.ok(remoteUses.length > 0);
  for (const use of remoteUses) {
    const separator = use.lastIndexOf("@");
    const action = use.slice(0, separator);
    const revision = use.slice(separator + 1);
    assert.match(revision, /^[0-9a-f]{40}$/, `${use} is not pinned to a commit`);
    assert.equal(revision, approved.get(action), `${action} uses an unapproved commit`);
  }
  for (const action of [
    "actions/checkout",
    "actions/setup-node",
    "actions/setup-python",
    "actions/download-artifact",
    "actions/upload-artifact",
    "softprops/action-gh-release",
  ]) {
    assert.ok(remoteUses.includes(`${action}@${approved.get(action)}`), `${action} is missing`);
  }
});

test("Windows updater replaces public-chain verification with the pinned private-PKI policy", () => {
  const main = fs.readFileSync(path.join(desktopRoot, "src", "main.cjs"), "utf8");
  const verifier = fs.readFileSync(
    path.join(desktopRoot, "src", "windows-private-pki-runtime.cjs"),
    "utf8"
  );
  assert.match(main, /configurePrivatePkiUpdateVerification\(autoUpdater/);
  assert.match(verifier, /windowsPrivateRootSha256/);
  assert.match(verifier, /windowsClientSignerSha256/);
  assert.match(verifier, /verifyUpdateCodeSignature/);
  assert.match(verifier, /windows-private-pki\.ps1/);
});

test("macOS release config emits architecture-specific DMG and ZIP assets", () => {
  assert.deepEqual(packageJson.build.mac.target, ["dmg", "zip"]);
  assert.match(packageJson.build.mac.artifactName, /mac-\$\{arch\}/);
  assert.equal(packageJson.build.mac.hardenedRuntime, true);
  assert.equal(packageJson.build.mac.minimumSystemVersion, "15.0");
  assert.equal(packageJson.scripts["dist:mac"], "npm run dist:mac:arm64");
  assert.match(packageJson.scripts["dist:mac:arm64"], /verify:mac:native/);
  assert.match(packageJson.scripts["dist:mac:arm64"], /--arm64/);
  assert.doesNotMatch(packageJson.scripts["dist:mac:arm64"], /--x64|--universal/);
  assert.equal(packageJson.build.afterPack, "scripts/after-pack.cjs");
  assert.equal(packageJson.build.afterSign, "scripts/after-sign.cjs");
  assert.equal(packageJson.build.mac.sign, "scripts/sign-macos.cjs");
  assert.match(packageJson.scripts["dist:mac:arm64:release"], /MACOS_DISTRIBUTION_BUILD=1/);
  assert.match(packageJson.scripts["dist:mac:arm64:release"], /forceCodeSigning=true/);
});

test("macOS release exposes a reusable packaged smoke test", () => {
  const smokeScript = path.join(desktopRoot, "scripts", "smoke-macos-package.cjs");
  assert.equal(packageJson.scripts["smoke:mac"], "node scripts/smoke-macos-package.cjs");
  assert.equal(
    packageJson.scripts["smoke:mac:image-scan"],
    "node scripts/smoke-macos-package.cjs --synthetic-image-scan"
  );
  assert.equal(
    packageJson.scripts["verify:mac:distribution"],
    "node scripts/verify-macos-distribution.cjs"
  );
  assert.ok(fs.existsSync(smokeScript), smokeScript);
  const smokeSource = fs.readFileSync(smokeScript, "utf8");
  assert.match(smokeSource, /libwechatdb_client\.dylib/);
  assert.match(smokeSource, /wechatdb_native_build\.json/);
  assert.match(smokeSource, /macosXkeyContract/);
  assert.match(smokeSource, /database_key_online_authorization_required/);
  assert.match(smokeSource, /\/api\/health/);
  assert.doesNotMatch(smokeSource, /require\(["']koffi["']\)/);
  assert.doesNotMatch(smokeSource, /sidecarProc|sidecarPort|sidecarToken/);
});

test("packaged macOS startup establishes pinned user trust before launching the backend", () => {
  const mainSource = fs.readFileSync(path.join(desktopRoot, "src", "main.cjs"), "utf8");
  const mainStart = mainSource.indexOf("async function main()");
  const trustCall = mainSource.indexOf(
    "const evidence = ensureMacosPrivatePkiTrust",
    mainStart
  );
  const backendLaunch = mainSource.indexOf("await ensureMainWindowReady()", mainStart);

  assert.ok(mainStart >= 0);
  assert.ok(trustCall > mainStart, "macOS private-PKI trust bootstrap is not wired into main startup");
  assert.ok(backendLaunch > trustCall, "backend can launch before macOS private-PKI trust is ready");
});

test("macOS native resources expose reproducible build and architecture verification", () => {
  const buildScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "build-macos-image-helper.cjs"),
    "utf8"
  );
  const verifyScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "verify-macos-native.cjs"),
    "utf8"
  );

  assert.equal(
    packageJson.scripts["build:mac:image-helper"],
    "node scripts/build-macos-image-helper.cjs"
  );
  assert.equal(
    packageJson.scripts["verify:mac:native"],
    "node scripts/verify-macos-native.cjs --arch arm64 --require-host-arch"
  );
  assert.match(buildScript, /MACOSX_DEPLOYMENT_TARGET/);
  assert.match(buildScript, /-mmacosx-version-min=/);
  assert.match(buildScript, /"arm64"/);
  assert.match(buildScript, /"x86_64"/);
  assert.match(verifyScript, /only arm64 is complete/);
  assert.match(verifyScript, /maximumNativeMinOS/);
  assert.match(verifyScript, /ffmpeg-static/);
  assert.match(verifyScript, /resolveNativeCoreArtifacts\(\{[\s\S]*platform:\s*"darwin"/);
  for (const resource of [
    "libwechatdb_client.dylib",
    "wechatdb_broker",
    "wechatdb_native_build.json",
    "libwx_key.dylib",
    "image_scan_helper",
  ]) {
    assert.match(verifyScript, new RegExp(resource.replace(".", "\\.")));
  }
  for (const retiredResource of [
    "libwcdb_api.dylib",
    "libWCDB.dylib",
    "koffi",
    "InitProtection",
    "wcdb_open_account",
  ]) {
    assert.doesNotMatch(verifyScript, new RegExp(retiredResource.replace(".", "\\.")));
  }
});

test("macOS image helper manifest locks source inputs and the tracked artifact", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(desktopRoot, "scripts", "macos-image-helper-manifest.json"), "utf8")
  );
  const digest = (filePath, { normalizeText = false } = {}) => {
    const raw = fs.readFileSync(filePath);
    const content = normalizeText
      ? Buffer.from(raw.toString("utf8").replace(/\r\n/g, "\n"), "utf8")
      : raw;
    return crypto.createHash("sha256").update(content).digest("hex");
  };

  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.deploymentTarget, "15.0");
  assert.deepEqual(manifest.architectures, ["arm64", "x86_64"]);
  for (const entry of manifest.inputs) {
    const filePath = path.join(repoRoot, entry.path);
    assert.ok(fs.existsSync(filePath), filePath);
    assert.equal(digest(filePath, { normalizeText: true }), entry.sha256, entry.path);
  }
  const artifactPath = path.join(repoRoot, manifest.artifact.path);
  assert.ok(fs.existsSync(artifactPath), artifactPath);
  assert.equal(digest(artifactPath), manifest.artifact.sha256, manifest.artifact.path);
});

test("macOS helper package probe uses a nonexistent PID and a hard timeout", () => {
  const smokeScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "smoke-macos-package.cjs"),
    "utf8"
  );

  assert.match(smokeScript, /\["2147483647", "0"\.repeat\(32\)\]/);
  assert.match(smokeScript, /timeout:\s*5_000/);
  assert.match(smokeScript, /assert\.ifError\(imageHelperProbe\.error\)/);
});

test("macOS package smoke performs a real image-key memory scan", () => {
  const smokeScript = fs.readFileSync(
    path.join(desktopRoot, "scripts", "smoke-macos-package.cjs"),
    "utf8"
  );

  assert.match(smokeScript, /IMAGE_KEY_MAPPING_ADDRESS/);
  assert.match(smokeScript, /0x1000000ULL/);
  assert.match(smokeScript, /mach_vm_allocate/);
  assert.match(smokeScript, /VM_FLAGS_FIXED/);
  assert.doesNotMatch(smokeScript, /MAP_FIXED/);
  assert.match(smokeScript, /-Wl,-pagezero_size,0x1000000/);
  assert.doesNotMatch(smokeScript, /-Wl,-no_pie|-Wl,-segaddr/);
  assert.match(smokeScript, /_dyld_get_image_header\(0\)/);
  assert.match(smokeScript, /memcpy\(\(void \*\)\(uintptr_t\)image_key_mapping, "0123456789abcdef", 16\)/);
  assert.match(smokeScript, /ready mapping=0x%llx image=0x%llx/);
  assert.match(smokeScript, /createCipheriv\("aes-128-ecb"/);
  assert.match(smokeScript, /spawnSync\(imageHelper/);
  assert.match(smokeScript, /Buffer\.from\(helperPayload\.aesKey, "hex"\)/);
  assert.match(smokeScript, /if \(runSyntheticImageScan\)/);
  assert.match(smokeScript, /await probePackagedImageScanner\(imageHelper, tempRoot\)/);
  assert.match(smokeScript, /SYNTHETIC_IMAGE_SCAN_FLAG = "--synthetic-image-scan"/);
  assert.match(smokeScript, /timeout: 30_000/);
  assert.match(smokeScript, /30-second production budget/);

  const workflow = fs.readFileSync(
    path.join(repoRoot, ".github", "workflows", "macos-private-build.yml"),
    "utf8"
  );
  assert.match(workflow, /run_image_scan_diagnostic:/);
  assert.match(workflow, /if: \$\{\{ inputs\.run_image_scan_diagnostic \}\}/);
  assert.match(workflow, /continue-on-error: true/);
  assert.match(workflow, /npm run smoke:mac:image-scan/);
});

test("unsigned macOS CI packages are ad-hoc sealed before DMG creation", () => {
  const afterPack = fs.readFileSync(path.join(desktopRoot, "scripts", "after-pack.cjs"), "utf8");

  assert.match(afterPack, /electronPlatformName !== "darwin"/);
  assert.match(afterPack, /"--deep"/);
  assert.match(afterPack, /"--options",\s*\n\s*"runtime"/);
  assert.match(afterPack, /codesign.*--verify/s);
  assert.match(afterPack, /MACOS_DISTRIBUTION_BUILD/);
});

test("macOS signing keeps debugger entitlement off the app and on capture helpers", () => {
  const appEntitlements = fs.readFileSync(path.join(desktopRoot, "entitlements.mac.plist"), "utf8");
  const helperEntitlements = fs.readFileSync(
    path.join(repoRoot, "src", "wechat_decrypt_tool", "native", "macos", "source", "image_scan_entitlements.plist"),
    "utf8"
  );
  const signer = fs.readFileSync(path.join(desktopRoot, "scripts", "sign-macos.cjs"), "utf8");
  const afterSign = fs.readFileSync(path.join(desktopRoot, "scripts", "after-sign.cjs"), "utf8");

  assert.doesNotMatch(appEntitlements, /com\.apple\.security\.get-task-allow/);
  assert.doesNotMatch(appEntitlements, /com\.apple\.security\.cs\.debugger/);
  assert.match(helperEntitlements, /com\.apple\.security\.cs\.debugger/);
  assert.match(signer, /image_scan_helper/);
  assert.match(signer, /helperEntitlements/);
  assert.match(afterSign, /stapler.*staple/s);
  assert.match(afterSign, /Developer ID Application/);
});

test("macOS archive verification checks ZIP, mounted DMG, signing, and distribution policy", () => {
  const verifier = fs.readFileSync(path.join(desktopRoot, "scripts", "macos-package-verifier.cjs"), "utf8");
  const smoke = fs.readFileSync(path.join(desktopRoot, "scripts", "smoke-macos-package.cjs"), "utf8");

  assert.match(verifier, /ditto/);
  assert.match(verifier, /hdiutil/);
  assert.match(verifier, /codesign/);
  assert.match(verifier, /Developer ID Application/);
  assert.match(verifier, /syspolicy_check/);
  assert.match(verifier, /stapler/);
  assert.match(verifier, /withMacosArtifacts/);
  assert.match(verifier, /macosXkeyContract\.checksumsFileName/);
  assert.match(verifier, /macosXkeyContract\.provenanceFileName/);
  assert.match(verifier, /macosXkeyContract\.thirdPartyNoticeFileName/);
  assert.match(verifier, /macos-private-pki-root\.cer/);
  assert.match(verifier, /macosPrivateRootSha256/);
  assert.match(verifier, /\["-d", "--entitlements", ":-", xkeyHelper\]/);
  assert.match(verifier, /assert\.match\(xkeyEntitlements, \/com\\\.apple\\\.security\\\.cs\\\.debugger\//);
  assert.match(smoke, /\["-d", "--entitlements", ":-", xkeyHelper\]/);
  assert.match(smoke, /resolveMacosPrivatePkiRuntime/);
  assert.match(
    verifier,
    /validatePackagedBackend\(\{ backendDir: backendRoot, platform: "darwin" \}\)/
  );
  for (const nativeCoreResource of [
    "libwechatdb_client.dylib",
    "wechatdb_broker",
    "wechatdb_native_build.json",
  ]) {
    assert.match(verifier, new RegExp(nativeCoreResource.replace(".", "\\.")));
  }
  assert.match(verifier, /requireArchitectures\(nativeClient, \["arm64"\]\)/);
  assert.match(verifier, /requireArchitectures\(nativeBroker, \["arm64"\]\)/);
  assert.match(verifier, /requireCompatibleMinimumOs\(filePath\)/);
  assert.match(
    verifier,
    /codesign", \["--verify", "--strict", "--verbose=2", nativeClient\]/
  );
  assert.match(
    verifier,
    /codesign", \["--verify", "--strict", "--verbose=2", nativeBroker\]/
  );
  const retiredVerifierBlock = verifier.match(
    /for \(const retiredPath of \[([\s\S]*?)\]\) \{([\s\S]*?)\n  \}/
  )?.[0] || "";
  for (const retiredResource of ["libwcdb_api.dylib", "libWCDB.dylib", "wcdb-sidecar.cjs", "koffi"]) {
    assert.match(retiredVerifierBlock, new RegExp(retiredResource.replace(".", "\\.")));
  }
  assert.match(
    retiredVerifierBlock,
    /assert\.equal\(fs\.existsSync\(retiredPath\), false, `Retired WCDB runtime was packaged:/
  );
  const retiredSmokeBlock = smoke.match(
    /for \(const retiredPath of \[([\s\S]*?)\]\) \{([\s\S]*?)\n  \}/
  )?.[0] || "";
  for (const retiredResource of ["libwcdb_api.dylib", "libWCDB.dylib", "wcdb-sidecar.cjs", "koffi"]) {
    assert.match(retiredSmokeBlock, new RegExp(retiredResource.replace(".", "\\.")));
  }
  const xkeyContract = JSON.parse(fs.readFileSync(
    path.join(repoRoot, "src", "wechat_decrypt_tool", "resources", "macos_db_key_contract.json"),
    "utf8"
  ));
  for (const [, field] of verifier.matchAll(/macosXkeyContract\.([A-Za-z0-9_]+)/g)) {
    assert.ok(Object.hasOwn(xkeyContract, field), `unknown macOS Xkey contract field: ${field}`);
  }
  assert.match(smoke, /withMacosArtifacts\(\{ distribution: false \}, async \(\{ zipAppPath \}\)/);
  assert.match(smoke, /runPackagedRuntimeSmoke\(zipAppPath\)/);
  assert.doesNotMatch(smoke, /findPackagedApp/);
});

test("macOS DMG cleanup retries a busy mount with force detach", () => {
  const calls = [];
  detachMountedDmg("/tmp/wda-mounted-dmg", (command, args) => {
    calls.push([command, args]);
    if (!args.includes("-force")) throw new Error("normal detach: resource busy");
  });

  assert.deepEqual(calls, [
    ["hdiutil", ["detach", "/tmp/wda-mounted-dmg"]],
    ["hdiutil", ["detach", "-force", "/tmp/wda-mounted-dmg"]],
  ]);
});

test("macOS DMG cleanup preserves both detach failures", () => {
  assert.throws(
    () => detachMountedDmg("/tmp/wda-mounted-dmg", (command, args) => {
      const mode = args.includes("-force") ? "forced" : "normal";
      throw new Error(`${command} ${mode} detach output`);
    }),
    (error) => {
      assert.ok(error instanceof AggregateError);
      assert.equal(error.errors.length, 2);
      assert.match(error.message, /hdiutil normal detach output/);
      assert.match(error.message, /hdiutil forced detach output/);
      assert.match(error.message, /mount directory was preserved/);
      return true;
    }
  );
});

test("tag release reuses the protected macOS build and publishes both platforms", () => {
  const workflow = fs
    .readFileSync(path.join(repoRoot, ".github", "workflows", "release.yml"), "utf8")
    .replace(/\r\n/g, "\n");
  const publishJob = workflow.split("\n  publish-release:\n", 2)[1] || "";

  assert.match(workflow, /^name: Release \(Windows and macOS ARM64\)$/m);
  assert.match(
    workflow,
    /\n  build-macos-arm64:\n\s+uses: \.\/\.github\/workflows\/macos-private-build\.yml\n\s+secrets: inherit/
  );
  assert.doesNotMatch(workflow, /native\/wce_integrity/);
  assert.doesNotMatch(workflow, /npm run dist:mac|npm run smoke:mac/);
  assert.match(publishJob, /needs:\s*\n\s*- build-windows/);
  assert.match(publishJob, /needs:[\s\S]*- build-macos-arm64/);
  assert.match(publishJob, /merge-multiple: true/);
});

test("Windows packages are built only by the tag-triggered release workflow", () => {
  const workflowsDir = path.join(repoRoot, ".github", "workflows");
  const workflow = fs
    .readFileSync(path.join(workflowsDir, "release.yml"), "utf8")
    .replace(/\r\n/g, "\n");

  // Desktop packaging is expensive; keep it off pull requests and main pushes.
  assert.match(workflow, /^on:\n  push:\n    tags:\n      - "v\*"\n/m);
  assert.match(workflow, /\n  build-windows:\n/);
  assert.match(workflow, /\n  build-macos-arm64:\n/);

  for (const entry of fs.readdirSync(workflowsDir)) {
    const source = fs.readFileSync(path.join(workflowsDir, entry), "utf8");
    if (!/npm run (?:dist|smoke):win/.test(source)) continue;
    assert.equal(
      entry,
      "release.yml",
      `${entry} packages the desktop app outside the tag-triggered release workflow`
    );
  }
});

test("macOS native window controls reserve the sidebar title-bar area", () => {
  const preload = fs.readFileSync(path.join(desktopRoot, "src", "preload.cjs"), "utf8");
  const main = fs.readFileSync(path.join(desktopRoot, "src", "main.cjs"), "utf8");
  const sidebar = fs.readFileSync(path.join(repoRoot, "frontend", "components", "SidebarRail.vue"), "utf8");

  assert.match(preload, /platform:\s*process\.platform/);
  assert.match(main, /titleBarStyle:\s*"hiddenInset"/);
  assert.match(main, /trafficLightPosition/);
  assert.match(sidebar, /isMacosDesktop/);
  assert.match(sidebar, /macos-sidebar-titlebar-spacer/);
  assert.match(sidebar, /--desktop-titlebar-height/);
});

test("frontend joins copied output paths using the native path style", async () => {
  const modulePath = path.join(repoRoot, "frontend", "lib", "native-path.js");
  const { joinNativePath } = await import(pathToFileURL(modulePath).href);

  assert.equal(joinNativePath("/Users/demo/output/", "wxid_demo"), "/Users/demo/output/wxid_demo");
  assert.equal(joinNativePath("D:\\wechat\\output\\", "wxid_demo"), "D:\\wechat\\output\\wxid_demo");
  assert.equal(joinNativePath("\\\\server\\share\\output", "wxid_demo"), "\\\\server\\share\\output\\wxid_demo");
});
