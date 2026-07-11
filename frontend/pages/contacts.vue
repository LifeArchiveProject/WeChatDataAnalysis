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

          <div class="contacts-export-panel h-full min-h-0 w-full space-y-3 overflow-y-auto pr-1">
            <section class="rounded-lg border border-[#e5e7eb] bg-white">
              <div class="flex items-center justify-between gap-3 border-b border-[#e5e7eb] px-4 py-2.5">
                <div>
                  <div class="text-[14px] font-medium text-[#111827]">好友验证</div>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="flex h-8 w-8 items-center justify-center rounded-md border border-[#e5e7eb] bg-white text-[#4b5563] transition hover:border-[#86efac] hover:bg-[#f0fdf4] hover:text-[#047857]"
                    title="导出好友验证"
                    aria-label="导出好友验证"
                    @click="friendVerificationExportOpen = true"
                  >
                    <i class="fa-solid fa-file-export" aria-hidden="true"></i>
                  </button>
                  <div class="rounded-full bg-[#f0fdf4] px-2.5 py-1 text-[12px] font-semibold text-[#047857]">
                    {{ friendVerificationTotal }}
                  </div>
                </div>
              </div>

              <div class="space-y-2.5 px-4 py-3">
                <div class="relative">
                  <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9ca3af]" fill="none" stroke="currentColor" viewBox="0 0 16 16" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.333 12.667A5.333 5.333 0 1 0 7.333 2a5.333 5.333 0 0 0 0 10.667ZM14 14l-2.9-2.9" />
                  </svg>
                  <input
                    v-model="friendVerificationKeyword"
                    type="text"
                    class="w-full rounded-md border border-[#e5e7eb] bg-white py-1.5 pl-9 pr-9 text-[13px] text-[#111827] outline-none transition placeholder:text-[#9ca3af] focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15"
                    placeholder="搜索验证内容、用户名、备注"
                  />
                  <button
                    v-if="friendVerificationKeyword"
                    type="button"
                    class="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-[#9ca3af] transition hover:bg-[#f3f4f6] hover:text-[#4b5563]"
                    title="清空"
                    @click="friendVerificationKeyword = ''"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div v-if="friendVerificationLoading && !friendVerifications.length" class="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-3 py-4 text-[13px] text-[#6b7280]">
                  正在加载好友验证记录…
                </div>
                <div v-else-if="friendVerificationError" class="rounded-md border border-[#fecaca] bg-[#fef2f2] px-3 py-3 text-[13px] leading-5 text-[#b91c1c]">
                  {{ friendVerificationError }}
                </div>
                <div v-else-if="!friendVerifications.length" class="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-3 py-4 text-[13px] text-[#6b7280]">
                  暂无好友验证记录
                </div>
                <div v-else class="max-h-[340px] space-y-1.5 overflow-y-auto pr-1">
                  <article
                    v-for="item in friendVerifications"
                    :key="`${item.timestamp}-${item.userName}-${item.type}-${item.scene}`"
                    class="cursor-pointer rounded-md border border-[#eef2f7] bg-white px-3 py-2 transition hover:border-[#dbeafe] hover:bg-[#fbfdff]"
                    title="点击跳转到会话"
                    @click="openChatByUsername(item.userName)"
                  >
                    <div class="flex items-start gap-3">
                      <div class="h-9 w-9 shrink-0 overflow-hidden rounded-md bg-[#e5e7eb]" :class="{ 'privacy-blur': privacyMode }">
                        <img
                          v-if="identityAvatar(friendVerificationContact(item)) && !avatarBroken[avatarBrokenKey(friendVerificationContact(item))]"
                          :src="identityAvatar(friendVerificationContact(item))"
                          :alt="friendVerificationDisplayName(item)"
                          class="h-full w-full object-cover"
                          loading="lazy"
                          decoding="async"
                          referrerpolicy="no-referrer"
                          @error="markAvatarBroken(friendVerificationContact(item))"
                        />
                        <div v-else class="flex h-full w-full items-center justify-center bg-[#07C160] text-xs font-bold text-white">
                          {{ identityFallback(friendVerificationDisplayName(item), friendVerificationContact(item)?.isGroup) }}
                        </div>
                      </div>
                      <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                        <div class="flex items-start justify-between gap-3">
                          <div class="min-w-0 flex-1">
                            <div class="truncate text-[13px] font-medium text-[#111827]" :title="friendVerificationRawTitle(item)">
                              {{ friendVerificationDisplayName(item) }}
                            </div>
                            <div class="mt-0.5 truncate text-[12px] text-[#6b7280]">
                              {{ item.content || item.remark || '（无验证内容）' }}
                            </div>
                          </div>
                          <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="item.isSender ? 'bg-[#eff6ff] text-[#1d4ed8]' : 'bg-[#f0fdf4] text-[#047857]'">
                            {{ item.isSender ? '我发起' : '对方发起' }}<span v-if="item.timeText" class="ml-1 font-normal opacity-75">{{ item.timeText }}</span>
                          </span>
                        </div>
                      </div>
                    </div>
                  </article>

                  <button
                    v-if="friendVerificationHasMore"
                    type="button"
                    class="w-full rounded-md border border-[#e5e7eb] bg-white px-3 py-2 text-[12px] font-medium text-[#4b5563] transition hover:border-[#bbf7d0] hover:bg-[#f0fdf4] hover:text-[#047857] disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="friendVerificationLoading"
                    @click="loadMoreFriendVerifications"
                  >
                    {{ friendVerificationLoading ? '加载中…' : `加载更多（${friendVerifications.length} / ${friendVerificationTotal}）` }}
                  </button>
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-[#e5e7eb] bg-white">
              <div class="border-b border-[#e5e7eb] px-4 py-3">
                <div class="text-[14px] font-medium text-[#111827]">导出联系人</div>
                <div class="mt-0.5 text-[12px] text-[#6b7280]">支持 HTML / JSON / TXT / Excel，导出范围由左侧分类控制。</div>
              </div>

              <div class="space-y-4 px-4 py-4">
                <div>
                  <div class="mb-2 text-[13px] font-medium text-[#111827]">导出格式</div>
                  <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <label
                      class="flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 transition"
                      :class="exportFormat === 'html' ? 'border-[#22c55e] bg-[#f0fdf4] text-[#047857]' : 'border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]'"
                    >
                      <input v-model="exportFormat" type="radio" value="html" class="sr-only" />
                      <span class="text-[13px] font-medium">HTML</span>
                      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="exportFormat === 'html' ? 'border-[#22c55e] bg-[#22c55e] text-white' : 'border-[#d1d5db] text-transparent'">
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                          <path fill-rule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.25 7.25a1 1 0 01-1.42 0L3.296 9.22a1 1 0 111.414-1.414l4.03 4.03 6.543-6.543a1 1 0 011.421 0z" clip-rule="evenodd" />
                        </svg>
                      </span>
                    </label>
                    <label
                      class="flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 transition"
                      :class="exportFormat === 'json' ? 'border-[#22c55e] bg-[#f0fdf4] text-[#047857]' : 'border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]'"
                    >
                      <input v-model="exportFormat" type="radio" value="json" class="sr-only" />
                      <span class="text-[13px] font-medium">JSON</span>
                      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="exportFormat === 'json' ? 'border-[#22c55e] bg-[#22c55e] text-white' : 'border-[#d1d5db] text-transparent'">
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.25 7.25a1 1 0 01-1.42 0L3.296 9.22a1 1 0 111.414-1.414l4.03 4.03 6.543-6.543a1 1 0 011.421 0z" clip-rule="evenodd" /></svg>
                      </span>
                    </label>
                    <label
                      class="flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 transition"
                      :class="exportFormat === 'txt' ? 'border-[#22c55e] bg-[#f0fdf4] text-[#047857]' : 'border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]'"
                    >
                      <input v-model="exportFormat" type="radio" value="txt" class="sr-only" />
                      <span class="text-[13px] font-medium">TXT</span>
                      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="exportFormat === 'txt' ? 'border-[#22c55e] bg-[#22c55e] text-white' : 'border-[#d1d5db] text-transparent'">
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.25 7.25a1 1 0 111.414-1.414l4.03 4.03 6.543-6.543a1 1 0 011.421 0z" clip-rule="evenodd" /></svg>
                      </span>
                    </label>
                    <label
                      class="flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 transition"
                      :class="exportFormat === 'excel' ? 'border-[#22c55e] bg-[#f0fdf4] text-[#047857]' : 'border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]'"
                    >
                      <input v-model="exportFormat" type="radio" value="excel" class="sr-only" />
                      <span class="text-[13px] font-medium">Excel</span>
                      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="exportFormat === 'excel' ? 'border-[#22c55e] bg-[#22c55e] text-white' : 'border-[#d1d5db] text-transparent'">
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.25 7.25a1 1 0 01-1.42 0L3.296 9.22a1 1 0 111.414-1.414l4.03 4.03 6.543-6.543a1 1 0 011.421 0z" clip-rule="evenodd" /></svg>
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
    <RecordExportDialog
      :open="friendVerificationExportOpen"
      dataset="friend-verifications"
      title="好友验证"
      :account="selectedAccount || ''"
      :query="friendVerificationKeyword"
      :type-options="friendVerificationExportTypes"
      @close="friendVerificationExportOpen = false"
    />
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { createXlsxBlob } from '~/lib/xlsx-export'
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

const friendVerificationKeyword = ref('')
const friendVerifications = ref([])
const friendVerificationTotal = ref(0)
const friendVerificationExportOpen = ref(false)
const friendVerificationExportTypes = [
  { value: 'incoming', label: '对方发起', icon: 'fa-arrow-down' },
  { value: 'outgoing', label: '我发起', icon: 'fa-arrow-up' },
]
const friendVerificationHasMore = ref(false)
const friendVerificationLoading = ref(false)
const friendVerificationError = ref('')
const FRIEND_VERIFICATION_PAGE_SIZE = 20

const avatarBrokenKey = (contact) => `${selectedAccount.value || ''}::${contact?.username || ''}`

const markAvatarBroken = (contact) => {
  const key = avatarBrokenKey(contact)
  if (key) avatarBroken[key] = true
}

const looksLikeRawId = (value) => {
  const text = String(value || '').trim()
  return !!(
    text.startsWith('wxid_') ||
    text.endsWith('@chatroom') ||
    /^\d{5,}@chatroom$/i.test(text)
  )
}

const identityDisplayName = (contact, fallback = '未知用户') => {
  const c = contact && typeof contact === 'object' ? contact : {}
  const rawUsername = String(c.username || '').trim()
  const candidates = [c.displayName, c.name, c.nickname, c.remark]
  for (const value of candidates) {
    const text = String(value || '').trim()
    if (!text) continue
    if (text !== rawUsername && !looksLikeRawId(text)) return text
  }
  const fb = String(fallback || '').trim()
  if (fb && !looksLikeRawId(fb)) return fb
  return c.isGroup ? '未知群聊' : '未知用户'
}

const identityAvatar = (contact) => {
  return String(contact?.avatar || contact?.avatarUrl || '').trim()
}

const identityFallback = (name, isGroup = false) => {
  if (isGroup) return '群'
  const text = String(name || '').trim()
  return text ? text.charAt(0) : '用'
}

const friendVerificationContact = (item) => {
  return item?.contact && typeof item.contact === 'object'
    ? item.contact
    : { username: String(item?.userName || '').trim(), displayName: '', avatar: '', isGroup: false }
}

const friendVerificationDisplayName = (item) => {
  return identityDisplayName(friendVerificationContact(item), item?.remark || '未知用户')
}

const friendVerificationRawTitle = (item) => {
  const username = String(item?.userName || '').trim()
  const name = friendVerificationDisplayName(item)
  return username ? `${name} · ${username}` : name
}

const openChatByUsername = (username) => {
  const u = String(username || '').trim()
  if (!u) return
  void navigateTo(`/chat/${encodeURIComponent(u)}`)
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

const escapeHtml = (value) => String(value == null ? '' : value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const renderContactHtmlValue = (value) => {
  const text = String(value == null ? '' : value).trim()
  return text ? escapeHtml(text) : '<span class="empty-value">未填写</span>'
}

const contactHtmlIdentityFields = [['username', '用户名'], ['displayName', '显示名称']]
const contactHtmlDetailFields = [
  ['remark', '备注'],
  ['nickname', '昵称'],
  ['alias', '微信号'],
  ['region', '地区'],
  ['source', '来源'],
]

const renderContactHtmlCard = (row, includeAvatar) => {
  const displayName = [row?.displayName, row?.remark, row?.nickname, row?.username]
    .map((value) => String(value || '').trim())
    .find(Boolean) || '未命名联系人'
  const initial = Array.from(displayName)[0]?.toUpperCase() || '?'
  const rawAvatarUrl = includeAvatar ? String(row?.avatarLink || '').trim() : ''
  const avatarUrl = /^https?:\/\//i.test(rawAvatarUrl) ? rawAvatarUrl : ''
  const avatarImage = avatarUrl
    ? `<span class="contact-avatar fallback">${escapeHtml(initial)}</span><img class="contact-avatar" src="${escapeHtml(avatarUrl)}" alt="${escapeHtml(displayName)}的头像" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true">`
    : `<span class="contact-avatar fallback">${escapeHtml(initial)}</span>`
  const identity = contactHtmlIdentityFields.map(([key, label]) => (
    `<div class="contact-field"><span>${escapeHtml(label)}</span><b>${renderContactHtmlValue(row?.[key])}</b></div>`
  )).join('')
  const details = contactHtmlDetailFields.map(([key, label]) => (
    `<div class="contact-field"><span>${escapeHtml(label)}</span><b>${renderContactHtmlValue(row?.[key])}</b></div>`
  )).join('')

  return `<article class="contact-card">
  <div class="contact-head"><figure><div class="avatar-frame">${avatarImage}</div></figure><div class="identity-fields">${identity}</div></div>
  <div class="contact-details">${details}</div>
</article>`
}

const buildContactsHtmlDocument = ({ account, contacts, includeAvatar }) => {
  const cards = contacts.map((row) => renderContactHtmlCard(row, includeAvatar)).join('\n')
  const content = cards
    ? `<section class="contact-grid">${cards}</section>`
    : '<div class="empty-state">没有符合条件的联系人</div>'
  const styles = `:root{--page:#ededed;--panel:#fff;--soft:#f7f7f7;--hover:#f5f7f5;--line:#e2e5e2;--line-strong:#d3d7d3;--text:#191919;--secondary:#555b56;--muted:#6d746e;--green:#07c160;--green-dark:#058f48;--green-soft:#e9f8ef}*{box-sizing:border-box;letter-spacing:0}html,body{margin:0;min-height:100%;background:var(--page);color:var(--text);font:13px/1.45 "Segoe UI","PingFang SC","Microsoft YaHei UI",sans-serif}.records-page{width:100%;min-height:100vh;padding:16px}.records-frame{width:min(100%,1400px);min-height:calc(100vh - 32px);margin:0 auto;overflow:hidden;border:1px solid var(--line-strong);border-radius:8px;background:var(--panel)}.masthead{position:sticky;z-index:5;top:0;display:flex;min-height:76px;align-items:center;justify-content:space-between;gap:24px;padding:14px 18px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.96)}.masthead h1{margin:0;font-size:21px;font-weight:500;line-height:1.3}.masthead .count{display:block;margin-top:2px;color:var(--muted);font-size:13px}.masthead .count strong{margin:0 3px;color:var(--secondary);font-size:14px;font-weight:500}.export-meta{max-width:55%;color:var(--muted);font-size:12px;text-align:right;overflow-wrap:anywhere}.section-bar{display:flex;min-height:50px;align-items:center;justify-content:space-between;gap:16px;padding:0 18px;border-bottom:1px solid var(--line);background:var(--soft)}.section-bar strong{font-size:14px;font-weight:500}.section-bar span{color:var(--muted)}.contact-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0 14px;padding:2px 14px 18px}.contact-card{min-width:0;padding:14px 8px 12px;border-bottom:1px solid var(--line);border-radius:6px}.contact-card:hover{background:var(--hover)}.contact-head{display:grid;grid-template-columns:50px minmax(0,1fr);align-items:start;gap:11px;min-width:0}figure{width:50px;margin:0;text-align:center}.avatar-frame{position:relative;width:50px;height:50px;overflow:hidden;border-radius:8px;background:var(--green-soft)}.contact-avatar{position:absolute;inset:0;display:grid;width:100%;height:100%;place-items:center;object-fit:cover}.contact-avatar.fallback{color:var(--green-dark);font-size:15px;font-weight:500}.identity-fields,.contact-details{min-width:0}.contact-details{margin-top:8px}.contact-field{display:grid;grid-template-columns:76px minmax(0,1fr);gap:7px;min-width:0;padding:3px 0}.contact-field span{color:var(--muted);font-size:12px;white-space:nowrap}.contact-field b{min-width:0;color:var(--secondary);font-size:12px;font-weight:400;line-height:1.45;overflow-wrap:anywhere}.empty-value{color:#a6aca7}.empty-state{display:grid;min-height:260px;place-items:center;color:var(--muted)}@media(max-width:1100px){.contact-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:640px){.records-page{padding:0}.records-frame{min-height:100vh;border:0;border-radius:0}.masthead{align-items:flex-start;flex-direction:column;gap:7px;padding:14px 16px}.export-meta{max-width:100%;text-align:left}.contact-grid{grid-template-columns:minmax(0,1fr);padding-inline:9px}}`
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>联系人导出</title><style>${styles}</style></head><body><div class="records-page"><main class="records-frame"><header class="masthead"><div><h1>联系人</h1><span class="count">共<strong>${contacts.length}</strong>个联系人</span></div><div class="export-meta">账号 ${escapeHtml(account)}</div></header><div class="section-bar"><strong>全部联系人</strong><span>已显示 ${contacts.length} 个</span></div>${content}</main></div></body></html>`
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
      row.avatarLink = String(item?.avatarLink || item?.avatar || '')
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
  if (!['html', 'json', 'txt', 'excel', 'csv'].includes(fmt)) {
    throw new Error('不支持的导出格式')
  }
  if (!exportFolderHandle.value) {
    throw new Error('请先选择导出目录')
  }

  const payload = await buildExportContactsPayload()
  const extension = fmt === 'excel' ? 'xlsx' : fmt
  const fileName = `contacts_${safeExportPart(payload.account)}_${buildExportTimestamp()}.${extension}`
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
  } else if (fmt === 'csv') {
    const lines = [columns.map(([, label]) => escapeCsvCell(label)).join(',')]
    for (const row of payload.contacts) {
      lines.push(columns.map(([key]) => escapeCsvCell(row[key])).join(','))
    }
    await writeWebExportFile({ fileName, content: `\uFEFF${lines.join('\n')}` })
  } else if (fmt === 'txt') {
    const lines = ['联系人导出', `账号: ${payload.account}`, `数量: ${payload.count}`, '']
    for (const [index, row] of payload.contacts.entries()) {
      const details = columns
        .map(([key, label]) => `${label}: ${String(row?.[key] == null ? '' : row[key])}`)
        .filter((value) => !value.endsWith(': '))
      lines.push(`[${index + 1}] ${details.join(' | ')}`)
    }
    await writeWebExportFile({ fileName, content: `${lines.join('\n')}\n` })
  } else if (fmt === 'html') {
    const document = buildContactsHtmlDocument({
      account: payload.account,
      contacts: payload.contacts,
      includeAvatar: !!includeAvatarLink.value,
    })
    await writeWebExportFile({ fileName, content: document })
  } else {
    await writeWebExportFile({
      fileName,
      content: createXlsxBlob({
        sheetName: '联系人',
        headers: columns.map(([, label]) => label),
        rows: payload.contacts.map((row) => columns.map(([key]) => row?.[key] == null ? '' : row[key]))
      })
    })
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

let friendVerificationRequestId = 0

const resetFriendVerifications = () => {
  friendVerifications.value = []
  friendVerificationTotal.value = 0
  friendVerificationHasMore.value = false
  friendVerificationError.value = ''
}

const loadFriendVerifications = async (options = {}) => {
  if (!selectedAccount.value) {
    friendVerificationRequestId += 1
    resetFriendVerifications()
    friendVerificationLoading.value = false
    return
  }

  const append = !!options.append
  const requestId = ++friendVerificationRequestId
  friendVerificationLoading.value = true
  friendVerificationError.value = ''

  try {
    const resp = await api.listFriendVerifications({
      account: selectedAccount.value,
      q: friendVerificationKeyword.value || '',
      limit: FRIEND_VERIFICATION_PAGE_SIZE,
      offset: append ? friendVerifications.value.length : 0,
    })
    if (requestId !== friendVerificationRequestId) return
    const items = Array.isArray(resp?.items) ? resp.items : []
    friendVerifications.value = append ? [...friendVerifications.value, ...items] : items
    friendVerificationTotal.value = Number(resp?.total || 0)
    friendVerificationHasMore.value = !!resp?.hasMore
  } catch (e) {
    if (requestId === friendVerificationRequestId) {
      if (!append) friendVerifications.value = []
      friendVerificationTotal.value = append ? friendVerificationTotal.value : 0
      friendVerificationHasMore.value = false
      friendVerificationError.value = e?.message || '加载好友验证记录失败'
    }
  } finally {
    if (requestId === friendVerificationRequestId) {
      friendVerificationLoading.value = false
    }
  }
}

const loadMoreFriendVerifications = () => {
  return loadFriendVerifications({ append: true })
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

let friendVerificationKeywordTimer = null
watch(() => friendVerificationKeyword.value, () => {
  if (friendVerificationKeywordTimer) clearTimeout(friendVerificationKeywordTimer)
  friendVerificationKeywordTimer = setTimeout(() => {
    void loadFriendVerifications()
  }, 250)
})

watch(() => selectedAccount.value, () => {
  void loadFriendVerifications()
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
  await loadFriendVerifications()
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
