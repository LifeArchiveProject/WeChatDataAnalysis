const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const mainSource = fs.readFileSync(path.join(__dirname, "..", "src", "main.cjs"), "utf8");

test("pending output transactions are recovered in development and packaged modes", () => {
  const start = mainSource.indexOf("async function applyPendingOutputDirOnStartup()");
  const end = mainSource.indexOf("async function refreshRendererCacheForPackagedUi", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);

  const functionSource = mainSource.slice(start, end);
  assert.doesNotMatch(functionSource, /if \(!app\.isPackaged\) return/);
  assert.match(functionSource, /applying pending output dir/);
  assert.match(functionSource, /await applyOutputDirChange/);
});

test("packaged output changes reject install-directory targets", () => {
  assert.match(mainSource, /output 目录不能位于安装目录内/);
  assert.match(mainSource, /legacyPathOverlapsConfiguredOutput/);
});

test("read-only output IPC does not recreate a source during a pending transaction", () => {
  assert.match(
    mainSource,
    /if \(ensureExists && !outputDirChangeInProgress && !transactionPending\)/
  );
  assert.match(mainSource, /resolveOutputDir\(\{ ensureExists: !outputTransactionPending \}\)/);
  assert.match(mainSource, /output 目录迁移待恢复，暂时无法打开目录/);
});
