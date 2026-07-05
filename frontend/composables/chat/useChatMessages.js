import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import {
  formatFileSize,
  formatTimeDivider,
  getVoiceDurationInSeconds,
  getVoiceWidth
} from '~/lib/chat/formatters'
import { createPerfTrace } from '~/lib/chat/perf-logger'
import { createMessageNormalizer, dedupeMessagesById } from '~/lib/chat/message-normalizer'

const DEFAULT_CHAT_SOURCE = 'auto'

export const useChatMessages = ({
  api,
  apiBase,
  selectedAccount,
  selectedContact,
  realtimeEnabled,
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
  const previewImageItems = ref([])
  const previewImageIndex = ref(-1)
  const previewVideoUrl = ref(null)
  const previewVideoPosterUrl = ref('')
  const previewVideoError = ref('')

  const resourceSidebarOpen = ref(false)
  const resourceTimeGroup = ref('day')
  const resourceItems = ref([])
  const resourceLoading = ref(false)
  const resourceError = ref('')
  const resourceHasMore = ref(true)
  const resourceOffset = ref(0)
  const resourcePageSize = 32
  let resourceScrollCheckScheduled = false

  const voiceRefs = new Map()
  const currentPlayingVoice = ref(null)
  const playingVoiceId = ref(null)

  const highlightServerIdStr = ref('')
  const highlightMessageId = ref('')
  let highlightTimer = null

  const messageTypeFilter = ref('all')
  const localMediaVersion = ref(0)
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
    getSelectedContact: () => selectedContact.value,
    getLocalMediaVersion: () => localMediaVersion.value
  })

  const bumpLocalMediaVersion = () => {
    localMediaVersion.value = (localMediaVersion.value + 1) % 1000000000
    return localMediaVersion.value
  }

  const renormalizeLoadedMessages = (username) => {
    const key = String(username || '').trim()
    if (!key) return
    const existing = allMessages.value[key]
    if (!Array.isArray(existing) || !existing.length) return

    const refreshed = dedupeMessagesById(existing.map((message) => {
      const normalized = normalizeMessage(message)
      return {
        ...message,
        ...normalized,
        _emojiDownloading: !!message?._emojiDownloading,
        _emojiDownloaded: typeof message?._emojiDownloaded === 'boolean' ? message._emojiDownloaded : normalized._emojiDownloaded,
        _quoteImageError: false,
        _quoteThumbError: false
      }
    }))

    allMessages.value = {
      ...allMessages.value,
      [key]: refreshed
    }
  }

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

  const clearReverseMessageSides = () => {
    reverseMessageSides.value = false
    if (!process.client) return
    try {
      localStorage.removeItem(reverseSidesStorageKey.value)
    } catch {}
  }

  watch(reverseSidesStorageKey, () => clearReverseMessageSides(), { immediate: true })

  const toggleReverseMessageSides = () => {
    clearReverseMessageSides()
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

  const toImagePreviewItem = (url, source = {}) => {
    const u = String(url || '').trim()
    if (!u) return null
    return {
      url: u,
      id: String(source?.id || source?.messageId || u),
      createTime: Number(source?.createTime || 0),
      label: String(source?.label || source?.content || '').trim()
    }
  }

  const buildPreviewGalleryFromLoadedMessages = () => {
    const list = Array.isArray(messages.value) ? messages.value : []
    const out = []
    const seen = new Set()
    const push = (url, source = {}) => {
      const item = toImagePreviewItem(url, source)
      if (!item || seen.has(item.url)) return
      seen.add(item.url)
      out.push(item)
    }
    for (const message of list) {
      if (message?.renderType === 'image') {
        push(message.imageUrl, message)
      }
      if (message?.quoteImageUrl) {
        push(message.quoteImageUrl, { ...message, id: `${message.id || ''}:quote-image` })
      }
      if (message?.quoteThumbUrl) {
        push(message.quoteThumbUrl, { ...message, id: `${message.id || ''}:quote-thumb` })
      }
    }
    return out
  }

  const openImagePreview = (url, gallery = null) => {
    const target = String(url || '').trim()
    previewImageUrl.value = target || null
    const source = Array.isArray(gallery) && gallery.length ? gallery : buildPreviewGalleryFromLoadedMessages()
    const normalized = []
    const seen = new Set()
    for (const item of source) {
      const next = typeof item === 'string' ? toImagePreviewItem(item) : toImagePreviewItem(item?.url || item?.imageUrl || item?.thumbUrl, item)
      if (!next || seen.has(next.url)) continue
      seen.add(next.url)
      normalized.push(next)
    }
    if (target && !seen.has(target)) {
      normalized.push(toImagePreviewItem(target))
    }
    previewImageItems.value = normalized.filter(Boolean)
    previewImageIndex.value = previewImageItems.value.findIndex((item) => String(item?.url || '') === target)
    if (previewImageIndex.value < 0 && previewImageItems.value.length) {
      previewImageIndex.value = 0
      previewImageUrl.value = previewImageItems.value[0].url
    }
  }

  const closeImagePreview = () => {
    previewImageUrl.value = null
    previewImageItems.value = []
    previewImageIndex.value = -1
  }

  const previewImageCount = computed(() => previewImageItems.value.length)
  const canSwitchPreviewImage = computed(() => previewImageItems.value.length > 1)

  const switchPreviewImage = (direction) => {
    const list = previewImageItems.value
    if (!Array.isArray(list) || list.length <= 1) return
    const current = Number(previewImageIndex.value || 0)
    const step = Number(direction || 0) < 0 ? -1 : 1
    const next = (current + step + list.length) % list.length
    previewImageIndex.value = next
    previewImageUrl.value = String(list[next]?.url || '') || null
  }

  const showPrevPreviewImage = () => switchPreviewImage(-1)
  const showNextPreviewImage = () => switchPreviewImage(1)

  const previewImageCounterText = computed(() => {
    const total = previewImageItems.value.length
    if (total <= 1) return ''
    const current = Math.max(0, Number(previewImageIndex.value || 0)) + 1
    return `${current} / ${total}`
  })

  const getResourceImageVariant = (message) => {
    const text = [
      message?.imageUrl,
      message?.imageFileId,
      message?.imageMd5
    ].map((v) => String(v || '').toLowerCase()).join(' ')
    if (text.includes('thumb') || text.includes('cdnthumb') || /(^|[_/-])t(\.|_|-|$)/.test(text)) {
      return '缩略图'
    }
    if (String(message?.imageMd5 || '').trim()) return '大图'
    return '缩略图'
  }

  const toResourceItem = (message) => {
    const renderType = String(message?.renderType || '').trim()
    if (renderType === 'image' && message?.imageUrl) {
      const variant = getResourceImageVariant(message)
      return {
        id: String(message?.id || `image:${message?.localId || ''}:${message?.imageUrl || ''}`),
        kind: 'image',
        url: String(message.imageUrl || ''),
        thumbUrl: String(message.imageUrl || ''),
        createTime: Number(message?.createTime || 0),
        message,
        variant,
        variantShort: variant === '大图' ? '大' : '缩'
      }
    }
    if (renderType === 'video' && (message?.videoThumbUrl || message?.videoUrl)) {
      return {
        id: String(message?.id || `video:${message?.localId || ''}:${message?.videoUrl || message?.videoThumbUrl || ''}`),
        kind: 'video',
        url: String(message?.videoUrl || ''),
        thumbUrl: String(message?.videoThumbUrl || message?.videoUrl || ''),
        createTime: Number(message?.createTime || 0),
        message,
        variant: '视频',
        variantShort: '视'
      }
    }
    return null
  }

  const resetResourceState = () => {
    resourceItems.value = []
    resourceOffset.value = 0
    resourceHasMore.value = true
    resourceError.value = ''
  }

  const loadResourceItems = async ({ reset = false } = {}) => {
    if (!selectedAccount.value || !selectedContact.value?.username) return
    if (resourceLoading.value) return
    if (!reset && !resourceHasMore.value) return
    if (reset) resetResourceState()

    resourceLoading.value = true
    resourceError.value = ''
    try {
      const response = await api.listChatMessages({
        account: selectedAccount.value,
        username: selectedContact.value.username,
        limit: resourcePageSize,
        offset: reset ? 0 : resourceOffset.value,
        order: 'desc',
        render_types: 'image,video',
        source: DEFAULT_CHAT_SOURCE
      })
      const raw = Array.isArray(response?.messages) ? response.messages : []
      const mapped = raw.map(normalizeMessage).map(toResourceItem).filter(Boolean)
      const seen = new Set((reset ? [] : resourceItems.value).map((item) => String(item?.id || '')))
      const deduped = mapped.filter((item) => {
        const id = String(item?.id || '')
        if (!id || seen.has(id)) return false
        seen.add(id)
        return true
      })
      resourceItems.value = reset ? deduped : [...resourceItems.value, ...deduped]
      resourceOffset.value = (reset ? 0 : resourceOffset.value) + raw.length
      resourceHasMore.value = !!response?.hasMore
    } catch (error) {
      resourceError.value = error?.message || '加载资源失败'
    } finally {
      resourceLoading.value = false
    }
  }

  const openResourceSidebar = async () => {
    resourceSidebarOpen.value = true
    if (!resourceItems.value.length) {
      await loadResourceItems({ reset: true })
    }
  }

  const closeResourceSidebar = () => {
    resourceSidebarOpen.value = false
  }

  const toggleResourceSidebar = async () => {
    if (resourceSidebarOpen.value) {
      closeResourceSidebar()
      return
    }
    await openResourceSidebar()
  }

  const onResourceSidebarScroll = (event) => {
    const el = event?.target
    if (!el || resourceScrollCheckScheduled) return
    resourceScrollCheckScheduled = true

    const run = () => {
      resourceScrollCheckScheduled = false
      if (resourceLoading.value || !resourceHasMore.value) return
      const distance = Number(el.scrollHeight || 0) - Number(el.scrollTop || 0) - Number(el.clientHeight || 0)
      if (distance < 520) {
        void loadResourceItems()
      }
    }

    if (process.client && typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(run)
    } else {
      setTimeout(run, 16)
    }
  }

  const resourceGroupOptions = [
    { value: 'day', label: '按天' },
    { value: 'week', label: '按周' },
    { value: 'month', label: '按月' },
    { value: 'year', label: '按年' }
  ]

  const formatResourceGroupKey = (ts, mode) => {
    const d = new Date(Number(ts || 0) * 1000)
    if (!Number.isFinite(d.getTime())) return '未知时间'
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    if (mode === 'year') return `${y}年`
    if (mode === 'month') return `${y}年${m}月`
    if (mode === 'week') {
      const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
      const weekDay = tmp.getUTCDay() || 7
      tmp.setUTCDate(tmp.getUTCDate() + 4 - weekDay)
      const weekYear = tmp.getUTCFullYear()
      const yearStart = new Date(Date.UTC(weekYear, 0, 1))
      const week = Math.ceil((((tmp - yearStart) / 86400000) + 1) / 7)
      return `${weekYear}年第${String(week).padStart(2, '0')}周`
    }
    return `${y}-${m}-${day}`
  }

  const groupedResourceItems = computed(() => {
    const groups = []
    let lastKey = ''
    for (const item of resourceItems.value) {
      const key = formatResourceGroupKey(item?.createTime, resourceTimeGroup.value)
      if (key !== lastKey) {
        groups.push({ type: 'divider', key: `divider:${key}`, label: key })
        lastKey = key
      }
      groups.push({ type: 'item', key: `item:${item.id}`, item })
    }
    return groups
  })

  const resourceGridColumnCount = computed(() => {
    const mode = String(resourceTimeGroup.value || 'day')
    if (mode === 'year') return 10
    if (mode === 'month') return 8
    if (mode === 'week') return 4
    return 3
  })

  const resourceGridGap = computed(() => {
    const mode = String(resourceTimeGroup.value || 'day')
    if (mode === 'year') return 4
    if (mode === 'month') return 6
    return 8
  })

  const resourceGridStyle = computed(() => ({
    gridTemplateColumns: `repeat(${resourceGridColumnCount.value}, minmax(0, 1fr))`,
    gap: `${resourceGridGap.value}px`
  }))

  const openResourcePreview = (resource) => {
    if (!resource) return
    if (resource.kind === 'video') {
      openVideoPreview(resource.url, resource.thumbUrl)
      return
    }
    const gallery = resourceItems.value
      .filter((item) => item.kind === 'image' && item.url)
      .map((item) => ({ url: item.url, id: item.id, createTime: item.createTime, label: item.variant }))
    openImagePreview(resource.url, gallery)
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

    const trace = createPerfTrace('chat-messages', {
      account: String(selectedAccount.value || '').trim(),
      selectedUsername: String(selectedContact.value?.username || '').trim(),
      username: String(username || '').trim(),
      reset: !!reset
    })

    trace.log('loadMessages:enter', {
      activeMessagesFor: String(activeMessagesFor.value || '').trim()
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
      params.source = DEFAULT_CHAT_SOURCE
      trace.log('loadMessages:request:start', {
        offset,
        existingCount: existing.length,
        renderTypeFilter: messageTypeFilter.value,
        source: DEFAULT_CHAT_SOURCE,
        realtime: !!realtimeEnabled.value
      })
      const response = await api.listChatMessages(params)
      trace.log('loadMessages:request:end', {
        source: response?.source || DEFAULT_CHAT_SOURCE,
        rawCount: Array.isArray(response?.messages) ? response.messages.length : 0,
        total: Number(response?.total || 0),
        hasMore: response?.hasMore
      })

      const raw = response?.messages || []
      trace.log('loadMessages:normalize:start', {
        rawCount: raw.length
      })
      const mapped = dedupeMessagesById(raw.map(normalizeMessage))
      trace.log('loadMessages:normalize:end', {
        mappedCount: mapped.length,
        renderTypeCounts: summarizeRenderTypes(mapped)
      })

      if (activeMessagesFor.value !== username) {
        trace.log('loadMessages:abort-stale', {
          activeMessagesFor: activeMessagesFor.value
        })
        return
      }

      trace.log('loadMessages:state-commit:start', {
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
      trace.log('loadMessages:state-commit:end', {
        storedCount: (allMessages.value[username] || []).length
      })

      messagesMeta.value = {
        ...messagesMeta.value,
        [username]: {
          total: Number(response?.total || 0),
          hasMore: response?.hasMore
        }
      }
      trace.log('loadMessages:meta-commit:end', {
        total: Number(response?.total || 0),
        hasMore: response?.hasMore
      })

      trace.log('loadMessages:nextTick:start')
      await nextTick()
      trace.log('loadMessages:nextTick:end', {
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
      trace.log('loadMessages:scroll:end', {
        hasContainer: !!nextContainer,
        scrollTop: nextContainer ? nextContainer.scrollTop : null,
        scrollHeight: nextContainer ? nextContainer.scrollHeight : null
      })
    } catch (error) {
      trace.log('loadMessages:error', {
        message: String(error?.message || ''),
        errorName: String(error?.name || '')
      })
      console.error('[chat-messages] loadMessages:error', {
        account: String(selectedAccount.value || '').trim(),
        username: String(username || '').trim(),
        reset: !!reset,
        error
      })
      messagesError.value = error?.message || '加载聊天记录失败'
    } finally {
      isLoadingMessages.value = false
      trace.log('loadMessages:exit', {
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
    bumpLocalMediaVersion()
    await loadMessages({ username: selectedContact.value.username, reset: true })
  }

  const refreshCurrentMessageMedia = async () => {
    if (!selectedContact.value?.username) return
    const trace = createPerfTrace('chat-messages', {
      account: String(selectedAccount.value || '').trim(),
      username: String(selectedContact.value?.username || '').trim(),
      action: 'refreshCurrentMessageMedia'
    })
    trace.log('refreshCurrentMessageMedia:start', {
      localMediaVersion: Number(localMediaVersion.value || 0)
    })
    bumpLocalMediaVersion()
    trace.log('refreshCurrentMessageMedia:version-bumped', {
      localMediaVersion: Number(localMediaVersion.value || 0)
    })
    renormalizeLoadedMessages(selectedContact.value.username)
    trace.log('refreshCurrentMessageMedia:renormalized', {
      renderedCount: (allMessages.value[selectedContact.value.username] || []).length
    })
    await nextTick()
    trace.log('refreshCurrentMessageMedia:end')
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
      source: DEFAULT_CHAT_SOURCE
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
    closeImagePreview()
    closeVideoPreview()
    resetResourceState()
    resourceSidebarOpen.value = false
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
      const response = await api.getChatContactProfile({
        account,
        source: DEFAULT_CHAT_SOURCE,
        username
      })
      const matched = response?.contact && typeof response.contact === 'object' ? response.contact : null
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

  const getMentionContactProfileCardId = (message, user) => {
    const messageId = String(message?.id ?? '').trim()
    const username = String(user?.username || '').trim()
    if (!messageId || !username) return ''
    return `mention:${messageId}:${username}`
  }

  const isMentionContactProfileCardForMessage = (message) => {
    const messageId = String(message?.id ?? '').trim()
    if (!messageId) return false
    return String(contactProfileCardMessageId.value || '').startsWith(`mention:${messageId}:`)
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

  const onMentionMouseEnter = async (message, user) => {
    const username = String(user?.username || '').trim()
    if (!username) return
    if (username === 'notify@all') return
    const cardId = getMentionContactProfileCardId(message, user)
    if (!cardId) return

    const displayName = String(user?.displayName || user?.nickname || user?.remark || username).trim()
    const avatar = String(user?.avatar || '').trim()
    if (!contactProfileData.value || String(contactProfileData.value?.username || '').trim() !== username) {
      contactProfileData.value = {
        username,
        displayName: displayName || username,
        avatar,
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
      if (!String(contactProfileData.value?.displayName || '').trim() && displayName) {
        contactProfileData.value.displayName = displayName
      }
      if (!String(contactProfileData.value?.avatar || '').trim() && avatar) {
        contactProfileData.value.avatar = avatar
      }
    }

    clearContactProfileHoverHideTimer()
    contactProfileCardMessageId.value = cardId
    contactProfileCardOpen.value = true
    await fetchContactProfile({ username, displayName, avatar })
  }

  const onMentionMouseLeave = () => {
    onMessageAvatarMouseLeave()
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
      resetResourceState()
      if (resourceSidebarOpen.value) {
        void loadResourceItems({ reset: true })
      }
    }
  )

  watch(
    () => selectedAccount.value,
    () => {
      clearContactProfileHoverHideTimer()
      closeContactProfileCard()
      contactProfileError.value = ''
      contactProfileData.value = null
      resetResourceState()
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
    previewImageItems,
    previewImageIndex,
    previewImageCount,
    previewImageCounterText,
    canSwitchPreviewImage,
    previewVideoUrl,
    previewVideoPosterUrl,
    previewVideoError,
    resourceSidebarOpen,
    resourceTimeGroup,
    resourceItems,
    groupedResourceItems,
    resourceGroupOptions,
    resourceGridStyle,
    resourceLoading,
    resourceError,
    resourceHasMore,
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
    showPrevPreviewImage,
    showNextPreviewImage,
    openVideoPreview,
    closeVideoPreview,
    onPreviewVideoError,
    openResourceSidebar,
    closeResourceSidebar,
    toggleResourceSidebar,
    loadResourceItems,
    onResourceSidebarScroll,
    openResourcePreview,
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
    refreshCurrentMessageMedia,
    refreshRealtimeIncremental,
    queueRealtimeRefresh,
    resetMessageState,
    fetchContactProfile,
    clearContactProfileHoverHideTimer,
    closeContactProfileCard,
    getMentionContactProfileCardId,
    isMentionContactProfileCardForMessage,
    onMessageAvatarMouseEnter,
    onMessageAvatarMouseLeave,
    onMentionMouseEnter,
    onMentionMouseLeave,
    onContactCardMouseEnter,
    formatFileSize
  }
}
