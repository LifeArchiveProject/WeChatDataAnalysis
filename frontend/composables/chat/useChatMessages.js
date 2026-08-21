import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { showErrorAlert } from '~/composables/useErrorNotice'
import {
  formatFileSize,
  formatTimeDivider,
  getVoiceDurationInSeconds,
  getVoiceWidth
} from '~/lib/chat/formatters'
import { createPerfTrace, isChatPerfLoggingEnabled, logPerfChannel } from '~/lib/chat/perf-logger'
import {
  buildImageGroupKey,
  deriveImageGroupMessages,
  findImageGroupKeyByMessageId
} from '~/lib/chat/image-groups'
import { createMessageNormalizer, dedupeMessagesById } from '~/lib/chat/message-normalizer'
import { PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT } from '~/lib/voice-transcript-invalidation'

const DEFAULT_CHAT_SOURCE = 'auto'
const IMAGE_GROUP_LAYOUT_DURATION_MS = 250
const IMAGE_GROUP_LAYOUT_EASING = 'cubic-bezier(0.2, 0, 0, 1)'
const NATIVE_VOICE_DISPATCH_TOKEN = Symbol('nativeVoiceDispatchToken')

const nativeVoiceErrorDetail = (error) => error?.data?.detail || error?.detail || {}

export const clearProjectVoiceTranscripts = (loadedConversations) => {
  if (!loadedConversations || typeof loadedConversations !== 'object') return
  for (const list of Object.values(loadedConversations)) {
    if (!Array.isArray(list)) continue
    for (const message of list) {
      const model = String(message?.voiceTranscriptModel || '').trim().toLowerCase()
      const status = String(message?.voiceTranscriptStatus || '').trim().toLowerCase()
      if (model === 'wechat-native') continue
      if (!model && status !== 'loading') continue
      message.voiceTranscript = ''
      message.voiceTranscriptStatus = 'idle'
      message.voiceTranscriptError = ''
      message.voiceTranscriptLanguage = ''
      message.voiceTranscriptModel = ''
    }
  }
}

export const mergeWechatNativeVoiceTranscript = (message, payload) => {
  const model = String(payload?.model ?? payload?.voiceTranscriptModel ?? '').trim().toLowerCase()
  const text = String(payload?.text ?? payload?.voiceTranscript ?? '').trim()
  if (model !== 'wechat-native' || !text) return message

  const language = String(payload?.language ?? payload?.voiceTranscriptLanguage ?? '').trim()
  if (
    String(message?.voiceTranscript || '').trim() === text
    && String(message?.voiceTranscriptStatus || '').trim() === 'success'
    && String(message?.voiceTranscriptModel || '').trim().toLowerCase() === 'wechat-native'
    && String(message?.voiceTranscriptLanguage || '').trim() === language
    && !String(message?.voiceTranscriptError || '').trim()
  ) return message

  return {
    ...message,
    voiceTranscript: text,
    voiceTranscriptStatus: 'success',
    voiceTranscriptError: '',
    voiceTranscriptLanguage: language,
    voiceTranscriptModel: 'wechat-native',
    voiceTranscriptNativeRequestId: ''
  }
}

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
  const messageTypeFilterScanPageSize = 640

  const allMessages = ref({})
  const messagesMeta = ref({})
  const isLoadingMessages = ref(false)
  const messagesError = ref('')
  const messageContainerRef = ref(null)
  const activeMessagesFor = ref('')
  const showJumpToBottom = ref(false)
  let lastRenderMessagesFingerprint = ''
  let messageLoadSeq = 0
  let messageLoadController = null
  let messageLoadTargetUsername = ''
  let realtimeRefreshController = null
  let realtimeRefreshTargetUsername = ''
  let nativeVoiceRevision = 0
  let projectTranscriptRevision = 0
  const nativeVoiceTranscriptPolls = new Map()

  const isAbortError = (error, controller = null) => {
    return !!(
      controller?.signal?.aborted
      || error?.name === 'AbortError'
      || error?.cause?.name === 'AbortError'
      || error?.message === 'This operation was aborted'
    )
  }

  const abortMessageLoad = () => {
    const controller = messageLoadController
    messageLoadController = null
    messageLoadTargetUsername = ''
    if (!controller || controller.signal.aborted) return
    try { controller.abort() } catch {}
  }

  const abortRealtimeRefresh = () => {
    const controller = realtimeRefreshController
    realtimeRefreshController = null
    realtimeRefreshTargetUsername = ''
    if (!controller || controller.signal.aborted) return
    try { controller.abort() } catch {}
  }

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
    logPerfChannel('chat-messages', phase, payload)
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
  const voiceTranscriptionStatus = ref(null)
  const voiceTranscriptionStatusLoading = ref(false)
  let voiceTranscriptionStatusPromise = null
  const voiceTranscriptionStatusKnown = computed(() => !!voiceTranscriptionStatus.value)
  const voiceTranscriptionAvailable = computed(() => voiceTranscriptionStatus.value?.available === true)
  const voiceTranscriptionUnavailableReason = computed(() => String(
    voiceTranscriptionStatus.value?.reason || '本地 Whisper 模型尚未准备好。'
  ).trim())

  const refreshVoiceTranscriptionStatus = async ({ force = false } = {}) => {
    if (!force && voiceTranscriptionStatus.value) return voiceTranscriptionStatus.value
    if (voiceTranscriptionStatusPromise) return await voiceTranscriptionStatusPromise
    voiceTranscriptionStatusLoading.value = true
    voiceTranscriptionStatusPromise = (async () => {
      try {
        voiceTranscriptionStatus.value = await api.getVoiceTranscriptionStatus()
      } catch (error) {
        voiceTranscriptionStatus.value = {
          available: false,
          reason: String(error?.message || '无法读取本地语音转文字状态').trim()
        }
      } finally {
        voiceTranscriptionStatusLoading.value = false
        voiceTranscriptionStatusPromise = null
      }
      return voiceTranscriptionStatus.value
    })()
    return await voiceTranscriptionStatusPromise
  }

  const nativeVoiceTranscriptionStatus = ref(null)
  const nativeVoiceTranscriptionStatusLoading = ref(false)
  let nativeVoiceTranscriptionStatusPromise = null
  let nativeVoiceTranscriptionStatusSequence = 0
  let nativeVoiceTranscriptionStatusUpdatedAt = 0
  const nativeVoiceTranscriptionStatusTtlMs = 5000
  const nativeVoiceTranscriptionStatusKnown = computed(() => !!nativeVoiceTranscriptionStatus.value)
  const nativeVoiceTranscriptionAvailable = computed(() => nativeVoiceTranscriptionStatus.value?.available === true)
  const nativeVoiceTranscriptionUnavailableReason = computed(() => {
    const reason = String(nativeVoiceTranscriptionStatus.value?.reason || '').trim()
    return ({
      runtime_trigger_e2e_not_validated: '当前微信版本的原生转写桥接尚未启用。',
      unsupported_platform: '微信原生语音转文字目前仅支持 Windows。',
      unsupported_architecture: '微信原生语音转文字需要 64 位 Windows。',
      weixin_main_ui_not_found: '请先登录并打开微信。',
      weixin_main_ui_ambiguous: '检测到多个微信主窗口，无法安全选择账号。',
      weixin_version_unsupported: '当前微信版本暂不支持微信原生语音转文字。请使用微信 4.1.12.26，并完全退出、重新启动微信后再试。',
      active_account_mismatch: '当前项目账号与已登录微信账号不一致。',
      active_account_unverified: '无法确认当前项目账号与已登录微信账号一致。',
      protected_build_unavailable: '当前受保护 DLL 或构建中的微信原生语音转文字功能不可用。',
      bridge_manager_unavailable: '微信原生语音转文字服务尚未就绪。',
      inspection_failed: '无法检查微信原生语音转文字状态。请重启本应用和微信后再试。',
      bridge_restart_required: '桥接状态已失效。请完全退出微信，重启本应用（开发模式下同时重启后端）后，再重新打开并登录微信。'
    })[reason] || reason || '微信原生语音转文字当前不可用。'
  })

  const refreshNativeVoiceTranscriptionStatus = async ({ force = false } = {}) => {
    const account = String(selectedAccount.value || '').trim()
    if (!account) {
      nativeVoiceTranscriptionStatus.value = null
      return null
    }
    if (
      !force
      && nativeVoiceTranscriptionStatus.value
      && (Date.now() - nativeVoiceTranscriptionStatusUpdatedAt) < nativeVoiceTranscriptionStatusTtlMs
    ) return nativeVoiceTranscriptionStatus.value
    if (nativeVoiceTranscriptionStatusPromise?.account === account) {
      return await nativeVoiceTranscriptionStatusPromise.promise
    }
    const sequence = ++nativeVoiceTranscriptionStatusSequence
    nativeVoiceTranscriptionStatusLoading.value = true
    const promise = (async () => {
      let result
      try {
        result = await api.getNativeVoiceTranscriptionStatus({ account })
      } catch (error) {
        result = {
          available: false,
          reason: String(error?.message || '无法读取微信原生语音转文字状态').trim()
        }
      } finally {
        if (sequence === nativeVoiceTranscriptionStatusSequence) {
          nativeVoiceTranscriptionStatusLoading.value = false
          nativeVoiceTranscriptionStatusPromise = null
        }
      }
      if (
        sequence === nativeVoiceTranscriptionStatusSequence
        && String(selectedAccount.value || '').trim() === account
      ) {
        nativeVoiceTranscriptionStatus.value = result
        nativeVoiceTranscriptionStatusUpdatedAt = Date.now()
      }
      return result
    })()
    nativeVoiceTranscriptionStatusPromise = { account, promise }
    return await promise
  }

  const highlightServerIdStr = ref('')
  const highlightMessageId = ref('')
  const expandedImageGroupKeys = ref(new Set())
  const imageGroupActiveItemIds = ref(new Map())
  const activeImageGroupTransitionKey = ref('')
  const imageGroupTransitioning = ref(false)
  let highlightTimer = null
  let activeImageGroupAnimations = []
  let activeImageGroupMotionCleanups = []
  let imageGroupTransitionSequence = 0

  const messageTypeFilter = ref('all')
  const localMediaVersion = ref(0)
  const largeImagePreferences = ref({})
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
    getLocalMediaVersion: () => localMediaVersion.value,
    shouldPreferLargeImage: (message) => shouldPreferLargeImageByPreference(message),
    getLargeImageVersion: (message) => getLargeImagePreferenceVersion(message)
  })

  const getLargeImagePreferenceStorageKey = () => {
    const account = String(selectedAccount.value || '').trim()
    const username = String(selectedContact.value?.username || '').trim()
    if (!account || !username) return ''
    return `wechatda:large_image_preferences:${account}:${username}`
  }

  const makeLargeImagePreferenceKeys = (message) => {
    const keys = []
    const serverId = String(message?.serverIdStr || message?.serverId || '').trim()
    const md5 = String(message?.imageMd5 || '').trim().toLowerCase()
    const fileId = String(message?.imageFileId || '').trim()
    const id = String(message?.id || '').trim()
    const localId = Number(message?.localId || 0)
    if (serverId) keys.push(`server:${serverId}`)
    if (md5) keys.push(`md5:${md5}`)
    if (fileId) keys.push(`file:${fileId}`)
    if (id) keys.push(`id:${id}`)
    if (localId) keys.push(`local:${localId}`)
    return keys
  }

  const loadLargeImagePreferences = () => {
    if (!process.client || typeof window === 'undefined') {
      largeImagePreferences.value = {}
      return {}
    }
    const key = getLargeImagePreferenceStorageKey()
    if (!key) {
      largeImagePreferences.value = {}
      return {}
    }
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) || '{}')
      largeImagePreferences.value = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    } catch {
      largeImagePreferences.value = {}
    }
    return largeImagePreferences.value
  }

  const saveLargeImagePreferences = () => {
    if (!process.client || typeof window === 'undefined') return
    const key = getLargeImagePreferenceStorageKey()
    if (!key) return
    try {
      window.localStorage.setItem(key, JSON.stringify(largeImagePreferences.value || {}))
    } catch {}
  }

  const getLargeImagePreferenceValue = (message) => {
    const prefs = largeImagePreferences.value || {}
    for (const key of makeLargeImagePreferenceKeys(message)) {
      const value = Number(prefs[key] || 0)
      if (value > 0) return value
    }
    return 0
  }

  const shouldPreferLargeImageByPreference = (message) => getLargeImagePreferenceValue(message) > 0
  const getLargeImagePreferenceVersion = (message) => getLargeImagePreferenceValue(message) || localMediaVersion.value

  const rememberLargeImagePreference = (message, triedAt = Date.now()) => {
    const keys = makeLargeImagePreferenceKeys(message)
    if (!keys.length) return
    const stamp = Number(triedAt || Date.now())
    const next = { ...(largeImagePreferences.value || {}) }
    for (const key of keys) next[key] = stamp
    largeImagePreferences.value = next
    saveLargeImagePreferences()
  }

  loadLargeImagePreferences()

  const bumpLocalMediaVersion = () => {
    localMediaVersion.value = (localMediaVersion.value + 1) % 1000000000
    return localMediaVersion.value
  }

  const renormalizeLoadedMessages = (username) => {
    const key = String(username || '').trim()
    if (!key) return
    const existing = allMessages.value[key]
    if (!Array.isArray(existing) || !existing.length) return

    loadLargeImagePreferences()
    const refreshed = hydrateQuoteImageUrls(dedupeMessagesById(existing.map((message) => {
      const normalized = normalizeMessage(message)
      return {
        ...message,
        ...normalized,
        _emojiDownloading: !!message?._emojiDownloading,
        _emojiDownloaded: typeof message?._emojiDownloaded === 'boolean' ? message._emojiDownloaded : normalized._emojiDownloaded,
        _imageLargeLoading: !!message?._imageLargeLoading,
        _imageLargeError: String(message?._imageLargeError || ''),
        _imageLargeLastTriedAt: Number(message?._imageLargeLastTriedAt || 0),
        _quoteImageError: false,
        _quoteThumbError: false
      }
    })))

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
    const expansionFingerprint = Array.from(expandedImageGroupKeys.value).sort().join('|')
    const fingerprint = `${String(selectedContact.value?.username || '').trim()}:${list.length}:${reverseSides ? '1' : '0'}:${expansionFingerprint}`
    const shouldLogRender = isDesktopRenderer()
      && isChatPerfLoggingEnabled()
      && fingerprint !== lastRenderMessagesFingerprint
    if (shouldLogRender) {
      logMessagePhase('renderMessages:start', {
        count: list.length,
        reverseSides
      })
    }
    const displayMessages = deriveImageGroupMessages(list, expandedImageGroupKeys.value)
    let previousTs = 0
    const rendered = displayMessages.map((message) => {
      const ts = Number(message.createTime || 0)
      const show = !previousTs || (ts && Math.abs(ts - previousTs) >= 300)
      if (ts) previousTs = ts
      const originalIsSent = !!message?.isSent
      const imageGroupItems = Array.isArray(message?.imageGroupItems)
        ? message.imageGroupItems.map((item) => {
            const itemOriginalIsSent = !!item?.isSent
            return {
              ...item,
              _originalIsSent: itemOriginalIsSent,
              isSent: reverseSides ? !itemOriginalIsSent : itemOriginalIsSent
            }
          })
        : null
      return {
        ...message,
        _originalIsSent: originalIsSent,
        isSent: reverseSides ? !originalIsSent : originalIsSent,
        ...(imageGroupItems ? { imageGroupItems } : {}),
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

  const toggleImageGroupExpanded = (groupKey, forceExpanded = null) => {
    const key = String(groupKey || '').trim()
    if (!key) return false
    const next = new Set(expandedImageGroupKeys.value)
    const shouldExpand = typeof forceExpanded === 'boolean' ? forceExpanded : !next.has(key)
    if (shouldExpand) next.add(key)
    else next.delete(key)
    expandedImageGroupKeys.value = next
    return shouldExpand
  }

  const getImageGroupActiveItemId = (groupKey) => (
    imageGroupActiveItemIds.value.get(String(groupKey || '').trim()) || ''
  )

  const setImageGroupActiveItemId = (groupKey, messageId) => {
    const key = String(groupKey || '').trim()
    const id = String(messageId || '').trim()
    if (!key || !id || imageGroupActiveItemIds.value.get(key) === id) return false
    const next = new Map(imageGroupActiveItemIds.value)
    next.set(key, id)
    imageGroupActiveItemIds.value = next
    return true
  }

  const captureImageGroupActiveItem = (groupKey) => {
    const container = messageContainerRef.value
    const key = String(groupKey || '').trim()
    if (!container || !key) return ''
    const stack = Array.from(
      container.querySelectorAll?.('[data-testid="image-group-stack"][data-group-key]') || []
    ).find((element) => String(element?.dataset?.groupKey || '') === key)
    const activeIndex = Number.parseInt(String(stack?.dataset?.activeIndex || ''), 10)
    const activeCard = Number.isSafeInteger(activeIndex)
      ? Array.from(stack?.querySelectorAll?.('[data-card-index]') || []).find(
          (element) => Number.parseInt(String(element?.dataset?.cardIndex || ''), 10) === activeIndex
        )
      : null
    const messageId = String(activeCard?.dataset?.messageId || '').trim()
    if (messageId) setImageGroupActiveItemId(key, messageId)
    return messageId
  }

  const findMessageElementById = (container, messageId) => {
    const target = String(messageId || '').trim()
    if (!container || !target) return null
    return Array.from(container.querySelectorAll?.('[data-msg-id]') || []).find(
      (element) => String(element?.dataset?.msgId || '').trim() === target
    ) || null
  }

  const captureImageGroupScrollAnchor = (groupKey) => {
    const container = messageContainerRef.value
    if (!container) return null
    const first = (messages.value || []).find((message) => buildImageGroupKey(message) === groupKey)
    const messageId = String(first?.id || '').trim()
    const element = findMessageElementById(container, messageId)
    if (!element) return null
    return {
      container,
      messageId,
      top: element.getBoundingClientRect().top
    }
  }

  const restoreImageGroupScrollAnchor = (anchor) => {
    if (!anchor?.container?.isConnected) return
    const element = findMessageElementById(anchor.container, anchor.messageId)
    if (!element) return
    const delta = element.getBoundingClientRect().top - Number(anchor.top || 0)
    if (Number.isFinite(delta) && Math.abs(delta) >= 0.5) {
      anchor.container.scrollTop += delta
    }
    updateJumpToBottomState()
  }

  const readImageGroupElementPose = (element) => {
    if (!element?.isConnected || typeof window === 'undefined') return null
    const rect = element.getBoundingClientRect()
    const style = window.getComputedStyle(element)
    let scaleX = 1
    let scaleY = 1
    let rotation = 0
    if (style.transform && style.transform !== 'none' && typeof DOMMatrixReadOnly === 'function') {
      try {
        const matrix = new DOMMatrixReadOnly(style.transform)
        scaleX = Math.max(0.001, Math.hypot(matrix.a, matrix.b))
        scaleY = Math.max(0.001, Math.hypot(matrix.c, matrix.d))
        rotation = Math.atan2(matrix.b, matrix.a) * (180 / Math.PI)
      } catch {}
    }
    const layoutWidth = Math.max(1, Number(element.offsetWidth || rect.width || 1))
    const layoutHeight = Math.max(1, Number(element.offsetHeight || rect.height || 1))
    return {
      centerX: rect.left + (rect.width / 2),
      centerY: rect.top + (rect.height / 2),
      width: layoutWidth * scaleX,
      height: layoutHeight * scaleY,
      rotation,
      opacity: Math.max(0, Math.min(1, Number.parseFloat(style.opacity) || 0)),
      zIndex: Number.parseInt(style.zIndex, 10) || 0
    }
  }

  const captureImageGroupLayout = (groupKey) => {
    const container = messageContainerRef.value
    const key = String(groupKey || '').trim()
    const cards = new Map()
    if (!container || !key) return { cards, control: null }

    for (const element of container.querySelectorAll?.('[data-image-group-key][data-image-group-item-index]') || []) {
      if (String(element?.dataset?.imageGroupKey || '') !== key) continue
      const index = Number.parseInt(String(element?.dataset?.imageGroupItemIndex || ''), 10)
      const pose = readImageGroupElementPose(element)
      if (!Number.isSafeInteger(index) || index < 0 || !pose) continue
      cards.set(index, { element, pose })
    }

    const controlElement = Array.from(
      container.querySelectorAll?.('[data-image-group-control-key]') || []
    ).find((element) => String(element?.dataset?.imageGroupControlKey || '') === key)
    const controlPose = readImageGroupElementPose(controlElement)
    return {
      cards,
      control: controlElement && controlPose ? { element: controlElement, pose: controlPose } : null
    }
  }

  const readImageGroupMotionTarget = (element) => {
    if (!element?.isConnected || typeof window === 'undefined') return null
    const previousTransition = element.style.transition
    const previousTransform = element.style.transform
    const previousTransformOrigin = element.style.transformOrigin
    const previousWillChange = element.style.willChange
    const previousPosition = element.style.position
    const previousZIndex = element.style.zIndex
    const finalStyle = window.getComputedStyle(element)
    const finalTransform = previousTransform || (
      finalStyle.transform && finalStyle.transform !== 'none' ? finalStyle.transform : 'none'
    )
    const finalOpacity = Math.max(0, Math.min(1, Number.parseFloat(finalStyle.opacity) || 0))

    element.style.transition = 'none'
    element.style.transform = 'none'
    const baseRect = element.getBoundingClientRect()
    element.style.transform = previousTransform
    element.style.transition = previousTransition

    return {
      baseRect,
      finalTransform,
      finalOpacity,
      restore: () => {
        element.style.transition = previousTransition
        element.style.transform = previousTransform
        element.style.transformOrigin = previousTransformOrigin
        element.style.willChange = previousWillChange
        element.style.position = previousPosition
        element.style.zIndex = previousZIndex
      }
    }
  }

  const buildImageGroupStartTransform = (sourcePose, baseRect) => {
    const baseWidth = Math.max(1, Number(baseRect?.width || 1))
    const baseHeight = Math.max(1, Number(baseRect?.height || 1))
    const baseCenterX = Number(baseRect?.left || 0) + (baseWidth / 2)
    const baseCenterY = Number(baseRect?.top || 0) + (baseHeight / 2)
    const translateX = Number(sourcePose?.centerX || 0) - baseCenterX
    const translateY = Number(sourcePose?.centerY || 0) - baseCenterY
    const scaleX = Math.max(0.001, Number(sourcePose?.width || 1) / baseWidth)
    const scaleY = Math.max(0.001, Number(sourcePose?.height || 1) / baseHeight)
    const rotation = Number(sourcePose?.rotation || 0)
    return `translate3d(${translateX}px, ${translateY}px, 0) rotate(${rotation}deg) scale(${scaleX}, ${scaleY})`
  }

  const registerImageGroupMotionCleanup = (cleanup) => {
    if (typeof cleanup === 'function') activeImageGroupMotionCleanups.push(cleanup)
  }

  const animateImageGroupMotionElement = (element, sourcePose, { fadeLabel = false } = {}) => {
    const target = readImageGroupMotionTarget(element)
    if (!target || typeof element.animate !== 'function') return null

    element.style.transformOrigin = '50% 50%'
    element.style.willChange = 'transform, opacity'
    if (!element.closest?.('[data-testid="image-group-stack"]')) {
      element.style.position = 'relative'
      element.style.zIndex = String(100 + Number(sourcePose?.zIndex || 0))
    }
    registerImageGroupMotionCleanup(target.restore)

    return element.animate([
      {
        transform: buildImageGroupStartTransform(sourcePose, target.baseRect),
        opacity: fadeLabel ? 0.25 : Number(sourcePose?.opacity ?? 1)
      },
      {
        transform: target.finalTransform,
        opacity: target.finalOpacity
      }
    ], {
      duration: IMAGE_GROUP_LAYOUT_DURATION_MS,
      easing: IMAGE_GROUP_LAYOUT_EASING,
      fill: 'both'
    })
  }

  const clearActiveImageGroupMotion = () => {
    const animations = activeImageGroupAnimations
    const cleanups = activeImageGroupMotionCleanups
    activeImageGroupAnimations = []
    activeImageGroupMotionCleanups = []
    for (const animation of animations) {
      try { animation.cancel() } catch {}
    }
    for (const cleanup of cleanups.reverse()) {
      try { cleanup() } catch {}
    }
  }

  const animateImageGroupLayout = async (sourceLayout, groupKey) => {
    const targetLayout = captureImageGroupLayout(groupKey)
    const animations = []

    for (const [index, source] of sourceLayout?.cards || []) {
      const target = targetLayout.cards.get(index)
      if (!target) continue
      const animation = animateImageGroupMotionElement(target.element, source.pose)
      if (animation) animations.push(animation)
    }

    if (sourceLayout?.control && targetLayout.control) {
      const animation = animateImageGroupMotionElement(
        targetLayout.control.element,
        sourceLayout.control.pose,
        { fadeLabel: true }
      )
      if (animation) animations.push(animation)
    }

    activeImageGroupAnimations = animations
    await Promise.allSettled(animations.map((animation) => animation.finished))
  }

  const clearImageGroupTransitionState = (sequence = null) => {
    if (sequence != null && sequence !== imageGroupTransitionSequence) return
    clearActiveImageGroupMotion()
    activeImageGroupTransitionKey.value = ''
    imageGroupTransitioning.value = false
    if (typeof document !== 'undefined') {
      delete document.documentElement.dataset.imageGroupTransition
      delete document.documentElement.dataset.imageGroupTransitionKey
    }
  }

  const cancelImageGroupTransition = () => {
    imageGroupTransitionSequence += 1
    clearImageGroupTransitionState()
  }

  const shouldReduceImageGroupMotion = () => (
    typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )

  const transitionImageGroupExpanded = async (groupKey, forceExpanded = null) => {
    const key = String(groupKey || '').trim()
    if (!key) return false

    const currentlyExpanded = expandedImageGroupKeys.value.has(key)
    const shouldExpand = typeof forceExpanded === 'boolean' ? forceExpanded : !currentlyExpanded
    if (shouldExpand === currentlyExpanded) return currentlyExpanded
    if (imageGroupTransitioning.value) return currentlyExpanded

    const canAnimate = (
      typeof document !== 'undefined'
      && document.visibilityState === 'visible'
      && typeof Element !== 'undefined'
      && typeof Element.prototype?.animate === 'function'
      && !shouldReduceImageGroupMotion()
    )
    if (!canAnimate) {
      if (shouldExpand) captureImageGroupActiveItem(key)
      return toggleImageGroupExpanded(key, shouldExpand)
    }

    const sequence = ++imageGroupTransitionSequence
    const direction = shouldExpand ? 'expand' : 'collapse'
    let committed = false

    imageGroupTransitioning.value = true
    activeImageGroupTransitionKey.value = key
    document.documentElement.dataset.imageGroupTransition = direction
    document.documentElement.dataset.imageGroupTransitionKey = key
    await nextTick()
    if (sequence !== imageGroupTransitionSequence) return currentlyExpanded
    if (shouldExpand) captureImageGroupActiveItem(key)
    const anchor = captureImageGroupScrollAnchor(key)
    const sourceLayout = captureImageGroupLayout(key)

    try {
      committed = true
      toggleImageGroupExpanded(key, shouldExpand)
      await nextTick()
      if (sequence !== imageGroupTransitionSequence) return shouldExpand
      restoreImageGroupScrollAnchor(anchor)
      await animateImageGroupLayout(sourceLayout, key)
    } catch {
      if (!committed && sequence === imageGroupTransitionSequence) {
        committed = true
        toggleImageGroupExpanded(key, shouldExpand)
        await nextTick()
        restoreImageGroupScrollAnchor(anchor)
      }
    } finally {
      if (!committed && sequence === imageGroupTransitionSequence) {
        toggleImageGroupExpanded(key, shouldExpand)
        await nextTick()
        restoreImageGroupScrollAnchor(anchor)
      }
      clearImageGroupTransitionState(sequence)
      await nextTick()
    }

    return shouldExpand
  }

  const clearExpandedImageGroups = () => {
    cancelImageGroupTransition()
    if (expandedImageGroupKeys.value.size) expandedImageGroupKeys.value = new Set()
    if (imageGroupActiveItemIds.value.size) imageGroupActiveItemIds.value = new Map()
  }

  const scrollToMessageId = async (id) => {
    const target = String(id || '').trim()
    if (!target) return false
    const groupKey = findImageGroupKeyByMessageId(messages.value, target)
    if (groupKey && !expandedImageGroupKeys.value.has(groupKey)) {
      toggleImageGroupExpanded(groupKey, true)
    }
    await nextTick()
    const container = messageContainerRef.value
    let element = container?.querySelector?.(`[data-msg-id="${CSS.escape(target)}"]`)
    if (!element) {
      if (groupKey) {
        toggleImageGroupExpanded(groupKey, true)
        await nextTick()
        element = container?.querySelector?.(`[data-msg-id="${CSS.escape(target)}"]`)
      }
    }
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
      if (message?.renderType === 'emoji') {
        push(message.emojiUrl, { ...message, id: `${message.id || ''}:emoji`, label: message.content || '表情' })
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
      loadLargeImagePreferences()
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

  const invalidateProjectVoiceTranscripts = () => {
    projectTranscriptRevision += 1
    clearProjectVoiceTranscripts(allMessages.value)
  }

  const stopNativeVoiceTranscriptPolling = () => {
    nativeVoiceRevision += 1
    for (const entry of nativeVoiceTranscriptPolls.values()) {
      try { entry.controller?.abort?.() } catch {}
    }
    nativeVoiceTranscriptPolls.clear()
    for (const list of Object.values(allMessages.value || {})) {
      if (!Array.isArray(list)) continue
      for (const message of list) {
        if (
          String(message?.voiceTranscriptStatus || '').trim().toLowerCase() === 'loading'
          && (
            String(message?.voiceTranscriptNativeRequestId || '').trim()
            || message?.[NATIVE_VOICE_DISPATCH_TOKEN]
          )
        ) {
          message.voiceTranscriptStatus = 'idle'
          message.voiceTranscriptError = ''
          delete message[NATIVE_VOICE_DISPATCH_TOKEN]
        }
      }
    }
  }

  const waitForNativeVoiceTranscriptPoll = (delayMs, signal) => new Promise((resolve) => {
    if (signal?.aborted || delayMs <= 0) {
      resolve()
      return
    }
    const finish = () => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }
    const timer = setTimeout(finish, delayMs)
    const onAbort = () => {
      clearTimeout(timer)
      finish()
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })

  // 按 requestId + 精确消息 identity 读取 bridge 回调缓存；packed_info_data 仅作为后端兼容回退。
  const pollNativeVoiceTranscript = async (
    message,
    { requestId = '', maxAttempts = 85, intervalMs = 1200 } = {}
  ) => {
    const accountAtStart = String(selectedAccount.value || '').trim()
    const usernameAtStart = String(selectedContact.value?.username || '').trim()
    const serverId = String(message?.serverIdStr || message?.serverId || '').trim()
    const localId = String(message?.localIdStr || message?.localId || '').trim()
    const nativeRequestId = String(requestId || '').trim()
    const messageId = String(message?.id || '').trim()
    if (
      !accountAtStart
      || !usernameAtStart
      || !serverId
      || serverId === '0'
      || typeof api?.getNativeVoiceTranscript !== 'function'
    ) return { status: 'pending', serverId, text: '', language: '', model: '' }

    const pollKey = `${accountAtStart}:${usernameAtStart}:${serverId}:${localId}:${nativeRequestId}`
    const active = nativeVoiceTranscriptPolls.get(pollKey)
    if (active?.promise) return await active.promise

    const attempts = Math.max(1, Math.min(120, Math.trunc(Number(maxAttempts) || 1)))
    const delayMs = Math.max(0, Math.min(10000, Math.trunc(Number(intervalMs) || 0)))
    const controller = typeof AbortController === 'function' ? new AbortController() : null
    const entry = { controller, promise: null }
    entry.promise = (async () => {
      let result = { status: 'pending', serverId, text: '', language: '', model: '' }
      for (let attempt = 0; attempt < attempts; attempt += 1) {
        if (
          controller?.signal?.aborted
          || String(selectedAccount.value || '').trim() !== accountAtStart
          || String(selectedContact.value?.username || '').trim() !== usernameAtStart
        ) return { ...result, status: 'cancelled' }

        try {
          result = await api.getNativeVoiceTranscript({
            account: accountAtStart,
            server_id: serverId,
            username: usernameAtStart,
            ...(localId && localId !== '0' ? { local_id: localId } : {}),
            ...(nativeRequestId ? { request_id: nativeRequestId } : {}),
            ...(controller ? { signal: controller.signal } : {})
          })
        } catch (error) {
          if (isAbortError(error, controller)) return { ...result, status: 'cancelled' }
          throw error
        }

        const list = allMessages.value[usernameAtStart]
        const index = Array.isArray(list)
          ? list.findIndex((item) => (
              (messageId && String(item?.id || '') === messageId)
              || String(item?.serverIdStr || item?.serverId || '').trim() === serverId
            ))
          : -1
        if (index < 0) return { ...result, status: 'stale' }

        const resultStatus = String(result?.status || '').trim().toLowerCase()
        if (['error', 'expired', 'released'].includes(resultStatus)) {
          const resultError = new Error(String(
            result?.message || result?.error?.message || '微信原生语音转文字未能返回结果。'
          ).trim())
          resultError.code = String(result?.code || result?.error?.code || `native_transcript_${resultStatus}`).trim()
          throw resultError
        }

        const updated = mergeWechatNativeVoiceTranscript(list[index], result)
        if (updated !== list[index]) {
          const next = list.slice()
          next[index] = updated
          allMessages.value = { ...allMessages.value, [usernameAtStart]: next }
          return { ...result, status: 'success', model: 'wechat-native' }
        }
        if (resultStatus === 'success') return result
        if (attempt + 1 < attempts) {
          await waitForNativeVoiceTranscriptPoll(delayMs, controller?.signal)
        }
      }
      return result
    })().finally(() => {
      if (nativeVoiceTranscriptPolls.get(pollKey) === entry) nativeVoiceTranscriptPolls.delete(pollKey)
    })
    nativeVoiceTranscriptPolls.set(pollKey, entry)
    return await entry.promise
  }

  // 批量读取当前会话语音消息的转写缓存并合并进消息列表（仅恢复展示，不触发识别）。
  // serverIdStr 为精确字符串，禁止转 Number（19 位 svr_id 超出 JS Number 安全范围）。
  const restoreVoiceTranscripts = async (username) => {
    const nativeTranscriptRevision = nativeVoiceRevision
    const transcriptRevision = projectTranscriptRevision
    const accountAtStart = String(selectedAccount.value || '').trim()
    const key = String(username || '').trim()
    if (!key || privacyMode?.value) return
    void refreshVoiceTranscriptionStatus()
    void refreshNativeVoiceTranscriptionStatus()
    const list = allMessages.value[key]
    if (!Array.isArray(list) || !list.length) return

    const pending = list.filter((m) => {
      if (String(m?.renderType || '') !== 'voice') return false
      if (!String(m?.serverIdStr || '').trim()) return false
      const status = String(m?.voiceTranscriptStatus || 'idle')
      return !status || status === 'idle'
    })
    if (!pending.length) return

    if (typeof api?.lookupNativeVoiceTranscriptionCache === 'function') {
      try {
        const nativeResponse = await api.lookupNativeVoiceTranscriptionCache({
          account: accountAtStart,
          username: key,
          items: pending.map((message) => ({
            server_id: String(message?.serverIdStr || message?.serverId || '').trim(),
            local_id: String(message?.localIdStr || message?.localId || '').trim()
          })).filter((item) => item.server_id && item.local_id && item.local_id !== '0')
        })
        if (
          nativeTranscriptRevision !== nativeVoiceRevision
          || String(selectedAccount.value || '').trim() !== accountAtStart
        ) return
        const nativeItems = Array.isArray(nativeResponse?.items) ? nativeResponse.items : []
        if (nativeItems.length) {
          const hits = new Map(nativeItems.map((item) => [
            `${String(item?.serverId || '').trim()}:${String(item?.localId || '').trim()}`,
            item
          ]))
          const current = allMessages.value[key]
          if (!Array.isArray(current) || !current.length) return
          let changed = false
          const resumedPolls = []
          const next = current.map((message) => {
            const identity = `${String(message?.serverIdStr || message?.serverId || '').trim()}:${String(message?.localIdStr || message?.localId || '').trim()}`
            const hit = hits.get(identity)
            const hitStatus = String(hit?.status || '').trim().toLowerCase()
            let updated = mergeWechatNativeVoiceTranscript(message, hit)
            if (updated === message && hitStatus === 'pending') {
              const requestId = String(hit?.requestId || '').trim()
              if (requestId) {
                updated = {
                  ...message,
                  voiceTranscriptStatus: 'loading',
                  voiceTranscriptError: '',
                  voiceTranscriptNativeRequestId: requestId
                }
                resumedPolls.push({
                  message: updated,
                  requestId,
                  intervalMs: Math.max(1200, Number(hit?.pollAfterMs) || 0)
                })
              }
            } else if (updated === message && hitStatus === 'error') {
              updated = {
                ...message,
                voiceTranscriptStatus: 'error',
                voiceTranscriptError: String(hit?.message || '微信原生语音转文字未能返回结果。').trim(),
                voiceTranscriptNativeRequestId: String(hit?.requestId || '').trim()
              }
            }
            if (updated !== message) changed = true
            return updated
          })
          if (changed) allMessages.value = { ...allMessages.value, [key]: next }
          for (const resumed of resumedPolls) {
            void pollNativeVoiceTranscript(resumed.message, {
              requestId: resumed.requestId,
              intervalMs: resumed.intervalMs
            }).then(async (result) => {
              const status = String(result?.status || '').trim().toLowerCase()
              if (['success', 'cancelled', 'stale'].includes(status)) return
              const pendingError = new Error('微信原生语音转文字尚未返回结果，请稍后重试。')
              pendingError.code = 'native_transcript_pending'
              throw pendingError
            }).catch(async (error) => {
              if (
                nativeTranscriptRevision !== nativeVoiceRevision
                || String(selectedAccount.value || '').trim() !== accountAtStart
                || String(selectedContact.value?.username || '').trim() !== key
              ) return
              await refreshNativeVoiceTranscriptionStatus({ force: true })
              if (
                nativeTranscriptRevision !== nativeVoiceRevision
                || String(selectedAccount.value || '').trim() !== accountAtStart
                || String(selectedContact.value?.username || '').trim() !== key
              ) return
              const messages = allMessages.value[key]
              const index = Array.isArray(messages)
                ? messages.findIndex((message) => (
                    String(message?.id || '') === String(resumed.message?.id || '')
                    || String(message?.serverIdStr || message?.serverId || '').trim()
                      === String(resumed.message?.serverIdStr || resumed.message?.serverId || '').trim()
                  ))
                : -1
              if (index < 0) return
              if (
                String(messages[index]?.voiceTranscriptNativeRequestId || '').trim()
                !== resumed.requestId
              ) return
              const detail = nativeVoiceErrorDetail(error)
              const updated = {
                ...messages[index],
                voiceTranscriptStatus: 'error',
                voiceTranscriptError: String(
                  detail?.message || error?.message || '微信原生语音转文字未能返回结果。'
                ).trim(),
                voiceTranscriptNativeRequestId: ''
              }
              const replacement = messages.slice()
              replacement[index] = updated
              allMessages.value = { ...allMessages.value, [key]: replacement }
            })
          }
        }
      } catch {}
    }

    if (typeof api?.lookupChatVoiceTranscriptionCache !== 'function') return
    const projectPending = (allMessages.value[key] || []).filter((message) => {
      if (String(message?.renderType || '') !== 'voice') return false
      if (!String(message?.serverIdStr || '').trim()) return false
      const status = String(message?.voiceTranscriptStatus || 'idle')
      return !status || status === 'idle'
    })
    if (!projectPending.length) return

    try {
      const resp = await api.lookupChatVoiceTranscriptionCache({
        account: accountAtStart,
        server_ids: projectPending.map((m) => String(m.serverIdStr).trim())
      })
      if (
        transcriptRevision !== projectTranscriptRevision
        || String(selectedAccount.value || '').trim() !== accountAtStart
      ) return
      const items = resp?.items
      if (!items || typeof items !== 'object') return

      const current = allMessages.value[key]
      if (!Array.isArray(current) || !current.length) return
      for (const m of current) {
        const sid = String(m?.serverIdStr || '').trim()
        if (!sid) continue
        const status = String(m?.voiceTranscriptStatus || 'idle')
        if (status && status !== 'idle') continue
        const hit = items[sid]
        if (!hit) continue
        m.voiceTranscript = String(hit.text || '').trim()
        m.voiceTranscriptLanguage = String(hit.language || '').trim()
        m.voiceTranscriptModel = String(hit.model || '').trim()
        m.voiceTranscriptStatus = 'success'
      }
    } catch {}
  }

  const transcribeVoice = async (message) => {
    const transcriptRevision = nativeVoiceRevision
    const accountAtStart = String(selectedAccount.value || '').trim()
    const usernameAtStart = String(selectedContact.value?.username || '').trim()
    // 语音消息的 svr_id 是 19 位大整数，超出 JS Number 安全范围（2^53），
    // 必须使用精确字符串 serverIdStr，否则后端会查不到语音数据。
    const serverIdStr = String(message?.serverIdStr ?? '').trim()
    const serverId = serverIdStr || String(message?.serverId ?? '').trim()
    const localIdStr = String(message?.localIdStr ?? '').trim()
    const localId = localIdStr || String(message?.localId ?? '').trim()
    const usableServerId = serverId && serverId !== '0' ? serverId : ''
    const usableLocalId = localId && localId !== '0' ? localId : ''
    if (
      !message
      || !accountAtStart
      || !usernameAtStart
      || (!usableServerId && !usableLocalId)
      || message.voiceTranscriptStatus === 'loading'
    ) return

    // 模板渲染的是 renderMessages 的浅拷贝（非响应式），直接改拷贝不会驱动 UI 更新，
    // 且 computed 重算时拷贝会被替换导致状态丢失。必须修改 allMessages 中的原对象。
    const key = usernameAtStart
    const list = key ? allMessages.value[key] : null
    const target =
      (Array.isArray(list) ? list.find((item) => item?.id === message.id) : null) || message

    const nativeDispatchToken = Symbol('nativeVoiceDispatch')
    Object.defineProperty(target, NATIVE_VOICE_DISPATCH_TOKEN, {
      configurable: true,
      enumerable: false,
      value: nativeDispatchToken,
      writable: true
    })
    target.voiceTranscriptStatus = 'loading'
    target.voiceTranscriptError = ''
    target.voiceTranscriptNativeRequestId = ''

    const requestIsCurrent = () => !(
      target[NATIVE_VOICE_DISPATCH_TOKEN] !== nativeDispatchToken
      || transcriptRevision !== nativeVoiceRevision
      || String(selectedAccount.value || '').trim() !== accountAtStart
      || String(selectedContact.value?.username || '').trim() !== usernameAtStart
    )

    const setVoiceError = (error, fallback = '语音识别失败') => {
      if (!requestIsCurrent()) return
      const detail = nativeVoiceErrorDetail(error)
      target.voiceTranscriptError = String(detail?.message || error?.message || fallback).trim()
      target.voiceTranscriptStatus = 'error'
      target.voiceTranscriptNativeRequestId = ''
    }

    if (typeof api?.triggerNativeVoiceTranscription !== 'function') {
      setVoiceError(null, '当前版本未提供微信原生语音转文字接口。')
      delete target[NATIVE_VOICE_DISPATCH_TOKEN]
      return
    }

    try {
      const nativeResult = await api.triggerNativeVoiceTranscription({
        account: accountAtStart,
        username: usernameAtStart,
        ...(usableServerId ? { server_id: usableServerId } : {}),
        ...(usableLocalId ? { local_id: usableLocalId } : {})
      })
      if (!requestIsCurrent()) return

      const resolvedServerId = String(nativeResult?.serverId ?? '').trim()
      const resolvedLocalId = String(nativeResult?.localId ?? '').trim()
      if (resolvedServerId && resolvedServerId !== '0') target.serverIdStr = resolvedServerId
      if (resolvedLocalId && resolvedLocalId !== '0') target.localIdStr = resolvedLocalId

      const nativeStatus = String(nativeResult?.status || '').trim().toLowerCase()
      if (nativeStatus === 'success') {
        const updated = mergeWechatNativeVoiceTranscript(target, {
          ...nativeResult,
          model: 'wechat-native'
        })
        if (updated === target) {
          const invalidResponse = new Error('微信原生语音转写返回了无效结果。')
          invalidResponse.code = 'native_transport_invalid_response'
          throw invalidResponse
        }
        Object.assign(target, updated)
        target.voiceTranscriptNativeRequestId = ''
        return
      }

      if (nativeStatus === 'accepted' || nativeStatus === 'pending') {
        const nativeRequestId = String(nativeResult?.requestId || '').trim()
        if (!nativeRequestId) {
          const invalidResponse = new Error('微信原生语音转写未返回可轮询的 requestId。')
          invalidResponse.code = 'native_transport_invalid_response'
          throw invalidResponse
        }
        target.voiceTranscriptNativeRequestId = nativeRequestId
        const pollResult = await pollNativeVoiceTranscript(target, {
          requestId: nativeRequestId,
          intervalMs: Math.max(1200, Number(nativeResult?.pollAfterMs) || 0)
        })
        if (!requestIsCurrent()) return
        if (String(pollResult?.status || '').trim().toLowerCase() === 'success') {
          const updated = mergeWechatNativeVoiceTranscript(target, {
            ...pollResult,
            model: 'wechat-native'
          })
          if (updated === target) {
            const invalidResponse = new Error('微信原生语音转写轮询返回了无效结果。')
            invalidResponse.code = 'native_transport_invalid_response'
            setVoiceError(invalidResponse)
            return
          }
          Object.assign(target, updated)
          target.voiceTranscriptNativeRequestId = ''
          return
        }
        if (['cancelled', 'stale'].includes(String(pollResult?.status || '').trim().toLowerCase())) return
        const pendingError = new Error('微信原生语音转写尚未返回结果，请稍后重试。')
        pendingError.code = 'native_transcript_pending'
        await refreshNativeVoiceTranscriptionStatus({ force: true })
        if (!requestIsCurrent()) return
        setVoiceError(pendingError)
        return
      }

      const invalidResponse = new Error('微信原生语音转写返回了未知状态。')
      invalidResponse.code = 'native_transport_invalid_response'
      throw invalidResponse
    } catch (error) {
      if (!requestIsCurrent()) return
      await refreshNativeVoiceTranscriptionStatus({ force: true })
      if (!requestIsCurrent()) return
      setVoiceError(error, '微信原生语音转写触发失败')
    } finally {
      if (target[NATIVE_VOICE_DISPATCH_TOKEN] === nativeDispatchToken) {
        delete target[NATIVE_VOICE_DISPATCH_TOKEN]
        if (String(target.voiceTranscriptStatus || '').trim().toLowerCase() === 'loading') {
          target.voiceTranscriptStatus = 'idle'
          target.voiceTranscriptError = ''
        }
      }
    }
  }

  // 本地 Whisper 是用户显式选择的备用路径；原生转写失败时不要静默切换来源。
  const transcribeVoiceLocally = async (message, { force = false } = {}) => {
    const transcriptRevision = projectTranscriptRevision
    const accountAtStart = String(selectedAccount.value || '').trim()
    const usernameAtStart = String(selectedContact.value?.username || '').trim()
    // 与微信原生路径一样，svr_id 必须保留精确字符串，不能经过 Number。
    const serverIdStr = String(message?.serverIdStr ?? '').trim()
    const serverId = serverIdStr || String(message?.serverId ?? '').trim()
    const usableServerId = serverId && serverId !== '0' ? serverId : ''
    if (
      !message
      || !accountAtStart
      || !usernameAtStart
      || !usableServerId
      || message.voiceTranscriptStatus === 'loading'
    ) return

    const key = usernameAtStart
    const list = key ? allMessages.value[key] : null
    const target =
      (Array.isArray(list) ? list.find((item) => item?.id === message.id) : null) || message
    const localDispatchToken = Symbol('localVoiceDispatch')
    Object.defineProperty(target, NATIVE_VOICE_DISPATCH_TOKEN, {
      configurable: true,
      enumerable: false,
      value: localDispatchToken,
      writable: true
    })
    target.voiceTranscriptStatus = 'loading'
    target.voiceTranscriptError = ''
    target.voiceTranscriptNativeRequestId = ''

    const requestIsCurrent = () => !(
      target[NATIVE_VOICE_DISPATCH_TOKEN] !== localDispatchToken
      || transcriptRevision !== projectTranscriptRevision
      || String(selectedAccount.value || '').trim() !== accountAtStart
      || String(selectedContact.value?.username || '').trim() !== usernameAtStart
    )

    const setVoiceError = (error, fallback = '本地语音转文字失败') => {
      if (!requestIsCurrent()) return
      const detail = nativeVoiceErrorDetail(error)
      target.voiceTranscriptError = String(detail?.message || error?.message || fallback).trim()
      target.voiceTranscriptStatus = 'error'
      target.voiceTranscriptNativeRequestId = ''
    }

    try {
      if (typeof api?.transcribeChatVoice !== 'function') {
        setVoiceError(null, '当前版本未提供本地语音转文字接口。')
        return
      }
      const capability = await refreshVoiceTranscriptionStatus({ force: true })
      if (!requestIsCurrent()) return
      if (!capability?.available) {
        setVoiceError(
          { message: String(capability?.reason || '本地 Whisper 模型尚未准备好。').trim() },
          '本地 Whisper 模型尚未准备好。'
        )
        return
      }

      const result = await api.transcribeChatVoice({
        account: accountAtStart,
        server_id: usableServerId,
        force: !!force
      })
      if (!requestIsCurrent()) return

      const text = String(result?.text || '').trim()
      if (!text) {
        setVoiceError(null, '本地语音转文字未返回文字。')
        return
      }
      target.voiceTranscript = text
      target.voiceTranscriptLanguage = String(result?.language || '').trim()
      target.voiceTranscriptModel = String(result?.model || '').trim()
      target.voiceTranscriptStatus = 'success'
      target.voiceTranscriptError = ''
      target.voiceTranscriptNativeRequestId = ''
    } catch (error) {
      setVoiceError(error)
    } finally {
      if (target[NATIVE_VOICE_DISPATCH_TOKEN] === localDispatchToken) {
        delete target[NATIVE_VOICE_DISPATCH_TOKEN]
        if (String(target.voiceTranscriptStatus || '').trim().toLowerCase() === 'loading') {
          target.voiceTranscriptStatus = 'idle'
          target.voiceTranscriptError = ''
        }
      }
    }
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
      showErrorAlert(error?.message || '下载失败')
    } finally {
      message._emojiDownloading = false
    }
  }

  const shouldShowImageLargeReload = (message) => {
    if (!message || String(message?.renderType || '').trim() !== 'image') return false
    if (!String(message?.imageUrl || '').trim()) return false
    return !!(
      String(message?.imageMd5 || '').trim()
      || String(message?.imageFileId || '').trim()
      || String(message?.serverIdStr || message?.serverId || '').trim()
    )
  }

  const buildManualLargeImageUrl = (message, version = Date.now()) => {
    const account = String(selectedAccount.value || '').trim()
    const username = String(selectedContact.value?.username || '').trim()
    if (!account || !username || !message) return ''

    const md5 = String(message?.imageMd5 || '').trim()
    const fileId = String(message?.imageFileId || '').trim()
    const serverId = String(message?.serverIdStr || message?.serverId || '').trim()
    if (!md5 && !fileId && !serverId) return ''

    const query = new URLSearchParams()
    query.set('account', account)
    query.set('username', username)
    if (md5) query.set('md5', md5)
    if (fileId) query.set('file_id', fileId)
    // Keep the direct local key for the first lookup and pass server_id only as
    // the message context needed by the explicit CDN-original fallback.
    if (serverId) query.set('server_id', serverId)
    query.set('prefer_live', 'true')
    query.set('deep_scan', 'true')
    query.set('fetch_remote', 'true')
    query.set('v', String(Number(version || Date.now())))
    return `${apiBase}/chat/media/image?${query.toString()}`
  }

  const isSameMessageIdentity = (left, right) => {
    if (!left || !right) return false
    const leftId = String(left?.id || '').trim()
    const rightId = String(right?.id || '').trim()
    if (leftId && rightId && leftId === rightId) return true

    const leftLocalId = Number(left?.localId || 0)
    const rightLocalId = Number(right?.localId || 0)
    if (leftLocalId && rightLocalId && leftLocalId === rightLocalId) return true

    const leftServerId = String(left?.serverIdStr || left?.serverId || '').trim()
    const rightServerId = String(right?.serverIdStr || right?.serverId || '').trim()
    if (leftServerId && rightServerId && leftServerId === rightServerId) return true

    return false
  }

  const hydrateQuoteImageUrls = (list, extraSources = []) => {
    const input = Array.isArray(list) ? list : []
    if (!input.length) return input

    const imageByServerId = new Map()
    const sources = [
      ...(Array.isArray(extraSources) ? extraSources : []),
      ...input
    ]
    for (const item of sources) {
      if (String(item?.renderType || '').trim() !== 'image') continue
      const serverId = String(item?.serverIdStr || item?.serverId || '').trim()
      if (!serverId) continue
      if (!String(item?.imageUrl || item?.imageMd5 || item?.imageFileId || '').trim()) continue
      imageByServerId.set(serverId, item)
    }
    if (!imageByServerId.size) return input

    let changed = false
    const output = input.map((message) => {
      const quoteServerId = String(message?.quoteServerId || '').trim()
      if (!quoteServerId) return message
      const quoteType = String(message?.quoteType || '').trim()
      const quoteContent = String(message?.quoteContent || '').trim()
      if (quoteType !== '3' && quoteContent !== '[图片]') return message

      const original = imageByServerId.get(quoteServerId)
      if (!original) return message

      const nextUrl = String(original?.imageUrl || '').trim()
      if (!nextUrl || nextUrl === String(message?.quoteImageUrl || '').trim()) return message

      changed = true
      return {
        ...message,
        quoteImageUrl: nextUrl,
        _quoteImageError: false
      }
    })

    return changed ? output : input
  }

  const persistLargeImageUrlForLoadedMessage = (message, nextUrl, triedAt) => {
    const username = String(selectedContact.value?.username || '').trim()
    const url = String(nextUrl || '').trim()
    if (!username || !url || !message) return false

    const list = allMessages.value[username]
    if (!Array.isArray(list) || !list.length) return false

    const index = list.findIndex((item) => isSameMessageIdentity(item, message))
    if (index < 0) return false

    const nextList = [...list]
    nextList[index] = {
      ...nextList[index],
      imageUrl: url,
      _imageLargeLoading: false,
      _imageLargeError: '',
      _imageLargeLastTriedAt: Number(triedAt || Date.now())
    }
    const hydrated = hydrateQuoteImageUrls(nextList)
    allMessages.value = {
      ...allMessages.value,
      [username]: hydrated
    }
    return true
  }

  const preloadImageUrl = (url) => {
    const src = String(url || '').trim()
    if (!src) return Promise.reject(new Error('缺少图片地址'))
    if (!process.client || typeof window === 'undefined') return Promise.resolve()

    return new Promise((resolve, reject) => {
      const img = new window.Image()
      let timer = null
      let settled = false
      const cleanup = () => {
        if (timer) {
          window.clearTimeout(timer)
          timer = null
        }
        img.onload = null
        img.onerror = null
      }
      const finish = (ok, value) => {
        if (settled) return
        settled = true
        cleanup()
        if (ok) resolve(value)
        else reject(value instanceof Error ? value : new Error(String(value || '图片加载失败')))
      }

      img.onload = () => {
        const width = Number(img.naturalWidth || 0)
        const height = Number(img.naturalHeight || 0)
        if (!width || !height) {
          finish(false, new Error('图片加载失败'))
          return
        }
        finish(true, { width, height })
      }
      img.onerror = () => finish(false, new Error('暂未找到可用大图'))
      timer = window.setTimeout(() => finish(false, new Error('查找大图超时')), 45000)
      try { img.decoding = 'async' } catch {}
      try { img.referrerPolicy = 'no-referrer' } catch {}
      img.src = src
    })
  }

  const onTryLoadLargeImageClick = async (message) => {
    if (!process.client) return
    if (!message || message._imageLargeLoading) return

    const triedAt = Date.now()
    const nextUrl = buildManualLargeImageUrl(message, triedAt)
    if (!nextUrl) {
      message._imageLargeError = '缺少图片定位信息，无法重新查找'
      return
    }

    const previousUrl = String(message?.imageUrl || '').trim()
    message._imageLargeLoading = true
    message._imageLargeError = ''

    try {
      await preloadImageUrl(nextUrl)
      rememberLargeImagePreference(message, triedAt)
      message.imageUrl = nextUrl
      message._imageLargeLastTriedAt = triedAt
      message._imageLargeError = ''
      persistLargeImageUrlForLoadedMessage(message, nextUrl, triedAt)

      if (previewImageUrl.value && String(previewImageUrl.value || '').trim() === previousUrl) {
        previewImageUrl.value = nextUrl
      }
      if (Array.isArray(previewImageItems.value) && previousUrl) {
        previewImageItems.value = previewImageItems.value.map((item) => {
          const itemUrl = String(item?.url || '').trim()
          const itemId = String(item?.id || '').trim()
          const messageId = String(message?.id || '').trim()
          if (itemUrl !== previousUrl && (!itemId || !messageId || itemId !== messageId)) return item
          return { ...item, url: nextUrl, thumbUrl: nextUrl }
        })
      }
    } catch (error) {
      message._imageLargeError = error?.message || '暂未找到可用大图'
    } finally {
      message._imageLargeLoading = false
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
      showErrorAlert(error?.message || '打开文件夹失败')
    }
  }

  const loadMessages = async ({ username, reset }) => {
    if (!username || !selectedAccount.value) return

    abortMessageLoad()
    const requestController = typeof AbortController === 'function' ? new AbortController() : null
    messageLoadController = requestController
    messageLoadTargetUsername = String(username || '').trim()
    const loadSeq = ++messageLoadSeq
    const accountAtStart = String(selectedAccount.value || '').trim()
    const filterAtStart = String(messageTypeFilter.value || 'all').trim() || 'all'
    const trace = createPerfTrace('chat-messages', {
      account: accountAtStart,
      selectedUsername: String(selectedContact.value?.username || '').trim(),
      username: String(username || '').trim(),
      reset: !!reset,
      loadSeq,
      filter: filterAtStart
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
      const filterActive = !!(messageTypeFilter.value && messageTypeFilter.value !== 'all')
      const currentMeta = messagesMeta.value[username] || {}
      const scanOffset = reset
        ? 0
        : Math.max(0, Number(currentMeta.nextScanOffset ?? currentMeta.scanOffset ?? 0) || 0)
      const filterOffset = reset
        ? 0
        : Math.max(0, Number(currentMeta.nextFilterOffset ?? 0) || 0)
      let requestScanOffset = scanOffset
      let requestFilterOffset = filterOffset
      let response = null
      const rawChunks = []
      const seenFilterCursors = new Set()
      // 筛选模式按“扫描窗口”分页。不要为了凑满 50 条一直扫；一旦拿到
      // 可渲染结果就先提交给 UI。只有当前窗口没有匹配时，才向前跳过
      // 少量空窗口，避免稀疏类型（红包/文件等）滚到顶部后看起来没反应。
      const maxFilterRequests = filterActive ? 6 : 1

      for (let requestIndex = 0; requestIndex < maxFilterRequests; requestIndex += 1) {
        const requestOffset = filterActive ? requestFilterOffset : (reset ? 0 : existing.length)
        const cursorKey = filterActive ? `${requestScanOffset}:${requestFilterOffset}` : 'default'
        if (filterActive && seenFilterCursors.has(cursorKey)) break
        if (filterActive) seenFilterCursors.add(cursorKey)

        const params = {
          account: selectedAccount.value,
          username,
          limit: messagePageSize,
          offset: requestOffset,
          order: 'asc'
        }
        if (filterActive) {
          params.render_types = messageTypeFilter.value
          params.filter_mode = 'progressive'
          params.scan_offset = requestScanOffset
          params.scan_limit = messageTypeFilterScanPageSize
        }
        params.source = DEFAULT_CHAT_SOURCE
        if (requestController) params.signal = requestController.signal
        if (isChatPerfLoggingEnabled()) params.perfTraceId = trace.id
        trace.log('loadMessages:request:start', {
          requestIndex,
          offset: requestOffset,
          scanOffset: filterActive ? requestScanOffset : null,
          filterOffset: filterActive ? requestFilterOffset : null,
          scanLimit: filterActive ? messageTypeFilterScanPageSize : null,
          existingCount: existing.length,
          renderTypeFilter: messageTypeFilter.value,
          source: DEFAULT_CHAT_SOURCE,
          realtime: !!realtimeEnabled.value
        })

        response = await api.listChatMessages(params)
        const pageRaw = Array.isArray(response?.messages) ? response.messages : []
        rawChunks.push(pageRaw)
        trace.log('loadMessages:request:end', {
          requestIndex,
          source: response?.source || DEFAULT_CHAT_SOURCE,
          rawCount: pageRaw.length,
          accumulatedRawCount: rawChunks.reduce((sum, chunk) => sum + chunk.length, 0),
          total: Number(response?.total || 0),
          hasMore: response?.hasMore,
          nextScanOffset: response?.nextScanOffset,
          nextFilterOffset: response?.nextFilterOffset
        })

        if (!filterActive) break
        if (!response?.hasMore) break
        if (pageRaw.length > 0) break

        const nextScanOffset = Math.max(
          0,
          Number(response?.nextScanOffset ?? (requestScanOffset + messageTypeFilterScanPageSize)) || 0
        )
        const nextFilterOffset = Math.max(0, Number(response?.nextFilterOffset ?? 0) || 0)
        const nextCursorKey = `${nextScanOffset}:${nextFilterOffset}`
        if (nextCursorKey === cursorKey || seenFilterCursors.has(nextCursorKey)) break
        requestScanOffset = nextScanOffset
        requestFilterOffset = nextFilterOffset
      }

      if (!response) response = { messages: [], total: 0, hasMore: false }
      const raw = filterActive
        ? rawChunks.slice().reverse().flat()
        : rawChunks.flat()
      trace.log('loadMessages:normalize:start', {
        rawCount: raw.length
      })
      loadLargeImagePreferences()
      const mapped = dedupeMessagesById(raw.map(normalizeMessage))
      trace.log('loadMessages:normalize:end', {
        mappedCount: mapped.length,
        renderTypeCounts: summarizeRenderTypes(mapped)
      })

      if (
        loadSeq !== messageLoadSeq
        || activeMessagesFor.value !== username
        || String(selectedAccount.value || '').trim() !== accountAtStart
        || String(selectedContact.value?.username || '').trim() !== String(username || '').trim()
        || (String(messageTypeFilter.value || 'all').trim() || 'all') !== filterAtStart
      ) {
        trace.log('loadMessages:abort-stale', {
          activeMessagesFor: activeMessagesFor.value,
          currentLoadSeq: messageLoadSeq,
          currentFilter: String(messageTypeFilter.value || 'all').trim() || 'all'
        })
        return
      }

      trace.log('loadMessages:state-commit:start', {
        mappedCount: mapped.length
      })
      if (reset) {
        allMessages.value = { ...allMessages.value, [username]: hydrateQuoteImageUrls(mapped) }
      } else {
        const existingIds = new Set(existing.map((message) => String(message?.id || '')))
        const older = mapped.filter((message) => {
          const id = String(message?.id || '')
          if (!id) return true
          if (existingIds.has(id)) return false
          existingIds.add(id)
          return true
        })
        const nextMessages = hydrateQuoteImageUrls([...older, ...existing])
        allMessages.value = {
          ...allMessages.value,
          [username]: nextMessages
        }
      }
      trace.log('loadMessages:state-commit:end', {
        storedCount: (allMessages.value[username] || []).length
      })

      void restoreVoiceTranscripts(username)

      messagesMeta.value = {
        ...messagesMeta.value,
        [username]: {
          total: Number(response?.total || 0),
          hasMore: response?.hasMore,
          renderTypes: filterActive ? String(messageTypeFilter.value || '') : '',
          filterMode: filterActive ? 'progressive' : '',
          scanOffset: filterActive ? scanOffset : null,
          filterOffset: filterActive ? filterOffset : null,
          scanLimit: filterActive ? messageTypeFilterScanPageSize : null,
          nextScanOffset: filterActive
            ? Math.max(
              scanOffset,
              Number(response?.nextScanOffset ?? (scanOffset + messageTypeFilterScanPageSize)) || scanOffset
            )
            : null,
          nextFilterOffset: filterActive
            ? Math.max(0, Number(response?.nextFilterOffset ?? 0) || 0)
            : null
        }
      }
      trace.log('loadMessages:meta-commit:end', {
        total: Number(response?.total || 0),
        hasMore: response?.hasMore,
        nextScanOffset: response?.nextScanOffset,
        nextFilterOffset: response?.nextFilterOffset
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
      if (isAbortError(error, requestController)) {
        trace.log('loadMessages:request:aborted')
        return
      }
      console.error('[chat-messages] loadMessages:error', {
        account: String(selectedAccount.value || '').trim(),
        username: String(username || '').trim(),
        reset: !!reset,
        error
      })
      if (loadSeq === messageLoadSeq) {
        messagesError.value = error?.message || '加载聊天记录失败'
      }
    } finally {
      if (messageLoadController === requestController) {
        messageLoadController = null
        messageLoadTargetUsername = ''
      }
      if (loadSeq === messageLoadSeq) {
        isLoadingMessages.value = false
      }
      trace.log('loadMessages:exit', {
        loading: isLoadingMessages.value,
        error: messagesError.value
      })
    }
  }

  const loadMoreMessages = async () => {
    if (!selectedContact.value) return
    if (isLoadingMessages.value) return
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

    abortRealtimeRefresh()
    const requestController = typeof AbortController === 'function' ? new AbortController() : null
    realtimeRefreshController = requestController
    realtimeRefreshTargetUsername = String(username || '').trim()
    if (requestController) params.signal = requestController.signal
    try {
      const response = await api.listChatMessages(params)
      if (selectedContact.value?.username !== username) return

      const rawMessages = response?.messages || []
      loadLargeImagePreferences()
      const latest = hydrateQuoteImageUrls(dedupeMessagesById(rawMessages.map(normalizeMessage)), existing)

      const latestById = new Map(
        latest
          .map((message) => [String(message?.id || ''), message])
          .filter(([id]) => !!id)
      )
      const latestByServerId = new Map(
        latest
          .map((message) => [String(message?.serverIdStr || message?.serverId || '').trim(), message])
          .filter(([serverId]) => !!serverId && serverId !== '0')
      )
      let existingChanged = false
      const updatedExisting = existing.map((message) => {
        const incoming = latestById.get(String(message?.id || ''))
          || latestByServerId.get(String(message?.serverIdStr || message?.serverId || '').trim())
        if (!incoming) return message
        const updated = mergeWechatNativeVoiceTranscript(message, incoming)
        if (updated !== message) existingChanged = true
        return updated
      })

      const seenIds = new Set(updatedExisting.map((message) => String(message?.id || '')))
      const seenServerIds = new Set(
        updatedExisting
          .map((message) => String(message?.serverIdStr || message?.serverId || '').trim())
          .filter((serverId) => !!serverId && serverId !== '0')
      )
      const newOnes = []
      for (const message of latest) {
        const id = String(message?.id || '')
        const serverId = String(message?.serverIdStr || message?.serverId || '').trim()
        if (!id || seenIds.has(id) || (serverId && serverId !== '0' && seenServerIds.has(serverId))) continue
        seenIds.add(id)
        if (serverId && serverId !== '0') seenServerIds.add(serverId)
        newOnes.push(message)
      }
      if (!newOnes.length && !existingChanged) return

      allMessages.value = {
        ...allMessages.value,
        [username]: hydrateQuoteImageUrls([...updatedExisting, ...newOnes])
      }

      await nextTick()
      const nextContainer = messageContainerRef.value
      if (nextContainer && atBottom) {
        nextContainer.scrollTop = nextContainer.scrollHeight
      }
      updateJumpToBottomState()
    } catch (error) {
      if (isAbortError(error, requestController)) return
      console.error('[chat-messages] refreshRealtimeIncremental:error', {
        account: String(selectedAccount.value || '').trim(),
        username: String(username || '').trim(),
        error
      })
    } finally {
      if (realtimeRefreshController === requestController) {
        realtimeRefreshController = null
        realtimeRefreshTargetUsername = ''
      }
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
    projectTranscriptRevision += 1
    abortMessageLoad()
    abortRealtimeRefresh()
    stopNativeVoiceTranscriptPolling()
    clearVoicePlaybackState()
    allMessages.value = {}
    messagesMeta.value = {}
    messagesError.value = ''
    highlightMessageId.value = ''
    highlightServerIdStr.value = ''
    clearExpandedImageGroups()
    closeImagePreview()
    closeVideoPreview()
    resetResourceState()
    resourceSidebarOpen.value = false
  }

  const contactProfileCardOpen = ref(false)
  const contactProfileCardMessageId = ref('')
  const contactProfileLoading = ref(false)
  const contactProfileVerificationLoading = ref(false)
  const contactProfileVerificationLoaded = ref(false)
  const contactProfileVerificationError = ref('')
  const contactProfileError = ref('')
  const contactProfileData = ref(null)
  const CONTACT_PROFILE_REQUEST_TIMEOUT_MS = 4500
  const CONTACT_PROFILE_HOVER_INTENT_MS = 250
  const CONTACT_PROFILE_CACHE_TTL_MS = 5 * 60 * 1000
  const CONTACT_VERIFICATION_CACHE_TTL_MS = 5 * 60 * 1000
  const CONTACT_PROFILE_CACHE_MAX_ENTRIES = 128
  const contactProfileCache = new Map()
  const contactProfileInflight = new Map()
  const contactVerificationCache = new Map()
  const contactVerificationInflight = new Map()
  let contactProfileFetchSeq = 0
  let contactProfileHoverIntentTimer = null
  let contactProfileHoverHideTimer = null
  let activeContactProfileRequest = null
  let activeContactVerificationRequest = null

  const makeContactProfileCacheKey = (account, username) => (
    `${String(account || '').trim()}\u0000${String(username || '').trim()}`
  )

  const readTimedCache = (cache, key, ttlMs) => {
    const entry = cache.get(key)
    if (!entry) return null
    if ((Date.now() - Number(entry.updatedAt || 0)) > ttlMs) {
      cache.delete(key)
      return null
    }
    return entry
  }

  const writeTimedCache = (cache, key, data) => {
    cache.delete(key)
    cache.set(key, { updatedAt: Date.now(), data })
    while (cache.size > CONTACT_PROFILE_CACHE_MAX_ENTRIES) {
      const oldestKey = cache.keys().next().value
      if (oldestKey == null) break
      cache.delete(oldestKey)
    }
  }

  const withContactProfileTimeout = (promise, ms, message = '请求超时', controller = null) => {
    let timer = null
    return new Promise((resolve, reject) => {
      timer = setTimeout(() => {
        timer = null
        const error = new Error(message)
        error.code = 'ETIMEDOUT'
        if (controller && !controller.signal.aborted) {
          try { controller.abort() } catch {}
        }
        reject(error)
      }, Math.max(1, Number(ms || 0)))

      Promise.resolve(promise).then(
        (value) => {
          if (timer) clearTimeout(timer)
          timer = null
          resolve(value)
        },
        (error) => {
          if (timer) clearTimeout(timer)
          timer = null
          reject(error)
        }
      )
    })
  }

  const abortInflightRequest = (entry, inflight) => {
    if (!entry) return
    if (inflight.get(entry.key) === entry) inflight.delete(entry.key)
    if (entry.controller && !entry.controller.signal.aborted) {
      try { entry.controller.abort() } catch {}
    }
  }

  const abortActiveContactProfileRequest = () => {
    const entry = activeContactProfileRequest
    activeContactProfileRequest = null
    abortInflightRequest(entry, contactProfileInflight)
  }

  const abortActiveContactVerificationRequest = () => {
    const entry = activeContactVerificationRequest
    activeContactVerificationRequest = null
    abortInflightRequest(entry, contactVerificationInflight)
  }

  const abortContactRequestsExcept = (key) => {
    if (activeContactProfileRequest?.key && activeContactProfileRequest.key !== key) {
      abortActiveContactProfileRequest()
    }
    if (activeContactVerificationRequest?.key && activeContactVerificationRequest.key !== key) {
      abortActiveContactVerificationRequest()
    }
  }

  const requestContactProfile = ({ account, username }) => {
    const key = makeContactProfileCacheKey(account, username)
    const cached = readTimedCache(contactProfileCache, key, CONTACT_PROFILE_CACHE_TTL_MS)
    if (cached) return Promise.resolve(cached.data)

    const pending = contactProfileInflight.get(key)
    if (pending) {
      activeContactProfileRequest = pending
      return pending.promise
    }

    const controller = typeof AbortController === 'function' ? new AbortController() : null
    const params = {
      account,
      source: DEFAULT_CHAT_SOURCE,
      username
    }
    if (controller) params.signal = controller.signal

    const entry = { key, controller, promise: null }
    entry.promise = withContactProfileTimeout(
      api.getChatContactProfile(params),
      CONTACT_PROFILE_REQUEST_TIMEOUT_MS,
      '联系人资料加载超时',
      controller
    ).then((response) => {
      writeTimedCache(contactProfileCache, key, response)
      return response
    }).finally(() => {
      if (contactProfileInflight.get(key) === entry) contactProfileInflight.delete(key)
      if (activeContactProfileRequest === entry) activeContactProfileRequest = null
    })
    contactProfileInflight.set(key, entry)
    activeContactProfileRequest = entry
    return entry.promise
  }

  const requestContactFriendVerifications = ({ account, username }) => {
    const key = makeContactProfileCacheKey(account, username)
    const cached = readTimedCache(contactVerificationCache, key, CONTACT_VERIFICATION_CACHE_TTL_MS)
    if (cached) return Promise.resolve(cached.data)

    const pending = contactVerificationInflight.get(key)
    if (pending) {
      activeContactVerificationRequest = pending
      return pending.promise
    }

    const controller = typeof AbortController === 'function' ? new AbortController() : null
    const params = {
      account,
      q: username,
      source: 'realtime',
      limit: 200,
      offset: 0
    }
    if (controller) params.signal = controller.signal

    const entry = { key, controller, promise: null }
    entry.promise = withContactProfileTimeout(
      api.listFriendVerifications(params),
      CONTACT_PROFILE_REQUEST_TIMEOUT_MS,
      '好友验证记录加载超时',
      controller
    ).then((response) => {
      const records = (Array.isArray(response?.items) ? response.items : [])
        .filter((item) => String(item?.userName || '').trim() === username)
        .map((item) => ({
          userName: username,
          isSender: !!item?.isSender,
          content: String(item?.content || '').trim(),
          remark: String(item?.remark || '').trim(),
          timeText: String(item?.timeText || '').trim(),
          timestamp: Number(item?.timestamp || 0)
        }))
      writeTimedCache(contactVerificationCache, key, records)
      return records
    }).finally(() => {
      if (contactVerificationInflight.get(key) === entry) contactVerificationInflight.delete(key)
      if (activeContactVerificationRequest === entry) activeContactVerificationRequest = null
    })
    contactVerificationInflight.set(key, entry)
    activeContactVerificationRequest = entry
    return entry.promise
  }

  const contactProfileInitialLoading = computed(() => (
    !!contactProfileLoading.value && !contactProfileData.value
  ))

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
  const contactProfileResolvedGroupNickname = computed(() => String(contactProfileData.value?.groupNickname || '').trim())
  const contactProfileIsFriend = computed(() => String(contactProfileData.value?.type || '').trim() === 'friend')
  const contactProfileFriendVerifications = computed(() => (
    Array.isArray(contactProfileData.value?.friendVerifications)
      ? contactProfileData.value.friendVerifications
      : []
  ))
  const contactProfileResolvedHeaderSubtitle = computed(() => {
    const username = contactProfileResolvedUsername.value
    if (username) return `微信ID：${username}`
    const alias = contactProfileResolvedAlias.value
    return alias ? `微信号：${alias}` : ''
  })
  const contactProfileResolvedAddTime = computed(() => {
    const text = String(contactProfileData.value?.addTimeText || '').trim()
    if (text) return text
    const value = contactProfileData.value?.addTime
    if (value == null || value === '') return ''
    const ts = Number(value)
    if (!Number.isFinite(ts) || ts <= 0) return ''
    const date = new Date((ts > 10000000000 ? ts : ts * 1000))
    if (Number.isNaN(date.getTime())) return ''
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  })
  const contactProfileResolvedCommonChatroomCount = computed(() => {
    const value = contactProfileData.value?.commonChatroomCount
    if (value == null || value === '') return null
    const count = Number(value)
    return Number.isFinite(count) && count >= 0 ? count : null
  })
  const contactProfileResolvedCommonChatrooms = computed(() => {
    const rows = Array.isArray(contactProfileData.value?.commonChatrooms)
      ? contactProfileData.value.commonChatrooms
      : []
    const seen = new Set()
    return rows
      .map((row) => {
        const item = row && typeof row === 'object' ? row : {}
        const username = String(item.username || item.roomUsername || '').trim()
        if (!username || seen.has(username)) return null
        seen.add(username)
        return {
          username,
          displayName: String(item.displayName || item.name || item.nickname || '').trim() || '未命名群聊',
          avatar: String(item.avatar || item.avatarUrl || '').trim(),
          avatarColor: String(item.avatarColor || '').trim() || '#07c160'
        }
      })
      .filter(Boolean)
  })
  const contactProfileHasMoreInfo = computed(() => (
    (contactProfileResolvedCommonChatroomCount.value != null && contactProfileResolvedCommonChatroomCount.value > 0)
    || contactProfileResolvedCommonChatrooms.value.length > 0
    || !!contactProfileResolvedSource.value
    || !!contactProfileResolvedAddTime.value
  ))
  const contactProfileResolvedAvatar = computed(() => {
    const avatar = String(contactProfileData.value?.avatar || '').trim()
    if (avatar) return avatar
    return String(selectedContact.value?.avatar || '').trim()
  })
  const contactProfileResolvedAvatarColor = computed(() => (
    String(contactProfileData.value?.avatarColor || '').trim()
    || String(selectedContact.value?.avatarColor || '').trim()
    || '#6b7280'
  ))

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

  const applyCachedContactVerifications = (profile, account, username) => {
    const key = makeContactProfileCacheKey(account, username)
    const cached = readTimedCache(contactVerificationCache, key, CONTACT_VERIFICATION_CACHE_TTL_MS)
    contactProfileVerificationLoaded.value = !!cached
    contactProfileVerificationError.value = ''
    return {
      ...profile,
      friendVerifications: cached ? cached.data : []
    }
  }

  const loadContactFriendVerifications = async () => {
    const seq = contactProfileFetchSeq
    const account = String(selectedAccount.value || '').trim()
    const username = String(contactProfileData.value?.username || '').trim()
    if (!account || !username || !contactProfileIsFriend.value) return

    const key = makeContactProfileCacheKey(account, username)
    abortContactRequestsExcept(key)
    contactProfileVerificationLoading.value = true
    contactProfileVerificationError.value = ''
    try {
      const records = await requestContactFriendVerifications({ account, username })
      if (
        seq !== contactProfileFetchSeq
        || String(contactProfileData.value?.username || '').trim() !== username
      ) return
      contactProfileData.value = {
        ...(contactProfileData.value || {}),
        friendVerifications: records
      }
      contactProfileVerificationLoaded.value = true
    } catch (error) {
      if (seq !== contactProfileFetchSeq || isAbortError(error)) return
      contactProfileVerificationLoaded.value = false
      contactProfileVerificationError.value = error?.code === 'ETIMEDOUT'
        ? '加载超时，请重试'
        : (error?.message || '好友验证记录加载失败')
    } finally {
      if (seq === contactProfileFetchSeq) contactProfileVerificationLoading.value = false
    }
  }

  const fetchContactProfile = async (options = {}) => {
    const seq = ++contactProfileFetchSeq
    const username = String(options?.username || contactProfileData.value?.username || selectedContact.value?.username || '').trim()
    const displayNameFallback = String(options?.displayName || '').trim()
    const avatarFallback = String(options?.avatar || '').trim()
    const account = String(selectedAccount.value || '').trim()
    if (!username || !account) {
      contactProfileData.value = null
      contactProfileLoading.value = false
      return
    }
    const key = makeContactProfileCacheKey(account, username)
    abortContactRequestsExcept(key)

    const contextPatch = {
      groupNickname: String(options?.groupNickname || contactProfileData.value?.groupNickname || '').trim(),
      avatarColor: String(options?.avatarColor || contactProfileData.value?.avatarColor || selectedContact.value?.avatarColor || '').trim()
    }

    contactProfileLoading.value = true
    contactProfileError.value = ''
    try {
      const response = await requestContactProfile({ account, username })
      if (seq !== contactProfileFetchSeq) return
      const matched = response?.contact && typeof response.contact === 'object' ? response.contact : null
      if (matched) {
        const normalized = { ...matched, ...contextPatch, username }
        if (!String(normalized.displayName || '').trim() && displayNameFallback) {
          normalized.displayName = displayNameFallback
        }
        if (!String(normalized.avatar || '').trim() && avatarFallback) {
          normalized.avatar = avatarFallback
        }
        contactProfileData.value = applyCachedContactVerifications(normalized, account, username)
      } else {
        const fallbackType = username.endsWith('@chatroom')
          ? 'group'
          : (username.startsWith('gh_') ? 'official' : 'friend')
        contactProfileData.value = applyCachedContactVerifications({
          username,
          type: fallbackType,
          displayName: displayNameFallback || selectedContact.value?.name || username,
          avatar: avatarFallback || selectedContact.value?.avatar || '',
          avatarColor: contextPatch.avatarColor,
          nickname: '',
          alias: '',
          gender: null,
          region: '',
          remark: '',
          signature: '',
          source: '',
          sourceScene: null,
          addTime: null,
          addTimeText: '',
          commonChatroomCount: null,
          commonChatrooms: [],
          ...contextPatch
        }, account, username)
      }
    } catch (error) {
      if (seq !== contactProfileFetchSeq) return
      if (isAbortError(error)) return
      contactProfileData.value = applyCachedContactVerifications({
        username,
        type: username.endsWith('@chatroom') ? 'group' : (username.startsWith('gh_') ? 'official' : 'friend'),
        displayName: displayNameFallback || selectedContact.value?.name || username,
        avatar: avatarFallback || selectedContact.value?.avatar || '',
        avatarColor: contextPatch.avatarColor,
        nickname: '',
        alias: '',
        gender: null,
        region: '',
        remark: '',
        signature: '',
        source: '',
        sourceScene: null,
        addTime: null,
        addTimeText: '',
        commonChatroomCount: null,
        commonChatrooms: [],
        ...contextPatch
      }, account, username)
      contactProfileError.value = error?.code === 'ETIMEDOUT' ? '' : (error?.message || '加载联系人资料失败')
    } finally {
      if (seq === contactProfileFetchSeq) contactProfileLoading.value = false
    }
  }

  const clearContactProfileHoverIntentTimer = () => {
    if (contactProfileHoverIntentTimer) {
      clearTimeout(contactProfileHoverIntentTimer)
      contactProfileHoverIntentTimer = null
    }
  }

  const clearContactProfileHoverHideTimer = () => {
    if (contactProfileHoverHideTimer) {
      clearTimeout(contactProfileHoverHideTimer)
      contactProfileHoverHideTimer = null
    }
  }

  const closeContactProfileCard = () => {
    clearContactProfileHoverIntentTimer()
    clearContactProfileHoverHideTimer()
    contactProfileFetchSeq++
    abortActiveContactProfileRequest()
    abortActiveContactVerificationRequest()
    contactProfileLoading.value = false
    contactProfileVerificationLoading.value = false
    contactProfileVerificationLoaded.value = false
    contactProfileVerificationError.value = ''
    contactProfileCardOpen.value = false
    contactProfileCardMessageId.value = ''
  }

  const applyContactProfilePreview = (options = {}) => {
    const username = String(options?.username || '').trim()
    const account = String(selectedAccount.value || '').trim()
    if (!username || !account) return
    const displayName = String(options?.displayName || username).trim() || username
    const avatar = String(options?.avatar || '').trim()
    const avatarColor = String(options?.avatarColor || '').trim()
    const groupNickname = String(options?.groupNickname || '').trim()
    const currentUsername = String(contactProfileData.value?.username || '').trim()

    if (currentUsername !== username) {
      contactProfileData.value = applyCachedContactVerifications({
        username,
        type: username.endsWith('@chatroom') ? 'group' : (username.startsWith('gh_') ? 'official' : 'friend'),
        displayName,
        avatar,
        avatarColor,
        nickname: '',
        alias: '',
        gender: null,
        region: '',
        remark: '',
        signature: '',
        source: '',
        sourceScene: null,
        addTime: null,
        addTimeText: '',
        commonChatroomCount: null,
        commonChatrooms: [],
        groupNickname
      }, account, username)
      return
    }

    contactProfileData.value = applyCachedContactVerifications({
      ...(contactProfileData.value || {}),
      displayName: String(contactProfileData.value?.displayName || '').trim() || displayName,
      avatar: String(contactProfileData.value?.avatar || '').trim() || avatar,
      avatarColor: avatarColor || String(contactProfileData.value?.avatarColor || '').trim(),
      groupNickname
    }, account, username)
  }

  const openContactProfileCardAfterIntent = ({ cardId, ...options }) => {
    const username = String(options?.username || '').trim()
    const account = String(selectedAccount.value || '').trim()
    if (!cardId || !username || !account) return
    abortContactRequestsExcept(makeContactProfileCacheKey(account, username))
    applyContactProfilePreview({ ...options, username })
    contactProfileCardMessageId.value = cardId
    contactProfileCardOpen.value = true
    void fetchContactProfile({ ...options, username })
  }

  const scheduleContactProfileCard = (options = {}) => {
    clearContactProfileHoverIntentTimer()
    clearContactProfileHoverHideTimer()
    contactProfileHoverIntentTimer = setTimeout(() => {
      contactProfileHoverIntentTimer = null
      openContactProfileCardAfterIntent(options)
    }, CONTACT_PROFILE_HOVER_INTENT_MS)
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

  const onMessageAvatarMouseEnter = (message) => {
    if (!!message?.isSent) return
    const messageId = String(message?.id ?? '').trim()
    if (!messageId) return
    const username = String(message?.senderUsername || '').trim()
    if (!username || username === 'self') return

    const senderName = String(message?.senderDisplayName || message?.sender || '').trim()
    const senderAvatar = String(message?.avatar || '').trim()
    scheduleContactProfileCard({
      cardId: messageId,
      username,
      displayName: senderName,
      avatar: senderAvatar,
      avatarColor: String(message?.avatarColor || '').trim(),
      groupNickname: message?.isGroup ? senderName : ''
    })
  }

  const onMentionMouseEnter = (message, user) => {
    const username = String(user?.username || '').trim()
    if (!username) return
    if (username === 'notify@all') return
    const cardId = getMentionContactProfileCardId(message, user)
    if (!cardId) return

    const displayName = String(user?.displayName || user?.nickname || user?.remark || username).trim()
    const avatar = String(user?.avatar || '').trim()
    scheduleContactProfileCard({
      cardId,
      username,
      displayName,
      avatar,
      avatarColor: String(user?.avatarColor || '').trim(),
      groupNickname: displayName
    })
  }

  const onMessageAvatarMouseLeave = () => {
    clearContactProfileHoverIntentTimer()
    clearContactProfileHoverHideTimer()
    contactProfileHoverHideTimer = setTimeout(() => {
      closeContactProfileCard()
    }, 120)
  }

  const onMentionMouseLeave = () => {
    onMessageAvatarMouseLeave()
  }

  const onContactCardMouseEnter = () => {
    clearContactProfileHoverIntentTimer()
    clearContactProfileHoverHideTimer()
  }

  const onProjectVoiceTranscriptsInvalidated = () => {
    invalidateProjectVoiceTranscripts()
    if (selectedContact.value?.username) void refreshSelectedMessages()
  }

  const onNativeVoiceWindowFocus = () => {
    void refreshNativeVoiceTranscriptionStatus({ force: true })
  }

  if (typeof window !== 'undefined') {
    window.addEventListener(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT, onProjectVoiceTranscriptsInvalidated)
    window.addEventListener('focus', onNativeVoiceWindowFocus)
  }

  watch(
    () => selectedContact.value?.username,
    (username) => {
      stopNativeVoiceTranscriptPolling()
      const nextUsername = String(username || '').trim()
      if (messageLoadTargetUsername && messageLoadTargetUsername !== nextUsername) {
        abortMessageLoad()
      }
      if (realtimeRefreshTargetUsername && realtimeRefreshTargetUsername !== nextUsername) {
        abortRealtimeRefresh()
      }
      clearExpandedImageGroups()
      loadLargeImagePreferences()
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
      stopNativeVoiceTranscriptPolling()
      nativeVoiceTranscriptionStatusSequence += 1
      nativeVoiceTranscriptionStatusPromise = null
      nativeVoiceTranscriptionStatusLoading.value = false
      nativeVoiceTranscriptionStatus.value = null
      nativeVoiceTranscriptionStatusUpdatedAt = 0
      void refreshNativeVoiceTranscriptionStatus()
      clearExpandedImageGroups()
      loadLargeImagePreferences()
      clearContactProfileHoverHideTimer()
      closeContactProfileCard()
      contactProfileError.value = ''
      contactProfileData.value = null
      resetResourceState()
    }
  )

  onUnmounted(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT, onProjectVoiceTranscriptsInvalidated)
      window.removeEventListener('focus', onNativeVoiceWindowFocus)
    }
    abortMessageLoad()
    abortRealtimeRefresh()
    stopNativeVoiceTranscriptPolling()
    if (highlightTimer) clearTimeout(highlightTimer)
    highlightTimer = null
    cancelImageGroupTransition()
    clearContactProfileHoverIntentTimer()
    clearContactProfileHoverHideTimer()
    abortActiveContactProfileRequest()
    abortActiveContactVerificationRequest()
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
    voiceTranscriptionStatus,
    voiceTranscriptionStatusLoading,
    voiceTranscriptionStatusKnown,
    voiceTranscriptionAvailable,
    voiceTranscriptionUnavailableReason,
    refreshVoiceTranscriptionStatus,
    nativeVoiceTranscriptionStatus,
    nativeVoiceTranscriptionStatusLoading,
    nativeVoiceTranscriptionStatusKnown,
    nativeVoiceTranscriptionAvailable,
    nativeVoiceTranscriptionUnavailableReason,
    refreshNativeVoiceTranscriptionStatus,
    highlightServerIdStr,
    highlightMessageId,
    expandedImageGroupKeys,
    imageGroupActiveItemIds,
    activeImageGroupTransitionKey,
    imageGroupTransitioning,
    contactProfileCardOpen,
    contactProfileCardMessageId,
    contactProfileLoading,
    contactProfileInitialLoading,
    contactProfileVerificationLoading,
    contactProfileVerificationLoaded,
    contactProfileVerificationError,
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
    contactProfileResolvedGroupNickname,
    contactProfileIsFriend,
    contactProfileFriendVerifications,
    contactProfileResolvedSourceScene,
    contactProfileResolvedHeaderSubtitle,
    contactProfileResolvedAddTime,
    contactProfileResolvedCommonChatroomCount,
    contactProfileResolvedCommonChatrooms,
    contactProfileHasMoreInfo,
    contactProfileResolvedAvatar,
    contactProfileResolvedAvatarColor,
    normalizeMessage,
    updateJumpToBottomState,
    scrollToBottom,
    flashMessage,
    scrollToMessageId,
    toggleImageGroupExpanded,
    transitionImageGroupExpanded,
    getImageGroupActiveItemId,
    setImageGroupActiveItemId,
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
    transcribeVoice,
    transcribeVoiceLocally,
    pollNativeVoiceTranscript,
    restoreVoiceTranscripts,
    stopNativeVoiceTranscriptPolling,
    invalidateProjectVoiceTranscripts,
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
    shouldShowImageLargeReload,
    onTryLoadLargeImageClick,
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
    loadContactFriendVerifications,
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
