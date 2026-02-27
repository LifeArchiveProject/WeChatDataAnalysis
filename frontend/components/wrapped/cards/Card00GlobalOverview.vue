<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
    <template #narrative>
      <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
        <p>
          <template v-if="totalMessages > 0">
            这一年，你在微信里发送了
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
            条消息，平均每天
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatFloat(messagesPerDay, 1) }}</span>
            条。
          </template>
          <template v-else>
            这一年，你在微信里还没有发出聊天消息——也许，你把时间留给了更重要的人和事。
          </template>

          <template v-if="activeDays > 0">
            在与你相伴的
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(activeDays) }}</span>
            天里，
            <template v-if="addedFriends > 0">
              你总共加了
              <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(addedFriends) }}</span>
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
      </div>
    </template>

    <div :class="variant === 'slide' ? 'w-full -mt-2 sm:-mt-4' : 'w-full'">
      <GlobalOverviewChart :data="card.data || {}" />
    </div>
  </WrappedCardShell>
</template>

<script setup>
import GlobalOverviewChart from '~/components/wrapped/visualizations/GlobalOverviewChart.vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
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

// Keep the same behavior as the chat page: media (including avatars) comes from backend :8000 in dev.
const mediaBase = process.client ? 'http://localhost:8000' : ''
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    // qpic/qlogo are often hotlink-protected; proxy via backend (same as chat page).
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${mediaBase}/api/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  // Most backend fields are like "/api/...", so just prefix.
  return `${mediaBase}${raw.startsWith('/') ? '' : '/'}${raw}`
}

const topContactAvatarUrl = computed(() => {
  return resolveMediaUrl(topContact.value?.avatarUrl)
})

const topGroupAvatarUrl = computed(() => {
  return resolveMediaUrl(topGroup.value?.avatarUrl)
})

const avatarOk = reactive({ topContact: true, topGroup: true })

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  if (!s) return '?'
  return s[0]
}

watch(topContactAvatarUrl, () => { avatarOk.topContact = true })
watch(topGroupAvatarUrl, () => { avatarOk.topGroup = true })

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
</script>
