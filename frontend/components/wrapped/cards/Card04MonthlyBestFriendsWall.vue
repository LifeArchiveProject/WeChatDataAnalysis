<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="card.narrative || ''" :variant="variant" :wide="true">
    <div class="w-full">
      <div class="flex flex-wrap justify-center gap-x-3 gap-y-4 px-3 py-2">
        <article
          v-for="item in months"
          :key="`month-${item.month}`"
          class="relative flex-shrink-0 monthly-polaroid"
          :class="item.winner ? '' : 'monthly-polaroid--empty'"
          :style="monthCardStyle(item.month)"
        >
          <!-- 有获胜者 -->
          <template v-if="item.winner">
            <div class="flex items-start gap-1.5 pt-0.5 px-0.5">
              <!-- 头像 -->
              <div class="polaroid-photo flex-shrink-0">
                <img
                  v-if="winnerAvatar(item) && avatarOk[item.winner.username] !== false"
                  :src="winnerAvatar(item)"
                  class="w-full h-full object-cover"
                  alt="avatar"
                  @error="avatarOk[item.winner.username] = false"
                />
                <span v-else class="wrapped-number text-xl select-none" style="color:var(--accent)">
                  {{ avatarFallback(item.winner.displayName) }}
                </span>
              </div>
              <!-- 右列：姓名 / 月份 / 综合分 / 4 维度 -->
              <div class="flex-1 min-w-0 pt-0.5 flex flex-col justify-between" style="height:70px">
                <div>
                  <div class="flex items-center justify-between gap-1 min-w-0">
                    <div class="wrapped-body text-[10px] text-[#000000cc] truncate flex-1 leading-tight" :title="item.winner.displayName">
                      {{ item.winner.displayName }}
                    </div>
                    <!-- 月份徽章 -->
                    <div class="month-badge wrapped-number text-[8px] font-bold flex-shrink-0" :style="{ color: 'var(--accent)', borderColor: 'var(--accent)' }">
                      {{ item.month }}月
                    </div>
                  </div>
                  <div class="mt-0.5 wrapped-number text-[9px] font-semibold" :style="{ color: 'var(--accent)' }">
                    综合分 {{ formatScore(item.winner.score100) }}
                  </div>
                </div>
                <!-- 4 维度 2×2 -->
                <div class="grid grid-cols-2 gap-x-2 gap-y-1">
                  <div v-for="metric in metricRows(item)" :key="metric.key" class="min-w-0">
                    <div class="flex items-center justify-between wrapped-label text-[8px] text-[#00000066]">
                      <span class="truncate">{{ metric.label }}</span>
                      <span v-if="metric.pct !== 100" class="wrapped-number flex-shrink-0 ml-0.5">{{ metric.pct }}</span>
                    </div>
                    <div class="mt-0.5 h-1 rounded-full bg-[#0000000D] overflow-hidden">
                      <div class="h-full rounded-full" :style="{ width: `${metric.pct}%`, backgroundColor: 'var(--accent)', opacity: '0.75' }" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <!-- 统计行 -->
            <div class="polaroid-caption">
              <div class="wrapped-body text-[9px] text-[#00000055] leading-snug">
                共 <span class="wrapped-number text-[#000000aa]">{{ formatInt(item?.raw?.totalMessages) }}</span> 条 ·
                互动 <span class="wrapped-number text-[#000000aa]">{{ formatInt(item?.raw?.interaction) }}</span> 次 ·
                活跃 <span class="wrapped-number text-[#000000aa]">{{ formatInt(item?.raw?.activeDays) }}</span> 天
              </div>
            </div>
          </template>

          <!-- 无数据：空白拍立得 -->
          <template v-else>
            <div class="polaroid-photo-empty flex-shrink-0 mx-auto">
              <span class="text-lg select-none" style="color:var(--accent);opacity:0.25">〜</span>
            </div>
            <div class="polaroid-caption">
              <div class="flex items-center justify-between gap-1">
                <div class="wrapped-label text-[9px] text-[#00000044]">本月静悄悄</div>
                <div class="month-badge wrapped-number text-[8px]" :style="{ color: 'var(--accent)', borderColor: 'var(--accent)', opacity: '0.5' }">
                  {{ item.month }}月
                </div>
              </div>
            </div>
          </template>
        </article>
      </div>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))
const formatScore = (n) => {
  const x = Number(n)
  if (!Number.isFinite(x)) return '0.0'
  return x.toFixed(1)
}
const clampPct = (n) => Math.max(0, Math.min(100, Math.round(Number(n || 0) * 100)))

const mediaBase = process.client ? 'http://localhost:8000' : ''
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${mediaBase}/api/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  return `${mediaBase}${raw.startsWith('/') ? '' : '/'}${raw}`
}

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  return s ? s[0] : '?'
}

const months = computed(() => {
  const raw = Array.isArray(props.card?.data?.months) ? props.card.data.months : []
  const byMonth = new Map()
  for (const x of raw) {
    const m = Number(x?.month)
    if (Number.isFinite(m) && m >= 1 && m <= 12) byMonth.set(m, x)
  }
  const out = []
  for (let m = 1; m <= 12; m += 1) {
    out.push(byMonth.get(m) || { month: m, winner: null, metrics: null, raw: null })
  }
  return out
})

const avatarOk = reactive({})
watch(
  months,
  () => { for (const key of Object.keys(avatarOk)) delete avatarOk[key] },
  { deep: true, immediate: true }
)

const winnerAvatar = (item) => resolveMediaUrl(item?.winner?.avatarUrl)

const metricRows = (item) => {
  const m = item?.metrics || {}
  return [
    { key: 'interaction', label: '互动', pct: clampPct(m.interactionScore) },
    { key: 'speed',       label: '速度', pct: clampPct(m.speedScore) },
    { key: 'continuity',  label: '连续', pct: clampPct(m.continuityScore) },
    { key: 'coverage',    label: '覆盖', pct: clampPct(m.coverageScore) }
  ]
}

// 12 个月各自独立 accent 色，驱动胶带、徽章、进度条
const accents = [
  '#C96A4E', // 1月 砖红
  '#5B82C4', // 2月 矢车菊蓝
  '#4EA87A', // 3月 薄荷绿
  '#C4953A', // 4月 琥珀金
  '#8B65B5', // 5月 薰衣草紫
  '#3A9FB5', // 6月 孔雀蓝
  '#C45F7A', // 7月 玫瑰粉
  '#3E7FC4', // 8月 天蓝
  '#6AA86A', // 9月 苔绿
  '#C47A3A', // 10月 暖橙
  '#9B6BAF', // 11月 丁香紫
  '#4A8EB5', // 12月 冬湖蓝
]

const monthCardStyle = (month) => {
  const idx = Math.max(0, Math.min(11, Number(month || 1) - 1))
  const rotations = [-9, 5, -4, 11, -2, 8, -7, 3, -10, 6, -3, 9]
  const yOffsets  = [5, -4, 6, -5, 3, -7, 3, -4, 7, -3, 5, -4]
  const widths    = [172, 165, 178, 168, 175, 163, 172, 167, 165, 178, 165, 170]
  return {
    transform: `rotate(${rotations[idx]}deg) translateY(${yOffsets[idx]}px)`,
    width: `${widths[idx]}px`,
    '--delay':  `${idx * 0.07}s`,
    '--accent': accents[idx],
  }
}
</script>

<style scoped>
/* ── 拍立得卡片基础 ── */
.monthly-polaroid {
  background: #FFFDF7;  /* 暖奶油底色 */
  padding: 4px 4px 0;
  border-radius: 3px;
  box-shadow:
    0 1px 1px rgba(0,0,0,0.06),
    0 4px 12px rgba(0,0,0,0.10),
    0 12px 28px rgba(0,0,0,0.08);
  animation: cardAppear 0.4s ease-out both;
  animation-delay: var(--delay, 0s);
}

@keyframes cardAppear {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* 空月卡片底色更浅 */
.monthly-polaroid--empty {
  background: #F7F5F0;
}

/* ── 彩色胶带条 ── */
.monthly-polaroid::before {
  content: '';
  position: absolute;
  top: -7px;
  left: 50%;
  width: 38px;
  height: 14px;
  transform: translateX(-50%) rotate(-1deg);
  border-radius: 2px;
  background: var(--accent, #c8a060);
  opacity: 0.55;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12);
  z-index: 1;
}

/* ── 头像区域 ── */
.polaroid-photo {
  width: 70px;
  height: 70px;
  background: #e0ddd8;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;   /* 照片圆角，更自然 */
}

/* ── 空月占位图 ── */
.polaroid-photo-empty {
  width: 70px;
  height: 44px;
  background: #E8E5DF;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 4px auto 0;
}

/* ── 月份小徽章 ── */
.month-badge {
  border: 1px solid;
  border-radius: 3px;
  padding: 0 3px;
  line-height: 1.6;
}

/* ── 底部信息条 ── */
.polaroid-caption {
  padding: 5px 5px 6px;
  border-top: 1px solid rgba(0,0,0,0.04);  /* 细分隔线，区分照片与文字区 */
  margin-top: 4px;
}
</style>
