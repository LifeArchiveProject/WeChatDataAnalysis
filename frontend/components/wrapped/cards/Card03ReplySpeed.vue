<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
    <!-- 子描述：仅在揭晓后出现，并使用“打字机”效果逐段输出 -->
    <template #narrative>
      <div v-if="phase === 'revealed'" class="mt-2 wrapped-body text-sm sm:text-base text-[#7F7F7F] leading-relaxed">
        <p class="whitespace-pre-wrap">
          <template v-for="(seg, i) in segments" :key="`${seg.type}-${i}`">
            <template v-if="seg.type === 'buddy'">
              <span
                v-if="isSegVisible(i)"
                class="inline-flex items-center gap-2 align-bottom px-1.5 py-0.5 rounded-lg bg-[#00000008]"
                :title="bestBuddy?.displayName || ''"
              >
                <span class="w-5 h-5 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                  <img
                    v-if="bestBuddyAvatarUrl && avatarOk.best"
                    :src="bestBuddyAvatarUrl"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk.best = false"
                  />
                  <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                    {{ avatarFallback(bestBuddy?.displayName) }}
                  </span>
                </span>
                <span class="wrapped-body text-sm text-[#000000e6] max-w-[12rem] truncate wrapped-privacy-name">
                  {{ bestBuddy?.displayName || '' }}
                </span>
              </span>
            </template>

            <template v-else-if="seg.type === 'contact'">
              <span
                v-if="isSegVisible(i)"
                class="inline-flex items-center gap-1.5 align-bottom px-1.5 py-0.5 rounded-lg bg-[#00000008]"
                :title="seg.contact?.displayName || ''"
              >
                <span class="w-4 h-4 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                  <img
                    v-if="resolveMediaUrl(seg.contact?.avatarUrl) && avatarOk[seg.contact?.username] !== false"
                    :src="resolveMediaUrl(seg.contact?.avatarUrl)"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk[seg.contact?.username] = false"
                  />
                  <span v-else class="wrapped-number text-[9px] text-[#00000066]">
                    {{ avatarFallback(seg.contact?.displayName) }}
                  </span>
                </span>
                <span class="wrapped-body text-sm text-[#000000e6] max-w-[8rem] truncate wrapped-privacy-name">
                  {{ seg.contact?.displayName || '' }}
                </span>
              </span>
            </template>

            <template v-else>
              <span
                v-if="seg.type === 'num'"
                class="wrapped-number text-[#07C160] font-semibold"
              >
                {{ segTextShown(i) }}
              </span>
              <span v-else>{{ segTextShown(i) }}</span>
            </template>
          </template>

          <span v-if="typingActive" class="type-caret" aria-hidden="true"></span>
        </p>
      </div>
    </template>

    <!-- 无可统计数据/索引未就绪：保留原来的引导与进度展示 -->
    <div v-if="replyEvents <= 0" class="text-sm text-[#7F7F7F]">
      <div class="rounded-xl border border-[#EDEDED] bg-white/60 p-4">
        <div class="wrapped-label text-xs text-[#00000066]">如何生成本页数据</div>
        <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
          <p>本页需要使用“消息搜索索引”来合并所有消息分片并计算回复耗时。</p>
          <p v-if="indexBuild && indexBuild.status === 'building'" class="mt-2">
            索引正在构建中：已索引
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(indexBuild.indexedMessages) }}</span>
            条消息。
            <span v-if="indexBuild.currentConversation" class="text-[#00000055]">（当前：{{ indexBuild.currentConversation }}）</span>
          </p>
          <p v-else-if="indexBuild && indexBuild.status === 'error'" class="mt-2 text-red-600">
            索引构建失败：{{ indexBuild.error || '未知错误' }}
          </p>
          <p v-if="!usedIndex" class="mt-2">
            你可以先在「聊天记录搜索」中构建索引（或调用后端接口
            <code class="px-1 py-0.5 bg-[#00000008] rounded">/api/chat/search-index/build</code>），
            然后回到这里点击左上角“强制刷新”或本页“重试”。
          </p>
        </div>
      </div>
    </div>

    <!-- 主内容：抽奖揭晓 + 右侧年度 Top10 总消息 bar race -->
    <div v-else class="w-full">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
        <!-- Left: 抽奖区 -->
        <div
          class="reply-buddy-rail flex flex-col items-center justify-center transition-transform duration-500 will-change-transform"
          :class="leftRailClass"
        >
          <div class="wrapped-label text-xs text-[#00000066]">最佳聊天搭子</div>

          <div
            class="mt-4 w-28 h-28 sm:w-32 sm:h-32 rounded-2xl border border-[#EDEDED] bg-white/60 overflow-hidden flex items-center justify-center"
          >
            <img
              v-if="shownAvatarUrl && shownAvatarOk"
              :src="shownAvatarUrl"
              class="w-full h-full object-cover wrapped-privacy-avatar"
              alt="avatar"
              @error="onShownAvatarError"
            />
            <img
              v-else-if="phase === 'idle'"
              src="/assets/images/LuckyBlock.png"
              class="w-full h-full object-contain"
              alt="Lucky Block"
            />
            <div
              v-else
              class="w-full h-full flex items-center justify-center wrapped-privacy-avatar"
            >
              <span class="wrapped-number text-3xl text-[#00000066]">
                {{ shownAvatarFallback }}
              </span>
            </div>
          </div>

          <div class="mt-4 min-h-[1.75rem] wrapped-body text-base text-[#000000e6] max-w-[18rem] truncate wrapped-privacy-name" :title="shownDisplayName">
            {{ shownDisplayName }}
          </div>

          <div class="mt-5">
            <button
              v-if="phase === 'idle'"
              type="button"
              class="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-[#07C160] text-white text-sm sm:text-base wrapped-label hover:bg-[#06AD56] transition shadow-sm"
              @click="startLottery"
            >
              今年谁是你的最佳聊天搭子呢？
            </button>

            <button
              v-else-if="phase === 'rolling'"
              type="button"
              disabled
              class="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-[#07C160]/70 text-white text-sm sm:text-base wrapped-label cursor-not-allowed"
            >
              生成中…
            </button>

            <button
              v-else
              type="button"
              class="inline-flex items-center justify-center px-4 py-2 rounded-xl bg-transparent border border-[#07C160]/35 text-[#07C160] text-sm wrapped-label hover:bg-[#07C160]/10 transition"
              @click="restart"
            >
              再看一次
            </button>
          </div>

        </div>

        <!-- Right: bar race（揭晓后出现） -->
        <Transition name="chart-fade">
          <div v-if="showChart" class="w-full">
            <div
              class="rounded-2xl border border-[#EDEDED] bg-white/60 p-4 sm:p-5"
            >
              <div class="flex items-center justify-between gap-4">
                <div>
                  <div class="wrapped-label text-xs text-[#00000066]">年度聊天排行（我发 + 对方）</div>
                  <div class="wrapped-body text-sm text-[#000000e6] mt-1">
                    <span class="wrapped-number text-[#07C160] font-semibold">{{ raceDate }}</span>
                    <span class="text-[#00000055]"> · 0.1秒/天</span>
                  </div>
                </div>
                <div class="flex items-center gap-3 text-[11px] text-[#00000066] shrink-0">
                  <span class="inline-flex items-center gap-1">
                    <span class="w-2 h-2 rounded-full bg-[#07C160]"></span>
                    我发
                  </span>
                  <span class="inline-flex items-center gap-1">
                    <span class="w-2 h-2 rounded-full bg-[#F2AA00]"></span>
                    对方
                  </span>
                </div>
              </div>

              <div v-if="raceDay > 0 && raceItems.length === 0" class="mt-4 wrapped-body text-sm text-[#7F7F7F]">
                暂无可展示的排行榜数据。
              </div>

              <div v-else class="race-scroll mt-4 max-h-[26rem] overflow-y-auto overflow-x-hidden pr-1">
                <TransitionGroup
                  name="race"
                  tag="div"
                  class="space-y-2"
                >
                  <div
                    v-for="item in raceItems"
                    :key="item.username"
                    class="race-row flex items-center gap-3"
                  >
                  <div class="w-6 text-right wrapped-label text-[11px] text-[#00000055]">
                    {{ item.rank }}
                  </div>

                  <div
                    class="w-7 h-7 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar"
                  >
                    <img
                      v-if="item.avatarUrl && avatarOk[item.username] !== false"
                      :src="item.avatarUrl"
                      class="w-full h-full object-cover"
                      alt="avatar"
                      @error="avatarOk[item.username] = false"
                    />
                    <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                      {{ avatarFallback(item.displayName) }}
                    </span>
                  </div>

                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-3">
                      <div class="min-w-0">
                        <div class="wrapped-body text-[#000000e6] text-sm truncate wrapped-privacy-name" :title="item.displayName">
                          {{ item.displayName }}
                        </div>
                      </div>
                      <div class="wrapped-number text-xs text-[#00000080] font-semibold">
                        {{ formatInt(item.value) }}
                      </div>
                    </div>
                    <div class="mt-1 h-2 rounded-full bg-[#00000008] overflow-hidden">
                      <div
                        class="race-bar-fill h-full rounded-full overflow-hidden flex"
                        :style="{ width: `${item.pct}%` }"
                      >
                        <div
                          class="race-bar race-bar-outgoing h-full"
                          :style="{ width: `${item.outgoingPartPct}%` }"
                        />
                        <div
                          class="race-bar race-bar-incoming h-full"
                          :style="{ width: `${item.incomingPartPct}%` }"
                        />
                      </div>
                    </div>
                  </div>
                  </div>
                </TransitionGroup>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

// Data (from backend)
const replyEvents = computed(() => Number(props.card?.data?.replyEvents || 0))
const fastestReplySeconds = computed(() => props.card?.data?.fastestReplySeconds ?? null)
const longestReplySeconds = computed(() => props.card?.data?.longestReplySeconds ?? null)
const sentToContacts = computed(() => Number(props.card?.data?.sentToContacts || 0))

const bestBuddy = computed(() => {
  const o = props.card?.data?.bestBuddy
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const fastestContact = computed(() => {
  const o = props.card?.data?.fastest
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const slowestContact = computed(() => {
  const o = props.card?.data?.slowest
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const usedIndex = computed(() => !!props.card?.data?.settings?.usedIndex)
const indexBuild = computed(() => {
  const st = props.card?.data?.settings?.indexStatus
  const b = st?.index?.build
  if (!b || typeof b !== 'object') return null
  return {
    status: String(b.status || ''),
    indexedMessages: Number(b.indexedMessages || 0),
    currentConversation: String(b.currentConversation || ''),
    error: String(b.error || '')
  }
})

// Media URL resolving (same behavior as other wrapped components)
const apiBase = useApiBase()
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
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

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  return s ? s[0] : '?'
}

const avatarOk = reactive({ best: true })
const bestBuddyAvatarUrl = computed(() => resolveMediaUrl(bestBuddy.value?.avatarUrl))
watch(bestBuddyAvatarUrl, () => { avatarOk.best = true })

const resetAvatarOk = () => {
  for (const k of Object.keys(avatarOk)) delete avatarOk[k]
  avatarOk.best = true
}

// ---------------- Lottery (7s, ease-out slowdown) ----------------
const phase = ref('idle') // idle | rolling | revealed
const shownUser = ref(null) // current candidate object
const shownAvatarOk = ref(true)
const leftDocked = ref(false) // center -> left after reveal (lg)
const showChart = ref(false) // shown after the left block docks
let lotteryTimer = null
let typingTimer = null
let raceTimer = null
let dockTimer = null
let chartTimer = null

const candidates = computed(() => {
  // Prefer allContacts (all contacts from contact.db) for more variety in lottery animation
  const allContacts = Array.isArray(props.card?.data?.allContacts) ? props.card.data.allContacts : []
  const topTotals = Array.isArray(props.card?.data?.topTotals) ? props.card.data.topTotals : []

  // Merge allContacts and topTotals, deduplicate by username
  const seen = new Set()
  const out = []

  for (const x of [...allContacts, ...topTotals]) {
    if (x && typeof x === 'object' && typeof x.displayName === 'string' && !seen.has(x.username)) {
      seen.add(x.username)
      out.push(x)
    }
  }

  // Ensure bestBuddy is in candidate pool
  if (bestBuddy.value && !seen.has(bestBuddy.value.username)) {
    out.unshift(bestBuddy.value)
  }

  return out
})

const shownDisplayName = computed(() => {
  if (phase.value === 'idle') return '点击按钮揭晓'
  const o = shownUser.value
  const name = String(o?.displayName || o?.maskedName || '').trim()
  return name || '…'
})

const shownAvatarUrl = computed(() => {
  const o = shownUser.value
  if (!o) return ''
  return resolveMediaUrl(o.avatarUrl)
})

const shownAvatarFallback = computed(() => (
  phase.value === 'idle' ? '?' : avatarFallback(shownDisplayName.value)
))
const onShownAvatarError = () => { shownAvatarOk.value = false }

const pickRandomCandidate = (prevUsername) => {
  const pool = candidates.value
  if (!Array.isArray(pool) || pool.length === 0) return bestBuddy.value || null
  if (pool.length === 1) return pool[0]
  for (let i = 0; i < 6; i += 1) {
    const idx = Math.floor(Math.random() * pool.length)
    const c = pool[idx]
    if (c && c.username !== prevUsername) return c
  }
  return pool[Math.floor(Math.random() * pool.length)]
}

const clearTimers = () => {
  if (lotteryTimer) clearTimeout(lotteryTimer)
  lotteryTimer = null
  if (typingTimer) clearTimeout(typingTimer)
  typingTimer = null
  if (raceTimer) clearInterval(raceTimer)
  raceTimer = null
  if (dockTimer) clearTimeout(dockTimer)
  dockTimer = null
  if (chartTimer) clearTimeout(chartTimer)
  chartTimer = null
}

const leftRailClass = computed(() => {
  const shouldCenter = phase.value !== 'revealed' || !leftDocked.value
  return [
    'ease-[cubic-bezier(0.22,1,0.36,1)]',
    shouldCenter ? 'lg:translate-x-1/2' : ''
  ]
})

const startLottery = () => {
  clearTimers()
  resetAvatarOk()
  shownAvatarOk.value = true
  leftDocked.value = false
  showChart.value = false

  phase.value = 'rolling'
  typingReset()
  raceReset()

  const durationMs = 7000
  // Too-fast swapping makes the avatar transition lag behind; slow it down a bit (but keep it lively).
  const minDelay = 60
  const maxDelay = 220
  const startedAt = performance.now()

  const tick = () => {
    const now = performance.now()
    const elapsed = now - startedAt
    const t = Math.max(0, Math.min(1, elapsed / durationMs))

    const prev = String(shownUser.value?.username || '')
    let next = pickRandomCandidate(prev)
    const target = bestBuddy.value
    // Near the end, gradually "stick" to the final result to create a smooth slow-stop feeling.
    if (target && typeof target === 'object') {
      if (t >= 0.97) {
        next = target
      } else if (t >= 0.85) {
        const p = Math.max(0, Math.min(1, (t - 0.85) / 0.12))
        if (Math.random() < p) next = target
      }
    }
    shownUser.value = next
    shownAvatarOk.value = true

    if (t >= 1) {
      finishReveal()
      return
    }

    // Ease-out: slow down near the end to build suspense.
    const easeOutCubic = 1 - Math.pow(1 - t, 3)
    const delay = Math.round(minDelay + (maxDelay - minDelay) * easeOutCubic)
    lotteryTimer = setTimeout(tick, delay)
  }

  tick()
}

const finishReveal = () => {
  clearTimers()
  phase.value = 'revealed'
  shownUser.value = bestBuddy.value || shownUser.value
  shownAvatarOk.value = true
  leftDocked.value = false
  showChart.value = false

  // Start the narrative right away; dock left, then show the chart.
  startTypewriter()

  const settleMs = 240
  const slideMs = 520
  dockTimer = setTimeout(() => { leftDocked.value = true }, settleMs)
  chartTimer = setTimeout(() => {
    showChart.value = true
    startRace()
  }, settleMs + slideMs)
}

const restart = () => {
  // Keep UX simple: replay the same reveal, but still run the suspense animation.
  startLottery()
}

// ---------------- Typewriter narrative ----------------
const typedSegIdx = ref(0)
const typedCharIdx = ref(0)
const typingActive = ref(false)

const formatDuration = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  if (!Number.isFinite(s) || s <= 0) return '0秒'
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  const ss = s % 60
  if (m < 60) return ss ? `${m}分${ss}秒` : `${m}分钟`
  const h = Math.floor(m / 60)
  const mm = m % 60
  if (h < 24) return mm ? `${h}小时${mm}分钟` : `${h}小时`
  const d = Math.floor(h / 24)
  const hh = h % 24
  return hh ? `${d}天${hh}小时` : `${d}天`
}

const segments = computed(() => {
  const buddy = bestBuddy.value
  if (!buddy) return []

  const outMsg = Number(buddy.outgoingMessages || 0)
  const inMsg = Number(buddy.incomingMessages || 0)
  const replyCount = Number(buddy.replyCount || 0)
  const avgReply = Math.round(Number(buddy.avgReplySeconds || 0))
  const fastest = fastestReplySeconds.value
  const longest = longestReplySeconds.value

  const segs = [
    { type: 'text', text: '今年你总共给 ' },
    { type: 'num', text: formatInt(sentToContacts.value) },
    { type: 'text', text: ' 人发送过消息，其中给 ' },
    { type: 'buddy' },
    { type: 'text', text: ' 发送了 ' },
    { type: 'num', text: formatInt(outMsg) },
    { type: 'text', text: ' 条消息，收到了 ' },
    { type: 'num', text: formatInt(inMsg) },
    { type: 'text', text: ' 条消息。' },
    { type: 'text', text: '你们之间统计到 ' },
    { type: 'num', text: formatInt(replyCount) },
    { type: 'text', text: ' 次回复，平均每条回复用时 ' },
    { type: 'num', text: formatDuration(avgReply) },
    { type: 'text', text: '。' }
  ]

  if (fastest != null) {
    segs.push({ type: 'text', text: '今年你最快一次只用了 ' })
    segs.push({ type: 'num', text: formatDuration(fastest) })
    segs.push({ type: 'text', text: ' 就回了' })
    if (fastestContact.value) {
      segs.push({ type: 'contact', contact: fastestContact.value })
    }
    segs.push({ type: 'text', text: '的消息；' })
  }
  if (longest != null) {
    segs.push({ type: 'text', text: '最长一次让' })
    if (slowestContact.value) {
      segs.push({ type: 'contact', contact: slowestContact.value })
    } else {
      segs.push({ type: 'text', text: '对方' })
    }
    segs.push({ type: 'text', text: '等了 ' })
    segs.push({ type: 'num', text: formatDuration(longest) })
    segs.push({ type: 'text', text: '。' })
  }
  return segs
})

const typingReset = () => {
  typedSegIdx.value = 0
  typedCharIdx.value = 0
  typingActive.value = false
}

const isSegVisible = (i) => {
  const segType = segments.value[i]?.type
  return i < typedSegIdx.value || (i === typedSegIdx.value && (segType === 'buddy' || segType === 'contact'))
}

const segTextShown = (i) => {
  const seg = segments.value[i]
  if (!seg || seg.type === 'buddy') return ''

  if (i < typedSegIdx.value) return String(seg.text || '')
  if (i > typedSegIdx.value) return ''
  return String(seg.text || '').slice(0, Math.max(0, typedCharIdx.value))
}

const startTypewriter = () => {
  typingReset()
  typingActive.value = true

  const charDelay = 26
  const segPause = 140

  const step = () => {
    const seg = segments.value[typedSegIdx.value]
    if (!seg) {
      typingActive.value = false
      typingTimer = null
      return
    }

    if (seg.type === 'buddy') {
      // Show the buddy tag as a whole, then continue.
      typedSegIdx.value += 1
      typedCharIdx.value = 0
      typingTimer = setTimeout(step, segPause)
      return
    }

    const txt = String(seg.text || '')
    typedCharIdx.value += 1
    if (typedCharIdx.value >= txt.length) {
      typedSegIdx.value += 1
      typedCharIdx.value = 0
      typingTimer = setTimeout(step, segPause)
      return
    }

    typingTimer = setTimeout(step, charDelay)
  }

  step()
}

// ---------------- Bar race (0.1s per day) ----------------
const race = computed(() => props.card?.data?.race || null)
const raceDays = computed(() => Math.max(0, Number(race.value?.days || 0)))
const raceSeriesRaw = computed(() => (Array.isArray(race.value?.series) ? race.value.series : []))
const topTotalsByUsername = computed(() => {
  const out = new Map()
  const arr = Array.isArray(props.card?.data?.topTotals) ? props.card.data.topTotals : []
  for (const x of arr) {
    if (!x || typeof x !== 'object') continue
    const username = String(x.username || '').trim()
    if (!username) continue
    out.set(username, {
      outgoingMessages: Math.max(0, Number(x.outgoingMessages || 0)),
      incomingMessages: Math.max(0, Number(x.incomingMessages || 0))
    })
  }
  return out
})

const raceSeries = computed(() => {
  // Pre-resolve avatar URLs once to avoid doing it in tight animation loops.
  const totalsByUsername = topTotalsByUsername.value
  return raceSeriesRaw.value
    .filter((x) => x && typeof x === 'object' && typeof x.username === 'string')
    .map((x) => {
      const username = String(x.username || '')
      const fallback = totalsByUsername.get(username)
      const outgoingMessages = Math.max(0, Number(x.outgoingMessages ?? fallback?.outgoingMessages ?? 0))
      const incomingMessages = Math.max(0, Number(x.incomingMessages ?? fallback?.incomingMessages ?? 0))

      let cumulativeCounts = Array.isArray(x.cumulativeCounts) ? x.cumulativeCounts.map((v) => Math.max(0, Number(v) || 0)) : []
      let cumulativeOutgoingCounts = Array.isArray(x.cumulativeOutgoingCounts) ? x.cumulativeOutgoingCounts.map((v) => Math.max(0, Number(v) || 0)) : []
      let cumulativeIncomingCounts = Array.isArray(x.cumulativeIncomingCounts) ? x.cumulativeIncomingCounts.map((v) => Math.max(0, Number(v) || 0)) : []

      if (cumulativeCounts.length === 0 && (cumulativeOutgoingCounts.length > 0 || cumulativeIncomingCounts.length > 0)) {
        const len = Math.max(cumulativeOutgoingCounts.length, cumulativeIncomingCounts.length)
        cumulativeCounts = Array.from({ length: len }, (_, i) => (
          Number(cumulativeOutgoingCounts[i] || 0) + Number(cumulativeIncomingCounts[i] || 0)
        ))
      }

      // Backward compatibility for old caches: split total curve using final in/out ratio.
      if (cumulativeCounts.length > 0 && (cumulativeOutgoingCounts.length === 0 || cumulativeIncomingCounts.length === 0)) {
        const splitBase = outgoingMessages + incomingMessages
        const outgoingRatio = splitBase > 0 ? outgoingMessages / splitBase : 0
        cumulativeOutgoingCounts = cumulativeCounts.map((v) => Math.max(0, Math.round((Number(v) || 0) * outgoingRatio)))
        cumulativeIncomingCounts = cumulativeCounts.map((v, i) => (
          Math.max(0, (Number(v) || 0) - Number(cumulativeOutgoingCounts[i] || 0))
        ))
      }

      return {
        username,
        displayName: String(x.displayName || x.maskedName || ''),
        avatarUrl: resolveMediaUrl(x.avatarUrl),
        cumulativeCounts,
        cumulativeOutgoingCounts,
        cumulativeIncomingCounts
      }
    })
})

const raceDay = ref(0)

const raceReset = () => {
  raceDay.value = 0
}

const pad2 = (n) => String(n).padStart(2, '0')
const raceDate = computed(() => {
  const y = Number(race.value?.year || props.card?.data?.year || new Date().getFullYear())
  const step = Math.max(0, Math.min(Math.max(0, raceDays.value), Number(raceDay.value || 0)))
  if (step <= 0) return `${y} 开局`
  const d = Math.max(0, Math.min(Math.max(0, raceDays.value - 1), step - 1))
  const dt = new Date(y, 0, 1 + d)
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`
})

const valueAtRaceStep = (arr, step) => {
  if (step <= 0 || !Array.isArray(arr) || arr.length === 0) return 0
  if (step - 1 < arr.length) return Math.max(0, Number(arr[step - 1] || 0))
  return Math.max(0, Number(arr[arr.length - 1] || 0))
}

const raceItems = computed(() => {
  const step = Math.max(0, Math.min(Math.max(0, raceDays.value), Number(raceDay.value || 0)))
  const list = raceSeries.value
  if (!Array.isArray(list) || list.length === 0) return []

  let items = list.map((s) => {
    const totalV = valueAtRaceStep(s.cumulativeCounts, step)
    let outgoingV = valueAtRaceStep(s.cumulativeOutgoingCounts, step)
    let incomingV = valueAtRaceStep(s.cumulativeIncomingCounts, step)
    let value = Math.max(0, totalV)
    let splitTotal = outgoingV + incomingV

    if (value <= 0 && splitTotal > 0) value = splitTotal
    if (splitTotal <= 0 && value > 0) {
      incomingV = value
      splitTotal = value
    }

    if (splitTotal > 0 && splitTotal !== value) {
      const scale = value / splitTotal
      outgoingV = Math.max(0, Math.round(outgoingV * scale))
      incomingV = Math.max(0, value - outgoingV)
      splitTotal = outgoingV + incomingV
    }

    const outgoingPartPct = splitTotal > 0
      ? Math.max(0, Math.min(100, Math.round((outgoingV / splitTotal) * 100)))
      : 0
    const incomingPartPct = splitTotal > 0 ? 100 - outgoingPartPct : 0

    return {
      ...s,
      value,
      outgoingValue: outgoingV,
      incomingValue: incomingV,
      outgoingPartPct,
      incomingPartPct
    }
  })

  // Hide 0-value rows so the "TOP10" can evolve naturally (people enter/leave the list over time),
  // and avoid showing an arbitrary fixed set of names at the very beginning.
  items = items.filter((x) => x.value > 0)
  if (items.length === 0) return []

  items.sort((a, b) => {
    if (b.value !== a.value) return b.value - a.value
    return String(a.username).localeCompare(String(b.username))
  })

  const maxV = Math.max(1, ...items.map((x) => x.value))
  return items.slice(0, 10).map((x, idx) => ({
    ...x,
    rank: idx + 1,
    pct: Math.max(0, Math.min(100, Math.round((x.value / maxV) * 100)))
  }))
})

const startRace = () => {
  if (!race.value || raceDays.value <= 0 || raceSeries.value.length === 0) return
  if (raceTimer) clearInterval(raceTimer)
  raceDay.value = 0

  raceTimer = setInterval(() => {
    if (raceDay.value >= raceDays.value) {
      clearInterval(raceTimer)
      raceTimer = null
      return
    }
    raceDay.value += 1
  }, 100)
}

// Keep state stable when backend card updates (e.g., refresh/retry).
watch(
  () => props.card?.data,
  () => {
    clearTimers()
    resetAvatarOk()
    phase.value = 'idle'
    shownUser.value = null
    shownAvatarOk.value = true
    leftDocked.value = false
    showChart.value = false
    typingReset()
    raceReset()
  }
)

onBeforeUnmount(() => {
  clearTimers()
})
</script>

<style scoped>
.type-caret {
  display: inline-block;
  width: 0.6ch;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.12em;
  background: rgba(7, 193, 96, 0.85);
  animation: caret-blink 1s steps(1) infinite;
}

@keyframes caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

.chart-fade-enter-active,
.chart-fade-leave-active {
  transition: opacity 240ms ease, transform 240ms ease !important;
}
.chart-fade-enter-from,
.chart-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.reply-buddy-rail {
  /* DOS theme sets `transition: text-shadow ... !important` on `*` (global).
     Use an explicit transition here so the rail slide stays smooth in all themes. */
  transition: transform 500ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.race-scroll {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.race-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.race-move {
  transition: transform 350ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.race-bar-fill {
  transition: width 120ms linear !important;
}

.race-bar {
  transition: width 120ms linear !important;
}

.race-bar-outgoing {
  background: #07c160;
}

.race-bar-incoming {
  background: #f2aa00;
}
</style>
