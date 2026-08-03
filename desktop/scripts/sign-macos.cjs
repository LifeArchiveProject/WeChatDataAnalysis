"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { signAsync } = require("@electron/osx-sign");
const { contract: macosXkeyContract } = require("./macos-xkey-packaging.cjs");

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

function isDistributionBuild() {
  return TRUE_VALUES.has(String(process.env.MACOS_DISTRIBUTION_BUILD || "").trim().toLowerCase());
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function inspectCodeSignature(filePath) {
  const verify = spawnSync(
    "/usr/bin/codesign",
    ["--verify", "--strict", "--verbose=2", filePath],
    { stdio: "ignore" }
  );
  if ((verify.status ?? 1) !== 0) throw new Error(`Code signature verification failed: ${filePath}`);
  const details = spawnSync("/usr/bin/codesign", ["-d", "--verbose=4", filePath], {
    encoding: "utf8",
  });
  const detailText = `${details.stdout || ""}\n${details.stderr || ""}`;
  const identifier = /^Identifier=([^\r\n]+)$/m.exec(detailText)?.[1]?.trim();
  if ((details.status ?? 1) !== 0 || !identifier) {
    throw new Error(`Unable to read code signature identifier: ${filePath}`);
  }
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "wda-macos-sign-cert-"));
  try {
    const prefix = path.join(tempDir, "leaf");
    const extracted = spawnSync(
      "/usr/bin/codesign",
      ["-d", "--extract-certificates", prefix, filePath],
      { stdio: "ignore" }
    );
    const certPath = `${prefix}0`;
    if ((extracted.status ?? 1) !== 0 || !fs.existsSync(certPath)) {
      throw new Error(`Unable to extract code signature leaf certificate: ${filePath}`);
    }
    const certificate = new crypto.X509Certificate(fs.readFileSync(certPath));
    return {
      identifier,
      leafSha256: certificate.fingerprint256.replaceAll(":", "").toLowerCase(),
    };
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function ignoreList(value) {
  if (value == null) return [];
  return Array.isArray(value) ? [...value] : [value];
}

function requiredSigningMode() {
  const mode = String(process.env.WCE_MACOS_SIGNING_MODE || "").trim().toLowerCase();
  if (!new Set(["self-signed", "developer-id"]).has(mode)) {
    throw new Error("WCE_MACOS_SIGNING_MODE must be exactly self-signed or developer-id.");
  }
  return mode;
}

function requireSelfSignedIdentity(expectedLeafSha256) {
  const identity = String(process.env.WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY || "").trim();
  if (!identity || identity === "-") {
    throw new Error("Self-signed distribution requires an explicit WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY.");
  }
  const listed = spawnSync(
    "/usr/bin/security",
    ["find-identity", "-v", "-p", "codesigning"],
    { encoding: "utf8" }
  );
  const output = `${listed.stdout || ""}\n${listed.stderr || ""}`;
  if ((listed.status ?? 1) !== 0) throw new Error("Unable to enumerate macOS code-signing identities.");
  const escaped = identity.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const exactMatches = output.match(new RegExp(`^[ \\t]*[0-9]+\\) [0-9A-Fa-f]{40} "${escaped}"[ \\t]*$`, "gm")) || [];
  if (exactMatches.length !== 1) {
    throw new Error("The configured self-signed host identity must have exactly one usable private key.");
  }
  const certificates = spawnSync(
    "/usr/bin/security",
    ["find-certificate", "-a", "-c", identity, "-p"],
    { encoding: "utf8" }
  );
  if ((certificates.status ?? 1) !== 0) throw new Error("Unable to inspect the configured host certificate.");
  const pemBlocks = String(certificates.stdout || "").match(/-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----/g) || [];
  const certificatesByPin = pemBlocks
    .map((pem) => new crypto.X509Certificate(pem))
    .filter((certificate) =>
      certificate.fingerprint256.replaceAll(":", "").toLowerCase() === expectedLeafSha256
    );
  if (certificatesByPin.length !== 1) {
    throw new Error("The configured self-signed host identity does not match WCE_MACOS_WCDA_HOST_SIGNER_SHA256.");
  }
  return {
    identity,
    leafSha1: certificatesByPin[0].fingerprint.replaceAll(":", "").toLowerCase(),
  };
}

module.exports = async function signMacos(options) {
  const helperSuffix = path.join(
    "Contents",
    "Resources",
    "backend",
    "native",
    "macos",
    "universal",
    "image_scan_helper"
  );
  const helperPath = path.join(options.app, helperSuffix);
  const databaseKeyHelperSuffix = path.join(
    "Contents",
    "Resources",
    "backend",
    "native",
    ...String(macosXkeyContract.bundleRelativePath).split("/"),
    macosXkeyContract.helperFileName
  );
  const databaseKeyHelperPath = path.join(options.app, databaseKeyHelperSuffix);
  const databaseKeyManifestPath = path.join(
    path.dirname(databaseKeyHelperPath),
    macosXkeyContract.manifestFileName
  );
  const databaseKeyTrustPath = path.join(
    path.dirname(databaseKeyHelperPath),
    macosXkeyContract.trustFileName
  );
  const backendSuffix = path.join("Contents", "Resources", "backend", "wechat-backend");
  const backendPath = path.join(options.app, backendSuffix);
  const helperEntitlements = path.resolve(
    __dirname,
    "..",
    "..",
    "src",
    "wechat_decrypt_tool",
    "native",
    "macos",
    "source",
    "image_scan_entitlements.plist"
  );
  if (!fs.existsSync(helperPath)) throw new Error(`Packaged image helper not found: ${helperPath}`);
  if (!fs.existsSync(helperEntitlements)) throw new Error(`Image helper entitlements not found: ${helperEntitlements}`);
  if (!fs.existsSync(databaseKeyHelperPath)) {
    throw new Error(`Packaged macOS database key helper not found: ${databaseKeyHelperPath}`);
  }
  if (!fs.existsSync(backendPath)) throw new Error(`Packaged backend not found: ${backendPath}`);
  const xkeyManifest = JSON.parse(fs.readFileSync(databaseKeyManifestPath, "utf8"));
  const xkeyTrust = JSON.parse(fs.readFileSync(databaseKeyTrustPath, "utf8"));
  const helperMetadata = xkeyManifest?.files?.[macosXkeyContract.helperFileName];
  if (
    !helperMetadata ||
    sha256File(databaseKeyHelperPath) !== helperMetadata.sha256 ||
    fs.statSync(databaseKeyHelperPath).size !== helperMetadata.size
  ) {
    throw new Error("Packaged macOS database key helper does not match its manifest.");
  }

  const distribution = isDistributionBuild();
  const expectedHelperSigner = String(process.env.WCE_MACOS_KEY_HELPER_SIGNER_SHA256 || "").trim();
  const expectedHostSigner = String(process.env.WCE_MACOS_WCDA_HOST_SIGNER_SHA256 || "").trim();
  const signingMode = distribution ? requiredSigningMode() : null;
  if (
    distribution &&
    (!/^[0-9a-f]{64}$/.test(expectedHelperSigner) || !/^[0-9a-f]{64}$/.test(expectedHostSigner))
  ) {
    throw new Error(
      "Distribution signing requires WCE_MACOS_KEY_HELPER_SIGNER_SHA256 and " +
      "WCE_MACOS_WCDA_HOST_SIGNER_SHA256."
    );
  }
  if (distribution && xkeyManifest?.signing?.mode !== signingMode) {
    throw new Error("The selected macOS signing mode does not match the producer helper manifest.");
  }
  const explicitIdentity = distribution && signingMode === "self-signed"
    ? requireSelfSignedIdentity(expectedHostSigner)
    : undefined;
  if (
    distribution &&
    (xkeyTrust.helperLeafCertificateSha256 !== expectedHelperSigner ||
      xkeyTrust.hostLeafCertificateSha256 !== expectedHostSigner)
  ) {
    throw new Error("Packaged macOS signer trust does not match protected environment pins.");
  }
  if (distribution) {
    const before = inspectCodeSignature(databaseKeyHelperPath);
    if (
      before.identifier !== macosXkeyContract.bundleId ||
      before.leafSha256 !== expectedHelperSigner
    ) {
      throw new Error("Producer-signed macOS database key helper identity does not match pins.");
    }
  }

  const baseOptionsForFile = options.optionsForFile;
  const preservedHelperHash = sha256File(databaseKeyHelperPath);
  await signAsync({
    ...options,
    ...(explicitIdentity ? { identity: explicitIdentity.identity } : {}),
    ignore: [
      ...ignoreList(options.ignore),
      (filePath) => path.resolve(filePath) === path.resolve(databaseKeyHelperPath),
    ],
    optionsForFile(filePath) {
      const inherited = typeof baseOptionsForFile === "function" ? baseOptionsForFile(filePath) || {} : {};
      const effective = signingMode === "self-signed"
        ? { ...inherited, timestamp: "none" }
        : inherited;
      if (filePath === helperPath || filePath.endsWith(path.sep + helperSuffix)) {
        return { ...effective, entitlements: helperEntitlements };
      }
      if (filePath === backendPath || filePath.endsWith(path.sep + backendSuffix)) {
        const backendRequirement = explicitIdentity
          ? `=designated => identifier "${macosXkeyContract.hostSigningIdentifier}" and certificate leaf = H"${explicitIdentity.leafSha1}"`
          : null;
        return {
          ...effective,
          ...(backendRequirement ? { requirements: backendRequirement } : {}),
          additionalArguments: [
            ...(effective.additionalArguments || []),
            "--identifier",
            macosXkeyContract.hostSigningIdentifier,
          ],
        };
      }
      return effective;
    },
  });

  if (sha256File(databaseKeyHelperPath) !== preservedHelperHash) {
    throw new Error("macOS app signing modified the producer-signed database key helper.");
  }
  if (distribution) {
    const helperAfter = inspectCodeSignature(databaseKeyHelperPath);
    if (
      helperAfter.identifier !== macosXkeyContract.bundleId ||
      helperAfter.leafSha256 !== expectedHelperSigner
    ) {
      throw new Error("macOS app signing replaced the producer helper identity.");
    }
    const backendAfter = inspectCodeSignature(backendPath);
    if (
      backendAfter.identifier !== macosXkeyContract.hostSigningIdentifier ||
      backendAfter.leafSha256 !== expectedHostSigner
    ) {
      throw new Error("Signed backend identity does not match the helper caller pin.");
    }
  }
};
