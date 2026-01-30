<template>
  <!-- PPT 风格：单张卡片占据全页面，鼠标滚轮切换 -->
  <div
    ref="deckEl"
    class="relative h-screen w-full overflow-hidden transition-colors duration-500"
    :style="{ backgroundColor: currentBg }"
  >
    <WrappedDeckBackground />

    <!-- 年份固定在右上角（类似 PPT 页眉），避免把年份写进标题里 -->
    <div class="absolute top-6 right-6 z-20 pointer-events-none select-none">
      <div class="relative">
        <div class="absolute -inset-6 rounded-full bg-[#07C160]/10 blur-2xl"></div>
        <div class="relative text-xs font-semibold tracking-[0.28em] text-[#00000066] text-right">
          {{ year }}年
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

           <!-- 生成面板：仅在尚未生成报告时显示（分享视图隐藏账号相关内容） -->
           <div v-if="bootstrapped && !report" class="absolute left-0 right-0 bottom-0 pb-8">
             <div class="max-w-5xl mx-auto px-6 sm:px-8 space-y-3">
               <div v-if="error" class="bg-white/90 backdrop-blur rounded-2xl border border-red-200 p-5">
                 <div class="text-red-700 font-semibold">生成失败</div>
                 <div class="mt-2 text-sm text-red-600 whitespace-pre-wrap">{{ error }}</div>
                <div class="mt-4 text-xs text-[#7F7F7F]">
                  提示：请确认已完成解密，并且后端服务正在运行（默认 http://127.0.0.1:8000）。
                </div>
              </div>

              <WrappedControls
                :accounts="accounts"
                :accounts-loading="accountsLoading"
                :loading="loading"
                :model-year="year"
                :model-account="account"
                :model-refresh="refresh"
                :show-account="false"
                @update:year="(v) => { year.value = v }"
                @update:account="(v) => { account.value = v }"
                @update:refresh="(v) => { refresh.value = v }"
                @reload="reload"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- Cards -->
      <section
        v-for="(c, idx) in report?.cards || []"
        :key="`${c?.id ?? idx}`"
        class="w-full"
        :style="slideStyle"
      >
        <Card01CyberSchedule
          v-if="c && (c.kind === 'time/weekday_hour_heatmap' || c.id === 1)"
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

const year = ref(Number(route.query?.year) || new Date().getFullYear())
// 分享视图不展示账号信息：默认让后端自动选择；需要指定时可用 query ?account=wxid_xxx
const account = ref(typeof route.query?.account === 'string' ? route.query.account : '')
const refresh = ref(false)

 const accounts = ref([])
 const accountsLoading = ref(true)

// Avoid flashing the "year card" controls before the initial auto-load finishes.
const bootstrapped = ref(false)

 const loading = ref(false)
 const error = ref('')
 const report = ref(null)

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

const reload = async () => {
  activeIndex.value = 0
  error.value = ''
  loading.value = true
  try {
    const resp = await api.getWrappedAnnual({
      year: year.value,
      account: account.value || null,
      refresh: !!refresh.value
    })
    report.value = resp || null
  } catch (e) {
    report.value = null
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
  // passive:false 才能 preventDefault，避免外层容器产生滚动/回弹
  deckEl.value?.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('keydown', onKeydown)
  deckEl.value?.addEventListener('touchstart', onTouchStart, { passive: true })
  deckEl.value?.addEventListener('touchend', onTouchEnd, { passive: true })

  try {
    await loadAccounts()
    // Auto-generate once if we already have decrypted accounts, to match "one click" expectations.
    if (accounts.value.length > 0) {
      await reload()
    }
  } finally {
    bootstrapped.value = true
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
