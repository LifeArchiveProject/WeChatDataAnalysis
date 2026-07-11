<template>
  <Teleport to="body">
    <div v-if="open" class="record-export-backdrop" role="presentation" @mousedown.self="emit('close')">
      <section
        class="record-export-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="`${title}导出`"
        @mousedown.stop
      >
        <header class="record-export-dialog__header">
          <h2>{{ title }}导出</h2>
          <button type="button" class="record-export-icon-button" title="关闭" aria-label="关闭" @click="emit('close')">
            <i class="fa-solid fa-xmark" aria-hidden="true"></i>
          </button>
        </header>

        <div class="record-export-dialog__body">
          <div class="record-export-field">
            <label>导出格式</label>
            <div class="record-export-segments" role="radiogroup" aria-label="导出格式">
              <button
                v-for="option in formatOptions"
                :key="option.value"
                type="button"
                role="radio"
                :aria-checked="format === option.value"
                :class="{ 'is-active': format === option.value }"
                @click="format = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div v-if="normalizedTypeOptions.length" class="record-export-field">
            <div class="record-export-field__label-row">
              <label>内容类型</label>
              <button type="button" class="record-export-select-all" @click="toggleAllTypes">
                {{ allTypesSelected ? '取消全选' : '全选' }}
              </button>
            </div>
            <div class="record-export-types">
              <label
                v-for="option in normalizedTypeOptions"
                :key="option.value"
                :class="{ 'is-active': selectedTypes.includes(option.value) }"
              >
                <input v-model="selectedTypes" type="checkbox" :value="option.value" class="sr-only" />
                <span class="record-export-check" aria-hidden="true">
                  <i class="fa-solid fa-check"></i>
                </span>
                <i v-if="option.icon" :class="['fa-solid', option.icon]" aria-hidden="true"></i>
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>

          <div class="record-export-field">
            <label for="record-export-file-name">文件名</label>
            <input
              id="record-export-file-name"
              v-model="fileName"
              type="text"
              class="record-export-input"
              :placeholder="`${dataset}-${dateStamp}`"
              autocomplete="off"
            />
          </div>

          <div class="record-export-field">
            <label>导出目录</label>
            <div class="record-export-folder-row">
              <div class="record-export-folder" :class="{ 'has-value': outputDir }" :title="outputDir || '尚未选择导出目录'">
                {{ outputDir || '尚未选择导出目录' }}
              </div>
              <button
                type="button"
                class="record-export-folder-button"
                title="选择导出目录"
                aria-label="选择导出目录"
                :disabled="pickingDirectory || exporting"
                @click="chooseDirectory"
              >
                <i class="fa-regular fa-folder-open" aria-hidden="true"></i>
              </button>
            </div>
          </div>

          <div v-if="message" class="record-export-message" :class="status">
            <i :class="status === 'success' ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-exclamation'" aria-hidden="true"></i>
            <span>{{ message }}</span>
          </div>
        </div>

        <footer class="record-export-dialog__footer">
          <button type="button" class="record-export-secondary" :disabled="exporting" @click="emit('close')">取消</button>
          <button type="button" class="record-export-primary" :disabled="!canExport" @click="startExport">
            <i :class="exporting ? 'fa-solid fa-arrow-rotate-right fa-spin' : 'fa-solid fa-file-export'" aria-hidden="true"></i>
            <span>{{ exporting ? '正在导出' : '导出' }}</span>
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  open: { type: Boolean, default: false },
  dataset: { type: String, required: true },
  title: { type: String, required: true },
  account: { type: String, default: '' },
  username: { type: String, default: '' },
  subjectName: { type: String, default: '' },
  query: { type: String, default: '' },
  typeOptions: { type: Array, default: () => [] },
  defaultTypes: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'exported'])
const api = useApi()

const formatOptions = [
  { value: 'html', label: 'HTML' },
  { value: 'json', label: 'JSON' },
  { value: 'txt', label: 'TXT' },
  { value: 'excel', label: 'Excel' },
]

const format = ref('html')
const selectedTypes = ref([])
const outputDir = ref('')
const fileName = ref('')
const exporting = ref(false)
const pickingDirectory = ref(false)
const message = ref('')
const status = ref('')

const dateStamp = computed(() => {
  const date = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`
})

const normalizedTypeOptions = computed(() => {
  return (Array.isArray(props.typeOptions) ? props.typeOptions : [])
    .map((option) => ({
      value: String(option?.value || '').trim(),
      label: String(option?.label || option?.value || '').trim(),
      icon: String(option?.icon || '').trim(),
    }))
    .filter((option) => option.value && option.label)
})

const allTypesSelected = computed(() => {
  const values = normalizedTypeOptions.value.map((option) => option.value)
  return values.length > 0 && values.every((value) => selectedTypes.value.includes(value))
})

const canExport = computed(() => {
  if (exporting.value || pickingDirectory.value || !props.account || !outputDir.value) return false
  return !normalizedTypeOptions.value.length || selectedTypes.value.length > 0
})

const resetSelection = () => {
  const available = normalizedTypeOptions.value.map((option) => option.value)
  const preferred = (Array.isArray(props.defaultTypes) ? props.defaultTypes : [])
    .map((value) => String(value || '').trim())
    .filter((value) => available.includes(value))
  selectedTypes.value = preferred.length ? preferred : available
}

const toggleAllTypes = () => {
  selectedTypes.value = allTypesSelected.value
    ? []
    : normalizedTypeOptions.value.map((option) => option.value)
}

const chooseDirectory = async () => {
  if (!process.client) return
  pickingDirectory.value = true
  message.value = ''
  status.value = ''
  try {
    if (window.wechatDesktop?.chooseDirectory) {
      const result = await window.wechatDesktop.chooseDirectory({ title: `选择${props.title}导出目录` })
      if (!result?.canceled && Array.isArray(result?.filePaths) && result.filePaths[0]) {
        outputDir.value = String(result.filePaths[0])
      }
      return
    }
    const result = await api.pickSystemDirectory({
      title: `选择${props.title}导出目录`,
      initial_dir: outputDir.value || '',
    })
    if (result?.path) outputDir.value = String(result.path)
  } catch (error) {
    status.value = 'error'
    message.value = error?.message || '选择导出目录失败'
  } finally {
    pickingDirectory.value = false
  }
}

const startExport = async () => {
  if (!canExport.value) return
  exporting.value = true
  message.value = ''
  status.value = ''
  try {
    const result = await api.exportRecords({
      account: props.account,
      dataset: props.dataset,
      username: props.username,
      subject_name: props.subjectName,
      format: format.value,
      types: selectedTypes.value,
      query: props.query || '',
      output_dir: outputDir.value,
      file_name: fileName.value,
    })
    status.value = 'success'
    message.value = `已导出 ${Number(result?.count || 0)} 条：${String(result?.outputPath || '')}`
    emit('exported', result)
  } catch (error) {
    status.value = 'error'
    message.value = error?.message || '导出失败'
  } finally {
    exporting.value = false
  }
}

watch(() => props.open, (open) => {
  if (!open) return
  format.value = 'html'
  fileName.value = ''
  message.value = ''
  status.value = ''
  resetSelection()
})

watch(normalizedTypeOptions, () => {
  if (props.open) resetSelection()
})
</script>

<style scoped>
.record-export-backdrop {
  position: fixed;
  z-index: 12000;
  inset: 0;
  display: grid;
  place-items: center;
  overflow-y: auto;
  padding: 20px;
  background: rgba(0, 0, 0, 0.38);
}

.record-export-dialog {
  width: min(620px, 100%);
  max-height: min(760px, calc(100vh - 40px));
  overflow: hidden;
  border: 1px solid var(--wx-line, #e5e7eb);
  border-radius: 8px;
  background: var(--wx-panel, #fff);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.2);
}

.record-export-dialog__header,
.record-export-dialog__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--wx-line, #e5e7eb);
}

.record-export-dialog__header h2 { margin: 0; color: var(--wx-text, #111827); font-size: 17px; font-weight: 600; }
.record-export-dialog__body { display: grid; gap: 18px; max-height: calc(100vh - 190px); overflow-y: auto; padding: 18px; }
.record-export-dialog__footer { justify-content: flex-end; border-top: 1px solid var(--wx-line, #e5e7eb); border-bottom: 0; }

.record-export-icon-button,
.record-export-folder-button {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid var(--wx-line, #e5e7eb);
  border-radius: 6px;
  color: var(--wx-text-secondary, #4b5563);
  background: var(--wx-panel, #fff);
  cursor: pointer;
}

.record-export-icon-button:hover,
.record-export-folder-button:hover { color: var(--wx-green-dark, #047857); background: var(--wx-green-soft, #f0fdf4); }
.record-export-field { display: grid; gap: 8px; }
.record-export-field > label,
.record-export-field__label-row label { color: var(--wx-text, #111827); font-size: 13px; font-weight: 500; }
.record-export-field__label-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }

.record-export-segments {
  display: grid;
  height: auto;
  min-height: 38px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--wx-line, #e5e7eb);
  border-radius: 6px;
  background: var(--wx-muted-surface, #f3f4f6);
}

.record-export-segments button {
  min-height: 38px;
  border: 0;
  border-right: 1px solid var(--wx-line, #e5e7eb);
  color: var(--wx-text-secondary, #4b5563);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.record-export-segments button:last-child { border-right: 0; }
.record-export-segments button.is-active { color: #fff; background: var(--wx-green, #07c160); }
.record-export-types { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }

.record-export-types label {
  display: flex;
  min-width: 0;
  height: 36px;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  border: 1px solid var(--wx-line, #e5e7eb);
  border-radius: 6px;
  color: var(--wx-text-secondary, #4b5563);
  background: var(--wx-panel, #fff);
  cursor: pointer;
  font-size: 12px;
}

.record-export-types label.is-active { border-color: #86efac; color: var(--wx-green-dark, #047857); background: var(--wx-green-soft, #f0fdf4); }
.record-export-types label > span:last-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.record-export-check { display: grid; width: 15px; height: 15px; flex: 0 0 auto; place-items: center; border: 1px solid #d1d5db; border-radius: 3px; color: transparent; font-size: 9px; }
.record-export-types label.is-active .record-export-check { border-color: var(--wx-green, #07c160); color: #fff; background: var(--wx-green, #07c160); }
.record-export-select-all { border: 0; color: var(--wx-green-dark, #047857); background: transparent; cursor: pointer; font-size: 12px; }

.record-export-input,
.record-export-folder {
  width: 100%;
  height: 38px;
  min-width: 0;
  padding: 0 11px;
  border: 1px solid var(--wx-line, #e5e7eb);
  border-radius: 6px;
  outline: 0;
  color: var(--wx-text, #111827);
  background: var(--wx-panel, #fff);
  font-size: 12px;
}

.record-export-input:focus { border-color: var(--wx-green, #07c160); box-shadow: 0 0 0 3px rgba(7, 193, 96, 0.12); }
.record-export-folder-row { display: flex; gap: 8px; }
.record-export-folder { display: flex; flex: 1; align-items: center; overflow: hidden; color: var(--wx-text-muted, #6b7280); text-overflow: ellipsis; white-space: nowrap; }
.record-export-folder.has-value { color: var(--wx-text-secondary, #4b5563); background: var(--wx-green-soft, #f0fdf4); }
.record-export-message { display: flex; align-items: flex-start; gap: 8px; padding: 10px 11px; border-radius: 6px; font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }
.record-export-message.success { color: #166534; background: #f0fdf4; }
.record-export-message.error { color: #b91c1c; background: #fef2f2; }

.record-export-primary,
.record-export-secondary {
  display: inline-flex;
  height: 36px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 16px;
  border: 1px solid var(--wx-line, #e5e7eb);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.record-export-secondary { color: var(--wx-text-secondary, #4b5563); background: var(--wx-panel, #fff); }
.record-export-primary { border-color: var(--wx-green, #07c160); color: #fff; background: var(--wx-green, #07c160); }
.record-export-primary:disabled,
.record-export-secondary:disabled,
.record-export-folder-button:disabled { cursor: not-allowed; opacity: 0.55; }

@media (max-width: 560px) {
  .record-export-backdrop { align-items: end; padding: 0; }
  .record-export-dialog { width: 100%; max-height: 92vh; border-radius: 8px 8px 0 0; }
  .record-export-types { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .record-export-segments { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .record-export-segments button { border-bottom: 1px solid var(--wx-line, #e5e7eb); }
  .record-export-segments button:nth-child(2n) { border-right: 0; }
  .record-export-segments button:nth-last-child(-n + 2) { border-bottom: 0; }
  .record-export-dialog__body { max-height: calc(92vh - 132px); }
}
</style>
