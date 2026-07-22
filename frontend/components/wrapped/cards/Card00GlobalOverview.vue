<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
    <template #narrative>
      <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
        <p>
          <template v-if="totalMessages > 0">
            这一年，你在微信里发送了
            <span class="wrapped-number text-[#07C160] font-semibold">{{ totalDisplay }}</span>
            条消息，平均每天
            <span class="wrapped-number text-[#07C160] font-semibold">{{ perDayDisplay }}</span>
            条。
          </template>
          <template v-else>
            这一年，你在微信里还没有发出聊天消息——也许，你把时间留给了更重要的人和事。
          </template>

          <template v-if="activeDays > 0">
            在与你相伴的
            <span class="wrapped-number text-[#07C160] font-semibold">{{ activeDaysDisplay }}</span>
            天里，
            <template v-if="addedFriends > 0">
              你总共加了
              <span class="wrapped-number text-[#07C160] font-semibold">{{ addedFriendsDisplay }}</span>
              位好友，
            </template>
            <template v-if="mostActiveHour !== null && mostActiveWeekdayName">
              你最常在 {{ mostActiveWeekdayName }} 的
              <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveHour }}</span>
              点出现。
            </template>
            <template v-else>
              你留下了不少对话的痕迹。
            </template>
          </template>

          <template v-if="topContact || topGroup">
            <template v-if="topContact">
              你发消息最多的人是
              「<span class="inline-flex items-center gap-2 align-bottom max-w-[12rem]" :title="topContact.displayName">
                <span class="w-6 h-6 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                  <img
                    v-if="topContactAvatarUrl && avatarOk.topContact"
                    :src="topContactAvatarUrl"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk.topContact = false"
                  />
                  <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                    {{ avatarFallback(topContact.displayName) }}
                  </span>
                </span>
                <span class="wrapped-privacy-name inline-block max-w-[10rem] truncate align-bottom">{{ topContact.displayName }}</span>
              </span>」
              （<span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(topContact.messages) }}</span> 条）
            </template>
            <template v-if="topContact && topGroup">，</template>
            <template v-if="topGroup">
              你最常发言的群是
              「<span class="inline-flex items-center gap-2 align-bottom max-w-[12rem]" :title="topGroup.displayName">
                <span class="w-6 h-6 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                  <img
                    v-if="topGroupAvatarUrl && avatarOk.topGroup"
                    :src="topGroupAvatarUrl"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk.topGroup = false"
                  />
                  <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                    {{ avatarFallback(topGroup.displayName) }}
                  </span>
                </span>
                <span class="wrapped-privacy-name inline-block max-w-[10rem] truncate align-bottom">{{ topGroup.displayName }}</span>
              </span>」
              （<span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(topGroup.messages) }}</span> 条）
            </template>
            。
          </template>

          <template v-if="topKind && topKindPct > 0">
            你更常用 {{ topKind.label }} 来表达（<span class="wrapped-number text-[#07C160] font-semibold">{{ topKindPct }}</span>%）。
          </template>

          <template v-if="topPhrase && topPhrase.phrase && topPhrase.count > 0">
            你说得最多的一句话是「<span class="inline-block max-w-[12rem] truncate align-bottom" :title="topPhrase.phrase">{{ topPhrase.phrase }}</span>」（<span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(topPhrase.count) }}</span> 次）。
          </template>

          <span class="hidden sm:inline text-[#00000055]">愿你的每一句分享，都有人回应。</span>
        </p>

        <!-- 发出的图片/视频、表情包小图标统计行 -->
        <div
          v-if="sentMediaCount > 0 || sentStickerCount > 0"
          class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-[#00000066]"
          :class="fxClass(0)"
        >
          <span v-if="sentMediaCount > 0" class="inline-flex items-center gap-1.5">
            <svg class="w-4 h-4 text-[#07C160]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
            发出图片/视频
            <span class="wrapped-number text-[#07C160] font-semibold">{{ mediaDisplay }}</span>
            条
          </span>
          <span v-if="sentStickerCount > 0" class="inline-flex items-center gap-1.5">
            <svg class="w-4 h-4 text-[#07C160]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <path d="M8 14s1.5 2 4 2 4-2 4-2" />
              <line x1="9" y1="9" x2="9.01" y2="9" />
              <line x1="15" y1="9" x2="15.01" y2="9" />
            </svg>
            发出表情包
            <span class="wrapped-number text-[#07C160] font-semibold">{{ stickerDisplay }}</span>
            条
          </span>
        </div>
      </div>
    </template>

    <div :class="variant === 'slide' ? 'w-full -mt-2 sm:-mt-4' : 'w-full'">
      <!-- 年度峰值日 -->
      <div
        v-if="peakDay"
        class="mb-4 rounded-2xl border border-[#EDEDED] bg-white/70 px-4 py-3"
        :class="fxClass(1)"
      >
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 wrapped-body text-sm text-[#7F7F7F]">
          <span class="inline-flex items-center gap-1 text-[#F59E0B] font-semibold">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M13.5 2s.5 2.5-1 4.5S9 9 9 11a3 3 0 0 0 6 .5c1.5 1 2.5 2.5 2.5 4.5a5.5 5.5 0 0 1-11 0c0-3 1.5-4.5 2-7C9 6.5 8.5 5 8.5 5S14 4.5 13.5 2Z" />
            </svg>
            年度峰值日
          </span>
          <span class="wrapped-number text-[#000000e6] font-semibold">{{ peakDay.date }}</span>
          <span v-if="peakDay.weekdayName">{{ peakDay.weekdayName }}</span>
          <span>
            发出
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(peakDay.count) }}</span>
            条消息<template v-if="peakMultipleText">，是日均的
            <span class="wrapped-number text-[#07C160] font-semibold">{{ peakMultipleText }}</span>
            倍</template>。
          </span>
          <span v-if="peakTopContact" class="inline-flex items-center gap-2" :title="peakTopContact.displayName">
            当日主角
            <span class="w-6 h-6 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
              <img
                v-if="peakContactAvatarUrl && avatarOk.peakContact"
                :src="peakContactAvatarUrl"
                class="w-full h-full object-cover"
                alt="avatar"
                @error="avatarOk.peakContact = false"
              />
              <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                {{ avatarFallback(peakTopContact.displayName) }}
              </span>
            </span>
            <span class="wrapped-privacy-name inline-block max-w-[10rem] truncate align-bottom">{{ peakTopContact.displayName }}</span>
            <span>（<span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(peakTopContact.messages) }}</span> 条）</span>
          </span>
        </div>

        <div
          v-if="peakDay.firstText || peakDay.lastText"
          class="mt-2 flex flex-col gap-1 wrapped-body text-xs text-[#00000066]"
        >
          <div v-if="peakDay.firstText" class="flex items-baseline gap-2 min-w-0">
            <span class="flex-shrink-0">
              首句<template v-if="peakDay.firstTime">
                <span class="wrapped-number ml-1">{{ peakDay.firstTime }}</span>
              </template>
            </span>
            <span class="wrapped-privacy-message truncate" :title="peakDay.firstText">{{ peakDay.firstText }}</span>
          </div>
          <div v-if="peakDay.lastText" class="flex items-baseline gap-2 min-w-0">
            <span class="flex-shrink-0">
              末句<template v-if="peakDay.lastTime">
                <span class="wrapped-number ml-1">{{ peakDay.lastTime }}</span>
              </template>
            </span>
            <span class="wrapped-privacy-message truncate" :title="peakDay.lastText">{{ peakDay.lastText }}</span>
          </div>
        </div>
      </div>

      <GlobalOverviewChart :data="card.data || {}" :is-active="isActive" />
    </div>
  </WrappedCardShell>
</template>

<script setup>
import GlobalOverviewChart from '~/components/wrapped/visualizations/GlobalOverviewChart.vue'
import { useCountUp } from '~/composables/useCountUp'
import { useReducedMotion } from '~/composables/useReducedMotion'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  // 卡片是否处于当前页：首次为 true 时播放入场动画（只播一次）
  isActive: { type: Boolean, default: true }
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const formatFloat = (n, digits = 1) => {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  return v.toFixed(digits)
}

const totalMessages = computed(() => Number(props.card?.data?.totalMessages || 0))
const activeDays = computed(() => Number(props.card?.data?.activeDays || 0))
const addedFriends = computed(() => Number(props.card?.data?.addedFriends || 0))
const messagesPerDay = computed(() => Number(props.card?.data?.messagesPerDay || 0))
const sentMediaCount = computed(() => Number(props.card?.data?.sentMediaCount || 0))
const sentStickerCount = computed(() => Number(props.card?.data?.sentStickerCount || 0))

const mostActiveHour = computed(() => {
  const h = props.card?.data?.mostActiveHour
  return Number.isFinite(Number(h)) ? Number(h) : null
})

const mostActiveWeekdayName = computed(() => {
  const s = props.card?.data?.mostActiveWeekdayName
  return typeof s === 'string' && s.trim() ? s.trim() : ''
})

const topContact = computed(() => {
  const o = props.card?.data?.topContact
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const topGroup = computed(() => {
  const o = props.card?.data?.topGroup
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const peakDay = computed(() => {
  const o = props.card?.data?.peakDay
  if (!o || typeof o !== 'object') return null
  if (typeof o.date !== 'string' || !o.date.trim()) return null
  if (!(Number(o.count) > 0)) return null
  return o
})

const peakTopContact = computed(() => {
  const o = peakDay.value?.topContact
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const peakMultipleText = computed(() => {
  const m = Number(peakDay.value?.multiple)
  if (!Number.isFinite(m) || m <= 0) return ''
  return formatFloat(m, 1)
})

const apiBase = useApiBase()
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    // qpic/qlogo are often hotlink-protected; proxy via backend (same as chat page).
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

const topContactAvatarUrl = computed(() => {
  return resolveMediaUrl(topContact.value?.avatarUrl)
})

const topGroupAvatarUrl = computed(() => {
  return resolveMediaUrl(topGroup.value?.avatarUrl)
})

const peakContactAvatarUrl = computed(() => {
  return resolveMediaUrl(peakTopContact.value?.avatarUrl)
})

const avatarOk = reactive({ topContact: true, topGroup: true, peakContact: true })

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  if (!s) return '?'
  return s[0]
}

watch(topContactAvatarUrl, () => { avatarOk.topContact = true })
watch(topGroupAvatarUrl, () => { avatarOk.topGroup = true })
watch(peakContactAvatarUrl, () => { avatarOk.peakContact = true })

const topKind = computed(() => {
  const o = props.card?.data?.topKind
  return o && typeof o === 'object' && typeof o.label === 'string' ? o : null
})

const topKindPct = computed(() => {
  const r = Number(topKind.value?.ratio || 0)
  if (!Number.isFinite(r) || r <= 0) return 0
  return Math.max(0, Math.min(100, Math.round(r * 100)))
})

const topPhrase = computed(() => {
  const o = props.card?.data?.topPhrase
  return o && typeof o === 'object' ? o : null
})

// ---------------- 入场动画：大数字滚动 + 区块淡入（isActive 首次为 true 时只播一次） ----------------

const reducedMotion = useReducedMotion()
const entered = ref(false)

const { display: totalDisplay, play: playTotal, finish: finishTotal } = useCountUp(() => totalMessages.value, { duration: 1.4 })
const { display: perDayDisplay, play: playPerDay, finish: finishPerDay } = useCountUp(() => messagesPerDay.value, { duration: 1.4, decimals: 1 })
const { display: activeDaysDisplay, play: playActiveDays, finish: finishActiveDays } = useCountUp(() => activeDays.value, { duration: 1.2, delay: 0.15 })
const { display: addedFriendsDisplay, play: playAddedFriends, finish: finishAddedFriends } = useCountUp(() => addedFriends.value, { duration: 1.2, delay: 0.3 })
const { display: mediaDisplay, play: playMedia, finish: finishMedia } = useCountUp(() => sentMediaCount.value, { duration: 1.2, delay: 0.45 })
const { display: stickerDisplay, play: playSticker, finish: finishSticker } = useCountUp(() => sentStickerCount.value, { duration: 1.2, delay: 0.55 })

const playAll = () => {
  playTotal(); playPerDay(); playActiveDays(); playAddedFriends(); playMedia(); playSticker()
}

const finishAll = () => {
  finishTotal(); finishPerDay(); finishActiveDays(); finishAddedFriends(); finishMedia(); finishSticker()
}

watch(() => props.isActive, (active) => {
  if (!active || entered.value) return
  entered.value = true
  if (typeof window === 'undefined') {
    // SSR 渲染直接输出终值，动画交由客户端水合后播放
    finishAll()
    return
  }
  playAll()
}, { immediate: true })

// 卡片数据晚于入场到达时，直接定格到最新终值
watch([totalMessages, messagesPerDay, activeDays, addedFriends, sentMediaCount, sentStickerCount], () => {
  if (entered.value) finishAll()
})

// 统计行 / 峰值日区块的级联淡入类；未入场时隐藏，reduced-motion 时直接终态。
const fxClass = (order) => {
  if (reducedMotion.value) return ''
  if (!entered.value) return 'wr-fx-pre'
  return order > 0 ? 'wr-fx-in wr-fx-in--late' : 'wr-fx-in'
}
</script>

<style scoped>
.wr-fx-pre {
  opacity: 0;
}

.wr-fx-in {
  animation: wr-fx-fade-up 0.5s ease-out both;
}

.wr-fx-in--late {
  animation-delay: 0.15s;
}

@keyframes wr-fx-fade-up {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .wr-fx-pre {
    opacity: 1;
  }

  .wr-fx-in,
  .wr-fx-in--late {
    animation: none !important;
  }
}
</style>
