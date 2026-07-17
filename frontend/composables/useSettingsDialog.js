export const useSettingsDialog = () => {
  const open = useState('settings-dialog-open', () => false)
  const focusTarget = useState('settings-dialog-focus-target', () => '')

  const openDialog = (target = '') => {
    focusTarget.value = String(target || '').trim()
    open.value = true
  }

  const closeDialog = () => {
    open.value = false
    focusTarget.value = ''
  }

  return {
    open,
    focusTarget,
    openDialog,
    closeDialog,
  }
}
