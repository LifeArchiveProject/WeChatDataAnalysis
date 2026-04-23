export const WECHAT_INSTALL_PATH_STORAGE_KEY = 'decrypt.wechatInstallPath'

export const normalizeWechatInstallPath = (value) => String(value || '').trim()

export const readStoredWechatInstallPath = () => {
  if (!process.client || typeof window === 'undefined') return ''
  try {
    return normalizeWechatInstallPath(window.localStorage.getItem(WECHAT_INSTALL_PATH_STORAGE_KEY) || '')
  } catch {
    return ''
  }
}

export const writeStoredWechatInstallPath = (value) => {
  if (!process.client || typeof window === 'undefined') return
  try {
    const normalized = normalizeWechatInstallPath(value)
    if (normalized) {
      window.localStorage.setItem(WECHAT_INSTALL_PATH_STORAGE_KEY, normalized)
    } else {
      window.localStorage.removeItem(WECHAT_INSTALL_PATH_STORAGE_KEY)
    }
  } catch {}
}
