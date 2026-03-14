import { normalizeApiBase, readApiBaseOverride } from '~/lib/api-settings'

// Client-side cache so that useApiBase() can be called safely outside
// the Nuxt composable context (e.g. inside async callbacks / onMounted chains).
let _clientCache = ''

export const useApiBase = () => {
  if (process.client && _clientCache) return _clientCache

  // useRuntimeConfig() requires the Nuxt app context, which is only
  // guaranteed during synchronous setup.  On the client we cache the
  // result so later (context-less) calls still work.
  let config
  try {
    config = useRuntimeConfig()
  } catch {
    // Context unavailable – fall back to cached value or default.
    return _clientCache || '/api'
  }

  // Default to same-origin `/api` so Nuxt devProxy / backend-mounted UI both work.
  // Override priority:
  // 1) Local UI setting (web + desktop)
  // 2) NUXT_PUBLIC_API_BASE env/runtime config
  // 3) `/api`
  const override = process.client ? readApiBaseOverride() : ''
  const runtime = String(config?.public?.apiBase || '').trim()
  const result = normalizeApiBase(override || runtime || '/api')

  if (process.client) _clientCache = result
  return result
}

/**
 * Call this when the user changes the API base override in settings
 * so the cached value is refreshed.
 */
export const invalidateApiBaseCache = () => {
  _clientCache = ''
}
