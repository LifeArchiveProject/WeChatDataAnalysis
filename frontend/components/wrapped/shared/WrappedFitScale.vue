<template>
  <div ref="boxEl" class="wr-fit-box">
    <div ref="contentEl" class="wr-fit-content" :style="innerStyle" :data-fit-scale="scale">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'

// 一屏自适应容器：内容自然高度超过可用高度时整体等比缩小到刚好放下。
// transform 不改变布局尺寸，scrollHeight 始终是未缩放值，测量无反馈回路。
//
// 与画幅舞台的关系：舞台自己的 scale 作用在布局盒之外，测量用的 clientHeight/scrollHeight
// 都是布局值，不受祖先 transform 影响 —— 两层 scale 是干净的乘法，没有反馈回路。
// 舞台化真正的红利是 slide 高度从「随窗口漂移的未知数」变成常量，理想终局是
// 每张卡在自己的画幅里 fitScale 恒等于 1，让这一层退化成防呆保险。
// data-fit-scale 就是为了让「哪张卡在哪个画幅下还在被压缩」可观测，而不是悄悄糊小。
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

// dev 下把「还在被压缩」喊出来：缩到 0.6 以下基本等同于「字小到看不清」，
// 在竖幅里就是变相丢元素，应该去改那张卡的排布而不是让它继续缩。
if (import.meta.dev) {
  watch(scale, (v) => {
    if (v < 0.6) console.warn(`[WrappedFitScale] 内容被压缩到 ${v}，该画幅下这张卡需要重排而不是继续缩`)
  })
}

onMounted(() => {
  measure()
  // 字体/图片等异步资源就绪后再校一次
  nextTick(measure)
  // 字体异步就绪会改变文本高度，RO 不会因 scrollHeight 变化而触发
  if (typeof document !== 'undefined' && document.fonts?.ready) {
    document.fonts.ready.then(schedule).catch(() => {})
  }
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
