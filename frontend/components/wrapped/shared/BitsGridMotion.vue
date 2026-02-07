<template>
  <div class="bits-grid-motion w-full h-full overflow-hidden">
    <section class="relative flex h-full w-full items-center justify-center overflow-hidden" :style="sectionStyle">
      <div class="bits-grid-motion-grid">
        <div
          v-for="rowIndex in safeRowCount"
          :key="`row-${rowIndex}`"
          class="bits-grid-motion-row"
          :style="rowInlineStyle"
        >
          <div
            v-for="columnIndex in renderColumnCount"
            :key="`cell-${rowIndex}-${columnIndex}`"
            class="bits-grid-motion-cell"
            v-show="loopedItems[resolveIndex(rowIndex, columnIndex)]"
          >
            <slot
              name="item"
              :item="loopedItems[resolveIndex(rowIndex, columnIndex)]"
              :index="resolveIndex(rowIndex, columnIndex)"
            >
              <div class="bits-grid-motion-fallback">
                {{ String(loopedItems[resolveIndex(rowIndex, columnIndex)] ?? '') }}
              </div>
            </slot>
          </div>
        </div>
      </div>

      <div class="bits-grid-motion-mask" />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import gsap from 'gsap'

const props = defineProps({
  items: { type: Array, default: () => [] },
  gradientColor: { type: String, default: 'rgba(7, 193, 96, 0.2)' },
  rowCount: { type: Number, default: 8 },
  columnCount: { type: Number, default: 10 },
  scrollSpeed: { type: Number, default: 38 },
  baseOffsetX: { type: Number, default: 0 },
  itemWidth: { type: Number, default: 300 },
  rowGap: { type: Number, default: 12 }
})

let removeTicker = null
let lastTickAt = 0
let loopDistance = 0
const marqueeX = ref(0)

const safeRowCount = computed(() => Math.max(1, Number(props.rowCount) || 1))
const safeColumnCount = computed(() => Math.max(1, Number(props.columnCount) || 1))
const safeItemWidth = computed(() => Math.max(1, Number(props.itemWidth) || 1))
const safeRowGap = computed(() => Math.max(0, Number(props.rowGap) || 0))
const safeScrollSpeed = computed(() => Math.max(0, Number(props.scrollSpeed) || 0))

const renderColumnCount = computed(() => safeColumnCount.value * 2)
const totalSlots = computed(() => safeRowCount.value * renderColumnCount.value)

const repeatedItems = computed(() => {
  const source = Array.isArray(props.items) ? props.items.filter(Boolean) : []
  if (!source.length) return []
  const output = []
  for (let idx = 0; idx < safeRowCount.value * safeColumnCount.value; idx += 1) {
    output.push(source[idx % source.length])
  }
  return output
})

const loopedItems = computed(() => {
  const base = repeatedItems.value
  if (!base.length) return []
  const output = []
  for (let idx = 0; idx < totalSlots.value; idx += 1) {
    output.push(base[idx % base.length])
  }
  return output
})

const rowInlineStyle = computed(() => ({
  willChange: 'transform',
  transform: `translate3d(${props.baseOffsetX + marqueeX.value}px, 0, 0)`
}))

const sectionStyle = computed(() => ({
  background: `radial-gradient(circle at center, ${props.gradientColor} 0%, transparent 72%)`
}))

const resolveIndex = (rowIndex, columnIndex) => (
  (Number(rowIndex) - 1) * renderColumnCount.value + (Number(columnIndex) - 1)
)

const updateMotion = () => {
  if (typeof window === 'undefined') return

  const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
  const dt = lastTickAt > 0 ? Math.min((now - lastTickAt) / 1000, 0.08) : 0
  lastTickAt = now

  if (loopDistance <= 0 || safeScrollSpeed.value <= 0 || dt <= 0) return

  marqueeX.value -= safeScrollSpeed.value * dt
  if (marqueeX.value <= -loopDistance) {
    marqueeX.value += loopDistance
  }
}

onMounted(() => {
  if (typeof window === 'undefined') return

  loopDistance = safeColumnCount.value * (safeItemWidth.value + safeRowGap.value)
  marqueeX.value = 0
  lastTickAt = 0

  // Kick one frame immediately to avoid initial static delay.
  marqueeX.value = -Math.min(loopDistance * 0.02, 8)

  gsap.ticker.lagSmoothing(1000, 33)
  removeTicker = gsap.ticker.add(updateMotion)
})

onUnmounted(() => {
  loopDistance = 0
  lastTickAt = 0
  if (typeof removeTicker === 'function') removeTicker()
})
</script>

<style scoped>
.bits-grid-motion-grid {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  width: 180%;
  height: 165%;
  transform: rotate(-15deg);
  transform-origin: center;
}

.bits-grid-motion-row {
  display: flex;
  gap: 12px;
}

.bits-grid-motion-cell {
  position: relative;
  height: 210px;
  min-width: 300px;
  flex-shrink: 0;
}

.bits-grid-motion-fallback {
  height: 100%;
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(7, 193, 96, 0.2);
  background: #ffffff;
  color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  text-align: center;
  font-size: 14px;
}

.bits-grid-motion-mask {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(243, 255, 248, 0.78) 0%, rgba(243, 255, 248, 0.12) 20%, rgba(243, 255, 248, 0) 38%),
    linear-gradient(90deg, rgba(243, 255, 248, 0.86) 0%, rgba(243, 255, 248, 0.12) 24%, rgba(243, 255, 248, 0) 44%),
    linear-gradient(270deg, rgba(243, 255, 248, 0.9) 0%, rgba(243, 255, 248, 0.14) 30%, rgba(243, 255, 248, 0) 48%),
    linear-gradient(0deg, rgba(243, 255, 248, 0.88) 0%, rgba(243, 255, 248, 0.16) 36%, rgba(243, 255, 248, 0) 58%);
  z-index: 3;
}
</style>
