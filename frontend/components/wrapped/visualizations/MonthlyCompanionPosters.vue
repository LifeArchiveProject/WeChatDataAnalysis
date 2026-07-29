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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { MONTH_CN, MONTH_EN, mod12, useMonthlyCompanions } from '~/composables/useMonthlyCompanions'

const props = defineProps({
  months: { type: Array, default: () => [] },
  summary: { type: Object, default: null },
  year: { type: Number, default: 0 },
  active: { type: Boolean, default: true }
})

const reducedMotion = useReducedMotion()
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

const drawPoster = (ctx, index) => {
  const item = monthItems.value[index] || {}
  const winner = item.winner || null
  const accentColor = colorOfIndex(index)
  const name = nameOfIndex(index) || '空 缺'
  const img = avatars[index]
  const isChampionMonth = !!champion.value && String(item?.winner?.username || '') === String(champion.value.username || '')

  ctx.clearRect(0, 0, P_W, P_H)
  ctx.textAlign = 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = FIELD
  ctx.fillRect(0, 0, P_W, P_H)

  // ---- 主视觉 ----
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, 0, P_W, ART_H)
  ctx.clip()

  if (img && img.width) {
    const s = Math.max(P_W / img.width, ART_H / img.height)
    ctx.filter = privacyMode.value
      ? 'blur(30px) contrast(1.1) saturate(0.8)'
      : 'contrast(1.1) saturate(0.86) brightness(1.02)'
    ctx.drawImage(img, (P_W - img.width * s) / 2, (ART_H - img.height * s) / 2, img.width * s, img.height * s)
    ctx.filter = 'none'
  } else {
    const g = ctx.createLinearGradient(0, 0, P_W, ART_H)
    g.addColorStop(0, shade(accentColor, 0.35))
    g.addColorStop(1, FIELD)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, P_W, ART_H)
    ctx.fillStyle = `${accentColor}66`
    ctx.font = `700 220px ${SANS}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(winner ? name[0] : '·', P_W / 2, ART_H * 0.46)
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
  }

  // 调色：暗部压向陪伴色，亮部留暖
  ctx.globalCompositeOperation = 'multiply'
  const grade = ctx.createLinearGradient(0, 0, 0, ART_H)
  grade.addColorStop(0, '#FFF3E2')
  grade.addColorStop(0.55, '#FFFFFF')
  grade.addColorStop(1, shade(accentColor, 0.78))
  ctx.fillStyle = grade
  ctx.fillRect(0, 0, P_W, ART_H)

  ctx.globalCompositeOperation = 'screen'
  ctx.fillStyle = `${accentColor}1A`
  ctx.fillRect(0, 0, P_W, ART_H)
  ctx.globalCompositeOperation = 'source-over'

  // 主视觉压到海报底色里
  const fade = ctx.createLinearGradient(0, ART_H * 0.5, 0, ART_H)
  fade.addColorStop(0, 'rgba(6,16,12,0)')
  fade.addColorStop(0.74, 'rgba(6,16,12,0.68)')
  fade.addColorStop(1, FIELD)
  ctx.fillStyle = fade
  ctx.fillRect(0, ART_H * 0.5, P_W, ART_H * 0.5)

  // 暗角
  const vig = ctx.createRadialGradient(P_W / 2, ART_H * 0.42, ART_H * 0.2, P_W / 2, ART_H * 0.42, ART_H * 0.86)
  vig.addColorStop(0, 'rgba(0,0,0,0)')
  vig.addColorStop(1, 'rgba(0,0,0,0.42)')
  ctx.fillStyle = vig
  ctx.fillRect(0, 0, P_W, ART_H)
  ctx.restore()

  // 片号
  ctx.fillStyle = 'rgba(255,255,255,0.5)'
  ctx.font = `600 22px ${NUM}`
  ctx.letterSpacing = '6px'
  ctx.fillText(`NO. ${pad2(index + 1)}`, 44, 66)
  ctx.letterSpacing = '0px'

  // 桂冠：这个月的主演正是年度主演
  if (isChampionMonth) {
    drawLaurel(ctx, P_W - 112, 92, 54, 'rgba(255,255,255,0.7)')
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = 'rgba(255,255,255,0.78)'
    ctx.font = `700 19px ${SANS}`
    ctx.fillText('年度', P_W - 112, 86)
    ctx.fillText('主演', P_W - 112, 108)
    ctx.restore()
  }

  // ---- 文字区 ----
  const cx = P_W / 2
  ctx.textAlign = 'center'

  // 出品行
  ctx.fillStyle = 'rgba(255,255,255,0.34)'
  ctx.font = `600 22px ${SANS}`
  ctx.letterSpacing = '8px'
  ctx.fillText('微信年度总结 呈现', cx, ART_H + 52)
  ctx.letterSpacing = '0px'

  // 标语
  ctx.fillStyle = 'rgba(255,255,255,0.6)'
  const tagline = `「${quoteOfIndex(index)}」`
  fitFont(ctx, tagline, P_W - 88, 31, '400', SANS, 21)
  ctx.fillText(tagline, cx, ART_H + 116)

  // 片名 = 那个月陪你最多的人（隐私模式：名字在画布里直接糊掉，强度随字号）
  const titleSize = fitFont(ctx, name, P_W - 96, 104, '800', SANS, 48)
  ctx.fillStyle = winner ? '#FFFFFF' : 'rgba(255,255,255,0.34)'
  ctx.font = `800 ${titleSize}px ${SANS}`
  ctx.letterSpacing = `${Math.round(titleSize * 0.06)}px`
  if (privacyMode.value && winner) ctx.filter = `blur(${Math.max(10, Math.round(titleSize * 0.36))}px)`
  ctx.fillText(name, cx + Math.round(titleSize * 0.03), ART_H + 232)
  ctx.filter = 'none'
  ctx.letterSpacing = '0px'

  ctx.fillStyle = accentColor
  ctx.fillRect(cx - 58, ART_H + 266, 116, 4)

  ctx.fillStyle = 'rgba(255,255,255,0.46)'
  ctx.font = `600 23px ${NUM}`
  ctx.letterSpacing = '8px'
  ctx.fillText(`${MONTH_CN[index]} · ${MONTH_EN[index]} · ${props.year || ''}`, cx + 5, ART_H + 314)
  ctx.letterSpacing = '0px'

  // ---- 演职员表 ----
  const cells = statsOfIndex(index)
  let by = ART_H + 402
  ctx.strokeStyle = 'rgba(255,255,255,0.16)'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(64, ART_H + 360)
  ctx.lineTo(P_W - 64, ART_H + 360)
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
const STEP = 0.118                  // 相邻两张海报的夹角
const CARD_H = 3.34
const CARD_W = CARD_H * (P_W / P_H)
const PERIOD = 12 * STEP

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
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearAlpha(0)

  scene = new THREE.Scene()
  scene.fog = new THREE.Fog(0x08110D, 1, 2)
  camera = new THREE.PerspectiveCamera(34, 1, 0.1, 90)

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

      copies.push({ mesh, mirror, angle: a })
    }

    posters.push({ copies, mat, mirrorMat, tex, cv })
  }
}

const syncCamera = () => {
  if (!camera || !renderer || !stageEl.value) return
  const box = stageEl.value
  const film = box.querySelector('.mph-film')
  const marquee = box.querySelector('.mph-marquee')
  const reserved = (film ? film.offsetHeight : 0) + (marquee ? marquee.offsetHeight : 0) + 22
  const w = Math.max(1, Math.round(box.clientWidth))
  const h = Math.max(1, Math.round(box.clientHeight - reserved))
  viewport.w = w
  viewport.h = h
  const aspect = w / h
  const halfTan = Math.tan((camera.fov * Math.PI) / 360)
  const dist = (CARD_H * 1.06) / (2 * halfTan)
  if (scene?.fog) {
    scene.fog.near = dist + 1.4
    scene.fog.far = dist + 10.5
  }
  camera.position.set(0, -CARD_H * 0.03, dist)
  camera.lookAt(0, -CARD_H * 0.09, 0)
  camera.aspect = aspect
  camera.updateProjectionMatrix()
  renderer.setSize(w, h, false)
  if (canvasEl.value) canvasEl.value.style.height = `${h}px`
}

const goTo = (index) => {
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
}

const tick = () => {
  rafId = requestAnimationFrame(tick)
  if (destroyed || !renderer || !scene || !camera) return
  if (viewport.w <= 1) return
  const now = performance.now()
  const dt = lastT ? Math.min(0.05, (now - lastT) / 1000) : 1 / 60
  lastT = now
  step(dt)
  const px = reducedMotion.value ? 0 : pointer.x * 0.3
  const py = reducedMotion.value ? 0 : pointer.y * 0.14
  camera.position.x += (px - camera.position.x) * 0.06
  camera.position.y += ((-CARD_H * 0.03 - py) - camera.position.y) * 0.06
  camera.lookAt(camera.position.x * 0.4, -CARD_H * 0.09, 0)
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
  const dx = e.clientX - drag.lastX
  drag.lastX = e.clientX
  drag.moved += Math.abs(dx)
  const d = dx * 0.0024
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
  const box = stageEl.value
  if (!box) return
  const r = box.getBoundingClientRect()
  const ndc = new THREE.Vector2(
    ((e.clientX - r.left) / r.width) * 2 - 1,
    -(((e.clientY - r.top) / viewport.h) * 2 - 1)
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
    buildScene()
    syncCamera()
    const land = championHomeIndex.value
    cur.value = land
    rot.target = -land * STEP
    // 入场：镜头从长廊深处横移过来，停在年度主演那张
    rot.current = reducedMotion.value ? rot.target : rot.target - STEP * 4.6
    startLoop()
    if (typeof ResizeObserver !== 'undefined' && stageEl.value) {
      ro = new ResizeObserver(() => syncCamera())
      ro.observe(stageEl.value)
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
</style>
