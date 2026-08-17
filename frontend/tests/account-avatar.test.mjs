import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildAccountAvatarUrl,
  resolveAccountSelfUsername,
} from '../lib/account-avatar.js'


test('uses the native self username instead of the suffixed account directory', () => {
  const info = {
    account: 'SimpleChinese_a73c',
    selfUsername: 'SimpleChinese',
  }

  assert.equal(resolveAccountSelfUsername(info.account, info), 'SimpleChinese')
  assert.equal(
    buildAccountAvatarUrl('/api', info.account, info),
    '/api/chat/avatar?account=SimpleChinese_a73c&username=SimpleChinese',
  )
})


test('keeps compatibility with an older backend by normalizing WeFlow directory suffixes', () => {
  assert.equal(resolveAccountSelfUsername('SimpleChinese_a73c'), 'SimpleChinese')
  assert.equal(resolveAccountSelfUsername('wxid_demo_a73c'), 'wxid_demo')
  assert.equal(resolveAccountSelfUsername('wxid_real_user_a73c'), 'wxid_real_user')
  assert.equal(resolveAccountSelfUsername('wxid_demo'), 'wxid_demo')
  assert.equal(resolveAccountSelfUsername('wxid_dead'), 'wxid_dead')
})


test('explicit backend identity wins over directory-name inference', () => {
  assert.equal(
    resolveAccountSelfUsername('alias_a73c', {
      realtime: { nativeWxid: 'wxid_real_user' },
    }),
    'wxid_real_user',
  )
})
