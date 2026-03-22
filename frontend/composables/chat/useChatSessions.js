import { computed, onMounted, ref } from 'vue'
import { normalizeSessionPreview } from '~/lib/chat/formatters'

const SESSION_LIST_WIDTH_KEY = 'ui.chat.session_list_width_physical'
const SESSION_LIST_WIDTH_KEY_LEGACY = 'ui.chat.session_list_width'
const SESSION_LIST_WIDTH_DEFAULT = 295
const SESSION_LIST_WIDTH_MIN = 220
const SESSION_LIST_WIDTH_MAX = 520

export const useChatSessions = ({ chatAccounts, selectedAccount, realtimeEnabled, api }) => {
  const showSearchAccountSwitcher = false

  const contacts = ref([])
  const selectedContact = ref(null)
  const searchQuery = ref('')
  const isLoadingContacts = ref(false)
  const contactsError = ref('')

  const sessionListWidth = ref(SESSION_LIST_WIDTH_DEFAULT)
  const sessionListResizing = ref(false)

  let sessionListResizeStartX = 0
  let sessionListResizeStartWidth = SESSION_LIST_WIDTH_DEFAULT
  let sessionListResizeStartDpr = 1
  let sessionListResizePrevCursor = ''
  let sessionListResizePrevUserSelect = ''

  const availableAccounts = computed(() => {
    return Array.isArray(chatAccounts?.accounts) ? chatAccounts.accounts : []
  })

  const clampSessionListWidth = (value) => {
    const next = Number.isFinite(value) ? value : SESSION_LIST_WIDTH_DEFAULT
    return Math.min(SESSION_LIST_WIDTH_MAX, Math.max(SESSION_LIST_WIDTH_MIN, Math.round(next)))
  }

  const loadSessionListWidth = () => {
    if (!process.client) return
    try {
      const raw = localStorage.getItem(SESSION_LIST_WIDTH_KEY)
      const value = parseInt(String(raw || ''), 10)
      if (!Number.isNaN(value)) {
        sessionListWidth.value = clampSessionListWidth(value)
        return
      }

      const legacy = localStorage.getItem(SESSION_LIST_WIDTH_KEY_LEGACY)
      const legacyValue = parseInt(String(legacy || ''), 10)
      if (!Number.isNaN(legacyValue)) {
        const dpr = window.devicePixelRatio || 1
        const converted = clampSessionListWidth(legacyValue * dpr)
        sessionListWidth.value = converted
        try {
          localStorage.setItem(SESSION_LIST_WIDTH_KEY, String(converted))
          localStorage.removeItem(SESSION_LIST_WIDTH_KEY_LEGACY)
        } catch {}
      }
    } catch {}
  }

  const saveSessionListWidth = () => {
    if (!process.client) return
    try {
      localStorage.setItem(SESSION_LIST_WIDTH_KEY, String(clampSessionListWidth(sessionListWidth.value)))
    } catch {}
  }

  const setSessionListResizingActive = (active) => {
    if (!process.client) return
    try {
      const body = document.body
      if (!body) return
      if (active) {
        sessionListResizePrevCursor = body.style.cursor || ''
        sessionListResizePrevUserSelect = body.style.userSelect || ''
        body.style.cursor = 'col-resize'
        body.style.userSelect = 'none'
      } else {
        body.style.cursor = sessionListResizePrevCursor
        body.style.userSelect = sessionListResizePrevUserSelect
        sessionListResizePrevCursor = ''
        sessionListResizePrevUserSelect = ''
      }
    } catch {}
  }

  const onSessionListResizerPointerMove = (event) => {
    if (!sessionListResizing.value) return
    const clientX = Number(event?.clientX || 0)
    sessionListWidth.value = clampSessionListWidth(
      sessionListResizeStartWidth + (clientX - sessionListResizeStartX) * (sessionListResizeStartDpr || 1)
    )
  }

  const stopSessionListResize = () => {
    if (!process.client) return
    if (!sessionListResizing.value) return
    sessionListResizing.value = false
    setSessionListResizingActive(false)
    try {
      window.removeEventListener('pointermove', onSessionListResizerPointerMove)
    } catch {}
    saveSessionListWidth()
  }

  const onSessionListResizerPointerUp = () => {
    stopSessionListResize()
  }

  const onSessionListResizerPointerDown = (event) => {
    if (!process.client) return
    try {
      event?.preventDefault?.()
    } catch {}

    sessionListResizing.value = true
    sessionListResizeStartX = Number(event?.clientX || 0)
    sessionListResizeStartWidth = Number(sessionListWidth.value || SESSION_LIST_WIDTH_DEFAULT)
    sessionListResizeStartDpr = window.devicePixelRatio || 1
    setSessionListResizingActive(true)

    try {
      window.addEventListener('pointermove', onSessionListResizerPointerMove)
      window.addEventListener('pointerup', onSessionListResizerPointerUp, { once: true })
    } catch {}
  }

  const resetSessionListWidth = () => {
    sessionListWidth.value = SESSION_LIST_WIDTH_DEFAULT
    saveSessionListWidth()
  }

  onMounted(() => {
    loadSessionListWidth()
  })

  const filteredContacts = computed(() => {
    const query = String(searchQuery.value || '').trim().toLowerCase()
    if (!query) return contacts.value
    return contacts.value.filter((contact) => {
      const name = String(contact?.name || '').toLowerCase()
      const username = String(contact?.username || '').toLowerCase()
      return name.includes(query) || username.includes(query)
    })
  })

  const mapSessions = (sessions) => {
    return sessions.map((session) => ({
      id: session.id,
      name: session.name || session.username || session.id,
      avatar: session.avatar || null,
      lastMessage: normalizeSessionPreview(session.lastMessage || ''),
      lastMessageTime: session.lastMessageTime || '',
      unreadCount: session.unreadCount || 0,
      isGroup: !!session.isGroup,
      isTop: !!session.isTop,
      username: session.username
    }))
  }

  const clearContactsState = (errorMessage = '') => {
    contacts.value = []
    selectedContact.value = null
    contactsError.value = errorMessage
  }

  const loadSessionsForSelectedAccount = async () => {
    if (!selectedAccount.value) {
      clearContactsState('')
      return []
    }

    const fetchSessions = async (source) => {
      const params = {
        account: selectedAccount.value,
        limit: 400,
        include_hidden: false,
        include_official: false
      }
      if (source) params.source = source
      return api.listChatSessions(params)
    }

    let sessionsResp = null
    if (realtimeEnabled?.value) {
      try {
        sessionsResp = await fetchSessions('realtime')
      } catch {
        sessionsResp = null
      }
    }
    if (!sessionsResp) {
      sessionsResp = await fetchSessions('')
    }

    const sessions = Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions : []
    contacts.value = mapSessions(sessions)
    contactsError.value = ''
    return contacts.value
  }

  const refreshSessionsForSelectedAccount = async ({ sourceOverride } = {}) => {
    if (!process.client || typeof window === 'undefined') return
    if (!selectedAccount.value) return
    if (isLoadingContacts.value) return

    const previousUsername = selectedContact.value?.username || ''
    const desiredSource = (sourceOverride != null)
      ? String(sourceOverride || '').trim()
      : (realtimeEnabled?.value ? 'realtime' : '')

    const params = {
      account: selectedAccount.value,
      limit: 400,
      include_hidden: false,
      include_official: false
    }

    let sessionsResp = null
    if (desiredSource) {
      try {
        sessionsResp = await api.listChatSessions({ ...params, source: desiredSource })
      } catch {
        sessionsResp = null
      }
    }
    if (!sessionsResp) {
      try {
        sessionsResp = await api.listChatSessions(params)
      } catch {
        return
      }
    }

    const sessions = Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions : []
    const nextContacts = mapSessions(sessions)
    contacts.value = nextContacts

    if (previousUsername) {
      const matched = nextContacts.find((contact) => contact.username === previousUsername)
      if (matched) selectedContact.value = matched
    }
  }

  const loadContacts = async () => {
    if (contacts.value.length && !isLoadingContacts.value) {
      return { usedPrefetched: true }
    }

    isLoadingContacts.value = true
    contactsError.value = ''
    try {
      const hadLoadedAccountSnapshot = !!chatAccounts.loaded
      await chatAccounts.ensureLoaded()
      if (!selectedAccount.value && hadLoadedAccountSnapshot) {
        await chatAccounts.ensureLoaded({ force: true })
      }

      if (!selectedAccount.value) {
        clearContactsState(chatAccounts.error || '未检测到已解密账号，请先解密数据库。')
        return { usedPrefetched: false }
      }

      await loadSessionsForSelectedAccount()
      return { usedPrefetched: false }
    } catch (error) {
      clearContactsState(error?.message || '加载联系人失败')
      return { usedPrefetched: false }
    } finally {
      isLoadingContacts.value = false
    }
  }

  return {
    showSearchAccountSwitcher,
    availableAccounts,
    contacts,
    selectedContact,
    searchQuery,
    filteredContacts,
    isLoadingContacts,
    contactsError,
    sessionListWidth,
    sessionListResizing,
    clearContactsState,
    loadContacts,
    loadSessionsForSelectedAccount,
    refreshSessionsForSelectedAccount,
    onSessionListResizerPointerDown,
    stopSessionListResize,
    resetSessionListWidth
  }
}
