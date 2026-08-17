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

test("macOS certificate extraction uses codesign's fixed filenames in an isolated cwd", () => {
  const {
    extractCodeSigningCertificateChain,
  } = require("../scripts/macos-codesign-certificates.cjs");
  let extractionCwd = "";
  const targetPath = path.join(desktopRoot, "fixture.app");
  const certificates = extractCodeSigningCertificateChain(targetPath, {
    spawnSyncImpl(command, args, options) {
      assert.equal(command, "/usr/bin/codesign");
      assert.deepEqual(args, ["--display", "--extract-certificates", targetPath]);
      assert.ok(path.isAbsolute(options.cwd));
      assert.ok(fs.statSync(options.cwd).isDirectory());
      extractionCwd = options.cwd;
      fs.writeFileSync(path.join(options.cwd, "codesign0"), "leaf-certificate");
      fs.writeFileSync(path.join(options.cwd, "codesign1"), "root-certificate");
      return { status: 0, stdout: "", stderr: "" };
    },
  });

  assert.deepEqual(certificates, [
    Buffer.from("leaf-certificate"),
    Buffer.from("root-certificate"),
  ]);
  assert.equal(fs.existsSync(extractionCwd), false);

  for (const scriptName of [
    "macos-xkey-packaging.cjs",
    "macos-native-core-packaging.cjs",
    "sign-macos.cjs",
    "after-sign.cjs",
    "macos-package-verifier.cjs",
  ]) {
    const script = fs.readFileSync(path.join(desktopRoot, "scripts", scriptName), "utf8");
    assert.match(script, /extractCodeSigningLeafCertificate/);
    assert.doesNotMatch(script, /--extract-certificates/);
  }
});

test("macOS signing preserves the producer helper and pins the direct backend parent", () => {
  assert.match(source, /WCE_MACOS_KEY_HELPER_SIGNER_SHA256/);
  assert.match(source, /WCE_MACOS_WCDA_HOST_SIGNER_SHA256/);
  assert.match(source, /preservedProducerPaths\.has\(path\.resolve\(filePath\)\)/);
  assert.match(source, /inheritedIgnoreRules\.some/);
  assert.doesNotMatch(source, /ignore:\s*\[/);
  assert.match(source, /--identifier/);
  assert.match(source, /requirements: backendRequirement/);
  assert.match(afterSign, /`-r\$\{appRequirement\}`/);
  assert.match(source, /certificate leaf = H/);
  assert.doesNotMatch(source, /anchor trusted/);
  assert.match(source, /hostSigningIdentifier/);
  assert.match(source, /Signed backend identity does not match the helper caller pin/);
  assert.match(source, /app signing replaced the producer helper identity/);
  assert.match(source, /libwechatdb_client\.dylib/);
  assert.match(source, /preservedNativeClientHash/);
  assert.match(source, /preservedNativeBrokerHash/);
  assert.match(source, /WCE_NATIVE_CORE_HOST_SIGNER_SHA256/);
  assert.match(source, /app signing replaced a producer native-core identity/);
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
  assert.match(workflow, /workflow_call/);
  assert.match(workflow, /workflow_dispatch/);
  assert.match(workflow, /ref: \$\{\{ github\.sha \}\}/);
  assert.match(workflow, /refs\/heads\/main\)/);
  assert.match(workflow, /refs\/tags\/v\*\)/);
  assert.match(workflow, /git merge-base --is-ancestor "\$WORKFLOW_REF" origin\/main/);
  assert.doesNotMatch(workflow, /git fetch --no-tags origin main/);
  assert.match(workflow, /PACKAGE_VERSION_INPUT: \$\{\{ inputs\.version \}\}/);
  assert.match(workflow, /tag_version="\$\{tag#v\}"/);
  assert.match(workflow, /printf 'PACKAGE_VERSION=%s\\n'/);
  assert.match(workflow, /npm version "\$PACKAGE_VERSION"/);
  assert.match(workflow, /name: release-macos-arm64/);
  assert.match(workflow, /desktop\/dist\/\*\.dmg/);
  assert.match(workflow, /desktop\/dist\/\*\.zip/);
  assert.match(workflow, /desktop\/dist\/latest-mac\.yml/);
  assert.match(workflow, /environment: macos-private-pki-production/);
  assert.match(workflow, /WCE_MACOS_WCDA_HOST_P12_BASE64/);
  assert.match(workflow, /WCE_MACOS_SELF_SIGNED_ROOT_CERT_BASE64/);
  assert.match(workflow, /CSC_NAME: \$\{\{ vars\.WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY \}\}/);
  assert.match(workflow, /test "\$CSC_NAME" = "\$WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY"/);
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
  assert.match(workflow, /security default-keychain -d user -s "\$keychain"/);
  assert.match(workflow, /per-device software identity/);
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
  assert.match(workflow, /WCE_NATIVE_CORE_ARTIFACT_RUN_ID/);
  assert.match(workflow, /wechatdb-native-macos-arm64-production/);
  assert.match(workflow, /macos-native-core-packaging\.cjs/);
  assert.match(workflow, /WCE_NATIVE_CORE_PRIVATE_ROOT_SHA256/);
  assert.match(workflow, /WCE_INTEGRITY_ARTIFACT_SHA256/);
  assert.match(workflow, /WCE_MACOS_PRIVATE_ROOT_CERT_PATH/);
  assert.match(workflow, /macos-private-pki-root\.cer/);
  assert.match(workflow, /consumer-smoke-macos-arm64/);
  assert.match(workflow, /needs: build-macos-arm64/);
  assert.match(workflow, /macos-private-pki-runtime\.test\.cjs/);
});

test("macOS private workflow verifies the pinned integrity Release before extraction", () => {
  assert.match(workflow, /release_tag="macos-integrity-\$WCE_INTEGRITY_BUILD_ID"/);
  assert.match(
    workflow,
    /asset_name="wce-integrity-macos-arm64-production-\$WCE_INTEGRITY_BUILD_ID\.zip"/
  );
  assert.match(workflow, /gh release download "\$release_tag"/);
  assert.match(workflow, /shasum -a 256 "\$archive"/);
  assert.match(workflow, /test "\$actual_sha256" = "\$WCE_INTEGRITY_ARTIFACT_SHA256"/);
  assert.match(workflow, /\/usr\/bin\/unzip -q "\$archive" -d "\$artifact_dir"/);
  assert.doesNotMatch(
    workflow,
    /gh run download "\$WCE_INTEGRITY_ARTIFACT_RUN_ID"/
  );

  const downloadIndex = workflow.indexOf('gh release download "$release_tag"');
  const hashIndex = workflow.indexOf('shasum -a 256 "$archive"');
  const extractIndex = workflow.indexOf('/usr/bin/unzip -q "$archive"');
  assert.ok(downloadIndex >= 0 && downloadIndex < hashIndex);
  assert.ok(hashIndex < extractIndex);
});

test("macOS private workflow retries transient Producer artifact downloads from a clean directory", () => {
  assert.match(workflow, /for attempt in 1 2 3/);
  assert.match(workflow, /rm -rf "\$artifact_dir"[\s\S]*gh run download/);
  assert.match(workflow, /if gh run download[\s\S]*downloaded=1[\s\S]*break/);
  assert.match(workflow, /test "\$downloaded" = 1/);
});
