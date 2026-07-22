"use strict";

const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const distRoot = path.join(desktopRoot, "dist");

function fail(message) {
  throw new Error(message);
}

function findPackagedApp() {
  const explicit = String(process.argv[2] || "").trim();
  if (explicit) return path.resolve(explicit);

  for (const entry of fs.readdirSync(distRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith("mac")) continue;
    const root = path.join(distRoot, entry.name);
    const appName = fs.readdirSync(root).find((name) => name.endsWith(".app"));
    if (appName) return path.join(root, appName);
  }
  fail(`No packaged .app found under ${distRoot}`);
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
  if (executable) fs.accessSync(filePath, fs.constants.X_OK);
}

function assertArchitecture(filePath, architecture, { universal = false } = {}) {
  const output = run("lipo", ["-archs", filePath], { capture: true }).trim().split(/\s+/);
  assert.ok(output.includes(architecture), `${filePath} does not contain ${architecture}: ${output.join(" ")}`);
  if (universal) {
    assert.ok(output.includes("arm64") && output.includes("x86_64"), `${filePath} is not universal2`);
  }
}

function createEncryptedSessionFixture(rootDir) {
  const koffi = require("koffi");
  const plainPath = path.join(rootDir, "plain-session.db");
  const encryptedPath = path.join(rootDir, "session.db");
  const sqlite = koffi.load("/usr/lib/libsqlite3.dylib");
  const sqliteOpen = sqlite.func("int sqlite3_open(const char* filename, _Out_ void** db)");
  const sqliteFileControl = sqlite.func(
    "int sqlite3_file_control(void* db, const char* dbName, int op, _Inout_ int* value)"
  );
  const sqliteExec = sqlite.func(
    "int sqlite3_exec(void* db, const char* sql, void* callback, void* context, _Out_ void** error)"
  );
  const sqliteFree = sqlite.func("void sqlite3_free(void* value)");
  const sqliteClose = sqlite.func("int sqlite3_close(void* db)");

  const db = [null];
  assert.equal(sqliteOpen(plainPath, db), 0, "failed to create the native WCDB smoke fixture");
  try {
    const reserveBytes = [80];
    assert.equal(
      sqliteFileControl(db[0], "main", 38, reserveBytes),
      0,
      "failed to configure SQLite reserve bytes"
    );

    const error = [null];
    const sql = `
      PRAGMA page_size=4096;
      CREATE TABLE SessionTable (
        username TEXT PRIMARY KEY,
        sort_timestamp INTEGER,
        last_timestamp INTEGER,
        summary TEXT,
        unread_count INTEGER,
        is_hidden INTEGER,
        draft TEXT,
        status INTEGER
      );
      INSERT INTO SessionTable VALUES (
        'wxid_friend', 1735689600, 1735689600, 'macOS WCDB smoke', 0, 0, '', 0
      );
    `;
    const rc = Number(sqliteExec(db[0], sql, null, null, error));
    try {
      const message = error[0] ? koffi.decode(error[0], "char", -1) : "";
      assert.equal(rc, 0, message || "failed to seed the native WCDB smoke fixture");
    } finally {
      if (error[0]) sqliteFree(error[0]);
    }
  } finally {
    sqliteClose(db[0]);
  }

  const pageSize = 4096;
  const saltSize = 16;
  const ivSize = 16;
  const hmacSize = 64;
  const reserveSize = ivSize + hmacSize;
  const plain = fs.readFileSync(plainPath);
  assert.equal(plain.length % pageSize, 0);
  assert.equal(plain.subarray(0, 16).toString("binary"), "SQLite format 3\0");
  assert.equal(plain[20], reserveSize);

  const keyMaterial = Buffer.alloc(32, 0x11);
  const salt = crypto.randomBytes(saltSize);
  const encryptionKey = crypto.pbkdf2Sync(keyMaterial, salt, 256000, 32, "sha512");
  const macSalt = Buffer.from(salt.map((byte) => byte ^ 0x3a));
  const macKey = crypto.pbkdf2Sync(encryptionKey, macSalt, 2, 32, "sha512");
  const encrypted = Buffer.alloc(plain.length);

  for (let pageOffset = 0, pageNumber = 1; pageOffset < plain.length; pageOffset += pageSize, pageNumber += 1) {
    const sourcePage = plain.subarray(pageOffset, pageOffset + pageSize);
    const targetPage = encrypted.subarray(pageOffset, pageOffset + pageSize);
    const payloadOffset = pageNumber === 1 ? saltSize : 0;
    const iv = crypto.randomBytes(ivSize);
    const cipher = crypto.createCipheriv("aes-256-cbc", encryptionKey, iv);
    cipher.setAutoPadding(false);
    const ciphertext = Buffer.concat([
      cipher.update(sourcePage.subarray(payloadOffset, pageSize - reserveSize)),
      cipher.final(),
    ]);

    if (pageNumber === 1) salt.copy(targetPage, 0);
    ciphertext.copy(targetPage, payloadOffset);
    iv.copy(targetPage, pageSize - reserveSize);

    const pageNumberBytes = Buffer.alloc(4);
    pageNumberBytes.writeUInt32LE(pageNumber);
    const digest = crypto
      .createHmac("sha512", macKey)
      .update(targetPage.subarray(payloadOffset, pageSize - hmacSize))
      .update(pageNumberBytes)
      .digest();
    digest.copy(targetPage, pageSize - hmacSize);
  }

  fs.writeFileSync(encryptedPath, encrypted);
  return { path: encryptedPath, key: keyMaterial.toString("hex") };
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

async function main() {
  if (process.platform !== "darwin") fail("macOS package smoke test must run on macOS");
  if (process.arch !== "arm64") fail(`Apple Silicon runner required, got ${process.arch}`);

  const appPath = findPackagedApp();
  const contents = path.join(appPath, "Contents");
  const resources = path.join(contents, "Resources");
  const electronExecutable = path.join(contents, "MacOS", path.basename(appPath, ".app"));
  const backend = path.join(resources, "backend", "wechat-backend");
  const nativeRoot = path.join(resources, "backend", "native");
  const wcdbApi = path.join(nativeRoot, "macos", "arm64", "libwcdb_api.dylib");
  const wcdb = path.join(nativeRoot, "macos", "universal", "libWCDB.dylib");
  const imageLibrary = path.join(nativeRoot, "macos", "universal", "libwx_key.dylib");
  const imageHelper = path.join(nativeRoot, "macos", "universal", "image_scan_helper");
  const integrity = path.join(nativeRoot, "libwce_integrity.dylib");
  const sidecar = path.join(resources, "wcdb-sidecar.cjs");
  const ffmpeg = path.join(resources, "ffmpeg", "ffmpeg");
  const koffiDir = path.join(resources, "app.asar.unpacked", "node_modules", "koffi");
  const koffiNative = path.join(koffiDir, "build", "koffi", "darwin_arm64", "koffi.node");

  for (const filePath of [electronExecutable, backend, wcdbApi, wcdb, imageLibrary, imageHelper, integrity, sidecar, ffmpeg, koffiNative]) {
    requirePath(filePath, { executable: [electronExecutable, backend, imageHelper, ffmpeg].includes(filePath) });
  }
  requirePath(path.join(resources, "backend", "THIRD_PARTY_NOTICES.md"));
  requirePath(path.join(nativeRoot, "macos", "WEFLOW_LICENSE.txt"));
  requirePath(path.join(resources, "ffmpeg", "LICENSE"));
  requirePath(path.join(resources, "ffmpeg", "ffmpeg.LICENSE"));

  assertArchitecture(electronExecutable, "arm64");
  assertArchitecture(backend, "arm64");
  assertArchitecture(wcdbApi, "arm64");
  assertArchitecture(integrity, "arm64");
  assertArchitecture(koffiNative, "arm64");
  assertArchitecture(wcdb, "arm64", { universal: true });
  assertArchitecture(imageLibrary, "arm64", { universal: true });
  assertArchitecture(imageHelper, "arm64", { universal: true });
  assertArchitecture(ffmpeg, "arm64");

  const ffmpegVersion = run(ffmpeg, ["-version"], { capture: true });
  assert.match(ffmpegVersion, /^ffmpeg version/m);

  const imageHelperProbe = spawnSync(imageHelper, [String(process.pid), "0".repeat(32)], {
    encoding: "utf8",
    stdio: "pipe",
  });
  const imageHelperOutput = `${imageHelperProbe.stdout || ""}\n${imageHelperProbe.stderr || ""}`;
  assert.doesNotMatch(imageHelperOutput, /dlopen failed|symbol not found/i);
  assert.match(String(imageHelperProbe.stdout || ""), /"success":(?:true|false)/);

  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const entitlements = run("codesign", ["-d", "--entitlements", "-", electronExecutable], { capture: true });
  assert.match(entitlements, /com\.apple\.security\.cs\.allow-jit/);

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "wda-macos-smoke-"));
  let backendProc = null;
  let sidecarProc = null;
  try {
    const backendPort = await getFreePort();
    const sidecarPort = await getFreePort();
    const sidecarToken = "package-smoke-token";
    const sidecarEnv = {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      WECHAT_TOOL_WCDB_SIDECAR_HOST: "127.0.0.1",
      WECHAT_TOOL_WCDB_SIDECAR_PORT: String(sidecarPort),
      WECHAT_TOOL_WCDB_SIDECAR_TOKEN: sidecarToken,
      WECHAT_TOOL_WCDB_API_DLL_PATH: wcdbApi,
      WECHAT_TOOL_WCDB_DLL_DIR: path.dirname(wcdbApi),
      WECHAT_TOOL_WCDB_RESOURCE_PATHS: JSON.stringify([path.dirname(wcdbApi), path.dirname(wcdb), resources]),
      WECHAT_TOOL_KOFFI_DIR: koffiDir,
    };
    sidecarProc = startProcess(electronExecutable, [sidecar], { cwd: resources, env: sidecarEnv });
    sidecarProc.once("exit", (code, signal) => {
      if (code && code !== 0) process.stderr.write(sidecarProc.output());
    });
    const sidecarHealth = await waitForJson(`http://127.0.0.1:${sidecarPort}/health`);
    assert.equal(sidecarHealth.body.ok, true);
    const sidecarInit = await requestJson(`http://127.0.0.1:${sidecarPort}/call`, {
      method: "POST",
      headers: { "x-wcdb-sidecar-token": sidecarToken },
      body: { action: "init", payload: {} },
      timeoutMs: 15_000,
    });
    assert.equal(sidecarInit.statusCode, 200);
    assert.equal(sidecarInit.body?.ok, true, sidecarInit.text || sidecarProc.output());
    assert.equal(sidecarInit.body?.result?.initialized, true);

    const fixture = createEncryptedSessionFixture(tempRoot);
    const opened = await requestJson(`http://127.0.0.1:${sidecarPort}/call`, {
      method: "POST",
      headers: { "x-wcdb-sidecar-token": sidecarToken },
      body: { action: "open_account", payload: { path: fixture.path, key: fixture.key } },
      timeoutMs: 15_000,
    });
    assert.equal(opened.statusCode, 200, opened.text || sidecarProc.output());
    assert.equal(opened.body?.ok, true, opened.text || sidecarProc.output());
    const fixtureHandle = Number(opened.body?.result?.handle || 0);
    assert.ok(fixtureHandle > 0, "packaged WCDB did not return an account handle");
    try {
      const sessions = await requestJson(`http://127.0.0.1:${sidecarPort}/call`, {
        method: "POST",
        headers: { "x-wcdb-sidecar-token": sidecarToken },
        body: { action: "get_sessions", payload: { handle: fixtureHandle } },
        timeoutMs: 15_000,
      });
      assert.equal(sessions.statusCode, 200, sessions.text || sidecarProc.output());
      assert.equal(sessions.body?.ok, true, sessions.text || sidecarProc.output());
      const rows = JSON.parse(String(sessions.body?.result?.payload || "[]"));
      assert.ok(
        Array.isArray(rows) && rows.some((row) => String(row?.username || "") === "wxid_friend"),
        "packaged WCDB did not return the synthetic realtime session"
      );
    } finally {
      await requestJson(`http://127.0.0.1:${sidecarPort}/call`, {
        method: "POST",
        headers: { "x-wcdb-sidecar-token": sidecarToken },
        body: { action: "close_account", payload: { handle: fixtureHandle } },
        timeoutMs: 5_000,
      });
    }

    const backendEnv = {
      ...process.env,
      WECHAT_TOOL_HOST: "127.0.0.1",
      WECHAT_TOOL_PORT: String(backendPort),
      WECHAT_TOOL_DATA_DIR: path.join(tempRoot, "data"),
      WECHAT_TOOL_OUTPUT_DIR: path.join(tempRoot, "output"),
      WECHAT_TOOL_UI_DIR: path.join(resources, "ui"),
      WECHAT_TOOL_WCDB_SIDECAR_URL: `http://127.0.0.1:${sidecarPort}`,
      WECHAT_TOOL_WCDB_SIDECAR_TOKEN: sidecarToken,
      WECHAT_TOOL_WCDB_API_DLL_PATH: wcdbApi,
      WECHAT_TOOL_FFMPEG: ffmpeg,
    };
    backendProc = startProcess(backend, [], { cwd: path.dirname(backend), env: backendEnv });
    backendProc.once("exit", (code, signal) => {
      if (code && code !== 0) process.stderr.write(backendProc.output());
    });
    const health = await waitForJson(`http://127.0.0.1:${backendPort}/api/health`);
    assert.equal(health.body?.status, "healthy");
    assert.equal(health.body?.service, "微信解密工具");

    const platform = await requestJson(`http://127.0.0.1:${backendPort}/api/system/platform`);
    assert.equal(platform.statusCode, 200);
    assert.equal(platform.body?.platform, "macos");
    assert.equal(platform.body?.database_key_extraction, false);
    assert.equal(platform.body?.database_key_manual_input, true);
    assert.equal(platform.body?.database_decryption, true);
    assert.equal(platform.body?.image_key_memory_scan, true);
    assert.equal(platform.body?.realtime_wcdb, true);
    assert.equal(platform.body?.account_archive_cross_platform, true);

    const keys = await requestJson(`http://127.0.0.1:${backendPort}/api/get_keys`);
    assert.equal(keys.statusCode, 200);
    assert.equal(keys.body?.data?.platform, "macos");
    assert.equal(keys.body?.data?.database_key_extraction, false);
    assert.equal(keys.body?.data?.manual_input_supported, true);
    assert.match(String(keys.body?.errmsg || ""), /手动填写/);
  } finally {
    await stopProcess(backendProc);
    await stopProcess(sidecarProc);
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }

  // Runtime processes must never modify the signed application bundle.
  run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  process.stdout.write(`macOS package smoke test passed: ${appPath}\n`);
}

main().catch((err) => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exitCode = 1;
});
