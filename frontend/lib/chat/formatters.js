export const normalizeSessionPreview = (value) => {
  const text = String(value || '').trim()
  if (!text) return ''
  const labelMap = {
    text: '文本',
    message: '消息',
    appmessage: '消息',
    'app message': '消息',
    image: '图片',
    img: '图片',
    picture: '图片',
    voice: '语音',
    audio: '语音',
    'contact card': '名片',
    contact: '名片',
    card: '名片',
    video: '视频',
    emoji: '动画表情',
    sticker: '动画表情',
    emoticon: '动画表情',
    location: '位置',
    miniprogram: '小程序',
    'mini program': '小程序',
    'mini-program': '小程序',
    link: '链接',
    url: '链接',
    article: '文章',
    music: '音乐',
    quote: '引用消息',
    live: '直播',
    announcement: '群公告',
    transfer: '转账',
    redpacket: '红包',
    'red packet': '红包',
    system: '系统消息',
    pat: '拍一拍',
    file: '文件',
    voip: '通话',
    chathistory: '聊天记录',
    'chat history': '聊天记录',
    聊天记录: '聊天记录'
  }
  const keyOf = (label) => String(label || '').trim().toLowerCase().replace(/[\s_-]+/g, ' ')
  const asLabel = (label) => {
    const zh = labelMap[keyOf(label)]
    return zh ? `[${zh}]` : ''
  }

  let out = text
    .replace(/\[([A-Za-z][A-Za-z0-9 _-]{0,40}|聊天记录)\]/g, (m, label) => asLabel(label) || m)
    .replace('[表情]', '[动画表情]')

  const direct = asLabel(out)
  if (direct) return direct

  out = out.replace(/^(.{1,128}?:\s*)([A-Za-z][A-Za-z0-9 _-]{0,40})$/, (m, prefix, label) => {
    const mapped = asLabel(label)
    return mapped ? `${prefix}${mapped}` : m
  })
  return out
}

export const formatSmartTime = (ts) => {
  if (!ts) return ''
  try {
    const date = new Date(Number(ts) * 1000)
    const now = new Date()
    const hh = String(date.getHours()).padStart(2, '0')
    const mm = String(date.getMinutes()).padStart(2, '0')
    const timeStr = `${hh}:${mm}`

    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const targetStart = new Date(date.getFullYear(), date.getMonth(), date.getDate())
    const dayDiff = Math.floor((todayStart - targetStart) / (1000 * 60 * 60 * 24))

    if (dayDiff === 0) return timeStr
    if (dayDiff === 1) return `昨天 ${timeStr}`
    if (dayDiff >= 2 && dayDiff <= 6) {
      const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
      return `${weekdays[date.getDay()]} ${timeStr}`
    }

    const month = date.getMonth() + 1
    const day = date.getDate()
    if (date.getFullYear() === now.getFullYear()) {
      return `${month}月${day}日 ${timeStr}`
    }

    return `${date.getFullYear()}年${month}月${day}日 ${timeStr}`
  } catch {
    return ''
  }
}

export const formatTimeDivider = (ts) => formatSmartTime(ts)

export const formatMessageTime = (ts) => {
  if (!ts) return ''
  try {
    const date = new Date(Number(ts) * 1000)
    const hh = String(date.getHours()).padStart(2, '0')
    const mm = String(date.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  } catch {
    return ''
  }
}

export const formatMessageFullTime = (ts) => {
  if (!ts) return ''
  try {
    const date = new Date(Number(ts) * 1000)
    const yyyy = String(date.getFullYear())
    const MM = String(date.getMonth() + 1).padStart(2, '0')
    const dd = String(date.getDate()).padStart(2, '0')
    const hh = String(date.getHours()).padStart(2, '0')
    const mm = String(date.getMinutes()).padStart(2, '0')
    const ss = String(date.getSeconds()).padStart(2, '0')
    return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`
  } catch {
    return ''
  }
}

export const formatFileSize = (size) => {
  if (!size) return ''
  const text = String(size).trim()
  const value = parseFloat(text)
  if (Number.isNaN(value)) return text
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(2)} KB`
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

export const formatTransferAmount = (amount) => {
  const text = String(amount ?? '').trim()
  if (!text) return ''
  return text.replace(/[￥¥]/g, '').trim()
}

export const getRedPacketText = (message) => {
  const text = String(message?.content ?? '').trim()
  if (!text || text === '[Red Packet]') return '恭喜发财，大吉大利'
  return text
}

export const isTransferReturned = (message) => {
  const paySubType = String(message?.paySubType || '').trim()
  if (paySubType === '4' || paySubType === '9') return true
  const status = String(message?.transferStatus || '').trim()
  const content = String(message?.content || '').trim()
  const text = `${status} ${content}`.trim()
  if (!text) return false
  return text.includes('退回') || text.includes('退还')
}

export const isTransferOverdue = (message) => {
  const paySubType = String(message?.paySubType || '').trim()
  if (paySubType === '10') return true
  const status = String(message?.transferStatus || '').trim()
  const content = String(message?.content || '').trim()
  const text = `${status} ${content}`.trim()
  if (!text) return false
  return text.includes('过期')
}

export const getTransferTitle = (message) => {
  const paySubType = String(message?.paySubType || '').trim()
  if (message?.transferStatus) return message.transferStatus
  switch (paySubType) {
    case '1':
      return '转账'
    case '3':
      return message?.isSent ? '已被接收' : '已收款'
    case '8':
      return '发起转账'
    case '4':
      return '已退还'
    case '9':
      return '已被退还'
    case '10':
      return '已过期'
    default:
      break
  }
  if (message?.content && message.content !== '转账' && message.content !== '[转账]') {
    return message.content
  }
  return '转账'
}

export const formatCount = (count) => {
  const value = Number(count || 0)
  if (!Number.isFinite(value) || value <= 0) return ''
  try {
    return value.toLocaleString()
  } catch {
    return String(value)
  }
}

export const escapeHtml = (value) => {
  if (!value) return ''
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export const highlightKeyword = (text, keyword) => {
  if (!text || !keyword) return escapeHtml(text || '')
  const escaped = escapeHtml(text)
  const kw = String(keyword || '').trim()
  if (!kw) return escaped
  try {
    const escapedKw = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escapedKw})`, 'gi')
    return escaped.replace(regex, '<mark class="search-highlight">$1</mark>')
  } catch {
    return escaped
  }
}

export const getVoiceDurationInSeconds = (durationMs) => {
  const value = Number(durationMs || 0)
  if (!Number.isFinite(value) || value <= 0) return 0
  return Math.max(1, Math.round(value / 1000))
}

export const getVoiceWidth = (durationMs) => {
  const seconds = getVoiceDurationInSeconds(durationMs)
  const clamped = Math.min(60, Math.max(1, seconds))
  return `${80 + clamped * 4}px`
}

export const toUnixSeconds = (datetimeLocal) => {
  const value = String(datetimeLocal || '').trim()
  if (!value) return null
  const date = new Date(value)
  const ms = date.getTime()
  if (Number.isNaN(ms)) return null
  return Math.floor(ms / 1000)
}

export const dateToUnixSeconds = (dateStr, endOfDay = false) => {
  const value = String(dateStr || '').trim()
  if (!value) return null
  const matched = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!matched) return null
  const year = Number(matched[1])
  const month = Number(matched[2])
  const day = Number(matched[3])
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null
  const date = new Date(year, month - 1, day, endOfDay ? 23 : 0, endOfDay ? 59 : 0, endOfDay ? 59 : 0)
  const ms = date.getTime()
  if (Number.isNaN(ms)) return null
  return Math.floor(ms / 1000)
}

export const getChatHistoryPreviewLines = (message) => {
  const raw = String(message?.content || '').trim()
  if (!raw) return []
  return raw.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).slice(0, 4)
}
