// 「私人词典」跨页（Card06 / KeywordDictionarySpread.vue）的版式引擎。
// 纯几何，无 Vue / DOM 依赖，可 `node --test` 直接跑（见 tests/wrapped-dictionary-layout.test.mjs）。
//
// ── 为什么要有这一层 ──
// 这张卡的画布跟着舞台画幅走（16:9 是 1600×900，3:4 是 1040×1386，9:16 是 900×1600 …），
// 而 .kd-spread 是 overflow:hidden 的：任何算出来落在画布外的东西直接被裁掉，不是「小一点」而是「没了」。
// 所以版式**不能按某一档硬写常量**，必须由画布宽高推出来。这里的每个数都只从 (W, H) 推导。
//
// ── 三条硬规则 ──
// ① 不靠缩小适配：字号 / 行高 / 镜片直径 / 行高 28 这些构件常量在任何画幅下都不变，变的只有排布；
// ② 16:9 逐像素零回归：buildDictionaryLayout(1600, 900) 必须逐字段等于 WIDE_BASELINE（测试里断言）；
// ③ 一个元素都不能丢：ENTRY_CAP 条词目 + 凡例 + 版权行 + 页码永远排得进版口，
//    排不下就加栏数 / 换版式，绝不砍词条、绝不缩字号。

const clamp = (v, a, b) => Math.min(Math.max(v, a), b)

// ── 构件常量（任何画幅下都不许动）──
export const ENTRY_CAP = 32 // 正编收录的词目上限；版口按这个容量排，词目少了也不重排
export const ROW_H = 28 // .kd-row 行高
export const IDX_HEAD_H = 58 // 栏头 24 + 下留白 34
export const LENS_R = 84 // 取词镜半径（.kd-lens 168×168）
export const FOLIO_H = 16 // 页码行高
export const DEF_LH = 33.44 // 释义 19px × 1.76
export const CITE_LH = 29.52 // 书证 18px × 1.64
export const PREFACE_LH = 24.03 // 小序 13.5px × 1.78
export const FANLI_LH = 19.8 // 凡例 11px × 1.8
export const CITES_MIN_H = 216 // 三条两行书证所需（= 16:9 基线，只许更大）
export const CITE_GAP = 22 // .kd-cites 的行距
const CITE_SLOTS_MIN = 3 // 书证条数下限 = 16:9 基线
const CITE_SLOTS_MAX = 6

// ── 版口口径 ──
const PW_MAX = 580 // 版心最宽（16:9 基线；再宽一行字就散了）
const PW_MIN = 320
const MARGIN_MIN = 44 // 左右跨页的外白边下限
const MARGIN_MAX = 132
const GUTTER_MIN = 80 // 中缝下限
const GUTTER_BAND_MAX = 116 // 中缝阴影带最宽（16:9 基线）
const SIDE_UNDER_PW = 560 // 版心窄于此，词头的〔词类〕/字数从词右边挪到词下面
const COL_W_MIN = 168 // 一栏最窄：词目(≈7 汉字后省略) + 引点 + 例数，再窄这一栏就不成行了
const COL_GAP_MAX = 36
const COL_GAP_MIN = 24
const WORD_MAX_PAD = 72 // 词目省略阈值 = 栏宽 - 引点 - 例数（16:9: 272-72=200）
const CITE_MAX_PAD = 32 // 书证最大宽 = 版心 - 32（16:9: 548）

// ── 页面上下白边 ──
const TOP_RATIO = 0.0622 // 900 × 0.0622 = 56 = 16:9 的天头
const BOTTOM_RATIO = 0.0467 // 900 × 0.0467 = 42 = 16:9 的地脚
const TOP_MIN = 30
const TOP_MAX = 96
const BOTTOM_MIN = 12
const BOTTOM_MAX = 96

// 页脚三件套（书口线 → 参见/版权 → 页码）。左右两页共用同一套纵坐标，
// 16:9 的左右页正是这样对齐的：ruleD/ruleE 780、see/colophon 796、folio 842。
const CITES_TO_RULE = 16
const RULE_TO_FOOT = 16
const FOOT_TO_FOLIO = 46

// 词条页从上往下的固定间距：[名字, 16:9 基线, 压到最紧]。
// 矮页把余量从这里回收，字号行高一概不动。
const LEAF_GAPS = [
  ['rheadRuleA', 26, 16], // 页眉 → 首栏线
  ['ruleAHw', 50, 24], // 首栏线 → 词头
  ['hwMeta', 20, 14], // 词头 → 题解行
  ['metaRuleB', 32, 22], // 题解行 → 次栏线
  ['ruleBDef', 24, 18], // 次栏线 → 释义
  ['defSec', 16, 12], // 释义 → 「书证」小标
  ['secRuleC', 22, 16], // 小标 → 三栏线
  ['ruleCCites', 26, 18] // 三栏线 → 书证
]
const LEAF_GAP_BASE = LEAF_GAPS.reduce((a, g) => a + g[1], 0) // 216
const LEAF_GAP_MIN = LEAF_GAPS.reduce((a, g) => a + g[2], 0) // 160

const HW_H = 176 // 词头盒（16:9 基线）
const HW_H_MIN = 158
const HW_H_UNDER = 212 // 侧标改叠到词下面时要多留一行的位置
const HW_H_UNDER_MIN = 194

const DEF_4LINE_H = 1150 // 页高到这里，释义从 3 行放开到 4 行

// 索引页头部固定间距
const IDX_RHEAD_TO_RULE = 26
const IDX_TOP_TO_TITLE = 60
const IDX_TITLE_TO_PREFACE = 42
const IDX_PREFACE_TO_FANLI = 8
const IDX_FANLI_TO_IDX = 16
const IDX_TO_RULE = 20 // 索引末行 → 书口线的最小留白
const FANLI_ONE_LINE_PW = 480 // 版心窄于此，凡例整句会折成两行
const PREFACE_LINES_BASE = 2
const PREFACE_LINES_MAX = 4

// 经折装（上下叠页）
const STACK_GUTTER_H = 90 // 横向折痕带
const STACK_TOP = 30 // 上下两册页共用同一条页眉基线（--kd-t-rhead 是共享变量）
const STACK_BOTTOM = 12
const STACK_MARGIN_RATIO = 0.051 // 900 × 0.051 = 46
const STACK_MARGIN_MIN = 36
const STACK_MARGIN_MAX = 64
const STACK_MIN_ASPECT = 1.45 // 只有明确的竖长画幅才考虑经折装

const round = (n) => Math.round(n)

// ── 页脚：给定页高与地脚，反推书口线 / 参见行 / 页码 ──
function pageFoot (pageH, bottom) {
  const folio = pageH - bottom - FOLIO_H
  const foot = folio - FOOT_TO_FOLIO
  const rule = foot - RULE_TO_FOOT
  return { folio, foot, rule }
}

// ── 词条页 ──
// 版式是「头部按天头起排、页脚贴地、书证吃掉中间所有余量」。
// 书证是唯一有弹性的块：够不到 216（= 三条两行）时，依次从天头 / 词头盒 / 地脚 / 头部行距里回收。
function buildLeaf (pageH, pw, fixed) {
  const sideUnder = pw < SIDE_UNDER_PW
  const defLines = pageH >= DEF_4LINE_H ? 4 : 3
  const defH = round(defLines * DEF_LH)
  const gaps = LEAF_GAPS.map(([k, base, min]) => ({ k, v: base, min }))
  const hwMin = sideUnder ? HW_H_UNDER_MIN : HW_H_MIN

  let hHw = sideUnder ? HW_H_UNDER : HW_H
  let top = fixed && fixed.top != null ? fixed.top : clamp(round(pageH * TOP_RATIO), TOP_MIN, TOP_MAX)
  let bottom = fixed && fixed.bottom != null ? fixed.bottom : clamp(round(pageH * BOTTOM_RATIO), BOTTOM_MIN, BOTTOM_MAX)

  const gapSum = () => gaps.reduce((a, g) => a + g.v, 0)
  const citesTop = () => top + gapSum() + hHw + defH
  const citesH = () => pageFoot(pageH, bottom).rule - CITES_TO_RULE - citesTop()

  let need = CITES_MIN_H - citesH()
  if (need > 0) { const t = Math.min(need, top - TOP_MIN); top -= t; need -= t }
  if (need > 0) { const t = Math.min(need, hHw - hwMin); hHw -= t; need -= t }
  if (need > 0) { const t = Math.min(need, bottom - BOTTOM_MIN); bottom -= t; need -= t }
  for (const g of gaps) {
    if (need <= 0) break
    const t = Math.min(need, g.v - g.min)
    g.v -= t
    need -= t
  }

  const g = Object.fromEntries(gaps.map((x) => [x.k, x.v]))
  const tRhead = top
  const tRuleA = tRhead + g.rheadRuleA
  const tHw = tRuleA + g.ruleAHw
  const tMeta = tHw + hHw + g.hwMeta
  const tRuleB = tMeta + g.metaRuleB
  const tDef = tRuleB + g.ruleBDef
  const tSeclabel = tDef + defH + g.defSec
  const tRuleC = tSeclabel + g.secRuleC
  const tCites = tRuleC + g.ruleCCites
  const foot = pageFoot(pageH, bottom)
  const hCites = foot.rule - CITES_TO_RULE - tCites
  const citeLines = hCites >= 320 ? 3 : 2

  return {
    top,
    tRhead,
    tRuleA,
    tHw,
    hHw,
    tMeta,
    tRuleB,
    tDef,
    tSeclabel,
    tRuleC,
    tCites,
    hCites,
    tRuleD: foot.rule,
    tSee: foot.foot,
    tFolio: foot.folio,
    defLines,
    // 书证够高就把每条从 2 行放开到 3 行（3 条 × 3 行 + 行距 ≈ 310）
    citeLines,
    // 竖幅里书证区能装下更多条真话，就多引几条 —— 补白只能用真数据补，不许拉大字号。
    // 下限恒为 3：16:9 的三条书证（221 > max-height 216）一条都不许少。
    citeSlots: clamp(Math.floor((hCites + CITE_GAP) / (citeLines * CITE_LH + CITE_GAP)), CITE_SLOTS_MIN, CITE_SLOTS_MAX),
    sideUnder,
    fits: hCites >= CITES_MIN_H
  }
}

// 词条页的最小高度：所有可回收项都压到底、书证刚好 216 时的页高。
function leafMinHeight (pw) {
  const hwMin = pw < SIDE_UNDER_PW ? HW_H_UNDER_MIN : HW_H_MIN
  const defH = round(3 * DEF_LH)
  const belowCites = CITES_TO_RULE + RULE_TO_FOOT + FOOT_TO_FOLIO + FOLIO_H + BOTTOM_MIN
  return TOP_MIN + LEAF_GAP_MIN + hwMin + defH + CITES_MIN_H + belowCites
}

// ── 索引页头部：页眉 → 篇题 → 小序 → 凡例 → 索引顶 ──
function indexHead (top, pw, prefaceLines) {
  const fanliLines = pw >= FANLI_ONE_LINE_PW ? 1 : 2
  const tRuleAR = top + IDX_RHEAD_TO_RULE
  const tBookTitle = top + IDX_TOP_TO_TITLE
  const tPreface = tBookTitle + IDX_TITLE_TO_PREFACE
  const tFanli = round(tPreface + prefaceLines * PREFACE_LH + IDX_PREFACE_TO_FANLI)
  const tIdx = round(tFanli + fanliLines * FANLI_LH + IDX_FANLI_TO_IDX)
  return { tRuleAR, tBookTitle, tPreface, tFanli, tIdx, fanliLines }
}

// 栏宽 / 栏距：栏数确定后把版心整分。
function columnMetrics (pw, cols) {
  const colGap = clamp(round(pw * 0.062), COL_GAP_MIN, COL_GAP_MAX)
  const colW = Math.floor((pw - (cols - 1) * colGap) / cols)
  return { colGap, colW }
}

function maxColumns (pw) {
  const colGap = clamp(round(pw * 0.062), COL_GAP_MIN, COL_GAP_MAX)
  return Math.max(1, Math.floor((pw + colGap) / (COL_W_MIN + colGap)))
}

// ── 索引页（左右跨页：页高已知，自上而下排，页脚贴地）──
// 栏数取「ENTRY_CAP 条词目全部排得进可用高度」的最少栏数——这是缺陷的正解：
// 可容行数 = floor((可用高 - 栏头 58) / 28)，栏数 = ceil(32 / 可容行数)。
function buildIndexInPage (pageH, pw, cap, fixed) {
  const top = fixed && fixed.top != null ? fixed.top : clamp(round(pageH * TOP_RATIO), TOP_MIN, TOP_MAX)
  const bottom = fixed && fixed.bottom != null ? fixed.bottom : clamp(round(pageH * BOTTOM_RATIO), BOTTOM_MIN, BOTTOM_MAX)
  const foot = pageFoot(pageH, bottom)
  const capCols = maxColumns(pw)

  let prefaceLines = PREFACE_LINES_BASE
  let head = indexHead(top, pw, prefaceLines)
  let avail = foot.rule - IDX_TO_RULE - head.tIdx

  let cols = capCols
  for (let c = 1; c <= capCols; c += 1) {
    const rows = Math.ceil(cap / c)
    if (IDX_HEAD_H + rows * ROW_H <= avail) { cols = c; break }
  }
  let rows = Math.ceil(cap / cols)
  let idxH = IDX_HEAD_H + rows * ROW_H

  // 余量先回填给小序（每多一行 24px，最多 4 行），只用掉一半余量，剩下的留白
  const extra = clamp(Math.floor((avail - idxH) / (2 * PREFACE_LH)), 0, PREFACE_LINES_MAX - PREFACE_LINES_BASE)
  if (extra > 0) {
    prefaceLines += extra
    head = indexHead(top, pw, prefaceLines)
    avail = foot.rule - IDX_TO_RULE - head.tIdx
    rows = Math.ceil(cap / cols)
    idxH = IDX_HEAD_H + rows * ROW_H
  }

  // 还剩得下一整行的话，把索引块在版口里居中，别让页脚上方空一大片
  const slack = avail - idxH
  const shift = slack >= ROW_H ? Math.floor(slack / 2) : 0

  const { colGap, colW } = columnMetrics(pw, cols)
  return {
    top,
    prefaceLines,
    fanliLines: head.fanliLines,
    tRuleAR: head.tRuleAR,
    tBookTitle: head.tBookTitle,
    tPreface: head.tPreface,
    tFanli: head.tFanli,
    tIdx: head.tIdx + shift,
    tRuleE: foot.rule,
    tColophon: foot.foot,
    tFolioR: foot.folio,
    cols,
    rows,
    colGap,
    colW,
    avail,
    fits: idxH <= avail && colW >= COL_W_MIN
  }
}

// ── 索引页（经折装：页高由内容反推）──
function indexPageHeight (pw, cap, cols) {
  const rows = Math.ceil(cap / cols)
  const head = indexHead(STACK_TOP, pw, PREFACE_LINES_BASE)
  const below = IDX_TO_RULE + RULE_TO_FOOT + FOOT_TO_FOLIO + FOLIO_H + STACK_BOTTOM
  return head.tIdx + IDX_HEAD_H + rows * ROW_H + below
}

// ── 左右跨页的横向口径 ──
// 版心先取 580（16:9 基线）与「外白边/中缝压到下限时还能给的宽度」的较小者，
// 余量按 16:9 的口径（外白边 : 中缝 = 264 : 176）分。
// 这一条同时复现了 16:9 的 132/580/176 和 1:1 的 44/516/80。
function spreadHoriz (W) {
  const pw = Math.max(PW_MIN, Math.min(PW_MAX, Math.floor((W - 2 * MARGIN_MIN - GUTTER_MIN) / 2)))
  const slack = W - 2 * pw
  let m = clamp(round(slack * 0.3), MARGIN_MIN, MARGIN_MAX)
  if (slack - 2 * m < GUTTER_MIN) m = Math.max(MARGIN_MIN, Math.floor((slack - GUTTER_MIN) / 2))
  const g = slack - 2 * m
  return { pw, m, g }
}

function buildSpreadLayout (W, H, cap) {
  const { pw, m, g } = spreadHoriz(W)
  const leaf = buildLeaf(H, pw)
  const idx = buildIndexInPage(H, pw, cap, { top: leaf.top })
  const bandW = Math.min(g, GUTTER_BAND_MAX)
  const prX = W - m - pw

  return {
    mode: 'spread',
    canvasW: W,
    canvasH: H,
    pw,
    leafX: m,
    leafY: 0,
    leafH: H,
    prX,
    prY: 0,
    prH: H,
    gutterX: m + pw + Math.round((g - bandW) / 2),
    gutterY: 0,
    gutterW: bandW,
    gutterH: H,
    gutterLine: Math.round(bandW / 2),
    tRhead: leaf.tRhead,
    tRuleA: leaf.tRuleA,
    tHw: leaf.tHw,
    hHw: leaf.hHw,
    tMeta: leaf.tMeta,
    tRuleB: leaf.tRuleB,
    tDef: leaf.tDef,
    tSeclabel: leaf.tSeclabel,
    tRuleC: leaf.tRuleC,
    tCites: leaf.tCites,
    hCites: leaf.hCites,
    tRuleD: leaf.tRuleD,
    tSee: leaf.tSee,
    tFolio: leaf.tFolio,
    tRuleAR: idx.tRuleAR,
    tBookTitle: idx.tBookTitle,
    tPreface: idx.tPreface,
    tFanli: idx.tFanli,
    tIdx: idx.tIdx,
    tRuleE: idx.tRuleE,
    tColophon: idx.tColophon,
    tFolioR: idx.tFolioR,
    cols: idx.cols,
    colW: idx.colW,
    colGap: idx.colGap,
    headH: IDX_HEAD_H,
    rowH: ROW_H,
    idxLeft: prX,
    idxTop: idx.tIdx,
    lensR: LENS_R,
    lensAnchorX: 36,
    lensPadX: 30,
    lensPadY: 20,
    lensRows: idx.rows,
    headSideW: leaf.sideUnder ? 0 : 118,
    headGap: leaf.sideUnder ? 0 : 24,
    citeMaxW: pw - CITE_MAX_PAD,
    wordMaxW: idx.colW - WORD_MAX_PAD,
    defLines: leaf.defLines,
    citeLines: leaf.citeLines,
    citeSlots: leaf.citeSlots,
    prefaceLines: idx.prefaceLines,
    idxAvail: idx.avail,
    fits: leaf.fits && idx.fits
  }
}

// ── 经折装：上册页立词条，中缝转成横向折痕带，下册页排索引 ──
// 下册页高度由索引真正需要的高度反推，上册页拿走剩下的；
// 栏数取「上册页仍装得下三条两行书证」的最少栏数。都排不下就返回 null，交给左右跨页。
function buildStackLayout (W, H, cap) {
  const m = clamp(round(W * STACK_MARGIN_RATIO), STACK_MARGIN_MIN, STACK_MARGIN_MAX)
  const pw = W - 2 * m
  const minLeaf = leafMinHeight(pw)
  const capCols = maxColumns(pw)

  let cols = 0
  let prH = 0
  let leafH = 0
  for (let c = 1; c <= capCols; c += 1) {
    const need = indexPageHeight(pw, cap, c)
    const rest = H - STACK_GUTTER_H - need
    if (rest >= minLeaf) { cols = c; prH = need; leafH = rest; break }
  }
  if (!cols) return null

  const leaf = buildLeaf(leafH, pw, { top: STACK_TOP, bottom: STACK_BOTTOM })
  const idx = buildIndexInPage(prH, pw, cap, { top: STACK_TOP, bottom: STACK_BOTTOM })
  if (!leaf.fits || !idx.fits) return null

  return {
    mode: 'stack',
    canvasW: W,
    canvasH: H,
    pw,
    leafX: m,
    leafY: 0,
    leafH,
    prX: m,
    prY: leafH + STACK_GUTTER_H,
    prH,
    gutterX: 0,
    gutterY: leafH,
    gutterW: W,
    gutterH: STACK_GUTTER_H,
    gutterLine: Math.round(STACK_GUTTER_H / 2),
    tRhead: leaf.tRhead,
    tRuleA: leaf.tRuleA,
    tHw: leaf.tHw,
    hHw: leaf.hHw,
    tMeta: leaf.tMeta,
    tRuleB: leaf.tRuleB,
    tDef: leaf.tDef,
    tSeclabel: leaf.tSeclabel,
    tRuleC: leaf.tRuleC,
    tCites: leaf.tCites,
    hCites: leaf.hCites,
    tRuleD: leaf.tRuleD,
    tSee: leaf.tSee,
    tFolio: leaf.tFolio,
    tRuleAR: idx.tRuleAR,
    tBookTitle: idx.tBookTitle,
    tPreface: idx.tPreface,
    tFanli: idx.tFanli,
    tIdx: idx.tIdx,
    tRuleE: idx.tRuleE,
    tColophon: idx.tColophon,
    tFolioR: idx.tFolioR,
    cols: idx.cols,
    colW: idx.colW,
    colGap: idx.colGap,
    headH: IDX_HEAD_H,
    rowH: ROW_H,
    idxLeft: m,
    idxTop: leafH + STACK_GUTTER_H + idx.tIdx,
    lensR: LENS_R,
    lensAnchorX: 36,
    lensPadX: 30,
    lensPadY: 12,
    lensRows: idx.rows,
    headSideW: leaf.sideUnder ? 0 : 118,
    headGap: leaf.sideUnder ? 0 : 24,
    citeMaxW: pw - CITE_MAX_PAD,
    wordMaxW: idx.colW - WORD_MAX_PAD,
    defLines: leaf.defLines,
    citeLines: leaf.citeLines,
    citeSlots: leaf.citeSlots,
    prefaceLines: idx.prefaceLines,
    idxAvail: idx.avail,
    fits: leaf.fits && idx.fits
  }
}

/**
 * 由画布尺寸推出整套版式。
 * @param {number} canvasW 画布宽（= 舞台设计宽，16:9 恒为 1600）
 * @param {number} canvasH 画布高
 * @param {number} cap 正编容量（默认 ENTRY_CAP=32）。按容量而不是实际词目数排版，
 *                     词目少的用户看到的版式与满编时完全一致（也保住了 16:9 的零回归）。
 */
export function buildDictionaryLayout (canvasW, canvasH, cap = ENTRY_CAP) {
  const W = Math.max(PW_MIN, round(Number(canvasW) || 0) || 1600)
  const H = Math.max(PW_MIN, round(Number(canvasH) || 0) || 900)
  const n = Math.max(1, round(Number(cap) || ENTRY_CAP))

  // 竖长画幅优先试经折装（词头能占满整幅版心，字最大）；排不下就回到左右跨页。
  if (H / W >= STACK_MIN_ASPECT) {
    const stacked = buildStackLayout(W, H, n)
    if (stacked) return stacked
  }
  return buildSpreadLayout(W, H, n)
}

// 16:9 零回归基线：改动前写死在组件里的那套绝对定位，一个数都不许变。
// 只用于测试断言，运行时一律走 buildDictionaryLayout。
export const WIDE_BASELINE = Object.freeze({
  mode: 'spread',
  pw: 580,
  leafX: 132,
  leafY: 0,
  leafH: 900,
  prX: 888,
  prY: 0,
  prH: 900,
  gutterX: 742,
  gutterY: 0,
  gutterW: 116,
  gutterH: 900,
  gutterLine: 58,
  tRhead: 56,
  tRuleA: 82,
  tHw: 132,
  hHw: 176,
  tMeta: 328,
  tRuleB: 360,
  tDef: 384,
  tSeclabel: 500,
  tRuleC: 522,
  tCites: 548,
  hCites: 216,
  tRuleD: 780,
  tSee: 796,
  tFolio: 842,
  tRuleAR: 82,
  tBookTitle: 116,
  tPreface: 158,
  tFanli: 214,
  tIdx: 250,
  tRuleE: 780,
  tColophon: 796,
  tFolioR: 842,
  cols: 2,
  colW: 272,
  colGap: 36,
  headH: 58,
  rowH: 28,
  idxLeft: 888,
  idxTop: 250,
  lensR: 84,
  lensAnchorX: 36,
  lensPadX: 30,
  lensPadY: 20,
  lensRows: 16,
  headSideW: 118,
  headGap: 24,
  citeMaxW: 548,
  wordMaxW: 200
})
