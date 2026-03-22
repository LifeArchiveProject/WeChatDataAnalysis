import { defineStore } from 'pinia'

import {
  UI_THEME_DARK,
  UI_THEME_LIGHT,
  applyUiTheme,
  normalizeUiTheme,
  readUiTheme,
  writeUiTheme,
} from '~/lib/ui-theme'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(UI_THEME_LIGHT)
  const initialized = ref(false)

  const isDark = computed(() => theme.value === UI_THEME_DARK)

  const set = (nextTheme) => {
    theme.value = normalizeUiTheme(nextTheme, UI_THEME_LIGHT)
    writeUiTheme(theme.value)
    applyUiTheme(theme.value)
  }

  const init = () => {
    if (initialized.value) {
      applyUiTheme(theme.value)
      return
    }
    initialized.value = true
    theme.value = readUiTheme(UI_THEME_LIGHT)
    applyUiTheme(theme.value)
  }

  const toggle = () => {
    set(isDark.value ? UI_THEME_LIGHT : UI_THEME_DARK)
  }

  return {
    theme,
    initialized,
    isDark,
    init,
    set,
    toggle,
  }
})
