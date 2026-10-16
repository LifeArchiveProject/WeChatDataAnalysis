import assert from 'node:assert/strict'
import test from 'node:test'
import vm from 'node:vm'

import { createFirstUseBootstrapScript } from '../lib/first-use-bootstrap-script.js'

const STORAGE_KEY = 'ui.first_use_agreement'
const VERSION = '2026-08-12.3'
const bootstrapScript = createFirstUseBootstrapScript({
  storageKey: STORAGE_KEY,
  version: VERSION,
  countdownMilliseconds: 20_000,
})

const createHarness = ({ pathname = '/', search = '', hash = '', stored = null } = {}) => {
  let now = 0
  let intervalCallback = null
  let clickCallback = null
  const replacements = []
  const rootAttributes = new Map()
  const pageAttributes = new Map()
  const storage = new Map()
  if (stored !== null) storage.set(STORAGE_KEY, stored)

  const label = { textContent: '请阅读（20 秒）' }
  const statusCopy = { textContent: '请先读完关键内容，20 秒后可确认。' }
  const statusDot = {
    classes: new Set(),
    classList: {
      add(value) {
        statusDot.classes.add(value)
      },
    },
  }
  const button = {
    disabled: true,
    querySelector: (selector) => selector === 'span' ? label : null,
    addEventListener(event, callback) {
      if (event === 'click') clickCallback = callback
    },
  }
  const page = {
    getAttribute: (name) => pageAttributes.get(name) || null,
    setAttribute: (name, value) => pageAttributes.set(name, String(value)),
  }
  const guard = { hidden: false }
  const documentElement = {
    setAttribute: (name, value) => rootAttributes.set(name, String(value)),
    removeAttribute: (name) => rootAttributes.delete(name),
  }
  const document = {
    readyState: 'complete',
    documentElement,
    addEventListener() {},
    querySelector(selector) {
      return {
        '.first-use-page': page,
        '.first-use-route-guard': guard,
        '[data-testid="first-use-confirm"]': button,
        '.first-use-footer-status p': statusCopy,
        '.first-use-status-dot': statusDot,
      }[selector] || null
    },
  }

  class FakeDate extends Date {
    constructor(...args) {
      super(...(args.length ? args : [now]))
    }

    static now() {
      return now
    }
  }

  const location = {
    pathname,
    search,
    hash,
    href: `http://127.0.0.1:10393${pathname}${search}${hash}`,
    replace(value) {
      replacements.push(String(value))
    },
  }
  const window = {
    location,
    localStorage: {
      getItem: (key) => storage.has(key) ? storage.get(key) : null,
      setItem: (key, value) => storage.set(key, String(value)),
    },
    setTimeout(callback) {
      callback()
      return 1
    },
    setInterval(callback) {
      intervalCallback = callback
      return 2
    },
    clearInterval() {
      intervalCallback = null
    },
  }

  vm.runInNewContext(bootstrapScript, {
    Date: FakeDate,
    JSON,
    Math,
    String,
    URL,
    document,
    encodeURIComponent,
    window,
  })

  return {
    advance(milliseconds) {
      now += milliseconds
      intervalCallback?.()
    },
    click() {
      assert.equal(typeof clickCallback, 'function')
      clickCallback({ preventDefault() {} })
    },
    button,
    guard,
    label,
    pageAttributes,
    replacements,
    rootAttributes,
    statusCopy,
    statusDot,
    storage,
  }
}

test('unaccepted root redirects before the Nuxt client mounts', () => {
  const harness = createHarness()

  assert.deepEqual(harness.replacements, ['/agreement?redirect=%2F'])
  assert.equal(harness.rootAttributes.has('data-first-use-accepted'), false)
})

test('accepted state skips the notice and hides the hydration guard', () => {
  const harness = createHarness({
    stored: JSON.stringify({ version: VERSION, acceptedAt: '2026-08-12T00:00:00.000Z' }),
  })

  assert.deepEqual(harness.replacements, [])
  assert.equal(harness.rootAttributes.get('data-first-use-accepted'), 'true')
})

test('malformed renderer storage safely falls back to the notice', () => {
  const harness = createHarness({ stored: '{bad json' })

  assert.deepEqual(harness.replacements, ['/agreement?redirect=%2F'])
})

test('agreement remains readable and confirmable when Nuxt never mounts', () => {
  const harness = createHarness({ pathname: '/agreement', search: '?redirect=%2Fchat' })

  assert.equal(harness.rootAttributes.get('data-first-use-route'), 'agreement')
  assert.equal(harness.guard.hidden, true)
  assert.equal(harness.button.disabled, true)

  harness.advance(20_000)
  assert.equal(harness.button.disabled, false)
  assert.equal(harness.label.textContent, '我已阅读全部内容并同意')
  assert.equal(harness.statusCopy.textContent, '重点和边界都看完了，确认后开工。')
  assert.equal(harness.statusDot.classes.has('ready'), true)

  harness.click()
  const acceptance = JSON.parse(harness.storage.get(STORAGE_KEY))
  assert.equal(acceptance.version, VERSION)
  assert.ok(acceptance.acceptedAt)
  assert.deepEqual(harness.replacements, ['/chat'])
})
