export const FIRST_USE_AGREEMENT_VERSION = '2026-08-12.3'
export const FIRST_USE_AGREEMENT_STORAGE_KEY = 'ui.first_use_agreement'

let acceptedForCurrentSession = false

const readStoredAgreement = () => {
  if (!process.client || typeof window === 'undefined') return null
  try {
    const parsed = JSON.parse(window.localStorage.getItem(FIRST_USE_AGREEMENT_STORAGE_KEY) || 'null')
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export const isFirstUseAgreementAccepted = () => {
  if (acceptedForCurrentSession) return true
  const stored = readStoredAgreement()
  const accepted = stored?.version === FIRST_USE_AGREEMENT_VERSION && Boolean(stored?.acceptedAt)
  if (accepted) acceptedForCurrentSession = true
  return accepted
}

export const persistFirstUseAgreementAcceptance = () => {
  acceptedForCurrentSession = true
  if (!process.client || typeof window === 'undefined') return
  try {
    window.localStorage.setItem(FIRST_USE_AGREEMENT_STORAGE_KEY, JSON.stringify({
      version: FIRST_USE_AGREEMENT_VERSION,
      acceptedAt: new Date().toISOString()
    }))
  } catch {}
}

export const normalizeFirstUseRedirect = (value) => {
  const target = String(Array.isArray(value) ? value[0] : value || '').trim()
  if (!target.startsWith('/') || target.startsWith('//') || target.startsWith('/agreement')) return '/'
  return target
}
