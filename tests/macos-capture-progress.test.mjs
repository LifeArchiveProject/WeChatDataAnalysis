import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as captureProgress from '../frontend/lib/macos-capture-progress.js'

const { followMacosCapture } = captureProgress

test('readiness from a previous transaction never enables login', async () => {
  let finish
  let polls = 0
  const progress = []
  const result = await followMacosCapture({
    start: () => new Promise(resolve => { finish = resolve }),
    transactionId: 'current',
    isActive: () => true,
    wait: () => new Promise(resolve => setImmediate(resolve)),
    getStatus: async () => {
      polls++
      if (polls === 1) return { transaction_id: 'previous', monitor_ready: true }
      if (polls === 2) return { transaction_id: 'current', monitor_ready: false }
      if (polls === 3) return { transaction_id: 'current', monitor_ready: true }
      finish({ status: 0 })
      return { transaction_id: 'previous', monitor_ready: true }
    },
    onProgress: ready => progress.push(ready)
  })
  assert.deepEqual(progress, [false, true])
  assert.equal(result.status, 0)
})

test('capture rejection stops status polling and is propagated', async () => {
  let polls = 0
  await assert.rejects(followMacosCapture({
    start: async () => { throw new Error('fixture cancelled') },
    transactionId: 'current',
    isActive: () => true,
    getStatus: async () => { polls++; return {} },
    onProgress: () => assert.fail('must not report ready'),
    wait: () => new Promise(resolve => setImmediate(resolve))
  }), /fixture cancelled/)
  assert.equal(polls, 0)
})

test('completion aborts an in-flight status request', async () => {
  let finish
  let aborted = false
  const result = await followMacosCapture({
    start: () => new Promise(resolve => { finish = resolve }),
    transactionId: 'current',
    isActive: () => true,
    wait: () => new Promise(resolve => setImmediate(resolve)),
    getStatus: ({ signal }) => new Promise((_, reject) => {
      signal.addEventListener('abort', () => { aborted = true; reject(new Error('aborted')) })
      finish('done')
    }),
    onProgress: () => assert.fail('capture is finished')
  })
  assert.equal(result, 'done')
  assert.equal(aborted, true)
})

test('progress forwards only whitelisted phases with the compatible readiness boolean', async () => {
  let finish
  let index = 0
  const phases = ['waiting_authorization', 'monitoring', 'captured', 'validating', 'restoring', null, undefined, 'complete', {}, true]
  const progress = []
  await followMacosCapture({
    start: () => new Promise(resolve => { finish = resolve }),
    transactionId: 'current',
    isActive: () => true,
    wait: () => new Promise(resolve => setImmediate(resolve)),
    getStatus: async () => {
      if (index === phases.length) finish('done')
      return { transaction_id: 'current', monitor_ready: index === 1, capture_phase: phases[index++] }
    },
    onProgress: (ready, phase) => progress.push([ready, phase])
  })
  assert.deepEqual(progress, phases.map((phase, index) => [index === 1, index < 5 ? phase : null]))
})

test('post-capture progress remains bound to the active transaction', async () => {
  let finish
  let polls = 0
  const progress = []
  await followMacosCapture({
    start: () => new Promise(resolve => { finish = resolve }),
    transactionId: 'current',
    isActive: () => true,
    wait: () => new Promise(resolve => setImmediate(resolve)),
    getStatus: async () => {
      polls++
      if (polls === 1) return { transaction_id: 'previous', monitor_ready: false, capture_phase: 'restoring' }
      if (polls === 2) return { transaction_id: 'current', monitor_ready: false, capture_phase: 'captured' }
      finish('done')
      return { transaction_id: 'current', monitor_ready: false, capture_phase: 'validating' }
    },
    onProgress: (ready, phase) => progress.push([ready, phase])
  })
  assert.deepEqual(progress, [[false, 'captured']])
})

test('an inactive request cannot publish an in-flight progress response', async () => {
  let finish
  let active = true
  const progress = []
  const result = await followMacosCapture({
    start: () => new Promise(resolve => { finish = resolve }),
    transactionId: 'current',
    isActive: () => active,
    wait: () => new Promise(resolve => setImmediate(resolve)),
    getStatus: async () => {
      active = false
      setImmediate(() => finish('cancelled'))
      return { transaction_id: 'current', monitor_ready: false, capture_phase: 'restoring' }
    },
    onProgress: (...values) => progress.push(values)
  })
  assert.equal(result, 'cancelled')
  assert.deepEqual(progress, [])
})

test('restoring is progress only and never replaces the completed request result', async () => {
  let finish
  let polls = 0
  const expected = { status: 1, errmsg: 'fixture restore conflict' }
  const progress = []
  const result = await followMacosCapture({
    start: () => new Promise(resolve => { finish = resolve }),
    transactionId: 'current',
    isActive: () => true,
    wait: () => new Promise(resolve => setImmediate(resolve)),
    getStatus: async () => {
      if (++polls === 2) finish(expected)
      return { transaction_id: 'current', monitor_ready: false, capture_phase: 'restoring' }
    },
    onProgress: (ready, phase) => progress.push([ready, phase])
  })
  assert.deepEqual(progress, [[false, 'restoring']])
  assert.equal(result, expected)
})

test('post-capture messages never invite another login or report completion', () => {
  for (const phase of ['captured', 'validating', 'restoring']) {
    for (const ready of [false, true]) {
      const message = captureProgress.macosCaptureProgressMessage(ready, phase)
      assert.doesNotMatch(message, /可以重新登录|完成管理员授权|获取成功|已恢复/)
      assert.match(message, /请勿再次登录/)
      assert.match(message, /临时微信.*关闭|关闭临时微信/)
      assert.match(message, /恢复腾讯原签名微信/)
    }
  }
  assert.match(captureProgress.macosCaptureProgressMessage(false, 'captured'), /已捕获密钥并通过消息库与会话库校验，正在完成后续复核/)
  assert.match(captureProgress.macosCaptureProgressMessage(false, 'validating'), /消息库与会话库校验/)
  assert.match(captureProgress.macosCaptureProgressMessage(false, 'restoring'), /恢复尚未完成/)
})

test('login guidance still requires monitor readiness and respects authorization phase', () => {
  assert.match(captureProgress.macosCaptureProgressMessage(true, 'monitoring'), /可以重新登录/)
  assert.match(captureProgress.macosCaptureProgressMessage(true, null), /可以重新登录/)
  assert.doesNotMatch(captureProgress.macosCaptureProgressMessage(false, 'monitoring'), /可以重新登录/)
  assert.doesNotMatch(captureProgress.macosCaptureProgressMessage(true, 'waiting_authorization'), /可以重新登录/)
  assert.match(captureProgress.macosCaptureProgressMessage(false, null), /完成管理员授权/)
})

test('decrypt page uses phase-aware messages and announces the temporary window closing', () => {
  const page = readFileSync(new URL('../frontend/pages/decrypt.vue', import.meta.url), 'utf8')
  assert.ok(/onProgress: \(ready, phase\) =>/.test(page), 'page must receive the transaction phase')
  assert.ok(/warning\.value = macosCaptureProgressMessage\(ready, phase\)/.test(page), 'page must use phase-aware messages')
  assert.ok(/捕获后临时微信窗口会关闭/.test(page), 'guide must announce temporary window closing')
})
