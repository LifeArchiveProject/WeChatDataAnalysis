import { defineStore } from 'pinia'

export const useImgHelperStore = defineStore('imgHelper', () => {
  const enabled = ref(false)
  const checking = ref(false)
  const toggling = ref(false)
  const error = ref('')

  const fetchStatus = async () => {
    if (!process.client) return
    const api = useApi()
    checking.value = true
    error.value = ''
    try {
      const resp = await api.getImgHelperStatus()
      enabled.value = !!resp?.enabled
    } catch (e) {
      error.value = e?.message || '获取插件状态失败'
    } finally {
      checking.value = false
    }
  }

  const toggle = async () => {
    if (toggling.value) return
    
    const targetState = !enabled.value
    
    if (targetState) {
        // Show warning for first time or every time? User said "首次开启提示hook可能存在风控风险"
        // We can use localStorage to track if it's the first time.
        const hasWarned = localStorage.getItem('img_helper_warned')
        if (!hasWarned) {
            const confirmed = window.confirm('【安全提示】\n开启“自动下载大图”功能将使用 Hook 技术修改微信内存逻辑。这可能存在一定的风控风险，建议仅在需要时开启。\n\n确认开启吗？')
            if (!confirmed) return
            localStorage.setItem('img_helper_warned', 'true')
        }
    }

    toggling.value = true
    error.value = ''
    const api = useApi()
    try {
      const resp = await api.toggleImgHelper(targetState)
      enabled.value = !!resp?.enabled
      return true
    } catch (e) {
      error.value = e?.message || '操作失败'
      if (process.client) {
          window.alert(error.value)
      }
      return false
    } finally {
      toggling.value = false
    }
  }

  // Initialize status
  if (process.client) {
    fetchStatus()
  }

  return {
    enabled,
    checking,
    toggling,
    error,
    fetchStatus,
    toggle
  }
})
