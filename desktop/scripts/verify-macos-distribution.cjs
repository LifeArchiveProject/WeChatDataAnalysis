"use strict";

const { verifyMacosArtifacts } = require("./macos-package-verifier.cjs");

async function main() {
  if (process.arch !== "arm64") throw new Error(`Apple Silicon verifier required, got ${process.arch}`);
  await verifyMacosArtifacts({ distribution: true });
  process.stdout.write("macOS Developer ID distribution verification passed for ZIP and DMG\n");
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
