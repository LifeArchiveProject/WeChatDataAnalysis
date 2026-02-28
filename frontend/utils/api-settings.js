export const API_BASE_OVERRIDE_KEY = 'ui.apiBaseOverride'

export const readApiBaseOverride = () => {
  if (!process.client) return ''
  try {
    const raw = localStorage.getItem(API_BASE_OVERRIDE_KEY)
    return String(raw || '').trim()
  } catch {
    return ''
  }
}

export const writeApiBaseOverride = (value) => {
  if (!process.client) return
  try {
    const v = String(value || '').trim()
    if (!v) localStorage.removeItem(API_BASE_OVERRIDE_KEY)
    else localStorage.setItem(API_BASE_OVERRIDE_KEY, v)
  } catch {}
}

export const normalizeApiBase = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return '/api'

  let v = raw.replace(/\/$/, '')

  // If a full origin is provided, auto-append `/api` when missing.
  if (/^https?:\/\//i.test(v) && !/\/api$/i.test(v)) {
    v = `${v}/api`
  }

  return v.replace(/\/$/, '')
}

