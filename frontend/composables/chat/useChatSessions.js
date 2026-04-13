import { computed, onMounted, ref } from 'vue'
import { normalizeSessionPreview } from '~/lib/chat/formatters'
import { createPerfTrace } from '~/lib/chat/perf-logger'

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

    const trace = createPerfTrace('chat-sessions', {
      account: String(selectedAccount.value || '').trim(),
      action: 'loadSessionsForSelectedAccount'
    })
    trace.log('loadSessions:start', {
      realtimeEnabled: !!realtimeEnabled?.value
    })

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
        trace.log('loadSessions:request:start', {
          source: 'realtime'
        })
        sessionsResp = await fetchSessions('realtime')
        trace.log('loadSessions:request:end', {
          source: 'realtime',
          rawCount: Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions.length : 0
        })
      } catch {
        sessionsResp = null
        trace.log('loadSessions:request:error', {
          source: 'realtime'
        })
      }
    }
    if (!sessionsResp) {
      trace.log('loadSessions:request:start', {
        source: 'default'
      })
      sessionsResp = await fetchSessions('')
      trace.log('loadSessions:request:end', {
        source: 'default',
        rawCount: Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions.length : 0
      })
    }

    const sessions = Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions : []
    contacts.value = mapSessions(sessions)
    contactsError.value = ''
    trace.log('loadSessions:end', {
      contactCount: contacts.value.length
    })
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
    const trace = createPerfTrace('chat-sessions', {
      account: String(selectedAccount.value || '').trim(),
      action: 'refreshSessionsForSelectedAccount',
      desiredSource
    })
    trace.log('refreshSessions:start', {
      previousUsername
    })

    const params = {
      account: selectedAccount.value,
      limit: 400,
      include_hidden: false,
      include_official: false
    }

    let sessionsResp = null
    if (desiredSource) {
      try {
        trace.log('refreshSessions:request:start', {
          source: desiredSource
        })
        sessionsResp = await api.listChatSessions({ ...params, source: desiredSource })
        trace.log('refreshSessions:request:end', {
          source: desiredSource,
          rawCount: Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions.length : 0
        })
      } catch {
        sessionsResp = null
        trace.log('refreshSessions:request:error', {
          source: desiredSource
        })
      }
    }
    if (!sessionsResp) {
      try {
        trace.log('refreshSessions:request:start', {
          source: 'default'
        })
        sessionsResp = await api.listChatSessions(params)
        trace.log('refreshSessions:request:end', {
          source: 'default',
          rawCount: Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions.length : 0
        })
      } catch {
        trace.log('refreshSessions:request:error', {
          source: 'default'
        })
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
    trace.log('refreshSessions:end', {
      contactCount: nextContacts.length,
      selectedUsername: String(selectedContact.value?.username || '').trim()
    })
  }

  const loadContacts = async () => {
    if (contacts.value.length && !isLoadingContacts.value) {
      return { usedPrefetched: true }
    }

    isLoadingContacts.value = true
    contactsError.value = ''
    const trace = createPerfTrace('chat-sessions', {
      account: String(selectedAccount.value || '').trim(),
      action: 'loadContacts'
    })
    trace.log('loadContacts:start', {
      cachedContacts: contacts.value.length
    })
    try {
      const hadLoadedAccountSnapshot = !!chatAccounts.loaded
      await chatAccounts.ensureLoaded()
      trace.log('loadContacts:accounts-ready', {
        hadLoadedAccountSnapshot,
        availableAccounts: Array.isArray(chatAccounts?.accounts) ? chatAccounts.accounts.length : 0
      })
      if (!selectedAccount.value && hadLoadedAccountSnapshot) {
        await chatAccounts.ensureLoaded({ force: true })
        trace.log('loadContacts:accounts-refreshed')
      }

      if (!selectedAccount.value) {
        clearContactsState(chatAccounts.error || '未检测到已解密账号，请先解密数据库。')
        trace.log('loadContacts:no-account', {
          error: contactsError.value
        })
        return { usedPrefetched: false }
      }

      await loadSessionsForSelectedAccount()
      trace.log('loadContacts:end', {
        contactCount: contacts.value.length
      })
      return { usedPrefetched: false }
    } catch (error) {
      clearContactsState(error?.message || '加载联系人失败')
      trace.log('loadContacts:error', {
        message: String(error?.message || '')
      })
      return { usedPrefetched: false }
    } finally {
      isLoadingContacts.value = false
      trace.log('loadContacts:exit', {
        loading: isLoadingContacts.value,
        error: contactsError.value
      })
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
