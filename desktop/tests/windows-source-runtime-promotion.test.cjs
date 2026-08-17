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
const {
  WINDOWS_NATIVE_ASR_ABI_VERSION,
  WINDOWS_NATIVE_ASR_AUTHORIZATION,
  WINDOWS_NATIVE_ASR_EXPORTS,
  WINDOWS_NATIVE_ASR_FEATURE_BIT,
  WINDOWS_NATIVE_ASR_TARGET,
} = require("../src/windows-native-asr-capability.cjs");
const { buildWindowsPeWithExports } = require("./pe-export-fixture.cjs");

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

function fixture({ clientExports = WINDOWS_NATIVE_ASR_EXPORTS } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-windows-source-promotion-"));
  const coreDir = path.join(root, "core");
  write(path.join(coreDir, "wechatdb_client.dll"), buildWindowsPeWithExports(clientExports));
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
    nativeAsrAbiVersion: WINDOWS_NATIVE_ASR_ABI_VERSION,
    nativeAsrAuthorization: WINDOWS_NATIVE_ASR_AUTHORIZATION,
    nativeAsrFeatureBit: WINDOWS_NATIVE_ASR_FEATURE_BIT,
    nativeAsrTarget: WINDOWS_NATIVE_ASR_TARGET,
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

test("Windows promotion rejects a source runtime without fused ASR exports", () => {
  const value = fixture({ clientExports: ["wce_client_abi_version"] });
  try {
    assert.throws(
      () => stageWindowsSourceRuntimeBundle({
        coreDir: value.coreDir,
        stageDir: path.join(value.root, "stage"),
        releaseTag: "windows-source-runtime-20260808-aaaaaaaa",
        nowUnix: NOW,
      }),
      /missing fused ASR ABI exports/
    );
  } finally {
    fs.rmSync(value.root, { recursive: true, force: true });
  }
});

test("Windows promotion rejects a source runtime with separate ASR authorization", () => {
  const value = fixture();
  try {
    const manifestPath = path.join(value.coreDir, "wechatdb_native_build.json");
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    manifest.nativeAsrAuthorization = "native-asr";
    write(manifestPath, manifest);
    assert.throws(
      () => stageWindowsSourceRuntimeBundle({
        coreDir: value.coreDir,
        stageDir: path.join(value.root, "stage"),
        releaseTag: "windows-source-runtime-20260808-aaaaaaaa",
        nowUnix: NOW,
      }),
      /nativeAsrAuthorization must equal database-read/
    );
  } finally {
    fs.rmSync(value.root, { recursive: true, force: true });
  }
});

test("Windows promotion workflow verifies the exact Producer Release asset before public no-auth download", () => {
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
  assert.match(workflow, /windows-native-\$env:NATIVE_BUILD_ID/);
  assert.match(
    workflow,
    /wechatdb-native-windows-x64-source-public-\$env:NATIVE_BUILD_ID\.zip/
  );
  assert.match(workflow, /gh release download \$releaseTag/);
  assert.match(workflow, /native_core_source_public_sha256/);
  assert.match(
    workflow,
    /Get-FileHash -LiteralPath \$archive -Algorithm SHA256/
  );
  assert.match(
    workflow,
    /\$actualArchiveSha256 -cne \$env:NATIVE_SOURCE_PUBLIC_SHA256/
  );
  assert.ok(
    workflow.indexOf("$actualArchiveSha256 =")
      < workflow.indexOf("Expand-Archive -LiteralPath $archive")
  );
  assert.match(workflow, /Expand-Archive -LiteralPath \$archive -DestinationPath \$destination/);
  assert.match(
    workflow,
    /\[string\]\$provenance\.build\.workflowRunId -cne \$env:NATIVE_RUN_ID/
  );
  assert.doesNotMatch(workflow, /gh run download/);
  assert.match(workflow, /refs\/tags\/\$env:WCE_SOURCE_RUNTIME_RELEASE_TAG/);
  assert.match(workflow, /--verify-tag/);
  assert.match(workflow, /\$ErrorActionPreference = 'SilentlyContinue'[\s\S]*gh release view/);
  assert.doesNotMatch(workflow, /ghp_[A-Za-z0-9]+/);
});
