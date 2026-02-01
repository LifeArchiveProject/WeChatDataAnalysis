<template>
  <!-- CRT 滤镜叠加层 - 复古主题使用 -->
  <div class="absolute inset-0 pointer-events-none select-none z-30" aria-hidden="true">
    <!-- 扫描线 / RGB 子像素 / 闪烁 / 暗角 / 曲率 -->
    <div class="absolute inset-0 crt-scanlines"></div>
    <div class="absolute inset-0 crt-rgb-pixels"></div>
    <div class="absolute inset-0 crt-flicker"></div>
    <div class="absolute inset-0 crt-vignette"></div>
    <div class="absolute inset-0 crt-curvature"></div>

    <!-- DOS: 语义化光标 -->
    <div v-if="theme === 'dos'" class="dos-cursor">█</div>
  </div>
</template>

<script setup>
const { theme } = useWrappedTheme()
</script>

<style scoped>
/* DOS 语义化光标 */
.dos-cursor {
  position: fixed;
  bottom: 20px;
  right: 20px;
  color: #33ff33;
  font-size: 1.5rem;
  font-family: var(--font-pixel-10), 'Courier New', monospace;
  text-shadow: 0 0 8px rgba(51, 255, 51, 0.6);
  animation: dos-cursor-blink 530ms steps(1) infinite;
  z-index: 100;
}

@keyframes dos-cursor-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
</style>
