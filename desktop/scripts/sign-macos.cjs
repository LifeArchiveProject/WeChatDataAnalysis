"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { signAsync } = require("@electron/osx-sign");
const { contract: macosXkeyContract } = require("./macos-xkey-packaging.cjs");
const { macosNativeManifestErrors } = require("./macos-native-core-packaging.cjs");
const {
  extractCodeSigningLeafCertificate,
} = require("./macos-codesign-certificates.cjs");

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
  const certificate = new crypto.X509Certificate(
    extractCodeSigningLeafCertificate(filePath)
  );
  return {
    identifier,
    leafSha256: certificate.fingerprint256.replaceAll(":", "").toLowerCase(),
  };
}

function ignoreList(value) {
  if (value == null) return [];
  return Array.isArray(value) ? [...value] : [value];
}

function matchesIgnoreRule(filePath, rule) {
  return typeof rule === "function" ? Boolean(rule(filePath)) : Boolean(filePath.match(rule));
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
  process.stdout.write(`Starting controlled macOS signing: ${options.app}\n`);
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
  const nativeCoreDirectory = path.join(
    options.app,
    "Contents",
    "Resources",
    "backend",
    "native"
  );
  const nativeClientPath = path.join(nativeCoreDirectory, "libwechatdb_client.dylib");
  const nativeBrokerPath = path.join(nativeCoreDirectory, "wechatdb_broker");
  const nativeManifestPath = path.join(nativeCoreDirectory, "wechatdb_native_build.json");
  const integrityPath = path.join(nativeCoreDirectory, "libwce_integrity.dylib");
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
  for (const nativePath of [nativeClientPath, nativeBrokerPath, nativeManifestPath, integrityPath]) {
    if (!fs.existsSync(nativePath)) {
      throw new Error(`Packaged macOS native-core component not found: ${nativePath}`);
    }
  }
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
  const nativeManifest = JSON.parse(fs.readFileSync(nativeManifestPath, "utf8"));
  if (
    distribution &&
    (!/^[0-9a-f]{64}$/.test(expectedHelperSigner) || !/^[0-9a-f]{64}$/.test(expectedHostSigner))
  ) {
    throw new Error(
      "Distribution signing requires WCE_MACOS_KEY_HELPER_SIGNER_SHA256 and " +
      "WCE_MACOS_WCDA_HOST_SIGNER_SHA256."
    );
  }
  let expectedNativeClientSigner = "";
  let expectedNativeBrokerSigner = "";
  if (distribution) {
    const nativeErrors = macosNativeManifestErrors(nativeManifest);
    if (nativeErrors.length) {
      throw new Error(`Packaged macOS native-core manifest is invalid: ${nativeErrors.join("; ")}`);
    }
    const requiredValue = (name, pattern) => {
      const value = String(process.env[name] || "").trim();
      if (!pattern.test(value)) throw new Error(`Missing or invalid ${name}.`);
      return value;
    };
    expectedNativeClientSigner = requiredValue(
      "WCE_NATIVE_CORE_CLIENT_SIGNER_SHA256",
      /^[0-9a-f]{64}$/
    );
    expectedNativeBrokerSigner = requiredValue(
      "WCE_NATIVE_CORE_BROKER_SIGNER_SHA256",
      /^[0-9a-f]{64}$/
    );
    const expectedNativeHostSigner = requiredValue(
      "WCE_NATIVE_CORE_HOST_SIGNER_SHA256",
      /^[0-9a-f]{64}$/
    );
    const expectedNativeRoot = requiredValue(
      "WCE_NATIVE_CORE_PRIVATE_ROOT_SHA256",
      /^[0-9a-f]{64}$/
    );
    const expectedNativeClientIdentifier = requiredValue(
      "WCE_NATIVE_CORE_CLIENT_SIGNING_IDENTIFIER",
      /^[A-Za-z0-9.-]+$/
    );
    const expectedNativeBrokerIdentifier = requiredValue(
      "WCE_NATIVE_CORE_BROKER_SIGNING_IDENTIFIER",
      /^[A-Za-z0-9.-]+$/
    );
    const expectedNativeHostIdentifier = requiredValue(
      "WCE_NATIVE_CORE_HOST_SIGNING_IDENTIFIER",
      /^[A-Za-z0-9.-]+$/
    );
    if (
      expectedNativeHostSigner !== expectedHostSigner ||
      expectedNativeHostIdentifier !== macosXkeyContract.hostSigningIdentifier ||
      nativeManifest.macosClientSignerSha256 !== expectedNativeClientSigner ||
      nativeManifest.macosBrokerSignerSha256 !== expectedNativeBrokerSigner ||
      nativeManifest.macosHostSignerSha256 !== expectedNativeHostSigner ||
      nativeManifest.macosPrivateRootSha256 !== expectedNativeRoot ||
      nativeManifest.macosClientSigningIdentifier !== expectedNativeClientIdentifier ||
      nativeManifest.macosBrokerSigningIdentifier !== expectedNativeBrokerIdentifier ||
      nativeManifest.macosHostSigningIdentifier !== expectedNativeHostIdentifier
    ) {
      throw new Error("Packaged macOS native-core identity does not match protected environment pins.");
    }
    const clientBefore = inspectCodeSignature(nativeClientPath);
    const brokerBefore = inspectCodeSignature(nativeBrokerPath);
    if (
      clientBefore.identifier !== expectedNativeClientIdentifier ||
      clientBefore.leafSha256 !== expectedNativeClientSigner ||
      brokerBefore.identifier !== expectedNativeBrokerIdentifier ||
      brokerBefore.leafSha256 !== expectedNativeBrokerSigner
    ) {
      throw new Error("Producer-signed macOS native-core identities do not match pins.");
    }
    const expectedIntegrityHash = requiredValue(
      "WCE_INTEGRITY_BINARY_SHA256",
      /^[0-9a-f]{64}$/
    );
    if (sha256File(integrityPath) !== expectedIntegrityHash) {
      throw new Error("Packaged export-integrity module does not match the protected artifact pin.");
    }
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
  const inheritedIgnoreRules = ignoreList(options.ignore);
  const preservedProducerPaths = new Set([
    databaseKeyHelperPath,
    nativeClientPath,
    nativeBrokerPath,
  ].map((filePath) => path.resolve(filePath)));
  const preservedHelperHash = sha256File(databaseKeyHelperPath);
  const preservedNativeClientHash = sha256File(nativeClientPath);
  const preservedNativeBrokerHash = sha256File(nativeBrokerPath);
  const preservedNativeManifestHash = sha256File(nativeManifestPath);
  await signAsync({
    ...options,
    ...(explicitIdentity ? { identity: explicitIdentity.identity } : {}),
    // @electron/osx-sign 1.3.3 drops array-valued ignore rules while validating
    // options. Keep one combined predicate so Producer signatures remain intact.
    ignore(filePath) {
      return preservedProducerPaths.has(path.resolve(filePath)) ||
        inheritedIgnoreRules.some((rule) => matchesIgnoreRule(filePath, rule));
    },
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
  process.stdout.write(`Completed controlled macOS signing: ${options.app}\n`);

  if (sha256File(databaseKeyHelperPath) !== preservedHelperHash) {
    throw new Error("macOS app signing modified the producer-signed database key helper.");
  }
  if (
    sha256File(nativeClientPath) !== preservedNativeClientHash ||
    sha256File(nativeBrokerPath) !== preservedNativeBrokerHash ||
    sha256File(nativeManifestPath) !== preservedNativeManifestHash
  ) {
    throw new Error("macOS app signing modified the producer native-core artifact.");
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
    const nativeClientAfter = inspectCodeSignature(nativeClientPath);
    const nativeBrokerAfter = inspectCodeSignature(nativeBrokerPath);
    const integrityAfter = inspectCodeSignature(integrityPath);
    if (
      nativeClientAfter.identifier !== nativeManifest.macosClientSigningIdentifier ||
      nativeClientAfter.leafSha256 !== expectedNativeClientSigner ||
      nativeBrokerAfter.identifier !== nativeManifest.macosBrokerSigningIdentifier ||
      nativeBrokerAfter.leafSha256 !== expectedNativeBrokerSigner ||
      integrityAfter.leafSha256 !== expectedHostSigner
    ) {
      throw new Error(
        "macOS app signing replaced a producer native-core identity or failed to bind the export-integrity module."
      );
    }
  }
};
