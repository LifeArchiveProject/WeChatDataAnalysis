"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  ARTIFACT_NAME,
  BINARY_NAME,
  resolveIntegrityNativeArtifact,
} = require("../scripts/integrity-native-packaging.cjs");

const SOURCE_REPOSITORY = "2977094657/WCDB";
const SOURCE_REVISION = "a".repeat(40);
const UI_REPOSITORY = "LifeArchiveProject/WeChatDataAnalysis";
const UI_REVISION = "b".repeat(40);
const BUILD_ID = "wcdb-macos-integrity-20260804-aabbccdd";
const RUN_ID = 123456;
const ISSUED = Math.floor(Date.now() / 1000) - 60;

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function environment(root, binarySha256) {
  return {
    WCE_INTEGRITY_ARTIFACT_DIR: root,
    WCE_INTEGRITY_ARTIFACT_REPOSITORY: SOURCE_REPOSITORY,
    WCE_INTEGRITY_ARTIFACT_RUN_ID: String(RUN_ID),
    WCE_INTEGRITY_SOURCE_REVISION: SOURCE_REVISION,
    WCE_INTEGRITY_BUILD_ID: BUILD_ID,
    WCE_INTEGRITY_BINARY_SHA256: binarySha256,
    WCE_INTEGRITY_UI_SOURCE_REPOSITORY: UI_REPOSITORY,
    WCE_INTEGRITY_UI_SOURCE_REVISION: UI_REVISION,
  };
}

function writeFixture(root) {
  fs.mkdirSync(root, { recursive: true });
  const binaryPath = path.join(root, BINARY_NAME);
  fs.writeFileSync(binaryPath, "arm64-python-extension-fixture");
  const binarySha256 = sha256(binaryPath);
  const manifest = {
    schemaVersion: 1,
    artifactName: ARTIFACT_NAME,
    platform: "macos",
    architecture: "arm64",
    binaryFileName: BINARY_NAME,
    binarySha256,
    binarySize: fs.statSync(binaryPath).size,
    pythonAbi: "abi3-py311",
    buildId: BUILD_ID,
    buildIssuedAtUnix: ISSUED,
    buildExpiresAtUnix: ISSUED + 45 * 24 * 60 * 60,
    sourceRepository: SOURCE_REPOSITORY,
    sourceRevision: SOURCE_REVISION,
    uiSourceRepository: UI_REPOSITORY,
    uiSourceRevision: UI_REVISION,
    distributionMode: "public",
    development: false,
  };
  const manifestPath = path.join(root, "wce_integrity_build.json");
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  const artifacts = [BINARY_NAME, "wce_integrity_build.json"].map((name) => ({
    path: name,
    sha256: sha256(path.join(root, name)),
    size: fs.statSync(path.join(root, name)).size,
  }));
  const provenance = {
    schemaVersion: 1,
    artifactName: ARTIFACT_NAME,
    producer: "github-actions",
    workflow: "macos-integrity-production.yml",
    repository: SOURCE_REPOSITORY,
    ref: "refs/heads/main",
    runId: RUN_ID,
    runAttempt: 1,
    sourceRevision: SOURCE_REVISION,
    uiSource: { repository: UI_REPOSITORY, revision: UI_REVISION },
    build: {
      id: BUILD_ID,
      issuedAtUnix: ISSUED,
      expiresAtUnix: ISSUED + 45 * 24 * 60 * 60,
      platform: "macos",
      architecture: "arm64",
      pythonAbi: "abi3-py311",
      distributionMode: "public",
    },
    manifestSha256: sha256(manifestPath),
    artifacts,
  };
  const provenancePath = path.join(root, "provenance.json");
  fs.writeFileSync(provenancePath, `${JSON.stringify(provenance, null, 2)}\n`);
  const checksums = [BINARY_NAME, "wce_integrity_build.json", "provenance.json"]
    .map((name) => `${sha256(path.join(root, name))}  ${name}`)
    .join("\n");
  fs.writeFileSync(path.join(root, "SHA256SUMS.txt"), `${checksums}\n`);
  return { binaryPath, binarySha256 };
}

function inspectArm64() {
  return { architectures: ["arm64"], hasPythonEntrypoint: true };
}

test("accepts the exact pinned production artifact", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wce-integrity-fixture-"));
  try {
    const fixture = writeFixture(root);
    const resolved = resolveIntegrityNativeArtifact({
      env: environment(root, fixture.binarySha256),
      platform: "darwin",
      binaryInspector: inspectArm64,
    });
    assert.equal(resolved.binaryPath, fixture.binaryPath);
    assert.equal(resolved.manifest.buildId, BUILD_ID);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("rejects tampered binary bytes", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wce-integrity-tamper-"));
  try {
    const fixture = writeFixture(root);
    fs.appendFileSync(fixture.binaryPath, "tampered");
    assert.throws(() => resolveIntegrityNativeArtifact({
      env: environment(root, fixture.binarySha256),
      platform: "darwin",
      binaryInspector: inspectArm64,
    }), /immutable production pins/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("rejects a mismatched WCDA UI revision", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wce-integrity-ui-"));
  try {
    const fixture = writeFixture(root);
    const env = environment(root, fixture.binarySha256);
    env.WCE_INTEGRITY_UI_SOURCE_REVISION = "c".repeat(40);
    assert.throws(() => resolveIntegrityNativeArtifact({
      env,
      platform: "darwin",
      binaryInspector: inspectArm64,
    }), /immutable production pins/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("rejects unexpected files and development build IDs", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wce-integrity-allowlist-"));
  try {
    const fixture = writeFixture(root);
    fs.writeFileSync(path.join(root, "source.rs"), "private");
    assert.throws(() => resolveIntegrityNativeArtifact({
      env: environment(root, fixture.binarySha256),
      platform: "darwin",
      binaryInspector: inspectArm64,
    }), /allowlist/);
    fs.rmSync(path.join(root, "source.rs"));
    const env = environment(root, fixture.binarySha256);
    env.WCE_INTEGRITY_BUILD_ID = "wcdb-macos-integrity-debug";
    assert.throws(() => resolveIntegrityNativeArtifact({
      env,
      platform: "darwin",
      binaryInspector: inspectArm64,
    }), /not production-grade/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
