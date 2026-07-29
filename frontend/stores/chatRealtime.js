import { defineStore } from 'pinia'

import { showErrorAlert } from '~/composables/useErrorNotice'
import { useChatAccountsStore } from '~/stores/chatAccounts'

const REALTIME_STREAM_RECONNECT_BASE_MS = 1_000
const REALTIME_STREAM_RECONNECT_MAX_MS = 30_000
const REALTIME_STREAM_STABLE_MS = 10_000

export const useChatRealtimeStore = defineStore('chatRealtime', () => {
  const chatAccounts = useChatAccountsStore()

  const enabled = ref(false)
  const available = ref(false)
  const checking = ref(false)
  const statusInfo = ref(null)
  const statusError = ref('')
  const toggling = ref(false)
  const toggleSeq = ref(0)
  const lastToggleAction = ref('')
  const changeSeq = ref(0)
  const priorityUsername = ref('')

  let eventSource = null
  let changeDebounceTimer = null
  let streamReconnectTimer = null
  let streamStabilityTimer = null
  let streamReconnectAttempt = 0
  let streamGeneration = 0
  let statusRequestGeneration = 0

  const getAccount = () => String(chatAccounts.selectedAccount || '').trim()

  const setPriorityUsername = (username) => {
    priorityUsername.value = String(username || '').trim()
  }

  const ensureReadyAccount = async () => {
    if (!process.client) return false
    await chatAccounts.ensureLoaded()
    return !!getAccount()
  }

  const statusRequestIsCurrent = (generation, account) => (
    generation === statusRequestGeneration && account === getAccount()
  )

  const realtimeUnavailableReason = (info, fallback = '') => {
    const directReason = String(
      info?.probe_error
      || info?.failure_reason
      || info?.error
      || fallback
      || ''
    ).trim()
    if (directReason) return directReason
    if (info?.dll_present === false) return '实时消息原生组件缺失或安装不完整。'
    if (info?.key_present === false) return '当前账号尚未保存数据库密钥。'
    if (!String(info?.db_storage_dir || '').trim()) return '当前账号缺少 db_storage 路径。'
    if (!String(info?.session_db_path || '').trim()) return '当前账号缺少实时会话数据库。'
    return '实时模式当前不可用。'
  }

  const publishRealtimeDataSourceStatus = ({ account, available: isAvailable, info, error: reason }) => {
    if (!account) return
    chatAccounts.applySourceResponse({
      account,
      dataSourceStatus: {
        preferredSource: 'realtime',
        activeSource: isAvailable ? 'realtime' : 'decrypted',
        fallbackActive: !isAvailable,
        reason: isAvailable ? '' : reason,
        message: '',
        retryAfterSeconds: isAvailable ? 0 : Number(info?.retry_after_seconds || 0),
      },
    })
  }

  const fetchStatus = async () => {
    if (!process.client) {
      return { account: '', available: false, info: null, error: '', stale: true }
    }
    const requestGeneration = ++statusRequestGeneration
    const account = getAccount()
    if (!account) {
      const nextError = '未检测到已解密账号，请先解密数据库。'
      available.value = false
      statusInfo.value = null
      statusError.value = nextError
      enabled.value = false
      checking.value = false
      stopStream()
      return { account, available: false, info: null, error: nextError, stale: false }
    }

    const api = useApi()
    checking.value = true
    statusError.value = ''
    try {
      const resp = await api.getChatRealtimeStatus({ account })
      const nextAvailable = !!resp?.available
      const nextInfo = resp?.realtime || null
      const nextError = nextAvailable ? '' : realtimeUnavailableReason(nextInfo)
      const result = {
        account,
        available: nextAvailable,
        info: nextInfo,
        error: nextError,
        stale: !statusRequestIsCurrent(requestGeneration, account),
      }
      if (result.stale) return result

      available.value = nextAvailable
      statusInfo.value = nextInfo
      statusError.value = nextError
      publishRealtimeDataSourceStatus(result)
      if (!nextAvailable) {
        enabled.value = false
        stopStream()
      }
      return result
    } catch (e) {
      const nextError = realtimeUnavailableReason(null, e?.message || '实时状态获取失败')
      const result = {
        account,
        available: false,
        info: null,
        error: nextError,
        stale: !statusRequestIsCurrent(requestGeneration, account),
      }
      if (result.stale) return result

      available.value = false
      statusInfo.value = null
      statusError.value = nextError
      publishRealtimeDataSourceStatus(result)
      enabled.value = false
      stopStream()
      return result
    } finally {
      if (statusRequestIsCurrent(requestGeneration, account)) checking.value = false
    }
  }

  const clearStreamReconnectTimer = () => {
    if (!streamReconnectTimer) return
    try {
      clearTimeout(streamReconnectTimer)
    } catch {}
    streamReconnectTimer = null
  }

  const clearStreamStabilityTimer = () => {
    if (!streamStabilityTimer) return
    try {
      clearTimeout(streamStabilityTimer)
    } catch {}
    streamStabilityTimer = null
  }

  const closeEventSource = () => {
    clearStreamStabilityTimer()
    const source = eventSource
    eventSource = null
    if (!source) return
    try {
      source.close()
    } catch {}
  }

  const stopStream = () => {
    streamGeneration += 1
    streamReconnectAttempt = 0
    clearStreamReconnectTimer()
    closeEventSource()
    if (changeDebounceTimer) {
      try {
        clearTimeout(changeDebounceTimer)
      } catch {}
      changeDebounceTimer = null
    }
  }

  const bumpChangeSeqDebounced = () => {
    if (changeDebounceTimer) return
    changeDebounceTimer = setTimeout(() => {
      changeDebounceTimer = null
      changeSeq.value += 1
    }, 500)
  }

  const streamIsCurrent = (generation, account) => (
    generation === streamGeneration
    && enabled.value
    && account === getAccount()
  )

  const reconnectDelayMs = (attempt) => Math.min(
    REALTIME_STREAM_RECONNECT_MAX_MS,
    REALTIME_STREAM_RECONNECT_BASE_MS * (2 ** Math.min(Math.max(0, attempt), 10))
  )

  const scheduleStreamReconnect = (generation, account) => {
    if (!streamIsCurrent(generation, account) || streamReconnectTimer) return

    const delay = reconnectDelayMs(streamReconnectAttempt)
    streamReconnectAttempt += 1
    streamReconnectTimer = setTimeout(() => {
      streamReconnectTimer = null
      if (!streamIsCurrent(generation, account)) return
      openStream(generation, account)
    }, delay)
  }

  const openStream = (generation, account) => {
    if (!streamIsCurrent(generation, account)) return

    closeEventSource()
    const apiBase = useApiBase()
    const url = `${apiBase}/chat/realtime/stream?account=${encodeURIComponent(account)}`
    let source = null
    try {
      source = new EventSource(url)
      eventSource = source
    } catch {
      eventSource = null
      scheduleStreamReconnect(generation, account)
      return
    }

    source.onopen = () => {
      if (!streamIsCurrent(generation, account) || eventSource !== source) {
        try {
          source.close()
        } catch {}
        return
      }
      clearStreamStabilityTimer()
      streamStabilityTimer = setTimeout(() => {
        streamStabilityTimer = null
        if (!streamIsCurrent(generation, account) || eventSource !== source) return
        streamReconnectAttempt = 0
      }, REALTIME_STREAM_STABLE_MS)
    }

    source.onmessage = (ev) => {
      if (!streamIsCurrent(generation, account) || eventSource !== source) return
      try {
        const data = JSON.parse(String(ev.data || '{}'))
        if (String(data?.type || '') === 'change') {
          bumpChangeSeqDebounced()
        }
      } catch {}
    }

    source.onerror = () => {
      if (!streamIsCurrent(generation, account) || eventSource !== source) {
        try {
          source.close()
        } catch {}
        return
      }
      closeEventSource()
      scheduleStreamReconnect(generation, account)
    }
  }

  const startStream = () => {
    stopStream()
    if (!process.client || typeof window === 'undefined') return
    if (!enabled.value) return
    const account = getAccount()
    if (!account) return
    if (typeof EventSource === 'undefined') return
    openStream(streamGeneration, account)
  }

  const enable = async ({ silent = false } = {}) => {
    if (toggling.value) return false
    toggling.value = true
    try {
      const ok = await ensureReadyAccount()
      if (!ok) {
        if (!silent && process.client && typeof window !== 'undefined') {
          window.alert('未检测到已解密账号，请先解密数据库。')
        }
        statusError.value = '未检测到已解密账号，请先解密数据库。'
        enabled.value = false
        stopStream()
        return false
      }

      const statusResult = await fetchStatus()
      if (!statusResult || statusResult.stale) return false
      if (!statusResult.available) {
        if (!silent && process.client && typeof window !== 'undefined') {
          showErrorAlert(statusResult.error || '实时模式不可用：缺少密钥或 db_storage 路径。')
        }
        enabled.value = false
        stopStream()
        return false
      }

      enabled.value = true
      startStream()
      lastToggleAction.value = 'enabled'
      toggleSeq.value += 1
      return true
    } finally {
      toggling.value = false
    }
  }

  const disable = async ({ silent = false } = {}) => {
    if (toggling.value) return false
    toggling.value = true
    try {
      const account = getAccount()
      enabled.value = false
      stopStream()

      if (!account) {
        lastToggleAction.value = 'disabled'
        toggleSeq.value += 1
        return true
      }

      lastToggleAction.value = 'disabled'
      toggleSeq.value += 1
      return true
    } finally {
      toggling.value = false
    }
  }

  const toggle = async (opts = {}) => {
    return enabled.value ? await disable(opts) : await enable(opts)
  }

  if (process.client) {
    watch(
      () => chatAccounts.selectedAccount,
      async () => {
        setPriorityUsername('')
        const statusResult = await fetchStatus()
        if (!statusResult?.stale && statusResult?.available && enabled.value) {
          startStream()
        }
      },
      { immediate: true }
    )
  }

  return {
    enabled,
    available,
    checking,
    statusInfo,
    statusError,
    toggling,
    toggleSeq,
    lastToggleAction,
    changeSeq,
    priorityUsername,

    setPriorityUsername,
    ensureReadyAccount,
    fetchStatus,
    startStream,
    stopStream,
    enable,
    disable,
    toggle,
  }
})
