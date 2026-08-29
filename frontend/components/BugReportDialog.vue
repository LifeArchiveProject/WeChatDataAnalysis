<template>
  <GuideDialog
    :open="open"
    wide
    show-close-icon
    eyebrow=""
    title="提交 Bug 反馈"
    description=""
    primary-label=""
    secondary-label=""
    :dismissible="!sending"
    @close="close"
  >
    <template #title-extra>
      <button type="button" class="bug-feedback-weq-link" title="打开 WeQ：面向 NTQQ 的本地消息数据库解密、解析与导出工具" @click="openWeqProject">
        <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>
        <span>本功能的 QQ 在线检测、Hook 注入与闪传能力来自 WeQ。WeQ 是面向 NTQQ 的本地消息数据库解密、解析与导出工具；感谢 H3CoF6 与项目贡献者。</span>
      </button>
    </template>
    <div class="bug-feedback">
      <div class="bug-feedback-status" :data-state="qqState" role="status">
        <i :class="['fa-solid', qqState === 'online' ? 'fa-circle-check' : qqState === 'loading' ? 'fa-spinner fa-spin' : 'fa-circle-exclamation']" aria-hidden="true"></i>
        <span>{{ qqStatusText }}</span>
      </div>

      <div class="bug-feedback-layout">
        <form class="bug-feedback-form" @submit.prevent="submit">
          <div class="bug-feedback-summary-row">
            <label class="bug-feedback-field">
              <span>问题标题 <b>*</b></span>
              <input ref="titleInput" v-model="form.title" type="text" maxlength="200" placeholder="一句话说明发生了什么" :disabled="sending || sent" />
            </label>
            <label class="bug-feedback-field">
              <span>微信版本 <b>*</b></span>
              <input v-model="form.wechatVersion" type="text" maxlength="100" placeholder="4.0.6" :disabled="sending || sent" />
            </label>
            <label class="bug-feedback-field">
              <span>出错功能 <b>*</b></span>
              <select v-model="form.module" :disabled="sending || sent">
                <option value="" disabled>请选择出错功能</option>
                <option v-for="item in moduleOptions" :key="item" :value="item">{{ item }}</option>
              </select>
            </label>
            <label class="bug-feedback-field">
              <span>问题发生时间 <b>*</b></span>
              <input v-model="form.occurredAt" type="text" maxlength="200" placeholder="2026-08-26 16:30（UTC+8）" :disabled="sending || sent" />
            </label>
          </div>
          <label class="bug-feedback-field">
            <span>问题描述 <b>*</b></span>
            <small>请说明哪个操作出现了什么问题。</small>
            <textarea v-model="form.description" rows="3" maxlength="20000" :disabled="sending || sent" />
          </label>
          <label class="bug-feedback-field">
            <span>复现步骤 <b>*</b></span>
            <small>请按实际操作顺序逐步填写。</small>
            <textarea v-model="form.steps" rows="4" maxlength="20000" placeholder="1. 打开……&#10;2. 选择……&#10;3. 点击……" :disabled="sending || sent" />
          </label>
          <label class="bug-feedback-field"><span>预期结果 <b>*</b></span><textarea v-model="form.expected" rows="3" maxlength="20000" :disabled="sending || sent" /></label>
          <label class="bug-feedback-field">
            <span>实际结果 <b>*</b></span>
            <small>请粘贴完整错误文本，不要只填写“失败”。</small>
            <textarea v-model="form.actual" rows="3" maxlength="20000" :disabled="sending || sent" />
          </label>

          <div class="bug-feedback-field">
            <span>截图或录屏</span>
            <small>选填；请先遮挡账号、路径和聊天内容。点击下方区域后按 Ctrl+V 可粘贴截图。</small>
            <div class="bug-feedback-paste-zone" tabindex="0" @paste="onScreenshotPaste">
              <i class="fa-regular fa-clipboard" aria-hidden="true"></i>
              <span>Ctrl+V 粘贴 PNG、JPEG 或 WebP，最多 5 张</span>
              <textarea v-model="form.screenshots" rows="2" maxlength="20000" placeholder="可填写截图或录屏说明" :disabled="sending || sent" @paste.stop="onScreenshotPaste" />
            </div>
            <div v-if="pastedScreenshots.length" class="bug-feedback-screenshots">
              <figure v-for="(item, index) in pastedScreenshots" :key="item.url">
                <img :src="item.url" :alt="`粘贴截图 ${index + 1}`" />
                <button type="button" :disabled="sending || sent" :aria-label="`移除截图 ${index + 1}`" @click="removeScreenshot(index)">×</button>
              </figure>
            </div>
          </div>

          <fieldset class="bug-feedback-confirmations" :disabled="sending || sent">
            <legend>提交确认 <b>*</b></legend>
            <label><input v-model="form.confirmations.duplicateSearch" type="checkbox" />我已搜索现有 Issue，未发现相同问题。</label>
            <label><input v-model="form.confirmations.logsAttached" type="checkbox" />我已上传问题对应时段的完整日志。</label>
            <label><input v-model="form.confirmations.sensitiveDataRemoved" type="checkbox" />我没有上传数据库、密钥或未脱敏的聊天内容。</label>
          </fieldset>
        </form>

      </div>

      <ErrorNotice v-if="error" :message="error" compact />
      <p v-if="sent" class="bug-feedback-success">日志与完整问题表单已上传并发出 QQ 闪传消息。</p>
      <p v-else-if="missingFields.length" class="bug-feedback-required">还需完成：{{ missingFields.join('、') }}</p>
      <div class="bug-feedback-actions">
        <button type="button" class="bug-feedback-cancel" :disabled="sending" @click="close">取消</button>
        <button type="button" class="bug-feedback-send" :disabled="sendDisabled" @click="submit">
          <i :class="['fa-solid', sending ? 'fa-spinner fa-spin' : sent ? 'fa-check' : 'fa-paper-plane']" aria-hidden="true"></i>{{ sendLabel }}
        </button>
      </div>
    </div>
  </GuideDialog>
</template>

<script setup>
const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['close'])
const { detectWechat } = useApi()
const moduleOptions = ['安装或启动', '微信与账号检测', '密钥获取或数据库解密', '聊天记录', '图片、视频或语音', '导入或导出', '其他']
const titleInput = ref(null)
const loading = ref(false)
const sending = ref(false)
const sent = ref(false)
const error = ref('')
const info = ref(null)
const pastedScreenshots = ref([])
const form = reactive({
  title: '', wechatVersion: '', module: '', occurredAt: '', description: '', steps: '', expected: '', actual: '', screenshots: '',
  confirmations: { duplicateSearch: false, logsAttached: false, sensitiveDataRemoved: false },
})

const logNames = computed(() => Array.isArray(info.value?.logs?.names) ? info.value.logs.names : [])
const qqState = computed(() => loading.value ? 'loading' : info.value?.qq?.online && info.value?.projectGroup?.found && logNames.value.length ? 'online' : 'offline')
const qqStatusText = computed(() => {
  if (loading.value) return '正在检测本机 QQ、项目群与应用日志…'
  if (info.value?.qq?.online && !info.value?.projectGroup?.found) return info.value?.projectGroup?.reason || '未检测到已加入的 WeChatDataAnalysis 项目群'
  if (info.value?.qq?.online && !logNames.value.length) return '已检测到 QQ，但尚未找到可发送的应用日志'
  if (info.value?.qq?.online) return `已检测到项目群 ${info.value.projectGroup.name}（${info.value.projectGroup.groupId}），可以发送日志`
  return info.value?.qq?.reason || '未检测到可用的 QQ 桌面端'
})
const missingFields = computed(() => {
  const missing = []
  if (!form.title.trim()) missing.push('问题标题')
  if (!form.wechatVersion.trim()) missing.push('微信版本')
  if (!form.module) missing.push('出错功能')
  if (!form.occurredAt.trim()) missing.push('问题发生时间')
  if (!form.description.trim()) missing.push('问题描述')
  if (!form.steps.trim()) missing.push('复现步骤')
  if (!form.expected.trim()) missing.push('预期结果')
  if (!form.actual.trim()) missing.push('实际结果')
  if (!form.confirmations.duplicateSearch || !form.confirmations.logsAttached || !form.confirmations.sensitiveDataRemoved) missing.push('提交确认')
  return missing
})
const sendDisabled = computed(() => loading.value || sending.value || sent.value || !info.value?.qq?.online || !info.value?.projectGroup?.found || !logNames.value.length || missingFields.value.length > 0)
const sendLabel = computed(() => sending.value ? '正在上传…' : sent.value ? '日志已发送' : '发送反馈日志')
const openWeqProject = async () => {
  const url = 'https://github.com/H3CoF6/WeQ'
  if (window.wechatDesktop?.openExternalUrl) await window.wechatDesktop.openExternalUrl(url)
  else window.open(url, '_blank', 'noopener,noreferrer')
}

const clearScreenshots = () => {
  for (const item of pastedScreenshots.value) URL.revokeObjectURL(item.url)
  pastedScreenshots.value = []
}
const removeScreenshot = (index) => {
  const [item] = pastedScreenshots.value.splice(index, 1)
  if (item) URL.revokeObjectURL(item.url)
}
const onScreenshotPaste = (event) => {
  const files = Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === 'file' && ['image/png', 'image/jpeg', 'image/webp'].includes(item.type))
    .map((item) => item.getAsFile())
    .filter(Boolean)
  if (!files.length) return
  event.preventDefault()
  error.value = ''
  for (const file of files) {
    if (pastedScreenshots.value.length >= 5) { error.value = '最多粘贴 5 张截图。'; break }
    if (file.size > 10 * 1024 * 1024) { error.value = '单张截图必须小于 10 MB。'; continue }
    const extension = file.type === 'image/jpeg' ? 'jpg' : file.type.split('/')[1]
    pastedScreenshots.value.push({ file, extension, url: URL.createObjectURL(file) })
  }
}

const currentOccurredAt = () => {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  const minutes = -now.getTimezoneOffset()
  const sign = minutes >= 0 ? '+' : '-'
  const absolute = Math.abs(minutes)
  const offset = `${sign}${Math.floor(absolute / 60)}${absolute % 60 ? `:${pad(absolute % 60)}` : ''}`
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}（UTC${offset}）`
}
const resetForm = () => {
  clearScreenshots()
  Object.assign(form, { title: '', wechatVersion: '', module: '', occurredAt: currentOccurredAt(), description: '', steps: '', expected: '', actual: '', screenshots: '' })
  Object.assign(form.confirmations, { duplicateSearch: false, logsAttached: false, sensitiveDataRemoved: false })
}
const loadInfo = async () => {
  loading.value = true
  error.value = ''
  try {
    if (!window.wechatDesktop?.getQqFeedbackInfo) throw new Error('QQ 群反馈仅支持桌面端。')
    const [desktopInfo, wechatInfo] = await Promise.all([window.wechatDesktop.getQqFeedbackInfo(), detectWechat().catch(() => null)])
    info.value = desktopInfo
    form.wechatVersion = String(wechatInfo?.data?.wechat_version || '')
  } catch (e) {
    info.value = { qq: { online: false, reason: e?.message || String(e) }, projectGroup: { found: false }, logs: { names: [] } }
  } finally { loading.value = false }
}
const submit = async () => {
  if (sendDisabled.value) return
  sending.value = true
  error.value = ''
  try {
    const screenshotFiles = await Promise.all(pastedScreenshots.value.map(async (item) => ({
      mimeType: item.file.type,
      bytes: new Uint8Array(await item.file.arrayBuffer()),
    })))
    const result = await window.wechatDesktop.sendQqBugReport({
      title: form.title.trim(), wechatVersion: form.wechatVersion.trim(), module: form.module, occurredAt: form.occurredAt.trim(),
      description: form.description.trim(), steps: form.steps.trim(), expected: form.expected.trim(), actual: form.actual.trim(),
      screenshots: form.screenshots.trim(), screenshotFiles, confirmations: { ...form.confirmations },
    })
    if (result?.status !== 'uploaded') throw new Error('日志未完成上传。')
    sent.value = true
  } catch (e) { error.value = e?.message || String(e) } finally { sending.value = false }
}
const close = () => {
  if (sending.value) return
  clearScreenshots()
  emit('close')
}
watch(() => props.open, async (open) => {
  if (!open) return
  resetForm()
  sent.value = false
  error.value = ''
  info.value = null
  await nextTick()
  titleInput.value?.focus?.()
  await loadInfo()
}, { immediate: true })
onBeforeUnmount(clearScreenshots)
</script>

<style scoped>
.bug-feedback { display: grid; gap: 14px; padding: 20px 24px 18px; }
.bug-feedback-weq-link { display: inline-flex; min-width: 0; flex: 1 1 0; align-items: flex-start; gap: 6px; border-left: 2px solid #0099ff; padding: 2px 0 2px 9px; color: #0099ff; font-size: 10.5px; font-weight: 500; line-height: 1.45; text-align: left; white-space: normal; }.bug-feedback-weq-link i { flex: 0 0 auto; margin-top: 2px; }.bug-feedback-weq-link:hover { color: #007dcc; text-decoration: underline; text-underline-offset: 2px; }
.bug-feedback-status { display: flex; align-items: flex-start; gap: 10px; border-radius: 8px; padding: 11px 13px; font-size: 12px; }
.bug-feedback-status { align-items: center; background: rgba(196,54,54,.08); color: #a12d2d; }.bug-feedback-status[data-state='online'] { background: rgba(7,183,91,.1); color: #087a40; }.bug-feedback-status[data-state='loading'] { background: var(--setup-surface-soft); color: var(--app-text-secondary); }
.bug-feedback-layout, .bug-feedback-form { display: grid; gap: 13px; min-width: 0; }.bug-feedback-form { border: 1px solid var(--app-border); border-radius: 9px; background: var(--app-surface-bg); padding: 16px; }
.bug-feedback-summary-row { display: grid; grid-template-columns: 1.25fr .65fr 1fr 1.25fr; gap: 12px; align-items: start; }
.bug-feedback-field { display: grid; gap: 6px; color: var(--app-text-secondary); font-size: 12px; font-weight: 600; }.bug-feedback-field b, .bug-feedback-confirmations b { color: #c43838; }.bug-feedback-field small { color: var(--setup-text-muted); font-size: 10.5px; font-weight: 400; line-height: 1.5; }
.bug-feedback-field :is(input,select,textarea) { width: 100%; border: 1px solid var(--app-border); border-radius: 7px; background: var(--app-surface-bg); padding: 9px 10px; color: var(--app-text-primary); font-size: 12px; font-weight: 400; outline: none; }.bug-feedback-field textarea { min-height: 68px; resize: vertical; }.bug-feedback-field :is(input,select,textarea):focus { border-color: #07b75b; box-shadow: 0 0 0 2px rgba(7,183,91,.12); }
.bug-feedback-confirmations { display: grid; gap: 8px; margin: 0; border: 1px solid var(--app-border); border-radius: 8px; padding: 12px; }.bug-feedback-confirmations legend { padding: 0 5px; color: var(--app-text-secondary); font-size: 12px; font-weight: 600; }.bug-feedback-confirmations label { display: flex; align-items: flex-start; gap: 8px; color: var(--app-text-secondary); font-size: 11px; line-height: 1.5; }
.bug-feedback-confirmations input { display: grid; width: 14px; height: 14px; flex: 0 0 14px; appearance: none; place-items: center; margin-top: 2px; border: 1px solid var(--app-border); border-radius: 3px; background: var(--app-surface-bg); }
.bug-feedback-confirmations input:checked { border-color: #07b75b; background: #07b75b; }
.bug-feedback-confirmations input:checked::after { width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; content: ''; transform: translateY(-1px) rotate(45deg); }
.bug-feedback-confirmations input:focus-visible { outline: 2px solid rgba(7,183,91,.32); outline-offset: 2px; }
.bug-feedback-paste-zone { display: grid; gap: 7px; border: 1px dashed rgba(0,153,255,.48); border-radius: 8px; background: rgba(0,153,255,.05); padding: 10px; color: #007dcc; font-size: 11px; font-weight: 500; outline: none; }.bug-feedback-paste-zone:focus-within { border-color: #0099ff; box-shadow: 0 0 0 2px rgba(0,153,255,.12); }.bug-feedback-paste-zone textarea { background: var(--app-surface-bg) !important; color: var(--app-text-primary) !important; }
.bug-feedback-screenshots { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }.bug-feedback-screenshots figure { position: relative; margin: 0; overflow: hidden; border: 1px solid var(--app-border); border-radius: 7px; background: var(--setup-surface-soft); aspect-ratio: 16/10; }.bug-feedback-screenshots img { width: 100%; height: 100%; object-fit: cover; }.bug-feedback-screenshots button { position: absolute; top: 4px; right: 4px; display: grid; width: 22px; height: 22px; place-items: center; border-radius: 50%; background: rgba(0,0,0,.62); color: #fff; font-size: 15px; line-height: 1; }
.bug-feedback-success, .bug-feedback-required { margin: 0; border-radius: 8px; padding: 9px 11px; font-size: 12px; }.bug-feedback-success { background: rgba(7,183,91,.1); color: #087a40; }.bug-feedback-required { background: var(--setup-surface-soft); color: var(--app-text-secondary); }.bug-feedback-actions { display: flex; justify-content: flex-end; gap: 8px; }.bug-feedback-actions button { min-width: 112px; border-radius: 8px; padding: 9px 14px; font-size: 12px; font-weight: 600; }.bug-feedback-actions button:disabled { cursor: not-allowed; opacity: .5; }.bug-feedback-cancel { border: 1px solid var(--app-border); background: var(--app-surface-bg); color: var(--app-text-secondary); }.bug-feedback-send { display: inline-flex; align-items: center; justify-content: center; gap: 7px; border: 1px solid #07b75b; background: #07b75b; color: #fff; }.bug-feedback-send:hover:not(:disabled) { background: #069f50; }
@media (max-width:760px) { .bug-feedback { padding: 16px; }.bug-feedback-summary-row { grid-template-columns: 1fr; }.bug-feedback-actions button { flex: 1; } }
</style>
