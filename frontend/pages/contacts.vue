<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
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
                <div v-for="group in groupedContacts" :key="group.key">
                  <div class="px-3 py-1 text-xs font-semibold text-gray-500 bg-gray-50 border-b border-gray-100">
                    {{ group.key }}
                  </div>
                  <div
                    v-for="contact in group.items"
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
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

useHead({ title: '联系人 - 微信数据分析助手' })

const api = useApi()

const chatAccounts = useChatAccountsStore()
const { accounts: availableAccounts, selectedAccount } = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

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

const normalizeContactGroupKey = (value) => {
  const key = String(value || '').trim().toUpperCase()
  if (key.length === 1 && key >= 'A' && key <= 'Z') return key
  return '#'
}

const buildContactSortKey = (contact) => {
  const pinyinKey = String(contact?.pinyinKey || '').trim().toLowerCase()
  if (pinyinKey) return pinyinKey
  const nameKey = String(contact?.displayName || '').trim().toLowerCase()
  if (nameKey) return nameKey
  return String(contact?.username || '').trim().toLowerCase()
}

const groupedContacts = computed(() => {
  const list = Array.isArray(contacts.value) ? contacts.value : []
  const rows = list.map((contact) => {
    return {
      contact,
      groupKey: normalizeContactGroupKey(contact?.pinyinInitial),
      sortKey: buildContactSortKey(contact),
      usernameKey: String(contact?.username || '').trim().toLowerCase(),
    }
  })

  rows.sort((a, b) => {
    if (a.groupKey !== b.groupKey) {
      if (a.groupKey === '#') return 1
      if (b.groupKey === '#') return -1
      return a.groupKey.localeCompare(b.groupKey)
    }
    const cmpKey = a.sortKey.localeCompare(b.sortKey)
    if (cmpKey !== 0) return cmpKey
    return a.usernameKey.localeCompare(b.usernameKey)
  })

  const groups = []
  for (const row of rows) {
    const last = groups[groups.length - 1]
    if (!last || last.key !== row.groupKey) {
      groups.push({ key: row.groupKey, items: [row.contact] })
    } else {
      last.items.push(row.contact)
    }
  }
  return groups
})

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
  await chatAccounts.ensureLoaded({ force: true })
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
  privacyStore.init()
  await loadAccounts()
  await loadContacts()
})
</script>
