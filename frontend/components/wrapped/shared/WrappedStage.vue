<template>
  <div
    ref="hostEl"
    class="wr-stage-host"
    :class="hostClass"
    :style="hostStyle"
    :data-frame="stage.frameId.value"
  >
    <div
      ref="stageEl"
      class="wr-stage"
      :class="stageClass"
      :style="stageStyle"
      :data-frame-tier="stage.tier.value"
    >
      <slot />
      <!-- 舞台内的浮层落点：卡片里的全屏遮罩/详情层/tooltip 从 body 改 teleport 到这里，
           `.wr-stage` 带 transform，天然是其 position:fixed 后代的包含块，
           于是 `fixed inset-0` 自动等于「铺满舞台」并随舞台缩放，一行 CSS 都不用改。 -->
      <div ref="portalEl" class="wr-stage-portal"></div>
    </div>

    <!-- 播放器层：返回/刷新/隐私/画幅/年份。必须是舞台的兄弟而不是后代——
         进舞台就会被 scale 缩到不可点，也会被一起拍进分享图。 -->
    <slot name="chrome" :gutter="gutter" />
  </div>
</template>

<script setup>
/**
 * 年度总结的画幅舞台。
 *
 * 结构：
 *   .wr-stage-host   占满内容区，画信箱边，overflow:hidden，**不带 transform**
 *     └ .wr-stage    设计像素常量盒；translate + scale 贴合 host；对外提供 --svw/--svh/--su
 *         ├ deck     今天的 .wrapped-deck-root（height:100%）
 *         └ portal   Teleport 落点
 *     └ chrome slot  浮层控件，不缩放、不入图
 *
 * 一条铁律：**舞台内 = 画面（会被截图、随画幅缩放）；舞台外 = 播放器（不缩放、不入图）。**
 *
 * ⚠️ 样式禁忌：`.wr-stage` 上不得出现 filter / opacity<1 / mask / contain:paint /
 * will-change:filter|opacity —— 任何一个都会新建 backdrop root，直接废掉 Card07 全篇的
 * backdrop-filter 磨砂玻璃。will-change:transform 也只在切画幅动画期间临时挂。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { fitStage } from '~/lib/wrapped-stage'
import { useWrappedStage } from '~/composables/useWrappedStage'

const props = defineProps({
  // 信箱边底色（影院卡在场时跟着转暗）
  shellBg: { type: String, default: '#E9F6EF' },
  // 附加到 .wr-stage 的类。隐私模式必须挂在这里而不是 deck 根上——
  // portal 是 stage 的子节点、deck 根的兄弟，挂 deck 根上的类继承不过去。
  stageClass: { type: [String, Array, Object], default: '' }
})

const stage = useWrappedStage()

const hostEl = ref(null)
const stageEl = ref(null)
const portalEl = ref(null)

let ro = null
let raf = 0

/* 顶栏（返回/刷新 · 隐私/分享/年份）在舞台之外、且**不跟随缩放**。
   框定画幅时它落在两侧留白里，压不到画面；跟随窗口时舞台铺满 host，它就压在画面头上。
   竖屏窗口下画面还要整体缩小（设计画布 ~814 宽映射到 393），卡片自己的上留白缩完只剩
   二十来个物理像素，标题会顶到图标底下。所以竖屏跟随窗口时，把顶栏那一条从可用画面里扣掉。 */
const CHROME_INSET = 64

const chromeInset = () => {
  if (stage.isFramed.value) return 0
  const el = hostEl.value
  if (!el) return 0
  const w = el.clientWidth
  const h = el.clientHeight
  if (!(w > 0 && h > 0) || w / h >= 1.15) return 0
  return CHROME_INSET
}

const measure = () => {
  raf = 0
  const el = hostEl.value
  if (!el) return
  // clientWidth/Height 是布局值，不受祖先 transform 影响；
  // getBoundingClientRect() 会被 Electron 页面缩放/父级 transform 污染，这里绝不能用。
  const w = el.clientWidth
  const h = Math.max(1, el.clientHeight - chromeInset())
  if (!w || !h) return
  const cur = stage.hostSize.value
  if (Math.abs(cur.w - w) > 0.5 || Math.abs(cur.h - h) > 0.5) {
    stage.hostSize.value = { w, h }
  }
}

const schedule = () => {
  if (raf || typeof requestAnimationFrame === 'undefined') return
  raf = requestAnimationFrame(measure)
}

const dpr = ref(1)

const fit = computed(() => {
  const d = stage.design.value
  const host = stage.hostSize.value
  if (!stage.isFramed.value) {
    /* 跟随窗口不再直接短路成 scale 1：竖屏窗口（手机）的设计画布已由 designSize
       改成「同比例的恒定面积画布」，需要真的算缩放。宽屏窗口下 design === host、
       inset 为 0，fitStage 算出来正好是 1，桌面浏览与改动前逐像素一致。 */
    const f = fitStage(host.w, host.h, d.w, d.h, dpr.value)
    // hostSize 已经扣掉了顶栏那一条，画面整体下移同样的量，正好落在顶栏下面
    return { ...f, top: f.top + chromeInset() }
  }
  return fitStage(host.w, host.h, d.w, d.h, dpr.value)
})

// 回写给共享状态，供拖拽换算、导出、卡片内坐标反算使用
watch(fit, (v) => {
  stage.scale.value = v.scale
  stage.rect.value = { left: v.left, top: v.top }
}, { immediate: true })

const gutter = computed(() => {
  const host = stage.hostSize.value
  const d = stage.design.value
  const f = fit.value
  return {
    x: Math.max(0, Math.round((host.w - d.w * f.scale) / 2)),
    y: Math.max(0, Math.round((host.h - d.h * f.scale) / 2))
  }
})

const stageStyle = computed(() => {
  const { w, h } = stage.design.value
  const { scale, left, top } = fit.value
  return {
    width: `${w}px`,
    height: `${h}px`,
    transform: `translate3d(${left}px, ${top}px, 0) scale(${scale})`,
    '--stage-w': `${w}px`,
    '--stage-h': `${h}px`,
    '--stage-scale': String(scale),
    // 舞台版的 vw/vh：卡片里所有 Nvh / Nvw 换成 calc(var(--svh) * N) / calc(var(--svw) * N)。
    // 不能用 cqh/cqw 做机械替换——容器单位绑定「最近的」尺寸容器，而 Card07 /
    // EmojiHoloCards / MonthlyCompanionPosters 已各自声明 container-type，会静默改绑。
    '--svw': `${w / 100}px`,
    '--svh': `${h / 100}px`,
    // 双轴基准标量：16:9 下恒等于 --svh（横屏逐像素零回归），竖幅下改由短边决定，
    // 避免「舞台变高 → 字变大 + 栏变窄」的双重挤压。
    '--su': `min(${h / 100}px, ${(w / 100) * 0.5625}px)`,
    // 排印缩放 —— ⚠️ 这是**过渡态**，不是终点。
    // 实测两头都碰过壁：1.43× 手机上正文只有 6.1px 看不清；2.42× 旧版式装不下，
    // 标题折行、FitScale 被压回 0.583，一样白搭。结论已定：旧版式 + 缩放系数永远调不平，
    // 框定画幅要走**原生重设计**（每页按画幅重新排版，字号在版式里生根，而不是全局乘一个系数）。
    // 在重设计落地前，过渡态取 (1600/W)^0.9、封顶 1.7：9:16 1.68 / 3:4 1.47 / 1:1 1.30。
    '--wf-text': String(Math.min(1.7, Math.max(1, Math.round(Math.pow(1600 / Math.max(1, w), 0.9) * 1000) / 1000))),
    // 页头标题/大标衬字用更缓的曲线（大字自带可读性，跟正文一个倍率会顶破版心折行）
    '--wf-title': String(Math.min(1.35, Math.max(1, Math.round((1 + (Math.pow(1600 / Math.max(1, w), 0.9) - 1) * 0.5) * 1000) / 1000)))
  }
})

const hostClass = computed(() => (stage.isFramed.value ? 'wr-stage-host--framed' : ''))

// 过渡只在「用户主动换画幅」时开一小会儿。常开会有两个副作用：
// 首帧从 identity 缓动到目标（每次进页面都莫名飘一下），以及窗口 resize 时舞台慢半拍。
const animating = ref(false)
let animTimer = null

watch(() => stage.frameId.value, () => {
  animating.value = true
  if (animTimer) clearTimeout(animTimer)
  animTimer = setTimeout(() => { animating.value = false }, 320)
})

const stageClass = computed(() => {
  const cls = []
  if (stage.isFramed.value) cls.push('wr-stage--framed')
  // 贴边时不给圆角，否则圆角会切在画面外沿上
  if (gutter.value.x > 8 || gutter.value.y > 8) cls.push('wr-stage--inset')
  if (animating.value) cls.push('wr-stage--animating')
  if (props.stageClass) cls.push(props.stageClass)
  return cls
})

const hostStyle = computed(() => ({
  backgroundColor: props.shellBg,
  transition: 'background-color 500ms ease'
}))

onMounted(() => {
  dpr.value = Math.max(1, Number(window.devicePixelRatio) || 1)
  stage.stageEl.value = stageEl.value
  stage.portalEl.value = portalEl.value
  measure()
  if (typeof ResizeObserver !== 'undefined' && hostEl.value) {
    // 只观察 host（尺寸不依赖舞台），绝不观察被缩放的节点，否则 RO 必然自激
    ro = new ResizeObserver(schedule)
    ro.observe(hostEl.value)
  }
  window.addEventListener('resize', schedule)
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
  window.removeEventListener('resize', schedule)
  if (animTimer) clearTimeout(animTimer)
  if (raf && typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(raf)
  stage.stageEl.value = null
  stage.portalEl.value = null
})

defineExpose({ hostEl, stageEl })
</script>

<style scoped>
.wr-stage-host {
  position: relative;
  width: 100%;
  height: 100dvh;
  min-height: 100dvh;
  overflow: hidden;
  /* 舞台已是缩放画面，页面级捏合缩放叠上去会双重缩放 */
  touch-action: none;
}

.wr-stage {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
  overflow: hidden;
  user-select: none;
}

/* 只在换画幅那一下过渡，且只过渡 transform。**绝不要**把 width/height 加进来：
   舞台盒里装着整个 deck，逐帧改布局尺寸 = 逐帧全量重排，还会把每张卡的
   ResizeObserver 一起抖起来（canvas/three 会跟着反复重开缓冲区）。 */
.wr-stage--animating {
  transition: transform 260ms cubic-bezier(0.22, 1, 0.36, 1);
}

@media (prefers-reduced-motion: reduce) {
  .wr-stage--animating {
    transition-duration: 1ms;
  }
}

/* 固定画幅时给画面一圈实体边界感：不是装饰，是「这就是你要发出去的那张图」的边界告知 */
.wr-stage--inset {
  border-radius: 14px;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.5) inset,
    0 18px 48px -12px rgba(6, 46, 28, 0.28),
    0 2px 10px -2px rgba(6, 46, 28, 0.16);
}

.wr-stage-portal {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
}
</style>

<style>
/* 桌面端隐藏标题栏，100dvh 会把标题栏高度叠进来产生外层滚动条，
   这里沿用 .wrapped-deck-root 原有的重解释规则（选择器随之改到 host）。 */
.wechat-desktop .wechat-desktop-content > .wr-stage-host {
  height: 100%;
  min-height: 100%;
}
</style>
