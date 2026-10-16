import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../pages/decrypt.vue', import.meta.url), 'utf8')
function feedback(result) {
  const start = source.indexOf('const showDbKeyPersistenceWarning =')
  const end = source.indexOf('\nconst runMacosLldbFallback', start)
  const context = { result, warning: { value: '' }, DB_KEY_PERSISTENCE_WARNING: 'KEY_SAVE_WARNING', logDecryptDebug: () => {} }
  vm.runInNewContext(`${source.slice(start, end)}\nshowDbKeyPersistenceWarning(result)`, context)
  return context.warning.value
}

test('partial success with an authenticated key does not ask for key recapture', () => {
  const message = feedback({ success_count:27, failure_count:1, total_databases:28, db_key_persisted:true })
  assert.match(message, /解密部分成功：27\/28/)
  assert.doesNotMatch(message, /KEY_SAVE_WARNING/)
})

test('recovered indexes are disclosed and key saving failures stay visible', () => {
  const message = feedback({ db_key_persisted:false, account_results:{ account:{ db_diagnostics:{ session:{ db_name:'session.db', success:true, index_repair:{ success:true } } } } } })
  assert.match(message, /重建索引.*session\.db/)
  assert.match(message, /KEY_SAVE_WARNING/)
})

test('normal success has no warning', () => {
  assert.equal(feedback({ db_key_persisted:true, success_count:28, failure_count:0 }), '')
})
