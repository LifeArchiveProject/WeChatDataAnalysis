import { defineStore } from 'pinia'

import { readPrivacyMode, writePrivacyMode } from '~/utils/privacy-mode'

export const usePrivacyStore = defineStore('privacy', () => {
  const privacyMode = ref(false)
  const initialized = ref(false)

  const init = () => {
    if (initialized.value) return
    initialized.value = true
    privacyMode.value = readPrivacyMode(false)
  }

  const set = (enabled) => {
    privacyMode.value = !!enabled
    writePrivacyMode(privacyMode.value)
  }

  const toggle = () => {
    set(!privacyMode.value)
  }

  return {
    privacyMode,
    init,
    set,
    toggle,
  }
})

