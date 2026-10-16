import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAgentPanelResize } from '../composables/useAgentPanelResize'

const Harness = defineComponent({
  setup() { const panel=ref(null), expanded=ref(false); return { panel, expanded, ...useAgentPanelResize(panel, expanded) } },
  template:'<aside ref="panel"><div role="separator" @pointerdown="start" @lostpointercapture="finish" @keydown="keyboard" @dblclick="reset" /></aside>',
})
let wrapper
beforeEach(() => { localStorage.clear(); vi.stubGlobal('innerWidth', 1400) })
afterEach(() => { wrapper?.unmount(); wrapper=null; vi.unstubAllGlobals() })
const pointer = (type, x, id=1) => window.dispatchEvent(new PointerEvent(type, {clientX:x, pointerId:id}))

describe('AI 侧栏宽度', () => {
  it('拖动后保存宽度，取消或卸载时释放光标与选区锁定', async () => {
    wrapper=mount(Harness, {attachTo:document.body})
    await wrapper.find('[role=separator]').trigger('pointerdown', {button:0,clientX:900,pointerId:1})
    pointer('pointermove',700)
    expect(wrapper.vm.width).toBe(640)
    expect(document.body.style.userSelect).toBe('none')
    pointer('pointercancel',700)
    expect(localStorage.getItem('chat-agent-panel-width')).toBe('640')
    expect(document.body.style.userSelect).toBe('')
    wrapper.unmount(); wrapper=mount(Harness, {attachTo:document.body})
    expect(wrapper.vm.width).toBe(640)
    await wrapper.find('[role=separator]').trigger('pointerdown', {button:0,clientX:900,pointerId:1})
    wrapper.unmount(); wrapper=null
    expect(document.body.style.cursor).toBe('')
  })
  it('键盘微调、边界和重置可用，缩小窗口不丢失偏好宽度', async () => {
    wrapper=mount(Harness, {attachTo:document.body})
    const separator=wrapper.find('[role=separator]')
    await separator.trigger('keydown',{key:'ArrowLeft',shiftKey:true})
    expect(wrapper.vm.width).toBe(520)
    vi.stubGlobal('innerWidth',400); window.dispatchEvent(new Event('resize'))
    expect(wrapper.vm.width).toBe(376)
    vi.stubGlobal('innerWidth',1400); window.dispatchEvent(new Event('resize'))
    expect(wrapper.vm.width).toBe(520)
    await separator.trigger('keydown',{key:'Home'}); expect(wrapper.vm.width).toBe(320)
    await separator.trigger('keydown',{key:'End'}); expect(wrapper.vm.width).toBe(1080)
    await separator.trigger('dblclick'); expect(wrapper.vm.width).toBe(440)
  })
})
