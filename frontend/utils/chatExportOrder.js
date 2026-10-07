// Older baselines sorted conversation hashes and did not record presentation order.
// Recover the visible order from the shared catalog without executing its JavaScript.
export const restoreLegacyChatExportOrder = (baseline, catalogText) => {
  if (!baseline || Array.isArray(baseline.conversationOrder)) return baseline
  try {
    const prefix = 'window.__WCE_FOLDER_SESSIONS__='
    const text = String(catalogText || '').trim()
    if (!text.startsWith(prefix)) return baseline
    const catalog = JSON.parse(text.slice(prefix.length).replace(/;\s*$/, ''))
    const byDirectory = new Map(Object.entries(baseline.conversations || {})
      .map(([key, value]) => [value?.directory, key]))
    const order = catalog.items.filter(item => byDirectory.has(item?.convDir))
      .map(item => byDirectory.get(item.convDir))
    return order.length ? { ...baseline, legacyConversationOrder: [...new Set(order)] } : baseline
  } catch {
    return baseline
  }
}
