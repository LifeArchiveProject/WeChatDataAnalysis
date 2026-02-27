<template>
  <!-- 由于父级 section 存在高度受限 (height: 695px)，取消激进的负间距和平移，改用温和的 padding 调整内部空间 -->
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="card.narrative || ''" :variant="variant" :wide="true" class="h-full monthly-best-friends-shell-lift">
    <!-- 将 mt 设为 0 或微负，整体靠容器 flex 分布 -->
    <div class="w-full h-full p-2 sm:p-4 -mt-5 sm:-mt-6 flex items-stretch">
      <!-- 拟真木板容器 -->
      <div class="wood-board-container relative w-full h-full rounded-2xl shadow-[0_10px_25px_rgba(0,0,0,0.15)] flex flex-col">
        <!-- 背景图层：必须带上 rounded-2xl 否则纯 CSS background 会溢出直角 -->
        <div class="wood-board-bg absolute inset-0 rounded-2xl"></div>
        <!-- 边缘受光与暗角阴影，且通过 overflow-hidden 和 rounded-2xl 确保不破坏外壳 -->
        <div class="wood-board-frame absolute inset-0 pointer-events-none z-20 rounded-2xl overflow-hidden"></div>

        <!-- 滚动区域包裹拍立得 -->
        <div class="flex flex-wrap justify-center content-start gap-x-6 sm:gap-x-8 gap-y-12 sm:gap-y-14 px-4 sm:px-8 py-8 w-full h-full relative z-10 overflow-y-auto overflow-x-hidden custom-scrollbar rounded-2xl">
          <article
            v-for="(item, index) in months"
            :key="`month-${item.month}`"
            class="relative flex-shrink-0 monthly-polaroid origin-center select-none cursor-grab"
            :class="[
              item.winner ? '' : 'monthly-polaroid--empty',
              { 'is-dragging': positions[index].dragging }
            ]"
            :style="monthCardStyle(item.month, index)"
            @pointerdown="(e) => onPointerDown(e, index)"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
          >
            <!-- 有获胜者 -->
            <template v-if="item.winner">
              <div class="flex items-start gap-1.5 pt-0.5 px-0.5">
                <!-- 头像 -->
                <div class="polaroid-photo flex-shrink-0 wrapped-privacy-avatar">
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
                      <div class="wrapped-body text-[10px] text-[#000000cc] truncate flex-1 leading-tight wrapped-privacy-name" :title="item.winner.displayName">
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
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, reactive, watch, ref } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }
})

// === 拖拽交互状态 ===
let maxZ = 10;
const draggingIdx = ref(-1);
const startCoords = { x: 0, y: 0 };
const initialOffsets = { dx: 0, dy: 0 };
const positions = reactive(Array(12).fill(0).map(() => ({ dx: 0, dy: 0, z: 1, dragging: false })))

const onPointerDown = (e, index) => {
  if (e.button !== 0 && e.type.startsWith('mouse')) return;
  e.preventDefault();

  const el = e.currentTarget;
  el.setPointerCapture(e.pointerId);

  draggingIdx.value = index;
  maxZ += 1;
  positions[index].z = maxZ;
  positions[index].dragging = true;

  startCoords.x = e.clientX;
  startCoords.y = e.clientY;
  initialOffsets.dx = positions[index].dx;
  initialOffsets.dy = positions[index].dy;
}

const onPointerMove = (e) => {
  if (draggingIdx.value === -1) return;
  const idx = draggingIdx.value;
  const dx = e.clientX - startCoords.x;
  const dy = e.clientY - startCoords.y;
  positions[idx].dx = initialOffsets.dx + dx;
  positions[idx].dy = initialOffsets.dy + dy;
}

const onPointerUp = (e) => {
  if (draggingIdx.value === -1) return;
  const idx = draggingIdx.value;
  positions[idx].dragging = false;

  const el = e.currentTarget;
  if (el.hasPointerCapture(e.pointerId)) {
    el.releasePointerCapture(e.pointerId);
  }
  draggingIdx.value = -1;
}

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

const monthCardStyle = (month, vIndex) => {
  const idx = Math.max(0, Math.min(11, Number(month || 1) - 1))
  // Increase angle spread
  const rotations = [-11, 8, -6, 14, -5, 12, -9, 4, -13, 7, -4, 11]
  // Significantly adjust vertical scatter to fill whitespace across two rows
  const yOffsets  = [20, -10, 30, -20, 15, -25, 25, -15, 35, -5, 10, -30]
  // Base width scaled up
  const widths    = [198, 192, 204, 194, 201, 190, 198, 194, 192, 204, 192, 196]

  const p = positions[vIndex] || { dx: 0, dy: 0, z: 1 }
  const ty = yOffsets[idx]

  return {
    '--rotate': `${rotations[idx]}deg`,
    '--drag-x': `${p.dx}px`,
    '--drag-y': `${p.dy + ty}px`,
    '--width': `${widths[idx]}px`,
    '--delay':  `${idx * 0.08}s`,
    '--accent': accents[idx],
    'z-index': p.z > 1 ? p.z : undefined,
  }
}
</script>

<style scoped>
.monthly-best-friends-shell-lift :deep(.relative.h-full.flex.flex-col) {
  padding-top: 2rem !important;
}

/* ── 拟真浅色木板背景（纯CSS） ── */
.wood-board-bg {
  /* 基础底色：温暖且带有微小绿意的米白/浅卡其，和应用背景呼应 */
  background-color: #E8EDE4;
  background-image:
    /* 木板接缝的立体浅灰阴影 */
    repeating-linear-gradient(to right, transparent, transparent 19.5%, rgba(0,0,0,0.04) 19.8%, rgba(0,0,0,0.08) 20%, transparent 20.2%),
    /* 细微的纵向浅色木纹 */
    repeating-linear-gradient(to right, transparent, transparent 1px, rgba(0,0,0,0.01) 1px, rgba(0,0,0,0.01) 2px),
    /* 宽条纹基础色差模拟浅色木材打磨 */
    linear-gradient(90deg, #E2e8DD 0%, #ebf0e7 15%, #E2e8DD 30%, #E8EDE4 50%, #dce4d6 75%, #E2e8DD 100%);
  background-size: 100% 100%;
}

.wood-board-frame {
  /* 去掉黑重的边框，改为温和的内收高光与微弱阴影边缘 */
  box-shadow:
    inset 0 0 40px rgba(0,0,0,0.06),
    inset 0 0 100px rgba(0,0,0,0.03),
    inset 0 1px 2px rgba(255,255,255,0.8),
    inset 0 -1px 3px rgba(0,0,0,0.05);
  border: 4px solid rgba(255, 255, 255, 0.4);
  border-bottom-color: rgba(220, 230, 215, 0.6);
  border-top-color: rgba(255, 255, 255, 0.9);
  border-radius: 1rem;
}

/* 隐藏式滚动条，不破坏木板质感 */
.wood-board-container .custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.wood-board-container .custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.wood-board-container .custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
}
.wood-board-container .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.2);
}

/* ── 拍立得卡片基础 ── */
.monthly-polaroid {
  background: #FFFDF7;  /* 暖奶油底色 */
  padding: 4px 4px 0;
  border-radius: 3px;
  /* 浅色背景下适度减弱阴影，保留立体感但不过于突兀 */
  box-shadow:
    0 2px 6px rgba(0,0,0,0.08),
    0 8px 16px rgba(0,0,0,0.06),
    0 16px 32px rgba(0,0,0,0.04);
  width: var(--width, 170px);
  transform: translate(var(--drag-x, 0px), var(--drag-y, 0px)) rotate(var(--rotate, 0deg));
  transform-origin: center center;
  position: relative;
  z-index: 1;
  transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.4s ease, z-index 0s 0.4s;
  animation: cardAppear 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
  animation-delay: var(--delay, 0s);
  touch-action: none;
}

.monthly-polaroid:hover:not(.is-dragging) {
  transform: translate(var(--drag-x, 0px), var(--drag-y, 0px)) scale(1.15) rotate(0deg) !important;
  z-index: 9999 !important;
  box-shadow:
    0 20px 40px rgba(0,0,0,0.12),
    0 8px 16px rgba(0,0,0,0.08);
  cursor: grab;
  transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.4s ease, z-index 0s 0s;
}

.monthly-polaroid.is-dragging {
  transition: transform 0s ease, box-shadow 0s ease !important;
  cursor: grabbing !important;
  z-index: 10000 !important;
  /* 拖拽时适度缩放，保留旋转角度 */
  transform: translate(var(--drag-x, 0px), var(--drag-y, 0px)) scale(1.05) rotate(var(--rotate, 0deg)) !important;
  box-shadow:
    0 24px 48px rgba(0,0,0,0.15),
    0 12px 20px rgba(0,0,0,0.1);
}

@keyframes cardAppear {
  0% {
    opacity: 0;
    transform: translate(var(--drag-x, 0px), calc(var(--drag-y, 0px) + 40px)) rotate(0deg) scale(0.8);
  }
  100% {
    opacity: 1;
    transform: translate(var(--drag-x, 0px), var(--drag-y, 0px)) rotate(var(--rotate, 0deg)) scale(1);
  }
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
  /* 调高胶带透明度并在浅色背景上自然融合 */
  opacity: 0.85;
  box-shadow:
    0 1px 2px rgba(0,0,0,0.08),
    inset 0 1px 1px rgba(255,255,255,0.6);
  z-index: 1;
  transition: transform 0.3s ease;
}

.monthly-polaroid:hover::before {
  transform: translateX(-50%) rotate(-4deg) scale(1.05);
  box-shadow:
    0 2px 4px rgba(0,0,0,0.12),
    inset 0 1px 1px rgba(255,255,255,0.6);
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
