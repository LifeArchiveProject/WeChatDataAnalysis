import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import MessageContent from '~/components/chat/MessageContent.vue'
import MessageItem from '~/components/chat/MessageItem.vue'
import { updateVoiceTranscriptById } from '~/composables/chat/useChatMessages'
import { mergeMessageTranscriptState } from '~/lib/chat/message-normalizer'

const makeMessage = (overrides = {}) => ({
  id: 'voice-1',
  serverIdStr: '1234567890123456789',
  localId: 42,
  createTime: 1700000000,
  renderType: 'voice',
  sender: '好友',
  senderDisplayName: '好友',
  isSent: false,
  isGroup: false,
  voiceUrl: '/api/chat/media/voice?server_id=1234567890123456789',
  voiceDuration: 3000,
  voiceTranscript: '',
  voiceTranscriptStatus: 'idle',
  voiceTranscriptError: '',
  wechatTranscript: '',
  transcriptSource: '',
  ...overrides
})

const makeState = () => ({
  privacyMode: false,
  voiceTranscriptionStatusKnown: true,
  voiceTranscriptionStatusLoading: false,
  voiceTranscriptionAvailable: true,
  voiceTranscriptionUnavailableReason: '',
  selectedContact: { username: 'wxid_friend' },
  transcribeVoice: vi.fn(),
  getVoiceWidth: () => '96px',
  getVoiceDurationInSeconds: () => 3,
  playVoice: vi.fn(),
  setVoiceRef: vi.fn(),
  playingVoiceId: null,
  openMediaContextMenu: vi.fn(),
  onMessageAvatarMouseEnter: vi.fn(),
  onMessageAvatarMouseLeave: vi.fn(),
  isMentionContactProfileCardForMessage: () => false,
  contactProfileCardOpen: false,
  contactProfileCardMessageId: '',
  highlightServerIdStr: '',
  highlightMessageId: ''
})

const mountOptions = {
  global: {
    stubs: {
      ContactProfileCard: true,
      ChatLocationCard: true,
      FileTypeIcon: true,
      LinkCard: true,
      ErrorNotice: true
    },
    directives: {
      chatLazySrc: () => {},
      chatMediaPerf: () => {}
    }
  }
}

describe('本地辅助识别请求定位', () => {
  it('主动识别请求携带 local_id 和 create_time 上下文', () => {
    const message = makeMessage({ serverIdStr: '0', localId: 42, createTime: 1700000000 })
    const request = {
      server_id: String(message.serverIdStr || message.serverId || '').trim(),
      local_id: Number(message.localId || 0),
      create_time: Number(message.createTime || 0)
    }
    expect(request).toEqual({ server_id: '0', local_id: 42, create_time: 1700000000 })
  })
})

describe('语音消息转写状态', () => {
  it('MessageContent 在 message prop 被替换后立即刷新缓存文字', async () => {
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: { state: makeState(), message: makeMessage() }
    })

    expect(wrapper.text()).toContain('本地辅助识别')
    await wrapper.setProps({
      message: makeMessage({
        voiceTranscriptStatus: 'success',
        voiceTranscript: '缓存恢复的简体文字'
      })
    })

    expect(wrapper.text()).toContain('缓存恢复的简体文字')
    expect(wrapper.text()).not.toContain('转文字')
  })

  it('官方微信转写优先显示，且与本地辅助识别并存', async () => {
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: {
        state: makeState(),
        message: makeMessage({
          wechatTranscript: '微信官方文字',
          transcriptSource: 'wechat',
          voiceTranscriptStatus: 'success',
          voiceTranscript: '本地辅助文字'
        })
      }
    })
    const text = wrapper.text()
    expect(text.indexOf('微信转写')).toBeLessThan(text.indexOf('本地辅助识别'))
    expect(text).toContain('微信官方文字')
    expect(text).toContain('本地辅助文字')
  })

  it('官方转写为空且未开始本地识别时提示切换微信会话', () => {
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: { state: makeState(), message: makeMessage() }
    })

    expect(wrapper.text()).toContain('微信转写尚未同步，请在微信中切换会话后刷新')
    expect(wrapper.text()).not.toContain('微信官方文字')
  })

  it('本地识别状态存在时不显示官方转写未同步提示', async () => {
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: {
        state: makeState(),
        message: makeMessage({ voiceTranscriptStatus: 'loading' })
      }
    })

    expect(wrapper.text()).not.toContain('微信转写尚未同步，请在微信中切换会话后刷新')
    await wrapper.setProps({
      message: makeMessage({ voiceTranscriptStatus: 'error', voiceTranscriptError: '识别失败' })
    })
    expect(wrapper.text()).not.toContain('微信转写尚未同步，请在微信中切换会话后刷新')
  })

  it('本地识别完成后按稳定 id 写回 reset/realtime 替换后的当前对象', async () => {
    let current = [{ id: 'voice-1', voiceTranscriptStatus: 'loading' }]
    let resolveRequest
    const deferred = new Promise((resolve) => { resolveRequest = resolve })
    const run = deferred.then(() => updateVoiceTranscriptById(() => current, 'voice-1', {
      voiceTranscript: '异步成功', voiceTranscriptStatus: 'success'
    }))
    current = [{ id: 'voice-1', voiceTranscriptStatus: 'loading', marker: 'replacement' }]
    resolveRequest()
    await run
    expect(current[0]).toMatchObject({ marker: 'replacement', voiceTranscript: '异步成功', voiceTranscriptStatus: 'success' })
  })

  it('本地识别失败后按稳定 id 写回替换后的当前对象', async () => {
    let current = [{ id: 'voice-1', voiceTranscriptStatus: 'loading' }]
    let rejectRequest
    const deferred = new Promise((_, reject) => { rejectRequest = reject })
    const run = deferred.catch((error) => updateVoiceTranscriptById(() => current, 'voice-1', {
      voiceTranscriptError: error.message, voiceTranscriptStatus: 'error'
    }))
    current = [{ id: 'voice-1', voiceTranscriptStatus: 'loading', marker: 'replacement' }]
    rejectRequest(new Error('识别失败'))
    await run
    expect(current[0]).toMatchObject({ marker: 'replacement', voiceTranscriptError: '识别失败', voiceTranscriptStatus: 'error' })
  })

  it('realtime 同 id 后到官方转写替换对象但保留本地状态', () => {
    const merged = mergeMessageTranscriptState(
      { id: 'voice-1', wechatTranscript: '后来到达的微信文字', transcriptSource: 'wechat', voiceTranscript: '', voiceTranscriptStatus: 'idle' },
      { id: 'voice-1', voiceTranscript: '已有本地文字', voiceTranscriptStatus: 'success', voiceTranscriptLanguage: 'zh' }
    )
    expect(merged.wechatTranscript).toBe('后来到达的微信文字')
    expect(merged.voiceTranscript).toBe('已有本地文字')
    expect(merged.voiceTranscriptStatus).toBe('success')
  })

  it('MessageItem 跟随父级替换消息对象展示 loading、成功、失败和重试', async () => {
    const state = makeState()
    const wrapper = mount(MessageItem, {
      ...mountOptions,
      props: { state, message: makeMessage() }
    })

    await wrapper.get('.wechat-voice-transcript__action').trigger('click')
    expect(state.transcribeVoice).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ message: makeMessage({ voiceTranscriptStatus: 'loading' }) })
    expect(wrapper.text()).toContain('正在本地辅助识别')

    await wrapper.setProps({
      message: makeMessage({ voiceTranscriptStatus: 'success', voiceTranscript: '识别成功的文字' })
    })
    expect(wrapper.text()).toContain('识别成功的文字')

    const failedMessage = makeMessage({
      voiceTranscriptStatus: 'error',
      voiceTranscriptError: 'CUDA 不可用，已回退失败'
    })
    await wrapper.setProps({ message: failedMessage })
    expect(wrapper.text()).toContain('CUDA 不可用，已回退失败')
    expect(wrapper.text()).toContain('重新本地识别')

    await wrapper.get('.wechat-voice-transcript__retry').trigger('click')
    await nextTick()
    expect(state.transcribeVoice).toHaveBeenLastCalledWith(failedMessage, { force: true })
  })

  it('模型缺失且禁止下载时不提供转写按钮并显示原因', () => {
    const state = {
      ...makeState(),
      voiceTranscriptionAvailable: false,
      voiceTranscriptionUnavailableReason: 'Whisper 模型尚未下载到本机缓存。 当前已禁止自动下载。'
    }
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: { state, message: makeMessage() }
    })

    expect(wrapper.find('.wechat-voice-transcript__action').exists()).toBe(false)
    expect(wrapper.text()).toContain('当前已禁止自动下载')
  })
})
