"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  ARTIFACT_NAME,
  CHECKSUM_FILE_NAMES,
  macosNativeManifestErrors,
  resolveMacosNativeCoreArtifacts,
} = require("../scripts/macos-native-core-packaging.cjs");

const SOURCE_REVISION = "a".repeat(40);
const BUILD_ID = "wcdb-macos-20260804-abcd1234";
const ISSUED = Math.floor(Date.now() / 1000) - 60;
const PINS = Object.freeze({
  client: "11".repeat(32),
  broker: "22".repeat(32),
  host: "33".repeat(32),
  root: "44".repeat(32),
});
const IDENTIFIERS = Object.freeze({
  client: "com.lifearchive.wechatdb.client",
  broker: "com.lifearchive.wechatdb.broker",
  host: "com.lifearchive.wechatdataanalysis.backend",
});

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function manifest() {
  return {
    schemaVersion: 3,
    platform: "macos",
    distributionMode: "public",
    buildId: BUILD_ID,
    buildIssuedAtUnix: ISSUED,
    buildExpiresAtUnix: ISSUED + 45 * 24 * 60 * 60,
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
    macosClientSigningIdentifier: IDENTIFIERS.client,
    macosBrokerSigningIdentifier: IDENTIFIERS.broker,
    macosHostSigningIdentifier: IDENTIFIERS.host,
    macosClientSignerSha256: PINS.client,
    macosBrokerSignerSha256: PINS.broker,
    macosHostSignerSha256: PINS.host,
    macosPrivateRootSha256: PINS.root,
    securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
    securityNoticeSha256: "55".repeat(32),
    securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
    securityCheckpointCount: 7,
    securityCheckpointSetSha256: "66".repeat(32),
  };
}

function environment(root) {
  return {
    WCE_NATIVE_CORE_ARTIFACT_DIR: root,
    WCE_NATIVE_CORE_ARTIFACT_REPOSITORY: "2977094657/WCDB",
    WCE_NATIVE_CORE_ARTIFACT_RUN_ID: "123456",
    WCE_NATIVE_CORE_SOURCE_REVISION: SOURCE_REVISION,
    WCE_NATIVE_CORE_BUILD_ID: BUILD_ID,
    WCE_NATIVE_CORE_CLIENT_SIGNER_SHA256: PINS.client,
    WCE_NATIVE_CORE_BROKER_SIGNER_SHA256: PINS.broker,
    WCE_NATIVE_CORE_HOST_SIGNER_SHA256: PINS.host,
    WCE_NATIVE_CORE_PRIVATE_ROOT_SHA256: PINS.root,
    WCE_NATIVE_CORE_CLIENT_SIGNING_IDENTIFIER: IDENTIFIERS.client,
    WCE_NATIVE_CORE_BROKER_SIGNING_IDENTIFIER: IDENTIFIERS.broker,
    WCE_NATIVE_CORE_HOST_SIGNING_IDENTIFIER: IDENTIFIERS.host,
  };
}

function writeFixture(root) {
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(path.join(root, "libwechatdb_client.dylib"), "signed-client");
  fs.writeFileSync(path.join(root, "wechatdb_broker"), "signed-broker");
  fs.writeFileSync(path.join(root, "wechatdb_native_build.json"), JSON.stringify(manifest()));
  const signing = {
    schemaVersion: 1,
    mode: "self-signed",
    privateRootCertificateSha256: PINS.root,
    client: {
      identifier: IDENTIFIERS.client,
      leafCertificateSha256: PINS.client,
      designatedRequirement: `identifier "${IDENTIFIERS.client}" and certificate leaf = H"AA"`,
    },
    broker: {
      identifier: IDENTIFIERS.broker,
      leafCertificateSha256: PINS.broker,
      designatedRequirement: `identifier "${IDENTIFIERS.broker}" and certificate leaf = H"BB"`,
    },
    hardenedRuntime: true,
    timestamped: false,
    notarized: false,
  };
  fs.writeFileSync(path.join(root, "macos_native_signing.json"), JSON.stringify(signing));
  fs.writeFileSync(path.join(root, "Test-MacosNativeProductionArtifact.py"), "print('contract')\n");
  fs.writeFileSync(
    path.join(root, "wda-macos-native-consumer-contract.json"),
    JSON.stringify({ artifactName: ARTIFACT_NAME })
  );
  const checksumLines = [...CHECKSUM_FILE_NAMES]
    .sort()
    .map((name) => `${sha256(path.join(root, name))}  ${name}`);
  fs.writeFileSync(path.join(root, "SHA256SUMS.txt"), `${checksumLines.join("\n")}\n`);
  const artifacts = CHECKSUM_FILE_NAMES.map((name) => ({
    path: name,
    sha256: sha256(path.join(root, name)),
    size: fs.statSync(path.join(root, name)).size,
  }));
  const value = manifest();
  const provenance = {
    schemaVersion: 1,
    artifactName: ARTIFACT_NAME,
    producer: "github-actions",
    workflow: ".github/workflows/macos-native-production.yml",
    repository: "2977094657/WCDB",
    runId: 123456,
    runAttempt: 1,
    sourceRevision: SOURCE_REVISION,
    build: {
      id: BUILD_ID,
      platform: "macos",
      architecture: "arm64",
      issuedAtUnix: value.buildIssuedAtUnix,
      expiresAtUnix: value.buildExpiresAtUnix,
      distributionMode: "public",
      offlineBootstrapFeatureBits: 3,
      offlineExportSealFormat: "WES2",
      signerTrustMode: "private-pki",
      privatePkiLeafRevocation: "build-and-lease-only",
      securityNoticeId: value.securityNoticeId,
      securityNoticeSha256: value.securityNoticeSha256,
      securityCheckpointSetId: value.securityCheckpointSetId,
      securityCheckpointCount: 7,
      securityCheckpointSetSha256: value.securityCheckpointSetSha256,
    },
    signers: {
      client: signing.client,
      broker: signing.broker,
      host: { identifier: IDENTIFIERS.host, leafCertificateSha256: PINS.host },
      privateRootCertificateSha256: PINS.root,
      timestamped: false,
      notarized: false,
    },
    manifestSha256: sha256(path.join(root, "wechatdb_native_build.json")),
    signingMetadataSha256: sha256(path.join(root, "macos_native_signing.json")),
    checksumsSha256: sha256(path.join(root, "SHA256SUMS.txt")),
    artifacts,
  };
  fs.writeFileSync(path.join(root, "provenance.json"), JSON.stringify(provenance));
}

function inspector(filePath) {
  const broker = path.basename(filePath) === "wechatdb_broker";
  return {
    identifier: broker ? IDENTIFIERS.broker : IDENTIFIERS.client,
    leafSha256: broker ? PINS.broker : PINS.client,
    architectures: ["arm64"],
  };
}

test("macOS native manifest accepts exact self-signed production policy", () => {
  assert.deepEqual(macosNativeManifestErrors(manifest(), { nowUnix: ISSUED + 1 }), []);
  assert.ok(macosNativeManifestErrors({ ...manifest(), macosHostSignerSha256: PINS.client }).length > 0);
});

test("macOS native artifact resolves by exact run, provenance, pins, and signatures", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-native-mac-"));
  try {
    writeFixture(root);
    const resolved = resolveMacosNativeCoreArtifacts({
      env: environment(root),
      platform: "darwin",
      nowUnix: ISSUED + 1,
      binaryInspector: inspector,
    });
    assert.equal(resolved.buildId, BUILD_ID);
    assert.deepEqual(resolved.names, [
      "libwechatdb_client.dylib",
      "wechatdb_broker",
      "wechatdb_native_build.json",
    ]);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("macOS native artifact rejects byte tampering and unexpected files", () => {
  for (const mutation of [
    (root) => fs.appendFileSync(path.join(root, "wechatdb_broker"), "tampered"),
    (root) => fs.writeFileSync(path.join(root, "unexpected.txt"), "no"),
  ]) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-native-mac-bad-"));
    try {
      writeFixture(root);
      mutation(root);
      assert.throws(
        () => resolveMacosNativeCoreArtifacts({
          env: environment(root),
          platform: "darwin",
          nowUnix: ISSUED + 1,
          binaryInspector: inspector,
        }),
        /checksum|allowlist|inventory/i
      );
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
});
