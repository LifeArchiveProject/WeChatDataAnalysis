import { computed, onMounted, onUnmounted, ref } from 'vue'

const STORAGE_KEY = 'chat-agent-panel-width'
const DEFAULT_WIDTH = 440

export function useAgentPanelResize(panel, expanded) {
  const preferred = ref(DEFAULT_WIDTH), available = ref(1200), reserved = ref(320), resizing = ref(false)
  let drag, observer
  const maximum = computed(() => Math.max(0, available.value - reserved.value))
  const minimum = computed(() => Math.min(320, maximum.value))
  const clamp = value => Math.round(Math.min(maximum.value, Math.max(minimum.value, value)))
  const width = computed(() => clamp(preferred.value))
  const save = () => { try { localStorage.setItem(STORAGE_KEY, String(preferred.value)) } catch { /* 隐私模式不影响拖动。 */ } }
  const measure = () => {
    const parent = panel.value?.parentElement
    available.value = Math.min(window.innerWidth, parent?.getBoundingClientRect().width || window.innerWidth)
    // 桌面并排时为聊天正文及其他侧栏留出空间；小窗口使用覆盖式侧栏。
    const others = parent?.querySelector('.chat-page-main') ? [...parent.children].filter(element => element !== panel.value && !element.classList.contains('chat-page-main') && getComputedStyle(element).position !== 'absolute' && getComputedStyle(element).position !== 'fixed').reduce((sum, element) => sum + element.getBoundingClientRect().width, 0) : 0
    reserved.value = window.innerWidth > 1000 ? Math.min(320 + others, Math.max(0, available.value - 320)) : 24
  }
  const finish = event => {
    if (!drag || (event?.pointerId != null && event.pointerId !== drag.id)) return
    const { target, id, userSelect, cursor } = drag
    drag = null; resizing.value = false
    document.body.style.userSelect = userSelect; document.body.style.cursor = cursor
    if (target.hasPointerCapture?.(id)) target.releasePointerCapture(id)
    save()
  }
  const start = event => {
    if (expanded.value || event.button !== 0 || drag) return
    event.preventDefault(); measure()
    drag = { x: event.clientX, width: width.value, target: event.currentTarget, id: event.pointerId, userSelect: document.body.style.userSelect, cursor: document.body.style.cursor }
    event.currentTarget.setPointerCapture?.(event.pointerId)
    document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize'
    resizing.value = true
  }
  const move = event => { if (drag && event.pointerId === drag.id) preferred.value = clamp(drag.width + drag.x - event.clientX) }
  const reset = () => { preferred.value = DEFAULT_WIDTH; save() }
  const keyboard = event => {
    const step = event.shiftKey ? 80 : 20
    const values = { ArrowLeft: width.value + step, ArrowRight: width.value - step, Home: minimum.value, End: maximum.value }
    if (event.key in values) { event.preventDefault(); preferred.value = clamp(values[event.key]); save() }
    else if (event.key === 'Enter') { event.preventDefault(); reset() }
  }
  onMounted(() => {
    try { const stored = Number(localStorage.getItem(STORAGE_KEY)); if (Number.isFinite(stored) && stored >= 320) preferred.value = stored } catch { /* 无本地存储时使用默认宽度。 */ }
    measure(); observer = new ResizeObserver(measure)
    if (panel.value?.parentElement) observer.observe(panel.value.parentElement)
    panel.value?.parentElement?.querySelectorAll('.session-list-panel, .resource-sidebar, .voice-transcription-sidebar').forEach(element => observer.observe(element))
    window.addEventListener('resize', measure); window.addEventListener('blur', finish)
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', finish); window.addEventListener('pointercancel', finish)
  })
  onUnmounted(() => {
    finish(); observer?.disconnect()
    window.removeEventListener('resize', measure); window.removeEventListener('blur', finish)
    window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', finish); window.removeEventListener('pointercancel', finish)
  })
  return { width, minimum, maximum, resizing, start, finish, reset, keyboard }
}
