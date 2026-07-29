"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function run(command, args, { capture = false } = {}) {
  const result = spawnSync(command, args, { encoding: "utf8", stdio: capture ? "pipe" : "inherit" });
  if (result.error) throw result.error;
  const output = `${result.stdout || ""}${result.stderr || ""}`;
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed (${result.status}):\n${output}`);
  return output;
}

module.exports = async function afterSign(context) {
  if (context.electronPlatformName !== "darwin" || process.env.MACOS_DISTRIBUTION_BUILD !== "1") return;

  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  if (!fs.existsSync(appPath)) throw new Error(`Signed macOS app not found: ${appPath}`);
  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const details = run("codesign", ["-dv", "--verbose=4", appPath], { capture: true });
  if (!/^Authority=Developer ID Application:/m.test(details) || /^Signature=adhoc$/m.test(details)) {
    throw new Error(`Release app is not signed with Developer ID Application:\n${details}`);
  }
  run("xcrun", ["stapler", "staple", "-v", appPath]);
  run("xcrun", ["stapler", "validate", "-v", appPath]);
};
