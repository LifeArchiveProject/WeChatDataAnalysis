"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..", "..");
const workflowPath = path.join(
  repoRoot,
  ".github",
  "workflows",
  "macos-source-runtime-consumer.yml"
);

test("public macOS consumer workflow has no private Producer or secret dependency", () => {
  const source = fs.readFileSync(workflowPath, "utf8");

  assert.doesNotMatch(source, /2977094657\/WCDB|WCE_MACOS_PRODUCER_READ_TOKEN|secrets\./);
  assert.match(
    source,
    /env -u GH_TOKEN -u GITHUB_TOKEN git[\s\S]*clone --depth 1[\s\S]*LifeArchiveProject\/WeChatDataAnalysis\.git/
  );
  assert.match(source, /env -u GH_TOKEN -u GITHUB_TOKEN node/);
  assert.match(source, /python3 -m venv/);
  assert.match(source, /result\.reason !== "downloaded"/);
  assert.match(source, /result\.reason !== "verified-cache"/);
});

test("consumer workflow validates all three runtime components", () => {
  const source = fs.readFileSync(workflowPath, "utf8");

  assert.match(source, /WCE_NATIVE_CORE_SOURCE_DIR/);
  assert.match(source, /WECHAT_TOOL_MACOS_DB_KEY_BUNDLE/);
  assert.match(source, /WCE_INTEGRITY_NATIVE_PATH/);
  assert.match(source, /codesign --verify --strict/);
  assert.match(source, /_required_native_core_build_manifest/);
  assert.match(source, /configure_native_core_entrypoint/);
  assert.match(source, /WECHAT_TOOL_NATIVE_CORE_LIBRARY/);
  assert.match(source, /WECHAT_TOOL_NATIVE_CORE_BROKER/);
  assert.match(source, /validate_macos_db_key_bundle/);
});
