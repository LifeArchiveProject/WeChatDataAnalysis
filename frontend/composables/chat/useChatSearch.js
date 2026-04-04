import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  dateToUnixSeconds,
  formatMessageFullTime,
  highlightKeyword
} from '~/lib/chat/formatters'

export const createEmptySearchContext = () => ({
  active: false,
  kind: 'search',
  label: '',
  username: '',
  anchorId: '',
  anchorIndex: -1,
  hasMoreBefore: false,
  hasMoreAfter: false,
  loadingBefore: false,
  loadingAfter: false,
  savedMessages: null,
  savedMeta: null
})

export const useChatSearch = ({
  api,
  heatColor,
  contacts,
  selectedAccount,
  selectedContact,
  privacyMode,
  allMessages,
  messagesMeta,
  messages,
  messageContainerRef,
  messagePageSize,
  hasMoreMessages,
  isLoadingMessages,
  normalizeMessage,
  updateJumpToBottomState,
  scrollToMessageId,
  flashMessage,
  highlightMessageId,
  searchContext,
  selectContact,
  loadMoreMessages
}) => {
const isDesktopRenderer = () => {
if (!process.client || typeof window === 'undefined') return false
return !!window.wechatDesktop?.__brand
}

const logSearchPhase = (phase, details = {}) => {
const payload = {
  account: String(selectedAccount.value || '').trim(),
  selectedUsername: String(selectedContact.value?.username || '').trim(),
  contextUsername: String(searchContext.value?.username || '').trim(),
  ...details
}

if (isDesktopRenderer()) {
  try {
    window.wechatDesktop?.logDebug?.('chat-search', phase, payload)
  } catch {}
}

console.info(`[chat-search] ${phase}`, payload)
}

const describeEventTarget = (target) => {
if (!target || typeof target !== 'object') return ''
const nodeName = String(target.nodeName || '').trim().toLowerCase()
let cls = ''
try {
  cls = typeof target.className === 'string'
    ? target.className
    : String(target.className?.baseVal || '')
} catch {
  cls = ''
}
cls = String(cls || '').trim().replace(/\s+/g, '.')
if (!nodeName) return cls.slice(0, 120)
if (!cls) return nodeName
return `${nodeName}.${cls}`.slice(0, 120)
}

const summarizeHitForLog = (hit, idx) => ({
index: Number(idx ?? -1),
hitId: String(hit?.id || '').trim(),
hitUsername: String(hit?.username || '').trim(),
conversationName: String(hit?.conversationName || '').trim(),
senderUsername: String(hit?.senderUsername || '').trim(),
renderType: String(hit?.renderType || '').trim(),
createTime: Number(hit?.createTime || 0),
isSent: !!hit?.isSent
})

const buildRunSearchLogDetails = ({ source = 'unknown', reset = false } = {}) => {
const q = String(messageSearchQuery.value || '').trim()
return {
  source: String(source || 'unknown'),
  reset: !!reset,
  scope: String(messageSearchScope.value || 'conversation'),
  queryLength: q.length,
  selectedContactUsername: String(selectedContact.value?.username || '').trim(),
  sender: String(messageSearchSender.value || '').trim(),
  sessionType: String(messageSearchSessionType.value || '').trim(),
  rangeDays: String(messageSearchRangeDays.value || '').trim(),
  startDate: String(messageSearchStartDate.value || '').trim(),
  endDate: String(messageSearchEndDate.value || '').trim(),
  offset: Number(messageSearchOffset.value || 0),
  resultCount: Number(messageSearchResults.value?.length || 0)
}
}

const messageSearchOpen = ref(false)
const messageSearchQuery = ref('')
const messageSearchScope = ref('global') // conversation | global
const messageSearchRangeDays = ref('') // empty means no time filter
const messageSearchSessionType = ref('') // empty means all (global only): group | single
const messageSearchSender = ref('') // 发送者筛选
const messageSearchSenderOptions = ref([])
const messageSearchSenderLoading = ref(false)
const messageSearchSenderError = ref('')
const messageSearchSenderOptionsKey = ref('')
const messageSearchSenderDropdownOpen = ref(false)
const messageSearchSenderDropdownRef = ref(null)
const messageSearchSenderDropdownInputRef = ref(null)
const messageSearchSenderDropdownQuery = ref('')
const messageSearchStartDate = ref('') // 自定义开始日期
const messageSearchEndDate = ref('') // 自定义结束日期
const messageSearchResults = ref([])
const messageSearchLoading = ref(false)
const messageSearchError = ref('')
const messageSearchBackendStatus = ref('')
const messageSearchIndexInfo = ref(null)
const messageSearchHasMore = ref(false)
const messageSearchOffset = ref(0)
const messageSearchLimit = 50
const messageSearchTotal = ref(0)
const messageSearchSelectedIndex = ref(-1)
const messageSearchInputRef = ref(null)
let messageSearchDebounceTimer = null
let messageSearchIndexPollTimer = null

// 搜索UI增强
const searchInputFocused = ref(false)
const showAdvancedFilters = ref(false)
const searchHistory = ref([])
const SEARCH_HISTORY_KEY = 'wechat_search_history'
const MAX_SEARCH_HISTORY = 10

// 加载搜索历史
const loadSearchHistory = () => {
if (!process.client) return
try {
  const saved = localStorage.getItem(SEARCH_HISTORY_KEY)
  if (saved) {
    searchHistory.value = JSON.parse(saved) || []
  }
} catch (e) {
  searchHistory.value = []
}
}

// 保存搜索历史
const saveSearchHistory = (query) => {
if (!process.client) return
if (!query || !query.trim()) return
const q = query.trim()
try {
  let history = [...searchHistory.value]
  // 移除重复项
  history = history.filter(item => item !== q)
  // 添加到开头
  history.unshift(q)
  // 限制数量
  if (history.length > MAX_SEARCH_HISTORY) {
    history = history.slice(0, MAX_SEARCH_HISTORY)
  }
  searchHistory.value = history
  localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(history))
} catch (e) {
  // ignore
}
}

// 清空搜索历史
const clearSearchHistory = () => {
if (!process.client) return
searchHistory.value = []
try {
  localStorage.removeItem(SEARCH_HISTORY_KEY)
} catch (e) {
  // ignore
}
}

// 应用搜索历史
const applySearchHistory = async (query) => {
messageSearchQuery.value = query
await runMessageSearch({ reset: true, source: 'history-apply' })
}

const messageSearchIndexExists = computed(() => !!messageSearchIndexInfo.value?.exists)
const messageSearchIndexReady = computed(() => !!messageSearchIndexInfo.value?.ready)
const messageSearchIndexBuildStatus = computed(() => String(messageSearchIndexInfo.value?.build?.status || ''))
const messageSearchIndexBuildIndexed = computed(() => Number(messageSearchIndexInfo.value?.build?.indexedMessages || 0))
const messageSearchIndexMetaCount = computed(() => {
const meta = messageSearchIndexInfo.value?.meta || {}
const v = meta.message_count ?? meta.messageCount ?? meta.message_count ?? 0
return Number(v || 0)
})

const messageSearchIndexProgressText = computed(() => {
if (messageSearchIndexBuildStatus.value !== 'building') return ''
const n = Number(messageSearchIndexBuildIndexed.value || 0)
return n > 0 ? `已索引 ${n.toLocaleString()} 条` : '准备中...'
})

const messageSearchIndexText = computed(() => {
if (!messageSearchIndexInfo.value) return ''
if (!messageSearchIndexExists.value) return '索引未建立'
if (messageSearchIndexBuildStatus.value === 'error') return '索引异常'
if (!messageSearchIndexReady.value) return '索引未完成，需重建'
const n = Number(messageSearchIndexMetaCount.value || 0)
return n > 0 ? `索引已就绪（${n.toLocaleString()} 条）` : '索引已就绪'
})

const messageSearchIndexActionText = computed(() => {
if (messageSearchIndexBuildStatus.value === 'building') return '建立中'
return messageSearchIndexExists.value ? '重建索引' : '建立索引'
})

const messageSearchIndexActionDisabled = computed(() => {
return messageSearchIndexBuildStatus.value === 'building' || messageSearchLoading.value
})

const formatCount = (n) => {
const v = Number(n || 0)
if (!Number.isFinite(v) || v <= 0) return ''
try {
  return v.toLocaleString()
} catch {
  return String(v)
}
}

const messageSearchSenderDisabled = computed(() => {
if (!selectedAccount.value) return true
const scope = String(messageSearchScope.value || 'conversation')
if (scope === 'conversation') {
  return !selectedContact.value?.username
}
const q = String(messageSearchQuery.value || '').trim()
if (q.length >= 2) return false
return !String(messageSearchSender.value || '').trim()
})

const messageSearchSelectedSenderInfo = computed(() => {
const u = String(messageSearchSender.value || '').trim()
if (!u) return null
const list = Array.isArray(messageSearchSenderOptions.value) ? messageSearchSenderOptions.value : []
const found = list.find((s) => String(s?.username || '').trim() === u)
if (found) return found
return { username: u, displayName: u, avatar: null, count: null }
})

const messageSearchSelectedSenderInitial = computed(() => {
const info = messageSearchSelectedSenderInfo.value
if (!info) return '人'
const n = String(info.displayName || info.username || '').trim()
return n ? n.charAt(0) : '人'
})

const messageSearchSenderLabel = computed(() => {
const cur = String(messageSearchSender.value || '').trim()
if (!cur) {
  if (String(messageSearchScope.value || '') === 'global' && String(messageSearchQuery.value || '').trim().length < 2) {
    return '发送者'
  }
  return '不限发送者'
}
const info = messageSearchSelectedSenderInfo.value
return String(info?.displayName || info?.username || cur)
})

const filteredMessageSearchSenderOptions = computed(() => {
const list = Array.isArray(messageSearchSenderOptions.value) ? messageSearchSenderOptions.value : []
const q = String(messageSearchSenderDropdownQuery.value || '').trim().toLowerCase()
if (!q) return list
return list.filter((s) => {
  const u = String(s?.username || '').toLowerCase()
  const n = String(s?.displayName || '').toLowerCase()
  return u.includes(q) || n.includes(q)
})
})

const closeMessageSearchSenderDropdown = () => {
messageSearchSenderDropdownOpen.value = false
messageSearchSenderDropdownQuery.value = ''
}

const getMessageSearchSenderFacetKey = () => {
const acc = String(selectedAccount.value || '').trim()
if (!acc) return ''
const scope = String(messageSearchScope.value || 'conversation')
const conv = scope === 'conversation' ? String(selectedContact.value?.username || '') : ''
const q = String(messageSearchQuery.value || '').trim()
const range = String(messageSearchRangeDays.value || '')
const sd = String(messageSearchStartDate.value || '')
const ed = String(messageSearchEndDate.value || '')
const st = scope === 'global' ? String(messageSearchSessionType.value || '').trim() : ''
return [acc, scope, conv, q, range, sd, ed, st].join('|')
}

const ensureMessageSearchSendersLoaded = async () => {
const key = getMessageSearchSenderFacetKey()
if (!key) return
if (messageSearchSenderOptionsKey.value === key && !messageSearchSenderLoading.value) return
const list = await fetchMessageSearchSenders()
messageSearchSenderOptionsKey.value = key
return list
}

const toggleMessageSearchSenderDropdown = async () => {
if (messageSearchSenderDisabled.value) return
if (messageSearchSenderDropdownOpen.value) {
  closeMessageSearchSenderDropdown()
  return
}
messageSearchSenderDropdownOpen.value = true
await ensureMessageSearchSendersLoaded()
await nextTick()
try {
  messageSearchSenderDropdownInputRef.value?.focus?.()
} catch {}
}

const selectMessageSearchSender = (username) => {
messageSearchSender.value = String(username || '')
closeMessageSearchSenderDropdown()
}

const fetchMessageSearchIndexStatus = async () => {
if (!selectedAccount.value) return null
logSearchPhase('search-index-status:start', {
  queryLength: String(messageSearchQuery.value || '').trim().length
})
try {
  const resp = await api.getChatSearchIndexStatus({ account: selectedAccount.value })
  messageSearchIndexInfo.value = resp?.index || null
  logSearchPhase('search-index-status:end', {
    exists: !!messageSearchIndexInfo.value?.exists,
    ready: !!messageSearchIndexInfo.value?.ready,
    buildStatus: String(messageSearchIndexInfo.value?.build?.status || '').trim()
  })
  return messageSearchIndexInfo.value
} catch (e) {
  logSearchPhase('search-index-status:error', {
    error: String(e?.message || e || '')
  })
  return null
}
}

const fetchMessageSearchSenders = async () => {
messageSearchSenderError.value = ''
if (!selectedAccount.value) {
  messageSearchSenderOptions.value = []
  messageSearchSenderOptionsKey.value = ''
  logSearchPhase('search-senders:skip:no-account')
  return []
}

const scope = String(messageSearchScope.value || 'conversation')
const msgQ = String(messageSearchQuery.value || '').trim()

const params = {
  account: selectedAccount.value,
  limit: 200
}

if (scope === 'conversation') {
  if (!selectedContact.value?.username) {
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    logSearchPhase('search-senders:skip:no-selected-contact', {
      scope
    })
    return []
  }
  params.username = selectedContact.value.username
} else {
  if (msgQ.length < 2) {
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    logSearchPhase('search-senders:skip:query-too-short', {
      scope,
      queryLength: msgQ.length
    })
    return []
  }
}

if (msgQ) {
  params.message_q = msgQ
}

params.render_types = 'text'

const range = String(messageSearchRangeDays.value || '')
if (range === 'custom') {
  const start = dateToUnixSeconds(messageSearchStartDate.value, false)
  const end = dateToUnixSeconds(messageSearchEndDate.value, true)
  if (start != null) params.start_time = start
  if (end != null) params.end_time = end
  if (start != null && end != null && start > end) {
    messageSearchSenderError.value = '时间范围不合法：开始日期不能晚于结束日期'
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    return []
  }
} else {
  const days = Number(range || 0)
  if (days > 0 && Number.isFinite(days)) {
    const end = Math.floor(Date.now() / 1000)
    const start = Math.max(0, end - Math.floor(days * 24 * 3600))
    params.start_time = start
    params.end_time = end
  }
}

if (scope === 'global') {
  const st = String(messageSearchSessionType.value || '').trim()
  if (st) params.session_type = st
}

messageSearchSenderLoading.value = true
logSearchPhase('search-senders:start', {
  scope,
  queryLength: msgQ.length,
  username: String(params.username || '').trim()
})
try {
  const resp = await api.listChatSearchSenders(params)
  const status = String(resp?.status || 'success')
  if (status !== 'success') {
    logSearchPhase('search-senders:non-success', {
      scope,
      status,
      queryLength: msgQ.length,
      message: String(resp?.message || '')
    })
    if (status !== 'index_building') {
      messageSearchSenderError.value = String(resp?.message || '加载发送者失败')
    }
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    return []
  }
  const list = Array.isArray(resp?.senders) ? resp.senders : []
  messageSearchSenderOptions.value = list
  messageSearchSenderOptionsKey.value = getMessageSearchSenderFacetKey()
  const cur = String(messageSearchSender.value || '').trim()
  if (cur && !list.some((s) => String(s?.username || '').trim() === cur)) {
    messageSearchSender.value = ''
  }
  logSearchPhase('search-senders:end', {
    scope,
    queryLength: msgQ.length,
    username: String(params.username || '').trim(),
    optionCount: list.length
  })
  return list
} catch (e) {
  messageSearchSenderError.value = e?.message || '加载发送者失败'
  messageSearchSenderOptions.value = []
  messageSearchSenderOptionsKey.value = ''
  logSearchPhase('search-senders:error', {
    scope,
    queryLength: msgQ.length,
    error: String(e?.message || e || '')
  })
  return []
} finally {
  messageSearchSenderLoading.value = false
}
}

const stopMessageSearchIndexPolling = () => {
if (messageSearchIndexPollTimer) clearInterval(messageSearchIndexPollTimer)
messageSearchIndexPollTimer = null
}

const ensureMessageSearchIndexPolling = () => {
if (messageSearchIndexPollTimer) return
messageSearchIndexPollTimer = setInterval(async () => {
  if (!messageSearchOpen.value) {
    stopMessageSearchIndexPolling()
    return
  }

  const info = await fetchMessageSearchIndexStatus()
  const exists = !!info?.exists
  const ready = !!info?.ready
  const bs = String(info?.build?.status || '')
  const done = exists && ready && bs !== 'building'
  if (done) {
    stopMessageSearchIndexPolling()
    if (String(messageSearchScope.value || '') === 'conversation') {
      await fetchMessageSearchSenders()
    }
    if (String(messageSearchQuery.value || '').trim()) {
      await runMessageSearch({ reset: true, source: 'index-poll-ready' })
    }
  }
}, 1200)
}

const onMessageSearchIndexAction = async () => {
if (!selectedAccount.value) return
const rebuild = messageSearchIndexExists.value
try {
  const resp = await api.buildChatSearchIndex({ account: selectedAccount.value, rebuild })
  messageSearchIndexInfo.value = resp?.index || null
  messageSearchBackendStatus.value = 'index_building'
  ensureMessageSearchIndexPolling()
} catch (e) {
  messageSearchError.value = e?.message || '建立索引失败'
}
}
const getMessageSearchHitAvatarUrl = (hit) => {
if (!hit) return ''
const scope = String(messageSearchScope.value || '')
const url =
  scope === 'global'
    ? (hit.conversationAvatar || hit.senderAvatar || '')
    : (hit.senderAvatar || hit.conversationAvatar || '')
return String(url || '').trim()
}

const getMessageSearchHitAvatarAlt = (hit) => {
if (!hit) return '头像'
const scope = String(messageSearchScope.value || '')
if (scope === 'global') {
  const name = String(hit.conversationName || hit.username || '').trim()
  return name ? `${name} 头像` : '头像'
}
let name = String(hit.senderDisplayName || '').trim()
if (!name) {
  name = hit.isSent ? '我' : String(hit.senderUsername || '').trim()
}
return name ? `${name} 头像` : '头像'
}

const getMessageSearchHitAvatarInitial = (hit) => {
if (!hit) return '?'
const scope = String(messageSearchScope.value || '')
let text = ''
if (scope === 'global') {
  text = String(hit.conversationName || hit.username || '').trim()
} else {
  text = String(hit.senderDisplayName || '').trim()
  if (!text) {
    text = hit.isSent ? '我' : String(hit.senderUsername || '').trim()
  }
}
return (text.charAt(0) || '?').toString()
}

const buildTransientSearchTargetContact = ({ username, displayName = '', avatar = '', isGroup = null } = {}) => {
const u = String(username || '').trim()
if (!u) return null
const name = String(displayName || u).trim() || u
return {
  id: u,
  username: u,
  name,
  avatar: String(avatar || '').trim() || null,
  avatarColor: '#4B5563',
  lastMessage: '',
  lastMessageTime: '',
  unreadCount: 0,
  isGroup: typeof isGroup === 'boolean' ? isGroup : u.endsWith('@chatroom'),
  isTop: false
}
}

const resolveSearchTargetContact = ({ username, displayName = '', avatar = '', isGroup = null } = {}) => {
const u = String(username || '').trim()
if (!u) return null
const existing = contacts.value.find((c) => String(c?.username || '').trim() === u)
if (existing) return existing
if (String(selectedContact.value?.username || '').trim() === u) return selectedContact.value
return buildTransientSearchTargetContact({ username: u, displayName, avatar, isGroup })
}
const searchContextBannerText = computed(() => {
if (!searchContext.value?.active) return ''
const kind = String(searchContext.value.kind || 'search')
if (kind === 'date') {
  const label = String(searchContext.value.label || '').trim()
  return label ? `已定位到 ${label}（上下文模式）` : '已定位到指定日期（上下文模式）'
}
if (kind === 'first') {
  return '已定位到会话顶部（上下文模式）'
}
return '已定位到搜索结果（上下文模式）'
})

// 回到最新按钮
const showJumpToBottom = ref(false)

// 时间侧边栏（按日期定位）
const timeSidebarOpen = ref(false)
const timeSidebarYear = ref(null)
const timeSidebarMonth = ref(null) // 1-12
const timeSidebarCounts = ref({}) // { 'YYYY-MM-DD': count }
const timeSidebarMax = ref(0)
const timeSidebarTotal = ref(0)
const timeSidebarLoading = ref(false)
const timeSidebarError = ref('')
const timeSidebarSelectedDate = ref('') // YYYY-MM-DD (current/selected day)
// Simple in-memory cache per (account|username|YYYY-MM)
const timeSidebarCache = ref({})
const timeSidebarWeekdays = ['一', '二', '三', '四', '五', '六', '日']

const timeSidebarMonthLabel = computed(() => {
const y = Number(timeSidebarYear.value || 0)
const m = Number(timeSidebarMonth.value || 0)
if (!y || !m) return ''
return `${y}年${m}月`
})

const timeSidebarYearOptions = computed(() => {
// WeChat history normally starts after 2011, but keep a broader range for safety.
const nowY = new Date().getFullYear()
const minY = 2000
const maxY = Math.max(nowY, Number(timeSidebarYear.value || 0) || nowY)
const years = []
for (let y = maxY; y >= minY; y--) years.push(y)
return years
})

const timeSidebarActiveDays = computed(() => {
const counts = timeSidebarCounts.value || {}
const keys = Object.keys(counts)
return keys.length
})

const _pad2 = (n) => String(n).padStart(2, '0')

const _dateStrFromEpochSeconds = (ts) => {
const t = Number(ts || 0)
if (!t) return ''
try {
  const d = new Date(t * 1000)
  return `${d.getFullYear()}-${_pad2(d.getMonth() + 1)}-${_pad2(d.getDate())}`
} catch {
  return ''
}
}

// Calendar heatmap color: reuse Wrapped heat palette, but bucket to Wrapped-like legend levels
// so ">=1 message" is always visibly tinted (instead of being almost white when max is huge).
const _calendarHeatColor = (count, maxV) => {
const v = Math.max(0, Number(count || 0))
const m = Math.max(0, Number(maxV || 0))
if (!(v > 0)) return ''
if (!(m > 0)) return heatColor(1, 1)
const levels = 6
const ratio = Math.max(0, Math.min(1, v / m))
const level = Math.min(levels, Math.max(1, Math.ceil(ratio * levels)))
const valueForLevel = Math.max(1, Math.round(level * (m / levels)))
return heatColor(valueForLevel, m)
}

const timeSidebarCalendarCells = computed(() => {
const y = Number(timeSidebarYear.value || 0)
const m = Number(timeSidebarMonth.value || 0) // 1-12
if (!y || !m) return []

const daysInMonth = new Date(y, m, 0).getDate()
const firstDow = new Date(y, m - 1, 1).getDay() // 0=Sun..6=Sat
const offset = (firstDow + 6) % 7 // Monday=0

const maxV = Math.max(0, Number(timeSidebarMax.value || 0))
const counts = timeSidebarCounts.value || {}
const selected = String(timeSidebarSelectedDate.value || '').trim()

const out = []
for (let i = 0; i < 42; i++) {
  const dayNum = i - offset + 1
  const inMonth = dayNum >= 1 && dayNum <= daysInMonth
  if (!inMonth) {
    out.push({
      key: `e:${y}-${m}:${i}`,
      day: '',
      dateStr: '',
      count: 0,
      disabled: true,
      className: 'calendar-day-outside',
      style: null,
      title: ''
    })
    continue
  }

  const dateStr = `${y}-${_pad2(m)}-${_pad2(dayNum)}`
  const count = Math.max(0, Number(counts[dateStr] || 0))
  const disabled = count <= 0

  const style = !disabled
    ? { backgroundColor: _calendarHeatColor(count, Math.max(maxV, count)) }
    : null

  const className = [
    disabled ? 'calendar-day-empty' : '',
    (selected && dateStr === selected) ? 'calendar-day-selected' : ''
  ].filter(Boolean).join(' ')

  out.push({
    key: dateStr,
    day: String(dayNum),
    dateStr,
    count,
    disabled,
    // NOTE: heatmap bg color is applied via inline style (reusing Wrapped heatmap palette).
    // Dynamic class names like `calendar-day-l${level}` may be purged by Tailwind and lead to no bg color.
    className,
    style,
    title: `${dateStr}：${count} 条`
  })
}
return out
})
const closeMessageSearch = (reason = 'manual') => {
logSearchPhase('message-search:close', {
  reason: String(reason || 'manual'),
  queryLength: String(messageSearchQuery.value || '').trim().length,
  resultCount: Number(messageSearchResults.value?.length || 0),
  selectedIndex: Number(messageSearchSelectedIndex.value ?? -1)
})
messageSearchOpen.value = false
closeMessageSearchSenderDropdown()
messageSearchError.value = ''
messageSearchLoading.value = false
messageSearchBackendStatus.value = ''
stopMessageSearchIndexPolling()
if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
messageSearchDebounceTimer = null
}

let timeSidebarReqId = 0

const closeTimeSidebar = () => {
timeSidebarOpen.value = false
timeSidebarError.value = ''
}

const _timeSidebarCacheKey = ({ account, username, year, month }) => {
const acc = String(account || '').trim()
const u = String(username || '').trim()
const y = Number(year || 0)
const m = Number(month || 0)
return `${acc}|${u}|${y}-${_pad2(m)}`
}

const _applyTimeSidebarMonthData = (data) => {
const counts = (data && typeof data.counts === 'object' && !Array.isArray(data.counts)) ? data.counts : {}
timeSidebarCounts.value = counts
timeSidebarMax.value = Math.max(0, Number(data?.max || 0))
timeSidebarTotal.value = Math.max(0, Number(data?.total || 0))
}

const loadTimeSidebarMonth = async ({ year, month, force } = {}) => {
if (!selectedAccount.value) return
if (!selectedContact.value?.username) return

const y = Number(year || timeSidebarYear.value || 0)
const m = Number(month || timeSidebarMonth.value || 0)
if (!y || !m) return

timeSidebarYear.value = y
timeSidebarMonth.value = m

const key = _timeSidebarCacheKey({
  account: selectedAccount.value,
  username: selectedContact.value.username,
  year: y,
  month: m
})

if (!force) {
  const cached = timeSidebarCache.value[key]
  if (cached) {
    timeSidebarError.value = ''
    _applyTimeSidebarMonthData(cached)
    return
  }
}

const reqId = ++timeSidebarReqId
timeSidebarLoading.value = true
timeSidebarError.value = ''

try {
  const resp = await api.getChatMessageDailyCounts({
    account: selectedAccount.value,
    username: selectedContact.value.username,
    year: y,
    month: m
  })
  if (reqId !== timeSidebarReqId) return
  if (String(resp?.status || '') !== 'success') {
    throw new Error(String(resp?.message || '加载日历失败'))
  }

  const data = {
    counts: resp?.counts || {},
    max: Number(resp?.max || 0),
    total: Number(resp?.total || 0)
  }

  _applyTimeSidebarMonthData(data)
  timeSidebarCache.value = { ...timeSidebarCache.value, [key]: data }
} catch (e) {
  if (reqId !== timeSidebarReqId) return
  timeSidebarError.value = e?.message || '加载日历失败'
  _applyTimeSidebarMonthData({ counts: {}, max: 0, total: 0 })
} finally {
  if (reqId === timeSidebarReqId) {
    timeSidebarLoading.value = false
  }
}
}

const _pickTimeSidebarInitialYearMonth = () => {
const list = messages.value || []
const last = Array.isArray(list) && list.length ? list[list.length - 1] : null
const ts = Number(last?.createTime || 0)
const d = ts ? new Date(ts * 1000) : new Date()
return { year: d.getFullYear(), month: d.getMonth() + 1 }
}

const _applyTimeSidebarSelectedDate = async (dateStr, { syncMonth } = {}) => {
const ds = String(dateStr || '').trim()
if (!ds) return
if (timeSidebarSelectedDate.value !== ds) {
  timeSidebarSelectedDate.value = ds
}
if (!syncMonth || !timeSidebarOpen.value) return

const parts = ds.split('-')
const y = Number(parts?.[0] || 0)
const m = Number(parts?.[1] || 0)
if (!y || !m) return

if (Number(timeSidebarYear.value || 0) !== y || Number(timeSidebarMonth.value || 0) !== m) {
  timeSidebarYear.value = y
  timeSidebarMonth.value = m
  // Fire and forget; request id guard + cache inside loadTimeSidebarMonth will handle racing.
  await loadTimeSidebarMonth({ year: y, month: m, force: false })
}
}

const toggleTimeSidebar = async () => {
timeSidebarOpen.value = !timeSidebarOpen.value
if (!timeSidebarOpen.value) return
closeMessageSearch()

const { year, month } = _pickTimeSidebarInitialYearMonth()
timeSidebarYear.value = year
timeSidebarMonth.value = month

// Default selected day: current viewport's latest loaded message day (usually "latest").
const list = messages.value || []
const last = Array.isArray(list) && list.length ? list[list.length - 1] : null
const ds = _dateStrFromEpochSeconds(Number(last?.createTime || 0))
if (ds) await _applyTimeSidebarSelectedDate(ds, { syncMonth: false })

await loadTimeSidebarMonth({ year, month, force: false })
}

const prevTimeSidebarMonth = async () => {
const y0 = Number(timeSidebarYear.value || 0)
const m0 = Number(timeSidebarMonth.value || 0)
if (!y0 || !m0) return
const y = m0 === 1 ? (y0 - 1) : y0
const m = m0 === 1 ? 12 : (m0 - 1)
await loadTimeSidebarMonth({ year: y, month: m, force: false })
}

const nextTimeSidebarMonth = async () => {
const y0 = Number(timeSidebarYear.value || 0)
const m0 = Number(timeSidebarMonth.value || 0)
if (!y0 || !m0) return
const y = m0 === 12 ? (y0 + 1) : y0
const m = m0 === 12 ? 1 : (m0 + 1)
await loadTimeSidebarMonth({ year: y, month: m, force: false })
}

const onTimeSidebarYearMonthChange = async () => {
if (!timeSidebarOpen.value) return
const y = Number(timeSidebarYear.value || 0)
const m = Number(timeSidebarMonth.value || 0)
if (!y || !m) return
await loadTimeSidebarMonth({ year: y, month: m, force: false })
}

const ensureMessageSearchScopeValid = () => {
if (messageSearchScope.value === 'conversation' && !selectedContact.value) {
  messageSearchScope.value = 'global'
}
}

const toggleMessageSearch = async () => {
const nextOpen = !messageSearchOpen.value
logSearchPhase('message-search:toggle', {
  nextOpen,
  queryLength: String(messageSearchQuery.value || '').trim().length,
  resultCount: Number(messageSearchResults.value?.length || 0)
})
messageSearchOpen.value = nextOpen
ensureMessageSearchScopeValid()
if (!messageSearchOpen.value) {
  closeMessageSearch('toggle-close')
  return
}
closeTimeSidebar()
await nextTick()
try {
  messageSearchInputRef.value?.focus?.()
} catch {}
logSearchPhase('message-search:open:ready', {
  scope: String(messageSearchScope.value || 'conversation'),
  selectedContactUsername: String(selectedContact.value?.username || '').trim()
})
await fetchMessageSearchIndexStatus()
await fetchMessageSearchSenders()
if (String(messageSearchQuery.value || '').trim()) {
  await runMessageSearch({ reset: true, source: 'toggle-open-with-query' })
}
}

let messageSearchReqId = 0

const runMessageSearch = async ({ reset, source = 'unknown' } = {}) => {
if (!selectedAccount.value) {
  logSearchPhase('runMessageSearch:skip:no-account', buildRunSearchLogDetails({ source, reset }))
  return
}
ensureMessageSearchScopeValid()

const q = String(messageSearchQuery.value || '').trim()
logSearchPhase('runMessageSearch:start', buildRunSearchLogDetails({ source, reset }))
if (!q) {
  logSearchPhase('runMessageSearch:skip:empty-query', buildRunSearchLogDetails({ source, reset }))
  messageSearchResults.value = []
  messageSearchHasMore.value = false
  messageSearchError.value = ''
  messageSearchSelectedIndex.value = -1
  messageSearchBackendStatus.value = ''
  messageSearchTotal.value = 0
  stopMessageSearchIndexPolling()
  return
}

if (reset) {
  messageSearchOffset.value = 0
  messageSearchResults.value = []
  messageSearchSelectedIndex.value = -1
}

const reqId = ++messageSearchReqId
messageSearchLoading.value = true
messageSearchError.value = ''
messageSearchBackendStatus.value = ''
logSearchPhase('runMessageSearch:request:start', {
  ...buildRunSearchLogDetails({ source, reset }),
  reqId
})

const scope = String(messageSearchScope.value || 'conversation')

const params = {
  account: selectedAccount.value,
  q,
  limit: messageSearchLimit,
  offset: messageSearchOffset.value
}

params.render_types = 'text'

const range = String(messageSearchRangeDays.value || '')
if (range === 'custom') {
  const start = dateToUnixSeconds(messageSearchStartDate.value, false)
  const end = dateToUnixSeconds(messageSearchEndDate.value, true)
  if (start != null) params.start_time = start
  if (end != null) params.end_time = end
  if (start != null && end != null && start > end) {
    messageSearchLoading.value = false
    messageSearchError.value = '时间范围不合法：开始日期不能晚于结束日期'
    return
  }
} else {
  const days = Number(range || 0)
  if (days > 0 && Number.isFinite(days)) {
    const end = Math.floor(Date.now() / 1000)
    const start = Math.max(0, end - Math.floor(days * 24 * 3600))
    params.start_time = start
    params.end_time = end
  }
}

if (scope === 'global') {
  const st = String(messageSearchSessionType.value || '').trim()
  if (st) params.session_type = st
}

if (String(messageSearchSender.value || '').trim()) {
  params.sender = String(messageSearchSender.value || '').trim()
}

if (scope === 'conversation') {
  if (!selectedContact.value?.username) {
    logSearchPhase('runMessageSearch:skip:no-selected-contact', buildRunSearchLogDetails({ source, reset }))
    messageSearchLoading.value = false
    messageSearchError.value = '请选择一个会话再搜索'
    return
  }
  params.username = selectedContact.value.username
}

try {
  const resp = await api.searchChatMessages(params)
  if (reqId !== messageSearchReqId) {
    logSearchPhase('runMessageSearch:response:stale', {
      ...buildRunSearchLogDetails({ source, reset }),
      reqId,
      activeReqId: Number(messageSearchReqId || 0),
      status: String(resp?.status || '').trim()
    })
    return
  }

  if (resp?.index) {
    messageSearchIndexInfo.value = resp.index
  }

  const status = String(resp?.status || 'success')
  messageSearchBackendStatus.value = status

  if (status === 'index_building') {
    logSearchPhase('runMessageSearch:response:index-building', {
      ...buildRunSearchLogDetails({ source, reset }),
      reqId,
      status
    })
    if (reset) {
      messageSearchResults.value = []
      messageSearchSelectedIndex.value = -1
    }
    messageSearchHasMore.value = false
    messageSearchTotal.value = 0
    ensureMessageSearchIndexPolling()
    return
  }

  if (status === 'index_error') {
    logSearchPhase('runMessageSearch:response:index-error', {
      ...buildRunSearchLogDetails({ source, reset }),
      reqId,
      status,
      message: String(resp?.message || '')
    })
    if (reset) {
      messageSearchResults.value = []
      messageSearchSelectedIndex.value = -1
    }
    messageSearchHasMore.value = false
    messageSearchTotal.value = 0
    messageSearchError.value = String(resp?.message || '索引错误')
    stopMessageSearchIndexPolling()
    return
  }

  if (status !== 'success') {
    logSearchPhase('runMessageSearch:response:non-success', {
      ...buildRunSearchLogDetails({ source, reset }),
      reqId,
      status,
      message: String(resp?.message || '')
    })
    if (reset) {
      messageSearchResults.value = []
      messageSearchSelectedIndex.value = -1
    }
    messageSearchHasMore.value = false
    messageSearchTotal.value = 0
    messageSearchError.value = String(resp?.message || '搜索失败')
    stopMessageSearchIndexPolling()
    return
  }

  const hits = Array.isArray(resp?.hits) ? resp.hits : []
  if (reset) {
    messageSearchResults.value = hits
  } else {
    messageSearchResults.value = [...messageSearchResults.value, ...hits]
  }
  messageSearchHasMore.value = !!resp?.hasMore
  messageSearchTotal.value = Number(resp?.total ?? resp?.totalInScan ?? 0)
  stopMessageSearchIndexPolling()

  if (messageSearchSelectedIndex.value < 0 && messageSearchResults.value.length) {
    messageSearchSelectedIndex.value = 0
  }

  logSearchPhase('runMessageSearch:response:success', {
    ...buildRunSearchLogDetails({ source, reset }),
    reqId,
    status,
    hitsCount: hits.length,
    total: Number(resp?.total ?? resp?.totalInScan ?? 0),
    hasMore: !!resp?.hasMore,
    backendScope: String(resp?.scope || '').trim(),
    backendUsername: String(resp?.username || '').trim()
  })

  // 保存搜索历史（仅在有结果时保存）
  if (!privacyMode.value && reset && hits.length > 0) {
    saveSearchHistory(q)
  }
} catch (e) {
  if (reqId !== messageSearchReqId) return
  messageSearchError.value = e?.message || '搜索失败'
  logSearchPhase('runMessageSearch:error', {
    ...buildRunSearchLogDetails({ source, reset }),
    reqId,
    error: String(e?.message || e || '')
  })
} finally {
  if (reqId === messageSearchReqId) {
    messageSearchLoading.value = false
    logSearchPhase('runMessageSearch:finalize', {
      ...buildRunSearchLogDetails({ source, reset }),
      reqId,
      loading: !!messageSearchLoading.value,
      error: String(messageSearchError.value || '')
    })
  }
}
}

const loadMoreSearchResults = async () => {
if (!messageSearchHasMore.value) return
if (messageSearchLoading.value) return
messageSearchOffset.value = Number(messageSearchOffset.value || 0) + messageSearchLimit
await runMessageSearch({ reset: false, source: 'load-more' })
}

const exitSearchContext = async () => {
if (!searchContext.value?.active) return
const u = String(searchContext.value.username || '').trim()
const saved = searchContext.value.savedMessages
const savedMeta = searchContext.value.savedMeta

if (u && saved) {
  allMessages.value = { ...allMessages.value, [u]: saved }
}
if (u && savedMeta) {
  messagesMeta.value = { ...messagesMeta.value, [u]: savedMeta }
}

searchContext.value = {
  active: false,
  kind: 'search',
  label: '',
  username: '',
  anchorId: '',
  anchorIndex: -1,
  hasMoreBefore: false,
  hasMoreAfter: false,
  loadingBefore: false,
  loadingAfter: false,
  savedMessages: null,
  savedMeta: null
}
highlightMessageId.value = ''
await nextTick()
updateJumpToBottomState()
}

const locateSearchHit = async (hit) => {
if (!process.client) return
if (!selectedAccount.value) {
  logSearchPhase('locateSearchHit:skip:no-account', {
    hitId: String(hit?.id || '').trim(),
    hitUsername: String(hit?.username || '').trim()
  })
  return
}
if (!hit?.id) {
  logSearchPhase('locateSearchHit:skip:missing-hit-id', {
    hitKeys: Object.keys(hit || {})
  })
  return
}

const targetUsername = String(hit?.username || selectedContact.value?.username || '').trim()
if (!targetUsername) {
  logSearchPhase('locateSearchHit:skip:missing-target-username', {
    hitId: String(hit?.id || '').trim(),
    hitUsername: String(hit?.username || '').trim(),
    selectedUsernameFallback: String(selectedContact.value?.username || '').trim()
  })
  return
}

logSearchPhase('locateSearchHit:start', {
  hitId: String(hit?.id || '').trim(),
  hitUsername: String(hit?.username || '').trim(),
  targetUsername,
  conversationName: String(hit?.conversationName || '').trim()
})

const targetContact = resolveSearchTargetContact({
  username: targetUsername,
  displayName: String(hit?.conversationName || hit?.username || targetUsername).trim(),
  avatar: String(hit?.conversationAvatar || hit?.senderAvatar || '').trim(),
  isGroup: targetUsername.endsWith('@chatroom')
})
logSearchPhase('locateSearchHit:target-resolved', {
  hitId: String(hit?.id || '').trim(),
  targetUsername,
  contactResolved: !!targetContact,
  contactSource: targetContact
    ? (contacts.value.find((c) => String(c?.username || '').trim() === targetUsername) ? 'contacts' : 'transient')
    : 'none'
})
if (targetContact && selectedContact.value?.username !== targetUsername) {
  logSearchPhase('locateSearchHit:selectContact:start', {
    hitId: String(hit?.id || '').trim(),
    targetUsername
  })
  await selectContact(targetContact, { skipLoadMessages: true })
  logSearchPhase('locateSearchHit:selectContact:done', {
    hitId: String(hit?.id || '').trim(),
    targetUsername
  })
}

if (searchContext.value?.active && searchContext.value.username !== targetUsername) {
  await exitSearchContext()
  logSearchPhase('locateSearchHit:exitSearchContext:done', {
    hitId: String(hit?.id || '').trim(),
    targetUsername
  })
}

if (!searchContext.value?.active) {
  searchContext.value = {
    active: true,
    kind: 'search',
    label: '',
    username: targetUsername,
    anchorId: String(hit.id),
    anchorIndex: -1,
    hasMoreBefore: true,
    hasMoreAfter: true,
    loadingBefore: false,
    loadingAfter: false,
    savedMessages: allMessages.value[targetUsername] || [],
    savedMeta: messagesMeta.value[targetUsername] || null
  }
} else {
  searchContext.value.kind = 'search'
  searchContext.value.label = ''
  searchContext.value.anchorId = String(hit.id)
  searchContext.value.hasMoreBefore = true
  searchContext.value.hasMoreAfter = true
  searchContext.value.loadingBefore = false
  searchContext.value.loadingAfter = false
}
logSearchPhase('locateSearchHit:search-context:ready', {
  hitId: String(hit?.id || '').trim(),
  targetUsername,
  contextActive: !!searchContext.value?.active,
  savedMessagesCount: Number(searchContext.value?.savedMessages?.length || 0)
})

try {
  logSearchPhase('locateSearchHit:messagesAround:start', {
    hitId: String(hit?.id || '').trim(),
    targetUsername,
    before: 35,
    after: 35
  })
  const resp = await api.getChatMessagesAround({
    account: selectedAccount.value,
    username: targetUsername,
    anchor_id: String(hit.id),
    before: 35,
    after: 35
  })

  const raw = resp?.messages || []
  const mapped = raw.map(normalizeMessage)
  allMessages.value = { ...allMessages.value, [targetUsername]: mapped }
  messagesMeta.value = { ...messagesMeta.value, [targetUsername]: { total: mapped.length, hasMore: false } }
  logSearchPhase('locateSearchHit:messagesAround:end', {
    hitId: String(hit?.id || '').trim(),
    targetUsername,
    messageCount: mapped.length,
    anchorId: String(resp?.anchorId || hit?.id || '').trim(),
    anchorIndex: Number(resp?.anchorIndex ?? -1)
  })

  searchContext.value.anchorId = String(resp?.anchorId || hit.id)
  searchContext.value.anchorIndex = Number(resp?.anchorIndex ?? -1)

  logSearchPhase('locateSearchHit:scroll:start', {
    hitId: String(hit?.id || '').trim(),
    targetUsername,
    anchorId: String(searchContext.value.anchorId || '').trim(),
    messageCount: mapped.length
  })
  const ok = await scrollToMessageId(searchContext.value.anchorId)
  logSearchPhase('locateSearchHit:scroll:end', {
    hitId: String(hit?.id || '').trim(),
    targetUsername,
    anchorId: String(searchContext.value.anchorId || '').trim(),
    scrollFound: !!ok
  })
  if (ok) flashMessage(searchContext.value.anchorId)
} catch (e) {
  logSearchPhase('locateSearchHit:error', {
    hitId: String(hit?.id || '').trim(),
    targetUsername,
    error: String(e?.message || e || '')
  })
  window.alert(e?.message || '定位失败')
}
}

const locateByAnchorId = async ({ targetUsername, anchorId, kind, label } = {}) => {
if (!process.client) return
if (!selectedAccount.value) return
const u = String(targetUsername || selectedContact.value?.username || '').trim()
const anchor = String(anchorId || '').trim()
if (!u || !anchor) return

const targetContact = resolveSearchTargetContact({
  username: u,
  displayName: String(selectedContact.value?.name || u).trim(),
  avatar: String(selectedContact.value?.avatar || '').trim(),
  isGroup: u.endsWith('@chatroom')
})
if (targetContact && selectedContact.value?.username !== u) {
  await selectContact(targetContact, { skipLoadMessages: true })
}

if (searchContext.value?.active && searchContext.value.username !== u) {
  await exitSearchContext()
}

const kindNorm = String(kind || 'search').trim() || 'search'
const labelNorm = String(label || '').trim()
const hasMoreBeforeInit = kindNorm === 'first' ? false : true

if (!searchContext.value?.active) {
  searchContext.value = {
    active: true,
    kind: kindNorm,
    label: labelNorm,
    username: u,
    anchorId: anchor,
    anchorIndex: -1,
    hasMoreBefore: hasMoreBeforeInit,
    hasMoreAfter: true,
    loadingBefore: false,
    loadingAfter: false,
    savedMessages: allMessages.value[u] || [],
    savedMeta: messagesMeta.value[u] || null
  }
} else {
  searchContext.value.kind = kindNorm
  searchContext.value.label = labelNorm
  searchContext.value.anchorId = anchor
  searchContext.value.username = u
  searchContext.value.hasMoreBefore = hasMoreBeforeInit
  searchContext.value.hasMoreAfter = true
  searchContext.value.loadingBefore = false
  searchContext.value.loadingAfter = false
}

try {
  const resp = await api.getChatMessagesAround({
    account: selectedAccount.value,
    username: u,
    anchor_id: anchor,
    before: 35,
    after: 35
  })

  const raw = resp?.messages || []
  const mapped = raw.map(normalizeMessage)
  allMessages.value = { ...allMessages.value, [u]: mapped }
  messagesMeta.value = { ...messagesMeta.value, [u]: { total: mapped.length, hasMore: false } }

  searchContext.value.anchorId = String(resp?.anchorId || anchor)
  searchContext.value.anchorIndex = Number(resp?.anchorIndex ?? -1)

  const ok = await scrollToMessageId(searchContext.value.anchorId)
  if (ok) flashMessage(searchContext.value.anchorId)
} catch (e) {
  window.alert(e?.message || '定位失败')
}
}

const locateByDate = async (dateStr) => {
if (!process.client) return
if (!selectedAccount.value) return
if (!selectedContact.value?.username) return

const ds = String(dateStr || '').trim()
if (!ds) return
await _applyTimeSidebarSelectedDate(ds, { syncMonth: true })

try {
  const resp = await api.getChatMessageAnchor({
    account: selectedAccount.value,
    username: selectedContact.value.username,
    kind: 'day',
    date: ds
  })
  const status = String(resp?.status || '')
  const anchorId = String(resp?.anchorId || '').trim()
  if (status !== 'success' || !anchorId) {
    window.alert('当日暂无聊天记录')
    return
  }
  await locateByAnchorId({ targetUsername: selectedContact.value.username, anchorId, kind: 'date', label: ds })
} catch (e) {
  window.alert(e?.message || '定位失败')
}
}

const jumpToConversationFirst = async () => {
if (!process.client) return
if (!selectedAccount.value) return
if (!selectedContact.value?.username) return

try {
  const resp = await api.getChatMessageAnchor({
    account: selectedAccount.value,
    username: selectedContact.value.username,
    kind: 'first'
  })
  const status = String(resp?.status || '')
  const anchorId = String(resp?.anchorId || '').trim()
  if (status !== 'success' || !anchorId) {
    window.alert('暂无聊天记录')
    return
  }
  const ds = _dateStrFromEpochSeconds(Number(resp?.createTime || 0))
  if (ds) await _applyTimeSidebarSelectedDate(ds, { syncMonth: true })
  await locateByAnchorId({ targetUsername: selectedContact.value.username, anchorId, kind: 'first', label: '' })
} catch (e) {
  window.alert(e?.message || '定位失败')
}
}

const onTimeSidebarDayClick = async (cell) => {
if (!cell || cell.disabled) return
const ds = String(cell.dateStr || '').trim()
if (!ds) return
await locateByDate(ds)
}

const _mergeContextMessages = (username, nextList) => {
const u = String(username || '').trim()
if (!u) return
const list = Array.isArray(nextList) ? nextList : []
allMessages.value = { ...allMessages.value, [u]: list }
// Keep meta aligned; context mode doesn't rely on hasMore from meta.
const prevMeta = messagesMeta.value[u] || null
messagesMeta.value = {
  ...messagesMeta.value,
  [u]: {
    total: Math.max(Number(prevMeta?.total || 0), list.length),
    hasMore: false
  }
}
}

const loadMoreSearchContextAfter = async () => {
if (!process.client) return
if (!selectedAccount.value) return
if (!searchContext.value?.active) return
if (searchContext.value.loadingAfter) return
if (!searchContext.value.hasMoreAfter) return

const u = String(searchContext.value.username || selectedContact.value?.username || '').trim()
if (!u) return
const existing = allMessages.value[u] || []
const last = Array.isArray(existing) && existing.length ? existing[existing.length - 1] : null
const anchorId = String(last?.id || '').trim()
if (!anchorId) {
  searchContext.value.hasMoreAfter = false
  return
}

const ctxUsername = u
searchContext.value.loadingAfter = true
try {
  const resp = await api.getChatMessagesAround({
    account: selectedAccount.value,
    username: ctxUsername,
    anchor_id: anchorId,
    before: 0,
    after: messagePageSize
  })

  if (!searchContext.value?.active || String(searchContext.value.username || '').trim() !== ctxUsername) return

  const raw = resp?.messages || []
  const mapped = raw.map(normalizeMessage)

  const existingIds = new Set(existing.map((m) => String(m?.id || '')))
  const appended = []
  for (const m of mapped) {
    const id = String(m?.id || '').trim()
    if (!id) continue
    if (existingIds.has(id)) continue
    existingIds.add(id)
    appended.push(m)
  }

  if (!appended.length) {
    searchContext.value.hasMoreAfter = false
    return
  }

  _mergeContextMessages(ctxUsername, [...existing, ...appended])
} catch (e) {
  window.alert(e?.message || '加载更多消息失败')
} finally {
  if (searchContext.value?.active && String(searchContext.value.username || '').trim() === ctxUsername) {
    searchContext.value.loadingAfter = false
  }
}
}

const loadMoreSearchContextBefore = async () => {
if (!process.client) return
if (!selectedAccount.value) return
if (!searchContext.value?.active) return
if (searchContext.value.loadingBefore) return
if (!searchContext.value.hasMoreBefore) return

const u = String(searchContext.value.username || selectedContact.value?.username || '').trim()
if (!u) return
const existing = allMessages.value[u] || []
const first = Array.isArray(existing) && existing.length ? existing[0] : null
const anchorId = String(first?.id || '').trim()
if (!anchorId) {
  searchContext.value.hasMoreBefore = false
  return
}

const c = messageContainerRef.value
const beforeScrollHeight = c ? c.scrollHeight : 0
const beforeScrollTop = c ? c.scrollTop : 0

const ctxUsername = u
searchContext.value.loadingBefore = true
try {
  const resp = await api.getChatMessagesAround({
    account: selectedAccount.value,
    username: ctxUsername,
    anchor_id: anchorId,
    before: messagePageSize,
    after: 0
  })

  if (!searchContext.value?.active || String(searchContext.value.username || '').trim() !== ctxUsername) return

  const raw = resp?.messages || []
  const mapped = raw.map(normalizeMessage)

  const existingIds = new Set(existing.map((m) => String(m?.id || '')))
  const prepended = []
  for (const m of mapped) {
    const id = String(m?.id || '').trim()
    if (!id) continue
    if (existingIds.has(id)) continue
    existingIds.add(id)
    prepended.push(m)
  }

  if (!prepended.length) {
    searchContext.value.hasMoreBefore = false
    return
  }

  _mergeContextMessages(ctxUsername, [...prepended, ...existing])

  await nextTick()
  const c2 = messageContainerRef.value
  if (c2) {
    const afterScrollHeight = c2.scrollHeight
    c2.scrollTop = beforeScrollTop + (afterScrollHeight - beforeScrollHeight)
  }
} catch (e) {
  window.alert(e?.message || '加载更多消息失败')
} finally {
  if (searchContext.value?.active && String(searchContext.value.username || '').trim() === ctxUsername) {
    searchContext.value.loadingBefore = false
  }
}
}

const onSearchHitPointerDown = (hit, idx, event) => {
logSearchPhase('search-result:pointerdown', {
  ...summarizeHitForLog(hit, idx),
  button: Number(event?.button ?? -1),
  detail: Number(event?.detail ?? 0),
  target: describeEventTarget(event?.target),
  currentTarget: describeEventTarget(event?.currentTarget)
})
}

const onSearchHitClickCapture = (hit, idx, event) => {
logSearchPhase('search-result:click-capture', {
  ...summarizeHitForLog(hit, idx),
  button: Number(event?.button ?? -1),
  detail: Number(event?.detail ?? 0),
  target: describeEventTarget(event?.target),
  currentTarget: describeEventTarget(event?.currentTarget)
})
}

const onSearchHitClick = async (hit, idx) => {
messageSearchSelectedIndex.value = Number(idx || 0)
logSearchPhase('onSearchHitClick', {
  ...summarizeHitForLog(hit, idx),
  selectedIndex: Number(messageSearchSelectedIndex.value || 0)
})
await locateSearchHit(hit)
logSearchPhase('onSearchHitClick:done', {
  ...summarizeHitForLog(hit, idx),
  selectedIndex: Number(messageSearchSelectedIndex.value || 0)
})
}

const onSearchNext = async () => {
const q = String(messageSearchQuery.value || '').trim()
if (!q) return

if (!messageSearchResults.value.length && !messageSearchLoading.value) {
  await runMessageSearch({ reset: true, source: 'search-next-bootstrap' })
}
if (!messageSearchResults.value.length) return

const cur = Number(messageSearchSelectedIndex.value || 0)
const next = (cur + 1) % messageSearchResults.value.length
messageSearchSelectedIndex.value = next
await locateSearchHit(messageSearchResults.value[next])
}

const onSearchPrev = async () => {
const q = String(messageSearchQuery.value || '').trim()
if (!q) return

if (!messageSearchResults.value.length && !messageSearchLoading.value) {
  await runMessageSearch({ reset: true, source: 'search-prev-bootstrap' })
}
if (!messageSearchResults.value.length) return

const cur = Number(messageSearchSelectedIndex.value || 0)
const prev = (cur - 1 + messageSearchResults.value.length) % messageSearchResults.value.length
messageSearchSelectedIndex.value = prev
await locateSearchHit(messageSearchResults.value[prev])
}
const openMessageSearch = async () => {
closeTimeSidebar()
messageSearchOpen.value = true
ensureMessageSearchScopeValid()
logSearchPhase('message-search:open:start', {
  scope: String(messageSearchScope.value || 'conversation'),
  queryLength: String(messageSearchQuery.value || '').trim().length
})
await nextTick()
try {
  messageSearchInputRef.value?.focus?.()
} catch {}
await fetchMessageSearchIndexStatus()
logSearchPhase('message-search:open:end', {
  scope: String(messageSearchScope.value || 'conversation'),
  queryLength: String(messageSearchQuery.value || '').trim().length
})
}
watch(messageSearchScope, async (next, prev) => {
logSearchPhase('message-search-scope:change', {
  previous: String(prev || '').trim(),
  next: String(next || '').trim(),
  open: !!messageSearchOpen.value,
  queryLength: String(messageSearchQuery.value || '').trim().length
})
if (!messageSearchOpen.value) return
ensureMessageSearchScopeValid()
closeMessageSearchSenderDropdown()
messageSearchSender.value = ''
messageSearchSenderOptions.value = []
messageSearchSenderOptionsKey.value = ''
await fetchMessageSearchSenders()
messageSearchOffset.value = 0
messageSearchResults.value = []
messageSearchSelectedIndex.value = -1
if (String(messageSearchQuery.value || '').trim()) {
  await runMessageSearch({ reset: true, source: 'scope-change' })
}
})

watch(messageSearchRangeDays, async (next, prev) => {
logSearchPhase('message-search-range:change', {
  previous: String(prev || '').trim(),
  next: String(next || '').trim(),
  open: !!messageSearchOpen.value,
  queryLength: String(messageSearchQuery.value || '').trim().length
})
if (!messageSearchOpen.value) return
closeMessageSearchSenderDropdown()
messageSearchOffset.value = 0
messageSearchResults.value = []
messageSearchSelectedIndex.value = -1
if (String(messageSearchQuery.value || '').trim()) {
  await runMessageSearch({ reset: true, source: 'range-change' })
}
})

watch(messageSearchSessionType, async (next, prev) => {
logSearchPhase('message-search-session-type:change', {
  previous: String(prev || '').trim(),
  next: String(next || '').trim(),
  open: !!messageSearchOpen.value,
  queryLength: String(messageSearchQuery.value || '').trim().length
})
if (!messageSearchOpen.value) return
if (String(messageSearchScope.value || '') !== 'global') return
closeMessageSearchSenderDropdown()
messageSearchSender.value = ''
messageSearchSenderOptions.value = []
messageSearchSenderOptionsKey.value = ''
await fetchMessageSearchSenders()
messageSearchOffset.value = 0
messageSearchResults.value = []
messageSearchSelectedIndex.value = -1
if (String(messageSearchQuery.value || '').trim()) {
  await runMessageSearch({ reset: true, source: 'session-type-change' })
}
})

watch([messageSearchStartDate, messageSearchEndDate], async ([nextStart, nextEnd], [prevStart, prevEnd]) => {
logSearchPhase('message-search-custom-range:change', {
  previousStart: String(prevStart || '').trim(),
  previousEnd: String(prevEnd || '').trim(),
  nextStart: String(nextStart || '').trim(),
  nextEnd: String(nextEnd || '').trim(),
  open: !!messageSearchOpen.value
})
if (!messageSearchOpen.value) return
if (String(messageSearchRangeDays.value || '') !== 'custom') return
closeMessageSearchSenderDropdown()
messageSearchOffset.value = 0
messageSearchResults.value = []
messageSearchSelectedIndex.value = -1
if (String(messageSearchQuery.value || '').trim()) {
  await runMessageSearch({ reset: true, source: 'custom-range-change' })
}
})

watch(messageSearchSender, async (next, prev) => {
logSearchPhase('message-search-sender:change', {
  previous: String(prev || '').trim(),
  next: String(next || '').trim(),
  open: !!messageSearchOpen.value,
  queryLength: String(messageSearchQuery.value || '').trim().length
})
if (!messageSearchOpen.value) return
messageSearchOffset.value = 0
messageSearchResults.value = []
messageSearchSelectedIndex.value = -1
if (String(messageSearchQuery.value || '').trim()) {
  await runMessageSearch({ reset: true, source: 'sender-change' })
}
})

watch(messageSearchQuery, (next, prev) => {
logSearchPhase('message-search-query:change', {
  previousLength: String(prev || '').trim().length,
  nextLength: String(next || '').trim().length,
  open: !!messageSearchOpen.value
})
if (!messageSearchOpen.value) return
if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
messageSearchDebounceTimer = null
const q = String(messageSearchQuery.value || '').trim()
if (q.length < 2) {
  logSearchPhase('message-search-query:debounce:skip-short', {
    queryLength: q.length
  })
  return
}
logSearchPhase('message-search-query:debounce:scheduled', {
  queryLength: q.length,
  delayMs: 280
})
messageSearchDebounceTimer = setTimeout(() => {
  logSearchPhase('message-search-query:debounce:fire', {
    queryLength: String(messageSearchQuery.value || '').trim().length
  })
  runMessageSearch({ reset: true, source: 'query-debounce' })
}, 280)
})

watch(
() => selectedContact.value?.username,
async () => {
  logSearchPhase('message-search-selected-contact:change', {
    open: !!messageSearchOpen.value,
    scope: String(messageSearchScope.value || '').trim(),
    selectedContactUsername: String(selectedContact.value?.username || '').trim()
  })
  if (!messageSearchOpen.value) return
  if (String(messageSearchScope.value || '') !== 'conversation') return
  closeMessageSearchSenderDropdown()
  messageSearchSender.value = ''
  messageSearchSenderOptions.value = []
  messageSearchSenderOptionsKey.value = ''
  await fetchMessageSearchSenders()
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true, source: 'selected-contact-change' })
  }
}
)

watch(messageSearchOpen, (next, prev) => {
logSearchPhase('message-search-open:change', {
  previous: !!prev,
  next: !!next,
  queryLength: String(messageSearchQuery.value || '').trim().length,
  resultCount: Number(messageSearchResults.value?.length || 0)
})
})

watch(messageSearchResults, (next, prev) => {
const nextList = Array.isArray(next) ? next : []
const prevList = Array.isArray(prev) ? prev : []
logSearchPhase('message-search-results:change', {
  previousCount: prevList.length,
  nextCount: nextList.length,
  firstHitId: String(nextList[0]?.id || '').trim(),
  selectedIndex: Number(messageSearchSelectedIndex.value ?? -1)
})
})

const autoLoadReady = ref(true)

let timeSidebarScrollSyncRaf = null
const syncTimeSidebarSelectedDateFromScroll = () => {
if (!process.client) return
if (!timeSidebarOpen.value) return
if (!selectedContact.value) return

const c = messageContainerRef.value
if (!c) return

if (timeSidebarScrollSyncRaf) return
timeSidebarScrollSyncRaf = requestAnimationFrame(() => {
  timeSidebarScrollSyncRaf = null
  try {
    const containerRect = c.getBoundingClientRect()
    const targetY = containerRect.top + 24
    const els = c.querySelectorAll?.('[data-msg-id][data-create-time]') || []
    if (!els || !els.length) return

    let chosen = null
    for (const el of els) {
      const r = el.getBoundingClientRect?.()
      if (!r) continue
      if (r.bottom >= targetY) {
        chosen = el
        break
      }
    }
    if (!chosen) chosen = els[els.length - 1]
    const ts = Number(chosen?.getAttribute?.('data-create-time') || 0)
    const ds = _dateStrFromEpochSeconds(ts)
    if (!ds) return
    // Don't await inside rAF; keep scroll handler snappy.
    _applyTimeSidebarSelectedDate(ds, { syncMonth: true })
  } catch {}
})
}

const contextAutoLoadTopReady = ref(true)
const contextAutoLoadBottomReady = ref(true)

const onMessageScrollInContextMode = async () => {
const c = messageContainerRef.value
if (!c) return
if (!searchContext.value?.active) return

const distBottom = c.scrollHeight - c.scrollTop - c.clientHeight

// Reset "ready" gates when user scrolls away from edges.
if (c.scrollTop > 160) contextAutoLoadTopReady.value = true
if (distBottom > 160) contextAutoLoadBottomReady.value = true

if (c.scrollTop <= 60 && contextAutoLoadTopReady.value && searchContext.value.hasMoreBefore && !searchContext.value.loadingBefore) {
  contextAutoLoadTopReady.value = false
  await loadMoreSearchContextBefore()
  return
}

if (distBottom <= 80 && contextAutoLoadBottomReady.value && searchContext.value.hasMoreAfter && !searchContext.value.loadingAfter) {
  contextAutoLoadBottomReady.value = false
  await loadMoreSearchContextAfter()
}
}

const onMessageScroll = async () => {
const c = messageContainerRef.value
if (!c) return
updateJumpToBottomState()
if (!selectedContact.value) return

// Keep the time sidebar selection in sync with the current viewport.
syncTimeSidebarSelectedDateFromScroll()

if (searchContext.value?.active) {
  await onMessageScrollInContextMode()
  return
}

if (c.scrollTop > 120) {
  autoLoadReady.value = true
  return
}

if (c.scrollTop <= 60 && autoLoadReady.value && hasMoreMessages.value && !isLoadingMessages.value) {
  autoLoadReady.value = false
  await loadMoreMessages()
}
}

  const resetSearchState = () => {
    closeMessageSearch()
    closeTimeSidebar()
    timeSidebarYear.value = null
    timeSidebarMonth.value = null
    _applyTimeSidebarMonthData({ counts: {}, max: 0, total: 0 })
    timeSidebarError.value = ''
    timeSidebarSelectedDate.value = ''
    messageSearchResults.value = []
    messageSearchOffset.value = 0
    messageSearchHasMore.value = false
    messageSearchBackendStatus.value = ''
    messageSearchTotal.value = 0
    messageSearchIndexInfo.value = null
    messageSearchSelectedIndex.value = -1
    searchContext.value = createEmptySearchContext()
    highlightMessageId.value = ''
  }

  onMounted(() => {
    loadSearchHistory()
  })

  onUnmounted(() => {
    if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
    messageSearchDebounceTimer = null
    stopMessageSearchIndexPolling()
    if (timeSidebarScrollSyncRaf) {
      cancelAnimationFrame(timeSidebarScrollSyncRaf)
      timeSidebarScrollSyncRaf = null
    }
  })

  return {
    messageSearchOpen,
    messageSearchQuery,
    messageSearchScope,
    messageSearchRangeDays,
    messageSearchSessionType,
    messageSearchSender,
    messageSearchSenderOptions,
    messageSearchSenderLoading,
    messageSearchSenderError,
    messageSearchSenderOptionsKey,
    messageSearchSenderDropdownOpen,
    messageSearchSenderDropdownRef,
    messageSearchSenderDropdownInputRef,
    messageSearchSenderDropdownQuery,
    messageSearchStartDate,
    messageSearchEndDate,
    messageSearchResults,
    messageSearchLoading,
    messageSearchError,
    messageSearchBackendStatus,
    messageSearchIndexInfo,
    messageSearchHasMore,
    messageSearchOffset,
    messageSearchTotal,
    messageSearchSelectedIndex,
    messageSearchInputRef,
    searchInputFocused,
    showAdvancedFilters,
    searchHistory,
    messageSearchIndexExists,
    messageSearchIndexReady,
    messageSearchIndexBuildStatus,
    messageSearchIndexBuildIndexed,
    messageSearchIndexMetaCount,
    messageSearchIndexProgressText,
    messageSearchIndexText,
    messageSearchIndexActionText,
    messageSearchIndexActionDisabled,
    messageSearchSenderDisabled,
    messageSearchSelectedSenderInfo,
    messageSearchSelectedSenderInitial,
    messageSearchSenderLabel,
    filteredMessageSearchSenderOptions,
    searchContextBannerText,
    timeSidebarOpen,
    timeSidebarYear,
    timeSidebarMonth,
    timeSidebarCounts,
    timeSidebarMax,
    timeSidebarTotal,
    timeSidebarLoading,
    timeSidebarError,
    timeSidebarSelectedDate,
    timeSidebarWeekdays,
    timeSidebarMonthLabel,
    timeSidebarYearOptions,
    timeSidebarActiveDays,
    timeSidebarCalendarCells,
    getMessageSearchHitAvatarUrl,
    getMessageSearchHitAvatarAlt,
    getMessageSearchHitAvatarInitial,
    closeMessageSearchSenderDropdown,
    ensureMessageSearchSendersLoaded,
    toggleMessageSearchSenderDropdown,
    selectMessageSearchSender,
    fetchMessageSearchIndexStatus,
    fetchMessageSearchSenders,
    onMessageSearchIndexAction,
    closeMessageSearch,
    closeTimeSidebar,
    loadTimeSidebarMonth,
    toggleTimeSidebar,
    prevTimeSidebarMonth,
    nextTimeSidebarMonth,
    onTimeSidebarYearMonthChange,
    toggleMessageSearch,
    openMessageSearch,
    runMessageSearch,
    loadMoreSearchResults,
    exitSearchContext,
    locateSearchHit,
    locateByAnchorId,
    locateByDate,
    jumpToConversationFirst,
    onTimeSidebarDayClick,
    loadMoreSearchContextAfter,
    loadMoreSearchContextBefore,
    onSearchHitPointerDown,
    onSearchHitClickCapture,
    onSearchHitClick,
    onSearchNext,
    onSearchPrev,
    syncTimeSidebarSelectedDateFromScroll,
    onMessageScrollInContextMode,
    onMessageScroll,
    clearSearchHistory,
    applySearchHistory,
    ensureMessageSearchScopeValid,
    resetSearchState
  }
}
