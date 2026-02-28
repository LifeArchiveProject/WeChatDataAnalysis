import { normalizeApiBase, readApiBaseOverride } from '~/utils/api-settings'

export const useApiBase = () => {
  const config = useRuntimeConfig()

  // Default to same-origin `/api` so Nuxt devProxy / backend-mounted UI both work.
  // Override priority:
  // 1) Local UI setting (web + desktop)
  // 2) NUXT_PUBLIC_API_BASE env/runtime config
  // 3) `/api`
  const override = process.client ? readApiBaseOverride() : ''
  const runtime = String(config?.public?.apiBase || '').trim()
  return normalizeApiBase(override || runtime || '/api')
}
