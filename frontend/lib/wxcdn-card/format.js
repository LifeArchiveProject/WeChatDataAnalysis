/**
 * WxCDN 套餐卡 · 纯函数：字节格式、倒计时、档位表、兑换码规范化。
 * 无框架依赖，node:test 可直接测。
 */
export const MiB = 1048576
export const GiB = MiB * 1024
export const TiB = GiB * 1024

/** 契约里的四档（展示用常量；真值以 /quota 为准） */
export const TIERS = {
  Free: { idx: 0, limit: 50 * MiB, period: 'day', label: '50 MiB / 天' },
  Plus: { idx: 1, limit: 10 * GiB, period: 'month', label: '10 GiB / 月' },
  Pro: { idx: 2, limit: 200 * GiB, period: 'month', label: '200 GiB / 月' },
  Ultra: { idx: 3, limit: null, period: 'lifetime', label: '不限量' },
}
export const ORDER = ['Free', 'Plus', 'Pro', 'Ultra']
export const nextTier = (t) => ORDER[Math.min(3, (TIERS[t]?.idx ?? 0) + 1)]
export const normalizeTier = (v) => {
  const s = String(v || '').trim().toLowerCase()
  return ORDER.find((t) => t.toLowerCase() === s) || null
}

export const pad2 = (n) => String(n).padStart(2, '0')
export const nowSec = () => Date.now() / 1000

export function fmtBytes(b) {
  if (b == null || !Number.isFinite(Number(b))) return { num: '—', unit: '' }
  b = Number(b)
  if (b < 1) return { num: '0', unit: 'B' }
  if (b < GiB) return { num: (b / MiB).toFixed(1), unit: 'MiB' }
  if (b < TiB) return { num: (b / GiB).toFixed(2), unit: 'GiB' }
  return { num: (b / TiB).toFixed(2), unit: 'TiB' }
}
export const fmtB = (b) => { const f = fmtBytes(b); return `${f.num} ${f.unit}`.trim() }
export const fmtLimit = (b) => (b == null ? '∞' : b >= GiB ? `${Math.round(b / GiB)} GiB` : `${Math.round(b / MiB)} MiB`)
export function fmtCountdown(sec) {
  sec = Math.max(0, Math.floor(Number(sec) || 0))
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60
  return d > 0 ? `${d}天${h}小时` : h > 0 ? `${h}小时${pad2(m)}分` : `${m}分${pad2(s)}秒`   // 不要写成 15:58:31：卡上另有真钟点，会看混
}
export const localHM = (ts) => { const d = new Date(ts * 1000); return `${pad2(d.getHours())}:${pad2(d.getMinutes())}` }
export const localDate = (ts) => { const d = new Date(ts * 1000); return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}` }
export const daysLeft = (ts) => Math.max(0, Math.ceil((Number(ts) - nowSec()) / 86400))

/**
 * 兑换码规范化（与后端一致）：去空白/连字符（含全角）、大写、去前导 WX、O→0 I→1 L→1、只留 Crockford 集、截 20 位。
 * 返回 { code, fixes } —— fixes 是被纠正过的下标，界面可以闪一下提示。
 */
export function normalizeRedeemCode(raw) {
  let s = String(raw || '').replace(/[\s\-‐‑–—－_]/g, '').toUpperCase()
  if (s.startsWith('WX')) s = s.slice(2)
  const out = [], fixes = []
  for (const ch of s) {
    let c = ch
    if (c === 'O') { c = '0'; fixes.push(out.length) } else if (c === 'I' || c === 'L') { c = '1'; fixes.push(out.length) }
    if (/[0-9A-HJKMNP-TV-Z]/.test(c) && out.length < 20) out.push(c)
  }
  return { code: out.join(''), fixes }
}
export const formatRedeemCode = (code) => Array.from({ length: 20 }, (_, i) => code[i] || '_').join('').replace(/(.{4})(?=.)/g, '$1-')

/** 把真实用量套进另一档（契约：套餐变化后同周期用量保留），用于浏览其它版本 */
export function projectPlan(snapshotAccount, snapshotQuota, tier) {
  const T = TIERS[tier]
  const used = Number(snapshotQuota?.usedBytes || 0)
  const account = { ...(snapshotAccount || {}), plan: tier }
  if (T.limit == null) return { account, quota: { period: 'lifetime', periodKey: 'lifetime', limitBytes: null, usedBytes: used, remainingBytes: null, resetsAt: null } }
  return { account, quota: { period: T.period, periodKey: T.period, limitBytes: T.limit, usedBytes: used, remainingBytes: Math.max(0, T.limit - used), resetsAt: snapshotQuota?.resetsAt ?? null } }
}
