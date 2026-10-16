"use strict";

const { spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const SHA256_PATTERN = /^[0-9a-f]{64}$/i;
const ROOT_CERTIFICATE_NAME = "macos-private-pki-root.cer";

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function requireRegularFile(filePath, label) {
  let stat;
  try {
    stat = fs.lstatSync(filePath);
  } catch {
    throw new Error(`Missing ${label}: ${filePath}`);
  }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0) {
    throw new Error(`Missing ${label}: ${filePath}`);
  }
  return filePath;
}

function resolveAppBundle(executablePath) {
  const executable = path.resolve(executablePath);
  const macosDirectory = path.dirname(executable);
  const contentsDirectory = path.dirname(macosDirectory);
  const appBundle = path.dirname(contentsDirectory);
  if (
    path.basename(macosDirectory) !== "MacOS" ||
    path.basename(contentsDirectory) !== "Contents" ||
    !path.basename(appBundle).endsWith(".app")
  ) {
    throw new Error(`Unable to resolve the packaged macOS app bundle from: ${executable}`);
  }
  let stat;
  try {
    stat = fs.lstatSync(appBundle);
  } catch {
    throw new Error(`Missing packaged macOS app bundle: ${appBundle}`);
  }
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`Invalid packaged macOS app bundle: ${appBundle}`);
  }
  return appBundle;
}

function readNativeManifest(manifestPath) {
  requireRegularFile(manifestPath, "native production manifest");
  if (fs.statSync(manifestPath).size > 16 * 1024) {
    throw new Error("Invalid native production manifest: file is too large.");
  }
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    throw new Error(`Invalid native production manifest: ${error.message}`);
  }
  const rootPin = String(manifest?.macosPrivateRootSha256 || "").trim().toLowerCase();
  if (
    manifest?.developmentBuild !== false ||
    manifest?.stagingPinnedSignerTrust !== false ||
    manifest?.macosSigningMode !== "self-signed" ||
    manifest?.macosSignerTrustMode !== "private-pki" ||
    !SHA256_PATTERN.test(rootPin) ||
    /^0{64}$/.test(rootPin)
  ) {
    throw new Error("Native manifest does not declare an approved macOS private-PKI identity.");
  }
  return { manifest, rootPin };
}

function resolveMacosPrivatePkiRuntime({ resourcesPath, executablePath = process.execPath } = {}) {
  const resources = path.resolve(resourcesPath);
  const appBundle = resolveAppBundle(executablePath);
  const backendRoot = path.join(resources, "backend");
  const nativeRoot = path.join(backendRoot, "native");
  const manifestPath = path.join(nativeRoot, "wechatdb_native_build.json");
  const { manifest, rootPin } = readNativeManifest(manifestPath);
  const rootCertificate = requireRegularFile(
    path.join(resources, "signing", ROOT_CERTIFICATE_NAME),
    "packaged macOS private-PKI root certificate"
  );
  const actualRoot = sha256File(rootCertificate);
  if (actualRoot !== rootPin) {
    throw new Error("Packaged macOS private-PKI root does not match the native manifest pin.");
  }

  const signedTargets = [
    { deep: true, label: "application", path: appBundle },
    {
      deep: false,
      label: "application executable",
      path: requireRegularFile(executablePath, "packaged application executable"),
    },
    {
      deep: false,
      label: "backend",
      path: requireRegularFile(path.join(backendRoot, "wechat-backend"), "packaged backend"),
    },
    {
      deep: false,
      label: "native client",
      path: requireRegularFile(path.join(nativeRoot, "libwechatdb_client.dylib"), "native client"),
    },
    {
      deep: false,
      label: "native broker",
      path: requireRegularFile(path.join(nativeRoot, "wechatdb_broker"), "native broker"),
    },
    {
      deep: false,
      label: "integrity module",
      path: requireRegularFile(path.join(nativeRoot, "libwce_integrity.dylib"), "integrity module"),
    },
    {
      deep: false,
      label: "database-key helper",
      path: requireRegularFile(
        path.join(nativeRoot, "macos", "db-key", "wda_xkey_helper"),
        "database-key helper"
      ),
    },
  ];
  return {
    appBundle,
    manifest,
    manifestPath,
    rootCertificate,
    rootSha256: actualRoot,
    signedTargets,
  };
}

function commandResult(spawn, command, args) {
  const result = spawn(command, args, {
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
  });
  if (result?.error) throw result.error;
  return {
    status: result?.status ?? 1,
    output: `${result?.stdout || ""}${result?.stderr || ""}`.trim(),
  };
}

function verifySignedTargets(identity, { spawn = spawnSync } = {}) {
  const failures = [];
  for (const target of identity.signedTargets) {
    const args = ["--verify"];
    if (target.deep) args.push("--deep");
    args.push("--strict", "--verbose=2", target.path);
    const result = commandResult(spawn, "/usr/bin/codesign", args);
    if (result.status !== 0) failures.push({ ...target, output: result.output, status: result.status });
  }
  return failures;
}

function isUntrustedChainFailure(failure) {
  return /CSSMERR_TP_NOT_TRUSTED|errSecNotTrusted|not trusted|unable to build (?:certificate )?chain/i.test(
    String(failure?.output || "")
  );
}

function summarizeFailure(failure) {
  const detail = String(failure?.output || "").replace(/\s+/g, " ").trim();
  return `${failure?.label || "target"}${detail ? `: ${detail.slice(0, 600)}` : ""}`;
}

function extractSealViolationFiles(failure) {
  const files = [];
  const pattern = /file (?:added|missing|modified):\s*([^\n]+)/g;
  const output = String(failure?.output || "");
  let match;
  while ((match = pattern.exec(output)) && files.length < 5) {
    const filePath = match[1].trim();
    if (filePath && !files.includes(filePath)) files.push(filePath);
  }
  return files;
}

function resolveUserDefaultKeychain({ spawn = spawnSync, homeDirectory = os.homedir() } = {}) {
  const result = commandResult(spawn, "/usr/bin/security", ["default-keychain", "-d", "user"]);
  if (result.status === 0) {
    let keychain = result.output.replace(/^\s*["']|["']\s*$/g, "").trim();
    if (keychain.startsWith("~/")) keychain = path.join(homeDirectory, keychain.slice(2));
    if (keychain) return keychain;
  }
  return path.join(path.resolve(homeDirectory), "Library", "Keychains", "login.keychain-db");
}

function ensureMacosPrivatePkiTrust({
  executablePath = process.execPath,
  homeDirectory = os.homedir(),
  platform = process.platform,
  resourcesPath = process.resourcesPath,
  spawn = spawnSync,
} = {}) {
  if (platform !== "darwin") {
    throw new Error("macOS private-PKI trust bootstrap is available on macOS only.");
  }
  const identity = resolveMacosPrivatePkiRuntime({ executablePath, resourcesPath });
  const initialFailures = verifySignedTargets(identity, { spawn });
  if (initialFailures.length === 0) {
    return {
      alreadyTrusted: true,
      keychain: "",
      newlyAdded: false,
      rootSha256: identity.rootSha256,
      verifiedTargetCount: identity.signedTargets.length,
    };
  }
  const nonTrustFailure = initialFailures.find((failure) => !isUntrustedChainFailure(failure));
  if (nonTrustFailure) {
    const violations = extractSealViolationFiles(nonTrustFailure);
    const hint = violations.length
      ? ` 应用包内容与签名清单不一致：${violations.join("、")}。若这是残留的多余文件，删除后重新打开应用即可恢复；否则请重新安装应用。`
      : "";
    throw new Error(
      `macOS signature verification failed before trust bootstrap (${summarizeFailure(nonTrustFailure)}).${hint}`
    );
  }

  const keychain = resolveUserDefaultKeychain({ homeDirectory, spawn });
  const installResult = commandResult(spawn, "/usr/bin/security", [
    "add-trusted-cert",
    "-r",
    "trustRoot",
    "-p",
    "codeSign",
    "-k",
    keychain,
    identity.rootCertificate,
  ]);
  if (installResult.status !== 0) {
    const detail = installResult.output ? ` (${installResult.output.slice(0, 600)})` : "";
    throw new Error(
      `未能为当前 macOS 用户信任应用签名证书，请在系统授权提示中确认后重试${detail}`
    );
  }

  const finalFailures = verifySignedTargets(identity, { spawn });
  if (finalFailures.length > 0) {
    throw new Error(`macOS 私有签名证书已写入，但签名复核仍失败 (${summarizeFailure(finalFailures[0])})。`);
  }
  return {
    alreadyTrusted: false,
    keychain,
    newlyAdded: true,
    rootSha256: identity.rootSha256,
    verifiedTargetCount: identity.signedTargets.length,
  };
}

module.exports = {
  ROOT_CERTIFICATE_NAME,
  ensureMacosPrivatePkiTrust,
  resolveMacosPrivatePkiRuntime,
  resolveUserDefaultKeychain,
  sha256File,
  verifySignedTargets,
};
