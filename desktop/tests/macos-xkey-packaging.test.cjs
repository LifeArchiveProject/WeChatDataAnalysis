"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  ARTIFACT_FILE_NAMES,
  BUILD_LIFETIME_SECONDS,
  contract,
  macosXkeyManifestErrors,
  resolveMacosXkeyArtifacts,
  stageMacosXkeyArtifacts,
} = require("../scripts/macos-xkey-packaging.cjs");

const ISSUED_AT = Math.floor(Date.now() / 1000) - 60;
const BUILD_ID = "wda-xkey-20260803";
const SOURCE_REVISION = "a".repeat(40);
const HELPER_SIGNER = "2".repeat(64);
const HOST_SIGNER = "3".repeat(64);
const REPOSITORY = "owner/private-producer";
const RUN_ID = 123456;

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function makeFixture(root, manifestPatch = {}) {
  fs.mkdirSync(root, { recursive: true });
  const helperPath = path.join(root, contract.helperFileName);
  fs.writeFileSync(helperPath, "universal-macho-fixture");
  const noticePath = path.join(root, contract.thirdPartyNoticeFileName);
  fs.mkdirSync(path.dirname(noticePath), { recursive: true });
  fs.writeFileSync(noticePath, "Frida test license\n");
  const metadata = (filePath) => ({ sha256: sha256(filePath), size: fs.statSync(filePath).size });
  const manifest = {
    schemaVersion: 1,
    artifactType: "wda-xkey-macos-key-capture",
    artifactName: contract.artifactName,
    distributionMode: "public",
    platform: "macos",
    architecture: "universal2",
    architectures: ["arm64", "x86_64"],
    appId: contract.appId,
    sourceRevision: SOURCE_REVISION,
    build: {
      id: BUILD_ID,
      issuedAtUnix: ISSUED_AT,
      expiresAtUnix: ISSUED_AT + BUILD_LIFETIME_SECONDS,
      validitySeconds: BUILD_LIFETIME_SECONDS,
      development: false,
    },
    authorizationMode: "embedded-private",
    onlineRequired: true,
    signing: {
      mode: "self-signed",
      helperLeafCertificateSha256: HELPER_SIGNER,
      hostLeafCertificateSha256: HOST_SIGNER,
      teamId: "",
      hardenedRuntime: true,
      timestamped: false,
      notarized: false,
    },
    files: {
      [contract.helperFileName]: metadata(helperPath),
      [contract.thirdPartyNoticeFileName]: metadata(noticePath),
    },
    ...manifestPatch,
  };
  const manifestPath = path.join(root, contract.manifestFileName);
  fs.writeFileSync(manifestPath, JSON.stringify(manifest));
  const trustPath = path.join(root, contract.trustFileName);
  fs.writeFileSync(trustPath, JSON.stringify({
    schemaVersion: 1,
    artifactName: contract.artifactName,
    sourceRevision: SOURCE_REVISION,
    buildId: BUILD_ID,
    appId: contract.appId,
    producerRepository: REPOSITORY,
    producerWorkflowRunId: RUN_ID,
    helperIdentifier: contract.bundleId,
    helperLeafCertificateSha256: HELPER_SIGNER,
    hostIdentifier: contract.hostSigningIdentifier,
    hostLeafCertificateSha256: HOST_SIGNER,
    signingMode: "self-signed",
    manifestSha256: sha256(manifestPath),
  }));
  const checksummed = [
    contract.helperFileName,
    contract.thirdPartyNoticeFileName,
    contract.manifestFileName,
    contract.trustFileName,
  ].sort();
  const checksumsPath = path.join(root, contract.checksumsFileName);
  fs.writeFileSync(
    checksumsPath,
    checksummed.map((name) => `${sha256(path.join(root, name))}  ${name}`).join("\n") + "\n"
  );
  fs.writeFileSync(path.join(root, contract.provenanceFileName), JSON.stringify({
    schemaVersion: 1,
    producer: "github-actions",
    workflow: ".github/workflows/macos-key-capture-production.yml",
    repository: REPOSITORY,
    runId: RUN_ID,
    runAttempt: 1,
    sourceRevision: SOURCE_REVISION,
    buildId: BUILD_ID,
    artifactName: contract.artifactName,
    manifestSha256: sha256(manifestPath),
    trustSha256: sha256(trustPath),
    checksumsSha256: sha256(checksumsPath),
  }));
  return { helperPath, manifest };
}

function envFor(root) {
  return {
    WCE_MACOS_XKEY_ARTIFACT_DIR: root,
    WCE_MACOS_XKEY_ARTIFACT_REPOSITORY: REPOSITORY,
    WCE_MACOS_XKEY_ARTIFACT_RUN_ID: String(RUN_ID),
    WCE_MACOS_XKEY_SOURCE_REVISION: SOURCE_REVISION,
    WCE_MACOS_XKEY_BUILD_ID: BUILD_ID,
    WCE_MACOS_KEY_HELPER_SIGNER_SHA256: HELPER_SIGNER,
    WCE_MACOS_WCDA_HOST_SIGNER_SHA256: HOST_SIGNER,
  };
}

function inspectValid() {
  return {
    identifier: contract.bundleId,
    leafSha256: HELPER_SIGNER,
    architectures: new Set(["arm64", "x86_64"]),
  };
}

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "wda-xkey-package-test-"));
}

test("manifest exposes only the exact minimal public metadata", () => {
  const root = tempDir();
  try {
    const { manifest } = makeFixture(root);
    assert.deepEqual(macosXkeyManifestErrors(manifest, { nowUnix: ISSUED_AT + 1 }), []);
    assert.equal(manifest.authorizationMode, "embedded-private");
    assert.equal(manifest.onlineRequired, true);
    assert.ok(macosXkeyManifestErrors({ ...manifest, unexpectedDetails: {} }).length > 0);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("darwin packaging refuses implicit or unpinned helper artifacts", () => {
  assert.throws(
    () => resolveMacosXkeyArtifacts({ env: {}, platform: "darwin", binaryInspector: inspectValid }),
    /WCE_MACOS_XKEY_ARTIFACT_DIR/
  );
  const root = tempDir();
  try {
    makeFixture(root);
    assert.throws(
      () => resolveMacosXkeyArtifacts({
        env: { WCE_MACOS_XKEY_ARTIFACT_DIR: root }, platform: "darwin", binaryInspector: inspectValid,
      }),
      /WCE_MACOS_XKEY_ARTIFACT_REPOSITORY/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("staging copies the exact six-file Producer artifact", () => {
  const root = tempDir();
  const artifact = path.join(root, "artifact");
  const native = path.join(root, "native");
  try {
    makeFixture(artifact);
    const result = stageMacosXkeyArtifacts({
      env: envFor(artifact),
      platform: "darwin",
      destinationNativeDir: native,
      binaryInspector: inspectValid,
      nowUnix: ISSUED_AT + 1,
      logger: { log() {} },
    });
    assert.equal(result.staged, true);
    assert.equal(ARTIFACT_FILE_NAMES.length, 6);
    const destination = path.join(native, ...contract.bundleRelativePath.split("/"));
    for (const name of ARTIFACT_FILE_NAMES) assert.ok(fs.statSync(path.join(destination, name)).isFile(), name);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("staging rejects tampering, expiry, signer drift, and missing x86_64", () => {
  const root = tempDir();
  try {
    const artifact = path.join(root, "artifact");
    const { helperPath } = makeFixture(artifact);
    fs.appendFileSync(helperPath, "patched");
    assert.throws(
      () => resolveMacosXkeyArtifacts({
        env: envFor(artifact), platform: "darwin", binaryInspector: inspectValid, nowUnix: ISSUED_AT + 1,
      }),
      /checksum set|hash\/size/
    );
    fs.rmSync(artifact, { recursive: true, force: true });
    makeFixture(artifact);
    assert.throws(
      () => resolveMacosXkeyArtifacts({
        env: envFor(artifact), platform: "darwin", binaryInspector: inspectValid,
        nowUnix: ISSUED_AT + BUILD_LIFETIME_SECONDS,
      }),
      /fixed expiration/
    );
    assert.throws(
      () => resolveMacosXkeyArtifacts({
        env: envFor(artifact), platform: "darwin", nowUnix: ISSUED_AT + 1,
        binaryInspector: () => ({
          identifier: contract.bundleId,
          leafSha256: "4".repeat(64),
          architectures: new Set(["arm64"]),
        }),
      }),
      /signature or Universal2 architecture/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("non-mac packaging ignores the optional Mac artifact channel", () => {
  const resolved = resolveMacosXkeyArtifacts({ env: {}, platform: "win32" });
  assert.equal(resolved.required, false);
  assert.equal(resolved.artifactDir, null);
});
