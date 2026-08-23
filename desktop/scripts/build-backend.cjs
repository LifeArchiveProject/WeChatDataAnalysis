const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const {
  contract: MACOS_XKEY_CONTRACT,
  stageMacosXkeyArtifacts,
} = require("./macos-xkey-packaging.cjs");
const {
  macosNativeManifestErrors,
  resolveMacosNativeCoreArtifacts,
} = require("./macos-native-core-packaging.cjs");
const {
  resolveIntegrityNativeArtifact,
} = require("./integrity-native-packaging.cjs");
const {
  assertWindowsNativeAsrCapability,
  windowsNativeAsrManifestErrors,
} = require("../src/windows-native-asr-capability.cjs");

const repoRoot = path.resolve(__dirname, "..", "..");
const entry = path.join(repoRoot, "src", "wechat_decrypt_tool", "backend_entry.py");

const distDir = path.join(repoRoot, "desktop", "resources", "backend");
const workDir = path.join(repoRoot, "desktop", "build", "pyinstaller");
const specDir = path.join(repoRoot, "desktop", "build", "pyinstaller-spec");
const nativeDir = path.join(repoRoot, "src", "wechat_decrypt_tool", "native");
const runtimeNativeDir = path.join(repoRoot, "desktop", "build", "native-runtime");
const skillDir = path.join(repoRoot, "skills", "wechat-mcp-copilot");
const macosXkeyContractPath = path.join(
  repoRoot,
  "src",
  "wechat_decrypt_tool",
  "resources",
  "macos_db_key_contract.json"
);

const NATIVE_CORE_MANIFEST = "wechatdb_native_build.json";
const NATIVE_CORE_ARTIFACTS = Object.freeze({
  win32: ["wechatdb_client.dll", "wechatdb_broker.exe", NATIVE_CORE_MANIFEST],
  darwin: ["libwechatdb_client.dylib", "wechatdb_broker", NATIVE_CORE_MANIFEST],
});
const NATIVE_CORE_FILE_NAMES = new Set(Object.values(NATIVE_CORE_ARTIFACTS).flat());
const LEGACY_WCDB_FILE_NAMES = new Set([
  "wcdb_api.dll",
  "WCDB.dll",
  "libwcdb_api.dylib",
  "libWCDB.dylib",
]);
const RETIRED_STANDALONE_ASR_FILE_NAMES = new Set([
  "wechat_native_asr_manifest.json",
  "wechat_native_asr_python_transport.py",
  "wechat_native_asr_weixin_hook.dll",
]);
const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["", "0", "false", "no", "off"]);
const NON_PRODUCTION_BUILD_ID_PATTERN =
  /(^|[._-])(dev|debug|test|local|snapshot|staging)([._-]|$)/i;
const SHA256_HEX_PATTERN = /^[0-9A-Fa-f]{64}$/;
const LOWERCASE_SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/;
const NATIVE_CORE_BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const NATIVE_CORE_SECURITY_NOTICE_ID = "WCE-AUTOMATED-ANALYSIS-NOTICE-V2";
const NATIVE_CORE_SECURITY_CHECKPOINT_SET_ID = "WCE-AI-CHECKPOINT-SET-V3";
const NATIVE_CORE_SECURITY_CHECKPOINT_COUNT = 7;

function isNonZeroSha256(value) {
  const text = String(value || "");
  return SHA256_HEX_PATTERN.test(text) && !/^0{64}$/.test(text);
}

function parseBooleanEnv(env, name) {
  const value = String(env[name] || "").trim().toLowerCase();
  if (TRUE_VALUES.has(value)) return true;
  if (FALSE_VALUES.has(value)) return false;
  throw new Error(`${name} must be a boolean value, received: ${env[name]}`);
}

function nativeCoreArtifactNames(platform = process.platform) {
  return [...(NATIVE_CORE_ARTIFACTS[platform] || [])];
}

function isCiEnvironment(env) {
  const value = String(env.CI || "").trim().toLowerCase();
  return value !== "" && !FALSE_VALUES.has(value);
}

function nativeCoreManifestErrors(manifest) {
  const errors = [];
  if (!manifest || Array.isArray(manifest) || typeof manifest !== "object") {
    return ["manifest must be a JSON object"];
  }
  if (!new Set([2, 3]).has(manifest.schemaVersion)) {
    errors.push("schemaVersion must equal 2 or 3");
  }
  if (manifest.schemaVersion === 3 && manifest.platform !== "macos") {
    errors.push("schemaVersion 3 requires platform macos");
  }
  if (manifest.schemaVersion === 2 && Object.prototype.hasOwnProperty.call(manifest, "platform")) {
    errors.push("schemaVersion 2 must not declare platform");
  }
  if (manifest.schemaVersion === 2) {
    errors.push(...windowsNativeAsrManifestErrors(manifest));
  }
  if (typeof manifest.buildId !== "string" || manifest.buildId.trim() === "") {
    errors.push("buildId must be a non-empty string");
  }
  if (manifest.securityNoticeId !== NATIVE_CORE_SECURITY_NOTICE_ID) {
    errors.push(`securityNoticeId must equal ${NATIVE_CORE_SECURITY_NOTICE_ID}`);
  }
  if (!LOWERCASE_SHA256_HEX_PATTERN.test(String(manifest.securityNoticeSha256 || ""))) {
    errors.push("securityNoticeSha256 must be a lowercase SHA-256 digest");
  }
  if (manifest.securityCheckpointSetId !== NATIVE_CORE_SECURITY_CHECKPOINT_SET_ID) {
    errors.push(
      `securityCheckpointSetId must equal ${NATIVE_CORE_SECURITY_CHECKPOINT_SET_ID}`
    );
  }
  if (manifest.securityCheckpointCount !== NATIVE_CORE_SECURITY_CHECKPOINT_COUNT) {
    errors.push(
      `securityCheckpointCount must equal ${NATIVE_CORE_SECURITY_CHECKPOINT_COUNT}`
    );
  }
  if (
    !LOWERCASE_SHA256_HEX_PATTERN.test(
      String(manifest.securityCheckpointSetSha256 || "")
    )
  ) {
    errors.push("securityCheckpointSetSha256 must be a lowercase SHA-256 digest");
  }
  return errors;
}

function nativeCoreProductionManifestErrors(
  manifest,
  { nowUnix = Math.floor(Date.now() / 1000) } = {}
) {
  if (manifest?.schemaVersion === 3) {
    return macosNativeManifestErrors(manifest, { nowUnix });
  }
  const errors = nativeCoreManifestErrors(manifest);
  const buildIssuedAtUnix = manifest?.buildIssuedAtUnix;
  const buildExpiresAtUnix = manifest?.buildExpiresAtUnix;
  const validBuildWindow =
    Number.isSafeInteger(buildIssuedAtUnix) &&
    buildIssuedAtUnix > 0 &&
    Number.isSafeInteger(buildExpiresAtUnix) &&
    buildExpiresAtUnix === buildIssuedAtUnix + NATIVE_CORE_BUILD_LIFETIME_SECONDS;
  if (!validBuildWindow) {
    errors.push("build validity window must equal exactly 45 days");
  } else if (!Number.isSafeInteger(nowUnix) || nowUnix < 0) {
    errors.push("current Unix time must be a non-negative integer");
  } else if (nowUnix >= buildExpiresAtUnix) {
    errors.push("build has reached its fixed expiration time");
  }
  if (manifest?.distributionMode !== "public") {
    errors.push("distributionMode must equal public");
  }
  if (Object.prototype.hasOwnProperty.call(manifest || {}, "distributionCapsule")) {
    errors.push("distributionCapsule must be absent");
  }
  if (manifest?.developmentBuild !== false) errors.push("developmentBuild must be false");
  if (manifest?.offlineBootstrapFeatureBits !== 3) {
    errors.push("offlineBootstrapFeatureBits must equal 3");
  }
  if (manifest?.offlineExportSealFormat !== "WES2") {
    errors.push("offlineExportSealFormat must equal WES2");
  }
  if (manifest?.codeSignatureEnforced !== true) errors.push("codeSignatureEnforced must be true");
  if (manifest?.rootPublicKeyCompiled !== true) errors.push("rootPublicKeyCompiled must be true");
  if (manifest?.testHooksEnabled !== false) errors.push("testHooksEnabled must be false");
  if (manifest?.stagingPinnedSignerTrust !== false) {
    errors.push("stagingPinnedSignerTrust must be false");
  }
  if (!isNonZeroSha256(manifest?.windowsClientSignerSha256)) {
    errors.push("windowsClientSignerSha256 must be a non-zero SHA-256 digest");
  }
  if (!isNonZeroSha256(manifest?.windowsBrokerSignerSha256)) {
    errors.push("windowsBrokerSignerSha256 must be a non-zero SHA-256 digest");
  }
  if (
    isNonZeroSha256(manifest?.windowsClientSignerSha256) &&
    String(manifest.windowsClientSignerSha256).toUpperCase() ===
      String(manifest.windowsBrokerSignerSha256 || "").toUpperCase()
  ) {
    errors.push("Windows client and broker signer pins must be distinct");
  }
  if (!new Set(["public", "private-pki"]).has(manifest?.windowsSignerTrustMode)) {
    errors.push("windowsSignerTrustMode must be public or private-pki");
  }
  const expectedLeafRevocation =
    manifest?.windowsSignerTrustMode === "private-pki"
      ? "build-and-lease-only"
      : "not-applicable";
  if (manifest?.windowsPrivatePkiLeafRevocation !== expectedLeafRevocation) {
    errors.push("windowsPrivatePkiLeafRevocation must match signer trust mode");
  }
  if (
    manifest?.windowsSignerTrustMode === "private-pki" &&
    !isNonZeroSha256(manifest?.windowsPrivateRootSha256)
  ) {
    errors.push("private-pki requires windowsPrivateRootSha256");
  }
  if (
    manifest?.windowsSignerTrustMode === "public" &&
    !new Set(["", "0".repeat(64)]).has(String(manifest?.windowsPrivateRootSha256 || ""))
  ) {
    errors.push("public signer trust must not declare windowsPrivateRootSha256");
  }
  if (NON_PRODUCTION_BUILD_ID_PATTERN.test(String(manifest?.buildId || "").trim())) {
    errors.push("buildId must not contain a development or staging label");
  }
  return errors;
}

function readNativeCoreManifest(artifactDir) {
  const manifestPath = path.join(artifactDir, NATIVE_CORE_MANIFEST);
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    throw new Error(`Invalid wechatdb native build manifest at ${manifestPath}: ${error.message}`);
  }
  const errors = nativeCoreManifestErrors(manifest);
  if (errors.length > 0) {
    throw new Error(`Invalid wechatdb native build manifest: ${errors.join("; ")}`);
  }
  return manifest;
}

function resolveNativeCoreArtifacts({ env = process.env, platform = process.platform } = {}) {
  const names = nativeCoreArtifactNames(platform);
  const explicitValue = String(env.WCE_NATIVE_CORE_ARTIFACT_DIR || "").trim();
  const explicitlyRequired =
    parseBooleanEnv(env, "WCE_NATIVE_CORE_REQUIRED") ||
    String(env.WECHAT_TOOL_NATIVE_CORE_MODE || "").trim().toLowerCase() === "required";
  const required = names.length > 0 || explicitlyRequired;
  const allowDevelopment = parseBooleanEnv(env, "WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS");

  if (names.length === 0) {
    if (explicitValue || required || allowDevelopment) {
      throw new Error(`wechatdb native core packaging is unsupported on platform: ${platform}`);
    }
    return { artifactDir: null, allowDevelopment: false, manifest: null, names, required };
  }

  if (allowDevelopment && !explicitValue) {
    throw new Error(
      "WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS requires an explicit WCE_NATIVE_CORE_ARTIFACT_DIR"
    );
  }
  if (allowDevelopment && isCiEnvironment(env)) {
    throw new Error("WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS is a local-only override and is forbidden in CI");
  }

  if (!explicitValue) {
    throw new Error(
      "Missing WCE_NATIVE_CORE_ARTIFACT_DIR. Expected a directory containing: " + names.join(", ")
    );
  }

  if (platform === "darwin" && !allowDevelopment) {
    const resolved = resolveMacosNativeCoreArtifacts({ env, platform });
    return { ...resolved, allowDevelopment: false, required: true };
  }

  const artifactDir = path.resolve(explicitValue);
  let directoryStat;
  try {
    directoryStat = fs.statSync(artifactDir);
  } catch (error) {
    throw new Error(`WCE_NATIVE_CORE_ARTIFACT_DIR is not readable: ${artifactDir}`);
  }
  if (!directoryStat.isDirectory()) {
    throw new Error(`WCE_NATIVE_CORE_ARTIFACT_DIR is not a directory: ${artifactDir}`);
  }

  const missing = [];
  for (const name of names) {
    const artifactPath = path.join(artifactDir, name);
    try {
      if (!fs.statSync(artifactPath).isFile()) missing.push(name);
    } catch {
      missing.push(name);
    }
  }
  if (missing.length > 0) {
    throw new Error(
      `Incomplete WCE_NATIVE_CORE_ARTIFACT_DIR (${artifactDir}). Missing files: ${missing.join(", ")}. ` +
      `Expected: ${names.join(", ")}`
    );
  }

  const manifest = readNativeCoreManifest(artifactDir);
  const productionErrors = nativeCoreProductionManifestErrors(manifest);
  if (productionErrors.length > 0 && !allowDevelopment) {
    throw new Error(
      "Refusing to stage a non-production wechatdb native core: " +
      productionErrors.join("; ") +
      ". Local development requires both WCE_NATIVE_CORE_ARTIFACT_DIR and " +
      "WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS=1."
    );
  }

  if (platform === "win32") {
    assertWindowsNativeAsrCapability({ nativeDir: artifactDir, manifest });
  }

  return { artifactDir, allowDevelopment, manifest, names, required };
}

function prepareRuntimeNativeDir(sourceDir, destinationDir) {
  fs.rmSync(destinationDir, { recursive: true, force: true });
  fs.mkdirSync(destinationDir, { recursive: true });
  fs.cpSync(sourceDir, destinationDir, {
    recursive: true,
    force: true,
    filter(sourcePath) {
      const relative = path.relative(sourceDir, sourcePath);
      if (!relative) return true;
      const normalizedRelative = relative.split(path.sep).join("/");
      if (normalizedRelative === "macos/db-key" || normalizedRelative.startsWith("macos/db-key/")) {
        return false;
      }
      const name = path.basename(relative);
      const pathSegments = normalizedRelative.split("/");
      if (pathSegments.includes("__pycache__") || name.endsWith(".pyc")) {
        return false;
      }
      if (
        name.startsWith("wechat_native_asr_python_transport.") ||
        name.startsWith("win32_native_voice_bridge.")
      ) {
        return false;
      }
      return !NATIVE_CORE_FILE_NAMES.has(name) &&
        !LEGACY_WCDB_FILE_NAMES.has(name) &&
        !RETIRED_STANDALONE_ASR_FILE_NAMES.has(name);
    },
  });
}

function buildIntegrityNativeBinary({ env = process.env, platform = process.platform } = {}) {
  if (platform !== "darwin" && platform !== "linux") return null;

  const artifactDir = String(env.WCE_INTEGRITY_ARTIFACT_DIR || "").trim();
  if (platform === "darwin" && artifactDir) {
    return resolveIntegrityNativeArtifact({ env, platform }).binaryPath;
  }
  const distributionRequired = platform === "darwin" && (
    parseBooleanEnv(env, "WCE_INTEGRITY_REQUIRED") ||
    String(env.MACOS_DISTRIBUTION_BUILD || "").trim() === "1"
  );
  if (distributionRequired) {
    throw new Error("A pinned macOS wce_integrity production artifact is required.");
  }

  const integrityManifest = path.join(repoRoot, "native", "wce_integrity", "Cargo.toml");
  if (!fs.existsSync(integrityManifest)) {
    throw new Error(
      "Private wce_integrity source is unavailable. Configure WCE_INTEGRITY_ARTIFACT_DIR for macOS packaging."
    );
  }
  const integrityTargetDir = path.join(repoRoot, "native", "wce_integrity", "target", "release");
  const fileName = platform === "darwin" ? "libwce_integrity.dylib" : "libwce_integrity.so";
  const result = spawnSync(
    "cargo",
    ["build", "--manifest-path", integrityManifest, "--release"],
    {
      cwd: repoRoot,
      env: {
        ...env,
        WCE_UI_PUBLIC_DIR: path.join(repoRoot, "frontend", ".output", "public"),
      },
      stdio: "inherit",
    }
  );
  if ((result.status ?? 1) !== 0) {
    throw new Error(`Failed to build the wce_integrity module for ${platform}.`);
  }

  const binary = path.join(integrityTargetDir, fileName);
  if (!fs.existsSync(binary)) {
    throw new Error(`wce_integrity build completed without expected artifact: ${binary}`);
  }
  return binary;
}

function validateRuntimeNativeHelpers(destinationDir, platform = process.platform) {
  if (platform !== "darwin") return;
  const imageScanHelper = path.join(destinationDir, "macos", "universal", "image_scan_helper");
  if (!fs.existsSync(imageScanHelper)) {
    throw new Error(`Missing macOS image scan helper: ${imageScanHelper}`);
  }
  fs.chmodSync(imageScanHelper, 0o755);
  const databaseKeyHelper = path.join(
    destinationDir,
    ...String(MACOS_XKEY_CONTRACT.bundleRelativePath).split("/"),
    MACOS_XKEY_CONTRACT.helperFileName
  );
  if (!fs.existsSync(databaseKeyHelper)) {
    throw new Error(`Missing controlled macOS database key helper: ${databaseKeyHelper}`);
  }
  fs.chmodSync(databaseKeyHelper, 0o755);
}

function runIntegrityPreflight(env = process.env, integrityNativeBinary = null) {
  const result = spawnSync(
    "uv",
    [
      "run",
      "python",
      "-c",
      [
        "from wechat_decrypt_tool.export_integrity import load_wce_integrity_native",
        "w=load_wce_integrity_native()",
        "required=('chat','sns','records-project','records-generic','contacts')",
        "assert all(w.export_css(kind).strip() for kind in required)",
        "assert callable(w.record_file) and callable(w.seal_export)",
      ].join(";"),
    ],
    {
      cwd: repoRoot,
      env: {
        ...env,
        ...(integrityNativeBinary
          ? { WCE_INTEGRITY_NATIVE_PATH: path.resolve(integrityNativeBinary) }
          : {}),
        PYTHONPATH: [path.join(repoRoot, "src"), env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
      },
      stdio: "inherit",
    }
  );
  if ((result.status ?? 1) !== 0) {
    throw new Error(
      "wce_integrity runtime is missing or stale. Rebuild or restore the platform implementation before packaging."
    );
  }
}

function runPackagedOpenccSmoke(packagedBackend, env = process.env) {
  const smokeDir = fs.mkdtempSync(path.join(os.tmpdir(), "wda-opencc-smoke-"));
  try {
    const smokeEnv = { ...env, PYTHONPATH: "" };
    delete smokeEnv.PYTHONHOME;
    const smoke = spawnSync(packagedBackend, ["--smoke-opencc"], {
      cwd: smokeDir,
      env: smokeEnv,
      encoding: "utf8",
      windowsHide: true,
    });
    if ((smoke.status ?? 1) !== 0) {
      throw new Error(smoke.stderr || smoke.stdout || "Packaged OpenCC smoke test failed.");
    }
    const outputLines = String(smoke.stdout || "").trim().split(/\r?\n/).filter(Boolean);
    let payload;
    try {
      payload = JSON.parse(outputLines.at(-1) || "");
    } catch {
      throw new Error(`Packaged OpenCC smoke test returned invalid JSON: ${smoke.stdout || "<empty>"}`);
    }
    const expected = {
      "繁體中文": "繁体中文",
      "軟體與資料庫": "软体与资料库",
    };
    if (!payload.frozen || JSON.stringify(payload.results) !== JSON.stringify(expected)) {
      throw new Error(`Packaged OpenCC smoke test returned an unexpected result: ${JSON.stringify(payload)}`);
    }
    console.log(`Packaged OpenCC smoke test passed: ${JSON.stringify(payload)}`);
  } finally {
    fs.rmSync(smokeDir, { recursive: true, force: true });
  }
}

function runPackagedWatchfilesSmoke(packagedBackend, env = process.env) {
  const smokeDir = fs.mkdtempSync(path.join(os.tmpdir(), "wda-watchfiles-smoke-"));
  try {
    const smokeEnv = { ...env, PYTHONPATH: "" };
    delete smokeEnv.PYTHONHOME;
    const smoke = spawnSync(packagedBackend, ["--smoke-watchfiles"], {
      cwd: smokeDir,
      env: smokeEnv,
      encoding: "utf8",
      windowsHide: true,
    });
    if ((smoke.status ?? 1) !== 0) {
      throw new Error(smoke.stderr || smoke.stdout || "Packaged watchfiles smoke test failed.");
    }
    const outputLines = String(smoke.stdout || "").trim().split(/\r?\n/).filter(Boolean);
    let payload;
    try {
      payload = JSON.parse(outputLines.at(-1) || "");
    } catch {
      throw new Error(`Packaged watchfiles smoke test returned invalid JSON: ${smoke.stdout || "<empty>"}`);
    }
    if (!payload.frozen || !payload.version || !payload.nativeModule) {
      throw new Error(
        `Packaged watchfiles smoke test returned an unexpected result: ${JSON.stringify(payload)}`
      );
    }
    console.log(`Packaged watchfiles smoke test passed: ${JSON.stringify(payload)}`);
  } finally {
    fs.rmSync(smokeDir, { recursive: true, force: true });
  }
}

function stageNativeCoreArtifacts({
  env = process.env,
  platform = process.platform,
  destinationDir = runtimeNativeDir,
  logger = console,
} = {}) {
  const resolved = resolveNativeCoreArtifacts({ env, platform });
  if (!resolved.artifactDir) {
    logger.warn("wechatdb native core packaging is unavailable on this platform.");
    return { ...resolved, staged: false };
  }

  fs.mkdirSync(destinationDir, { recursive: true });
  for (const name of resolved.names) {
    const destination = path.join(destinationDir, name);
    fs.copyFileSync(path.join(resolved.artifactDir, name), destination);
    if (platform === "darwin" && name === "wechatdb_broker") {
      fs.chmodSync(destination, 0o755);
    }
  }

  if (resolved.allowDevelopment) {
    logger.warn("Staged local development wechatdb native core artifacts; do not publish this package.");
  } else {
    logger.log(`Staged production wechatdb native core build: ${resolved.manifest.buildId}`);
  }
  return { ...resolved, staged: true };
}

function parseVersionTuple(rawVersion) {
  const nums = String(rawVersion || "")
    .split(/[^\d]+/)
    .map((x) => Number.parseInt(x, 10))
    .filter((n) => Number.isInteger(n) && n >= 0);
  while (nums.length < 4) nums.push(0);
  return nums.slice(0, 4);
}

function buildVersionInfoText(versionTuple, versionDot) {
  const [a, b, c, d] = versionTuple;
  return `# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(${a}, ${b}, ${c}, ${d}),
    prodvers=(${a}, ${b}, ${c}, ${d}),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [StringStruct('CompanyName', 'LifeArchiveProject'),
        StringStruct('FileDescription', 'WeChatDataAnalysis Backend'),
        StringStruct('FileVersion', '${versionDot}'),
        StringStruct('InternalName', 'wechat-backend'),
        StringStruct('LegalCopyright', 'LifeArchiveProject'),
        StringStruct('OriginalFilename', 'wechat-backend.exe'),
        StringStruct('ProductName', 'WeChatDataAnalysis'),
        StringStruct('ProductVersion', '${versionDot}')])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
`;
}

function pyInstallerAddData(sourcePath, targetPath) {
  return `${sourcePath}${path.delimiter}${targetPath}`;
}

function main() {
  fs.mkdirSync(distDir, { recursive: true });
  fs.mkdirSync(workDir, { recursive: true });
  fs.mkdirSync(specDir, { recursive: true });

  const integrityNativeBinary = buildIntegrityNativeBinary();
  prepareRuntimeNativeDir(nativeDir, runtimeNativeDir);
  stageNativeCoreArtifacts();
  stageMacosXkeyArtifacts({ destinationNativeDir: runtimeNativeDir });
  validateRuntimeNativeHelpers(runtimeNativeDir);
  runIntegrityPreflight(process.env, integrityNativeBinary);

  const desktopPackageJsonPath = path.join(repoRoot, "desktop", "package.json");
  let desktopVersion = "1.3.0";
  try {
    const pkg = JSON.parse(fs.readFileSync(desktopPackageJsonPath, { encoding: "utf8" }));
    const v = String(pkg?.version || "").trim();
    if (v) desktopVersion = v;
  } catch {}
  const versionTuple = parseVersionTuple(desktopVersion);
  const versionDot = versionTuple.join(".");
  const versionFilePath = path.join(workDir, "wechat-data-analysis-version.txt");
  if (process.platform === "win32") {
    fs.writeFileSync(versionFilePath, buildVersionInfoText(versionTuple, versionDot), { encoding: "utf8" });
  }

  const args = [
    "run",
    "pyinstaller",
    "--noconfirm",
    "--clean",
    "--name",
    "wechat-backend",
    "--onefile",
    "--distpath",
    distDir,
    "--workpath",
    workDir,
    "--specpath",
    specDir,
    "--add-data",
    pyInstallerAddData(runtimeNativeDir, "wechat_decrypt_tool/native"),
    "--add-data",
    pyInstallerAddData(skillDir, "skills/wechat-mcp-copilot"),
    "--add-data",
    pyInstallerAddData(macosXkeyContractPath, "wechat_decrypt_tool/resources"),
    "--collect-all",
    "faster_whisper",
    "--collect-all",
    "ctranslate2",
    "--collect-all",
    "av",
    "--collect-all",
    "opencc",
    "--collect-all",
    "watchfiles",
    entry,
  ];

  if (process.platform === "win32") {
    args.splice(
      args.length - 1,
      0,
      "--version-file",
      versionFilePath,
      "--hidden-import",
      "wechat_decrypt_tool.key_v4",
      "--hidden-import",
      "yara"
    );
  }
  if (integrityNativeBinary) {
    args.splice(
      args.length - 1,
      0,
      "--add-binary",
      pyInstallerAddData(integrityNativeBinary, "wechat_decrypt_tool/native")
    );
  }

  const result = spawnSync("uv", args, { cwd: repoRoot, stdio: "inherit" });
  if ((result.status ?? 1) !== 0) {
    process.exit(result.status ?? 1);
  }

  const packagedBackend = path.join(
    distDir,
    process.platform === "win32" ? "wechat-backend.exe" : "wechat-backend"
  );
  runPackagedOpenccSmoke(packagedBackend);
  runPackagedWatchfilesSmoke(packagedBackend);

  // Keep native dependencies outside the onefile extraction directory so the
  // broker and client library have stable paths at runtime.
  const packagedNativeDir = path.join(distDir, "native");
  fs.rmSync(packagedNativeDir, { recursive: true, force: true });
  fs.cpSync(runtimeNativeDir, packagedNativeDir, { recursive: true, force: true });
  if (integrityNativeBinary) {
    fs.copyFileSync(integrityNativeBinary, path.join(packagedNativeDir, path.basename(integrityNativeBinary)));
  }

  // Historical builds shipped pyproject.toml as a "project root" marker, which let
  // the packaged backend write `.env` into the signed .app bundle and break macOS
  // codesign verification on relaunch. Drop stale copies from incremental dists.
  fs.rmSync(path.join(distDir, "pyproject.toml"), { force: true });
}

module.exports = {
  nativeCoreArtifactNames,
  nativeCoreManifestErrors,
  nativeCoreProductionManifestErrors,
  buildIntegrityNativeBinary,
  prepareRuntimeNativeDir,
  resolveNativeCoreArtifacts,
  runPackagedOpenccSmoke,
  runPackagedWatchfilesSmoke,
  stageNativeCoreArtifacts,
};

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error?.message || error);
    process.exit(1);
  }
}
