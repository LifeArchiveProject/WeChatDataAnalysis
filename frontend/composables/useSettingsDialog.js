export const useSettingsDialog = () => {
  const open = useState('settings-dialog-open', () => false)

  const openDialog = () => {
    open.value = true
  }

  const closeDialog = () => {
    open.value = false
  }

  return {
    open,
    openDialog,
    closeDialog,
  }
}
