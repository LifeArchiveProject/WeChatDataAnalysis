import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createEmptySearchContext, useChatSearch } from '../composables/chat/useChatSearch'
import { useApi } from '../composables/useApi'

vi.mock('~/lib/server-error-logging', () => ({ reportServerError: vi.fn() }))
vi.mock('~/stores/chatAccounts', () => ({ useChatAccountsStore: () => ({ applySourceResponse: vi.fn() }) }))

const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const response = (month = 2, total = 3) => ({
  status: 'success', source: 'realtime', counts: { [`2020-${String(month).padStart(2, '0')}-01`]: total },
  total, max: total, scanLimited: false
})
let wrapper, originalClient
beforeEach(() => {
  originalClient = process.client
  process.client = true
  vi.useFakeTimers()
  vi.spyOn(console, 'info').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('useSettingsDialog', () => ({ openDialog: vi.fn() }))
  vi.stubGlobal('useApiBase', () => '/api')
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  process.client = originalClient
  localStorage.clear()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const setup = (fetchCounts = vi.fn(async () => response())) => {
  const args = {
    api: { getChatMessageDailyCounts: fetchCounts }, contacts: ref([]), selectedAccount: ref('account'),
    selectedContact: ref({ username: 'chat' }), privacyMode: ref(false), allMessages: ref({}),
    messagesMeta: ref({}), messages: ref([]), messageContainerRef: ref(null), messagePageSize: 50,
    hasMoreMessages: ref(false), isLoadingMessages: ref(false), normalizeMessage: message => message,
    updateJumpToBottomState: vi.fn(), scrollToMessageId: vi.fn(), flashMessage: vi.fn(), highlightMessageId: ref(''),
    searchContext: ref(createEmptySearchContext()), selectContact: vi.fn(), loadMoreMessages: vi.fn()
  }
  let search
  wrapper = mount(defineComponent({ setup() { search = useChatSearch(args); return () => h('div') } }))
  const load = (month = 2, extra = {}) => search.loadTimeSidebarMonth({ year: 2020, month, ...extra })
  const cells = () => search.timeSidebarCalendarCells.value.filter(cell => cell.day)
  return { args, search, load, cells, fetchCounts }
}

describe('月历请求与状态', () => {
  it('复用相同月份请求，完整统计后才启用有记录的日期', async () => {
    const task = deferred()
    const { load, cells, search, fetchCounts } = setup(vi.fn(() => task.promise))
    const first = load()
    expect(load()).toBe(first)
    expect(fetchCounts).toHaveBeenCalledTimes(1)
    expect(cells().every(cell => cell.disabled && cell.countText === '—')).toBe(true)
    task.resolve(response())
    await first
    expect(search.timeSidebarLoading.value).toBe(false)
    expect(cells()[0]).toMatchObject({ disabled: false, countText: '3' })
    expect(cells()[1]).toMatchObject({ disabled: true, countText: '0' })
  })

  it('快速切月后旧响应不能覆盖新月份，也不能清除新请求的加载状态', async () => {
    const old = deferred(), current = deferred()
    const { load, search, fetchCounts, cells } = setup(vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise))
    const first = load(2)
    const next = load(3)
    expect(fetchCounts.mock.calls[0][0].signal.aborted).toBe(true)
    old.resolve(response(2, 99))
    await first
    expect(search.timeSidebarLoading.value).toBe(true)
    expect(cells().every(cell => cell.countText === '—')).toBe(true)
    current.resolve(response(3, 2))
    await next
    expect(search.timeSidebarCounts.value).toEqual({ '2020-03-01': 2 })
  })

  it('切回缓存月份也使旧请求失效', async () => {
    const old = deferred()
    const { load, search, fetchCounts } = setup(vi.fn().mockResolvedValueOnce(response(2)).mockReturnValueOnce(old.promise))
    await load(2)
    const pending = load(3)
    await load(2)
    expect(fetchCounts.mock.calls[1][0].signal.aborted).toBe(true)
    expect(search.timeSidebarLoading.value).toBe(false)
    old.resolve(response(3, 99))
    await pending
    expect(search.timeSidebarCounts.value).toEqual({ '2020-02-01': 3 })
    expect(fetchCounts).toHaveBeenCalledTimes(2)
  })

  it.each(['account', 'contact', 'close', 'toggle', 'unmount'])('%s 使在途请求立即失效', async action => {
    const old = deferred()
    const { load, search, args, fetchCounts } = setup(vi.fn(() => old.promise))
    search.timeSidebarOpen.value = true
    const pending = load()
    if (action === 'account') args.selectedAccount.value = 'other-account'
    if (action === 'contact') args.selectedContact.value = { username: 'other-chat' }
    if (action === 'close') search.closeTimeSidebar()
    if (action === 'toggle') await search.toggleTimeSidebar()
    if (action === 'unmount') { wrapper.unmount(); wrapper = null }
    expect(fetchCounts.mock.calls[0][0].signal.aborted).toBe(true)
    old.resolve(response(2, 99))
    await pending
    expect(search.timeSidebarCounts.value).toEqual({})
    expect(search.timeSidebarLoading.value).toBe(false)
  })

  it('切月后旧请求报错不能污染新月份', async () => {
    const old = deferred()
    const { load, search } = setup(vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(response(3)))
    const pending = load(2)
    await load(3)
    old.reject(new Error('旧错误'))
    await pending
    expect(search.timeSidebarError.value).toBe('')
    expect(search.timeSidebarTotal.value).toBe(3)
  })

  it('失败和不完整统计不缓存，重试绕过缓存', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error('无法完整加载日历，请稍后重试'))
      .mockResolvedValueOnce({ ...response(), scanLimited: true }).mockResolvedValue(response())
    const { load, search, cells } = setup(fetch)
    await load()
    expect(search.timeSidebarError.value).toContain('完整加载')
    expect(cells().every(cell => cell.disabled && cell.countText === '—')).toBe(true)
    await load()
    expect(search.timeSidebarError.value).toContain('不完整')
    await search.retryTimeSidebarMonth()
    expect(search.timeSidebarError.value).toBe('')
    await search.retryTimeSidebarMonth()
    expect(fetch).toHaveBeenCalledTimes(4)
  })

  it('缓存 30 秒过期，账号和会话之间不共享统计', async () => {
    const { load, args, fetchCounts } = setup()
    await load()
    await load()
    expect(fetchCounts).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(30_000)
    await load()
    expect(fetchCounts).toHaveBeenCalledTimes(2)
    args.selectedAccount.value = 'second'
    await load()
    args.selectedContact.value = { username: 'second-chat' }
    await load()
    expect(fetchCounts).toHaveBeenCalledTimes(4)
    expect(fetchCounts.mock.calls[3][0]).toMatchObject({ account: 'second', username: 'second-chat', source: 'auto' })
  })

  it('缓存超过 120 项时淘汰最久未访问的月份', async () => {
    const { load, fetchCounts } = setup()
    for (let i = 0; i < 121; i++) await load(i % 12 + 1, { year: 2000 + Math.floor(i / 12) })
    expect(fetchCounts).toHaveBeenCalledTimes(121)
    await load(1, { year: 2000 })
    expect(fetchCounts).toHaveBeenCalledTimes(122)
    await load(1, { year: 2010 })
    expect(fetchCounts).toHaveBeenCalledTimes(122)
  })

  it('20 秒超时后退出加载，手动重试可以恢复', async () => {
    const fetch = vi.fn().mockImplementationOnce(() => new Promise(() => {})).mockResolvedValue(response())
    vi.stubGlobal('$fetch', fetch)
    const api = useApi()
    const { load, search, cells } = setup(api.getChatMessageDailyCounts)
    const pending = load()
    await vi.advanceTimersByTimeAsync(20_000)
    await pending
    expect(search.timeSidebarLoading.value).toBe(false)
    expect(search.timeSidebarError.value).toBe('加载日历超时，请重试')
    expect(cells().every(cell => cell.disabled && cell.countText === '—')).toBe(true)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][1]).toMatchObject({ timeout: 20_000, retry: 0 })
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    await search.retryTimeSidebarMonth()
    expect(search.timeSidebarReady.value).toBe(true)
    expect(search.timeSidebarError.value).toBe('')
  })

  it('API 传递主动取消，取消后释放超时计时器', async () => {
    const fetch = vi.fn(() => new Promise(() => {}))
    vi.stubGlobal('$fetch', fetch)
    const controller = new AbortController()
    const pending = useApi().getChatMessageDailyCounts({ signal: controller.signal, account: 'acc', username: 'chat', year: 2020, month: 2 })
    const check = expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await check
    expect(fetch.mock.calls[0][0]).not.toContain('signal')
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('已经取消的请求不再发往服务器', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('$fetch', fetch)
    const controller = new AbortController()
    controller.abort()
    await expect(useApi().getChatMessageDailyCounts({ signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetch).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('打开后立即关闭不会在下一微任务重新发起月历请求', async () => {
    const task = deferred()
    const { args, search, fetchCounts } = setup(vi.fn(() => task.promise))
    args.messages.value = [{ createTime: new Date(2020, 1, 1).getTime() / 1000 }]
    const pending = search.toggleTimeSidebar()
    search.closeTimeSidebar()
    task.resolve(response())
    await pending
    expect(search.timeSidebarOpen.value).toBe(false)
    expect(search.timeSidebarReady.value).toBe(false)
    expect(fetchCounts.mock.calls[0][0].signal.aborted).toBe(true)
  })
})
