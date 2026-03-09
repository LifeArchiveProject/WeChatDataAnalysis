<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- Left sidebar rail is provided by `frontend/app.vue` -->
    <div v-if="false" class="border-r border-gray-200 flex flex-col" style="background-color: #e8e7e7; width: 60px; min-width: 60px; max-width: 60px">
      <div class="flex-1 flex flex-col justify-start pt-0 gap-0">
        <!-- 头像（类似微信侧边栏） -->
        <div class="w-full h-[60px] flex items-center justify-center">
          <div class="w-[40px] h-[40px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">
            <img v-if="selfAvatarUrl" :src="selfAvatarUrl" alt="avatar" class="w-full h-full object-cover" />
            <div
              v-else
              class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
              style="background-color: #4B5563"
            >
              我
            </div>
          </div>
        </div>

        <!-- 聊天图标 (与 oh-my-wechat 一致) -->
        <div class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center group">
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md bg-transparent group-hover:bg-[#E1E1E1] flex items-center justify-center transition-colors">
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)] text-[#07b75b]">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z" />
              </svg>
            </div>
          </div>
        </div>

        <!-- 朋友圈图标（Aperture 风格） -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="朋友圈"
          @click="goSns"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
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

        <!-- 联系人图标 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="联系人"
          @click="goContacts"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
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

        <!-- 年度总结图标 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="年度总结"
          @click="goWrapped"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
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

        <!-- 实时模式按钮（全局） -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center group"
          :class="realtimeChecking ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'"
          :title="realtimeEnabled ? '关闭实时更新（全局）' : (realtimeAvailable ? '开启实时更新（全局）' : (realtimeStatusError || '实时模式不可用'))"
          @click="toggleRealtimeFromSidebar"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="realtimeEnabled ? 'text-[#07b75b]' : 'text-[#5d5d5d]'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M13 2L4 14h7l-1 8 9-12h-7z" />
            </svg>
          </div>
        </div>
        
        <!-- 隐私模式按钮 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          @click="togglePrivacyMode"
          :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="privacyMode ? 'text-[#07b75b]' : 'text-[#5d5d5d]'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path v-if="privacyMode" stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
              <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
            </svg>
          </div>
        </div>

        <!-- 设置按钮 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          @click="goSettings"
          title="设置"
        >
          <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]">
            <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)] text-[#5d5d5d]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
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

    <!-- 中间列表区域 -->
    <div
      class="session-list-panel border-r border-gray-200 flex flex-col min-h-0 shrink-0 relative"
      :style="{ backgroundColor: '#F7F7F7', '--session-list-width': sessionListWidth + 'px' }"
    >
      <!-- 拖动调整会话列表宽度 -->
      <div
        class="session-list-resizer"
        :class="{ 'session-list-resizer-active': sessionListResizing }"
        title="拖动调整会话列表宽度"
        @pointerdown="onSessionListResizerPointerDown"
        @dblclick="resetSessionListWidth"
      />
      <!-- 聊天列表 -->
      <div class="h-full flex flex-col min-h-0">
        <!-- 搜索栏 -->
        <div class="p-3 border-b border-gray-200" style="background-color: #F7F7F7">
          <div class="flex items-center gap-2">
            <div class="contact-search-wrapper flex-1">
              <svg class="contact-search-icon" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
              </svg>
              <input
                type="text"
                placeholder="搜索联系人"
                v-model="searchQuery"
                class="contact-search-input"
                :class="{ 'privacy-blur': privacyMode }"
              >
              <button
                v-if="searchQuery"
                type="button"
                class="contact-search-clear"
                @click="searchQuery = ''"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>
            </div>

            <select
              v-if="availableAccounts.length > 1"
              v-model="selectedAccount"
              @change="onAccountChange"
              class="account-select"
            >
              <option v-for="acc in availableAccounts" :key="acc" :value="acc">{{ acc }}</option>
            </select>
          </div>
        </div>

        <!-- 联系人列表 -->
        <div class="flex-1 overflow-y-auto min-h-0">
          <div v-if="isLoadingContacts" class="px-3 py-4 h-full overflow-hidden">
            <div v-for="i in 15" :key="i" class="flex items-center space-x-3 h-[calc(80px/var(--dpr))]">
              <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md bg-gray-200 skeleton-pulse"></div>
              <div class="flex-1 space-y-2">
                <div class="h-3.5 bg-gray-200 rounded skeleton-pulse" :style="{ width: (60 + (i % 4) * 15) + 'px' }"></div>
                <div class="h-3 bg-gray-200 rounded skeleton-pulse" :style="{ width: (80 + (i % 3) * 20) + 'px' }"></div>
              </div>
            </div>
          </div>
          <div v-else-if="contactsError" class="px-3 py-2 text-sm text-red-500 whitespace-pre-wrap">
            {{ contactsError }}
          </div>
          <div v-else-if="contacts.length === 0" class="px-3 py-2 text-sm text-gray-500">
            暂无会话
          </div>
          <template v-else>
            <div v-for="contact in filteredContacts" :key="contact.id"
              class="px-3 cursor-pointer transition-colors duration-150 border-b border-gray-100 h-[calc(80px/var(--dpr))] flex items-center"
              :class="contact.isTop
                ? (selectedContact?.id === contact.id
                    ? 'bg-[#D2D2D2] hover:bg-[#C7C7C7]'
                    : 'bg-[#EAEAEA] hover:bg-[#DEDEDE]')
                : (selectedContact?.id === contact.id
                    ? 'bg-[#DEDEDE] hover:bg-[#d3d3d3]'
                    : 'hover:bg-[#eaeaea]')"
              @click="selectContact(contact)">
              <div class="flex items-center space-x-3 w-full">
                <!-- 联系人头像 -->
                <div class="relative flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                  <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md overflow-hidden bg-gray-300">
                    <div v-if="contact.avatar" class="w-full h-full">
                      <img :src="contact.avatar" :alt="contact.name" class="w-full h-full object-cover" referrerpolicy="no-referrer" @error="onAvatarError($event, contact)">
                    </div>
                    <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                      :style="{ backgroundColor: contact.avatarColor || '#4B5563' }">
                      {{ contact.name.charAt(0) }}
                    </div>
                  </div>
                  <span
                    v-if="contact.unreadCount > 0"
                    class="absolute z-10 -top-[calc(4px/var(--dpr))] -right-[calc(4px/var(--dpr))] w-[calc(10px/var(--dpr))] h-[calc(10px/var(--dpr))] bg-[#ed4d4d] rounded-full"
                  ></span>
                </div>
                
                <!-- 联系人信息 -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-medium text-gray-900 truncate" :class="{ 'privacy-blur': privacyMode }">{{ contact.name }}</h3>
                    <div class="flex items-center flex-shrink-0 ml-2">
                      <span class="text-xs text-gray-500">{{ contact.lastMessageTime }}</span>
                    </div>
                  </div>
                  <p class="text-xs text-gray-500 truncate mt-0.5 leading-tight" :class="{ 'privacy-blur': privacyMode }">
                    <span
                      v-for="(seg, idx) in parseTextWithEmoji(
                        (contact.unreadCount > 0 ? `[${contact.unreadCount > 99 ? '99+' : contact.unreadCount}条] ` : '') +
                        String(contact.lastMessage || '')
                      )"
                      :key="idx"
                    >
                      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                      <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 样式展示列表已移除 -->
    </div>

    <!-- 右侧聊天区域 -->
    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <div class="flex-1 flex min-h-0">
      <!-- 聊天主区域 -->
      <div class="flex-1 flex flex-col min-h-0 min-w-0">
        <div v-if="selectedContact" class="flex-1 flex flex-col min-h-0 relative">
          <!-- 聊天头部 -->
          <div class="chat-header">
            <div class="flex items-center gap-3">
              <h2 class="text-base font-medium text-gray-900" :class="{ 'privacy-blur': privacyMode }">
                {{ selectedContact ? selectedContact.name : '' }}
              </h2>
            </div>
            <div class="ml-auto flex items-center gap-2">
              <button
                class="header-btn-icon"
                @click="refreshSelectedMessages"
                :disabled="isLoadingMessages"
                title="刷新消息"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
              </button>
              <button
                class="header-btn-icon"
                @click="openExportModal"
                :disabled="isExportCreating"
                title="导出聊天记录"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
              </button>
              <button
                class="header-btn-icon"
                :class="{ 'header-btn-icon-active': reverseMessageSides }"
                @click="toggleReverseMessageSides"
                :disabled="!selectedContact"
                :title="reverseMessageSides ? '取消反转消息位置' : '反转消息位置'"
              >
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 7h14" />
                  <path d="M14 3l4 4-4 4" />
                  <path d="M20 17H6" />
                  <path d="M10 13l-4 4 4 4" />
                </svg>
              </button>
              <button
                class="header-btn-icon"
                :class="{ 'header-btn-icon-active': messageSearchOpen }"
                @click="toggleMessageSearch"
                :title="messageSearchOpen ? '关闭搜索 (Esc)' : '搜索聊天记录 (Ctrl+F)'"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
                </svg>
              </button>
              <button
                class="header-btn-icon"
                :class="{ 'header-btn-icon-active': timeSidebarOpen }"
                @click="toggleTimeSidebar"
                :disabled="!selectedContact || isLoadingMessages"
                title="按日期定位"
              >
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
              <button
                type="button"
                class="text-xs px-3 py-1 rounded-md bg-white border border-emerald-200 hover:bg-emerald-100"
                @click="exitSearchContext"
              >
                退出定位
              </button>
              <button
                type="button"
                class="text-xs px-3 py-1 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                @click="refreshSelectedMessages"
              >
                返回最新
              </button>
            </div>
          </div>

        <!-- 聊天消息区域 -->
        <div ref="messageContainerRef" class="flex-1 overflow-y-auto p-4 min-h-0" @scroll="onMessageScroll">
          <div v-if="selectedContact && hasMoreMessages" class="flex justify-center mb-4">
            <div
              class="text-xs px-3 py-1 rounded-md bg-white border border-gray-200 text-gray-700 select-none"
              :class="isLoadingMessages ? 'opacity-60' : 'hover:bg-gray-50 cursor-pointer'"
              @click="!isLoadingMessages && loadMoreMessages()"
            >
              {{ isLoadingMessages ? '加载中...' : '继续上滑加载更多' }}
            </div>
          </div>

          <div v-if="isLoadingMessages && messages.length === 0" class="text-center text-sm text-gray-500 py-6">
            加载中...
          </div>
          <div v-else-if="messagesError" class="text-center text-sm text-red-500 py-6 whitespace-pre-wrap">
            {{ messagesError }}
          </div>
          <div v-else-if="messages.length === 0" class="text-center text-sm text-gray-500 py-6">
            暂无聊天记录
          </div>

          <div
            v-for="message in renderMessages"
            :key="message.id"
            class="mb-6"
            :class="[
              (highlightServerIdStr && message.serverIdStr && highlightServerIdStr === message.serverIdStr) ? 'message-locate-highlight' : '',
              (highlightMessageId === message.id) ? 'bg-emerald-100/50 rounded-md px-2 py-1 -mx-2' : ''
            ]"
            :data-server-id="message.serverIdStr || ''"
            :data-msg-id="message.id"
            :data-create-time="message.createTime"
          >
            <div v-if="message.showTimeDivider" class="flex justify-center mb-4">
              <div class="px-3 py-1 text-xs text-[#9e9e9e]">
                {{ message.timeDivider }}
              </div>
            </div>

            <div v-if="message.renderType === 'system'" class="flex justify-center">
              <div class="px-3 py-1 text-xs text-[#9e9e9e]">
                {{ message.content }}
              </div>
            </div>

            <div v-else class="flex items-center" :class="message.isSent ? 'justify-end' : 'justify-start'">
              <div class="flex items-start max-w-md" :class="message.isSent ? 'flex-row-reverse' : ''">
                <!-- 消息发送者头像 -->
                <div
                  class="relative"
                  @mouseenter="onMessageAvatarMouseEnter(message)"
                  @mouseleave="onMessageAvatarMouseLeave"
                >
                  <div class="w-[calc(42px/var(--dpr))] h-[calc(42px/var(--dpr))] rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="[message.isSent ? 'ml-3' : 'mr-3', { 'privacy-blur': privacyMode }]">
                    <div v-if="message.avatar" class="w-full h-full">
                      <img
                        :src="message.avatar"
                        :alt="message.sender + '的头像'"
                        class="w-full h-full object-cover"
                        referrerpolicy="no-referrer"
                        @error="onAvatarError($event, message)"
                      >
                    </div>
                    <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                      :style="{ backgroundColor: message.avatarColor || (message.isSent ? '#4B5563' : '#6B7280') }">
                      {{ message.sender.charAt(0) }}
                    </div>
                  </div>

                  <div
                    v-if="contactProfileCardOpen && contactProfileCardMessageId === String(message.id ?? '')"
                    class="absolute z-40 w-[360px] max-w-[88vw] bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden"
                    :class="message.isSent ? 'right-0 top-[calc(100%+8px)]' : 'left-0 top-[calc(100%+8px)]'"
                    @mouseenter="onContactCardMouseEnter"
                    @mouseleave="onMessageAvatarMouseLeave"
                  >
                    <div class="px-3 py-2 border-b border-gray-200 text-sm font-medium text-gray-900">联系人资料</div>
                    <div class="p-3 space-y-3 bg-[#F6F6F6]">
                      <div v-if="contactProfileLoading" class="text-sm text-gray-500 text-center py-4">资料加载中...</div>
                      <div v-else-if="contactProfileError" class="text-sm text-red-500 whitespace-pre-wrap">{{ contactProfileError }}</div>
                      <div v-else class="bg-white rounded-md border border-gray-100 overflow-hidden">
                        <div class="p-3 flex items-center gap-3 border-b border-gray-100">
                          <div class="w-12 h-12 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                            <img v-if="contactProfileResolvedAvatar" :src="contactProfileResolvedAvatar" alt="头像" class="w-full h-full object-cover" referrerpolicy="no-referrer" />
                            <div v-else class="w-full h-full flex items-center justify-center text-white text-sm font-bold" style="background-color:#4B5563">{{ contactProfileResolvedName.charAt(0) || '?' }}</div>
                          </div>
                          <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                            <div class="text-sm text-gray-900 truncate">{{ contactProfileResolvedName || '未知联系人' }}</div>
                            <div class="text-xs text-gray-500 truncate">{{ contactProfileResolvedUsername }}</div>
                          </div>
                        </div>

                        <div class="text-sm">
                          <div class="px-3 py-2.5 flex items-start gap-3 border-b border-gray-100">
                            <div class="w-12 text-gray-500 shrink-0">昵称</div>
                            <div class="text-gray-900 break-all" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedNickname || '-' }}</div>
                          </div>
                          <div class="px-3 py-2.5 flex items-start gap-3 border-b border-gray-100">
                            <div class="w-12 text-gray-500 shrink-0">微信号</div>
                            <div class="text-gray-900 break-all" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedAlias || '-' }}</div>
                          </div>
                          <div class="px-3 py-2.5 flex items-start gap-3 border-b border-gray-100">
                            <div class="w-12 text-gray-500 shrink-0">性别</div>
                            <div class="text-gray-900 break-all" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedGender || '-' }}</div>
                          </div>
                          <div class="px-3 py-2.5 flex items-start gap-3 border-b border-gray-100">
                            <div class="w-12 text-gray-500 shrink-0">地区</div>
                            <div class="text-gray-900 break-all" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedRegion || '-' }}</div>
                          </div>
                          <div class="px-3 py-2.5 flex items-start gap-3 border-b border-gray-100">
                            <div class="w-12 text-gray-500 shrink-0">备注</div>
                            <div class="text-gray-900 break-all" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedRemark || '-' }}</div>
                          </div>
                          <div class="px-3 py-2.5 flex items-start gap-3 border-b border-gray-100">
                            <div class="w-12 text-gray-500 shrink-0">签名</div>
                            <div class="text-gray-900 whitespace-pre-wrap break-words" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedSignature || '-' }}</div>
                          </div>
                          <div class="px-3 py-2.5 flex items-start gap-3" :title="contactProfileResolvedSourceScene != null ? `来源场景码：${contactProfileResolvedSourceScene}` : ''">
                            <div class="w-12 text-gray-500 shrink-0">来源</div>
                            <div class="text-gray-900 break-all" :class="{ 'privacy-blur': privacyMode }">{{ contactProfileResolvedSource || '-' }}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <!-- 消息内容气泡（精简：移除了专用消息组件） -->
                <div
                  class="flex flex-col relative group"
                  :class="[message.isSent ? 'items-end' : 'items-start', { 'privacy-blur': privacyMode }]"
                  @contextmenu="openMediaContextMenu($event, message, 'message')"
                >
                  <div v-if="message.isGroup && !message.isSent && message.senderDisplayName" class="text-[11px] text-gray-500 mb-1" :class="message.isSent ? 'text-right' : 'text-left'">
                    {{ message.senderDisplayName }}
                  </div>
                  <div
                    class="absolute -top-6 z-10 rounded bg-black/70 text-white text-[10px] px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap"
                    :class="message.isSent ? 'right-0' : 'left-0'"
                  >
                    {{ message.fullTime }}
                  </div>
                  <!-- 链接消息仍使用 LinkCard -->
                  <LinkCard
                    v-if="message.renderType === 'link'"
                    :href="message.url"
                    :heading="message.title || message.content"
                    :abstract="message.content"
                    :preview="message.preview"
                    :fromAvatar="message.fromAvatar"
                    :from="message.from"
                    :linkType="message.linkType"
                    :isSent="message.isSent"
                    :variant="message.linkCardVariant || 'default'"
                  />
                  <div v-else-if="message.renderType === 'file'"
                    class="wechat-redpacket-card wechat-special-card wechat-file-card msg-radius"
                    :class="message.isSent ? 'wechat-special-sent-side' : ''"
                    @click="onFileClick(message)"
                    @contextmenu="openMediaContextMenu($event, message, 'file')">
                    <div class="wechat-redpacket-content">
                      <div class="wechat-redpacket-info wechat-file-info">
                        <span class="wechat-file-name">{{ message.title || message.content || '文件' }}</span>
                        <span class="wechat-file-size" v-if="message.fileSize">{{ formatFileSize(message.fileSize) }}</span>
                      </div>
                      <img :src="getFileIconUrl(message.title)" alt="" class="wechat-file-icon" />
                    </div>
                    <div class="wechat-redpacket-bottom wechat-file-bottom">
                      <img :src="wechatPcLogoUrl" alt="" class="wechat-file-logo" />
                      <span>微信电脑版</span>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'image'"
                    class="max-w-sm">
                    <div class="msg-radius overflow-hidden cursor-pointer" :class="message.isSent ? '' : ''" @click="message.imageUrl && openImagePreview(message.imageUrl)" @contextmenu="openMediaContextMenu($event, message, 'image')">
                      <img v-if="message.imageUrl" :src="message.imageUrl" alt="图片" class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity">
                      <div v-else class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                        :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                        {{ message.content }}
                      </div>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'video'" class="max-w-sm">
                    <div class="msg-radius overflow-hidden relative bg-black/5" @contextmenu="openMediaContextMenu($event, message, 'video')">
                      <img v-if="message.videoThumbUrl" :src="message.videoThumbUrl" alt="视频" class="block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover">
                      <div v-else class="px-3 py-2 text-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                        :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                        {{ message.content }}
                      </div>
                      <button
                        v-if="message.videoThumbUrl && message.videoUrl"
                        type="button"
                        class="absolute inset-0 flex items-center justify-center"
                        @click.stop="openVideoPreview(message.videoUrl, message.videoThumbUrl)"
                      >
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </button>
                      <div class="absolute inset-0 flex items-center justify-center" v-else-if="message.videoThumbUrl">
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'voice'"
                    class="wechat-voice-wrapper"
                    @contextmenu="openMediaContextMenu($event, message, 'voice')">
                    <div
                      class="wechat-voice-bubble msg-radius"
                      :class="message.isSent ? 'wechat-voice-sent' : 'wechat-voice-received'"
                      :style="{ width: getVoiceWidth(message.voiceDuration) }"
                      @click="message.voiceUrl && playVoice(message)"
                    >
                      <div class="wechat-voice-content" :class="message.isSent ? 'flex-row-reverse' : ''">
                        <svg class="wechat-voice-icon" :class="[message.isSent ? 'voice-icon-sent' : 'voice-icon-received', { 'voice-playing': playingVoiceId === message.id }]" viewBox="0 0 32 32" fill="currentColor">
                          <path d="M10.24 11.616l-4.224 4.192 4.224 4.192c1.088-1.056 1.76-2.56 1.76-4.192s-0.672-3.136-1.76-4.192z"></path>
                          <path class="voice-wave-2" d="M15.199 6.721l-1.791 1.76c1.856 1.888 3.008 4.48 3.008 7.328s-1.152 5.44-3.008 7.328l1.791 1.76c2.336-2.304 3.809-5.536 3.809-9.088s-1.473-6.784-3.809-9.088z"></path>
                          <path class="voice-wave-3" d="M20.129 1.793l-1.762 1.76c3.104 3.168 5.025 7.488 5.025 12.256s-1.921 9.088-5.025 12.256l1.762 1.76c3.648-3.616 5.887-8.544 5.887-14.016s-2.239-10.432-5.887-14.016z"></path>
                        </svg>
                        <span class="wechat-voice-duration">{{ getVoiceDurationInSeconds(message.voiceDuration) }}"</span>
                      </div>
                      <span v-if="!message.voiceRead && !message.isSent" class="wechat-voice-unread"></span>
                    </div>
                    <audio
                      v-if="message.voiceUrl"
                      :ref="el => setVoiceRef(message.id, el)"
                      :src="message.voiceUrl"
                      preload="none"
                      class="hidden"
                    ></audio>
                  </div>
                  <div v-else-if="message.renderType === 'voip'"
                    class="wechat-voip-bubble msg-radius"
                    :class="message.isSent ? 'wechat-voip-sent' : 'wechat-voip-received'">
                    <div class="wechat-voip-content" :class="message.isSent ? 'flex-row-reverse' : ''">
                      <img v-if="message.voipType === 'video'" src="/assets/images/wechat/wechat-video-light.png" class="wechat-voip-icon" alt="">
                      <img v-else src="/assets/images/wechat/wechat-audio-light.png" class="wechat-voip-icon" alt="">
                      <span class="wechat-voip-text">{{ message.content || '通话' }}</span>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'emoji'" class="max-w-sm flex items-center group" :class="message.isSent ? 'flex-row-reverse' : ''">
                    <template v-if="message.emojiUrl">
                      <img :src="message.emojiUrl" alt="表情" class="w-24 h-24 object-contain" @contextmenu="openMediaContextMenu($event, message, 'emoji')">
                      <button
                        v-if="shouldShowEmojiDownload(message)"
                        class="text-xs px-2 py-1 rounded bg-white border border-gray-200 text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity"
                        :class="message.isSent ? 'mr-2' : 'ml-2'"
                        :disabled="!!message._emojiDownloading"
                        @click.stop="onEmojiDownloadClick(message)"
                      >
                        {{ message._emojiDownloading ? '下载中...' : (message._emojiDownloaded ? '已下载' : '下载') }}
                      </button>
                    </template>
                    <div v-else class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                      :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                      {{ message.content }}
                    </div>
                  </div>
                  <template v-else-if="message.renderType === 'quote'">
                    <div
                      class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                      :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                      <span v-for="(seg, idx) in parseTextWithEmoji(message.content)" :key="idx">
                        <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                        <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                      </span>
                    </div>
                      <div
                        v-if="message.quoteTitle || message.quoteContent"
                       class="mt-[5px] px-2 text-xs text-neutral-600 rounded max-w-[404px] max-h-[65px] overflow-hidden flex items-start bg-[#e1e1e1]">
                       <div class="py-2 min-w-0 flex-1">
                         <div v-if="isQuotedVoice(message)" class="flex items-center gap-1 min-w-0">
                           <span v-if="message.quoteTitle" class="truncate flex-shrink-0">{{ message.quoteTitle }}:</span>
                           <button
                             type="button"
                             class="flex items-center gap-1 min-w-0 hover:opacity-80"
                            :disabled="!message.quoteVoiceUrl"
                            :class="!message.quoteVoiceUrl ? 'opacity-60 cursor-not-allowed' : ''"
                            @click.stop="message.quoteVoiceUrl && playQuoteVoice(message)"
                          >
                            <svg
                              class="wechat-voice-icon wechat-quote-voice-icon"
                              :class="{ 'voice-playing': playingVoiceId === getQuoteVoiceId(message) }"
                              viewBox="0 0 32 32"
                              fill="currentColor"
                            >
                              <path d="M10.24 11.616l-4.224 4.192 4.224 4.192c1.088-1.056 1.76-2.56 1.76-4.192s-0.672-3.136-1.76-4.192z"></path>
                              <path class="voice-wave-2" d="M15.199 6.721l-1.791 1.76c1.856 1.888 3.008 4.48 3.008 7.328s-1.152 5.44-3.008 7.328l1.791 1.76c2.336-2.304 3.809-5.536 3.809-9.088s-1.473-6.784-3.809-9.088z"></path>
                              <path class="voice-wave-3" d="M20.129 1.793l-1.762 1.76c3.104 3.168 5.025 7.488 5.025 12.256s-1.921 9.088-5.025 12.256l1.762 1.76c3.648-3.616 5.887-8.544 5.887-14.016s-2.239-10.432-5.887-14.016z"></path>
                            </svg>
                            <span v-if="getVoiceDurationInSeconds(message.quoteVoiceLength) > 0" class="flex-shrink-0">{{ getVoiceDurationInSeconds(message.quoteVoiceLength) }}"</span>
                            <span v-else class="flex-shrink-0">语音</span>
                          </button>
                          <audio
                            v-if="message.quoteVoiceUrl"
                            :ref="el => setVoiceRef(getQuoteVoiceId(message), el)"
                            :src="message.quoteVoiceUrl"
                            preload="none"
                             class="hidden"
                           ></audio>
                         </div>
                         <div v-else class="min-w-0 flex items-start">
                           <template v-if="isQuotedLink(message)">
                             <div class="line-clamp-2 min-w-0 flex-1">
                               <span v-if="message.quoteTitle">{{ message.quoteTitle }}:</span>
                               <span
                                 v-if="getQuotedLinkText(message)"
                                 :class="message.quoteTitle ? 'ml-1' : ''"
                               >
                                 🔗 {{ getQuotedLinkText(message) }}
                               </span>
                             </div>
                           </template>
                           <template v-else>
                             <div class="line-clamp-2 min-w-0 flex-1">
                               <span v-if="message.quoteTitle">{{ message.quoteTitle }}:</span>
                               <span
                                 v-if="message.quoteContent && !(isQuotedImage(message) && message.quoteTitle && message.quoteImageUrl && !message._quoteImageError)"
                                 :class="message.quoteTitle ? 'ml-1' : ''"
                               >
                                 {{ message.quoteContent }}
                               </span>
                             </div>
                           </template>
                         </div>
                       </div>
                       <div
                         v-if="isQuotedLink(message) && message.quoteThumbUrl && !message._quoteThumbError"
                         class="ml-2 my-2 flex-shrink-0 max-w-[98px] max-h-[49px] overflow-hidden flex items-center justify-center cursor-pointer"
                         @click.stop="openImagePreview(message.quoteThumbUrl)"
                       >
                         <img
                           :src="message.quoteThumbUrl"
                           alt="引用链接缩略图"
                           class="max-h-[49px] w-auto max-w-[98px] object-contain"
                           loading="lazy"
                           decoding="async"
                           referrerpolicy="no-referrer"
                           @error="onQuoteThumbError(message)"
                         />
                       </div>
                       <div
                         v-if="!isQuotedLink(message) && isQuotedImage(message) && message.quoteImageUrl && !message._quoteImageError"
                         class="ml-2 my-2 flex-shrink-0 max-w-[98px] max-h-[49px] overflow-hidden flex items-center justify-center cursor-pointer"
                         @click.stop="openImagePreview(message.quoteImageUrl)"
                       >
                         <img
                           :src="message.quoteImageUrl"
                           alt="引用图片"
                           class="max-h-[49px] w-auto max-w-[98px] object-contain"
                           loading="lazy"
                           decoding="async"
                           @error="onQuoteImageError(message)"
                         />
                       </div>
                     </div>
                   </template>
                  <!-- 合并转发聊天记录（Chat History） -->
                  <div
                    v-else-if="message.renderType === 'chatHistory'"
                    class="wechat-chat-history-card wechat-special-card msg-radius"
                    :class="message.isSent ? 'wechat-special-sent-side' : ''"
                    @click.stop="openChatHistoryModal(message)"
                  >
                    <div class="wechat-chat-history-body">
                      <div class="wechat-chat-history-title">{{ message.title || '聊天记录' }}</div>
                      <div class="wechat-chat-history-preview" v-if="getChatHistoryPreviewLines(message).length">
                        <div
                          v-for="(line, idx) in getChatHistoryPreviewLines(message)"
                          :key="idx"
                          class="wechat-chat-history-line"
                        >
                          {{ line }}
                        </div>
                      </div>
                    </div>
                    <div class="wechat-chat-history-bottom">
                      <span>聊天记录</span>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'transfer'"
                    class="wechat-transfer-card msg-radius"
                    :class="[{ 'wechat-transfer-received': message.transferReceived, 'wechat-transfer-returned': isTransferReturned(message), 'wechat-transfer-overdue': isTransferOverdue(message) }, message.isSent ? 'wechat-transfer-sent-side' : 'wechat-transfer-received-side']">
                    <div class="wechat-transfer-content">
                      <img src="/assets/images/wechat/wechat-returned.png" v-if="isTransferReturned(message)" class="wechat-transfer-icon" alt="">
                      <img src="/assets/images/wechat/overdue.png" v-else-if="isTransferOverdue(message)" class="wechat-transfer-icon" alt="">
                      <img src="/assets/images/wechat/wechat-trans-icon2.png" v-else-if="message.transferReceived" class="wechat-transfer-icon" alt="">
                      <img src="/assets/images/wechat/wechat-trans-icon1.png" v-else class="wechat-transfer-icon" alt="">
                      <div class="wechat-transfer-info">
                        <span class="wechat-transfer-amount" v-if="message.amount">¥{{ formatTransferAmount(message.amount) }}</span>
                        <span class="wechat-transfer-status">{{ getTransferTitle(message) }}</span>
                      </div>
                    </div>
                    <div class="wechat-transfer-bottom">
                      <span>微信转账</span>
                    </div>
                  </div>
                  <!-- 红包消息 - 微信风格橙色卡片 -->
                  <div v-else-if="message.renderType === 'redPacket'" class="wechat-redpacket-card wechat-special-card msg-radius"
                    :class="[{ 'wechat-redpacket-received': message.redPacketReceived }, message.isSent ? 'wechat-special-sent-side' : '']">
                    <div class="wechat-redpacket-content">
                      <img src="/assets/images/wechat/wechat-trans-icon3.png" v-if="!message.redPacketReceived" class="wechat-redpacket-icon" alt="">
                      <img src="/assets/images/wechat/wechat-trans-icon4.png" v-else class="wechat-redpacket-icon" alt="">
                      <div class="wechat-redpacket-info">
                        <span class="wechat-redpacket-text">{{ getRedPacketText(message) }}</span>
                        <span class="wechat-redpacket-status" v-if="message.redPacketReceived">已领取</span>
                      </div>
                    </div>
                    <div class="wechat-redpacket-bottom">
                      <span>微信红包</span>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'location'" class="max-w-sm">
                    <ChatLocationCard :message="message" />
                  </div>
                  <!-- 文本消息 -->
                  <div v-else-if="message.renderType === 'text'"
                    class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                    :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                    <span v-for="(seg, idx) in parseTextWithEmoji(message.content)" :key="idx">
                      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                      <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                    </span>
                  </div>
                  <!-- 表情消息 -->
                  <!-- 其他类型统一降级为普通文本展示 -->
                  <div v-else
                    class="px-3 py-2 text-xs max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed text-gray-700"
                    :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                    {{ message.content || ('[' + (message.type || 'unknown') + '] 消息组件已移除') }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

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

      <!-- 未选择联系人时的提示 -->
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

    <!-- 右侧时间侧边栏（按日期定位） -->
    <transition name="sidebar-slide">
      <div v-if="timeSidebarOpen" class="time-sidebar">
        <div class="time-sidebar-header">
          <div class="time-sidebar-title">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3M3 11h18" />
              <rect x="4" y="5" width="16" height="16" rx="2" ry="2" stroke-width="2" />
            </svg>
            <span>按日期定位</span>
          </div>
          <button
            type="button"
            class="time-sidebar-close"
            @click="closeTimeSidebar"
            title="关闭 (Esc)"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="time-sidebar-body">
          <div class="calendar-header">
            <button
              type="button"
              class="calendar-nav-btn"
              :disabled="timeSidebarLoading"
              title="上个月"
              @click="prevTimeSidebarMonth"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div class="calendar-month-label calendar-month-label-selects">
              <select
                v-model.number="timeSidebarYear"
                class="calendar-ym-select"
                :disabled="timeSidebarLoading"
                title="选择年份"
                @change="onTimeSidebarYearMonthChange"
              >
                <option v-for="y in timeSidebarYearOptions" :key="y" :value="y">
                  {{ y }}年
                </option>
              </select>
              <select
                v-model.number="timeSidebarMonth"
                class="calendar-ym-select"
                :disabled="timeSidebarLoading"
                title="选择月份"
                @change="onTimeSidebarYearMonthChange"
              >
                <option v-for="mm in 12" :key="mm" :value="mm">
                  {{ mm }}月
                </option>
              </select>
            </div>
            <button
              type="button"
              class="calendar-nav-btn"
              :disabled="timeSidebarLoading"
              title="下个月"
              @click="nextTimeSidebarMonth"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          <div v-if="timeSidebarError" class="time-sidebar-status time-sidebar-status-error">
            {{ timeSidebarError }}
          </div>
          <div v-else class="time-sidebar-status">
            <span v-if="timeSidebarLoading">加载中...</span>
            <span v-else>本月 {{ timeSidebarTotal }} 条消息，{{ timeSidebarActiveDays }} 天有聊天</span>
          </div>

          <div class="calendar-weekdays">
            <div v-for="w in timeSidebarWeekdays" :key="w" class="calendar-weekday">{{ w }}</div>
          </div>

          <div class="calendar-grid">
            <button
              v-for="cell in timeSidebarCalendarCells"
              :key="cell.key"
              type="button"
              class="calendar-day"
              :class="cell.className"
              :style="cell.style"
              :disabled="cell.disabled"
              :title="cell.title"
              @click="onTimeSidebarDayClick(cell)"
            >
              <span v-if="cell.day" class="calendar-day-number">{{ cell.day }}</span>
            </button>
          </div>

          <div class="time-sidebar-actions">
            <button
              type="button"
              class="time-sidebar-action-btn"
              :disabled="timeSidebarLoading || !selectedContact || isLoadingMessages"
              @click="jumpToConversationFirst"
              title="定位到会话最早消息附近"
            >
              跳转到顶部
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 右侧搜索侧边栏 -->
    <transition name="sidebar-slide">
      <div v-if="messageSearchOpen" class="search-sidebar">
          <!-- 侧边栏头部 -->
          <div class="search-sidebar-header">
            <div class="search-sidebar-title">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
              </svg>
              <span>搜索聊天记录</span>
            </div>
            <button
              type="button"
              class="search-sidebar-close"
              @click="closeMessageSearch"
              title="关闭搜索 (Esc)"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <!-- 搜索输入区域（整合所有筛选条件） -->
          <div class="search-sidebar-input-section">
            <!-- 第一行：范围 + 输入框 + 搜索按钮 -->
            <div class="search-input-combined" :class="{ 'search-input-combined-focused': searchInputFocused }">
              <!-- 左侧：范围切换 -->
              <div class="search-scope-inline">
                <button
                  type="button"
                  class="scope-inline-btn"
                  :class="{ 'scope-inline-btn-active': messageSearchScope === 'conversation' }"
                  :disabled="!selectedContact"
                  @click="messageSearchScope = 'conversation'"
                  title="当前会话"
                >
                  当前
                </button>
                <span class="scope-inline-divider">/</span>
                <button
                  type="button"
                  class="scope-inline-btn"
                  :class="{ 'scope-inline-btn-active': messageSearchScope === 'global' }"
                  @click="messageSearchScope = 'global'"
                  title="全部会话"
                >
                  全部
                </button>
              </div>

              <!-- 中间：搜索输入框 -->
              <input
                ref="messageSearchInputRef"
                v-model="messageSearchQuery"
                type="text"
                placeholder="输入关键词..."
                class="search-input-inline"
                :class="{ 'privacy-blur': privacyMode }"
                @focus="searchInputFocused = true"
                @blur="searchInputFocused = false"
                @keydown.enter.exact.prevent="runMessageSearch({ reset: true })"
                @keydown.enter.shift.prevent="onSearchPrev"
                @keydown.escape="closeMessageSearch"
              />

              <!-- 清除按钮 -->
                <button
                  v-if="messageSearchQuery"
                  type="button"
                  class="search-clear-inline"
                  @click="messageSearchQuery = ''; runMessageSearch({ reset: true })"
                >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>

              <!-- 搜索按钮 -->
              <button
                type="button"
                class="search-btn-inline"
                :disabled="messageSearchLoading"
                @click="runMessageSearch({ reset: true })"
              >
                <svg v-if="messageSearchLoading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                </svg>
              </button>
            </div>

            <!-- 第二行：筛选条件 -->
            <div class="search-filters-row">
              <!-- 时间范围 -->
              <select
                v-model="messageSearchRangeDays"
                class="search-filter-select search-filter-select-time"
                title="时间范围"
              >
                <option value="">不限时间</option>
                <option value="1">今天</option>
                <option value="3">最近3天</option>
                <option value="7">最近7天</option>
                <option value="30">最近30天</option>
                <option value="90">最近3个月</option>
                <option value="180">最近半年</option>
                <option value="365">最近1年</option>
                <option value="custom">自定义...</option>
              </select>

              <!-- 发送者筛选 -->
              <div ref="messageSearchSenderDropdownRef" class="relative flex-1">
                <button
                  type="button"
                  class="search-filter-select w-full flex items-center justify-between gap-1 disabled:opacity-60 disabled:cursor-not-allowed"
                  title="按发送者筛选"
                  :disabled="messageSearchSenderDisabled"
                  @click="toggleMessageSearchSenderDropdown"
                >
                    <span class="flex items-center gap-1 min-w-0">
                      <span class="w-4 h-4 rounded overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                        <img
                          v-if="messageSearchSelectedSenderInfo?.avatar"
                          :src="messageSearchSelectedSenderInfo.avatar"
                          alt=""
                          class="w-full h-full object-cover"
                        />
                        <span v-else class="w-full h-full flex items-center justify-center text-[9px] text-gray-500">
                          {{ messageSearchSelectedSenderInitial }}
                        </span>
                      </span>
                      <span class="truncate" :class="{ 'privacy-blur': privacyMode }">{{ messageSearchSenderLabel }}</span>
                    </span>
                    <svg class="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                    </svg>
                  </button>

                <div
                  v-if="messageSearchSenderDropdownOpen"
                  class="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-50 overflow-hidden"
                >
                  <div class="p-2 border-b border-gray-100">
                    <input
                      ref="messageSearchSenderDropdownInputRef"
                      v-model="messageSearchSenderDropdownQuery"
                      type="text"
                      placeholder="搜索发送者"
                      class="w-full text-xs px-2 py-1.5 bg-gray-50 border border-gray-200 rounded-md outline-none focus:border-[#03C160] focus:ring-1 focus:ring-[#03C160]/20"
                      :class="{ 'privacy-blur': privacyMode }"
                    />
                  </div>

                  <div class="max-h-64 overflow-y-auto">
                    <button
                      type="button"
                      class="w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs hover:bg-gray-50"
                      :class="!messageSearchSender ? 'bg-gray-50' : ''"
                      @click="selectMessageSearchSender('')"
                    >
                      <span class="w-6 h-6 rounded-md overflow-hidden bg-gray-200 flex-shrink-0 flex items-center justify-center text-[10px] text-gray-500">
                        全
                      </span>
                      <span class="truncate">不限发送者</span>
                    </button>

                    <div v-if="messageSearchSenderLoading" class="px-2 py-3 text-xs text-gray-500">
                      加载中...
                    </div>
                    <div v-else-if="messageSearchSenderError" class="px-2 py-3 text-xs text-red-500 whitespace-pre-wrap">
                      {{ messageSearchSenderError }}
                    </div>
                    <div v-else-if="filteredMessageSearchSenderOptions.length === 0" class="px-2 py-3 text-xs text-gray-500">
                      {{ messageSearchScope === 'global' && String(messageSearchQuery || '').trim().length < 2 ? '请输入关键词后再筛选发送者' : '暂无发送者' }}
                    </div>
                    <template v-else>
                      <button
                        v-for="s in filteredMessageSearchSenderOptions"
                        :key="s.username"
                        type="button"
                        class="w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs hover:bg-gray-50"
                        :class="messageSearchSender === s.username ? 'bg-gray-50' : ''"
                        @click="selectMessageSearchSender(s.username)"
                      >
                        <div class="w-6 h-6 rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                          <img v-if="s.avatar" :src="s.avatar" :alt="(s.displayName || s.username) + '头像'" class="w-full h-full object-cover" />
                          <div v-else class="w-full h-full flex items-center justify-center text-white text-[10px] font-bold" style="background-color: #6B7280">
                            {{ String(s.displayName || s.username || '').charAt(0) }}
                          </div>
                        </div>
                        <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                          <div class="truncate text-gray-800">{{ s.displayName || s.username }}</div>
                          <div class="truncate text-[10px] text-gray-400">{{ s.username }}</div>
                        </div>
                        <div class="text-[10px] text-gray-400 flex-shrink-0">{{ formatCount(s.count) }}</div>
                      </button>
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <!-- 会话类型（仅全局搜索） -->
            <div v-if="messageSearchScope === 'global'" class="search-session-type-row">
              <button
                type="button"
                class="search-session-type-btn"
                :class="{ 'search-session-type-btn-active': !String(messageSearchSessionType || '').trim() }"
                @click="messageSearchSessionType = ''"
              >
                全部
              </button>
              <button
                type="button"
                class="search-session-type-btn"
                :class="{ 'search-session-type-btn-active': String(messageSearchSessionType || '') === 'group' }"
                @click="messageSearchSessionType = 'group'"
              >
                群聊
              </button>
              <button
                type="button"
                class="search-session-type-btn"
                :class="{ 'search-session-type-btn-active': String(messageSearchSessionType || '') === 'single' }"
                @click="messageSearchSessionType = 'single'"
              >
                单聊
              </button>
            </div>

            <!-- 自定义时间范围（当选择自定义时显示） -->
            <div v-if="messageSearchRangeDays === 'custom'" class="search-custom-date-row">
              <input
                v-model="messageSearchStartDate"
                type="date"
                class="search-date-input"
                title="开始日期"
              />
              <span class="search-date-separator">至</span>
              <input
                v-model="messageSearchEndDate"
                type="date"
                class="search-date-input"
                title="结束日期"
              />
            </div>
          </div>

          <!-- 搜索历史 -->
          <div v-if="!messageSearchQuery.trim() && searchHistory.length > 0" class="search-sidebar-history">
            <div class="sidebar-section-header">
              <span class="sidebar-section-title">搜索历史</span>
              <button type="button" class="sidebar-clear-btn" @click="clearSearchHistory">清空</button>
            </div>
            <div class="sidebar-history-list">
              <button
                v-for="(item, idx) in searchHistory"
                :key="idx"
                type="button"
                class="sidebar-history-item"
                :class="{ 'privacy-blur': privacyMode }"
                @click="applySearchHistory(item)"
              >
                <svg class="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span class="truncate">{{ item }}</span>
              </button>
            </div>
          </div>

          <!-- 搜索状态 -->
          <div class="search-sidebar-status">
            <div v-if="messageSearchError" class="sidebar-status-error">
              {{ messageSearchError }}
            </div>
            <div v-else-if="messageSearchQuery.trim()" class="sidebar-status-info">
              <div class="flex items-center justify-between gap-2">
                <div class="min-w-0">
                  <template v-if="messageSearchBackendStatus === 'index_building'">
                    正在建立索引
                    <span v-if="messageSearchIndexProgressText" class="sidebar-status-detail">（{{ messageSearchIndexProgressText }}）</span>
                  </template>
                  <template v-else>
                    找到 <strong>{{ messageSearchTotal }}</strong> 条结果
                  </template>
                </div>
                <button
                  type="button"
                  class="sidebar-index-btn"
                  :disabled="messageSearchIndexActionDisabled"
                  @click="onMessageSearchIndexAction"
                >
                  {{ messageSearchIndexActionText }}
                </button>
              </div>
              <div v-if="messageSearchBackendStatus !== 'index_building' && messageSearchIndexText" class="sidebar-status-detail mt-0.5">
                {{ messageSearchIndexText }}
              </div>
            </div>
          </div>

          <!-- 搜索结果列表 -->
          <div class="search-sidebar-results">
            <div v-if="messageSearchResults.length" class="sidebar-results-list">
              <div
                v-for="(hit, idx) in messageSearchResults"
                :key="hit.id + ':' + idx"
                class="sidebar-result-card"
                :class="{ 'sidebar-result-card-selected': idx === messageSearchSelectedIndex }"
                @click="onSearchHitClick(hit, idx)"
              >
                <div class="sidebar-result-row">
                  <div class="sidebar-result-avatar" :class="{ 'privacy-blur': privacyMode }">
                    <img
                      v-if="getMessageSearchHitAvatarUrl(hit)"
                      :src="getMessageSearchHitAvatarUrl(hit)"
                      :alt="getMessageSearchHitAvatarAlt(hit)"
                      class="w-full h-full object-cover"
                    />
                    <div v-else class="sidebar-result-avatar-fallback">
                      {{ getMessageSearchHitAvatarInitial(hit) }}
                    </div>
                  </div>
                  <div class="sidebar-result-body" :class="{ 'privacy-blur': privacyMode }">
                    <div class="sidebar-result-header">
                      <span v-if="messageSearchScope === 'global'" class="sidebar-result-contact">
                        {{ hit.conversationName || hit.username }}
                      </span>
                      <span class="sidebar-result-time">{{ formatMessageFullTime(hit.createTime) }}</span>
                    </div>
                    <div class="sidebar-result-sender">
                      {{ hit.senderDisplayName || hit.senderUsername || (hit.isSent ? '我' : '') }}
                    </div>
                    <div class="sidebar-result-content" v-html="highlightKeyword(hit.snippet || hit.content || hit.title || '', messageSearchQuery)"></div>
                  </div>
                </div>
              </div>

              <!-- 加载更多 -->
              <div v-if="messageSearchHasMore" class="sidebar-load-more">
                <button
                  type="button"
                  class="sidebar-load-more-btn"
                  :disabled="messageSearchLoading"
                  @click="loadMoreSearchResults"
                >
                  {{ messageSearchLoading ? '加载中...' : '加载更多' }}
                </button>
              </div>
            </div>

            <!-- 索引构建中 -->
            <div v-else-if="messageSearchQuery.trim() && !messageSearchLoading && !messageSearchError && messageSearchBackendStatus === 'index_building'" class="sidebar-empty-state">
              <svg class="sidebar-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div class="sidebar-empty-text">正在建立搜索索引</div>
              <div class="sidebar-empty-hint">首次建立索引会花一些时间，完成后会自动开始搜索</div>
              <div v-if="messageSearchIndexProgressText" class="sidebar-empty-hint mt-1">{{ messageSearchIndexProgressText }}</div>
            </div>

            <!-- 空状态 -->
            <div v-else-if="messageSearchQuery.trim() && !messageSearchLoading && !messageSearchError && messageSearchBackendStatus !== 'index_building' && messageSearchTotal === 0" class="sidebar-empty-state">
              <svg class="sidebar-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div class="sidebar-empty-text">未找到相关消息</div>
              <div class="sidebar-empty-hint">尝试调整关键词或过滤条件</div>
            </div>

            <!-- 初始提示 -->
            <div v-else-if="!messageSearchQuery.trim() && !searchHistory.length" class="sidebar-initial-state">
              <svg class="sidebar-initial-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
              </svg>
              <div class="sidebar-initial-text">输入关键词开始搜索</div>
              <div class="sidebar-initial-hint">
                <kbd>Enter</kbd> 下一条 · <kbd>Shift+Enter</kbd> 上一条
              </div>
            </div>
          </div>
        </div>
      </transition>

    <!-- 图片预览弹窗 (全局固定定位) -->
    <div v-if="previewImageUrl" 
      class="fixed inset-0 z-[13000] bg-black/90 flex items-center justify-center cursor-zoom-out"
      @click="closeImagePreview">
      <img :src="previewImageUrl" alt="预览" class="max-w-[90vw] max-h-[90vh] object-contain" @click.stop>
      <button 
        class="absolute top-4 right-4 text-white/80 hover:text-white p-2 rounded-full bg-black/30 hover:bg-black/50 transition-colors"
        @click="closeImagePreview">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- 视频预览弹窗 (全局固定定位) -->
    <div
      v-if="previewVideoUrl"
      class="fixed inset-0 z-[13000] bg-black/90 flex items-center justify-center"
      @click="closeVideoPreview"
    >
      <div class="relative max-w-[92vw] max-h-[92vh] flex flex-col items-center" @click.stop>
        <video
          :key="previewVideoUrl"
          :src="previewVideoUrl"
          :poster="previewVideoPosterUrl"
          class="max-w-[90vw] max-h-[90vh] object-contain"
          controls
          autoplay
          playsinline
          @error="onPreviewVideoError"
        ></video>
        <div
          v-if="previewVideoError"
          class="mt-3 text-xs text-red-200 whitespace-pre-wrap text-center max-w-[90vw]"
        >
          {{ previewVideoError }}
        </div>
      </div>
      <button
        class="absolute top-4 right-4 text-white/80 hover:text-white p-2 rounded-full bg-black/30 hover:bg-black/50 transition-colors"
        @click.stop="closeVideoPreview"
      >
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- 浮动窗口（可拖动）：合并消息 / 链接卡片 -->
    <div
      v-for="win in floatingWindows"
      :key="win.id"
      class="fixed"
      :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.zIndex }"
      @mousedown="focusFloatingWindow(win.id)"
    >
      <div
        class="bg-[#f7f7f7] rounded-xl shadow-xl overflow-hidden border border-gray-200 flex flex-col"
        :style="{ width: win.width + 'px', height: win.height + 'px' }"
      >
        <div
          class="px-3 py-2 bg-[#f7f7f7] border-b border-gray-200 flex items-center justify-between select-none cursor-move"
          @mousedown.stop="startFloatingWindowDrag(win.id, $event)"
          @touchstart.stop="startFloatingWindowDrag(win.id, $event)"
        >
          <div class="text-sm text-[#161616] truncate min-w-0">{{ win.title || (win.kind === 'link' ? '链接' : '聊天记录') }}</div>
          <button
            type="button"
            class="p-2 rounded hover:bg-black/5 flex-shrink-0"
            @click.stop="closeFloatingWindow(win.id)"
            aria-label="关闭"
            title="关闭"
          >
            <svg class="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-auto bg-[#f7f7f7]">
          <!-- Chat history window -->
          <template v-if="win.kind === 'chatHistory'">
            <div v-if="win.loading" class="text-xs text-gray-500 text-center py-2">加载中...</div>
            <div v-if="!win.records || !win.records.length" class="text-sm text-gray-500 text-center py-10">
              没有可显示的聊天记录
            </div>
            <template v-else>
              <div
                v-for="(rec, idx) in win.records"
                :key="rec.id || idx"
                class="px-4 py-3 flex gap-3 border-b border-gray-100 bg-[#f7f7f7]"
              >
                <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                  <img
                    v-if="rec.senderAvatar"
                    :src="rec.senderAvatar"
                    alt="头像"
                    class="w-full h-full object-cover"
                    referrerpolicy="no-referrer"
                    loading="lazy"
                    decoding="async"
                  />
                  <div v-else class="w-full h-full flex items-center justify-center text-xs font-bold text-gray-600">
                    {{ (rec.senderDisplayName || rec.sourcename || '?').charAt(0) }}
                  </div>
                </div>

                <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                  <div class="flex items-start gap-2">
                    <div class="min-w-0 flex-1">
                      <div
                        v-if="win.info?.isChatRoom && (rec.senderDisplayName || rec.sourcename)"
                        class="text-xs text-gray-500 leading-none truncate mb-1"
                      >
                        {{ rec.senderDisplayName || rec.sourcename }}
                      </div>
                    </div>
                    <div v-if="rec.fullTime || rec.sourcetime" class="text-xs text-gray-400 flex-shrink-0 leading-none">
                      {{ rec.fullTime || rec.sourcetime }}
                    </div>
                  </div>

                  <div class="mt-1">
                    <!-- Nested chat history -->
                    <div
                      v-if="rec.renderType === 'chatHistory'"
                      class="wechat-chat-history-card wechat-special-card msg-radius cursor-pointer"
                      @click.stop="openNestedChatHistory(rec)"
                    >
                      <div class="wechat-chat-history-body">
                        <div class="wechat-chat-history-title">{{ rec.title || '聊天记录' }}</div>
                        <div class="wechat-chat-history-preview" v-if="getChatHistoryPreviewLines(rec).length">
                          <div
                            v-for="(line, lidx) in getChatHistoryPreviewLines(rec)"
                            :key="lidx"
                            class="wechat-chat-history-line"
                          >
                            {{ line }}
                          </div>
                        </div>
                      </div>
                      <div class="wechat-chat-history-bottom">
                        <span>聊天记录</span>
                      </div>
                    </div>

                    <!-- Link card -->
                    <div
                      v-else-if="rec.renderType === 'link'"
                      class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
                      @click.stop="openChatHistoryLinkWindow(rec)"
                      @contextmenu="openMediaContextMenu($event, rec, 'message')"
                    >
                      <div class="wechat-link-content">
                        <div class="wechat-link-title">{{ rec.title || rec.content || rec.url || '链接' }}</div>
                        <div v-if="rec.content || rec.preview" class="wechat-link-summary">
                          <div v-if="rec.content" class="wechat-link-desc">{{ rec.content }}</div>
                          <div v-if="rec.preview" class="wechat-link-thumb">
                            <img :src="rec.preview" :alt="rec.title || '链接预览'" class="wechat-link-thumb-img" referrerpolicy="no-referrer" loading="lazy" decoding="async" @error="onChatHistoryLinkPreviewError(rec)" />
                          </div>
                        </div>
                      </div>
                      <div class="wechat-link-from">
                        <div class="wechat-link-from-avatar" :style="rec._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                          <span v-if="(!rec.fromAvatar) || (!rec._fromAvatarImgOk)">{{ getChatHistoryLinkFromAvatarText(rec) || '\u200B' }}</span>
                          <img
                            v-if="rec.fromAvatar && !rec._fromAvatarImgError"
                            :src="rec.fromAvatar"
                            alt=""
                            class="wechat-link-from-avatar-img"
                            referrerpolicy="no-referrer"
                            loading="lazy"
                            decoding="async"
                            @load="onChatHistoryFromAvatarLoad(rec)"
                            @error="onChatHistoryFromAvatarError(rec)"
                          />
                        </div>
                        <div class="wechat-link-from-name">{{ getChatHistoryLinkFromText(rec) || '\u200B' }}</div>
                      </div>
                    </div>

                    <!-- Image -->
                    <div
                      v-else-if="rec.renderType === 'image'"
                      class="msg-radius overflow-hidden cursor-pointer inline-block"
                      @click="rec.imageUrl && openImagePreview(rec.imageUrl)"
                      @contextmenu="openMediaContextMenu($event, rec, 'image')"
                    >
                      <img
                        v-if="rec.imageUrl"
                        :src="rec.imageUrl"
                        alt="图片"
                        class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity"
                      />
                      <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[图片]' }}</div>
                    </div>

                    <!-- Emoji -->
                    <div
                      v-else-if="rec.renderType === 'emoji'"
                      class="inline-block"
                      @contextmenu="openMediaContextMenu($event, rec, 'emoji')"
                    >
                      <img v-if="rec.emojiUrl" :src="rec.emojiUrl" alt="表情" class="w-24 h-24 object-contain" />
                      <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[表情]' }}</div>
                    </div>

                    <!-- Video (fallback to thumbnail/play) -->
                    <div
                      v-else-if="rec.renderType === 'video'"
                      class="msg-radius overflow-hidden relative bg-black/5 inline-block"
                      @contextmenu="openMediaContextMenu($event, rec, 'video')"
                    >
                      <img
                        v-if="rec.videoThumbUrl && !rec._videoThumbError"
                        :src="rec.videoThumbUrl"
                        alt="视频"
                        class="block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover"
                        @error="onChatHistoryVideoThumbError(rec)"
                      />
                      <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[视频]' }}</div>
                      <button
                        v-if="rec.videoUrl"
                        type="button"
                        class="absolute inset-0 flex items-center justify-center"
                        @click.stop="openVideoPreview(rec.videoUrl, rec.videoThumbUrl)"
                      >
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </button>
                      <div
                        v-if="rec.videoDuration"
                        class="absolute bottom-2 right-2 text-xs text-white bg-black/55 px-1.5 py-0.5 rounded"
                      >
                        {{ formatChatHistoryVideoDuration(rec.videoDuration) }}
                      </div>
                    </div>

                    <!-- Text / others -->
                    <div
                      v-else
                      class="text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                      @contextmenu="openMediaContextMenu($event, rec, 'message')"
                    >
                      <span v-for="(seg, sidx) in parseTextWithEmoji(rec.content)" :key="sidx">
                        <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                        <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </template>

          <!-- Link detail window -->
          <template v-else-if="win.kind === 'link'">
            <div class="p-4 space-y-3">
              <div
                class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
                @click.stop="win.url && openUrlInBrowser(win.url)"
                @contextmenu="openMediaContextMenu($event, win, 'message')"
              >
                <div class="wechat-link-content">
                  <div class="wechat-link-title">{{ win.title || win.url || '链接' }}</div>
                  <div v-if="win.content || win.preview" class="wechat-link-summary">
                    <div v-if="win.content" class="wechat-link-desc">{{ win.content }}</div>
                    <div v-if="win.preview" class="wechat-link-thumb">
                      <img :src="win.preview" :alt="win.title || '链接预览'" class="wechat-link-thumb-img" referrerpolicy="no-referrer" loading="lazy" decoding="async" @error="onChatHistoryLinkPreviewError(win)" />
                    </div>
                  </div>
                </div>
                <div class="wechat-link-from">
                  <div class="wechat-link-from-avatar" :style="win._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                    <span v-if="(!win.fromAvatar) || (!win._fromAvatarImgOk)">{{ getChatHistoryLinkFromAvatarText(win) || '\u200B' }}</span>
                    <img
                      v-if="win.fromAvatar && !win._fromAvatarImgError"
                      :src="win.fromAvatar"
                      alt=""
                      class="wechat-link-from-avatar-img"
                      referrerpolicy="no-referrer"
                      loading="lazy"
                      decoding="async"
                      @load="onChatHistoryFromAvatarLoad(win)"
                      @error="onChatHistoryFromAvatarError(win)"
                    />
                  </div>
                  <div class="wechat-link-from-name">{{ getChatHistoryLinkFromText(win) || '\u200B' }}</div>
                </div>
              </div>

              <div v-if="win.loading" class="text-xs text-gray-500">解析中...</div>
              <div v-if="win.url" class="text-xs text-gray-500 break-all">{{ win.url }}</div>
              <div class="flex gap-2">
                <button
                  class="px-3 py-1.5 text-sm rounded-md border border-gray-200 bg-white hover:bg-gray-50"
                  type="button"
                  :disabled="!win.url"
                  :class="!win.url ? 'opacity-50 cursor-not-allowed' : ''"
                  @click.stop="win.url && openUrlInBrowser(win.url)"
                >
                  在浏览器打开
                </button>
                <button
                  class="px-3 py-1.5 text-sm rounded-md border border-gray-200 bg-white hover:bg-gray-50"
                  type="button"
                  :disabled="!win.url"
                  :class="!win.url ? 'opacity-50 cursor-not-allowed' : ''"
                  @click.stop="win.url && copyTextToClipboard(win.url)"
                >
                  复制链接
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 合并转发聊天记录弹窗 -->
    <div
      v-if="chatHistoryModalVisible"
      class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      @click="closeChatHistoryModal"
    >
      <div
        class="w-[92vw] max-w-[560px] max-h-[80vh] bg-[#f7f7f7] rounded-xl shadow-xl overflow-hidden flex flex-col"
        @click.stop
      >
        <div class="px-4 py-3 bg-[#f7f7f7] border-b border-gray-200 flex items-center justify-between">
          <div class="flex items-center gap-2 min-w-0">
            <button
              v-if="chatHistoryModalStack.length"
              type="button"
              class="p-2 rounded hover:bg-black/5 flex-shrink-0"
              @click="goBackChatHistoryModal"
              aria-label="返回"
              title="返回"
            >
              <svg class="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div class="text-sm text-[#161616] truncate">{{ chatHistoryModalTitle || '聊天记录' }}</div>
          </div>
          <button
            type="button"
            class="p-2 rounded hover:bg-black/5"
            @click="closeChatHistoryModal"
            aria-label="关闭"
            title="关闭"
          >
            <svg class="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-auto bg-[#f7f7f7]">
          <div v-if="!chatHistoryModalRecords.length" class="text-sm text-gray-500 text-center py-10">
            没有可显示的聊天记录
          </div>
          <template v-else>
            <div
              v-for="(rec, idx) in chatHistoryModalRecords"
              :key="rec.id || idx"
              class="px-4 py-3 flex gap-3 border-b border-gray-100 bg-[#f7f7f7]"
            >
              <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="rec.senderAvatar"
                  :src="rec.senderAvatar"
                  alt="头像"
                  class="w-full h-full object-cover"
                  referrerpolicy="no-referrer"
                  loading="lazy"
                  decoding="async"
                />
                <div v-else class="w-full h-full flex items-center justify-center text-xs font-bold text-gray-600">
                  {{ (rec.senderDisplayName || rec.sourcename || '?').charAt(0) }}
                </div>
              </div>

              <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                <div class="flex items-start gap-2">
                  <div class="min-w-0 flex-1">
                    <div
                      v-if="chatHistoryModalInfo?.isChatRoom && (rec.senderDisplayName || rec.sourcename)"
                      class="text-xs text-gray-500 leading-none truncate mb-1"
                    >
                      {{ rec.senderDisplayName || rec.sourcename }}
                    </div>
                  </div>
                  <div v-if="rec.fullTime || rec.sourcetime" class="text-xs text-gray-400 flex-shrink-0 leading-none">
                    {{ rec.fullTime || rec.sourcetime }}
                  </div>
                </div>

                  <div class="mt-1">
                  <!-- 合并转发聊天记录（Chat History） -->
                  <div
                    v-if="rec.renderType === 'chatHistory'"
                    class="wechat-chat-history-card wechat-special-card msg-radius cursor-pointer"
                    @click.stop="openNestedChatHistory(rec)"
                  >
                    <div class="wechat-chat-history-body">
                      <div class="wechat-chat-history-title">{{ rec.title || '聊天记录' }}</div>
                      <div class="wechat-chat-history-preview" v-if="getChatHistoryPreviewLines(rec).length">
                        <div
                          v-for="(line, lidx) in getChatHistoryPreviewLines(rec)"
                          :key="lidx"
                          class="wechat-chat-history-line"
                        >
                          {{ line }}
                        </div>
                      </div>
                    </div>
                    <div class="wechat-chat-history-bottom">
                      <span>聊天记录</span>
                    </div>
                  </div>

                  <!-- 链接卡片 -->
                  <div
                    v-else-if="rec.renderType === 'link'"
                    class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
                    @click.stop="openChatHistoryLinkWindow(rec)"
                    @contextmenu="openMediaContextMenu($event, rec, 'message')"
                  >
                    <div class="wechat-link-content">
                      <div class="wechat-link-title">{{ rec.title || rec.content || rec.url || '链接' }}</div>
                      <div v-if="rec.content || rec.preview" class="wechat-link-summary">
                        <div v-if="rec.content" class="wechat-link-desc">{{ rec.content }}</div>
                        <div v-if="rec.preview" class="wechat-link-thumb">
                          <img :src="rec.preview" :alt="rec.title || '链接预览'" class="wechat-link-thumb-img" referrerpolicy="no-referrer" loading="lazy" decoding="async" @error="onChatHistoryLinkPreviewError(rec)" />
                        </div>
                      </div>
                    </div>
                    <div class="wechat-link-from">
                      <div class="wechat-link-from-avatar" :style="rec._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                        <span v-if="(!rec.fromAvatar) || (!rec._fromAvatarImgOk)">{{ getChatHistoryLinkFromAvatarText(rec) || '\u200B' }}</span>
                        <img
                          v-if="rec.fromAvatar && !rec._fromAvatarImgError"
                          :src="rec.fromAvatar"
                          alt=""
                          class="wechat-link-from-avatar-img"
                          referrerpolicy="no-referrer"
                          loading="lazy"
                          decoding="async"
                          @load="onChatHistoryFromAvatarLoad(rec)"
                          @error="onChatHistoryFromAvatarError(rec)"
                        />
                      </div>
                      <div class="wechat-link-from-name">{{ getChatHistoryLinkFromText(rec) || '\u200B' }}</div>
                    </div>
                  </div>

                  <!-- 视频 -->
                  <div
                    v-else-if="rec.renderType === 'video'"
                    class="msg-radius overflow-hidden relative bg-black/5 inline-block"
                    @contextmenu="openMediaContextMenu($event, rec, 'video')"
                  >
                    <img
                      v-if="rec.videoThumbUrl && !rec._videoThumbError"
                      :src="rec.videoThumbUrl"
                      alt="视频"
                      class="block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover"
                      @error="onChatHistoryVideoThumbError(rec)"
                    />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[视频]' }}</div>

                    <button
                      v-if="rec.videoThumbUrl && rec.videoUrl"
                      type="button"
                      class="absolute inset-0 flex items-center justify-center"
                      @click.stop="openVideoPreview(rec.videoUrl, rec.videoThumbUrl)"
                    >
                      <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    </button>
                    <div class="absolute inset-0 flex items-center justify-center" v-else-if="rec.videoThumbUrl">
                      <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    </div>
                    <div
                      v-if="rec.videoDuration"
                      class="absolute bottom-2 right-2 text-xs text-white bg-black/55 px-1.5 py-0.5 rounded"
                    >
                      {{ formatChatHistoryVideoDuration(rec.videoDuration) }}
                    </div>
                  </div>

                  <!-- 图片 -->
                  <div
                    v-else-if="rec.renderType === 'image'"
                    class="msg-radius overflow-hidden cursor-pointer inline-block"
                    @click="rec.imageUrl && openImagePreview(rec.imageUrl)"
                    @contextmenu="openMediaContextMenu($event, rec, 'image')"
                  >
                    <img
                      v-if="rec.imageUrl"
                      :src="rec.imageUrl"
                      alt="图片"
                      class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity"
                    />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[图片]' }}</div>
                  </div>

                  <!-- 表情 -->
                  <div
                    v-else-if="rec.renderType === 'emoji'"
                    class="inline-block"
                    @contextmenu="openMediaContextMenu($event, rec, 'emoji')"
                  >
                    <img v-if="rec.emojiUrl" :src="rec.emojiUrl" alt="表情" class="w-24 h-24 object-contain" />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[表情]' }}</div>
                  </div>

                  <!-- 引用（回复） -->
                  <div v-else-if="rec.renderType === 'quote'" class="max-w-[420px]">
                    <div
                      class="px-2 text-xs text-neutral-700 rounded max-w-[404px] flex items-center bg-[#e1e1e1] cursor-pointer select-none"
                      @click="openChatHistoryQuote(rec)"
                      @contextmenu="openMediaContextMenu($event, rec.quoteMedia || rec, rec.quote?.kind || 'message')"
                    >
                      <div class="w-10 h-10 rounded overflow-hidden bg-neutral-300 flex-shrink-0 mr-2">
                        <img
                          v-if="rec.quote?.thumbUrl && !rec._quoteThumbError"
                          :src="rec.quote.thumbUrl"
                          alt="引用"
                          class="w-full h-full object-cover"
                          @error="onChatHistoryQuoteThumbError(rec)"
                        />
                        <div v-else class="w-full h-full flex items-center justify-center text-[10px] text-neutral-600">
                          {{ rec.quote?.kind === 'video' ? '视频' : (rec.quote?.kind === 'image' ? '图片' : '表情') }}
                        </div>
                      </div>
                      <div class="min-w-0 flex-1 py-2">
                        <div class="line-clamp-2">
                          {{ rec.quote?.label || (rec.quote?.kind === 'video' ? '[视频]' : (rec.quote?.kind === 'image' ? '[图片]' : '[表情]')) }}
                        </div>
                      </div>
                      <div v-if="rec.quote?.kind === 'video' && rec.quote?.duration" class="ml-2 flex-shrink-0 text-[11px] text-neutral-600">
                        {{ formatChatHistoryVideoDuration(rec.quote.duration) }}
                      </div>
                    </div>

                    <div
                      class="mt-1 text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                      @contextmenu="openMediaContextMenu($event, rec, 'message')"
                    >
                      <span v-for="(seg, sidx) in parseTextWithEmoji(rec.content)" :key="sidx">
                        <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                        <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                      </span>
                    </div>
                  </div>

                  <!-- 文本/其它 -->
                  <div
                    v-else
                    class="text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                    @contextmenu="openMediaContextMenu($event, rec, 'message')"
                  >
                    <span v-for="(seg, sidx) in parseTextWithEmoji(rec.content)" :key="sidx">
                      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                      <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
      </div>
    </div>

    <div
      v-if="contextMenu.visible"
      class="fixed z-[12000] bg-white border border-gray-200 rounded-md shadow-lg text-sm"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <button
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        @click="onCopyMessageTextClick"
      >
        复制文本
      </button>
      <button
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        @click="onCopyMessageJsonClick"
      >
        复制消息 JSON
      </button>
      <button
        v-if="contextMenu.message?.renderType === 'quote' && contextMenu.message?.quoteServerId"
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        @click="onLocateQuotedMessageClick"
      >
        定位引用消息
      </button>
      <button
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        :disabled="contextMenu.disabled"
        :class="contextMenu.disabled ? 'opacity-50 cursor-not-allowed' : ''"
        @click="onOpenFolderClick"
      >
        打开文件夹
      </button>

      <div class="border-t border-gray-200"></div>

      <button
        v-if="contextMenu.message?.id"
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        @click="onEditMessageClick"
      >
        {{ isLikelyTextMessage(contextMenu.message) ? '修改消息' : '编辑源码' }}
      </button>
      <button
        v-if="contextMenu.message?.id"
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        @click="onEditMessageFieldsClick"
      >
        字段编辑
      </button>
      <button
        v-if="contextMenu.editStatus?.modified"
        class="block w-full text-left px-3 py-2 hover:bg-gray-100 text-red-600"
        type="button"
        @click="onResetEditedMessageClick"
      >
        恢复原消息
      </button>
      <button
        v-if="contextMenu.message?.id"
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        @click="onRepairMessageSenderAsMeClick"
      >
        修复为我发送
      </button>
      <button
        v-if="contextMenu.message?.id"
        class="block w-full text-left px-3 py-2 hover:bg-gray-100 text-orange-600"
        type="button"
        @click="onFlipWechatMessageDirectionClick"
      >
        反转微信气泡位置
      </button>
      <div v-if="contextMenu.editStatusLoading" class="px-3 py-2 text-xs text-gray-400">检查修改状态…</div>
    </div>

    <!-- 修改消息弹窗 -->
    <div v-if="messageEditModal.open" class="fixed inset-0 z-[11000] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeMessageEditModal"></div>
      <div class="relative w-[860px] max-w-[95vw] bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">{{ messageEditModal.mode === 'content' ? '修改消息' : '编辑源码' }}</div>
          <button class="ml-auto text-gray-400 hover:text-gray-600" type="button" @click="closeMessageEditModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-3">
          <div v-if="messageEditModal.error" class="text-sm text-red-600 whitespace-pre-wrap">{{ messageEditModal.error }}</div>
          <div v-if="messageEditModal.loading" class="text-sm text-gray-500">加载中…</div>

          <textarea
            v-model="messageEditModal.draft"
            class="w-full min-h-[240px] rounded-md border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#03C160]/20"
            :disabled="messageEditModal.loading || messageEditModal.saving"
            :placeholder="messageEditModal.mode === 'content' ? '请输入新的消息内容' : '请输入新的 message_content（可输入 0x... 写入 BLOB）'"
          ></textarea>

          <details v-if="messageEditModal.rawRow" class="text-xs">
            <summary class="cursor-pointer select-none text-gray-700 hover:text-gray-900">查看源消息（raw）</summary>
            <div class="mt-2 rounded border border-gray-200 bg-gray-50 p-2 overflow-auto">
              <pre class="text-[11px] leading-snug whitespace-pre-wrap break-words">{{ prettyJson(messageEditModal.rawRow) }}</pre>
            </div>
          </details>
        </div>

        <div class="px-5 py-3 border-t border-gray-200 flex items-center justify-end gap-2">
          <button class="text-sm px-4 py-2 rounded border border-gray-200 hover:bg-gray-50" type="button" @click="closeMessageEditModal">取消</button>
          <button
            class="text-sm px-4 py-2 rounded bg-[#03C160] text-white hover:bg-[#02ad55]"
            type="button"
            :disabled="messageEditModal.loading || messageEditModal.saving"
            :class="messageEditModal.loading || messageEditModal.saving ? 'opacity-60 cursor-not-allowed' : ''"
            @click="saveMessageEditModal"
          >
            保存
          </button>
        </div>
      </div>
    </div>

    <!-- 字段编辑弹窗 -->
    <div v-if="messageFieldsModal.open" class="fixed inset-0 z-[11000] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeMessageFieldsModal"></div>
      <div class="relative w-[920px] max-w-[95vw] bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">字段编辑</div>
          <button class="ml-auto text-gray-400 hover:text-gray-600" type="button" @click="closeMessageFieldsModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-3">
          <div v-if="messageFieldsModal.error" class="text-sm text-red-600 whitespace-pre-wrap">{{ messageFieldsModal.error }}</div>
          <div v-if="messageFieldsModal.loading" class="text-sm text-gray-500">加载中…</div>

          <div class="flex items-center gap-3">
            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input v-model="messageFieldsModal.unsafe" type="checkbox" class="rounded border-gray-300" />
              <span>我已知风险（允许修改 local_id / WCDB_CT / BLOB 等）</span>
            </label>
            <div class="text-xs text-gray-500">修改时间/类型会自动同步 message_resource 关键字段</div>
          </div>

          <textarea
            v-model="messageFieldsModal.editsJson"
            class="w-full min-h-[320px] rounded-md border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#03C160]/20"
            :disabled="messageFieldsModal.loading || messageFieldsModal.saving"
            placeholder='{ "message_content": "...", "create_time": 123 }'
          ></textarea>

          <details v-if="messageFieldsModal.rawRow" class="text-xs">
            <summary class="cursor-pointer select-none text-gray-700 hover:text-gray-900">查看源消息（raw）</summary>
            <div class="mt-2 rounded border border-gray-200 bg-gray-50 p-2 overflow-auto">
              <pre class="text-[11px] leading-snug whitespace-pre-wrap break-words">{{ prettyJson(messageFieldsModal.rawRow) }}</pre>
            </div>
          </details>
        </div>

        <div class="px-5 py-3 border-t border-gray-200 flex items-center justify-end gap-2">
          <button class="text-sm px-4 py-2 rounded border border-gray-200 hover:bg-gray-50" type="button" @click="closeMessageFieldsModal">取消</button>
          <button
            class="text-sm px-4 py-2 rounded bg-[#03C160] text-white hover:bg-[#02ad55]"
            type="button"
            :disabled="messageFieldsModal.loading || messageFieldsModal.saving"
            :class="messageFieldsModal.loading || messageFieldsModal.saving ? 'opacity-60 cursor-not-allowed' : ''"
            @click="saveMessageFieldsModal"
          >
            保存
          </button>
        </div>
      </div>
    </div>

    <!-- 导出弹窗 -->
    <div v-if="exportModalOpen" class="fixed inset-0 z-[11000] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeExportModal"></div>
      <div class="relative w-[960px] max-w-[95vw] bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">导出聊天记录（离线 ZIP）</div>
          <button class="ml-auto text-gray-400 hover:text-gray-700" type="button" @click="closeExportModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-5">
          <div v-if="exportError" class="text-sm text-red-600 whitespace-pre-wrap">{{ exportError }}</div>
          <div v-if="privacyMode" class="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-md px-3 py-2">
            已开启隐私模式：导出将隐藏会话/用户名/内容，并且不会打包头像与媒体。
          </div>

          <div class="space-y-5">
            <div class="flex flex-wrap items-end gap-6">
              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">范围</div>
                <div class="flex flex-wrap gap-2 text-sm text-gray-700">
                  <label class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border cursor-pointer transition-colors" :class="exportScope === 'current' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="current" v-model="exportScope" class="hidden" />
                    <span>当前会话</span>
                  </label>
                  <label class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border cursor-pointer transition-colors" :class="exportScope === 'selected' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="selected" v-model="exportScope" class="hidden" />
                    <span>选择会话（批量）</span>
                  </label>
                </div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">格式</div>
                <div class="flex items-center gap-2 text-sm text-gray-700">
                  <label class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border cursor-pointer transition-colors" :class="exportFormat === 'json' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="json" v-model="exportFormat" class="hidden" />
                    <span>JSON</span>
                  </label>
                  <label class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border cursor-pointer transition-colors" :class="exportFormat === 'txt' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="txt" v-model="exportFormat" class="hidden" />
                    <span>TXT</span>
                  </label>
                  <label class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border cursor-pointer transition-colors" :class="exportFormat === 'html' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="html" v-model="exportFormat" class="hidden" />
                    <span>HTML</span>
                  </label>
                </div>
              </div>

              <div class="flex-1 min-w-[320px]">
                <div class="text-sm font-medium text-gray-800 mb-2">时间范围（可选）</div>
                <div class="flex items-center gap-2 flex-wrap">
                  <input
                    v-model="exportStartLocal"
                    type="datetime-local"
                    class="px-2.5 py-1.5 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                  <span class="text-gray-400">-</span>
                  <input
                    v-model="exportEndLocal"
                    type="datetime-local"
                    class="px-2.5 py-1.5 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                </div>
              </div>
            </div>

            <div v-if="exportFormat === 'html'" class="mt-3">
              <div class="text-sm font-medium text-gray-800 mb-2">HTML 选项</div>
              <div class="p-3 bg-gray-50 rounded-md border border-gray-200">
                <label class="flex items-start gap-2 text-sm text-gray-700">
                  <input type="checkbox" v-model="exportDownloadRemoteMedia" :disabled="privacyMode" />
                  <span>允许联网下载链接/引用缩略图（提高离线完整性）</span>
                </label>
                <div class="mt-1 text-xs text-gray-500">
                  仅 HTML 生效；会在导出时尝试下载远程缩略图并写入 ZIP（已做安全限制）。隐私模式下自动忽略。
                </div>

                <div class="mt-3 flex flex-wrap items-center gap-3">
                  <div class="text-sm text-gray-700">每页消息数</div>
                  <input
                    v-model.number="exportHtmlPageSize"
                    type="number"
                    min="0"
                    step="100"
                    class="w-32 px-2.5 py-1.5 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                  <div class="text-xs text-gray-500">推荐 1000；0=单文件（打开大聊天可能很卡）</div>
                </div>
              </div>
            </div>

            <div v-if="exportScope === 'selected'" class="mt-3">
              <div class="flex items-center gap-2 mb-2">
                <button
                  type="button"
                  class="text-xs px-2 py-1 rounded border border-gray-200"
                  :class="exportListTab === 'all' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white hover:bg-gray-50 text-gray-700'"
                  @click="exportListTab = 'all'"
                >
                  全部 {{ exportContactCounts.total }}
                </button>
                <button
                  type="button"
                  class="text-xs px-2 py-1 rounded border border-gray-200"
                  :class="exportListTab === 'groups' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white hover:bg-gray-50 text-gray-700'"
                  @click="exportListTab = 'groups'"
                >
                  群聊 {{ exportContactCounts.groups }}
                </button>
                <button
                  type="button"
                  class="text-xs px-2 py-1 rounded border border-gray-200"
                  :class="exportListTab === 'singles' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white hover:bg-gray-50 text-gray-700'"
                  @click="exportListTab = 'singles'"
                >
                  单聊 {{ exportContactCounts.singles }}
                </button>
                <div class="ml-auto text-xs text-gray-500">点击 tab 筛选</div>
              </div>
              <div class="flex items-center gap-2 mb-2">
                <input
                  v-model="exportSearchQuery"
                  type="text"
                  placeholder="搜索会话（名称/username）"
                  class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  :class="{ 'privacy-blur': privacyMode }"
                />
              </div>
              <div class="border border-gray-200 rounded-md max-h-56 overflow-y-auto">
                <div
                  v-for="c in exportFilteredContacts"
                  :key="c.username"
                  class="px-3 py-2 border-b border-gray-100 flex items-center gap-2 hover:bg-gray-50"
                >
                  <input type="checkbox" :value="c.username" v-model="exportSelectedUsernames" />
                  <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                    <img v-if="c.avatar" :src="c.avatar" :alt="c.name + '头像'" class="w-full h-full object-cover" referrerpolicy="no-referrer" @error="onAvatarError($event, c)" />
                    <div v-else class="w-full h-full flex items-center justify-center text-xs font-bold text-gray-600">
                      {{ (c.name || c.username || '?').charAt(0) }}
                    </div>
                  </div>
                  <div class="min-w-0" :class="{ 'privacy-blur': privacyMode }">
                    <div class="text-sm text-gray-800 truncate">
                      {{ c.name }}
                      <span class="text-xs text-gray-500">{{ c.isGroup ? '（群）' : '' }}</span>
                    </div>
                    <div class="text-xs text-gray-500 truncate">{{ c.username }}</div>
                  </div>
                </div>
                <div v-if="exportFilteredContacts.length === 0" class="px-3 py-3 text-sm text-gray-500">
                  无匹配会话
                </div>
              </div>
              <div class="mt-2 text-xs text-gray-500">
                已选 {{ exportSelectedUsernames.length }} 个会话
              </div>
            </div>

            <div>
              <div class="text-sm font-medium text-gray-800 mb-2">消息类型（导出内容）</div>
              <div class="mt-2 p-3 bg-gray-50 rounded-md border border-gray-200">
                <div class="flex items-center gap-2 mb-2">
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = exportMessageTypeOptions.map((x) => x.value)"
                  >
                    全选
                  </button>
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = ['voice']"
                  >
                    只语音
                  </button>
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = ['transfer']"
                  >
                    只转账
                  </button>
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = ['redPacket']"
                  >
                    只红包
                  </button>
                  <div class="ml-auto text-xs text-gray-500">已选 {{ exportMessageTypes.length }} 项</div>
                </div>
                <div class="grid grid-cols-3 md:grid-cols-4 gap-2 text-sm text-gray-700">
                  <label v-for="opt in exportMessageTypeOptions" :key="opt.value" class="flex items-center gap-2">
                    <input type="checkbox" :value="opt.value" v-model="exportMessageTypes" />
                    <span>{{ opt.label }}</span>
                  </label>
                </div>
              </div>
              <div class="mt-1 text-xs text-gray-500">
                仅导出已勾选的消息类型；勾选图片/表情/视频/语音/文件时，会导出对应多媒体文件。
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">文件名（可选）</div>
                <input
                  v-model="exportFileName"
                  type="text"
                  placeholder="例如：我的微信导出_2025-12-23.zip"
                  class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                />
                <div class="mt-1 text-xs text-gray-500">不填则自动生成</div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">导出目录</div>
                <div class="flex items-center gap-2">
                  <div class="px-3 py-2 rounded-md border border-gray-200 bg-gray-50 text-xs break-all min-h-[38px] min-w-0 flex-1">
                    {{ exportFolder || '未选择' }}
                  </div>
                  <button
                    type="button"
                    class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                    @click="chooseExportFolder"
                  >
                    选择文件夹
                  </button>
                  <button
                    v-if="exportFolder"
                    type="button"
                    class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                    @click="exportFolder = ''; exportFolderHandle = null; exportSaveMsg = ''"
                  >
                    清空
                  </button>
                </div>
                <div class="mt-1 text-xs text-gray-500">桌面端与支持 File System Access API 的浏览器均可选择目录。</div>
              </div>
            </div>
          </div>

          <div v-if="exportJob" class="border border-gray-200 rounded-md bg-gray-50 p-4">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-gray-900">任务：{{ exportJob.exportId }}</div>
              <div class="text-xs text-gray-600">状态：{{ exportJob.status }}</div>
            </div>
            <div class="mt-2 text-xs text-gray-700 space-y-2">
              <div class="flex items-center justify-between">
                <div>会话：{{ exportJob.progress?.conversationsDone || 0 }}/{{ exportJob.progress?.conversationsTotal || 0 }}</div>
                <div class="text-gray-600">{{ exportOverallPercent }}%</div>
              </div>
              <div class="h-2 rounded-full bg-white border border-gray-200 overflow-hidden">
                <div
                  class="h-full bg-[#03C160] transition-all duration-300"
                  :style="{ width: exportOverallPercent + '%' }"
                ></div>
              </div>

              <div v-if="exportJob.status === 'running' && exportJob.progress?.currentConversationUsername" class="space-y-1">
                <div class="flex items-center justify-between gap-2">
                  <div class="truncate">
                    当前：{{ exportJob.progress?.currentConversationName || exportJob.progress?.currentConversationUsername }}
                    （{{ exportJob.progress?.currentConversationMessagesExported || 0 }}/{{ exportJob.progress?.currentConversationMessagesTotal || 0 }}）
                  </div>
                  <div class="text-gray-600">
                    <span v-if="exportCurrentPercent != null">{{ exportCurrentPercent }}%</span>
                    <span v-else>…</span>
                  </div>
                </div>
                <div class="h-2 rounded-full bg-white border border-gray-200 overflow-hidden">
                  <div
                    v-if="exportCurrentPercent != null"
                    class="h-full bg-sky-500 transition-all duration-300"
                    :style="{ width: exportCurrentPercent + '%' }"
                  ></div>
                  <div v-else class="h-full bg-sky-500/60 animate-pulse" style="width: 30%"></div>
                </div>
              </div>

              <div>消息：{{ exportJob.progress?.messagesExported || 0 }}；媒体：{{ exportJob.progress?.mediaCopied || 0 }}；缺失：{{ exportJob.progress?.mediaMissing || 0 }}</div>
            </div>

            <div class="mt-3 flex items-center gap-2">
              <button
                v-if="exportJob.status === 'done' && hasWebExportFolder"
                class="text-sm px-3 py-2 rounded-md bg-[#03C160] text-white hover:bg-[#02a650] disabled:opacity-60"
                type="button"
                :disabled="exportSaveBusy"
                @click="saveExportToSelectedFolder"
              >
                {{ exportSaveBusy ? '保存中...' : '保存到已选目录' }}
              </button>
              <a
                v-if="exportJob.status === 'done' && !hasWebExportFolder"
                class="text-sm px-3 py-2 rounded-md bg-[#03C160] text-white hover:bg-[#02a650]"
                :href="getExportDownloadUrl(exportJob.exportId)"
                target="_blank"
              >
                下载 ZIP
              </a>
              <button
                v-if="exportJob.status === 'running'"
                class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                type="button"
                @click="cancelCurrentExport"
              >
                取消任务
              </button>
            </div>
            <div v-if="exportSaveMsg" class="mt-2 text-xs text-green-600 whitespace-pre-wrap">{{ exportSaveMsg }}</div>

            <div v-if="exportJob.status === 'error'" class="mt-2 text-sm text-red-600 whitespace-pre-wrap">
              {{ exportJob.error || '导出失败' }}
            </div>
          </div>
        </div>

        <div class="px-5 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
          <button class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50" type="button" @click="closeExportModal">
            关闭
          </button>
          <button
            class="text-sm px-3 py-2 rounded-md bg-[#03C160] text-white hover:bg-[#02a650] disabled:opacity-60"
            type="button"
            @click="startChatExport"
            :disabled="isExportCreating"
          >
            {{ isExportCreating ? '创建中...' : '开始导出' }}
          </button>
        </div>
      </div>
    </div>
  </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick, defineComponent, h, toRaw } from 'vue'
import { storeToRefs } from 'pinia'

definePageMeta({
  key: 'chat'
})

import { useApi } from '~/composables/useApi'
import { parseTextWithEmoji } from '~/utils/wechat-emojis'
import { DESKTOP_SETTING_AUTO_REALTIME_KEY, readLocalBoolSetting } from '~/utils/desktop-settings'
import { heatColor } from '~/utils/wrapped/heatmap'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { useChatRealtimeStore } from '~/stores/chatRealtime'
import { usePrivacyStore } from '~/stores/privacy'
import wechatPcLogoUrl from '~/assets/images/wechat/WeChat-Icon-Logo.wine.svg'
import miniProgramIconUrl from '~/assets/images/wechat/mini-program.svg'
import zipIconUrl from '~/assets/images/wechat/zip.png'
import pdfIconUrl from '~/assets/images/wechat/pdf.png'
import wordIconUrl from '~/assets/images/wechat/word.png'
import excelIconUrl from '~/assets/images/wechat/excel.png'

// 根据文件名获取对应的图标URL
const getFileIconUrl = (fileName) => {
  if (!fileName) return zipIconUrl
  const ext = String(fileName).split('.').pop()?.toLowerCase() || ''
  switch (ext) {
    case 'pdf':
      return pdfIconUrl
    case 'doc':
    case 'docx':
      return wordIconUrl
    case 'xls':
    case 'xlsx':
    case 'csv':
      return excelIconUrl
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
    default:
      return zipIconUrl
  }
}

// 设置页面标题
useHead({
  title: '聊天记录查看器 - 微信数据分析助手'
})

const route = useRoute()

const routeUsername = computed(() => {
  const raw = route.params.username
  return (Array.isArray(raw) ? raw[0] : raw) || ''
})

const buildChatPath = (username) => {
  return username ? `/chat/${encodeURIComponent(username)}` : '/chat'
}

// 响应式数据
const selectedContact = ref(null)
const contactProfileCardOpen = ref(false)
const contactProfileCardMessageId = ref('')
const contactProfileLoading = ref(false)
const contactProfileError = ref('')
const contactProfileData = ref(null)
let contactProfileHoverHideTimer = null

// 隐私模式
const privacyStore = usePrivacyStore()
privacyStore.init()
const { privacyMode } = storeToRefs(privacyStore)

// 会话列表（中间栏）宽度（按物理像素 px 配置）：默认 295px，支持拖动调整并持久化
const SESSION_LIST_WIDTH_KEY = 'ui.chat.session_list_width_physical'
const SESSION_LIST_WIDTH_KEY_LEGACY = 'ui.chat.session_list_width'
const SESSION_LIST_WIDTH_DEFAULT = 295
const SESSION_LIST_WIDTH_MIN = 220
const SESSION_LIST_WIDTH_MAX = 520

const sessionListWidth = ref(SESSION_LIST_WIDTH_DEFAULT)
const sessionListResizing = ref(false)

let sessionListResizeStartX = 0
let sessionListResizeStartWidth = SESSION_LIST_WIDTH_DEFAULT
let sessionListResizeStartDpr = 1
let sessionListResizePrevCursor = ''
let sessionListResizePrevUserSelect = ''

const clampSessionListWidth = (n) => {
  const v = Number.isFinite(n) ? n : SESSION_LIST_WIDTH_DEFAULT
  return Math.min(SESSION_LIST_WIDTH_MAX, Math.max(SESSION_LIST_WIDTH_MIN, Math.round(v)))
}

const loadSessionListWidth = () => {
  if (!process.client) return
  try {
    const raw = localStorage.getItem(SESSION_LIST_WIDTH_KEY)
    const v = parseInt(String(raw || ''), 10)
    if (!Number.isNaN(v)) {
      sessionListWidth.value = clampSessionListWidth(v)
      return
    }

    // Legacy: value was stored as CSS px. Convert to physical px using current dpr.
    const legacy = localStorage.getItem(SESSION_LIST_WIDTH_KEY_LEGACY)
    const legacyV = parseInt(String(legacy || ''), 10)
    if (!Number.isNaN(legacyV)) {
      const dpr = window.devicePixelRatio || 1
      const converted = clampSessionListWidth(legacyV * dpr)
      sessionListWidth.value = converted
      try {
        localStorage.setItem(SESSION_LIST_WIDTH_KEY, String(converted))
        localStorage.removeItem(SESSION_LIST_WIDTH_KEY_LEGACY)
      } catch {}
    }
  } catch {}
}

const saveSessionListWidth = () => {
  if (!process.client) return
  try {
    localStorage.setItem(SESSION_LIST_WIDTH_KEY, String(clampSessionListWidth(sessionListWidth.value)))
  } catch {}
}

const setSessionListResizingActive = (active) => {
  if (!process.client) return
  try {
    const body = document.body
    if (!body) return
    if (active) {
      sessionListResizePrevCursor = body.style.cursor || ''
      sessionListResizePrevUserSelect = body.style.userSelect || ''
      body.style.cursor = 'col-resize'
      body.style.userSelect = 'none'
    } else {
      body.style.cursor = sessionListResizePrevCursor
      body.style.userSelect = sessionListResizePrevUserSelect
      sessionListResizePrevCursor = ''
      sessionListResizePrevUserSelect = ''
    }
  } catch {}
}

const onSessionListResizerPointerMove = (ev) => {
  if (!sessionListResizing.value) return
  const clientX = Number(ev?.clientX || 0)
  // `clientX` delta is in CSS px. We store width as physical px, so multiply by dpr.
  sessionListWidth.value = clampSessionListWidth(
    sessionListResizeStartWidth + (clientX - sessionListResizeStartX) * (sessionListResizeStartDpr || 1)
  )
}

const stopSessionListResize = () => {
  if (!process.client) return
  if (!sessionListResizing.value) return
  sessionListResizing.value = false
  setSessionListResizingActive(false)
  try {
    window.removeEventListener('pointermove', onSessionListResizerPointerMove)
  } catch {}
  saveSessionListWidth()
}

const onSessionListResizerPointerUp = () => {
  stopSessionListResize()
}

const onSessionListResizerPointerDown = (ev) => {
  if (!process.client) return
  try {
    ev?.preventDefault?.()
  } catch {}

  sessionListResizing.value = true
  sessionListResizeStartX = Number(ev?.clientX || 0)
  sessionListResizeStartWidth = Number(sessionListWidth.value || SESSION_LIST_WIDTH_DEFAULT)
  sessionListResizeStartDpr = window.devicePixelRatio || 1
  setSessionListResizingActive(true)

  try {
    window.addEventListener('pointermove', onSessionListResizerPointerMove)
    window.addEventListener('pointerup', onSessionListResizerPointerUp, { once: true })
  } catch {}
}

const resetSessionListWidth = () => {
  sessionListWidth.value = SESSION_LIST_WIDTH_DEFAULT
  saveSessionListWidth()
}

onMounted(() => {
  loadSessionListWidth()
})

// 桌面端设置（仅 Electron 环境可见）
const isDesktopEnv = ref(false)

const desktopAutoRealtime = ref(false)

// 尽量早读本地设置，避免首次加载联系人时拿不到 autoRealtime 选项
if (process.client) {
  desktopAutoRealtime.value = readLocalBoolSetting(DESKTOP_SETTING_AUTO_REALTIME_KEY, false)
}

// 联系人数据
const contacts = ref([])

const searchQuery = ref('')

const isLoadingContacts = ref(false)
const contactsError = ref('')
const chatAccounts = useChatAccountsStore()
const { selectedAccount, accounts: availableAccounts } = storeToRefs(chatAccounts)

// Realtime is a global switch (SidebarRail) and only affects the selected account.
const realtimeStore = useChatRealtimeStore()
const {
  enabled: realtimeEnabled,
  toggleSeq: realtimeToggleSeq,
  lastToggleAction: realtimeLastToggleAction,
  changeSeq: realtimeChangeSeq,
} = storeToRefs(realtimeStore)

let realtimeRefreshFuture = null
let realtimeRefreshQueued = false
let realtimeSessionsRefreshFuture = null
let realtimeSessionsRefreshQueued = false

const allMessages = ref({})

const messagesMeta = ref({})
const isLoadingMessages = ref(false)
const messagesError = ref('')

// 消息类型筛选（展示）
const messageTypeFilter = ref('all')
const messageTypeFilterOptions = [
  { value: 'all', label: '全部' },
  { value: 'text', label: '文本' },
  { value: 'image', label: '图片' },
  { value: 'emoji', label: '表情' },
  { value: 'video', label: '视频' },
  { value: 'voice', label: '语音' },
  { value: 'chatHistory', label: '聊天记录' },
  { value: 'transfer', label: '转账' },
  { value: 'redPacket', label: '红包' },
  { value: 'file', label: '文件' },
  { value: 'link', label: '链接' },
  { value: 'quote', label: '引用' },
  { value: 'system', label: '系统' },
  { value: 'voip', label: '通话' }
]

  // 消息搜索（会话内/全局）
  const messageSearchOpen = ref(false)
  const messageSearchQuery = ref('')
  const messageSearchScope = ref('global') // conversation | global
  const messageSearchRangeDays = ref('') // empty means no time filter
  const messageSearchSessionType = ref('') // empty means all (global only): group | single
  const messageSearchSender = ref('') // 发送者筛选
  const messageSearchSenderOptions = ref([])
  const messageSearchSenderLoading = ref(false)
  const messageSearchSenderError = ref('')
  const messageSearchSenderOptionsKey = ref('')
  const messageSearchSenderDropdownOpen = ref(false)
  const messageSearchSenderDropdownRef = ref(null)
  const messageSearchSenderDropdownInputRef = ref(null)
  const messageSearchSenderDropdownQuery = ref('')
  const messageSearchStartDate = ref('') // 自定义开始日期
  const messageSearchEndDate = ref('') // 自定义结束日期
  const messageSearchResults = ref([])
  const messageSearchLoading = ref(false)
  const messageSearchError = ref('')
  const messageSearchBackendStatus = ref('')
  const messageSearchIndexInfo = ref(null)
  const messageSearchHasMore = ref(false)
  const messageSearchOffset = ref(0)
  const messageSearchLimit = 50
  const messageSearchTotal = ref(0)
  const messageSearchSelectedIndex = ref(-1)
  const messageSearchInputRef = ref(null)
  let messageSearchDebounceTimer = null
  let messageSearchIndexPollTimer = null

// 搜索UI增强
const searchInputFocused = ref(false)
const showAdvancedFilters = ref(false)
const searchHistory = ref([])
const SEARCH_HISTORY_KEY = 'wechat_search_history'
const MAX_SEARCH_HISTORY = 10

// 加载搜索历史
const loadSearchHistory = () => {
  if (!process.client) return
  try {
    const saved = localStorage.getItem(SEARCH_HISTORY_KEY)
    if (saved) {
      searchHistory.value = JSON.parse(saved) || []
    }
  } catch (e) {
    searchHistory.value = []
  }
}

// 保存搜索历史
const saveSearchHistory = (query) => {
  if (!process.client) return
  if (!query || !query.trim()) return
  const q = query.trim()
  try {
    let history = [...searchHistory.value]
    // 移除重复项
    history = history.filter(item => item !== q)
    // 添加到开头
    history.unshift(q)
    // 限制数量
    if (history.length > MAX_SEARCH_HISTORY) {
      history = history.slice(0, MAX_SEARCH_HISTORY)
    }
    searchHistory.value = history
    localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(history))
  } catch (e) {
    // ignore
  }
}

// 清空搜索历史
const clearSearchHistory = () => {
  if (!process.client) return
  searchHistory.value = []
  try {
    localStorage.removeItem(SEARCH_HISTORY_KEY)
  } catch (e) {
    // ignore
  }
}

// 应用搜索历史
const applySearchHistory = async (query) => {
  messageSearchQuery.value = query
  await runMessageSearch({ reset: true })
}

const messageSearchIndexExists = computed(() => !!messageSearchIndexInfo.value?.exists)
const messageSearchIndexReady = computed(() => !!messageSearchIndexInfo.value?.ready)
const messageSearchIndexBuildStatus = computed(() => String(messageSearchIndexInfo.value?.build?.status || ''))
const messageSearchIndexBuildIndexed = computed(() => Number(messageSearchIndexInfo.value?.build?.indexedMessages || 0))
const messageSearchIndexMetaCount = computed(() => {
  const meta = messageSearchIndexInfo.value?.meta || {}
  const v = meta.message_count ?? meta.messageCount ?? meta.message_count ?? 0
  return Number(v || 0)
})

const messageSearchIndexProgressText = computed(() => {
  if (messageSearchIndexBuildStatus.value !== 'building') return ''
  const n = Number(messageSearchIndexBuildIndexed.value || 0)
  return n > 0 ? `已索引 ${n.toLocaleString()} 条` : '准备中...'
})

const messageSearchIndexText = computed(() => {
  if (!messageSearchIndexInfo.value) return ''
  if (!messageSearchIndexExists.value) return '索引未建立'
  if (messageSearchIndexBuildStatus.value === 'error') return '索引异常'
  if (!messageSearchIndexReady.value) return '索引未完成，需重建'
  const n = Number(messageSearchIndexMetaCount.value || 0)
  return n > 0 ? `索引已就绪（${n.toLocaleString()} 条）` : '索引已就绪'
})

const messageSearchIndexActionText = computed(() => {
  if (messageSearchIndexBuildStatus.value === 'building') return '建立中'
  return messageSearchIndexExists.value ? '重建索引' : '建立索引'
})

const messageSearchIndexActionDisabled = computed(() => {
  return messageSearchIndexBuildStatus.value === 'building' || messageSearchLoading.value
})

const formatCount = (n) => {
  const v = Number(n || 0)
  if (!Number.isFinite(v) || v <= 0) return ''
  try {
    return v.toLocaleString()
  } catch {
    return String(v)
  }
}

const messageSearchSenderDisabled = computed(() => {
  if (!selectedAccount.value) return true
  const scope = String(messageSearchScope.value || 'conversation')
  if (scope === 'conversation') {
    return !selectedContact.value?.username
  }
  const q = String(messageSearchQuery.value || '').trim()
  if (q.length >= 2) return false
  return !String(messageSearchSender.value || '').trim()
})

const messageSearchSelectedSenderInfo = computed(() => {
  const u = String(messageSearchSender.value || '').trim()
  if (!u) return null
  const list = Array.isArray(messageSearchSenderOptions.value) ? messageSearchSenderOptions.value : []
  const found = list.find((s) => String(s?.username || '').trim() === u)
  if (found) return found
  return { username: u, displayName: u, avatar: null, count: null }
})

const messageSearchSelectedSenderInitial = computed(() => {
  const info = messageSearchSelectedSenderInfo.value
  if (!info) return '人'
  const n = String(info.displayName || info.username || '').trim()
  return n ? n.charAt(0) : '人'
})

const messageSearchSenderLabel = computed(() => {
  const cur = String(messageSearchSender.value || '').trim()
  if (!cur) {
    if (String(messageSearchScope.value || '') === 'global' && String(messageSearchQuery.value || '').trim().length < 2) {
      return '发送者'
    }
    return '不限发送者'
  }
  const info = messageSearchSelectedSenderInfo.value
  return String(info?.displayName || info?.username || cur)
})

const filteredMessageSearchSenderOptions = computed(() => {
  const list = Array.isArray(messageSearchSenderOptions.value) ? messageSearchSenderOptions.value : []
  const q = String(messageSearchSenderDropdownQuery.value || '').trim().toLowerCase()
  if (!q) return list
  return list.filter((s) => {
    const u = String(s?.username || '').toLowerCase()
    const n = String(s?.displayName || '').toLowerCase()
    return u.includes(q) || n.includes(q)
  })
})

const closeMessageSearchSenderDropdown = () => {
  messageSearchSenderDropdownOpen.value = false
  messageSearchSenderDropdownQuery.value = ''
}

const getMessageSearchSenderFacetKey = () => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return ''
  const scope = String(messageSearchScope.value || 'conversation')
  const conv = scope === 'conversation' ? String(selectedContact.value?.username || '') : ''
  const q = String(messageSearchQuery.value || '').trim()
  const range = String(messageSearchRangeDays.value || '')
  const sd = String(messageSearchStartDate.value || '')
  const ed = String(messageSearchEndDate.value || '')
  const st = scope === 'global' ? String(messageSearchSessionType.value || '').trim() : ''
  return [acc, scope, conv, q, range, sd, ed, st].join('|')
}

const ensureMessageSearchSendersLoaded = async () => {
  const key = getMessageSearchSenderFacetKey()
  if (!key) return
  if (messageSearchSenderOptionsKey.value === key && !messageSearchSenderLoading.value) return
  const list = await fetchMessageSearchSenders()
  messageSearchSenderOptionsKey.value = key
  return list
}

const toggleMessageSearchSenderDropdown = async () => {
  if (messageSearchSenderDisabled.value) return
  if (messageSearchSenderDropdownOpen.value) {
    closeMessageSearchSenderDropdown()
    return
  }
  messageSearchSenderDropdownOpen.value = true
  await ensureMessageSearchSendersLoaded()
  await nextTick()
  try {
    messageSearchSenderDropdownInputRef.value?.focus?.()
  } catch {}
}

const selectMessageSearchSender = (username) => {
  messageSearchSender.value = String(username || '')
  closeMessageSearchSenderDropdown()
}

const fetchMessageSearchIndexStatus = async () => {
  if (!selectedAccount.value) return null
  const api = useApi()
  try {
    const resp = await api.getChatSearchIndexStatus({ account: selectedAccount.value })
    messageSearchIndexInfo.value = resp?.index || null
    return messageSearchIndexInfo.value
  } catch (e) {
    return null
  }
}

const fetchMessageSearchSenders = async () => {
  messageSearchSenderError.value = ''
  if (!selectedAccount.value) {
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    return []
  }

  const scope = String(messageSearchScope.value || 'conversation')
  const msgQ = String(messageSearchQuery.value || '').trim()

  const params = {
    account: selectedAccount.value,
    limit: 200
  }

  if (scope === 'conversation') {
    if (!selectedContact.value?.username) {
      messageSearchSenderOptions.value = []
      messageSearchSenderOptionsKey.value = ''
      return []
    }
    params.username = selectedContact.value.username
  } else {
    if (msgQ.length < 2) {
      messageSearchSenderOptions.value = []
      messageSearchSenderOptionsKey.value = ''
      return []
    }
  }

  if (msgQ) {
    params.message_q = msgQ
  }

  params.render_types = 'text'

  const range = String(messageSearchRangeDays.value || '')
  if (range === 'custom') {
    const start = dateToUnixSeconds(messageSearchStartDate.value, false)
    const end = dateToUnixSeconds(messageSearchEndDate.value, true)
    if (start != null) params.start_time = start
    if (end != null) params.end_time = end
    if (start != null && end != null && start > end) {
      messageSearchSenderError.value = '时间范围不合法：开始日期不能晚于结束日期'
      messageSearchSenderOptions.value = []
      messageSearchSenderOptionsKey.value = ''
      return []
    }
  } else {
    const days = Number(range || 0)
    if (days > 0 && Number.isFinite(days)) {
      const end = Math.floor(Date.now() / 1000)
      const start = Math.max(0, end - Math.floor(days * 24 * 3600))
      params.start_time = start
      params.end_time = end
    }
  }

  if (scope === 'global') {
    const st = String(messageSearchSessionType.value || '').trim()
    if (st) params.session_type = st
  }

  const api = useApi()
  messageSearchSenderLoading.value = true
  try {
    const resp = await api.listChatSearchSenders(params)
    const status = String(resp?.status || 'success')
    if (status !== 'success') {
      if (status !== 'index_building') {
        messageSearchSenderError.value = String(resp?.message || '加载发送者失败')
      }
      messageSearchSenderOptions.value = []
      messageSearchSenderOptionsKey.value = ''
      return []
    }
    const list = Array.isArray(resp?.senders) ? resp.senders : []
    messageSearchSenderOptions.value = list
    messageSearchSenderOptionsKey.value = getMessageSearchSenderFacetKey()
    const cur = String(messageSearchSender.value || '').trim()
    if (cur && !list.some((s) => String(s?.username || '').trim() === cur)) {
      messageSearchSender.value = ''
    }
    return list
  } catch (e) {
    messageSearchSenderError.value = e?.message || '加载发送者失败'
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    return []
  } finally {
    messageSearchSenderLoading.value = false
  }
}

const stopMessageSearchIndexPolling = () => {
  if (messageSearchIndexPollTimer) clearInterval(messageSearchIndexPollTimer)
  messageSearchIndexPollTimer = null
}

const ensureMessageSearchIndexPolling = () => {
  if (messageSearchIndexPollTimer) return
  messageSearchIndexPollTimer = setInterval(async () => {
    if (!messageSearchOpen.value) {
      stopMessageSearchIndexPolling()
      return
    }

    const info = await fetchMessageSearchIndexStatus()
    const exists = !!info?.exists
    const ready = !!info?.ready
    const bs = String(info?.build?.status || '')
    const done = exists && ready && bs !== 'building'
    if (done) {
      stopMessageSearchIndexPolling()
      if (String(messageSearchScope.value || '') === 'conversation') {
        await fetchMessageSearchSenders()
      }
      if (String(messageSearchQuery.value || '').trim()) {
        await runMessageSearch({ reset: true })
      }
    }
  }, 1200)
}

const onMessageSearchIndexAction = async () => {
  if (!selectedAccount.value) return
  const api = useApi()
  const rebuild = messageSearchIndexExists.value
  try {
    const resp = await api.buildChatSearchIndex({ account: selectedAccount.value, rebuild })
    messageSearchIndexInfo.value = resp?.index || null
    messageSearchBackendStatus.value = 'index_building'
    ensureMessageSearchIndexPolling()
  } catch (e) {
    messageSearchError.value = e?.message || '建立索引失败'
  }
}

// 关键词高亮函数
const highlightKeyword = (text, keyword) => {
  if (!text || !keyword) return escapeHtml(text || '')
  const escaped = escapeHtml(text)
  const kw = keyword.trim()
  if (!kw) return escaped
  try {
    // 转义正则特殊字符
    const escapedKw = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escapedKw})`, 'gi')
    return escaped.replace(regex, '<mark class="search-highlight">$1</mark>')
  } catch (e) {
    return escaped
  }
}

// HTML转义
const escapeHtml = (str) => {
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const getMessageSearchHitAvatarUrl = (hit) => {
  if (!hit) return ''
  const scope = String(messageSearchScope.value || '')
  const url =
    scope === 'global'
      ? (hit.conversationAvatar || hit.senderAvatar || '')
      : (hit.senderAvatar || hit.conversationAvatar || '')
  return String(url || '').trim()
}

const getMessageSearchHitAvatarAlt = (hit) => {
  if (!hit) return '头像'
  const scope = String(messageSearchScope.value || '')
  if (scope === 'global') {
    const name = String(hit.conversationName || hit.username || '').trim()
    return name ? `${name} 头像` : '头像'
  }
  let name = String(hit.senderDisplayName || '').trim()
  if (!name) {
    name = hit.isSent ? '我' : String(hit.senderUsername || '').trim()
  }
  return name ? `${name} 头像` : '头像'
}

const getMessageSearchHitAvatarInitial = (hit) => {
  if (!hit) return '?'
  const scope = String(messageSearchScope.value || '')
  let text = ''
  if (scope === 'global') {
    text = String(hit.conversationName || hit.username || '').trim()
  } else {
    text = String(hit.senderDisplayName || '').trim()
    if (!text) {
      text = hit.isSent ? '我' : String(hit.senderUsername || '').trim()
    }
  }
  return (text.charAt(0) || '?').toString()
}

// 搜索定位上下文（避免破坏正常分页）
const searchContext = ref({
  active: false,
  kind: 'search', // search | date | first
  label: '',
  username: '',
  anchorId: '',
  anchorIndex: -1,
  hasMoreBefore: false,
  hasMoreAfter: false,
  loadingBefore: false,
  loadingAfter: false,
  savedMessages: null,
  savedMeta: null
})
const highlightMessageId = ref('')
let highlightMessageTimer = null

const searchContextBannerText = computed(() => {
  if (!searchContext.value?.active) return ''
  const kind = String(searchContext.value.kind || 'search')
  if (kind === 'date') {
    const label = String(searchContext.value.label || '').trim()
    return label ? `已定位到 ${label}（上下文模式）` : '已定位到指定日期（上下文模式）'
  }
  if (kind === 'first') {
    return '已定位到会话顶部（上下文模式）'
  }
  return '已定位到搜索结果（上下文模式）'
})

// 回到最新按钮
const showJumpToBottom = ref(false)

// 时间侧边栏（按日期定位）
const timeSidebarOpen = ref(false)
const timeSidebarYear = ref(null)
const timeSidebarMonth = ref(null) // 1-12
const timeSidebarCounts = ref({}) // { 'YYYY-MM-DD': count }
const timeSidebarMax = ref(0)
const timeSidebarTotal = ref(0)
const timeSidebarLoading = ref(false)
const timeSidebarError = ref('')
const timeSidebarSelectedDate = ref('') // YYYY-MM-DD (current/selected day)
// Simple in-memory cache per (account|username|YYYY-MM)
const timeSidebarCache = ref({})
const timeSidebarWeekdays = ['一', '二', '三', '四', '五', '六', '日']

const timeSidebarMonthLabel = computed(() => {
  const y = Number(timeSidebarYear.value || 0)
  const m = Number(timeSidebarMonth.value || 0)
  if (!y || !m) return ''
  return `${y}年${m}月`
})

const timeSidebarYearOptions = computed(() => {
  // WeChat history normally starts after 2011, but keep a broader range for safety.
  const nowY = new Date().getFullYear()
  const minY = 2000
  const maxY = Math.max(nowY, Number(timeSidebarYear.value || 0) || nowY)
  const years = []
  for (let y = maxY; y >= minY; y--) years.push(y)
  return years
})

const timeSidebarActiveDays = computed(() => {
  const counts = timeSidebarCounts.value || {}
  const keys = Object.keys(counts)
  return keys.length
})

const _pad2 = (n) => String(n).padStart(2, '0')

const _dateStrFromEpochSeconds = (ts) => {
  const t = Number(ts || 0)
  if (!t) return ''
  try {
    const d = new Date(t * 1000)
    return `${d.getFullYear()}-${_pad2(d.getMonth() + 1)}-${_pad2(d.getDate())}`
  } catch {
    return ''
  }
}

// Calendar heatmap color: reuse Wrapped heat palette, but bucket to Wrapped-like legend levels
// so ">=1 message" is always visibly tinted (instead of being almost white when max is huge).
const _calendarHeatColor = (count, maxV) => {
  const v = Math.max(0, Number(count || 0))
  const m = Math.max(0, Number(maxV || 0))
  if (!(v > 0)) return ''
  if (!(m > 0)) return heatColor(1, 1)
  const levels = 6
  const ratio = Math.max(0, Math.min(1, v / m))
  const level = Math.min(levels, Math.max(1, Math.ceil(ratio * levels)))
  const valueForLevel = Math.max(1, Math.round(level * (m / levels)))
  return heatColor(valueForLevel, m)
}

const timeSidebarCalendarCells = computed(() => {
  const y = Number(timeSidebarYear.value || 0)
  const m = Number(timeSidebarMonth.value || 0) // 1-12
  if (!y || !m) return []

  const daysInMonth = new Date(y, m, 0).getDate()
  const firstDow = new Date(y, m - 1, 1).getDay() // 0=Sun..6=Sat
  const offset = (firstDow + 6) % 7 // Monday=0

  const maxV = Math.max(0, Number(timeSidebarMax.value || 0))
  const counts = timeSidebarCounts.value || {}
  const selected = String(timeSidebarSelectedDate.value || '').trim()

  const out = []
  for (let i = 0; i < 42; i++) {
    const dayNum = i - offset + 1
    const inMonth = dayNum >= 1 && dayNum <= daysInMonth
    if (!inMonth) {
      out.push({
        key: `e:${y}-${m}:${i}`,
        day: '',
        dateStr: '',
        count: 0,
        disabled: true,
        className: 'calendar-day-outside',
        style: null,
        title: ''
      })
      continue
    }

    const dateStr = `${y}-${_pad2(m)}-${_pad2(dayNum)}`
    const count = Math.max(0, Number(counts[dateStr] || 0))
    const disabled = count <= 0

    const style = !disabled
      ? { backgroundColor: _calendarHeatColor(count, Math.max(maxV, count)) }
      : null

    const className = [
      disabled ? 'calendar-day-empty' : '',
      (selected && dateStr === selected) ? 'calendar-day-selected' : ''
    ].filter(Boolean).join(' ')

    out.push({
      key: dateStr,
      day: String(dayNum),
      dateStr,
      count,
      disabled,
      // NOTE: heatmap bg color is applied via inline style (reusing Wrapped heatmap palette).
      // Dynamic class names like `calendar-day-l${level}` may be purged by Tailwind and lead to no bg color.
      className,
      style,
      title: `${dateStr}：${count} 条`
    })
  }
  return out
})

// 导出（离线 zip）
const exportModalOpen = ref(false)
const isExportCreating = ref(false)
const exportError = ref('')

// current: 当前会话（映射为 selected + 单个 username）
const exportScope = ref('current') // current | selected | all | groups | singles
const exportFormat = ref('json') // json | txt | html
const exportDownloadRemoteMedia = ref(true)
const exportHtmlPageSize = ref(1000) // <=0 means single-file HTML (may be slow for huge chats)
const exportMessageTypeOptions = [
  { value: 'text', label: '文本' },
  { value: 'image', label: '图片' },
  { value: 'emoji', label: '表情' },
  { value: 'video', label: '视频' },
  { value: 'voice', label: '语音' },
  { value: 'chatHistory', label: '聊天记录' },
  { value: 'transfer', label: '转账' },
  { value: 'redPacket', label: '红包' },
  { value: 'file', label: '文件' },
  { value: 'link', label: '链接' },
  { value: 'quote', label: '引用' },
  { value: 'system', label: '系统' },
  { value: 'voip', label: '通话' }
]
const exportMessageTypes = ref(exportMessageTypeOptions.map((x) => x.value))

const exportStartLocal = ref('') // datetime-local
const exportEndLocal = ref('') // datetime-local
const exportFileName = ref('')
const exportFolder = ref('')
const exportFolderHandle = ref(null)
const exportSaveBusy = ref(false)
const exportSaveMsg = ref('')
const exportAutoSavedFor = ref('')

const exportSearchQuery = ref('')
const exportListTab = ref('all') // all | groups | singles
const exportSelectedUsernames = ref([])

const exportJob = ref(null)
let exportPollTimer = null
let exportEventSource = null

const _clamp01 = (n) => Math.min(1, Math.max(0, n))
const _asNumber = (v) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

const exportOverallPercent = computed(() => {
  const job = exportJob.value
  const p = job?.progress || {}
  const total = _asNumber(p.conversationsTotal)
  const done = _asNumber(p.conversationsDone)
  if (total <= 0) return 0

  const currentTotal = _asNumber(p.currentConversationMessagesTotal)
  const currentDone = _asNumber(p.currentConversationMessagesExported)
  const fracCurrent = currentTotal > 0 ? _clamp01(currentDone / currentTotal) : 0
  const overall = _clamp01((done + (job?.status === 'running' ? fracCurrent : 0)) / total)
  return Math.round(overall * 100)
})

const exportCurrentPercent = computed(() => {
  const p = exportJob.value?.progress || {}
  const total = _asNumber(p.currentConversationMessagesTotal)
  const done = _asNumber(p.currentConversationMessagesExported)
  if (total <= 0) return null
  return Math.round(_clamp01(done / total) * 100)
})

const exportFilteredContacts = computed(() => {
  const q = String(exportSearchQuery.value || '').trim().toLowerCase()
  let list = Array.isArray(contacts.value) ? contacts.value : []

  const tab = String(exportListTab.value || 'all')
  if (tab === 'groups') list = list.filter((c) => !!c?.isGroup)
  if (tab === 'singles') list = list.filter((c) => !c?.isGroup)

  if (!q) return list
  return list.filter((c) => {
    const name = String(c?.name || '').toLowerCase()
    const username = String(c?.username || '').toLowerCase()
    return name.includes(q) || username.includes(q)
  })
})

const contactProfileResolvedName = computed(() => {
  const profile = contactProfileData.value || {}
  const displayName = String(profile?.displayName || '').trim()
  if (displayName) return displayName
  const contactName = String(selectedContact.value?.name || '').trim()
  if (contactName) return contactName
  return String(profile?.username || selectedContact.value?.username || '').trim()
})

const contactProfileResolvedUsername = computed(() => {
  const profile = contactProfileData.value || {}
  return String(profile?.username || selectedContact.value?.username || '').trim()
})

const contactProfileResolvedNickname = computed(() => {
  return String(contactProfileData.value?.nickname || '').trim()
})

const contactProfileResolvedAlias = computed(() => {
  return String(contactProfileData.value?.alias || '').trim()
})

const contactProfileResolvedGender = computed(() => {
  const value = contactProfileData.value?.gender
  if (value == null || value === '') return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  if (n === 1) return '男'
  if (n === 2) return '女'
  if (n === 0) return '未知'
  return String(n)
})

const contactProfileResolvedRegion = computed(() => {
  return String(contactProfileData.value?.region || '').trim()
})

const contactProfileResolvedRemark = computed(() => {
  return String(contactProfileData.value?.remark || '').trim()
})

const contactProfileResolvedSignature = computed(() => {
  return String(contactProfileData.value?.signature || '').trim()
})

const contactProfileResolvedSource = computed(() => {
  return String(contactProfileData.value?.source || '').trim()
})

const contactProfileResolvedSourceScene = computed(() => {
  const value = contactProfileData.value?.sourceScene
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
})

const contactProfileResolvedAvatar = computed(() => {
  const profileAvatar = String(contactProfileData.value?.avatar || '').trim()
  if (profileAvatar) return profileAvatar
  return String(selectedContact.value?.avatar || '').trim()
})

const isDesktopExportRuntime = () => {
  return !!(process.client && window?.wechatDesktop?.chooseDirectory)
}

const isWebDirectoryPickerSupported = () => {
  return !!(process.client && typeof window.showDirectoryPicker === 'function')
}

const hasWebExportFolder = computed(() => {
  return !!(isWebDirectoryPickerSupported() && exportFolderHandle.value)
})

const chooseExportFolder = async () => {
  exportError.value = ''
  exportSaveMsg.value = ''
  try {
    if (!process.client) {
      exportError.value = '当前环境不支持选择导出目录'
      return
    }

    if (isDesktopExportRuntime()) {
      const result = await window.wechatDesktop.chooseDirectory({ title: '选择导出目录' })
      if (result && !result.canceled && Array.isArray(result.filePaths) && result.filePaths.length > 0) {
        exportFolder.value = String(result.filePaths[0] || '').trim()
        exportFolderHandle.value = null
      }
      return
    }

    if (isWebDirectoryPickerSupported()) {
      const handle = await window.showDirectoryPicker()
      if (handle) {
        exportFolderHandle.value = handle
        exportFolder.value = `浏览器目录：${String(handle.name || '已选择')}`
      }
      return
    }

    exportError.value = '当前浏览器不支持目录选择，请使用桌面端或 Chromium 新版浏览器'
  } catch (e) {
    exportError.value = e?.message || '选择导出目录失败'
  }
}

const guessExportZipName = (job) => {
  const raw = String(job?.zipPath || '').trim()
  if (raw) {
    const name = raw.replace(/\\/g, '/').split('/').pop()
    if (name && name.toLowerCase().endsWith('.zip')) {
      return name
    }
  }
  const exportId = String(job?.exportId || '').trim() || 'export'
  return `wechat_chat_export_${exportId}.zip`
}

const saveExportToSelectedFolder = async (options = {}) => {
  const autoSave = !!options?.auto
  exportError.value = ''
  exportSaveMsg.value = ''
  if (!process.client || !isWebDirectoryPickerSupported()) {
    exportError.value = '当前环境不支持保存到浏览器目录'
    return
  }
  const handle = exportFolderHandle.value
  if (!handle || typeof handle.getFileHandle !== 'function') {
    exportError.value = '请先选择浏览器导出目录'
    return
  }

  const exportId = exportJob.value?.exportId
  if (!exportId || String(exportJob.value?.status || '') !== 'done') {
    exportError.value = '导出任务尚未完成'
    return
  }

  exportSaveBusy.value = true
  try {
    const resp = await fetch(getExportDownloadUrl(exportId))
    if (!resp.ok) {
      throw new Error(`下载导出文件失败（${resp.status}）`)
    }
    const blob = await resp.blob()
    const fileName = guessExportZipName(exportJob.value)
    const fileHandle = await handle.getFileHandle(fileName, { create: true })
    const writable = await fileHandle.createWritable()
    await writable.write(blob)
    await writable.close()
    exportAutoSavedFor.value = String(exportId)
    exportSaveMsg.value = autoSave
      ? `已自动保存到已选目录：${fileName}`
      : `已保存到已选目录：${fileName}`
  } catch (e) {
    exportError.value = e?.message || '保存到浏览器目录失败'
  } finally {
    exportSaveBusy.value = false
  }
}

const exportContactCounts = computed(() => {
  const list = Array.isArray(contacts.value) ? contacts.value : []
  const total = list.length
  const groups = list.filter((c) => !!c?.isGroup).length
  return { total, groups, singles: total - groups }
})

const toUnixSeconds = (datetimeLocal) => {
  const v = String(datetimeLocal || '').trim()
  if (!v) return null
  const d = new Date(v)
  const ms = d.getTime()
  if (Number.isNaN(ms)) return null
  return Math.floor(ms / 1000)
}

const dateToUnixSeconds = (dateStr, endOfDay = false) => {
  const v = String(dateStr || '').trim()
  if (!v) return null
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return null
  const y = Number(m[1])
  const mo = Number(m[2])
  const d = Number(m[3])
  if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null
  const dt = new Date(y, mo - 1, d, endOfDay ? 23 : 0, endOfDay ? 59 : 0, endOfDay ? 59 : 0)
  const ms = dt.getTime()
  if (Number.isNaN(ms)) return null
  return Math.floor(ms / 1000)
}

const stopExportPolling = () => {
  if (exportEventSource) {
    try {
      exportEventSource.close()
    } catch (e) {
      // ignore
    }
    exportEventSource = null
  }
  if (exportPollTimer) {
    clearInterval(exportPollTimer)
    exportPollTimer = null
  }
}

const startExportHttpPolling = (exportId) => {
  if (!exportId) return
  const api = useApi()
  exportPollTimer = setInterval(async () => {
    try {
      const resp = await api.getChatExport(exportId)
      exportJob.value = resp?.job || exportJob.value

      const st = String(exportJob.value?.status || '')
      if (st === 'done' || st === 'error' || st === 'cancelled') {
        stopExportPolling()
      }
    } catch (e) {
      // keep polling; transient errors are possible while exporting
    }
  }, 1200)
}

const startExportPolling = (exportId) => {
  stopExportPolling()
  if (!exportId) return

  if (process.client && typeof window !== 'undefined' && typeof EventSource !== 'undefined') {
    const apiBase = useApiBase()
    const url = `${apiBase}/chat/exports/${encodeURIComponent(String(exportId))}/events`
    try {
      exportEventSource = new EventSource(url)
      exportEventSource.onmessage = (ev) => {
        try {
          const next = JSON.parse(String(ev.data || '{}'))
          exportJob.value = next || exportJob.value
          const st = String(exportJob.value?.status || '')
          if (st === 'done' || st === 'error' || st === 'cancelled') {
            stopExportPolling()
          }
        } catch (e) {
          // ignore
        }
      }
      exportEventSource.onerror = () => {
        // fallback to HTTP polling
        try {
          exportEventSource?.close()
        } catch (e) {
          // ignore
        }
        exportEventSource = null
        if (!exportPollTimer) startExportHttpPolling(exportId)
      }
      return
    } catch (e) {
      exportEventSource = null
    }
  }

  startExportHttpPolling(exportId)
}

const openExportModal = () => {
  exportModalOpen.value = true
  exportError.value = ''
  exportSaveMsg.value = ''
  exportListTab.value = 'all'
  exportStartLocal.value = ''
  exportEndLocal.value = ''
  exportMessageTypes.value = exportMessageTypeOptions.map((x) => x.value)
  exportAutoSavedFor.value = ''

  if (selectedContact.value?.username) {
    exportScope.value = 'current'
  } else {
    exportScope.value = 'all'
  }
}

const closeExportModal = () => {
  exportModalOpen.value = false
  exportError.value = ''
}

const fetchContactProfile = async (options = {}) => {
  const username = String(options?.username || contactProfileData.value?.username || selectedContact.value?.username || '').trim()
  const displayNameFallback = String(options?.displayName || '').trim()
  const avatarFallback = String(options?.avatar || '').trim()
  const account = String(selectedAccount.value || '').trim()
  if (!username || !account) {
    contactProfileData.value = null
    return
  }

  contactProfileLoading.value = true
  contactProfileError.value = ''
  try {
    const api = useApi()
    const resp = await api.listChatContacts({
      account,
      include_friends: true,
      include_groups: true,
      include_officials: true,
    })
    const list = Array.isArray(resp?.contacts) ? resp.contacts : []
    const matched = list.find((item) => String(item?.username || '').trim() === username)
    if (matched) {
      const normalized = {
        ...matched,
        username,
      }
      if (!String(normalized.displayName || '').trim() && displayNameFallback) {
        normalized.displayName = displayNameFallback
      }
      if (!String(normalized.avatar || '').trim() && avatarFallback) {
        normalized.avatar = avatarFallback
      }
      contactProfileData.value = normalized
    } else {
      contactProfileData.value = {
        username,
        displayName: displayNameFallback || selectedContact.value?.name || username,
        avatar: avatarFallback || selectedContact.value?.avatar || '',
        nickname: '',
        alias: '',
        gender: null,
        region: '',
        remark: '',
        signature: '',
        source: '',
        sourceScene: null,
      }
    }
  } catch (e) {
    contactProfileData.value = {
      username,
      displayName: displayNameFallback || selectedContact.value?.name || username,
      avatar: avatarFallback || selectedContact.value?.avatar || '',
      nickname: '',
      alias: '',
      gender: null,
      region: '',
      remark: '',
      signature: '',
      source: '',
      sourceScene: null,
    }
    contactProfileError.value = e?.message || '加载联系人资料失败'
  } finally {
    contactProfileLoading.value = false
  }
}

const clearContactProfileHoverHideTimer = () => {
  if (contactProfileHoverHideTimer) {
    clearTimeout(contactProfileHoverHideTimer)
    contactProfileHoverHideTimer = null
  }
}

const closeContactProfileCard = () => {
  contactProfileCardOpen.value = false
  contactProfileCardMessageId.value = ''
}

const onMessageAvatarMouseEnter = async (message) => {
  const isSent = !!message?.isSent
  if (isSent) return
  const messageId = String(message?.id ?? '').trim()
  if (!messageId) return
  const username = String(message?.senderUsername || '').trim()
  if (!username || username === 'self') return

  const senderName = String(message?.senderDisplayName || message?.sender || '').trim()
  const senderAvatar = String(message?.avatar || '').trim()
  if (!contactProfileData.value || String(contactProfileData.value?.username || '').trim() !== username) {
    contactProfileData.value = {
      username,
      displayName: senderName || username,
      avatar: senderAvatar,
      nickname: '',
      alias: '',
      gender: null,
      region: '',
      remark: '',
      signature: '',
      source: '',
      sourceScene: null,
    }
  } else {
    if (!String(contactProfileData.value?.displayName || '').trim() && senderName) {
      contactProfileData.value.displayName = senderName
    }
    if (!String(contactProfileData.value?.avatar || '').trim() && senderAvatar) {
      contactProfileData.value.avatar = senderAvatar
    }
  }

  clearContactProfileHoverHideTimer()
  contactProfileCardMessageId.value = messageId
  contactProfileCardOpen.value = true
  await fetchContactProfile({ username, displayName: senderName, avatar: senderAvatar })
}

const onMessageAvatarMouseLeave = () => {
  clearContactProfileHoverHideTimer()
  contactProfileHoverHideTimer = setTimeout(() => {
    closeContactProfileCard()
  }, 120)
}

const onContactCardMouseEnter = () => {
  clearContactProfileHoverHideTimer()
}

watch(exportModalOpen, (open) => {
  if (!process.client) return
  if (!open) {
    stopExportPolling()
    return
  }

  const exportId = exportJob.value?.exportId
  const st = String(exportJob.value?.status || '')
  if (exportId && (st === 'queued' || st === 'running')) {
    startExportPolling(exportId)
  }
})

watch(
  () => selectedContact.value?.username,
  () => {
    clearContactProfileHoverHideTimer()
    closeContactProfileCard()
    contactProfileError.value = ''
    contactProfileData.value = null
  }
)

watch(
  () => selectedContact.value?.username,
  async () => {
    if (!timeSidebarOpen.value) return
    // When switching conversations with the time sidebar open, re-initialize month and refetch counts.
    const { year, month } = _pickTimeSidebarInitialYearMonth()
    timeSidebarYear.value = year
    timeSidebarMonth.value = month

     const list = messages.value || []
     const last = Array.isArray(list) && list.length ? list[list.length - 1] : null
     const ds = _dateStrFromEpochSeconds(Number(last?.createTime || 0))
     if (ds) {
       await _applyTimeSidebarSelectedDate(ds, { syncMonth: false })
     } else {
       timeSidebarSelectedDate.value = ''
     }

    await loadTimeSidebarMonth({ year, month, force: false })
  }
)

watch(
  () => selectedAccount.value,
  () => {
    clearContactProfileHoverHideTimer()
    closeContactProfileCard()
    contactProfileError.value = ''
    contactProfileData.value = null
  }
)

watch(
  () => ({
    exportId: String(exportJob.value?.exportId || ''),
    status: String(exportJob.value?.status || '')
  }),
  async ({ exportId, status }) => {
    if (!process.client || status !== 'done' || !exportId) return
    if (!hasWebExportFolder.value) return
    if (exportAutoSavedFor.value === exportId) return
    if (exportSaveBusy.value) return
    await saveExportToSelectedFolder({ auto: true })
  }
)

const getExportDownloadUrl = (exportId) => {
  const apiBase = useApiBase()
  return `${apiBase}/chat/exports/${encodeURIComponent(String(exportId || ''))}/download`
}

const startChatExport = async () => {
  exportError.value = ''
  exportSaveMsg.value = ''
  if (!selectedAccount.value) {
    exportError.value = '未选择账号'
    return
  }

  let scope = exportScope.value
  let usernames = []
  if (scope === 'current') {
    scope = 'selected'
    if (selectedContact.value?.username) {
      usernames = [selectedContact.value.username]
    }
  } else if (scope === 'selected') {
    usernames = Array.isArray(exportSelectedUsernames.value) ? exportSelectedUsernames.value.filter(Boolean) : []
  }

  if (scope === 'selected' && (!usernames || usernames.length === 0)) {
    exportError.value = '请选择至少一个会话'
    return
  }

  const hasDesktopFolder = isDesktopExportRuntime() && !!String(exportFolder.value || '').trim()
  const hasWebFolder = !isDesktopExportRuntime() && !!exportFolderHandle.value
  if (!hasDesktopFolder && !hasWebFolder) {
    exportError.value = '请先选择导出目录'
    return
  }

  const startTime = toUnixSeconds(exportStartLocal.value)
  const endTime = toUnixSeconds(exportEndLocal.value)
  if (startTime && endTime && startTime > endTime) {
    exportError.value = '时间范围不合法：开始时间不能晚于结束时间'
    return
  }

  const messageTypes = Array.isArray(exportMessageTypes.value) ? exportMessageTypes.value.filter(Boolean) : []
  if (messageTypes.length === 0) {
    exportError.value = '请至少勾选一个消息类型'
    return
  }

  const selectedTypeSet = new Set(messageTypes.map((t) => String(t || '').trim()))
  const mediaKindSet = new Set()
  if (selectedTypeSet.has('chatHistory')) {
    // 合并消息内部可能包含任意媒体类型；即使只勾选了 chatHistory，也需要打包媒体才可离线查看。
    mediaKindSet.add('image')
    mediaKindSet.add('emoji')
    mediaKindSet.add('video')
    mediaKindSet.add('video_thumb')
    mediaKindSet.add('voice')
    mediaKindSet.add('file')
  }
  if (selectedTypeSet.has('image')) mediaKindSet.add('image')
  if (selectedTypeSet.has('emoji')) mediaKindSet.add('emoji')
  if (selectedTypeSet.has('video')) {
    mediaKindSet.add('video')
    mediaKindSet.add('video_thumb')
  }
  if (selectedTypeSet.has('voice')) mediaKindSet.add('voice')
  if (selectedTypeSet.has('file')) mediaKindSet.add('file')

  const mediaKinds = Array.from(mediaKindSet)
  const includeMedia = !privacyMode.value && mediaKinds.length > 0

  isExportCreating.value = true
  exportAutoSavedFor.value = ''
  try {
    const api = useApi()
    const resp = await api.createChatExport({
      account: selectedAccount.value,
      scope,
      usernames,
      format: exportFormat.value,
      start_time: startTime,
      end_time: endTime,
      include_hidden: false,
      include_official: false,
      message_types: messageTypes,
      include_media: includeMedia,
      media_kinds: mediaKinds,
      download_remote_media: exportFormat.value === 'html' && !!exportDownloadRemoteMedia.value,
      html_page_size: Math.max(0, Math.floor(Number(exportHtmlPageSize.value || 1000))),
      output_dir: isDesktopExportRuntime() ? String(exportFolder.value || '').trim() : null,
      privacy_mode: !!privacyMode.value,
      file_name: exportFileName.value || null
    })

    exportJob.value = resp?.job || null
    const exportId = exportJob.value?.exportId
    if (exportId) startExportPolling(exportId)
  } catch (e) {
    exportError.value = e?.message || '创建导出任务失败'
  } finally {
    isExportCreating.value = false
  }
}

const cancelCurrentExport = async () => {
  const exportId = exportJob.value?.exportId
  if (!exportId) return

  try {
    const api = useApi()
    await api.cancelChatExport(exportId)
    const resp = await api.getChatExport(exportId)
    exportJob.value = resp?.job || exportJob.value
  } catch (e) {
    exportError.value = e?.message || '取消导出失败'
  }
}

const messagePageSize = 50

const messageContainerRef = ref(null)
const activeMessagesFor = ref('')

const updateJumpToBottomState = () => {
  const c = messageContainerRef.value
  if (!c) {
    showJumpToBottom.value = false
    return
  }
  const dist = c.scrollHeight - (c.scrollTop + c.clientHeight)
  showJumpToBottom.value = dist > 240
}

const scrollToBottom = () => {
  const c = messageContainerRef.value
  if (!c) return
  c.scrollTop = c.scrollHeight
  updateJumpToBottomState()
}

const flashMessage = (id) => {
  if (!id) return
  highlightMessageId.value = id
  if (highlightMessageTimer) clearTimeout(highlightMessageTimer)
  highlightMessageTimer = setTimeout(() => {
    highlightMessageId.value = ''
  }, 2500)
}

const scrollToMessageId = async (id) => {
  if (!process.client) return false
  if (!id) return false
  await nextTick()
  const c = messageContainerRef.value
  if (!c) return false
  const escape = (v) => {
    try {
      if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(v)
    } catch {}
    return String(v).replace(/\"/g, '\\\"')
  }
  const sel = `[data-msg-id="${escape(String(id))}"]`
  const el = c.querySelector(sel)
  if (!el) return false
  try {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  } catch {
    try {
      el.scrollIntoView()
    } catch {}
  }
  return true
}

// 图片预览状态
const previewImageUrl = ref(null)
const previewVideoUrl = ref(null)
const previewVideoPosterUrl = ref('')
const previewVideoError = ref('')

const openImagePreview = (url) => {
  if (!process.client) return
  previewImageUrl.value = url
  document.body.style.overflow = 'hidden'
}

const closeImagePreview = () => {
  if (!process.client) return
  previewImageUrl.value = null
  if (!previewVideoUrl.value) document.body.style.overflow = ''
}

const openVideoPreview = (url, poster) => {
  if (!process.client) return
  const u = String(url || '').trim()
  if (!u) return
  previewVideoError.value = ''
  previewVideoPosterUrl.value = String(poster || '').trim()
  previewVideoUrl.value = u
  document.body.style.overflow = 'hidden'
}

const closeVideoPreview = () => {
  if (!process.client) return
  previewVideoUrl.value = null
  previewVideoPosterUrl.value = ''
  previewVideoError.value = ''
  if (!previewImageUrl.value) document.body.style.overflow = ''
}

const onPreviewVideoError = () => {
  previewVideoError.value = '视频加载失败。'
}

const voiceRefs = ref({})
const currentPlayingVoice = ref(null)
const playingVoiceId = ref(null)
const highlightServerIdStr = ref('')
let highlightTimer = null

const setVoiceRef = (id, el) => {
  if (el) {
    voiceRefs.value[id] = el
    el.onended = () => {
      if (playingVoiceId.value === id) {
        playingVoiceId.value = null
        currentPlayingVoice.value = null
      }
    }
  }
}

const playVoice = (message) => {
  const audio = voiceRefs.value[message.id]
  if (!audio) return

  // 停止当前播放的语音
  if (currentPlayingVoice.value && currentPlayingVoice.value !== audio) {
    currentPlayingVoice.value.pause()
    currentPlayingVoice.value.currentTime = 0
    playingVoiceId.value = null
  }

  if (audio.paused) {
    audio.play()
    currentPlayingVoice.value = audio
    playingVoiceId.value = message.id
  } else {
    audio.pause()
    audio.currentTime = 0
    currentPlayingVoice.value = null
    playingVoiceId.value = null
  }
}

// 将毫秒转换为秒（voiceLength 存储的是毫秒）
const getVoiceDurationInSeconds = (durationMs) => {
  const ms = parseInt(durationMs) || 0
  return Math.round(ms / 1000)
}

// 根据语音时长计算宽度（基于秒数）
const getVoiceWidth = (durationMs) => {
  const seconds = getVoiceDurationInSeconds(durationMs)
  const minWidth = 80
  const maxWidth = 200
  const width = Math.min(maxWidth, minWidth + seconds * 4)
  return `${width}px`
}

const getQuoteVoiceId = (message) => {
  return `quote:${message?.id || ''}`
}

const isQuotedVoice = (message) => {
  const t = String(message?.quoteType || '').trim()
  if (t === '34') return true
  if (String(message?.quoteContent || '').trim() === '[语音]' && String(message?.quoteServerId || '').trim()) return true
  return false
}

const isQuotedImage = (message) => {
  const t = String(message?.quoteType || '').trim()
  if (t === '3') return true
  if (String(message?.quoteContent || '').trim() === '[图片]' && String(message?.quoteServerId || '').trim()) return true
  return false
}

const isQuotedLink = (message) => {
  const t = String(message?.quoteType || '').trim()
  if (t === '49') return true
  return /^\[链接\]\s*/.test(String(message?.quoteContent || '').trim())
}

const getQuotedLinkText = (message) => {
  const raw = String(message?.quoteContent || '').trim()
  if (!raw) return ''
  const stripped = raw.replace(/^\[链接\]\s*/u, '').trim()
  return stripped || raw
}

const onQuoteImageError = (message) => {
  try {
    if (message) message._quoteImageError = true
  } catch {}
}

const onQuoteThumbError = (message) => {
  try {
    if (message) message._quoteThumbError = true
  } catch {}
}

const playQuoteVoice = (message) => {
  playVoice({ id: getQuoteVoiceId(message) })
}

const contextMenu = ref({ visible: false, x: 0, y: 0, message: null, kind: '', disabled: false, editStatus: null, editStatusLoading: false })

const closeContextMenu = () => {
  contextMenu.value = { visible: false, x: 0, y: 0, message: null, kind: '', disabled: false, editStatus: null, editStatusLoading: false }
}

const openMediaContextMenu = (e, message, kind) => {
  if (!process.client) return
  e.preventDefault()
  e.stopPropagation()

  let actualKind = kind

  let disabled = true
  if (kind === 'voice') {
    disabled = !(message?.serverIdStr || message?.serverId)
  } else if (kind === 'file') {
    disabled = !message?.fileMd5
  } else if (kind === 'image') {
    disabled = !(message?.imageMd5 || message?.imageFileId)
  } else if (kind === 'emoji') {
    disabled = !message?.emojiMd5
  } else if (kind === 'video') {
    if (message?.videoMd5 || message?.videoFileId) {
      disabled = false
      actualKind = 'video'
    } else if (message?.videoThumbMd5 || message?.videoThumbFileId) {
      disabled = false
      actualKind = 'video_thumb'
    } else {
      disabled = true
    }
  }

  contextMenu.value = {
    visible: true,
    x: e.clientX,
    y: e.clientY,
    message,
    kind: actualKind,
    disabled,
    editStatus: null,
    editStatusLoading: false
  }

  try {
    const account = String(selectedAccount.value || '').trim()
    const username = String(selectedContact.value?.username || '').trim()
    const messageId = String(message?.id || '').trim()
    if (account && username && messageId) {
      contextMenu.value.editStatusLoading = true
      void loadContextMenuEditStatus({ account, username, message_id: messageId })
    }
  } catch {}
}

const loadContextMenuEditStatus = async (params) => {
  if (!process.client) return
  const account = String(params?.account || '').trim()
  const username = String(params?.username || '').trim()
  const messageId = String(params?.message_id || '').trim()
  if (!account || !username || !messageId) {
    contextMenu.value.editStatusLoading = false
    return
  }

  try {
    const api = useApi()
    const resp = await api.getChatEditStatus({ account, username, message_id: messageId })
    const cur = String(contextMenu.value?.message?.id || '').trim()
    if (contextMenu.value.visible && cur === messageId) {
      contextMenu.value.editStatus = resp || { modified: false }
    }
  } catch {
    const cur = String(contextMenu.value?.message?.id || '').trim()
    if (contextMenu.value.visible && cur === messageId) {
      contextMenu.value.editStatus = null
    }
  } finally {
    const cur = String(contextMenu.value?.message?.id || '').trim()
    if (contextMenu.value.visible && cur === messageId) {
      contextMenu.value.editStatusLoading = false
    }
  }
}

const prettyJson = (obj) => {
  try {
    return JSON.stringify(obj ?? null, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

const isLikelyTextMessage = (m) => {
  if (!m) return false
  const rt = String(m?.renderType || '').trim()
  if (rt && rt !== 'text') return false
  if (m?.imageUrl || m?.emojiUrl || m?.videoUrl || m?.voiceUrl) return false
  return true
}

const messageEditModal = ref({
  open: false,
  loading: false,
  saving: false,
  error: '',
  mode: 'content',
  sessionId: '',
  messageId: '',
  draft: '',
  rawRow: null,
})

const closeMessageEditModal = () => {
  messageEditModal.value = {
    open: false,
    loading: false,
    saving: false,
    error: '',
    mode: 'content',
    sessionId: '',
    messageId: '',
    draft: '',
    rawRow: null,
  }
}

const openMessageEditModal = async ({ message, mode }) => {
  if (!process.client) return
  const account = String(selectedAccount.value || '').trim()
  const sessionId = String(selectedContact.value?.username || '').trim()
  const messageId = String(message?.id || '').trim()
  if (!account || !sessionId || !messageId) return
  const resolvedMode = mode === 'raw' ? 'raw' : 'content'
  const initialDraft = resolvedMode === 'content'
    ? (typeof message?.content === 'string' ? message.content : String(message?.content ?? ''))
    : ''

  messageEditModal.value = {
    open: true,
    loading: true,
    saving: false,
    error: '',
    mode: resolvedMode,
    sessionId,
    messageId,
    draft: initialDraft,
    rawRow: null,
  }

  try {
    const api = useApi()
    const resp = await api.getChatMessageRaw({ account, username: sessionId, message_id: messageId })
    const row = resp?.row || null
    const rawContent = row?.message_content
    const rawDraft = typeof rawContent === 'string' ? rawContent : String(rawContent ?? '')
    const draft = resolvedMode === 'raw' ? rawDraft : messageEditModal.value.draft
    messageEditModal.value = { ...messageEditModal.value, loading: false, rawRow: row, draft }
  } catch (e) {
    messageEditModal.value = { ...messageEditModal.value, loading: false, error: e?.message || '加载失败' }
  }
}

const saveMessageEditModal = async () => {
  if (!process.client) return
  if (messageEditModal.value.saving || messageEditModal.value.loading) return

  const account = String(selectedAccount.value || '').trim()
  if (!account) return

  const sessionId = String(messageEditModal.value.sessionId || '').trim()
  const messageId = String(messageEditModal.value.messageId || '').trim()
  if (!sessionId || !messageId) return

  messageEditModal.value = { ...messageEditModal.value, saving: true, error: '' }
  try {
    const api = useApi()
    const resp = await api.editChatMessage({
      account,
      session_id: sessionId,
      message_id: messageId,
      edits: {
        message_content: String(messageEditModal.value.draft ?? ''),
      },
      unsafe: false,
    })

    if (resp?.updated_message) {
      try {
        const u = normalizeMessage(resp.updated_message)
        const uname = String(selectedContact.value?.username || '').trim()
        const list = allMessages.value[uname] || []
        const idx = list.findIndex((m) => String(m?.id || '') === String(u?.id || ''))
        if (idx >= 0) {
          const next = [...list]
          next[idx] = u
          allMessages.value = { ...allMessages.value, [uname]: next }
        } else {
          await refreshSelectedMessages()
        }
      } catch {
        await refreshSelectedMessages()
      }
    } else {
      await refreshSelectedMessages()
    }

    closeMessageEditModal()
  } catch (e) {
    messageEditModal.value = { ...messageEditModal.value, saving: false, error: e?.message || '保存失败' }
    return
  } finally {
    messageEditModal.value = { ...messageEditModal.value, saving: false }
  }
}

const messageFieldsModal = ref({
  open: false,
  loading: false,
  saving: false,
  error: '',
  sessionId: '',
  messageId: '',
  unsafe: false,
  editsJson: '',
  rawRow: null,
})

const closeMessageFieldsModal = () => {
  messageFieldsModal.value = {
    open: false,
    loading: false,
    saving: false,
    error: '',
    sessionId: '',
    messageId: '',
    unsafe: false,
    editsJson: '',
    rawRow: null,
  }
}

const openMessageFieldsModal = async (message) => {
  if (!process.client) return
  const account = String(selectedAccount.value || '').trim()
  const sessionId = String(selectedContact.value?.username || '').trim()
  const messageId = String(message?.id || '').trim()
  if (!account || !sessionId || !messageId) return

  messageFieldsModal.value = {
    open: true,
    loading: true,
    saving: false,
    error: '',
    sessionId,
    messageId,
    unsafe: false,
    editsJson: '',
    rawRow: null,
  }

  try {
    const api = useApi()
    const resp = await api.getChatMessageRaw({ account, username: sessionId, message_id: messageId })
    const row = resp?.row || null
    const seed = {}
    for (const k of ['message_content', 'local_type', 'create_time', 'server_id', 'origin_source', 'source']) {
      if (row && Object.prototype.hasOwnProperty.call(row, k)) seed[k] = row[k]
    }
    messageFieldsModal.value = {
      ...messageFieldsModal.value,
      loading: false,
      rawRow: row,
      editsJson: JSON.stringify(seed, null, 2),
    }
  } catch (e) {
    messageFieldsModal.value = { ...messageFieldsModal.value, loading: false, error: e?.message || '加载失败' }
  }
}

const saveMessageFieldsModal = async () => {
  if (!process.client) return
  if (messageFieldsModal.value.saving || messageFieldsModal.value.loading) return

  const account = String(selectedAccount.value || '').trim()
  if (!account) return

  const sessionId = String(messageFieldsModal.value.sessionId || '').trim()
  const messageId = String(messageFieldsModal.value.messageId || '').trim()
  if (!sessionId || !messageId) return

  let edits = null
  try {
    edits = JSON.parse(String(messageFieldsModal.value.editsJson || '').trim() || 'null')
  } catch {
    messageFieldsModal.value = { ...messageFieldsModal.value, error: 'JSON 格式错误' }
    return
  }
  if (!edits || typeof edits !== 'object' || Array.isArray(edits)) {
    messageFieldsModal.value = { ...messageFieldsModal.value, error: 'edits 必须是 JSON 对象' }
    return
  }
  if (!Object.keys(edits).length) {
    messageFieldsModal.value = { ...messageFieldsModal.value, error: 'edits 不能为空' }
    return
  }

  messageFieldsModal.value = { ...messageFieldsModal.value, saving: true, error: '' }
  try {
    const api = useApi()
    await api.editChatMessage({
      account,
      session_id: sessionId,
      message_id: messageId,
      edits,
      unsafe: !!messageFieldsModal.value.unsafe,
    })
    await refreshSelectedMessages()
    closeMessageFieldsModal()
  } catch (e) {
    messageFieldsModal.value = { ...messageFieldsModal.value, saving: false, error: e?.message || '保存失败' }
    return
  } finally {
    messageFieldsModal.value = { ...messageFieldsModal.value, saving: false }
  }
}

const onEditMessageClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return
  const mode = isLikelyTextMessage(m) ? 'content' : 'raw'
  closeContextMenu()
  await openMessageEditModal({ message: m, mode })
}

const onEditMessageFieldsClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return
  closeContextMenu()
  await openMessageFieldsModal(m)
}

const onResetEditedMessageClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return
  const account = String(selectedAccount.value || '').trim()
  const sessionId = String(selectedContact.value?.username || '').trim()
  const messageId = String(m?.id || '').trim()
  if (!account || !sessionId || !messageId) return

  const ok = window.confirm('确认恢复该条消息到首次快照吗？')
  if (!ok) return

  try {
    const api = useApi()
    await api.resetChatEditedMessage({ account, session_id: sessionId, message_id: messageId })
    closeContextMenu()
    await refreshSelectedMessages()
  } catch (e) {
    window.alert(e?.message || '恢复失败')
  } finally {
    closeContextMenu()
  }
}

const onRepairMessageSenderAsMeClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return
  const account = String(selectedAccount.value || '').trim()
  const sessionId = String(selectedContact.value?.username || '').trim()
  const messageId = String(m?.id || '').trim()
  if (!account || !sessionId || !messageId) return

  const ok = window.confirm('确认将该消息修复为“我发送”吗？这会修改 real_sender_id 字段。')
  if (!ok) return

  try {
    const api = useApi()
    await api.repairChatMessageSender({ account, session_id: sessionId, message_id: messageId, mode: 'me' })
    closeContextMenu()
    await refreshSelectedMessages()
  } catch (e) {
    window.alert(e?.message || '修复失败')
  } finally {
    closeContextMenu()
  }
}

const onFlipWechatMessageDirectionClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return
  const account = String(selectedAccount.value || '').trim()
  const sessionId = String(selectedContact.value?.username || '').trim()
  const messageId = String(m?.id || '').trim()
  if (!account || !sessionId || !messageId) return

  const ok = window.confirm(
    '确认反转该消息在微信客户端的左右气泡位置吗？\\n\\n这会修改 packed_info_data 字段（有风险）。\\n可通过“恢复原消息”撤销。'
  )
  if (!ok) return

  try {
    const api = useApi()
    await api.flipChatMessageDirection({ account, session_id: sessionId, message_id: messageId })
    closeContextMenu()
    await refreshSelectedMessages()
  } catch (e) {
    window.alert(e?.message || '反转失败')
  } finally {
    closeContextMenu()
  }
}

const copyTextToClipboard = async (text) => {
  if (!process.client) return false

  const t = String(text ?? '').trim()
  if (!t) return false

  try {
    await navigator.clipboard.writeText(t)
    return true
  } catch {}

  // Fallback for insecure contexts / old browsers.
  try {
    const el = document.createElement('textarea')
    el.value = t
    el.setAttribute('readonly', 'true')
    el.style.position = 'fixed'
    el.style.left = '-9999px'
    el.style.top = '-9999px'
    document.body.appendChild(el)
    el.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(el)
    if (ok) return true
  } catch {}

  try {
    window.prompt('复制内容：', t)
    return true
  } catch {
    return false
  }
}

const onCopyMessageTextClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return

  try {
    const text = String(m?.content || '').trim()
    if (!text) {
      window.alert('该消息没有可复制的文本')
      return
    }
    const ok = await copyTextToClipboard(text)
    if (!ok) window.alert('复制失败：无法写入剪贴板')
  } catch (e) {
    console.error('复制失败:', e)
    window.alert('复制失败')
  } finally {
    closeContextMenu()
  }
}

const onCopyMessageJsonClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  if (!m) return

  try {
    const raw = toRaw(m) || m
    const json = JSON.stringify(raw, (_k, v) => (typeof v === 'bigint' ? v.toString() : v), 2)
    const ok = await copyTextToClipboard(json)
    if (!ok) window.alert('复制失败：无法写入剪贴板')
  } catch (e) {
    console.error('复制失败:', e)
    window.alert('复制失败')
  } finally {
    closeContextMenu()
  }
}

const onOpenFolderClick = async () => {
  if (contextMenu.value.disabled) return
  const api = useApi()
  const m = contextMenu.value.message
  const kind = contextMenu.value.kind

  try {
    if (!selectedAccount.value) return
    if (!selectedContact.value?.username) return

    const params = {
      account: selectedAccount.value,
      username: selectedContact.value.username,
      kind
    }

    if (kind === 'voice') {
      params.server_id = m.serverIdStr || m.serverId
    } else if (kind === 'file') {
      params.md5 = m.fileMd5
    } else if (kind === 'image') {
      if (m.imageMd5) params.md5 = m.imageMd5
      else if (m.imageFileId) params.file_id = m.imageFileId
    } else if (kind === 'emoji') {
      params.md5 = m.emojiMd5
    } else if (kind === 'video') {
      params.md5 = m.videoMd5
      if (m.videoFileId) params.file_id = m.videoFileId
    } else if (kind === 'video_thumb') {
      params.md5 = m.videoThumbMd5
      if (m.videoThumbFileId) params.file_id = m.videoThumbFileId
    }

    await api.openChatMediaFolder(params)
  } finally {
    closeContextMenu()
  }
}

const locateMessageByServerId = async (serverIdStr) => {
  if (!process.client) return false
  const target = String(serverIdStr || '').trim()
  if (!target) return false
  if (!selectedContact.value) return false

  for (let i = 0; i < 30; i++) {
    const list = messages.value || []
    const found = list.find((m) => String(m?.serverIdStr || m?.serverId || '').trim() === target)
    if (found) {
      await nextTick()
      const container = messageContainerRef.value
      const el = container?.querySelector?.(`[data-server-id="${target}"]`)
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
      highlightServerIdStr.value = target
      if (highlightTimer) clearTimeout(highlightTimer)
      highlightTimer = setTimeout(() => {
        highlightServerIdStr.value = ''
        highlightTimer = null
      }, 1800)
      return true
    }

    if (!hasMoreMessages.value) break
    if (isLoadingMessages.value) {
      await new Promise((r) => setTimeout(r, 120))
      continue
    }
    await loadMoreMessages()
  }

  return false
}

const onLocateQuotedMessageClick = async () => {
  if (!process.client) return
  const m = contextMenu.value.message
  const target = String(m?.quoteServerId || '').trim()
  try {
    const ok = await locateMessageByServerId(target)
    if (!ok) window.alert('未找到被引用消息（可能未加载或不在本地）')
  } finally {
    closeContextMenu()
  }
}

const closeMessageSearch = () => {
  messageSearchOpen.value = false
  closeMessageSearchSenderDropdown()
  messageSearchError.value = ''
  messageSearchLoading.value = false
  messageSearchBackendStatus.value = ''
  stopMessageSearchIndexPolling()
  if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
  messageSearchDebounceTimer = null
}

let timeSidebarReqId = 0

const closeTimeSidebar = () => {
  timeSidebarOpen.value = false
  timeSidebarError.value = ''
}

const _timeSidebarCacheKey = ({ account, username, year, month }) => {
  const acc = String(account || '').trim()
  const u = String(username || '').trim()
  const y = Number(year || 0)
  const m = Number(month || 0)
  return `${acc}|${u}|${y}-${_pad2(m)}`
}

const _applyTimeSidebarMonthData = (data) => {
  const counts = (data && typeof data.counts === 'object' && !Array.isArray(data.counts)) ? data.counts : {}
  timeSidebarCounts.value = counts
  timeSidebarMax.value = Math.max(0, Number(data?.max || 0))
  timeSidebarTotal.value = Math.max(0, Number(data?.total || 0))
}

const loadTimeSidebarMonth = async ({ year, month, force } = {}) => {
  if (!selectedAccount.value) return
  if (!selectedContact.value?.username) return

  const y = Number(year || timeSidebarYear.value || 0)
  const m = Number(month || timeSidebarMonth.value || 0)
  if (!y || !m) return

  timeSidebarYear.value = y
  timeSidebarMonth.value = m

  const key = _timeSidebarCacheKey({
    account: selectedAccount.value,
    username: selectedContact.value.username,
    year: y,
    month: m
  })

  if (!force) {
    const cached = timeSidebarCache.value[key]
    if (cached) {
      timeSidebarError.value = ''
      _applyTimeSidebarMonthData(cached)
      return
    }
  }

  const reqId = ++timeSidebarReqId
  const api = useApi()
  timeSidebarLoading.value = true
  timeSidebarError.value = ''

  try {
    const resp = await api.getChatMessageDailyCounts({
      account: selectedAccount.value,
      username: selectedContact.value.username,
      year: y,
      month: m
    })
    if (reqId !== timeSidebarReqId) return
    if (String(resp?.status || '') !== 'success') {
      throw new Error(String(resp?.message || '加载日历失败'))
    }

    const data = {
      counts: resp?.counts || {},
      max: Number(resp?.max || 0),
      total: Number(resp?.total || 0)
    }

    _applyTimeSidebarMonthData(data)
    timeSidebarCache.value = { ...timeSidebarCache.value, [key]: data }
  } catch (e) {
    if (reqId !== timeSidebarReqId) return
    timeSidebarError.value = e?.message || '加载日历失败'
    _applyTimeSidebarMonthData({ counts: {}, max: 0, total: 0 })
  } finally {
    if (reqId === timeSidebarReqId) {
      timeSidebarLoading.value = false
    }
  }
}

const _pickTimeSidebarInitialYearMonth = () => {
  const list = messages.value || []
  const last = Array.isArray(list) && list.length ? list[list.length - 1] : null
  const ts = Number(last?.createTime || 0)
  const d = ts ? new Date(ts * 1000) : new Date()
  return { year: d.getFullYear(), month: d.getMonth() + 1 }
}

const _applyTimeSidebarSelectedDate = async (dateStr, { syncMonth } = {}) => {
  const ds = String(dateStr || '').trim()
  if (!ds) return
  if (timeSidebarSelectedDate.value !== ds) {
    timeSidebarSelectedDate.value = ds
  }
  if (!syncMonth || !timeSidebarOpen.value) return

  const parts = ds.split('-')
  const y = Number(parts?.[0] || 0)
  const m = Number(parts?.[1] || 0)
  if (!y || !m) return

  if (Number(timeSidebarYear.value || 0) !== y || Number(timeSidebarMonth.value || 0) !== m) {
    timeSidebarYear.value = y
    timeSidebarMonth.value = m
    // Fire and forget; request id guard + cache inside loadTimeSidebarMonth will handle racing.
    await loadTimeSidebarMonth({ year: y, month: m, force: false })
  }
}

const toggleTimeSidebar = async () => {
  timeSidebarOpen.value = !timeSidebarOpen.value
  if (!timeSidebarOpen.value) return
  closeMessageSearch()

  const { year, month } = _pickTimeSidebarInitialYearMonth()
  timeSidebarYear.value = year
  timeSidebarMonth.value = month

  // Default selected day: current viewport's latest loaded message day (usually "latest").
  const list = messages.value || []
  const last = Array.isArray(list) && list.length ? list[list.length - 1] : null
  const ds = _dateStrFromEpochSeconds(Number(last?.createTime || 0))
  if (ds) await _applyTimeSidebarSelectedDate(ds, { syncMonth: false })

  await loadTimeSidebarMonth({ year, month, force: false })
}

const prevTimeSidebarMonth = async () => {
  const y0 = Number(timeSidebarYear.value || 0)
  const m0 = Number(timeSidebarMonth.value || 0)
  if (!y0 || !m0) return
  const y = m0 === 1 ? (y0 - 1) : y0
  const m = m0 === 1 ? 12 : (m0 - 1)
  await loadTimeSidebarMonth({ year: y, month: m, force: false })
}

const nextTimeSidebarMonth = async () => {
  const y0 = Number(timeSidebarYear.value || 0)
  const m0 = Number(timeSidebarMonth.value || 0)
  if (!y0 || !m0) return
  const y = m0 === 12 ? (y0 + 1) : y0
  const m = m0 === 12 ? 1 : (m0 + 1)
  await loadTimeSidebarMonth({ year: y, month: m, force: false })
}

const onTimeSidebarYearMonthChange = async () => {
  if (!timeSidebarOpen.value) return
  const y = Number(timeSidebarYear.value || 0)
  const m = Number(timeSidebarMonth.value || 0)
  if (!y || !m) return
  await loadTimeSidebarMonth({ year: y, month: m, force: false })
}

const ensureMessageSearchScopeValid = () => {
  if (messageSearchScope.value === 'conversation' && !selectedContact.value) {
    messageSearchScope.value = 'global'
  }
}

const toggleMessageSearch = async () => {
  messageSearchOpen.value = !messageSearchOpen.value
  ensureMessageSearchScopeValid()
  if (!messageSearchOpen.value) return
  closeTimeSidebar()
  await nextTick()
  try {
    messageSearchInputRef.value?.focus?.()
  } catch {}
  await fetchMessageSearchIndexStatus()
  await fetchMessageSearchSenders()
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true })
  }
}

let messageSearchReqId = 0

const runMessageSearch = async ({ reset } = {}) => {
  if (!selectedAccount.value) return
  ensureMessageSearchScopeValid()

  const q = String(messageSearchQuery.value || '').trim()
  if (!q) {
    messageSearchResults.value = []
    messageSearchHasMore.value = false
    messageSearchError.value = ''
    messageSearchSelectedIndex.value = -1
    messageSearchBackendStatus.value = ''
    messageSearchTotal.value = 0
    stopMessageSearchIndexPolling()
    return
  }

  if (reset) {
    messageSearchOffset.value = 0
    messageSearchResults.value = []
    messageSearchSelectedIndex.value = -1
  }

  const reqId = ++messageSearchReqId
  const api = useApi()
  messageSearchLoading.value = true
  messageSearchError.value = ''
  messageSearchBackendStatus.value = ''

  const scope = String(messageSearchScope.value || 'conversation')

  const params = {
    account: selectedAccount.value,
    q,
    limit: messageSearchLimit,
    offset: messageSearchOffset.value
  }

  params.render_types = 'text'

  const range = String(messageSearchRangeDays.value || '')
  if (range === 'custom') {
    const start = dateToUnixSeconds(messageSearchStartDate.value, false)
    const end = dateToUnixSeconds(messageSearchEndDate.value, true)
    if (start != null) params.start_time = start
    if (end != null) params.end_time = end
    if (start != null && end != null && start > end) {
      messageSearchLoading.value = false
      messageSearchError.value = '时间范围不合法：开始日期不能晚于结束日期'
      return
    }
  } else {
    const days = Number(range || 0)
    if (days > 0 && Number.isFinite(days)) {
      const end = Math.floor(Date.now() / 1000)
      const start = Math.max(0, end - Math.floor(days * 24 * 3600))
      params.start_time = start
      params.end_time = end
    }
  }

  if (scope === 'global') {
    const st = String(messageSearchSessionType.value || '').trim()
    if (st) params.session_type = st
  }

  if (String(messageSearchSender.value || '').trim()) {
    params.sender = String(messageSearchSender.value || '').trim()
  }

  if (scope === 'conversation') {
    if (!selectedContact.value?.username) {
      messageSearchLoading.value = false
      messageSearchError.value = '请选择一个会话再搜索'
      return
    }
    params.username = selectedContact.value.username
  }

  try {
    const resp = await api.searchChatMessages(params)
    if (reqId !== messageSearchReqId) return

    if (resp?.index) {
      messageSearchIndexInfo.value = resp.index
    }

    const status = String(resp?.status || 'success')
    messageSearchBackendStatus.value = status

    if (status === 'index_building') {
      if (reset) {
        messageSearchResults.value = []
        messageSearchSelectedIndex.value = -1
      }
      messageSearchHasMore.value = false
      messageSearchTotal.value = 0
      ensureMessageSearchIndexPolling()
      return
    }

    if (status === 'index_error') {
      if (reset) {
        messageSearchResults.value = []
        messageSearchSelectedIndex.value = -1
      }
      messageSearchHasMore.value = false
      messageSearchTotal.value = 0
      messageSearchError.value = String(resp?.message || '索引错误')
      stopMessageSearchIndexPolling()
      return
    }

    if (status !== 'success') {
      if (reset) {
        messageSearchResults.value = []
        messageSearchSelectedIndex.value = -1
      }
      messageSearchHasMore.value = false
      messageSearchTotal.value = 0
      messageSearchError.value = String(resp?.message || '搜索失败')
      stopMessageSearchIndexPolling()
      return
    }

    const hits = Array.isArray(resp?.hits) ? resp.hits : []
    if (reset) {
      messageSearchResults.value = hits
    } else {
      messageSearchResults.value = [...messageSearchResults.value, ...hits]
    }
    messageSearchHasMore.value = !!resp?.hasMore
    messageSearchTotal.value = Number(resp?.total ?? resp?.totalInScan ?? 0)
    stopMessageSearchIndexPolling()

    if (messageSearchSelectedIndex.value < 0 && messageSearchResults.value.length) {
      messageSearchSelectedIndex.value = 0
    }

    // 保存搜索历史（仅在有结果时保存）
    if (!privacyMode.value && reset && hits.length > 0) {
      saveSearchHistory(q)
    }
  } catch (e) {
    if (reqId !== messageSearchReqId) return
    messageSearchError.value = e?.message || '搜索失败'
  } finally {
    if (reqId === messageSearchReqId) {
      messageSearchLoading.value = false
    }
  }
}

const loadMoreSearchResults = async () => {
  if (!messageSearchHasMore.value) return
  if (messageSearchLoading.value) return
  messageSearchOffset.value = Number(messageSearchOffset.value || 0) + messageSearchLimit
  await runMessageSearch({ reset: false })
}

const exitSearchContext = async () => {
  if (!searchContext.value?.active) return
  const u = String(searchContext.value.username || '').trim()
  const saved = searchContext.value.savedMessages
  const savedMeta = searchContext.value.savedMeta

  if (u && saved) {
    allMessages.value = { ...allMessages.value, [u]: saved }
  }
  if (u && savedMeta) {
    messagesMeta.value = { ...messagesMeta.value, [u]: savedMeta }
  }

  searchContext.value = {
    active: false,
    kind: 'search',
    label: '',
    username: '',
    anchorId: '',
    anchorIndex: -1,
    hasMoreBefore: false,
    hasMoreAfter: false,
    loadingBefore: false,
    loadingAfter: false,
    savedMessages: null,
    savedMeta: null
  }
  highlightMessageId.value = ''
  await nextTick()
  updateJumpToBottomState()
}

const locateSearchHit = async (hit) => {
  if (!process.client) return
  if (!selectedAccount.value) return
  if (!hit?.id) return

  const targetUsername = String(hit?.username || selectedContact.value?.username || '').trim()
  if (!targetUsername) return

  const targetContact = contacts.value.find((c) => c?.username === targetUsername)
  if (targetContact && selectedContact.value?.username !== targetUsername) {
    await selectContact(targetContact, { skipLoadMessages: true })
  }

  if (searchContext.value?.active && searchContext.value.username !== targetUsername) {
    await exitSearchContext()
  }

  if (!searchContext.value?.active) {
    searchContext.value = {
      active: true,
      kind: 'search',
      label: '',
      username: targetUsername,
      anchorId: String(hit.id),
      anchorIndex: -1,
      hasMoreBefore: true,
      hasMoreAfter: true,
      loadingBefore: false,
      loadingAfter: false,
      savedMessages: allMessages.value[targetUsername] || [],
      savedMeta: messagesMeta.value[targetUsername] || null
    }
  } else {
    searchContext.value.kind = 'search'
    searchContext.value.label = ''
    searchContext.value.anchorId = String(hit.id)
    searchContext.value.hasMoreBefore = true
    searchContext.value.hasMoreAfter = true
    searchContext.value.loadingBefore = false
    searchContext.value.loadingAfter = false
  }

  try {
    const api = useApi()
    const resp = await api.getChatMessagesAround({
      account: selectedAccount.value,
      username: targetUsername,
      anchor_id: String(hit.id),
      before: 35,
      after: 35
    })

    const raw = resp?.messages || []
    const mapped = raw.map(normalizeMessage)
    allMessages.value = { ...allMessages.value, [targetUsername]: mapped }
    messagesMeta.value = { ...messagesMeta.value, [targetUsername]: { total: mapped.length, hasMore: false } }

    searchContext.value.anchorId = String(resp?.anchorId || hit.id)
    searchContext.value.anchorIndex = Number(resp?.anchorIndex ?? -1)

    const ok = await scrollToMessageId(searchContext.value.anchorId)
    if (ok) flashMessage(searchContext.value.anchorId)
  } catch (e) {
    window.alert(e?.message || '定位失败')
  }
}

const locateByAnchorId = async ({ targetUsername, anchorId, kind, label } = {}) => {
  if (!process.client) return
  if (!selectedAccount.value) return
  const u = String(targetUsername || selectedContact.value?.username || '').trim()
  const anchor = String(anchorId || '').trim()
  if (!u || !anchor) return

  const targetContact = contacts.value.find((c) => c?.username === u)
  if (targetContact && selectedContact.value?.username !== u) {
    await selectContact(targetContact, { skipLoadMessages: true })
  }

  if (searchContext.value?.active && searchContext.value.username !== u) {
    await exitSearchContext()
  }

  const kindNorm = String(kind || 'search').trim() || 'search'
  const labelNorm = String(label || '').trim()
  const hasMoreBeforeInit = kindNorm === 'first' ? false : true

  if (!searchContext.value?.active) {
    searchContext.value = {
      active: true,
      kind: kindNorm,
      label: labelNorm,
      username: u,
      anchorId: anchor,
      anchorIndex: -1,
      hasMoreBefore: hasMoreBeforeInit,
      hasMoreAfter: true,
      loadingBefore: false,
      loadingAfter: false,
      savedMessages: allMessages.value[u] || [],
      savedMeta: messagesMeta.value[u] || null
    }
  } else {
    searchContext.value.kind = kindNorm
    searchContext.value.label = labelNorm
    searchContext.value.anchorId = anchor
    searchContext.value.username = u
    searchContext.value.hasMoreBefore = hasMoreBeforeInit
    searchContext.value.hasMoreAfter = true
    searchContext.value.loadingBefore = false
    searchContext.value.loadingAfter = false
  }

  try {
    const api = useApi()
    const resp = await api.getChatMessagesAround({
      account: selectedAccount.value,
      username: u,
      anchor_id: anchor,
      before: 35,
      after: 35
    })

    const raw = resp?.messages || []
    const mapped = raw.map(normalizeMessage)
    allMessages.value = { ...allMessages.value, [u]: mapped }
    messagesMeta.value = { ...messagesMeta.value, [u]: { total: mapped.length, hasMore: false } }

    searchContext.value.anchorId = String(resp?.anchorId || anchor)
    searchContext.value.anchorIndex = Number(resp?.anchorIndex ?? -1)

    const ok = await scrollToMessageId(searchContext.value.anchorId)
    if (ok) flashMessage(searchContext.value.anchorId)
  } catch (e) {
    window.alert(e?.message || '定位失败')
  }
}

const locateByDate = async (dateStr) => {
  if (!process.client) return
  if (!selectedAccount.value) return
  if (!selectedContact.value?.username) return

  const ds = String(dateStr || '').trim()
  if (!ds) return
  await _applyTimeSidebarSelectedDate(ds, { syncMonth: true })

  try {
    const api = useApi()
    const resp = await api.getChatMessageAnchor({
      account: selectedAccount.value,
      username: selectedContact.value.username,
      kind: 'day',
      date: ds
    })
    const status = String(resp?.status || '')
    const anchorId = String(resp?.anchorId || '').trim()
    if (status !== 'success' || !anchorId) {
      window.alert('当日暂无聊天记录')
      return
    }
    await locateByAnchorId({ targetUsername: selectedContact.value.username, anchorId, kind: 'date', label: ds })
  } catch (e) {
    window.alert(e?.message || '定位失败')
  }
}

const jumpToConversationFirst = async () => {
  if (!process.client) return
  if (!selectedAccount.value) return
  if (!selectedContact.value?.username) return

  try {
    const api = useApi()
    const resp = await api.getChatMessageAnchor({
      account: selectedAccount.value,
      username: selectedContact.value.username,
      kind: 'first'
    })
    const status = String(resp?.status || '')
    const anchorId = String(resp?.anchorId || '').trim()
    if (status !== 'success' || !anchorId) {
      window.alert('暂无聊天记录')
      return
    }
    const ds = _dateStrFromEpochSeconds(Number(resp?.createTime || 0))
    if (ds) await _applyTimeSidebarSelectedDate(ds, { syncMonth: true })
    await locateByAnchorId({ targetUsername: selectedContact.value.username, anchorId, kind: 'first', label: '' })
  } catch (e) {
    window.alert(e?.message || '定位失败')
  }
}

const onTimeSidebarDayClick = async (cell) => {
  if (!cell || cell.disabled) return
  const ds = String(cell.dateStr || '').trim()
  if (!ds) return
  await locateByDate(ds)
}

const _mergeContextMessages = (username, nextList) => {
  const u = String(username || '').trim()
  if (!u) return
  const list = Array.isArray(nextList) ? nextList : []
  allMessages.value = { ...allMessages.value, [u]: list }
  // Keep meta aligned; context mode doesn't rely on hasMore from meta.
  const prevMeta = messagesMeta.value[u] || null
  messagesMeta.value = {
    ...messagesMeta.value,
    [u]: {
      total: Math.max(Number(prevMeta?.total || 0), list.length),
      hasMore: false
    }
  }
}

const loadMoreSearchContextAfter = async () => {
  if (!process.client) return
  if (!selectedAccount.value) return
  if (!searchContext.value?.active) return
  if (searchContext.value.loadingAfter) return
  if (!searchContext.value.hasMoreAfter) return

  const u = String(searchContext.value.username || selectedContact.value?.username || '').trim()
  if (!u) return
  const existing = allMessages.value[u] || []
  const last = Array.isArray(existing) && existing.length ? existing[existing.length - 1] : null
  const anchorId = String(last?.id || '').trim()
  if (!anchorId) {
    searchContext.value.hasMoreAfter = false
    return
  }

  const ctxUsername = u
  searchContext.value.loadingAfter = true
  try {
    const api = useApi()
    const resp = await api.getChatMessagesAround({
      account: selectedAccount.value,
      username: ctxUsername,
      anchor_id: anchorId,
      before: 0,
      after: messagePageSize
    })

    if (!searchContext.value?.active || String(searchContext.value.username || '').trim() !== ctxUsername) return

    const raw = resp?.messages || []
    const mapped = raw.map(normalizeMessage)

    const existingIds = new Set(existing.map((m) => String(m?.id || '')))
    const appended = []
    for (const m of mapped) {
      const id = String(m?.id || '').trim()
      if (!id) continue
      if (existingIds.has(id)) continue
      existingIds.add(id)
      appended.push(m)
    }

    if (!appended.length) {
      searchContext.value.hasMoreAfter = false
      return
    }

    _mergeContextMessages(ctxUsername, [...existing, ...appended])
  } catch (e) {
    window.alert(e?.message || '加载更多消息失败')
  } finally {
    if (searchContext.value?.active && String(searchContext.value.username || '').trim() === ctxUsername) {
      searchContext.value.loadingAfter = false
    }
  }
}

const loadMoreSearchContextBefore = async () => {
  if (!process.client) return
  if (!selectedAccount.value) return
  if (!searchContext.value?.active) return
  if (searchContext.value.loadingBefore) return
  if (!searchContext.value.hasMoreBefore) return

  const u = String(searchContext.value.username || selectedContact.value?.username || '').trim()
  if (!u) return
  const existing = allMessages.value[u] || []
  const first = Array.isArray(existing) && existing.length ? existing[0] : null
  const anchorId = String(first?.id || '').trim()
  if (!anchorId) {
    searchContext.value.hasMoreBefore = false
    return
  }

  const c = messageContainerRef.value
  const beforeScrollHeight = c ? c.scrollHeight : 0
  const beforeScrollTop = c ? c.scrollTop : 0

  const ctxUsername = u
  searchContext.value.loadingBefore = true
  try {
    const api = useApi()
    const resp = await api.getChatMessagesAround({
      account: selectedAccount.value,
      username: ctxUsername,
      anchor_id: anchorId,
      before: messagePageSize,
      after: 0
    })

    if (!searchContext.value?.active || String(searchContext.value.username || '').trim() !== ctxUsername) return

    const raw = resp?.messages || []
    const mapped = raw.map(normalizeMessage)

    const existingIds = new Set(existing.map((m) => String(m?.id || '')))
    const prepended = []
    for (const m of mapped) {
      const id = String(m?.id || '').trim()
      if (!id) continue
      if (existingIds.has(id)) continue
      existingIds.add(id)
      prepended.push(m)
    }

    if (!prepended.length) {
      searchContext.value.hasMoreBefore = false
      return
    }

    _mergeContextMessages(ctxUsername, [...prepended, ...existing])

    await nextTick()
    const c2 = messageContainerRef.value
    if (c2) {
      const afterScrollHeight = c2.scrollHeight
      c2.scrollTop = beforeScrollTop + (afterScrollHeight - beforeScrollHeight)
    }
  } catch (e) {
    window.alert(e?.message || '加载更多消息失败')
  } finally {
    if (searchContext.value?.active && String(searchContext.value.username || '').trim() === ctxUsername) {
      searchContext.value.loadingBefore = false
    }
  }
}

const onSearchHitClick = async (hit, idx) => {
  messageSearchSelectedIndex.value = Number(idx || 0)
  await locateSearchHit(hit)
}

const onSearchNext = async () => {
  const q = String(messageSearchQuery.value || '').trim()
  if (!q) return

  if (!messageSearchResults.value.length && !messageSearchLoading.value) {
    await runMessageSearch({ reset: true })
  }
  if (!messageSearchResults.value.length) return

  const cur = Number(messageSearchSelectedIndex.value || 0)
  const next = (cur + 1) % messageSearchResults.value.length
  messageSearchSelectedIndex.value = next
  await locateSearchHit(messageSearchResults.value[next])
}

const onSearchPrev = async () => {
  const q = String(messageSearchQuery.value || '').trim()
  if (!q) return

  if (!messageSearchResults.value.length && !messageSearchLoading.value) {
    await runMessageSearch({ reset: true })
  }
  if (!messageSearchResults.value.length) return

  const cur = Number(messageSearchSelectedIndex.value || 0)
  const prev = (cur - 1 + messageSearchResults.value.length) % messageSearchResults.value.length
  messageSearchSelectedIndex.value = prev
  await locateSearchHit(messageSearchResults.value[prev])
}

// 消息样式展示数据
// 计算属性：当前选中联系人的消息
const messages = computed(() => {
  if (!selectedContact.value) return []
  return allMessages.value[selectedContact.value.username] || []
})

// 智能时间格式化：今天显示时间，昨天显示"昨天 HH:MM"，本周显示"星期X HH:MM"，本年显示"MM月DD日 HH:MM"，跨年显示"YYYY年MM月DD日 HH:MM"
const formatSmartTime = (ts) => {
  if (!ts) return ''
  try {
    const d = new Date(Number(ts) * 1000)
    const now = new Date()
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const timeStr = `${hh}:${mm}`

    // 计算日期差异（基于日历日期，而非24小时）
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const targetStart = new Date(d.getFullYear(), d.getMonth(), d.getDate())
    const dayDiff = Math.floor((todayStart - targetStart) / (1000 * 60 * 60 * 24))

    // 今天
    if (dayDiff === 0) {
      return timeStr
    }

    // 昨天
    if (dayDiff === 1) {
      return `昨天 ${timeStr}`
    }

    // 本周内（2-6天前，显示星期）
    if (dayDiff >= 2 && dayDiff <= 6) {
      const weekDays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
      return `${weekDays[d.getDay()]} ${timeStr}`
    }

    // 本年内
    const month = d.getMonth() + 1
    const day = d.getDate()
    if (d.getFullYear() === now.getFullYear()) {
      return `${month}月${day}日 ${timeStr}`
    }

    // 跨年
    return `${d.getFullYear()}年${month}月${day}日 ${timeStr}`
  } catch {
    return ''
  }
}

const formatTimeDivider = (ts) => {
  return formatSmartTime(ts)
}

const formatMessageTime = (ts) => {
  if (!ts) return ''
  try {
    const d = new Date(Number(ts) * 1000)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  } catch {
    return ''
  }
}

const formatMessageFullTime = (ts) => {
  if (!ts) return ''
  try {
    const d = new Date(Number(ts) * 1000)
    const yyyy = String(d.getFullYear())
    const MM = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`
  } catch {
    return ''
  }
}

const formatFileSize = (size) => {
  if (!size) return ''
  const s = String(size).trim()
  const num = parseFloat(s)
  if (isNaN(num)) return s
  if (num < 1024) return `${num} B`
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(2)} KB`
  return `${(num / 1024 / 1024).toFixed(2)} MB`
}

const formatTransferAmount = (amount) => {
  const s = String(amount ?? '').trim()
  if (!s) return ''
  return s.replace(/[￥¥]/g, '').trim()
}

const getRedPacketText = (message) => {
  const text = String(message?.content ?? '').trim()
  if (!text || text === '[Red Packet]') return '恭喜发财，大吉大利'
  return text
}

// 文件类型图标组件
const FileIconPdf = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', class: 'text-red-500' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' }),
      h('path', { d: 'M14 2v6h6', stroke: 'currentColor', 'stroke-width': '1.5' }),
      h('text', { x: '7', y: '17', 'font-size': '6', fill: 'currentColor', 'font-weight': 'bold' }, 'PDF')
    ])
  }
})

const FileIconZip = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', class: 'text-yellow-600' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' }),
      h('path', { d: 'M14 2v6h6', stroke: 'currentColor', 'stroke-width': '1.5' }),
      h('text', { x: '7', y: '17', 'font-size': '6', fill: 'currentColor', 'font-weight': 'bold' }, 'ZIP')
    ])
  }
})

const FileIconDoc = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', class: 'text-blue-600' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' }),
      h('path', { d: 'M14 2v6h6', stroke: 'currentColor', 'stroke-width': '1.5' }),
      h('text', { x: '5', y: '17', 'font-size': '5', fill: 'currentColor', 'font-weight': 'bold' }, 'DOC')
    ])
  }
})

const FileIconXls = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', class: 'text-green-600' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h6v6h6v10H6z', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' }),
      h('path', { d: 'M14 2v6h6', stroke: 'currentColor', 'stroke-width': '1.5' }),
      h('text', { x: '6', y: '17', 'font-size': '5', fill: 'currentColor', 'font-weight': 'bold' }, 'XLS')
    ])
  }
})

const FileIconPpt = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', class: 'text-orange-500' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' }),
      h('path', { d: 'M14 2v6h6', stroke: 'currentColor', 'stroke-width': '1.5' }),
      h('text', { x: '6', y: '17', 'font-size': '5', fill: 'currentColor', 'font-weight': 'bold' }, 'PPT')
    ])
  }
})

const FileIconTxt = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', class: 'text-gray-500' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z', stroke: 'currentColor', 'stroke-width': '1.5', fill: 'none' }),
      h('path', { d: 'M14 2v6h6', stroke: 'currentColor', 'stroke-width': '1.5' }),
      h('text', { x: '6', y: '17', 'font-size': '5', fill: 'currentColor', 'font-weight': 'bold' }, 'TXT')
    ])
  }
})

const FileIconDefault = defineComponent({
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'currentColor', class: 'text-gray-400' }, [
      h('path', { d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h6v6h6v10H6z' })
    ])
  }
})

// 根据文件名获取对应图标
const getFileIcon = (fileName) => {
  if (!fileName) return FileIconDefault
  const ext = String(fileName).split('.').pop()?.toLowerCase() || ''
  switch (ext) {
    case 'pdf': return FileIconPdf
    case 'zip': case 'rar': case '7z': case 'tar': case 'gz': return FileIconZip
    case 'doc': case 'docx': return FileIconDoc
    case 'xls': case 'xlsx': case 'csv': return FileIconXls
    case 'ppt': case 'pptx': return FileIconPpt
    case 'txt': case 'md': case 'log': return FileIconTxt
    default: return FileIconDefault
  }
}

// 文件点击事件 - 打开文件所在文件夹
const onFileClick = async (message) => {
  if (!message?.fileMd5) return
  const api = useApi()
  
  try {
    if (!selectedAccount.value) return
    if (!selectedContact.value?.username) return
    
    await api.openChatMediaFolder({
      account: selectedAccount.value,
      username: selectedContact.value.username,
      kind: 'file',
      md5: message.fileMd5
    })
  } catch (err) {
    console.error('打开文件夹失败:', err)
  }
}

const isTransferReturned = (message) => {
  const paySubType = String(message?.paySubType || '').trim()
  if (paySubType === '4' || paySubType === '9') return true
  const s = String(message?.transferStatus || '').trim()
  const c = String(message?.content || '').trim()
  const text = `${s} ${c}`.trim()
  if (!text) return false
  return text.includes('退回') || text.includes('退还')
}

const isTransferOverdue = (message) => {
  const paySubType = String(message?.paySubType || '').trim()
  if (paySubType === '10') return true
  const s = String(message?.transferStatus || '').trim()
  const c = String(message?.content || '').trim()
  const text = `${s} ${c}`.trim()
  if (!text) return false
  return text.includes('过期')
}

const getTransferTitle = (message) => {
  const paySubType = String(message.paySubType || '').trim()
  // paysubtype 含义：
  // 1=不明确 3=已收款/接收转账 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期
  // 优先使用后端计算的 transferStatus（如果有）
  if (message.transferStatus) return message.transferStatus
  switch (paySubType) {
    case '1': return '转账'
    case '3': return message.isSent ? '已被接收' : '已收款'
    case '8': return '发起转账'
    case '4': return '已退还'
    case '9': return '已被退还'
    case '10': return '已过期'
  }
  if (message.content && message.content !== '转账' && message.content !== '[转账]') {
    return message.content
  }
  return '转账'
}

// 反转消息位置（仅影响本工具显示，不建议通过写坏 BLOB 字段来实现）
const reverseMessageSides = ref(false)
const reverseSidesStorageKey = computed(() => {
  const a = String(selectedAccount.value || '').trim()
  const sid = String(selectedContact.value?.username || '').trim()
  if (a && sid) return `wechatda:reverse_message_sides:${a}:${sid}`
  return 'wechatda:reverse_message_sides:global'
})
const loadReverseMessageSides = () => {
  if (!process.client) return
  try {
    const v = localStorage.getItem(reverseSidesStorageKey.value)
    reverseMessageSides.value = v === '1'
  } catch {}
}
watch(reverseSidesStorageKey, () => loadReverseMessageSides(), { immediate: true })
watch(reverseMessageSides, (v) => {
  if (!process.client) return
  try {
    localStorage.setItem(reverseSidesStorageKey.value, v ? '1' : '0')
  } catch {}
})
const toggleReverseMessageSides = () => {
  reverseMessageSides.value = !reverseMessageSides.value
}

const renderMessages = computed(() => {
  const list = messages.value || []
  const reverseSides = !!reverseMessageSides.value
  let prevTs = 0
  return list.map((m) => {
    const ts = Number(m.createTime || 0)
    const show = !prevTs || (ts && Math.abs(ts - prevTs) >= 300)
    if (ts) prevTs = ts
    const origIsSent = !!m?.isSent
    return {
      ...m,
      _originalIsSent: origIsSent,
      isSent: reverseSides ? !origIsSent : origIsSent,
      showTimeDivider: !!show,
      timeDivider: formatTimeDivider(ts)
    }
  })
})

const filteredContacts = computed(() => {
  const q = (searchQuery.value || '').trim().toLowerCase()
  if (!q) return contacts.value
  return contacts.value.filter((c) => {
    const name = (c.name || '').toLowerCase()
    const username = (c.username || '').toLowerCase()
    return name.includes(q) || username.includes(q)
  })
})

const hasMoreMessages = computed(() => {
  if (!selectedContact.value) return false
  const key = selectedContact.value.username
  const meta = messagesMeta.value[key]
  if (!meta) return false
  if (meta.hasMore != null) return !!meta.hasMore
  const total = Number(meta.total || 0)
  const loaded = messages.value.length
  return total > loaded
})

// 已移除切换标签逻辑

// 选择联系人
const selectContact = async (contact, options = {}) => {
  if (!contact) return
  const nextUsername = contact?.username || ''
  if (searchContext.value?.active && searchContext.value.username && searchContext.value.username !== nextUsername) {
    await exitSearchContext()
  }
  selectedContact.value = contact
  const username = nextUsername
  if (!username) return
  if (options.syncRoute !== false && username) {
    const current = routeUsername.value || ''
    if (current !== username) {
      await navigateTo(buildChatPath(username), { replace: options.replaceRoute !== false })
    }
  }
  if (options.skipLoadMessages) return
  loadMessages({ username, reset: true })
}

const applyRouteSelection = async () => {
  if (!contacts.value || contacts.value.length === 0) {
    selectedContact.value = null
    return
  }

  const requested = routeUsername.value || ''
  if (requested) {
    const matched = contacts.value.find((c) => c.username === requested)
    if (matched) {
      if (selectedContact.value?.username !== matched.username) {
        await selectContact(matched, { syncRoute: false })
      }
      return
    }
  }

  await selectContact(contacts.value[0], { syncRoute: true, replaceRoute: true })
}

// 已移除样式选择逻辑

// 默认选择第一个联系人
onMounted(() => {
  if (process.client && typeof window !== 'undefined') {
    isDesktopEnv.value = !!window.wechatDesktop
  }
  loadContacts()
  loadSearchHistory()
})

const loadContacts = async () => {
  isLoadingContacts.value = true
  contactsError.value = ''

  try {
    await chatAccounts.ensureLoaded()

    if (!selectedAccount.value) {
      contacts.value = []
      selectedContact.value = null
      contactsError.value = chatAccounts.error || '未检测到已解密账号，请先解密数据库。'
      return
    }
    await loadSessionsForSelectedAccount()
  } catch (e) {
    contacts.value = []
    selectedContact.value = null
    contactsError.value = e?.message || '加载联系人失败'
  } finally {
    isLoadingContacts.value = false
  }

  await tryEnableRealtimeAuto()
}

const loadSessionsForSelectedAccount = async () => {
  const api = useApi()

  if (!selectedAccount.value) {
    contacts.value = []
    selectedContact.value = null
    return
  }

  const fetchSessions = async (source) => {
    const params = {
      account: selectedAccount.value,
      limit: 400,
      include_hidden: false,
      include_official: false
    }
    if (source) params.source = source
    return await api.listChatSessions(params)
  }

  let sessionsResp = null
  if (realtimeEnabled.value) {
    try {
      sessionsResp = await fetchSessions('realtime')
    } catch {
      sessionsResp = null
    }
  }
  if (!sessionsResp) {
    sessionsResp = await fetchSessions('')
  }

  const sessions = sessionsResp?.sessions || []
  contacts.value = sessions.map((s) => ({
    id: s.id,
    name: s.name || s.username || s.id,
    avatar: s.avatar || null,
    lastMessage: normalizeSessionPreview(s.lastMessage || ''),
    lastMessageTime: s.lastMessageTime || '',
    unreadCount: s.unreadCount || 0,
    isGroup: !!s.isGroup,
    isTop: !!s.isTop,
    username: s.username
  }))

  allMessages.value = {}
  messagesMeta.value = {}
  messagesError.value = ''
  selectedContact.value = null

  closeMessageSearch()
  closeTimeSidebar()
  timeSidebarYear.value = null
  timeSidebarMonth.value = null
  _applyTimeSidebarMonthData({ counts: {}, max: 0, total: 0 })
  timeSidebarError.value = ''
  timeSidebarSelectedDate.value = ''
  messageSearchResults.value = []
  messageSearchOffset.value = 0
  messageSearchHasMore.value = false
  messageSearchBackendStatus.value = ''
  messageSearchTotal.value = 0
  messageSearchIndexInfo.value = null
  messageSearchSelectedIndex.value = -1
  searchContext.value = {
    active: false,
    kind: 'search',
    label: '',
    username: '',
    anchorId: '',
    anchorIndex: -1,
    hasMoreBefore: false,
    hasMoreAfter: false,
    loadingBefore: false,
    loadingAfter: false,
    savedMessages: null,
    savedMeta: null
  }
  highlightMessageId.value = ''

  await applyRouteSelection()
}

const refreshSessionsForSelectedAccount = async ({ sourceOverride } = {}) => {
  if (!process.client || typeof window === 'undefined') return
  if (!selectedAccount.value) return
  if (isLoadingContacts.value) return

  const api = useApi()
  const prevSelected = selectedContact.value?.username || ''

  const desiredSource = (sourceOverride != null)
    ? String(sourceOverride || '').trim()
    : (realtimeEnabled.value ? 'realtime' : '')

  const params = {
    account: selectedAccount.value,
    limit: 400,
    include_hidden: false,
    include_official: false
  }

  let sessionsResp = null
  if (desiredSource) {
    try {
      sessionsResp = await api.listChatSessions({ ...params, source: desiredSource })
    } catch {
      sessionsResp = null
    }
  }
  if (!sessionsResp) {
    try {
      sessionsResp = await api.listChatSessions(params)
    } catch {
      return
    }
  }

  const sessions = sessionsResp?.sessions || []
  const nextContacts = sessions.map((s) => ({
    id: s.id,
    name: s.name || s.username || s.id,
    avatar: s.avatar || null,
    lastMessage: normalizeSessionPreview(s.lastMessage || ''),
    lastMessageTime: s.lastMessageTime || '',
    unreadCount: s.unreadCount || 0,
    isGroup: !!s.isGroup,
    isTop: !!s.isTop,
    username: s.username
  }))

  contacts.value = nextContacts

  if (prevSelected) {
    const matched = nextContacts.find((c) => c.username === prevSelected)
    if (matched) {
      selectedContact.value = matched
    }
  }
}

const queueRealtimeSessionsRefresh = () => {
  if (realtimeSessionsRefreshFuture) {
    realtimeSessionsRefreshQueued = true
    return
  }

  realtimeSessionsRefreshFuture = refreshSessionsForSelectedAccount({ sourceOverride: 'realtime' }).finally(() => {
    realtimeSessionsRefreshFuture = null
    if (realtimeSessionsRefreshQueued) {
      realtimeSessionsRefreshQueued = false
      queueRealtimeSessionsRefresh()
    }
  })
}

const onAccountChange = async () => {
  try {
    isLoadingContacts.value = true
    contactsError.value = ''
    await loadSessionsForSelectedAccount()
  } catch (e) {
    contactsError.value = e?.message || '加载联系人失败'
  } finally {
    isLoadingContacts.value = false
  }
}

const normalizeMessage = (msg) => {
  const isSent = !!msg.isSent
  const sender = isSent ? '我' : (msg.senderDisplayName || msg.senderUsername || selectedContact.value?.name || '')
  const fallbackAvatar = (!isSent && !selectedContact.value?.isGroup) ? (selectedContact.value?.avatar || null) : null

  const apiBase = useApiBase()
  const normalizeMaybeUrl = (u) => (typeof u === 'string' ? u.trim() : '')
  const isUsableMediaUrl = (u) => {
    const v = normalizeMaybeUrl(u)
    if (!v) return false
    return (
      /^https?:\/\//i.test(v)
      || /^blob:/i.test(v)
      || /^data:/i.test(v)
      || /^\/api\/chat\/media\//i.test(v)
    )
  }

  // WeChat public account thumbnails (mmbiz.qpic.cn, wx.qlogo.cn...) are hotlink-protected:
  // the browser will get a placeholder image ("此图片来自微信公众号平台").
  // Proxy them via backend with a mp.weixin.qq.com Referer to fetch the real image.
  const normalizedThumbUrl = (() => {
    // Backend may provide either `thumbUrl` (appmsg) or `preview` (some exports). Use the first usable one.
    const candidates = [msg.thumbUrl, msg.preview]
    for (const cand of candidates) {
      if (isUsableMediaUrl(cand)) return normalizeMaybeUrl(cand)
    }
    return ''
  })()
  const normalizedLinkPreviewUrl = (() => {
    const u = normalizedThumbUrl
    if (!u) return ''
    if (/^\/api\/chat\/media\//i.test(u) || /^blob:/i.test(u) || /^data:/i.test(u)) return u
    if (!/^https?:\/\//i.test(u)) return u
    try {
      const host = new URL(u).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(u)}`
      }
    } catch {}
    return u
  })()

  const fromUsername = String(msg.fromUsername || '').trim()
  const fromAvatar = fromUsername
    ? `${apiBase}/chat/avatar?account=${encodeURIComponent(selectedAccount.value || '')}&username=${encodeURIComponent(fromUsername)}`
    : (() => {
      // App/web link shares may not provide `fromUsername` (sourceusername), so we don't have a WeChat avatar.
      // Fall back to a best-effort website favicon fetched via backend.
      const href = String(msg.url || '').trim()
      return href ? `${apiBase}/chat/media/favicon?url=${encodeURIComponent(href)}` : ''
    })()

  const localEmojiUrl = msg.emojiMd5 ? `${apiBase}/chat/media/emoji?account=${encodeURIComponent(selectedAccount.value || '')}&md5=${encodeURIComponent(msg.emojiMd5)}&username=${encodeURIComponent(selectedContact.value?.username || '')}` : ''
  const localImageUrl = (() => {
    if (!msg.imageMd5 && !msg.imageFileId) return ''
    const parts = [
      `account=${encodeURIComponent(selectedAccount.value || '')}`,
      msg.imageMd5 ? `md5=${encodeURIComponent(msg.imageMd5)}` : '',
      msg.imageFileId ? `file_id=${encodeURIComponent(msg.imageFileId)}` : '',
      `username=${encodeURIComponent(selectedContact.value?.username || '')}`,
    ].filter(Boolean)
    return `${apiBase}/chat/media/image?${parts.join('&')}`
  })()
  const normalizedImageUrl = (() => {
    const cur = (isUsableMediaUrl(msg.imageUrl) ? normalizeMaybeUrl(msg.imageUrl) : '')
    // If backend already returns a local media endpoint, prefer the locally-built URL because it includes file_id.
    if (cur && /\/api\/chat\/media\/image\b/i.test(cur) && localImageUrl) {
      return localImageUrl
    }
    return cur || localImageUrl || ''
  })()
  const normalizedEmojiUrl = msg.emojiUrl || localEmojiUrl
  const localVideoThumbUrl = (() => {
    if (!msg.videoThumbMd5 && !msg.videoThumbFileId) return ''
    const parts = [
      `account=${encodeURIComponent(selectedAccount.value || '')}`,
      msg.videoThumbMd5 ? `md5=${encodeURIComponent(msg.videoThumbMd5)}` : '',
      msg.videoThumbFileId ? `file_id=${encodeURIComponent(msg.videoThumbFileId)}` : '',
      `username=${encodeURIComponent(selectedContact.value?.username || '')}`,
    ].filter(Boolean)
    return `${apiBase}/chat/media/video_thumb?${parts.join('&')}`
  })()

  const localVideoUrl = (() => {
    if (!msg.videoMd5 && !msg.videoFileId) return ''
    const parts = [
      `account=${encodeURIComponent(selectedAccount.value || '')}`,
      msg.videoMd5 ? `md5=${encodeURIComponent(msg.videoMd5)}` : '',
      msg.videoFileId ? `file_id=${encodeURIComponent(msg.videoFileId)}` : '',
      `username=${encodeURIComponent(selectedContact.value?.username || '')}`,
    ].filter(Boolean)
    return `${apiBase}/chat/media/video?${parts.join('&')}`
  })()

  const normalizedVideoThumbUrl = (isUsableMediaUrl(msg.videoThumbUrl) ? normalizeMaybeUrl(msg.videoThumbUrl) : '') || localVideoThumbUrl
  const normalizedVideoUrl = (isUsableMediaUrl(msg.videoUrl) ? normalizeMaybeUrl(msg.videoUrl) : '') || localVideoUrl
  const serverIdStr = String(msg.serverIdStr || (msg.serverId != null ? String(msg.serverId) : '')).trim()
  const normalizedVoiceUrl = (() => {
    if (msg.voiceUrl) return msg.voiceUrl
    if (!serverIdStr) return ''
    if (String(msg.renderType || '') !== 'voice') return ''
    return `${apiBase}/chat/media/voice?account=${encodeURIComponent(selectedAccount.value || '')}&server_id=${encodeURIComponent(serverIdStr)}`
  })()

  const remoteFromServer = (
    typeof msg.emojiRemoteUrl === 'string'
    && /^https?:\/\//i.test(msg.emojiRemoteUrl)
    && !/\/api\/chat\/media\/emoji\b/i.test(msg.emojiRemoteUrl)
    && !/\blocalhost\b/i.test(msg.emojiRemoteUrl)
    && !/\b127\.0\.0\.1\b/i.test(msg.emojiRemoteUrl)
  ) ? msg.emojiRemoteUrl : ''

  const remoteFromEmojiUrl = (
    typeof msg.emojiUrl === 'string'
    && /^https?:\/\//i.test(msg.emojiUrl)
    && !/\/api\/chat\/media\/emoji\b/i.test(msg.emojiUrl)
    && !/\blocalhost\b/i.test(msg.emojiUrl)
    && !/\b127\.0\.0\.1\b/i.test(msg.emojiUrl)
  ) ? msg.emojiUrl : ''

  const emojiRemoteUrl = remoteFromServer || remoteFromEmojiUrl
  const emojiIsLocal = typeof normalizedEmojiUrl === 'string' && /\/api\/chat\/media\/emoji\b/i.test(normalizedEmojiUrl)
  const emojiDownloaded = !!emojiRemoteUrl && !!emojiIsLocal

  const replyText = String(msg.content || '').trim()
  let quoteContent = String(msg.quoteContent || '')
  const qcTrim = quoteContent.trim()
  if (replyText && qcTrim) {
    if (qcTrim === replyText) {
      quoteContent = ''
    } else {
      const lines = qcTrim.split(/\r?\n/).map((x) => x.trim())
      if (lines.length && (lines[0] === replyText || lines[0] === replyText.split(/\r?\n/)[0]?.trim())) {
        quoteContent = qcTrim.split(/\r?\n/).slice(1).join('\n').trim()
      } else if (qcTrim.startsWith(replyText)) {
        quoteContent = qcTrim.slice(replyText.length).trim()
      }
    }
  }

  const quoteServerIdStr = String(msg.quoteServerId || '').trim()
  const quoteTypeStr = String(msg.quoteType || '').trim()
  const quoteVoiceUrl = quoteServerIdStr
    ? `${apiBase}/chat/media/voice?account=${encodeURIComponent(selectedAccount.value || '')}&server_id=${encodeURIComponent(quoteServerIdStr)}`
    : ''
  const quoteImageUrl = (() => {
    if (!quoteServerIdStr) return ''
    if (quoteTypeStr !== '3' && String(msg.quoteContent || '').trim() !== '[图片]') return ''
    const convUsername = String(selectedContact.value?.username || '').trim()
    const parts = [
      `account=${encodeURIComponent(selectedAccount.value || '')}`,
      `server_id=${encodeURIComponent(quoteServerIdStr)}`,
      convUsername ? `username=${encodeURIComponent(convUsername)}` : ''
    ].filter(Boolean)
    return parts.length ? `${apiBase}/chat/media/image?${parts.join('&')}` : ''
  })()
  const quoteThumbUrl = (() => {
    const raw = isUsableMediaUrl(msg.quoteThumbUrl) ? normalizeMaybeUrl(msg.quoteThumbUrl) : ''
    if (!raw) return ''
    if (/^\/api\/chat\/media\//i.test(raw) || /^blob:/i.test(raw) || /^data:/i.test(raw)) return raw
    if (!/^https?:\/\//i.test(raw)) return raw
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  })()

  return {
    id: msg.id,
    serverId: msg.serverId || 0,
    serverIdStr,
    sender,
    senderUsername: msg.senderUsername || '',
    senderDisplayName: msg.senderDisplayName || '',
    content: msg.content || '',
    time: formatMessageTime(msg.createTime),
    fullTime: formatMessageFullTime(msg.createTime),
    createTime: Number(msg.createTime || 0),
    isSent,
    type: 'text',
    renderType: msg.renderType || 'text',
    voipType: msg.voipType || '',
    title: msg.title || '',
    url: msg.url || '',
    recordItem: msg.recordItem || '',
    imageMd5: msg.imageMd5 || '',
    imageFileId: msg.imageFileId || '',
    emojiMd5: msg.emojiMd5 || '',
    emojiUrl: normalizedEmojiUrl || '',
    emojiLocalUrl: localEmojiUrl || '',
    emojiRemoteUrl,
    _emojiDownloaded: !!emojiDownloaded,
    thumbUrl: msg.thumbUrl || '',
    imageUrl: normalizedImageUrl || '',
    videoMd5: msg.videoMd5 || '',
    videoThumbMd5: msg.videoThumbMd5 || '',
    videoFileId: msg.videoFileId || '',
    videoThumbFileId: msg.videoThumbFileId || '',
    videoThumbUrl: normalizedVideoThumbUrl || '',
    videoUrl: normalizedVideoUrl || '',
    quoteTitle: msg.quoteTitle || '',
    quoteContent,
    quoteUsername: msg.quoteUsername || '',
    quoteServerId: quoteServerIdStr,
    quoteType: quoteTypeStr,
    quoteVoiceLength: msg.quoteVoiceLength || '',
    quoteVoiceUrl,
    quoteImageUrl: quoteImageUrl || '',
    quoteThumbUrl: quoteThumbUrl || '',
    _quoteImageError: false,
    _quoteThumbError: false,
    amount: msg.amount || '',
    coverUrl: msg.coverUrl || '',
    fileSize: msg.fileSize || '',
    fileMd5: msg.fileMd5 || '',
    paySubType: msg.paySubType || '',
    transferStatus: msg.transferStatus || '',
    transferReceived: msg.paySubType === '3' || msg.transferStatus === '已收款' || msg.transferStatus === '已被接收',
    voiceUrl: normalizedVoiceUrl || '',
    voiceDuration: msg.voiceLength || msg.voiceDuration || '',
    locationLat: msg.locationLat ?? null,
    locationLng: msg.locationLng ?? null,
    locationPoiname: String(msg.locationPoiname || '').trim(),
    locationLabel: String(msg.locationLabel || '').trim(),
    preview: normalizedLinkPreviewUrl || '',
    linkType: String(msg.linkType || '').trim(),
    linkStyle: String(msg.linkStyle || '').trim(),
    linkCardVariant: String(msg.linkStyle || '').trim() === 'cover' ? 'cover' : 'default',
    from: String(msg.from || '').trim(),
    fromUsername,
    fromAvatar,
    isGroup: !!selectedContact.value?.isGroup,
    // Backends may use either `senderAvatar` (our API) or `avatar` (exported JSON).
    avatar: msg.senderAvatar || msg.avatar || fallbackAvatar || null,
    avatarColor: null
  }
}

const onAvatarError = (e, target) => {
  // Make sure we fall back to the initial avatar if the URL 404s/blocks.
  try { e?.target && (e.target.style.display = 'none') } catch {}
  try { if (target) target.avatar = null } catch {}
}

const shouldShowEmojiDownload = (message) => {
  if (!message?.emojiMd5) return false
  const u = String(message?.emojiRemoteUrl || '').trim()
  if (!u) return false
  if (!/^https?:\/\//i.test(u)) return false
  return true
}

const onEmojiDownloadClick = async (message) => {
  if (!process.client) return
  if (!message?.emojiMd5) return
  if (!selectedAccount.value) return

  const emojiUrl = String(message?.emojiRemoteUrl || '').trim()
  if (!emojiUrl) {
    window.alert('该表情没有可用的下载地址')
    return
  }

  if (message._emojiDownloading) return
  message._emojiDownloading = true

  try {
    const api = useApi()
    await api.downloadChatEmoji({
      account: selectedAccount.value,
      md5: message.emojiMd5,
      emoji_url: emojiUrl,
      force: false
    })
    message._emojiDownloaded = true
    if (message.emojiLocalUrl) {
      message.emojiUrl = message.emojiLocalUrl
    }
  } catch (e) {
    window.alert(e?.message || '下载失败')
  } finally {
    message._emojiDownloading = false
  }
}

const getChatHistoryPreviewLines = (message) => {
  const raw = String(message?.content || '').trim()
  if (!raw) return []
  return raw.split(/\r?\n/).map((x) => x.trim()).filter(Boolean).slice(0, 4)
}

// 浮动窗口：合并消息 / 链接卡片（支持同时打开多个，且可拖动）
const floatingWindows = ref([])
let floatingWindowSeq = 0
let floatingWindowZ = 70
const floatingDragState = { id: '', offsetX: 0, offsetY: 0 }

const clampNumber = (n, min, max) => Math.min(max, Math.max(min, n))
const getFloatingWindowById = (id) => {
  const list = Array.isArray(floatingWindows.value) ? floatingWindows.value : []
  return list.find((w) => String(w?.id || '') === String(id || '')) || null
}

const focusFloatingWindow = (id) => {
  const w = getFloatingWindowById(id)
  if (!w) return
  floatingWindowZ += 1
  w.zIndex = floatingWindowZ
}

const closeFloatingWindow = (id) => {
  const key = String(id || '')
  floatingWindows.value = (Array.isArray(floatingWindows.value) ? floatingWindows.value : []).filter((w) => String(w?.id || '') !== key)
  if (floatingDragState.id && String(floatingDragState.id) === key) {
    floatingDragState.id = ''
  }
}

const closeTopFloatingWindow = () => {
  const list = Array.isArray(floatingWindows.value) ? floatingWindows.value : []
  if (!list.length) return
  const top = list.reduce((acc, cur) => (Number(cur?.zIndex || 0) >= Number(acc?.zIndex || 0) ? cur : acc), list[0])
  if (top?.id) closeFloatingWindow(top.id)
}

const normalizeSessionPreview = (value) => {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/^\[location\]/i.test(text)) return text.replace(/^\[location\]/i, '[位置]')
  if (/:\s*\[location\]$/i.test(text)) return text.replace(/\[location\]$/i, '[位置]')
  return text
}

const openFloatingWindow = (payload) => {
  if (!process.client) return null
  const w0 = Number(payload?.width || 0) > 0 ? Number(payload.width) : 560
  const h0 = Number(payload?.height || 0) > 0 ? Number(payload.height) : 560
  const margin = 12
  const vpW = Math.max(320, window.innerWidth || 0)
  const vpH = Math.max(240, window.innerHeight || 0)
  const n = (Array.isArray(floatingWindows.value) ? floatingWindows.value.length : 0)
  const dx = 24 * (n % 6)
  const dy = 24 * (n % 6)
  const x0 = payload?.x != null ? Number(payload.x) : Math.round((vpW - w0) / 2 + dx)
  const y0 = payload?.y != null ? Number(payload.y) : Math.round((vpH - h0) / 2 + dy)

  floatingWindowSeq += 1
  floatingWindowZ += 1
  const win = {
    id: String(payload?.id || `fw_${Date.now()}_${floatingWindowSeq}`),
    kind: String(payload?.kind || 'chatHistory'),
    title: String(payload?.title || ''),
    zIndex: floatingWindowZ,
    x: clampNumber(x0, margin, Math.max(margin, vpW - w0 - margin)),
    y: clampNumber(y0, margin, Math.max(margin, vpH - h0 - margin)),
    width: w0,
    height: h0,
    // custom data per kind
    info: payload?.info || null,
    records: Array.isArray(payload?.records) ? payload.records : [],
    url: String(payload?.url || ''),
    content: String(payload?.content || ''),
    preview: String(payload?.preview || ''),
    from: String(payload?.from || ''),
    fromAvatar: String(payload?.fromAvatar || ''),
    loading: !!payload?.loading,
  }
  floatingWindows.value = [...(Array.isArray(floatingWindows.value) ? floatingWindows.value : []), win]
  // Return the reactive proxy from the state array; otherwise mutating the raw object won't trigger re-renders
  // (the UI would only update after an unrelated reactive change such as focusing the window).
  return getFloatingWindowById(win.id) || win
}

const startFloatingWindowDrag = (id, e) => {
  if (!process.client) return
  const w = getFloatingWindowById(id)
  if (!w) return
  focusFloatingWindow(id)
  const ev = e?.touches?.[0] || e
  const cx = Number(ev?.clientX || 0)
  const cy = Number(ev?.clientY || 0)
  floatingDragState.id = String(id || '')
  floatingDragState.offsetX = cx - Number(w.x || 0)
  floatingDragState.offsetY = cy - Number(w.y || 0)
  try { e?.preventDefault?.() } catch {}
}

const onFloatingWindowMouseMove = (e) => {
  if (!process.client) return
  const id = String(floatingDragState.id || '')
  if (!id) return
  const w = getFloatingWindowById(id)
  if (!w) return
  const ev = e?.touches?.[0] || e
  const cx = Number(ev?.clientX || 0)
  const cy = Number(ev?.clientY || 0)
  const margin = 8
  const vpW = Math.max(320, window.innerWidth || 0)
  const vpH = Math.max(240, window.innerHeight || 0)
  const nx = cx - Number(floatingDragState.offsetX || 0)
  const ny = cy - Number(floatingDragState.offsetY || 0)
  w.x = clampNumber(nx, margin, Math.max(margin, vpW - Number(w.width || 0) - margin))
  w.y = clampNumber(ny, margin, Math.max(margin, vpH - Number(w.height || 0) - margin))
}

const onFloatingWindowMouseUp = () => {
  floatingDragState.id = ''
}

// Legacy modal state kept only so the old template block compiles (we now use floating windows instead).
const chatHistoryModalVisible = ref(false)
const chatHistoryModalTitle = ref('')
const chatHistoryModalRecords = ref([])
const chatHistoryModalInfo = ref({ isChatRoom: false })
const chatHistoryModalStack = ref([])
const goBackChatHistoryModal = () => {}
const closeChatHistoryModal = () => {
  chatHistoryModalVisible.value = false
  chatHistoryModalTitle.value = ''
  chatHistoryModalRecords.value = []
  chatHistoryModalInfo.value = { isChatRoom: false }
  chatHistoryModalStack.value = []
}

const isMaybeMd5 = (value) => /^[0-9a-f]{32}$/i.test(String(value || '').trim())
const pickFirstMd5 = (...values) => {
  for (const v of values) {
    const s = String(v || '').trim()
    if (isMaybeMd5(s)) return s.toLowerCase()
  }
  return ''
}

const normalizeChatHistoryUrl = (value) => String(value || '').trim().replace(/\s+/g, '')
const stripWeChatInvisible = (value) => {
  // WeChat sometimes uses invisible filler characters like U+3164 (Hangul Filler) for "empty".
  return String(value || '').replace(/[\u3164\u2800]/g, '').trim()
}

const parseChatHistoryRecord = (recordItemXml) => {
  if (!process.client) return { info: null, items: [] }
  const xml = String(recordItemXml || '').trim()
  if (!xml) return { info: null, items: [] }

  const normalized = xml
    .replace(/&#x20;/g, ' ')
    // Strip control characters that are illegal in XML 1.0 (common in some recordItem payloads)
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
    // Escape stray ampersands (URLs sometimes contain raw '&' instead of '&amp;')
    .replace(/&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[\da-fA-F]+;)/g, '&amp;')
  let doc
  try {
    doc = new DOMParser().parseFromString(normalized, 'text/xml')
  } catch {
    return { info: null, items: [] }
  }

  const parserErrors = doc.getElementsByTagName('parsererror')
  if (parserErrors && parserErrors.length) return { info: null, items: [] }

  const getText = (node, tag) => {
    try {
      if (!node) return ''
      const els = Array.from(node.getElementsByTagName(tag) || [])
      const direct = els.find((el) => el && el.parentNode === node)
      const el = direct || els[0]
      return String(el?.textContent || '').trim()
    } catch {
      return ''
    }
  }

  const getDirectChildXml = (node, tag) => {
    try {
      if (!node) return ''
      const children = Array.from(node.children || [])
      const el = children.find((c) => String(c?.tagName || '').toLowerCase() === String(tag || '').toLowerCase())
      if (!el) return ''
      // If the child is a plain text/CDATA wrapper that contains another XML document, prefer that raw string.
      const raw = String(el.textContent || '').trim()
      if (raw && raw.startsWith('<') && raw.endsWith('>')) return raw

      // Otherwise serialize the element (nested recorditem may be provided as real XML nodes).
      if (typeof XMLSerializer !== 'undefined') {
        return new XMLSerializer().serializeToString(el)
      }
    } catch {}
    return ''
  }

  const getAnyXml = (node, tag) => {
    try {
      if (!node) return ''
      const els = Array.from(node.getElementsByTagName(tag) || [])
      const direct = els.find((el) => el && el.parentNode === node)
      const el = direct || els[0]
      if (!el) return ''

      const raw = String(el.textContent || '').trim()
      if (raw && raw.startsWith('<') && raw.endsWith('>')) return raw
      if (typeof XMLSerializer !== 'undefined') return new XMLSerializer().serializeToString(el)
    } catch {}
    return ''
  }

  const sameTag = (el, tag) => String(el?.tagName || '').toLowerCase() === String(tag || '').toLowerCase()

  const closestAncestorByTag = (node, tag) => {
    const lower = String(tag || '').toLowerCase()
    let cur = node
    while (cur) {
      if (cur.nodeType === 1 && String(cur.tagName || '').toLowerCase() === lower) return cur
      cur = cur.parentNode
    }
    return null
  }

  const root = doc?.documentElement
  const isChatRoom = String(getText(root, 'isChatRoom') || '').trim() === '1'
  const title = getText(root, 'title')
  const desc = getText(root, 'desc') || getText(root, 'info')

  const datalist = (() => {
    try {
      const all = Array.from(doc.getElementsByTagName('datalist') || [])
      // Prefer the datalist belonging to the top-level recorditem to avoid flattening nested records.
      const top = root ? all.find((el) => closestAncestorByTag(el, 'recorditem') === root) : null
      return top || all[0] || null
    } catch {
      return null
    }
  })()
  const datalistCount = (() => {
    try {
      if (!datalist) return 0
      const v = String(datalist.getAttribute('count') || '').trim()
      return Math.max(0, parseInt(v, 10) || 0)
    } catch {
      return 0
    }
  })()

  const itemNodes = (() => {
    if (datalist) return Array.from(datalist.children || []).filter((el) => sameTag(el, 'dataitem'))
    // Some recordItem payloads omit the <datalist> wrapper.
    return Array.from(root?.children || []).filter((el) => sameTag(el, 'dataitem'))
  })()

  const parsed = itemNodes.map((node, idx) => {
    const datatype = String(node.getAttribute('datatype') || getText(node, 'datatype') || '').trim()
    const dataid = String(node.getAttribute('dataid') || getText(node, 'dataid') || '').trim() || String(idx)

    const sourcename = getText(node, 'sourcename')
    const sourcetime = getText(node, 'sourcetime')
    const sourceheadurl = normalizeChatHistoryUrl(getText(node, 'sourceheadurl'))
    const datatitle = getText(node, 'datatitle')
    const datadesc = getText(node, 'datadesc')
    const link = normalizeChatHistoryUrl(getText(node, 'link') || getText(node, 'dataurl') || getText(node, 'url'))
    const datafmt = getText(node, 'datafmt')
    const duration = getText(node, 'duration')

    const fullmd5 = getText(node, 'fullmd5')
    const thumbfullmd5 = getText(node, 'thumbfullmd5')
    const md5 = getText(node, 'md5') || getText(node, 'emoticonmd5') || getText(node, 'emojiMd5')
    const fromnewmsgid = getText(node, 'fromnewmsgid')
    const srcMsgLocalid = getText(node, 'srcMsgLocalid') || getText(node, 'srcMsgLocalId')
    const srcMsgCreateTime = getText(node, 'srcMsgCreateTime')
    const cdnurlstring = normalizeChatHistoryUrl(getText(node, 'cdnurlstring'))
    const encrypturlstring = normalizeChatHistoryUrl(getText(node, 'encrypturlstring'))
    const externurl = normalizeChatHistoryUrl(getText(node, 'externurl'))
    const aeskey = getText(node, 'aeskey')
    const nestedRecordItem = getAnyXml(node, 'recorditem') || getDirectChildXml(node, 'recorditem') || getText(node, 'recorditem')

    let content = datatitle || datadesc
    if (!content) {
      if (datatype === '4') content = '[视频]'
      else if (datatype === '2' || datatype === '3') content = '[图片]'
      else if (datatype === '47' || datatype === '37') content = '[表情]'
      else if (datatype) content = `[消息 ${datatype}]`
      else content = '[消息]'
    }

    // Guess renderType using both datatype and available tags.
    const fmt = String(datafmt || '').trim().toLowerCase().replace(/^\./, '')
    const imageFormats = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif'])

    let renderType = 'text'
    if (datatype === '17') {
      renderType = 'chatHistory'
    } else if (datatype === '5' || link) {
      renderType = 'link'
    } else if (datatype === '4' || String(duration || '').trim() || fmt === 'mp4') {
      renderType = 'video'
    } else if (datatype === '47' || datatype === '37') {
      renderType = 'emoji'
    } else if (
      datatype === '2'
      || datatype === '3'
      || imageFormats.has(fmt)
      || (datatype !== '1' && isMaybeMd5(fullmd5))
    ) {
      renderType = 'image'
    } else if (isMaybeMd5(md5) && /表情/.test(String(content || ''))) {
      // Some merged-forward records use non-standard datatype but still provide emoticon md5.
      renderType = 'emoji'
    }

    let outTitle = ''
    let outUrl = ''
    let recordItem = ''
    if (renderType === 'chatHistory') {
      outTitle = datatitle || content || '聊天记录'
      content = datadesc || ''
      recordItem = nestedRecordItem
    } else if (renderType === 'link') {
      outTitle = datatitle || content || ''
      outUrl = link || externurl || ''
      const cleanDesc = stripWeChatInvisible(datadesc)
      const cleanTitle = stripWeChatInvisible(outTitle)
      // Keep card description only when it's not a filler placeholder and not identical to the title.
      if (!cleanDesc || (cleanTitle && cleanDesc === cleanTitle)) {
        content = ''
      } else {
        content = String(datadesc || '').trim()
      }
    }

    return {
      id: dataid,
      datatype,
      sourcename,
      sourcetime,
      sourceheadurl,
      datafmt,
      duration,
      fullmd5,
      thumbfullmd5,
      md5,
      fromnewmsgid,
      srcMsgLocalid,
      srcMsgCreateTime,
      cdnurlstring,
      encrypturlstring,
      externurl,
      aeskey,
      renderType,
      title: outTitle,
      recordItem,
      url: outUrl,
      content
    }
  })

  return {
    info: { isChatRoom, title, desc, count: datalistCount },
    items: parsed
  }
}

const formatChatHistoryVideoDuration = (value) => {
  const total = Math.max(0, parseInt(String(value || '').trim(), 10) || 0)
  const m = Math.floor(total / 60)
  const s = total % 60
  if (m <= 0) return `0:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

const normalizeChatHistoryRecordItem = (rec) => {
  const apiBase = useApiBase()
  const account = encodeURIComponent(selectedAccount.value || '')
  const username = encodeURIComponent(selectedContact.value?.username || '')

  const out = { ...(rec || {}) }
  out.senderDisplayName = String(out.sourcename || '').trim()
  out.senderAvatar = normalizeChatHistoryUrl(out.sourceheadurl)
  out.fullTime = String(out.sourcetime || '').trim()

  if (out.renderType === 'link') {
    const linkUrl = String(out.url || out.externurl || '').trim()
    out.url = linkUrl
    out.from = String(out.from || '').trim()
    const previewCandidates = []

    // Some link cards store thumbnails with a "file_id" naming scheme: local_id_create_time.
    const fileId = (() => {
      const lid = parseInt(String(out.srcMsgLocalid || '').trim(), 10) || 0
      const ct = parseInt(String(out.srcMsgCreateTime || '').trim(), 10) || 0
      if (lid > 0 && ct > 0) return `${lid}_${ct}`
      return ''
    })()
    if (fileId) {
      previewCandidates.push(
        `${apiBase}/chat/media/image?account=${account}&file_id=${encodeURIComponent(fileId)}&username=${username}`
      )
    }

    // Fallback: some records still carry md5-ish fields.
    out.previewMd5 = pickFirstMd5(out.fullmd5, out.thumbfullmd5, out.md5)
    const srcServerId = String(out.fromnewmsgid || '').trim()
    if (out.previewMd5) {
      const previewParts = [
        `account=${account}`,
        `md5=${encodeURIComponent(out.previewMd5)}`,
        srcServerId ? `server_id=${encodeURIComponent(srcServerId)}` : '',
        `username=${username}`
      ].filter(Boolean)
      previewCandidates.push(`${apiBase}/chat/media/image?${previewParts.join('&')}`)
    }

    out._linkPreviewCandidates = previewCandidates
    out._linkPreviewCandidateIndex = 0
    out._linkPreviewError = false
    out.preview = previewCandidates[0] || ''

    const fromUsername = String(out.fromUsername || '').trim()
    out.fromUsername = fromUsername
    out.fromAvatar = fromUsername
      ? `${apiBase}/chat/avatar?account=${account}&username=${encodeURIComponent(fromUsername)}`
      : (linkUrl ? `${apiBase}/chat/media/favicon?url=${encodeURIComponent(linkUrl)}` : '')
    out._fromAvatarLast = out.fromAvatar
    out._fromAvatarImgOk = false
    out._fromAvatarImgError = false
  } else if (out.renderType === 'video') {
    out.videoMd5 = pickFirstMd5(out.fullmd5, out.md5)
    out.videoThumbMd5 = pickFirstMd5(out.thumbfullmd5)
    out.videoDuration = String(out.duration || '').trim()
    const thumbCandidates = []
    if (out.videoMd5) {
      thumbCandidates.push(`${apiBase}/chat/media/video_thumb?account=${account}&md5=${encodeURIComponent(out.videoMd5)}&username=${username}`)
    }
    if (out.videoThumbMd5 && out.videoThumbMd5 !== out.videoMd5) {
      thumbCandidates.push(`${apiBase}/chat/media/video_thumb?account=${account}&md5=${encodeURIComponent(out.videoThumbMd5)}&username=${username}`)
    }
    out._videoThumbCandidates = thumbCandidates
    out._videoThumbCandidateIndex = 0
    out._videoThumbError = false
    out.videoThumbUrl = thumbCandidates[0] || ''
    out.videoUrl = out.videoMd5
      ? `${apiBase}/chat/media/video?account=${account}&md5=${encodeURIComponent(out.videoMd5)}&username=${username}`
      : ''
    if (!out.content || /^\[.+\]$/.test(String(out.content || '').trim())) out.content = '[视频]'
  } else if (out.renderType === 'emoji') {
    out.emojiMd5 = pickFirstMd5(out.md5, out.fullmd5, out.thumbfullmd5)
    const remoteEmojiUrl = String(out.cdnurlstring || out.externurl || out.encrypturlstring || '').trim()
    const remoteAesKey = String(out.aeskey || '').trim()
    out.emojiRemoteUrl = remoteEmojiUrl
    out.emojiUrl = out.emojiMd5
      ? `${apiBase}/chat/media/emoji?account=${account}&md5=${encodeURIComponent(out.emojiMd5)}&username=${username}${remoteEmojiUrl ? `&emoji_url=${encodeURIComponent(remoteEmojiUrl)}` : ''}${remoteAesKey ? `&aes_key=${encodeURIComponent(remoteAesKey)}` : ''}`
      : ''
    if (!out.content || /^\[.+\]$/.test(String(out.content || '').trim())) out.content = '[表情]'
  } else if (out.renderType === 'image') {
    out.imageMd5 = pickFirstMd5(out.fullmd5, out.thumbfullmd5, out.md5)
    const srcServerId = String(out.fromnewmsgid || '').trim()
    const imgParts = [
      `account=${account}`,
      out.imageMd5 ? `md5=${encodeURIComponent(out.imageMd5)}` : '',
      srcServerId ? `server_id=${encodeURIComponent(srcServerId)}` : '',
      `username=${username}`
    ].filter(Boolean)
    out.imageUrl = imgParts.length ? `${apiBase}/chat/media/image?${imgParts.join('&')}` : ''
    if (!out.content || /^\[.+\]$/.test(String(out.content || '').trim())) out.content = '[图片]'
  }

  return out
}

const enhanceChatHistoryRecords = (records) => {
  const list = Array.isArray(records) ? records : []
  const videoByThumbMd5 = new Map()
  const videoByMd5 = new Map()
  const imageByMd5 = new Map()
  const emojiByMd5 = new Map()

  for (const rec of list) {
    if (!rec) continue
    if (rec.renderType === 'video' && rec.videoThumbMd5) {
      videoByThumbMd5.set(String(rec.videoThumbMd5).toLowerCase(), rec)
    }
    if (rec.renderType === 'video' && rec.videoMd5) {
      videoByMd5.set(String(rec.videoMd5).toLowerCase(), rec)
    }
    if (rec.renderType === 'image') {
      const keys = [
        pickFirstMd5(rec.imageMd5),
        pickFirstMd5(rec.fullmd5),
        pickFirstMd5(rec.thumbfullmd5),
      ].filter(Boolean)
      for (const k of keys) imageByMd5.set(k, rec)
    }
    if (rec.renderType === 'emoji') {
      const keys = [
        pickFirstMd5(rec.emojiMd5),
        pickFirstMd5(rec.md5),
        pickFirstMd5(rec.fullmd5),
        pickFirstMd5(rec.thumbfullmd5),
      ].filter(Boolean)
      for (const k of keys) emojiByMd5.set(k, rec)
    }
  }

  for (const rec of list) {
    if (!rec) continue
    if (String(rec.renderType || '') !== 'text') continue

    const refKey = pickFirstMd5(rec.thumbfullmd5) || pickFirstMd5(rec.fullmd5)
    if (!refKey) continue

    const v = videoByThumbMd5.get(refKey) || videoByMd5.get(refKey)
    if (v) {
      const quoteThumbCandidates = Array.isArray(v._videoThumbCandidates) ? v._videoThumbCandidates.slice() : []
      rec._quoteThumbCandidates = quoteThumbCandidates
      rec._quoteThumbCandidateIndex = 0
      rec._quoteThumbError = false
      const quoteThumbUrl = quoteThumbCandidates[0] || v.videoThumbUrl || ''
      rec.renderType = 'quote'
      rec.quote = {
        kind: 'video',
        thumbUrl: quoteThumbUrl,
        url: v.videoUrl || '',
        duration: v.videoDuration || '',
        label: v.content || '[视频]',
        targetId: v.id || ''
      }
      rec.quoteMedia = {
        videoMd5: v.videoMd5,
        videoThumbMd5: v.videoThumbMd5,
        videoUrl: v.videoUrl,
        videoThumbUrl: quoteThumbUrl
      }
      continue
    }

    const img = imageByMd5.get(refKey)
    if (img) {
      rec.renderType = 'quote'
      rec.quote = {
        kind: 'image',
        thumbUrl: img.imageUrl || '',
        url: img.imageUrl || '',
        label: img.content || '[图片]',
        targetId: img.id || ''
      }
      rec.quoteMedia = {
        imageMd5: img.imageMd5,
        imageUrl: img.imageUrl
      }
      continue
    }

    const em = emojiByMd5.get(refKey)
    if (em) {
      rec.renderType = 'quote'
      rec.quote = {
        kind: 'emoji',
        thumbUrl: em.emojiUrl || '',
        url: em.emojiUrl || '',
        label: em.content || '[表情]',
        targetId: em.id || ''
      }
      rec.quoteMedia = {
        emojiMd5: em.emojiMd5,
        emojiUrl: em.emojiUrl
      }
    }
  }

  return list
}

const onChatHistoryVideoThumbError = (rec) => {
  if (!rec) return
  const candidates = rec._videoThumbCandidates
  if (!Array.isArray(candidates) || candidates.length <= 1) {
    rec._videoThumbError = true
    return
  }

  const cur = Math.max(0, Number(rec._videoThumbCandidateIndex || 0))
  const next = cur + 1
  if (next < candidates.length) {
    rec._videoThumbCandidateIndex = next
    rec.videoThumbUrl = candidates[next]
    return
  }
  rec._videoThumbError = true
}

const onChatHistoryLinkPreviewError = (rec) => {
  if (!rec) return
  const candidates = rec._linkPreviewCandidates
  if (!Array.isArray(candidates) || candidates.length <= 1) {
    rec._linkPreviewError = true
    return
  }

  const cur = Math.max(0, Number(rec._linkPreviewCandidateIndex || 0))
  const next = cur + 1
  if (next < candidates.length) {
    rec._linkPreviewCandidateIndex = next
    rec.preview = candidates[next]
    rec._linkPreviewError = false
    return
  }
  rec._linkPreviewError = true
}

const onChatHistoryFromAvatarLoad = (rec) => {
  try {
    if (rec) {
      rec._fromAvatarImgOk = true
      rec._fromAvatarImgError = false
      rec._fromAvatarLast = String(rec.fromAvatar || '').trim()
    }
  } catch {}
}

const onChatHistoryFromAvatarError = (rec) => {
  try {
    if (rec) {
      rec._fromAvatarImgOk = false
      rec._fromAvatarImgError = true
      rec._fromAvatarLast = String(rec.fromAvatar || '').trim()
    }
  } catch {}
}

const onChatHistoryQuoteThumbError = (rec) => {
  if (!rec || !rec.quote) return
  const candidates = rec._quoteThumbCandidates
  if (!Array.isArray(candidates) || candidates.length <= 1) {
    rec._quoteThumbError = true
    return
  }

  const cur = Math.max(0, Number(rec._quoteThumbCandidateIndex || 0))
  const next = cur + 1
  if (next < candidates.length) {
    rec._quoteThumbCandidateIndex = next
    rec.quote.thumbUrl = candidates[next]
    return
  }
  rec._quoteThumbError = true
}

const openChatHistoryQuote = (rec) => {
  if (!process.client) return
  const q = rec?.quote
  if (!q) return

  const kind = String(q.kind || '')
  const url = String(q.url || '').trim()
  if (!url) return

  if (kind === 'video') {
    openVideoPreview(url, q?.thumbUrl)
    return
  }

  if (kind === 'image' || kind === 'emoji') {
    openImagePreview(url)
  }
}

const isChatHistoryRecordItemIncomplete = (recordItemXml) => {
  const recordItem = String(recordItemXml || '').trim()
  if (!recordItem) return true
  try {
    const parsed = parseChatHistoryRecord(recordItem)
    const got = Array.isArray(parsed?.items) ? parsed.items.length : 0
    const expect = Math.max(0, parseInt(String(parsed?.info?.count || '0'), 10) || 0)
    if (expect > 0 && got < expect) return true
    if (got <= 0) return true
  } catch {
    return true
  }
  return false
}

const buildChatHistoryWindowPayload = (payload) => {
  const title0 = String(payload?.title || '聊天记录')
  const content0 = String(payload?.content || '')
  const recordItem0 = String(payload?.recordItem || '').trim()
  const parsed = parseChatHistoryRecord(recordItem0)
  const info0 = parsed?.info || { isChatRoom: false, count: 0 }
  const items = Array.isArray(parsed?.items) ? parsed.items : []
  let records0 = items.length ? enhanceChatHistoryRecords(items.map(normalizeChatHistoryRecordItem)) : []
  if (!records0.length) {
    // 降级：使用摘要内容按行展示
    const lines = content0.trim().split(/\r?\n/).map((x) => x.trim()).filter(Boolean)
    records0 = lines.map((line, idx) => normalizeChatHistoryRecordItem({
      id: String(idx),
      datatype: '1',
      sourcename: '',
      sourcetime: '',
      content: line,
      renderType: 'text'
    }))
  }
  return { title0, content0, recordItem0, info0, records0 }
}

const openChatHistoryModal = (message) => {
  if (!process.client) return
  const { title0, content0, recordItem0, info0, records0 } = buildChatHistoryWindowPayload(message)
  const win = openFloatingWindow({
    kind: 'chatHistory',
    title: title0 || '聊天记录',
    info: info0,
    records: records0,
    width: 560,
    height: Math.round(Math.max(420, (window.innerHeight || 700) * 0.78)),
  })
  if (!win) return
  // Pre-resolve link cards inside this chat history so they render like WeChat (source/app name, etc).
  try { resolveChatHistoryLinkRecords(win) } catch {}
  // Root chatHistory messages usually carry the full recordItem already; no further resolve here.
}

const openNestedChatHistory = (rec) => {
  if (!process.client) return
  const title0 = String(rec?.title || '聊天记录')
  const content0 = String(rec?.content || '')
  const recordItem0 = String(rec?.recordItem || '').trim()
  const sid = String(rec?.fromnewmsgid || '').trim()

  const { info0, records0 } = buildChatHistoryWindowPayload({ title: title0, content: content0, recordItem: recordItem0 })
  const win = openFloatingWindow({
    kind: 'chatHistory',
    title: title0 || '聊天记录',
    info: info0,
    records: records0,
    width: 560,
    height: Math.round(Math.max(420, (window.innerHeight || 700) * 0.78)),
    loading: false,
  })
  if (!win) return
  try { resolveChatHistoryLinkRecords(win) } catch {}

  if (!sid) return
  if (!selectedAccount.value) return
  if (rec && rec._nestedResolving) return

  if (!isChatHistoryRecordItemIncomplete(recordItem0)) return
  rec._nestedResolving = true
  win.loading = true

  ;(async () => {
    try {
      const api = useApi()
      const resp = await api.resolveNestedChatHistory({
        account: selectedAccount.value,
        server_id: sid,
      })
      const resolved = String(resp?.recordItem || '').trim()
      if (!resolved) return
      win.title = String(resp?.title || title0 || '聊天记录')
      const parsed = parseChatHistoryRecord(resolved)
      win.info = parsed?.info || { isChatRoom: false, count: 0 }
      const items = Array.isArray(parsed?.items) ? parsed.items : []
      win.records = items.length ? enhanceChatHistoryRecords(items.map(normalizeChatHistoryRecordItem)) : []
      if (!win.records.length) {
        const lines = String(resp?.content || content0 || '').trim().split(/\r?\n/).map((x) => x.trim()).filter(Boolean)
        win.info = { isChatRoom: false, count: 0 }
        win.records = lines.map((line, idx) => normalizeChatHistoryRecordItem({ id: String(idx), datatype: '1', sourcename: '', sourcetime: '', content: line, renderType: 'text' }))
      }
      try { resolveChatHistoryLinkRecords(win) } catch {}
    } catch {}
    finally {
      win.loading = false
      try { rec._nestedResolving = false } catch {}
    }
  })()
}

const getChatHistoryLinkFromText = (rec) => {
  const from0 = String(rec?.from || '').trim()
  if (from0) return from0
  const u = String(rec?.url || '').trim()
  if (!u) return ''
  try { return new URL(u).hostname || '' } catch { return '' }
}

const getChatHistoryLinkFromAvatarText = (rec) => {
  const t = String(getChatHistoryLinkFromText(rec) || '').trim()
  return t ? (Array.from(t)[0] || '') : ''
}

const openUrlInBrowser = (url) => {
  const u = String(url || '').trim()
  if (!u) return
  try { window.open(u, '_blank', 'noopener,noreferrer') } catch {}
}

const resolveChatHistoryLinkRecord = async (rec) => {
  if (!process.client) return null
  if (!rec) return null
  if (!selectedAccount.value) return null
  const sid = String(rec?.fromnewmsgid || '').trim()
  if (!sid) return null
  if (rec._linkResolving) return null
  rec._linkResolving = true
  try {
    const api = useApi()
    const resp = await api.resolveAppMsg({
      account: selectedAccount.value,
      server_id: sid,
    })
    if (resp && typeof resp === 'object') {
      const title = String(resp.title || '').trim()
      const content = String(resp.content || '').trim()
      const url = String(resp.url || '').trim()
      const from = String(resp.from || '').trim()
      const apiBase = useApiBase()
      const normalizePreviewUrl = (u) => {
        const raw = String(u || '').trim()
        if (!raw) return ''
        if (/^\/api\/chat\/media\//i.test(raw) || /^blob:/i.test(raw) || /^data:/i.test(raw)) return raw
        if (!/^https?:\/\//i.test(raw)) return ''
        try {
          const host = new URL(raw).hostname.toLowerCase()
          if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
            return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
          }
        } catch {}
        return raw
      }
      if (title) rec.title = title
      if (content && !stripWeChatInvisible(rec.content)) rec.content = content
      if (url) rec.url = url
      if (from) rec.from = from
      if (resp.linkStyle) rec.linkStyle = String(resp.linkStyle || '').trim()
      if (resp.linkType) rec.linkType = String(resp.linkType || '').trim()

      const fromUsername = String(resp.fromUsername || '').trim()
      if (fromUsername) rec.fromUsername = fromUsername
      const fromAvatarUrl = fromUsername
        ? `${apiBase}/chat/avatar?account=${encodeURIComponent(selectedAccount.value || '')}&username=${encodeURIComponent(fromUsername)}`
        : (url ? `${apiBase}/chat/media/favicon?url=${encodeURIComponent(url)}` : '')
      if (fromAvatarUrl) {
        const last = String(rec._fromAvatarLast || '').trim()
        rec.fromAvatar = fromAvatarUrl
        if (String(fromAvatarUrl).trim() !== last) {
          rec._fromAvatarLast = String(fromAvatarUrl).trim()
          rec._fromAvatarImgOk = false
          rec._fromAvatarImgError = false
        }
      }

      const style0 = String(resp.linkStyle || '').trim()
      const thumb0 = String(resp.thumbUrl || '').trim()
      const cover0 = String(resp.coverUrl || '').trim()
      const picked = style0 === 'cover' ? (cover0 || thumb0) : (thumb0 || cover0)
      const previewResolved = normalizePreviewUrl(picked)
      if (previewResolved) {
        const curPreview = String(rec.preview || '').trim()
        const candidates0 = Array.isArray(rec._linkPreviewCandidates) ? rec._linkPreviewCandidates.slice() : []
        if (curPreview && !candidates0.includes(curPreview)) candidates0.push(curPreview)
        if (!candidates0.includes(previewResolved)) candidates0.push(previewResolved)
        rec._linkPreviewCandidates = candidates0
        if (!curPreview || rec._linkPreviewError) {
          rec.preview = previewResolved
          rec._linkPreviewCandidateIndex = candidates0.indexOf(previewResolved)
          rec._linkPreviewError = false
        }
      }
      return resp
    }
  } catch {}
  finally {
    try { rec._linkResolving = false } catch {}
  }
  return null
}

const resolveChatHistoryLinkRecords = (win) => {
  if (!process.client) return
  const records = Array.isArray(win?.records) ? win.records : []
  const targets = records.filter((r) => {
    if (!r) return false
    if (String(r.renderType || '') !== 'link') return false
    if (!String(r.fromnewmsgid || '').trim()) return false
    const fromMissing = String(r.from || '').trim() === ''
    const previewMissing = !String(r.preview || '').trim()
    const urlMissing = !String(r.url || '').trim()
    const fromAvatarMissing = !String(r.fromAvatar || '').trim()
    return fromMissing || previewMissing || urlMissing || fromAvatarMissing
  })
  if (!targets.length) return
  // Resolve sequentially to avoid spamming the backend.
  ;(async () => {
    for (const r of targets.slice(0, 12)) {
      await resolveChatHistoryLinkRecord(r)
    }
  })()
}

const openChatHistoryLinkWindow = (rec) => {
  if (!process.client) return
  const title0 = String(rec?.title || rec?.content || '链接').trim()
  const url0 = String(rec?.url || '').trim()
  const preview0 = String(rec?.preview || '').trim()
  const from0 = String(rec?.from || '').trim()
  const fromAvatar0 = String(rec?.fromAvatar || '').trim()
  const needResolve = !!String(rec?.fromnewmsgid || '').trim() && (!url0 || !from0 || !preview0 || !fromAvatar0)
  const win = openFloatingWindow({
    kind: 'link',
    title: title0 || '链接',
    url: url0,
    content: String(rec?.content || '').trim(),
    preview: preview0,
    from: from0,
    fromAvatar: fromAvatar0,
    width: 520,
    height: 420,
    loading: needResolve,
  })
  if (!win) return
  focusFloatingWindow(win.id)
  try {
    win._linkPreviewCandidates = Array.isArray(rec?._linkPreviewCandidates) ? rec._linkPreviewCandidates.slice() : (preview0 ? [preview0] : [])
    win._linkPreviewCandidateIndex = Math.max(0, Number(rec?._linkPreviewCandidateIndex || 0))
    win._linkPreviewError = false
  } catch {}
  try {
    win._fromAvatarLast = fromAvatar0
    win._fromAvatarImgOk = false
    win._fromAvatarImgError = false
  } catch {}

  if (needResolve) {
    // Fill missing fields lazily so the card footer matches WeChat.
    ;(async () => {
      const resp = await resolveChatHistoryLinkRecord(rec)
      if (resp && win) {
        win.title = String(rec?.title || title0 || '链接').trim()
        win.url = String(rec?.url || url0 || '').trim()
        win.content = String(rec?.content || '').trim()
        win.from = String(rec?.from || '').trim()
        const nextPreview = String(rec?.preview || '').trim()
        if (nextPreview) win.preview = nextPreview
        const nextFromAvatar = String(rec?.fromAvatar || '').trim()
        if (nextFromAvatar) {
          win.fromAvatar = nextFromAvatar
          win._fromAvatarLast = nextFromAvatar
          win._fromAvatarImgOk = false
          win._fromAvatarImgError = false
        }
        try {
          win._linkPreviewCandidates = Array.isArray(rec?._linkPreviewCandidates) ? rec._linkPreviewCandidates.slice() : (win.preview ? [win.preview] : [])
          win._linkPreviewCandidateIndex = Math.max(0, Number(rec?._linkPreviewCandidateIndex || 0))
          win._linkPreviewError = false
        } catch {}
      }
      if (win) win.loading = false
    })()
  } else {
    win.loading = false
  }
}

const onGlobalClick = (e) => {
  if (contextMenu.value.visible) closeContextMenu()
  if (messageSearchSenderDropdownOpen.value) {
    const el = messageSearchSenderDropdownRef.value
    const t = e?.target
    if (el && t && !el.contains(t)) {
      closeMessageSearchSenderDropdown()
    }
  }
}

const openMessageSearch = async () => {
  closeTimeSidebar()
  messageSearchOpen.value = true
  ensureMessageSearchScopeValid()
  await nextTick()
  try {
    messageSearchInputRef.value?.focus?.()
  } catch {}
  await fetchMessageSearchIndexStatus()
}

const onGlobalKeyDown = (e) => {
  if (!process.client) return

  const key = String(e?.key || '')
  const lower = key.toLowerCase()

  if ((e.ctrlKey || e.metaKey) && lower === 'f') {
    e.preventDefault()
    openMessageSearch()
    return
  }

  if (key === 'Escape') {
    if (contextMenu.value.visible) closeContextMenu()
    if (previewImageUrl.value) closeImagePreview()
    if (previewVideoUrl.value) closeVideoPreview()
    if (Array.isArray(floatingWindows.value) && floatingWindows.value.length) closeTopFloatingWindow()
    if (chatHistoryModalVisible.value) closeChatHistoryModal()
    if (contactProfileCardOpen.value) {
      clearContactProfileHoverHideTimer()
      closeContactProfileCard()
    }
    if (messageSearchSenderDropdownOpen.value) closeMessageSearchSenderDropdown()
    if (messageSearchOpen.value) closeMessageSearch()
    if (timeSidebarOpen.value) closeTimeSidebar()
    if (searchContext.value?.active) exitSearchContext()
  }
}

onMounted(() => {
  if (!process.client) return
  document.addEventListener('click', onGlobalClick)
  document.addEventListener('keydown', onGlobalKeyDown)
  document.addEventListener('mousemove', onFloatingWindowMouseMove)
  document.addEventListener('mouseup', onFloatingWindowMouseUp)
  document.addEventListener('touchmove', onFloatingWindowMouseMove)
  document.addEventListener('touchend', onFloatingWindowMouseUp)
  document.addEventListener('touchcancel', onFloatingWindowMouseUp)
})

onUnmounted(() => {
  if (!process.client) return
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onGlobalKeyDown)
  document.removeEventListener('mousemove', onFloatingWindowMouseMove)
  document.removeEventListener('mouseup', onFloatingWindowMouseUp)
  document.removeEventListener('touchmove', onFloatingWindowMouseMove)
  document.removeEventListener('touchend', onFloatingWindowMouseUp)
  document.removeEventListener('touchcancel', onFloatingWindowMouseUp)
  clearContactProfileHoverHideTimer()
  stopSessionListResize()
  if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
  messageSearchDebounceTimer = null
  if (highlightMessageTimer) clearTimeout(highlightMessageTimer)
  highlightMessageTimer = null
  stopMessageSearchIndexPolling()
  stopExportPolling()
})

const dedupeMessagesById = (list) => {
  const arr = Array.isArray(list) ? list : []
  const seen = new Set()
  const out = []
  for (const m of arr) {
    const id = String(m?.id || '')
    if (!id) {
      out.push(m)
      continue
    }
    if (seen.has(id)) continue
    seen.add(id)
    out.push(m)
  }
  return out
}

const loadMessages = async ({ username, reset }) => {
  if (!username) return
  if (!selectedAccount.value) return

  const api = useApi()
  messagesError.value = ''
  isLoadingMessages.value = true
  activeMessagesFor.value = username

  try {
    const existing = allMessages.value[username] || []
    const container = messageContainerRef.value
    const beforeScrollHeight = container ? container.scrollHeight : 0
    const beforeScrollTop = container ? container.scrollTop : 0
    const offset = reset ? 0 : existing.length

    const params = {
      account: selectedAccount.value,
      username,
      limit: messagePageSize,
      offset,
      order: 'asc',
    }
    if (messageTypeFilter.value && messageTypeFilter.value !== 'all') {
      params.render_types = messageTypeFilter.value
    }
    if (realtimeEnabled.value) {
      // In realtime mode, read directly from WCDB to avoid blocking on background sync.
      params.source = 'realtime'
    }
    const resp = await api.listChatMessages(params)

    const raw = resp?.messages || []
    const mapped = dedupeMessagesById(raw.map(normalizeMessage))

    if (activeMessagesFor.value !== username) {
      return
    }

    if (reset) {
      allMessages.value = {
        ...allMessages.value,
        [username]: mapped
      }
    } else {
      const existingIds = new Set(existing.map((m) => String(m?.id || '')))
      const older = mapped.filter((m) => {
        const id = String(m?.id || '')
        if (!id) return true
        if (existingIds.has(id)) return false
        existingIds.add(id)
        return true
      })
      allMessages.value = {
        ...allMessages.value,
        [username]: [...older, ...existing]
      }
    }

    messagesMeta.value = {
      ...messagesMeta.value,
      [username]: {
        total: Number(resp?.total || 0),
        hasMore: resp?.hasMore
      }
    }

    await nextTick()
    const c = messageContainerRef.value
    if (c) {
      if (reset) {
        c.scrollTop = c.scrollHeight
      } else {
        const afterScrollHeight = c.scrollHeight
        c.scrollTop = beforeScrollTop + (afterScrollHeight - beforeScrollHeight)
      }
    }
    updateJumpToBottomState()
  } catch (e) {
    messagesError.value = e?.message || '加载聊天记录失败'
  } finally {
    isLoadingMessages.value = false
  }
}

const loadMoreMessages = async () => {
  if (!selectedContact.value) return
  if (searchContext.value?.active) return
  await loadMessages({ username: selectedContact.value.username, reset: false })
}

const refreshSelectedMessages = async () => {
  if (!selectedContact.value) return
  if (searchContext.value?.active) await exitSearchContext()
  await loadMessages({ username: selectedContact.value.username, reset: true })
}

const refreshRealtimeIncremental = async () => {
  if (!realtimeEnabled.value) return
  if (!selectedAccount.value) return
  if (!selectedContact.value?.username) return
  if (searchContext.value?.active) return
  if (isLoadingMessages.value) return

  const username = selectedContact.value.username
  const existing = allMessages.value[username] || []
  if (!existing.length) return

  const container = messageContainerRef.value
  const atBottom = !!container && (container.scrollHeight - container.scrollTop - container.clientHeight) < 80

  const api = useApi()
  const params = {
    account: selectedAccount.value,
    username,
    limit: 30,
    offset: 0,
    order: 'asc',
  }
  if (messageTypeFilter.value && messageTypeFilter.value !== 'all') {
    params.render_types = messageTypeFilter.value
  }
  params.source = 'realtime'

  const resp = await api.listChatMessages(params)
  if (selectedContact.value?.username !== username) return

  const raw = resp?.messages || []
  const latest = raw.map(normalizeMessage)
  const seenIds = new Set(existing.map((m) => String(m?.id || '')))
  const newOnes = []
  for (const m of latest) {
    const id = String(m?.id || '')
    if (!id) continue
    if (seenIds.has(id)) continue
    seenIds.add(id)
    newOnes.push(m)
  }
  if (!newOnes.length) return

  allMessages.value = {
    ...allMessages.value,
    [username]: [...existing, ...newOnes]
  }

  await nextTick()
  const c = messageContainerRef.value
  if (c && atBottom) {
    c.scrollTop = c.scrollHeight
  }
  updateJumpToBottomState()
}

const queueRealtimeRefresh = () => {
  if (realtimeRefreshFuture) {
    realtimeRefreshQueued = true
    return
  }

  realtimeRefreshFuture = refreshRealtimeIncremental().finally(() => {
    realtimeRefreshFuture = null
    if (realtimeRefreshQueued) {
      realtimeRefreshQueued = false
      queueRealtimeRefresh()
    }
  })
}

const tryEnableRealtimeAuto = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!desktopAutoRealtime.value) return
  if (realtimeEnabled.value) return
  if (!selectedAccount.value) return

  try {
    await realtimeStore.enable({ silent: true })
  } catch {}
}

watch(realtimeChangeSeq, () => {
  queueRealtimeRefresh()
  queueRealtimeSessionsRefresh()
})

watch(realtimeToggleSeq, async () => {
  const action = String(realtimeLastToggleAction.value || '')
  if (action === 'enabled') {
    await refreshSessionsForSelectedAccount({ sourceOverride: 'realtime' })
    if (selectedContact.value?.username) {
      await refreshSelectedMessages()
    }
    return
  }
  if (action === 'disabled') {
    await refreshSessionsForSelectedAccount({ sourceOverride: '' })
    if (selectedContact.value?.username) {
      await refreshSelectedMessages()
    }
  }
})

watch(
  () => selectedContact.value?.username,
  (u) => {
    realtimeStore.setPriorityUsername(u || '')
  }
)

watch(messageTypeFilter, async (next, prev) => {
  if (String(next || '') === String(prev || '')) return
  if (!selectedContact.value?.username) return
  await refreshSelectedMessages()
})

watch(
  routeUsername,
  async () => {
    if (isLoadingContacts.value) return
    await applyRouteSelection()
  },
  { immediate: true }
)

watch(messageSearchScope, async () => {
  if (!messageSearchOpen.value) return
  ensureMessageSearchScopeValid()
  closeMessageSearchSenderDropdown()
  messageSearchSender.value = ''
  messageSearchSenderOptions.value = []
  messageSearchSenderOptionsKey.value = ''
  await fetchMessageSearchSenders()
  messageSearchOffset.value = 0
  messageSearchResults.value = []
  messageSearchSelectedIndex.value = -1
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true })
  }
})

watch(messageSearchRangeDays, async () => {
  if (!messageSearchOpen.value) return
  closeMessageSearchSenderDropdown()
  messageSearchOffset.value = 0
  messageSearchResults.value = []
  messageSearchSelectedIndex.value = -1
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true })
  }
})

watch(messageSearchSessionType, async () => {
  if (!messageSearchOpen.value) return
  if (String(messageSearchScope.value || '') !== 'global') return
  closeMessageSearchSenderDropdown()
  messageSearchSender.value = ''
  messageSearchSenderOptions.value = []
  messageSearchSenderOptionsKey.value = ''
  await fetchMessageSearchSenders()
  messageSearchOffset.value = 0
  messageSearchResults.value = []
  messageSearchSelectedIndex.value = -1
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true })
  }
})

watch([messageSearchStartDate, messageSearchEndDate], async () => {
  if (!messageSearchOpen.value) return
  if (String(messageSearchRangeDays.value || '') !== 'custom') return
  closeMessageSearchSenderDropdown()
  messageSearchOffset.value = 0
  messageSearchResults.value = []
  messageSearchSelectedIndex.value = -1
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true })
  }
})

watch(messageSearchSender, async () => {
  if (!messageSearchOpen.value) return
  messageSearchOffset.value = 0
  messageSearchResults.value = []
  messageSearchSelectedIndex.value = -1
  if (String(messageSearchQuery.value || '').trim()) {
    await runMessageSearch({ reset: true })
  }
})

watch(messageSearchQuery, () => {
  if (!messageSearchOpen.value) return
  if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
  messageSearchDebounceTimer = null
  const q = String(messageSearchQuery.value || '').trim()
  if (q.length < 2) return
  messageSearchDebounceTimer = setTimeout(() => {
    runMessageSearch({ reset: true })
  }, 280)
})

watch(
  () => selectedContact.value?.username,
  async () => {
    if (!messageSearchOpen.value) return
    if (String(messageSearchScope.value || '') !== 'conversation') return
    closeMessageSearchSenderDropdown()
    messageSearchSender.value = ''
    messageSearchSenderOptions.value = []
    messageSearchSenderOptionsKey.value = ''
    await fetchMessageSearchSenders()
    if (String(messageSearchQuery.value || '').trim()) {
      await runMessageSearch({ reset: true })
    }
  }
)

const autoLoadReady = ref(true)

let timeSidebarScrollSyncRaf = null
const syncTimeSidebarSelectedDateFromScroll = () => {
  if (!process.client) return
  if (!timeSidebarOpen.value) return
  if (!selectedContact.value) return

  const c = messageContainerRef.value
  if (!c) return

  if (timeSidebarScrollSyncRaf) return
  timeSidebarScrollSyncRaf = requestAnimationFrame(() => {
    timeSidebarScrollSyncRaf = null
    try {
      const containerRect = c.getBoundingClientRect()
      const targetY = containerRect.top + 24
      const els = c.querySelectorAll?.('[data-msg-id][data-create-time]') || []
      if (!els || !els.length) return

      let chosen = null
      for (const el of els) {
        const r = el.getBoundingClientRect?.()
        if (!r) continue
        if (r.bottom >= targetY) {
          chosen = el
          break
        }
      }
      if (!chosen) chosen = els[els.length - 1]
      const ts = Number(chosen?.getAttribute?.('data-create-time') || 0)
      const ds = _dateStrFromEpochSeconds(ts)
      if (!ds) return
      // Don't await inside rAF; keep scroll handler snappy.
      _applyTimeSidebarSelectedDate(ds, { syncMonth: true })
    } catch {}
  })
}

const contextAutoLoadTopReady = ref(true)
const contextAutoLoadBottomReady = ref(true)

const onMessageScrollInContextMode = async () => {
  const c = messageContainerRef.value
  if (!c) return
  if (!searchContext.value?.active) return

  const distBottom = c.scrollHeight - c.scrollTop - c.clientHeight

  // Reset "ready" gates when user scrolls away from edges.
  if (c.scrollTop > 160) contextAutoLoadTopReady.value = true
  if (distBottom > 160) contextAutoLoadBottomReady.value = true

  if (c.scrollTop <= 60 && contextAutoLoadTopReady.value && searchContext.value.hasMoreBefore && !searchContext.value.loadingBefore) {
    contextAutoLoadTopReady.value = false
    await loadMoreSearchContextBefore()
    return
  }

  if (distBottom <= 80 && contextAutoLoadBottomReady.value && searchContext.value.hasMoreAfter && !searchContext.value.loadingAfter) {
    contextAutoLoadBottomReady.value = false
    await loadMoreSearchContextAfter()
  }
}

const onMessageScroll = async () => {
  const c = messageContainerRef.value
  if (!c) return
  updateJumpToBottomState()
  if (!selectedContact.value) return

  // Keep the time sidebar selection in sync with the current viewport.
  syncTimeSidebarSelectedDateFromScroll()

  if (searchContext.value?.active) {
    await onMessageScrollInContextMode()
    return
  }

  if (c.scrollTop > 120) {
    autoLoadReady.value = true
    return
  }

  if (c.scrollTop <= 60 && autoLoadReady.value && hasMoreMessages.value && !isLoadingMessages.value) {
    autoLoadReady.value = false
    await loadMoreMessages()
  }
}

const LinkCard = defineComponent({
  name: 'LinkCard',
  props: {
    href: { type: String, default: '' },
    heading: { type: String, default: '' },
    abstract: { type: String, default: '' },
    preview: { type: String, default: '' },
    fromAvatar: { type: String, default: '' },
    from: { type: String, default: '' },
    linkType: { type: String, default: '' },
    isSent: { type: Boolean, default: false },
    badge: { type: String, default: '' },
    variant: { type: String, default: 'default' }
  },
  setup(props) {
    const fromAvatarImgOk = ref(false)
    const fromAvatarImgError = ref(false)
    const lastFromAvatarUrl = ref('')

    const getFromText = () => {
      const raw = String(props.from || '').trim()
      if (raw) return raw
      // Fallback: when the appmsg XML doesn't provide sourcedisplayname/appname,
      // show the host so the footer row still matches WeChat's fixed card layout.
      try {
        const href = String(props.href || '').trim()
        if (!/^https?:\/\//i.test(href)) return ''
        const host = new URL(href).hostname
        return String(host || '').trim()
      } catch {
        return ''
      }
    }

    return () => {
      const fromText = getFromText()
      const href = String(props.href || '').trim()
      const canNavigate = /^https?:\/\//i.test(href)
      const badgeText = String(props.badge || '').trim()
      // WeChat link cards show a small avatar next to the source text. We don't
      // always have a real image URL, so fall back to the first glyph.
      const fromAvatarText = (() => {
        const t = String(fromText || '').trim()
        return t ? (Array.from(t)[0] || '') : ''
      })()
      const fromAvatarUrl = String(props.fromAvatar || '').trim()
      const isMiniProgram = String(props.linkType || '').trim() === 'mini_program'
      const isCoverVariant = !isMiniProgram && String(props.variant || '').trim() === 'cover'
      const Tag = canNavigate ? 'a' : 'div'

      // Props may change when switching accounts/chats; reset load state per URL.
      if (fromAvatarUrl !== lastFromAvatarUrl.value) {
        lastFromAvatarUrl.value = fromAvatarUrl
        fromAvatarImgOk.value = false
        fromAvatarImgError.value = false
      }

      const showFromAvatarImg = Boolean(fromAvatarUrl) && !fromAvatarImgError.value
      const showFromAvatarText = (!fromAvatarUrl) || (!fromAvatarImgOk.value)
      const fromAvatarStyle = fromAvatarImgOk.value
        ? {
            background: isCoverVariant ? 'rgba(255, 255, 255, 0.92)' : '#fff',
            color: 'transparent'
          }
        : null
      const miniProgramAvatarStyle = fromAvatarImgOk.value
        ? {
            background: '#fff',
            color: 'transparent'
          }
        : null
      const onFromAvatarLoad = () => {
        fromAvatarImgOk.value = true
        fromAvatarImgError.value = false
      }
      const onFromAvatarError = () => {
        fromAvatarImgOk.value = false
        fromAvatarImgError.value = true
      }

      if (isCoverVariant) {
        const fromRow = h('div', { class: 'wechat-link-cover-from' }, [
          h('div', { class: 'wechat-link-cover-from-avatar', style: fromAvatarStyle, 'aria-hidden': 'true' }, [
            showFromAvatarText ? (fromAvatarText || '\u200B') : null,
            showFromAvatarImg ? h('img', {
              src: fromAvatarUrl,
              alt: '',
              class: 'wechat-link-cover-from-avatar-img',
              referrerpolicy: 'no-referrer',
              onLoad: onFromAvatarLoad,
              onError: onFromAvatarError
            }) : null
          ].filter(Boolean)),
          h('div', { class: 'wechat-link-cover-from-name', style: { flex: '1 1 auto', minWidth: '0' } }, fromText || '\u200B'),
          badgeText ? h('div', { class: 'wechat-link-cover-badge' }, badgeText) : null,
        ].filter(Boolean))

        return h(
          Tag,
          {
            ...(canNavigate ? { href, target: '_blank', rel: 'noreferrer' } : { role: 'group', 'aria-disabled': 'true' }),
            class: [
              'wechat-link-card-cover',
              !canNavigate ? 'wechat-link-card--disabled' : '',
              'wechat-special-card',
              'msg-radius',
              props.isSent ? 'wechat-special-sent-side' : ''
            ].filter(Boolean).join(' '),
            style: {
              width: '137px',
              minWidth: '137px',
              maxWidth: '137px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              flex: '0 0 auto',
              background: '#fff',
              border: 'none',
              boxShadow: 'none',
              textDecoration: 'none',
              outline: 'none'
            }
          },
          [
            props.preview ? h('div', { class: 'wechat-link-cover-image-wrap' }, [
              h('img', {
                src: props.preview,
                alt: props.heading || '链接封面',
                class: 'wechat-link-cover-image',
                referrerpolicy: 'no-referrer'
              }),
              fromRow,
            ]) : fromRow,
            h('div', { class: 'wechat-link-cover-title' }, props.heading || href)
          ].filter(Boolean)
        )
      }

      const headingText = String(props.heading || href || '').trim()
      let abstractText = String(props.abstract || '').trim()
      if (abstractText && headingText && abstractText === headingText) abstractText = ''

      if (isMiniProgram) {
        return h(
          Tag,
          {
            ...(canNavigate ? { href, target: '_blank', rel: 'noreferrer' } : { role: 'group', 'aria-disabled': 'true' }),
            class: [
              'wechat-link-card',
              'wechat-link-card--mini-program',
              !canNavigate ? 'wechat-link-card--disabled' : '',
              'wechat-special-card',
              'msg-radius',
              props.isSent ? 'wechat-special-sent-side' : ''
            ].filter(Boolean).join(' '),
            style: {
              width: '210px',
              minWidth: '210px',
              maxWidth: '210px',
              maxHeight: '270px',
              height: '270px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              flex: '0 0 auto',
              background: '#fff',
              border: 'none',
              boxShadow: 'none',
              textDecoration: 'none',
              outline: 'none'
            }
          },
          [
            h('div', { class: 'wechat-link-mini-body' }, [
              h('div', { class: 'wechat-link-mini-header' }, [
                h('div', { class: 'wechat-link-mini-header-avatar', style: miniProgramAvatarStyle, 'aria-hidden': 'true' }, [
                  showFromAvatarText ? (fromAvatarText || '\u200B') : null,
                  showFromAvatarImg ? h('img', {
                    src: fromAvatarUrl,
                    alt: '',
                    class: 'wechat-link-mini-header-avatar-img',
                    referrerpolicy: 'no-referrer',
                    onLoad: onFromAvatarLoad,
                    onError: onFromAvatarError
                  }) : null
                ].filter(Boolean)),
                h('div', { class: 'wechat-link-mini-header-name' }, fromText || '\u200B')
              ]),
              h('div', { class: 'wechat-link-mini-title' }, headingText || abstractText || href),
              h('div', { class: ['wechat-link-mini-preview', !props.preview ? 'wechat-link-mini-preview--empty' : ''].filter(Boolean).join(' ') }, [
                props.preview ? h('img', {
                  src: props.preview,
                  alt: props.heading || '小程序预览',
                  class: 'wechat-link-mini-preview-img',
                  referrerpolicy: 'no-referrer'
                }) : null
              ].filter(Boolean))
            ]),
            h('div', { class: 'wechat-link-mini-footer' }, [
              h('img', {
                src: miniProgramIconUrl,
                alt: '',
                class: 'wechat-link-mini-footer-icon',
                'aria-hidden': 'true'
              }),
              h('span', { class: 'wechat-link-mini-footer-text' }, '小程序')
            ])
          ]
        )
      }

      return h(
        Tag,
        {
          ...(canNavigate ? { href, target: '_blank', rel: 'noreferrer' } : { role: 'group', 'aria-disabled': 'true' }),
          class: [
            'wechat-link-card',
            !canNavigate ? 'wechat-link-card--disabled' : '',
            'wechat-special-card',
            'msg-radius',
            props.isSent ? 'wechat-special-sent-side' : ''
          ].filter(Boolean).join(' '),
          // Inline size is intentional: LinkCard is a local component rendered via `h()` and
          // does not inherit the SFC scoped CSS attribute, so relying on scoped CSS for exact
          // sizing is fragile. Keep width in sync with the WeChat desktop card size.
          style: {
            width: '210px',
            minWidth: '210px',
            maxWidth: '210px',
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            flex: '0 0 auto',
            background: '#fff',
            border: 'none',
            boxShadow: 'none',
            textDecoration: 'none',
            outline: 'none'
          }
        },
        [
          h('div', { class: 'wechat-link-content' }, [
            h('div', { class: 'wechat-link-title' }, headingText || href),
            (abstractText || props.preview)
              ? h('div', { class: 'wechat-link-summary' }, [
                abstractText ? h('div', { class: 'wechat-link-desc' }, abstractText) : null,
                props.preview ? h('div', { class: 'wechat-link-thumb' }, [
                  h('img', { src: props.preview, alt: props.heading || '链接预览', class: 'wechat-link-thumb-img', referrerpolicy: 'no-referrer' })
                ]) : null
              ].filter(Boolean))
              : null
          ].filter(Boolean)),
          h('div', { class: 'wechat-link-from' }, [
            h('div', { class: 'wechat-link-from-avatar', style: fromAvatarStyle, 'aria-hidden': 'true' }, [
              showFromAvatarText ? (fromAvatarText || '\u200B') : null,
              showFromAvatarImg ? h('img', {
                src: fromAvatarUrl,
                alt: '',
                class: 'wechat-link-from-avatar-img',
                referrerpolicy: 'no-referrer',
                onLoad: onFromAvatarLoad,
                onError: onFromAvatarError
              }) : null
            ].filter(Boolean)),
            h('div', { class: 'wechat-link-from-name', style: { flex: '1 1 auto', minWidth: '0' } }, fromText || '\u200B'),
            badgeText ? h('div', { class: 'wechat-link-badge' }, badgeText) : null
          ].filter(Boolean))
        ].filter(Boolean)
      )
    }
  }
})

</script>

<style scoped>
/* LinkCard：小程序标记与无 URL 降级 */
::deep(.wechat-link-badge) {
  margin-left: auto;
  padding-left: 8px;
  font-size: 11px;
  color: #b2b2b2;
  white-space: nowrap;
  flex-shrink: 0;
}

::deep(.wechat-link-cover-badge) {
  margin-left: auto;
  padding-left: 8px;
  font-size: 11px;
  color: rgba(243, 243, 243, 0.92);
  white-space: nowrap;
  flex-shrink: 0;
}

::deep(.wechat-link-card.wechat-link-card--disabled),
::deep(.wechat-link-card-cover.wechat-link-card--disabled) {
  cursor: default;
}

::deep(.wechat-link-card.wechat-link-card--disabled:hover),
::deep(.wechat-link-card-cover.wechat-link-card--disabled:hover) {
  background: #fff;
}

/* 滚动条样式 */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #a1a1a1;
}

/* 会话列表宽度：按物理像素(px)配置，按 dpr 换算为 CSS px */
.session-list-panel {
  width: calc(var(--session-list-width, 295px) / var(--dpr));
}

/* 会话列表拖动条（中间栏右侧） */
.session-list-resizer {
  position: absolute;
  top: 0;
  right: -3px; /* 覆盖在 border 上，便于拖动 */
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 50;
}

.session-list-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 2px;
  width: 2px;
  background: transparent;
  transition: background-color 0.15s ease;
}

.session-list-resizer:hover::after,
.session-list-resizer-active::after {
  background: rgba(0, 0, 0, 0.12);
}

/* 消息气泡样式 */
.message-bubble {
  border-radius: var(--message-radius);
  position: relative;
  z-index: 1;
}

/* 发送的消息（右侧绿色气泡） */
.sent-message {
  background-color: #95EB69 !important;
  border-radius: var(--message-radius);
}

.sent-message::after {
  content: '';
  position: absolute;
  top: 50%;
  right: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background-color: #95EB69;
  border-radius: 2px;
}

/* 接收的消息（左侧白色气泡） */
.received-message {
  background-color: white !important;
  border-radius: var(--message-radius);
}

.received-message::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background-color: white;
  border-radius: 2px;
}

/* 聊天标签页样式 */
.chat-tab {
  cursor: pointer;
  transition: all 0.2s ease;
  color: #606060;
}

.chat-tab:hover:not(.selected) {
  background-color: #E5E5E5;
}

.chat-tab.selected {
  color: #07b75b !important;
}

.chat-tab:not(.selected):hover {
  color: #07b75b;
}

/* 语音消息样式 */
.voice-message-wrap {
  display: flex;
  width: 100%;
}

.voice-bubble {
  border-radius: var(--message-radius);
  position: relative;
  transition: opacity 0.15s ease;
}

.voice-bubble:hover {
  opacity: 0.85;
}

.voice-bubble:active {
  opacity: 0.7;
}

.voice-sent {
  border-radius: var(--message-radius);
}

.voice-sent::after {
  content: '';
  position: absolute;
  top: 50%;
  right: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background-color: #95EC69;
  border-radius: 2px;
}

.voice-received {
  border-radius: var(--message-radius);
}

.voice-received::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background-color: white;
  border-radius: 2px;
}

/* 语音消息样式 - 微信风格 */
.wechat-voice-wrapper {
  display: flex;
  width: 100%;
  position: relative;
}

.wechat-voice-bubble {
  border-radius: var(--message-radius);
  position: relative;
  transition: opacity 0.15s ease;
  min-width: 80px;
  max-width: 200px;
}

.wechat-voice-bubble:hover {
  opacity: 0.85;
}

.wechat-voice-bubble:active {
  opacity: 0.7;
}

.wechat-voice-sent {
  background: #95EC69;
}

.wechat-voice-sent::after {
  content: '';
  position: absolute;
  top: 50%;
  right: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background: #95EC69;
  border-radius: 2px;
}

.wechat-voice-received {
  background: white;
}

.wechat-voice-received::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background: white;
  border-radius: 2px;
}

.wechat-voice-content {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  gap: 8px;
}

/* 语音图标样式 */
.wechat-voice-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: #1a1a1a;
}

.wechat-quote-voice-icon {
  width: 14px;
  height: 14px;
  color: inherit;
}

.voice-icon-sent {
  transform: scaleX(-1);
}

/* 播放时的波动动画 */
.wechat-voice-icon.voice-playing .voice-wave-2 {
  animation: voice-wave-2 1s infinite;
}

.wechat-voice-icon.voice-playing .voice-wave-3 {
  animation: voice-wave-3 1s infinite;
}

@keyframes voice-wave-2 {
  0%, 33% { opacity: 0; }
  34%, 100% { opacity: 1; }
}

@keyframes voice-wave-3 {
  0%, 66% { opacity: 0; }
  67%, 100% { opacity: 1; }
}

.wechat-voice-duration {
  font-size: 14px;
  color: #1a1a1a;
}

.wechat-voice-unread {
  position: absolute;
  top: 50%;
  right: -20px;
  transform: translateY(-50%);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e75e58;
}

/* 音视频通话消息样式 - 微信风格 */
.wechat-voip-bubble {
  border-radius: var(--message-radius);
  position: relative;
  min-width: 120px;
}

.wechat-voip-sent {
  background: #95EC69;
}

.wechat-voip-sent::after {
  content: '';
  position: absolute;
  top: 50%;
  right: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background: #95EC69;
  border-radius: 2px;
}

.wechat-voip-received {
  background: white;
}

.wechat-voip-received::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background: white;
  border-radius: 2px;
}

.wechat-voip-content {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  gap: 8px;
}

.wechat-voip-icon {
  width: 22px;
  height: 14px;
  flex-shrink: 0;
  object-fit: contain;
}

.wechat-voip-text {
  font-size: 14px;
  color: #1a1a1a;
}

/* 统一特殊消息尾巴（红包 / 文件等） */
:deep(.wechat-special-card) {
  position: relative;
  overflow: visible;
}

:deep(.wechat-special-card)::after {
  content: '';
  position: absolute;
  top: 12px;
  left: -4px;
  width: 12px;
  height: 12px;
  background-color: inherit;
  transform: rotate(45deg);
  border-radius: 2px;
}

:deep(.wechat-special-sent-side)::after {
  left: auto;
  right: -4px;
}

.wechat-chat-history-card {
  width: 210px;
  background: #ffffff;
  border-radius: var(--message-radius);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.wechat-chat-history-card:hover {
  background: #f5f5f5;
}

.wechat-chat-history-body {
  padding: 10px 12px;
}

.wechat-chat-history-title {
  font-size: 14px;
  font-weight: 400;
  color: #161616;
  margin-bottom: 6px;
}

.wechat-chat-history-preview {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.4;
}

.wechat-chat-history-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wechat-chat-history-bottom {
  height: 27px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-top: none;
  position: relative;
}

.wechat-chat-history-bottom::before {
  content: '';
  position: absolute;
  top: 0;
  left: 13px;
  right: 13px;
  height: 1.5px;
  background: #e8e8e8;
}

.wechat-chat-history-bottom span {
  font-size: 12px;
  color: #b2b2b2;
}

/* 转账消息样式 - 微信风格 */
.wechat-transfer-card {
  width: 210px;
  background: #f79c46;
  border-radius: var(--message-radius);
  overflow: visible;
  position: relative;
}

.wechat-transfer-card::after {
  content: '';
  position: absolute;
  top: 16px;
  left: -4px;
  width: 10px;
  height: 10px;
  background: #f79c46;
  transform: rotate(45deg);
  border-radius: 2px;
}

.wechat-transfer-sent-side::after {
  left: auto;
  right: -4px;
}

.wechat-transfer-content {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  min-height: 58px;
}

.wechat-transfer-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  object-fit: contain;
}

.wechat-transfer-info {
  flex: 1;
  margin-left: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wechat-transfer-amount {
  font-size: 16px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wechat-transfer-status {
  font-size: 12px;
  color: #fff;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wechat-transfer-bottom {
  height: 27px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-top: none;
  position: relative;
}

.wechat-transfer-bottom::before {
  content: '';
  position: absolute;
  top: 0;
  left: 13px;
  right: 13px;
  height: 1px;
  background: rgba(255,255,255,0.2);
}

.wechat-transfer-bottom span {
  font-size: 11px;
  color: #fff;
}

/* 已领取的转账样式 */
.wechat-transfer-received {
  background: #FDCE9D;
}

.wechat-transfer-received::after {
  background: #FDCE9D;
}

.wechat-transfer-received .wechat-transfer-amount,
.wechat-transfer-received .wechat-transfer-status {
  color: #fff;
}

.wechat-transfer-received .wechat-transfer-bottom span {
  color: #fff;
}

/* 退回的转账样式 */
.wechat-transfer-returned {
  background: #fde1c3;
}

.wechat-transfer-returned::after {
  background: #fde1c3;
}

.wechat-transfer-returned .wechat-transfer-amount,
.wechat-transfer-returned .wechat-transfer-status {
  color: #fff;
}

.wechat-transfer-returned .wechat-transfer-bottom span {
  color: #fff;
}

/* 过期的转账样式 */
.wechat-transfer-overdue {
  background: #E9CFB3;
}

.wechat-transfer-overdue::after {
  background: #E9CFB3;
}

.wechat-transfer-overdue .wechat-transfer-amount,
.wechat-transfer-overdue .wechat-transfer-status {
  color: #fff;
}

.wechat-transfer-overdue .wechat-transfer-bottom span {
  color: #fff;
}

/* 红包消息样式 - 微信风格 */
.wechat-redpacket-card {
  width: 210px;
  background: #fa9d3b;
  border-radius: var(--message-radius);
  overflow: visible;
  position: relative;
}

.wechat-redpacket-content {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  min-height: 58px;
}

.wechat-redpacket-icon {
  width: 32px;
  height: 36px;
  flex-shrink: 0;
  object-fit: contain;
}

.wechat-redpacket-info {
  flex: 1;
  margin-left: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wechat-redpacket-text {
  font-size: 14px;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wechat-redpacket-status {
  font-size: 12px;
  color: #fff;
  margin-top: 2px;
}

.wechat-redpacket-bottom {
  height: 27px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-top: none;
  position: relative;
}

.wechat-redpacket-bottom::before {
  content: '';
  position: absolute;
  top: 0;
  left: 13px;
  right: 13px;
  height: 1px;
  background: rgba(255,255,255,0.2);
}

.wechat-redpacket-bottom span {
  font-size: 11px;
  color: #faecda;
}

/* 已领取的红包样式 */
.wechat-redpacket-received {
  background: #f8e2c6;
}

.wechat-redpacket-received .wechat-redpacket-text,
.wechat-redpacket-received .wechat-redpacket-status {
  color: #b88550;
}

.wechat-redpacket-received .wechat-redpacket-bottom span {
  color: #c9a67a;
}

/* 文件消息样式 - 基于红包样式覆盖 */
.wechat-file-card {
  width: 210px;
  background: #fff;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.wechat-file-card .wechat-redpacket-content {
  padding: 10px 12px;
  min-height: 58px;
}

.wechat-file-card .wechat-redpacket-bottom {
  height: 27px;
  padding: 0 12px;
  border-top: none;
  position: relative;
}

.wechat-file-card .wechat-redpacket-bottom::before {
  content: '';
  position: absolute;
  top: 0;
  left: 13px;
  right: 13px;
  height: 1.5px;
  background: #e8e8e8;
}

.wechat-file-card:hover {
  background: #f5f5f5;
}

.wechat-file-card .wechat-file-info {
  margin-left: 0;
  margin-right: 10px;
}

.wechat-file-name {
  font-size: 14px;
  color: #1a1a1a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
  line-height: 1.4;
}

.wechat-file-size {
  font-size: 12px;
  color: #b2b2b2;
  margin-top: 4px;
}

.wechat-file-icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  object-fit: contain;
}

.wechat-file-bottom {
  border-top: 1px solid #e8e8e8;
}

.wechat-file-bottom span {
  font-size: 12px;
  color: #b2b2b2;
}

.wechat-file-logo {
  width: 18px;
  height: 18px;
  object-fit: contain;
  margin-right: 4px;
}

/* 链接消息样式 - 微信风格 */
:deep(.wechat-link-card) {
  width: 210px;
  min-width: 210px;
  max-width: 210px;
  background: #fff;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  border: none;
  box-shadow: none;
  outline: none;
  cursor: pointer;
  text-decoration: none;
  transition: background-color 0.15s ease;
}

:deep(.wechat-link-card:hover) {
  background: #f5f5f5;
}

:deep(.wechat-link-content) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-sizing: border-box;
  padding: 10px 10px 8px;
  flex: 1 1 auto;
}

:deep(.wechat-link-summary) {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 42px;
}

:deep(.wechat-link-title) {
  font-size: 14px;
  color: #1a1a1a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
  word-break: break-word;
}

:deep(.wechat-link-desc) {
  font-size: 12px;
  color: #8c8c8c;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
  word-break: break-word;
  flex: 1 1 auto;
  min-width: 0;
}

:deep(.wechat-link-thumb) {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  border-radius: 0;
  overflow: hidden;
  background: #f2f2f2;
  align-self: flex-start;
}

:deep(.wechat-link-thumb-img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

:deep(.wechat-link-card--mini-program) {
  max-height: 270px;
  height: 270px;
}

:deep(.wechat-link-mini-body) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  box-sizing: border-box;
  flex: 1 1 auto;
  min-height: 0;
}

:deep(.wechat-link-mini-header) {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

:deep(.wechat-link-mini-header-avatar) {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #14c15f;
  color: #fff;
  font-size: 11px;
  line-height: 20px;
  text-align: center;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

:deep(.wechat-link-mini-header-avatar-img) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

:deep(.wechat-link-mini-header-name) {
  font-size: 13px;
  color: #7d7d7d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1 1 auto;
}

:deep(.wechat-link-mini-title) {
  font-size: 13px;
  line-height: 1.45;
  color: #1a1a1a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

:deep(.wechat-link-mini-preview) {
  width: 100%;
  height: auto;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
  background: #f2f2f2;
  margin-top: auto;
}

:deep(.wechat-link-mini-preview--empty) {
  background: #f7f7f7;
}

:deep(.wechat-link-mini-preview-img) {
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
  display: block;
}

:deep(.wechat-link-mini-footer) {
  height: 23px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  box-sizing: border-box;
  position: relative;
  flex-shrink: 0;
}

:deep(.wechat-link-mini-footer)::before {
  content: '';
  position: absolute;
  top: 0;
  left: 12px;
  right: 12px;
  height: 1px;
  background: #e8e8e8;
}

:deep(.wechat-link-mini-footer-icon) {
  width: 12px;
  height: 12px;
  object-fit: contain;
  flex-shrink: 0;
}

:deep(.wechat-link-mini-footer-text) {
  font-size: 10px;
  color: #8c8c8c;
}

:deep(.wechat-link-from) {
  height: 30px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  position: relative;
  flex-shrink: 0;
}

:deep(.wechat-link-from)::before {
  content: '';
  position: absolute;
  top: 0;
  left: 11px;
  right: 11px;
  height: 1.5px;
  background: #e8e8e8;
}

:deep(.wechat-link-from-avatar) {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #111;
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

:deep(.wechat-link-from-avatar-img) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

:deep(.wechat-link-from-name) {
  font-size: 12px;
  color: #b2b2b2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 链接封面卡片（170x230 图 + 60 底栏） */
:deep(.wechat-link-card-cover) {
  width: 137px;
  min-width: 137px;
  max-width: 137px;
  background: #fff;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  border: none;
  box-shadow: none;
  outline: none;
  cursor: pointer;
  text-decoration: none;
  transition: background-color 0.15s ease;
}

:deep(.wechat-link-card-cover:hover) {
  background: #f5f5f5;
}

:deep(.wechat-link-cover-image-wrap) {
  width: 137px;
  height: 180px;
  position: relative;
  overflow: hidden;
  border-radius: 4px 4px 0 0;
  background: #f2f2f2;
  flex-shrink: 0;
}

:deep(.wechat-link-cover-image) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
}

/* 仅公众号封面卡片去掉菱形尖角，其它消息保持原样 */
:deep(.wechat-link-card-cover.wechat-special-card)::after {
  content: none !important;
}

:deep(.wechat-link-cover-from) {
  height: 30px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  box-sizing: border-box;
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background: transparent;
  flex-shrink: 0;
}

:deep(.wechat-link-cover-from-avatar) {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #111;
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

:deep(.wechat-link-cover-from-avatar-img) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

:deep(.wechat-link-cover-from-name) {
  font-size: 12px;
  color: #f3f3f3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.wechat-link-cover-title) {
  height: 50px;
  padding: 7px 10px 0;
  box-sizing: border-box;
  font-size: 12px;
  line-height: 1.24;
  color: #1a1a1a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  flex-shrink: 0;
}

/* 隐私模式模糊效果 */
.privacy-blur {
  filter: blur(9px);
  transition: filter 0.2s ease;
}

.privacy-blur:hover {
  filter: none;
}

/* 定位引用消息的高亮效果 */
.message-locate-highlight {
  position: relative;
  animation: locate-pulse 1.8s ease-out;
}

.message-locate-highlight::before {
  content: '';
  position: absolute;
  inset: -4px -8px;
  border-radius: 8px;
  background: rgba(3, 193, 96, 0.12);
  pointer-events: none;
  animation: locate-fade 1.8s ease-out forwards;
}

@keyframes locate-pulse {
  0% {
    transform: scale(1.02);
  }
  15% {
    transform: scale(1);
  }
  100% {
    transform: scale(1);
  }
}

@keyframes locate-fade {
  0% {
    opacity: 1;
    background: rgba(3, 193, 96, 0.15);
  }
  70% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

/* 骨架屏加载动画 */
.skeleton-pulse {
  animation: skeleton-loading 1.5s ease-in-out infinite;
}

@keyframes skeleton-loading {
  0% {
    opacity: 0.6;
  }
  50% {
    opacity: 0.3;
  }
  100% {
    opacity: 0.6;
  }
}
</style>
