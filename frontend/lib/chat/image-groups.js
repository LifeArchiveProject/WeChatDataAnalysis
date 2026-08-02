const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const normalizeGroupCount = (value) => {
  const count = Number.parseInt(String(value ?? '').trim(), 10)
  return Number.isSafeInteger(count) && count >= 2 ? count : 0
}

export const normalizeImageGroupMetadata = (message) => {
  const type = String(message?.imageGroupType ?? '').trim()
  const id = String(message?.imageGroupId ?? '').trim().toLowerCase()
  const count = normalizeGroupCount(message?.imageGroupCount)
  if (!type || !UUID_RE.test(id) || !count) {
    return {
      imageGroupType: '',
      imageGroupId: '',
      imageGroupCount: 0
    }
  }
  return {
    imageGroupType: type,
    imageGroupId: id,
    imageGroupCount: count
  }
}

export const buildImageGroupKey = (message) => {
  if (String(message?.renderType || '') !== 'image') return ''

  const metadata = normalizeImageGroupMetadata(message)
  if (!metadata.imageGroupId) return ''
  return `${metadata.imageGroupType}:${metadata.imageGroupId}:${metadata.imageGroupCount}`
}

export const deriveImageGroupMessages = (messages, expandedKeys = new Set()) => {
  const input = Array.isArray(messages) ? messages : []
  const groups = new Map()

  for (const message of input) {
    const key = buildImageGroupKey(message)
    if (!key) continue
    const items = groups.get(key) || []
    items.push(message)
    groups.set(key, items)
  }

  const emitted = new Set()
  const output = []
  for (const message of input) {
    const key = buildImageGroupKey(message)
    const items = key ? groups.get(key) : null
    if (!key || !items || items.length < 2) {
      output.push(message)
      continue
    }
    const protocolCount = normalizeGroupCount(message.imageGroupCount)
    if (expandedKeys?.has?.(key)) {
      output.push({
        ...message,
        imageGroupKey: key,
        imageGroupItems: items,
        imageGroupItemIndex: items.indexOf(message),
        imageGroupProtocolCount: protocolCount,
        imageGroupExpanded: true,
        imageGroupIsFirst: items[0] === message
      })
      continue
    }

    if (emitted.has(key)) continue
    emitted.add(key)

    output.push({
      ...items[0],
      imageGroupKey: key,
      imageGroupItems: items,
      imageGroupProtocolCount: protocolCount,
      imageGroupCollapsed: true
    })
  }

  return output
}

export const findImageGroupKeyByMessageId = (messages, messageId) => {
  const target = String(messageId ?? '').trim()
  if (!target) return ''
  const message = (Array.isArray(messages) ? messages : []).find(
    (item) => String(item?.id ?? '').trim() === target
  )
  return buildImageGroupKey(message)
}
