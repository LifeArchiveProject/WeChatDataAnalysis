export const useAdvancedFeaturesDialog = () => {
  const open = useState('advanced-features-dialog-open', () => false)

  const openDialog = () => { open.value = true }
  const closeDialog = () => { open.value = false }

  return { open, openDialog, closeDialog }
}
