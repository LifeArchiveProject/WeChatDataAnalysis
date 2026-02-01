<template>
  <div class="year-selector" :class="selectorClass">
    <!-- Game Boy 风格 -->
    <div v-if="theme === 'gameboy'" class="year-gameboy">
      <div class="gameboy-year-box">
        <button
          class="gameboy-arrow"
          :disabled="!canGoPrev"
          @click="prevYear"
          aria-label="Previous year"
        >◀</button>
        <span class="gameboy-year-value">{{ modelValue }}</span>
        <button
          class="gameboy-arrow"
          :disabled="!canGoNext"
          @click="nextYear"
          aria-label="Next year"
        >▶</button>
      </div>
    </div>

    <!-- DOS 风格 -->
    <div v-else-if="theme === 'dos'" class="year-dos">
      <span class="dos-prompt">C:\WRAPPED&gt;</span>
      <span class="dos-label">YEAR:</span>
      <button
        class="dos-arrow"
        :disabled="!canGoPrev"
        @click="prevYear"
        aria-label="Previous year"
      >[-]</button>
      <span class="dos-value">{{ modelValue }}</span>
      <button
        class="dos-arrow"
        :disabled="!canGoNext"
        @click="nextYear"
        aria-label="Next year"
      >[+]</button>
    </div>

    <!-- Modern 风格：下拉菜单（默认） -->
    <div v-else class="year-modern">
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

const { theme } = useWrappedTheme()

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

const selectorClass = computed(() => {
  return `year-selector-${theme.value}`
})

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

/* ========== Game Boy 风格 ========== */
.year-gameboy {
  font-family: 'Press Start 2P', 'Courier New', monospace;
}

.gameboy-year-box {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #0f380f;
  border: 3px solid #306230;
  padding: 6px 8px;
  box-shadow:
    inset 2px 2px 0 #9bbc0f,
    inset -2px -2px 0 #0f380f;
}

.gameboy-arrow {
  background: #306230;
  border: none;
  color: #9bbc0f;
  font-size: 8px;
  padding: 4px 6px;
  cursor: pointer;
  transition: background 0.1s;
}

.gameboy-arrow:hover:not(:disabled) {
  background: #8bac0f;
  color: #0f380f;
}

.gameboy-arrow:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.gameboy-year-value {
  color: #9bbc0f;
  font-size: 10px;
  min-width: 40px;
  text-align: center;
  letter-spacing: 2px;
}

/* ========== DOS 风格 ========== */
.year-dos {
  font-family: 'Courier New', 'Consolas', monospace;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
  color: #33ff33;
  text-shadow: 0 0 5px #33ff33;
}

.dos-prompt {
  color: #1a5c1a;
}

.dos-label {
  color: #33ff33;
}

.dos-arrow {
  background: transparent;
  border: none;
  color: #33ff33;
  font-family: inherit;
  font-size: inherit;
  cursor: pointer;
  padding: 0 2px;
  text-shadow: 0 0 5px #33ff33;
  transition: color 0.1s;
}

.dos-arrow:hover:not(:disabled) {
  color: #66ff66;
  text-shadow: 0 0 8px #66ff66;
}

.dos-arrow:disabled {
  color: #1a5c1a;
  cursor: not-allowed;
  text-shadow: none;
}

.dos-value {
  background: #0a1a0a;
  padding: 2px 6px;
  border: 1px solid #1a5c1a;
  letter-spacing: 1px;
  min-width: 50px;
  text-align: center;
}
</style>
