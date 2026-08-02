"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");

const {
  stageWindowsPrivatePkiEvidence,
} = require("../scripts/native-core-before-pack.cjs");

const {
  assertProducerArtifactIsNotResigned,
  invokePolicy,
  normalizeHex,
  resolveSigningAssurance,
  resolveSigningEnvironment,
  resolveTimestampUrl,
} = require("../scripts/windows-private-pki-sign.cjs");

function makeRootFixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-private-pki-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const certificate = path.join(root, "root.cer");
  fs.writeFileSync(certificate, "public certificate fixture");
  return certificate;
}

test("private-PKI signing environment contains no exportable key material", (t) => {
  const certificate = makeRootFixture(t);
  const resolved = resolveSigningEnvironment({
    WCE_WINDOWS_CLIENT_CERT_THUMBPRINT: "aa".repeat(20),
    WCE_WINDOWS_CLIENT_SIGNER_SHA256: "bb".repeat(32),
    WCE_WINDOWS_PRIVATE_ROOT_SHA256: "cc".repeat(32),
    WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH: certificate,
    WCE_RFC3161_TIMESTAMP_URL: "https://timestamp.example.test/rfc3161",
  });
  assert.equal(resolved.certificateThumbprint, "AA".repeat(20));
  assert.equal(resolved.expectedSignerSha256, "BB".repeat(32));
  assert.equal(resolved.expectedRootSha256, "CC".repeat(32));
  assert.equal(resolved.privateRootCertificatePath, certificate);
  assert.equal(resolved.signingAssurance, "tpm");
  assert.equal(Object.keys(resolved).some((name) => /password|private.?key|pfx/i.test(name)), false);
});

test("private-PKI signing requires an explicit opt-in for Software KSP", (t) => {
  const certificate = makeRootFixture(t);
  const resolved = resolveSigningEnvironment({
    WCE_WINDOWS_SIGNING_ASSURANCE: "software-ksp",
    WCE_WINDOWS_CLIENT_CERT_THUMBPRINT: "aa".repeat(20),
    WCE_WINDOWS_CLIENT_SIGNER_SHA256: "bb".repeat(32),
    WCE_WINDOWS_PRIVATE_ROOT_SHA256: "cc".repeat(32),
    WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH: certificate,
    WCE_RFC3161_TIMESTAMP_URL: "https://timestamp.example.test/rfc3161",
  });
  assert.equal(resolved.signingAssurance, "software-ksp");
  assert.equal(resolveSigningAssurance(undefined), "tpm");
  assert.throws(() => resolveSigningAssurance("software"), /tpm or software-ksp/);
});

test("private-PKI signing rejects malformed pins and timestamp credentials", (t) => {
  const certificate = makeRootFixture(t);
  assert.throws(() => normalizeHex("AA", 64, "pin"), /64 hexadecimal/);
  assert.throws(
    () => resolveTimestampUrl("https://user:secret@timestamp.example.test"),
    /must not contain credentials/
  );
  assert.throws(
    () =>
      resolveSigningEnvironment({
        WCE_WINDOWS_CLIENT_CERT_THUMBPRINT: "aa".repeat(20),
        WCE_WINDOWS_CLIENT_SIGNER_SHA256: "bb".repeat(32),
        WCE_WINDOWS_PRIVATE_ROOT_SHA256: "cc".repeat(32),
        WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH: certificate,
        WCE_RFC3161_TIMESTAMP_URL: "file:///timestamp",
      }),
    /absolute HTTP\(S\) URL/
  );
});

test("private-PKI signing hook never changes producer-owned native files", () => {
  assert.throws(
    () => assertProducerArtifactIsNotResigned("C:\\artifact\\wechatdb_client.dll"),
    /producer-owned/
  );
  assert.throws(
    () => assertProducerArtifactIsNotResigned("C:\\artifact\\wechatdb_broker.exe"),
    /producer-owned/
  );
  assert.doesNotThrow(() => assertProducerArtifactIsNotResigned("C:\\app\\wechat-backend.exe"));
});

test("policy invocation passes arguments without a command shell", () => {
  let observed = null;
  const output = invokePolicy(
    {
      Action: "Verify",
      Path: "C:\\package\\app.exe",
      ExpectedSignerSha256: "AA".repeat(32),
      powershellPath: "powershell-test.exe",
    },
    {
      env: {},
      spawn(command, args, options) {
        observed = { command, args, options };
        return { status: 0, stdout: "verified", stderr: "" };
      },
    }
  );
  assert.equal(output, "verified");
  assert.equal(observed.command, "powershell-test.exe");
  assert.equal(observed.options.shell, undefined);
  assert.ok(observed.args.includes("-NonInteractive"));
  assert.ok(observed.args.includes("C:\\package\\app.exe"));
});

test("private-PKI policy completes the untrusted chain without installing trust", (t) => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "scripts", "windows-private-pki.ps1"),
    "utf8"
  );
  const certificate = makeRootFixture(t);
  const rootSha256 = crypto
    .createHash("sha256")
    .update(fs.readFileSync(certificate))
    .digest("hex")
    .toUpperCase();
  const signingDir = path.join(path.dirname(certificate), "staged-signing");
  stageWindowsPrivatePkiEvidence({
    env: {
      WCE_WINDOWS_PRIVATE_ROOT_CERT_PATH: certificate,
      WCE_WINDOWS_PRIVATE_ROOT_SHA256: rootSha256,
    },
    manifest: {
      windowsSignerTrustMode: "private-pki",
      windowsPrivateRootSha256: rootSha256,
    },
    signingDir,
  });
  const packagedSource = fs.readFileSync(
    path.join(signingDir, "windows-private-pki.ps1"),
    "utf8"
  );
  assert.equal(packagedSource, source);
  assert.match(source, /\[ValidateSet\('tpm', 'software-ksp'\)\]/);
  assert.match(source, /\[string\]\$SigningAssurance\s*=\s*'tpm'/);
  assert.match(source, /Microsoft Platform Crypto Provider/);
  assert.match(source, /Microsoft Software Key Storage Provider/);
  assert.match(source, /keyAssurance\s*=\s*\$signingIdentity\.Assurance/);
  assert.match(source, /Cert:\\CurrentUser\\CA/);
  assert.ok(source.includes("issuerStore = 'CurrentUser\\CA'"));
  assert.ok(!source.includes("issuerStore = 'CurrentUser\\\\CA'"));
  assert.match(source, /Add-PrivatePkiIssuerCertificate/);
  assert.match(source, /finally\s*\{[\s\S]*Remove-PrivatePkiIssuerCertificate/);
  assert.match(source, /Invoke-VerifiedTimestampedSign/);
  assert.match(source, /Local\\LifeArchiveProject\.WDA\.PrivatePki\.Signing\.v1/);
  assert.match(source, /WaitOne\(\[TimeSpan\]::FromMinutes\(5\)\)/);
  assert.match(source, /ReleaseMutex\(\)/);
  assert.match(source, /Invoke-FreshWinVerifyTrust/);
  assert.match(source, /-Action', 'TrustProbe'/);
  assert.match(source, /\.wda-unsigned/);
  assert.match(source, /\.wda-signing/);
  assert.match(source, /\[string\[\]\]\$Arguments\.Clone\(\)/);
  assert.match(source, /copyAttempt\s*=\s*1;\s*\$copyAttempt\s*-le\s*20/);
  assert.match(source, /MaximumAttempts\s*=\s*5/);
  assert.match(source, /Cert:\\CurrentUser\\Root/);
  assert.match(source, /Cert:\\CurrentUser\\TrustedPublisher/);
  assert.doesNotMatch(source, /Import-Certificate[\s\S]{0,160}Cert:\\CurrentUser\\Root/);
});
