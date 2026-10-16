const HTTP_URL_RE = /https?:\/\/[^\s<>"'`]+/gi
const TRAILING_URL_PUNCTUATION_RE = /[.,;!，。；！、）】》〉」』]+$/u

export const normalizeMessageHttpUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : ''
  } catch {
    return ''
  }
}

const splitTextSegment = (segment) => {
  const text = String(segment?.content || '')
  if (!text) return segment ? [segment] : []

  const output = []
  let cursor = 0
  HTTP_URL_RE.lastIndex = 0
  for (const match of text.matchAll(HTTP_URL_RE)) {
    const start = Number(match.index || 0)
    const rawMatch = String(match[0] || '')
    const candidate = rawMatch.replace(TRAILING_URL_PUNCTUATION_RE, '')
    const url = normalizeMessageHttpUrl(candidate)
    if (!url) continue
    if (start > cursor) output.push({ type: 'text', content: text.slice(cursor, start) })
    output.push({ type: 'link', content: candidate, url })
    cursor = start + candidate.length
  }
  if (cursor < text.length) output.push({ type: 'text', content: text.slice(cursor) })
  return output.length ? output : [segment]
}

export const linkifyMessageSegments = (segments) => {
  const output = []
  for (const segment of Array.isArray(segments) ? segments : []) {
    if (segment?.type === 'text') output.push(...splitTextSegment(segment))
    else if (segment) output.push(segment)
  }
  return output
}

export const openMessageExternalUrl = async (value) => {
  const url = normalizeMessageHttpUrl(value)
  if (!url || typeof window === 'undefined') return false

  if (window.wechatDesktop?.openExternalUrl) {
    try {
      const result = await window.wechatDesktop.openExternalUrl(url)
      if (result?.ok !== false) return true
    } catch {}
  }

  try {
    window.open(url, '_blank', 'noopener,noreferrer')
    return true
  } catch {
    return false
  }
}
