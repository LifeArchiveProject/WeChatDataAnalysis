import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useChatMessages } from '~/composables/chat/useChatMessages'
import { useApi } from '~/composables/useApi'

vi.mock('~/lib/server-error-logging', () => ({ reportServerError: vi.fn() }))
vi.mock('~/stores/chatAccounts', () => ({
  useChatAccountsStore: () => ({ applySourceResponse: vi.fn() })
}))

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('chat API performance probe', () => {
  it('reuses the message-load trace id for the API request', async () => {
    localStorage.setItem('debug.chat.performance', '1')
    vi.spyOn(console, 'info').mockImplementation(() => {})
    const api = {
      listChatMessages: vi.fn(async () => ({ messages: [], total: 0, hasMore: false }))
    }
    let state
    const wrapper = mount(defineComponent({
      setup() {
        state = useChatMessages({
          api,
          apiBase: '/api',
          selectedAccount: ref('account-a'),
          selectedContact: ref({ username: '44372432598@chatroom' }),
          realtimeEnabled: ref(false),
          privacyMode: ref(false),
          searchContext: ref({ active: false })
        })
        return () => h('div')
      }
    }))

    await state.loadMessages({ username: '44372432598@chatroom', reset: true })

    expect(api.listChatMessages).toHaveBeenCalledWith(expect.objectContaining({
      perfTraceId: expect.stringMatching(/^chat-messages-/)
    }))
    wrapper.unmount()
  })

  it('sends trace timestamps and logs only this request resource timing', async () => {
    localStorage.setItem('debug.chat.performance', '1')
    const getEntriesByName = vi.fn(() => [
      { startTime: 20, fetchStart: 20, requestStart: 22, responseStart: 30, responseEnd: 35, duration: 15 },
      {
        startTime: 105,
        fetchStart: 110,
        requestStart: 120,
        responseStart: 150,
        responseEnd: 175,
        duration: 70,
        transferSize: 123,
        encodedBodySize: 100,
        decodedBodySize: 200,
        initiatorType: 'fetch'
      }
    ])
    vi.stubGlobal('performance', {
      now: vi.fn().mockReturnValueOnce(100).mockReturnValueOnce(200),
      getEntriesByName,
      setResourceTimingBufferSize: vi.fn()
    })
    vi.stubGlobal('useApiBase', () => '/api')
    const fetch = vi.fn(async () => ({ messages: [], total: 0, hasMore: false }))
    vi.stubGlobal('$fetch', fetch)
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})

    const api = useApi()
    await api.listChatMessages({
      account: 'account-a',
      username: '44372432598@chatroom',
      limit: 50,
      perfTraceId: 'chat-messages-test'
    })

    const [, options] = fetch.mock.calls[0]
    expect(options.headers.get('X-WCDA-Perf-Trace')).toBe('chat-messages-test')
    expect(Number(options.headers.get('X-WCDA-Perf-Sent-Ms'))).toBeGreaterThan(0)
    expect(performance.setResourceTimingBufferSize).toHaveBeenCalledWith(5000)
    const completion = info.mock.calls.find(([message]) => message === '[chat-api] request:complete')
    expect(completion?.[1]).toMatchObject({
      traceId: 'chat-messages-test',
      resourceTimingFound: true,
      resourceStartMs: 105,
      fetchStartMs: 110,
      requestStartMs: 120,
      responseStartMs: 150,
      responseEndMs: 175,
      queueMs: 10,
      ttfbMs: 30,
      downloadMs: 25
    })
    expect(getEntriesByName).toHaveBeenCalledWith(expect.stringContaining('/api/chat/messages?'))
  })
})
