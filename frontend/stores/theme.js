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

  // 只在客户端落地：SidebarRail 在 setup 里就调用 init()，服务端渲染时也会跑到。
  // 之前这里会在 SSR 阶段把 initialized 置为 true 并序列化进 Pinia payload，
  // 客户端 hydrate 后 init() 直接走「已初始化」分支，把默认的浅色套上去，
  // localStorage 里存的 dark 永远读不到 —— 结果就是带侧边栏的页面深色模式全部失效。
  // 现在改成客户端每次都以 localStorage 为准，多次调用也幂等。
  const init = () => {
    if (!process.client) return
    initialized.value = true
    theme.value = readUiTheme(theme.value)
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
