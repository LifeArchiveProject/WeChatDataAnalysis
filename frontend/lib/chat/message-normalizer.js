import { formatMessageFullTime, formatMessageTime } from '~/lib/chat/formatters'

const normalizeMaybeUrl = (value) => (typeof value === 'string' ? value.trim() : '')

const normalizeAtUsernames = (value) => {
  if (!Array.isArray(value)) return []
  const seen = new Set()
  const output = []
  for (const item of value) {
    const username = String(item || '').trim()
    if (!username || seen.has(username)) continue
    seen.add(username)
    output.push(username)
  }
  return output
}

const normalizeAtUsers = (value) => {
  if (!Array.isArray(value)) return []
  const seen = new Set()
  const output = []
  for (const item of value) {
    if (!item || typeof item !== 'object') continue
    const username = String(item.username || item.userName || item.wxid || '').trim()
    if (!username || seen.has(username)) continue
    seen.add(username)
    output.push({
      username,
      displayName: String(item.displayName || item.name || item.nickname || item.remark || username).trim(),
      avatar: normalizeMaybeUrl(item.avatar || item.avatarUrl || '')
    })
  }
  return output
}

const isUsableMediaUrl = (value) => {
  const text = normalizeMaybeUrl(value)
  if (!text) return false
  return (
    /^https?:\/\//i.test(text)
    || /^blob:/i.test(text)
    || /^data:/i.test(text)
    || /^\/api\/chat\/media\//i.test(text)
  )
}

const buildAccountMediaUrl = (apiBase, path, parts) => {
  return `${apiBase}${path}?${parts.filter(Boolean).join('&')}`
}

const isManualLargeImageUrl = (value) => {
  const text = normalizeMaybeUrl(value)
  if (!/\/api\/chat\/media\/image\b/i.test(text)) return false
  try {
    const url = new URL(text, 'http://wechat-data-analysis.local')
    return (
      String(url.searchParams.get('prefer_live') || '').toLowerCase() === 'true'
      || String(url.searchParams.get('deep_scan') || '').toLowerCase() === 'true'
    )
  } catch {
    return /\b(?:prefer_live|deep_scan)=true\b/i.test(text)
  }
}

export const createMessageNormalizer = ({
  apiBase,
  getSelectedAccount,
  getSelectedContact,
  getLocalMediaVersion,
  shouldPreferLargeImage,
  getLargeImageVersion
}) => {
  return (msg) => {
    const account = String(getSelectedAccount?.() || '').trim()
    const contact = getSelectedContact?.() || null
    const username = String(contact?.username || '').trim()
    const localMediaVersion = Number(getLocalMediaVersion?.() || 0)
    const serverIdStr = String(msg.serverIdStr || (msg.serverId != null ? String(msg.serverId) : '')).trim()
    const isSent = !!msg.isSent
    const rawSenderDisplayName = String(msg.senderDisplayName || '').trim()
    const rawSenderUsername = String(msg.senderUsername || '').trim()
    const rawSender = String(msg.sender || '').trim()
    const messageConversationUsername = String(msg.username || msg.chatUsername || msg.sessionId || '').trim()
    const conversationIsGroup = !!(
      contact?.isGroup
      || username.endsWith('@chatroom')
      || messageConversationUsername.endsWith('@chatroom')
      || msg.isGroup
    )
    const senderDisplayName = isSent
      ? ''
      : (
          rawSenderDisplayName
          || (conversationIsGroup && rawSender && rawSender !== rawSenderUsername ? rawSender : '')
          || rawSenderUsername
        )
    const sender = isSent ? '我' : (senderDisplayName || contact?.name || '')
    const fallbackAvatar = (!isSent && !conversationIsGroup) ? (contact?.avatar || null) : null
    const atUsers = normalizeAtUsers(msg.atUsers)
    const atUsernamesFromUsers = atUsers.map((item) => item.username)
    const atUsernames = normalizeAtUsernames(
      Array.isArray(msg.atUsernames) && msg.atUsernames.length ? msg.atUsernames : atUsernamesFromUsers
    )

    const normalizedThumbUrl = (() => {
      const candidates = [msg.thumbUrl, msg.preview]
      for (const candidate of candidates) {
        if (isUsableMediaUrl(candidate)) return normalizeMaybeUrl(candidate)
      }
      return ''
    })()

    const normalizedLinkPreviewUrl = (() => {
      const url = normalizedThumbUrl
      if (!url) return ''
      if (/^\/api\/chat\/media\//i.test(url) || /^blob:/i.test(url) || /^data:/i.test(url)) return url
      if (!/^https?:\/\//i.test(url)) return url
      try {
        const host = new URL(url).hostname.toLowerCase()
        if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
          return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(url)}`
        }
      } catch {}
      return url
    })()

    const fromUsername = String(msg.fromUsername || '').trim()
    const fromAvatar = fromUsername
      ? `${apiBase}/chat/avatar?account=${encodeURIComponent(account)}&username=${encodeURIComponent(fromUsername)}`
      : (() => {
        const href = String(msg.url || '').trim()
        return href ? `${apiBase}/chat/media/favicon?url=${encodeURIComponent(href)}` : ''
      })()

    const localEmojiUrl = msg.emojiMd5
      ? `${apiBase}/chat/media/emoji?account=${encodeURIComponent(account)}&md5=${encodeURIComponent(msg.emojiMd5)}&username=${encodeURIComponent(username)}`
      : ''

    const localImageUrl = (() => {
      if (!msg.imageMd5 && !msg.imageFileId) return ''
      return buildAccountMediaUrl(apiBase, '/chat/media/image', [
        `account=${encodeURIComponent(account)}`,
        msg.imageMd5 ? `md5=${encodeURIComponent(msg.imageMd5)}` : '',
        msg.imageFileId ? `file_id=${encodeURIComponent(msg.imageFileId)}` : '',
        `username=${encodeURIComponent(username)}`,
        localMediaVersion > 0 ? `v=${encodeURIComponent(String(localMediaVersion))}` : ''
      ])
    })()

    const preferLargeImage = !!shouldPreferLargeImage?.(msg)
    const localLargeImageUrl = (() => {
      if (!preferLargeImage) return ''
      if (!msg.imageMd5 && !msg.imageFileId && !serverIdStr) return ''
      const version = Number(getLargeImageVersion?.(msg) || localMediaVersion || 0)
      return buildAccountMediaUrl(apiBase, '/chat/media/image', [
        `account=${encodeURIComponent(account)}`,
        msg.imageMd5 ? `md5=${encodeURIComponent(msg.imageMd5)}` : '',
        msg.imageFileId ? `file_id=${encodeURIComponent(msg.imageFileId)}` : '',
        `username=${encodeURIComponent(username)}`,
        (!msg.imageMd5 && !msg.imageFileId && serverIdStr) ? `server_id=${encodeURIComponent(serverIdStr)}` : '',
        'prefer_live=true',
        'deep_scan=true',
        version > 0 ? `v=${encodeURIComponent(String(version))}` : ''
      ])
    })()

    const normalizedImageUrl = (() => {
      const current = isUsableMediaUrl(msg.imageUrl) ? normalizeMaybeUrl(msg.imageUrl) : ''
      if (preferLargeImage && localLargeImageUrl) {
        if (current && isManualLargeImageUrl(current)) return current
        return localLargeImageUrl
      }
      if (current && /\/api\/chat\/media\/image\b/i.test(current) && localImageUrl) {
        if (isManualLargeImageUrl(current)) return current
        return localImageUrl
      }
      return current || localImageUrl || ''
    })()

    const normalizedEmojiUrl = msg.emojiUrl || localEmojiUrl

    const localVideoThumbUrl = (() => {
      if (!msg.videoThumbMd5 && !msg.videoThumbFileId) return ''
      return buildAccountMediaUrl(apiBase, '/chat/media/video_thumb', [
        `account=${encodeURIComponent(account)}`,
        msg.videoThumbMd5 ? `md5=${encodeURIComponent(msg.videoThumbMd5)}` : '',
        msg.videoThumbFileId ? `file_id=${encodeURIComponent(msg.videoThumbFileId)}` : '',
        `username=${encodeURIComponent(username)}`,
        localMediaVersion > 0 ? `v=${encodeURIComponent(String(localMediaVersion))}` : ''
      ])
    })()

    const localVideoUrl = (() => {
      if (!msg.videoMd5 && !msg.videoFileId) return ''
      return buildAccountMediaUrl(apiBase, '/chat/media/video', [
        `account=${encodeURIComponent(account)}`,
        msg.videoMd5 ? `md5=${encodeURIComponent(msg.videoMd5)}` : '',
        msg.videoFileId ? `file_id=${encodeURIComponent(msg.videoFileId)}` : '',
        `username=${encodeURIComponent(username)}`
      ])
    })()

    const normalizedVideoThumbUrl = (isUsableMediaUrl(msg.videoThumbUrl) ? normalizeMaybeUrl(msg.videoThumbUrl) : '') || localVideoThumbUrl
    const normalizedVideoUrl = (isUsableMediaUrl(msg.videoUrl) ? normalizeMaybeUrl(msg.videoUrl) : '') || localVideoUrl
    const normalizedVoiceUrl = (() => {
      if (msg.voiceUrl) return msg.voiceUrl
      if (!serverIdStr) return ''
      if (String(msg.renderType || '') !== 'voice') return ''
      return `${apiBase}/chat/media/voice?account=${encodeURIComponent(account)}&server_id=${encodeURIComponent(serverIdStr)}`
    })()

    const remoteFromServer = (
      typeof msg.emojiRemoteUrl === 'string'
      && /^https?:\/\//i.test(msg.emojiRemoteUrl)
      && !/\/api\/chat\/media\/emoji\b/i.test(msg.emojiRemoteUrl)
      && !/\blocalhost\b/i.test(msg.emojiRemoteUrl)
      && !/\b127\.0\.0\.1\b/i.test(msg.emojiRemoteUrl)
    ) ? msg.emojiRemoteUrl : ''

    const remoteFromEmojiUrl = (
      typeof msg.emojiUrl === 'string'
      && /^https?:\/\//i.test(msg.emojiUrl)
      && !/\/api\/chat\/media\/emoji\b/i.test(msg.emojiUrl)
      && !/\blocalhost\b/i.test(msg.emojiUrl)
      && !/\b127\.0\.0\.1\b/i.test(msg.emojiUrl)
    ) ? msg.emojiUrl : ''

    const emojiRemoteUrl = remoteFromServer || remoteFromEmojiUrl
    const emojiIsLocal = typeof normalizedEmojiUrl === 'string' && /\/api\/chat\/media\/emoji\b/i.test(normalizedEmojiUrl)
    const emojiDownloaded = !!emojiRemoteUrl && !!emojiIsLocal

    const replyText = String(msg.content || '').trim()
    let quoteContent = String(msg.quoteContent || '')
    const trimmedQuoteContent = quoteContent.trim()
    if (replyText && trimmedQuoteContent) {
      if (trimmedQuoteContent === replyText) {
        quoteContent = ''
      } else {
        const lines = trimmedQuoteContent.split(/\r?\n/).map((item) => item.trim())
        if (lines.length && (lines[0] === replyText || lines[0] === replyText.split(/\r?\n/)[0]?.trim())) {
          quoteContent = trimmedQuoteContent.split(/\r?\n/).slice(1).join('\n').trim()
        } else if (trimmedQuoteContent.startsWith(replyText)) {
          quoteContent = trimmedQuoteContent.slice(replyText.length).trim()
        }
      }
    }

    const quoteServerIdStr = String(msg.quoteServerId || '').trim()
    const quoteTypeStr = String(msg.quoteType || '').trim()
    const quoteVoiceUrl = quoteServerIdStr
      ? `${apiBase}/chat/media/voice?account=${encodeURIComponent(account)}&server_id=${encodeURIComponent(quoteServerIdStr)}`
      : ''

    const quoteImageUrl = (() => {
      if (!quoteServerIdStr) return ''
      if (quoteTypeStr !== '3' && String(msg.quoteContent || '').trim() !== '[图片]') return ''
      return buildAccountMediaUrl(apiBase, '/chat/media/image', [
        `account=${encodeURIComponent(account)}`,
        `server_id=${encodeURIComponent(quoteServerIdStr)}`,
        username ? `username=${encodeURIComponent(username)}` : '',
        'prefer_live=true',
        'deep_scan=true',
        localMediaVersion > 0 ? `v=${encodeURIComponent(String(localMediaVersion))}` : ''
      ])
    })()

    const quoteThumbUrl = (() => {
      const raw = isUsableMediaUrl(msg.quoteThumbUrl) ? normalizeMaybeUrl(msg.quoteThumbUrl) : ''
      if (!raw) return ''
      if (/^\/api\/chat\/media\//i.test(raw) || /^blob:/i.test(raw) || /^data:/i.test(raw)) return raw
      if (!/^https?:\/\//i.test(raw)) return raw
      try {
        const host = new URL(raw).hostname.toLowerCase()
        if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
          return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
        }
      } catch {}
      return raw
    })()

    return {
      id: msg.id,
      localId: Number(msg.localId || 0),
      serverId: msg.serverId || 0,
      serverIdStr,
      type: Number(msg.type || 0),
      sender,
      senderUsername: rawSenderUsername,
      senderDisplayName,
      content: msg.content || '',
      time: formatMessageTime(msg.createTime),
      fullTime: formatMessageFullTime(msg.createTime),
      createTime: Number(msg.createTime || 0),
      isSent,
      renderType: msg.renderType || 'text',
      voipType: msg.voipType || '',
      atUsernames,
      atUsers,
      title: msg.title || '',
      url: msg.url || '',
      recordItem: msg.recordItem || '',
      imageMd5: msg.imageMd5 || '',
      imageFileId: msg.imageFileId || '',
      emojiMd5: msg.emojiMd5 || '',
      emojiUrl: normalizedEmojiUrl || '',
      emojiLocalUrl: localEmojiUrl || '',
      emojiRemoteUrl,
      _emojiDownloaded: !!emojiDownloaded,
      thumbUrl: msg.thumbUrl || '',
      imageUrl: normalizedImageUrl || '',
      videoMd5: msg.videoMd5 || '',
      videoThumbMd5: msg.videoThumbMd5 || '',
      videoFileId: msg.videoFileId || '',
      videoThumbFileId: msg.videoThumbFileId || '',
      videoThumbUrl: normalizedVideoThumbUrl || '',
      videoUrl: normalizedVideoUrl || '',
      quoteTitle: msg.quoteTitle || '',
      quoteContent,
      quoteUsername: msg.quoteUsername || '',
      quoteServerId: quoteServerIdStr,
      quoteType: quoteTypeStr,
      quoteVoiceLength: msg.quoteVoiceLength || '',
      quoteVoiceUrl,
      quoteImageUrl: quoteImageUrl || '',
      quoteThumbUrl: quoteThumbUrl || '',
      _quoteImageError: false,
      _quoteThumbError: false,
      amount: msg.amount || '',
      coverUrl: msg.coverUrl || '',
      objectId: String(msg.objectId || '').trim(),
      objectNonceId: String(msg.objectNonceId || '').trim(),
      fileSize: msg.fileSize || '',
      fileMd5: msg.fileMd5 || '',
      paySubType: msg.paySubType || '',
      transferStatus: msg.transferStatus || '',
      transferReceived: msg.paySubType === '3' || msg.transferStatus === '已收款' || msg.transferStatus === '已被接收',
      voiceUrl: normalizedVoiceUrl || '',
      voiceDuration: msg.voiceLength || msg.voiceDuration || '',
      locationLat: msg.locationLat ?? null,
      locationLng: msg.locationLng ?? null,
      locationPoiname: String(msg.locationPoiname || '').trim(),
      locationLabel: String(msg.locationLabel || '').trim(),
      preview: normalizedLinkPreviewUrl || '',
      linkType: String(msg.linkType || '').trim(),
      linkStyle: String(msg.linkStyle || '').trim(),
      linkCardVariant: String(msg.linkStyle || '').trim() === 'cover' ? 'cover' : 'default',
      from: String(msg.from || '').trim(),
      fromUsername,
      fromAvatar,
      isGroup: conversationIsGroup,
      avatar: msg.senderAvatar || msg.avatar || fallbackAvatar || null,
      avatarColor: null
    }
  }
}

export const dedupeMessagesById = (list) => {
  const input = Array.isArray(list) ? list : []
  const seen = new Set()
  const output = []
  for (const item of input) {
    const id = String(item?.id || '')
    if (!id) {
      output.push(item)
      continue
    }
    if (seen.has(id)) continue
    seen.add(id)
    output.push(item)
  }
  return output
}
