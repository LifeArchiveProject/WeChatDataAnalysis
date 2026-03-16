<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <SessionListPanel :state="chatState" />

    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <div class="flex-1 flex min-h-0">
        <ConversationPane :state="chatState" />
      </div>
    </div>

    <ChatOverlays :state="chatState" />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useApi } from '~/composables/useApi'
import { createEmptySearchContext, useChatSearch } from '~/composables/chat/useChatSearch'
import { useChatSessions } from '~/composables/chat/useChatSessions'
import { useChatMessages } from '~/composables/chat/useChatMessages'
import { useChatExport } from '~/composables/chat/useChatExport'
import { useChatEditing } from '~/composables/chat/useChatEditing'
import { useChatHistoryWindows } from '~/composables/chat/useChatHistoryWindows'
import { DESKTOP_SETTING_AUTO_REALTIME_KEY, readLocalBoolSetting } from '~/lib/desktop-settings'
import {
  formatCount as formatSearchCount,
  formatMessageFullTime,
  formatTransferAmount,
  getChatHistoryPreviewLines,
  getRedPacketText,
  getTransferTitle,
  highlightKeyword,
  isTransferOverdue,
  isTransferReturned
} from '~/lib/chat/formatters'
import { parseTextWithEmoji } from '~/lib/wechat-emojis'
import { heatColor } from '~/lib/wrapped/heatmap'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { useChatRealtimeStore } from '~/stores/chatRealtime'
import { usePrivacyStore } from '~/stores/privacy'

definePageMeta({
  key: 'chat'
})

useHead({
  title: '??????? - ????????'
})

const route = useRoute()
const api = useApi()
const apiBase = useApiBase()

const routeUsername = computed(() => {
  const raw = route.params.username
  return (Array.isArray(raw) ? raw[0] : raw) || ''
})

const buildChatPath = (username) => {
  return username ? `/chat/${encodeURIComponent(username)}` : '/chat'
}

const privacyStore = usePrivacyStore()
privacyStore.init()
const { privacyMode } = storeToRefs(privacyStore)

const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const realtimeStore = useChatRealtimeStore()
const {
  enabled: realtimeEnabled,
  toggleSeq: realtimeToggleSeq,
  lastToggleAction: realtimeLastToggleAction,
  changeSeq: realtimeChangeSeq
} = storeToRefs(realtimeStore)

const desktopAutoRealtime = ref(false)
if (process.client) {
  desktopAutoRealtime.value = readLocalBoolSetting(DESKTOP_SETTING_AUTO_REALTIME_KEY, false)
}

const searchContext = ref(createEmptySearchContext())

const sessionState = useChatSessions({
  chatAccounts,
  selectedAccount,
  realtimeEnabled,
  api
})

const {
  availableAccounts,
  contacts,
  selectedContact,
  searchQuery,
  filteredContacts,
  isLoadingContacts,
  contactsError,
  showSearchAccountSwitcher,
  sessionListWidth,
  sessionListResizing,
  loadContacts,
  loadSessionsForSelectedAccount,
  refreshSessionsForSelectedAccount,
  onSessionListResizerPointerDown,
  stopSessionListResize,
  resetSessionListWidth
} = sessionState

const messageState = useChatMessages({
  api,
  apiBase,
  selectedAccount,
  selectedContact,
  realtimeStore,
  realtimeEnabled,
  desktopAutoRealtime,
  privacyMode,
  searchContext
})

const {
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
  highlightServerIdStr,
  highlightMessageId,
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
  loadMessages,
  loadMoreMessages,
  refreshSelectedMessages,
  queueRealtimeRefresh,
  tryEnableRealtimeAuto,
  resetMessageState,
  onAvatarError,
  contactProfileCardOpen,
  contactProfileCardMessageId,
  contactProfileLoading,
  contactProfileError,
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
  clearContactProfileHoverHideTimer,
  closeContactProfileCard,
  onMessageAvatarMouseEnter,
  onMessageAvatarMouseLeave,
  onContactCardMouseEnter,
  toggleReverseMessageSides
} = messageState

let exitSearchContext = async () => {}

const selectContact = async (contact, options = {}) => {
  if (!contact) return
  const nextUsername = contact?.username || ''
  if (searchContext.value?.active && searchContext.value.username && searchContext.value.username !== nextUsername) {
    await exitSearchContext()
  }
  selectedContact.value = contact
  if (!nextUsername) return

  if (!options.skipLoadMessages) {
    loadMessages({ username: nextUsername, reset: true })
  }

  if (options.syncRoute !== false && nextUsername) {
    const current = routeUsername.value || ''
    if (current !== nextUsername) {
      await navigateTo(buildChatPath(nextUsername), { replace: options.replaceRoute !== false })
    }
  }
}

const applyRouteSelection = async () => {
  if (!contacts.value || contacts.value.length === 0) {
    selectedContact.value = null
    return
  }

  const requested = routeUsername.value || ''
  if (requested) {
    const matched = contacts.value.find((contact) => contact.username === requested)
    if (matched) {
      if (selectedContact.value?.username !== matched.username) {
        await selectContact(matched, { syncRoute: false })
      }
      return
    }
  }

  await selectContact(contacts.value[0], { syncRoute: true, replaceRoute: true })
}

const searchState = useChatSearch({
  api,
  heatColor,
  contacts,
  selectedAccount,
  selectedContact,
  privacyMode,
  allMessages,
  messagesMeta,
  messages,
  messageContainerRef,
  messagePageSize,
  hasMoreMessages,
  isLoadingMessages,
  normalizeMessage,
  updateJumpToBottomState,
  scrollToMessageId,
  flashMessage,
  highlightMessageId,
  searchContext,
  selectContact,
  loadMoreMessages
})

exitSearchContext = searchState.exitSearchContext

let locateServerIdTimer = null
const locateMessageByServerId = async (serverIdStr) => {
  if (!process.client) return false
  const target = String(serverIdStr || '').trim()
  if (!target) return false
  if (!selectedContact.value) return false

  for (let i = 0; i < 30; i++) {
    const list = messages.value || []
    const found = list.find((message) => String(message?.serverIdStr || message?.serverId || '').trim() === target)
    if (found) {
      await nextTick()
      const container = messageContainerRef.value
      const element = container?.querySelector?.(`[data-server-id="${target}"]`)
      if (element && typeof element.scrollIntoView === 'function') {
        element.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
      highlightServerIdStr.value = target
      if (locateServerIdTimer) clearTimeout(locateServerIdTimer)
      locateServerIdTimer = setTimeout(() => {
        highlightServerIdStr.value = ''
        locateServerIdTimer = null
      }, 1800)
      return true
    }

    if (!hasMoreMessages.value) break
    if (isLoadingMessages.value) {
      await new Promise((resolve) => setTimeout(resolve, 120))
      continue
    }
    await loadMoreMessages()
  }

  return false
}

const exportState = useChatExport({
  api,
  apiBase,
  contacts,
  selectedAccount,
  selectedContact,
  privacyMode
})

const historyState = useChatHistoryWindows({
  api,
  apiBase,
  selectedAccount,
  selectedContact,
  openImagePreview,
  openVideoPreview
})

const editingState = useChatEditing({
  api,
  selectedAccount,
  selectedContact,
  refreshSelectedMessages,
  normalizeMessage,
  allMessages,
  locateMessageByServerId
})

const {
  contextMenu,
  closeContextMenu,
  closeMessageEditModal,
  closeMessageFieldsModal
} = editingState

const {
  floatingWindows,
  closeTopFloatingWindow,
  closeChatHistoryModal,
  chatHistoryModalVisible,
  onFloatingWindowMouseMove,
  onFloatingWindowMouseUp
} = historyState

const { stopExportPolling } = exportState

const resetAccountScopedState = () => {
  resetMessageState()
  searchState.resetSearchState()
  closeContextMenu()
  closeMessageEditModal()
  closeMessageFieldsModal()
  clearContactProfileHoverHideTimer()
  closeContactProfileCard()
}

let realtimeSessionsRefreshFuture = null
let realtimeSessionsRefreshQueued = false

const queueRealtimeSessionsRefresh = () => {
  if (realtimeSessionsRefreshFuture) {
    realtimeSessionsRefreshQueued = true
    return
  }

  realtimeSessionsRefreshFuture = refreshSessionsForSelectedAccount({ sourceOverride: 'realtime' }).finally(() => {
    realtimeSessionsRefreshFuture = null
    if (realtimeSessionsRefreshQueued) {
      realtimeSessionsRefreshQueued = false
      queueRealtimeSessionsRefresh()
    }
  })
}

const onAccountChange = async () => {
  try {
    isLoadingContacts.value = true
    contactsError.value = ''
    await loadSessionsForSelectedAccount()
  } catch (error) {
    contactsError.value = error?.message || '???????'
  } finally {
    isLoadingContacts.value = false
  }

  resetAccountScopedState()
  await applyRouteSelection()
}

const onGlobalClick = (event) => {
  if (contextMenu.value.visible) closeContextMenu()
  if (searchState.messageSearchSenderDropdownOpen.value) {
    const element = searchState.messageSearchSenderDropdownRef.value
    const target = event?.target
    if (element && target && !element.contains(target)) {
      searchState.closeMessageSearchSenderDropdown()
    }
  }
}

const onGlobalKeyDown = (event) => {
  if (!process.client) return

  const key = String(event?.key || '')
  const lower = key.toLowerCase()

  if ((event.ctrlKey || event.metaKey) && lower === 'f') {
    event.preventDefault()
    searchState.openMessageSearch()
    return
  }

  if (key === 'Escape') {
    if (contextMenu.value.visible) closeContextMenu()
    if (previewImageUrl.value) closeImagePreview()
    if (previewVideoUrl.value) closeVideoPreview()
    if (Array.isArray(floatingWindows.value) && floatingWindows.value.length) closeTopFloatingWindow()
    if (chatHistoryModalVisible.value) closeChatHistoryModal()
    if (contactProfileCardOpen.value) {
      clearContactProfileHoverHideTimer()
      closeContactProfileCard()
    }
    if (searchState.messageSearchSenderDropdownOpen.value) searchState.closeMessageSearchSenderDropdown()
    if (searchState.messageSearchOpen.value) searchState.closeMessageSearch()
    if (searchState.timeSidebarOpen.value) searchState.closeTimeSidebar()
    if (searchContext.value?.active) exitSearchContext()
  }
}

onMounted(async () => {
  if (!process.client) return

  document.addEventListener('click', onGlobalClick)
  document.addEventListener('keydown', onGlobalKeyDown)
  document.addEventListener('mousemove', onFloatingWindowMouseMove)
  document.addEventListener('mouseup', onFloatingWindowMouseUp)
  document.addEventListener('touchmove', onFloatingWindowMouseMove)
  document.addEventListener('touchend', onFloatingWindowMouseUp)
  document.addEventListener('touchcancel', onFloatingWindowMouseUp)

  await loadContacts()
  await applyRouteSelection()
  await tryEnableRealtimeAuto()
})

onUnmounted(() => {
  if (!process.client) return

  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onGlobalKeyDown)
  document.removeEventListener('mousemove', onFloatingWindowMouseMove)
  document.removeEventListener('mouseup', onFloatingWindowMouseUp)
  document.removeEventListener('touchmove', onFloatingWindowMouseMove)
  document.removeEventListener('touchend', onFloatingWindowMouseUp)
  document.removeEventListener('touchcancel', onFloatingWindowMouseUp)

  if (locateServerIdTimer) clearTimeout(locateServerIdTimer)
  locateServerIdTimer = null
  stopSessionListResize()
  stopExportPolling()
})

watch(realtimeChangeSeq, () => {
  queueRealtimeRefresh()
  queueRealtimeSessionsRefresh()
})

watch(realtimeToggleSeq, async () => {
  const action = String(realtimeLastToggleAction.value || '')
  if (action === 'enabled') {
    await refreshSessionsForSelectedAccount({ sourceOverride: 'realtime' })
    if (selectedContact.value?.username) {
      await refreshSelectedMessages()
    }
    return
  }

  if (action === 'disabled') {
    await refreshSessionsForSelectedAccount({ sourceOverride: '' })
    if (selectedContact.value?.username) {
      await refreshSelectedMessages()
    }
  }
})

watch(
  () => selectedContact.value?.username,
  (username) => {
    realtimeStore.setPriorityUsername(username || '')
  }
)

watch(messageTypeFilter, async (next, prev) => {
  if (String(next || '') === String(prev || '')) return
  if (!selectedContact.value?.username) return
  await refreshSelectedMessages()
})

watch(
  routeUsername,
  async () => {
    if (!process.client) return
    if (isLoadingContacts.value) return
    if (!contacts.value.length) return
    await applyRouteSelection()
  }
)

const chatState = {
  chatAccounts,
  selectedAccount,
  availableAccounts,
  contacts,
  selectedContact,
  filteredContacts,
  searchQuery,
  showSearchAccountSwitcher,
  isLoadingContacts,
  contactsError,
  sessionListWidth,
  sessionListResizing,
  onSessionListResizerPointerDown,
  resetSessionListWidth,
  selectContact,
  onAccountChange,
  privacyMode,
  parseTextWithEmoji,
  formatMessageFullTime,
  highlightKeyword,
  formatCount: formatSearchCount,
  formatTransferAmount,
  getChatHistoryPreviewLines,
  getRedPacketText,
  getTransferTitle,
  isTransferOverdue,
  isTransferReturned,
  ...messageState,
  ...searchState,
  ...exportState,
  ...editingState,
  ...historyState
}
</script>
