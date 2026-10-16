import assert from 'node:assert/strict'
import test from 'node:test'
import { restoreLegacyChatExportOrder } from '../utils/chatExportOrder.js'

test('browser folder migration recovers catalog order from hash-sorted baselines', () => {
  const baseline = { conversations: {
    a: { directory: 'conversations/second' },
    z: { directory: 'conversations/first' },
  } }
  const catalog = 'window.__WCE_FOLDER_SESSIONS__=' + JSON.stringify({ items: [
    { convDir: 'conversations/first' }, { convDir: 'conversations/unknown' },
    { convDir: 'conversations/second' }, { convDir: 'conversations/first' },
  ] }) + ';\n'
  const migrated = restoreLegacyChatExportOrder(baseline, catalog)
  assert.deepEqual(migrated.legacyConversationOrder, ['z', 'a'])
  assert.equal(baseline.conversationOrder, undefined)
  const persisted = { ...baseline, conversationOrder: ['z', 'a'] }
  assert.equal(restoreLegacyChatExportOrder(persisted, catalog), persisted)
})

test('missing or malformed legacy catalogs preserve the baseline', () => {
  const baseline = { conversations: { a: { directory: 'conversations/a' } } }
  for (const text of ['', 'window.__WCE_FOLDER_SESSIONS__=invalid;',
    'window.__WCE_FOLDER_SESSIONS__={};', 'throw new Error("do not execute")']) {
    assert.equal(restoreLegacyChatExportOrder(baseline, text), baseline)
  }
})
