<template>
  <div
    class="image-group-shell"
    :class="{ 'image-group-shell--sent': message.isSent }"
    data-testid="image-group-shell"
  >
    <div
      ref="stackRef"
      class="image-group-stack"
      :class="{
        'image-group-stack--dragging': dragging,
        'image-group-stack--transitioning': transitioning
      }"
      :data-active-index="activeIndex"
      :data-group-key="message.imageGroupKey || ''"
      data-testid="image-group-stack"
      :style="{ '--image-group-transition-duration': transitionDurationMs + 'ms' }"
      role="group"
      :aria-label="`组合图片，共 ${protocolCount} 张`"
      :aria-busy="transitioning ? 'true' : 'false'"
      tabindex="0"
      @keydown="onKeydown"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerCancel"
      @lostpointercapture="onLostPointerCapture"
      @contextmenu.stop.prevent
      @dragstart.prevent
    >
      <div
        v-for="(item, index) in items"
        :key="item.id || `${message.imageGroupKey}:${index}`"
        class="image-group-card"
        :class="{ 'image-group-card--active': index === activeIndex }"
        :style="cardStyle(index)"
        :data-card-index="index"
        :data-image-group-key="message.imageGroupKey || ''"
        :data-image-group-item-index="index"
        :data-message-id="item.id || ''"
        data-testid="image-group-card"
        :aria-hidden="index === activeIndex ? 'false' : 'true'"
        @click="onCardClick($event, index)"
        @contextmenu.stop="openItemContextMenu($event, item)"
      >
        <img
          v-if="item.imageUrl && !item._imageRenderError"
          v-chat-lazy-src="item.imageUrl"
          alt="图片"
          draggable="false"
          loading="lazy"
          decoding="async"
          fetchpriority="low"
          @error="onImageError(item)"
        >
        <div v-else class="image-group-placeholder">
          <i class="fa-regular fa-image" aria-hidden="true"></i>
          <span>图片未缓存</span>
        </div>
      </div>
    </div>

    <button
      type="button"
      class="image-group-expand"
      data-testid="image-group-expand"
      :aria-label="`展开 ${protocolCount} 张组合图片`"
      :disabled="interactionLocked"
      :data-image-group-control-key="message.imageGroupKey || ''"
      @click.stop="toggleExpanded"
    >
      展开 {{ protocolCount }}
    </button>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  message: { type: Object, required: true },
  state: { type: Object, required: true }
})

const stackRef = ref(null)
const dragX = ref(0)
const dragging = ref(false)
const transitioning = ref(false)
const shuffleDirection = ref(0)
const settlementProgress = ref(0)
const transitionDurationMs = ref(0)
const outgoingIndex = ref(-1)
const boundaryReturnX = ref(0)
const boundaryReturning = ref(false)

const items = computed(() => (
  Array.isArray(props.message?.imageGroupItems) ? props.message.imageGroupItems : []
))
const savedActiveItemId = String(
  props.state?.getImageGroupActiveItemId?.(props.message?.imageGroupKey) || ''
).trim()
const savedActiveIndex = savedActiveItemId
  ? items.value.findIndex((item) => String(item?.id || '').trim() === savedActiveItemId)
  : -1
const activeIndex = ref(savedActiveIndex >= 0 ? savedActiveIndex : 0)
const protocolCount = computed(() => Math.max(
  items.value.length,
  Number(props.message?.imageGroupProtocolCount || props.message?.imageGroupCount || 0)
))
const readMaybeRef = (value) => (
  value && typeof value === 'object' && 'value' in value ? value.value : value
)
const interactionLocked = computed(() => (
  dragging.value
  || transitioning.value
  || !!shuffleDirection.value
  || boundaryReturning.value
  || !!readMaybeRef(props.state?.imageGroupTransitioning)
))

let activePointerId = null
let pointerStartX = 0
let pointerStartY = 0
let pointerStartAt = 0
let pointerLastX = 0
let pointerLastAt = 0
let pointerVelocityX = 0
let horizontalIntent = false
let pointerStartedOnActiveCard = false
let measuredStackWidth = 200
let settlementTimer = null
let settlementTargetIndex = null
let transitionFrame = null
let suppressClickUntil = 0

const modulo = (value, length) => ((value % length) + length) % length
const mix = (from, to, progress) => from + ((to - from) * progress)
const resolveTargetIndex = (direction, count) => Math.max(
  0,
  Math.min(count - 1, activeIndex.value + direction)
)
const measureStackWidth = () => {
  measuredStackWidth = Math.max(
    160,
    Number(stackRef.value?.getBoundingClientRect?.().width || measuredStackWidth || 200)
  )
  return measuredStackWidth
}

const basePoseForRank = (rank) => {
  const fanDirection = props.message?.isSent ? -1 : 1
  const depth = Math.min(Math.max(rank, 0), 3)
  const translateX = [0, 7, 11, 15][depth] * fanDirection
  return {
    x: translateX,
    y: 0,
    rotate: [0, 2, 3.2, 4.2][depth] * fanDirection,
    scale: [1, 0.94, 0.92, 0.9][depth],
    opacity: rank > 3 ? 0 : 1
  }
}

const currentSwipeDirection = () => {
  if (dragX.value < 0) return 1
  if (dragX.value > 0) return -1
  return 0
}

const cardStyle = (index) => {
  const count = items.value.length
  if (!count) return {}

  const currentRank = modulo(index - activeIndex.value, count)
  const idlePose = basePoseForRank(currentRank)
  const direction = dragging.value ? currentSwipeDirection() : shuffleDirection.value
  const progress = dragging.value
    ? Math.min(1, Math.abs(dragX.value) / 150)
    : settlementProgress.value

  let pose = idlePose
  let zIndex = count - currentRank
  if (boundaryReturning.value && index === activeIndex.value) {
    pose = {
      x: boundaryReturnX.value * 0.18,
      y: 0,
      rotate: boundaryReturnX.value * 0.006,
      scale: 0.99,
      opacity: 1
    }
    zIndex = count + 2
  } else if (direction) {
    const nextActiveIndex = settlementTargetIndex == null
      ? resolveTargetIndex(direction, count)
      : settlementTargetIndex
    const atBoundary = nextActiveIndex === activeIndex.value
    const finalRank = modulo(index - nextActiveIndex, count)
    const finalPose = basePoseForRank(finalRank)

    if (index === (dragging.value ? activeIndex.value : outgoingIndex.value)) {
      const side = direction > 0 ? -1 : 1
      const sidePose = { x: side * 150, y: 0, rotate: side * 15, scale: 0.7, opacity: 1 }
      if (dragging.value && atBoundary) {
        pose = {
          x: dragX.value * 0.18,
          y: 0,
          rotate: dragX.value * 0.006,
          scale: 0.99,
          opacity: 1
        }
        zIndex = count + 2
      } else if (progress <= 1) {
        const overdrag = dragging.value ? Math.max(0, Math.abs(dragX.value) - 150) * 0.16 : 0
        pose = {
          x: (side * 150 * progress) + (side * overdrag),
          y: 0,
          rotate: side * 15 * progress,
          scale: 1 - (0.3 * progress),
          opacity: 1
        }
        zIndex = count + 2
      } else {
        const returnProgress = Math.min(1, progress - 1)
        pose = {
          x: mix(sidePose.x, finalPose.x, returnProgress),
          y: 0,
          rotate: mix(sidePose.rotate, finalPose.rotate, returnProgress),
          scale: mix(sidePose.scale, finalPose.scale, returnProgress),
          opacity: mix(sidePose.opacity, finalPose.opacity, returnProgress)
        }
        zIndex = count - finalRank
      }
    } else {
      const incomingProgress = Math.min(1, progress / 2)
      pose = {
        x: mix(idlePose.x, finalPose.x, incomingProgress),
        y: 0,
        rotate: mix(idlePose.rotate, finalPose.rotate, incomingProgress),
        scale: mix(idlePose.scale, finalPose.scale, incomingProgress),
        opacity: mix(idlePose.opacity, finalPose.opacity, incomingProgress)
      }
      zIndex = progress < 1 ? count - currentRank : count - finalRank
      if (index === nextActiveIndex && progress >= 1) zIndex = count + 1
    }
  }

  return {
    zIndex,
    opacity: String(pose.opacity),
    pointerEvents: index === activeIndex.value && !transitioning.value ? 'auto' : 'none',
    transform: `translate3d(${pose.x}px, ${pose.y}px, 0) rotate(${pose.rotate}deg) scale(${pose.scale})`
  }
}

const prefersReducedMotion = () => (
  typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches
)

const SHUFFLE_HALF_DURATION_MS = 150

const clearSettlementTimer = () => {
  if (settlementTimer) clearTimeout(settlementTimer)
  settlementTimer = null
  if (transitionFrame != null && typeof window !== 'undefined') {
    window.cancelAnimationFrame(transitionFrame)
  }
  transitionFrame = null
}

const commitSettlement = () => {
  clearSettlementTimer()
  transitioning.value = false
  if (settlementTargetIndex != null) activeIndex.value = settlementTargetIndex
  settlementTargetIndex = null
  outgoingIndex.value = -1
  boundaryReturnX.value = 0
  boundaryReturning.value = false
  shuffleDirection.value = 0
  settlementProgress.value = 0
  transitionDurationMs.value = 0
  dragX.value = 0
}

const settleBack = () => {
  const direction = currentSwipeDirection()
  const startProgress = Math.min(1, Math.abs(dragX.value) / 150)
  if (prefersReducedMotion()) {
    commitSettlement()
    return
  }
  if (!direction || startProgress <= 0) {
    commitSettlement()
    return
  }

  const targetIndex = resolveTargetIndex(direction, items.value.length)
  if (targetIndex === activeIndex.value) {
    transitioning.value = false
    boundaryReturning.value = true
    boundaryReturnX.value = dragX.value
    transitionDurationMs.value = 120
    dragX.value = 0
    clearSettlementTimer()
    nextTick(() => {
      transitionFrame = window.requestAnimationFrame(() => {
        transitionFrame = null
        transitioning.value = true
        boundaryReturnX.value = 0
        settlementTimer = window.setTimeout(commitSettlement, transitionDurationMs.value)
      })
    })
    return
  }

  transitioning.value = false
  settlementTargetIndex = null
  outgoingIndex.value = activeIndex.value
  shuffleDirection.value = direction
  settlementProgress.value = startProgress
  transitionDurationMs.value = Math.max(60, Math.round(160 * startProgress))
  dragX.value = 0
  clearSettlementTimer()
  nextTick(() => {
    transitionFrame = window.requestAnimationFrame(() => {
      transitionFrame = null
      transitioning.value = true
      settlementProgress.value = 0
      settlementTimer = window.setTimeout(commitSettlement, transitionDurationMs.value)
    })
  })
}

const completeSwipe = (direction) => {
  const count = items.value.length
  if (count < 2 || !direction) {
    settleBack()
    return
  }

  const startProgress = Math.min(1, Math.abs(dragX.value) / 150)
  const targetIndex = resolveTargetIndex(direction, count)
  if (targetIndex === activeIndex.value) {
    settleBack()
    return
  }
  if (prefersReducedMotion()) {
    settlementTargetIndex = targetIndex
    commitSettlement()
    return
  }
  settlementTargetIndex = targetIndex
  outgoingIndex.value = activeIndex.value
  shuffleDirection.value = direction
  settlementProgress.value = startProgress
  transitioning.value = false
  dragX.value = 0
  clearSettlementTimer()

  const halfDuration = SHUFFLE_HALF_DURATION_MS
  const outboundDuration = Math.max(0, Math.round(halfDuration * (1 - startProgress)))
  const beginReturn = () => {
    transitionDurationMs.value = halfDuration
    transitioning.value = true
    settlementProgress.value = 2
    settlementTimer = window.setTimeout(commitSettlement, halfDuration)
  }

  nextTick(() => {
    transitionFrame = window.requestAnimationFrame(() => {
      transitionFrame = null
      if (outboundDuration <= 0) {
        settlementProgress.value = 1
        beginReturn()
        return
      }
      transitionDurationMs.value = outboundDuration
      transitioning.value = true
      settlementProgress.value = 1
      settlementTimer = window.setTimeout(beginReturn, outboundDuration)
    })
  })
}

const resetPointer = () => {
  activePointerId = null
  horizontalIntent = false
  pointerStartedOnActiveCard = false
  dragging.value = false
}

const onPointerDown = (event) => {
  if (activePointerId != null || event.button !== 0 || items.value.length < 2) return
  if (transitioning.value || shuffleDirection.value || boundaryReturning.value) return

  activePointerId = event.pointerId
  pointerStartX = event.clientX
  pointerStartY = event.clientY
  pointerStartAt = event.timeStamp
  pointerLastX = event.clientX
  pointerLastAt = event.timeStamp
  pointerVelocityX = 0
  horizontalIntent = false
  const pressedCard = event.target?.closest?.('[data-card-index]')
  pointerStartedOnActiveCard = (
    Number.parseInt(String(pressedCard?.dataset?.cardIndex || ''), 10) === activeIndex.value
  )
  measureStackWidth()
  dragging.value = true
  dragX.value = 0
  event.currentTarget?.setPointerCapture?.(event.pointerId)
}

const onPointerMove = (event) => {
  if (event.pointerId !== activePointerId || !dragging.value) return
  const dx = event.clientX - pointerStartX
  const dy = event.clientY - pointerStartY
  if (!horizontalIntent) {
    if (Math.abs(dx) < 6) return
    if (Math.abs(dy) > Math.abs(dx)) return
    horizontalIntent = true
  }

  event.preventDefault()
  const elapsed = Math.max(1, event.timeStamp - pointerLastAt)
  pointerVelocityX = ((event.clientX - pointerLastX) / elapsed * 0.72) + (pointerVelocityX * 0.28)
  pointerLastX = event.clientX
  pointerLastAt = event.timeStamp
  dragX.value = dx
}

const finishPointer = (event, cancelled = false) => {
  if (event.pointerId !== activePointerId) return
  const elapsed = Math.max(1, event.timeStamp - pointerStartAt)
  const distance = dragX.value
  const averageVelocity = distance / elapsed
  const velocity = Math.abs(pointerVelocityX) > Math.abs(averageVelocity) ? pointerVelocityX : averageVelocity
  const width = measuredStackWidth
  const distanceDirection = distance < 0 ? 1 : distance > 0 ? -1 : 0
  const velocityDirection = velocity < 0 ? 1 : velocity > 0 ? -1 : 0
  const distanceTriggered = Math.abs(distance) >= width * 0.22
  const velocityTriggered = Math.abs(velocity) >= 0.25
  const velocityAgreesWithGesture = (
    !distanceDirection
    || distanceDirection === velocityDirection
    || Math.abs(distance) <= 6
  )
  const direction = distanceTriggered
    ? distanceDirection
    : (velocityTriggered && velocityAgreesWithGesture ? velocityDirection : distanceDirection)
  const thresholdReached = distanceTriggered || (velocityTriggered && velocityAgreesWithGesture)
  const canNavigate = resolveTargetIndex(direction, items.value.length) !== activeIndex.value
  const shouldSwitch = !cancelled && horizontalIntent && thresholdReached && canNavigate

  const completedHorizontalDrag = horizontalIntent
  const shouldPreview = !cancelled && !completedHorizontalDrag && pointerStartedOnActiveCard
  if (completedHorizontalDrag) suppressClickUntil = Date.now() + 320
  resetPointer()
  try {
    event.currentTarget?.releasePointerCapture?.(event.pointerId)
  } catch {}

  if (!completedHorizontalDrag) {
    dragX.value = 0
    if (shouldPreview) {
      suppressClickUntil = Date.now() + 80
      previewItem(items.value[activeIndex.value])
    }
    return
  }

  if (!shouldSwitch) {
    settleBack()
    return
  }
  completeSwipe(direction)
}

const onPointerUp = (event) => finishPointer(event, false)
const onPointerCancel = (event) => finishPointer(event, true)
const onLostPointerCapture = (event) => {
  if (event.pointerId === activePointerId) finishPointer(event, true)
}

const previewItem = (item) => {
  const url = String(item?.imageUrl || '').trim()
  if (!url || typeof props.state?.openImagePreview !== 'function') return
  props.state.openImagePreview(url, items.value)
}

const onCardClick = (event, index) => {
  if (Date.now() < suppressClickUntil || index !== activeIndex.value) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  previewItem(items.value[index])
}

const onKeydown = (event) => {
  if (transitioning.value || shuffleDirection.value || boundaryReturning.value || items.value.length < 2) return
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    if (activeIndex.value > 0) activeIndex.value -= 1
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    if (activeIndex.value < items.value.length - 1) activeIndex.value += 1
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    previewItem(items.value[activeIndex.value])
  }
}

const onImageError = (item) => {
  const fallback = String(item?.imageFallbackUrl || '').trim()
  if (fallback && fallback !== String(item?.imageUrl || '').trim() && !item?._imageFallbackTried) {
    item._imageFallbackTried = true
    item.imageUrl = fallback
    return
  }
  item._imageRenderError = true
  props.state?.onMessageImageRenderError?.(item)
}

const openItemContextMenu = (event, item) => {
  props.state?.openMediaContextMenu?.(event, item, 'image')
}

const toggleExpanded = () => {
  if (interactionLocked.value) return
  const transition = props.state?.transitionImageGroupExpanded
  if (typeof transition === 'function') {
    void transition(props.message?.imageGroupKey)
    return
  }
  props.state?.toggleImageGroupExpanded?.(props.message?.imageGroupKey)
}

watch(
  () => items.value.map((item) => String(item?.id || '')).join('|'),
  async (_nextIds, previousIds) => {
    if (transitioning.value || shuffleDirection.value || boundaryReturning.value) commitSettlement()
    const activeId = String(previousIds || '').split('|')[activeIndex.value] || ''
    await nextTick()
    const nextIndex = items.value.findIndex((item) => String(item?.id || '') === activeId)
    activeIndex.value = nextIndex >= 0 ? nextIndex : Math.min(activeIndex.value, Math.max(0, items.value.length - 1))
    dragX.value = 0
  }
)

watch(activeIndex, (index) => {
  const messageId = String(items.value[index]?.id || '').trim()
  if (messageId) {
    props.state?.setImageGroupActiveItemId?.(props.message?.imageGroupKey, messageId)
  }
}, { immediate: true })

onBeforeUnmount(() => clearSettlementTimer())
</script>

<style scoped>
.image-group-shell {
  --image-group-expand-bg: #eeedf0;
  --image-group-expand-text: #a09fa4;
  display: flex;
  align-items: center;
  gap: 36px;
  max-width: 100%;
}

:global(html[data-theme='dark']) .image-group-shell {
  --image-group-expand-bg: var(--app-surface-muted);
  --image-group-expand-text: var(--app-text-muted);
}

.image-group-shell--sent {
  flex-direction: row-reverse;
}

.image-group-stack {
  position: relative;
  width: clamp(150px, 30vw, 200px);
  aspect-ratio: 3 / 4;
  flex: 0 0 auto;
  outline: none;
  touch-action: pan-y;
  user-select: none;
  cursor: grab;
  isolation: isolate;
  z-index: 1;
}

.image-group-stack--dragging {
  cursor: grabbing;
}

.image-group-stack--transitioning {
  cursor: default;
}

.image-group-stack:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.72);
  outline-offset: 4px;
}

.image-group-card {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-surface-muted);
  box-shadow: 0 1px 2px rgba(20, 24, 31, 0.08);
  transform-origin: 50% 50%;
  will-change: transform;
}

.image-group-stack--transitioning .image-group-card {
  transition: transform var(--image-group-transition-duration) cubic-bezier(0.25, 0.1, 0.25, 1);
}

.image-group-card img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
}

.image-group-placeholder {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  align-content: center;
  gap: 8px;
  color: #8a919b;
  font-size: 12px;
}

.image-group-placeholder > i {
  font-size: 26px;
}

.image-group-expand {
  position: relative;
  z-index: 0;
  width: 75px;
  height: 31px;
  padding: 0 12px;
  border: 0;
  border-radius: 16px;
  color: var(--image-group-expand-text);
  background: var(--image-group-expand-bg);
  font-size: 13px;
  line-height: 31px;
  white-space: nowrap;
  cursor: pointer;
}

.image-group-expand:hover {
  color: var(--app-text-secondary);
  background: var(--app-list-hover);
}

.image-group-expand:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.72);
  outline-offset: 2px;
}

.image-group-expand:disabled {
  cursor: default;
}

@media (max-width: 480px) {
  .image-group-shell {
    gap: 12px;
  }

  .image-group-stack {
    width: clamp(140px, 47vw, 176px);
  }

  .image-group-expand {
    min-width: 58px;
    height: 30px;
    padding: 0 10px;
    font-size: 12px;
    line-height: 30px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .image-group-stack--transitioning .image-group-card {
    transition: none;
  }
}
</style>
