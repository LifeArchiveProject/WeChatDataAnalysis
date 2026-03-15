import { ref } from 'vue'
import {
  buildChatHistoryWindowPayload,
  createChatHistoryRecordNormalizer,
  enhanceChatHistoryRecords,
  formatChatHistoryVideoDuration,
  getChatHistoryPreviewLines,
  isChatHistoryRecordItemIncomplete,
  normalizeChatHistoryUrl,
  parseChatHistoryRecord,
  pickFirstMd5,
  stripWeChatInvisible
} from '~/lib/chat/chat-history'

export const useChatHistoryWindows = ({
  api,
  apiBase,
  selectedAccount,
  selectedContact,
  openImagePreview,
  openVideoPreview
}) => {
  const floatingWindows = ref([])
  let floatingWindowSeq = 0
  let floatingWindowZ = 70
  const floatingDragState = { id: '', offsetX: 0, offsetY: 0 }

  const clampNumber = (value, min, max) => Math.min(max, Math.max(min, value))
  const normalizeRecordItem = createChatHistoryRecordNormalizer({
    apiBase,
    getSelectedAccount: () => selectedAccount.value,
    getSelectedContact: () => selectedContact.value
  })

  const getFloatingWindowById = (id) => {
    const list = Array.isArray(floatingWindows.value) ? floatingWindows.value : []
    return list.find((item) => String(item?.id || '') === String(id || '')) || null
  }

  const focusFloatingWindow = (id) => {
    const windowItem = getFloatingWindowById(id)
    if (!windowItem) return
    floatingWindowZ += 1
    windowItem.zIndex = floatingWindowZ
  }

  const closeFloatingWindow = (id) => {
    const key = String(id || '')
    floatingWindows.value = (Array.isArray(floatingWindows.value) ? floatingWindows.value : []).filter((item) => String(item?.id || '') !== key)
    if (floatingDragState.id && String(floatingDragState.id) === key) {
      floatingDragState.id = ''
    }
  }

  const closeTopFloatingWindow = () => {
    const list = Array.isArray(floatingWindows.value) ? floatingWindows.value : []
    if (!list.length) return
    const top = [...list].sort((a, b) => Number(b?.zIndex || 0) - Number(a?.zIndex || 0))[0]
    if (top?.id) closeFloatingWindow(top.id)
  }

  const openFloatingWindow = (payload) => {
    if (!process.client || typeof window === 'undefined') return null
    floatingWindowSeq += 1
    floatingWindowZ += 1
    const width = clampNumber(Number(payload?.width || 520), 360, Math.max(360, (window.innerWidth || 1200) - 48))
    const height = clampNumber(Number(payload?.height || 420), 320, Math.max(320, (window.innerHeight || 900) - 48))
    const x = clampNumber(Number(payload?.x || Math.round(((window.innerWidth || width) - width) / 2)), 16, Math.max(16, (window.innerWidth || width) - width - 16))
    const y = clampNumber(Number(payload?.y || Math.round(((window.innerHeight || height) - height) / 2)), 16, Math.max(16, (window.innerHeight || height) - height - 16))

    const windowItem = {
      id: `chat-floating-${floatingWindowSeq}`,
      kind: String(payload?.kind || 'chatHistory'),
      title: String(payload?.title || ''),
      info: payload?.info || { isChatRoom: false },
      records: Array.isArray(payload?.records) ? payload.records : [],
      url: String(payload?.url || ''),
      content: String(payload?.content || ''),
      preview: String(payload?.preview || ''),
      from: String(payload?.from || ''),
      fromAvatar: String(payload?.fromAvatar || ''),
      loading: !!payload?.loading,
      width,
      height,
      x,
      y,
      zIndex: floatingWindowZ
    }
    floatingWindows.value = [...floatingWindows.value, windowItem]
    return windowItem
  }

  const startFloatingWindowDrag = (id, event) => {
    if (!process.client) return
    const windowItem = getFloatingWindowById(id)
    if (!windowItem) return
    focusFloatingWindow(id)
    const point = 'touches' in event ? event.touches?.[0] : event
    floatingDragState.id = id
    floatingDragState.offsetX = Number(point?.clientX || 0) - Number(windowItem.x || 0)
    floatingDragState.offsetY = Number(point?.clientY || 0) - Number(windowItem.y || 0)
  }

  const onFloatingWindowMouseMove = (event) => {
    if (!process.client) return
    if (!floatingDragState.id) return
    const windowItem = getFloatingWindowById(floatingDragState.id)
    if (!windowItem) return
    const point = 'touches' in event ? event.touches?.[0] : event
    const nextX = Number(point?.clientX || 0) - floatingDragState.offsetX
    const nextY = Number(point?.clientY || 0) - floatingDragState.offsetY
    windowItem.x = clampNumber(nextX, 8, Math.max(8, (window.innerWidth || nextX) - windowItem.width - 8))
    windowItem.y = clampNumber(nextY, 8, Math.max(8, (window.innerHeight || nextY) - windowItem.height - 8))
  }

  const onFloatingWindowMouseUp = () => {
    floatingDragState.id = ''
  }

  const chatHistoryModalVisible = ref(false)
  const chatHistoryModalTitle = ref('')
  const chatHistoryModalRecords = ref([])
  const chatHistoryModalInfo = ref({ isChatRoom: false })
  const chatHistoryModalStack = ref([])
  const goBackChatHistoryModal = () => {}
  const closeChatHistoryModal = () => {
    chatHistoryModalVisible.value = false
    chatHistoryModalTitle.value = ''
    chatHistoryModalRecords.value = []
    chatHistoryModalInfo.value = { isChatRoom: false }
    chatHistoryModalStack.value = []
  }

  const onChatHistoryVideoThumbError = (record) => {
    if (!record) return
    const candidates = record._videoThumbCandidates
    if (!Array.isArray(candidates) || candidates.length <= 1) {
      record._videoThumbError = true
      return
    }
    const current = Math.max(0, Number(record._videoThumbCandidateIndex || 0))
    const next = current + 1
    if (next < candidates.length) {
      record._videoThumbCandidateIndex = next
      record.videoThumbUrl = candidates[next]
      return
    }
    record._videoThumbError = true
  }

  const onChatHistoryLinkPreviewError = (record) => {
    if (!record) return
    const candidates = record._linkPreviewCandidates
    if (!Array.isArray(candidates) || candidates.length <= 1) {
      record._linkPreviewError = true
      return
    }
    const current = Math.max(0, Number(record._linkPreviewCandidateIndex || 0))
    const next = current + 1
    if (next < candidates.length) {
      record._linkPreviewCandidateIndex = next
      record.preview = candidates[next]
      record._linkPreviewError = false
      return
    }
    record._linkPreviewError = true
  }

  const onChatHistoryFromAvatarLoad = (record) => {
    try {
      if (record) {
        record._fromAvatarImgOk = true
        record._fromAvatarImgError = false
        record._fromAvatarLast = String(record.fromAvatar || '').trim()
      }
    } catch {}
  }

  const onChatHistoryFromAvatarError = (record) => {
    try {
      if (record) {
        record._fromAvatarImgOk = false
        record._fromAvatarImgError = true
        record._fromAvatarLast = String(record.fromAvatar || '').trim()
      }
    } catch {}
  }

  const onChatHistoryQuoteThumbError = (record) => {
    if (!record || !record.quote) return
    const candidates = record._quoteThumbCandidates
    if (!Array.isArray(candidates) || candidates.length <= 1) {
      record._quoteThumbError = true
      return
    }
    const current = Math.max(0, Number(record._quoteThumbCandidateIndex || 0))
    const next = current + 1
    if (next < candidates.length) {
      record._quoteThumbCandidateIndex = next
      record.quote.thumbUrl = candidates[next]
      return
    }
    record._quoteThumbError = true
  }

  const openChatHistoryQuote = (record) => {
    if (!process.client) return
    const quote = record?.quote
    if (!quote) return
    const kind = String(quote.kind || '')
    const url = String(quote.url || '').trim()
    if (!url) return

    if (kind === 'video') {
      openVideoPreview(url, quote?.thumbUrl)
      return
    }
    if (kind === 'image' || kind === 'emoji') {
      openImagePreview(url)
    }
  }

  const getChatHistoryLinkFromText = (record) => {
    const from = String(record?.from || '').trim()
    if (from) return from
    const url = String(record?.url || '').trim()
    if (!url) return ''
    try { return new URL(url).hostname || '' } catch { return '' }
  }

  const getChatHistoryLinkFromAvatarText = (record) => {
    const text = String(getChatHistoryLinkFromText(record) || '').trim()
    return text ? (Array.from(text)[0] || '') : ''
  }

  const openUrlInBrowser = (url) => {
    const next = String(url || '').trim()
    if (!next) return
    try { window.open(next, '_blank', 'noopener,noreferrer') } catch {}
  }

  const resolveChatHistoryLinkRecord = async (record) => {
    if (!process.client || !record || !selectedAccount.value) return null
    const serverId = String(record?.fromnewmsgid || '').trim()
    if (!serverId || record._linkResolving) return null

    record._linkResolving = true
    try {
      const response = await api.resolveAppMsg({
        account: selectedAccount.value,
        server_id: serverId
      })
      if (response && typeof response === 'object') {
        const title = String(response.title || '').trim()
        const content = String(response.content || '').trim()
        const url = String(response.url || '').trim()
        const from = String(response.from || '').trim()

        const normalizePreviewUrl = (value) => {
          const raw = String(value || '').trim()
          if (!raw) return ''
          if (/^\/api\/chat\/media\//i.test(raw) || /^blob:/i.test(raw) || /^data:/i.test(raw)) return raw
          if (!/^https?:\/\//i.test(raw)) return ''
          try {
            const host = new URL(raw).hostname.toLowerCase()
            if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
              return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
            }
          } catch {}
          return raw
        }

        if (title) record.title = title
        if (content && !stripWeChatInvisible(record.content)) record.content = content
        if (url) record.url = url
        if (from) record.from = from
        if (response.linkStyle) record.linkStyle = String(response.linkStyle || '').trim()
        if (response.linkType) record.linkType = String(response.linkType || '').trim()

        const fromUsername = String(response.fromUsername || '').trim()
        if (fromUsername) record.fromUsername = fromUsername
        const fromAvatarUrl = fromUsername
          ? `${apiBase}/chat/avatar?account=${encodeURIComponent(selectedAccount.value || '')}&username=${encodeURIComponent(fromUsername)}`
          : (url ? `${apiBase}/chat/media/favicon?url=${encodeURIComponent(url)}` : '')
        if (fromAvatarUrl) {
          const last = String(record._fromAvatarLast || '').trim()
          record.fromAvatar = fromAvatarUrl
          if (String(fromAvatarUrl).trim() !== last) {
            record._fromAvatarLast = String(fromAvatarUrl).trim()
            record._fromAvatarImgOk = false
            record._fromAvatarImgError = false
          }
        }

        const style = String(response.linkStyle || '').trim()
        const thumb = String(response.thumbUrl || '').trim()
        const cover = String(response.coverUrl || '').trim()
        const picked = style === 'cover' ? (cover || thumb) : (thumb || cover)
        const previewResolved = normalizePreviewUrl(picked)
        if (previewResolved) {
          const currentPreview = String(record.preview || '').trim()
          const candidates = Array.isArray(record._linkPreviewCandidates) ? record._linkPreviewCandidates.slice() : []
          if (currentPreview && !candidates.includes(currentPreview)) candidates.push(currentPreview)
          if (!candidates.includes(previewResolved)) candidates.push(previewResolved)
          record._linkPreviewCandidates = candidates
          if (!currentPreview || record._linkPreviewError) {
            record.preview = previewResolved
            record._linkPreviewCandidateIndex = candidates.indexOf(previewResolved)
            record._linkPreviewError = false
          }
        }
        return response
      }
    } catch {}
    finally {
      try { record._linkResolving = false } catch {}
    }
    return null
  }

  const resolveChatHistoryLinkRecords = (windowItem) => {
    if (!process.client) return
    const records = Array.isArray(windowItem?.records) ? windowItem.records : []
    const targets = records.filter((record) => {
      if (!record) return false
      if (String(record.renderType || '') !== 'link') return false
      if (!String(record.fromnewmsgid || '').trim()) return false
      const fromMissing = String(record.from || '').trim() === ''
      const previewMissing = !String(record.preview || '').trim()
      const urlMissing = !String(record.url || '').trim()
      const fromAvatarMissing = !String(record.fromAvatar || '').trim()
      return fromMissing || previewMissing || urlMissing || fromAvatarMissing
    })
    if (!targets.length) return
    ;(async () => {
      for (const target of targets.slice(0, 12)) {
        await resolveChatHistoryLinkRecord(target)
      }
    })()
  }

  const openChatHistoryLinkWindow = (record) => {
    if (!process.client) return
    const title = String(record?.title || record?.content || '链接').trim()
    const url = String(record?.url || '').trim()
    const preview = String(record?.preview || '').trim()
    const from = String(record?.from || '').trim()
    const fromAvatar = String(record?.fromAvatar || '').trim()
    const needResolve = !!String(record?.fromnewmsgid || '').trim() && (!url || !from || !preview || !fromAvatar)
    const windowItem = openFloatingWindow({
      kind: 'link',
      title: title || '链接',
      url,
      content: String(record?.content || '').trim(),
      preview,
      from,
      fromAvatar,
      width: 520,
      height: 420,
      loading: needResolve
    })
    if (!windowItem) return
    focusFloatingWindow(windowItem.id)
    try {
      windowItem._linkPreviewCandidates = Array.isArray(record?._linkPreviewCandidates) ? record._linkPreviewCandidates.slice() : (preview ? [preview] : [])
      windowItem._linkPreviewCandidateIndex = Math.max(0, Number(record?._linkPreviewCandidateIndex || 0))
      windowItem._linkPreviewError = false
      windowItem._fromAvatarLast = fromAvatar
      windowItem._fromAvatarImgOk = !!record?._fromAvatarImgOk
      windowItem._fromAvatarImgError = !!record?._fromAvatarImgError
      windowItem.fromnewmsgid = String(record?.fromnewmsgid || '').trim()
    } catch {}
    if (needResolve) {
      ;(async () => {
        await resolveChatHistoryLinkRecord(windowItem)
        windowItem.loading = false
      })()
    }
  }

  const openChatHistoryModal = (message) => {
    if (!process.client) return
    const { title0, info0, records0 } = buildChatHistoryWindowPayload(message, normalizeRecordItem)
    const windowItem = openFloatingWindow({
      kind: 'chatHistory',
      title: title0 || '聊天记录',
      info: info0,
      records: records0,
      width: 560,
      height: Math.round(Math.max(420, (window.innerHeight || 700) * 0.78))
    })
    if (!windowItem) return
    try { resolveChatHistoryLinkRecords(windowItem) } catch {}
  }

  const openNestedChatHistory = (record) => {
    if (!process.client) return
    const title = String(record?.title || '聊天记录')
    const content = String(record?.content || '')
    const recordItem = String(record?.recordItem || '').trim()
    const serverId = String(record?.fromnewmsgid || '').trim()

    const { info0, records0 } = buildChatHistoryWindowPayload({ title, content, recordItem }, normalizeRecordItem)
    const windowItem = openFloatingWindow({
      kind: 'chatHistory',
      title: title || '聊天记录',
      info: info0,
      records: records0,
      width: 560,
      height: Math.round(Math.max(420, (window.innerHeight || 700) * 0.78)),
      loading: false
    })
    if (!windowItem) return
    try { resolveChatHistoryLinkRecords(windowItem) } catch {}

    if (!serverId || !selectedAccount.value || record?._nestedResolving || !isChatHistoryRecordItemIncomplete(recordItem)) return
    record._nestedResolving = true
    windowItem.loading = true

    ;(async () => {
      try {
        const response = await api.resolveNestedChatHistory({
          account: selectedAccount.value,
          server_id: serverId
        })
        const resolved = String(response?.recordItem || '').trim()
        if (!resolved) return
        windowItem.title = String(response?.title || title || '聊天记录')
        const parsed = parseChatHistoryRecord(resolved)
        windowItem.info = parsed?.info || { isChatRoom: false, count: 0 }
        const items = Array.isArray(parsed?.items) ? parsed.items : []
        windowItem.records = items.length ? enhanceChatHistoryRecords(items.map(normalizeRecordItem)) : []
        if (!windowItem.records.length) {
          const lines = String(response?.content || content || '').trim().split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
          windowItem.info = { isChatRoom: false, count: 0 }
          windowItem.records = lines.map((line, idx) => normalizeRecordItem({
            id: String(idx),
            datatype: '1',
            sourcename: '',
            sourcetime: '',
            content: line,
            renderType: 'text'
          }))
        }
        try { resolveChatHistoryLinkRecords(windowItem) } catch {}
      } catch {}
      finally {
        windowItem.loading = false
        try { record._nestedResolving = false } catch {}
      }
    })()
  }

  return {
    floatingWindows,
    chatHistoryModalVisible,
    chatHistoryModalTitle,
    chatHistoryModalRecords,
    chatHistoryModalInfo,
    chatHistoryModalStack,
    goBackChatHistoryModal,
    closeChatHistoryModal,
    getFloatingWindowById,
    focusFloatingWindow,
    closeFloatingWindow,
    closeTopFloatingWindow,
    openFloatingWindow,
    startFloatingWindowDrag,
    onFloatingWindowMouseMove,
    onFloatingWindowMouseUp,
    formatChatHistoryVideoDuration,
    getChatHistoryPreviewLines,
    onChatHistoryVideoThumbError,
    onChatHistoryLinkPreviewError,
    onChatHistoryFromAvatarLoad,
    onChatHistoryFromAvatarError,
    onChatHistoryQuoteThumbError,
    openChatHistoryQuote,
    getChatHistoryLinkFromText,
    getChatHistoryLinkFromAvatarText,
    openUrlInBrowser,
    resolveChatHistoryLinkRecord,
    resolveChatHistoryLinkRecords,
    openChatHistoryLinkWindow,
    openChatHistoryModal,
    openNestedChatHistory
  }
}
