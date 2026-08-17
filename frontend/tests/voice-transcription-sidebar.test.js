import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineComponent, h, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import VoiceTranscriptionSidebar from '~/components/chat/VoiceTranscriptionSidebar.vue'
import { useApi } from '~/composables/useApi'
import { clearProjectVoiceTranscripts, useChatMessages } from '~/composables/chat/useChatMessages'
import { notifyProjectVoiceTranscriptsInvalidated } from '~/lib/voice-transcript-invalidation'

vi.mock('~/lib/server-error-logging', () => ({ reportServerError: vi.fn() }))
vi.mock('~/stores/chatAccounts', () => ({
  useChatAccountsStore: () => ({ applySourceResponse: vi.fn() })
}))

const chatPageSource = readFileSync(resolve(process.cwd(), 'pages/chat/[[username]].vue'), 'utf8')
const voiceSidebarSource = readFileSync(resolve(process.cwd(), 'components/chat/VoiceTranscriptionSidebar.vue'), 'utf8')
const decryptPageSource = readFileSync(resolve(process.cwd(), 'pages/decrypt.vue'), 'utf8')
const useApiSource = readFileSync(resolve(process.cwd(), 'composables/useApi.js'), 'utf8')
const chatMessagesSource = readFileSync(resolve(process.cwd(), 'composables/chat/useChatMessages.js'), 'utf8')
const chatOverlaysSource = readFileSync(resolve(process.cwd(), 'components/chat/ChatOverlays.vue'), 'utf8')
const settingsDialogSource = readFileSync(resolve(process.cwd(), 'components/SettingsDialog.vue'), 'utf8')

const createDeferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })

  return { promise, resolve, reject }
}

const mountChatMessagesState = (api) => {
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
        realtimeEnabled: ref(false),
        privacyMode: ref(false),
        searchContext: ref({ active: false })
      })
      return () => h('div')
    }
  }))
  return { state, selectedAccount, selectedContact, wrapper }
}

const makeState = (overrides = {}) => ({
  voiceSidebarOpen: ref(true),
  voiceTranscriptionStatus: ref({
    available: true,
    model: 'medium',
    modelReady: true,
    requestedDevice: 'cuda',
    activeDevice: 'cuda',
    cuda: {
      available: true,
      devices: [{ name: 'NVIDIA GeForce RTX 3060 Laptop GPU' }]
    },
    models: [
      { id: 'small', name: 'Small', downloaded: true, size: '约 466 MB' },
      { id: 'medium', name: 'Medium', downloaded: true, size: '约 1.5 GB', selected: true }
    ]
  }),
  voiceTranscriptionStatusLoading: ref(false),
  voicePanelBusy: ref(false),
  voicePanelError: ref(''),
  voiceBatchConcurrency: ref(0),
  voiceBatchJob: ref({
    jobId: 'voice-batch-1',
    status: 'running',
    total: 10,
    completed: 4,
    success: 3,
    native: 2,
    cached: 1,
    failed: 1,
    percent: 40,
    requestedConcurrency: 0,
    concurrency: 3
  }),
  closeVoiceSidebar: vi.fn(),
  refreshVoicePanel: vi.fn(),
  setVoicePanelDevice: vi.fn(),
  setVoicePanelModel: vi.fn(),
  setVoiceBatchConcurrency: vi.fn(),
  openVoiceModelSettings: vi.fn(),
  startVoiceBatch: vi.fn(),
  cancelVoiceBatch: vi.fn(),
  ...overrides
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('聊天页语音转文字侧栏', () => {
  it('微信原生结果不承诺 force 重跑，失败时只提供普通重试', () => {
    expect(chatMessagesSource).toContain('const transcribeVoice = async (message) =>')
    expect(chatMessagesSource).not.toContain('const transcribeVoice = async (message, { force')
    expect(chatOverlaysSource).not.toContain('重新微信转文字')
    expect(chatOverlaysSource).not.toContain('transcribe(message, { force:')
    expect(chatOverlaysSource).toContain('重试微信转文字')
    expect(chatOverlaysSource).toContain("voiceTranscriptModel === 'wechat-native'")
  })

  it('展示模型、设备和批量进度，并允许取消任务', async () => {
    const state = makeState()
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })

    expect(wrapper.text()).toContain('Medium')
    expect(wrapper.text()).toContain('模型已就绪')
    expect(wrapper.text()).toContain('NVIDIA GeForce RTX 3060 Laptop GPU')
    expect(wrapper.text()).toContain('4 / 10')
    expect(wrapper.text()).toContain('本项目转写')
    expect(wrapper.text()).toContain('微信原生转写')
    expect(wrapper.text()).toContain('并发 3')
    expect(wrapper.get('.voice-concurrency-select').attributes()).toHaveProperty('disabled')
    expect(wrapper.findAll('.voice-stat')[0].get('strong').text()).toBe('1')
    expect(wrapper.findAll('.voice-stat')[1].get('strong').text()).toBe('2')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('40')

    await wrapper.get('.voice-batch-cancel').trigger('click')
    expect(state.cancelVoiceBatch).toHaveBeenCalledTimes(1)
  })

  it('空闲时允许切换模型、设备并开始全部转写', async () => {
    const state = makeState({
      voiceBatchJob: ref({ status: 'idle', percent: 0 })
    })
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })

    await wrapper.get('.voice-model-select').setValue('small')
    expect(state.setVoicePanelModel).toHaveBeenCalledWith('small')

    await wrapper.get('.voice-device-cpu').trigger('click')
    expect(state.setVoicePanelDevice).toHaveBeenCalledWith('cpu')

    const concurrencyInput = wrapper.get('.voice-concurrency-select')
    expect(concurrencyInput.element.value).toBe('0')
    expect(concurrencyInput.attributes()).toMatchObject({ type: 'number', min: '0', step: '1', inputmode: 'numeric' })
    expect(concurrencyInput.attributes()).not.toHaveProperty('max')
    expect(wrapper.text()).toContain('并发线程数')
    expect(wrapper.text()).toContain('0 自动，输入正整数')
    for (const concurrency of [5, 16, 128]) {
      await concurrencyInput.setValue(String(concurrency))
      await concurrencyInput.trigger(concurrency === 128 ? 'keydown' : 'blur', concurrency === 128 ? { key: 'Enter' } : undefined)
      expect(state.setVoiceBatchConcurrency).toHaveBeenLastCalledWith(concurrency)
    }

    await wrapper.get('.voice-batch-start').trigger('click')
    expect(state.startVoiceBatch).toHaveBeenCalledTimes(1)
  })

  it('并发线程数保留非法草稿并在修正前阻止启动', async () => {
    const state = makeState({
      voiceBatchConcurrency: ref(2),
      voiceBatchJob: ref({ status: 'idle', percent: 0 })
    })
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })
    const input = wrapper.get('.voice-concurrency-select')

    for (const value of ['2.5', '-1']) {
      await input.setValue(value)
      await input.trigger('blur')
      expect(input.element.value).toBe(value)
      expect(input.attributes('aria-invalid')).toBe('true')
      expect(wrapper.text()).toContain('不支持：请输入 0 或正整数')
    }
    expect(state.setVoiceBatchConcurrency).not.toHaveBeenCalled()

    await wrapper.get('.voice-batch-start').trigger('click')
    expect(state.startVoiceBatch).not.toHaveBeenCalled()
    expect(state.setVoiceBatchConcurrency).not.toHaveBeenCalled()

    await input.setValue('128')
    expect(input.attributes('aria-invalid')).toBe('false')
    await wrapper.get('.voice-batch-start').trigger('click')
    expect(state.setVoiceBatchConcurrency).toHaveBeenLastCalledWith(128)
    expect(state.startVoiceBatch).toHaveBeenCalledTimes(1)
    expect(input.attributes('aria-invalid')).toBe('false')
  })

  it('空输入提交为自动，原生 badInput 不会被当成自动', async () => {
    const state = makeState({
      voiceBatchConcurrency: ref(3),
      voiceBatchJob: ref({ status: 'idle', percent: 0 })
    })
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })
    const input = wrapper.get('.voice-concurrency-select')

    await input.setValue('')
    await input.trigger('blur')
    expect(input.element.value).toBe('0')
    expect(state.setVoiceBatchConcurrency).toHaveBeenLastCalledWith(0)

    state.setVoiceBatchConcurrency.mockClear()
    wrapper.vm.onConcurrencyInput({ target: { value: '', validity: { badInput: true } } })
    await wrapper.get('.voice-batch-start').trigger('click')
    expect(state.setVoiceBatchConcurrency).not.toHaveBeenCalled()
    expect(state.startVoiceBatch).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('不支持：请输入 0 或正整数')
  })

  it('任务返回的 requestedConcurrency 会同步输入草稿', async () => {
    const state = makeState({
      voiceBatchConcurrency: ref(1),
      voiceBatchJob: ref({ status: 'idle', percent: 0 })
    })
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })
    const input = wrapper.get('.voice-concurrency-select')

    await input.setValue('2.5')
    await input.trigger('blur')
    state.voiceBatchJob.value = { jobId: 'voice-batch-2', status: 'running', requestedConcurrency: 128, concurrency: 128 }
    await wrapper.vm.$nextTick()

    expect(input.element.value).toBe('128')
    expect(input.attributes('aria-invalid')).toBe('false')
    expect(input.attributes()).toHaveProperty('disabled')
  })

  it('未下载模型不可直接选择，并提供设置下载入口', async () => {
    const state = makeState({
      voiceBatchJob: ref({ status: 'idle', percent: 0 }),
      voiceTranscriptionStatus: ref({
        available: false,
        model: 'large-v3',
        modelReady: false,
        modelSettingSource: 'settings',
        requestedDevice: 'cpu',
        cuda: { available: false, devices: [], reason: '未检测到 GPU' },
        reason: 'Whisper 模型尚未下载到本机缓存。',
        models: [
          { id: 'small', name: 'Small', downloaded: true },
          { id: 'large-v3', name: 'Large v3', downloaded: false, selected: true }
        ]
      })
    })
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })

    const options = wrapper.findAll('.voice-model-select option')
    expect(options.find((option) => option.attributes('value') === 'large-v3')?.attributes()).toHaveProperty('disabled')

    await wrapper.get('.voice-model-settings').trigger('click')
    expect(state.openVoiceModelSettings).toHaveBeenCalledTimes(1)
  })

  it('环境变量锁定推理设备时不可切换', () => {
    const state = makeState({
      voiceBatchJob: ref({ status: 'idle', percent: 0 }),
      voiceTranscriptionStatus: ref({
        available: true,
        model: 'medium',
        modelReady: true,
        modelSettingSource: 'settings',
        deviceSource: 'env',
        requestedDevice: 'cuda',
        activeDevice: 'cuda',
        cuda: { available: true, devices: [{ name: 'NVIDIA GPU' }] },
        models: [{ id: 'medium', name: 'Medium', downloaded: true, selected: true }]
      })
    })
    const wrapper = mount(VoiceTranscriptionSidebar, { props: { state } })

    expect(wrapper.get('.voice-device-cpu').attributes()).toHaveProperty('disabled')
    expect(wrapper.get('.voice-device-cuda').attributes()).toHaveProperty('disabled')
    expect(wrapper.text()).toContain('推理设备由启动环境变量固定')
  })

  it('聊天页对账号异步响应、失效任务及右侧面板互斥有保护', () => {
    expect(chatPageSource).toContain('voicePanelRequestRevision')
    expect(chatPageSource).toContain('voicePanelContextStillCurrent')
    expect(chatPageSource).toContain('isVoiceJobMissingError')
    expect(chatPageSource).toContain("searchState.closeMessageSearch('voice-panel')")
    expect(chatPageSource).toContain('toggleMessageSearch: toggleChatMessageSearch')
    expect(chatPageSource).toContain('toggleTimeSidebar: toggleChatTimeSidebar')
  })

  it('两处批量入口发送并展示受控并发数', () => {
    const batchApiSource = useApiSource.slice(
      useApiSource.indexOf('const startVoiceTranscriptionBatch'),
      useApiSource.indexOf('const getLatestVoiceTranscriptionBatch')
    )
    expect(batchApiSource).toContain('concurrency')
    expect(batchApiSource).toContain('concurrency < 0')
    expect(batchApiSource).not.toMatch(/concurrency\s*>/)
    expect(batchApiSource).toContain("throw new RangeError('并发线程数必须是非负整数（0 表示自动）')")
    expect(batchApiSource).toMatch(/force: !!data\.force,\s*concurrency/)

    expect(chatPageSource).toContain('const voiceBatchConcurrency = ref(0)')
    expect(chatPageSource).toContain('concurrency: normalizeVoiceBatchConcurrency(voiceBatchConcurrency.value)')
    expect(chatPageSource).toContain("hasOwnProperty.call(job, 'requestedConcurrency')")

    expect(decryptPageSource).toContain('data-testid="voice-onboarding-concurrency"')
    const onboardingConcurrencyMarker = decryptPageSource.indexOf('data-testid="voice-onboarding-concurrency"')
    const onboardingConcurrencyInput = decryptPageSource.slice(
      decryptPageSource.lastIndexOf('<input', onboardingConcurrencyMarker),
      decryptPageSource.indexOf('>', onboardingConcurrencyMarker) + 1
    )
    expect(onboardingConcurrencyInput).toContain('type="number"')
    expect(onboardingConcurrencyInput).toContain('min="0"')
    expect(onboardingConcurrencyInput).not.toContain('max=')
    expect(decryptPageSource).toContain(':disabled="voiceBatchRunning || voiceOnboardingLoading || voiceModelBusy"')
    expect(decryptPageSource).toContain(':aria-invalid="voiceBatchConcurrencyError')
    expect(decryptPageSource).toContain('@input="onVoiceBatchConcurrencyInput"')
    expect(decryptPageSource).toContain('@blur="commitVoiceBatchConcurrency"')
    expect(decryptPageSource).toContain('@keydown.enter.prevent="commitVoiceBatchConcurrency"')
    expect(decryptPageSource).toContain('并发线程数')
    expect(decryptPageSource).toContain('0 自动，输入正整数')
    expect(decryptPageSource).toContain('不支持：请输入 0 或正整数')
    expect(decryptPageSource).toContain('|| !commitVoiceBatchConcurrency()')
    expect(decryptPageSource).toContain('并发 {{ voiceBatchActualConcurrency }}')
    expect(decryptPageSource).toContain('concurrency: voiceBatchConcurrency.value')
    expect(decryptPageSource).toContain("hasOwnProperty.call(job, 'requestedConcurrency')")
    expect(decryptPageSource).toContain('syncVoiceBatchConcurrencyDraft(job.requestedConcurrency)')
  })

  it('全局删除入口只在设置中，并通过全局事件使聊天缓存失效', () => {
    expect(useApiSource).toContain('const deleteAllVoiceTranscriptionCache = async () =>')
    expect(useApiSource).toMatch(/voice\/transcription\/cache\/all',[\s\S]*?method: 'DELETE'/)
    expect(voiceSidebarSource).not.toContain('删除本项目转写结果')
    expect(chatPageSource).not.toContain('deleteProjectVoiceTranscripts')
    expect(chatPageSource).not.toContain('voicePanelMessage')

    expect(settingsDialogSource).toContain('data-testid="voice-transcript-global-delete"')
    expect(settingsDialogSource).toContain('删除全部本项目转写结果')
    expect(settingsDialogSource).toContain(':disabled="voiceTranscriptDeleteBusy"')
    expect(settingsDialogSource).toContain('此操作不可撤销')
    expect(settingsDialogSource).toContain('所有账号中由本项目 Whisper 生成的全部转写文字')
    expect(settingsDialogSource).toContain('微信原生转写、原始语音和已下载模型都会保留')
    expect(settingsDialogSource).toContain('await api.deleteAllVoiceTranscriptionCache()')
    expect(settingsDialogSource).toContain('notifyProjectVoiceTranscriptsInvalidated(result)')
    expect(settingsDialogSource).toContain('accountsScanned')
    expect(settingsDialogSource).toContain('accountsChanged')
    expect(settingsDialogSource).toContain('deletedMessages')
    expect(settingsDialogSource).toContain("String(result?.status || '').toLowerCase() === 'partial'")
    expect(settingsDialogSource).toContain('voiceTranscriptDeleteWarning')
    expect(settingsDialogSource).toContain('部分清理完成：')
    expect(settingsDialogSource).toContain('仍有账号正在批量转写，请先完成或取消后重试。')
    const settingsDeleteSource = settingsDialogSource.slice(
      settingsDialogSource.indexOf('const deleteAllProjectVoiceTranscripts = async () =>'),
      settingsDialogSource.indexOf('const refreshVoiceTranscriptionStatus')
    )
    expect(settingsDeleteSource.indexOf('notifyProjectVoiceTranscriptsInvalidated(result)')).toBeLessThan(
      settingsDeleteSource.indexOf("String(result?.status || '').toLowerCase() === 'partial'")
    )
    expect(settingsDeleteSource).toMatch(/if \(String\(result\?\.status[\s\S]*?voiceTranscriptDeleteWarning\.value = `[\s\S]*?else \{[\s\S]*?voiceTranscriptDeleteMessage\.value = `/)
    expect(settingsDeleteSource).not.toContain('voiceModelAction.value')
    expect(settingsDeleteSource).not.toContain('isVoiceModelDownloading')

    expect(chatPageSource).toContain("import { PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT } from '~/lib/voice-transcript-invalidation'")
    expect(chatPageSource).toMatch(/const onProjectVoiceTranscriptsInvalidated = \(\) => \{\s*resetVoiceBatchState\(\)\s*\}/)
    expect(chatPageSource).toContain('window.addEventListener(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT, onProjectVoiceTranscriptsInvalidated)')
    expect(chatPageSource).toContain('window.removeEventListener(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT, onProjectVoiceTranscriptsInvalidated)')

    expect(chatMessagesSource).toContain('let projectTranscriptRevision = 0')
    expect(chatMessagesSource).toContain('const invalidateProjectVoiceTranscripts = () =>')
    expect(chatMessagesSource).toContain("if (model === 'wechat-native') continue")
    expect(chatMessagesSource).toContain("if (!model && status !== 'loading') continue")
    expect(chatMessagesSource).toContain('PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT')
    expect(chatMessagesSource).toContain('window.addEventListener(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT')
    expect(chatMessagesSource).toContain('window.removeEventListener(PROJECT_VOICE_TRANSCRIPTS_INVALIDATED_EVENT')
    expect(chatMessagesSource).toMatch(/const onProjectVoiceTranscriptsInvalidated[\s\S]*?invalidateProjectVoiceTranscripts\(\)[\s\S]*?refreshSelectedMessages\(\)/)
    expect(chatMessagesSource).toContain('transcriptRevision !== projectTranscriptRevision')
    expect(chatMessagesSource).toMatch(/lookupChatVoiceTranscriptionCache[\s\S]*?transcriptRevision !== projectTranscriptRevision/)
    expect(chatMessagesSource).toMatch(/triggerNativeVoiceTranscription[\s\S]*?if \(!requestIsCurrent\(\)\) return/)
    expect(chatMessagesSource).toMatch(/const restoreVoiceTranscripts[\s\S]*?const accountAtStart[\s\S]*?account: accountAtStart[\s\S]*?selectedAccount\.value[\s\S]*?accountAtStart/)
    expect(chatMessagesSource).toMatch(/const transcribeVoice[\s\S]*?const accountAtStart[\s\S]*?account: accountAtStart[\s\S]*?selectedAccount\.value[\s\S]*?accountAtStart/)
    const resetMessageStateSource = chatMessagesSource.slice(
      chatMessagesSource.indexOf('const resetMessageState = () =>'),
      chatMessagesSource.indexOf('const contactProfileCardOpen')
    )
    expect(resetMessageStateSource).toContain('projectTranscriptRevision += 1')
  })

  it('清理内存转写时保留微信原生结果，并重置项目结果和尚未返回的项目请求', () => {
    const native = {
      voiceTranscript: '微信原生文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native',
      voiceTranscriptLanguage: 'zh'
    }
    const project = {
      voiceTranscript: '项目文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'medium',
      voiceTranscriptLanguage: 'zh'
    }
    const loading = {
      voiceTranscript: '',
      voiceTranscriptStatus: 'loading',
      voiceTranscriptModel: '',
      voiceTranscriptError: ''
    }
    const unmarked = {
      voiceTranscript: '来源未标记的旧文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: ''
    }

    clearProjectVoiceTranscripts({ friend: [native, project, loading, unmarked] })

    expect(native).toMatchObject({
      voiceTranscript: '微信原生文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native'
    })
    expect(project).toMatchObject({ voiceTranscript: '', voiceTranscriptStatus: 'idle', voiceTranscriptModel: '' })
    expect(loading).toMatchObject({ voiceTranscript: '', voiceTranscriptStatus: 'idle', voiceTranscriptModel: '' })
    expect(unmarked).toMatchObject({
      voiceTranscript: '来源未标记的旧文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: ''
    })
  })

  it('设置页广播全局删除后，已打开聊天立即清项目文字并刷新当前会话', async () => {
    const refreshedMessages = createDeferred()
    const api = {
      getVoiceTranscriptionStatus: vi.fn(async () => ({ available: true })),
      listChatMessages: vi.fn(() => refreshedMessages.promise)
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const native = {
      id: 'native',
      renderType: 'voice',
      voiceTranscript: '微信原生文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'wechat-native'
    }
    const project = {
      id: 'project',
      renderType: 'voice',
      voiceTranscript: '项目文字',
      voiceTranscriptStatus: 'success',
      voiceTranscriptModel: 'medium'
    }
    const loading = {
      id: 'loading',
      renderType: 'voice',
      voiceTranscript: '',
      voiceTranscriptStatus: 'loading',
      voiceTranscriptModel: ''
    }
    state.allMessages.value = { wxid_friend: [native, project, loading] }

    expect(notifyProjectVoiceTranscriptsInvalidated({ deletedMessages: 2 })).toBe(true)
    expect(native).toMatchObject({ voiceTranscript: '微信原生文字', voiceTranscriptModel: 'wechat-native' })
    expect(project).toMatchObject({ voiceTranscript: '', voiceTranscriptStatus: 'idle', voiceTranscriptModel: '' })
    expect(loading).toMatchObject({ voiceTranscript: '', voiceTranscriptStatus: 'idle', voiceTranscriptModel: '' })
    await vi.waitFor(() => expect(api.listChatMessages).toHaveBeenCalledTimes(1))
    expect(api.listChatMessages).toHaveBeenCalledWith(expect.objectContaining({
      account: 'account-a',
      username: 'wxid_friend'
    }))

    refreshedMessages.resolve({ messages: [], total: 0, hasMore: false })
    await vi.waitFor(() => expect(state.isLoadingMessages.value).toBe(false))
    wrapper.unmount()
  })

  it('单条转写始终使用请求开始时账号，切换账号后的迟到响应不会写回', async () => {
    const transcription = createDeferred()
    const api = {
      triggerNativeVoiceTranscription: vi.fn(() => transcription.promise)
    }
    const { state, selectedAccount, wrapper } = mountChatMessagesState(api)
    const message = {
      id: 'voice-account-race',
      serverIdStr: '1234567890123456789',
      renderType: 'voice',
      voiceTranscript: '',
      voiceTranscriptStatus: 'idle',
      voiceTranscriptModel: ''
    }
    state.allMessages.value = { wxid_friend: [message] }

    const pending = state.transcribeVoice(message)
    await vi.waitFor(() => expect(api.triggerNativeVoiceTranscription).toHaveBeenCalledTimes(1))
    expect(api.triggerNativeVoiceTranscription).toHaveBeenCalledWith(expect.objectContaining({ account: 'account-a' }))

    selectedAccount.value = 'account-b'
    transcription.resolve({
      status: 'success',
      serverId: '1234567890123456789',
      localId: '1',
      text: '不应写入 B 的迟到文字',
      language: '',
      model: 'wechat-native'
    })
    await pending

    expect(message.voiceTranscript).toBe('')
    expect(message.voiceTranscriptModel).toBe('')
    expect(message.voiceTranscriptStatus).not.toBe('success')
    wrapper.unmount()
  })

  it('账号重置会使正在进行的单条转写响应失效', async () => {
    const transcription = createDeferred()
    const api = {
      triggerNativeVoiceTranscription: vi.fn(() => transcription.promise)
    }
    const { state, wrapper } = mountChatMessagesState(api)
    const message = {
      id: 'voice-reset-race',
      serverIdStr: '2234567890123456789',
      renderType: 'voice',
      voiceTranscript: '',
      voiceTranscriptStatus: 'idle',
      voiceTranscriptModel: ''
    }
    state.allMessages.value = { wxid_friend: [message] }

    const pending = state.transcribeVoice(message)
    await vi.waitFor(() => expect(api.triggerNativeVoiceTranscription).toHaveBeenCalledTimes(1))
    state.resetMessageState()
    transcription.resolve({
      status: 'success',
      serverId: '2234567890123456789',
      localId: '1',
      text: '重置后不应写回',
      language: '',
      model: 'wechat-native'
    })
    await pending

    expect(state.allMessages.value).toEqual({})
    expect(message.voiceTranscript).toBe('')
    expect(message.voiceTranscriptModel).toBe('')
    expect(message.voiceTranscriptStatus).not.toBe('success')
    wrapper.unmount()
  })

  it('批量 API 将自动和手动并发值写入请求体', async () => {
    const fetch = vi.fn(async (_url, options) => options.body)
    vi.stubGlobal('useApiBase', () => 'http://127.0.0.1:10392/api')
    vi.stubGlobal('$fetch', fetch)
    const api = useApi()

    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: false })
    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: false, concurrency: null })
    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: false, concurrency: '' })
    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: false, concurrency: 0 })
    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: true, concurrency: 5 })
    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: true, concurrency: 16 })
    await api.startVoiceTranscriptionBatch({ account: 'wxid_demo', force: true, concurrency: 128 })

    for (const call of [1, 2, 3, 4]) {
      expect(fetch).toHaveBeenNthCalledWith(call, '/chat/media/voice/transcription/batch', expect.objectContaining({
        body: { account: 'wxid_demo', force: false, concurrency: 0 }
      }))
    }
    for (const [index, concurrency] of [5, 16, 128].entries()) {
      expect(fetch).toHaveBeenNthCalledWith(index + 5, '/chat/media/voice/transcription/batch', expect.objectContaining({
        body: { account: 'wxid_demo', force: true, concurrency }
      }))
    }

    for (const concurrency of [2.5, -1, '3', 'bad', ' ', true]) {
      await expect(api.startVoiceTranscriptionBatch({ account: 'wxid_demo', concurrency })).rejects.toThrow(
        '并发线程数必须是非负整数（0 表示自动）'
      )
    }
    expect(fetch).toHaveBeenCalledTimes(7)
  })

  it('全局删除 API 不携带账号并调用明确的 all 路由', async () => {
    const fetch = vi.fn(async () => ({ accountsScanned: 2, accountsChanged: 1, deletedMessages: 3 }))
    vi.stubGlobal('useApiBase', () => 'http://127.0.0.1:10392/api')
    vi.stubGlobal('$fetch', fetch)
    const api = useApi()

    await api.deleteAllVoiceTranscriptionCache()
    expect(fetch).toHaveBeenCalledWith(
      '/chat/media/voice/transcription/cache/all',
      expect.objectContaining({ method: 'DELETE' })
    )
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('窄窗口使用覆盖式抽屉而不是继续压缩聊天区', () => {
    expect(voiceSidebarSource).toContain('@media (max-width: 1100px)')
    expect(voiceSidebarSource).toMatch(/position:\s*absolute/)
    expect(voiceSidebarSource).toMatch(/width:\s*344px/)
    expect(voiceSidebarSource).toMatch(/width:\s*min\(344px, 100%\)/)
    expect(voiceSidebarSource).not.toContain('@media (max-width: 520px)')
  })

  it('使用紧凑的扁平分区和项目主题色', () => {
    expect(voiceSidebarSource).toContain('space-y-0 overflow-y-auto px-4 py-1')
    expect(voiceSidebarSource).toMatch(/\.voice-panel-section\s*\{[^}]*border-radius:\s*0;[^}]*padding:\s*12px 0;/s)
    expect(voiceSidebarSource).toMatch(/\.voice-panel-muted\s*\{[^}]*font-size:\s*11px;[^}]*line-height:\s*1\.45;/s)
    expect(voiceSidebarSource).toContain('var(--app-accent)')
    expect(voiceSidebarSource).not.toMatch(/#03c160|#245fbd/)
  })
})
