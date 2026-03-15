<template>
  <div class="flex-1 flex flex-col min-h-0 min-w-0">
    <div v-if="selectedContact" class="flex-1 flex flex-col min-h-0 relative">
      <div class="chat-header">
        <div class="flex items-center gap-3">
          <h2 class="text-base font-medium text-gray-900" :class="{ 'privacy-blur': privacyMode }">
            {{ selectedContact ? selectedContact.name : '' }}
          </h2>
        </div>
        <div class="ml-auto flex items-center gap-2">
          <button class="header-btn-icon" @click="refreshSelectedMessages" :disabled="isLoadingMessages" title="刷新消息">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
          </button>
          <button class="header-btn-icon" @click="openExportModal" :disabled="isExportCreating" title="导出聊天记录">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
          </button>
          <button class="header-btn-icon" :class="{ 'header-btn-icon-active': reverseMessageSides }" @click="toggleReverseMessageSides" :disabled="!selectedContact" :title="reverseMessageSides ? '取消反转消息位置' : '反转消息位置'">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 7h14" />
              <path d="M14 3l4 4-4 4" />
              <path d="M20 17H6" />
              <path d="M10 13l-4 4 4 4" />
            </svg>
          </button>
          <button class="header-btn-icon" :class="{ 'header-btn-icon-active': messageSearchOpen }" @click="toggleMessageSearch" :title="messageSearchOpen ? '关闭搜索 (Esc)' : '搜索聊天记录 (Ctrl+F)'">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 16 16">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
            </svg>
          </button>
          <button class="header-btn-icon" :class="{ 'header-btn-icon-active': timeSidebarOpen }" @click="toggleTimeSidebar" :disabled="!selectedContact || isLoadingMessages" title="按日期定位">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M8 7V3m8 4V3M3 11h18" />
              <rect x="4" y="5" width="16" height="16" rx="2" ry="2" stroke-width="1.8" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 14h2m3 0h2m3 0h2M7 18h2m3 0h2" />
            </svg>
          </button>
          <select
            v-model="messageTypeFilter"
            class="message-filter-select"
            :disabled="isLoadingMessages || searchContext.active"
            :title="searchContext.active ? '上下文模式下暂不可筛选' : '筛选消息类型'"
          >
            <option v-for="opt in messageTypeFilterOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
      </div>

      <div v-if="searchContext.active" class="px-6 py-2 border-b border-emerald-200 bg-emerald-50 flex items-center gap-3">
        <div class="text-sm text-emerald-900">
          {{ searchContextBannerText }}
        </div>
        <div class="ml-auto flex items-center gap-2">
          <button type="button" class="text-xs px-3 py-1 rounded-md bg-white border border-emerald-200 hover:bg-emerald-100" @click="exitSearchContext">
            退出定位
          </button>
          <button type="button" class="text-xs px-3 py-1 rounded-md bg-white border border-gray-200 hover:bg-gray-50" @click="refreshSelectedMessages">
            返回最新
          </button>
        </div>
      </div>

      <MessageList :state="state" />

      <button
        v-if="showJumpToBottom"
        type="button"
        class="absolute bottom-6 right-6 z-20 w-10 h-10 rounded-full bg-white/90 border border-gray-200 shadow hover:bg-white flex items-center justify-center"
        title="回到最新"
        @click="scrollToBottom"
      >
        <svg class="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
    </div>

    <div v-else class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <div class="w-20 h-20 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-[#03C160]/10 to-[#03C160]/5 flex items-center justify-center">
          <svg class="w-10 h-10 text-[#03C160]/60" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z"/>
          </svg>
        </div>
        <h3 class="text-base font-medium text-gray-700 mb-1.5">选择一个会话</h3>
        <p class="text-sm text-gray-400">
          从左侧列表选择联系人查看聊天记录
        </p>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'
import MessageList from '~/components/chat/MessageList.vue'

export default defineComponent({
  name: 'ConversationPane',
  components: { MessageList },
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    return {
      ...props.state
    }
  }
})
</script>
