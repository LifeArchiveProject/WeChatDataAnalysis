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

          <!-- 最早最晚消息描述（按一天中的时刻） -->
          <template v-if="earliestSent && latestSent && totalMessages > 0">
            <template v-if="sameMomentTarget">
              最先想起的是「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」，
              最后放不下的也还是「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」。
            </template>
            <template v-else>
              <template v-if="sameMomentDate">
                在 {{ earliestDateLabel }}，最早的一条发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」，
                最晚的一条发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>」。
              </template>
              <template v-else-if="!hasMomentDates">
                最早的一条发给了
                <span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>，
                最晚的一条发给了
                <span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>。
              </template>
              <template v-else-if="momentVariant === 0">
                最早的一条（{{ earliestDateLabel }}）发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」，
                最晚的一条（{{ latestDateLabel }}）发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>」。
              </template>
              <template v-else-if="momentVariant === 1">
                最早的收件人是「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」（{{ earliestDateLabel }}），
                最晚的收件人是「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>」（{{ latestDateLabel }}）。
              </template>
              <template v-else-if="momentVariant === 2">
                在 {{ earliestDateLabel }}，你把消息发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」；
                在 {{ latestDateLabel }}，你又发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>」。
              </template>
              <template v-else-if="momentVariant === 3">
                最早与最晚，分别写给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」（{{ earliestDateLabel }}）
                和「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>」（{{ latestDateLabel }}）。
              </template>
              <template v-else>
                最早的一条落在 {{ earliestDateLabel }}，发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ earliestSent.displayName }}</span>」；
                最晚的一条落在 {{ latestDateLabel }}，发给了「<span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ latestSent.displayName }}</span>」。
              </template>
            </template>
          </template>
        </p>

        <!-- 今年第一条/最后一条消息（按日期时间戳） -->
        <p v-if="yearFirstSent && totalMessages > 0" class="mt-2">
          今年的第一条消息（<span class="wrapped-number text-[#07C160] font-semibold">{{ yearFirstDateLabel }} {{ yearFirstSent.time }}</span>）发给了
          <img
            v-if="yearFirstSent.avatarUrl"
            :src="yearFirstSent.avatarUrl"
            :alt="yearFirstSent.displayName"
            class="inline-block w-5 h-5 rounded align-middle mx-0.5 wrapped-privacy-avatar"
          /><span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ yearFirstSent.displayName }}</span>：「<span class="wrapped-privacy-message">{{ yearFirstSent.content || '...' }}</span>」<template v-if="yearLastSent">；
          最后一条消息（<span class="wrapped-number text-[#07C160] font-semibold">{{ yearLastDateLabel }} {{ yearLastSent.time }}</span>）发给了
          <img
            v-if="yearLastSent.avatarUrl"
            :src="yearLastSent.avatarUrl"
            :alt="yearLastSent.displayName"
            class="inline-block w-5 h-5 rounded align-middle mx-0.5 wrapped-privacy-avatar"
          /><span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ yearLastSent.displayName }}</span>：「<span class="wrapped-privacy-message">{{ yearLastSent.content || '...' }}</span>」</template>。
          <template v-if="sameYearTarget">
            <span class="text-[#7F7F7F]">——从年初到年末，始终如一。</span>
          </template>
        </p>
      </div>
    </template>

    <!-- 内容区域：上下布局 -->
    <div class="flex flex-col gap-4">
      <!-- 上部：两个聊天回放水平排列 -->
      <div v-if="earliestSent || latestSent" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <ChatReplayAnimation
          v-if="earliestSent"
          :time="earliestSent.time"
          :date="earliestSent.date"
          :display-name="earliestSent.displayName"
          :masked-name="earliestSent.maskedName"
          :avatar-url="earliestSent.avatarUrl"
          :content="earliestSent.content"
          label="最早的一条"
          :delay="0"
        />

        <ChatReplayAnimation
          v-if="latestSent"
          :time="latestSent.time"
          :date="latestSent.date"
          :display-name="latestSent.displayName"
          :masked-name="latestSent.maskedName"
          :avatar-url="latestSent.avatarUrl"
          :content="latestSent.content"
          label="最晚的一条"
          :delay="600"
        />
      </div>

      <!-- 下部：热力图全宽 -->
      <div class="w-full">
        <WeekdayHourHeatmap
          :weekday-labels="card.data?.weekdayLabels"
          :hour-labels="card.data?.hourLabels"
          :matrix="card.data?.matrix"
          :total-messages="card.data?.totalMessages || 0"
        />
      </div>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed } from 'vue'
import ChatReplayAnimation from '~/components/wrapped/visualizations/ChatReplayAnimation.vue'

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


const earliestSent = computed(() => {
  const o = props.card?.data?.earliestSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const latestSent = computed(() => {
  const o = props.card?.data?.latestSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const _formatDateLabel = (ymd) => {
  const s = String(ymd || '').trim()
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return s
  const mm = String(Number(m[2]))
  const dd = String(Number(m[3]))
  return `${mm}月${dd}日`
}

const earliestDateLabel = computed(() => _formatDateLabel(earliestSent.value?.date))
const latestDateLabel = computed(() => _formatDateLabel(latestSent.value?.date))
const hasMomentDates = computed(() => Boolean(earliestDateLabel.value && latestDateLabel.value))
const sameMomentDate = computed(() => hasMomentDates.value && earliestDateLabel.value === latestDateLabel.value)

const sameMomentTarget = computed(() => {
  const a = earliestSent.value
  const b = latestSent.value
  if (!a || !b) return false

  const ua = String(a.username || '').trim()
  const ub = String(b.username || '').trim()
  if (ua && ub) return ua === ub

  // Fallback: compare display names if username missing.
  const da = String(a.displayName || '').trim()
  const db = String(b.displayName || '').trim()
  return !!da && !!db && da === db
})

const momentVariant = computed(() => {
  const a = earliestSent.value
  const b = latestSent.value
  if (!a || !b) return 0

  const t0 = Number(a.timestamp || 0)
  const t1 = Number(b.timestamp || 0)
  const seed = (Number.isFinite(t0) ? t0 : 0) ^ (Number.isFinite(t1) ? t1 : 0) ^ 0x9e3779b9
  // 5 variants (0..4)
  return Math.abs(seed) % 5
})

// 今年第一条/最后一条消息（按日期时间戳排序）
const yearFirstSent = computed(() => {
  const o = props.card?.data?.yearFirstSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const yearLastSent = computed(() => {
  const o = props.card?.data?.yearLastSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const yearFirstDateLabel = computed(() => _formatDateLabel(yearFirstSent.value?.date))
const yearLastDateLabel = computed(() => _formatDateLabel(yearLastSent.value?.date))

const sameYearTarget = computed(() => {
  const a = yearFirstSent.value
  const b = yearLastSent.value
  if (!a || !b) return false

  const ua = String(a.username || '').trim()
  const ub = String(b.username || '').trim()
  if (ua && ub) return ua === ub

  // Fallback: compare display names if username missing.
  const da = String(a.displayName || '').trim()
  const db = String(b.displayName || '').trim()
  return !!da && !!db && da === db
})

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
