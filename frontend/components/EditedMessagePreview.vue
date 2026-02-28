<template>
  <div v-if="!message" class="flex items-center justify-center py-4">
    <span class="text-sm text-gray-400">（无数据）</span>
  </div>

  <!-- 完全复用聊天页消息结构：外层 flex + 头像 + 气泡 -->
  <div v-else class="flex items-center" :class="message.isSent ? 'justify-end' : 'justify-start'">
    <div class="flex items-start" :class="message.isSent ? 'flex-row-reverse' : ''">
      <!-- 头像（与聊天页完全一致） -->
      <div class="relative">
        <div
          class="w-[calc(42px/var(--dpr,1))] h-[calc(42px/var(--dpr,1))] rounded-md overflow-hidden bg-gray-300 flex-shrink-0"
          :class="message.isSent ? 'ml-3' : 'mr-3'"
        >
          <div v-if="resolvedAvatar" class="w-full h-full">
            <img
              :src="resolvedAvatar"
              alt="avatar"
              class="w-full h-full object-cover"
              referrerpolicy="no-referrer"
            />
          </div>
          <div
            v-else
            class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
            :style="{ backgroundColor: message.avatarColor || (message.isSent ? '#4B5563' : '#6B7280') }"
          >
            {{ avatarLetter }}
          </div>
        </div>
      </div>

      <!-- 消息内容气泡（与聊天页完全一致） -->
      <div
        class="flex flex-col relative group"
        :class="message.isSent ? 'items-end' : 'items-start'"
      >
        <!-- 群聊发送者名（可选） -->
        <div
          v-if="senderName && !message.isSent"
          class="text-[11px] text-gray-500 mb-1"
          :class="message.isSent ? 'text-right' : 'text-left'"
        >
          {{ senderName }}
        </div>

        <!-- 时间悬浮 tooltip -->
        <div
          v-if="message.fullTime"
          class="absolute -top-6 z-10 rounded bg-black/70 text-white text-[10px] px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap"
          :class="message.isSent ? 'right-0' : 'left-0'"
        >
          {{ message.fullTime }}
        </div>

        <!-- 表情 -->
        <div v-if="renderType === 'emoji' && message.emojiUrl">
          <img :src="normalizeMaybeUrl(message.emojiUrl)" alt="emoji" class="w-24 h-24 object-contain" />
        </div>

        <!-- 图片 -->
        <div v-else-if="renderType === 'image' && message.imageUrl" class="max-w-sm">
          <div class="msg-radius overflow-hidden">
            <img :src="normalizeMaybeUrl(message.imageUrl)" alt="图片" class="max-w-[240px] max-h-[240px] object-cover" />
          </div>
        </div>

        <!-- 视频 -->
        <div
          v-else-if="renderType === 'video'"
          class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
          :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'"
        >
          [视频]
        </div>

        <!-- 语音 -->
        <div
          v-else-if="renderType === 'voice'"
          class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
          :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'"
        >
          [语音]
        </div>

        <!-- 默认文本消息 -->
        <div
          v-else
          class="px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
          :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'"
        >
          {{ message.content || '' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  message: { type: Object, default: null },
})

const apiBase = useApiBase()

const normalizeMaybeUrl = (u) => {
  const raw = String(u || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw) || /^blob:/i.test(raw) || /^data:/i.test(raw)) return raw
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw
}

const renderType = computed(() => String(props.message?.renderType || '').trim())

const resolvedAvatar = computed(() => {
  const m = props.message
  if (!m) return ''
  return normalizeMaybeUrl(m.avatar || m.senderAvatar || '')
})

const avatarLetter = computed(() => {
  const m = props.message
  if (!m) return '?'
  const name = m.senderDisplayName || m.senderUsername || m.sender || ''
  return name.charAt(0) || '?'
})

const senderName = computed(() => {
  const m = props.message
  if (!m) return ''
  return m.senderDisplayName || m.senderUsername || ''
})
</script>
