<template>
  <div v-if="variant === 'panel'" class="bg-white rounded-2xl border border-[#EDEDED] overflow-hidden">
    <div class="px-6 py-5 border-b border-[#F3F3F3]">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-xs font-semibold tracking-[0.22em] text-[#00000066]">
            CARD {{ String(cardId).padStart(2, '0') }}
          </div>
          <h2 class="mt-2 text-xl font-bold text-[#000000e6]">{{ title }}</h2>
          <p v-if="narrative" class="mt-2 text-sm text-[#7F7F7F]">
            {{ narrative }}
          </p>
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
    <div class="relative h-full max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12 flex flex-col">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-xs font-semibold tracking-[0.22em] text-[#00000066]">
            CARD {{ String(cardId).padStart(2, '0') }}
          </div>
          <h2 class="mt-2 text-2xl sm:text-3xl font-bold text-[#000000e6]">{{ title }}</h2>
          <p v-if="narrative" class="mt-3 text-sm sm:text-base text-[#7F7F7F] max-w-2xl">
            {{ narrative }}
          </p>
        </div>
        <slot name="badge" />
      </div>

      <div class="mt-6 sm:mt-8 flex-1 flex items-center">
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
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})
</script>
