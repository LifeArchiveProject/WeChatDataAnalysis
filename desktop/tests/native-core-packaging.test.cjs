const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  nativeCoreArtifactNames,
  nativeCoreProductionManifestErrors,
  prepareRuntimeNativeDir,
  resolveNativeCoreArtifacts,
  stageNativeCoreArtifacts,
} = require("../scripts/build-backend.cjs");
const {
  WINDOWS_NATIVE_ASR_ABI_VERSION,
  WINDOWS_NATIVE_ASR_AUTHORIZATION,
  WINDOWS_NATIVE_ASR_EXPORTS,
  WINDOWS_NATIVE_ASR_FEATURE_BIT,
  WINDOWS_NATIVE_ASR_TARGET,
} = require("../src/windows-native-asr-capability.cjs");
const { buildWindowsPeWithExports } = require("./pe-export-fixture.cjs");
const { PRODUCER_WORKFLOW } = require("../scripts/linux-native-core-packaging.cjs");

const BUILD_ISSUED_AT_UNIX = Math.floor(Date.now() / 1000) - 60;
const BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const PRODUCTION_MANIFEST = Object.freeze({
  schemaVersion: 2,
  distributionMode: "public",
  buildId: "release-2026.07.27",
  buildIssuedAtUnix: BUILD_ISSUED_AT_UNIX,
  buildExpiresAtUnix: BUILD_ISSUED_AT_UNIX + BUILD_LIFETIME_SECONDS,
  readOnlyBuild: true,
  wechatActions: [],
  developmentBuild: false,
  offlineBootstrapFeatureBits: 3,
  offlineExportSealFormat: "WES2",
  codeSignatureEnforced: true,
  rootPublicKeyCompiled: true,
  testHooksEnabled: false,
  stagingPinnedSignerTrust: false,
  windowsSignerTrustMode: "private-pki",
  windowsPrivatePkiLeafRevocation: "build-and-lease-only",
  windowsClientSignerSha256: "11".repeat(32),
  windowsBrokerSignerSha256: "22".repeat(32),
  windowsPrivateRootSha256: "33".repeat(32),
  securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
  securityNoticeSha256: "aa".repeat(32),
  securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
  securityCheckpointCount: 7,
  securityCheckpointSetSha256: "bb".repeat(32),
  nativeAsrAbiVersion: WINDOWS_NATIVE_ASR_ABI_VERSION,
  nativeAsrAuthorization: WINDOWS_NATIVE_ASR_AUTHORIZATION,
  nativeAsrFeatureBit: WINDOWS_NATIVE_ASR_FEATURE_BIT,
  nativeAsrTarget: WINDOWS_NATIVE_ASR_TARGET,
});

const DEVELOPMENT_MANIFEST = Object.freeze({
  schemaVersion: 2,
  distributionMode: "public",
  buildId: "dev-local",
  readOnlyBuild: true,
  wechatActions: [],
  developmentBuild: true,
  offlineBootstrapFeatureBits: 0,
  offlineExportSealFormat: "none",
  codeSignatureEnforced: false,
  rootPublicKeyCompiled: false,
  testHooksEnabled: true,
  stagingPinnedSignerTrust: false,
  windowsSignerTrustMode: "public",
  windowsPrivatePkiLeafRevocation: "not-applicable",
  securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
  securityNoticeSha256: "aa".repeat(32),
  securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
  securityCheckpointCount: 7,
  securityCheckpointSetSha256: "bb".repeat(32),
  nativeAsrAbiVersion: 0,
  nativeAsrAuthorization: "none",
  nativeAsrFeatureBit: 0,
  nativeAsrTarget: { wechatVersion: "", weixinSha256: "" },
});

const MACOS_DEVELOPMENT_MANIFEST = Object.freeze({
  schemaVersion: 3,
  platform: "macos",
  distributionMode: "public",
  buildId: "dev-local",
  buildIssuedAtUnix: 0,
  buildExpiresAtUnix: 0,
  developmentBuild: true,
  offlineBootstrapFeatureBits: 0,
  offlineExportSealFormat: "none",
  codeSignatureEnforced: false,
  rootPublicKeyCompiled: false,
  testHooksEnabled: true,
  stagingPinnedSignerTrust: false,
  macosSigningMode: "self-signed",
  macosSignerTrustMode: "development",
  macosPrivatePkiLeafRevocation: "not-applicable",
  macosClientSigningIdentifier: "com.lifearchive.wechatdb.client",
  macosBrokerSigningIdentifier: "com.lifearchive.wechatdb.broker",
  macosHostSigningIdentifier: "com.lifearchive.wechatdataanalysis.backend",
  macosClientSignerSha256: "0".repeat(64),
  macosBrokerSignerSha256: "0".repeat(64),
  macosHostSignerSha256: "0".repeat(64),
  macosPrivateRootSha256: "0".repeat(64),
  securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
  securityNoticeSha256: "aa".repeat(32),
  securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
  securityCheckpointCount: 7,
  securityCheckpointSetSha256: "bb".repeat(32),
});

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "wda-native-package-"));
}

function writeArtifactSet(
  root,
  platform,
  manifest,
  { clientExports = WINDOWS_NATIVE_ASR_EXPORTS, omit = [] } = {}
) {
  fs.mkdirSync(root, { recursive: true });
  for (const name of nativeCoreArtifactNames(platform)) {
    if (omit.includes(name) || name === "wechatdb_native_build.json") continue;
    const content =
      platform === "win32" && name === "wechatdb_client.dll"
        ? buildWindowsPeWithExports(clientExports)
        : `fixture:${name}`;
    fs.writeFileSync(path.join(root, name), content);
  }
  if (!omit.includes("wechatdb_native_build.json")) {
    fs.writeFileSync(path.join(root, "wechatdb_native_build.json"), JSON.stringify(manifest));
  }
}

function quietLogger() {
  return { log() {}, warn() {} };
}

// ---- Linux（schema v4）固定件 -------------------------------------------------
// Linux 没有代码签名，产物身份 = 内容哈希，所以固定件必须把哈希算对，
// 否则测的就不是「校验逻辑」而是「固定件写错了」。
const LINUX_BUILD_ISSUED_AT_UNIX = Math.floor(Date.now() / 1000) - 60;
const LINUX_REPOSITORY = "LifeArchiveProject/WCDB";
const LINUX_SOURCE_REVISION = "a8f42de851a34365834e566bf587089af5df7c19";
const LINUX_BUILD_ID = "linux-x64-release-2026.09.16";

function sha256Hex(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

// 最小可用 ELF 头：测试只需要 64 位 / 小端 / x86-64 / 类型正确。
function linuxElfBytes(type) {
  const buffer = Buffer.alloc(64);
  buffer.write("\x7fELF", 0, "latin1");
  buffer[4] = 2;
  buffer[5] = 1;
  buffer.writeUInt16LE(type, 16);
  buffer.writeUInt16LE(0x3e, 18);
  return buffer;
}

function linuxManifest({ sourceRuntime = true, overrides = {} } = {}) {
  return {
    schemaVersion: 4,
    platform: "linux",
    distributionMode: "public",
    buildId: LINUX_BUILD_ID,
    buildIssuedAtUnix: LINUX_BUILD_ISSUED_AT_UNIX,
    buildExpiresAtUnix: LINUX_BUILD_ISSUED_AT_UNIX + BUILD_LIFETIME_SECONDS,
    developmentBuild: false,
    offlineBootstrapFeatureBits: 3,
    offlineExportSealFormat: "WES2",
    codeSignatureEnforced: true,
    rootPublicKeyCompiled: true,
    testHooksEnabled: false,
    stagingPinnedSignerTrust: false,
    linuxIntegrityMode: "content-hash-pin",
    linuxClientSha256: "",
    linuxBrokerSha256: "",
    linuxPeerVerification: "same-user-peer-credentials",
    linuxHostVerification: sourceRuntime ? "same-user-direct-parent" : "content-hash-pin",
    securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
    securityNoticeSha256: "aa".repeat(32),
    securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
    securityCheckpointCount: 7,
    securityCheckpointSetSha256: "bb".repeat(32),
    ...(sourceRuntime ? { sourceRuntime: true } : {}),
    ...overrides,
  };
}

const LINUX_CHECKSUM_FILE_NAMES = [
  "Test-LinuxNativeProductionArtifact.py",
  "libwechatdb_client.so",
  "wechatdb_broker",
  "wechatdb_native_build.json",
];

function writeLinuxArtifactSet(
  root,
  { sourceRuntime = true, manifestOverrides = {}, provenanceOverrides = {}, tamperClient = false } = {}
) {
  fs.mkdirSync(root, { recursive: true });
  const clientName = "libwechatdb_client.so";
  const brokerName = "wechatdb_broker";
  const manifestName = "wechatdb_native_build.json";
  const clientBytes = linuxElfBytes(3);
  const brokerBytes = linuxElfBytes(2);

  const manifest = linuxManifest({ sourceRuntime, overrides: manifestOverrides });
  manifest.linuxClientSha256 = sha256Hex(clientBytes);
  manifest.linuxBrokerSha256 = sha256Hex(brokerBytes);
  Object.assign(manifest, manifestOverrides);

  fs.writeFileSync(path.join(root, clientName), clientBytes);
  fs.writeFileSync(path.join(root, brokerName), brokerBytes);
  fs.writeFileSync(path.join(root, "Test-LinuxNativeProductionArtifact.py"), "# fixture\n");
  fs.writeFileSync(path.join(root, manifestName), JSON.stringify(manifest, null, 2));

  const checksums = LINUX_CHECKSUM_FILE_NAMES.map(
    (name) => `${sha256Hex(fs.readFileSync(path.join(root, name)))}  ${name}`
  ).join("\n") + "\n";
  fs.writeFileSync(path.join(root, "SHA256SUMS.txt"), checksums);

  const provenance = {
    schemaVersion: 1,
    artifactName: "wechatdb-native-linux-x64-source-public",
    producer: "manual",
    workflow: "manual",
    repository: LINUX_REPOSITORY,
    runId: 0,
    runAttempt: 0,
    sourceRevision: LINUX_SOURCE_REVISION,
    build: {
      architecture: "x64",
      distributionMode: manifest.distributionMode,
      expiresAtUnix: manifest.buildExpiresAtUnix,
      id: manifest.buildId,
      integrityMode: manifest.linuxIntegrityMode,
      issuedAtUnix: manifest.buildIssuedAtUnix,
      linuxBrokerSha256: manifest.linuxBrokerSha256,
      linuxClientSha256: manifest.linuxClientSha256,
      offlineBootstrapFeatureBits: manifest.offlineBootstrapFeatureBits,
      offlineExportSealFormat: manifest.offlineExportSealFormat,
      platform: "linux",
      readOnlyBuild: true,
      securityCheckpointCount: manifest.securityCheckpointCount,
      securityCheckpointSetId: manifest.securityCheckpointSetId,
      securityCheckpointSetSha256: manifest.securityCheckpointSetSha256,
      securityNoticeId: manifest.securityNoticeId,
      securityNoticeSha256: manifest.securityNoticeSha256,
      ...(sourceRuntime
        ? { linuxHostVerification: manifest.linuxHostVerification, sourceRuntime: true }
        : {}),
      ...(provenanceOverrides.build || {}),
    },
    manifestSha256: sha256Hex(fs.readFileSync(path.join(root, manifestName))),
    checksumsSha256: sha256Hex(fs.readFileSync(path.join(root, "SHA256SUMS.txt"))),
    artifacts: LINUX_CHECKSUM_FILE_NAMES.map((name) => ({
      path: name,
      sha256: sha256Hex(fs.readFileSync(path.join(root, name))),
      size: fs.statSync(path.join(root, name)).size,
    })),
  };
  const { build: _ignoredBuild, ...provenanceTopLevel } = provenanceOverrides;
  Object.assign(provenance, provenanceTopLevel);
  fs.writeFileSync(path.join(root, "provenance.json"), JSON.stringify(provenance, null, 2));

  if (tamperClient) {
    // 密封之后再改字节：SHA256SUMS / provenance 仍然声称原始哈希。
    const bytes = Buffer.from(fs.readFileSync(path.join(root, clientName)));
    bytes[40] ^= 0xff;
    fs.writeFileSync(path.join(root, clientName), bytes);
  }
  return { manifest, provenance };
}

function linuxEnv(artifactDir, overrides = {}) {
  return {
    WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir,
    WCE_NATIVE_CORE_ARTIFACT_REPOSITORY: LINUX_REPOSITORY,
    WCE_NATIVE_CORE_SOURCE_REVISION: LINUX_SOURCE_REVISION,
    WCE_NATIVE_CORE_BUILD_ID: LINUX_BUILD_ID,
    ...overrides,
  };
}

test("artifact names are platform-specific and complete", () => {
  assert.deepEqual(nativeCoreArtifactNames("win32"), [
    "wechatdb_client.dll",
    "wechatdb_broker.exe",
    "wechatdb_native_build.json",
  ]);
  assert.deepEqual(nativeCoreArtifactNames("darwin"), [
    "libwechatdb_client.dylib",
    "wechatdb_broker",
    "wechatdb_native_build.json",
  ]);
  assert.deepEqual(nativeCoreArtifactNames("linux"), [
    "libwechatdb_client.so",
    "wechatdb_broker",
    "wechatdb_native_build.json",
  ]);
});

test("runtime staging filters checked-out native and legacy WCDB files", () => {
  const root = makeTempDir();
  const source = path.join(root, "source");
  const destination = path.join(root, "stage");
  fs.mkdirSync(path.join(source, "nested"), { recursive: true });
  fs.mkdirSync(path.join(source, "__pycache__"), { recursive: true });
  fs.writeFileSync(path.join(source, "ordinary.dll"), "ordinary");
  fs.writeFileSync(path.join(source, "wechatdb_client.dll"), "unchecked");
  fs.writeFileSync(path.join(source, "wechatdb_broker.exe"), "unchecked");
  fs.writeFileSync(path.join(source, "wechatdb_native_build.json"), "unchecked");
  fs.writeFileSync(path.join(source, "wcdb_api.dll"), "legacy");
  fs.writeFileSync(path.join(source, "WCDB.dll"), "legacy-dependency");
  fs.writeFileSync(path.join(source, "libwcdb_api.dylib"), "legacy-macos");
  fs.writeFileSync(path.join(source, "libWCDB.dylib"), "legacy-macos-dependency");
  fs.writeFileSync(path.join(source, "wechat_native_asr_manifest.json"), "retired");
  fs.writeFileSync(path.join(source, "wechat_native_asr_python_transport.py"), "retired");
  fs.writeFileSync(path.join(source, "wechat_native_asr_weixin_hook.dll"), "retired");
  fs.writeFileSync(
    path.join(source, "__pycache__", "wechat_native_asr_python_transport.cpython-312.pyc"),
    "retired-bytecode"
  );
  fs.writeFileSync(path.join(source, "nested", "resource.bin"), "nested");

  try {
    prepareRuntimeNativeDir(source, destination);
    assert.ok(fs.existsSync(path.join(destination, "ordinary.dll")));
    assert.ok(fs.existsSync(path.join(destination, "nested", "resource.bin")));
    assert.equal(fs.existsSync(path.join(destination, "wechatdb_client.dll")), false);
    assert.equal(fs.existsSync(path.join(destination, "wechatdb_broker.exe")), false);
    assert.equal(fs.existsSync(path.join(destination, "wechatdb_native_build.json")), false);
    assert.equal(fs.existsSync(path.join(destination, "wcdb_api.dll")), false);
    assert.equal(fs.existsSync(path.join(destination, "WCDB.dll")), false);
    assert.equal(fs.existsSync(path.join(destination, "libwcdb_api.dylib")), false);
    assert.equal(fs.existsSync(path.join(destination, "libWCDB.dylib")), false);
    assert.equal(fs.existsSync(path.join(destination, "wechat_native_asr_manifest.json")), false);
    assert.equal(fs.existsSync(path.join(destination, "wechat_native_asr_python_transport.py")), false);
    assert.equal(fs.existsSync(path.join(destination, "wechat_native_asr_weixin_hook.dll")), false);
    assert.equal(fs.existsSync(path.join(destination, "__pycache__")), false);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("supported-platform packaging always requires an explicit artifact directory", () => {
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: {}, platform: "win32" }),
    /Missing WCE_NATIVE_CORE_ARTIFACT_DIR/
  );
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: { WCE_NATIVE_CORE_REQUIRED: "1" }, platform: "win32" }),
    /Missing WCE_NATIVE_CORE_ARTIFACT_DIR/
  );
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: { WECHAT_TOOL_NATIVE_CORE_MODE: "required" }, platform: "darwin" }),
    /Missing WCE_NATIVE_CORE_ARTIFACT_DIR/
  );
});

test("an explicit partial directory fails instead of falling back", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "partial");
  writeArtifactSet(artifactDir, "win32", PRODUCTION_MANIFEST, { omit: ["wechatdb_broker.exe"] });

  try {
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
          platform: "win32",
        }),
      /Incomplete WCE_NATIVE_CORE_ARTIFACT_DIR.*wechatdb_broker\.exe/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("production staging copies the complete Windows trio", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  const destination = path.join(root, "stage");
  fs.mkdirSync(destination, { recursive: true });
  writeArtifactSet(artifactDir, "win32", PRODUCTION_MANIFEST);

  try {
    const result = stageNativeCoreArtifacts({
      destinationDir: destination,
      env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir, WCE_NATIVE_CORE_REQUIRED: "true" },
      logger: quietLogger(),
      platform: "win32",
    });

    assert.equal(result.staged, true);
    assert.equal(result.allowDevelopment, false);
    assert.equal(result.manifest.buildId, PRODUCTION_MANIFEST.buildId);
    for (const name of nativeCoreArtifactNames("win32")) {
      assert.ok(fs.statSync(path.join(destination, name)).isFile(), name);
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Windows staging rejects a manifest without the fused ASR contract", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  const legacyManifest = { ...PRODUCTION_MANIFEST };
  delete legacyManifest.nativeAsrAbiVersion;
  delete legacyManifest.nativeAsrAuthorization;
  delete legacyManifest.nativeAsrFeatureBit;
  delete legacyManifest.nativeAsrTarget;
  writeArtifactSet(artifactDir, "win32", legacyManifest);

  try {
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
          platform: "win32",
        }),
      /nativeAsrAbiVersion must equal 1.*nativeAsrFeatureBit must equal 16.*nativeAsrAuthorization must equal database-read.*nativeAsrTarget must be an object/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Windows staging rejects a fused ASR runtime with a separate entitlement contract", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  writeArtifactSet(artifactDir, "win32", {
    ...PRODUCTION_MANIFEST,
    nativeAsrAuthorization: "native-asr",
  });

  try {
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
          platform: "win32",
        }),
      /nativeAsrAuthorization must equal database-read/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Windows staging rejects an otherwise valid client without fused ASR exports", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  writeArtifactSet(artifactDir, "win32", PRODUCTION_MANIFEST, {
    clientExports: ["wce_client_abi_version"],
  });

  try {
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
          platform: "win32",
        }),
      /missing fused ASR ABI exports: wce_native_asr_get_status, wce_native_asr_begin, wce_native_asr_poll, wce_native_asr_close/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("local macOS development staging copies the complete trio", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  const destination = path.join(root, "stage");
  writeArtifactSet(artifactDir, "darwin", MACOS_DEVELOPMENT_MANIFEST);

  try {
    const result = stageNativeCoreArtifacts({
      destinationDir: destination,
      env: {
        WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir,
        WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1",
      },
      logger: quietLogger(),
      platform: "darwin",
    });

    assert.equal(result.staged, true);
    for (const name of nativeCoreArtifactNames("darwin")) {
      assert.ok(fs.statSync(path.join(destination, name)).isFile(), name);
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("production manifest validation reports every release security field", () => {
  const errors = nativeCoreProductionManifestErrors(DEVELOPMENT_MANIFEST);
  assert.ok(errors.includes("developmentBuild must be false"));
  assert.ok(errors.includes("codeSignatureEnforced must be true"));
  assert.ok(errors.includes("rootPublicKeyCompiled must be true"));
  assert.ok(errors.includes("testHooksEnabled must be false"));
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      stagingPinnedSignerTrust: true,
    }).includes("stagingPinnedSignerTrust must be false")
  );
  const missingStagingTrust = { ...PRODUCTION_MANIFEST };
  delete missingStagingTrust.stagingPinnedSignerTrust;
  assert.ok(
    nativeCoreProductionManifestErrors(missingStagingTrust).includes(
      "stagingPinnedSignerTrust must be false"
    )
  );
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      windowsClientSignerSha256: "00".repeat(32),
    }).includes("windowsClientSignerSha256 must be a non-zero SHA-256 digest")
  );
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      windowsBrokerSignerSha256: PRODUCTION_MANIFEST.windowsClientSignerSha256,
    }).includes("Windows client and broker signer pins must be distinct")
  );
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      windowsPrivateRootSha256: "",
    }).includes("private-pki requires windowsPrivateRootSha256")
  );
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      windowsSignerTrustMode: "staging",
    }).includes("windowsSignerTrustMode must be public or private-pki")
  );
  assert.equal(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      windowsSignerTrustMode: "public",
      windowsPrivatePkiLeafRevocation: "not-applicable",
      windowsPrivateRootSha256: "00".repeat(32),
    }).length,
    0
  );
  assert.ok(errors.includes("buildId must not contain a development or staging label"));
  assert.ok(errors.includes("offlineBootstrapFeatureBits must equal 3"));
  assert.ok(errors.includes("offlineExportSealFormat must equal WES2"));
  for (const buildId of ["staging-security-12345678", "release.test.2026.07.27"]) {
    assert.ok(
      nativeCoreProductionManifestErrors({ ...PRODUCTION_MANIFEST, buildId }).includes(
        "buildId must not contain a development or staging label"
      )
    );
  }
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      buildExpiresAtUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix - 1,
    }).includes("build validity window must equal exactly 45 days")
  );
  assert.ok(
    nativeCoreProductionManifestErrors(PRODUCTION_MANIFEST, {
      nowUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix,
    }).includes("build has reached its fixed expiration time")
  );
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      distributionMode: "controlled",
      distributionCapsule: { recipient: "fixture" },
    }).includes("distributionCapsule must be absent")
  );
  assert.ok(
    nativeCoreProductionManifestErrors({
      ...PRODUCTION_MANIFEST,
      windowsPrivatePkiLeafRevocation: "not-applicable",
    }).includes("windowsPrivatePkiLeafRevocation must match signer trust mode")
  );
});

test("V2 notice and V3 checkpoint metadata cannot be bypassed by the development override", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  const cases = [
    { securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V1" },
    { securityNoticeSha256: "AA".repeat(32) },
    { securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V2" },
    { securityCheckpointCount: 6 },
    { securityCheckpointSetSha256: "BB".repeat(32) },
  ];

  try {
    for (const [index, patch] of cases.entries()) {
      writeArtifactSet(
        artifactDir,
        "win32",
        { ...DEVELOPMENT_MANIFEST, ...patch }
      );
      assert.throws(
        () =>
          resolveNativeCoreArtifacts({
            env: {
              WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1",
              WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir,
            },
            platform: "win32",
          }),
        /Invalid wechatdb native build manifest/,
        `case ${index}`
      );
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("artifact staging rejects invalid and expired fixed build windows", () => {
  const root = makeTempDir();
  try {
    const cases = [
      {
        name: "missing-window",
        manifest: Object.fromEntries(
          Object.entries(PRODUCTION_MANIFEST).filter(
            ([name]) => name !== "buildIssuedAtUnix" && name !== "buildExpiresAtUnix"
          )
        ),
        message: /build validity window must equal exactly 45 days/,
      },
      {
        name: "wrong-window",
        manifest: {
          ...PRODUCTION_MANIFEST,
          buildExpiresAtUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix - 1,
        },
        message: /build validity window must equal exactly 45 days/,
      },
      {
        name: "expired-window",
        manifest: {
          ...PRODUCTION_MANIFEST,
          buildIssuedAtUnix: 1,
          buildExpiresAtUnix: 1 + BUILD_LIFETIME_SECONDS,
        },
        message: /build has reached its fixed expiration time/,
      },
    ];

    for (const item of cases) {
      const artifactDir = path.join(root, item.name);
      writeArtifactSet(artifactDir, "win32", item.manifest);
      assert.throws(
        () =>
          resolveNativeCoreArtifacts({
            env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
            platform: "win32",
          }),
        item.message
      );
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("development artifacts require an explicit local override", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  const destination = path.join(root, "stage");
  fs.mkdirSync(destination, { recursive: true });
  writeArtifactSet(artifactDir, "win32", DEVELOPMENT_MANIFEST, {
    clientExports: ["wce_client_abi_version"],
  });

  try {
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
          platform: "win32",
        }),
      /Refusing to stage a non-production wechatdb native core/
    );
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: { WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1" },
          platform: "win32",
        }),
      /requires an explicit WCE_NATIVE_CORE_ARTIFACT_DIR/
    );
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: {
            CI: "true",
            WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1",
            WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir,
          },
          platform: "win32",
        }),
      /local-only override and is forbidden in CI/
    );

    const result = stageNativeCoreArtifacts({
      destinationDir: destination,
      env: {
        WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1",
        WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir,
      },
      logger: quietLogger(),
      platform: "win32",
    });
    assert.equal(result.staged, true);
    assert.equal(result.allowDevelopment, true);
    assert.equal(result.manifest.nativeAsrAuthorization, "none");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("malformed and structurally invalid manifests fail even with a development override", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  writeArtifactSet(artifactDir, "win32", DEVELOPMENT_MANIFEST);
  const env = {
    WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1",
    WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir,
  };

  try {
    fs.writeFileSync(path.join(artifactDir, "wechatdb_native_build.json"), "{broken");
    assert.throws(
      () => resolveNativeCoreArtifacts({ env, platform: "win32" }),
      /Invalid wechatdb native build manifest/
    );

    fs.writeFileSync(
      path.join(artifactDir, "wechatdb_native_build.json"),
      JSON.stringify({ ...DEVELOPMENT_MANIFEST, schemaVersion: 1, buildId: "" })
    );
    assert.throws(
      () => resolveNativeCoreArtifacts({ env, platform: "win32" }),
      /schemaVersion must equal 2, 3 or 4; buildId must be a non-empty string/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Linux native core is a required closed artifact set", () => {
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: {}, platform: "linux" }),
    /Missing WCE_NATIVE_CORE_ARTIFACT_DIR/
  );
  assert.throws(
    () =>
      resolveNativeCoreArtifacts({
        env: { WCE_NATIVE_CORE_REQUIRED: "yes" },
        platform: "linux",
      }),
    /Missing WCE_NATIVE_CORE_ARTIFACT_DIR/
  );
});

test("Linux source-public and production profiles both resolve from sealed artifacts", () => {
  const root = makeTempDir();
  try {
    for (const sourceRuntime of [true, false]) {
      const artifactDir = path.join(root, sourceRuntime ? "sp" : "prod");
      writeLinuxArtifactSet(artifactDir, { sourceRuntime });
      const resolved = resolveNativeCoreArtifacts({
        env: linuxEnv(artifactDir),
        platform: "linux",
      });
      assert.equal(resolved.required, true);
      assert.equal(resolved.allowDevelopment, false);
      assert.deepEqual(resolved.names, [
        "libwechatdb_client.so",
        "wechatdb_broker",
        "wechatdb_native_build.json",
      ]);
      assert.equal(
        resolved.manifest.linuxHostVerification,
        sourceRuntime ? "same-user-direct-parent" : "content-hash-pin"
      );
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Linux content-hash pins reject any post-seal tampering", () => {
  const root = makeTempDir();
  try {
    const artifactDir = path.join(root, "tampered");
    writeLinuxArtifactSet(artifactDir, { tamperClient: true });
    assert.throws(
      () => resolveNativeCoreArtifacts({ env: linuxEnv(artifactDir), platform: "linux" }),
      /checksum set does not match the artifact allowlist/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Linux protected pins fail closed on build id, revision and repository drift", () => {
  const root = makeTempDir();
  try {
    const artifactDir = path.join(root, "pinned");
    writeLinuxArtifactSet(artifactDir);
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: linuxEnv(artifactDir, { WCE_NATIVE_CORE_BUILD_ID: "linux-x64-other-2026.09.16" }),
          platform: "linux",
        }),
      /does not match the protected build id pin/
    );
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: linuxEnv(artifactDir, { WCE_NATIVE_CORE_SOURCE_REVISION: "0".repeat(40) }),
          platform: "linux",
        }),
      /provenance revision does not match the protected pin/
    );
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: linuxEnv(artifactDir, { WCE_NATIVE_CORE_ARTIFACT_REPOSITORY: "evil/fork" }),
          platform: "linux",
        }),
      /provenance repository does not match the protected pin/
    );
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: linuxEnv(artifactDir, { WCE_NATIVE_CORE_ARTIFACT_RUN_ID: "123" }),
          platform: "linux",
        }),
      /must not claim a CI run/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Linux artifacts are only accepted from the reviewed producer workflow", () => {
  const root = makeTempDir();
  try {
    // A workflow-produced artifact has to come from the reviewed producer, not
    // from any workflow that happens to know the pin format.
    const rogueDir = path.join(root, "rogue");
    writeLinuxArtifactSet(rogueDir, {
      provenanceOverrides: {
        producer: "github-actions",
        workflow: ".github/workflows/rogue-production.yml",
        runId: 4242,
        runAttempt: 1,
      },
    });
    assert.throws(
      () =>
        resolveNativeCoreArtifacts({
          env: linuxEnv(rogueDir, { WCE_NATIVE_CORE_ARTIFACT_RUN_ID: "4242" }),
          platform: "linux",
        }),
      /must come from \.github\/workflows\/linux-native-production\.yml/
    );

    const reviewedDir = path.join(root, "reviewed");
    writeLinuxArtifactSet(reviewedDir, {
      provenanceOverrides: {
        producer: "github-actions",
        workflow: PRODUCER_WORKFLOW,
        runId: 4242,
        runAttempt: 1,
      },
    });
    const resolved = resolveNativeCoreArtifacts({
      env: linuxEnv(reviewedDir, { WCE_NATIVE_CORE_ARTIFACT_RUN_ID: "4242" }),
      platform: "linux",
    });
    assert.equal(resolved.provenance.runId, 4242);
    assert.equal(resolved.provenance.workflow, PRODUCER_WORKFLOW);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Linux profile self-consistency and binary identity are enforced", () => {
  const root = makeTempDir();
  try {
    // 声明 sourceRuntime 却用 production 强度的 host 校验：必须拒绝。
    const inconsistent = path.join(root, "inconsistent");
    writeLinuxArtifactSet(inconsistent, {
      manifestOverrides: { linuxHostVerification: "content-hash-pin" },
    });
    assert.throws(
      () => resolveNativeCoreArtifacts({ env: linuxEnv(inconsistent), platform: "linux" }),
      /linuxHostVerification must equal same-user-direct-parent/
    );

    // 客户端不是 ELF：必须拒绝。
    const notElf = path.join(root, "not-elf");
    writeLinuxArtifactSet(notElf);
    fs.writeFileSync(path.join(notElf, "libwechatdb_client.so"), "not an elf at all");
    assert.throws(
      () => resolveNativeCoreArtifacts({ env: linuxEnv(notElf), platform: "linux" }),
      /checksum set does not match the artifact allowlist/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("packaged Linux native core is re-hashed before packing", () => {
  const root = makeTempDir();
  try {
    const { validatePackagedBackend } = require("../scripts/native-core-before-pack.cjs");
    const nativeDir = path.join(root, "native");
    writeLinuxArtifactSet(nativeDir);
    fs.writeFileSync(path.join(root, "wechat-backend"), "# packaged backend\n");

    const validated = validatePackagedBackend({ backendDir: root, platform: "linux" });
    assert.equal(validated.platform, "linux");

    // 打包后再被替换一个字节 → 内容哈希必须拦住。
    fs.writeFileSync(path.join(nativeDir, "wechatdb_broker"), linuxElfBytes(3));
    assert.throws(
      () => validatePackagedBackend({ backendDir: root, platform: "linux" }),
      /Packaged Linux native core failed content verification: content hash mismatch for wechatdb_broker/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("boolean packaging flags reject ambiguous values", () => {
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: { WCE_NATIVE_CORE_REQUIRED: "sometimes" }, platform: "win32" }),
    /WCE_NATIVE_CORE_REQUIRED must be a boolean value/
  );
});
