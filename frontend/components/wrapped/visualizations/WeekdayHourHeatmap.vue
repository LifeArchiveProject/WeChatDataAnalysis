<template>
  <div class="w-full">
    <div class="flex items-center justify-between gap-4">
      <div class="text-sm text-[#7F7F7F]">
        共 <span class="text-[#07C160] font-semibold">{{ totalMessages }}</span> 条消息
      </div>
      <div class="text-xs text-[#00000066]">24H × 7Days</div>
    </div>

    <div class="mt-4 overflow-x-auto" data-wrapped-scroll-x>
      <div class="min-w-[720px]">
        <div class="grid gap-[3px] [grid-template-columns:24px_1fr] text-[11px] text-[#00000066] mb-2">
          <div></div>
          <div class="grid gap-[3px] [grid-template-columns:repeat(24,minmax(0,1fr))]">
            <span
              v-for="(s, idx) in timeLabels"
              :key="idx"
              class="col-span-4 font-mono"
            >
              {{ s }}
            </span>
          </div>
        </div>

        <div class="grid gap-[3px] [grid-template-columns:24px_1fr] items-stretch">
          <div class="grid gap-[3px] [grid-template-rows:repeat(7,minmax(0,1fr))] text-[11px] text-[#00000066]">
            <div v-for="(w, wi) in weekdayLabels" :key="wi" class="flex items-center">
              {{ w }}
            </div>
          </div>

          <div class="grid gap-[3px] [grid-template-columns:repeat(24,minmax(0,1fr))]">
            <template v-for="(row, wi) in matrixSafe" :key="wi">
              <div
                v-for="(v, hi) in row"
                :key="`${wi}-${hi}`"
                class="aspect-square min-h-[10px] rounded-[2px] transition-transform duration-150 hover:scale-125 hover:z-10 relative"
                :style="{ backgroundColor: colorFor(v) }"
                :title="tooltipFor(wi, hi, v)"
              />
            </template>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 flex items-center justify-between text-xs text-[#00000066]">
      <div class="flex items-center gap-2">
        <span>低</span>
        <div class="flex items-center gap-[2px]">
          <span v-for="i in 6" :key="i" class="w-4 h-2 rounded-[2px]" :style="{ backgroundColor: legendColor(i) }"></span>
        </div>
        <span>高</span>
      </div>
      <div v-if="maxValue > 0">最大 {{ maxValue }}</div>
    </div>
  </div>
</template>

<script setup>
import { heatColor, maxInMatrix, formatHourRange } from '~/utils/wrapped/heatmap'

const props = defineProps({
  weekdayLabels: { type: Array, default: () => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'] },
  hourLabels: { type: Array, default: () => Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0')) },
  matrix: { type: Array, default: () => [] },
  totalMessages: { type: Number, default: 0 }
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

const tooltipFor = (weekdayIndex, hour, v) => {
  const w = props.weekdayLabels?.[weekdayIndex] ?? `周${weekdayIndex + 1}`
  const hr = formatHourRange(hour)
  const n = Number(v) || 0
  return `${w} ${hr}：${n} 条`
}

const legendColor = (i) => {
  const t = i / 6
  return heatColor(Math.max(1, t * (maxValue.value || 1)), maxValue.value || 1)
}
</script>
