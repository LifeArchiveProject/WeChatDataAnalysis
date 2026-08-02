const test = require("node:test");
const assert = require("node:assert/strict");
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

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "wda-native-package-"));
}

function writeArtifactSet(root, platform, manifest, { omit = [] } = {}) {
  fs.mkdirSync(root, { recursive: true });
  for (const name of nativeCoreArtifactNames(platform)) {
    if (omit.includes(name) || name === "wechatdb_native_build.json") continue;
    fs.writeFileSync(path.join(root, name), `fixture:${name}`);
  }
  if (!omit.includes("wechatdb_native_build.json")) {
    fs.writeFileSync(path.join(root, "wechatdb_native_build.json"), JSON.stringify(manifest));
  }
}

function quietLogger() {
  return { log() {}, warn() {} };
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
  assert.deepEqual(nativeCoreArtifactNames("linux"), []);
});

test("runtime staging filters checked-out native and legacy WCDB files", () => {
  const root = makeTempDir();
  const source = path.join(root, "source");
  const destination = path.join(root, "stage");
  fs.mkdirSync(path.join(source, "nested"), { recursive: true });
  fs.writeFileSync(path.join(source, "ordinary.dll"), "ordinary");
  fs.writeFileSync(path.join(source, "wechatdb_client.dll"), "unchecked");
  fs.writeFileSync(path.join(source, "wechatdb_broker.exe"), "unchecked");
  fs.writeFileSync(path.join(source, "wechatdb_native_build.json"), "unchecked");
  fs.writeFileSync(path.join(source, "wcdb_api.dll"), "legacy");
  fs.writeFileSync(path.join(source, "WCDB.dll"), "legacy-dependency");
  fs.writeFileSync(path.join(source, "libwcdb_api.dylib"), "legacy-macos");
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

test("production staging copies the complete macOS trio", () => {
  const root = makeTempDir();
  const artifactDir = path.join(root, "artifacts");
  const destination = path.join(root, "stage");
  writeArtifactSet(artifactDir, "darwin", PRODUCTION_MANIFEST);

  try {
    const result = stageNativeCoreArtifacts({
      destinationDir: destination,
      env: { WCE_NATIVE_CORE_ARTIFACT_DIR: artifactDir },
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
  writeArtifactSet(artifactDir, "win32", DEVELOPMENT_MANIFEST);

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
      /schemaVersion must equal 2; buildId must be a non-empty string/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("unsupported platforms stay optional but fail closed when configured", () => {
  const optional = resolveNativeCoreArtifacts({ env: {}, platform: "linux" });
  assert.equal(optional.artifactDir, null);
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: { WCE_NATIVE_CORE_REQUIRED: "yes" }, platform: "linux" }),
    /unsupported on platform: linux/
  );
});

test("boolean packaging flags reject ambiguous values", () => {
  assert.throws(
    () => resolveNativeCoreArtifacts({ env: { WCE_NATIVE_CORE_REQUIRED: "sometimes" }, platform: "win32" }),
    /WCE_NATIVE_CORE_REQUIRED must be a boolean value/
  );
});
