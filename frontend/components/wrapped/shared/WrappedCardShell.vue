<template>
  <div v-if="variant === 'panel'" class="bg-white rounded-2xl border border-[#EDEDED] overflow-hidden">
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
    <div
      class="relative h-full flex flex-col"
      :class="hideChrome ? '' : (wide
        ? 'px-10 pt-20 pb-12 sm:px-14 sm:pt-24 sm:pb-14 lg:px-20 xl:px-20 2xl:px-40'
        : 'max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12')"
    >
        <div v-if="!hideChrome" class="flex items-start justify-between gap-4">
          <div>
            <h2 class="wrapped-title text-2xl sm:text-3xl text-[#000000e6]">{{ title }}</h2>
            <slot name="narrative">
              <p v-if="narrative" class="mt-3 wrapped-body text-sm sm:text-base text-[#7F7F7F] max-w-2xl whitespace-pre-wrap">
                {{ narrative }}
              </p>
            </slot>
          </div>
          <slot name="badge" />
        </div>

        <div class="flex-1 flex items-center" :class="hideChrome ? '' : 'mt-6 sm:mt-8'">
          <div class="w-full">
            <slot />
          </div>
        </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  cardId: { type: Number, required: true },
  title: { type: String, required: true },
  narrative: { type: String, default: '' },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  // Slide 模式下是否取消 max-width 限制（让内容直接铺满页面宽度）。
  // 用于需要横向展示的可视化（如年度日历热力图）。
  wide: { type: Boolean, default: false },
  // 隐藏标题/叙事区域（如关键词卡片 storm 阶段沉浸模式）。
  hideChrome: { type: Boolean, default: false }
})
</script>
