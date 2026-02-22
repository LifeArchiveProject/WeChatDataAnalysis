<template>
  <div
    class="border-r border-gray-200 flex flex-col"
    :style="{ backgroundColor: '#e8e7e7', width: '60px', minWidth: '60px', maxWidth: '60px' }"
  >
    <div class="flex-1 flex flex-col justify-start pt-0 gap-0">
      <!-- Avatar -->
      <div class="w-full h-[60px] flex items-center justify-center">
        <div class="w-[40px] h-[40px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">
          <img v-if="selfAvatarUrl" :src="selfAvatarUrl" alt="avatar" class="w-full h-full object-cover" />
          <div
            v-else
            class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
            :style="{ backgroundColor: '#4B5563' }"
          >
            我
          </div>
        </div>
      </div>

      <!-- Chat -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="聊天"
        @click="goChat"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isChatRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Edits -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="修改记录"
        @click="goEdits"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isEditsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Moments -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="朋友圈"
        @click="goSns"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isSnsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
            <svg
              class="w-full h-full"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="14.31" y1="8" x2="20.05" y2="17.94" />
              <line x1="9.69" y1="8" x2="21.17" y2="8" />
              <line x1="7.38" y1="12" x2="13.12" y2="2.06" />
              <line x1="9.69" y1="16" x2="3.95" y2="6.06" />
              <line x1="14.31" y1="16" x2="2.83" y2="16" />
              <line x1="16.62" y1="12" x2="10.88" y2="21.94" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Contacts -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="联系人"
        @click="goContacts"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isContactsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
              <circle cx="10" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Wrapped -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="年度总结"
        @click="goWrapped"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isWrappedRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
            <svg
              class="w-full h-full"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <rect x="4" y="5" width="16" height="15" rx="2" />
              <path d="M8 3v4" />
              <path d="M16 3v4" />
              <path d="M4 9h16" />
              <path d="M8.5 15l2-2 1.5 1.5 3-3" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Realtime -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center group"
        :class="realtimeBusy ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'"
        :title="realtimeTitle"
        @click="toggleRealtime"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <svg
            class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]"
            :class="realtimeEnabled ? 'text-[#07b75b]' : 'text-[#5d5d5d]'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M13 2L4 14h7l-1 8 9-12h-7z" />
          </svg>
        </div>
      </div>

      <!-- Privacy -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        @click="privacyStore.toggle"
        :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="privacyMode ? 'text-[#07b75b]' : 'text-[#5d5d5d]'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path v-if="privacyMode" stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
            <path v-else stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
            <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
          </svg>
        </div>
      </div>

      <!-- Settings -->
      <div
        class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        @click="goSettings"
        title="设置"
      >
        <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
          <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isSettingsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
            />
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { useChatRealtimeStore } from '~/stores/chatRealtime'
import { usePrivacyStore } from '~/stores/privacy'

const route = useRoute()

const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const realtimeStore = useChatRealtimeStore()
const { enabled: realtimeEnabled, available: realtimeAvailable, checking: realtimeChecking, statusError: realtimeStatusError, toggling: realtimeToggling } = storeToRefs(realtimeStore)

onMounted(async () => {
  await chatAccounts.ensureLoaded()
})

const sidebarMediaBase = process.client ? 'http://localhost:8000' : ''

const selfAvatarUrl = computed(() => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return ''
  return `${sidebarMediaBase}/api/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(acc)}`
})

const isChatRoute = computed(() => route.path?.startsWith('/chat'))
const isEditsRoute = computed(() => route.path?.startsWith('/edits'))
const isSnsRoute = computed(() => route.path?.startsWith('/sns'))
const isContactsRoute = computed(() => route.path?.startsWith('/contacts'))
const isWrappedRoute = computed(() => route.path?.startsWith('/wrapped'))
const isSettingsRoute = computed(() => route.path?.startsWith('/settings'))

const goChat = async () => {
  await navigateTo('/chat')
}

const goEdits = async () => {
  await navigateTo('/edits')
}

const goSns = async () => {
  await navigateTo('/sns')
}

const goContacts = async () => {
  await navigateTo('/contacts')
}

const goWrapped = async () => {
  await navigateTo('/wrapped')
}

const goSettings = async () => {
  await navigateTo('/settings')
}

const realtimeBusy = computed(() => !!realtimeChecking.value || !!realtimeToggling.value)

const realtimeTitle = computed(() => {
  if (realtimeEnabled.value) return '关闭实时更新（全局）'
  if (realtimeAvailable.value) return '开启实时更新（全局）'
  return realtimeStatusError.value || '实时模式不可用'
})

const toggleRealtime = async () => {
  if (realtimeBusy.value) return
  await realtimeStore.toggle({ silent: false })
}
</script>
