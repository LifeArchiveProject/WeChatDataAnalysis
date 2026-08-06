const fs = require("fs");
const crypto = require("crypto");
const path = require("path");

const {
  nativeCoreArtifactNames,
  nativeCoreProductionManifestErrors,
} = require("./build-backend.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const LEGACY_WCDB_PATHS = [
  "wcdb_api.dll",
  "WCDB.dll",
  "libwcdb_api.dylib",
  "libWCDB.dylib",
  path.join("macos", "arm64", "libwcdb_api.dylib"),
  path.join("macos", "universal", "libWCDB.dylib"),
];
const PRIVATE_PKI_ROOT_NAME = "windows-private-pki-root.cer";
const PRIVATE_PKI_POLICY_NAME = "windows-private-pki.ps1";
const MACOS_PRIVATE_PKI_ROOT_NAME = "macos-private-pki-root.cer";
const privatePkiPolicySource = path.join(__dirname, PRIVATE_PKI_POLICY_NAME);
const SIGNING_RESOURCE_NAMES = new Set([
  PRIVATE_PKI_ROOT_NAME,
  PRIVATE_PKI_POLICY_NAME,
  MACOS_PRIVATE_PKI_ROOT_NAME,
]);

function requireRegularFile(filePath, label) {
  try {
    const stat = fs.statSync(filePath);
    if (stat.isFile() && stat.size > 0) return;
  } catch {}
  throw new Error(`Packaged ${label} is missing or empty: ${filePath}`);
}

function readManifest(manifestPath) {
  requireRegularFile(manifestPath, "wechatdb native manifest");
  const stat = fs.statSync(manifestPath);
  if (stat.size > 16 * 1024) {
    throw new Error(`Packaged wechatdb native manifest is too large: ${manifestPath}`);
  }
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    if (!manifest || Array.isArray(manifest) || typeof manifest !== "object") {
      throw new Error("manifest root must be an object");
    }
    return manifest;
  } catch (error) {
    throw new Error(
      `Packaged wechatdb native manifest is invalid: ${error?.message || error}`
    );
  }
}

function requireSha256(value, name) {
  const normalized = String(value || "").trim().toUpperCase();
  if (!/^[0-9A-F]{64}$/.test(normalized) || /^0{64}$/.test(normalized)) {
    throw new Error(`${name} must be a non-zero SHA-256 digest.`);
  }
  return normalized;
}

function resetSigningEvidenceDirectory(signingDir) {
  fs.mkdirSync(signingDir, { recursive: true });
  for (const entry of fs.readdirSync(signingDir, { withFileTypes: true })) {
    if (entry.isFile() && SIGNING_RESOURCE_NAMES.has(entry.name)) {
      fs.rmSync(path.join(signingDir, entry.name), { force: true });
      continue;
    }
    if (entry.isFile() && entry.name === ".gitkeep") continue;
    throw new Error(`Unexpected file in private-PKI signing resources: ${entry.name}`);
  }
}

function stageWindowsPrivatePkiEvidence({
  env = process.env,
  manifest,
  signingDir = path.join(desktopRoot, "resources", "signing"),
} = {}) {
  if (manifest?.windowsSignerTrustMode !== "private-pki") {
    throw new Error("Windows production packaging requires private-pki signer trust.");
  }
  const manifestRoot = requireSha256(
    manifest.windowsPrivateRootSha256,
    "manifest windowsPrivateRootSha256"
  );
  const expectedRoot = requireSha256(
    env.WCE_WINDOWS_PRIVATE_ROOT_SHA256,
    "WCE_WINDOWS_PRIVATE_ROOT_SHA256"
  );
  if (manifestRoot !== expectedRoot) {
    throw new Error("Protected private-PKI root pin does not match the native manifest.");
  }
  const sourceValue = String(env.WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH || "").trim();
  if (!sourceValue) throw new Error("WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH is required.");
  const source = path.resolve(sourceValue);
  requireRegularFile(source, "private-PKI root certificate");
  const actualRoot = crypto.createHash("sha256").update(fs.readFileSync(source)).digest("hex").toUpperCase();
  if (actualRoot !== expectedRoot) {
    throw new Error("Private-PKI root certificate file does not match the protected root pin.");
  }
  requireRegularFile(privatePkiPolicySource, "private-PKI verification policy");

  resetSigningEvidenceDirectory(signingDir);
  fs.copyFileSync(source, path.join(signingDir, PRIVATE_PKI_ROOT_NAME));
  fs.copyFileSync(privatePkiPolicySource, path.join(signingDir, PRIVATE_PKI_POLICY_NAME));
  return { rootSha256: actualRoot, signingDir };
}

function stageMacosPrivatePkiEvidence({
  env = process.env,
  manifest,
  signingDir = path.join(desktopRoot, "resources", "signing"),
} = {}) {
  if (
    manifest?.macosSigningMode !== "self-signed" ||
    manifest?.macosSignerTrustMode !== "private-pki"
  ) {
    throw new Error("macOS production packaging requires self-signed private-pki signer trust.");
  }
  const manifestRoot = requireSha256(
    manifest.macosPrivateRootSha256,
    "manifest macosPrivateRootSha256"
  );
  const expectedRoot = requireSha256(
    env.WCE_NATIVE_CORE_PRIVATE_ROOT_SHA256,
    "WCE_NATIVE_CORE_PRIVATE_ROOT_SHA256"
  );
  if (manifestRoot !== expectedRoot) {
    throw new Error("Protected macOS private-PKI root pin does not match the native manifest.");
  }
  const sourceValue = String(env.WCE_MACOS_PRIVATE_ROOT_CERT_PATH || "").trim();
  if (!sourceValue) throw new Error("WCE_MACOS_PRIVATE_ROOT_CERT_PATH is required.");
  const source = path.resolve(sourceValue);
  requireRegularFile(source, "macOS private-PKI root certificate");
  const actualRoot = crypto
    .createHash("sha256")
    .update(fs.readFileSync(source))
    .digest("hex")
    .toUpperCase();
  if (actualRoot !== expectedRoot) {
    throw new Error("macOS private-PKI root certificate file does not match the protected root pin.");
  }

  resetSigningEvidenceDirectory(signingDir);
  fs.copyFileSync(source, path.join(signingDir, MACOS_PRIVATE_PKI_ROOT_NAME));
  return { rootSha256: actualRoot, signingDir };
}

function validatePackagedBackend({
  backendDir = path.join(desktopRoot, "resources", "backend"),
  platform = process.platform,
} = {}) {
  const names = nativeCoreArtifactNames(platform);
  if (names.length === 0) {
    throw new Error(`wechatdb native core packaging is unsupported on platform: ${platform}`);
  }

  const backendExecutable = path.join(
    backendDir,
    platform === "win32" ? "wechat-backend.exe" : "wechat-backend"
  );
  const nativeDir = path.join(backendDir, "native");
  requireRegularFile(backendExecutable, "backend executable");
  for (const name of names) {
    requireRegularFile(path.join(nativeDir, name), `wechatdb native component ${name}`);
  }
  for (const relativePath of LEGACY_WCDB_PATHS) {
    if (fs.existsSync(path.join(nativeDir, relativePath))) {
      throw new Error(`Legacy WCDB runtime must not be packaged: ${relativePath}`);
    }
  }

  const manifest = readManifest(path.join(nativeDir, "wechatdb_native_build.json"));
  const errors = nativeCoreProductionManifestErrors(manifest);
  if (errors.length > 0) {
    throw new Error(
      `Packaged backend rejected a non-production wechatdb native core: ${errors.join("; ")}`
    );
  }
  return { backendDir, manifest, nativeDir, platform };
}

async function beforePack(context) {
  const platform =
    context?.electronPlatformName || context?.packager?.platform?.nodeName || process.platform;
  const validated = validatePackagedBackend({ platform });
  if (platform === "win32") {
    stageWindowsPrivatePkiEvidence({ manifest: validated.manifest });
  } else if (platform === "darwin") {
    stageMacosPrivatePkiEvidence({ manifest: validated.manifest });
  }
}

exports.default = beforePack;
exports.stageMacosPrivatePkiEvidence = stageMacosPrivatePkiEvidence;
exports.stageWindowsPrivatePkiEvidence = stageWindowsPrivatePkiEvidence;
exports.validatePackagedBackend = validatePackagedBackend;
