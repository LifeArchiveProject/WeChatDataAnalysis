export const WECHAT_INSTALL_PATH_STORAGE_KEY = 'decrypt.wechatInstallPath'

export const isLikelyWechatDataPath = (value) => {
  const segments = String(value || '')
    .trim()
    .split(/[\\/]+/)
    .map(segment => segment.toLowerCase())
    .filter(Boolean)

  return segments.some(segment => (
    segment === 'xwechat_files' ||
    segment === 'wechat files' ||
    segment === 'weixin files' ||
    segment === 'db_storage' ||
    segment.startsWith('wxid_')
  ))
}

export const normalizeWechatInstallPath = (value) => {
  const normalized = String(value || '').trim()
  return isLikelyWechatDataPath(normalized) ? '' : normalized
}

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
