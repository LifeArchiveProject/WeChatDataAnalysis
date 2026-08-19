import { beforeEach, describe, expect, it, vi } from 'vitest'

const applySourceResponse = vi.fn()

vi.mock('~/stores/chatAccounts', () => ({
  useChatAccountsStore: () => ({ applySourceResponse })
}))

vi.mock('~/lib/server-error-logging', () => ({
  reportServerError: vi.fn()
}))

const { useApi } = await import('~/composables/useApi')

describe('useApi voice transcription methods', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    globalThis.useApiBase = vi.fn(() => '/api')
    globalThis.$fetch = vi.fn().mockResolvedValue({})
  })

  it('exposes all voice transcription methods to page callers', () => {
    const api = useApi()

    expect(typeof api.getVoiceTranscriptionStatus).toBe('function')
    expect(typeof api.setVoiceTranscriptionDevice).toBe('function')
    expect(typeof api.transcribeChatVoice).toBe('function')
    expect(typeof api.lookupChatVoiceTranscriptionCache).toBe('function')
  })
})
