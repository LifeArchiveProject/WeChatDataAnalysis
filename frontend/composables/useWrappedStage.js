import { computed, inject, provide, readonly, ref } from 'vue'

import {
  DEFAULT_FRAME_ID,
  FRAME_PRESETS,
  FRAME_STORAGE_KEY,
  designSize,
  findFrame,
  frameTier,
  normalizeFrameId
} from '~/lib/wrapped-stage'

// 年度总结舞台的共享状态。页面侧 createWrappedStage() 建一份并 provide，
// 卡片侧 useWrappedStage() 取用；脱离舞台单独渲染时拿到的是「16:9、scale 1」的惰性兜底，
// 不会因为 inject 落空而炸。
const STAGE_KEY = Symbol.for('wrapped.stage')

let fallbackStage = null

const makeFallback = () => {
  if (fallbackStage) return fallbackStage
  const design = ref({ w: 1600, h: 900 })
  fallbackStage = {
    frameId: readonly(ref(DEFAULT_FRAME_ID)),
    frame: readonly(ref(findFrame(DEFAULT_FRAME_ID))),
    frames: FRAME_PRESETS,
    design: readonly(design),
    scale: readonly(ref(1)),
    tier: readonly(ref('wide')),
    isFramed: readonly(ref(false)),
    portalEl: ref(null),
    stageEl: ref(null),
    portalTarget: computed(() => 'body'),
    setFrame: () => {},
    // 舞台缺席时坐标系就是屏幕坐标系，换算恒等，「视口」就是真视口
    toStageDelta: (px) => px,
    toStagePoint: (x, y) => ({ x, y }),
    viewportSize: () => ({
      w: typeof window === 'undefined' ? 1600 : window.innerWidth,
      h: typeof window === 'undefined' ? 900 : window.innerHeight
    }),
    pixelRatio: (cap = 3) => Math.min(cap, typeof window === 'undefined' ? 1 : (window.devicePixelRatio || 1))
  }
  return fallbackStage
}

/**
 * 建立舞台状态（只在 pages/wrapped/index.vue 调一次）。
 * hostSize 由 WrappedStage.vue 的 ResizeObserver 回写。
 */
export function createWrappedStage () {
  const frameId = ref(DEFAULT_FRAME_ID)
  const hostSize = ref({ w: 0, h: 0 })
  const scale = ref(1)
  const rect = ref({ left: 0, top: 0 })
  const portalEl = ref(null)
  const stageEl = ref(null)

  const frame = computed(() => findFrame(frameId.value) || findFrame(DEFAULT_FRAME_ID))
  const ratio = computed(() => Number(frame.value?.ratio) || 0)
  const isFramed = computed(() => ratio.value > 0)
  const design = computed(() => designSize(ratio.value, hostSize.value.w, hostSize.value.h))
  /* 版式档位。
     ⚠️ 跟随窗口（ratio<=0）时必须按**窗口实际比例**判档，不能用 frameTier 的默认 'wide'：
     否则手机上（393×852，比例 0.46）会套上 16:9 的桌面横屏版式——舞台明明铺满了屏幕，
     版式却是给宽屏排的，字小、栏窄，整屏没被利用起来。
     框定画幅时窗口无关，仍然按画幅比例判档（这正是当初把 Tailwind 断点换成 tier 的原因）。 */
  const tier = computed(() => {
    if (ratio.value > 0) return frameTier(ratio.value)
    const { w, h } = hostSize.value
    if (!(w > 0 && h > 0)) return frameTier(0)
    return frameTier(w / h)
  })

  const setFrame = (id) => {
    const next = normalizeFrameId(id)
    if (next === frameId.value) return
    frameId.value = next
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(FRAME_STORAGE_KEY, next)
    } catch {
      // 隐私模式/禁用存储时忽略，画幅仅本次会话有效
    }
  }

  // SSR 期间不碰 localStorage，避免 hydration class 不一致（见 dark-mode-architecture）
  const initFrame = (preferred) => {
    if (typeof window === 'undefined') return
    if (preferred && findFrame(String(preferred))) {
      frameId.value = normalizeFrameId(preferred)
      return
    }
    try {
      const saved = window.localStorage.getItem(FRAME_STORAGE_KEY)
      if (saved) frameId.value = normalizeFrameId(saved)
    } catch {
      // ignore
    }
  }

  // 屏幕 CSS px → 舞台设计 px。凡是把 clientX/clientY 的差值直接写进
  // 舞台内 transform / CSS 变量的地方都要过这一层，否则缩放后手感和位移全部串味。
  const toStageDelta = (px) => {
    const k = scale.value || 1
    return px / k
  }

  const toStagePoint = (clientX, clientY) => {
    const k = scale.value || 1
    const el = stageEl.value
    if (!el) return { x: clientX / k, y: clientY / k }
    const r = el.getBoundingClientRect()
    return { x: (clientX - r.left) / k, y: (clientY - r.top) / k }
  }

  // 舞台内的「视口」就是设计盒。跟随窗口模式下 design 已等于 host 实测尺寸，
  // 所以这一个出口对两种模式都成立。
  const viewportSize = () => ({ w: design.value.w, h: design.value.h })

  // canvas / WebGL 的有效像素比。画布的 CSS 尺寸是舞台单位，真正上屏的物理尺寸
  // 还要再乘一次舞台 scale —— 大屏上舞台放大时不补这一刀就是欠采样发糊。
  // 只在 scale>1 时补，缩小时保持过采样（无害，且导出时正好用得上）。
  const pixelRatio = (cap = 3) => {
    const dpr = typeof window === 'undefined' ? 1 : (window.devicePixelRatio || 1)
    return Math.min(cap, dpr * Math.max(1, scale.value || 1))
  }

  // 卡片里的全屏浮层从 body 改 teleport 到这里：.wr-stage 带 transform，
  // 天然是其 position:fixed 后代的包含块，于是 `fixed inset-0` 自动等于「铺满舞台」。
  const portalTarget = computed(() => portalEl.value || 'body')

  const stage = {
    frameId,
    frame,
    frames: FRAME_PRESETS,
    ratio,
    isFramed,
    design,
    tier,
    scale,
    rect,
    hostSize,
    portalEl,
    stageEl,
    portalTarget,
    setFrame,
    initFrame,
    toStageDelta,
    toStagePoint,
    viewportSize,
    pixelRatio
  }

  provide(STAGE_KEY, stage)
  return stage
}

export function useWrappedStage () {
  return inject(STAGE_KEY, makeFallback())
}
