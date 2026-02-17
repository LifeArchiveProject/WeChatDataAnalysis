// Generate WeChat/WeFlow WxIsaac64 keystream via WeFlow's WASM module.
//
// Usage:
//   node tools/weflow_wasm_keystream.js <key> <size>
//
// Prints a base64-encoded keystream to stdout (no extra logs).

const fs = require('fs')
const path = require('path')
const vm = require('vm')

function usageAndExit() {
  process.stderr.write('Usage: node tools/weflow_wasm_keystream.js <key> <size>\\n')
  process.exit(2)
}

const key = String(process.argv[2] || '').trim()
const size = Number(process.argv[3] || 0)

if (!key || !Number.isFinite(size) || size <= 0) usageAndExit()

const basePath = path.join(__dirname, '..', 'WeFlow', 'electron', 'assets', 'wasm')
const wasmPath = path.join(basePath, 'wasm_video_decode.wasm')
const jsPath = path.join(basePath, 'wasm_video_decode.js')

if (!fs.existsSync(wasmPath) || !fs.existsSync(jsPath)) {
  process.stderr.write(`WeFlow WASM assets not found: ${basePath}\\n`)
  process.exit(1)
}

const wasmBinary = fs.readFileSync(wasmPath)
const jsContent = fs.readFileSync(jsPath, 'utf8')

let capturedKeystream = null
let resolveInit
let rejectInit
const initPromise = new Promise((res, rej) => {
  resolveInit = res
  rejectInit = rej
})

const mockGlobal = {
  console: { log: () => {}, error: () => {} }, // keep stdout clean
  Buffer,
  Uint8Array,
  Int8Array,
  Uint16Array,
  Int16Array,
  Uint32Array,
  Int32Array,
  Float32Array,
  Float64Array,
  BigInt64Array,
  BigUint64Array,
  Array,
  Object,
  Function,
  String,
  Number,
  Boolean,
  Error,
  Promise,
  require,
  process,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
}

mockGlobal.Module = {
  onRuntimeInitialized: () => resolveInit(),
  wasmBinary,
  print: () => {},
  printErr: () => {},
}

mockGlobal.self = mockGlobal
mockGlobal.self.location = { href: jsPath }
mockGlobal.WorkerGlobalScope = function () {}
mockGlobal.VTS_WASM_URL = `file://${wasmPath}`

mockGlobal.wasm_isaac_generate = (ptr, n) => {
  const buf = new Uint8Array(mockGlobal.Module.HEAPU8.buffer, ptr, n)
  capturedKeystream = new Uint8Array(buf) // copy view
}

try {
  const context = vm.createContext(mockGlobal)
  new vm.Script(jsContent, { filename: jsPath }).runInContext(context)
} catch (e) {
  rejectInit(e)
}

;(async () => {
  try {
    await initPromise

    if (!mockGlobal.Module.WxIsaac64 && mockGlobal.Module.asm && mockGlobal.Module.asm.WxIsaac64) {
      mockGlobal.Module.WxIsaac64 = mockGlobal.Module.asm.WxIsaac64
    }
    if (!mockGlobal.Module.WxIsaac64) {
      throw new Error('WxIsaac64 not found in WASM module')
    }

    capturedKeystream = null
    const isaac = new mockGlobal.Module.WxIsaac64(key)
    isaac.generate(size)
    if (isaac.delete) isaac.delete()

    if (!capturedKeystream) throw new Error('Failed to capture keystream')

    const out = Buffer.from(capturedKeystream)
    // Match WeFlow worker logic: reverse the captured Uint8Array.
    out.reverse()
    process.stdout.write(out.toString('base64'))
  } catch (e) {
    process.stderr.write(String(e && e.stack ? e.stack : e) + '\\n')
    process.exit(1)
  }
})()

