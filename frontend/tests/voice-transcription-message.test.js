import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import MessageContent from '~/components/chat/MessageContent.vue'
import ChatHistoryFloatingWindows from '~/components/chat/ChatHistoryFloatingWindows.vue'
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
  nativeVoiceTranscriptionStatusKnown: true,
  nativeVoiceTranscriptionStatusLoading: false,
  nativeVoiceTranscriptionAvailable: true,
  nativeVoiceTranscriptionUnavailableReason: '',
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
        voiceTranscript: '缓存恢复的简体文字',
        voiceTranscriptModel: 'tiny'
      })
    })

    expect(wrapper.text()).toContain('缓存恢复的简体文字')
    expect(wrapper.text()).toContain('本项目转写')
    expect(wrapper.get('[data-transcript-source="project"]').attributes('title')).toContain('tiny')
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
      message: makeMessage({ voiceTranscriptStatus: 'success', voiceTranscript: '识别成功的文字', voiceTranscriptModel: 'medium' })
    })
    expect(wrapper.text()).toContain('识别成功的文字')
    expect(wrapper.text()).toContain('本项目转写')

    const failedMessage = makeMessage({
      voiceTranscriptStatus: 'error',
      voiceTranscriptError: 'CUDA 不可用，已回退失败'
    })
    await wrapper.setProps({ message: failedMessage })
    expect(wrapper.text()).toContain('CUDA 不可用，已回退失败')
    expect(wrapper.text()).toContain('重试')

    await wrapper.get('.wechat-voice-transcript__retry').trigger('click')
    await nextTick()
    expect(state.transcribeVoice).toHaveBeenLastCalledWith(failedMessage)
  })

  it('微信原生桥接不可用时不提供主转写按钮并显示原因', () => {
    const state = {
      ...makeState(),
      nativeVoiceTranscriptionAvailable: false,
      nativeVoiceTranscriptionUnavailableReason: '当前微信版本暂不支持微信原生语音转文字。请使用微信 4.1.12.26，并完全退出、重新启动微信后再试。'
    }
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: { state, message: makeMessage() }
    })

    expect(wrapper.find('.wechat-voice-transcript__action').exists()).toBe(false)
    expect(wrapper.text()).toContain('请使用微信 4.1.12.26')
  })

  it('桥接要求重启时隐藏错误态重试按钮并显示权威状态', () => {
    const state = {
      ...makeState(),
      nativeVoiceTranscriptionAvailable: false,
      nativeVoiceTranscriptionStatusLoading: false,
      nativeVoiceTranscriptionUnavailableReason: '桥接状态已失效。请完全退出微信，重启本应用（开发模式下同时重启后端）后，再重新打开并登录微信。'
    }
    const wrapper = mount(MessageContent, {
      ...mountOptions,
      props: {
        state,
        message: makeMessage({
          voiceTranscriptStatus: 'error',
          voiceTranscriptError: '微信原生回调状态不确定。'
        })
      }
    })

    expect(wrapper.find('.wechat-voice-transcript__retry').exists()).toBe(false)
    expect(wrapper.text()).toContain('完全退出微信')
    expect(wrapper.text()).toContain('重启本应用')
  })

  it('合并转发浮窗在不提供新转写操作时仍展示微信原生文字', () => {
    const state = {
      ...makeState(),
      floatingWindows: [{
        id: 'history-1',
        kind: 'chatHistory',
        title: '聊天记录',
        x: 10,
        y: 10,
        zIndex: 10,
        width: 420,
        height: 500,
        records: [makeMessage({
          voiceTranscriptStatus: '',
          voiceTranscript: '微信已经转写的合成文字',
          voiceTranscriptModel: 'wechat-native'
        })]
      }],
      focusFloatingWindow: vi.fn(),
      startFloatingWindowDrag: vi.fn(),
      closeFloatingWindow: vi.fn()
    }
    const wrapper = mount(ChatHistoryFloatingWindows, {
      ...mountOptions,
      props: { state }
    })

    expect(wrapper.text()).toContain('微信已经转写的合成文字')
    expect(wrapper.text()).toContain('微信原生转写')
    expect(wrapper.get('[data-transcript-source="wechat"]').attributes('title')).toContain('微信客户端原生')
    expect(wrapper.find('.wechat-voice-transcript__action').exists()).toBe(false)
    expect(wrapper.find('.wechat-voice-transcript__retry').exists()).toBe(false)
  })
})
