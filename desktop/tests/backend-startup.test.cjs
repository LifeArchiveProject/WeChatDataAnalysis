const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS,
  PACKAGED_BACKEND_STARTUP_TIMEOUT_MS,
  isBackendHealthResponse,
  isWcdbSidecarHealthResponse,
  resolveBackendStartupTimeoutMs,
  shouldRetryBackendOnDifferentPort,
  shouldWaitForBackendReplacement,
} = require("../src/backend-startup.cjs");

test("health checks require the expected 200 JSON identity", () => {
  assert.equal(
    isBackendHealthResponse({
      statusCode: 200,
      body: JSON.stringify({ status: "healthy", service: "微信解密工具" }),
    }),
    true
  );
  assert.equal(isBackendHealthResponse({ statusCode: 404, body: "{}" }), false);
  assert.equal(isBackendHealthResponse({ statusCode: 200, body: "not-json" }), false);
  assert.equal(
    isBackendHealthResponse({ statusCode: 200, body: JSON.stringify({ status: "healthy" }) }),
    false
  );
  assert.equal(
    isWcdbSidecarHealthResponse({ statusCode: 200, body: JSON.stringify({ ok: true }) }),
    true
  );
  assert.equal(
    isWcdbSidecarHealthResponse({ statusCode: 401, body: JSON.stringify({ ok: true }) }),
    false
  );
});

test("packaged backend allows PyInstaller onefile cold starts longer than 30 seconds", () => {
  assert.equal(DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS, 30_000);
  assert.equal(PACKAGED_BACKEND_STARTUP_TIMEOUT_MS, 180_000);
  assert.equal(resolveBackendStartupTimeoutMs({ isPackaged: false }), 30_000);
  assert.equal(resolveBackendStartupTimeoutMs({ isPackaged: true }), 180_000);
});

test("backend startup timeout accepts a bounded support override", () => {
  assert.equal(
    resolveBackendStartupTimeoutMs({ isPackaged: true, envValue: "240000" }),
    240_000
  );
  assert.equal(
    resolveBackendStartupTimeoutMs({ isPackaged: true, envValue: "not-a-number" }),
    PACKAGED_BACKEND_STARTUP_TIMEOUT_MS
  );
  assert.equal(
    resolveBackendStartupTimeoutMs({ isPackaged: true, envValue: "999" }),
    PACKAGED_BACKEND_STARTUP_TIMEOUT_MS
  );
});

test("a slow live process does not trigger port walking even after binding its port", () => {
  assert.equal(
    shouldRetryBackendOnDifferentPort({ isPackaged: true, portAvailableAfterFailure: true }),
    false
  );
  assert.equal(
    shouldRetryBackendOnDifferentPort({ isPackaged: true, portAvailableAfterFailure: false }),
    true
  );
  assert.equal(
    shouldRetryBackendOnDifferentPort({
      isPackaged: true,
      portAvailableAfterFailure: false,
      backendProcessStillRunning: true,
    }),
    false
  );
  assert.equal(
    shouldRetryBackendOnDifferentPort({ isPackaged: false, portAvailableAfterFailure: false }),
    false
  );
});

test("only an explicit outer waiter tolerates the sidecar backend hand-off", () => {
  assert.equal(
    shouldWaitForBackendReplacement({
      allowBackendReplacement: true,
      sidecarRestartInProgress: true,
    }),
    true
  );
  assert.equal(
    shouldWaitForBackendReplacement({
      allowBackendReplacement: false,
      sidecarRestartInProgress: true,
    }),
    false
  );
  assert.equal(
    shouldWaitForBackendReplacement({
      allowBackendReplacement: true,
      sidecarRestartInProgress: false,
    }),
    false
  );
});
