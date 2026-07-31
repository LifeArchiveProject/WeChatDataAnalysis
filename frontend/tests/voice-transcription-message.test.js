import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import MessageContent from '~/components/chat/MessageContent.vue'
import MessageItem from '~/components/chat/MessageItem.vue'

const makeMessage = (overrides = {}) => ({
  id: 'voice-1',
  serverIdStr: '1234567890123456789',
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

describe('语音消息转写状态', () => {
  it('MessageContent 在 message prop 被替换后立即刷新缓存文字', async () => {
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: { state: makeState(), message: makeMessage() }
    })

    expect(wrapper.text()).toContain('转文字')
    await wrapper.setProps({
      message: makeMessage({
        voiceTranscriptStatus: 'success',
        voiceTranscript: '缓存恢复的简体文字'
      })
    })

    expect(wrapper.text()).toContain('缓存恢复的简体文字')
    expect(wrapper.text()).not.toContain('转文字')
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
    expect(wrapper.text()).toContain('正在转文字')

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
    expect(wrapper.text()).toContain('重试')

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
