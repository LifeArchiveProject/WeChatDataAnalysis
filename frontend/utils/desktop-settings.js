export const DESKTOP_SETTING_AUTO_REALTIME_KEY = 'desktop.settings.autoRealtime'
export const DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY = 'desktop.settings.defaultToChatWhenData'

export const readLocalBoolSetting = (key, fallback = false) => {
  if (!process.client) return !!fallback
  try {
    const raw = localStorage.getItem(String(key || ''))
    if (raw == null) return !!fallback
    return String(raw).toLowerCase() === 'true'
  } catch {
    return !!fallback
  }
}

export const writeLocalBoolSetting = (key, value) => {
  if (!process.client) return
  try {
    localStorage.setItem(String(key || ''), value ? 'true' : 'false')
  } catch {}
}
