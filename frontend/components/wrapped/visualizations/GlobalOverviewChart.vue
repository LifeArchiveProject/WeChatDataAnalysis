<template>
  <div class="w-full">
    <div class="overview-card">
      <div class="flex items-center justify-between gap-4">
        <div class="wrapped-label text-xs text-[#00000066]">年度聊天画像</div>
        <div class="wrapped-body text-xs text-[#00000066]">Radar</div>
      </div>

      <div class="mt-4 grid gap-6 sm:grid-cols-[280px_1fr] items-center">
        <div class="w-full max-w-[320px] mx-auto">
          <svg viewBox="0 0 220 220" class="w-full h-auto select-none">
            <!-- Grid -->
            <g>
              <polygon
                v-for="i in rings"
                :key="i"
                :points="gridPolygonPoints(i / rings)"
                fill="none"
                class="overview-grid-line"
                stroke-width="1"
              />
              <line
                v-for="(p, idx) in axisPoints"
                :key="idx"
                :x1="cx"
                :y1="cy"
                :x2="p.x"
                :y2="p.y"
                class="overview-axis-line"
                stroke-width="1"
              />
            </g>

            <!-- Data polygon -->
            <polygon
              :points="dataPolygonPoints"
              class="overview-data-polygon"
              stroke-width="2"
            />

            <!-- Data nodes + tooltips -->
            <g>
              <circle
                v-for="(p, idx) in dataPoints"
                :key="idx"
                :cx="p.x"
                :cy="p.y"
                r="4"
                class="overview-data-node"
                stroke-width="1.5"
              >
                <title>{{ p.title }}</title>
              </circle>
            </g>

            <!-- Labels -->
            <g>
              <text
                v-for="(l, idx) in labels"
                :key="idx"
                :x="l.x"
                :y="l.y"
                :text-anchor="l.anchor"
                dominant-baseline="middle"
                font-size="11"
                class="overview-label"
              >
                {{ l.label }}
              </text>
            </g>
          </svg>
        </div>

        <div class="grid gap-3">
          <div
            v-for="m in metrics"
            :key="m.key"
            class="flex items-center justify-between gap-4"
          >
            <div class="wrapped-body text-sm text-[#00000099]">{{ m.name }}</div>
            <div class="flex items-center gap-3 min-w-[160px]">
              <div class="overview-progress-bg">
                <div class="overview-progress-fill" :style="{ width: Math.round(m.norm * 100) + '%' }" />
              </div>
              <div
                :class="[
                  'wrapped-number text-sm w-[74px] text-right',
                  m.display === '—' ? 'text-[#00000055]' : 'text-[#07C160] font-semibold'
                ]"
              >
                {{ m.display }}
              </div>
            </div>
          </div>

          <!-- Note removed per UI requirement (keep layout compact). -->
        </div>
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

const formatFloat = (n, digits = 1) => {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  return v.toFixed(digits)
}

const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0))
const logNorm = (v, maxLog) => {
  const n = Number(v) || 0
  const ml = Number(maxLog) || 1
  if (n <= 0) return 0
  return clamp01(Math.log10(1 + n) / ml)
}

const totalMessages = computed(() => Number(props.data?.totalMessages || 0))
const activeDays = computed(() => Number(props.data?.activeDays || 0))
const messagesPerDay = computed(() => Number(props.data?.messagesPerDay || 0))

const topContactMessages = computed(() => Number(props.data?.topContact?.messages || 0))
const topGroupMessages = computed(() => Number(props.data?.topGroup?.messages || 0))

const topKindPct = computed(() => {
  const ratio = Number(props.data?.topKind?.ratio || 0)
  if (!Number.isFinite(ratio) || ratio <= 0) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
})

const metrics = computed(() => [
  {
    key: 'totalMessages',
    name: '发送消息',
    label: '发送',
    display: `${formatInt(totalMessages.value)} 条`,
    norm: logNorm(totalMessages.value, 6)
  },
  {
    key: 'activeDays',
    name: '发消息天数',
    label: '天数',
    display: `${formatInt(activeDays.value)}/365`,
    norm: clamp01(activeDays.value / 365)
  },
  {
    key: 'messagesPerDay',
    name: '日均发送',
    label: '日均',
    display: `${formatFloat(messagesPerDay.value, 1)} 条`,
    norm: logNorm(messagesPerDay.value, 3)
  },
  {
    key: 'topContactMessages',
    name: '发得最多的人',
    label: '常发',
    display: topContactMessages.value > 0 ? `${formatInt(topContactMessages.value)} 条` : '—',
    norm: logNorm(topContactMessages.value, 5)
  },
  {
    key: 'topGroupMessages',
    name: '发言最多的群',
    label: '发言',
    display: topGroupMessages.value > 0 ? `${formatInt(topGroupMessages.value)} 条` : '—',
    norm: logNorm(topGroupMessages.value, 5)
  },
  {
    key: 'topKindPct',
    name: '最常用表达',
    label: '表达',
    display: topKindPct.value > 0 ? `${topKindPct.value}%` : '—',
    norm: clamp01(topKindPct.value / 100)
  }
])

const rings = 5
const cx = 110
const cy = 110
const radius = 74

const axisPoints = computed(() => {
  const n = metrics.value.length
  return metrics.value.map((_, idx) => {
    const a = (Math.PI * 2 * idx) / n - Math.PI / 2
    return { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a), a }
  })
})

const gridPolygonPoints = (t) => {
  const pts = axisPoints.value.map((p) => `${cx + (p.x - cx) * t},${cy + (p.y - cy) * t}`)
  return pts.join(' ')
}

const dataPoints = computed(() => {
  const pts = []
  const n = metrics.value.length
  for (let i = 0; i < n; i++) {
    const m = metrics.value[i]
    const a = (Math.PI * 2 * i) / n - Math.PI / 2
    const r = radius * clamp01(m.norm)
    const x = cx + r * Math.cos(a)
    const y = cy + r * Math.sin(a)
    pts.push({ x, y, title: `${m.name}：${m.display}` })
  }
  return pts
})

const dataPolygonPoints = computed(() => dataPoints.value.map((p) => `${p.x},${p.y}`).join(' '))

const labels = computed(() => {
  const out = []
  const n = metrics.value.length
  for (let i = 0; i < n; i++) {
    const m = metrics.value[i]
    const a = (Math.PI * 2 * i) / n - Math.PI / 2
    const r = radius + 18
    const x = cx + r * Math.cos(a)
    const y = cy + r * Math.sin(a)
    const cos = Math.cos(a)
    let anchor = 'middle'
    if (cos > 0.35) anchor = 'start'
    else if (cos < -0.35) anchor = 'end'
    out.push({ x, y, label: m.label, anchor })
  }
  return out
})
</script>

<style>
/* ========== 基础样式 ========== */
.overview-card {
  @apply rounded-2xl border border-[#00000010] bg-white/60 backdrop-blur p-4 sm:p-6;
}

.overview-grid-line {
  stroke: rgba(0, 0, 0, 0.08);
}

.overview-axis-line {
  stroke: rgba(0, 0, 0, 0.10);
}

.overview-data-polygon {
  fill: rgba(7, 193, 96, 0.18);
  stroke: rgba(7, 193, 96, 0.85);
}

.overview-data-node {
  fill: #07C160;
  stroke: white;
}

.overview-label {
  fill: rgba(0, 0, 0, 0.70);
}

.overview-progress-bg {
  @apply h-2 flex-1 rounded-full bg-[#0000000d] overflow-hidden;
}

.overview-progress-fill {
  @apply h-full rounded-full bg-[#07C160];
}

/* ========== Game Boy 主题 ========== */

.wrapped-theme-gameboy .overview-card {
  background: #8bac0f !important;
  border: 4px solid #306230 !important;
  border-radius: 0 !important;
  backdrop-filter: none;
  box-shadow:
    inset -2px -2px 0 0 #306230,
    inset 2px 2px 0 0 #c5d870;
}

.wrapped-theme-gameboy .overview-progress-bg {
  background: #306230 !important;
  border-radius: 0 !important;
}

.wrapped-theme-gameboy .overview-progress-fill {
  background: #0f380f !important;
  border-radius: 0 !important;
}

.wrapped-theme-gameboy .overview-grid-line {
  stroke: #306230;
  stroke-opacity: 0.4;
}

.wrapped-theme-gameboy .overview-axis-line {
  stroke: #306230;
  stroke-opacity: 0.5;
}

.wrapped-theme-gameboy .overview-data-polygon {
  fill: rgba(15, 56, 15, 0.3);
  stroke: #0f380f;
}

.wrapped-theme-gameboy .overview-data-node {
  fill: #0f380f;
  stroke: #9bbc0f;
}

.wrapped-theme-gameboy .overview-label {
  fill: #0f380f;
}

.wrapped-theme-gameboy .wrapped-label,
.wrapped-theme-gameboy .wrapped-body {
  color: #306230 !important;
}

.wrapped-theme-gameboy .wrapped-number {
  color: #0f380f !important;
}

/* ========== DOS 主题 ========== */

.wrapped-theme-dos .overview-card {
  background: #0a0a0a !important;
  border: 1px solid #33ff33 !important;
  box-shadow: 0 0 10px rgba(51, 255, 51, 0.2);
  backdrop-filter: none;
}

.wrapped-theme-dos .overview-grid-line {
  stroke: #33ff33;
  stroke-opacity: 0.2;
}

.wrapped-theme-dos .overview-axis-line {
  stroke: #33ff33;
  stroke-opacity: 0.3;
}

.wrapped-theme-dos .overview-data-polygon {
  fill: rgba(51, 255, 51, 0.15);
  stroke: #33ff33;
}

.wrapped-theme-dos .overview-data-node {
  fill: #33ff33;
  stroke: #0a0a0a;
}

.wrapped-theme-dos .overview-label {
  fill: #33ff33;
}

.wrapped-theme-dos .overview-progress-bg {
  background: #1a1a1a !important;
  border: 1px solid #33ff33;
}

.wrapped-theme-dos .overview-progress-fill {
  background: #33ff33 !important;
  box-shadow: 0 0 5px #33ff33;
}

.wrapped-theme-dos .wrapped-label,
.wrapped-theme-dos .wrapped-body {
  color: #22aa22 !important;
  text-shadow: 0 0 3px #22aa22;
}

.wrapped-theme-dos .wrapped-number {
  color: #33ff33 !important;
  text-shadow: 0 0 5px #33ff33;
}

/* ========== VHS 主题 ========== */

.wrapped-theme-vhs .overview-card {
  background: #16213e !important;
  border: 1px solid #0f3460 !important;
  backdrop-filter: none;
}

.wrapped-theme-vhs .overview-grid-line {
  stroke: #0f3460;
  stroke-opacity: 0.6;
}

.wrapped-theme-vhs .overview-axis-line {
  stroke: #0f3460;
  stroke-opacity: 0.8;
}

.wrapped-theme-vhs .overview-data-polygon {
  fill: rgba(233, 69, 96, 0.2);
  stroke: #e94560;
}

.wrapped-theme-vhs .overview-data-node {
  fill: #e94560;
  stroke: #16213e;
}

.wrapped-theme-vhs .overview-label {
  fill: #a0a0a0;
}

.wrapped-theme-vhs .overview-progress-bg {
  background: #0f3460 !important;
}

.wrapped-theme-vhs .overview-progress-fill {
  background: linear-gradient(90deg, #e94560, #0f3460) !important;
}

.wrapped-theme-vhs .wrapped-label,
.wrapped-theme-vhs .wrapped-body {
  color: #a0a0a0 !important;
}

.wrapped-theme-vhs .wrapped-number {
  color: #e94560 !important;
  text-shadow:
    -1px 0 rgba(0, 255, 247, 0.5),
    1px 0 rgba(255, 0, 255, 0.5);
}
</style>
