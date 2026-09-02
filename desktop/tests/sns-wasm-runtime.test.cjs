"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  resolveSnsWasmFixture,
  smokeElectronNodeWasm,
} = require("../scripts/sns-wasm-smoke.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "..");
const nativeRoot = path.join(repoRoot, "src", "wechat_decrypt_tool", "native");

test("npm Electron executable decrypts the fixed SNS JPEG fixture as Node", () => {
  const electronExecutable = require("electron");
  const expected = resolveSnsWasmFixture(nativeRoot).fixture.keystreamSha256;
  assert.equal(
    smokeElectronNodeWasm({ electronExecutable, nativeRoot }),
    expected,
  );
});

test("packaged backend smoke contract requires Electron run-as-node and WASM", () => {
  const source = fs.readFileSync(
    path.join(repoRoot, "src", "wechat_decrypt_tool", "backend_entry.py"),
    "utf8",
  );
  assert.match(source, /--smoke-sns-wasm/);
  assert.match(source, /weflow_decrypt_sns_image_bytes/);
  assert.match(source, /keystreamProvider/);

  const mediaSource = fs.readFileSync(
    path.join(repoRoot, "src", "wechat_decrypt_tool", "sns_media.py"),
    "utf8",
  );
  assert.match(mediaSource, /WECHAT_TOOL_NODE_EXECUTABLE/);
  assert.match(mediaSource, /WECHAT_TOOL_NODE_MODE/);
  assert.match(mediaSource, /helper_env\["ELECTRON_RUN_AS_NODE"\] = "1"/);
  assert.doesNotMatch(mediaSource, /from \.isaac64 import Isaac64/);
});
