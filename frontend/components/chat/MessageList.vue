<template>
  <div ref="messageContainerRef" class="message-list flex-1 overflow-y-auto p-4 min-h-0" @scroll="onMessageScroll">
    <div v-if="selectedContact && hasMoreMessages" class="flex justify-center mb-4">
      <div
        class="message-list-load-more text-xs px-3 py-1 rounded-md border select-none"
        :class="isLoadingMessages ? 'opacity-60' : 'hover:bg-gray-50 cursor-pointer'"
        @click="!isLoadingMessages && loadMoreMessages()"
      >
        {{ isLoadingMessages ? '加载中...' : '继续上滑加载更多' }}
      </div>
    </div>

    <div v-if="isLoadingMessages && messages.length === 0" class="message-list-status text-center text-sm py-6">
      加载中...
    </div>
    <div v-else-if="messagesError" class="text-center text-sm text-red-500 py-6 whitespace-pre-wrap">
      {{ messagesError }}
    </div>
    <div v-else-if="messages.length === 0" class="message-list-status text-center text-sm py-6">
      暂无聊天记录
    </div>

    <MessageItem
      v-for="message in renderMessages"
      :key="message.id"
      :message="message"
      :state="state"
    />
  </div>
</template>

<script>
import { defineComponent } from 'vue'
import MessageItem from '~/components/chat/MessageItem.vue'

export default defineComponent({
  name: 'MessageList',
  components: { MessageItem },
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
