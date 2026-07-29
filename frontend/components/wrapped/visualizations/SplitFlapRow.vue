<template>
  <div
    class="sf-row"
    :class="[`sf-row--${size}`, { 'sf-row--paused': paused }]"
    role="text"
    :aria-label="text"
  >
    <div
      v-for="(cell, i) in cells"
      :key="i"
      class="sf-cell"
    >
      <!-- 静态上半：翻动中提前露出新字的上半 -->
      <div class="sf-half sf-half--top">
        <span class="sf-glyph sf-glyph--top">{{ cell.flipping ? cell.next : cell.shown }}</span>
      </div>
      <!-- 静态下半：等新翻板落下前一直是旧字 -->
      <div class="sf-half sf-half--bot">
        <span class="sf-glyph sf-glyph--bot">{{ cell.shown }}</span>
      </div>

      <!-- 两段式翻板：上板携旧字折下（0→-89°），下板携新字落下（89°→0）。
           perspective 写进 transform 本身，完全不依赖 preserve-3d / backface。 -->
      <template v-if="cell.flipping">
        <div
          :key="`a-${cell.flipId}`"
          class="sf-flap sf-flap--a"
          :style="{ '--fd': `${cell.dur / 2}ms` }"
        >
          <span class="sf-glyph sf-glyph--top">{{ cell.prev }}</span>
        </div>
        <div
          :key="`b-${cell.flipId}`"
          class="sf-flap sf-flap--b"
          :style="{ '--fd': `${cell.dur / 2}ms` }"
        >
          <span class="sf-glyph sf-glyph--bot">{{ cell.next }}</span>
        </div>
      </template>

      <!-- 中缝转轴 -->
      <span class="sf-hinge" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, reactive, watch } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  // 固定格数（机械板一排格子恒定，文字居中，两侧留空板）
  cellCount: { type: Number, default: 9 },
  // 高速滚动模式：text 每次变化用 spinMs 快翻，不逐格错峰
  spinning: { type: Boolean, default: false },
  // 落定翻动时长与逐格错峰
  flipMs: { type: Number, default: 300 },
  spinMs: { type: Number, default: 150 },
  staggerMs: { type: Number, default: 55 },
  paused: { type: Boolean, default: false },
  reduced: { type: Boolean, default: false },
  size: { type: String, default: 'lg' } // 'lg' | 'md'
})

const emit = defineEmits(['settled'])

const BLANK = '　'

const padChars = (raw) => {
  let s = String(raw || '')
  const n = Math.max(1, props.cellCount)
  const arr = Array.from(s)
  let visible = arr
  if (arr.length > n) visible = [...arr.slice(0, n - 1), '…']
  const pad = n - visible.length
  const left = Math.floor(pad / 2)
  const out = []
  for (let i = 0; i < left; i += 1) out.push(BLANK)
  out.push(...visible)
  while (out.length < n) out.push(BLANK)
  return out
}

const cells = reactive(
  padChars(props.text).map((ch) => ({
    shown: ch,
    prev: ch,
    next: ch,
    pending: null,
    flipping: false,
    flipId: 0,
    dur: props.flipMs,
    timer: null
  }))
)

let staggerTimers = []
let settleToken = 0

const clearStagger = () => {
  for (const t of staggerTimers) clearTimeout(t)
  staggerTimers = []
}

const clearAllTimers = () => {
  clearStagger()
  for (const c of cells) {
    if (c.timer) { clearTimeout(c.timer); c.timer = null }
  }
}

const commitCell = (i) => {
  const c = cells[i]
  c.shown = c.next
  c.flipping = false
  c.timer = null
  const p = c.pending
  c.pending = null
  if (p != null && p !== c.shown) flipCell(i, p, c.dur)
}

const flipCell = (i, ch, dur) => {
  const c = cells[i]
  if (c.flipping) {
    c.pending = ch
    return
  }
  if (c.shown === ch) return
  c.prev = c.shown
  c.next = ch
  c.dur = Math.max(80, dur)
  c.flipping = true
  c.flipId += 1
  c.timer = setTimeout(() => commitCell(i), c.dur)
}

const applyInstant = (chars) => {
  clearAllTimers()
  chars.forEach((ch, i) => {
    const c = cells[i]
    c.shown = ch
    c.prev = ch
    c.next = ch
    c.pending = null
    c.flipping = false
  })
}

// 高速滚动：所有格子同拍快翻（pending 合并中途换字）
const applySpin = (chars) => {
  chars.forEach((ch, i) => flipCell(i, ch, props.spinMs))
}

// 落定：从左到右逐格错峰翻到目标字，最后一格落稳后 emit settled
const applySettle = (chars) => {
  clearStagger()
  settleToken += 1
  const token = settleToken
  chars.forEach((ch, i) => {
    staggerTimers.push(setTimeout(() => flipCell(i, ch, props.flipMs), i * props.staggerMs))
  })
  const total = (chars.length - 1) * props.staggerMs + props.flipMs + 60
  staggerTimers.push(setTimeout(() => {
    if (token === settleToken) emit('settled')
  }, total))
}

const apply = () => {
  const chars = padChars(props.text)
  if (props.reduced) {
    applyInstant(chars)
    emit('settled')
    return
  }
  if (props.paused) {
    // 深藏后台时不再起新翻动，直接落到目标字，避免恢复时错乱
    applyInstant(chars)
    return
  }
  if (props.spinning) {
    applySpin(chars)
  } else {
    applySettle(chars)
  }
}

watch(() => [props.text, props.spinning], apply)

onBeforeUnmount(clearAllTimers)
</script>

<style scoped>
.sf-row {
  --sf-w: 42px;
  --sf-h: 56px;
  --sf-fs: 26px;
  --sf-r: 7px;
  display: inline-flex;
  gap: 6px;
}

.sf-row--md {
  --sf-w: 30px;
  --sf-h: 40px;
  --sf-fs: 19px;
  --sf-r: 5px;
  gap: 4px;
}

.sf-cell {
  position: relative;
  width: var(--sf-w);
  height: var(--sf-h);
  border-radius: var(--sf-r);
  background: #101416;
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.05),
    inset 0 -10px 14px rgba(0, 0, 0, 0.42),
    0 1px 2px rgba(0, 0, 0, 0.5),
    0 6px 16px rgba(0, 0, 0, 0.3);
}

.sf-half {
  position: absolute;
  left: 1.5px;
  right: 1.5px;
  overflow: hidden;
}

.sf-half--top {
  top: 1.5px;
  height: calc(50% - 2.25px);
  border-radius: calc(var(--sf-r) - 2px) calc(var(--sf-r) - 2px) 2px 2px;
  background: linear-gradient(180deg, #272e33 0%, #1b2124 100%);
}

.sf-half--bot {
  bottom: 1.5px;
  height: calc(50% - 2.25px);
  border-radius: 2px 2px calc(var(--sf-r) - 2px) calc(var(--sf-r) - 2px);
  background: linear-gradient(180deg, #20262a 0%, #14191c 100%);
}

.sf-glyph {
  position: absolute;
  left: 0;
  width: 100%;
  height: calc(var(--sf-h) - 3px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--sf-fs);
  font-weight: 650;
  letter-spacing: 0;
  color: #F5EFE1;
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.4);
  user-select: none;
}

.sf-glyph--top { top: 0; }
.sf-glyph--bot { bottom: 0; }

/* 翻板：上板折下 / 下板落下。perspective 内联在 transform 中，规避 preserve-3d。 */
.sf-flap {
  position: absolute;
  left: 1.5px;
  right: 1.5px;
  height: calc(50% - 2.25px);
  overflow: hidden;
  z-index: 2;
  will-change: transform;
}

.sf-flap--a {
  top: 1.5px;
  border-radius: calc(var(--sf-r) - 2px) calc(var(--sf-r) - 2px) 2px 2px;
  background: linear-gradient(180deg, #272e33 0%, #1b2124 100%);
  transform-origin: 50% calc(100% + 2.25px);
  animation: sf-fold var(--fd, 150ms) cubic-bezier(0.55, 0.05, 0.75, 0.4) forwards;
}

/* 折下过程中板面渐暗，模拟受光变化 */
.sf-flap--a::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  opacity: 0;
  animation: sf-shade var(--fd, 150ms) linear forwards;
}

.sf-flap--b {
  bottom: 1.5px;
  border-radius: 2px 2px calc(var(--sf-r) - 2px) calc(var(--sf-r) - 2px);
  background: linear-gradient(180deg, #20262a 0%, #14191c 100%);
  transform-origin: 50% calc(0% - 2.25px);
  transform: perspective(340px) rotateX(89deg);
  animation: sf-land var(--fd, 150ms) cubic-bezier(0.3, 0.6, 0.35, 1.18) forwards;
  animation-delay: var(--fd, 150ms);
}

@keyframes sf-fold {
  from { transform: perspective(340px) rotateX(0deg); }
  to { transform: perspective(340px) rotateX(-89deg); }
}

@keyframes sf-shade {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes sf-land {
  to { transform: perspective(340px) rotateX(0deg); }
}

.sf-hinge {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 1.5px;
  transform: translateY(-50%);
  background: rgba(0, 0, 0, 0.5);
  z-index: 3;
  pointer-events: none;
}

/* 转轴两侧的小轴销 */
.sf-hinge::before,
.sf-hinge::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 2.5px;
  height: 7px;
  transform: translateY(-50%);
  border-radius: 2px;
  background: #0a0d0f;
}

.sf-hinge::before { left: 0; }
.sf-hinge::after { right: 0; }

.sf-row--paused .sf-flap--a,
.sf-row--paused .sf-flap--a::after,
.sf-row--paused .sf-flap--b {
  animation-play-state: paused;
}
</style>
