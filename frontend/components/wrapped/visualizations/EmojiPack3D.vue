<template>
  <div ref="rootEl" class="p3-root" data-deck-nodrag>
    <canvas ref="canvasEl" class="p3-canvas" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'

/**
 * 年度卡包（3D）。
 *
 * CSS 贴渐变的平面 div 做不出箔膜的「贵」——没有厚度、没有真实反光、镜头也不会动。
 * 这里换成真物体：圆角盒 + MeshPhysicalMaterial 的 iridescence（薄膜干涉，就是彩虹箔的物理成因）
 * + PMREM 预滤的棚灯环境贴图，转动时高光会沿着袋面扫过去。
 * 撕口是逐顶点折起来的一条 ribbon，不是把 div 遮一半。
 */

const props = defineProps({
  year: { type: Number, default: 0 },
  sentCount: { type: Number, default: 0 },
  typeCount: { type: Number, default: 0 },
  cardCount: { type: Number, default: 7 },
  heroColor: { type: String, default: '#C08BFF' },
  // 袋口露出来的那张表情（撕开后第一个发出来的），没有就退回纯色卡背
  nextSrc: { type: String, default: '' },
  active: { type: Boolean, default: true },
  reducedMotion: { type: Boolean, default: false }
})

const emit = defineEmits(['opened', 'progress'])

const rootEl = ref(null)
const canvasEl = ref(null)

let THREE = null
let renderer = null
let scene = null
let camera = null
let packGroup = null
let bodyMesh = null
let artMesh = null
let stripFront = null
let stripBack = null
let stripBaseAttr = null
let mouthGroup = null
let stackMesh = null
let glowMesh = null
let envRT = null
const disposables = []

let raf = 0
let destroyed = false
let ready = false

const PACK_W = 1.0
const PACK_H = 1.46
const PACK_D = 0.085
const STRIP_H = 0.2

let rip = 0
let opened = false
const pointer = { x: 0, y: 0, tx: 0, ty: 0 }
let clock = 0

const fmt = (n) => Math.round(Number(n) || 0).toLocaleString('zh-CN')

// ---------- 棚灯环境 ----------
// 纯金属没有漫反射，颜色 100% 来自环境反射：环境暗 → 卡包就是黑的。
// 所以底子用 three 自带的 RoomEnvironment（明亮棚拍），再叠几条彩色灯管，
// 转动时箔面才有东西可反、也才有颜色。
const buildEnvTexture = () => {
  const cv = document.createElement('canvas')
  cv.width = 1024
  cv.height = 512
  const g = cv.getContext('2d')

  const base = g.createLinearGradient(0, 0, 0, 512)
  base.addColorStop(0, '#FFF6E3')
  base.addColorStop(0.38, '#D9C99C')
  base.addColorStop(0.7, '#5A6B54')
  base.addColorStop(1, '#1B2A20')
  g.fillStyle = base
  g.fillRect(0, 0, 1024, 512)

  const bar = (cx, cy, w, h, color, alpha) => {
    const rg = g.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h))
    rg.addColorStop(0, color)
    rg.addColorStop(1, 'rgba(0,0,0,0)')
    g.globalAlpha = alpha
    g.save()
    g.translate(cx, cy)
    g.scale(1, h / w)
    g.translate(-cx, -cy)
    g.fillStyle = rg
    g.beginPath()
    g.arc(cx, cy, w, 0, Math.PI * 2)
    g.fill()
    g.restore()
    g.globalAlpha = 1
  }

  bar(300, 130, 430, 95, '#FFFFFF', 1)
  bar(780, 190, 340, 80, '#FFE9BE', 0.95)
  bar(520, 400, 520, 120, '#FFC49A', 0.55)
  bar(70, 320, 300, 70, '#A9F5D8', 0.45)

  const tex = new THREE.CanvasTexture(cv)
  tex.mapping = THREE.EquirectangularReflectionMapping
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

// ---------- 袋面印刷 ----------
// 只有几行字＝一块背景板。这里按真实卡包的平面语言排：
// 棱镜纹底 + 内框 + 顶栏厂牌 + 中央菱形徽记 + 标题区 + 底部条码。
// 大量图形用低透明度白，让底下的箔膜透上来，才像「印在箔纸上」而不是贴了张图。
const buildArtTexture = () => {
  const W = 640
  const H = 900
  const cv = document.createElement('canvas')
  cv.width = W
  cv.height = H
  const g = cv.getContext('2d')
  const cjk = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif'
  const hero = props.heroColor

  g.clearRect(0, 0, W, H)

  // ① 棱镜纹：斜向细条纹，箔纸最典型的底纹
  g.save()
  g.translate(W / 2, H / 2)
  g.rotate(-0.42)
  for (let i = -60; i < 60; i += 1) {
    g.globalAlpha = i % 5 === 0 ? 0.10 : 0.045
    g.fillStyle = '#FFFFFF'
    g.fillRect(i * 22, -H, i % 5 === 0 ? 5 : 2, H * 2)
  }
  g.restore()
  g.globalAlpha = 1

  // ② 中央光带：一道斜向高光，给平面一点「反光」的错觉
  const sweep = g.createLinearGradient(0, H * 0.22, W, H * 0.66)
  sweep.addColorStop(0, 'rgba(255,255,255,0)')
  sweep.addColorStop(0.46, 'rgba(255,255,255,0.16)')
  sweep.addColorStop(0.54, 'rgba(255,255,255,0.05)')
  sweep.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = sweep
  g.fillRect(0, 0, W, H)

  // ③ 金框 + 装饰艺术角扇（与卡背同一套框架语言）
  g.strokeStyle = 'rgba(227,190,107,0.85)'
  g.lineWidth = 5
  g.strokeRect(30, 30, W - 60, H - 60)
  g.strokeStyle = 'rgba(239,223,175,0.4)'
  g.lineWidth = 1.5
  g.strokeRect(48, 48, W - 96, H - 96)
  const fan = (cx, cy, sx, sy) => {
    g.save()
    g.translate(cx, cy)
    g.scale(sx, sy)
    const tri = (s, color) => {
      g.fillStyle = color
      g.beginPath()
      g.moveTo(0, 0)
      g.lineTo(s, 0)
      g.lineTo(0, s)
      g.closePath()
      g.fill()
    }
    tri(60, 'rgba(231,196,118,0.95)')
    tri(39, 'rgba(11,29,20,0.96)')
    tri(22, 'rgba(247,227,168,0.95)')
    g.restore()
  }
  fan(48, 48, 1, 1)
  fan(W - 48, 48, -1, 1)
  fan(48, H - 48, 1, -1)
  fan(W - 48, H - 48, -1, -1)

  // ④ 顶栏：厂牌 + 年份，中间一条分隔线
  g.fillStyle = 'rgba(239,223,175,0.9)'
  g.font = `600 19px ${cjk}`
  g.letterSpacing = '7px'
  g.fillText('WECHAT WRAPPED', 62, 96)
  g.letterSpacing = '4px'
  g.fillStyle = hero
  g.font = `700 19px ${cjk}`
  const yr = String(props.year || '')
  g.fillText(yr, W - 62 - g.measureText(yr).width, 96)
  g.letterSpacing = '0px'
  g.strokeStyle = 'rgba(227,190,107,0.35)'
  g.lineWidth = 1
  g.beginPath()
  g.moveTo(62, 118)
  g.lineTo(W - 62, 118)
  g.stroke()

  // ⑤ 中央徽记：实心金箔菱徽 + 阴刻笑脸 + 八向金短芒（与卡背同一枚标）
  const ex = W / 2
  const ey = 330
  g.save()
  g.translate(ex, ey)

  g.fillStyle = 'rgba(240,214,140,0.92)'
  for (let i = 0; i < 8; i += 1) {
    const a = (i / 8) * Math.PI * 2
    const txr = Math.cos(a) * 168
    const tyr = Math.sin(a) * 168
    const bxr = Math.cos(a) * 128
    const byr = Math.sin(a) * 128
    const px = -Math.sin(a) * 10
    const py = Math.cos(a) * 10
    g.beginPath()
    g.moveTo(txr, tyr)
    g.lineTo(bxr + px, byr + py)
    g.lineTo(bxr - px, byr - py)
    g.closePath()
    g.fill()
  }

  // 金箔菱面：渐层填充 + 凿刻高光/暗边 + 内圈刻线
  const gold = g.createLinearGradient(-90, -90, 90, 90)
  gold.addColorStop(0, '#F7E3A8')
  gold.addColorStop(0.45, '#E3BE6B')
  gold.addColorStop(1, '#A97F35')
  g.save()
  g.rotate(Math.PI / 4)
  const R = 86
  g.fillStyle = gold
  g.beginPath()
  g.roundRect(-R, -R, R * 2, R * 2, 10)
  g.fill()
  g.strokeStyle = '#7A5C1F'
  g.lineWidth = 3
  g.stroke()
  g.strokeStyle = 'rgba(251,239,196,0.9)'
  g.lineWidth = 3.5
  g.beginPath()
  g.moveTo(-R + 8, R - 12)
  g.lineTo(-R + 8, -R + 8)
  g.lineTo(R - 12, -R + 8)
  g.stroke()
  g.strokeStyle = 'rgba(110,83,34,0.9)'
  g.beginPath()
  g.moveTo(R - 8, -R + 12)
  g.lineTo(R - 8, R - 8)
  g.lineTo(-R + 12, R - 8)
  g.stroke()
  g.strokeStyle = 'rgba(140,107,38,0.9)'
  g.lineWidth = 2
  g.beginPath()
  g.roundRect(-R + 18, -R + 18, (R - 18) * 2, (R - 18) * 2, 7)
  g.stroke()
  g.restore()

  // 阴刻笑脸：刻进金面的墨绿，下缘一道受光刻缘
  g.fillStyle = '#11291B'
  g.beginPath()
  g.arc(-30, -16, 10, 0, Math.PI * 2)
  g.fill()
  g.beginPath()
  g.arc(30, -16, 10, 0, Math.PI * 2)
  g.fill()
  g.strokeStyle = '#11291B'
  g.lineWidth = 10
  g.lineCap = 'round'
  g.beginPath()
  g.arc(0, 4, 44, 0.28 * Math.PI, 0.72 * Math.PI)
  g.stroke()
  g.strokeStyle = 'rgba(251,239,196,0.5)'
  g.lineWidth = 2.5
  g.beginPath()
  g.arc(0, 1, 44, 0.3 * Math.PI, 0.7 * Math.PI)
  g.stroke()
  g.restore()

  // ⑥ 标题区
  g.fillStyle = '#F8F3E4'
  g.shadowColor = 'rgba(0,0,0,0.5)'
  g.shadowBlur = 16
  g.font = `800 76px ${cjk}`
  g.letterSpacing = '3px'
  g.fillText('表情包', 62, H - 258)
  g.fillText('年度卡包', 62, H - 176)
  g.shadowBlur = 0

  g.fillStyle = 'rgba(239,223,175,0.72)'
  g.font = `400 24px ${cjk}`
  g.letterSpacing = '1px'
  g.fillText(`${fmt(props.sentCount)} 次发送 · ${fmt(props.typeCount)} 种收录`, 62, H - 128)

  // ⑦ 底部：金箔张数徽章 + 条码，把版面压住
  const badge = `${props.cardCount} CARDS`
  g.font = `700 22px ${cjk}`
  g.letterSpacing = '5px'
  const bw = g.measureText(badge).width + 36
  const grd = g.createLinearGradient(62, 0, 62 + bw, 0)
  grd.addColorStop(0, '#F7E3A8')
  grd.addColorStop(1, '#D8B15E')
  g.fillStyle = grd
  g.beginPath()
  g.roundRect(62, H - 104, bw, 42, 8)
  g.fill()
  g.fillStyle = '#123024'
  g.fillText(badge, 80, H - 75)

  g.letterSpacing = '0px'
  let bx = W - 62
  for (let i = 0; i < 26; i += 1) {
    const w = 1 + (i % 4 === 0 ? 3 : (i % 3 === 0 ? 2 : 1))
    bx -= w + 3
    g.globalAlpha = 0.3 + (i % 3) * 0.14
    g.fillStyle = '#EFDFAF'
    g.fillRect(bx, H - 100, w, 34)
  }
  g.globalAlpha = 1

  const tex = new THREE.CanvasTexture(cv)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = renderer?.capabilities?.getMaxAnisotropy?.() || 1
  return tex
}

// 箔膜的细闪：粗糙度贴图里撒噪点，高光就会碎成一粒粒金属闪片。
// 注意 roughnessMap 是「乘」到 roughness 上的，所以基准值必须接近 255，
// 否则整体粗糙度被乘到接近 0，卡包就变成一面镜子（照到什么是什么，很容易全黑）。
const buildFlakeRoughness = () => {
  const S = 512
  const cv = document.createElement('canvas')
  cv.width = S
  cv.height = S
  const g = cv.getContext('2d')
  const img = g.createImageData(S, S)
  const d = img.data
  for (let i = 0; i < d.length; i += 4) {
    const n = Math.random()
    const v = n > 0.965 ? 110 : (n > 0.9 ? 190 : 232 + Math.random() * 23)
    d[i] = d[i + 1] = d[i + 2] = v
    d[i + 3] = 255
  }
  g.putImageData(img, 0, 0)
  const tex = new THREE.CanvasTexture(cv)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.repeat.set(3, 4)
  return tex
}

// 撕条的印刷。做成 map 贴到金属材质上：白＝原样反射箔色，深色＝压暗，
// 相当于「印在箔纸上的油墨」；而且贴图跟着顶点一起变形，卷起来时印刷也跟着卷。
const buildStripTexture = () => {
  const W = 1024
  const H = 200
  const cv = document.createElement('canvas')
  cv.width = W
  cv.height = H
  const g = cv.getContext('2d')
  const cjk = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif'

  // 金封条：像礼盒上那一圈金箔封贴
  const band = g.createLinearGradient(0, 0, 0, H)
  band.addColorStop(0, '#F4E2AC')
  band.addColorStop(0.5, '#E0BE72')
  band.addColorStop(1, '#C09A4C')
  g.fillStyle = band
  g.fillRect(0, 0, W, H)

  // 撕线：一排齿孔，压暗成小圆点
  g.fillStyle = 'rgba(18,48,32,0.5)'
  for (let x = 18; x < W - 12; x += 26) {
    g.beginPath()
    g.arc(x, H - 26, 5, 0, Math.PI * 2)
    g.fill()
  }

  // 撕开指引印在封条上（真封条都这么印），箭头指向撕的方向
  g.fillStyle = 'rgba(18,48,32,0.85)'
  g.font = `700 34px ${cjk}`
  g.letterSpacing = '8px'
  g.fillText('沿封口撕开 ▸', 34, 76)

  // 厂牌字样
  g.fillStyle = 'rgba(18,48,32,0.7)'
  g.font = `700 34px ${cjk}`
  g.letterSpacing = '14px'
  const label = 'WECHAT WRAPPED'
  g.fillText(label, W - g.measureText(label).width - 40, 76)

  // 两端各压一道暗边，让封条有卷边的厚度暗示
  const edge = g.createLinearGradient(0, 0, 0, H)
  edge.addColorStop(0, 'rgba(90,66,20,0.45)')
  edge.addColorStop(0.16, 'rgba(255,255,255,0)')
  edge.addColorStop(0.86, 'rgba(255,255,255,0)')
  edge.addColorStop(1, 'rgba(90,66,20,0.5)')
  g.fillStyle = edge
  g.fillRect(0, 0, W, H)

  const tex = new THREE.CanvasTexture(cv)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = renderer?.capabilities?.getMaxAnisotropy?.() || 1
  return tex
}

// 袋口那摞卡的贴图：底下几张的侧棱 + 最上面那张露出上半截的表情
const buildStackTexture = () => {
  const W = 512
  const H = 190
  const cv = document.createElement('canvas')
  cv.width = W
  cv.height = H
  const g = cv.getContext('2d')

  // 垛的纸边底色：真卡垛侧面是米白纸色（和台面上那叠一致）
  const base = g.createLinearGradient(0, 0, 0, H)
  base.addColorStop(0, '#F0EAD8')
  base.addColorStop(0.55, '#DDD5BC')
  base.addColorStop(1, '#BBB295')
  g.fillStyle = base
  g.fillRect(0, 0, W, H)

  // 下面还压着几张：右下角错开的卡边
  g.strokeStyle = 'rgba(120,105,70,0.35)'
  g.lineWidth = 2
  for (let i = 1; i <= 3; i += 1) {
    g.beginPath()
    g.moveTo(W - 8 - i * 7, H)
    g.lineTo(W - 8 - i * 7, 26 + i * 8)
    g.stroke()
  }

  // 袋口内的落影，越往上越暗
  const sh = g.createLinearGradient(0, 0, 0, H * 0.6)
  sh.addColorStop(0, 'rgba(6,12,9,0.62)')
  sh.addColorStop(1, 'rgba(6,12,9,0)')
  g.fillStyle = sh
  g.fillRect(0, 0, W, H * 0.6)

  const tex = new THREE.CanvasTexture(cv)
  tex.colorSpace = THREE.SRGBColorSpace
  stackCanvas = cv
  stackTexRef = tex
  paintStackSticker()
  return tex
}

// 把下一张表情画到那摞卡的最上面一张上（图片异步到达，到了再重绘）
let stackCanvas = null
let stackTexRef = null
let stackImg = null
const paintStackSticker = () => {
  const cv = stackCanvas
  const tex = stackTexRef
  const src = String(props.nextSrc || '')
  if (!cv || !tex || !src) return
  if (!stackImg || stackImg.dataset.src !== src) {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.dataset.src = src
    img.onload = () => {
      if (destroyed || stackImg !== img) return
      drawStackSticker(img)
    }
    img.onerror = () => {}
    stackImg = img
    img.src = src
    return
  }
  if (stackImg.complete && stackImg.naturalWidth > 0) drawStackSticker(stackImg)
}

const drawStackSticker = (img) => {
  const cv = stackCanvas
  const tex = stackTexRef
  if (!cv || !tex) return
  const g = cv.getContext('2d')
  const W = cv.width
  const H = cv.height
  // 只露出这张卡的上半截，像是刚从袋口冒出来
  const cardW = Math.round(W * 0.62)
  const cardH = Math.round(H * 1.5)
  const x = Math.round((W - cardW) / 2)
  const y = Math.round(H * 0.30)

  g.save()
  g.beginPath()
  g.roundRect(x, y, cardW, cardH, 12)
  g.clip()
  // nextSrc 现在是整张卡背版面：满幅画进卡片矩形，不再垫白框
  const dh = img.naturalWidth > 0 ? cardW * (img.naturalHeight / img.naturalWidth) : cardH
  g.drawImage(img, x, y, cardW, Math.max(dh, cardH))
  g.restore()

  g.strokeStyle = 'rgba(122,92,31,0.55)'
  g.lineWidth = 2
  g.beginPath()
  g.roundRect(x, y, cardW, cardH, 12)
  g.stroke()

  // 袋口的落影压回去，保证这张卡是「在袋子里」
  const sh = g.createLinearGradient(0, 0, 0, H * 0.55)
  sh.addColorStop(0, 'rgba(6,12,9,0.66)')
  sh.addColorStop(1, 'rgba(6,12,9,0)')
  g.fillStyle = sh
  g.fillRect(0, 0, W, H * 0.55)

  tex.needsUpdate = true
}

const radialTexture = (stops) => {
  const S = 256
  const cv = document.createElement('canvas')
  cv.width = cv.height = S
  const g = cv.getContext('2d')
  const rg = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2)
  for (const [o, c] of stops) rg.addColorStop(o, c)
  g.fillStyle = rg
  g.fillRect(0, 0, S, S)
  return new THREE.CanvasTexture(cv)
}

const build = async () => {
  const mod = await import('three')
  THREE = mod.default || mod
  if (destroyed) return
  const { RoundedBoxGeometry } = await import('three/examples/jsm/geometries/RoundedBoxGeometry.js')
  if (destroyed || !canvasEl.value) return

  renderer = new THREE.WebGLRenderer({
    canvas: canvasEl.value,
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance'
  })
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.15
  renderer.setClearAlpha(0)

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50)
  camera.position.set(0, 0, 4.4)

  // 环境反射：PMREM 预滤后，iridescence 才有东西可以折射出彩虹
  const envTex = buildEnvTexture()
  const pmrem = new THREE.PMREMGenerator(renderer)
  pmrem.compileEquirectangularShader()
  envRT = pmrem.fromEquirectangular(envTex)
  scene.environment = envRT.texture
  envTex.dispose()
  pmrem.dispose()

  scene.add(new THREE.AmbientLight(0xffffff, 0.35))
  const key = new THREE.DirectionalLight(0xffffff, 2.1)
  key.position.set(-1.6, 2.2, 2.4)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xf0c97e, 1.3)
  rim.position.set(2.2, -0.6, -1.4)
  scene.add(rim)

  packGroup = new THREE.Group()
  scene.add(packGroup)

  const flakes = buildFlakeRoughness()
  disposables.push(flakes)

  // 袋身：圆角盒＝有厚度、有软边，光滑过渡才不像贴纸
  const bodyGeo = new RoundedBoxGeometry(PACK_W, PACK_H, PACK_D, 5, 0.03)
  const foilMat = new THREE.MeshPhysicalMaterial({
    // 孔雀石绿底色：金属只反环境，底色决定它把环境「染」成什么颜色——和卡背同一套金绿语系
    color: new THREE.Color('#46916A'),
    metalness: 0.92,
    roughness: 0.34,
    roughnessMap: flakes,
    // 薄膜干涉：彩虹箔的物理成因，随视角连续变色
    iridescence: 1,
    iridescenceIOR: 1.34,
    iridescenceThicknessRange: [120, 780],
    envMapIntensity: 1.55,
    clearcoat: 1,
    clearcoatRoughness: 0.14
  })
  bodyMesh = new THREE.Mesh(bodyGeo, foilMat)
  packGroup.add(bodyMesh)
  disposables.push(bodyGeo, foilMat)

  // 印刷层：贴在袋面前方一丁点，文字不会被金属度吃掉
  // 印刷区只占撕条以下的部分，否则顶栏会被撕条盖掉（之前「2025」就是这么被切一半的）
  const artTex = buildArtTexture()
  const artH = PACK_H - STRIP_H
  const artGeo = new THREE.PlaneGeometry(PACK_W, artH)
  const artMat = new THREE.MeshBasicMaterial({ map: artTex, transparent: true, depthWrite: false })
  artMesh = new THREE.Mesh(artGeo, artMat)
  artMesh.position.z = PACK_D / 2 + 0.002
  artMesh.position.y = -STRIP_H / 2
  packGroup.add(artMesh)
  disposables.push(artTex, artGeo, artMat)

  // 袋口：撕开后露出的暗腔 + 亮边 + 里面那摞卡
  mouthGroup = new THREE.Group()
  mouthGroup.position.y = PACK_H / 2 - STRIP_H * 0.5
  packGroup.add(mouthGroup)

  // 袋口内壁：上深下浅的渐变 + 顶边一道亮光，
  // 纯色填充会变成一块生硬的黑矩形，看着像渲染破了个洞
  const mouthCv = document.createElement('canvas')
  mouthCv.width = 8
  mouthCv.height = 128
  {
    const mg = mouthCv.getContext('2d')
    const grd = mg.createLinearGradient(0, 0, 0, 128)
    grd.addColorStop(0, 'rgba(240,220,160,0.9)')
    grd.addColorStop(0.06, 'rgba(6,14,10,1)')
    grd.addColorStop(0.55, 'rgba(9,18,13,0.96)')
    grd.addColorStop(1, 'rgba(13,24,17,0)')
    mg.fillStyle = grd
    mg.fillRect(0, 0, 8, 128)
  }
  const mouthTex = new THREE.CanvasTexture(mouthCv)
  mouthTex.colorSpace = THREE.SRGBColorSpace
  const mouthGeo = new THREE.PlaneGeometry(PACK_W * 0.97, STRIP_H * 1.05)
  const mouthMat = new THREE.MeshBasicMaterial({ map: mouthTex, transparent: true, depthWrite: false })
  const mouthMesh = new THREE.Mesh(mouthGeo, mouthMat)
  mouthMesh.position.z = PACK_D / 2 + 0.001
  mouthGroup.add(mouthMesh)
  disposables.push(mouthTex, mouthGeo, mouthMat)

  // 袋口里那摞卡：最上面一张就是下一张要发出来的表情，
  // 之前是一块纯色平面，看着就是条白杠
  const stackGeo = new THREE.PlaneGeometry(PACK_W * 0.86, STRIP_H * 0.8)
  const stackTex = buildStackTexture()
  const stackMat = new THREE.MeshBasicMaterial({ map: stackTex, color: 0xffffff, transparent: true })
  stackMesh = new THREE.Mesh(stackGeo, stackMat)
  stackMesh.position.set(0, -STRIP_H * 0.5, PACK_D / 2 + 0.004)
  mouthGroup.add(stackMesh)
  disposables.push(stackGeo, stackMat)
  if (stackTex) disposables.push(stackTex)

  // 撕条：逐顶点折起，正反两片（背面哑光，卷起来才看得出是「撕开了」）
  const stripGeo = new THREE.PlaneGeometry(PACK_W, STRIP_H, 64, 3)
  stripBaseAttr = stripGeo.attributes.position.array.slice(0)
  // 封条是金箔材质：底色换成暖白，让金色印刷贴图自己说话
  // （沿用袋身的物理参数，颜色若还是绿的会把金压成橄榄色）
  const stripMat = foilMat.clone()
  stripMat.color = new THREE.Color('#EDE4CC')
  const stripTex = buildStripTexture()
  stripMat.map = stripTex
  stripMat.transparent = true
  disposables.push(stripTex)
  stripFront = new THREE.Mesh(stripGeo, stripMat)
  stripFront.position.set(0, PACK_H / 2 - STRIP_H / 2, PACK_D / 2 + 0.003)
  packGroup.add(stripFront)
  disposables.push(stripGeo, stripMat)

  const backGeo = stripGeo.clone()
  // 膜的背面是哑光的，别做成刺眼的纯白；金封条的背面是浅卡其纸色
  const backMat = new THREE.MeshStandardMaterial({ color: 0xc4b791, roughness: 0.92, metalness: 0.04, side: THREE.BackSide, transparent: true })
  stripBack = new THREE.Mesh(backGeo, backMat)
  // 必须和正面完全重合：一个 FrontSide 一个 BackSide，本来就不会画到同一个像素，
  // 之前往后挪了 4mm，纸卷过来以后那点偏移就变成并排的两张纸片了
  stripBack.position.copy(stripFront.position)
  packGroup.add(stripBack)
  disposables.push(backGeo, backMat)

  // 袋口透出的一点内光，克制到只够照亮撕口，不做爆炸
  const glowTex = radialTexture([[0, 'rgba(255,255,255,0.9)'], [0.42, props.heroColor], [1, 'rgba(0,0,0,0)']])
  const glowGeo = new THREE.PlaneGeometry(1.5, 0.72)
  const glowMat = new THREE.MeshBasicMaterial({
    map: glowTex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0
  })
  glowMesh = new THREE.Mesh(glowGeo, glowMat)
  glowMesh.position.set(0, PACK_H / 2 - STRIP_H / 2, PACK_D)
  packGroup.add(glowMesh)
  disposables.push(glowTex, glowGeo, glowMat)

  applyRip(0)
  resize()
  ready = true

  // 开场推镜：从远处压过来，比静止的正面图有戏得多
  if (!props.reducedMotion) {
    gsap.fromTo(
      camera.position,
      { z: 5.6 },
      { z: 4.7, duration: 1.5, ease: 'power3.out' }
    )
    gsap.fromTo(
      packGroup.rotation,
      { y: -0.85, x: 0.22 },
      { y: -0.18, x: 0.04, duration: 1.6, ease: 'power3.out' }
    )
  } else {
    camera.position.z = 4.7
    packGroup.rotation.set(0, -0.18, 0)
  }

  loop()
}

// ---------- 撕口：一张纸从左往右被揭开 ----------
// 关键是折痕是一条**竖线**，跟着撕口右移；已揭开的部分绕这条竖线卷回来，
// 盖在还没揭的部分上、露出背面。绕水平轴转只会得到一个扭曲的斜坡，不是揭开。
const CURL_R = 0.05 // 卷起来的半径，越小卷得越紧
const applyRip = (v) => {
  rip = Math.max(0, Math.min(1, v))
  if (!stripFront || !stripBaseAttr) return

  const attr = stripFront.geometry.attributes.position
  const arr = attr.array
  const xf = -PACK_W / 2 + rip * PACK_W // 折痕所在的 x
  const arc = Math.PI * CURL_R // 卷完半圈所需的弧长

  for (let i = 0; i < arr.length; i += 3) {
    const bx = stripBaseAttr[i]
    const by = stripBaseAttr[i + 1]
    const s = xf - bx // >0 表示这个点已经被揭起来了，值＝离折痕多远

    if (s <= 0) {
      arr[i] = bx
      arr[i + 1] = by
      arr[i + 2] = 0
      continue
    }

    if (s < arc) {
      // 正在绕折痕卷起的那一段
      const th = s / CURL_R
      arr[i] = xf - CURL_R * Math.sin(th)
      arr[i + 2] = CURL_R * (1 - Math.cos(th))
    } else {
      // 已经翻过来的平坦部分，贴在未揭开的那半上方，继续往右伸
      arr[i] = xf + (s - arc)
      arr[i + 2] = 2 * CURL_R
    }
    // 翻过来的部分带一点自重下垂，别像块铁皮
    arr[i + 1] = by - Math.min(0.05, s * 0.06)
  }
  attr.needsUpdate = true
  stripFront.geometry.computeVertexNormals()

  const battr = stripBack.geometry.attributes.position
  battr.array.set(arr)
  battr.needsUpdate = true
  stripBack.geometry.computeVertexNormals()

  // 袋口跟着撕口敞开
  if (mouthGroup) {
    mouthGroup.scale.x = Math.max(0.0001, rip)
    mouthGroup.position.x = -(PACK_W / 2) * (1 - rip)
  }
  if (stackMesh) stackMesh.position.y = -STRIP_H * 0.5 + rip * STRIP_H * 0.42
  emit('progress', rip)
}

const setRip = (v) => applyRip(v)

// 撕口在画布上的像素位置。卡包开完就会下沉，所以要在爆光那一刻先算好存住，
// 喷洒层拿它当喷发原点，表情才是真的从袋口冒出来。
let mouthAtOpen = null
const captureMouth = () => {
  const el = rootEl.value
  if (!THREE || !camera || !packGroup || !el) return
  const w = el.clientWidth
  const h = el.clientHeight
  if (!w || !h) return
  const r = el.getBoundingClientRect()
  const my = PACK_H / 2 - STRIP_H / 2
  // 投影撕口的左右两端，而不是一个中心点：喷洒层在这条线段上随机取点，
  // 表情才是沿整个袋口宽度冒出来的，也自动跟着卡包的透视和旋转走。
  const project = (lx) => {
    const v = new THREE.Vector3(lx, my, PACK_D / 2)
    packGroup.localToWorld(v)
    v.project(camera)
    return { x: r.left + (v.x * 0.5 + 0.5) * w, y: r.top + (-v.y * 0.5 + 0.5) * h }
  }
  mouthAtOpen = { left: project(-PACK_W / 2), right: project(PACK_W / 2) }
}

const getMouth = () => mouthAtOpen

// ---------- 开包 ----------
const openBurst = () => {
  if (opened) return
  opened = true
  applyRip(1)
  captureMouth()

  if (props.reducedMotion) {
    emit('opened')
    return
  }

  const tl = gsap.timeline()
  // 撕到底就立刻通知外面开喷，别等袋子的收尾动作演完——那段等待看着就是卡了一下
  tl.call(() => emit('opened'), null, 0.12)

  // 撕条脱手翻飞出画，并在半途淡掉——否则它会一直挂在画面里
  tl.to(stripFront.position, { y: PACK_H * 1.35, x: 0.5, z: 1.4, duration: 0.6, ease: 'power2.in' }, 0)
    .to(stripFront.rotation, { x: -2.8, z: 1.1, duration: 0.6, ease: 'power2.in' }, 0)
    .to(stripBack.position, { y: PACK_H * 1.35, x: 0.5, z: 1.39, duration: 0.6, ease: 'power2.in' }, 0)
    .to(stripBack.rotation, { x: -2.8, z: 1.1, duration: 0.6, ease: 'power2.in' }, 0)
    .to([stripFront.material, stripBack.material], {
      opacity: 0,
      duration: 0.34,
      ease: 'power2.in',
      onComplete: () => {
        stripFront.visible = false
        stripBack.visible = false
      }
    }, 0.22)

  // 袋口内光亮一下就收，不做爆炸
  tl.to(glowMesh.material, { opacity: 0.75, duration: 0.12, ease: 'power2.out' }, 0.02)
    .to(glowMesh.material, { opacity: 0, duration: 0.42, ease: 'power2.in' }, 0.2)

  // 卡包不退场：整段喷洒期间它都得留在画面里当喷口，只是轻轻沉一点让出上方空间
  tl.to(packGroup.position, { y: -0.12, duration: 0.5, ease: 'power2.out' }, 0.36)
}

let autoTween = null
const autoOpen = (delay = 0) => {
  if (opened || props.reducedMotion) {
    if (props.reducedMotion) openBurst()
    return
  }
  autoTween?.kill?.()
  const holder = { v: rip }
  autoTween = gsap.to(holder, {
    v: 1,
    duration: 0.62,
    delay,
    ease: 'power2.inOut',
    onUpdate: () => applyRip(holder.v),
    onComplete: openBurst
  })
}

defineExpose({ setRip, autoOpen, openBurst, getMouth, get rip() { return rip } })

// ---------- 循环 / 尺寸 ----------
const resize = () => {
  const el = rootEl.value
  if (!el || !renderer || !camera) return
  const w = el.clientWidth
  const h = el.clientHeight
  if (!w || !h) return
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

const loop = () => {
  if (destroyed) return
  raf = requestAnimationFrame(loop)
  if (!ready || !renderer) return
  clock += 0.016

  if (!props.reducedMotion) {
    // 转动始终跟手：撕开之后、喷洒期间也能继续把玩卡包
    pointer.x += (pointer.tx - pointer.x) * 0.07
    pointer.y += (pointer.ty - pointer.y) * 0.07
    packGroup.rotation.y = -0.18 + pointer.x * 0.5 + Math.sin(clock * 0.5) * 0.05
    packGroup.rotation.x = 0.04 + pointer.y * 0.34 + Math.sin(clock * 0.72) * 0.03
    // 上下浮动只在待撕时做，开包后位置交给时间线，免得打架
    if (!opened) packGroup.position.y = Math.sin(clock * 0.62) * 0.03
  }
  renderer.render(scene, camera)
}

const onPointerMove = (e) => {
  const el = rootEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  if (!r.width || !r.height) return
  pointer.tx = ((e.clientX - r.left) / r.width) * 2 - 1
  pointer.ty = -(((e.clientY - r.top) / r.height) * 2 - 1)
}

let ro = null
onMounted(() => {
  if (!import.meta.client) return
  build()
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  if (typeof ResizeObserver !== 'undefined' && rootEl.value) {
    ro = new ResizeObserver(() => resize())
    ro.observe(rootEl.value)
  }
})

watch(() => props.active, (on) => { if (on) resize() })
// 表情图是异步拿到的，晚到就重画袋口那张
watch(() => props.nextSrc, () => { paintStackSticker() })

onBeforeUnmount(() => {
  destroyed = true
  if (raf) cancelAnimationFrame(raf)
  autoTween?.kill?.()
  window.removeEventListener('pointermove', onPointerMove)
  ro?.disconnect?.()
  ro = null
  for (const d of disposables) { try { d.dispose?.() } catch {} }
  try { envRT?.dispose?.() } catch {}
  try { renderer?.dispose?.() } catch {}
  renderer = null
  scene = null
})
</script>

<style scoped>
.p3-root {
  position: absolute;
  inset: 0;
  touch-action: none;
}
.p3-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
