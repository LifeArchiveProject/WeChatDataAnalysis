<template>
  <div ref="rootEl" class="kw-cloud relative w-full h-full select-none">
    <!-- Words -->
    <div
      class="absolute inset-0"
      :class="shouldAnimate ? 'kw-animate' : ''"
      @pointerdown="onBgPointerDown"
    >
      <button
        v-for="(w, idx) in placedWords"
        :key="w.word"
        type="button"
        class="kw-word"
        :class="selectedWord === w.word ? 'kw-word--selected' : ''"
        :style="wordStyle(w, idx)"
        :title="`${w.word} · ${formatInt(w.count)} 次`"
        @pointerdown.stop="selectWord(w.word)"
      >
        {{ w.word }}
      </button>
    </div>

    <!-- Empty state -->
    <div v-if="placedWords.length === 0" class="absolute inset-0 flex items-center justify-center">
      <div class="rounded-2xl border border-[#EDEDED] bg-white/70 backdrop-blur px-5 py-4 text-center">
        <div class="wrapped-title text-base text-[#000000e6]">暂无关键词</div>
        <div class="mt-1 wrapped-body text-sm text-[#7F7F7F]">这一年你还没有足够的文字消息来生成词云。</div>
      </div>
    </div>

    <!-- Examples panel -->
    <transition name="kw-panel">
      <div
        v-if="selectedInfo"
        class="kw-panel absolute left-1/2 bottom-3 -translate-x-1/2 w-[min(92%,420px)] rounded-2xl border border-[#EDEDED] bg-white/80 backdrop-blur shadow-[0_16px_40px_rgba(0,0,0,0.14)] overflow-hidden"
        data-no-accel
        @pointerdown.stop
      >
        <div class="flex items-start justify-between gap-3 px-4 pt-4 pb-2 border-b border-[#F3F3F3]">
          <div class="min-w-0">
            <div class="wrapped-title text-base text-[#000000e6] truncate">
              {{ selectedInfo.word }}
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
                <div :class="privacyMode ? 'privacy-blur' : ''" class="wrapped-body text-sm text-[#000000e6] leading-snug whitespace-pre-wrap break-words">
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
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { parseTextWithEmoji } from '~/utils/wechat-emojis'

const props = defineProps({
  keywords: { type: Array, default: () => [] }, // [{word,count,weight}]
  examples: { type: Array, default: () => [] }, // [{word,count,messages:[]}]
  privacyMode: { type: Boolean, default: false },
  animate: { type: Boolean, default: true },
  reducedMotion: { type: Boolean, default: false }
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const privacyMode = computed(() => !!props.privacyMode)

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
const selectWord = (w) => { selectedWord.value = String(w || '').trim() }

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
  left: `${Number(w?.x || 0)}px`,
  top: `${Number(w?.y || 0)}px`,
  fontSize: `${Math.max(10, Math.round(Number(w?.fontSize || 14)))}px`,
  fontWeight: Number(w?.fontWeight || 600),
  color: String(w?.color || '#111827'),
  '--d': `${Math.max(0, Number(idx || 0) * 15)}ms`
})

const clamp = (v, a, b) => Math.min(Math.max(v, a), b)
const palette = ['#07C160', '#0EA5E9', '#F2AA00', '#111827', '#16A34A', '#2563EB']

const layoutWords = async () => {
  if (!import.meta.client) return
  if (!width.value || !height.value) return

  const ctx = ensureMeasureCtx()
  if (!ctx) return

  const margin = 18
  const w = width.value
  const h = height.value
  const cx = w / 2
  const cy = h / 2

  const src = (Array.isArray(props.keywords) ? props.keywords : [])
    .map((x) => ({
      word: String(x?.word || '').trim(),
      count: Number(x?.count || 0),
      weight: Number(x?.weight || 0)
    }))
    .filter((x) => x.word && Number.isFinite(x.count) && x.count > 0)

  src.sort((a, b) => {
    if (b.weight !== a.weight) return b.weight - a.weight
    if (b.count !== a.count) return b.count - a.count
    return a.word.localeCompare(b.word)
  })

  const maxFont = clamp(Math.round(Math.min(54, Math.max(34, h * 0.095))), 32, 54)
  const minFont = clamp(Math.round(Math.min(20, Math.max(14, h * 0.03))), 14, 20)

  const boxes = []
  const placed = []

  const intersects = (a, b) => !(
    a.x2 <= b.x1 ||
    a.x1 >= b.x2 ||
    a.y2 <= b.y1 ||
    a.y1 >= b.y2
  )

  for (let idx = 0; idx < src.length; idx += 1) {
    const item = src[idx]
    const wn = clamp((item.weight - 0.2) / 0.8, 0, 1)
    const fontSize = Math.round(minFont + (maxFont - minFont) * wn)
    const fontWeight = idx <= 2 ? 800 : (idx <= 10 ? 700 : 600)

    ctx.font = `${fontWeight} ${fontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif`
    const textW = Math.ceil(ctx.measureText(item.word).width || 0)
    const textH = Math.ceil(fontSize * 1.18)
    const bw = textW + 10
    const bh = textH + 6

    let placedOk = false
    let best = null

    const angleStep = 0.35
    const radiusStep = 6
    for (let t = 0; t < 250; t += 1) {
      const ang = t * angleStep
      const rad = t * radiusStep
      const x = cx + Math.cos(ang) * rad
      const y = cy + Math.sin(ang) * rad
      const box = { x1: x - bw / 2, y1: y - bh / 2, x2: x + bw / 2, y2: y + bh / 2 }

      if (box.x1 < margin || box.y1 < margin || box.x2 > (w - margin) || box.y2 > (h - margin)) continue

      let ok = true
      for (const b of boxes) {
        if (intersects(box, b)) { ok = false; break }
      }
      if (!ok) continue

      best = { x, y }
      placedOk = true
      break
    }

    if (!placedOk || !best) continue

    const color = idx === 0 ? '#07C160' : palette[idx % palette.length]
    placed.push({
      word: item.word,
      count: Math.round(Number(item.count) || 0),
      weight: item.weight,
      fontSize,
      fontWeight,
      color,
      x: best.x,
      y: best.y
    })
    boxes.push({ x1: best.x - bw / 2, y1: best.y - bh / 2, x2: best.x + bw / 2, y2: best.y + bh / 2 })
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
.kw-word {
  position: absolute;
  left: 0;
  top: 0;
  transform: translate(-50%, -50%);
  line-height: 1.15;
  letter-spacing: 0.02em;
  padding: 2px 6px;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  background: rgba(255, 255, 255, 0.42);
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.08);
  transition: transform 160ms ease, filter 160ms ease, background 160ms ease, box-shadow 160ms ease;
  opacity: 1;
}

.kw-word:hover {
  transform: translate(-50%, -50%) scale(1.04);
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.12);
}

.kw-word--selected {
  background: rgba(7, 193, 96, 0.12);
  border-color: rgba(7, 193, 96, 0.28);
  box-shadow: 0 18px 42px rgba(7, 193, 96, 0.18);
  filter: drop-shadow(0 0 10px rgba(7, 193, 96, 0.28));
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
  transform: translate(-50%, 10px);
}
</style>
