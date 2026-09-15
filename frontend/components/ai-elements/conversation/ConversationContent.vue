<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '~/lib/cn'
import { computed } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const classes = computed(() => cn(
  'flex flex-col gap-8 p-4',
  props.class,
))
</script>

<template>
  <div :class="classes">
    <slot />
  </div>
</template>
