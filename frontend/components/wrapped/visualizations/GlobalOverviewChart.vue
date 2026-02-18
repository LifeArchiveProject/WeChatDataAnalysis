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
</style>
