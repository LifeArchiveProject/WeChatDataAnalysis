"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  PAYLOAD_FILES,
  PROFILE,
  stageWindowsSourceRuntimeBundle,
} = require("../scripts/windows-source-runtime-promotion.cjs");

const NOW = 1_786_000_100;
const ISSUED = 1_786_000_000;
const EXPIRES = ISSUED + 45 * 24 * 60 * 60;
const REVISION = "a".repeat(40);
const BUILD_ID = "wcdb-windows-native-20260808-aaaaaaaa";

function write(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(
    file,
    typeof value === "string" || Buffer.isBuffer(value)
      ? value
      : `${JSON.stringify(value, null, 2)}\n`
  );
}

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-windows-source-promotion-"));
  const coreDir = path.join(root, "core");
  write(path.join(coreDir, "wechatdb_client.dll"), "client");
  write(path.join(coreDir, "wechatdb_broker.exe"), "broker");
  write(path.join(coreDir, "wechatdb_native_build.json"), {
    schemaVersion: 2,
    distributionMode: "public",
    buildId: BUILD_ID,
    buildIssuedAtUnix: ISSUED,
    buildExpiresAtUnix: EXPIRES,
    sourceRuntime: true,
    windowsHostVerification: "same-user-direct-parent",
    developmentBuild: false,
    codeSignatureEnforced: true,
    rootPublicKeyCompiled: true,
    testHooksEnabled: false,
    stagingPinnedSignerTrust: false,
    offlineBootstrapFeatureBits: 3,
    offlineExportSealFormat: "WES2",
    securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
    securityCheckpointCount: 7,
  });
  const provenance = {
    schemaVersion: 1,
    artifactName: "wechatdb-native-windows-x64-source-public",
    source: { repository: "2977094657/WCDB", revision: REVISION },
    build: {
      id: BUILD_ID,
      issuedAtUnix: ISSUED,
      expiresAtUnix: EXPIRES,
      workflowRunId: 101,
      sourceRuntime: true,
      windowsHostVerification: "same-user-direct-parent",
    },
  };
  write(
    path.join(coreDir, "provenance.json"),
    `\uFEFF${JSON.stringify(provenance, null, 2)}\n`
  );
  return { root, coreDir };
}

test("Windows promotion stages only the restricted native-core allowlist", () => {
  const value = fixture();
  try {
    const stageDir = path.join(value.root, "stage");
    const result = stageWindowsSourceRuntimeBundle({
      coreDir: value.coreDir,
      stageDir,
      releaseTag: "windows-source-runtime-20260808-aaaaaaaa",
      nowUnix: NOW,
    });
    assert.equal(result.manifest.profile, PROFILE);
    assert.equal(result.expiresAtUnix, EXPIRES);
    assert.deepEqual(Object.keys(result.manifest.files), PAYLOAD_FILES.map(([name]) => name));
    assert.equal(result.manifest.components.nativeCore.producerRunId, 101);
    for (const [relative] of PAYLOAD_FILES) {
      assert.equal(fs.statSync(path.join(stageDir, ...relative.split("/"))).isFile(), true);
    }
  } finally {
    fs.rmSync(value.root, { recursive: true, force: true });
  }
});

test("Windows promotion rejects packaged native-core artifacts", () => {
  const value = fixture();
  try {
    const manifestPath = path.join(value.coreDir, "wechatdb_native_build.json");
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    manifest.sourceRuntime = false;
    write(manifestPath, manifest);
    assert.throws(
      () => stageWindowsSourceRuntimeBundle({
        coreDir: value.coreDir,
        stageDir: path.join(value.root, "stage"),
        releaseTag: "windows-source-runtime-20260808-aaaaaaaa",
        nowUnix: NOW,
      }),
      /not the exact restricted source-public profile/
    );
  } finally {
    fs.rmSync(value.root, { recursive: true, force: true });
  }
});

test("Windows promotion workflow verifies Producer output before public no-auth download", () => {
  const workflow = fs.readFileSync(
    path.join(__dirname, "..", "..", ".github", "workflows", "windows-source-runtime-promotion.yml"),
    "utf8"
  );
  const verify = workflow.indexOf("Verify source-public native-core Producer artifact");
  const publish = workflow.indexOf("Publish public Release assets");
  const publicDownload = workflow.indexOf("Verify public no-auth download");
  assert.ok(verify > 0);
  assert.ok(publish > verify);
  assert.ok(publicDownload > publish);
  assert.match(workflow, /WCE_NATIVE_CORE_ARTIFACT_READ_TOKEN/);
  assert.match(workflow, /refs\/tags\/\$env:WCE_SOURCE_RUNTIME_RELEASE_TAG/);
  assert.match(workflow, /--verify-tag/);
  assert.match(workflow, /\$ErrorActionPreference = 'SilentlyContinue'[\s\S]*gh release view/);
  assert.doesNotMatch(workflow, /ghp_[A-Za-z0-9]+/);
});
