"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const policyScript = path.join(__dirname, "windows-private-pki.ps1");
const PRODUCER_OWNED_FILES = new Set(["wechatdb_client.dll", "wechatdb_broker.exe"]);

function normalizeHex(value, length, name) {
  const normalized = String(value || "").replace(/\s+/g, "").toUpperCase();
  if (!new RegExp(`^[0-9A-F]{${length}}$`).test(normalized)) {
    throw new Error(`${name} must contain exactly ${length} hexadecimal characters.`);
  }
  return normalized;
}

function resolveRootCertificate(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    throw new Error("WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH is required.");
  }
  const resolved = path.resolve(raw);
  let stat;
  try {
    stat = fs.statSync(resolved);
  } catch {
    throw new Error(`Private-PKI root certificate is not readable: ${resolved}`);
  }
  if (!stat.isFile() || stat.size <= 0) {
    throw new Error(`Private-PKI root certificate is not a non-empty file: ${resolved}`);
  }
  return resolved;
}

function resolveTimestampUrl(value) {
  let parsed;
  try {
    parsed = new URL(String(value || "").trim());
  } catch {
    throw new Error("WCE_RFC3161_TIMESTAMP_URL must be an absolute HTTP(S) URL.");
  }
  if (!new Set(["http:", "https:"]).has(parsed.protocol) || !parsed.hostname) {
    throw new Error("WCE_RFC3161_TIMESTAMP_URL must be an absolute HTTP(S) URL.");
  }
  if (parsed.username || parsed.password) {
    throw new Error("WCE_RFC3161_TIMESTAMP_URL must not contain credentials.");
  }
  return parsed.toString();
}

function resolveSigningAssurance(value) {
  const normalized = String(value || "tpm").trim().toLowerCase();
  if (!new Set(["tpm", "software-ksp"]).has(normalized)) {
    throw new Error("WCE_WINDOWS_SIGNING_ASSURANCE must be tpm or software-ksp.");
  }
  return normalized;
}

function resolveSigningEnvironment(env = process.env) {
  return {
    signingAssurance: resolveSigningAssurance(env.WCE_WINDOWS_SIGNING_ASSURANCE),
    certificateThumbprint: normalizeHex(
      env.WCE_WINDOWS_CLIENT_CERT_THUMBPRINT,
      40,
      "WCE_WINDOWS_CLIENT_CERT_THUMBPRINT"
    ),
    expectedSignerSha256: normalizeHex(
      env.WCE_NATIVE_CORE_CLIENT_SIGNER_SHA256 || env.WCE_WINDOWS_CLIENT_SIGNER_SHA256,
      64,
      "WCE_WINDOWS_CLIENT_SIGNER_SHA256"
    ),
    expectedRootSha256: normalizeHex(
      env.WCE_WINDOWS_PRIVATE_ROOT_SHA256,
      64,
      "WCE_WINDOWS_PRIVATE_ROOT_SHA256"
    ),
    privateRootCertificatePath: resolveRootCertificate(
      env.WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH
    ),
    timestampUrl: resolveTimestampUrl(env.WCE_RFC3161_TIMESTAMP_URL),
    signToolPath: String(env.WCE_SIGNTOOL_PATH || "").trim(),
    powershellPath: String(env.WCE_POWERSHELL_PATH || "powershell.exe").trim(),
  };
}

function invokePolicy(parameters, { env = process.env, spawn = spawnSync } = {}) {
  const powershellPath = String(parameters.powershellPath || env.WCE_POWERSHELL_PATH || "powershell.exe");
  const args = [
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    policyScript,
  ];
  for (const [name, value] of Object.entries(parameters)) {
    if (name === "powershellPath" || value === undefined || value === null || value === "") continue;
    args.push(`-${name}`, String(value));
  }
  const result = spawn(powershellPath, args, {
    cwd: path.resolve(__dirname, ".."),
    encoding: "utf8",
    env,
    maxBuffer: 8 * 1024 * 1024,
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    const details = [result.stderr, result.stdout].filter(Boolean).join("\n").trim();
    throw new Error(`Windows private-PKI policy failed${details ? `:\n${details}` : "."}`);
  }
  return String(result.stdout || "").trim();
}

function assertProducerArtifactIsNotResigned(filePath) {
  const name = path.basename(filePath).toLowerCase();
  if (PRODUCER_OWNED_FILES.has(name)) {
    throw new Error(`Refusing to alter producer-owned native artifact: ${name}`);
  }
}

async function sign(configuration) {
  if (process.platform !== "win32") {
    throw new Error("The Windows private-PKI signing hook can run only on Windows.");
  }
  if (String(configuration?.hash || "").toLowerCase() !== "sha256") {
    throw new Error("Windows private-PKI signing requires SHA-256 only.");
  }
  const filePath = path.resolve(String(configuration?.path || ""));
  assertProducerArtifactIsNotResigned(filePath);
  const signing = resolveSigningEnvironment();
  const output = invokePolicy({
    Action: "Sign",
    Path: filePath,
    CertificateThumbprint: signing.certificateThumbprint,
    ExpectedSignerSha256: signing.expectedSignerSha256,
    ExpectedRootSha256: signing.expectedRootSha256,
    PrivateRootCertificatePath: signing.privateRootCertificatePath,
    TimestampUrl: signing.timestampUrl,
    SignToolPath: signing.signToolPath,
    SigningAssurance: signing.signingAssurance,
    Description: String(configuration?.name || "WeChatDataAnalysis"),
    powershellPath: signing.powershellPath,
  });
  if (output) console.log(output);
}

function parseCli(arguments_) {
  const values = {};
  for (let index = 0; index < arguments_.length; index += 2) {
    const key = arguments_[index];
    const value = arguments_[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error("Expected --name value arguments.");
    }
    values[key.slice(2)] = value;
  }
  return values;
}

function verifyFile({ filePath, expectedSignerSha256, expectedRootSha256, rootCertificatePath }) {
  return invokePolicy({
    Action: "Verify",
    Path: path.resolve(filePath),
    ExpectedSignerSha256: normalizeHex(expectedSignerSha256, 64, "expected signer SHA-256"),
    ExpectedRootSha256: normalizeHex(expectedRootSha256, 64, "expected root SHA-256"),
    PrivateRootCertificatePath: resolveRootCertificate(rootCertificatePath),
  });
}

module.exports = {
  PRODUCER_OWNED_FILES,
  assertProducerArtifactIsNotResigned,
  invokePolicy,
  normalizeHex,
  resolveSigningAssurance,
  resolveSigningEnvironment,
  resolveTimestampUrl,
  sign,
  verifyFile,
};

if (require.main === module) {
  try {
    const [command, ...rest] = process.argv.slice(2);
    const values = parseCli(rest);
    if (command === "verify") {
      const output = verifyFile({
        filePath: values.path,
        expectedSignerSha256: values["signer-sha256"],
        expectedRootSha256: values["root-sha256"],
        rootCertificatePath: values["root-certificate"],
      });
      if (output) console.log(output);
    } else if (command === "preflight") {
      const signing = resolveSigningEnvironment();
      const output = invokePolicy({
        Action: "Preflight",
        CertificateThumbprint: signing.certificateThumbprint,
        ExpectedSignerSha256: signing.expectedSignerSha256,
        ExpectedRootSha256: signing.expectedRootSha256,
        PrivateRootCertificatePath: signing.privateRootCertificatePath,
        TimestampUrl: signing.timestampUrl,
        SignToolPath: signing.signToolPath,
        SigningAssurance: signing.signingAssurance,
        powershellPath: signing.powershellPath,
      });
      if (output) console.log(output);
    } else {
      throw new Error("Usage: windows-private-pki-sign.cjs verify|preflight ...");
    }
  } catch (error) {
    console.error(error?.message || error);
    process.exit(1);
  }
}
