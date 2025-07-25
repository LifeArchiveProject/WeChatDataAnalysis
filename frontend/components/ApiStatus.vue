<template>
  <div v-if="appStore.apiStatus !== 'connected'" 
       class="fixed top-4 right-4 bg-red-50 border border-red-200 rounded-lg p-4 shadow-lg max-w-sm z-50">
    <div class="flex items-start">
      <svg class="h-5 w-5 text-red-600 mr-2 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <div>
        <h4 class="text-red-800 font-semibold">API连接问题</h4>
        <p class="text-red-700 text-sm mt-1">{{ appStore.apiMessage || '无法连接到后端服务' }}</p>
        <p class="text-red-600 text-xs mt-2">请确保后端服务正在运行 (端口: 8000)</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useAppStore } from '~/stores/app'

const appStore = useAppStore()
</script>