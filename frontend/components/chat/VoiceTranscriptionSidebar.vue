<template>
  <transition name="sidebar-slide">
    <aside
      v-if="voiceSidebarOpen"
      class="resource-sidebar voice-transcription-sidebar flex h-full flex-shrink-0 flex-col border-l"
      aria-label="语音转文字"
    >
      <div class="resource-sidebar-header flex items-center gap-1.5 border-b px-3 py-2.5">
        <div class="min-w-0 flex-1">
          <div class="resource-sidebar-title flex items-center gap-2 text-sm font-medium">
            <svg class="resource-sidebar-icon h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="8" y="3" width="8" height="12" rx="4" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
            </svg>
            <span>语音转文字</span>
          </div>
          <div class="resource-sidebar-muted mt-0.5 text-[11px]">批量转写当前账号语音</div>
        </div>
        <button
          type="button"
          class="resource-sidebar-close rounded-md p-1 transition-colors"
          :disabled="voicePanelBusy"
          title="刷新状态"
          aria-label="刷新语音转文字状态"
          @click="refreshVoicePanel"
        >
          <svg class="h-4 w-4" :class="{ 'animate-spin': voicePanelBusy || voiceTranscriptionStatusLoading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M20 6v5h-5M4 18v-5h5M6.1 9A7 7 0 0 1 18 6l2 5M17.9 15A7 7 0 0 1 6 18l-2-5" />
          </svg>
        </button>
        <button
          type="button"
          class="resource-sidebar-close rounded-md p-1 transition-colors"
          title="关闭"
          aria-label="关闭语音转文字面板"
          @click="closeVoiceSidebar"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="min-h-0 flex-1 space-y-0 overflow-y-auto px-4 py-1 scrollbar-custom">
        <div v-if="voicePanelError" class="voice-panel-alert" role="alert">{{ voicePanelError }}</div>

        <section class="voice-panel-section" aria-labelledby="voice-model-title">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h3 id="voice-model-title" class="voice-panel-heading">识别模型</h3>
              <p class="voice-panel-muted mt-0.5">模型保存在本机</p>
            </div>
            <span class="voice-status-badge" :class="voiceStatus.modelReady ? 'is-ready' : 'is-missing'">
              {{ voiceStatus.modelReady ? '模型已就绪' : '模型未下载' }}
            </span>
          </div>

          <label class="mt-2 block text-[11px] font-medium" for="voice-model-select">当前模型</label>
          <select
            id="voice-model-select"
            class="voice-model-select mt-1 w-full rounded-md border px-2.5 py-1.5 text-xs outline-none"
            :value="voiceCurrentModel"
            :disabled="voicePanelBusy || voiceBatchActive || voiceModelLocked || !voiceSelectableModels.length"
            @change="onModelChange"
          >
            <option
              v-if="voiceCurrentModel && (!voiceCurrentModelInfo || !voiceCurrentModelInfo.downloaded)"
              :value="voiceCurrentModel"
              disabled
            >
              {{ voiceCurrentModelInfo?.name || voiceCurrentModel }} · 未下载
            </option>
            <option v-for="model in voiceSelectableModels" :key="model.id" :value="model.id">
              {{ model.name || model.id }} · 已下载
            </option>
          </select>
          <div class="mt-1.5 flex items-start justify-between gap-2">
            <p v-if="voiceCurrentModelInfo" class="voice-panel-muted min-w-0 text-[11px]">
              {{ voiceCurrentModelInfo.size || '' }}
              <span v-if="voiceCurrentModelInfo.quality"> · {{ voiceCurrentModelInfo.quality }}</span>
              <span v-if="voiceCurrentModelInfo.speed"> · {{ voiceCurrentModelInfo.speed }}</span>
            </p>
            <button
              type="button"
              class="voice-model-settings shrink-0 text-[11px] font-medium"
              @click="openVoiceModelSettings"
            >下载或管理模型</button>
          </div>
          <p v-if="voiceModelLocked" class="voice-panel-warning mt-1.5 text-[11px]">模型由启动环境变量固定，请在设置中查看当前状态。</p>
          <p v-if="!voiceStatus.available && voiceStatus.reason" class="voice-panel-warning mt-1.5 text-[11px]">
            {{ voiceStatus.reason }}
          </p>
        </section>

        <section class="voice-panel-section" aria-labelledby="voice-device-title">
          <div class="flex items-center justify-between gap-2">
            <div>
              <h3 id="voice-device-title" class="voice-panel-heading">推理设备</h3>
              <p class="voice-panel-muted mt-0.5">CUDA 失败自动回退 CPU</p>
            </div>
            <span class="voice-panel-device-label">{{ voiceActiveDeviceLabel }}</span>
          </div>
          <div class="voice-device-switch mt-2 grid grid-cols-2 gap-0.5 rounded-md p-0.5" role="radiogroup" aria-label="推理设备">
            <button
              type="button"
              class="voice-device-cpu rounded-[5px] px-2 py-1.5 text-[11px] font-medium"
              :class="{ 'is-active': voiceRequestedDevice === 'cpu' }"
              :aria-checked="voiceRequestedDevice === 'cpu'"
              :disabled="voicePanelBusy || voiceBatchActive || voiceDeviceLocked"
              role="radio"
              @click="setVoicePanelDevice('cpu')"
            >CPU</button>
            <button
              type="button"
              class="voice-device-cuda rounded-[5px] px-2 py-1.5 text-[11px] font-medium"
              :class="{ 'is-active': voiceRequestedDevice === 'cuda' }"
              :aria-checked="voiceRequestedDevice === 'cuda'"
              :disabled="voicePanelBusy || voiceBatchActive || voiceDeviceLocked || !voiceCudaAvailable"
              role="radio"
              @click="setVoicePanelDevice('cuda')"
            >NVIDIA GPU</button>
          </div>
          <p class="voice-panel-muted mt-1.5 truncate" :title="voiceCudaDeviceName || voiceStatus.cuda?.reason || ''">
            {{ voiceCudaAvailable ? (voiceCudaDeviceName || '已检测到可用 NVIDIA GPU') : (voiceStatus.cuda?.reason || '未检测到可用 NVIDIA GPU') }}
          </p>
          <p v-if="voiceDeviceLocked" class="voice-panel-warning mt-1.5 text-[11px]">推理设备由启动环境变量固定，无法在这里切换。</p>
        </section>

        <section class="voice-panel-section" aria-labelledby="voice-batch-title">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h3 id="voice-batch-title" class="voice-panel-heading">全部语音</h3>
              <p class="voice-panel-muted mt-0.5">优先复用微信原生转写</p>
            </div>
            <div class="flex flex-wrap items-center justify-end gap-1">
              <span v-if="voiceBatchActualConcurrency" class="voice-status-badge is-concurrency">并发 {{ voiceBatchActualConcurrency }}</span>
              <span class="voice-status-badge" :class="voiceBatchActive ? 'is-running' : ''">{{ voiceBatchStatusLabel }}</span>
            </div>
          </div>

          <div class="mt-2 flex items-start justify-between gap-2">
            <label for="voice-batch-concurrency" class="voice-panel-muted font-medium">并发线程数</label>
            <div class="min-w-0 text-right">
              <div class="flex items-center justify-end gap-1.5">
                <input
                  id="voice-batch-concurrency"
                  class="voice-concurrency-select h-7 w-14 rounded-md border px-1.5 text-center text-[11px] tabular-nums outline-none"
                  type="number"
                  min="0"
                  step="1"
                  inputmode="numeric"
                  :value="voiceBatchConcurrencyDraft"
                  :disabled="voicePanelBusy || voiceBatchActive"
                  :aria-invalid="voiceBatchConcurrencyError ? 'true' : 'false'"
                  :aria-describedby="voiceBatchConcurrencyError ? 'voice-batch-concurrency-hint voice-batch-concurrency-error' : 'voice-batch-concurrency-hint'"
                  title="0 自动，输入正整数"
                  @input="onConcurrencyInput"
                  @blur="commitConcurrencyDraft"
                  @keydown.enter.prevent="commitConcurrencyDraft"
                >
                <span id="voice-batch-concurrency-hint" class="voice-panel-muted whitespace-nowrap">0 自动，输入正整数</span>
              </div>
              <p v-if="voiceBatchConcurrencyError" id="voice-batch-concurrency-error" class="voice-concurrency-error mt-1 text-[10px]" role="alert">
                {{ voiceBatchConcurrencyError }}
              </p>
            </div>
          </div>

          <template v-if="voiceBatchHasProgress">
            <div class="mt-3 flex items-center justify-between text-[11px]">
              <span>{{ voiceBatchCompleted }} / {{ voiceBatchTotal }}</span>
              <span>{{ voiceBatchPercent }}%</span>
            </div>
            <div
              class="voice-progress mt-1 h-1.5 overflow-hidden rounded-full"
              role="progressbar"
              aria-label="批量语音转写进度"
              :aria-valuemin="0"
              :aria-valuemax="100"
              :aria-valuenow="voiceBatchPercent"
            >
              <div class="voice-progress-bar h-full rounded-full" :style="{ width: `${voiceBatchPercent}%` }" />
            </div>
            <div class="mt-2 grid grid-cols-3 gap-1.5 text-center">
              <div class="voice-stat"><strong>{{ voiceBatchProject }}</strong><span>本项目转写</span></div>
              <div class="voice-stat"><strong>{{ voiceBatchNative }}</strong><span>微信原生转写</span></div>
              <div class="voice-stat"><strong>{{ voiceBatchFailed }}</strong><span>失败</span></div>
            </div>
          </template>
          <p v-else class="voice-panel-muted mt-2">仅处理当前账号中尚无文字的语音。</p>

          <p v-if="voiceBatchJob?.error" class="voice-panel-warning mt-2 text-[11px]">{{ voiceBatchJob.error }}</p>
          <p v-if="voiceBatchJob?.warning" class="voice-panel-warning mt-2 text-[11px]">{{ voiceBatchJob.warning }}</p>

          <button
            v-if="voiceBatchActive"
            type="button"
            class="voice-batch-cancel mt-3 w-full rounded-md border px-3 py-1.5 text-xs font-medium transition-colors"
            :disabled="voicePanelBusy"
            @click="cancelVoiceBatch"
          >取消批量转写</button>
          <button
            v-else
            type="button"
            class="voice-batch-start mt-3 w-full rounded-md px-3 py-1.5 text-xs font-medium text-white transition-colors"
            :disabled="voicePanelBusy || !voiceStatus.available"
            @click="onStartVoiceBatch"
          >{{ voiceBatchStatus === 'done' ? '再次扫描全部语音' : '转写全部语音' }}</button>
        </section>
      </div>
    </aside>
  </transition>
</template>

<script>
import { computed, defineComponent, ref, watch } from 'vue'

const readMaybeRef = (value) => {
  if (value && typeof value === 'object' && 'value' in value) return value.value
  return value
}

const activeBatchStatuses = new Set(['queued', 'running'])

export default defineComponent({
  name: 'VoiceTranscriptionSidebar',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    const voiceStatus = computed(() => readMaybeRef(props.state.voiceTranscriptionStatus) || {})
    const voiceModels = computed(() => Array.isArray(voiceStatus.value.models) ? voiceStatus.value.models : [])
    const voiceSelectableModels = computed(() => voiceModels.value.filter((model) => model?.downloaded === true))
    const voiceCurrentModel = computed(() => String(voiceStatus.value.model || '').trim())
    const voiceCurrentModelInfo = computed(() => {
      return voiceModels.value.find((model) => String(model?.id || '') === voiceCurrentModel.value) || null
    })
    const voiceRequestedDevice = computed(() => {
      const device = String(voiceStatus.value.requestedDevice || voiceStatus.value.device || 'cpu').toLowerCase()
      return device === 'cuda' ? 'cuda' : 'cpu'
    })
    const voiceCudaAvailable = computed(() => voiceStatus.value.cuda?.available === true)
    const voiceCudaDeviceName = computed(() => {
      const devices = Array.isArray(voiceStatus.value.cuda?.devices) ? voiceStatus.value.cuda.devices : []
      return String(devices[0]?.name || '').trim()
    })
    const voiceModelLocked = computed(() => String(voiceStatus.value.modelSettingSource || '') === 'env')
    const voiceDeviceLocked = computed(() => String(voiceStatus.value.deviceSource || '') === 'env')
    const voiceActiveDeviceLabel = computed(() => {
      const active = String(voiceStatus.value.activeDevice || '').toLowerCase()
      if (active === 'cuda') return 'NVIDIA GPU'
      if (active === 'cpu') return 'CPU'
      return voiceRequestedDevice.value === 'cuda' ? 'NVIDIA GPU' : 'CPU'
    })

    const voiceBatchJob = computed(() => readMaybeRef(props.state.voiceBatchJob) || { status: 'idle' })
    const voiceBatchStatus = computed(() => String(voiceBatchJob.value.status || 'idle').toLowerCase())
    const voiceBatchActive = computed(() => activeBatchStatuses.has(voiceBatchStatus.value))
    const normalizeVoiceBatchConcurrency = (value) => {
      const concurrency = Number(value)
      return Number.isInteger(concurrency) && concurrency >= 0 ? concurrency : 0
    }
    const voiceBatchConcurrency = computed(() => normalizeVoiceBatchConcurrency(readMaybeRef(props.state.voiceBatchConcurrency)))
    const voiceBatchConcurrencyDraft = ref('0')
    const voiceBatchConcurrencyError = ref('')
    const voiceBatchConcurrencyBadInput = ref(false)
    const voiceBatchActualConcurrency = computed(() => normalizeVoiceBatchConcurrency(voiceBatchJob.value.concurrency))
    const voiceBatchTotal = computed(() => Math.max(0, Number(voiceBatchJob.value.total || 0)))
    const voiceBatchCompleted = computed(() => Math.max(0, Number(voiceBatchJob.value.completed || 0)))
    const voiceBatchPercent = computed(() => Math.min(100, Math.max(0, Number(voiceBatchJob.value.percent || 0))))
    const voiceBatchSuccess = computed(() => Math.max(0, Number(voiceBatchJob.value.success || 0)))
    const voiceBatchNative = computed(() => Math.max(0, Number(voiceBatchJob.value.native || 0)))
    const voiceBatchProject = computed(() => Math.max(0, voiceBatchSuccess.value - voiceBatchNative.value))
    const voiceBatchFailed = computed(() => Math.max(0, Number(voiceBatchJob.value.failed || 0)))
    const voiceBatchHasProgress = computed(() => voiceBatchTotal.value > 0 || voiceBatchActive.value || voiceBatchStatus.value === 'done')
    const voiceBatchStatusLabel = computed(() => ({
      idle: '未开始',
      queued: '排队中',
      running: '转换中',
      done: '已完成',
      cancelled: '已取消',
      error: '失败'
    })[voiceBatchStatus.value] || voiceBatchStatus.value)

    const onModelChange = (event) => {
      const model = String(event?.target?.value || '').trim()
      if (voiceSelectableModels.value.some((item) => String(item?.id || '') === model)) {
        props.state.setVoicePanelModel?.(model)
      }
    }

    const parseConcurrencyDraft = (value) => {
      const draft = String(value ?? '').trim()
      if (!draft) return { valid: true, value: 0 }
      const concurrency = Number(draft)
      return Number.isInteger(concurrency) && concurrency >= 0
        ? { valid: true, value: concurrency }
        : { valid: false, value: null }
    }

    const syncConcurrencyDraft = (value) => {
      voiceBatchConcurrencyDraft.value = String(normalizeVoiceBatchConcurrency(value))
      voiceBatchConcurrencyError.value = ''
      voiceBatchConcurrencyBadInput.value = false
    }

    watch(voiceBatchConcurrency, syncConcurrencyDraft, { immediate: true })
    watch(voiceBatchJob, (job) => {
      if (job && Object.prototype.hasOwnProperty.call(job, 'requestedConcurrency')) {
        syncConcurrencyDraft(job.requestedConcurrency)
      }
    }, { immediate: true })

    const onConcurrencyInput = (event) => {
      voiceBatchConcurrencyDraft.value = String(event?.target?.value ?? '')
      voiceBatchConcurrencyBadInput.value = event?.target?.validity?.badInput === true
      if (!voiceBatchConcurrencyBadInput.value && parseConcurrencyDraft(voiceBatchConcurrencyDraft.value).valid) {
        voiceBatchConcurrencyError.value = ''
      }
    }

    const commitConcurrencyDraft = (event) => {
      if (voiceBatchActive.value || readMaybeRef(props.state.voicePanelBusy)) return false
      const parsed = parseConcurrencyDraft(voiceBatchConcurrencyDraft.value)
      if (voiceBatchConcurrencyBadInput.value || event?.target?.validity?.badInput === true || !parsed.valid) {
        voiceBatchConcurrencyError.value = '不支持：请输入 0 或正整数'
        return false
      }
      voiceBatchConcurrencyDraft.value = String(parsed.value)
      if (event?.target) event.target.value = String(parsed.value)
      voiceBatchConcurrencyError.value = ''
      voiceBatchConcurrencyBadInput.value = false
      props.state.setVoiceBatchConcurrency?.(parsed.value)
      return true
    }

    const onStartVoiceBatch = () => {
      if (!commitConcurrencyDraft()) return
      props.state.startVoiceBatch?.()
    }

    return {
      ...props.state,
      voiceStatus,
      voiceModels,
      voiceSelectableModels,
      voiceCurrentModel,
      voiceCurrentModelInfo,
      voiceRequestedDevice,
      voiceCudaAvailable,
      voiceCudaDeviceName,
      voiceModelLocked,
      voiceDeviceLocked,
      voiceActiveDeviceLabel,
      voiceBatchJob,
      voiceBatchStatus,
      voiceBatchActive,
      voiceBatchConcurrency,
      voiceBatchConcurrencyDraft,
      voiceBatchConcurrencyError,
      voiceBatchActualConcurrency,
      voiceBatchTotal,
      voiceBatchCompleted,
      voiceBatchPercent,
      voiceBatchSuccess,
      voiceBatchNative,
      voiceBatchProject,
      voiceBatchFailed,
      voiceBatchHasProgress,
      voiceBatchStatusLabel,
      onModelChange,
      onConcurrencyInput,
      commitConcurrencyDraft,
      onStartVoiceBatch
    }
  }
})
</script>

<style scoped>
.voice-panel-section {
  border: 0;
  border-bottom: 1px solid var(--search-panel-border, #e5e7eb);
  border-radius: 0;
  background: transparent;
  padding: 12px 0;
}

.voice-panel-section:last-child {
  border-bottom: 0;
}

.voice-transcription-sidebar {
  width: 344px;
  max-width: 42vw;
}

.voice-model-settings {
  color: var(--app-accent);
}

.voice-model-settings:hover {
  color: var(--app-accent-hover);
}

.voice-panel-heading {
  color: var(--search-panel-text, #1f2937);
  font-size: 13px;
  font-weight: 600;
}

.voice-panel-muted {
  color: var(--search-panel-muted, #6b7280);
  font-size: 11px;
  line-height: 1.45;
}

.voice-panel-warning {
  color: color-mix(in srgb, var(--warning-color) 70%, var(--search-panel-text));
  line-height: 1.5;
}

.voice-panel-alert {
  border: 1px solid rgb(239 68 68 / 25%);
  border-radius: 10px;
  background: rgb(239 68 68 / 8%);
  color: var(--danger-color);
  padding: 8px 10px;
  font-size: 11px;
}

.voice-status-badge {
  flex: none;
  border-radius: 999px;
  background: var(--search-input-bg, #fff);
  color: var(--search-panel-muted, #6b7280);
  padding: 2px 7px;
  font-size: 10px;
  line-height: 1.4;
}

.voice-status-badge.is-ready {
  background: color-mix(in srgb, var(--app-accent) 10%, transparent);
  color: var(--app-accent);
}

.voice-status-badge.is-missing {
  background: rgb(245 158 11 / 12%);
  color: #b45309;
}

.voice-status-badge.is-running {
  background: color-mix(in srgb, var(--app-accent) 10%, transparent);
  color: var(--app-accent);
}

.voice-status-badge.is-concurrency {
  background: var(--search-input-bg, #fff);
  color: var(--app-accent);
}

.voice-model-select {
  border-color: var(--search-input-border, #d1d5db);
  background: var(--search-input-bg, #fff);
  color: var(--search-panel-text, #1f2937);
}

.voice-model-select:focus {
  border-color: var(--app-accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--app-accent) 12%, transparent);
}

.voice-concurrency-select {
  border-color: var(--search-input-border, #d1d5db);
  background: var(--search-input-bg, #fff);
  color: var(--search-panel-text, #1f2937);
}

.voice-concurrency-select:focus {
  border-color: var(--app-accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--app-accent) 12%, transparent);
}

.voice-concurrency-select:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.voice-concurrency-select[aria-invalid='true'] {
  border-color: var(--danger-color);
}

.voice-concurrency-error {
  color: var(--danger-color);
}

.voice-panel-device-label {
  color: var(--search-panel-muted, #6b7280);
  font-size: 10px;
}

.voice-device-switch {
  background: var(--search-input-bg, #fff);
}

.voice-device-switch button {
  color: var(--search-panel-muted, #6b7280);
}

.voice-device-switch button:hover:not(:disabled) {
  color: var(--search-panel-text, #1f2937);
}

.voice-device-switch button.is-active {
  background: color-mix(in srgb, var(--app-accent) 10%, transparent);
  color: var(--app-accent);
}

.voice-device-switch button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.voice-progress {
  background: var(--search-input-border, #e5e7eb);
}

.voice-progress-bar {
  background: var(--app-accent);
  transition: width 180ms ease;
}

.voice-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-radius: 6px;
  background: var(--search-input-bg, #fff);
  padding: 5px 3px;
}

.voice-stat strong {
  color: var(--search-panel-text, #1f2937);
  font-size: 12px;
}

.voice-stat span {
  color: var(--search-panel-muted, #6b7280);
  font-size: 9px;
  line-height: 1.3;
}

.voice-batch-start {
  background: var(--app-accent);
}

.voice-batch-start:hover:not(:disabled) {
  background: var(--app-accent-hover);
}

.voice-batch-start:disabled,
.voice-batch-cancel:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.voice-batch-cancel {
  border-color: rgb(239 68 68 / 35%);
  color: var(--danger-color);
}

.voice-batch-cancel:hover:not(:disabled) {
  background: rgb(239 68 68 / 8%);
}

:global(html[data-theme='dark']) .voice-panel-warning {
  color: #fbbf24;
}

:global(html[data-theme='dark']) .voice-panel-alert,
:global(html[data-theme='dark']) .voice-batch-cancel {
  color: #fca5a5;
}

@media (max-width: 1100px) {
  .voice-transcription-sidebar {
    position: absolute;
    inset: 0 0 0 auto;
    z-index: 40;
    width: min(344px, 100%);
    max-width: 100%;
    box-shadow: -16px 0 36px rgb(15 23 42 / 18%);
    overscroll-behavior: contain;
  }
}

</style>
