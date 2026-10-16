import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    // API连接状态
    apiStatus: 'unknown', // unknown, connected, error
    apiMessage: '',
    
    // 最近的检测结果
    lastDetectionResult: null,
    
    // 当前登录账号信息
    currentAccount: null,
    
    // 全局加载状态
    globalLoading: false,
    
    // 全局错误信息
    globalError: null
  }),
  
  actions: {
    // 设置API状态
    setApiStatus(status, message = '') {
      this.apiStatus = status
      this.apiMessage = message
    },
    
    // 保存检测结果
    saveDetectionResult(result) {
      this.lastDetectionResult = result
    },
    
    // 设置当前登录账号
    setCurrentAccount(account) {
      this.currentAccount = account
    },
    
    // 设置全局加载状态
    setGlobalLoading(loading) {
      this.globalLoading = loading
    },
    
    // 设置全局错误
    setGlobalError(error) {
      this.globalError = error
      // 3秒后自动清除错误
      if (error) {
        setTimeout(() => {
          this.globalError = null
        }, 3000)
      }
    },
    
    // 清除全局错误
    clearGlobalError() {
      this.globalError = null
    }
  },
  
  getters: {
    // 是否已连接到API
    isApiConnected: (state) => state.apiStatus === 'connected',
    
    // 是否有检测结果
    hasDetectionResult: (state) => state.lastDetectionResult !== null,
    
    // 获取可用的数据库路径列表
    availableDbPaths: (state) => {
      if (!state.lastDetectionResult || !state.lastDetectionResult.data) {
        return []
      }
      
      const accounts = state.lastDetectionResult.data.user_accounts || []
      return accounts
        .filter(account => account.db_storage_path)
        .map(account => ({
          wxid: account.wxid,
          path: account.db_storage_path
        }))
    }
  }
})