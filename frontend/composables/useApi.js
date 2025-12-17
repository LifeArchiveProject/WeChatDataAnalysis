// API请求组合式函数
export const useApi = () => {
  const config = useRuntimeConfig()
  
  // 基础请求函数
  const request = async (url, options = {}) => {
    try {
      // 在客户端使用完整的API路径
      const baseURL = process.client ? 'http://localhost:8000/api' : '/api'
      
      const response = await $fetch(url, {
        baseURL,
        ...options,
        onResponseError({ response }) {
          if (response.status === 400) {
            throw new Error(response._data?.detail || '请求参数错误')
          } else if (response.status === 500) {
            throw new Error('服务器错误，请稍后重试')
          }
        }
      })
      return response
    } catch (error) {
      console.error('API请求错误:', error)
      throw error
    }
  }
  
  // 微信检测API
  const detectWechat = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.data_root_path) {
      query.set('data_root_path', params.data_root_path)
    }
    const url = '/wechat-detection' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }
  
  // 检测当前登录账号API
  const detectCurrentAccount = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.data_root_path) {
      query.set('data_root_path', params.data_root_path)
    }
    const url = '/current-account' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }
  
  // 数据库解密API
  const decryptDatabase = async (data) => {
    return await request('/decrypt', {
      method: 'POST',
      body: data
    })
  }
  
  // 健康检查API
  const healthCheck = async () => {
    return await request('/health')
  }

  const listChatAccounts = async () => {
    return await request('/chat/accounts')
  }

  const listChatSessions = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.limit != null) query.set('limit', String(params.limit))
    if (params && params.include_hidden != null) query.set('include_hidden', String(!!params.include_hidden))
    if (params && params.include_official != null) query.set('include_official', String(!!params.include_official))
    const url = '/chat/sessions' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const listChatMessages = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.limit != null) query.set('limit', String(params.limit))
    if (params && params.offset != null) query.set('offset', String(params.offset))
    if (params && params.order) query.set('order', params.order)
    const url = '/chat/messages' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const openChatMediaFolder = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.kind) query.set('kind', params.kind)
    if (params && params.md5) query.set('md5', params.md5)
    if (params && params.server_id != null) query.set('server_id', String(params.server_id))
    const url = '/chat/media/open_folder' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url, { method: 'POST' })
  }

  // 获取图片解密密钥
  const getMediaKeys = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.force_extract) query.set('force_extract', 'true')
    const url = '/media/keys' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 保存图片解密密钥
  const saveMediaKeys = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.xor_key) query.set('xor_key', params.xor_key)
    if (params && params.aes_key) query.set('aes_key', params.aes_key)
    const url = '/media/keys' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url, { method: 'POST', body: { account: params.account, force_extract: false } })
  }

  // 批量解密所有图片
  const decryptAllMedia = async (params = {}) => {
    return await request('/media/decrypt_all', {
      method: 'POST',
      body: {
        account: params.account || null,
        xor_key: params.xor_key || null,
        aes_key: params.aes_key || null
      }
    })
  }
  
  return {
    detectWechat,
    detectCurrentAccount,
    decryptDatabase,
    healthCheck,
    listChatAccounts,
    listChatSessions,
    listChatMessages,
    openChatMediaFolder,
    getMediaKeys,
    saveMediaKeys,
    decryptAllMedia
  }
}