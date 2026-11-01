<template>
  <Teleport to="body">
    <Transition name="guide-dialog">
      <div
        v-if="open"
        class="guide-dialog-overlay"
        :class="{ 'guide-dialog-overlay--export': exportStyle }"
        @mousedown.self="requestClose"
      >
        <section
          ref="dialogPanel"
          class="guide-dialog-panel theme-scope"
          :class="{
            'guide-dialog-panel--wide': wide,
            'guide-dialog-panel--export': exportStyle,
            'app-export-modal': exportStyle
          }"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="description ? descriptionId : undefined"
          tabindex="-1"
        >
          <button
            v-if="showCloseIcon && !exportStyle"
            type="button"
            class="guide-dialog-close"
            aria-label="关闭"
            @click="requestClose"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>

          <header v-if="exportStyle" class="app-export-header">
            <div class="app-export-header__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 8h16v11H4z" />
                <path d="M9 8V5h6v3M4 12h16" />
                <path d="M10 12v2h4v-2" />
              </svg>
            </div>
            <div class="app-export-header__copy">
              <div class="app-export-header__title-row">
                <h2 :id="titleId">{{ title }}</h2>
                <span v-if="badge" class="app-export-badge app-export-badge--warning">{{ badge }}</span>
                <slot name="title-extra" />
              </div>
              <p v-if="description" :id="descriptionId">{{ description }}</p>
            </div>
            <button
              v-if="showCloseIcon"
              type="button"
              class="app-export-icon-button"
              aria-label="关闭"
              @click="requestClose"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6 6 18" />
              </svg>
            </button>
          </header>

          <div :class="exportStyle ? 'guide-dialog-export-body' : 'guide-dialog-body'">
            <template v-if="!exportStyle">
              <p v-if="eyebrow" class="guide-dialog-eyebrow" :data-tone="tone">{{ eyebrow }}</p>
              <div class="guide-dialog-title-row">
                <h2 :id="titleId" class="guide-dialog-title">{{ title }}</h2>
                <slot name="title-extra" />
              </div>
              <p v-if="description" :id="descriptionId" class="guide-dialog-description">{{ description }}</p>
            </template>

            <!-- 要点用编号 + 发丝分隔，读起来像规格说明，不再是彩框里的绿勾清单 -->
            <ol v-if="details.length" class="guide-dialog-details">
              <li v-for="(detail, index) in details" :key="`${index}-${detail}`">
                <span class="guide-dialog-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
                <span>{{ detail }}</span>
              </li>
            </ol>

            <slot />

            <p v-if="note" class="guide-dialog-note">{{ note }}</p>

            <ErrorNotice v-if="errorMessage" :message="errorMessage" compact class="guide-dialog-error" />
          </div>

          <footer
            v-if="primaryLabel || secondaryLabel"
            :class="exportStyle ? 'app-export-footer guide-dialog-export-footer' : 'guide-dialog-actions'"
            :data-actions="secondaryLabel ? 'two' : 'one'"
          >
            <div :class="exportStyle ? 'app-export-footer__actions' : 'guide-dialog-action-buttons'">
              <button
                v-if="secondaryLabel"
                type="button"
                :class="exportStyle ? 'app-export-secondary-button' : 'guide-dialog-button guide-dialog-button--secondary'"
                :disabled="busy"
                @click="$emit('secondary')"
              >
                {{ secondaryLabel }}
              </button>
              <button
                ref="primaryButton"
                type="button"
                :class="exportStyle ? 'app-export-primary-button' : 'guide-dialog-button guide-dialog-button--primary'"
                :disabled="busy"
                @click="$emit('primary')"
              >
                <svg v-if="busy" class="guide-dialog-spinner" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity="0.25" />
                  <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
                </svg>
                {{ primaryLabel }}
              </button>
            </div>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  eyebrow: { type: String, default: '操作提示' },
  title: { type: String, required: true },
  description: { type: String, required: true },
  details: { type: Array, default: () => [] },
  note: { type: String, default: '' },
  errorMessage: { type: String, default: '' },
  primaryLabel: { type: String, default: '我知道了，继续' },
  secondaryLabel: { type: String, default: '' },
  tone: { type: String, default: 'guide' },
  busy: { type: Boolean, default: false },
  dismissible: { type: Boolean, default: true },
  wide: { type: Boolean, default: false },
  showCloseIcon: { type: Boolean, default: false },
  exportStyle: { type: Boolean, default: false },
  badge: { type: String, default: '' }
})

const emit = defineEmits(['primary', 'secondary', 'close'])
const dialogPanel = ref(null)
const primaryButton = ref(null)
const id = useId()
const titleId = `guide-dialog-title-${id}`
const descriptionId = `guide-dialog-description-${id}`
let previouslyFocusedElement = null

const requestClose = () => {
  if (!props.dismissible || props.busy) return
  emit('close')
}

const onKeydown = (event) => {
  if (!props.open) return
  if (event.key === 'Escape') {
    requestClose()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = Array.from(
    dialogPanel.value?.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])') || []
  )
  if (!focusable.length) {
    event.preventDefault()
    dialogPanel.value?.focus?.()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      previouslyFocusedElement = document.activeElement
      await nextTick()
      primaryButton.value?.focus?.()
      return
    }

    const focusTarget = previouslyFocusedElement
    previouslyFocusedElement = null
    await nextTick()
    focusTarget?.focus?.()
  }
)

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.guide-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 180;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(14, 22, 18, 0.44);
}

.guide-dialog-overlay--export {
  z-index: 12000;
  padding: 16px;
  background: rgba(25, 25, 25, 0.48);
  backdrop-filter: blur(2px);
}

/* 一整块连续表面：不分头/身/脚色带，层级交给字号、留白和发丝线 */
.guide-dialog-panel {
  position: relative;
  display: flex;
  width: min(460px, 100%);
  max-height: min(760px, calc(100vh - 48px));
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(16, 32, 24, 0.1);
  border-radius: 14px;
  background: #ffffff;
  color: #16201a;
  outline: none;
}

.guide-dialog-panel--export {
  width: min(460px, calc(100vw - 32px));
  height: auto;
  min-height: 0;
  max-height: min(760px, calc(100dvh - 32px));
  border-radius: 8px;
}

.guide-dialog-panel--export.guide-dialog-panel--wide {
  width: min(1000px, calc(100vw - 32px));
  max-height: min(720px, calc(100dvh - 32px));
}

.guide-dialog-export-body {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  background: var(--app-surface-soft);
}

.guide-dialog-export-body:empty { display: none; }

.guide-dialog-export-footer { justify-content: flex-end; }

.guide-dialog-export-footer[data-actions='two'] .app-export-footer__actions {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.guide-dialog-export-footer[data-actions='two'] :is(.app-export-secondary-button, .app-export-primary-button) {
  width: 100%;
}
.guide-dialog-action-buttons { display: contents; }

.guide-dialog-panel--export .app-export-header + .app-export-footer {
  border-top: 0;
}

.guide-dialog-close {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 1;
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #8a948e;
  transition: color 150ms ease, background-color 150ms ease;
}

.guide-dialog-close:hover {
  color: #26312b;
  background: rgba(16, 32, 24, 0.05);
}

.guide-dialog-close svg {
  width: 16px;
  height: 16px;
}

.guide-dialog-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-right: 32px;
}

.guide-dialog-title-row .guide-dialog-title {
  min-width: 0;
}

.guide-dialog-panel--wide {
  width: min(1000px, 100%);
  max-height: min(720px, calc(100vh - 48px));
}

.guide-dialog-panel--wide .guide-dialog-body {
  padding: 24px 24px 18px;
}

.guide-dialog-panel--wide .guide-dialog-title {
  font-size: 18px;
}

.guide-dialog-panel--wide .guide-dialog-description {
  margin-top: 6px;
  font-size: 12.5px;
}

.guide-dialog-panel--wide .guide-dialog-actions[data-actions='one'] {
  grid-template-columns: 96px;
  justify-content: end;
  padding: 14px 24px 20px;
}

.guide-dialog-body {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 28px 28px 24px;
}

/* 提示类别只靠一行小字的颜色区分，不做图标彩块 */
.guide-dialog-eyebrow {
  margin: 0 0 10px;
  color: #79837c;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.4;
}

.guide-dialog-eyebrow[data-tone='warning'] { color: #b07d22; }

.guide-dialog-title {
  margin: 0;
  color: #16201a;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.022em;
  line-height: 1.35;
}

.guide-dialog-description {
  margin: 10px 0 0;
  color: #6b756e;
  font-size: 14px;
  line-height: 1.75;
}

/* 要点：编号 + 行间发丝线，读起来像规格说明 */
.guide-dialog-details {
  margin: 22px 0 0;
  padding: 0;
  list-style: none;
  counter-reset: none;
}

.guide-dialog-details li {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 12px;
  padding: 11px 0;
  border-top: 1px solid rgba(16, 32, 24, 0.07);
  color: #3f4a44;
  font-size: 13.5px;
  line-height: 1.65;
}

.guide-dialog-details li:last-child {
  border-bottom: 1px solid rgba(16, 32, 24, 0.07);
}

.guide-dialog-index {
  color: #b3bab6;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  line-height: 1.9;
  letter-spacing: 0.02em;
}

.guide-dialog-note {
  margin: 18px 0 0;
  color: #6f7a73;
  font-size: 12.5px;
  line-height: 1.7;
}

.guide-dialog-error { margin-top: 18px; }

.guide-dialog-actions {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  padding: 20px 28px 24px;
}

/* 单按钮铺满整行，双按钮等分并排：两种情况都不会出现「孤零零挂在右下角」 */
.guide-dialog-actions[data-actions='one'] { grid-template-columns: minmax(0, 1fr); }
.guide-dialog-actions[data-actions='two'] { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.guide-dialog-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 18px;
  border: 1px solid transparent;
  border-radius: 9px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease;
}

.guide-dialog-button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px #ffffff, 0 0 0 4px rgba(7, 193, 96, 0.35);
}

.guide-dialog-button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.guide-dialog-button--secondary {
  border-color: rgba(16, 32, 24, 0.14);
  color: #3d4541;
  background: transparent;
}

.guide-dialog-button--secondary:hover:not(:disabled) {
  background: rgba(16, 32, 24, 0.04);
}

.guide-dialog-button--primary {
  color: #ffffff;
  background: #07c160;
}

.guide-dialog-button--primary:hover:not(:disabled) { background: #06ad56; }
.guide-dialog-button--primary:active:not(:disabled) { background: #059b4d; }

.guide-dialog-spinner {
  width: 16px;
  height: 16px;
  animation: guide-dialog-spin 0.8s linear infinite;
}

.guide-dialog-enter-active,
.guide-dialog-leave-active { transition: opacity 180ms ease; }

.guide-dialog-enter-active .guide-dialog-panel,
.guide-dialog-leave-active .guide-dialog-panel {
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1), opacity 180ms ease;
}

.guide-dialog-enter-from,
.guide-dialog-leave-to { opacity: 0; }

.guide-dialog-enter-from .guide-dialog-panel,
.guide-dialog-leave-to .guide-dialog-panel {
  opacity: 0;
  transform: translateY(10px) scale(0.985);
}

@keyframes guide-dialog-spin {
  to { transform: rotate(360deg); }
}

/* 深色：整块表面同样不分色带，只把发丝线和文字层级换到深色一侧 */
html[data-theme='dark'] .guide-dialog-overlay {
  background: rgba(0, 0, 0, 0.58);
}

html[data-theme='dark'] .guide-dialog-panel {
  border-color: var(--setup-border);
  background: var(--app-surface-bg);
  color: var(--app-text-primary);
}

html[data-theme='dark'] .guide-dialog-title {
  color: var(--app-text-primary);
}

html[data-theme='dark'] .guide-dialog-eyebrow {
  color: var(--setup-text-muted);
}

html[data-theme='dark'] .guide-dialog-eyebrow[data-tone='warning'] {
  color: var(--setup-warn);
}

html[data-theme='dark'] .guide-dialog-description,
html[data-theme='dark'] .guide-dialog-note {
  color: var(--setup-text-secondary);
}

html[data-theme='dark'] .guide-dialog-details li {
  border-top-color: rgba(255, 255, 255, 0.09);
  color: var(--setup-text-secondary);
}

html[data-theme='dark'] .guide-dialog-details li:last-child {
  border-bottom-color: rgba(255, 255, 255, 0.09);
}

html[data-theme='dark'] .guide-dialog-index {
  color: var(--setup-text-muted);
}

html[data-theme='dark'] .guide-dialog-button:focus-visible {
  box-shadow: 0 0 0 2px var(--app-surface-bg), 0 0 0 4px rgba(62, 181, 117, 0.45);
}

html[data-theme='dark'] .guide-dialog-button--secondary {
  border-color: rgba(255, 255, 255, 0.16);
  color: var(--setup-text-secondary);
}

html[data-theme='dark'] .guide-dialog-button--secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.06);
}

html[data-theme='dark'] .guide-dialog-close {
  color: var(--setup-text-muted);
}

html[data-theme='dark'] .guide-dialog-close:hover {
  color: var(--app-text-primary);
  background: rgba(255, 255, 255, 0.07);
}

@media (max-width: 520px) {
  .guide-dialog-overlay {
    align-items: flex-end;
    padding: 12px;
  }

  .guide-dialog-panel { max-height: calc(100vh - 24px); }
  .guide-dialog-body { padding: 22px 20px 18px; }
  .guide-dialog-actions[data-actions='two'] { grid-template-columns: minmax(0, 1fr); }
  .guide-dialog-actions { padding: 18px 20px 20px; }
}

@media (prefers-reduced-motion: reduce) {
  .guide-dialog-enter-active,
  .guide-dialog-leave-active,
  .guide-dialog-enter-active .guide-dialog-panel,
  .guide-dialog-leave-active .guide-dialog-panel { transition: none; }
}
</style>
