"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const HOST = String(process.env.WECHAT_TOOL_WCDB_SIDECAR_HOST || "127.0.0.1").trim() || "127.0.0.1";
const PORT = Number.parseInt(String(process.env.WECHAT_TOOL_WCDB_SIDECAR_PORT || "0").trim(), 10);
const TOKEN = String(process.env.WECHAT_TOOL_WCDB_SIDECAR_TOKEN || "").trim();

let koffi = null;
let nativeLib = null;
let nativeDllPath = "";
let initialized = false;
let protectionResults = [];
const preloadedLibs = [];
const funcs = Object.create(null);

class ApiError extends Error {
  constructor(message, rc = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.rc = rc;
    this.details = details;
  }
}

function log(message) {
  process.stderr.write(`[wcdb-sidecar] ${new Date().toISOString()} ${message}\n`);
}

function jsonResponse(res, statusCode, payload) {
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": String(body.length),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function readRequestJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on("data", (chunk) => {
      total += chunk.length;
      if (total > 16 * 1024 * 1024) {
        reject(new ApiError("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8").trim();
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(new ApiError(`invalid json: ${err?.message || err}`));
      }
    });
    req.on("error", reject);
  });
}

function parseResourcePaths() {
  const out = [];
  const seen = new Set();

  function add(value) {
    const raw = String(value || "").trim();
    if (!raw) return;
    const resolved = path.resolve(raw);
    const key = resolved.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(resolved);
  }

  const raw = String(process.env.WECHAT_TOOL_WCDB_RESOURCE_PATHS || "").trim();
  if (raw) {
    try {
      const decoded = JSON.parse(raw);
      if (Array.isArray(decoded)) {
        for (const item of decoded) add(item);
      }
    } catch {
      for (const item of raw.split(path.delimiter)) add(item);
    }
  }

  const dllDir = getDllDir();
  add(dllDir);
  add(path.dirname(dllDir));
  add(process.cwd());
  return out;
}

function getDllDir() {
  const fromEnv = String(process.env.WECHAT_TOOL_WCDB_DLL_DIR || "").trim();
  if (fromEnv) return path.resolve(fromEnv);

  const dllPath = String(process.env.WECHAT_TOOL_WCDB_API_DLL_PATH || "").trim();
  if (dllPath) return path.dirname(path.resolve(dllPath));

  return process.cwd();
}

function getDllPath() {
  const fromEnv = String(process.env.WECHAT_TOOL_WCDB_API_DLL_PATH || "").trim();
  if (fromEnv) return path.resolve(fromEnv);
  return path.join(getDllDir(), "wcdb_api.dll");
}

function loadKoffi() {
  if (koffi) return koffi;

  const koffiDir = String(process.env.WECHAT_TOOL_KOFFI_DIR || "").trim();
  if (koffiDir) {
    koffi = require(path.resolve(koffiDir));
  } else {
    koffi = require("koffi");
  }
  return koffi;
}

function tryFunc(signature) {
  try {
    return nativeLib.func(signature);
  } catch {
    return null;
  }
}

function loadNative() {
  if (nativeLib) return nativeLib;

  const ffi = loadKoffi();
  const dllDir = getDllDir();
  nativeDllPath = getDllPath();
  if (!fs.existsSync(nativeDllPath)) {
    throw new ApiError(`wcdb_api.dll not found: ${nativeDllPath}`);
  }

  try {
    process.chdir(dllDir);
  } catch {}

  for (const dep of ["WCDB.dll", "SDL2.dll", "VoipEngine.dll"]) {
    const depPath = path.join(dllDir, dep);
    if (!fs.existsSync(depPath)) continue;
    try {
      preloadedLibs.push(ffi.load(depPath));
      log(`preloaded dependency ${depPath}`);
    } catch (err) {
      log(`preload dependency failed ${depPath}: ${err?.message || err}`);
    }
  }

  nativeLib = ffi.load(nativeDllPath);
  funcs.InitProtection = tryFunc("int32 InitProtection(const char* resourcePath)");
  funcs.wcdb_init = tryFunc("int32 wcdb_init()");
  funcs.wcdb_shutdown = tryFunc("int32 wcdb_shutdown()");
  funcs.wcdb_open_account = tryFunc("int32 wcdb_open_account(const char* path, const char* key, _Out_ int64* handle)");
  funcs.wcdb_close_account = tryFunc("int32 wcdb_close_account(int64 handle)");
  funcs.wcdb_set_my_wxid = tryFunc("int32 wcdb_set_my_wxid(int64 handle, const char* wxid)");
  funcs.wcdb_get_sessions = tryFunc("int32 wcdb_get_sessions(int64 handle, _Out_ void** outJson)");
  funcs.wcdb_get_messages = tryFunc(
    "int32 wcdb_get_messages(int64 handle, const char* username, int32 limit, int32 offset, _Out_ void** outJson)"
  );
  funcs.wcdb_open_message_cursor = tryFunc(
    "int32 wcdb_open_message_cursor(int64 handle, const char* sessionId, int32 batchSize, int32 ascending, int32 beginTimestamp, int32 endTimestamp, _Out_ int64* cursor)"
  );
  funcs.wcdb_open_message_cursor_lite = tryFunc(
    "int32 wcdb_open_message_cursor_lite(int64 handle, const char* sessionId, int32 batchSize, int32 ascending, int32 beginTimestamp, int32 endTimestamp, _Out_ int64* cursor)"
  );
  funcs.wcdb_fetch_message_batch = tryFunc(
    "int32 wcdb_fetch_message_batch(int64 handle, int64 cursor, _Out_ void** outJson, _Out_ int32* hasMore)"
  );
  funcs.wcdb_close_message_cursor = tryFunc(
    "int32 wcdb_close_message_cursor(int64 handle, int64 cursor)"
  );
  funcs.wcdb_get_message_count = tryFunc(
    "int32 wcdb_get_message_count(int64 handle, const char* username, _Out_ int32* count)"
  );
  funcs.wcdb_get_display_names = tryFunc(
    "int32 wcdb_get_display_names(int64 handle, const char* usernamesJson, _Out_ void** outJson)"
  );
  funcs.wcdb_get_avatar_urls = tryFunc(
    "int32 wcdb_get_avatar_urls(int64 handle, const char* usernamesJson, _Out_ void** outJson)"
  );
  funcs.wcdb_get_contact = tryFunc(
    "int32 wcdb_get_contact(int64 handle, const char* username, _Out_ void** outJson)"
  );
  funcs.wcdb_get_group_member_count = tryFunc(
    "int32 wcdb_get_group_member_count(int64 handle, const char* chatroomId, _Out_ int32* count)"
  );
  funcs.wcdb_get_group_members = tryFunc(
    "int32 wcdb_get_group_members(int64 handle, const char* chatroomId, _Out_ void** outJson)"
  );
  funcs.wcdb_get_group_nicknames = tryFunc(
    "int32 wcdb_get_group_nicknames(int64 handle, const char* chatroomId, _Out_ void** outJson)"
  );
  funcs.wcdb_exec_query = tryFunc(
    "int32 wcdb_exec_query(int64 handle, const char* kind, const char* dbPath, const char* sql, _Out_ void** outJson)"
  );
  funcs.wcdb_update_message = tryFunc(
    "int32 wcdb_update_message(int64 handle, const char* sessionId, int64 localId, int32 createTime, const char* newContent, _Out_ void** outError)"
  );
  funcs.wcdb_delete_message = tryFunc(
    "int32 wcdb_delete_message(int64 handle, const char* sessionId, int64 localId, int32 createTime, const char* dbPathHint, _Out_ void** outError)"
  );
  funcs.wcdb_get_sns_timeline = tryFunc(
    "int32 wcdb_get_sns_timeline(int64 handle, int32 limit, int32 offset, const char* usernamesJson, const char* keyword, int32 startTime, int32 endTime, _Out_ void** outJson)"
  );
  funcs.wcdb_decrypt_sns_image = tryFunc(
    "int32 wcdb_decrypt_sns_image(void* encryptedData, int32 len, const char* key, _Out_ void** outHex)"
  );
  funcs.wcdb_get_logs = tryFunc("int32 wcdb_get_logs(_Out_ void** outJson)");
  funcs.wcdb_free_string = tryFunc("void wcdb_free_string(void* ptr)");

  if (!funcs.wcdb_init || !funcs.wcdb_open_account || !funcs.wcdb_get_logs || !funcs.wcdb_free_string) {
    throw new ApiError("wcdb_api.dll is missing required exports");
  }

  log(`loaded ${nativeDllPath}`);
  return nativeLib;
}

function requireFunc(name) {
  loadNative();
  const fn = funcs[name];
  if (!fn) throw new ApiError(`${name} not exported`, -404);
  return fn;
}

function ptrToString(ptr) {
  if (!ptr) return "";
  return loadKoffi().decode(ptr, "char", -1);
}

function freeStringPtr(ptr) {
  if (!ptr || !funcs.wcdb_free_string) return;
  try {
    funcs.wcdb_free_string(ptr);
  } catch {}
}

function getLogs() {
  try {
    loadNative();
    const out = [null];
    const rc = Number(funcs.wcdb_get_logs(out));
    try {
      if (rc !== 0 || !out[0]) return [];
      const payload = ptrToString(out[0]);
      const decoded = JSON.parse(payload || "[]");
      return Array.isArray(decoded) ? decoded.map((x) => String(x)) : [];
    } finally {
      freeStringPtr(out[0]);
    }
  } catch {
    return [];
  }
}

function callOutJson(name, args) {
  const fn = requireFunc(name);
  const out = [null];
  const rc = Number(fn(...args, out));
  try {
    if (rc !== 0) throw new ApiError(`${name} failed`, rc);
    return ptrToString(out[0]);
  } finally {
    freeStringPtr(out[0]);
  }
}

function callOutError(name, args) {
  const fn = requireFunc(name);
  const out = [null];
  const rc = Number(fn(...args, out));
  try {
    if (rc !== 0) {
      const message = ptrToString(out[0]) || `${name} failed`;
      throw new ApiError(message, rc);
    }
    return null;
  } finally {
    freeStringPtr(out[0]);
  }
}

function ensureInitialized() {
  loadNative();
  if (initialized) {
    return { initialized: true, dllPath: nativeDllPath, protection: protectionResults };
  }

  protectionResults = [];
  if (funcs.InitProtection) {
    for (const resourcePath of parseResourcePaths()) {
      try {
        const rc = Number(funcs.InitProtection(resourcePath));
        protectionResults.push({ path: resourcePath, rc });
        log(`InitProtection rc=${rc} path=${resourcePath}`);
        if (rc === 0) break;
      } catch (err) {
        protectionResults.push({ path: resourcePath, error: String(err?.message || err) });
      }
    }
  }

  const rc = Number(funcs.wcdb_init());
  if (rc !== 0) {
    throw new ApiError("wcdb_init failed", rc, { protection: protectionResults });
  }
  initialized = true;
  return { initialized: true, dllPath: nativeDllPath, protection: protectionResults };
}

function normalizeHandle(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) throw new ApiError("invalid handle");
  return n;
}

function handleAction(action, payload) {
  const data = payload && typeof payload === "object" ? payload : {};

  switch (action) {
    case "init":
      return ensureInitialized();

    case "get_logs":
      loadNative();
      return { logs: getLogs() };

    case "open_account": {
      ensureInitialized();
      const dbPath = String(data.path || "").trim();
      const key = String(data.key || "").trim();
      if (!dbPath) throw new ApiError("missing account path");
      if (key.length !== 64) throw new ApiError("invalid db key");
      const out = [0];
      const rc = Number(requireFunc("wcdb_open_account")(dbPath, key, out));
      const handle = Number(out[0] || 0);
      if (rc !== 0 || handle <= 0) throw new ApiError("wcdb_open_account failed", rc);
      return { handle };
    }

    case "close_account": {
      const handle = normalizeHandle(data.handle);
      try {
        requireFunc("wcdb_close_account")(handle);
      } catch {}
      return { closed: true };
    }

    case "set_my_wxid": {
      const fn = requireFunc("wcdb_set_my_wxid");
      const rc = Number(fn(normalizeHandle(data.handle), String(data.wxid || "").trim()));
      return { success: rc === 0, rc };
    }

    case "get_sessions":
      return { payload: callOutJson("wcdb_get_sessions", [normalizeHandle(data.handle)]) };

    case "get_messages":
      return {
        payload: callOutJson("wcdb_get_messages", [
          normalizeHandle(data.handle),
          String(data.username || "").trim(),
          Number.parseInt(String(data.limit || 0), 10) || 0,
          Number.parseInt(String(data.offset || 0), 10) || 0,
        ]),
      };

    case "open_message_cursor":
    case "open_message_cursor_lite": {
      const fnName = action === "open_message_cursor_lite" ? "wcdb_open_message_cursor_lite" : "wcdb_open_message_cursor";
      const out = [0];
      const rc = Number(
        requireFunc(fnName)(
          normalizeHandle(data.handle),
          String(data.session_id || "").trim(),
          Number.parseInt(String(data.batch_size || 0), 10) || 1,
          data.ascending ? 1 : 0,
          Number.parseInt(String(data.begin_timestamp || 0), 10) || 0,
          Number.parseInt(String(data.end_timestamp || 0), 10) || 0,
          out
        )
      );
      const cursor = Number(out[0] || 0);
      if (rc !== 0 || cursor <= 0) throw new ApiError(`${fnName} failed`, rc);
      return { cursor, rc };
    }

    case "fetch_message_batch": {
      const fn = requireFunc("wcdb_fetch_message_batch");
      const out = [null];
      const outHasMore = [0];
      const rc = Number(fn(normalizeHandle(data.handle), normalizeHandle(data.cursor), out, outHasMore));
      try {
        if (rc !== 0 || !out[0]) throw new ApiError("wcdb_fetch_message_batch failed", rc);
        return {
          payload: ptrToString(out[0]),
          hasMore: Number(outHasMore[0] || 0) === 1,
          rc,
        };
      } finally {
        freeStringPtr(out[0]);
      }
    }

    case "close_message_cursor": {
      const rc = Number(requireFunc("wcdb_close_message_cursor")(normalizeHandle(data.handle), normalizeHandle(data.cursor)));
      return { closed: rc === 0, rc };
    }

    case "get_message_count": {
      const out = [0];
      const rc = Number(
        requireFunc("wcdb_get_message_count")(normalizeHandle(data.handle), String(data.username || "").trim(), out)
      );
      return { count: rc === 0 ? Number(out[0] || 0) : 0, rc };
    }

    case "get_display_names":
      return {
        payload: callOutJson("wcdb_get_display_names", [
          normalizeHandle(data.handle),
          JSON.stringify(Array.isArray(data.usernames) ? data.usernames : []),
        ]),
      };

    case "get_avatar_urls":
      return {
        payload: callOutJson("wcdb_get_avatar_urls", [
          normalizeHandle(data.handle),
          JSON.stringify(Array.isArray(data.usernames) ? data.usernames : []),
        ]),
      };

    case "get_contact":
      return {
        payload: callOutJson("wcdb_get_contact", [
          normalizeHandle(data.handle),
          String(data.username || "").trim(),
        ]),
      };

    case "get_group_members":
      return {
        payload: callOutJson("wcdb_get_group_members", [
          normalizeHandle(data.handle),
          String(data.chatroom_id || "").trim(),
        ]),
      };

    case "get_group_nicknames":
      return {
        payload: callOutJson("wcdb_get_group_nicknames", [
          normalizeHandle(data.handle),
          String(data.chatroom_id || "").trim(),
        ]),
      };

    case "exec_query":
      return {
        payload: callOutJson("wcdb_exec_query", [
          normalizeHandle(data.handle),
          String(data.kind || "").trim(),
          data.path == null ? null : String(data.path || "").trim(),
          String(data.sql || ""),
        ]),
      };

    case "update_message":
      callOutError("wcdb_update_message", [
        normalizeHandle(data.handle),
        String(data.session_id || "").trim(),
        Number(data.local_id || 0),
        Number.parseInt(String(data.create_time || 0), 10) || 0,
        String(data.new_content || ""),
      ]);
      return { success: true };

    case "delete_message":
      callOutError("wcdb_delete_message", [
        normalizeHandle(data.handle),
        String(data.session_id || "").trim(),
        Number(data.local_id || 0),
        Number.parseInt(String(data.create_time || 0), 10) || 0,
        String(data.db_path_hint || ""),
      ]);
      return { success: true };

    case "get_sns_timeline":
      return {
        payload: callOutJson("wcdb_get_sns_timeline", [
          normalizeHandle(data.handle),
          Number.parseInt(String(data.limit || 0), 10) || 0,
          Number.parseInt(String(data.offset || 0), 10) || 0,
          JSON.stringify(Array.isArray(data.usernames) ? data.usernames : []),
          String(data.keyword || ""),
          Number.parseInt(String(data.start_time || 0), 10) || 0,
          Number.parseInt(String(data.end_time || 0), 10) || 0,
        ]),
      };

    case "decrypt_sns_image": {
      ensureInitialized();
      const raw = Buffer.from(String(data.data_b64 || ""), "base64");
      if (!raw.length) return { data_b64: "" };
      const key = String(data.key || "").trim();
      if (!key) return { data_b64: raw.toString("base64") };

      const out = [null];
      const rc = Number(requireFunc("wcdb_decrypt_sns_image")(raw, raw.length, key, out));
      try {
        if (rc !== 0 || !out[0]) return { data_b64: raw.toString("base64"), rc };
        const hex = ptrToString(out[0]).replace(/[^0-9a-f]/gi, "");
        if (!hex) return { data_b64: raw.toString("base64"), rc };
        return { data_b64: Buffer.from(hex, "hex").toString("base64"), rc };
      } finally {
        freeStringPtr(out[0]);
      }
    }

    case "shutdown": {
      if (nativeLib && initialized && funcs.wcdb_shutdown) {
        try {
          funcs.wcdb_shutdown();
        } finally {
          initialized = false;
        }
      }
      return { shutdown: true };
    }

    default:
      throw new ApiError(`unknown action: ${action}`);
  }
}

async function handleRequest(req, res) {
  try {
    if (req.method === "GET" && req.url === "/health") {
      jsonResponse(res, 200, { ok: true, initialized, dllPath: nativeDllPath || getDllPath() });
      return;
    }

    if (req.method !== "POST" || req.url !== "/call") {
      jsonResponse(res, 404, { ok: false, error: "not found" });
      return;
    }

    if (TOKEN && String(req.headers["x-wcdb-sidecar-token"] || "") !== TOKEN) {
      jsonResponse(res, 401, { ok: false, error: "unauthorized" });
      return;
    }

    const body = await readRequestJson(req);
    const action = String(body?.action || "").trim();
    const result = handleAction(action, body?.payload || {});
    jsonResponse(res, 200, { ok: true, result });
  } catch (err) {
    const rc = Number.isFinite(err?.rc) ? Number(err.rc) : 0;
    const error = err?.message || String(err);
    log(`error rc=${rc} message=${error}`);
    jsonResponse(res, 200, {
      ok: false,
      error,
      rc,
      details: err?.details || null,
      logs: getLogs().slice(-20),
    });
  }
}

if (!Number.isInteger(PORT) || PORT <= 0 || PORT > 65535) {
  log(`invalid sidecar port: ${process.env.WECHAT_TOOL_WCDB_SIDECAR_PORT || ""}`);
  process.exit(2);
}

const server = http.createServer((req, res) => {
  void handleRequest(req, res);
});

server.listen(PORT, HOST, () => {
  log(`listening http://${HOST}:${PORT} dll=${getDllPath()} koffi=${process.env.WECHAT_TOOL_KOFFI_DIR || "node_modules"}`);
});

process.on("SIGTERM", () => {
  try {
    server.close(() => process.exit(0));
  } catch {
    process.exit(0);
  }
});

process.on("SIGINT", () => {
  try {
    server.close(() => process.exit(0));
  } catch {
    process.exit(0);
  }
});
