<template>
  <div class="w-full">
    <div class="flex items-center justify-between gap-4">
      <div class="wrapped-body text-sm text-[#7F7F7F]">
        共 <span class="wrapped-number text-[#07C160] font-semibold">{{ totalMessages }}</span> 条消息
      </div>
      <div class="wrapped-label text-xs text-[#00000066]">24H x 7Days</div>
    </div>

    <div class="mt-4 overflow-x-auto" data-wrapped-scroll-x>
      <div class="min-w-[720px]">
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

          <div class="grid gap-[3px] [grid-template-columns:repeat(24,minmax(0,1fr))]">
            <template v-for="(row, wi) in matrixSafe" :key="wi">
              <div
                v-for="(v, hi) in row"
                :key="`${wi}-${hi}`"
                class="heatmap-cell aspect-square min-h-[10px] rounded-[2px] transition-transform duration-150 hover:scale-125 hover:z-10 relative"
                :style="{ backgroundColor: colorFor(v), transformOrigin: originFor(wi, hi) }"
                :title="tooltipFor(wi, hi, v)"
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
  </div>
</template>

<script setup>
import { themedHeatColor, maxInMatrix, formatHourRange } from '~/utils/wrapped/heatmap'
import { useWrappedTheme } from '~/composables/useWrappedTheme'

const props = defineProps({
  weekdayLabels: { type: Array, default: () => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'] },
  hourLabels: { type: Array, default: () => Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0')) },
  matrix: { type: Array, default: () => [] },
  totalMessages: { type: Number, default: 0 }
})

const { theme } = useWrappedTheme()

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

const colorFor = (v) => themedHeatColor(v, maxValue.value, theme.value)

const tooltipFor = (weekdayIndex, hour, v) => {
  const w = props.weekdayLabels?.[weekdayIndex] ?? `周${weekdayIndex + 1}`
  const hr = formatHourRange(hour)
  const n = Number(v) || 0
  return `${w} ${hr}：${n} 条`
}

const legendColor = (i) => {
  const t = i / 6
  return themedHeatColor(Math.max(1, t * (maxValue.value || 1)), maxValue.value || 1, theme.value)
}

const originFor = (weekdayIndex, hour) => {
  // Avoid hover scaling pushing scrollWidth/scrollHeight and showing scrollbars:
  // keep the "outer" edges anchored on the first/last row/col.
  const x = hour === 0 ? 'left' : (hour === 23 ? 'right' : 'center')
  const y = weekdayIndex === 0 ? 'top' : (weekdayIndex === 6 ? 'bottom' : 'center')
  return `${x} ${y}`
}
</script>

<style>
/* ========== Game Boy 主题 ========== */

.wrapped-theme-gameboy .heatmap-cell {
  border-radius: 0 !important;
}

.wrapped-theme-gameboy .wrapped-label,
.wrapped-theme-gameboy .wrapped-body {
  color: #306230 !important;
}

.wrapped-theme-gameboy .wrapped-number {
  color: #0f380f !important;
}

.wrapped-theme-gameboy .heatmap-legend-cell {
  border-radius: 0 !important;
}

/* ========== DOS 主题 ========== */

.wrapped-theme-dos .heatmap-cell {
  border-radius: 0 !important;
  box-shadow: 0 0 2px rgba(51, 255, 51, 0.3);
}

.wrapped-theme-dos .wrapped-label,
.wrapped-theme-dos .wrapped-body {
  color: #22aa22 !important;
  text-shadow: 0 0 3px #22aa22;
}

.wrapped-theme-dos .wrapped-number {
  color: #33ff33 !important;
  text-shadow: 0 0 5px #33ff33;
}

.wrapped-theme-dos .heatmap-legend-cell {
  border-radius: 0 !important;
}

/* ========== VHS 主题 ========== */

.wrapped-theme-vhs .wrapped-label,
.wrapped-theme-vhs .wrapped-body {
  color: #a0a0a0 !important;
}

.wrapped-theme-vhs .wrapped-number {
  color: #e94560 !important;
  text-shadow:
    -1px 0 rgba(0, 255, 247, 0.5),
    1px 0 rgba(255, 0, 255, 0.5);
}
</style>
