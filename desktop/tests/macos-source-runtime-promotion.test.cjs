"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  PAYLOAD_FILES,
  PROFILE,
  stageSourceRuntimeBundle,
} = require("../scripts/macos-source-runtime-promotion.cjs");

const NOW = 1_786_000_100;
const ISSUED = 1_786_000_000;
const EXPIRES = ISSUED + 45 * 24 * 60 * 60;
const REVISION = "a".repeat(40);

function write(file, value, mode = 0o644) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(
    file,
    typeof value === "string" || Buffer.isBuffer(value)
      ? value
      : `${JSON.stringify(value, null, 2)}\n`
  );
  fs.chmodSync(file, mode);
}

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-source-promotion-"));
  const coreDir = path.join(root, "core");
  const xkeyDir = path.join(root, "xkey");
  const integrityDir = path.join(root, "integrity");
  write(path.join(coreDir, "libwechatdb_client.dylib"), "client", 0o755);
  write(path.join(coreDir, "wechatdb_broker"), "broker", 0o755);
  write(path.join(coreDir, "wechatdb_native_build.json"), {
    schemaVersion: 3,
    platform: "macos",
    buildId: "wcdb-macos-native-20260804-aaaaaaaa",
    buildIssuedAtUnix: ISSUED,
    buildExpiresAtUnix: EXPIRES,
    sourceRuntime: true,
    macosHostVerification: "same-user-direct-parent",
    developmentBuild: false,
    codeSignatureEnforced: true,
    rootPublicKeyCompiled: true,
    testHooksEnabled: false,
    offlineBootstrapFeatureBits: 3,
    offlineExportSealFormat: "WES2",
    securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
    securityCheckpointCount: 7,
  });
  write(path.join(coreDir, "provenance.json"), {
    artifactName: "wechatdb-native-macos-arm64-source-public",
    sourceRevision: REVISION,
    runId: 101,
    build: {
      id: "wcdb-macos-native-20260804-aaaaaaaa",
      sourceRuntime: true,
      macosHostVerification: "same-user-direct-parent",
    },
  });

  write(path.join(xkeyDir, "wda_xkey_helper"), "helper", 0o755);
  write(path.join(xkeyDir, "wda_xkey_build.json"), {
    schemaVersion: 1,
    artifactName: "wda-xkey-macos-universal-source-public",
    sourceRuntime: true,
    hostVerification: "same-user-direct-parent",
    sourceRevision: REVISION,
    authorizationMode: "embedded-private",
    onlineRequired: true,
    build: {
      id: "wda-xkey-20260804-aaaaaaaa",
      issuedAtUnix: ISSUED,
      expiresAtUnix: EXPIRES,
      development: false,
    },
  });
  write(path.join(xkeyDir, "wda_xkey_trust.json"), { ok: true });
  write(path.join(xkeyDir, "SHA256SUMS.txt"), "a".repeat(64) + "  wda_xkey_helper\n");
  write(path.join(xkeyDir, "THIRD_PARTY_NOTICES", "FRIDA-COPYING.txt"), "license\n");
  write(path.join(xkeyDir, "provenance.json"), {
    artifactName: "wda-xkey-macos-universal-source-public",
    sourceRevision: REVISION,
    buildId: "wda-xkey-20260804-aaaaaaaa",
    runId: 102,
  });

  write(path.join(integrityDir, "libwce_integrity.dylib"), "integrity", 0o755);
  write(path.join(integrityDir, "wce_integrity_build.json"), {
    schemaVersion: 1,
    artifactName: "wce-integrity-macos-arm64-production",
    platform: "macos",
    architecture: "arm64",
    development: false,
    distributionMode: "public",
    buildId: "wcdb-macos-integrity-20260804-aaaaaaaa",
    buildIssuedAtUnix: ISSUED,
    buildExpiresAtUnix: EXPIRES,
    sourceRevision: REVISION,
  });
  write(path.join(integrityDir, "provenance.json"), {
    artifactName: "wce-integrity-macos-arm64-production",
    runId: 103,
  });
  return { root, coreDir, xkeyDir, integrityDir };
}

test("promotion stages only the restricted source-runtime allowlist", () => {
  const value = fixture();
  const stageDir = path.join(value.root, "stage");
  const result = stageSourceRuntimeBundle({
    ...value,
    stageDir,
    releaseTag: "macos-source-runtime-20260804-aaaaaaaa",
    nowUnix: NOW,
  });
  assert.equal(result.manifest.profile, PROFILE);
  assert.equal(result.expiresAtUnix, EXPIRES);
  assert.deepEqual(Object.keys(result.manifest.files), PAYLOAD_FILES.map(([name]) => name));
  assert.equal(result.manifest.components.nativeCore.producerRunId, 101);
  assert.equal(result.manifest.components.databaseKey.producerRunId, 102);
  assert.equal(result.manifest.components.exportIntegrity.producerRunId, 103);
  for (const [relative, executable] of PAYLOAD_FILES) {
    const file = path.join(stageDir, ...relative.split("/"));
    assert.equal(fs.statSync(file).isFile(), true);
    if (process.platform !== "win32") {
      assert.equal((fs.statSync(file).mode & 0o111) !== 0, executable);
    }
  }
});

test("promotion rejects a packaged or development native core", () => {
  const value = fixture();
  const manifestPath = path.join(value.coreDir, "wechatdb_native_build.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.sourceRuntime = false;
  write(manifestPath, manifest);
  assert.throws(
    () => stageSourceRuntimeBundle({
      ...value,
      stageDir: path.join(value.root, "stage"),
      releaseTag: "macos-source-runtime-20260804-aaaaaaaa",
      nowUnix: NOW,
    }),
    /not the exact restricted source-public profile/
  );
});

test("promotion workflow never exposes a private token in a public asset", () => {
  const workflow = fs.readFileSync(
    path.join(__dirname, "..", "..", ".github", "workflows", "macos-source-runtime-promotion.yml"),
    "utf8"
  );
  assert.match(workflow, /WCE_MACOS_PRODUCER_READ_TOKEN/);
  assert.match(workflow, /Verify public no-auth download/);
  assert.match(workflow, /env -u GH_TOKEN -u GITHUB_TOKEN curl/);
  assert.doesNotMatch(workflow, /ghp_[A-Za-z0-9]+/);
});
