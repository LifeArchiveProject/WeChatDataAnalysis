"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(desktopRoot, "scripts", "sign-macos.cjs"), "utf8");
const afterSign = fs.readFileSync(path.join(desktopRoot, "scripts", "after-sign.cjs"), "utf8");
const workflow = fs.readFileSync(
  path.resolve(desktopRoot, "..", ".github", "workflows", "macos-private-build.yml"),
  "utf8"
);

test("macOS signing preserves the producer helper and pins the direct backend parent", () => {
  assert.match(source, /WCE_MACOS_KEY_HELPER_SIGNER_SHA256/);
  assert.match(source, /WCE_MACOS_WCDA_HOST_SIGNER_SHA256/);
  assert.match(source, /path\.resolve\(filePath\).*path\.resolve\(databaseKeyHelperPath\)/s);
  assert.match(source, /--identifier/);
  assert.match(source, /requirements: backendRequirement/);
  assert.match(afterSign, /`-r\$\{appRequirement\}`/);
  assert.match(source, /certificate leaf = H/);
  assert.doesNotMatch(source, /anchor trusted/);
  assert.match(source, /hostSigningIdentifier/);
  assert.match(source, /Signed backend identity does not match the helper caller pin/);
  assert.match(source, /app signing replaced the producer helper identity/);
});

test("self-signed production mode disables unavailable Apple timestamps without allowing ad-hoc", () => {
  assert.match(source, /signingMode === "self-signed"/);
  assert.match(source, /timestamp: "none"/);
  assert.match(source, /WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY/);
  assert.match(source, /find-identity/);
  assert.doesNotMatch(source, /identity:\s*["']-["']/);
});

test("self-signed private workflow imports a persistent identity and never notarizes", () => {
  assert.match(afterSign, /WCE_MACOS_SIGNING_MODE/);
  assert.match(afterSign, /codesign.*--verify.*--deep.*--strict/s);
  assert.match(afterSign, /notarization and stapling are disabled/);
  assert.match(afterSign, /verifyDesignatedRequirement/);
  assert.match(afterSign, /normalized !== expected/);
  assert.match(afterSign, /`-R=identifier/);
  assert.match(workflow, /workflow_dispatch/);
  assert.match(workflow, /ref: \$\{\{ github\.sha \}\}/);
  assert.match(workflow, /test "\$WORKFLOW_REF" = "refs\/heads\/main"/);
  assert.doesNotMatch(workflow, /git fetch --no-tags origin main/);
  assert.match(workflow, /PACKAGE_VERSION: \$\{\{ inputs\.version \}\}/);
  assert.deepEqual(
    workflow.split(/\r?\n/).filter((line) => line.includes("${{ inputs.version }}")).map((line) => line.trim()),
    ["PACKAGE_VERSION: ${{ inputs.version }}", "name: WeChatDataAnalysis-macos-arm64-${{ inputs.version }}"]
  );
  assert.match(workflow, /npm version "\$PACKAGE_VERSION"/);
  assert.match(workflow, /environment: macos-private-pki-production/);
  assert.match(workflow, /WCE_MACOS_WCDA_HOST_P12_BASE64/);
  assert.match(workflow, /WCE_MACOS_SELF_SIGNED_ROOT_CERT_BASE64/);
  assert.match(workflow, /timeout-minutes: 5/);
  assert.match(workflow, /sudo -n security add-trusted-cert -d -r trustRoot -p codeSign/);
  assert.match(workflow, /-k \/Library\/Keychains\/System\.keychain/);
  assert.match(workflow, /disposable GitHub-hosted VM/);
  assert.match(workflow, /openssl pkcs12 -in "\$p12" -cacerts -nokeys/);
  assert.match(workflow, /cmp "\$RUNNER_TEMP\/wda-host-chain\.cer" "\$root_cert"/);
  assert.match(workflow, /openssl verify -CAfile "\$root_pem" "\$p12_leaf"/);
  assert.match(workflow, /Extended Key Usage/);
  assert.match(workflow, /actual_host_leaf_sha256/);
  assert.match(workflow, /security import/);
  assert.doesNotMatch(workflow, /security remove-trusted-cert/);
  assert.match(workflow, /security delete-keychain/);
  assert.doesNotMatch(workflow, /APPLE_ID|notarytool|stapler/);
});

test("macOS private workflow keeps the canonical Producer and WCDA certificate variable contract", () => {
  for (const name of [
    "WCE_MACOS_WCDA_HOST_P12_BASE64",
    "WCE_MACOS_WCDA_HOST_P12_PASSWORD",
    "WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY",
    "WCE_MACOS_KEY_HELPER_SIGNER_SHA256",
    "WCE_MACOS_WCDA_HOST_SIGNER_SHA256",
  ]) {
    assert.match(workflow, new RegExp(`\\b${name}\\b`), `${name} must remain part of the workflow contract`);
  }
  for (const retiredAlias of [
    "WCE_MACOS_HOST_P12_BASE64",
    "WCE_MACOS_HOST_P12_PASSWORD",
    "WCE_MACOS_HOST_SIGNING_IDENTITY",
    "WCE_MACOS_HELPER_SIGNER_SHA256",
    "WCE_MACOS_HOST_SIGNER_SHA256",
  ]) {
    assert.doesNotMatch(workflow, new RegExp(`\\b${retiredAlias}\\b`));
  }
});
