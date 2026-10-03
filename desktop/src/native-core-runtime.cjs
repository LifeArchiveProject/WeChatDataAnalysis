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
const ZERO_SHA256_HEX = "0".repeat(64);
const LINUX_MANIFEST_FIELDS = [
  "linuxIntegrityMode",
  "linuxClientSha256",
  "linuxBrokerSha256",
  "linuxPeerVerification",
  "linuxHostVerification",
];
// Linux 清单是纯内容哈希身份：不得夹带任何代码签名身份字段，与 native_core_client
// 的字段隔离约束一致（在那里由 NativeCoreProtocolError 拒绝）。
const CODE_SIGNING_IDENTITY_FIELDS = [
  "windowsSignerTrustMode",
  "windowsPrivatePkiLeafRevocation",
  "windowsClientSignerSha256",
  "windowsBrokerSignerSha256",
  "windowsPrivateRootSha256",
  "windowsHostVerification",
  "macosSigningMode",
  "macosSignerTrustMode",
  "macosPrivatePkiLeafRevocation",
  "macosClientSigningIdentifier",
  "macosBrokerSigningIdentifier",
  "macosHostSigningIdentifier",
  "macosClientSignerSha256",
  "macosBrokerSignerSha256",
  "macosHostSignerSha256",
  "macosPrivateRootSha256",
  "macosHostVerification",
];
// Linux 的发布形态（schema v4）没有代码签名：身份 = 两组内容哈希 pin + 直接父进程的
// 宿主校验。发布工作流发的就是这一份受限 source-public 产物，所以冻结应用必须消费它
// ——与 Windows（schema v2）同一原则。macOS（schema v3）走真正的签名 production，
// 冻结态只认 production。
const PACKAGED_SOURCE_PUBLIC_SCHEMAS = new Set([2, 4]);

function hasOwnField(value, name) {
  return Object.prototype.hasOwnProperty.call(value || {}, name);
}

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
  if (platform === "linux") {
    return ["libwechatdb_client.so", "wechatdb_broker", NATIVE_CORE_MANIFEST];
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
  const identityMatches =
    (manifest?.schemaVersion === 2 && !hasOwnField(manifest, "platform")) ||
    (manifest?.schemaVersion === 3 && manifest?.platform === "macos") ||
    (manifest?.schemaVersion === 4 && manifest?.platform === "linux");
  if (!identityMatches) return false;
  if (typeof manifest.buildId !== "string" || !BUILD_ID_PATTERN.test(manifest.buildId)) {
    return false;
  }
  // Linux 的内容哈希身份字段属于 Linux 清单专有：schema v2/v3 不得夹带，
  // schema v4 必须完整声明且不得混入签名身份字段。与 native_core_client 的字段
  // 隔离约束一致，避免出现「桌面放行、后端拒绝」的半可用状态。
  const declaredLinuxFields = LINUX_MANIFEST_FIELDS.filter((name) =>
    hasOwnField(manifest, name)
  ).length;
  if (manifest.schemaVersion === 4) {
    return (
      declaredLinuxFields === LINUX_MANIFEST_FIELDS.length &&
      !CODE_SIGNING_IDENTITY_FIELDS.some((name) => hasOwnField(manifest, name))
    );
  }
  return declaredLinuxFields === 0;
}

function hasLinuxContentHashIdentity(manifest) {
  const clientPin = String(manifest?.linuxClientSha256 || "").toLowerCase();
  const brokerPin = String(manifest?.linuxBrokerSha256 || "").toLowerCase();
  return (
    manifest?.platform === "linux" &&
    manifest.linuxIntegrityMode === "content-hash-pin" &&
    manifest.linuxPeerVerification === "same-user-peer-credentials" &&
    isNonZeroSha256(clientPin) &&
    isNonZeroSha256(brokerPin) &&
    clientPin !== brokerPin
  );
}

// 宿主校验强度必须与 sourceRuntime 自洽（与 native_core_client 的授权矩阵同一条规则）：
// 源码分发只认「直接父进程」，其余情况用「内容哈希 pin」；development 构建不带
// sourceRuntime，所以这里只覆盖两种签发态。
function hasLinuxHostVerificationPairing(manifest) {
  const expected =
    manifest?.sourceRuntime === true
      ? "same-user-direct-parent"
      : "content-hash-pin";
  return manifest?.linuxHostVerification === expected;
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
  if (manifest?.schemaVersion === 3) {
    const expected =
      manifest?.macosSignerTrustMode === "private-pki"
        ? "build-and-lease-only"
        : "not-applicable";
    return manifest?.macosPrivatePkiLeafRevocation === expected;
  }
  const expected =
    manifest?.windowsSignerTrustMode === "private-pki"
      ? "build-and-lease-only"
      : "not-applicable";
  return manifest?.windowsPrivatePkiLeafRevocation === expected;
}

function isProductionNativeCoreManifestBase(manifest, options = {}) {
  const common = (
    hasValidManifestIdentity(manifest) &&
    hasActiveProductionBuildWindow(manifest, options) &&
    manifest.distributionMode === "public" &&
    hasNoDistributionCapsule(manifest) &&
    !NON_PRODUCTION_BUILD_ID_PATTERN.test(manifest.buildId) &&
    (manifest.schemaVersion !== 2 ||
      (manifest.readOnlyBuild === true &&
        Array.isArray(manifest.wechatActions) &&
        manifest.wechatActions.length === 0)) &&
    manifest.developmentBuild === false &&
    manifest.offlineBootstrapFeatureBits === 3 &&
    manifest.offlineExportSealFormat === "WES2" &&
    manifest.codeSignatureEnforced === true &&
    manifest.rootPublicKeyCompiled === true &&
    manifest.testHooksEnabled === false &&
    manifest.stagingPinnedSignerTrust === false &&
    hasCurrentSecurityContract(manifest)
  );
  if (!common) return false;
  if (manifest.schemaVersion === 3) {
    const identifiers = [
      manifest.macosClientSigningIdentifier,
      manifest.macosBrokerSigningIdentifier,
      manifest.macosHostSigningIdentifier,
    ];
    const pins = [
      manifest.macosClientSignerSha256,
      manifest.macosBrokerSignerSha256,
      manifest.macosHostSignerSha256,
      manifest.macosPrivateRootSha256,
    ];
    return (
      manifest.platform === "macos" &&
      manifest.macosSigningMode === "self-signed" &&
      manifest.macosSignerTrustMode === "private-pki" &&
      hasExpectedLeafRevocation(manifest) &&
      identifiers.every((value) => /^[A-Za-z0-9.-]+$/.test(String(value || ""))) &&
      new Set(identifiers).size === 3 &&
      pins.every(isNonZeroSha256) &&
      new Set(pins.map((value) => String(value).toLowerCase())).size === 4
    );
  }
  if (manifest.schemaVersion === 4) {
    return hasLinuxContentHashIdentity(manifest) && hasLinuxHostVerificationPairing(manifest);
  }
  return (
    isNonZeroSha256(manifest.windowsClientSignerSha256) &&
    isNonZeroSha256(manifest.windowsBrokerSignerSha256) &&
    String(manifest.windowsClientSignerSha256).toUpperCase() !==
      String(manifest.windowsBrokerSignerSha256).toUpperCase() &&
    new Set(["public", "private-pki"]).has(manifest.windowsSignerTrustMode) &&
    hasExpectedLeafRevocation(manifest) &&
    (manifest.windowsSignerTrustMode !== "private-pki" ||
      isNonZeroSha256(manifest.windowsPrivateRootSha256)) &&
    (manifest.windowsSignerTrustMode !== "public" ||
      new Set(["", "0".repeat(64)]).has(String(manifest.windowsPrivateRootSha256 || "")))
  );
}

function hasSourceRuntimeFields(manifest) {
  return (
    Object.prototype.hasOwnProperty.call(manifest || {}, "sourceRuntime") ||
    Object.prototype.hasOwnProperty.call(manifest || {}, "macosHostVerification") ||
    Object.prototype.hasOwnProperty.call(manifest || {}, "windowsHostVerification")
  );
}

function isProductionNativeCoreManifest(manifest, options = {}) {
  return (
    isProductionNativeCoreManifestBase(manifest, options) &&
    !hasSourceRuntimeFields(manifest)
  );
}

function isSourcePublicNativeCoreManifest(manifest, options = {}) {
  if (
    !isProductionNativeCoreManifestBase(manifest, options) ||
    manifest.sourceRuntime !== true
  ) {
    return false;
  }
  if (manifest.schemaVersion === 3) {
    return manifest.macosHostVerification === "same-user-direct-parent";
  }
  if (manifest.schemaVersion === 4) {
    return manifest.linuxHostVerification === "same-user-direct-parent";
  }
  return (
    manifest.schemaVersion === 2 &&
    manifest.windowsHostVerification === "same-user-direct-parent"
  );
}

function isDevelopmentNativeCoreManifest(manifest) {
  const common = (
    hasValidManifestIdentity(manifest) &&
    manifest.distributionMode === "public" &&
    hasNoDistributionCapsule(manifest) &&
    manifest.buildId === "dev-local" &&
    (manifest.schemaVersion !== 2 ||
      (manifest.readOnlyBuild === true &&
        Array.isArray(manifest.wechatActions) &&
        manifest.wechatActions.length === 0)) &&
    manifest.developmentBuild === true &&
    manifest.offlineBootstrapFeatureBits === 0 &&
    manifest.offlineExportSealFormat === "none" &&
    manifest.codeSignatureEnforced === false &&
    manifest.rootPublicKeyCompiled === false &&
    manifest.testHooksEnabled === true &&
    manifest.stagingPinnedSignerTrust === false &&
    hasCurrentSecurityContract(manifest)
  );
  if (!common) return false;
  if (manifest.schemaVersion === 3) {
    const identifiers = [
      manifest.macosClientSigningIdentifier,
      manifest.macosBrokerSigningIdentifier,
      manifest.macosHostSigningIdentifier,
    ];
    const pins = [
      manifest.macosClientSignerSha256,
      manifest.macosBrokerSignerSha256,
      manifest.macosHostSignerSha256,
      manifest.macosPrivateRootSha256,
    ];
    return (
      manifest.platform === "macos" &&
      manifest.macosSigningMode === "self-signed" &&
      manifest.macosSignerTrustMode === "development" &&
      hasExpectedLeafRevocation(manifest) &&
      identifiers.every((value) => /^[A-Za-z0-9.-]+$/.test(String(value || ""))) &&
      new Set(identifiers).size === 3 &&
      pins.every((value) => String(value || "") === ZERO_SHA256_HEX)
    );
  }
  if (manifest.schemaVersion === 4) {
    // dev-local 的 Linux 构建不携带任何内容哈希身份，且不声明 sourceRuntime。
    return (
      manifest.platform === "linux" &&
      manifest.linuxIntegrityMode === "development" &&
      manifest.linuxPeerVerification === "same-user-peer-credentials" &&
      manifest.sourceRuntime !== true &&
      new Set(["content-hash-pin", "same-user-direct-parent"]).has(
        manifest.linuxHostVerification
      ) &&
      String(manifest.linuxClientSha256 || "") === ZERO_SHA256_HEX &&
      String(manifest.linuxBrokerSha256 || "") === ZERO_SHA256_HEX
    );
  }
  return manifest.windowsSignerTrustMode === "public" && hasExpectedLeafRevocation(manifest);
}

function manifestMatchesPlatform(manifest, platform) {
  return (
    (platform === "win32" && manifest?.schemaVersion === 2) ||
    (platform === "darwin" && manifest?.schemaVersion === 3 && manifest?.platform === "macos") ||
    (platform === "linux" && manifest?.schemaVersion === 4 && manifest?.platform === "linux")
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
  const platformMatch = complete && manifestMatchesPlatform(manifest, platform);
  const production = platformMatch && (
    isProductionNativeCoreManifest(manifest, { nowUnix }) ||
    (isPackaged &&
      PACKAGED_SOURCE_PUBLIC_SCHEMAS.has(manifest?.schemaVersion) &&
      isSourcePublicNativeCoreManifest(manifest, { nowUnix }))
  );
  const sourcePublic =
    platformMatch && isSourcePublicNativeCoreManifest(manifest, { nowUnix });
  const development = platformMatch && isDevelopmentNativeCoreManifest(manifest);
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
  if (!isPackaged && platform === "darwin" && !sourcePublic) {
    throw new Error(
      "Source WeChatDataAnalysis on macOS requires the exact restricted source-public wechatdb native core"
    );
  }
  // Linux 与 macOS 同一条规则：源码态只接受受限 source-public 产物（发布工作流发的就是
  // 这一份）。后端 native_core_client 在 Linux 上同样只授权 source-public，两边必须一致，
  // 否则出现「桌面放行、后端拒绝」的半可用状态。
  if (!isPackaged && platform === "linux" && !sourcePublic) {
    throw new Error(
      "Source WeChatDataAnalysis on Linux requires the exact restricted source-public wechatdb native core"
    );
  }
  if (!isPackaged && platform === "win32" && !sourcePublic && !development) {
    throw new Error(
      "Source WeChatDataAnalysis on Windows requires the exact restricted source-public or dev-local wechatdb native core"
    );
  }

  const enableDevelopmentOverride = !isPackaged && development;
  const reason = isPackaged
    ? "production-artifacts"
    : sourcePublic
      ? "source-public-artifacts"
      : "source-development-artifacts";

  return {
    artifactState: isPackaged
      ? "production"
      : sourcePublic
        ? "source-public"
        : "development",
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
  isSourcePublicNativeCoreManifest,
  nativeCoreArtifactNames,
  readNativeCoreManifest,
  resolveNativeCoreRuntimePolicy,
};
