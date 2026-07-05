<template>
  <div
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
      <div class="message-time-divider px-3 py-1 text-xs">
        {{ message.timeDivider }}
      </div>
    </div>

    <div v-if="message.renderType === 'system'" class="flex justify-center">
      <div class="message-time-divider px-3 py-1 text-xs">
        {{ message.content }}
      </div>
    </div>

    <div v-else class="flex items-center" :class="message.isSent ? 'justify-end' : 'justify-start'">
      <div class="flex items-start max-w-md" :class="message.isSent ? 'flex-row-reverse' : ''">
        <div
          class="relative"
          @mouseenter="onMessageAvatarMouseEnter(message)"
          @mouseleave="onMessageAvatarMouseLeave"
        >
          <div class="w-[calc(42px/var(--dpr))] h-[calc(42px/var(--dpr))] rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="[message.isSent ? 'ml-3' : 'mr-3', { 'privacy-blur': privacyMode }]">
            <div v-if="message.avatar" class="w-full h-full">
              <img
                v-chat-lazy-src="message.avatar"
                :alt="message.sender + '的头像'"
                class="w-full h-full object-cover"
                loading="lazy"
                decoding="async"
                fetchpriority="low"
                referrerpolicy="no-referrer"
                v-chat-media-perf="{ kind: 'message-avatar', meta: { conversation: selectedContact?.username || '', messageId: message.id, serverId: message.serverIdStr || '', senderUsername: message.senderUsername || '' } }"
                @error="onAvatarError($event, message)"
              >
            </div>
            <div
              v-else
              class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
              :style="{ backgroundColor: message.avatarColor || (message.isSent ? '#4B5563' : '#6B7280') }"
            >
              {{ message.sender.charAt(0) }}
            </div>
          </div>

          <ContactProfileCard
            v-if="contactProfileCardOpen && contactProfileCardMessageId === String(message.id ?? '')"
            :state="state"
            class="absolute z-40 w-[360px] max-w-[88vw]"
            :class="message.isSent ? 'right-0 top-[calc(100%+8px)]' : 'left-0 top-[calc(100%+8px)]'"
          />
        </div>

        <div
          class="flex flex-col relative group"
          :class="[message.isSent ? 'items-end' : 'items-start', { 'privacy-blur': privacyMode }]"
          @contextmenu="openMediaContextMenu($event, message, 'message')"
        >
          <div v-if="message.isGroup && !message.isSent && message.senderDisplayName" class="message-sender-name text-[11px] mb-1" :class="message.isSent ? 'text-right' : 'text-left'">
            {{ message.senderDisplayName }}
          </div>
          <div
            class="absolute -top-6 z-10 rounded bg-black/70 text-white text-[10px] px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap"
            :class="message.isSent ? 'right-0' : 'left-0'"
          >
            {{ message.fullTime }}
          </div>

          <MessageContent :message="message" :state="state" />

          <ContactProfileCard
            v-if="isMentionContactProfileCardForMessage && isMentionContactProfileCardForMessage(message)"
            :state="state"
            class="absolute z-40 w-[360px] max-w-[88vw]"
            :class="message.isSent ? 'right-0 top-[calc(100%+8px)]' : 'left-0 top-[calc(100%+8px)]'"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'
import ContactProfileCard from '~/components/chat/ContactProfileCard.vue'
import MessageContent from '~/components/chat/MessageContent.vue'

export default defineComponent({
  name: 'MessageItem',
  components: { ContactProfileCard, MessageContent },
  props: {
    state: { type: Object, required: true },
    message: { type: Object, required: true }
  },
  setup(props) {
    return {
      ...props.state,
      message: props.message
    }
  }
})
</script>

<style scoped>
.chat-contact-card {
  background-color: var(--app-surface-bg);
  border: 1px solid var(--app-border);
  color: var(--app-text-primary);
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.16);
}

html[data-theme='dark'] .chat-contact-card {
  box-shadow: 0 24px 56px rgba(0, 0, 0, 0.42);
}

.chat-contact-card .bg-white {
  background-color: var(--app-surface-bg);
}

.chat-contact-card [class*='bg-[#F6F6F6]'] {
  background-color: var(--app-surface-soft);
}

.chat-contact-card .bg-gray-200 {
  background-color: var(--app-border-soft);
}

.chat-contact-card :is(.border-gray-100, .border-gray-200, .border-gray-300) {
  border-color: var(--app-border);
}

.chat-contact-card :is(.text-gray-900, .text-gray-800, .text-gray-700) {
  color: var(--app-text-primary);
}

.chat-contact-card :is(.text-gray-600, .text-gray-500, .text-gray-400) {
  color: var(--app-text-muted);
}
</style>
