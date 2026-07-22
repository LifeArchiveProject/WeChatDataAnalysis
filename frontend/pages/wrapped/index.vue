<template>
  <div
    ref="deckEl"
    class="wrapped-deck-root relative h-screen w-full overflow-hidden transition-colors duration-500"
    :class="{ 'wrapped-privacy': privacyMode }"
    :style="{ backgroundColor: currentBg }"
    role="region"
    aria-roledescription="carousel"
    aria-label="微信年度总结"
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
        <ErrorNotice :message="error" compact class="mt-1 wrapped-body text-xs text-red-600" />
      </div>
    </div>

    <!-- 右上角：隐私模式 + 年份选择器（主题化） -->
    <div v-show="!deckChromeHidden" class="absolute top-6 right-6 z-20 pointer-events-auto select-none transition-opacity duration-300">
      <div class="relative">
        <div class="absolute -inset-6 rounded-full bg-[#07C160]/10 blur-2xl"></div>
        <div class="relative flex items-center justify-end gap-3">
          <button
            type="button"
            class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent text-[#07C160] hover:bg-[#07C160]/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 transition"
            :aria-label="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
            :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
            @click="privacyStore.toggle"
          >
            <svg
              class="w-4 h-4"
              :class="privacyMode ? 'text-[#07C160]' : 'text-[#00000080]'"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              aria-hidden="true"
            >
              <path
                v-if="privacyMode"
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
              />
              <path
                v-else
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
              />
              <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
            </svg>
          </button>

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

    <!-- 翻页播报（供屏幕阅读器） -->
    <div class="sr-only" aria-live="polite">{{ slideAnnouncement }}</div>

    <!-- 右侧进度圆点导航 -->
    <WrappedProgressDots
      v-show="!deckChromeHidden && dotItems.length > 1"
      :items="dotItems"
      :active-index="activeIndex"
      @select="onDotSelect"
    />

    <!-- 右下角：保存当前页为图片 -->
    <button
      v-show="!deckChromeHidden && report"
      type="button"
      class="absolute bottom-6 right-6 z-20 pointer-events-auto inline-flex items-center justify-center w-10 h-10 rounded-full bg-white/90 backdrop-blur border border-[#07C160]/20 text-[#07C160] shadow-sm hover:bg-[#07C160]/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 disabled:opacity-60 disabled:cursor-not-allowed transition"
      :disabled="exporting"
      aria-label="保存当前页为图片"
      title="保存当前页为图片"
      @click="exportActiveSlide"
    >
      <svg v-if="exporting" class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
      </svg>
      <svg
        v-else
        class="w-4 h-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <path d="M7 10l5 5 5-5" />
        <path d="M12 15V3" />
      </svg>
    </button>

    <div
      ref="trackEl"
      class="relative h-full w-full will-change-transform transition-transform ease-[cubic-bezier(0.22,1,0.36,1)]"
      :class="deckTrackClass"
      :style="trackStyle"
    >
      <!-- Cover -->
      <section class="w-full" :style="slideStyle">
        <div class="h-full w-full relative">
          <WrappedHero
            :year="year"
            :card-manifests="report?.cards || []"
            :is-active="activeIndex === 0"
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
            <ErrorNotice :message="c?.error || '未知错误'" compact class="wrapped-body text-sm text-red-600" />
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
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card01CyberSchedule
          v-else-if="c && (c.kind === 'time/weekday_hour_heatmap' || c.id === 1)"
          :card="c"
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card02MessageChars
          v-else-if="c && (c.kind === 'text/message_chars' || c.id === 2)"
          :card="c"
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card06KeywordsWordCloud
          v-else-if="c && (c.kind === 'text/keywords_wordcloud' || c.id === 6)"
          :card="c"
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card03ReplySpeed
          v-else-if="c && (c.kind === 'chat/reply_speed' || c.id === 3)"
          :card="c"
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card04MonthlyBestFriendsWall
          v-else-if="c && (c.kind === 'chat/monthly_best_friends_wall' || c.id === 4)"
          :card="c"
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card04EmojiUniverse
          v-else-if="c && (c.kind === 'emoji/annual_universe' || c.id === 5)"
          :card="c"
          :is-active="activeIndex === idx + 1"
          variant="slide"
          class="h-full w-full"
        />
        <Card07BentoSummary
          v-else-if="c && (c.kind === 'global/bento_summary' || c.id === 7)"
          :card="c"
          :is-active="activeIndex === idx + 1"
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
import { storeToRefs } from 'pinia'
import { usePrivacyStore } from '~/stores/privacy'
import { useReducedMotion } from '~/composables/useReducedMotion'

useHead({
  title: '年度总结 · WeChat Wrapped',
  bodyAttrs: { style: 'overflow: hidden; overscroll-behavior: none;' }
})

const api = useApi()
const route = useRoute()
const router = useRouter()

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

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
// reload 中后端 snap 年份回写 year 时置位，抑制 watch(year) 的二次 reload。
let suppressYearWatch = false

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
const trackEl = ref(null)
const viewportHeight = ref(0)
const activeIndex = ref(0)
const navLocked = ref(false)
const wheelAcc = ref(0)
let lastWheelAt = 0

const reducedMotion = useReducedMotion()

// 触屏/笔跟手拖拽状态（鼠标仍走滚轮翻页）
const dragging = ref(false)
const dragOffset = ref(0)
let dragPointerId = null
let dragStartY = 0
let dragLastY = 0
let dragLastT = 0
let dragVelocity = 0 // px/ms，向下为正

const exporting = ref(false)

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

// 年度总结沿用旧版浅绿色底色，避免继承聊天页灰底或引导页绿底。
const currentBg = '#F3FFF8'
// reduced-motion 时把 700ms 翻页过渡降为 150ms
const deckTrackClass = computed(() => [
  'z-10',
  reducedMotion.value ? 'duration-150' : 'duration-700'
])

const applyViewportBg = () => {
  if (!import.meta.client) return
  document.documentElement.style.backgroundColor = currentBg
  document.body.style.backgroundColor = currentBg
}

const slideStyle = computed(() => (
  viewportHeight.value > 0 ? { height: `${viewportHeight.value}px` } : { height: '100%' }
))

const trackStyle = computed(() => {
  const base = viewportHeight.value > 0 ? -activeIndex.value * viewportHeight.value : 0
  const style = { transform: `translate3d(0, ${base + dragOffset.value}px, 0)` }
  // 拖拽期间关闭过渡以保证跟手；松手后恢复类上的过渡完成收尾/回弹
  if (dragging.value) style.transition = 'none'
  return style
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

// 进度圆点数据：封面 + 各卡片（标题用于 tooltip，loading 用于细环 spinner）
const dotItems = computed(() => {
  const cards = Array.isArray(report.value?.cards) ? report.value.cards : []
  return [
    { title: '封面', loading: false },
    ...cards.map((c, i) => ({
      title: String(c?.title || `第 ${i + 2} 页`),
      loading: c?.status === 'loading'
    }))
  ]
})

const onDotSelect = (i) => {
  goTo(i)
  lockNav()
}

// 翻页后播报给屏幕阅读器的文案
const slideAnnouncement = computed(() => {
  const item = dotItems.value[activeIndex.value]
  return `第 ${activeIndex.value + 1} 页 · ${item?.title || ''}`
})

// 导出当前 slide 为 PNG（html-to-image 按需加载）
const exportActiveSlide = async () => {
  if (exporting.value) return
  const el = trackEl.value?.children?.[activeIndex.value]
  if (!el) return
  exporting.value = true
  try {
    const { toPng } = await import('html-to-image')
    const dataUrl = await toPng(el, { pixelRatio: 2, backgroundColor: currentBg })
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = `wechat-wrapped-${year.value}-${activeIndex.value + 1}.png`
    a.click()
  } catch (e) {
    window.alert(`保存图片失败：${e?.message || e}`)
  } finally {
    exporting.value = false
  }
}

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

  // 慢滚间隔过久时清零累积量，避免跨时间误触发翻页
  const now = e.timeStamp || Date.now()
  if (now - lastWheelAt > 160) wheelAcc.value = 0
  lastWheelAt = now

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

  // Shift+左右键留给年份选择器（WrappedYearSelector）
  if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ' || (e.key === 'ArrowRight' && !e.shiftKey)) {
    e.preventDefault()
    next()
    lockNav()
    return
  }
  if (e.key === 'ArrowUp' || e.key === 'PageUp' || (e.key === 'ArrowLeft' && !e.shiftKey)) {
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

// —— 触屏/笔全程跟手拖拽翻页 ——
const onPointerDown = (e) => {
  // 鼠标仍走滚轮翻页，只接管触屏/笔
  if (e.pointerType !== 'touch' && e.pointerType !== 'pen') return
  if (!slides.value || slides.value.length <= 1) return
  if (dragPointerId !== null) return
  if (isEditable(e.target)) return
  // 卡内自带 pointer 拖拽（如好友墙拍立得）已 preventDefault，deck 不抢手势；
  // data-deck-nodrag 供卡内拖拽区显式声明豁免。
  if (e.defaultPrevented) return
  if (e.target instanceof Element && e.target.closest('[data-deck-nodrag]')) return

  // 复用 onWheel 的内部可滚动区检测：还能滚的区域交还给原生滚动
  const scrollX = e.target instanceof Element ? e.target.closest('[data-wrapped-scroll-x]') : null
  if (scrollX && scrollX.scrollWidth > scrollX.clientWidth + 1) return
  const scrollY = findScrollableYAncestor(e.target)
  if (scrollY && (scrollY.scrollTop > 0 || scrollY.scrollTop + scrollY.clientHeight < scrollY.scrollHeight - 1)) return

  dragPointerId = e.pointerId
  dragStartY = e.clientY
  dragLastY = e.clientY
  dragLastT = e.timeStamp
  dragVelocity = 0
  dragOffset.value = 0
  dragging.value = true
  try {
    deckEl.value?.setPointerCapture?.(e.pointerId)
  } catch {
    // 部分环境（如旧 WebView）不支持指针捕获，降级为普通监听
  }
}

const onPointerMove = (e) => {
  if (!dragging.value || e.pointerId !== dragPointerId) return
  const dy = e.clientY - dragStartY
  const dt = e.timeStamp - dragLastT
  if (dt > 0) dragVelocity = (e.clientY - dragLastY) / dt
  dragLastY = e.clientY
  dragLastT = e.timeStamp

  // 首/末页越界拖拽加 0.35 阻尼
  const overFirst = activeIndex.value <= 0 && dy > 0
  const overLast = activeIndex.value >= slides.value.length - 1 && dy < 0
  dragOffset.value = (overFirst || overLast) ? dy * 0.35 : dy
}

// commit=false（pointercancel）时仅回弹不翻页
const finishDrag = (commit, upTimeStamp = 0) => {
  if (!dragging.value) return
  const dy = dragOffset.value
  dragging.value = false
  dragPointerId = null
  dragOffset.value = 0

  if (!commit) return
  // 手指停顿后释放：速度值已过期，视为 0，避免误翻页
  if (upTimeStamp && upTimeStamp - dragLastT > 100) dragVelocity = 0
  const threshold = Math.max(1, viewportHeight.value) * 0.25
  const byDistance = Math.abs(dy) > threshold
  // 速度判定加最小位移门槛，抖动轻点不触发翻页
  const byVelocity = Math.abs(dragVelocity) > 0.5 && Math.abs(dy) > 15
  if (!byDistance && !byVelocity) return

  // 距离达标看位移方向，否则看松手瞬间速度方向（上滑=下一页）
  const dir = byDistance ? (dy < 0 ? 1 : -1) : (dragVelocity < 0 ? 1 : -1)
  goTo(activeIndex.value + dir)
  lockNav()
}

const onPointerUp = (e) => {
  if (e.pointerId !== dragPointerId) return
  finishDrag(true, e.timeStamp)
}

const onPointerCancel = (e) => {
  if (e.pointerId !== dragPointerId) return
  finishDrag(false)
}

// 拖拽期间阻止浏览器接管触摸手势，否则会触发 pointercancel 丢失跟手
const onDeckTouchMove = (e) => {
  if (dragging.value) e.preventDefault()
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

// slide 索引 → 卡片数据加载（slide 0 为封面，无需加载）
const loadCardAtSlide = (slideIdx) => {
  const cardIdx = Number(slideIdx) - 1
  if (!Number.isFinite(cardIdx) || cardIdx < 0) return
  const id = Number(report.value?.cards?.[cardIdx]?.id)
  if (!Number.isFinite(id)) return
  void ensureCardLoaded(id)
}

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
      // 回写 snap 年份时抑制 watch(year)，避免二次 reload（双请求 + 卡片闪烁）
      if (respYear !== year.value) suppressYearWatch = true
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
      loadCardAtSlide(activeIndex.value)
    }
    // 报告就绪后立即预取第一张卡，封面翻下来时无需等待
    loadCardAtSlide(1)
  } catch (e) {
    if (token !== reportToken) return
    report.value = null
    error.value = e?.message || String(e)
  } finally {
    if (token !== reportToken) return
    loading.value = false
  }
}

// Lazy-load the active slide's card data. 同时 fire-and-forget 预取相邻卡，减少翻页等待。
watch(activeIndex, (i) => {
  // reload 进行中 manifest 尚未就绪，跳过（reload 末尾已有首卡预取）
  if (loading.value) return
  loadCardAtSlide(i)
  loadCardAtSlide(i + 1)
  loadCardAtSlide(i - 1)
})

onMounted(async () => {
  privacyStore.init()
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
  deckEl.value?.addEventListener('pointerdown', onPointerDown)
  deckEl.value?.addEventListener('pointermove', onPointerMove)
  deckEl.value?.addEventListener('pointerup', onPointerUp)
  deckEl.value?.addEventListener('pointercancel', onPointerCancel)
  // passive:false：拖拽期间 preventDefault 阻止浏览器把触摸手势判定为滚动
  deckEl.value?.addEventListener('touchmove', onDeckTouchMove, { passive: false })

  await loadAccounts()
  // Auto-generate once if we already have chat accounts (direct WCDB or legacy), to match "one click" expectations.
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
  deckEl.value?.removeEventListener('pointerdown', onPointerDown)
  deckEl.value?.removeEventListener('pointermove', onPointerMove)
  deckEl.value?.removeEventListener('pointerup', onPointerUp)
  deckEl.value?.removeEventListener('pointercancel', onPointerCancel)
  deckEl.value?.removeEventListener('touchmove', onDeckTouchMove)
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
  if (suppressYearWatch) {
    suppressYearWatch = false
    return
  }
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
