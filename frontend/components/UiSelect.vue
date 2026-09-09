<template>
  <span class="ui-select" :class="{ 'is-plain': plain, 'is-mono': mono }">
    <button ref="trigger" type="button" class="ui-select-trigger" role="combobox"
      :aria-label="label" aria-haspopup="listbox" :aria-expanded="open" :aria-controls="open ? listId : undefined"
      :aria-activedescendant="open && active >= 0 ? `${listId}-${active}` : undefined" :disabled="disabled"
      :title="selected?.label || placeholder" @click="open ? close() : show()" @keydown="onKeydown">
      <span :class="{ 'is-placeholder': !selected }">{{ selected?.label || placeholder }}</span>
      <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
    </button>
    <Teleport to="body">
      <div v-if="open" :id="searchable ? undefined : listId" ref="menu" class="ui-select-menu" :class="{ 'is-mono': mono }"
        :role="searchable ? undefined : 'listbox'" :aria-label="searchable ? undefined : label" :aria-busy="loading" :style="position" @mousedown="onMenuMouseDown">
        <div v-if="searchable" class="ui-select-search">
          <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
          <input ref="searchInput" v-model="query" type="search" role="combobox" :aria-label="searchPlaceholder" :placeholder="searchPlaceholder"
            aria-autocomplete="list" aria-expanded="true" :aria-controls="listId" :aria-activedescendant="active >= 0 ? `${listId}-${active}` : undefined"
            autocomplete="off" @keydown="onSearchKeydown" />
        </div>
        <div :id="searchable ? listId : undefined" :role="searchable ? 'listbox' : undefined" :aria-label="searchable ? label : undefined">
        <div v-if="loading" class="ui-select-empty" role="status">正在加载…</div>
        <div v-else-if="loadError" class="ui-select-empty" role="status">{{ loadError }}，重新打开可重试。</div>
        <div v-for="(option, index) in visibleOptions" :id="`${listId}-${index}`" :key="option.value"
          role="option" :aria-selected="option.value === modelValue" :aria-disabled="option.disabled || undefined"
          class="ui-select-option" :class="{ 'is-active': active === index, 'is-selected': option.value === modelValue, 'is-disabled': option.disabled }"
          @mousemove="!option.disabled && (active = index)" @click.stop="choose(index)">
          <span class="ui-select-option-copy"><span>{{ option.label }}</span><small v-if="option.description">{{ option.description }}</small></span>
          <i v-if="option.value === modelValue" class="fa-solid fa-check" aria-hidden="true"></i>
        </div>
        <div v-if="!visibleOptions.length && !loading && !loadError" class="ui-select-empty" role="status">{{ query.trim() ? '没有匹配的选项' : '暂无可选项' }}</div>
        </div>
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
const props = defineProps({
  modelValue: { type: String, default: '' }, options: { type: Array, default: () => [] },
  label: { type: String, required: true }, placeholder: { type: String, default: '请选择' },
  disabled: Boolean, plain: Boolean, mono: Boolean, loading: Boolean,
  searchable: Boolean, searchPlaceholder: { type: String, default: '搜索选项' },
  loadError: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'change', 'open'])
const listId = `select-${useId()}`
const trigger = ref(null), menu = ref(null), open = ref(false), active = ref(-1), position = ref({})
const selected = computed(() => props.options.find(option => option.value === props.modelValue))
const query = ref(''), searchInput = ref(null)
const visibleOptions = computed(() => {
  const term = props.searchable ? query.value.trim().toLowerCase() : ''
  return term ? props.options.filter(option => `${option.label} ${option.value}`.toLowerCase().includes(term)) : props.options
})
let search = '', lastKeyTime = 0
const close = () => { open.value = false; search = ''; query.value = '' }
const reveal = () => nextTick(() => menu.value?.querySelectorAll('[role="option"]')[active.value]?.scrollIntoView?.({ block: 'nearest' }))
const show = () => {
  if (props.disabled) return
  query.value = ''
  // 弹层挂到 body，避免被设置页的滚动容器裁切；空间不足时向上展开。
  const rect = trigger.value.getBoundingClientRect()
  const below = window.innerHeight - rect.bottom - 12, above = rect.top - 12
  const upwards = below < 220 && above > below
  const height = Math.min(280, Math.max(60, upwards ? above : below))
  const width = Math.min(Math.max(rect.width, 180), window.innerWidth - 24)
  position.value = { width: `${width}px`, maxHeight: `${height}px`, left: `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`,
    ...(upwards ? { bottom: `${window.innerHeight - rect.top + 6}px` } : { top: `${rect.bottom + 6}px` }) }
  active.value = props.options.findIndex(option => option.value === props.modelValue && !option.disabled)
  if (active.value < 0) active.value = props.options.findIndex(option => !option.disabled)
  open.value = true
  emit('open')
  reveal()
  if (props.searchable) nextTick(() => searchInput.value?.focus())
}
const choose = index => {
  const option = visibleOptions.value[index]
  if (!option || option.disabled) return
  emit('update:modelValue', option.value)
  if (option.value !== props.modelValue) emit('change', option.value)
  close()
  trigger.value?.focus()
}
const move = delta => {
  const enabled = visibleOptions.value.map((option, index) => option.disabled ? -1 : index).filter(index => index >= 0)
  if (!enabled.length) return
  active.value = enabled[(enabled.indexOf(active.value) + delta + enabled.length) % enabled.length]
  reveal()
}
const onKeydown = event => {
  if (event.key === 'Escape' && open.value) { event.preventDefault(); event.stopPropagation(); close(); return }
  if (event.key === 'Tab') { close(); return }
  if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
    event.preventDefault()
    if (!open.value) { show(); return }
    if (event.key === 'Enter' || event.key === ' ') choose(active.value)
    else if (event.key === 'Home' || event.key === 'End') {
      const enabled = visibleOptions.value.map((option, index) => option.disabled ? -1 : index).filter(index => index >= 0)
      active.value = event.key === 'Home' ? enabled[0] : enabled.at(-1)
      reveal()
    } else move(event.key === 'ArrowDown' ? 1 : -1)
  } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    if (!open.value) show()
    if (props.searchable) { query.value += event.key; return }
    search = Date.now() - lastKeyTime > 700 ? event.key : search + event.key
    lastKeyTime = Date.now()
    const found = props.options.findIndex(option => !option.disabled && option.label.toLowerCase().startsWith(search.toLowerCase()))
    if (found >= 0) { active.value = found; reveal() }
  }
}
const onMenuMouseDown = event => {
  // 选项点击保留键盘焦点；搜索输入允许原生光标定位和文字选择。
  if (!searchInput.value?.contains(event.target)) event.preventDefault()
}
const onSearchKeydown = event => {
  if (event.isComposing || event.keyCode === 229) return
  if (event.key === 'Escape') {
    event.preventDefault(); event.stopPropagation(); close(); trigger.value?.focus()
  } else if (event.key === 'Tab') {
    // 菜单传送到 body，回到触发器后再执行原生 Tab，继续表单中的焦点顺序。
    close(); trigger.value?.focus()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault(); move(event.key === 'ArrowDown' ? 1 : -1)
  } else if (event.key === 'Enter') {
    event.preventDefault(); choose(active.value)
  }
}
const outside = event => { if (!trigger.value?.contains(event.target) && !menu.value?.contains(event.target)) close() }
const onScroll = event => { if (!menu.value?.contains(event.target)) close() }
watch(open, value => {
  // 仅在展开期间监听，滚动页面时收起菜单，避免菜单与字段脱离。
  const method = value ? 'addEventListener' : 'removeEventListener'
  document[method]('pointerdown', outside, true)
  document[method]('scroll', onScroll, true)
  window[method]('resize', close)
})
watch(() => props.disabled, value => { if (value) close() })
watch(visibleOptions, (options, previous) => {
  if (!open.value) return
  // 冷启动的异步选项直接更新当前菜单，保留键盘定位，不要求用户再打开一次。
  const value = previous?.[active.value]?.value ?? props.modelValue
  active.value = options.findIndex(option => option.value === value && !option.disabled)
  if (active.value < 0) active.value = options.findIndex(option => option.value === props.modelValue && !option.disabled)
  if (active.value < 0) active.value = options.findIndex(option => !option.disabled)
  reveal()
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside, true)
  document.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', close)
})
</script>

<style>
.ui-select { display: block; min-width: 0; }
.ui-select .ui-select-trigger { width: 100%; height: 34px; min-height: 34px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 10px; border: 1px solid var(--app-border, #e7e9ed); border-radius: 6px; background: var(--app-surface-bg, #fff); color: var(--app-text-primary, #20272f); font-size: 12px; font-weight: 400; text-align: left; cursor: pointer; }
.ui-select-trigger > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-select-trigger > i { font-size: 9px; color: #88938d; transition: transform .15s; }
.ui-select-trigger[aria-expanded=true] { border-color: #079b57; box-shadow: 0 0 0 2px #079b5712; }
.ui-select-trigger[aria-expanded=true] > i { transform: rotate(180deg); }
.ui-select-trigger:disabled { opacity: .45; cursor: not-allowed; }
.ui-select-trigger .is-placeholder { color: #929b97; }
.ui-select.is-plain .ui-select-trigger { height: 29px; min-height: 29px; padding-left: 0; background: transparent; border-color: transparent; font-weight: 550; }
.ui-select.is-mono .ui-select-trigger, .ui-select-menu.is-mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
.ui-select-menu { position: fixed; z-index: 21000; overflow-y: auto; overscroll-behavior: contain; box-sizing: border-box; padding: 5px; border: 1px solid #e1e7e3; border-radius: 9px; background: #fff; color: #29332e; box-shadow: 0 8px 28px #182c231c, 0 2px 6px #182c230a; font-size: 12px; line-height: 1.5; scrollbar-width: thin; scrollbar-color: #cbd5ce transparent; }
.ui-select-search { position:sticky; top:-5px; z-index:1; padding:5px 3px 8px; margin-top:-1px; background:inherit; border-bottom:1px solid #e1e7e3; }
.ui-select-search > i { position:absolute; left:13px; top:16px; color:#7c8981; font-size:11px; pointer-events:none; }
.ui-select-search input { box-sizing:border-box; width:100%; height:32px; padding:0 9px 0 29px; border:1px solid #e1e7e3; border-radius:5px; color:inherit; background:transparent; font:inherit; outline:none; }
.ui-select-search input:focus { border-color:#079b57; }
.ui-select-search input::placeholder { color:#7c8981; }
.ui-select-option { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 8px 10px; border-radius: 5px; cursor: pointer; }
.ui-select-option-copy { min-width: 0; overflow-wrap: anywhere; }
.ui-select-option-copy small { display: block; margin-top: 2px; color: #7c8981; font-size: 10px; }
.ui-select-option.is-active { background: #f1f5f2; }
.ui-select-option.is-selected { color: #07834a; background: #edf8f1; font-weight: 500; }
.ui-select-option.is-active.is-selected { background: #e1f2e8; }
.ui-select-option > i { flex-shrink: 0; font-size: 10px; }
.ui-select-option.is-disabled { opacity: .4; cursor: not-allowed; }
.ui-select-empty { padding: 12px 10px; color: #7c8981; }
html[data-theme=dark] .ui-select-menu { color: #e6eaed; background: #262b2d; border-color: #3b4340; box-shadow: 0 8px 28px #0005; }
html[data-theme=dark] .ui-select-search, html[data-theme=dark] .ui-select-search input { border-color:#3b4340; }
html[data-theme=dark] .ui-select-search input:focus { border-color:#70d6a4; }
html[data-theme=dark] .ui-select-option.is-active { background: #343c37; }
html[data-theme=dark] .ui-select-option.is-selected { color: #70d6a4; background: #1a3e2d; }
html[data-theme=dark] .ui-select-option-copy small { color: #a0aea6; }
@media (prefers-reduced-motion: reduce) { .ui-select-trigger > i { transition: none; } }
</style>
