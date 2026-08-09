"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  ensureWindowsSourceNativeCore,
  publicReleaseUrl,
  validateWindowsSourceRuntimeDirectory,
} = require("../src/windows-source-native-core-bootstrap.cjs");
const {
  applySourceRuntimeEnvironment,
  ensureSourceNativeCore,
} = require("../src/source-native-core-bootstrap.cjs");

const NOW_UNIX = 1786162000;
const ISSUED_AT_UNIX = NOW_UNIX - 60;
const EXPIRES_AT_UNIX = ISSUED_AT_UNIX + 45 * 24 * 60 * 60;
const ARCHIVE_CONTENT = Buffer.from("fixture-windows-source-runtime", "utf8");

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

const NATIVE_MANIFEST = Object.freeze({
  schemaVersion: 2,
  distributionMode: "public",
  buildId: "wcdb-windows-source-fixture-abcd1234",
  buildIssuedAtUnix: ISSUED_AT_UNIX,
  buildExpiresAtUnix: EXPIRES_AT_UNIX,
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
  securityNoticeSha256: "44".repeat(32),
  securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
  securityCheckpointCount: 7,
  securityCheckpointSetSha256: "55".repeat(32),
  sourceRuntime: true,
  windowsHostVerification: "same-user-direct-parent",
});

const PAYLOADS = new Map([
  ["native-core/wechatdb_client.dll", Buffer.from("client")],
  ["native-core/wechatdb_broker.exe", Buffer.from("broker")],
  [
    "native-core/wechatdb_native_build.json",
    Buffer.from(`${JSON.stringify(NATIVE_MANIFEST, null, 2)}\n`),
  ],
]);

const RUNTIME_MANIFEST = Object.freeze({
  schemaVersion: 1,
  profile: "windows-source-public",
  platform: "win32",
  architecture: "x64",
  releaseTag: "windows-source-runtime-fixture-abcd1234",
  createdAtUnix: NOW_UNIX - 30,
  expiresAtUnix: EXPIRES_AT_UNIX,
  components: {
    nativeCore: {
      artifactName: "wechatdb-native-windows-x64-source-public",
      buildId: NATIVE_MANIFEST.buildId,
      sourceRevision: "11".repeat(20),
      producerRunId: 101,
      expiresAtUnix: EXPIRES_AT_UNIX,
      path: "native-core",
    },
  },
  files: Object.fromEntries(
    [...PAYLOADS].map(([name, value]) => [
      name,
      { sha256: sha256(value), size: value.length, executable: name.endsWith(".exe") },
    ])
  ),
});
const RUNTIME_MANIFEST_RAW = Buffer.from(`${JSON.stringify(RUNTIME_MANIFEST, null, 2)}\n`);
const PIN = Object.freeze({
  schemaVersion: 2,
  platform: "win32",
  architecture: "x64",
  publisherRepository: "LifeArchiveProject/WeChatDataAnalysis",
  releaseTag: RUNTIME_MANIFEST.releaseTag,
  assetName: "wechatdataanalysis-windows-source-runtime-x64-v1.tar.gz",
  assetSha256: sha256(ARCHIVE_CONTENT),
  runtimeManifestSha256: sha256(RUNTIME_MANIFEST_RAW),
  expiresAtUnix: EXPIRES_AT_UNIX,
});
const ARCHIVE_NAMES = [
  "./",
  "./runtime-manifest.json",
  "./native-core/",
  "./native-core/wechatdb_client.dll",
  "./native-core/wechatdb_broker.exe",
  "./native-core/wechatdb_native_build.json",
];

function writeConfig(root, pin = PIN) {
  const file = path.join(root, "pin.json");
  fs.writeFileSync(file, `${JSON.stringify(pin, null, 2)}\n`);
  return file;
}

function writeRuntime(root) {
  for (const [relative, content] of PAYLOADS) {
    const file = path.join(root, ...relative.split("/"));
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  }
  fs.writeFileSync(path.join(root, "runtime-manifest.json"), RUNTIME_MANIFEST_RAW);
}

function fixtureTools() {
  let downloads = 0;
  const spawnSyncImpl = (command, args, options) => {
    if (command === "curl.exe") {
      downloads += 1;
      assert.equal(options.shell, false);
      assert.equal(options.env.GH_TOKEN, undefined);
      assert.equal(args.at(-1), publicReleaseUrl(PIN));
      fs.writeFileSync(args[args.indexOf("--output") + 1], ARCHIVE_CONTENT);
      return { status: 0, stdout: "", stderr: "" };
    }
    if (command === "tar.exe" && args[0] === "-tzf") {
      return { status: 0, stdout: `${ARCHIVE_NAMES.join("\n")}\n`, stderr: "" };
    }
    if (command === "tar.exe" && args[0] === "-tvzf") {
      return {
        status: 0,
        stdout: `${ARCHIVE_NAMES.map((name) => `${name.endsWith("/") ? "d" : "-"}rwx fixture ${name}`).join("\n")}\n`,
        stderr: "",
      };
    }
    if (command === "tar.exe" && args[0] === "-xzf") {
      writeRuntime(args[args.indexOf("-C") + 1]);
      return { status: 0, stdout: "", stderr: "" };
    }
    throw new Error(`unexpected command: ${command} ${args.join(" ")}`);
  };
  return { spawnSyncImpl, get downloads() { return downloads; } };
}

function withTempRoot(callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-windows-source-runtime-"));
  try {
    return callback(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("Windows source bootstrap downloads publicly once and reuses verified cache", () =>
  withTempRoot((root) => {
    const tools = fixtureTools();
    const options = {
      arch: "x64",
      cacheRoot: path.join(root, "cache"),
      configPath: writeConfig(root),
      env: { GH_TOKEN: "must-not-leak", GITHUB_TOKEN: "must-not-leak" },
      nowUnix: NOW_UNIX,
      platform: "win32",
      spawnSyncImpl: tools.spawnSyncImpl,
    };
    const first = ensureWindowsSourceNativeCore(options);
    assert.equal(first.reason, "downloaded");
    assert.equal(first.policy.artifactState, "source-public");
    assert.equal(tools.downloads, 1);
    validateWindowsSourceRuntimeDirectory(first.runtimeDir, PIN, { nowUnix: NOW_UNIX });

    const second = ensureWindowsSourceNativeCore({
      ...options,
      spawnSyncImpl() {
        throw new Error("verified cache must not invoke external tools");
      },
    });
    assert.equal(second.reason, "verified-cache");
    assert.equal(second.runtimeDir, first.runtimeDir);
  }));

test("Windows source bootstrap rejects an expired pin before network access", () =>
  withTempRoot((root) => {
    assert.throws(
      () => ensureWindowsSourceNativeCore({
        arch: "x64",
        cacheRoot: path.join(root, "cache"),
        configPath: writeConfig(root, { ...PIN, expiresAtUnix: NOW_UNIX }),
        env: {},
        nowUnix: NOW_UNIX,
        platform: "win32",
        spawnSyncImpl() {
          throw new Error("expired pin must fail before network access");
        },
      }),
      /已过期.*拉取最新代码/
    );
  }));

test("tracked Windows source pin selects the exact immutable public Release asset", () => {
  const trackedPin = JSON.parse(fs.readFileSync(
    path.join(__dirname, "..", "resources", "native-core-source-windows.json"),
    "utf8"
  ));
  assert.equal(
    publicReleaseUrl(trackedPin),
    "https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/download/" +
      "windows-source-runtime-20260809-8e355001-71122b5b/" +
      "wechatdataanalysis-windows-source-runtime-x64-v1.tar.gz"
  );
  assert.equal(trackedPin.assetSha256, "aa041a31015ab243179c56343e67c4250011193663d9b2a5497c07771140e315");
  assert.equal(trackedPin.runtimeManifestSha256, "50e35244f9ffb75f03e2dbff69c77bd1f85886b7a9ddb24c3539020646461137");
  assert.equal(trackedPin.expiresAtUnix, 1790145553);
});

test("generic source bootstrap wires the verified Windows directory without macOS-only variables", () =>
  withTempRoot((root) => {
    const tools = fixtureTools();
    const result = ensureSourceNativeCore({
      arch: "x64",
      cacheRoot: path.join(root, "cache"),
      configPath: writeConfig(root),
      env: {},
      nowUnix: NOW_UNIX,
      platform: "win32",
      spawnSyncImpl: tools.spawnSyncImpl,
    });
    const env = {};
    applySourceRuntimeEnvironment(env, result);
    assert.equal(env.WCE_NATIVE_CORE_SOURCE_DIR, result.nativeDir);
    assert.equal("WECHAT_TOOL_MACOS_DB_KEY_BUNDLE" in env, false);
    assert.equal("WCE_INTEGRITY_NATIVE_PATH" in env, false);
  }));

test("direct Electron source launch performs the Windows bootstrap before runtime policy", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "main.cjs"), "utf8");
  const windowsGate = source.indexOf('process.platform === "win32"');
  const bootstrap = source.indexOf("ensureSourceNativeCore({ env })", windowsGate);
  const policy = source.indexOf("applyNativeCoreRuntimePolicy(env", bootstrap);
  assert.ok(windowsGate > 0);
  assert.ok(bootstrap > windowsGate);
  assert.ok(policy > bootstrap);
});
