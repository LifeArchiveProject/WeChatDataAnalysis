import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'

const source = await readFile(new URL('../stores/chatAccounts.js', import.meta.url), 'utf8')

const createRef = (value) => ({ value })

const createStoreHarness = () => {
  let requestCount = 0
  const context = vm.createContext({
    computed: (getter) => ({
      get value() {
        return getter()
      },
    }),
    defineStore: (_name, setup) => setup,
    localStorage: {
      getItem: () => null,
      removeItem: () => {},
      setItem: () => {},
    },
    process: { client: true },
    ref: createRef,
    useApiBase: () => '',
    watch: () => {},
    $fetch: async () => {
      requestCount += 1
      if (requestCount === 1) throw new Error('临时不可用')
      return { accounts: ['wxid_demo'], default_account: 'wxid_demo' }
    },
  })

  const executable = source
    .replace(/^import .*$/m, '')
    .replace('export const useChatAccountsStore', 'const useChatAccountsStore')
    .concat('\nthis.store = useChatAccountsStore()')
  vm.runInContext(executable, context)

  return {
    get requestCount() {
      return requestCount
    },
    store: context.store,
  }
}

test('账号列表首次加载失败后可以由 ensureLoaded 重试', async () => {
  const harness = createStoreHarness()

  await harness.store.ensureLoaded()
  assert.equal(harness.requestCount, 1)
  assert.equal(harness.store.loaded.value, false)
  assert.deepEqual(Array.from(harness.store.accounts.value), [])
  assert.equal(harness.store.error.value, '临时不可用')

  await harness.store.ensureLoaded()
  assert.equal(harness.requestCount, 2)
  assert.equal(harness.store.loaded.value, true)
  assert.deepEqual(Array.from(harness.store.accounts.value), ['wxid_demo'])
  assert.equal(harness.store.selectedAccount.value, 'wxid_demo')
  assert.equal(harness.store.error.value, '')
})
