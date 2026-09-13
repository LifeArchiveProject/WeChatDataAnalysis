<script setup lang="ts">
import type { UIMessage } from 'ai'
import type { HTMLAttributes } from 'vue'
import { cn } from '~/lib/cn'

interface Props {
  from: UIMessage['role']
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <div
    :class="
      cn(
        'group flex w-full max-w-[80%] gap-2',
        props.from === 'user' ? 'is-user ml-auto justify-end' : 'is-assistant',
        props.class,
      )
    "
    v-bind="$attrs"
  >
    <slot />
  </div>
</template>
