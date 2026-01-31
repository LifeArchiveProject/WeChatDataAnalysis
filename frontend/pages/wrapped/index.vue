<template>
  <div
    ref="deckEl"
    class="relative h-screen w-full overflow-hidden transition-colors duration-500"
    :class="{ 'wrapped-retro': retro }"
    :style="{ backgroundColor: currentBg }"
  >
    <!-- PPT 风格：单张卡片占据全页面，鼠标滚轮切换 -->
    <WrappedDeckBackground />
    <WrappedCRTOverlay v-if="retro" />

    <!-- 左上角：刷新 + 复古模式开关 -->
    <div class="absolute top-6 left-6 z-20 select-none">
      <div class="flex items-center gap-3">
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

        <button
          type="button"
          class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent transition disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30"
          :class="retro ? 'text-[#07C160] hover:bg-[#07C160]/10' : 'text-[#00000055] hover:bg-[#000000]/5'"
          :aria-pressed="retro ? 'true' : 'false'"
          aria-label="复古模式（像素字体 + CRT 滤镜）"
          title="复古模式：像素字体 + CRT 滤镜"
          @click="retro = !retro"
        >
          <img
            src="/assets/images/wechat-audio-dark.png"
            class="w-4 h-4 transition"
            :style="{ filter: retro ? 'none' : 'grayscale(1)', opacity: retro ? '1' : '0.55' }"
            alt=""
            aria-hidden="true"
            draggable="false"
          />
        </button>
      </div>

      <div v-if="error" class="mt-2 pointer-events-auto bg-white/90 backdrop-blur rounded-xl border border-red-200 px-3 py-2">
        <div class="wrapped-label text-xs text-red-700">生成失败</div>
        <div class="mt-1 wrapped-body text-xs text-red-600 whitespace-pre-wrap">{{ error }}</div>
      </div>
    </div>

    <!-- 右上角：年份（仅可切换有数据的年份） -->
    <div class="absolute top-6 right-6 z-20 pointer-events-auto select-none">
      <div class="relative">
        <div class="absolute -inset-6 rounded-full bg-[#07C160]/10 blur-2xl"></div>
        <div class="relative flex justify-end">
          <div class="relative inline-flex items-center">
            <select
              class="pointer-events-auto appearance-none bg-transparent pr-5 pl-0 py-0.5 rounded-md wrapped-label text-xs text-[#00000066] text-right focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 hover:bg-[#000000]/5 transition disabled:opacity-70 disabled:cursor-default"
              :disabled="loading || accountsLoading || yearOptions.length <= 1"
              :value="String(year)"
              @change="setYear($event.target.value)"
            >
              <option v-for="y in yearOptions" :key="y" :value="String(y)">{{ y }}年</option>
            </select>
            <svg
              v-if="yearOptions.length > 1"
              class="pointer-events-none absolute right-1 w-3 h-3 text-[#00000066]"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fill-rule="evenodd"
                d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 10.94l3.71-3.71a.75.75 0 1 1 1.06 1.06l-4.24 4.24a.75.75 0 0 1-1.06 0L5.21 8.29a.75.75 0 0 1 .02-1.08z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
        </div>
        <div class="relative mt-1 h-[1px] w-16 ml-auto bg-gradient-to-l from-[#07C160]/40 to-transparent"></div>
      </div>
    </div>

    <div
      class="relative z-10 h-full w-full will-change-transform transition-transform duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]"
      :style="trackStyle"
    >
      <!-- Cover -->
      <section class="w-full" :style="slideStyle">
        <div class="h-full w-full relative">
          <WrappedHero :year="year" variant="slide" class="h-full w-full" />
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
          v-if="!c || c.status !== 'ok'"
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

const year = ref(Number(route.query?.year) || new Date().getFullYear())
// 分享视图不展示账号信息：默认让后端自动选择；需要指定时可用 query ?account=wxid_xxx
const account = ref(typeof route.query?.account === 'string' ? route.query.account : '')

// Retro mode: pixel font + CRT overlay.
const retro = ref(true)

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
let navUnlockTimer = null

const WRAPPED_BG = '#F3FFF8'

const slides = computed(() => {
  const cards = Array.isArray(report.value?.cards) ? report.value.cards : []
  const coverBg = WRAPPED_BG
  const out = [{ key: 'cover', bg: coverBg }]
  for (const c of cards) out.push({ key: `card-${c?.id ?? out.length}`, bg: cardBg(c) })
  return out
})

const currentBg = computed(() => slides.value?.[activeIndex.value]?.bg || '#ffffff')

const slideStyle = computed(() => (
  viewportHeight.value > 0 ? { height: `${viewportHeight.value}px` } : { height: '100%' }
))

const trackStyle = computed(() => {
  const dy = viewportHeight.value > 0 ? -activeIndex.value * viewportHeight.value : 0
  return { transform: `translate3d(0, ${dy}px, 0)` }
})

const cardBg = (card) => {
  // 当前统一使用同一套背景色（后续扩展更多卡片时再按 id/kind 细分）。
  void card
  return WRAPPED_BG
}

const clampIndex = (i) => {
  const max = Math.max(0, slides.value.length - 1)
  return Math.min(Math.max(0, i), max)
}

const goTo = (i) => {
  activeIndex.value = clampIndex(i)
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
  const h = deckEl.value?.clientHeight || window.innerHeight || 0
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

const reload = async (forceRefresh = false) => {
  const token = ++reportToken
  activeIndex.value = 0
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

const setYear = async (y) => {
  const ny = Number(y)
  if (!Number.isFinite(ny)) return
  if (ny === year.value) return
  // Only allow switching to years that the backend reported as having data.
  if (Array.isArray(availableYears.value) && availableYears.value.length > 0 && !availableYears.value.includes(ny)) return
  year.value = ny
  await reload()
}

onMounted(() => {
  try {
    const saved = localStorage.getItem('wrapped_retro')
    if (saved === '0') retro.value = false
    if (saved === '1') retro.value = true
  } catch {
    // ignore
  }
})

watch(retro, (v) => {
  try {
    localStorage.setItem('wrapped_retro', v ? '1' : '0')
  } catch {
    // ignore
  }
})

onMounted(async () => {
  updateViewport()
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
</script>
