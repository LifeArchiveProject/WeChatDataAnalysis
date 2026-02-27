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

    <!-- 卡片壳体 -->
    <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant" :wide="true" :hide-chrome="isAnimating">
      <template #narrative>
        <div class="mt-2 wrapped-body text-sm sm:text-base text-[#7F7F7F] leading-relaxed">
          <p class="whitespace-pre-wrap">
            <template v-if="phase !== 'cloud'">
              你的话，正在涌来。
            </template>
            <template v-else>
              这一年，你一共发出了 <span class="font-medium text-[#07C160]">{{ card.data?.meta?.matchedCandidates || 0 }}</span> 句简短的表达，其中 <span class="font-medium text-[#07C160]">{{ card.data?.meta?.uniquePhrases || 0 }}</span> 句话成了你的专属口头禅。
              <template v-if="card.data?.topKeyword">
                「<span class="font-medium text-[#07C160] wrapped-privacy-keyword">{{ card.data.topKeyword.word }}</span>」是你最常说的话，足足被你重复了 <span class="font-medium text-[#07C160]">{{ card.data.topKeyword.count }}</span> 次。
              </template>
              点击气泡，找回当时的心情。
            </template>
          </p>
        </div>
      </template>

      <div class="w-full">
        <div
          ref="stageEl"
          class="kw-stage relative w-full h-[56vh] min-h-[360px] max-h-[680px] rounded-[28px] overflow-hidden"
        >

          <!-- 词云 -->
          <transition name="cloud-fade">
            <div v-if="phase === 'cloud'" class="absolute inset-0 z-30 p-3 sm:p-5">
              <KeywordWordCloud
                :keywords="keywords"
                :examples="examples"
                :animate="true"
                :reduced-motion="reducedMotion"
              />
            </div>
          </transition>
        </div>

        <div v-if="phase === 'cloud'" class="mt-3 flex justify-center">
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
import KeywordWordCloud from '~/components/wrapped/visualizations/KeywordWordCloud.vue'
import { parseTextWithEmoji } from '~/utils/wechat-emojis'
import { usePrivacyStore } from '~/stores/privacy'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const cardRoot = ref(null)
const stageEl = ref(null)
const overlayEl = ref(null)

const phase = ref('idle') // 'idle' | 'storm' | 'packed' | 'merge' | 'burst' | 'cloud'
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
  const centerX = vw / 2
  const centerY = vh / 2

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
        gsap.fromTo(
          el,
          { opacity: 0, scale: 0.94, y: 10 },
          { opacity: 1, scale: 1, y: 0, duration: 0.18, ease: 'power2.out' }
        )
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
