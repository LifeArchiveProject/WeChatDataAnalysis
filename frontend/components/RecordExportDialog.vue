<template>
  <Teleport to="body">
    <div v-if="open" class="app-export-backdrop" role="presentation" @keydown.esc="requestClose">
      <div class="app-export-backdrop__hit-area" aria-hidden="true" @mousedown="requestClose"></div>
      <section
        class="app-export-modal app-export-modal--compact record-export-dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="recordExportTitleId"
        @mousedown.stop
      >
        <header class="app-export-header">
          <div class="app-export-header__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v11" />
              <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
              <path d="M4 19h16" />
            </svg>
          </div>
          <div class="app-export-header__copy">
            <h2 :id="recordExportTitleId">导出{{ title }}</h2>
            <p>选择导出格式、内容类型和保存位置</p>
          </div>
          <button type="button" class="app-export-icon-button" title="关闭" aria-label="关闭导出面板" :disabled="exporting" @click="requestClose">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </header>

        <div class="app-export-workspace">
          <main class="app-export-settings app-export-settings--single">
            <section class="app-export-panel" aria-labelledby="record-export-format-title">
              <header class="app-export-panel__header">
                <div>
                  <h3 id="record-export-format-title">格式与内容</h3>
                  <p>选择结果格式，以及需要包含的记录类型。</p>
                </div>
                <span class="app-export-badge">{{ formatLabel }}</span>
              </header>

              <div class="record-export-segments app-export-format-grid" role="radiogroup" aria-label="导出格式">
                <button
                  v-for="option in formatOptions"
                  :key="option.value"
                  type="button"
                  role="radio"
                  class="app-export-format-option"
                  :aria-checked="format === option.value"
                  :class="{ 'is-active': format === option.value }"
                  @click="format = option.value"
                >
                  <span class="app-export-format-option__code">{{ option.label }}</span>
                  <span class="app-export-format-option__meta">{{ option.meta }}</span>
                  <span class="app-export-radio-check" aria-hidden="true">
                    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                      <path d="m4 10 4 4 8-8" />
                    </svg>
                  </span>
                </button>
              </div>

              <template v-if="normalizedTypeOptions.length">
                <div class="app-export-type-heading">
                  <h4>内容类型</h4>
                  <button type="button" class="app-export-text-button" @click="toggleAllTypes">
                    {{ allTypesSelected ? '取消全选' : '全部选择' }}
                  </button>
                </div>
                <div class="record-export-types app-export-type-grid">
                  <label
                    v-for="option in normalizedTypeOptions"
                    :key="option.value"
                    class="app-export-type-option"
                    :class="{ 'is-active': selectedTypes.includes(option.value) }"
                  >
                    <input v-model="selectedTypes" type="checkbox" :value="option.value" class="sr-only" />
                    <span class="record-export-check app-export-checkbox" aria-hidden="true">
                      <i class="fa-solid fa-check"></i>
                    </span>
                    <i v-if="option.icon" :class="['fa-solid', option.icon]" aria-hidden="true"></i>
                    <span>{{ option.label }}</span>
                  </label>
                </div>
              </template>
            </section>

            <section class="app-export-panel" aria-labelledby="record-export-output-title">
              <header class="app-export-panel__header">
                <div>
                  <h3 id="record-export-output-title">文件与目录</h3>
                  <p>文件名可留空，保存目录为必选项。</p>
                </div>
                <span class="app-export-badge" :class="{ 'app-export-badge--warning': !outputDir }">
                  {{ outputDir ? '位置已设置' : '需要目录' }}
                </span>
              </header>

              <div class="app-export-field">
                <div class="app-export-field__label">
                  <label for="record-export-file-name">文件名</label>
                  <span>可选，留空时自动生成</span>
                </div>
                <input
                  id="record-export-file-name"
                  v-model="fileName"
                  type="text"
                  class="record-export-input app-export-input"
                  :placeholder="`${dataset}-${dateStamp}`"
                  autocomplete="off"
                />
              </div>

              <div class="app-export-field">
                <div class="app-export-field__label">
                  <h4>保存目录</h4>
                  <span class="app-export-required">必选</span>
                </div>
                <div class="app-export-destination" :class="{ 'has-value': outputDir }">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M3 7.5h7l2-2h9v13H3z" />
                  </svg>
                  <div class="app-export-destination__copy">
                    <strong :title="outputDir || '尚未选择导出目录'">{{ outputDir || '尚未选择导出目录' }}</strong>
                    <small>{{ outputDir ? '导出完成后会写入此目录' : '开始导出前需要先完成此项' }}</small>
                  </div>
                  <button
                    type="button"
                    class="app-export-secondary-button"
                    :disabled="pickingDirectory || exporting"
                    @click="chooseDirectory"
                  >
                    <i class="fa-regular fa-folder-open" aria-hidden="true"></i>
                    {{ outputDir ? '更改' : '选择目录' }}
                  </button>
                  <button
                    v-if="outputDir"
                    type="button"
                    class="app-export-icon-button app-export-icon-button--danger"
                    title="清空目录"
                    aria-label="清空导出目录"
                    :disabled="exporting"
                    @click="outputDir = ''"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" />
                    </svg>
                  </button>
                </div>
              </div>

              <div v-if="message" class="app-export-result" :class="status === 'success' ? 'app-export-result--success' : 'app-export-result--error'">
                <svg v-if="status === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" />
                  <path d="m8 12 2.5 2.5L16 9" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v6M12 17h.01" />
                </svg>
                <ErrorNotice v-if="status === 'error'" :message="message" compact />
                <span v-else role="status">{{ message }}</span>
              </div>
            </section>
          </main>
        </div>

        <footer class="app-export-footer">
          <div class="app-export-summary">
            <span>格式 <strong>{{ formatLabel }}</strong></span>
            <span v-if="normalizedTypeOptions.length" class="app-export-summary__separator"></span>
            <span v-if="normalizedTypeOptions.length">内容 <strong>{{ selectedTypes.length }} 类</strong></span>
            <span class="app-export-summary__separator"></span>
            <span class="app-export-summary__path" :class="{ 'is-missing': !outputDir }">{{ outputDir || '尚未选择目录' }}</span>
          </div>
          <div class="app-export-footer__actions">
            <button type="button" class="app-export-secondary-button" :disabled="exporting" @click="requestClose">取消</button>
            <button type="button" class="app-export-primary-button" :disabled="!canExport" @click="startExport">
            <i :class="exporting ? 'fa-solid fa-arrow-rotate-right fa-spin' : 'fa-solid fa-file-export'" aria-hidden="true"></i>
              <span>{{ exporting ? '正在导出' : '开始导出' }}</span>
            </button>
          </div>
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
  { value: 'html', label: 'HTML', meta: '可阅读网页' },
  { value: 'json', label: 'JSON', meta: '结构化数据' },
  { value: 'txt', label: 'TXT', meta: '纯文本记录' },
  { value: 'excel', label: 'Excel', meta: '表格工作簿' },
]

const format = ref('html')
const selectedTypes = ref([])
const outputDir = ref('')
const fileName = ref('')
const exporting = ref(false)
const pickingDirectory = ref(false)
const message = ref('')
const status = ref('')

const recordExportTitleId = computed(() => `record-export-title-${String(props.dataset || 'records').replace(/[^a-z0-9_-]/gi, '-')}`)
const formatLabel = computed(() => formatOptions.find((option) => option.value === format.value)?.label || 'HTML')

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

const requestClose = () => {
  if (!exporting.value) emit('close')
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
.record-export-dialog {
  height: auto;
}

.record-export-segments {
  height: auto;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.record-export-types label > span:last-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

@media (max-width: 560px) {
  .record-export-types { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .record-export-segments { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
