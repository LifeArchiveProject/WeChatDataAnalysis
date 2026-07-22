import { ref, computed, unref, onBeforeUnmount } from 'vue'
import { gsap } from 'gsap'
import { useReducedMotion } from './useReducedMotion'

/**
 * 数字滚动（count-up）动画。
 *
 * const { display, play } = useCountUp(() => props.total, { duration: 1.2 })
 * 模板中使用 {{ display }}（已做 toLocaleString 千分位格式化），
 * 卡片入场（isActive 首次为 true）时调用 play()。
 * reduced-motion 偏好命中时 play() 直接呈现终值。
 */
export function useCountUp(source, options = {}) {
  const {
    duration = 1.2,
    ease = 'power2.out',
    delay = 0,
    decimals = 0,
    format = (n) => Number(n).toLocaleString('zh-CN', {
      maximumFractionDigits: decimals,
      minimumFractionDigits: decimals,
    }),
  } = options

  const reducedMotion = useReducedMotion()
  const current = ref(0)
  let tween = null

  const targetValue = () => {
    const v = Number(typeof source === 'function' ? source() : unref(source))
    return Number.isFinite(v) ? v : 0
  }

  const play = () => {
    const target = targetValue()
    if (tween) { tween.kill(); tween = null }
    if (reducedMotion.value) {
      current.value = target
      return
    }
    const obj = { v: current.value }
    tween = gsap.to(obj, {
      v: target,
      duration,
      ease,
      delay,
      onUpdate: () => { current.value = obj.v },
      onComplete: () => { current.value = target; tween = null },
    })
  }

  // 立即定格到终值（跳过/离屏时使用）。
  const finish = () => {
    if (tween) { tween.kill(); tween = null }
    current.value = targetValue()
  }

  onBeforeUnmount(() => { if (tween) tween.kill() })

  const display = computed(() => format(decimals > 0 ? current.value : Math.round(current.value)))
  return { display, value: current, play, finish }
}
