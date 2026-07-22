<template>
  <div class="w-full">
    <div class="flex items-center justify-between gap-4">
      <div class="wrapped-body text-sm text-[#7F7F7F]">
        共 <span class="wrapped-number text-[#07C160] font-semibold">{{ totalDisplay }}</span> 条消息
      </div>
      <div class="wrapped-label text-xs text-[#00000066]">24H x 7Days</div>
    </div>

    <div class="mt-4 overflow-x-auto" data-wrapped-scroll-x>
      <!-- Keep original style, but slightly shrink the overall grid width (thus shrinking cells). -->
      <div class="min-w-[520px] max-w-[600px] mx-auto">
        <div class="grid gap-[3px] [grid-template-columns:24px_1fr] text-[11px] text-[#00000066] mb-2">
          <div></div>
          <div class="grid gap-[3px] [grid-template-columns:repeat(24,minmax(0,1fr))]">
            <span
              v-for="(s, idx) in timeLabels"
              :key="idx"
              class="col-span-4 wrapped-number"
            >
              {{ s }}
            </span>
          </div>
        </div>

        <div class="grid gap-[3px] [grid-template-columns:24px_1fr] items-stretch">
          <div class="grid gap-[3px] [grid-template-rows:repeat(7,minmax(0,1fr))] text-[11px] text-[#00000066]">
            <div v-for="(w, wi) in weekdayLabels" :key="wi" class="flex items-center wrapped-body">
              {{ w }}
            </div>
          </div>

          <div ref="gridEl" class="grid gap-[3px] [grid-template-columns:repeat(24,minmax(0,1fr))]">
            <template v-for="(row, wi) in matrixSafe" :key="wi">
              <div
                v-for="(v, hi) in row"
                :key="`${wi}-${hi}`"
                class="heatmap-cell aspect-square min-h-[10px] rounded-[2px] transition-transform duration-150 hover:scale-125 hover:z-10 relative"
                :class="cellStateClass"
                :style="{
                  backgroundColor: colorFor(v),
                  transformOrigin: originFor(wi, hi),
                  animationDelay: cellDelay(hi)
                }"
                @mouseenter="showTip(wi, hi, v, $event)"
                @mouseleave="hideTip"
                @click="toggleTip(wi, hi, v, $event)"
              />
            </template>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 flex items-center justify-between text-xs text-[#00000066]">
      <div class="flex items-center gap-2">
        <span class="wrapped-body">低</span>
        <div class="flex items-center gap-[2px]">
          <span v-for="i in 6" :key="i" class="heatmap-legend-cell w-4 h-2 rounded-[2px]" :style="{ backgroundColor: legendColor(i) }"></span>
        </div>
        <span class="wrapped-body">高</span>
      </div>
      <div v-if="maxValue > 0" class="wrapped-number">最大 {{ maxValue }}</div>
    </div>

    <!-- 三枚派生小徽章：热力图扫完后依次淡入 -->
    <div v-if="badges.length" class="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
      <div
        v-for="(b, i) in badges"
        :key="b.key"
        class="wr-hm-badge rounded-xl border border-[#EDEDED] bg-[#FAFAFA] px-3 py-2.5"
        :class="badgeStateClass"
        :style="{ animationDelay: badgeDelay(i) }"
      >
        <div class="wrapped-label text-[10px] text-[#00000066]">{{ b.label }}</div>
        <div class="wrapped-number text-base text-[#07C160] font-semibold mt-0.5">{{ b.value }}</div>
        <div class="wrapped-body text-[11px] text-[#7F7F7F] mt-0.5">{{ b.sub }}</div>
      </div>
    </div>

    <!-- 自绘轻量 tooltip（替代原生 title，支持触屏点按） -->
    <Teleport to="body">
      <div
        v-if="tipOpen && tipCell"
        ref="tipEl"
        class="fixed z-[60] pointer-events-none"
        :style="{ left: `${tipX}px`, top: `${tipY}px` }"
        role="tooltip"
      >
        <div class="wr-hm-tip">
          <div class="wr-hm-tip__time wrapped-number">{{ tipTitle }}</div>
          <div class="wr-hm-tip__body wrapped-body">{{ tipBody }}</div>
          <div
            class="wr-hm-tip__arrow"
            :class="tipPlacement === 'bottom' ? 'wr-hm-tip__arrow--top' : 'wr-hm-tip__arrow--bottom'"
            aria-hidden="true"
          ></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { heatColor, maxInMatrix, formatHourRange } from '~/lib/wrapped/heatmap'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useCountUp } from '~/composables/useCountUp'

const props = defineProps({
  weekdayLabels: { type: Array, default: () => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'] },
  hourLabels: { type: Array, default: () => Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0')) },
  matrix: { type: Array, default: () => [] },
  totalMessages: { type: Number, default: 0 },
  isActive: { type: Boolean, default: true }
})

const matrixSafe = computed(() => {
  // Expect 7x24, but keep defensive to avoid UI crashes.
  const m = Array.isArray(props.matrix) ? props.matrix : []
  const out = []
  for (let i = 0; i < 7; i++) {
    const row = Array.isArray(m[i]) ? m[i] : []
    const r = []
    for (let h = 0; h < 24; h++) r.push(Number(row[h] || 0))
    out.push(r)
  }
  return out
})

const maxValue = computed(() => maxInMatrix(matrixSafe.value))

const timeLabels = computed(() => {
  // Show every 4 hours to reduce clutter, inspired by EchoTrace.
  const labels = []
  for (let i = 0; i < 24; i += 4) labels.push(props.hourLabels[i] ?? String(i).padStart(2, '0'))
  return labels
})

const colorFor = (v) => heatColor(v, maxValue.value)

const legendColor = (i) => {
  const t = i / 6
  return heatColor(Math.max(1, t * (maxValue.value || 1)), maxValue.value || 1)
}

const originFor = (weekdayIndex, hour) => {
  // Avoid hover scaling pushing scrollWidth/scrollHeight and showing scrollbars:
  // keep the "outer" edges anchored on the first/last row/col.
  const x = hour === 0 ? 'left' : (hour === 23 ? 'right' : 'center')
  const y = weekdayIndex === 0 ? 'top' : (weekdayIndex === 6 ? 'bottom' : 'center')
  return `${x} ${y}`
}

// ---------- 入场动画：按小时列 0 -> 23 逐列点亮 ----------

const SWEEP_STEP_MS = 45 // 每列点亮间隔
const SWEEP_CELL_MS = 320 // 单元格点亮动画时长
const sweepEndMs = 23 * SWEEP_STEP_MS + SWEEP_CELL_MS

const reducedMotion = useReducedMotion()
const entered = ref(false)

const { display: totalDisplay, play: playTotal } = useCountUp(() => Number(props.totalMessages || 0), { duration: 1.4 })

// isActive 首次为 true 时触发入场（只播一次）；reduced-motion 由 useCountUp 内部与 CSS 类共同兜底。
watch(
  () => props.isActive,
  (active) => {
    if (!active || entered.value) return
    entered.value = true
    playTotal()
  },
  { immediate: true }
)

const cellStateClass = computed(() => {
  if (reducedMotion.value) return ''
  if (!entered.value) return 'wr-hm-cell--pending'
  return 'wr-hm-cell--sweep'
})

const cellDelay = (hour) => {
  if (reducedMotion.value || !entered.value) return '0ms'
  return `${hour * SWEEP_STEP_MS}ms`
}

const badgeStateClass = computed(() => {
  if (reducedMotion.value) return ''
  if (!entered.value) return 'wr-hm-badge--pending'
  return 'wr-hm-badge--in'
})

const badgeDelay = (i) => {
  if (reducedMotion.value || !entered.value) return '0ms'
  return `${sweepEndMs + i * 160}ms`
}

// ---------- 派生小徽章 ----------

const badges = computed(() => {
  const m = matrixSafe.value
  let total = 0
  const hourTotals = new Array(24).fill(0)
  let weekdaySum = 0
  let weekendSum = 0
  for (let w = 0; w < 7; w++) {
    for (let h = 0; h < 24; h++) {
      const v = m[w][h]
      total += v
      hourTotals[h] += v
      if (w >= 5) weekendSum += v
      else weekdaySum += v
    }
  }
  if (total <= 0) return []

  // 深夜指数：0-5 点消息占比
  let night = 0
  for (let h = 0; h < 6; h++) night += hourTotals[h]
  const nightPct = (night * 100) / total

  // 最安静的一小时（并列取更早的）
  let quietH = 0
  let quietV = Infinity
  for (let h = 0; h < 24; h++) {
    if (hourTotals[h] < quietV) {
      quietV = hourTotals[h]
      quietH = h
    }
  }

  // 工作日 vs 周末：按日均比较（工作日 5 天 / 周末 2 天）
  const weekdayAvg = weekdaySum / 5
  const weekendAvg = weekendSum / 2
  let ratioLabel = '—'
  if (weekendAvg > 0) ratioLabel = `${(weekdayAvg / weekendAvg).toFixed(1)} : 1`
  else if (weekdayAvg > 0) ratioLabel = '全在工作日'

  return [
    { key: 'night', label: '深夜指数', value: `${nightPct.toFixed(1)}%`, sub: '0-5 点消息占比' },
    { key: 'quiet', label: '最安静的一小时', value: formatHourRange(quietH), sub: `仅 ${quietV} 条` },
    { key: 'ratio', label: '工作日 vs 周末', value: ratioLabel, sub: '日均消息量之比' }
  ]
})

// ---------- 自绘 tooltip ----------

const gridEl = ref(null)
const tipEl = ref(null)
const tipOpen = ref(false)
const tipCell = ref(null) // { w, h, v }
const tipX = ref(0)
const tipY = ref(0)
const tipPlacement = ref('top') // 'top' | 'bottom'
const tipAnchorEl = ref(null)
let tipRaf = 0

const tipTitle = computed(() => {
  const c = tipCell.value
  if (!c) return ''
  const w = props.weekdayLabels?.[c.w] ?? `周${c.w + 1}`
  return `${w} ${formatHourRange(c.h)}`
})

const tipBody = computed(() => {
  const c = tipCell.value
  if (!c) return ''
  const n = Number(c.v) || 0
  return n > 0 ? `${n} 条消息` : '没有消息'
})

const updateTipLayout = () => {
  if (!import.meta.client) return
  const anchor = tipAnchorEl.value
  const tip = tipEl.value
  if (!anchor || !tip) return

  const a = anchor.getBoundingClientRect()
  const t = tip.getBoundingClientRect()
  if (!t.width || !t.height) return

  const gap = 8
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

  tipX.value = Math.round(left)
  tipY.value = Math.round(top)
  tipPlacement.value = placement
}

const scheduleTipLayout = () => {
  if (!import.meta.client) return
  if (!tipOpen.value) return
  if (tipRaf) cancelAnimationFrame(tipRaf)
  tipRaf = requestAnimationFrame(() => {
    tipRaf = 0
    updateTipLayout()
  })
}

const showTip = async (w, h, v, e) => {
  tipCell.value = { w, h, v }
  tipAnchorEl.value = e?.currentTarget || null
  tipOpen.value = true
  await nextTick()
  updateTipLayout()
}

const hideTip = () => {
  tipOpen.value = false
  tipCell.value = null
  tipAnchorEl.value = null
}

// 触屏点按：同格再点一次关闭，点其它格切换。
const toggleTip = (w, h, v, e) => {
  const c = tipCell.value
  if (tipOpen.value && c && c.w === w && c.h === h) {
    hideTip()
    return
  }
  showTip(w, h, v, e)
}

// 点击热力图以外的区域时收起 tooltip（触屏无 mouseleave）。
const onDocPointerDown = (e) => {
  if (!tipOpen.value) return
  const grid = gridEl.value
  if (grid && e?.target && grid.contains(e.target)) return
  hideTip()
}

onMounted(() => {
  if (!import.meta.client) return
  window.addEventListener('resize', scheduleTipLayout)
  document.addEventListener('pointerdown', onDocPointerDown)
})

onBeforeUnmount(() => {
  if (!import.meta.client) return
  window.removeEventListener('resize', scheduleTipLayout)
  document.removeEventListener('pointerdown', onDocPointerDown)
  if (tipRaf) cancelAnimationFrame(tipRaf)
  tipRaf = 0
})
</script>

<style scoped>
/* 入场前隐藏，扫到该列时点亮；fill-mode 用 backwards：
   动画结束后回到自然样式，避免 forwards 的 transform 压住 hover 缩放。 */
.wr-hm-cell--pending {
  opacity: 0;
}

.wr-hm-cell--sweep {
  animation: wr-hm-light-up 320ms ease-out backwards;
}

@keyframes wr-hm-light-up {
  from {
    opacity: 0;
    transform: scale(0.35);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.wr-hm-badge--pending {
  opacity: 0;
}

.wr-hm-badge--in {
  animation: wr-hm-badge-in 420ms ease-out backwards;
}

@keyframes wr-hm-badge-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.wr-hm-tip {
  position: relative;
  max-width: 220px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(245, 245, 245, 0.95);
  backdrop-filter: blur(6px);
  padding: 8px 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.wr-hm-tip__time {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.04);
  background: rgba(255, 255, 255, 0.7);
  font-size: 10px;
  color: rgba(0, 0, 0, 0.4);
}

.wr-hm-tip__body {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.85);
  white-space: nowrap;
}

.wr-hm-tip__arrow {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
}

.wr-hm-tip__arrow--bottom {
  bottom: -7px;
  border-left: 7px solid transparent;
  border-right: 7px solid transparent;
  border-top: 7px solid rgba(245, 245, 245, 0.95);
}

.wr-hm-tip__arrow--top {
  top: -7px;
  border-left: 7px solid transparent;
  border-right: 7px solid transparent;
  border-bottom: 7px solid rgba(245, 245, 245, 0.95);
}
</style>
