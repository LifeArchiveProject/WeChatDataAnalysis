<template>
  <div class="year-selector">
    <div class="year-modern">
      <div class="relative inline-flex items-center">
        <select
          class="appearance-none bg-transparent pr-5 pl-0 py-0.5 rounded-md wrapped-label text-xs text-[#00000066] text-right focus:outline-none focus-visible:ring-2 focus-visible:ring-[#07C160]/30 hover:bg-[#000000]/5 transition disabled:opacity-70 disabled:cursor-default"
          :disabled="years.length <= 1"
          :value="String(modelValue)"
          aria-label="选择年份"
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

// years 为降序数组（新年份在前）：更早年份 = 下标更大
const olderYear = () => {
  if (currentIndex.value >= 0 && currentIndex.value < props.years.length - 1) {
    emit('update:modelValue', props.years[currentIndex.value + 1])
  }
}

const newerYear = () => {
  if (currentIndex.value > 0) {
    emit('update:modelValue', props.years[currentIndex.value - 1])
  }
}

const onSelectChange = (e) => {
  const val = Number(e.target.value)
  if (Number.isFinite(val)) {
    emit('update:modelValue', val)
  }
}

// Shift+左右键切换年份（不带 Shift 的左右键留给 deck 翻页）
const handleKeydown = (e) => {
  if (props.years.length <= 1) return
  if (!e.shiftKey) return

  // 检查是否在可编辑元素中
  const el = e.target
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) {
    return
  }

  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    olderYear()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    newerYear()
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
