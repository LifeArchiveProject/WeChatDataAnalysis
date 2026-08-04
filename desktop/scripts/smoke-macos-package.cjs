"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { verifyAppBundle, withMacosArtifacts } = require("./macos-package-verifier.cjs");
const { contract: macosXkeyContract } = require("./macos-xkey-packaging.cjs");

const { validatePackagedBackend } = require("./native-core-before-pack.cjs");
const {
  ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
  ENV_NATIVE_CORE_MODE,
  applyNativeCoreRuntimePolicy,
} = require("../src/native-core-runtime.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const SUPPORTED_ARCHITECTURE = "arm64";
const PACKAGE_MINIMUM_MACOS_VERSION = "15.0";
const SYNTHETIC_IMAGE_SCAN_FLAG = "--synthetic-image-scan";
const runSyntheticImageScan = process.argv.slice(2).includes(SYNTHETIC_IMAGE_SCAN_FLAG);

function fail(message) {
  throw new Error(message);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
    ...options,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    fail(`${command} ${args.join(" ")} failed (${result.status})${details ? `:\n${details}` : ""}`);
  }
  return String(result.stdout || "") + String(result.stderr || "");
}

function requirePath(filePath, { executable = false } = {}) {
  assert.ok(fs.existsSync(filePath), `Missing packaged resource: ${filePath}`);
  const stat = fs.lstatSync(filePath);
  assert.ok(stat.isFile(), `Packaged resource is not a regular file: ${filePath}`);
  assert.equal(stat.isSymbolicLink(), false, `Packaged resource must not link outside the app: ${filePath}`);
  if (executable) fs.accessSync(filePath, fs.constants.X_OK);
}

function versionTuple(value) {
  return String(value)
    .split(".")
    .map((part) => Number.parseInt(part, 10) || 0);
}

function compareVersions(left, right) {
  const a = versionTuple(left);
  const b = versionTuple(right);
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const delta = (a[index] || 0) - (b[index] || 0);
    if (delta !== 0) return delta;
  }
  return 0;
}

function assertMinimumOSCompatible(filePath, packageMinimumOS) {
  const output = run("otool", ["-l", filePath], { capture: true });
  const versions = [...output.matchAll(/^\s*minos\s+([0-9.]+)\s*$/gm)].map((match) => match[1]);
  assert.ok(versions.length > 0, `Missing LC_BUILD_VERSION minos: ${filePath}`);
  for (const version of versions) {
    assert.ok(
      compareVersions(version, packageMinimumOS) <= 0,
      `${filePath} requires macOS ${version}, above package minimum ${packageMinimumOS}`
    );
  }
}

function assertArchitecture(filePath, architecture, { universal = false } = {}) {
  const output = run("lipo", ["-archs", filePath], { capture: true }).trim().split(/\s+/);
  assert.ok(output.includes(architecture), `${filePath} does not contain ${architecture}: ${output.join(" ")}`);
  if (universal) {
    assert.ok(output.includes("arm64") && output.includes("x86_64"), `${filePath} is not universal2`);
  }
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address && typeof address === "object" ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function requestJson(url, { method = "GET", headers = {}, body = null, timeoutMs = 2_000 } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body == null ? null : Buffer.from(JSON.stringify(body), "utf8");
    const req = http.request(url, {
      method,
      headers: {
        ...headers,
        ...(payload
          ? { "content-type": "application/json", "content-length": String(payload.length) }
          : {}),
      },
    }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let decoded = null;
        try {
          decoded = JSON.parse(text);
        } catch {}
        resolve({ statusCode: res.statusCode || 0, body: decoded, text });
      });
    });
    req.once("error", reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`Request timed out: ${url}`)));
    if (payload) req.write(payload);
    req.end();
  });
}

async function waitForJson(url, options = {}, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await requestJson(url, options);
      if (response.statusCode >= 200 && response.statusCode < 500 && response.body) return response;
      lastError = new Error(`HTTP ${response.statusCode}: ${response.text}`);
    } catch (err) {
      lastError = err;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
}

function startProcess(command, args, options) {
  const chunks = [];
  const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"], ...options });
  const collect = (chunk) => {
    chunks.push(Buffer.from(chunk));
    if (chunks.reduce((total, item) => total + item.length, 0) > 256 * 1024) chunks.shift();
  };
  child.stdout?.on("data", collect);
  child.stderr?.on("data", collect);
  child.output = () => Buffer.concat(chunks).toString("utf8");
  return child;
}

async function stopProcess(child) {
  if (!child || child.exitCode != null) return;
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {}
      resolve();
    }, 5_000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    try {
      child.kill("SIGTERM");
    } catch {
      clearTimeout(timer);
      resolve();
    }
  });
}

async function waitForProcessOutput(child, pattern, timeoutMs = 5_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const output = child.output();
    if (pattern.test(output)) return;
    if (child.exitCode != null || child.signalCode != null) {
      fail(`Synthetic image-key target exited before it was ready:\n${output}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  fail(`Synthetic image-key target did not become ready:\n${child.output()}`);
}

async function probePackagedImageScanner(imageHelper, tempRoot) {
  const sourcePath = path.join(tempRoot, "image-key-target.c");
  const targetPath = path.join(tempRoot, "image-key-target");
  fs.writeFileSync(sourcePath, `
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach-o/dyld.h>
#include <unistd.h>

#define IMAGE_KEY_MAPPING_ADDRESS ((mach_vm_address_t)0x1000000ULL)
#define IMAGE_KEY_MAPPING_SIZE 0x4000

int main(void) {
    uintptr_t image_base = (uintptr_t)_dyld_get_image_header(0);
    if (image_base <= (uintptr_t)IMAGE_KEY_MAPPING_ADDRESS) {
        fprintf(stderr, "synthetic image base is not above probe mapping: 0x%llx\\n",
                (unsigned long long)image_base);
        return 1;
    }

    mach_vm_address_t image_key_mapping = IMAGE_KEY_MAPPING_ADDRESS;
    kern_return_t allocation_result = mach_vm_allocate(
        mach_task_self(),
        &image_key_mapping,
        IMAGE_KEY_MAPPING_SIZE,
        VM_FLAGS_FIXED
    );
    if (allocation_result != KERN_SUCCESS) {
        fprintf(stderr, "mach_vm_allocate image-key probe failed: %d\\n", allocation_result);
        return 2;
    }
    if (image_key_mapping != IMAGE_KEY_MAPPING_ADDRESS) {
        fprintf(stderr, "unexpected image-key mapping: 0x%llx\\n", image_key_mapping);
        return 3;
    }

    memcpy((void *)(uintptr_t)image_key_mapping, "0123456789abcdef", 16);
    printf("ready mapping=0x%llx image=0x%llx\\n",
           image_key_mapping,
           (unsigned long long)image_base);
    fflush(stdout);
    for (;;) pause();
}
`, "utf8");
  run("xcrun", [
    "clang",
    "-arch",
    SUPPORTED_ARCHITECTURE,
    `-mmacosx-version-min=${PACKAGE_MINIMUM_MACOS_VERSION}`,
    "-O0",
    // Shrink PAGEZERO only for this throwaway target. The fixed page directly
    // after it becomes the first readable/writable region without relocating
    // the normal PIE image or colliding with macOS's dyld shared cache.
    "-Wl,-pagezero_size,0x1000000",
    sourcePath,
    "-o",
    targetPath,
  ], { capture: true });

  let targetProc = null;
  try {
    targetProc = startProcess(targetPath, [], { cwd: tempRoot, env: process.env });
    await waitForProcessOutput(
      targetProc,
      /(?:^|\n)ready mapping=0x[0-9a-f]+ image=0x[0-9a-f]+\n/i
    );
    assert.ok(Number(targetProc.pid) > 0, "synthetic image-key target has no PID");

    const expectedKey = "0123456789abcdef";
    const jpegBlock = Buffer.from("ffd8ffe000104a464946000101000001", "hex");
    const cipher = crypto.createCipheriv("aes-128-ecb", Buffer.from(expectedKey, "ascii"), null);
    cipher.setAutoPadding(false);
    const ciphertext = Buffer.concat([cipher.update(jpegBlock), cipher.final()]);
    const helperProbe = spawnSync(imageHelper, [String(targetProc.pid), ciphertext.toString("hex")], {
      encoding: "utf8",
      stdio: "pipe",
      // Match the production direct-helper budget. The first invocation on a
      // clean macOS VM also pays dyld and private-PKI validation cold-start cost.
      timeout: 30_000,
    });
    const helperOutput = `${helperProbe.stdout || ""}\n${helperProbe.stderr || ""}`;
    if (helperProbe.error) {
      throw new Error(
        `Packaged image helper failed or exceeded the 30-second production budget: ` +
        `${helperProbe.error.message}\n${helperOutput}`
      );
    }
    assert.equal(helperProbe.status, 0, helperOutput);
    assert.doesNotMatch(helperOutput, /dlopen failed|symbol not found/i);

    const responseLine = String(helperProbe.stdout || "")
      .split(/\r?\n/)
      .reverse()
      .find((line) => line.trim().startsWith("{"));
    assert.ok(responseLine, `image helper returned no JSON response:\n${helperOutput}`);
    const helperPayload = JSON.parse(responseLine);
    assert.equal(helperPayload.success, true, helperOutput);
    assert.match(String(helperPayload.aesKey || ""), /^[0-9a-f]{32}$/i);
    assert.equal(Buffer.from(helperPayload.aesKey, "hex").toString("ascii"), expectedKey);
  } finally {
    await stopProcess(targetProc);
  }
}

async function runPackagedRuntimeSmoke(appPath) {
  const contents = path.join(appPath, "Contents");
  const resources = path.join(contents, "Resources");
  const infoPlist = path.join(contents, "Info.plist");
  const electronExecutable = path.join(contents, "MacOS", path.basename(appPath, ".app"));
  const backendRoot = path.join(resources, "backend");
  const backend = path.join(backendRoot, "wechat-backend");
  const nativeRoot = path.join(backendRoot, "native");
  const nativeClient = path.join(nativeRoot, "libwechatdb_client.dylib");
  const nativeBroker = path.join(nativeRoot, "wechatdb_broker");
  const nativeManifest = path.join(nativeRoot, "wechatdb_native_build.json");
  const imageLibrary = path.join(nativeRoot, "macos", "universal", "libwx_key.dylib");
  const imageHelper = path.join(nativeRoot, "macos", "universal", "image_scan_helper");
  const xkeyRoot = path.join(nativeRoot, ...String(macosXkeyContract.bundleRelativePath).split("/"));
  const xkeyHelper = path.join(xkeyRoot, macosXkeyContract.helperFileName);
  const integrity = path.join(nativeRoot, "libwce_integrity.dylib");
  const ffmpeg = path.join(resources, "ffmpeg", "ffmpeg");

  for (const filePath of [
    electronExecutable,
    backend,
    nativeClient,
    nativeBroker,
    nativeManifest,
    imageLibrary,
    imageHelper,
    xkeyHelper,
    integrity,
    ffmpeg,
  ]) {
    requirePath(filePath, {
      executable: [electronExecutable, backend, nativeBroker, imageHelper, xkeyHelper, ffmpeg].includes(filePath),
    });
  }
  requirePath(path.join(resources, "backend", "THIRD_PARTY_NOTICES.md"));
  requirePath(path.join(nativeRoot, "macos", "WEFLOW_LICENSE.txt"));
  requirePath(path.join(resources, "ffmpeg", "LICENSE"));
  requirePath(path.join(resources, "ffmpeg", "ffmpeg.LICENSE"));
  for (const name of [
    macosXkeyContract.manifestFileName,
    macosXkeyContract.trustFileName,
    macosXkeyContract.checksumsFileName,
    macosXkeyContract.provenanceFileName,
    macosXkeyContract.thirdPartyNoticeFileName,
  ]) {
    requirePath(path.join(xkeyRoot, name));
  }
  const xkeyManifest = JSON.parse(
    fs.readFileSync(path.join(xkeyRoot, macosXkeyContract.manifestFileName), "utf8")
  );
  const fridaNotice = fs.readFileSync(path.join(xkeyRoot, macosXkeyContract.thirdPartyNoticeFileName));
  assert.equal(
    crypto.createHash("sha256").update(fridaNotice).digest("hex"),
    xkeyManifest.files[macosXkeyContract.thirdPartyNoticeFileName].sha256,
    "Packaged Frida license notice differs from the producer manifest"
  );

  const packageMinimumOS = run(
    "plutil",
    ["-extract", "LSMinimumSystemVersion", "raw", "-o", "-", infoPlist],
    { capture: true }
  ).trim();
  assert.equal(
    packageMinimumOS,
    PACKAGE_MINIMUM_MACOS_VERSION,
    "Info.plist must match the minimum version supported by bundled native resources"
  );

  for (const retiredPath of [
    path.join(nativeRoot, "macos", "arm64", "libwcdb_api.dylib"),
    path.join(nativeRoot, "macos", "universal", "libWCDB.dylib"),
    path.join(resources, "wcdb-sidecar.cjs"),
    path.join(resources, "app.asar.unpacked", "node_modules", "koffi"),
  ]) {
    assert.equal(fs.existsSync(retiredPath), false, `Retired WCDB runtime was packaged: ${retiredPath}`);
  }

  const packagedNative = validatePackagedBackend({ backendDir: backendRoot, platform: "darwin" });
  assert.equal(path.resolve(packagedNative.nativeDir), path.resolve(nativeRoot));

  const nativeCoreEnv = {};
  const nativeCorePolicy = applyNativeCoreRuntimePolicy(nativeCoreEnv, {
    isPackaged: true,
    nativeDir: nativeRoot,
    platform: "darwin",
  });
  assert.equal(nativeCorePolicy.artifactState, "production");
  assert.equal(nativeCorePolicy.manifest.buildId, packagedNative.manifest.buildId);
  assert.equal(nativeCoreEnv[ENV_NATIVE_CORE_MODE], "required");
  assert.equal(nativeCoreEnv[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], undefined);

  assertArchitecture(electronExecutable, "arm64");
  assertArchitecture(backend, "arm64");
  assertArchitecture(nativeClient, "arm64");
  assertArchitecture(nativeBroker, "arm64");
  assertArchitecture(integrity, "arm64");
  assertArchitecture(imageLibrary, "arm64", { universal: true });
  assertArchitecture(imageHelper, "arm64", { universal: true });
  assertArchitecture(xkeyHelper, "arm64", { universal: true });
  assertArchitecture(ffmpeg, "arm64");

  for (const filePath of [
    electronExecutable,
    backend,
    nativeClient,
    nativeBroker,
    imageLibrary,
    imageHelper,
    xkeyHelper,
    integrity,
    ffmpeg,
  ]) {
    assertMinimumOSCompatible(filePath, packageMinimumOS);
  }

  const ffmpegVersion = run(ffmpeg, ["-version"], { capture: true });
  assert.match(ffmpegVersion, /^ffmpeg version/m);

  const imageHelperProbe = spawnSync(imageHelper, ["2147483647", "0".repeat(32)], {
    encoding: "utf8",
    stdio: "pipe",
    timeout: 5_000,
  });
  assert.ifError(imageHelperProbe.error);
  const imageHelperOutput = `${imageHelperProbe.stdout || ""}\n${imageHelperProbe.stderr || ""}`;
  assert.doesNotMatch(imageHelperOutput, /dlopen failed|symbol not found/i);
  assert.match(String(imageHelperProbe.stdout || ""), /"success":(?:true|false)/);

  run("codesign", ["--verify", "--strict", "--verbose=2", nativeClient]);
  run("codesign", ["--verify", "--strict", "--verbose=2", nativeBroker]);
  run("codesign", ["--verify", "--strict", "--verbose=2", integrity]);
  run("codesign", ["--verify", "--strict", "--verbose=2", xkeyHelper]);
  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const entitlements = run("codesign", ["-d", "--entitlements", "-", electronExecutable], { capture: true });
  assert.match(entitlements, /com\.apple\.security\.cs\.allow-jit/);
  const helperEntitlements = run("codesign", ["-d", "--entitlements", "-", imageHelper], { capture: true });
  assert.match(helperEntitlements, /com\.apple\.security\.cs\.debugger/);

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "wda-macos-smoke-"));
  let backendProc = null;
  try {
    if (runSyntheticImageScan) {
      await probePackagedImageScanner(imageHelper, tempRoot);
    }

    const backendPort = await getFreePort();
    const backendEnv = {
      ...process.env,
      ...nativeCoreEnv,
      WECHAT_TOOL_HOST: "127.0.0.1",
      WECHAT_TOOL_PORT: String(backendPort),
      WECHAT_TOOL_DATA_DIR: path.join(tempRoot, "data"),
      WECHAT_TOOL_OUTPUT_DIR: path.join(tempRoot, "output"),
      WECHAT_TOOL_UI_DIR: path.join(resources, "ui"),
      WECHAT_TOOL_NATIVE_CORE_LICENSE_URL: "https://license.invalid/v1/leases",
      WECHAT_TOOL_NATIVE_CORE_LICENSE_TOKEN: "package-smoke-no-network",
      WECHAT_TOOL_NATIVE_CORE_LICENSE_TIMEOUT_SECONDS: "1",
      WECHAT_TOOL_FFMPEG: ffmpeg,
    };
    for (const name of [
      ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
      "WECHAT_TOOL_NATIVE_CORE_ALLOW_STAGING_BUILD_FOR_TESTS",
      "WECHAT_TOOL_NATIVE_CORE_LIBRARY",
      "WECHAT_TOOL_NATIVE_CORE_BROKER",
      "WECHAT_TOOL_NATIVE_CORE_ENDPOINT",
      "WECHAT_TOOL_NATIVE_CORE_TRUST_KEY_PATH",
      "WECHAT_TOOL_WCDB_API_DLL_PATH",
      "WECHAT_TOOL_WCDB_DLL_DIR",
      "WECHAT_TOOL_WCDB_RESOURCE_PATHS",
      "WECHAT_TOOL_WCDB_SIDECAR",
      "WECHAT_TOOL_WCDB_SIDECAR_HOST",
      "WECHAT_TOOL_WCDB_SIDECAR_PORT",
      "WECHAT_TOOL_WCDB_SIDECAR_TOKEN",
      "WECHAT_TOOL_WCDB_SIDECAR_URL",
      "WECHAT_TOOL_KOFFI_DIR",
    ]) {
      delete backendEnv[name];
    }
    backendProc = startProcess(backend, [], { cwd: path.dirname(backend), env: backendEnv });
    backendProc.once("exit", (code, signal) => {
      if (code && code !== 0) process.stderr.write(backendProc.output());
    });
    const health = await waitForJson(`http://127.0.0.1:${backendPort}/api/health`);
    assert.equal(health.statusCode, 200, health.text || backendProc.output());
    assert.equal(health.body?.status, "healthy");
    assert.equal(health.body?.service, "微信解密工具");
    const capabilities = await waitForJson(`http://127.0.0.1:${backendPort}/api/system/platform`);
    assert.equal(capabilities.statusCode, 200, capabilities.text || backendProc.output());
    assert.equal(capabilities.body?.platform, "macos");
    const capabilityEvidence = JSON.stringify(capabilities.body || {});
    assert.equal(
      capabilities.body?.database_key_extraction,
      true,
      `Packaged database-key capability is unavailable: ${capabilityEvidence}`
    );
    assert.equal(
      capabilities.body?.database_key_online_authorization_required,
      true,
      `Packaged database-key authorization policy is invalid: ${capabilityEvidence}`
    );
    assert.match(String(capabilities.body?.database_key_build_id || ""), /^[A-Za-z0-9._-]+$/);
  } finally {
    await stopProcess(backendProc);
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }

  // Runtime processes must never modify the signed application bundle.
  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  process.stdout.write(`macOS package smoke test passed: ${appPath}\n`);
}

async function main() {
  if (process.platform !== "darwin") fail("macOS package smoke test must run on macOS");
  if (process.arch !== SUPPORTED_ARCHITECTURE) {
    fail(`Apple Silicon runner required, got ${process.arch}`);
  }

  const explicitAppPath = String(
    process.argv.slice(2).find((arg) => arg !== SYNTHETIC_IMAGE_SCAN_FLAG) || ""
  ).trim();
  if (explicitAppPath) {
    const appPath = path.resolve(explicitAppPath);
    verifyAppBundle(appPath, { distribution: false, source: "explicit app bundle" });
    await runPackagedRuntimeSmoke(appPath);
    return;
  }

  await withMacosArtifacts({ distribution: false }, async ({ zipAppPath }) => {
    await runPackagedRuntimeSmoke(zipAppPath);
  });
}

main().catch((err) => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exitCode = 1;
});
