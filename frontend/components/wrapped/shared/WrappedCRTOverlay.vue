<template>
  <!-- CRT 滤镜叠加层 - 模拟老电视机效果 -->
  <div class="absolute inset-0 pointer-events-none select-none z-30" aria-hidden="true">
    <!-- 扫描线层 - 水平条纹带滚动动画 -->
    <div class="absolute inset-0 crt-scanlines"></div>

    <!-- RGB 子像素层 - 模拟 CRT 像素结构 -->
    <div class="absolute inset-0 crt-rgb-pixels"></div>

    <!-- 闪烁层 - 轻微亮度波动 -->
    <div class="absolute inset-0 crt-flicker"></div>

    <!-- 暗角层 - 边缘渐暗效果 -->
    <div class="absolute inset-0 crt-vignette"></div>

    <!-- 屏幕曲率层 - 边缘微暗模拟曲面 -->
    <div class="absolute inset-0 crt-curvature"></div>
  </div>
</template>

<script setup>
// CRT 滤镜叠加层组件
// 通过多层叠加实现复古显像管效果，不修改原始背景
</script>
