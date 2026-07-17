<template>
  <div v-if="open" class="app-export-backdrop">
    <div class="app-export-backdrop__hit-area" aria-hidden="true" @click="requestClose"></div>

    <section class="app-export-modal app-export-modal--medium" role="dialog" aria-modal="true" aria-labelledby="account-export-title">
      <header class="app-export-header">
        <div class="app-export-header__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3v11" />
            <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
            <path d="M4 19h16" />
          </svg>
        </div>

        <div class="app-export-header__copy">
          <div class="app-export-header__title-row">
            <h2 id="account-export-title">导出账号归档</h2>
            <span class="app-export-badge">ZIP 归档</span>
          </div>
          <p>打包已解密数据库与本地资源，用于备份、迁移或后续分析</p>
        </div>

        <button
          type="button"
          class="app-export-icon-button"
          :disabled="running"
          title="关闭"
          aria-label="关闭导出面板"
          @click="requestClose"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </header>

      <div v-if="!selectedAccount" class="app-export-alert app-export-alert--warning" role="status">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v6M12 17h.01" />
        </svg>
        <span>当前未选择账号，请先导入或切换到一个已解密账号后再导出。</span>
      </div>
      <div v-if="globalError" class="app-export-alert app-export-alert--error">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v6M12 17h.01" />
        </svg>
        <ErrorNotice :message="globalError" compact />
      </div>
      <div v-if="globalMessage" class="app-export-alert app-export-alert--success" role="status">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="m8 12 2.5 2.5L16 9" />
        </svg>
        <span>{{ globalMessage }}</span>
      </div>

      <div class="app-export-workspace">
        <main class="app-export-settings app-export-settings--single">
          <section class="app-export-panel" aria-labelledby="account-export-content-title">
            <header class="app-export-panel__header">
              <div>
                <h3 id="account-export-content-title">归档内容</h3>
                <p>勾选要包含在 ZIP 归档中的本地数据。</p>
              </div>
              <span class="app-export-badge" :class="{ 'app-export-badge--warning': !hasSelectedContent }">{{ contentSummary }}</span>
            </header>

            <div class="app-export-choice-grid">
              <label
                class="app-export-choice"
                :class="{ 'is-active': includeDatabases }"
              >
                <input v-model="includeDatabases" type="checkbox" class="sr-only" />
                <span class="app-export-choice__icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <ellipse cx="12" cy="5" rx="8" ry="3" />
                    <path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
                    <path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
                  </svg>
                </span>
                <span class="app-export-choice__copy">
                  <strong>数据库</strong>
                  <p>包含 .db / .sqlite 数据库和必要的账号元信息。</p>
                </span>
                <span class="app-export-radio-check" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 10 4 4 8-8" /></svg>
                </span>
              </label>

              <label
                class="app-export-choice"
                :class="{ 'is-active': includeResources }"
              >
                <input v-model="includeResources" type="checkbox" class="sr-only" />
                <span class="app-export-choice__icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
                    <path d="M3.3 7L12 12l8.7-5" />
                    <path d="M12 22V12" />
                  </svg>
                </span>
                <span class="app-export-choice__copy">
                  <strong>资源文件</strong>
                  <p>包含 resource、sns_resource 和朋友圈媒体缓存。</p>
                </span>
                <span class="app-export-radio-check" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 10 4 4 8-8" /></svg>
                </span>
              </label>
            </div>
          </section>

          <section class="app-export-panel" aria-labelledby="account-export-output-title">
            <header class="app-export-panel__header">
              <div>
                <h3 id="account-export-output-title">保存位置</h3>
                <p>选择 ZIP 文件的保存目录。</p>
              </div>
              <span class="app-export-badge" :class="{ 'app-export-badge--warning': !hasExportTarget }">{{ hasExportTarget ? '位置已设置' : '需要目录' }}</span>
            </header>

            <div class="app-export-destination" :class="{ 'has-value': hasExportTarget }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 7.5h7l2-2h9v13H3z" />
              </svg>
              <div class="app-export-destination__copy">
                <strong :title="exportFolder || '尚未选择导出目录'">{{ exportFolder || '尚未选择导出目录' }}</strong>
                <small>{{ hasExportTarget ? '归档完成后会写入此目录' : '开始导出前需要先完成此项' }}</small>
              </div>
              <button type="button" class="app-export-secondary-button" :disabled="running" @click="chooseExportFolder">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M3 7a2 2 0 012-2h5l2 2h7a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
                  <path d="M12 11v5M9.5 13.5h5" />
                </svg>
                {{ hasExportTarget ? '更改' : '选择目录' }}
              </button>
              <button v-if="hasExportTarget" type="button" class="app-export-icon-button app-export-icon-button--danger" :disabled="running" title="清空目录" aria-label="清空导出目录" @click="clearExportFolderSelection">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" />
                </svg>
              </button>
            </div>
          </section>

          <section v-if="task" class="app-export-panel" aria-labelledby="account-export-task-title">
            <header class="app-export-panel__header">
              <div>
                <h3 id="account-export-task-title">{{ task.label }}</h3>
                <p v-if="task.message">{{ task.message }}</p>
              </div>
              <span class="app-export-status" :data-status="task.status">{{ statusLabel(task.status) }}</span>
            </header>

            <div class="app-export-progress-block">
              <div class="app-export-progress-heading">
                <span>{{ taskProgressLabel }}</span>
                <strong>{{ taskProgress }}%</strong>
              </div>
              <div class="app-export-progress" role="progressbar" aria-label="账号归档进度" :aria-valuenow="taskProgress" aria-valuemin="0" aria-valuemax="100">
                <span :style="{ transform: `scaleX(${taskProgress / 100})` }"></span>
              </div>
              <p v-if="task.detail" class="app-export-progress-note">{{ task.detail }}</p>
            </div>

            <div v-if="task.outputPath" class="app-export-result app-export-result--success">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <path d="m8 12 2.5 2.5L16 9" />
              </svg>
              <span>{{ task.outputPath }}</span>
            </div>
            <div v-if="task.error" class="app-export-result app-export-result--error">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v6M12 17h.01" />
              </svg>
              <ErrorNotice :message="task.error" compact />
            </div>
          </section>
        </main>
      </div>

      <footer class="app-export-footer">
        <div class="app-export-summary">
          <span>账号 <strong>{{ selectedAccount || '未选择' }}</strong></span>
          <span class="app-export-summary__separator"></span>
          <span>内容 <strong>{{ contentSummary }}</strong></span>
          <span class="app-export-summary__separator"></span>
          <span class="app-export-summary__path" :class="{ 'is-missing': !hasExportTarget }">{{ exportFolder || '尚未选择目录' }}</span>
        </div>
        <div class="app-export-footer__actions">
          <button
            type="button"
            :class="running ? 'app-export-danger-button' : 'app-export-primary-button'"
            :disabled="running ? cancelRequested : !canStartExport"
            @click="running ? cancelExport() : startExport()"
          >
            <svg v-if="running && cancelRequested" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            {{ running ? (cancelRequested ? '正在取消...' : '取消导出') : '开始导出' }}
          </button>
        </div>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'

const props = defineProps({
  open: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

const api = useApi()
const apiBase = useApiBase()
const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const running = ref(false)
const globalError = ref('')
const globalMessage = ref('')
const exportFolder = ref('')
const exportFolderHandle = ref(null)
const includeDatabases = ref(true)
const includeResources = ref(true)
const task = ref(null)
const currentExportId = ref('')
const cancelRequested = ref(false)
const cancelSent = ref(false)

const isDesktopExportRuntime = () => {
  return !!(process.client && typeof window !== 'undefined' && window?.wechatDesktop?.chooseDirectory)
}

const isWebDirectoryPickerSupported = () => {
  return !!(process.client && typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function')
}

const hasExportTarget = computed(() => {
  return isDesktopExportRuntime()
    ? !!String(exportFolder.value || '').trim()
    : !!exportFolderHandle.value
})

const hasSelectedContent = computed(() => !!includeDatabases.value || !!includeResources.value)

const contentSummary = computed(() => {
  if (includeDatabases.value && includeResources.value) return '数据库 + 资源文件'
  if (includeDatabases.value) return '仅数据库'
  if (includeResources.value) return '仅资源文件'
  return '未选择内容'
})

const canStartExport = computed(() => {
  if (running.value) return false
  if (!selectedAccount.value) return false
  if (!hasExportTarget.value) return false
  return hasSelectedContent.value
})

const taskProgress = computed(() => {
  const value = Number(task.value?.progress || 0)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
})

const taskProgressLabel = computed(() => {
  if (task.value?.status === 'done') return '\u5bfc\u51fa\u8fdb\u5ea6'
  if (task.value?.status === 'cancelled') return '\u5df2\u53d6\u6d88'
  if (task.value?.status === 'error') return '\u5bfc\u51fa\u5931\u8d25'
  if (cancelRequested.value) return '\u6b63\u5728\u53d6\u6d88'
  const processed = Number(task.value?.processedBytes || 0)
  const total = Number(task.value?.totalBytes || 0)
  if (total > 0) return `\u5bfc\u51fa\u8fdb\u5ea6\uff1a${formatBytes(processed)} / ${formatBytes(total)}`
  return '\u5bfc\u51fa\u8fdb\u5ea6'
})

const progressBarClass = computed(() => {
  if (task.value?.status === 'error') return 'bg-[#ef4444]'
  if (task.value?.status === 'cancelled') return 'bg-[#9ca3af]'
  return 'bg-[#07C160]'
})

const statusLabel = (status) => {
  if (status === 'running') return '导出中'
  if (status === 'done') return '已完成'
  if (status === 'error') return '失败'
  if (status === 'cancelled') return '已取消'
  return '等待中'
}

const statusClass = (status) => {
  if (status === 'running') return 'bg-blue-100 text-blue-700'
  if (status === 'done') return 'bg-emerald-100 text-emerald-700'
  if (status === 'error') return 'bg-red-100 text-red-700'
  if (status === 'cancelled') return 'bg-gray-100 text-gray-600'
  return 'bg-gray-100 text-gray-600'
}

const formatBytes = (value) => {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const digits = size >= 100 || index === 0 ? 0 : size >= 10 ? 1 : 2
  return `${size.toFixed(digits)} ${units[index]}`
}

const buildExportTimestamp = () => {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

const sanitizeFileNamePart = (value, fallback = 'export') => {
  const cleaned = String(value || '')
    .trim()
    .replace(/[^0-9A-Za-z._-]+/g, '_')
    .replace(/^[._-]+|[._-]+$/g, '')
  return cleaned || fallback
}

const buildBrowserOutputLabel = (fileName) => {
  const folderLabel = String(exportFolder.value || '浏览器目录').trim()
  return `${folderLabel}/${fileName}`
}

const saveResponseToBrowserFolder = async ({ response, fileName }) => {
  if (!exportFolderHandle.value || typeof exportFolderHandle.value.getFileHandle !== 'function') {
    throw new Error('请先选择浏览器导出目录。')
  }

  const safeName = sanitizeFileNamePart(fileName, 'wechat_archive.zip')
  const fileHandle = await exportFolderHandle.value.getFileHandle(safeName, { create: true })
  const writable = await fileHandle.createWritable()

  const totalBytes = Number(response.headers.get('Content-Length') || 0)
  let writtenBytes = 0

  if (response.body && typeof response.body.getReader === 'function') {
    const reader = response.body.getReader()
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        if (!value || !value.byteLength) continue
        await writable.write(value)
        writtenBytes += value.byteLength
        if (task.value) {
          task.value.detail = totalBytes > 0
            ? `正在保存到浏览器目录：${formatBytes(writtenBytes)} / ${formatBytes(totalBytes)}`
            : `正在保存到浏览器目录：${formatBytes(writtenBytes)}`
        }
      }
      await writable.close()
    } catch (error) {
      try { await reader.cancel() } catch {}
      try { await writable.abort() } catch {}
      throw error
    }
  } else {
    const blob = await response.blob()
    writtenBytes = Number(blob.size || 0)
    if (task.value) task.value.detail = `正在保存到浏览器目录：${formatBytes(writtenBytes)}`
    await writable.write(blob)
    await writable.close()
  }

  return buildBrowserOutputLabel(safeName)
}

const chooseExportFolder = async () => {
  globalError.value = ''
  globalMessage.value = ''
  try {
    if (isDesktopExportRuntime()) {
      const result = await window.wechatDesktop.chooseDirectory({ title: '选择导出目录' })
      if (result?.canceled) return
      const selected = Array.isArray(result?.filePaths) ? result.filePaths[0] : ''
      if (selected) {
        exportFolder.value = String(selected || '').trim()
        exportFolderHandle.value = null
      }
      return
    }

    if (!isWebDirectoryPickerSupported()) {
      globalError.value = '当前环境不支持选择导出目录。'
      return
    }

    const handle = await window.showDirectoryPicker({ mode: 'readwrite' })
    exportFolderHandle.value = handle
    exportFolder.value = `浏览器目录：${String(handle.name || '已选择')}`
  } catch (error) {
    if (error?.name === 'AbortError') return
    globalError.value = error?.message || '选择导出目录失败。'
  }
}

const clearExportFolderSelection = () => {
  exportFolder.value = ''
  exportFolderHandle.value = null
}

const validateSelections = () => {
  const errors = []
  if (!selectedAccount.value) errors.push('未选择账号。')
  if (!hasExportTarget.value) errors.push('请先选择导出目录。')
  if (!hasSelectedContent.value) errors.push('请至少选择数据库或资源文件。')
  return errors
}

const translateArchiveMessage = (message) => {
  const text = String(message || '')
  if (!text) return ''
  return text
    .replace('Waiting to start...', '等待开始...')
    .replace('Preparing export...', '正在准备导出...')
    .replace('Scanning export content...', '正在扫描导出内容...')
    .replace('Calculating total archive size.', '\u6b63\u5728\u8ba1\u7b97\u5f52\u6863\u603b\u5927\u5c0f\u3002')
    .replace('Preparing database and resource file list.', '正在准备数据库和资源文件列表。')
    .replace('Scanning resource files...', '正在扫描资源文件...')
    .replace(/Scanned (\d+) resource files\./, '已扫描 $1 个资源文件。')
    .replace('Writing ZIP archive...', '正在写入 ZIP 归档...')
    .replace('Packing account folder directly.', '\u6b63\u5728\u76f4\u63a5\u6253\u5305\u8d26\u53f7\u6587\u4ef6\u5939\u3002')
    .replace(/Ready to pack (\d+) files \(([0-9.]+) MB\)\./, '\u5df2\u8ba1\u7b97\u603b\u5927\u5c0f\uff1a$1 \u4e2a\u6587\u4ef6\uff08$2 MB\uff09\u3002')
    .replace(/Packed (\d+)\/(\d+) files \(([0-9.]+)\/([0-9.]+) MB\)\./, '\u5df2\u6253\u5305 $1/$2 \u4e2a\u6587\u4ef6\uff08$3/$4 MB\uff09\u3002')
    .replace(/Packed (\d+) files \(([0-9.]+) MB\)\./, '\u5df2\u6253\u5305 $1 \u4e2a\u6587\u4ef6\uff08$2 MB\uff09\u3002')
    .replace(/Found (\d+) database files and (\d+) resource files\./, '发现 $1 个数据库文件和 $2 个资源文件。')
    .replace(/Processed (\d+)\/(\d+) files\./, '已处理 $1/$2 个文件。')
    .replace('Finalizing ZIP archive...', '正在完成 ZIP 归档...')
    .replace('Moving archive to target folder.', '正在移动归档到目标目录。')
    .replace('Export completed.', '导出完成。')
    .replace(/Exported (\d+) database files and (\d+) resource files\./, '已导出 $1 个数据库文件和 $2 个资源文件。')
    .replace('Cancelling export...', '正在取消导出...')
    .replace('Waiting for the current file operation to stop.', '正在等待当前文件写入停止。')
    .replace('Export cancelled.', '导出已取消。')
    .replace('Temporary archive has been removed.', '临时归档文件已删除。')
    .replace('Export failed.', '导出失败。')
}

const shouldHideArchiveProgressDetail = (detail) => {
  const text = String(detail || '').trim()
  return /^Ready to pack \d+ files/.test(text) || /^Packed \d+\/\d+ files/.test(text) || /^Packed \d+ files/.test(text)
}

const normalizeArchiveJob = (job = {}) => {
  const rawDetail = String(job.detail || '')
  return {
    label: '\u8d26\u53f7\u5f52\u6863',
    status: String(job.status || 'running'),
    message: job.message ? translateArchiveMessage(job.message) : '\u6b63\u5728\u6253\u5305...',
    detail: rawDetail && !shouldHideArchiveProgressDetail(rawDetail) ? translateArchiveMessage(rawDetail) : '',
    outputPath: String(job.zipPath || ''),
    error: job.error || '',
    progress: Number(job.progress || 0),
    databaseCount: Number(job.databaseCount || 0),
    resourceFileCount: Number(job.resourceFileCount || 0),
    totalBytes: Number(job.totalBytes || 0),
    processedBytes: Number(job.processedBytes || 0),
    fileName: String(job.fileName || '')
  }
}

const waitForArchiveJob = async (exportId) => {
  while (true) {
    const response = await api.getAccountArchiveExport(exportId)
    const job = response?.job || {}
    task.value = normalizeArchiveJob(job)

    if (job.status === 'done' || job.status === 'error' || job.status === 'cancelled') {
      return job
    }

    await new Promise((resolve) => setTimeout(resolve, 600))
  }
}

const cancelExport = async () => {
  if (!currentExportId.value || cancelSent.value) return
  cancelRequested.value = true
  cancelSent.value = true
  if (task.value) {
    task.value.message = '正在取消导出...'
    task.value.detail = '正在等待当前文件写入停止。'
  }
  try {
    await api.cancelAccountArchiveExport(currentExportId.value)
  } catch (error) {
    cancelSent.value = false
    cancelRequested.value = false
    globalError.value = error?.message || '取消导出失败。'
  }
}

const startExport = async () => {
  globalError.value = ''
  globalMessage.value = ''

  const errors = validateSelections()
  if (errors.length > 0) {
    globalError.value = errors.join('\n')
    return
  }

  running.value = true
  currentExportId.value = ''
  cancelRequested.value = false
  cancelSent.value = false
  task.value = {
    label: '账号归档',
    status: 'running',
    message: '正在创建导出任务...',
    detail: '',
    outputPath: '',
    error: '',
    progress: 1
  }

  try {
    const stamp = buildExportTimestamp()
    const fileName = `wechat_archive_${sanitizeFileNamePart(selectedAccount.value, 'account')}_${stamp}.zip`
    const createResponse = await api.createAccountArchiveExport({
      account: selectedAccount.value,
      output_dir: isDesktopExportRuntime() ? String(exportFolder.value || '').trim() : null,
      include_databases: !!includeDatabases.value,
      include_resources: !!includeResources.value,
      file_name: fileName
    })

    const createdJob = createResponse?.job || {}
    currentExportId.value = String(createdJob.exportId || '').trim()
    if (!currentExportId.value) throw new Error('创建导出任务失败。')
    task.value = normalizeArchiveJob(createdJob)

    const finalJob = await waitForArchiveJob(currentExportId.value)
    task.value = normalizeArchiveJob(finalJob)

    if (finalJob.status === 'cancelled') {
      globalMessage.value = '导出已取消。'
      return
    }
    if (finalJob.status === 'error') {
      throw new Error(finalJob.error || '导出失败。')
    }

    const resultFileName = String(finalJob.fileName || fileName).trim()
    task.value.detail = `打包完成：数据库 ${Number(finalJob.databaseCount || 0)} 个，资源文件 ${Number(finalJob.resourceFileCount || 0)} 个，总计 ${formatBytes(finalJob.totalBytes || 0)}。`

    if (isDesktopExportRuntime()) {
      task.value.outputPath = String(finalJob.zipPath || '').trim()
    } else {
      task.value.message = '正在保存到浏览器目录...'
      task.value.progress = 98
      const zipPath = String(finalJob.zipPath || '').trim()
      const query = new URLSearchParams()
      query.set('path', zipPath)
      const downloadUrl = `${apiBase}/account/archive_export/download?${query.toString()}`
      const downloadResponse = await fetch(downloadUrl)
      if (!downloadResponse.ok) {
        throw new Error(`下载导出文件失败（${downloadResponse.status}）。`)
      }
      task.value.outputPath = await saveResponseToBrowserFolder({
        response: downloadResponse,
        fileName: resultFileName
      })
      task.value.progress = 100
    }

    task.value.status = 'done'
    task.value.message = '导出完成。'
    globalMessage.value = '导出完成。'
  } catch (error) {
    if (task.value) {
      task.value.status = 'error'
      task.value.error = error?.message || '导出失败。'
    }
    globalError.value = error?.message || '导出失败。'
  } finally {
    running.value = false
    cancelRequested.value = false
    cancelSent.value = false
  }
}

const requestClose = () => {
  emit('close')
}

const onWindowKeydown = (event) => {
  if (event?.key !== 'Escape') return
  if (!props.open) return
  event.preventDefault()
  if (running.value) {
    cancelExport()
    return
  }
  requestClose()
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    globalError.value = ''
    globalMessage.value = ''
    task.value = null
    await chatAccounts.ensureLoaded()
  }
)

onMounted(() => {
  if (process.client && typeof window !== 'undefined') {
    window.addEventListener('keydown', onWindowKeydown)
  }
})

onBeforeUnmount(() => {
  if (!process.client || typeof window === 'undefined') return
  window.removeEventListener('keydown', onWindowKeydown)
})
</script>
