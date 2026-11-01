/**
 * WxCDN 套餐卡 · 母版（CardMaster）。
 * 一张 644×407 的卡 = 92×37 格（7×11px），母版按 2x 画在离屏 canvas，四档渲染器各自"显影"它。
 * 上半部（行 0–27）是图，边到边；下带（行 28–37）是额度、量表、兑换槽、身份行。
 * 未接入时下带只有兑换槽。
 */
import { fmtBytes, fmtB, fmtLimit, fmtCountdown, localDate, daysLeft, nowSec } from './format.js'

export const COLS = 92, ROWS = 37, CW = 7, CH = 11, CARD_W = 644, CARD_H = 407, M = 2
export const WIN = { c0: 0, c1: 92, r0: 0, r1: 27 }
export const WIN_ROWS_IDLE = 37     // 未接入时图铺满整张卡（兑换输入在卡下方的 DOM 行）
export const imageRows = (st) => (st?.connected && st?.viewPlan ? WIN.r1 : WIN_ROWS_IDLE)
export const PAD_C = 3.5, RIGHT_C = 87.5
export const PAL = { paper: '#F4F0E8', ink: '#1B1917', cobalt: '#2F5BEA', vermilion: '#E8442B', amber: '#F2B233', amberInk: '#8A5A00', dark: '#0E0C0B', light: '#F2EDE0' }
export const gx = (c) => c * CW * M
export const gy = (r) => r * CH * M
export const mkCanvas = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c }
const clamp = (v, a, b) => Math.max(a, Math.min(b, v))

export class CardMaster {
  /** @param {object} st 共享状态（见 PlanWindow.vue 的 cardState） */
  constructor(st) { this.st = st; this.dirty = true; this.cache = {}; this.win = mkCanvas((WIN.c1 - WIN.c0) * CW * M, Math.ceil((WIN_ROWS_IDLE - WIN.r0) * CH * M)); this.utilLines = []; this.bigW = 0; this.bigUnit = ''; this.bigLabel = '' }
  invalidate() { this.dirty = true }
  get(variant) {
    if (this.dirty) { this.cache = {}; this.dirty = false; this.buildUtil(); this.drawWindow() }
    if (!this.cache[variant]) this.cache[variant] = this.draw(variant)
    return this.cache[variant]
  }
  buildUtil() {
    const st = this.st, U = [], p = st.viewPlan
    if (st.reveal.stamp) U.push({ r: imageRows(st) - 0.8, c: RIGHT_C, t: st.reveal.stamp, right: true, color: st.reveal.stampColor || 'cobalt' })
    if (!st.connected || !p) { this.utilLines = U; return }
    const q = p.quota, a = p.account
    if (q.limitBytes != null) { U.push({ r: 34, c: PAD_C, t: `USED ${fmtB(q.usedBytes)} / ${fmtLimit(q.limitBytes)}` }); U.push({ r: 34, c: 38, t: '0' }); U.push({ r: 34, c: RIGHT_C, t: fmtLimit(q.limitBytes), right: true }) }
    else { U.push({ r: 34, c: PAD_C, t: `已用 ${Number(q.usedBytes || 0).toLocaleString('en-US')} B` }); U.push({ r: 34, c: 38, t: '没有上限 · 河床不闭合' }) }   // 小字一律走上层真字：粒子分辨不出 9px
    if (st.exhausted && st.view === st.tier && q.resetsAt) U.push({ r: 35, c: PAD_C, t: `用完了 · ${fmtCountdown(q.resetsAt - nowSec())} 后重置`, color: 'vermilion' })
    if (st.view !== st.tier) U.push({ r: 35, c: RIGHT_C, t: `预览 · 不是你现在的套餐（${String(st.tier).toUpperCase()}）`, right: true, color: 'amber' })
    else {
      const same = !a.permanentPlan || a.permanentPlan === a.plan
      U.push({ r: 35, c: RIGHT_C, t: `${a.nickname || ''} · ${String(a.plan || '').toUpperCase()}${same ? '' : ` · 永久底座 ${String(a.permanentPlan).toUpperCase()}`}`.replace(/^ · /, ''), right: true })
      if (a.plan === 'Pro' && a.proExpiresAt) U.push({ r: 36, c: RIGHT_C, t: `PRO → ${localDate(a.proExpiresAt)} · 还有 ${daysLeft(a.proExpiresAt)} 天`, right: true, color: daysLeft(a.proExpiresAt) <= 7 ? 'amber' : null })
      else if (a.proExpiresAt && a.proExpiresAt < nowSec()) U.push({ r: 36, c: RIGHT_C, t: `PRO 已于 ${localDate(a.proExpiresAt)} 到期 · 已回落 ${String(a.plan || '').toUpperCase()}`, right: true, color: 'amber' })
      if (q.resetsAt) U.push({ r: 36.5, c: PAD_C, t: `${localDate(q.resetsAt)} 重置 · 还有 ${fmtCountdown(q.resetsAt - nowSec())}` })
      else U.push({ r: 36.5, c: PAD_C, t: '终身额度 · 不重置' })
    }
    if (st.offline) U.push({ r: 1.4, c: RIGHT_C, t: '离线 · 等待网络', right: true, color: 'vermilion' })
    this.utilLines = U
  }
  drawWindow() {
    const c = this.win, x = c.getContext('2d'), w = c.width, p = this.st.reveal.p, img = this.st.reveal.image
    const h = Math.round((imageRows(this.st) - WIN.r0) * CH * M)
    x.fillStyle = PAL.paper; x.fillRect(0, 0, w, c.height)
    if (img && img.width && img.height) {
      const rows = Math.floor(p * h)
      if (rows > 0) {
        const s = Math.max(w / img.width, h / img.height); const dw = img.width * s, dh = img.height * s; const dx = (w - dw) / 2, dy = (h - dh) / 2   // cover
        x.save(); x.beginPath(); x.rect(0, 0, w, rows); x.clip(); x.drawImage(img, dx, dy, dw, dh); x.restore()
      }
    }
    x.fillStyle = 'rgba(27,25,23,.16)'
    for (let yy = Math.floor(p * h) + 6; yy < h; yy += 14) for (let xx = 6; xx < w; xx += 14) x.fillRect(xx, yy, 2, 2)
    if (p < 1 && p > 0) { x.fillStyle = 'rgba(255,255,255,.6)'; x.fillRect(0, Math.floor(p * h) - 2, w, 3) }
  }
  draw(variant) {
    const st = this.st, dark = variant === 'dark', util = variant === 'full'
    const c = mkCanvas(CARD_W * M, CARD_H * M), x = c.getContext('2d')
    const ink = dark ? PAL.light : PAL.ink
    x.fillStyle = dark ? PAL.dark : PAL.paper; x.fillRect(0, 0, c.width, c.height)
    const wh = Math.round((imageRows(st) - WIN.r0) * CH * M)
    x.textBaseline = 'alphabetic'; x.drawImage(this.win, 0, 0, this.win.width, wh, gx(WIN.c0), gy(WIN.r0), this.win.width, wh)
    const p = st.viewPlan
    this.bigW = 0; this.bigUnit = ''; this.bigLabel = ''
    if (st.connected && p) {
      const q = p.quota
      const big = q.limitBytes == null ? fmtBytes(q.usedBytes) : fmtBytes(st.disp.remaining)
      const exhausted = st.exhausted && st.view === st.tier && q.limitBytes != null
      const txt = exhausted ? '0' : big.num
      x.fillStyle = exhausted ? PAL.vermilion : ink; x.font = `400 ${64 * M}px 'Instrument Serif', 'Times New Roman', serif`; x.fillText(txt, gx(PAD_C), gy(32.2))
      const bw = x.measureText(txt).width; this.bigW = bw / M; this.bigUnit = exhausted ? 'B' : big.unit; this.bigLabel = q.limitBytes == null ? '累计 · LIFETIME' : '剩余 · REMAINING'
      if (util) { x.font = `600 ${11 * M}px 'JetBrains Mono', monospace`; x.fillText(this.bigUnit, gx(PAD_C) + bw + 10 * M, gy(32.2)); x.font = `400 ${9 * M}px 'JetBrains Mono', monospace`; x.fillText(this.bigLabel, gx(PAD_C) + bw + 10 * M, gy(30.0)) }
      if (q.limitBytes != null) {
        const x0 = gx(38), x1 = gx(RIGHT_C + 1), y0 = gy(30.4), hh = gy(1.6) - gy(0); const rem = clamp(st.disp.remaining / q.limitBytes, 0, 1)
        x.fillStyle = dark ? 'rgba(242,237,224,.14)' : 'rgba(27,25,23,.14)'; x.fillRect(x0, y0, x1 - x0, hh)
        x.fillStyle = exhausted ? PAL.vermilion : PAL.cobalt; x.fillRect(x0, y0, (x1 - x0) * rem, hh)
        x.strokeStyle = ink; x.lineWidth = 2; x.strokeRect(x0, y0, x1 - x0, hh)
      } else {
        x.strokeStyle = dark ? 'rgba(242,237,224,.35)' : 'rgba(27,25,23,.35)'; x.setLineDash([6, 8]); x.lineWidth = 2; x.beginPath(); x.moveTo(gx(38), gy(31.2)); x.lineTo(gx(RIGHT_C + 1), gy(31.2)); x.stroke(); x.setLineDash([])
      }
    }
    if (util) this.drawUtil(x, dark)
    return c
  }
  drawUtil(x, dark) {
    const col = { ink: dark ? PAL.light : PAL.ink, cobalt: PAL.cobalt, vermilion: PAL.vermilion, amber: PAL.amber }
    x.font = `400 ${9 * M}px 'JetBrains Mono', monospace`; x.textBaseline = 'alphabetic'; x.letterSpacing = '1px'
    for (const u of this.utilLines) { x.fillStyle = col[u.color || 'ink']; x.textAlign = u.right ? 'right' : 'left'; x.fillText(u.t.replace(' ▮', ''), gx(u.c) + (u.right ? CW * M : 0), gy(u.r) - 6) }
    x.textAlign = 'left'; x.letterSpacing = '0px'
  }
}
