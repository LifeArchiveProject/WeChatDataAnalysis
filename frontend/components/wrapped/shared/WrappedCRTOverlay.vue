<template>
  <!-- CRT/VHS 滤镜叠加层 - 根据主题切换效果 -->
  <div class="absolute inset-0 pointer-events-none select-none z-30" aria-hidden="true">
    <!-- Game Boy / DOS: 扫描线层 -->
    <div v-if="theme !== 'vhs'" class="absolute inset-0 crt-scanlines"></div>

    <!-- Game Boy / DOS: RGB 子像素层 -->
    <div v-if="theme !== 'vhs'" class="absolute inset-0 crt-rgb-pixels"></div>

    <!-- Game Boy / DOS: 闪烁层 -->
    <div v-if="theme !== 'vhs'" class="absolute inset-0 crt-flicker"></div>

    <!-- 共享: 暗角层 -->
    <div class="absolute inset-0 crt-vignette"></div>

    <!-- Game Boy / DOS: 屏幕曲率层 -->
    <div v-if="theme !== 'vhs'" class="absolute inset-0 crt-curvature"></div>

    <!-- VHS: 跟踪线效果 -->
    <div v-if="theme === 'vhs'" class="vhs-tracking"></div>

    <!-- VHS: REC 指示器 -->
    <div v-if="theme === 'vhs'" class="vhs-rec">REC</div>

    <!-- VHS: 时间戳 -->
    <div v-if="theme === 'vhs'" class="vhs-timestamp">{{ vhsTimestamp }}</div>
  </div>
</template>

<script setup>
// CRT/VHS 滤镜叠加层组件
// 根据当前主题切换不同的视觉效果

const { theme } = useWrappedTheme()

// VHS 时间戳（实时更新）
const vhsTimestamp = ref('')

const updateTimestamp = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const year = now.getFullYear()
  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
  const seconds = String(now.getSeconds()).padStart(2, '0')
  vhsTimestamp.value = `${month}/${day}/${year}  ${hours}:${minutes}:${seconds}`
}

let timestampInterval = null

onMounted(() => {
  updateTimestamp()
  timestampInterval = setInterval(updateTimestamp, 1000)
})

onUnmounted(() => {
  if (timestampInterval) {
    clearInterval(timestampInterval)
  }
})
</script>
