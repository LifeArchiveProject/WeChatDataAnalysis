<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
    <template #narrative>
      <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
        <p>
          <template v-if="totalMessages <= 0">
            今年你没有发出聊天消息
          </template>

          <template v-else-if="personality === 'early_bird'">
            清晨
            <span class="wrapped-number text-[#07C160] font-semibold">{{ pad2(mostActiveHour) }}</span>:00，
            当城市还在沉睡，你已经开始了新一天的问候。
            <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveWeekdayName }}</span>
            是你最健谈的一天，这一年你用
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
            条消息记录了这些早起时光。
          </template>

          <template v-else-if="personality === 'office_worker'">
            忙碌的上午
            <span class="wrapped-number text-[#07C160] font-semibold">{{ pad2(mostActiveHour) }}</span>:00，
            是你最常敲击键盘的时刻。
            <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveWeekdayName }}</span>
            最活跃，这一年你用
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
            条消息把工作与生活都留在了对话里。
          </template>

          <template v-else-if="personality === 'afternoon'">
            午后的阳光里，
            <span class="wrapped-number text-[#07C160] font-semibold">{{ pad2(mostActiveHour) }}</span>:00
            是你最爱分享的时刻。
            <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveWeekdayName }}</span>
            的聊天最热闹，这一年共
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
            条消息<span class="whitespace-nowrap">串起了</span>你的午后时光。
          </template>

          <template v-else-if="personality === 'night_owl'">
            夜幕降临，
            <span class="wrapped-number text-[#07C160] font-semibold">{{ pad2(mostActiveHour) }}</span>:00
            是你最常出没的时刻。
            <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveWeekdayName }}</span>
            最活跃，这一年
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
            条消息陪你把每个夜晚都聊得更亮。
          </template>

          <template v-else-if="personality === 'late_night'">
            当世界沉睡，凌晨
            <span class="wrapped-number text-[#07C160] font-semibold">{{ pad2(mostActiveHour) }}</span>:00
            的你依然在线。
            <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveWeekdayName }}</span>
            最活跃，这一年
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
            条深夜消息，是你与这个世界的悄悄话。
          </template>

          <template v-else>
            你在
            <span class="wrapped-number text-[#07C160] font-semibold">{{ pad2(mostActiveHour) }}</span>:00
            最活跃
          </template>
        </p>
      </div>
    </template>

    <WeekdayHourHeatmap
      :weekday-labels="card.data?.weekdayLabels"
      :hour-labels="card.data?.hourLabels"
      :matrix="card.data?.matrix"
      :total-messages="card.data?.totalMessages || 0"
    />
  </WrappedCardShell>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const _DEFAULT_WEEKDAYS_ZH = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const weekdayLabels = computed(() => {
  const labels = props.card?.data?.weekdayLabels
  if (Array.isArray(labels) && labels.length >= 7) return labels
  return _DEFAULT_WEEKDAYS_ZH
})

const matrix = computed(() => {
  const m = props.card?.data?.matrix
  return Array.isArray(m) ? m : null
})

const totalMessages = computed(() => Number(props.card?.data?.totalMessages || 0))

const mostActiveHour = computed(() => {
  if (!matrix.value || !Array.isArray(matrix.value) || matrix.value.length < 7) return null

  let bestH = 0
  let bestTotal = -1

  for (let h = 0; h < 24; h += 1) {
    let total = 0
    for (let w = 0; w < 7; w += 1) {
      const row = matrix.value[w]
      if (!Array.isArray(row) || row.length < 24) continue
      const v = Number(row[h] || 0)
      if (Number.isFinite(v)) total += v
    }
    // Tie-breaker: pick earliest hour.
    if (total > bestTotal || (total === bestTotal && h < bestH)) {
      bestTotal = total
      bestH = h
    }
  }

  return bestTotal >= 0 ? bestH : null
})

const mostActiveWeekdayIndex = computed(() => {
  if (!matrix.value || !Array.isArray(matrix.value) || matrix.value.length < 7) return null

  let bestW = 0
  let bestTotal = -1

  for (let w = 0; w < 7; w += 1) {
    const row = matrix.value[w]
    if (!Array.isArray(row) || row.length < 24) continue
    let total = 0
    for (let h = 0; h < 24; h += 1) {
      const v = Number(row[h] || 0)
      if (Number.isFinite(v)) total += v
    }
    // Tie-breaker: pick earliest weekday.
    if (total > bestTotal || (total === bestTotal && w < bestW)) {
      bestTotal = total
      bestW = w
    }
  }

  return bestTotal >= 0 ? bestW : null
})

const mostActiveWeekdayName = computed(() => {
  const idx = mostActiveWeekdayIndex.value
  if (idx === null) return ''
  return String(weekdayLabels.value[idx] || '')
})

const personality = computed(() => {
  const hour = mostActiveHour.value
  if (hour === null) return 'unknown'
  if (hour >= 5 && hour <= 8) return 'early_bird'
  if (hour >= 9 && hour <= 12) return 'office_worker'
  if (hour >= 13 && hour <= 17) return 'afternoon'
  if (hour >= 18 && hour <= 23) return 'night_owl'
  if (hour >= 0 && hour <= 4) return 'late_night'
  return 'unknown'
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const pad2 = (h) => String(Number(h ?? 0)).padStart(2, '0')
</script>
