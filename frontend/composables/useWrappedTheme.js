/**
 * 年度总结页面主题管理 composable
 * 支持四种主题：modern（现代）、gameboy（Game Boy）、dos（DOS终端）、vhs（VHS录像带）
 */

const STORAGE_KEY = 'wrapped-theme'
const VALID_THEMES = ['off', 'gameboy', 'dos', 'vhs']

// 全局响应式状态（跨组件共享）
const theme = ref('off')
let initialized = false
let keyboardInitialized = false

export function useWrappedTheme() {
  // 初始化：从 localStorage 读取（仅执行一次）
  const initTheme = () => {
    if (initialized) return
    if (import.meta.client) {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved && VALID_THEMES.includes(saved)) {
        theme.value = saved
      }
      initialized = true
    }
  }

  // 立即初始化（客户端）
  if (import.meta.client) {
    initTheme()
  }

  // 设置主题
  const setTheme = (newTheme) => {
    if (!VALID_THEMES.includes(newTheme)) {
      console.warn(`Invalid theme: ${newTheme}`)
      return
    }
    theme.value = newTheme
    if (import.meta.client) {
      localStorage.setItem(STORAGE_KEY, newTheme)
    }
  }

  // 切换到下一个主题（循环）
  const cycleTheme = () => {
    const currentIndex = VALID_THEMES.indexOf(theme.value)
    const nextIndex = (currentIndex + 1) % VALID_THEMES.length
    setTheme(VALID_THEMES[nextIndex])
  }

  // 计算属性：是否为复古模式（非 off）
  const isRetro = computed(() => theme.value !== 'off')

  // 计算属性：当前主题的 CSS 类名
  const themeClass = computed(() => {
    if (theme.value === 'off') return ''
    return `wrapped-retro wrapped-theme-${theme.value}`
  })

  // 计算属性：主题显示名称
  const themeName = computed(() => {
    const names = {
      off: 'Modern',
      gameboy: 'Game Boy',
      dos: 'DOS Terminal',
      vhs: 'VHS Tape'
    }
    return names[theme.value] || 'Modern'
  })

  // 全局 F1-F4 快捷键切换主题（仅初始化一次）
  const initKeyboardShortcuts = () => {
    if (keyboardInitialized || !import.meta.client) return
    keyboardInitialized = true

    const handleKeydown = (e) => {
      // 检查是否在可编辑元素中
      const el = e.target
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) {
        return
      }

      if (e.key === 'F1') {
        e.preventDefault()
        setTheme('off')
      } else if (e.key === 'F2') {
        e.preventDefault()
        setTheme('gameboy')
      } else if (e.key === 'F3') {
        e.preventDefault()
        setTheme('dos')
      } else if (e.key === 'F4') {
        e.preventDefault()
        setTheme('vhs')
      }
    }

    window.addEventListener('keydown', handleKeydown)
  }

  // 自动初始化键盘快捷键
  if (import.meta.client) {
    initKeyboardShortcuts()
  }

  return {
    theme: readonly(theme),
    setTheme,
    cycleTheme,
    isRetro,
    themeClass,
    themeName,
    VALID_THEMES
  }
}
