<template>
  <div class="chat-export-backdrop" @keydown.esc="closeExportModal">
    <div class="chat-export-backdrop__hit-area" aria-hidden="true" @click="closeExportModal"></div>

    <section
      class="chat-export-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="chat-export-title"
    >
      <header class="chat-export-header">
        <div class="chat-export-header__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3v11" />
            <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
            <path d="M4 19h16" />
          </svg>
        </div>
        <div class="chat-export-header__copy">
          <h2 id="chat-export-title">导出聊天记录</h2>
          <p>选择会话范围、导出内容和保存位置</p>
        </div>
        <button
          type="button"
          class="chat-export-icon-button"
          aria-label="关闭导出面板"
          title="关闭"
          @click="closeExportModal"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </header>

      <div v-if="exportError" class="chat-export-alert chat-export-alert--error">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v6M12 17h.01" />
        </svg>
        <ErrorNotice :message="exportError" compact />
      </div>
      <div v-if="privacyMode" class="chat-export-alert chat-export-alert--warning" role="status">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="5" y="10" width="14" height="10" rx="2" />
          <path d="M8 10V7a4 4 0 0 1 8 0v3" />
        </svg>
        <span>隐私模式已开启，导出内容会隐藏身份和消息正文，且不包含头像与媒体。</span>
      </div>

      <div class="chat-export-workspace">

        <main class="chat-export-stage chat-export-stage--single">
          <section
            id="chat-export-panel-scope"
            class="chat-export-panel chat-export-panel--scope"
            aria-labelledby="chat-export-scope-title"
          >
            <header class="chat-export-panel__header">
              <div>
                <h3 id="chat-export-scope-title">会话范围</h3>
                <p>当前会话已默认选中，可按范围筛选或搜索后调整。</p>
              </div>
              <span class="chat-export-count">{{ exportSelectedCount }} 个会话</span>
            </header>

            <div class="chat-export-scope-toolbar">
              <label class="chat-export-search">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m16 16 4 4" />
                </svg>
                <input
                  v-model="exportSearchQuery"
                  type="search"
                  placeholder="搜索名称或 username"
                  aria-label="搜索导出会话"
                  :class="{ 'privacy-blur': privacyMode }"
                />
              </label>
              <select
                v-model="exportListTab"
                class="chat-export-select"
                aria-label="筛选会话范围"
                @change="onExportListScopeChange(exportListTab)"
              >
                <option value="current" :disabled="!selectedContact?.username">当前会话 {{ selectedContact?.username ? exportContactCounts.current : 0 }}</option>
                <option value="all">全部 {{ exportTargetsLoading ? '...' : exportContactCounts.total }}</option>
                <option value="groups">群聊 {{ exportTargetsLoading ? '...' : exportContactCounts.groups }}</option>
                <option value="singles">单聊 {{ exportTargetsLoading ? '...' : exportContactCounts.singles }}</option>
              </select>
              <button
                type="button"
                class="chat-export-secondary-button"
                :disabled="exportFilteredContacts.length === 0"
                @click="toggleExportFilteredContactsSelection"
              >
                {{ areExportFilteredContactsAllSelected ? '取消全选' : '全选结果' }}
              </button>
            </div>

            <div class="chat-export-load-state">
              <span v-if="exportTargetsLoading" role="status">正在加载会话列表...</span>
              <ErrorNotice v-else-if="exportTargetsError" :message="exportTargetsError" compact class="chat-export-load-state--error" />
              <span v-else>共 {{ exportFilteredContacts.length }} 个结果</span>
            </div>

            <div class="chat-export-contact-list" role="listbox" aria-label="可导出的会话" aria-multiselectable="true">
              <button
                v-for="c in exportFilteredContacts"
                :key="c.username"
                type="button"
                class="chat-export-contact"
                :class="{ 'chat-export-contact--selected': isExportContactSelected(c.username) }"
                role="option"
                :aria-selected="isExportContactSelected(c.username)"
                @click="toggleExportContactSelection(c.username)"
              >
                <span class="chat-export-checkbox" :class="{ 'chat-export-checkbox--checked': isExportContactSelected(c.username) }" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="m4 10 4 4 8-8" />
                  </svg>
                </span>
                <span class="chat-export-avatar" :class="{ 'privacy-blur': privacyMode }">
                  <img v-if="c.avatar" :src="c.avatar" :alt="c.name + '头像'" referrerpolicy="no-referrer" @error="onAvatarError($event, c)" />
                  <span v-else>{{ (c.name || c.username || '?').charAt(0) }}</span>
                </span>
                <span class="chat-export-contact__copy" :class="{ 'privacy-blur': privacyMode }">
                  <strong>
                    {{ c.name }}
                    <span v-if="c.isGroup">群聊</span>
                    <span v-if="!c.inSessionList" class="chat-export-contact__supplement">补充</span>
                  </strong>
                  <small>{{ c.username }}</small>
                </span>
              </button>
              <div v-if="exportFilteredContacts.length === 0" class="chat-export-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m16 16 4 4" />
                </svg>
                <strong>没有匹配的会话</strong>
                <span>修改搜索词或切换会话范围。</span>
              </div>
            </div>
          </section>

          <div class="chat-export-settings-column">
          <section
            id="chat-export-panel-content"
            class="chat-export-panel chat-export-panel--content"
            aria-labelledby="chat-export-content-title"
          >
            <header class="chat-export-panel__header">
              <div>
                <h3 id="chat-export-content-title">格式与内容</h3>
                <p>选择结果格式和需要写入归档的消息类型。</p>
              </div>
              <span class="chat-export-count">{{ exportMessageTypeCount }} 类消息</span>
            </header>

            <fieldset class="chat-export-fieldset">
              <legend>文件格式</legend>
              <div class="chat-export-format-grid">
                <label
                  v-for="formatOption in exportFormatOptions"
                  :key="formatOption.value"
                  class="chat-export-format-option"
                  :class="{ 'chat-export-format-option--selected': exportFormat === formatOption.value }"
                >
                  <input v-model="exportFormat" type="radio" :value="formatOption.value" class="sr-only" />
                  <span class="chat-export-format-option__code">{{ formatOption.label }}</span>
                  <span class="chat-export-format-option__meta">{{ formatOption.meta }}</span>
                  <span class="chat-export-format-option__check" aria-hidden="true">
                    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                      <path d="m4 10 4 4 8-8" />
                    </svg>
                  </span>
                </label>
              </div>
            </fieldset>

            <div class="chat-export-message-heading">
              <div>
                <h4>消息类型</h4>
                <p>媒体类型会同时打包可用的本地资源。</p>
              </div>
              <button type="button" class="chat-export-text-button" @click="toggleAllExportMessageTypes">
                {{ areAllExportMessageTypesSelected ? '取消全选' : '全部选择' }}
              </button>
            </div>

            <div class="chat-export-type-grid">
              <label
                v-for="opt in exportMessageTypeOptions"
                :key="opt.value"
                class="chat-export-type-option"
                :class="{ 'chat-export-type-option--selected': exportMessageTypes.includes(opt.value) }"
              >
                <input v-model="exportMessageTypes" type="checkbox" :value="opt.value" class="sr-only" />
                <span class="chat-export-checkbox" :class="{ 'chat-export-checkbox--checked': exportMessageTypes.includes(opt.value) }" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="m4 10 4 4 8-8" />
                  </svg>
                </span>
                <span>{{ opt.label }}</span>
              </label>
            </div>
          </section>

          <section
            id="chat-export-panel-output"
            class="chat-export-panel chat-export-panel--output"
            aria-labelledby="chat-export-output-title"
          >
            <header class="chat-export-panel__header">
              <div>
                <h3 id="chat-export-output-title">时间与文件</h3>
                <p>时间范围和文件名可留空，保存目录为必选项。</p>
              </div>
              <span class="chat-export-count" :class="{ 'chat-export-count--warning': !exportHasFolder }">
                {{ exportHasFolder ? '位置已设置' : '需要目录' }}
              </span>
            </header>

            <div class="chat-export-output-section">
              <div class="chat-export-compact-label">
                <h4>时间范围</h4>
                <span>{{ exportTimeSummary }}</span>
              </div>
              <div class="chat-export-time-grid">
                <label>
                  <span>开始时间</span>
                  <input v-model="exportStartLocal" type="datetime-local" />
                </label>
                <span class="chat-export-time-grid__arrow" aria-hidden="true">至</span>
                <label>
                  <span>结束时间</span>
                  <input v-model="exportEndLocal" type="datetime-local" />
                </label>
              </div>
            </div>

            <div class="chat-export-output-section">
              <div class="chat-export-compact-label">
                <h4>ZIP 文件名</h4>
                <span>可选，留空时自动生成</span>
              </div>
              <input
                v-model="exportFileName"
                class="chat-export-input"
                type="text"
                placeholder="例如：微信聊天记录_2026-07-11.zip"
                aria-label="导出文件名"
              />
            </div>

            <div class="chat-export-output-section chat-export-output-section--destination">
              <div class="chat-export-compact-label">
                <h4>保存目录</h4>
                <span class="chat-export-compact-label__required">必选</span>
              </div>
              <div class="chat-export-destination" :class="{ 'chat-export-destination--selected': exportHasFolder }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M3 7.5h7l2-2h9v13H3z" />
                </svg>
                <div>
                  <strong>{{ exportFolder || '尚未选择保存目录' }}</strong>
                  <small>{{ exportFolder ? '导出完成后会写入此目录' : '开始导出前需要先完成此项' }}</small>
                </div>
                <button type="button" class="chat-export-secondary-button" @click="chooseExportFolder">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                  {{ exportFolder ? '更改' : '选择目录' }}
                </button>
                <button
                  v-if="exportFolder"
                  type="button"
                  class="chat-export-icon-button chat-export-icon-button--danger"
                  aria-label="清空导出目录"
                  title="清空目录"
                  @click="clearExportFolderSelection"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" />
                  </svg>
                </button>
              </div>
            </div>
          </section>

          <section
            v-if="exportJob"
            id="chat-export-panel-task"
            class="chat-export-panel chat-export-panel--task"
            aria-labelledby="chat-export-task-title"
          >
            <header class="chat-export-panel__header">
              <div>
                <h3 id="chat-export-task-title">导出任务</h3>
                <p class="chat-export-task-id">{{ exportJob.exportId }}</p>
              </div>
              <span class="chat-export-task-status" :data-status="exportJob.status">{{ exportJobStatusLabel }}</span>
            </header>

            <div class="chat-export-task-stats">
              <div>
                <span>消息</span>
                <strong>{{ exportJob.progress?.messagesExported || 0 }}</strong>
              </div>
              <div>
                <span>已复制媒体</span>
                <strong>{{ exportJob.progress?.mediaCopied || 0 }}</strong>
              </div>
              <div>
                <span>缺失媒体</span>
                <strong>{{ exportJob.progress?.mediaMissing || 0 }}</strong>
              </div>
            </div>

            <div class="chat-export-progress-block">
              <div class="chat-export-progress-block__heading">
                <span>总体进度</span>
                <strong>{{ exportOverallPercent }}%</strong>
              </div>
              <div class="chat-export-progress" role="progressbar" aria-label="导出总体进度" :aria-valuenow="exportOverallPercent" aria-valuemin="0" aria-valuemax="100">
                <span :style="{ transform: `scaleX(${exportOverallPercent / 100})` }"></span>
              </div>
              <p>已完成 {{ exportJob.progress?.conversationsDone || 0 }} / {{ exportJob.progress?.conversationsTotal || 0 }} 个会话</p>
            </div>

            <div v-if="exportJob.status === 'running' && exportJob.progress?.currentConversationUsername" class="chat-export-progress-block chat-export-progress-block--current">
              <div class="chat-export-progress-block__heading">
                <span class="chat-export-progress-block__current-name">
                  当前：{{ exportJob.progress?.currentConversationName || exportJob.progress?.currentConversationUsername }}
                </span>
                <strong>{{ exportCurrentPercent != null ? `${exportCurrentPercent}%` : '处理中' }}</strong>
              </div>
              <div class="chat-export-progress" role="progressbar" aria-label="当前会话进度" :aria-valuenow="exportCurrentPercent == null ? undefined : exportCurrentPercent" aria-valuemin="0" aria-valuemax="100">
                <span v-if="exportCurrentPercent != null" :style="{ transform: `scaleX(${exportCurrentPercent / 100})` }"></span>
                <span v-else class="chat-export-progress__indeterminate"></span>
              </div>
              <p>{{ exportJob.progress?.currentConversationMessagesExported || 0 }} / {{ exportJob.progress?.currentConversationMessagesTotal || 0 }} 条消息</p>
            </div>

            <div v-if="exportJob.status === 'done'" class="chat-export-result chat-export-result--success">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <path d="m8 12 2.5 2.5L16 9" />
              </svg>
              <div>
                <strong>导出已完成</strong>
                <span>{{ exportBackendZipPath || 'ZIP 文件已生成' }}</span>
                <span v-if="hasWebExportFolder">浏览器目录：{{ exportFolder || '未选择' }}</span>
                <span v-if="exportSaveState === 'saving'" class="chat-export-result__info">{{ exportSaveProgressText }}</span>
                <span v-else-if="exportSaveMsg" class="chat-export-result__success">{{ exportSaveMsg }}</span>
                <ErrorNotice v-else-if="exportSaveError" :message="exportSaveError" compact class="chat-export-result__error" />
              </div>
              <a
                v-if="!hasWebExportFolder"
                class="chat-export-primary-button chat-export-primary-button--compact"
                :href="getExportDownloadUrl(exportJob.exportId)"
                target="_blank"
              >
                下载 ZIP
              </a>
            </div>

            <div v-if="exportJob.status === 'error'" class="chat-export-result chat-export-result--error">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v6M12 17h.01" />
              </svg>
              <div>
                <strong>导出失败</strong>
                <ErrorNotice :message="exportJob.error || '任务未能完成'" compact />
              </div>
            </div>
          </section>
          </div>
        </main>
      </div>

      <footer class="chat-export-footer">
        <div class="chat-export-summary" aria-live="polite">
          <span><strong>{{ exportSelectedCount }}</strong> 个会话</span>
          <span class="chat-export-summary__separator" aria-hidden="true"></span>
          <span><strong>{{ exportFormatLabel }}</strong> · {{ exportMessageTypeCount }} 类消息</span>
          <span class="chat-export-summary__separator" aria-hidden="true"></span>
          <button
            type="button"
            class="chat-export-summary__destination"
            :class="{ 'chat-export-summary__destination--missing': !exportHasFolder }"
            @click="chooseExportFolder"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path d="M3 7.5h7l2-2h9v13H3z" />
            </svg>
            {{ exportFolder || '未选择保存目录' }}
          </button>
        </div>
        <div class="chat-export-footer__actions">
          <button type="button" class="chat-export-secondary-button" @click="closeExportModal">关闭</button>
          <button
            v-if="!(exportJob && (exportJob.status === 'queued' || exportJob.status === 'running'))"
            type="button"
            class="chat-export-primary-button"
            :disabled="isExportCreating"
            @click="startChatExportFromPanel"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 3v11" />
              <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
              <path d="M4 19h16" />
            </svg>
            {{ isExportCreating ? '正在创建' : '开始导出' }}
          </button>
          <button
            v-else
            type="button"
            class="chat-export-danger-button"
            :disabled="exportCancelRequested"
            @click="cancelCurrentExport"
          >
            {{ exportCancelRequested ? '正在取消' : '取消任务' }}
          </button>
        </div>
      </footer>
    </section>
  </div>
</template>

<script>
import { computed, defineComponent } from 'vue'

const readMaybeRef = (value) => {
  if (value && typeof value === 'object' && 'value' in value) return value.value
  return value
}

const FORMAT_OPTIONS = [
  { value: 'html', label: 'HTML', meta: '可浏览归档' },
  { value: 'json', label: 'JSON', meta: '结构化数据' },
  { value: 'txt', label: 'TXT', meta: '纯文本记录' },
  { value: 'excel', label: 'Excel', meta: '表格工作簿' },
]

const JOB_STATUS_LABELS = {
  queued: '等待开始',
  running: '正在导出',
  done: '已完成',
  error: '失败',
  cancelled: '已取消',
}

export default defineComponent({
  name: 'ChatExportDialog',
  props: {
    state: { type: Object, required: true },
  },
  setup(props) {
    const stateValue = (key) => readMaybeRef(props.state[key])
    const exportSelectedCount = computed(() => {
      const selected = stateValue('exportSelectedUsernames')
      return Array.isArray(selected) ? selected.length : 0
    })
    const exportMessageTypeCount = computed(() => {
      const selected = stateValue('exportMessageTypes')
      return Array.isArray(selected) ? selected.length : 0
    })
    const exportFormatLabel = computed(() => {
      const value = String(stateValue('exportFormat') || 'html').toLowerCase()
      return FORMAT_OPTIONS.find((option) => option.value === value)?.label || value.toUpperCase()
    })
    const exportHasFolder = computed(() => Boolean(String(stateValue('exportFolder') || '').trim()))
    const exportTimeSummary = computed(() => {
      const start = String(stateValue('exportStartLocal') || '').trim()
      const end = String(stateValue('exportEndLocal') || '').trim()
      if (!start && !end) return '全部时间'
      if (start && end) return '仅导出所选时间段'
      return start ? '从开始时间至今' : '截止到结束时间'
    })
    const exportJobStatusLabel = computed(() => {
      const status = String(stateValue('exportJob')?.status || '').toLowerCase()
      return JOB_STATUS_LABELS[status] || status || '任务详情'
    })

    const startChatExportFromPanel = async () => {
      if (typeof props.state.startChatExport === 'function') {
        await props.state.startChatExport()
      }
    }

    return {
      ...props.state,
      exportFormatOptions: FORMAT_OPTIONS,
      exportSelectedCount,
      exportMessageTypeCount,
      exportFormatLabel,
      exportHasFolder,
      exportTimeSummary,
      exportJobStatusLabel,
      startChatExportFromPanel,
    }
  },
})
</script>

<style scoped>
.chat-export-backdrop {
  position: fixed;
  inset: 0;
  z-index: 11000;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(25, 25, 25, 0.48);
  backdrop-filter: blur(2px);
}

.chat-export-backdrop__hit-area {
  position: absolute;
  inset: 0;
}

.chat-export-modal {
  --export-accent-soft: #edf9f2;
  --export-accent-border: #bce7cc;
  --export-accent-text: #087a41;
  --export-warning-soft: #fff8e8;
  --export-warning-border: #f2d79a;
  --export-warning-text: #8a5a00;
  --export-danger-soft: #fff2f1;
  --export-danger-border: #f1c0bc;
  --export-danger-text: #b42318;
  position: relative;
  display: flex;
  width: min(1180px, calc(100vw - 32px));
  height: min(760px, calc(100dvh - 32px));
  min-height: min(620px, calc(100dvh - 32px));
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface-bg);
  color: var(--app-text-primary);
  box-shadow: 0 28px 70px rgba(25, 25, 25, 0.26);
  letter-spacing: 0;
}

.chat-export-modal :is(button, input, select, a):focus-visible {
  outline: 2px solid var(--app-accent);
  outline-offset: 2px;
}

.chat-export-header {
  display: flex;
  min-height: 64px;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface-bg);
}

.chat-export-header__icon {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: var(--app-accent);
}

.chat-export-header__icon {
  width: 40px;
  height: 40px;
  border: 1px solid var(--export-accent-border);
  border-radius: 7px;
  background: var(--export-accent-soft);
}

.chat-export-header__icon svg {
  width: 21px;
  height: 21px;
}

.chat-export-header__copy {
  min-width: 0;
  flex: 1;
}

.chat-export-header h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  line-height: 1.35;
}

.chat-export-header p {
  margin: 3px 0 0;
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.chat-export-icon-button {
  display: inline-grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--app-text-muted);
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.chat-export-icon-button:hover {
  background: var(--app-neutral-btn-hover);
  color: var(--app-text-primary);
}

.chat-export-icon-button:active,
.chat-export-secondary-button:active,
.chat-export-primary-button:active,
.chat-export-danger-button:active {
  transform: translateY(1px);
}

.chat-export-icon-button svg {
  width: 17px;
  height: 17px;
}

.chat-export-icon-button--danger:hover {
  background: var(--export-danger-soft);
  color: var(--export-danger-text);
}

.chat-export-alert {
  display: flex;
  min-height: 40px;
  flex: 0 0 auto;
  align-items: center;
  gap: 9px;
  padding: 9px 20px;
  border-bottom: 1px solid;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.chat-export-alert svg {
  width: 17px;
  height: 17px;
  flex: 0 0 auto;
}

.chat-export-alert--error {
  border-color: var(--export-danger-border);
  background: var(--export-danger-soft);
  color: var(--export-danger-text);
}

.chat-export-alert--warning {
  border-color: var(--export-warning-border);
  background: var(--export-warning-soft);
  color: var(--export-warning-text);
}

.chat-export-workspace {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
}


.chat-export-stage {
  display: grid;
  width: 100%;
  min-width: 0;
  min-height: 0;
  grid-template-columns: minmax(400px, 0.78fr) minmax(600px, 1.22fr);
  overflow: hidden;
  padding: 0;
  background: var(--app-surface-bg);
}

.chat-export-panel {
  width: 100%;
  max-width: none;
  margin: 0;
}

.chat-export-panel--scope {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  padding: 18px 20px 20px;
}

.chat-export-settings-column {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  border-left: 1px solid var(--app-border);
  background: var(--app-surface-soft);
  scrollbar-color: var(--scrollbar-thumb) transparent;
  scrollbar-width: thin;
}

.chat-export-settings-column > .chat-export-panel {
  padding: 10px 16px;
  border-bottom: 1px solid var(--app-border);
}

.chat-export-settings-column > .chat-export-panel:last-child {
  border-bottom: 0;
}

.chat-export-panel--content {
  display: block;
}

.chat-export-panel--content .chat-export-format-option__meta {
  display: none;
}

.chat-export-settings-column .chat-export-panel__header {
  min-height: 24px;
  margin-bottom: 6px;
}

.chat-export-settings-column .chat-export-panel__header p {
  display: none;
}

.chat-export-panel__header {
  display: flex;
  min-height: 36px;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 8px;
}

.chat-export-panel h3,
.chat-export-panel h4,
.chat-export-panel p {
  margin: 0;
}

.chat-export-panel h3 {
  color: var(--app-text-primary);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.4;
}

.chat-export-panel__header p {
  margin-top: 2px;
  color: var(--app-text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.chat-export-count,
.chat-export-task-status {
  display: inline-flex;
  min-height: 27px;
  flex: 0 0 auto;
  align-items: center;
  padding: 4px 9px;
  border: 1px solid var(--export-accent-border);
  border-radius: 5px;
  background: var(--export-accent-soft);
  color: var(--export-accent-text);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.chat-export-count--warning,
.chat-export-task-status[data-status='error'] {
  border-color: var(--export-warning-border);
  background: var(--export-warning-soft);
  color: var(--export-warning-text);
}

.chat-export-scope-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px 88px;
  gap: 8px;
}

.chat-export-scope-toolbar > .chat-export-secondary-button {
  min-width: 88px;
  white-space: nowrap;
}

.chat-export-search {
  position: relative;
  display: flex;
  min-width: 0;
  align-items: center;
}

.chat-export-search svg {
  position: absolute;
  left: 12px;
  width: 16px;
  height: 16px;
  color: var(--app-text-muted);
  pointer-events: none;
}

.chat-export-search input,
.chat-export-input,
.chat-export-select,
.chat-export-time-grid input {
  box-sizing: border-box;
  border: 1px solid var(--app-input-border);
  border-radius: 6px;
  background: var(--app-input-bg);
  color: var(--app-text-primary);
  font-size: 13px;
  transition: border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease;
}

.chat-export-search input:hover,
.chat-export-input:hover,
.chat-export-select:hover,
.chat-export-time-grid input:hover {
  border-color: color-mix(in srgb, var(--app-input-border) 55%, var(--app-text-muted));
}

.chat-export-search input:focus,
.chat-export-input:focus,
.chat-export-select:focus,
.chat-export-time-grid input:focus {
  border-color: var(--app-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--app-accent) 15%, transparent);
  outline: none;
}

.chat-export-search input {
  width: 100%;
  height: 38px;
  padding: 0 12px 0 36px;
}

.chat-export-search input::placeholder,
.chat-export-input::placeholder {
  color: var(--app-text-muted);
}

.chat-export-select {
  width: 100%;
  height: 38px;
  padding: 0 10px;
}

.chat-export-secondary-button,
.chat-export-primary-button,
.chat-export-danger-button {
  display: inline-flex;
  min-height: 38px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 8px 13px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  cursor: pointer;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, transform 160ms ease, opacity 160ms ease;
}

.chat-export-secondary-button {
  border: 1px solid var(--app-border);
  background: var(--app-neutral-btn-bg);
  color: var(--app-text-secondary);
}

.chat-export-secondary-button:hover:not(:disabled) {
  background: var(--app-neutral-btn-hover);
  color: var(--app-text-primary);
}

.chat-export-secondary-button svg,
.chat-export-primary-button svg {
  width: 16px;
  height: 16px;
}

.chat-export-secondary-button:disabled,
.chat-export-primary-button:disabled,
.chat-export-danger-button:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.chat-export-primary-button {
  border: 1px solid var(--app-accent);
  background: var(--app-accent);
  color: #fff;
  text-decoration: none;
}

.chat-export-primary-button:hover:not(:disabled) {
  border-color: var(--app-accent-hover);
  background: var(--app-accent-hover);
}

.chat-export-primary-button--compact {
  min-height: 34px;
  padding: 7px 11px;
  font-size: 12px;
}

.chat-export-danger-button {
  border: 1px solid var(--export-danger-border);
  background: var(--app-neutral-btn-bg);
  color: var(--export-danger-text);
}

.chat-export-danger-button:hover:not(:disabled) {
  background: var(--export-danger-soft);
}

.chat-export-load-state {
  min-height: 28px;
  padding: 8px 1px 6px;
  color: var(--app-text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.chat-export-load-state--error {
  color: var(--export-danger-text);
}

.chat-export-contact-list {
  min-height: 260px;
  flex: 1 1 auto;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: 7px;
  background: var(--app-surface-bg);
  scrollbar-color: var(--scrollbar-thumb) transparent;
  scrollbar-width: thin;
}

.chat-export-contact {
  display: flex;
  width: 100%;
  min-height: 58px;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 0;
  border-bottom: 1px solid var(--app-border-subtle);
  background: transparent;
  color: var(--app-text-primary);
  text-align: left;
  cursor: pointer;
  transition: background-color 150ms ease;
}

.chat-export-contact:last-of-type {
  border-bottom: 0;
}

.chat-export-contact:hover {
  background: var(--app-list-hover);
}

.chat-export-contact--selected,
.chat-export-contact--selected:hover {
  background: var(--export-accent-soft);
}

.chat-export-checkbox {
  display: grid;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid var(--app-input-border);
  border-radius: 4px;
  background: var(--app-input-bg);
  color: transparent;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease;
}

.chat-export-checkbox svg {
  width: 12px;
  height: 12px;
}

.chat-export-checkbox--checked {
  border-color: var(--app-accent);
  background: var(--app-accent);
  color: #fff;
}

.chat-export-avatar {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  overflow: hidden;
  border-radius: 6px;
  background: var(--app-surface-muted);
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.chat-export-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-export-contact__copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.chat-export-contact__copy strong,
.chat-export-contact__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-export-contact__copy strong {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
}

.chat-export-contact__copy strong > span {
  display: inline-block;
  margin-left: 5px;
  color: var(--app-text-muted);
  font-size: 10px;
  font-weight: 500;
}

.chat-export-contact__copy strong > .chat-export-contact__supplement {
  color: var(--export-accent-text);
}

.chat-export-contact__copy small {
  color: var(--app-text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.chat-export-empty {
  display: flex;
  height: 100%;
  min-height: 180px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 28px;
  color: var(--app-text-muted);
  text-align: center;
}

.chat-export-empty svg {
  width: 30px;
  height: 30px;
  margin-bottom: 10px;
  opacity: 0.7;
}

.chat-export-empty strong {
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.chat-export-empty span {
  margin-top: 4px;
  font-size: 11px;
}

.chat-export-fieldset {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.chat-export-fieldset legend,
.chat-export-message-heading h4,
.chat-export-output-section h4 {
  color: var(--app-text-primary);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
}

.chat-export-fieldset legend {
  margin-bottom: 6px;
}

.chat-export-format-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.chat-export-format-option {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 42px;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  padding: 8px 32px 8px 11px;
  border: 1px solid var(--app-border);
  border-radius: 7px;
  background: var(--app-surface-bg);
  cursor: pointer;
  transition: border-color 160ms ease, background-color 160ms ease, transform 160ms ease;
}

.chat-export-format-option:hover {
  background: var(--app-neutral-btn-hover);
}

.chat-export-format-option:active {
  transform: scale(0.99);
}

.chat-export-format-option:focus-within {
  outline: 2px solid var(--app-accent);
  outline-offset: 2px;
}

.chat-export-format-option--selected,
.chat-export-format-option--selected:hover {
  border-color: var(--export-accent-border);
  background: var(--export-accent-soft);
}

.chat-export-format-option__code {
  color: var(--app-text-primary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
}

.chat-export-format-option--selected .chat-export-format-option__code {
  color: var(--export-accent-text);
}

.chat-export-format-option__meta {
  overflow: hidden;
  color: var(--app-text-muted);
  font-size: 10px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-export-format-option__check {
  position: absolute;
  top: 50%;
  right: 10px;
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
  border: 1px solid var(--app-border);
  border-radius: 50%;
  color: transparent;
  transform: translateY(-50%);
}

.chat-export-format-option__check svg {
  width: 12px;
  height: 12px;
}

.chat-export-format-option--selected .chat-export-format-option__check {
  border-color: var(--app-accent);
  background: var(--app-accent);
  color: #fff;
}

.chat-export-panel--content .chat-export-message-heading p {
  display: none;
}

.chat-export-message-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--app-border);
}

.chat-export-message-heading p,
.chat-export-output-section p {
  margin-top: 3px;
  color: var(--app-text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.chat-export-text-button {
  flex: 0 0 auto;
  padding: 3px 0;
  border: 0;
  background: transparent;
  color: var(--export-accent-text);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.chat-export-text-button:hover {
  color: var(--app-accent-hover);
}

.chat-export-type-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 5px;
  margin-top: 8px;
}

.chat-export-type-option {
  display: flex;
  min-width: 0;
  height: 28px;
  align-items: center;
  gap: 6px;
  padding: 0 7px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-surface-bg);
  color: var(--app-text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 150ms ease, background-color 150ms ease, color 150ms ease, transform 150ms ease;
}

.chat-export-type-option:hover {
  background: var(--app-neutral-btn-hover);
}

.chat-export-type-option:active {
  transform: scale(0.99);
}

.chat-export-type-option:focus-within {
  outline: 2px solid var(--app-accent);
  outline-offset: 2px;
}

.chat-export-type-option--selected,
.chat-export-type-option--selected:hover {
  border-color: var(--export-accent-border);
  background: var(--export-accent-soft);
  color: var(--export-accent-text);
}

.chat-export-output-section {
  padding: 8px 0;
  border-top: 1px solid var(--app-border);
}

.chat-export-panel__header + .chat-export-output-section {
  padding-top: 0;
  border-top: 0;
}

.chat-export-compact-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.chat-export-compact-label > span {
  overflow: hidden;
  color: var(--app-text-muted);
  font-size: 10px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-export-compact-label > .chat-export-compact-label__required {
  color: var(--export-warning-text);
  font-weight: 600;
}

.chat-export-time-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 22px minmax(0, 1fr);
  align-items: end;
  gap: 8px;
}

.chat-export-time-grid label {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  color: var(--app-text-secondary);
  font-size: 11px;
}

.chat-export-time-grid input {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding: 0 10px;
}

.chat-export-time-grid__arrow {
  display: flex;
  height: 34px;
  align-items: center;
  justify-content: center;
  color: var(--app-text-muted);
  font-size: 11px;
}

.chat-export-input {
  width: 100%;
  height: 36px;
  padding: 0 12px;
}

.chat-export-output-section--destination {
  padding-bottom: 0;
}

.chat-export-destination {
  display: grid;
  min-height: 56px;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px dashed var(--export-warning-border);
  border-radius: 7px;
  background: var(--export-warning-soft);
  color: var(--export-warning-text);
}

.chat-export-destination--selected {
  grid-template-columns: 28px minmax(0, 1fr) auto 34px;
  border-style: solid;
  border-color: var(--export-accent-border);
  background: var(--export-accent-soft);
  color: var(--export-accent-text);
}

.chat-export-destination > svg {
  width: 20px;
  height: 20px;
  justify-self: center;
}

.chat-export-destination > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.chat-export-destination strong,
.chat-export-destination small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-export-destination strong {
  color: var(--app-text-primary);
  font-size: 12px;
  font-weight: 600;
}

.chat-export-destination small {
  color: var(--app-text-muted);
  font-size: 10px;
}

.chat-export-task-id {
  max-width: 520px;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-export-task-status[data-status='running'],
.chat-export-task-status[data-status='queued'] {
  border-color: var(--export-warning-border);
  background: var(--export-warning-soft);
  color: var(--export-warning-text);
}

.chat-export-task-status[data-status='cancelled'] {
  border-color: var(--app-border);
  background: var(--app-surface-soft);
  color: var(--app-text-secondary);
}

.chat-export-task-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 24px;
  border-top: 1px solid var(--app-border);
  border-bottom: 1px solid var(--app-border);
}

.chat-export-task-stats > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  padding: 15px 16px;
  border-right: 1px solid var(--app-border);
}

.chat-export-task-stats > div:last-child {
  border-right: 0;
}

.chat-export-task-stats span {
  color: var(--app-text-muted);
  font-size: 11px;
}

.chat-export-task-stats strong {
  color: var(--app-text-primary);
  font-size: 20px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.chat-export-progress-block {
  margin-top: 18px;
}

.chat-export-progress-block--current {
  padding-top: 18px;
  border-top: 1px solid var(--app-border);
}

.chat-export-progress-block__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.chat-export-progress-block__heading strong {
  color: var(--app-text-primary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.chat-export-progress-block__current-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-export-progress {
  position: relative;
  height: 7px;
  margin-top: 9px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--app-surface-muted);
}

.chat-export-progress > span {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--app-accent);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 260ms ease;
}

.chat-export-progress > .chat-export-progress__indeterminate {
  right: auto;
  width: 32%;
  transform: translateX(-110%);
  animation: chat-export-progress-slide 1.2s ease-in-out infinite;
}

.chat-export-progress-block > p {
  margin-top: 7px;
  color: var(--app-text-muted);
  font-size: 11px;
}

@keyframes chat-export-progress-slide {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(420%); }
}

.chat-export-result {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: start;
  gap: 11px;
  margin-top: 24px;
  padding: 14px;
  border: 1px solid;
  border-radius: 7px;
}

.chat-export-result > svg {
  width: 22px;
  height: 22px;
}

.chat-export-result > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.chat-export-result strong {
  font-size: 13px;
  font-weight: 650;
}

.chat-export-result span {
  overflow-wrap: anywhere;
  color: var(--app-text-secondary);
  font-size: 11px;
  line-height: 1.5;
}

.chat-export-result--success {
  border-color: var(--export-accent-border);
  background: var(--export-accent-soft);
  color: var(--export-accent-text);
}

.chat-export-result--error {
  grid-template-columns: 24px minmax(0, 1fr);
  border-color: var(--export-danger-border);
  background: var(--export-danger-soft);
  color: var(--export-danger-text);
}

.chat-export-result__info {
  color: #14779d !important;
}

.chat-export-result__success {
  color: var(--export-accent-text) !important;
}

.chat-export-result__error {
  color: var(--export-danger-text) !important;
}

.chat-export-footer {
  display: flex;
  min-height: 66px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 12px 18px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface-bg);
}

.chat-export-summary {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
  color: var(--app-text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.chat-export-summary > span {
  flex: 0 0 auto;
}

.chat-export-summary strong {
  color: var(--app-text-primary);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.chat-export-summary__separator {
  width: 1px;
  height: 14px;
  background: var(--app-border);
}

.chat-export-summary__destination {
  display: flex;
  min-width: 0;
  max-width: 240px;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  padding: 3px 4px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--export-accent-text);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.chat-export-summary__destination svg {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
}

.chat-export-summary__destination--missing {
  color: var(--export-warning-text);
}

.chat-export-summary__destination:hover {
  background: var(--app-neutral-btn-hover);
}

.chat-export-footer__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

:global(html[data-theme='dark']) .chat-export-modal {
  --export-accent-soft: rgba(62, 181, 117, 0.14);
  --export-accent-border: rgba(82, 201, 136, 0.34);
  --export-accent-text: #7bd8a2;
  --export-warning-soft: rgba(214, 153, 30, 0.13);
  --export-warning-border: rgba(225, 170, 58, 0.32);
  --export-warning-text: #e9c46c;
  --export-danger-soft: rgba(218, 76, 67, 0.13);
  --export-danger-border: rgba(235, 103, 94, 0.32);
  --export-danger-text: #ff9189;
  box-shadow: 0 28px 70px rgba(0, 0, 0, 0.5);
}

:global(html[data-theme='dark']) .chat-export-modal :is(input, select) {
  color-scheme: dark;
}

@media (max-width: 980px) {
  .chat-export-stage {
    display: block;
    overflow-y: auto;
    scrollbar-color: var(--scrollbar-thumb) transparent;
    scrollbar-width: thin;
  }

  .chat-export-panel--scope {
    min-height: 520px;
  }

  .chat-export-contact-list {
    height: 340px;
    flex: 0 0 auto;
  }

  .chat-export-settings-column {
    overflow: visible;
    border-top: 1px solid var(--app-border);
    border-left: 0;
  }

}

@media (max-width: 760px) {
  .chat-export-backdrop {
    padding: 0;
  }

  .chat-export-modal {
    width: 100vw;
    height: 100dvh;
    min-height: 100dvh;
    border: 0;
    border-radius: 0;
  }

  .chat-export-header {
    min-height: 60px;
    padding: 10px 14px;
  }

  .chat-export-header__icon {
    width: 36px;
    height: 36px;
  }

  .chat-export-header p {
    display: none;
  }

  .chat-export-panel--scope,
  .chat-export-settings-column > .chat-export-panel {
    padding: 16px;
  }

  .chat-export-panel--scope {
    min-height: 500px;
  }

  .chat-export-panel__header {
    margin-bottom: 12px;
  }

  .chat-export-scope-toolbar {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .chat-export-search {
    grid-column: 1 / -1;
  }

  .chat-export-contact-list {
    height: min(340px, calc(100dvh - 300px));
    min-height: 220px;
  }

  .chat-export-format-option__meta {
    display: none;
  }

  .chat-export-format-option {
    min-height: 48px;
  }

  .chat-export-type-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .chat-export-destination,
  .chat-export-destination--selected {
    grid-template-columns: 30px minmax(0, 1fr) auto;
  }

  .chat-export-destination--selected .chat-export-icon-button {
    grid-column: 3;
  }

  .chat-export-destination--selected .chat-export-secondary-button {
    grid-column: 2;
    grid-row: 2;
    justify-self: start;
  }

  .chat-export-footer {
    min-height: 70px;
    padding: 10px 12px;
  }

  .chat-export-summary {
    gap: 7px;
  }

  .chat-export-summary__destination,
  .chat-export-summary__separator:nth-of-type(2) {
    display: none;
  }

  .chat-export-result {
    grid-template-columns: 24px minmax(0, 1fr);
  }

  .chat-export-result .chat-export-primary-button {
    grid-column: 2;
    justify-self: start;
  }
}

@media (max-width: 520px) {
  .chat-export-format-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chat-export-type-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chat-export-time-grid {
    grid-template-columns: 1fr;
  }

  .chat-export-time-grid__arrow {
    display: none;
  }
}

@media (max-width: 430px) {
  .chat-export-count {
    display: none;
  }

  .chat-export-format-option {
    padding-right: 12px;
    text-align: center;
  }

  .chat-export-format-option__check {
    display: none;
  }

  .chat-export-summary > span:nth-of-type(2),
  .chat-export-summary__separator:first-of-type {
    display: none;
  }

  .chat-export-footer__actions .chat-export-secondary-button {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .chat-export-modal *,
  .chat-export-modal *::before,
  .chat-export-modal *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>
