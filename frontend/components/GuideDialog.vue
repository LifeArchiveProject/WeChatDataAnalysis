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
          class="guide-dialog-panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
          tabindex="-1"
        >
          <div class="guide-dialog-heading">
            <div class="guide-dialog-icon" :data-tone="tone" aria-hidden="true">
              <svg v-if="tone === 'warning'" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
              </svg>
              <svg v-else-if="tone === 'info'" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <circle cx="12" cy="12" r="9" stroke-width="1.8" />
                <path stroke-linecap="round" stroke-width="1.8" d="M12 10.5V17m0-10h.01" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M8.5 11.5h7M8.5 15h4.5M6 4h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H9l-5 3v-4.5A2 2 0 0 1 2 15.5V8a4 4 0 0 1 4-4Z" />
              </svg>
            </div>

            <div class="guide-dialog-copy">
              <p v-if="eyebrow" class="guide-dialog-eyebrow">{{ eyebrow }}</p>
              <h2 :id="titleId">{{ title }}</h2>
              <p :id="descriptionId" class="guide-dialog-description">{{ description }}</p>
            </div>
          </div>

          <ul v-if="details.length" class="guide-dialog-details">
            <li v-for="(detail, index) in details" :key="`${index}-${detail}`">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="m5 10 3 3 7-7" />
              </svg>
              <span>{{ detail }}</span>
            </li>
          </ul>

          <p v-if="note" class="guide-dialog-note">{{ note }}</p>

          <footer class="guide-dialog-actions">
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
  padding: 20px;
  background: rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(4px);
}

.guide-dialog-panel {
  width: min(520px, 100%);
  max-height: min(720px, calc(100vh - 40px));
  overflow-y: auto;
  border: 1px solid var(--app-border, #e7e7e7);
  border-radius: 8px;
  background: var(--app-surface-bg, #ffffff);
  color: var(--app-text-primary, #191919);
  box-shadow: 0 20px 54px rgba(0, 0, 0, 0.2);
  outline: none;
  padding: 24px;
}

.guide-dialog-heading {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.guide-dialog-icon {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  place-items: center;
  border-radius: 8px;
  color: #07a951;
  background: rgba(7, 193, 96, 0.1);
}

.guide-dialog-icon[data-tone='warning'] {
  color: #b86d00;
  background: rgba(250, 173, 20, 0.14);
}

.guide-dialog-icon[data-tone='info'] {
  color: #1677a6;
  background: rgba(16, 174, 239, 0.12);
}

.guide-dialog-icon svg {
  width: 23px;
  height: 23px;
}

.guide-dialog-copy {
  min-width: 0;
}

.guide-dialog-eyebrow {
  margin: 0 0 5px;
  color: var(--app-accent, #07c160);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.guide-dialog-copy h2 {
  margin: 0;
  color: var(--app-text-primary, #191919);
  font-size: 20px;
  font-weight: 650;
  line-height: 1.4;
  letter-spacing: 0;
}

.guide-dialog-description {
  margin: 8px 0 0;
  color: var(--app-text-secondary, #5f5f5f);
  font-size: 14px;
  line-height: 1.75;
}

.guide-dialog-details {
  margin: 20px 0 0;
  padding: 0;
  list-style: none;
}

.guide-dialog-details li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid var(--app-border-soft, #ececec);
  color: var(--app-text-secondary, #5f5f5f);
  font-size: 13px;
  line-height: 1.65;
}

.guide-dialog-details svg {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  margin-top: 2px;
  color: var(--app-accent, #07c160);
}

.guide-dialog-note {
  margin: 16px 0 0;
  padding-left: 12px;
  border-left: 3px solid rgba(250, 173, 20, 0.8);
  color: var(--app-text-muted, #909090);
  font-size: 12px;
  line-height: 1.65;
}

.guide-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--app-border-soft, #ececec);
}

.guide-dialog-button {
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: 7px;
  padding: 9px 16px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease;
}

.guide-dialog-button:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.32);
  outline-offset: 2px;
}

.guide-dialog-button:disabled {
  cursor: wait;
  opacity: 0.62;
}

.guide-dialog-button--secondary {
  border: 1px solid var(--app-border, #e7e7e7);
  color: var(--app-text-secondary, #5f5f5f);
  background: var(--app-neutral-btn-bg, #ffffff);
}

.guide-dialog-button--secondary:hover:not(:disabled) {
  background: var(--app-neutral-btn-hover, #f7f7f7);
}

.guide-dialog-button--primary {
  border: 1px solid var(--app-accent, #07c160);
  color: #ffffff;
  background: var(--app-accent, #07c160);
}

.guide-dialog-button--primary:hover:not(:disabled) {
  border-color: var(--app-accent-hover, #06ad56);
  background: var(--app-accent-hover, #06ad56);
}

.guide-dialog-spinner {
  width: 16px;
  height: 16px;
  animation: guide-dialog-spin 0.8s linear infinite;
}

.guide-dialog-enter-active,
.guide-dialog-leave-active {
  transition: opacity 160ms ease;
}

.guide-dialog-enter-active .guide-dialog-panel,
.guide-dialog-leave-active .guide-dialog-panel {
  transition: transform 180ms ease, opacity 160ms ease;
}

.guide-dialog-enter-from,
.guide-dialog-leave-to {
  opacity: 0;
}

.guide-dialog-enter-from .guide-dialog-panel,
.guide-dialog-leave-to .guide-dialog-panel {
  opacity: 0;
  transform: translateY(8px) scale(0.985);
}

@keyframes guide-dialog-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 520px) {
  .guide-dialog-overlay {
    align-items: flex-end;
    padding: 12px;
  }

  .guide-dialog-panel {
    max-height: calc(100vh - 24px);
    padding: 20px;
  }

  .guide-dialog-actions {
    flex-direction: column-reverse;
  }

  .guide-dialog-button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .guide-dialog-enter-active,
  .guide-dialog-leave-active,
  .guide-dialog-enter-active .guide-dialog-panel,
  .guide-dialog-leave-active .guide-dialog-panel {
    transition: none;
  }
}
</style>
