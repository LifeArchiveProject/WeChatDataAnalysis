"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const {
  extractCodeSigningLeafCertificate,
} = require("./macos-codesign-certificates.cjs");

function run(command, args, { capture = false } = {}) {
  const result = spawnSync(command, args, { encoding: "utf8", stdio: capture ? "pipe" : "inherit" });
  if (result.error) throw result.error;
  const output = `${result.stdout || ""}${result.stderr || ""}`;
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed (${result.status}):\n${output}`);
  return output;
}

function inspectSignedIdentity(filePath) {
  const details = run("codesign", ["-dv", "--verbose=4", filePath], { capture: true });
  const identifier = /^Identifier=([^\r\n]+)$/m.exec(details)?.[1]?.trim();
  if (!identifier || /^Signature=adhoc$/m.test(details)) {
    throw new Error(`Signed file has no certificate-backed identity: ${filePath}`);
  }
  const cert = new crypto.X509Certificate(extractCodeSigningLeafCertificate(filePath));
  return {
    details,
    identifier,
    leafSha256: cert.fingerprint256.replaceAll(":", "").toLowerCase(),
    leafSha1: cert.fingerprint.replaceAll(":", "").toLowerCase(),
  };
}

function verifyDesignatedRequirement(filePath, identifier, leafSha1) {
  const requirement = run("codesign", ["-d", "-r-", filePath], { capture: true });
  const designated = requirement
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^designated\s*=>/i.test(line));
  if (designated.length !== 1) {
    throw new Error(`Signed file has an ambiguous designated requirement: ${filePath}`);
  }
  const normalized = designated[0].replace(/\s+/g, " ").replace(/;$/, "").toLowerCase();
  if (/\b(?:anchor|trusted)\b/i.test(normalized)) {
    throw new Error(`Self-signed designated requirement must not depend on anchor trusted: ${filePath}`);
  }
  const expected = `designated => identifier "${identifier}" and certificate leaf = h"${leafSha1}"`.toLowerCase();
  if (normalized !== expected) {
    throw new Error(`Signed file lacks the fixed identifier + leaf designated requirement: ${filePath}`);
  }
  run("codesign", [
    "--verify", "--strict", "--verbose=2",
    `-R=identifier "${identifier}" and certificate leaf = H"${leafSha1}"`,
    filePath,
  ]);
}

module.exports = async function afterSign(context) {
  if (context.electronPlatformName !== "darwin" || process.env.MACOS_DISTRIBUTION_BUILD !== "1") return;

  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  if (!fs.existsSync(appPath)) throw new Error(`Signed macOS app not found: ${appPath}`);
  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const mode = String(process.env.WCE_MACOS_SIGNING_MODE || "").trim().toLowerCase();
  if (mode === "self-signed") {
    const expectedHostSigner = String(process.env.WCE_MACOS_WCDA_HOST_SIGNER_SHA256 || "").trim();
    if (!/^[0-9a-f]{64}$/.test(expectedHostSigner) || /^0{64}$/.test(expectedHostSigner)) {
      throw new Error("Self-signed verification requires WCE_MACOS_WCDA_HOST_SIGNER_SHA256.");
    }
    const appIdentity = inspectSignedIdentity(appPath);
    const backendPath = path.join(appPath, "Contents", "Resources", "backend", "wechat-backend");
    if (!fs.existsSync(backendPath)) throw new Error(`Signed backend not found: ${backendPath}`);
    const backendIdentity = inspectSignedIdentity(backendPath);
    if (
      appIdentity.identifier !== "com.lifearchive.wechatdataanalysis" ||
      backendIdentity.identifier !== "com.lifearchive.wechatdataanalysis.backend" ||
      appIdentity.leafSha256 !== expectedHostSigner ||
      backendIdentity.leafSha256 !== expectedHostSigner
    ) {
      throw new Error("Self-signed app/backend identity does not match the fixed host signer pin.");
    }
    const signingIdentity = String(process.env.WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY || "").trim();
    if (!signingIdentity || signingIdentity === "-") {
      throw new Error("Self-signed verification requires the explicit host signing identity.");
    }
    const appRequirement = `=designated => identifier "com.lifearchive.wechatdataanalysis" and certificate leaf = H"${appIdentity.leafSha1}"`;
    const entitlements = path.join(context.packager.projectDir, "entitlements.mac.plist");
    run("codesign", [
      "--force", "--sign", signingIdentity, "--options", "runtime", "--timestamp=none",
      "--identifier", "com.lifearchive.wechatdataanalysis", `-r${appRequirement}`,
      "--entitlements", entitlements, appPath,
    ]);
    run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
    const sealedAppIdentity = inspectSignedIdentity(appPath);
    if (
      sealedAppIdentity.identifier !== "com.lifearchive.wechatdataanalysis" ||
      sealedAppIdentity.leafSha256 !== expectedHostSigner
    ) {
      throw new Error("Re-sealed self-signed app identity drifted from the host pin.");
    }
    verifyDesignatedRequirement(
      appPath,
      "com.lifearchive.wechatdataanalysis",
      sealedAppIdentity.leafSha1
    );
    verifyDesignatedRequirement(
      backendPath,
      "com.lifearchive.wechatdataanalysis.backend",
      backendIdentity.leafSha1
    );
    process.stdout.write("Verified persistent self-signed app/backend identities; notarization and stapling are disabled.\n");
    return;
  }
  if (mode !== "developer-id") {
    throw new Error("WCE_MACOS_SIGNING_MODE must be self-signed or developer-id.");
  }
  const details = inspectSignedIdentity(appPath).details;
  if (!/^Authority=Developer ID Application:/m.test(details)) {
    throw new Error(`Release app is not signed with Developer ID Application:\n${details}`);
  }
  run("xcrun", ["stapler", "staple", "-v", appPath]);
  run("xcrun", ["stapler", "validate", "-v", appPath]);
};
