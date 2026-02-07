<template>
  <!-- Shared backdrop for modern/gameboy "Wrapped" slides (keeps cover + cards visually consistent). -->
  <div v-if="theme !== 'win98'" class="absolute inset-0 pointer-events-none select-none z-0" aria-hidden="true">
    <!-- Soft color blobs (brand + warm highlights) -->
    <div class="absolute -top-24 -left-24 w-80 h-80 bg-[#07C160] opacity-[0.08] rounded-full blur-3xl"></div>
    <div class="absolute -top-24 -right-24 w-96 h-96 bg-[#F2AA00] opacity-[0.06] rounded-full blur-3xl"></div>
    <div class="absolute -bottom-28 left-40 w-[28rem] h-[28rem] bg-[#10AEEF] opacity-[0.06] rounded-full blur-3xl"></div>

    <!-- Subtle grid for "data / report" vibe -->
    <div
      class="absolute inset-0 bg-[linear-gradient(rgba(7,193,96,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(7,193,96,0.05)_1px,transparent_1px)] bg-[size:52px_52px] opacity-[0.28]"
    ></div>

    <!-- Grain/noise: gameboy 使用动态 canvas 噪点，其它主题沿用现有纹理 -->
    <WrappedGameboyDither
      v-if="theme === 'gameboy'"
      class="opacity-[0.3]"
      style="filter: contrast(1.16)"
      :pattern-refresh-interval="1"
      :pattern-alpha="56"
      mix-blend-mode="overlay"
      :pattern-size="256"
    />
    <div v-else class="absolute inset-0 wrapped-noise-enhanced opacity-[0.08]"></div>

    <!-- Gentle vignette so typography stays readable on textured bg -->
    <div class="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-white/50 to-transparent"></div>
    <div class="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-white/40 to-transparent"></div>
  </div>

  <!-- Win98: classic desktop icons (purely decorative) -->
  <div v-else class="absolute inset-0 pointer-events-none select-none z-0" aria-hidden="true">
    <div class="win98-desktop-icons">
      <div v-for="it in desktopIcons" :key="it.label" class="win98-desktop-icon">
        <img class="win98-desktop-icon__img" :src="it.src" :alt="it.label" />
        <div class="win98-desktop-icon__label">{{ it.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
const { theme } = useWrappedTheme()

const desktopIcons = [
  { label: '我的文档', src: '/assets/images/win98-icons/folder.png' },
  { label: '图片', src: '/assets/images/win98-icons/photos.png' },
  { label: '收件箱', src: '/assets/images/win98-icons/mail.png' },
  { label: '回收站', src: '/assets/images/win98-icons/recycle.png' }
]
</script>

<style scoped>
.win98-desktop-icons {
  position: absolute;
  top: 84px; /* leave space for top-left controls */
  left: 14px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.win98-desktop-icon {
  width: 74px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.win98-desktop-icon__img {
  width: 32px;
  height: 32px;
  image-rendering: pixelated;
}

.win98-desktop-icon__label {
  max-width: 74px;
  padding: 0 2px;
  font-size: 12px;
  line-height: 1.1;
  color: #ffffff;
  text-align: center;
  text-shadow: 1px 1px 0 #000000;
  word-break: break-word;
}
</style>
