/**
 * WxCDN 套餐卡 · 四档渲染器：同一张母版，四种显影技术。
 *   Free  = ASCII 字符格（92×37，母版按格采样密度字符，大数用块字）
 *   Plus  = 161×102 低分辨率 Bayer 双版印刷（墨版 + 钴蓝版套印偏移，Silkscreen 位图小字）
 *   Pro   = 拼豆（母版量化到珠子板，7px 一颗圆珠贴在钉板上，高光随光源扫过，显影 = 珠子一排排放上去）
 *   Ultra = 粒子（three.js，动态加载；母版每个像素变一粒光，指针斥力，点击冲击波）
 * 接口：{ cv, render(t, dt, pointer), dispose() }；pointer = {x,y,click} 卡内坐标或 null。
 */
import { COLS, ROWS, CW, CH, CARD_W, CARD_H, M, WIN, PAD_C, PAL, gx, gy, mkCanvas, imageRows } from './master.js'
import { fmtBytes, fmtLimit } from './format.js'

const DENS = ' .:-=+*#%@'
const BLOCK = { 0: ['111', '101', '101', '101', '111'], 1: ['010', '110', '010', '010', '111'], 2: ['111', '001', '111', '100', '111'], 3: ['111', '001', '111', '001', '111'], 4: ['101', '101', '111', '001', '001'], 5: ['111', '100', '111', '001', '111'], 6: ['111', '100', '111', '101', '111'], 7: ['111', '001', '001', '001', '001'], 8: ['111', '101', '111', '101', '111'], 9: ['111', '101', '111', '001', '111'], '.': ['0', '0', '0', '0', '1'], '—': ['000', '000', '111', '000', '000'] }
const BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
const HEX = '0123456789ABCDEF'
const rnd = (n) => (Math.random() * n) | 0
const clamp = (v, a, b) => Math.max(a, Math.min(b, v))
const classify = (r, g, b) => (b > r + 50 && b > g + 20) ? 'cobalt' : (r > g + 70 && r > b + 70) ? 'vermilion' : (r > 200 && g > 140 && b < 110) ? 'amber' : 'ink'
const COLOR = { ink: PAL.ink, cobalt: PAL.cobalt, vermilion: PAL.vermilion, amber: PAL.amber }
const inkFor = (name, dark) => (name === 'amber' && !dark ? PAL.amberInk : COLOR[name])   // 亮琥珀只在熄灯的 Ultra 上成立
const cjk = (s) => /[㐀-鿿]/.test(s)

function setup2D(cv, dpr = Math.min(window.devicePixelRatio || 1, 2)) { cv.width = CARD_W * dpr; cv.height = CARD_H * dpr; const x = cv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); return x }
const blink = (t) => Math.floor(t / 0.55) % 2 === 0

/** 大数（真字或块字）右侧的单位与标签 */
function drawUnitLabel(ctx, master, color = 'rgba(27,25,23,.65)', ink = PAL.ink) {
  if (!master.bigUnit) return
  ctx.font = "9.5px 'JetBrains Mono', monospace"; ctx.fillStyle = color; ctx.fillText(master.bigLabel || '', PAD_C * CW + (master.bigW || 0) + 12, 30.0 * CH)
  ctx.font = "600 11px 'JetBrains Mono', monospace"; ctx.fillStyle = ink; ctx.fillText(master.bigUnit || '', PAD_C * CW + (master.bigW || 0) + 12, 32.2 * CH)
}
/** 小字层：真字 + 纸底 */
function drawUtil(ctx, master, t, { paper = PAL.paper, ink = null, dark = false, plate = null } = {}) {
  ctx.font = "9.5px 'JetBrains Mono', monospace"; ctx.textBaseline = 'alphabetic'; ctx.letterSpacing = '0.6px'
  for (const u of master.utilLines) {
    const s = u.cursor ? u.t.replace('▮', blink(t) ? '▮' : ' ') : u.t
    const w = ctx.measureText(s).width; const x0 = u.right ? (u.c + 1) * CW - w : u.c * CW
    if (plate) ctx.drawImage(plate, (x0 - 3) * 2, (u.r * CH - 11) * 2, (w + 6) * 2, 26, x0 - 3, u.r * CH - 11, w + 6, 13)   // 把底纹贴回来，不是糊一块白
    else if (paper) { ctx.fillStyle = paper; ctx.fillRect(x0 - 3, u.r * CH - 11, w + 6, 13) }
    ctx.fillStyle = u.color ? inkFor(u.color, dark) : (ink || PAL.ink); ctx.fillText(s, x0, u.r * CH - 3)
  }
  ctx.letterSpacing = '0px'
}

/* ── Free · ASCII ── */
export class AsciiRenderer {
  constructor(cv, master, st) { this.cv = cv; this.master = master; this.st = st; this.ctx = setup2D(cv); this.small = mkCanvas(COLS, ROWS); this.sctx = this.small.getContext('2d', { willReadFrequently: true }); this.heat = new Float32Array(COLS * ROWS); this.typed = new Float32Array(ROWS).fill(1); this.nextReprint = 9; this.reRow = null }
  render(t, dt, pointer) {
    const { ctx, st } = this; const m = this.master.get('plain')
    this.sctx.drawImage(m, 0, 0, COLS, ROWS); const d = this.sctx.getImageData(0, 0, COLS, ROWS).data
    ctx.fillStyle = PAL.paper; ctx.fillRect(0, 0, CARD_W, CARD_H)
    ctx.font = "11px 'JetBrains Mono', monospace"; ctx.textBaseline = 'top'
    if (pointer) { const pc = pointer.x / CW, pr = pointer.y / CH; for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) { const dd = Math.hypot(c - pc, (r - pr) * 1.55); if (dd < 6) this.heat[r * COLS + c] = Math.max(this.heat[r * COLS + c], 1 - dd / 6) } }
    for (let i = 0; i < this.heat.length; i++) this.heat[i] *= Math.pow(0.35, dt)
    if (!st.reduced && (this.nextReprint -= dt) <= 0) { this.nextReprint = 9; this.reRow = rnd(ROWS); this.typed[this.reRow] = 0 }
    if (this.reRow != null && this.typed[this.reRow] < 1) this.typed[this.reRow] = Math.min(1, this.typed[this.reRow] + dt / 1.1)
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      if (c / COLS > this.typed[r]) continue
      const i = (r * COLS + c) * 4, R = d[i], G = d[i + 1], B = d[i + 2]; const L = (0.299 * R + 0.587 * G + 0.114 * B) / 255
      const k = Math.min(9, Math.round((1 - L - 0.09) * 11)); if (k <= 0) continue
      const cls = classify(R, G, B); const h = this.heat[r * COLS + c]
      ctx.fillStyle = cls === 'ink' ? `rgba(27,25,23,${(0.78 + h * 0.22).toFixed(2)})` : COLOR[cls]
      ctx.fillText(DENS[k], c * CW, r * CH)
    }
    const p = st.viewPlan
    if (st.connected && p) {
      const q = p.quota; const ex = st.exhausted && st.view === st.tier && q.limitBytes != null; const bv = q.limitBytes == null ? fmtBytes(q.usedBytes) : fmtBytes(st.disp.remaining); const txt = ex ? '0' : bv.num
      ctx.fillStyle = PAL.paper; ctx.fillRect(PAD_C * CW - 3, 27.2 * CH, 34 * CW, 6.0 * CH)
      ctx.fillStyle = ex ? PAL.vermilion : PAL.ink; let cc = PAD_C
      for (const ch of txt) { const g = BLOCK[ch]; if (!g) continue; for (let r = 0; r < 5; r++) for (let c = 0; c < g[r].length; c++) if (g[r][c] === '1') ctx.fillText('█', (cc + c) * CW, (27.9 + r) * CH); cc += g[0].length + 1 }
      this.master.bigW = (cc - PAD_C) * CW                                   // 标签/单位与另外三档同一个位置
      ctx.textBaseline = 'alphabetic'; drawUnitLabel(ctx, this.master); ctx.textBaseline = 'top'
      if (q.limitBytes != null) {
        const n = Math.round(clamp(st.disp.remaining / q.limitBytes, 0, 1) * 23); const col = ex ? PAL.vermilion : PAL.cobalt
        ctx.fillStyle = PAL.paper; ctx.fillRect(38 * CW - 2, 30 * CH - 2, 54 * CW, 2.2 * CH)
        ctx.fillStyle = PAL.ink; ctx.fillText('[', 38 * CW, 30.5 * CH)
        for (let i = 0; i < 23; i++) { ctx.fillStyle = i < n ? col : 'rgba(27,25,23,.3)'; ctx.fillText(i < n ? '██' : '░░', (39 + i * 2) * CW, 30.5 * CH) }
        ctx.fillStyle = PAL.ink; ctx.fillText(']', 85 * CW, 30.5 * CH)
      }
    }
    for (const u of this.master.utilLines) {
      const s = u.cursor ? u.t.replace('▮', blink(t) ? '▮' : ' ') : u.t
      const cells = [...s].reduce((a, ch) => a + (ch.charCodeAt(0) > 255 ? 2 : 1), 0); const c0 = u.right ? u.c + 1 - cells : u.c
      ctx.fillStyle = PAL.paper; ctx.fillRect(c0 * CW - 2, (u.r - 1) * CH + 1, cells * CW + 4, CH - 1)
      ctx.fillStyle = inkFor(u.color || 'ink', false); let cc = c0
      for (const ch of s) { ctx.fillText(ch, cc * CW, (u.r - 1) * CH); cc += ch.charCodeAt(0) > 255 ? 2 : 1 }
    }
  }
  dispose() {}
}

/* ── Plus · 绘图仪（一支笔按行走蛇形线，墨越重线抖得越厉害；显影＝笔正在画） ── */
export class PlotterRenderer {
  constructor(cv, master, st) {
    this.cv = cv; this.master = master; this.st = st; this.ctx = setup2D(cv)
    this.ROW = 4.6; this.DX = 1.55
    this.rows = Math.floor(CARD_H / this.ROW)
    this.small = mkCanvas(CARD_W, CARD_H); this.sctx = this.small.getContext('2d', { willReadFrequently: true })
    this.paths = []; this.lastImg = null; this.paper = null
  }
  makePaper() {
    const D = 2, w = CARD_W * D, h = CARD_H * D, c = mkCanvas(w, h), x = c.getContext('2d')
    x.fillStyle = '#F5F2EA'; x.fillRect(0, 0, w, h)
    x.strokeStyle = 'rgba(27,25,23,.045)'; x.lineWidth = 1                                  // 绘图纸的浅格
    for (let i = 0; i <= w; i += 20) { x.beginPath(); x.moveTo(i + .5, 0); x.lineTo(i + .5, h); x.stroke() }
    for (let j = 0; j <= h; j += 20) { x.beginPath(); x.moveTo(0, j + .5); x.lineTo(w, j + .5); x.stroke() }
    this.paper = c
  }
  build() {
    const m = this.master.get('plain')
    this.sctx.drawImage(m, 0, 0, CARD_W, CARD_H); const d = this.sctx.getImageData(0, 0, CARD_W, CARD_H).data
    const { ROW, DX } = this
    const PENS = [PAL.ink, PAL.cobalt, PAL.vermilion]
    const paths = PENS.map(() => new Path2D())
    const at = (x, y) => { const i = ((y | 0) * CARD_W + (x | 0)) * 4; return [d[i], d[i + 1], d[i + 2]] }
    this.rowsMeta = []
    for (let r = 0; r < this.rows; r++) {
      const y0 = (r + 0.5) * ROW
      let phase = r * 1.7, pen = -1, down = false
      const rev = r % 2 === 1                                                                // 蛇形：一行来一行去
      for (let k = 0; k <= (CARD_W - 2) / DX; k++) {
        const x = rev ? CARD_W - 2 - k * DX : 2 + k * DX
        const [R, G, B] = at(x, y0)
        const L = (0.299 * R + 0.587 * G + 0.114 * B) / 255
        const sat = Math.max(R, G, B) - Math.min(R, G, B)
        const T = Math.pow(clamp(((1 - L) - 0.08) * 2.0, 0, 1), 0.88)          // 头像本身发灰，先把调子拉开
        const p2 = sat > 34 ? (B > R + 14 ? 1 : (R > B + 24 ? 2 : 0)) : 0                    // 换笔：蓝的走钴蓝，暖的走朱红
        const amp = T * ROW * 0.72, freq = 0.5 + T * 1.9
        phase += freq
        const yy = y0 + Math.sin(phase) * amp
        if (T < 0.07) { down = false; continue }                                             // 抬笔：纸留白
        if (!down || p2 !== pen) { paths[p2].moveTo(x, yy); down = true; pen = p2 }
        else paths[p2].lineTo(x, yy)
      }
      this.rowsMeta.push({ y0, rev })
    }
    this.paths = paths; this.PENS = PENS
  }
  render(t, dt, pointer) {
    const { ctx, st, ROW } = this; const m = this.master.get('plain')
    if (!this.paper) this.makePaper()
    if (m !== this.lastImg) { this.build(); this.lastImg = m }
    const imgH = (imageRows(st) - WIN.r0) * CH, rev = st.reveal.p * imgH
    ctx.drawImage(this.paper, 0, 0, CARD_W, CARD_H)
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, CARD_W, rev); ctx.rect(0, imgH, CARD_W, CARD_H - imgH); ctx.clip()
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'
    for (let i = 0; i < this.paths.length; i++) { ctx.strokeStyle = this.PENS[i]; ctx.lineWidth = i === 0 ? 1.05 : 0.95; ctx.globalAlpha = i === 0 ? 0.92 : 0.86; ctx.stroke(this.paths[i]) }
    ctx.globalAlpha = 1; ctx.restore()
    ctx.strokeStyle = 'rgba(27,25,23,.4)'; ctx.lineWidth = 1                                  // 版心的定位角
    for (const [cx, cy, sx, sy] of [[6, 6, 1, 1], [CARD_W - 6, 6, -1, 1], [6, imgH - 6, 1, -1], [CARD_W - 6, imgH - 6, -1, -1]]) {
      ctx.beginPath(); ctx.moveTo(cx, cy + sy * 9); ctx.lineTo(cx, cy); ctx.lineTo(cx + sx * 9, cy); ctx.stroke()
    }
    if (st.reveal.p < 0.999 && st.reveal.p > 0) {                                             // 笔头：正在画的那一点
      const ri = Math.min(this.rowsMeta.length - 1, Math.floor(rev / ROW))
      const meta = this.rowsMeta[ri]; const frac = (rev / ROW) - ri
      const px = meta.rev ? CARD_W - frac * CARD_W : frac * CARD_W
      ctx.strokeStyle = PAL.vermilion; ctx.lineWidth = 1.2
      ctx.beginPath(); ctx.moveTo(px - 7, meta.y0); ctx.lineTo(px + 7, meta.y0); ctx.moveTo(px, meta.y0 - 7); ctx.lineTo(px, meta.y0 + 7); ctx.stroke()
      ctx.beginPath(); ctx.arc(px, meta.y0, 3.2, 0, Math.PI * 2); ctx.stroke()
      ctx.strokeStyle = 'rgba(232,68,43,.25)'; ctx.beginPath(); ctx.moveTo(0, meta.y0); ctx.lineTo(CARD_W, meta.y0); ctx.stroke()
    }
    const p = st.viewPlan
    if (st.connected && p) {
      const q = p.quota, ex = st.exhausted && st.view === st.tier && q.limitBytes != null
      const bv = q.limitBytes == null ? fmtBytes(q.usedBytes) : fmtBytes(st.disp.remaining); const txt = ex ? '0' : bv.num
      ctx.drawImage(this.paper, (PAD_C * CW - 6) * 2, 28.2 * CH * 2, 34 * CW * 2, 5.2 * CH * 2, PAD_C * CW - 6, 28.2 * CH, 34 * CW, 5.2 * CH)
      ctx.font = "400 64px 'Instrument Serif', 'Times New Roman', serif"; ctx.textBaseline = 'alphabetic'
      ctx.lineWidth = 1.1; ctx.strokeStyle = ex ? PAL.vermilion : PAL.ink                     // 大数也是笔画出来的：只描边
      ctx.strokeText(txt, PAD_C * CW, 32.2 * CH)
      ctx.fillStyle = ex ? 'rgba(232,68,43,.1)' : 'rgba(27,25,23,.08)'; ctx.fillText(txt, PAD_C * CW, 32.2 * CH)
      this.master.bigW = ctx.measureText(txt).width
    }
    drawUtil(ctx, this.master, t, { paper: '#F5F2EA' }); drawUnitLabel(ctx, this.master)
  }
  dispose() {}
}

/* ── Plus · 点阵针打（9 针打印头 + 绿条链式纸，一行一行砸出来） ── */
export class DotMatrixRenderer {
  constructor(cv, master, st) {
    this.cv = cv; this.master = master; this.st = st; this.ctx = setup2D(cv)
    this.D = 2; this.P = 6                                                   // 缓冲 2x，针距 6 设备像素 = 3 CSS px
    this.EDGE = 26                                                           // 两侧的走纸孔条
    this.buf = mkCanvas(CARD_W * this.D, CARD_H * this.D); this.bx = this.buf.getContext('2d')
    this.cols = Math.floor((CARD_W * this.D) / this.P); this.rows = Math.floor((CARD_H * this.D) / this.P)
    this.small = mkCanvas(this.cols, this.rows); this.sctx = this.small.getContext('2d', { willReadFrequently: true })
    this.paper = null; this.lastImg = null
  }
  makePaper() {
    const D = this.D, w = CARD_W * D, h = CARD_H * D, c = mkCanvas(w, h), x = c.getContext('2d')
    x.fillStyle = '#F7F5ED'; x.fillRect(0, 0, w, h)
    x.fillStyle = 'rgba(126,166,132,.18)'                                     // 绿条：每 6 行一条
    for (let y = 0; y < h; y += 88) x.fillRect(0, y, w, 44)
    const E = this.EDGE
    x.fillStyle = 'rgba(27,25,23,.05)'; x.fillRect(0, 0, E, h); x.fillRect(w - E, 0, E, h)
    x.strokeStyle = 'rgba(27,25,23,.3)'; x.setLineDash([3, 5]); x.lineWidth = 1                       // 撕线
    x.beginPath(); x.moveTo(E + .5, 0); x.lineTo(E + .5, h); x.moveTo(w - E - .5, 0); x.lineTo(w - E - .5, h); x.stroke(); x.setLineDash([])
    for (let y = 14; y < h; y += 25.4) for (const cx of [E / 2, w - E / 2]) {                          // 走纸孔
      x.fillStyle = '#DCD8CE'; x.beginPath(); x.arc(cx, y, 5.4, 0, Math.PI * 2); x.fill()
      x.strokeStyle = 'rgba(27,25,23,.22)'; x.lineWidth = 1; x.beginPath(); x.arc(cx, y, 5.4, 0, Math.PI * 2); x.stroke()
      x.strokeStyle = 'rgba(255,255,255,.7)'; x.beginPath(); x.arc(cx, y - 0.7, 4.6, Math.PI * 1.1, Math.PI * 1.9); x.stroke()
    }
    this.paper = c
  }
  build() {
    const m = this.master.get('plain'), { cols, rows, P, D, EDGE } = this
    this.sctx.drawImage(m, 0, 0, cols, rows); const d = this.sctx.getImageData(0, 0, cols, rows).data
    const INKS = [PAL.ink, PAL.cobalt, PAL.vermilion, PAL.amber]
    const paths = []; for (let i = 0; i < 12; i++) paths.push(new Path2D())
    const R = [0, 1.55, 2.15, 2.75]
    for (let y = 0; y < rows; y++) {
      const pass = (y / 21) | 0                                                                        // 一趟打印头：整趟略有偏移与浓淡
      const off = ((pass * 2654435761) % 7) / 7 * 1.1 - 0.55
      for (let x = 0; x < cols; x++) {
        const i = (y * cols + x) * 4, Rc = d[i], G = d[i + 1], B = d[i + 2]
        const L = (0.299 * Rc + 0.587 * G + 0.114 * B) / 255
        const sat = Math.max(Rc, G, B) - Math.min(Rc, G, B)
        const T = Math.pow(clamp(((1 - L) - 0.07) * 1.95, 0, 1), 0.85)
        let lvl = Math.round(T * 3 + (BAYER[y & 3][x & 3] / 16 - 0.5) * 0.95)
        lvl = Math.max(0, Math.min(3, lvl)); if (lvl === 0) continue
        const ink = sat > 34 ? (B > Rc + 14 ? 1 : (Rc > B + 40 && G < Rc - 40 ? 2 : 3)) : 0
        const cx = x * P + P / 2 + off, cy = y * P + P / 2
        if (cx < EDGE + 4 || cx > CARD_W * D - EDGE - 4) continue                                       // 孔条上不打字
        const pth = paths[ink * 3 + (lvl - 1)]
        pth.moveTo(cx + R[lvl], cy); pth.arc(cx, cy, R[lvl], 0, Math.PI * 2)
      }
    }
    this.bx.clearRect(0, 0, this.buf.width, this.buf.height)
    for (let ink = 0; ink < 4; ink++) for (let l = 0; l < 3; l++) {
      this.bx.globalAlpha = [0.55, 0.78, 0.95][l]; this.bx.fillStyle = INKS[ink]; this.bx.fill(paths[ink * 3 + l])
    }
    this.bx.globalAlpha = 1
  }
  render(t, dt, pointer) {
    const { ctx, st, D } = this; const m = this.master.get('plain')
    if (!this.paper) this.makePaper()
    if (m !== this.lastImg) { this.build(); this.lastImg = m }
    const imgH = (imageRows(st) - WIN.r0) * CH, rev = st.reveal.p * imgH
    ctx.drawImage(this.paper, 0, 0, CARD_W, CARD_H)
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, CARD_W, rev); ctx.rect(0, imgH, CARD_W, CARD_H - imgH); ctx.clip()
    ctx.drawImage(this.buf, 0, 0, CARD_W, CARD_H); ctx.restore()
    if (st.reveal.p > 0.001 && st.reveal.p < 0.999) {                                                   // 打印头正在这一行上来回
      const hx = (Math.sin(t * 9.5) * 0.5 + 0.5) * (CARD_W - 90) + 45
      ctx.fillStyle = 'rgba(27,25,23,.16)'; ctx.fillRect(0, rev - 1, CARD_W, 2)
      ctx.fillStyle = PAL.ink; ctx.fillRect(hx - 16, rev - 7, 32, 9)
      ctx.fillStyle = PAL.vermilion; ctx.fillRect(hx - 3, rev - 1, 6, 3)
    }
    drawUtil(ctx, this.master, t, { plate: this.paper }); drawUnitLabel(ctx, this.master)
  }
  dispose() {}
}

/* ── Pro · 拼豆 ── */
const BEADS = [[241, 235, 221], [255, 255, 255], [27, 25, 23], [140, 138, 133], [201, 197, 188], [47, 91, 234], [143, 180, 240], [199, 217, 245], [30, 58, 138], [63, 143, 94], [31, 90, 60], [158, 216, 184], [232, 217, 168], [242, 178, 51], [232, 68, 43], [185, 169, 227], [245, 200, 170], [120, 84, 60], [92, 122, 150]]
export class BeadRenderer {
  constructor(cv, master, st) { this.cv = cv; this.master = master; this.st = st; this.ctx = setup2D(cv); this.cell = 7; this.BC = Math.round(CARD_W / this.cell); this.BR = Math.round(CARD_H / this.cell); this.small = mkCanvas(this.BC, this.BR); this.sctx = this.small.getContext('2d', { willReadFrequently: true }); this.idx = new Int16Array(this.BC * this.BR); this.lastImg = null; this.placedAt = new Float32Array(this.BR).fill(-9); this.lastRows = -1; this.sprites = []; this.board = null; this.lx = 9; this.ly = 9 }
  quantize() {
    const m = this.master.get('plain'); this.sctx.drawImage(m, 0, 0, this.BC, this.BR); const d = this.sctx.getImageData(0, 0, this.BC, this.BR).data
    const imgRows = Math.round((imageRows(this.st) - WIN.r0) * CH / this.cell)
    for (let y = 0; y < this.BR; y++) for (let x = 0; x < this.BC; x++) {
      const i = y * this.BC + x, j = i * 4, R = d[j], G = d[j + 1], B = d[j + 2]
      const L = (0.299 * R + 0.587 * G + 0.114 * B) / 255; const sat = Math.max(R, G, B) - Math.min(R, G, B)
      if ((y >= imgRows || !this.st.reveal.image) && L > 0.9 && sat < 24) { this.idx[i] = -1; continue }   // 纸面（或没有图时的整个图区）：空钉
      let best = 0, bd = 1e9; for (let k = 0; k < BEADS.length; k++) { const b = BEADS[k]; const dd = (R - b[0]) ** 2 + (G - b[1]) ** 2 * 1.4 + (B - b[2]) ** 2; if (dd < bd) { bd = dd; best = k } }
      this.idx[i] = best
    }
  }
  /** 钉板：板色 + 每格一根钉子（豆盖不到的地方才看得见） */
  makeBoard() {
    const D = 2, w = CARD_W * D, h = CARD_H * D, c = mkCanvas(w, h), x = c.getContext('2d'); const cs = this.cell * D
    x.fillStyle = '#F0ECE3'; x.fillRect(0, 0, w, h)
    x.strokeStyle = 'rgba(27,25,23,.045)'; x.lineWidth = 1
    for (let i = 0; i <= this.BC; i++) { x.beginPath(); x.moveTo(i * cs + .5, 0); x.lineTo(i * cs + .5, h); x.stroke() }
    for (let j = 0; j <= this.BR; j++) { x.beginPath(); x.moveTo(0, j * cs + .5); x.lineTo(w, j * cs + .5); x.stroke() }
    for (let j = 0; j < this.BR; j++) for (let i = 0; i < this.BC; i++) {
      const cx = i * cs + cs / 2, cy = j * cs + cs / 2
      x.fillStyle = 'rgba(27,25,23,.11)'; x.beginPath(); x.arc(cx, cy + 1.1, cs * 0.19, 0, Math.PI * 2); x.fill()
      x.fillStyle = 'rgba(255,255,255,.9)'; x.beginPath(); x.arc(cx, cy - 0.5, cs * 0.16, 0, Math.PI * 2); x.fill()
    }
    this.board = c
  }
  /** 一颗豆 = 一小段塑料管：平色管壁 + 正中通孔 + 环上月牙高光；孔壁背着光的一侧才亮 */
  makeSprites(hx, hy) {
    const S2 = 34, cx = S2 / 2, cy = S2 / 2, rad = S2 * 0.48, hole = rad * 0.5, a = Math.atan2(hy, hx)
    this.sprites = BEADS.map(([R, G, B]) => {
      const c = mkCanvas(S2, S2), x = c.getContext('2d')
      const mix = (f) => `rgb(${clamp(R * f, 0, 255) | 0},${clamp(G * f, 0, 255) | 0},${clamp(B * f, 0, 255) | 0})`
      const lift = (f) => `rgb(${clamp(R + (255 - R) * f, 0, 255) | 0},${clamp(G + (255 - G) * f, 0, 255) | 0},${clamp(B + (255 - B) * f, 0, 255) | 0})`
      x.fillStyle = 'rgba(24,20,14,.20)'; x.beginPath(); x.ellipse(cx + rad * .10, cy + rad * .17, rad * .99, rad * .95, 0, 0, Math.PI * 2); x.fill()   // 落在板上的影
      const g = x.createLinearGradient(cx + hx * rad, cy + hy * rad, cx - hx * rad, cy - hy * rad)
      g.addColorStop(0, lift(.17)); g.addColorStop(.42, mix(1)); g.addColorStop(1, mix(.62))
      x.fillStyle = g; x.beginPath(); x.arc(cx, cy, rad, 0, Math.PI * 2); x.fill()                                                                      // 管壁
      x.globalAlpha = .55; x.strokeStyle = mix(.5); x.lineWidth = S2 * .05; x.beginPath(); x.arc(cx, cy, rad - S2 * .025, 0, Math.PI * 2); x.stroke(); x.globalAlpha = 1   // 豆与豆的分界
      const gh = x.createLinearGradient(cx + hx * hole, cy + hy * hole, cx - hx * hole, cy - hy * hole)
      gh.addColorStop(0, mix(.24)); gh.addColorStop(.55, mix(.4)); gh.addColorStop(1, mix(.88))
      x.fillStyle = gh; x.beginPath(); x.arc(cx, cy, hole, 0, Math.PI * 2); x.fill()                                                                    // 通孔：迎光侧最暗，对侧内壁被照亮
      x.strokeStyle = 'rgba(255,255,255,.45)'; x.lineWidth = S2 * .03; x.beginPath(); x.arc(cx, cy, hole + S2 * .012, a + Math.PI - .95, a + Math.PI + .95); x.stroke()   // 对侧唇口
      x.lineCap = 'round'
      x.strokeStyle = 'rgba(255,255,255,.4)'; x.lineWidth = (rad - hole) * .42; x.beginPath(); x.arc(cx, cy, (rad + hole) / 2, a - .62, a + .62); x.stroke()              // 环上月牙
      x.strokeStyle = 'rgba(255,255,255,.15)'; x.lineWidth = (rad - hole) * .34; x.beginPath(); x.arc(cx, cy, (rad + hole) / 2, a + Math.PI - .5, a + Math.PI + .5); x.stroke()
      return c
    })
  }
  render(t, dt, pointer) {
    const { ctx, cell, BC, BR, st } = this; const m = this.master.get('plain')
    if (m !== this.lastImg) { this.quantize(); this.lastImg = m }
    const imgRows = Math.round((imageRows(st) - WIN.r0) * CH / cell); const rows = Math.min(imgRows, Math.floor(st.reveal.p * imgRows + 0.001))
    if (rows !== this.lastRows) { for (let y = Math.max(0, this.lastRows); y < rows; y++) this.placedAt[y] = t; if (rows < this.lastRows) for (let y = rows; y < imgRows; y++) this.placedAt[y] = -9; this.lastRows = rows }
    const lx = Math.cos(t * 0.25) * 0.55 - 0.2, ly = -0.55 + Math.sin(t * 0.19) * 0.2
    if (!this.sprites.length || (!st.reduced && Math.abs(lx - this.lx) + Math.abs(ly - this.ly) > 0.04)) { this.makeSprites(lx, ly); this.lx = lx; this.ly = ly }
    if (!this.board) this.makeBoard()
    ctx.drawImage(this.board, 0, 0, CARD_W, CARD_H)
    const px = pointer ? pointer.x : -1e4, py = pointer ? pointer.y : -1e4
    for (let y = 0; y < BR; y++) {
      const inImg = y < imgRows; if (inImg && y >= rows) continue
      const age = inImg ? t - this.placedAt[y] : 9; const pop = st.reduced ? 1 : age < 0.35 ? 0.55 + 0.45 * (1 - Math.pow(1 - age / 0.35, 2)) * (1 + 0.25 * Math.sin(age / 0.35 * Math.PI)) : 1
      for (let x = 0; x < BC; x++) {
        const k = this.idx[y * BC + x]; if (k < 0) continue; const sp = this.sprites[k]; const cx = x * cell + cell / 2, cy = y * cell + cell / 2
        const dd = Math.hypot(cx - px, cy - py); const lift = dd < 42 ? (1 - dd / 42) : 0; const s = cell * 1.2 * pop * (1 + lift * 0.26)
        ctx.drawImage(sp, cx - s / 2, cy - s / 2 - lift * 2, s, s)
      }
    }
    const p = st.viewPlan
    if (st.connected && p) {
      const q = p.quota; const ex = st.exhausted && st.view === st.tier && q.limitBytes != null; const bv = q.limitBytes == null ? fmtBytes(q.usedBytes) : fmtBytes(st.disp.remaining); const txt = ex ? '0' : bv.num
      const rx = PAD_C * CW - 6, ry = 28.2 * CH, rw = 34 * CW, rh = 5.2 * CH
      ctx.drawImage(this.board, rx * 2, ry * 2, rw * 2, rh * 2, rx, ry, rw, rh)   // 把钉板还回来，不是一块白板
      ctx.fillStyle = ex ? PAL.vermilion : PAL.ink; ctx.font = "400 64px 'Instrument Serif', 'Times New Roman', serif"; ctx.textBaseline = 'alphabetic'; ctx.fillText(txt, PAD_C * CW, 32.2 * CH); this.master.bigW = ctx.measureText(txt).width
    }
    drawUtil(ctx, this.master, t); drawUnitLabel(ctx, this.master)
  }
  dispose() {}
}

/* ── Ultra · 粒子（three.js 动态加载） ── */
const P_VERT = `
uniform float uTime, uShock, uBright, uReveal, uPR; uniform vec2 uPointer, uShockC;
attribute vec3 aColor; attribute float aSeed, aBright, aOrder;
varying vec3 vColor; varying float vA;
vec3 curl(vec3 p){ return vec3(sin(p.y*3.1+uTime*0.6+aSeed*6.0), cos(p.x*2.7-uTime*0.5+aSeed*4.0), sin((p.x+p.y)*2.2+uTime*0.4)); }
void main(){
  vec3 pos = position; pos += curl(position) * 0.022;
  vec2 d = pos.xy - uPointer; float dist = length(d); float f = smoothstep(0.5, 0.0, dist); pos.xy += normalize(d + 1e-4) * f * 0.3;
  vec2 ds = pos.xy - uShockC; float sd = length(ds); float ring = exp(-pow((sd - uShock * 4.0) * 3.0, 2.0)) * step(0.001, uShock) * (1.0 - uShock); pos.xy += normalize(ds + 1e-4) * ring * 0.6;
  float revealed = aOrder < 0.0 ? 1.0 : step(aOrder, uReveal);
  vA = aBright * revealed * (0.88 + 0.12 * sin(uTime * 1.6 + aSeed * 40.0)) + f * 0.6;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0); gl_Position = projectionMatrix * mv;
  gl_PointSize = (2.2 + f * 1.5) * uPR; vColor = aColor;
}`
const P_FRAG = `uniform float uBright; varying vec3 vColor; varying float vA; void main(){ vec2 uv = gl_PointCoord - 0.5; float d = length(uv); if (d > 0.5) discard; float a = smoothstep(0.5, 0.1, d) * vA * uBright; gl_FragColor = vec4(vColor * (0.7 + 0.6 * vA), a); }`
export class ParticleRenderer {
  constructor(cv, master, st, overlay) { this.cv = cv; this.master = master; this.st = st; this.ov = overlay; this.octx = setup2D(overlay); this.ok = false; this.ready = false; this.lastImg = null; this.shockT = -1 }
  async init() {
    if (this.ready) return this.ok
    const THREE = await import('three'); this.THREE = THREE
    try { this.R = new THREE.WebGLRenderer({ canvas: this.cv, antialias: false, alpha: true }) } catch (e) { this.ready = true; return false }
    const R = this.R; R.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25)); R.setSize(CARD_W, CARD_H, false); R.setClearColor(0x000000, 0)
    const CARD_U = 6.44, CARD_V = 4.07
    this.scene = new THREE.Scene(); this.camera = new THREE.OrthographicCamera(-CARD_U / 2, CARD_U / 2, CARD_V / 2, -CARD_V / 2, 0.1, 10); this.camera.position.z = 5
    this.SW = 400; this.SH = 253; this.small = mkCanvas(this.SW, this.SH); this.sctx = this.small.getContext('2d', { willReadFrequently: true })
    const N = this.SW * this.SH; const pos = new Float32Array(N * 3), col = new Float32Array(N * 3), seed = new Float32Array(N), bright = new Float32Array(N), order = new Float32Array(N)
    for (let y = 0; y < this.SH; y++) for (let x = 0; x < this.SW; x++) { const i = y * this.SW + x; pos[i * 3] = (x / this.SW - 0.5) * CARD_U + (Math.random() - 0.5) * 0.01; pos[i * 3 + 1] = (0.5 - y / this.SH) * CARD_V; pos[i * 3 + 2] = 0; seed[i] = Math.random(); order[i] = -1 }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('aColor', new THREE.BufferAttribute(col, 3)); g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1)); g.setAttribute('aBright', new THREE.BufferAttribute(bright, 1)); g.setAttribute('aOrder', new THREE.BufferAttribute(order, 1))
    this.U = { uTime: { value: 0 }, uShock: { value: 0 }, uBright: { value: 1 }, uReveal: { value: 1 }, uPR: { value: R.getPixelRatio() }, uPointer: { value: new THREE.Vector2(99, 99) }, uShockC: { value: new THREE.Vector2(0, 0) } }
    this.points = new THREE.Points(g, new THREE.ShaderMaterial({ uniforms: this.U, vertexShader: P_VERT, fragmentShader: P_FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); this.scene.add(this.points)
    this.CARD_U = CARD_U; this.CARD_V = CARD_V; this.ok = true; this.ready = true; return true
  }
  sample() {
    const m = this.master.get('dark'); this.sctx.drawImage(m, 0, 0, this.SW, this.SH); const d = this.sctx.getImageData(0, 0, this.SW, this.SH).data
    const col = this.points.geometry.getAttribute('aColor'), br = this.points.geometry.getAttribute('aBright'), od = this.points.geometry.getAttribute('aOrder')
    const wx0 = Math.floor(WIN.c0 / COLS * this.SW), wx1 = Math.ceil(WIN.c1 / COLS * this.SW), wy0 = Math.floor(WIN.r0 / ROWS * this.SH), wy1 = Math.ceil(imageRows(this.st) / ROWS * this.SH); const winIdx = []
    /* 图区取反：纸底沉到黑里，墨与颜色才发光——和另外三档「纸是空的」保持同一套语义 */
    for (let y = 0; y < this.SH; y++) for (let x = 0; x < this.SW; x++) {
      const i = y * this.SW + x, j = i * 4
      const R = d[j] / 255, G = d[j + 1] / 255, B = d[j + 2] / 255
      const L = 0.299 * R + 0.587 * G + 0.114 * B
      const inWin = x >= wx0 && x < wx1 && y >= wy0 && y < wy1
      if ((!inWin && L < 0.12) || (inWin && !this.st.reveal.image)) { col.setXYZ(i, 0.95, 0.85, 0.6); br.setX(i, 0.028); if (!inWin) od.setX(i, -1); continue }   // 底座尘
      if (inWin) {
        const mx = Math.max(R, G, B), mn = Math.min(R, G, B), k = mx > 0.05 ? 1 / mx : 0            // k：保色相不保明度
        const matter = Math.max(1 - L, (mx - mn) * 1.6)                                              // 落在纸上的东西 = 墨 + 彩，纸本身趋零
        col.setXYZ(i, k ? 0.34 + 0.66 * R * k : 0.98, k ? 0.40 + 0.60 * G * k : 0.95, k ? 0.46 + 0.54 * B * k : 0.88)
        br.setX(i, 0.028 + Math.pow(matter, 1.5) * 1.25)
        winIdx.push([i, matter])
      } else { col.setXYZ(i, R + 0.05, G + 0.05, B + 0.05); br.setX(i, 0.45 + L * 1.1); od.setX(i, -1) }   // 下带的字：直接给亮
    }
    winIdx.sort((a, b) => b[1] - a[1]); winIdx.forEach(([i], k) => od.setX(i, k / winIdx.length))   // 先显墨，后显尘
    col.needsUpdate = br.needsUpdate = od.needsUpdate = true
  }
  render(t, dt, pointer) {
    if (!this.ok) return; const { st } = this; const m = this.master; const img = m.get('dark'); if (this.lastImg !== img) { this.sample(); this.lastImg = img }
    this.U.uTime.value = t; this.U.uReveal.value = st.reveal.p
    if (pointer && !st.reduced) this.U.uPointer.value.set((pointer.x / CARD_W - 0.5) * this.CARD_U, (0.5 - pointer.y / CARD_H) * this.CARD_V); else this.U.uPointer.value.set(99, 99)
    if (pointer && pointer.click && this.shockT < 0) { this.shockT = 0; this.U.uShockC.value.copy(this.U.uPointer.value); pointer.click = false }
    if (this.shockT >= 0) { this.shockT += dt; this.U.uShock.value = clamp(this.shockT / 0.7, 0, 1); if (this.shockT > 0.7) { this.shockT = -1; this.U.uShock.value = 0 } }
    this.R.render(this.scene, this.camera)
    const o = this.octx; o.clearRect(0, 0, CARD_W, CARD_H)
    drawUtil(o, m, t, { paper: null, ink: 'rgba(242,237,224,.8)', dark: true }); drawUnitLabel(o, m, 'rgba(242,237,224,.8)', PAL.light)
  }
  dispose() { try { this.points?.geometry?.dispose(); this.points?.material?.dispose(); this.R?.dispose() } catch (e) {} this.ok = false }
}
