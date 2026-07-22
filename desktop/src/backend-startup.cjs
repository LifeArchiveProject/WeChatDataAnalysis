const DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS = 30_000;
// PyInstaller onefile extraction/imports are silent; captured cold starts have exceeded 90 seconds.
const PACKAGED_BACKEND_STARTUP_TIMEOUT_MS = 180_000;
const MIN_BACKEND_STARTUP_TIMEOUT_MS = 5_000;
const MAX_BACKEND_STARTUP_TIMEOUT_MS = 600_000;

function resolveBackendStartupTimeoutMs({ isPackaged = false, envValue } = {}) {
  const fallback = isPackaged
    ? PACKAGED_BACKEND_STARTUP_TIMEOUT_MS
    : DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS;
  const raw = String(envValue ?? "").trim();
  if (!raw) return fallback;

  const parsed = Number(raw);
  if (
    !Number.isInteger(parsed) ||
    parsed < MIN_BACKEND_STARTUP_TIMEOUT_MS ||
    parsed > MAX_BACKEND_STARTUP_TIMEOUT_MS
  ) {
    return fallback;
  }
  return parsed;
}

function shouldRetryBackendOnDifferentPort({
  isPackaged = false,
  portAvailableAfterFailure = true,
  backendProcessStillRunning = false,
} = {}) {
  return Boolean(
    isPackaged &&
      !backendProcessStillRunning &&
      portAvailableAfterFailure === false
  );
}

function shouldWaitForBackendReplacement({
  allowBackendReplacement = false,
  sidecarRestartInProgress = false,
} = {}) {
  return Boolean(allowBackendReplacement && sidecarRestartInProgress);
}

function parseHealthJson(response) {
  if (Number(response?.statusCode) !== 200) return null;
  try {
    const parsed = JSON.parse(String(response?.body || ""));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isBackendHealthResponse(response) {
  const payload = parseHealthJson(response);
  return payload?.status === "healthy" && payload?.service === "微信解密工具";
}

function isWcdbSidecarHealthResponse(response) {
  const payload = parseHealthJson(response);
  return payload?.ok === true;
}

module.exports = {
  DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS,
  PACKAGED_BACKEND_STARTUP_TIMEOUT_MS,
  isBackendHealthResponse,
  isWcdbSidecarHealthResponse,
  resolveBackendStartupTimeoutMs,
  shouldRetryBackendOnDifferentPort,
  shouldWaitForBackendReplacement,
};
