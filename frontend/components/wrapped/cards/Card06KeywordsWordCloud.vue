<template>
  <div ref="cardRoot" class="h-full w-full">
    <!-- 全屏气泡覆盖层：storm/packed/merge/burst 阶段 Teleport 到 body，不受父级 transform 影响 -->
    <Teleport to="body">
      <div
        v-if="showOverlay"
        ref="overlayEl"
        class="kw-overlay fixed inset-0 overflow-hidden"
        :class="{ 'wrapped-privacy': privacyMode }"
        :style="{ zIndex: 9999 }"
        @pointerdown="onStagePointerDown"
      >
        <!-- 提示（accelerated 默认开启，此提示基本不显示） -->
        <div
          v-if="showHint"
          class="absolute bottom-3 right-3 z-30 wrapped-label text-[10px] text-[#00000055] bg-white/55 backdrop-blur rounded-lg px-2 py-1 border border-[#0000000a]"
          data-no-accel
        >
          点击空白处加速
        </div>

        <!-- 气泡层 -->
        <div class="absolute inset-0 z-10">
          <div
            v-for="b in bubbles"
            :key="b.id"
            :ref="(el) => registerBubbleEl(b.id, el)"
            class="kw-bubble absolute"
            :class="`kw-bubble--d${b.depth}`"
            :style="bubbleStyle(b)"
          >
            <div
              class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-[#95EC69] text-black bubble-tail-r"
            >
              <span class="wrapped-privacy-message">
                <span v-if="Array.isArray(b.segments) && b.segments.length > 0">
                  <span v-for="(seg, idx) in b.segments" :key="`${b.id}-${idx}`">
                    <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                    <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                  </span>
                </span>
                <span v-else>{{ b.text }}</span>
              </span>
            </div>
          </div>
        </div>

      </div>
    </Teleport>

    <!-- 这张卡破例不显示外部标题与描述：书名印在封面上，小序印在书里，整屏只有一本书 -->
    <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant" :wide="true" :hide-chrome="true">
      <div class="kw-stage relative w-full h-[92vh] min-h-[520px]">
        <!-- 合着的词典：翻开它，话才涌出来 -->
        <div v-if="phase === 'book' || phase === 'opening' || phase === 'storm'" class="absolute inset-0 flex items-center justify-center">
          <div
            ref="bookEl"
            class="kwb"
            :class="{ 'kwb--open': phase !== 'book' }"
            role="button"
            tabindex="0"
            :aria-label="`翻开${card.title}`"
            @click="openBook"
            @keydown.enter.prevent="openBook"
            @keydown.space.prevent="openBook"
            @pointermove="onBookPointerMove"
            @pointerleave="onBookPointerLeave"
          >
            <span class="kwb-shadow" aria-hidden="true" />
            <span ref="bookStackEl" class="kwb-stack">
            <span class="kwb-block" aria-hidden="true">
              <!-- 书芯首页＝扉页：凸版印刷 + 订口弧光 + 书口叠纸 + 缎带书签，翻开后才淡入 -->
              <span class="kwb-leaf">
                <span class="kwb-print">
                  <span class="kwb-ht-kicker">{{ yearCn }}</span>
                  <span class="kwb-ht-title">年度词典</span>
                  <span class="kwb-ht-rule" />
                  <span class="kwb-ht-loz" />
                  <span class="kwb-ht-imprint">私家藏本 · 立目 <span class="kwb-ht-num">{{ keywords.length }}</span></span>
                  <span class="kwb-ht-folio">i</span>
                </span>
                <svg class="kwb-ribbon" viewBox="0 0 380 526" preserveAspectRatio="none" aria-hidden="true">
                  <defs>
                    <linearGradient id="kwbRibG" gradientUnits="userSpaceOnUse" x1="10" y1="-10" x2="60" y2="460">
                      <stop offset="0" stop-color="#0B713F" />
                      <stop offset="0.3" stop-color="#12A75C" />
                      <stop offset="0.48" stop-color="#0A8C4C" />
                      <stop offset="0.64" stop-color="#19B96C" />
                      <stop offset="0.82" stop-color="#078044" />
                      <stop offset="1" stop-color="#0B9450" />
                    </linearGradient>
                    <linearGradient id="kwbRibS" gradientUnits="userSpaceOnUse" x1="0" y1="-10" x2="0" y2="460">
                      <stop offset="0.26" stop-color="rgba(255,255,255,0)" />
                      <stop offset="0.44" stop-color="rgba(255,255,255,0.32)" />
                      <stop offset="0.62" stop-color="rgba(255,255,255,0)" />
                    </linearGradient>
                    <filter id="kwbRibB" x="-40%" y="-40%" width="180%" height="180%">
                      <feGaussianBlur stdDeviation="3" />
                    </filter>
                  </defs>
                  <!-- 落在纸面上的软影。走向：从订口顶端翻过页顶，沿右侧空白边距垂下，不压排印栏 -->
                  <g filter="url(#kwbRibB)" transform="translate(5 6)" opacity="0.22">
                    <path d="M 16 -10 C 110 34, 246 56, 300 128 C 336 180, 332 262, 314 330 C 302 372, 298 404, 297 438" fill="none" stroke="#3A2E18" stroke-width="15" />
                    <path d="M 289.5 432 L 304.5 432 L 304.5 460 L 297 447 L 289.5 460 Z" fill="#3A2E18" />
                  </g>
                  <!-- 缎带本体：深色打底出边缘，中间盖一层顺长度走的缎面渐变 -->
                  <path d="M 16 -10 C 110 34, 246 56, 300 128 C 336 180, 332 262, 314 330 C 302 372, 298 404, 297 438" fill="none" stroke="#056B38" stroke-width="15" />
                  <path d="M 289.5 432 L 304.5 432 L 304.5 460 L 297 447 L 289.5 460 Z" fill="url(#kwbRibG)" stroke="#056B38" stroke-width="1" />
                  <path d="M 16 -10 C 110 34, 246 56, 300 128 C 336 180, 332 262, 314 330 C 302 372, 298 404, 297 438" fill="none" stroke="url(#kwbRibG)" stroke-width="12.6" />
                  <path d="M 14 -12 C 108 32, 244 54, 298 126 C 334 178, 330 260, 312 328 C 300 370, 296 402, 295 436" fill="none" stroke="url(#kwbRibS)" stroke-width="4.5" />
                </svg>
              </span>
            </span>
            <span class="kwb-spine" aria-hidden="true" />
            <!-- 腰封：环绕整摞书（书脊到书口），翻开时随手滑落 -->
            <span class="kwb-obi" aria-hidden="false">
              <span class="kwb-obi-kicker">{{ yearCn }} 年度词典</span>
              <span class="kwb-obi-title">{{ card.title }}</span>
              <span class="kwb-obi-meta">收短句 {{ formatInt(card.data?.meta?.matchedCandidates) }} · 立目 {{ keywords.length }}</span>
            </span>
            <span ref="bookCoverEl" class="kwb-cover">
              <!-- 正面：与打字卡装订的是同一本《你说过的话》——词典身份写在腰封上 -->
              <span class="kwb-face">
                <span class="kwb-frame" aria-hidden="true" />
                <svg class="kwb-seal" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="12" r="10.4" fill="none" stroke="#DDBE7E" stroke-width="1.1" opacity="0.85" />
                  <circle cx="12" cy="12" r="8.6" fill="none" stroke="#A98753" stroke-width="0.5" opacity="0.6" />
                  <path
                    d="M12 6.6c-3.2 0-5.7 2.1-5.7 4.7 0 1.5.83 2.8 2.1 3.66l-.5 1.9 2.2-1.2c.6.15 1.24.24 1.9.24 3.2 0 5.7-2.1 5.7-4.7s-2.5-4.6-5.7-4.6z"
                    fill="#DDBE7E"
                    opacity="0.9"
                  />
                </svg>
                <span class="kwb-title">你说过的话</span>
                <span class="kwb-year">{{ card.data?.year || '' }}</span>
                <span class="kwb-rule" aria-hidden="true" />
                <span class="kwb-author">著者 · 你</span>
                <span class="kwb-imprint">微信铸字车间 印行</span>
                <span class="kwb-gloss" aria-hidden="true" />
                <span class="kwb-hotspot" aria-hidden="true" />
              </span>
              <!-- 背面：封面内衬（不放任何文字，避免翻过来是镜像字）。
                   装饰全是无字工艺：布面包边 + 烫金内线 + 帘纹环衬纸 + 盲压徽记 -->
              <span class="kwb-back" aria-hidden="true">
                <span class="kwb-endpaper">
                  <span class="kwb-emblem" />
                </span>
              </span>
            </span>
            </span>
          </div>
        </div>

        <!-- 风暴落定后翻开的那本词典 -->
        <transition name="cloud-fade">
          <div v-if="phase === 'cloud'" class="absolute inset-0">
            <KeywordDictionarySpread
              :keywords="keywords"
              :examples="examples"
              :top-keyword="card.data?.topKeyword || null"
              :year="Number(card.data?.year) || 0"
              :meta="card.data?.meta || {}"
              :title="card.title"
              :reduced-motion="reducedMotion"
              :paused="!isVisible"
            />
          </div>
        </transition>

        <!-- 唯一的控件：浮在底部，不参与书的居中 -->
        <div v-if="phase === 'cloud'" class="kw-replay">
          <button type="button" class="kw-chip" @click="replay">再看一遍</button>
        </div>
      </div>
    </WrappedCardShell>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { gsap } from 'gsap'
import KeywordDictionarySpread from '~/components/wrapped/visualizations/KeywordDictionarySpread.vue'
import { parseTextWithEmoji } from '~/lib/wechat-emojis'
import { usePrivacyStore } from '~/stores/privacy'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const cardRoot = ref(null)
const overlayEl = ref(null)

// 'idle' → 'book'（合着的词典，等用户翻开）→ 'opening' → 'storm' → 'packed' → 'merge' → 'burst' → 'cloud'
const phase = ref('idle')
const bookEl = ref(null)
const bookCoverEl = ref(null)
// 消息从书里涌出：风暴气泡的出发点（视口坐标）
let stormOrigin = null
const hasPlayed = ref(false)
const accelerated = ref(true) // 默认加速

// 通知父级 deck 隐藏顶部 UI
const deckChromeHidden = inject('deckChromeHidden', ref(false))

const isAnimating = computed(() => ['storm', 'packed', 'merge', 'burst'].includes(phase.value))
const showOverlay = computed(() => isAnimating.value && !reducedMotion.value)

// phase 变化时同步 deck chrome 可见性
watch(phase, () => {
  deckChromeHidden.value = isAnimating.value
})

const reducedMotion = ref(false)
const detectReducedMotion = () => {
  if (!import.meta.client) return
  try {
    reducedMotion.value = !!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
  } catch {
    reducedMotion.value = false
  }
}

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const yearCn = computed(() => {
  const y = String(props.card?.data?.year || '')
  const map = { 0: '〇', 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九' }
  return y ? Array.from(y).map((c) => map[c] ?? c).join('') : ''
})

const topWord = computed(() => String(props.card?.data?.topKeyword?.word || '').trim())
const topCount = computed(() => Number(props.card?.data?.topKeyword?.count || 0))

const keywords = computed(() => Array.isArray(props.card?.data?.keywords) ? props.card.data.keywords : [])
const examples = computed(() => Array.isArray(props.card?.data?.examples) ? props.card.data.examples : [])
const bubblePool = computed(() => {
  const xs = Array.isArray(props.card?.data?.bubbleMessages) ? props.card.data.bubbleMessages : []
  return xs.map((x) => String(x || '')).filter((x) => x.trim())
})

const showHint = computed(() => (!reducedMotion.value) && phase.value === 'storm' && !accelerated.value)

const TOTAL_ANIMATION_LIMIT_MS = 10000
const STORM_STAGE_LIMIT_MS = 6200
const MERGE_MIN_BUDGET_MS = 1800
const PACKED_PAUSE_MS = 120

// 气泡状态
const bubbles = ref([])
let bubbleSeq = 0
const bubbleEls = new Map()
const registerBubbleEl = (id, el) => {
  if (!id) return
  if (el) bubbleEls.set(id, el)
  else bubbleEls.delete(id)
}

const clamp = (v, a, b) => Math.min(Math.max(v, a), b)
const lerp = (a, b, t) => a + (b - a) * t

const hash32 = (s) => {
  const str = String(s || '')
  let h = 2166136261
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

const mulberry32 = (a) => () => {
  let t = (a += 0x6D2B79F5)
  t = Math.imul(t ^ (t >>> 15), t | 1)
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296
}

const bubbleStyle = (b) => ({
  left: `${Math.round(Number(b.x || 0))}px`,
  top: `${Math.round(Number(b.y || 0))}px`,
  zIndex: String(10 + (Number(b.depth || 1) * 20) + (Number(b.id || 0) % 9))
})

let textMeasureCanvas = null
const getTextMeasureContext = () => {
  if (!import.meta.client) return null
  if (!textMeasureCanvas) {
    try {
      textMeasureCanvas = document.createElement('canvas')
    } catch {
      textMeasureCanvas = null
    }
  }
  return textMeasureCanvas?.getContext?.('2d') || null
}

const estimateTextWidth = (text, compact = false) => {
  const s = String(text || '')
  const ctx = getTextMeasureContext()
  if (ctx) {
    // 与 text-sm / text-[12px] 接近的字体测量。
    ctx.font = compact
      ? "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
      : "14px -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    return Math.max(0, ctx.measureText(s).width)
  }

  // SSR/异常回退估算。
  const chars = Array.from(s)
  return chars.reduce((acc, ch) => acc + (/[^\x00-\xff]/.test(ch) ? (compact ? 11 : 13) : (compact ? 7 : 8.5)), 0)
}

const bubbleSizeForText = (text, compact = false) => {
  const chars = Array.from(String(text || ''))
  const visualUnits = chars.reduce((acc, ch) => acc + (/[^\x00-\xff]/.test(ch) ? 1 : 0.56), 0)
  const raw = estimateTextWidth(text, compact)
  const minWBase = compact ? 56 : 74
  const minWLong = compact
    ? (visualUnits >= 18 ? 120 : (visualUnits >= 12 ? 90 : minWBase))
    : (visualUnits >= 26 ? 182 : (visualUnits >= 14 ? 122 : minWBase))
  const minW = Math.max(minWBase, minWLong)
  // 与聊天页一致：max-w-sm (24rem = 384px) 到达上限后再换行。
  const maxWByType = compact ? (visualUnits >= 18 ? 300 : 220) : 384
  const maxWByViewport = Math.max(140, (curViewW || 0) - 12)
  const maxW = Math.min(maxWByType, maxWByViewport)
  const paddingX = compact ? 22 : 26
  const preferredW = raw + paddingX
  const w = clamp(Math.round(preferredW), minW, maxW)

  const usableLineW = Math.max(1, w - paddingX)
  const lines = Math.max(1, Math.ceil(raw / usableLineW))

  // 不限制气泡高度：按估算行数增长，不做固定上限裁剪。
  const lineH = compact ? 16 : 20
  const paddingY = compact ? 12 : 14
  const h = Math.max(compact ? 26 : 32, Math.round((lines * lineH) + paddingY))

  return { w, h }
}

let stormTimer = null
let packedTimer = null
let mainTl = null
let hardStopTimer = null
let animationStartedAt = 0
let animationDeadlineAt = 0

// 记录全屏视口尺寸（storm 阶段使用）
let curViewW = 0
let curViewH = 0

const clearTimers = () => {
  if (stormTimer) clearTimeout(stormTimer)
  stormTimer = null
  if (packedTimer) clearTimeout(packedTimer)
  packedTimer = null
  if (hardStopTimer) clearTimeout(hardStopTimer)
  hardStopTimer = null
}

const armHardStop = () => {
  if (!import.meta.client) return
  if (hardStopTimer) clearTimeout(hardStopTimer)
  hardStopTimer = null
  const remain = Math.max(0, Math.round(animationDeadlineAt - performance.now()))
  hardStopTimer = setTimeout(() => {
    if (phase.value !== 'cloud') skipToCloud()
  }, remain + 8)
}

const stopParticles = () => {}

const killTimeline = () => {
  if (mainTl) {
    try { mainTl.kill() } catch {}
  }
  mainTl = null
}

const reset = () => {
  clearTimers()
  killTimeline()
  stopParticles()
  bubbles.value = []
  bubbleEls.clear()
  bubbleSeq = 0
  accelerated.value = true
  animationStartedAt = 0
  animationDeadlineAt = 0
  stormOrigin = null
  phase.value = 'idle'
}

const skipToCloud = () => {
  clearTimers()
  killTimeline()
  stopParticles()
  bubbles.value = []
  bubbleEls.clear()
  accelerated.value = true
  animationStartedAt = 0
  animationDeadlineAt = 0
  phase.value = 'cloud'
  hasPlayed.value = true
}

const replay = () => {
  hasPlayed.value = false
  reset()
  maybeStart()
}

const onStagePointerDown = (e) => {
  if (phase.value !== 'storm') return
  if (e?.target?.closest?.('[data-no-accel]')) return
  accelerated.value = true
}

// Visibility gating
const isVisible = ref(false)
let io = null
const updateVisibility = (v) => { isVisible.value = !!v }

// 卡片进入视野时先摆出合着的书，等用户翻开
const maybeStart = () => {
  if (!import.meta.client) return
  detectReducedMotion()

  const ready = props.card && props.card.status === 'ok' && props.card.data
  if (!ready) return
  if (!isVisible.value) return

  if (reducedMotion.value) {
    phase.value = 'cloud'
    hasPlayed.value = true
    return
  }

  if (hasPlayed.value) return
  if (phase.value !== 'idle') return
  phase.value = 'book'
}

// 卡包式悬浮：书跟着光标微倾，封面上有一粒跟手的反光
const bookStackEl = ref(null)
const onBookPointerMove = (e) => {
  if (phase.value !== 'book' || reducedMotion.value) return
  const el = bookEl.value
  const st = bookStackEl.value
  if (!el || !st) return
  const r = el.getBoundingClientRect()
  if (!r.width || !r.height) return
  const px = (e.clientX - r.left) / r.width
  const py = (e.clientY - r.top) / r.height
  const nx = px * 2 - 1
  const ny = py * 2 - 1
  gsap.to(st, {
    rotationY: -15 + nx * 7.5,
    rotationX: 4 - ny * 6,
    rotationZ: -0.6,
    duration: 0.5,
    ease: 'power2.out',
    overwrite: 'auto',
  })
  el.style.setProperty('--kx', `${Math.round(px * 100)}%`)
  el.style.setProperty('--ky', `${Math.round(py * 100)}%`)
}
const onBookPointerLeave = () => {
  const st = bookStackEl.value
  if (!st) return
  // 回到基准姿态后清掉行内 transform，交还给 CSS 呼吸动画
  gsap.to(st, {
    rotationY: -15,
    rotationX: 4,
    rotationZ: -0.6,
    duration: 0.7,
    ease: 'power3.out',
    overwrite: 'auto',
    clearProps: 'transform',
  })
}

// 翻开封面 → 记下书的位置作为风暴出发点 → 话从书里涌出来
const openBook = () => {
  if (!import.meta.client) return
  if (phase.value !== 'book') return

  phase.value = 'opening'

  const el = bookEl.value
  const cover = bookCoverEl.value
  if (!el || !cover) { startStorm(); return }

  // 悬浮倾斜让位：清掉行内姿态，翻页动画从基准开始
  if (bookStackEl.value) {
    gsap.killTweensOf(bookStackEl.value)
    bookStackEl.value.style.transform = ''
  }

  // 封面绕书脊向左翻开后，跨页的视觉重心会跑到容器中心左侧约半个封面宽，
  // 所以一边翻一边把整本右移，让「翻开后的样子」居中，而不是「合着的样子」居中。
  gsap.timeline()
    .to(el, { scale: 1.06, duration: 0.34, ease: 'power2.out' }, 0)
    .to(cover, { rotateY: -164, duration: 0.86, ease: 'power3.inOut' }, 0.06)
    .to(el, { x: 152, duration: 0.86, ease: 'power3.inOut' }, 0.06)
    .to(el, { scale: 1.14, duration: 0.5, ease: 'power2.in' }, 0.44)
    // 封面转到一半就放话出来，读起来才是「从书里涌出」而不是「翻完再放动画」
    .call(startStorm, null, 0.46)
}

const startStorm = () => {
  if (!import.meta.client) return
  if (phase.value !== 'opening') return

  // 话从「书此刻真正所在的位置」涌出，而不是点击那一瞬的位置
  const bel = bookEl.value
  if (bel) {
    const r = bel.getBoundingClientRect()
    stormOrigin = { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  } else {
    stormOrigin = null
  }

  // 使用全屏视口尺寸
  curViewW = window.innerWidth || 0
  curViewH = window.innerHeight || 0
  if (!curViewW || !curViewH) return

  // 开始 storm
  phase.value = 'storm'
  accelerated.value = true
  animationStartedAt = performance.now()
  animationDeadlineAt = animationStartedAt + TOTAL_ANIMATION_LIMIT_MS
  armHardStop()

  const vw = curViewW
  const vh = curViewH
  const area = vw * vh
  // 目标：先铺满一层，再形成二/三层重叠。
  const maxBubbles = clamp(Math.round(area / 1900), 240, 1600)
  const maxLayers = 3
  const targetBaseCoverage = 0.9985
  const targetLayer2Coverage = 0.20
  // 收束点＝书原来所在的位置：话从哪儿涌出来，就往哪儿收回去
  const centerX = stormOrigin ? stormOrigin.x : vw / 2
  const centerY = stormOrigin ? stormOrigin.y : vh / 2

  const seed = hash32(`${props.card?.data?.year || 0}|${props.card?.data?.topKeyword?.word || ''}|${Date.now()}`)
  const rng = mulberry32(seed)

  // 打乱气泡消息
  const msgs = bubblePool.value.length > 0
    ? [...bubblePool.value]
    : (keywords.value.length > 0 ? keywords.value.map((k) => String(k?.word || '')).filter((x) => x.trim()) : [])
  if (msgs.length === 0) {
    skipToCloud()
    return
  }
  for (let i = msgs.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    const tmp = msgs[i]
    msgs[i] = msgs[j]
    msgs[j] = tmp
  }
  let msgIdx = 0

  // ========== 网格系统 ==========
  const cell = 36 // 更细网格，提高覆盖检测精度
  const grid = new Map()
  const boxById = new Map()

  const cellKey = (cx, cy) => `${cx},${cy}`

  const addToGrid = (id, box) => {
    const minX = Math.floor(box.x / cell)
    const maxX = Math.floor((box.x + box.w) / cell)
    const minY = Math.floor(box.y / cell)
    const maxY = Math.floor((box.y + box.h) / cell)
    for (let x = minX; x <= maxX; x += 1) {
      for (let y = minY; y <= maxY; y += 1) {
        const k = cellKey(x, y)
        const arr = grid.get(k) || []
        arr.push(id)
        grid.set(k, arr)
      }
    }
  }

  const intersects = (a, b, margin) => !(
    (a.x + a.w + margin) <= b.x ||
    (b.x + b.w + margin) <= a.x ||
    (a.y + a.h + margin) <= b.y ||
    (b.y + b.h + margin) <= a.y
  )

  // 无边界留白，无中心留白，气泡可以铺满到边缘。
  // allowOverlap=false 时用于首层紧密铺满；true 时允许叠层（最多 maxLayers 层）。
  const canPlace = (box, margin, allowOverlap = false) => {
    if (box.x < 0 || box.y < 0 || (box.x + box.w) > vw || (box.y + box.h) > vh) return false

    // 第一层约束：真实覆盖到的网格不能超过最大层数。
    const minOX = Math.floor(box.x / cell)
    const maxOX = Math.floor((box.x + box.w) / cell)
    const minOY = Math.floor(box.y / cell)
    const maxOY = Math.floor((box.y + box.h) / cell)
    for (let cx = minOX; cx <= maxOX; cx += 1) {
      for (let cy = minOY; cy <= maxOY; cy += 1) {
        const arr = grid.get(cellKey(cx, cy))
        const layerCount = Array.isArray(arr) ? arr.length : 0
        if (layerCount >= maxLayers) return false
      }
    }

    if (allowOverlap) return true

    const minCX = minOX - 1
    const maxCX = maxOX + 1
    const minCY = minOY - 1
    const maxCY = maxOY + 1

    for (let cx = minCX; cx <= maxCX; cx += 1) {
      for (let cy = minCY; cy <= maxCY; cy += 1) {
        const arr = grid.get(cellKey(cx, cy))
        if (!arr) continue
        for (const id of arr) {
          const b = boxById.get(id)
          if (!b) continue
          if (intersects(box, b, margin)) return false
        }
      }
    }
    return true
  }

  // ========== Gap-filling: 找出未被覆盖的空网格单元格 ==========
  const gridCols = Math.ceil(vw / cell)
  const gridRows = Math.ceil(vh / cell)
  const totalCells = gridCols * gridRows

  const computeCoverage = (layerAtLeast = 1) => {
    let covered = 0
    for (let cy = 0; cy < gridRows; cy += 1) {
      for (let cx = 0; cx < gridCols; cx += 1) {
        const arr = grid.get(cellKey(cx, cy))
        if ((arr?.length || 0) >= layerAtLeast) covered += 1
      }
    }
    return totalCells > 0 ? covered / totalCells : 1
  }

  const findEmptyCells = () => {
    const empty = []
    for (let cy = 0; cy < gridRows; cy += 1) {
      for (let cx = 0; cx < gridCols; cx += 1) {
        const arr = grid.get(cellKey(cx, cy))
        if (!arr || arr.length === 0) {
          empty.push({ cx, cy })
        }
      }
    }
    return empty
  }

  // ========== 优先放置到空区域的 placeBox ==========
  const placeBox = (w, h) => {
    const emptyCells = findEmptyCells()

    // 优先在空网格区域放置
    if (emptyCells.length > 0) {
      const maxTries = Math.min(emptyCells.length, 24)
      for (let t = 0; t < maxTries; t += 1) {
        const idx = Math.floor(rng() * emptyCells.length)
        const { cx, cy } = emptyCells[idx]
        const baseX = cx * cell
        const baseY = cy * cell

        // 在空单元格位置附近放置，带微小随机偏移
        const x = clamp(Math.round(baseX + (rng() - 0.3) * cell * 0.5), 0, vw - w)
        const y = clamp(Math.round(baseY + (rng() - 0.3) * cell * 0.5), 0, vh - h)
        const box = { x, y, w, h }
        if (canPlace(box, 1, false)) return box

        // 重试：直接放在单元格起始位置
        const x2 = clamp(baseX, 0, vw - w)
        const y2 = clamp(baseY, 0, vh - h)
        const box2 = { x: x2, y: y2, w, h }
        if (canPlace(box2, -1, false)) return box2
      }
    }

    // 随机回退：允许重叠（最多三层），用于形成堆叠层次。
    for (let i = 0; i < 40; i += 1) {
      const x = Math.floor(rng() * Math.max(1, vw - w))
      const y = Math.floor(rng() * Math.max(1, vh - h))
      const box = { x, y, w, h }
      if (canPlace(box, -3, true)) return box
    }

    return null
  }

  // 高密度补缝：专门往未覆盖网格里塞紧凑泡泡，避免剩余缝隙。
  const placeGapFillBox = (text) => {
    const emptyCells = findEmptyCells()
    if (emptyCells.length === 0) return null
    const compactSz = bubbleSizeForText(text, true)
    // 过长文本不强塞补缝，避免出现“长消息窄气泡”。
    if (compactSz.w > 210) return null
    const w = compactSz.w
    const h = compactSz.h
    const tries = Math.min(64, emptyCells.length)
    for (let i = 0; i < tries; i += 1) {
      const idx = Math.floor(rng() * emptyCells.length)
      const { cx, cy } = emptyCells[idx]
      const baseX = cx * cell
      const baseY = cy * cell
      const x = clamp(Math.round(baseX + (cell - w) / 2), 0, vw - w)
      const y = clamp(Math.round(baseY + (cell - h) / 2), 0, vh - h)
      const box = { x, y, w, h }
      if (canPlace(box, -4, true)) return box
    }
    return null
  }

  const getLayerDepthForBox = (box) => {
    let existing = 0
    const minCX = Math.floor(box.x / cell)
    const maxCX = Math.floor((box.x + box.w) / cell)
    const minCY = Math.floor(box.y / cell)
    const maxCY = Math.floor((box.y + box.h) / cell)
    for (let cx = minCX; cx <= maxCX; cx += 1) {
      for (let cy = minCY; cy <= maxCY; cy += 1) {
        const layerCount = (grid.get(cellKey(cx, cy)) || []).length
        if (layerCount > existing) existing = layerCount
      }
    }
    return clamp(existing + 1, 1, maxLayers)
  }

  // ========== 逐个生成气泡 ==========
  let consecutiveFailures = 0
  const MAX_CONSECUTIVE_FAILURES = 80

  const spawnOne = () => {
    if (!isVisible.value) return
    if (phase.value !== 'storm') return
    const now = performance.now()
    const elapsed = animationStartedAt > 0 ? (now - animationStartedAt) : 0
    const remain = animationDeadlineAt > 0 ? (animationDeadlineAt - now) : TOTAL_ANIMATION_LIMIT_MS

    // 结束条件：底层覆盖近乎满屏，且有可见二层重叠；或达到上限；或连续失败。
    const coverage = computeCoverage(1)
    const layer2Coverage = computeCoverage(2)
    if (
      elapsed >= STORM_STAGE_LIMIT_MS ||
      remain <= MERGE_MIN_BUDGET_MS ||
      (coverage >= targetBaseCoverage && layer2Coverage >= targetLayer2Coverage) ||
      bubbles.value.length >= maxBubbles ||
      consecutiveFailures >= MAX_CONSECUTIVE_FAILURES
    ) {
      phase.value = 'packed'
      clearTimers()
      const packedPause = clamp(Math.round(Math.min(PACKED_PAUSE_MS, Math.max(36, remain - MERGE_MIN_BUDGET_MS))), 24, PACKED_PAUSE_MS)
      packedTimer = setTimeout(() => runMergeBurst(rng, centerX, centerY), packedPause)
      return
    }

    const text = msgs.length > 0 ? msgs[msgIdx % msgs.length] : ''
    msgIdx += 1

    const sz = bubbleSizeForText(text)
    let box = placeBox(sz.w, sz.h)

    // 如果标准尺寸放不下，尝试紧凑尺寸
    if (!box) {
      const compactSz = bubbleSizeForText(text, true)
      box = placeBox(compactSz.w, compactSz.h)
      if (box) {
        box = { ...box, w: compactSz.w, h: compactSz.h }
      }
    }

    if (!box) {
      box = placeGapFillBox(text)
    }

    if (!box) {
      consecutiveFailures += 1
    } else {
      consecutiveFailures = 0
      const depth = getLayerDepthForBox(box)
      const id = ++bubbleSeq
      boxById.set(id, box)
      addToGrid(id, box)
      bubbles.value = [...bubbles.value, {
        id, text, x: box.x, y: box.y, w: box.w, h: box.h,
        segments: parseTextWithEmoji(text),
        depth
      }]

      requestAnimationFrame(() => {
        const el = bubbleEls.get(id)
        if (!el) return
        if (stormOrigin) {
          // 每条消息都从书里飞出来，落到自己的位置
          const dx = stormOrigin.x - (box.x + box.w / 2)
          const dy = stormOrigin.y - (box.y + box.h / 2)
          gsap.fromTo(
            el,
            { opacity: 0, scale: 0.28, x: dx, y: dy, rotate: (rng() - 0.5) * 26 },
            { opacity: 1, scale: 1, x: 0, y: 0, rotate: 0, duration: 0.52, ease: 'power3.out' }
          )
        } else {
          gsap.fromTo(
            el,
            { opacity: 0, scale: 0.94, y: 10 },
            { opacity: 1, scale: 1, y: 0, duration: 0.18, ease: 'power2.out' }
          )
        }
      })
    }

    // 加速模式下极快生成
    const interval = accelerated.value ? 12 : Math.max(16, Math.round(lerp(420, 32, (bubbles.value.length / Math.max(1, maxBubbles)) ** 2)))
    stormTimer = setTimeout(spawnOne, interval)
  }

  // 启动
  spawnOne()
}

const runMergeBurst = (rng, centerX, centerY) => {
  if (!import.meta.client) return
  if (!isVisible.value) return
  if (phase.value !== 'packed') return

  const now = performance.now()
  const remainMs = animationDeadlineAt > 0 ? Math.max(0, animationDeadlineAt - now) : TOTAL_ANIMATION_LIMIT_MS
  if (remainMs <= 140) {
    skipToCloud()
    return
  }

  const els = []
  const deltas = []
  const dist = []
  for (const b of bubbles.value) {
    const el = bubbleEls.get(b.id)
    if (!el) continue
    const dx = (centerX - (b.x + b.w / 2))
    const dy = (centerY - (b.y + b.h / 2))
    const d = Math.hypot(dx, dy)
    els.push(el)
    deltas.push({ dx, dy, b })
    dist.push(d)
  }

  // 按距离排序：远的先动
  const order = els.map((_, i) => i).sort((a, b) => dist[b] - dist[a])
  const elsSorted = order.map((i) => els[i])
  const deltasSorted = order.map((i) => deltas[i])

  phase.value = 'merge'
  killTimeline()

  // 根据剩余时间动态压缩 merge/burst，确保总时长不超过 10s。
  const availableMs = Math.max(260, remainMs - 40)
  const availableSec = availableMs / 1000
  const n = Math.max(1, elsSorted.length)

  const mergeDur = clamp((availableMs * 0.32) / 1000, 0.26, 0.80)
  const squeezeDur = clamp((availableMs * 0.08) / 1000, 0.06, 0.14)
  const burstDur = clamp((availableMs * 0.18) / 1000, 0.18, 0.45)

  const mergeStaggerBudget = Math.max(0, (availableMs * 0.22) / 1000)
  const burstStaggerBudget = Math.max(0, (availableMs * 0.12) / 1000)
  const staggerMerge = n > 1 ? Math.min(0.0035, mergeStaggerBudget / (n - 1)) : 0
  const staggerBurst = n > 1 ? Math.min(0.0018, burstStaggerBudget / (n - 1)) : 0

  mainTl = gsap.timeline({
    defaults: { ease: 'power3.inOut' },
    onUpdate: () => {
      if (animationDeadlineAt > 0 && performance.now() >= animationDeadlineAt && phase.value !== 'cloud') {
        skipToCloud()
      }
    },
    onComplete: () => {
      bubbles.value = []
      bubbleEls.clear()
      clearTimers()
      animationStartedAt = 0
      animationDeadlineAt = 0
      phase.value = 'cloud'
      hasPlayed.value = true
      stopParticles()
    }
  })

  mainTl.to(elsSorted, {
    duration: mergeDur,
    x: (i) => {
      const it = deltasSorted[i]
      const jitter = (rng() - 0.5) * 18
      return it.dx + jitter
    },
    y: (i) => {
      const it = deltasSorted[i]
      const jitter = (rng() - 0.5) * 18
      return it.dy + jitter
    },
    scale: 0.72,
    opacity: 0.15,
    stagger: staggerMerge
  })

  mainTl.call(() => { phase.value = 'burst' })

  mainTl.to(elsSorted, { duration: squeezeDur, scale: 0.66, ease: 'power2.in' })

  const vw = curViewW || window.innerWidth
  const vh = curViewH || window.innerHeight
  const burstOffsets = deltasSorted.map(() => {
    const ang = rng() * Math.PI * 2
    const rad = Math.min(vw, vh) * (0.28 + rng() * 0.45)
    return { x: Math.cos(ang) * rad, y: Math.sin(ang) * rad }
  })

  mainTl.to(elsSorted, {
    duration: burstDur,
    x: (i) => {
      const it = deltasSorted[i]
      return it.dx + (burstOffsets[i]?.x || 0)
    },
    y: (i) => {
      const it = deltasSorted[i]
      return it.dy + (burstOffsets[i]?.y || 0)
    },
    opacity: 0,
    scale: 0.92,
    ease: 'power3.out',
    stagger: staggerBurst
  })

  const tlTotal = mainTl.totalDuration()
  if (tlTotal > availableSec && availableSec > 0.06) {
    mainTl.timeScale(Math.max(1, tlTotal / availableSec))
  }
}

watch(
  () => [isVisible.value, props.card?.status, props.card?.data?.year],
  () => {
    if (!import.meta.client) return
    if (!isVisible.value) {
      if (phase.value !== 'cloud') {
        reset()
      } else {
        clearTimers()
        killTimeline()
        stopParticles()
      }
      return
    }
    maybeStart()
  }
)

onMounted(() => {
  privacyStore.init()
  if (!import.meta.client) return
  detectReducedMotion()

  if (typeof IntersectionObserver !== 'undefined' && cardRoot.value) {
    io = new IntersectionObserver(
      (entries) => {
        const ent = entries && entries[0]
        updateVisibility(!!ent?.isIntersecting && (ent.intersectionRatio || 0) >= 0.35)
      },
      { threshold: [0, 0.35, 0.6, 1] }
    )
    io.observe(cardRoot.value)
  } else {
    isVisible.value = true
  }

  maybeStart()
})

onBeforeUnmount(() => {
  io?.disconnect?.()
  io = null
  // 确保 deck chrome 恢复
  deckChromeHidden.value = false
  reset()
})
</script>

<style scoped>
.kw-stage {
  transition: none !important;
}

.kw-overlay {
  /* 确保不受父级 transform 影响 */
  contain: layout;
  /* 保持年度总结原背景，不再强制改成绿色底色。 */
  background: transparent;
}

.kw-halo {
  background: radial-gradient(circle at center, rgba(7, 193, 96, 0.16) 0%, rgba(7, 193, 96, 0.06) 38%, transparent 72%);
}

/* ───────── 合着的年度词典 ─────────
   要点：书本身是一个有厚度的 3D 物体（封面 / 书脊 / 书口 / 底封各占一个面），
   放在透视里由一盏偏左上的灯照着，而不是一张画了阴影的平面矩形。 */
.kwb {
  position: relative;
  width: 384px;
  height: 536px;
  cursor: pointer;
  outline: none;
  perspective: 2400px;
  perspective-origin: 52% 42%;
  will-change: transform;
  /* 纸的「肌理」：feTurbulence 细噪点，透明度压到 5% 上下——只该被手感觉到，不该被眼睛看到 */
  --kwb-grain: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' seed='7' stitchTiles='stitch'/%3E%3CfeColorMatrix type='matrix' values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.55 0.55 0.55 0 0'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23g)' opacity='0.055'/%3E%3C/svg%3E");
}

/* 书体：整体略微侧转，才看得见厚度 */
.kwb-body,
.kwb-cover,
.kwb-block,
.kwb-spine,
.kwb-shadow { position: absolute; }

.kwb-stack {
  position: absolute;
  inset: 0;
  transform-style: preserve-3d;
  transform: rotateX(4deg) rotateY(-15deg) rotateZ(-0.6deg);
  animation: kwb-breathe 11s ease-in-out infinite alternate;
}
@keyframes kwb-breathe {
  from { transform: rotateX(4deg) rotateY(-15deg) rotateZ(-0.6deg) translate3d(0, -5px, 0); }
  to   { transform: rotateX(5.4deg) rotateY(-11.5deg) rotateZ(-0.6deg) translate3d(0, 5px, 0); }
}
.kwb--open .kwb-stack { animation: none; }

/* 落影：书是斜的，影子也跟着偏，并且贴地一侧最实 */
.kwb-shadow {
  left: -4%;
  right: -12%;
  bottom: -30px;
  height: 66px;
  background:
    radial-gradient(44% 50% at 40% 40%, rgba(42, 33, 18, 0.40), rgba(42, 33, 18, 0) 76%),
    radial-gradient(78% 44% at 56% 48%, rgba(42, 33, 18, 0.16), rgba(42, 33, 18, 0) 80%);
  filter: blur(11px);
  transform: skewX(-9deg);
}

/* 书口：整摞纸的侧面，靠书脊一端被压暗，靠外一端受光 */
.kwb-block {
  left: 18px;
  right: -14px;
  top: 7px;
  bottom: 3px;
  border-radius: 2px 6px 6px 2px;
  transform: translateZ(-6px);
  background:
    repeating-linear-gradient(90deg, rgba(122, 104, 74, 0.30) 0 0.5px, rgba(255, 253, 246, 0) 0.5px 2.4px),
    linear-gradient(90deg, #DED5C0 0%, #F4EFE2 26%, #FDFBF5 58%, #E9E1CE 86%, #CFC4AB 100%);
  box-shadow:
    inset -4px 0 7px rgba(108, 90, 60, 0.30),
    inset 0 2px 3px rgba(255, 255, 255, 0.75),
    inset 0 -3px 6px rgba(108, 90, 60, 0.22);
  transition: background 420ms ease;
}
.kwb--open .kwb-block {
  background:
    linear-gradient(90deg, rgba(120, 102, 72, 0.18) 0 1px, rgba(255, 255, 255, 0) 1px 100%),
    radial-gradient(130% 96% at 10% 8%, #FFFEFA 0%, rgba(255, 253, 248, 0) 62%),
    linear-gradient(100deg, #F6F2E7 0%, #FCFAF4 48%, #EDE7D7 100%);
  box-shadow: inset 12px 0 24px rgba(120, 102, 72, 0.18);
}

/* ── 书芯首页（扉页）。合着时不可见，翻开时随封面过半淡入 ── */
.kwb-leaf {
  position: absolute;
  inset: 0;
  border-radius: 2px 6px 6px 2px;
  overflow: hidden;
  opacity: 0;
  transition: opacity 520ms ease 240ms;
  background:
    var(--kwb-grain),
    repeating-linear-gradient(0deg, rgba(146, 128, 96, 0.035) 0 1px, rgba(255, 255, 255, 0) 1px 4px),
    radial-gradient(130% 96% at 12% 6%, #FFFEFB 0%, rgba(255, 254, 249, 0) 60%),
    radial-gradient(110% 90% at 92% 96%, rgba(233, 226, 211, 0.72) 0%, rgba(233, 226, 211, 0) 58%),
    linear-gradient(100deg, #F5F1E6 0%, #FCFAF4 46%, #F0EADA 100%);
}
.kwb--open .kwb-leaf { opacity: 1; }

/* 订口弧光：纸在铰链处卷进书脊——先暗、隔一道受光的弧脊、再归平 */
.kwb-leaf::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg,
    rgba(107, 90, 60, 0.26) 0,
    rgba(107, 90, 60, 0.10) 9px,
    rgba(255, 255, 255, 0.55) 24px,
    rgba(255, 255, 255, 0) 46px,
    rgba(255, 255, 255, 0) 100%);
}

/* 书口叠纸：右缘露出一指宽的下层纸痕，暗示这是一摞纸的第一张 */
.kwb-leaf::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  width: 9px;
  border-radius: 0 6px 6px 0;
  background: repeating-linear-gradient(90deg, rgba(120, 102, 72, 0.15) 0 1px, rgba(255, 253, 246, 0.85) 1px 2.6px);
  box-shadow: inset -1px 0 1px rgba(120, 102, 72, 0.22);
}

/* 扉页排印：凸版口吻——墨色偏暖、字缝里嵌一线纸白（letterpress 压痕） */
.kwb-print {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 92px 30px 0 36px;
  gap: 17px;
  -webkit-font-smoothing: antialiased;
}
.kwb-ht-kicker {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.52em;
  text-indent: 0.52em;
  color: rgba(90, 78, 60, 0.60);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.72);
}
.kwb-ht-title {
  font-size: 31px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: 0.34em;
  text-indent: 0.34em;
  color: #352D20;
  text-shadow:
    0 1px 0 rgba(255, 255, 255, 0.66),
    0 -1px 0 rgba(88, 72, 48, 0.12);
}
/* 文武线：一粗一细，老排印的题名框线 */
.kwb-ht-rule {
  width: 96px;
  height: 6px;
  border-top: 1.5px solid rgba(88, 72, 48, 0.36);
  border-bottom: 0.5px solid rgba(88, 72, 48, 0.24);
}
/* 一点词典红：中缝菱花，和最终跨页里的检字红同源 */
.kwb-ht-loz {
  width: 7px;
  height: 7px;
  margin-top: 2px;
  border-radius: 1px;
  transform: rotate(45deg);
  background: #A8412C;
  opacity: 0.82;
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.34),
    0 1px 1px rgba(120, 40, 24, 0.28);
}
.kwb-ht-imprint {
  margin-top: 2px;
  font-size: 10px;
  letter-spacing: 0.3em;
  text-indent: 0.3em;
  color: rgba(110, 98, 80, 0.62);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.6);
  font-variant-numeric: tabular-nums;
}
.kwb-ht-num { letter-spacing: 0.04em; }
/* 卷首用小罗马页码 */
.kwb-ht-folio {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 20px;
  text-align: center;
  font-size: 10px;
  font-style: italic;
  color: rgba(120, 108, 88, 0.52);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5);
}

.kwb-ribbon {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

/* 书脊：圆脊，中间最亮两侧收暗，顶底各一条起脊线 */
.kwb-spine {
  left: 0;
  top: 0;
  bottom: 0;
  width: 34px;
  border-radius: 8px 1px 1px 8px;
  transform: translateZ(1px);
  background:
    linear-gradient(90deg,
      #06110A 0%, #0C2213 12%, #1B4A2D 38%, #23583A 52%, #143423 70%, #0A1B10 90%, #050D08 100%);
  box-shadow: inset -3px 0 7px rgba(0, 0, 0, 0.6);
}
.kwb-spine::before,
.kwb-spine::after {
  content: '';
  position: absolute;
  left: 4px;
  right: 4px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(203, 172, 112, 0.34), transparent);
}
.kwb-spine::before { top: 62px; }
.kwb-spine::after { bottom: 62px; }

.kwb-cover {
  inset: 0 0 0 20px;
  border-radius: 1px 7px 7px 1px;
  transform-origin: 0% 50%;
  transform-style: preserve-3d;
  transform: translateZ(8px);
}

.kwb-face,
.kwb-back {
  position: absolute;
  inset: 0;
  border-radius: 1px 7px 7px 1px;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  overflow: hidden;
}

/* 内衬底＝封面布往里包的「包边」：同一块布，受光比正面亮半档 */
.kwb-back {
  transform: rotateY(180deg);
  background:
    repeating-linear-gradient(0deg, rgba(255, 246, 226, 0.030) 0 1px, rgba(0, 0, 0, 0.026) 1px 2px),
    repeating-linear-gradient(90deg, rgba(255, 246, 226, 0.024) 0 1px, rgba(0, 0, 0, 0.022) 1px 2px),
    radial-gradient(120% 80% at 24% 4%, rgba(235, 255, 240, 0.10), rgba(235, 255, 240, 0) 52%),
    linear-gradient(154deg, #17492D 0%, #10351F 52%, #081F10 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 240, 214, 0.10),
    inset 0 0 30px rgba(0, 0, 0, 0.32);
}

/* 环衬纸：帘纹（横向帘线 + 竖向链线）+ 细噪点，四周留出布面包边，
   纸与布的交界压一道烫金内线（真精装的 turn-in tooling） */
.kwb-endpaper {
  position: absolute;
  inset: 13px;
  border-radius: 1px 4px 4px 1px;
  background:
    var(--kwb-grain),
    repeating-linear-gradient(0deg, rgba(146, 128, 96, 0.050) 0 1px, rgba(255, 255, 255, 0) 1px 4px),
    repeating-linear-gradient(90deg, rgba(146, 128, 96, 0.040) 0 1px, rgba(255, 255, 255, 0) 1px 26px),
    radial-gradient(115% 85% at 30% 10%, #FCFAF3 0%, rgba(252, 250, 243, 0) 55%),
    linear-gradient(168deg, #F4EFE2 0%, #EAE3D1 58%, #DCD2BC 100%);
  box-shadow:
    0 0 0 1px rgba(212, 180, 118, 0.40),
    0 0 0 2.5px rgba(20, 15, 6, 0.50),
    inset -10px 0 22px rgba(112, 94, 64, 0.20),
    inset 2px 0 5px rgba(255, 255, 255, 0.5),
    inset 0 -3px 10px rgba(112, 94, 64, 0.10);
}

/* 盲压徽记：不烫金、不带字，只靠纸面凹陷的光影成形（上缘压暗、下缘接光）。
   三层：外盘、内环、中心菱花，呼应封面边框的几何语言 */
.kwb-emblem {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 152px;
  height: 152px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at 50% 40%, rgba(101, 84, 55, 0.075), rgba(101, 84, 55, 0.022) 56%, rgba(101, 84, 55, 0) 70%);
  box-shadow:
    inset 0 2.5px 3px rgba(101, 84, 55, 0.40),
    inset 0 -1.5px 2px rgba(255, 255, 255, 0.88),
    0 1px 0 rgba(255, 255, 255, 0.68),
    0 -1px 1px rgba(101, 84, 55, 0.18);
}
.kwb-emblem::before {
  content: '';
  position: absolute;
  inset: 13px;
  border-radius: 50%;
  box-shadow:
    inset 0 1.5px 2px rgba(101, 84, 55, 0.32),
    inset 0 -1px 1px rgba(255, 255, 255, 0.72);
}
.kwb-emblem::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 46px;
  height: 46px;
  border-radius: 6px;
  transform: translate(-50%, -50%) rotate(45deg);
  box-shadow:
    inset 0 1.5px 2px rgba(101, 84, 55, 0.34),
    inset 0 -1px 1px rgba(255, 255, 255, 0.68);
}

/* 封面：细布纹 + 沿书脊的暗部 + 左上受光，边缘一圈倒角高光 */
.kwb-face {
  background:
    repeating-linear-gradient(0deg, rgba(255, 246, 226, 0.034) 0 1px, rgba(0, 0, 0, 0.030) 1px 2px),
    repeating-linear-gradient(90deg, rgba(255, 246, 226, 0.026) 0 1px, rgba(0, 0, 0, 0.026) 1px 2px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.46) 0%, rgba(0, 0, 0, 0) 16%),
    radial-gradient(120% 78% at 26% 4%, rgba(235, 255, 240, 0.14), rgba(235, 255, 240, 0) 54%),
    radial-gradient(110% 86% at 96% 100%, rgba(0, 0, 0, 0.36), rgba(0, 0, 0, 0) 56%),
    linear-gradient(154deg, #1C5B39 0%, #123F27 46%, #07230F 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 240, 214, 0.17),
    inset -1px 0 0 rgba(255, 240, 214, 0.08),
    inset 0 -1px 0 rgba(0, 0, 0, 0.55),
    inset 0 0 60px rgba(0, 0, 0, 0.30);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 13px;
  padding: 0 34px 96px;
}

.kwb-frame {
  position: absolute;
  inset: 30px 26px;
  border: 1px solid rgba(206, 176, 116, 0.46);
  border-radius: 1px;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.48), inset 0 1px 0 rgba(0, 0, 0, 0.36);
}
.kwb-frame::after {
  content: '';
  position: absolute;
  inset: 6px;
  border: 0.5px solid rgba(206, 176, 116, 0.22);
}

.kwb-seal {
  width: 46px;
  height: 46px;
  margin-bottom: 2px;
  filter: drop-shadow(0 1px 0 rgba(0, 0, 0, 0.5));
}

.kwb-year {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.34em;
  text-indent: 0.34em;
  color: rgba(200, 172, 118, 0.78);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.55);
  font-variant-numeric: tabular-nums;
}

.kwb-author {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 128px;
  text-align: center;
  font-size: 10.5px;
  letter-spacing: 0.3em;
  text-indent: 0.3em;
  color: rgba(200, 172, 118, 0.62);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.5);
}

.kwb-imprint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 112px;
  text-align: center;
  font-size: 8px;
  letter-spacing: 0.26em;
  text-indent: 0.26em;
  color: rgba(200, 172, 118, 0.34);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.45);
}

/* 跟手的封面反光（卡包式悬浮） */
.kwb-hotspot {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.35s ease;
  background: radial-gradient(300px circle at var(--kx, 50%) var(--ky, 40%), rgba(255, 250, 228, 0.14), transparent 62%);
}
.kwb:hover .kwb-hotspot {
  opacity: 1;
}

/* 腰封：一条环绕整摞书的纸带（书脊缘到书口缘），浮在封面前 */
.kwb-obi {
  position: absolute;
  left: 1px;
  right: -14px;
  bottom: 5px;
  height: 88px;
  transform: translateZ(11px);
  border-radius: 2px;
  background:
    repeating-linear-gradient(0deg, rgba(146, 128, 96, 0.04) 0 1px, rgba(255, 255, 255, 0) 1px 4px),
    linear-gradient(90deg, rgba(120, 102, 72, 0.22) 0%, rgba(120, 102, 72, 0) 4%, rgba(120, 102, 72, 0) 94%, rgba(120, 102, 72, 0.26) 100%),
    linear-gradient(180deg, #FBF7EC 0%, #F3EDDD 62%, #E9E1CC 100%);
  box-shadow:
    0 -3px 9px rgba(0, 0, 0, 0.30),
    0 3px 7px rgba(30, 40, 30, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    inset 0 -2px 4px rgba(120, 102, 72, 0.18);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 0 34px 0 46px;
  opacity: 1;
  transition: opacity 0.32s ease;
}
/* 翻开时腰封退场（带子从书上滑掉） */
.kwb--open .kwb-obi {
  opacity: 0;
  pointer-events: none;
}
.kwb-obi::before {
  content: '';
  position: absolute;
  top: 6px;
  left: 18px;
  right: 18px;
  height: 2px;
  background: linear-gradient(90deg, rgba(7, 113, 62, 0), rgba(7, 113, 62, 0.55), rgba(7, 113, 62, 0));
}
.kwb-obi-kicker {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.4em;
  text-indent: 0.4em;
  color: #A8412C;
}
.kwb-obi-title {
  max-width: 100%;
  font-size: 14.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0B3D26;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kwb-obi-meta {
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: rgba(53, 45, 32, 0.55);
  font-variant-numeric: tabular-nums;
}

/* 书名＝这张卡的标题，烫金压印：金属渐变 + 下压投影 */
.kwb-title {
  max-width: 300px;
  text-align: center;
  font-family: 'Songti SC', 'STSong', 'SimSun', serif;
  font-size: 33px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: 0.24em;
  text-indent: 0.24em;
  background: linear-gradient(172deg, #FBEFCB 0%, #DDBE7E 30%, #A98753 54%, #F3E2B4 74%, #C9A968 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 1px 0 rgba(0, 0, 0, 0.62)) drop-shadow(0 0 12px rgba(216, 190, 134, 0.12));
}

.kwb-rule {
  width: 66px;
  height: 1px;
  background: linear-gradient(90deg, rgba(206, 176, 116, 0), rgba(206, 176, 116, 0.74), rgba(206, 176, 116, 0));
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.5);
}

/* （封面脚注并入腰封） */

/* 灯从左上扫过封面 */
.kwb-gloss {
  position: absolute;
  top: -30%;
  bottom: -30%;
  left: -60%;
  width: 42%;
  background: linear-gradient(100deg, rgba(255, 255, 255, 0) 0%, rgba(255, 246, 224, 0.085) 46%, rgba(255, 255, 255, 0) 100%);
  transform: rotate(9deg);
  animation: kwb-gloss 8.5s ease-in-out infinite;
}
@keyframes kwb-gloss {
  0%, 66% { transform: translate3d(0, 0, 0) rotate(9deg); }
  100% { transform: translate3d(480px, 0, 0) rotate(9deg); }
}

.kwb:hover .kwb-stack,
.kwb:focus-visible .kwb-stack {
  animation: none;
  transform: rotateX(3deg) rotateY(-9deg) rotateZ(-0.4deg) translate3d(0, -4px, 0) scale(1.015);
  transition: transform 460ms cubic-bezier(0.32, 0.72, 0, 1);
}

@media (prefers-reduced-motion: reduce) {
  .kwb-stack, .kwb-gloss { animation: none; }
}

.kw-replay {
  position: absolute;
  right: 26px;
  bottom: 20px;
  display: flex;
  justify-content: flex-end;
  pointer-events: none;
  z-index: 20;
}
.kw-replay > * { pointer-events: auto; }

.kw-chip {
  font-size: 11px;
  line-height: 1;
  padding: 7px 10px;
  border-radius: 9999px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(255, 255, 255, 0.55);
  color: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(10px);
  transition: background 160ms ease, transform 160ms ease, color 160ms ease, border-color 160ms ease;
}

.kw-chip:hover {
  background: rgba(255, 255, 255, 0.72);
  transform: translateY(-1px);
}

.kw-bubble {
  will-change: transform, opacity;
  transform: translate3d(0, 0, 0);
}

.kw-bubble--d1 .msg-bubble { box-shadow: 0 4px 10px rgba(0, 0, 0, 0.10); }
.kw-bubble--d2 .msg-bubble { box-shadow: 0 8px 16px rgba(0, 0, 0, 0.13); }
.kw-bubble--d3 .msg-bubble { box-shadow: 0 12px 22px rgba(0, 0, 0, 0.16); }

.cloud-fade-enter-active,
.cloud-fade-leave-active {
  transition: opacity 800ms ease, transform 800ms cubic-bezier(0.22, 1, 0.36, 1);
}
.cloud-fade-enter-from,
.cloud-fade-leave-to {
  opacity: 0;
  transform: scale(0.96);
}
</style>
