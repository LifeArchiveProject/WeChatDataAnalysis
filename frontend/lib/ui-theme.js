export const UI_THEME_KEY = 'ui.theme'
export const UI_THEME_LIGHT = 'light'
export const UI_THEME_DARK = 'dark'

export const normalizeUiTheme = (value, fallback = UI_THEME_LIGHT) => {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === UI_THEME_DARK) return UI_THEME_DARK
  if (normalized === UI_THEME_LIGHT) return UI_THEME_LIGHT
  return fallback === UI_THEME_DARK ? UI_THEME_DARK : UI_THEME_LIGHT
}

export const readUiTheme = (fallback = UI_THEME_LIGHT) => {
  if (!process.client) return normalizeUiTheme(fallback)
  try {
    const raw = localStorage.getItem(UI_THEME_KEY)
    return normalizeUiTheme(raw, fallback)
  } catch {
    return normalizeUiTheme(fallback)
  }
}

export const writeUiTheme = (theme) => {
  if (!process.client) return
  try {
    localStorage.setItem(UI_THEME_KEY, normalizeUiTheme(theme))
  } catch {}
}

export const applyUiTheme = (theme) => {
  if (!process.client || typeof document === 'undefined') return
  const normalized = normalizeUiTheme(theme)
  const root = document.documentElement
  root.dataset.theme = normalized
  root.classList.toggle('theme-dark', normalized === UI_THEME_DARK)
  root.style.colorScheme = normalized === UI_THEME_DARK ? 'dark' : 'light'
}
