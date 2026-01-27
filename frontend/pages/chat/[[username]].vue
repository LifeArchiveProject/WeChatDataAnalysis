<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- 左侧边栏 -->
    <div class="border-r border-gray-200 flex flex-col" style="background-color: #e8e7e7; width: 60px; min-width: 60px; max-width: 60px">
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
        
        <!-- 隐私模式按钮 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          @click="privacyMode = !privacyMode"
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

        <!-- 设置按钮（仅桌面端） -->
        <div
          v-if="isDesktopEnv"
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          @click="openDesktopSettings"
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
    <div class="w-80 border-r border-gray-200 flex flex-col min-h-0" style="background-color: #F7F7F7">
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
            <div v-for="i in 15" :key="i" class="flex items-center space-x-3 py-2">
              <div class="w-10 h-10 rounded-md bg-gray-200 skeleton-pulse"></div>
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
              class="px-3 py-2 cursor-pointer transition-colors duration-150 border-b border-gray-100"
              :class="selectedContact?.id === contact.id ? 'bg-[#DEDEDE] hover:bg-[#d3d3d3]' : 'hover:bg-[#eaeaea]'"
              @click="selectContact(contact)">
              <div class="flex items-center space-x-3">
                <!-- 联系人头像 -->
                <div class="w-10 h-10 rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                  <div v-if="contact.avatar" class="w-full h-full">
                    <img :src="contact.avatar" :alt="contact.name" class="w-full h-full object-cover">
                  </div>
                  <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                    :style="{ backgroundColor: contact.avatarColor || '#4B5563' }">
                    {{ contact.name.charAt(0) }}
                  </div>
                </div>
                
                <!-- 联系人信息 -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-medium text-gray-900 truncate" :class="{ 'privacy-blur': privacyMode }">{{ contact.name }}</h3>
                    <div class="flex items-center flex-shrink-0 ml-2">
                      <span v-if="contact.unreadCount > 0" class="text-[10px] text-white bg-red-500 rounded-full min-w-[18px] h-[18px] px-1 flex items-center justify-center mr-2">
                        {{ contact.unreadCount > 99 ? '99+' : contact.unreadCount }}
                      </span>
                      <span class="text-xs text-gray-500">{{ contact.lastMessageTime }}</span>
                    </div>
                  </div>
                  <p class="text-xs text-gray-500 truncate mt-0.5 leading-tight" :class="{ 'privacy-blur': privacyMode }">{{ contact.lastMessage }}</p>
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
      <!-- 桌面端将自绘标题栏放到右侧区域，避免遮挡左侧栏（更接近原生微信布局） -->
      <DesktopTitleBar />
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
                class="header-btn"
                @click="refreshSelectedMessages"
                :disabled="isLoadingMessages"
                title="刷新消息"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
                <span>刷新</span>
              </button>
              <button
                class="header-btn"
                :class="realtimeEnabled ? 'bg-emerald-100 border-emerald-200' : ''"
                @click="toggleRealtime"
                :disabled="realtimeChecking"
                :title="realtimeEnabled ? '关闭实时更新' : (realtimeAvailable ? '开启实时更新' : (realtimeStatusError || '实时模式不可用'))"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>{{ realtimeEnabled ? '实时开' : '实时关' }}</span>
              </button>
              <button
                class="header-btn"
                @click="openExportModal"
                :disabled="isExportCreating"
                title="导出聊天记录"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                <span>导出</span>
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
            </div>
          </div>

          <div v-if="searchContext.active" class="px-6 py-2 border-b border-emerald-200 bg-emerald-50 flex items-center gap-3">
            <div class="text-sm text-emerald-900">
              已定位到搜索结果（上下文模式）
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
                <div class="w-[36px] h-[36px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="[message.isSent ? 'ml-3' : 'mr-3', { 'privacy-blur': privacyMode }]">
                  <div v-if="message.avatar" class="w-full h-full">
                    <img
                      :src="message.avatar"
                      :alt="message.sender + '的头像'"
                      class="w-full h-full object-cover"
                      referrerpolicy="no-referrer"
                      @error="onMessageAvatarError($event, message)"
                    >
                  </div>
                  <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                    :style="{ backgroundColor: message.avatarColor || (message.isSent ? '#4B5563' : '#6B7280') }">
                    {{ message.sender.charAt(0) }}
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
                    :isSent="message.isSent"
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
                      <a
                        v-if="message.videoThumbUrl && message.videoUrl"
                        :href="message.videoUrl"
                        target="_blank"
                        rel="noreferrer"
                        class="absolute inset-0 flex items-center justify-center"
                      >
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </a>
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
                      class="mt-[5px] px-2 text-xs text-neutral-600 rounded max-w-[404px] max-h-[61px] flex items-center bg-[#e1e1e1]">
                      <div class="py-2 min-w-0 w-full">
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
                        <div v-else class="line-clamp-2">{{ message.quoteTitle ? (message.quoteTitle + ': ') : '' }}{{ message.quoteContent }}</div>
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
                    :class="[{ 'wechat-transfer-received': message.transferReceived, 'wechat-transfer-returned': isTransferReturned(message) }, message.isSent ? 'wechat-transfer-sent-side' : 'wechat-transfer-received-side']">
                    <div class="wechat-transfer-content">
                      <img src="/assets/images/wechat/wechat-returned.png" v-if="isTransferReturned(message)" class="wechat-transfer-icon" alt="">
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
      class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center cursor-zoom-out"
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

    <!-- 合并转发聊天记录弹窗 -->
    <div
      v-if="chatHistoryModalVisible"
      class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      @click="closeChatHistoryModal"
    >
      <div
        class="w-[92vw] max-w-[560px] max-h-[80vh] bg-white rounded-xl shadow-xl overflow-hidden flex flex-col"
        @click.stop
      >
        <div class="px-4 py-3 bg-neutral-100 border-b border-gray-200 flex items-center justify-between">
          <div class="text-sm text-[#161616] truncate">{{ chatHistoryModalTitle || '聊天记录' }}</div>
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

        <div class="flex-1 overflow-auto bg-white">
          <div v-if="!chatHistoryModalRecords.length" class="text-sm text-gray-500 text-center py-10">
            没有可显示的聊天记录
          </div>
          <template v-else>
            <div
              v-for="(rec, idx) in chatHistoryModalRecords"
              :key="rec.id || idx"
              class="px-4 py-3 flex gap-3 border-b border-gray-100"
            >
              <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="rec.senderAvatar"
                  :src="rec.senderAvatar"
                  alt="头像"
                  class="w-full h-full object-cover"
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
                  <!-- 视频 -->
                  <div
                    v-if="rec.renderType === 'video'"
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

                    <a
                      v-if="rec.videoThumbUrl && rec.videoUrl"
                      :href="rec.videoUrl"
                      target="_blank"
                      rel="noreferrer"
                      class="absolute inset-0 flex items-center justify-center"
                    >
                      <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    </a>
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
      class="fixed z-50 bg-white border border-gray-200 rounded-md shadow-lg text-sm"
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
    </div>

    <!-- 导出弹窗 -->
    <div v-if="exportModalOpen" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeExportModal"></div>
      <div class="relative w-[780px] max-w-[92vw] bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">导出聊天记录（离线 ZIP）</div>
          <button class="ml-auto text-gray-400 hover:text-gray-700" type="button" @click="closeExportModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-4">
          <div v-if="exportError" class="text-sm text-red-600 whitespace-pre-wrap">{{ exportError }}</div>
          <div v-if="privacyMode" class="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-md px-3 py-2">
            已开启隐私模式：导出将隐藏会话/用户名/内容，并且不会打包头像与媒体。
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div class="text-sm font-medium text-gray-800 mb-2">范围</div>
              <div class="space-y-2 text-sm text-gray-700">
                <label class="flex items-center gap-2">
                  <input type="radio" value="current" v-model="exportScope" />
                  <span>当前会话</span>
                </label>
                <label class="flex items-center gap-2">
                  <input type="radio" value="selected" v-model="exportScope" />
                  <span>选择会话（批量）</span>
                </label>
                <label class="flex items-center gap-2">
                  <input type="radio" value="all" v-model="exportScope" />
                  <span>全部会话</span>
                </label>
                <label class="flex items-center gap-2">
                  <input type="radio" value="groups" v-model="exportScope" />
                  <span>仅群聊</span>
                </label>
                <label class="flex items-center gap-2">
                  <input type="radio" value="singles" v-model="exportScope" />
                  <span>仅单聊</span>
                </label>
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
                      <img v-if="c.avatar" :src="c.avatar" :alt="c.name + '头像'" class="w-full h-full object-cover" />
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
            </div>

            <div class="space-y-4">
              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">格式</div>
                <div class="flex items-center gap-4 text-sm text-gray-700">
                  <label class="flex items-center gap-2">
                    <input type="radio" value="json" v-model="exportFormat" />
                    <span>JSON</span>
                  </label>
                  <label class="flex items-center gap-2">
                    <input type="radio" value="txt" v-model="exportFormat" />
                    <span>TXT</span>
                  </label>
                </div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">时间范围（可选）</div>
                <div class="grid grid-cols-2 gap-2">
                  <input
                    v-model="exportStartLocal"
                    type="datetime-local"
                    class="px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                  <input
                    v-model="exportEndLocal"
                    type="datetime-local"
                    class="px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                </div>
                <div class="flex items-center gap-2 mt-2">
                  <button type="button" class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50" @click="exportStartLocal=''; exportEndLocal=''">全部</button>
                  <button type="button" class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50" @click="applyExportQuickRangeDays(7)">最近7天</button>
                  <button type="button" class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50" @click="applyExportQuickRangeDays(30)">最近30天</button>
                </div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">消息类型（导出内容）</div>
                <div class="space-y-2 text-sm text-gray-700">
                  <label class="flex items-center gap-2">
                    <input type="radio" value="all" v-model="exportMessageTypeMode" />
                    <span>全部消息（不筛选）</span>
                  </label>
                  <label class="flex items-center gap-2">
                    <input type="radio" value="filter" v-model="exportMessageTypeMode" />
                    <span>按类型筛选（可多选）</span>
                  </label>
                </div>
                <div v-if="exportMessageTypeMode === 'filter'" class="mt-2">
                  <div class="flex items-center gap-2 mb-2">
                    <button
                      type="button"
                      class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50"
                      @click="exportMessageTypes = exportMessageTypeOptions.map((x) => x.value)"
                    >
                      全选
                    </button>
                    <button
                      type="button"
                      class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50"
                      @click="exportMessageTypes = ['voice']"
                    >
                      只语音
                    </button>
                    <button
                      type="button"
                      class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50"
                      @click="exportMessageTypes = ['transfer']"
                    >
                      只转账
                    </button>
                    <button
                      type="button"
                      class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50"
                      @click="exportMessageTypes = ['redPacket']"
                    >
                      只红包
                    </button>
                    <div class="ml-auto text-xs text-gray-500">已选 {{ exportMessageTypes.length }} 项</div>
                  </div>
                  <div class="grid grid-cols-2 gap-2 text-sm text-gray-700">
                    <label v-for="opt in exportMessageTypeOptions" :key="opt.value" class="flex items-center gap-2">
                      <input type="checkbox" :value="opt.value" v-model="exportMessageTypes" />
                      <span>{{ opt.label }}</span>
                    </label>
                  </div>
                  <div class="mt-1 text-xs text-gray-500">
                    仅导出所选类型的消息（影响导出消息条数与进度统计）。
                  </div>
                </div>
                <div v-else class="mt-1 text-xs text-gray-500">
                  默认导出会话内全部消息；如需只导出语音/转账/红包等，请选择“按类型筛选”。
                </div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">离线媒体文件（可选）</div>
                <label class="flex items-center gap-2 text-sm text-gray-700">
                  <input type="checkbox" v-model="exportIncludeMedia" :disabled="privacyMode" />
                  <span>打包媒体文件到 ZIP（图片/表情/视频/语音/文件）</span>
                </label>
                <div class="mt-1 text-xs text-gray-500">
                  仅影响 ZIP 是否包含媒体文件；消息条数由“消息类型（导出内容）”决定。
                </div>
                <div class="grid grid-cols-2 gap-2 mt-2 text-sm text-gray-700">
                  <label class="flex items-center gap-2" :class="(exportIncludeMedia && !privacyMode) ? '' : 'opacity-50'">
                    <input type="checkbox" value="image" v-model="exportMediaKinds" :disabled="!exportIncludeMedia || privacyMode" />
                    <span>图片</span>
                  </label>
                  <label class="flex items-center gap-2" :class="(exportIncludeMedia && !privacyMode) ? '' : 'opacity-50'">
                    <input type="checkbox" value="emoji" v-model="exportMediaKinds" :disabled="!exportIncludeMedia || privacyMode" />
                    <span>表情</span>
                  </label>
                  <label class="flex items-center gap-2" :class="(exportIncludeMedia && !privacyMode) ? '' : 'opacity-50'">
                    <input type="checkbox" value="video" v-model="exportMediaKinds" :disabled="!exportIncludeMedia || privacyMode" />
                    <span>视频</span>
                  </label>
                  <label class="flex items-center gap-2" :class="(exportIncludeMedia && !privacyMode) ? '' : 'opacity-50'">
                    <input type="checkbox" value="voice" v-model="exportMediaKinds" :disabled="!exportIncludeMedia || privacyMode" />
                    <span>语音</span>
                  </label>
                  <label class="flex items-center gap-2" :class="(exportIncludeMedia && !privacyMode) ? '' : 'opacity-50'">
                    <input type="checkbox" value="file" v-model="exportMediaKinds" :disabled="!exportIncludeMedia || privacyMode" />
                    <span>文件</span>
                  </label>
                  <label class="flex items-center gap-2" :class="(exportIncludeMedia && !privacyMode) ? '' : 'opacity-50'">
                    <input type="checkbox" value="video_thumb" v-model="exportMediaKinds" :disabled="!exportIncludeMedia || privacyMode" />
                    <span>视频缩略图</span>
                  </label>
                </div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">文件名（可选）</div>
                <input
                  v-model="exportFileName"
                  type="text"
                  placeholder="例如：我的微信导出_2025-12-23.zip"
                  class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                />
                <div class="mt-1 text-xs text-gray-500">不填则自动生成（输出位置：output/exports/{账号}/）。</div>
              </div>

              <div class="space-y-2">
                <label class="flex items-center gap-2 text-sm text-gray-700">
                  <input type="checkbox" v-model="exportIncludeHidden" />
                  <span>包含隐藏会话（仅对“全部/群/单”有效）</span>
                </label>
                <label class="flex items-center gap-2 text-sm text-gray-700">
                  <input type="checkbox" v-model="exportIncludeOfficial" />
                  <span>包含公众号/官方会话（仅对“全部/群/单”有效）</span>
                </label>
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

              <div v-if="exportJob.progress?.currentConversationUsername" class="space-y-1">
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
              <a
                v-if="exportJob.status === 'done'"
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

  <!-- 桌面端设置弹窗 -->
  <div
    v-if="desktopSettingsOpen"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="closeDesktopSettings"
  >
    <div class="w-full max-w-md bg-white rounded-lg shadow-lg">
      <div class="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
        <div class="text-base font-medium text-gray-900">设置</div>
        <button
          type="button"
          class="text-gray-500 hover:text-gray-700"
          @click="closeDesktopSettings"
          title="关闭"
        >
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="px-5 py-4 space-y-4">
        <div class="flex items-center justify-between gap-4">
          <div class="min-w-0">
            <div class="text-sm font-medium text-gray-900">开机自启动</div>
            <div class="text-xs text-gray-500">系统登录后自动启动桌面端</div>
          </div>
          <input
            type="checkbox"
            class="h-4 w-4"
            :checked="desktopAutoLaunch"
            :disabled="desktopAutoLaunchLoading"
            @change="onDesktopAutoLaunchToggle"
          />
        </div>
        <div v-if="desktopAutoLaunchError" class="text-xs text-red-600 whitespace-pre-wrap">
          {{ desktopAutoLaunchError }}
        </div>

        <div class="flex items-center justify-between gap-4">
          <div class="min-w-0">
            <div class="text-sm font-medium text-gray-900">关闭窗口行为</div>
            <div class="text-xs text-gray-500">点击关闭按钮时：默认最小化到托盘</div>
          </div>
          <select
            class="text-sm px-2 py-1 rounded-md border border-gray-200"
            :disabled="desktopCloseBehaviorLoading"
            :value="desktopCloseBehavior"
            @change="onDesktopCloseBehaviorChange"
          >
            <option value="tray">最小化到托盘</option>
            <option value="exit">直接退出</option>
          </select>
        </div>
        <div v-if="desktopCloseBehaviorError" class="text-xs text-red-600 whitespace-pre-wrap">
          {{ desktopCloseBehaviorError }}
        </div>

        <div class="flex items-center justify-between gap-4">
          <div class="min-w-0">
            <div class="text-sm font-medium text-gray-900">启动后自动开启实时获取</div>
            <div class="text-xs text-gray-500">进入聊天页后自动打开“实时开关”（默认关闭）</div>
          </div>
          <input
            type="checkbox"
            class="h-4 w-4"
            :checked="desktopAutoRealtime"
            @change="onDesktopAutoRealtimeToggle"
          />
        </div>

        <div class="flex items-center justify-between gap-4">
          <div class="min-w-0">
            <div class="text-sm font-medium text-gray-900">有数据时默认进入聊天页</div>
            <div class="text-xs text-gray-500">有已解密账号时，打开应用默认跳转到 /chat（默认关闭）</div>
          </div>
          <input
            type="checkbox"
            class="h-4 w-4"
            :checked="desktopDefaultToChatWhenData"
            @change="onDesktopDefaultToChatToggle"
          />
        </div>
      </div>

      <div class="px-5 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
        <button
          type="button"
          class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
          @click="closeDesktopSettings"
        >
          关闭
        </button>
      </div>
    </div>
  </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick, defineComponent, h, toRaw } from 'vue'

definePageMeta({
  key: 'chat'
})

import { useApi } from '~/composables/useApi'
import { parseTextWithEmoji } from '~/utils/wechat-emojis'
import wechatPcLogoUrl from '~/assets/images/wechat/WeChat-Icon-Logo.wine.svg'
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
const isSnsRoute = computed(() => route.path?.startsWith('/sns'))

const routeUsername = computed(() => {
  const raw = route.params.username
  return (Array.isArray(raw) ? raw[0] : raw) || ''
})

const buildChatPath = (username) => {
  return username ? `/chat/${encodeURIComponent(username)}` : '/chat'
}

// 响应式数据
const selectedContact = ref(null)

// 隐私模式
const privacyMode = ref(false)
const PRIVACY_MODE_KEY = 'ui.privacy_mode'

onMounted(() => {
  if (!process.client) return
  try {
    privacyMode.value = localStorage.getItem(PRIVACY_MODE_KEY) === '1'
  } catch {}
})

watch(
  () => privacyMode.value,
  (v) => {
    if (!process.client) return
    try {
      localStorage.setItem(PRIVACY_MODE_KEY, v ? '1' : '0')
    } catch {}
  }
)

// 桌面端设置（仅 Electron 环境可见）
const isDesktopEnv = ref(false)
const desktopSettingsOpen = ref(false)

const DESKTOP_SETTING_AUTO_REALTIME_KEY = 'desktop.settings.autoRealtime'
const DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY = 'desktop.settings.defaultToChatWhenData'

const desktopAutoRealtime = ref(false)
const desktopDefaultToChatWhenData = ref(false)

const desktopAutoLaunch = ref(false)
const desktopAutoLaunchLoading = ref(false)
const desktopAutoLaunchError = ref('')

const desktopCloseBehavior = ref('tray') // tray | exit
const desktopCloseBehaviorLoading = ref(false)
const desktopCloseBehaviorError = ref('')

const readLocalBool = (key) => {
  if (!process.client) return false
  try {
    return localStorage.getItem(key) === 'true'
  } catch {
    return false
  }
}

const writeLocalBool = (key, value) => {
  if (!process.client) return
  try {
    localStorage.setItem(key, value ? 'true' : 'false')
  } catch {}
}

// 尽量早读本地设置，避免首次加载联系人时拿不到 autoRealtime 选项
if (process.client) {
  desktopAutoRealtime.value = readLocalBool(DESKTOP_SETTING_AUTO_REALTIME_KEY)
  desktopDefaultToChatWhenData.value = readLocalBool(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY)
}

const refreshDesktopAutoLaunch = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.getAutoLaunch) return
  desktopAutoLaunchLoading.value = true
  desktopAutoLaunchError.value = ''
  try {
    desktopAutoLaunch.value = !!(await window.wechatDesktop.getAutoLaunch())
  } catch (e) {
    desktopAutoLaunchError.value = e?.message || '读取开机自启动状态失败'
  } finally {
    desktopAutoLaunchLoading.value = false
  }
}

const setDesktopAutoLaunch = async (enabled) => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.setAutoLaunch) return
  desktopAutoLaunchLoading.value = true
  desktopAutoLaunchError.value = ''
  try {
    desktopAutoLaunch.value = !!(await window.wechatDesktop.setAutoLaunch(!!enabled))
  } catch (e) {
    desktopAutoLaunchError.value = e?.message || '设置开机自启动失败'
    await refreshDesktopAutoLaunch()
  } finally {
    desktopAutoLaunchLoading.value = false
  }
}

const refreshDesktopCloseBehavior = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.getCloseBehavior) return
  desktopCloseBehaviorLoading.value = true
  desktopCloseBehaviorError.value = ''
  try {
    const v = await window.wechatDesktop.getCloseBehavior()
    desktopCloseBehavior.value = (String(v || '').toLowerCase() === 'exit') ? 'exit' : 'tray'
  } catch (e) {
    desktopCloseBehaviorError.value = e?.message || '读取关闭窗口行为失败'
  } finally {
    desktopCloseBehaviorLoading.value = false
  }
}

const setDesktopCloseBehavior = async (behavior) => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.setCloseBehavior) return
  const desired = (String(behavior || '').toLowerCase() === 'exit') ? 'exit' : 'tray'
  desktopCloseBehaviorLoading.value = true
  desktopCloseBehaviorError.value = ''
  try {
    const v = await window.wechatDesktop.setCloseBehavior(desired)
    desktopCloseBehavior.value = (String(v || '').toLowerCase() === 'exit') ? 'exit' : 'tray'
  } catch (e) {
    desktopCloseBehaviorError.value = e?.message || '设置关闭窗口行为失败'
    await refreshDesktopCloseBehavior()
  } finally {
    desktopCloseBehaviorLoading.value = false
  }
}

const openDesktopSettings = async () => {
  desktopSettingsOpen.value = true
  await refreshDesktopAutoLaunch()
  await refreshDesktopCloseBehavior()
}

const closeDesktopSettings = () => {
  desktopSettingsOpen.value = false
}

const onDesktopAutoLaunchToggle = async (ev) => {
  const checked = !!ev?.target?.checked
  await setDesktopAutoLaunch(checked)
}

const onDesktopCloseBehaviorChange = async (ev) => {
  const v = String(ev?.target?.value || '').trim()
  await setDesktopCloseBehavior(v)
}

const onDesktopAutoRealtimeToggle = async (ev) => {
  const checked = !!ev?.target?.checked
  desktopAutoRealtime.value = checked
  writeLocalBool(DESKTOP_SETTING_AUTO_REALTIME_KEY, checked)
  if (checked) {
    // 开启后尝试立即启用实时模式（不可用则静默忽略）
    try {
      await tryEnableRealtimeAuto()
    } catch {}
  }
}

const onDesktopDefaultToChatToggle = (ev) => {
  const checked = !!ev?.target?.checked
  desktopDefaultToChatWhenData.value = checked
  writeLocalBool(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, checked)
}

// 联系人数据
const contacts = ref([])

const searchQuery = ref('')

const isLoadingContacts = ref(false)
const contactsError = ref('')
const selectedAccount = ref(null)

const availableAccounts = ref([])

const sidebarMediaBase = process.client ? 'http://localhost:8000' : ''

const selfAvatarUrl = computed(() => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return ''
  return `${sidebarMediaBase}/api/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(acc)}`
})

const goSns = async () => {
  await navigateTo('/sns')
}

// 实时更新（WCDB DLL + db_storage watcher）
const realtimeEnabled = ref(false)
const realtimeAvailable = ref(false)
const realtimeChecking = ref(false)
const realtimeStatusInfo = ref(null)
const realtimeStatusError = ref('')
let realtimeEventSource = null
let realtimeRefreshFuture = null
let realtimeRefreshQueued = false
let realtimeSessionsRefreshFuture = null
let realtimeSessionsRefreshQueued = false
let realtimeFullSyncFuture = null
let realtimeFullSyncQueued = false
let realtimeFullSyncPriority = ''
let realtimeChangeDebounceTimer = null

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
  username: '',
  anchorId: '',
  anchorIndex: -1,
  savedMessages: null,
  savedMeta: null
})
const highlightMessageId = ref('')
let highlightMessageTimer = null

// 回到最新按钮
const showJumpToBottom = ref(false)

// 导出（离线 zip）
const exportModalOpen = ref(false)
const isExportCreating = ref(false)
const exportError = ref('')

// current: 当前会话（映射为 selected + 单个 username）
const exportScope = ref('current') // current | selected | all | groups | singles
const exportFormat = ref('json') // json | txt
const exportMessageTypeMode = ref('all') // all | filter
const exportMessageTypeOptions = [
  { value: 'text', label: '文本' },
  { value: 'image', label: '图片' },
  { value: 'emoji', label: '表情' },
  { value: 'video', label: '视频' },
  { value: 'voice', label: '语音' },
  { value: 'transfer', label: '转账' },
  { value: 'redPacket', label: '红包' },
  { value: 'file', label: '文件' },
  { value: 'link', label: '链接' },
  { value: 'quote', label: '引用' },
  { value: 'system', label: '系统' },
  { value: 'voip', label: '通话' }
]
const exportMessageTypes = ref(exportMessageTypeOptions.map((x) => x.value))
const exportIncludeMedia = ref(true)
const exportMediaKinds = ref(['image', 'emoji', 'video', 'video_thumb', 'voice', 'file'])
const exportIncludeHidden = ref(false)
const exportIncludeOfficial = ref(false)

const exportStartLocal = ref('') // datetime-local
const exportEndLocal = ref('') // datetime-local
const exportFileName = ref('')

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
    const base = 'http://localhost:8000'
    const url = `${base}/api/chat/exports/${encodeURIComponent(String(exportId))}/events`
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
  exportListTab.value = 'all'

  if (privacyMode.value) {
    exportIncludeMedia.value = false
  }

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

const getExportDownloadUrl = (exportId) => {
  const base = process.client ? 'http://localhost:8000' : ''
  return `${base}/api/chat/exports/${encodeURIComponent(String(exportId || ''))}/download`
}

const startChatExport = async () => {
  exportError.value = ''
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

  const startTime = toUnixSeconds(exportStartLocal.value)
  const endTime = toUnixSeconds(exportEndLocal.value)
  if (startTime && endTime && startTime > endTime) {
    exportError.value = '时间范围不合法：开始时间不能晚于结束时间'
    return
  }

  const messageTypes = exportMessageTypeMode.value === 'filter'
    ? (Array.isArray(exportMessageTypes.value) ? exportMessageTypes.value.filter(Boolean) : [])
    : []
  if (exportMessageTypeMode.value === 'filter' && messageTypes.length === 0) {
    exportError.value = '请选择至少一个消息类型'
    return
  }

  isExportCreating.value = true
  try {
    const api = useApi()
    const resp = await api.createChatExport({
      account: selectedAccount.value,
      scope,
      usernames,
      format: exportFormat.value,
      start_time: startTime,
      end_time: endTime,
      include_hidden: exportIncludeHidden.value,
      include_official: exportIncludeOfficial.value,
      message_types: messageTypes,
      include_media: exportIncludeMedia.value && !privacyMode.value,
      media_kinds: (exportIncludeMedia.value && !privacyMode.value) ? exportMediaKinds.value : [],
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

const applyExportQuickRangeDays = (days) => {
  const now = new Date()
  const end = new Date(now.getTime())
  const start = new Date(now.getTime() - Number(days) * 24 * 3600 * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  exportStartLocal.value = fmt(start)
  exportEndLocal.value = fmt(end)
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

const openImagePreview = (url) => {
  previewImageUrl.value = url
  document.body.style.overflow = 'hidden'
}

const closeImagePreview = () => {
  previewImageUrl.value = null
  document.body.style.overflow = ''
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

const playQuoteVoice = (message) => {
  playVoice({ id: getQuoteVoiceId(message) })
}

const contextMenu = ref({ visible: false, x: 0, y: 0, message: null, kind: '', disabled: false })

const closeContextMenu = () => {
  contextMenu.value = { visible: false, x: 0, y: 0, message: null, kind: '', disabled: false }
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
    disabled
  }
}

const copyTextToClipboard = async (text) => {
  if (!process.client) return false
  if (typeof text !== 'string') return false

  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {}

  try {
    const el = document.createElement('textarea')
    el.value = text
    el.setAttribute('readonly', 'true')
    el.style.position = 'fixed'
    el.style.left = '-9999px'
    el.style.top = '-9999px'
    document.body.appendChild(el)
    el.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(el)
    return ok
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

const ensureMessageSearchScopeValid = () => {
  if (messageSearchScope.value === 'conversation' && !selectedContact.value) {
    messageSearchScope.value = 'global'
  }
}

const toggleMessageSearch = async () => {
  messageSearchOpen.value = !messageSearchOpen.value
  ensureMessageSearchScopeValid()
  if (!messageSearchOpen.value) return
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
    username: '',
    anchorId: '',
    anchorIndex: -1,
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
      username: targetUsername,
      anchorId: String(hit.id),
      anchorIndex: -1,
      savedMessages: allMessages.value[targetUsername] || [],
      savedMeta: messagesMeta.value[targetUsername] || null
    }
  } else {
    searchContext.value.anchorId = String(hit.id)
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

const getTransferTitle = (message) => {
  const paySubType = String(message.paySubType || '').trim()
  // paysubtype 含义：
  // 1=不明确 3=已收款/接收转账 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期
  // 优先使用后端计算的 transferStatus（如果有）
  if (message.transferStatus) return message.transferStatus
  switch (paySubType) {
    case '1': return '转账'
    case '3': return message.isSent ? '已收款' : '已被接收'
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

const renderMessages = computed(() => {
  const list = messages.value || []
  let prevTs = 0
  return list.map((m) => {
    const ts = Number(m.createTime || 0)
    const show = !prevTs || (ts && Math.abs(ts - prevTs) >= 300)
    if (ts) prevTs = ts
    return {
      ...m,
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
  const api = useApi()
  isLoadingContacts.value = true
  contactsError.value = ''

  try {
    const accountsResp = await api.listChatAccounts()
    const accounts = accountsResp?.accounts || []
    availableAccounts.value = accounts
    selectedAccount.value = selectedAccount.value || accountsResp?.default_account || accounts[0] || null

    if (!selectedAccount.value) {
      contacts.value = []
      selectedContact.value = null
      contactsError.value = accountsResp?.message || '未检测到已解密账号，请先解密数据库。'
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
    lastMessage: s.lastMessage || '',
    lastMessageTime: s.lastMessageTime || '',
    unreadCount: s.unreadCount || 0,
    isGroup: !!s.isGroup,
    username: s.username
  }))

  allMessages.value = {}
  messagesMeta.value = {}
  messagesError.value = ''
  selectedContact.value = null

  closeMessageSearch()
  messageSearchResults.value = []
  messageSearchOffset.value = 0
  messageSearchHasMore.value = false
  messageSearchBackendStatus.value = ''
  messageSearchTotal.value = 0
  messageSearchIndexInfo.value = null
  messageSearchSelectedIndex.value = -1
  searchContext.value = {
    active: false,
    username: '',
    anchorId: '',
    anchorIndex: -1,
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
    lastMessage: s.lastMessage || '',
    lastMessageTime: s.lastMessageTime || '',
    unreadCount: s.unreadCount || 0,
    isGroup: !!s.isGroup,
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

const runRealtimeFullSync = async (priorityUsername) => {
  if (!realtimeEnabled.value) return null
  if (!process.client || typeof window === 'undefined') return null
  if (!selectedAccount.value) return null

  try {
    const api = useApi()
    return await api.syncChatRealtimeAll({
      account: selectedAccount.value,
      max_scan: 200,
      priority_username: String(priorityUsername || '').trim(),
      priority_max_scan: 600,
      include_hidden: true,
      include_official: true
    })
  } catch {
    return null
  }
}

const queueRealtimeFullSync = (priorityUsername) => {
  const u = String(priorityUsername || '').trim()
  if (u) realtimeFullSyncPriority = u

  if (realtimeFullSyncFuture) {
    realtimeFullSyncQueued = true
    return realtimeFullSyncFuture
  }

  const priority = realtimeFullSyncPriority
  realtimeFullSyncPriority = ''

  realtimeFullSyncFuture = runRealtimeFullSync(priority).finally(() => {
    realtimeFullSyncFuture = null
    if (realtimeFullSyncQueued) {
      realtimeFullSyncQueued = false
      queueRealtimeFullSync(realtimeFullSyncPriority)
    }
  })

  return realtimeFullSyncFuture
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

  const mediaBase = process.client ? 'http://localhost:8000' : ''
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
        return `${mediaBase}/api/chat/media/proxy_image?url=${encodeURIComponent(u)}`
      }
    } catch {}
    return u
  })()

  const fromUsername = String(msg.fromUsername || '').trim()
  const fromAvatar = fromUsername
    ? `${mediaBase}/api/chat/avatar?account=${encodeURIComponent(selectedAccount.value || '')}&username=${encodeURIComponent(fromUsername)}`
    : ''

  const localEmojiUrl = msg.emojiMd5 ? `${mediaBase}/api/chat/media/emoji?account=${encodeURIComponent(selectedAccount.value || '')}&md5=${encodeURIComponent(msg.emojiMd5)}&username=${encodeURIComponent(selectedContact.value?.username || '')}` : ''
  const localImageUrl = (() => {
    if (!msg.imageMd5 && !msg.imageFileId) return ''
    const parts = [
      `account=${encodeURIComponent(selectedAccount.value || '')}`,
      msg.imageMd5 ? `md5=${encodeURIComponent(msg.imageMd5)}` : '',
      msg.imageFileId ? `file_id=${encodeURIComponent(msg.imageFileId)}` : '',
      `username=${encodeURIComponent(selectedContact.value?.username || '')}`,
    ].filter(Boolean)
    return `${mediaBase}/api/chat/media/image?${parts.join('&')}`
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
    return `${mediaBase}/api/chat/media/video_thumb?${parts.join('&')}`
  })()

  const localVideoUrl = (() => {
    if (!msg.videoMd5 && !msg.videoFileId) return ''
    const parts = [
      `account=${encodeURIComponent(selectedAccount.value || '')}`,
      msg.videoMd5 ? `md5=${encodeURIComponent(msg.videoMd5)}` : '',
      msg.videoFileId ? `file_id=${encodeURIComponent(msg.videoFileId)}` : '',
      `username=${encodeURIComponent(selectedContact.value?.username || '')}`,
    ].filter(Boolean)
    return `${mediaBase}/api/chat/media/video?${parts.join('&')}`
  })()

  const normalizedVideoThumbUrl = (isUsableMediaUrl(msg.videoThumbUrl) ? normalizeMaybeUrl(msg.videoThumbUrl) : '') || localVideoThumbUrl
  const normalizedVideoUrl = (isUsableMediaUrl(msg.videoUrl) ? normalizeMaybeUrl(msg.videoUrl) : '') || localVideoUrl
  const serverIdStr = String(msg.serverIdStr || (msg.serverId != null ? String(msg.serverId) : '')).trim()
  const normalizedVoiceUrl = (() => {
    if (msg.voiceUrl) return msg.voiceUrl
    if (!serverIdStr) return ''
    if (String(msg.renderType || '') !== 'voice') return ''
    return `${mediaBase}/api/chat/media/voice?account=${encodeURIComponent(selectedAccount.value || '')}&server_id=${encodeURIComponent(serverIdStr)}`
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
    quoteServerId: String(msg.quoteServerId || '').trim(),
    quoteType: String(msg.quoteType || '').trim(),
    quoteVoiceLength: msg.quoteVoiceLength || '',
    quoteVoiceUrl: String(msg.quoteServerId || '').trim()
      ? `${mediaBase}/api/chat/media/voice?account=${encodeURIComponent(selectedAccount.value || '')}&server_id=${encodeURIComponent(String(msg.quoteServerId || '').trim())}`
      : '',
    amount: msg.amount || '',
    coverUrl: msg.coverUrl || '',
    fileSize: msg.fileSize || '',
    fileMd5: msg.fileMd5 || '',
    paySubType: msg.paySubType || '',
    transferStatus: msg.transferStatus || '',
    transferReceived: msg.paySubType === '3' || msg.transferStatus === '已收款',
    voiceUrl: normalizedVoiceUrl || '',
    voiceDuration: msg.voiceLength || msg.voiceDuration || '',
    preview: normalizedLinkPreviewUrl || '',
    from: String(msg.from || '').trim(),
    fromUsername,
    fromAvatar,
    isGroup: !!selectedContact.value?.isGroup,
    // Backends may use either `senderAvatar` (our API) or `avatar` (exported JSON).
    avatar: msg.senderAvatar || msg.avatar || fallbackAvatar || null,
    avatarColor: null
  }
}

const onMessageAvatarError = (e, message) => {
  // Make sure we fall back to the initial avatar if the URL 404s/blocks.
  try { e?.target && (e.target.style.display = 'none') } catch {}
  try { if (message) message.avatar = null } catch {}
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

// 合并转发聊天记录弹窗
const chatHistoryModalVisible = ref(false)
const chatHistoryModalTitle = ref('')
const chatHistoryModalRecords = ref([])
const chatHistoryModalInfo = ref({ isChatRoom: false })

const isMaybeMd5 = (value) => /^[0-9a-f]{32}$/i.test(String(value || '').trim())
const pickFirstMd5 = (...values) => {
  for (const v of values) {
    const s = String(v || '').trim()
    if (isMaybeMd5(s)) return s.toLowerCase()
  }
  return ''
}

const normalizeChatHistoryUrl = (value) => String(value || '').trim().replace(/\s+/g, '')

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
      const el = node.getElementsByTagName(tag)?.[0]
      return String(el?.textContent || '').trim()
    } catch {
      return ''
    }
  }

  const root = doc?.documentElement
  const isChatRoom = String(getText(root, 'isChatRoom') || '').trim() === '1'
  const title = getText(root, 'title')
  const desc = getText(root, 'desc') || getText(root, 'info')

  const items = Array.from(doc.getElementsByTagName('dataitem') || [])
  const parsed = items.map((node, idx) => {
    const datatype = String(node.getAttribute('datatype') || '').trim()
    const dataid = String(node.getAttribute('dataid') || '').trim() || String(idx)

    const sourcename = getText(node, 'sourcename')
    const sourcetime = getText(node, 'sourcetime')
    const sourceheadurl = normalizeChatHistoryUrl(getText(node, 'sourceheadurl'))
    const datatitle = getText(node, 'datatitle')
    const datadesc = getText(node, 'datadesc')
    const datafmt = getText(node, 'datafmt')
    const duration = getText(node, 'duration')

    const fullmd5 = getText(node, 'fullmd5')
    const thumbfullmd5 = getText(node, 'thumbfullmd5')
    const md5 = getText(node, 'md5') || getText(node, 'emoticonmd5') || getText(node, 'emojiMd5')
    const fromnewmsgid = getText(node, 'fromnewmsgid')
    const srcMsgLocalid = getText(node, 'srcMsgLocalid')
    const srcMsgCreateTime = getText(node, 'srcMsgCreateTime')
    const cdnurlstring = normalizeChatHistoryUrl(getText(node, 'cdnurlstring'))
    const encrypturlstring = normalizeChatHistoryUrl(getText(node, 'encrypturlstring'))
    const externurl = normalizeChatHistoryUrl(getText(node, 'externurl'))
    const aeskey = getText(node, 'aeskey')

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
    if (datatype === '4' || String(duration || '').trim() || fmt === 'mp4') {
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
      content
    }
  })

  return {
    info: { isChatRoom, title, desc },
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
  const mediaBase = process.client ? 'http://localhost:8000' : ''
  const account = encodeURIComponent(selectedAccount.value || '')
  const username = encodeURIComponent(selectedContact.value?.username || '')

  const out = { ...(rec || {}) }
  out.senderDisplayName = String(out.sourcename || '').trim()
  out.senderAvatar = normalizeChatHistoryUrl(out.sourceheadurl)
  out.fullTime = String(out.sourcetime || '').trim()

  if (out.renderType === 'video') {
    out.videoMd5 = pickFirstMd5(out.fullmd5, out.md5)
    out.videoThumbMd5 = pickFirstMd5(out.thumbfullmd5)
    out.videoDuration = String(out.duration || '').trim()
    const thumbCandidates = []
    if (out.videoMd5) {
      thumbCandidates.push(`${mediaBase}/api/chat/media/video_thumb?account=${account}&md5=${encodeURIComponent(out.videoMd5)}&username=${username}`)
    }
    if (out.videoThumbMd5 && out.videoThumbMd5 !== out.videoMd5) {
      thumbCandidates.push(`${mediaBase}/api/chat/media/video_thumb?account=${account}&md5=${encodeURIComponent(out.videoThumbMd5)}&username=${username}`)
    }
    out._videoThumbCandidates = thumbCandidates
    out._videoThumbCandidateIndex = 0
    out._videoThumbError = false
    out.videoThumbUrl = thumbCandidates[0] || ''
    out.videoUrl = out.videoMd5
      ? `${mediaBase}/api/chat/media/video?account=${account}&md5=${encodeURIComponent(out.videoMd5)}&username=${username}`
      : ''
    if (!out.content || /^\[.+\]$/.test(String(out.content || '').trim())) out.content = '[视频]'
  } else if (out.renderType === 'emoji') {
    out.emojiMd5 = pickFirstMd5(out.md5, out.fullmd5, out.thumbfullmd5)
    const remoteEmojiUrl = String(out.cdnurlstring || out.externurl || out.encrypturlstring || '').trim()
    const remoteAesKey = String(out.aeskey || '').trim()
    out.emojiRemoteUrl = remoteEmojiUrl
    out.emojiUrl = out.emojiMd5
      ? `${mediaBase}/api/chat/media/emoji?account=${account}&md5=${encodeURIComponent(out.emojiMd5)}&username=${username}${remoteEmojiUrl ? `&emoji_url=${encodeURIComponent(remoteEmojiUrl)}` : ''}${remoteAesKey ? `&aes_key=${encodeURIComponent(remoteAesKey)}` : ''}`
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
    out.imageUrl = imgParts.length ? `${mediaBase}/api/chat/media/image?${imgParts.join('&')}` : ''
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
    try {
      window.open(url, '_blank', 'noreferrer')
    } catch {}
    return
  }

  if (kind === 'image' || kind === 'emoji') {
    openImagePreview(url)
  }
}

const openChatHistoryModal = (message) => {
  if (!process.client) return
  chatHistoryModalTitle.value = String(message?.title || '聊天记录')

  const recordItem = String(message?.recordItem || '').trim()
  const parsed = parseChatHistoryRecord(recordItem)
  chatHistoryModalInfo.value = parsed?.info || { isChatRoom: false }
  const records = parsed?.items
  chatHistoryModalRecords.value = Array.isArray(records) ? enhanceChatHistoryRecords(records.map(normalizeChatHistoryRecordItem)) : []

  if (!chatHistoryModalRecords.value.length) {
    // 降级：使用摘要内容按行展示
    const lines = String(message?.content || '').trim().split(/\r?\n/).map((x) => x.trim()).filter(Boolean)
    chatHistoryModalInfo.value = { isChatRoom: false }
    chatHistoryModalRecords.value = lines.map((line, idx) => normalizeChatHistoryRecordItem({ id: String(idx), datatype: '1', sourcename: '', sourcetime: '', content: line, renderType: 'text' }))
  }

  chatHistoryModalVisible.value = true
  document.body.style.overflow = 'hidden'
}

const closeChatHistoryModal = () => {
  chatHistoryModalVisible.value = false
  chatHistoryModalTitle.value = ''
  chatHistoryModalRecords.value = []
  chatHistoryModalInfo.value = { isChatRoom: false }
  document.body.style.overflow = previewImageUrl.value ? 'hidden' : ''
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
    if (chatHistoryModalVisible.value) closeChatHistoryModal()
    if (messageSearchSenderDropdownOpen.value) closeMessageSearchSenderDropdown()
    if (messageSearchOpen.value) closeMessageSearch()
    if (searchContext.value?.active) exitSearchContext()
  }
}

onMounted(() => {
  if (!process.client) return
  document.addEventListener('click', onGlobalClick)
  document.addEventListener('keydown', onGlobalKeyDown)
})

onUnmounted(() => {
  if (!process.client) return
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onGlobalKeyDown)
  if (messageSearchDebounceTimer) clearTimeout(messageSearchDebounceTimer)
  messageSearchDebounceTimer = null
  if (highlightMessageTimer) clearTimeout(highlightMessageTimer)
  highlightMessageTimer = null
  stopMessageSearchIndexPolling()
  stopExportPolling()
  stopRealtimeStream()
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

const fetchRealtimeStatus = async () => {
  if (!process.client) return
  if (!selectedAccount.value) {
    realtimeAvailable.value = false
    realtimeStatusInfo.value = null
    realtimeStatusError.value = ''
    return
  }

  const api = useApi()
  realtimeChecking.value = true
  try {
    const resp = await api.getChatRealtimeStatus({ account: selectedAccount.value })
    realtimeAvailable.value = !!resp?.available
    realtimeStatusInfo.value = resp?.realtime || null
    realtimeStatusError.value = ''
  } catch (e) {
    realtimeAvailable.value = false
    realtimeStatusInfo.value = null
    realtimeStatusError.value = e?.message || '实时状态获取失败'
  } finally {
    realtimeChecking.value = false
  }
}

const stopRealtimeStream = () => {
  if (realtimeEventSource) {
    try {
      realtimeEventSource.close()
    } catch {}
    realtimeEventSource = null
  }
  if (realtimeChangeDebounceTimer) {
    try {
      clearTimeout(realtimeChangeDebounceTimer)
    } catch {}
    realtimeChangeDebounceTimer = null
  }
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

const queueRealtimeChange = () => {
  if (!process.client || typeof window === 'undefined') return
  if (!realtimeEnabled.value) return
  if (realtimeChangeDebounceTimer) return

  // Debounce noisy db_storage change events to avoid hammering the backend.
  realtimeChangeDebounceTimer = setTimeout(() => {
    realtimeChangeDebounceTimer = null
    queueRealtimeRefresh()
    queueRealtimeSessionsRefresh()
  }, 500)
}

const startRealtimeStream = () => {
  stopRealtimeStream()
  if (!process.client || typeof window === 'undefined') return
  if (!realtimeEnabled.value) return
  if (!selectedAccount.value) return
  if (typeof EventSource === 'undefined') return

  const base = 'http://localhost:8000'
  const url = `${base}/api/chat/realtime/stream?account=${encodeURIComponent(String(selectedAccount.value))}`
  try {
    realtimeEventSource = new EventSource(url)
  } catch (e) {
    realtimeEventSource = null
    return
  }

  realtimeEventSource.onmessage = (ev) => {
    try {
      const data = JSON.parse(String(ev.data || '{}'))
      if (String(data?.type || '') === 'change') {
        queueRealtimeChange()
      }
    } catch {}
  }

  realtimeEventSource.onerror = () => {
    stopRealtimeStream()
  }
}

const toggleRealtime = async (opts = {}) => {
  const silent = !!opts?.silent
  if (!process.client || typeof window === 'undefined') return
  if (!selectedAccount.value) return

  if (!realtimeEnabled.value) {
    await fetchRealtimeStatus()
    if (!realtimeAvailable.value) {
      if (!silent) {
        window.alert(realtimeStatusError.value || '实时模式不可用：缺少密钥或 db_storage 路径。')
      }
      return false
    }
    realtimeEnabled.value = true
    startRealtimeStream()
    queueRealtimeSessionsRefresh()
    if (selectedContact.value?.username) {
      await refreshSelectedMessages()
    }
    return true
  }

  realtimeEnabled.value = false
  stopRealtimeStream()
  await refreshSessionsForSelectedAccount({ sourceOverride: '' })
  if (selectedContact.value?.username) {
    await refreshSelectedMessages()
  }
  return true
}

const tryEnableRealtimeAuto = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!isDesktopEnv.value) return
  if (!desktopAutoRealtime.value) return
  if (realtimeEnabled.value) return
  if (!selectedAccount.value) return

  try {
    await toggleRealtime({ silent: true })
  } catch {}
}

watch(selectedAccount, async () => {
  await fetchRealtimeStatus()
  if (realtimeEnabled.value) {
    startRealtimeStream()
  }
})

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

const onMessageScroll = async () => {
  const c = messageContainerRef.value
  if (!c) return
  updateJumpToBottomState()
  if (!selectedContact.value) return
  if (searchContext.value?.active) return

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
    href: { type: String, required: true },
    heading: { type: String, default: '' },
    abstract: { type: String, default: '' },
    preview: { type: String, default: '' },
    fromAvatar: { type: String, default: '' },
    from: { type: String, default: '' },
    isSent: { type: Boolean, default: false }
  },
  setup(props) {
    const getFromText = () => {
      const raw = String(props.from || '').trim()
      if (raw) return raw
      // Fallback: when the appmsg XML doesn't provide sourcedisplayname/appname,
      // show the host so the footer row still matches WeChat's fixed card layout.
      try {
        const host = new URL(String(props.href || '')).hostname
        return String(host || '').trim()
      } catch {
        return ''
      }
    }

    return () => {
      const fromText = getFromText()
      // WeChat link cards show a small avatar next to the source text. We don't
      // always have a real image URL, so fall back to the first glyph.
      const fromAvatarText = (() => {
        const t = String(fromText || '').trim()
        return t ? (Array.from(t)[0] || '') : ''
      })()
      const fromAvatarUrl = String(props.fromAvatar || '').trim()
      return h(
        'a',
        {
          href: props.href,
          target: '_blank',
          rel: 'noreferrer',
          class: [
            'wechat-link-card',
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
            h('div', { class: 'wechat-link-info' }, [
              h('div', { class: 'wechat-link-title' }, props.heading || props.href),
              props.abstract ? h('div', { class: 'wechat-link-desc' }, props.abstract) : null
            ].filter(Boolean)),
            props.preview ? h('div', { class: 'wechat-link-thumb' }, [
              h('img', { src: props.preview, alt: props.heading || '链接预览', class: 'wechat-link-thumb-img', referrerpolicy: 'no-referrer' })
            ]) : null
          ].filter(Boolean)),
          h('div', { class: 'wechat-link-from' }, [
            h('div', { class: 'wechat-link-from-avatar', 'aria-hidden': 'true' }, [
              fromAvatarText || '\u200B',
              fromAvatarUrl ? h('img', {
                src: fromAvatarUrl,
                alt: '',
                class: 'wechat-link-from-avatar-img',
                referrerpolicy: 'no-referrer',
                onError: (e) => { try { e?.target && (e.target.style.display = 'none') } catch {} }
              }) : null
            ].filter(Boolean)),
            h('div', { class: 'wechat-link-from-name' }, fromText || '\u200B')
          ])
        ].filter(Boolean)
      )
    }
  }
})

</script>

<style scoped>
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
  background: #f8e2c6;
}

.wechat-transfer-received::after {
  background: #f8e2c6;
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
  flex-direction: row;
  align-items: flex-start;
  gap: 10px;
  box-sizing: border-box;
  /* Keep a small breathing room above the footer divider. */
  padding: 8px 10px 6px;
  flex: 1 1 auto;
}

:deep(.wechat-link-info) {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1 1 auto;
  min-width: 0;
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
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
  word-break: break-word;
}

:deep(.wechat-link-thumb) {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 0;
  overflow: hidden;
  background: #f2f2f2;
  /* Center the thumbnail in the content area (WeChat desktop style). */
  align-self: center;
}

:deep(.wechat-link-thumb-img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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
