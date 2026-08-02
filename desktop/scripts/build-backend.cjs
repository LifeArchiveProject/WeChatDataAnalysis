const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..", "..");
const entry = path.join(repoRoot, "src", "wechat_decrypt_tool", "backend_entry.py");

const distDir = path.join(repoRoot, "desktop", "resources", "backend");
const workDir = path.join(repoRoot, "desktop", "build", "pyinstaller");
const specDir = path.join(repoRoot, "desktop", "build", "pyinstaller-spec");
const nativeDir = path.join(repoRoot, "src", "wechat_decrypt_tool", "native");
const runtimeNativeDir = path.join(repoRoot, "desktop", "build", "native-runtime");
const skillDir = path.join(repoRoot, "skills", "wechat-mcp-copilot");
const projectToml = path.join(repoRoot, "pyproject.toml");
const thirdPartyNotices = path.join(repoRoot, "THIRD_PARTY_NOTICES.md");

const NATIVE_CORE_MANIFEST = "wechatdb_native_build.json";
const NATIVE_CORE_ARTIFACTS = Object.freeze({
  win32: ["wechatdb_client.dll", "wechatdb_broker.exe", NATIVE_CORE_MANIFEST],
  darwin: ["libwechatdb_client.dylib", "wechatdb_broker", NATIVE_CORE_MANIFEST],
});
const NATIVE_CORE_FILE_NAMES = new Set(Object.values(NATIVE_CORE_ARTIFACTS).flat());
const LEGACY_WCDB_FILE_NAMES = new Set(["wcdb_api.dll", "WCDB.dll", "libwcdb_api.dylib"]);
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
  if (manifest.schemaVersion !== 2) errors.push("schemaVersion must equal 2");
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
      const name = path.basename(relative);
      return !NATIVE_CORE_FILE_NAMES.has(name) && !LEGACY_WCDB_FILE_NAMES.has(name);
    },
  });
}

function buildIntegrityNativeBinary({ env = process.env, platform = process.platform } = {}) {
  if (platform !== "darwin" && platform !== "linux") return null;

  const integrityManifest = path.join(repoRoot, "native", "wce_integrity", "Cargo.toml");
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
}

function runIntegrityPreflight(env = process.env) {
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
  validateRuntimeNativeHelpers(runtimeNativeDir);
  runIntegrityPreflight();

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

  // Keep native dependencies outside the onefile extraction directory so the
  // broker and client library have stable paths at runtime.
  const packagedNativeDir = path.join(distDir, "native");
  fs.rmSync(packagedNativeDir, { recursive: true, force: true });
  fs.cpSync(runtimeNativeDir, packagedNativeDir, { recursive: true, force: true });
  if (integrityNativeBinary) {
    fs.copyFileSync(integrityNativeBinary, path.join(packagedNativeDir, path.basename(integrityNativeBinary)));
  }

  if (fs.existsSync(projectToml)) {
    try {
      fs.copyFileSync(projectToml, path.join(distDir, "pyproject.toml"));
    } catch {}
  }
  if (fs.existsSync(thirdPartyNotices)) {
    try {
      fs.copyFileSync(thirdPartyNotices, path.join(distDir, "THIRD_PARTY_NOTICES.md"));
    } catch {}
  }
}

module.exports = {
  nativeCoreArtifactNames,
  nativeCoreManifestErrors,
  nativeCoreProductionManifestErrors,
  prepareRuntimeNativeDir,
  resolveNativeCoreArtifacts,
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
