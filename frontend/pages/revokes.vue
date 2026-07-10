<template>
  <div class="h-screen flex overflow-hidden" style="background-color: var(--app-shell-bg)">
    <div class="flex-1 min-h-0 overflow-auto p-4">
      <div class="mx-auto flex h-full min-h-0 max-w-7xl flex-col gap-4">
        <header class="rounded-lg border border-[#e5e7eb] bg-white px-5 py-4">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 class="text-[26px] font-semibold tracking-[-0.03em] text-[#111827]">撤回 / 可撤回缓存</h1>
            </div>
            <div class="relative w-full lg:w-[360px]">
              <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9ca3af]" fill="none" stroke="currentColor" viewBox="0 0 16 16" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.333 12.667A5.333 5.333 0 1 0 7.333 2a5.333 5.333 0 0 0 0 10.667ZM14 14l-2.9-2.9" />
              </svg>
              <input v-model="keyword" type="text" class="w-full rounded-md border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-[13px] text-[#111827] outline-none transition placeholder:text-[#9ca3af] focus:border-[#07C160] focus:ring-2 focus:ring-[#07C160]/15" placeholder="搜索会话、消息 ID、撤回内容" />
            </div>
          </div>
        </header>

        <section class="grid gap-3 md:grid-cols-4">
          <div v-for="card in statCards" :key="card.label" class="rounded-lg border border-[#e5e7eb] bg-white px-4 py-3">
            <div class="text-[12px] text-[#6b7280]">{{ card.label }}</div>
            <div class="mt-1 text-[24px] font-semibold tabular-nums text-[#111827]">{{ card.value }}</div>
          </div>
        </section>

        <section class="min-h-0 flex flex-1 flex-col rounded-lg border border-[#e5e7eb] bg-white">
          <div class="flex items-center justify-between border-b border-[#e5e7eb] px-4 py-3">
            <div class="text-[14px] font-medium text-[#111827]">撤回索引与候选缓存</div>
            <button type="button" class="text-[12px] text-[#07C160] hover:text-[#04994c] disabled:opacity-60" :disabled="loading" @click="loadItems({ force: true })">
              {{ loading ? '刷新中…' : '刷新' }}
            </button>
          </div>

          <div class="min-h-0 flex-1 overflow-auto p-4">
            <div v-if="loading && !items.length" class="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-4 py-6 text-[13px] text-[#6b7280]">正在加载撤回记录…</div>
            <div v-else-if="error" class="rounded-md border border-[#fecaca] bg-[#fef2f2] px-4 py-4 text-[13px] text-[#b91c1c]">{{ error }}</div>
            <div v-else-if="!items.length" class="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-4 py-6 text-[13px] text-[#6b7280]">暂无撤回/可撤回缓存</div>
            <div v-else class="space-y-2">
              <div class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
                当前列表中「可批量撤回缓存」只是微信为本机发送消息保留的撤回候选索引；只有「已撤回」才表示实际发生过撤回。
              </div>
              <article
                v-for="item in items"
                :key="recordKey(item)"
                class="cursor-pointer rounded-lg border border-[#eef2f7] bg-white px-4 py-3 transition hover:border-[#bbf7d0] hover:bg-[#fcfffd]"
                title="点击跳转到会话"
                @click="openChatByUsername(item.sessionName || item.toUserName)"
              >
                <div class="flex items-start gap-3">
                  <div class="h-11 w-11 shrink-0 overflow-hidden rounded-md bg-[#e5e7eb]" :class="{ 'privacy-blur': privacyMode }">
                    <img
                      v-if="identityAvatar(recordContact(item)) && !avatarBroken[avatarBrokenKey(recordContact(item), recordKey(item))]"
                      :src="identityAvatar(recordContact(item))"
                      :alt="recordTitle(item)"
                      class="h-full w-full object-cover"
                      loading="lazy"
                      decoding="async"
                      referrerpolicy="no-referrer"
                      @error="markAvatarBroken(recordContact(item), recordKey(item))"
                    />
                    <div v-else class="flex h-full w-full items-center justify-center bg-[#07C160] text-xs font-bold text-white">
                      {{ identityFallback(recordTitle(item), recordContact(item)?.isGroup) }}
                    </div>
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                        <div class="truncate text-[14px] font-semibold text-[#111827]" :title="recordRawTitle(item)">{{ recordTitle(item) }}</div>
                        <div class="mt-1 truncate text-[12px] text-[#6b7280]">{{ recordSubtitle(item) }}</div>
                      </div>
                      <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="item.kind === 'batch' ? 'bg-amber-50 text-amber-700' : 'bg-[#f0fdf4] text-[#047857]'">
                        {{ item.recordTypeLabel || (item.kind === 'batch' ? '可批量撤回缓存' : '已撤回') }}
                      </span>
                    </div>

                    <div v-if="item.kind === 'batch'" class="mt-3 grid gap-2 text-[11px] text-[#6b7280] sm:grid-cols-4">
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">消息时间：{{ item.msgCreateTimeText || '—' }}</div>
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">原消息：{{ recalledMessageText(item) || '未在消息库中找到' }}</div>
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">batch_id：{{ item.batchId }}</div>
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">msg_local：{{ item.msgLocalId }}</div>
                    </div>
                    <div v-else class="mt-3 grid gap-2 text-[11px] text-[#6b7280] sm:grid-cols-4">
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">撤回时间：{{ item.revokeTimeText || '—' }}</div>
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">原消息：{{ recalledMessageText(item) || '未在消息库中找到' }}</div>
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">message_type：{{ item.messageType }}</div>
                      <div class="rounded-md bg-[#f9fafb] px-2 py-1.5">svr_id：{{ item.svrId || 0 }}</div>
                    </div>
                  </div>
                </div>
              </article>
            </div>

            <button v-if="hasMore" type="button" class="mt-4 w-full rounded-md border border-[#e5e7eb] bg-white px-3 py-2 text-[13px] font-medium text-[#4b5563] transition hover:border-[#bbf7d0] hover:bg-[#f0fdf4] hover:text-[#047857] disabled:opacity-60" :disabled="loading" @click="loadItems({ append: true })">
              {{ loading ? '加载中…' : `加载更多（${items.length} / ${total}）` }}
            </button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

useHead({ title: '撤回 / 可撤回缓存 - 微信数据分析助手' })

const api = useApi()
const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)
const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const keyword = ref('')
const items = ref([])
const total = ref(0)
const actualTotal = ref(0)
const candidateTotal = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
const PAGE_SIZE = 80
let requestId = 0
let keywordTimer = null
const avatarBroken = reactive({})

const batchCount = computed(() => items.value.filter((item) => item?.kind === 'batch').length)
const singleCount = computed(() => items.value.filter((item) => item?.kind === 'single').length)
const statCards = computed(() => [
  { label: '匹配总数', value: total.value },
  { label: '已撤回', value: actualTotal.value || singleCount.value },
  { label: '可撤回缓存', value: candidateTotal.value || batchCount.value },
  { label: '当前加载', value: items.value.length },
])

const recordKey = (item) => item.kind === 'batch'
  ? `batch-${item.localId}-${item.msgUniqueId}`
  : `single-${item.svrId}-${item.revokeTime}`

const recordContact = (item) => {
  return item?.sessionContact && typeof item.sessionContact === 'object' ? item.sessionContact : null
}

const looksLikeRawId = (value) => {
  const text = String(value || '').trim()
  return !!(text.startsWith('wxid_') || text.endsWith('@chatroom') || /^\d{5,}@chatroom$/i.test(text))
}

const identityDisplayName = (contact, fallback = '未知会话') => {
  const c = contact && typeof contact === 'object' ? contact : {}
  const rawUsername = String(c.username || '').trim()
  for (const value of [c.displayName, c.name, c.nickname, c.remark]) {
    const text = String(value || '').trim()
    if (text && text !== rawUsername && !looksLikeRawId(text)) return text
  }
  const fb = String(fallback || '').trim()
  if (fb && !looksLikeRawId(fb)) return fb
  return c.isGroup ? '未知群聊' : '未知会话'
}

const identityAvatar = (contact) => String(contact?.avatar || contact?.avatarUrl || '').trim()

const avatarBrokenKey = (contact, fallback = '') => {
  return `${selectedAccount.value || ''}::${contact?.username || fallback || ''}`
}

const markAvatarBroken = (contact, fallback = '') => {
  const key = avatarBrokenKey(contact, fallback)
  if (key) avatarBroken[key] = true
}

const identityFallback = (name, isGroup = false) => {
  if (isGroup) return '群'
  const text = String(name || '').trim()
  return text ? text.charAt(0) : '撤'
}

const recalledMessageText = (item) => {
  const text = String(item?.messageSummary || item?.message?.content || '').trim()
  return text
}

const openChatByUsername = (username) => {
  const u = String(username || '').trim()
  if (!u) return
  void navigateTo(`/chat/${encodeURIComponent(u)}`)
}

const recordTitle = (item) => item.kind === 'batch'
  ? identityDisplayName(recordContact(item), item.sessionName || '未知会话')
  : identityDisplayName(recordContact(item), item.toUserName || '未知会话')

const recordRawTitle = (item) => {
  const raw = item.kind === 'batch' ? item.sessionName : item.toUserName
  return raw ? `${recordTitle(item)} · ${raw}` : recordTitle(item)
}

const recordSubtitle = (item) => item.kind === 'batch'
  ? (recalledMessageText(item) ? `可撤回候选：${recalledMessageText(item)}` : `可撤回候选 · msg_local：${item.msgLocalId || '—'}`)
  : (recalledMessageText(item) ? `已撤回：${recalledMessageText(item)}` : (item.content || '无撤回内容摘要'))

const resetItems = () => {
  items.value = []
  total.value = 0
  actualTotal.value = 0
  candidateTotal.value = 0
  hasMore.value = false
  error.value = ''
}

const loadItems = async (options = {}) => {
  await chatAccounts.ensureLoaded()
  if (!selectedAccount.value) {
    requestId += 1
    resetItems()
    error.value = '未找到可用账号，先完成检测或导入。'
    return
  }

  const append = !!options.append
  const rid = ++requestId
  loading.value = true
  error.value = ''
  try {
    const resp = await api.listRevokeRecords({
      account: selectedAccount.value,
      q: keyword.value || '',
      limit: PAGE_SIZE,
      offset: append ? items.value.length : 0,
    })
    if (rid !== requestId) return
    const next = Array.isArray(resp?.items) ? resp.items : []
    items.value = append ? [...items.value, ...next] : next
    total.value = Number(resp?.total || 0)
    actualTotal.value = Number(resp?.actualTotal || 0)
    candidateTotal.value = Number(resp?.candidateTotal || 0)
    hasMore.value = !!resp?.hasMore
  } catch (e) {
    if (rid === requestId) {
      if (!append) resetItems()
      error.value = e?.message || '加载撤回记录失败'
    }
  } finally {
    if (rid === requestId) loading.value = false
  }
}

watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => { void loadItems() }, 250)
})

watch(() => selectedAccount.value, () => { void loadItems() })

onMounted(async () => {
  privacyStore.init()
  await chatAccounts.ensureLoaded()
  await loadItems()
})
</script>
