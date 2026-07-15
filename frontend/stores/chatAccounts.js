import { defineStore } from 'pinia'

const SELECTED_ACCOUNT_KEY = 'ui.selected_account'

export const useChatAccountsStore = defineStore('chatAccounts', () => {
  const accounts = ref([])
  const accountInfos = ref([])
  const switchableAccounts = ref([])
  const selectedAccount = ref(null)
  const sourceStatusByAccount = ref({})
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

  const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value || {}, key)

  const normalizeSourceStatus = (value) => {
    if (!value || typeof value !== 'object') return null

    const hasStatusFields = [
      'fallbackActive',
      'activeSource',
      'preferredSource',
      'sourceFallback',
      'sourceFallbackReason',
      'sourceFallbackMessage',
      'sourceFallbackRetryAfterSeconds',
    ].some((key) => hasOwn(value, key))
    if (!hasStatusFields) return null

    const fallbackActive = hasOwn(value, 'fallbackActive')
      ? !!value.fallbackActive
      : !!value.sourceFallback
    const retryRaw = value.retryAfterSeconds ?? value.sourceFallbackRetryAfterSeconds ?? 0
    const retryNumber = Number(retryRaw)

    return {
      preferredSource: String(value.preferredSource || value.sourceRequested || '').trim(),
      activeSource: String(value.activeSource || value.dataSource || value.source || (fallbackActive ? 'decrypted' : '')).trim(),
      fallbackActive,
      reason: String(value.reason || value.sourceFallbackReason || '').trim(),
      message: String(value.message || value.sourceFallbackMessage || '').trim(),
      retryAfterSeconds: Number.isFinite(retryNumber) ? Math.max(0, Math.floor(retryNumber)) : 0,
    }
  }

  const setSourceStatus = (account, value) => {
    const accountName = normalizeAccountName(account || selectedAccount.value)
    const status = normalizeSourceStatus(value)
    if (!accountName || !status) return false
    sourceStatusByAccount.value = {
      ...sourceStatusByAccount.value,
      [accountName]: status,
    }
    return true
  }

  const applySourceResponse = (response) => {
    if (!response || typeof response !== 'object') return

    const defaultAccount = normalizeAccountName(response.account || selectedAccount.value)

    if (response.dataSourceStatus) {
      setSourceStatus(defaultAccount, response.dataSourceStatus)
    }
    setSourceStatus(defaultAccount, response)

    const accountInfoItems = Array.isArray(response.accountInfos)
      ? response.accountInfos
      : (Array.isArray(response.items) ? response.items : [])
    for (const item of accountInfoItems) {
      if (!item?.dataSourceStatus) continue
      setSourceStatus(item.account || item.name, item.dataSourceStatus)
    }

    const jobs = [response.job, ...(Array.isArray(response.jobs) ? response.jobs : [])]
    for (const job of jobs) {
      if (!job || typeof job !== 'object') continue
      const account = normalizeAccountName(job.account || defaultAccount)
      setSourceStatus(account, job.dataSourceStatus)
      setSourceStatus(account, job.options)
    }

    setSourceStatus(defaultAccount, response.options)
  }

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

  const selectedDataSourceStatus = computed(() => {
    const account = normalizeAccountName(selectedAccount.value)
    return account ? (sourceStatusByAccount.value[account] || null) : null
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

        const nextSourceStatuses = {}
        for (const info of accountInfos.value) {
          const account = normalizeAccountName(info?.account || info?.name)
          const status = normalizeSourceStatus(info?.dataSourceStatus)
          if (account && status) nextSourceStatuses[account] = status
        }
        sourceStatusByAccount.value = nextSourceStatuses

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
        sourceStatusByAccount.value = {}
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
    sourceStatusByAccount,
    selectedDataSourceStatus,
    loading,
    error,
    loaded,
    ensureLoaded,
    setSelectedAccount,
    applySourceResponse,
  }
})
