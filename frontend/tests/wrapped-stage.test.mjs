import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DEFAULT_FRAME_ID,
  FRAME_PRESETS,
  STAGE_AREA,
  designSize,
  exportScale,
  findFrame,
  fitStage,
  frameTier,
  normalizeFrameId
} from '../lib/wrapped-stage.js'

test('画幅预设自洽：id 唯一、ratio 与 label 对得上、导出为长边 1080 基线', () => {
  const ids = FRAME_PRESETS.map((f) => f.id)
  assert.equal(new Set(ids).size, ids.length)
  assert.ok(ids.includes(DEFAULT_FRAME_ID))

  for (const f of FRAME_PRESETS) {
    if (f.id === 'fit') {
      assert.equal(f.ratio, 0)
      assert.equal(f.exportSize, null)
      continue
    }
    const [a, b] = f.id.split(':').map(Number)
    assert.ok(Math.abs(f.ratio - a / b) < 1e-9, `${f.id} ratio 与 id 不符`)

    const [ew, eh] = f.exportSize
    assert.ok(Math.abs(ew / eh - f.ratio) < 0.01, `${f.id} 导出像素与比例不符`)
    assert.equal(Math.max(ew, eh) >= 1080, true)
  }
})

test('normalizeFrameId：未知值回落，不抛错', () => {
  assert.equal(normalizeFrameId('9:16'), '9:16')
  assert.equal(normalizeFrameId(' 1:1 '), '1:1')
  assert.equal(normalizeFrameId('7:3'), DEFAULT_FRAME_ID)
  assert.equal(normalizeFrameId(null), DEFAULT_FRAME_ID)
  assert.equal(normalizeFrameId(undefined), DEFAULT_FRAME_ID)
  assert.equal(normalizeFrameId(123), DEFAULT_FRAME_ID)
  assert.equal(findFrame('nope'), null)
})

test('designSize：恒定面积、偶数边、比例误差 < 0.5%', () => {
  for (const f of FRAME_PRESETS) {
    if (f.id === 'fit') continue
    const { w, h } = designSize(f.ratio)
    assert.equal(w % 2, 0, `${f.id} 宽不是偶数`)
    assert.equal(h % 2, 0, `${f.id} 高不是偶数`)
    assert.ok(Math.abs(w / h - f.ratio) / f.ratio < 0.005, `${f.id} 比例漂移过大`)
    // 面积守恒（取整后允许 1% 误差）
    assert.ok(Math.abs(w * h - STAGE_AREA) / STAGE_AREA < 0.01, `${f.id} 面积不守恒`)
  }
})

test('designSize：16:9 精确等于 1600×900，9:16 精确等于 900×1600', () => {
  assert.deepEqual(designSize(16 / 9), { w: 1600, h: 900 })
  assert.deepEqual(designSize(9 / 16), { w: 900, h: 1600 })
  assert.deepEqual(designSize(1), { w: 1200, h: 1200 })
})

test('designSize：跟随窗口模式回落到 host 实测尺寸', () => {
  assert.deepEqual(designSize(0, 1280, 720), { w: 1280, h: 720 })
  assert.deepEqual(designSize(-1, 1280.4, 719.6), { w: 1280, h: 720 })
  // host 未知时也不能产出 0/NaN
  const d = designSize(0, 0, 0)
  assert.ok(d.w > 0 && d.h > 0)
})

test('frameTier：分档边界', () => {
  assert.equal(frameTier(16 / 9), 'wide')
  assert.equal(frameTier(1.5), 'wide')
  assert.equal(frameTier(4 / 3), 'landscape')
  assert.equal(frameTier(1), 'square')
  assert.equal(frameTier(4 / 5), 'portrait')
  assert.equal(frameTier(3 / 4), 'portrait')
  assert.equal(frameTier(9 / 16), 'tall')
  // 跟随窗口 = 桌面横屏基线
  assert.equal(frameTier(0), 'wide')
  assert.equal(frameTier(NaN), 'wide')
})

test('fitStage：等比贴合并居中', () => {
  const r = fitStage(1600, 900, 1600, 900, 1)
  assert.equal(r.scale, 1)
  assert.equal(r.left, 0)
  assert.equal(r.top, 0)

  // 宽窗口放竖幅：左右出信箱边，scale 由高度决定
  const t = fitStage(1920, 1000, 900, 1600, 1)
  assert.ok(Math.abs(t.scale - 1000 / 1600) < 1e-3)
  assert.ok(t.left > 0)
  assert.equal(t.top, 0)

  // 允许放大（大屏不留白）
  const up = fitStage(3200, 1800, 1600, 900, 1)
  assert.ok(up.scale >= 1.99)
})

test('fitStage：缩放吸附到设备像素边界，且永不溢出 host', () => {
  for (const dpr of [1, 2, 3]) {
    for (const [hw, hh] of [[1437, 803], [1280, 719], [901, 1601], [377, 812]]) {
      const { scale, left, top } = fitStage(hw, hh, 900, 1600, dpr)
      assert.ok(scale > 0)
      assert.ok(900 * scale <= hw + 0.001, 'scale 后超出 host 宽度')
      assert.ok(1600 * scale <= hh + 0.001, 'scale 后超出 host 高度')
      assert.ok(left >= 0 && top >= 0)
      // 吸附：scale * 设计宽 * dpr 落在整数上
      const px = scale * 900 * dpr
      assert.ok(Math.abs(px - Math.round(px)) < 1e-6, '未吸附到设备像素')
    }
  }
})

test('fitStage：非法输入不产生 NaN', () => {
  for (const args of [[0, 0, 900, 1600], [1280, 720, 0, 0], [NaN, 720, 900, 1600], [1280, NaN, 900, 1600]]) {
    const r = fitStage(...args)
    assert.equal(r.scale, 1)
    assert.equal(r.left, 0)
    assert.equal(r.top, 0)
    assert.ok(Number.isFinite(r.scale))
  }
})

test('exportScale：把设计尺寸抬到平台推荐像素', () => {
  const nine = findFrame('9:16')
  assert.ok(Math.abs(exportScale(nine, designSize(nine.ratio)) - 1080 / 900) < 1e-9)

  const square = findFrame('1:1')
  assert.ok(Math.abs(exportScale(square, designSize(square.ratio)) - 1080 / 1200) < 1e-9 || exportScale(square, designSize(square.ratio)) === 1)

  // 跟随窗口没有目标像素，兜底 2 倍
  assert.equal(exportScale(findFrame('fit'), { w: 1280, h: 720 }), 2)
  assert.equal(exportScale(null, null), 2)
})
