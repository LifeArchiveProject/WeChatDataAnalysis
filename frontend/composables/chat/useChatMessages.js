import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import {
  formatFileSize,
  formatTimeDivider,
  getVoiceDurationInSeconds,
  getVoiceWidth
} from '~/lib/chat/formatters'
import { createMessageNormalizer, dedupeMessagesById } from '~/lib/chat/message-normalizer'

export const useChatMessages = ({
  api,
  apiBase,
  selectedAccount,
  selectedContact,
  realtimeStore,
  realtimeEnabled,
  desktopAutoRealtime,
  privacyMode,
  searchContext
}) => {
  const messagePageSize = 50

  const allMessages = ref({})
  const messagesMeta = ref({})
  const isLoadingMessages = ref(false)
  const messagesError = ref('')
  const messageContainerRef = ref(null)
  const activeMessagesFor = ref('')
  const showJumpToBottom = ref(false)
  let lastRenderMessagesFingerprint = ''

  const isDesktopRenderer = () => {
    if (!process.client || typeof window === 'undefined') return false
    return !!window.wechatDesktop?.__brand
  }

  const logMessagePhase = (phase, details = {}) => {
    const payload = {
      account: String(selectedAccount.value || '').trim(),
      selectedUsername: String(selectedContact.value?.username || '').trim(),
      activeMessagesFor: String(activeMessagesFor.value || '').trim(),
      ...details
    }

    if (isDesktopRenderer()) {
      try {
        window.wechatDesktop?.logDebug?.('chat-messages', phase, payload)
      } catch {}
    }

    console.info(`[chat-messages] ${phase}`, payload)
  }

  const summarizeRenderTypes = (list) => {
    const counts = {}
    for (const item of Array.isArray(list) ? list : []) {
      const key = String(item?.renderType || 'unknown').trim() || 'unknown'
      counts[key] = Number(counts[key] || 0) + 1
    }
    return counts
  }

  const previewImageUrl = ref(null)
  const previewVideoUrl = ref(null)
  const previewVideoPosterUrl = ref('')
  const previewVideoError = ref('')

  const voiceRefs = new Map()
  const currentPlayingVoice = ref(null)
  const playingVoiceId = ref(null)

  const highlightServerIdStr = ref('')
  const highlightMessageId = ref('')
  let highlightTimer = null

  const messageTypeFilter = ref('all')
  const messageTypeFilterOptions = [
    { value: 'all', label: '全部' },
    { value: 'text', label: '文本' },
    { value: 'image', label: '图片' },
    { value: 'emoji', label: '表情' },
    { value: 'video', label: '视频' },
    { value: 'voice', label: '语音' },
    { value: 'file', label: '文件' },
    { value: 'link', label: '链接' },
    { value: 'quote', label: '引用' },
    { value: 'chatHistory', label: '聊天记录' },
    { value: 'transfer', label: '转账' },
    { value: 'redPacket', label: '红包' },
    { value: 'location', label: '位置' },
    { value: 'voip', label: '通话' },
    { value: 'system', label: '系统' }
  ]

  const normalizeMessage = createMessageNormalizer({
    apiBase,
    getSelectedAccount: () => selectedAccount.value,
    getSelectedContact: () => selectedContact.value
  })

  const messages = computed(() => {
    if (!selectedContact.value) return []
    return allMessages.value[selectedContact.value.username] || []
  })

  const hasMoreMessages = computed(() => {
    if (!selectedContact.value) return false
    const key = selectedContact.value.username
    const meta = messagesMeta.value[key]
    if (!meta) return false
    if (meta.hasMore != null) return !!meta.hasMore
    const total = Number(meta.total || 0)
    const loaded = messages.value.length
    return total > loaded
  })

  const reverseMessageSides = ref(false)
  const reverseSidesStorageKey = computed(() => {
    const account = String(selectedAccount.value || '').trim()
    const username = String(selectedContact.value?.username || '').trim()
    if (account && username) return `wechatda:reverse_message_sides:${account}:${username}`
    return 'wechatda:reverse_message_sides:global'
  })

  const loadReverseMessageSides = () => {
    if (!process.client) return
    try {
      const value = localStorage.getItem(reverseSidesStorageKey.value)
      reverseMessageSides.value = value === '1'
    } catch {}
  }

  watch(reverseSidesStorageKey, () => loadReverseMessageSides(), { immediate: true })
  watch(reverseMessageSides, (value) => {
    if (!process.client) return
    try {
      localStorage.setItem(reverseSidesStorageKey.value, value ? '1' : '0')
    } catch {}
  })

  const toggleReverseMessageSides = () => {
    reverseMessageSides.value = !reverseMessageSides.value
  }

  const renderMessages = computed(() => {
    const list = messages.value || []
    const reverseSides = !!reverseMessageSides.value
    const fingerprint = `${String(selectedContact.value?.username || '').trim()}:${list.length}:${reverseSides ? '1' : '0'}`
    const shouldLogRender = isDesktopRenderer() && fingerprint !== lastRenderMessagesFingerprint
    if (shouldLogRender) {
      logMessagePhase('renderMessages:start', {
        count: list.length,
        reverseSides
      })
    }
    let previousTs = 0
    const rendered = list.map((message) => {
      const ts = Number(message.createTime || 0)
      const show = !previousTs || (ts && Math.abs(ts - previousTs) >= 300)
      if (ts) previousTs = ts
      const originalIsSent = !!message?.isSent
      return {
        ...message,
        _originalIsSent: originalIsSent,
        isSent: reverseSides ? !originalIsSent : originalIsSent,
        showTimeDivider: !!show,
        timeDivider: formatTimeDivider(ts)
      }
    })
    if (shouldLogRender) {
      lastRenderMessagesFingerprint = fingerprint
      logMessagePhase('renderMessages:end', {
        count: rendered.length,
        reverseSides
      })
    }
    return rendered
  })

  const updateJumpToBottomState = () => {
    const container = messageContainerRef.value
    if (!container) {
      showJumpToBottom.value = false
      return
    }
    const distance = container.scrollHeight - container.scrollTop - container.clientHeight
    showJumpToBottom.value = distance > 160
  }

  const scrollToBottom = () => {
    const container = messageContainerRef.value
    if (!container) return
    container.scrollTop = container.scrollHeight
    updateJumpToBottomState()
  }

  const flashMessage = (id) => {
    highlightMessageId.value = String(id || '').trim()
    if (highlightTimer) clearTimeout(highlightTimer)
    highlightTimer = setTimeout(() => {
      highlightMessageId.value = ''
      highlightServerIdStr.value = ''
      highlightTimer = null
    }, 2200)
  }

  const scrollToMessageId = async (id) => {
    const target = String(id || '').trim()
    if (!target) return false
    await nextTick()
    const container = messageContainerRef.value
    const element = container?.querySelector?.(`[data-msg-id="${CSS.escape(target)}"]`)
    if (!element || typeof element.scrollIntoView !== 'function') return false
    element.scrollIntoView({ block: 'center', behavior: 'smooth' })
    return true
  }

  const openImagePreview = (url) => {
    previewImageUrl.value = String(url || '').trim() || null
  }

  const closeImagePreview = () => {
    previewImageUrl.value = null
  }

  const openVideoPreview = (url, poster) => {
    previewVideoUrl.value = String(url || '').trim() || null
    previewVideoPosterUrl.value = String(poster || '').trim()
    previewVideoError.value = ''
  }

  const closeVideoPreview = () => {
    previewVideoUrl.value = null
    previewVideoPosterUrl.value = ''
    previewVideoError.value = ''
  }

  const onPreviewVideoError = () => {
    previewVideoError.value = '视频加载失败，可能是资源不存在或无法访问。'
  }

  const setVoiceRef = (id, element) => {
    const key = String(id || '').trim()
    if (!key) return
    if (element) {
      voiceRefs.set(key, element)
    } else {
      voiceRefs.delete(key)
    }
  }

  const playVoiceById = async (voiceId) => {
    const key = String(voiceId || '').trim()
    if (!key) return
    const audio = voiceRefs.get(key)
    if (!audio) return

    try {
      if (currentPlayingVoice.value && currentPlayingVoice.value !== audio) {
        currentPlayingVoice.value.pause()
        currentPlayingVoice.value.currentTime = 0
      }
    } catch {}

    if (currentPlayingVoice.value === audio && !audio.paused) {
      try {
        audio.pause()
        audio.currentTime = 0
      } catch {}
      currentPlayingVoice.value = null
      playingVoiceId.value = null
      return
    }

    try {
      await audio.play()
      currentPlayingVoice.value = audio
      playingVoiceId.value = key
      audio.onended = () => {
        if (playingVoiceId.value === key) {
          currentPlayingVoice.value = null
          playingVoiceId.value = null
        }
      }
    } catch {}
  }

  const playVoice = async (message) => {
    await playVoiceById(message?.id)
  }

  const getQuoteVoiceId = (message) => `quote-${String(message?.quoteServerId || message?.id || '')}`

  const playQuoteVoice = async (message) => {
    await playVoiceById(getQuoteVoiceId(message))
  }

  const isQuotedVoice = (message) => String(message?.quoteType || '').trim() === '34'
  const isQuotedImage = (message) => {
    return !!String(message?.quoteImageUrl || '').trim() || String(message?.quoteContent || '').trim() === '[图片]'
  }
  const isQuotedLink = (message) => {
    return String(message?.quoteType || '').trim() === '5' || !!String(message?.quoteThumbUrl || '').trim()
  }
  const getQuotedLinkText = (message) => {
    const title = String(message?.quoteTitle || '').trim()
    const content = String(message?.quoteContent || '').trim()
    return content || title || ''
  }

  const onQuoteImageError = (message) => {
    if (message) message._quoteImageError = true
  }

  const onQuoteThumbError = (message) => {
    if (message) message._quoteThumbError = true
  }

  const onAvatarError = (event, target) => {
    try { event?.target && (event.target.style.display = 'none') } catch {}
    try { if (target) target.avatar = null } catch {}
  }

  const shouldShowEmojiDownload = (message) => {
    if (!message?.emojiMd5) return false
    const url = String(message?.emojiRemoteUrl || '').trim()
    if (!url) return false
    if (!/^https?:\/\//i.test(url)) return false
    return true
  }

  const onEmojiDownloadClick = async (message) => {
    if (!process.client) return
    if (!message?.emojiMd5) return
    if (!selectedAccount.value) return

    const emojiUrl = String(message?.emojiRemoteUrl || '').trim()
    if (!emojiUrl) {
      window.alert('该表情没有可用的下载地址')
      return
    }
    if (message._emojiDownloading) return

    message._emojiDownloading = true
    try {
      await api.downloadChatEmoji({
        account: selectedAccount.value,
        md5: message.emojiMd5,
        emoji_url: emojiUrl,
        force: false
      })
      message._emojiDownloaded = true
      if (message.emojiLocalUrl) {
        message.emojiUrl = message.emojiLocalUrl
      }
    } catch (error) {
      window.alert(error?.message || '下载失败')
    } finally {
      message._emojiDownloading = false
    }
  }

  const onFileClick = async (message) => {
    if (!message?.fileMd5) return
    try {
      if (!selectedAccount.value) return
      if (!selectedContact.value?.username) return
      await api.openChatMediaFolder({
        account: selectedAccount.value,
        username: selectedContact.value.username,
        kind: 'file',
        md5: message.fileMd5
      })
    } catch (error) {
      console.error('打开文件夹失败:', error)
    }
  }

  const loadMessages = async ({ username, reset }) => {
    if (!username || !selectedAccount.value) return

    logMessagePhase('loadMessages:enter', {
      username,
      reset
    })
    messagesError.value = ''
    isLoadingMessages.value = true
    activeMessagesFor.value = username

    try {
      const existing = allMessages.value[username] || []
      const container = messageContainerRef.value
      const beforeScrollHeight = container ? container.scrollHeight : 0
      const beforeScrollTop = container ? container.scrollTop : 0
      const offset = reset ? 0 : existing.length

      const params = {
        account: selectedAccount.value,
        username,
        limit: messagePageSize,
        offset,
        order: 'asc'
      }
      if (messageTypeFilter.value && messageTypeFilter.value !== 'all') {
        params.render_types = messageTypeFilter.value
      }
      if (realtimeEnabled.value) {
        params.source = 'realtime'
      }
      logMessagePhase('loadMessages:request:start', {
        username,
        reset,
        offset,
        existingCount: existing.length,
        renderTypeFilter: messageTypeFilter.value,
        realtime: !!realtimeEnabled.value
      })
      const response = await api.listChatMessages(params)
      logMessagePhase('loadMessages:request:end', {
        username,
        reset,
        rawCount: Array.isArray(response?.messages) ? response.messages.length : 0,
        total: Number(response?.total || 0),
        hasMore: response?.hasMore
      })

      const raw = response?.messages || []
      logMessagePhase('loadMessages:normalize:start', {
        username,
        rawCount: raw.length
      })
      const mapped = dedupeMessagesById(raw.map(normalizeMessage))
      logMessagePhase('loadMessages:normalize:end', {
        username,
        mappedCount: mapped.length,
        renderTypeCounts: summarizeRenderTypes(mapped)
      })

      if (activeMessagesFor.value !== username) {
        logMessagePhase('loadMessages:abort-stale', {
          username,
          activeMessagesFor: activeMessagesFor.value
        })
        return
      }

      logMessagePhase('loadMessages:state-commit:start', {
        username,
        reset,
        mappedCount: mapped.length
      })
      if (reset) {
        allMessages.value = { ...allMessages.value, [username]: mapped }
      } else {
        const existingIds = new Set(existing.map((message) => String(message?.id || '')))
        const older = mapped.filter((message) => {
          const id = String(message?.id || '')
          if (!id) return true
          if (existingIds.has(id)) return false
          existingIds.add(id)
          return true
        })
        allMessages.value = {
          ...allMessages.value,
          [username]: [...older, ...existing]
        }
      }
      logMessagePhase('loadMessages:state-commit:end', {
        username,
        storedCount: (allMessages.value[username] || []).length
      })

      messagesMeta.value = {
        ...messagesMeta.value,
        [username]: {
          total: Number(response?.total || 0),
          hasMore: response?.hasMore
        }
      }
      logMessagePhase('loadMessages:meta-commit:end', {
        username,
        total: Number(response?.total || 0),
        hasMore: response?.hasMore
      })

      logMessagePhase('loadMessages:nextTick:start', {
        username
      })
      await nextTick()
      logMessagePhase('loadMessages:nextTick:end', {
        username,
        renderedCount: (allMessages.value[username] || []).length
      })
      const nextContainer = messageContainerRef.value
      if (nextContainer) {
        if (reset) {
          nextContainer.scrollTop = nextContainer.scrollHeight
        } else {
          const afterScrollHeight = nextContainer.scrollHeight
          nextContainer.scrollTop = beforeScrollTop + (afterScrollHeight - beforeScrollHeight)
        }
      }
      updateJumpToBottomState()
      logMessagePhase('loadMessages:scroll:end', {
        username,
        hasContainer: !!nextContainer,
        scrollTop: nextContainer ? nextContainer.scrollTop : null,
        scrollHeight: nextContainer ? nextContainer.scrollHeight : null
      })
    } catch (error) {
      console.error('[chat-messages] loadMessages:error', {
        account: String(selectedAccount.value || '').trim(),
        username: String(username || '').trim(),
        reset: !!reset,
        error
      })
      messagesError.value = error?.message || '加载聊天记录失败'
    } finally {
      isLoadingMessages.value = false
      logMessagePhase('loadMessages:exit', {
        username,
        reset,
        loading: isLoadingMessages.value,
        error: messagesError.value
      })
    }
  }

  const loadMoreMessages = async () => {
    if (!selectedContact.value) return
    if (searchContext.value?.active) return
    await loadMessages({ username: selectedContact.value.username, reset: false })
  }

  const refreshSelectedMessages = async () => {
    if (!selectedContact.value) return
    await loadMessages({ username: selectedContact.value.username, reset: true })
  }

  const refreshRealtimeIncremental = async () => {
    if (!realtimeEnabled.value || !selectedAccount.value || !selectedContact.value?.username) return
    if (searchContext.value?.active || isLoadingMessages.value) return

    const username = selectedContact.value.username
    const existing = allMessages.value[username] || []
    if (!existing.length) return

    const container = messageContainerRef.value
    const atBottom = !!container && (container.scrollHeight - container.scrollTop - container.clientHeight) < 80

    const params = {
      account: selectedAccount.value,
      username,
      limit: 30,
      offset: 0,
      order: 'asc',
      source: 'realtime'
    }
    if (messageTypeFilter.value && messageTypeFilter.value !== 'all') {
      params.render_types = messageTypeFilter.value
    }

    try {
      const response = await api.listChatMessages(params)
      if (selectedContact.value?.username !== username) return

      const rawMessages = response?.messages || []
      const latest = rawMessages.map(normalizeMessage)

      const seenIds = new Set(existing.map((message) => String(message?.id || '')))
      const newOnes = []
      for (const message of latest) {
        const id = String(message?.id || '')
        if (!id || seenIds.has(id)) continue
        seenIds.add(id)
        newOnes.push(message)
      }
      if (!newOnes.length) return

      allMessages.value = { ...allMessages.value, [username]: [...existing, ...newOnes] }

      await nextTick()
      const nextContainer = messageContainerRef.value
      if (nextContainer && atBottom) {
        nextContainer.scrollTop = nextContainer.scrollHeight
      }
      updateJumpToBottomState()
    } catch (error) {
      console.error('[chat-messages] refreshRealtimeIncremental:error', {
        account: String(selectedAccount.value || '').trim(),
        username: String(username || '').trim(),
        error
      })
    }
  }

  let realtimeRefreshFuture = null
  let realtimeRefreshQueued = false

  const queueRealtimeRefresh = () => {
    if (realtimeRefreshFuture) {
      realtimeRefreshQueued = true
      return
    }

    realtimeRefreshFuture = refreshRealtimeIncremental().finally(() => {
      realtimeRefreshFuture = null
      if (realtimeRefreshQueued) {
        realtimeRefreshQueued = false
        queueRealtimeRefresh()
      }
    })
  }

  const tryEnableRealtimeAuto = async () => {
    if (!process.client || typeof window === 'undefined') return
    if (!desktopAutoRealtime.value || realtimeEnabled.value || !selectedAccount.value) return
    try {
      await realtimeStore.enable({ silent: true })
    } catch {}
  }

  const clearVoicePlaybackState = () => {
    try {
      currentPlayingVoice.value?.pause?.()
      if (currentPlayingVoice.value) currentPlayingVoice.value.currentTime = 0
    } catch {}
    currentPlayingVoice.value = null
    playingVoiceId.value = null
    voiceRefs.clear()
  }

  const resetMessageState = () => {
    clearVoicePlaybackState()
    allMessages.value = {}
    messagesMeta.value = {}
    messagesError.value = ''
    highlightMessageId.value = ''
    highlightServerIdStr.value = ''
  }

  const contactProfileCardOpen = ref(false)
  const contactProfileCardMessageId = ref('')
  const contactProfileLoading = ref(false)
  const contactProfileError = ref('')
  const contactProfileData = ref(null)
  let contactProfileHoverHideTimer = null

  const contactProfileResolvedName = computed(() => {
    const profile = contactProfileData.value || {}
    const displayName = String(profile?.displayName || '').trim()
    if (displayName) return displayName
    const contactName = String(selectedContact.value?.name || '').trim()
    if (contactName) return contactName
    return String(profile?.username || selectedContact.value?.username || '').trim()
  })

  const contactProfileResolvedUsername = computed(() => {
    const profile = contactProfileData.value || {}
    return String(profile?.username || selectedContact.value?.username || '').trim()
  })

  const contactProfileResolvedNickname = computed(() => String(contactProfileData.value?.nickname || '').trim())
  const contactProfileResolvedAlias = computed(() => String(contactProfileData.value?.alias || '').trim())
  const contactProfileResolvedRegion = computed(() => String(contactProfileData.value?.region || '').trim())
  const contactProfileResolvedRemark = computed(() => String(contactProfileData.value?.remark || '').trim())
  const contactProfileResolvedSignature = computed(() => String(contactProfileData.value?.signature || '').trim())
  const contactProfileResolvedSource = computed(() => String(contactProfileData.value?.source || '').trim())
  const contactProfileResolvedAvatar = computed(() => {
    const avatar = String(contactProfileData.value?.avatar || '').trim()
    if (avatar) return avatar
    return String(selectedContact.value?.avatar || '').trim()
  })

  const contactProfileResolvedGender = computed(() => {
    const value = contactProfileData.value?.gender
    if (value == null || value === '') return ''
    const gender = Number(value)
    if (!Number.isFinite(gender)) return ''
    if (gender === 1) return '男'
    if (gender === 2) return '女'
    if (gender === 0) return '未知'
    return String(gender)
  })

  const contactProfileResolvedSourceScene = computed(() => {
    const value = contactProfileData.value?.sourceScene
    if (value == null || value === '') return null
    const scene = Number(value)
    return Number.isFinite(scene) ? scene : null
  })

  const fetchContactProfile = async (options = {}) => {
    const username = String(options?.username || contactProfileData.value?.username || selectedContact.value?.username || '').trim()
    const displayNameFallback = String(options?.displayName || '').trim()
    const avatarFallback = String(options?.avatar || '').trim()
    const account = String(selectedAccount.value || '').trim()
    if (!username || !account) {
      contactProfileData.value = null
      return
    }

    contactProfileLoading.value = true
    contactProfileError.value = ''
    try {
      const response = await api.listChatContacts({
        account,
        include_friends: true,
        include_groups: true,
        include_officials: true
      })
      const list = Array.isArray(response?.contacts) ? response.contacts : []
      const matched = list.find((item) => String(item?.username || '').trim() === username)
      if (matched) {
        const normalized = { ...matched, username }
        if (!String(normalized.displayName || '').trim() && displayNameFallback) {
          normalized.displayName = displayNameFallback
        }
        if (!String(normalized.avatar || '').trim() && avatarFallback) {
          normalized.avatar = avatarFallback
        }
        contactProfileData.value = normalized
      } else {
        contactProfileData.value = {
          username,
          displayName: displayNameFallback || selectedContact.value?.name || username,
          avatar: avatarFallback || selectedContact.value?.avatar || '',
          nickname: '',
          alias: '',
          gender: null,
          region: '',
          remark: '',
          signature: '',
          source: '',
          sourceScene: null
        }
      }
    } catch (error) {
      contactProfileData.value = {
        username,
        displayName: displayNameFallback || selectedContact.value?.name || username,
        avatar: avatarFallback || selectedContact.value?.avatar || '',
        nickname: '',
        alias: '',
        gender: null,
        region: '',
        remark: '',
        signature: '',
        source: '',
        sourceScene: null
      }
      contactProfileError.value = error?.message || '加载联系人资料失败'
    } finally {
      contactProfileLoading.value = false
    }
  }

  const clearContactProfileHoverHideTimer = () => {
    if (contactProfileHoverHideTimer) {
      clearTimeout(contactProfileHoverHideTimer)
      contactProfileHoverHideTimer = null
    }
  }

  const closeContactProfileCard = () => {
    contactProfileCardOpen.value = false
    contactProfileCardMessageId.value = ''
  }

  const onMessageAvatarMouseEnter = async (message) => {
    if (!!message?.isSent) return
    const messageId = String(message?.id ?? '').trim()
    if (!messageId) return
    const username = String(message?.senderUsername || '').trim()
    if (!username || username === 'self') return

    const senderName = String(message?.senderDisplayName || message?.sender || '').trim()
    const senderAvatar = String(message?.avatar || '').trim()
    if (!contactProfileData.value || String(contactProfileData.value?.username || '').trim() !== username) {
      contactProfileData.value = {
        username,
        displayName: senderName || username,
        avatar: senderAvatar,
        nickname: '',
        alias: '',
        gender: null,
        region: '',
        remark: '',
        signature: '',
        source: '',
        sourceScene: null
      }
    } else {
      if (!String(contactProfileData.value?.displayName || '').trim() && senderName) {
        contactProfileData.value.displayName = senderName
      }
      if (!String(contactProfileData.value?.avatar || '').trim() && senderAvatar) {
        contactProfileData.value.avatar = senderAvatar
      }
    }

    clearContactProfileHoverHideTimer()
    contactProfileCardMessageId.value = messageId
    contactProfileCardOpen.value = true
    await fetchContactProfile({ username, displayName: senderName, avatar: senderAvatar })
  }

  const onMessageAvatarMouseLeave = () => {
    clearContactProfileHoverHideTimer()
    contactProfileHoverHideTimer = setTimeout(() => {
      closeContactProfileCard()
    }, 120)
  }

  const onContactCardMouseEnter = () => {
    clearContactProfileHoverHideTimer()
  }

  watch(
    () => selectedContact.value?.username,
    () => {
      clearContactProfileHoverHideTimer()
      closeContactProfileCard()
      contactProfileError.value = ''
      contactProfileData.value = null
    }
  )

  watch(
    () => selectedAccount.value,
    () => {
      clearContactProfileHoverHideTimer()
      closeContactProfileCard()
      contactProfileError.value = ''
      contactProfileData.value = null
    }
  )

  onUnmounted(() => {
    if (highlightTimer) clearTimeout(highlightTimer)
    highlightTimer = null
    clearContactProfileHoverHideTimer()
    clearVoicePlaybackState()
  })

  return {
    allMessages,
    messagesMeta,
    messages,
    renderMessages,
    hasMoreMessages,
    isLoadingMessages,
    messagesError,
    messageContainerRef,
    showJumpToBottom,
    messagePageSize,
    messageTypeFilter,
    messageTypeFilterOptions,
    reverseMessageSides,
    previewImageUrl,
    previewVideoUrl,
    previewVideoPosterUrl,
    previewVideoError,
    voiceRefs,
    currentPlayingVoice,
    playingVoiceId,
    highlightServerIdStr,
    highlightMessageId,
    contactProfileCardOpen,
    contactProfileCardMessageId,
    contactProfileLoading,
    contactProfileError,
    contactProfileData,
    contactProfileResolvedName,
    contactProfileResolvedUsername,
    contactProfileResolvedNickname,
    contactProfileResolvedAlias,
    contactProfileResolvedGender,
    contactProfileResolvedRegion,
    contactProfileResolvedRemark,
    contactProfileResolvedSignature,
    contactProfileResolvedSource,
    contactProfileResolvedSourceScene,
    contactProfileResolvedAvatar,
    normalizeMessage,
    updateJumpToBottomState,
    scrollToBottom,
    flashMessage,
    scrollToMessageId,
    openImagePreview,
    closeImagePreview,
    openVideoPreview,
    closeVideoPreview,
    onPreviewVideoError,
    setVoiceRef,
    playVoice,
    playQuoteVoice,
    getQuoteVoiceId,
    getVoiceDurationInSeconds,
    getVoiceWidth,
    isQuotedVoice,
    isQuotedImage,
    isQuotedLink,
    getQuotedLinkText,
    onQuoteImageError,
    onQuoteThumbError,
    onAvatarError,
    shouldShowEmojiDownload,
    onEmojiDownloadClick,
    onFileClick,
    toggleReverseMessageSides,
    loadMessages,
    loadMoreMessages,
    refreshSelectedMessages,
    refreshRealtimeIncremental,
    queueRealtimeRefresh,
    tryEnableRealtimeAuto,
    resetMessageState,
    fetchContactProfile,
    clearContactProfileHoverHideTimer,
    closeContactProfileCard,
    onMessageAvatarMouseEnter,
    onMessageAvatarMouseLeave,
    onContactCardMouseEnter,
    formatFileSize
  }
}
