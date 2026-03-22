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
                :src="message.avatar"
                :alt="message.sender + '的头像'"
                class="w-full h-full object-cover"
                referrerpolicy="no-referrer"
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

          <div
            v-if="contactProfileCardOpen && contactProfileCardMessageId === String(message.id ?? '')"
            class="chat-contact-card absolute z-40 w-[360px] max-w-[88vw] rounded-lg overflow-hidden"
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
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'
import MessageContent from '~/components/chat/MessageContent.vue'

export default defineComponent({
  name: 'MessageItem',
  components: { MessageContent },
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
