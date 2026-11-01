"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const {
  assertDisjointMessagePages,
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
  enumerateProtectedSourceFiles,
  enumerateSearchSnapshotFiles,
  isSearchSnapshotDatabaseName,
  parseWindowsProcessSnapshot,
  resolveKeyStoreAccounts,
  sanitizeError,
  searchIndexEvidence,
  selectUniqueSecondTextMessage,
  snapshotDatabaseFiles,
} = require("../scripts/smoke-windows-real-database.cjs");

const powershell = path.join(
  process.env.SystemRoot || process.env.WINDIR || "C:\\Windows",
  "System32",
  "WindowsPowerShell",
  "v1.0",
  "powershell.exe"
);

function runPowerShell(args, options = {}) {
  const result = spawnSync(powershell, ["-NoLogo", "-NoProfile", "-NonInteractive", ...args], {
    encoding: "utf8",
    windowsHide: true,
    maxBuffer: 8 * 1024 * 1024,
    ...options,
  });
  if (result.error) throw result.error;
  return result;
}

function createProcessSnapshotSpawner(processes) {
  return (executable, args) => {
    assert.equal(path.basename(executable).toLowerCase(), "powershell.exe");
    assert.ok(args.includes("-NonInteractive"));
    assert.match(args.at(-1), /Get-CimInstance Win32_Process/);
    return {
      status: 0,
      stdout: JSON.stringify(processes),
      stderr: "",
    };
  };
}

function createZipFixture(contentRoot, archivePath, entries) {
  return runPowerShell(
    [
      "-Command",
      "Add-Type -AssemblyName System.IO.Compression;" +
        "Add-Type -AssemblyName System.IO.Compression.FileSystem;" +
        "$s=[IO.File]::Open($env:WCE_FIXTURE_ARCHIVE,[IO.FileMode]::CreateNew);" +
        "$z=[IO.Compression.ZipArchive]::new($s,[IO.Compression.ZipArchiveMode]::Create);" +
        "try{$items=$env:WCE_FIXTURE_ITEMS|ConvertFrom-Json;foreach($i in $items){" +
        "[void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile(" +
        "$z,(Join-Path $env:WCE_FIXTURE_ROOT $i.source),$i.entry," +
        "[IO.Compression.CompressionLevel]::NoCompression)}}" +
        "finally{$z.Dispose();$s.Dispose()}",
    ],
    {
      env: {
        ...process.env,
        WCE_FIXTURE_ROOT: contentRoot,
        WCE_FIXTURE_ARCHIVE: archivePath,
        WCE_FIXTURE_ITEMS: JSON.stringify(entries),
      },
    }
  );
}

test("real-database smoke parses a structured Windows process snapshot", () => {
  assert.deepEqual(
    parseWindowsProcessSnapshot(
      JSON.stringify({
        ProcessId: 27924,
        ParentProcessId: 10456,
        Name: "WXWork.exe",
        ExecutablePath: "D:\\abc\\WXWork\\WXWork.exe",
      })
    ),
    [
      {
        processId: 27924,
        parentProcessId: 10456,
        imageName: "wxwork.exe",
        executablePath: "D:\\abc\\WXWork\\WXWork.exe",
      },
    ]
  );
});

test("real-database smoke ignores WXWork WeChatAppEx processes by path and ancestry", () => {
  assert.doesNotThrow(() =>
    assertProcessPreconditions({
      spawnProcess: createProcessSnapshotSpawner([
        {
          ProcessId: 100,
          ParentProcessId: 4,
          Name: "WXWork.exe",
          ExecutablePath: "D:\\abc\\WXWork\\WXWork.exe",
        },
        {
          ProcessId: 101,
          ParentProcessId: 100,
          Name: "WeChatAppEx.exe",
          ExecutablePath:
            "C:\\Users\\test\\AppData\\Roaming\\Tencent\\WXWork\\wmpf_Applet\\runtime\\WeChatAppEx.exe",
        },
        {
          ProcessId: 102,
          ParentProcessId: 101,
          Name: "WeChatAppEx.exe",
          ExecutablePath: null,
        },
        {
          ProcessId: 103,
          ParentProcessId: 999,
          Name: "WeChatAppEx.exe",
          ExecutablePath:
            "C:\\Users\\test\\AppData\\Roaming\\Tencent\\WXWork\\wmpf_Applet\\runtime\\WeChatAppEx.exe",
        },
        {
          ProcessId: 104,
          ParentProcessId: 100,
          Name: "WeChatAppEx.exe",
          ExecutablePath: null,
        },
      ]),
      env: { SystemRoot: "C:\\Windows" },
    })
  );
});

test("real-database smoke blocks personal or unclassified WeChatAppEx processes", () => {
  for (const processRecord of [
    {
      ProcessId: 201,
      ParentProcessId: 200,
      Name: "WeChatAppEx.exe",
      ExecutablePath:
        "C:\\Users\\test\\AppData\\Roaming\\Tencent\\WeChat\\XPlugin\\WeChatAppEx.exe",
    },
    {
      ProcessId: 202,
      ParentProcessId: 999,
      Name: "WeChatAppEx.exe",
      ExecutablePath: null,
    },
  ]) {
    assert.throws(
      () =>
        assertProcessPreconditions({
          spawnProcess: createProcessSnapshotSpawner([processRecord]),
          env: { SystemRoot: "C:\\Windows" },
        }),
      /requires WeChat to be fully exited/
    );
  }
});

test("real-database smoke always blocks WeChat and Weixin images", () => {
  for (const imageName of ["WeChat.exe", "Weixin.exe"]) {
    assert.throws(
      () =>
        assertProcessPreconditions({
          spawnProcess: createProcessSnapshotSpawner([
            {
              ProcessId: 301,
              ParentProcessId: 4,
              Name: imageName,
              ExecutablePath: `D:\\WXWork\\${imageName}`,
            },
          ]),
          env: { SystemRoot: "C:\\Windows" },
        }),
      /requires WeChat to be fully exited/
    );
  }
});

test("real-database smoke still blocks an existing backend or broker", () => {
  for (const imageName of ["wechat-backend.exe", "wechatdb_broker.exe"]) {
    assert.throws(
      () =>
        assertProcessPreconditions({
          spawnProcess: createProcessSnapshotSpawner([
            {
              ProcessId: 401,
              ParentProcessId: 4,
              Name: imageName,
              ExecutablePath: `C:\\runtime\\${imageName}`,
            },
          ]),
          env: { SystemRoot: "C:\\Windows" },
        }),
      /existing backend or broker process/
    );
  }
});

test("real-database smoke writes only one minimal account record", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-real-smoke-keys-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const firstRoot = path.join(root, "first", "db_storage");
  const secondRoot = path.join(root, "second", "db_storage");
  fs.mkdirSync(firstRoot, { recursive: true });
  fs.mkdirSync(secondRoot, { recursive: true });
  const source = path.join(root, "account_keys.json");
  fs.writeFileSync(
    source,
    JSON.stringify({
      second: {
        db_key: "22".repeat(32),
        db_key_source_db_storage_path: secondRoot,
        image_aes_key: "must-not-be-copied",
      },
      first: {
        db_key: "11".repeat(32),
        db_key_source_db_storage_path: firstRoot,
        image_xor_key: "must-not-be-copied",
      },
    })
  );

  const resolved = resolveKeyStoreAccounts(source);
  assert.deepEqual(resolved.accounts.map((item) => item.account), ["first", "second"]);
  const isolated = createIsolatedKeyStorePayload(resolved.accounts[0]);
  assert.deepEqual(Object.keys(isolated), ["first"]);
  assert.deepEqual(Object.keys(isolated.first).sort(), [
    "db_key",
    "db_key_source_db_storage_path",
    "db_key_source_wxid_dir",
  ]);
  assert.equal(isolated.first.db_key_source_db_storage_path, fs.realpathSync(firstRoot));
});

test("real-database smoke copies only the decrypted databases needed for search", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-real-smoke-snapshot-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceOutput = path.join(root, "source-output");
  const accountRoot = path.join(sourceOutput, "databases", "account");
  const isolatedOutput = path.join(root, "isolated-output");
  fs.mkdirSync(accountRoot, { recursive: true });
  fs.mkdirSync(isolatedOutput, { recursive: true });

  const contents = new Map([
    ["session.db", "session-fixture"],
    ["contact.db", "contact-fixture"],
    ["message_0.db", "message-fixture"],
    ["biz_message_1.db", "biz-message-fixture"],
    ["chat_search_index.db", "stale-index-must-not-copy"],
    ["media_0.db", "media-must-not-copy"],
  ]);
  for (const [name, content] of contents) {
    fs.writeFileSync(path.join(accountRoot, name), content);
  }

  const files = enumerateSearchSnapshotFiles(sourceOutput, "account");
  assert.deepEqual(
    files.map((filePath) => path.basename(filePath)),
    ["biz_message_1.db", "contact.db", "message_0.db", "session.db"]
  );
  const snapshotFiles = new Map();
  let expectedBytes = 0;
  for (const filePath of files) {
    const bytes = fs.readFileSync(filePath);
    expectedBytes += bytes.length;
    snapshotFiles.set(filePath.toLowerCase(), {
      size: bytes.length,
      sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    });
  }
  const sourceHashesBefore = files.map((filePath) =>
    crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex")
  );

  const evidence = await copySearchSnapshotFiles({
    files,
    snapshot: { files: snapshotFiles },
    outputRoot: isolatedOutput,
    account: "account",
  });
  assert.deepEqual(evidence, { databaseCount: files.length, databaseBytes: expectedBytes });
  assert.deepEqual(
    fs.readdirSync(path.join(isolatedOutput, "databases", "account")).sort(),
    files.map((filePath) => path.basename(filePath)).sort()
  );
  assert.deepEqual(
    files.map((filePath) =>
      crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex")
    ),
    sourceHashesBefore
  );
});

test("real-database smoke snapshots every protected source file and its metadata", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-real-smoke-source-tree-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const nested = path.join(root, "nested");
  fs.mkdirSync(nested, { recursive: true });
  const database = path.join(root, "message_0.db");
  const journal = path.join(root, "message_0.db-wal");
  const metadata = path.join(nested, "database.meta");
  fs.writeFileSync(database, "database");
  fs.writeFileSync(journal, "journal");
  fs.writeFileSync(metadata, "metadata");

  const files = enumerateProtectedSourceFiles([root]);
  assert.deepEqual(
    files.map((filePath) => path.relative(root, filePath).replaceAll("\\", "/")).sort(),
    ["message_0.db", "message_0.db-wal", "nested/database.meta"]
  );
  const before = await snapshotDatabaseFiles(files);
  const current = fs.statSync(metadata);
  fs.utimesSync(metadata, current.atime, new Date(current.mtimeMs + 5000));
  const after = await snapshotDatabaseFiles(enumerateProtectedSourceFiles([root]));
  assert.throws(
    () => compareDatabaseSnapshots(before, after),
    /timestamp changed during smoke/
  );
});

test("real-database smoke search snapshot whitelist excludes generated indexes and media", () => {
  for (const name of [
    "session.db",
    "contact.db",
    "head_image.db",
    "message_resource.db",
    "message.db",
    "message_12.db",
    "biz_message_3.db",
  ]) {
    assert.equal(isSearchSnapshotDatabaseName(name), true, name);
  }
  for (const name of ["chat_search_index.db", "message_fts.db", "media_0.db", "general.db"]) {
    assert.equal(isSearchSnapshotDatabaseName(name), false, name);
  }
});

test("real-database smoke refuses to copy an active SQLite snapshot", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-real-smoke-active-snapshot-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const accountRoot = path.join(root, "databases", "account");
  fs.mkdirSync(accountRoot, { recursive: true });
  for (const name of ["session.db", "contact.db", "message_0.db"]) {
    fs.writeFileSync(path.join(accountRoot, name), name);
  }
  fs.writeFileSync(path.join(accountRoot, "session.db-wal"), "active-wal");
  assert.throws(
    () => enumerateSearchSnapshotFiles(root, "account"),
    /still attached to a SQLite journal/
  );
});

test("real-database smoke follows progressive pagination cursors and rejects repeats", () => {
  const firstQuery = createMessagePageQuery({
    account: "account",
    username: "conversation",
    source: "realtime",
    limit: 10,
  });
  assert.equal(firstQuery.get("offset"), "0");
  assert.equal(firstQuery.get("scan_offset"), "0");
  assert.equal(firstQuery.get("filter_mode"), "progressive");

  const nextQuery = createNextMessagePageQuery({
    account: "account",
    username: "conversation",
    source: "realtime",
    limit: 10,
    response: { hasMore: true, nextScanOffset: 100, nextFilterOffset: 10 },
  });
  assert.equal(nextQuery.get("offset"), "10");
  assert.equal(nextQuery.get("scan_offset"), "100");
  assert.deepEqual(
    assertDisjointMessagePages([{ id: "first" }], [{ id: "second" }]),
    { firstPageCount: 1, secondPageCount: 1, duplicateCount: 0 }
  );
  assert.throws(
    () => assertDisjointMessagePages([{ id: "same" }], [{ id: "same" }]),
    /repeated a first-page message/
  );
});

test("real-database smoke selects only a unique-second text export target", () => {
  const selected = selectUniqueSecondTextMessage([
    { id: "a", renderType: "text", content: "same second first", createTime: 100 },
    { id: "b", renderType: "text", content: "same second second", createTime: 100 },
    { id: "c", renderType: "image", content: "ignored image", createTime: 101 },
    { id: "d", renderType: "text", content: "unique target", createTime: 102 },
  ]);
  assert.equal(selected?.message?.id, "d");
  assert.equal(selected?.createTime, 102);
  assert.equal(
    selectUniqueSecondTextMessage([
      { renderType: "text", content: "first", createTime: 100 },
      { renderType: "text", content: "second", createTime: 100 },
    ]),
    null
  );
});

test("real-database smoke derives bounded text probes and fails closed on index errors", () => {
  const probes = deriveSearchProbeCandidates([
    { id: "message:1", renderType: "text", content: "\u0000AlphaBeta 真实消息内容" },
    { id: "message:2", renderType: "image", content: "must-not-be-used" },
  ]);
  assert.ok(probes.length > 0);
  assert.ok(probes.every((candidate) => candidate.probe.length <= 24));
  assert.ok(probes.every((candidate) => !/[\u0000-\u001f\u007f]/.test(candidate.probe)));

  assert.deepEqual(
    searchIndexEvidence({
      status: "success",
      index: { ready: true, meta: { message_count: "42" }, build: { status: "ready" } },
    }),
    { ready: true, building: false, messageCount: 42 }
  );
  assert.throws(
    () =>
      searchIndexEvidence({
        status: "success",
        index: { ready: false, meta: {}, build: { status: "error", error: "sensitive" } },
      }),
    /search index build failed/
  );
});

test("real-database smoke always requests a bounded unencrypted privacy export", () => {
  const request = createPrivacyExportRequest({
    account: "account",
    username: "session",
    createTime: 123,
    outputDir: "C:\\acceptance",
  });
  assert.equal(request.privacy_mode, true);
  assert.equal(request.include_media, false);
  assert.equal(request.download_remote_media, false);
  assert.equal(request.encrypt, false);
  assert.equal(request.start_time, 123);
  assert.equal(request.end_time, 123);
  assert.deepEqual(request.usernames, ["session"]);
  assert.deepEqual(request.message_types, ["text"]);
});

test("real-database smoke preserves and redacts the backend privacy export error", () => {
  const account = "wxid_private_observation_fixture";
  const databasePath = "D:\\private-fixture\\message_0.db";
  const error = createPrivacyExportTerminalError({
    status: "error",
    error: `native seal failed for ${account} at ${databasePath}`,
  }, [account, databasePath]);

  assert.match(error.message, /native seal failed/);
  assert.match(error.message, /status error/);
  assert.doesNotMatch(error.message, new RegExp(account));
  assert.ok(!error.message.includes(databasePath));

  const sanitized = sanitizeError(error, [account, databasePath]);
  assert.match(sanitized, /native seal failed/);
  assert.match(sanitized, /\[redacted\]/);
  assert.doesNotMatch(sanitized, new RegExp(account));
  assert.ok(!sanitized.includes(databasePath));
});

test("real-database smoke redacts privacy errors before bounding their length", () => {
  const secret = "private-secret-crossing-the-error-boundary";
  const nestedSecret = `${secret}\\message_0.db`;
  const error = createPrivacyExportTerminalError({
    status: "error",
    error: `${"x".repeat(2040)}${secret}`,
  }, [secret]);

  assert.match(error.message, /\[redacted\]/);
  assert.ok(!error.message.includes(secret.slice(0, 8)));

  const sanitized = sanitizeError(new Error(nestedSecret), [secret, nestedSecret]);
  assert.match(sanitized, /\[redacted\]/);
  assert.ok(!sanitized.includes("message_0.db"));
});

test("real-database smoke strips project and process injection overrides from the backend", () => {
  const isolated = createIsolatedBackendEnvironment(
    {
      SystemRoot: "C:\\Windows",
      PATH: "C:\\Windows\\System32",
      WECHAT_TOOL_NATIVE_CORE_ENDPOINT: "attacker-endpoint",
      WECHAT_TOOL_WCDB_API_DLL_PATH: "legacy.dll",
      WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS: "1",
      PYTHONPATH: "injected-python",
      NODE_OPTIONS: "--require injected.js",
      HTTPS_PROXY: "http://proxy.invalid",
      no_proxy: "license.fqyw.love",
      SSLKEYLOGFILE: "C:\\capture\\tls.keys",
      SSL_CERT_FILE: "C:\\capture\\root.pem",
      REQUESTS_CA_BUNDLE: "C:\\capture\\requests.pem",
      NODE_EXTRA_CA_CERTS: "C:\\capture\\node.pem",
    },
    {
      WECHAT_TOOL_NATIVE_CORE_MODE: "required",
      WECHAT_TOOL_REALTIME_AUTOSYNC: "0",
    }
  );
  assert.equal(isolated.SystemRoot, "C:\\Windows");
  assert.equal(isolated.PATH, "C:\\Windows\\System32");
  assert.equal(isolated.WECHAT_TOOL_NATIVE_CORE_MODE, "required");
  assert.equal(isolated.WECHAT_TOOL_REALTIME_AUTOSYNC, "0");
  assert.equal(isolated.WECHAT_TOOL_NATIVE_CORE_ENDPOINT, undefined);
  assert.equal(isolated.WECHAT_TOOL_WCDB_API_DLL_PATH, undefined);
  assert.equal(isolated.WCE_NATIVE_CORE_ALLOW_DEVELOPMENT_ARTIFACTS, undefined);
  assert.equal(isolated.PYTHONPATH, undefined);
  assert.equal(isolated.NODE_OPTIONS, undefined);
  assert.equal(isolated.HTTPS_PROXY, undefined);
  assert.equal(isolated.no_proxy, undefined);
  assert.equal(isolated.SSLKEYLOGFILE, undefined);
  assert.equal(isolated.SSL_CERT_FILE, undefined);
  assert.equal(isolated.REQUESTS_CA_BUNDLE, undefined);
  assert.equal(isolated.NODE_EXTRA_CA_CERTS, undefined);
});

test("real-database smoke keeps issuer import and cleanup evidence inside cleanup guards", () => {
  const script = fs.readFileSync(
    path.join(__dirname, "..", "scripts", "smoke-windows-real-database.cjs"),
    "utf8"
  );
  const run = script.split("async function runRealDatabaseSmoke", 2)[1];
  const guardedTry = run.indexOf("try {");
  const issuerImport = run.indexOf("issuerCacheEvidence = ensurePrivatePkiIssuerCached");
  const finalizer = run.indexOf("} finally {");
  assert.ok(guardedTry >= 0 && issuerImport > guardedTry && issuerImport < finalizer);
  assert.match(run, /secureSmokeDirectory\(path\.dirname\(cleanupPath\)\)/);
  assert.ok(run.indexOf("secureSmokeDirectory(path.dirname(cleanupPath))") < run.indexOf("atomicWriteJson(cleanupPath"));
});

test("server cleanup requires explicit remote license-service coordinates", () => {
  const script = fs.readFileSync(
    path.join(__dirname, "..", "scripts", "complete-windows-real-smoke-server-cleanup.ps1"),
    "utf8"
  );
  assert.match(
    script,
    /\[Parameter\(Mandatory = \$true\)\]\[string\]\$RemoteCliPath/
  );
  assert.match(
    script,
    /\[Parameter\(Mandatory = \$true\)\]\[string\]\$RemoteDatabasePath/
  );
  assert.match(script, /\$RemoteCliPath,\s*\r?\n\s*'--database', \$RemoteDatabasePath/);
  assert.match(script, /controlledDistributionsUnbound -ne 1/);
  assert.doesNotMatch(script, /\/var\/lib\/wcl-license\/licenses\.sqlite3/);
});

test("real-database smoke updates cleanup evidence without leaving a temporary file", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-real-smoke-evidence-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const evidencePath = path.join(root, "cleanup.json");
  atomicWriteJson(evidencePath, { deleted: false });
  atomicWriteJson(evidencePath, { deleted: true }, { replace: true });
  assert.deepEqual(JSON.parse(fs.readFileSync(evidencePath, "utf8")), { deleted: true });
  assert.deepEqual(fs.readdirSync(root), ["cleanup.json"]);
});

test("Windows privacy helper accepts an integrity manifest larger than the legacy limit", {
  skip: process.platform !== "win32",
}, (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-privacy-helper-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const content = path.join(root, "content");
  const integrity = path.join(content, "_integrity");
  fs.mkdirSync(integrity, { recursive: true });
  fs.writeFileSync(
    path.join(content, "manifest.json"),
    JSON.stringify({
      account: "hidden",
      accountsAvailable: [],
      options: { privacyMode: true, includeMedia: false },
    })
  );
  fs.writeFileSync(path.join(content, "report.json"), JSON.stringify({ account: "hidden" }));
  fs.writeFileSync(
    path.join(integrity, "manifest.json"),
    Buffer.concat([
      Buffer.from('{"padding":"', "utf8"),
      Buffer.alloc(8 * 1024 * 1024, "x"),
      Buffer.from('"}\n', "utf8"),
    ])
  );
  fs.writeFileSync(path.join(integrity, "signature.wes"), Buffer.from("WES1fixture", "ascii"));
  const probePath = path.join(root, "sensitive-values.json");
  fs.writeFileSync(
    probePath,
    JSON.stringify({
      schemaVersion: 1,
      values: ["private-account", "private-session", "private-message"],
    })
  );
  const archive = path.join(root, "privacy.zip");
  const compressed = createZipFixture(content, archive, [
    { source: "manifest.json", entry: "manifest.json" },
    { source: "report.json", entry: "report.json" },
    { source: "_integrity\\manifest.json", entry: "_integrity/manifest.json" },
    { source: "_integrity\\signature.wes", entry: "_integrity/signature.wes" },
  ]);
  assert.equal(compressed.status, 0, compressed.stderr || compressed.stdout);

  const inspected = runPowerShell([
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    path.join(__dirname, "..", "scripts", "inspect-windows-privacy-export.ps1"),
    "-ArchivePath",
    archive,
    "-SensitiveValuesPath",
    probePath,
  ]);
  assert.equal(inspected.status, 0, inspected.stderr || inspected.stdout);
  const evidence = JSON.parse(inspected.stdout.trim());
  assert.equal(evidence.accountRedacted, true);
  assert.equal(evidence.accountsAvailableCount, 0);
  assert.equal(evidence.wes1Present, true);
  assert.equal(evidence.mediaEntriesPresent, false);
  assert.equal(evidence.sensitiveValuesChecked, 3);
});

test("Windows privacy helper rejects media and sensitive text entries", {
  skip: process.platform !== "win32",
}, (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-privacy-helper-negative-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const integrity = path.join(root, "_integrity");
  const media = path.join(root, "media");
  fs.mkdirSync(integrity, { recursive: true });
  fs.mkdirSync(media, { recursive: true });
  fs.writeFileSync(
    path.join(root, "manifest.json"),
    JSON.stringify({
      account: "hidden",
      accountsAvailable: [],
      options: { privacyMode: true, includeMedia: false },
    })
  );
  fs.writeFileSync(path.join(root, "report.json"), JSON.stringify({ account: "hidden" }));
  fs.writeFileSync(path.join(integrity, "manifest.json"), "{}\n");
  fs.writeFileSync(path.join(integrity, "signature.wes"), Buffer.from("WES1fixture", "ascii"));
  fs.writeFileSync(path.join(media, "leak.txt"), "private-message");
  const probePath = path.join(root, "probe.json");
  fs.writeFileSync(
    probePath,
    JSON.stringify({ schemaVersion: 1, values: ["private-message"] })
  );
  const archive = path.join(root, "privacy-with-media.zip");
  const compressed = createZipFixture(root, archive, [
    { source: "manifest.json", entry: "manifest.json" },
    { source: "report.json", entry: "report.json" },
    { source: "_integrity\\manifest.json", entry: "_integrity/manifest.json" },
    { source: "_integrity\\signature.wes", entry: "_integrity/signature.wes" },
    { source: "media\\leak.txt", entry: "media/leak.txt" },
  ]);
  assert.equal(compressed.status, 0, compressed.stderr || compressed.stdout);
  const inspected = runPowerShell([
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    path.join(__dirname, "..", "scripts", "inspect-windows-privacy-export.ps1"),
    "-ArchivePath",
    archive,
    "-SensitiveValuesPath",
    probePath,
  ]);
  assert.notEqual(inspected.status, 0, "Privacy helper accepted a media-bearing archive.");
});

test("Windows smoke temp directory helper restricts inherited ACLs", {
  skip: process.platform !== "win32",
}, (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-secure-smoke-dir-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const secured = runPowerShell([
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    path.join(__dirname, "..", "scripts", "secure-windows-smoke-directory.ps1"),
    "-DirectoryPath",
    root,
  ]);
  assert.equal(secured.status, 0, secured.stderr || secured.stdout);
  const evidence = JSON.parse(secured.stdout.trim());
  assert.equal(evidence.protected, true);
  assert.equal(evidence.currentUserOnly, true);

  const repeated = runPowerShell([
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    path.join(__dirname, "..", "scripts", "secure-windows-smoke-directory.ps1"),
    "-DirectoryPath",
    root,
  ]);
  assert.equal(repeated.status, 0, repeated.stderr || repeated.stdout);
  assert.equal(JSON.parse(repeated.stdout.trim()).currentUserOnly, true);
});

test("Windows smoke credential helper fingerprints the DPAPI credential independently of its lease", {
  skip: process.platform !== "win32",
}, (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "wda-smoke-credential-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const credentialPath = path.join(root, "device-credential.bin");
  const deviceIdHex = "21".repeat(32);
  const buildId = "release-credential-fixture";
  const serviceUrl = "https://license.fqyw.love/v1/leases";
  const credential = "fixture-device-credential-token-0123456789abcdef";
  const deviceId = Buffer.from(deviceIdHex, "hex");
  const buildDigest = crypto.createHash("sha256").update(buildId, "utf8").digest();
  const service = Buffer.from(serviceUrl, "ascii");
  const serviceLength = Buffer.alloc(4);
  serviceLength.writeUInt32BE(service.length);
  const entropy = crypto
    .createHash("sha256")
    .update(
      Buffer.concat([
        Buffer.from("WeChatDataAnalysis/native-core/device-credential/v2\0", "ascii"),
        deviceId,
        buildDigest,
        serviceLength,
        service,
      ])
    )
    .digest();

  const writeProtectedFixture = (leaseByte) => {
    const plaintext = Buffer.from(
      JSON.stringify({
        schemaVersion: 2,
        credential,
        leaseBase64: Buffer.alloc(224, leaseByte).toString("base64"),
      }),
      "utf8"
    );
    const protectedResult = runPowerShell(
      [
        "-Command",
        "Add-Type -AssemblyName System.Security;" +
          "$p=[Convert]::FromBase64String($env:WCE_DPAPI_PLAINTEXT);" +
          "$e=[Convert]::FromBase64String($env:WCE_DPAPI_ENTROPY);" +
          "$v=[Security.Cryptography.ProtectedData]::Protect(" +
          "$p,$e,[Security.Cryptography.DataProtectionScope]::CurrentUser);" +
          "[Convert]::ToBase64String($v)",
      ],
      {
        env: {
          ...process.env,
          WCE_DPAPI_PLAINTEXT: plaintext.toString("base64"),
          WCE_DPAPI_ENTROPY: entropy.toString("base64"),
        },
      }
    );
    assert.equal(protectedResult.status, 0, protectedResult.stderr || protectedResult.stdout);
    fs.writeFileSync(
      credentialPath,
      Buffer.concat([Buffer.from("WCEDC001", "ascii"), Buffer.from(protectedResult.stdout.trim(), "base64")])
    );
  };
  const inspect = () => {
    const result = runPowerShell([
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      path.join(__dirname, "..", "scripts", "inspect-windows-smoke-device-credential.ps1"),
      "-CredentialPath",
      credentialPath,
      "-DeviceIdHex",
      deviceIdHex,
      "-BuildId",
      buildId,
      "-ServiceUrl",
      serviceUrl,
    ]);
    assert.equal(result.status, 0, result.stderr || result.stdout);
    return JSON.parse(result.stdout.trim());
  };

  writeProtectedFixture(0x31);
  const first = inspect();
  writeProtectedFixture(0x32);
  const second = inspect();
  const expected = crypto.createHash("sha256").update(credential, "ascii").digest("hex");
  assert.equal(first.credentialSha256, expected);
  assert.equal(second.credentialSha256, expected);
  assert.notEqual(first.leaseSha256, second.leaseSha256);
  assert.notEqual(first.protectedFileSha256, second.protectedFileSha256);
});

test("Windows smoke CNG helper deletes the exact random software key", {
  skip: process.platform !== "win32",
}, (t) => {
  const keyName = `LifeArchiveProject.WeChatDB.Native.RealSmoke.${cryptoRandomHex()}`;
  const env = { ...process.env, WCE_TEST_CNG_KEY_NAME: keyName };
  const directDelete =
    "$p=[Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider;" +
    "$n=$env:WCE_TEST_CNG_KEY_NAME;" +
    "if([Security.Cryptography.CngKey]::Exists($n,$p,[Security.Cryptography.CngKeyOpenOptions]::Silent)){" +
    "$k=[Security.Cryptography.CngKey]::Open($n,$p,[Security.Cryptography.CngKeyOpenOptions]::Silent);" +
    "try{$k.Delete()}finally{$k.Dispose()}}";
  t.after(() => {
    const cleanup = runPowerShell(["-Command", directDelete], { env });
    assert.equal(cleanup.status, 0, cleanup.stderr || cleanup.stdout);
  });

  const created = runPowerShell(
    [
      "-Command",
      "$p=[Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider;" +
        "$o=[Security.Cryptography.CngKeyCreationParameters]::new();$o.Provider=$p;" +
        "$o.KeyUsage=[Security.Cryptography.CngKeyUsages]::Signing;" +
        "$k=[Security.Cryptography.CngKey]::Create(" +
        "[Security.Cryptography.CngAlgorithm]::ECDsaP256,$env:WCE_TEST_CNG_KEY_NAME,$o);" +
        "$k.Dispose()",
    ],
    { env }
  );
  assert.equal(created.status, 0, created.stderr || created.stdout);

  const inspected = runPowerShell(
    [
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      path.join(__dirname, "..", "scripts", "remove-windows-smoke-device-key.ps1"),
      "-Action",
      "Inspect",
      "-KeyName",
      keyName,
    ],
    { env }
  );
  assert.equal(inspected.status, 0, inspected.stderr || inspected.stdout);
  const inspection = JSON.parse(inspected.stdout.trim());
  assert.equal(inspection.found, true);
  assert.equal(inspection.deleted, false);

  const removed = runPowerShell(
    [
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      path.join(__dirname, "..", "scripts", "remove-windows-smoke-device-key.ps1"),
      "-Action",
      "Delete",
      "-KeyName",
      keyName,
    ],
    { env }
  );
  assert.equal(removed.status, 0, removed.stderr || removed.stdout);
  const deletion = JSON.parse(removed.stdout.trim());
  assert.equal(deletion.found, true);
  assert.equal(deletion.deleted, true);
  assert.equal(deletion.provider, "Microsoft Software Key Storage Provider");
  assert.equal(deletion.deviceIdHex, inspection.deviceIdHex);

  const checked = runPowerShell(
    [
      "-Command",
      "$p=[Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider;" +
        "if([Security.Cryptography.CngKey]::Exists($env:WCE_TEST_CNG_KEY_NAME,$p," +
        "[Security.Cryptography.CngKeyOpenOptions]::Silent)){exit 1}",
    ],
    { env }
  );
  assert.equal(checked.status, 0, "CNG helper left its random test key behind.");
});

test("Windows smoke CNG helper rejects an uppercase key suffix", {
  skip: process.platform !== "win32",
}, () => {
  const rejected = runPowerShell([
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    path.join(__dirname, "..", "scripts", "remove-windows-smoke-device-key.ps1"),
    "-Action",
    "Inspect",
    "-KeyName",
    "LifeArchiveProject.WeChatDB.Native.RealSmoke.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  ]);
  assert.notEqual(rejected.status, 0);
});

test("Windows smoke CNG helper fails closed for a wrong-algorithm collision", {
  skip: process.platform !== "win32",
}, (t) => {
  const keyName = `LifeArchiveProject.WeChatDB.Native.RealSmoke.${cryptoRandomHex()}`;
  const env = { ...process.env, WCE_TEST_CNG_KEY_NAME: keyName };
  const directDelete =
    "$p=[Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider;" +
    "$n=$env:WCE_TEST_CNG_KEY_NAME;" +
    "if([Security.Cryptography.CngKey]::Exists($n,$p,[Security.Cryptography.CngKeyOpenOptions]::Silent)){" +
    "$k=[Security.Cryptography.CngKey]::Open($n,$p,[Security.Cryptography.CngKeyOpenOptions]::Silent);" +
    "try{$k.Delete()}finally{$k.Dispose()}}";
  t.after(() => {
    const cleanup = runPowerShell(["-Command", directDelete], { env });
    assert.equal(cleanup.status, 0, cleanup.stderr || cleanup.stdout);
  });
  const created = runPowerShell(
    [
      "-Command",
      "$p=[Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider;" +
        "$o=[Security.Cryptography.CngKeyCreationParameters]::new();$o.Provider=$p;" +
        "$o.KeyUsage=[Security.Cryptography.CngKeyUsages]::Signing;" +
        "$k=[Security.Cryptography.CngKey]::Create(" +
        "[Security.Cryptography.CngAlgorithm]::Rsa,$env:WCE_TEST_CNG_KEY_NAME,$o);" +
        "$k.Dispose()",
    ],
    { env }
  );
  assert.equal(created.status, 0, created.stderr || created.stdout);

  const inspected = runPowerShell(
    [
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      path.join(__dirname, "..", "scripts", "remove-windows-smoke-device-key.ps1"),
      "-Action",
      "Inspect",
      "-KeyName",
      keyName,
    ],
    { env }
  );
  assert.notEqual(inspected.status, 0, "Wrong-algorithm key collision was silently ignored.");
});

function cryptoRandomHex() {
  return require("node:crypto").randomBytes(16).toString("hex");
}
