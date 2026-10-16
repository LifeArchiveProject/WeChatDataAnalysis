export const joinNativePath = (basePath, childName) => {
  const base = String(basePath || '').trim().replace(/[\\/]+$/, '')
  const child = String(childName || '').trim().replace(/^[\\/]+/, '')
  if (!base || !child) return base || child

  const usesWindowsSeparators = /^[A-Za-z]:[\\/]/.test(base) || base.startsWith('\\\\')
  return `${base}${usesWindowsSeparators ? '\\' : '/'}${child}`
}
