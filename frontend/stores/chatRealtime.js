import { defineStore } from 'pinia'

import { useChatAccountsStore } from '~/stores/chatAccounts'

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

  const getAccount = () => String(chatAccounts.selectedAccount || '').trim()

  const setPriorityUsername = (username) => {
    priorityUsername.value = String(username || '').trim()
  }

  const ensureReadyAccount = async () => {
    if (!process.client) return false
    await chatAccounts.ensureLoaded()
    return !!getAccount()
  }

  const fetchStatus = async () => {
    if (!process.client) return
    const account = getAccount()
    if (!account) {
      available.value = false
      statusInfo.value = null
      statusError.value = '未检测到已解密账号，请先解密数据库。'
      return
    }

    const api = useApi()
    checking.value = true
    statusError.value = ''
    try {
      const resp = await api.getChatRealtimeStatus({ account })
      available.value = !!resp?.available
      statusInfo.value = resp?.realtime || null
      statusError.value = ''
    } catch (e) {
      available.value = false
      statusInfo.value = null
      statusError.value = e?.message || '实时状态获取失败'
    } finally {
      checking.value = false
    }
  }

  const stopStream = () => {
    if (eventSource) {
      try {
        eventSource.close()
      } catch {}
      eventSource = null
    }
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

  const startStream = () => {
    stopStream()
    if (!process.client || typeof window === 'undefined') return
    if (!enabled.value) return
    const account = getAccount()
    if (!account) return
    if (typeof EventSource === 'undefined') return

    const apiBase = useApiBase()
    const url = `${apiBase}/chat/realtime/stream?account=${encodeURIComponent(account)}`

    try {
      eventSource = new EventSource(url)
    } catch {
      eventSource = null
      return
    }

    eventSource.onmessage = (ev) => {
      try {
        const data = JSON.parse(String(ev.data || '{}'))
        if (String(data?.type || '') === 'change') {
          bumpChangeSeqDebounced()
        }
      } catch {}
    }

    eventSource.onerror = () => {
      // Keep `enabled` as-is; same behavior as the old in-page implementation.
      stopStream()
    }
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
        return false
      }

      await fetchStatus()
      if (!available.value) {
        if (!silent && process.client && typeof window !== 'undefined') {
          window.alert(statusError.value || '实时模式不可用：缺少密钥或 db_storage 路径。')
        }
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

      try {
        const api = useApi()
        await api.syncChatRealtimeAll({
          account,
          max_scan: 200,
          priority_username: priorityUsername.value || '',
          priority_max_scan: 5000,
          include_hidden: true,
          include_official: true,
        })
      } catch (e) {
        if (!silent && process.client && typeof window !== 'undefined') {
          window.alert(e?.message || '关闭实时模式时同步失败')
        }
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
        await fetchStatus()
        if (enabled.value) {
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
