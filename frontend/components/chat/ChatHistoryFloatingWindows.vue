<template>
  <div
    v-for="win in floatingWindows"
    :key="win.id"
    class="fixed"
    :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.zIndex }"
    @mousedown="focusFloatingWindow(win.id)"
  >
    <div
      class="chat-floating-window rounded-xl overflow-hidden flex flex-col"
      :style="{ width: win.width + 'px', height: win.height + 'px' }"
    >
      <div
        class="chat-floating-window__header px-3 py-2 flex items-center justify-between select-none cursor-move"
        @mousedown.stop="startFloatingWindowDrag(win.id, $event)"
        @touchstart.stop="startFloatingWindowDrag(win.id, $event)"
      >
        <div class="chat-floating-window__title text-sm truncate min-w-0">
          {{ win.title || (win.kind === 'link' ? '链接' : '聊天记录') }}
        </div>
        <button
          type="button"
          class="chat-floating-window__close p-2 rounded flex-shrink-0"
          aria-label="关闭"
          title="关闭"
          @click.stop="closeFloatingWindow(win.id)"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="chat-floating-window__body flex-1 overflow-auto">
        <template v-if="win.kind === 'chatHistory'">
          <div v-if="win.loading" class="text-xs text-gray-500 text-center py-2">加载中...</div>
          <div v-if="!win.records || !win.records.length" class="text-sm text-gray-500 text-center py-10">
            没有可显示的聊天记录
          </div>
          <template v-else>
            <div
              v-for="(rec, idx) in win.records"
              :key="rec.id || idx"
              class="chat-floating-window__row px-4 py-3 flex gap-3"
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
                  <div
                    v-if="rec.renderType === 'chatHistory'"
                    class="wechat-chat-history-card wechat-special-card msg-radius cursor-pointer"
                    @click.stop="openNestedChatHistory(rec)"
                  >
                    <div class="wechat-chat-history-body">
                      <div class="wechat-chat-history-title">{{ rec.title || '聊天记录' }}</div>
                      <div v-if="getChatHistoryPreviewLines(rec).length" class="wechat-chat-history-preview">
                        <div
                          v-for="(line, lineIndex) in getChatHistoryPreviewLines(rec)"
                          :key="lineIndex"
                          class="wechat-chat-history-line"
                        >
                          {{ line }}
                        </div>
                      </div>
                    </div>
                    <div class="wechat-chat-history-bottom"><span>聊天记录</span></div>
                  </div>

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
                          <img
                            :src="rec.preview"
                            :alt="rec.title || '链接预览'"
                            class="wechat-link-thumb-img"
                            referrerpolicy="no-referrer"
                            loading="lazy"
                            decoding="async"
                            @error="onChatHistoryLinkPreviewError(rec)"
                          />
                        </div>
                      </div>
                    </div>
                    <div class="wechat-link-from">
                      <div class="wechat-link-from-avatar" :style="rec._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                        <span v-if="!rec.fromAvatar || !rec._fromAvatarImgOk">{{ getChatHistoryLinkFromAvatarText(rec) || '\u200B' }}</span>
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

                  <MessageContent
                    v-else-if="rec.renderType === 'voice'"
                    :message="voiceRecordMessage(win, rec, idx)"
                    :state="messageState"
                    :hide-type-footer="true"
                  />

                  <div
                    v-else-if="rec.renderType === 'image'"
                    class="msg-radius overflow-hidden cursor-pointer inline-block"
                    @click="rec.imageUrl && openImagePreview(rec.imageUrl)"
                    @contextmenu="openMediaContextMenu($event, rec, 'image')"
                  >
                    <img v-if="rec.imageUrl" :src="rec.imageUrl" alt="图片" class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity" />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[图片]' }}</div>
                  </div>

                  <div
                    v-else-if="rec.renderType === 'emoji'"
                    class="inline-block"
                    :class="rec.emojiUrl ? 'cursor-pointer' : ''"
                    @click="rec.emojiUrl && openImagePreview(rec.emojiUrl)"
                    @contextmenu="openMediaContextMenu($event, rec, 'emoji')"
                  >
                    <img v-if="rec.emojiUrl" :src="rec.emojiUrl" alt="表情" class="w-24 h-24 object-contain hover:opacity-90 transition-opacity" />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[表情]' }}</div>
                  </div>

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
                      aria-label="播放视频"
                      @click.stop="openVideoPreview(rec.videoUrl, rec.videoThumbUrl)"
                    >
                      <span class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                      </span>
                    </button>
                    <div v-if="rec.videoDuration" class="absolute bottom-2 right-2 text-xs text-white bg-black/55 px-1.5 py-0.5 rounded">
                      {{ formatChatHistoryVideoDuration(rec.videoDuration) }}
                    </div>
                  </div>

                  <div
                    v-else
                    class="text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                    @contextmenu="openMediaContextMenu($event, rec, 'message')"
                  >
                    <template v-for="(segment, segmentIndex) in recordTextSegments(rec.content)" :key="segmentIndex">
                      <span v-if="segment.type === 'text'">{{ segment.content }}</span>
                      <a
                        v-else-if="segment.type === 'link'"
                        class="chat-history-text-link"
                        :href="segment.url"
                        target="_blank"
                        rel="noopener noreferrer"
                        @click.prevent.stop="openRecordUrl(segment.url)"
                      >{{ segment.content }}</a>
                      <img v-else :src="segment.emojiSrc" :alt="segment.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </template>

        <template v-else-if="win.kind === 'link'">
          <div class="p-4 space-y-3">
            <div
              class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
              @click.stop="win.url && openRecordUrl(win.url)"
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
                  <span v-if="!win.fromAvatar || !win._fromAvatarImgOk">{{ getChatHistoryLinkFromAvatarText(win) || '\u200B' }}</span>
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
                @click.stop="win.url && openRecordUrl(win.url)"
              >
                在浏览器打开
              </button>
              <button
                class="px-3 py-1.5 text-sm rounded-md border border-gray-200 bg-white hover:bg-gray-50"
                type="button"
                :disabled="!win.url"
                :class="!win.url ? 'opacity-50 cursor-not-allowed' : ''"
                @click.stop="win.url && copyRecordUrl(win.url)"
              >
                复制链接
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'
import MessageContent from '~/components/chat/MessageContent.vue'
import { linkifyMessageSegments, openMessageExternalUrl } from '~/lib/chat/message-links'

export default defineComponent({
  name: 'ChatHistoryFloatingWindows',
  components: { MessageContent },
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    const recordTextSegments = (content) => {
      const parser = props.state?.parseTextWithEmoji
      const segments = typeof parser === 'function'
        ? parser(String(content || ''))
        : [{ type: 'text', content: String(content || '') }]
      return linkifyMessageSegments(segments)
    }

    const openRecordUrl = (url) => {
      if (typeof props.state?.openUrlInBrowser === 'function') {
        props.state.openUrlInBrowser(url)
        return
      }
      void openMessageExternalUrl(url)
    }

    const copyRecordUrl = async (url) => {
      if (typeof props.state?.copyTextToClipboard === 'function') {
        await props.state.copyTextToClipboard(url)
        return
      }
      try { await navigator.clipboard.writeText(String(url || '')) } catch {}
    }

    const voiceRecordMessage = (win, record, index) => ({
      ...record,
      id: String(record?.id || `${win?.id || 'chat-history'}-voice-${index}`),
      isSent: false,
      voiceRead: true,
      content: String(record?.content || '[语音]')
    })

    return {
      ...props.state,
      messageState: props.state,
      recordTextSegments,
      openRecordUrl,
      copyRecordUrl,
      voiceRecordMessage
    }
  }
})
</script>

<style scoped>
.chat-history-text-link {
  color: #245fbd;
  cursor: pointer;
  overflow-wrap: anywhere;
  text-decoration: none;
}

.chat-history-text-link:hover {
  color: #174a99;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
