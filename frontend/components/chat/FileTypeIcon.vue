<template>
  <img
    v-if="iconUrl"
    :src="iconUrl"
    alt=""
    class="wechat-file-icon"
  />
  <svg v-else-if="kind === 'ppt'" viewBox="0 0 24 24" fill="none" class="wechat-file-icon text-orange-500">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" fill="none" />
    <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" />
    <text x="6" y="17" font-size="5" fill="currentColor" font-weight="bold">PPT</text>
  </svg>
  <svg v-else-if="kind === 'txt'" viewBox="0 0 24 24" fill="none" class="wechat-file-icon text-gray-500">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" fill="none" />
    <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" />
    <text x="6" y="17" font-size="5" fill="currentColor" font-weight="bold">TXT</text>
  </svg>
  <svg v-else viewBox="0 0 24 24" fill="currentColor" class="wechat-file-icon text-gray-400">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h6v6h6v10H6z" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { getFileIconKind, getFileIconUrl } from '~/lib/chat/file-icons'

const props = defineProps({
  fileName: { type: String, default: '' }
})

const kind = computed(() => getFileIconKind(props.fileName))
const iconUrl = computed(() => getFileIconUrl(props.fileName))
</script>
