import { getChatHistoryPreviewLines } from '~/lib/chat/formatters'

export const isMaybeMd5 = (value) => /^[0-9a-f]{32}$/i.test(String(value || '').trim())

export const pickFirstMd5 = (...values) => {
  for (const value of values) {
    const text = String(value || '').trim()
    if (isMaybeMd5(text)) return text.toLowerCase()
  }
  return ''
}

export const normalizeChatHistoryUrl = (value) => String(value || '').trim().replace(/\s+/g, '')

export const stripWeChatInvisible = (value) => {
  return String(value || '').replace(/[\u3164\u2800]/g, '').trim()
}

export const parseChatHistoryRecord = (recordItemXml) => {
  if (!process.client) return { info: null, items: [] }
  const xml = String(recordItemXml || '').trim()
  if (!xml) return { info: null, items: [] }

  const normalized = xml
    .replace(/&#x20;/g, ' ')
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
    .replace(/&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[\da-fA-F]+;)/g, '&amp;')

  let doc
  try {
    doc = new DOMParser().parseFromString(normalized, 'text/xml')
  } catch {
    return { info: null, items: [] }
  }

  const parserErrors = doc.getElementsByTagName('parsererror')
  if (parserErrors && parserErrors.length) return { info: null, items: [] }

  const getText = (node, tag) => {
    try {
      if (!node) return ''
      const elements = Array.from(node.getElementsByTagName(tag) || [])
      const direct = elements.find((el) => el && el.parentNode === node)
      const target = direct || elements[0]
      return String(target?.textContent || '').trim()
    } catch {
      return ''
    }
  }

  const getDirectChildXml = (node, tag) => {
    try {
      if (!node) return ''
      const children = Array.from(node.children || [])
      const target = children.find((child) => String(child?.tagName || '').toLowerCase() === String(tag || '').toLowerCase())
      if (!target) return ''
      const raw = String(target.textContent || '').trim()
      if (raw && raw.startsWith('<') && raw.endsWith('>')) return raw
      if (typeof XMLSerializer !== 'undefined') {
        return new XMLSerializer().serializeToString(target)
      }
    } catch {}
    return ''
  }

  const getAnyXml = (node, tag) => {
    try {
      if (!node) return ''
      const elements = Array.from(node.getElementsByTagName(tag) || [])
      const direct = elements.find((el) => el && el.parentNode === node)
      const target = direct || elements[0]
      if (!target) return ''
      const raw = String(target.textContent || '').trim()
      if (raw && raw.startsWith('<') && raw.endsWith('>')) return raw
      if (typeof XMLSerializer !== 'undefined') return new XMLSerializer().serializeToString(target)
    } catch {}
    return ''
  }

  const sameTag = (element, tag) => String(element?.tagName || '').toLowerCase() === String(tag || '').toLowerCase()

  const closestAncestorByTag = (node, tag) => {
    const lower = String(tag || '').toLowerCase()
    let current = node
    while (current) {
      if (current.nodeType === 1 && String(current.tagName || '').toLowerCase() === lower) return current
      current = current.parentNode
    }
    return null
  }

  const root = doc?.documentElement
  const isChatRoom = String(getText(root, 'isChatRoom') || '').trim() === '1'
  const title = getText(root, 'title')
  const desc = getText(root, 'desc') || getText(root, 'info')

  const datalist = (() => {
    try {
      const all = Array.from(doc.getElementsByTagName('datalist') || [])
      const top = root ? all.find((el) => closestAncestorByTag(el, 'recorditem') === root) : null
      return top || all[0] || null
    } catch {
      return null
    }
  })()

  const datalistCount = (() => {
    try {
      if (!datalist) return 0
      const value = String(datalist.getAttribute('count') || '').trim()
      return Math.max(0, parseInt(value, 10) || 0)
    } catch {
      return 0
    }
  })()

  const itemNodes = (() => {
    if (datalist) return Array.from(datalist.children || []).filter((el) => sameTag(el, 'dataitem'))
    return Array.from(root?.children || []).filter((el) => sameTag(el, 'dataitem'))
  })()

  const parsed = itemNodes.map((node, idx) => {
    const datatype = String(node.getAttribute('datatype') || getText(node, 'datatype') || '').trim()
    const dataid = String(node.getAttribute('dataid') || getText(node, 'dataid') || '').trim() || String(idx)

    const sourcename = getText(node, 'sourcename')
    const sourcetime = getText(node, 'sourcetime')
    const sourceheadurl = normalizeChatHistoryUrl(getText(node, 'sourceheadurl'))
    const datatitle = getText(node, 'datatitle')
    const datadesc = getText(node, 'datadesc')
    const link = normalizeChatHistoryUrl(getText(node, 'link') || getText(node, 'dataurl') || getText(node, 'url'))
    const datafmt = getText(node, 'datafmt')
    const duration = getText(node, 'duration')

    const fullmd5 = getText(node, 'fullmd5')
    const thumbfullmd5 = getText(node, 'thumbfullmd5')
    const md5 = getText(node, 'md5') || getText(node, 'emoticonmd5') || getText(node, 'emojiMd5')
    const fromnewmsgid = getText(node, 'fromnewmsgid')
    const srcMsgLocalid = getText(node, 'srcMsgLocalid') || getText(node, 'srcMsgLocalId')
    const srcMsgCreateTime = getText(node, 'srcMsgCreateTime')
    const cdnurlstring = normalizeChatHistoryUrl(getText(node, 'cdnurlstring'))
    const encrypturlstring = normalizeChatHistoryUrl(getText(node, 'encrypturlstring'))
    const externurl = normalizeChatHistoryUrl(getText(node, 'externurl'))
    const aeskey = getText(node, 'aeskey')
    const nestedRecordItem = getAnyXml(node, 'recorditem') || getDirectChildXml(node, 'recorditem') || getText(node, 'recorditem')

    let content = datatitle || datadesc
    if (!content) {
      if (datatype === '4') content = '[视频]'
      else if (datatype === '2' || datatype === '3') content = '[图片]'
      else if (datatype === '47' || datatype === '37') content = '[表情]'
      else if (datatype) content = `[消息 ${datatype}]`
      else content = '[消息]'
    }

    const fmt = String(datafmt || '').trim().toLowerCase().replace(/^\./, '')
    const imageFormats = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif'])

    let renderType = 'text'
    if (datatype === '17') {
      renderType = 'chatHistory'
    } else if (datatype === '5' || link) {
      renderType = 'link'
    } else if (datatype === '4' || String(duration || '').trim() || fmt === 'mp4') {
      renderType = 'video'
    } else if (datatype === '47' || datatype === '37') {
      renderType = 'emoji'
    } else if (
      datatype === '2'
      || datatype === '3'
      || imageFormats.has(fmt)
      || (datatype !== '1' && isMaybeMd5(fullmd5))
    ) {
      renderType = 'image'
    } else if (isMaybeMd5(md5) && /表情/.test(String(content || ''))) {
      renderType = 'emoji'
    }

    let outTitle = ''
    let outUrl = ''
    let recordItem = ''
    if (renderType === 'chatHistory') {
      outTitle = datatitle || content || '聊天记录'
      content = datadesc || ''
      recordItem = nestedRecordItem
    } else if (renderType === 'link') {
      outTitle = datatitle || content || ''
      outUrl = link || externurl || ''
      const cleanDesc = stripWeChatInvisible(datadesc)
      const cleanTitle = stripWeChatInvisible(outTitle)
      if (!cleanDesc || (cleanTitle && cleanDesc === cleanTitle)) {
        content = ''
      } else {
        content = String(datadesc || '').trim()
      }
    }

    return {
      id: dataid,
      datatype,
      sourcename,
      sourcetime,
      sourceheadurl,
      datafmt,
      duration,
      fullmd5,
      thumbfullmd5,
      md5,
      fromnewmsgid,
      srcMsgLocalid,
      srcMsgCreateTime,
      cdnurlstring,
      encrypturlstring,
      externurl,
      aeskey,
      renderType,
      title: outTitle,
      recordItem,
      url: outUrl,
      content
    }
  })

  return {
    info: { isChatRoom, title, desc, count: datalistCount },
    items: parsed
  }
}

export const formatChatHistoryVideoDuration = (value) => {
  const total = Math.max(0, parseInt(String(value || '').trim(), 10) || 0)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  if (minutes <= 0) return `0:${String(seconds).padStart(2, '0')}`
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

export const createChatHistoryRecordNormalizer = ({ apiBase, getSelectedAccount, getSelectedContact }) => {
  return (record) => {
    const account = encodeURIComponent(String(getSelectedAccount?.() || '').trim())
    const username = encodeURIComponent(String(getSelectedContact?.()?.username || '').trim())
    const output = { ...(record || {}) }

    output.senderDisplayName = String(output.sourcename || '').trim()
    output.senderAvatar = normalizeChatHistoryUrl(output.sourceheadurl)
    output.fullTime = String(output.sourcetime || '').trim()

    if (output.renderType === 'link') {
      const linkUrl = String(output.url || output.externurl || '').trim()
      output.url = linkUrl
      output.from = String(output.from || '').trim()
      const previewCandidates = []
      const fileId = (() => {
        const localId = parseInt(String(output.srcMsgLocalid || '').trim(), 10) || 0
        const createTime = parseInt(String(output.srcMsgCreateTime || '').trim(), 10) || 0
        if (localId > 0 && createTime > 0) return `${localId}_${createTime}`
        return ''
      })()
      if (fileId) {
        previewCandidates.push(
          `${apiBase}/chat/media/image?account=${account}&file_id=${encodeURIComponent(fileId)}&username=${username}`
        )
      }

      output.previewMd5 = pickFirstMd5(output.fullmd5, output.thumbfullmd5, output.md5)
      const srcServerId = String(output.fromnewmsgid || '').trim()
      if (output.previewMd5) {
        const previewParts = [
          `account=${account}`,
          `md5=${encodeURIComponent(output.previewMd5)}`,
          srcServerId ? `server_id=${encodeURIComponent(srcServerId)}` : '',
          `username=${username}`
        ].filter(Boolean)
        previewCandidates.push(`${apiBase}/chat/media/image?${previewParts.join('&')}`)
      }

      output._linkPreviewCandidates = previewCandidates
      output._linkPreviewCandidateIndex = 0
      output._linkPreviewError = false
      output.preview = previewCandidates[0] || ''

      const fromUsername = String(output.fromUsername || '').trim()
      output.fromUsername = fromUsername
      output.fromAvatar = fromUsername
        ? `${apiBase}/chat/avatar?account=${account}&username=${encodeURIComponent(fromUsername)}`
        : (linkUrl ? `${apiBase}/chat/media/favicon?url=${encodeURIComponent(linkUrl)}` : '')
      output._fromAvatarLast = output.fromAvatar
      output._fromAvatarImgOk = false
      output._fromAvatarImgError = false
    } else if (output.renderType === 'video') {
      output.videoMd5 = pickFirstMd5(output.fullmd5, output.md5)
      output.videoThumbMd5 = pickFirstMd5(output.thumbfullmd5)
      output.videoDuration = String(output.duration || '').trim()
      const thumbCandidates = []
      if (output.videoMd5) {
        thumbCandidates.push(`${apiBase}/chat/media/video_thumb?account=${account}&md5=${encodeURIComponent(output.videoMd5)}&username=${username}`)
      }
      if (output.videoThumbMd5 && output.videoThumbMd5 !== output.videoMd5) {
        thumbCandidates.push(`${apiBase}/chat/media/video_thumb?account=${account}&md5=${encodeURIComponent(output.videoThumbMd5)}&username=${username}`)
      }
      output._videoThumbCandidates = thumbCandidates
      output._videoThumbCandidateIndex = 0
      output._videoThumbError = false
      output.videoThumbUrl = thumbCandidates[0] || ''
      output.videoUrl = output.videoMd5
        ? `${apiBase}/chat/media/video?account=${account}&md5=${encodeURIComponent(output.videoMd5)}&username=${username}`
        : ''
      if (!output.content || /^\[.+\]$/.test(String(output.content || '').trim())) output.content = '[视频]'
    } else if (output.renderType === 'emoji') {
      output.emojiMd5 = pickFirstMd5(output.md5, output.fullmd5, output.thumbfullmd5)
      const remoteEmojiUrl = String(output.cdnurlstring || output.externurl || output.encrypturlstring || '').trim()
      const remoteAesKey = String(output.aeskey || '').trim()
      output.emojiRemoteUrl = remoteEmojiUrl
      output.emojiUrl = output.emojiMd5
        ? `${apiBase}/chat/media/emoji?account=${account}&md5=${encodeURIComponent(output.emojiMd5)}&username=${username}${remoteEmojiUrl ? `&emoji_url=${encodeURIComponent(remoteEmojiUrl)}` : ''}${remoteAesKey ? `&aes_key=${encodeURIComponent(remoteAesKey)}` : ''}`
        : ''
      if (!output.content || /^\[.+\]$/.test(String(output.content || '').trim())) output.content = '[表情]'
    } else if (output.renderType === 'image') {
      output.imageMd5 = pickFirstMd5(output.fullmd5, output.thumbfullmd5, output.md5)
      const srcServerId = String(output.fromnewmsgid || '').trim()
      const imageParts = [
        `account=${account}`,
        output.imageMd5 ? `md5=${encodeURIComponent(output.imageMd5)}` : '',
        srcServerId ? `server_id=${encodeURIComponent(srcServerId)}` : '',
        `username=${username}`
      ].filter(Boolean)
      output.imageUrl = imageParts.length ? `${apiBase}/chat/media/image?${imageParts.join('&')}` : ''
      if (!output.content || /^\[.+\]$/.test(String(output.content || '').trim())) output.content = '[图片]'
    }

    return output
  }
}

export const enhanceChatHistoryRecords = (records) => {
  const list = Array.isArray(records) ? records : []
  const videoByThumbMd5 = new Map()
  const videoByMd5 = new Map()
  const imageByMd5 = new Map()
  const emojiByMd5 = new Map()

  for (const record of list) {
    if (!record) continue
    if (record.renderType === 'video' && record.videoThumbMd5) {
      videoByThumbMd5.set(String(record.videoThumbMd5).toLowerCase(), record)
    }
    if (record.renderType === 'video' && record.videoMd5) {
      videoByMd5.set(String(record.videoMd5).toLowerCase(), record)
    }
    if (record.renderType === 'image') {
      const keys = [
        pickFirstMd5(record.imageMd5),
        pickFirstMd5(record.fullmd5),
        pickFirstMd5(record.thumbfullmd5)
      ].filter(Boolean)
      for (const key of keys) imageByMd5.set(key, record)
    }
    if (record.renderType === 'emoji') {
      const keys = [
        pickFirstMd5(record.emojiMd5),
        pickFirstMd5(record.md5),
        pickFirstMd5(record.fullmd5),
        pickFirstMd5(record.thumbfullmd5)
      ].filter(Boolean)
      for (const key of keys) emojiByMd5.set(key, record)
    }
  }

  for (const record of list) {
    if (!record || String(record.renderType || '') !== 'text') continue

    const refKey = pickFirstMd5(record.thumbfullmd5) || pickFirstMd5(record.fullmd5)
    if (!refKey) continue

    const video = videoByThumbMd5.get(refKey) || videoByMd5.get(refKey)
    if (video) {
      const quoteThumbCandidates = Array.isArray(video._videoThumbCandidates) ? video._videoThumbCandidates.slice() : []
      record._quoteThumbCandidates = quoteThumbCandidates
      record._quoteThumbCandidateIndex = 0
      record._quoteThumbError = false
      const quoteThumbUrl = quoteThumbCandidates[0] || video.videoThumbUrl || ''
      record.renderType = 'quote'
      record.quote = {
        kind: 'video',
        thumbUrl: quoteThumbUrl,
        url: video.videoUrl || '',
        duration: video.videoDuration || '',
        label: video.content || '[视频]',
        targetId: video.id || ''
      }
      record.quoteMedia = {
        videoMd5: video.videoMd5,
        videoThumbMd5: video.videoThumbMd5,
        videoUrl: video.videoUrl,
        videoThumbUrl: quoteThumbUrl
      }
      continue
    }

    const image = imageByMd5.get(refKey)
    if (image) {
      record.renderType = 'quote'
      record.quote = {
        kind: 'image',
        thumbUrl: image.imageUrl || '',
        url: image.imageUrl || '',
        label: image.content || '[图片]',
        targetId: image.id || ''
      }
      record.quoteMedia = {
        imageMd5: image.imageMd5,
        imageUrl: image.imageUrl
      }
      continue
    }

    const emoji = emojiByMd5.get(refKey)
    if (emoji) {
      record.renderType = 'quote'
      record.quote = {
        kind: 'emoji',
        thumbUrl: emoji.emojiUrl || '',
        url: emoji.emojiUrl || '',
        label: emoji.content || '[表情]',
        targetId: emoji.id || ''
      }
      record.quoteMedia = {
        emojiMd5: emoji.emojiMd5,
        emojiUrl: emoji.emojiUrl
      }
    }
  }

  return list
}

export const isChatHistoryRecordItemIncomplete = (recordItemXml) => {
  const recordItem = String(recordItemXml || '').trim()
  if (!recordItem) return true
  try {
    const parsed = parseChatHistoryRecord(recordItem)
    const got = Array.isArray(parsed?.items) ? parsed.items.length : 0
    const expected = Math.max(0, parseInt(String(parsed?.info?.count || '0'), 10) || 0)
    if (expected > 0 && got < expected) return true
    if (got <= 0) return true
  } catch {
    return true
  }
  return false
}

export const buildChatHistoryWindowPayload = (payload, normalizeRecordItem) => {
  const title0 = String(payload?.title || '聊天记录')
  const content0 = String(payload?.content || '')
  const recordItem0 = String(payload?.recordItem || '').trim()
  const parsed = parseChatHistoryRecord(recordItem0)
  const info0 = parsed?.info || { isChatRoom: false, count: 0 }
  const items = Array.isArray(parsed?.items) ? parsed.items : []
  let records0 = items.length ? enhanceChatHistoryRecords(items.map(normalizeRecordItem)) : []
  if (!records0.length) {
    const lines = content0.trim().split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
    records0 = lines.map((line, idx) => normalizeRecordItem({
      id: String(idx),
      datatype: '1',
      sourcename: '',
      sourcetime: '',
      content: line,
      renderType: 'text'
    }))
  }
  return { title0, content0, recordItem0, info0, records0 }
}

export { getChatHistoryPreviewLines }
