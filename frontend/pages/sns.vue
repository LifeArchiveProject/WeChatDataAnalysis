<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- 左侧朋友圈联系人 -->
    <div class="w-[280px] flex flex-col min-h-0 border-r border-gray-200 bg-[#EDEDED]">
      <div class="p-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold text-gray-700">朋友圈联系人</div>
          <div class="text-xs text-gray-500">{{ snsUsers.length }}</div>
        </div>
        <input
            v-model="snsUserQuery"
            type="text"
            placeholder="搜索"
            class="mt-2 w-full px-3 py-2 rounded-md border border-gray-200 bg-white text-sm outline-none focus:ring-2 focus:ring-[#576b95]/30 focus:border-[#576b95]"
        />

        <div class="mt-2 flex gap-2">
          <button
              type="button"
              class="flex-1 px-3 py-2 rounded-md text-sm border border-gray-200 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              @click="onExportAllClick"
              :disabled="!selectedAccount || exportJob?.status === 'running'"
              title="导出全部朋友圈（HTML 离线 ZIP）"
          >
            导出全部
          </button>
          <button
              type="button"
              class="flex-1 px-3 py-2 rounded-md text-sm border border-gray-200 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              @click="onExportCurrentClick"
              :disabled="!selectedAccount || !selectedSnsUser || exportJob?.status === 'running'"
              title="导出当前选中联系人（HTML 离线 ZIP）"
          >
            导出此人
          </button>
        </div>
        <div v-if="exportError" class="mt-2 text-xs text-red-600 whitespace-pre-wrap">{{ exportError }}</div>
        <div v-else-if="exportJob" class="mt-2 text-xs text-gray-500">
          <span>导出状态：{{ exportJob.status }}</span>
          <button
              v-if="exportJob.status === 'done' && exportJob.exportId"
              type="button"
              class="ml-2 text-xs text-[#576b95] hover:underline bg-transparent border-0 p-0"
              @click="downloadSnsExport(exportJob.exportId)"
          >
            下载 ZIP
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
                v-if="postAvatarUrl(u.username)"
                :src="postAvatarUrl(u.username)"
                :alt="u.displayName || u.username"
                class="w-full h-full object-cover"
                referrerpolicy="no-referrer"
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
    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <div ref="timelineScrollEl" class="flex-1 overflow-auto min-h-0 bg-white" @scroll="onScroll">
	        <div class="max-w-2xl mx-auto px-4 py-4">
            <div class="relative w-full mb-12 -mt-4 bg-white">
              <div class="h-64 w-full bg-[#333333] relative overflow-hidden group">
                <img
                    v-if="activeCover && activeCover.media && activeCover.media.length > 0"
                    :src="getSnsMediaUrl(activeCover, activeCover.media[0], 0, activeCover.media[0].url)"
                    class="w-full h-full object-cover"
                    alt="朋友圈封面"
                    @load="onCoverMediaLoaded(activeCover, $event)"
                />
                <div
                    v-if="snsMediaStageLabel(snsCoverStageKey(activeCover)) || snsMediaStageLoading[snsCoverStageKey(activeCover)]"
                    class="absolute top-3 left-3 z-20 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                >
                  <div
                      class="text-[10px] px-2 py-0.5 rounded backdrop-blur-sm shadow-sm"
                      :class="snsMediaStageBadgeColorClass(snsCoverStageKey(activeCover))"
                      :title="snsMediaStageBadgeTitle(snsCoverStageKey(activeCover))"
                  >
                    {{ snsMediaStageLabel(snsCoverStageKey(activeCover)) || '识别中' }}
                  </div>
                </div>

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
                          @loadeddata="onLocalVideoLoaded(post.id, post.media[0].id); onSnsMediaLoaded(post, post.media[0], 0)"
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
                          @loadeddata="onSnsMediaLoaded(post, post.media[0], 0)"
                          @error="onLivePhotoVideoError(post.id, 0)"
                      ></video>

                      <img
                          v-else
                          :src="getMediaThumbSrc(post, post.media[0], 0)"
                          class="rounded-sm max-h-[360px] object-cover"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @load="onSnsMediaLoaded(post, post.media[0], 0, $event)"
                          @error="onMediaError(post.id, 0)"
                      />

                      <div
                          v-if="snsMediaStageLabel(snsMediaStageKey(post.id, 0, 'thumb')) || snsMediaStageLoading[snsMediaStageKey(post.id, 0, 'thumb')]"
                          class="absolute top-2 left-2 z-20 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                      >
                        <div
                            class="text-[10px] px-2 py-0.5 rounded backdrop-blur-sm shadow-sm"
                            :class="snsMediaStageBadgeColorClass(snsMediaStageKey(post.id, 0, 'thumb'))"
                            :title="snsMediaStageBadgeTitle(snsMediaStageKey(post.id, 0, 'thumb'))"
                        >
                          {{ snsMediaStageLabel(snsMediaStageKey(post.id, 0, 'thumb')) || '识别中' }}
                        </div>
                      </div>
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
                          @loadeddata="onLocalVideoLoaded(post.id, m.id); onSnsMediaLoaded(post, m, idx)"
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
                          @loadeddata="onSnsMediaLoaded(post, m, idx)"
                          @error="onLivePhotoVideoError(post.id, idx)"
                      ></video>
                      <img
                          v-else-if="!hasMediaError(post.id, idx) && getMediaThumbSrc(post, m, idx)"
                          :src="getMediaThumbSrc(post, m, idx)"
                          class="w-full h-full object-cover"
                          alt=""
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @load="onSnsMediaLoaded(post, m, idx, $event)"
                          @error="onMediaError(post.id, idx)"
                      />

                      <div
                          v-if="snsMediaStageLabel(snsMediaStageKey(post.id, idx, 'thumb')) || snsMediaStageLoading[snsMediaStageKey(post.id, idx, 'thumb')]"
                          class="absolute top-1 left-1 z-20 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                      >
                        <div
                            class="text-[10px] px-1.5 py-0.5 rounded backdrop-blur-sm shadow-sm"
                            :class="snsMediaStageBadgeColorClass(snsMediaStageKey(post.id, idx, 'thumb'))"
                            :title="snsMediaStageBadgeTitle(snsMediaStageKey(post.id, idx, 'thumb'))"
                        >
                          {{ snsMediaStageLabel(snsMediaStageKey(post.id, idx, 'thumb')) || '识别中' }}
                        </div>
                      </div>
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

	    <!-- 图片预览弹窗 + 候选匹配选择 -->
	    <div
	      v-if="previewCtx"
	      class="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center"
	      @click="closeImagePreview"
	    >
	      <div class="relative max-w-[92vw] max-h-[92vh] flex flex-col items-center" @click.stop>
	        <video
	          v-if="previewLivePhotoVideoSrc && !previewHasLivePhotoVideoError"
	          ref="previewLiveVideoEl"
	          :src="previewLivePhotoVideoSrc"
	          :poster="previewSrc"
	          class="max-w-[90vw] max-h-[70vh] object-contain"
	          autoplay
	          loop
	          :muted="previewLivePhotoMuted"
	          playsinline
	          @error="onPreviewLivePhotoVideoError"
	        ></video>
	        <img v-else :src="previewSrc" alt="预览" class="max-w-[90vw] max-h-[70vh] object-contain" />

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
import { parseTextWithEmoji } from '~/utils/wechat-emojis'
import { SNS_SETTING_USE_CACHE_KEY, readLocalBoolSetting } from '~/utils/desktop-settings'

useHead({ title: '朋友圈 - 微信数据分析助手' })

// Nuxt dev mode can load hundreds of module resources, quickly filling the default
// ResourceTiming buffer (150). If it overflows, `<img>` requests may not produce
// entries, making Server-Timing based stage detection always fall back to "unknown".
if (process.client) {
  try {
    if (typeof performance !== 'undefined' && performance?.setResourceTimingBufferSize) {
      performance.setResourceTimingBufferSize(5000)
    }
  } catch {}
}

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

const selectedSnsUserInfo = computed(() => {
  const uname = String(selectedSnsUser.value || '').trim()
  if (!uname) return null
  const list = Array.isArray(snsUsers.value) ? snsUsers.value : []
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
  const list = Array.isArray(snsUsers.value) ? snsUsers.value : []
  if (!q) return list
  return list.filter((u) => {
    const uname = String(u?.username || '').toLowerCase()
    const dn = String(u?.displayName || '').toLowerCase()
    return uname.includes(q) || dn.includes(q)
  })
})

const pageSize = 20

const apiBase = useApiBase()

// 朋友圈导出（HTML 离线 ZIP）
const exportJob = ref(null)
const exportError = ref('')
let exportEventSource = null
let exportPollTimer = null

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

const downloadSnsExport = (exportId) => {
  if (!process.client) return
  const id = String(exportId || '').trim()
  if (!id) return
  const url = `${apiBase}/sns/exports/${encodeURIComponent(id)}/download`
  window.open(url, '_blank', 'noopener,noreferrer')
}

const onExportAllClick = async () => {
  if (!selectedAccount.value) return
  exportError.value = ''
  try {
    const resp = await api.createSnsExport({
      account: selectedAccount.value,
      scope: 'all',
      usernames: [],
      use_cache: snsUseCache.value ? 1 : 0
    })
    exportJob.value = resp?.job || null
    const exportId = exportJob.value?.exportId
    if (exportId) startSnsExportPolling(exportId)
  } catch (e) {
    exportError.value = e?.message || '创建导出任务失败'
  }
}

const onExportCurrentClick = async () => {
  if (!selectedAccount.value) return
  const uname = String(selectedSnsUser.value || '').trim()
  if (!uname) return
  exportError.value = ''
  try {
    const resp = await api.createSnsExport({
      account: selectedAccount.value,
      scope: 'selected',
      usernames: [uname],
      use_cache: snsUseCache.value ? 1 : 0
    })
    exportJob.value = resp?.job || null
    const exportId = exportJob.value?.exportId
    if (exportId) startSnsExportPolling(exportId)
  } catch (e) {
    exportError.value = e?.message || '创建导出任务失败'
  }
}

// Track failed images per-post, per-index to render placeholders instead of broken <img>.
const mediaErrors = ref({})

const mediaErrorKey = (postId, idx) => `${String(postId || '')}:${String(idx || 0)}`
const hasMediaError = (postId, idx) => !!mediaErrors.value[mediaErrorKey(postId, idx)]
const onMediaError = (postId, idx) => {
  mediaErrors.value[mediaErrorKey(postId, idx)] = true
}

// Hover badge: show which SNS media pipeline stage produced the image.
// Backend provides `X-SNS-Source` (and optional `X-SNS-Hit-Type`, `X-SNS-X-Enc`) on `/api/sns/media` responses.
const snsMediaStage = ref({}) // stageKey -> { source, hitType, xEnc }
const snsMediaStageLoading = ref({}) // stageKey -> boolean
const snsMediaStageInFlight = new Set()

const isSnsMediaApiUrl = (url) => {
  const u = String(url || '').trim()
  return !!u && u.includes('/api/sns/media')
}

const snsMediaStageKey = (postId, idx, kind = 'thumb') => {
  const acc = String(selectedAccount.value || '').trim()
  const pid = String(postId || '').trim()
  return `sns:${acc}:${pid}:${String(Number(idx) || 0)}:${String(kind || 'thumb')}`
}

const snsCoverStageKey = (cover) => {
  const acc = String(selectedAccount.value || '').trim()
  const cid = String(cover?.id || cover?.tid || cover?.createTime || '').trim()
  return `sns:${acc}:cover:${cid || '0'}`
}

const snsMediaStageLabel = (key) => {
  const k = String(key || '').trim()
  if (!k) return ''
  const info = snsMediaStage.value[k]
  if (!info || typeof info !== 'object') return ''

  const source = String(info?.source || '').trim()
  const hitType = String(info?.hitType || '').trim()

  if (source === 'remote-cache') return '远程缓存'
  if (source === 'remote-decrypt') return '远程解密'
  if (source === 'remote') return '远程直出'
  if (source === 'deterministic-hash') return hitType ? `本地命中(${hitType})` : '本地命中'
  if (source === 'manual-pick') return '手动匹配'
  if (source === 'local-heuristic') return '本地兜底'
  if (source === 'local-heuristic-next') return '本地兜底(跳过)'
  if (source === 'browser-cache') return '浏览器缓存'
  if (source === 'bkg-cover') return '封面缓存'
  if (source === 'proxy') return '远程代理'
  if (source === 'unknown') return '未知'
  if (source === 'error') return '获取失败'
  return source || '未知'
}

const snsMediaStageBadgeColorClass = (key) => {
  const k = String(key || '').trim()
  const source = String(snsMediaStage.value?.[k]?.source || '').trim()

  if (source.startsWith('remote')) return 'bg-emerald-600/85 text-white'
  if (source === 'deterministic-hash') return 'bg-sky-600/85 text-white'
  if (source.startsWith('local')) return 'bg-blue-600/85 text-white'
  if (source === 'manual-pick') return 'bg-amber-600/90 text-white'
  if (source === 'browser-cache') return 'bg-slate-600/85 text-white'
  if (source === 'proxy') return 'bg-fuchsia-600/85 text-white'
  if (source === 'bkg-cover') return 'bg-indigo-600/85 text-white'
  if (source === 'error') return 'bg-red-600/85 text-white'
  return 'bg-black/50 text-white'
}

const snsMediaStageBadgeTitle = (key) => {
  const k = String(key || '').trim()
  const info = snsMediaStage.value?.[k]
  if (!info || typeof info !== 'object') return ''
  const source = String(info?.source || '').trim()
  const hitType = String(info?.hitType || '').trim()
  const xEnc = String(info?.xEnc || '').trim()

  const parts = []
  if (source) parts.push(`source=${source}`)
  if (hitType) parts.push(`hit=${hitType}`)
  if (xEnc) parts.push(`x-enc=${xEnc}`)
  return parts.join(' · ')
}

const readSnsStageFromResourceTiming = (url) => {
  try {
    if (!process.client) return null
    if (typeof performance === 'undefined' || !performance?.getEntriesByName) return null
    const u = String(url || '').trim()
    if (!u) return null
    const entries = performance.getEntriesByName(u) || []
    const latest = [...entries].reverse().find((e) => String(e?.entryType || '') === 'resource')
    if (!latest) return null

    // Prefer backend-injected stage info from `Server-Timing`.
    const st = latest?.serverTiming
    if (Array.isArray(st) && st.length > 0) {
      let source = ''
      let hitType = ''
      let xEnc = ''
      for (const item of st) {
        const name = String(item?.name || '').trim()
        const desc = String(item?.description || '').trim()
        if (name === 'sns_source' && desc) source = desc
        else if (name.startsWith('sns_source_')) source = name.slice('sns_source_'.length) || desc
        else if (name === 'sns_hit' && desc) hitType = desc
        else if (name.startsWith('sns_hit_')) hitType = name.slice('sns_hit_'.length) || desc
        else if (name === 'sns_xenc' && desc) xEnc = desc
        else if (name.startsWith('sns_xenc_')) xEnc = name.slice('sns_xenc_'.length) || desc
      }
      if (source) return { source, hitType, xEnc }
    }

    // When DevTools shows "(from disk cache)", browsers may not expose `serverTiming` at all.
    // Best-effort: infer a browser cache hit from ResourceTiming sizes.
    const transferSize = Number(latest?.transferSize)
    if (Number.isFinite(transferSize) && transferSize === 0) {
      return { source: 'browser-cache', hitType: 'transfer=0', xEnc: '' }
    }

    return null
  } catch {
    return null
  }
}

const ensureSnsMediaStage = async (key, url) => {
  if (!process.client) return
  const k = String(key || '').trim()
  const u = String(url || '').trim()
  if (!k || !u) return
  if (!isSnsMediaApiUrl(u)) return

  const existingSource = String(snsMediaStage.value?.[k]?.source || '').trim()
  if (existingSource && existingSource !== 'unknown') return
  if (snsMediaStageLoading.value[k]) return
  if (snsMediaStageInFlight.has(k)) return

  snsMediaStageInFlight.add(k)
  snsMediaStageLoading.value[k] = true

  try {
    // Prefer stage info from the *same* request that loaded the <img>/<video> element
    // (via Server-Timing + Timing-Allow-Origin), to avoid a non-idempotent extra fetch.
    let info = null
    for (const delayMs of [0, 0, 16, 50, 120, 250, 500]) {
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))
      info = readSnsStageFromResourceTiming(u)
      if (info) break
    }
    snsMediaStage.value[k] = info || { source: 'unknown', hitType: '', xEnc: '' }
  } finally {
    snsMediaStageLoading.value[k] = false
    snsMediaStageInFlight.delete(k)
  }
}

const eventCurrentSrc = (ev) => {
  try {
    const el = ev?.target || ev?.currentTarget
    return String(el?.currentSrc || el?.src || '').trim()
  } catch {
    return ''
  }
}

const onSnsMediaLoaded = (post, m, idx = 0, ev) => {
  const pid = String(post?.id || '').trim()
  if (!pid) return
  const key = snsMediaStageKey(pid, idx, 'thumb')
  const u = eventCurrentSrc(ev) || getMediaThumbSrc(post, m, idx)
  ensureSnsMediaStage(key, u)
}

const onCoverMediaLoaded = (cover, ev) => {
  const c = cover || activeCover.value
  if (!c || !Array.isArray(c.media) || c.media.length <= 0) return
  const u = eventCurrentSrc(ev) || getSnsMediaUrl(c, c.media[0], 0, c.media[0].url)
  ensureSnsMediaStage(snsCoverStageKey(c), u)
}

watch([selectedAccount, snsUseCache], () => {
  snsMediaStage.value = {}
  snsMediaStageLoading.value = {}
  snsMediaStageInFlight.clear()
})

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
  if (!w || !h) return ''
  return `${t}:${w}x${h}`
}

// Our backend matches SNS cache images by width/height and then uses `idx` to
// pick the N-th match. `idx` must be the index within the same size-group,
// not the global media index in the post, otherwise images can shift.
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

const getSnsMediaUrl = (post, m, idx, rawUrl) => {
  const raw = upgradeTencentHttps(String(rawUrl || '').trim())
  if (!raw) return ''
  const rawLower = raw.toLowerCase()

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
        // const pick = getSnsMediaOverridePick(post?.id, idx)
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
        const pid = String(post?.id || '').trim()
        if (pid) parts.set('post_id', pid)

        const mid = String(m?.id || '').trim()
        if (mid) parts.set('media_id', mid)

        const postType = String(post?.type || '1').trim()
        if (postType) parts.set('post_type', postType)

        const mediaType = String(m?.type || '2').trim()
        if (mediaType) parts.set('media_type', mediaType)

        const token = String(m?.token || m?.urlAttrs?.token || m?.thumbAttrs?.token || '').trim()
        if (token) parts.set('token', token)

        const key = String(m?.key || m?.urlAttrs?.key || m?.thumbAttrs?.key || '').trim()
        if (key) parts.set('key', key)

        parts.set('use_cache', snsUseCache.value ? '1' : '0')
        // When cache is disabled, bust browser caching so backend really downloads+decrypts each time.
        if (!snsUseCache.value) parts.set('_t', String(Date.now()))

        if (md5) parts.set('md5', md5)
        // Bump this when changing backend matching logic to avoid stale cached wrong images.
        parts.set('v', '9')
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
  return getSnsMediaUrl(post, m, idx, m?.url || m?.thumb)
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

// 图片预览 + 候选匹配选择
const previewCtx = ref(null) // { post, media, idx }
const previewCandidatesOpen = ref(false)
const previewCandidates = reactive({
  loading: false,
  loadingMore: false,
  error: '',
  items: [],
  count: 0,
  hasMore: false
})

const resetPreviewCandidates = () => {
  previewCandidates.loading = false
  previewCandidates.loadingMore = false
  previewCandidates.error = ''
  previewCandidates.items = []
  previewCandidates.count = 0
  previewCandidates.hasMore = false
}

const previewSrc = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return ''
  return getMediaPreviewSrc(ctx.post, ctx.media, ctx.idx)
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


const loadPreviewCandidates = async ({ reset }) => {
  const ctx = previewCtx.value
  if (!ctx) return
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return

  const toInt = (v) => Number.parseInt(String(v || '').trim(), 10) || 0
  const w = toInt(ctx.media?.size?.width || ctx.media?.size?.w)
  const h = toInt(ctx.media?.size?.height || ctx.media?.size?.h)

  // Without dimensions, local matching is too noisy; keep it empty.
  if (w <= 0 || h <= 0) {
    resetPreviewCandidates()
    return
  }

  const limit = 24
  const offset = reset ? 0 : (previewCandidates.items?.length || 0)

  if (reset) {
    resetPreviewCandidates()
    previewCandidates.loading = true
  } else {
    previewCandidates.loadingMore = true
  }
  previewCandidates.error = ''

  try {
    const resp = await api.listSnsMediaCandidates({
      account: acc,
      create_time: Number(ctx.post?.createTime || 0),
      width: w,
      height: h,
      limit,
      offset
    })
    const items = Array.isArray(resp?.items) ? resp.items : []
    previewCandidates.count = Number(resp?.count || 0)
    previewCandidates.hasMore = !!resp?.hasMore
    if (reset) {
      previewCandidates.items = items
    } else {
      previewCandidates.items = [...(previewCandidates.items || []), ...items]
    }
  } catch (e) {
    previewCandidates.error = e?.message || '加载候选失败'
  } finally {
    previewCandidates.loading = false
    previewCandidates.loadingMore = false
  }
}

const openImagePreview = async (post, m, idx = 0) => {
  if (!process.client) return
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
  previewCandidatesOpen.value = false
  resetPreviewCandidates()
  document.body.style.overflow = 'hidden'
  // Load the first page so we can show the candidate count in the header.
  await loadPreviewCandidates({ reset: true })
}

const closeImagePreview = () => {
  if (!process.client) return
  previewCtx.value = null
  previewCandidatesOpen.value = false
  resetPreviewCandidates()
  document.body.style.overflow = ''
}

const onMediaClick = (post, m, idx = 0) => {
  if (!process.client) return
  const mt = Number(m?.type || 0)

  // 视频点击逻辑
  if (mt === 6) {
    // Open a playable mp4 via backend (downloads+decrypts as needed).
    const remoteUrl = getSnsRemoteVideoSrc(post, m)
    if (remoteUrl) {
      window.open(remoteUrl, '_blank', 'noopener,noreferrer')
      return
    }

    // Last-resort: open raw CDN url.
    const u = String(m?.url || '').trim()
    if (u) window.open(u, '_blank', 'noopener,noreferrer')
    return
  }

  // 图片：打开预览
  void openImagePreview(post, m, idx)
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
        snsUserQuery.value = ''
        selectedSnsUser.value = ''
        snsUsers.value = []
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
