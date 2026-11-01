"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function extractCodeSigningCertificateChain(filePath, {
  spawnSyncImpl = spawnSync,
  codesignPath = "/usr/bin/codesign",
} = {}) {
  const targetPath = path.resolve(filePath);
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "wda-codesign-cert-"));
  try {
    const result = spawnSyncImpl(
      codesignPath,
      ["--display", "--extract-certificates", targetPath],
      { cwd: tempDir, encoding: "utf8", stdio: "pipe" }
    );
    if (result.error) throw result.error;
    if ((result.status ?? 1) !== 0) {
      const output = `${result.stdout || ""}${result.stderr || ""}`;
      throw new Error(
        `${codesignPath} certificate extraction failed (${result.status})` +
        `${output ? `:\n${output}` : ""}`
      );
    }

    const certificates = [];
    for (let index = 0; ; index += 1) {
      const certificatePath = path.join(tempDir, `codesign${index}`);
      if (!fs.existsSync(certificatePath)) break;
      const stat = fs.lstatSync(certificatePath);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0) {
        throw new Error(`Invalid extracted code-signing certificate: codesign${index}`);
      }
      certificates.push(fs.readFileSync(certificatePath));
    }
    if (certificates.length === 0) {
      throw new Error(`Missing extracted code-signing leaf certificate: ${targetPath}`);
    }
    return certificates;
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function extractCodeSigningLeafCertificate(filePath, options) {
  return extractCodeSigningCertificateChain(filePath, options)[0];
}

module.exports = {
  extractCodeSigningCertificateChain,
  extractCodeSigningLeafCertificate,
};
