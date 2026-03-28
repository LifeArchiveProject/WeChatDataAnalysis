<template>
    <div
      class="session-list-panel border-r flex flex-col min-h-0 shrink-0 relative"
      :style="{ '--session-list-width': sessionListWidth + 'px' }"
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
        <div class="session-list-search p-3 border-b">
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
              v-if="showSearchAccountSwitcher"
              v-model="selectedAccount"
              @change="onAccountChange"
              class="account-select"
            >
              <option v-if="!availableAccounts.length" disabled value="">{{ chatAccounts.loading ? '加载中...' : (chatAccounts.error || '无数据库') }}</option>
              <option v-for="acc in availableAccounts" :key="acc" :value="acc">{{ acc }}</option>
            </select>
          </div>
        </div>

        <!-- 联系人列表 -->
        <div class="session-list-scroll flex-1 overflow-y-auto min-h-0">
          <div v-if="isLoadingContacts" class="px-3 py-4 h-full overflow-hidden">
            <div v-for="i in 15" :key="i" class="flex items-center space-x-3 h-[calc(80px/var(--dpr))]">
              <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md bg-gray-200 skeleton-pulse"></div>
              <div class="flex-1 space-y-2">
                <div class="h-3.5 bg-gray-200 rounded skeleton-pulse" :style="{ width: (60 + (i % 4) * 15) + 'px' }"></div>
                <div class="h-3 bg-gray-200 rounded skeleton-pulse" :style="{ width: (80 + (i % 3) * 20) + 'px' }"></div>
              </div>
            </div>
          </div>
          <div v-else-if="contactsError" class="session-list-status px-3 py-2 text-sm text-red-500 whitespace-pre-wrap">
            {{ contactsError }}
          </div>
          <div v-else-if="contacts.length === 0" class="session-list-status px-3 py-2 text-sm">
            暂无会话
          </div>
          <div v-else class="pb-4">
            <div v-for="contact in filteredContacts" :key="contact.id"
              class="session-list-item px-3 cursor-pointer transition-colors duration-150 h-[calc(80px/var(--dpr))] flex items-center"
              :class="{
                'session-list-item--top': contact.isTop,
                'session-list-item--selected': selectedContact?.id === contact.id
              }"
              @click="selectContact(contact)">
              <div class="flex items-center space-x-3 w-full">
                <!-- 联系人头像 -->
                <div class="relative flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                  <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md overflow-hidden bg-gray-300">
                    <div v-if="contact.avatar" class="w-full h-full">
                      <img :src="contact.avatar" :alt="contact.name" class="w-full h-full object-cover" loading="lazy" referrerpolicy="no-referrer" @error="onAvatarError($event, contact)">
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
                    <h3 class="session-list-item-name text-sm truncate" :class="{ 'privacy-blur': privacyMode }">{{ contact.name }}</h3>
                    <div class="flex items-center flex-shrink-0 ml-2">
                      <span class="session-list-item-time text-xs">{{ contact.lastMessageTime }}</span>
                    </div>
                  </div>
                  <p class="session-list-item-preview text-xs truncate mt-0.5 leading-tight" :class="{ 'privacy-blur': privacyMode }">
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
          </div>
        </div>
      </div>

      <!-- 样式展示列表已移除 -->
    </div>
</template>

<script>
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'SessionListPanel',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    return { ...props.state }
  }
})
</script>
