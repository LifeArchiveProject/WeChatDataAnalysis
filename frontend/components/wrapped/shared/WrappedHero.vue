<template>
  <div :class="rootClass">
    <div v-if="variant !== 'slide'" class="absolute inset-0 pointer-events-none">
      <div class="absolute -top-24 -left-24 w-80 h-80 bg-[#07C160] opacity-[0.08] rounded-full blur-3xl"></div>
      <div class="absolute -top-20 -right-20 w-96 h-96 bg-[#F2AA00] opacity-[0.07] rounded-full blur-3xl"></div>
      <div class="absolute -bottom-24 left-40 w-96 h-96 bg-[#10AEEF] opacity-[0.07] rounded-full blur-3xl"></div>
      <div class="absolute inset-0 bg-[linear-gradient(rgba(7,193,96,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(7,193,96,0.05)_1px,transparent_1px)] bg-[size:52px_52px] opacity-[0.35]"></div>
    </div>

    <div :class="innerClass">
      <template v-if="variant === 'slide'">
        <div class="h-full flex flex-col justify-between">
          <div class="flex items-start justify-between gap-4">
            <div class="text-xs font-semibold tracking-[0.28em] text-[#00000080]">
              WECHAT · WRAPPED
            </div>
            <div class="text-xs font-semibold tracking-[0.22em] text-[#00000055]">
              年度回望
            </div>
          </div>

          <div class="mt-10 sm:mt-14">
            <h1 class="text-4xl sm:text-6xl font-black tracking-tight text-[#000000e6] leading-[1.05]">
              把这一年的聊天
              <span class="block mt-3 text-[#07C160]">
                轻轻翻一翻
              </span>
            </h1>

            <div class="mt-7 sm:mt-9 max-w-2xl">
              <p class="text-base sm:text-lg text-[#00000080] leading-relaxed">
                有些问候写在对话框里，有些陪伴藏在深夜里。
                我们不读取内容，只把时间整理成几张卡片，让你温柔地回望这一年。
              </p>
            </div>
          </div>

          <div class="pb-1">
            <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[#00000066]">
              <!-- Intentionally left blank (avoid "feature bullet list" tone on the cover). -->
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="flex items-start justify-between gap-4">
          <div class="text-xs font-semibold tracking-[0.28em] text-[#00000080]">
            WECHAT · WRAPPED
          </div>
          <!-- 年份放到右上角（分享视图不包含账号信息） -->
          <span
            class="inline-flex items-center px-3 py-1 rounded-full text-xs bg-[#00000008] text-[#00000099] border border-[#00000010]"
          >
            {{ yearText }}
          </span>
        </div>

        <div class="mt-5 sm:mt-7 flex flex-col gap-2">
          <h1 class="text-3xl sm:text-4xl font-bold text-[#000000e6] leading-tight">
            聊天年度总结
          </h1>
          <p class="text-sm sm:text-base text-[#7F7F7F] max-w-2xl">
            从时间里回看你的聊天节奏。第一张卡：年度赛博作息表（24H × 7Days）。
          </p>
        </div>

        <!-- Badges intentionally removed: keep the hero more human and less "feature list". -->
      </template>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  year: { type: Number, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const yearText = computed(() => `${props.year}年`)

const rootClass = computed(() => {
  const base = 'relative overflow-hidden'
  return props.variant === 'slide'
    ? `${base} h-full w-full`
    : `${base} rounded-2xl border border-[#EDEDED] bg-white`
})

const innerClass = computed(() => (
  props.variant === 'slide'
    ? 'relative h-full max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12'
    : 'relative px-6 py-7 sm:px-8 sm:py-9'
))
</script>
