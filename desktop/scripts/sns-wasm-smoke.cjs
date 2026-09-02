"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function resolveSnsWasmFixture(nativeRoot) {
  const wasmRoot = path.join(path.resolve(nativeRoot), "weflow_wasm");
  const helper = path.join(wasmRoot, "weflow_wasm_keystream.js");
  const fixturePath = path.join(wasmRoot, "sns_image_fixture.json");
  for (const filePath of [
    helper,
    fixturePath,
    path.join(wasmRoot, "wasm_video_decode.js"),
    path.join(wasmRoot, "wasm_video_decode.wasm"),
  ]) {
    assert.ok(fs.statSync(filePath).isFile(), `Missing SNS WASM resource: ${filePath}`);
  }
  const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assert.match(String(fixture.key || ""), /^\d+$/);
  assert.ok(Number(fixture.size) > 0);
  return { fixture, fixturePath, helper };
}

function decodeAndVerifyFixture(keystream, fixture) {
  assert.equal(keystream.length, Number(fixture.size));
  assert.equal(
    crypto.createHash("sha256").update(keystream).digest("hex"),
    fixture.keystreamSha256,
    "SNS WASM keystream hash differs from the fixed fixture"
  );
  const encrypted = Buffer.from(String(fixture.encryptedBase64 || ""), "base64");
  assert.equal(encrypted.length, keystream.length);
  const plaintext = Buffer.alloc(encrypted.length);
  for (let index = 0; index < encrypted.length; index += 1) {
    plaintext[index] = encrypted[index] ^ keystream[index];
  }
  assert.equal(plaintext.subarray(0, 4).toString("hex"), fixture.plaintextMagicHex);
  assert.equal(plaintext[0], 0xff);
  assert.equal(plaintext[1], 0xd8);
  assert.equal(
    crypto.createHash("sha256").update(plaintext).digest("hex"),
    fixture.plaintextSha256,
    "SNS fixture did not decrypt to the expected JPEG"
  );
  return plaintext;
}

function smokeElectronNodeWasm({ electronExecutable, nativeRoot, env = process.env }) {
  const { fixture, helper } = resolveSnsWasmFixture(nativeRoot);
  const result = spawnSync(
    path.resolve(electronExecutable),
    [helper, String(fixture.key), String(fixture.size)],
    {
      cwd: path.dirname(helper),
      encoding: "utf8",
      windowsHide: true,
      env: { ...env, ELECTRON_RUN_AS_NODE: "1" },
      timeout: 30_000,
    }
  );
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const keystream = Buffer.from(String(result.stdout || "").trim(), "base64");
  decodeAndVerifyFixture(keystream, fixture);
  return fixture.keystreamSha256;
}

function smokePackagedBackendWasm({ backendExecutable, electronExecutable, nativeRoot, env = process.env }) {
  const { fixture } = resolveSnsWasmFixture(nativeRoot);
  const smokeEnv = {
    ...env,
    PYTHONPATH: "",
    WECHAT_TOOL_NODE_EXECUTABLE: path.resolve(electronExecutable),
    WECHAT_TOOL_NODE_MODE: "electron-run-as-node",
  };
  delete smokeEnv.PYTHONHOME;
  delete smokeEnv.ELECTRON_RUN_AS_NODE;
  const result = spawnSync(path.resolve(backendExecutable), ["--smoke-sns-wasm"], {
    cwd: path.dirname(backendExecutable),
    encoding: "utf8",
    windowsHide: true,
    env: smokeEnv,
    timeout: 30_000,
  });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const line = String(result.stdout || "").trim().split(/\r?\n/).filter(Boolean).at(-1);
  const payload = JSON.parse(line || "{}");
  assert.equal(payload.frozen, true);
  assert.equal(payload.keystreamProvider, "electron-node-wasm");
  assert.equal(payload.mediaType, "image/jpeg");
  assert.equal(payload.plaintextSha256, fixture.plaintextSha256);
  assert.equal(payload.keystreamSha256, fixture.keystreamSha256);
  return payload;
}

module.exports = {
  decodeAndVerifyFixture,
  resolveSnsWasmFixture,
  smokeElectronNodeWasm,
  smokePackagedBackendWasm,
};
