const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  ENV_SOURCE_NATIVE_CORE_DIR,
  ensureSourceNativeCore,
  validateDownloadedSourceArtifact,
} = require("../src/source-native-core-bootstrap.cjs");
const { resolveNativeCoreRuntimeDir } = require("../src/native-core-path.cjs");

const TRACKED_PIN = Object.freeze({
  schemaVersion: 1,
  platform: "darwin",
  architecture: "arm64",
  artifactName: "wechatdb-native-macos-arm64-development",
  producerRepository: "2977094657/WCDB",
  producerWorkflow: ".github/workflows/macos-native-production.yml",
  producerWorkflowRunId: 30889464728,
  producerWorkflowRunAttempt: 1,
  sourceRevision: "d54688b2ea12d6cf25858ff3e41d7f6a1fb98f9f",
  checksumsSha256: "c656a5f5292a9106453fdea55a331c57d5e396d17618454a27dfa13e5cc9aa41",
});
const PIN = Object.freeze({
  ...TRACKED_PIN,
  checksumsSha256: "5f5a8264251735bcb903aa47a3aeaeeec15a31759dd1c1357542c9aa247ee698",
});

const DEVELOPMENT_MANIFEST = Object.freeze({
  schemaVersion: 3,
  platform: "macos",
  distributionMode: "public",
  buildId: "dev-local",
  buildIssuedAtUnix: 0,
  buildExpiresAtUnix: 0,
  developmentBuild: true,
  offlineBootstrapFeatureBits: 0,
  offlineExportSealFormat: "none",
  codeSignatureEnforced: false,
  rootPublicKeyCompiled: false,
  testHooksEnabled: true,
  stagingPinnedSignerTrust: false,
  macosSigningMode: "self-signed",
  macosSignerTrustMode: "development",
  macosPrivatePkiLeafRevocation: "not-applicable",
  macosClientSigningIdentifier: "com.lifearchive.wechatdb.client",
  macosBrokerSigningIdentifier: "com.lifearchive.wechatdb.broker",
  macosHostSigningIdentifier: "com.lifearchive.wechatdataanalysis.backend",
  macosClientSignerSha256: "0".repeat(64),
  macosBrokerSignerSha256: "0".repeat(64),
  macosHostSignerSha256: "0".repeat(64),
  macosPrivateRootSha256: "0".repeat(64),
  securityNoticeId: "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
  securityNoticeSha256: "1".repeat(64),
  securityCheckpointSetId: "WCE-AI-CHECKPOINT-SET-V3",
  securityCheckpointCount: 7,
  securityCheckpointSetSha256: "2".repeat(64),
});

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function writeConfig(root, pin = PIN) {
  const configPath = path.join(root, "pin.json");
  fs.writeFileSync(configPath, `${JSON.stringify(pin, null, 2)}\n`);
  return configPath;
}

function writeCoreTrio(root) {
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(path.join(root, "libwechatdb_client.dylib"), "client");
  fs.writeFileSync(path.join(root, "wechatdb_broker"), "broker");
  fs.writeFileSync(
    path.join(root, "wechatdb_native_build.json"),
    `${JSON.stringify(DEVELOPMENT_MANIFEST, null, 2)}\n`
  );
}

function writeDownloadedArtifact(root, pin = PIN) {
  writeCoreTrio(root);
  const manifestPath = path.join(root, "wechatdb_native_build.json");
  const provenance = {
    architecture: "arm64",
    artifactName: pin.artifactName,
    buildId: "dev-local",
    manifestSha256: sha256(manifestPath),
    platform: "macos",
    producerRepository: pin.producerRepository,
    producerWorkflow: pin.producerWorkflow,
    producerWorkflowRunAttempt: pin.producerWorkflowRunAttempt,
    producerWorkflowRunId: pin.producerWorkflowRunId,
    profile: "source-development",
    schemaVersion: 1,
    sourceRevision: pin.sourceRevision,
  };
  fs.writeFileSync(
    path.join(root, "source_provenance.json"),
    `${JSON.stringify(provenance, null, 2)}\n`
  );
  const checksumNames = [
    "libwechatdb_client.dylib",
    "source_provenance.json",
    "wechatdb_broker",
    "wechatdb_native_build.json",
  ];
  fs.writeFileSync(
    path.join(root, "SHA256SUMS.txt"),
    `${checksumNames.map((name) => `${sha256(path.join(root, name))}  ${name}`).join("\n")}\n`
  );
}

function withTempRoot(callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-source-native-"));
  try {
    return callback(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("tracked macOS source pin selects the exact authenticated Producer artifact", () => {
  const tracked = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "..", "resources", "native-core-source-macos.json"),
      "utf8"
    )
  );
  assert.deepEqual(tracked, TRACKED_PIN);
});

test("macOS source bootstrap downloads once, validates, and reuses the verified cache", () =>
  withTempRoot((root) => {
    const configPath = writeConfig(root);
    const cacheRoot = path.join(root, "cache");
    let downloads = 0;
    const spawnSyncImpl = (command, args, options) => {
      downloads += 1;
      assert.equal(command, "gh");
      assert.equal(options.shell, false);
      assert.deepEqual(args.slice(0, 3), ["run", "download", String(PIN.producerWorkflowRunId)]);
      const destination = args[args.indexOf("--dir") + 1];
      writeDownloadedArtifact(destination);
      return { status: 0, stdout: "", stderr: "" };
    };

    const first = ensureSourceNativeCore({
      arch: "arm64",
      cacheRoot,
      configPath,
      env: {},
      platform: "darwin",
      spawnSyncImpl,
    });
    assert.equal(first.reason, "downloaded");
    assert.equal(downloads, 1);
    validateDownloadedSourceArtifact(first.nativeDir, PIN);

    const second = ensureSourceNativeCore({
      arch: "arm64",
      cacheRoot,
      configPath,
      env: {},
      platform: "darwin",
      spawnSyncImpl() {
        throw new Error("cache hit must not invoke gh");
      },
    });
    assert.equal(second.reason, "verified-cache");
    assert.equal(second.nativeDir, first.nativeDir);
  }));

test("tampered cached source artifact is replaced from the pinned Producer run", () =>
  withTempRoot((root) => {
    const configPath = writeConfig(root);
    const cacheRoot = path.join(root, "cache");
    const first = ensureSourceNativeCore({
      arch: "arm64",
      cacheRoot,
      configPath,
      env: {},
      platform: "darwin",
      spawnSyncImpl(command, args) {
        writeDownloadedArtifact(args[args.indexOf("--dir") + 1]);
        return { status: 0, stdout: "", stderr: "" };
      },
    });
    fs.writeFileSync(path.join(first.nativeDir, "wechatdb_broker"), "tampered");
    let repaired = 0;
    const second = ensureSourceNativeCore({
      arch: "arm64",
      cacheRoot,
      configPath,
      env: {},
      platform: "darwin",
      spawnSyncImpl(command, args) {
        repaired += 1;
        writeDownloadedArtifact(args[args.indexOf("--dir") + 1]);
        return { status: 0, stdout: "", stderr: "" };
      },
    });
    assert.equal(repaired, 1);
    assert.equal(second.reason, "downloaded");
    validateDownloadedSourceArtifact(second.nativeDir, PIN);
  }));

test("source artifact rejects checksum, provenance, and file allowlist substitutions", () =>
  withTempRoot((root) => {
    writeDownloadedArtifact(root);
    fs.writeFileSync(path.join(root, "libwechatdb_client.dylib"), "tampered");
    assert.throws(() => validateDownloadedSourceArtifact(root, PIN), /SHA256SUMS/);
  }));

test("explicit developer core directory remains usable without GitHub access", () =>
  withTempRoot((root) => {
    const nativeDir = path.join(root, "manual");
    writeCoreTrio(nativeDir);
    const result = ensureSourceNativeCore({
      arch: "arm64",
      configPath: path.join(root, "missing.json"),
      env: { [ENV_SOURCE_NATIVE_CORE_DIR]: nativeDir },
      platform: "darwin",
      spawnSyncImpl() {
        throw new Error("explicit core must not invoke gh");
      },
    });
    assert.equal(result.reason, "explicit-directory");
    assert.equal(result.nativeDir, path.resolve(nativeDir));
  }));

test("source bootstrap fails before child processes with actionable private-repository guidance", () =>
  withTempRoot((root) => {
    const configPath = writeConfig(root);
    const cacheRoot = path.join(root, "cache");
    assert.throws(
      () =>
        ensureSourceNativeCore({
          arch: "arm64",
          cacheRoot,
          configPath,
          env: {},
          platform: "darwin",
          spawnSyncImpl() {
            return { status: 1, stdout: "", stderr: "HTTP 404" };
          },
        }),
      /gh auth login.*2977094657\/WCDB/s
    );
    assert.deepEqual(fs.existsSync(cacheRoot) ? fs.readdirSync(cacheRoot) : [], []);
  }));

test("runtime directory honors a source-only override and packaged apps ignore it", () => {
  const env = { [ENV_SOURCE_NATIVE_CORE_DIR]: "/tmp/private-native" };
  assert.equal(
    resolveNativeCoreRuntimeDir({
      env,
      isPackaged: false,
      repoRoot: "/repo",
      resourcesPath: "/app/resources",
    }),
    path.resolve("/tmp/private-native")
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

test("development launcher finishes native preflight before spawning the frontend", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "scripts", "dev.cjs"), "utf8");
  const preflight = source.indexOf("ensureSourceNativeCore(");
  const frontendSpawn = source.indexOf("const frontend = spawnLogged(");
  assert.ok(preflight >= 0);
  assert.ok(frontendSpawn > preflight);
  assert.match(source, /sharedEnv\[ENV_SOURCE_NATIVE_CORE_DIR\] = sourceNativeCore\.nativeDir/);
});

test("verified artifact restores executable modes normalized by GitHub artifacts", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "source-native-core-bootstrap.cjs"),
    "utf8"
  );
  assert.match(source, /chmodSync\(path\.join\(directory, "wechatdb_broker"\), 0o755\)/);
  assert.match(
    source,
    /validateDownloadedSourceArtifact\(nativeDir, pin\);\s+ensureRuntimePermissions\(nativeDir\);/
  );
});
