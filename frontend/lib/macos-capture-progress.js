// The capture request can take minutes. Readiness belongs to its transaction,
// not to a timer or a ready file left by a previous login.
const capturePhases = new Set(['waiting_authorization', 'monitoring', 'captured', 'validating', 'restoring'])

export function macosCaptureProgressMessage(ready, phase) {
  if (phase === 'captured') {
    return '已捕获密钥并通过消息库与会话库校验，正在完成后续复核。临时微信窗口将按流程关闭，随后恢复腾讯原签名微信；请勿再次登录。'
  }
  if (phase === 'validating') {
    return '正在使用本账号消息库与会话库校验候选密钥。临时微信窗口会关闭并恢复腾讯原签名微信；请勿再次登录。'
  }
  if (phase === 'restoring') {
    return '正在关闭临时微信并恢复腾讯原签名微信，请勿再次登录；恢复尚未完成，请等待本次请求结果。'
  }
  return ready === true && phase !== 'waiting_authorization'
    ? '监测已就绪，可以重新登录。请只在当前微信中登录同一个账号；捕获后临时微信窗口会关闭，并恢复腾讯原签名微信。'
    : '正在准备监测，请完成管理员授权；监测就绪前请不要登录。'
}

export async function followMacosCapture({ start, getStatus, transactionId, isActive, onProgress, wait = (ms) => new Promise(resolve => setTimeout(resolve, ms)) }) {
  const monitor = new AbortController()
  let finished = false
  const completion = (async () => {
    try {
      return { value: await start() }
    } catch (error) {
      return { error }
    } finally {
      // Mark completion directly, before a concurrently resolved status can publish.
      finished = true
      monitor.abort()
    }
  })()
  while (!finished && isActive()) {
    await Promise.race([completion, wait(500)])
    if (finished || !isActive()) break
    try {
      const status = await getStatus({ signal: monitor.signal })
      if (!finished && isActive() && transactionId && status?.transaction_id === transactionId) {
        onProgress(status.monitor_ready === true, capturePhases.has(status.capture_phase) ? status.capture_phase : null)
      }
    } catch {
      // A transient status failure must never be interpreted as permission to log in.
    }
  }
  const outcome = await completion
  if (outcome.error) throw outcome.error
  return outcome.value
}
