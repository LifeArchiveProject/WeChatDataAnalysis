import { computed, ref, watch } from 'vue'
import { reportServerErrorFromResponse } from '~/lib/server-error-logging'
import { toUnixSeconds } from '~/lib/chat/formatters'

export const useChatExport = ({ api, apiBase, contacts, selectedAccount, selectedContact, privacyMode }) => {
  const exportModalOpen = ref(false)
  const isExportCreating = ref(false)
  const exportError = ref('')

  const exportScope = ref('current')
  const exportFormat = ref('json')
  const exportDownloadRemoteMedia = ref(true)
  const exportHtmlPageSize = ref(1000)
  const exportMessageTypeOptions = [
    { value: 'text', label: '文本' },
    { value: 'image', label: '图片' },
    { value: 'emoji', label: '表情' },
    { value: 'video', label: '视频' },
    { value: 'voice', label: '语音' },
    { value: 'chatHistory', label: '聊天记录' },
    { value: 'transfer', label: '转账' },
    { value: 'redPacket', label: '红包' },
    { value: 'file', label: '文件' },
    { value: 'link', label: '链接' },
    { value: 'quote', label: '引用' },
    { value: 'system', label: '系统' },
    { value: 'voip', label: '通话' }
  ]
  const exportMessageTypes = ref(exportMessageTypeOptions.map((item) => item.value))

  const exportStartLocal = ref('')
  const exportEndLocal = ref('')
  const exportFileName = ref('')
  const exportFolder = ref('')
  const exportFolderHandle = ref(null)
  const exportSaveBusy = ref(false)
  const exportSaveMsg = ref('')
  const exportAutoSavedFor = ref('')

  const exportSearchQuery = ref('')
  const exportListTab = ref('all')
  const exportSelectedUsernames = ref([])

  const exportJob = ref(null)
  let exportPollTimer = null
  let exportEventSource = null

  const clamp01 = (value) => Math.min(1, Math.max(0, value))
  const asNumber = (value) => {
    const next = Number(value)
    return Number.isFinite(next) ? next : 0
  }

  const exportOverallPercent = computed(() => {
    const job = exportJob.value
    const progress = job?.progress || {}
    const total = asNumber(progress.conversationsTotal)
    const done = asNumber(progress.conversationsDone)
    if (total <= 0) return 0

    const currentTotal = asNumber(progress.currentConversationMessagesTotal)
    const currentDone = asNumber(progress.currentConversationMessagesExported)
    const currentFraction = currentTotal > 0 ? clamp01(currentDone / currentTotal) : 0
    const overall = clamp01((done + (job?.status === 'running' ? currentFraction : 0)) / total)
    return Math.round(overall * 100)
  })

  const exportCurrentPercent = computed(() => {
    const progress = exportJob.value?.progress || {}
    const total = asNumber(progress.currentConversationMessagesTotal)
    const done = asNumber(progress.currentConversationMessagesExported)
    if (total <= 0) return null
    return Math.round(clamp01(done / total) * 100)
  })

  const normalizeExportSelectedUsernames = (list) => {
    const seen = new Set()
    return (Array.isArray(list) ? list : []).reduce((acc, item) => {
      const username = String(item || '').trim()
      if (!username || seen.has(username)) return acc
      seen.add(username)
      acc.push(username)
      return acc
    }, [])
  }

  const getExportFilteredContacts = ({ tab = exportListTab.value, query = exportSearchQuery.value } = {}) => {
    const normalizedQuery = String(query || '').trim().toLowerCase()
    let list = Array.isArray(contacts.value) ? contacts.value : []

    const normalizedTab = String(tab || 'all')
    if (normalizedTab === 'groups') list = list.filter((contact) => !!contact?.isGroup)
    if (normalizedTab === 'singles') list = list.filter((contact) => !contact?.isGroup)

    if (!normalizedQuery) return list
    return list.filter((contact) => {
      const name = String(contact?.name || '').toLowerCase()
      const username = String(contact?.username || '').toLowerCase()
      return name.includes(normalizedQuery) || username.includes(normalizedQuery)
    })
  }

  const exportFilteredContacts = computed(() => {
    return getExportFilteredContacts()
  })

  const exportContactCounts = computed(() => {
    const list = Array.isArray(contacts.value) ? contacts.value : []
    const total = list.length
    const groups = list.filter((contact) => !!contact?.isGroup).length
    return { total, groups, singles: total - groups }
  })

  const exportSelectedUsernameSet = computed(() => {
    return new Set(normalizeExportSelectedUsernames(exportSelectedUsernames.value))
  })

  const setExportSelectedUsernames = (list) => {
    exportSelectedUsernames.value = normalizeExportSelectedUsernames(list)
  }

  const getExportFilteredUsernames = (tab = exportListTab.value) => {
    return getExportFilteredContacts({ tab })
      .map((contact) => String(contact?.username || '').trim())
      .filter(Boolean)
  }

  const selectExportFilteredContacts = (tab = exportListTab.value) => {
    setExportSelectedUsernames(getExportFilteredUsernames(tab))
  }

  const clearExportFilteredContacts = () => {
    setExportSelectedUsernames([])
  }

  const areExportFilteredContactsAllSelected = (tab = exportListTab.value) => {
    const usernames = getExportFilteredUsernames(tab)
    if (usernames.length !== exportSelectedUsernameSet.value.size) return false
    return usernames.every((username) => exportSelectedUsernameSet.value.has(username))
  }

  const onExportListTabClick = (tab) => {
    const nextTab = String(tab || 'all')
    const isSameTab = String(exportListTab.value || 'all') === nextTab
    exportListTab.value = nextTab

    if (isSameTab) {
      if (areExportFilteredContactsAllSelected(nextTab)) {
        clearExportFilteredContacts(nextTab)
      } else {
        selectExportFilteredContacts(nextTab)
      }
      return
    }

    selectExportFilteredContacts(nextTab)
  }

  const isExportContactSelected = (username) => {
    return exportSelectedUsernameSet.value.has(String(username || '').trim())
  }

  const onExportBatchScopeClick = (tab) => {
    exportScope.value = 'selected'
    onExportListTabClick(tab)
  }

  const isDesktopExportRuntime = () => {
    return !!(process.client && window?.wechatDesktop?.chooseDirectory)
  }

  const isWebDirectoryPickerSupported = () => {
    return !!(process.client && typeof window.showDirectoryPicker === 'function')
  }

  const hasWebExportFolder = computed(() => {
    return !!(isWebDirectoryPickerSupported() && exportFolderHandle.value)
  })

  const chooseExportFolder = async () => {
    exportError.value = ''
    exportSaveMsg.value = ''
    try {
      if (!process.client) {
        exportError.value = '当前环境不支持选择导出目录'
        return
      }

      if (isDesktopExportRuntime()) {
        const result = await window.wechatDesktop.chooseDirectory({ title: '选择导出目录' })
        if (result && !result.canceled && Array.isArray(result.filePaths) && result.filePaths.length > 0) {
          exportFolder.value = String(result.filePaths[0] || '').trim()
          exportFolderHandle.value = null
        }
        return
      }

      if (isWebDirectoryPickerSupported()) {
        const handle = await window.showDirectoryPicker()
        if (handle) {
          exportFolderHandle.value = handle
          exportFolder.value = `浏览器目录：${String(handle.name || '已选择')}`
        }
        return
      }

      exportError.value = '当前浏览器不支持目录选择，请使用桌面端或 Chromium 新版浏览器'
    } catch (error) {
      exportError.value = error?.message || '选择导出目录失败'
    }
  }

  const guessExportZipName = (job) => {
    const raw = String(job?.zipPath || '').trim()
    if (raw) {
      const name = raw.replace(/\\/g, '/').split('/').pop()
      if (name && name.toLowerCase().endsWith('.zip')) return name
    }
    const exportId = String(job?.exportId || '').trim() || 'export'
    return `wechat_chat_export_${exportId}.zip`
  }

  const getExportDownloadUrl = (exportId) => {
    return `${apiBase}/chat/exports/${encodeURIComponent(String(exportId || ''))}/download`
  }

  const saveExportToSelectedFolder = async (options = {}) => {
    const autoSave = !!options?.auto
    exportError.value = ''
    exportSaveMsg.value = ''
    if (!process.client || !isWebDirectoryPickerSupported()) {
      exportError.value = '当前环境不支持保存到浏览器目录'
      return
    }
    const handle = exportFolderHandle.value
    if (!handle || typeof handle.getFileHandle !== 'function') {
      exportError.value = '请先选择浏览器导出目录'
      return
    }

    const exportId = exportJob.value?.exportId
    if (!exportId || String(exportJob.value?.status || '') !== 'done') {
      exportError.value = '导出任务尚未完成'
      return
    }

    exportSaveBusy.value = true
    try {
      const response = await fetch(getExportDownloadUrl(exportId))
      if (!response.ok) {
        await reportServerErrorFromResponse(response, {
          method: 'GET',
          requestUrl: getExportDownloadUrl(exportId),
          message: `下载导出文件失败（${response.status}）`,
          source: 'chat.exportDownload'
        })
        throw new Error(`下载导出文件失败（${response.status}）`)
      }
      const blob = await response.blob()
      const fileName = guessExportZipName(exportJob.value)
      const fileHandle = await handle.getFileHandle(fileName, { create: true })
      const writable = await fileHandle.createWritable()
      await writable.write(blob)
      await writable.close()
      exportAutoSavedFor.value = String(exportId)
      exportSaveMsg.value = autoSave
        ? `已自动保存到已选目录：${fileName}`
        : `已保存到已选目录：${fileName}`
    } catch (error) {
      exportError.value = error?.message || '保存到浏览器目录失败'
    } finally {
      exportSaveBusy.value = false
    }
  }

  const stopExportPolling = () => {
    if (exportEventSource) {
      try {
        exportEventSource.close()
      } catch {}
      exportEventSource = null
    }
    if (exportPollTimer) {
      clearInterval(exportPollTimer)
      exportPollTimer = null
    }
  }

  const startExportHttpPolling = (exportId) => {
    if (!exportId) return
    exportPollTimer = setInterval(async () => {
      try {
        const response = await api.getChatExport(exportId)
        exportJob.value = response?.job || exportJob.value
        const status = String(exportJob.value?.status || '')
        if (status === 'done' || status === 'error' || status === 'cancelled') {
          stopExportPolling()
        }
      } catch {}
    }, 1200)
  }

  const startExportPolling = (exportId) => {
    stopExportPolling()
    if (!exportId) return

    if (process.client && typeof window !== 'undefined' && typeof EventSource !== 'undefined') {
      const url = `${apiBase}/chat/exports/${encodeURIComponent(String(exportId))}/events`
      try {
        exportEventSource = new EventSource(url)
        exportEventSource.onmessage = (event) => {
          try {
            const next = JSON.parse(String(event.data || '{}'))
            exportJob.value = next || exportJob.value
            const status = String(exportJob.value?.status || '')
            if (status === 'done' || status === 'error' || status === 'cancelled') {
              stopExportPolling()
            }
          } catch {}
        }
        exportEventSource.onerror = () => {
          try {
            exportEventSource?.close()
          } catch {}
          exportEventSource = null
          if (!exportPollTimer) startExportHttpPolling(exportId)
        }
        return
      } catch {
        exportEventSource = null
      }
    }

    startExportHttpPolling(exportId)
  }

  const openExportModal = () => {
    exportModalOpen.value = true
    exportError.value = ''
    exportSaveMsg.value = ''
    exportSearchQuery.value = ''
    exportListTab.value = 'all'
    exportSelectedUsernames.value = []
    exportStartLocal.value = ''
    exportEndLocal.value = ''
    exportMessageTypes.value = exportMessageTypeOptions.map((item) => item.value)
    exportAutoSavedFor.value = ''
    exportScope.value = selectedContact.value?.username ? 'current' : 'selected'
    if (!selectedContact.value?.username) {
      selectExportFilteredContacts('all')
    }
  }

  const closeExportModal = () => {
    exportModalOpen.value = false
    exportError.value = ''
  }

  watch(exportModalOpen, (open) => {
    if (!process.client) return
    if (!open) {
      stopExportPolling()
      return
    }

    const exportId = exportJob.value?.exportId
    const status = String(exportJob.value?.status || '')
    if (exportId && (status === 'queued' || status === 'running')) {
      startExportPolling(exportId)
    }
  })

  watch(exportScope, (scope, previousScope) => {
    if (scope !== 'selected' || previousScope === 'selected') return
    if (exportSelectedUsernames.value.length > 0) return
    selectExportFilteredContacts(exportListTab.value)
  })

  watch(
    () => ({
      exportId: String(exportJob.value?.exportId || ''),
      status: String(exportJob.value?.status || '')
    }),
    async ({ exportId, status }) => {
      if (!process.client || status !== 'done' || !exportId) return
      if (!hasWebExportFolder.value) return
      if (exportAutoSavedFor.value === exportId) return
      if (exportSaveBusy.value) return
      await saveExportToSelectedFolder({ auto: true })
    }
  )

  const startChatExport = async () => {
    exportError.value = ''
    exportSaveMsg.value = ''
    if (!selectedAccount.value) {
      exportError.value = '未选择账号'
      return
    }

    let scope = exportScope.value
    let usernames = []
    if (scope === 'current') {
      scope = 'selected'
      if (selectedContact.value?.username) {
        usernames = [selectedContact.value.username]
      }
    } else if (scope === 'selected') {
      usernames = Array.isArray(exportSelectedUsernames.value) ? exportSelectedUsernames.value.filter(Boolean) : []
    }

    if (scope === 'selected' && (!usernames || usernames.length === 0)) {
      exportError.value = '请选择至少一个会话'
      return
    }

    const hasDesktopFolder = isDesktopExportRuntime() && !!String(exportFolder.value || '').trim()
    const hasWebFolder = !isDesktopExportRuntime() && !!exportFolderHandle.value
    if (!hasDesktopFolder && !hasWebFolder) {
      exportError.value = '请先选择导出目录'
      return
    }

    const startTime = toUnixSeconds(exportStartLocal.value)
    const endTime = toUnixSeconds(exportEndLocal.value)
    if (startTime && endTime && startTime > endTime) {
      exportError.value = '时间范围不合法：开始时间不能晚于结束时间'
      return
    }

    const messageTypes = Array.isArray(exportMessageTypes.value) ? exportMessageTypes.value.filter(Boolean) : []
    if (messageTypes.length === 0) {
      exportError.value = '请至少勾选一个消息类型'
      return
    }

    const selectedTypeSet = new Set(messageTypes.map((item) => String(item || '').trim()))
    const mediaKindSet = new Set()
    if (selectedTypeSet.has('chatHistory')) {
      mediaKindSet.add('image')
      mediaKindSet.add('emoji')
      mediaKindSet.add('video')
      mediaKindSet.add('video_thumb')
      mediaKindSet.add('voice')
      mediaKindSet.add('file')
    }
    if (selectedTypeSet.has('image')) mediaKindSet.add('image')
    if (selectedTypeSet.has('emoji')) mediaKindSet.add('emoji')
    if (selectedTypeSet.has('video')) {
      mediaKindSet.add('video')
      mediaKindSet.add('video_thumb')
    }
    if (selectedTypeSet.has('voice')) mediaKindSet.add('voice')
    if (selectedTypeSet.has('file')) mediaKindSet.add('file')

    const mediaKinds = Array.from(mediaKindSet)
    const includeMedia = !privacyMode.value && mediaKinds.length > 0

    isExportCreating.value = true
    exportAutoSavedFor.value = ''
    try {
      const response = await api.createChatExport({
        account: selectedAccount.value,
        scope,
        usernames,
        format: exportFormat.value,
        start_time: startTime,
        end_time: endTime,
        include_hidden: false,
        include_official: false,
        message_types: messageTypes,
        include_media: includeMedia,
        media_kinds: mediaKinds,
        download_remote_media: exportFormat.value === 'html' && !!exportDownloadRemoteMedia.value,
        html_page_size: Math.max(0, Math.floor(Number(exportHtmlPageSize.value || 1000))),
        output_dir: isDesktopExportRuntime() ? String(exportFolder.value || '').trim() : null,
        privacy_mode: !!privacyMode.value,
        file_name: exportFileName.value || null
      })

      exportJob.value = response?.job || null
      const exportId = exportJob.value?.exportId
      if (exportId) startExportPolling(exportId)
    } catch (error) {
      exportError.value = error?.message || '创建导出任务失败'
    } finally {
      isExportCreating.value = false
    }
  }

  const cancelCurrentExport = async () => {
    const exportId = exportJob.value?.exportId
    if (!exportId) return

    try {
      await api.cancelChatExport(exportId)
      const response = await api.getChatExport(exportId)
      exportJob.value = response?.job || exportJob.value
    } catch (error) {
      exportError.value = error?.message || '取消导出失败'
    }
  }

  return {
    exportModalOpen,
    isExportCreating,
    exportError,
    exportScope,
    exportFormat,
    exportDownloadRemoteMedia,
    exportHtmlPageSize,
    exportMessageTypeOptions,
    exportMessageTypes,
    exportStartLocal,
    exportEndLocal,
    exportFileName,
    exportFolder,
    exportFolderHandle,
    exportSaveBusy,
    exportSaveMsg,
    exportAutoSavedFor,
    exportSearchQuery,
    exportListTab,
    exportSelectedUsernames,
    exportJob,
    exportOverallPercent,
    exportCurrentPercent,
    exportFilteredContacts,
    exportContactCounts,
    onExportBatchScopeClick,
    onExportListTabClick,
    isExportContactSelected,
    hasWebExportFolder,
    chooseExportFolder,
    getExportDownloadUrl,
    saveExportToSelectedFolder,
    openExportModal,
    closeExportModal,
    startChatExport,
    cancelCurrentExport,
    stopExportPolling
  }
}
