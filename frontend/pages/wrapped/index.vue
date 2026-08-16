<template>
  <WrappedStage :shell-bg="shellBg" :stage-class="privacyMode ? 'wrapped-privacy' : ''">
    <div
      ref="deckEl"
      class="wrapped-deck-root relative h-full w-full overflow-hidden transition-colors duration-500"
      :style="{ backgroundColor: stageBg }"
      role="region"
      aria-roledescription="carousel"
      aria-label="微信年度总结"
    >
    <!-- PPT 风格：单张卡片占据全页面，鼠标滚轮切换 -->
    <WrappedDeckBackground />

    <!-- 翻页播报（供屏幕阅读器） -->
    <div class="sr-only" aria-live="polite">{{ slideAnnouncement }}</div>

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
        class="w-full relative"
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

    <template #chrome>
      <!-- 排版调试叠层：/wrapped?debug=box 打开。逐层描边并标出左右余量，
           「到底是哪一层没居中」一眼可见，不用再靠截图猜。只在 dev 下可用。 -->
      <div v-if="debugBox" class="wf-debug" aria-hidden="true">
        <div v-for="b in debugBoxes" :key="b.name" class="wf-debug__box" :style="b.style">
          <span class="wf-debug__tag">{{ b.name }} · 左{{ b.gapL }} 右{{ b.gapR }} · 宽{{ b.w }}</span>
        </div>
      </div>

      <!-- 左上角：返回 + 刷新。挂在 host 上（舞台的兄弟）——进舞台会被 scale 缩到不可点，
           也会被一并拍进分享图。 -->
      <div v-show="!chromeHidden" class="absolute top-6 left-6 z-20 select-none transition-opacity duration-300">
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 transition"
            :class="deckDark ? 'text-[#4ADE80] hover:bg-white/10' : 'text-[#07C160] hover:bg-[#07C160]/10'"
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
            class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 disabled:opacity-60 disabled:cursor-not-allowed transition"
            :class="deckDark ? 'text-[#4ADE80] hover:bg-white/10' : 'text-[#07C160] hover:bg-[#07C160]/10'"
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
      <div v-show="!chromeHidden" class="absolute top-6 right-6 z-20 pointer-events-auto select-none transition-opacity duration-300">
        <div class="relative">
          <div class="absolute -inset-6 rounded-full bg-[#07C160]/10 blur-2xl"></div>
          <div class="relative flex items-center justify-end gap-3">
            <button
              type="button"
              class="pointer-events-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-transparent focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 transition"
              :class="deckDark ? 'hover:bg-white/10' : 'hover:bg-[#07C160]/10'"
              :aria-label="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
              :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
              @click="privacyStore.toggle"
            >
              <svg
                class="w-4 h-4"
                :class="privacyMode ? (deckDark ? 'text-[#4ADE80]' : 'text-[#07C160]') : (deckDark ? 'text-[#FFFFFF8C]' : 'text-[#00000080]')"
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

            <!-- 分享 · 画幅：右组的语义是「怎么呈现」——隐私改可见性、画幅改版面、年份改数据范围 -->
            <WrappedFrameMenu
              ref="frameMenuEl"
              v-model="frameId"
              :frames="stage.frames"
              :dark="deckDark"
              :exporting="exporting"
              :status-text="exportStatus"
              :status-tone="exportTone"
              :can-export="canExportImage"
              :page-count="slides.length"
              @export="exportCurrentFrame"
              @export-all="exportAllPages"
            />

            <WrappedYearSelector
              v-if="yearOptions.length > 1"
              v-model="year"
              :years="yearOptions"
              :dark="deckDark"
            />
            <div v-else class="wrapped-label text-xs" :class="deckDark ? 'text-[#FFFFFF66]' : 'text-[#00000066]'">{{ year }}年</div>
          </div>
          <div class="relative mt-1 h-[1px] w-16 ml-auto bg-gradient-to-l from-[#07C160]/40 to-transparent"></div>
        </div>
      </div>

      <!-- 导出进度。落点由 exportBadgePlacement 算在**舞台之外**的信箱边里：
           截图的 clip 就是 .wr-stage 的屏幕矩形，这条留白带不会入图，
           所以整个导出过程它都可以亮着（这是唯一能让用户看见进度的地方）。
           跟随窗口时舞台铺满 host、没有留白，placement 为 null，这一档不显示。 -->
      <Transition name="wr-exp">
        <div
          v-if="exportBadgeVisible"
          class="wr-exp"
          :class="deckDark ? 'wr-exp--dark' : ''"
          :style="exportBadgePlacement.style"
          role="status"
          aria-live="polite"
        >
          <span class="wr-exp__dot" aria-hidden="true"></span>
          <span class="wr-exp__text">{{ exportProgressText }}</span>
          <span v-if="exportProgressPct !== null" class="wr-exp__bar" aria-hidden="true">
            <i :style="{ width: `${exportProgressPct}%` }"></i>
          </span>
        </div>
      </Transition>
    </template>
  </WrappedStage>
</template>

<script setup>
import { useApi } from '~/composables/useApi'
import { storeToRefs } from 'pinia'
import { usePrivacyStore } from '~/stores/privacy'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { createWrappedStage } from '~/composables/useWrappedStage'
import { exportScale } from '~/lib/wrapped-stage'

useHead({
  title: '年度总结 · WeChat Wrapped',
  bodyAttrs: { style: 'overflow: hidden; overscroll-behavior: none;' }
})

const api = useApi()
const route = useRoute()
const router = useRouter()

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

// 画幅舞台：deck 不再等于浏览器视口，而是渲染进一个设计像素恒定的舞台盒。
// 默认 'fit'（跟随窗口），此时舞台 = host、scale 恒 1，与舞台化之前逐像素一致。
const stage = createWrappedStage()
const frameId = computed({
  get: () => stage.frameId.value,
  set: (v) => stage.setFrame(v)
})

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
// 轨道元素：批量导出要读它的**实际** transform，确认这一页真的翻到位了才截图
const trackEl = ref(null)
// 每张 slide 的高度 = 舞台设计高度（常量），不再实测窗口。
// ⚠️ 绝不能改回 getBoundingClientRect().height：那是**变换后**的视觉高度，
// 舞台缩放后会静默变成 h*scale，轨道位移比 slide 矮 scale 倍，翻页越翻越偏。
const slideHeight = computed(() => stage.design.value.h)
const activeIndex = ref(0)
const navLocked = ref(false)
// 批量导出接管翻页期间冻结一切用户翻页输入（滚轮/键盘/触屏拖拽）
const navFrozen = ref(false)
const wheelAcc = ref(0)
let lastWheelAt = 0
// 本次滚动手势是否已翻过页：触控板惯性尾巴（事件间隔持续 <160ms）会被整段忽略，
// 避免一次滑动在 650ms 解锁后又凑满阈值、多翻一页。
let wheelGestureConsumed = false

const reducedMotion = useReducedMotion()

// 触屏/笔跟手拖拽状态（鼠标仍走滚轮翻页）
const dragging = ref(false)
const dragOffset = ref(0)
let dragPointerId = null
let dragStartY = 0
let dragLastY = 0
let dragLastT = 0
let dragVelocity = 0 // 舞台单位/ms，向下为正

// 屏幕 CSS px → 舞台设计 px
const toStageY = (clientY) => clientY / (stage.scale.value || 1)

// 允许子卡片隐藏 deck 顶部 UI（如关键词卡片 storm 阶段）
// 卡片可以请求顶栏让位（C7 是满幅版面、C6 在动画中）。
const deckChromeHidden = ref(false)
provide('deckChromeHidden', deckChromeHidden)

// 导出期间强制让位。与卡片的请求分开记账：卡片的请求在框定画幅下要被忽略，
// 导出的不能被忽略（宽画幅下舞台几乎撑满 host，顶栏可能压到舞台角上被拍进图）。
const chromeForcedHidden = ref(false)

/* 导出模式开关（单页导出与整份打包都置位）。
   语义是页面与卡片之间的契约，两侧必须一致：

   - 为 true 期间：这一页**立刻呈现终态**——不播入场动画、不等用户交互、
     不留「点击开始 / 翻开词典 / 撕开包装」这类提示。
     很多卡的最终画面藏在交互后面（合着的词典、未开奖的秒回、未撕开的表情包），
     不给这个信号，导出的就是入口态而不是正文。
   - 由 true 变回 false 时：卡片要**恢复到进入导出前的状态**（同样不播动画）。
     否则用户导出一次之后回去浏览，词典已经翻开、秒回已经开过奖，惊喜被剧透。
   - 为 false 时：行为与导出功能存在之前一字不差。

   deck 自己也吃这个开关：翻页过渡直接关掉（见 trackStyle），
   导出期间是「瞬时切页」而不是真的翻一遍。 */
const exportMode = ref(false)
provide('wrappedExportMode', exportMode)

/* 顶栏是否隐藏。
   ⚠️ 框定画幅时不理会卡片的让位请求：那时顶栏在舞台**之外**（落在两侧留白里），
   压不到画面，让位只会让用户在最想导出的那一页（C7 年度全景）找不到导出控件。
   跟随窗口时舞台铺满 host，顶栏确实会压住内容，让位仍然有效。 */
const chromeHidden = computed(() => chromeForcedHidden.value || (deckChromeHidden.value && !stage.isFramed.value))

// 影院模式的卡片（如年度海报长廊）在场时，顶栏与 deck 底色一起转暗
const deckDark = ref(false)
provide('deckDark', deckDark)

let navUnlockTimer = null

const slides = computed(() => {
  const cards = Array.isArray(report.value?.cards) ? report.value.cards : []
  const out = [{ key: 'cover' }]
  for (const c of cards) out.push({ key: `card-${c?.id ?? out.length}` })
  return out
})

// 年度总结沿用旧版浅绿色底色，避免继承聊天页灰底或引导页绿底；影院卡在场时整体转暗。
// 舞台内（画面）与舞台外（信箱边）分成两个色：同色会让「固定画幅」在视觉上不存在。
const stageBg = computed(() => (deckDark.value ? '#0A100D' : '#F3FFF8'))
const shellBg = computed(() => (deckDark.value ? '#050908' : '#E9F6EF'))
// reduced-motion 时把 700ms 翻页过渡降为 150ms
const deckTrackClass = computed(() => [
  'z-10',
  reducedMotion.value ? 'duration-150' : 'duration-700'
])

const applyViewportBg = () => {
  if (!import.meta.client) return
  // 视口底色跟信箱边走，overscroll 橡皮筋才不会露白
  document.documentElement.style.backgroundColor = shellBg.value
  document.body.style.backgroundColor = shellBg.value
  document.documentElement.style.setProperty('--wrapped-shell-bg', shellBg.value)
}

watch(shellBg, applyViewportBg)

// SSR / 首帧 host 还没量到时 design 会退化成 1px，此时用 100% 顶住，等 RO 回写再走像素值
const stageMeasured = computed(() => slideHeight.value > 2)

const slideStyle = computed(() => (
  stageMeasured.value ? { height: `${slideHeight.value}px` } : { height: '100%' }
))

const trackStyle = computed(() => {
  const base = stageMeasured.value ? -activeIndex.value * slideHeight.value : 0
  const style = { transform: `translate3d(0, ${base + dragOffset.value}px, 0)` }
  // 拖拽期间关闭过渡以保证跟手；松手后恢复类上的过渡完成收尾/回弹
  if (dragging.value) style.transition = 'none'
  /* 导出期间「瞬时切页」：不走 700ms 过渡，activeIndex 一改画面就到位。
     导出要的是每一页的终态画面，翻页过程本身没有任何一帧会被截进图，
     真翻一遍只是白等 9 × 700ms，还把「到位没有」变成一个要靠时序猜的问题。
     内联 transition 优先级高于 deckTrackClass 上的 duration-700 类。 */
  if (exportMode.value) style.transition = 'none'
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

// 翻页后播报给屏幕阅读器的文案
const slideAnnouncement = computed(() => {
  const cards = Array.isArray(report.value?.cards) ? report.value.cards : []
  const title = activeIndex.value === 0 ? '封面' : String(cards[activeIndex.value - 1]?.title || '')
  return `第 ${activeIndex.value + 1} 页 · ${title}`
})

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
  // 批量导出期间翻页由导出流程独占：用户此时滚一下会让下一张截到错的页
  if (navFrozen.value) { e.preventDefault(); return }
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

  // lastWheelAt 必须对每个事件更新（含锁定/忽略期间），间隔检测才能识别“同一次滑动的连续事件流”
  const now = e.timeStamp || Date.now()
  const gap = now - lastWheelAt
  lastWheelAt = now

  // 间隔够大 = 新手势：清零累积量，解除“本手势已翻页”标记
  if (gap > 160) {
    wheelAcc.value = 0
    wheelGestureConsumed = false
  }

  // 同一手势已经翻过页（惯性尾巴还在发事件）：整段忽略，等真实停顿
  if (wheelGestureConsumed) return
  if (navLocked.value) return

  wheelAcc.value += e.deltaY
  const threshold = 80
  if (Math.abs(wheelAcc.value) < threshold) return

  if (wheelAcc.value > 0) next()
  else prev()

  wheelAcc.value = 0
  wheelGestureConsumed = true
  lockNav()
}

const onKeydown = (e) => {
  if (navFrozen.value) return
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
  if (navFrozen.value) return
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
  // clientY 是屏幕 CSS px，而 dragOffset 会被写进舞台内的 translate3d 再乘一次 scale。
  // 在入口一次性换算成舞台单位，之后全程舞台坐标系——否则 scale≠1 时内容跟不上手指。
  dragStartY = toStageY(e.clientY)
  dragLastY = dragStartY
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
  const y = toStageY(e.clientY)
  const dy = y - dragStartY
  const dt = e.timeStamp - dragLastT
  if (dt > 0) dragVelocity = (y - dragLastY) / dt
  dragLastY = y
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
  const threshold = Math.max(1, slideHeight.value) * 0.25
  const byDistance = Math.abs(dy) > threshold
  // 速度判定加最小位移门槛，抖动轻点不触发翻页。
  // dy / dragVelocity 已是**舞台单位**：门槛按画面比例算（划过画面 1.7% 才算数），
  // 而不是物理手指位移——换画幅/换窗口时手感的相对尺度保持一致。
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

// —— 排版调试叠层（/wrapped?debug=box，仅 dev）——
const debugBox = computed(() => import.meta.dev && String(route.query?.debug || '') === 'box')
const debugBoxes = ref([])
let debugTimer = null

const sampleDebugBoxes = () => {
  if (!debugBox.value || !import.meta.client) return
  const host = document.querySelector('.wr-stage-host')
  if (!host) return
  const hr = host.getBoundingClientRect()
  const pick = [
    ['stage', '.wr-stage'],
    ['deck', '.wrapped-deck-root'],
    ['shell', '.wr-shell'],
    ['body', '.wr-shell-body'],
    ['content', '.wr-fit-content']
  ]
  const out = []
  for (const [name, sel] of pick) {
    const el = document.querySelector(sel)
    if (!el) continue
    const r = el.getBoundingClientRect()
    out.push({
      name,
      w: Math.round(r.width),
      gapL: Math.round(r.left - hr.left),
      gapR: Math.round(hr.right - r.right),
      style: {
        left: `${Math.round(r.left - hr.left)}px`,
        top: `${Math.round(r.top - hr.top)}px`,
        width: `${Math.round(r.width)}px`,
        height: `${Math.round(r.height)}px`
      }
    })
  }
  debugBoxes.value = out
}

watch(debugBox, (on) => {
  // SSR 期间不要起定时器：服务端 setInterval 会把这次渲染吊住（实测 /wrapped?debug=box 返回 500）
  if (!import.meta.client) return
  if (debugTimer) clearInterval(debugTimer)
  debugTimer = null
  if (!on) { debugBoxes.value = []; return }
  sampleDebugBoxes()
  debugTimer = setInterval(sampleDebugBoxes, 600)
}, { immediate: true })

// —— 分享 · 导出 ——
const frameMenuEl = ref(null)
const exporting = ref(false)
const exportStatus = ref('')
const exportTone = ref('info')
let exportStatusTimer = null

/* 导出进度：显示在**舞台之外**的信箱边里。
   截图的 clip 就是 .wr-stage 的屏幕矩形，舞台外的任何东西都不入图，
   所以进度可以一直亮着，用户看得见「导出到第几页了」。
   exportProgressText 为空 = 不显示。 */
const exportProgressText = ref('')
// null = 不确定进度（单页导出），数字 = 百分比（整份打包）
const exportProgressPct = ref(null)

const EXPORT_BADGE_H = 30        // 与样式里 .wr-exp 的高度对齐，两处要一起改
const EXPORT_BADGE_MIN_BAND = 40 // 横躺时：留白带至少这么高才塞得进药丸
const EXPORT_BADGE_MIN_SIDE = 132 // 横躺在侧带上：还要装得下整句文案
const EXPORT_BADGE_MIN_RAIL = 38 // 侧带窄到装不下整句时改成竖立（转 90°），只要装得下药丸的「高」

/* 进度徽标落在哪条留白带上。坐标系是 .wr-stage-host（chrome 插槽的定位父级，position:relative）。

   实测（1440×900 窗口，host 1440×755）：桌面横屏窗口下留白**永远在两侧**，
   上下带是 0；侧带宽度 16:9 只有 49px、4:3 有 217px、9:16 有 508px。
   所以侧带分两档：够宽就横躺，窄了就沿着信箱边竖起来（转 90°，此时占的横向宽度
   只有药丸的高 30px）。上下带的分支留给竖屏窗口（手机上装 16:9 这种宽画幅）。

   ⚠️ 一条都装不下时返回 null，**绝不硬塞**：
   - 跟随窗口（fit）舞台铺满 host，四条带全是 0；
   - 1280×800 这种窗口配 16:9，上下带只有 18px，塞进去的字比进度本身还碍眼。
   塞了就会压在画面上、被 clip 一起拍进图，正是这次要避免的事。
   这一档沿用原来的做法：面板里的 exportStatus 文案，导出结束顶栏回来时可见。 */
const exportBadgePlacement = computed(() => {
  if (!stage.isFramed.value) return null
  const d = stage.design.value
  const k = stage.scale.value || 1
  const r = stage.rect.value
  const host = stage.hostSize.value
  const sw = d.w * k
  const sh = d.h * k
  if (!(sw > 0 && sh > 0 && host.w > 0 && host.h > 0)) return null

  const bandTop = r.top
  const bandBottom = host.h - (r.top + sh)
  const bandLeft = r.left
  const bandRight = host.w - (r.left + sw)

  // 优先下方：视线离开画面最短，也不跟右上角的分享面板抢位置
  if (bandBottom >= EXPORT_BADGE_MIN_BAND) {
    return {
      where: 'bottom',
      style: {
        left: '50%',
        top: `${Math.round(r.top + sh + (bandBottom - EXPORT_BADGE_H) / 2)}px`,
        transform: 'translateX(-50%)',
        maxWidth: `${Math.round(host.w - 24)}px`
      }
    }
  }
  if (bandTop >= EXPORT_BADGE_MIN_BAND) {
    return {
      where: 'top',
      style: {
        left: '50%',
        top: `${Math.round((bandTop - EXPORT_BADGE_H) / 2)}px`,
        transform: 'translateX(-50%)',
        maxWidth: `${Math.round(host.w - 24)}px`
      }
    }
  }

  const side = Math.max(bandLeft, bandRight)
  if (side < EXPORT_BADGE_MIN_RAIL) return null
  const onRight = bandRight >= bandLeft
  const cx = Math.round(onRight ? r.left + sw + bandRight / 2 : bandLeft / 2)
  const cy = Math.round(r.top + sh / 2)
  if (side >= EXPORT_BADGE_MIN_SIDE) {
    return {
      where: onRight ? 'right' : 'left',
      style: {
        left: `${cx}px`,
        top: `${cy}px`,
        transform: 'translate(-50%, -50%)',
        maxWidth: `${Math.round(side - 24)}px`
      }
    }
  }
  /* 竖立：整块转 90°，横向只占药丸的高（30px），长度沿信箱边铺开。
     左轨从下往上读、右轨从上往下读，跟胶片边缘的惯例一致。 */
  return {
    where: onRight ? 'right-rail' : 'left-rail',
    style: {
      left: `${cx}px`,
      top: `${cy}px`,
      transform: `translate(-50%, -50%) rotate(${onRight ? 90 : -90}deg)`,
      maxWidth: `${Math.round(sh - 24)}px`
    }
  }
})

const exportBadgeVisible = computed(() => (
  exporting.value && !!exportProgressText.value && !!exportBadgePlacement.value
))

const desktopBridge = () => (import.meta.client ? (window.wechatDesktop || null) : null)
const canExportImage = computed(() => import.meta.client && typeof desktopBridge()?.captureRegion === 'function')

const setExportStatus = (text, tone = 'info') => {
  exportStatus.value = text
  exportTone.value = tone
  if (exportStatusTimer) clearTimeout(exportStatusTimer)
  if (debugTimer) clearInterval(debugTimer)
  if (text) exportStatusTimer = setTimeout(() => { exportStatus.value = '' }, 4200)
}

const nextFrames = (n = 2) => new Promise((resolve) => {
  let left = Math.max(1, n)
  const tick = () => { left -= 1; if (left <= 0) resolve(); else requestAnimationFrame(tick) }
  requestAnimationFrame(tick)
})

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const slideTitleAt = (i) => {
  const cards = Array.isArray(report.value?.cards) ? report.value.cards : []
  if (i === 0) return '封面'
  return String(cards[i - 1]?.title || `第${i + 1}页`)
}

const currentSlideTitle = () => slideTitleAt(activeIndex.value)

// 文件名安全化：主进程也会做一遍，但前端先做，别把非法字符送出门。
// 分隔符 / 控制字符 / Windows 保留字符全换成下划线，首尾点号去掉（`.` 开头在 macOS 是隐藏文件）。
const safeFileName = (raw, fallback = '页面') => {
  const s = String(raw ?? '')
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\.+/, '')
    .replace(/\.+$/, '')
    .slice(0, 60)
    .trim()
  return s || fallback
}

const frameKey = () => String(stage.frameId.value || 'fit').replace(':', 'x')

/* 导出几何：clip 用的是舞台在屏幕上的**视觉**矩形（getBoundingClientRect），因为要的正是屏幕上那块区域。
   宽度 = 设计宽 × 舞台缩放 k。要出到平台像素 target，需要的倍率是 target / (设计宽 × k) = exportScale / k。
   ⚠️ 这里是除以 k 不是乘以 k：乘反了会出成 design × exportScale × k²（9:16 实测只有 481×855）。
   CDP 的 clip.scale 会**再乘一次页面的设备像素比**（Retina 上是 2），
   不除掉就会出成目标尺寸的两倍（实测 9:16 出 2160×3840）。
   单页导出与整份打包共用这一份算法——两处各写一遍必然会漂。 */
const exportGeometry = () => {
  const el = stage.stageEl.value
  if (!el) return null
  const r = el.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  // 倍率要从**取整后**的裁剪框反推，否则 406.5 这种半像素会让出图差 1px（1081×1921）。
  const clipW = Math.round(r.width)
  const clipH = Math.round(r.height)
  if (!(clipW > 0 && clipH > 0)) return null
  const design = stage.design.value
  const targetW = Math.round(design.w * exportScale(stage.frame.value, design))
  return {
    x: r.left,
    y: r.top,
    width: clipW,
    height: clipH,
    scale: targetW / clipW / dpr,
    outWidth: targetW,
    outHeight: Math.round(design.h * (targetW / design.w))
  }
}

// 导出「画面本身」：截取舞台矩形，顶部控件先隐藏所以天然不入图。
const exportCurrentFrame = async () => {
  const bridge = desktopBridge()
  if (exporting.value) return
  if (!canExportImage.value || !bridge) {
    setExportStatus('浏览器里暂不能直接出图，请在桌面应用中导出，或用系统截图', 'error')
    return
  }
  if (!stage.stageEl.value) return

  exporting.value = true
  chromeForcedHidden.value = true
  /* 单页导出同样要终态：用户在词典页点「导出图片」，要的是翻开的词典跨页，
     不是他刚好停在的那本合着的书。exportMode 一置位卡片就跳到终态（不播动画）。 */
  exportMode.value = true
  exportProgressText.value = '正在出图…'
  frameMenuEl.value?.close?.()
  try {
    // 卡片切终态是一次普通的响应式更新：给它几帧落地，再等版面指纹收敛。
    await nextFrames(3)
    await waitForSlideReady(activeIndex.value)
    const geo = exportGeometry()
    if (!geo) throw new Error('舞台尚未就绪，稍后再试')
    const res = await bridge.captureRegion({
      ...geo,
      name: `年度总结-${year.value}-${frameKey()}-${currentSlideTitle()}`
    })
    if (res?.ok) {
      const size = res.width && res.height ? ` · ${res.width}×${res.height}` : ''
      setExportStatus(`已保存${size}，已在访达中选中：output/年度总结/`)
    }
    else setExportStatus(res?.error || '导出失败', 'error')
  } catch (e) {
    setExportStatus(e?.message || String(e), 'error')
  } finally {
    // 卡片靠 exportMode 落回导出前的状态（含失败/中断路径），这一行不能漏
    exportMode.value = false
    exportProgressText.value = ''
    exportProgressPct.value = null
    chromeForcedHidden.value = false
    exporting.value = false
  }
}

// —— 整份打包：逐页翻过去截图，攒成一个 zip ——

const canExportAll = computed(() => import.meta.client && typeof desktopBridge()?.wrappedBatchBegin === 'function')

const rafOnce = () => new Promise((resolve) => requestAnimationFrame(() => resolve()))

const slideElAt = (i) => trackEl.value?.children?.[i] || null

// 封面无数据可等；卡片页 error 也算「定了」——那一页就是错误态，照样出图，不能把整批卡死
const slideDataSettled = (i) => {
  if (i <= 0) return true
  const st = String(report.value?.cards?.[i - 1]?.status || 'idle')
  return st === 'ok' || st === 'error'
}

/* 轨道真的停在这一页了吗。
   activeIndex 只是「我们想去哪」，translate3d 上还挂着 700ms 过渡；
   读**计算后**的 transform 才知道画面到没到位。这是「这一页可截了」最硬的一条信号。 */
const trackSettledAt = (i) => {
  const el = trackEl.value
  if (!el) return false
  const want = -clampIndex(i) * slideHeight.value
  const raw = window.getComputedStyle(el).transform
  if (!raw || raw === 'none') return Math.abs(want) < 0.6
  const nums = raw.slice(raw.indexOf('(') + 1, raw.lastIndexOf(')')).split(',').map((s) => parseFloat(s))
  // matrix(a,b,c,d,tx,ty) 6 位 / matrix3d 16 位（ty 在第 14 位）
  const ty = nums.length === 16 ? nums[13] : nums[5]
  if (!Number.isFinite(ty)) return false
  return Math.abs(ty - want) < 0.6
}

/* 版面快照：同一帧里能观测到的「这一页现在长什么样」。
   采两类东西：
   - 抽样元素的屏幕矩形（GSAP 直接改内联样式、不进 getAnimations，只能靠位置采样看出「还在动」）
   - 同一批元素的「会动的计算样式」。**这一半不能省**：很多入场根本不挪位置——
     透明度淡入、滤镜、描边偏移(stroke-dashoffset)、渐变位移、颜色过渡。
     实测作息页只看矩形时全程读数是 0，把这些样式采进来才现形。
   另外单列一份 struct 字符串：元素增减、scrollHeight、data-fit-scale（异步测量后才写上，
   写的瞬间整页会缩一下）、图片解码完成数、canvas 尺寸——这些是「一次性事件」，
   不是持续动效，出现了就必须把收敛计时重来。
   为什么不采 canvas 像素：取 2D 上下文会把尚未初始化的 WebGL 画布**永久**占成 2D，
   那会弄坏用户浏览时的 3D 卡片。导出的兜底不值得冒这个险。 */
const SAMPLE_NODES = 48
const FINITE_ANIM_MAX_MS = 8000   // 超过这个时长的动画按环境动效看待，不再当作「入场没演完」
const STYLE_WEIGHT = 3        // 一个元素改一次样式，折算成「挪了 3px」，好把两类变化并成一个标量

/* 扫一遍这一页上的动画，分成两堆：
   - finite：还在跑、而且会结束的（入场的一部分）——它没跑完就不是终态。
   - endless：无限循环 / 长得离谱的（星星眨眼、扫光、呼吸）——它到天荒地老也不会停。
   endless 的**目标元素及其子树**在收敛判定里只比位置、不比样式：
   实测作息页稳态里一直在变的就是几十颗 sk-star（透明度闪烁）和一条 sk-glint，
   而且它们是错峰启动的，参与变化的元素数要三四秒才涨稳——不摘掉就白等这三四秒。
   只摘样式、保留矩形，是为了不把「带呼吸光效、同时正飞进来的卡片」一起漏掉：
   它飞进来时位置在变，照样能被看见。 */
const collectAnimations = (el) => {
  const endless = new Set()
  let finite = 0
  try {
    for (const a of el.getAnimations({ subtree: true })) {
      if (a.playState !== 'running') continue
      const t = a.effect?.getComputedTiming?.()
      if (!t) continue
      const end = Number(t.endTime)
      if (t.iterations === Infinity || !Number.isFinite(end) || end > FINITE_ANIM_MAX_MS) {
        const target = a.effect.target
        if (target) endless.add(target)
      } else finite += 1
    }
  } catch {
    // 不支持 getAnimations 时两头都空着，后面的运动量采样照样能兜住
  }
  return { endless, finite }
}

// 顺着祖先链找一次就够，不用拿整个 endless 集合去 contains（48 个元素 × 集合大小太贵）
const drivenByEndless = (node, endless, root) => {
  if (!endless.size) return false
  let n = node
  while (n && n !== root) {
    if (endless.has(n)) return true
    n = n.parentElement
  }
  return endless.has(root)
}

const slideSnapshot = (el, endless) => {
  const nodes = el.querySelectorAll('*')
  const step = Math.max(1, Math.floor(nodes.length / SAMPLE_NODES))
  const rects = []
  const styles = []
  const ambient = []
  for (let k = 0; k < nodes.length; k += step) {
    const node = nodes[k]
    const r = node.getBoundingClientRect()
    rects.push(r.left, r.top, r.width, r.height)
    const cs = window.getComputedStyle(node)
    styles.push(`${cs.opacity}|${cs.transform}|${cs.filter}|${cs.strokeDashoffset}|${cs.backgroundPosition}|${cs.color}|${cs.backgroundColor}|${cs.clipPath}`)
    ambient.push(drivenByEndless(node, endless, el))
  }
  const imgs = el.querySelectorAll('img')
  let decoded = 0
  for (const im of imgs) if (im.complete && im.naturalWidth > 0) decoded += 1
  const fits = []
  for (const f of el.querySelectorAll('[data-fit-scale]')) fits.push(f.getAttribute('data-fit-scale'))
  const canv = []
  for (const c of el.querySelectorAll('canvas')) canv.push(`${c.width}x${c.height}`)
  return {
    rects,
    styles,
    ambient,
    imgPending: imgs.length - decoded,
    struct: `${el.scrollHeight}|${el.childElementCount}|${nodes.length}|${decoded}/${imgs.length}|${fits.join(',')}|${canv.join(',')}`
  }
}

/* 两次采样之间的「运动量」：矩形位移(px) 加上折算过的样式变化，摊到每个抽样元素上。
   churn = 这一拍里有多少个元素的样式变了——用来分辨「一批批进场」和「固定那几个在循环」。
   结构变了就返回 null：那一拍的差值没有可比性（元素错位了），交给调用方重新计时。 */
const motionBetween = (a, b) => {
  if (!a || !b) return null
  if (a.struct !== b.struct || a.rects.length !== b.rects.length) return null
  let sum = 0
  for (let k = 0; k < b.rects.length; k += 4) {
    sum += Math.abs(b.rects[k] - a.rects[k])
      + Math.abs(b.rects[k + 1] - a.rects[k + 1])
      + Math.abs(b.rects[k + 2] - a.rects[k + 2])
      + Math.abs(b.rects[k + 3] - a.rects[k + 3])
  }
  let churn = 0
  for (let k = 0; k < b.styles.length; k += 1) {
    if (b.ambient[k] || a.ambient[k]) continue        // 无限循环动画驱动的元素只比位置
    if (b.styles[k] !== a.styles[k]) churn += 1
  }
  const n = Math.max(1, b.rects.length / 4)
  return { score: (sum + STYLE_WEIGHT * churn) / n, churn }
}

const imagesPending = (el) => {
  let pending = 0
  for (const im of el.querySelectorAll('img')) if (!im.complete || !(im.naturalWidth > 0)) pending += 1
  return pending
}

/* 等到第 i 页「真的可截了」。
   全是**有界**等待：任何一环卡住都不会把导出吊死——数据是懒加载的（走后端，可能真的慢），
   图片要解码，字体会晚到，动画更是各页各脾气。每一环都有自己的上限，超时就往下走。

   ⚠️ 判定收敛为什么不能只用「版面连续 N 次不变」：
   实测（导出模式、9:16、每 2 帧采一次运动量，单位 px/抽样元素）这九页分成两类——
   - 会停的：打字 / 口头禅 / 秒回 / 好友墙 / Bento 读数几拍内落到 0。
   - **永远不停的**：封面稳定在 0.78、全局总览在 0.5 上下 —— 这是无限循环的环境动效
     （网格滚动、扫光、呼吸）造成的固有抖动，读数到天荒地老也不会变成 0。
   所以只等「不变」的规则对后一类永远不成立，每页都会白等满上限。

   判定因此有两条路，覆盖两类页：
   - 快路（真的静止）：连续 QUIET_WINS 个窗口运动量 ≤ QUIET_ABS。入场被 exportMode 压掉、
     终态直接落地的页走这条，约 0.45s 就走。
   - 慢路（自身抖动基线）：一页哪怕一直在动，它的动也会稳定在**自己的**那个水平上。
     连续 PLATEAU_WINS 个窗口的运动量都落在同一条带子里（相对带宽，不设绝对阈值，
     因为 0.78 和 0.5 各是各的基线），且这期间没有结构变化、没有会结束的动画，
     就认定「剩下的都是环境动效」，可以截。
     光看水平还不够：入场是一批批进场的，参与变化的元素数(churn)会一路往上涨，
     水平却可能在某一段恰好持平；所以还要求 churn 在这几个窗口里一模一样——
     环境动效是固定那几个元素在动，churn 是常数；入场没走完时 churn 一定还在变。
     慢路另加 PLATEAU_MIN_MS 的最小观察期，免得刚切过去、动画还没起步就被判成基线。
   两条路都没走通就等到 SETTLE_MAX_MS 为止（覆盖实测最慢的作息/口头禅那一档 4.5s）。 */
const WAIT_DATA_MS = 20000     // 卡片数据（走后端，可能真的慢）
const NAV_MAX_MS = 600         // 瞬时切页只需一两帧；留一点余量兜住 slideHeight 刚变的那帧
const WAIT_FONT_MS = 1500      // 字体晚到会让整页文本重排
const WAIT_IMG_MS = 6000       // Bento 有 44 张图、秒回 21 张，没加载完会截出空头像
const DECODE_MAX_MS = 2000     // 加载完还要真的解码到位
const SETTLE_MAX_MS = 5000     // 兜底上限：入场没被压掉时，最慢的一档实测 4.5s 收敛
const SETTLE_WIN_MS = 220      // 一个观察窗口 ≈ 7 次采样，取中位数躲开偶发单帧抖动
const QUIET_ABS = 0.08         // 「真的静止」的绝对阈值（px/抽样元素）
const QUIET_WINS = 2           // 连续 2 个安静窗口即可（≈0.45s）
const PLATEAU_WINS = 5         // 基线要连续 5 个窗口稳住（≈1.1s）才算数
const PLATEAU_MIN_MS = 1400    // 慢路的最小观察期，防止把「动画还没起步」当成基线
const PLATEAU_BAND = 0.5       // 基线带宽：窗口间高低差不超过基线的 50%

// 收敛判定：wins 是按时间排好的窗口记录，elapsed 是进入收敛阶段以来的毫秒数
const settleReached = (wins, elapsed) => {
  // 快路：真的不动了
  if (wins.length >= QUIET_WINS) {
    const tail = wins.slice(-QUIET_WINS)
    if (tail.every((w) => !w.dirty && w.level <= QUIET_ABS)) return true
  }
  // 慢路：动是动，但已经稳在这一页自己的抖动基线上
  if (wins.length >= PLATEAU_WINS && elapsed >= PLATEAU_MIN_MS) {
    const tail = wins.slice(-PLATEAU_WINS)
    if (tail.some((w) => w.dirty)) return false
    const levels = tail.map((w) => w.level)
    const hi = Math.max(...levels)
    const lo = Math.min(...levels)
    if (hi - lo > Math.max(QUIET_ABS, PLATEAU_BAND * lo)) return false
    const churns = tail.map((w) => w.churn)
    if (Math.max(...churns) !== Math.min(...churns)) return false
    return true
  }
  return false
}

const waitForSlideReady = async (i) => {
  // 1) 数据：这一页是懒加载的，先催一把再等状态落定
  loadCardAtSlide(i)
  const dataDeadline = performance.now() + WAIT_DATA_MS
  while (!slideDataSettled(i) && performance.now() < dataDeadline) await sleep(80)

  // 2) 画面真的停在这一页（读实际 transform，不是读 activeIndex）
  const navDeadline = performance.now() + NAV_MAX_MS
  while (!trackSettledAt(i) && performance.now() < navDeadline) await rafOnce()

  // 3) 字体就绪：字体晚到会让整页文本重排，排完才是最终版面。
  //    首页之后 document.fonts.ready 是已兑现的 promise，这一步几乎不花时间。
  try {
    if (typeof document !== 'undefined' && document.fonts?.ready) {
      await Promise.race([document.fonts.ready, sleep(WAIT_FONT_MS)])
    }
  } catch {
    // 不支持 FontFaceSet 时跳过
  }

  // 4) 图片：先等到 complete 且 naturalWidth>0，再尽量 decode 到位。
  //    只等 complete 有时还会截到没画出来的那一帧；两步都有界，卡住就往下走。
  const imgDeadline = performance.now() + WAIT_IMG_MS
  while (performance.now() < imgDeadline) {
    const el = slideElAt(i)
    if (!el || imagesPending(el) === 0) break
    await sleep(60)
  }
  const imgEl = slideElAt(i)
  if (imgEl) {
    const decodes = []
    for (const im of imgEl.querySelectorAll('img')) {
      if (typeof im.decode === 'function') decodes.push(im.decode().catch(() => {}))
    }
    if (decodes.length) await Promise.race([Promise.all(decodes), sleep(DECODE_MAX_MS)])
  }

  // 5) 版面收敛：按窗口统计运动量，走上面那两条路里先成立的一条
  const settleStart = performance.now()
  const wins = []
  let bucket = []
  let winStart = settleStart
  let dirty = false
  let prev = null
  while (performance.now() - settleStart < SETTLE_MAX_MS) {
    await rafOnce()
    await rafOnce()
    const el = slideElAt(i)
    if (!el) break
    const anims = collectAnimations(el)
    const snap = slideSnapshot(el, anims.endless)
    const m = motionBetween(prev, snap)
    prev = snap
    if (m) bucket.push(m)
    else if (wins.length || bucket.length) dirty = true    // 结构变了：这一窗作废
    // 图片刚解出来、或者还有会结束的动画在跑，都说明这一窗不是终态
    if (snap.imgPending > 0 || anims.finite > 0) dirty = true
    if (performance.now() - winStart < SETTLE_WIN_MS) continue
    const scores = bucket.map((x) => x.score).sort((a, b) => a - b)
    wins.push({
      level: scores.length ? scores[scores.length >> 1] : 0,
      churn: bucket.length ? Math.max(...bucket.map((x) => x.churn)) : 0,
      dirty
    })
    bucket = []
    dirty = false
    winStart = performance.now()
    if (settleReached(wins, performance.now() - settleStart)) break
  }
  await nextFrames(2)
}

/* 逐页导出打包。
   全程 chromeForcedHidden：顶栏在宽画幅下会压到舞台角上，被拍进图。
   全程 navFrozen：用户此时滚一下会让下一张截到错的页。 */
const exportAllPages = async () => {
  const bridge = desktopBridge()
  if (exporting.value) return
  if (!canExportAll.value || !bridge) {
    setExportStatus('浏览器里暂不能直接出图，请在桌面应用中导出，或用系统截图', 'error')
    return
  }
  const total = slides.value.length
  if (total <= 0) {
    setExportStatus('还没有可导出的页面', 'error')
    return
  }

  const originalIndex = activeIndex.value
  exporting.value = true
  navFrozen.value = true
  chromeForcedHidden.value = true
  // 卡片进终态（词典翻开、秒回开奖、表情包撕开），并且不播入场动画；
  // 同时把轨道过渡关成 none —— 从这一刻起翻页是瞬时的，没有可见的翻页过程。
  exportMode.value = true
  /* ⚠️ 这里**不**关面板（单页导出会关）。面板跟顶栏一起被 chromeForcedHidden 隐藏，
     不会入图；留着它，导出结束顶栏回来的那一刻用户正好看到「已打包 N 张」，
     而不是对着一个什么都没发生的画面猜结果。
     导出途中的进度画在**舞台之外**的信箱边里（见 .wr-exp / exportBadgePlacement）：
     截图的 clip 就是舞台矩形，那条留白带不会入图，所以进度可以一直亮着。 */

  let batchId = null
  try {
    exportProgressPct.value = 0
    exportProgressText.value = `正在导出 0/${total}`
    setExportStatus(`正在导出 0/${total}…`)
    await nextFrames(3)

    const begun = await bridge.wrappedBatchBegin({
      label: `年度总结-${year.value}-${frameKey()}`
    })
    if (!begun?.ok || !begun?.batchId) throw new Error(begun?.error || '无法开始批量导出')
    batchId = begun.batchId

    for (let i = 0; i < total; i++) {
      exportProgressText.value = `正在导出 ${i + 1}/${total}`
      exportProgressPct.value = Math.round((i / total) * 100)
      setExportStatus(`正在导出 ${i + 1}/${total}…`)
      goTo(i)
      await waitForSlideReady(i)
      // 进度提示的自动消失是 4.2s，等版面这一段可能更久，稳定后补一次
      setExportStatus(`正在导出 ${i + 1}/${total}…`)

      const geo = exportGeometry()
      if (!geo) throw new Error('舞台尚未就绪，稍后再试')
      const res = await bridge.wrappedBatchCapture({
        batchId,
        index: i,
        name: safeFileName(slideTitleAt(i), `第${i + 1}页`),
        ...geo
      })
      if (!res?.ok) throw new Error(res?.error || `第 ${i + 1} 页导出失败`)
    }

    exportProgressText.value = `正在打包 ${total} 张`
    exportProgressPct.value = 100
    setExportStatus(`正在打包 ${total} 张…`)
    const zipName = safeFileName(`微信年度总结_${year.value}_${frameKey()}`, `微信年度总结_${year.value}`)
    const fin = await bridge.wrappedBatchFinish({ batchId, zipName })
    batchId = null
    if (!fin?.ok) throw new Error(fin?.error || '打包失败')

    const count = Number.isFinite(Number(fin.count)) ? Number(fin.count) : total
    const mb = Number(fin.bytes) > 0 ? ` · ${(Number(fin.bytes) / 1048576).toFixed(1)}MB` : ''
    setExportStatus(`已打包 ${count} 张${mb}，已在访达中选中：output/年度总结/`)
  } catch (e) {
    if (batchId) {
      try {
        await bridge.wrappedBatchAbort?.({ batchId })
      } catch {
        // 清理失败不覆盖真正的错误
      }
    }
    setExportStatus(e?.message || String(e), 'error')
  } finally {
    /* 顺序有讲究：先在**还处于瞬时切页**的规则下跳回原页，再关 exportMode。
       反过来先关 exportMode，goTo 就会带着 700ms 过渡从末页一路滑回去，
       用户会看到一段莫名其妙的倒放。 */
    goTo(originalIndex)
    await nextFrames(2)
    // 卡片靠 exportMode 落回导出前的状态（合上词典、收起开奖），含失败/中断路径
    exportMode.value = false
    exportProgressText.value = ''
    exportProgressPct.value = null
    navFrozen.value = false
    chromeForcedHidden.value = false
    exporting.value = false
  }
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
  // 画幅：URL ?frame= 优先于 localStorage（分享出去的深链要带得动画幅）
  stage.initFrame(route.query?.frame)
  applyViewportBg()
  // 舞台高度由 WrappedStage 的 host ResizeObserver 驱动，deck 自己不再测窗口。
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
    document.documentElement.style.removeProperty('--wrapped-shell-bg')
  }
  if (exportStatusTimer) clearTimeout(exportStatusTimer)
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

// 画幅写回 URL，深链能带着画幅分享出去
watch(() => stage.frameId.value, async (id) => {
  if (!import.meta.client) return
  const next = { ...route.query }
  if (id && id !== 'fit') next.frame = id
  else delete next.frame
  try {
    await router.replace({ query: next })
  } catch {
    // ignore
  }
})
</script>

<style>
/* 高度改由 WrappedStage 的 .wr-stage-host 承担（含桌面端 100% 重解释）；
   deck 在舞台内一律填满舞台盒。 */
.wrapped-deck-root {
  height: 100%;
  min-height: 0;
}

/* 导出进度徽标。永远画在舞台外的信箱边上（位置由 exportBadgePlacement 给），
   所以它可以在整个导出过程中亮着而不会被拍进图。
   高度写死 30px —— exportBadgePlacement 的 EXPORT_BADGE_H 按这个值算居中，两处要一起改。 */
.wr-exp {
  position: absolute;
  z-index: 30;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 13px;
  border-radius: 9999px;
  border: 1px solid rgba(7, 193, 96, 0.22);
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 6px 18px -8px rgba(6, 46, 28, 0.35);
  font-size: 12px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  color: rgba(6, 46, 28, 0.78);
  white-space: nowrap;
  pointer-events: none;
  overflow: hidden;
}

.wr-exp--dark {
  border-color: rgba(74, 222, 128, 0.26);
  background: rgba(12, 22, 17, 0.86);
  color: rgba(226, 245, 233, 0.88);
  box-shadow: 0 6px 18px -8px rgba(0, 0, 0, 0.6);
}

.wr-exp__dot {
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  background: #07C160;
  animation: wr-exp-pulse 1100ms ease-in-out infinite;
}

.wr-exp--dark .wr-exp__dot { background: #4ADE80; }

.wr-exp__text {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 进度条贴在药丸底边内侧，不额外占高度 */
.wr-exp__bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  background: rgba(7, 193, 96, 0.14);
}

.wr-exp__bar > i {
  display: block;
  height: 100%;
  background: #07C160;
  transition: width 200ms ease;
}

.wr-exp--dark .wr-exp__bar { background: rgba(74, 222, 128, 0.16); }
.wr-exp--dark .wr-exp__bar > i { background: #4ADE80; }

@keyframes wr-exp-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.wr-exp-enter-active,
.wr-exp-leave-active { transition: opacity 180ms ease; }
.wr-exp-enter-from,
.wr-exp-leave-to { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .wr-exp__dot { animation-duration: 3000ms; }
  .wr-exp__bar > i { transition-duration: 1ms; }
}

/* 排版调试叠层 */
.wf-debug { position: absolute; inset: 0; z-index: 40; pointer-events: none; }
.wf-debug__box { position: absolute; outline: 1px dashed rgba(224, 82, 63, 0.8); }
.wf-debug__tag {
  position: absolute; left: 0; top: 0; transform: translateY(-100%);
  font-size: 10px; line-height: 14px; padding: 0 4px; white-space: nowrap;
  background: rgba(224, 82, 63, 0.9); color: #fff; font-variant-numeric: tabular-nums;
}
</style>
