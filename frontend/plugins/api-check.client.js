// 客户端插件：检查API连接状态
export default defineNuxtPlugin((nuxtApp) => {
  const { healthCheck } = useApi()
  const appStore = useAppStore()
  let intervalId = 0
  
  // 检查API连接
  const checkApiConnection = async () => {
    try {
      const result = await healthCheck()
      if (result.status === 'healthy') {
        appStore.setApiStatus('connected', '已连接到后端API')
      } else {
        appStore.setApiStatus('error', 'API响应异常')
      }
    } catch (error) {
      appStore.setApiStatus('error', '无法连接到后端API，请确保后端服务已启动')
      console.error('API连接失败:', error)
    }
  }

  nuxtApp.hook('app:mounted', () => {
    void checkApiConnection()

    if (!intervalId) {
      intervalId = window.setInterval(() => {
        void checkApiConnection()
      }, 30000)
    }
  })
})
