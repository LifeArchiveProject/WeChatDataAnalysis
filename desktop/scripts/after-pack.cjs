"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", stdio: "pipe" });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    throw new Error(
      `${command} ${args.join(" ")} failed (${result.status})${details ? `:\n${details}` : ""}`
    );
  }
}

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") return;

  const appName = `${context.packager.appInfo.productFilename}.app`;
  const appPath = path.join(context.appOutDir, appName);
  const entitlements = path.join(context.packager.projectDir, "entitlements.mac.plist");
  if (!fs.existsSync(appPath)) throw new Error(`Packaged macOS app not found: ${appPath}`);
  if (!fs.existsSync(entitlements)) throw new Error(`macOS entitlements not found: ${entitlements}`);

  if (process.env.MACOS_DISTRIBUTION_BUILD === "1") {
    const mode = String(process.env.WCE_MACOS_SIGNING_MODE || "").trim().toLowerCase();
    if (mode === "self-signed") {
      for (const name of [
        "WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY",
        "WCE_MACOS_WCDA_HOST_SIGNER_SHA256",
        "WCE_MACOS_KEY_HELPER_SIGNER_SHA256",
      ]) {
        if (!String(process.env[name] || "").trim()) {
          throw new Error(`Missing required self-signed macOS environment variable: ${name}`);
        }
      }
      for (const name of ["APPLE_ID", "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID"]) {
        if (String(process.env[name] || "").trim()) {
          throw new Error(`Self-signed macOS builds must not configure notarization: ${name}`);
        }
      }
      process.stdout.write(`Persistent self-signed identity will seal macOS application bundle: ${appPath}\n`);
      return;
    }
    if (mode !== "developer-id") {
      throw new Error("WCE_MACOS_SIGNING_MODE must be self-signed or developer-id for distribution builds.");
    }
    for (const name of ["CSC_LINK", "CSC_KEY_PASSWORD", "APPLE_ID", "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID"]) {
      if (!String(process.env[name] || "").trim()) throw new Error(`Missing required macOS distribution environment variable: ${name}`);
    }
    process.stdout.write(`Developer ID signing will seal macOS application bundle: ${appPath}\n`);
    return;
  }

  // Ordinary CI intentionally has no Developer ID. Seal the complete bundle so
  // its archived resources are still verifiable; release builds take the
  // Developer ID path above and are signed by electron-builder afterwards.
  run("codesign", [
    "--force",
    "--deep",
    "--sign",
    "-",
    "--options",
    "runtime",
    "--entitlements",
    entitlements,
    appPath,
  ]);
  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  process.stdout.write(`Ad-hoc sealed macOS application bundle: ${appPath}\n`);
};
