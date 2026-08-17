import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  mergeWechatNativeVoiceTranscript,
  useChatMessages
} from '~/composables/chat/useChatMessages'
import { useApi } from '~/composables/useApi'

vi.mock('~/lib/server-error-logging', () => ({ reportServerError: vi.fn() }))
vi.mock('~/stores/chatAccounts', () => ({
  useChatAccountsStore: () => ({ applySourceResponse: vi.fn() })
}))


const mountChatMessagesState = (api, { realtime = false } = {}) => {
  const selectedAccount = ref('account-a')
  const selectedContact = ref({ username: 'wxid_friend' })
  let state
  const wrapper = mount(defineComponent({
    setup() {
      state = useChatMessages({
        api,
        apiBase: 'http://127.0.0.1:10392/api',
        selectedAccount,
        selectedContact,
        realtimeEnabled: ref(realtime),
        privacyMode: ref(false),
        searchContext: ref({ active: false })
      })
      return () => h('div')
    }
  }))
  return { state, wrapper, selectedAccount, selectedContact }
}

const existingVoice = () => ({
  id: 'voice-1',
  serverIdStr: '9007199254740993',
  localIdStr: '4294967295',
  renderType: 'voice',
  voiceTranscript: '',
  voiceTranscriptStatus: 'idle',
  voiceTranscriptError: '',
  voiceTranscriptLanguage: '',
  voiceTranscriptModel: ''
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const nativeError = (code, message = code) => Object.assign(new Error(message), {
  code,
  data: { detail: { code, message } }
})

const deferred = () => {
  let resolve
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

describe('微信原生转写定向轮询', () => {
  it('pending 后命中时更新 allMessages 中已有语音对象', async () => {
    const api = {
      getNativeVoiceTranscript: vi.fn()
        .mockResolvedValueOnce({
          status: 'pending',
          serverId: '9007199254740993',
          text: '',
          language: '',
          model: ''
        })
        .mockResolvedValueOnce({
          status: 'success',
          serverId: '9007199254740993',
          text: '微信刚生成的文字',
          language: '',
          model: 'wechat-native'
        })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    const result = await state.pollNativeVoiceTranscript(message, {
      requestId: 'request-1',
      maxAttempts: 2,
      intervalMs: 0
    })

    expect(result).toMatchObject({ status: 'success', model: 'wechat-native' })
    expect(api.getNativeVoiceTranscript).toHaveBeenCalledTimes(2)
    expect(api.getNativeVoiceTranscript.mock.calls[0][0]).toMatchObject({
      account: 'account-a',
      server_id: '9007199254740993',
      username: 'wxid_friend',
      local_id: '4294967295',
      request_id: 'request-1'
    })
    expect(state.allMessages.value.wxid_friend).toHaveLength(1)
    expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
      id: 'voice-1',
      voiceTranscript: '微信刚生成的文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptError: '',
      voiceTranscriptModel: 'wechat-native'
    })
    wrapper.unmount()
  })

  it('轮询预算允许微信回调在第 32 次查询才完成', async () => {
    const pending = {
      status: 'pending',
      serverId: '9007199254740993',
      localId: '4294967295',
      requestId: 'request-slow',
      text: '',
      language: '',
      model: ''
    }
    const getNativeVoiceTranscript = vi.fn()
    for (let index = 0; index < 31; index += 1) {
      getNativeVoiceTranscript.mockResolvedValueOnce(pending)
    }
    getNativeVoiceTranscript.mockResolvedValueOnce({
      status: 'success',
      serverId: '9007199254740993',
      localId: '4294967295',
      requestId: 'request-slow',
      text: '较晚返回的微信文字',
      language: '',
      model: 'wechat-native'
    })
    const api = { getNativeVoiceTranscript }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    const result = await state.pollNativeVoiceTranscript(message, {
      requestId: 'request-slow',
      maxAttempts: 32,
      intervalMs: 0
    })

    expect(api.getNativeVoiceTranscript).toHaveBeenCalledTimes(32)
    expect(result).toMatchObject({ status: 'success', text: '较晚返回的微信文字' })
    wrapper.unmount()
  })

  it('realtime 刷新按同一 server_id 更新已有语音而不是只追加新 ID', async () => {
    const api = {
      listChatMessages: vi.fn().mockResolvedValue({
        messages: [{
          id: 'voice-from-realtime-source',
          serverId: '9007199254740993',
          serverIdStr: '9007199254740993',
          renderType: 'voice',
          voiceTranscript: 'realtime 更新的原生文字',
          voiceTranscriptStatus: 'success',
          voiceTranscriptError: '',
          voiceTranscriptLanguage: '',
          voiceTranscriptModel: 'wechat-native'
        }]
      })
    }
    const { state, wrapper } = mountChatMessagesState(api, { realtime: true })
    state.allMessages.value = { wxid_friend: [existingVoice()] }

    await state.refreshRealtimeIncremental()

    expect(state.allMessages.value.wxid_friend).toHaveLength(1)
    expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
      id: 'voice-1',
      voiceTranscript: 'realtime 更新的原生文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native'
    })
    wrapper.unmount()
  })

  it('页面重载后从项目 native cache 恢复 callback-only 结果', async () => {
    const api = {
      lookupNativeVoiceTranscriptionCache: vi.fn().mockResolvedValue({
        status: 'success',
        items: [{
          serverId: '9007199254740993',
          localId: '4294967295',
          text: '刷新后恢复的微信回调文字',
          language: '',
          model: 'wechat-native'
        }]
      }),
      lookupChatVoiceTranscriptionCache: vi.fn().mockResolvedValue({ status: 'success', items: {} }),
      getVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: false }),
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: true })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    state.allMessages.value = { wxid_friend: [existingVoice()] }

    await state.restoreVoiceTranscripts('wxid_friend')

    expect(api.lookupNativeVoiceTranscriptionCache).toHaveBeenCalledWith({
      account: 'account-a',
      username: 'wxid_friend',
      items: [{
        server_id: '9007199254740993',
        local_id: '4294967295'
      }]
    })
    expect(api.lookupChatVoiceTranscriptionCache).not.toHaveBeenCalled()
    expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
      voiceTranscript: '刷新后恢复的微信回调文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native'
    })
    wrapper.unmount()
  })

  it('切换会话中止轮询后解除 loading，并可在返回时从 native cache 恢复', async () => {
    const api = {
      lookupNativeVoiceTranscriptionCache: vi.fn().mockResolvedValue({
        status: 'success',
        items: [{
          serverId: '9007199254740993',
          localId: '4294967295',
          text: '离开会话期间完成的微信文字',
          language: '',
          model: 'wechat-native'
        }]
      }),
      lookupChatVoiceTranscriptionCache: vi.fn(),
      getVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: false }),
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: true })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = {
      ...existingVoice(),
      voiceTranscriptStatus: 'loading',
      voiceTranscriptNativeRequestId: 'request-in-flight'
    }
    state.allMessages.value = { wxid_friend: [message] }

    state.stopNativeVoiceTranscriptPolling()
    expect(message.voiceTranscriptStatus).toBe('idle')
    expect(message.voiceTranscriptNativeRequestId).toBe('request-in-flight')

    await state.restoreVoiceTranscripts('wxid_friend')
    expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
      voiceTranscript: '离开会话期间完成的微信文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native',
      voiceTranscriptNativeRequestId: ''
    })
    expect(api.lookupChatVoiceTranscriptionCache).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('返回会话时恢复 pending requestId 并续轮询到 success，不读取旧 Whisper cache', async () => {
    const api = {
      lookupNativeVoiceTranscriptionCache: vi.fn().mockResolvedValue({
        status: 'success',
        items: [{
          serverId: '9007199254740993',
          localId: '4294967295',
          status: 'pending',
          requestId: 'request-resumed',
          pollAfterMs: 1200
        }]
      }),
      getNativeVoiceTranscript: vi.fn().mockResolvedValue({
        status: 'success',
        serverId: '9007199254740993',
        localId: '4294967295',
        text: '返回会话后继续收到的微信文字',
        model: 'wechat-native'
      }),
      lookupChatVoiceTranscriptionCache: vi.fn().mockResolvedValue({
        status: 'success',
        items: { '9007199254740993': { text: '不应覆盖的旧 Whisper 文字' } }
      }),
      getVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: false }),
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: true })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    state.allMessages.value = { wxid_friend: [existingVoice()] }

    await state.restoreVoiceTranscripts('wxid_friend')
    await vi.waitFor(() => {
      expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
        voiceTranscript: '返回会话后继续收到的微信文字',
        voiceTranscriptStatus: 'success',
        voiceTranscriptModel: 'wechat-native',
        voiceTranscriptNativeRequestId: ''
      })
    })

    expect(api.getNativeVoiceTranscript).toHaveBeenCalledWith(expect.objectContaining({
      account: 'account-a',
      username: 'wxid_friend',
      server_id: '9007199254740993',
      local_id: '4294967295',
      request_id: 'request-resumed'
    }))
    expect(api.lookupChatVoiceTranscriptionCache).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('返回会话时恢复 native error，且不会被旧 Whisper cache 覆盖', async () => {
    const api = {
      lookupNativeVoiceTranscriptionCache: vi.fn().mockResolvedValue({
        status: 'success',
        items: [{
          serverId: '9007199254740993',
          localId: '4294967295',
          status: 'error',
          requestId: 'request-error',
          code: 'native_trigger_timeout',
          message: '微信原生语音转文字等待超时。'
        }]
      }),
      lookupChatVoiceTranscriptionCache: vi.fn().mockResolvedValue({
        status: 'success',
        items: { '9007199254740993': { text: '不应覆盖的旧 Whisper 文字' } }
      }),
      getVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: false }),
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({ available: true })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    state.allMessages.value = { wxid_friend: [existingVoice()] }

    await state.restoreVoiceTranscripts('wxid_friend')

    expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
      voiceTranscript: '',
      voiceTranscriptStatus: 'error',
      voiceTranscriptError: '微信原生语音转文字等待超时。',
      voiceTranscriptNativeRequestId: 'request-error'
    })
    expect(api.lookupChatVoiceTranscriptionCache).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('pending 或非微信来源不会覆盖已有本项目文字', () => {
    const project = {
      voiceTranscript: '本项目文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'small'
    }
    expect(mergeWechatNativeVoiceTranscript(project, {
      status: 'pending',
      text: '',
      model: ''
    })).toBe(project)
    expect(mergeWechatNativeVoiceTranscript(project, {
      status: 'success',
      text: '另一个项目结果',
      model: 'medium'
    })).toBe(project)
  })
})

describe('微信原生转写 native-first 编排', () => {
  it.each([
    ['会话', ({ selectedContact }) => { selectedContact.value = { username: 'wxid_other' } }],
    ['账号', ({ selectedAccount }) => { selectedAccount.value = 'account-b' }]
  ])('trigger 返回前切换%s会解除 pre-trigger loading', async (_label, switchContext) => {
    const pendingTrigger = deferred()
    const api = {
      triggerNativeVoiceTranscription: vi.fn(() => pendingTrigger.promise),
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({
        available: false,
        reason: 'bridge_restart_required'
      })
    }
    const mounted = mountChatMessagesState(api)
    const { state, wrapper } = mounted
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    const request = state.transcribeVoice(message)
    expect(message.voiceTranscriptStatus).toBe('loading')

    switchContext(mounted)
    await nextTick()
    expect(message.voiceTranscriptStatus).toBe('idle')
    expect(message.voiceTranscriptError).toBe('')

    pendingTrigger.resolve({
      status: 'accepted',
      serverId: '9007199254740993',
      localId: '4294967295',
      requestId: 'request-after-navigation'
    })
    await request

    expect(message.voiceTranscriptStatus).toBe('idle')
    expect(message.voiceTranscriptNativeRequestId || '').toBe('')
    wrapper.unmount()
  })

  it('useApi 以精确字符串 POST，并以完整 identity 和 requestId 查询原生结果', async () => {
    const fetch = vi.fn(async (_url, options = {}) => options.body || { available: true })
    vi.stubGlobal('useApiBase', () => 'http://127.0.0.1:10392/api')
    vi.stubGlobal('$fetch', fetch)
    const api = useApi()

    await api.triggerNativeVoiceTranscription({
      account: 'account-a',
      username: 'wxid_friend',
      server_id: '9007199254740993',
      local_id: '4294967295'
    })
    await api.getNativeVoiceTranscript({
      account: 'account-a',
      username: 'wxid_friend',
      server_id: '9007199254740993',
      local_id: '4294967295',
      request_id: 'request-1'
    })
    await api.lookupNativeVoiceTranscriptionCache({
      account: 'account-a',
      username: 'wxid_friend',
      items: [{
        server_id: '9007199254740993',
        local_id: '4294967295'
      }]
    })
    await api.getNativeVoiceTranscriptionStatus({ account: 'account-a' })

    expect(fetch).toHaveBeenNthCalledWith(1, '/chat/media/voice/transcription/native/trigger', expect.objectContaining({
      method: 'POST',
      body: {
        account: 'account-a',
        username: 'wxid_friend',
        server_id: '9007199254740993',
        local_id: '4294967295'
      }
    }))
    expect(fetch).toHaveBeenNthCalledWith(
      4,
      '/chat/media/voice/transcription/native/status?account=account-a',
      expect.any(Object)
    )
    expect(fetch.mock.calls[1][0]).toContain('account=account-a')
    expect(fetch.mock.calls[1][0]).toContain('username=wxid_friend')
    expect(fetch.mock.calls[1][0]).toContain('server_id=9007199254740993')
    expect(fetch.mock.calls[1][0]).toContain('local_id=4294967295')
    expect(fetch.mock.calls[1][0]).toContain('request_id=request-1')
    expect(fetch.mock.calls[2]).toEqual([
      '/chat/media/voice/transcription/native/cache_lookup',
      expect.objectContaining({
        method: 'POST',
        body: {
          account: 'account-a',
          username: 'wxid_friend',
          items: [{
            server_id: '9007199254740993',
            local_id: '4294967295'
          }]
        }
      })
    ])
    expect(fetch.mock.calls[0][1].body.server_id).toBe('9007199254740993')
    expect(typeof fetch.mock.calls[0][1].body.server_id).toBe('string')
  })

  it('useApi 保留后端原生错误 code 供严格回退判定', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetch = vi.fn(async (_url, options = {}) => {
      await options.onResponseError({
        response: {
          status: 503,
          _data: {
            detail: {
              code: 'native_weixin_not_running',
              message: 'Weixin 未运行'
            }
          }
        }
      })
    })
    vi.stubGlobal('useApiBase', () => 'http://127.0.0.1:10392/api')
    vi.stubGlobal('$fetch', fetch)
    const api = useApi()

    await expect(api.triggerNativeVoiceTranscription({
      account: 'account-a',
      username: 'wxid_friend',
      server_id: '9007199254740993'
    })).rejects.toMatchObject({
      code: 'native_weixin_not_running',
      status: 503,
      detail: expect.objectContaining({ code: 'native_weixin_not_running' })
    })
  })

  it('原生 fast path 成功时立即写入 wechat-native 且不加载 Whisper', async () => {
    const api = {
      triggerNativeVoiceTranscription: vi.fn().mockResolvedValue({
        status: 'success',
        serverId: '9007199254740993',
        localId: '4294967295',
        text: '微信已有文字',
        language: '',
        model: 'wechat-native'
      }),
      getVoiceTranscriptionStatus: vi.fn(),
      transcribeChatVoice: vi.fn()
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    await state.transcribeVoice(message)

    expect(api.triggerNativeVoiceTranscription).toHaveBeenCalledWith({
      account: 'account-a',
      username: 'wxid_friend',
      server_id: '9007199254740993',
      local_id: '4294967295'
    })
    expect(api.getVoiceTranscriptionStatus).not.toHaveBeenCalled()
    expect(api.transcribeChatVoice).not.toHaveBeenCalled()
    expect(message).toMatchObject({
      voiceTranscript: '微信已有文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native'
    })
    wrapper.unmount()
  })

  it('accepted 后使用既有精确 server_id 轮询并合并微信结果', async () => {
    const api = {
      triggerNativeVoiceTranscription: vi.fn().mockResolvedValue({
        status: 'accepted',
        serverId: '9007199254740993',
        localId: '4294967295',
        requestId: 'request-1'
      }),
      getNativeVoiceTranscript: vi.fn().mockResolvedValue({
        status: 'success',
        serverId: '9007199254740993',
        text: '微信轮询文字',
        language: '',
        model: 'wechat-native'
      }),
      getVoiceTranscriptionStatus: vi.fn(),
      transcribeChatVoice: vi.fn()
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    await state.transcribeVoice(message)

    expect(api.getNativeVoiceTranscript).toHaveBeenCalledTimes(1)
    expect(api.getNativeVoiceTranscript).toHaveBeenCalledWith(expect.objectContaining({
      account: 'account-a',
      server_id: '9007199254740993',
      username: 'wxid_friend',
      local_id: '4294967295',
      request_id: 'request-1'
    }))
    expect(api.transcribeChatVoice).not.toHaveBeenCalled()
    expect(state.allMessages.value.wxid_friend[0]).toMatchObject({
      voiceTranscript: '微信轮询文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native'
    })
    wrapper.unmount()
  })

  it('accepted/pending 缺少 requestId 时拒绝降级为无代际绑定轮询', async () => {
    const api = {
      triggerNativeVoiceTranscription: vi.fn().mockResolvedValue({
        status: 'accepted',
        serverId: '9007199254740993',
        localId: '4294967295',
        requestId: ''
      }),
      getNativeVoiceTranscript: vi.fn(),
      transcribeChatVoice: vi.fn()
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    await state.transcribeVoice(message)

    expect(api.getNativeVoiceTranscript).not.toHaveBeenCalled()
    expect(api.transcribeChatVoice).not.toHaveBeenCalled()
    expect(message.voiceTranscriptStatus).toBe('error')
    expect(message.voiceTranscriptError).toContain('requestId')
    wrapper.unmount()
  })

  it('账号切换后丢弃旧账号的延迟 native status 响应', async () => {
    let resolveAccountA
    let resolveAccountB
    const api = {
      getNativeVoiceTranscriptionStatus: vi.fn(({ account }) => new Promise((resolve) => {
        if (account === 'account-a') resolveAccountA = resolve
        else resolveAccountB = resolve
      }))
    }
    const { state, wrapper, selectedAccount } = mountChatMessagesState(api)

    const accountARequest = state.refreshNativeVoiceTranscriptionStatus({ force: true })
    selectedAccount.value = 'account-b'
    await nextTick()
    const accountBRequest = state.refreshNativeVoiceTranscriptionStatus({ force: true })
    resolveAccountB({ available: false, reason: 'account-b-not-ready' })
    await accountBRequest
    resolveAccountA({ available: true, reason: '' })
    await accountARequest

    expect(state.nativeVoiceTranscriptionStatus.value).toEqual({
      available: false,
      reason: 'account-b-not-ready'
    })
    wrapper.unmount()
  })

  it('窗口重新获得焦点时刷新此前不可用的微信原生状态', async () => {
    const api = {
      getNativeVoiceTranscriptionStatus: vi.fn()
        .mockResolvedValueOnce({ available: false, reason: 'weixin_main_ui_not_found' })
        .mockResolvedValueOnce({ available: true, reason: '' })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    await state.refreshNativeVoiceTranscriptionStatus({ force: true })
    expect(state.nativeVoiceTranscriptionAvailable.value).toBe(false)

    window.dispatchEvent(new Event('focus'))
    await vi.waitFor(() => expect(api.getNativeVoiceTranscriptionStatus).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(state.nativeVoiceTranscriptionAvailable.value).toBe(true))

    wrapper.unmount()
  })

  it('微信版本不匹配时明确提示受支持版本和重启步骤', async () => {
    const api = {
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({
        available: false,
        reason: 'weixin_version_unsupported'
      })
    }
    const { state, wrapper } = mountChatMessagesState(api)

    await state.refreshNativeVoiceTranscriptionStatus({ force: true })

    expect(state.nativeVoiceTranscriptionAvailable.value).toBe(false)
    expect(state.nativeVoiceTranscriptionUnavailableReason.value).toBe(
      '当前微信版本暂不支持微信原生语音转文字。请使用微信 4.1.12.26，并完全退出、重新启动微信后再试。'
    )
    wrapper.unmount()
  })

  it('状态检查失败时显示中文恢复提示而不是内部 reason code', async () => {
    const api = {
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({
        available: false,
        reason: 'inspection_failed'
      })
    }
    const { state, wrapper } = mountChatMessagesState(api)

    await state.refreshNativeVoiceTranscriptionStatus({ force: true })

    expect(state.nativeVoiceTranscriptionUnavailableReason.value).toBe(
      '无法检查微信原生语音转文字状态。请重启本应用和微信后再试。'
    )
    wrapper.unmount()
  })

  it('受保护 DLL 或构建不可用时不显示单独 ASR 授权提示', async () => {
    const api = {
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({
        available: false,
        reason: 'protected_build_unavailable'
      })
    }
    const { state, wrapper } = mountChatMessagesState(api)

    await state.refreshNativeVoiceTranscriptionStatus({ force: true })

    expect(state.nativeVoiceTranscriptionUnavailableReason.value).toBe(
      '当前受保护 DLL 或构建中的微信原生语音转文字功能不可用。'
    )
    expect(state.nativeVoiceTranscriptionUnavailableReason.value).not.toContain('授权')
    wrapper.unmount()
  })

  it.each([
    'native_transport_unavailable',
    'native_weixin_not_running',
    'native_weixin_version_unsupported'
  ])('原生可用性错误 %s 也不静默回退 Whisper', async (code) => {
    const error = nativeError(code, '原生能力不可用')
    const api = {
      triggerNativeVoiceTranscription: vi.fn().mockRejectedValue(error),
      getVoiceTranscriptionStatus: vi.fn(),
      transcribeChatVoice: vi.fn().mockResolvedValue({
        text: 'Whisper 回退文字',
        language: 'zh',
        model: 'small'
      })
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    await state.transcribeVoice(message)

    expect(api.getVoiceTranscriptionStatus).not.toHaveBeenCalled()
    expect(api.transcribeChatVoice).not.toHaveBeenCalled()
    expect(message.voiceTranscriptStatus).toBe('error')
    expect(message.voiceTranscriptError).toBe('原生能力不可用')
    wrapper.unmount()
  })

  it.each([
    'voice_message_not_found',
    'voice_message_ambiguous',
    'voice_message_id_mismatch',
    'voice_message_not_voice',
    'native_trigger_rejected',
    'native_trigger_timeout',
    'native_transport_failed',
    'native_message_lookup_unavailable'
  ])('错误 %s 不静默回退 Whisper', async (code) => {
    const error = nativeError(code, `原生失败 ${code}`)
    const api = {
      triggerNativeVoiceTranscription: vi.fn().mockRejectedValue(error),
      getVoiceTranscriptionStatus: vi.fn(),
      transcribeChatVoice: vi.fn()
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    await state.transcribeVoice(message)

    expect(api.getVoiceTranscriptionStatus).not.toHaveBeenCalled()
    expect(api.transcribeChatVoice).not.toHaveBeenCalled()
    expect(message.voiceTranscriptStatus).toBe('error')
    expect(message.voiceTranscriptError).toBe(`原生失败 ${code}`)
    wrapper.unmount()
  })

  it('native callback 状态不确定后强制刷新 status 并立即禁用桥接', async () => {
    const error = nativeError('native_transport_failed', '微信原生回调状态不确定')
    const api = {
      triggerNativeVoiceTranscription: vi.fn().mockRejectedValue(error),
      getNativeVoiceTranscriptionStatus: vi.fn().mockResolvedValue({
        available: false,
        reason: 'bridge_restart_required'
      }),
      transcribeChatVoice: vi.fn()
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = existingVoice()
    state.allMessages.value = { wxid_friend: [message] }

    await state.transcribeVoice(message)

    expect(api.getNativeVoiceTranscriptionStatus).toHaveBeenCalledWith({ account: 'account-a' })
    expect(state.nativeVoiceTranscriptionAvailable.value).toBe(false)
    expect(state.nativeVoiceTranscriptionUnavailableReason.value).toContain('完全退出微信')
    expect(state.nativeVoiceTranscriptionUnavailableReason.value).toContain('重启本应用')
    expect(api.transcribeChatVoice).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
