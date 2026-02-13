<template>
  <div class="vb-stack relative select-none" :style="stackStyle">
    <div
      v-for="(card, index) in cards"
      :key="String(card.id)"
      class="vb-stack-card absolute top-1/2 left-1/2 overflow-hidden rounded-2xl bg-white/80 shadow-sm"
      :style="{
        width: `${dims.width}px`,
        height: `${dims.height}px`,
        touchAction: index === cards.length - 1 ? 'none' : 'auto',
        pointerEvents: index === cards.length - 1 ? 'auto' : 'none'
      }"
      :ref="(el) => onCardRef(card.id, el)"
      @pointerdown="(e) => onPointerDown(e, card.id, index)"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerCancel"
    >
      <img :src="card.img" class="w-full h-full object-cover" alt="" draggable="false" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'

type StackCard = {
  id: string | number
  img: string
}

const props = withDefaults(
  defineProps<{
    randomRotation?: boolean
    sensitivity?: number
    sendToBackOnClick?: boolean
    cardDimensions?: { width?: number; height?: number }
    cardsData?: StackCard[]
  }>(),
  {
    randomRotation: false,
    sensitivity: 180,
    sendToBackOnClick: true,
    cardDimensions: () => ({ width: 200, height: 200 }),
    cardsData: () => []
  }
)

const dims = computed(() => {
  const w = Number(props.cardDimensions?.width)
  const h = Number(props.cardDimensions?.height)
  return {
    width: Number.isFinite(w) && w > 0 ? Math.floor(w) : 200,
    height: Number.isFinite(h) && h > 0 ? Math.floor(h) : 200
  }
})

const stackStyle = computed(() => ({
  width: `${dims.value.width}px`,
  height: `${dims.value.height}px`
}))

const cards = ref<StackCard[]>([])
const elMap = new Map<string, HTMLDivElement>()
const rotationMap = ref(new Map<string, number>())
const mounted = ref(false)

const ROT_RANGE_DEG = 7
const STACK_OFFSET_X = 2
const STACK_OFFSET_Y = 4
const STACK_SCALE_STEP = 0.03
const MAX_TILT_DEG = 22

function normalizeCards(data: unknown): StackCard[] {
  const raw = Array.isArray(data) ? data : []
  const out: StackCard[] = []
  for (const item of raw) {
    const id = (item as any)?.id
    const img = String((item as any)?.img || '').trim()
    if (id === null || id === undefined) continue
    if (!img) continue
    out.push({ id, img })
  }
  return out
}

function ensureRotations(list: StackCard[]) {
  const next = new Map(rotationMap.value)
  if (!props.randomRotation) {
    for (const c of list) next.set(String(c.id), 0)
    rotationMap.value = next
    return
  }
  for (const c of list) {
    const key = String(c.id)
    if (next.has(key)) continue
    next.set(key, Math.round((Math.random() * 2 - 1) * ROT_RANGE_DEG))
  }
  rotationMap.value = next
}

function onCardRef(id: StackCard['id'], el: Element | null) {
  const key = String(id)
  if (el && el instanceof HTMLDivElement) elMap.set(key, el)
  else elMap.delete(key)
}

function applyLayout(animate: boolean) {
  if (!mounted.value) return
  const total = cards.value.length
  if (total === 0) return

  cards.value.forEach((card, idx) => {
    const key = String(card.id)
    const el = elMap.get(key)
    if (!el) return

    const orderFromTop = total - 1 - idx
    const x = orderFromTop * STACK_OFFSET_X
    const y = orderFromTop * STACK_OFFSET_Y
    const scale = Math.max(0.88, 1 - orderFromTop * STACK_SCALE_STEP)
    const rotation = rotationMap.value.get(key) ?? 0

    const tweenVars: gsap.TweenVars = {
      x,
      y,
      rotation,
      rotationX: 0,
      rotationY: 0,
      scale,
      xPercent: -50,
      yPercent: -50,
      zIndex: idx + 1,
      transformOrigin: 'center center',
      ease: 'power3.out',
      duration: animate ? 0.32 : 0
    }

    gsap.killTweensOf(el)
    if (animate) gsap.to(el, tweenVars)
    else gsap.set(el, tweenVars)
  })
}

watch(
  () => props.cardsData,
  (val) => {
    const nextCards = normalizeCards(val)
    cards.value = nextCards
    ensureRotations(nextCards)
    nextTick(() => applyLayout(false))
  },
  { immediate: true }
)

watch(
  () => [props.randomRotation, props.cardDimensions?.width, props.cardDimensions?.height] as const,
  () => {
    ensureRotations(cards.value)
    nextTick(() => applyLayout(false))
  }
)

onMounted(() => {
  mounted.value = true
  applyLayout(false)
})

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

let activePointerId: number | null = null
let activeCardId: string | null = null
let startClientX = 0
let startClientY = 0
let startX = 0
let startY = 0
let startRotationZ = 0
let startScale = 1
let lastDx = 0
let lastDy = 0

function sendToBack(id: string) {
  if (cards.value.length < 2) return
  const list = cards.value.slice()
  const idx = list.findIndex((c) => String(c.id) === id)
  if (idx < 0) return
  const [card] = list.splice(idx, 1)
  if (!card) return
  cards.value = [card, ...list]
}

function onPointerDown(e: PointerEvent, id: StackCard['id'], index: number) {
  if (activePointerId !== null) return
  if (index !== cards.value.length - 1) return

  const key = String(id)
  const el = elMap.get(key)
  if (!el) return

  activePointerId = e.pointerId
  activeCardId = key
  startClientX = e.clientX
  startClientY = e.clientY
  startX = Number(gsap.getProperty(el, 'x')) || 0
  startY = Number(gsap.getProperty(el, 'y')) || 0
  startRotationZ = Number(gsap.getProperty(el, 'rotation')) || 0
  startScale = Number(gsap.getProperty(el, 'scale')) || 1
  lastDx = 0
  lastDy = 0

  try {
    el.setPointerCapture(e.pointerId)
  } catch {}

  gsap.killTweensOf(el)
  gsap.set(el, { zIndex: 999 })
  gsap.to(el, { scale: startScale * 1.03, duration: 0.12, ease: 'power2.out' })
}

function onPointerMove(e: PointerEvent) {
  if (activePointerId === null || e.pointerId !== activePointerId) return
  const key = activeCardId
  if (!key) return
  const el = elMap.get(key)
  if (!el) return

  const dx = e.clientX - startClientX
  const dy = e.clientY - startClientY
  lastDx = dx
  lastDy = dy

  const w = Math.max(1, dims.value.width)
  const h = Math.max(1, dims.value.height)
  const nx = dx / (w * 0.55)
  const ny = dy / (h * 0.55)
  const tiltY = clamp(Math.tanh(nx) * MAX_TILT_DEG, -MAX_TILT_DEG, MAX_TILT_DEG)
  const tiltX = clamp(-Math.tanh(ny) * MAX_TILT_DEG, -MAX_TILT_DEG, MAX_TILT_DEG)

  gsap.set(el, {
    x: startX + dx,
    y: startY + dy,
    rotation: startRotationZ + dx / 18,
    rotationX: tiltX,
    rotationY: tiltY
  })
}

function finishPointer(id: number, shouldSendBack: boolean) {
  const key = activeCardId
  activePointerId = null
  activeCardId = null

  const el = key ? elMap.get(key) : null
  if (el) {
    try {
      el.releasePointerCapture(id)
    } catch {}
  }

  if (shouldSendBack && key) sendToBack(key)
  applyLayout(true)
}

function onPointerUp(e: PointerEvent) {
  if (activePointerId === null || e.pointerId !== activePointerId) return
  const dist = Math.hypot(lastDx, lastDy)
  const clickLike = dist < 6
  const shouldSendBack = dist > Number(props.sensitivity || 0) || (props.sendToBackOnClick && clickLike)
  finishPointer(e.pointerId, shouldSendBack)
}

function onPointerCancel(e: PointerEvent) {
  if (activePointerId === null || e.pointerId !== activePointerId) return
  finishPointer(e.pointerId, false)
}
</script>

<style scoped>
.vb-stack {
  perspective: 1000px;
}

.vb-stack-card {
  will-change: transform;
  transform-style: preserve-3d;
  backface-visibility: hidden;
  cursor: grab;
}

.vb-stack-card:active {
  cursor: grabbing;
}
</style>
