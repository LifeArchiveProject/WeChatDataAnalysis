export const ERROR_LOG_GUIDANCE = '如需开发者协助，请打开左侧边栏的“设置”，在“桌面行为”中找到“日志文件”，点击“打开日志”，然后将日志文件发送给开发者。'

export const ERROR_LOG_MANUAL_GUIDANCE = '如需开发者协助，请记录此错误；若“日志文件”一栏显示了文件路径，请按该路径手动找到日志文件并发送给开发者。'

export const withErrorLogGuidance = (message) => {
  const text = String(message || '').trim() || '操作失败'
  if (text.includes(ERROR_LOG_GUIDANCE)) return text
  return `${text}\n\n${ERROR_LOG_GUIDANCE}`
}

export const showErrorAlert = (message) => {
  if (!process.client || typeof window === 'undefined') return
  window.alert(withErrorLogGuidance(message))
}
