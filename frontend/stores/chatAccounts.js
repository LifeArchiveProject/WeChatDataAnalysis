import { defineStore } from 'pinia'

const SELECTED_ACCOUNT_KEY = 'ui.selected_account'

export const useChatAccountsStore = defineStore('chatAccounts', () => {
  const accounts = ref([])
  const accountInfos = ref([])
  const switchableAccounts = ref([])
  const selectedAccount = ref(null)
  const loading = ref(false)
  const error = ref('')
  const loaded = ref(false)

  // Capture apiBase during synchronous store setup when Nuxt context is available.
  // useApiBase() calls useRuntimeConfig() which requires the Nuxt app context;
  // that context can be lost inside deferred async functions (e.g. onMounted callbacks).
  const _apiBase = useApiBase()

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

  const normalizeAccountName = (value) => String(value || '').trim()

  const uniqueAccounts = (values = []) => {
    const out = []
    const seen = new Set()
    for (const value of Array.isArray(values) ? values : []) {
      const account = normalizeAccountName(value)
      if (!account || seen.has(account)) continue
      seen.add(account)
      out.push(account)
    }
    return out
  }

  const normalizeAccountInfos = (resp, nextAccounts) => {
    const raw = Array.isArray(resp?.accountInfos)
      ? resp.accountInfos
      : (Array.isArray(resp?.items) ? resp.items : [])
    const infos = []
    const seen = new Set()

    for (const item of raw) {
      if (!item || typeof item !== 'object') continue
      const account = normalizeAccountName(item.account || item.name)
      if (!account || seen.has(account)) continue
      seen.add(account)
      infos.push({ ...item, account, name: normalizeAccountName(item.name || account) || account })
    }

    for (const account of nextAccounts) {
      if (!account || seen.has(account)) continue
      seen.add(account)
      infos.push({ account, name: account })
    }

    return infos
  }

  const deriveSwitchableAccounts = (resp, infos, nextAccounts) => {
    const explicit = uniqueAccounts(
      resp?.switchableAccounts
      || resp?.switchable_accounts
      || resp?.keyReadyAccounts
      || []
    )
    const accountSet = new Set(nextAccounts)
    if (explicit.length) {
      return explicit.filter((account) => !accountSet.size || accountSet.has(account))
    }

    return uniqueAccounts(
      infos
        .filter((info) => {
          const keysReady = !!(info.keysReady || info.keyReady || info.switchable)
          const hasDbKey = !!(info.dbKeyPresent || info.db_key_present)
          const hasImageKey = !!(info.imageKeyPresent || info.image_key_present)
          return keysReady || (hasDbKey && hasImageKey)
        })
        .map((info) => info.account || info.name)
    ).filter((account) => !accountSet.size || accountSet.has(account))
  }

  const accountInfoByName = computed(() => {
    const out = {}
    for (const info of Array.isArray(accountInfos.value) ? accountInfos.value : []) {
      const account = normalizeAccountName(info?.account || info?.name)
      if (!account) continue
      out[account] = info
    }
    return out
  })

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
        const resp = await $fetch('/chat/accounts', { baseURL: _apiBase })
        const nextAccounts = uniqueAccounts(Array.isArray(resp?.accounts) ? resp.accounts : [])
        accounts.value = nextAccounts
        accountInfos.value = normalizeAccountInfos(resp, nextAccounts)
        switchableAccounts.value = deriveSwitchableAccounts(resp, accountInfos.value, nextAccounts)

        const preferred = String(selectedAccount.value || '').trim()
        const defaultAccount = String(resp?.default_account || '').trim()
        const defaultSwitchable = String(resp?.defaultSwitchableAccount || resp?.default_switchable_account || '').trim()
        const fallback = defaultSwitchable || defaultAccount || nextAccounts[0] || ''
        const selectableAccounts = uniqueAccounts([...nextAccounts, ...switchableAccounts.value])
        const nextSelected = preferred && selectableAccounts.includes(preferred) ? preferred : (fallback || null)

        selectedAccount.value = nextSelected
        writeSelectedAccount(nextSelected)
        loaded.value = true
      } catch (e) {
        accounts.value = []
        accountInfos.value = []
        switchableAccounts.value = []
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
    accountInfos,
    accountInfoByName,
    switchableAccounts,
    selectedAccount,
    loading,
    error,
    loaded,
    ensureLoaded,
    setSelectedAccount,
  }
})
