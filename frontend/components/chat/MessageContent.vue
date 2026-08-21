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
                  <ImageGroupStack
                    v-else-if="message.renderType === 'image' && message.imageGroupCollapsed"
                    :message="message"
                    :state="state"
                  />
                  <div v-else-if="message.renderType === 'image'"
                    class="max-w-sm flex items-center group"
                    :class="message.isSent ? 'flex-row-reverse' : ''">
                  <div
                    class="msg-radius overflow-hidden cursor-pointer flex-shrink-0"
                    :class="message.isSent ? '' : ''"
                    :data-image-group-key="message.imageGroupKey || undefined"
                    :data-image-group-item-index="message.imageGroupExpanded ? message.imageGroupItemIndex : undefined"
                    :data-image-group-message-id="message.imageGroupExpanded ? message.id : undefined"
                    @click="message.imageUrl && openImagePreview(message.imageUrl)"
                    @contextmenu="openMediaContextMenu($event, message, 'image')"
                  >
                      <img
                        v-if="message.imageUrl && !message._imageRenderError"
                        v-chat-lazy-src="imageGroupLazySource(message)"
                        alt="图片"
                        class="block min-w-[96px] min-h-[96px] max-w-[240px] max-h-[240px] object-cover bg-gray-100 hover:opacity-90 transition-opacity"
                        loading="lazy"
                        decoding="async"
                        fetchpriority="low"
                        v-chat-media-perf="{ kind: 'message-image', meta: { conversation: selectedContact?.username || '', messageId: message.id, serverId: message.serverIdStr || '', imageMd5: message.imageMd5 || '', imageFileId: message.imageFileId || '' } }"
                        @error="onMessageImageRenderError(message)"
                      >
                      <div v-else-if="message.imageUrl" class="wechat-media-placeholder wechat-media-placeholder--image">
                        <i class="fa-regular fa-image" aria-hidden="true"></i>
                        <span>图片未缓存</span>
                      </div>
                      <div v-else class="px-3 py-1.5 text-[13px] max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                        :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                        {{ message.content }}
                      </div>
                    </div>
                    <button
                      v-if="message.imageGroupExpanded && message.imageGroupIsFirst"
                      type="button"
                      class="image-group-collapse"
                      :class="message.isSent ? 'mr-2' : 'ml-2'"
                      :disabled="imageGroupTransitioning"
                      :data-image-group-control-key="message.imageGroupKey || ''"
                      @click.stop="toggleImageGroupWithTransition(message.imageGroupKey)"
                    >
                      收起 {{ message.imageGroupProtocolCount || message.imageGroupItems?.length || '' }}
                    </button>
                    <div
                      v-if="shouldShowImageLargeReload(message)"
                      class="flex max-w-[260px] flex-col gap-1"
                      :class="message.isSent ? 'mr-2' : 'ml-2'"
                    >
                      <button
                        type="button"
                        class="whitespace-nowrap rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 opacity-0 shadow-sm transition-opacity hover:bg-gray-50 focus:opacity-100 group-hover:opacity-100 disabled:cursor-wait disabled:opacity-60"
                        :disabled="!!message._imageLargeLoading"
                        title="先从微信本地目录查找大图；本地没有时通过原图接口获取。"
                        @click.stop.prevent="onTryLoadLargeImageClick(message)"
                      >
                        {{ message._imageLargeLoading ? '获取中...' : '尝试加载大图' }}
                      </button>
                      <ErrorNotice
                        v-if="message._imageLargeError"
                        :message="message._imageLargeError"
                        compact
                        class="text-[11px] text-red-600"
                      />
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'video'" class="max-w-sm">
                    <div class="msg-radius overflow-hidden relative bg-black/5" @contextmenu="openMediaContextMenu($event, message, 'video')">
                      <img
                        v-if="message.videoThumbUrl && !message._videoThumbRenderError"
                        v-chat-lazy-src="message.videoThumbUrl"
                        alt="视频"
                        class="block w-[220px] min-h-[120px] max-w-[260px] h-auto max-h-[260px] object-cover bg-gray-100"
                        loading="lazy"
                        decoding="async"
                        fetchpriority="low"
                        v-chat-media-perf="{ kind: 'message-video-thumb', meta: { conversation: selectedContact?.username || '', messageId: message.id, serverId: message.serverIdStr || '', videoThumbMd5: message.videoThumbMd5 || '', videoThumbFileId: message.videoThumbFileId || '' } }"
                        @error="onMessageVideoThumbRenderError(message)"
                      >
                      <div v-else-if="message.videoThumbUrl" class="wechat-media-placeholder wechat-media-placeholder--video">
                        <i class="fa-solid fa-video" aria-hidden="true"></i>
                        <span>视频未缓存</span>
                      </div>
                      <div v-else class="px-3 py-1.5 text-[13px] relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
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
                    :class="message.isSent ? 'wechat-voice-wrapper--sent' : 'wechat-voice-wrapper--received'"
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
                    <div
                      v-if="!privacyMode && (
                        typeof transcribeVoice === 'function'
                        || typeof transcribeVoiceLocally === 'function'
                        || message.voiceTranscriptStatus === 'success'
                        || !!message.voiceTranscript
                      )"
                      class="wechat-voice-transcript"
                      :class="[
                        message.isSent ? 'wechat-voice-transcript--sent' : 'wechat-voice-transcript--received',
                        message.voiceTranscriptStatus === 'error' ? 'wechat-voice-transcript--error' : '',
                        isVoiceTranscriptActionState(message) ? 'wechat-voice-transcript--actions' : ''
                      ]"
                    >
                      <template v-if="isVoiceTranscriptIdle(message)">
                        <div class="wechat-voice-transcript__actions" role="group" aria-label="语音转文字">
                          <button
                            v-if="typeof transcribeVoice === 'function' && nativeVoiceTranscriptionAvailable"
                            type="button"
                            class="wechat-voice-transcript__action wechat-voice-transcript__action--wechat"
                            title="使用微信转文字"
                            aria-label="微信转文字"
                            @click.stop="transcribeVoice(message)"
                          >
                            <img :src="wechatPcLogoUrl" alt="" aria-hidden="true" class="wechat-voice-transcript__icon wechat-voice-transcript__icon--wechat">
                            <span>微信转文字</span>
                          </button>
                          <button
                            v-if="canShowLocalVoiceAction(message)"
                            type="button"
                            class="wechat-voice-transcript__action wechat-voice-transcript__action--local wechat-voice-transcript__local-action"
                            :title="voiceLocalActionTitle()"
                            aria-label="本地转文字"
                            @click.stop="transcribeVoiceLocally(message)"
                          >
                            <i class="fa-solid fa-language wechat-voice-transcript__icon" aria-hidden="true"></i>
                            <span>本地转文字</span>
                          </button>
                        </div>
                        <span
                          v-if="!nativeVoiceTranscriptionStatusKnown || nativeVoiceTranscriptionStatusLoading || !voiceTranscriptionStatusKnown || voiceTranscriptionStatusLoading"
                          class="wechat-voice-transcript__status"
                          role="status"
                        >正在检查转写能力…</span>
                      </template>
                      <span v-else-if="message.voiceTranscriptStatus === 'loading'" class="wechat-voice-transcript__status" role="status">
                        <i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>
                        正在转文字…
                      </span>
                      <template v-else-if="message.voiceTranscriptStatus === 'success' || !!message.voiceTranscript">
                        <span
                          class="wechat-voice-transcript__source"
                          :class="`wechat-voice-transcript__source--${voiceTranscriptSourceKey(message)}`"
                          :data-transcript-source="voiceTranscriptSourceKey(message)"
                          :title="voiceTranscriptSourceTitle(message)"
                        >{{ voiceTranscriptSourceLabel(message) }}</span>
                        <p class="wechat-voice-transcript__text">{{ message.voiceTranscript || '未识别到文字' }}</p>
                      </template>
                      <template v-else>
                        <span class="wechat-voice-transcript__error">{{ message.voiceTranscriptError || '语音识别失败' }}</span>
                        <div class="wechat-voice-transcript__actions" role="group" aria-label="重新转文字">
                          <button
                            v-if="typeof transcribeVoice === 'function' && nativeVoiceTranscriptionAvailable && !nativeVoiceTranscriptionStatusLoading"
                            type="button"
                            class="wechat-voice-transcript__action wechat-voice-transcript__action--wechat wechat-voice-transcript__retry"
                            title="重试微信转文字"
                            aria-label="微信转文字"
                            @click.stop="transcribeVoice(message)"
                          >
                            <img :src="wechatPcLogoUrl" alt="" aria-hidden="true" class="wechat-voice-transcript__icon wechat-voice-transcript__icon--wechat">
                            <span>微信转文字</span>
                          </button>
                          <button
                            v-if="canShowLocalVoiceAction(message, true)"
                            type="button"
                            class="wechat-voice-transcript__action wechat-voice-transcript__action--local wechat-voice-transcript__local-action"
                            :title="voiceLocalActionTitle()"
                            aria-label="本地转文字"
                            @click.stop="transcribeVoiceLocally(message, { force: true })"
                          >
                            <i class="fa-solid fa-language wechat-voice-transcript__icon" aria-hidden="true"></i>
                            <span>本地转文字</span>
                          </button>
                        </div>
                        <span
                          v-if="!voiceTranscriptionAvailable && (!voiceTranscriptionStatusKnown || voiceTranscriptionStatusLoading)"
                          class="wechat-voice-transcript__status"
                          role="status"
                        >正在检查本地模型…</span>
                        <span
                          v-else-if="!voiceTranscriptionAvailable"
                          class="wechat-voice-transcript__error"
                        >本地模型未就绪</span>
                      </template>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'voip'"
                    class="wechat-voip-bubble msg-radius"
                    :class="message.isSent ? 'wechat-voip-sent' : 'wechat-voip-received'">
                    <div class="wechat-voip-content" :class="message.isSent ? 'flex-row-reverse' : ''">
                      <img
                        :src="message.voipType === 'video' ? '/assets/images/wechat/wechat-video-call.svg' : '/assets/images/wechat/wechat-audio-call.svg'"
                        class="wechat-voip-icon"
                        :class="{
                          'wechat-voip-icon--video': message.voipType === 'video',
                          'wechat-voip-icon--mirrored': message.voipType === 'video' && message.isSent,
                        }"
                        alt=""
                      >
                      <span class="wechat-voip-text">{{ message.content || '通话' }}</span>
                    </div>
                  </div>
                  <div v-else-if="message.renderType === 'emoji'" class="max-w-sm flex items-center group" :class="message.isSent ? 'flex-row-reverse' : ''">
                    <template v-if="message.emojiUrl && !message._emojiRenderError">
                      <img
                        v-chat-lazy-src="message.emojiUrl"
                        alt="表情"
                        class="w-24 h-24 object-contain cursor-pointer hover:opacity-90 transition-opacity"
                        loading="lazy"
                        decoding="async"
                        fetchpriority="low"
                        @click.stop="openImagePreview(message.emojiUrl)"
                        @contextmenu="openMediaContextMenu($event, message, 'emoji')"
                        @error="onMessageEmojiRenderError(message)"
                      >
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
                    <div v-else-if="message.emojiUrl" class="wechat-media-placeholder wechat-media-placeholder--emoji">
                      <i class="fa-regular fa-face-smile" aria-hidden="true"></i>
                      <span>表情未缓存</span>
                    </div>
                    <div v-else class="px-3 py-1.5 text-[13px] max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                      :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                      {{ message.content }}
                    </div>
                  </div>
                  <template v-else-if="message.renderType === 'quote'">
                    <div
                      class="px-3 py-1.5 text-[13px] max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                      :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                      <span v-for="(seg, idx) in parseMessageTextSegments(message)" :key="idx">
                        <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                        <a
                          v-else-if="seg.type === 'link'"
                          class="chat-message-link"
                          :href="seg.url"
                          target="_blank"
                          rel="noopener noreferrer"
                          @click.prevent.stop="openMessageUrl(seg.url)"
                        >{{ seg.content }}</a>
                        <span
                          v-else-if="seg.type === 'mention'"
                          class="chat-mention"
                          @mouseenter="handleMentionMouseEnter(message, seg.user)"
                          @mouseleave="handleMentionMouseLeave"
                        >{{ seg.content }}</span>
                        <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" loading="lazy" decoding="async">
                      </span>
                    </div>
                      <div
                        v-if="message.quoteTitle || message.quoteContent"
                       class="wechat-quote-preview mt-[5px] px-2 text-xs rounded max-w-[404px] max-h-[65px] overflow-hidden flex items-start">
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
                            v-chat-lazy-src="message.quoteThumbUrl"
                            alt="引用链接缩略图"
                            class="max-h-[49px] w-auto max-w-[98px] object-contain"
                            loading="lazy"
                            decoding="async"
                            fetchpriority="low"
                            referrerpolicy="no-referrer"
                            v-chat-media-perf="{ kind: 'quote-thumb', meta: { conversation: selectedContact?.username || '', messageId: message.id, quoteServerId: message.quoteServerId || '' } }"
                           @error="onQuoteThumbError(message)"
                         />
                       </div>
                       <div
                         v-if="!isQuotedLink(message) && isQuotedImage(message) && message.quoteImageUrl && !message._quoteImageError"
                         class="ml-2 my-2 flex-shrink-0 max-w-[98px] max-h-[49px] overflow-hidden flex items-center justify-center cursor-pointer"
                         @click.stop="openImagePreview(message.quoteImageUrl)"
                       >
                          <img
                            v-chat-lazy-src="message.quoteImageUrl"
                            alt="引用图片"
                            class="max-h-[49px] w-auto max-w-[98px] object-contain"
                            loading="lazy"
                            decoding="async"
                            fetchpriority="low"
                            v-chat-media-perf="{ kind: 'quote-image', meta: { conversation: selectedContact?.username || '', messageId: message.id, quoteServerId: message.quoteServerId || '' } }"
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
                    <div v-if="!hideTypeFooter" class="wechat-chat-history-bottom">
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
                    class="px-3 py-1.5 text-[13px] max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                    :class="message.isSent ? 'bg-[#95EC69] text-black bubble-tail-r' : 'bg-white text-gray-800 bubble-tail-l'">
                    <span v-for="(seg, idx) in parseMessageTextSegments(message)" :key="idx">
                      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                      <a
                        v-else-if="seg.type === 'link'"
                        class="chat-message-link"
                        :href="seg.url"
                        target="_blank"
                        rel="noopener noreferrer"
                        @click.prevent.stop="openMessageUrl(seg.url)"
                      >{{ seg.content }}</a>
                      <span
                        v-else-if="seg.type === 'mention'"
                        class="chat-mention"
                        @mouseenter="handleMentionMouseEnter(message, seg.user)"
                        @mouseleave="handleMentionMouseLeave"
                      >{{ seg.content }}</span>
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
import { defineComponent, toRef } from 'vue'
import wechatPcLogoUrl from '~/assets/images/wechat/WeChat-Icon-Logo.wine.svg'
import ChatLocationCard from '~/components/ChatLocationCard.vue'
import FileTypeIcon from '~/components/chat/FileTypeIcon.vue'
import ImageGroupStack from '~/components/chat/ImageGroupStack.vue'
import LinkCard from '~/components/chat/LinkCard.vue'
import { linkifyMessageSegments, openMessageExternalUrl } from '~/lib/chat/message-links'

const MENTION_SEPARATOR_RE = /[\s\u00a0\u1680\u180e\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\ufeff]/
const MENTION_TRAILING_BOUNDARY_RE = /[\s\u00a0\u1680\u180e\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\ufeff,，.。!！?？:：;；、)]/
const MENTION_LEADING_BOUNDARY_RE = /[\s\u00a0\u1680\u180e\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\ufeff([（{]/

const normalizeMentionLabel = (value) => String(value || '').trim().replace(/^@+/, '')

const getMentionUsers = (message) => {
  const users = []
  const seen = new Set()
  const pushUser = (item) => {
    if (!item || typeof item !== 'object') return
    const username = String(item.username || item.userName || item.wxid || '').trim()
    if (!username || seen.has(username)) return
    seen.add(username)
    users.push({
      ...item,
      username,
      displayName: String(item.displayName || item.name || item.nickname || item.remark || username).trim(),
      avatar: String(item.avatar || item.avatarUrl || '').trim()
    })
  }

  if (Array.isArray(message?.atUsers)) {
    for (const item of message.atUsers) pushUser(item)
  }

  if (!users.length && Array.isArray(message?.atUsernames)) {
    for (const usernameRaw of message.atUsernames) {
      const username = String(usernameRaw || '').trim()
      if (!username || seen.has(username)) continue
      seen.add(username)
      users.push({
        username,
        displayName: username === 'notify@all' ? '所有人' : username,
        avatar: ''
      })
    }
  }

  return users
}

const findNextMentionStart = (text, fromIndex) => {
  let idx = text.indexOf('@', Math.max(0, fromIndex || 0))
  while (idx >= 0) {
    const before = idx > 0 ? text.charAt(idx - 1) : ''
    const beforeOk = !before || MENTION_LEADING_BOUNDARY_RE.test(before)
    if (beforeOk) return idx
    idx = text.indexOf('@', idx + 1)
  }
  return -1
}

const findNextMentionRange = (text, fromIndex) => {
  const start = findNextMentionStart(text, fromIndex)
  if (start < 0) return null
  let end = start + 1
  while (end < text.length && !MENTION_SEPARATOR_RE.test(text.charAt(end))) {
    end += 1
  }
  return end > start + 1 ? { start, end } : null
}

const buildMentionRanges = (message) => {
  const text = String(message?.content || '')
  const users = getMentionUsers(message)
  if (!text || !users.length) return []

  const ranges = []
  let cursor = 0
  for (const user of users) {
    const fallback = findNextMentionRange(text, cursor)
    if (!fallback) break

    const label = normalizeMentionLabel(user.displayName)
    let start = fallback.start
    let end = fallback.end
    if (label) {
      const token = `@${label}`
      const exactEnd = start + token.length
      const after = text.charAt(exactEnd)
      if (text.startsWith(token, start) && (!after || MENTION_TRAILING_BOUNDARY_RE.test(after))) {
        end = exactEnd
      }
    }
    if (start < cursor || end <= start) continue
    ranges.push({ start, end, user })
    cursor = end
  }

  return ranges
}

export default defineComponent({
  name: 'MessageContent',
  components: { ChatLocationCard, FileTypeIcon, ImageGroupStack, LinkCard },
  props: {
    state: { type: Object, required: true },
    message: { type: Object, required: true },
    hideTypeFooter: { type: Boolean, default: false }
  },
  setup(props) {
    const readMaybeRef = (value) => (
      value && typeof value === 'object' && 'value' in value ? value.value : value
    )
    const voiceTranscriptStatus = (message) => String(message?.voiceTranscriptStatus || '').trim().toLowerCase()
    const isVoiceTranscriptIdle = (message) => {
      const status = voiceTranscriptStatus(message)
      return !String(message?.voiceTranscript || '').trim() && (!status || status === 'idle')
    }
    const isVoiceTranscriptActionState = (message) => (
      isVoiceTranscriptIdle(message)
      || (!String(message?.voiceTranscript || '').trim() && voiceTranscriptStatus(message) === 'error')
    )
    const canShowLocalVoiceAction = (message, allowError = false) => {
      const status = String(message?.voiceTranscriptStatus || 'idle').trim().toLowerCase()
      const hasText = !!String(message?.voiceTranscript || '').trim()
      const localKnown = readMaybeRef(props.state?.voiceTranscriptionStatusKnown)
      const localLoading = readMaybeRef(props.state?.voiceTranscriptionStatusLoading) === true
      if (
        typeof props.state?.transcribeVoiceLocally !== 'function'
        || hasText
        || (status !== 'idle' && !(allowError && status === 'error'))
        || localKnown === false
        || localLoading
      ) return false
      return true
    }
    const voiceLocalActionTitle = () => {
      const localAvailable = readMaybeRef(props.state?.voiceTranscriptionAvailable) === true
      const localReason = String(readMaybeRef(props.state?.voiceTranscriptionUnavailableReason) || '').trim()
      const nativeReason = String(readMaybeRef(props.state?.nativeVoiceTranscriptionUnavailableReason) || '').trim()
      return (!localAvailable && localReason) || nativeReason || '使用本地转文字'
    }
    const isActiveImageGroupTransition = (message) => (
      !!message?.imageGroupExpanded
      && String(readMaybeRef(props.state?.activeImageGroupTransitionKey) || '')
        === String(message?.imageGroupKey || '')
    )
    const imageGroupLazySource = (message) => {
      const src = String(message?.imageUrl || '').trim()
      return isActiveImageGroupTransition(message) ? { src, eager: true } : src
    }
    const toggleImageGroupWithTransition = (groupKey) => {
      const transition = props.state?.transitionImageGroupExpanded
      if (typeof transition === 'function') {
        void transition(groupKey)
        return
      }
      props.state?.toggleImageGroupExpanded?.(groupKey)
    }

    const voiceTranscriptSourceKey = (message) => {
      const model = String(message?.voiceTranscriptModel || '').trim().toLowerCase()
      if (model === 'wechat-native') return 'wechat'
      return model ? 'project' : 'unknown'
    }

    const voiceTranscriptSourceLabel = (message) => ({
      wechat: '微信原生转写',
      project: '本项目转写',
      unknown: '转写来源未标记'
    })[voiceTranscriptSourceKey(message)]

    const voiceTranscriptSourceTitle = (message) => {
      const source = voiceTranscriptSourceKey(message)
      if (source === 'wechat') return '文字由微信客户端原生语音转文字能力生成'
      const model = String(message?.voiceTranscriptModel || '').trim()
      if (source === 'project') return `文字由本项目本地 Whisper 转写（模型：${model}）`
      return '该转写记录没有来源标记'
    }

    const parseEmojiSegments = (text) => {
      const fn = props.state?.parseTextWithEmoji
      if (typeof fn === 'function') return fn(String(text || ''))
      return [{ type: 'text', content: String(text || '') }]
    }

    const appendEmojiSegments = (output, text) => {
      if (!text) return
      const segments = linkifyMessageSegments(parseEmojiSegments(text))
      for (const seg of segments) output.push(seg)
    }

    const parseMessageTextSegments = (message) => {
      const text = String(message?.content || '')
      const mentionRanges = buildMentionRanges(message)
      if (!mentionRanges.length) return linkifyMessageSegments(parseEmojiSegments(text))

      const output = []
      let pos = 0
      for (const range of mentionRanges) {
        if (range.start > pos) appendEmojiSegments(output, text.slice(pos, range.start))
        output.push({
          type: 'mention',
          content: text.slice(range.start, range.end),
          user: range.user
        })
        pos = range.end
      }
      if (pos < text.length) appendEmojiSegments(output, text.slice(pos))
      return output
    }

    const openMessageUrl = (url) => {
      if (typeof props.state?.openUrlInBrowser === 'function') {
        props.state.openUrlInBrowser(url)
        return
      }
      void openMessageExternalUrl(url)
    }

    const handleMentionMouseEnter = (message, user) => {
      if (typeof props.state?.onMentionMouseEnter === 'function') {
        props.state.onMentionMouseEnter(message, user)
      }
    }

    const handleMentionMouseLeave = () => {
      if (typeof props.state?.onMentionMouseLeave === 'function') {
        props.state.onMentionMouseLeave()
      } else if (typeof props.state?.onMessageAvatarMouseLeave === 'function') {
        props.state.onMessageAvatarMouseLeave()
      }
    }

    const onMessageImageRenderError = (message) => {
      const fallback = String(message?.imageFallbackUrl || '').trim()
      if (fallback && fallback !== String(message?.imageUrl || '').trim() && !message?._imageFallbackTried) {
        message._imageFallbackTried = true
        message.imageUrl = fallback
        return
      }
      message._imageRenderError = true
      if (typeof props.state?.onMessageImageRenderError === 'function') {
        props.state.onMessageImageRenderError(message)
      }
    }

    const onMessageVideoThumbRenderError = (message) => {
      message._videoThumbRenderError = true
      if (typeof props.state?.onMessageVideoThumbRenderError === 'function') {
        props.state.onMessageVideoThumbRenderError(message)
      }
    }

    const onMessageEmojiRenderError = (message) => {
      message._emojiRenderError = true
      if (typeof props.state?.onMessageEmojiRenderError === 'function') {
        props.state.onMessageEmojiRenderError(message)
      }
    }

    return {
      ...props.state,
      message: toRef(props, 'message'),
      hideTypeFooter: toRef(props, 'hideTypeFooter'),
      isVoiceTranscriptIdle,
      isVoiceTranscriptActionState,
      canShowLocalVoiceAction,
      voiceLocalActionTitle,
      parseMessageTextSegments,
      openMessageUrl,
      handleMentionMouseEnter,
      handleMentionMouseLeave,
      onMessageImageRenderError,
      onMessageVideoThumbRenderError,
      onMessageEmojiRenderError,
      imageGroupLazySource,
      toggleImageGroupWithTransition,
      voiceTranscriptSourceKey,
      voiceTranscriptSourceLabel,
      voiceTranscriptSourceTitle,
      wechatPcLogoUrl
    }
  }
})
</script>

<style scoped>
.chat-mention {
  color: #576b95;
  font-weight: 500;
  border-radius: 3px;
  padding: 0 1px;
  cursor: default;
}

.chat-mention:hover {
  background: rgba(87, 107, 149, 0.1);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.chat-message-link {
  color: #245fbd;
  cursor: pointer;
  overflow-wrap: anywhere;
  text-decoration: none;
}

.chat-message-link:hover {
  color: #174a99;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.wechat-media-placeholder {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  width: 160px;
  height: 112px;
  border-radius: var(--message-radius);
  color: #8a919b;
  background: #e4e6e8;
  font-size: 12px;
}

.wechat-media-placeholder > i { font-size: 24px; }
.wechat-media-placeholder--image { width: 160px; height: 128px; }
.wechat-media-placeholder--video { width: 220px; height: 124px; color: #d1d5db; background: #34383d; }
.wechat-media-placeholder--emoji { width: 96px; height: 96px; background: rgba(255, 255, 255, 0.58); }

.image-group-collapse {
  height: 30px;
  padding: 0 11px;
  border: 0;
  border-radius: 8px;
  color: var(--app-text-muted);
  background: var(--app-surface-muted);
  font-size: 12px;
  line-height: 30px;
  white-space: nowrap;
}

.image-group-collapse:hover {
  color: var(--app-text-secondary);
  background: var(--app-list-hover);
}

.image-group-collapse:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.72);
  outline-offset: 2px;
}

.image-group-collapse:disabled {
  cursor: default;
}

/* 深色：占位块不能是浅灰，否则未加载的图片/视频比正文还亮 */
html[data-theme='dark'] .wechat-media-placeholder {
  color: var(--app-text-muted);
  background: var(--app-surface-soft);
}

html[data-theme='dark'] .wechat-media-placeholder--emoji {
  background: rgba(255, 255, 255, 0.08);
}
</style>
