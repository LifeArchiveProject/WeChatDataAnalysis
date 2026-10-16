<template>
  <div class="cine" :class="{ 'cine--flicker': flicker && !reducedMotion }" aria-hidden="true">
    <div class="cine-grain" :style="{ opacity: grain }" />
    <div class="cine-vignette" />
  </div>
</template>

<script setup>
// 影厅材质层：胶片颗粒 + 暗角 + 放映机的轻微闪烁。
// 所有走影院风格的卡片共用这一层，保证材质一致。
import { useReducedMotion } from '~/composables/useReducedMotion'

defineProps({
  grain: { type: Number, default: 0.055 },
  flicker: { type: Boolean, default: true }
})

const reducedMotion = useReducedMotion()
</script>

<style scoped>
.cine {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 30;
}

.cine-grain {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj4KICA8ZmlsdGVyIGlkPSJuIj4KICAgIDxmZVR1cmJ1bGVuY2UgdHlwZT0iZnJhY3RhbE5vaXNlIiBiYXNlRnJlcXVlbmN5PSIwLjkiIG51bU9jdGF2ZXM9IjUiIHN0aXRjaFRpbGVzPSJzdGl0Y2giLz4KICAgIDxmZUNvbG9yTWF0cml4IHR5cGU9InNhdHVyYXRlIiB2YWx1ZXM9IjAiLz4KICA8L2ZpbHRlcj4KICA8cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsdGVyPSJ1cmwoI24pIiBvcGFjaXR5PSIwLjUiLz4KPC9zdmc+");
  background-repeat: repeat;
  background-size: 190px 190px;
  mix-blend-mode: overlay;
}

.cine-vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(78% 66% at 50% 46%, rgba(0, 0, 0, 0) 40%, rgba(0, 0, 0, 0.5) 100%);
}

.cine--flicker {
  animation: cine-flicker 5.5s ease-in-out infinite;
}

@keyframes cine-flicker {
  0%, 100% { opacity: 1; }
  17% { opacity: 0.955; }
  19% { opacity: 1; }
  46% { opacity: 0.975; }
  48% { opacity: 1; }
  73% { opacity: 0.945; }
  76% { opacity: 1; }
}
</style>
