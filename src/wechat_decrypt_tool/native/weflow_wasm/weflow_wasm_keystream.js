// Generate WeChat/WeFlow WxIsaac64 keystream via the vendored WASM module.
//
// Usage:
//   node weflow_wasm_keystream.js <key> <size>
//   node weflow_wasm_keystream.js --stdio
//
// CLI mode prints base64 to stdout. Stdio mode accepts one JSON request per
// line and keeps the initialized WASM module alive across requests.

const fs = require('fs')
const path = require('path')
const vm = require('vm')

function usageAndExit() {
  process.stderr.write('Usage: node weflow_wasm_keystream.js <key> <size>\\n')
  process.exit(2)
}

const stdioMode = process.argv[2] === '--stdio'
const cliKey = String(process.argv[2] || '').trim()
const cliSize = Number(process.argv[3] || 0)

if (!stdioMode && (!cliKey || !Number.isFinite(cliSize) || cliSize <= 0)) usageAndExit()

const basePath = __dirname
const wasmPath = path.join(basePath, 'wasm_video_decode.wasm')
const jsPath = path.join(basePath, 'wasm_video_decode.js')

if (!fs.existsSync(wasmPath) || !fs.existsSync(jsPath)) {
  process.stderr.write(`Vendored WASM assets not found: ${basePath}\\n`)
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
  console: { log: () => {}, error: () => {} },
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
  capturedKeystream = new Uint8Array(buf)
}

try {
  const context = vm.createContext(mockGlobal)
  new vm.Script(jsContent, { filename: jsPath }).runInContext(context)
} catch (e) {
  rejectInit(e)
}

async function generateKeystream(key, size) {
  await initPromise

  if (!mockGlobal.Module.WxIsaac64 && mockGlobal.Module.asm && mockGlobal.Module.asm.WxIsaac64) {
    mockGlobal.Module.WxIsaac64 = mockGlobal.Module.asm.WxIsaac64
  }
  if (!mockGlobal.Module.WxIsaac64) throw new Error('WxIsaac64 not found in WASM module')

  const alignedSize = Math.ceil(size / 8) * 8
  capturedKeystream = null
  const isaac = new mockGlobal.Module.WxIsaac64(key)
  isaac.generate(alignedSize)
  if (isaac.delete) isaac.delete()
  if (!capturedKeystream) throw new Error('Failed to capture keystream')

  const out = Buffer.from(capturedKeystream)
  out.reverse()
  return out.subarray(0, size)
}

async function runStdioMode() {
  const readline = require('readline')
  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })
  for await (const line of input) {
    let request = null
    try {
      request = JSON.parse(line.replace(/^\uFEFF/, ''))
      const key = String(request.key || '').trim()
      const size = Number(request.size || 0)
      if (!key || !Number.isFinite(size) || size <= 0) throw new Error('Invalid key or size')
      const data = await generateKeystream(key, size)
      process.stdout.write(JSON.stringify({ id: request.id, data: data.toString('base64') }) + '\n')
    } catch (e) {
      process.stdout.write(JSON.stringify({
        id: request && request.id,
        error: String(e && e.message ? e.message : e)
      }) + '\n')
    }
  }
}

;(async () => {
  try {
    if (stdioMode) {
      await runStdioMode()
      return
    }
    const out = await generateKeystream(cliKey, cliSize)
    process.stdout.write(out.toString('base64'))
  } catch (e) {
    process.stderr.write(String(e && e.stack ? e.stack : e) + '\\n')
    process.exit(1)
  }
})()
