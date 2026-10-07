import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AiSettings from '../components/AiSettings.vue'
import source from '../../src/wechat_decrypt_tool/ai/providers.py?raw'

// 复用后端预设，确保前端实际覆盖全部服务，而不是另一份过期名单。
const presets = source.split('\n').filter(line => line.trim().startsWith('{"provider":')).map(line => JSON.parse(line.trim().replace(/,$/, '')))
const request = vi.fn()
let wrapper
beforeEach(() => {
  vi.stubGlobal('useAiApi', () => ({ request }))
  vi.stubGlobal('useSettingsDialog', () => ({ focusTarget: ref(''), openDialog: vi.fn() }))
  request.mockReset().mockImplementation(async path => {
    if (path === '/settings') return { profiles: [], presets, defaults: {} }
    if (path === '/models') return { models: ['upstream-model'], model_details: [{ id: 'upstream-model', vision: null }] }
    return []
  })
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals() })

const open = async () => {
  wrapper = mount(AiSettings, { attachTo: document.body, global: { stubs: { teleport: true } } })
  await flushPromises()
  await wrapper.find('.ais-add').trigger('click')
}
const choose = async provider => {
  await wrapper.findAll('.ais-provider-choice').find(button => button.find(`[data-provider="${provider}"]`).exists()).trigger('click')
  await flushPromises()
}
const manualInput = () => wrapper.findAll('label').find(label => label.text().includes('手动输入（备用）')).find('input')

describe('AI 服务预设', () => {
  it('通过设置保存已确认的原生等级，清空后恢复自动识别', async () => {
    await open(); await choose('ollama')
    const levels = wrapper.find('[aria-label="供应商确认的原生推理等级"]')
    await levels.setValue('low， high, max, low')
    await levels.trigger('change')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(request.mock.calls.find(([path]) => path === '/profiles')[1].body.model_overrides.reasoning_efforts).toEqual(['low', 'high', 'max'])
    await wrapper.find('.ais-add').trigger('click'); await choose('ollama')
    const cleared = wrapper.find('[aria-label="供应商确认的原生推理等级"]')
    await cleared.setValue('low, high'); await cleared.trigger('change')
    await cleared.setValue(''); await cleared.trigger('change')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(request.mock.calls.filter(([path]) => path === '/profiles').at(-1)[1].body.model_overrides.reasoning_efforts).toBeUndefined()
  })
  it('显示全部预设，自定义位于末尾，搜索别名并清空无结果状态', async () => {
    await open()
    expect(wrapper.findAll('.ais-provider-choice')).toHaveLength(presets.length)
    expect(wrapper.findAll('.ais-provider-choice').at(-1).text()).toContain('自定义')
    const search = wrapper.find('.ais-provider-search input')
    for (const [query, provider] of [['小米', 'xiaomi'], ['MiMo', 'xiaomi'], ['谷歌', 'gemini'], ['千问', 'qwen'], [' gLm ', 'zhipu'], ['火山', 'doubao'], ['SiliconCloud', 'siliconflow'], ['lmstudio', 'lmstudio']]) {
      await search.setValue(query)
      expect(wrapper.findAll('.ais-provider-choice')).toHaveLength(1)
      expect(wrapper.find(`.ais-provider-choice [data-provider="${provider}"]`).exists()).toBe(true)
    }
    await search.setValue('没有这家服务')
    expect(wrapper.find('[role=status]').text()).toContain('没有匹配的 AI 服务')
    await wrapper.findAll('button').find(button => button.text() === '清空搜索').trigger('click')
    expect(wrapper.findAll('.ais-provider-choice')).toHaveLength(presets.length)
  })

  it.each(presets)('$name 正确预填并支持保存，不内置模型或图片能力', async preset => {
    await open()
    await choose(preset.provider)
    expect(wrapper.find('input[type=url]').element.value).toBe(preset.base_url)
    expect(wrapper.find('input[maxlength="80"]').element.value).toBe(preset.name)
    expect(wrapper.find('[aria-label="接口协议"]').text()).toContain(preset.protocol === 'anthropic' ? 'Claude Messages' : 'OpenAI 兼容')
    expect(wrapper.find('[role=switch]').element.checked).toBe(false)
    if (!['ollama', 'lmstudio'].includes(preset.provider)) {
      expect(request.mock.calls.filter(([path]) => path === '/models')).toHaveLength(0)
      await wrapper.find('input[type=password]').setValue('new-key')
      await wrapper.find('input[type=password]').trigger('blur')
      await flushPromises()
    }
    const fetch = request.mock.calls.find(([path]) => path === '/models')[1].body
    expect(fetch.base_url).toBe(preset.base_url)
    expect(fetch.protocol).toBe(preset.protocol)
    expect(wrapper.find('[aria-label="选择模型"]').text()).toContain('upstream-model')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    const saved = request.mock.calls.find(([path]) => path === '/profiles')[1].body
    expect(saved).toMatchObject({ ...preset, model: 'upstream-model', vision: false })
    expect(saved.api_key).toBe(['ollama', 'lmstudio'].includes(preset.provider) ? '' : 'new-key')
  })

  it('切换预设清空密钥、手动模式与模型状态，并忽略迟到响应', async () => {
    const original = request.getMockImplementation()
    let resolveOld
    request.mockImplementation((path, options) => path === '/models' ? new Promise(resolve => { resolveOld = resolve }) : original(path, options))
    await open(); await choose('deepseek')
    await wrapper.find('input[type=password]').setValue('old-key')
    await wrapper.find('input[type=password]').trigger('blur')
    await manualInput().setValue(true)
    await wrapper.find('input[placeholder="上游不支持获取列表时手动填写"]').setValue('old-model')
    await wrapper.find('[role=switch]').setValue(true)
    await wrapper.find('.ais-change-provider').trigger('click')
    await wrapper.find('.ais-provider-search input').setValue('谷歌')
    await choose('gemini')
    resolveOld({ models: ['old-model'] }); await flushPromises()
    expect(wrapper.find('input[type=password]').element.value).toBe('')
    expect(manualInput().element.checked).toBe(false)
    expect(wrapper.find('[role=switch]').element.checked).toBe(false)
    expect(wrapper.text()).not.toContain('old-model')
    expect(wrapper.find('.ais-primary').attributes('disabled')).toBeDefined()
    await wrapper.find('.ais-change-provider').trigger('click')
    expect(wrapper.findAll('.ais-provider-choice')).toHaveLength(presets.length)
  })

  it.each(['ollama', 'lmstudio'])('%s 失败提示检查本地服务，仍可手动填写后保存', async provider => {
    const original = request.getMockImplementation()
    request.mockImplementation(async (path, options) => { if (path === '/models') throw new Error('连接失败'); return original(path, options) })
    await open(); await choose(provider)
    expect(wrapper.find('[role=dialog]').text()).toContain('请检查本地服务是否已启动')
    await manualInput().setValue(true)
    await wrapper.find('input[placeholder="上游不支持获取列表时手动填写"]').setValue('local-model')
    expect(wrapper.find('.ais-primary').attributes('disabled')).toBeUndefined()
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(request.mock.calls.find(([path]) => path === '/profiles')[1].body).toMatchObject({ provider, model: 'local-model', api_key: '' })
  })

  it.each(['ollama', 'lmstudio'])('%s 改填局域网 HTTP 地址后仍免密钥自动获取，并提示明文传输', async provider => {
    await open(); await choose(provider)
    const dialogText = () => wrapper.find('[role=dialog]').text()
    const fetches = () => request.mock.calls.filter(([path]) => path === '/models')
    const fillAddress = async value => {
      await wrapper.find('input[type=url]').setValue(value)
      await wrapper.find('input[type=url]').trigger('blur'); await flushPromises()
    }
    expect(fetches()).toHaveLength(1)
    expect(dialogText()).not.toContain('明文 HTTP')
    await fillAddress('http://192.168.1.5:11434/v1')
    expect(fetches()).toHaveLength(2)
    expect(fetches().at(-1)[1].body).toMatchObject({ base_url: 'http://192.168.1.5:11434/v1', api_key: '' })
    expect(dialogText()).toContain('API 密钥可留空')
    expect(dialogText()).toContain('明文 HTTP')
    // 同一预设改填 HTTPS 远程地址时，仍需先填写密钥。
    await fillAddress('https://ollama.example.com/v1')
    expect(wrapper.find('input[type=url]').element.value).toBe('https://ollama.example.com/v1')
    expect(fetches()).toHaveLength(2)
    expect(dialogText()).not.toContain('API 密钥可留空')
    expect(dialogText()).not.toContain('明文 HTTP')
  })

  it('已有云端配置切换到本地时明确清空保存的密钥', async () => {
    const original = request.getMockImplementation()
    const profile = { ...presets[0], id: 'saved', has_key: true, model: 'cloud-model', vision: false }
    request.mockImplementation(async (path, options) => path === '/settings' ? { profiles: [profile], presets, defaults: {} } : original(path, options))
    await open()
    await wrapper.find('[aria-label="关闭服务弹窗"]').trigger('click')
    await wrapper.find('.ais-service-card').trigger('click'); await flushPromises()
    expect(request.mock.calls.find(([path]) => path === '/models')[1].body.api_key).toBeNull()
    await wrapper.find('.ais-change-provider').trigger('click'); await choose('ollama')
    expect(request.mock.calls.filter(([path]) => path === '/models').at(-1)[1].body).toMatchObject({ profile_id: 'saved', api_key: '' })
    expect(wrapper.find('input[type=password]').attributes('placeholder')).not.toContain('保留已有密钥')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(request.mock.calls.find(([path]) => path === '/profiles/saved')[1].body.api_key).toBe('')
  })

  it('搜索列表支持 Tab 焦点循环和 Escape 关闭后焦点恢复', async () => {
    await open()
    await wrapper.find('[aria-label="关闭服务弹窗"]').trigger('click')
    wrapper.find('.ais-add').element.focus()
    await wrapper.find('.ais-add').trigger('click')
    const dialog = wrapper.find('[role=dialog]')
    await dialog.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(wrapper.findAll('.ais-provider-choice').at(-1).element)
    await dialog.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(wrapper.find('[aria-label="关闭服务弹窗"]').element)
    await dialog.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role=dialog]').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('.ais-add').element)
  })

  it('从输入框拖选到遮罩松开时保留弹窗和表单，正常点击遮罩仍关闭', async () => {
    await open(); await choose('custom')
    const input = wrapper.find('input[type=url]')
    const overlay = wrapper.find('.ais-dialog-overlay')
    await input.setValue('https://example.com/v1')
    await input.trigger('pointerdown', { button:0, isPrimary:true })
    await overlay.trigger('pointerup', { button:0, isPrimary:true })
    await overlay.trigger('click')
    expect(wrapper.find('[role=dialog]').exists()).toBe(true)
    expect(input.element.value).toBe('https://example.com/v1')

    await overlay.trigger('pointerdown', { button:0, isPrimary:true })
    await overlay.trigger('pointerup', { button:0, isPrimary:true })
    await overlay.trigger('click'); await flushPromises()
    expect(wrapper.find('[role=dialog]').exists()).toBe(false)
  })

  it('从遮罩拖入弹窗或取消指针操作都不关闭弹窗', async () => {
    await open(); await choose('custom')
    const overlay = wrapper.find('.ais-dialog-overlay')
    await overlay.trigger('pointerdown', { button:0, isPrimary:true })
    await wrapper.find('input[type=url]').trigger('pointerup', { button:0, isPrimary:true })
    await overlay.trigger('click')
    expect(wrapper.find('[role=dialog]').exists()).toBe(true)

    await overlay.trigger('pointerdown', { button:0, isPrimary:true })
    await overlay.trigger('pointercancel')
    await overlay.trigger('click')
    expect(wrapper.find('[role=dialog]').exists()).toBe(true)
  })
})

it('模块导航统一显示用途，并支持键盘切换', async()=>{
  wrapper=mount(AiSettings,{attachTo:document.body,global:{stubs:{LocalSearchSettings:true}}})
  await flushPromises()
  expect(wrapper.findAll('[role=tab]').map(tab=>tab.text())).toEqual(['模型服务连接与模型配置','本地检索按意思查找聊天','用量记录调用明细与消耗'])
  await wrapper.find('#ais-config-tab').trigger('keydown',{key:'ArrowRight'});await flushPromises()
  expect(wrapper.find('#ais-local-tab').attributes('aria-selected')).toBe('true')
  expect(document.activeElement.id).toBe('ais-local-tab')
  await wrapper.find('#ais-local-tab').trigger('keydown',{key:'End'});await flushPromises()
  expect(wrapper.find('#ais-usage-tab').attributes('aria-selected')).toBe('true')
})

it('模型搜索收进下拉菜单，关闭时不占用表单空间', async () => {
  const original = request.getMockImplementation()
  request.mockImplementation(async (path,options) => path === '/models' ? {models:['deepseek-v4','grok-4.6'],model_details:[]} : original(path,options))
  await open(); await choose('custom')
  await wrapper.find('input[type=password]').setValue('test-key')
  await wrapper.find('input[type=password]').trigger('blur'); await flushPromises()
  expect(wrapper.find('.ais-model-search').exists()).toBe(false)
  expect(wrapper.find('input[placeholder="搜索模型"]').exists()).toBe(false)
  await wrapper.find('[aria-label="选择模型"]').trigger('click')
  await wrapper.find('.ui-select-menu input[placeholder="搜索模型"]').setValue('grok')
  expect(wrapper.findAll('[role=option]')).toHaveLength(1)
  await wrapper.find('[role=option]').trigger('click')
  expect(wrapper.find('[aria-label="选择模型"]').text()).toContain('grok-4.6')
  expect(wrapper.find('input[placeholder="搜索模型"]').exists()).toBe(false)
})

it('按目录显示参数并自动设置上下文、视觉能力和 Logo', async () => {
  const original = request.getMockImplementation()
  const detail = { id:'upstream-model', name:'测试模型', source:'models.dev', provider_id:'openai', provider_name:'OpenAI',
    logo_url:'https://models.dev/logos/openai.svg', vision:true, tool_call:false, reasoning:true, temperature:false,
    modalities:{input:['text','image'],output:['text']}, limit:{context:128000,output:16384}, cost:{input:0,output:2.5} }
  request.mockImplementation(async (path, options) => path === '/models' ? {models:[detail.id],model_details:[detail]} : original(path, options))
  await open(); await choose('openai')
  await wrapper.find('input[type=password]').setValue('test-key')
  await wrapper.find('input[type=password]').trigger('blur'); await flushPromises()
  expect(wrapper.find('[aria-label="模型参数"]').text()).toContain('128,000 tokens')
  expect(wrapper.find('[aria-label="模型参数"]').text()).toContain('16,384 tokens')
  expect(wrapper.find('[aria-label="模型参数"]').text()).toContain('$0')
  expect(wrapper.find('[aria-label="模型参数"] [data-provider="openai"] .ais-provider-monochrome').exists()).toBe(true)
  expect(wrapper.find('[aria-label="模型参数"] img').exists()).toBe(false)
  expect(wrapper.find('[role=switch]').element.checked).toBe(true)
  expect(wrapper.find('[role=switch]').attributes('disabled')).toBeUndefined()
  await wrapper.find('form').trigger('submit'); await flushPromises()
  expect(request.mock.calls.find(([path]) => path === '/profiles')[1].body).toMatchObject({context_window:128000,vision:true})
})

it('手动模型也查询目录，未匹配时保留用户补充的窗口和图片能力', async () => {
  await open(); await choose('custom'); await manualInput().setValue(true)
  await wrapper.find('input[placeholder="上游不支持获取列表时手动填写"]').setValue('private-model')
  await wrapper.find('input[type=number]').setValue(64000)
  await wrapper.find('[role=switch]').setValue(true)
  await wrapper.find('form').trigger('submit'); await flushPromises()
  expect(request.mock.calls.some(([path]) => path.startsWith('/model-metadata?'))).toBe(true)
  expect(request.mock.calls.find(([path]) => path === '/profiles')[1].body).toMatchObject({context_window:64000,vision:true})
})

it('自动识别后可手动覆盖，刷新列表和保存都不会覆盖手动值', async () => {
  const original = request.getMockImplementation()
  const detail = {id:'upstream-model',source:'upstream',vision:true,tool_call:true,
    limit:{context:128000,output:16384},field_sources:{vision:'models.dev','limit.context':'upstream'}}
  request.mockImplementation(async (path, options) => path === '/models' ? {models:[detail.id],model_details:[detail]} : original(path,options))
  await open(); await choose('custom')
  await wrapper.find('input[type=password]').setValue('test-key')
  await wrapper.find('input[type=password]').trigger('blur'); await flushPromises()
  expect(wrapper.find('input[type=number]').element.value).toBe('128000')
  expect(wrapper.find('.ais-model-section').text()).toContain('自动识别')
  expect(wrapper.find('.ais-vision-copy').text()).toContain('自动识别')
  expect(wrapper.text()).not.toContain('上游自动识别')
  expect(wrapper.text()).not.toContain('models.dev')
  await wrapper.find('input[type=number]').setValue(64000)
  await wrapper.find('[role=switch]').setValue(false)
  await wrapper.findAll('button').find(button=>button.text()==='从上游获取').trigger('click'); await flushPromises()
  expect(wrapper.find('input[type=number]').element.value).toBe('64000')
  expect(wrapper.find('[role=switch]').element.checked).toBe(false)
  expect(wrapper.text()).toContain('手动设置')
  await wrapper.find('form').trigger('submit'); await flushPromises()
  expect(request.mock.calls.find(([path])=>path==='/profiles')[1].body.model_overrides).toMatchObject({context_window:64000,vision:false})
})

it('恢复自动识别可清除手动覆盖，切换模型不会沿用上个模型的设置', async () => {
  const original = request.getMockImplementation()
  const detail = {id:'upstream-model',source:'models.dev',vision:true,limit:{context:128000}}
  request.mockImplementation(async (path, options) => path === '/models' ? {models:[detail.id],model_details:[detail]} : original(path,options))
  await open(); await choose('custom')
  await wrapper.find('input[type=password]').setValue('test-key')
  await wrapper.find('input[type=password]').trigger('blur'); await flushPromises()
  await wrapper.find('input[type=number]').setValue(64000)
  await wrapper.find('[role=switch]').setValue(false)
  await wrapper.findAll('button').find(button=>button.text()==='恢复自动识别').trigger('click'); await flushPromises()
  expect(wrapper.find('input[type=number]').element.value).toBe('128000')
  expect(wrapper.find('[role=switch]').element.checked).toBe(true)
  await manualInput().setValue(true)
  await wrapper.find('input[placeholder="上游不支持获取列表时手动填写"]').setValue('unknown-model')
  expect(wrapper.find('input[type=number]').element.value).toBe('')
  expect(wrapper.find('[role=switch]').element.checked).toBe(false)
  expect(wrapper.findAll('button').some(button => button.text() === '恢复自动识别')).toBe(false)
})
