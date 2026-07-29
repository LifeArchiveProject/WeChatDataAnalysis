<template>
  <div ref="boxEl" class="wr-fit-box">
    <div ref="contentEl" class="wr-fit-content" :style="innerStyle">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'

// 一屏自适应容器：内容自然高度超过可用高度时整体等比缩小到刚好放下。
// transform 不改变布局尺寸，scrollHeight 始终是未缩放值，测量无反馈回路。
const boxEl = ref(null)
const contentEl = ref(null)
const scale = ref(1)
const measured = ref(false)

let ro = null
let raf = 0

const measure = () => {
  raf = 0
  const box = boxEl.value
  const content = contentEl.value
  if (!box || !content) return
  const bh = box.clientHeight
  const ch = content.scrollHeight
  if (!bh || !ch) return
  const next = Math.min(1, bh / ch)
  const rounded = next >= 1 ? 1 : Math.max(0.3, Math.floor(next * 1000) / 1000)
  if (Math.abs(rounded - scale.value) > 0.004) scale.value = rounded
  measured.value = true
}

const schedule = () => {
  if (raf || typeof requestAnimationFrame === 'undefined') return
  raf = requestAnimationFrame(measure)
}

onMounted(() => {
  measure()
  // 字体/图片等异步资源就绪后再校一次
  nextTick(measure)
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(schedule)
    if (boxEl.value) ro.observe(boxEl.value)
    if (contentEl.value) ro.observe(contentEl.value)
  }
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
  if (raf && typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(raf)
})

const innerStyle = computed(() => {
  const style = {}
  if (scale.value < 1) {
    style.transform = `scale(${scale.value})`
    style.transformOrigin = '50% 50%'
  }
  // 首次测量前隐藏，避免超高内容闪现一帧再缩小
  if (!measured.value) style.visibility = 'hidden'
  return style
})
</script>

<style scoped>
.wr-fit-box {
  height: 100%;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wr-fit-content {
  width: 100%;
  flex: 0 0 auto;
}
</style>
