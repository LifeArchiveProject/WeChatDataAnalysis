<template>
  <Teleport to="body">
    <Transition name="guide-dialog">
      <div
        v-if="open"
        class="guide-dialog-overlay"
        @mousedown.self="requestClose"
      >
        <section
          ref="dialogPanel"
          class="guide-dialog-panel theme-scope"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
          tabindex="-1"
        >
          <div class="guide-dialog-body">
            <p v-if="eyebrow" class="guide-dialog-eyebrow" :data-tone="tone">{{ eyebrow }}</p>
            <h2 :id="titleId" class="guide-dialog-title">{{ title }}</h2>
            <p :id="descriptionId" class="guide-dialog-description">{{ description }}</p>

            <!-- 要点用编号 + 发丝分隔，读起来像规格说明，不再是彩框里的绿勾清单 -->
            <ol v-if="details.length" class="guide-dialog-details">
              <li v-for="(detail, index) in details" :key="`${index}-${detail}`">
                <span class="guide-dialog-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
                <span>{{ detail }}</span>
              </li>
            </ol>

            <p v-if="note" class="guide-dialog-note">{{ note }}</p>

            <ErrorNotice v-if="errorMessage" :message="errorMessage" compact class="guide-dialog-error" />
          </div>

          <footer class="guide-dialog-actions" :data-actions="secondaryLabel ? 'two' : 'one'">
            <button
              v-if="secondaryLabel"
              type="button"
              class="guide-dialog-button guide-dialog-button--secondary"
              :disabled="busy"
              @click="$emit('secondary')"
            >
              {{ secondaryLabel }}
            </button>
            <button
              ref="primaryButton"
              type="button"
              class="guide-dialog-button guide-dialog-button--primary"
              :disabled="busy"
              @click="$emit('primary')"
            >
              <svg v-if="busy" class="guide-dialog-spinner" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity="0.25" />
                <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
              </svg>
              {{ primaryLabel }}
            </button>
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
  dismissible: { type: Boolean, default: true }
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
    dialogPanel.value?.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex="-1"])') || []
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

/* 一整块连续表面：不分头/身/脚色带，层级交给字号、留白和发丝线 */
.guide-dialog-panel {
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
