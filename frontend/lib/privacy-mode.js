export const PRIVACY_MODE_KEY = 'ui.privacy_mode'

export const readPrivacyMode = (fallback = false) => {
  if (!process.client) return !!fallback
  try {
    const raw = localStorage.getItem(PRIVACY_MODE_KEY)
    if (raw == null) return !!fallback
    const normalized = String(raw).trim().toLowerCase()
    return normalized === '1' || normalized === 'true'
  } catch {
    return !!fallback
  }
}

export const writePrivacyMode = (enabled) => {
  if (!process.client) return
  try {
    localStorage.setItem(PRIVACY_MODE_KEY, enabled ? '1' : '0')
  } catch {}
}
