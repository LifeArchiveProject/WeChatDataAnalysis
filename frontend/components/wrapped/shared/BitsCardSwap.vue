<template>
  <div
    ref="containerRef"
    class="bits-card-swap absolute bottom-0 right-0 translate-x-[24%] translate-y-[-2%] origin-bottom-right overflow-visible [perspective:900px]"
    :style="containerStyle"
  >
    <div
      v-for="(_, index) in visibleCardCount"
      :key="index"
      ref="cardRefs"
      class="bits-card-swap-item absolute top-1/2 left-1/2 rounded-xl [transform-style:preserve-3d] [will-change:transform] [backface-visibility:hidden]"
      :style="cardStyle"
      @click="onCardClick(index)"
    >
      <slot :name="`card-${index}`" :index="index" />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import gsap from 'gsap'

const props = defineProps({
  cardCount: { type: Number, default: 3 },
  width: { type: [Number, String], default: 250 },
  height: { type: [Number, String], default: 300 },
  cardDistance: { type: Number, default: 24 },
  verticalDistance: { type: Number, default: 34 },
  delay: { type: Number, default: 4200 },
  pauseOnHover: { type: Boolean, default: false },
  onCardClick: { type: Function, default: null },
  skewAmount: { type: Number, default: 4 },
  easing: { type: String, default: 'elastic' }
})

const emit = defineEmits(['cardClick'])

const containerRef = ref(null)
const cardRefs = ref([])
const order = ref([0, 1, 2])
const timelineRef = ref(null)
let intervalRef = null

const toPx = (value) => (typeof value === 'number' ? `${value}px` : value)

const containerStyle = computed(() => ({
  width: toPx(props.width),
  height: toPx(props.height)
}))

const cardStyle = computed(() => ({
  width: toPx(props.width),
  height: toPx(props.height)
}))

const visibleCardCount = computed(() => {
  const count = Number(props.cardCount)
  if (!Number.isFinite(count)) return 1
  const normalized = Math.floor(count)
  return Math.max(1, normalized)
})

const config = computed(() => {
  if (props.easing === 'elastic') {
    return {
      ease: 'elastic.out(0.6,0.9)',
      dropDuration: 1.8,
      moveDuration: 1.8,
      returnDuration: 1.8,
      overlap: 0.85,
      returnDelay: 0.08
    }
  }
  return {
    ease: 'power1.inOut',
    dropDuration: 0.8,
    moveDuration: 0.8,
    returnDuration: 0.8,
    overlap: 0.45,
    returnDelay: 0.2
  }
})

const makeSlot = (index, total) => ({
  x: index * props.cardDistance,
  y: -index * props.verticalDistance,
  z: -index * props.cardDistance * 1.5,
  zIndex: total - index
})

const placeNow = (element, slot) => {
  gsap.set(element, {
    x: slot.x,
    y: slot.y,
    z: slot.z,
    xPercent: -50,
    yPercent: -50,
    skewY: props.skewAmount,
    transformOrigin: 'center center',
    zIndex: slot.zIndex,
    force3D: true
  })
}

const initializeCards = () => {
  const list = cardRefs.value || []
  if (!list.length) return
  const total = visibleCardCount.value
  list.forEach((element, index) => {
    if (!element) return
    placeNow(element, makeSlot(index, total))
  })
}

const updateCardPositions = () => {
  const list = cardRefs.value || []
  if (!list.length) return
  const total = visibleCardCount.value
  list.forEach((element, index) => {
    if (!element) return
    const slot = makeSlot(index, total)
    gsap.set(element, {
      x: slot.x,
      y: slot.y,
      z: slot.z,
      skewY: props.skewAmount
    })
  })
}

const runSwap = () => {
  const total = visibleCardCount.value
  if (order.value.length !== total) {
    order.value = Array.from({ length: total }, (_, idx) => idx)
  }
  const activeOrder = order.value.slice(0, total)
  if (activeOrder.length < 2) return
  const [front, ...rest] = activeOrder
  const frontElement = cardRefs.value[front]
  if (!frontElement) return

  const tl = gsap.timeline()
  timelineRef.value = tl

  tl.to(frontElement, {
    y: '+=480',
    duration: config.value.dropDuration,
    ease: config.value.ease
  })

  tl.addLabel('promote', `-=${config.value.dropDuration * config.value.overlap}`)

  rest.forEach((index, slotIndex) => {
    const element = cardRefs.value[index]
    if (!element) return
    const slot = makeSlot(slotIndex, activeOrder.length)
    tl.set(element, { zIndex: slot.zIndex }, 'promote')
    tl.to(
      element,
      {
        x: slot.x,
        y: slot.y,
        z: slot.z,
        duration: config.value.moveDuration,
        ease: config.value.ease
      },
      `promote+=${slotIndex * 0.15}`
    )
  })

  const backSlot = makeSlot(activeOrder.length - 1, activeOrder.length)

  tl.addLabel('return', `promote+=${config.value.moveDuration * config.value.returnDelay}`)
  tl.call(() => {
    gsap.set(frontElement, { zIndex: backSlot.zIndex })
  }, undefined, 'return')
  tl.set(frontElement, { x: backSlot.x, z: backSlot.z }, 'return')
  tl.to(
    frontElement,
    {
      y: backSlot.y,
      duration: config.value.returnDuration,
      ease: config.value.ease
    },
    'return'
  )

  tl.call(() => {
    order.value = [...rest, front]
  })
}

const stopAnimation = () => {
  if (timelineRef.value) {
    timelineRef.value.kill()
    timelineRef.value = null
  }
  if (intervalRef) {
    clearInterval(intervalRef)
    intervalRef = null
  }
}

const startAnimation = () => {
  stopAnimation()
  if (visibleCardCount.value < 2) {
    initializeCards()
    return
  }
  runSwap()
  intervalRef = window.setInterval(runSwap, props.delay)
}

const resumeAnimation = () => {
  timelineRef.value?.play()
  if (!intervalRef) intervalRef = window.setInterval(runSwap, props.delay)
}

const onMouseEnter = () => {
  stopAnimation()
}

const onMouseLeave = () => {
  resumeAnimation()
}

const setupHoverListeners = () => {
  if (!props.pauseOnHover || !containerRef.value) return
  containerRef.value.addEventListener('mouseenter', onMouseEnter)
  containerRef.value.addEventListener('mouseleave', onMouseLeave)
}

const removeHoverListeners = () => {
  if (!containerRef.value) return
  containerRef.value.removeEventListener('mouseenter', onMouseEnter)
  containerRef.value.removeEventListener('mouseleave', onMouseLeave)
}

const onCardClick = (index) => {
  emit('cardClick', index)
  if (typeof props.onCardClick === 'function') props.onCardClick(index)
}

watch(
  () => [props.cardDistance, props.verticalDistance, props.skewAmount],
  () => {
    updateCardPositions()
  }
)

watch(
  () => props.delay,
  () => {
    if (intervalRef) {
      clearInterval(intervalRef)
      intervalRef = window.setInterval(runSwap, props.delay)
    }
  }
)

watch(
  () => props.pauseOnHover,
  () => {
    removeHoverListeners()
    setupHoverListeners()
  }
)

onMounted(async () => {
  await nextTick()
  initializeCards()
  startAnimation()
  setupHoverListeners()
})

watch(
  () => visibleCardCount.value,
  async () => {
    order.value = Array.from({ length: visibleCardCount.value }, (_, idx) => idx)
    await nextTick()
    initializeCards()
    startAnimation()
  }
)

onUnmounted(() => {
  stopAnimation()
  removeHoverListeners()
})
</script>
