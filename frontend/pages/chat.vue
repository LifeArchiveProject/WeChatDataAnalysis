<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- 左侧边栏 -->
    <div class="w-16 border-r border-gray-200 flex flex-col" style="background-color: #EDEDED">
      <div class="flex-1 flex flex-col justify-start pt-0">
        <!-- 聊天图标 (与 oh-my-wechat 一致) -->
        <div class="w-16 h-16 flex items-center justify-center chat-tab text-[#03C160]">
          <div class="w-7 h-7">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z"/>
            </svg>
          </div>
        </div>
        
        <!-- 隐私模式按钮 -->
        <div
          class="w-16 h-12 flex items-center justify-center cursor-pointer transition-colors"
          :class="privacyMode ? 'text-[#03C160]' : 'text-gray-500 hover:text-gray-700'"
          @click="privacyMode = !privacyMode"
          :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
        >
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path v-if="privacyMode" stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
            <path v-else stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
            <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
          </svg>
        </div>
      </div>
    </div>

    <!-- 中间列表区域 -->
    <div class="w-80 border-r border-gray-200 flex flex-col min-h-0" style="background-color: #F7F7F7">
      <!-- 聊天列表 -->
      <div class="h-full flex flex-col min-h-0">
        <!-- 搜索栏 -->
        <div class="h-16 p-4 border-b border-gray-200" style="background-color: #F7F7F7">
          <div class="flex items-center space-x-2">
            <div class="relative flex-1">
              <input
                type="text"
                placeholder="搜索"
                v-model="searchQuery"
                class="w-full pl-8 pr-4 py-2 text-sm focus:outline-none rounded-md"
                style="background-color: #EAEAEA; border: none;"
              >
              <svg class="w-4 h-4 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
              </svg>
            </div>

            <select
              v-if="availableAccounts.length > 1"
              v-model="selectedAccount"
              @change="onAccountChange"
              class="text-xs px-2 py-2 rounded-md border border-gray-200 focus:outline-none"
              style="background-color: #EAEAEA;"
            >
              <option v-for="acc in availableAccounts" :key="acc" :value="acc">{{ acc }}</option>
            </select>
          </div>
        </div>

        <!-- 联系人列表 -->
        <div class="flex-1 overflow-y-auto min-h-0">
          <div v-if="isLoadingContacts" class="px-3 py-2 text-sm text-gray-500">
            加载中...
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
              :class="selectedContact?.id === contact.id ? 'bg-[#DEDEDE]' : 'hover:bg-[#eaeaea]'"
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
      <div v-if="selectedContact" class="flex-1 flex flex-col min-h-0">
        <!-- 聊天头部 -->
        <div class="h-16 px-6 flex items-center" style="background-color: #EDEDED; border-bottom: 1px solid #d5d5d5;">
          <div class="flex items-center space-x-3">
            <h2 class="text-lg font-medium text-gray-900" :class="{ 'privacy-blur': privacyMode }">
              {{ selectedContact ? selectedContact.name : '' }}
            </h2>
          </div>
          <div class="ml-auto flex items-center space-x-2">
            <button
              class="text-xs px-3 py-1 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
              @click="refreshSelectedMessages"
              :disabled="isLoadingMessages"
            >
              刷新
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

          <div v-for="message in renderMessages" :key="message.id" class="mb-6">
            <div v-if="message.showTimeDivider" class="flex justify-center mb-4">
              <div class="px-3 py-1 rounded-md text-xs text-gray-600" style="background-color: rgba(222,222,222,0.65)">
                {{ message.timeDivider }}
              </div>
            </div>

            <div v-if="message.renderType === 'system'" class="flex justify-center">
              <div class="px-3 py-1 rounded-md text-xs text-gray-600" style="background-color: rgba(222,222,222,0.65)">
                {{ message.content }}
              </div>
            </div>

            <div v-else class="flex items-center" :class="message.isSent ? 'justify-end' : 'justify-start'">
              <div class="flex items-start max-w-md" :class="message.isSent ? 'flex-row-reverse' : ''">
                <!-- 消息发送者头像 -->
                <div class="w-[36px] h-[36px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="[message.isSent ? 'ml-3' : 'mr-3', { 'privacy-blur': privacyMode }]">
                  <div v-if="message.avatar" class="w-full h-full">
                    <img :src="message.avatar" :alt="message.sender + '的头像'" class="w-full h-full object-cover">
                  </div>
                  <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                    :style="{ backgroundColor: message.avatarColor || (message.isSent ? '#4B5563' : '#6B7280') }">
                    {{ message.sender.charAt(0) }}
                  </div>
                </div>
                
                <!-- 消息内容气泡（精简：移除了专用消息组件） -->
                <div class="flex flex-col relative group" :class="[message.isSent ? 'items-end' : 'items-start', { 'privacy-blur': privacyMode }]">
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
                    :from="message.from"
                  />
                  <div v-else-if="message.renderType === 'file'"
                    class="max-w-80 py-2.5 pr-2 pl-4 flex items-start bg-white space-x-2.5 rounded-xl cursor-pointer border border-neutral-200 hover:bg-gray-50 transition-colors"
                    @contextmenu="openMediaContextMenu($event, message, 'file')">
                    <div class="flex-1 min-w-0">
                      <h4 class="break-words font-medium text-sm text-gray-900">{{ message.title || message.content }}</h4>
                      <small class="text-neutral-500 text-xs" v-if="message.fileSize">{{ formatFileSize(message.fileSize) }}</small>
                    </div>
                    <div class="shrink-0 w-10 h-10 flex items-center justify-center">
                      <!-- 文件图标 -->
                      <svg class="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h6v6h6v10H6z"/>
                      </svg>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'image'"
                    class="max-w-sm">
                    <div class="rounded-lg overflow-hidden cursor-pointer" :class="message.isSent ? '' : ''" @click="message.imageUrl && openImagePreview(message.imageUrl)" @contextmenu="openMediaContextMenu($event, message, 'image')">
                      <img v-if="message.imageUrl" :src="message.imageUrl" alt="图片" class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity">
                      <div v-else class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                        :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                        {{ message.content }}
                      </div>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'video'" class="max-w-sm">
                    <div class="rounded-lg overflow-hidden relative bg-black/5" @contextmenu="openMediaContextMenu($event, message, 'video')">
                      <img v-if="message.videoThumbUrl" :src="message.videoThumbUrl" alt="视频" class="max-w-[260px] max-h-[260px] object-cover">
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
                    class="voice-message-wrap"
                    :class="message.isSent ? 'justify-end' : 'justify-start'"
                    @contextmenu="openMediaContextMenu($event, message, 'voice')">
                    <div
                      class="voice-bubble cursor-pointer select-none"
                      :class="message.isSent ? 'bg-[#95EC69] voice-sent' : 'bg-white voice-received'"
                      :style="{ minWidth: '80px', maxWidth: '180px' }"
                      @click="message.voiceUrl && playVoice(message)"
                    >
                      <div class="flex items-center gap-1.5 px-3 py-2" :class="message.isSent ? 'flex-row-reverse' : ''">
                        <!-- 声波图标 -->
                        <svg class="w-5 h-5 flex-shrink-0" :class="message.isSent ? 'text-gray-700' : 'text-gray-500'" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
                        </svg>
                        <span class="text-xs font-medium" :class="message.isSent ? 'text-gray-700' : 'text-gray-600'">
                          {{ message.voiceDuration || '' }}
                        </span>
                      </div>
                    </div>
                    <!-- 隐藏的 audio 元素用于播放 -->
                    <audio
                      v-if="message.voiceUrl"
                      :ref="el => setVoiceRef(message.id, el)"
                      :src="message.voiceUrl"
                      preload="none"
                      class="hidden"
                    ></audio>
                  </div>
                  <div v-else-if="message.renderType === 'emoji'" class="max-w-sm">
                    <img v-if="message.emojiUrl" :src="message.emojiUrl" alt="表情" class="w-24 h-24 object-contain" @contextmenu="openMediaContextMenu($event, message, 'emoji')">
                    <div v-else class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                      :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                      {{ message.content }}
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'quote'"
                    class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed rounded-lg"
                    :class="message.isSent ? 'bg-[#95EC69] text-black' : 'bg-white text-gray-800'">
                    <div>{{ message.content }}</div>
                    <div 
                      v-if="message.quoteTitle || message.quoteContent"
                      class="mt-2 pl-1.5 pr-2.5 py-1 text-xs leading-normal text-neutral-600 border-l-2 rounded"
                      :class="message.isSent ? 'bg-white/25 border-white/55' : 'bg-[rgba(222,222,222,0.3)] border-[rgba(193,193,193,0.6)]'">
                      <div class="font-medium" v-if="message.quoteTitle">{{ message.quoteTitle }}</div>
                      <div class="line-clamp-2 opacity-80" v-if="message.quoteContent">{{ message.quoteContent }}</div>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'transfer'"
                    class="max-w-[20em] w-fit py-4 pl-4 pr-6 flex gap-4 items-center bg-white rounded-2xl border border-neutral-200">
                    <div class="shrink-0 w-10 h-10">
                      <!-- 转账图标 (黄色双向箭头) -->
                      <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 relative -left-1 -top-1">
                        <rect width="40" height="40" fill="white"/>
                        <path fill-rule="evenodd" clip-rule="evenodd" d="M20 36C28.8366 36 36 28.8366 36 20C36 11.1634 28.8366 4 20 4C11.1634 4 4 11.1634 4 20C4 28.8366 11.1634 36 20 36ZM16.872 13.8839C17.3602 13.3957 17.3602 12.6043 16.872 12.1161C16.3839 11.628 15.5924 11.628 15.1043 12.1161L12.3602 14.8602C11.5466 15.6738 11.5466 16.9929 12.3602 17.8065L15.1043 20.5506C15.5924 21.0387 16.3839 21.0387 16.872 20.5506C17.3602 20.0624 17.3602 19.2709 16.872 18.7828L15.6726 17.5833H26.4048C27.0951 17.5833 27.6548 17.0237 27.6548 16.3333C27.6548 15.643 27.0951 15.0833 26.4048 15.0833H15.6726L16.872 13.8839ZM24.372 20.4494C23.8838 19.9613 23.0924 19.9613 22.6042 20.4494C22.1161 20.9376 22.1161 21.7291 22.6042 22.2172L23.8037 23.4167H13.0715C12.3811 23.4167 11.8215 23.9763 11.8215 24.6667C11.8215 25.357 12.3811 25.9167 13.0715 25.9167H23.8037L22.6042 27.1161C22.1161 27.6043 22.1161 28.3957 22.6042 28.8839C23.0924 29.372 23.8838 29.372 24.372 28.8839L27.116 26.1399L27.1161 26.1398C27.9297 25.3262 27.9297 24.0071 27.1161 23.1935L27.116 23.1934L24.372 20.4494Z" fill="#FFCC33"/>
                      </svg>
                    </div>
                    <div>
                      <h4 class="font-medium text-sm">{{ getTransferTitle(message) }}</h4>
                      <p class="text-sm text-neutral-600" v-if="message.amount">{{ message.amount }}</p>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'redPacket'" class="max-w-64">
                    <!-- 有封面的红包 -->
                    <div v-if="message.coverUrl" class="w-64 bg-white overflow-hidden rounded-2xl border border-neutral-200">
                      <img :src="message.coverUrl" alt="红包封面" class="rounded-2xl w-full object-cover">
                      <div class="py-2 pl-2 pr-3 flex gap-1">
                        <div class="w-6 h-6">
                          <!-- 红包图标 -->
                          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-full h-full">
                            <rect width="24" height="24" rx="4" fill="#FA9D3B"/>
                            <path d="M12 6C9.5 6 7.5 7.5 7.5 9.5C7.5 11 8.5 12 10 12.5L9 14H15L14 12.5C15.5 12 16.5 11 16.5 9.5C16.5 7.5 14.5 6 12 6Z" fill="#FFF2D9"/>
                            <rect x="9" y="14" width="6" height="4" rx="0.5" fill="#FFF2D9"/>
                          </svg>
                        </div>
                        <div>
                          <h4 class="font-medium text-sm">{{ message.content || '红包' }}</h4>
                        </div>
                      </div>
                    </div>
                    <!-- 无封面的红包 -->
                    <div v-else class="max-w-[20em] w-fit py-4 pl-4 pr-6 flex gap-4 items-center bg-white rounded-2xl border border-neutral-200">
                      <div class="shrink-0 w-10 h-10">
                        <!-- 红包图标 -->
                        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 relative -left-1 -top-1">
                          <rect width="40" height="40" fill="white"/>
                          <path fill-rule="evenodd" clip-rule="evenodd" d="M20 36C28.8366 36 36 28.8366 36 20C36 11.1634 28.8366 4 20 4C11.1634 4 4 11.1634 4 20C4 28.8366 11.1634 36 20 36Z" fill="#FA9D3B"/>
                          <path d="M20 10C15.5 10 12 12.5 12 15.5C12 18 14 20 16.5 21L15 24H25L23.5 21C26 20 28 18 28 15.5C28 12.5 24.5 10 20 10Z" fill="#FFF2D9"/>
                          <rect x="15" y="24" width="10" height="6" rx="1" fill="#FFF2D9"/>
                        </svg>
                      </div>
                      <div>
                        <h4 class="font-medium text-sm">{{ message.content || '红包' }}</h4>
                        <p class="text-sm text-neutral-600" v-if="message.title">{{ message.title }}</p>
                      </div>
                    </div>
                  </div>
                  <!-- 文本消息 -->
                  <div v-else-if="message.renderType === 'text'"
                    class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                    :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                    {{ message.content }}
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
      </div>
      
      <!-- 未选择联系人时的提示 -->
      <div v-else class="flex-1 flex items-center justify-center">
        <div class="text-center text-gray-500">
          <div class="w-24 h-24 mx-auto mb-4 text-gray-300">
            <svg fill="currentColor" viewBox="0 0 20 20">
              <path d="M18 13V5a2 2 0 00-2-2H4a2 2 0 00-2 2v8a2 2 0 002 2h3l3 3 3-3h3a2 2 0 002-2zM5 7v14l11-7z"/>
            </svg>
          </div>
          <h3 class="text-lg font-medium text-gray-700 mb-2">微信聊天记录查看器</h3>
          <p class="text-gray-500">
            请选择一个联系人查看聊天记录
          </p>
        </div>
      </div>
    </div>

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

    <div
      v-if="contextMenu.visible"
      class="fixed z-50 bg-white border border-gray-200 rounded-md shadow-lg text-sm"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <button
        class="block w-full text-left px-3 py-2 hover:bg-gray-100"
        type="button"
        :disabled="contextMenu.disabled"
        @click="onOpenFolderClick"
      >
        打开文件夹
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, defineComponent, h } from 'vue'

import { useApi } from '~/composables/useApi'

// 设置页面标题
useHead({
  title: '聊天记录查看器 - 微信数据分析助手'
})

// 响应式数据
const selectedContact = ref(null)

// 隐私模式
const privacyMode = ref(false)

// 联系人数据
const contacts = ref([])

const searchQuery = ref('')

const isLoadingContacts = ref(false)
const contactsError = ref('')
const selectedAccount = ref(null)

const availableAccounts = ref([])

const allMessages = ref({})

const messagesMeta = ref({})
const isLoadingMessages = ref(false)
const messagesError = ref('')

const messagePageSize = 50

const messageContainerRef = ref(null)
const activeMessagesFor = ref('')

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

const setVoiceRef = (id, el) => {
  if (el) {
    voiceRefs.value[id] = el
  }
}

const playVoice = (message) => {
  const audio = voiceRefs.value[message.id]
  if (!audio) return

  // 停止当前播放的语音
  if (currentPlayingVoice.value && currentPlayingVoice.value !== audio) {
    currentPlayingVoice.value.pause()
    currentPlayingVoice.value.currentTime = 0
  }

  if (audio.paused) {
    audio.play()
    currentPlayingVoice.value = audio
  } else {
    audio.pause()
    audio.currentTime = 0
    currentPlayingVoice.value = null
  }
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

  let disabled = false
  if (kind === 'voice') {
    disabled = !message?.serverId
  } else if (kind === 'file') {
    disabled = !message?.fileMd5
  } else if (kind === 'image') {
    disabled = !message?.imageMd5
  } else if (kind === 'emoji') {
    disabled = !message?.emojiMd5
  } else if (kind === 'video') {
    if (message?.videoMd5) {
      disabled = false
      actualKind = 'video'
    } else if (message?.videoThumbMd5) {
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
      params.server_id = m.serverId
    } else if (kind === 'file') {
      params.md5 = m.fileMd5
    } else if (kind === 'image') {
      params.md5 = m.imageMd5
    } else if (kind === 'emoji') {
      params.md5 = m.emojiMd5
    } else if (kind === 'video') {
      params.md5 = m.videoMd5
    } else if (kind === 'video_thumb') {
      params.md5 = m.videoThumbMd5
    }

    await api.openChatMediaFolder(params)
  } finally {
    closeContextMenu()
  }
}

// 消息样式展示数据
// 计算属性：当前选中联系人的消息
const messages = computed(() => {
  if (!selectedContact.value) return []
  return allMessages.value[selectedContact.value.username] || []
})

const formatTimeDivider = (ts) => {
  if (!ts) return ''
  try {
    const d = new Date(Number(ts) * 1000)
    const now = new Date()
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
    if (sameDay) return `${hh}:${mm}`
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${m}-${dd} ${hh}:${mm}`
  } catch {
    return ''
  }
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

const getTransferTitle = (message) => {
  if (message.transferStatus) return message.transferStatus
  if (message.content && message.content !== '转账' && message.content !== '[转账]') {
    return message.content
  }
  const paySubType = String(message.paySubType || '').trim()
  switch (paySubType) {
    case '1': return '转账'
    case '3': return '接收转账'
    case '8': return '发起转账'
    case '4': return '已退回'
    case '9': return '已被退回'
    case '10': return '已过期'
    default: return '转账'
  }
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
const selectContact = (contact) => {
  selectedContact.value = contact
  loadMessages({ username: contact.username, reset: true })
}

// 已移除样式选择逻辑

// 默认选择第一个联系人
onMounted(() => {
  loadContacts()
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
}

const loadSessionsForSelectedAccount = async () => {
  const api = useApi()

  if (!selectedAccount.value) {
    contacts.value = []
    selectedContact.value = null
    return
  }

  const sessionsResp = await api.listChatSessions({
    account: selectedAccount.value,
    limit: 400,
    include_hidden: false,
    include_official: false
  })

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

  if (contacts.value.length > 0) {
    selectContact(contacts.value[0])
  }
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
  const normalizedImageUrl = msg.imageUrl || (msg.imageMd5 ? `${mediaBase}/api/chat/media/image?account=${encodeURIComponent(selectedAccount.value || '')}&md5=${encodeURIComponent(msg.imageMd5)}&username=${encodeURIComponent(selectedContact.value?.username || '')}` : '')
  const normalizedEmojiUrl = msg.emojiUrl || (msg.emojiMd5 ? `${mediaBase}/api/chat/media/emoji?account=${encodeURIComponent(selectedAccount.value || '')}&md5=${encodeURIComponent(msg.emojiMd5)}&username=${encodeURIComponent(selectedContact.value?.username || '')}` : '')
  const normalizedVideoThumbUrl = msg.videoThumbUrl || (msg.videoThumbMd5 ? `${mediaBase}/api/chat/media/video_thumb?account=${encodeURIComponent(selectedAccount.value || '')}&md5=${encodeURIComponent(msg.videoThumbMd5)}&username=${encodeURIComponent(selectedContact.value?.username || '')}` : '')
  const normalizedVideoUrl = msg.videoUrl || (msg.videoMd5 ? `${mediaBase}/api/chat/media/video?account=${encodeURIComponent(selectedAccount.value || '')}&md5=${encodeURIComponent(msg.videoMd5)}&username=${encodeURIComponent(selectedContact.value?.username || '')}` : '')
  const normalizedVoiceUrl = msg.voiceUrl || (msg.serverId ? `${mediaBase}/api/chat/media/voice?account=${encodeURIComponent(selectedAccount.value || '')}&server_id=${encodeURIComponent(String(msg.serverId))}` : '')

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
    title: msg.title || '',
    url: msg.url || '',
    imageMd5: msg.imageMd5 || '',
    emojiMd5: msg.emojiMd5 || '',
    emojiUrl: normalizedEmojiUrl || '',
    thumbUrl: msg.thumbUrl || '',
    imageUrl: normalizedImageUrl || '',
    videoMd5: msg.videoMd5 || '',
    videoThumbMd5: msg.videoThumbMd5 || '',
    videoThumbUrl: normalizedVideoThumbUrl || '',
    videoUrl: normalizedVideoUrl || '',
    quoteTitle: msg.quoteTitle || '',
    quoteContent,
    amount: msg.amount || '',
    coverUrl: msg.coverUrl || '',
    fileSize: msg.fileSize || '',
    fileMd5: msg.fileMd5 || '',
    paySubType: msg.paySubType || '',
    transferStatus: msg.transferStatus || '',
    voiceUrl: normalizedVoiceUrl || '',
    voiceDuration: msg.voiceDuration || '',
    preview: msg.thumbUrl || '',
    from: '',
    isGroup: !!selectedContact.value?.isGroup,
    avatar: msg.senderAvatar || fallbackAvatar || null,
    avatarColor: null
  }
}

const onGlobalClick = () => {
  if (contextMenu.value.visible) closeContextMenu()
}

onMounted(() => {
  if (!process.client) return
  document.addEventListener('click', onGlobalClick)
})

onUnmounted(() => {
  if (!process.client) return
  document.removeEventListener('click', onGlobalClick)
})

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

    const resp = await api.listChatMessages({
      account: selectedAccount.value,
      username,
      limit: messagePageSize,
      offset,
      order: 'asc'
    })

    const raw = resp?.messages || []
    const mapped = raw.map(normalizeMessage)

    if (activeMessagesFor.value !== username) {
      return
    }

    if (reset) {
      allMessages.value = {
        ...allMessages.value,
        [username]: mapped
      }
    } else {
      allMessages.value = {
        ...allMessages.value,
        [username]: [...mapped, ...existing]
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
  } catch (e) {
    messagesError.value = e?.message || '加载聊天记录失败'
  } finally {
    isLoadingMessages.value = false
  }
}

const loadMoreMessages = async () => {
  if (!selectedContact.value) return
  await loadMessages({ username: selectedContact.value.username, reset: false })
}

const refreshSelectedMessages = async () => {
  if (!selectedContact.value) return
  await loadMessages({ username: selectedContact.value.username, reset: true })
}

const autoLoadReady = ref(true)

const onMessageScroll = async () => {
  const c = messageContainerRef.value
  if (!c) return
  if (!selectedContact.value) return

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
    from: { type: String, default: '' }
  },
  setup(props) {
    return () => h(
      'a',
      {
        href: props.href,
        target: '_blank',
        rel: 'noreferrer',
        class: 'block max-w-sm w-full bg-white rounded-xl border border-neutral-200 overflow-hidden hover:bg-gray-50 transition-colors'
      },
      [
        props.preview ? h('div', { class: 'w-full bg-black/5' }, [
          h('img', { src: props.preview, alt: props.heading || '链接预览', class: 'w-full max-h-40 object-cover' })
        ]) : null,
        h('div', { class: 'px-3 py-2' }, [
          h('div', { class: 'text-sm font-medium text-gray-900 line-clamp-2' }, props.heading || props.href),
          props.abstract ? h('div', { class: 'text-xs text-gray-600 mt-1 line-clamp-2' }, props.abstract) : null,
          props.from ? h('div', { class: 'text-[10px] text-gray-400 mt-1 truncate' }, props.from) : null
        ])
      ].filter(Boolean)
    )
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
  border-radius: 8px;
  position: relative;
  z-index: 1;
}

/* 发送的消息（右侧绿色气泡） */
.sent-message {
  background-color: #95EB69 !important;
  border-radius: 8px;
}

.sent-message::after {
  content: '';
  position: absolute;
  top: 50%;
  right: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 12px;
  height: 12px;
  background-color: #95EB69;
  border-radius: 3px;
  z-index: -1;
}

/* 接收的消息（左侧白色气泡） */
.received-message {
  background-color: white !important;
  border-radius: 8px;
}

.received-message::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -4px;
  transform: translateY(-50%) rotate(45deg);
  width: 12px;
  height: 12px;
  background-color: white;
  border-radius: 3px;
  z-index: -1;
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
  color: #03C160;
}

.chat-tab:not(.selected):hover {
  color: #03C160;
}

/* 语音消息样式 */
.voice-message-wrap {
  display: flex;
  width: 100%;
}

.voice-bubble {
  border-radius: 8px;
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
  border-radius: 8px;
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
  z-index: -1;
}

.voice-received {
  border-radius: 8px;
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
  z-index: -1;
}

/* 隐私模式模糊效果 */
.privacy-blur {
  filter: blur(9px);
  transition: filter 0.2s ease;
}

.privacy-blur:hover {
  filter: blur(4px);
}
</style>