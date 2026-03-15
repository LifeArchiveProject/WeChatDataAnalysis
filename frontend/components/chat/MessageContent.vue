<template>
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
                      <FileTypeIcon :file-name="message.title" />
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
</template>

<script>
import { defineComponent } from 'vue'
import wechatPcLogoUrl from '~/assets/images/wechat/WeChat-Icon-Logo.wine.svg'
import ChatLocationCard from '~/components/ChatLocationCard.vue'
import FileTypeIcon from '~/components/chat/FileTypeIcon.vue'
import LinkCard from '~/components/chat/LinkCard.vue'

export default defineComponent({
  name: 'MessageContent',
  components: { ChatLocationCard, FileTypeIcon, LinkCard },
  props: {
    state: { type: Object, required: true },
    message: { type: Object, required: true }
  },
  setup(props) {
    return {
      ...props.state,
      message: props.message,
      wechatPcLogoUrl
    }
  }
})
</script>
