/** 套餐弹窗的开关（与 useSettingsDialog 同形）。reason: 'manual' | 'quota' | 'frozen' */
export const usePlanWindow = () => {
  const open = useState('plan-window-open', () => false)
  const reason = useState('plan-window-reason', () => 'manual')
  const openPlanWindow = (why = 'manual') => { reason.value = String(why || 'manual'); open.value = true }
  const closePlanWindow = () => { open.value = false }
  return { open, reason, openPlanWindow, closePlanWindow }
}
