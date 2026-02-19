<template>
  <div class="w-full">
    <div v-if="weeks > 0" class="overflow-x-auto" data-wrapped-scroll-x>
      <div class="w-max mx-auto" :style="{ '--cell': `${cellPx}px` }">
        <!-- Month labels -->
        <div
          class="grid gap-[2px] text-[11px] text-[#00000066] mb-2"
          :style="{ gridTemplateColumns: `36px repeat(${weeks}, var(--cell))` }"
        >
          <div></div>
          <span
            v-for="(m, idx) in monthLabels"
            :key="idx"
            class="wrapped-number whitespace-nowrap"
          >
            {{ m }}
          </span>
        </div>

        <!-- Grid -->
        <div
          class="grid gap-[2px] items-stretch"
          :style="{
            gridTemplateColumns: `36px repeat(${weeks}, var(--cell))`,
            gridTemplateRows: `repeat(7, var(--cell))`
          }"
        >
          <div
            v-for="(w, wi) in weekdayTicks"
            :key="wi"
            class="flex items-center wrapped-body text-[11px] text-[#00000066]"
            :style="{ gridColumn: '1', gridRow: String(wi + 1) }"
          >
            {{ w }}
          </div>

          <div
            v-for="(c, idx) in cells"
            :key="idx"
            class="heatmap-cell rounded-[2px] transition-transform duration-150 hover:scale-125 hover:z-10"
            :style="{
              backgroundColor: colorFor(c),
              transformOrigin: originFor(c),
              gridColumn: String((c.col ?? 0) + 2),
              gridRow: String((c.row ?? 0) + 1)
            }"
            @mouseenter="showTooltip(c, $event)"
            @mousemove="scheduleTooltipLayout"
            @mouseleave="hideTooltip"
          ></div>
        </div>

        <div class="mt-4 flex items-center justify-between text-xs text-[#00000066] w-full">
          <div class="flex items-center gap-2">
            <span class="wrapped-body">低</span>
            <div class="flex items-center gap-[2px]">
              <span
                v-for="i in 6"
                :key="i"
                class="heatmap-legend-cell w-4 h-2 rounded-[2px]"
                :style="{ backgroundColor: legendColor(i) }"
              />
            </div>
            <span class="wrapped-body">高</span>
          </div>
          <div v-if="maxValue > 0" class="wrapped-number">最大 {{ maxValue }}</div>
        </div>
      </div>
    </div>

    <Teleport to="body">
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
    </Teleport>
  </div>
</template>

<script setup>
import { heatColor } from '~/utils/wrapped/heatmap'

const props = defineProps({
  year: { type: Number, default: new Date().getFullYear() },
  // 0-indexed day-of-year array; length should be 365/366
  dailyCounts: { type: Array, default: () => [] },
  days: { type: Number, default: 0 },
  highlights: { type: Array, default: () => [] }
})

// Cell size of each day square (px). Tuned to fit Card00 slide width without truncation.
const cellPx = 15

const MARKER_ORDER = [
  'sent_chars_max',
  'received_chars_max',
  'sent_messages_max',
  'received_messages_max',
  'added_friends_max',
  'sticker_messages_max',
  'emoji_chars_max'
]

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
  const out = Array.from({ length: cols }, () => '')
  for (let m = 0; m < 12; m += 1) {
    const monthStart = Date.UTC(Number(props.year), m, 1)
    const doy = Math.round((monthStart - jan1UtcMs.value) / 86400000)
    const col = Math.floor((doy + startWeekday.value) / 7)
    if (col >= 0 && col < out.length && !out[col]) out[col] = `${m + 1}月`
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
      count: Number(counts.value[doy] || 0),
      highlights: normalizedHighlights
    })
  }
  return out
})

const colorFor = (cell) => {
  if (!cell || !cell.valid) return 'transparent'
  return heatColor(cell.count, maxValue.value)
}

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

  const a = anchor.getBoundingClientRect()
  const t = tip.getBoundingClientRect()
  if (!t.width || !t.height) return

  const gap = 10
  const padding = 10

  let left = a.left + a.width / 2 - t.width / 2
  left = Math.min(window.innerWidth - padding - t.width, Math.max(padding, left))

  let top = a.top - gap - t.height
  let placement = 'top'
  if (top < padding) {
    top = a.bottom + gap
    placement = 'bottom'
  }

  if (top + t.height > window.innerHeight - padding) {
    top = window.innerHeight - padding - t.height
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

onMounted(() => {
  if (!import.meta.client) return
  window.addEventListener('resize', scheduleTooltipLayout)
})

onBeforeUnmount(() => {
  if (!import.meta.client) return
  window.removeEventListener('resize', scheduleTooltipLayout)
  if (tooltipRaf) cancelAnimationFrame(tooltipRaf)
  tooltipRaf = 0
})

const legendColor = (i) => {
  const m = maxValue.value || 1
  const t = i / 6
  return heatColor(Math.max(1, t * m), m)
}

const originFor = (cell) => {
  if (!cell) return 'center center'
  const col = Number(cell.col || 0)
  const row = Number(cell.row || 0)
  const x = col === 0 ? 'left' : (col === weeks.value - 1 ? 'right' : 'center')
  const y = row === 0 ? 'top' : (row === 6 ? 'bottom' : 'center')
  return `${x} ${y}`
}
</script>

<style scoped>
.wr-heatmap-tooltip {
  @apply relative w-[260px] max-w-[80vw] rounded-2xl border border-[#00000010] bg-[#F5F5F5]/95 backdrop-blur px-3 py-3 shadow-xl;
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
</style>
