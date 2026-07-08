<template>
  <div class="contacts-page h-screen flex overflow-hidden" style="background-color: var(--app-shell-bg)">
    <div class="flex-1 flex flex-col min-h-0" style="background-color: var(--app-shell-bg)">
      <div class="flex-1 min-h-0 overflow-hidden p-4">
        <div class="h-full grid grid-cols-1 lg:grid-cols-[460px_minmax(0,1fr)] gap-4">
          <div class="bg-white border border-gray-200 rounded-lg flex flex-col min-h-0 overflow-hidden">
            <div class="p-3 border-b border-gray-200" style="background-color: var(--app-surface-muted)">
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
              </div>
            </div>

            <div class="px-3 py-3 border-b border-gray-200 bg-white">
              <div class="grid grid-cols-3 gap-2">
                <label
                  v-for="card in contactFilterCards"
                  :key="card.key"
                  class="contact-type-filter-card"
                  :class="{ 'is-active': contactTypes[card.key] }"
                >
                  <input v-model="contactTypes[card.key]" type="checkbox" class="sr-only" />
                  <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      v-for="path in card.iconPaths"
                      :key="path"
                      :d="path"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="1.8"
                    />
                  </svg>
                  <span class="min-w-0 flex-1 truncate text-xs font-medium">{{ card.label }}</span>
                  <span class="text-xs tabular-nums font-semibold">{{ card.count }}</span>
                </label>
              </div>
              <div class="mt-2 text-right text-xs text-gray-500">总计 {{ counts.total }}</div>
            </div>

            <div class="flex-1 min-h-0 overflow-auto" @scroll.passive="onContactsScroll">
              <div v-if="loading" class="p-4 text-sm text-gray-500">加载中…</div>
              <div v-else-if="error" class="p-4 text-sm text-red-500 whitespace-pre-wrap">{{ error }}</div>
              <div v-else-if="contacts.length === 0" class="p-4 text-sm text-gray-500">暂无联系人</div>
              <div v-else>
                <div v-for="group in visibleGroupedContacts" :key="group.key">
                  <div class="px-3 py-1 text-xs font-semibold text-gray-500 bg-gray-50 border-b border-gray-100">
                    {{ group.key }}
                  </div>
                  <div
                    v-for="contact in group.items"
                    :key="contact.username"
                    class="px-3 py-2 border-b border-gray-100 flex items-center gap-3"
                  >
                    <div class="w-10 h-10 rounded-md overflow-hidden bg-gray-300 shrink-0" :class="{ 'privacy-blur': privacyMode }">
                      <img
                        v-if="contact.avatar && !avatarBroken[avatarBrokenKey(contact)]"
                        :src="contact.avatar"
                        :alt="contact.displayName"
                        class="w-full h-full object-cover"
                        loading="lazy"
                        decoding="async"
                        referrerpolicy="no-referrer"
                        @error="markAvatarBroken(contact)"
                      />
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
                    <div class="text-xs px-2 py-0.5 rounded" :class="typeBadgeClass(contact)">
                      {{ typeLabel(contact) }}
                    </div>
                  </div>
                </div>
                <button
                  v-if="visibleContacts.length < sortedContacts.length"
                  type="button"
                  class="w-full px-3 py-3 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                  @click="showMoreContacts"
                >
                  加载更多（{{ visibleContacts.length }} / {{ sortedContacts.length }}）
                </button>
              </div>
            </div>
          </div>

          <div class="contacts-export-panel w-full self-start">
            <section class="rounded-lg border border-[#e5e7eb] bg-white">
              <div class="border-b border-[#e5e7eb] px-4 py-3">
                <div class="text-[14px] font-medium text-[#111827]">导出联系人</div>
                <div class="mt-0.5 text-[12px] text-[#6b7280]">支持 JSON / CSV，导出范围由左侧分类控制。</div>
              </div>

              <div class="space-y-4 px-4 py-4">
                <div>
                  <div class="mb-2 text-[13px] font-medium text-[#111827]">导出格式</div>
                  <div class="grid grid-cols-2 gap-3">
                    <label
                      class="flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 transition"
                      :class="exportFormat === 'json' ? 'border-[#22c55e] bg-[#f0fdf4] text-[#047857]' : 'border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]'"
                    >
                      <input v-model="exportFormat" type="radio" value="json" class="sr-only" />
                      <span class="text-[13px] font-medium">JSON</span>
                      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="exportFormat === 'json' ? 'border-[#22c55e] bg-[#22c55e] text-white' : 'border-[#d1d5db] text-transparent'">
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                          <path fill-rule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.25 7.25a1 1 0 01-1.42 0L3.296 9.22a1 1 0 111.414-1.414l4.03 4.03 6.543-6.543a1 1 0 011.421 0z" clip-rule="evenodd" />
                        </svg>
                      </span>
                    </label>
                    <label
                      class="flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 transition"
                      :class="exportFormat === 'csv' ? 'border-[#22c55e] bg-[#f0fdf4] text-[#047857]' : 'border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]'"
                    >
                      <input v-model="exportFormat" type="radio" value="csv" class="sr-only" />
                      <span class="text-[13px] font-medium">CSV (Excel)</span>
                      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="exportFormat === 'csv' ? 'border-[#22c55e] bg-[#22c55e] text-white' : 'border-[#d1d5db] text-transparent'">
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                          <path fill-rule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.25 7.25a1 1 0 01-1.42 0L3.296 9.22a1 1 0 111.414-1.414l4.03 4.03 6.543-6.543a1 1 0 011.421 0z" clip-rule="evenodd" />
                        </svg>
                      </span>
                    </label>
                  </div>
                </div>

                <div>
                  <div class="mb-2 text-[13px] font-medium text-[#111827]">导出目录</div>
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <div class="min-w-0 flex-1 rounded-md border border-dashed px-3 py-2.5 text-[12px] leading-5" :class="exportFolder ? 'border-[#86efac] bg-[#f0fdf4] text-[#166534]' : 'border-[#d1d5db] bg-[#f9fafb] text-[#6b7280]'">
                      <div class="truncate" :title="exportFolder || '尚未选择导出目录'">{{ exportFolder || '尚未选择导出目录' }}</div>
                    </div>
                    <button
                      type="button"
                      class="inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md border border-[#d1d5db] bg-white px-3 py-2.5 text-[13px] font-medium text-[#111827] transition hover:bg-[#f9fafb]"
                      @click="chooseExportFolder"
                    >
                      选择目录
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  class="inline-flex w-full items-center justify-center gap-2 rounded-md px-4 py-2 text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-60"
                  :class="canExport && !exporting ? 'bg-[#07C160] text-white hover:bg-[#06ad56]' : 'bg-[#d1d5db] text-white'"
                  :disabled="!canExport || exporting"
                  @click="startExport"
                >
                  {{ exporting ? '导出中…' : '开始导出' }}
                </button>

                <div
                  v-if="exportMsg"
                  class="rounded-md border px-3 py-2.5 text-[13px] leading-5 whitespace-pre-wrap"
                  :class="exportOk ? 'border-[#bbf7d0] bg-[#f0fdf4] text-[#15803d]' : 'border-[#fecaca] bg-[#fef2f2] text-[#b91c1c]'"
                >
                  {{ exportMsg }}
                </div>
              </div>
            </section>
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
const { selectedAccount } = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const searchKeyword = ref('')

const contactTypes = reactive({
  friends: true,
  groups: false,
  officials: false,
  services: false,
  formerFriends: false,
  blocked: false,
})

const contacts = ref([])
const avatarBroken = reactive({})
const CONTACTS_RENDER_BATCH_SIZE = 80
const visibleContactLimit = ref(CONTACTS_RENDER_BATCH_SIZE)
const counts = reactive({
  friends: 0,
  groups: 0,
  officials: 0,
  services: 0,
  formerFriends: 0,
  blocked: 0,
  total: 0,
})

const loading = ref(false)
const error = ref('')

const exportFormat = ref('json')
const includeAvatarLink = ref(true)
const exportFolder = ref('')
const exportFolderHandle = ref(null)
const exporting = ref(false)
const exportMsg = ref('')
const exportOk = ref(false)

const avatarBrokenKey = (contact) => `${selectedAccount.value || ''}::${contact?.username || ''}`

const markAvatarBroken = (contact) => {
  const key = avatarBrokenKey(contact)
  if (key) avatarBroken[key] = true
}

const contactTypeIconPaths = {
  user: [
    'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    'M4.5 20a7.5 7.5 0 0 1 15 0',
  ],
  users: [
    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    'M2.5 20a6.5 6.5 0 0 1 13 0',
    'M17 11a3 3 0 1 0 0-6',
    'M17.5 20a5 5 0 0 0-3-4.6',
  ],
  message: [
    'M5 6.5h14v10H8l-3 3v-13Z',
  ],
  userX: [
    'M11 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    'M3.5 20a7.5 7.5 0 0 1 11.2-6.5',
    'M17 14l4 4',
    'M21 14l-4 4',
  ],
}

const contactFilterCards = computed(() => [
  { key: 'friends', label: '好友', count: counts.friends, iconPaths: contactTypeIconPaths.user },
  { key: 'groups', label: '群聊', count: counts.groups, iconPaths: contactTypeIconPaths.users },
  { key: 'officials', label: '公众号', count: counts.officials, iconPaths: contactTypeIconPaths.message },
  { key: 'services', label: '服务号', count: counts.services, iconPaths: contactTypeIconPaths.message },
  { key: 'formerFriends', label: '曾经的好友', count: counts.formerFriends, iconPaths: contactTypeIconPaths.userX },
  { key: 'blocked', label: '黑名单', count: counts.blocked, iconPaths: contactTypeIconPaths.userX },
])

const typeLabel = (contactOrType) => {
  const contact = typeof contactOrType === 'string' ? null : contactOrType
  const type = typeof contactOrType === 'string' ? contactOrType : contactOrType?.type
  if (type === 'friend') return '好友'
  if (type === 'group') return '群聊'
  if (type === 'official') {
    if (contact?.officialAccountKind === 'service') return '服务号'
    if (contact?.officialAccountKind === 'enterprise') return '企业号'
    return '公众号'
  }
  if (type === 'former_friend') return '曾经的好友'
  if (type === 'blocked') return '黑名单'
  return '其他'
}

const typeBadgeClass = (contactOrType) => {
  const contact = typeof contactOrType === 'string' ? null : contactOrType
  const type = typeof contactOrType === 'string' ? contactOrType : contactOrType?.type
  if (type === 'friend') return 'bg-blue-100 text-blue-700'
  if (type === 'group') return 'bg-green-100 text-green-700'
  if (type === 'official') {
    if (contact?.officialAccountKind === 'service') return 'bg-amber-100 text-amber-700'
    return 'bg-orange-100 text-orange-700'
  }
  if (type === 'former_friend') return 'bg-purple-100 text-purple-700'
  if (type === 'blocked') return 'bg-red-100 text-red-700'
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

const sortedContacts = computed(() => {
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

  return rows.map((row) => row.contact)
})

const groupContacts = (list) => {
  const groups = []
  for (const contact of Array.isArray(list) ? list : []) {
    const groupKey = normalizeContactGroupKey(contact?.pinyinInitial)
    const last = groups[groups.length - 1]
    if (!last || last.key !== groupKey) {
      groups.push({ key: groupKey, items: [contact] })
    } else {
      last.items.push(contact)
    }
  }
  return groups
}

const visibleContacts = computed(() => sortedContacts.value.slice(0, visibleContactLimit.value))

const visibleGroupedContacts = computed(() => groupContacts(visibleContacts.value))

const resetVisibleContacts = () => {
  visibleContactLimit.value = CONTACTS_RENDER_BATCH_SIZE
}

const showMoreContacts = () => {
  visibleContactLimit.value = Math.min(
    sortedContacts.value.length,
    visibleContactLimit.value + CONTACTS_RENDER_BATCH_SIZE,
  )
}

const onContactsScroll = (event) => {
  const el = event?.target
  if (!el || visibleContactLimit.value >= sortedContacts.value.length) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 240) {
    showMoreContacts()
  }
}

const isDesktopExportRuntime = () => {
  return !!(process.client && window?.wechatDesktop?.chooseDirectory)
}

const isWebDirectoryPickerSupported = () => {
  return !!(process.client && typeof window.showDirectoryPicker === 'function')
}

const hasSelectedContactTypes = computed(() => {
  return !!(
    contactTypes.friends ||
    contactTypes.groups ||
    contactTypes.officials ||
    contactTypes.services ||
    contactTypes.formerFriends ||
    contactTypes.blocked
  )
})

const buildContactIncludeParams = () => {
  return {
    include_friends: !!contactTypes.friends,
    include_groups: !!contactTypes.groups,
    include_officials: !!(contactTypes.officials || contactTypes.services),
    include_official_subscriptions: !!contactTypes.officials,
    include_official_services: !!contactTypes.services,
    include_former_friends: !!contactTypes.formerFriends,
    include_blocked: !!contactTypes.blocked,
  }
}

const buildContactTypePayload = () => {
  return {
    friends: !!contactTypes.friends,
    groups: !!contactTypes.groups,
    officials: !!(contactTypes.officials || contactTypes.services),
    official_subscriptions: !!contactTypes.officials,
    official_services: !!contactTypes.services,
    former_friends: !!contactTypes.formerFriends,
    blocked: !!contactTypes.blocked,
  }
}

const buildContactsLoadKey = () => JSON.stringify({
  account: String(selectedAccount.value || ''),
  keyword: String(searchKeyword.value || ''),
  ...buildContactIncludeParams(),
})

const canExport = computed(() => {
  const hasExportTarget = isDesktopExportRuntime()
    ? !!exportFolder.value
    : !!exportFolderHandle.value
  return !!selectedAccount.value && hasExportTarget && hasSelectedContactTypes.value
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

const numberFrom = (...values) => {
  for (const value of values) {
    const n = Number(value)
    if (Number.isFinite(n)) return n
  }
  return 0
}

const resetCounts = () => {
  counts.friends = 0
  counts.groups = 0
  counts.officials = 0
  counts.services = 0
  counts.formerFriends = 0
  counts.blocked = 0
  counts.total = 0
}

const applyCounts = (source = {}) => {
  counts.friends = numberFrom(source.friends, source.private)
  counts.groups = numberFrom(source.groups, source.group)
  counts.officials = numberFrom(source.officialSubscriptions, source.official_subscription, source.officials)
  counts.services = numberFrom(source.services, source.officialServices, source.official_service)
  counts.formerFriends = numberFrom(source.formerFriends, source.former_friends, source.former_friend)
  counts.blocked = numberFrom(source.blocked)
  counts.total = numberFrom(
    source.total,
    counts.friends + counts.groups + counts.officials + counts.services + counts.formerFriends + counts.blocked,
  )
}

const buildExportContactsPayload = async () => {
  const resp = await api.listChatContacts({
    account: selectedAccount.value,
    source: 'auto',
    keyword: searchKeyword.value || '',
    ...buildContactIncludeParams(),
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
      officialAccountKind: String(item?.officialAccountKind || ''),
      officialAccountType: item?.officialAccountType == null ? '' : String(item?.officialAccountType),
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
          ...buildContactTypePayload(),
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
      ['officialAccountKind', '公众号类型'],
      ['officialAccountType', '公众号类型码'],
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

let contactsLoadRequestId = 0
let contactsLoadInFlightKey = ''
let contactsLoadInFlightPromise = null
let lastContactsLoadKey = ''

const loadContacts = async (options = {}) => {
  if (!selectedAccount.value) {
    contactsLoadRequestId += 1
    contactsLoadInFlightPromise = null
    contactsLoadInFlightKey = ''
    contacts.value = []
    resetVisibleContacts()
    resetCounts()
    lastContactsLoadKey = ''
    return
  }

  const loadKey = buildContactsLoadKey()
  if (!options.force && contactsLoadInFlightPromise && contactsLoadInFlightKey === loadKey) {
    return contactsLoadInFlightPromise.catch(() => {})
  }
  if (!options.force && lastContactsLoadKey === loadKey) {
    return
  }

  const requestId = ++contactsLoadRequestId
  loading.value = true
  error.value = ''

  const promise = (async () => {
    const resp = await api.listChatContacts({
      account: selectedAccount.value,
      source: 'auto',
      keyword: searchKeyword.value || '',
      ...buildContactIncludeParams(),
    })
    if (requestId !== contactsLoadRequestId) return
    contacts.value = Array.isArray(resp?.contacts) ? resp.contacts : []
    resetVisibleContacts()
    applyCounts(resp?.counts || {})
    lastContactsLoadKey = loadKey
  })()

  contactsLoadInFlightKey = loadKey
  contactsLoadInFlightPromise = promise

  try {
    await promise
  } catch (e) {
    if (requestId === contactsLoadRequestId) {
      contacts.value = []
      resetVisibleContacts()
      resetCounts()
      error.value = e?.message || '加载联系人失败'
    }
  } finally {
    if (contactsLoadInFlightPromise === promise) {
      contactsLoadInFlightPromise = null
      contactsLoadInFlightKey = ''
    }
    if (requestId === contactsLoadRequestId) {
      loading.value = false
    }
  }
}

let keywordTimer = null
watch(() => searchKeyword.value, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => {
    void loadContacts()
  }, 250)
})

watch(() => [
  selectedAccount.value,
  contactTypes.friends,
  contactTypes.groups,
  contactTypes.officials,
  contactTypes.services,
  contactTypes.formerFriends,
  contactTypes.blocked,
], () => {
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
    exportMsg.value = '请先选择账号、导出目录，并在左侧至少勾选一种联系人类型'
    return
  }

  exporting.value = true
  try {
    const resp = isDesktopExportRuntime()
      ? await api.exportChatContacts({
          account: selectedAccount.value,
          source: 'auto',
          output_dir: exportFolder.value,
          format: exportFormat.value,
          include_avatar_link: includeAvatarLink.value,
          keyword: searchKeyword.value || '',
          contact_types: buildContactTypePayload()
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

<style scoped>
.contact-type-filter-card {
  min-width: 0;
  height: 38px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  background: var(--app-surface-bg);
  color: var(--app-text-secondary);
  padding: 0 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.contact-type-filter-card:hover {
  border-color: #e5e7eb;
  background: #f9fafb;
  color: var(--app-text-primary);
}

.contact-type-filter-card.is-active {
  border-color: #22c55e;
  background: #f0fdf4;
  color: #047857;
  box-shadow: none;
}

.contact-type-filter-card.is-active:hover {
  border-color: #22c55e;
  background: #f0fdf4;
  color: #047857;
}
</style>
