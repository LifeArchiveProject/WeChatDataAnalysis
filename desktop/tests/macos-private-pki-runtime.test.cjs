"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  ensureMacosPrivatePkiTrust,
  resolveMacosPrivatePkiRuntime,
} = require("../src/macos-private-pki-runtime.cjs");

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function makeRuntime(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-macos-private-pki-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const appPath = path.join(root, "WeChatDataAnalysis.app");
  const resourcesPath = path.join(appPath, "Contents", "Resources");
  const executablePath = path.join(appPath, "Contents", "MacOS", "WeChatDataAnalysis");
  const nativeRoot = path.join(resourcesPath, "backend", "native");
  const signingRoot = path.join(resourcesPath, "signing");
  const xkeyRoot = path.join(nativeRoot, "macos", "db-key");
  fs.mkdirSync(path.dirname(executablePath), { recursive: true });
  fs.mkdirSync(nativeRoot, { recursive: true });
  fs.mkdirSync(signingRoot, { recursive: true });
  fs.mkdirSync(xkeyRoot, { recursive: true });

  for (const filePath of [
    executablePath,
    path.join(resourcesPath, "backend", "wechat-backend"),
    path.join(nativeRoot, "libwechatdb_client.dylib"),
    path.join(nativeRoot, "wechatdb_broker"),
    path.join(nativeRoot, "libwce_integrity.dylib"),
    path.join(xkeyRoot, "wda_xkey_helper"),
  ]) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, path.basename(filePath));
  }

  const rootCertificate = path.join(signingRoot, "macos-private-pki-root.cer");
  fs.writeFileSync(rootCertificate, "public private-PKI root fixture");
  const rootPin = sha256(rootCertificate);
  fs.writeFileSync(
    path.join(nativeRoot, "wechatdb_native_build.json"),
    JSON.stringify({
      schemaVersion: 3,
      developmentBuild: false,
      stagingPinnedSignerTrust: false,
      macosSigningMode: "self-signed",
      macosSignerTrustMode: "private-pki",
      macosPrivateRootSha256: rootPin,
    })
  );
  return { appPath, executablePath, resourcesPath, rootCertificate, rootPin };
}

function fakeResult(status, stdout = "", stderr = "") {
  return { status, stdout, stderr, error: null };
}

test("packaged macOS runtime installs the pinned public root into user trust once", (t) => {
  const fixture = makeRuntime(t);
  const calls = [];
  let trusted = false;
  const evidence = ensureMacosPrivatePkiTrust({
    executablePath: fixture.executablePath,
    homeDirectory: path.join(path.dirname(fixture.appPath), "home"),
    platform: "darwin",
    resourcesPath: fixture.resourcesPath,
    spawn(command, args, options) {
      calls.push({ command, args, options });
      if (command === "/usr/bin/codesign") {
        return trusted
          ? fakeResult(0)
          : fakeResult(1, "", "CSSMERR_TP_NOT_TRUSTED\nIn architecture: arm64");
      }
      if (command === "/usr/bin/security" && args[0] === "default-keychain") {
        return fakeResult(0, '"/Users/example/Library/Keychains/login.keychain-db"\n');
      }
      if (command === "/usr/bin/security" && args[0] === "add-trusted-cert") {
        trusted = true;
        return fakeResult(0);
      }
      throw new Error(`Unexpected command: ${command} ${args.join(" ")}`);
    },
  });

  assert.equal(evidence.alreadyTrusted, false);
  assert.equal(evidence.newlyAdded, true);
  assert.equal(evidence.rootSha256, fixture.rootPin);
  const addCall = calls.find(
    (call) => call.command === "/usr/bin/security" && call.args[0] === "add-trusted-cert"
  );
  assert.ok(addCall);
  assert.deepEqual(addCall.args, [
    "add-trusted-cert",
    "-r",
    "trustRoot",
    "-p",
    "codeSign",
    "-k",
    "/Users/example/Library/Keychains/login.keychain-db",
    fixture.rootCertificate,
  ]);
  assert.equal(addCall.args.includes("-d"), false, "runtime trust must stay in the user domain");
});

test("packaged macOS runtime skips Keychain changes when signatures already verify", (t) => {
  const fixture = makeRuntime(t);
  const calls = [];
  const evidence = ensureMacosPrivatePkiTrust({
    executablePath: fixture.executablePath,
    platform: "darwin",
    resourcesPath: fixture.resourcesPath,
    spawn(command, args) {
      calls.push([command, args]);
      assert.equal(command, "/usr/bin/codesign");
      return fakeResult(0);
    },
  });

  assert.equal(evidence.alreadyTrusted, true);
  assert.equal(evidence.newlyAdded, false);
  assert.equal(calls.some(([command]) => command === "/usr/bin/security"), false);
});

test("packaged macOS runtime rejects a modified root before invoking Keychain", (t) => {
  const fixture = makeRuntime(t);
  fs.appendFileSync(fixture.rootCertificate, "tampered");
  assert.throws(
    () => resolveMacosPrivatePkiRuntime({
      executablePath: fixture.executablePath,
      resourcesPath: fixture.resourcesPath,
    }),
    /root does not match/i
  );
});

test("packaged macOS runtime names bundle files that break the code seal", (t) => {
  const fixture = makeRuntime(t);
  const envPath = path.join(fixture.resourcesPath, "backend", ".env");
  let securityCalled = false;
  assert.throws(
    () => ensureMacosPrivatePkiTrust({
      executablePath: fixture.executablePath,
      platform: "darwin",
      resourcesPath: fixture.resourcesPath,
      spawn(command) {
        if (command === "/usr/bin/security") securityCalled = true;
        return fakeResult(1, "", `a sealed resource is missing or invalid\nfile added: ${envPath}`);
      },
    }),
    (error) => {
      const message = String(error?.message || "");
      return (
        /signature verification failed/i.test(message) &&
        message.includes(envPath) &&
        message.includes("删除后重新打开应用即可恢复")
      );
    }
  );
  assert.equal(securityCalled, false);
});

test("packaged macOS runtime never treats a damaged signature as a trust bootstrap", (t) => {
  const fixture = makeRuntime(t);
  let securityCalled = false;
  assert.throws(
    () => ensureMacosPrivatePkiTrust({
      executablePath: fixture.executablePath,
      platform: "darwin",
      resourcesPath: fixture.resourcesPath,
      spawn(command) {
        if (command === "/usr/bin/security") securityCalled = true;
        return fakeResult(1, "", "code object is not signed at all");
      },
    }),
    /signature verification failed/i
  );
  assert.equal(securityCalled, false);
});
