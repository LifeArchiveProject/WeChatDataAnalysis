import { nextTick, ref, toRaw } from 'vue'
import { showErrorAlert } from '~/composables/useErrorNotice'

const CONTEXT_MENU_MARGIN = 8
const MODIFY_TEXT_UNAVAILABLE_MESSAGE = '当前环境无法完成此操作，请联系开发者协助处理。'

const initialContextMenu = () => ({
  visible: false,
  x: 0,
  y: 0,
  message: null,
  kind: '',
  disabled: false
})

export const useChatEditing = ({
  api,
  selectedAccount,
  selectedContact,
  locateMessageByServerId
}) => {
  const contextMenu = ref(initialContextMenu())
  const contextMenuElement = ref(null)
  const modifyTextUnavailableDialogOpen = ref(false)

  const closeContextMenu = () => {
    contextMenu.value = initialContextMenu()
  }

  const repositionContextMenu = () => {
    if (!process.client || !contextMenu.value.visible) return
    const menuEl = contextMenuElement.value
    if (!menuEl) return

    const rect = menuEl.getBoundingClientRect()
    const viewportWidth = Math.max(window.innerWidth || 0, document.documentElement?.clientWidth || 0)
    const viewportHeight = Math.max(window.innerHeight || 0, document.documentElement?.clientHeight || 0)
    if (!viewportWidth || !viewportHeight) return

    const maxX = Math.max(CONTEXT_MENU_MARGIN, viewportWidth - rect.width - CONTEXT_MENU_MARGIN)
    const maxY = Math.max(CONTEXT_MENU_MARGIN, viewportHeight - rect.height - CONTEXT_MENU_MARGIN)
    const currentX = Number(contextMenu.value.x || 0)
    const currentY = Number(contextMenu.value.y || 0)
    const nextX = Math.min(Math.max(currentX, CONTEXT_MENU_MARGIN), maxX)
    const nextY = Math.min(Math.max(currentY, CONTEXT_MENU_MARGIN), maxY)

    if (nextX !== currentX || nextY !== currentY) {
      contextMenu.value = {
        ...contextMenu.value,
        x: nextX,
        y: nextY
      }
    }
  }

  const scheduleContextMenuReposition = () => {
    if (!process.client) return
    void nextTick(() => {
      const run = () => repositionContextMenu()
      if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(run)
      } else {
        run()
      }
    })
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
      disabled
    }
    scheduleContextMenuReposition()
  }

  const isLikelyTextMessage = (message) => {
    if (!message) return false
    const renderType = String(message?.renderType || '').trim()
    if (renderType && renderType !== 'text') return false
    if (message?.imageUrl || message?.emojiUrl || message?.videoUrl || message?.voiceUrl) return false
    return true
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
      if (!ok) showErrorAlert('复制失败：无法写入剪贴板')
    } catch {
      showErrorAlert('复制失败')
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
      if (!ok) showErrorAlert('复制失败：无法写入剪贴板')
    } catch {
      showErrorAlert('复制失败')
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

  const onEditMessageClick = () => {
    const message = contextMenu.value.message
    closeContextMenu()
    if (!isLikelyTextMessage(message)) return
    modifyTextUnavailableDialogOpen.value = true
  }

  const closeModifyTextUnavailableDialog = () => {
    modifyTextUnavailableDialogOpen.value = false
  }

  const onLocateQuotedMessageClick = async () => {
    const message = contextMenu.value.message
    if (!message?.quoteServerId) return
    closeContextMenu()
    const ok = await locateMessageByServerId(message.quoteServerId)
    if (!ok && process.client) {
      showErrorAlert('定位引用消息失败')
    }
  }

  return {
    contextMenu,
    contextMenuElement,
    modifyTextUnavailableDialogOpen,
    modifyTextUnavailableMessage: MODIFY_TEXT_UNAVAILABLE_MESSAGE,
    closeContextMenu,
    closeModifyTextUnavailableDialog,
    openMediaContextMenu,
    isLikelyTextMessage,
    copyTextToClipboard,
    onCopyMessageTextClick,
    onCopyMessageJsonClick,
    onOpenFolderClick,
    onEditMessageClick,
    onLocateQuotedMessageClick
  }
}
