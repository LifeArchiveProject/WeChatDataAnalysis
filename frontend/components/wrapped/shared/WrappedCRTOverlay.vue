<template>
  <!-- CRT 滤镜叠加层 - 复古主题使用 -->
  <div class="absolute inset-0 pointer-events-none select-none z-30" aria-hidden="true">
    <!-- Game Boy: noise 作为最前景层统一覆盖整个画面 -->
    <WrappedGameboyDither
      v-if="theme === 'gameboy'"
      class="opacity-[0.3]"
      style="filter: contrast(1.16)"
      :pattern-refresh-interval="1"
      :pattern-alpha="56"
      mix-blend-mode="overlay"
      :pattern-size="256"
    />

    <!-- 扫描线 / RGB 子像素 / 闪烁 / 暗角 / 曲率 -->
    <div class="absolute inset-0 crt-scanlines"></div>
    <div class="absolute inset-0 crt-rgb-pixels"></div>
    <div class="absolute inset-0 crt-flicker"></div>
    <div class="absolute inset-0 crt-vignette"></div>
    <div class="absolute inset-0 crt-curvature"></div>

  </div>
</template>

<script setup>
const { theme } = useWrappedTheme()
</script>
