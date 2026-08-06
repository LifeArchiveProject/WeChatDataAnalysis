<template>
  <div class="w-full">
    <div class="flex items-center justify-between">
      <div v-for="(step, index) in steps" :key="index" class="flex items-center flex-1" :class="index === steps.length - 1 ? 'flex-none' : ''">
        <!-- 步骤圆点 -->
        <div class="flex items-center gap-2">
          <div
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-medium transition-colors duration-200"
            :class="getStepClass(index)"
          >
            <!-- 已完成显示勾选 -->
            <svg v-if="index < currentStep" class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
            </svg>
            <!-- 未完成显示数字 -->
            <span v-else>{{ index + 1 }}</span>
          </div>
          <!-- 步骤标题 -->
          <div
            class="whitespace-nowrap text-[13px] transition-colors duration-200"
            :class="getTextClass(index)"
          >
            {{ step.title }}
          </div>
        </div>

        <!-- 连接线 -->
        <div
          v-if="index < steps.length - 1"
          class="mx-3 h-px flex-1 transition-colors duration-200"
          :class="index < currentStep ? 'bg-[#9BD9B5]' : 'bg-[rgba(17,24,20,0.12)]'"
        ></div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  steps: {
    type: Array,
    required: true,
    // 每个step应该有 { title: string, description?: string }
  },
  currentStep: {
    type: Number,
    default: 0
  }
})

// 状态靠「填充 + 字重」区分，不靠把未开始的步骤调淡 ——
// 淡灰会被当成 disabled，让人以为不可操作。
const getStepClass = (index) => {
  if (index < props.currentStep) {
    // 已完成：描边 + 绿色勾
    return 'border border-[rgba(17,24,20,0.14)] text-[#07A34F]'
  } else if (index === props.currentStep) {
    // 当前：实心绿
    return 'border border-[#07C160] bg-[#07C160] text-white'
  }
  // 未开始：同样是描边，数字保持可读的中性灰
  return 'border border-[rgba(17,24,20,0.14)] text-[#6E756F]'
}

// 文字：当前步骤加重并压黑，其余保持正常可读的灰，不做淡化
const getTextClass = (index) => {
  if (index === props.currentStep) return 'font-medium text-[#101613]'
  return 'text-[#5A625D]'
}
</script>
