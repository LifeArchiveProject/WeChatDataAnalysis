<template>
  <div class="year-selector">
    <div class="year-modern">
      <div class="relative inline-flex items-center">
        <select
          class="appearance-none bg-transparent pr-5 pl-0 py-0.5 rounded-md wrapped-label text-xs text-[#00000066] text-right focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 hover:bg-[#000000]/5 transition disabled:opacity-70 disabled:cursor-default"
          :disabled="years.length <= 1"
          :value="String(modelValue)"
          @change="onSelectChange"
        >
          <option v-for="y in years" :key="y" :value="String(y)">{{ y }}年</option>
        </select>
        <svg
          v-if="years.length > 1"
          class="pointer-events-none absolute right-1 w-3 h-3 text-[#00000066]"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 10.94l3.71-3.71a.75.75 0 1 1 1.06 1.06l-4.24 4.24a.75.75 0 0 1-1.06 0L5.21 8.29a.75.75 0 0 1 .02-1.08z"
            clip-rule="evenodd"
          />
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: Number,
    required: true
  },
  years: {
    type: Array,
    required: true
  }
})

const emit = defineEmits(['update:modelValue'])

const currentIndex = computed(() => props.years.indexOf(props.modelValue))
const canGoPrev = computed(() => currentIndex.value > 0)
const canGoNext = computed(() => currentIndex.value < props.years.length - 1)

const prevYear = () => {
  if (canGoPrev.value) {
    emit('update:modelValue', props.years[currentIndex.value - 1])
  }
}

const nextYear = () => {
  if (canGoNext.value) {
    emit('update:modelValue', props.years[currentIndex.value + 1])
  }
}

const onSelectChange = (e) => {
  const val = Number(e.target.value)
  if (Number.isFinite(val)) {
    emit('update:modelValue', val)
  }
}

// 全局左右键切换年份（所有主题）
const handleKeydown = (e) => {
  if (props.years.length <= 1) return

  // 检查是否在可编辑元素中
  const el = e.target
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) {
    return
  }

  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    prevYear()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    nextYear()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
/* ========== Modern 风格 ========== */
.year-modern {
  display: flex;
  align-items: center;
}
</style>
