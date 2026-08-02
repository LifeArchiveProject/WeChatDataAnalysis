import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { normalizeSessionPreview } from '~/lib/chat/formatters'
import { createPerfTrace } from '~/lib/chat/perf-logger'

const SESSION_LIST_WIDTH_KEY = 'ui.chat.session_list_width_css_v2'
const SESSION_LIST_WIDTH_KEY_CSS_V1 = 'ui.chat.session_list_width_css'
const SESSION_LIST_WIDTH_KEY_PHYSICAL = 'ui.chat.session_list_width_physical'
const SESSION_LIST_WIDTH_KEY_LEGACY = 'ui.chat.session_list_width'
const SESSION_LIST_WIDTH_DEFAULT = 300
const SESSION_LIST_WIDTH_MIN = 260
const SESSION_LIST_WIDTH_MAX = 520
const DEFAULT_CHAT_SOURCE = 'auto'

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
  let sessionListResizePrevCursor = ''
  let sessionListResizePrevUserSelect = ''
  let sessionsRequestController = null
  let sessionsRequestPromise = null
  let sessionsRequestKey = ''
  let sessionsRequestSeq = 0

  const isAbortError = (error, controller = null) => {
    return !!(
      controller?.signal?.aborted
      || error?.name === 'AbortError'
      || error?.cause?.name === 'AbortError'
      || error?.message === 'This operation was aborted'
    )
  }

  const abortSessionsRequest = () => {
    sessionsRequestSeq += 1
    const controller = sessionsRequestController
    sessionsRequestController = null
    sessionsRequestPromise = null
    sessionsRequestKey = ''
    if (!controller || controller.signal.aborted) return
    try { controller.abort() } catch {}
  }

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

      const persistMigratedWidth = (nextWidth) => {
        const normalized = clampSessionListWidth(nextWidth)
        sessionListWidth.value = normalized
        localStorage.setItem(SESSION_LIST_WIDTH_KEY, String(normalized))
        localStorage.removeItem(SESSION_LIST_WIDTH_KEY_CSS_V1)
        localStorage.removeItem(SESSION_LIST_WIDTH_KEY_PHYSICAL)
        localStorage.removeItem(SESSION_LIST_WIDTH_KEY_LEGACY)
      }

      const cssV1Raw = localStorage.getItem(SESSION_LIST_WIDTH_KEY_CSS_V1)
      const cssV1Value = parseInt(String(cssV1Raw || ''), 10)
      if (!Number.isNaN(cssV1Value)) {
        persistMigratedWidth(cssV1Value === 320 ? SESSION_LIST_WIDTH_DEFAULT : cssV1Value)
        return
      }

      const physicalRaw = localStorage.getItem(SESSION_LIST_WIDTH_KEY_PHYSICAL)
      const physicalValue = parseInt(String(physicalRaw || ''), 10)
      if (!Number.isNaN(physicalValue)) {
        const dpr = window.devicePixelRatio || 1
        const previousCssWidth = physicalValue / dpr
        persistMigratedWidth(dpr > 1 ? Math.max(SESSION_LIST_WIDTH_DEFAULT, previousCssWidth) : previousCssWidth)
        return
      }

      const legacy = localStorage.getItem(SESSION_LIST_WIDTH_KEY_LEGACY)
      const legacyValue = parseInt(String(legacy || ''), 10)
      if (!Number.isNaN(legacyValue)) {
        persistMigratedWidth(legacyValue)
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
      sessionListResizeStartWidth + (clientX - sessionListResizeStartX)
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

  watch(
    () => selectedAccount.value,
    () => abortSessionsRequest()
  )

  onUnmounted(() => {
    abortSessionsRequest()
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

  const requestSessionsForSelectedAccount = async (source = DEFAULT_CHAT_SOURCE) => {
    const account = String(selectedAccount.value || '').trim()
    if (!account) return null

    const desiredSource = String(source || DEFAULT_CHAT_SOURCE).trim() || DEFAULT_CHAT_SOURCE
    const requestKey = `${account}\u0000${desiredSource}`
    if (sessionsRequestPromise && sessionsRequestKey === requestKey) {
      return sessionsRequestPromise
    }

    abortSessionsRequest()
    const requestSeq = ++sessionsRequestSeq
    const controller = typeof AbortController === 'function' ? new AbortController() : null
    sessionsRequestController = controller
    sessionsRequestKey = requestKey

    const params = {
      account,
      limit: 400,
      include_hidden: false,
      include_official: false,
      source: desiredSource
    }
    if (controller) params.signal = controller.signal

    const requestPromise = api.listChatSessions(params)
    sessionsRequestPromise = requestPromise
    try {
      return await requestPromise
    } finally {
      if (requestSeq === sessionsRequestSeq && sessionsRequestPromise === requestPromise) {
        sessionsRequestController = null
        sessionsRequestPromise = null
        sessionsRequestKey = ''
      }
    }
  }

  const loadSessionsForSelectedAccount = async () => {
    if (!selectedAccount.value) {
      clearContactsState('')
      return []
    }

    const requestAccount = String(selectedAccount.value || '').trim()
    const trace = createPerfTrace('chat-sessions', {
      account: requestAccount,
      action: 'loadSessionsForSelectedAccount'
    })
    trace.log('loadSessions:start', {
      source: DEFAULT_CHAT_SOURCE,
      realtimeEnabled: !!realtimeEnabled?.value
    })

    try {
      trace.log('loadSessions:request:start', {
        source: DEFAULT_CHAT_SOURCE
      })
      const sessionsResp = await requestSessionsForSelectedAccount(DEFAULT_CHAT_SOURCE)
      if (requestAccount !== String(selectedAccount.value || '').trim()) return contacts.value
      trace.log('loadSessions:request:end', {
        source: sessionsResp?.source || DEFAULT_CHAT_SOURCE,
        rawCount: Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions.length : 0
      })
      const sessions = Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions : []
      contacts.value = mapSessions(sessions)
      contactsError.value = ''
      trace.log('loadSessions:end', {
        contactCount: contacts.value.length
      })
      return contacts.value
    } catch (error) {
      if (isAbortError(error)) return contacts.value
      trace.log('loadSessions:request:error', {
        source: DEFAULT_CHAT_SOURCE,
        message: error?.message || ''
      })
      clearContactsState(error?.message || '加载会话失败')
      return []
    }
  }

  const refreshSessionsForSelectedAccount = async ({ sourceOverride } = {}) => {
    if (!process.client || typeof window === 'undefined') return
    if (!selectedAccount.value) return
    if (isLoadingContacts.value) return

    const requestAccount = String(selectedAccount.value || '').trim()
    const previousUsername = selectedContact.value?.username || ''
    const desiredSource = (sourceOverride != null)
      ? String(sourceOverride || '').trim()
      : DEFAULT_CHAT_SOURCE
    const trace = createPerfTrace('chat-sessions', {
      account: requestAccount,
      action: 'refreshSessionsForSelectedAccount',
      desiredSource
    })
    trace.log('refreshSessions:start', {
      previousUsername
    })

    let sessionsResp = null
    try {
      trace.log('refreshSessions:request:start', {
        source: desiredSource || DEFAULT_CHAT_SOURCE
      })
      sessionsResp = await requestSessionsForSelectedAccount(desiredSource || DEFAULT_CHAT_SOURCE)
      if (requestAccount !== String(selectedAccount.value || '').trim()) return
      trace.log('refreshSessions:request:end', {
        source: sessionsResp?.source || desiredSource || DEFAULT_CHAT_SOURCE,
        rawCount: Array.isArray(sessionsResp?.sessions) ? sessionsResp.sessions.length : 0
      })
    } catch (error) {
      if (isAbortError(error)) return
      trace.log('refreshSessions:request:error', {
        source: desiredSource || DEFAULT_CHAT_SOURCE,
        message: error?.message || ''
      })
      contactsError.value = error?.message || '刷新会话失败'
      return
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
        clearContactsState(chatAccounts.error || '未检测到聊天账号，请先保存密钥/db_storage 路径或使用旧模式解密数据库。')
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
