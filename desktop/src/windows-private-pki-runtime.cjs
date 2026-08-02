"use strict";

const { spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const POLICY_SHA256 = "5EC859FA7AC688547A294E415B1013525A979B9F2B2E5EF32C041BBDB4FF7B73";
const SHA256_PATTERN = /^[0-9A-Fa-f]{64}$/;

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex").toUpperCase();
}

function requireFile(filePath, label) {
  let stat;
  try {
    stat = fs.statSync(filePath);
  } catch {
    throw new Error(`Missing ${label}.`);
  }
  if (!stat.isFile() || stat.size <= 0) throw new Error(`Missing ${label}.`);
  return filePath;
}

function resolvePrivatePkiRuntime(resourcesPath) {
  const resources = path.resolve(resourcesPath);
  const nativeRoot = path.join(resources, "backend", "native");
  const manifestPath = requireFile(
    path.join(nativeRoot, "wechatdb_native_build.json"),
    "native production manifest"
  );
  const rootCertificate = requireFile(
    path.join(resources, "signing", "windows-private-pki-root.cer"),
    "private-PKI root certificate"
  );
  const policyScript = requireFile(
    path.join(resources, "signing", "windows-private-pki.ps1"),
    "private-PKI verification policy"
  );
  let manifest;
  try {
    const stat = fs.statSync(manifestPath);
    if (stat.size > 16 * 1024) throw new Error("manifest is too large");
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    throw new Error(`Invalid native production manifest: ${error.message}`);
  }
  const signer = String(manifest?.windowsClientSignerSha256 || "").toUpperCase();
  const root = String(manifest?.windowsPrivateRootSha256 || "").toUpperCase();
  if (
    manifest?.developmentBuild !== false ||
    manifest?.stagingPinnedSignerTrust !== false ||
    manifest?.windowsSignerTrustMode !== "private-pki" ||
    !SHA256_PATTERN.test(signer) ||
    /^0{64}$/.test(signer) ||
    !SHA256_PATTERN.test(root) ||
    /^0{64}$/.test(root)
  ) {
    throw new Error("Native manifest does not declare an approved private-PKI identity.");
  }
  if (sha256File(rootCertificate) !== root) {
    throw new Error("Packaged private-PKI root does not match the native manifest pin.");
  }
  if (sha256File(policyScript) !== POLICY_SHA256) {
    throw new Error("Packaged private-PKI verification policy was modified.");
  }
  return {
    expectedRootSha256: root,
    expectedSignerSha256: signer,
    manifest,
    policyScript,
    rootCertificate,
  };
}

function verifyPrivatePkiExecutable(
  executablePath,
  { resourcesPath, spawn = spawnSync, powershellPath = "powershell.exe" } = {}
) {
  const target = requireFile(path.resolve(executablePath), "update installer");
  if (path.extname(target).toLowerCase() !== ".exe") {
    throw new Error("Private-PKI update verification accepts Windows executables only.");
  }
  const identity = resolvePrivatePkiRuntime(resourcesPath);
  const args = [
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    identity.policyScript,
    "-Action",
    "Verify",
    "-Path",
    target,
    "-ExpectedSignerSha256",
    identity.expectedSignerSha256,
    "-ExpectedRootSha256",
    identity.expectedRootSha256,
    "-PrivateRootCertificatePath",
    identity.rootCertificate,
  ];
  const result = spawn(powershellPath, args, {
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    throw new Error("Downloaded update failed the private-PKI Authenticode policy.");
  }
  return true;
}

function ensurePrivatePkiIssuerCached(
  { resourcesPath, spawn = spawnSync, powershellPath = "powershell.exe" } = {}
) {
  const identity = resolvePrivatePkiRuntime(resourcesPath);
  const args = [
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    identity.policyScript,
    "-Action",
    "CacheIssuer",
    "-ExpectedSignerSha256",
    identity.expectedSignerSha256,
    "-ExpectedRootSha256",
    identity.expectedRootSha256,
    "-PrivateRootCertificatePath",
    identity.rootCertificate,
  ];
  const result = spawn(powershellPath, args, {
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    throw new Error("Unable to cache the pinned private-PKI public issuer certificate.");
  }
  let evidence;
  try {
    evidence = JSON.parse(String(result.stdout || "").trim());
  } catch {
    throw new Error("Private-PKI issuer cache returned invalid evidence.");
  }
  if (
    evidence?.rootSha256 !== identity.expectedRootSha256 ||
    evidence?.issuerStore !== "CurrentUser\\CA" ||
    evidence?.trustedRootInstalled !== false
  ) {
    throw new Error("Private-PKI issuer cache did not preserve the pinned trust policy.");
  }
  return evidence;
}

function configurePrivatePkiUpdateVerification(
  updater,
  {
    isPackaged = false,
    platform = process.platform,
    resourcesPath = process.resourcesPath,
    verifier = verifyPrivatePkiExecutable,
  } = {}
) {
  if (!updater || platform !== "win32" || !isPackaged) return false;
  updater.verifyUpdateCodeSignature = async (_publisherNames, installerPath) => {
    try {
      verifier(installerPath, { resourcesPath });
      return null;
    } catch (error) {
      return `Private-PKI update signature rejected: ${error?.message || "verification failed"}`;
    }
  };
  return true;
}

module.exports = {
  POLICY_SHA256,
  configurePrivatePkiUpdateVerification,
  ensurePrivatePkiIssuerCached,
  resolvePrivatePkiRuntime,
  sha256File,
  verifyPrivatePkiExecutable,
};
