import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useChatExport } from '../composables/chat/useChatExport'

const scopes = []
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()) })

function setup({ types = ['link'], privacy = false, transcribe = false, available = true } = {}) {
  const api = {
    createChatExport: vi.fn().mockResolvedValue({ job: null }),
    getVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available, reason: '请先下载模型' }),
  }
  const scope = effectScope()
  scopes.push(scope)
  const state = scope.run(() => useChatExport({ api, apiBase: ref(''), contacts: ref([]),
    selectedAccount: ref('test-account'), selectedContact: ref(null), privacyMode: ref(privacy) }))
  state.exportSelectedUsernames.value = ['friend']
  state.exportFolderHandle.value = {}
  state.exportMessageTypes.value = types
  state.exportTranscribeVoice.value = transcribe
  return { state, api }
}

describe('导出媒体与语音模型选项', () => {
  it.each([
    { format: 'html', privacy: false, expected: true },
    { format: 'json', privacy: false, expected: false },
    { format: 'html', privacy: true, expected: false },
  ])('远程缩略图仅在 HTML 且非隐私模式启用：%j', async ({ format, privacy, expected }) => {
    const { state, api } = setup({ privacy })
    state.exportFormat.value = format
    state.exportDownloadRemoteMedia.value = true
    await state.startChatExport()
    expect(api.createChatExport).toHaveBeenCalledWith(expect.objectContaining({ download_remote_media: expected }))
  })

  it('只选择链接和小程序时仍打包本地图片', async () => {
    const { state, api } = setup()
    await state.startChatExport()
    expect(api.createChatExport).toHaveBeenCalledWith(expect.objectContaining({
      include_media: true, media_kinds: ['image'], download_remote_media: false, transcribe_voice: false,
    }))
  })

  it.each([
    { privacy: false, types: ['voice'], expected: true },
    { privacy: true, types: ['voice'], expected: false },
    { privacy: false, types: ['text'], expected: false },
  ])('转写选项遵循语音筛选和隐私模式：%j', async ({ privacy, types, expected }) => {
    const { state, api } = setup({ privacy, types, transcribe: true })
    await state.startChatExport()
    expect(api.createChatExport).toHaveBeenCalledWith(expect.objectContaining({ transcribe_voice: expected }))
    expect(api.getVoiceTranscriptionStatus).toHaveBeenCalledTimes(expected ? 1 : 0)
  })

  it('模型不可用时给出原因，不创建转写导出任务', async () => {
    const { state, api } = setup({ types: ['voice'], transcribe: true, available: false })
    await state.startChatExport()
    expect(api.createChatExport).not.toHaveBeenCalled()
    expect(state.exportError.value).toBe('请先下载模型')
  })
})
