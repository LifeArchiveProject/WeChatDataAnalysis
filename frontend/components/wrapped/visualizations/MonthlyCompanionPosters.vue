<template>
  <div class="mph-root">
    <div v-if="!hasData" class="mph-empty">
      <div class="rounded-2xl border border-white/10 bg-white/5 backdrop-blur px-6 py-5 text-center">
        <div class="wrapped-title text-base text-white/90">这一年还很安静</div>
        <div class="mt-1 wrapped-body text-sm text-white/45">聊天互动还不够，还排不满一整条海报长廊。</div>
      </div>
    </div>

    <div
      v-else
      ref="stageEl"
      class="mph-stage"
      :class="{ 'mph-stage--drag': dragging }"
      data-deck-nodrag
      @pointerdown="onPointerDown"
      @click="onStageClick"
    >
      <canvas ref="canvasEl" class="mph-canvas" aria-hidden="true" />

      <!-- 底部 HUD：左边场次牌，右边年度主演 -->
      <div class="mph-marquee">
        <div class="mph-slate" :style="{ '--accent': accent }">
          <span class="mph-slate-k wrapped-label">NOW SHOWING</span>
          <span class="mph-slate-no wrapped-number">{{ pad2(cur + 1) }}</span>
          <span class="mph-slate-en wrapped-label">{{ MONTH_EN[cur] }}</span>
        </div>

        <!-- 年度主演（桂冠） -->
        <button
          v-if="champion"
          type="button"
          class="mph-laurel"
          :style="{ '--accent': championColor }"
          :aria-label="`看 ${championName} 的主场月`"
          @click.stop="goTo(championHomeIndex)"
        >
          <svg class="mph-laurel-leaf mph-laurel-leaf--l" viewBox="0 0 30 60" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path d="M25 4C12 12 6 26 9 42c1.5 8 5 14 9 18" stroke-linecap="round" />
            <path d="M22 12c-6 0-9 3-10 8M18 22c-6 0-9 3-9 8M16 33c-5 1-7 4-7 9M17 44c-4 2-5 5-4 9" stroke-linecap="round" />
          </svg>
          <span class="mph-laurel-text">
            <span class="mph-laurel-k wrapped-label">年度主演</span>
            <span class="mph-laurel-v"><span class="wrapped-privacy-name">{{ championName }}</span></span>
            <span class="mph-laurel-s"><span class="wrapped-number">{{ champion.monthsWon }}</span> 部主演</span>
          </span>
          <svg class="mph-laurel-leaf mph-laurel-leaf--r" viewBox="0 0 30 60" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path d="M5 4C18 12 24 26 21 42c-1.5 8-5 14-9 18" stroke-linecap="round" />
            <path d="M8 12c6 0 9 3 10 8M12 22c6 0 9 3 9 8M14 33c5 1 7 4 7 9M13 44c4 2 5 5 4 9" stroke-linecap="round" />
          </svg>
        </button>
      </div>

      <!-- 胶片条：一格一个月，连续同一个主演连成一条 -->
      <div class="mph-film">
        <div class="mph-perf" aria-hidden="true" />
        <div class="mph-frames">
          <button
            v-for="m in 12"
            :key="m"
            type="button"
            class="mph-frame"
            :class="{ 'mph-frame--on': cur === m - 1 }"
            :style="{ '--accent': colorOfIndex(m - 1) }"
            :aria-label="`看 ${m} 月的海报`"
            :aria-current="cur === m - 1 ? 'true' : undefined"
            @click.stop="goTo(m - 1)"
          >
            <span class="mph-frame-no wrapped-number">{{ m }}</span>
          </button>
        </div>
        <div class="mph-perf" aria-hidden="true" />
        <div class="mph-runs">
          <div
            v-for="run in runs"
            :key="`${run.start}-${run.username || 'quiet'}`"
            class="mph-run"
            :class="{ 'mph-run--quiet': !run.username }"
            :style="{ gridColumn: `${run.start + 1} / span ${run.count}`, '--accent': run.color }"
          >
            <span v-if="run.username" class="mph-run-name wrapped-privacy-name">{{ run.displayName }}</span>
          </div>
        </div>
      </div>

      <div class="sr-only" aria-live="polite">{{ cur + 1 }}月，主演 {{ nameOfIndex(cur) || '空缺' }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { MONTH_CN, MONTH_EN, mod12, useMonthlyCompanions } from '~/composables/useMonthlyCompanions'
import { useWrappedStage } from '~/composables/useWrappedStage'

const stage = useWrappedStage()

const props = defineProps({
  months: { type: Array, default: () => [] },
  summary: { type: Object, default: null },
  year: { type: Number, default: 0 },
  active: { type: Boolean, default: true }
})

const reducedMotion = useReducedMotion()

/* 导出模式（页面级 provide）。这一页唯一的入场就是「镜头从长廊深处横移过来」：
   rot.current 起手落后 rot.target 4.6 个身位，靠 step() 每帧指数逼近，实测要 2.5s 才停稳。
   导出时直接把镜头放在终点上，第一帧就是年度主演在 C 位的那张。
   为假时行为与导出功能存在之前一字不差。 */
const exportMode = inject('wrappedExportMode', ref(false))
// 入场镜头的起手落后量（身位）；改这里等于同时改「播」和「还原时重新上膛」两处
const ENTRY_LAG = 4.6
// 这记横移还欠着没演完：用户一旦自己拖过/点过海报就作废（别在还原时把镜头从他手里抢走）
let entryPending = false

const {
  privacyMode, monthItems, hasData, colorOfIndex, nameOfIndex,
  champion, championName, championColor, championHomeIndex,
  runs, quoteOfIndex, statsOfIndex, avatars, preloadAvatars
} = useMonthlyCompanions(props)

const pad2 = (n) => String(n).padStart(2, '0')

const cur = ref(0)
const accent = computed(() => colorOfIndex(cur.value))

// ---------- 一张海报 ----------
// 27×40 英寸单页海报比例，一眼就是电影的形状
const P_W = 760
const P_H = 1140
const ART_H = Math.round(P_H * 0.56)
const FIELD = '#06100C'
const SANS = '"PingFang SC", -apple-system, "Helvetica Neue", "Microsoft YaHei", Arial, sans-serif'
const COND = '"Avenir Next Condensed", "Helvetica Neue", "PingFang SC", Arial, sans-serif'
const NUM = '"SF Pro Display", -apple-system, "Helvetica Neue", Arial, sans-serif'

const shade = (hex, f) => {
  const h = String(hex).replace('#', '')
  const r = Math.round(parseInt(h.slice(0, 2), 16) * f)
  const g = Math.round(parseInt(h.slice(2, 4), 16) * f)
  const b = Math.round(parseInt(h.slice(4, 6), 16) * f)
  return `rgb(${r}, ${g}, ${b})`
}

// 按可用宽度自动降字号，缩完把 ctx.font 留在合适的号上直接画
const fitFont = (ctx, text, maxWidth, startPx, weight, family, minPx) => {
  let size = startPx
  ctx.font = `${weight} ${size}px ${family}`
  while (size > minPx && ctx.measureText(text).width > maxWidth) {
    size -= 1
    ctx.font = `${weight} ${size}px ${family}`
  }
  return size
}

// 影片颗粒：生成一次，全部海报共用
let grainCanvas = null
const getGrain = () => {
  if (grainCanvas) return grainCanvas
  const n = 160
  const cv = document.createElement('canvas')
  cv.width = n
  cv.height = n
  const ctx = cv.getContext('2d')
  const img = ctx.createImageData(n, n)
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 118 + Math.random() * 62
    img.data[i] = v
    img.data[i + 1] = v
    img.data[i + 2] = v
    img.data[i + 3] = 255
  }
  ctx.putImageData(img, 0, 0)
  grainCanvas = cv
  return cv
}

const drawLaurel = (ctx, cx, cy, r, color) => {
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  for (const side of [-1, 1]) {
    const from = side < 0 ? Math.PI * 0.66 : Math.PI * 0.34
    const to = side < 0 ? Math.PI * 1.34 : Math.PI * -0.34
    ctx.beginPath()
    ctx.arc(cx, cy, r, from, to, side > 0)
    ctx.stroke()
    for (let i = 0; i < 6; i += 1) {
      const t = 0.1 + i * 0.16
      const a = from + (to - from) * t
      const px = cx + Math.cos(a) * r
      const py = cy + Math.sin(a) * r
      ctx.save()
      ctx.translate(px, py)
      ctx.rotate(a + side * 0.62)
      ctx.beginPath()
      ctx.ellipse(r * 0.13, 0, r * 0.155, r * 0.06, 0, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()
    }
  }
  ctx.restore()
}

// 竖幅：海报在屏幕上被放大了，同一张画布上的字必须跟着一起长——
// 否则「放大」只放大了图，演职员表那几行还是看不清。
// posterMode 决定用哪套版式，posterTS 由海报实际上屏高度反推（见 resolvePosterFit）。
let posterMode = 'wide'
let posterTS = 1
// 竖幅版式在 ts=1 时占的文字区高度；ts 变大就从主视觉那边借高度过来
const NARROW_TEXT_H = 596
const narrowArtH = () => Math.max(Math.round(P_H * 0.3), P_H - Math.round(NARROW_TEXT_H * posterTS) - 20)

const drawPoster = (ctx, index) => {
  const item = monthItems.value[index] || {}
  const winner = item.winner || null
  const accentColor = colorOfIndex(index)
  const name = nameOfIndex(index) || '空 缺'
  const img = avatars[index]
  const isChampionMonth = !!champion.value && String(item?.winner?.username || '') === String(champion.value.username || '')
  const tall = posterMode === 'tall'
  const ts = tall ? posterTS : 1
  const u = (v) => Math.round(v * ts)      // 竖幅刻度：字号与行距同倍放大
  const artH = tall ? narrowArtH() : ART_H

  ctx.clearRect(0, 0, P_W, P_H)
  ctx.textAlign = 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = FIELD
  ctx.fillRect(0, 0, P_W, P_H)

  // ---- 主视觉 ----
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, 0, P_W, artH)
  ctx.clip()

  if (img && img.width) {
    const s = Math.max(P_W / img.width, artH / img.height)
    ctx.filter = privacyMode.value
      ? 'blur(30px) contrast(1.1) saturate(0.8)'
      : 'contrast(1.1) saturate(0.86) brightness(1.02)'
    ctx.drawImage(img, (P_W - img.width * s) / 2, (artH - img.height * s) / 2, img.width * s, img.height * s)
    ctx.filter = 'none'
  } else {
    const g = ctx.createLinearGradient(0, 0, P_W, artH)
    g.addColorStop(0, shade(accentColor, 0.35))
    g.addColorStop(1, FIELD)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, P_W, artH)
    ctx.fillStyle = `${accentColor}66`
    ctx.font = `700 ${Math.round(artH * 0.345)}px ${SANS}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(winner ? name[0] : '·', P_W / 2, artH * 0.46)
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
  }

  // 调色：暗部压向陪伴色，亮部留暖
  ctx.globalCompositeOperation = 'multiply'
  const grade = ctx.createLinearGradient(0, 0, 0, artH)
  grade.addColorStop(0, '#FFF3E2')
  grade.addColorStop(0.55, '#FFFFFF')
  grade.addColorStop(1, shade(accentColor, 0.78))
  ctx.fillStyle = grade
  ctx.fillRect(0, 0, P_W, artH)

  ctx.globalCompositeOperation = 'screen'
  ctx.fillStyle = `${accentColor}1A`
  ctx.fillRect(0, 0, P_W, artH)
  ctx.globalCompositeOperation = 'source-over'

  // 主视觉压到海报底色里
  const fade = ctx.createLinearGradient(0, artH * 0.5, 0, artH)
  fade.addColorStop(0, 'rgba(6,16,12,0)')
  fade.addColorStop(0.74, 'rgba(6,16,12,0.68)')
  fade.addColorStop(1, FIELD)
  ctx.fillStyle = fade
  ctx.fillRect(0, artH * 0.5, P_W, artH * 0.5)

  // 暗角
  const vig = ctx.createRadialGradient(P_W / 2, artH * 0.42, artH * 0.2, P_W / 2, artH * 0.42, artH * 0.86)
  vig.addColorStop(0, 'rgba(0,0,0,0)')
  vig.addColorStop(1, 'rgba(0,0,0,0.42)')
  ctx.fillStyle = vig
  ctx.fillRect(0, 0, P_W, artH)
  ctx.restore()

  // 片号
  ctx.fillStyle = 'rgba(255,255,255,0.5)'
  ctx.font = `600 ${tall ? u(26) : 22}px ${NUM}`
  ctx.letterSpacing = `${tall ? u(7) : 6}px`
  ctx.fillText(`NO. ${pad2(index + 1)}`, tall ? 48 : 44, tall ? u(74) : 66)
  ctx.letterSpacing = '0px'

  // 桂冠：这个月的主演正是年度主演
  if (isChampionMonth) {
    const ly = tall ? u(96) : 92
    drawLaurel(ctx, P_W - (tall ? 118 : 112), ly, tall ? u(58) : 54, 'rgba(255,255,255,0.7)')
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = 'rgba(255,255,255,0.78)'
    ctx.font = `700 ${tall ? u(23) : 19}px ${SANS}`
    ctx.fillText('年度', P_W - (tall ? 118 : 112), ly - (tall ? u(7) : 6))
    ctx.fillText('主演', P_W - (tall ? 118 : 112), ly + (tall ? u(19) : 16))
    ctx.restore()
  }

  // ---- 文字区 ----
  const cx = P_W / 2
  ctx.textAlign = 'center'
  const cells = statsOfIndex(index)

  if (tall) {
    // 竖幅版式：字号整体上一档，演职员表拆成两行（宁可换行，也不缩号）
    const inner = P_W - 84

    ctx.fillStyle = 'rgba(255,255,255,0.34)'
    ctx.letterSpacing = `${u(9)}px`
    fitFont(ctx, '微信年度总结 呈现', inner, u(26), '600', SANS, u(18))
    ctx.fillText('微信年度总结 呈现', cx, artH + u(54))
    ctx.letterSpacing = '0px'

    ctx.fillStyle = 'rgba(255,255,255,0.62)'
    const tagline = `「${quoteOfIndex(index)}」`
    fitFont(ctx, tagline, inner, u(36), '400', SANS, u(26))
    ctx.fillText(tagline, cx, artH + u(126))

    const titleSize = fitFont(ctx, name, P_W - 96, u(116), '800', SANS, u(54))
    ctx.fillStyle = winner ? '#FFFFFF' : 'rgba(255,255,255,0.34)'
    ctx.font = `800 ${titleSize}px ${SANS}`
    ctx.letterSpacing = `${Math.round(titleSize * 0.06)}px`
    if (privacyMode.value && winner) ctx.filter = `blur(${Math.max(10, Math.round(titleSize * 0.36))}px)`
    ctx.fillText(name, cx + Math.round(titleSize * 0.03), artH + u(258))
    ctx.filter = 'none'
    ctx.letterSpacing = '0px'

    ctx.fillStyle = accentColor
    ctx.fillRect(cx - u(70), artH + u(290), u(140), Math.max(4, u(5)))

    ctx.fillStyle = 'rgba(255,255,255,0.5)'
    ctx.letterSpacing = `${u(7)}px`
    fitFont(ctx, `${MONTH_CN[index]} · ${MONTH_EN[index]} · ${props.year || ''}`, inner, u(26), '600', NUM, u(18))
    ctx.fillText(`${MONTH_CN[index]} · ${MONTH_EN[index]} · ${props.year || ''}`, cx + u(4), artH + u(346))
    ctx.letterSpacing = '0px'

    ctx.strokeStyle = 'rgba(255,255,255,0.16)'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(72, artH + u(396))
    ctx.lineTo(P_W - 72, artH + u(396))
    ctx.stroke()

    ctx.letterSpacing = `${u(3)}px`
    if (winner) {
      const cast = `主演  ${name}      共同出演  你`
      ctx.fillStyle = 'rgba(255,255,255,0.72)'
      fitFont(ctx, cast, inner, u(27), '600', COND, u(19))
      if (privacyMode.value) ctx.filter = `blur(${u(8)}px)`
      ctx.fillText(cast, cx, artH + u(442))
      ctx.filter = 'none'
      // 一行四项在窄海报上必然被缩到看不清，改成两行两项：换行不缩号
      const c1 = `消息 ${cells[0][0]}    ·    来回 ${cells[1][0]}`
      const c2 = `在场 ${cells[2][0]} 天    ·    回复 ${cells[3][0]}`
      ctx.fillStyle = 'rgba(255,255,255,0.56)'
      fitFont(ctx, c1, inner, u(26), '400', COND, u(18))
      ctx.fillText(c1, cx, artH + u(488))
      fitFont(ctx, c2, inner, u(26), '400', COND, u(18))
      ctx.fillText(c2, cx, artH + u(524))
      ctx.fillStyle = accentColor
      ctx.font = `700 ${u(31)}px ${NUM}`
      ctx.fillText(`羁绊指数 ${Number(winner.score100 || 0).toFixed(1)}`, cx, artH + u(578))
    } else {
      ctx.fillStyle = 'rgba(255,255,255,0.62)'
      ctx.font = `600 ${u(27)}px ${COND}`
      ctx.fillText('本月无主演', cx, artH + u(442))
      ctx.fillStyle = 'rgba(255,255,255,0.44)'
      fitFont(ctx, '这个月的对话安静得能听见回声', inner, u(25), '400', COND, u(18))
      ctx.fillText('这个月的对话安静得能听见回声', cx, artH + u(492))
    }
    ctx.letterSpacing = '0px'
  } else {
    // 出品行
    ctx.fillStyle = 'rgba(255,255,255,0.34)'
    ctx.font = `600 22px ${SANS}`
    ctx.letterSpacing = '8px'
    ctx.fillText('微信年度总结 呈现', cx, artH + 52)
    ctx.letterSpacing = '0px'

    // 标语
    ctx.fillStyle = 'rgba(255,255,255,0.6)'
    const tagline = `「${quoteOfIndex(index)}」`
    fitFont(ctx, tagline, P_W - 88, 31, '400', SANS, 21)
    ctx.fillText(tagline, cx, artH + 116)

    // 片名 = 那个月陪你最多的人（隐私模式：名字在画布里直接糊掉，强度随字号）
    const titleSize = fitFont(ctx, name, P_W - 96, 104, '800', SANS, 48)
    ctx.fillStyle = winner ? '#FFFFFF' : 'rgba(255,255,255,0.34)'
    ctx.font = `800 ${titleSize}px ${SANS}`
    ctx.letterSpacing = `${Math.round(titleSize * 0.06)}px`
    if (privacyMode.value && winner) ctx.filter = `blur(${Math.max(10, Math.round(titleSize * 0.36))}px)`
    ctx.fillText(name, cx + Math.round(titleSize * 0.03), artH + 232)
    ctx.filter = 'none'
    ctx.letterSpacing = '0px'

    ctx.fillStyle = accentColor
    ctx.fillRect(cx - 58, artH + 266, 116, 4)

    ctx.fillStyle = 'rgba(255,255,255,0.46)'
    ctx.font = `600 23px ${NUM}`
    ctx.letterSpacing = '8px'
    ctx.fillText(`${MONTH_CN[index]} · ${MONTH_EN[index]} · ${props.year || ''}`, cx + 5, artH + 314)
    ctx.letterSpacing = '0px'

    // ---- 演职员表 ----
    let by = artH + 402
    ctx.strokeStyle = 'rgba(255,255,255,0.16)'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(64, artH + 360)
    ctx.lineTo(P_W - 64, artH + 360)
    ctx.stroke()

    ctx.fillStyle = 'rgba(255,255,255,0.62)'
    ctx.letterSpacing = '3px'
    ctx.font = `600 23px ${COND}`
    if (winner) fitFont(ctx, `主演  ${name}      共同出演  你`, P_W - 104, 23, '600', COND, 15)
    if (privacyMode.value && winner) ctx.filter = 'blur(7px)'
    if (winner) {
      ctx.fillText(`主演  ${name}      共同出演  你`, cx, by)
      ctx.filter = 'none'
      by += 38
      // 演职员表那行按海报宽度自动缩号，长名字/大数字都不会顶出画面
      const credits = `消息 ${cells[0][0]}   ·   来回 ${cells[1][0]}   ·   在场 ${cells[2][0]} 天   ·   回复 ${cells[3][0]}`
      ctx.fillStyle = 'rgba(255,255,255,0.48)'
      fitFont(ctx, credits, P_W - 104, 21, '400', COND, 14)
      ctx.fillText(credits, cx, by)
      by += 44
      ctx.fillStyle = accentColor
      ctx.font = `700 26px ${NUM}`
      ctx.fillText(`羁绊指数 ${Number(winner.score100 || 0).toFixed(1)}`, cx, by)
    } else {
      ctx.fillText('本月无主演', cx, by)
      by += 40
      ctx.fillStyle = 'rgba(255,255,255,0.4)'
      ctx.font = `400 21px ${COND}`
      ctx.fillText('这个月的对话安静得能听见回声', cx, by)
    }
    ctx.letterSpacing = '0px'
  }
  ctx.textAlign = 'left'

  // ---- 胶片颗粒 ----
  const grain = ctx.createPattern(getGrain(), 'repeat')
  ctx.save()
  ctx.globalCompositeOperation = 'overlay'
  ctx.globalAlpha = 0.16
  ctx.fillStyle = grain
  ctx.fillRect(0, 0, P_W, P_H)
  ctx.restore()

  // 印张的高光边
  ctx.strokeStyle = 'rgba(255,255,255,0.1)'
  ctx.lineWidth = 2
  ctx.strokeRect(1, 1, P_W - 2, P_H - 2)
}

// ---------- three ----------
const stageEl = ref(null)
const canvasEl = ref(null)
const dragging = ref(false)

let THREE = null
let renderer = null
let scene = null
let camera = null
let rig = null
let posters = []
let rafId = 0
let ro = null
let destroyed = false
let initing = false
let lastT = 0
const viewport = { w: 1, h: 1 }
const pointer = { x: 0, y: 0 }

const RA = 24                       // 长廊弧半径
const CARD_H = 3.34
const CARD_W = CARD_H * (P_W / P_H)
const STEP_WIDE = 0.118             // 16:9 下相邻两张海报的夹角（基线，逐像素不变）
// 再密就两张贴到一起：一格弧长正好等于一张海报的宽
const STEP_MIN = (CARD_W * 1.02) / RA
// 窄画幅判定：低于这个画布宽高比就按竖幅重排（16:9 舞台上这里恒 ≥1.9）
const WIDE_ASPECT = 1.7
const FOV = 34
const HALF_TAN = Math.tan((FOV * Math.PI) / 360)

// 竖幅下镜头的俯角和视差都要收：海报放大后上下余量本来就薄，再压一压就切顶
let lookY = -CARD_H * 0.09
let camBaseY = -CARD_H * 0.03
let panX = 0.3
let panY = 0.14

let STEP = STEP_WIDE
let PERIOD = 12 * STEP

const rot = { current: 0, target: 0, velocity: 0 }

const MIRROR_VERT = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

const MIRROR_FRAG = `
uniform sampler2D uMap;
uniform float uLit;
varying vec2 vUv;
void main() {
  vec4 c = texture2D(uMap, vUv);
  float fade = smoothstep(0.0, 0.55, vUv.y);
  gl_FragColor = vec4(c.rgb * vec3(0.62, 0.7, 0.66), c.a * fade * 0.26 * uLit);
}
`

const buildScene = () => {
  renderer = new THREE.WebGLRenderer({ canvas: canvasEl.value, antialias: true, alpha: true, powerPreference: 'high-performance' })
  // 计入舞台缩放：画布 CSS 尺寸是舞台单位，上屏物理尺寸还要乘一次 stage.scale
  renderer.setPixelRatio(stage.pixelRatio(3))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearAlpha(0)

  scene = new THREE.Scene()
  scene.fog = new THREE.Fog(0x08110D, 1, 2)
  camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 90)

  rig = new THREE.Group()
  rig.position.z = -RA
  scene.add(rig)

  const geo = new THREE.PlaneGeometry(CARD_W, CARD_H)
  const maxAniso = renderer.capabilities.getMaxAnisotropy()

  for (let i = 0; i < 12; i += 1) {
    const cv = document.createElement('canvas')
    cv.width = P_W
    cv.height = P_H
    drawPoster(cv.getContext('2d'), i)
    const tex = new THREE.CanvasTexture(cv)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = maxAniso
    tex.minFilter = THREE.LinearMipmapLinearFilter

    const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true })
    const mirrorMat = new THREE.ShaderMaterial({
      uniforms: { uMap: { value: tex }, uLit: { value: 1 } },
      vertexShader: MIRROR_VERT,
      fragmentShader: MIRROR_FRAG,
      transparent: true,
      depthWrite: false,
      fog: false
    })

    // 首尾各复制一轮，长廊两头都不会空
    const copies = []
    for (let k = -1; k <= 1; k += 1) {
      const a = i * STEP + k * PERIOD
      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.set(Math.sin(a) * RA, 0, Math.cos(a) * RA)
      mesh.rotation.y = a
      mesh.userData.index = i
      rig.add(mesh)

      const mirror = new THREE.Mesh(geo, mirrorMat)
      mirror.position.set(Math.sin(a) * RA, -CARD_H - 0.12, Math.cos(a) * RA)
      mirror.rotation.y = a
      mirror.scale.y = -1
      rig.add(mirror)

      copies.push({ mesh, mirror, angle: a, k })
    }

    posters.push({ copies, mat, mirrorMat, tex, cv })
  }
}

// 换画幅 = 舞台 scale 变了 = 画布上屏物理尺寸变了：重设像素比并重算构图，
// 否则大屏放大后 3D 区域发糊（文字锐利、海报糊，最容易被当成「导出坏了」）
watch(() => stage.scale.value, () => {
  if (!renderer) return
  renderer.setPixelRatio(stage.pixelRatio(3))
  syncCamera()
})

// 竖幅下视野变窄，把长廊的间距收紧，邻片才露得进画面。
// （反过来放大夹角只会把邻片推得更远——9:16 下就只剩 C 位一张。）
const stepFor = (aspect) => {
  if (aspect >= WIDE_ASPECT) return STEP_WIDE
  return Math.max(STEP_MIN, STEP_WIDE * (aspect / WIDE_ASPECT))
}

// 换间距＝把 12 张（各 3 份副本）沿弧重新钉一遍位置，
// 同时把当前转角按比例映射过去，保证 C 位还是同一个月。
const applyStep = (next) => {
  if (!posters.length || Math.abs(next - STEP) < 1e-4) return
  const k = next / STEP
  STEP = next
  PERIOD = 12 * STEP
  rot.current *= k
  rot.target *= k
  for (let i = 0; i < posters.length; i += 1) {
    for (const c of posters[i].copies) {
      const a = i * STEP + c.k * PERIOD
      c.angle = a
      c.mesh.position.set(Math.sin(a) * RA, 0, Math.cos(a) * RA)
      c.mesh.rotation.y = a
      c.mirror.position.set(Math.sin(a) * RA, -CARD_H - 0.12, Math.cos(a) * RA)
      c.mirror.rotation.y = a
    }
  }
}

// 16:9（含跟随窗口的横屏）走原样；只有真正变窄的画布才进重排分支
const isWideFrame = (aspect) => stage.tier.value === 'wide' && aspect >= WIDE_ASPECT

// 双轴 fit 的纯计算部分：不碰 camera 对象，init 里也能先算一次好定版式
const resolvePosterFit = (w, h) => {
  const aspect = w / h
  const wide = isWideFrame(aspect)
  // 纵向：16:9 沿用「海报贴满可用高度」的既有构图。
  // 竖幅下不再把海报锁死在一个设计常量上——那等于把窄画幅多出来的高度全让给空地，
  // 海报只剩三分之一屏宽，画布里的演职员表落到十来个像素。这里让它吃满可用高度的
  // 86%，剩下的 14% 是 C 位那张 1.12 放大 + 镜头俯角要用的余量，不是留白。
  const fitH = wide ? h : h * 0.86
  const distV = (CARD_H * 1.06 * (h / fitH)) / (2 * HALF_TAN)
  // 横向：C 位那张必须整张进画，留 8% 余量。16:9 下这一支恒不约束（1.6 ≪ 5.8）。
  const distH = (CARD_W / 2) / (HALF_TAN * aspect)
  const dist = Math.max(distV, distH * 1.08)
  // C 位海报在屏幕上的高度（设计 px，已含 1.12 放大）——竖幅版式的字号就按它反推
  const cardH = (CARD_H * 1.12 * (h / 2)) / (dist * HALF_TAN)
  return { aspect, wide, dist, cardH }
}

// 画布上最小的一号字是 26 * ts；让它上屏后不低于 23.5 设计 px
const applyPosterMode = (fit) => {
  const mode = fit.wide ? 'wide' : 'tall'
  const want = mode === 'tall'
    ? Math.min(1.3, Math.max(1, (23.5 * P_H) / (26 * Math.max(1, fit.cardH))))
    : 1
  const ts = Math.round(want * 20) / 20
  if (mode === posterMode && Math.abs(ts - posterTS) < 1e-6) return
  posterMode = mode
  posterTS = ts
  if (posters.length) repaintAll()
}

// 画布可用区：舞台盒扣掉底部胶片条和场次牌
const readBox = () => {
  const box = stageEl.value
  if (!box) return null
  const film = box.querySelector('.mph-film')
  const marquee = box.querySelector('.mph-marquee')
  const reserved = (film ? film.offsetHeight : 0) + (marquee ? marquee.offsetHeight : 0) + 22
  return {
    w: Math.max(1, Math.round(box.clientWidth)),
    h: Math.max(1, Math.round(box.clientHeight - reserved))
  }
}

const syncCamera = () => {
  if (!camera || !renderer || !stageEl.value) return
  const bx = readBox()
  if (!bx) return
  const { w, h } = bx
  viewport.w = w
  viewport.h = h
  const fit = resolvePosterFit(w, h)
  applyStep(stepFor(fit.aspect))
  applyPosterMode(fit)
  if (scene?.fog) {
    scene.fog.near = fit.dist + 1.4
    scene.fog.far = fit.dist + 10.5
  }
  lookY = fit.wide ? -CARD_H * 0.09 : -CARD_H * 0.02
  camBaseY = fit.wide ? -CARD_H * 0.03 : -CARD_H * 0.005
  panX = fit.wide ? 0.3 : 0.16
  panY = fit.wide ? 0.14 : 0.05
  camera.position.set(0, camBaseY, fit.dist)
  camera.lookAt(0, lookY, 0)
  camera.aspect = fit.aspect
  camera.updateProjectionMatrix()
  renderer.setSize(w, h, false)
  if (canvasEl.value) canvasEl.value.style.height = `${h}px`
}

const goTo = (index) => {
  entryPending = false
  const target = mod12(index)
  const want = -target * STEP
  const diff = ((want - rot.target + PERIOD / 2) % PERIOD + PERIOD) % PERIOD - PERIOD / 2
  rot.target += diff
}

const step = (dt) => {
  const prev = rot.current
  const k = reducedMotion.value ? 999 : 7.2
  rot.current += (rot.target - rot.current) * (1 - Math.exp(-k * dt))
  if (!dragging.value) rot.velocity = (rot.current - prev) / Math.max(dt, 0.001)
  rig.rotation.y = rot.current

  const idx = mod12(Math.round(-rot.current / STEP))
  if (idx !== cur.value) cur.value = idx

  // C 位打亮，两侧按角度退入暗处并偏冷
  for (let i = 0; i < posters.length; i += 1) {
    let best = Infinity
    for (const c of posters[i].copies) {
      const d = Math.abs(c.angle + rot.current) / STEP
      if (d < best) best = d
    }
    const lit = Math.max(0, 1 - best * 0.46)
    const v = 0.26 + 0.82 * lit
    posters[i].mat.color.setRGB(v * 0.99, v, v * 1.02)
    posters[i].mirrorMat.uniforms.uLit.value = lit
    const sc = 1 + Math.max(0, 1 - best) * 0.12
    for (const c of posters[i].copies) {
      c.mesh.scale.setScalar(sc)
      c.mirror.scale.set(sc, -sc, sc)
    }
  }

  if (rot.current > PERIOD) { rot.current -= PERIOD; rot.target -= PERIOD }
  else if (rot.current < -PERIOD) { rot.current += PERIOD; rot.target += PERIOD }

  // 镜头贴上终点即算入场演完（指数逼近不会精确收敛，取半格以内为准）
  if (entryPending && Math.abs(rot.target - rot.current) < STEP * 0.02) entryPending = false
}

const tick = () => {
  rafId = requestAnimationFrame(tick)
  if (destroyed || !renderer || !scene || !camera) return
  if (viewport.w <= 1) return
  const now = performance.now()
  const dt = lastT ? Math.min(0.05, (now - lastT) / 1000) : 1 / 60
  lastT = now
  step(dt)
  const px = reducedMotion.value ? 0 : pointer.x * panX
  const py = reducedMotion.value ? 0 : pointer.y * panY
  camera.position.x += (px - camera.position.x) * 0.06
  camera.position.y += ((camBaseY - py) - camera.position.y) * 0.06
  camera.lookAt(camera.position.x * 0.4, lookY, 0)
  renderer.render(scene, camera)
}

// ---------- 交互 ----------
let suppressClickUntil = 0
const drag = { id: null, lastX: 0, moved: 0 }

const onPointerDown = (e) => {
  if (e.button === 2 || drag.id !== null) return
  if (e.target instanceof Element && e.target.closest('.mph-film, .mph-laurel')) return
  drag.id = e.pointerId
  drag.lastX = e.clientX
  drag.moved = 0
  dragging.value = true
  rot.velocity = 0
  try { stageEl.value?.setPointerCapture?.(e.pointerId) } catch {}
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragUp)
  window.addEventListener('pointercancel', onDragUp)
  if (e.pointerType === 'touch' || e.pointerType === 'pen') e.preventDefault()
}

const onDragMove = (e) => {
  if (e.pointerId !== drag.id) return
  entryPending = false
  const dx = e.clientX - drag.lastX
  drag.lastX = e.clientX
  drag.moved += Math.abs(dx)
  // 间距收紧后同样的位移会掠过更多张，按 STEP 等比换算，各画幅手感一致
  const d = dx * 0.0024 * (STEP / STEP_WIDE)
  rot.target += d
  rot.current += d
  rot.velocity = d * 60
}

const onDragUp = (e) => {
  if (e.pointerId !== drag.id) return
  drag.id = null
  dragging.value = false
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragUp)
  window.removeEventListener('pointercancel', onDragUp)
  if (drag.moved > 6) suppressClickUntil = Date.now() + 260
  const projected = rot.target + rot.velocity * 0.13
  rot.target = -STEP * Math.round(-projected / STEP)
}

// 点两侧的海报，把它请到 C 位
const onStageClick = (e) => {
  if (Date.now() < suppressClickUntil || !camera || !renderer) return
  if (e.target instanceof Element && e.target.closest('.mph-film, .mph-laurel, .mph-slate')) return
  const cv = canvasEl.value
  if (!cv) return
  // 两个轴都用画布自己的实测矩形：x 用舞台盒宽、y 用变换前的 viewport.h 时，
  // 一来两轴不同坐标系，二来 y 还多算了底部胶片条那一截，点谁都会点错海报。
  const r = cv.getBoundingClientRect()
  if (!r.width || !r.height) return
  const ndc = new THREE.Vector2(
    ((e.clientX - r.left) / r.width) * 2 - 1,
    -(((e.clientY - r.top) / r.height) * 2 - 1)
  )
  const ray = new THREE.Raycaster()
  ray.setFromCamera(ndc, camera)
  const hits = ray.intersectObjects(posters.flatMap((p) => p.copies.map((c) => c.mesh)), false)
  if (hits.length) goTo(hits[0].object.userData.index)
}

const onStageMove = (e) => {
  const box = stageEl.value
  if (!box) return
  const r = box.getBoundingClientRect()
  if (!r.width || !r.height) return
  pointer.x = Math.min(1, Math.max(-1, ((e.clientX - r.left) / r.width) * 2 - 1))
  pointer.y = Math.min(1, Math.max(-1, ((e.clientY - r.top) / r.height) * 2 - 1))
}

const onStageLeave = () => {
  pointer.x = 0
  pointer.y = 0
}

// ---------- 生命周期 ----------
const startLoop = () => {
  if (rafId || destroyed) return
  rafId = requestAnimationFrame(tick)
}

const stopLoop = () => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = 0
  lastT = 0
}

const repaintAll = () => {
  for (let i = 0; i < posters.length; i += 1) {
    drawPoster(posters[i].cv.getContext('2d'), i)
    posters[i].tex.needsUpdate = true
  }
}

const init = async () => {
  if (!import.meta.client || destroyed || renderer || initing || !hasData.value) return
  initing = true
  try {
    THREE = await import('three')
    if (destroyed) return
    if (document?.fonts?.ready) { try { await document.fonts.ready } catch {} }
    await preloadAvatars()
    if (destroyed || !canvasEl.value) return
    // 先把版式定下来再画海报，省掉「按横幅画一遍再按竖幅重画一遍」
    const bx0 = readBox()
    if (bx0) applyPosterMode(resolvePosterFit(bx0.w, bx0.h))
    buildScene()
    syncCamera()
    const land = championHomeIndex.value
    cur.value = land
    rot.target = -land * STEP
    // 入场：镜头从长廊深处横移过来，停在年度主演那张
    entryPending = !(reducedMotion.value || exportMode.value)
    rot.current = entryPending ? rot.target - STEP * ENTRY_LAG : rot.target
    startLoop()
    if (typeof ResizeObserver !== 'undefined' && stageEl.value) {
      ro = new ResizeObserver(() => syncCamera())
      ro.observe(stageEl.value)
      // 胶片条 / 场次牌的高度是从画布高度里扣掉的：竖幅下主演名换行、胶片条长高时
      // 只观察舞台盒不会重算，画布就会顶到条子底下去
      const film = stageEl.value.querySelector('.mph-film')
      const marquee = stageEl.value.querySelector('.mph-marquee')
      if (film) ro.observe(film)
      if (marquee) ro.observe(marquee)
    }
    stageEl.value?.addEventListener('pointermove', onStageMove)
    stageEl.value?.addEventListener('pointerleave', onStageLeave)
  } finally {
    initing = false
  }
}

const teardown = () => {
  stopLoop()
  ro?.disconnect()
  ro = null
  stageEl.value?.removeEventListener('pointermove', onStageMove)
  stageEl.value?.removeEventListener('pointerleave', onStageLeave)
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragUp)
  window.removeEventListener('pointercancel', onDragUp)
  for (const p of posters) {
    try { p.tex.dispose() } catch {}
    try { p.mat.dispose() } catch {}
    try { p.mirrorMat.dispose() } catch {}
  }
  posters = []
  try { renderer?.dispose?.() } catch {}
  renderer = null
  scene = null
  camera = null
  rig = null
}

onMounted(() => {
  if (!import.meta.client) return
  if (props.active) void init()
})

watch(() => props.active, (v) => {
  if (!import.meta.client) return
  if (v) {
    if (!renderer) void init()
    else startLoop()
  } else {
    stopLoop()
  }
})

/* 导出模式：进去镜头立刻站到终点，出来把镜头重新拉回长廊深处。
   —— 还原必须真的还原：这一页的开场就是那记横移，用户导出一次再回来
      若镜头已经停在 C 位，这记推轨就白做了。
   种子值在 setup 期就定：init() 会在导出已开时直接把镜头放到终点，
   等 watch 回调再判断「是否还欠一次入场」就已经看不出来了。 */
let exportOwesEntry = exportMode.value

watch(exportMode, (on) => {
  if (!import.meta.client || destroyed) return

  if (on) {
    if (renderer) {
      // renderer 已在：入场可能正演到一半，把镜头直接推到终点
      exportOwesEntry = entryPending
      entryPending = false
      rot.current = rot.target
      rot.velocity = 0
    } else {
      // 还没 init：这一次入场本来就还欠着，init() 会读 exportMode 直接落位
      exportOwesEntry = true
    }
    return
  }

  if (!exportOwesEntry) return
  exportOwesEntry = false
  if (!renderer || reducedMotion.value) return
  // 重新上膛：镜头退回长廊深处，翻到本页（或此刻就在本页）时照旧横移过来
  entryPending = true
  rot.current = rot.target - STEP * ENTRY_LAG
  rot.velocity = 0
})

watch(privacyMode, () => {
  if (renderer) repaintAll()
})

const dataSignature = computed(() => monthItems.value
  .map((it) => `${it?.winner?.username || '-'}:${Number(it?.raw?.totalMessages || 0)}`)
  .join('|'))

watch(dataSignature, async (sig, prev) => {
  if (!import.meta.client || destroyed || sig === prev) return
  teardown()
  if (props.active) await init()
})

onBeforeUnmount(() => {
  destroyed = true
  teardown()
})
</script>

<style scoped>
.mph-root {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.mph-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mph-stage {
  position: relative;
  width: 100%;
  height: 100%;
  container-type: size;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  cursor: grab;
  overflow: hidden;
}

.mph-stage--drag {
  cursor: grabbing;
}

.mph-canvas {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  display: block;
}

/* ---------- 场次牌 ---------- */
.mph-marquee {
  position: absolute;
  left: 0;
  right: 0;
  bottom: max(58px, 8.6cqh);
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2cqw;
}

.mph-slate {
  display: flex;
  align-items: baseline;
  gap: 0.7cqw;
  pointer-events: none;
}

.mph-slate-k {
  font-size: max(8px, 0.72cqw);
  color: rgba(255, 255, 255, 0.3);
}

.mph-slate-no {
  font-size: max(22px, 2.4cqw);
  font-weight: 800;
  line-height: 1;
  color: var(--accent, #4ADE80);
  transition: color 420ms ease;
}

.mph-slate-en {
  font-size: max(9px, 0.8cqw);
  color: rgba(255, 255, 255, 0.34);
}

/* ---------- 年度主演桂冠 ---------- */
.mph-laurel {
  display: flex;
  align-items: center;
  gap: 0.3cqw;
  padding: 0.4cqh 0.6cqw;
  color: var(--accent, #4ADE80);
  cursor: pointer;
  transition: transform 260ms cubic-bezier(0.34, 1.5, 0.5, 1), opacity 260ms ease;
  opacity: 0.92;
  border-radius: 9999px;
  background: radial-gradient(60% 70% at 50% 50%, rgba(4, 10, 8, 0.82), rgba(4, 10, 8, 0));
}

.mph-laurel:hover {
  transform: translateY(-2px);
  opacity: 1;
}

.mph-laurel-leaf {
  width: max(22px, 1.7cqw);
  height: auto;
  flex: none;
}

.mph-laurel-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.2;
  padding: 0 0.2cqw;
}

.mph-laurel-k {
  font-size: max(7px, 0.62cqw);
  color: rgba(255, 255, 255, 0.4);
}

.mph-laurel-v {
  font-size: max(12px, 1.15cqw);
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
}

.mph-laurel-s {
  font-size: max(7px, 0.62cqw);
  color: rgba(255, 255, 255, 0.4);
}

/* ---------- 胶片条 ---------- */
.mph-film {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 4;
  padding: 4px 0 0;
  background: rgba(0, 0, 0, 0.34);
  border-radius: 4px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.05);
}

.mph-perf {
  height: 7px;
  background-image: radial-gradient(circle at 7px 50%, rgba(255, 255, 255, 0.26) 2.2px, transparent 2.4px);
  background-size: 19px 100%;
  opacity: 0.9;
}

.mph-frames {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 2px;
  padding: 3px 4px;
}

.mph-frame {
  position: relative;
  height: max(20px, 2.6cqh);
  border-radius: 2px;
  background: color-mix(in srgb, var(--accent, #4ADE80) 22%, transparent);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: background 240ms ease, box-shadow 240ms ease;
}

.mph-frame:hover {
  background: color-mix(in srgb, var(--accent, #4ADE80) 45%, transparent);
}

.mph-frame--on {
  background: color-mix(in srgb, var(--accent, #4ADE80) 82%, transparent);
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.85);
}

.mph-frame-no {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: max(9px, 0.78cqw);
  font-weight: 700;
  color: rgba(255, 255, 255, 0.55);
}

.mph-frame--on .mph-frame-no {
  color: #04120C;
}

.mph-runs {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 2px;
  padding: 5px 4px 3px;
  height: max(19px, 2.4cqh);
}

.mph-run {
  position: relative;
  height: 2px;
  border-radius: 9999px;
  background: var(--accent, #4ADE80);
  opacity: 0.75;
}

.mph-run--quiet {
  opacity: 0.22;
}

.mph-run-name {
  position: absolute;
  left: 50%;
  top: 4px;
  transform: translateX(-50%);
  font-size: max(8px, 0.74cqw);
  font-weight: 600;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.42);
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ==================== 窄画幅重排 ====================
   HUD 的字号全部挂在 cqw 上：画幅一窄 cqw 就掉，整条 HUD 会一路缩到 8px 下限，
   胶片条上的月份数字只剩 10px——全场最小的字就出在这里。
   非 16:9 的画幅一律换成放大后的固定字号（宽度够，缺的只是敢不敢写大），
   胶片格、桂冠、场次牌也跟着长大。长廊本身的重排在 JS 里
   （resolvePosterFit 双轴 fit + 竖幅收紧 STEP + 竖幅海报版式 posterMode/posterTS）。 */
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-slate-k { font-size: 15px; letter-spacing: 0.14em; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-slate-no { font-size: 46px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-slate-en { font-size: 17px; letter-spacing: 0.1em; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-slate { gap: 12px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-marquee { gap: 24px; }

[data-frame-tier]:not([data-frame-tier="wide"]) .mph-laurel-leaf { width: 34px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-laurel { gap: 6px; padding: 4px 10px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-laurel-k,
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-laurel-s { font-size: 15px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-laurel-v { font-size: 27px; }

/* 竖幅下桂冠只剩半条 HUD 宽：名字改成换行，别再被 nowrap 顶出画面 */
[data-frame-tier="portrait"] .mph-laurel-v,
[data-frame-tier="tall"] .mph-laurel-v {
  white-space: normal;
  text-align: center;
  max-width: 240px;
  line-height: 1.22;
}

/* 12 格横排，9:16 下一格也有 70px 宽：数字放到 19px 才读得出来，格子同步加高 */
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-frame-no { font-size: 19px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-frame { height: 34px; border-radius: 3px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-frames { gap: 3px; padding: 4px 5px; }
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-perf {
  height: 9px;
  background-image: radial-gradient(circle at 9px 50%, rgba(255, 255, 255, 0.26) 2.8px, transparent 3px);
  background-size: 24px 100%;
}

[data-frame-tier]:not([data-frame-tier="wide"]) .mph-run-name { font-size: 17px; }

/* 一格只有六七十像素宽：主演名放开省略号，改成换行，
   .mph-runs 同步留出三行的余量（RO 已经观察胶片条，长高会重算画布） */
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-run-name {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  line-height: 1.15;
  letter-spacing: 0.04em;
  top: 6px;
  width: 100%;
  text-align: center;
}

[data-frame-tier]:not([data-frame-tier="wide"]) .mph-runs {
  height: auto;
  padding: 8px 5px 66px;
}

[data-frame-tier]:not([data-frame-tier="wide"]) .mph-run { height: 3px; }

/* 场次牌钉在胶片条正上方：cqh 在竖幅（舞台更高）下会把它推进胶片条里 */
[data-frame-tier]:not([data-frame-tier="wide"]) .mph-marquee { bottom: 150px; }
</style>
