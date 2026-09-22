import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('../pages/wrapped/index.vue', import.meta.url), 'utf8')

test('年度总结复用账号 store 的单次加载结果', () => {
  assert.match(source, /const \{ selectedAccount, accounts, loading: accountsLoading \} = storeToRefs\(chatAccountsStore\)/)
  assert.match(source, /await chatAccountsStore\.ensureLoaded\(\)/)
  assert.doesNotMatch(source, /api\.listChatAccounts\(/)
  assert.doesNotMatch(source, /const loadAccounts\s*=/)
})
