<template>
  <div class="w-full">
    <!-- 聊天气泡区域 -->
    <div class="rounded-2xl border border-[#00000010] bg-[#F5F5F5] p-3 sm:p-4">
      <div class="flex flex-col gap-3">
        <!-- Received (left) -->
        <div class="flex items-start gap-2">
          <div class="avatar-box bg-white">
            <svg viewBox="0 0 24 24" class="w-4 h-4" fill="none" stroke="#07C160" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M8 3h10a2 2 0 0 1 2 2v14H6V5a2 2 0 0 1 2-2z" />
              <path d="M6 7H4a2 2 0 0 0-2 2v10h4" />
            </svg>
          </div>
          <div class="px-3 py-2 text-sm max-w-[85%] relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-white text-gray-800 bubble-tail-l">
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
        <div class="flex items-start gap-2 justify-end">
          <div class="px-3 py-2 text-sm max-w-[85%] relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-[#95EC69] text-black bubble-tail-r">
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
          <div class="keyboard-hint">键帽磨损程度反映你的打字频率</div>
          <div class="keyboard-stats">{{ formatInt(totalKeyHits) }} 次敲击</div>
        </div>

        <!-- 键盘主体 -->
        <div class="keyboard-body">
          <div v-for="(row, ri) in keyboardRows" :key="ri" class="kb-row">
            <div
              v-for="key in row"
              :key="key.code + key.label"
              class="kb-key"
              :class="[`kb-w-${key.w || 1}`, { 'kb-space': key.isSpace, 'kb-func': key.isFunc }, getKeyClasses(key.code)]"
              :style="getKeyStyle(key.code)"
            >
              <div class="kb-key-top" :style="getKeyTopStyle(key.code)">
                <span v-if="key.sub" class="kb-sub" :style="getLabelStyle(key.code)">{{ key.sub }}</span>
                <span v-if="key.label" class="kb-label" :class="{ 'kb-label-sm': key.isFunc }" :style="getLabelStyle(key.code)">{{ key.label }}</span>
                <div v-if="key.isSpace" class="kb-space-bar"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部品牌 -->
        <div class="keyboard-brand">微信机械键盘</div>
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

// ========== 10级磨损系统 ==========

// 磨损等级阈值
const LEVEL_THRESHOLDS = [0, 0.10, 0.20, 0.35, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]

// 获取磨损等级 (0-10)
const getWearLevel = (wear) => {
  if (wear === 0) return 0
  if (wear >= 1) return 10
  for (let i = 1; i < LEVEL_THRESHOLDS.length; i++) {
    if (wear <= LEVEL_THRESHOLDS[i]) return i
  }
  return 10
}

// 获取当前等级内的进度 (0-1)，用于等级内平滑过渡
const getWearProgress = (wear) => {
  const level = getWearLevel(wear)
  if (level === 0 || level === 10) return 0
  const start = LEVEL_THRESHOLDS[level - 1]
  const end = LEVEL_THRESHOLDS[level]
  return (wear - start) / (end - start)
}

// 根据键码确定缺角/破碎方向 (用于 level 8-9)
const getBrokenCorner = (code) => {
  const hash = code.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)
  return ['tl', 'tr', 'bl', 'br'][hash % 4]
}

// 获取键的CSS类名
const getKeyClasses = (code) => {
  const level = getWearLevel(getWear(code))
  const classes = [`kb-level-${level}`]
  if (level === 8) classes.push(`kb-broken-${getBrokenCorner(code)}`)
  if (level === 9) classes.push(`kb-shattered-${getBrokenCorner(code)}`)
  return classes.join(' ')
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

// 键帽样式 - 基于10级系统
const getKeyStyle = (code) => {
  const w = getWear(code)
  const level = getWearLevel(w)
  const progress = getWearProgress(w)

  // 等级对应的基础亮度和饱和度
  const levelParams = [
    { l: 94, s: 8 },   // 0: 全新
    { l: 92, s: 12 },  // 1: 指纹油渍
    { l: 89, s: 16 },  // 2: 涂层初磨
    { l: 85, s: 20 },  // 3: 涂层磨损
    { l: 80, s: 24 },  // 4: 涂层剥落
    { l: 76, s: 26 },  // 5: 表面凹陷
    { l: 72, s: 28 },  // 6: 细微裂纹
    { l: 68, s: 30 },  // 7: 网状龟裂
    { l: 64, s: 32 },  // 8: 缺角碎裂
    { l: 60, s: 34 },  // 9: 严重破损
    { l: 45, s: 10 },  // 10: 完全报废（轴体底座）
  ]

  const current = levelParams[level]
  const next = levelParams[Math.min(level + 1, 10)]

  // 等级内平滑插值
  const baseL = current.l + (next.l - current.l) * progress
  const sat = current.s + (next.s - current.s) * progress

  return {
    '--key-bg': `hsl(40, ${sat}%, ${baseL}%)`,
    '--key-bg-dark': `hsl(40, ${sat}%, ${baseL - 6}%)`,
    '--key-border': `hsl(40, ${Math.max(0, sat - 2)}%, ${baseL - 18}%)`,
    '--wear-level': level,
    '--wear-progress': progress,
  }
}

const getKeyTopStyle = (code) => {
  const w = getWear(code)
  const level = getWearLevel(w)
  const progress = getWearProgress(w)

  // 高光和深度随等级变化
  const highlightLevels = [0.55, 0.48, 0.40, 0.32, 0.24, 0.18, 0.12, 0.08, 0.05, 0.02, 0]
  const depthLevels = [0.12, 0.14, 0.16, 0.18, 0.20, 0.24, 0.28, 0.32, 0.36, 0.40, 0.45]

  const highlight = highlightLevels[level] + (highlightLevels[Math.min(level + 1, 10)] - highlightLevels[level]) * progress
  const depth = depthLevels[level] + (depthLevels[Math.min(level + 1, 10)] - depthLevels[level]) * progress

  return {
    background: `linear-gradient(180deg, var(--key-bg) 0%, var(--key-bg-dark) 100%)`,
    boxShadow: `inset 0 1px 0 rgba(255,255,255,${highlight}), inset 0 -1px 2px rgba(0,0,0,${depth})`,
  }
}

const getLabelStyle = (code) => {
  const w = getWear(code)
  const level = getWearLevel(w)
  const progress = getWearProgress(w)

  // 标签透明度和模糊度随等级变化
  const opacityLevels = [1, 0.95, 0.88, 0.75, 0.55, 0.35, 0.18, 0.08, 0.03, 0.01, 0]
  const blurLevels = [0, 0.2, 0.4, 0.7, 1.0, 1.4, 1.8, 2.2, 2.6, 3.0, 3.5]

  const opacity = opacityLevels[level] + (opacityLevels[Math.min(level + 1, 10)] - opacityLevels[level]) * progress
  const blur = blurLevels[level] + (blurLevels[Math.min(level + 1, 10)] - blurLevels[level]) * progress

  return {
    opacity: opacity,
    filter: `blur(${blur}px)`,
  }
}
</script>

<style>
/* 头像 */
.avatar-box {
  @apply w-8 h-8 rounded-lg border border-[#00000010] flex items-center justify-center flex-shrink-0;
}

/* 键盘外框 */
.keyboard-outer {
  @apply mt-3 rounded-2xl p-1;
  /* Needed for ::before/::after overlays (scanlines, speaker grill, etc.) */
  position: relative;
  isolation: isolate;
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
  @apply relative flex items-center justify-between mb-2 px-1;
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

.keyboard-hint {
  @apply absolute left-1/2 -translate-x-1/2 text-[9px] text-[#00000055];
}

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

/* ========== 10级磨损视觉效果 ========== */

/* Level 1: 指纹油渍 - 中心淡淡油光 */
.kb-level-1 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 20%;
  background: radial-gradient(ellipse at center, rgba(255,255,255,0.15) 0%, transparent 70%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 2: 涂层初磨 - 边缘变薄 */
.kb-level-2 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 50%, rgba(180,160,140,0.12) 100%);
  pointer-events: none;
  border-radius: 4px;
}

/* Level 3: 涂层磨损 - 浅色磨痕纹理 */
.kb-level-3 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 30% 40%, rgba(160,140,120,0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 70% 60%, rgba(160,140,120,0.12) 0%, transparent 45%);
  pointer-events: none;
  border-radius: 4px;
}

/* Level 4: 涂层剥落 - 斑驳露底色 */
.kb-level-4 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 25% 35%, rgba(140,120,100,0.25) 0%, transparent 40%),
    radial-gradient(ellipse at 65% 55%, rgba(140,120,100,0.20) 0%, transparent 35%),
    radial-gradient(ellipse at 50% 70%, rgba(140,120,100,0.18) 0%, transparent 30%);
  pointer-events: none;
  border-radius: 4px;
}

/* Level 5: 表面凹陷 - 中心凹陷阴影 */
.kb-level-5 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.18),
    inset 0 -1px 2px rgba(0,0,0,0.24),
    inset 0 3px 6px rgba(0,0,0,0.15) !important;
}
.kb-level-5 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 15%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.12) 0%, transparent 70%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 6: 细微裂纹 - 边缘1-2条细裂纹 */
.kb-level-6 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.12),
    inset 0 -1px 2px rgba(0,0,0,0.28),
    inset 0 3px 8px rgba(0,0,0,0.18) !important;
}
.kb-level-6 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    /* 主裂纹 - 从右上角延伸 */
    linear-gradient(135deg,
      transparent 0%, transparent 72%,
      rgba(80,60,40,0.35) 72%, rgba(80,60,40,0.35) 73%,
      transparent 73%, transparent 100%
    ),
    /* 细小分支 */
    linear-gradient(160deg,
      transparent 0%, transparent 78%,
      rgba(80,60,40,0.25) 78%, rgba(80,60,40,0.25) 79%,
      transparent 79%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
.kb-level-6 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 10%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.15) 0%, transparent 70%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 7: 网状龟裂 - 多条裂纹交叉 */
.kb-level-7 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.08),
    inset 0 -1px 2px rgba(0,0,0,0.32),
    inset 0 4px 10px rgba(0,0,0,0.22) !important;
}
.kb-level-7 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    /* 主裂纹 - 对角线 */
    linear-gradient(135deg,
      transparent 0%, transparent 25%,
      rgba(70,50,30,0.4) 25%, rgba(70,50,30,0.4) 26%,
      transparent 26%, transparent 65%,
      rgba(70,50,30,0.35) 65%, rgba(70,50,30,0.35) 66%,
      transparent 66%, transparent 100%
    ),
    /* 交叉裂纹 */
    linear-gradient(45deg,
      transparent 0%, transparent 35%,
      rgba(70,50,30,0.3) 35%, rgba(70,50,30,0.3) 36%,
      transparent 36%, transparent 70%,
      rgba(70,50,30,0.25) 70%, rgba(70,50,30,0.25) 71%,
      transparent 71%, transparent 100%
    ),
    /* 横向裂纹 */
    linear-gradient(95deg,
      transparent 0%, transparent 40%,
      rgba(70,50,30,0.28) 40%, rgba(70,50,30,0.28) 41%,
      transparent 41%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
.kb-level-7 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 5%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.18) 0%, transparent 65%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 8: 缺角碎裂 - clip-path切割缺角 */
.kb-level-8 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.05),
    inset 0 -1px 2px rgba(0,0,0,0.36),
    inset 0 4px 12px rgba(0,0,0,0.25) !important;
}
.kb-level-8 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg,
      transparent 0%, transparent 20%,
      rgba(60,40,20,0.45) 20%, rgba(60,40,20,0.45) 21%,
      transparent 21%, transparent 55%,
      rgba(60,40,20,0.4) 55%, rgba(60,40,20,0.4) 56%,
      transparent 56%, transparent 100%
    ),
    linear-gradient(45deg,
      transparent 0%, transparent 30%,
      rgba(60,40,20,0.35) 30%, rgba(60,40,20,0.35) 31%,
      transparent 31%, transparent 65%,
      rgba(60,40,20,0.3) 65%, rgba(60,40,20,0.3) 66%,
      transparent 66%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
/* 缺角方向变体 */
.kb-broken-tl .kb-key-top {
  clip-path: polygon(18% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 22%);
}
.kb-broken-tr .kb-key-top {
  clip-path: polygon(0% 0%, 82% 0%, 100% 20%, 100% 100%, 0% 100%);
}
.kb-broken-bl .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 100%, 20% 100%, 0% 78%);
}
.kb-broken-br .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 80%, 82% 100%, 0% 100%);
}

/* Level 9: 严重破损 - 大面积不规则破碎 */
.kb-level-9 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.02),
    inset 0 -1px 2px rgba(0,0,0,0.40),
    inset 0 5px 14px rgba(0,0,0,0.30) !important;
}
.kb-level-9 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(125deg,
      transparent 0%, transparent 15%,
      rgba(50,30,10,0.5) 15%, rgba(50,30,10,0.5) 16%,
      transparent 16%, transparent 45%,
      rgba(50,30,10,0.45) 45%, rgba(50,30,10,0.45) 46%,
      transparent 46%, transparent 100%
    ),
    linear-gradient(55deg,
      transparent 0%, transparent 25%,
      rgba(50,30,10,0.4) 25%, rgba(50,30,10,0.4) 26%,
      transparent 26%, transparent 60%,
      rgba(50,30,10,0.35) 60%, rgba(50,30,10,0.35) 61%,
      transparent 61%, transparent 100%
    ),
    linear-gradient(170deg,
      transparent 0%, transparent 50%,
      rgba(50,30,10,0.38) 50%, rgba(50,30,10,0.38) 51%,
      transparent 51%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
/* 严重破碎方向变体 */
.kb-shattered-tl .kb-key-top {
  clip-path: polygon(28% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 35%, 12% 18%);
}
.kb-shattered-tr .kb-key-top {
  clip-path: polygon(0% 0%, 72% 0%, 88% 15%, 100% 32%, 100% 100%, 0% 100%);
}
.kb-shattered-bl .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 100%, 30% 100%, 10% 82%, 0% 65%);
}
.kb-shattered-br .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 68%, 90% 85%, 70% 100%, 0% 100%);
}

/* Level 10: 完全报废 - 键帽消失，显示轴体 */
.kb-level-10 .kb-key-top {
  opacity: 0 !important;
}
.kb-level-10::before {
  /* 轴座底座 - 深灰色凹槽 */
  background: linear-gradient(180deg, #3a3a3c 0%, #2c2c2e 100%) !important;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
}
.kb-level-10::after {
  content: '';
  position: absolute;
  /* 十字轴心居中 */
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 40%;
  height: 40%;
  /* Cherry MX 风格十字轴 */
  background:
    /* 横向 */
    linear-gradient(90deg,
      transparent 0%, transparent 30%,
      #606065 30%, #707075 35%, #606065 40%,
      #555558 45%, #555558 55%,
      #606065 60%, #707075 65%, #606065 70%,
      transparent 70%, transparent 100%
    ),
    /* 纵向 */
    linear-gradient(0deg,
      transparent 0%, transparent 30%,
      #606065 30%, #707075 35%, #606065 40%,
      #555558 45%, #555558 55%,
      #606065 60%, #707075 65%, #606065 70%,
      transparent 70%, transparent 100%
    );
  border-radius: 1px;
  box-shadow:
    0 1px 2px rgba(0,0,0,0.4),
    inset 0 0 1px rgba(255,255,255,0.1);
  z-index: 1;
}

/* 高磨损等级性能优化 */
.kb-level-8 .kb-key-top,
.kb-level-9 .kb-key-top {
  will-change: clip-path;
}

.keyboard-brand {
  @apply mt-2 text-center text-[8px] text-[#00000025] tracking-[0.15em] uppercase;
}

</style>
