<template>
  <div class="error-notice" :class="{ 'error-notice--compact': compact }" role="alert">
    <div class="error-notice__message">{{ normalizedMessage }}</div>
    <div class="error-notice__guidance">
      <span>{{ guidance }}</span>
      <button
        v-if="!manual"
        type="button"
        class="error-notice__action"
        @click="openLogSettings"
      >
        打开设置
      </button>
    </div>
  </div>
</template>

<script setup>
import {
  ERROR_LOG_GUIDANCE,
  ERROR_LOG_MANUAL_GUIDANCE,
} from '~/composables/useErrorNotice'

const props = defineProps({
  message: {
    type: [String, Number],
    default: '',
  },
  compact: {
    type: Boolean,
    default: false,
  },
  manual: {
    type: Boolean,
    default: false,
  },
})

const { openDialog } = useSettingsDialog()
const normalizedMessage = computed(() => String(props.message || '').trim() || '操作失败')
const guidance = computed(() => props.manual ? ERROR_LOG_MANUAL_GUIDANCE : ERROR_LOG_GUIDANCE)
const openLogSettings = () => openDialog('log-file')
</script>

<style scoped>
.error-notice {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.error-notice:not(.error-notice--compact) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
  line-height: 1.55;
}

.error-notice__message {
  font-weight: 500;
}

.error-notice__guidance {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  color: #7f1d1d;
  font-size: 12px;
  font-weight: 400;
}

.error-notice--compact .error-notice__guidance {
  margin-top: 8px;
  color: currentColor;
  opacity: 0.88;
}

.error-notice__action {
  flex: none;
  border: 1px solid currentColor;
  border-radius: 6px;
  padding: 3px 8px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
}

.error-notice__action:hover {
  background: rgba(185, 28, 28, 0.08);
}

html[data-theme='dark'] .error-notice:not(.error-notice--compact) {
  border-color: #7f1d1d;
  background: #2b1719;
  color: #fca5a5;
}

html[data-theme='dark'] .error-notice:not(.error-notice--compact) .error-notice__guidance {
  color: #fecaca;
}

@media (max-width: 640px) {
  .error-notice__guidance {
    flex-direction: column;
  }
}
</style>
