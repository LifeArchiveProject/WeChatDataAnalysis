const roundPerfMs = (value) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  return Number(numeric.toFixed(1))
}

const isDesktopShell = () => {
  if (typeof window === 'undefined') return false
  return !!window.wechatDesktop?.__brand
}

export const nowPerfMs = () => {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

export const logPerfChannel = (channel, phase, details = {}) => {
  const payload = { ...details }
  if (isDesktopShell()) {
    try {
      window.wechatDesktop?.logDebug?.(channel, phase, payload)
    } catch {}
  }
  try {
    console.info(`[${channel}] ${phase}`, payload)
  } catch {}
}

export const createPerfTrace = (channel, baseDetails = {}) => {
  const traceId = `${channel}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const startedAt = nowPerfMs()
  let lastAt = startedAt

  return {
    id: traceId,
    log(phase, details = {}) {
      const now = nowPerfMs()
      const payload = {
        ...baseDetails,
        ...details,
        traceId,
        elapsedMs: roundPerfMs(now - startedAt),
        deltaMs: roundPerfMs(now - lastAt)
      }
      lastAt = now
      logPerfChannel(channel, phase, payload)
      return payload
    }
  }
}

export const getLatestResourceTiming = (resourceUrl) => {
  const url = String(resourceUrl || '').trim()
  if (!url || typeof performance === 'undefined' || typeof performance.getEntriesByName !== 'function') {
    return {}
  }

  try {
    const entries = performance.getEntriesByName(url)
    if (!entries?.length) return {}
    const entry = entries[entries.length - 1]
    return {
      resourceDurationMs: roundPerfMs(entry.duration),
      fetchStartMs: roundPerfMs(entry.fetchStart),
      responseEndMs: roundPerfMs(entry.responseEnd),
      transferSize: Number.isFinite(entry.transferSize) ? Number(entry.transferSize) : null,
      encodedBodySize: Number.isFinite(entry.encodedBodySize) ? Number(entry.encodedBodySize) : null,
      decodedBodySize: Number.isFinite(entry.decodedBodySize) ? Number(entry.decodedBodySize) : null,
      initiatorType: String(entry.initiatorType || '').trim()
    }
  } catch {
    return {}
  }
}
