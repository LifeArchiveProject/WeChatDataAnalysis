<template>
  <div class="w-full">
    <div class="flex items-center justify-between">
      <div v-for="(step, index) in steps" :key="index" class="flex items-center flex-1" :class="index === steps.length - 1 ? 'flex-none' : ''">
        <!-- 步骤圆点 -->
        <div class="flex flex-col items-center">
          <div 
            class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-all duration-300"
            :class="getStepClass(index)"
          >
            <!-- 已完成显示勾选 -->
            <svg v-if="index < currentStep" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
            </svg>
            <!-- 未完成显示数字 -->
            <span v-else>{{ index + 1 }}</span>
          </div>
          <!-- 步骤标题 -->
          <div 
            class="mt-2 text-xs font-medium whitespace-nowrap transition-colors duration-300"
            :class="getTextClass(index)"
          >
            {{ step.title }}
          </div>
        </div>
        
        <!-- 连接线 -->
        <div 
          v-if="index < steps.length - 1"
          class="flex-1 h-0.5 mx-4 transition-colors duration-300"
          :class="index < currentStep ? 'bg-[#07C160]' : 'bg-[#EDEDED]'"
        ></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

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

// 获取步骤圆点样式
const getStepClass = (index) => {
  if (index < props.currentStep) {
    // 已完成
    return 'bg-[#07C160] text-white'
  } else if (index === props.currentStep) {
    // 当前步骤
    return 'bg-[#07C160] text-white ring-4 ring-[#07C160]/20'
  } else {
    // 未开始
    return 'bg-[#F7F7F7] text-[#7F7F7F] border-2 border-[#EDEDED]'
  }
}

// 获取文字样式
const getTextClass = (index) => {
  if (index <= props.currentStep) {
    return 'text-[#07C160]'
  } else {
    return 'text-[#7F7F7F]'
  }
}
</script>
