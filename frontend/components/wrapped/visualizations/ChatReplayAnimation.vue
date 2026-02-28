<template>
  <div class="wrapped-chat-replay">
    <!-- Top bar -->
    <div class="wrapped-chat-replay__top">
      <div class="wrapped-chat-replay__top-left">
        <div class="wrapped-chat-replay__avatar wrapped-privacy-avatar">
          <img
            v-if="resolvedAvatarUrl && avatarOk"
            :src="resolvedAvatarUrl"
            alt="avatar"
            @error="onAvatarError"
          />
          <span v-else class="wrapped-chat-replay__avatar-fallback wrapped-number">
            {{ avatarFallback }}
          </span>
        </div>

        <div class="min-w-0">
          <div class="wrapped-label text-[10px] text-[#00000066]">{{ label }}</div>
          <div class="wrapped-body text-sm text-[#000000e6] truncate wrapped-privacy-name" :title="displayName">
            {{ displayNameShown }}
          </div>
        </div>
      </div>

      <div class="wrapped-chat-replay__top-right">
        <div class="wrapped-label text-[10px] text-[#00000066]">聊天回放</div>
        <div v-if="showTimestamp" class="wrapped-label text-[10px] text-[#00000055]">
          {{ date }} {{ time }}
        </div>
      </div>
    </div>

    <!-- Chat area -->
    <div class="wrapped-chat-replay__chat">
      <div class="wrapped-chat-replay__row">
        <div v-if="showTyping" class="wrapped-chat-replay__typing" aria-label="typing">
          <span class="wrapped-chat-replay__dot" />
          <span class="wrapped-chat-replay__dot" />
          <span class="wrapped-chat-replay__dot" />
        </div>

        <transition name="wrapped-chat-replay-slide">
          <div v-if="showBubble" class="wrapped-chat-replay__bubble">
            <div class="wrapped-chat-replay__bubble-text wrapped-privacy-message" :title="content">
              {{ typedText }}
            </div>
          </div>
        </transition>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  time: { type: String, default: '' }, // "05:23"
  date: { type: String, default: '' }, // "2024-01-15"
  displayName: { type: String, default: '' }, // 发送对象名称
  maskedName: { type: String, default: '' }, // 脱敏名称
  avatarUrl: { type: String, default: '' }, // 头像URL
  content: { type: String, default: '' }, // 消息内容
  label: { type: String, default: '' }, // "最早的一条" / "最晚的一条"
  delay: { type: Number, default: 0 }, // 动画开始延迟（ms）
  privacyMode: { type: Boolean, default: false } // 是否启用隐私模糊
})

const showTyping = ref(false)
const showBubble = ref(false)
const typedText = ref('')
const showTimestamp = ref(false)

const avatarOk = ref(true)
const onAvatarError = () => { avatarOk.value = false }

const displayNameShown = computed(() => String(props.displayName || props.maskedName || '').trim())

const apiBase = useApiBase()
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    // qpic/qlogo are often hotlink-protected; proxy via backend (same as chat page).
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw.startsWith('/') ? raw : `/${raw}`
}

const resolvedAvatarUrl = computed(() => resolveMediaUrl(props.avatarUrl))
const avatarFallback = computed(() => {
  const s = displayNameShown.value
  return s ? s[0] : '?'
})

let timers = []
let typingTimer = null

const cleanup = () => {
  for (const t of timers) clearTimeout(t)
  timers = []
  if (typingTimer) clearTimeout(typingTimer)
  typingTimer = null
}

const reset = () => {
  showTyping.value = false
  showBubble.value = false
  typedText.value = ''
  showTimestamp.value = false
  avatarOk.value = true
}

const startTyping = () => {
  const chars = Array.from(String(props.content || ''))
  if (chars.length === 0) {
    showTimestamp.value = true
    return
  }

  let i = 0
  const step = () => {
    i += 1
    typedText.value = chars.slice(0, i).join('')
    if (i >= chars.length) {
      showTimestamp.value = true
      typingTimer = null
      return
    }
    typingTimer = setTimeout(step, 50)
  }

  step()
}

const start = () => {
  cleanup()
  reset()

  const base = Math.max(0, Number(props.delay) || 0)

  timers.push(setTimeout(() => { showTyping.value = true }, base + 500))
  timers.push(setTimeout(() => {
    showTyping.value = false
    showBubble.value = true
  }, base + 1500))
  timers.push(setTimeout(() => { startTyping() }, base + 1700))
}

onMounted(start)
onBeforeUnmount(cleanup)

watch(
  () => [props.time, props.date, props.displayName, props.maskedName, props.avatarUrl, props.content, props.label, props.delay],
  () => start()
)
</script>

<style>
.wrapped-chat-replay {
  /* 微信风格 CSS 变量 */
  --wr-chat-frame-bg: #EDEDED;
  --wr-chat-top-bg: #EDEDED;
  --wr-chat-chat-bg: #EDEDED;
  --wr-chat-border: transparent;

  --wr-chat-bubble-bg: #95EC69;
  --wr-chat-bubble-tail: #95EC69;
  --wr-chat-bubble-text: #000000;

  --wr-chat-typing-bg: #FFFFFF;
  --wr-chat-typing-dot: rgba(0, 0, 0, 0.55);

  background: var(--wr-chat-frame-bg);
  border: none;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.wrapped-chat-replay__top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--wr-chat-top-bg);
  border-bottom: none;
}

.wrapped-chat-replay__top-right {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  text-align: right;
}

.wrapped-chat-replay__top-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.wrapped-chat-replay__avatar {
  width: 34px;
  height: 34px;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wrapped-chat-replay__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.wrapped-chat-replay__avatar-fallback {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.55);
}

.wrapped-chat-replay__chat {
  padding: 10px 12px;
  background: var(--wr-chat-chat-bg);
  min-height: 90px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.wrapped-chat-replay__row {
  display: flex;
  justify-content: flex-end;
  align-items: flex-end;
  gap: 10px;
  min-height: 36px;
}

.wrapped-chat-replay__typing,
.wrapped-chat-replay__bubble {
  max-width: 82%;
  position: relative;
  border-radius: 4px;
}

.wrapped-chat-replay__typing {
  background: var(--wr-chat-typing-bg);
  padding: 10px 12px;
}

.wrapped-chat-replay__bubble {
  background: var(--wr-chat-bubble-bg);
  padding: 10px 12px;
}

.wrapped-chat-replay__bubble-text {
  color: var(--wr-chat-bubble-text) !important;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}

.wrapped-chat-replay__dot {
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  background: var(--wr-chat-typing-dot);
  display: inline-block;
  margin-right: 4px;
  animation: wrapped-chat-replay-dot 1s infinite ease-in-out;
}

.wrapped-chat-replay__dot:nth-child(2) { animation-delay: 0.15s; }
.wrapped-chat-replay__dot:nth-child(3) { animation-delay: 0.3s; }
.wrapped-chat-replay__dot:last-child { margin-right: 0; }

@keyframes wrapped-chat-replay-dot {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.55; }
  40% { transform: translateY(-3px); opacity: 1; }
}

.wrapped-chat-replay-slide-enter-active {
  transition: opacity 220ms ease, transform 220ms ease;
}
.wrapped-chat-replay-slide-enter-from {
  opacity: 0;
  transform: translateX(18px);
}
.wrapped-chat-replay-slide-enter-to {
  opacity: 1;
  transform: translateX(0);
}
</style>
