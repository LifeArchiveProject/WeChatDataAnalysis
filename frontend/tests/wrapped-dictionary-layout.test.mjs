import assert from 'node:assert/strict'
import test from 'node:test'

import { FRAME_PRESETS, designSize, frameTier } from '../lib/wrapped-stage.js'
import {
  ENTRY_CAP,
  IDX_HEAD_H,
  LENS_R,
  ROW_H,
  WIDE_BASELINE,
  buildDictionaryLayout
} from '../lib/wrapped-dictionary-layout.js'

// 组件里的画布规则：wide（16:9 与「跟随窗口」）恒用 1600×900 常量，其余档位直接取该画幅的设计盒。
const canvasOf = (frame) => {
  const tier = frameTier(frame.ratio)
  if (tier === 'wide') return { w: 1600, h: 900, tier }
  const d = designSize(frame.ratio)
  return { w: d.w, h: d.h, tier }
}

const CANVASES = FRAME_PRESETS.map((f) => ({ id: f.id, ...canvasOf(f) }))

test('16:9 逐像素零回归：算出来的版式逐字段等于改动前写死的绝对定位', () => {
  const L = buildDictionaryLayout(1600, 900)
  for (const [k, v] of Object.entries(WIDE_BASELINE)) {
    assert.equal(L[k], v, `16:9 的 ${k} 变了：${L[k]} != ${v}`)
  }
  // 词目再少也不许重排（16:9 永远两栏，索引顶恒在 250）
  assert.equal(L.cols, 2)
  assert.equal(L.idxTop, 250)
  assert.equal(L.citeSlots, 3, '16:9 的书证恒为三条')
})

test('每一档画幅：32 条词目 + 凡例 + 版权行 + 页码全部落在画布内', () => {
  for (const c of CANVASES) {
    const L = buildDictionaryLayout(c.w, c.h)
    const where = `${c.id}(${c.tier}) ${c.w}×${c.h}`

    // ① 索引：可用高度装得下最深一栏
    const rowsFit = Math.floor((L.idxAvail - IDX_HEAD_H) / ROW_H)
    const rowsUsed = Math.ceil(ENTRY_CAP / L.cols)
    assert.equal(L.lensRows, rowsUsed, `${where} lensRows 与实际行数对不上`)
    assert.ok(rowsUsed <= rowsFit, `${where} 每栏 ${rowsUsed} 行 > 可容 ${rowsFit} 行`)
    assert.ok(L.cols * ENTRY_CAP >= ENTRY_CAP, `${where} 栏数不足以收下全部词目`)

    // ② 索引末行不许压过书口线，整块不许出画布
    const idxBottom = L.prY + L.tIdx + IDX_HEAD_H + rowsUsed * ROW_H
    assert.ok(idxBottom <= L.prY + L.tRuleE, `${where} 索引末行 ${idxBottom} 压过书口线`)
    assert.ok(idxBottom <= c.h, `${where} 索引末行 ${idxBottom} 掉出画布`)

    // ③ 凡例 / 版权行 / 两个页码整行可见
    assert.ok(L.prY + L.tFanli + 40 <= c.h, `${where} 凡例掉出画布`)
    assert.ok(L.prY + L.tColophon + 20 <= c.h, `${where} 版权行掉出画布`)
    assert.ok(L.prY + L.tFolioR + 16 <= c.h, `${where} 右页页码掉出画布`)
    assert.ok(L.leafY + L.tFolio + 16 <= c.h, `${where} 左页页码掉出画布`)

    // ④ 横向：两张册页与栏组都在版口内
    assert.ok(L.leafX + L.pw <= c.w, `${where} 词条页出界`)
    assert.ok(L.prX + L.pw <= c.w, `${where} 索引页出界`)
    assert.ok(L.cols * L.colW + (L.cols - 1) * L.colGap <= L.pw, `${where} 栏组比版心还宽`)

    // ⑤ 两张册页本身不许出画布
    assert.ok(L.leafY + L.leafH <= c.h, `${where} 词条页高出画布`)
    assert.ok(L.prY + L.prH <= c.h, `${where} 索引页高出画布`)
  }
})

test('构件常量在任何画幅下都不缩：行高 / 栏头 / 镜片直径 / 书证条数 / 截断行数', () => {
  for (const c of CANVASES) {
    const L = buildDictionaryLayout(c.w, c.h)
    const where = `${c.id} ${c.w}×${c.h}`
    assert.equal(L.rowH, ROW_H, `${where} 索引行高被改了`)
    assert.equal(L.headH, IDX_HEAD_H, `${where} 栏头高被改了`)
    assert.equal(L.lensR, LENS_R, `${where} 取词镜直径被改了`)
    assert.ok(L.hCites >= 216, `${where} 书证区 ${L.hCites} < 16:9 的 216`)
    assert.ok(L.citeSlots >= 3, `${where} 书证少于三条`)
    assert.ok(L.defLines >= 3, `${where} 释义少于三行`)
    assert.ok(L.citeLines >= 2, `${where} 书证每条少于两行`)
    assert.ok(L.prefaceLines >= 2, `${where} 小序少于两行`)
    // 词头可用宽度不得低于 16:9 的 438（否则长词条的字号会比 16:9 小）
    assert.ok(L.pw - L.headSideW - L.headGap >= 436, `${where} 词头可用宽 ${L.pw - L.headSideW - L.headGap} 比 16:9 窄`)
  }
})

test('取词镜的护栏在任何画幅下都不反向，且整圈留在画布内', () => {
  for (const c of CANVASES) {
    const L = buildDictionaryLayout(c.w, c.h)
    const where = `${c.id} ${c.w}×${c.h}`
    const xLo = Math.max(L.idxLeft + L.lensAnchorX - L.lensPadX, L.lensR + 8)
    const xHi = Math.min(L.idxLeft + (L.cols - 1) * (L.colW + L.colGap) + L.lensAnchorX + L.lensPadX, c.w - L.lensR - 8)
    const yLo = Math.max(L.idxTop + L.lensPadY, L.lensR + 8)
    const yHi = Math.min(L.idxTop + L.headH + L.lensRows * L.rowH + L.lensPadY, c.h - L.lensR - 8)
    assert.ok(xLo <= xHi, `${where} 镜片横向 clamp 反向`)
    assert.ok(yLo <= yHi, `${where} 镜片纵向 clamp 反向`)
    assert.ok(xLo - L.lensR >= 0 && xHi + L.lensR <= c.w, `${where} 镜圈横向出画布`)
    assert.ok(yLo - L.lensR >= 0 && yHi + L.lensR <= c.h, `${where} 镜圈纵向出画布`)
  }
})

test('3:4 / 4:5 排不下经折装就自动回到左右跨页，绝不留下裁掉的词条', () => {
  for (const [w, h] of [[1040, 1386], [1074, 1342]]) {
    const L = buildDictionaryLayout(w, h)
    assert.equal(L.mode, 'spread', `${w}×${h} 不该用经折装`)
    assert.equal(L.prY, 0)
    assert.equal(L.prH, h)
  }
  // 9:16 够高，经折装装得下，词头能占满整幅版心
  const tall = buildDictionaryLayout(900, 1600)
  assert.equal(tall.mode, 'stack')
  assert.equal(tall.cols, 3)
  assert.equal(tall.leafH + tall.gutterH + tall.prH, 1600)
})

// 舞台面积恒定（STAGE_AREA），所以「所有可能的画布」就是 designSize 在各宽高比上的取值。
// 从比 9:16 还竖扫到比 16:9 还宽，每一格都必须排得下。
test('任意宽高比的画布都排得下：0.40 → 2.50 逐格扫描', () => {
  for (let r = 0.4; r <= 2.5001; r += 0.01) {
    const { w, h } = designSize(r)
    const L = buildDictionaryLayout(w, h)
    const rowsUsed = Math.ceil(ENTRY_CAP / L.cols)
    const idxBottom = L.prY + L.tIdx + IDX_HEAD_H + rowsUsed * ROW_H
    const where = `ratio ${r.toFixed(2)} → ${w}×${h}`
    assert.ok(L.fits, `${where} 排不下`)
    assert.ok(idxBottom <= L.prY + L.tRuleE, `${where} 索引末行压过书口线`)
    assert.ok(idxBottom <= h, `${where} 索引末行掉出画布`)
    assert.ok(L.prY + L.tFolioR + 16 <= h, `${where} 页码掉出画布`)
    assert.ok(L.prY + L.tFanli + 40 <= h, `${where} 凡例掉出画布`)
    assert.ok(L.cols * L.colW + (L.cols - 1) * L.colGap <= L.pw, `${where} 栏组出界`)
    assert.ok(L.prX + L.pw <= w, `${where} 索引页横向出界`)
    assert.ok(L.hCites >= 216, `${where} 书证区被挤瘪`)
    assert.ok(L.colW >= 168, `${where} 栏宽 ${L.colW} 已经窄到排不成行`)
  }
})
