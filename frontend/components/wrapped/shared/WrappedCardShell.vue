<template>
  <div v-if="variant === 'panel'" class="window bg-white rounded-2xl border border-[#EDEDED] overflow-hidden">
    <div class="px-6 py-5 border-b border-[#F3F3F3]">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="wrapped-title text-xl text-[#000000e6]">{{ title }}</h2>
          <slot name="narrative">
            <p v-if="narrative" class="mt-2 wrapped-body text-sm text-[#7F7F7F] whitespace-pre-wrap">
              {{ narrative }}
            </p>
          </slot>
        </div>
        <slot name="badge" />
      </div>
    </div>
    <div class="px-6 py-6">
      <slot />
    </div>
  </div>

  <!-- Slide 模式：单张卡片占据全页面，背景由外层（年度总结）统一控制 -->
  <section v-else class="relative h-full w-full overflow-hidden">
    <div :class="slideContainerClass">
      <!-- Win98：把整页内容包进一个“窗口” -->
      <div v-if="isWin98" class="window w-full flex-1 flex flex-col overflow-hidden">
        <div class="title-bar">
          <div class="title-bar-text">
            <img class="title-bar-icon" src="/assets/images/windows-0.png" alt="" aria-hidden="true" />
            <span>{{ title }}</span>
          </div>
          <div class="title-bar-controls" aria-hidden="true">
            <button type="button" aria-label="Minimize" tabindex="-1"></button>
            <button type="button" aria-label="Maximize" tabindex="-1"></button>
            <button type="button" aria-label="Close" tabindex="-1"></button>
          </div>
        </div>

        <div class="window-body flex-1 flex flex-col min-h-0">
          <slot name="narrative">
            <p v-if="narrative" class="wrapped-body text-sm sm:text-base whitespace-pre-wrap">
              {{ narrative }}
            </p>
          </slot>

          <div class="mt-4 flex-1 min-h-0 overflow-auto">
            <div class="w-full">
              <slot />
            </div>
          </div>
        </div>
      </div>

      <!-- 其他主题：保持原样 -->
      <template v-else>
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="wrapped-title text-[#000000e6]" :class="slideTitleClass">{{ title }}</h2>
            <div :class="slideNarrativeWrapClass">
              <slot name="narrative">
                <p v-if="narrative" class="mt-3 wrapped-body text-sm sm:text-base text-[#7F7F7F] max-w-2xl whitespace-pre-wrap">
                  {{ narrative }}
                </p>
              </slot>
            </div>
          </div>
          <slot name="badge" />
        </div>

        <div class="flex-1 flex items-center" :class="slideContentWrapClass">
          <div class="w-full">
            <slot />
          </div>
        </div>
      </template>
    </div>
  </section>
</template>

<script setup>
defineProps({
  cardId: { type: Number, required: true },
  title: { type: String, required: true },
  narrative: { type: String, default: '' },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const { theme } = useWrappedTheme()
const isWin98 = computed(() => theme.value === 'win98')
const isGameboy = computed(() => theme.value === 'gameboy')
const isCompactSlide = computed(() => isGameboy.value)

const slideTitleClass = computed(() => (
  isCompactSlide.value ? 'text-xl sm:text-2xl' : 'text-2xl sm:text-3xl'
))

// Keep as a computed so we can tune per-theme spacing later without touching template.
const slideNarrativeWrapClass = computed(() => '')

const slideContentWrapClass = computed(() => (
  isCompactSlide.value ? 'mt-4 sm:mt-5' : 'mt-6 sm:mt-8'
))

const slideContainerClass = computed(() => (
  isWin98.value
    ? 'relative h-full max-w-5xl mx-auto px-6 pt-2 pb-4 sm:px-8 sm:pt-3 sm:pb-6 flex flex-col'
    : (isCompactSlide.value
      ? 'relative h-full max-w-5xl mx-auto px-6 pt-5 pb-6 sm:px-8 sm:pt-6 sm:pb-7 flex flex-col'
      : 'relative h-full max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12 flex flex-col')
))
</script>

<style>
/* ========== Game Boy 主题 ========== */

/* 卡片背景 */
.wrapped-theme-gameboy .bg-white {
  background: #9bbc0f !important;
  border-color: #306230 !important;
}

/* 标题 */
.wrapped-theme-gameboy .wrapped-title {
  color: #0f380f !important;
  font-family: var(--font-pixel-10), 'Courier New', monospace;
}

/* 描述文字 */
.wrapped-theme-gameboy .wrapped-body {
  color: #306230 !important;
}

/* 数字高亮 */
.wrapped-theme-gameboy .wrapped-number {
  color: #0f380f !important;
  font-family: var(--font-pixel-10), 'Courier New', monospace;
}

/* 边框 */
.wrapped-theme-gameboy .border-\[\#EDEDED\],
.wrapped-theme-gameboy .border-\[\#F3F3F3\] {
  border-color: #306230 !important;
}

</style>
