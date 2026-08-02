const fs = require("fs");
const path = require("path");

const ENV_NATIVE_CORE_MODE = "WECHAT_TOOL_NATIVE_CORE_MODE";
const ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD =
  "WECHAT_TOOL_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD";
const NATIVE_CORE_MANIFEST = "wechatdb_native_build.json";
const BUILD_ID_PATTERN = /^[A-Za-z0-9._-]+$/;
const NON_PRODUCTION_BUILD_ID_PATTERN =
  /(^|[._-])(dev|debug|test|local|snapshot|staging)([._-]|$)/i;
const SHA256_HEX_PATTERN = /^[0-9A-Fa-f]{64}$/;
const LOWERCASE_SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/;
const NATIVE_CORE_BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60;
const NATIVE_CORE_MODES = new Set(["required"]);
const NATIVE_CORE_SECURITY_NOTICE_ID = "WCE-AUTOMATED-ANALYSIS-NOTICE-V2";
const NATIVE_CORE_SECURITY_CHECKPOINT_SET_ID = "WCE-AI-CHECKPOINT-SET-V3";
const NATIVE_CORE_SECURITY_CHECKPOINT_COUNT = 7;

function isNonZeroSha256(value) {
  const text = String(value || "");
  return SHA256_HEX_PATTERN.test(text) && !/^0{64}$/.test(text);
}

function nativeCoreArtifactNames(platform = process.platform) {
  if (platform === "win32") {
    return ["wechatdb_client.dll", "wechatdb_broker.exe", NATIVE_CORE_MANIFEST];
  }
  if (platform === "darwin") {
    return ["libwechatdb_client.dylib", "wechatdb_broker", NATIVE_CORE_MANIFEST];
  }
  return [];
}

function readNativeCoreManifest(nativeDir, fsImpl = fs) {
  const manifestPath = path.join(nativeDir, NATIVE_CORE_MANIFEST);
  try {
    const stat = fsImpl.statSync(manifestPath);
    if (!stat.isFile() || stat.size <= 0 || stat.size > 16 * 1024) return null;
    const value = JSON.parse(fsImpl.readFileSync(manifestPath, "utf8"));
    return value && !Array.isArray(value) && typeof value === "object" ? value : null;
  } catch {
    return null;
  }
}

function hasCompleteNativeCore(nativeDir, platform = process.platform, fsImpl = fs) {
  const names = nativeCoreArtifactNames(platform);
  if (names.length === 0) return false;
  return names.every((name) => {
    try {
      return fsImpl.statSync(path.join(nativeDir, name)).isFile();
    } catch {
      return false;
    }
  });
}

function hasValidManifestIdentity(manifest) {
  return (
    manifest?.schemaVersion === 2 &&
    typeof manifest?.buildId === "string" &&
    BUILD_ID_PATTERN.test(manifest.buildId)
  );
}

function hasActiveProductionBuildWindow(
  manifest,
  { nowUnix = Math.floor(Date.now() / 1000) } = {}
) {
  const buildIssuedAtUnix = manifest?.buildIssuedAtUnix;
  const buildExpiresAtUnix = manifest?.buildExpiresAtUnix;
  return (
    Number.isSafeInteger(nowUnix) &&
    nowUnix >= 0 &&
    Number.isSafeInteger(buildIssuedAtUnix) &&
    buildIssuedAtUnix > 0 &&
    Number.isSafeInteger(buildExpiresAtUnix) &&
    buildExpiresAtUnix === buildIssuedAtUnix + NATIVE_CORE_BUILD_LIFETIME_SECONDS &&
    nowUnix < buildExpiresAtUnix
  );
}

function hasCurrentSecurityContract(manifest) {
  return (
    manifest?.securityNoticeId === NATIVE_CORE_SECURITY_NOTICE_ID &&
    LOWERCASE_SHA256_HEX_PATTERN.test(String(manifest.securityNoticeSha256 || "")) &&
    manifest.securityCheckpointSetId === NATIVE_CORE_SECURITY_CHECKPOINT_SET_ID &&
    manifest.securityCheckpointCount === NATIVE_CORE_SECURITY_CHECKPOINT_COUNT &&
    LOWERCASE_SHA256_HEX_PATTERN.test(
      String(manifest.securityCheckpointSetSha256 || "")
    )
  );
}

function hasNoDistributionCapsule(manifest) {
  return !Object.prototype.hasOwnProperty.call(manifest || {}, "distributionCapsule");
}

function hasExpectedLeafRevocation(manifest) {
  const expected =
    manifest?.windowsSignerTrustMode === "private-pki"
      ? "build-and-lease-only"
      : "not-applicable";
  return manifest?.windowsPrivatePkiLeafRevocation === expected;
}

function isProductionNativeCoreManifest(manifest, options = {}) {
  return (
    hasValidManifestIdentity(manifest) &&
    hasActiveProductionBuildWindow(manifest, options) &&
    manifest.distributionMode === "public" &&
    hasNoDistributionCapsule(manifest) &&
    !NON_PRODUCTION_BUILD_ID_PATTERN.test(manifest.buildId) &&
    manifest.developmentBuild === false &&
    manifest.offlineBootstrapFeatureBits === 3 &&
    manifest.offlineExportSealFormat === "WES2" &&
    manifest.codeSignatureEnforced === true &&
    manifest.rootPublicKeyCompiled === true &&
    manifest.testHooksEnabled === false &&
    manifest.stagingPinnedSignerTrust === false &&
    isNonZeroSha256(manifest.windowsClientSignerSha256) &&
    isNonZeroSha256(manifest.windowsBrokerSignerSha256) &&
    String(manifest.windowsClientSignerSha256).toUpperCase() !==
      String(manifest.windowsBrokerSignerSha256).toUpperCase() &&
    new Set(["public", "private-pki"]).has(manifest.windowsSignerTrustMode) &&
    hasExpectedLeafRevocation(manifest) &&
    (manifest.windowsSignerTrustMode !== "private-pki" ||
      isNonZeroSha256(manifest.windowsPrivateRootSha256)) &&
    (manifest.windowsSignerTrustMode !== "public" ||
      new Set(["", "0".repeat(64)]).has(String(manifest.windowsPrivateRootSha256 || ""))) &&
    hasCurrentSecurityContract(manifest)
  );
}

function isDevelopmentNativeCoreManifest(manifest) {
  return (
    hasValidManifestIdentity(manifest) &&
    manifest.distributionMode === "public" &&
    hasNoDistributionCapsule(manifest) &&
    manifest.buildId === "dev-local" &&
    manifest.developmentBuild === true &&
    manifest.offlineBootstrapFeatureBits === 0 &&
    manifest.offlineExportSealFormat === "none" &&
    manifest.codeSignatureEnforced === false &&
    manifest.rootPublicKeyCompiled === false &&
    manifest.testHooksEnabled === true &&
    manifest.stagingPinnedSignerTrust === false &&
    manifest.windowsSignerTrustMode === "public" &&
    hasExpectedLeafRevocation(manifest) &&
    hasCurrentSecurityContract(manifest)
  );
}

function resolveNativeCoreRuntimePolicy({
  env = process.env,
  fsImpl = fs,
  isPackaged = false,
  nativeDir,
  nowUnix = Math.floor(Date.now() / 1000),
  platform = process.platform,
} = {}) {
  const directory = path.resolve(String(nativeDir || ""));
  const names = nativeCoreArtifactNames(platform);
  if (names.length === 0) {
    throw new Error(`wechatdb native core runtime is unsupported on platform: ${platform}`);
  }

  const complete = hasCompleteNativeCore(directory, platform, fsImpl);
  const manifest = complete ? readNativeCoreManifest(directory, fsImpl) : null;
  const production = complete && isProductionNativeCoreManifest(manifest, { nowUnix });
  const development = complete && isDevelopmentNativeCoreManifest(manifest);
  const explicitValue = String(env[ENV_NATIVE_CORE_MODE] || "").trim().toLowerCase();
  const explicit = explicitValue !== "";
  if (explicit && !NATIVE_CORE_MODES.has(explicitValue)) {
    throw new Error(
      `${ENV_NATIVE_CORE_MODE} must be required after native-core migration`
    );
  }

  if (!complete) {
    throw new Error(
      `Required wechatdb native core is incomplete in ${directory}. Expected: ${names.join(", ")}`
    );
  }
  if (isPackaged && !production) {
    throw new Error("Packaged WeChatDataAnalysis requires an approved production wechatdb native core");
  }
  if (!isPackaged && !development) {
    throw new Error("Source WeChatDataAnalysis requires the exact dev-local wechatdb native core");
  }

  const enableDevelopmentOverride = !isPackaged;
  const reason = isPackaged ? "production-artifacts" : "source-development-artifacts";

  return {
    artifactState: isPackaged ? "production" : "development",
    enableDevelopmentOverride,
    explicit,
    manifest,
    mode: "required",
    nativeDir: directory,
    reason,
  };
}

function applyNativeCoreRuntimePolicy(env, options = {}) {
  const target = env || process.env;
  const policy = resolveNativeCoreRuntimePolicy({ ...options, env: target });
  target[ENV_NATIVE_CORE_MODE] = policy.mode;
  if (policy.enableDevelopmentOverride) {
    target[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD] = "1";
  } else {
    delete target[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD];
  }
  return policy;
}

module.exports = {
  ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
  ENV_NATIVE_CORE_MODE,
  applyNativeCoreRuntimePolicy,
  hasCompleteNativeCore,
  isDevelopmentNativeCoreManifest,
  isProductionNativeCoreManifest,
  nativeCoreArtifactNames,
  readNativeCoreManifest,
  resolveNativeCoreRuntimePolicy,
};
