<template>
  <Teleport to="body">
    <Transition name="afd" @after-leave="onAfterLeave">
      <div
        v-if="open"
        class="afd-overlay"
        @mousedown.self="requestClose"
      >
        <section
          ref="panelEl"
          class="afd-panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descId"
          tabindex="-1"
        >
          <header class="afd-head">
            <p class="afd-rule afd-mono" aria-hidden="true">
              <b>PRO</b>
              <span>— 高级版</span>
              <i class="afd-rule__line"><em></em></i>
            </p>
            <div class="afd-titlerow">
              <h2 :id="titleId" class="afd-title">不止能读，<em>还能写</em></h2>
              <span class="afd-badge afd-mono">暂时不可用</span>
            </div>
            <p :id="descId" class="afd-desc">{{ FEATURE_UNAVAILABLE_MESSAGE }}</p>
            <button
              ref="closeBtn"
              type="button"
              class="afd-close afd-mono"
              aria-label="关闭"
              title="关闭 (Esc)"
              @click="requestClose"
            >×</button>
          </header>

          <!-- 引擎把清单 + 舞台挂进 host；面板外观全由 pro-demos.css 的 .pd-root 令牌负责 -->
          <div class="afd-body">
            <div ref="host" class="afd-host"></div>
          </div>

          <footer class="afd-foot">
            <p class="afd-foot__meta afd-mono">{{ PRO_TOTAL }} 项 · 写入 / 动作</p>
            <button type="button" class="afd-get afd-mono" @click="openDeveloperContact">
              获取 — QQ {{ DEVELOPER_QQ }} · 备注「高级版」 <i aria-hidden="true">↗</i>
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { gsap } from 'gsap'
import { PRO_TOTAL } from '@website/js/pro-demos/catalog.js'
import { DEVELOPER_QQ, FEATURE_UNAVAILABLE_MESSAGE, openDeveloperContact } from '~/lib/developer-support'

const props = defineProps({
  open: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

const panelEl = ref(null)
const closeBtn = ref(null)
const host = ref(null)
const id = useId()
const titleId = `afd-title-${id}`
const descId = `afd-desc-${id}`

// 引擎实例只在打开期间存在；mountSeq 让「打开→关闭→再打开」期间的异步回调作废
let panel = null
let mountSeq = 0
let previouslyFocused = null
let pageLocked = false
let savedOverflow = ''

const destroyPanel = () => {
  if (!panel) return
  try { panel.destroy() } catch {}
  panel = null
}

const prefersReducedMotion = () => (
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false
)

// 引擎（8 组场景）和它的样式体积都不小，首次打开时才一起拉进来；
// CSS 也走动态 import，才不会随 SidebarRail 混进每个页面的 entry.css
const loadEngine = () => Promise.all([
  import('@website/js/pro-demos/index.js'),
  import('@website/css/pro-demos.css')
]).then(([mod]) => mod)

const mountPanel = async () => {
  const seq = ++mountSeq
  destroyPanel()
  await nextTick()
  if (seq !== mountSeq || !props.open || !host.value) return
  const { createProPanel } = await loadEngine()
  if (seq !== mountSeq || !props.open || !host.value) return
  host.value.replaceChildren()
  panel = createProPanel(host.value, { gsap, reduced: prefersReducedMotion() })
}

// 打开期间锁住页面滚动，并让 #__nuxt 对键盘 / 读屏器不可达（弹窗 Teleport 在 body 下，不受影响）
const lockPage = () => {
  if (pageLocked || typeof document === 'undefined') return
  pageLocked = true
  savedOverflow = document.documentElement.style.overflow
  document.documentElement.style.overflow = 'hidden'
  document.getElementById('__nuxt')?.setAttribute('inert', '')
}

const unlockPage = () => {
  if (!pageLocked) return
  pageLocked = false
  document.documentElement.style.overflow = savedOverflow
  document.getElementById('__nuxt')?.removeAttribute('inert')
}

const requestClose = () => emit('close')

// 淡出期间保留画面，淡出结束再拆引擎；若期间又打开了，mountPanel 会自己先拆旧的
const onAfterLeave = () => {
  if (!props.open) destroyPanel()
}

const onKeydown = (event) => {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose()
    return
  }
  if (event.key !== 'Tab') return
  const root = panelEl.value
  if (!root) return
  const focusable = Array.from(root.querySelectorAll('button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'))
  if (!focusable.length) {
    event.preventDefault()
    root.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  const outside = !root.contains(active)
  if (event.shiftKey && (active === first || outside)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || outside)) {
    event.preventDefault()
    first.focus()
  }
}

const applyOpen = async (isOpen) => {
  if (isOpen) {
    previouslyFocused = document.activeElement
    lockPage()
    await nextTick()
    closeBtn.value?.focus?.()
    await mountPanel()
    return
  }
  mountSeq++
  if (panel) panel.pause()
  // 先解除 inert 再还焦点，否则侧栏按钮还是不可聚焦的
  unlockPage()
  const target = previouslyFocused
  previouslyFocused = null
  await nextTick()
  target?.focus?.()
}

watch(() => props.open, applyOpen, { flush: 'post' })

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  // 开发态热替换会整个重建组件而 watch 不会再触发：挂载时已是打开态就直接接上
  if (props.open) applyOpen(true)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  mountSeq++
  destroyPanel()
  unlockPage()
})
</script>

<style scoped>
/* 无论宿主浅色/深色，这块都是固定的暗色「解密实验室」；令牌与 pro-demos.css 的 .pd-root 同一套 */
.afd-overlay {
  position: fixed;
  inset: 0;
  z-index: 12000;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.62);
  -webkit-backdrop-filter: blur(3px);
  backdrop-filter: blur(3px);
}

.afd-panel {
  --afd-bg: #070b09;
  --afd-ink: #e9f1eb;
  --afd-dim: #9aa8a0;
  --afd-faint: #5c6a63;
  --afd-line: rgba(150, 180, 160, 0.14);
  --afd-line-strong: rgba(150, 180, 160, 0.28);
  --afd-amber: #ffc24b;
  --afd-neon: #3df28d;
  --afd-mono: "JetBrains Mono", "SF Mono", ui-monospace, Menlo, Consolas, monospace;
  --afd-sans: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", -apple-system, "Segoe UI", sans-serif;

  /* 尺寸先定高（min(760px, 视口 − 32)），宽度再按内容收口：
     舞台是 16:10 场景屏，通常被高度封顶，面板宽 = 舞台宽 + 清单栏 + 栏距 + 内边距，
     这样清单栏永远只有一栏文字的宽度，不会在清单与舞台之间留出一片黑；
     宽度不够时（窄窗口）舞台退回按宽度定高，清单栏宽度不变。
     --afd-chrome = 刊头 120 + 页脚 50 + 正文内边距 40 + 上下边框 2；--afd-hud = 舞台 HUD 两行 + 进度线 + 三处 10px 间距 */
  --afd-list-w: 240px;
  --afd-gap: 28px;
  --afd-hud: 80px;
  --afd-chrome: 212px;
  --afd-pad-x: 48px;
  --afd-h: min(760px, calc(100dvh - 32px));
  --afd-stage-max: calc((var(--afd-h) - var(--afd-chrome) - var(--afd-hud)) * 1.6);
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: min(1120px, calc(100vw - 32px), calc(var(--afd-stage-max) + var(--afd-list-w) + var(--afd-gap) + var(--afd-pad-x) + 2px));
  height: var(--afd-h);
  overflow: hidden;
  border: 1px solid var(--afd-line-strong);
  border-radius: 8px;
  background: var(--afd-bg);
  color: var(--afd-ink);
  font-family: var(--afd-sans);
  font-size: 13px;
  line-height: 1.5;
  box-shadow: 0 40px 120px rgba(0, 0, 0, 0.6), inset 0 0 0 1px rgba(61, 242, 141, 0.04);
  outline: none;
}

.afd-mono { font-family: var(--afd-mono); }

/* ── 刊头（行高全部写死，面板宽度公式里的 --afd-chrome 才站得住）── */
.afd-head {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 60px 16px 24px;
  border-bottom: 1px solid var(--afd-line);
}

.afd-rule {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  font-size: 10px;
  line-height: 1.5;
  letter-spacing: 0.24em;
  color: var(--afd-amber);
}

.afd-rule b {
  flex: none;
  padding: 3px 6px 2px 9px;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: #140d01;
  background: var(--afd-amber);
  box-shadow: 0 0 22px rgba(255, 194, 75, 0.4);
}

.afd-rule span { flex: none; }

.afd-rule__line {
  position: relative;
  flex: 1;
  max-width: 360px;
  height: 1px;
  background: rgba(255, 194, 75, 0.28);
}

.afd-rule__line em {
  position: absolute;
  top: -1px;
  left: 0;
  width: 30px;
  height: 3px;
  border-radius: 2px;
  background: linear-gradient(90deg, transparent, var(--afd-amber));
  box-shadow: 0 0 10px rgba(255, 194, 75, 0.8);
  animation: afd-spark 3.2s ease-in-out infinite;
}

.afd-titlerow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
}

.afd-title {
  margin: 0;
  font-size: 24px;
  font-weight: 900;
  line-height: 1.2;
  letter-spacing: 0.01em;
  color: var(--afd-ink);
  white-space: nowrap;
}

.afd-title em {
  font-style: normal;
  color: var(--afd-amber);
  text-shadow: 0 0 32px rgba(255, 194, 75, 0.5);
}

.afd-badge {
  padding: 3px 8px 2px 10px;
  border: 1px solid rgba(255, 194, 75, 0.5);
  background: rgba(255, 194, 75, 0.08);
  font-size: 10px;
  line-height: 1.5;
  letter-spacing: 0.2em;
  color: var(--afd-amber);
  white-space: nowrap;
}

.afd-desc {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--afd-dim);
}

.afd-close {
  position: absolute;
  top: 12px;
  right: 14px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  font-size: 20px;
  line-height: 1;
  color: var(--afd-faint);
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background-color 0.2s;
}

.afd-close:hover {
  color: var(--afd-ink);
  border-color: var(--afd-line-strong);
  background: rgba(255, 255, 255, 0.04);
}

.afd-close:focus-visible {
  outline: 1px solid rgba(255, 194, 75, 0.7);
  outline-offset: 1px;
}

/* ── 正文：引擎面板撑满 ── */
.afd-body {
  min-height: 0;
  padding: 20px 24px;
  overflow: hidden;
  /* 作为尺寸容器，下面舞台栏的 cqh 才有得量 */
  container-type: size;
}

.afd-host {
  height: 100%;
  min-height: 0;
}

.afd-host :deep(.pd-root) {
  --pd-list-cols: 1;
  height: 100%;
}

/* 上下堆叠时（引擎 ≤720px 容器宽）面板按内容自然长高、由 .afd-body 滚动；
   若仍撑成 100%，auto 行会被压得比舞台矮，舞台就叠到清单上 */
.afd-host :deep(.pd-panel) { height: auto; }

/* 左右双栏时：舞台栏 = min(剩余宽度, 按可用高度封顶的 16:10 宽)，清单吃掉其余 ——
   面板宽已按内容收口，其余通常就是 --afd-list-w */
@container (min-width: 721px) {
  .afd-host :deep(.pd-panel) {
    height: 100%;
    grid-template-columns:
      minmax(200px, 1fr)
      min(calc(100% - var(--afd-list-w) - var(--afd-gap)), calc((100cqh - var(--afd-hud)) * 1.6));
    column-gap: var(--afd-gap);
  }
}

/* 单栏清单里分组标签紧跟组名与计数，别被推到栏最右 */
.afd-host :deep(.pd-group__head em) { margin-left: 6px; }

/* 底缘渐隐提示还能滚；多留一段底部内边距，滚到底时末项能完整露出 */
.afd-host :deep(.pd-list) {
  padding-bottom: 36px;
  -webkit-mask-image: linear-gradient(180deg, #000 calc(100% - 36px), transparent);
  mask-image: linear-gradient(180deg, #000 calc(100% - 36px), transparent);
}

/* ── 页脚 ── */
.afd-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 16px;
  padding: 12px 24px 14px;
  border-top: 1px solid var(--afd-line);
}

.afd-foot__meta {
  margin: 0;
  font-size: 10.5px;
  letter-spacing: 0.16em;
  color: var(--afd-faint);
}

.afd-get {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 5px;
  border: 0;
  border-bottom: 1px dashed rgba(255, 194, 75, 0.45);
  border-radius: 0;
  background: none;
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--afd-amber);
  opacity: 0.92;
  cursor: pointer;
  transition: opacity 0.3s, border-color 0.3s, text-shadow 0.3s;
}

.afd-get i {
  font-style: normal;
  transition: transform 0.3s;
}

.afd-get:hover {
  opacity: 1;
  border-color: var(--afd-amber);
  text-shadow: 0 0 18px rgba(255, 194, 75, 0.55);
}

.afd-get:hover i { transform: translate(3px, -3px); }

.afd-get:focus-visible {
  outline: 1px solid rgba(255, 194, 75, 0.7);
  outline-offset: 3px;
}

/* ── 出入场 ── */
.afd-enter-active,
.afd-leave-active { transition: opacity 180ms ease; }

.afd-enter-active .afd-panel,
.afd-leave-active .afd-panel {
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1), opacity 180ms ease;
}

.afd-enter-from,
.afd-leave-to { opacity: 0; }

.afd-enter-from .afd-panel,
.afd-leave-to .afd-panel {
  opacity: 0;
  transform: translateY(10px) scale(0.985);
}

@keyframes afd-spark {
  0% { left: 0; opacity: 0; }
  12% { opacity: 1; }
  86% { opacity: 1; }
  100% { left: calc(100% - 30px); opacity: 0; }
}

/* ── 窄窗 / 矮窗：面板贴边 12px 铺满高度，宽度仍按内容收口并居中；引擎在 ≤720px 容器宽时自己把清单堆到舞台下面 ── */
@media (max-width: 900px), (max-height: 640px) {
  .afd-overlay { padding: 0; }

  .afd-panel {
    /* 刊头 107 + 页脚 46 + 正文内边距 28 + 上下边框 2 */
    --afd-chrome: 183px;
    --afd-pad-x: 36px;
    --afd-h: calc(100dvh - 24px);
    position: absolute;
    inset: 12px;
    width: min(calc(100vw - 24px), calc(var(--afd-stage-max) + var(--afd-list-w) + var(--afd-gap) + var(--afd-pad-x) + 2px));
    height: auto;
    margin-inline: auto;
  }

  .afd-head { padding: 14px 52px 12px 18px; }
  .afd-title { font-size: 20px; white-space: normal; }
  .afd-body { padding: 14px 18px; overflow: auto; }
  .afd-foot { padding: 10px 18px 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .afd-rule__line em { animation: none; }

  .afd-enter-active,
  .afd-leave-active,
  .afd-enter-active .afd-panel,
  .afd-leave-active .afd-panel { transition: none; }
}
</style>
