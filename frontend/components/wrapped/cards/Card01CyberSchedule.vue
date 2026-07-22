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
            v-if="yearFirstAvatarUrl"
            :src="yearFirstAvatarUrl"
            :alt="yearFirstSent.displayName"
            class="inline-block w-5 h-5 rounded align-middle mx-0.5 wrapped-privacy-avatar"
          /><span class="wrapped-number text-[#07C160] font-semibold wrapped-privacy-name">{{ yearFirstSent.displayName }}</span>：「<span class="wrapped-privacy-message">{{ yearFirstSent.content || '...' }}</span>」<template v-if="yearLastSent">；
          最后一条消息（<span class="wrapped-number text-[#07C160] font-semibold">{{ yearLastDateLabel }} {{ yearLastSent.time }}</span>）发给了
          <img
            v-if="yearLastAvatarUrl"
            :src="yearLastAvatarUrl"
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
          :avatar-url="resolveMediaUrl(earliestSent.avatarUrl)"
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
          :avatar-url="resolveMediaUrl(latestSent.avatarUrl)"
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
          :is-active="isActive"
        />
      </div>

      <!-- 深夜守夜人：夜空面板（无深夜单聊对象时整区隐藏） -->
      <div
        v-if="nightPartner"
        class="wr-night w-full"
        :class="{
          'wr-night--entered': nightEntered,
          'wr-night--paused': !isActive,
          'wr-night--reduced': reducedMotion
        }"
      >
        <span
          v-for="(st, i) in nightStars"
          :key="i"
          class="wr-night-star"
          :style="st"
          aria-hidden="true"
        ></span>

        <div class="relative z-10 flex items-start justify-between gap-4">
          <div class="min-w-0">
            <div class="wrapped-label text-[10px] text-[#9FB0DA]">NIGHT WATCH</div>
            <h3 class="wrapped-title text-lg text-white mt-1">深夜守夜人</h3>
            <p class="wrapped-body text-xs text-[#B9C4E4] mt-2 leading-relaxed">
              今年凌晨 0:00 - 5:59，你留下了
              <span class="wrapped-number text-[#FFE9A3] font-semibold">{{ formatInt(nightTotal) }}</span>
              条深夜单聊消息，其中
              <span class="wrapped-number text-[#FFE9A3] font-semibold">{{ formatInt(nightMine) }}</span>
              条由你发出。
            </p>
          </div>

          <!-- partner 头像置于“月亮”位置 -->
          <div class="wr-night-moon wrapped-privacy-avatar">
            <img
              v-if="nightPartnerAvatarUrl && nightAvatarOk"
              :src="nightPartnerAvatarUrl"
              :alt="nightPartner.displayName"
              @error="nightAvatarOk = false"
            />
            <span v-else class="wr-night-moon__fallback wrapped-number">{{ nightAvatarFallback }}</span>
          </div>
        </div>

        <p class="relative z-10 mt-4 wrapped-body text-sm text-[#E6EAF7]">
          陪你守夜最多的是「<span class="wrapped-number text-[#FFE9A3] font-semibold wrapped-privacy-name">{{ nightPartner.displayName }}</span>」，
          夜空被 TA 点亮了
          <span class="wrapped-number text-[#FFE9A3] font-semibold text-lg">{{ nightShareDisplay }}</span>%。
        </p>

        <!-- 最晚一刻：时钟时刻 + 气泡淡入 -->
        <div v-if="nightMoment" class="wr-night-moment relative z-10 mt-4 flex items-center gap-4">
          <div class="flex-shrink-0">
            <div class="wrapped-number text-2xl font-semibold text-white">{{ nightMoment.time }}</div>
            <div class="wrapped-label text-[10px] text-[#9FB0DA] mt-0.5">{{ nightMomentDateLabel }} · 最晚的一刻</div>
          </div>
          <div class="wr-night-bubble" :class="{ 'wr-night-bubble--sent': nightMoment.direction === 'sent' }">
            <div class="wrapped-label text-[10px] text-[#00000066] mb-1">
              {{ nightMoment.direction === 'sent' ? '你说' : 'TA 说' }}
            </div>
            <div class="wrapped-body text-sm wrapped-privacy-message">{{ nightMoment.content || '...' }}</div>
          </div>
        </div>
      </div>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import ChatReplayAnimation from '~/components/wrapped/visualizations/ChatReplayAnimation.vue'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useCountUp } from '~/composables/useCountUp'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  isActive: { type: Boolean, default: true } // deck 当前展示页时为 true
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

// ---------- 深夜守夜人 ----------

const reducedMotion = useReducedMotion()

const nightCompanion = computed(() => {
  const o = props.card?.data?.nightCompanion
  return o && typeof o === 'object' ? o : null
})

const nightPartner = computed(() => {
  const p = nightCompanion.value?.partner
  return p && typeof p === 'object' && typeof p.displayName === 'string' ? p : null
})

const nightMoment = computed(() => {
  const m = nightCompanion.value?.latestMoment
  return m && typeof m === 'object' && typeof m.time === 'string' ? m : null
})

const nightTotal = computed(() => Number(nightCompanion.value?.nightMessagesTotal || 0))
const nightMine = computed(() => Number(nightCompanion.value?.myNightMessages || 0))
const nightShare = computed(() => Number(nightPartner.value?.sharePct || 0))
const nightMomentDateLabel = computed(() => _formatDateLabel(nightMoment.value?.date))

const apiBase = useApiBase()
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    // qpic/qlogo 常有防盗链；与聊天页一致走后端代理。
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw.startsWith('/') ? raw : `/${raw}`
}

const nightPartnerAvatarUrl = computed(() => resolveMediaUrl(nightPartner.value?.avatarUrl))
const yearFirstAvatarUrl = computed(() => resolveMediaUrl(yearFirstSent.value?.avatarUrl))
const yearLastAvatarUrl = computed(() => resolveMediaUrl(yearLastSent.value?.avatarUrl))

const nightAvatarOk = ref(true)
const nightAvatarFallback = computed(() => {
  const s = String(nightPartner.value?.displayName || nightPartner.value?.maskedName || '').trim()
  return s ? s[0] : '?'
})

// 星点数量按深夜消息量分档；位置用 LCG 生成，保证同一数据下渲染稳定不跳动。
const nightStars = computed(() => {
  const total = nightTotal.value
  let count = 10
  if (total >= 1000) count = 42
  else if (total >= 300) count = 30
  else if (total >= 100) count = 22
  else if (total >= 20) count = 14

  let seed = ((total + 7) * 2654435761) % 2147483647
  if (seed <= 0) seed = 12345
  const rand = () => {
    seed = (seed * 48271) % 2147483647
    return seed / 2147483647
  }

  const stars = []
  for (let i = 0; i < count; i += 1) {
    const size = 1.5 + rand() * 2
    stars.push({
      left: `${(rand() * 96 + 2).toFixed(2)}%`,
      top: `${(rand() * 72 + 3).toFixed(2)}%`,
      width: `${size.toFixed(1)}px`,
      height: `${size.toFixed(1)}px`,
      animationDelay: `${(rand() * 2.4).toFixed(2)}s`,
      animationDuration: `${(2 + rand() * 2).toFixed(2)}s`
    })
  }
  return stars
})

const { display: nightShareDisplay, play: playNightShare } = useCountUp(
  () => nightShare.value,
  { duration: 1.6, delay: 0.4, decimals: 1 }
)

// isActive 首次为 true 时触发入场（只播一次）。
const nightEntered = ref(false)
watch(
  () => props.isActive,
  (active) => {
    if (!active || nightEntered.value) return
    nightEntered.value = true
    playNightShare()
  },
  { immediate: true }
)
</script>

<style scoped>
.wr-night {
  position: relative;
  overflow: hidden;
  border-radius: 16px;
  padding: 20px;
  background: linear-gradient(165deg, #0A1030 0%, #16224A 55%, #23345F 100%);
}

.wr-night-star {
  position: absolute;
  border-radius: 9999px;
  background: #ffffff;
  opacity: 0.25;
  animation: wr-night-twinkle 2.8s ease-in-out infinite;
}

@keyframes wr-night-twinkle {
  0%,
  100% {
    opacity: 0.2;
    transform: scale(0.8);
  }
  50% {
    opacity: 0.95;
    transform: scale(1.2);
  }
}

/* 离屏时暂停循环动画；reduced-motion 直接关闭 */
.wr-night--paused .wr-night-star {
  animation-play-state: paused;
}

.wr-night--reduced .wr-night-star {
  animation: none;
  opacity: 0.55;
}

.wr-night-moon {
  position: relative;
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  border-radius: 9999px;
  overflow: hidden;
  background: #ffe9a3;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 0 22px 6px rgba(255, 233, 163, 0.4),
    0 0 60px 14px rgba(255, 233, 163, 0.15);
}

.wr-night-moon img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.wr-night-moon__fallback {
  font-size: 18px;
  color: rgba(0, 0, 0, 0.55);
}

/* 最晚一刻整块淡入：入场（wr-night--entered）后延迟出现 */
.wr-night-moment {
  opacity: 0;
  transform: translateY(8px);
  transition:
    opacity 600ms ease 900ms,
    transform 600ms ease 900ms;
}

.wr-night--entered .wr-night-moment {
  opacity: 1;
  transform: none;
}

.wr-night--reduced .wr-night-moment {
  transition: none;
}

.wr-night-bubble {
  position: relative;
  min-width: 0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  color: #1a1a1a;
  padding: 8px 12px;
  word-break: break-word;
}

.wr-night-bubble--sent {
  background: #95ec69;
}
</style>
