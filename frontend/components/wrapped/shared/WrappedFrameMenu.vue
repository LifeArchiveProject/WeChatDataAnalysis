<template>
  <div ref="rootEl" class="wf-menu" :class="{ 'wf-menu--dark': dark }" @keydown.stop="onKeydown">
    <button
      ref="triggerEl"
      type="button"
      class="wf-trigger"
      :class="open ? 'is-open' : ''"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="dialog"
      aria-label="分享 · 选择画幅"
      title="分享 · 选择画幅"
      @click="toggle"
    >
      <svg class="wf-trigger__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="18" cy="5" r="2.6" />
        <circle cx="6" cy="12" r="2.6" />
        <circle cx="18" cy="19" r="2.6" />
        <path d="M8.4 10.8 15.6 6.7" />
        <path d="M8.4 13.2l7.2 4.1" />
      </svg>
      <span v-if="current && current.id !== 'fit'" class="wf-trigger__badge">{{ current.label }}</span>
    </button>

    <Transition name="wf-pop">
      <div v-if="open" class="wf-panel" role="dialog" aria-label="选择分享画幅">
        <div class="wf-panel__head">
          <div class="wf-panel__title">分享画幅</div>
          <div class="wf-panel__sub">整份年度总结按所选比例出画，元素随画幅重排</div>
        </div>

        <div class="wf-list">
          <button
            v-for="f in frames"
            :key="f.id"
            type="button"
            class="wf-item"
            :class="{ 'is-active': f.id === modelValue }"
            @click="pick(f.id)"
          >
            <span class="wf-thumb" aria-hidden="true">
              <span class="wf-thumb__box" :style="thumbStyle(f)"></span>
            </span>
            <span class="wf-item__text">
              <span class="wf-item__row">
                <span class="wf-item__label">{{ f.label }}</span>
                <span class="wf-item__caption">{{ f.caption }}</span>
              </span>
              <span class="wf-item__platforms">{{ f.platforms }}</span>
            </span>
            <span class="wf-item__px">{{ f.exportSize ? `${f.exportSize[0]}×${f.exportSize[1]}` : '自适应' }}</span>
          </button>
        </div>

        <div class="wf-panel__foot">
          <button
            type="button"
            class="wf-export"
            :disabled="exporting"
            @click="$emit('export')"
          >
            <svg v-if="!exporting" class="wf-export__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 3v12" />
              <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
              <path d="M4 17v2.5A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5V17" />
            </svg>
            <svg v-else class="wf-export__icon wf-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.4" stroke-opacity="0.25" />
              <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
            </svg>
            <span>{{ exporting ? '正在出图…' : '导出当前页为图片' }}</span>
          </button>

          <!-- 次级动作：整份打包。产物写在按钮下面一行，点之前就知道会拿到什么 -->
          <button
            type="button"
            class="wf-export wf-export--zip"
            :disabled="exporting"
            @click="$emit('export-all')"
          >
            <svg class="wf-export__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z" />
              <path d="M12 3v18" />
              <path d="M10.4 6.2h3.2M10.4 9h3.2M10.4 11.8h3.2" />
            </svg>
            <span>导出全部页面（ZIP）</span>
          </button>
          <p class="wf-zip-note">{{ zipNote }}</p>

          <p v-if="statusText" class="wf-status" :class="statusTone === 'error' ? 'is-error' : ''">{{ statusText }}</p>
          <p v-else class="wf-hint">{{ hintText }}</p>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, required: true },
  frames: { type: Array, required: true },
  dark: { type: Boolean, default: false },
  exporting: { type: Boolean, default: false },
  statusText: { type: String, default: '' },
  statusTone: { type: String, default: 'info' },
  // 桌面端才有原生截图通道，浏览器端给不同的说明
  canExport: { type: Boolean, default: false },
  // 整份打包会出几张图（封面 + 各卡片）。由页面传真实页数，文案不写死。
  pageCount: { type: Number, default: 9 },
})

const emit = defineEmits(['update:modelValue', 'export', 'export-all'])

const open = ref(false)
const rootEl = ref(null)
const triggerEl = ref(null)

const frames = computed(() => props.frames)
const current = computed(() => props.frames.find((f) => f.id === props.modelValue) || null)

const hintText = computed(() => (
  props.canExport
    ? '导出的是画面本身，顶部控件不会入图'
    : '桌面应用内可直接导出；浏览器里请用系统截图'
))

// 「点了会得到什么」：一个 zip 文件，解压出来是 N 张 PNG，尺寸随当前画幅
const zipNote = computed(() => {
  const n = Math.max(1, Number(props.pageCount) || 0)
  const size = current.value && Array.isArray(current.value.exportSize)
    ? `每张 ${current.value.exportSize[0]}×${current.value.exportSize[1]}`
    : '尺寸跟随当前窗口比例'
  return `一个 zip 文件，解压后是 ${n} 张 PNG（封面 + 各页），${size}；换画幅会换尺寸`
})

// 缩略图按真实比例画，直接把「这张图长什么样」摆在选项旁边
const thumbStyle = (f) => {
  const r = Number(f.ratio) || 0
  const BOX = 26
  if (r <= 0) return { width: `${BOX}px`, height: `${Math.round(BOX * 0.62)}px`, borderStyle: 'dashed' }
  const w = r >= 1 ? BOX : Math.round(BOX * r)
  const h = r >= 1 ? Math.round(BOX / r) : BOX
  return { width: `${w}px`, height: `${h}px` }
}

const pick = (id) => {
  emit('update:modelValue', id)
}

const toggle = () => { open.value = !open.value }
const close = () => { open.value = false }

const onKeydown = (e) => {
  if (e.key === 'Escape') {
    close()
    triggerEl.value?.focus?.()
  }
}

const onDocPointerDown = (e) => {
  if (!open.value) return
  const el = rootEl.value
  if (el && e.target instanceof Node && el.contains(e.target)) return
  close()
}

// 面板开着时不让方向键翻页（deck 的 keydown 挂在 window 上）
const onWindowKeydown = (e) => {
  if (!open.value) return
  if (e.key === 'Escape') { close(); return }
  const el = rootEl.value
  if (el && e.target instanceof Node && el.contains(e.target)) e.stopPropagation()
}

watch(() => props.modelValue, () => {
  // 选完不自动关闭：换画幅是要反复比对的动作
})

onMounted(() => {
  document.addEventListener('pointerdown', onDocPointerDown, true)
  window.addEventListener('keydown', onWindowKeydown, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  window.removeEventListener('keydown', onWindowKeydown, true)
})

defineExpose({ close })
</script>

<style scoped>
.wf-menu {
  position: relative;
  display: inline-flex;
}

/* ── 触发按钮：沿用 chrome 那一排 36px 圆钮的尺寸与配色 ── */
.wf-trigger {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 9999px;
  background: transparent;
  color: #07C160;
  transition: background-color 160ms ease, color 160ms ease;
}

.wf-trigger:hover { background: rgba(7, 193, 96, 0.1); }
.wf-trigger:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(7, 193, 96, 0.3);
}
.wf-trigger.is-open { background: rgba(7, 193, 96, 0.14); }

.wf-menu--dark .wf-trigger { color: #4ADE80; }
.wf-menu--dark .wf-trigger:hover { background: rgba(255, 255, 255, 0.1); }
.wf-menu--dark .wf-trigger.is-open { background: rgba(255, 255, 255, 0.14); }

.wf-trigger__icon { width: 16px; height: 16px; }

/* 当前画幅贴在按钮右下角，不用展开面板就知道现在是哪一格 */
.wf-trigger__badge {
  position: absolute;
  right: -3px;
  bottom: -2px;
  padding: 0 3px;
  border-radius: 5px;
  font-size: 8px;
  line-height: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
  color: #FFFFFF;
  background: #07C160;
  box-shadow: 0 1px 3px rgba(6, 46, 28, 0.35);
}
.wf-menu--dark .wf-trigger__badge {
  color: #05130C;
  background: #4ADE80;
}

/* ── 面板 ── */
.wf-panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 60;
  width: 328px;
  /* host 是 overflow:hidden 的，矮窗口下面板会被裁掉一截 —— 高度封顶 + 列表内滚 */
  max-height: calc(100dvh - 108px);
  display: flex;
  flex-direction: column;
  padding: 14px 14px 12px;
  border-radius: 18px;
  border: 1px solid rgba(7, 193, 96, 0.18);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.9) inset,
    0 24px 60px -18px rgba(6, 46, 28, 0.32),
    0 4px 14px -6px rgba(6, 46, 28, 0.2);
  text-align: left;
}

.wf-menu--dark .wf-panel {
  border-color: rgba(74, 222, 128, 0.22);
  background: rgba(12, 22, 17, 0.9);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.07) inset,
    0 24px 60px -18px rgba(0, 0, 0, 0.66);
}

.wf-panel__head { padding: 0 2px 10px; }

.wf-panel__title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: rgba(0, 0, 0, 0.86);
}

.wf-panel__sub {
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.6;
  color: rgba(0, 0, 0, 0.42);
}

.wf-menu--dark .wf-panel__title { color: rgba(243, 248, 244, 0.94); }
.wf-menu--dark .wf-panel__sub { color: rgba(255, 255, 255, 0.42); }

.wf-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.wf-panel__head,
.wf-panel__foot {
  flex: 0 0 auto;
}

.wf-item {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 7px 8px;
  border-radius: 11px;
  text-align: left;
  transition: background-color 140ms ease;
}

.wf-item:hover { background: rgba(7, 193, 96, 0.07); }
.wf-item:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(7, 193, 96, 0.32);
}
.wf-item.is-active { background: rgba(7, 193, 96, 0.12); }

.wf-menu--dark .wf-item:hover { background: rgba(255, 255, 255, 0.06); }
.wf-menu--dark .wf-item.is-active { background: rgba(74, 222, 128, 0.14); }

/* 比例缩略图：按真实宽高比画的空框，选中时填成实心 */
.wf-thumb {
  flex: 0 0 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wf-thumb__box {
  display: block;
  border: 1.5px solid rgba(0, 0, 0, 0.26);
  border-radius: 3px;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.wf-item.is-active .wf-thumb__box {
  border-color: #07C160;
  background: rgba(7, 193, 96, 0.24);
}

.wf-menu--dark .wf-thumb__box { border-color: rgba(255, 255, 255, 0.34); }
.wf-menu--dark .wf-item.is-active .wf-thumb__box {
  border-color: #4ADE80;
  background: rgba(74, 222, 128, 0.26);
}

.wf-item__text {
  flex: 1 1 auto;
  min-width: 0;
}

.wf-item__row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.wf-item__label {
  font-size: 12.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
  color: rgba(0, 0, 0, 0.84);
}

.wf-item__caption {
  font-size: 10.5px;
  color: rgba(0, 0, 0, 0.4);
}

.wf-item__platforms {
  display: block;
  margin-top: 1px;
  font-size: 10.5px;
  line-height: 1.45;
  color: rgba(0, 0, 0, 0.38);
  /* 平台名是选画幅的唯一依据，任何画幅下都不许省略 */
  white-space: normal;
  overflow-wrap: anywhere;
}

.wf-item__px {
  flex: 0 0 auto;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: rgba(0, 0, 0, 0.3);
}

.wf-menu--dark .wf-item__label { color: rgba(243, 248, 244, 0.92); }
.wf-menu--dark .wf-item__caption,
.wf-menu--dark .wf-item__platforms { color: rgba(255, 255, 255, 0.42); }
.wf-menu--dark .wf-item__px { color: rgba(255, 255, 255, 0.32); }

.wf-panel__foot {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.07);
}

.wf-menu--dark .wf-panel__foot { border-top-color: rgba(255, 255, 255, 0.09); }

.wf-export {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  height: 34px;
  border-radius: 10px;
  background: #07C160;
  color: #FFFFFF;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  transition: background-color 140ms ease, opacity 140ms ease;
}

.wf-export:hover:not(:disabled) { background: #06AD56; }
.wf-export:disabled { opacity: 0.62; cursor: not-allowed; }
.wf-export:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(7, 193, 96, 0.34);
}

.wf-menu--dark .wf-export { background: #3EE58A; color: #05130C; }
.wf-menu--dark .wf-export:hover:not(:disabled) { background: #34D67D; }

/* 次级动作：绿底薄一层，不用白底（白底在这块玻璃面板上会碎成两块） */
.wf-export--zip {
  margin-top: 7px;
  height: 32px;
  background: rgba(7, 193, 96, 0.11);
  color: #06A24F;
  font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(7, 193, 96, 0.26);
}

.wf-export--zip:hover:not(:disabled) { background: rgba(7, 193, 96, 0.18); }

.wf-menu--dark .wf-export--zip {
  background: rgba(74, 222, 128, 0.14);
  color: #7FE9AC;
  box-shadow: inset 0 0 0 1px rgba(74, 222, 128, 0.28);
}
.wf-menu--dark .wf-export--zip:hover:not(:disabled) { background: rgba(74, 222, 128, 0.22); }

.wf-zip-note {
  margin-top: 5px;
  font-size: 10px;
  line-height: 1.5;
  color: rgba(0, 0, 0, 0.36);
}

.wf-menu--dark .wf-zip-note { color: rgba(255, 255, 255, 0.36); }

.wf-export__icon { width: 15px; height: 15px; }

.wf-spin { animation: wf-spin 900ms linear infinite; }
@keyframes wf-spin { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: reduce) {
  .wf-spin { animation-duration: 2400ms; }
}

.wf-hint,
.wf-status {
  margin-top: 7px;
  font-size: 10.5px;
  line-height: 1.5;
  color: rgba(0, 0, 0, 0.36);
}

.wf-status { color: rgba(7, 193, 96, 0.92); }
.wf-status.is-error { color: #E0523F; }

.wf-menu--dark .wf-hint { color: rgba(255, 255, 255, 0.36); }
.wf-menu--dark .wf-status { color: #6EE7A0; }
.wf-menu--dark .wf-status.is-error { color: #FF8F7D; }

.wf-pop-enter-active,
.wf-pop-leave-active {
  transition: opacity 160ms ease, transform 160ms cubic-bezier(0.22, 1, 0.36, 1);
}

.wf-pop-enter-from,
.wf-pop-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}
</style>
