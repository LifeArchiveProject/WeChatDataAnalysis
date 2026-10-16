import { ref } from 'vue'

// 全局单例：整个应用只挂一个 matchMedia 监听。
let _prefersReducedMotion = null

/**
 * 用户系统级"减少动态效果"偏好。
 * 命中时各卡片应跳过入场动画（直接呈现终态）并暂停循环动画。
 */
export function useReducedMotion() {
  if (_prefersReducedMotion) return _prefersReducedMotion
  const prefers = ref(false)
  _prefersReducedMotion = prefers
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    prefers.value = mq.matches
    const onChange = (e) => { prefers.value = e.matches }
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onChange)
    else if (typeof mq.addListener === 'function') mq.addListener(onChange)
  }
  return prefers
}
