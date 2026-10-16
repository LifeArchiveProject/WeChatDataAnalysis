"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

const {
  resolvePackagedRuntime,
  waitForBackend,
} = require("./smoke-windows-package.cjs");
const {
  ensurePrivatePkiIssuerCached,
  resolvePrivatePkiRuntime,
} = require("../src/windows-private-pki-runtime.cjs");

const DEVICE_KEY_PREFIX = "LifeArchiveProject.WeChatDB.Native.RealSmoke.";
const DEVICE_KEY_PATTERN = new RegExp(
  `^${DEVICE_KEY_PREFIX.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[0-9a-f]{32}$`
);
const BLOCKING_WECHAT_IMAGES = new Set(["wechat.exe", "weixin.exe"]);
const WECHAT_APP_EX_IMAGE = "wechatappex.exe";
const WXWORK_IMAGE = "wxwork.exe";
const CONFLICTING_RUNTIME_IMAGES = new Set([
  "wechat-backend.exe",
  "wechatdb_broker.exe",
]);
const MAX_HTTP_BYTES = 16 * 1024 * 1024;
const MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024;
const REALTIME_MESSAGE_PAGE_SIZE = 10;
const SEARCH_INDEX_TIMEOUT_MS = 15 * 60 * 1000;
const PRODUCTION_LICENSE_URL = "https://license.fqyw.love/v1/leases";
const SEARCH_SNAPSHOT_FIXED_DATABASES = new Set([
  "contact.db",
  "head_image.db",
  "message_resource.db",
  "session.db",
]);
const CHILD_ENV_BLOCKED_EXACT = new Set([
  "ALL_PROXY",
  "AWS_CA_BUNDLE",
  "COR_ENABLE_PROFILING",
  "COR_PROFILER",
  "CURL_CA_BUNDLE",
  "DOTNET_STARTUP_HOOKS",
  "ELECTRON_RUN_AS_NODE",
  "GIT_SSL_CAINFO",
  "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH",
  "HTTPS_PROXY",
  "HTTP_PROXY",
  "NODE_OPTIONS",
  "NODE_EXTRA_CA_CERTS",
  "NO_PROXY",
  "PIP_CERT",
  "PYTHONHOME",
  "PYTHONPATH",
  "REQUESTS_CA_BUNDLE",
  "SSLKEYLOGFILE",
  "SSL_CERT_DIR",
  "SSL_CERT_FILE",
  "UV_PROJECT_ENVIRONMENT",
]);

function parseWindowsProcessSnapshot(output) {
  const text = String(output || "").replace(/^\uFEFF/, "").trim();
  if (!text) return [];
  const payload = JSON.parse(text);
  const records = Array.isArray(payload) ? payload : payload == null ? [] : [payload];
  return records.map((record) => {
    if (!record || typeof record !== "object" || Array.isArray(record)) {
      throw new Error("Invalid Windows process snapshot.");
    }
    const processId = Number(record.ProcessId);
    const parentProcessId = Number(record.ParentProcessId);
    const imageName = String(record.Name || "").trim().toLowerCase();
    if (
      !Number.isSafeInteger(processId) ||
      processId < 0 ||
      !Number.isSafeInteger(parentProcessId) ||
      parentProcessId < 0 ||
      !imageName
    ) {
      throw new Error("Invalid Windows process snapshot.");
    }
    return {
      processId,
      parentProcessId,
      imageName,
      executablePath:
        typeof record.ExecutablePath === "string" ? record.ExecutablePath.trim() : "",
    };
  });
}

function listWindowsProcesses({ spawnProcess = spawnSync, env = process.env } = {}) {
  const powershell = path.join(
    String(env.SystemRoot || env.WINDIR || "C:\\Windows"),
    "System32",
    "WindowsPowerShell",
    "v1.0",
    "powershell.exe"
  );
  const result = spawnProcess(
    powershell,
    [
      "-NoLogo",
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "$ErrorActionPreference='Stop';" +
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);" +
        "@(Get-CimInstance Win32_Process -ErrorAction Stop | " +
        "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath) | " +
        "ConvertTo-Json -Compress",
    ],
    {
      encoding: "utf8",
      windowsHide: true,
      maxBuffer: 8 * 1024 * 1024,
    }
  );
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    throw new Error("Cannot inspect Windows process state.");
  }
  try {
    return parseWindowsProcessSnapshot(result.stdout);
  } catch {
    throw new Error("Cannot inspect Windows process state.");
  }
}

function hasPathSegment(executablePath, expectedSegment) {
  return String(executablePath || "")
    .split(/[\\/]+/)
    .some((segment) => segment.toLowerCase() === expectedSegment);
}

function isWxWorkProcess(processRecord) {
  return (
    processRecord.imageName === WXWORK_IMAGE ||
    hasPathSegment(processRecord.executablePath, "wxwork")
  );
}

function isWxWorkWeChatAppEx(processRecord, processesById) {
  if (hasPathSegment(processRecord.executablePath, "wxwork")) return true;

  const visited = new Set([processRecord.processId]);
  let parentProcessId = processRecord.parentProcessId;
  while (parentProcessId > 0 && !visited.has(parentProcessId)) {
    visited.add(parentProcessId);
    const parent = processesById.get(parentProcessId);
    if (!parent) return false;
    if (BLOCKING_WECHAT_IMAGES.has(parent.imageName)) return false;
    if (isWxWorkProcess(parent)) return true;
    parentProcessId = parent.parentProcessId;
  }
  return false;
}

function assertProcessPreconditions(options = {}) {
  const processes = listWindowsProcesses(options);
  const processesById = new Map(
    processes.map((processRecord) => [processRecord.processId, processRecord])
  );
  const blocking = processes.filter(
    (processRecord) =>
      BLOCKING_WECHAT_IMAGES.has(processRecord.imageName) ||
      (processRecord.imageName === WECHAT_APP_EX_IMAGE &&
        !isWxWorkWeChatAppEx(processRecord, processesById))
  );
  if (blocking.length > 0) {
    throw new Error(
      `Real-database smoke requires WeChat to be fully exited (${blocking.length} related processes remain).`
    );
  }
  const conflicting = processes.filter((processRecord) =>
    CONFLICTING_RUNTIME_IMAGES.has(processRecord.imageName)
  );
  if (conflicting.length > 0) {
    throw new Error("Real-database smoke found an existing backend or broker process.");
  }
}

function resolveSourceOutputDirectory(env = process.env) {
  const explicit = String(env.WCE_REAL_DATABASE_OUTPUT_DIR || "").trim();
  if (explicit) return path.resolve(explicit);

  const appData = String(env.APPDATA || "").trim();
  assert.ok(appData, "APPDATA is required to resolve the configured WDA output directory.");
  const userData = path.join(appData, "wechat-data-analysis-desktop");
  const settingsPath = path.join(userData, "desktop-settings.json");
  let configured = "";
  try {
    const settings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
    configured = String(settings?.outputDir || "").trim();
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw new Error("Cannot read the WDA desktop output setting.");
    }
  }
  return path.resolve(configured || path.join(userData, "output"));
}

function canonicalDirectory(directoryPath) {
  try {
    const resolved = path.resolve(directoryPath);
    const stat = fs.statSync(resolved);
    assert.ok(stat.isDirectory(), "Expected a directory.");
    return fs.realpathSync.native ? fs.realpathSync.native(resolved) : fs.realpathSync(resolved);
  } catch {
    throw new Error("Expected an accessible directory.");
  }
}

function resolveKeyStoreAccounts(keyStorePath) {
  let payload;
  try {
    payload = JSON.parse(fs.readFileSync(keyStorePath, "utf8"));
  } catch {
    throw new Error("Cannot read the configured account key store.");
  }
  assert.ok(payload && typeof payload === "object" && !Array.isArray(payload));
  const accounts = [];
  const roots = new Map();
  for (const [account, value] of Object.entries(payload)) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    if (!/^[^\\/:\0]+$/.test(account) || account === "." || account === "..") continue;
    const dbKey = String(value.db_key || "").trim();
    if (!/^[0-9a-fA-F]{64}$/.test(dbKey)) continue;
    const explicitRoot = String(value.db_key_source_db_storage_path || "").trim();
    const wxidRoot = String(value.db_key_source_wxid_dir || "").trim();
    const rawRoot = explicitRoot || (wxidRoot ? path.join(wxidRoot, "db_storage") : "");
    if (!rawRoot || !path.isAbsolute(rawRoot)) continue;
    let root;
    try {
      root = canonicalDirectory(rawRoot);
    } catch {
      continue;
    }
    const rootKey = root.toLowerCase();
    if (!roots.has(rootKey)) roots.set(rootKey, root);
    accounts.push({ account, dbKey, root });
  }
  assert.ok(accounts.length > 0, "No production account has a complete database key and source root.");
  accounts.sort((left, right) => left.account.localeCompare(right.account));
  return { accounts, roots: [...roots.values()] };
}

function createIsolatedKeyStorePayload(accountEntry) {
  assert.ok(accountEntry && typeof accountEntry === "object" && !Array.isArray(accountEntry));
  const account = String(accountEntry.account || "").trim();
  const dbKey = String(accountEntry.dbKey || "").trim();
  const root = canonicalDirectory(String(accountEntry.root || ""));
  assert.match(account, /^[^\\/:\0]+$/);
  assert.notEqual(account, ".");
  assert.notEqual(account, "..");
  assert.match(dbKey, /^[0-9a-fA-F]{64}$/);
  return {
    [account]: {
      db_key: dbKey,
      db_key_source_wxid_dir: "",
      db_key_source_db_storage_path: root,
    },
  };
}

function enumerateDatabaseFiles(roots) {
  const files = [];
  const seen = new Set();
  function walk(directory) {
    let entries;
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true });
    } catch {
      throw new Error("Cannot enumerate the source database tree.");
    }
    for (const entry of entries) {
      const candidate = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) {
        throw new Error("Database source tree contains a symbolic link.");
      }
      if (entry.isDirectory()) {
        walk(candidate);
      } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".db")) {
        let real;
        try {
          real = fs.realpathSync.native
            ? fs.realpathSync.native(candidate)
            : fs.realpathSync(candidate);
        } catch {
          throw new Error("Cannot resolve a source database file.");
        }
        const key = real.toLowerCase();
        if (!seen.has(key)) {
          seen.add(key);
          files.push(real);
        }
      }
    }
  }
  for (const root of roots) walk(root);
  files.sort((left, right) => left.localeCompare(right));
  assert.ok(files.length > 0, "No source database files were found.");
  return files;
}

function enumerateProtectedSourceFiles(roots) {
  const files = [];
  const seen = new Set();
  function walk(directory) {
    let entries;
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true });
    } catch {
      throw new Error("Cannot enumerate the protected source tree.");
    }
    for (const entry of entries) {
      const candidate = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) {
        throw new Error("Protected source tree contains a symbolic link.");
      }
      if (entry.isDirectory()) {
        walk(candidate);
        continue;
      }
      if (!entry.isFile()) continue;
      let real;
      try {
        real = fs.realpathSync.native
          ? fs.realpathSync.native(candidate)
          : fs.realpathSync(candidate);
      } catch {
        throw new Error("Cannot resolve a protected source file.");
      }
      const key = real.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        files.push(real);
      }
    }
  }
  for (const root of roots) walk(root);
  files.sort((left, right) => left.localeCompare(right));
  assert.ok(files.length > 0, "No protected source files were found.");
  return files;
}

function hashFile(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(filePath);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

async function snapshotDatabaseFiles(files) {
  const snapshot = new Map();
  let totalBytes = 0;
  for (let index = 0; index < files.length; index += 1) {
    const filePath = files[index];
    let before;
    try {
      before = fs.statSync(filePath, { bigint: true });
    } catch {
      throw new Error(`Database ${index + 1} cannot be inspected.`);
    }
    assert.ok(before.isFile(), `Database ${index + 1} is not a regular file.`);
    let sha256;
    try {
      sha256 = await hashFile(filePath);
    } catch {
      throw new Error(`Database ${index + 1} could not be hashed.`);
    }
    let after;
    try {
      after = fs.statSync(filePath, { bigint: true });
    } catch {
      throw new Error(`Database ${index + 1} cannot be inspected after hashing.`);
    }
    if (
      before.size !== after.size ||
      before.mtimeNs !== after.mtimeNs ||
      before.ctimeNs !== after.ctimeNs ||
      before.birthtimeNs !== after.birthtimeNs ||
      before.mode !== after.mode
    ) {
      throw new Error(`Database ${index + 1} changed while its hash was being computed.`);
    }
    snapshot.set(filePath.toLowerCase(), {
      size: Number(after.size),
      mtimeNs: after.mtimeNs.toString(),
      ctimeNs: after.ctimeNs.toString(),
      birthtimeNs: after.birthtimeNs.toString(),
      mode: Number(after.mode),
      sha256,
    });
    totalBytes += Number(after.size);
  }
  return { files: snapshot, totalBytes };
}

function compareDatabaseSnapshots(before, after) {
  assert.equal(after.files.size, before.files.size, "Source database file count changed.");
  for (const [key, expected] of before.files) {
    const actual = after.files.get(key);
    assert.ok(actual, "A source database disappeared during smoke.");
    assert.equal(actual.size, expected.size, "A source database size changed during smoke.");
    assert.equal(actual.mtimeNs, expected.mtimeNs, "A source database timestamp changed during smoke.");
    assert.equal(actual.ctimeNs, expected.ctimeNs, "A source database metadata record changed during smoke.");
    assert.equal(actual.birthtimeNs, expected.birthtimeNs, "A source database identity changed during smoke.");
    assert.equal(actual.mode, expected.mode, "A source database mode changed during smoke.");
    assert.equal(actual.sha256, expected.sha256, "A source database hash changed during smoke.");
  }
}

function isSearchSnapshotDatabaseName(fileName) {
  const name = String(fileName || "").trim().toLowerCase();
  return (
    SEARCH_SNAPSHOT_FIXED_DATABASES.has(name) ||
    /^message(?:_[0-9]+)?\.db$/.test(name) ||
    /^biz_message(?:_[0-9]+)?\.db$/.test(name)
  );
}

function enumerateSearchSnapshotFiles(sourceOutput, account) {
  const accountName = String(account || "").trim();
  assert.match(accountName, /^[^\\/:\0]+$/);
  assert.notEqual(accountName, ".");
  assert.notEqual(accountName, "..");

  const databasesRoot = canonicalDirectory(path.join(sourceOutput, "databases"));
  const accountRoot = canonicalDirectory(path.join(databasesRoot, accountName));
  const relativeAccount = path.relative(databasesRoot, accountRoot);
  assert.ok(
    relativeAccount && !relativeAccount.startsWith("..") && !path.isAbsolute(relativeAccount),
    "The decrypted snapshot account escaped the configured output directory."
  );

  const files = [];
  let entries;
  try {
    entries = fs.readdirSync(accountRoot, { withFileTypes: true });
  } catch {
    throw new Error("Cannot enumerate the decrypted search snapshot.");
  }
  for (const entry of entries) {
    if (!isSearchSnapshotDatabaseName(entry.name)) continue;
    if (entry.isSymbolicLink()) {
      throw new Error("The decrypted snapshot contains a symbolic-link database.");
    }
    if (!entry.isFile()) continue;
    const candidate = path.join(accountRoot, entry.name);
    let real;
    try {
      real = fs.realpathSync.native
        ? fs.realpathSync.native(candidate)
        : fs.realpathSync(candidate);
    } catch {
      throw new Error("Cannot resolve a decrypted snapshot database.");
    }
    const relativeFile = path.relative(accountRoot, real);
    assert.ok(
      relativeFile && !relativeFile.startsWith("..") && !path.isAbsolute(relativeFile),
      "A decrypted snapshot database escaped its account directory."
    );
    files.push(real);
  }
  files.sort((left, right) => path.basename(left).localeCompare(path.basename(right)));
  const names = new Set(files.map((filePath) => path.basename(filePath).toLowerCase()));
  assert.ok(names.has("session.db"), "The decrypted search snapshot has no session database.");
  assert.ok(names.has("contact.db"), "The decrypted search snapshot has no contact database.");
  assert.ok(
    files.some((filePath) => /(?:^|_)message(?:_[0-9]+)?\.db$/i.test(path.basename(filePath))),
    "The decrypted search snapshot has no message database."
  );
  for (const filePath of files) {
    for (const suffix of ["-journal", "-shm", "-wal"]) {
      assert.ok(
        !fs.existsSync(`${filePath}${suffix}`),
        "The decrypted search snapshot is still attached to a SQLite journal."
      );
    }
  }
  return files;
}

async function copySearchSnapshotFiles({ files, snapshot, outputRoot, account }) {
  assert.ok(Array.isArray(files) && files.length > 0);
  assert.ok(snapshot?.files instanceof Map);
  const destinationRoot = assertPathInside(
    outputRoot,
    path.join(outputRoot, "databases", String(account || ""))
  );
  fs.mkdirSync(destinationRoot, { recursive: true });

  let copiedBytes = 0;
  for (const source of files) {
    const expected = snapshot.files.get(source.toLowerCase());
    assert.ok(expected, "A decrypted snapshot database was not hashed before copying.");
    const destination = assertPathInside(destinationRoot, path.join(destinationRoot, path.basename(source)));
    fs.copyFileSync(source, destination, fs.constants.COPYFILE_EXCL);
    const actual = fs.statSync(destination);
    assert.equal(actual.size, expected.size, "A copied decrypted snapshot database has the wrong size.");
    assert.equal(
      await hashFile(destination),
      expected.sha256,
      "A copied decrypted snapshot database has the wrong hash."
    );
    copiedBytes += actual.size;
  }
  return { databaseCount: files.length, databaseBytes: copiedBytes };
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

function requestBuffer(port, method, requestPath, body = null, maximumBytes = MAX_HTTP_BYTES) {
  return new Promise((resolve, reject) => {
    const encoded = body === null ? null : Buffer.from(JSON.stringify(body), "utf8");
    const request = http.request(
      {
        host: "127.0.0.1",
        port,
        path: requestPath,
        method,
        timeout: 180_000,
        headers: encoded
          ? { "Content-Type": "application/json", "Content-Length": String(encoded.length) }
          : {},
      },
      (response) => {
        const chunks = [];
        let size = 0;
        response.on("data", (chunk) => {
          size += chunk.length;
          if (size > maximumBytes) {
            request.destroy(new Error("HTTP response exceeded the smoke-test limit."));
            return;
          }
          chunks.push(chunk);
        });
        response.on("end", () => {
          const statusCode = response.statusCode || 0;
          if (statusCode < 200 || statusCode >= 300) {
            reject(new Error(`Packaged backend returned HTTP ${statusCode}.`));
            return;
          }
          resolve(Buffer.concat(chunks));
        });
      }
    );
    request.once("error", reject);
    request.once("timeout", () => request.destroy(new Error("Packaged backend request timed out.")));
    if (encoded) request.write(encoded);
    request.end();
  });
}

async function requestJson(port, method, requestPath, body = null) {
  const encoded = await requestBuffer(port, method, requestPath, body);
  let payload;
  try {
    payload = JSON.parse(encoded.toString("utf8"));
  } catch {
    throw new Error("Packaged backend returned invalid JSON.");
  }
  assert.ok(payload && typeof payload === "object" && !Array.isArray(payload));
  return payload;
}

function createMessagePageQuery({
  account,
  username,
  source,
  limit = REALTIME_MESSAGE_PAGE_SIZE,
  scanOffset = 0,
  filterOffset = 0,
  scanLimit = 100,
}) {
  for (const [name, value] of [
    ["limit", limit],
    ["scanOffset", scanOffset],
    ["filterOffset", filterOffset],
    ["scanLimit", scanLimit],
  ]) {
    assert.ok(Number.isSafeInteger(value) && value >= 0, `${name} must be a non-negative integer.`);
  }
  assert.ok(limit > 0, "limit must be positive.");
  assert.ok(scanLimit >= 50 && scanLimit <= 2000, "scanLimit is outside the API bounds.");
  return new URLSearchParams({
    account: String(account),
    username: String(username),
    source: String(source),
    limit: String(limit),
    offset: String(filterOffset),
    order: "desc",
    render_types: "text",
    filter_mode: "progressive",
    scan_offset: String(scanOffset),
    scan_limit: String(scanLimit),
  });
}

function createNextMessagePageQuery({ account, username, source, limit, response }) {
  assert.equal(response?.hasMore, true, "The first message page did not advertise another page.");
  const scanOffset = Number(response?.nextScanOffset);
  const filterOffset = Number(response?.nextFilterOffset);
  assert.ok(
    Number.isSafeInteger(scanOffset) && scanOffset >= 0,
    "The first message page did not return a valid scan cursor."
  );
  assert.ok(
    Number.isSafeInteger(filterOffset) && filterOffset >= 0,
    "The first message page did not return a valid filter cursor."
  );
  return createMessagePageQuery({
    account,
    username,
    source,
    limit,
    scanOffset,
    filterOffset,
  });
}

function messagePageIdentity(message) {
  const identity = String(message?.id || "").trim();
  assert.ok(identity, "A paginated message has no stable id.");
  return identity;
}

function assertDisjointMessagePages(firstPage, secondPage) {
  assert.ok(Array.isArray(firstPage) && firstPage.length > 0, "The first message page is empty.");
  assert.ok(Array.isArray(secondPage) && secondPage.length > 0, "The second message page is empty.");
  const firstIds = firstPage.map(messagePageIdentity);
  const secondIds = secondPage.map(messagePageIdentity);
  assert.equal(new Set(firstIds).size, firstIds.length, "The first message page contains duplicates.");
  assert.equal(new Set(secondIds).size, secondIds.length, "The second message page contains duplicates.");
  const firstSet = new Set(firstIds);
  const duplicateCount = secondIds.filter((identity) => firstSet.has(identity)).length;
  assert.equal(duplicateCount, 0, "The second message page repeated a first-page message.");
  return {
    firstPageCount: firstPage.length,
    secondPageCount: secondPage.length,
    duplicateCount,
  };
}

function selectUniqueSecondTextMessage(messages) {
  const candidates = [];
  const counts = new Map();
  for (const message of Array.isArray(messages) ? messages : []) {
    const content = String(message?.content || "").trim();
    if (String(message?.renderType || "").trim().toLowerCase() !== "text" || content.length < 3) {
      continue;
    }
    const rawTime = message?.createTime ?? message?.create_time ?? message?.timestamp;
    const createTime = Number.parseInt(String(rawTime || "0"), 10);
    if (!Number.isSafeInteger(createTime) || createTime <= 0) continue;
    counts.set(createTime, (counts.get(createTime) || 0) + 1);
    candidates.push({ message, createTime });
  }
  const selected = candidates.find(({ createTime }) => counts.get(createTime) === 1);
  return selected || null;
}

function deriveSearchProbeCandidates(messages, { maximum = 40 } = {}) {
  assert.ok(Number.isSafeInteger(maximum) && maximum > 0);
  const candidates = [];
  const seen = new Set();
  for (const message of Array.isArray(messages) ? messages : []) {
    if (String(message?.renderType || "").trim().toLowerCase() !== "text") continue;
    const content = String(message?.content || "")
      .normalize("NFKC")
      .replace(/[\u0000-\u001f\u007f]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    const identity = String(message?.id || "").trim();
    if (!identity || content.length < 2) continue;
    const runs = content.match(/[\p{L}\p{N}]{2,64}/gu) || [];
    runs.sort((left, right) => right.length - left.length);
    for (const run of runs) {
      const probe = [...run].slice(0, 24).join("");
      if (probe.length < 2 || seen.has(probe)) continue;
      seen.add(probe);
      candidates.push({ identity, content, probe });
      if (candidates.length >= maximum) return candidates;
    }
  }
  return candidates;
}

function searchIndexEvidence(payload) {
  assert.equal(payload?.status, "success", "Search-index status request failed.");
  const index = payload?.index;
  assert.ok(index && typeof index === "object" && !Array.isArray(index));
  const buildStatus = String(index?.build?.status || "").trim();
  if (buildStatus === "error") {
    throw new Error("The decrypted search index build failed.");
  }
  const rawMessageCount = String(index?.meta?.message_count || "").trim();
  const messageCount = /^[0-9]+$/.test(rawMessageCount) ? Number(rawMessageCount) : 0;
  return {
    ready: index.ready === true,
    building: buildStatus === "building",
    messageCount,
  };
}

async function waitForSearchIndexReady(port, account, timeoutMs = SEARCH_INDEX_TIMEOUT_MS) {
  assert.ok(Number.isSafeInteger(timeoutMs) && timeoutMs > 0);
  const query = new URLSearchParams({
    account: String(account),
    source: "decrypted",
    rebuild: "true",
  });
  const started = await requestJson(port, "POST", `/api/chat/search-index/build?${query}`);
  searchIndexEvidence(started);

  const deadline = Date.now() + timeoutMs;
  const statusQuery = new URLSearchParams({
    account: String(account),
    source: "decrypted",
  });
  while (Date.now() < deadline) {
    const payload = await requestJson(port, "GET", `/api/chat/search-index/status?${statusQuery}`);
    const evidence = searchIndexEvidence(payload);
    if (evidence.ready) {
      assert.ok(evidence.messageCount > 0, "The decrypted search index contains no messages.");
      return evidence;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("The decrypted search index did not become ready before the deadline.");
}

function createPrivacyExportRequest({ account, username, createTime, outputDir }) {
  const request = {
    account,
    source: "realtime",
    scope: "selected",
    usernames: [username],
    format: "json",
    include_hidden: false,
    include_official: false,
    include_media: false,
    media_kinds: [],
    message_types: ["text"],
    output_dir: outputDir,
    allow_process_key_extract: false,
    download_remote_media: false,
    privacy_mode: true,
    file_name: "private-pki-real-smoke.zip",
    encrypt: false,
  };
  if (Number.isSafeInteger(createTime) && createTime > 0) {
    request.start_time = createTime;
    request.end_time = createTime;
  }
  return request;
}

function createIsolatedBackendEnvironment(env, overrides) {
  const childEnv = {};
  for (const [name, value] of Object.entries(env || {})) {
    const normalized = String(name).toUpperCase();
    if (
      normalized.startsWith("WECHAT_TOOL_") ||
      normalized.startsWith("WCE_") ||
      CHILD_ENV_BLOCKED_EXACT.has(normalized)
    ) {
      continue;
    }
    childEnv[name] = value;
  }
  return Object.assign(childEnv, overrides);
}

async function startPackagedBackend(runtime, childEnv, port, stdout, stderr) {
  const processHandle = spawn(runtime.backend, [], {
    cwd: path.dirname(runtime.backend),
    windowsHide: true,
    stdio: ["ignore", stdout, stderr],
    env: { ...childEnv, WECHAT_TOOL_PORT: String(port) },
  });
  try {
    await waitForBackend(processHandle, port);
    return processHandle;
  } catch (error) {
    try {
      await stopProcessTree(processHandle);
    } catch {
      // Preserve the startup error; final cleanup will still remove the isolated directory.
    }
    throw error;
  }
}

function waitForChildExit(processHandle, timeoutMs = 30_000) {
  if (!processHandle || processHandle.exitCode !== null) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const onExit = () => {
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      processHandle.removeListener("exit", onExit);
      reject(new Error("Packaged backend process tree did not stop before the deadline."));
    }, timeoutMs);
    processHandle.once("exit", onExit);
  });
}

async function stopProcessTree(processHandle, { spawnProcess = spawnSync } = {}) {
  if (!processHandle || processHandle.exitCode !== null) return;
  const result = spawnProcess("taskkill.exe", ["/pid", String(processHandle.pid), "/t", "/f"], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error && result.error.code !== "ENOENT") throw result.error;
  await waitForChildExit(processHandle);
  if ((result.status ?? 1) !== 0 && processHandle.exitCode === null) {
    throw new Error("Unable to stop the packaged backend process tree.");
  }
}

function invokePowerShell(scriptPath, arguments_) {
  const result = spawnSync(
    "powershell.exe",
    [
      "-NoLogo",
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      scriptPath,
      ...arguments_,
    ],
    { encoding: "utf8", windowsHide: true, maxBuffer: 8 * 1024 * 1024 }
  );
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    throw new Error("Windows acceptance helper failed.");
  }
  try {
    return JSON.parse(String(result.stdout || "").trim());
  } catch {
    throw new Error("Windows acceptance helper returned invalid JSON.");
  }
}

function inspectPrivacyArchive(archivePath, sensitiveValuesPath = "") {
  const args = ["-ArchivePath", path.resolve(archivePath)];
  if (sensitiveValuesPath) {
    args.push("-SensitiveValuesPath", path.resolve(sensitiveValuesPath));
  }
  return invokePowerShell(
    path.join(__dirname, "inspect-windows-privacy-export.ps1"),
    args
  );
}

function inspectSmokeDeviceKey(keyName) {
  assert.match(keyName, DEVICE_KEY_PATTERN);
  return invokePowerShell(
    path.join(__dirname, "remove-windows-smoke-device-key.ps1"),
    ["-Action", "Inspect", "-KeyName", keyName]
  );
}

function inspectSmokeDeviceCredential({ credentialPath, deviceIdHex, buildId, serviceUrl }) {
  assert.match(String(deviceIdHex || ""), /^[0-9a-f]{64}$/);
  assert.match(String(buildId || ""), /^[A-Za-z0-9._-]{8,128}$/);
  return invokePowerShell(
    path.join(__dirname, "inspect-windows-smoke-device-credential.ps1"),
    [
      "-CredentialPath",
      path.resolve(credentialPath),
      "-DeviceIdHex",
      String(deviceIdHex),
      "-BuildId",
      String(buildId),
      "-ServiceUrl",
      String(serviceUrl),
    ]
  );
}

function removeSmokeDeviceKey(keyName) {
  assert.match(keyName, DEVICE_KEY_PATTERN);
  return invokePowerShell(
    path.join(__dirname, "remove-windows-smoke-device-key.ps1"),
    ["-Action", "Delete", "-KeyName", keyName]
  );
}

function secureSmokeDirectory(directoryPath) {
  const evidence = invokePowerShell(
    path.join(__dirname, "secure-windows-smoke-directory.ps1"),
    ["-DirectoryPath", path.resolve(directoryPath)]
  );
  assert.equal(evidence.protected, true);
  assert.equal(evidence.currentUserOnly, true);
  return evidence;
}

function removePrivatePkiIssuer(runtime) {
  const identity = resolvePrivatePkiRuntime(path.join(runtime.root, "resources"));
  const evidence = invokePowerShell(
    path.join(__dirname, "remove-windows-private-pki-issuer.ps1"),
    [
      "-RootCertificatePath",
      identity.rootCertificate,
      "-ExpectedRootSha256",
      identity.expectedRootSha256,
    ]
  );
  assert.equal(evidence.issuerStore, "CurrentUser\\CA");
  assert.equal(evidence.remaining, 0);
  return evidence;
}

function atomicWriteJson(filePath, payload, { replace = false } = {}) {
  const resolved = path.resolve(filePath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  if (!replace) assert.ok(!fs.existsSync(resolved), "Acceptance evidence already exists.");
  const temporary = `${resolved}.${process.pid}.${crypto.randomUUID()}.tmp`;
  try {
    fs.writeFileSync(temporary, `${JSON.stringify(payload, null, 2)}\n`, {
      encoding: "utf8",
      flag: "wx",
      mode: 0o600,
    });
    fs.renameSync(temporary, resolved);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
}

function assertPathInside(parentPath, candidatePath) {
  const parent = path.resolve(parentPath);
  const candidate = path.resolve(candidatePath);
  const relative = path.relative(parent, candidate);
  assert.ok(relative && !relative.startsWith("..") && !path.isAbsolute(relative));
  return candidate;
}

function assertPathOutside(parentPaths, candidatePath, label) {
  const candidate = path.resolve(candidatePath);
  for (const parentPath of parentPaths) {
    const parent = path.resolve(parentPath);
    const relative = path.relative(parent, candidate);
    const inside = relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
    assert.ok(!inside, `${label} must stay outside production data roots.`);
  }
  return candidate;
}

function sanitizeText(value, sensitiveValues) {
  let text = String(value || "");
  const secrets = [...new Set((sensitiveValues || []).map((item) => String(item || "")))]
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
  for (const secret of secrets) {
    text = text.split(secret).join("[redacted]");
  }
  return text;
}

function sanitizeError(error, sensitiveValues) {
  return sanitizeText(
    error?.stack || error?.message || error || "Unknown smoke failure.",
    sensitiveValues
  );
}

function boundSanitizedText(value, maximumLength) {
  if (value.length <= maximumLength) return value;
  const redaction = "[redacted]";
  const bounded = value.slice(0, maximumLength);
  const partialRedaction = value.lastIndexOf(redaction, maximumLength - 1);
  if (partialRedaction >= 0 && partialRedaction + redaction.length > maximumLength) {
    return `${bounded.slice(0, maximumLength - redaction.length)}${redaction}`;
  }
  return bounded;
}

function createPrivacyExportTerminalError(job, sensitiveValues = []) {
  const status = String(job?.status || "unknown").trim() || "unknown";
  const detail = boundSanitizedText(
    sanitizeText(String(job?.error || "").trim(), sensitiveValues),
    2048
  );
  return new Error(
    `Privacy export ended with status ${status}${detail ? `: ${detail}` : "."}`
  );
}

async function runRealDatabaseSmoke({ env = process.env } = {}) {
  if (process.platform !== "win32") {
    throw new Error("The packaged real-database smoke runs only on Windows.");
  }
  if (String(env.WCE_REAL_DATABASE_SMOKE_ALLOWED || "") !== "1") {
    throw new Error("Set WCE_REAL_DATABASE_SMOKE_ALLOWED=1 on an isolated acceptance host.");
  }
  assertProcessPreconditions();

  const packageRoot = path.resolve(
    String(env.WCE_REAL_DATABASE_PACKAGE_ROOT || process.argv[2] || "").trim()
  );
  assert.ok(packageRoot && packageRoot !== path.parse(packageRoot).root);
  const runtime = resolvePackagedRuntime(packageRoot);
  const manifest = JSON.parse(fs.readFileSync(runtime.manifest, "utf8"));
  assert.equal(manifest.developmentBuild, false);
  assert.equal(manifest.stagingPinnedSignerTrust, false);
  assert.equal(manifest.windowsSignerTrustMode, "private-pki");

  const sourceOutput = resolveSourceOutputDirectory(env);
  const sourceKeyStore = path.join(sourceOutput, "account_keys.json");
  let keyStoreBefore;
  try {
    keyStoreBefore = await hashFile(sourceKeyStore);
  } catch {
    throw new Error("Cannot hash the configured account key store.");
  }
  const { accounts: storedAccounts, roots } = resolveKeyStoreAccounts(sourceKeyStore);
  const sourceFiles = enumerateDatabaseFiles(roots);
  const protectedSourceFiles = enumerateProtectedSourceFiles(roots);
  const expectedCountRaw = String(env.WCE_REAL_DATABASE_EXPECTED_DB_COUNT || "").trim();
  assert.match(expectedCountRaw, /^[1-9][0-9]*$/, "An explicit positive database count is required.");
  const expectedCount = Number.parseInt(expectedCountRaw, 10);
  assert.equal(sourceFiles.length, expectedCount);
  const before = await snapshotDatabaseFiles(protectedSourceFiles);
  const databaseBytes = sourceFiles.reduce((total, filePath) => {
    const entry = before.files.get(filePath.toLowerCase());
    assert.ok(entry, "A source database is missing from the protected source snapshot.");
    return total + entry.size;
  }, 0);
  const selectedAccount = storedAccounts[0];
  const sourceSearchFiles = enumerateSearchSnapshotFiles(sourceOutput, selectedAccount.account);
  const sourceSearchBefore = await snapshotDatabaseFiles(sourceSearchFiles);
  const deviceKeyName = DEVICE_KEY_PREFIX + crypto.randomUUID().replaceAll("-", "");
  const cleanupPathRaw = String(env.WCE_REAL_DATABASE_DEVICE_CLEANUP_PATH || "").trim();
  assert.ok(cleanupPathRaw, "A server device-cleanup record path is required.");
  assert.ok(path.isAbsolute(cleanupPathRaw), "The server device-cleanup record path must be absolute.");
  const protectedDataRoots = [sourceOutput, ...roots];
  const cleanupPath = assertPathOutside(
    protectedDataRoots,
    cleanupPathRaw,
    "Server device-cleanup evidence"
  );
  assert.ok(!fs.existsSync(cleanupPath), "The server device-cleanup record already exists.");
  const acceptancePathRaw = String(env.WCE_REAL_DATABASE_ACCEPTANCE_PATH || "").trim();
  const acceptancePath = acceptancePathRaw ? path.resolve(acceptancePathRaw) : "";
  if (acceptancePathRaw) {
    assert.ok(path.isAbsolute(acceptancePathRaw), "The acceptance evidence path must be absolute.");
    assertPathOutside(protectedDataRoots, acceptancePath, "Acceptance evidence");
    assert.notEqual(
      acceptancePath.toLowerCase(),
      cleanupPath.toLowerCase(),
      "Acceptance and device-cleanup evidence require separate files."
    );
    assert.ok(!fs.existsSync(acceptancePath), "The acceptance evidence already exists.");
  }
  fs.mkdirSync(path.dirname(cleanupPath), { recursive: true });
  const cleanupDirectoryEvidence = secureSmokeDirectory(path.dirname(cleanupPath));

  let tempRoot = "";
  let stdout = null;
  let stderr = null;
  let backend = null;
  let operationError = null;
  let result = null;
  let deviceCleanup = null;
  let issuerCacheEvidence = null;
  const sensitiveValues = [
    sourceOutput,
    sourceKeyStore,
    ...storedAccounts.map((item) => item.account),
    ...storedAccounts.map((item) => item.dbKey),
    ...roots,
  ];

  try {
    issuerCacheEvidence = ensurePrivatePkiIssuerCached({
      resourcesPath: path.join(runtime.root, "resources"),
    });
    const deviceBeforeRegistration = inspectSmokeDeviceKey(deviceKeyName);
    assert.equal(
      deviceBeforeRegistration.found,
      false,
      "The random smoke device key unexpectedly existed before registration."
    );
    const tempParent = assertPathOutside(
      protectedDataRoots,
      os.tmpdir(),
      "Real-database smoke temporary directory"
    );
    tempRoot = fs.mkdtempSync(path.join(tempParent, "wda-packaged-real-smoke-"));
    sensitiveValues.push(tempRoot);
    secureSmokeDirectory(tempRoot);
    const dataRoot = path.join(tempRoot, "data");
    const credentialPath = path.join(
      dataRoot,
      ".native-core-license-v1",
      "device-credential.bin"
    );
    const outputRoot = path.join(tempRoot, "output");
    const exportRoot = path.join(tempRoot, "exports");
    fs.mkdirSync(dataRoot, { recursive: true });
    fs.mkdirSync(outputRoot, { recursive: true });
    fs.mkdirSync(exportRoot, { recursive: true });
    const snapshotCopy = await copySearchSnapshotFiles({
      files: sourceSearchFiles,
      snapshot: sourceSearchBefore,
      outputRoot,
      account: selectedAccount.account,
    });
    atomicWriteJson(
      path.join(outputRoot, "account_keys.json"),
      createIsolatedKeyStorePayload(selectedAccount)
    );

    const stdoutPath = path.join(tempRoot, "backend.out.log");
    const stderrPath = path.join(tempRoot, "backend.err.log");
    stdout = fs.openSync(stdoutPath, "w");
    stderr = fs.openSync(stderrPath, "w");
    let port = await getFreePort();
    const childEnv = createIsolatedBackendEnvironment(env, {
      WECHAT_TOOL_DATA_DIR: dataRoot,
      WECHAT_TOOL_OUTPUT_DIR: outputRoot,
      WECHAT_TOOL_HOST: "127.0.0.1",
      WECHAT_TOOL_NATIVE_CORE_MODE: "required",
      WECHAT_TOOL_NATIVE_CORE_DEVICE_KEY_NAME: deviceKeyName,
      WECHAT_TOOL_NATIVE_CORE_BACKGROUND_PRIME: "0",
      WECHAT_TOOL_REALTIME_AUTOSYNC: "0",
      WECHAT_TOOL_SNS_AUTOSYNC: "0",
    });
    backend = await startPackagedBackend(runtime, childEnv, port, stdout, stderr);

    const accountResponse = await requestJson(port, "GET", "/api/chat/accounts");
    assert.equal(accountResponse.status, "success");
    const apiAccounts = Array.isArray(accountResponse.accounts) ? accountResponse.accounts : [];
    const selectedAccounts = apiAccounts.filter(
      (account) => String(account) === selectedAccount.account
    );
    assert.equal(
      selectedAccounts.length,
      1,
      "Packaged backend did not preserve the isolated acceptance account."
    );
    assert.equal(apiAccounts.length, 1, "Packaged backend loaded an account outside the isolated key store.");

    let sessionCount = 0;
    let messagesRead = 0;
    let exportTarget = null;
    let paginationTarget = null;
    for (const account of selectedAccounts) {
      const sessionQuery = new URLSearchParams({
        account: String(account),
        source: "realtime",
        limit: "20",
        include_hidden: "true",
        include_official: "true",
        preview: "none",
      });
      const sessions = await requestJson(port, "GET", `/api/chat/sessions?${sessionQuery}`);
      assert.equal(sessions.status, "success");
      assert.equal(sessions.source, "realtime");
      assert.notEqual(sessions.sourceFallback, true);
      const items = Array.isArray(sessions.sessions) ? sessions.sessions : [];
      assert.ok(items.length > 0, "A configured account returned no realtime sessions.");
      sessionCount += items.length;

      for (const session of items) {
        const username = String(session?.username || "").trim();
        if (!username) continue;
        const messageQuery = createMessagePageQuery({
          account: String(account),
          username,
          source: "realtime",
        });
        const messages = await requestJson(port, "GET", `/api/chat/messages?${messageQuery}`);
        assert.equal(messages.status, "success");
        assert.equal(messages.source, "realtime");
        assert.notEqual(messages.sourceFallback, true);
        const rows = Array.isArray(messages.messages) ? messages.messages : [];
        if (rows.length === 0) continue;
        messagesRead += rows.length;

        if (!exportTarget && messages.hasMore !== true) {
          const selected = selectUniqueSecondTextMessage(rows);
          if (selected) {
            const selectedMessage = selected.message;
            exportTarget = {
              account: String(account),
              username,
              createTime: selected.createTime,
              completeSessionVerified: true,
              privacyValues: [
                String(account),
                username,
                String(selectedMessage.content || "").trim(),
                String(selectedMessage.senderUsername || "").trim(),
                String(session?.displayName || session?.name || session?.remark || "").trim(),
              ].filter((value, index, values) => value.length >= 3 && values.indexOf(value) === index),
            };
            sensitiveValues.push(...exportTarget.privacyValues);
          }
        }

        if (!paginationTarget && messages.hasMore === true) {
          const nextQuery = createNextMessagePageQuery({
            account: String(account),
            username,
            source: "realtime",
            limit: REALTIME_MESSAGE_PAGE_SIZE,
            response: messages,
          });
          const next = await requestJson(port, "GET", `/api/chat/messages?${nextQuery}`);
          assert.equal(next.status, "success");
          assert.equal(next.source, "realtime");
          assert.notEqual(next.sourceFallback, true);
          const nextRows = Array.isArray(next.messages) ? next.messages : [];
          if (nextRows.length > 0) {
            const pageEvidence = assertDisjointMessagePages(rows, nextRows);
            messagesRead += nextRows.length;
            paginationTarget = { username, pageEvidence };
            sensitiveValues.push(username);
          }
        }

        if (exportTarget && paginationTarget) break;
      }
      if (exportTarget && paginationTarget) break;
    }
    assert.ok(exportTarget, "Packaged backend returned no bounded realtime message sample.");
    assert.ok(paginationTarget, "Packaged backend returned no verifiable second realtime message page.");
    assert.ok(exportTarget.createTime > 0, "Bounded realtime text message has no usable timestamp.");
    assert.equal(
      exportTarget.completeSessionVerified,
      true,
      "Privacy export target was not selected from a complete realtime session scan."
    );
    assert.ok(exportTarget.privacyValues.length >= 3, "Privacy export lacks sufficient real-data probes.");

    const registeredDevice = inspectSmokeDeviceKey(deviceKeyName);
    assert.equal(registeredDevice.found, true, "The first realtime query did not create a device credential.");
    assert.equal(registeredDevice.deleted, false);
    assert.match(String(registeredDevice.deviceIdHex || ""), /^[0-9a-f]{64}$/);
    sensitiveValues.push(String(registeredDevice.deviceIdHex));
    const registeredCredential = inspectSmokeDeviceCredential({
      credentialPath,
      deviceIdHex: registeredDevice.deviceIdHex,
      buildId: manifest.buildId,
      serviceUrl: PRODUCTION_LICENSE_URL,
    });
    assert.equal(registeredCredential.schemaVersion, 2);
    assert.match(String(registeredCredential.credentialSha256 || ""), /^[0-9a-f]{64}$/);
    sensitiveValues.push(String(registeredCredential.credentialSha256));

    const decryptedSessionQuery = new URLSearchParams({
      account: String(selectedAccount.account),
      source: "decrypted",
      limit: "50",
      include_hidden: "true",
      include_official: "true",
      preview: "none",
    });
    const decryptedSessions = await requestJson(
      port,
      "GET",
      `/api/chat/sessions?${decryptedSessionQuery}`
    );
    assert.equal(decryptedSessions.status, "success");
    assert.equal(decryptedSessions.source, "decrypted");
    assert.notEqual(decryptedSessions.sourceFallback, true);
    const decryptedSessionItems = Array.isArray(decryptedSessions.sessions)
      ? decryptedSessions.sessions
      : [];
    assert.ok(decryptedSessionItems.length > 0, "The copied decrypted snapshot has no sessions.");

    const searchCandidates = [];
    let decryptedMessagesRead = 0;
    for (const session of decryptedSessionItems) {
      const username = String(session?.username || "").trim();
      if (!username) continue;
      const query = createMessagePageQuery({
        account: selectedAccount.account,
        username,
        source: "decrypted",
        limit: 30,
      });
      const payload = await requestJson(port, "GET", `/api/chat/messages?${query}`);
      assert.equal(payload.status, "success");
      assert.equal(payload.source, "decrypted");
      assert.notEqual(payload.sourceFallback, true);
      const rows = Array.isArray(payload.messages) ? payload.messages : [];
      decryptedMessagesRead += rows.length;
      for (const candidate of deriveSearchProbeCandidates(rows, {
        maximum: 40 - searchCandidates.length,
      })) {
        searchCandidates.push({ ...candidate, username });
        sensitiveValues.push(username, candidate.identity, candidate.content, candidate.probe);
      }
      if (searchCandidates.length >= 40) break;
    }
    assert.ok(searchCandidates.length > 0, "The copied decrypted snapshot has no searchable text probe.");

    const indexEvidence = await waitForSearchIndexReady(
      port,
      selectedAccount.account,
      SEARCH_INDEX_TIMEOUT_MS
    );
    let searchVerified = false;
    for (const candidate of searchCandidates) {
      const searchQuery = new URLSearchParams({
        account: selectedAccount.account,
        username: candidate.username,
        q: candidate.probe,
        source: "decrypted",
        limit: "100",
        offset: "0",
        render_types: "text",
        include_hidden: "true",
        include_official: "true",
      });
      const search = await requestJson(port, "GET", `/api/chat/search?${searchQuery}`);
      assert.equal(search.status, "success", "The decrypted snapshot search did not complete.");
      assert.equal(search.source, "decrypted_index");
      assert.equal(search?.freshness?.kind, "snapshot");
      const hits = Array.isArray(search.hits) ? search.hits : [];
      const matched = hits.some((hit) => {
        if (String(hit?.id || "").trim() === candidate.identity) return true;
        return (
          String(hit?.username || "").trim() === candidate.username &&
          String(hit?.content || "").trim() === candidate.content
        );
      });
      if (matched) {
        searchVerified = true;
        break;
      }
    }
    assert.ok(searchVerified, "The decrypted snapshot search did not return its source message.");

    await stopProcessTree(backend);
    backend = null;
    port = await getFreePort();
    backend = await startPackagedBackend(runtime, childEnv, port, stdout, stderr);

    const restartedSessionQuery = new URLSearchParams({
      account: selectedAccount.account,
      source: "realtime",
      limit: "20",
      include_hidden: "true",
      include_official: "true",
      preview: "none",
    });
    const restartedSessions = await requestJson(
      port,
      "GET",
      `/api/chat/sessions?${restartedSessionQuery}`
    );
    assert.equal(restartedSessions.status, "success");
    assert.equal(restartedSessions.source, "realtime");
    assert.notEqual(restartedSessions.sourceFallback, true);
    const restartedSessionItems = Array.isArray(restartedSessions.sessions)
      ? restartedSessions.sessions
      : [];
    assert.ok(restartedSessionItems.length > 0, "The restarted backend returned no realtime sessions.");
    assert.ok(
      restartedSessionItems.some(
        (session) => String(session?.username || "").trim() === paginationTarget.username
      ),
      "The restarted backend lost the paginated realtime session."
    );

    const restartedMessageQuery = createMessagePageQuery({
      account: selectedAccount.account,
      username: paginationTarget.username,
      source: "realtime",
      limit: REALTIME_MESSAGE_PAGE_SIZE,
    });
    const restartedMessages = await requestJson(
      port,
      "GET",
      `/api/chat/messages?${restartedMessageQuery}`
    );
    assert.equal(restartedMessages.status, "success");
    assert.equal(restartedMessages.source, "realtime");
    assert.notEqual(restartedMessages.sourceFallback, true);
    const restartedRows = Array.isArray(restartedMessages.messages)
      ? restartedMessages.messages
      : [];
    assert.ok(restartedRows.length > 0, "The restarted backend returned no realtime messages.");

    const restartedDevice = inspectSmokeDeviceKey(deviceKeyName);
    assert.equal(restartedDevice.found, true);
    assert.equal(restartedDevice.deleted, false);
    sensitiveValues.push(String(restartedDevice.deviceIdHex || ""));
    assert.equal(
      restartedDevice.deviceIdHex,
      registeredDevice.deviceIdHex,
      "The packaged backend did not reuse its isolated device credential after restart."
    );
    const restartedCredential = inspectSmokeDeviceCredential({
      credentialPath,
      deviceIdHex: restartedDevice.deviceIdHex,
      buildId: manifest.buildId,
      serviceUrl: PRODUCTION_LICENSE_URL,
    });
    assert.equal(restartedCredential.schemaVersion, 2);
    assert.match(String(restartedCredential.credentialSha256 || ""), /^[0-9a-f]{64}$/);
    sensitiveValues.push(String(restartedCredential.credentialSha256));
    assert.equal(
      restartedCredential.credentialSha256,
      registeredCredential.credentialSha256,
      "The packaged backend replaced its DPAPI-protected device credential after restart."
    );

    const created = await requestJson(
      port,
      "POST",
      "/api/chat/exports",
      createPrivacyExportRequest({ ...exportTarget, outputDir: exportRoot })
    );
    assert.equal(created.status, "success");
    const exportId = String(created?.job?.exportId || "").trim();
    assert.match(exportId, /^[0-9a-f]{12}$/);

    const deadline = Date.now() + 180_000;
    let job = null;
    while (Date.now() < deadline) {
      const status = await requestJson(port, "GET", `/api/chat/exports/${exportId}`);
      job = status.job;
      if (job?.status === "done") break;
      if (job?.status === "error" || job?.status === "cancelled") {
        throw createPrivacyExportTerminalError(job, sensitiveValues);
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    assert.equal(job?.status, "done", "Privacy export did not finish before the deadline.");
    const exportedMessages = Number(job?.progress?.messagesExported || 0);
    assert.equal(exportedMessages, 1, "Privacy export was not limited to one realtime text message.");

    const downloaded = await requestBuffer(
      port,
      "GET",
      `/api/chat/exports/${exportId}/download`,
      null,
      MAX_DOWNLOAD_BYTES
    );
    assert.ok(downloaded.length > 0);
    const downloadPath = path.join(tempRoot, "privacy-export.zip");
    fs.writeFileSync(downloadPath, downloaded, { flag: "wx" });
    const serverPath = assertPathInside(tempRoot, String(job.zipPath || ""));
    assert.equal(await hashFile(downloadPath), await hashFile(serverPath));
    const privacyProbePath = path.join(tempRoot, "privacy-sensitive-values.json");
    atomicWriteJson(privacyProbePath, {
      schemaVersion: 1,
      values: exportTarget.privacyValues,
    });
    const archive = inspectPrivacyArchive(downloadPath, privacyProbePath);
    assert.equal(archive.wes1Present, true);
    assert.equal(archive.accountRedacted, true);
    assert.equal(archive.mediaEntriesPresent, false);
    assert.equal(archive.sensitiveValuesChecked, exportTarget.privacyValues.length);

    result = {
      schemaVersion: 1,
      verifiedAtUtc: new Date().toISOString(),
      status: "passed",
      buildId: String(manifest.buildId),
      accountCount: selectedAccounts.length,
      databaseCount: sourceFiles.length,
      databaseBytes,
      protectedSourceFileCount: protectedSourceFiles.length,
      protectedSourceBytes: before.totalBytes,
      realtimeSessionCount: sessionCount,
      boundedMessagesRead: messagesRead,
      initialOnlineRegistrationVerified: true,
      realtimeSessionQueryVerified: true,
      realtimeMessageQueryVerified: true,
      realtimeFirstPageMessages: paginationTarget.pageEvidence.firstPageCount,
      realtimeSecondPageMessages: paginationTarget.pageEvidence.secondPageCount,
      paginationDuplicateCount: paginationTarget.pageEvidence.duplicateCount,
      realtimePaginationVerified: true,
      decryptedSnapshotDatabaseCount: snapshotCopy.databaseCount,
      decryptedSnapshotBytes: snapshotCopy.databaseBytes,
      decryptedSnapshotMessagesRead: decryptedMessagesRead,
      searchIndexReady: indexEvidence.ready,
      searchIndexMessageCount: indexEvidence.messageCount,
      decryptedSnapshotSearchVerified: searchVerified,
      packagedBackendRestarted: true,
      credentialReusedAfterRestart: true,
      dpapiCredentialFingerprintReusedAfterRestart: true,
      restartRealtimeSessionQueryVerified: true,
      restartRealtimeMessageQueryVerified: true,
      restartRealtimeMessagesRead: restartedRows.length,
      privacyExportMessages: exportedMessages,
      privacyExportUniqueSecondVerified: true,
      privacyMetadataRedacted: true,
      wes1VerifiedDuringSeal: true,
      wes1SidecarPresent: true,
      exportDownloadSha256: await hashFile(downloadPath),
      sourceDatabaseHashesStable: false,
      sourceProtectedTreeStable: false,
      sourceDecryptedSnapshotHashesStable: false,
      sourceKeyStoreStable: false,
      deviceKeyDeleted: false,
      issuerCacheRestored: false,
      cleanupEvidenceDirectoryProtected: cleanupDirectoryEvidence.currentUserOnly === true,
      serverSeatCleanupPending: true,
    };
  } catch (error) {
    operationError = error;
  } finally {
    try {
      await stopProcessTree(backend);
    } catch (error) {
      operationError ||= error;
    }
    for (const descriptor of [stdout, stderr]) {
      if (descriptor === null) continue;
      try {
        fs.closeSync(descriptor);
      } catch (error) {
        operationError ||= error;
      }
    }

    try {
      const afterFiles = enumerateProtectedSourceFiles(roots);
      const after = await snapshotDatabaseFiles(afterFiles);
      compareDatabaseSnapshots(before, after);
      const sourceSearchAfterFiles = enumerateSearchSnapshotFiles(
        sourceOutput,
        selectedAccount.account
      );
      const sourceSearchAfter = await snapshotDatabaseFiles(sourceSearchAfterFiles);
      compareDatabaseSnapshots(sourceSearchBefore, sourceSearchAfter);
      assert.equal(await hashFile(sourceKeyStore), keyStoreBefore, "Source key store changed during smoke.");
      if (result) {
        result.sourceDatabaseHashesStable = true;
        result.sourceProtectedTreeStable = true;
        result.sourceDecryptedSnapshotHashesStable = true;
        result.sourceKeyStoreStable = true;
      }
    } catch (error) {
      operationError ||= error;
    }

    try {
      const inspectedDevice = inspectSmokeDeviceKey(deviceKeyName);
      if (inspectedDevice.found) {
        sensitiveValues.push(String(inspectedDevice.deviceIdHex || ""));
        assert.equal(inspectedDevice.deleted, false);
        assert.match(String(inspectedDevice.deviceIdHex || ""), /^[0-9a-f]{64}$/);
        const cleanupRecord = {
          schemaVersion: 1,
          buildId: String(manifest.buildId),
          deviceIdHex: String(inspectedDevice.deviceIdHex),
          localDeviceKeyDeleted: false,
          serverSeatCleanupPending: true,
        };
        atomicWriteJson(cleanupPath, cleanupRecord);
        deviceCleanup = removeSmokeDeviceKey(deviceKeyName);
        assert.equal(deviceCleanup.found, true);
        assert.equal(deviceCleanup.deleted, true);
        assert.equal(deviceCleanup.deviceIdHex, inspectedDevice.deviceIdHex);
        cleanupRecord.localDeviceKeyDeleted = true;
        atomicWriteJson(cleanupPath, cleanupRecord, { replace: true });
      } else if (result) {
        throw new Error("Packaged backend did not create the isolated smoke device key.");
      }
      if (result) result.deviceKeyDeleted = Boolean(deviceCleanup?.deleted);
    } catch (error) {
      operationError ||= error;
    }

    if (tempRoot) {
      try {
        fs.rmSync(tempRoot, { recursive: true, force: true });
      } catch (error) {
        operationError ||= error;
      }
    }
    if (issuerCacheEvidence?.newlyAdded === true) {
      try {
        const issuerCleanup = removePrivatePkiIssuer(runtime);
        if (result) result.issuerCacheRestored = issuerCleanup.remaining === 0;
      } catch (error) {
        operationError ||= error;
      }
    } else if (result) {
      result.issuerCacheRestored = true;
    }
  }

  if (operationError) {
    throw new Error(sanitizeError(operationError, sensitiveValues));
  }
  assert.ok(result?.sourceDatabaseHashesStable);
  assert.ok(result?.sourceProtectedTreeStable);
  assert.ok(result?.sourceDecryptedSnapshotHashesStable);
  assert.ok(result?.sourceKeyStoreStable);
  assert.ok(result?.deviceKeyDeleted);
  assert.ok(result?.issuerCacheRestored);
  if (acceptancePath) atomicWriteJson(acceptancePath, result);
  return result;
}

module.exports = {
  assertProcessPreconditions,
  atomicWriteJson,
  compareDatabaseSnapshots,
  copySearchSnapshotFiles,
  createIsolatedBackendEnvironment,
  createIsolatedKeyStorePayload,
  createMessagePageQuery,
  createNextMessagePageQuery,
  createPrivacyExportRequest,
  createPrivacyExportTerminalError,
  deriveSearchProbeCandidates,
  enumerateDatabaseFiles,
  enumerateProtectedSourceFiles,
  enumerateSearchSnapshotFiles,
  isSearchSnapshotDatabaseName,
  parseWindowsProcessSnapshot,
  resolveKeyStoreAccounts,
  resolveSourceOutputDirectory,
  runRealDatabaseSmoke,
  sanitizeError,
  searchIndexEvidence,
  selectUniqueSecondTextMessage,
  snapshotDatabaseFiles,
  assertDisjointMessagePages,
};

if (require.main === module) {
  runRealDatabaseSmoke()
    .then((result) => {
      console.log(
        JSON.stringify({
          status: result.status,
          buildId: result.buildId,
          accountCount: result.accountCount,
          databaseCount: result.databaseCount,
          databaseBytes: result.databaseBytes,
          realtimeSessionCount: result.realtimeSessionCount,
          boundedMessagesRead: result.boundedMessagesRead,
          initialOnlineRegistrationVerified: result.initialOnlineRegistrationVerified,
          realtimePaginationVerified: result.realtimePaginationVerified,
          realtimeFirstPageMessages: result.realtimeFirstPageMessages,
          realtimeSecondPageMessages: result.realtimeSecondPageMessages,
          paginationDuplicateCount: result.paginationDuplicateCount,
          decryptedSnapshotDatabaseCount: result.decryptedSnapshotDatabaseCount,
          decryptedSnapshotSearchVerified: result.decryptedSnapshotSearchVerified,
          searchIndexReady: result.searchIndexReady,
          packagedBackendRestarted: result.packagedBackendRestarted,
          credentialReusedAfterRestart: result.credentialReusedAfterRestart,
          dpapiCredentialFingerprintReusedAfterRestart:
            result.dpapiCredentialFingerprintReusedAfterRestart,
          restartRealtimeMessageQueryVerified: result.restartRealtimeMessageQueryVerified,
          privacyExportMessages: result.privacyExportMessages,
          privacyExportUniqueSecondVerified: result.privacyExportUniqueSecondVerified,
          privacyMetadataRedacted: result.privacyMetadataRedacted,
          wes1SidecarPresent: result.wes1SidecarPresent,
          sourceDatabaseHashesStable: result.sourceDatabaseHashesStable,
          sourceProtectedTreeStable: result.sourceProtectedTreeStable,
          sourceDecryptedSnapshotHashesStable: result.sourceDecryptedSnapshotHashesStable,
          sourceKeyStoreStable: result.sourceKeyStoreStable,
          deviceKeyDeleted: result.deviceKeyDeleted,
          serverSeatCleanupPending: result.serverSeatCleanupPending,
        })
      );
    })
    .catch((error) => {
      console.error(error?.message || error);
      process.exit(1);
    });
}
