<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
    <template #narrative>
      <p class="mt-2 wrapped-body text-sm text-[#00000055]">
        <template v-if="totalMessages <= 0">
          这一年，你在微信里还没有发出聊天消息——也许，你把时间留给了更重要的人和事。
        </template>
        <template v-else>
          这一年，你在微信里发送了
          <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(totalMessages) }}</span>
          条消息，平均每天
          <span class="wrapped-number text-[#07C160] font-semibold">{{ messagesPerDay.toFixed(1) }}</span>
          条。

          <template v-if="activeDays > 0">
            在与你相伴的
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(activeDays) }}</span>
            天里，<template v-if="addedFriends > 0">你总共加了
              <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(addedFriends) }}</span>
              位好友，</template><template v-if="mostActiveHour !== null && mostActiveWeekdayName">你最常在 {{ mostActiveWeekdayName }} 的
              <span class="wrapped-number text-[#07C160] font-semibold">{{ mostActiveHour }}</span>
              点出现。</template><template v-else>你留下了不少对话的痕迹。</template>
          </template>

          <template v-if="topContact || topGroup">
            <template v-if="topContact">你发消息最多的人是「<span class="wrapped-privacy-name">{{ topContact.displayName }}</span>」（<span class="wrapped-number">{{ formatInt(topContact.messages) }}</span> 条）</template><template v-if="topContact && topGroup">，</template><template v-if="topGroup">你最常发言的群是「<span class="wrapped-privacy-name">{{ topGroup.displayName }}</span>」（<span class="wrapped-number">{{ formatInt(topGroup.messages) }}</span> 条）</template>。
          </template>

          <template v-if="topKind">你更常用{{ topKind.label }}来表达（<span class="wrapped-number">{{ topKindPct }}</span>%）。</template>

          <template v-if="topPhrase && topPhrase.phrase && topPhrase.count > 0">你说得最多的一句话是「<span class="wrapped-privacy-keyword">{{ topPhrase.phrase }}</span>」（<span class="wrapped-number">{{ formatInt(topPhrase.count) }}</span> 次）。</template>

          愿你的每一句分享，都有人回应。
        </template>
      </p>
    </template>

    <div class="w-full annual-index" :class="{ 'ai--in': entered, 'ai--still': !isActive }">
      <!-- 背景剪影层：用本人真实数据做的描边幽灵字，衬在右侧面板空区（与左侧描边年份同语言） -->
      <div v-if="totalMessages > 0" class="ai-bg" aria-hidden="true">
        <!-- 年度口头禅（过长时退化为次数） -->
        <span v-if="ghostPhrase" class="ai-ghost ai-ghost--phrase wrapped-number wrapped-privacy-message">{{ ghostPhrase }}</span>
        <!-- 口头禅次数 -->
        <span v-if="ghostPhraseCount" class="ai-ghost ai-ghost--count wrapped-number">{{ ghostPhraseCount }}</span>
        <!-- 峰值日期 -->
        <span v-if="ghostPeakDate" class="ai-ghost ai-ghost--peak wrapped-number">{{ ghostPeakDate }}</span>
        <!-- 新朋友数 -->
        <span v-if="addedFriends > 0" class="ai-ghost ai-ghost--friends wrapped-number">+{{ formatInt(addedFriends) }}</span>
      </div>

      <div v-if="totalMessages > 0" class="ai-grid">
        <!-- 左：巨型数字块（衬底为描边年份，纯排印，无光效） -->
        <div class="ai-hero">
          <div v-if="heroYear" class="ai-hero-year wrapped-number" aria-hidden="true">{{ heroYear }}</div>
          <div class="ai-hero-body">
            <div class="ai-hero-num wrapped-number">{{ totalDisplay }}</div>
            <div class="ai-hero-sub wrapped-body">
              条消息 · 日均
              <span class="wrapped-number text-[#07C160] font-semibold">{{ perDayDisplay }}</span>
              条
            </div>
          </div>
        </div>

        <!-- 右：编辑面板（层级差异化：头条 / 双栏 / 题注 / 数据带 / 峰值条目） -->
        <div class="ai-panel">
          <!-- ① 头条：最常联系 -->
          <div v-if="topContact" class="aip-block aip-featured" :style="{ '--row-delay': '260ms' }" :title="topContact.displayName">
            <span class="aip-label wrapped-label">最常联系</span>
            <div class="aip-featured-row">
              <span class="aip-avatar aip-avatar--lg wrapped-privacy-avatar">
                <img v-if="topContactAvatarUrl && avatarOk.topContact" :src="topContactAvatarUrl" alt="" @error="avatarOk.topContact = false" />
                <span v-else class="wrapped-number text-sm text-[#00000066]">{{ avatarFallback(topContact.displayName) }}</span>
              </span>
              <span class="aip-featured-name wrapped-body wrapped-privacy-name">{{ topContact.displayName }}</span>
              <span class="aip-featured-num wrapped-number">{{ formatInt(topContact.messages) }}<i class="aip-unit">条</i></span>
            </div>
          </div>

          <!-- ② 双栏：最活跃群聊 / 年度口头禅 -->
          <div v-if="topGroup || (topPhrase && topPhrase.phrase && topPhrase.count > 0)" class="aip-block aip-duo" :style="{ '--row-delay': '350ms' }">
            <div v-if="topGroup" class="aip-duo-item" :title="topGroup.displayName">
              <span class="aip-label wrapped-label">最活跃群聊</span>
              <span class="aip-duo-value">
                <span class="aip-avatar wrapped-privacy-avatar">
                  <img v-if="topGroupAvatarUrl && avatarOk.topGroup" :src="topGroupAvatarUrl" alt="" @error="avatarOk.topGroup = false" />
                  <span v-else class="wrapped-number text-[10px] text-[#00000066]">{{ avatarFallback(topGroup.displayName) }}</span>
                </span>
                <span class="aip-duo-text truncate wrapped-privacy-name">{{ topGroup.displayName }}</span>
                <span class="aip-num wrapped-number">{{ formatInt(topGroup.messages) }}<i class="aip-unit">条</i></span>
              </span>
            </div>
            <div v-if="topPhrase && topPhrase.phrase && topPhrase.count > 0" class="aip-duo-item" :title="topPhrase.phrase">
              <span class="aip-label wrapped-label">年度口头禅</span>
              <span class="aip-duo-value">
                <span class="aip-quote truncate wrapped-privacy-message">「{{ topPhrase.phrase }}」</span>
                <span class="aip-num wrapped-number">×{{ formatInt(topPhrase.count) }}</span>
              </span>
            </div>
          </div>

          <!-- ③ 题注：出现时刻 -->
          <p v-if="mostActiveHour !== null && mostActiveWeekdayName" class="aip-block aip-when wrapped-body" :style="{ '--row-delay': '440ms' }">
            这一年，你最常出现在
            <span class="aip-when-token wrapped-number">{{ mostActiveWeekdayName }}</span>
            的
            <span class="aip-when-token wrapped-number">{{ mostActiveHour }} 点</span>
          </p>

          <!-- ④ 数据带：小数字横排（「最长连续」悬停联动热力图） -->
          <div v-if="miniStats.length" class="aip-block aip-strip" :style="{ '--row-delay': '520ms' }">
            <div
              v-for="s in miniStats"
              :key="s.key"
              class="aip-stat"
              :class="{ 'aip-stat--linked': !!s.focus }"
              :title="s.title || undefined"
              @mouseenter="rowFocus = s.focus || null"
              @mouseleave="rowFocus = null"
            >
              <span class="aip-stat-num wrapped-number">{{ s.num }}<i class="aip-unit">{{ s.unit }}</i></span>
              <span class="aip-stat-label wrapped-label">{{ s.label }}</span>
            </div>
          </div>

          <!-- ⑤ 峰值日：面板底部唯一保留点线语言的琥珀条目 -->
          <div
            v-if="peakDay"
            class="aip-block ai-row--peak"
            :style="{ '--row-delay': '610ms' }"
            @mouseenter="rowFocus = peakFocus"
            @mouseleave="rowFocus = null"
          >
            <div class="relative w-full">
              <button
                type="button"
                class="ai-peak-btn"
                :class="{ 'ai-peak-btn--open': peakOpen, 'ai-peak-btn--static': !peakHasStory }"
                :aria-expanded="peakHasStory ? String(peakOpen) : undefined"
                @click.stop="togglePeak"
              >
                <span class="ai-row__label ai-row__label--peak wrapped-label">
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M13.5 2s.5 2.5-1 4.5S9 9 9 11a3 3 0 0 0 6 .5c1.5 1 2.5 2.5 2.5 4.5a5.5 5.5 0 0 1-11 0c0-3 1.5-4.5 2-7C9 6.5 8.5 5 8.5 5S14 4.5 13.5 2Z" />
                  </svg>
                  年度峰值日
                </span>
                <span class="ai-row__leader ai-row__leader--peak" aria-hidden="true"></span>
                <span class="ai-row__value">
                  <span class="ai-row__text">{{ peakDateLabel }}<template v-if="peakDay.weekdayName"> {{ peakDay.weekdayName }}</template></span>
                  <span class="ai-row__num wrapped-number">{{ formatInt(peakDay.count) }}</span>
                  <span class="ai-row__unit">条</span>
                  <span v-if="peakMultipleText" class="ai-row__peak-mult wrapped-number">日均 {{ peakMultipleText }} 倍</span>
                  <svg
                    v-if="peakHasStory"
                    class="ai-peak-chevron"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </span>
              </button>

              <Transition name="peak-pop">
                <div v-if="peakOpen && peakHasStory" class="peak-popover" @click.stop>
                  <div v-if="peakTopContact" class="flex items-center gap-2.5 min-w-0">
                    <span class="w-8 h-8 rounded-lg overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                      <img
                        v-if="peakContactAvatarUrl && avatarOk.peakContact"
                        :src="peakContactAvatarUrl"
                        class="w-full h-full object-cover"
                        alt="avatar"
                        @error="avatarOk.peakContact = false"
                      />
                      <span v-else class="wrapped-number text-xs text-[#00000066]">{{ avatarFallback(peakTopContact.displayName) }}</span>
                    </span>
                    <span class="min-w-0">
                      <span class="block wrapped-body text-sm text-[#000000e6] font-medium truncate wrapped-privacy-name">{{ peakTopContact.displayName }}</span>
                      <span class="block wrapped-label text-[10px] text-[#00000055]">
                        当日主角 ·
                        <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(peakTopContact.messages) }}</span>
                        条
                      </span>
                    </span>
                  </div>

                  <!-- 首末句：以你自己的绿色气泡原样呈现 -->
                  <div v-if="peakDay.firstText || peakDay.lastText" class="peak-msgs">
                    <div v-if="peakDay.firstText" class="peak-msg">
                      <span class="peak-msg__meta wrapped-label">那天的第一句<template v-if="peakDay.firstTime"> · {{ peakDay.firstTime }}</template></span>
                      <span class="peak-msg__bubble wrapped-body wrapped-privacy-message">{{ peakDay.firstText }}</span>
                    </div>
                    <div v-if="peakDay.lastText" class="peak-msg">
                      <span class="peak-msg__meta wrapped-label">那天的最后一句<template v-if="peakDay.lastTime"> · {{ peakDay.lastTime }}</template></span>
                      <span class="peak-msg__bubble wrapped-body wrapped-privacy-message">{{ peakDay.lastText }}</span>
                    </div>
                  </div>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </div>

      <!-- 传入推迟后的 entered：热力图波浪与其余入场同步在翻页落定后开播 -->
      <div class="ai-heatmap">
        <GlobalOverviewChart :data="card.data || {}" :is-active="entered" :focus-doys="rowFocus" />
      </div>
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

const { display: totalDisplay, restart: restartTotal, finish: finishTotal } = useCountUp(() => totalMessages.value, { duration: 1.6, delay: 0.2 })
const { display: perDayDisplay, restart: restartPerDay, finish: finishPerDay } = useCountUp(() => messagesPerDay.value, { duration: 1.4, delay: 0.3, decimals: 1 })
const { display: activeDaysDisplay, restart: restartActiveDays, finish: finishActiveDays } = useCountUp(() => activeDays.value, { duration: 1.2, delay: 0.5 })
const { display: addedFriendsDisplay, restart: restartAddedFriends, finish: finishAddedFriends } = useCountUp(() => addedFriends.value, { duration: 1.2, delay: 0.65 })
const { display: mediaDisplay, restart: restartMedia, finish: finishMedia } = useCountUp(() => sentMediaCount.value, { duration: 1.2, delay: 0.8 })
const { display: stickerDisplay, restart: restartSticker, finish: finishSticker } = useCountUp(() => sentStickerCount.value, { duration: 1.2, delay: 0.95 })

const restartAll = () => {
  restartTotal(); restartPerDay(); restartActiveDays(); restartAddedFriends(); restartMedia(); restartSticker()
}

const finishAll = () => {
  finishTotal(); finishPerDay(); finishActiveDays(); finishAddedFriends(); finishMedia(); finishSticker()
}

// 每次翻到本页都重播入场。时序与 deck 700ms 翻页动画错开，避免两波动画叠加掉帧：
// 进入后 450ms（翻页基本落定）才开播；离开后 750ms（翻页彻底结束）才复位，翻走过程中内容不消失。
const ENTRANCE_START_DELAY_MS = 450
const ENTRANCE_RESET_DELAY_MS = 750
let entranceDelayTimer = 0
let entranceResetTimer = 0

const clearEntranceTimers = () => {
  if (typeof window === 'undefined') return
  if (entranceDelayTimer) { window.clearTimeout(entranceDelayTimer); entranceDelayTimer = 0 }
  if (entranceResetTimer) { window.clearTimeout(entranceResetTimer); entranceResetTimer = 0 }
}

watch(() => props.isActive, (active) => {
  if (typeof window === 'undefined') {
    // SSR 渲染直接输出终值，动画交由客户端水合后播放
    entered.value = true
    finishAll()
    return
  }
  clearEntranceTimers()
  if (!active) {
    entranceResetTimer = window.setTimeout(() => {
      entranceResetTimer = 0
      entered.value = false
    }, ENTRANCE_RESET_DELAY_MS)
    return
  }
  if (reducedMotion.value) {
    entered.value = true
    finishAll()
    return
  }
  // 极快折返（复位尚未发生）时保持现状，不重播
  if (entered.value) return
  entranceDelayTimer = window.setTimeout(() => {
    entranceDelayTimer = 0
    entered.value = true
    restartAll()
  }, ENTRANCE_START_DELAY_MS)
}, { immediate: true })

onBeforeUnmount(clearEntranceTimers)

// 卡片数据晚于入场到达时，直接定格到最新终值
watch([totalMessages, messagesPerDay, activeDays, addedFriends, sentMediaCount, sentStickerCount], () => {
  if (entered.value) finishAll()
})

// 峰值日日期展示为「M月D日」
const peakDateLabel = computed(() => {
  const s = String(peakDay.value?.date || '')
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return s
  return `${Number(m[2])}月${Number(m[3])}日`
})

// 数据带：小数字横排（数值为 0 的自动缺席；「最长连续」悬停联动热力图）
const miniStats = computed(() => {
  const out = []
  if (activeDays.value > 0) {
    out.push({ key: 'days', num: activeDaysDisplay.value, unit: '天', label: '活跃天数' })
  }
  if (longestStreak.value && longestStreak.value.len >= 3) {
    out.push({
      key: 'streak', num: formatInt(longestStreak.value.len), unit: '天', label: '最长连续',
      focus: { start: longestStreak.value.start, end: longestStreak.value.end },
      title: `${streakRangeLabel.value}，悬停联动热力图`,
    })
  }
  if (addedFriends.value > 0) {
    out.push({ key: 'friends', num: addedFriendsDisplay.value, unit: '位', label: '新朋友' })
  }
  if (sentMediaCount.value > 0) {
    out.push({ key: 'media', num: mediaDisplay.value, unit: '条', label: '图片/视频' })
  }
  if (sentStickerCount.value > 0) {
    out.push({ key: 'sticker', num: stickerDisplay.value, unit: '条', label: '表情包' })
  }
  return out
})

// 衬底描边年份：优先取热力图年份，缺失时从峰值日日期推断
const heroYear = computed(() => {
  const y = Number(props.card?.data?.annualHeatmap?.year)
  if (Number.isFinite(y) && y > 2000) return String(y)
  const m = String(peakDay.value?.date || '').match(/^(\d{4})-/)
  return m ? m[1] : ''
})

// 最长连续活跃区间：前端直接从逐日计数推导（doy 0 起）
const longestStreak = computed(() => {
  const arr = props.card?.data?.annualHeatmap?.dailyCounts
  if (!Array.isArray(arr) || arr.length === 0) return null
  let best = null
  let runStart = -1
  for (let i = 0; i <= arr.length; i += 1) {
    const active = i < arr.length && Number(arr[i] || 0) > 0
    if (active && runStart < 0) runStart = i
    if (!active && runStart >= 0) {
      const len = i - runStart
      if (!best || len > best.len) best = { start: runStart, end: i - 1, len }
      runStart = -1
    }
  }
  return best
})

const doyToLabel = (doy) => {
  const y = Number(props.card?.data?.annualHeatmap?.year)
  if (!Number.isFinite(y)) return ''
  const d = new Date(Date.UTC(y, 0, 1 + doy))
  return `${d.getUTCMonth() + 1}月${d.getUTCDate()}日`
}

const streakRangeLabel = computed(() => {
  const s = longestStreak.value
  if (!s) return ''
  return `${doyToLabel(s.start)} – ${doyToLabel(s.end)}`
})

// 峰值日在热力图上的聚焦区间（单日）
const peakFocus = computed(() => {
  const hs = props.card?.data?.annualHeatmap?.highlights
  const doy = Number(Array.isArray(hs) && hs[0] ? hs[0].doy : NaN)
  return Number.isFinite(doy) ? { start: doy, end: doy } : null
})

// 目录行悬停 → 热力图聚光该区间
const rowFocus = ref(null)

// ---------------- 背景幽灵字（真实数据做剪影） ----------------

// 口头禅短（≤6 字）才做大字剪影，过长退化为不展示（次数剪影仍在）
const ghostPhrase = computed(() => {
  const p = String(topPhrase.value?.phrase || '').trim()
  if (!p || Number(topPhrase.value?.count || 0) <= 0) return ''
  return p.length <= 6 ? `「${p}」` : ''
})

const ghostPhraseCount = computed(() => {
  const n = Number(topPhrase.value?.count || 0)
  return n > 0 ? `×${formatInt(n)}` : ''
})

// 峰值日期短格式 "8/19"
const ghostPeakDate = computed(() => {
  const m = String(peakDay.value?.date || '').match(/^\d{4}-(\d{2})-(\d{2})$/)
  return m ? `${Number(m[1])}/${Number(m[2])}` : ''
})

// ---------------- 峰值日故事弹层 ----------------

const peakHasStory = computed(() => !!(peakTopContact.value || peakDay.value?.firstText || peakDay.value?.lastText))
const peakOpen = ref(false)

const togglePeak = () => {
  if (!peakHasStory.value) return
  peakOpen.value = !peakOpen.value
}

// 离开本页时收起弹层（不做自动展开，故事由用户主动点开）
watch(entered, (on) => {
  if (!on) peakOpen.value = false
})

const onDocPointerDown = () => {
  if (peakOpen.value) peakOpen.value = false
}

onMounted(() => {
  if (typeof document !== 'undefined') document.addEventListener('pointerdown', onDocPointerDown)
})

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('pointerdown', onDocPointerDown)
})

</script>

<style scoped>
/* ---------------- 目录页排印（editorial index） ---------------- */

.ai-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 18px 48px;
  align-items: center;
  padding: 4px 0 10px;
}

@media (min-width: 1024px) {
  .ai-grid {
    grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
    padding: 8px 0 16px;
  }
}

/* 左：巨型数字块 */
.ai-hero {
  position: relative;
  text-align: center;
  padding: 26px 0 10px;
}

@media (min-width: 1024px) {
  .ai-hero {
    text-align: left;
    padding: 30px 0 14px 6px;
  }
}

/* 衬底描边年份：纯排印的层次，不用任何光效 */
.ai-hero-year {
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  font-size: clamp(4.4rem, 9vw, 7rem);
  line-height: 1;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: transparent;
  -webkit-text-stroke: 1.5px rgba(7, 193, 96, 0.18);
  user-select: none;
  pointer-events: none;
}

@media (min-width: 1024px) {
  .ai-hero-year {
    left: 0;
    transform: none;
  }
}

.ai-hero-body {
  position: relative;
}

.ai-hero-num {
  font-size: clamp(2.9rem, 6vw, 4.4rem);
  line-height: 1.02;
  font-weight: 700;
  letter-spacing: 0.005em;
  color: #000000e6;
  font-variant-numeric: tabular-nums;
}

.ai-hero-sub {
  margin-top: 8px;
  font-size: 14px;
  color: #00000066;
}

/* 右：目录索引 */
.ai-list {
  list-style: none;
  margin: 0;
  padding: 0;
  min-width: 0;
}

.ai-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 5.5px 0;
  min-width: 0;
}

.ai-row__label {
  flex-shrink: 0;
  font-size: 12px;
  color: #00000066;
  letter-spacing: 0.02em;
}

/* 点线引导（print 目录页语言） */
.ai-row__leader {
  flex: 1 1 24px;
  min-width: 24px;
  border-bottom: 2px dotted rgba(0, 0, 0, 0.13);
  transform: translateY(-4px);
  transition: border-color 0.2s ease;
}

.ai-row:hover .ai-row__leader {
  border-color: rgba(7, 193, 96, 0.45);
}

/* 与热力图联动的行：悬停时给一点"可指向"暗示 */
.ai-row--linked {
  cursor: crosshair;
}

.ai-row--linked:hover .ai-row__num {
  text-shadow: 0 0 12px rgba(7, 193, 96, 0.45);
}

.ai-row__value {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 62%;
}

.ai-row__avatar {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  overflow: hidden;
  flex-shrink: 0;
  align-self: center;
}

.ai-row__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ai-row__text {
  font-size: 14px;
  font-weight: 500;
  color: #000000e6;
}

.ai-row__num {
  font-size: 14px;
  font-weight: 650;
  color: #07c160;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.ai-row__unit {
  font-size: 11px;
  color: #00000055;
  flex-shrink: 0;
}

/* 峰值日行：目录中唯一的琥珀条目 */
.ai-row--peak {
  padding: 3px 0 0;
}

.ai-peak-btn {
  display: flex;
  align-items: baseline;
  gap: 10px;
  width: 100%;
  padding: 4px 6px;
  margin: 0 -6px;
  border: none;
  background: none;
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
  transition: background 0.2s ease;
  -webkit-tap-highlight-color: transparent;
}

.ai-peak-btn:hover {
  background: rgba(245, 158, 11, 0.07);
}

.ai-peak-btn--static {
  cursor: default;
}

.ai-peak-btn:focus-visible {
  outline: 2px solid rgba(245, 158, 11, 0.45);
  outline-offset: 2px;
}

.ai-row__label--peak {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #b45309;
}

.ai-row__leader--peak {
  border-color: rgba(245, 158, 11, 0.3);
}

.ai-peak-btn:hover .ai-row__leader--peak {
  border-color: rgba(245, 158, 11, 0.55);
}

.ai-row__peak-mult {
  font-size: 11px;
  color: #b45309;
  flex-shrink: 0;
}

.ai-peak-chevron {
  width: 12px;
  height: 12px;
  color: #b45309;
  opacity: 0.7;
  align-self: center;
  transition: transform 0.25s ease;
}

.ai-peak-btn--open .ai-peak-chevron {
  transform: rotate(180deg);
}

/* ---------------- 入场：逐行浮现（每次进页重播），无循环动效 ---------------- */

.annual-index:not(.ai--in) .ai-hero-body,
.annual-index:not(.ai--in) .ai-hero-year,
.annual-index:not(.ai--in) .ai-row {
  opacity: 0;
}

.ai--in .ai-hero-body {
  animation: ai-rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) 0.05s both;
}

.ai--in .ai-hero-year {
  animation: ai-fade 0.8s ease 0.25s both;
}

.ai--in .ai-row {
  animation: ai-row-in 0.45s ease var(--row-delay, 0ms) both;
}

.ai--still .ai-hero-body,
.ai--still .ai-hero-year,
.ai--still .ai-row {
  animation-play-state: paused;
}

@keyframes ai-rise {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@keyframes ai-fade {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes ai-row-in {
  from {
    opacity: 0;
    transform: translateX(-10px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

/* ---------------- 峰值日故事弹层 ---------------- */

.peak-popover {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 40;
  width: min(360px, calc(100vw - 48px));
  background: #ffffff;
  border: 1px solid #ededed;
  border-radius: 14px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.peak-msgs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 首末句都是本人发出的消息：右对齐绿色气泡 */
.peak-msg {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.peak-msg__meta {
  font-size: 10px;
  color: #00000055;
}

.peak-msg__bubble {
  max-width: 100%;
  background: #95ec69;
  color: #0b3d1f;
  border-radius: 12px;
  border-top-right-radius: 4px;
  padding: 6px 10px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

.peak-pop-enter-active,
.peak-pop-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.peak-pop-enter-from,
.peak-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ---------------- 背景剪影层 ---------------- */

.annual-index {
  position: relative;
  z-index: 0;
}

.ai-bg {
  position: absolute;
  inset: -16px -8px -8px;
  z-index: -1;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.9s ease 0.55s;
}

.ai--in .ai-bg {
  opacity: 1;
}

/* 幽灵字基底：描边空心字，与左侧「2025」同语言 */
.ai-ghost {
  position: absolute;
  line-height: 1;
  font-weight: 800;
  white-space: nowrap;
  color: transparent;
  user-select: none;
}

/* 年度口头禅：右上大字，微倾 */
.ai-ghost--phrase {
  top: -3%;
  right: 1%;
  font-size: clamp(3rem, 5.2vw, 4.4rem);
  letter-spacing: 0.02em;
  transform: rotate(-3deg);
  -webkit-text-stroke: 1.5px rgba(7, 193, 96, 0.16);
}

/* 口头禅次数：跟在口头禅右下 */
.ai-ghost--count {
  top: 13%;
  right: 3%;
  font-size: 1.6rem;
  transform: rotate(-3deg);
  -webkit-text-stroke: 1.2px rgba(7, 193, 96, 0.2);
}

/* 峰值日期：右下（峰值条目附近），琥珀描边 */
.ai-ghost--peak {
  top: 33%;
  right: -0.5%;
  font-size: clamp(2.4rem, 4vw, 3.4rem);
  transform: rotate(2.5deg);
  -webkit-text-stroke: 1.5px rgba(245, 158, 11, 0.2);
}

/* 新朋友数：中缝偏右下 */
.ai-ghost--friends {
  top: 37%;
  left: 45%;
  font-size: 2rem;
  transform: rotate(-2deg);
  -webkit-text-stroke: 1.2px rgba(0, 0, 0, 0.07);
}

/* 窄屏（单列堆叠）时只保留口头禅一枚小幽灵字，避免压在文字底下 */
@media (max-width: 1023px) {
  .ai-ghost--count,
  .ai-ghost--peak,
  .ai-ghost--friends {
    display: none;
  }

  .ai-ghost--phrase {
    top: 0;
    right: 0;
    font-size: 2.2rem;
  }
}

/* ---------------- 右栏编辑面板（层级差异化） ---------------- */

.ai-panel {
  display: flex;
  flex-direction: column;
  gap: 15px;
  min-width: 0;
}

.aip-label {
  display: block;
  font-size: 11px;
  color: #00000059;
  letter-spacing: 0.06em;
}

.aip-unit {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: #00000055;
  margin-left: 2px;
}

.aip-avatar {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: #0000000d;
  display: flex;
  align-items: center;
  justify-content: center;
}

.aip-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.aip-avatar--lg {
  width: 36px;
  height: 36px;
  border-radius: 10px;
}

/* ① 头条：绿色侧标线 */
.aip-featured {
  border-left: 3px solid #07c160;
  padding-left: 14px;
}

.aip-featured-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  min-width: 0;
}

.aip-featured-name {
  font-size: 17px;
  font-weight: 600;
  color: #000000e6;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.aip-featured-num {
  margin-left: auto;
  font-size: 22px;
  font-weight: 700;
  color: #07c160;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* ② 双栏 */
.aip-duo {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px 18px;
}

@media (min-width: 640px) {
  .aip-duo {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .aip-duo-item + .aip-duo-item {
    border-left: 1px solid #00000010;
    padding-left: 18px;
  }
}

.aip-duo-value {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 5px;
  min-width: 0;
}

.aip-duo-text {
  font-size: 14px;
  font-weight: 500;
  color: #000000e6;
  min-width: 0;
}

.aip-num {
  font-size: 14px;
  font-weight: 650;
  color: #07c160;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.aip-quote {
  font-size: 15px;
  font-weight: 600;
  color: #000000e6;
  min-width: 0;
}

/* ③ 题注 */
.aip-when {
  font-size: 13px;
  color: #00000066;
}

.aip-when-token {
  color: #07c160;
  font-weight: 600;
}

/* ④ 数据带：暗色小数字 + 细线分隔，与绿色主数字形成对比 */
.aip-strip {
  display: flex;
  align-items: stretch;
  border-top: 1px solid #00000010;
  border-bottom: 1px solid #00000010;
  padding: 9px 0;
}

.aip-stat {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  text-align: center;
  padding: 0 6px;
}

.aip-stat + .aip-stat {
  border-left: 1px solid #00000010;
}

.aip-stat-num {
  font-size: 16px;
  font-weight: 650;
  color: #000000e6;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.aip-stat-label {
  font-size: 10px;
  color: #00000059;
  white-space: nowrap;
}

.aip-stat--linked {
  cursor: crosshair;
}

.aip-stat--linked:hover .aip-stat-num {
  color: #07c160;
}

/* 面板分块入场：与目录行同一动画语言 */
.annual-index:not(.ai--in) .aip-block {
  opacity: 0;
}

.ai--in .aip-block {
  animation: ai-row-in 0.45s ease var(--row-delay, 0ms) both;
}

.ai--still .aip-block {
  animation-play-state: paused;
}

@media (prefers-reduced-motion: reduce) {
  .annual-index:not(.ai--in) .ai-hero-body,
  .annual-index:not(.ai--in) .ai-hero-year,
  .annual-index:not(.ai--in) .ai-row,
  .annual-index:not(.ai--in) .aip-block {
    opacity: 1;
  }

  .ai--in .ai-hero-body,
  .ai--in .ai-hero-year,
  .ai--in .ai-row,
  .ai--in .aip-block {
    animation: none !important;
  }

  .peak-pop-enter-active,
  .peak-pop-leave-active {
    transition: none;
  }
}
</style>
