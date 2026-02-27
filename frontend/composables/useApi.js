// API请求组合式函数
export const useApi = () => {
  const config = useRuntimeConfig()
  
  // 基础请求函数
  const request = async (url, options = {}) => {
    try {
      // Default to same-origin `/api` so Nuxt devProxy / backend-mounted UI both work.
      // Override via `NUXT_PUBLIC_API_BASE`, e.g. `http://127.0.0.1:8000/api`.
      const apiBase = String(config?.public?.apiBase || '').trim()
      const baseURL = (apiBase ? apiBase : '/api').replace(/\/$/, '')
      
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
    if (params && params.source) query.set('source', params.source)
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
    if (params && params.render_types) query.set('render_types', params.render_types)
    if (params && params.source) query.set('source', params.source)
    const url = '/chat/messages' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const getChatMessageRaw = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.message_id) query.set('message_id', params.message_id)
    const url = '/chat/messages/raw' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const editChatMessage = async (payload = {}) => {
    return await request('/chat/messages/edit', {
      method: 'POST',
      body: payload
    })
  }

  const repairChatMessageSender = async (payload = {}) => {
    return await request('/chat/messages/repair_sender', {
      method: 'POST',
      body: payload
    })
  }

  // Flip message direction in the WeChat client by swapping packed_info_data (unsafe, but undoable via reset).
  const flipChatMessageDirection = async (payload = {}) => {
    return await request('/chat/messages/flip_direction', {
      method: 'POST',
      body: payload
    })
  }

  const listChatEditedSessions = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    const url = '/chat/edits/sessions' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const listChatEditedMessages = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    const url = '/chat/edits/messages' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const getChatEditStatus = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.message_id) query.set('message_id', params.message_id)
    const url = '/chat/edits/message_status' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const resetChatEditedMessage = async (payload = {}) => {
    return await request('/chat/edits/reset_message', {
      method: 'POST',
      body: payload
    })
  }

  const resetChatEditedSession = async (payload = {}) => {
    return await request('/chat/edits/reset_session', {
      method: 'POST',
      body: payload
    })
  }

  const getChatRealtimeStatus = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    const url = '/chat/realtime/status' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const syncChatRealtimeMessages = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.max_scan != null) query.set('max_scan', String(params.max_scan))
    if (params && params.backfill_limit != null) query.set('backfill_limit', String(params.backfill_limit))
    const url = '/chat/realtime/sync' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url, { method: 'POST' })
  }

  const syncChatRealtimeAll = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.max_scan != null) query.set('max_scan', String(params.max_scan))
    if (params && params.priority_username) query.set('priority_username', params.priority_username)
    if (params && params.priority_max_scan != null) query.set('priority_max_scan', String(params.priority_max_scan))
    if (params && params.include_hidden != null) query.set('include_hidden', String(!!params.include_hidden))
    if (params && params.include_official != null) query.set('include_official', String(!!params.include_official))
    const url = '/chat/realtime/sync_all' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url, { method: 'POST' })
  }

  const searchChatMessages = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.q) query.set('q', params.q)
    if (params && params.username) query.set('username', params.username)
    if (params && params.sender) query.set('sender', params.sender)
    if (params && params.session_type) query.set('session_type', params.session_type)
    if (params && params.limit != null) query.set('limit', String(params.limit))
    if (params && params.offset != null) query.set('offset', String(params.offset))
    if (params && params.start_time != null) query.set('start_time', String(params.start_time))
    if (params && params.end_time != null) query.set('end_time', String(params.end_time))
    if (params && params.render_types) query.set('render_types', params.render_types)
    if (params && params.include_hidden != null) query.set('include_hidden', String(!!params.include_hidden))
    if (params && params.include_official != null) query.set('include_official', String(!!params.include_official))
    if (params && params.session_limit != null) query.set('session_limit', String(params.session_limit))
    if (params && params.per_chat_scan != null) query.set('per_chat_scan', String(params.per_chat_scan))
    if (params && params.scan_limit != null) query.set('scan_limit', String(params.scan_limit))
    const url = '/chat/search' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const listChatSearchSenders = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.session_type) query.set('session_type', params.session_type)
    if (params && params.limit != null) query.set('limit', String(params.limit))
    if (params && params.q) query.set('q', params.q)
    if (params && params.message_q) query.set('message_q', params.message_q)
    if (params && params.start_time != null) query.set('start_time', String(params.start_time))
    if (params && params.end_time != null) query.set('end_time', String(params.end_time))
    if (params && params.render_types) query.set('render_types', params.render_types)
    if (params && params.include_hidden != null) query.set('include_hidden', String(!!params.include_hidden))
    if (params && params.include_official != null) query.set('include_official', String(!!params.include_official))
    const url = '/chat/search-index/senders' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const getChatSearchIndexStatus = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    const url = '/chat/search-index/status' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const buildChatSearchIndex = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.rebuild != null) query.set('rebuild', String(!!params.rebuild))
    const url = '/chat/search-index/build' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url, { method: 'POST' })
  }

  const getChatMessagesAround = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.anchor_id) query.set('anchor_id', params.anchor_id)
    if (params && params.before != null) query.set('before', String(params.before))
    if (params && params.after != null) query.set('after', String(params.after))
    const url = '/chat/messages/around' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 聊天记录日历热力图：某月每日消息数
  const getChatMessageDailyCounts = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.year != null) query.set('year', String(params.year))
    if (params && params.month != null) query.set('month', String(params.month))
    const url = '/chat/messages/daily_counts' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 聊天记录定位锚点：某日第一条 / 会话最早一条
  const getChatMessageAnchor = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.kind) query.set('kind', String(params.kind))
    if (params && params.date) query.set('date', String(params.date))
    const url = '/chat/messages/anchor' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 解析嵌套合并转发聊天记录（通过 server_id）
  const resolveNestedChatHistory = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.server_id != null) query.set('server_id', String(params.server_id))
    const url = '/chat/chat_history/resolve' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 解析卡片/小程序等 App 消息（通过 server_id）
  const resolveAppMsg = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.server_id != null) query.set('server_id', String(params.server_id))
    const url = '/chat/appmsg/resolve' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 朋友圈时间线
  const listSnsTimeline = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.limit != null) query.set('limit', String(params.limit))
    if (params && params.offset != null) query.set('offset', String(params.offset))
    if (params && params.usernames && Array.isArray(params.usernames) && params.usernames.length > 0) {
      query.set('usernames', params.usernames.join(','))
    } else if (params && params.usernames && typeof params.usernames === 'string') {
      query.set('usernames', params.usernames)
    }
    if (params && params.keyword) query.set('keyword', params.keyword)
    const url = '/sns/timeline' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 朋友圈联系人列表（按发圈数统计）
  const listSnsUsers = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.keyword) query.set('keyword', String(params.keyword))
    if (params && params.limit != null) query.set('limit', String(params.limit))
    const url = '/sns/users' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 朋友圈图片本地缓存候选（用于错图时手动选择）
  const listSnsMediaCandidates = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.create_time != null) query.set('create_time', String(params.create_time))
    if (params && params.width != null) query.set('width', String(params.width))
    if (params && params.height != null) query.set('height', String(params.height))
    if (params && params.limit != null) query.set('limit', String(params.limit))
    if (params && params.offset != null) query.set('offset', String(params.offset))
    const url = '/sns/media_candidates' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 保存朋友圈图片手动匹配结果（本机）
  const saveSnsMediaPicks = async (data = {}) => {
    return await request('/sns/media_picks', {
      method: 'POST',
      body: {
        account: data.account || null,
        picks: (data && data.picks && typeof data.picks === 'object' && !Array.isArray(data.picks)) ? data.picks : {}
      }
    })
  }

  const openChatMediaFolder = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.username) query.set('username', params.username)
    if (params && params.kind) query.set('kind', params.kind)
    if (params && params.md5) query.set('md5', params.md5)
    if (params && params.file_id) query.set('file_id', params.file_id)
    if (params && params.server_id != null) query.set('server_id', String(params.server_id))
    const url = '/chat/media/open_folder' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url, { method: 'POST' })
  }

  const downloadChatEmoji = async (data = {}) => {
    return await request('/chat/media/emoji/download', {
      method: 'POST',
      body: {
        account: data.account || null,
        md5: data.md5 || '',
        emoji_url: data.emoji_url || '',
        force: !!data.force
      }
    })
  }

  // 保存图片解密密钥
  const saveMediaKeys = async (params = {}) => {
    return await request('/media/keys', {
      method: 'POST',
      body: {
        account: params.account || null,
        xor_key: params.xor_key || '',
        aes_key: params.aes_key || null
      }
    })
  }

  // 获取已保存的密钥（数据库密钥 + 图片密钥）
  const getSavedKeys = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    const url = '/keys' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
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

  // 聊天记录导出（离线zip）
  const createChatExport = async (data = {}) => {
    return await request('/chat/exports', {
      method: 'POST',
      body: {
        account: data.account || null,
        scope: data.scope || 'selected',
        usernames: Array.isArray(data.usernames) ? data.usernames : [],
        format: data.format || 'json',
        start_time: data.start_time != null ? Number(data.start_time) : null,
        end_time: data.end_time != null ? Number(data.end_time) : null,
        include_hidden: !!data.include_hidden,
        include_official: !!data.include_official,
        message_types: Array.isArray(data.message_types) ? data.message_types : [],
        include_media: data.include_media == null ? true : !!data.include_media,
        media_kinds: Array.isArray(data.media_kinds) ? data.media_kinds : ['image', 'emoji', 'video', 'video_thumb', 'voice', 'file'],
        output_dir: data.output_dir == null ? null : String(data.output_dir || '').trim(),
        allow_process_key_extract: !!data.allow_process_key_extract,
        download_remote_media: !!data.download_remote_media,
        html_page_size: data.html_page_size != null ? Number(data.html_page_size) : 1000,
        privacy_mode: !!data.privacy_mode,
        file_name: data.file_name || null
      }
    })
  }

  const getChatExport = async (exportId) => {
    if (!exportId) throw new Error('Missing exportId')
    return await request(`/chat/exports/${encodeURIComponent(String(exportId))}`)
  }

  const listChatExports = async () => {
    return await request('/chat/exports')
  }

  const cancelChatExport = async (exportId) => {
    if (!exportId) throw new Error('Missing exportId')
    return await request(`/chat/exports/${encodeURIComponent(String(exportId))}`, { method: 'DELETE' })
  }

  // 朋友圈导出（离线 HTML zip）
  const createSnsExport = async (data = {}) => {
    return await request('/sns/exports', {
      method: 'POST',
      body: {
        account: data.account || null,
        scope: data.scope || 'selected',
        usernames: Array.isArray(data.usernames) ? data.usernames : [],
        use_cache: data.use_cache == null ? true : !!data.use_cache,
        output_dir: data.output_dir == null ? null : String(data.output_dir || '').trim(),
        file_name: data.file_name || null
      }
    })
  }

  const getSnsExport = async (exportId) => {
    if (!exportId) throw new Error('Missing exportId')
    return await request(`/sns/exports/${encodeURIComponent(String(exportId))}`)
  }

  const cancelSnsExport = async (exportId) => {
    if (!exportId) throw new Error('Missing exportId')
    return await request(`/sns/exports/${encodeURIComponent(String(exportId))}`, { method: 'DELETE' })
  }

  // 联系人
  const listChatContacts = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.account) query.set('account', params.account)
    if (params && params.keyword) query.set('keyword', params.keyword)
    if (params && params.include_friends != null) query.set('include_friends', String(!!params.include_friends))
    if (params && params.include_groups != null) query.set('include_groups', String(!!params.include_groups))
    if (params && params.include_officials != null) query.set('include_officials', String(!!params.include_officials))
    const url = '/chat/contacts' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  const exportChatContacts = async (payload = {}) => {
    return await request('/chat/contacts/export', {
      method: 'POST',
      body: {
        account: payload.account || null,
        output_dir: payload.output_dir || '',
        format: payload.format || 'json',
        include_avatar_link: payload.include_avatar_link == null ? true : !!payload.include_avatar_link,
        keyword: payload.keyword || null,
        contact_types: {
          friends: payload?.contact_types?.friends == null ? true : !!payload.contact_types.friends,
          groups: payload?.contact_types?.groups == null ? true : !!payload.contact_types.groups,
          officials: payload?.contact_types?.officials == null ? true : !!payload.contact_types.officials,
        }
      }
    })
  }

  // WeChat Wrapped（年度总结）
  const getWrappedAnnual = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.year != null) query.set('year', String(params.year))
    if (params && params.account) query.set('account', String(params.account))
    if (params && params.refresh != null) query.set('refresh', String(!!params.refresh))
    const url = '/wrapped/annual' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // WeChat Wrapped（年度总结）- 目录/元信息（轻量，用于按页懒加载）
  const getWrappedAnnualMeta = async (params = {}) => {
    const query = new URLSearchParams()
    if (params && params.year != null) query.set('year', String(params.year))
    if (params && params.account) query.set('account', String(params.account))
    if (params && params.refresh != null) query.set('refresh', String(!!params.refresh))
    const url = '/wrapped/annual/meta' + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // WeChat Wrapped（年度总结）- 单张卡片（按页加载）
  const getWrappedAnnualCard = async (cardId, params = {}) => {
    if (cardId == null) throw new Error('Missing cardId')
    const query = new URLSearchParams()
    if (params && params.year != null) query.set('year', String(params.year))
    if (params && params.account) query.set('account', String(params.account))
    if (params && params.refresh != null) query.set('refresh', String(!!params.refresh))
    const safeId = encodeURIComponent(String(cardId))
    const url = `/wrapped/annual/cards/${safeId}` + (query.toString() ? `?${query.toString()}` : '')
    return await request(url)
  }

  // 获取微信进程状态
  const getWxStatus = async () => {
    return await request('/wechat/status')
  }

  // 获取数据库密钥
  const getKeys = async () => {
    return await request('/get_keys')
  }

  // 获取图片密钥
  const getImageKey = async () => {
    return await request('/get_image_key')
  }

  return {
    detectWechat,
    detectCurrentAccount,
    decryptDatabase,
    healthCheck,
    listChatAccounts,
    listChatSessions,
    listChatMessages,
    getChatMessageRaw,
    editChatMessage,
    repairChatMessageSender,
    flipChatMessageDirection,
    listChatEditedSessions,
    listChatEditedMessages,
    getChatEditStatus,
    resetChatEditedMessage,
    resetChatEditedSession,
    getChatRealtimeStatus,
    syncChatRealtimeMessages,
    syncChatRealtimeAll,
    searchChatMessages,
    getChatSearchIndexStatus,
    buildChatSearchIndex,
    listChatSearchSenders,
    getChatMessagesAround,
    getChatMessageDailyCounts,
    getChatMessageAnchor,
    resolveNestedChatHistory,
    resolveAppMsg,
    listSnsTimeline,
    listSnsUsers,
    listSnsMediaCandidates,
    saveSnsMediaPicks,
    openChatMediaFolder,
    downloadChatEmoji,
    saveMediaKeys,
    getSavedKeys,
    decryptAllMedia,
    createChatExport,
    getChatExport,
    listChatExports,
    cancelChatExport,
    createSnsExport,
    getSnsExport,
    cancelSnsExport,
    listChatContacts,
    exportChatContacts,
    getWrappedAnnual,
    getWrappedAnnualMeta,
    getWrappedAnnualCard,
    getKeys,
    getImageKey,
    getWxStatus,
  }
}
