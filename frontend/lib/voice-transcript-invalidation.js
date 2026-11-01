export const PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT = 'wcda:project-voice-transcripts-invalidated'

export const notifyProjectVoiceTranscriptsInvalidated = (detail = {}) => {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return false
  window.dispatchEvent(new CustomEvent(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT, {
    detail: detail && typeof detail === 'object' ? detail : {}
  }))
  return true
}
