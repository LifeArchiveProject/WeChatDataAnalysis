<template>
  <div class="records-page records-page--favorites">
    <div class="records-page__scroll">
      <main class="records-page__frame">
        <header class="records-masthead">
          <div class="records-masthead__identity">
            <div class="records-masthead__title-group">
              <h1>收藏</h1>
              <span class="records-masthead__count">共<strong>{{ databaseTotal }}</strong>条收藏</span>
            </div>
          </div>

          <div class="records-masthead__actions">
            <label class="records-search">
              <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
              <input v-model="keyword" type="search" aria-label="搜索收藏" placeholder="搜索正文、标题或来源" autocomplete="off" />
              <button v-if="keyword" type="button" class="records-search__clear" title="清空搜索" aria-label="清空搜索" @click="keyword = ''">
                <i class="fa-solid fa-xmark" aria-hidden="true"></i>
              </button>
            </label>
            <button type="button" class="records-icon-button" title="导出收藏" aria-label="导出收藏" @click="exportDialogOpen = true">
              <i class="fa-solid fa-file-export" aria-hidden="true"></i>
            </button>
            <button
              type="button"
              class="records-icon-button"
              :title="loading ? '正在刷新' : '刷新收藏'"
              :aria-label="loading ? '正在刷新' : '刷新收藏'"
              :disabled="loading"
              @click="loadItems({ force: true })"
            >
              <i class="fa-solid fa-arrow-rotate-right" :class="{ 'fa-spin': loading }" aria-hidden="true"></i>
            </button>
          </div>
        </header>

        <section class="records-body favorites-chat" aria-label="收藏消息列表">
          <div class="favorites-toolbar">
            <div class="favorites-types" role="group" aria-label="收藏类型">
              <button
                v-for="option in typeOptions"
                :key="option.value"
                type="button"
                :class="{ 'is-active': kindFilter === option.value }"
                :aria-pressed="kindFilter === option.value"
                @click="kindFilter = option.value"
              >
                <i :class="['fa-solid', option.icon]" aria-hidden="true"></i>
                <span>{{ option.label }}</span>
                <span class="favorites-types__count">{{ option.count }}</span>
              </button>
            </div>

            <label class="favorites-tag-filter" :class="{ 'is-disabled': !tags.length }">
              <i class="fa-solid fa-tag" aria-hidden="true"></i>
              <select v-model="tagFilter" aria-label="按收藏标签筛选" :disabled="!tags.length">
                <option value="0">全部标签</option>
                <option v-for="tag in tags" :key="tag.localId" :value="String(tag.localId)">
                  {{ tag.name || `标签 ${tag.localId}` }}
                </option>
              </select>
              <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
            </label>
          </div>

          <div v-if="loading && !items.length" class="records-state records-state--loading" role="status" aria-live="polite">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-arrow-rotate-right fa-spin"></i></span>
              <div class="records-state__title">正在加载收藏</div>
              <div class="records-state__text">正在读取实时收藏库</div>
            </div>
          </div>
          <div v-else-if="error" class="records-state records-state--error" role="alert">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-triangle-exclamation"></i></span>
              <div class="records-state__title">加载失败</div>
              <div class="records-state__text">{{ error }}</div>
            </div>
          </div>
          <div v-else-if="!items.length" class="records-state">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-regular fa-bookmark"></i></span>
              <div class="records-state__title">暂无收藏</div>
              <div class="records-state__text">当前筛选条件下没有收藏内容</div>
            </div>
          </div>
          <div v-else class="favorites-message-list">
            <article v-for="item in items" :key="favoriteKey(item)" class="favorite-message-row">
              <button
                type="button"
                class="favorite-avatar"
                :class="{ 'privacy-blur': privacyMode }"
                :title="sourceChatUsername(item) ? `打开${sourceDisplayName(item)}的会话` : sourceDisplayName(item)"
                :disabled="!sourceChatUsername(item)"
                @click="openSourceChat(item)"
              >
                <img
                  v-if="sourceAvatar(item) && !avatarBroken[favoriteKey(item)]"
                  :src="sourceAvatar(item)"
                  :alt="sourceDisplayName(item)"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                  @error="avatarBroken[favoriteKey(item)] = true"
                />
                <span v-else>{{ sourceInitial(item) }}</span>
              </button>

              <div class="favorite-message-body" :class="{ 'privacy-blur': privacyMode }">
                <div class="favorite-message-head">
                  <div class="favorite-sender-line">
                    <strong>{{ sourceDisplayName(item) }}</strong>
                    <span v-if="sourceContextName(item)">来自 {{ sourceContextName(item) }}</span>
                  </div>
                  <time>{{ item.updateTimeText || '时间未记录' }}</time>
                </div>

                <div class="favorite-content-stack">
                  <MessageContent
                    v-for="message in favoriteMessages(item)"
                    :key="message.id"
                    :message="message"
                    :state="messageState"
                  />
                </div>
              </div>
            </article>
          </div>

          <button v-if="hasMore" type="button" class="records-more" :disabled="loading" @click="loadItems({ append: true })">
            <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
            <span>{{ loading ? '正在载入' : `继续载入 ${items.length} / ${total}` }}</span>
          </button>
        </section>
      </main>
    </div>

    <div v-if="preview.kind" class="favorite-preview" role="dialog" aria-modal="true" aria-label="媒体预览" @click.self="closePreview">
      <button type="button" class="favorite-preview__close" title="关闭预览" aria-label="关闭预览" @click="closePreview">
        <i class="fa-solid fa-xmark" aria-hidden="true"></i>
      </button>
      <img v-if="preview.kind === 'image'" :src="preview.url" alt="收藏图片预览" />
      <video v-else-if="preview.kind === 'video'" :src="preview.url" :poster="preview.poster" controls autoplay></video>
    </div>

    <ChatHistoryFloatingWindows :state="historyOverlayState" />

    <RecordExportDialog
      :open="exportDialogOpen"
      dataset="favorites"
      title="收藏"
      :account="selectedAccount || ''"
      :query="keyword"
      :type-options="favoriteExportTypeOptions"
      @close="exportDialogOpen = false"
    />
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import ChatHistoryFloatingWindows from '~/components/chat/ChatHistoryFloatingWindows.vue'
import MessageContent from '~/components/chat/MessageContent.vue'
import { useChatHistoryWindows } from '~/composables/chat/useChatHistoryWindows'
import { getChatHistoryPreviewLines } from '~/lib/chat/chat-history'
import { parseTextWithEmoji } from '~/lib/wechat-emojis'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

useHead({ title: '收藏 - 微信数据分析助手' })

const api = useApi()
const apiBase = String(useApiBase() || '/api').replace(/\/$/, '')
const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)
const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const TYPE_META = {
  1: { label: '文本', icon: 'fa-align-left' },
  2: { label: '图片', icon: 'fa-image' },
  3: { label: '语音', icon: 'fa-microphone-lines' },
  4: { label: '视频', icon: 'fa-video' },
  5: { label: '链接', icon: 'fa-link' },
  6: { label: '位置', icon: 'fa-location-dot' },
  7: { label: '音乐', icon: 'fa-music' },
  8: { label: '文件', icon: 'fa-file' },
  14: { label: '聊天记录', icon: 'fa-comments' },
  16: { label: '商品', icon: 'fa-bag-shopping' },
  18: { label: '笔记', icon: 'fa-note-sticky' },
  20: { label: '视频号', icon: 'fa-circle-play' },
}

const favoriteExportTypeOptions = [
  { value: 'text', label: '文本', icon: 'fa-align-left' },
  { value: 'image', label: '图片', icon: 'fa-image' },
  { value: 'voice', label: '语音', icon: 'fa-microphone-lines' },
  { value: 'video', label: '视频', icon: 'fa-video' },
  { value: 'file', label: '文件', icon: 'fa-file' },
  { value: 'link', label: '链接 / 视频号', icon: 'fa-link' },
  { value: 'location', label: '位置', icon: 'fa-location-dot' },
  { value: 'chatHistory', label: '聊天记录', icon: 'fa-comments' },
  { value: 'emoji', label: '表情', icon: 'fa-face-smile' },
  { value: 'other', label: '其他', icon: 'fa-ellipsis' },
]

const keyword = ref('')
const kindFilter = ref('all')
const tagFilter = ref('0')
const items = ref([])
const total = ref(0)
const databaseTotal = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
const tags = ref([])
const typeCounts = ref({})
const exportDialogOpen = ref(false)
const avatarBroken = reactive({})
const preview = reactive({ kind: '', url: '', poster: '' })
const historySelectedContact = ref({ username: '' })
const playingVoiceId = ref('')
const voiceRefs = new Map()
const PAGE_SIZE = 60
let requestId = 0
let keywordTimer = null

const typeOptions = computed(() => {
  const rows = Object.entries(typeCounts.value || {})
    .map(([value, count]) => ({
      value: String(value),
      count: Number(count || 0),
      ...(TYPE_META[Number(value)] || { label: `类型 ${value}`, icon: 'fa-bookmark' }),
    }))
    .filter((item) => item.count > 0)
    .sort((a, b) => Number(a.value) - Number(b.value))
  return [{ label: '全部', value: 'all', icon: 'fa-layer-group', count: Number(databaseTotal.value || 0) }, ...rows]
})

const favoriteKey = (item) => `${item?.localId || 0}-${item?.serverId || 0}`
const looksLikeRawId = (value) => {
  const text = String(value || '').trim()
  return text.startsWith('wxid_') || text.endsWith('@chatroom') || text.startsWith('gh_')
}

const contactName = (contact) => {
  const raw = String(contact?.username || '').trim()
  for (const value of [contact?.displayName, contact?.name, contact?.nickname, contact?.remark]) {
    const text = String(value || '').trim()
    if (text && text !== raw && !looksLikeRawId(text)) return text
  }
  return ''
}

const sourceIdentity = (item) => item?.senderContact || item?.sourceChatContact || item?.sourceContact || {}
const sourceDisplayName = (item) => String(item?.originalMessage?.senderDisplayName || '').trim()
  || contactName(sourceIdentity(item))
  || String(item?.sourceName || '').trim()
  || '未知来源'
const sourceAvatar = (item) => String(
  item?.originalMessage?.senderAvatar || sourceIdentity(item)?.avatar || sourceIdentity(item)?.avatarUrl || ''
).trim()
const sourceInitial = (item) => Array.from(sourceDisplayName(item))[0] || '?'
const sourceChatUsername = (item) => String(item?.conversationUsername || item?.sourceUsername || item?.sourceChatUsername || '').trim()
const sourceContextName = (item) => {
  const context = item?.conversationContact || item?.sourceContact
  if (!context?.isGroup) return ''
  const name = contactName(context)
  return name && name !== sourceDisplayName(item) ? name : ''
}

const openSourceChat = (item) => {
  const username = sourceChatUsername(item)
  if (username) void navigateTo(`/chat/${encodeURIComponent(username)}`)
}

const buildMediaUrl = (kind, item, md5) => {
  const account = String(selectedAccount.value || '').trim()
  const hash = String(md5 || '').trim()
  if (!account || !hash) return ''
  const query = new URLSearchParams({ account, md5: hash })
  const username = sourceChatUsername(item)
  if (username) query.set('username', username)
  return `${apiBase}/chat/media/${kind}?${query.toString()}`
}

const buildVoiceUrl = (item) => {
  const account = String(selectedAccount.value || '').trim()
  const serverId = String(item?.sourceId || '').trim()
  if (!account || !/^\d+$/.test(serverId)) return ''
  return `${apiBase}/favorites/media/voice?${new URLSearchParams({ account, server_id: serverId }).toString()}`
}

const attachmentMessage = (item, attachment, index) => {
  const original = item?.originalMessage && typeof item.originalMessage === 'object' ? item.originalMessage : {}
  let renderType = String(attachment?.renderType || 'text').trim()
  if (renderType === 'contact') renderType = 'text'
  const title = String(attachment?.title || attachment?.typeLabel || '收藏内容').trim()
  const content = String(attachment?.description || attachment?.title || `[${attachment?.typeLabel || '收藏内容'}]`).trim()
  const fullMd5 = String(attachment?.fullMd5 || '').trim()
  const thumbMd5 = String(attachment?.thumbMd5 || '').trim()
  const location = attachment?.location || {}
  const explicitPreview = String(attachment?.preview || '').trim()
  const message = {
    id: `${favoriteKey(item)}-attachment-${attachment?.dataId || index}`,
    type: attachment?.dataType || item?.type || 0,
    renderType,
    isSent: false,
    content,
    title,
    url: String(attachment?.url || attachment?.mediaUrl || '').trim(),
    preview: explicitPreview || (renderType === 'link' && thumbMd5 ? buildMediaUrl('image', item, thumbMd5) : ''),
    from: String(attachment?.sourceName || '').trim(),
    fromAvatar: String(attachment?.sourceAvatar || '').trim(),
    linkType: String(attachment?.linkType || '').trim(),
    imageMd5: String(original.imageMd5 || fullMd5 || thumbMd5).trim(),
    imageUrl: renderType === 'image'
      ? String(original.imageUrl || buildMediaUrl('image', item, fullMd5 || thumbMd5)).trim()
      : '',
    imageFallbackUrl: renderType === 'image' && fullMd5 && thumbMd5 && fullMd5 !== thumbMd5
      ? buildMediaUrl('image', item, thumbMd5)
      : '',
    emojiUrl: renderType === 'emoji'
      ? String(original.emojiUrl || buildMediaUrl('emoji', item, fullMd5 || thumbMd5)).trim()
      : '',
    videoUrl: renderType === 'video'
      ? String(original.videoUrl || buildMediaUrl('video', item, fullMd5)).trim()
      : '',
    videoThumbUrl: renderType === 'video'
      ? String(original.videoThumbUrl || buildMediaUrl('video_thumb', item, thumbMd5)).trim()
      : '',
    videoThumbMd5: String(original.videoThumbMd5 || thumbMd5).trim(),
    voiceUrl: renderType === 'voice' ? buildVoiceUrl(item) : '',
    voiceDuration: Number(attachment?.duration || 0),
    voiceRead: true,
    fileSize: Number(attachment?.fullSize || 0),
    fileMd5: fullMd5,
    sourceUsername: sourceChatUsername(item),
    locationLat: location?.latitude || '',
    locationLng: location?.longitude || '',
    locationPoiname: location?.poiname || attachment?.title || '',
    locationLabel: location?.label || location?.address || attachment?.description || '',
  }
  return message
}

const favoriteMessages = (item) => {
  if (Number(item?.type) === 14) {
    const original = item?.originalMessage && typeof item.originalMessage === 'object' ? item.originalMessage : {}
    return [{
      ...original,
      id: `${favoriteKey(item)}-chat-history`,
      type: 49,
      renderType: 'chatHistory',
      isSent: false,
      title: String(original.title || item.title || '聊天记录'),
      content: String(original.content || item.summary || '聊天记录'),
      _favoriteItem: item,
    }]
  }
  const messages = (item.textBlocks || []).map((text, index) => ({
    id: `${favoriteKey(item)}-text-${index}`,
    type: 1,
    renderType: 'text',
    isSent: false,
    content: String(text || ''),
  }))
  for (const [index, attachment] of (item.attachments || []).entries()) {
    messages.push(attachmentMessage(item, attachment, index))
  }
  if (!messages.length) {
    messages.push({
      id: `${favoriteKey(item)}-fallback`,
      type: item?.type || 0,
      renderType: 'text',
      isSent: false,
      content: String(item?.summary || item?.title || item?.typeLabel || '收藏内容'),
    })
  }
  return messages
}

const formatFileSize = (value) => {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes >= 10240 ? 0 : 1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

const getVoiceDurationInSeconds = (duration) => {
  const value = Number(duration || 0)
  if (!Number.isFinite(value) || value <= 0) return 0
  return Math.max(1, Math.round(value > 1000 ? value / 1000 : value))
}

const getVoiceWidth = (duration) => `${Math.min(230, 86 + getVoiceDurationInSeconds(duration) * 3)}px`

const setVoiceRef = (id, element) => {
  if (element) voiceRefs.set(String(id), element)
  else voiceRefs.delete(String(id))
}

const playVoice = async (message) => {
  const id = String(message?.id || '')
  const audio = voiceRefs.get(id)
  if (!audio) return
  for (const [otherId, otherAudio] of voiceRefs.entries()) {
    if (otherId !== id && !otherAudio.paused) otherAudio.pause()
  }
  if (!audio.paused) {
    audio.pause()
    playingVoiceId.value = ''
    return
  }
  audio.onended = () => { playingVoiceId.value = '' }
  audio.onerror = () => { playingVoiceId.value = '' }
  try {
    await audio.play()
    playingVoiceId.value = id
  } catch {
    playingVoiceId.value = ''
  }
}

const openImagePreview = (url) => {
  if (!url) return
  Object.assign(preview, { kind: 'image', url, poster: '' })
}

const openVideoPreview = (url, poster = '') => {
  if (!url) return
  Object.assign(preview, { kind: 'video', url, poster })
}

const closePreview = () => Object.assign(preview, { kind: '', url: '', poster: '' })

const onFileClick = async (message) => {
  if (!message?.fileMd5) return
  try {
    await api.openChatMediaFolder({
      account: selectedAccount.value,
      username: message?.sourceUsername || '',
      kind: 'file',
      md5: message.fileMd5,
    })
  } catch {
    // The file card remains useful even when the original attachment is not cached locally.
  }
}

const historyState = useChatHistoryWindows({
  api,
  apiBase,
  selectedAccount,
  selectedContact: historySelectedContact,
  openImagePreview,
  openVideoPreview,
  buildVoiceUrl: (record, fallbackUrl) => {
    const serverId = String(record?.fromnewmsgid || '').trim()
    if (!/^\d+$/.test(serverId) || !selectedAccount.value) return fallbackUrl
    return `${apiBase}/favorites/media/voice?${new URLSearchParams({
      account: selectedAccount.value,
      server_id: serverId,
    }).toString()}`
  },
})

const openFavoriteChatHistory = (message) => {
  const item = message?._favoriteItem || {}
  historySelectedContact.value = { username: sourceChatUsername(item) }
  historyState.openChatHistoryModal(message)
}

const copyTextToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(String(text || ''))
    return true
  } catch {
    return false
  }
}

const messageState = reactive({
  privacyMode,
  selectedContact: computed(() => ({ username: '' })),
  parseTextWithEmoji,
  formatFileSize,
  openImagePreview,
  openVideoPreview,
  onFileClick,
  openMediaContextMenu: () => {},
  getVoiceWidth,
  getVoiceDurationInSeconds,
  playVoice,
  setVoiceRef,
  playingVoiceId,
  shouldShowImageLargeReload: () => false,
  shouldShowEmojiDownload: () => false,
  onEmojiDownloadClick: () => {},
  onMessageVideoThumbRenderError: (message) => {
    const candidates = Array.isArray(message?._videoThumbCandidates) ? message._videoThumbCandidates : []
    const next = Math.max(0, Number(message?._videoThumbCandidateIndex || 0)) + 1
    if (message && next < candidates.length) {
      message._videoThumbCandidateIndex = next
      message.videoThumbUrl = candidates[next]
      message._videoThumbRenderError = false
    }
  },
  openChatHistoryModal: openFavoriteChatHistory,
  getChatHistoryPreviewLines,
  highlightServerIdStr: '',
  highlightMessageId: '',
  contactProfileCardOpen: false,
  contactProfileCardMessageId: '',
  onMessageAvatarMouseEnter: () => {},
  onMessageAvatarMouseLeave: () => {},
  isMentionContactProfileCardForMessage: () => false,
  onAvatarError: () => {},
})

const historyOverlayState = {
  ...historyState,
  privacyMode,
  selectedContact: historySelectedContact,
  parseTextWithEmoji,
  formatFileSize,
  openImagePreview,
  openVideoPreview,
  onFileClick,
  openMediaContextMenu: () => {},
  getVoiceWidth,
  getVoiceDurationInSeconds,
  playVoice,
  setVoiceRef,
  playingVoiceId,
  shouldShowImageLargeReload: () => false,
  shouldShowEmojiDownload: () => false,
  onEmojiDownloadClick: () => {},
  openChatHistoryModal: openFavoriteChatHistory,
  getChatHistoryPreviewLines,
  copyTextToClipboard,
}

const resetItems = () => {
  items.value = []
  total.value = 0
  hasMore.value = false
  error.value = ''
}

const loadItems = async (options = {}) => {
  await chatAccounts.ensureLoaded()
  if (!selectedAccount.value) {
    requestId += 1
    resetItems()
    databaseTotal.value = 0
    tags.value = []
    typeCounts.value = {}
    error.value = '未找到可用账号，先完成检测或导入。'
    return
  }

  const append = !!options.append
  const rid = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response = await api.listFavorites({
      account: selectedAccount.value,
      q: keyword.value || '',
      kind: kindFilter.value,
      tagId: Number(tagFilter.value || 0),
      limit: PAGE_SIZE,
      offset: append ? items.value.length : 0,
    })
    if (rid !== requestId) return
    const next = Array.isArray(response?.items) ? response.items : []
    items.value = append ? [...items.value, ...next] : next
    total.value = Number(response?.total || 0)
    databaseTotal.value = Number(response?.databaseTotal || 0)
    hasMore.value = !!response?.hasMore
    tags.value = Array.isArray(response?.tags) ? response.tags : []
    typeCounts.value = response?.typeCounts && typeof response.typeCounts === 'object' ? response.typeCounts : {}
  } catch (loadError) {
    if (rid === requestId) {
      if (!append) resetItems()
      error.value = loadError?.message || '加载收藏失败'
    }
  } finally {
    if (rid === requestId) loading.value = false
  }
}

watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => { void loadItems() }, 250)
})
watch(kindFilter, () => { void loadItems() })
watch(tagFilter, () => { void loadItems() })
watch(() => selectedAccount.value, () => { void loadItems() })

onMounted(async () => {
  document.addEventListener('mousemove', historyState.onFloatingWindowMouseMove)
  document.addEventListener('mouseup', historyState.onFloatingWindowMouseUp)
  document.addEventListener('touchmove', historyState.onFloatingWindowMouseMove)
  document.addEventListener('touchend', historyState.onFloatingWindowMouseUp)
  document.addEventListener('touchcancel', historyState.onFloatingWindowMouseUp)
  privacyStore.init()
  await chatAccounts.ensureLoaded()
  await loadItems()
})

onBeforeUnmount(() => {
  if (keywordTimer) clearTimeout(keywordTimer)
  document.removeEventListener('mousemove', historyState.onFloatingWindowMouseMove)
  document.removeEventListener('mouseup', historyState.onFloatingWindowMouseUp)
  document.removeEventListener('touchmove', historyState.onFloatingWindowMouseMove)
  document.removeEventListener('touchend', historyState.onFloatingWindowMouseUp)
  document.removeEventListener('touchcancel', historyState.onFloatingWindowMouseUp)
  for (const audio of voiceRefs.values()) audio.pause()
  voiceRefs.clear()
})
</script>

<style scoped>
.favorites-chat { background: var(--chat-main-bg, #ededed); }

.favorites-toolbar {
  position: sticky;
  z-index: 3;
  top: 0;
  display: flex;
  min-height: 52px;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 7px 18px;
  border-bottom: 1px solid var(--wx-line);
  background: color-mix(in srgb, var(--wx-panel) 96%, transparent);
  backdrop-filter: blur(10px);
}

.favorites-types { display: flex; min-width: 0; gap: 3px; overflow-x: auto; scrollbar-width: none; }
.favorites-types::-webkit-scrollbar { display: none; }
.favorites-types button {
  display: flex;
  min-height: 34px;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 0;
  border-radius: 6px;
  color: var(--wx-text-muted);
  background: transparent;
  cursor: pointer;
  font-size: 13px;
}
.favorites-types button:hover { background: var(--wx-muted-surface); }
.favorites-types button.is-active { color: var(--wx-green-dark); background: var(--wx-green-soft); }
.favorites-types__count { min-width: 18px; color: inherit; font-size: 11px; font-variant-numeric: tabular-nums; opacity: 0.78; }

.favorites-tag-filter {
  position: relative;
  display: flex;
  width: 148px;
  height: 34px;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  border: 1px solid var(--wx-line);
  border-radius: 6px;
  color: var(--wx-text-muted);
  background: var(--wx-panel);
}
.favorites-tag-filter > i { flex: 0 0 auto; font-size: 11px; }
.favorites-tag-filter > i:last-child { pointer-events: none; }
.favorites-tag-filter select { min-width: 0; flex: 1; border: 0; outline: 0; color: var(--wx-text-secondary); background: transparent; appearance: none; font-size: 12px; }
.favorites-tag-filter.is-disabled { opacity: 0.55; }

.favorites-message-list { padding: 22px 24px 12px; }
.favorite-message-row { display: grid; grid-template-columns: 42px minmax(0, 1fr); align-items: start; gap: 11px; margin-bottom: 24px; }
.favorite-avatar {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  overflow: hidden;
  border: 0;
  border-radius: 5px;
  color: #fff;
  background: #607b68;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
}
.favorite-avatar:disabled { cursor: default; }
.favorite-avatar img { width: 100%; height: 100%; object-fit: cover; }
.favorite-message-body { min-width: 0; }
.favorite-message-head { display: flex; max-width: 620px; align-items: baseline; justify-content: space-between; gap: 14px; margin-bottom: 6px; }
.favorite-sender-line { display: flex; min-width: 0; align-items: baseline; gap: 8px; }
.favorite-sender-line strong { overflow: hidden; color: #576b95; font-size: 12px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.favorite-sender-line span { overflow: hidden; color: var(--wx-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.favorite-message-head time { flex: 0 0 auto; color: var(--wx-text-muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.favorite-content-stack { display: flex; max-width: 100%; align-items: flex-start; flex-direction: column; gap: 7px; }
.favorite-preview { position: fixed; z-index: 12500; inset: 0; display: grid; place-items: center; padding: 50px; background: rgba(0, 0, 0, 0.82); }
.favorite-preview img,
.favorite-preview video { display: block; max-width: min(1100px, 94vw); max-height: 90vh; object-fit: contain; }
.favorite-preview__close { position: absolute; top: 18px; right: 18px; display: grid; width: 38px; height: 38px; place-items: center; border: 0; border-radius: 50%; color: #fff; background: rgba(255, 255, 255, 0.14); cursor: pointer; }

@media (max-width: 760px) {
  .records-masthead__actions { display: grid; width: 100%; grid-template-columns: minmax(0, 1fr) 36px 36px; }
  .records-masthead__actions .records-search { width: auto; min-width: 0; }
  .favorites-toolbar { align-items: stretch; flex-direction: column; gap: 6px; padding: 7px 11px; }
  .favorites-tag-filter { width: 100%; }
  .favorites-message-list { padding: 18px 11px 8px; }
  .favorite-message-row { grid-template-columns: 36px minmax(0, 1fr); gap: 9px; margin-bottom: 20px; }
  .favorite-avatar { width: 34px; height: 34px; }
  .favorite-message-head { align-items: flex-start; flex-direction: column; gap: 1px; }
  .favorite-message-head time { margin-left: 0; }
  .favorite-preview { padding: 42px 10px 10px; }
}
</style>
