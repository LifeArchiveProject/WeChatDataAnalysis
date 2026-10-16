const isDesktopShell = () => {
  if (typeof window === 'undefined') return false
  return !!window.wechatDesktop?.__brand
}

const formatError = (error) => {
  if (!error) return ''
  if (error instanceof Error) {
    return {
      name: String(error.name || 'Error'),
      message: String(error.message || ''),
      stack: String(error.stack || '')
    }
  }
  if (typeof error === 'object') {
    try {
      return JSON.parse(JSON.stringify(error))
    } catch {}
  }
  return String(error)
}

const logDesktopDebug = (phase, details = {}) => {
  if (!isDesktopShell()) return
  try {
    window.wechatDesktop?.logDebug?.('nuxt-bootstrap', phase, {
      href: String(window.location?.href || ''),
      ...details
    })
  } catch {}
  try {
    console.info(`[nuxt-bootstrap] ${phase}`, details)
  } catch {}
}

export default defineNuxtPlugin((nuxtApp) => {
  logDesktopDebug('plugin:setup')

  if (typeof window !== 'undefined') {
    window.addEventListener('error', (event) => {
      logDesktopDebug('window:error', {
        message: String(event?.message || ''),
        filename: String(event?.filename || ''),
        lineno: Number(event?.lineno || 0),
        colno: Number(event?.colno || 0),
        error: formatError(event?.error)
      })
    })

    window.addEventListener('unhandledrejection', (event) => {
      logDesktopDebug('window:unhandledrejection', {
        reason: formatError(event?.reason)
      })
    })
  }

  nuxtApp.hook('app:created', () => {
    logDesktopDebug('app:created')
  })

  nuxtApp.hook('app:beforeMount', () => {
    logDesktopDebug('app:beforeMount')
  })

  nuxtApp.hook('app:mounted', () => {
    logDesktopDebug('app:mounted')
  })

  nuxtApp.hook('page:start', () => {
    logDesktopDebug('page:start')
  })

  nuxtApp.hook('page:finish', () => {
    logDesktopDebug('page:finish')
  })

  nuxtApp.hook('vue:error', (error, _instance, info) => {
    logDesktopDebug('vue:error', {
      info: String(info || ''),
      error: formatError(error)
    })
  })
})
