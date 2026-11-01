<template>
  <span class="od" :class="`od--${size}`" role="text" :aria-label="String(displayValue)">
    <template v-for="(slot, i) in slots" :key="i">
      <span v-if="slot.sep" class="od-sep" :class="{ 'od-sep--dim': slot.dim }">,</span>
      <span v-else class="od-digit">
        <span
          class="od-strip"
          :style="{ transform: `translateY(calc(${slot.pos} * var(--od-h) * -1))` }"
        >
          <span v-for="d in 10" :key="d" class="od-ch">{{ d - 1 }}</span>
          <span class="od-ch od-ch--blank">&nbsp;</span>
        </span>
      </span>
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'

// 机械里程表：每一位是一条 0-9 竖带，靠 translateY 滚动到当前数字。
// 位数由 maxValue 固定（终值已知），前导零显示为空板，跨千分位插逗号。
const props = defineProps({
  value: { type: Number, default: 0 },
  maxValue: { type: Number, default: 0 },
  size: { type: String, default: 'md' } // 'md' | 'lg'
})

const displayValue = computed(() => Math.max(0, Math.round(Number(props.value) || 0)))

const digitCount = computed(() => {
  const m = Math.max(1, Math.round(Number(props.maxValue) || 0), displayValue.value)
  return String(m).length
})

const slots = computed(() => {
  const n = digitCount.value
  const str = String(displayValue.value).padStart(n, ' ')
  const out = []
  for (let i = 0; i < n; i += 1) {
    const ch = str[i]
    const digitsLeft = n - i // 本位起（含）右侧还有几位
    if (i > 0 && digitsLeft % 3 === 0) {
      // 逗号左侧全是空板时淡显
      out.push({ sep: true, dim: str.slice(0, i).trim() === '' })
    }
    out.push({ sep: false, pos: ch === ' ' ? 10 : Number(ch) })
  }
  return out
})
</script>

<style scoped>
.od {
  --od-h: 1.25em;
  display: inline-flex;
  align-items: center;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.od-digit {
  display: inline-block;
  height: var(--od-h);
  overflow: hidden;
}

.od-strip {
  display: block;
  transition: transform 150ms cubic-bezier(0.3, 0.5, 0.4, 1) !important;
  will-change: transform;
}

.od-ch {
  display: block;
  height: var(--od-h);
  line-height: var(--od-h);
  text-align: center;
  min-width: 1ch;
}

.od-sep {
  display: inline-block;
  line-height: var(--od-h);
  opacity: 0.55;
  transition: opacity 150ms ease !important;
}

.od-sep--dim {
  opacity: 0;
}
</style>
