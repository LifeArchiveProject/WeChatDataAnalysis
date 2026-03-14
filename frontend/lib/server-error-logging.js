import { useApiBase } from '~/composables/useApiBase'

const FRONTEND_SERVER_ERROR_ENDPOINT = '/admin/log-frontend-server-error'

const normalizeStatus = (value) => {
  const n = Number(value)
  if (!Number.isInteger(n)) return 0
  return n
}

const stringifyDetail = (value) => {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  try {
    return JSON.stringify(value)
  } catch {
    return String(value).trim()
  }
}

const currentOrigin = () => {
  if (!process.client || typeof window === 'undefined') return ''
  try {
    return String(window.location?.origin || '').trim()
  } catch {
    return ''
  }
}

const normalizeBasePath = (apiBase) => {
  const raw = String(apiBase || '').trim()
  if (!raw) return '/api'
  if (/^https?:\/\//i.test(raw)) {
    try {
      const u = new URL(raw)
      return u.pathname.replace(/\/+$/, '') || '/'
    } catch {
      return '/api'
    }
  }
  return raw.replace(/\/+$/, '') || '/'
}

const normalizePathname = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    return new URL(raw).pathname.replace(/\/+$/, '')
  } catch {
    return raw.split(/[?#]/, 1)[0].replace(/\/+$/, '')
  }
}

export const isServerErrorStatus = (status) => normalizeStatus(status) >= 500

export const resolveRequestUrl = (requestUrl, apiBase = '') => {
  const raw = String(requestUrl || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) return raw

  const origin = currentOrigin()
  if (!origin) return raw

  if (raw.startsWith('/')) {
    const prefix = normalizeBasePath(apiBase)
    const combined = raw === prefix || raw.startsWith(`${prefix}/`) ? raw : `${prefix}${raw}`
    if (/^https?:\/\//i.test(String(apiBase || '').trim())) {
      try {
        const baseUrl = new URL(String(apiBase).trim())
        return new URL(combined, `${baseUrl.origin}/`).toString()
      } catch {
        return new URL(combined, origin).toString()
      }
    }
    return new URL(combined, origin).toString()
  }

  if (/^https?:\/\//i.test(String(apiBase || '').trim())) {
    try {
      const base = String(apiBase).trim()
      return new URL(raw, base.endsWith('/') ? base : `${base}/`).toString()
    } catch {
      return new URL(raw, origin).toString()
    }
  }

  return new URL(raw, origin).toString()
}

const isFrontendServerLogUrl = (requestUrl) => {
  const path = normalizePathname(requestUrl)
  return path.endsWith('/api/admin/log-frontend-server-error') || path.endsWith('/admin/log-frontend-server-error')
}

const extractBackendDetail = (data) => {
  if (data == null) return ''
  if (typeof data === 'string') return data.trim()
  if (typeof data === 'object' && !Array.isArray(data) && Object.prototype.hasOwnProperty.call(data, 'detail')) {
    return stringifyDetail(data.detail)
  }
  return stringifyDetail(data)
}

const resolveApiBase = (apiBase) => {
  const raw = String(apiBase || '').trim()
  if (raw) return raw
  if (!process.client) return ''
  try {
    return String(useApiBase() || '').trim()
  } catch {
    return ''
  }
}

export const extractServerErrorFromError = (error) => {
  const response = error?.response
  return {
    status: normalizeStatus(error?.status ?? response?.status),
    backendDetail: extractBackendDetail(response?._data ?? response?.data ?? error?.data),
    message: String(error?.message || '').trim(),
    requestUrl: String(response?.url || error?.request || '').trim(),
  }
}

export const extractServerErrorDetailFromResponse = async (response) => {
  if (!response || typeof response.clone !== 'function') return ''
  try {
    const clone = response.clone()
    const contentType = String(clone.headers?.get?.('content-type') || '').toLowerCase()
    if (contentType.includes('json')) {
      try {
        const payload = await clone.json()
        return extractBackendDetail(payload)
      } catch {}
    }
    const text = String(await clone.text()).trim()
    if (!text) return ''
    if (contentType.includes('json')) {
      try {
        return extractBackendDetail(JSON.parse(text))
      } catch {}
    }
    return text
  } catch {
    return ''
  }
}

export const reportServerError = async (context = {}) => {
  if (!process.client || typeof window === 'undefined') return false

  const status = normalizeStatus(context.status)
  if (!isServerErrorStatus(status)) return false

  const apiBase = resolveApiBase(context.apiBase)
  const requestUrl = resolveRequestUrl(context.requestUrl, apiBase)
  if (!requestUrl || isFrontendServerLogUrl(requestUrl)) return false

  const endpointUrl = resolveRequestUrl(FRONTEND_SERVER_ERROR_ENDPOINT, apiBase)
  if (!endpointUrl) return false

  const payload = {
    status,
    method: String(context.method || 'GET').trim().toUpperCase() || 'GET',
    request_url: requestUrl,
    message: String(context.message || '').trim(),
    backend_detail: String(context.backendDetail || '').trim(),
    source: String(context.source || '').trim(),
    page_url: String(window.location?.href || '').trim(),
  }

  try {
    await fetch(endpointUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    })
    return true
  } catch {
    return false
  }
}

export const reportServerErrorFromError = async (error, context = {}) => {
  const info = extractServerErrorFromError(error)
  return await reportServerError({
    ...context,
    status: context.status ?? info.status,
    requestUrl: context.requestUrl || info.requestUrl,
    message: context.message || info.message,
    backendDetail: context.backendDetail || info.backendDetail,
  })
}

export const reportServerErrorFromResponse = async (response, context = {}) => {
  const status = normalizeStatus(context.status ?? response?.status)
  if (!isServerErrorStatus(status)) return false
  const backendDetail = context.backendDetail || (await extractServerErrorDetailFromResponse(response))
  return await reportServerError({
    ...context,
    status,
    requestUrl: context.requestUrl || response?.url || '',
    backendDetail,
  })
}
