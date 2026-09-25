<template>
  <div class="ai-settings" :inert="dialogStep ? true : undefined">
    <header class="ais-heading">
      <div class="ais-heading-icon"><WandSparkles :size="16" :stroke-width="1.8" aria-hidden="true" /></div>
      <div><h3>AI 服务</h3><p>管理 AI 模型、本地搜索与对话体验。</p></div>
      <span class="ais-local"><Lock :size="16" :stroke-width="1.8" aria-hidden="true" /> {{ activeTab==='local' ? '搜索在本机运行' : '密钥本机保存' }}</span>
    </header>

    <div class="ais-tabs" role="tablist" aria-label="AI 服务页面">
      <button v-for="tab in settingsTabs" :key="tab.id" :id="`ais-${tab.id}-tab`" type="button" role="tab"
        :aria-selected="activeTab === tab.id" :aria-controls="`ais-${tab.id}`" :tabindex="activeTab===tab.id ? 0 : -1"
        @click="activeTab=tab.id" @keydown="navigateTabs($event,tab.id)">
        <component :is="tab.icon" :size="16" :stroke-width="1.8" aria-hidden="true" /><span class="ais-tab-copy"><strong>{{ tab.label }}</strong><small>{{ tab.hint }}</small></span>
      </button>
    </div>
    <LocalSearchSettings v-if="activeTab === 'local'" account-wide id="ais-local" role="tabpanel" aria-labelledby="ais-local-tab" />
    <p v-if="error" role="alert" class="ais-feedback is-error">{{ error }}</p>
    <p v-if="notice" role="status" class="ais-feedback is-success"><CircleCheck :size="16" :stroke-width="1.8" aria-hidden="true" />{{ notice }}</p>

    <div id="ais-config" v-show="activeTab === 'config'" role="tabpanel" aria-labelledby="ais-config-tab">
      <div class="ais-profilebar">
        <div><h4>已连接的服务</h4><p class="ais-muted">统一管理聊天总结与关注提醒使用的模型。</p></div>
        <button type="button" class="ais-add" :disabled="busy" @click="startNew"><Plus :size="16" :stroke-width="1.8" aria-hidden="true" />新增服务</button>
      </div>
      <div class="ais-service-list">
        <button v-for="p in profiles" :key="p.id" type="button" class="ais-service-card" :disabled="busy" :aria-label="`编辑 ${p.name}`" @click="edit(p)">
          <AiProviderIcon :provider="p.provider" />
          <span class="ais-service-copy"><strong>{{ p.name }}</strong><small>{{ p.model }}</small><small v-if="p.context_window">上下文 {{ formatNumber(p.context_window) }} tokens</small></span>
          <span v-if="p.vision" class="ais-tag">支持图片</span><ChevronRight :size="16" :stroke-width="1.8" aria-hidden="true" />
        </button>
        <div v-if="!profiles.length" class="ais-empty"><Plug :size="16" :stroke-width="1.8" aria-hidden="true" /><h4>连接你的第一个 AI 服务</h4><p>选择服务商，填写密钥，即可获取可用模型。</p></div>
      </div>
      <p class="ais-footnote">密钥仅保存在本机。分析内容将发送至你选择的服务。</p>

      <Teleport to="body">
      <div v-if="dialogStep" class="ais-dialog-overlay" @pointerdown="onBackdropPointerDown" @pointerup="onBackdropPointerUp" @pointercancel="backdropPressed = false" @click="onBackdropClick" @keydown.stop="onDialogKeydown">
      <section ref="dialogPanel" class="ai-settings ais-dialog" :class="{ 'ais-provider-picker': dialogStep === 'providers' }" role="dialog" aria-modal="true" aria-labelledby="ais-dialog-title" tabindex="-1">
        <header class="ais-dialog-heading"><div><h3 id="ais-dialog-title">{{ dialogStep === 'providers' ? '选择 AI 服务' : editId ? '编辑 AI 服务' : '添加 AI 服务' }}</h3><p>{{ dialogStep === 'providers' ? '选择服务商，也可以连接兼容接口的自定义服务。' : '连接服务后，从上游获取并选择可用模型。' }}</p></div><button type="button" class="ais-icon-button" aria-label="关闭服务弹窗" :disabled="busy" @click="closeDialog"><X :size="16" :stroke-width="1.8" aria-hidden="true" /></button></header>
        <template v-if="dialogStep === 'providers'">
          <label class="ais-provider-search"><span class="ais-sr-only">搜索 AI 服务</span><Search :size="16" :stroke-width="1.8" aria-hidden="true" /><input v-model="providerSearch" type="search" placeholder="搜索服务名称，例如：谷歌、千问、火山" /></label>
          <div class="ais-provider-grid">
            <button v-for="p in filteredPresets" :key="p.provider" type="button" class="ais-provider-choice" @click="chooseProvider(p.provider)"><AiProviderIcon :provider="p.provider" /><span><strong>{{ providerInfo(p.provider)?.label || p.name }}</strong><small>{{ providerInfo(p.provider)?.caption || providerHint(p.provider) }}</small></span><ChevronRight :size="16" :stroke-width="1.8" aria-hidden="true" /></button>
          </div>
          <div v-if="!filteredPresets.length" class="ais-empty" role="status"><p>没有匹配的 AI 服务，试试其他名称。</p><button type="button" @click="providerSearch = ''">清空搜索</button></div>
        </template>
        <template v-else>
        <p v-if="error" role="alert" class="ais-feedback is-error">{{ error }}</p>
        <p v-if="notice" role="status" class="ais-feedback is-success">{{ notice }}</p>
      <form class="ais-editor" @submit.prevent="save">
        <div class="ais-editor-heading">
          <div class="ais-selected-provider"><AiProviderIcon :provider="form.provider" /><div><h4>{{ presets.find(p => p.provider === form.provider)?.name || form.provider }}</h4><span>{{ providerHint(form.provider) }}</span></div></div>
          <button type="button" class="ais-change-provider" :disabled="busy" @click="showProviders">更换服务商</button>
        </div>
        <div class="ais-form-body">
          <div class="ais-connection">
          <div class="ais-fields">
            <label>配置名称<input v-model.trim="form.name" required maxlength="80" placeholder="例如：日常总结" /></label>
            <label>接口协议<UiSelect v-model="form.protocol" label="接口协议" :options="protocolOptions" /></label>
          </div>
          <div class="ais-fields ais-address-row">
            <label>API 地址<input v-model.trim="form.base_url" class="ais-mono" required type="url" placeholder="https://…" @blur="autoFetchModels" /></label>
          </div>
          <label class="ais-key-label"><span>API 密钥 <span v-if="editId && form.has_key && !key" class="ais-tag">已保存</span></span><input v-model="key" type="password" autocomplete="new-password" :placeholder="editId && !credentialsReset ? '留空保留已有密钥' : '输入 API 密钥，本地服务可留空'" @blur="autoFetchModels" /></label>
          <p v-if="isLocalService" class="ais-muted">请先启动本地服务并准备好模型；未启用鉴权时，API 密钥可留空。</p>

          </div>
          <div class="ais-model-config">
          <div class="ais-model-section">
            <div class="ais-section-heading">
              <div><h5>使用模型</h5><span v-if="models.length && !modelError">已从上游获取 {{ models.length }} 个模型</span><span v-else>模型列表直接来自你的服务商</span></div>
              <button type="button" class="ais-refresh" :disabled="busy || modelsLoading || !form.base_url" @click="getModels"><LoaderCircle v-if="modelsLoading" class="agent-icon-spin" :size="16" :stroke-width="1.8" aria-hidden="true" /><RefreshCw v-else :size="16" :stroke-width="1.8" aria-hidden="true" />{{ modelsLoading ? '获取中…' : '从上游获取' }}</button>
            </div>
            <p v-if="modelError" role="alert" class="ais-feedback is-error">{{ modelError }}</p>
            <template v-if="!manualModel">
              <div class="ais-model-controls">
                <UiSelect v-model="form.model" label="选择模型" mono searchable search-placeholder="搜索模型" :disabled="modelsLoading || !models.length" :options="modelOptions" :placeholder="modelsLoading ? '正在加载模型…' : isLocalService ? '启动本地服务后，从上游获取模型' : '填写密钥后，从上游获取模型'" @change="selectModel" />
              </div>
            </template>
            <label v-else>模型名称<input v-model.trim="form.model" class="ais-mono" required placeholder="上游不支持获取列表时手动填写" @blur="fetchMetadata" /></label>
            <label class="ais-manual"><input v-model="manualModel" type="checkbox" />手动输入（备用）</label>
            <div class="ais-section-heading"><h5>模型能力</h5><button v-if="hasOverrides" type="button" class="ais-refresh" @click="restoreAutomatic">恢复自动识别</button></div>
            <p class="ais-muted">模型能力将自动识别，你也可以按需调整。</p>
            <label>模型上下文窗口（tokens） · {{ capabilitySource('context_window') }}<input v-model.number="form.context_window" type="number" min="4096" max="10000000" placeholder="自动识别，或手动填写" @input="setOverride('context_window', $event.target.value ? Number($event.target.value) : null)" /></label>
          </div>

          <label class="ais-vision">
            <span class="ais-vision-icon"><ImageIcon :size="16" :stroke-width="1.8" aria-hidden="true" /></span>
            <span class="ais-vision-copy"><strong>此模型支持图片理解</strong><small>{{ capabilitySource('vision') }} · 可手动调整，用于图片与扫描文档。</small></span>
            <input v-model="form.vision" class="ais-switch" type="checkbox" role="switch" @change="setOverride('vision', $event.target.checked)" />
          </label>
          <details class="ais-capability-options"><summary>其他能力与参数</summary>
            <label>最大输出（tokens） · {{ capabilitySource('max_output_tokens') }}<input :value="form.model_overrides.max_output_tokens ?? selectedMetadata?.limit?.output ?? ''" type="number" min="1" max="10000000" placeholder="自动识别，或手动填写" @input="setOverride('max_output_tokens', $event.target.value ? Number($event.target.value) : null)" /></label>
            <label v-for="field in editableCapabilities" :key="field.key">{{ field.label }}<UiSelect :model-value="overrideChoice(field.key)" :label="field.label" :options="capabilityOptions(field.key)" @update:model-value="setOverride(field.key, $event === 'auto' ? null : $event === 'yes')" /></label>
            <label>原生推理等级 · {{ capabilitySource('reasoning_efforts') }}
              <input aria-label="供应商确认的原生推理等级" :value="(form.model_overrides.reasoning_efforts ?? selectedMetadata?.reasoning_efforts ?? []).join(', ')" maxlength="800" placeholder="例如：low, high, max" @change="setReasoningEfforts($event.target.value)" />
              <small class="ais-muted">仅填写供应商已确认支持的等级，用逗号分隔；留空恢复自动识别。</small>
            </label>
            <AiModelMetadata v-if="selectedMetadata" :metadata="selectedMetadata" />
            <p v-else class="ais-muted">暂未获取到参考参数，使用上方手动配置。</p>
          </details>
          </div>
        </div>
        <footer class="ais-editor-footer">
          <button v-if="editId" type="button" class="ais-icon-button ais-delete" :disabled="busy" title="删除配置" aria-label="删除配置" @click="remove"><Trash2 :size="16" :stroke-width="1.8" aria-hidden="true" /></button><span v-else>密钥仅保存在本机</span>
          <div><button type="button" :disabled="busy || !editId" title="检查已保存的服务能否正常响应；修改配置后请先保存" @click="test">{{ testing ? '测试中…' : '测试连接' }}</button><button class="ais-primary" :disabled="busy || modelsLoading || !form.model || (!manualModel && !models.includes(form.model))"><Check :size="16" :stroke-width="1.8" aria-hidden="true" />保存配置</button></div>
        </footer>
      </form>
      <p class="ais-footnote">测试使用已保存的配置，修改后请先保存。测试会产生少量用量，可在「使用量审计」查看。</p>
        </template>
      </section>
      </div>
      </Teleport>
    </div>

    <div id="ais-usage" v-show="activeTab === 'usage'" role="tabpanel" aria-labelledby="ais-usage-tab">
      <div class="ais-metrics">
        <div><span>累计调用</span><strong>{{ formatNumber(usage?.calls) }}<small>次</small></strong></div>
        <div><span>输入 tokens</span><strong>{{ formatNumber(usage?.input_tokens) }}</strong></div>
        <div><span>输出 tokens</span><strong>{{ formatNumber(usage?.output_tokens) }}</strong></div>
      </div>
      <div class="ais-audit-toolbar"><div><h4>调用明细</h4><p>失败 {{ usage?.failed_calls || 0 }} 次 · 用量未知 {{ usage?.unknown_usage_calls || 0 }} 次</p></div><div><button type="button" :disabled="busy" @click="action(() => loadAudit(true))"><RefreshCw :size="16" :stroke-width="1.8" aria-hidden="true" />刷新</button><button type="button" :disabled="!audit.length" @click="exportAudit"><Download :size="16" :stroke-width="1.8" aria-hidden="true" />导出已加载记录</button></div></div>
      <div class="ais-table-wrap">
        <table v-if="audit.length" class="ais-audit-table"><thead><tr><th>模型 / 时间</th><th>状态</th><th>用量</th><th>详情</th></tr></thead>
          <tbody><tr v-for="r in audit" :key="r.id">
            <td><strong :title="r.model">{{ r.model || r.profile_name || r.profile_id }}</strong><small>{{ r.started_at ? new Date(r.started_at * 1000).toLocaleString() : '历史记录' }}</small></td>
            <td><span class="ais-status" :class="'status-' + (r.status || 'success')">{{ statusLabel(r.status) }}</span><small v-if="r.http_status">HTTP {{ r.http_status }}</small></td>
            <td class="ais-token-cell"><span>输入 {{ r.usage_known === false ? '未知' : (r.usage?.input_tokens ?? '未知') }}</span><span>输出 {{ r.usage_known === false ? '未知' : (r.usage?.output_tokens ?? '未知') }}</span></td>
            <td><details><summary>查看</summary><div class="ais-audit-detail">{{ r.profile_name || r.profile_id }}<br />第 {{ r.attempt || 1 }} 次尝试 · 图片 {{ r.image_count || 0 }} 张<br />{{ r.account ? '账号 ' + r.account : '' }}<br v-if="r.account" />{{ r.task_id ? '任务 ' + r.task_id : '独立调用 / 连接测试' }}</div></details></td>
          </tr></tbody></table>
        <div v-else class="ais-empty"><ChartBar :size="16" :stroke-width="1.8" aria-hidden="true" /><h4>还没有调用记录</h4><p>完成第一次总结或连接测试后，用量会显示在这里。</p></div>
      </div>
      <button v-if="hasMoreAudit" type="button" class="ais-load-more" :disabled="busy" @click="action(() => loadAudit(false))">加载更多</button>
      <p class="ais-footnote">每次重试单独记录，费用以服务商账单为准。审计不包含密钥和聊天正文。</p>
    </div>
  </div>
</template>

<script setup>
import { ChartBar, ChartNoAxesColumn, Check, ChevronRight, CircleCheck, Download, Image as ImageIcon, LoaderCircle, Lock, Plug, Plus, RefreshCw, Search, Trash2, WandSparkles, X } from '@lucide/vue'
import AiModelMetadata from './AiModelMetadata.vue'
import LocalSearchSettings from './LocalSearchSettings.vue'
import AiProviderIcon from './AiProviderIcon.vue'
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import UiSelect from './UiSelect.vue'
import '~/assets/css/ai-settings.css'
const activeTab = ref('config')
const settingsTabs = [
  {id:'config',label:'模型服务',hint:'连接与模型配置',icon:Plug},
  {id:'local',label:'本地检索',hint:'按意思查找聊天',icon:Search},
  {id:'usage',label:'用量记录',hint:'调用明细与消耗',icon:ChartNoAxesColumn},
]
function navigateTabs(event,id){
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return
  event.preventDefault()
  const index=settingsTabs.findIndex(tab=>tab.id===id)
  const next=event.key==='Home'?0:event.key==='End'?settingsTabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+settingsTabs.length)%settingsTabs.length
  activeTab.value=settingsTabs[next].id
  nextTick(()=>document.getElementById(`ais-${activeTab.value}-tab`)?.focus())
}
const localSettingsTarget = useSettingsDialog().focusTarget || ref('')
// 服务连接结果不带入本地检索、Agent 或审计页面。
watch(activeTab, () => { error.value = ''; notice.value = '' })
watch(localSettingsTarget, target => { if (target === 'local-search') activeTab.value = 'local' }, { immediate: true })
const formatNumber = (value) => Number(value || 0).toLocaleString('zh-CN')
const protocolOptions = [{ value: 'openai', label: 'OpenAI 兼容' }, { value: 'anthropic', label: 'Claude Messages' }]
const providerPresentation = {
  deepseek: { hint: 'DeepSeek 官方接口', aliases: '深度求索' },
  xiaomi: { caption: '小米 MiMo 开放平台', hint: '小米官方 OpenAI 兼容接口', aliases: '小米 MiMo' },
  claude: { hint: 'Claude Messages 接口', aliases: 'Anthropic' },
  kimi: { hint: 'Moonshot 兼容接口', aliases: '月之暗面' },
  openai: { hint: 'OpenAI 官方接口', aliases: 'ChatGPT GPT' },
  gemini: { label: 'Gemini', caption: 'Google AI Studio', hint: 'Google AI Studio 兼容接口', aliases: '谷歌' },
  qwen: { label: '通义千问', caption: '阿里云百炼', hint: '阿里云百炼 · 国内通用接口', aliases: '通义 千问 阿里 DashScope' },
  zhipu: { caption: '智谱开放平台', hint: '智谱开放平台 · 国内通用接口', aliases: '智谱 GLM BigModel' },
  doubao: { label: '豆包', caption: '火山方舟', hint: '火山方舟 · 国内通用接口', aliases: '字节 火山引擎 Volcengine Ark' },
  siliconflow: { caption: 'SiliconCloud', hint: '硅基流动 · 国内模型服务', aliases: 'SiliconCloud' },
  openrouter: { caption: '多模型聚合服务', hint: '聚合多个服务商的模型', aliases: '' },
  requesty: { caption: '多模型聚合服务', hint: '聚合多个服务商的模型', aliases: '' },
  groq: { hint: 'Groq 官方兼容接口', aliases: '' },
  ollama: { caption: '本地模型服务', hint: '本地模型 · 默认端口 11434', aliases: '本机 local' },
  lmstudio: { caption: '本地模型服务', hint: '本地模型 · 默认端口 1234', aliases: '本机 local' },
  custom: { hint: '自定义地址与接口协议', aliases: '兼容' },
}
const providerInfo = provider => providerPresentation[provider === 'anthropic' ? 'claude' : provider]
const providerHint = provider => providerInfo(provider)?.hint || '连接模型服务'
const providerSearch = ref('')
const filteredPresets = computed(() => {
  const query = providerSearch.value.trim().toLowerCase()
  return presets.value.filter(p => `${p.name} ${p.provider} ${providerHint(p.provider)} ${providerInfo(p.provider)?.aliases || ''}`.toLowerCase().includes(query))
    .sort((a, b) => Number(a.provider === 'custom') - Number(b.provider === 'custom'))
})
const dialogStep = ref(''), dialogPanel = ref(null)
let returnFocus = null
let backdropPressed = false
// 拖选文字时，浏览器可能把弹窗内按下、遮罩上松开的 click 派发到遮罩。
// 只有按下和松开都发生在遮罩上的主键点击才关闭弹窗。
const onBackdropPointerDown = event => {
  backdropPressed = event.button === 0 && event.isPrimary !== false && event.target === event.currentTarget
}
const onBackdropPointerUp = event => {
  backdropPressed = backdropPressed && event.target === event.currentTarget
}
const onBackdropClick = event => {
  const shouldClose = backdropPressed && event.target === event.currentTarget
  backdropPressed = false
  if (shouldClose) closeDialog()
}
const focusDialog = () => nextTick(() => dialogPanel.value?.focus())
const closeDialog = () => {
  if (busy.value) return
  backdropPressed = false
  dialogStep.value = ''; key.value = ''; error.value = ''
  invalidateModels()
  nextTick(() => { if (returnFocus?.isConnected) returnFocus.focus() })
}
const showProviders = () => { providerSearch.value = ''; dialogStep.value = 'providers'; focusDialog() }
const startNew = () => { returnFocus = document.activeElement; reset(); error.value = ''; notice.value = ''; showProviders() }
const chooseProvider = provider => {
  form.provider = provider; applyPreset(); dialogStep.value = 'edit'; focusDialog()
  if (isLocalService.value) autoFetchModels()
}
const onDialogKeydown = event => {
  if (event.key === 'Escape') { event.preventDefault(); closeDialog() }
  if (event.key !== 'Tab') return
  const nodes = [...dialogPanel.value.querySelectorAll('button:not(:disabled), input:not(:disabled), [tabindex="0"]')]
  const first = nodes[0], last = nodes.at(-1)
  if (!first) { event.preventDefault(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogPanel.value)) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialogPanel.value)) { event.preventDefault(); first.focus() }
}
const api = useAiApi()
const profiles = ref([]), presets = ref([]), models = ref([]), editId = ref(''), key = ref('')
const busy = ref(false), error = ref(''), notice = ref(''), usage = ref(null)
const testing = ref(false)
const audit = ref([]), hasMoreAudit = ref(false)
const statusLabel = (status) => ({ success: '成功', failed: '失败', cancelled: '已取消', interrupted: '已中断', running: '执行中' }[status] || (status ? '未知状态' : '历史成功调用'))
const loadAudit = async (reset = true) => {
  const rows = await api.request(`/usage/records?limit=50&offset=${reset ? 0 : audit.value.length}`)
  audit.value = reset ? rows : [...audit.value, ...rows]; hasMoreAudit.value = rows.length === 50
  usage.value = await api.request('/usage')
}
const exportAudit = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(audit.value, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = 'ai-usage-audit.json'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
const blank = () => ({ provider: 'deepseek', name: 'DeepSeek', protocol: 'openai', base_url: 'https://api.deepseek.com/v1', model: '', vision: false, context_window: null, model_overrides: {} })
const form = reactive(blank())
// 切换预设后明确清空凭据，不让后端复用原配置的密钥。
const credentialsReset = ref(false)
const isLocalService = computed(() => {
  if (!['ollama', 'lmstudio'].includes(form.provider)) return false
  try { return ['localhost', '127.0.0.1', '[::1]'].includes(new URL(form.base_url).hostname) } catch { return false }
})
const manualModel = ref(false), modelDetails = ref([]), modelError = ref(''), modelsLoading = ref(false)
const manualMetadata = ref(null)
const selectedMetadata = computed(() => {
  const detail = modelDetails.value.find(x => x.id === form.model && x.source)
  return detail || (manualMetadata.value?.id === form.model ? manualMetadata.value : null)
})
const hasOverrides = computed(() => Object.values(form.model_overrides).some(value => value != null))
const editableCapabilities = [{key:'tool_call',label:'工具调用'},{key:'structured_output',label:'结构化输出'},{key:'reasoning',label:'推理'},{key:'temperature',label:'温度参数'},{key:'attachment',label:'附件输入'}]
const overrideChoice = key => form.model_overrides[key] == null ? 'auto' : form.model_overrides[key] ? 'yes' : 'no'
const capabilityOptions = key => [{value:'auto',label:`自动（${selectedMetadata.value?.[key] === true ? '支持' : selectedMetadata.value?.[key] === false ? '不支持' : '未知'}）`},{value:'yes',label:'支持'},{value:'no',label:'不支持'}]
const capabilitySource = key => {
  if (form.model_overrides[key] != null) return '手动设置'
  const known = key === 'context_window' ? selectedMetadata.value?.limit?.context : key === 'max_output_tokens' ? selectedMetadata.value?.limit?.output : selectedMetadata.value?.[key]
  return known == null ? '未识别' : '自动识别'
}
const setOverride = (key, value) => {
  if (value == null) { delete form.model_overrides[key]; selectModel() }
  else form.model_overrides[key] = value
}
const setReasoningEfforts = value => {
  const levels = [...new Set(value.split(/[,，\s]+/).map(level => level.trim()).filter(Boolean))]
  setOverride('reasoning_efforts', levels.length ? levels : null)
}
const restoreAutomatic = async () => {
  form.model_overrides = {}; form.context_window = null; form.vision = false
  await fetchMetadata(); selectModel(false)
}
let metadataRequest = 0
const fetchMetadata = async () => {
  const request = ++metadataRequest
  if (!form.model) { manualMetadata.value = null; return }
  try {
    const params = new URLSearchParams({ provider: form.provider, model: form.model, base_url: form.base_url, protocol: form.protocol })
    const data = await api.request(`/model-metadata?${params}`)
    if (request !== metadataRequest) return
    manualMetadata.value = data.metadata || null
    if (manualMetadata.value) selectModel()
  } catch { if (request === metadataRequest) manualMetadata.value = null }
}
watch(() => form.model, () => { metadataRequest++; manualMetadata.value = null; form.context_window = null; form.vision = false; form.model_overrides = {} }, { flush: 'sync' })
const modelOptions = computed(() => {
  const options = models.value.map(model => ({ value: model, label: model, description: modelDetails.value.find(x => x.id === model)?.vision === true ? '支持图片理解' : '' }))
  if (form.model && !options.some(option => option.value === form.model)) options.unshift({ value: form.model, label: form.model, description: models.value.includes(form.model) ? '当前选择' : '未在上游列表中确认', disabled: true })
  return options
})
let modelRequest = 0, fetchedSignature = ''
const discoverySignature = () => JSON.stringify([editId.value, form.base_url, form.protocol, key.value])
const invalidateModels = () => {
  modelRequest++; metadataRequest++; manualMetadata.value = null; modelsLoading.value = false; models.value = []; modelDetails.value = []
  modelError.value = ''; fetchedSignature = ''
}
watch([editId, () => form.base_url, () => form.protocol, key], () => {
  invalidateModels(); form.model = ''; form.vision = false
}, { flush: 'sync' })
onBeforeUnmount(() => { modelRequest++; metadataRequest++; key.value = '' })
const action = async (fn) => {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e) { error.value = e.message } finally { busy.value = false }
}
const load = async () => {
  const data = await api.request('/settings')
  profiles.value = data.profiles; presets.value = data.presets
  await loadAudit()
}
const reset = () => { invalidateModels(); editId.value = ''; key.value = ''; credentialsReset.value = false; manualModel.value = false; Object.assign(form, blank()) }
const edit = (p) => {
  if (!dialogStep.value) returnFocus = document.activeElement
  dialogStep.value = 'edit'; error.value = ''; notice.value = ''; focusDialog()
  invalidateModels(); editId.value = p.id; key.value = ''; credentialsReset.value = false; manualModel.value = false
  Object.assign(form, p); form.model = p.model; form.vision = p.vision
  form.model_overrides = { ...(p.model_overrides || {}) }
  manualMetadata.value = p.automatic_metadata || p.model_metadata || null
  void getModels()
}
const applyPreset = () => {
  const p = presets.value.find(x => x.provider === form.provider)
  key.value = ''; credentialsReset.value = true; form.has_key = false; manualModel.value = false
  if (p) Object.assign(form, { provider: p.provider, name: p.name, protocol: p.protocol, base_url: p.base_url })
  invalidateModels(); form.model = ''; form.vision = false
}
const save = () => action(async () => {
  if (manualModel.value) await fetchMetadata()
  const body = { ...form, context_window: form.context_window || null, api_key: key.value.trim() || (editId.value && !credentialsReset.value ? null : '') }
  await api.request(editId.value ? `/profiles/${editId.value}` : '/profiles', { method: editId.value ? 'PUT' : 'POST', body })
  await load(); key.value = ''; dialogStep.value = ''; invalidateModels(); notice.value = '配置已保存'
  nextTick(() => returnFocus?.isConnected && returnFocus.focus())
})
const selectModel = (keepSaved = true) => {
  const detail = selectedMetadata.value || modelDetails.value.find(x => x.id === form.model)
  const saved = profiles.value.find(x => x.id === editId.value)
  const sameSaved = keepSaved && saved?.model === form.model && saved?.base_url === form.base_url && saved?.protocol === form.protocol
  form.vision = form.model_overrides.vision ?? (typeof detail?.vision === 'boolean' ? detail.vision : (sameSaved && saved.model_overrides?.vision == null ? saved.vision : false))
  form.context_window = form.model_overrides.context_window ?? detail?.limit?.context ?? (sameSaved && saved.model_overrides?.context_window == null ? saved.context_window : null) ?? null
}
const getModels = async () => {
  if (busy.value || modelsLoading.value) return
  const request = ++modelRequest, signature = discoverySignature()
  modelsLoading.value = true; modelError.value = ''
  try {
    const data = await api.request('/models', { method: 'POST', body: { provider: form.provider, base_url: form.base_url, protocol: form.protocol, api_key: key.value.trim() || (credentialsReset.value ? '' : null), profile_id: editId.value } })
    // 切换配置或修改凭据后，迟到的响应不能覆盖当前模型列表。
    if (request !== modelRequest) return
    models.value = data.models || []; modelDetails.value = data.model_details || []; fetchedSignature = signature
    if (!models.value.length) { modelError.value = '上游没有返回可用模型，可重试或使用手动输入。'; return }
    if (!form.model) {
      form.model = modelDetails.value.find(x => x.vision === true)?.id || models.value[0]
      selectModel()
    } else if (!models.value.includes(form.model)) {
      modelError.value = '已保存模型未出现在上游列表中，请重新选择，或启用手动输入保留。'
    } else {
      selectModel()
    }
  } catch (e) {
    if (request === modelRequest) modelError.value = isLocalService.value ? `${e.message}。请检查本地服务是否已启动、地址和端口是否正确；启用鉴权时请填写密钥，也可使用手动输入。` : e.message
  } finally {
    if (request === modelRequest) modelsLoading.value = false
  }
}
const autoFetchModels = () => {
  if (!form.base_url || modelsLoading.value || fetchedSignature === discoverySignature()) return
  if (!key.value.trim() && !(editId.value && !credentialsReset.value) && form.provider !== 'custom' && !isLocalService.value) return
  void getModels()
}
const test = () => action(async () => {
  testing.value = true
  try {
    const result = await api.request(`/profiles/${editId.value}/test`, { method: 'POST' })
    // 兼容旧后端也不直接展示模型自由生成的测试回答。
    notice.value = '连接成功，模型已正常响应。' + (result.test_type === 'image' ? '本次也测试了图片输入。' : '')
    await load()
  } finally { testing.value = false }
})
const remove = () => action(async () => { await api.request(`/profiles/${editId.value}`, { method: 'DELETE' }); reset(); await load(); dialogStep.value = ''; notice.value = '配置已删除，引用它的规则已暂停'; nextTick(() => document.querySelector('.ais-add')?.focus()) })
onMounted(() => action(load))
</script>
