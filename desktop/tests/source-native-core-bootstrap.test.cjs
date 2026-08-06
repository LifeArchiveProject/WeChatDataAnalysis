"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  ENV_INTEGRITY_NATIVE_PATH,
  ENV_MACOS_DB_KEY_BUNDLE,
  ENV_SOURCE_NATIVE_CORE_DIR,
  applySourceRuntimeEnvironment,
  ensureSourceNativeCore,
  publicReleaseUrl,
  validateSourceRuntimeDirectory,
} = require("../src/source-native-core-bootstrap.cjs");
const { resolveNativeCoreRuntimeDir } = require("../src/native-core-path.cjs");

const NOW_UNIX = 1785839600;
const BUILD_ISSUED_AT_UNIX = NOW_UNIX - 60;
const BUILD_EXPIRES_AT_UNIX = BUILD_ISSUED_AT_UNIX + 45 * 24 * 60 * 60;
const RUNTIME_EXPIRES_AT_UNIX = NOW_UNIX + 30 * 24 * 60 * 60;
const ARCHIVE_CONTENT = Buffer.from("fixture-public-release-archive", "utf8");
const TRACKED_PIN = Object.freeze({
  schemaVersion: 2,
  platform: "darwin",
  architecture: "arm64",
  publisherRepository: "LifeArchiveProject/WeChatDataAnalysis",
  releaseTag: "macos-source-runtime-20260806-85320d56-d5c9a29d",
  assetName: "wechatdataanalysis-macos-source-runtime-arm64-v1.tar.gz",
  assetSha256: "335c50bd82340a0f526f5e0456555ebe73bf33980c6ff94a9a34a7f2f42cc096",
  runtimeManifestSha256: "dcc7ef896783d910a58a1722da88899625b986819e8c384d8e11b941cb7b5cd6",
  expiresAtUnix: 1789726924,
});

const SOURCE_PUBLIC_CORE_MANIFEST = Object.freeze({
  schemaVersion: 3,
  platform: "macos",
  distributionMode: "public",
  buildId: "wcdb-macos-native-fixture-abcd1234",
  buildIssuedAtUnix: BUILD_ISSUED_AT_UNIX,
  buildExpiresAtUnix: BUILD_EXPIRES_AT_UNIX,
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
  sourceRuntime: true,
  macosHostVerification: "same-user-direct-parent",
});

function sha256Buffer(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

const PAYLOADS = new Map([
  ["native-core/libwechatdb_client.dylib", Buffer.from("client")],
  ["native-core/wechatdb_broker", Buffer.from("broker")],
  [
    "native-core/wechatdb_native_build.json",
    Buffer.from(`${JSON.stringify(SOURCE_PUBLIC_CORE_MANIFEST, null, 2)}\n`),
  ],
  ["db-key/SHA256SUMS.txt", Buffer.from("fixture checksums")],
  ["db-key/THIRD_PARTY_NOTICES/FRIDA-COPYING.txt", Buffer.from("fixture notice")],
  ["db-key/provenance.json", Buffer.from('{"fixture":true}\n')],
  ["db-key/wda_xkey_build.json", Buffer.from('{"fixture":true}\n')],
  ["db-key/wda_xkey_helper", Buffer.from("helper")],
  ["db-key/wda_xkey_trust.json", Buffer.from('{"fixture":true}\n')],
  ["integrity/libwce_integrity.dylib", Buffer.from("integrity")],
]);
const EXECUTABLES = new Set([
  "native-core/libwechatdb_client.dylib",
  "native-core/wechatdb_broker",
  "db-key/wda_xkey_helper",
  "integrity/libwce_integrity.dylib",
]);
const RUNTIME_MANIFEST = Object.freeze({
  schemaVersion: 1,
  profile: "macos-source-public",
  platform: "darwin",
  architecture: "arm64",
  releaseTag: "macos-source-runtime-fixture-abcd1234",
  createdAtUnix: NOW_UNIX - 30,
  expiresAtUnix: RUNTIME_EXPIRES_AT_UNIX,
  components: {
    nativeCore: {
      artifactName: "wechatdb-native-macos-arm64-source-public",
      buildId: SOURCE_PUBLIC_CORE_MANIFEST.buildId,
      sourceRevision: "11".repeat(20),
      producerRunId: 101,
      expiresAtUnix: BUILD_EXPIRES_AT_UNIX,
      path: "native-core",
    },
    databaseKey: {
      artifactName: "wda-xkey-macos-universal-source-public",
      buildId: "wda-xkey-fixture-abcd1234",
      sourceRevision: "22".repeat(20),
      producerRunId: 102,
      expiresAtUnix: BUILD_EXPIRES_AT_UNIX,
      path: "db-key",
    },
    exportIntegrity: {
      artifactName: "wce-integrity-macos-arm64-production",
      buildId: "wce-integrity-fixture-abcd1234",
      sourceRevision: "33".repeat(20),
      producerRunId: 103,
      expiresAtUnix: BUILD_EXPIRES_AT_UNIX,
      path: "integrity",
    },
  },
  files: Object.fromEntries(
    [...PAYLOADS].map(([name, value]) => [
      name,
      {
        sha256: sha256Buffer(value),
        size: value.length,
        executable: EXECUTABLES.has(name),
      },
    ])
  ),
});
const RUNTIME_MANIFEST_RAW = Buffer.from(`${JSON.stringify(RUNTIME_MANIFEST, null, 2)}\n`);
const PIN = Object.freeze({
  schemaVersion: 2,
  platform: "darwin",
  architecture: "arm64",
  publisherRepository: "LifeArchiveProject/WeChatDataAnalysis",
  releaseTag: RUNTIME_MANIFEST.releaseTag,
  assetName: "wechatdataanalysis-macos-source-runtime-arm64-v1.tar.gz",
  assetSha256: sha256Buffer(ARCHIVE_CONTENT),
  runtimeManifestSha256: sha256Buffer(RUNTIME_MANIFEST_RAW),
  expiresAtUnix: RUNTIME_EXPIRES_AT_UNIX,
});

const ARCHIVE_NAMES = [
  "./",
  "./db-key/",
  "./runtime-manifest.json",
  "./integrity/",
  "./native-core/",
  "./native-core/wechatdb_native_build.json",
  "./native-core/libwechatdb_client.dylib",
  "./native-core/wechatdb_broker",
  "./integrity/libwce_integrity.dylib",
  "./db-key/THIRD_PARTY_NOTICES/",
  "./db-key/provenance.json",
  "./db-key/wda_xkey_trust.json",
  "./db-key/wda_xkey_build.json",
  "./db-key/wda_xkey_helper",
  "./db-key/SHA256SUMS.txt",
  "./db-key/THIRD_PARTY_NOTICES/FRIDA-COPYING.txt",
];

function writeConfig(root, pin = PIN) {
  const configPath = path.join(root, "pin.json");
  fs.writeFileSync(configPath, `${JSON.stringify(pin, null, 2)}\n`);
  return configPath;
}

function writeRuntime(root) {
  for (const [relative, content] of PAYLOADS) {
    const file = path.join(root, ...relative.split("/"));
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  }
  fs.writeFileSync(path.join(root, "runtime-manifest.json"), RUNTIME_MANIFEST_RAW);
}

function fixtureTools({ archiveNames = ARCHIVE_NAMES, onExtract = writeRuntime } = {}) {
  let downloads = 0;
  let extractions = 0;
  const spawnSyncImpl = (command, args, options) => {
    if (command === "/usr/bin/curl") {
      downloads += 1;
      assert.equal(options.shell, false);
      assert.equal(options.env.GH_TOKEN, undefined);
      assert.equal(options.env.GITHUB_TOKEN, undefined);
      assert.equal(args.at(-1), publicReleaseUrl(PIN));
      fs.writeFileSync(args[args.indexOf("--output") + 1], ARCHIVE_CONTENT);
      return { status: 0, stdout: "", stderr: "" };
    }
    if (command === "/usr/bin/tar" && args[0] === "-tzf") {
      return { status: 0, stdout: `${archiveNames.join("\n")}\n`, stderr: "" };
    }
    if (command === "/usr/bin/tar" && args[0] === "-tvzf") {
      const stdout = archiveNames
        .map((name) => `${name.endsWith("/") ? "d" : "-"}rwxr-xr-x fixture ${name}`)
        .join("\n");
      return { status: 0, stdout: `${stdout}\n`, stderr: "" };
    }
    if (command === "/usr/bin/tar" && args[0] === "-xzf") {
      extractions += 1;
      onExtract(args[args.indexOf("-C") + 1]);
      return { status: 0, stdout: "", stderr: "" };
    }
    throw new Error(`unexpected command: ${command} ${args.join(" ")}`);
  };
  return {
    spawnSyncImpl,
    get downloads() {
      return downloads;
    },
    get extractions() {
      return extractions;
    },
  };
}

function withTempRoot(callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-source-runtime-"));
  try {
    return callback(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("tracked macOS source pin selects the exact public WCDA Release asset", () => {
  const tracked = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "..", "resources", "native-core-source-macos.json"),
      "utf8"
    )
  );
  assert.deepEqual(tracked, TRACKED_PIN);
  assert.equal(
    publicReleaseUrl(tracked),
    "https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/download/" +
      "macos-source-runtime-20260806-85320d56-d5c9a29d/" +
      "wechatdataanalysis-macos-source-runtime-arm64-v1.tar.gz"
  );
});

test("macOS source bootstrap downloads publicly once and reuses the verified cache", () =>
  withTempRoot((root) => {
    const tools = fixtureTools();
    const options = {
      arch: "arm64",
      cacheRoot: path.join(root, "cache"),
      configPath: writeConfig(root),
      env: { GH_TOKEN: "must-not-leak", GITHUB_TOKEN: "must-not-leak" },
      nowUnix: NOW_UNIX,
      platform: "darwin",
      spawnSyncImpl: tools.spawnSyncImpl,
    };
    const first = ensureSourceNativeCore(options);
    assert.equal(first.reason, "downloaded");
    assert.equal(first.policy.artifactState, "source-public");
    assert.equal(tools.downloads, 1);
    assert.equal(tools.extractions, 1);
    validateSourceRuntimeDirectory(first.runtimeDir, PIN, { nowUnix: NOW_UNIX });

    const second = ensureSourceNativeCore({
      ...options,
      spawnSyncImpl() {
        throw new Error("verified cache must not invoke curl or tar");
      },
    });
    assert.equal(second.reason, "verified-cache");
    assert.equal(second.runtimeDir, first.runtimeDir);
  }));

test("tampered cached runtime is repaired from the pinned public asset", () =>
  withTempRoot((root) => {
    const tools = fixtureTools();
    const options = {
      arch: "arm64",
      cacheRoot: path.join(root, "cache"),
      configPath: writeConfig(root),
      env: {},
      nowUnix: NOW_UNIX,
      platform: "darwin",
      spawnSyncImpl: tools.spawnSyncImpl,
    };
    const first = ensureSourceNativeCore(options);
    fs.writeFileSync(path.join(first.nativeDir, "wechatdb_broker"), "tampered");
    const second = ensureSourceNativeCore(options);
    assert.equal(second.reason, "downloaded");
    assert.equal(tools.downloads, 2);
    validateSourceRuntimeDirectory(second.runtimeDir, PIN, { nowUnix: NOW_UNIX });
  }));

test("archive path traversal is rejected before extraction", () =>
  withTempRoot((root) => {
    const names = [...ARCHIVE_NAMES];
    names[names.indexOf("./native-core/wechatdb_broker")] = "../../outside";
    const tools = fixtureTools({ archiveNames: names });
    assert.throws(
      () =>
        ensureSourceNativeCore({
          arch: "arm64",
          cacheRoot: path.join(root, "cache"),
          configPath: writeConfig(root),
          env: {},
          nowUnix: NOW_UNIX,
          platform: "darwin",
          spawnSyncImpl: tools.spawnSyncImpl,
        }),
      /path traversal/
    );
    assert.equal(tools.extractions, 0);
  }));

test("expired tracked runtime fails before any network request", () =>
  withTempRoot((root) => {
    const expired = { ...PIN, expiresAtUnix: NOW_UNIX };
    assert.throws(
      () =>
        ensureSourceNativeCore({
          arch: "arm64",
          cacheRoot: path.join(root, "cache"),
          configPath: writeConfig(root, expired),
          env: {},
          nowUnix: NOW_UNIX,
          platform: "darwin",
          spawnSyncImpl() {
            throw new Error("expired pin must fail before curl");
          },
        }),
      /已过期.*拉取最新代码/
    );
  }));

test("source runtime injects native core, XKey, and export-integrity paths together", () =>
  withTempRoot((root) => {
    writeRuntime(root);
    const validated = validateSourceRuntimeDirectory(root, PIN, { nowUnix: NOW_UNIX });
    const env = {};
    applySourceRuntimeEnvironment(env, validated);
    assert.equal(env[ENV_SOURCE_NATIVE_CORE_DIR], path.join(root, "native-core"));
    assert.equal(env[ENV_MACOS_DB_KEY_BUNDLE], path.join(root, "db-key"));
    assert.equal(
      env[ENV_INTEGRITY_NATIVE_PATH],
      path.join(root, "integrity", "libwce_integrity.dylib")
    );
  }));

test("runtime directory honors a source-only override and packaged apps ignore it", () => {
  const env = { [ENV_SOURCE_NATIVE_CORE_DIR]: "/tmp/public-native" };
  assert.equal(
    resolveNativeCoreRuntimeDir({
      env,
      isPackaged: false,
      repoRoot: "/repo",
      resourcesPath: "/app/resources",
    }),
    path.resolve("/tmp/public-native")
  );
  assert.equal(
    resolveNativeCoreRuntimeDir({
      env,
      isPackaged: true,
      repoRoot: "/repo",
      resourcesPath: "/app/resources",
    }),
    path.resolve("/app/resources", "backend", "native")
  );
});

test("development launcher finishes the complete public runtime preflight before spawning", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "scripts", "dev.cjs"), "utf8");
  const preflight = source.indexOf("ensureSourceNativeCore(");
  const frontendSpawn = source.indexOf("const frontend = spawnLogged(");
  assert.ok(preflight >= 0);
  assert.ok(frontendSpawn > preflight);
  assert.match(source, /applySourceRuntimeEnvironment\(sharedEnv, sourceNativeCore\)/);
});

test("public source bootstrap contains no private Producer or gh authentication path", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "source-native-core-bootstrap.cjs"),
    "utf8"
  );
  const config = fs.readFileSync(
    path.join(__dirname, "..", "resources", "native-core-source-macos.json"),
    "utf8"
  );
  assert.doesNotMatch(`${source}\n${config}`, /2977094657\/WCDB|gh auth|gh run download/);
  assert.match(source, /"\/usr\/bin\/curl"/);
  assert.match(source, /"\/usr\/bin\/tar"/);
  assert.match(source, /delete clean\[name\]/);
});

test("verified runtime restores executable modes only after full validation", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "source-native-core-bootstrap.cjs"),
    "utf8"
  );
  assert.match(source, /validateSourceRuntimeDirectory\(temporary, pin, \{ nowUnix \}\);\s+ensureRuntimePermissions\(temporary\);/);
  assert.match(source, /executable \? 0o755 : 0o644/);
});
