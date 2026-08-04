const path = require("path");

const ENV_SOURCE_NATIVE_CORE_DIR = "WCE_NATIVE_CORE_SOURCE_DIR";

function resolveNativeCoreRuntimeDir({
  env = process.env,
  isPackaged = false,
  repoRoot,
  resourcesPath,
} = {}) {
  if (isPackaged) {
    return path.resolve(String(resourcesPath || ""), "backend", "native");
  }
  const explicit = String(env?.[ENV_SOURCE_NATIVE_CORE_DIR] || "").trim();
  if (explicit) return path.resolve(explicit);
  return path.resolve(String(repoRoot || ""), "src", "wechat_decrypt_tool", "native");
}

module.exports = {
  ENV_SOURCE_NATIVE_CORE_DIR,
  resolveNativeCoreRuntimeDir,
};
