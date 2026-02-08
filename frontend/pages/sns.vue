<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- 左侧边栏 -->
    <div class="border-r border-gray-200 flex flex-col" style="background-color: #e8e7e7; width: 60px; min-width: 60px; max-width: 60px">
      <div class="flex-1 flex flex-col justify-start pt-0 gap-0">
        <!-- 头像（类似微信侧边栏） -->
        <div class="w-full h-[60px] flex items-center justify-center">
          <div class="w-[40px] h-[40px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">
            <img v-if="selfAvatarUrl" :src="selfAvatarUrl" alt="avatar" class="w-full h-full object-cover" />
            <div
              v-else
              class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
              style="background-color: #4B5563"
            >
              我
            </div>
          </div>
        </div>

        <!-- 聊天图标 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="聊天"
          @click="goChat"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isChatRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path
                  d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z"
                />
              </svg>
            </div>
          </div>
        </div>

        <!-- 朋友圈图标（Aperture 风格） -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="朋友圈"
          @click="goSns"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isSnsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg
                class="w-full h-full"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="14.31" y1="8" x2="20.05" y2="17.94" />
                <line x1="9.69" y1="8" x2="21.17" y2="8" />
                <line x1="7.38" y1="12" x2="13.12" y2="2.06" />
                <line x1="9.69" y1="16" x2="3.95" y2="6.06" />
                <line x1="14.31" y1="16" x2="2.83" y2="16" />
                <line x1="16.62" y1="12" x2="10.88" y2="21.94" />
              </svg>
            </div>
          </div>
        </div>

        <!-- 联系人图标 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="联系人"
          @click="goContacts"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isContactsRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
                <circle cx="10" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
          </div>
        </div>

        <!-- 年度总结图标 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="年度总结"
          @click="goWrapped"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="isWrappedRoute ? 'text-[#07b75b]' : 'text-[#5d5d5d]'">
              <svg
                class="w-full h-full"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <rect x="4" y="4" width="16" height="16" rx="2" />
                <path d="M8 16v-5" />
                <path d="M12 16v-8" />
                <path d="M16 16v-3" />
              </svg>
            </div>
          </div>
        </div>

        <!-- 隐私模式按钮 -->
        <div
          class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          @click="privacyMode = !privacyMode"
          :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
        >
          <div
            class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent group-hover:bg-[#E1E1E1]"
          >
            <svg class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="privacyMode ? 'text-[#07b75b]' : 'text-[#5d5d5d]'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path v-if="privacyMode" stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
              <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧朋友圈区域 -->
    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <!-- 桌面端标题栏放在内容区（与聊天页一致） -->
      <DesktopTitleBar />

	      <div class="flex-1 overflow-auto min-h-0">
	        <div class="max-w-2xl mx-auto px-4 py-4">
	          <div v-if="error" class="text-sm text-red-500 whitespace-pre-wrap py-2">{{ error }}</div>
	          <div v-else-if="isLoading && posts.length === 0" class="text-sm text-gray-500 py-2">加载中…</div>
	          <div v-else-if="posts.length === 0" class="text-sm text-gray-500 py-2">暂无朋友圈数据</div>

	          <!-- 图片匹配提示（实验功能） -->
	          <div v-if="!error" class="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
	            <div class="font-medium">图片匹配（实验功能）</div>
	            <div class="mt-1 leading-5">
	              图片可能会出现错配或无法显示。点击图片进入预览，可在“候选匹配”中手动选择；你的选择会保存在本机并在下次优先使用。
	            </div>
	            <label class="mt-2 flex items-start gap-2 select-none">
	              <input v-model="snsAvoidOtherPicked" type="checkbox" class="mt-[2px]" />
	              <span class="leading-5">
	                自动匹配时，避开已被你手动指定到其他动态的图片（降低重复）
	              </span>
	            </label>
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
                  {{ post.contentDesc }}
                </div>

                <div v-if="post.media && post.media.length > 0" class="mt-2" :class="{ 'privacy-blur': privacyMode }">
                  <div v-if="post.media.length === 1" class="max-w-[360px]">
                    <div
                      v-if="!hasMediaError(post.id, 0) && getMediaThumbSrc(post, post.media[0], 0)"
                      class="inline-block cursor-pointer relative"
                      @click.stop="onMediaClick(post, post.media[0], 0)"
                    >
                      <img
                        :src="getMediaThumbSrc(post, post.media[0], 0)"
                        class="rounded-sm max-h-[360px] object-cover"
                        alt=""
                        loading="lazy"
                        referrerpolicy="no-referrer"
                        @error="onMediaError(post.id, 0)"
                      />
                      <div
                        v-if="Number(post.media[0]?.type || 0) === 6"
                        class="absolute inset-0 flex items-center justify-center pointer-events-none"
                      >
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </div>
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
                      class="w-[116px] h-[116px] rounded-[2px] overflow-hidden bg-gray-100 border border-gray-200 flex items-center justify-center cursor-pointer relative"
                      @click.stop="onMediaClick(post, m, idx)"
                    >
                      <img
                        v-if="!hasMediaError(post.id, idx) && getMediaThumbSrc(post, m, idx)"
                        :src="getMediaThumbSrc(post, m, idx)"
                        class="w-full h-full object-cover"
                        alt=""
                        loading="lazy"
                        referrerpolicy="no-referrer"
                        @error="onMediaError(post.id, idx)"
                      />
                      <span v-else class="text-[10px] text-gray-400">图片失败</span>

                      <!-- 视频缩略图的播放提示 -->
                      <div v-if="Number(m?.type || 0) === 6" class="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div class="w-10 h-10 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="post.location" class="mt-2 text-xs text-[#576b95] truncate" :class="{ 'privacy-blur': privacyMode }">
                  {{ post.location }}
                </div>

                <div class="mt-2 flex items-center justify-between">
                  <span class="text-xs text-gray-400" :class="{ 'privacy-blur': privacyMode }">{{ formatRelativeTime(post.createTime) }}</span>
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
	                      <span class="text-gray-900" :class="{ 'privacy-blur': privacyMode }">: {{ String(c?.content || '').trim() }}</span>
	                    </div>
	                  </div>
	                </div>
              </div>
            </div>
          </div>

          <div v-if="hasMore" class="py-2">
            <button
              type="button"
              class="w-full text-sm text-gray-600 py-2 rounded bg-white hover:bg-gray-50 border border-gray-200"
              :disabled="isLoading"
              @click="loadPosts({ reset: false })"
            >
              {{ isLoading ? '加载中…' : '加载更多' }}
            </button>
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
	        <img :src="previewSrc" alt="预览" class="max-w-[90vw] max-h-[70vh] object-contain" />

	        <!-- 候选匹配面板（仅在本地缓存匹配时有意义） -->
	        <div class="mt-3 w-full max-w-[90vw] rounded bg-black/35 text-white text-xs px-3 py-2">
	          <div class="flex items-center justify-between gap-2">
	            <div class="truncate">
	              候选匹配：
	              <span v-if="previewCandidates.loading">加载中…</span>
	              <span v-else-if="previewCandidates.count > 0">共 {{ previewCandidates.count }} 个</span>
	              <span v-else>未找到本地候选（可能仅能显示占位图）</span>
	              <span v-if="previewEffectiveIdx != null" class="ml-2 text-white/80">当前：#{{ Number(previewEffectiveIdx) + 1 }}</span>
	              <span v-if="previewHasUserOverride" class="ml-2 text-emerald-200">(已保存)</span>
	            </div>
	            <div class="flex items-center gap-2 flex-shrink-0">
	              <button
	                type="button"
	                class="px-2 py-1 rounded bg-white/10 hover:bg-white/20 transition-colors"
	                @click="toggleCandidatePanel"
	              >
	                {{ previewCandidatesOpen ? '收起' : '展开' }}
	              </button>
	              <button
	                v-if="previewHasUserOverride"
	                type="button"
	                class="px-2 py-1 rounded bg-white/10 hover:bg-white/20 transition-colors"
	                @click="clearUserOverrideForPreview"
	              >
	                恢复自动
	              </button>
	            </div>
	          </div>

	          <div v-if="previewCandidates.error" class="mt-2 text-red-200 whitespace-pre-wrap">
	            {{ previewCandidates.error }}
	          </div>

	          <div v-if="previewCandidatesOpen && previewCandidates.count > 0" class="mt-2">
	            <div class="flex gap-2 overflow-x-auto pb-1">
	              <button
	                v-for="cand in previewCandidates.items"
	                :key="cand.idx"
	                type="button"
	                class="flex-shrink-0 w-24"
	                @click="selectCandidateForPreview(cand.idx)"
	              >
	                <div class="w-24 h-24 rounded bg-black/20 overflow-hidden border border-white/10">
	                  <img :src="getPreviewCandidateSrc(cand.idx)" class="w-full h-full object-cover" alt="" />
	                </div>
	                <div class="mt-1 text-[11px] text-white/80">#{{ Number(cand.idx) + 1 }}</div>
	              </button>
	            </div>

	            <div v-if="previewCandidates.hasMore" class="mt-2">
	              <button
	                type="button"
	                class="px-2 py-1 rounded bg-white/10 hover:bg-white/20 transition-colors"
	                :disabled="previewCandidates.loadingMore"
	                @click="loadMorePreviewCandidates"
	              >
	                {{ previewCandidates.loadingMore ? '加载中…' : '加载更多候选' }}
	              </button>
	            </div>
	          </div>
	        </div>
	      </div>

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
useHead({ title: '朋友圈 - 微信数据分析助手' })

const route = useRoute()

const isChatRoute = computed(() => route.path?.startsWith('/chat'))
const isSnsRoute = computed(() => route.path?.startsWith('/sns'))
const isContactsRoute = computed(() => route.path?.startsWith('/contacts'))
const isWrappedRoute = computed(() => route.path?.startsWith('/wrapped'))

// 隐私模式（聊天/朋友圈共用本地开关）
const PRIVACY_MODE_KEY = 'ui.privacy_mode'
const privacyMode = ref(false)

onMounted(() => {
  if (!process.client) return
  try {
    privacyMode.value = localStorage.getItem(PRIVACY_MODE_KEY) === '1'
  } catch {}
})

watch(
  () => privacyMode.value,
  (v) => {
    if (!process.client) return
    try {
      localStorage.setItem(PRIVACY_MODE_KEY, v ? '1' : '0')
    } catch {}
  }
)

const api = useApi()
const selectedAccount = ref(null)
const availableAccounts = ref([])

const posts = ref([])
const hasMore = ref(true)
const isLoading = ref(false)
const error = ref('')

const pageSize = 20

const mediaBase = process.client ? 'http://localhost:8000' : ''

// User overrides for SNS image matching (account-local, stored in localStorage).
const SNS_MEDIA_OVERRIDE_PREFIX = 'sns_media_override:v1:'
const SNS_MEDIA_OVERRIDE_REV_PREFIX = 'sns_media_override_rev:v1:'
const snsMediaOverrides = ref({})
const snsMediaOverrideRev = ref('0')

const snsOverrideStorageKey = (account) => `${SNS_MEDIA_OVERRIDE_PREFIX}${String(account || '').trim()}`
const snsOverrideRevStorageKey = (account) => `${SNS_MEDIA_OVERRIDE_REV_PREFIX}${String(account || '').trim()}`
const snsOverrideMediaKey = (postId, idx) => `${String(postId || '')}:${String(Number(idx) || 0)}`

const loadSnsMediaOverrides = () => {
  if (!process.client) return
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) {
    snsMediaOverrides.value = {}
    snsMediaOverrideRev.value = '0'
    return
  }
  try {
    const raw = localStorage.getItem(snsOverrideStorageKey(acc))
    const parsed = raw ? JSON.parse(raw) : {}
    snsMediaOverrides.value = parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    snsMediaOverrides.value = {}
  }
  try {
    const rev = localStorage.getItem(snsOverrideRevStorageKey(acc))
    snsMediaOverrideRev.value = String(rev || '0')
  } catch {
    snsMediaOverrideRev.value = '0'
  }
}

const saveSnsMediaOverrides = () => {
  if (!process.client) return
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return
  try {
    localStorage.setItem(snsOverrideStorageKey(acc), JSON.stringify(snsMediaOverrides.value || {}))
  } catch {}
  try {
    localStorage.setItem(snsOverrideRevStorageKey(acc), String(snsMediaOverrideRev.value || '0'))
  } catch {}
}

// Settings: avoid auto-using an image that was manually pinned to another SNS post.
const SNS_SNS_SETTINGS_PREFIX = 'sns_settings:v1:'
const snsAvoidOtherPicked = ref(true)
const snsAvoidOtherPickedStorageKey = (account) => `${SNS_SNS_SETTINGS_PREFIX}${String(account || '').trim()}:avoid_other_picked`

const loadSnsSettings = () => {
  if (!process.client) return
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return
  try {
    const raw = localStorage.getItem(snsAvoidOtherPickedStorageKey(acc))
    if (raw == null || raw === '') return
    snsAvoidOtherPicked.value = raw === '1' || raw === 'true'
  } catch {}
}

const saveSnsSettings = () => {
  if (!process.client) return
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return
  try {
    localStorage.setItem(snsAvoidOtherPickedStorageKey(acc), snsAvoidOtherPicked.value ? '1' : '0')
  } catch {}
}

const syncSnsMediaPicksToBackend = async () => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return
  try {
    await api.saveSnsMediaPicks({ account: acc, picks: snsMediaOverrides.value || {} })
  } catch {}
}

const getSnsMediaOverridePick = (postId, idx) => {
  const key = snsOverrideMediaKey(postId, idx)
  const v = snsMediaOverrides.value?.[key]
  return String(v || '').trim()
}

const setSnsMediaOverridePick = (postId, idx, pick) => {
  if (!process.client) return
  const key = snsOverrideMediaKey(postId, idx)
  const v = String(pick || '').trim()
  if (!v) {
    if (snsMediaOverrides.value && Object.prototype.hasOwnProperty.call(snsMediaOverrides.value, key)) {
      delete snsMediaOverrides.value[key]
    }
  } else {
    snsMediaOverrides.value[key] = v
  }
  saveSnsMediaOverrides()
  // Keep backend in sync so it can apply duplicate-avoidance logic.
  // Then bump `pv` so other auto-matched images reload using the updated picks.
  void syncSnsMediaPicksToBackend().finally(() => {
    snsMediaOverrideRev.value = String(Date.now())
    saveSnsMediaOverrides()
  })
}

// Track failed images per-post, per-index to render placeholders instead of broken <img>.
const mediaErrors = ref({})

const mediaErrorKey = (postId, idx) => `${String(postId || '')}:${String(idx || 0)}`
const hasMediaError = (postId, idx) => !!mediaErrors.value[mediaErrorKey(postId, idx)]
const onMediaError = (postId, idx) => {
  mediaErrors.value[mediaErrorKey(postId, idx)] = true
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

const selfAvatarUrl = computed(() => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return ''
  return `${mediaBase}/api/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(acc)}`
})

const postAvatarUrl = (username) => {
  const acc = String(selectedAccount.value || '').trim()
  const u = String(username || '').trim()
  if (!acc || !u) return ''
  return `${mediaBase}/api/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(u)}`
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
      return `${mediaBase}/api/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
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
    if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn') || host.endsWith('.tc.qq.com')) {
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

  // If backend already provides a local media endpoint, keep it as-is.
  if (rawLower.startsWith('/api/') || rawLower.startsWith('blob:') || rawLower.startsWith('data:')) return raw

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
        const pick = getSnsMediaOverridePick(post?.id, idx)
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
        if (pick) parts.set('pick', pick)
        if (!pick && snsAvoidOtherPicked.value) {
          const pid = String(post?.id || '').trim()
          if (pid) parts.set('post_id', pid)
          parts.set('avoid_picked', '1')
          parts.set('pv', String(snsMediaOverrideRev.value || '0'))
        }
        if (md5) parts.set('md5', md5)
        // Bump this when changing backend matching logic to avoid stale cached wrong images.
        parts.set('v', '7')
        parts.set('url', raw)
        return `${mediaBase}/api/sns/media?${parts.toString()}`
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

const previewHasUserOverride = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return false
  return !!getSnsMediaOverridePick(ctx.post?.id, ctx.idx)
})

const previewEffectiveIdx = computed(() => {
  const ctx = previewCtx.value
  if (!ctx) return null
  const pick = getSnsMediaOverridePick(ctx.post?.id, ctx.idx)
  if (pick) {
    const found = (previewCandidates.items || []).find((c) => String(c?.key || '') === pick)
    if (found) return Number(found.idx)
    return null
  }
  const baseIdx = mediaSizeGroupIndex(ctx.post, ctx.media, ctx.idx)
  if (!snsAvoidOtherPicked.value) return baseIdx
  const curPid = String(ctx.post?.id || '').trim()
  if (!curPid) return baseIdx

  // Mirror backend logic: skip candidates that were manually pinned to other posts.
  const reserved = new Set()
  try {
    for (const [k, v] of Object.entries(snsMediaOverrides.value || {})) {
      const pid = String(k || '').split(':', 1)[0].trim()
      if (!pid || pid === curPid) continue
      const key = String(v || '').trim()
      if (key) reserved.add(key)
    }
  } catch {}

  const items = Array.isArray(previewCandidates.items) ? [...previewCandidates.items] : []
  items.sort((a, b) => Number(a?.idx || 0) - Number(b?.idx || 0))
  for (const c of items) {
    const i = Number(c?.idx)
    const key = String(c?.key || '').trim()
    if (!Number.isFinite(i) || i < baseIdx) continue
    if (!key) continue
    if (!reserved.has(key)) return i
  }
  return baseIdx
})

const toggleCandidatePanel = () => {
  previewCandidatesOpen.value = !previewCandidatesOpen.value
}

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

const getPreviewCandidateSrc = (candIdx) => {
  const ctx = previewCtx.value
  const acc = String(selectedAccount.value || '').trim()
  if (!ctx || !acc) return ''

  const idxNum = Number(candIdx)
  const cand = (previewCandidates.items || []).find((c) => Number(c?.idx) === idxNum)
  const key = String(cand?.key || '').trim()
  if (!key) return ''

  const parts = new URLSearchParams()
  parts.set('account', acc)
  parts.set('pick', key)
  const ct = String(ctx.post?.createTime || '').trim()
  if (ct) parts.set('create_time', ct)
  parts.set('v', '7')
  return `${mediaBase}/api/sns/media?${parts.toString()}`
}

const selectCandidateForPreview = (candIdx) => {
  const ctx = previewCtx.value
  if (!ctx) return
  const idxNum = Number(candIdx)
  const cand = (previewCandidates.items || []).find((c) => Number(c?.idx) === idxNum)
  const key = String(cand?.key || '').trim()
  if (!key) return
  setSnsMediaOverridePick(ctx.post?.id, ctx.idx, key)
  // Allow <img> to retry after user switches candidates.
  try {
    delete mediaErrors.value[mediaErrorKey(ctx.post?.id, ctx.idx)]
  } catch {}
}

const clearUserOverrideForPreview = () => {
  const ctx = previewCtx.value
  if (!ctx) return
  setSnsMediaOverridePick(ctx.post?.id, ctx.idx, '')
  try {
    delete mediaErrors.value[mediaErrorKey(ctx.post?.id, ctx.idx)]
  } catch {}
}

const loadMorePreviewCandidates = async () => {
  if (previewCandidates.loading || previewCandidates.loadingMore) return
  if (!previewCandidates.hasMore) return
  await loadPreviewCandidates({ reset: false })
}

const onMediaClick = (post, m, idx = 0) => {
  if (!process.client) return
  const mt = Number(m?.type || 0)
  // 视频：打开视频链接（新窗口），图片：打开预览
  if (mt === 6) {
    const u = String(m?.url || '').trim()
     if (u) window.open(u, '_blank', 'noopener,noreferrer')
     return
   }
  // Open preview overlay; it also loads local candidates for manual selection.
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
  try {
    const resp = await api.listChatAccounts()
    const accounts = resp?.accounts || []
    availableAccounts.value = accounts
    selectedAccount.value = selectedAccount.value || resp?.default_account || accounts[0] || null
  } catch (e) {
    error.value = e?.message || '加载账号失败'
    availableAccounts.value = []
    selectedAccount.value = null
  }
}

const loadPosts = async ({ reset }) => {
  if (!selectedAccount.value) return
  if (isLoading.value) return
  error.value = ''
  isLoading.value = true
  try {
    const offset = reset ? 0 : posts.value.length
    const resp = await api.listSnsTimeline({
      account: selectedAccount.value,
      limit: pageSize,
      offset
    })
    const items = resp?.timeline || []
    if (reset) {
      posts.value = items
    } else {
      posts.value = [...posts.value, ...items]
    }
    hasMore.value = !!resp?.hasMore
  } catch (e) {
    error.value = e?.message || '加载朋友圈失败'
  } finally {
    isLoading.value = false
  }
}

const goChat = async () => {
  await navigateTo('/chat')
}

const goSns = async () => {
  await navigateTo('/sns')
}

const goContacts = async () => {
  await navigateTo('/contacts')
}

const goWrapped = async () => {
  await navigateTo('/wrapped')
}

watch(
  () => selectedAccount.value,
  async (v, oldV) => {
    if (v && v !== oldV) {
      // Account switch: reload overrides and reset preview state.
      loadSnsMediaOverrides()
      loadSnsSettings()
      void syncSnsMediaPicksToBackend()
      if (previewCtx.value) closeImagePreview()
      await loadPosts({ reset: true })
    } else if (!v) {
      snsMediaOverrides.value = {}
    }
  }
)

watch(
  () => snsAvoidOtherPicked.value,
  () => {
    saveSnsSettings()
  }
)

onMounted(async () => {
  await loadAccounts()
  loadSnsMediaOverrides()
  loadSnsSettings()
  void syncSnsMediaPicksToBackend()
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
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onGlobalKeyDown)
})
</script>

<style scoped>
/* 隐私模式模糊效果 */
.privacy-blur {
  filter: blur(9px);
  transition: filter 0.2s ease;
}

.privacy-blur:hover {
  filter: none;
}
</style>
