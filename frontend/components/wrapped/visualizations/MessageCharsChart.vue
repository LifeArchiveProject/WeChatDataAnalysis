<template>
  <div class="w-full">
    <!-- 聊天气泡区域 -->
    <div class="rounded-2xl border border-[#00000010] bg-[#F5F5F5] p-3 sm:p-4">
      <div class="flex flex-col gap-3">
        <!-- Received (left) -->
        <div class="flex items-end gap-2">
          <div class="avatar-box bg-white">
            <svg viewBox="0 0 24 24" class="w-4 h-4" fill="none" stroke="#07C160" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M8 3h10a2 2 0 0 1 2 2v14H6V5a2 2 0 0 1 2-2z" />
              <path d="M6 7H4a2 2 0 0 0-2 2v10h4" />
            </svg>
          </div>
          <div class="bubble-left">
            <div class="wrapped-label text-xs text-[#00000066]">你收到的字</div>
            <div class="mt-0.5 wrapped-number text-xl sm:text-2xl text-[#000000e6]">
              {{ formatInt(receivedChars) }}
            </div>
            <div class="mt-1 wrapped-body text-xs text-[#7F7F7F]">
              <template v-if="receivedA4Text">{{ receivedA4Text }}</template>
              <template v-else-if="receivedChars > 0">这么多字，都是别人认真对你的回应。</template>
              <template v-else>今年还没有收到文字消息。</template>
            </div>
            <div v-if="receivedA4 && receivedA4.a4 && receivedA4.a4.sheets > 0" class="mt-1 text-[10px] text-[#00000055] wrapped-label">
              约 {{ formatInt(receivedA4.a4.sheets) }} 张 A4 · 堆叠高度约 {{ receivedA4.a4.heightText }}
            </div>
          </div>
        </div>

        <!-- Sent (right) -->
        <div class="flex items-end gap-2 justify-end">
          <div class="bubble-right">
            <div class="wrapped-label text-xs text-[#00000080] text-right">你发送的字</div>
            <div class="mt-0.5 wrapped-number text-xl sm:text-2xl text-[#000000e6] text-right">
              {{ formatInt(sentChars) }}
            </div>
            <div class="mt-1 wrapped-body text-xs text-[#00000099] text-right">
              <template v-if="sentBookText">{{ sentBookText }}</template>
              <template v-else-if="sentChars > 0">这么多字，是你打出的每一次认真。</template>
              <template v-else>今年还没有文字消息。</template>
            </div>
          </div>
          <div class="avatar-box bg-[#95EC69]">
            <svg viewBox="0 0 24 24" class="w-4 h-4" fill="none" stroke="#1f2d1f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- 键盘磨损可视化 -->
    <div class="keyboard-outer">
      <div class="keyboard-inner">
        <!-- 顶部信息 -->
        <div class="keyboard-header">
          <div class="keyboard-dots">
            <span class="dot dot-red"></span>
            <span class="dot dot-yellow"></span>
            <span class="dot dot-green"></span>
          </div>
          <div class="keyboard-stats">{{ formatInt(totalKeyHits) }} KEYSTROKES</div>
        </div>

        <!-- 键盘主体 -->
        <div class="keyboard-body">
          <div v-for="(row, ri) in keyboardRows" :key="ri" class="kb-row">
            <div
              v-for="key in row"
              :key="key.code + key.label"
              class="kb-key"
              :class="[`kb-w-${key.w || 1}`, { 'kb-space': key.isSpace }]"
              :style="getKeyStyle(key.code)"
            >
              <div class="kb-key-top" :style="getKeyTopStyle(key.code)">
                <span v-if="key.sub" class="kb-sub">{{ key.sub }}</span>
                <span v-if="key.label" class="kb-label" :class="{ 'kb-label-sm': key.isFunc }" :style="getLabelStyle(key.code)">{{ key.label }}</span>
                <div v-if="key.isSpace" class="kb-space-bar"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部品牌 -->
        <div class="keyboard-brand">WeChat Mechanical KB</div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  data: { type: Object, default: () => ({}) }
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const sentChars = computed(() => Number(props.data?.sentChars || 0))
const receivedChars = computed(() => Number(props.data?.receivedChars || 0))

const sentBookText = computed(() => props.data?.sentBook?.text || '')
const receivedA4 = computed(() => props.data?.receivedA4 || null)
const receivedA4Text = computed(() => receivedA4.value?.text || '')

// 从后端获取键盘统计数据
const keyboardData = computed(() => props.data?.keyboard || null)

// 总敲击次数（优先使用后端数据）
const totalKeyHits = computed(() => {
  // 注意：totalKeyHits 可能为 0（比如今年没发出文字消息），不能用 truthy 判断。
  const backend = Number(keyboardData.value?.totalKeyHits)
  if (Number.isFinite(backend)) return backend

  // 回退：粗略估算（仅基于"你发送的字"，假设拼音输入 + 一定比例空格）
  const letterHits = Math.round(sentChars.value * 2.8)
  return letterHits + Math.round(letterHits * 0.15)
})

// 获取各键的敲击次数（优先使用后端精确数据）
const keyHitsMap = computed(() => {
  const backendHits = keyboardData.value?.keyHits
  const backendSpace = Number(keyboardData.value?.spaceHits || 0)
  if (backendHits && typeof backendHits === 'object') {
    // 后端把空格次数单独放在 spaceHits，这里合并进 keyHitsMap 以便空格键也能显示磨损。
    return backendSpace > 0 ? { ...backendHits, space: backendSpace } : backendHits
  }

  // 回退：使用默认频率估算（仅基于"你发送的字"）
  const defaultFreq = {
    a: 0.121, i: 0.118, n: 0.098, e: 0.089, u: 0.082, g: 0.072, h: 0.065,
    o: 0.052, z: 0.048, s: 0.042, x: 0.038, y: 0.036, d: 0.032, l: 0.028,
    j: 0.026, b: 0.022, c: 0.020, w: 0.018, m: 0.016, f: 0.014, t: 0.012,
    r: 0.010, p: 0.009, k: 0.007, q: 0.005, v: 0.001,
  }
  const letterHits = Math.round(sentChars.value * 2.8)
  const spaceHits = Math.round(letterHits * 0.15)
  const result = {}
  for (const [k, freq] of Object.entries(defaultFreq)) {
    result[k] = Math.round(freq * letterHits)
  }
  if (spaceHits > 0) result.space = spaceHits
  return result
})

// 计算磨损程度（0-1），基于实际敲击次数
const getWear = (code) => {
  const k = code.toLowerCase()
  const hits = Number(keyHitsMap.value[k] || 0)
  if (!Number.isFinite(hits) || hits <= 0) return 0

  const values = Object.values(keyHitsMap.value).map((v) => Number(v) || 0)
  const maxHits = Math.max(...values, 1)
  // 小数量级键（如数字/标点）容易"看起来没变化"，用对数缩放增强可视化差异。
  const ratio = Math.log1p(hits) / Math.log1p(maxHits)
  return Math.min(1, Math.pow(ratio, 1.6))
}

// 键盘布局
const keyboardRows = [
  [
    { code: '`', label: '`', sub: '~' }, { code: '1', label: '1', sub: '!' },
    { code: '2', label: '2', sub: '@' }, { code: '3', label: '3', sub: '#' },
    { code: '4', label: '4', sub: '$' }, { code: '5', label: '5', sub: '%' },
    { code: '6', label: '6', sub: '^' }, { code: '7', label: '7', sub: '&' },
    { code: '8', label: '8', sub: '*' }, { code: '9', label: '9', sub: '(' },
    { code: '0', label: '0', sub: ')' }, { code: '-', label: '-', sub: '_' },
    { code: '=', label: '=', sub: '+' }, { code: 'backspace', label: '⌫', w: 2, isFunc: true },
  ],
  [
    { code: 'tab', label: 'Tab', w: 1.5, isFunc: true },
    { code: 'q', label: 'Q' }, { code: 'w', label: 'W' }, { code: 'e', label: 'E' },
    { code: 'r', label: 'R' }, { code: 't', label: 'T' }, { code: 'y', label: 'Y' },
    { code: 'u', label: 'U' }, { code: 'i', label: 'I' }, { code: 'o', label: 'O' },
    { code: 'p', label: 'P' }, { code: '[', label: '[', sub: '{' },
    { code: ']', label: ']', sub: '}' }, { code: '\\', label: '\\', sub: '|', w: 1.5 },
  ],
  [
    { code: 'caps', label: 'Caps', w: 1.75, isFunc: true },
    { code: 'a', label: 'A' }, { code: 's', label: 'S' }, { code: 'd', label: 'D' },
    { code: 'f', label: 'F' }, { code: 'g', label: 'G' }, { code: 'h', label: 'H' },
    { code: 'j', label: 'J' }, { code: 'k', label: 'K' }, { code: 'l', label: 'L' },
    { code: ';', label: ';', sub: ':' }, { code: "'", label: "'", sub: '"' },
    { code: 'enter', label: 'Enter', w: 2.25, isFunc: true },
  ],
  [
    { code: 'shift', label: 'Shift', w: 2.25, isFunc: true },
    { code: 'z', label: 'Z' }, { code: 'x', label: 'X' }, { code: 'c', label: 'C' },
    { code: 'v', label: 'V' }, { code: 'b', label: 'B' }, { code: 'n', label: 'N' },
    { code: 'm', label: 'M' }, { code: ',', label: ',', sub: '<' },
    { code: '.', label: '.', sub: '>' }, { code: '/', label: '/', sub: '?' },
    { code: 'shift', label: 'Shift', w: 2.75, isFunc: true },
  ],
  [
    { code: 'ctrl', label: 'Ctrl', w: 1.25, isFunc: true },
    { code: 'alt', label: 'Alt', w: 1.25, isFunc: true },
    { code: 'space', label: '', w: 6.25, isSpace: true },
    { code: 'alt', label: 'Alt', w: 1.25, isFunc: true },
    { code: 'ctrl', label: 'Ctrl', w: 1.25, isFunc: true },
  ],
]

// 键帽样式
const getKeyStyle = (code) => {
  const w = getWear(code)
  // Light theme: clean keys are bright; wear makes keys warmer and slightly darker.
  const baseL = 94 - w * 18
  const sat = 8 + w * 20
  return {
    '--key-bg': `hsl(40, ${sat}%, ${baseL}%)`,
    '--key-bg-dark': `hsl(40, ${sat}%, ${baseL - 6}%)`,
    '--key-border': `hsl(40, ${Math.max(0, sat - 2)}%, ${baseL - 18}%)`,
  }
}

const getKeyTopStyle = (code) => {
  const w = getWear(code)
  const highlight = 0.55 - w * 0.35
  const depth = 0.12 + w * 0.06
  return {
    background: `linear-gradient(180deg, var(--key-bg) 0%, var(--key-bg-dark) 100%)`,
    // 用连续函数替代"阈值切换"，避免出现"没到阈值就看不出变化"的感觉。
    boxShadow: `inset 0 1px 0 rgba(255,255,255,${highlight}), inset 0 -1px 2px rgba(0,0,0,${depth})`,
  }
}

const getLabelStyle = (code) => {
  const w = getWear(code)
  return {
    opacity: 1 - w * 0.85,
    filter: `blur(${w * 1.8}px)`,
  }
}
</script>

<style scoped>
/* 头像 */
.avatar-box {
  @apply w-8 h-8 rounded-lg border border-[#00000010] flex items-center justify-center flex-shrink-0;
}

/* 气泡 - 左侧 */
.bubble-left {
  @apply relative max-w-[85%] bg-white shadow-sm rounded-xl px-3 py-2;
}
.bubble-left::before {
  content: '';
  position: absolute;
  left: -6px;
  bottom: 8px;
  width: 0;
  height: 0;
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
  border-right: 6px solid #fff;
  filter: drop-shadow(-1px 0 0 rgba(0,0,0,0.05));
}

/* 气泡 - 右侧 */
.bubble-right {
  @apply relative max-w-[85%] bg-[#95EC69] shadow-sm rounded-xl px-3 py-2;
}
.bubble-right::after {
  content: '';
  position: absolute;
  right: -6px;
  bottom: 8px;
  width: 0;
  height: 0;
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
  border-left: 6px solid #95EC69;
  filter: drop-shadow(1px 0 0 rgba(0,0,0,0.05));
}

/* 键盘外框 */
.keyboard-outer {
  @apply mt-3 rounded-2xl p-1;
  background: linear-gradient(145deg, #ffffff, #e8e8e8);
  border: 1px solid rgba(0,0,0,0.06);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}

.keyboard-inner {
  @apply rounded-xl p-3;
  background: linear-gradient(180deg, #fbfbfb, #f0f0f0);
  border: 1px solid rgba(0,0,0,0.06);
}

.keyboard-header {
  @apply flex items-center justify-between mb-2 px-1;
}

.keyboard-dots {
  @apply flex items-center gap-1.5;
}
.dot {
  @apply w-2 h-2 rounded-full;
}
.dot-red { background: #ff5f57; }
.dot-yellow { background: #febc2e; }
.dot-green { background: #28c840; }

.keyboard-stats {
  @apply text-[10px] text-[#00000066] tracking-wider;
  font-family: ui-monospace, monospace;
}

.keyboard-body {
  @apply rounded-lg p-2;
  background: #f4f4f5;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.12);
}

.kb-row {
  @apply flex justify-center gap-[3px] mb-[3px];
}
.kb-row:last-child {
  @apply mb-0;
}

/* 键帽 */
.kb-key {
  --unit: 22px;
  height: 26px;
  width: var(--unit);
  position: relative;
}
@media (min-width: 640px) {
  .kb-key {
    --unit: 28px;
    height: 32px;
  }
}

/* 宽度变体 */
.kb-w-1 { width: var(--unit); }
.kb-w-1\.25 { width: calc(var(--unit) * 1.25 + 3px * 0.25); }
.kb-w-1\.5 { width: calc(var(--unit) * 1.5 + 3px * 0.5); }
.kb-w-1\.75 { width: calc(var(--unit) * 1.75 + 3px * 0.75); }
.kb-w-2 { width: calc(var(--unit) * 2 + 3px); }
.kb-w-2\.25 { width: calc(var(--unit) * 2.25 + 3px * 1.25); }
.kb-w-2\.75 { width: calc(var(--unit) * 2.75 + 3px * 1.75); }
.kb-w-6\.25 { width: calc(var(--unit) * 6.25 + 3px * 5.25); }

.kb-key::before {
  content: '';
  position: absolute;
  inset: 0;
  top: 2px;
  background: #d4d4d8;
  border-radius: 4px;
}

.kb-key-top {
  position: absolute;
  inset: 0;
  bottom: 2px;
  border-radius: 4px;
  border: 1px solid var(--key-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.kb-sub {
  font-size: 7px;
  line-height: 1;
  color: #666;
  margin-bottom: 1px;
}
@media (min-width: 640px) {
  .kb-sub {
    font-size: 8px;
  }
}

.kb-label {
  font-size: 10px;
  font-weight: 500;
  color: #262626;
  line-height: 1;
  text-shadow: 0 1px 0 rgba(255,255,255,0.6);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
}
@media (min-width: 640px) {
  .kb-label {
    font-size: 11px;
  }
}

.kb-label-sm {
  font-size: 7px !important;
  font-weight: 400;
}
@media (min-width: 640px) {
  .kb-label-sm {
    font-size: 8px !important;
  }
}

.kb-space-bar {
  width: 50%;
  height: 3px;
  background: rgba(0,0,0,0.12);
  border-radius: 2px;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.18);
}

.keyboard-brand {
  @apply mt-2 text-center text-[8px] text-[#00000025] tracking-[0.15em] uppercase;
}
</style>
