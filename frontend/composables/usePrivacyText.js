import { storeToRefs } from 'pinia'
import { usePrivacyStore } from '~/stores/privacy'

// 年度总结隐私模式的文字脱敏：
// - 文字一律替换为等长星号（不再用 CSS 模糊——大字号下模糊仍可辨认）
// - 数字与空白保留（数字不属于隐私口径），标点一并打星以免句式泄义
// - 头像/表情包等图像仍走 CSS 模糊（见 tailwind.css 的 wrapped-privacy-* 规则）
export function usePrivacyText() {
  const privacyStore = usePrivacyStore()
  const { privacyMode } = storeToRefs(privacyStore)

  // 任意文本：非数字、非空白字符全部替换为 '*'
  const star = (value) => {
    const s = String(value ?? '')
    if (!privacyMode.value || !s) return s
    return s.replace(/[^\d\s]/gu, '*')
  }

  // 名字类：优先用后端 maskedName（已是全星号），否则本地全字符打星。
  // 注意与 star() 的区别——名字里的数字也属于身份信息，一并打星。
  const starName = (display, masked) => {
    if (!privacyMode.value) return String(display ?? '')
    const m = String(masked || '').trim()
    if (m) return m
    const s = String(display ?? '').trim()
    return s ? '*'.repeat(Math.max(1, Math.min([...s].length, 6))) : s
  }

  return { privacyMode, star, starName }
}
