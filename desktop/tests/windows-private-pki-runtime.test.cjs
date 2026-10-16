"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  POLICY_SHA256,
  configurePrivatePkiUpdateVerification,
  ensurePrivatePkiIssuerCached,
  resolvePrivatePkiRuntime,
  verifyPrivatePkiExecutable,
} = require("../src/windows-private-pki-runtime.cjs");

const policySource = path.join(__dirname, "..", "scripts", "windows-private-pki.ps1");

function makeRuntime(t) {
  const resources = fs.mkdtempSync(path.join(os.tmpdir(), "wda-private-pki-runtime-"));
  t.after(() => fs.rmSync(resources, { recursive: true, force: true }));
  const nativeRoot = path.join(resources, "backend", "native");
  const signingRoot = path.join(resources, "signing");
  fs.mkdirSync(nativeRoot, { recursive: true });
  fs.mkdirSync(signingRoot, { recursive: true });
  const rootCertificate = path.join(signingRoot, "windows-private-pki-root.cer");
  fs.writeFileSync(rootCertificate, "public root certificate fixture");
  const rootPin = crypto.createHash("sha256").update(fs.readFileSync(rootCertificate)).digest("hex");
  fs.copyFileSync(policySource, path.join(signingRoot, "windows-private-pki.ps1"));
  fs.writeFileSync(
    path.join(nativeRoot, "wechatdb_native_build.json"),
    JSON.stringify({
      schemaVersion: 2,
      buildId: "release-private-pki-2026.07.29",
      developmentBuild: false,
      codeSignatureEnforced: true,
      rootPublicKeyCompiled: true,
      testHooksEnabled: false,
      stagingPinnedSignerTrust: false,
      windowsSignerTrustMode: "private-pki",
      windowsClientSignerSha256: "11".repeat(32),
      windowsBrokerSignerSha256: "22".repeat(32),
      windowsPrivateRootSha256: rootPin,
    })
  );
  const installer = path.join(resources, "update.exe");
  fs.writeFileSync(installer, "installer fixture");
  return { installer, resources, rootCertificate };
}

test("packaged update verifier pins the public root, policy, and client leaf", (t) => {
  const fixture = makeRuntime(t);
  const identity = resolvePrivatePkiRuntime(fixture.resources);
  assert.equal(identity.expectedSignerSha256, "11".repeat(32).toUpperCase());
  assert.equal(
    crypto.createHash("sha256").update(fs.readFileSync(identity.policyScript)).digest("hex").toUpperCase(),
    POLICY_SHA256
  );
});

test("packaged update verifier invokes PowerShell without a command shell", (t) => {
  const fixture = makeRuntime(t);
  let observed = null;
  assert.equal(
    verifyPrivatePkiExecutable(fixture.installer, {
      resourcesPath: fixture.resources,
      powershellPath: "powershell-test.exe",
      spawn(command, args, options) {
        observed = { args, command, options };
        return { status: 0, stdout: "verified", stderr: "" };
      },
    }),
    true
  );
  assert.equal(observed.command, "powershell-test.exe");
  assert.equal(observed.options.shell, undefined);
  assert.ok(observed.args.includes("Verify"));
  assert.ok(observed.args.includes(fixture.installer));
});

test("packaged runtime caches only the pinned public issuer without trusting it", (t) => {
  const fixture = makeRuntime(t);
  const identity = resolvePrivatePkiRuntime(fixture.resources);
  let observed = null;
  const evidence = ensurePrivatePkiIssuerCached({
    resourcesPath: fixture.resources,
    powershellPath: "powershell-test.exe",
    spawn(command, args, options) {
      observed = { args, command, options };
      return {
        status: 0,
        stdout: JSON.stringify({
          rootSha256: identity.expectedRootSha256,
          issuerStore: "CurrentUser\\CA",
          newlyAdded: true,
          trustedRootInstalled: false,
        }),
        stderr: "",
      };
    },
  });
  assert.equal(evidence.newlyAdded, true);
  assert.equal(observed.command, "powershell-test.exe");
  assert.equal(observed.options.shell, undefined);
  assert.ok(observed.args.includes("CacheIssuer"));
  assert.ok(observed.args.includes(identity.rootCertificate));
});

test("packaged update verifier rejects modified root and policy evidence", (t) => {
  const fixture = makeRuntime(t);
  fs.appendFileSync(fixture.rootCertificate, "tampered");
  assert.throws(() => resolvePrivatePkiRuntime(fixture.resources), /root does not match/);

  const second = makeRuntime(t);
  fs.appendFileSync(path.join(second.resources, "signing", "windows-private-pki.ps1"), "# tampered");
  assert.throws(() => resolvePrivatePkiRuntime(second.resources), /policy was modified/);
});

test("electron-updater uses the private-PKI callback only in packaged Windows", async () => {
  const updater = {};
  assert.equal(
    configurePrivatePkiUpdateVerification(updater, { isPackaged: false, platform: "win32" }),
    false
  );
  assert.equal(
    configurePrivatePkiUpdateVerification(updater, {
      isPackaged: true,
      platform: "win32",
      resourcesPath: "C:\\resources",
      verifier(filePath, options) {
        assert.equal(filePath, "C:\\download\\Setup.exe");
        assert.equal(options.resourcesPath, "C:\\resources");
      },
    }),
    true
  );
  assert.equal(await updater.verifyUpdateCodeSignature([], "C:\\download\\Setup.exe"), null);

  configurePrivatePkiUpdateVerification(updater, {
    isPackaged: true,
    platform: "win32",
    verifier() {
      throw new Error("bad signer");
    },
  });
  assert.match(await updater.verifyUpdateCodeSignature([], "bad.exe"), /bad signer/);
});
