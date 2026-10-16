<template>
  <WrappedCardShell
    :card-id="card.id"
    :title="card.title"
    :narrative="''"
    :variant="variant"
    :wide="true"
    :hide-chrome="variant === 'slide'"
    :bleed="variant === 'slide'"
    :class="variant === 'slide' ? 'cyber-shell' : ''"
    :style="skyVars"
  >
    <!-- panel 变体沿用外壳页头（slide 由场景内自绘页头） -->
    <template v-if="variant !== 'slide'" #narrative>
      <p class="mt-2 wrapped-body text-sm text-[#00000055]" :style="{ '--nar-em': '#07C160' }">
        <template v-if="totalMessages <= 0">今年你还没有发出聊天消息——夜空暂时无星。</template>
        <template v-else>{{ plainNarrative }}</template>
      </p>
    </template>

    <div
      class="sk-stage"
      :class="{
        'sk--in': entered,
        'sk--still': !isActive,
        'sk--reduced': reducedMotion,
        'sk--flat': flatMotion,
        'sk--panel': variant !== 'slide',
        'sk--day': dayness > 0.55
      }"
    >
      <!-- ================= 天空 ================= -->
      <div class="sk-sky" aria-hidden="true"></div>

      <!-- 星空：数量随深夜消息量，白天自动隐去 -->
      <div class="sk-stars" aria-hidden="true">
        <span v-for="(st, i) in nightStars" :key="`st-${i}`" class="sk-star" :style="st"></span>
        <svg v-for="(g, i) in glintStars" :key="`gl-${i}`" class="sk-glint" :style="g" viewBox="0 0 24 24">
          <path d="M12 1 L13.6 10.4 L23 12 L13.6 13.6 L12 23 L10.4 13.6 L1 12 L10.4 10.4 Z" />
        </svg>
      </div>

      <!-- 晨昏方位光：贴着太阳所在的地平线位置升起的暖光 -->
      <div class="sk-azglow" aria-hidden="true"></div>
      <!-- 平流雾：黎明与黄昏时才浮现 -->
      <div class="sk-mist sk-mist--a" aria-hidden="true"></div>
      <div class="sk-mist sk-mist--b" aria-hidden="true"></div>

      <!-- ================= 日月 ================= -->
      <div class="sk-sun" aria-hidden="true">
        <i class="sk-sun-halo"></i>
        <i class="sk-sun-flare"></i>
        <i class="sk-sun-core"></i>
      </div>
      <div class="sk-moon" aria-hidden="true">
        <i class="sk-moon-halo"></i>
        <i class="sk-moon-disc">
          <b class="sk-moon-shade"></b>
          <b class="sk-moon-crater sk-moon-crater--a"></b>
          <b class="sk-moon-crater sk-moon-crater--b"></b>
          <b class="sk-moon-crater sk-moon-crater--c"></b>
        </i>
      </div>

      <!-- ================= 空状态 ================= -->
      <div v-if="totalMessages <= 0" class="sk-empty">
        <div class="sk-empty-horizon" aria-hidden="true"><i></i></div>
        <p class="wrapped-body text-sm text-[#9FB0DA]">等第一条消息发出，这里会升起你的太阳。</p>
      </div>

      <template v-else>
        <!-- ================= 消息地形（24 小时山脊） ================= -->
        <svg
          class="sk-terrain"
          :viewBox="`0 0 1000 ${terTotal}`"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <!-- userSpaceOnUse：山脊高低变化时渐变停点不漂移；山体一直填到卡底，大地与仪表带同为一块 -->
            <linearGradient id="skTerFill" x1="0" y1="0" x2="0" :y2="terTotal" gradientUnits="userSpaceOnUse">
              <stop offset="0" stop-color="rgba(13, 20, 41, 0.5)" />
              <stop offset="0.4" stop-color="rgba(8, 13, 29, 0.84)" />
              <stop offset="0.56" stop-color="rgba(4, 7, 16, 0.97)" />
              <stop offset="1" stop-color="#030509" />
            </linearGradient>
          </defs>
          <path class="sk-ter-fill" :d="terrainClosedPath" />
          <path class="sk-ter-rim" :d="terrainRimPath" vector-effect="non-scaling-stroke" />
          <circle
            v-if="scrubCursor"
            class="sk-ter-dot"
            :cx="scrubCursor.cx"
            :cy="scrubCursor.cy"
            r="3.2"
            vector-effect="non-scaling-stroke"
          />
        </svg>

        <!-- 掠时层：横向掠过/拖拽即拨动一天的光线 -->
        <div
          ref="scrubEl"
          class="sk-scrub"
          data-deck-nodrag
          role="slider"
          :aria-label="sceneAriaLabel"
          :aria-valuemin="0"
          :aria-valuemax="23"
          :aria-valuenow="targetHour"
          :aria-valuetext="`${pad2(targetHour)}:00，${formatInt(readoutCount)} 条消息`"
          tabindex="0"
          @pointerdown="onScrubDown"
          @pointermove="onScrubMove"
          @pointerup="onScrubUp"
          @pointercancel="onScrubUp"
          @pointerleave="onScrubLeave"
          @keydown.left.prevent="nudgeHour(-1)"
          @keydown.right.prevent="nudgeHour(1)"
        ></div>

        <!-- 测量发丝线：掠动时从天垂到山脊表面 -->
        <div
          class="sk-hairline"
          :class="{ 'sk-hairline--on': scrubbing }"
          :style="scrubCursor ? { bottom: `${scrubCursor.bottomPx}px` } : null"
          aria-hidden="true"
        ></div>

        <!-- 时刻星钉：晨光最早 / 一天最晚（碰到即把天色拨到那一刻） -->
        <button
          v-for="p in pins"
          :key="`pin-${p.key}`"
          type="button"
          class="sk-pin"
          :class="{ 'sk-pin--hot': pinHover === p.key, 'sk-pin--silver': p.silver }"
          :style="{ left: `${p.xPct}%`, bottom: `${p.bottomPx}px` }"
          @pointerenter="onPinEnter(p)"
          @pointerleave="onPinLeave"
          @click.stop="pinHover = pinHover === p.key ? null : p.key"
        >
          <svg viewBox="0 0 14 14" aria-hidden="true">
            <path d="M7 0.8 L8.5 5.5 L13.2 7 L8.5 8.5 L7 13.2 L5.5 8.5 L0.8 7 L5.5 5.5 Z" />
          </svg>
          <span class="sr-only">{{ p.label }} {{ p.time }}</span>
        </button>

        <!-- 星钉弹层 -->
        <Transition name="sk-pop">
          <div
            v-if="activePin"
            class="sk-pin-tip"
            :style="{ left: `${activePin.tipLeftPct}%`, bottom: `${activePin.bottomPx + 26}px` }"
          >
            <div class="wrapped-label text-[10px] text-[#9FB0DA]">{{ activePin.label }} · {{ activePin.date }} {{ activePin.time }}</div>
            <div class="mt-1.5 flex justify-end">
              <div class="sk-bubble sk-bubble--sent">
                <div class="wrapped-label text-[10px] text-[#00000066] mb-0.5">
                  你对 <span class="wrapped-privacy-name">{{ activePin.who }}</span> 说
                </div>
                <div class="wrapped-body text-xs wrapped-privacy-message">{{ activePin.text }}</div>
              </div>
            </div>
          </div>
        </Transition>

        <!-- 文字层容器。16:9 / 4:3 / 1:1 下 display:contents（不生成盒，页头/判词/读数照旧各自
             absolute 定位，逐像素零回归）；竖幅下才变成真正的纵向流容器，把「左判词 / 右读数」
             的左右分栏折成 判词 → 读数 的一列。 -->
        <div class="sk-column">
          <!-- ================= 页头（slide 自绘，与光线同呼吸） ================= -->
          <header v-if="variant === 'slide'" class="sk-head">
            <h2 class="sk-title wrapped-title">{{ card.title }}</h2>
            <p class="sk-nar wrapped-body">
              <template v-if="personality === 'early_bird'">清晨 <b class="sk-em">{{ pad2(mostActiveHour) }}</b>:00，当城市还在沉睡，你已经开始了新一天的问候。</template>
              <template v-else-if="personality === 'office_worker'">忙碌的上午 <b class="sk-em">{{ pad2(mostActiveHour) }}</b>:00，是你最常敲击键盘的时刻。</template>
              <template v-else-if="personality === 'afternoon'">午后的阳光里，<b class="sk-em">{{ pad2(mostActiveHour) }}</b>:00 是你最爱分享的时刻。</template>
              <template v-else-if="personality === 'night_owl'">夜幕降临，<b class="sk-em">{{ pad2(mostActiveHour) }}</b>:00 是你最常出没的时刻。</template>
              <template v-else-if="personality === 'late_night'">当世界沉睡，凌晨 <b class="sk-em">{{ pad2(mostActiveHour) }}</b>:00 的你依然在线。</template>
              <template v-else>你在 <b class="sk-em">{{ pad2(mostActiveHour) }}</b>:00 最活跃。</template>
              <template v-if="mostActiveWeekdayName"><b class="sk-em">{{ mostActiveWeekdayName }}</b>最活跃，</template>这一年你用 <b class="sk-em">{{ formatInt(totalMessages) }}</b> 条消息，把这些时刻都留在了对话里。
            </p>
          </header>

          <!-- ================= 判词（横幅在左 / 竖幅在上） ================= -->
          <div class="sk-verdict">
            <div class="sk-kicker wrapped-label">时段人格 · 这一年的答案</div>
            <div class="sk-word wrapped-title">{{ personaTitle }}</div>
            <p class="sk-word-sub wrapped-body">
              {{ personaLine }}
              <template v-if="mostActiveHour !== null && mostActiveWeekdayName">
                最常亮起在<span class="sk-token wrapped-number">{{ mostActiveWeekdayName }}</span>的
                <span class="sk-token wrapped-number">{{ pad2(mostActiveHour) }}:00</span>。
              </template>
            </p>
            <template v-if="earliestSent && latestSent">
              <p v-if="earliestSent.displayName === latestSent.displayName" class="sk-word-echo wrapped-body">
                最先想起的是「<span class="sk-token wrapped-privacy-name">{{ earliestSent.displayName }}</span>」，最后放不下的也还是同一个人。
              </p>
              <p v-else class="sk-word-echo wrapped-body">
                一天里最早的一条发给了「<span class="sk-token wrapped-privacy-name">{{ earliestSent.displayName }}</span>」，最晚的一条发给了「<span class="sk-token wrapped-privacy-name">{{ latestSent.displayName }}</span>」。
              </p>
            </template>
          </div>

          <!-- ================= 时刻仪表（横幅在右 / 竖幅贴着地平线） ================= -->
          <div class="sk-readout" aria-live="off">
            <div class="sk-ro-scope wrapped-label">{{ readoutScopeLabel }} · {{ twilightWord }}</div>
            <div class="sk-ro-hour wrapped-number">{{ pad2(targetHour) }}<i>:</i>00</div>
            <div class="sk-ro-count wrapped-number">{{ readoutCountDisplay }} <i>条</i><em>{{ readoutShareText }}</em></div>
            <p class="sk-ro-care wrapped-body">{{ careLine }}</p>

            <!-- 星期拨片：跟着读数走，切换整片山脊 -->
            <div class="sk-chips" role="group" aria-label="按星期查看">
              <button
                type="button"
                class="sk-chip wrapped-label"
                :class="{ 'sk-chip--on': weekdaySel < 0 }"
                :style="{ '--chip-d': '1450ms' }"
                @click="setWeekday(-1)"
              >全年</button>
              <button
                v-for="(w, wi) in weekdayShort"
                :key="`wd-${wi}`"
                type="button"
                class="sk-chip wrapped-label"
                :class="{ 'sk-chip--on': weekdaySel === wi }"
                :style="{ '--chip-d': `${1500 + wi * 45}ms` }"
                @click="setWeekday(wi)"
              >{{ w }}</button>
            </div>
          </div>
        </div>

        <!-- ================= 大地仪表带 ================= -->
        <div class="sk-ground">
          <div class="sk-ground-sheen" aria-hidden="true"></div>

          <div class="sk-inst">
            <!-- 光谱：早八人 ←→ 夜猫子 -->
            <div
              class="sk-cluster"
              :style="{ '--inst-d': '1550ms' }"
              :title="`19:00 后与凌晨的消息占全年 ${spectrumPct}%`"
            >
              <div class="sk-cl-label wrapped-label">早八人 · 夜猫子</div>
              <div class="sk-spectrum" aria-hidden="true">
                <svg class="sk-sp-glyph" viewBox="0 0 12 12"><circle cx="6" cy="6" r="2.6" fill="currentColor" /><g stroke="currentColor" stroke-width="1" stroke-linecap="round"><line x1="6" y1="0.6" x2="6" y2="2.2" /><line x1="6" y1="9.8" x2="6" y2="11.4" /><line x1="0.6" y1="6" x2="2.2" y2="6" /><line x1="9.8" y1="6" x2="11.4" y2="6" /><line x1="2.2" y1="2.2" x2="3.3" y2="3.3" /><line x1="8.7" y1="8.7" x2="9.8" y2="9.8" /><line x1="9.8" y1="2.2" x2="8.7" y2="3.3" /><line x1="3.3" y1="8.7" x2="2.2" y2="9.8" /></g></svg>
                <span class="sk-sp-bar"><i class="sk-sp-marker" :style="{ left: `${spectrumPct}%` }"></i></span>
                <svg class="sk-sp-glyph" viewBox="0 0 12 12"><path d="M 8.6 1.6 A 5 5 0 1 0 10.4 8.4 A 4.1 4.1 0 0 1 8.6 1.6 Z" fill="currentColor" /></svg>
              </div>
              <div class="sk-cl-note">夜晚浓度 <b class="wrapped-number">{{ spectrumPct }}%</b></div>
            </div>

            <i class="sk-inst-rule" aria-hidden="true"></i>

            <!-- 深夜指数 / 守夜人 -->
            <div class="sk-cluster-wrap" :style="{ '--inst-d': '1650ms' }">
              <component
                :is="nightPartner ? 'button' : 'div'"
                :type="nightPartner ? 'button' : undefined"
                class="sk-cluster sk-cluster--night"
                :class="{ 'sk-cluster--open': nightOpen }"
                :aria-expanded="nightPartner ? String(nightOpen) : undefined"
                @pointerenter="onNightEnter"
                @pointerleave="onHoverRelease"
                @click.stop="nightPartner ? (nightOpen = !nightOpen) : null"
              >
                <span v-if="nightPartner" class="sk-night-avatar wrapped-privacy-avatar">
                  <img
                    v-if="nightPartnerAvatarUrl && nightAvatarOk"
                    :src="nightPartnerAvatarUrl"
                    :alt="nightPartner.displayName"
                    @error="nightAvatarOk = false"
                  />
                  <span v-else class="sk-night-avatar-fb wrapped-number">☾</span>
                </span>
                <span class="sk-cl-main">
                  <span class="sk-cl-label wrapped-label">深夜指数<em class="sk-cl-value wrapped-number">{{ nightSharePctDisplay }}%</em></span>
                  <span v-if="nightPartner" class="sk-cl-note sk-cl-note--row">
                    <span class="sk-cl-ellip">守夜人 <b class="wrapped-privacy-name">{{ nightPartner.displayName }}</b> 陪你点亮 {{ nightShare }}% 的深夜</span>
                    <svg class="sk-chevron" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5 L8 6 L4.5 9.5" /></svg>
                  </span>
                  <span v-else class="sk-cl-note">的话留给了凌晨</span>
                </span>
              </component>

              <!-- 守夜人弹层：贴着集群向上展开 -->
              <Transition name="sk-pop">
                <div v-if="nightOpen && nightPartner" class="sk-night-pop" @click.stop>
                  <span
                    v-for="(st, i) in popStars"
                    :key="`ps-${i}`"
                    class="sk-star sk-pop-star"
                    :style="st"
                    aria-hidden="true"
                  ></span>
                  <div class="wrapped-label text-[10px] text-[#9FB0DA]">
                    凌晨 0:00 – 5:59 · TA 陪你聊了
                    <span class="wrapped-number text-[#FFE9A3] font-semibold">{{ formatInt(nightPartner.nightMessages) }}</span>
                    条 · 点亮你
                    <span class="wrapped-number text-[#FFE9A3] font-semibold">{{ nightShare }}</span>%
                    的深夜
                  </div>
                  <div v-if="nightMoment" class="mt-2 flex items-center gap-3 min-w-0">
                    <div class="flex-shrink-0">
                      <div class="wrapped-number text-xl font-semibold text-white">{{ nightMoment.time }}</div>
                      <div class="wrapped-label text-[10px] text-[#9FB0DA] mt-0.5">{{ nightMomentDateLabel }} · 最晚的一刻</div>
                    </div>
                    <div class="sk-bubble min-w-0" :class="{ 'sk-bubble--sent': nightMoment.direction === 'sent' }">
                      <div class="wrapped-label text-[10px] text-[#00000066] mb-0.5">
                        {{ nightMoment.direction === 'sent' ? '你说' : 'TA 说' }}
                      </div>
                      <div class="wrapped-body text-xs wrapped-privacy-message">{{ trimText(nightMoment.content) }}</div>
                    </div>
                  </div>
                </div>
              </Transition>
            </div>

            <i class="sk-inst-rule" aria-hidden="true"></i>

            <!-- 工作日 vs 周末 -->
            <div
              v-if="tugVisible"
              class="sk-cluster"
              :style="{ '--inst-d': '1750ms' }"
              :title="`工作日日均 ${formatInt(weekdayAvg)} 条 · 周末日均 ${formatInt(weekendAvg)} 条`"
            >
              <div class="sk-cl-label wrapped-label">工作日 VS 周末<em class="sk-cl-value wrapped-number">{{ tugRatioText }}</em></div>
              <div class="sk-meter" aria-hidden="true">
                <i class="sk-meter__wd" :style="{ flexGrow: tugWdPct }"></i>
                <i class="sk-meter__we" :style="{ flexGrow: 100 - tugWdPct }"></i>
              </div>
              <div class="sk-cl-note">日均 <b class="wrapped-number">{{ formatInt(weekdayAvg) }}</b> vs <b class="wrapped-number">{{ formatInt(weekendAvg) }}</b> 条</div>
            </div>

            <i v-if="tugVisible" class="sk-inst-rule" aria-hidden="true"></i>

            <!-- 最安静的一小时 -->
            <div
              v-if="quietestHour"
              class="sk-cluster"
              :style="{ '--inst-d': '1850ms' }"
              @pointerenter="onQuietEnter"
              @pointerleave="onHoverRelease"
            >
              <div class="sk-cl-label wrapped-label">最安静的一小时<em class="sk-cl-value wrapped-number">{{ pad2(quietestHour.hour) }}:00</em></div>
              <div class="sk-cl-note">仅 {{ formatInt(quietestHour.count) }} 条 · 世界都睡了</div>
            </div>
          </div>

          <!-- 年度地平线：第一条 ←——→ 最后一条 -->
          <div v-if="yearFirstSent || yearLastSent" class="sk-yearline">
            <div
              v-if="yearFirstSent"
              class="sk-yl-end"
              :title="momentTitle(yearFirstSent)"
              @pointerenter="onMomentEnter(yearFirstSent)"
              @pointerleave="onHoverRelease"
            >
              <span class="sk-yl-cap wrapped-label">年度第一条</span>
              <span class="sk-yl-val sk-yl-val--gold wrapped-number">{{ yearFirstDateLabel }} {{ yearFirstSent.time }}</span>
            </div>
            <div class="sk-yl-line" aria-hidden="true"></div>
            <div
              v-if="yearLastSent"
              class="sk-yl-end sk-yl-end--r"
              :title="momentTitle(yearLastSent)"
              @pointerenter="onMomentEnter(yearLastSent)"
              @pointerleave="onHoverRelease"
            >
              <span class="sk-yl-cap wrapped-label">年度最后一条</span>
              <span class="sk-yl-val sk-yl-val--silver wrapped-number">{{ yearLastDateLabel }} {{ yearLastSent.time }}</span>
            </div>
          </div>

        </div>

        <!-- 材质层：细颗粒压住渐变色带 + 随昼夜呼吸的暗角 -->
        <div class="sk-grain" aria-hidden="true"></div>
        <div class="sk-vignette" aria-hidden="true"></div>
      </template>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useCountUp } from '~/composables/useCountUp'
import { useWrappedStage } from '~/composables/useWrappedStage'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  isActive: { type: Boolean, default: true } // deck 当前展示页时为 true
})

const stage = useWrappedStage()

// 竖幅（3:4 / 4:5 / 9:16）走纵向四段流：判词 → 读数 → 日月地平线 → 仪表带
const isTallish = computed(() => stage.tier.value === 'portrait' || stage.tier.value === 'tall')

const _DEFAULT_WEEKDAYS_ZH = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const weekdayLabels = computed(() => {
  const labels = props.card?.data?.weekdayLabels
  if (Array.isArray(labels) && labels.length >= 7) return labels
  return _DEFAULT_WEEKDAYS_ZH
})

const weekdayShort = computed(() => weekdayLabels.value.map((s) => String(s || '').replace(/^周|^星期/, '') || s))

const matrix = computed(() => {
  const m = props.card?.data?.matrix
  return Array.isArray(m) ? m : null
})

const totalMessages = computed(() => Number(props.card?.data?.totalMessages || 0))

// ---------- 通用格式化 ----------

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))
const pad2 = (h) => String(Number(h ?? 0)).padStart(2, '0')

const _formatDateLabel = (ymd) => {
  const s = String(ymd || '').trim()
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return s
  return `${Number(m[2])}月${Number(m[3])}日`
}

const trimText = (s) => {
  const t = String(s || '').trim()
  return t.length > 26 ? `${t.slice(0, 26)}…` : (t || '...')
}

const momentTitle = (m) => {
  if (!m) return ''
  return `${m.time} 发给 ${m.displayName}：${m.content || ''}`
}

// ---------- 小时聚合 ----------

const hourTotals = computed(() => {
  const out = Array.from({ length: 24 }, () => 0)
  if (!matrix.value) return out
  for (let w = 0; w < 7; w += 1) {
    const row = matrix.value[w]
    if (!Array.isArray(row)) continue
    for (let h = 0; h < 24; h += 1) {
      const v = Number(row[h] || 0)
      if (Number.isFinite(v)) out[h] += v
    }
  }
  return out
})

const allHoursTotal = computed(() => hourTotals.value.reduce((a, b) => a + b, 0))

// 单元格全局最大值：星期视图共用一把尺，切换时高低可对比
const matrixCellMax = computed(() => {
  let m = 1
  if (!matrix.value) return m
  for (let w = 0; w < 7; w += 1) {
    const row = matrix.value[w]
    if (!Array.isArray(row)) continue
    for (let h = 0; h < 24; h += 1) {
      const v = Number(row[h] || 0)
      if (v > m) m = v
    }
  }
  return m
})

const mostActiveHour = computed(() => {
  if (allHoursTotal.value <= 0) return null
  let bestH = 0
  let bestV = -1
  for (let h = 0; h < 24; h += 1) {
    const v = hourTotals.value[h]
    if (v > bestV) { bestV = v; bestH = h }
  }
  return bestH
})

const mostActiveWeekdayIndex = computed(() => {
  if (!matrix.value) return null
  let bestW = 0
  let bestV = -1
  for (let w = 0; w < 7; w += 1) {
    const row = matrix.value[w]
    if (!Array.isArray(row)) continue
    let s = 0
    for (let h = 0; h < 24; h += 1) s += Number(row[h] || 0)
    if (s > bestV) { bestV = s; bestW = w }
  }
  return bestV >= 0 ? bestW : null
})

const mostActiveWeekdayName = computed(() => {
  const idx = mostActiveWeekdayIndex.value
  if (idx === null) return ''
  return String(weekdayLabels.value[idx] || '')
})

// ---------- 时段人格 ----------

const personality = computed(() => {
  const hour = mostActiveHour.value
  if (hour === null) return 'unknown'
  if (hour >= 5 && hour <= 8) return 'early_bird'
  if (hour >= 9 && hour <= 12) return 'office_worker'
  if (hour >= 13 && hour <= 17) return 'afternoon'
  if (hour >= 18 && hour <= 23) return 'night_owl'
  if (hour >= 0 && hour <= 4) return 'late_night'
  return 'unknown'
})

const _PERSONA = {
  early_bird: { title: '早八人', line: '城市还没醒，你的对话框先亮了。' },
  office_worker: { title: '朝九晚五派', line: '工作的间隙，也是聊天的黄金时段。' },
  afternoon: { title: '午后电台', line: '阳光正好的时候，你的话也最多。' },
  night_owl: { title: '夜猫子', line: '夜幕降临后，你的话匣子才真正打开。' },
  late_night: { title: '凌晨电台', line: '当世界安静下来，你还在线。' },
  unknown: { title: '神出鬼没', line: '你的活跃时刻，自成一派。' }
}

const personaTitle = computed(() => _PERSONA[personality.value]?.title || _PERSONA.unknown.title)
const personaLine = computed(() => _PERSONA[personality.value]?.line || '')

// panel 变体的一段式叙事（slide 自绘富文本页头）
const plainNarrative = computed(() => {
  const h = mostActiveHour.value
  if (h === null) return ''
  return `${personaLine.value} ${mostActiveWeekdayName.value || ''}的 ${pad2(h)}:00 是你最常亮起的时刻，这一年共 ${formatInt(totalMessages.value)} 条消息。`
})

// ---------- 取值范围（全年 / 某个星期） ----------

const weekdaySel = ref(-1) // -1 = 全年

const dialVals = computed(() => {
  if (weekdaySel.value < 0) return hourTotals.value
  const row = matrix.value?.[weekdaySel.value]
  const out = Array.from({ length: 24 }, () => 0)
  if (!Array.isArray(row)) return out
  for (let h = 0; h < 24; h += 1) out[h] = Number(row[h] || 0)
  return out
})

const dialMax = computed(() => {
  // 全年视图用小时总量归一；星期视图用矩阵单元格最大值（跨星期同尺，可对比）
  if (weekdaySel.value < 0) return Math.max(1, ...hourTotals.value)
  return matrixCellMax.value
})

const dialScopeTotal = computed(() => dialVals.value.reduce((a, b) => a + b, 0))

// 当前视图内的峰值小时（切星期时光线自动落到那一天的峰值）
const dialPeakHour = computed(() => {
  let bestH = mostActiveHour.value ?? 12
  let bestV = -1
  for (let h = 0; h < 24; h += 1) {
    const v = dialVals.value[h]
    if (v > bestV) { bestV = v; bestH = h }
  }
  return bestH
})

const setWeekday = (w) => {
  if (weekdaySel.value === w) return
  weekdaySel.value = w
  selHourF.value = null // 回到该视图的峰值
}

// ---------- 场景几何 ----------
// 横轴：一天 24 小时铺满全宽（两侧留 X_PAD% 呼吸），0 点在最左、24 点在最右。
// 纵轴：地平线 = 大地仪表带上缘；日月沿一条大弧线运行，山脊立在地平线上。

const X_PAD = 3 // 横向留白（%）
const TER_H = 190 // 山脊起伏区高度（px，与渲染高度 1:1）。构件尺寸：各画幅恒定，不随画幅缩放

// 大地仪表带高度（px）。**这里是唯一真源**——CSS 通过 skyVars 下发的
// --ter-h / --ground-h / --ter-total 消费，样式表里不得再写第二份数字：
// 早先 CSS 的 .sk--panel{--ground-h:132px} 与 JS 的 148 脱钩，星钉与发丝线整体偏了 16px。
// 竖幅下四组仪表要折成 2×2，仪表带随之长高。
const groundH = computed(() => {
  if (props.variant !== 'slide') return 132
  // 竖幅下四组仪表折成 2×2 且排印整体放大（见文末「竖幅放大」），仪表带随之长高。
  // 9:16 最窄，注解换行最多，留得比 3:4 / 4:5 更足。
  // tall（9:16）下仪表带的排印又放大了一档（见文末「9:16 读数放大」），
  // 注解普遍折成两行，仪表带要再长一截才装得下。
  if (stage.tier.value === 'tall') return 362
  return isTallish.value ? 282 : 148
})

// 山体画布总高：从山脊一直填到卡底，与仪表带融为一块大地
const terTotal = computed(() => TER_H + groundH.value)

const xPctOf = (hFloat) => X_PAD + (Math.max(0, Math.min(24, hFloat)) / 24) * (100 - X_PAD * 2)
const hourCenterPct = (h) => xPctOf(h + 0.5)

// 太阳高度：h=6 升起、12 正午、18 落下；夜里为负（月亮取反）
const sunAltOf = (h) => Math.sin(((h - 6) / 12) * Math.PI)

// ---------- 消息山脊 ----------

// 展示高度（0..1），入场时从平地长起，切星期时整体变形
const shownHeights = Array.from({ length: 24 }, () => 0)
const terrainVer = ref(0)
let heightTweens = []

const targetHeights = computed(() => {
  const out = []
  for (let h = 0; h < 24; h += 1) {
    const v = dialVals.value[h]
    const pct = Math.max(0, Math.min(1, v / dialMax.value))
    out.push(v <= 0 ? 0.018 : 0.08 + Math.pow(pct, 0.58) * 0.92)
  }
  return out
})

const killHeightTweens = () => {
  for (const t of heightTweens) t.kill()
  heightTweens = []
}

const setHeightsNow = (arr) => {
  killHeightTweens()
  for (let h = 0; h < 24; h += 1) shownHeights[h] = arr[h]
  terrainVer.value += 1
}

const morphHeightsTo = (arr, { duration = 0.85, stagger = 0.012, ease = 'power3.inOut' } = {}) => {
  if (reducedMotion.value || typeof window === 'undefined') {
    setHeightsNow(arr)
    return
  }
  killHeightTweens()
  for (let h = 0; h < 24; h += 1) {
    const obj = { v: shownHeights[h] }
    heightTweens.push(gsap.to(obj, {
      v: arr[h],
      duration,
      delay: h * stagger,
      ease,
      onUpdate: () => { shownHeights[h] = obj.v; terrainVer.value += 1 }
    }))
  }
}

watch(targetHeights, (arr) => {
  if (!entered.value) return
  morphHeightsTo(arr)
})

// Catmull-Rom → 三次贝塞尔，山脊平滑成一条山脉线
const _catmullPath = (pts) => {
  if (pts.length < 2) return ''
  let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`
  for (let i = 0; i < pts.length - 1; i += 1) {
    const p0 = pts[Math.max(0, i - 1)]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[Math.min(pts.length - 1, i + 2)]
    const c1x = p1[0] + (p2[0] - p0[0]) / 6
    const c1y = p1[1] + (p2[1] - p0[1]) / 6
    const c2x = p2[0] - (p3[0] - p1[0]) / 6
    const c2y = p2[1] - (p3[1] - p1[1]) / 6
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`
  }
  return d
}

const TER_TOP_PAD = 16 // 最高峰离山脊层顶部的余量
const terYOf = (frac) => TER_H - 4 - frac * (TER_H - TER_TOP_PAD - 4)

const terrainPts = computed(() => {
  // 依赖 version 以驱动重算
  void terrainVer.value
  const pts = [[0, terYOf(shownHeights[0] * 0.55)]]
  for (let h = 0; h < 24; h += 1) {
    pts.push([hourCenterPct(h) * 10, terYOf(shownHeights[h])])
  }
  pts.push([1000, terYOf(shownHeights[23] * 0.55)])
  return pts
})

const terrainRimPath = computed(() => _catmullPath(terrainPts.value))
const terrainClosedPath = computed(() => `${terrainRimPath.value} L 1000 ${terTotal.value} L 0 ${terTotal.value} Z`)

// ---------- 选中小时 + 相位（连续小时数，驱动光线与读数） ----------

const selHourF = ref(null) // 掠动/悬停到的小时（浮点）；null = 跟随当前视图峰值
const targetHourF = computed(() => (selHourF.value !== null ? selHourF.value : dialPeakHour.value + 0.5))
const targetHour = computed(() => Math.max(0, Math.min(23, Math.floor(targetHourF.value))))
const scrubbing = computed(() => selHourF.value !== null)

const phase = ref(2) // 连续相位；入场前停在夜色里
let phaseTween = null

const phaseNorm = computed(() => ((phase.value % 24) + 24) % 24)

const killPhaseTween = () => {
  if (phaseTween) { phaseTween.kill(); phaseTween = null }
}

const tweenPhaseTo = (h, { duration = 0.7, ease = 'power3.out', delay = 0, direct = false } = {}) => {
  killPhaseTween()
  const cur = phase.value
  // direct = 按绝对值走（入场长扫用）；否则走圆上最短路径
  let dest = h
  if (!direct) {
    const curN = ((cur % 24) + 24) % 24
    const delta = ((((h - curN) % 24) + 36) % 24) - 12
    dest = cur + delta
  }
  if (reducedMotion.value || typeof window === 'undefined') {
    phase.value = dest
    return
  }
  const obj = { v: cur }
  phaseTween = gsap.to(obj, {
    v: dest,
    duration,
    ease,
    delay,
    onUpdate: () => { phase.value = obj.v },
    onComplete: () => { phase.value = dest; phaseTween = null }
  })
}

// 掠动跟随：短促的追随缓动，光线像被指尖牵着走
watch(targetHourF, (h) => {
  if (!entered.value) return
  finishReadout()
  tweenPhaseTo(h, { duration: scrubbing.value ? 0.5 : 0.95, ease: scrubbing.value ? 'power3.out' : 'power3.inOut' })
})

watch(weekdaySel, () => {
  if (entered.value) finishReadout()
})

// ---------- 掠时交互 ----------

const scrubEl = ref(null)
const draggingScrub = ref(false)
let scrubPointerId = null

const hourFromEvent = (e) => {
  const el = scrubEl.value
  if (!el) return null
  const rect = el.getBoundingClientRect()
  if (!rect.width) return null
  const pct = ((e.clientX - rect.left) / rect.width) * 100
  const hf = ((pct - X_PAD) / (100 - X_PAD * 2)) * 24
  return Math.max(0.01, Math.min(23.99, hf))
}

const onScrubMove = (e) => {
  const h = hourFromEvent(e)
  if (h === null) return
  selHourF.value = h
}

const onScrubDown = (e) => {
  const h = hourFromEvent(e)
  if (h === null) return
  if (e.pointerType === 'touch' || e.pointerType === 'pen') e.preventDefault()
  draggingScrub.value = true
  scrubPointerId = e.pointerId
  selHourF.value = h
  try { scrubEl.value?.setPointerCapture?.(e.pointerId) } catch {}
}

const onScrubUp = (e) => {
  if (scrubPointerId !== null && e.pointerId !== scrubPointerId) return
  draggingScrub.value = false
  scrubPointerId = null
}

const onScrubLeave = () => {
  if (draggingScrub.value) return
  selHourF.value = null
  pinHover.value = null
}

const nudgeHour = (d) => {
  const cur = selHourF.value !== null ? selHourF.value : dialPeakHour.value + 0.5
  selHourF.value = Math.max(0.01, Math.min(23.99, Math.floor(cur) + d + 0.5))
}

// 数据元素的「借光」：碰到哪个时刻，天色就拨到那个时刻
const _hourFloatOf = (timeStr) => {
  const m = String(timeStr || '').match(/^(\d{1,2}):(\d{2})/)
  if (!m) return null
  const h = Number(m[1]) + Number(m[2]) / 60
  return h >= 0 && h < 24 ? h : null
}

const hoverScrub = (hf) => {
  if (hf === null || hf === undefined) return
  selHourF.value = Math.max(0.01, Math.min(23.99, hf))
}

const onHoverRelease = () => {
  if (draggingScrub.value) return
  selHourF.value = null
}

const onNightEnter = () => hoverScrub(_hourFloatOf(nightMoment.value?.time) ?? 1.8)
const onQuietEnter = () => hoverScrub(quietestHour.value ? quietestHour.value.hour + 0.5 : null)
const onMomentEnter = (m) => hoverScrub(_hourFloatOf(m?.time))

// ---------- 读数 ----------

const readoutScopeLabel = computed(() => (weekdaySel.value < 0 ? '全年' : String(weekdayLabels.value[weekdaySel.value] || '')))

const readoutCount = computed(() => Number(dialVals.value[targetHour.value] || 0))

const { display: readoutCountDisplay, restart: restartReadout, finish: finishReadout } = useCountUp(
  () => readoutCount.value,
  { duration: 1.1, delay: 0.35 }
)

const readoutShareText = computed(() => {
  const total = dialScopeTotal.value
  const v = readoutCount.value
  const pct = total > 0 ? Math.round((v * 1000) / total) / 10 : 0
  if (weekdaySel.value < 0 && targetHour.value === mostActiveHour.value) return `全年最亮 · 占 ${pct}%`
  if (weekdaySel.value >= 0 && targetHour.value === dialPeakHour.value) return `这一天最亮 · 占 ${pct}%`
  return `占${weekdaySel.value < 0 ? '全年' : '这一天'} ${pct}%`
})

// 每个钟点一句话：掠到哪一小时，就说那一小时的人话
const _CARE_LINES = [
  '跨过零点还没说完的话，都带着舍不得。',
  '凌晨一点，城市静了音，你还有下文。',
  '两点钟的对话框，装着白天没说出口的话。',
  '三点还亮着的屏幕，是还没放下的人。',
  '四点，夜最深处，连消息都轻手轻脚。',
  '五点，天边泛起灰蓝，有人已经醒着想事了。',
  '六点，第一缕光和第一声早安一起抵达。',
  '七点，通勤路上，手指比脚步先出发。',
  '八点，早八人的问候准时上线。',
  '九点，忙碌开场，消息夹在待办之间。',
  '十点，工作间隙的闲聊，是上午的糖。',
  '十一点，一句「中午吃什么」准时出现。',
  '十二点，饭点的热闹，一半在桌上，一半在群里。',
  '下午一点，午休的尾巴，留给想聊的人。',
  '两点，午后阳光斜过来，话也慢悠悠。',
  '三点，需要一杯咖啡，也需要一句闲话。',
  '四点，一天过了大半，惦记的人冒出来了。',
  '五点，快下班的键盘，敲得格外轻快。',
  '六点，暮色四合，正是想起谁的时候。',
  '七点，晚饭后的消息，都带着烟火气。',
  '八点，一天里最松弛的对话在这会儿。',
  '九点，夜刚好，话也刚好。',
  '十点，道过晚安之后，才轮到真心话。',
  '十一点，最后一轮消息，把今天好好说完。'
]

const careLine = computed(() => {
  const h = targetHour.value
  const q = quietestHour.value
  if (q && h === q.hour && weekdaySel.value < 0) {
    return `这一小时全年只有 ${formatInt(q.count)} 条——世界都睡了。`
  }
  return _CARE_LINES[h] || ''
})

// 暮光阶段词（Apple Solar 表盘的天文词汇）：按太阳高度分段
const twilightWord = computed(() => {
  const alt = sunAltOf(phaseNorm.value)
  if (alt > 0.55) return '白昼'
  if (alt > 0.16) return '斜阳'
  if (alt > 0) return '金色时刻'
  if (alt > -0.12) return '民用暮光'
  if (alt > -0.24) return '航海暮光'
  if (alt > -0.38) return '天文暮光'
  return '夜'
})

const sceneAriaLabel = computed(() => {
  const h = mostActiveHour.value
  if (h === null) return '24 小时消息光线仪'
  return `24 小时消息光线仪，左右掠动查看每小时。最活跃 ${pad2(h)}:00，共 ${formatInt(hourTotals.value[h] || 0)} 条`
})

// ---------- 天空相位（颜色 / 星光 / 晨昏光 / 墨色随时刻插值） ----------

const _hex = (s) => [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)]
const _lerp = (a, b, t) => a + (b - a) * t
const _lerpRgb = (a, b, t) => [Math.round(_lerp(a[0], b[0], t)), Math.round(_lerp(a[1], b[1], t)), Math.round(_lerp(a[2], b[2], t))]
const _css = (rgb, alpha = 1) => (alpha >= 1 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`)

// [小时, [天顶, 上层, 下层, 地平线], 星光, 晨昏光, 白昼度, 雾]
const SKY_KEYS = [
  [0.0, ['#04060F', '#0A0F22', '#111931', '#18203C'], 1.0, 0.0, 0.0, 0.0],
  [3.8, ['#05081A', '#0D142E', '#1A2140', '#262A4E'], 0.95, 0.04, 0.0, 0.06],
  [5.0, ['#0A1128', '#161E44', '#2B2C58', '#4A3A66'], 0.7, 0.2, 0.0, 0.3],
  [6.0, ['#142244', '#2C3A6E', '#6C4F80', '#C87F6B'], 0.3, 0.62, 0.06, 0.55],
  [6.9, ['#1D3A64', '#3E5C92', '#A97C85', '#F0A45F'], 0.08, 0.92, 0.3, 0.6],
  [8.5, ['#2C5C96', '#4E7DB4', '#88A8CA', '#C4D0D6'], 0.0, 0.3, 0.85, 0.25],
  [12.5, ['#336FB2', '#5E93CA', '#96B6D9', '#CCDAE3'], 0.0, 0.12, 1.0, 0.0],
  [16.3, ['#2F5E99', '#5882B2', '#96A2C3', '#DAB293'], 0.0, 0.3, 0.88, 0.0],
  [18.2, ['#24406C', '#4C5992', '#A26C89', '#EE9260'], 0.06, 0.95, 0.34, 0.1],
  [19.3, ['#141F44', '#2B3266', '#573F78', '#9C5A63'], 0.4, 0.55, 0.05, 0.15],
  [20.6, ['#0A1128', '#141B3E', '#232453', '#372C58'], 0.8, 0.16, 0.0, 0.05],
  [22.0, ['#060916', '#0C1226', '#141B36', '#1C2442'], 0.96, 0.0, 0.0, 0.0],
  [24.0, ['#04060F', '#0A0F22', '#111931', '#18203C'], 1.0, 0.0, 0.0, 0.0]
].map(([h, colors, star, az, day, mist]) => [h, colors.map(_hex), star, az, day, mist])

const skyAt = (hour) => {
  const h = ((hour % 24) + 24) % 24
  let i = 0
  while (i < SKY_KEYS.length - 2 && h >= SKY_KEYS[i + 1][0]) i += 1
  const [h0, c0, s0, a0, d0, m0] = SKY_KEYS[i]
  const [h1, c1, s1, a1, d1, m1] = SKY_KEYS[i + 1]
  const t = h1 > h0 ? Math.max(0, Math.min(1, (h - h0) / (h1 - h0))) : 0
  return {
    colors: c0.map((rgb, ci) => _lerpRgb(rgb, c1[ci], t)),
    star: _lerp(s0, s1, t),
    az: _lerp(a0, a1, t),
    dayness: _lerp(d0, d1, t),
    mist: _lerp(m0, m1, t)
  }
}

const _INK_NIGHT = _hex('#F3F6FF')
const _INK_DAY = _hex('#0C1D36')
const _RIM_WARM = _hex('#FFD98F')
const _RIM_SILVER = _hex('#BCCBF2')

const skyState = computed(() => skyAt(phaseNorm.value))
const dayness = computed(() => skyState.value.dayness)

const skyVars = computed(() => {
  const h = phaseNorm.value
  const { colors, star, az, dayness: day, mist } = skyState.value
  const alt = sunAltOf(h)

  // 日 / 月位置（同一条弧线，太阳白天在上，月亮夜里在上）
  const xs = xPctOf(h)
  const horizonFrac = 0.985
  const archFrac = 0.75
  const sunFrac = horizonFrac - Math.max(0, alt) * archFrac
  const moonFrac = horizonFrac - Math.max(0, -alt) * archFrac
  const sunA = Math.max(0, Math.min(1, alt * 6 + 0.35))
  const moonA = Math.max(0, Math.min(1, -alt * 6 + 0.35))
  // 水平光晕只在贴近地平线时出现（升落时分的大气拉丝）
  const flareA = sunA * Math.max(0, Math.min(1, 1 - alt * 2.6))

  // 墨色：夜里霜白，白天钢青，跟着天光换气
  const ink = _lerpRgb(_INK_NIGHT, _INK_DAY, day)
  const rim = _lerpRgb(_RIM_SILVER, _RIM_WARM, Math.max(0, Math.min(1, alt * 3 + 0.55)))

  return {
    '--sky-a': _css(colors[0]),
    '--sky-b': _css(colors[1]),
    '--sky-c': _css(colors[2]),
    '--sky-d': _css(colors[3]),
    '--star-alpha': star.toFixed(2),
    '--az-a': az.toFixed(2),
    '--az-x': `${xs.toFixed(2)}%`,
    '--mist-a': mist.toFixed(2),
    '--sun-x': `${xs.toFixed(2)}%`,
    '--sun-y': sunFrac.toFixed(4),
    '--sun-a': sunA.toFixed(2),
    '--flare-a': flareA.toFixed(2),
    '--vig-a': (0.42 - day * 0.3).toFixed(2),
    '--moon-x': `${xs.toFixed(2)}%`,
    '--moon-y': moonFrac.toFixed(4),
    '--moon-a': moonA.toFixed(2),
    '--ink': _css(ink),
    '--ink-2': _css(ink, 0.72),
    '--ink-3': _css(ink, 0.45),
    '--rim': _css(rim),
    '--rim-soft': _css(rim, 0.55),
    '--scrub-x': `${xPctOf(targetHourF.value).toFixed(2)}%`,
    // 场景几何的唯一真源：CSS 只消费，不再自己写一份数字（见 groundH 注释）
    '--ter-h': `${TER_H}px`,
    '--ground-h': `${groundH.value}px`,
    '--ter-total': `${terTotal.value}px`
  }
})

// ---------- 掠动游标 ----------

const scrubCursor = computed(() => {
  if (!scrubbing.value) return null
  void terrainVer.value
  const h = targetHour.value
  const y = terYOf(shownHeights[h])
  return {
    cx: (hourCenterPct(h) * 10).toFixed(1),
    cy: y.toFixed(1),
    // 发丝线垂到山脊表面为止。SVG 高度 = --ter-total，1 个 viewBox 单位恒等于 1px，
    // 所以「距卡底像素」= terTotal - y（+2 是压住描边的构件余量，不随画幅变）
    bottomPx: Math.round(terTotal.value - y) + 2
  }
})

// ---------- 派生指标 ----------

// 深夜指数：0-5 点消息占比（%）
const nightIndexPct = computed(() => {
  const total = allHoursTotal.value
  if (total <= 0) return 0
  let night = 0
  for (let h = 0; h < 6; h += 1) night += hourTotals.value[h]
  return Math.round((night * 1000) / total) / 10
})

// 光谱：夜晚浓度 = 19:00 之后 + 凌晨的消息占比
const spectrumPct = computed(() => {
  const total = allHoursTotal.value
  if (total <= 0) return 50
  let night = 0
  for (let h = 0; h < 24; h += 1) {
    if (h >= 19 || h < 5) night += hourTotals.value[h]
  }
  return Math.round((night * 1000) / total) / 10
})

const quietestHour = computed(() => {
  if (allHoursTotal.value <= 0) return null
  let bestH = 0
  let bestV = Infinity
  for (let h = 0; h < 24; h += 1) {
    const v = hourTotals.value[h]
    if (v < bestV) { bestV = v; bestH = h }
  }
  return { hour: bestH, count: bestV }
})

const weekdayAvg = computed(() => {
  if (!matrix.value) return 0
  let s = 0
  for (let w = 0; w < 5; w += 1) {
    const row = matrix.value[w]
    if (!Array.isArray(row)) continue
    for (let h = 0; h < 24; h += 1) s += Number(row[h] || 0)
  }
  return s / 5
})

const weekendAvg = computed(() => {
  if (!matrix.value) return 0
  let s = 0
  for (let w = 5; w < 7; w += 1) {
    const row = matrix.value[w]
    if (!Array.isArray(row)) continue
    for (let h = 0; h < 24; h += 1) s += Number(row[h] || 0)
  }
  return s / 2
})

const tugVisible = computed(() => weekdayAvg.value > 0 || weekendAvg.value > 0)
const tugWdPct = computed(() => {
  const a = weekdayAvg.value
  const b = weekendAvg.value
  if (a + b <= 0) return 50
  return Math.round((a * 100) / (a + b))
})
const tugRatioText = computed(() => {
  if (weekendAvg.value > 0) return `${(weekdayAvg.value / weekendAvg.value).toFixed(1)} : 1`
  return weekdayAvg.value > 0 ? '全在工作日' : '—'
})

// ---------- 时刻星钉：晨光最早 / 一天最晚 ----------

const earliestSent = computed(() => {
  const o = props.card?.data?.earliestSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const latestSent = computed(() => {
  const o = props.card?.data?.latestSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const pinHover = ref(null)

// 星钉弹层贴边留白（%）。弹层 max-width 270px + translateX(-50%)，窄画幅下
// 12% 的老留白不足以兜住半个弹层（900px 宽时 12% 只有 108px < 135px），会切掉半句话。
// 取「半个弹层 + 16px 余量」换算成百分比，与 12% 取大者：1600px 设计宽下恒等于 12。
const tipEdgePct = computed(() => {
  const w = Math.max(1, Number(stage.design.value?.w) || 1600)
  return Math.max(12, Math.min(40, ((270 / 2 + 16) / w) * 100))
})

const pins = computed(() => {
  void terrainVer.value
  const list = []
  const push = (key, label, m, silver) => {
    if (!m || !m.time) return
    const hf = _hourFloatOf(m.time)
    if (hf === null) return
    list.push({ key, label, hf, silver, time: m.time, date: _formatDateLabel(m.date), who: m.displayName, text: trimText(m.content) })
  }
  push('dawn', '晨光里最早的一条', earliestSent.value, false)
  push('late', '一天中最晚的一条', latestSent.value, true)

  // 两枚星钉几乎同角度时错开一点，避免重叠
  if (list.length === 2 && Math.abs(list[0].hf - list[1].hf) < 0.7) {
    list[0].hf = Math.max(0.05, list[0].hf - 0.4)
    list[1].hf = Math.min(23.95, list[1].hf + 0.4)
  }

  const pad = tipEdgePct.value
  return list.map((p) => {
    const xPct = xPctOf(p.hf)
    const hi = Math.max(0, Math.min(23, Math.floor(p.hf)))
    // 与 scrubCursor 同一把尺：terTotal 是 JS/CSS 共用的唯一真源
    const bottomPx = terTotal.value - terYOf(shownHeights[hi]) + 10
    return {
      ...p,
      xPct: +xPct.toFixed(2),
      bottomPx: Math.round(bottomPx),
      tipLeftPct: +Math.max(pad, Math.min(100 - pad, xPct)).toFixed(2)
    }
  })
})

const activePin = computed(() => pins.value.find((p) => p.key === pinHover.value) || null)

const onPinEnter = (p) => {
  pinHover.value = p.key
  hoverScrub(p.hf)
}

const onPinLeave = () => {
  pinHover.value = null
  onHoverRelease()
}

// ---------- 深夜守夜人 ----------

const nightCompanion = computed(() => {
  const o = props.card?.data?.nightCompanion
  return o && typeof o === 'object' ? o : null
})

const nightPartner = computed(() => {
  const p = nightCompanion.value?.partner
  return p && typeof p === 'object' && typeof p.displayName === 'string' ? p : null
})

const nightMoment = computed(() => {
  const m = nightCompanion.value?.latestMoment
  return m && typeof m === 'object' && typeof m.time === 'string' ? m : null
})

const nightTotal = computed(() => Number(nightCompanion.value?.nightMessagesTotal || 0))
const nightShare = computed(() => Number(nightPartner.value?.sharePct || 0))
const nightMomentDateLabel = computed(() => _formatDateLabel(nightMoment.value?.date))

const nightOpen = ref(false)

const onDocPointerDown = () => {
  if (nightOpen.value) nightOpen.value = false
  if (pinHover.value) pinHover.value = null
}

const apiBase = useApiBase()
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    // qpic/qlogo 常有防盗链；与聊天页一致走后端代理。
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw.startsWith('/') ? raw : `/${raw}`
}

const nightPartnerAvatarUrl = computed(() => resolveMediaUrl(nightPartner.value?.avatarUrl))
const nightAvatarOk = ref(true)

const { display: nightSharePctDisplay, restart: restartNightShare, finish: finishNightShare } = useCountUp(
  () => nightIndexPct.value,
  { duration: 1.4, delay: 1.5, decimals: 1 }
)

// 弹层里的小星空：LCG 稳定生成
const popStars = computed(() => {
  let seed = ((nightTotal.value + 101) * 1103515245) % 2147483647
  if (seed <= 0) seed = 424242
  const rand = () => {
    seed = (seed * 48271) % 2147483647
    return seed / 2147483647
  }
  const stars = []
  for (let i = 0; i < 14; i += 1) {
    const size = 1.2 + rand() * 1.6
    stars.push({
      left: `${(rand() * 94 + 3).toFixed(2)}%`,
      top: `${(rand() * 82 + 6).toFixed(2)}%`,
      width: `${size.toFixed(1)}px`,
      height: `${size.toFixed(1)}px`,
      animationDelay: `${(rand() * 2.4).toFixed(2)}s`,
      animationDuration: `${(1.8 + rand() * 2).toFixed(2)}s`
    })
  }
  return stars
})

// ---------- 背景星空（数量随深夜消息量，LCG 保证稳定） ----------

const reducedMotion = useReducedMotion()

/* 导出模式（页面级 provide）。为真期间这一页必须**立刻**是终态：
   光线已经扫到峰值、山脊已经长齐、读数已经落定，而不是还停在入场那 4 秒的夜色里。
   为假时行为与导出功能存在之前一字不差。
   flatMotion 比 exportMode 多包一帧「还原中」：退出导出把这一页收回夜色时，
   同样不该看见那串 0.7~3.2s 的 CSS 过渡倒着放一遍。 */
const exportMode = inject('wrappedExportMode', ref(false))
const exportRestoring = ref(false)
const flatMotion = computed(() => exportMode.value || exportRestoring.value)

const nightStars = computed(() => {
  const total = nightTotal.value || allHoursTotal.value
  let count = 26
  if (total >= 1000) count = 64
  else if (total >= 300) count = 52
  else if (total >= 100) count = 40
  else if (total >= 20) count = 32

  let seed = ((total + 7) * 2654435761) % 2147483647
  if (seed <= 0) seed = 12345
  const rand = () => {
    seed = (seed * 48271) % 2147483647
    return seed / 2147483647
  }

  const stars = []
  for (let i = 0; i < count; i += 1) {
    const size = 1 + rand() * 1.9
    stars.push({
      left: `${(rand() * 97 + 1.5).toFixed(2)}%`,
      top: `${(rand() * 66 + 2).toFixed(2)}%`,
      width: `${size.toFixed(1)}px`,
      height: `${size.toFixed(1)}px`,
      opacity: (0.35 + rand() * 0.65).toFixed(2),
      animationDelay: `${(rand() * 3.2).toFixed(2)}s`,
      animationDuration: `${(2.2 + rand() * 2.6).toFixed(2)}s`
    })
  }
  return stars
})

// 亮星：四芒闪，位置由 LCG 定
const glintStars = computed(() => {
  let seed = ((nightTotal.value + 31) * 69069) % 2147483647
  if (seed <= 0) seed = 777
  const rand = () => {
    seed = (seed * 48271) % 2147483647
    return seed / 2147483647
  }
  const out = []
  for (let i = 0; i < 3; i += 1) {
    const size = 10 + rand() * 8
    out.push({
      left: `${(8 + rand() * 84).toFixed(2)}%`,
      top: `${(5 + rand() * 40).toFixed(2)}%`,
      width: `${size.toFixed(1)}px`,
      height: `${size.toFixed(1)}px`,
      animationDelay: `${(rand() * 4).toFixed(2)}s`
    })
  }
  return out
})

// ---------- 入场：每次翻到本页重播 ----------

const entered = ref(false)
let startTimer = 0
let resetTimer = 0

const playEntry = () => {
  entered.value = true
  restartReadout()
  restartNightShare()
  // 光线从峰值前 20 小时扫入：整段昼夜在入场时走一遍
  const target = dialPeakHour.value + 0.5
  killPhaseTween()
  phase.value = target - 20
  tweenPhaseTo(target, { duration: 3.1, ease: 'power2.inOut', delay: 0.5, direct: true })
  // 山脊跟着光线从西向东长出来
  morphHeightsTo(targetHeights.value, { duration: 1.05, stagger: 0.05, ease: 'power3.out' })
}

// 收回夜色：入场前的那一帧（原本只在翻走 750ms 后跑，导出还原也走同一条）
const resetToNight = () => {
  entered.value = false
  nightOpen.value = false
  pinHover.value = null
  selHourF.value = null
  weekdaySel.value = -1
  killPhaseTween()
  killHeightTweens()
  // 复位到峰值前 20 小时的夜色，下次翻入重播整段昼夜
  phase.value = dialPeakHour.value + 0.5 - 20
  setHeightsNow(Array.from({ length: 24 }, () => 0))
}

const settleInstant = () => {
  // 入场长扫可能正在飞（导出是从半截里接手的）：不掐掉它，phase 会被 onUpdate 一路改回去
  killPhaseTween()
  entered.value = true
  phase.value = targetHourF.value
  setHeightsNow(targetHeights.value)
  finishReadout()
  finishNightShare()
}

watch(
  () => props.isActive,
  (active) => {
    if (typeof window === 'undefined') {
      settleInstant()
      return
    }
    if (startTimer) { window.clearTimeout(startTimer); startTimer = 0 }
    if (resetTimer) { window.clearTimeout(resetTimer); resetTimer = 0 }
    if (!active) {
      resetTimer = window.setTimeout(() => {
        resetTimer = 0
        resetToNight()
      }, 750)
      return
    }
    // 导出模式与 reduced 走同一条：翻到本页立刻是终态，不等那 450ms + 4s 长扫
    if (reducedMotion.value || exportMode.value) {
      settleInstant()
      return
    }
    if (entered.value) return
    startTimer = window.setTimeout(() => {
      startTimer = 0
      playEntry()
    }, 450)
  },
  { immediate: true }
)

/* 导出模式：进去立刻把整段昼夜走完，出来还原成进入导出前的样子。
   —— 还原必须真的还原：这一页的主体验就是「光从夜里扫过来、山脊跟着长出来」，
      用户导出一次再回来看见的若是已经落定的白昼，这段就被剧透了。
   放在 isActive 那条 watch 之后，immediate 才能在「导出已经打开时才挂载」的情况下
   直接落到终态。
   种子值不能等 watch 回调来填：isActive 那条 watch 的 immediate 先跑，
   它会在导出已开时直接把 entered 置真，晚一步再拍快照就把「没入场过」记成了「入场过」。 */
let exportSnapshot = exportMode.value ? { entered: false } : null

watch(exportMode, (on) => {
  if (typeof window === 'undefined') return

  if (on) {
    if (exportSnapshot) return
    exportSnapshot = { entered: entered.value }
    if (startTimer) { window.clearTimeout(startTimer); startTimer = 0 }
    if (resetTimer) { window.clearTimeout(resetTimer); resetTimer = 0 }
    if (props.isActive) settleInstant()
    return
  }

  const snap = exportSnapshot
  exportSnapshot = null
  if (!snap) return
  // 导出前本来就入场过了：保持终态，别把用户的进度抹回夜色
  if (snap.entered) return

  // 还原同样不播动画：这一帧把那串 0.7~3.2s 的过渡关掉，直接跳回夜色
  exportRestoring.value = true
  if (startTimer) { window.clearTimeout(startTimer); startTimer = 0 }
  if (resetTimer) { window.clearTimeout(resetTimer); resetTimer = 0 }
  resetToNight()
  // 用户正停在本页：按没进过导出时的路子重新播一遍整段昼夜
  if (props.isActive && !reducedMotion.value) {
    startTimer = window.setTimeout(() => {
      startTimer = 0
      playEntry()
    }, 450)
  } else if (props.isActive) {
    settleInstant()
  }
  nextTick(() => { exportRestoring.value = false })
}, { immediate: true })

onMounted(() => {
  if (typeof document !== 'undefined') document.addEventListener('pointerdown', onDocPointerDown)
})

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('pointerdown', onDocPointerDown)
  killPhaseTween()
  killHeightTweens()
  if (typeof window === 'undefined') return
  if (startTimer) window.clearTimeout(startTimer)
  if (resetTimer) window.clearTimeout(resetTimer)
})

// ---------- 年度地平线 ----------

const yearFirstSent = computed(() => {
  const o = props.card?.data?.yearFirstSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const yearLastSent = computed(() => {
  const o = props.card?.data?.yearLastSent
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const yearFirstDateLabel = computed(() => _formatDateLabel(yearFirstSent.value?.date))
const yearLastDateLabel = computed(() => _formatDateLabel(yearLastSent.value?.date))
</script>

<style scoped>
/* ================= 舞台 ================= */

/* slide：absolute inset-0 直接铺满 slide（bleed 模式无 FitScale，可用高度怎么变都无缝） */
/* ⚠️ --ter-h / --ground-h / --ter-total 由 script 的 skyVars 下发到外壳根节点，往下继承进来。
   这里**不要**再写一份数字：CSS 与 JS 各写一份正是星钉/发丝线偏 16px 的老病根。 */
.sk-stage {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.sk-stage.sk--panel {
  position: relative;
  inset: auto;
  width: 100%;
  aspect-ratio: 16 / 8.6;
  min-height: 460px;
  border-radius: 18px;
}

/* ================= 天空 ================= */

.sk-sky {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    var(--sky-a, #04060f) 0%,
    var(--sky-b, #0a0f22) 40%,
    var(--sky-c, #111931) 72%,
    var(--sky-d, #18203c) 100%
  );
}

/* 星空 */
.sk-stars {
  position: absolute;
  inset: 0;
  opacity: var(--star-alpha, 1);
  pointer-events: none;
  /* 地平线附近有大气霭，星星淡出 */
  mask-image: linear-gradient(180deg, #000 0%, #000 62%, transparent 88%);
  -webkit-mask-image: linear-gradient(180deg, #000 0%, #000 62%, transparent 88%);
}

.sk-star {
  position: absolute;
  border-radius: 9999px;
  background: #ffffff;
  animation: sk-twinkle 2.8s ease-in-out infinite;
}

@keyframes sk-twinkle {
  0%, 100% { transform: scale(0.8); filter: brightness(0.7); }
  50% { transform: scale(1.15); filter: brightness(1.3); }
}

.sk-glint {
  position: absolute;
  fill: rgba(255, 255, 255, 0.85);
  filter: drop-shadow(0 0 5px rgba(190, 210, 255, 0.8));
  animation: sk-glint-breathe 5.5s ease-in-out infinite;
}

@keyframes sk-glint-breathe {
  0%, 100% { transform: scale(0.75); opacity: 0.5; }
  50% { transform: scale(1.05); opacity: 1; }
}

.sk--still .sk-star,
.sk--still .sk-glint { animation-play-state: paused; }
.sk--reduced .sk-star,
.sk--reduced .sk-glint { animation: none; }

/* 晨昏方位光：跟着太阳的横坐标贴地生长 */
.sk-azglow {
  position: absolute;
  left: var(--az-x, 50%);
  bottom: calc(var(--ground-h) - 30px);
  width: calc(var(--svw) * 96);
  height: calc(var(--svh) * 52);
  transform: translateX(-50%);
  background: radial-gradient(
    52% 100% at 50% 100%,
    rgba(255, 168, 92, 0.62),
    rgba(255, 140, 90, 0.2) 46%,
    transparent 76%
  );
  opacity: var(--az-a, 0);
  pointer-events: none;
  mix-blend-mode: screen;
}

/* 平流雾 */
.sk-mist {
  position: absolute;
  left: -8%;
  right: -8%;
  pointer-events: none;
  filter: blur(26px);
  opacity: calc(var(--mist-a, 0) * 0.5);
  mix-blend-mode: screen;
}

.sk-mist--a {
  bottom: calc(var(--ground-h) + 40px);
  height: 90px;
  background: linear-gradient(90deg, transparent, rgba(214, 204, 224, 0.32) 30%, rgba(230, 214, 210, 0.4) 55%, transparent 90%);
}

.sk-mist--b {
  bottom: calc(var(--ground-h) - 6px);
  height: 60px;
  background: linear-gradient(90deg, transparent 6%, rgba(196, 196, 226, 0.3) 45%, rgba(214, 202, 220, 0.24) 70%, transparent);
}

/* ================= 日月 ================= */

.sk-sun,
.sk-moon {
  position: absolute;
  left: var(--sun-x, 50%);
  top: calc((100% - var(--ground-h)) * var(--sun-y, 0.3));
  width: 0;
  height: 0;
  pointer-events: none;
  opacity: var(--sun-a, 1);
}

.sk-moon {
  left: var(--moon-x, 50%);
  top: calc((100% - var(--ground-h)) * var(--moon-y, 0.3));
  opacity: var(--moon-a, 0);
}

.sk-sun i,
.sk-moon i {
  position: absolute;
  display: block;
  transform: translate(-50%, -50%);
  border-radius: 9999px;
}

.sk-sun-core {
  width: 30px;
  height: 30px;
  background: radial-gradient(circle at 40% 36%, #fffdf4 0%, #ffedb8 46%, #ffc76a 100%);
  box-shadow: 0 0 18px 4px rgba(255, 214, 130, 0.75);
}

.sk-sun-halo {
  width: 190px;
  height: 190px;
  background: radial-gradient(closest-side, rgba(255, 214, 138, 0.5), rgba(255, 190, 120, 0.16) 46%, transparent 74%);
  mix-blend-mode: screen;
}

.sk-sun-flare {
  width: 340px;
  height: 44px;
  border-radius: 9999px;
  background: radial-gradient(closest-side, rgba(255, 206, 138, 0.55), transparent 78%);
  mix-blend-mode: screen;
  opacity: var(--flare-a, 0);
}

.sk-moon-halo {
  width: 128px;
  height: 128px;
  background: radial-gradient(closest-side, rgba(214, 226, 255, 0.3), rgba(206, 220, 255, 0.09) 50%, transparent 75%);
  mix-blend-mode: screen;
}

.sk-moon-disc {
  width: 26px;
  height: 26px;
  background: radial-gradient(circle at 38% 34%, #fbfcff 0%, #e6ebf6 52%, #c2cadd 100%);
  box-shadow: 0 0 14px 3px rgba(206, 222, 255, 0.55);
  overflow: hidden;
}

.sk-moon-shade {
  position: absolute;
  right: -22%;
  top: -14%;
  width: 82%;
  height: 82%;
  border-radius: 9999px;
  background: rgba(94, 106, 138, 0.34);
  filter: blur(3px);
}

.sk-moon-crater {
  position: absolute;
  border-radius: 9999px;
  background: rgba(128, 138, 168, 0.4);
}

.sk-moon-crater--a { left: 22%; top: 30%; width: 22%; height: 22%; }
.sk-moon-crater--b { left: 52%; top: 56%; width: 14%; height: 14%; }
.sk-moon-crater--c { left: 38%; top: 14%; width: 10%; height: 10%; }

/* ================= 消息山脊 ================= */

.sk-terrain {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  /* = JS 的 terTotal（TER_H + groundH）。高度与 viewBox 恒等，1 个 viewBox 单位 = 1px，
     星钉 / 发丝线的 bottomPx 才能和山脊表面严丝合缝 */
  height: var(--ter-total, 338px);
  display: block;
  pointer-events: none;
}

.sk-ter-fill {
  fill: url(#skTerFill);
}

.sk-ter-rim {
  fill: none;
  stroke: var(--rim, #ffd98f);
  stroke-width: 1.6;
  stroke-linecap: round;
  opacity: 0.9;
  filter: drop-shadow(0 0 6px var(--rim-soft, rgba(255, 217, 143, 0.55)));
}

.sk-ter-dot {
  fill: var(--rim, #ffd98f);
  stroke: rgba(255, 255, 255, 0.85);
  stroke-width: 1;
  filter: drop-shadow(0 0 6px var(--rim-soft, rgba(255, 217, 143, 0.55)));
}

/* 掠时层 + 测量发丝线 */
.sk-scrub {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: var(--ground-h);
  z-index: 20;
  cursor: crosshair;
  touch-action: none;
  -webkit-tap-highlight-color: transparent;
  outline: none;
}

.sk-hairline {
  position: absolute;
  left: var(--scrub-x, 50%);
  top: 118px;
  bottom: calc(var(--ground-h) - 1px);
  width: 1px;
  background: linear-gradient(180deg, transparent, var(--ink-3, rgba(243, 246, 255, 0.45)) 24%, var(--ink-3, rgba(243, 246, 255, 0.45)) 86%, transparent);
  opacity: 0;
  transition: opacity 0.25s ease;
  pointer-events: none;
  z-index: 8; /* 沉到判词/读数文字之下，掠过时不压字 */
}

.sk-hairline--on { opacity: 0.55; }

/* ================= 星钉 ================= */

.sk-pin {
  position: absolute;
  z-index: 25;
  width: 26px;
  height: 26px;
  margin-left: -13px;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  opacity: 0;
  transition: opacity 0.5s ease 2.6s, bottom 0.4s ease;
}

.sk--in .sk-pin { opacity: 1; }

.sk-pin svg {
  width: 14px;
  height: 14px;
  margin: 6px;
  fill: #ffd666;
  filter: drop-shadow(0 0 5px rgba(255, 214, 102, 0.65));
  transition: transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.sk-pin--silver svg {
  fill: #c9d4f2;
  filter: drop-shadow(0 0 5px rgba(178, 195, 240, 0.7));
}

.sk-pin--hot svg { transform: scale(1.4); }

.sk-pin-tip {
  position: absolute;
  z-index: 40;
  transform: translateX(-50%);
  width: max-content;
  max-width: 270px;
  background: rgba(11, 17, 38, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(6px);
  padding: 10px 12px;
  pointer-events: none;
}

/* ================= 文字层容器 ================= */

/* 默认不生成盒：页头/判词/读数照旧各自 absolute 贴边定位，与舞台化之前逐像素一致。
   只有竖幅分支才把它变成真正的纵向流容器（见文末「竖幅重排」）。 */
.sk-column {
  display: contents;
}

/* ================= 页头 ================= */

.sk-head {
  position: absolute;
  z-index: 10;
  left: clamp(24px, calc(var(--svw) * 4.5), 72px);
  right: clamp(24px, calc(var(--svw) * 4.5), 72px);
  top: clamp(40px, calc(var(--svh) * 6.5), 64px);
  pointer-events: none;
}

.sk-title {
  font-size: clamp(1.35rem, calc(var(--svw) * 2), 1.8rem);
  color: var(--ink, #f3f6ff);
  transition: color 0.2s linear;
}

.sk-nar {
  margin-top: 10px;
  max-width: 46rem;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2, rgba(243, 246, 255, 0.72));
  transition: color 0.2s linear;
}

.sk-em {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--ink, #f3f6ff);
}

/* 页头入场 */
.sk-head { opacity: 0; transform: translateY(8px); transition: opacity 0.7s ease 0.15s, transform 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.15s, color 0.2s linear; }
.sk--in .sk-head { opacity: 1; transform: none; }

/* ================= 判词 ================= */

.sk-verdict {
  position: absolute;
  z-index: 10;
  left: clamp(24px, calc(var(--svw) * 4.5), 72px);
  top: clamp(158px, calc(var(--svh) * 24), 218px);
  max-width: min(calc(var(--svw) * 46), 560px);
  pointer-events: none;
}

.sk-kicker {
  font-size: 10px;
  letter-spacing: 0.22em;
  color: var(--ink-3, rgba(243, 246, 255, 0.45));
  opacity: 0;
  transition: opacity 0.6s ease 2.45s, color 0.2s linear;
}

.sk--in .sk-kicker { opacity: 1; }

.sk-word {
  margin-top: 10px;
  font-size: clamp(2.6rem, calc(var(--svw) * 5.2), 4.1rem);
  line-height: 1.08;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: var(--ink, #f3f6ff);
  text-shadow: 0 0 34px var(--rim-soft, rgba(255, 217, 143, 0.4));
  opacity: 0;
  transform: translateY(14px);
  filter: blur(10px);
  transition:
    opacity 0.8s ease 2.6s,
    transform 0.9s cubic-bezier(0.22, 1, 0.36, 1) 2.6s,
    filter 0.9s ease 2.6s,
    letter-spacing 1.1s cubic-bezier(0.22, 1, 0.36, 1) 2.6s,
    color 0.2s linear;
}

.sk--in .sk-word {
  opacity: 1;
  transform: none;
  filter: blur(0);
  letter-spacing: 0.06em;
}

.sk-word-sub {
  margin-top: 12px;
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--ink-2, rgba(243, 246, 255, 0.72));
  opacity: 0;
  transition: opacity 0.7s ease 3s, color 0.2s linear;
}

.sk-word-echo {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--ink-3, rgba(243, 246, 255, 0.45));
  opacity: 0;
  transition: opacity 0.7s ease 3.2s, color 0.2s linear;
}

.sk--in .sk-word-sub,
.sk--in .sk-word-echo { opacity: 1; }

.sk-token {
  font-weight: 600;
  color: var(--ink, #f3f6ff);
  transition: color 0.2s linear;
}

/* ================= 时刻仪表（右） ================= */

.sk-readout {
  position: absolute;
  /* 高于掠时层（z20）：文字 pointer-events none 不挡掠动，星期拨片才收得到点击 */
  z-index: 22;
  right: clamp(24px, calc(var(--svw) * 4.5), 72px);
  top: clamp(150px, calc(var(--svh) * 22), 206px);
  text-align: right;
  pointer-events: none;
  max-width: 300px;
}

.sk-ro-scope {
  font-size: 10px;
  letter-spacing: 0.2em;
  color: var(--ink-3, rgba(243, 246, 255, 0.45));
  transition: color 0.2s linear;
}

.sk-ro-hour {
  margin-top: 2px;
  font-size: clamp(3rem, calc(var(--svw) * 5.4), 4.4rem);
  font-weight: 200;
  line-height: 1.05;
  letter-spacing: 0.02em;
  color: var(--ink, #f3f6ff);
  font-variant-numeric: tabular-nums;
  transition: color 0.2s linear;
}

.sk-ro-hour i {
  font-style: normal;
  font-weight: 100;
  opacity: 0.55;
}

.sk-ro-count {
  margin-top: 2px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink, #f3f6ff);
  font-variant-numeric: tabular-nums;
  transition: color 0.2s linear;
}

.sk-ro-count i {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: var(--ink-3, rgba(243, 246, 255, 0.45));
  margin-right: 6px;
}

.sk-ro-count em {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: var(--ink-3, rgba(243, 246, 255, 0.45));
}

.sk-ro-care {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-2, rgba(243, 246, 255, 0.72));
  transition: color 0.2s linear;
}

.sk-readout { opacity: 0; transform: translateY(8px); transition: opacity 0.7s ease 1.15s, transform 0.7s cubic-bezier(0.22, 1, 0.36, 1) 1.15s; }
.sk--in .sk-readout { opacity: 1; transform: none; }

/* ================= 星期拨片（读数区内右对齐） ================= */

.sk-chips {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 5px;
  pointer-events: auto;
}

.sk-chip {
  min-width: 30px;
  padding: 3px 8px;
  border-radius: 9999px;
  border: 1px solid color-mix(in srgb, var(--ink, #f3f6ff) 22%, transparent);
  background: color-mix(in srgb, var(--ink, #f3f6ff) 5%, transparent);
  color: var(--ink-2, rgba(243, 246, 255, 0.72));
  font-size: 10px;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease, opacity 0.45s ease var(--chip-d, 1.4s), transform 0.45s ease var(--chip-d, 1.4s);
  -webkit-tap-highlight-color: transparent;
  opacity: 0;
  transform: translateY(6px);
}

.sk--in .sk-chip { opacity: 1; transform: none; }

.sk-chip:hover {
  border-color: color-mix(in srgb, var(--rim, #ffd98f) 60%, transparent);
  color: var(--ink, #f3f6ff);
}

.sk-chip--on {
  border-color: color-mix(in srgb, var(--rim, #ffd98f) 75%, transparent);
  background: color-mix(in srgb, var(--rim, #ffd98f) 16%, transparent);
  color: var(--ink, #f3f6ff);
  font-weight: 600;
}

/* ================= 大地仪表带 ================= */

/* 大地仪表带：不再自带底色——山体填充就是它的大地，仪表直接刻在山体上 */
.sk-ground {
  position: absolute;
  z-index: 24;
  left: 0;
  right: 0;
  bottom: 0;
  height: var(--ground-h);
}

/* 日月在地平线上的反光拉丝 */
.sk-ground-sheen {
  position: absolute;
  left: var(--az-x, 50%);
  top: -12px;
  width: 240px;
  height: 110%;
  transform: translateX(-50%);
  background: radial-gradient(46% 58% at 50% 8%, rgba(255, 190, 120, 0.34), rgba(255, 190, 120, 0.05) 55%, transparent 78%);
  filter: blur(10px);
  opacity: calc(var(--az-a, 0) * 0.45);
  mix-blend-mode: screen;
  pointer-events: none;
}

/* 仪表行 */
.sk-inst {
  position: relative;
  z-index: 1;
  height: calc(var(--ground-h) - 34px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: clamp(14px, calc(var(--svw) * 2), 30px);
  padding: 0 clamp(24px, calc(var(--svw) * 4.5), 72px);
}

.sk-cluster-wrap {
  position: relative;
  min-width: 0;
}

.sk-inst-rule {
  width: 1px;
  align-self: stretch;
  margin: 20px 0;
  background: linear-gradient(180deg, transparent, rgba(255, 255, 255, 0.1) 30%, rgba(255, 255, 255, 0.1) 70%, transparent);
  flex: 0 0 auto;
}

.sk-cluster {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 0;
  border: none;
  background: none;
  text-align: left;
  color: inherit;
  font: inherit;
  opacity: 0;
  transform: translateY(9px);
  transition: opacity 0.55s ease var(--inst-d, 1.5s), transform 0.55s ease var(--inst-d, 1.5s);
}

.sk--in .sk-cluster { opacity: 1; transform: none; }

.sk-cluster--night {
  flex-direction: row;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.sk-cl-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.sk-cl-label {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 10px;
  letter-spacing: 0.16em;
  color: #93a3cc;
  white-space: nowrap;
}

.sk-cl-value {
  font-size: 17px;
  font-weight: 650;
  letter-spacing: 0;
  color: #f4f7ff;
  font-style: normal;
  font-variant-numeric: tabular-nums;
}

.sk-cluster--night .sk-cl-value { color: #ffe9a3; }

.sk-cl-note {
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.5);
  white-space: nowrap;
}

.sk-cl-note b {
  font-weight: 500;
  color: rgba(255, 255, 255, 0.78);
}

.sk-cl-note--row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.sk-cl-ellip {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sk-chevron {
  width: 10px;
  height: 10px;
  color: #93a3cc;
  flex-shrink: 0;
  transition: transform 0.2s ease, color 0.2s ease;
}

.sk-cluster--open .sk-chevron {
  transform: rotate(90deg);
  color: #ffe9a3;
}

/* 光谱小仪 */
.sk-spectrum {
  display: flex;
  align-items: center;
  gap: 8px;
  width: clamp(150px, calc(var(--svw) * 13), 210px);
}

.sk-sp-glyph {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
}

.sk-sp-glyph:first-child { color: #ffd66e; }
.sk-sp-glyph:last-child { color: #b9c9f2; }

.sk-sp-bar {
  position: relative;
  flex: 1;
  height: 3px;
  border-radius: 9999px;
  background: linear-gradient(90deg, #ffd66e 0%, #c98d8a 45%, #7d7ab8 70%, #4a5490 100%);
  opacity: 0.9;
}

.sk-sp-marker {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 11px;
  height: 11px;
  border-radius: 9999px;
  transform: translate(-50%, -50%);
  background: #ffffff;
  border: 2.5px solid rgba(6, 9, 20, 0.9);
  box-shadow: 0 0 9px 2px rgba(255, 255, 255, 0.4);
  transition: left 1s cubic-bezier(0.22, 1, 0.36, 1) 1.9s;
}

.sk-stage:not(.sk--in) .sk-sp-marker { left: 50% !important; }

/* 工作日 / 周末比例尺 */
.sk-meter {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 3px;
  width: clamp(130px, calc(var(--svw) * 11), 190px);
}

.sk-meter i {
  display: block;
  height: 100%;
  border-radius: 999px;
  flex-basis: 0;
  transition: flex-grow 0.8s cubic-bezier(0.22, 1, 0.36, 1) 2s;
}

.sk-meter__wd { background: #07c160; }
.sk-meter__we { background: rgba(242, 170, 0, 0.65); }

.sk-stage:not(.sk--in) .sk-meter i { flex-grow: 1 !important; }

/* 守夜人头像 */
.sk-night-avatar {
  width: 46px;
  height: 46px;
  border-radius: 9999px;
  overflow: hidden;
  flex-shrink: 0;
  background: #ffe9a3;
  border: 1.5px solid rgba(255, 233, 163, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 0 16px 3px rgba(255, 233, 163, 0.28),
    0 0 40px 8px rgba(255, 233, 163, 0.08);
  transition: box-shadow 0.25s ease, border-color 0.25s ease;
}

.sk-night-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.sk-night-avatar-fb {
  font-size: 19px;
  color: rgba(0, 0, 0, 0.55);
}

.sk-cluster--night:hover .sk-night-avatar,
.sk-cluster--open .sk-night-avatar {
  border-color: rgba(255, 233, 163, 0.9);
  box-shadow:
    0 0 22px 6px rgba(255, 233, 163, 0.4),
    0 0 56px 14px rgba(255, 233, 163, 0.14);
}

/* 年度地平线 */
.sk-yearline {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 clamp(24px, calc(var(--svw) * 4.5), 72px);
  opacity: 0;
  transition: opacity 0.7s ease 2.1s;
}

.sk--in .sk-yearline { opacity: 1; }

.sk-yl-end {
  display: flex;
  align-items: baseline;
  gap: 8px;
  cursor: default;
  flex-shrink: 0;
}

.sk-yl-cap {
  font-size: 9px;
  letter-spacing: 0.1em;
  color: #7f8db2;
}

.sk-yl-val {
  font-size: 11.5px;
  font-weight: 600;
}

.sk-yl-val--gold { color: #ffe9a3; }
.sk-yl-val--silver { color: #b9c4e4; }

.sk-yl-line {
  position: relative;
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(255, 233, 163, 0.55), rgba(255, 255, 255, 0.1) 40%, rgba(255, 255, 255, 0.1) 60%, rgba(185, 196, 228, 0.5));
}

.sk-yl-line::before,
.sk-yl-line::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 5px;
  height: 5px;
  border-radius: 9999px;
  transform: translateY(-50%);
}

.sk-yl-line::before {
  left: 0;
  background: #ffe9a3;
  box-shadow: 0 0 10px 2px rgba(255, 233, 163, 0.5);
}

.sk-yl-line::after {
  right: 0;
  background: #b9c4e4;
  box-shadow: 0 0 10px 2px rgba(185, 196, 228, 0.45);
}

/* ================= 弹层 ================= */

.sk-night-pop {
  position: absolute;
  z-index: 40;
  left: 0;
  bottom: calc(100% + 12px);
  width: max-content;
  max-width: 340px;
  overflow: hidden;
  background:
    radial-gradient(circle at 86% 12%, rgba(255, 233, 163, 0.1), transparent 42%),
    rgba(11, 17, 38, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(6px);
  padding: 10px 12px;
}

.sk-pop-star {
  position: absolute;
  z-index: 0;
  --star-alpha: 1;
}

.sk-night-pop > :not(.sk-pop-star) {
  position: relative;
  z-index: 1;
}

.sk-pop-enter-active,
.sk-pop-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.sk-pop-enter-from,
.sk-pop-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* 聊天气泡 */
.sk-bubble {
  position: relative;
  min-width: 0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  color: #1a1a1a;
  padding: 8px 12px;
  word-break: break-word;
}

.sk-bubble--sent { background: #95ec69; }

/* ================= 材质层 ================= */

.sk-grain {
  position: absolute;
  inset: 0;
  z-index: 28;
  pointer-events: none;
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj4KICA8ZmlsdGVyIGlkPSJuIj4KICAgIDxmZVR1cmJ1bGVuY2UgdHlwZT0iZnJhY3RhbE5vaXNlIiBiYXNlRnJlcXVlbmN5PSIwLjkiIG51bU9jdGF2ZXM9IjUiIHN0aXRjaFRpbGVzPSJzdGl0Y2giLz4KICAgIDxmZUNvbG9yTWF0cml4IHR5cGU9InNhdHVyYXRlIiB2YWx1ZXM9IjAiLz4KICA8L2ZpbHRlcj4KICA8cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsdGVyPSJ1cmwoI24pIiBvcGFjaXR5PSIwLjUiLz4KPC9zdmc+");
  background-repeat: repeat;
  background-size: 190px 190px;
  mix-blend-mode: overlay;
  opacity: 0.05;
}

.sk-vignette {
  position: absolute;
  inset: 0;
  z-index: 28;
  pointer-events: none;
  background: radial-gradient(84% 74% at 50% 44%, rgba(0, 0, 0, 0) 52%, rgba(2, 4, 12, 0.62) 100%);
  opacity: var(--vig-a, 0.4);
}

/* ================= 空状态 ================= */

.sk-empty {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
}

.sk-empty-horizon {
  position: relative;
  width: min(420px, 70%);
  height: 40px;
}

.sk-empty-horizon::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.22) 30%, rgba(255, 255, 255, 0.22) 70%, transparent);
}

.sk-empty-horizon i {
  position: absolute;
  left: 50%;
  bottom: -13px;
  width: 26px;
  height: 26px;
  transform: translateX(-50%);
  border-radius: 9999px;
  background: radial-gradient(circle at 40% 36%, #fffdf4 0%, #ffedb8 46%, #ffc76a 100%);
  box-shadow: 0 0 18px 4px rgba(255, 214, 130, 0.5);
  clip-path: inset(0 0 50% 0);
}

/* ================================================================
   画幅重排（tier=wide 即 16:9 / 跟随窗口不受任何影响：以下全部带 tier 前缀）
   面积恒定 ⇒ 构件尺寸一律保持 16:9 下的设计常量，只换排布。
   ================================================================ */

/* ---- 构件尺寸去掉宽度轴，改成 16:9 下的计算值（否则窄画幅会掉到 clamp 下限） ---- */

/* clamp(1.35rem, 2svw, 1.8rem) 在 1600px 宽下 = 1.8rem = 28.8px */
[data-frame-tier="landscape"] .sk-title,
[data-frame-tier="square"] .sk-title,
[data-frame-tier="portrait"] .sk-title,
[data-frame-tier="tall"] .sk-title {
  font-size: 28.8px;
}

/* clamp(2.6rem, 5.2svw, 4.1rem) → 4.1rem = 65.6px */
[data-frame-tier="landscape"] .sk-word,
[data-frame-tier="square"] .sk-word,
[data-frame-tier="portrait"] .sk-word,
[data-frame-tier="tall"] .sk-word {
  font-size: 65.6px;
}

/* clamp(3rem, 5.4svw, 4.4rem) → 4.4rem = 70.4px */
[data-frame-tier="landscape"] .sk-ro-hour,
[data-frame-tier="square"] .sk-ro-hour,
[data-frame-tier="portrait"] .sk-ro-hour,
[data-frame-tier="tall"] .sk-ro-hour {
  font-size: 70.4px;
}

/* 两条量条也是构件：clamp(150px, 13svw, 210px) → 208px；clamp(130px, 11svw, 190px) → 176px */
[data-frame-tier="landscape"] .sk-spectrum,
[data-frame-tier="square"] .sk-spectrum,
[data-frame-tier="portrait"] .sk-spectrum,
[data-frame-tier="tall"] .sk-spectrum {
  width: 208px;
}

[data-frame-tier="landscape"] .sk-meter,
[data-frame-tier="square"] .sk-meter,
[data-frame-tier="portrait"] .sk-meter,
[data-frame-tier="tall"] .sk-meter {
  width: 176px;
}

/* ---- 竖幅：左判词 / 右读数 → 纵向四段流 ----
   判词（上）→ 读数（贴着地平线）→ 日月山脊 → 仪表带（下）。
   .sk-column 从 display:contents 变成真容器；三块文字改回普通流。 */

[data-frame-tier="portrait"] .sk-column,
[data-frame-tier="tall"] .sk-column {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  /* 底边停在山脊画布上沿之上 10px：读数贴着地平线，不压山峰 */
  bottom: calc(var(--ter-total, 338px) + 10px);
  /* 原本挂在 .sk-readout 上的 z22（要高于掠时层 z20，星期拨片才收得到点击）
     现在由容器承担——容器一旦成盒就会建层叠上下文，子级的 z22 会被关进来 */
  z-index: 22;
  gap: 22px;
  padding-top: clamp(40px, calc(var(--svh) * 6.5), 64px);
  padding-left: clamp(24px, calc(var(--svw) * 4.5), 72px);
  padding-right: clamp(24px, calc(var(--svw) * 4.5), 72px);
  pointer-events: none;
}

[data-frame-tier="portrait"] .sk-head,
[data-frame-tier="tall"] .sk-head,
[data-frame-tier="portrait"] .sk-verdict,
[data-frame-tier="tall"] .sk-verdict,
[data-frame-tier="portrait"] .sk-readout,
[data-frame-tier="tall"] .sk-readout {
  position: static;
  left: auto;
  right: auto;
  top: auto;
  z-index: auto;
  /* 判词不再是贴左的窄栏、读数不再是贴右的窄栏：整列通栏 */
  max-width: none;
}

/* 竖幅多出来的那截高度，先分一点给「页头 → 判词」的呼吸，而不是全甩给底下的空天。
   16:9 下这段间距实测 84px；竖幅按画面高度等比放开，封顶 130px。 */
[data-frame-tier="portrait"] .sk-verdict,
[data-frame-tier="tall"] .sk-verdict {
  margin-top: clamp(0px, calc(var(--svh) * 7 - 22px), 130px);
}

/* 读数被推到列底 —— 判词与页头抱团在上，中间留给日月弧线 */
[data-frame-tier="portrait"] .sk-readout,
[data-frame-tier="tall"] .sk-readout {
  margin-top: auto;
  text-align: left;
  /* 竖长的「时刻 / 条数 / 人话 / 拨片」四行折成仪表盘式两列，省下一半高度 */
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-areas:
    "scope scope"
    "hour  count"
    "hour  care"
    "chips chips";
  column-gap: 20px;
  align-items: start;
}

[data-frame-tier="portrait"] .sk-ro-scope,
[data-frame-tier="tall"] .sk-ro-scope { grid-area: scope; }

[data-frame-tier="portrait"] .sk-ro-hour,
[data-frame-tier="tall"] .sk-ro-hour { grid-area: hour; align-self: center; }

[data-frame-tier="portrait"] .sk-ro-count,
[data-frame-tier="tall"] .sk-ro-count { grid-area: count; align-self: end; }

[data-frame-tier="portrait"] .sk-ro-care,
[data-frame-tier="tall"] .sk-ro-care { grid-area: care; align-self: start; }

[data-frame-tier="portrait"] .sk-chips,
[data-frame-tier="tall"] .sk-chips {
  grid-area: chips;
  justify-content: flex-start;
  flex-wrap: wrap;
}

/* ---- 竖幅：四组仪表横排 780–900px 装不下 900/1040 的窗口，折成 2×2 ---- */

/* 仪表带定高 + 舞台 overflow:hidden = 长名字/多行注解会被切掉。
   竖幅下改成「不低于设计高度、需要时向上长」，一个字都不丢。 */
[data-frame-tier="portrait"] .sk-ground,
[data-frame-tier="tall"] .sk-ground {
  height: auto;
  min-height: var(--ground-h);
  padding-bottom: 12px;
}

[data-frame-tier="portrait"] .sk-inst,
[data-frame-tier="tall"] .sk-inst {
  display: grid;
  /* 中列留给竖发丝线，两侧各一组仪表 */
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  height: auto;
  align-items: center;
  column-gap: clamp(14px, calc(var(--svw) * 2), 30px);
  row-gap: 13px;
  padding-top: 16px;
}

[data-frame-tier="portrait"] .sk-inst-rule,
[data-frame-tier="tall"] .sk-inst-rule {
  margin: 2px 0;
}

/* 分隔线一根不丢，只是换朝向：第 4 个孩子正是两行之间那根，转成通栏横线，
   同时把后两组仪表挤到第 3 行，天然形成 2×2 + 十字发丝线 */
[data-frame-tier="portrait"] .sk-inst-rule:nth-child(4),
[data-frame-tier="tall"] .sk-inst-rule:nth-child(4) {
  grid-column: 1 / -1;
  width: auto;
  height: 1px;
  align-self: center;
  margin: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1) 30%, rgba(255, 255, 255, 0.1) 70%, transparent);
}

/* 栏一变窄就必须放开截断：nowrap / ellipsis 全部改成换行 */
[data-frame-tier="portrait"] .sk-cl-label,
[data-frame-tier="tall"] .sk-cl-label {
  flex-wrap: wrap;
  white-space: normal;
}

[data-frame-tier="portrait"] .sk-cl-note,
[data-frame-tier="tall"] .sk-cl-note {
  white-space: normal;
}

[data-frame-tier="portrait"] .sk-cl-note--row,
[data-frame-tier="tall"] .sk-cl-note--row {
  align-items: flex-start;
}

[data-frame-tier="portrait"] .sk-cl-ellip,
[data-frame-tier="tall"] .sk-cl-ellip {
  overflow: visible;
  text-overflow: clip;
}

[data-frame-tier="portrait"] .sk-chevron,
[data-frame-tier="tall"] .sk-chevron {
  margin-top: 3px;
}

/* 年度地平线跟在 2×2 之后（仪表带已改 height:auto） */
[data-frame-tier="portrait"] .sk-yearline,
[data-frame-tier="tall"] .sk-yearline {
  margin-top: 12px;
  flex-wrap: wrap;
  row-gap: 6px;
}

/* 守夜人弹层挂在右列，靠右开会顶出画外——改成向左展开 */
[data-frame-tier="portrait"] .sk-night-pop,
[data-frame-tier="tall"] .sk-night-pop {
  left: auto;
  right: 0;
  max-width: min(340px, calc(var(--svw) * 76));
}

/* ================================================================
   竖幅放大（tier=portrait / tall，即 3:4 / 4:5 / 9:16）
   —— 竖幅少了一半横向宽度，却多出一截高度：上面的重排已把「左判词 / 右读数」
   折成一列、把四组仪表折成 2×2，腾出的高度在这里换成排印密度。
   16:9（wide）与 landscape / square 不受任何影响：以下全部带 portrait / tall 前缀。
   字号一律写绝对 px：竖幅舞台变高时不能让字跟着高度轴涨。
   ================================================================ */

/* ---- 页头 ---- */
[data-frame-tier="portrait"] .sk-title,
[data-frame-tier="tall"] .sk-title {
  font-size: 46px;
  line-height: 1.24;
}

[data-frame-tier="portrait"] .sk-nar,
[data-frame-tier="tall"] .sk-nar {
  margin-top: 14px;
  font-size: 22px;
  line-height: 1.7;
  max-width: none;
}

/* ---- 判词 ---- */
[data-frame-tier="portrait"] .sk-kicker,
[data-frame-tier="tall"] .sk-kicker {
  font-size: 17px;
  letter-spacing: 0.18em;
}

[data-frame-tier="portrait"] .sk-word,
[data-frame-tier="tall"] .sk-word {
  margin-top: 14px;
  font-size: 92px;
}

[data-frame-tier="portrait"] .sk-word-sub,
[data-frame-tier="tall"] .sk-word-sub {
  margin-top: 18px;
  font-size: 24px;
  line-height: 1.72;
}

[data-frame-tier="portrait"] .sk-word-echo,
[data-frame-tier="tall"] .sk-word-echo {
  margin-top: 10px;
  font-size: 21px;
  line-height: 1.72;
}

/* ---- 时刻仪表 ---- */
[data-frame-tier="portrait"] .sk-ro-scope,
[data-frame-tier="tall"] .sk-ro-scope {
  font-size: 17px;
  letter-spacing: 0.16em;
}

[data-frame-tier="portrait"] .sk-ro-hour,
[data-frame-tier="tall"] .sk-ro-hour {
  font-size: 104px;
  font-weight: 250;
}

[data-frame-tier="portrait"] .sk-ro-count,
[data-frame-tier="tall"] .sk-ro-count {
  margin-top: 4px;
  font-size: 28px;
}

[data-frame-tier="portrait"] .sk-ro-count i,
[data-frame-tier="tall"] .sk-ro-count i,
[data-frame-tier="portrait"] .sk-ro-count em,
[data-frame-tier="tall"] .sk-ro-count em {
  font-size: 20px;
}

[data-frame-tier="portrait"] .sk-ro-care,
[data-frame-tier="tall"] .sk-ro-care {
  margin-top: 12px;
  font-size: 21px;
  line-height: 1.62;
}

[data-frame-tier="portrait"] .sk-readout,
[data-frame-tier="tall"] .sk-readout {
  column-gap: 26px;
}

/* ---- 星期拨片 ---- */
[data-frame-tier="portrait"] .sk-chips,
[data-frame-tier="tall"] .sk-chips {
  margin-top: 22px;
  gap: 8px;
}

[data-frame-tier="portrait"] .sk-chip,
[data-frame-tier="tall"] .sk-chip {
  min-width: 46px;
  padding: 6px 14px;
  font-size: 16px;
}

/* ---- 仪表带上的四组读数 ---- */
[data-frame-tier="portrait"] .sk-inst,
[data-frame-tier="tall"] .sk-inst {
  row-gap: 18px;
  padding-top: 18px;
}

/* 排印放大后年度地平线离卡底只剩 12px，社交画幅里太贴边——留出一口气 */
[data-frame-tier="portrait"] .sk-ground,
[data-frame-tier="tall"] .sk-ground {
  padding-bottom: 22px;
}

[data-frame-tier="portrait"] .sk-cluster,
[data-frame-tier="tall"] .sk-cluster {
  gap: 8px;
}

[data-frame-tier="portrait"] .sk-cl-main,
[data-frame-tier="tall"] .sk-cl-main {
  gap: 8px;
}

[data-frame-tier="portrait"] .sk-cl-label,
[data-frame-tier="tall"] .sk-cl-label {
  font-size: 20px;
  letter-spacing: 0.1em;
  gap: 12px;
}

[data-frame-tier="portrait"] .sk-cl-value,
[data-frame-tier="tall"] .sk-cl-value {
  font-size: 30px;
}

[data-frame-tier="portrait"] .sk-cl-note,
[data-frame-tier="tall"] .sk-cl-note {
  font-size: 17px;
  line-height: 1.45;
}

[data-frame-tier="portrait"] .sk-chevron,
[data-frame-tier="tall"] .sk-chevron {
  width: 15px;
  height: 15px;
  margin-top: 5px;
}

/* 构件跟着排印一起长大：量条、光谱、守夜人头像 */
[data-frame-tier="portrait"] .sk-spectrum,
[data-frame-tier="tall"] .sk-spectrum {
  width: 292px;
  gap: 11px;
}

[data-frame-tier="portrait"] .sk-sp-glyph,
[data-frame-tier="tall"] .sk-sp-glyph {
  width: 16px;
  height: 16px;
}

[data-frame-tier="portrait"] .sk-sp-bar,
[data-frame-tier="tall"] .sk-sp-bar {
  height: 5px;
}

[data-frame-tier="portrait"] .sk-sp-marker,
[data-frame-tier="tall"] .sk-sp-marker {
  width: 16px;
  height: 16px;
  border-width: 3.5px;
}

[data-frame-tier="portrait"] .sk-meter,
[data-frame-tier="tall"] .sk-meter {
  width: 252px;
  height: 5px;
  gap: 4px;
}

[data-frame-tier="portrait"] .sk-night-avatar,
[data-frame-tier="tall"] .sk-night-avatar {
  width: 66px;
  height: 66px;
  border-width: 2px;
}

[data-frame-tier="portrait"] .sk-night-avatar-fb,
[data-frame-tier="tall"] .sk-night-avatar-fb {
  font-size: 28px;
}

[data-frame-tier="portrait"] .sk-cluster--night,
[data-frame-tier="tall"] .sk-cluster--night {
  gap: 16px;
}

/* ---- 年度地平线 ---- */
[data-frame-tier="portrait"] .sk-yearline,
[data-frame-tier="tall"] .sk-yearline {
  margin-top: 16px;
  gap: 20px;
}

[data-frame-tier="portrait"] .sk-yl-cap,
[data-frame-tier="tall"] .sk-yl-cap {
  font-size: 17px;
  letter-spacing: 0.06em;
}

[data-frame-tier="portrait"] .sk-yl-val,
[data-frame-tier="tall"] .sk-yl-val {
  font-size: 20px;
}

[data-frame-tier="portrait"] .sk-yl-line::before,
[data-frame-tier="tall"] .sk-yl-line::before,
[data-frame-tier="portrait"] .sk-yl-line::after,
[data-frame-tier="tall"] .sk-yl-line::after {
  width: 7px;
  height: 7px;
}

/* ---- 山脊上的时刻星钉：竖幅下同步放大，不然缩在山脊上看不见 ---- */
[data-frame-tier="portrait"] .sk-pin,
[data-frame-tier="tall"] .sk-pin {
  width: 34px;
  height: 34px;
  margin-left: -17px;
}

[data-frame-tier="portrait"] .sk-pin svg,
[data-frame-tier="tall"] .sk-pin svg {
  width: 20px;
  height: 20px;
  margin: 7px;
}

/* ================================================================
   9:16（tier=tall）读数放大
   —— 9:16 是信息密度最难看清的一档：判词以下（时刻仪表 / 星期拨片 / 四组仪表 /
   年度地平线）原本全是 16–20px 的小字，恰恰是这一页信息量最大的部分。
   这里给它们单独定一档更大的尺度，并让构件（拨片、量条、光谱、头像、星钉）
   跟着字一起长大；仪表带高度由 groundH() 的 352 承接。
   只挂 tall：16:9 / landscape / square / portrait(3:4·4:5) 一律不受影响。
   ================================================================ */

/* 页头与判词之间那口气略收，省下的高度还给日月弧线所在的空天 */
[data-frame-tier="tall"] .sk-verdict {
  margin-top: clamp(0px, calc(var(--svh) * 4.6 - 14px), 96px);
}

[data-frame-tier="tall"] .sk-kicker {
  font-size: 24px;
  letter-spacing: 0.16em;
}

[data-frame-tier="tall"] .sk-word-sub {
  font-size: 27px;
  line-height: 1.66;
}

[data-frame-tier="tall"] .sk-word-echo {
  font-size: 24px;
  line-height: 1.66;
}

/* ---- 时刻仪表 ---- */
[data-frame-tier="tall"] .sk-ro-scope {
  font-size: 24px;
  letter-spacing: 0.14em;
}

[data-frame-tier="tall"] .sk-ro-count {
  margin-top: 6px;
  font-size: 36px;
}

[data-frame-tier="tall"] .sk-ro-count i,
[data-frame-tier="tall"] .sk-ro-count em {
  font-size: 25px;
}

[data-frame-tier="tall"] .sk-ro-count i {
  margin-right: 10px;
}

[data-frame-tier="tall"] .sk-ro-care {
  margin-top: 14px;
  font-size: 27px;
  line-height: 1.55;
}

/* ---- 星期拨片：手指大小的按钮，字也读得清 ---- */
[data-frame-tier="tall"] .sk-chips {
  margin-top: 26px;
  gap: 10px;
}

[data-frame-tier="tall"] .sk-chip {
  min-width: 60px;
  padding: 8px 17px;
  font-size: 24px;
  letter-spacing: 0.06em;
}

/* ---- 大地仪表带上的四组读数 ---- */
[data-frame-tier="tall"] .sk-inst {
  row-gap: 18px;
  padding-top: 14px;
}

[data-frame-tier="tall"] .sk-ground { padding-bottom: 18px; }

[data-frame-tier="tall"] .sk-cluster,
[data-frame-tier="tall"] .sk-cl-main {
  gap: 10px;
}

[data-frame-tier="tall"] .sk-cl-label {
  font-size: 27px;
  letter-spacing: 0.06em;
  gap: 14px;
}

/* 40px 的大数如果吃默认行高，一行标签就撑到 60px，两排仪表白白多占 28px；
   收紧行高，让高度回到标签本身的尺度 */
[data-frame-tier="tall"] .sk-cl-value {
  font-size: 40px;
  line-height: 1.1;
}

[data-frame-tier="tall"] .sk-cl-note {
  font-size: 24px;
  line-height: 1.42;
}

[data-frame-tier="tall"] .sk-chevron {
  width: 19px;
  height: 19px;
  margin-top: 7px;
}

/* 构件跟着排印一起长大 */
[data-frame-tier="tall"] .sk-spectrum {
  width: 320px;
  gap: 13px;
}

[data-frame-tier="tall"] .sk-sp-glyph {
  width: 19px;
  height: 19px;
}

[data-frame-tier="tall"] .sk-sp-bar { height: 6px; }

[data-frame-tier="tall"] .sk-sp-marker {
  width: 19px;
  height: 19px;
  border-width: 4px;
}

[data-frame-tier="tall"] .sk-meter {
  width: 280px;
  height: 6px;
  gap: 5px;
}

[data-frame-tier="tall"] .sk-night-avatar {
  width: 78px;
  height: 78px;
  border-width: 2.5px;
}

[data-frame-tier="tall"] .sk-night-avatar-fb { font-size: 33px; }

[data-frame-tier="tall"] .sk-cluster--night { gap: 18px; }

/* ---- 年度地平线 ---- */
[data-frame-tier="tall"] .sk-yearline {
  margin-top: 14px;
  gap: 22px;
}

[data-frame-tier="tall"] .sk-yl-cap {
  font-size: 24px;
  letter-spacing: 0.04em;
}

[data-frame-tier="tall"] .sk-yl-val { font-size: 27px; }

[data-frame-tier="tall"] .sk-yl-line::before,
[data-frame-tier="tall"] .sk-yl-line::after {
  width: 9px;
  height: 9px;
}

/* ---- 山脊星钉 ---- */
[data-frame-tier="tall"] .sk-pin {
  width: 40px;
  height: 40px;
  margin-left: -20px;
}

[data-frame-tier="tall"] .sk-pin svg {
  width: 24px;
  height: 24px;
  margin: 8px;
}

/* ================= panel 变体微调 ================= */

.sk--panel .sk-head { display: none; }
.sk--panel .sk-verdict { top: 36px; }
.sk--panel .sk-readout { top: 32px; }
.sk--panel .sk-word { font-size: clamp(2rem, calc(var(--svw) * 3.6), 2.8rem); }
.sk--panel .sk-ro-hour { font-size: clamp(2.2rem, calc(var(--svw) * 3.8), 3.2rem); }
/* panel 的 --ground-h（132px）已回到 script 的 groundH()，CSS 不再复写第二份 */

/* ================= 导出 / 还原：无过渡 =================
   页头、判词、读数、芯片、星钉这些的入场是纯 CSS 过渡（最晚一条 delay 3.2s），
   JS 那边的 settleInstant() 管不到它们。导出模式下把这一组过渡整个关掉，
   终态由 .sk--in 直接给出（还原那一帧同理，直接跳回未入场的初值）。
   只关 transition，不动 animation：星光/星芒是环境动效，与入场无关。 */
.sk--flat .sk-head,
.sk--flat .sk-kicker,
.sk--flat .sk-word,
.sk--flat .sk-word-sub,
.sk--flat .sk-word-echo,
.sk--flat .sk-readout,
.sk--flat .sk-chip,
.sk--flat .sk-cluster,
.sk--flat .sk-yearline,
.sk--flat .sk-pillar,
.sk--flat .sk-pin,
.sk--flat .sk-sp-marker,
.sk--flat .sk-meter i {
  transition: none !important;
}

/* ================= reduced motion ================= */

@media (prefers-reduced-motion: reduce) {
  .sk-head,
  .sk-kicker,
  .sk-word,
  .sk-word-sub,
  .sk-word-echo,
  .sk-readout,
  .sk-chip,
  .sk-cluster,
  .sk-yearline,
  .sk-pillar,
  .sk-pin,
  .sk-sp-marker,
  .sk-meter i {
    transition: none !important;
    animation: none !important;
  }

  .sk-stage .sk-head,
  .sk-stage .sk-kicker,
  .sk-stage .sk-word,
  .sk-stage .sk-word-sub,
  .sk-stage .sk-word-echo,
  .sk-stage .sk-readout,
  .sk-stage .sk-chip,
  .sk-stage .sk-cluster,
  .sk-stage .sk-yearline,
  .sk-stage .sk-pillar,
  .sk-stage .sk-pin {
    opacity: 1;
    transform: none;
    filter: none;
  }
}
</style>

<style>
/* 作息卡 slide 模式：整卡天空由 JS 相位驱动（含 FitScale 缩放时露出的边缘） */
.cyber-shell {
  background: linear-gradient(180deg, var(--sky-a, #04060f) 0%, var(--sky-b, #0a0f22) 40%, var(--sky-c, #111931) 72%, var(--sky-d, #18203c) 100%);
}
</style>
