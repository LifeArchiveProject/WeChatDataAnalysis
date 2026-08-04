const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
  ENV_NATIVE_CORE_MODE,
  applyNativeCoreRuntimePolicy,
  isProductionNativeCoreManifest,
  nativeCoreArtifactNames,
  resolveNativeCoreRuntimePolicy,
} = require("../src/native-core-runtime.cjs");

const BUILD_ISSUED_AT_UNIX = Math.floor(Date.now() / 1000) - 60;
const BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const PRODUCTION_MANIFEST = Object.freeze({
  schemaVersion: 2,
  distributionMode: "public",
  buildId: "release-2026.07.27",
  buildIssuedAtUnix: BUILD_ISSUED_AT_UNIX,
  buildExpiresAtUnix: BUILD_ISSUED_AT_UNIX + BUILD_LIFETIME_SECONDS,
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
});

const DEVELOPMENT_MANIFEST = Object.freeze({
  schemaVersion: 2,
  distributionMode: "public",
  buildId: "dev-local",
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
});

const MACOS_PRODUCTION_MANIFEST = Object.freeze({
  schemaVersion: 3,
  platform: "macos",
  distributionMode: "public",
  buildId: "wcdb-macos-20260804-abcd1234",
  buildIssuedAtUnix: BUILD_ISSUED_AT_UNIX,
  buildExpiresAtUnix: BUILD_ISSUED_AT_UNIX + BUILD_LIFETIME_SECONDS,
  developmentBuild: false,
  offlineBootstrapFeatureBits: 3,
  offlineExportSealFormat: "WES2",
  codeSignatureEnforced: true,
  rootPublicKeyCompiled: true,
  testHooksEnabled: false,
  stagingPinnedSignerTrust: false,
  macosSigningMode: "self-signed",
  macosSignerTrustMode: "private-pki",
  macosPrivatePkiLeafRevocation: "build-and-lease-only",
  macosClientSigningIdentifier: "com.lifearchive.wechatdb.client",
  macosBrokerSigningIdentifier: "com.lifearchive.wechatdb.broker",
  macosHostSigningIdentifier: "com.lifearchive.wechatdataanalysis.backend",
  macosClientSignerSha256: "11".repeat(32),
  macosBrokerSignerSha256: "22".repeat(32),
  macosHostSignerSha256: "33".repeat(32),
  macosPrivateRootSha256: "44".repeat(32),
  securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
  securityNoticeSha256: "aa".repeat(32),
  securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
  securityCheckpointCount: 7,
  securityCheckpointSetSha256: "bb".repeat(32),
});

const MACOS_DEVELOPMENT_MANIFEST = Object.freeze({
  ...MACOS_PRODUCTION_MANIFEST,
  buildId: "dev-local",
  buildIssuedAtUnix: 0,
  buildExpiresAtUnix: 0,
  developmentBuild: true,
  offlineBootstrapFeatureBits: 0,
  offlineExportSealFormat: "none",
  codeSignatureEnforced: false,
  rootPublicKeyCompiled: false,
  testHooksEnabled: true,
  macosSignerTrustMode: "development",
  macosPrivatePkiLeafRevocation: "not-applicable",
  macosClientSignerSha256: "00".repeat(32),
  macosBrokerSignerSha256: "00".repeat(32),
  macosHostSignerSha256: "00".repeat(32),
  macosPrivateRootSha256: "00".repeat(32),
});

function makeArtifacts(platform, manifest, { omit = [] } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-native-runtime-"));
  for (const name of nativeCoreArtifactNames(platform)) {
    if (omit.includes(name) || name === "wechatdb_native_build.json") continue;
    fs.writeFileSync(path.join(root, name), `fixture:${name}`);
  }
  if (!omit.includes("wechatdb_native_build.json")) {
    fs.writeFileSync(
      path.join(root, "wechatdb_native_build.json"),
      JSON.stringify(manifest)
    );
  }
  return root;
}

function cleanup(root) {
  fs.rmSync(root, { recursive: true, force: true });
}

test("source development artifacts auto-enable required mode and the local override", () => {
  const nativeDir = makeArtifacts("win32", DEVELOPMENT_MANIFEST);
  const env = {};
  try {
    const policy = applyNativeCoreRuntimePolicy(env, {
      isPackaged: false,
      nativeDir,
      platform: "win32",
    });
    assert.equal(policy.mode, "required");
    assert.equal(policy.reason, "source-development-artifacts");
    assert.equal(policy.artifactState, "development");
    assert.equal(env[ENV_NATIVE_CORE_MODE], "required");
    assert.equal(env[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], "1");
  } finally {
    cleanup(nativeDir);
  }
});

test("desktop rejects explicit legacy rollout modes", () => {
  const nativeDir = makeArtifacts("win32", DEVELOPMENT_MANIFEST);
  try {
    for (const mode of ["off", "prefer"]) {
      assert.throws(
        () =>
          applyNativeCoreRuntimePolicy({ [ENV_NATIVE_CORE_MODE]: mode }, {
            isPackaged: false,
            nativeDir,
            platform: "win32",
          }),
        /must be required after native-core migration/
      );
    }

    const requiredEnv = { [ENV_NATIVE_CORE_MODE]: "required" };
    const required = applyNativeCoreRuntimePolicy(requiredEnv, {
      isPackaged: false,
      nativeDir,
      platform: "win32",
    });
    assert.equal(required.mode, "required");
    assert.equal(requiredEnv[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], "1");
  } finally {
    cleanup(nativeDir);
  }
});

test("packaged development artifacts fail closed", () => {
  const nativeDir = makeArtifacts("win32", DEVELOPMENT_MANIFEST);
  try {
    assert.throws(
      () => applyNativeCoreRuntimePolicy({}, {
        isPackaged: true,
        nativeDir,
        platform: "win32",
      }),
      /requires an approved production wechatdb native core/
    );
  } finally {
    cleanup(nativeDir);
  }
});

test("packaged production artifacts auto-enable required mode without a development override", () => {
  const nativeDir = makeArtifacts("win32", PRODUCTION_MANIFEST);
  const env = {};
  try {
    const policy = applyNativeCoreRuntimePolicy(env, {
      isPackaged: true,
      nativeDir,
      platform: "win32",
    });
    assert.equal(policy.mode, "required");
    assert.equal(policy.reason, "production-artifacts");
    assert.equal(env[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], undefined);
  } finally {
    cleanup(nativeDir);
  }
});

test("packaged macOS production artifacts enable required mode", () => {
  const nativeDir = makeArtifacts("darwin", MACOS_PRODUCTION_MANIFEST);
  const env = {};
  try {
    const policy = applyNativeCoreRuntimePolicy(env, {
      isPackaged: true,
      nativeDir,
      platform: "darwin",
    });
    assert.equal(policy.mode, "required");
    assert.equal(policy.reason, "production-artifacts");
    assert.equal(policy.manifest.platform, "macos");
    assert.equal(env[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], undefined);
  } finally {
    cleanup(nativeDir);
  }
});

test("source macOS development artifacts enable only the explicit development override", () => {
  const nativeDir = makeArtifacts("darwin", MACOS_DEVELOPMENT_MANIFEST);
  const env = {};
  try {
    const policy = applyNativeCoreRuntimePolicy(env, {
      isPackaged: false,
      nativeDir,
      platform: "darwin",
    });
    assert.equal(policy.artifactState, "development");
    assert.equal(policy.manifest.platform, "macos");
    assert.equal(env[ENV_NATIVE_CORE_MODE], "required");
    assert.equal(env[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], "1");
  } finally {
    cleanup(nativeDir);
  }
});

test("Windows and macOS manifest schemas cannot cross platform boundaries", () => {
  const windowsWithMacManifest = makeArtifacts("win32", MACOS_PRODUCTION_MANIFEST);
  const macWithWindowsManifest = makeArtifacts("darwin", PRODUCTION_MANIFEST);
  try {
    assert.throws(
      () => resolveNativeCoreRuntimePolicy({
        env: {},
        isPackaged: true,
        nativeDir: windowsWithMacManifest,
        platform: "win32",
      }),
      /requires an approved production/
    );
    assert.throws(
      () => resolveNativeCoreRuntimePolicy({
        env: {},
        isPackaged: true,
        nativeDir: macWithWindowsManifest,
        platform: "darwin",
      }),
      /requires an approved production/
    );
  } finally {
    cleanup(windowsWithMacManifest);
    cleanup(macWithWindowsManifest);
  }
});

test("macOS production identity substitution fails closed", () => {
  const rejected = [
    { ...MACOS_PRODUCTION_MANIFEST, macosSigningMode: "developer-id" },
    { ...MACOS_PRODUCTION_MANIFEST, macosSignerTrustMode: "development" },
    { ...MACOS_PRODUCTION_MANIFEST, macosPrivatePkiLeafRevocation: "not-applicable" },
    {
      ...MACOS_PRODUCTION_MANIFEST,
      macosHostSigningIdentifier: MACOS_PRODUCTION_MANIFEST.macosBrokerSigningIdentifier,
    },
    {
      ...MACOS_PRODUCTION_MANIFEST,
      macosHostSignerSha256: MACOS_PRODUCTION_MANIFEST.macosClientSignerSha256,
    },
    { ...MACOS_PRODUCTION_MANIFEST, macosPrivateRootSha256: "00".repeat(32) },
  ];
  assert.equal(isProductionNativeCoreManifest(MACOS_PRODUCTION_MANIFEST), true);
  for (const manifest of rejected) {
    assert.equal(isProductionNativeCoreManifest(manifest), false);
    const nativeDir = makeArtifacts("darwin", manifest);
    try {
      assert.throws(
        () => resolveNativeCoreRuntimePolicy({
          env: {},
          isPackaged: true,
          nativeDir,
          platform: "darwin",
        }),
        /requires an approved production/
      );
    } finally {
      cleanup(nativeDir);
    }
  }
});

test("source and packaged artifact profiles cannot be swapped", () => {
  const productionDir = makeArtifacts("win32", PRODUCTION_MANIFEST);
  const developmentDir = makeArtifacts("win32", DEVELOPMENT_MANIFEST);
  try {
    assert.throws(
      () => applyNativeCoreRuntimePolicy({}, {
        isPackaged: false,
        nativeDir: productionDir,
        platform: "win32",
      }),
      /requires the exact dev-local/
    );
    assert.throws(
      () => applyNativeCoreRuntimePolicy({}, {
        isPackaged: true,
        nativeDir: developmentDir,
        platform: "win32",
      }),
      /requires an approved production/
    );
  } finally {
    cleanup(productionDir);
    cleanup(developmentDir);
  }
});

test("every production manifest gate fails closed", () => {
  const missingStagingTrust = { ...PRODUCTION_MANIFEST };
  delete missingStagingTrust.stagingPinnedSignerTrust;
  const rejected = [
    { ...PRODUCTION_MANIFEST, schemaVersion: 1 },
    { ...PRODUCTION_MANIFEST, distributionMode: "controlled" },
    { ...PRODUCTION_MANIFEST, distributionCapsule: { recipient: "fixture" } },
    { ...PRODUCTION_MANIFEST, buildIssuedAtUnix: 0 },
    { ...PRODUCTION_MANIFEST, buildIssuedAtUnix: 1.5 },
    {
      ...PRODUCTION_MANIFEST,
      buildExpiresAtUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix - 1,
    },
    { ...PRODUCTION_MANIFEST, buildId: "dev-local" },
    { ...PRODUCTION_MANIFEST, buildId: "staging-security-12345678" },
    { ...PRODUCTION_MANIFEST, buildId: "release.test.2026.07.27" },
    { ...PRODUCTION_MANIFEST, developmentBuild: true },
    { ...PRODUCTION_MANIFEST, offlineBootstrapFeatureBits: 0 },
    { ...PRODUCTION_MANIFEST, offlineExportSealFormat: "WES1" },
    { ...PRODUCTION_MANIFEST, codeSignatureEnforced: false },
    { ...PRODUCTION_MANIFEST, rootPublicKeyCompiled: false },
    { ...PRODUCTION_MANIFEST, testHooksEnabled: true },
    { ...PRODUCTION_MANIFEST, stagingPinnedSignerTrust: true },
    { ...PRODUCTION_MANIFEST, windowsClientSignerSha256: "00".repeat(32) },
    { ...PRODUCTION_MANIFEST, windowsBrokerSignerSha256: "00".repeat(32) },
    {
      ...PRODUCTION_MANIFEST,
      windowsBrokerSignerSha256: PRODUCTION_MANIFEST.windowsClientSignerSha256,
    },
    { ...PRODUCTION_MANIFEST, windowsSignerTrustMode: "staging" },
    { ...PRODUCTION_MANIFEST, windowsPrivatePkiLeafRevocation: "not-applicable" },
    { ...PRODUCTION_MANIFEST, windowsPrivateRootSha256: "" },
    { ...PRODUCTION_MANIFEST, securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V1" },
    { ...PRODUCTION_MANIFEST, securityNoticeSha256: "AA".repeat(32) },
    { ...PRODUCTION_MANIFEST, securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V2" },
    { ...PRODUCTION_MANIFEST, securityCheckpointCount: 6 },
    { ...PRODUCTION_MANIFEST, securityCheckpointSetSha256: "BB".repeat(32) },
    missingStagingTrust,
  ];
  assert.equal(isProductionNativeCoreManifest(PRODUCTION_MANIFEST), true);
  for (const manifest of rejected) {
    assert.equal(isProductionNativeCoreManifest(manifest), false);
    const nativeDir = makeArtifacts("win32", manifest);
    try {
      assert.throws(
        () => resolveNativeCoreRuntimePolicy({
          env: {},
          isPackaged: true,
          nativeDir,
          platform: "win32",
        }),
        /requires an approved production wechatdb native core/
      );
    } finally {
      cleanup(nativeDir);
    }
  }
});

test("packaged runtime rejects a production build at its fixed expiration boundary", () => {
  const nativeDir = makeArtifacts("win32", PRODUCTION_MANIFEST);
  try {
    assert.equal(
      isProductionNativeCoreManifest(PRODUCTION_MANIFEST, {
        nowUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix - 1,
      }),
      true
    );
    assert.equal(
      isProductionNativeCoreManifest(PRODUCTION_MANIFEST, {
        nowUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix,
      }),
      false
    );
    assert.throws(
      () =>
        resolveNativeCoreRuntimePolicy({
          env: {},
          isPackaged: true,
          nativeDir,
          nowUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix,
          platform: "win32",
        }),
      /requires an approved production wechatdb native core/
    );
  } finally {
    cleanup(nativeDir);
  }
});

test("partial artifacts fail before the desktop starts", () => {
  const nativeDir = makeArtifacts("win32", PRODUCTION_MANIFEST, {
    omit: ["wechatdb_broker.exe"],
  });
  try {
    assert.throws(
      () => resolveNativeCoreRuntimePolicy({
        env: {},
        isPackaged: true,
        nativeDir,
        platform: "win32",
      }),
      /Required wechatdb native core is incomplete/
    );
  } finally {
    cleanup(nativeDir);
  }
});

test("ambiguous native core modes fail before the desktop starts a runtime", () => {
  assert.throws(
    () => resolveNativeCoreRuntimePolicy({ env: { [ENV_NATIVE_CORE_MODE]: "sometimes" } }),
    /must be required after native-core migration/
  );
});

test("desktop startBackend clears legacy WCDB state and never starts the sidecar", () => {
  const mainSource = fs.readFileSync(path.join(__dirname, "..", "src", "main.cjs"), "utf8");
  const startBackend = mainSource.match(/function startBackend\(\) \{([\s\S]*?)\n\}/)?.[1] || "";
  assert.match(startBackend, /configureNativeCoreRuntime\(env\)/);
  assert.match(startBackend, /clearLegacyWcdbEnvironment\(env\)/);
  assert.doesNotMatch(startBackend, /startWcdbSidecar\(/);
  assert.doesNotMatch(startBackend, /ensureWcdbSidecarEnv\(/);
  assert.doesNotMatch(startBackend, /WECHAT_TOOL_WCDB_API_DLL_PATH\s*=/);
});

test("desktop account deletion clears encrypted native raw-key cache while backend is stopped", () => {
  const mainSource = fs.readFileSync(path.join(__dirname, "..", "src", "main.cjs"), "utf8");
  const deleteStart = mainSource.indexOf("async function deleteAccountDataFromDisk");
  const deleteEnd = mainSource.indexOf("\nfunction getExeDir", deleteStart);
  const deleteSource = mainSource.slice(deleteStart, deleteEnd);

  assert.match(mainSource, /function clearNativeCoreRawKeyCache\(\)/);
  assert.match(mainSource, /\.native-core-cache-v1/);
  assert.match(deleteSource, /clearNativeCoreRawKeyCache\(\)/);
  assert.ok(
    deleteSource.indexOf("stopBackendAndWait") <
      deleteSource.indexOf("clearNativeCoreRawKeyCache()")
  );
});
