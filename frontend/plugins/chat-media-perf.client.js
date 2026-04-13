import { createPerfTrace, getLatestResourceTiming } from '~/lib/chat/perf-logger'

const CHAT_LAZY_SRC_EVENT = 'chat-lazy-src:start'
const CHAT_LAZY_ROOT_MARGIN = '240px 0px 520px 0px'

const nextRenderTick = (callback) => {
  if (typeof window === 'undefined') {
    setTimeout(callback, 0)
    return
  }
  if (typeof window.requestAnimationFrame !== 'function') {
    window.setTimeout(callback, 0)
    return
  }
  window.requestAnimationFrame(() => {
    window.setTimeout(callback, 0)
  })
}

const readImageSrc = (element) => {
  return String(
    element?.currentSrc
    || element?.getAttribute?.('src')
    || element?.src
    || ''
  ).trim()
}

const normalizeBindingValue = (value) => {
  if (!value || typeof value !== 'object') {
    return { kind: 'image', meta: {} }
  }
  return {
    kind: String(value.kind || 'image').trim() || 'image',
    meta: value.meta && typeof value.meta === 'object' ? { ...value.meta } : {}
  }
}

const ensurePerfState = (element) => {
  if (!element.__chatMediaPerfState) {
    element.__chatMediaPerfState = {
      src: '',
      trace: null,
      finalized: true,
      onLoad: null,
      onError: null,
      onLazyStart: null
    }
  }
  return element.__chatMediaPerfState
}

const normalizeLazySrc = (value) => {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'object') return String(value.src || '').trim()
  return String(value || '').trim()
}

const ensureLazySrcState = (element) => {
  if (!element.__chatLazySrcState) {
    element.__chatLazySrcState = {
      src: '',
      loadedSrc: '',
      observer: null,
      timer: null
    }
  }
  return element.__chatLazySrcState
}

const cleanupLazySrcObserver = (element) => {
  const state = element?.__chatLazySrcState
  if (!state) return
  if (state.observer) {
    try { state.observer.disconnect() } catch {}
    state.observer = null
  }
  if (state.timer) {
    try { clearTimeout(state.timer) } catch {}
    state.timer = null
  }
}

const applyLazySrc = (element, reason = '') => {
  const state = element?.__chatLazySrcState
  const src = String(state?.src || '').trim()
  if (!element || !src) return
  if (state.loadedSrc === src && readImageSrc(element) === src) return

  state.loadedSrc = src
  element.setAttribute('src', src)
  try {
    element.dispatchEvent(new CustomEvent(CHAT_LAZY_SRC_EVENT, {
      detail: { src, reason }
    }))
  } catch {}
}

const updateLazySrc = (element, binding, reason = '') => {
  const state = ensureLazySrcState(element)
  const nextSrc = normalizeLazySrc(binding?.value)

  cleanupLazySrcObserver(element)
  state.src = nextSrc

  if (!nextSrc) {
    state.loadedSrc = ''
    try { element.removeAttribute('src') } catch {}
    return
  }

  if (state.loadedSrc !== nextSrc || readImageSrc(element) !== nextSrc) {
    state.loadedSrc = ''
    try { element.removeAttribute('src') } catch {}
    try { element.setAttribute('data-chat-lazy-src', nextSrc) } catch {}
  }

  if (typeof window === 'undefined' || typeof window.IntersectionObserver !== 'function') {
    state.timer = setTimeout(() => applyLazySrc(element, `${reason}:fallback`), 0)
    return
  }

  state.observer = new window.IntersectionObserver((entries) => {
    const entry = entries?.[0]
    if (!entry?.isIntersecting) return
    cleanupLazySrcObserver(element)
    applyLazySrc(element, `${reason}:intersect`)
  }, {
    root: null,
    rootMargin: CHAT_LAZY_ROOT_MARGIN,
    threshold: 0.01
  })
  state.observer.observe(element)
}

const finalizeTracking = (element, status, reason = '') => {
  const state = element?.__chatMediaPerfState
  if (!state?.trace || state.finalized) return

  const currentSrc = readImageSrc(element) || state.src
  state.trace.log(status === 'load' ? 'resource:load' : 'resource:error', {
    reason,
    currentSrc,
    complete: !!element?.complete,
    naturalWidth: Number(element?.naturalWidth || 0),
    naturalHeight: Number(element?.naturalHeight || 0),
    ...getLatestResourceTiming(currentSrc)
  })
  state.finalized = true
}

const beginTracking = (element, binding, reason = '') => {
  const state = ensurePerfState(element)
  const src = readImageSrc(element)
  if (!src) return
  if (state.src === src && state.trace && !state.finalized) return

  const { kind, meta } = normalizeBindingValue(binding?.value)
  state.src = src
  state.finalized = false
  state.trace = createPerfTrace('chat-media-ui', {
    kind,
    src,
    ...meta
  })
  state.trace.log('resource:start', {
    reason,
    complete: !!element?.complete,
    loading: String(element?.getAttribute?.('loading') || '').trim(),
    decoding: String(element?.getAttribute?.('decoding') || '').trim()
  })

  if (element?.complete) {
    nextRenderTick(() => finalizeTracking(element, 'load', 'complete-sync'))
  }
}

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.directive('chat-media-perf', {
    mounted(element, binding) {
      const state = ensurePerfState(element)
      state.onLoad = () => finalizeTracking(element, 'load', 'load-event')
      state.onError = () => finalizeTracking(element, 'error', 'error-event')
      state.onLazyStart = () => beginTracking(element, binding, 'lazy-src')
      element.addEventListener('load', state.onLoad)
      element.addEventListener('error', state.onError)
      element.addEventListener(CHAT_LAZY_SRC_EVENT, state.onLazyStart)
      beginTracking(element, binding, 'mounted')
    },
    updated(element, binding) {
      const state = ensurePerfState(element)
      const nextSrc = readImageSrc(element)
      if (!nextSrc) return
      if (nextSrc !== state.src) {
        beginTracking(element, binding, 'updated-src')
        return
      }
      if (element?.complete && !state.finalized) {
        nextRenderTick(() => finalizeTracking(element, 'load', 'updated-complete'))
      }
    },
    beforeUnmount(element) {
      const state = element?.__chatMediaPerfState
      if (state?.onLoad) element.removeEventListener('load', state.onLoad)
      if (state?.onError) element.removeEventListener('error', state.onError)
      if (state?.onLazyStart) element.removeEventListener(CHAT_LAZY_SRC_EVENT, state.onLazyStart)
      if (state?.trace && !state.finalized) {
        finalizeTracking(element, element?.complete ? 'load' : 'error', 'before-unmount')
      }
      delete element.__chatMediaPerfState
    }
  })

  nuxtApp.vueApp.directive('chat-lazy-src', {
    mounted(element, binding) {
      updateLazySrc(element, binding, 'mounted')
    },
    updated(element, binding) {
      const state = ensureLazySrcState(element)
      const nextSrc = normalizeLazySrc(binding?.value)
      if (nextSrc === state.src && (state.loadedSrc === nextSrc || !readImageSrc(element))) {
        return
      }
      updateLazySrc(element, binding, 'updated')
    },
    beforeUnmount(element) {
      cleanupLazySrcObserver(element)
      delete element.__chatLazySrcState
    }
  })
})
