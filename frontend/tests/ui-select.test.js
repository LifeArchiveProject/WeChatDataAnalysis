import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import UiSelect from '../components/UiSelect.vue'

const props = { label: '接口协议', modelValue: 'a', options: [
  { value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta', disabled: true }, { value: 'c', label: 'Claude' },
] }
describe('统一下拉菜单', () => {
  it('异步选项更新不收起菜单，并保持可用的键盘选择', async () => {
    const wrapper=mount(UiSelect,{attachTo:document.body,props:{label:'模型',options:[],loading:true}})
    const trigger=wrapper.find('[role=combobox]')
    await trigger.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    expect(document.querySelector('[role=listbox]').textContent).toContain('正在加载')
    await wrapper.setProps({loading:false,options:[{value:'a',label:'模型 A'},{value:'b',label:'模型 B'}]})
    expect(trigger.attributes('aria-expanded')).toBe('true')
    await trigger.trigger('keydown',{key:'ArrowDown'})
    await wrapper.setProps({options:[{value:'c',label:'新模型'},{value:'a',label:'模型 A'},{value:'b',label:'模型 B'}]})
    expect(document.querySelector('[role=option].is-active').textContent).toContain('模型 B')
    await trigger.trigger('keydown',{key:'Enter'})
    expect(wrapper.emitted('update:modelValue')).toEqual([['b']])
    wrapper.unmount()
  })
  it('方向键跳过禁用项，回车才提交，Esc 不关闭外层弹窗', async () => {
    const wrapper = mount(UiSelect, { attachTo: document.body, props })
    const trigger = wrapper.find('[role=combobox]')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(document.querySelector('[role=option].is-active').textContent).toContain('Claude')
    await trigger.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toEqual([['c']])
    await trigger.trigger('click')
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    trigger.element.dispatchEvent(event); await flushPromises()
    expect(event.defaultPrevented).toBe(true)
    expect(trigger.attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })
  it('菜单在空间不足时向上展开，页面滚动和点击外部会关闭', async () => {
    const wrapper = mount(UiSelect, { attachTo: document.body, props })
    const trigger = wrapper.find('[role=combobox]')
    trigger.element.getBoundingClientRect = () => ({ left: 20, top: window.innerHeight - 80, bottom: window.innerHeight - 46, width: 200 })
    await trigger.trigger('click')
    const menu = document.querySelector('[role=listbox]')
    expect(menu.style.bottom).toBe('86px')
    menu.dispatchEvent(new Event('scroll')); await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('true')
    document.dispatchEvent(new Event('scroll')); await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })); await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })
})
