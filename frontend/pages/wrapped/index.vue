<template>
  <div
    ref="deckEl"
    class="wrapped-deck-root relative h-screen w-full overflow-hidden transition-colors duration-500"
    :style="{ backgroundColor: currentBg }"
  >
    <!-- PPT 风格：单张卡片占据全页面，鼠标滚轮切换 -->
    <WrappedDeckBackground />

    <!-- 左上角：返回 + 刷新 -->
    <div v-show="!deckChromeHidden" class="absolute top-6 left-6 z-20 select-none transition-opacity duration-300">
      <div class="flex items-center gap-3">
        <button
          type="button"
          class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent text-[#07C160] hover:bg-[#07C160]/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 transition"
          aria-label="返回上一级"
          title="返回上一级"
          @click="goBack"
        >
          <svg
            class="w-4 h-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </button>

        <button
          type="button"
          class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent text-[#07C160] hover:bg-[#07C160]/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 disabled:opacity-60 disabled:cursor-not-allowed transition"
          :disabled="loading || accountsLoading || accounts.length === 0"
          aria-label="强制刷新（忽略缓存）"
          title="强制刷新（忽略缓存）"
          @click="reload(true)"
        >
          <!-- Refresh icon (spins while loading) -->
          <svg
            class="w-4 h-4"
            :class="loading ? 'animate-spin' : ''"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M21 12a9 9 0 1 1-3-6.7" />
            <path d="M21 3v7h-7" />
          </svg>
        </button>

      </div>

      <div v-if="error" class="mt-2 pointer-events-auto bg-white/90 backdrop-blur rounded-xl border border-red-200 px-3 py-2">
        <div class="wrapped-label text-xs text-red-700">生成失败</div>
        <div class="mt-1 wrapped-body text-xs text-red-600 whitespace-pre-wrap">{{ error }}</div>
      </div>
    </div>

    <!-- 右上角：年份选择器（主题化） -->
    <div v-show="!deckChromeHidden" class="absolute top-6 right-6 z-20 pointer-events-auto select-none transition-opacity duration-300">
      <div class="relative">
        <div class="absolute -inset-6 rounded-full bg-[#07C160]/10 blur-2xl"></div>
        <div class="relative flex justify-end">
          <WrappedYearSelector
            v-if="yearOptions.length > 1"
            v-model="year"
            :years="yearOptions"
          />
          <div v-else class="wrapped-label text-xs text-[#00000066]">{{ year }}年</div>
        </div>
        <div class="relative mt-1 h-[1px] w-16 ml-auto bg-gradient-to-l from-[#07C160]/40 to-transparent"></div>
      </div>
    </div>

    <div
      class="relative h-full w-full will-change-transform transition-transform duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]"
      :class="deckTrackClass"
      :style="trackStyle"
    >
      <!-- Cover -->
      <section class="w-full" :style="slideStyle">
        <div class="h-full w-full relative">
          <WrappedHero
            :year="year"
            :card-manifests="report?.cards || []"
            variant="slide"
            class="h-full w-full"
          />
        </div>
      </section>

      <!-- Cards -->
      <section
        v-for="(c, idx) in report?.cards || []"
        :key="`${c?.id ?? idx}`"
        class="w-full"
        :style="slideStyle"
      >
        <WrappedCardShell
          v-if="!c || (c.status !== 'ok' && !(c.kind === 'global/bento_summary' || c.id === 7))"
          :card-id="Number(c?.id || (idx + 1))"
          :title="c?.title || '正在生成…'"
          :narrative="c?.status === 'error' ? '生成失败' : (c?.status === 'loading' ? '正在生成本页数据…' : '进入该页后将开始生成')"
          variant="slide"
          class="h-full w-full"
        >
          <div v-if="c?.status === 'error'" class="text-sm text-[#7F7F7F]">
            <div class="wrapped-body text-sm text-red-600 whitespace-pre-wrap">{{ c?.error || '未知错误' }}</div>
            <button
              type="button"
              class="mt-4 inline-flex items-center justify-center px-4 py-2 rounded-lg bg-[#07C160] text-white text-sm wrapped-label hover:bg-[#06AD56] transition"
              @click="retryCard(Number(c?.id))"
            >
              重试
            </button>
          </div>

          <div v-else class="flex items-center gap-3 text-sm text-[#7F7F7F]">
            <svg class="w-4 h-4 animate-spin text-[#07C160]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
              />
            </svg>
            <div class="wrapped-body text-sm text-[#7F7F7F]">
              <span v-if="c?.status === 'idle'">翻到此页后开始生成…</span>
              <span v-else>正在生成本页数据…</span>
            </div>
          </div>
        </WrappedCardShell>

        <Card00GlobalOverview
          v-else-if="c && (c.kind === 'global/overview' || c.id === 0)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card01CyberSchedule
          v-else-if="c && (c.kind === 'time/weekday_hour_heatmap' || c.id === 1)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card02MessageChars
          v-else-if="c && (c.kind === 'text/message_chars' || c.id === 2)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card06KeywordsWordCloud
          v-else-if="c && (c.kind === 'text/keywords_wordcloud' || c.id === 6)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card03ReplySpeed
          v-else-if="c && (c.kind === 'chat/reply_speed' || c.id === 3)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card04MonthlyBestFriendsWall
          v-else-if="c && (c.kind === 'chat/monthly_best_friends_wall' || c.id === 4)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card04EmojiUniverse
          v-else-if="c && (c.kind === 'emoji/annual_universe' || c.id === 5)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <Card07BentoSummary
          v-else-if="c && (c.kind === 'global/bento_summary' || c.id === 7)"
          :card="c"
          variant="slide"
          class="h-full w-full"
        />
        <WrappedCardShell
          v-else
          :card-id="Number(c?.id || (idx + 1))"
          :title="c?.title || '暂不支持的卡片'"
          :narrative="`kind=${c?.kind} / id=${c?.id}`"
          variant="slide"
          class="h-full w-full"
        >
          <div class="text-sm text-[#7F7F7F]">
            该卡片暂未实现，后续会逐步补齐。
          </div>
        </WrappedCardShell>
      </section>
    </div>

  </div>
</template>

<script setup>
import { useApi } from '~/composables/useApi'

useHead({
  title: '年度总结 · WeChat Wrapped',
  bodyAttrs: { style: 'overflow: hidden; overscroll-behavior: none;' }
})

const api = useApi()
const route = useRoute()
const router = useRouter()

const queryYear = Number(route.query?.year)
const defaultYear = new Date().getFullYear() - 1
const year = ref(Number.isFinite(queryYear) ? queryYear : defaultYear)
// 分享视图不展示账号信息：默认让后端自动选择；需要指定时可用 query ?account=wxid_xxx
const account = ref(typeof route.query?.account === 'string' ? route.query.account : '')

 const accounts = ref([])
 const accountsLoading = ref(true)

const loading = ref(false)
const error = ref('')
const report = ref(null)

// If user clicks "强制刷新", pass refresh=true for subsequent per-card requests in this session.
const refreshCards = ref(false)
let reportToken = 0

const availableYears = ref([])
const yearOptions = computed(() => {
  const ys = Array.isArray(availableYears.value) ? availableYears.value : []
  const out = ys
    .map((x) => Number(x))
    .filter((x) => Number.isFinite(x))
    .sort((a, b) => b - a)
  // Fallback to current year if backend couldn't provide a list yet.
  return out.length > 0 ? out : [year.value]
})

const deckEl = ref(null)
const viewportHeight = ref(0)
const activeIndex = ref(0)
const navLocked = ref(false)
const wheelAcc = ref(0)

// 允许子卡片隐藏 deck 顶部 UI（如关键词卡片 storm 阶段）
const deckChromeHidden = ref(false)
provide('deckChromeHidden', deckChromeHidden)

let navUnlockTimer = null
let deckResizeObserver = null

const slides = computed(() => {
  const cards = Array.isArray(report.value?.cards) ? report.value.cards : []
  const out = [{ key: 'cover' }]
  for (const c of cards) out.push({ key: `card-${c?.id ?? out.length}` })
  return out
})

const currentBg = computed(() => '#F3FFF8')
const deckTrackClass = computed(() => 'z-10')

const applyViewportBg = () => {
  if (!import.meta.client) return
  const bg = currentBg.value
  document.documentElement.style.backgroundColor = bg
  document.body.style.backgroundColor = bg
}

const slideStyle = computed(() => (
  viewportHeight.value > 0 ? { height: `${viewportHeight.value}px` } : { height: '100%' }
))

const trackStyle = computed(() => {
  const dy = viewportHeight.value > 0 ? -activeIndex.value * viewportHeight.value : 0
  return { transform: `translate3d(0, ${dy}px, 0)` }
})

const clampIndex = (i) => {
  const max = Math.max(0, slides.value.length - 1)
  return Math.min(Math.max(0, i), max)
}

const goTo = (i) => {
  activeIndex.value = clampIndex(i)
}

const goBack = async () => {
  await router.push('/chat')
}

const next = () => goTo(activeIndex.value + 1)
const prev = () => goTo(activeIndex.value - 1)

const lockNav = () => {
  navLocked.value = true
  if (navUnlockTimer) clearTimeout(navUnlockTimer)
  navUnlockTimer = setTimeout(() => { navLocked.value = false }, 650)
}

const isEditable = (t) => {
  const el = t
  if (!el || !(el instanceof Element)) return false
  const tag = el.tagName
  return el.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

const findScrollableYAncestor = (t) => {
  let el = t instanceof Element ? t : null
  while (el && el !== deckEl.value) {
    const style = window.getComputedStyle(el)
    const oy = style.overflowY
    const scrollable = (oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 1
    if (scrollable) return el
    el = el.parentElement
  }
  return null
}

const onWheel = (e) => {
  if (!slides.value || slides.value.length <= 1) return
  if (isEditable(e.target)) return

  // 若在可水平滚动区域且用户在做水平滚动手势，则不拦截
  const scrollX = e.target instanceof Element ? e.target.closest('[data-wrapped-scroll-x]') : null
  if (scrollX && scrollX.scrollWidth > scrollX.clientWidth + 1) {
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
  }

  const scrollY = findScrollableYAncestor(e.target)
  if (scrollY) {
    const canUp = scrollY.scrollTop > 0
    const canDown = scrollY.scrollTop + scrollY.clientHeight < scrollY.scrollHeight - 1
    if ((e.deltaY < 0 && canUp) || (e.deltaY > 0 && canDown)) return
  }

  // 进入 deck 逻辑：阻止默认滚动，转为“翻页”
  e.preventDefault()
  if (navLocked.value) return

  wheelAcc.value += e.deltaY
  const threshold = 80
  if (Math.abs(wheelAcc.value) < threshold) return

  if (wheelAcc.value > 0) next()
  else prev()

  wheelAcc.value = 0
  lockNav()
}

const onKeydown = (e) => {
  if (!slides.value || slides.value.length <= 1) return
  if (isEditable(e.target)) return

  if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ') {
    e.preventDefault()
    next()
    lockNav()
    return
  }
  if (e.key === 'ArrowUp' || e.key === 'PageUp') {
    e.preventDefault()
    prev()
    lockNav()
    return
  }
  if (e.key === 'Home') {
    e.preventDefault()
    goTo(0)
    lockNav()
    return
  }
  if (e.key === 'End') {
    e.preventDefault()
    goTo(slides.value.length - 1)
    lockNav()
  }
}

let touchStartY = 0
const onTouchStart = (e) => {
  if (!slides.value || slides.value.length <= 1) return
  touchStartY = e.touches?.[0]?.clientY ?? 0
}
const onTouchEnd = (e) => {
  if (!slides.value || slides.value.length <= 1) return
  const endY = e.changedTouches?.[0]?.clientY ?? 0
  const dy = endY - touchStartY
  if (Math.abs(dy) < 50) return
  if (dy < 0) next()
  else prev()
  lockNav()
}

const updateViewport = () => {
  const h = Math.round(deckEl.value?.getBoundingClientRect?.().height || deckEl.value?.clientHeight || window.innerHeight || 0)
  if (!h) return
  // Avoid endless reflows from 1px rounding errors (especially in Electron).
  if (Math.abs(viewportHeight.value - h) > 1) viewportHeight.value = h
}

const loadAccounts = async () => {
  accountsLoading.value = true
  try {
    const resp = await api.listChatAccounts()
    accounts.value = Array.isArray(resp?.accounts) ? resp.accounts : []
  } catch (e) {
    accounts.value = []
  } finally {
    accountsLoading.value = false
  }
}

const ensureCardLoaded = async (cardId) => {
  const id = Number(cardId)
  if (!Number.isFinite(id)) return
  const token = reportToken

  const cards = report.value?.cards
  if (!Array.isArray(cards)) return

  const idx = cards.findIndex((x) => Number(x?.id) === id)
  if (idx < 0) return

  const cur = cards[idx]
  if (cur?.status === 'ok' || cur?.status === 'loading') return

  // Mark as loading immediately so the UI can show a spinner on this slide.
  cards[idx] = {
    ...(cur || {}),
    id,
    title: cur?.title || `Card ${id}`,
    scope: cur?.scope || 'global',
    category: cur?.category || 'A',
    kind: cur?.kind || '',
    status: 'loading',
    error: ''
  }

  try {
    const resp = await api.getWrappedAnnualCard(id, {
      year: year.value,
      account: account.value || null,
      refresh: !!refreshCards.value
    })

    // Ignore stale responses after year/account reload.
    if (token !== reportToken) return

    if (resp && Number(resp?.id) === id) {
      cards[idx] = resp
    } else {
      // Best-effort fallback (shouldn't happen unless backend shape changes).
      cards[idx] = resp || cards[idx]
    }
  } catch (e) {
    if (token !== reportToken) return
    const msg = e?.message || String(e)
    cards[idx] = {
      ...(cur || {}),
      id,
      title: cur?.title || `Card ${id}`,
      scope: cur?.scope || 'global',
      category: cur?.category || 'A',
      kind: cur?.kind || '',
      status: 'error',
      narrative: '',
      data: null,
      error: msg
    }
  }
}

const retryCard = async (cardId) => {
  await ensureCardLoaded(cardId)
}

provide('wrappedRetryCard', retryCard)

const reload = async (forceRefresh = false, preserveIndex = false) => {
  const token = ++reportToken
  const keepIndex = preserveIndex ? activeIndex.value : 0
  if (!preserveIndex) activeIndex.value = 0
  error.value = ''
  loading.value = true
  refreshCards.value = !!forceRefresh
  try {
    const resp = await api.getWrappedAnnualMeta({
      year: year.value,
      account: account.value || null,
      refresh: !!forceRefresh
    })

    if (token !== reportToken) return

    const manifest = Array.isArray(resp?.cards) ? resp.cards : []
    report.value = {
      ...(resp || {}),
      cards: manifest.map((m, i) => ({
        id: Number(m?.id ?? i),
        title: String(m?.title || `Card ${m?.id ?? i}`),
        scope: m?.scope || 'global',
        category: m?.category || 'A',
        kind: String(m?.kind || ''),
        status: 'idle',
        narrative: '',
        data: null,
        error: ''
      }))
    }

    // Backend may snap the year to the latest available year (only years with data are selectable).
    const respYear = Number(resp?.year)
    if (Number.isFinite(respYear)) {
      year.value = respYear
      try {
        await router.replace({ query: { ...route.query, year: String(respYear) } })
      } catch {
        // ignore
      }
    }

    availableYears.value = Array.isArray(resp?.availableYears) ? resp.availableYears : []

    if (preserveIndex) {
      activeIndex.value = clampIndex(keepIndex)
      const cardIdx = Number(activeIndex.value) - 1
      if (cardIdx >= 0) {
        const id = Number(report.value?.cards?.[cardIdx]?.id)
        if (Number.isFinite(id)) void ensureCardLoaded(id)
      }
    }
  } catch (e) {
    if (token !== reportToken) return
    report.value = null
    error.value = e?.message || String(e)
  } finally {
    if (token !== reportToken) return
    loading.value = false
  }
}

// Lazy-load the active slide's card data.
watch(activeIndex, (i) => {
  const cardIdx = Number(i) - 1
  if (!Number.isFinite(cardIdx) || cardIdx < 0) return
  const c = report.value?.cards?.[cardIdx]
  const id = Number(c?.id)
  if (!Number.isFinite(id)) return
  void ensureCardLoaded(id)
})

onMounted(async () => {
  applyViewportBg()
  updateViewport()
  if (import.meta.client && typeof ResizeObserver !== 'undefined' && deckEl.value) {
    deckResizeObserver = new ResizeObserver(() => {
      updateViewport()
    })
    deckResizeObserver.observe(deckEl.value)
  }
  window.addEventListener('resize', updateViewport)
  // passive:false 才能 preventDefault，避免外层容器产生滚动/回弹
  deckEl.value?.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('keydown', onKeydown)
  deckEl.value?.addEventListener('touchstart', onTouchStart, { passive: true })
  deckEl.value?.addEventListener('touchend', onTouchEnd, { passive: true })

  await loadAccounts()
  // Auto-generate once if we already have decrypted accounts, to match "one click" expectations.
  if (accounts.value.length > 0) {
    await reload()
  }
})

onBeforeUnmount(() => {
  if (import.meta.client) {
    document.documentElement.style.backgroundColor = ''
    document.body.style.backgroundColor = ''
  }
  deckResizeObserver?.disconnect()
  deckResizeObserver = null
  window.removeEventListener('resize', updateViewport)
  deckEl.value?.removeEventListener('wheel', onWheel)
  window.removeEventListener('keydown', onKeydown)
  deckEl.value?.removeEventListener('touchstart', onTouchStart)
  deckEl.value?.removeEventListener('touchend', onTouchEnd)
  if (navUnlockTimer) clearTimeout(navUnlockTimer)
})

watch(
  () => slides.value.length,
  () => {
    // Slide 数量变化（重新生成/新增卡片）时，确保 index 合法
    activeIndex.value = clampIndex(activeIndex.value)
  }
)

// 监听年份变化（由 WrappedYearSelector v-model 触发）
watch(year, async (newYear, oldYear) => {
  if (newYear === oldYear) return
  // 仅允许切换到后端报告有数据的年份
  if (Array.isArray(availableYears.value) && availableYears.value.length > 0 && !availableYears.value.includes(newYear)) {
    year.value = oldYear
    return
  }
  await reload(false, true)
})
</script>

<style>
.wrapped-deck-root {
  height: 100dvh;
  min-height: 100dvh;
}

.wechat-desktop .wechat-desktop-content > .wrapped-deck-root {
  height: 100%;
  min-height: 100%;
}
</style>
