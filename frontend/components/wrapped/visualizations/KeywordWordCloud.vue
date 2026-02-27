<template>
  <div ref="rootEl" class="kw-cloud relative w-full h-full select-none">
    <!-- Words -->
    <div
      class="absolute inset-0"
      :class="shouldAnimate ? 'kw-animate' : ''"
      @pointerdown="onBgPointerDown"
    >
      <div class="kw-cloud-core" :style="{ '--cloud-scale': String(cloudScale) }">
        <div class="kw-cloud-halo" aria-hidden="true" />
          <button
            v-for="(w, idx) in placedWords"
            :key="w.word"
            type="button"
            class="kw-word"
            :class="selectedWord === w.word ? 'kw-word--selected' : ''"
            :style="wordStyle(w, idx)"
            :title="`${w.word} · ${formatInt(w.count)} 次`"
            @pointerdown.stop="selectWord(w.word, $event)"
          >
            <span class="wrapped-privacy-keyword">{{ w.word }}</span>
          </button>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="placedWords.length === 0" class="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div class="rounded-2xl border border-[#EDEDED] bg-white/70 backdrop-blur px-5 py-4 text-center">
          <div class="wrapped-title text-base text-[#000000e6]">暂无常用语</div>
          <div class="mt-1 wrapped-body text-sm text-[#7F7F7F]">这一年你还没有足够的重复短句来生成常用语词云。</div>
        </div>
      </div>

      <!-- Examples panel -->
      <Teleport to="body">
        <transition name="kw-panel">
          <div
            v-if="selectedInfo"
            class="kw-panel fixed z-[100] w-[min(92%,420px)] rounded-2xl border border-[#EDEDED] bg-white/80 backdrop-blur shadow-[0_16px_40px_rgba(0,0,0,0.14)] overflow-hidden"
            :class="{ 'wrapped-privacy': privacyMode }"
            :style="panelStyle"
            data-no-accel
            @pointerdown.stop
          >
            <div class="flex items-start justify-between gap-3 px-4 pt-4 pb-2 border-b border-[#F3F3F3]">
              <div class="min-w-0">
                <div class="wrapped-title text-base text-[#000000e6] truncate">
                  <span class="wrapped-privacy-keyword">{{ selectedInfo.word }}</span>
                  <span class="wrapped-number text-sm text-[#07C160] font-semibold">· {{ formatInt(selectedInfo.count) }} 次</span>
                </div>
                <div class="mt-0.5 wrapped-body text-xs text-[#7F7F7F]">
                  点击其它词，看看它出现的瞬间
                </div>
              </div>

              <button
                type="button"
                class="inline-flex items-center justify-center w-8 h-8 rounded-full text-[#00000066] hover:bg-[#00000008] transition"
                aria-label="关闭"
                @click="clearSelection"
              >
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M18 6L6 18" />
                  <path d="M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="px-4 py-3 max-h-[220px] overflow-auto">
              <div v-if="selectedInfo.messages.length === 0" class="wrapped-body text-sm text-[#7F7F7F]">
                没找到可展示的例句。
              </div>

              <div v-else class="space-y-2">
                <div
                  v-for="(m, i) in selectedInfo.messages"
                  :key="`${selectedInfo.word}-${i}-${m.raw}`"
                  class="flex justify-end"
                >
                  <div class="relative bubble-tail-r bg-[#95EC69] msg-radius px-3 py-2 shadow-[0_6px_16px_rgba(0,0,0,0.12)] max-w-[92%]">
                    <div class="wrapped-body text-sm text-[#000000e6] leading-snug whitespace-pre-wrap break-words wrapped-privacy-message">
                      <span v-if="Array.isArray(m.segments) && m.segments.length > 0">
                        <span v-for="(seg, sidx) in m.segments" :key="`${selectedInfo.word}-${i}-${sidx}`">
                          <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                          <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                        </span>
                      </span>
                      <span v-else>{{ m.raw }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition>
      </Teleport>
    </div>
  </template>

  <script setup>
  import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { storeToRefs } from 'pinia'
  import { parseTextWithEmoji } from '~/utils/wechat-emojis'
  import { usePrivacyStore } from '~/stores/privacy'

const props = defineProps({
  keywords: { type: Array, default: () => [] }, // [{word,count,weight}]
  examples: { type: Array, default: () => [] }, // [{word,count,messages:[]}]
  animate: { type: Boolean, default: true },
  reducedMotion: { type: Boolean, default: false }
})

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const rootEl = ref(null)
const width = ref(0)
const height = ref(0)

let resizeObserver = null
const updateSize = () => {
  if (!import.meta.client) return
  const rect = rootEl.value?.getBoundingClientRect?.()
  if (!rect) return
  width.value = Math.max(0, Math.round(rect.width || 0))
  height.value = Math.max(0, Math.round(rect.height || 0))
}

const shouldAnimate = computed(() => !!props.animate && !props.reducedMotion)

const examplesMap = computed(() => {
  const out = new Map()
  const list = Array.isArray(props.examples) ? props.examples : []
  for (const x of list) {
    const w = String(x?.word || '').trim()
    if (!w) continue
    const cnt = Number(x?.count || 0)
    const msgs = Array.isArray(x?.messages) ? x.messages.map((m) => String(m || '')).filter((m) => m.trim()) : []
    out.set(w, {
      word: w,
      count: Number.isFinite(cnt) ? cnt : 0,
      messages: msgs.slice(0, 3).map((m) => ({ raw: m, segments: parseTextWithEmoji(m) }))
    })
  }
  return out
})

const selectedWord = ref('')
const mousePos = ref({ x: 0, y: 0 })
const selectedInfo = computed(() => {
  const w = String(selectedWord.value || '').trim()
  if (!w) return null
  const ex = examplesMap.value.get(w)
  if (ex) return ex

  // Fallback: if examples missing, still show count from keywords.
  const kw = (Array.isArray(props.keywords) ? props.keywords : []).find((k) => String(k?.word || '').trim() === w)
  const cnt = kw ? Number(kw.count || 0) : 0
  return { word: w, count: Number.isFinite(cnt) ? cnt : 0, messages: [] }
})

const clearSelection = () => { selectedWord.value = '' }
const selectWord = (w, e) => {
  selectedWord.value = String(w || '').trim()
  if (e && Number.isFinite(e.clientX) && Number.isFinite(e.clientY)) {
    mousePos.value = { x: e.clientX, y: e.clientY }
  }
}

const panelStyle = computed(() => {
  if (!import.meta.client) return {}

  const vw = window.innerWidth || 0
  const vh = window.innerHeight || 0
  const maxW = 420
  const maxH = 280
  const margin = 12

  let left = mousePos.value.x + 20
  let top = mousePos.value.y - (maxH / 2)

  if ((left + maxW) > (vw - margin)) {
    left = mousePos.value.x - maxW - 20
  }
  if (left < margin) left = margin

  if (top < margin) top = margin
  if ((top + maxH) > (vh - margin)) top = Math.max(margin, vh - maxH - margin)

  return {
    left: `${Math.round(left)}px`,
    top: `${Math.round(top)}px`
  }
})

const onBgPointerDown = (e) => {
  if (!e) return
  // Clicking blank area closes the panel.
  clearSelection()
}

// Spiral layout (canvas measureText).
let measureCanvas = null
let measureCtx = null
const ensureMeasureCtx = () => {
  if (!import.meta.client) return null
  if (measureCtx) return measureCtx
  measureCanvas = document.createElement('canvas')
  measureCtx = measureCanvas.getContext('2d')
  return measureCtx
}

const placedWords = ref([])

const wordStyle = (w, idx) => ({
  left: `${Number(w?.xPct ?? 50)}%`,
  top: `${Number(w?.yPct ?? 50)}%`,
  fontSize: `${Math.max(10, Math.round(Number(w?.fontSize || 14)))}px`,
  fontWeight: Number(w?.fontWeight || 600),
  '--kw-color': String(w?.color || '#111827'),
  '--d': `${Math.max(0, Number(idx || 0) * 40)}ms`
})

  const clamp = (v, a, b) => Math.min(Math.max(v, a), b)
  const cloudScale = computed(() => {
    // 根据容器宽高自适应放大
    const maxScaleByW = width.value ? clamp(width.value / 520, 0.8, 1.3) : 1
    const maxScaleByH = height.value ? clamp(height.value / 520, 0.8, 1.3) : 1
    return Math.min(maxScaleByW, maxScaleByH)
  })
  const seededRandom = (seed) => {
    const x = Math.sin(seed) * 10000
    return x - Math.floor(x)
  }

  const layoutWords = async () => {
    if (!import.meta.client) return
    if (!width.value || !height.value) return

    const ctx = ensureMeasureCtx()
    if (!ctx) return

    // 允许根据实际容器比例一定程度上拉伸碰撞边界的空间，但不改变布局基础数值逻辑
    const baseW = 560
    const baseH = 560

    const srcRaw = (Array.isArray(props.keywords) ? props.keywords : [])
      .map((x) => ({
      word: String(x?.word || '').trim(),
      count: Number(x?.count || 0),
      weight: Number(x?.weight || 0)
    }))
    .filter((x) => x.word && Number.isFinite(x.count) && x.count > 0)

  srcRaw.sort((a, b) => {
    if (b.weight !== a.weight) return b.weight - a.weight
    if (b.count !== a.count) return b.count - a.count
    return a.word.localeCompare(b.word)
  })

  const topWords = srcRaw.slice(0, 32)
  if (topWords.length === 0) {
    placedWords.value = []
    await nextTick()
    return
  }

  const maxCount = Math.max(1, Number(topWords[0]?.count || 1))
  const placedItems = []
  const placed = []

  const canPlace = (x, y, wPct, hPct) => {
    const halfW = wPct / 2
    const halfH = hPct / 2
    const dx = x - 50
    const dy = y - 50
    const dist = Math.sqrt((dx * dx) + (dy * dy))
    const maxR = 49 - Math.max(halfW, halfH)
    if (dist > maxR) return false

    const pad = 4.0
    for (const p of placedItems) {
      if (
        (x - halfW - pad) < (p.x + (p.w / 2)) &&
        (x + halfW + pad) > (p.x - (p.w / 2)) &&
        (y - halfH - pad) < (p.y + (p.h / 2)) &&
        (y + halfH + pad) > (p.y - (p.h / 2))
      ) {
        return false
      }
    }
    return true
  }

  for (let i = 0; i < topWords.length; i += 1) {
    const item = topWords[i]
    const ratio = clamp(item.count / maxCount, 0, 1)
    const fontSize = Math.round(12 + (Math.pow(ratio, 0.65) * 20))
    const fontWeight = i === 0 ? 800 : 600

    ctx.font = `${fontWeight} ${fontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif`
    const textW = Math.ceil(ctx.measureText(item.word).width || 0)
    const textH = Math.ceil(fontSize * 1.1)
    const widthPct = (textW / baseW) * 100
    const heightPct = (textH / baseH) * 100

    let x = 50
    let y = 50
    let placedOk = false
    const tries = i === 0 ? 1 : 420

    for (let t = 0; t < tries; t += 1) {
      if (i === 0) {
        x = 50
        y = 50
      } else {
        const spiralIndex = i + (t * 0.28)
        const radius = (Math.sqrt(spiralIndex) * 7.6) + ((seededRandom((i * 1000) + t) * 1.2) - 0.6)
        const angle = (spiralIndex * 2.399963) + (seededRandom((i * 2000) + t) * 0.35)
        
        // Use an oval shape logic so it spreads wider horizontally over time
        x = 50 + (radius * Math.cos(angle) * 1.3)
        y = 50 + (radius * Math.sin(angle) * 0.7)
      }

      if (canPlace(x, y, widthPct, heightPct)) {
        placedOk = true
        break
      }
    }

    if (!placedOk) continue

    placedItems.push({ x, y, w: widthPct, h: heightPct })
    const alpha = Math.min(1, Math.max(0.35, 0.35 + (ratio * 0.65)))
    const color = i === 0 ? '#2f3338' : `rgba(45, 49, 54, ${alpha})`
    placed.push({
      word: item.word,
      count: Math.round(Number(item.count) || 0),
      weight: item.weight,
      fontSize,
      fontWeight,
      color,
      xPct: Number(x.toFixed(2)),
      yPct: Number(y.toFixed(2))
    })
  }

  placedWords.value = placed
  await nextTick()
}

watch(
  () => [width.value, height.value, props.keywords],
  () => {
    if (!import.meta.client) return
    layoutWords()
  },
  { deep: true }
)

watch(
  () => props.examples,
  () => {
    // Keep selection stable if possible; clear if word no longer exists.
    if (!selectedWord.value) return
    if (!examplesMap.value.get(selectedWord.value) && !(Array.isArray(props.keywords) && props.keywords.find((k) => k?.word === selectedWord.value))) {
      selectedWord.value = ''
    }
  },
  { deep: true }
)

onMounted(() => {
  privacyStore.init()
  if (!import.meta.client) return
  updateSize()
  if (typeof ResizeObserver !== 'undefined' && rootEl.value) {
    resizeObserver = new ResizeObserver(() => updateSize())
    resizeObserver.observe(rootEl.value)
  } else {
    window.addEventListener('resize', updateSize)
  }
  layoutWords()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect?.()
  resizeObserver = null
  if (import.meta.client) window.removeEventListener('resize', updateSize)
  measureCanvas = null
  measureCtx = null
})
</script>

<style scoped>
.kw-cloud-core {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 100%;
  max-width: 720px;
  height: 480px;
  transform: translate(-50%, -50%) scale(var(--cloud-scale, 1));
  transform-origin: center;
}

.kw-cloud-halo {
  position: absolute;
  inset: -6% -15%;
  background:
    radial-gradient(ellipse at 35% 45%, rgba(7, 193, 96, 0.12), transparent 55%),
    radial-gradient(ellipse at 65% 50%, rgba(242, 170, 0, 0.10), transparent 58%),
    radial-gradient(ellipse at 50% 65%, rgba(0, 0, 0, 0.04), transparent 60%);
  filter: blur(24px);
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
}

.kw-word {
  position: absolute;
  z-index: 1;
  transform: translate(-50%, -50%);
  line-height: 1.2;
  letter-spacing: 0.02em;
  padding: 4px 8px;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  border: none;
  box-shadow: none;
  color: var(--kw-color);
  text-shadow: none;
  transition: transform 160ms ease, filter 160ms ease, color 160ms ease;
  opacity: 1;
}

.kw-word:hover {
  transform: translate(-50%, -50%) scale(1.08);
  color: #2b2f35;
}

.kw-word--selected {
  color: #202429;
  transform: translate(-50%, -50%) scale(1.12);
  font-weight: 800;
}

.kw-animate .kw-word {
  opacity: 0;
  animation: kw-pop 450ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
  animation-delay: var(--d, 0ms);
}

@keyframes kw-pop {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.92);
    filter: blur(2px);
  }
  100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
    filter: blur(0);
  }
}

.kw-panel-enter-active,
.kw-panel-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.kw-panel-enter-from,
.kw-panel-leave-to {
  opacity: 0;
  transform: translate(0, 10px);
}
</style>
