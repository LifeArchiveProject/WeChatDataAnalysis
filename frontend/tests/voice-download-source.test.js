import { afterEach, expect, it, vi } from 'vitest'
import { useApi } from '~/composables/useApi'

vi.mock('~/stores/chatAccounts', () => ({
  useChatAccountsStore: () => ({ applySourceResponse: vi.fn() })
}))

afterEach(() => vi.unstubAllGlobals())

it('下载源切换通过现有设置接口发送，并保留模型与设备设置请求', async () => {
  const fetch = vi.fn(async () => ({ status: 'success' }))
  vi.stubGlobal('useApiBase', () => '/api')
  vi.stubGlobal('$fetch', fetch)
  const api = useApi()
  for (const data of [
    { download_source: 'hf-mirror' },
    { download_source: 'huggingface' },
    { model: 'turbo' },
    { device: 'cpu' }
  ]) {
    await api.setVoiceTranscriptionSettings(data)
    expect(fetch).toHaveBeenLastCalledWith('/chat/media/voice/transcription/settings', expect.objectContaining({
      method: 'PUT', body: data
    }))
  }
})
