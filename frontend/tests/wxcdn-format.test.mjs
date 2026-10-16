import assert from 'node:assert/strict'
import test from 'node:test'
import { MiB, GiB, TiB, fmtBytes, fmtB, fmtLimit, fmtCountdown, normalizeRedeemCode, formatRedeemCode, projectPlan, nextTier, normalizeTier } from '../lib/wxcdn-card/format.js'

test('字节格式：MiB 一位小数、GiB/TiB 两位、null 为破折号', () => {
  assert.deepEqual(fmtBytes(13212672), { num: '12.6', unit: 'MiB' })
  assert.deepEqual(fmtBytes(10 * GiB - 826781696), { num: '9.23', unit: 'GiB' })
  assert.deepEqual(fmtBytes(1.34 * TiB), { num: '1.34', unit: 'TiB' })
  assert.equal(fmtB(0), '0 B')
  assert.equal(fmtBytes(null).num, '—')
  assert.equal(fmtLimit(50 * MiB), '50 MiB'); assert.equal(fmtLimit(200 * GiB), '200 GiB'); assert.equal(fmtLimit(null), '∞')
})

test('倒计时：带单位，别长得像钟点', () => {
  assert.equal(fmtCountdown(5 * 3600 + 12 * 60 + 33), '5小时12分')
  assert.equal(fmtCountdown(25 * 86400 + 3600), '25天1小时')
  assert.equal(fmtCountdown(90), '1分30秒')
  assert.equal(fmtCountdown(-5), '0分00秒')
})

test('兑换码规范化：去空白连字符（含全角）、大写、去 wx、O/I/L 纠正、只留 Crockford、截 20 位', () => {
  assert.equal(normalizeRedeemCode(' wx-7k9m p4rx-2v8d-q6yt-h3nc ').code, '7K9MP4RX2V8DQ6YTH3NC')
  const r = normalizeRedeemCode('WX-O1IL-ABCD－EFGH_JKMN—PQRS')
  assert.equal(r.code, '0111ABCDEFGHJKMNPQRS')
  assert.deepEqual(r.fixes, [0, 2, 3])
  assert.equal(normalizeRedeemCode('wx-uuuu-1234').code, '1234')          // U 不在 Crockford 集
  assert.equal(normalizeRedeemCode('0123456789ABCDEFGHJKMNPQ').code.length, 20)
  assert.equal(formatRedeemCode('7K9M'), '7K9M-____-____-____-____')
})

test('档位：下一档与套用真实用量', () => {
  assert.equal(nextTier('Free'), 'Plus'); assert.equal(nextTier('Ultra'), 'Ultra'); assert.equal(normalizeTier('pro'), 'Pro'); assert.equal(normalizeTier('x'), null)
  const p = projectPlan({ nickname: 'a', permanentPlan: 'Free' }, { usedBytes: 13212672, resetsAt: 123 }, 'Plus')
  assert.equal(p.quota.limitBytes, 10 * GiB); assert.equal(p.quota.remainingBytes, 10 * GiB - 13212672); assert.equal(p.account.plan, 'Plus')
  assert.equal(projectPlan({}, { usedBytes: 5 }, 'Ultra').quota.limitBytes, null)
})
