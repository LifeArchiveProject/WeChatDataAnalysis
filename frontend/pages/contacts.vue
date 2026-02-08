<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <div class="border-r border-gray-200 flex flex-col" style="background-color: #e8e7e7; width: 60px; min-width: 60px; max-width: 60px">
      <div class="flex-1 flex flex-col justify-start pt-0 gap-0">
        <div class="w-full h-[60px] flex items-center justify-center">
          <div class="w-[40px] h-[40px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">
            <img v-if="selfAvatarUrl" :src="selfAvatarUrl" alt="avatar" class="w-full h-full object-cover" />
            <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold" style="background-color: #4B5563">我</div>
          </div>
        </div>

        <div class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group" title="聊天" @click="goChat">
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isChatRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z" />
              </svg>
            </div>
          </div>
        </div>

        <div class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group" title="朋友圈" @click="goSns">
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isSnsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="14.31" y1="8" x2="20.05" y2="17.94" />
                <line x1="9.69" y1="8" x2="21.17" y2="8" />
                <line x1="7.38" y1="12" x2="13.12" y2="2.06" />
                <line x1="9.69" y1="16" x2="3.95" y2="6.06" />
                <line x1="14.31" y1="16" x2="2.83" y2="16" />
                <line x1="16.62" y1="12" x2="10.88" y2="21.94" />
              </svg>
            </div>
          </div>
        </div>

        <div class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group" title="联系人">
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)] text-[#07b75b]">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
                <circle cx="10" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
          </div>
        </div>

        <div class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group" title="年度总结" @click="goWrapped">
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isWrappedRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="4" y="4" width="16" height="16" rx="2" />
                <path d="M8 16v-5" />
                <path d="M12 16v-8" />
                <path d="M16 16v-3" />
              </svg>
            </div>
          </div>
        </div>

        <div class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group" @click="privacyMode = !privacyMode" :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'">
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
            <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="privacyMode ? 'text-[#07b75b]' : 'text-[#5d5d5d]'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path v-if="privacyMode" stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
              <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <DesktopTitleBar />
      <div class="flex-1 min-h-0 overflow-hidden p-4">
        <div class="h-full grid grid-cols-1 lg:grid-cols-[400px_minmax(0,1fr)] gap-4">
          <div class="bg-white border border-gray-200 rounded-lg flex flex-col min-h-0 overflow-hidden">
            <div class="p-3 border-b border-gray-200" style="background-color: #F7F7F7">
              <div class="flex items-center gap-2">
                <div class="contact-search-wrapper flex-1" :class="{ 'privacy-blur': privacyMode }">
                  <svg class="contact-search-icon" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
                  </svg>
                  <input v-model="searchKeyword" class="contact-search-input" type="text" placeholder="搜索联系人" />
                  <button v-if="searchKeyword" type="button" class="contact-search-clear" @click="searchKeyword = ''">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <select v-if="availableAccounts.length > 1" v-model="selectedAccount" class="account-select">
                  <option v-for="acc in availableAccounts" :key="acc" :value="acc">{{ acc }}</option>
                </select>
              </div>
            </div>

            <div class="px-3 py-2 border-b border-gray-200 bg-white flex items-center gap-4 text-sm">
              <label class="flex items-center gap-2">
                <input v-model="contactTypes.friends" type="checkbox" />
                <span>好友 {{ counts.friends }}</span>
              </label>
              <label class="flex items-center gap-2">
                <input v-model="contactTypes.groups" type="checkbox" />
                <span>群聊 {{ counts.groups }}</span>
              </label>
              <label class="flex items-center gap-2">
                <input v-model="contactTypes.officials" type="checkbox" />
                <span>公众号 {{ counts.officials }}</span>
              </label>
              <span class="ml-auto text-gray-500">总计 {{ counts.total }}</span>
            </div>

            <div class="flex-1 min-h-0 overflow-auto">
              <div v-if="loading" class="p-4 text-sm text-gray-500">加载中…</div>
              <div v-else-if="error" class="p-4 text-sm text-red-500 whitespace-pre-wrap">{{ error }}</div>
              <div v-else-if="contacts.length === 0" class="p-4 text-sm text-gray-500">暂无联系人</div>
              <div v-else>
                <div
                  v-for="contact in contacts"
                  :key="contact.username"
                  class="px-3 py-2 border-b border-gray-100 flex items-center gap-3"
                >
                  <div class="w-10 h-10 rounded-md overflow-hidden bg-gray-300 shrink-0" :class="{ 'privacy-blur': privacyMode }">
                    <img v-if="contact.avatar" :src="contact.avatar" :alt="contact.displayName" class="w-full h-full object-cover" referrerpolicy="no-referrer" />
                    <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold" style="background-color:#4B5563">{{ contact.displayName?.charAt(0) || '?' }}</div>
                  </div>
                  <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                    <div class="text-sm text-gray-900 truncate">{{ contact.displayName }}</div>
                    <div class="text-xs text-gray-500 truncate">{{ contact.username }}</div>
                    <div class="text-[11px] text-gray-500 truncate" v-if="contact.type !== 'group' && (contact.region || contact.source)">
                      <span v-if="contact.region">地区：{{ contact.region }}</span>
                      <span v-if="contact.region && contact.source"> · </span>
                      <span
                        v-if="contact.source"
                        :title="contact.sourceScene != null ? `来源场景码：${contact.sourceScene}` : ''"
                      >来源：{{ contact.source }}</span>
                    </div>
                  </div>
                  <div class="text-xs px-2 py-0.5 rounded" :class="typeBadgeClass(contact.type)">
                    {{ typeLabel(contact.type) }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="bg-white border border-gray-200 rounded-lg p-4 flex flex-col gap-3">
            <div>
              <div class="text-base font-medium text-gray-900">导出联系人</div>
              <div class="text-xs text-gray-500 mt-1">支持 JSON / CSV，默认包含头像链接</div>
            </div>

            <div class="space-y-2 text-sm">
              <div class="font-medium text-gray-800">导出格式</div>
              <label class="flex items-center gap-2"><input v-model="exportFormat" type="radio" value="json" /> JSON</label>
              <label class="flex items-center gap-2"><input v-model="exportFormat" type="radio" value="csv" /> CSV (Excel)</label>
            </div>

            <div class="space-y-2 text-sm">
              <div class="font-medium text-gray-800">导出类型（多选）</div>
              <label class="flex items-center gap-2"><input v-model="exportTypes.friends" type="checkbox" /> 好友</label>
              <label class="flex items-center gap-2"><input v-model="exportTypes.groups" type="checkbox" /> 群聊</label>
              <label class="flex items-center gap-2"><input v-model="exportTypes.officials" type="checkbox" /> 公众号</label>
            </div>

            <label class="flex items-center gap-2 text-sm">
              <input v-model="includeAvatarLink" type="checkbox" />
              导出头像链接
            </label>

            <div class="space-y-2 text-sm">
              <div class="font-medium text-gray-800">导出目录</div>
              <div class="px-2 py-2 rounded border border-gray-200 bg-gray-50 text-xs break-all min-h-[38px]">{{ exportFolder || '未选择' }}</div>
              <button type="button" class="w-full px-3 py-2 rounded border border-gray-200 hover:bg-gray-50" @click="chooseExportFolder">选择文件夹</button>
            </div>

            <button
              type="button"
              class="mt-2 w-full px-3 py-2 rounded text-white"
              :class="canExport && !exporting ? 'bg-[#03C160] hover:bg-[#02ad56]' : 'bg-gray-300 cursor-not-allowed'"
              :disabled="!canExport || exporting"
              @click="startExport"
            >
              {{ exporting ? '导出中…' : '开始导出' }}
            </button>

            <div v-if="exportMsg" class="text-xs whitespace-pre-wrap" :class="exportOk ? 'text-green-600' : 'text-red-500'">{{ exportMsg }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
useHead({ title: '联系人 - 微信数据分析助手' })

const route = useRoute()
const api = useApi()

const isChatRoute = computed(() => route.path?.startsWith('/chat'))
const isSnsRoute = computed(() => route.path?.startsWith('/sns'))
const isWrappedRoute = computed(() => route.path?.startsWith('/wrapped'))

const PRIVACY_MODE_KEY = 'ui.privacy_mode'
const privacyMode = ref(false)
onMounted(() => {
  if (!process.client) return
  try {
    privacyMode.value = localStorage.getItem(PRIVACY_MODE_KEY) === '1'
  } catch {}
})
watch(() => privacyMode.value, (v) => {
  if (!process.client) return
  try {
    localStorage.setItem(PRIVACY_MODE_KEY, v ? '1' : '0')
  } catch {}
})

const sidebarMediaBase = process.client ? 'http://localhost:8000' : ''

const availableAccounts = ref([])
const selectedAccount = ref(null)
const searchKeyword = ref('')

const contactTypes = reactive({
  friends: true,
  groups: true,
  officials: true,
})

const contacts = ref([])
const counts = reactive({
  friends: 0,
  groups: 0,
  officials: 0,
  total: 0,
})

const loading = ref(false)
const error = ref('')

const exportFormat = ref('json')
const includeAvatarLink = ref(true)
const exportTypes = reactive({
  friends: true,
  groups: true,
  officials: true,
})
const exportFolder = ref('')
const exportFolderHandle = ref(null)
const exporting = ref(false)
const exportMsg = ref('')
const exportOk = ref(false)

const selfAvatarUrl = computed(() => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return ''
  return `${sidebarMediaBase}/api/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(acc)}`
})

const typeLabel = (type) => {
  if (type === 'friend') return '好友'
  if (type === 'group') return '群聊'
  if (type === 'official') return '公众号'
  return '其他'
}

const typeBadgeClass = (type) => {
  if (type === 'friend') return 'bg-blue-100 text-blue-700'
  if (type === 'group') return 'bg-green-100 text-green-700'
  if (type === 'official') return 'bg-orange-100 text-orange-700'
  return 'bg-gray-100 text-gray-600'
}

const goChat = async () => {
  await navigateTo('/chat')
}

const goSns = async () => {
  await navigateTo('/sns')
}

const goWrapped = async () => {
  await navigateTo('/wrapped')
}

const isDesktopExportRuntime = () => {
  return !!(process.client && window?.wechatDesktop?.chooseDirectory)
}

const isWebDirectoryPickerSupported = () => {
  return !!(process.client && typeof window.showDirectoryPicker === 'function')
}

const canExport = computed(() => {
  const hasExportTarget = isDesktopExportRuntime()
    ? !!exportFolder.value
    : !!exportFolderHandle.value
  return !!selectedAccount.value && hasExportTarget && (exportTypes.friends || exportTypes.groups || exportTypes.officials)
})

const safeExportPart = (value) => {
  const cleaned = String(value || '').trim().replace(/[^0-9A-Za-z._-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
  return cleaned || 'account'
}

const buildExportTimestamp = () => {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

const escapeCsvCell = (value) => {
  const text = String(value == null ? '' : value)
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

const buildExportContactsPayload = async () => {
  const resp = await api.listChatContacts({
    account: selectedAccount.value,
    keyword: searchKeyword.value || '',
    include_friends: exportTypes.friends,
    include_groups: exportTypes.groups,
    include_officials: exportTypes.officials,
  })
  const contactsList = Array.isArray(resp?.contacts) ? resp.contacts : []
  const exportContacts = contactsList.map((item) => {
    const row = {
      username: String(item?.username || ''),
      displayName: String(item?.displayName || ''),
      remark: String(item?.remark || ''),
      nickname: String(item?.nickname || ''),
      alias: String(item?.alias || ''),
      type: String(item?.type || ''),
      region: String(item?.region || ''),
      country: String(item?.country || ''),
      province: String(item?.province || ''),
      city: String(item?.city || ''),
      source: String(item?.source || ''),
      sourceScene: item?.sourceScene == null ? '' : String(item?.sourceScene),
    }
    if (includeAvatarLink.value) {
      row.avatarLink = String(item?.avatarLink || '')
    }
    return row
  })

  return {
    account: String(selectedAccount.value || ''),
    count: exportContacts.length,
    contacts: exportContacts,
  }
}

const writeWebExportFile = async ({ fileName, content }) => {
  if (!exportFolderHandle.value || typeof exportFolderHandle.value.getFileHandle !== 'function') {
    throw new Error('未选择浏览器导出目录')
  }
  const fileHandle = await exportFolderHandle.value.getFileHandle(fileName, { create: true })
  const writable = await fileHandle.createWritable()
  await writable.write(content)
  await writable.close()
}

const exportContactsInWeb = async () => {
  const fmt = String(exportFormat.value || 'json').toLowerCase()
  if (fmt !== 'json' && fmt !== 'csv') {
    throw new Error('网页端仅支持 JSON/CSV 导出')
  }
  if (!exportFolderHandle.value) {
    throw new Error('请先选择导出目录')
  }

  const payload = await buildExportContactsPayload()
  const fileName = `contacts_${safeExportPart(payload.account)}_${buildExportTimestamp()}.${fmt}`

  if (fmt === 'json') {
    const jsonPayload = {
      exportedAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      account: payload.account,
      count: payload.count,
      filters: {
        keyword: String(searchKeyword.value || ''),
        contactTypes: {
          friends: !!exportTypes.friends,
          groups: !!exportTypes.groups,
          officials: !!exportTypes.officials,
        },
        includeAvatarLink: !!includeAvatarLink.value,
      },
      contacts: payload.contacts,
    }
    await writeWebExportFile({ fileName, content: JSON.stringify(jsonPayload, null, 2) })
  } else {
    const columns = [
      ['username', '用户名'],
      ['displayName', '显示名称'],
      ['remark', '备注'],
      ['nickname', '昵称'],
      ['alias', '微信号'],
      ['type', '类型'],
      ['region', '地区'],
      ['country', '国家/地区码'],
      ['province', '省份'],
      ['city', '城市'],
      ['source', '来源'],
      ['sourceScene', '来源场景码'],
    ]
    if (includeAvatarLink.value) {
      columns.push(['avatarLink', '头像链接'])
    }
    const lines = [columns.map(([, label]) => escapeCsvCell(label)).join(',')]
    for (const row of payload.contacts) {
      lines.push(columns.map(([key]) => escapeCsvCell(row[key])).join(','))
    }
    await writeWebExportFile({ fileName, content: `\uFEFF${lines.join('\n')}` })
  }

  return {
    count: payload.count,
    outputPath: `${exportFolder.value}/${fileName}`,
  }
}

const loadAccounts = async () => {
  try {
    const resp = await api.listChatAccounts()
    const accounts = resp?.accounts || []
    availableAccounts.value = accounts
    selectedAccount.value = selectedAccount.value || resp?.default_account || accounts[0] || null
  } catch (e) {
    availableAccounts.value = []
    selectedAccount.value = null
  }
}

const loadContacts = async () => {
  if (!selectedAccount.value) {
    contacts.value = []
    counts.friends = 0
    counts.groups = 0
    counts.officials = 0
    counts.total = 0
    return
  }
  loading.value = true
  error.value = ''
  try {
    const resp = await api.listChatContacts({
      account: selectedAccount.value,
      keyword: searchKeyword.value || '',
      include_friends: contactTypes.friends,
      include_groups: contactTypes.groups,
      include_officials: contactTypes.officials,
    })
    contacts.value = Array.isArray(resp?.contacts) ? resp.contacts : []
    counts.friends = Number(resp?.counts?.friends || 0)
    counts.groups = Number(resp?.counts?.groups || 0)
    counts.officials = Number(resp?.counts?.officials || 0)
    counts.total = Number(resp?.counts?.total || contacts.value.length)
  } catch (e) {
    contacts.value = []
    error.value = e?.message || '加载联系人失败'
  } finally {
    loading.value = false
  }
}

let keywordTimer = null
watch(() => searchKeyword.value, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => {
    void loadContacts()
  }, 250)
})

watch(() => [selectedAccount.value, contactTypes.friends, contactTypes.groups, contactTypes.officials], () => {
  void loadContacts()
})

const chooseExportFolder = async () => {
  exportMsg.value = ''
  exportOk.value = false
  try {
    if (!process.client) {
      exportMsg.value = '当前环境不支持选择导出目录'
      return
    }

    if (isDesktopExportRuntime()) {
      const result = await window.wechatDesktop.chooseDirectory({ title: '选择导出目录' })
      if (result && !result.canceled && Array.isArray(result.filePaths) && result.filePaths.length > 0) {
        exportFolder.value = String(result.filePaths[0] || '')
        exportFolderHandle.value = null
      }
      return
    }

    if (isWebDirectoryPickerSupported()) {
      const handle = await window.showDirectoryPicker()
      if (handle) {
        exportFolderHandle.value = handle
        exportFolder.value = `浏览器目录：${String(handle.name || '已选择')}`
      }
      return
    }

    exportMsg.value = '当前浏览器不支持目录选择，请使用桌面端或 Chromium 新版浏览器'
  } catch (e) {
    exportMsg.value = e?.message || '选择文件夹失败'
    exportOk.value = false
  }
}

const startExport = async () => {
  exportMsg.value = ''
  exportOk.value = false

  if (!canExport.value) {
    exportMsg.value = '请先选择账号、导出目录，并至少勾选一种联系人类型'
    return
  }

  exporting.value = true
  try {
    const resp = isDesktopExportRuntime()
      ? await api.exportChatContacts({
          account: selectedAccount.value,
          output_dir: exportFolder.value,
          format: exportFormat.value,
          include_avatar_link: includeAvatarLink.value,
          keyword: searchKeyword.value || '',
          contact_types: {
            friends: exportTypes.friends,
            groups: exportTypes.groups,
            officials: exportTypes.officials,
          }
        })
      : await exportContactsInWeb()
    exportOk.value = true
    exportMsg.value = `导出成功：${resp?.outputPath || ''}\n共 ${Number(resp?.count || 0)} 个联系人`
  } catch (e) {
    exportOk.value = false
    exportMsg.value = e?.message || '导出失败'
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await loadAccounts()
  await loadContacts()
})
</script>

<style scoped>
.privacy-blur {
  filter: blur(9px);
  transition: filter 0.2s ease;
}

.privacy-blur:hover {
  filter: none;
}
</style>
