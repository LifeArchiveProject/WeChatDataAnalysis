<template>
  <canvas
    ref="grainRef"
    class="pointer-events-none absolute inset-0 h-full w-full"
    :style="canvasStyle"
    aria-hidden="true"
  ></canvas>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  patternRefreshInterval: {
    type: Number,
    default: 2
  },
  patternAlpha: {
    type: Number,
    default: 20
  },
  mixBlendMode: {
    type: String,
    default: 'multiply'
  },
  patternSize: {
    type: Number,
    default: 512
  }
})

const grainRef = ref(null)

const canvasStyle = computed(() => `image-rendering: pixelated; mix-blend-mode: ${props.mixBlendMode};`)

let animationId = 0
let frame = 0
let noiseData
let noise32

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const resize = () => {
  const canvas = grainRef.value
  if (!canvas) return
  const size = Math.max(64, Math.round(props.patternSize))
  canvas.width = size
  canvas.height = size
}

const initImageData = (ctx) => {
  const canvas = grainRef.value
  if (!canvas) return
  noiseData = ctx.createImageData(canvas.width, canvas.height)
  noise32 = new Uint32Array(noiseData.data.buffer)
}

const drawGrain = () => {
  if (!noise32) return
  const alpha = clamp(Math.round(props.patternAlpha), 0, 255) << 24
  for (let i = 0; i < noise32.length; i++) {
    const value = (Math.random() * 255) | 0
    noise32[i] = alpha | (value << 16) | (value << 8) | value
  }
}

const loop = (ctx) => {
  const refreshEvery = Math.max(1, Math.round(props.patternRefreshInterval))
  if (frame % refreshEvery === 0) {
    drawGrain()
    ctx.putImageData(noiseData, 0, 0)
  }

  frame++
  animationId = window.requestAnimationFrame(() => loop(ctx))
}

onMounted(() => {
  const canvas = grainRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d', { alpha: true })
  if (!ctx) return

  resize()
  initImageData(ctx)
  drawGrain()
  ctx.putImageData(noiseData, 0, 0)
  loop(ctx)

  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  window.cancelAnimationFrame(animationId)
})
</script>
