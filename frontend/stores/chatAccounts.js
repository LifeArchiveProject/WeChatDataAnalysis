import { defineStore } from 'pinia'

const SELECTED_ACCOUNT_KEY = 'ui.selected_account'

export const useChatAccountsStore = defineStore('chatAccounts', () => {
  const accounts = ref([])
  const selectedAccount = ref(null)
  const loading = ref(false)
  const error = ref('')
  const loaded = ref(false)

  let loadPromise = null

  const readSelectedAccount = () => {
    if (!process.client) return null
    try {
      const raw = localStorage.getItem(SELECTED_ACCOUNT_KEY)
      const v = String(raw || '').trim()
      return v || null
    } catch {
      return null
    }
  }

  const writeSelectedAccount = (value) => {
    if (!process.client) return
    try {
      const v = String(value || '').trim()
      if (!v) {
        localStorage.removeItem(SELECTED_ACCOUNT_KEY)
        return
      }
      localStorage.setItem(SELECTED_ACCOUNT_KEY, v)
    } catch {}
  }

  const setSelectedAccount = (next) => {
    selectedAccount.value = next ? String(next) : null
    writeSelectedAccount(selectedAccount.value)
  }

  if (process.client) {
    watch(selectedAccount, (next) => {
      writeSelectedAccount(next)
    })
  }

  const ensureLoaded = async ({ force = false } = {}) => {
    if (!process.client) return
    if (loaded.value && !force) return

    if (loadPromise && !force) {
      await loadPromise
      return
    }

    loadPromise = (async () => {
      loading.value = true
      error.value = ''

      if (!selectedAccount.value) {
        const cached = readSelectedAccount()
        if (cached) selectedAccount.value = cached
      }

      try {
        const api = useApi()
        const resp = await api.listChatAccounts()
        const nextAccounts = Array.isArray(resp?.accounts) ? resp.accounts : []
        accounts.value = nextAccounts

        const preferred = String(selectedAccount.value || '').trim()
        const defaultAccount = String(resp?.default_account || '').trim()
        const fallback = defaultAccount || nextAccounts[0] || ''
        const nextSelected = preferred && nextAccounts.includes(preferred) ? preferred : (fallback || null)

        selectedAccount.value = nextSelected
        writeSelectedAccount(nextSelected)
        loaded.value = true
      } catch (e) {
        accounts.value = []
        selectedAccount.value = null
        writeSelectedAccount(null)
        loaded.value = true
        error.value = e?.message || '加载账号失败'
      } finally {
        loading.value = false
      }
    })()

    try {
      await loadPromise
    } finally {
      loadPromise = null
    }
  }

  return {
    accounts,
    selectedAccount,
    loading,
    error,
    loaded,
    ensureLoaded,
    setSelectedAccount,
  }
})
