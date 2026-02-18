/**
 * 年度总结页面主题管理 composable
 * 仅保留 modern（现代）主题
 */

// 全局响应式状态（跨组件共享）
// Note: 历史上曾尝试过 gameboy / win98 等主题，但目前已移除，仅保留 Modern。
const theme = ref('off') // off === Modern

export function useWrappedTheme() {
  const setTheme = (newTheme) => {
    // Only keep Modern.
    if (newTheme !== 'off') {
      console.warn(`Wrapped theme '${newTheme}' has been removed; falling back to Modern.`)
    }
    theme.value = 'off'
  }

  const cycleTheme = () => setTheme('off')

  const isRetro = computed(() => false)
  const themeClass = computed(() => '')

  return {
    theme: readonly(theme),
    setTheme,
    cycleTheme,
    isRetro,
    themeClass
  }
}
