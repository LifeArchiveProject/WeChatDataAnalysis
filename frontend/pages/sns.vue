<template>
  <div class="sns-page h-screen flex overflow-hidden" style="background-color: var(--app-shell-bg)">
    <!-- 左侧朋友圈联系人 -->
    <div class="w-[280px] flex flex-col min-h-0 border-r border-gray-200 bg-[#EDEDED]" style="background-color: var(--app-shell-bg)">
      <div class="p-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold text-gray-700">朋友圈联系人</div>
          <div class="text-xs text-gray-500">{{ visibleSnsUsers.length }}</div>
        </div>
        <input
            v-model="snsUserQuery"
            type="text"
            placeholder="搜索"
            class="mt-2 w-full px-3 py-2 rounded-md border border-gray-200 bg-white text-sm outline-none focus:ring-2 focus:ring-[#576b95]/30 focus:border-[#576b95]"
        />

        <div class="mt-3">
          <button
              type="button"
              class="w-full px-3 py-2.5 rounded-md text-sm border border-gray-200 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!selectedAccount"
              @click="openExportModal"
          >
            导出朋友圈
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-auto min-h-0 bg-white">
        <div
            class="px-3 py-2 text-sm cursor-pointer flex items-center gap-2 border-b border-gray-100 hover:bg-gray-50"
            :class="selectedSnsUser ? 'text-gray-700' : 'bg-gray-50 text-gray-900 font-medium'"
            @click="selectSnsUser('')"
        >
          <div class="w-8 h-8 rounded-md bg-gray-200 flex items-center justify-center text-xs text-gray-500 flex-shrink-0">全</div>
          <div class="flex-1 min-w-0 truncate">全部</div>
        </div>

        <div
            v-for="u in filteredSnsUsers"
            :key="u.username"
            class="px-3 py-2 text-sm cursor-pointer flex items-center gap-2 border-b border-gray-100 hover:bg-gray-50"
            :class="selectedSnsUser === u.username ? 'bg-gray-50 text-gray-900 font-medium' : 'text-gray-700'"
            @click="selectSnsUser(u.username)"
        >
          <div class="w-8 h-8 rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
            <img
                v-if="postAvatarUrl(u.username) && !hasSnsAvatarError(u.username)"
                :src="postAvatarUrl(u.username)"
                :alt="u.displayName || u.username"
                class="w-full h-full object-cover"
                referrerpolicy="no-referrer"
                @error="onSnsAvatarError(u.username)"
            />
            <div
                v-else
                class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                style="background-color: #4B5563"
            >
              {{ (u.displayName || u.username || '友').charAt(0) }}
            </div>
          </div>

          <div class="flex-1 min-w-0">
            <div class="truncate" :class="{ 'privacy-blur': privacyMode }">{{ u.displayName || u.username }}</div>
            <div class="text-[11px] text-gray-400 truncate">
              <span>{{ u.username }}</span>
              <span> · </span>
              <!-- `postCount` is computed from the decrypted sqlite snapshot (cache). The timeline API may only return
                   the visible subset (e.g. privacy setting: "only last 3 days"), so show loaded/cache for the selected user. -->
              <template v-if="selectedSnsUser === u.username">
                <span>{{ posts.length }}</span>
                <span v-if="u.postCount != null">/{{ u.postCount || 0 }}</span>
                <span> 条</span>
              </template>
              <template v-else>
                <span>{{ u.postCount || 0 }} 条</span>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧朋友圈区域 -->
    <div class="flex-1 flex flex-col min-h-0" style="background-color: var(--app-shell-bg)">
      <div ref="timelineScrollEl" class="flex-1 overflow-auto min-h-0 bg-white" @scroll="onScroll">
	        <div class="max-w-2xl mx-auto px-4 py-4">
            <div class="relative w-full mb-12 -mt-4 bg-white">
              <div class="h-64 w-full bg-[#333333] relative overflow-hidden group">
                <img
                    v-if="activeCover && activeCover.media && activeCover.media.length > 0"
                    :src="getSnsMediaUrl(activeCover, activeCover.media[0], 0, activeCover.media[0].url)"
                    class="w-full h-full object-cover"
                    alt="朋友圈封面"
                />

                <div
                    v-if="(activeCover && Number(activeCover.createTime || 0)) || (covers && covers.length > 1)"
                    class="absolute top-3 right-3 z-10 text-[11px] text-white bg-black/40 backdrop-blur-sm px-2 py-1 rounded pointer-events-none"
                >
                  <span v-if="activeCover && Number(activeCover.createTime || 0)">{{ formatCoverTime(activeCover.createTime) }}</span>
                  <span v-if="covers && covers.length > 1">
                    <span v-if="activeCover && Number(activeCover.createTime || 0)">&nbsp;·&nbsp;</span>{{ coverIndex + 1 }}/{{ covers.length }}
                  </span>
                </div>

                <button
                    v-if="covers && covers.length > 1"
                    type="button"
                    class="absolute left-2 top-1/2 -translate-y-1/2 z-10 text-white/90 hover:text-white p-2 rounded-full bg-black/25 hover:bg-black/40 transition-colors"
                    title="上一张封面"
                    @click.stop="prevCover"
                >
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                  </svg>
                </button>

                <button
                    v-if="covers && covers.length > 1"
                    type="button"
                    class="absolute right-2 top-1/2 -translate-y-1/2 z-10 text-white/90 hover:text-white p-2 rounded-full bg-black/25 hover:bg-black/40 transition-colors"
                    title="下一张封面"
                    @click.stop="nextCover"
                >
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
              <div class="absolute right-4 -bottom-6 flex items-end gap-4">
                <div class="text-white font-bold text-xl mb-7 drop-shadow-md">
                  {{ selfInfo.nickname || '获取中...' }}
                </div>

                <div class="w-[72px] h-[72px] rounded-lg bg-white p-[2px] shadow-sm">
                  <img
                      v-if="selfInfo.wxid"
                      :src="postAvatarUrl(selfInfo.wxid)"
                      class="w-full h-full rounded-md object-cover bg-gray-100"
                      :alt="selfInfo.nickname"
                      referrerpolicy="no-referrer"
                  />
                  <div v-else class="w-full h-full rounded-md bg-gray-300 flex items-center justify-center text-gray-500 text-xs">
                    ...
                  </div>
                </div>
              </div>
            </div>
            <div v-if="error" class="text-sm text-red-500 whitespace-pre-wrap py-4 text-center">{{ error }}</div>

            <div v-else-if="isLoading && posts.length === 0" class="flex flex-col items-center justify-center py-16">
              <div class="w-8 h-8 border-[3px] border-gray-200 border-t-[#576b95] rounded-full animate-spin"></div>
              <div class="mt-4 text-sm text-gray-400">正在前往朋友圈...</div>
            </div>

            <div v-else-if="posts.length === 0" class="text-sm text-gray-400 py-16 text-center">暂无朋友圈数据</div>

            <div v-if="!error && posts.length > 0" class="text-[11px] text-gray-500 mb-2 flex flex-wrap gap-x-3 gap-y-1">
              <span v-if="selectedSnsUserInfo">缓存统计：{{ selectedSnsUserInfo.postCount || 0 }}</span>
              <span v-if="!hasMore && !isLoading">（已到末尾）</span>
            </div>
            <div v-if="showSnsCountMismatchHint" class="text-[11px] text-amber-700 mb-3">
              提示：左侧“缓存统计”来自解密后的 sns.db；当前 timeline 接口只返回可见部分，所以会出现
              <span class="font-medium">{{ posts.length }}/{{ selectedSnsUserInfo?.postCount || 0 }}</span>。
            </div>

	          <div v-for="post in posts" :key="post.id" class="bg-white rounded-sm px-4 py-4 mb-3">
	            <div class="flex items-start gap-3" @contextmenu.prevent="openPostContextMenu($event, post)">
              <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="postAvatarUrl(post.username)"
                  :src="postAvatarUrl(post.username)"
                  :alt="post.displayName || post.username"
                  class="w-full h-full object-cover"
                  referrerpolicy="no-referrer"
                />
                <div
                  v-else
                  class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                  style="background-color: #4B5563"
                >
                  {{ (post.displayName || post.username || '友').charAt(0) }}
                </div>
              </div>

              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium leading-5 text-[#576b95]" :class="{ 'privacy-blur': privacyMode }">
                  {{ post.displayName || post.username }}
                </div>

                <div
                    v-if="post.contentDesc"
                    class="mt-1 text-sm text-gray-900 leading-6 whitespace-pre-wrap break-words"
                    :class="{ 'privacy-blur': privacyMode }"
                >
                  <span v-for="(seg, idx) in parseTextWithEmoji(String(post.contentDesc || ''))" :key="idx">
                    <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                    <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                  </span>
                </div>

                <div v-if="post.type === 3" class="mt-2 w-full" :class="{ 'privacy-blur': privacyMode }">
                  <a :href="post.contentUrl" target="_blank" class="block w-full bg-[#F7F7F7] p-2 rounded-sm no-underline hover:bg-[#EFEFEF] transition-colors">
                    <div class="flex items-center gap-3">
                      <img
                          v-if="getArticleCardThumbSrc(post)"
                          :src="getArticleCardThumbSrc(post)"
                          class="w-12 h-12 object-cover flex-shrink-0 bg-white"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="onArticleThumbError(post)"
                      />
                      <div v-else class="w-12 h-12 flex items-center justify-center bg-gray-200 text-gray-400 flex-shrink-0 text-xs">
                        文章
                      </div>

                      <div class="flex-1 min-w-0 flex items-center overflow-hidden h-12">
                        <div class="text-[13px] text-gray-900 leading-tight line-clamp-2">{{ post.title }}</div>
                      </div>
                    </div>
                  </a>
                </div>

                <div v-else-if="post.type === 28 && post.finderFeed && Object.keys(post.finderFeed).length > 0" class="mt-2 w-full max-w-[304px]" :class="{ 'privacy-blur': privacyMode }">
                  <!-- 浏览器没有看微信视频号的环境，暂时不进行跳转 -->
                  <div class="relative w-full overflow-hidden rounded-sm bg-[#F7F7F7]">
                    <img
                        v-if="getFinderFeedThumbSrc(post)"
                        :src="getFinderFeedThumbSrc(post)"
                        class="block w-full aspect-square object-cover"
                        alt=""
                        loading="lazy"
                        referrerpolicy="no-referrer"
                    />
                    <div v-else class="w-full aspect-square flex items-center justify-center bg-gray-200">
                      <span class="line-clamp-3 px-4 text-center text-[13px] leading-5 text-gray-500">{{ formatFinderFeedCardText(post) }}</span>
                    </div>
                    <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                      <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="isExternalShareMoment(post)" class="mt-2 w-full" :class="{ 'privacy-blur': privacyMode }">
                  <a
                      v-if="getMomentLinkCardUrl(post)"
                      :href="getMomentLinkCardUrl(post)"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="block w-full bg-[#F7F7F7] p-2 rounded-sm no-underline hover:bg-[#EFEFEF] transition-colors"
                  >
                    <div class="flex items-center gap-3">
                      <img
                          v-if="getExternalShareCardThumbSrc(post)"
                          :src="getExternalShareCardThumbSrc(post)"
                          class="w-12 h-12 object-cover flex-shrink-0 bg-white"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="onExternalShareCardThumbError(post)"
                      />
                      <div v-else class="w-12 h-12 flex items-center justify-center bg-gray-200 text-gray-400 flex-shrink-0 text-xs">
                        {{ formatExternalSharePlaceholder(post) }}
                      </div>

                      <div class="flex-1 min-w-0 flex items-center overflow-hidden h-12">
                        <div class="text-[13px] text-gray-900 leading-tight line-clamp-2">{{ formatExternalShareCardTitle(post) }}</div>
                      </div>
                    </div>
                  </a>
                  <div v-else class="block w-full bg-[#F7F7F7] p-2 rounded-sm">
                    <div class="flex items-center gap-3">
                      <img
                          v-if="getExternalShareCardThumbSrc(post)"
                          :src="getExternalShareCardThumbSrc(post)"
                          class="w-12 h-12 object-cover flex-shrink-0 bg-white"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="onExternalShareCardThumbError(post)"
                      />
                      <div v-else class="w-12 h-12 flex items-center justify-center bg-gray-200 text-gray-400 flex-shrink-0 text-xs">
                        {{ formatExternalSharePlaceholder(post) }}
                      </div>

                      <div class="flex-1 min-w-0 flex items-center overflow-hidden h-12">
                        <div class="text-[13px] text-gray-900 leading-tight line-clamp-2">{{ formatExternalShareCardTitle(post) }}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="post.media && post.media.length > 0" class="mt-2" :class="{ 'privacy-blur': privacyMode }">
                  <div v-if="post.media.length === 1" class="max-w-[360px]">
                    <div
                        v-if="!hasMediaError(post.id, 0) && getMediaThumbSrc(post, post.media[0], 0)"
                        class="inline-block cursor-pointer relative group"
                        @click.stop="onMediaClick(post, post.media[0], 0)"
                        @mouseenter="onLivePhotoEnter(post.id, 0, post.media[0])"
                        @mouseleave="onLivePhotoLeave(post.id, 0, post.media[0])"
                    >
                      <video
                          v-if="Number(post.media[0]?.type || 0) === 6"
                          :src="getSnsRemoteVideoSrc(post, post.media[0])"
                          :poster="getMediaThumbSrc(post, post.media[0], 0)"
                          class="rounded-sm max-h-[360px] max-w-full object-cover"
                          autoplay
                          loop
                          muted
                          playsinline
                          @loadeddata="onLocalVideoLoaded(post.id, post.media[0].id)"
                          @error="onLocalVideoError(post.id, post.media[0].id)"
                      ></video>

                      <video
                          v-else-if="isLivePhotoMedia(post.media[0]) && isLivePhotoActive(post.id, 0) && !hasLivePhotoVideoError(post.id, 0)"
                          ref="livePhotoHoverVideoEl"
                          :src="getLivePhotoVideoSrc(post, post.media[0], 0)"
                          :poster="getMediaThumbSrc(post, post.media[0], 0)"
                          class="rounded-sm max-h-[360px] max-w-full object-cover pointer-events-none"
                          autoplay
                          loop
                          :muted="livePhotoHoverMuted"
                          playsinline
                          @error="onLivePhotoVideoError(post.id, 0)"
                      ></video>

                      <img
                          v-else
                          :src="getMediaThumbSrc(post, post.media[0], 0)"
                          class="rounded-sm max-h-[360px] object-cover"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="onMediaError(post.id, 0)"
                      />
                      <div
                          v-if="Number(post.media[0]?.type || 0) === 6 && !isLocalVideoLoaded(post.id, post.media[0].id)"
                          class="absolute inset-0 flex items-center justify-center pointer-events-none"
                      >
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </div>

                      <div
                          v-if="isLivePhotoMedia(post.media[0])"
                          class="absolute top-2 right-2 bg-black/30 backdrop-blur-sm text-white p-1 rounded-full pointer-events-none z-10 shadow-sm"
                      >
                        <LivePhotoIcon :size="16" class="block" />
                      </div>

                      <button
                        v-if="isLivePhotoMedia(post.media[0]) && isLivePhotoActive(post.id, 0) && !hasLivePhotoVideoError(post.id, 0)"
                        type="button"
                        class="absolute top-2 right-10 text-white/90 hover:text-white p-1 rounded-full bg-black/30 hover:bg-black/50 transition-colors z-10"
                        :title="livePhotoHoverMuted ? '开启声音' : '静音'"
                        @click.stop="toggleLivePhotoHoverMuted"
                      >
                        <svg v-if="livePhotoHoverMuted" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5L6 9H2v6h4l5 4V5z" />
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M23 9l-6 6M17 9l6 6" />
                        </svg>
                        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5L6 9H2v6h4l5 4V5z" />
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.5 8.5a4 4 0 010 7" />
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.5 5.5a8 8 0 010 13" />
                        </svg>
                      </button>

                      <button
                        type="button"
                        class="absolute bottom-2 right-2 z-20 flex h-7 w-7 items-center justify-center rounded-full bg-black/45 text-white opacity-0 transition group-hover:opacity-100 hover:bg-[#07c160]"
                        title="下载"
                        aria-label="下载朋友圈媒体"
                        @click.stop="downloadSnsMedia(post, post.media[0], 0)"
                      >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v11m0 0l4-4m-4 4l-4-4M5 21h14" />
                        </svg>
                      </button>
                    </div>
                    <div
                        v-else
                        class="w-[240px] h-[180px] rounded-sm bg-gray-100 border border-gray-200 flex items-center justify-center text-xs text-gray-400"
                        title="图片加载失败"
                        @click.stop="onMediaClick(post, post.media[0], 0)"
                        style="cursor: pointer;"
                    >
                      图片加载失败
                    </div>
                  </div>

                  <div v-else class="grid grid-cols-3 gap-1 max-w-[360px]">
                    <div
                        v-for="(m, idx) in post.media.slice(0, 9)"
                        :key="idx"
                        class="w-[116px] h-[116px] rounded-[2px] overflow-hidden bg-gray-100 border border-gray-200 flex items-center justify-center cursor-pointer relative group"
                        @click.stop="onMediaClick(post, m, idx)"
                        @mouseenter="onLivePhotoEnter(post.id, idx, m)"
                        @mouseleave="onLivePhotoLeave(post.id, idx, m)"
                    >
                      <video
                          v-if="!hasMediaError(post.id, idx) && Number(m?.type || 0) === 6"
                          :src="getSnsRemoteVideoSrc(post, m)"
                          :poster="getMediaThumbSrc(post, m, idx)"
                          class="w-full h-full object-cover"
                          autoplay
                          loop
                          muted
                          playsinline
                          @loadeddata="onLocalVideoLoaded(post.id, m.id)"
                          @error="onLocalVideoError(post.id, m.id)"
                      ></video>
                      <video
                          v-else-if="isLivePhotoMedia(m) && isLivePhotoActive(post.id, idx) && !hasLivePhotoVideoError(post.id, idx)"
                          ref="livePhotoHoverVideoEl"
                          :src="getLivePhotoVideoSrc(post, m, idx)"
                          :poster="getMediaThumbSrc(post, m, idx)"
                          class="w-full h-full object-cover pointer-events-none"
                          autoplay
                          loop
                          :muted="livePhotoHoverMuted"
                          playsinline
                          @error="onLivePhotoVideoError(post.id, idx)"
                      ></video>
                      <img
                          v-else-if="!hasMediaError(post.id, idx) && getMediaThumbSrc(post, m, idx)"
                          :src="getMediaThumbSrc(post, m, idx)"
                          class="w-full h-full object-cover"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="onMediaError(post.id, idx)"
                      />
                      <!-- 不知道微信朋友圈可不可以发多视频，先这样写吧-->
                      <span v-else class="text-[10px] text-gray-400">图片失败</span>

                      <div
                          v-if="Number(m?.type || 0) === 6 && !isLocalVideoLoaded(post.id, m.id)"
                          class="absolute inset-0 flex items-center justify-center pointer-events-none"
                      >
                        <div class="w-10 h-10 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </div>

                      <div
                          v-if="isLivePhotoMedia(m)"
                          class="absolute top-1 right-1 bg-black/30 backdrop-blur-sm text-white p-0.5 rounded-full pointer-events-none z-10 shadow-sm"
                      >
                        <LivePhotoIcon :size="14" class="block" />
                      </div>

                      <button
                        v-if="isLivePhotoMedia(m) && isLivePhotoActive(post.id, idx) && !hasLivePhotoVideoError(post.id, idx)"
                        type="button"
                        class="absolute top-1 right-7 text-white/90 hover:text-white p-0.5 rounded-full bg-black/30 hover:bg-black/50 transition-colors z-10"
                        :title="livePhotoHoverMuted ? '开启声音' : '静音'"
                        @click.stop="toggleLivePhotoHoverMuted"
                      >
                        <svg v-if="livePhotoHoverMuted" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5L6 9H2v6h4l5 4V5z" />
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M23 9l-6 6M17 9l6 6" />
                        </svg>
                        <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5L6 9H2v6h4l5 4V5z" />
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.5 8.5a4 4 0 010 7" />
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.5 5.5a8 8 0 010 13" />
                        </svg>
                      </button>

                      <button
                        type="button"
                        class="absolute bottom-1.5 right-1.5 z-20 flex h-6 w-6 items-center justify-center rounded-full bg-black/45 text-white opacity-0 transition group-hover:opacity-100 hover:bg-[#07c160]"
                        title="下载"
                        aria-label="下载朋友圈媒体"
                        @click.stop="downloadSnsMedia(post, m, idx)"
                      >
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v11m0 0l4-4m-4 4l-4-4M5 21h14" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>

                <div v-if="post.location" class="mt-2 text-xs text-[#576b95] truncate" :class="{ 'privacy-blur': privacyMode }">
                  {{ post.location }}
                </div>

                <div class="mt-2 flex items-center justify-between">
                  <div class="flex items-center gap-2 min-w-0">
                    <span class="text-xs text-gray-400" :class="{ 'privacy-blur': privacyMode }">{{ formatRelativeTime(post.createTime) }}</span>
                    <button
                      v-if="Number(post?.type || 0) === 3 && formatMomentTypeLabel(post)"
                      type="button"
                      class="text-xs text-[#576b95] truncate bg-transparent p-0 border-0 hover:underline"
                      :class="{ 'privacy-blur': privacyMode }"
                      :title="formatMomentTypeLabel(post)"
                      @click.stop="onMomentTypeLabelClick(post)"
                    >{{ formatMomentTypeLabel(post) }}</button>
                    <span
                      v-else-if="formatMomentTypeLabel(post)"
                      class="text-xs text-[#576b95] truncate"
                      :class="{ 'privacy-blur': privacyMode }"
                      :title="formatMomentTypeLabel(post)"
                    >{{ formatMomentTypeLabel(post) }}</span>
                  </div>
                </div>

	                <!-- 点赞/评论（参考 WeFlow 展示） -->
	                <div
	                  v-if="(post.likes && post.likes.length > 0) || (post.comments && post.comments.length > 0)"
	                  class="mt-2 bg-gray-100 rounded-sm px-2 py-1"
	                >
	                  <div v-if="post.likes && post.likes.length > 0" class="flex items-start gap-1 text-xs text-[#576b95] leading-5">
	                    <svg
	                      xmlns="http://www.w3.org/2000/svg"
	                      width="14"
	                      height="14"
	                      class="mt-[3px] mr-[10px] flex-shrink-0 opacity-80"
	                      viewBox="0 0 24 24"
	                      fill="none"
	                      stroke="currentColor"
	                      stroke-width="2"
	                      stroke-linecap="round"
	                      stroke-linejoin="round"
	                    >
	                      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 1-4.5 2.5C10.5 4 9.26 3 7.5 3A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
	                    </svg>
	                    <div class="break-words" :class="{ 'privacy-blur': privacyMode }">
	                      {{ formatLikes(post.likes) }}
	                    </div>
	                  </div>

	                  <div v-if="post.likes && post.likes.length > 0 && post.comments && post.comments.length > 0" class="my-1 border-t border-gray-200"></div>

	                  <div v-if="post.comments && post.comments.length > 0" class="space-y-1">
	                    <div v-for="(c, idx) in post.comments" :key="c?.id || idx" class="text-xs leading-5 break-words">
	                      <span class="font-medium text-[#576b95]" :class="{ 'privacy-blur': privacyMode }">
	                        {{ cleanLikeName(c?.nickname || c?.displayName || c?.username || '') || '未知' }}
	                      </span>
	                      <template v-if="cleanLikeName(c?.refNickname || c?.refUsername || c?.refUserName || '')">
	                        <span class="mx-1 text-gray-500">回复</span>
	                        <span class="font-medium text-[#576b95]" :class="{ 'privacy-blur': privacyMode }">
	                          {{ cleanLikeName(c?.refNickname || c?.refUsername || c?.refUserName || '') }}
	                        </span>
	                      </template>
	                      <span class="text-gray-900" :class="{ 'privacy-blur': privacyMode }">:
                          <span v-for="(seg, sidx) in parseTextWithEmoji(String(c?.content || '').trim())" :key="sidx">
                            <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                            <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                          </span>
                        </span>
                        <span v-if="getCommentImages(c).length > 0" class="inline-flex flex-wrap align-middle gap-1 ml-1">
                          <button
                            v-for="(img, iidx) in getCommentImages(c)"
                            :key="commentImageKey(post, c, iidx)"
                            type="button"
                            class="inline-flex w-10 h-10 rounded-[6px] overflow-hidden bg-gray-200 border border-gray-200 items-center justify-center align-middle cursor-pointer hover:opacity-90"
                            title="查看评论图片"
                            @click.stop="openCommentImagePreview(post, img, iidx)"
                          >
                            <img
                              v-if="!hasCommentImageError(post, c, iidx) && getCommentImageThumbSrc(post, img, iidx)"
                              :src="getCommentImageThumbSrc(post, img, iidx)"
                              alt="评论图片"
                              class="w-full h-full object-cover"
                              loading="lazy"
                              referrerpolicy="no-referrer"
                              @error="onCommentImageError(post, c, iidx)"
                            />
                            <span v-else class="text-[10px] text-gray-500">图片</span>
                          </button>
                        </span>
	                    </div>
	                  </div>
	                </div>
              </div>
            </div>
          </div>

            <div v-if="isLoading && posts.length > 0" class="py-4 flex justify-center items-center">
              <div class="w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin"></div>
            </div>
            <div v-if="!hasMore && posts.length > 0" class="py-6 text-center text-xs text-gray-400">
              —— 到底了 ——
            </div>
        </div>
      </div>
    </div>

    <!-- 右键菜单（复制 JSON 方便定位问题） -->
    <div
      v-if="contextMenu.visible"
      class="fixed z-50 bg-white border border-gray-200 rounded-md shadow-lg text-sm"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <button class="block w-full text-left px-3 py-2 hover:bg-gray-100" type="button" @click="onCopyPostTextClick">
        复制文案
      </button>
      <button class="block w-full text-left px-3 py-2 hover:bg-gray-100" type="button" @click="onCopyPostJsonClick">
        复制朋友圈 JSON
      </button>
    </div>

    <!-- SNS export modal -->
    <div v-if="exportModalOpen" class="app-export-backdrop">
      <div class="app-export-backdrop__hit-area" aria-hidden="true" @click="closeExportModal"></div>
      <section class="app-export-modal" role="dialog" aria-modal="true" aria-labelledby="sns-export-title">
        <header class="app-export-header">
          <div class="app-export-header__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v11" />
              <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
              <path d="M4 19h16" />
            </svg>
          </div>
          <div class="app-export-header__copy">
            <h2 id="sns-export-title">导出朋友圈</h2>
            <p>选择联系人范围、导出格式和保存位置</p>
          </div>
          <button type="button" class="app-export-icon-button" title="关闭" aria-label="关闭导出面板" @click="closeExportModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </header>

        <div v-if="exportError" class="app-export-alert app-export-alert--error" role="alert">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v6M12 17h.01" />
          </svg>
          <span>{{ exportError }}</span>
        </div>

        <div class="app-export-workspace">
          <div class="app-export-layout">
            <section class="app-export-scope" aria-labelledby="sns-export-scope-title">
              <header class="app-export-panel__header">
                <div>
                  <h3 id="sns-export-scope-title">联系人范围</h3>
                  <p>搜索并勾选需要导出朋友圈的联系人。</p>
                </div>
                <span class="app-export-badge">{{ exportSelectedCount }} 人</span>
              </header>

              <div class="app-export-toolbar">
                <label class="app-export-search">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                    <circle cx="11" cy="11" r="7" />
                    <path d="m16 16 4 4" />
                  </svg>
                  <input v-model="exportSearchQuery" type="search" placeholder="搜索名称或 username" aria-label="搜索导出联系人" :class="{ 'privacy-blur': privacyMode }" />
                </label>
                <button type="button" class="app-export-secondary-button" :disabled="!exportFilteredSnsUsers.length" @click="toggleSelectAllFilteredExportUsers">
                  {{ areAllFilteredExportUsersSelected ? '取消全选' : '全选结果' }}
                </button>
                <button type="button" class="app-export-secondary-button" :disabled="!exportSelectedCount" @click="clearExportSelectedUsers">清空</button>
              </div>

              <div class="app-export-load-state">共 {{ exportFilteredSnsUsers.length }} 个结果</div>
              <div class="app-export-contact-list" role="listbox" aria-label="可导出的朋友圈联系人" aria-multiselectable="true">
                <div v-if="!exportFilteredSnsUsers.length" class="app-export-empty">没有匹配的联系人</div>
                <label
                  v-for="u in exportFilteredSnsUsers"
                  :key="u.username"
                  class="app-export-contact"
                  :class="{ 'is-active': exportSelectedUsernameSet.has(u.username) }"
                  role="option"
                  :aria-selected="exportSelectedUsernameSet.has(u.username)"
                >
                  <input v-model="exportSelectedUsernames" type="checkbox" :value="u.username" class="sr-only" />
                  <span class="app-export-checkbox" aria-hidden="true">
                    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 10 4 4 8-8" /></svg>
                  </span>
                  <span class="app-export-contact__avatar" :class="{ 'privacy-blur': privacyMode }">
                    <img
                      v-if="postAvatarUrl(u.username) && !hasSnsAvatarError(u.username)"
                      :src="postAvatarUrl(u.username)"
                      :alt="`${u.displayName || u.username}头像`"
                      referrerpolicy="no-referrer"
                      @error="onSnsAvatarError(u.username)"
                    />
                    <span v-else>{{ (u.displayName || u.username || '友').charAt(0) }}</span>
                  </span>
                  <span class="app-export-contact__copy" :class="{ 'privacy-blur': privacyMode }">
                    <strong>{{ u.displayName || u.username }}</strong>
                    <small>{{ u.username }} · {{ u.postCount || 0 }} 条</small>
                  </span>
                </label>
              </div>
            </section>

            <main class="app-export-settings">
              <section class="app-export-panel" aria-labelledby="sns-export-format-title">
                <header class="app-export-panel__header">
                  <div>
                    <h3 id="sns-export-format-title">格式与文件</h3>
                    <p>选择离线 ZIP 内的结果格式和文件名。</p>
                  </div>
                  <span class="app-export-badge">{{ exportFormatLabel }}</span>
                </header>

                <div class="min-w-[280px]">
                  <div class="grid grid-cols-2 gap-2 sm:grid-cols-4" :class="'app-export-format-grid'">
                    <label
                      v-for="item in exportFormatOptions"
                      :key="item.value"
                      class="app-export-format-option"
                      :class="{ 'is-active': exportFormat === item.value }"
                    >
                      <input v-model="exportFormat" type="radio" :value="item.value" class="sr-only" />
                      <span class="app-export-format-option__code">{{ item.label }}</span>
                      <span class="app-export-format-option__meta">{{ item.meta }}</span>
                      <span class="app-export-radio-check" aria-hidden="true">
                        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 10 4 4 8-8" /></svg>
                      </span>
                    </label>
                  </div>
                </div>

                <div class="app-export-field">
                  <div class="app-export-field__label">
                    <label for="sns-export-file-name">ZIP 文件名</label>
                    <span>可选，留空时自动生成</span>
                  </div>
                  <input id="sns-export-file-name" v-model="exportFileName" type="text" class="app-export-input" placeholder="例如：朋友圈_2026-07-12.zip" />
                </div>
              </section>

              <section class="app-export-panel" aria-labelledby="sns-export-output-title">
                <header class="app-export-panel__header">
                  <div>
                    <h3 id="sns-export-output-title">保存位置</h3>
                    <p>{{ exportFolderHint }}</p>
                  </div>
                  <span class="app-export-badge" :class="{ 'app-export-badge--warning': !hasSelectedExportFolder }">{{ hasSelectedExportFolder ? exportFolderModeText : '需要目录' }}</span>
                </header>

                <div class="app-export-destination" :class="{ 'has-value': hasSelectedExportFolder }">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7.5h7l2-2h9v13H3z" /></svg>
                  <div class="app-export-destination__copy">
                    <strong :title="exportFolder || '尚未选择导出目录'">{{ exportFolder || '尚未选择导出目录' }}</strong>
                    <small>{{ hasSelectedExportFolder ? '导出完成后会写入此目录' : '开始导出前需要先完成此项' }}</small>
                  </div>
                  <button type="button" class="app-export-secondary-button" :disabled="exportSaveBusy" @click="chooseExportFolder">
                    {{ hasSelectedExportFolder ? '更改' : '选择目录' }}
                  </button>
                  <button v-if="hasSelectedExportFolder" type="button" class="app-export-icon-button app-export-icon-button--danger" :disabled="exportSaveBusy" title="清空目录" aria-label="清空导出目录" @click="clearExportFolderSelection">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" /></svg>
                  </button>
                </div>
              </section>

              <section v-if="exportJob" class="app-export-panel" aria-labelledby="sns-export-task-title">
                <header class="app-export-panel__header">
                  <div>
                    <h3 id="sns-export-task-title">导出任务</h3>
                    <p class="app-export-task-id">{{ exportJob.exportId || '-' }}</p>
                  </div>
                  <span class="app-export-status" :data-status="exportJob.status">{{ snsExportStatusLabel }}</span>
                </header>

                <div class="app-export-task-stats">
                  <div><span>联系人</span><strong>{{ exportJob.progress?.usersDone || 0 }}/{{ exportJob.progress?.usersTotal || 0 }}</strong></div>
                  <div><span>格式</span><strong>{{ exportActiveFormatLabel }}</strong></div>
                  <div><span>已复制媒体</span><strong>{{ exportJob.progress?.mediaCopied || 0 }}</strong></div>
                  <div><span>缺失媒体</span><strong>{{ exportJob.progress?.mediaMissing || 0 }}</strong></div>
                </div>

                <div class="app-export-progress-block">
                  <div class="app-export-progress-heading">
                    <span>总体进度 · {{ exportJob.progress?.postsExported || 0 }}/{{ exportJob.progress?.postsTotal || 0 }} 条动态</span>
                    <strong>{{ exportOverallPercent }}%</strong>
                  </div>
                  <div class="app-export-progress" role="progressbar" aria-label="朋友圈导出总体进度" :aria-valuenow="exportOverallPercent" aria-valuemin="0" aria-valuemax="100">
                    <span :style="{ transform: `scaleX(${exportOverallPercent / 100})` }"></span>
                  </div>
                </div>

                <div v-if="exportCurrentTargetLabel" class="app-export-progress-block">
                  <div class="app-export-progress-heading">
                    <span>当前：{{ exportCurrentTargetLabel }}（{{ exportJob.progress?.currentUserPostsDone || 0 }}/{{ exportJob.progress?.currentUserPostsTotal || 0 }}）</span>
                    <strong>{{ exportCurrentPercent != null ? `${exportCurrentPercent}%` : '处理中' }}</strong>
                  </div>
                  <div class="app-export-progress" role="progressbar" aria-label="当前联系人导出进度" :aria-valuenow="exportCurrentPercent == null ? undefined : exportCurrentPercent" aria-valuemin="0" aria-valuemax="100">
                    <span v-if="exportCurrentPercent != null" :style="{ transform: `scaleX(${exportCurrentPercent / 100})` }"></span>
                    <span v-else class="app-export-progress__indeterminate"></span>
                  </div>
                </div>

                <div v-if="exportMediaPrepareTotal > 0" class="app-export-progress-block">
                  <div class="app-export-progress-heading">
                    <span>媒体准备 · {{ exportMediaPrepared }}/{{ exportMediaPrepareTotal }}</span>
                    <strong>{{ exportMediaPreparePercent }}%</strong>
                  </div>
                  <div class="app-export-progress" role="progressbar" aria-label="朋友圈媒体准备进度" :aria-valuenow="exportMediaPreparePercent" aria-valuemin="0" aria-valuemax="100">
                    <span :style="{ transform: `scaleX(${exportMediaPreparePercent / 100})` }"></span>
                  </div>
                </div>

                <div v-if="isExportCancelling && canCancelSnsExport" class="app-export-result app-export-result--warning" role="status">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 17h.01" /></svg>
                  <span>已发送取消请求，正在等待当前步骤结束…</span>
                </div>
                <div v-else-if="exportJob.status === 'cancelled'" class="app-export-result app-export-result--warning" role="status">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 17h.01" /></svg>
                  <span>导出已取消。</span>
                </div>
                <div v-else-if="exportJob.status === 'error' && exportJob.error" class="app-export-result app-export-result--error" role="alert">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 17h.01" /></svg>
                  <span>{{ exportJob.error }}</span>
                </div>
                <div v-if="exportOutputPathText" class="app-export-result app-export-result--success">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></svg>
                  <span>已导出到：{{ exportOutputPathText }}</span>
                </div>
                <div v-if="exportSaveProgressText" class="app-export-result app-export-result--warning" role="status">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 17h.01" /></svg>
                  <span>{{ exportSaveProgressText }}</span>
                </div>
                <div v-if="exportSaveError" class="app-export-result app-export-result--error" role="alert">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 17h.01" /></svg>
                  <span>{{ exportSaveError }}</span>
                </div>
                <div v-else-if="exportSaveMsg" class="app-export-result app-export-result--success">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></svg>
                  <span>{{ exportSaveMsg }}</span>
                  <button v-if="exportJob.status === 'done' && exportJob.exportId && hasWebExportFolder" type="button" class="app-export-secondary-button" :disabled="exportSaveBusy" @click="saveSnsExportToSelectedFolder()">
                    {{ exportSaveBusy ? '保存中…' : '重新保存' }}
                  </button>
                </div>
                <button v-else-if="exportJob.status === 'done' && exportJob.exportId && hasWebExportFolder" type="button" class="app-export-secondary-button sns-export-save-button" :disabled="exportSaveBusy" @click="saveSnsExportToSelectedFolder()">
                  {{ exportSaveBusy ? '保存中…' : '保存到已选文件夹' }}
                </button>
              </section>
            </main>
          </div>
        </div>

        <footer class="app-export-footer">
          <div class="app-export-summary">
            <span>联系人 <strong>{{ exportSelectedCount }}</strong></span>
            <span class="app-export-summary__separator"></span>
            <span>格式 <strong>{{ exportFormatLabel }}</strong></span>
            <span class="app-export-summary__separator"></span>
            <span class="app-export-summary__path" :class="{ 'is-missing': !hasSelectedExportFolder }">{{ exportFolder || '尚未选择目录' }}</span>
          </div>
          <div class="app-export-footer__actions">
            <button type="button" class="app-export-secondary-button" @click="closeExportModal">取消</button>
            <button type="button" :class="canCancelSnsExport ? 'app-export-danger-button' : 'app-export-primary-button'" :disabled="exportPrimaryActionDisabled" @click="handleExportPrimaryAction">
              {{ exportPrimaryActionLabel }}
            </button>
          </div>
        </footer>
      </section>
    </div>

    <!-- Image preview modal -->
	    <div
	      v-if="previewCtx"
	      class="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center overflow-hidden"
	      @click="closeImagePreview"
        @wheel.prevent="onPreviewWheel"
        @dblclick.stop="resetPreviewImageTransform"
	    >
	      <div class="relative max-w-[92vw] max-h-[92vh] flex flex-col items-center" @click.stop>
	        <video
	          v-if="previewIsVideo"
	          ref="previewVideoEl"
	          :key="previewVideoKey"
	          :src="previewVideoSrc"
	          :poster="previewVideoPoster"
	          class="max-w-[90vw] max-h-[70vh] object-contain"
	          controls
	          autoplay
	          playsinline
	          @error="onPreviewVideoError"
	        ></video>
	        <video
	          v-else-if="previewLivePhotoVideoSrc && !previewHasLivePhotoVideoError"
	          ref="previewLiveVideoEl"
	          :src="previewLivePhotoVideoSrc"
	          :poster="previewSrc"
	          class="max-w-[90vw] max-h-[70vh] object-contain"
            :style="previewImageTransformStyle"
	          autoplay
	          loop
	          :muted="previewLivePhotoMuted"
	          playsinline
	          @error="onPreviewLivePhotoVideoError"
	        ></video>
	        <img
            v-else
            :src="previewSrc"
            alt="预览"
            class="max-w-[90vw] max-h-[70vh] object-contain select-none"
            :style="previewImageTransformStyle"
            draggable="false"
            @error="onPreviewImageError"
            @dblclick.stop="resetPreviewImageTransform"
          />

	        <div
	          v-if="previewIsVideo && previewVideoError"
	          class="mt-3 text-xs text-red-200 whitespace-pre-wrap text-center max-w-[90vw]"
	        >
	          {{ previewVideoError }}
	        </div>

	      </div>

        <div
          v-if="!previewIsVideo"
          class="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-full bg-black/35 border border-white/15 px-3 py-2 text-white backdrop-blur"
          @click.stop
          @dblclick.stop
        >
          <button
            type="button"
            class="w-8 h-8 rounded-full hover:bg-white/15 flex items-center justify-center text-lg leading-none"
            title="缩小"
            @click.stop="zoomPreviewImageOut"
          >−</button>
          <button
            type="button"
            class="min-w-[54px] h-8 px-2 rounded-full hover:bg-white/15 text-xs"
            title="重置缩放"
            @click.stop="resetPreviewImageTransform"
          >{{ previewImagePercent }}%</button>
          <button
            type="button"
            class="w-8 h-8 rounded-full hover:bg-white/15 flex items-center justify-center text-lg leading-none"
            title="放大"
            @click.stop="zoomPreviewImageIn"
          >+</button>
        </div>

	      <button
	        v-if="previewLivePhotoVideoSrc && !previewHasLivePhotoVideoError"
	        class="absolute top-4 right-16 text-white/80 hover:text-white p-2 rounded-full bg-black/30 hover:bg-black/50 transition-colors"
	        :title="previewLivePhotoMuted ? '开启声音' : '静音'"
	        @click.stop="togglePreviewLivePhotoMuted"
	      >
	        <svg v-if="previewLivePhotoMuted" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
	          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5L6 9H2v6h4l5 4V5z" />
	          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M23 9l-6 6M17 9l6 6" />
	        </svg>
	        <svg v-else class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
	          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5L6 9H2v6h4l5 4V5z" />
	          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.5 8.5a4 4 0 010 7" />
	          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.5 5.5a8 8 0 010 13" />
	        </svg>
	      </button>

	      <button
	        class="absolute top-4 right-4 text-white/80 hover:text-white p-2 rounded-full bg-black/30 hover:bg-black/50 transition-colors"
	        @click.stop="closeImagePreview"
	      >
	        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
	          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
	        </svg>
	      </button>
	    </div>
	  </div>
	</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'
import { parseTextWithEmoji } from '~/lib/wechat-emojis'
import { SNS_SETTING_USE_CACHE_KEY, readLocalBoolSetting } from '~/lib/desktop-settings'
import { reportServerErrorFromError, reportServerErrorFromResponse } from '~/lib/server-error-logging'

useHead({ title: '朋友圈 - 微信数据分析助手' })

const api = useApi()

const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const posts = ref([])
// De-dupe across pages to tolerate slight offset drift when the backend filters/omits some rows.
const seenPostIds = new Set()
// NOTE: Backend `/api/sns/timeline` uses SQL OFFSET on the raw timeline rows.
// The UI filters out some rows (e.g. type=7 cover), so `posts.length` must NOT be used as the next OFFSET.
const timelineOffset = ref(0)
const hasMore = ref(true)
// When timeline API reports `hasMore=false` but cached sidebar count indicates more, keep paging.
// If we hit an empty page, stop trying to avoid infinite requests.
const cachePagingExhausted = ref(false)
const timelineScrollEl = ref(null)
const isLoading = ref(false)
const error = ref('')
const snsUseCache = ref(true)

const coverData = ref(null)
const covers = ref([])
const coverIndex = ref(0)

const activeCover = computed(() => {
  const list = Array.isArray(covers.value) ? covers.value : []
  if (list.length > 0) {
    const idx = Math.max(0, Math.min(Number(coverIndex.value) || 0, list.length - 1))
    return list[idx] || null
  }
  return coverData.value
})

const prevCover = () => {
  const list = Array.isArray(covers.value) ? covers.value : []
  if (list.length <= 1) return
  const cur = Number(coverIndex.value) || 0
  coverIndex.value = (cur - 1 + list.length) % list.length
}

const nextCover = () => {
  const list = Array.isArray(covers.value) ? covers.value : []
  if (list.length <= 1) return
  const cur = Number(coverIndex.value) || 0
  coverIndex.value = (cur + 1) % list.length
}

const formatCoverTime = (tsSeconds) => {
  const t = Number(tsSeconds || 0)
  if (!t) return ''
  const d = new Date(t * 1000)
  const pad2 = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

// 左侧朋友圈联系人栏
const snsUsers = ref([])
const snsUserQuery = ref('')
// 空字符串表示“全部”
const selectedSnsUser = ref('')
const snsAvatarErrors = ref({})

const shouldHideSnsUser = (item) => {
  const username = String(item?.username || '').trim()
  const displayName = String(item?.displayName || '').trim()
  const postCount = Number(item?.postCount || 0)
  if (!username) return true
  if (!Number.isFinite(postCount) || postCount <= 0) return true
  return /^v3_/i.test(username) && /@stranger$/i.test(username) && (!displayName || displayName === username)
}

const visibleSnsUsers = computed(() => {
  const list = Array.isArray(snsUsers.value) ? snsUsers.value : []
  return list.filter((item) => !shouldHideSnsUser(item))
})

const snsAvatarErrorKey = (username) => String(username || '').trim()

const hasSnsAvatarError = (username) => {
  const key = snsAvatarErrorKey(username)
  return key ? !!snsAvatarErrors.value[key] : false
}

const onSnsAvatarError = (username) => {
  const key = snsAvatarErrorKey(username)
  if (!key || snsAvatarErrors.value[key]) return
  snsAvatarErrors.value = {
    ...snsAvatarErrors.value,
    [key]: true
  }
}

const selectedSnsUserInfo = computed(() => {
  const uname = String(selectedSnsUser.value || '').trim()
  if (!uname) return null
  const list = visibleSnsUsers.value
  return list.find((u) => String(u?.username || '').trim() === uname) || null
})

const showSnsCountMismatchHint = computed(() => {
  const uname = String(selectedSnsUser.value || '').trim()
  if (!uname) return false
  const cached = Number(selectedSnsUserInfo.value?.postCount || 0) || 0
  const shown = Array.isArray(posts.value) ? posts.value.length : 0
  return cached > 0 && shown > 0 && !hasMore.value && !isLoading.value && shown < cached
})

const filteredSnsUsers = computed(() => {
  const q = String(snsUserQuery.value || '').trim().toLowerCase()
  const list = visibleSnsUsers.value
  if (!q) return list
  return list.filter((u) => {
    const uname = String(u?.username || '').toLowerCase()
    const dn = String(u?.displayName || '').toLowerCase()
    return uname.includes(q) || dn.includes(q)
  })
})

const pageSize = 20

const apiBase = useApiBase()

// 朋友圈导出（离线 ZIP）
const exportFormat = ref('html')
const exportFormatOptions = [
  { value: 'html', label: 'HTML', meta: '可阅读网页' },
  { value: 'json', label: 'JSON', meta: '结构化数据' },
  { value: 'txt', label: 'TXT', meta: '纯文本记录' },
  { value: 'excel', label: 'Excel', meta: '表格工作簿' }
]
const exportFolder = ref('')
const exportFolderHandle = ref(null)
const exportSaveBusy = ref(false)
const exportSaveMsg = ref('')
const exportSaveError = ref('')
const exportSaveState = ref('idle')
const exportSaveBytesWritten = ref(0)
const exportSaveBytesTotal = ref(0)
const exportAutoSavedFor = ref('')
const exportJob = ref(null)
const exportError = ref('')
const exportModalOpen = ref(false)
const exportFileName = ref('')
const exportSearchQuery = ref('')
const exportSelectedUsernames = ref([])
const isExportCancelling = ref(false)
let exportEventSource = null
let exportPollTimer = null

const asNumber = (v) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0))

const formatBytes = (value) => {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const digits = size >= 100 || index === 0 ? 0 : size >= 10 ? 1 : 2
  return `${size.toFixed(digits)} ${units[index]}`
}

const resetExportSaveFeedback = ({ resetAutoSavedFor = false } = {}) => {
  exportSaveMsg.value = ''
  exportSaveError.value = ''
  exportSaveState.value = 'idle'
  exportSaveBytesWritten.value = 0
  exportSaveBytesTotal.value = 0
  if (resetAutoSavedFor) exportAutoSavedFor.value = ''
}

const isDesktopExportRuntime = () => {
  return !!(process.client && window?.wechatDesktop?.chooseDirectory)
}

const isWebDirectoryPickerSupported = () => {
  return !!(process.client && typeof window.showDirectoryPicker === 'function')
}

const hasDesktopExportFolder = computed(() => {
  return !!(isDesktopExportRuntime() && String(exportFolder.value || '').trim())
})

const hasWebExportFolder = computed(() => {
  return !!(!isDesktopExportRuntime() && isWebDirectoryPickerSupported() && exportFolderHandle.value)
})

const hasSelectedExportFolder = computed(() => {
  return !!(hasDesktopExportFolder.value || hasWebExportFolder.value)
})

const exportFormatLabel = computed(() => {
  return exportFormatOptions.find((item) => item.value === exportFormat.value)?.label || 'HTML'
})

const exportActiveFormat = computed(() => {
  const raw = String(exportJob.value?.options?.format || exportFormat.value || 'html').trim().toLowerCase()
  return exportFormatOptions.some((item) => item.value === raw) ? raw : 'html'
})

const exportActiveFormatLabel = computed(() => {
  return exportFormatOptions.find((item) => item.value === exportActiveFormat.value)?.label || 'HTML'
})

const exportOverallPercent = computed(() => {
  const status = String(exportJob.value?.status || '').trim()
  if (status === 'done') return 100
  const progress = exportJob.value?.progress || {}
  const postsTotal = asNumber(progress.postsTotal)
  const postsDone = asNumber(progress.postsExported)
  if (postsTotal > 0) return Math.round(clamp01(postsDone / postsTotal) * 100)
  const usersTotal = asNumber(progress.usersTotal)
  const usersDone = asNumber(progress.usersDone)
  if (usersTotal > 0) return Math.round(clamp01(usersDone / usersTotal) * 100)
  return 0
})

const exportCurrentPercent = computed(() => {
  const progress = exportJob.value?.progress || {}
  const total = asNumber(progress.currentUserPostsTotal)
  const done = asNumber(progress.currentUserPostsDone)
  if (total <= 0) return null
  return Math.round(clamp01(done / total) * 100)
})

const exportCurrentTargetLabel = computed(() => {
  const progress = exportJob.value?.progress || {}
  return String(progress.currentDisplayName || progress.currentUsername || '').trim()
})

const exportMediaPrepareTotal = computed(() => {
  return asNumber(exportJob.value?.progress?.mediaPrepareTotal)
})

const exportMediaPrepared = computed(() => {
  return asNumber(exportJob.value?.progress?.mediaPrepared)
})

const exportMediaPreparePercent = computed(() => {
  if (exportMediaPrepareTotal.value <= 0) return 0
  return Math.round(clamp01(exportMediaPrepared.value / exportMediaPrepareTotal.value) * 100)
})

const isSnsExportBusy = computed(() => {
  const status = String(exportJob.value?.status || '').trim()
  return status === 'queued' || status === 'running'
})

const snsExportStatusLabel = computed(() => {
  const status = String(exportJob.value?.status || '').trim()
  if (status === 'running') return '导出中'
  if (status === 'done') return '已完成'
  if (status === 'error') return '失败'
  if (status === 'cancelled') return '已取消'
  return '等待中'
})

const canCancelSnsExport = computed(() => {
  if (!exportJob.value?.exportId) return false
  const status = String(exportJob.value?.status || '').trim()
  return status === 'queued' || status === 'running'
})

const exportPrimaryActionLabel = computed(() => {
  if (canCancelSnsExport.value) return isExportCancelling.value ? '取消中…' : '取消导出'
  return isSnsExportBusy.value ? '导出中…' : '开始导出'
})

const exportPrimaryActionDisabled = computed(() => {
  if (canCancelSnsExport.value) return isExportCancelling.value
  return !selectedAccount.value || !exportSelectedCount.value || isSnsExportBusy.value
})

const handleExportPrimaryAction = async () => {
  if (canCancelSnsExport.value) {
    await cancelSnsExportJob()
    return
  }
  await startSnsExportFromModal()
}

const normalizeExportSelectedUsernames = (list) => {
  const validUsernames = new Set(
    visibleSnsUsers.value
      .map((item) => String(item?.username || '').trim())
      .filter(Boolean)
  )
  const seen = new Set()
  return (Array.isArray(list) ? list : []).reduce((acc, item) => {
    const username = String(item || '').trim()
    if (!username || seen.has(username)) return acc
    if (validUsernames.size > 0 && !validUsernames.has(username)) return acc
    seen.add(username)
    acc.push(username)
    return acc
  }, [])
}

const exportSelectedUsernameSet = computed(() => {
  return new Set(normalizeExportSelectedUsernames(exportSelectedUsernames.value))
})

const exportSelectedCount = computed(() => {
  return exportSelectedUsernameSet.value.size
})

const exportFilteredSnsUsers = computed(() => {
  const q = String(exportSearchQuery.value || '').trim().toLowerCase()
  const list = visibleSnsUsers.value
  if (!q) return list
  return list.filter((item) => {
    const username = String(item?.username || '').toLowerCase()
    const displayName = String(item?.displayName || '').toLowerCase()
    return username.includes(q) || displayName.includes(q)
  })
})

const exportFilteredSnsUsernames = computed(() => {
  return exportFilteredSnsUsers.value
    .map((item) => String(item?.username || '').trim())
    .filter(Boolean)
})

const areAllFilteredExportUsersSelected = computed(() => {
  const usernames = exportFilteredSnsUsernames.value
  if (!usernames.length) return false
  return usernames.every((username) => exportSelectedUsernameSet.value.has(username))
})

const clearExportSelectedUsers = () => {
  exportSelectedUsernames.value = []
}

const toggleSelectAllFilteredExportUsers = () => {
  const usernames = exportFilteredSnsUsernames.value
  if (!usernames.length) return

  if (areAllFilteredExportUsersSelected.value) {
    const removeSet = new Set(usernames)
    exportSelectedUsernames.value = normalizeExportSelectedUsernames(exportSelectedUsernames.value)
      .filter((username) => !removeSet.has(username))
    return
  }

  exportSelectedUsernames.value = normalizeExportSelectedUsernames([
    ...exportSelectedUsernames.value,
    ...usernames
  ])
}

const openExportModal = () => {
  exportModalOpen.value = true
  exportError.value = ''
  exportSearchQuery.value = ''
  exportFileName.value = ''
  exportSelectedUsernames.value = selectedSnsUser.value
    ? normalizeExportSelectedUsernames([selectedSnsUser.value])
    : []
}

const closeExportModal = () => {
  exportModalOpen.value = false
  exportError.value = ''
  exportSearchQuery.value = ''
}

const exportBackendZipPath = computed(() => {
  return String(exportJob.value?.zipPath || '').trim()
})

const exportFolderModeText = computed(() => {
  if (isDesktopExportRuntime()) return '\u684c\u9762\u7aef\u76ee\u5f55'
  if (isWebDirectoryPickerSupported()) return '\u6d4f\u89c8\u5668\u76ee\u5f55'
  return '\u9700\u9009\u62e9\u6587\u4ef6\u5939'
})

const exportFolderHint = computed(() => {
  if (isDesktopExportRuntime()) {
    return hasDesktopExportFolder.value
      ? '\u4f1a\u50cf\u666e\u901a\u804a\u5929\u8bb0\u5f55\u5bfc\u51fa\u4e00\u6837\uff0c\u5b8c\u6210\u540e\u76f4\u63a5\u5199\u5165\u4e0a\u9762\u7684\u6587\u4ef6\u5939\u3002'
      : '\u8bf7\u5148\u9009\u62e9\u6587\u4ef6\u5939\uff0c\u5bfc\u51fa\u5b8c\u6210\u540e\u4f1a\u76f4\u63a5\u5199\u5165\u8be5\u76ee\u5f55\u3002'
  }
  if (isWebDirectoryPickerSupported()) {
    return hasWebExportFolder.value
      ? '\u5bfc\u51fa\u5b8c\u6210\u540e\u4f1a\u81ea\u52a8\u4fdd\u5b58\u5230\u6240\u9009\u6d4f\u89c8\u5668\u76ee\u5f55\u3002'
      : '\u8bf7\u5148\u9009\u62e9\u6d4f\u89c8\u5668\u76ee\u5f55\uff0c\u5bfc\u51fa\u5b8c\u6210\u540e\u4f1a\u81ea\u52a8\u4fdd\u5b58\u3002'
  }
  return '\u5f53\u524d\u73af\u5883\u4e0d\u652f\u6301\u76ee\u5f55\u9009\u62e9\uff0c\u8bf7\u4f7f\u7528\u684c\u9762\u7aef\u6216 Chromium \u65b0\u7248\u6d4f\u89c8\u5668\u3002'
})

const guessSnsExportZipName = (job) => {
  const raw = String(job?.zipPath || '').trim()
  if (raw) {
    const name = raw.replace(/\\/g, '/').split('/').pop()
    if (name && name.toLowerCase().endsWith('.zip')) return name
  }
  const format = String(job?.options?.format || exportFormat.value || 'html').trim().toLowerCase() || 'html'
  const exportId = String(job?.exportId || '').trim() || 'export'
  return `wechat_sns_export_${format}_${exportId}.zip`
}

const exportSaveProgressText = computed(() => {
  if (exportSaveState.value !== 'saving') return ''
  const fileName = guessSnsExportZipName(exportJob.value)
  if (exportSaveBytesTotal.value > 0) {
    return `\u6b63\u5728\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\u76ee\u5f55\uff1a${fileName}\uff08${formatBytes(exportSaveBytesWritten.value)} / ${formatBytes(exportSaveBytesTotal.value)}\uff09`
  }
  return `\u6b63\u5728\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\u76ee\u5f55\uff1a${fileName}\uff08${formatBytes(exportSaveBytesWritten.value)}\uff09`
})

const exportOutputPathText = computed(() => {
  if (String(exportJob.value?.status || '') !== 'done') return ''
  if (hasWebExportFolder.value) return ''
  const raw = exportBackendZipPath.value
  if (!raw) return ''
  if (isDesktopExportRuntime()) return raw
  const requestedOutputDir = String(exportJob.value?.options?.outputDir || '').trim()
  return requestedOutputDir ? raw : ''
})

const chooseExportFolder = async () => {
  exportError.value = ''
  resetExportSaveFeedback()
  try {
    if (!process.client) {
      exportError.value = '\u5f53\u524d\u73af\u5883\u4e0d\u652f\u6301\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55'
      return
    }

    if (isDesktopExportRuntime()) {
      const result = await window.wechatDesktop.chooseDirectory({ title: '\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55' })
      if (result && !result.canceled && Array.isArray(result.filePaths) && result.filePaths.length > 0) {
        exportFolder.value = String(result.filePaths[0] || '').trim()
        exportFolderHandle.value = null
      }
      return
    }

    if (isWebDirectoryPickerSupported()) {
      const handle = await window.showDirectoryPicker()
      if (handle) {
        exportFolderHandle.value = handle
        exportFolder.value = `\u6d4f\u89c8\u5668\u76ee\u5f55\uff1a${String(handle.name || '\u5df2\u9009\u62e9')}`
      }
      return
    }

    exportError.value = '\u5f53\u524d\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u76ee\u5f55\u9009\u62e9\uff0c\u8bf7\u4f7f\u7528\u684c\u9762\u7aef\u6216 Chromium \u65b0\u7248\u6d4f\u89c8\u5668'
  } catch (error) {
    const message = String(error?.message || '').trim()
    if (error?.name === 'AbortError' || message.includes('The user aborted a request')) {
      return
    }
    exportError.value = error?.message || '\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55\u5931\u8d25'
  }
}

const clearExportFolderSelection = () => {
  exportFolder.value = ''
  exportFolderHandle.value = null
  resetExportSaveFeedback({ resetAutoSavedFor: true })
}

const getSnsExportDownloadUrl = (exportId) => {
  return `${apiBase}/sns/exports/${encodeURIComponent(String(exportId || ''))}/download`
}

const saveSnsExportToSelectedFolder = async (options = {}) => {
  const autoSave = !!options?.auto
  exportError.value = ''
  resetExportSaveFeedback()
  if (!process.client || !isWebDirectoryPickerSupported()) {
    exportError.value = '\u5f53\u524d\u73af\u5883\u4e0d\u652f\u6301\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\u76ee\u5f55'
    return
  }
  const handle = exportFolderHandle.value
  if (!handle || typeof handle.getFileHandle !== 'function') {
    exportError.value = '\u8bf7\u5148\u9009\u62e9\u6d4f\u89c8\u5668\u5bfc\u51fa\u76ee\u5f55'
    return
  }

  const exportId = exportJob.value?.exportId
  if (!exportId || String(exportJob.value?.status || '') !== 'done') {
    exportError.value = '\u5bfc\u51fa\u4efb\u52a1\u5c1a\u672a\u5b8c\u6210'
    return
  }

  exportSaveBusy.value = true
  exportSaveState.value = 'saving'
  try {
    const response = await fetch(getSnsExportDownloadUrl(exportId))
    if (!response.ok) {
      await reportServerErrorFromResponse(response, {
        method: 'GET',
        requestUrl: getSnsExportDownloadUrl(exportId),
        message: `\u4e0b\u8f7d\u5bfc\u51fa\u6587\u4ef6\u5931\u8d25\uff08${response.status}\uff09`,
        source: 'sns.exportDownload'
      })
      throw new Error(`\u4e0b\u8f7d\u5bfc\u51fa\u6587\u4ef6\u5931\u8d25\uff08${response.status}\uff09`)
    }
    exportSaveBytesTotal.value = asNumber(response.headers.get('Content-Length'))
    const fileName = guessSnsExportZipName(exportJob.value)
    const fileHandle = await handle.getFileHandle(fileName, { create: true })
    const writable = await fileHandle.createWritable()
    if (response.body && typeof response.body.getReader === 'function') {
      const reader = response.body.getReader()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          if (!value || !value.byteLength) continue
          await writable.write(value)
          exportSaveBytesWritten.value += value.byteLength
        }
        await writable.close()
      } catch (error) {
        try {
          await reader.cancel()
        } catch {}
        try {
          await writable.abort()
        } catch {}
        throw error
      }
    } else {
      const blob = await response.blob()
      exportSaveBytesWritten.value = asNumber(blob.size)
      if (exportSaveBytesTotal.value <= 0) exportSaveBytesTotal.value = exportSaveBytesWritten.value
      await writable.write(blob)
      await writable.close()
    }
    exportAutoSavedFor.value = String(exportId)
    exportSaveState.value = 'success'
    const folderLabel = String(exportFolder.value || '').trim() || '\u5df2\u9009\u76ee\u5f55'
    exportSaveMsg.value = autoSave
      ? `\u6d4f\u89c8\u5668\u76ee\u5f55\u81ea\u52a8\u4fdd\u5b58\u6210\u529f\uff1a${fileName}\n\u4f4d\u7f6e\uff1a${folderLabel}`
      : `\u6d4f\u89c8\u5668\u76ee\u5f55\u4fdd\u5b58\u6210\u529f\uff1a${fileName}\n\u4f4d\u7f6e\uff1a${folderLabel}`
  } catch (error) {
    exportSaveState.value = 'error'
    exportSaveError.value = `\u6d4f\u89c8\u5668\u76ee\u5f55\u4fdd\u5b58\u5931\u8d25\uff1a${error?.message || '\u672a\u77e5\u9519\u8bef'}`
  } finally {
    exportSaveBusy.value = false
  }
}
const stopSnsExportPolling = () => {
  if (exportEventSource) {
    try {
      exportEventSource.close()
    } catch {}
    exportEventSource = null
  }
  if (exportPollTimer) {
    clearInterval(exportPollTimer)
    exportPollTimer = null
  }
}

const startSnsExportHttpPolling = (exportId) => {
  if (!exportId) return
  stopSnsExportPolling()
  exportPollTimer = setInterval(async () => {
    try {
      const resp = await api.getSnsExport(exportId)
      exportJob.value = resp?.job || exportJob.value
      const st = String(exportJob.value?.status || '')
      if (st === 'done' || st === 'error' || st === 'cancelled') stopSnsExportPolling()
    } catch {
      // ignore transient errors
    }
  }, 1200)
}

const startSnsExportPolling = (exportId) => {
  stopSnsExportPolling()
  if (!exportId) return

  if (process.client && typeof window !== 'undefined' && typeof EventSource !== 'undefined') {
    const url = `${apiBase}/sns/exports/${encodeURIComponent(String(exportId))}/events`
    try {
      exportEventSource = new EventSource(url)
      exportEventSource.onmessage = (ev) => {
        try {
          const next = JSON.parse(String(ev.data || '{}'))
          exportJob.value = next || exportJob.value
          const st = String(exportJob.value?.status || '')
          if (st === 'done' || st === 'error' || st === 'cancelled') stopSnsExportPolling()
        } catch {}
      }
      exportEventSource.onerror = () => {
        try {
          exportEventSource?.close()
        } catch {}
        exportEventSource = null
        if (!exportPollTimer) startSnsExportHttpPolling(exportId)
      }
      return
    } catch {
      exportEventSource = null
    }
  }

  startSnsExportHttpPolling(exportId)
}

const ensureSnsExportFolderReady = () => {
  if (hasSelectedExportFolder.value) return true
  exportError.value = isDesktopExportRuntime() || isWebDirectoryPickerSupported()
    ? '\u8bf7\u5148\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55'
    : '\u5f53\u524d\u73af\u5883\u4e0d\u652f\u6301\u76ee\u5f55\u9009\u62e9\uff0c\u8bf7\u4f7f\u7528\u684c\u9762\u7aef\u6216 Chromium \u65b0\u7248\u6d4f\u89c8\u5668'
  return false
}

const cancelSnsExportJob = async () => {
  const exportId = String(exportJob.value?.exportId || '').trim()
  if (!exportId || !canCancelSnsExport.value || isExportCancelling.value) return
  exportError.value = ''
  isExportCancelling.value = true
  try {
    await api.cancelSnsExport(exportId)
    try {
      const resp = await api.getSnsExport(exportId)
      exportJob.value = resp?.job || exportJob.value
    } catch {
      // ignore refresh errors, polling/SSE will continue updating the job
    }
  } catch (e) {
    exportError.value = e?.message || '取消导出任务失败'
    isExportCancelling.value = false
  }
}

const startSnsExport = async ({ scope, usernames, fileName } = {}) => {
  if (!selectedAccount.value) return false
  exportError.value = ''
  isExportCancelling.value = false
  resetExportSaveFeedback({ resetAutoSavedFor: true })
  if (!ensureSnsExportFolderReady()) return false

  const normalizedScope = String(scope || '').trim() === 'all' ? 'all' : 'selected'
  const normalizedUsernames = normalizeExportSelectedUsernames(usernames)
  if (normalizedScope === 'selected' && normalizedUsernames.length === 0) {
    exportError.value = '请选择至少一个联系人'
    return false
  }

  try {
    const resp = await api.createSnsExport({
      account: selectedAccount.value,
      scope: normalizedScope,
      usernames: normalizedUsernames,
      format: exportFormat.value,
      use_cache: snsUseCache.value ? 1 : 0,
      output_dir: hasDesktopExportFolder.value ? String(exportFolder.value || '').trim() : null,
      file_name: String(fileName || '').trim() || null
    })
    exportJob.value = resp?.job || null
    const exportId = exportJob.value?.exportId
    if (exportId) startSnsExportPolling(exportId)
    return true
  } catch (e) {
    exportError.value = e?.message || '创建导出任务失败'
    return false
  }
}

const startSnsExportFromModal = async () => {
  const usernames = normalizeExportSelectedUsernames(exportSelectedUsernames.value)
  if (!usernames.length) {
    exportError.value = '请选择至少一个联系人'
    return
  }

  const created = await startSnsExport({
    scope: 'selected',
    usernames,
    fileName: exportFileName.value
  })
  if (created) exportError.value = ''
}

// Track failed images per-post, per-index to render placeholders instead of broken <img>.
const mediaErrors = ref({})

const mediaErrorKey = (postId, idx) => `${String(postId || '')}:${String(idx || 0)}`
const hasMediaError = (postId, idx) => !!mediaErrors.value[mediaErrorKey(postId, idx)]
const onMediaError = (postId, idx) => {
  mediaErrors.value[mediaErrorKey(postId, idx)] = true
}

// Article card thumbnail is best-effort: try SNS media thumb first, then fall back to
// extracting the cover from mp.weixin.qq.com HTML. Track per-post stage so we don't
// keep showing a broken <img>.
const articleThumbStage = ref({}) // postId -> 'proxy' | 'none'

const selfInfo = ref({ wxid: '', nickname: '' })

const loadSelfInfo = async () => {
  if (!selectedAccount.value) return
  try {
    const resp = await $fetch(`${apiBase}/sns/self_info?account=${encodeURIComponent(selectedAccount.value)}`)
    if (resp && resp.wxid) {
      selfInfo.value = resp
    }
  } catch (e) {
    await reportServerErrorFromError(e, {
      method: 'GET',
      requestUrl: `${apiBase}/sns/self_info?account=${encodeURIComponent(selectedAccount.value)}`,
      source: 'sns.loadSelfInfo',
      apiBase,
    })
    console.error('获取个人信息失败', e)
  }
}

const loadSnsUsers = async () => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) {
    snsUsers.value = []
    return
  }

  try {
    const resp = await api.listSnsUsers({ account: acc, limit: 5000 })
    snsUsers.value = Array.isArray(resp?.items) ? resp.items : []
  } catch (e) {
    console.error('加载朋友圈联系人失败', e)
    snsUsers.value = []
  }
}

const selectSnsUser = async (username) => {
  const next = String(username || '').trim()
  if (selectedSnsUser.value === next) return
  selectedSnsUser.value = next
  if (previewCtx.value) closeImagePreview()
  await loadPosts({ reset: true })
}

const getArticleThumbProxyUrl = (contentUrl) => {
  const u = String(contentUrl || '').trim()
  if (!u) return ''
  return `${apiBase}/sns/article_thumb?url=${encodeURIComponent(u)}`
}

const guessOfficialAccountNameFromTitle = (title) => {
  const t = String(title || '').trim()
  if (!t) return ''
  // Common patterns in Chinese titles: 《公众号名》, 「公众号名」, 【公众号名】
  const m = /[《「【](.+?)[》」】]/.exec(t)
  if (m && m[1]) return String(m[1]).trim()
  return ''
}

const getArticleCardThumbCandidates = (post) => {
  const list = Array.isArray(post?.media) ? post.media : []
  const mediaSrc = list.length > 0 ? getMediaThumbSrc(post, list[0], 0) : ''
  const proxySrc = getArticleThumbProxyUrl(post?.contentUrl)
  return { mediaSrc, proxySrc }
}

const getArticleCardThumbSrc = (post) => {
  const pid = String(post?.id || '').trim()
  const { mediaSrc, proxySrc } = getArticleCardThumbCandidates(post)
  const stage = String(articleThumbStage.value[pid] || '').trim()
  if (stage === 'proxy') return proxySrc || ''
  if (stage === 'none') return ''
  return mediaSrc || proxySrc
}

const onArticleThumbError = (post) => {
  const pid = String(post?.id || '').trim()
  if (!pid) return

  const { mediaSrc, proxySrc } = getArticleCardThumbCandidates(post)
  const stage = String(articleThumbStage.value[pid] || '').trim()

  if (stage === 'proxy') {
    articleThumbStage.value[pid] = 'none'
    return
  }

  // Default: try media first (if any), then fall back to proxy.
  if (mediaSrc && proxySrc && mediaSrc !== proxySrc) {
    articleThumbStage.value[pid] = 'proxy'
  } else {
    articleThumbStage.value[pid] = 'none'
  }
}

const extractMpBizFromUrl = (contentUrl) => {
  const u = String(contentUrl || '').trim()
  if (!u) return ''
  const m = /[?&]__biz=([^&#]+)/.exec(u)
  if (!m?.[1]) return ''
  try {
    return decodeURIComponent(m[1])
  } catch {
    return String(m[1])
  }
}

const getMomentOfficialAccount = (post) => {
  const off = (post && typeof post.official === 'object' && post.official) ? post.official : null
  const biz = String(off?.biz || extractMpBizFromUrl(post?.contentUrl) || '').trim()
  const username = String(off?.username || '').trim()
  const displayName = String(off?.displayName || '').trim() || guessOfficialAccountNameFromTitle(post?.title)
  const st0 = off?.serviceType
  const serviceType = (st0 === undefined || st0 === null || st0 === '') ? null : Number(st0)
  return { biz, username, displayName, serviceType }
}

const getFinderFeedThumbSrc = (post) => {
  const u = String(post?.finderFeed?.thumbUrl || '').trim()
  if (!u) return ''
  return getProxyExternalUrl(u)
}

const getMomentLinkCardUrl = (post) => {
  const u = String(post?.contentUrl || '').trim()
  if (u) return u

  const list = Array.isArray(post?.media) ? post.media : []
  const m0 = list.length > 0 ? list[0] : null
  const u2 = String(m0?.url || '').trim()
  return u2
}

const isExternalShareMoment = (post) => {
  const t = Number(post?.type || 0)
  return t === 42 || t === 5
}

const formatExternalShareUrlLabel = (url) => {
  const u = String(url || '').trim()
  if (!u) return ''
  try {
    const parsed = new URL(u)
    const host = String(parsed.hostname || '').replace(/^www\\./, '')
    const path = String(parsed.pathname || '')
    const out = `${host}${path && path !== '/' ? path : ''}`
    return out || u
  } catch {
    return u
  }
}

const formatExternalSharePlaceholder = (post) => {
  const t = Number(post?.type || 0)
  if (t === 42) return '音乐'
  return '链接'
}

const formatExternalShareCardTitle = (post) => {
  const title = String(post?.title || '').trim()
  if (title) return title
  const u = String(getMomentLinkCardUrl(post) || '').trim()
  if (u) return formatExternalShareUrlLabel(u)
  const t = Number(post?.type || 0)
  if (t === 42) return '音乐分享'
  return '外部分享'
}

const getExternalShareCardThumbSrc = (post) => {
  const pid = String(post?.id || '').trim()
  if (!pid) return ''

  const list = Array.isArray(post?.media) ? post.media : []
  const m0 = list.length > 0 ? list[0] : null
  if (!m0) return ''
  if (hasMediaError(pid, 0)) return ''
  return getMediaThumbSrc(post, m0, 0)
}

const onExternalShareCardThumbError = (post) => {
  const pid = String(post?.id || '').trim()
  if (!pid) return
  onMediaError(pid, 0)
}

const formatFinderFeedCardText = (post) => {
  const title = String(post?.title || '').trim()
  if (title) return title

  const desc = String(post?.finderFeed?.desc || '').trim()
  if (desc) return desc.replace(/\s+/g, ' ')

  const fallback = String(post?.contentDesc || '').trim()
  return fallback ? fallback.replace(/\s+/g, ' ') : '视频号'
}

const formatMomentOfficialSource = (post) => {
  if (Number(post?.type || 0) !== 3) return ''
  const info = getMomentOfficialAccount(post)
  // ServiceType: 1=服务号, 0=公众号 (when available). Fallbacks are best-effort.
  const prefix = info.serviceType === 1 ? '服务号' : '公众号'

  const name = String(info.displayName || '').trim()
  return name ? `${prefix}·${name}` : prefix
}

const formatExternalShareSourceLabel = (post) => {
  // Prefer DB-provided source name from Moments XML: `<appInfo><appName>...`
  const n = String(post?.sourceName || '').trim()
  if (n) return n

  const url = String(getMomentLinkCardUrl(post) || '').trim()
  if (!url) {
    return Number(post?.type || 0) === 42 ? '音乐' : '外部分享'
  }
  return formatExternalShareUrlLabel(url)
}

const formatMomentTypeLabel = (post) => {
  const t = Number(post?.type || 0)
  if (!t) return ''
  if (t === 3) return formatMomentOfficialSource(post)
  if (t === 28) {
    const name = String(post?.finderFeed?.nickname || '').trim()
    return name ? `视频号·${name}` : '视频号'
  }
  if (isExternalShareMoment(post)) return formatExternalShareSourceLabel(post)
  return ''
}

const onMomentTypeLabelClick = (post) => {
  if (!process.client) return
  const t = Number(post?.type || 0)
  if (t !== 3) return

  const info = getMomentOfficialAccount(post)
  if (info.username) {
    navigateTo(`/chat/${encodeURIComponent(info.username)}`)
    return
  }

  // Fallback: open MP profile page by __biz
  if (info.biz) {
    const url = `https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=${encodeURIComponent(info.biz)}#wechat_redirect`
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

// Right-click context menu (copy text / JSON) to help debug SNS parsing issues.
const contextMenu = ref({ visible: false, x: 0, y: 0, post: null })

const closeContextMenu = () => {
  contextMenu.value = { visible: false, x: 0, y: 0, post: null }
}

const openPostContextMenu = (e, post) => {
  if (!process.client) return
  e?.preventDefault?.()
  e?.stopPropagation?.()
  contextMenu.value = {
    visible: true,
    x: e?.clientX ?? 0,
    y: e?.clientY ?? 0,
    post
  }
}

const copyTextToClipboard = async (text) => {
  if (!process.client) return false
  if (typeof text !== 'string') return false

  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {}

  try {
    const el = document.createElement('textarea')
    el.value = text
    el.setAttribute('readonly', 'true')
    el.style.position = 'fixed'
    el.style.left = '-9999px'
    el.style.top = '-9999px'
    document.body.appendChild(el)
    el.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(el)
    return ok
  } catch {
    return false
  }
}

const onCopyPostTextClick = async () => {
  if (!process.client) return
  const post = contextMenu.value.post
  if (!post) return

  try {
    const text = String(post?.contentDesc || '').trim()
    if (!text) {
      window.alert('该朋友圈没有可复制的文本')
      return
    }
    const ok = await copyTextToClipboard(text)
    if (!ok) window.alert('复制失败：无法写入剪贴板')
  } catch (e) {
    console.error('复制失败:', e)
    window.alert('复制失败')
  } finally {
    closeContextMenu()
  }
}

const onCopyPostJsonClick = async () => {
  if (!process.client) return
  const post = contextMenu.value.post
  if (!post) return

  try {
    const raw = toRaw(post) || post
    const json = JSON.stringify(raw, (_k, v) => (typeof v === 'bigint' ? v.toString() : v), 2)
    const ok = await copyTextToClipboard(json)
    if (!ok) window.alert('复制失败：无法写入剪贴板')
  } catch (e) {
    console.error('复制失败:', e)
    window.alert('复制失败')
  } finally {
    closeContextMenu()
  }
}

const onScroll = (e) => {
  const { scrollTop, clientHeight, scrollHeight } = e.target
  if (scrollTop + clientHeight >= scrollHeight - 200) {
    if (hasMore.value && !isLoading.value) {
      loadPosts({ reset: false })
    }
  }
}

const postAvatarUrl = (username) => {
  const acc = String(selectedAccount.value || '').trim()
  const u = String(username || '').trim()
  if (!acc || !u) return ''
  return `${apiBase}/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(u)}`
}

const cleanLikeName = (v) => String(v ?? '').replace(/\u00A0/g, ' ').trim()
const formatLikes = (likes) => {
  const arr = Array.isArray(likes) ? likes : []
  const names = arr.map(cleanLikeName).filter(Boolean)
  return names.join('、')
}

const normalizeMediaUrl = (u) => {
  const raw = String(u || '').trim()
  if (!raw) return ''
  if (!/^https?:\/\//i.test(raw)) return raw
  try {
    const host = new URL(raw).hostname.toLowerCase()
    if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
      return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
    }
  } catch {}
  return raw
}

// WeFlow replaces http->https for SNS CDN URLs; do the same before proxying/fetching.
const upgradeTencentHttps = (u) => {
  const raw = String(u || '').trim()
  if (!raw) return ''
  if (!/^http:\/\//i.test(raw)) return raw
  try {
    const host = new URL(raw).hostname.toLowerCase()
    if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn') || host.endsWith('.tc.qq.com') || host.endsWith('.video.qq.com')) {
      return raw.replace(/^http:\/\//i, 'https://')
    }
  } catch {}
  return raw
}

const normalizeHex32 = (value) => {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  const hex = raw.replace(/[^0-9a-fA-F]/g, '').toLowerCase()
  return hex.length >= 32 ? hex.slice(0, 32) : ''
}

const mediaSizeKey = (m) => {
  const t = String(m?.type ?? '')
  const w = String(m?.size?.width || m?.size?.w || '').trim()
  const h = String(m?.size?.height || m?.size?.h || '').trim()
  const total = String(m?.size?.totalSize || m?.size?.total_size || m?.size?.total || '').trim()
  return `${t}:${w}:${h}:${total}`
}

const mediaSizeGroupIndex = (post, m, idx) => {
  const list = Array.isArray(post?.media) ? post.media : []
  const key = mediaSizeKey(m)
  const i0 = Number(idx) || 0
  if (!key || i0 <= 0) return i0
  let count = 0
  for (let i = 0; i < i0; i++) {
    if (mediaSizeKey(list[i]) === key) count++
  }
  return count
}

const getSnsMediaUrl = (post, m, idx, rawUrl, options = {}) => {
  const raw = upgradeTencentHttps(String(rawUrl || '').trim())
  if (!raw) return ''
  const rawLower = raw.toLowerCase()
  const preferFull = !!options?.preferFull

  // If backend already provides a local media endpoint, rewrite it to the effective API base
  // (so web builds with a custom API port still work).
  if (rawLower.startsWith('/api/')) return `${apiBase}${raw.slice(4)}`
  if (rawLower.startsWith('blob:') || rawLower.startsWith('data:')) return raw

  // For Moments images/thumbnails, prefer a backend endpoint that can decrypt local cache.
  if (/^https?:\/\//i.test(raw)) {
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn') || host.endsWith('.tc.qq.com')) {
        const acc = String(selectedAccount.value || '').trim()
        const ct = String(post?.createTime || '').trim()
        const w = String(m?.size?.width || m?.size?.w || '').trim()
        const h = String(m?.size?.height || m?.size?.h || '').trim()
        const ts = String(m?.size?.totalSize || m?.size?.total_size || m?.size?.total || '').trim()
        const sizeIdx = mediaSizeGroupIndex(post, m, idx)
        let md5 = normalizeHex32(m?.urlAttrs?.md5 || m?.thumbAttrs?.md5 || m?.urlAttrs?.MD5 || m?.thumbAttrs?.MD5)
        if (!md5) {
          const match = /[?&]md5=([0-9a-fA-F]{16,32})/.exec(raw)
          if (match?.[1]) md5 = normalizeHex32(match[1])
        }

        const parts = new URLSearchParams()
        if (acc) parts.set('account', acc)
        if (ct) parts.set('create_time', ct)
        if (w) parts.set('width', w)
        if (h) parts.set('height', h)
        if (/^\d+$/.test(ts)) parts.set('total_size', ts)
        parts.set('idx', String(Number(sizeIdx) || 0))

        const pid = String(post?.id || post?.tid || '').trim()
        if (pid) parts.set('post_id', pid)

        const mid = String(m?.id || '').trim()
        if (mid) parts.set('media_id', mid)

        const postType = String(post?.type || '1').trim()
        if (postType) parts.set('post_type', postType)

        const mediaType = String(m?.type || '2').trim()
        if (mediaType) parts.set('media_type', mediaType)

        const thumbCandidate = String(m?.thumb || m?.thumbUrl || '').trim()
        const isThumbRequest = (!preferFull) && !!thumbCandidate && raw === upgradeTencentHttps(thumbCandidate)
        const token = String(
          isThumbRequest
            ? (m?.thumbToken || m?.thumbUrlToken || m?.thumbAttrs?.token || m?.token || m?.urlAttrs?.token || '')
            : (m?.token || m?.urlAttrs?.token || m?.thumbToken || m?.thumbUrlToken || m?.thumbAttrs?.token || '')
        ).trim()
        if (token) parts.set('token', token)

        const key = String(
          isThumbRequest
            ? (m?.thumbKey || m?.thumbAttrs?.key || m?.key || m?.urlAttrs?.key || '')
            : (m?.key || m?.urlAttrs?.key || m?.thumbKey || m?.thumbAttrs?.key || '')
        ).trim()
        if (key) parts.set('key', key)

        parts.set('use_cache', snsUseCache.value ? '1' : '0')
        // When cache is disabled, bust browser caching so backend really downloads+decrypts each time.
        if (!snsUseCache.value) parts.set('_t', String(Date.now()))
        if (md5) parts.set('md5', md5)
        if (preferFull) parts.set('variant', 'full')
        // 修改后端媒体匹配逻辑时递增版本号，避免浏览器复用旧的错误缓存。
        parts.set('v', preferFull ? '12' : '11')
        parts.set('url', raw)
        return `${apiBase}/sns/media?${parts.toString()}`
      }
    } catch {}
  }

  return normalizeMediaUrl(raw)
}

const getMediaThumbSrc = (post, m, idx = 0) => {
  return getSnsMediaUrl(post, m, idx, m?.thumb || m?.url)
}

const getMediaPreviewSrc = (post, m, idx = 0) => {
  return getSnsMediaUrl(post, m, idx, m?.url || m?.originUrl || m?.originalUrl || m?.thumb || m?.thumbUrl, { preferFull: true })
}

const inferSnsDownloadExt = (blob, url, isVideo = false) => {
  const type = String(blob?.type || '').toLowerCase()
  if (type.includes('mp4')) return 'mp4'
  if (type.includes('quicktime')) return 'mov'
  if (type.includes('webm')) return 'webm'
  if (type.includes('png')) return 'png'
  if (type.includes('webp')) return 'webp'
  if (type.includes('gif')) return 'gif'
  if (type.includes('jpeg') || type.includes('jpg')) return 'jpg'
  try {
    const pathname = new URL(String(url || ''), window.location.href).pathname
    const m = pathname.match(/\.([a-z0-9]{2,5})$/i)
    if (m?.[1]) return m[1].toLowerCase()
  } catch {}
  return isVideo ? 'mp4' : 'jpg'
}

const makeSnsDownloadName = (post, m, idx, ext) => {
  const ts = Number(post?.createTime || 0)
  const baseTime = ts > 0 ? new Date(ts * 1000) : new Date()
  const pad2 = (n) => String(n).padStart(2, '0')
  const stamp = `${baseTime.getFullYear()}${pad2(baseTime.getMonth() + 1)}${pad2(baseTime.getDate())}_${pad2(baseTime.getHours())}${pad2(baseTime.getMinutes())}${pad2(baseTime.getSeconds())}`
  const mediaId = String(m?.id || m?.mediaId || '').trim().replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 24)
  const suffix = mediaId || String(Number(idx) || 0)
  return `sns_${stamp}_${suffix}.${ext || 'jpg'}`
}

const triggerBrowserDownload = (blob, filename) => {
  if (!process.client || typeof document === 'undefined') return false
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60000)
  return true
}

const downloadSnsMedia = async (post, m, idx = 0) => {
  if (!process.client) return
  const isVideo = Number(m?.type || 0) === 6
  const candidates = [
    isVideo ? getSnsRemoteVideoSrc(post, m) : '',
    getMediaPreviewSrc(post, m, idx),
    getMediaThumbSrc(post, m, idx),
    normalizeMediaUrl(upgradeTencentHttps(String(m?.url || m?.originUrl || m?.originalUrl || m?.thumb || '').trim()))
  ].map((u) => String(u || '').trim()).filter(Boolean)

  const seen = new Set()
  const urls = candidates.filter((u) => {
    if (seen.has(u)) return false
    seen.add(u)
    return true
  })
  if (!urls.length) return

  for (const url of urls) {
    try {
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const blob = await resp.blob()
      if (!blob || !blob.size) throw new Error('empty media')
      const ext = inferSnsDownloadExt(blob, url, isVideo)
      triggerBrowserDownload(blob, makeSnsDownloadName(post, m, idx, ext))
      return
    } catch {}
  }

  try {
    window.open(urls[0], '_blank', 'noopener,noreferrer')
  } catch {}
}

const commentImageErrors = ref({})

const commentImageKey = (post, comment, idx = 0) => {
  const postId = String(post?.id || post?.tid || '').trim()
  const commentId = String(comment?.id || comment?.commentId || comment?.cmtid || '').trim()
  const img = Array.isArray(comment?.images) ? comment.images[idx] : null
  const imageId = String(img?.id || img?.mediaId || img?.media_id || img?.md5 || img?.url || img?.thumbUrl || '').trim()
  return `${postId}:${commentId}:${imageId}:${Number(idx) || 0}`
}

const getCommentImages = (comment) => {
  const list = Array.isArray(comment?.images) ? comment.images : []
  return list.filter((img) => {
    if (!img || typeof img !== 'object') return false
    return !!String(img.url || img.thumb || img.thumbUrl || img.thumb_url || '').trim()
  })
}

const toCommentImageMedia = (img) => {
  if (!img || typeof img !== 'object') return null
  const thumb = String(img.thumb || img.thumbUrl || img.thumb_url || img.url || '').trim()
  const url = String(img.url || img.originUrl || img.origin_url || thumb || '').trim()
  const mediaId = String(img.id || img.mediaId || img.media_id || '').trim()
  const md5 = String(img.md5 || '').trim()
  const token = String(img.token || img.urlToken || img.url_token || '').trim()
  const key = String(img.key || '').trim()
  const thumbToken = String(img.thumbToken || img.thumbUrlToken || img.thumb_url_token || token || '').trim()
  const thumbKey = String(img.thumbKey || img.thumb_key || key || '').trim()
  const width = Number(img.width || img.size?.width || 0) || 0
  const height = Number(img.height || img.size?.height || 0) || 0
  const totalSize = Number(img.fileSize || img.file_size || img.size?.totalSize || img.size?.total_size || 0) || 0

  return {
    type: Number(img.type || 2) || 2,
    id: mediaId,
    mediaId,
    url,
    thumb,
    token,
    key,
    thumbToken,
    thumbUrlToken: thumbToken,
    thumbKey,
    md5,
    urlAttrs: {
      ...(img.urlAttrs || {}),
      token: token || img.urlAttrs?.token || '',
      key: key || img.urlAttrs?.key || '',
      md5: md5 || img.urlAttrs?.md5 || ''
    },
    thumbAttrs: {
      ...(img.thumbAttrs || {}),
      token: thumbToken || img.thumbAttrs?.token || '',
      key: thumbKey || img.thumbAttrs?.key || '',
      md5: md5 || img.thumbAttrs?.md5 || ''
    },
    size: {
      ...(img.size || {}),
      width: width || img.size?.width,
      height: height || img.size?.height,
      totalSize: totalSize || img.size?.totalSize || img.size?.total_size
    }
  }
}

const getCommentImageThumbSrc = (post, img, idx = 0) => {
  const m = toCommentImageMedia(img)
  if (!m) return ''
  return getSnsMediaUrl(post, m, idx, m.thumb || m.url)
}

const hasCommentImageError = (post, comment, idx = 0) => {
  return !!commentImageErrors.value[commentImageKey(post, comment, idx)]
}

const onCommentImageError = (post, comment, idx = 0) => {
  commentImageErrors.value = {
    ...commentImageErrors.value,
    [commentImageKey(post, comment, idx)]: true
  }
}

const openCommentImagePreview = (post, img, idx = 0) => {
  const m = toCommentImageMedia(img)
  if (!m) return
  openImagePreview(post, m, idx)
}


const getSnsVideoUrl = (postId, mediaId) => {
  // 本地缓存视频
  const acc = String(selectedAccount.value || '').trim()
  if (!acc || !postId || !mediaId) return ''
  return `${apiBase}/sns/video?account=${encodeURIComponent(acc)}&post_id=${encodeURIComponent(postId)}&media_id=${encodeURIComponent(mediaId)}`
}

const getSnsRemoteVideoSrc = (post, m) => {
  // Remote mp4 (download+decrypt on backend; WeFlow compatible).
  const acc = String(selectedAccount.value || '').trim()
  const rawUrl = upgradeTencentHttps(String(m?.url || '').trim())
  if (!acc || !rawUrl) return ''

  const token = String(m?.token || m?.urlAttrs?.token || m?.thumbAttrs?.token || '').trim()
  const key = String(m?.videoKey || m?.key || m?.urlAttrs?.key || '').trim()

  const parts = new URLSearchParams()
  parts.set('account', acc)
  parts.set('url', rawUrl)
  if (token) parts.set('token', token)
  if (key) parts.set('key', key)
  parts.set('use_cache', snsUseCache.value ? '1' : '0')
  // When cache is disabled, bust browser caching so backend really downloads+decrypts each time.
  if (!snsUseCache.value) parts.set('_t', String(Date.now()))
  parts.set('v', '1')
  return `${apiBase}/sns/video_remote?${parts.toString()}`
}

const localVideoStatus = ref({})

const videoStatusKey = (postId, mediaId) => `${String(postId)}:${String(mediaId)}`

const onLocalVideoLoaded = (postId, mediaId) => {
  localVideoStatus.value[videoStatusKey(postId, mediaId)] = 'loaded'
}

const onLocalVideoError = (postId, mediaId) => {
  localVideoStatus.value[videoStatusKey(postId, mediaId)] = 'error'
}


const isLocalVideoLoaded = (postId, mediaId) => {
  return localVideoStatus.value[videoStatusKey(postId, mediaId)] === 'loaded'
}

// 实况（Live Photo）：鼠标悬停播放远程解密视频
const activeLivePhotoKey = ref('')
const livePhotoVideoErrors = ref({})
const livePhotoHoverVideoEl = ref(null)
const livePhotoHoverMuted = ref(false)

const livePhotoKey = (postId, idx) => `${String(postId || '')}:${String(idx || 0)}`

const isLivePhotoMedia = (m) => {
  const lp = m?.livePhoto
  return !!(lp && typeof lp === 'object' && String(lp?.url || '').trim())
}

const isLivePhotoActive = (postId, idx) => activeLivePhotoKey.value === livePhotoKey(postId, idx)
const hasLivePhotoVideoError = (postId, idx) => !!livePhotoVideoErrors.value[livePhotoKey(postId, idx)]

const playLivePhotoHoverVideo = async ({ allowFallbackMute } = { allowFallbackMute: true }) => {
  if (!process.client) return
  const k = String(activeLivePhotoKey.value || '')
  if (!k) return

  await nextTick()
  if (activeLivePhotoKey.value !== k) return

  const el = livePhotoHoverVideoEl.value
  if (!el) return

  el.muted = !!livePhotoHoverMuted.value
  try {
    el.volume = livePhotoHoverMuted.value ? 0 : 1
  } catch {}

  try {
    await el.play()
  } catch {
    if (allowFallbackMute && !livePhotoHoverMuted.value) {
      livePhotoHoverMuted.value = true
      await nextTick()
      if (activeLivePhotoKey.value !== k) return
      const el2 = livePhotoHoverVideoEl.value
      if (!el2) return
      el2.muted = true
      try {
        el2.volume = 0
      } catch {}
      try {
        await el2.play()
      } catch {}
    }
  }
}

const toggleLivePhotoHoverMuted = () => {
  livePhotoHoverMuted.value = !livePhotoHoverMuted.value
  void playLivePhotoHoverVideo({ allowFallbackMute: false })
}

const onLivePhotoEnter = (postId, idx, m) => {
  if (!isLivePhotoMedia(m)) return
  if (hasLivePhotoVideoError(postId, idx)) return
  activeLivePhotoKey.value = livePhotoKey(postId, idx)
  livePhotoHoverMuted.value = false
  void playLivePhotoHoverVideo({ allowFallbackMute: true })
}

const onLivePhotoLeave = (postId, idx, m) => {
  if (!isLivePhotoMedia(m)) return
  const k = livePhotoKey(postId, idx)
  if (activeLivePhotoKey.value === k) activeLivePhotoKey.value = ''
}

const onLivePhotoVideoError = (postId, idx) => {
  const k = livePhotoKey(postId, idx)
  livePhotoVideoErrors.value[k] = true
  if (activeLivePhotoKey.value === k) activeLivePhotoKey.value = ''
}

const getLivePhotoVideoSrc = (post, m, idx = 0) => {
  const acc = String(selectedAccount.value || '').trim()
  const lp = (m && typeof m === 'object') ? m.livePhoto : null
  const rawUrl = upgradeTencentHttps(String(lp?.url || '').trim())
  if (!acc || !rawUrl) return ''

  const token = String(lp?.token || m?.token || m?.urlAttrs?.token || '').trim()
  const key = String(lp?.key || m?.videoKey || '').trim()

  const parts = new URLSearchParams()
  parts.set('account', acc)
  parts.set('url', rawUrl)
  if (token) parts.set('token', token)
  if (key) parts.set('key', key)
  parts.set('use_cache', snsUseCache.value ? '1' : '0')
  // When cache is disabled, bust browser caching so backend really downloads+decrypts each time.
  if (!snsUseCache.value) parts.set('_t', String(Date.now()))
  // Version bump for frontend cache busting when endpoint changes.
  parts.set('v', '1')
  return `${apiBase}/sns/video_remote?${parts.toString()}`
}

// 图片预览
const previewCtx = ref(null) // { post, media, idx }
const PREVIEW_IMAGE_MIN_SCALE = 0.25
const PREVIEW_IMAGE_MAX_SCALE = 8
const PREVIEW_IMAGE_WHEEL_STEP = 1.18
const previewImageScale = ref(1)
const previewImageUseThumbFallback = ref(false)

const previewSrc = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return ''
  if (previewImageUseThumbFallback.value) return getMediaThumbSrc(ctx.post, ctx.media, ctx.idx)
  return getMediaPreviewSrc(ctx.post, ctx.media, ctx.idx)
})

const previewImagePercent = computed(() => Math.round(previewImageScale.value * 100))

const previewImageTransformStyle = computed(() => ({
  transform: `scale(${previewImageScale.value})`,
  transformOrigin: 'center center',
  transition: 'transform 120ms ease-out',
  cursor: previewImageScale.value > 1 ? 'zoom-out' : 'zoom-in'
}))

const setPreviewImageScale = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return
  previewImageScale.value = Math.min(PREVIEW_IMAGE_MAX_SCALE, Math.max(PREVIEW_IMAGE_MIN_SCALE, n))
}

const resetPreviewImageTransform = () => {
  previewImageScale.value = 1
}

const zoomPreviewImageBy = (factor) => {
  setPreviewImageScale(previewImageScale.value * Number(factor || 1))
}

const zoomPreviewImageIn = () => {
  zoomPreviewImageBy(PREVIEW_IMAGE_WHEEL_STEP)
}

const zoomPreviewImageOut = () => {
  zoomPreviewImageBy(1 / PREVIEW_IMAGE_WHEEL_STEP)
}

const onPreviewWheel = (e) => {
  if (previewIsVideo.value) return
  const direction = Number(e?.deltaY || 0) > 0 ? -1 : 1
  const steps = Math.max(1, Math.min(6, Math.ceil(Math.abs(Number(e?.deltaY || 0)) / 120)))
  zoomPreviewImageBy(Math.pow(PREVIEW_IMAGE_WHEEL_STEP, direction * steps))
}

const onPreviewImageError = () => {
  if (previewImageUseThumbFallback.value) return
  previewImageUseThumbFallback.value = true
}

const previewVideoEl = ref(null)
const previewVideoMode = ref('') // 'local' | 'remote' | 'raw'
const previewVideoError = ref('')
const previewVideoTried = reactive({ local: false, remote: false, raw: false })

const resetPreviewVideo = () => {
  previewVideoMode.value = ''
  previewVideoError.value = ''
  previewVideoTried.local = false
  previewVideoTried.remote = false
  previewVideoTried.raw = false
}

const previewIsVideo = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return false
  return Number(ctx.media?.type || 0) === 6
})

const previewVideoPoster = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return ''
  if (Number(ctx.media?.type || 0) !== 6) return ''
  return getMediaThumbSrc(ctx.post, ctx.media, ctx.idx) || ''
})

const previewVideoSrc = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return ''
  if (Number(ctx.media?.type || 0) !== 6) return ''

  const local = getSnsVideoUrl(ctx.post?.id, ctx.media?.id)
  const remote = getSnsRemoteVideoSrc(ctx.post, ctx.media)
  const raw = upgradeTencentHttps(String(ctx.media?.url || '').trim())

  const mode = String(previewVideoMode.value || '').toLowerCase()
  if (mode === 'local') return local
  if (mode === 'remote') return remote
  if (mode === 'raw') return raw
  return local || remote || raw || ''
})

const previewVideoKey = computed(() => {
  if (!previewIsVideo.value) return ''
  return `${String(previewVideoMode.value || '')}:${String(previewVideoSrc.value || '')}`
})

const previewLivePhotoVideoSrc = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return ''
  if (!isLivePhotoMedia(ctx.media)) return ''
  return getLivePhotoVideoSrc(ctx.post, ctx.media, ctx.idx)
})

const previewLiveVideoEl = ref(null)
const previewLivePhotoMuted = ref(false)

const previewHasLivePhotoVideoError = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return false
  if (!isLivePhotoMedia(ctx.media)) return false
  return hasLivePhotoVideoError(ctx.post?.id, ctx.idx)
})

const playPreviewLiveVideo = async ({ allowFallbackMute } = { allowFallbackMute: true }) => {
  if (!process.client) return
  await nextTick()
  const el = previewLiveVideoEl.value
  if (!el) return

  el.muted = !!previewLivePhotoMuted.value
  try {
    el.volume = previewLivePhotoMuted.value ? 0 : 1
  } catch {}

  try {
    // Autoplay with sound may be blocked by browser policies; we fallback to muted playback so preview still animates.
    await el.play()
  } catch (e) {
    if (allowFallbackMute && !previewLivePhotoMuted.value) {
      previewLivePhotoMuted.value = true
      await nextTick()
      const el2 = previewLiveVideoEl.value
      if (!el2) return
      el2.muted = true
      try {
        el2.volume = 0
      } catch {}
      try {
        await el2.play()
      } catch {}
    }
  }
}

const togglePreviewLivePhotoMuted = () => {
  previewLivePhotoMuted.value = !previewLivePhotoMuted.value
  void playPreviewLiveVideo({ allowFallbackMute: false })
}

const onPreviewLivePhotoVideoError = () => {
  const ctx = previewCtx.value
  if (!ctx) return
  onLivePhotoVideoError(ctx.post?.id, ctx.idx)
}

watch(
  () => previewLivePhotoVideoSrc.value,
  (src) => {
    if (!src) return
    previewLivePhotoMuted.value = false
    void playPreviewLiveVideo({ allowFallbackMute: true })
  }
)

const openImagePreview = (post, m, idx = 0) => {
  if (!process.client) return
  resetPreviewVideo()
  resetPreviewImageTransform()
  previewImageUseThumbFallback.value = false
  // Stop any background hover-playing live photo when opening the preview.
  activeLivePhotoKey.value = ''
  // Preview is an intentional action; allow retry even if hover playback failed once.
  if (isLivePhotoMedia(m)) {
    const k = livePhotoKey(post?.id, idx)
    if (k) {
      try {
        delete livePhotoVideoErrors.value[k]
      } catch {}
    }
  }
  previewCtx.value = { post, media: m, idx: Number(idx) || 0 }
  document.body.style.overflow = 'hidden'
}

const openVideoPreview = (post, m, idx = 0) => {
  if (!process.client) return
  resetPreviewVideo()
  resetPreviewImageTransform()
  previewImageUseThumbFallback.value = false
  activeLivePhotoKey.value = ''

  const local = getSnsVideoUrl(post?.id, m?.id)
  const remote = getSnsRemoteVideoSrc(post, m)
  const raw = upgradeTencentHttps(String(m?.url || '').trim())

  if (local) previewVideoMode.value = 'local'
  else if (remote) previewVideoMode.value = 'remote'
  else if (raw) previewVideoMode.value = 'raw'
  else previewVideoError.value = '视频地址缺失。'

  previewCtx.value = { post, media: m, idx: Number(idx) || 0 }
  document.body.style.overflow = 'hidden'
}

const onPreviewVideoError = () => {
  const ctx = previewCtx.value
  if (!ctx) return
  if (Number(ctx.media?.type || 0) !== 6) return

  const current = String(previewVideoMode.value || '').toLowerCase()
  if (current === 'local') previewVideoTried.local = true
  if (current === 'remote') previewVideoTried.remote = true
  if (current === 'raw') previewVideoTried.raw = true

  // Fallback order: local -> remote -> raw
  const remote = getSnsRemoteVideoSrc(ctx.post, ctx.media)
  if (!previewVideoTried.remote && remote) {
    previewVideoMode.value = 'remote'
    return
  }

  const raw = upgradeTencentHttps(String(ctx.media?.url || '').trim())
  if (!previewVideoTried.raw && raw) {
    previewVideoMode.value = 'raw'
    return
  }

  previewVideoError.value = '视频加载失败：可能是本地缓存不存在，或远程下载/解密失败。'
}

const closeImagePreview = () => {
  if (!process.client) return
  previewCtx.value = null
  resetPreviewVideo()
  resetPreviewImageTransform()
  previewImageUseThumbFallback.value = false
  document.body.style.overflow = ''
}

const onMediaClick = (post, m, idx = 0) => {
  if (!process.client) return
  const mt = Number(m?.type || 0)

  // 视频点击逻辑
  if (mt === 6) {
    openVideoPreview(post, m, idx)
    return
  }

  // 图片：打开预览
  openImagePreview(post, m, idx)
}

const formatRelativeTime = (tsSeconds) => {
  const t = Number(tsSeconds || 0)
  if (!t) return ''
  const now = Date.now()
  const diff = Math.max(0, Math.floor((now - t * 1000) / 1000))
  if (diff < 60) return '刚刚'
  const mins = Math.floor(diff / 60)
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}个月前`
  const years = Math.floor(months / 12)
  return `${years}年前`
}

const loadAccounts = async () => {
  error.value = ''
  await chatAccounts.ensureLoaded({ force: true })
  if (!selectedAccount.value) {
    error.value = chatAccounts.error || '未检测到已解密账号，请先解密数据库。'
  }
}

const loadPosts = async ({ reset }) => {
  if (!selectedAccount.value) return
  if (isLoading.value) return
  error.value = ''
  isLoading.value = true
  try {
    if (reset) {
      timelineOffset.value = 0
      hasMore.value = true
      cachePagingExhausted.value = false
      seenPostIds.clear()
      posts.value = []
      if (process.client && timelineScrollEl.value) {
        try {
          timelineScrollEl.value.scrollTop = 0
        } catch {}
      }
    }
    const offset = reset ? 0 : Number(timelineOffset.value || 0)
    const resp = await api.listSnsTimeline({
      account: selectedAccount.value,
      limit: pageSize,
      offset,
      usernames: selectedSnsUser.value ? [String(selectedSnsUser.value).trim()] : []
    })
    const items = Array.isArray(resp?.timeline) ? resp.timeline : []
    // Advance offset by the number of rows consumed by the backend.
    // When `hasMore` is true, the backend definitely scanned at least `limit` raw rows (even if it filtered some out).
    // When `hasMore` is false, we're at the end, so advance by the actual returned count.
    const limitUsed = Number(resp?.limit || pageSize) || pageSize
    timelineOffset.value = offset + (resp?.hasMore ? limitUsed : items.length)

    const nextItems = []
    for (const p of items) {
      if (!p || p.type === 7) continue
      const pid = String(p.id || p.tid || '').trim()
      if (pid) {
        if (seenPostIds.has(pid)) continue
        seenPostIds.add(pid)
      }
      nextItems.push(p)
    }

    if (reset) {
      posts.value = nextItems
      coverData.value = resp?.cover || null
      const cs = Array.isArray(resp?.covers) ? resp.covers : []
      covers.value = cs.length > 0 ? cs : (resp?.cover ? [resp.cover] : [])
      coverIndex.value = 0
    } else {
      posts.value = [...posts.value, ...nextItems]
    }

    // Keep sidebar count from lagging behind what we've already loaded (useful when sqlite snapshot is incomplete).
    const selUname = String(selectedSnsUser.value || '').trim()
    if (selUname && Array.isArray(snsUsers.value) && snsUsers.value.length > 0) {
      const idx = snsUsers.value.findIndex((u) => String(u?.username || '').trim() === selUname)
      if (idx >= 0) {
        const cur = Number(snsUsers.value[idx]?.postCount || 0) || 0
        if (posts.value.length > cur) {
          const nextUsers = [...snsUsers.value]
          nextUsers[idx] = { ...nextUsers[idx], postCount: posts.value.length }
          snsUsers.value = nextUsers
        }
      }
    }

    const backendHasMore = !!resp?.hasMore
    if (!backendHasMore && items.length === 0) {
      cachePagingExhausted.value = true
    }

    const cachedTotal = selUname ? (Number(selectedSnsUserInfo.value?.postCount || 0) || 0) : 0
    const shown = Array.isArray(posts.value) ? posts.value.length : 0
    const allowCachePaging = !cachePagingExhausted.value && cachedTotal > 0 && shown < cachedTotal
    hasMore.value = backendHasMore || allowCachePaging
  } catch (e) {
    error.value = e?.message || '加载朋友圈失败'
  } finally {
    isLoading.value = false

    // Auto-trigger next page when we're already near bottom (e.g. first page too short to scroll,
    // or we need to continue paging from cache after WCDB "visible subset" ends).
    if (process.client) {
      setTimeout(async () => {
        try {
          await nextTick()
        } catch {}
        if (error.value) return
        if (isLoading.value || !hasMore.value) return
        const el = timelineScrollEl.value
        if (!el) return
        const { scrollTop, clientHeight, scrollHeight } = el
        if (scrollTop + clientHeight >= scrollHeight - 200) {
          loadPosts({ reset: false })
        }
      }, 0)
    }
  }
}


watch(
    () => selectedAccount.value,
    async (v, oldV) => {
      if (v && v !== oldV) {
        stopSnsExportPolling()
        exportJob.value = null
        exportError.value = ''
        isExportCancelling.value = false
        exportModalOpen.value = false
        exportFileName.value = ''
        exportSearchQuery.value = ''
        exportSelectedUsernames.value = []
        resetExportSaveFeedback({ resetAutoSavedFor: true })
        snsUserQuery.value = ''
        selectedSnsUser.value = ''
        snsUsers.value = []
        snsAvatarErrors.value = {}
        activeLivePhotoKey.value = ''
        livePhotoVideoErrors.value = {}
        if (previewCtx.value) closeImagePreview()
        await loadSelfInfo()
        await loadSnsUsers()
        await loadPosts({ reset: true })
      }
    },
    { immediate: true }
)

watch(
  () => ({
    exportId: String(exportJob.value?.exportId || ''),
    status: String(exportJob.value?.status || '')
  }),
  async ({ exportId, status }) => {
    if (!process.client || status !== 'done' || !exportId) return
    if (!hasWebExportFolder.value) return
    if (exportAutoSavedFor.value === exportId) return
    if (exportSaveBusy.value) return
    await saveSnsExportToSelectedFolder({ auto: true })
  }
)

watch(
  () => ({
    exportId: String(exportJob.value?.exportId || ''),
    status: String(exportJob.value?.status || '')
  }),
  ({ exportId, status }, prev) => {
    if (!exportId) {
      isExportCancelling.value = false
      return
    }
    if (exportId !== String(prev?.exportId || '')) {
      isExportCancelling.value = false
      return
    }
    if (status !== 'queued' && status !== 'running') {
      isExportCancelling.value = false
    }
  }
)



onMounted(async () => {
  privacyStore.init()
  snsUseCache.value = readLocalBoolSetting(SNS_SETTING_USE_CACHE_KEY, true)
  await loadAccounts()
})

const onGlobalClick = () => {
  if (contextMenu.value.visible) closeContextMenu()
}

const onGlobalKeyDown = (e) => {
  if (!process.client) return
  if (String(e?.key || '') === 'Escape') {
    if (exportModalOpen.value) {
      closeExportModal()
      return
    }
    if (previewCtx.value) closeImagePreview()
    if (contextMenu.value.visible) closeContextMenu()
  }
}

onMounted(() => {
  if (!process.client) return
  document.addEventListener('click', onGlobalClick)
  document.addEventListener('keydown', onGlobalKeyDown)
})

onUnmounted(() => {
  if (!process.client) return
  stopSnsExportPolling()
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onGlobalKeyDown)
})

const getProxyExternalUrl = (url) => {
  // 目前难以计算enc，代理获取封面图（thumbnail）
  const u = String(url || '').trim()
  if (!u) return ''
  return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(u)}`
}


</script>
