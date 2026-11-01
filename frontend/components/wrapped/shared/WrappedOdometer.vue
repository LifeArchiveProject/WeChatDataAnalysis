<template>
  <span class="wodo" :class="{ 'wodo--ink': ink, 'wodo--instant': reducedMotion }" :aria-label="ariaText" role="img">
    <template v-for="(t, i) in tokens" :key="`${tokens.length}-${i}`">
      <span v-if="t.digit === null" class="wodo-sep" aria-hidden="true">{{ t.ch }}</span>
      <span v-else class="wodo-col" aria-hidden="true">
        <span
          class="wodo-strip"
          :style="{
            transform: `translateY(-${!settled && shown ? t.digit : 0}em)`,
            transitionDuration: !settled && shown ? `${duration}s` : '0s',
            transitionDelay: !settled && shown ? `${t.delay}s` : '0s'
          }"
        >
          <span
            v-for="(dv, di) in wheel(t.digit)"
            :key="di"
            class="wodo-d"
            :class="{ 'wodo-d--folded': settled && di > 0 }"
          >{{ dv }}</span>
        </span>
      </span>
    </template>
  </span>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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

// ========== 滚定之后把窗口外的九格收起来 ==========
//
// 每一位是「1em 高的窗口 + 10em 高的竖带」，靠 translateY(-Dem) 把第 D 格推进窗口。
// 代价是：竖带的前 D 格永远躺在读数**上方** D×1em 处。这一位越大、字号越大，
// 探得越远 —— hero 大数是 66px，数字 8 那一位的第一格就在读数上方 528px，
// 直接落到舞台盒外面，逐画幅审计会把它们记成「数位掉出画幅」
// （竖幅只是把读数推得离上沿更近，所以数得更多；16:9 同样有，不是画幅回归）。
//
// 滚动结束后这九格不再有用途，于是把竖带整体旋到「读数在第 0 格」，其余九格折成零高：
//   · 十格仍在 DOM 里且都在流内 → 列宽还是「十个字形取最大」，宽度一像素不动；
//   · **第 0 格照旧是满高的那一格**（滚动前是数字 0，滚定后是读数位）——
//     .wodo 是 inline-flex、外面又是 align-items:baseline 的 flex，基线取自这一格的行盒；
//     只折后九格会让基线改由别处合成，hero 大数实测从 66px 撑到 87px，正是要避开的回归；
//   · 此时 transform 已归零，读数落点与折叠前完全重合；
//   · overflow:hidden 兼作两用——裁掉零高格里的字形，并让 flex 项的
//     min-height:auto 解析成 0（否则自动最小尺寸会把它顶回 1em）。
// 因此各画幅（含 16:9）逐像素零回归，只是竖带不再向舞台外伸。
const WHEEL = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
const settled = ref(false)
let settleTimer = 0

// 滚动中是 0-9 原序；滚定后旋到读数位打头（0-9 的循环顺序不变，只是换了起点）
const wheel = (digit) => (settled.value ? WHEEL.map((_, i) => (digit + i) % 10) : WHEEL)

const clearSettleTimer = () => {
  if (settleTimer) {
    window.clearTimeout(settleTimer)
    settleTimer = 0
  }
}

// 最后一位落定的时刻 = 时长 + 最大接力延迟，再留一帧余量
const settleDelayMs = computed(() => {
  const maxDelay = tokens.value.reduce((m, t) => Math.max(m, Number(t.delay) || 0), 0)
  return Math.round((Number(props.duration) || 0) * 1000 + maxDelay * 1000) + 120
})

// play 收回（翻走本页）时必须重新展开，否则下次重播只剩一格可滚。
// 数值变化同理：新的目标位可能落在别的格上。
watch([shown, ariaText], ([isShown]) => {
  clearSettleTimer()
  settled.value = false
  if (!isShown || typeof window === 'undefined') return
  if (reducedMotion.value) {
    settled.value = true
    return
  }
  settleTimer = window.setTimeout(() => {
    settled.value = true
    settleTimer = 0
  }, settleDelayMs.value)
}, { immediate: true })

onBeforeUnmount(clearSettleTimer)
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

/* 滚定后窗口外那九格：零高 + 裁字形。留在流内只为撑住列宽（见上方注释）。 */
.wodo-d--folded {
  height: 0;
  min-height: 0;
  overflow: hidden;
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
