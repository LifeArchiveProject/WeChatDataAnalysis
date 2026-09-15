<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '~/lib/cn'
import { reactiveOmit } from '@vueuse/core'
import { StickToBottom } from 'vue-stick-to-bottom'
import { ref } from 'vue'

interface Props {
  ariaLabel?: string
  class?: HTMLAttributes['class']
  initial?: boolean | 'instant' | { damping?: number, stiffness?: number, mass?: number }
  resize?: 'instant' | { damping?: number, stiffness?: number, mass?: number }
  damping?: number
  stiffness?: number
  mass?: number
  anchor?: 'auto' | 'none'
}

const props = withDefaults(defineProps<Props>(), {
  ariaLabel: 'Conversation',
  initial: true,
  damping: 0.7,
  stiffness: 0.05,
  mass: 1.25,
  anchor: 'none',
})
const delegatedProps = reactiveOmit(props, 'class')
const conversation = ref<InstanceType<typeof StickToBottom> | null>(null)
// 将库实际管理的滚动节点交给业务层，避免依赖组件内部的 DOM 层级。
defineExpose({ getViewport: () => conversation.value?.scrollRef ?? null })
</script>

<template>
  <StickToBottom
    ref="conversation"
    v-bind="delegatedProps"
    :class="cn('relative flex-1 overflow-y-hidden', props.class)"
    role="log"
  >
    <slot />
  </StickToBottom>
</template>
