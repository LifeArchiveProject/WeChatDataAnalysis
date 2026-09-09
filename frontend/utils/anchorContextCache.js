// 仅保留少量短期上下文；预读和点击定位共用同一个请求，不持久化聊天内容。
export const createAnchorContextCache = (fetchContext, { ttl = 30000, limit = 8 } = {}) => {
  const entries = new Map()
  const read = params => {
    const key = JSON.stringify([params.account, params.username, params.anchor_id])
    const existing = entries.get(key)
    if (existing && Date.now() - existing.created < ttl) return existing.promise
    const entry = { created: Date.now() }
    entry.promise = Promise.resolve().then(() => fetchContext(params)).catch(error => {
      if (entries.get(key) === entry) entries.delete(key)
      throw error
    })
    entries.delete(key)
    entries.set(key, entry)
    while (entries.size > limit) entries.delete(entries.keys().next().value)
    return entry.promise
  }
  return { read, clear: () => entries.clear() }
}
