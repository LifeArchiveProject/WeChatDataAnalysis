<template>
  <div ref="rootEl" class="w-full" :class="{ 'wr-anim-paused': !isActive }">
    <div v-if="weeks > 0" class="hm-scroller" :class="{ 'hm-scroller--stacked': stacked }" data-wrapped-scroll-x>
      <div class="hm-body mx-auto" :class="stacked ? 'hm-body--stacked' : 'w-max'" :style="{ '--cell': `${cellPx}px` }">
        <!-- 竖幅下 1×53 的横条折成多段（段内仍是 7 行 × N 列）：横滚等于把 10–12 月推出视野 -->
        <div v-for="(seg, si) in segmentViews" :key="si" class="hm-seg">
          <!-- Month labels：悬停聚焦当月，点击钉住 -->
          <div
            class="grid gap-[2px] text-[11px] text-[#00000066] mb-2"
            :style="{ gridTemplateColumns: `36px repeat(${seg.cols}, var(--cell))` }"
          >
            <div></div>
            <span
              v-for="(m, idx) in seg.months"
              :key="idx"
              class="wrapped-number whitespace-nowrap"
              :class="m.text ? ['hm-month', { 'hm-month--active': activeMonth === m.month }] : ''"
              @mouseenter="m.text && (monthFocus = m.month)"
              @mouseleave="m.text && (monthFocus = -1)"
              @click="m.text && toggleMonthPin(m.month)"
            >
              {{ m.text }}
            </span>
          </div>

          <!-- Grid：支持鼠标按住拖选一段日期看统计（data-deck-nodrag 防止触屏拖动翻页） -->
          <div
            class="grid gap-[2px] items-stretch select-none"
            data-deck-nodrag
            :style="{
              gridTemplateColumns: `36px repeat(${seg.cols}, var(--cell))`,
              gridTemplateRows: `repeat(7, var(--cell))`
            }"
          >
            <div
              v-for="(w, wi) in weekdayTicks"
              :key="`wd-${wi}`"
              class="flex items-center wrapped-body text-[11px] text-[#00000066]"
              :style="{ gridColumn: '1', gridRow: String(wi + 1) }"
            >
              {{ w }}
            </div>

            <div
              v-for="(c, idx) in seg.cells"
              :key="`c-${idx}`"
              class="heatmap-cell rounded-[2px] transition-transform duration-150 hover:scale-125 hover:z-10"
              :class="cellClass(c)"
              :style="cellStyle(c, seg)"
              @mouseenter="onCellMouseEnter(c, $event)"
              @mousemove="scheduleTooltipLayout"
              @mouseleave="hideTooltip"
              @pointerdown="onCellPointerDown(c, $event)"
            ></div>
          </div>
        </div>

        <div class="mt-4 flex items-center justify-between gap-4 text-xs text-[#00000066] w-full">
          <div class="flex items-center gap-2">
            <span class="wrapped-body">低</span>
            <div class="flex items-center gap-[2px]">
              <span
                v-for="i in 6"
                :key="i"
                class="heatmap-legend-cell w-4 h-2 rounded-[2px] hm-legend"
                :class="{ 'hm-legend--active': legendFocus === i }"
                :style="{ backgroundColor: legendColor(i) }"
                @mouseenter="legendFocus = i"
                @mouseleave="legendFocus = 0"
              />
            </div>
            <span class="wrapped-body">高</span>
            <span class="wrapped-body text-[#00000040] hidden sm:inline hm-hint">在格子上拖动可圈选统计</span>
          </div>
          <div v-if="legendInfoText" class="wrapped-number hm-info" :class="{ 'hm-info--rich': !!selSummary || activeMonth >= 0 || legendFocus > 0 }">
            {{ legendInfoText }}
          </div>
        </div>
      </div>
    </div>

    <!-- tooltip 挂舞台 portal：舞台带 transform，fixed 后代以舞台为包含块，
         所以下面的 left/top 是**舞台坐标**，夹边也按舞台盒算。 -->
    <Teleport :to="stage.portalTarget.value">
      <Transition name="wr-tip">
        <div
          v-if="tooltipOpen && tooltipCell && tooltipCell.ymd"
          ref="tooltipEl"
          class="fixed z-[60] pointer-events-none"
          :style="{ left: `${tooltipX}px`, top: `${tooltipY}px` }"
          role="tooltip"
        >
          <div class="wr-heatmap-tooltip">
            <div class="flex justify-center mb-2">
              <span class="wr-heatmap-tooltip__time wrapped-number">{{ tooltipCell.ymd }}</span>
            </div>

            <div class="flex flex-col gap-2">
              <div class="flex justify-end">
                <div class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-[#95EC69] text-black bubble-tail-r">
                  <div class="wrapped-body">{{ tooltipPrimaryText }}</div>
                </div>
              </div>

              <div v-for="(line, i) in tooltipHighlightLines" :key="i" class="flex justify-start">
                <div class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-white text-gray-800 bubble-tail-l">
                  <div class="wrapped-body">{{ line }}</div>
                </div>
              </div>
            </div>

            <div
              class="wr-heatmap-tooltip__arrow"
              :class="tooltipPlacement === 'bottom' ? 'wr-heatmap-tooltip__arrow--top' : 'wr-heatmap-tooltip__arrow--bottom'"
              aria-hidden="true"
            ></div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { heatColor } from '~/lib/wrapped/heatmap'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useWrappedStage } from '~/composables/useWrappedStage'

const stage = useWrappedStage()

const props = defineProps({
  year: { type: Number, default: new Date().getFullYear() },
  // 0-indexed day-of-year array; length should be 365/366
  dailyCounts: { type: Array, default: () => [] },
  days: { type: Number, default: 0 },
  highlights: { type: Array, default: () => [] },
  // 卡片是否处于当前页：首次为 true 时播放入场动画，false 时暂停循环动画
  isActive: { type: Boolean, default: true },
  // 外部聚焦区间（{ start, end }，doy 0 起）：目录行悬停联动时其余格子变淡
  focusDoys: { type: Object, default: null }
})

// 格子边长。16:9 保持历史值 15px（为 Card00 的 slide 宽度手调过，逐像素零回归）；
// 竖幅/方幅下改成**按可用宽度撑满**——固定 15px 会让年历缩成中间一小条、两侧大片空白，
// 那正是「缩小适配」的反面教材。段数也一起按宽度选，让格子落在 20–30px 的舒适区。
const AXIS_W = 36   // 左侧周几刻度列
const GAP = 2       // 格间距
const CELL_MIN = 15
const CELL_MAX = 26

const availW = ref(0)

const MARKER_ORDER = [
  'sent_chars_max',
  'received_chars_max',
  'sent_messages_max',
  'received_messages_max',
  'added_friends_max',
  'sticker_messages_max',
  'emoji_chars_max'
]

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const isLeapYear = (y) => {
  const n = Number(y)
  if (!Number.isFinite(n)) return false
  return n % 4 === 0 && (n % 100 !== 0 || n % 400 === 0)
}

const daysInYear = computed(() => {
  const d = Number(props.days || 0)
  const arr = Array.isArray(props.dailyCounts) ? props.dailyCounts : []
  if (d > 0) return d
  if (arr.length > 0) return arr.length
  return isLeapYear(props.year) ? 366 : 365
})

const counts = computed(() => {
  const arr = Array.isArray(props.dailyCounts) ? props.dailyCounts : []
  const out = []
  for (let i = 0; i < daysInYear.value; i += 1) out.push(Number(arr[i] || 0))
  return out
})

const highlightsMap = computed(() => {
  const hs = Array.isArray(props.highlights) ? props.highlights : []
  const map = new Map()
  for (const raw of hs) {
    const key = typeof raw?.key === 'string' ? raw.key : ''
    const doyNum = Number(raw?.doy)
    if (!key || !Number.isFinite(doyNum)) continue
    const doy = Math.floor(doyNum)
    if (doy < 0 || doy >= daysInYear.value) continue

    const item = {
      key,
      label: typeof raw?.label === 'string' && raw.label.trim() ? raw.label.trim() : key,
      valueLabel: typeof raw?.valueLabel === 'string' ? raw.valueLabel : ''
    }

    const arr = map.get(doy) || []
    arr.push(item)
    map.set(doy, arr)
  }

  // Sort markers per-day by a stable order to keep UI deterministic.
  for (const [doy, arr] of map.entries()) {
    arr.sort((a, b) => {
      const ia = MARKER_ORDER.indexOf(a.key)
      const ib = MARKER_ORDER.indexOf(b.key)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
    map.set(doy, arr)
  }

  return map
})

const maxValue = computed(() => {
  let m = 0
  for (const v of counts.value) {
    const n = Number(v)
    if (Number.isFinite(n) && n > m) m = n
  }
  return m
})

const jan1UtcMs = computed(() => Date.UTC(Number(props.year), 0, 1))
const startWeekday = computed(() => {
  const d = new Date(jan1UtcMs.value)
  const w = d.getUTCDay() // 0=Sun..6=Sat
  return (w + 6) % 7 // 0=Mon..6=Sun
})

const weeks = computed(() => Math.ceil((daysInYear.value + startWeekday.value) / 7))

const weekdayTicks = computed(() => ['周一', '', '周三', '', '周五', '', '周日'])

const monthLabels = computed(() => {
  const cols = weeks.value
  const out = Array.from({ length: cols }, () => ({ text: '', month: -1 }))
  for (let m = 0; m < 12; m += 1) {
    const monthStart = Date.UTC(Number(props.year), m, 1)
    const doy = Math.round((monthStart - jan1UtcMs.value) / 86400000)
    const col = Math.floor((doy + startWeekday.value) / 7)
    if (col >= 0 && col < out.length && !out[col].text) out[col] = { text: `${m + 1}月`, month: m }
  }
  return out
})

const cells = computed(() => {
  const out = []
  const cols = weeks.value
  const leading = startWeekday.value
  const totalCells = cols * 7
  for (let i = 0; i < totalCells; i += 1) {
    const col = Math.floor(i / 7)
    const row = i % 7
    const doy = i - leading
    if (doy < 0 || doy >= daysInYear.value) {
      out.push({
        valid: false,
        row,
        col,
        count: 0,
        ymd: '',
        highlights: []
      })
      continue
    }

    const d = new Date(Date.UTC(Number(props.year), 0, 1 + doy))
    const y = d.getUTCFullYear()
    const mo = String(d.getUTCMonth() + 1).padStart(2, '0')
    const da = String(d.getUTCDate()).padStart(2, '0')
    const ymd = `${y}-${mo}-${da}`

    const highlights = highlightsMap.value.get(doy) || []
    const normalizedHighlights = Array.isArray(highlights) ? highlights : []

    out.push({
      valid: true,
      row,
      col,
      doy,
      ymd,
      mon: d.getUTCMonth(),
      count: Number(counts.value[doy] || 0),
      highlights: normalizedHighlights
    })
  }
  return out
})

// ---------------- 画幅分段：竖幅把 1×53 的横条折成多段 ----------------
//
// cells / monthLabels 的计算逻辑一律不动（doy ↔ col/row 的映射是全年唯一真相），
// 只在渲染层按 col 区间切片成 N 个子网格，段内列号 = 全局列号 − 段起始列。

// 单列纵向流的画幅：段落居中、图例吃满整行、不再靠横滚兜底
const stacked = computed(() => {
  const t = stage.tier.value
  return t === 'square' || t === 'portrait' || t === 'tall'
})

// 「把一行填满」的格子边长（不夹上下限）
const rawCellFor = (n) => {
  const w = availW.value
  const cols = Math.max(1, Math.ceil(weeks.value / Math.max(1, n)))
  if (!(w > 0)) return 0
  return Math.floor((w - AXIS_W - (cols - 1) * GAP) / cols)
}

// 段数取「格子还没小到看不清」的**最少**段数。
// ⚠️ 别反过来按目标格子大小去凑段数：段数越多 → 每段列越少 → 格子越大 → 但总高度也翻倍。
// 1:1 舞台 1112 宽时一行就能放下 53 列（格子 18px），分两段反而把年历撑到 484px 高、
// 把整张 Card00 顶出画幅（实测 FitScale 掉到 0.872，等于又在缩小适配）。
const segmentCount = computed(() => {
  if (!stacked.value) return 1
  const cols = weeks.value
  if (cols <= 0 || !(availW.value > 0)) return 1
  for (let n = 1; n <= 6; n += 1) if (rawCellFor(n) >= CELL_MIN) return n
  return 6
})

// 撑满宽度：段内列数定下来之后，格子边长就是填满这一行的那个值。
// ⚠️ 只在竖幅/方幅（stacked）生效。横屏（含全屏「跟随窗口」）保持 15px 常量：
// 那里版心是 max-w-5xl 定宽而窗口可以极宽，按「可用宽」撑会把 53 列算成 26px、
// 总宽 1518px 直接顶出版心，页面右侧整段被裁（全屏下实测把年历砍到只剩 11 个月）。
const cellPx = computed(() => {
  if (!stacked.value) return CELL_MIN
  const raw = rawCellFor(segmentCount.value)
  if (!raw) return CELL_MIN
  return Math.max(CELL_MIN, Math.min(CELL_MAX, raw))
})

const segments = computed(() => {
  const cols = weeks.value
  const n = Math.max(1, segmentCount.value)
  if (n <= 1 || cols <= 0) return [{ startCol: 0, cols: Math.max(0, cols) }]
  const per = Math.ceil(cols / n)
  const out = []
  for (let s = 0; s < n; s += 1) {
    const startCol = s * per
    if (startCol >= cols) break
    out.push({ startCol, cols: Math.min(per, cols - startCol) })
  }
  return out
})

const segmentViews = computed(() => {
  const all = cells.value
  const labels = monthLabels.value
  return segments.value.map((seg) => {
    const end = seg.startCol + seg.cols
    const segCells = all.filter((c) => c.col >= seg.startCol && c.col < end)
    const months = labels.slice(seg.startCol, end).map((m) => ({ ...m }))
    // 段从月中开起时首列没有月标：补上该段第一天所属月份（同月标已在段内则不补）
    if (months.length > 0 && !months[0].text) {
      const firstValid = segCells.find((c) => c.valid)
      const mo = firstValid ? Number(firstValid.mon) : -1
      if (mo >= 0 && !months.some((m) => m.month === mo)) {
        months[0] = { text: `${mo + 1}月`, month: mo }
      }
    }
    return { startCol: seg.startCol, cols: seg.cols, cells: segCells, months }
  })
})

const colorFor = (cell) => {
  if (!cell || !cell.valid) return 'transparent'
  return heatColor(cell.count, maxValue.value)
}

// ---------------- 入场动画（每次翻到本页都重播一遍） ----------------

const reducedMotion = useReducedMotion()
const entered = ref(false)
const entranceDone = ref(false)
let entranceTimer = 0

// 入场扫过 600ms + 单格动画 350ms。
const ENTRANCE_SWEEP_MS = 600
const ENTRANCE_CELL_MS = 350

// 离开后延迟复位（翻页动画结束后再复位，翻走过程中格子不消失），回来时重播。
const RESET_DELAY_MS = 750
let resetTimer = 0

watch(() => props.isActive, (active) => {
  if (typeof window === 'undefined') return
  if (entranceTimer) { window.clearTimeout(entranceTimer); entranceTimer = 0 }
  if (resetTimer) { window.clearTimeout(resetTimer); resetTimer = 0 }
  if (!active) {
    resetTimer = window.setTimeout(() => {
      resetTimer = 0
      entered.value = false
      entranceDone.value = false
    }, RESET_DELAY_MS)
    return
  }
  if (entered.value) return
  entered.value = true
  if (reducedMotion.value) {
    entranceDone.value = true
    return
  }
  entranceTimer = window.setTimeout(() => {
    entranceTimer = 0
    entranceDone.value = true
  }, ENTRANCE_SWEEP_MS + ENTRANCE_CELL_MS)
}, { immediate: true })

const entranceAnimating = computed(() => entered.value && !entranceDone.value && !reducedMotion.value)

const hasMarker = (cell) => !!(cell && cell.valid && Array.isArray(cell.highlights) && cell.highlights.length > 0)

// ---------------- 探索交互：月份聚焦 / 图例分档 / 拖选范围 / 外部联动 ----------------

const monthFocus = ref(-1) // 悬停中的月份（0-11）
const monthPinned = ref(-1) // 点击钉住的月份
const legendFocus = ref(0) // 悬停中的图例档位（1-6，0 = 无）
const selecting = ref(false)
const selStart = ref(-1)
const selEnd = ref(-1)

const activeMonth = computed(() => (monthFocus.value >= 0 ? monthFocus.value : monthPinned.value))

const toggleMonthPin = (m) => {
  if (m < 0) return
  monthPinned.value = monthPinned.value === m ? -1 : m
}

const monthTotals = computed(() => {
  const out = Array.from({ length: 12 }, () => 0)
  for (const c of cells.value) {
    if (c.valid && c.mon >= 0) out[c.mon] += c.count
  }
  return out
})

// 与 heatColor 的 sqrt 色阶一致的分档（0 = 无消息，1-6 与图例一一对应）
const bucketFor = (cell) => {
  const n = Number(cell?.count || 0)
  const m = maxValue.value
  if (n <= 0 || m <= 0) return 0
  return Math.min(6, Math.max(1, Math.ceil(Math.sqrt(n / m) * 6)))
}

const selRange = computed(() => {
  if (selStart.value < 0 || selEnd.value < 0) return null
  return { s: Math.min(selStart.value, selEnd.value), e: Math.max(selStart.value, selEnd.value) }
})

const externalFocus = computed(() => {
  const f = props.focusDoys
  if (!f) return null
  const s = Number(f.start)
  const e = Number(f.end)
  if (!Number.isFinite(s) || !Number.isFinite(e)) return null
  return { s: Math.min(s, e), e: Math.max(s, e) }
})

// 变淡优先级：拖选 > 外部联动 > 月份 > 图例分档
const isDimmed = (cell) => {
  if (!cell || !cell.valid) return false
  const sel = selRange.value
  if (sel) return cell.doy < sel.s || cell.doy > sel.e
  const ext = externalFocus.value
  if (ext) return cell.doy < ext.s || cell.doy > ext.e
  if (activeMonth.value >= 0) return cell.mon !== activeMonth.value
  if (legendFocus.value > 0) return bucketFor(cell) !== legendFocus.value
  return false
}

const isSelected = (cell) => {
  const sel = selRange.value
  return !!(sel && cell && cell.valid && cell.doy >= sel.s && cell.doy <= sel.e)
}

const doyLabel = (doy) => {
  const d = new Date(jan1UtcMs.value + doy * 86400000)
  return `${d.getUTCMonth() + 1}月${d.getUTCDate()}日`
}

// 拖选统计摘要（也用于右下角信息位）
const selSummary = computed(() => {
  const sel = selRange.value
  if (!sel) return ''
  const daysN = sel.e - sel.s + 1
  let total = 0
  for (let i = sel.s; i <= sel.e; i += 1) total += Number(counts.value[i] || 0)
  const avg = daysN > 0 ? total / daysN : 0
  const avgText = avg >= 100 ? String(Math.round(avg)) : avg.toFixed(1)
  return `${doyLabel(sel.s)} – ${doyLabel(sel.e)} · ${daysN} 天 · ${formatInt(total)} 条 · 日均 ${avgText}`
})

// 右下角信息位：拖选摘要 > 月份小计 > 图例档位天数 > 全年最大值
const legendInfoText = computed(() => {
  if (selSummary.value) return selSummary.value
  if (activeMonth.value >= 0) return `${activeMonth.value + 1}月 · ${formatInt(monthTotals.value[activeMonth.value] || 0)} 条`
  if (legendFocus.value > 0) {
    let n = 0
    for (const c of cells.value) {
      if (c.valid && bucketFor(c) === legendFocus.value) n += 1
    }
    return `该热度档 · ${n} 天`
  }
  return maxValue.value > 0 ? `最大 ${formatInt(maxValue.value)}` : ''
})

const cellClass = (cell) => ({
  'wr-cell-pre': !entered.value && !reducedMotion.value,
  'wr-cell-enter': entranceAnimating.value,
  'wr-cell-highlight': hasMarker(cell),
  'hm-dim': entranceDone.value || reducedMotion.value ? isDimmed(cell) : false,
  'hm-sel': isSelected(cell)
})

const cellStyle = (cell, seg) => {
  const startCol = Number(seg?.startCol) || 0
  const style = {
    backgroundColor: colorFor(cell),
    transformOrigin: originFor(cell, seg),
    gridColumn: String((cell.col ?? 0) - startCol + 2),
    gridRow: String((cell.row ?? 0) + 1)
  }
  if (entranceAnimating.value) {
    // 按周列从左到右波浪级联，全部列的 delay 落在 600ms 内。
    style.animationDelay = `${Math.round(((cell.col ?? 0) * ENTRANCE_SWEEP_MS) / Math.max(1, weeks.value))}ms`
  }
  return style
}

// ---------------- Tooltip ----------------

const tooltipOpen = ref(false)
const tooltipCell = ref(null)
const tooltipX = ref(0)
const tooltipY = ref(0)
const tooltipPlacement = ref('top') // 'top' | 'bottom'
const tooltipEl = ref(null)
const tooltipAnchorEl = ref(null)
let tooltipRaf = 0

const tooltipPrimaryText = computed(() => {
  const c = tooltipCell.value
  if (!c || !c.valid) return ''
  const n = Number(c.count) || 0
  if (n <= 0) return '这一天没有聊天消息'
  return `这一天有 ${n} 条聊天消息`
})

const tooltipHighlightLines = computed(() => {
  const c = tooltipCell.value
  if (!c || !c.valid) return []
  const hs = Array.isArray(c.highlights) ? c.highlights : []
  const out = []
  for (const h of hs) {
    if (!h) continue
    const label = String(h.label || h.key || '').trim()
    if (!label) continue
    const v = String(h.valueLabel || '').trim()
    out.push(v ? `${label}：${v}` : label)
  }
  return out
})

const updateTooltipLayout = () => {
  if (!import.meta.client) return
  const anchor = tooltipAnchorEl.value
  const tip = tooltipEl.value
  if (!anchor || !tip) return

  // getBoundingClientRect 是**缩放后**的屏幕矩形，而 tooltip 的 left/top 写进舞台坐标系，
  // 所以锚点与自身尺寸都要先换算回舞台单位，夹边也按舞台盒而不是浏览器窗口。
  const a = anchor.getBoundingClientRect()
  const t = tip.getBoundingClientRect()
  if (!t.width || !t.height) return

  const aTL = stage.toStagePoint(a.left, a.top)
  const aW = stage.toStageDelta(a.width)
  const aH = stage.toStageDelta(a.height)
  const tW = stage.toStageDelta(t.width)
  const tH = stage.toStageDelta(t.height)
  const vp = stage.viewportSize()

  const gap = 10
  const padding = 10

  let left = aTL.x + aW / 2 - tW / 2
  left = Math.min(vp.w - padding - tW, Math.max(padding, left))

  let top = aTL.y - gap - tH
  let placement = 'top'
  if (top < padding) {
    top = aTL.y + aH + gap
    placement = 'bottom'
  }

  if (top + tH > vp.h - padding) {
    top = vp.h - padding - tH
  }

  tooltipX.value = Math.round(left)
  tooltipY.value = Math.round(top)
  tooltipPlacement.value = placement
}

const scheduleTooltipLayout = () => {
  if (!import.meta.client) return
  if (!tooltipOpen.value) return
  if (tooltipRaf) cancelAnimationFrame(tooltipRaf)
  tooltipRaf = requestAnimationFrame(() => {
    tooltipRaf = 0
    updateTooltipLayout()
  })
}

const showTooltip = async (cell, e) => {
  if (!cell || !cell.valid || !cell.ymd) return
  tooltipCell.value = cell
  tooltipAnchorEl.value = e?.currentTarget || null
  tooltipOpen.value = true
  await nextTick()
  updateTooltipLayout()
}

const hideTooltip = () => {
  tooltipOpen.value = false
  tooltipCell.value = null
  tooltipAnchorEl.value = null
}

// 触屏没有 hover：点格子显示 tooltip，点空白关闭（见 document 级监听）。
let lastTouchTs = 0

const rootEl = ref(null)

const clearSelection = () => {
  selecting.value = false
  selStart.value = -1
  selEnd.value = -1
}

const onCellMouseEnter = (cell, e) => {
  // 拖选进行中：扩展选区，不弹 tooltip
  if (selecting.value) {
    if (cell && cell.valid) selEnd.value = cell.doy
    return
  }
  // 触屏 tap 会补发 mouseenter，避免与 pointerdown 分支互相打架。
  if (Date.now() - lastTouchTs < 700) return
  showTooltip(cell, e)
}

const onCellPointerDown = (cell, e) => {
  if (!e) return
  // 鼠标左键按下：开始拖选（松手时若没拖动则视为普通点击并清空）
  if (e.pointerType === 'mouse') {
    if (e.button !== 0 || !cell || !cell.valid) return
    selecting.value = true
    selStart.value = cell.doy
    selEnd.value = cell.doy
    hideTooltip()
    e.preventDefault()
    return
  }
  lastTouchTs = Date.now()
  if (tooltipOpen.value && tooltipCell.value === cell) {
    hideTooltip()
    return
  }
  showTooltip(cell, e)
}

const onWindowPointerUp = () => {
  if (!selecting.value) return
  selecting.value = false
  // 没有真正拖动 = 普通点击，不保留单日选区
  if (selStart.value === selEnd.value) clearSelection()
}

const onDocPointerDown = (e) => {
  if (!e) return
  const t = e.target
  const inRoot = t && typeof t.closest === 'function' && rootEl.value && rootEl.value.contains(t)
  // 鼠标点击热力图外：清除拖选选区
  if (e.pointerType === 'mouse') {
    if (selRange.value && !inRoot) clearSelection()
    return
  }
  if (!tooltipOpen.value) return
  if (t && typeof t.closest === 'function' && t.closest('.heatmap-cell')) return
  hideTooltip()
}

// 可用宽度：格子边长与段数都由它推。观察自身布局盒（不受祖先 transform 影响）。
let availRo = null
const measureAvail = () => {
  const el = rootEl.value
  if (!el) return
  const w = el.clientWidth
  if (w > 0 && Math.abs(w - availW.value) > 0.5) availW.value = w
}

onMounted(() => {
  if (!import.meta.client) return
  measureAvail()
  if (typeof ResizeObserver !== 'undefined' && rootEl.value) {
    availRo = new ResizeObserver(measureAvail)
    availRo.observe(rootEl.value)
  }
  window.addEventListener('resize', scheduleTooltipLayout)
  window.addEventListener('pointerup', onWindowPointerUp)
  document.addEventListener('pointerdown', onDocPointerDown, true)
})

onBeforeUnmount(() => {
  availRo?.disconnect()
  availRo = null
  if (!import.meta.client) return
  window.removeEventListener('resize', scheduleTooltipLayout)
  window.removeEventListener('pointerup', onWindowPointerUp)
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  if (tooltipRaf) cancelAnimationFrame(tooltipRaf)
  tooltipRaf = 0
  if (entranceTimer) {
    clearTimeout(entranceTimer)
    entranceTimer = 0
  }
  if (resetTimer) {
    clearTimeout(resetTimer)
    resetTimer = 0
  }
})

const legendColor = (i) => {
  const m = maxValue.value || 1
  const t = i / 6
  return heatColor(Math.max(1, t * m), m)
}

// hover 放大的锚点按**段内相对列**判断：分段后每段都有自己的左右边界
const originFor = (cell, seg) => {
  if (!cell) return 'center center'
  const startCol = Number(seg?.startCol) || 0
  const segCols = Number(seg?.cols) || weeks.value
  const col = Number(cell.col || 0) - startCol
  const row = Number(cell.row || 0)
  const x = col === 0 ? 'left' : (col === segCols - 1 ? 'right' : 'center')
  const y = row === 0 ? 'top' : (row === 6 ? 'bottom' : 'center')
  return `${x} ${y}`
}
</script>

<style scoped>
/* ---------------- 分段容器 ---------------- */

/* 16:9 / 4:3 保持原样：等价于原来的 .overflow-x-auto */
.hm-scroller {
  overflow-x: auto;
}

/* 竖幅：横滚会把 10–12 月推出视野 = 丢数据，这里必须失效 */
.hm-scroller--stacked {
  overflow-x: visible;
}

.hm-seg {
  width: max-content;
}

/* 单列纵向流：段落居中堆叠，图例吃满整行（横条时 w-max 会把「最大 N」挤出可视区） */
.hm-body--stacked {
  width: 100%;
}

.hm-body--stacked .hm-seg {
  margin-left: auto;
  margin-right: auto;
}

.hm-body--stacked .hm-seg + .hm-seg {
  margin-top: 14px;
}

/* 竖幅下信息位放开 nowrap：拖选摘要可能很长，宁可换行也不越界 */
.hm-body--stacked .hm-info {
  white-space: normal;
  text-align: right;
}

.wr-heatmap-tooltip {
  @apply relative w-[260px] max-w-[calc(var(--svw)*80)] rounded-2xl border border-[#00000010] bg-[#F5F5F5]/95 backdrop-blur px-3 py-3 shadow-xl;
}

.wr-heatmap-tooltip__time {
  @apply inline-flex items-center justify-center px-2 py-[2px] rounded-md border border-[#0000000a] bg-white/70 text-[10px] text-[#00000066];
}

.wr-heatmap-tooltip__arrow {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
}

.wr-heatmap-tooltip__arrow--bottom {
  bottom: -8px;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-top: 8px solid rgba(245, 245, 245, 0.95);
  filter: drop-shadow(0 1px 0 rgba(0, 0, 0, 0.06));
}

.wr-heatmap-tooltip__arrow--top {
  top: -8px;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-bottom: 8px solid rgba(245, 245, 245, 0.95);
  filter: drop-shadow(0 -1px 0 rgba(0, 0, 0, 0.06));
}

/* Tooltip 淡入 + 4px 上移 */
.wr-tip-enter-active,
.wr-tip-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.wr-tip-enter-from,
.wr-tip-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* 入场前隐藏，避免动画开始前闪现 */
.wr-cell-pre {
  opacity: 0;
}

.wr-cell-enter {
  animation: wr-cell-in 0.35s ease-out both;
}

@keyframes wr-cell-in {
  from {
    opacity: 0;
    transform: scale(0.6);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* ---------------- 探索交互样式 ---------------- */

/* 变淡（月份聚焦 / 图例分档 / 拖选 / 外部联动之外的格子） */
.heatmap-cell {
  transition-property: transform, opacity;
}

.hm-dim {
  opacity: 0.16;
}

/* 拖选选中：内描边细环 */
.hm-sel {
  box-shadow: inset 0 0 0 1.5px rgba(7, 193, 96, 0.85);
}

/* 峰值日格子被选中/变淡时仍保持可辨识 */
.wr-cell-highlight.hm-dim {
  opacity: 0.45;
}

.hm-month {
  cursor: pointer;
  border-radius: 4px;
  padding: 0 2px;
  margin: 0 -2px;
  transition: color 0.15s ease, background 0.15s ease;
}

.hm-month:hover {
  color: #07c160;
}

.hm-month--active {
  color: #07c160;
  font-weight: 600;
  background: rgba(7, 193, 96, 0.08);
}

.hm-legend {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.hm-legend--active {
  transform: scale(1.35);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12);
}

.hm-hint {
  margin-left: 10px;
}

.hm-info {
  white-space: nowrap;
  transition: color 0.15s ease;
}

.hm-info--rich {
  color: #07c160;
  font-weight: 600;
}

/* 峰值日标记：静态弥散金色光晕（多层模糊阴影，无动画、无描边框） */
.wr-cell-highlight {
  position: relative;
  z-index: 5;
  background-color: #f59e0b !important;
  box-shadow:
    0 0 4px 1px rgba(245, 158, 11, 0.65),
    0 0 12px 4px rgba(245, 158, 11, 0.45),
    0 0 26px 10px rgba(245, 158, 11, 0.22);
}

/* 卡片离屏时暂停本组件动画 */
.wr-anim-paused .heatmap-cell {
  animation-play-state: paused;
}

@media (prefers-reduced-motion: reduce) {
  .heatmap-cell,
  .heatmap-cell::after {
    animation: none !important;
    transition: none !important;
  }
}
</style>
