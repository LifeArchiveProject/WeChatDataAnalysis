<template>
  <span class="wodo" :class="{ 'wodo--ink': ink, 'wodo--instant': reducedMotion }" :aria-label="ariaText" role="img">
    <template v-for="(t, i) in tokens" :key="`${tokens.length}-${i}`">
      <span v-if="t.digit === null" class="wodo-sep" aria-hidden="true">{{ t.ch }}</span>
      <span v-else class="wodo-col" aria-hidden="true">
        <span
          class="wodo-strip"
          :style="{
            transform: `translateY(-${shown ? t.digit : 0}em)`,
            transitionDuration: shown ? `${duration}s` : '0s',
            transitionDelay: shown ? `${t.delay}s` : '0s'
          }"
        >
          <span v-for="d in 10" :key="d" class="wodo-d">{{ d - 1 }}</span>
        </span>
      </span>
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useReducedMotion } from '~/composables/useReducedMotion'

// 里程表数字：每一位是一条 0-9 的竖排滚轮，play=true 时从 0 滚到目标位。
// play=false 时瞬时归零（transition 置 0），供翻回本页时重播。
const props = defineProps({
  value: { type: Number, default: 0 },
  // 触发滚动；false 时立刻回到全 0
  play: { type: Boolean, default: true },
  duration: { type: Number, default: 1.5 },
  // 每一位的接力延迟（从最高位开始）
  stagger: { type: Number, default: 0.055 },
  // 渐变墨着色（沿用年度总结的墨绿大数语言）
  ink: { type: Boolean, default: false }
})

const reducedMotion = useReducedMotion()
const shown = computed(() => props.play || reducedMotion.value)

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const ariaText = computed(() => nfInt.format(Math.round(Number(props.value) || 0)))

const tokens = computed(() => {
  const chars = ariaText.value.split('')
  let digitIdx = 0
  const digitCount = chars.filter((c) => /\d/.test(c)).length
  return chars.map((ch) => {
    if (!/\d/.test(ch)) return { ch, digit: null, delay: 0 }
    const t = { ch, digit: Number(ch), delay: digitIdx * props.stagger }
    digitIdx += 1
    // 低位稍晚落定，读起来像进位完成
    void digitCount
    return t
  })
})
</script>

<style scoped>
.wodo {
  display: inline-flex;
  align-items: flex-start;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  vertical-align: baseline;
}

.wodo-col {
  display: inline-block;
  height: 1em;
  overflow: hidden;
}

.wodo-strip {
  display: flex;
  flex-direction: column;
  transition-property: transform;
  transition-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
  will-change: transform;
}

.wodo--instant .wodo-strip {
  transition: none !important;
}

.wodo-d {
  display: block;
  height: 1em;
  line-height: 1;
  text-align: center;
}

.wodo-sep {
  display: inline-block;
  line-height: 1;
  opacity: 0.55;
  padding: 0 0.02em;
}

/* 渐变墨：与末页大数同源的墨绿 */
.wodo--ink .wodo-d {
  background: linear-gradient(180deg, var(--wodo-hi, #10ac63) 0%, var(--wodo-lo, #05673a) 92%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.wodo--ink .wodo-sep {
  color: var(--wodo-lo, #05673a);
  opacity: 0.45;
}
</style>
