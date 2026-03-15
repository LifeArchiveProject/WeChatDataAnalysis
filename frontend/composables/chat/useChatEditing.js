import { ref, toRaw } from 'vue'

const initialContextMenu = () => ({
  visible: false,
  x: 0,
  y: 0,
  message: null,
  kind: '',
  disabled: false,
  editStatus: null,
  editStatusLoading: false
})

const initialMessageEditModal = () => ({
  open: false,
  loading: false,
  saving: false,
  error: '',
  mode: 'content',
  sessionId: '',
  messageId: '',
  draft: '',
  rawRow: null
})

const initialMessageFieldsModal = () => ({
  open: false,
  loading: false,
  saving: false,
  error: '',
  sessionId: '',
  messageId: '',
  unsafe: false,
  editsJson: '',
  rawRow: null
})

export const useChatEditing = ({
  api,
  selectedAccount,
  selectedContact,
  refreshSelectedMessages,
  normalizeMessage,
  allMessages,
  locateMessageByServerId
}) => {
  const contextMenu = ref(initialContextMenu())
  const messageEditModal = ref(initialMessageEditModal())
  const messageFieldsModal = ref(initialMessageFieldsModal())

  const closeContextMenu = () => {
    contextMenu.value = initialContextMenu()
  }

  const loadContextMenuEditStatus = async (params) => {
    if (!process.client) return
    const account = String(params?.account || '').trim()
    const username = String(params?.username || '').trim()
    const messageId = String(params?.message_id || '').trim()
    if (!account || !username || !messageId) {
      contextMenu.value.editStatusLoading = false
      return
    }

    try {
      const response = await api.getChatEditStatus({ account, username, message_id: messageId })
      const current = String(contextMenu.value?.message?.id || '').trim()
      if (contextMenu.value.visible && current === messageId) {
        contextMenu.value.editStatus = response || { modified: false }
      }
    } catch {
      const current = String(contextMenu.value?.message?.id || '').trim()
      if (contextMenu.value.visible && current === messageId) {
        contextMenu.value.editStatus = null
      }
    } finally {
      const current = String(contextMenu.value?.message?.id || '').trim()
      if (contextMenu.value.visible && current === messageId) {
        contextMenu.value.editStatusLoading = false
      }
    }
  }

  const openMediaContextMenu = (event, message, kind) => {
    if (!process.client) return
    event.preventDefault()
    event.stopPropagation()

    let actualKind = kind
    let disabled = true
    if (kind === 'voice') {
      disabled = !(message?.serverIdStr || message?.serverId)
    } else if (kind === 'file') {
      disabled = !message?.fileMd5
    } else if (kind === 'image') {
      disabled = !(message?.imageMd5 || message?.imageFileId)
    } else if (kind === 'emoji') {
      disabled = !message?.emojiMd5
    } else if (kind === 'video') {
      if (message?.videoMd5 || message?.videoFileId) {
        disabled = false
        actualKind = 'video'
      } else if (message?.videoThumbMd5 || message?.videoThumbFileId) {
        disabled = false
        actualKind = 'video_thumb'
      }
    }

    contextMenu.value = {
      visible: true,
      x: event.clientX,
      y: event.clientY,
      message,
      kind: actualKind,
      disabled,
      editStatus: null,
      editStatusLoading: false
    }

    try {
      const account = String(selectedAccount.value || '').trim()
      const username = String(selectedContact.value?.username || '').trim()
      const messageId = String(message?.id || '').trim()
      if (account && username && messageId) {
        contextMenu.value.editStatusLoading = true
        void loadContextMenuEditStatus({ account, username, message_id: messageId })
      }
    } catch {}
  }

  const prettyJson = (value) => {
    try {
      return JSON.stringify(value ?? null, null, 2)
    } catch {
      return String(value ?? '')
    }
  }

  const isLikelyTextMessage = (message) => {
    if (!message) return false
    const renderType = String(message?.renderType || '').trim()
    if (renderType && renderType !== 'text') return false
    if (message?.imageUrl || message?.emojiUrl || message?.videoUrl || message?.voiceUrl) return false
    return true
  }

  const closeMessageEditModal = () => {
    messageEditModal.value = initialMessageEditModal()
  }

  const openMessageEditModal = async ({ message, mode }) => {
    if (!process.client) return
    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(selectedContact.value?.username || '').trim()
    const messageId = String(message?.id || '').trim()
    if (!account || !sessionId || !messageId) return

    const resolvedMode = mode === 'raw' ? 'raw' : 'content'
    const initialDraft = resolvedMode === 'content'
      ? (typeof message?.content === 'string' ? message.content : String(message?.content ?? ''))
      : ''

    messageEditModal.value = {
      open: true,
      loading: true,
      saving: false,
      error: '',
      mode: resolvedMode,
      sessionId,
      messageId,
      draft: initialDraft,
      rawRow: null
    }

    try {
      const response = await api.getChatMessageRaw({ account, username: sessionId, message_id: messageId })
      const row = response?.row || null
      const rawContent = row?.message_content
      const rawDraft = typeof rawContent === 'string' ? rawContent : String(rawContent ?? '')
      const draft = resolvedMode === 'raw' ? rawDraft : messageEditModal.value.draft
      messageEditModal.value = { ...messageEditModal.value, loading: false, rawRow: row, draft }
    } catch (error) {
      messageEditModal.value = { ...messageEditModal.value, loading: false, error: error?.message || '加载失败' }
    }
  }

  const saveMessageEditModal = async () => {
    if (!process.client) return
    if (messageEditModal.value.saving || messageEditModal.value.loading) return

    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(messageEditModal.value.sessionId || '').trim()
    const messageId = String(messageEditModal.value.messageId || '').trim()
    if (!account || !sessionId || !messageId) return

    messageEditModal.value = { ...messageEditModal.value, saving: true, error: '' }
    try {
      const response = await api.editChatMessage({
        account,
        session_id: sessionId,
        message_id: messageId,
        edits: {
          message_content: String(messageEditModal.value.draft ?? '')
        },
        unsafe: false
      })

      if (response?.updated_message) {
        try {
          const updated = normalizeMessage(response.updated_message)
          const username = String(selectedContact.value?.username || '').trim()
          const list = allMessages.value[username] || []
          const index = list.findIndex((message) => String(message?.id || '') === String(updated?.id || ''))
          if (index >= 0) {
            const next = [...list]
            next[index] = updated
            allMessages.value = { ...allMessages.value, [username]: next }
          } else {
            await refreshSelectedMessages()
          }
        } catch {
          await refreshSelectedMessages()
        }
      } else {
        await refreshSelectedMessages()
      }

      closeMessageEditModal()
    } catch (error) {
      messageEditModal.value = { ...messageEditModal.value, saving: false, error: error?.message || '保存失败' }
      return
    } finally {
      messageEditModal.value = { ...messageEditModal.value, saving: false }
    }
  }

  const closeMessageFieldsModal = () => {
    messageFieldsModal.value = initialMessageFieldsModal()
  }

  const openMessageFieldsModal = async (message) => {
    if (!process.client) return
    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(selectedContact.value?.username || '').trim()
    const messageId = String(message?.id || '').trim()
    if (!account || !sessionId || !messageId) return

    messageFieldsModal.value = {
      open: true,
      loading: true,
      saving: false,
      error: '',
      sessionId,
      messageId,
      unsafe: false,
      editsJson: '',
      rawRow: null
    }

    try {
      const response = await api.getChatMessageRaw({ account, username: sessionId, message_id: messageId })
      const row = response?.row || null
      const seed = {}
      for (const key of ['message_content', 'local_type', 'create_time', 'server_id', 'origin_source', 'source']) {
        if (row && Object.prototype.hasOwnProperty.call(row, key)) seed[key] = row[key]
      }
      messageFieldsModal.value = {
        ...messageFieldsModal.value,
        loading: false,
        rawRow: row,
        editsJson: JSON.stringify(seed, null, 2)
      }
    } catch (error) {
      messageFieldsModal.value = { ...messageFieldsModal.value, loading: false, error: error?.message || '加载失败' }
    }
  }

  const saveMessageFieldsModal = async () => {
    if (!process.client) return
    if (messageFieldsModal.value.saving || messageFieldsModal.value.loading) return

    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(messageFieldsModal.value.sessionId || '').trim()
    const messageId = String(messageFieldsModal.value.messageId || '').trim()
    if (!account || !sessionId || !messageId) return

    let edits = null
    try {
      edits = JSON.parse(String(messageFieldsModal.value.editsJson || '').trim() || 'null')
    } catch {
      messageFieldsModal.value = { ...messageFieldsModal.value, error: 'JSON 格式错误' }
      return
    }
    if (!edits || typeof edits !== 'object' || Array.isArray(edits)) {
      messageFieldsModal.value = { ...messageFieldsModal.value, error: 'edits 必须是 JSON 对象' }
      return
    }
    if (!Object.keys(edits).length) {
      messageFieldsModal.value = { ...messageFieldsModal.value, error: 'edits 不能为空' }
      return
    }

    messageFieldsModal.value = { ...messageFieldsModal.value, saving: true, error: '' }
    try {
      await api.editChatMessage({
        account,
        session_id: sessionId,
        message_id: messageId,
        edits,
        unsafe: !!messageFieldsModal.value.unsafe
      })
      await refreshSelectedMessages()
      closeMessageFieldsModal()
    } catch (error) {
      messageFieldsModal.value = { ...messageFieldsModal.value, saving: false, error: error?.message || '保存失败' }
      return
    } finally {
      messageFieldsModal.value = { ...messageFieldsModal.value, saving: false }
    }
  }

  const copyTextToClipboard = async (text) => {
    if (!process.client) return false

    const value = String(text ?? '').trim()
    if (!value) return false

    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {}

    try {
      const element = document.createElement('textarea')
      element.value = value
      element.setAttribute('readonly', 'true')
      element.style.position = 'fixed'
      element.style.left = '-9999px'
      element.style.top = '-9999px'
      document.body.appendChild(element)
      element.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(element)
      if (ok) return true
    } catch {}

    try {
      window.prompt('复制内容：', value)
      return true
    } catch {
      return false
    }
  }

  const onCopyMessageTextClick = async () => {
    if (!process.client) return
    const message = contextMenu.value.message
    if (!message) return
    try {
      const text = String(message?.content || '').trim()
      if (!text) {
        window.alert('该消息没有可复制的文本')
        return
      }
      const ok = await copyTextToClipboard(text)
      if (!ok) window.alert('复制失败：无法写入剪贴板')
    } catch {
      window.alert('复制失败')
    } finally {
      closeContextMenu()
    }
  }

  const onCopyMessageJsonClick = async () => {
    if (!process.client) return
    const message = contextMenu.value.message
    if (!message) return
    try {
      const raw = toRaw(message) || message
      const json = JSON.stringify(raw, (_key, value) => (typeof value === 'bigint' ? value.toString() : value), 2)
      const ok = await copyTextToClipboard(json)
      if (!ok) window.alert('复制失败：无法写入剪贴板')
    } catch {
      window.alert('复制失败')
    } finally {
      closeContextMenu()
    }
  }

  const onOpenFolderClick = async () => {
    if (contextMenu.value.disabled) return
    const message = contextMenu.value.message
    const kind = contextMenu.value.kind

    try {
      if (!selectedAccount.value || !selectedContact.value?.username) return

      const params = {
        account: selectedAccount.value,
        username: selectedContact.value.username,
        kind
      }

      if (kind === 'voice') {
        params.server_id = message.serverIdStr || message.serverId
      } else if (kind === 'file') {
        params.md5 = message.fileMd5
      } else if (kind === 'image') {
        if (message.imageMd5) params.md5 = message.imageMd5
        else if (message.imageFileId) params.file_id = message.imageFileId
      } else if (kind === 'emoji') {
        params.md5 = message.emojiMd5
      } else if (kind === 'video') {
        params.md5 = message.videoMd5
        if (message.videoFileId) params.file_id = message.videoFileId
      } else if (kind === 'video_thumb') {
        params.md5 = message.videoThumbMd5
        if (message.videoThumbFileId) params.file_id = message.videoThumbFileId
      }

      await api.openChatMediaFolder(params)
    } finally {
      closeContextMenu()
    }
  }

  const onEditMessageClick = async () => {
    const message = contextMenu.value.message
    if (!message) return
    const mode = isLikelyTextMessage(message) ? 'content' : 'raw'
    closeContextMenu()
    await openMessageEditModal({ message, mode })
  }

  const onEditMessageFieldsClick = async () => {
    const message = contextMenu.value.message
    if (!message) return
    closeContextMenu()
    await openMessageFieldsModal(message)
  }

  const onResetEditedMessageClick = async () => {
    if (!process.client) return
    const message = contextMenu.value.message
    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(selectedContact.value?.username || '').trim()
    const messageId = String(message?.id || '').trim()
    if (!message || !account || !sessionId || !messageId) return

    const ok = window.confirm('确认恢复该条消息到首次快照吗？')
    if (!ok) return

    try {
      await api.resetChatEditedMessage({ account, session_id: sessionId, message_id: messageId })
      closeContextMenu()
      await refreshSelectedMessages()
    } catch (error) {
      window.alert(error?.message || '恢复失败')
    } finally {
      closeContextMenu()
    }
  }

  const onRepairMessageSenderAsMeClick = async () => {
    if (!process.client) return
    const message = contextMenu.value.message
    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(selectedContact.value?.username || '').trim()
    const messageId = String(message?.id || '').trim()
    if (!message || !account || !sessionId || !messageId) return

    const ok = window.confirm('确认将该消息修复为“我发送”吗？这会修改 real_sender_id 字段。')
    if (!ok) return

    try {
      await api.repairChatMessageSender({ account, session_id: sessionId, message_id: messageId, mode: 'me' })
      closeContextMenu()
      await refreshSelectedMessages()
    } catch (error) {
      window.alert(error?.message || '修复失败')
    } finally {
      closeContextMenu()
    }
  }

  const onFlipWechatMessageDirectionClick = async () => {
    if (!process.client) return
    const message = contextMenu.value.message
    const account = String(selectedAccount.value || '').trim()
    const sessionId = String(selectedContact.value?.username || '').trim()
    const messageId = String(message?.id || '').trim()
    if (!message || !account || !sessionId || !messageId) return

    const ok = window.confirm(
      '确认反转该消息在微信客户端的左右气泡位置吗？\n\n这会修改 packed_info_data 字段（有风险）。\n可通过“恢复原消息”撤销。'
    )
    if (!ok) return

    try {
      await api.flipChatMessageDirection({ account, session_id: sessionId, message_id: messageId })
      closeContextMenu()
      await refreshSelectedMessages()
    } catch (error) {
      window.alert(error?.message || '反转失败')
    } finally {
      closeContextMenu()
    }
  }

  const onLocateQuotedMessageClick = async () => {
    const message = contextMenu.value.message
    if (!message?.quoteServerId) return
    closeContextMenu()
    const ok = await locateMessageByServerId(message.quoteServerId)
    if (!ok && process.client) {
      window.alert('定位引用消息失败')
    }
  }

  return {
    contextMenu,
    messageEditModal,
    messageFieldsModal,
    closeContextMenu,
    openMediaContextMenu,
    prettyJson,
    isLikelyTextMessage,
    closeMessageEditModal,
    openMessageEditModal,
    saveMessageEditModal,
    closeMessageFieldsModal,
    openMessageFieldsModal,
    saveMessageFieldsModal,
    copyTextToClipboard,
    onCopyMessageTextClick,
    onCopyMessageJsonClick,
    onOpenFolderClick,
    onEditMessageClick,
    onEditMessageFieldsClick,
    onResetEditedMessageClick,
    onRepairMessageSenderAsMeClick,
    onFlipWechatMessageDirectionClick,
    onLocateQuotedMessageClick
  }
}
