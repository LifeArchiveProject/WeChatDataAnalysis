/* Bundled from WeQ flash-transfer protocol at edc61a911e719858f24ffb38d1af9d9a27c0aa49; see THIRD_PARTY_NOTICES.md. */
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// output/qq-feedback-bundle-entry.ts
var qq_feedback_bundle_entry_exports = {};
__export(qq_feedback_bundle_entry_exports, {
  SendFlashMsg: () => SendFlashMsg,
  createFlashFileset: () => createFlashFileset,
  stageFlashFileset: () => stageFlashFileset,
  uploadFlashMainFiles: () => uploadFlashMainFiles
});
module.exports = __toCommonJS(qq_feedback_bundle_entry_exports);

// WeQ/packages/protocol/src/oidb/flashtransfer/upload.ts
var import_node_crypto6 = require("node:crypto");
var import_node_fs3 = require("node:fs");
var import_node_path = require("node:path");

// WeQ/packages/protocol/src/highway/hash-file.ts
var import_node_crypto2 = require("node:crypto");
var import_node_fs = require("node:fs");

// WeQ/packages/protocol/src/highway/sha1-stream.ts
var import_node_crypto = require("node:crypto");
var SHA1_BLOCK_SIZE = 64;
var SHA1_DIGEST_SIZE = 20;
function rotl(x, n) {
  return (x << n | x >>> 32 - n) >>> 0;
}
var Sha1Stream = class {
  state = new Uint32Array(5);
  count = new Uint32Array(2);
  // [low, high] bit count
  buffer = new Uint8Array(SHA1_BLOCK_SIZE);
  constructor() {
    this.reset();
  }
  reset() {
    this.state[0] = 1732584193;
    this.state[1] = 4023233417;
    this.state[2] = 2562383102;
    this.state[3] = 271733878;
    this.state[4] = 3285377520;
    this.count[0] = 0;
    this.count[1] = 0;
  }
  transform(data, offset) {
    const w = new Uint32Array(80);
    const dv = new DataView(data.buffer, data.byteOffset + offset, 64);
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(i * 4, false);
    for (let i = 16; i < 80; i++) {
      w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    }
    let a = this.state[0];
    let b = this.state[1];
    let c = this.state[2];
    let d = this.state[3];
    let e = this.state[4];
    for (let i = 0; i < 80; i++) {
      let temp;
      if (i < 20) temp = (b & c | ~b & d) + 1518500249;
      else if (i < 40) temp = (b ^ c ^ d) + 1859775393;
      else if (i < 60) temp = (b & c | b & d | c & d) + 2400959708;
      else temp = (b ^ c ^ d) + 3395469782;
      temp = temp + rotl(a, 5) + e + w[i] >>> 0;
      e = d;
      d = c;
      c = rotl(b, 30);
      b = a;
      a = temp;
    }
    this.state[0] = this.state[0] + a >>> 0;
    this.state[1] = this.state[1] + b >>> 0;
    this.state[2] = this.state[2] + c >>> 0;
    this.state[3] = this.state[3] + d >>> 0;
    this.state[4] = this.state[4] + e >>> 0;
  }
  update(data) {
    const len = data.length;
    let index = this.count[0] >>> 3 & 63;
    this.count[0] = this.count[0] + (len << 3) >>> 0;
    if (this.count[0] < len << 3) this.count[1] = this.count[1] + 1 >>> 0;
    this.count[1] = this.count[1] + (len >>> 29) >>> 0;
    const partLen = SHA1_BLOCK_SIZE - index;
    let i = 0;
    if (len >= partLen) {
      this.buffer.set(data.subarray(0, partLen), index);
      this.transform(this.buffer, 0);
      i = partLen;
      while (i + SHA1_BLOCK_SIZE <= len) {
        this.transform(data, i);
        i += SHA1_BLOCK_SIZE;
      }
      index = 0;
    }
    this.buffer.set(data.subarray(i), index);
  }
  /** 输出当前 state(20B)。littleEndian=true 小端,false 大端。不 finalize。 */
  hash(littleEndian) {
    const digest = new Uint8Array(SHA1_DIGEST_SIZE);
    const dv = new DataView(digest.buffer);
    for (let i = 0; i < 5; i++) {
      if (littleEndian) dv.setUint32(i * 4, this.state[i], true);
      else dv.setUint32(i * 4, this.state[i], false);
    }
    return digest;
  }
};
function computeSha1StateV(bytes, sliceCount, sliceSize) {
  const states = [];
  const sha1 = new Sha1Stream();
  for (let i = 0; i < sliceCount; i++) {
    const start = i * sliceSize;
    const end = Math.min(start + sliceSize, bytes.length);
    sha1.update(bytes.subarray(start, end));
    if (i !== sliceCount - 1) {
      states.push(sha1.hash(true));
    } else {
      states.push(new Uint8Array((0, import_node_crypto.createHash)("sha1").update(Buffer.from(bytes)).digest()));
    }
  }
  return states;
}

// WeQ/packages/protocol/src/highway/hash-file.ts
var FLASH_SLICE_SIZE = 1024 * 1024;
function computeHashes(bytes) {
  const md5 = (0, import_node_crypto2.createHash)("md5").update(Buffer.from(bytes)).digest();
  const sha1 = (0, import_node_crypto2.createHash)("sha1").update(Buffer.from(bytes)).digest();
  return {
    md5: new Uint8Array(md5),
    sha1: new Uint8Array(sha1),
    md5Hex: md5.toString("hex"),
    sha1Hex: sha1.toString("hex")
  };
}
async function readFileRange(filePath, start, len) {
  const handle = await import_node_fs.promises.open(filePath, "r");
  try {
    const buf = Buffer.alloc(len);
    const { bytesRead } = await handle.read(buf, 0, len, start);
    return new Uint8Array(buf.subarray(0, bytesRead));
  } finally {
    await handle.close();
  }
}
async function hashFlashFileStreaming(filePath) {
  const { size } = await import_node_fs.promises.stat(filePath);
  const sliceCount = Math.ceil(size / FLASH_SLICE_SIZE);
  const md5 = (0, import_node_crypto2.createHash)("md5");
  const sha1 = (0, import_node_crypto2.createHash)("sha1");
  const blockSha1 = new Sha1Stream();
  const sha1StateV = [];
  let offset = 0;
  let sliceIndex = 0;
  while (offset < size) {
    const len = Math.min(FLASH_SLICE_SIZE, size - offset);
    const chunk = await readFileRange(filePath, offset, len);
    md5.update(Buffer.from(chunk));
    sha1.update(Buffer.from(chunk));
    blockSha1.update(chunk);
    if (sliceIndex !== sliceCount - 1) {
      sha1StateV.push(blockSha1.hash(true));
    }
    offset += len;
    sliceIndex += 1;
  }
  const sha1Digest = sha1.digest();
  if (sliceCount > 0) {
    sha1StateV.push(new Uint8Array(sha1Digest));
  }
  const md5Digest = md5.digest();
  return {
    md5: new Uint8Array(md5Digest),
    sha1: new Uint8Array(sha1Digest),
    md5Hex: md5Digest.toString("hex"),
    sha1Hex: sha1Digest.toString("hex"),
    sha1StateV,
    sliceCount
  };
}

// WeQ/packages/protocol/src/highway/sliceupload.ts
var import_node_crypto3 = require("node:crypto");

// WeQ/packages/protocol/src/protobuf.ts
function message(fields) {
  return { fields };
}
function isMessage(type) {
  return typeof type !== "string";
}
var WIRE_VARINT = 0;
var WIRE_LEN = 2;
function wireOf(type) {
  if (isMessage(type)) return WIRE_LEN;
  return type === "string" || type === "bytes" ? WIRE_LEN : WIRE_VARINT;
}
var Writer = class {
  buf = [];
  varint(value) {
    let v = value;
    while (v > 0x7fn) {
      this.buf.push(Number(v & 0x7fn | 0x80n));
      v >>= 7n;
    }
    this.buf.push(Number(v));
  }
  tag(field, wire) {
    this.varint(BigInt(field) << 3n | BigInt(wire));
  }
  lenDelim(bytes) {
    this.varint(BigInt(bytes.length));
    for (let i = 0; i < bytes.length; i++) this.buf.push(bytes[i]);
  }
  finish() {
    return Uint8Array.from(this.buf);
  }
};
var UTF8_ENCODER = new TextEncoder();
var UTF8_DECODER = new TextDecoder();
function toBigInt(v) {
  return typeof v === "bigint" ? v : BigInt(v);
}
function zigzag(n) {
  return BigInt.asUintN(64, n << 1n ^ n >> 63n);
}
function writeScalar(w, type, tag, value, force) {
  switch (type) {
    case "bool": {
      const b = value === true;
      if (force || b) {
        w.tag(tag, WIRE_VARINT);
        w.varint(b ? 1n : 0n);
      }
      return;
    }
    case "string": {
      const s = String(value);
      if (force || s !== "") {
        w.tag(tag, WIRE_LEN);
        w.lenDelim(UTF8_ENCODER.encode(s));
      }
      return;
    }
    case "bytes": {
      const b = value;
      if (force || b.length > 0) {
        w.tag(tag, WIRE_LEN);
        w.lenDelim(b);
      }
      return;
    }
    case "sint32":
    case "sint64": {
      const n = toBigInt(value);
      if (force || n !== 0n) {
        w.tag(tag, WIRE_VARINT);
        w.varint(zigzag(n));
      }
      return;
    }
    default: {
      const n = toBigInt(value);
      if (force || n !== 0n) {
        w.tag(tag, WIRE_VARINT);
        w.varint(BigInt.asUintN(64, n));
      }
    }
  }
}
function writeField(w, field, value, force) {
  if (isMessage(field.type)) {
    if (value == null) return;
    w.tag(field.tag, WIRE_LEN);
    w.lenDelim(encode(field.type, value));
    return;
  }
  writeScalar(w, field.type, field.tag, value, force);
}
function encode(schema, obj) {
  const w = new Writer();
  for (const field of schema.fields) {
    const value = obj[field.name];
    if (value == null) continue;
    if (field.repeated) {
      if (!Array.isArray(value)) continue;
      for (const item of value) {
        if (item == null) continue;
        writeField(w, field, item, true);
      }
    } else {
      writeField(w, field, value, field.force === true);
    }
  }
  return w.finish();
}
var Reader = class {
  constructor(data) {
    this.data = data;
  }
  pos = 0;
  get eof() {
    return this.pos >= this.data.length;
  }
  varint() {
    let result = 0n;
    let shift = 0n;
    let byte;
    do {
      byte = this.data[this.pos++];
      result |= BigInt(byte & 127) << shift;
      shift += 7n;
    } while (byte & 128);
    return result;
  }
  tag() {
    const t = this.varint();
    return { field: Number(t >> 3n), wire: Number(t & 7n) };
  }
  lenDelim() {
    const len = Number(this.varint());
    const out = this.data.subarray(this.pos, this.pos + len);
    this.pos += len;
    return out;
  }
  skip(wire) {
    switch (wire) {
      case 0:
        this.varint();
        return;
      case 1:
        this.pos += 8;
        return;
      case 2: {
        const len = Number(this.varint());
        this.pos += len;
        return;
      }
      case 5:
        this.pos += 4;
        return;
      default:
        throw new Error(`protobuf: unknown wire type ${wire}`);
    }
  }
};
function readScalar(r, type) {
  switch (type) {
    case "bool":
      return r.varint() !== 0n;
    case "string":
      return UTF8_DECODER.decode(r.lenDelim());
    case "bytes":
      return r.lenDelim().slice();
    case "int32":
      return Number(BigInt.asIntN(32, r.varint()));
    case "uint32":
      return Number(BigInt.asUintN(32, r.varint()));
    case "sint32":
      return Number(BigInt.asIntN(32, unzigzag(r.varint())));
    case "int64":
      return BigInt.asIntN(64, r.varint());
    case "uint64":
      return r.varint();
    case "sint64":
      return BigInt.asIntN(64, unzigzag(r.varint()));
  }
}
function unzigzag(n) {
  return n >> 1n ^ -(n & 1n);
}
function decode(schema, data) {
  const byTag = /* @__PURE__ */ new Map();
  for (const f of schema.fields) byTag.set(f.tag, f);
  const r = new Reader(data);
  const out = {};
  while (!r.eof) {
    const { field, wire } = r.tag();
    const def = byTag.get(field);
    if (!def || wire !== wireOf(def.type)) {
      r.skip(wire);
      continue;
    }
    const value = isMessage(def.type) ? decode(def.type, r.lenDelim()) : readScalar(r, def.type);
    if (def.repeated) {
      const arr = out[def.name] ?? [];
      arr.push(value);
      out[def.name] = arr;
    } else {
      out[def.name] = value;
    }
  }
  return out;
}

// WeQ/packages/protocol/src/highway/sliceupload.ts
var SLICEUPLOAD_URL = "https://multimedia.qfile.qq.com/sliceupload";
var FLASH_EMPTY = message([]);
var FLASH_SHA1_STATE_V = message([
  { name: "state", tag: 1, type: "bytes", repeated: true }
]);
var FLASH_SLICE_PAYLOAD = message([
  { name: "field1", tag: 1, type: FLASH_EMPTY },
  { name: "rkey", tag: 2, type: "string" },
  { name: "start", tag: 3, type: "uint32", force: true },
  { name: "end", tag: 4, type: "uint32", force: true },
  { name: "sha1", tag: 5, type: "bytes" },
  { name: "sha1StateV", tag: 6, type: FLASH_SHA1_STATE_V },
  { name: "chunk", tag: 7, type: "bytes" }
]);
var FLASH_SLICE_UPLOAD_BODY = message([
  { name: "field1", tag: 1, type: "uint32", force: true },
  { name: "appid", tag: 2, type: "uint32", force: true },
  { name: "field3", tag: 3, type: "uint32", force: true },
  { name: "payload", tag: 107, type: FLASH_SLICE_PAYLOAD }
]);
var FLASH_SLICE_UPLOAD_RESP = message([{ name: "status", tag: 5, type: "string" }]);
function buildSliceBody(part, opts) {
  return encode(FLASH_SLICE_UPLOAD_BODY, {
    field1: 0,
    appid: opts?.appid ?? 14901,
    field3: 2,
    payload: {
      field1: {},
      rkey: part.rkey,
      start: part.start,
      end: part.end,
      sha1: part.sha1,
      sha1StateV: { state: part.sha1StateV.map((s) => new Uint8Array(s)) },
      chunk: part.chunk
    }
  });
}
async function postSliceupload(bodyBytes, label) {
  const reqAppid = decode(FLASH_SLICE_UPLOAD_BODY, bodyBytes).appid;
  console.log(
    `[sliceupload] ${label}: POST ${SLICEUPLOAD_URL} body=${bodyBytes.length}B appid=${reqAppid}`
  );
  const resp = await fetch(SLICEUPLOAD_URL, {
    method: "POST",
    body: new Uint8Array(bodyBytes),
    headers: {
      Accept: "*/*",
      Connection: "Keep-Alive",
      "User-Agent": "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2)",
      Pragma: "no-cache",
      "Cache-Control": "no-cache",
      "Content-Length": String(bodyBytes.length),
      "X-Retried-Times": "1"
    }
  });
  if (!resp.ok) {
    const errBody = await resp.text().catch(() => "");
    console.error(`[sliceupload] ${label}: HTTP ${resp.status} \u54CD\u5E94=${errBody.slice(0, 300)}`);
    throw new Error(`${label} failed: HTTP ${resp.status} ${errBody.slice(0, 300)}`);
  }
  const respBuf = new Uint8Array(await resp.arrayBuffer());
  const status = decode(FLASH_SLICE_UPLOAD_RESP, respBuf).status;
  console.log(`[sliceupload] ${label}: HTTP ${resp.status}, status=${JSON.stringify(status)}`);
  if (status !== "success") {
    console.error(
      `[sliceupload] ${label}: \u4E1A\u52A1\u5931\u8D25, \u539F\u59CB\u54CD\u5E94=${Buffer.from(respBuf).toString("hex").slice(0, 400)}`
    );
    throw new Error(
      `${label} failed: ${typeof status === "string" ? status : "no status in response"}`
    );
  }
}
async function sliceuploadFile(filePath, fileSize, rkey, sha1StateV, sliceCount, fileName) {
  for (let i = 0; i < sliceCount; i++) {
    const start = i * FLASH_SLICE_SIZE;
    const chunkLen = Math.min(FLASH_SLICE_SIZE, fileSize - start);
    const chunk = await readFileRange(filePath, start, chunkLen);
    const chunkSha1 = new Uint8Array((0, import_node_crypto3.createHash)("sha1").update(Buffer.from(chunk)).digest());
    console.log(
      `[sliceupload] ${fileName} slice ${i}: start=${start} end=${start + chunkLen - 1} len=${chunkLen} sha1=${Buffer.from(chunkSha1).toString("hex")}`
    );
    const bodyBytes = buildSliceBody({
      rkey,
      start,
      end: start + chunkLen - 1,
      sha1: chunkSha1,
      sha1StateV,
      chunk
    });
    await postSliceupload(bodyBytes, `${fileName} slice ${i}`);
  }
}

// WeQ/packages/protocol/src/transport.ts
async function sendOidb(nt, pid, req) {
  const reply = await nt.sendOidbPacket(
    pid,
    req.command,
    req.subCommand,
    Buffer.from(req.body),
    req.isUid ?? false
  );
  return new Uint8Array(reply);
}

// WeQ/packages/protocol/src/oidb/invoke.ts
async function invokeOidb(nt, pid, spec, params) {
  const reqBytes = encode(spec.reqSchema, spec.serialize(params));
  const respBytes = await sendOidb(nt, pid, {
    command: spec.command,
    subCommand: spec.subCommand,
    body: reqBytes,
    isUid: spec.uinForm ?? false
  });
  return spec.deserialize(decode(spec.respSchema, respBytes));
}

// WeQ/packages/protocol/src/oidb/shared.ts
function toInt(value) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "bigint") {
    const n = Number(value);
    return Number.isFinite(n) ? Math.trunc(n) : 0;
  }
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    return Number.isFinite(n) ? Math.trunc(n) : 0;
  }
  return 0;
}

// WeQ/packages/protocol/src/oidb/flashtransfer/schemas.ts
var FLASH_EMPTY2 = message([]);
var FLASH_APPLY_HEAD_SUB = message([
  { name: "seq", tag: 1, type: "uint32" },
  { name: "sub", tag: 2, type: "uint32" }
]);
var FLASH_APPLY_HEAD_CONFIG = message([
  { name: "field101", tag: 101, type: "uint32" },
  { name: "field102", tag: 102, type: "uint32" },
  { name: "field103", tag: 103, type: "uint32" },
  { name: "field200", tag: 200, type: "uint32" }
]);
var FLASH_APPLY_HEAD_FLAG = message([{ name: "field1", tag: 1, type: "uint32" }]);
var FLASH_APPLY_HEAD = message([
  { name: "sub", tag: 1, type: FLASH_APPLY_HEAD_SUB },
  { name: "config", tag: 2, type: FLASH_APPLY_HEAD_CONFIG },
  { name: "field3", tag: 3, type: FLASH_APPLY_HEAD_FLAG }
]);
var FLASH_APPLY_HEAD_RESP = message([
  { name: "sub", tag: 1, type: FLASH_APPLY_HEAD_SUB },
  { name: "msg", tag: 3, type: "string" }
]);
var FLASH_APPLY_FILE_INFO5 = message([
  { name: "field1", tag: 1, type: "uint32", force: true },
  { name: "field2", tag: 2, type: "uint32", force: true },
  { name: "field3", tag: 3, type: "uint32", force: true },
  { name: "field4", tag: 4, type: "uint32", force: true }
]);
var FLASH_APPLY_FILE_INFO = message([
  { name: "fileSize", tag: 1, type: "uint32", force: true },
  { name: "md5", tag: 2, type: "string", force: true },
  { name: "sha1", tag: 3, type: "string", force: true },
  { name: "fileName", tag: 4, type: "string", force: true },
  { name: "field5", tag: 5, type: FLASH_APPLY_FILE_INFO5 },
  { name: "field6", tag: 6, type: "uint32", force: true },
  { name: "field7", tag: 7, type: "uint32", force: true },
  { name: "field8", tag: 8, type: "uint32", force: true },
  { name: "field9", tag: 9, type: "uint32", force: true }
]);
var FLASH_APPLY_PAYLOAD_FIELD3 = message([
  { name: "field1", tag: 1, type: "uint32", force: true },
  { name: "field2", tag: 2, type: "uint32", force: true },
  { name: "field3", tag: 3, type: "uint32", force: true },
  { name: "field4", tag: 4, type: FLASH_EMPTY2 }
]);
var FLASH_APPLY_FILESET_WRAP = message([
  { name: "filesetUuid", tag: 1, type: "string", force: true },
  { name: "uploadKey", tag: 2, type: "string", force: true },
  { name: "fileUuid", tag: 3, type: "string", force: true },
  { name: "field4", tag: 4, type: "uint32", force: true },
  { name: "field5", tag: 5, type: "uint32", force: true },
  { name: "field6", tag: 6, type: "uint32", force: true },
  { name: "field7", tag: 7, type: "uint32", force: true },
  { name: "field8", tag: 8, type: FLASH_EMPTY2 },
  { name: "field9", tag: 9, type: "uint32", force: true },
  { name: "field10", tag: 10, type: "uint32", force: true },
  { name: "field11", tag: 11, type: "uint32", force: true },
  { name: "field12", tag: 12, type: "uint32", force: true },
  { name: "field13", tag: 13, type: "uint32", force: true },
  { name: "field14", tag: 14, type: "uint32", force: true }
]);
var FLASH_APPLY_UPLOAD_WRAPPER = message([
  { name: "fileInfo", tag: 1, type: FLASH_APPLY_FILE_INFO },
  { name: "fileId", tag: 2, type: "string", force: true },
  { name: "field3", tag: 3, type: "uint32", force: true },
  { name: "field4", tag: 4, type: "uint32", force: true },
  { name: "field5", tag: 5, type: "uint32", force: true },
  { name: "field6", tag: 6, type: "uint32", force: true }
]);
var FLASH_APPLY_FLAG2 = message([{ name: "field1", tag: 1, type: "uint32", force: true }]);
var FLASH_APPLY_UPLOAD_PAYLOAD = message([
  { name: "wrapper", tag: 1, type: FLASH_APPLY_UPLOAD_WRAPPER },
  { name: "flag2", tag: 2, type: FLASH_APPLY_FLAG2 },
  { name: "field3", tag: 3, type: FLASH_APPLY_PAYLOAD_FIELD3 },
  { name: "filesetWrap", tag: 10, type: FLASH_APPLY_FILESET_WRAP }
]);
var FLASH_APPLY_UPLOAD_REQ = message([
  { name: "head", tag: 1, type: FLASH_APPLY_HEAD },
  { name: "payload", tag: 12, type: FLASH_APPLY_UPLOAD_PAYLOAD }
]);
var FLASH_RKEY_WRAP = message([{ name: "rkey", tag: 1, type: "string" }]);
var FLASH_APPLY_UPLOAD_RESP = message([
  { name: "head", tag: 1, type: FLASH_APPLY_HEAD_RESP },
  { name: "rkeyWrap", tag: 2, type: FLASH_RKEY_WRAP }
]);
var FLASH_PREPARE_PAYLOAD_F6_F1 = message([
  { name: "field1", tag: 1, type: "uint32", force: true },
  { name: "field2", tag: 2, type: FLASH_EMPTY2 }
]);
var FLASH_PREPARE_PAYLOAD_F6_F2 = message([{ name: "field3", tag: 3, type: FLASH_EMPTY2 }]);
var FLASH_PREPARE_PAYLOAD_F6_F3 = message([
  { name: "field11", tag: 11, type: FLASH_EMPTY2 },
  { name: "field12", tag: 12, type: FLASH_EMPTY2 }
]);
var FLASH_PREPARE_PAYLOAD_F6 = message([
  { name: "field1", tag: 1, type: FLASH_PREPARE_PAYLOAD_F6_F1 },
  { name: "field2", tag: 2, type: FLASH_PREPARE_PAYLOAD_F6_F2 },
  { name: "field3", tag: 3, type: FLASH_PREPARE_PAYLOAD_F6_F3 },
  { name: "field10", tag: 10, type: "uint32", force: true }
]);
var FLASH_PREPARE_WRAPPER = message([
  { name: "fileInfo", tag: 1, type: FLASH_APPLY_FILE_INFO },
  { name: "field2", tag: 2, type: "uint32", force: true }
]);
var FLASH_PREPARE_UPLOAD_PAYLOAD = message([
  { name: "wrapper", tag: 1, type: FLASH_PREPARE_WRAPPER },
  { name: "field2", tag: 2, type: "uint32", force: true },
  { name: "field3", tag: 3, type: "uint32", force: true },
  { name: "field4", tag: 4, type: "uint32", force: true },
  { name: "field5", tag: 5, type: "uint32", force: true },
  { name: "field6", tag: 6, type: FLASH_PREPARE_PAYLOAD_F6 },
  { name: "field7", tag: 7, type: "uint32", force: true },
  { name: "field8", tag: 8, type: "uint32", force: true },
  { name: "filesetWrap", tag: 9, type: FLASH_APPLY_FILESET_WRAP }
]);
var FLASH_PREPARE_UPLOAD_REQ = message([
  { name: "head", tag: 1, type: FLASH_APPLY_HEAD },
  { name: "payload", tag: 2, type: FLASH_PREPARE_UPLOAD_PAYLOAD }
]);
var FLASH_PREPARE_UPLOAD_RESP = message([
  { name: "head", tag: 1, type: FLASH_APPLY_HEAD_RESP },
  { name: "rkeyWrap", tag: 2, type: FLASH_RKEY_WRAP }
]);
var FLASH_FILE_ID = message([
  { name: "sha1", tag: 2, type: "bytes" },
  { name: "fileSize", tag: 3, type: "uint32" },
  { name: "appid", tag: 4, type: "uint32" },
  { name: "timestamp", tag: 5, type: "uint64" },
  { name: "env", tag: 6, type: "string" },
  { name: "ttl", tag: 10, type: "uint32" },
  { name: "sessionId", tag: 11, type: "bytes" },
  { name: "field15", tag: 15, type: "bytes" },
  { name: "region", tag: 16, type: "string" }
]);
var FLASH_UPLOADER = message([
  { name: "uin", tag: 1, type: "string" },
  { name: "nickname", tag: 2, type: "string" },
  { name: "uid", tag: 3, type: "string" },
  { name: "field4", tag: 4, type: FLASH_EMPTY2 }
]);
var FLASH_UPLOAD_FILE_INFO = message([
  { name: "fileName", tag: 2, type: "string" },
  { name: "origName", tag: 3, type: "string" },
  { name: "fileType", tag: 4, type: "uint32" },
  { name: "fileSize", tag: 5, type: "uint64" },
  { name: "uploader", tag: 10, type: FLASH_UPLOADER },
  { name: "field16", tag: 16, type: "uint32" },
  { name: "field20", tag: 20, type: "uint32" },
  { name: "field21", tag: 21, type: "uint32" }
]);
var FLASH_APPLY_FILESET_REQ = message([
  { name: "field1", tag: 1, type: "uint32" },
  { name: "fileInfo", tag: 2, type: FLASH_UPLOAD_FILE_INFO },
  { name: "typeCode", tag: 3, type: "uint32" },
  { name: "field12", tag: 12, type: "uint32" }
]);
var FLASH_APPLY_FILESET_RESP = message([
  { name: "filesetUuid", tag: 1, type: "string" },
  { name: "uploadKey", tag: 2, type: "string" },
  { name: "uploadUrl", tag: 3, type: "string" },
  { name: "expire", tag: 4, type: "uint64" },
  { name: "ttl", tag: 5, type: "uint32" }
]);
var FLASH_COMMIT_FILE_INFO = message([
  { name: "filesetUuid", tag: 1, type: "string" },
  { name: "fileUuid", tag: 2, type: "string" },
  { name: "field3", tag: 3, type: "uint32", force: true },
  { name: "field4", tag: 4, type: FLASH_EMPTY2 },
  { name: "field5", tag: 5, type: "uint32", force: true },
  { name: "field6", tag: 6, type: "uint32", force: true },
  { name: "formatCode", tag: 7, type: "uint32", force: true },
  { name: "fileName", tag: 8, type: "string" },
  { name: "origName", tag: 9, type: "string" },
  { name: "field10", tag: 10, type: "uint32", force: true },
  { name: "fileSize", tag: 11, type: "uint64" },
  { name: "field12", tag: 12, type: "uint32", force: true },
  { name: "field24", tag: 24, type: FLASH_EMPTY2 }
]);
var FLASH_COMMIT_FILE_REQ = message([
  { name: "field1", tag: 1, type: "uint32" },
  { name: "filesetUuid", tag: 2, type: "string" },
  { name: "uploadKey", tag: 3, type: "string" },
  { name: "commitInfo", tag: 4, type: FLASH_COMMIT_FILE_INFO, repeated: true },
  { name: "field5", tag: 5, type: "uint32" },
  { name: "field6", tag: 6, type: "uint32" }
]);
var FLASH_COMMIT_FILE_RESP = message([
  { name: "field1", tag: 1, type: "uint32" },
  { name: "filesetUuid", tag: 2, type: "string" },
  { name: "uploadKey", tag: 3, type: "string" }
]);
var FLASH_COMPLETE_FILESET_REQ = message([
  { name: "filesetUuid", tag: 1, type: "string" },
  { name: "field2", tag: 2, type: "string" }
]);
var FLASH_COMPLETE_FILESET_RESP = message([]);
var FLASH_SET_STATUS_REQ = message([
  { name: "filesetUuid", tag: 1, type: "string" },
  { name: "status", tag: 2, type: "uint32" }
]);
var FLASH_SET_STATUS_RESP = message([]);
var FLASH_FILE_UPLOAD_URL = message([{ name: "uploadUrl", tag: 1, type: "string" }]);
var FLASH_FILE_DOWNLOAD_INFO = message([
  { name: "field1", tag: 1, type: "uint32" },
  { name: "downloadUrl", tag: 2, type: "string" }
]);
var FLASH_FILE_ID_WRAP = message([
  { name: "fileId", tag: 1, type: "string" },
  { name: "download", tag: 2, type: FLASH_FILE_DOWNLOAD_INFO }
]);
var FLASH_FILE_ENTRY = message([
  { name: "filesetUuid", tag: 1, type: "string" },
  { name: "fileName", tag: 2, type: "string" },
  { name: "origName", tag: 3, type: "string" },
  { name: "fileType", tag: 4, type: "uint32" },
  { name: "fileSize", tag: 5, type: "uint64" },
  { name: "uploadUrlWrap", tag: 8, type: FLASH_FILE_UPLOAD_URL },
  { name: "fileIdWrap", tag: 9, type: FLASH_FILE_ID_WRAP }
]);
var FLASH_GET_DETAIL_REQ = message([
  { name: "filesetUuid", tag: 1, type: "string" },
  { name: "field2", tag: 2, type: "uint32" }
]);
var FLASH_GET_DETAIL_RESP = message([
  { name: "entries", tag: 1, type: FLASH_FILE_ENTRY, repeated: true }
]);
var FLASH_SEND_TARGET_UID = message([{ name: "targetUid", tag: 1, type: "string" }]);
var FLASH_SEND_TARGET_GROUP_ID = message([{ name: "groupId", tag: 1, type: "uint32" }]);
var FLASH_SEND_TARGET = message([
  { name: "field1", tag: 1, type: "uint32" },
  { name: "targetUid", tag: 2, type: FLASH_SEND_TARGET_UID },
  { name: "targetGroup", tag: 3, type: FLASH_SEND_TARGET_GROUP_ID }
]);
var FLASH_SEND_REQ = message([
  { name: "target", tag: 1, type: FLASH_SEND_TARGET },
  { name: "filesetUuid", tag: 2, type: "string" }
]);
var FLASH_SEND_RESP_ECHO = message([{ name: "target", tag: 3, type: FLASH_SEND_TARGET }]);
var FLASH_SEND_RESP = message([{ name: "echo", tag: 1, type: FLASH_SEND_RESP_ECHO }]);

// WeQ/packages/protocol/src/oidb/flashtransfer/apply-fileset.ts
var ApplyFileset;
((ApplyFileset2) => {
  ApplyFileset2.command = 37839;
  ApplyFileset2.subCommand = 1;
  ApplyFileset2.reqSchema = FLASH_APPLY_FILESET_REQ;
  ApplyFileset2.respSchema = FLASH_APPLY_FILESET_RESP;
  ApplyFileset2.serialize = (p) => ({
    field1: 1,
    fileInfo: {
      fileName: p.fileName,
      origName: p.origName,
      fileType: 1,
      fileSize: BigInt(p.fileSize),
      uploader: {
        uin: p.uploader.uin,
        nickname: p.uploader.nickname,
        uid: p.uploader.uid,
        field4: {}
      },
      field16: 1,
      field20: 0,
      field21: 0
    },
    typeCode: p.typeCode,
    field12: 1
  });
  ApplyFileset2.deserialize = (body) => {
    const filesetUuid = typeof body.filesetUuid === "string" ? body.filesetUuid : "";
    if (!filesetUuid) throw new Error("apply fileset failed: missing fileset_uuid");
    return {
      filesetUuid,
      uploadKey: typeof body.uploadKey === "string" ? body.uploadKey : "",
      uploadUrl: typeof body.uploadUrl === "string" ? body.uploadUrl : "",
      expire: toInt(body.expire),
      ttl: toInt(body.ttl)
    };
  };
  ApplyFileset2.invoke = (nt, pid, params) => invokeOidb(nt, pid, ApplyFileset2, params);
})(ApplyFileset || (ApplyFileset = {}));

// WeQ/packages/protocol/src/oidb/flashtransfer/file-id.ts
var import_node_crypto4 = require("node:crypto");
var FLASH_FILE_ID_TTL_SECONDS = 1209600;
var FLASH_FILE_ID_TTL_THUMB_SECONDS = 8985599;
var FLASH_APPID_MAIN = 14901;
var FLASH_APPID_PNG_THUMB = 14903;
function buildFileId(sha1, fileSize, appid = FLASH_APPID_MAIN) {
  const isThumb = appid !== FLASH_APPID_MAIN;
  const fileId = {
    sha1: new Uint8Array(sha1),
    fileSize,
    appid,
    timestamp: BigInt(Date.now()) * 1000n,
    // 微秒时间戳
    env: "prod",
    ttl: isThumb ? FLASH_FILE_ID_TTL_THUMB_SECONDS : FLASH_FILE_ID_TTL_SECONDS,
    sessionId: (0, import_node_crypto4.randomBytes)(16),
    field15: (0, import_node_crypto4.randomBytes)(3),
    region: "gz"
  };
  return Buffer.from(encode(FLASH_FILE_ID, fileId)).toString("base64url");
}

// WeQ/packages/protocol/src/oidb/flashtransfer/apply-upload.ts
var ApplyUpload;
((ApplyUpload2) => {
  ApplyUpload2.command = 4777;
  ApplyUpload2.subCommand = 103;
  ApplyUpload2.uinForm = true;
  ApplyUpload2.reqSchema = FLASH_APPLY_UPLOAD_REQ;
  ApplyUpload2.respSchema = FLASH_APPLY_UPLOAD_RESP;
  let seqCounter = 100;
  ApplyUpload2.serialize = (p) => {
    const isThumb = p.thumbType !== void 0;
    const isJpg = p.thumbType === "jpg";
    return {
      head: {
        sub: { seq: seqCounter++, sub: 103 },
        config: {
          field101: 2,
          field102: 4,
          field103: isThumb ? isJpg ? 24 : 23 : 22,
          field200: 5
        },
        field3: { field1: 1 }
      },
      payload: {
        wrapper: {
          fileInfo: {
            fileSize: p.fileSize,
            md5: p.md5,
            sha1: p.sha1,
            fileName: p.fileName,
            field5: { field1: isJpg ? 1 : 0, field2: 0, field3: 0, field4: 0 },
            field6: p.width ?? 0,
            field7: p.height ?? 0,
            field8: 0,
            field9: isJpg ? 0 : 1
          },
          fileId: p.fileId,
          field3: 1,
          field4: Math.floor(Date.now() / 1e3),
          field5: isThumb ? FLASH_FILE_ID_TTL_THUMB_SECONDS : FLASH_FILE_ID_TTL_SECONDS,
          field6: 0
        },
        flag2: { field1: 2 },
        field3: { field1: 0, field2: 0, field3: 0, field4: {} },
        filesetWrap: {
          filesetUuid: p.filesetUuid,
          uploadKey: p.filesetUuid,
          fileUuid: p.fileUuid,
          field4: p.fileIndex,
          field5: isThumb && !isJpg ? 1 : 0,
          field6: isThumb ? isJpg ? 1 : 0 : 0,
          field7: isThumb ? isJpg ? 2 : 26 : p.formatCode,
          field8: {},
          field9: 1,
          field10: 0,
          field11: 0,
          field12: 0,
          field13: 0,
          field14: 0
        }
      }
    };
  };
  ApplyUpload2.deserialize = (_body) => {
  };
  ApplyUpload2.invoke = (nt, pid, params) => invokeOidb(nt, pid, ApplyUpload2, params);
})(ApplyUpload || (ApplyUpload = {}));

// WeQ/packages/protocol/src/oidb/flashtransfer/commit-file.ts
var CommitFile;
((CommitFile2) => {
  CommitFile2.command = 37840;
  CommitFile2.subCommand = 1;
  CommitFile2.reqSchema = FLASH_COMMIT_FILE_REQ;
  CommitFile2.respSchema = FLASH_COMMIT_FILE_RESP;
  CommitFile2.serialize = (p) => ({
    field1: 1,
    filesetUuid: p.filesetUuid,
    uploadKey: p.filesetUuid,
    commitInfo: p.entries.map((entry) => ({
      filesetUuid: p.filesetUuid,
      fileUuid: entry.fileUuid,
      field3: 0,
      field4: {},
      field5: 1,
      field6: entry.fileIndex,
      formatCode: entry.formatCode,
      fileName: entry.fileName,
      origName: entry.origName,
      field10: 0,
      fileSize: BigInt(entry.fileSize),
      field12: 0,
      field24: {}
    })),
    field5: 1,
    field6: 1
  });
  CommitFile2.deserialize = (body) => ({
    filesetUuid: typeof body.filesetUuid === "string" ? body.filesetUuid : ""
  });
  CommitFile2.invoke = (nt, pid, params) => invokeOidb(nt, pid, CommitFile2, params);
})(CommitFile || (CommitFile = {}));

// WeQ/packages/protocol/src/oidb/flashtransfer/complete-fileset.ts
var CompleteFileset;
((CompleteFileset2) => {
  CompleteFileset2.command = 37851;
  CompleteFileset2.subCommand = 1;
  CompleteFileset2.reqSchema = FLASH_COMPLETE_FILESET_REQ;
  CompleteFileset2.respSchema = FLASH_COMPLETE_FILESET_RESP;
  CompleteFileset2.serialize = (p) => ({
    filesetUuid: p.filesetUuid,
    field2: ""
  });
  CompleteFileset2.deserialize = (_body) => {
  };
  CompleteFileset2.invoke = (nt, pid, params) => invokeOidb(nt, pid, CompleteFileset2, params);
})(CompleteFileset || (CompleteFileset = {}));

// WeQ/packages/protocol/src/oidb/flashtransfer/file-type.ts
var FORMAT_CODE_UNKNOWN = 11;
var FORMAT_CODE_BY_EXTENSION = {
  // 音频
  ".mp3": 1,
  ".wav": 1,
  ".flac": 1,
  ".m4a": 1,
  ".aac": 1,
  ".ogg": 1,
  // 视频
  ".mp4": 2,
  ".mov": 2,
  ".avi": 2,
  ".mkv": 2,
  ".webm": 2,
  ".flv": 2,
  // Word / 文档
  ".doc": 3,
  ".docx": 3,
  // 压缩包
  ".rar": 4,
  ".zip": 4,
  ".7z": 4,
  ".gz": 4,
  ".tar": 4,
  ".bz2": 4,
  // Android
  ".apk": 5,
  // Excel
  ".xls": 6,
  ".xlsx": 6,
  // PowerPoint
  ".ppt": 7,
  ".pptx": 7,
  // PDF / 纯文本
  ".pdf": 9,
  ".txt": 10,
  // 图片：本次抓包确认 PNG=26；其他常见图片按同一图片类型处理。
  ".png": 26,
  ".jpg": 26,
  ".jpeg": 26,
  ".gif": 26,
  ".bmp": 26,
  ".webp": 26,
  // Photoshop
  ".psd": 12,
  // 字体 / Apple / 设计文件
  ".ttf": 16,
  ".otf": 16,
  ".ipa": 17,
  ".key": 18,
  ".numbers": 20,
  ".pages": 21,
  ".sketch": 22,
  // 安装包 / 磁盘镜像
  ".dmg": 23,
  ".pkg": 24,
  // 本次抓包中以下扩展名均落到 unknown=11：
  ".ai": FORMAT_CODE_UNKNOWN,
  ".bak": FORMAT_CODE_UNKNOWN,
  ".exe": FORMAT_CODE_UNKNOWN,
  ".md": FORMAT_CODE_UNKNOWN,
  ".py": FORMAT_CODE_UNKNOWN,
  ".unknown": FORMAT_CODE_UNKNOWN,
  ".url": FORMAT_CODE_UNKNOWN,
  ".xmind": FORMAT_CODE_UNKNOWN
};
function fileTypeCode(fileName) {
  const normalized = fileName.toLowerCase();
  const ext = normalized.match(/\.([^.]+)$/)?.[1] ?? "";
  const extension = ext ? `.${ext}` : "";
  const formatCode = FORMAT_CODE_BY_EXTENSION[extension] ?? FORMAT_CODE_UNKNOWN;
  if (formatCode === 4) {
    return {
      typeCode: ext === "zip" ? 6 : 2,
      formatCode
    };
  }
  return {
    typeCode: 7,
    formatCode
  };
}

// WeQ/packages/protocol/src/oidb/flashtransfer/prepare-upload.ts
var PrepareUpload;
((PrepareUpload2) => {
  PrepareUpload2.command = 4777;
  PrepareUpload2.subCommand = 100;
  PrepareUpload2.uinForm = true;
  PrepareUpload2.reqSchema = FLASH_PREPARE_UPLOAD_REQ;
  PrepareUpload2.respSchema = FLASH_PREPARE_UPLOAD_RESP;
  let seqCounter = 200;
  PrepareUpload2.serialize = (p) => {
    const isThumb = p.thumbType !== void 0;
    const isJpg = p.thumbType === "jpg";
    return {
      head: {
        sub: { seq: seqCounter++, sub: 100 },
        config: {
          field101: 2,
          field102: 4,
          field103: isThumb ? isJpg ? 24 : 23 : 22,
          field200: 5
        },
        field3: { field1: 1 }
      },
      payload: {
        wrapper: {
          fileInfo: {
            fileSize: p.fileSize,
            md5: "",
            sha1: p.sha1,
            fileName: p.fileName,
            field5: { field1: isJpg ? 1 : 0, field2: 0, field3: 0, field4: 0 },
            field6: p.width ?? 0,
            field7: p.height ?? 0,
            field8: 0,
            field9: isJpg ? 0 : 1
          },
          field2: 0
        },
        field2: 1,
        field3: 0,
        field4: 0,
        field5: 0,
        field6: {
          field1: { field1: 0, field2: {} },
          field2: { field3: {} },
          field3: { field11: {}, field12: {} },
          field10: 0
        },
        field7: 0,
        field8: 0,
        filesetWrap: {
          filesetUuid: p.filesetUuid,
          uploadKey: p.filesetUuid,
          fileUuid: p.fileUuid,
          field4: p.fileIndex,
          field5: 0,
          field6: isThumb ? 1 : 0,
          field7: isThumb ? isJpg ? 2 : 26 : p.formatCode,
          field8: {},
          field9: 1,
          field10: 0,
          field11: 0,
          field12: 0,
          field13: 0,
          field14: 0
        }
      }
    };
  };
  PrepareUpload2.deserialize = (body) => {
    const rkey = body.rkeyWrap?.rkey;
    return typeof rkey === "string" && rkey ? rkey : null;
  };
  PrepareUpload2.invoke = (nt, pid, params) => invokeOidb(nt, pid, PrepareUpload2, params);
})(PrepareUpload || (PrepareUpload = {}));

// WeQ/packages/protocol/src/oidb/flashtransfer/set-status.ts
var SetFilesetStatus;
((SetFilesetStatus2) => {
  SetFilesetStatus2.command = 37841;
  SetFilesetStatus2.subCommand = 1;
  SetFilesetStatus2.reqSchema = FLASH_SET_STATUS_REQ;
  SetFilesetStatus2.respSchema = FLASH_SET_STATUS_RESP;
  SetFilesetStatus2.serialize = (p) => ({
    filesetUuid: p.filesetUuid,
    status: p.status ?? 6
  });
  SetFilesetStatus2.deserialize = (_body) => {
  };
  SetFilesetStatus2.invoke = (nt, pid, params) => invokeOidb(nt, pid, SetFilesetStatus2, params);
})(SetFilesetStatus || (SetFilesetStatus = {}));

// WeQ/packages/protocol/src/oidb/flashtransfer/thumbnail.ts
var import_node_crypto5 = require("node:crypto");
var import_node_fs2 = require("node:fs");
async function prepareThumbnail(nt, pid, filesetUuid, thumbPath, fileIndex) {
  const thumbBytes = await import_node_fs2.promises.readFile(thumbPath);
  if (thumbBytes.length < 24 || !thumbBytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    throw new Error(`thumbnail is not a valid PNG: ${thumbPath}`);
  }
  const firstChunkLength = thumbBytes.readUInt32BE(8);
  if (thumbBytes.toString("ascii", 12, 16) !== "IHDR" || firstChunkLength < 8 || thumbBytes.length < 24) {
    throw new Error(`thumbnail PNG has no valid IHDR: ${thumbPath}`);
  }
  const width = thumbBytes.readUInt32BE(16);
  const height = thumbBytes.readUInt32BE(20);
  if (width === 0 || height === 0)
    throw new Error(`thumbnail PNG has invalid dimensions: ${thumbPath}`);
  const appid = FLASH_APPID_PNG_THUMB;
  const fileUuid = (0, import_node_crypto5.randomUUID)();
  const fileName = `${(0, import_node_crypto5.randomUUID)().slice(0, 8)}_one.png`;
  const hashes = computeHashes(new Uint8Array(thumbBytes));
  const fileSize = thumbBytes.length;
  const rkey = await PrepareUpload.invoke(nt, pid, {
    filesetUuid,
    fileUuid,
    fileName,
    fileSize,
    sha1: hashes.sha1Hex,
    fileIndex,
    formatCode: 26,
    thumbType: "png",
    width,
    height
  });
  return {
    nt,
    pid,
    filesetUuid,
    fileIndex,
    rkey,
    fileId: buildFileId(hashes.sha1, fileSize, appid),
    fileUuid,
    fileName,
    fileSize,
    md5Hex: hashes.md5Hex,
    sha1Hex: hashes.sha1Hex,
    sha1: new Uint8Array(hashes.sha1),
    sha1StateV: computeSha1StateV(new Uint8Array(thumbBytes), 1, fileSize),
    chunk: new Uint8Array(thumbBytes),
    width,
    height,
    appid
  };
}
async function applyThumbnail(thumb) {
  await ApplyUpload.invoke(thumb.nt, thumb.pid, {
    filesetUuid: thumb.filesetUuid,
    fileUuid: thumb.fileUuid,
    fileId: thumb.fileId,
    fileName: thumb.fileName,
    fileSize: thumb.fileSize,
    md5: thumb.md5Hex,
    sha1: thumb.sha1Hex,
    fileIndex: thumb.fileIndex,
    formatCode: 26,
    thumbType: "png",
    width: thumb.width,
    height: thumb.height
  });
}
async function sliceuploadThumbnail(thumb) {
  if (thumb.rkey === null) {
    return;
  }
  const bodyBytes = buildSliceBody(
    {
      rkey: thumb.rkey,
      start: 0,
      end: thumb.fileSize - 1,
      sha1: thumb.sha1,
      sha1StateV: thumb.sha1StateV,
      chunk: thumb.chunk
    },
    { appid: thumb.appid }
  );
  await postSliceupload(bodyBytes, "thumbnail sliceupload");
}

// WeQ/packages/protocol/src/oidb/flashtransfer/upload.ts
var MAX_FLASH_BYTES = 4 * 1024 * 1024 * 1024;
function displayName(override, fallback) {
  const cleaned = (override ?? "").replace(/[/\\]/g, "_").trim();
  return cleaned || fallback;
}
async function prepareAndApply(nt, pid, filesetUuid, item) {
  const hashes = await hashFlashFileStreaming(item.path);
  const rkey = await PrepareUpload.invoke(nt, pid, {
    filesetUuid,
    fileUuid: item.fileUuid,
    fileName: item.fileName,
    fileSize: item.fileSize,
    sha1: hashes.sha1Hex,
    fileIndex: item.fileIndex,
    formatCode: item.formatCode
  });
  const fileId = buildFileId(hashes.sha1, item.fileSize);
  await ApplyUpload.invoke(nt, pid, {
    filesetUuid,
    fileUuid: item.fileUuid,
    fileId,
    fileName: item.fileName,
    fileSize: item.fileSize,
    md5: hashes.md5Hex,
    sha1: hashes.sha1Hex,
    fileIndex: item.fileIndex,
    formatCode: item.formatCode
  });
  if (rkey === null) return null;
  return { rkey, sha1StateV: hashes.sha1StateV, sliceCount: hashes.sliceCount };
}
async function createFlashFileset(nt, pid, files, opts) {
  if (files.length === 0) throw new Error("upload flash files: files is empty");
  const items = [];
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const stat = await import_node_fs3.promises.stat(file.path);
    if (!stat.isFile()) throw new Error(`upload flash files: not a file: ${file.path}`);
    if (stat.size === 0) throw new Error(`upload flash files: file is empty: ${file.path}`);
    if (stat.size > MAX_FLASH_BYTES)
      throw new Error(`upload flash files: file too large: ${file.path}`);
    const fileName = displayName(file.name, (0, import_node_path.basename)(file.path));
    const { formatCode } = fileTypeCode(fileName);
    items.push({
      path: file.path,
      fileName,
      fileSize: stat.size,
      fileUuid: (0, import_node_crypto6.randomUUID)(),
      fileIndex: i + 1,
      formatCode
    });
  }
  const first = items[0];
  const isMulti = items.length > 1;
  const filesetName = opts.name?.trim() || (isMulti ? `${first.fileName}\u7B49${items.length}\u4E2A\u6587\u4EF6` : first.fileName);
  const totalSize = items.reduce((sum, item) => sum + item.fileSize, 0);
  const { typeCode } = fileTypeCode(first.fileName);
  const apply = await ApplyFileset.invoke(nt, pid, {
    fileName: filesetName,
    origName: filesetName,
    fileSize: totalSize,
    typeCode,
    uploader: opts.uploader
  });
  return {
    filesetUuid: apply.filesetUuid,
    shareUrl: apply.uploadUrl,
    thumbPath: opts.thumbPath,
    items
  };
}
async function stageFlashFileset(nt, pid, pending) {
  const { filesetUuid, items } = pending;
  const entries = items.map((item) => ({
    fileUuid: item.fileUuid,
    fileName: item.fileName,
    origName: item.fileName,
    fileSize: item.fileSize,
    formatCode: item.formatCode,
    fileIndex: item.fileIndex
  }));
  await CommitFile.invoke(nt, pid, { filesetUuid, entries });
  await CompleteFileset.invoke(nt, pid, { filesetUuid });
  if (pending.thumbPath !== void 0) {
    const thumb = await prepareThumbnail(nt, pid, filesetUuid, pending.thumbPath, items.length + 1);
    await applyThumbnail(thumb);
    await sliceuploadThumbnail(thumb);
  }
}
async function uploadFlashMainFiles(nt, pid, pending) {
  const { filesetUuid, items } = pending;
  const results = await Promise.all(
    items.map(async (item) => ({
      item,
      upload: await prepareAndApply(nt, pid, filesetUuid, item)
    }))
  );
  const prepared = results.filter(
    (r) => r.upload !== null
  );
  await Promise.all(
    prepared.map(
      ({ item, upload }) => sliceuploadFile(
        item.path,
        item.fileSize,
        upload.rkey,
        upload.sha1StateV,
        upload.sliceCount,
        item.fileName
      )
    )
  );
  await SetFilesetStatus.invoke(nt, pid, { filesetUuid });
}

// WeQ/packages/protocol/src/oidb/flashtransfer/send-flash.ts
var SendFlashMsg;
((SendFlashMsg2) => {
  SendFlashMsg2.command = 37847;
  SendFlashMsg2.subCommand = 1;
  SendFlashMsg2.reqSchema = FLASH_SEND_REQ;
  SendFlashMsg2.respSchema = FLASH_SEND_RESP;
  SendFlashMsg2.serialize = (p) => {
    if (p.groupId !== void 0) {
      return {
        target: { field1: 2, targetGroup: { groupId: p.groupId } },
        filesetUuid: p.filesetUuid
      };
    }
    if (!p.targetUid) throw new Error("send_flash_msg: target_uid or group_id is required");
    return {
      target: { field1: 1, targetUid: { targetUid: p.targetUid } },
      filesetUuid: p.filesetUuid
    };
  };
  SendFlashMsg2.deserialize = (_body) => {
  };
  SendFlashMsg2.invoke = (nt, pid, params) => invokeOidb(nt, pid, SendFlashMsg2, params);
})(SendFlashMsg || (SendFlashMsg = {}));
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  SendFlashMsg,
  createFlashFileset,
  stageFlashFileset,
  uploadFlashMainFiles
});
