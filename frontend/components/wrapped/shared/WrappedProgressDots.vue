<template>
  <nav class="wrapped-progress-dots" aria-label="页面导航">
    <ol class="dots-list">
      <li v-for="(item, i) in items" :key="i">
        <button
          type="button"
          class="dot-btn"
          :class="{ 'is-active': i === activeIndex, 'is-loading': item.loading }"
          :aria-label="`跳转到第 ${i + 1} 页：${item.title}`"
          :aria-current="i === activeIndex ? 'true' : undefined"
          @click="$emit('select', i)"
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="dot-tooltip" aria-hidden="true">{{ item.title }}</span>
        </button>
      </li>
    </ol>
    <div class="dots-page wrapped-label" aria-hidden="true">{{ activeIndex + 1 }}/{{ items.length }}</div>
  </nav>
</template>

<script setup>
defineProps({
  // [{ title: String, loading: Boolean }]，顺序与 deck slide 一致（封面 + 卡片）
  items: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: 0 }
})

defineEmits(['select'])
</script>

<style scoped>
.wrapped-progress-dots {
  position: absolute;
  right: 20px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  user-select: none;
}

.dots-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* 按钮留出比圆点更大的命中区域 */
.dot-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
}

.dot-btn:focus-visible {
  outline: none;
  border-radius: 9999px;
  box-shadow: 0 0 0 2px rgba(7, 193, 96, 0.3);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 9999px;
  background: rgba(0, 0, 0, 0.16);
  transition: transform 0.25s ease, background-color 0.25s ease, border-color 0.25s ease;
}

.dot-btn:hover .dot {
  background: rgba(0, 0, 0, 0.32);
}

.dot-btn.is-active .dot {
  background: #07c160;
  transform: scale(1.45);
}

/* loading 状态：细环 spinner */
.dot-btn.is-loading .dot {
  background: transparent;
  border: 1.5px solid rgba(7, 193, 96, 0.25);
  border-top-color: #07c160;
  animation: wrapped-dot-spin 0.8s linear infinite;
}

@keyframes wrapped-dot-spin {
  to {
    transform: rotate(360deg);
  }
}

.dot-btn.is-active.is-loading .dot {
  animation: wrapped-dot-spin-active 0.8s linear infinite;
}

/* active + loading 同时保留放大与旋转 */
@keyframes wrapped-dot-spin-active {
  from {
    transform: scale(1.45) rotate(0deg);
  }
  to {
    transform: scale(1.45) rotate(360deg);
  }
}

.dot-tooltip {
  position: absolute;
  right: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%) translateX(4px);
  white-space: nowrap;
  padding: 4px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(7, 193, 96, 0.2);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
  color: rgba(0, 0, 0, 0.72);
  font-size: 12px;
  line-height: 1.4;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.dot-btn:hover .dot-tooltip,
.dot-btn:focus-visible .dot-tooltip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

.dots-page {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.4);
  font-variant-numeric: tabular-nums;
}
</style>
