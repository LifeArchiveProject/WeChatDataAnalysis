const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const crypto = require("crypto");
const os = require("os");
const path = require("path");

const { nativeCoreArtifactNames } = require("../scripts/build-backend.cjs");
const {
  stageWindowsPrivatePkiEvidence,
  validatePackagedBackend,
} = require("../scripts/native-core-before-pack.cjs");

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

function makeBackend(platform, manifest = PRODUCTION_MANIFEST) {
  const backendDir = fs.mkdtempSync(path.join(os.tmpdir(), "wda-before-pack-"));
  const nativeDir = path.join(backendDir, "native");
  fs.mkdirSync(nativeDir, { recursive: true });
  fs.writeFileSync(
    path.join(backendDir, platform === "win32" ? "wechat-backend.exe" : "wechat-backend"),
    "backend"
  );
  for (const name of nativeCoreArtifactNames(platform)) {
    if (name === "wechatdb_native_build.json") continue;
    fs.writeFileSync(path.join(nativeDir, name), name);
  }
  fs.writeFileSync(
    path.join(nativeDir, "wechatdb_native_build.json"),
    JSON.stringify(manifest)
  );
  return backendDir;
}

test("beforePack accepts a complete production backend trio", () => {
  for (const platform of ["win32", "darwin"]) {
    const backendDir = makeBackend(platform);
    try {
      const result = validatePackagedBackend({ backendDir, platform });
      assert.equal(result.manifest.buildId, PRODUCTION_MANIFEST.buildId);
    } finally {
      fs.rmSync(backendDir, { recursive: true, force: true });
    }
  }
});

test("beforePack rejects development artifacts even if a staging override was used", () => {
  const backendDir = makeBackend("win32", {
    schemaVersion: 2,
    buildId: "dev-local",
    developmentBuild: true,
    codeSignatureEnforced: false,
    rootPublicKeyCompiled: false,
    testHooksEnabled: true,
    stagingPinnedSignerTrust: false,
  });
  try {
    assert.throws(
      () => validatePackagedBackend({ backendDir, platform: "win32" }),
      /rejected a non-production wechatdb native core/
    );
  } finally {
    fs.rmSync(backendDir, { recursive: true, force: true });
  }
});

test("beforePack rejects a staging trust profile under a release build ID", () => {
  const backendDir = makeBackend("win32", {
    ...PRODUCTION_MANIFEST,
    stagingPinnedSignerTrust: true,
  });
  try {
    assert.throws(
      () => validatePackagedBackend({ backendDir, platform: "win32" }),
      /stagingPinnedSignerTrust must be false/
    );
  } finally {
    fs.rmSync(backendDir, { recursive: true, force: true });
  }
});

test("beforePack rejects invalid and expired fixed build windows", () => {
  const invalidBackend = makeBackend("win32", {
    ...PRODUCTION_MANIFEST,
    buildExpiresAtUnix: PRODUCTION_MANIFEST.buildExpiresAtUnix - 1,
  });
  const expiredBackend = makeBackend("win32", {
    ...PRODUCTION_MANIFEST,
    buildIssuedAtUnix: 1,
    buildExpiresAtUnix: 1 + BUILD_LIFETIME_SECONDS,
  });
  try {
    assert.throws(
      () => validatePackagedBackend({ backendDir: invalidBackend, platform: "win32" }),
      /build validity window must equal exactly 45 days/
    );
    assert.throws(
      () => validatePackagedBackend({ backendDir: expiredBackend, platform: "win32" }),
      /build has reached its fixed expiration time/
    );
  } finally {
    fs.rmSync(invalidBackend, { recursive: true, force: true });
    fs.rmSync(expiredBackend, { recursive: true, force: true });
  }
});

test("beforePack rejects stale legacy WCDB files and partial trios", () => {
  const backendDir = makeBackend("win32");
  const nativeDir = path.join(backendDir, "native");
  try {
    fs.writeFileSync(path.join(nativeDir, "wcdb_api.dll"), "legacy");
    assert.throws(
      () => validatePackagedBackend({ backendDir, platform: "win32" }),
      /Legacy WCDB runtime must not be packaged/
    );
    fs.rmSync(path.join(nativeDir, "wcdb_api.dll"));
    fs.rmSync(path.join(nativeDir, "wechatdb_broker.exe"));
    assert.throws(
      () => validatePackagedBackend({ backendDir, platform: "win32" }),
      /wechatdb_broker\.exe is missing or empty/
    );
  } finally {
    fs.rmSync(backendDir, { recursive: true, force: true });
  }
});

test("beforePack rejects the retired macOS WCDB bridge", () => {
  const backendDir = makeBackend("darwin");
  const legacy = path.join(backendDir, "native", "macos", "arm64", "libwcdb_api.dylib");
  try {
    fs.mkdirSync(path.dirname(legacy), { recursive: true });
    fs.writeFileSync(legacy, "legacy");
    assert.throws(
      () => validatePackagedBackend({ backendDir, platform: "darwin" }),
      /Legacy WCDB runtime must not be packaged: .*libwcdb_api\.dylib/
    );
  } finally {
    fs.rmSync(backendDir, { recursive: true, force: true });
  }
});

test("beforePack rejects the retired macOS WCDB dynamic library", () => {
  const backendDir = makeBackend("darwin");
  const legacy = path.join(backendDir, "native", "macos", "universal", "libWCDB.dylib");
  try {
    fs.mkdirSync(path.dirname(legacy), { recursive: true });
    fs.writeFileSync(legacy, "legacy");
    assert.throws(
      () => validatePackagedBackend({ backendDir, platform: "darwin" }),
      /Legacy WCDB runtime must not be packaged: .*libWCDB\.dylib/
    );
  } finally {
    fs.rmSync(backendDir, { recursive: true, force: true });
  }
});

test("beforePack stages only the pinned public root and verifier", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-signing-evidence-"));
  const rootCertificate = path.join(root, "root.cer");
  const signingDir = path.join(root, "staged");
  fs.writeFileSync(rootCertificate, "DER public root fixture");
  const rootPin = crypto.createHash("sha256").update(fs.readFileSync(rootCertificate)).digest("hex");
  try {
    const result = stageWindowsPrivatePkiEvidence({
      env: {
        WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH: rootCertificate,
        WCE_WINDOWS_PRIVATE_ROOT_SHA256: rootPin,
      },
      manifest: { ...PRODUCTION_MANIFEST, windowsPrivateRootSha256: rootPin },
      signingDir,
    });
    assert.equal(result.rootSha256, rootPin.toUpperCase());
    assert.deepEqual(fs.readdirSync(signingDir).sort(), [
      "windows-private-pki-root.cer",
      "windows-private-pki.ps1",
    ]);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("beforePack rejects a root certificate outside the native trust domain", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-signing-mismatch-"));
  const rootCertificate = path.join(root, "root.cer");
  fs.writeFileSync(rootCertificate, "wrong root");
  try {
    assert.throws(
      () =>
        stageWindowsPrivatePkiEvidence({
          env: {
            WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH: rootCertificate,
            WCE_WINDOWS_PRIVATE_ROOT_SHA256: PRODUCTION_MANIFEST.windowsPrivateRootSha256,
          },
          manifest: PRODUCTION_MANIFEST,
          signingDir: path.join(root, "staged"),
        }),
      /does not match the protected root pin/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
