// 客户端插件：检查API连接状态
export default defineNuxtPlugin(async (nuxtApp) => {
  const { healthCheck } = useApi()
  const appStore = useAppStore()
  
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
  
  // 初始检查
  await checkApiConnection()
  
  // 定期检查（每30秒）
  setInterval(checkApiConnection, 30000)
})