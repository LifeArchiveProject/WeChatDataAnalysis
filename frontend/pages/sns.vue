<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- 右侧朋友圈区域 -->
    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <div class="flex-1 overflow-auto min-h-0 bg-white" @scroll="onScroll">
	        <div class="max-w-2xl mx-auto px-4 py-4">
            <div class="relative w-full mb-12 -mt-4 bg-white">
              <div class="h-64 w-full bg-[#333333] relative overflow-hidden">
                <img
                    v-if="coverData && coverData.media && coverData.media.length > 0"
                    :src="getSnsMediaUrl(coverData, coverData.media[0], 0, coverData.media[0].url)"
                    class="w-full h-full object-cover"
                    alt="朋友圈封面"
                />
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

                <div v-if="post.type === 3" class="mt-2 max-w-[360px]" :class="{ 'privacy-blur': privacyMode }">
                  <a :href="post.contentUrl" target="_blank" class="block bg-gray-100 p-2 rounded-sm border border-gray-200 no-underline hover:bg-gray-200 transition-colors">
                    <div class="flex items-center gap-3">
                      <img
                          v-if="post.contentUrl && !hasArticleThumbError(post.id)"
                          :src="getArticleThumbProxyUrl(post.contentUrl)"
                          class="w-12 h-12 object-cover flex-shrink-0 bg-white"
                          alt=""
                          @error="onArticleThumbError(post.id)"
                      />
                      <div v-else class="w-12 h-12 flex items-center justify-center bg-gray-200 text-gray-400 flex-shrink-0 text-xs">
                        文章
                      </div>

                      <div class="flex-1 flex flex-col justify-between overflow-hidden h-12">
                        <div class="text-[13px] text-gray-900 leading-tight line-clamp-2">{{ post.title }}</div>
                      </div>
                    </div>
                    <div class="text-[11px] text-[#576b95] mt-1 pt-1 border-t border-gray-200/50">
                      公众号文章分享
                    </div>
                  </a>
                </div>

                <div v-else-if="post.type === 28 && post.finderFeed && Object.keys(post.finderFeed).length > 0" class="mt-2 max-w-[360px]" :class="{ 'privacy-blur': privacyMode }">
                  <div class="block bg-gray-100 p-2 rounded-sm border border-gray-200 no-underline hover:bg-gray-200 transition-colors">
                    <!-- 浏览器没有看微信视频号的环境，暂时不进行跳转！！-->
                    <div class="flex items-start gap-3">
                      <div class="relative w-14 h-16 flex-shrink-0 bg-black overflow-hidden rounded-sm">
                        <img
                            v-if="post.finderFeed.thumbUrl"
                            :src="getProxyExternalUrl(post.finderFeed.thumbUrl)"
                            class="w-full h-full object-cover opacity-80"
                            alt="finder cover"
                        />
                        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                          <svg class="w-5 h-5 text-white/90" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </div>
                      <div class="flex-1 flex flex-col overflow-hidden">
                        <div class="text-xs text-gray-500 truncate">{{ post.finderFeed.nickname }}</div>
                        <div class="text-[13px] text-gray-900 leading-tight line-clamp-2 mt-[2px]">{{ post.finderFeed.desc || post.title }}</div>
                      </div>
                    </div>
                    <div class="text-[11px] text-[#576b95] mt-1 pt-1 border-t border-gray-200/50">
                      视频号 · 动态
                    </div>
                  </div>
                </div>

                <div v-else-if="post.media && post.media.length > 0" class="mt-2" :class="{ 'privacy-blur': privacyMode }">
                  <div v-if="post.media.length === 1" class="max-w-[360px]">
                    <div
                        v-if="!hasMediaError(post.id, 0) && getMediaThumbSrc(post, post.media[0], 0)"
                        class="inline-block cursor-pointer relative"
                        @click.stop="onMediaClick(post, post.media[0], 0)"
                    >
                      <video
                          v-if="Number(post.media[0]?.type || 0) === 6"
                          :src="getSnsVideoUrl(post.id, post.media[0].id)"
                          :poster="getMediaThumbSrc(post, post.media[0], 0)"
                          class="rounded-sm max-h-[360px] max-w-full object-cover"
                          autoplay
                          loop
                          muted
                          playsinline
                          @loadeddata="onLocalVideoLoaded(post.id, post.media[0].id)"
                          @error="onLocalVideoError(post.id, post.media[0].id)"
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
                      <video
                          v-if="!hasMediaError(post.id, idx) && Number(m?.type || 0) === 6"
                          :src="getSnsVideoUrl(post.id, m.id)"
                          :poster="getMediaThumbSrc(post, m, idx)"
                          class="w-full h-full object-cover"
                          autoplay
                          loop
                          muted
                          playsinline
                          @loadeddata="onLocalVideoLoaded(post.id, m.id)"
                          @error="onLocalVideoError(post.id, m.id)"
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
	        <img :src="previewSrc" alt="预览" class="max-w-[90vw] max-h-[70vh] object-contain" />

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
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

useHead({ title: '朋友圈 - 微信数据分析助手' })

const api = useApi()

const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const posts = ref([])
const hasMore = ref(true)
const isLoading = ref(false)
const error = ref('')

const coverData = ref(null)

const pageSize = 20

const mediaBase = process.client ? 'http://localhost:8000' : ''

// Track failed images per-post, per-index to render placeholders instead of broken <img>.
const mediaErrors = ref({})

const mediaErrorKey = (postId, idx) => `${String(postId || '')}:${String(idx || 0)}`
const hasMediaError = (postId, idx) => !!mediaErrors.value[mediaErrorKey(postId, idx)]
const onMediaError = (postId, idx) => {
  mediaErrors.value[mediaErrorKey(postId, idx)] = true
}

const articleThumbErrors = ref({})

const hasArticleThumbError = (postId) => !!articleThumbErrors.value[postId]

const onArticleThumbError = (postId) => {
  articleThumbErrors.value[postId] = true
}

const selfInfo = ref({ wxid: '', nickname: '' })

const loadSelfInfo = async () => {
  if (!selectedAccount.value) return
  try {
    const resp = await $fetch(`${mediaBase}/api/sns/self_info?account=${encodeURIComponent(selectedAccount.value)}`)
    if (resp && resp.wxid) {
      selfInfo.value = resp
    }
  } catch (e) {
    console.error('获取个人信息失败', e)
  }
}

const getArticleThumbProxyUrl = (contentUrl) => {
  const u = String(contentUrl || '').trim()
  if (!u) return ''
  return `${mediaBase}/api/sns/article_thumb?url=${encodeURIComponent(u)}`
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


const getSnsVideoUrl = (postId, mediaId) => {
  // 本地缓存视频
  const acc = String(selectedAccount.value || '').trim()
  if (!acc || !postId || !mediaId) return ''
  return `${mediaBase}/api/sns/video?account=${encodeURIComponent(acc)}&post_id=${encodeURIComponent(postId)}&media_id=${encodeURIComponent(mediaId)}`
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

const onMediaClick = (post, m, idx = 0) => {
  if (!process.client) return
  const mt = Number(m?.type || 0)

  // 视频点击逻辑
  if (mt === 6) {
    // 1. 如果本地缓存加载成功，永远不请求 CDN！直接在新标签页打开本地的高清完整视频
    if (isLocalVideoLoaded(post.id, m.id)) {
      const localUrl = getSnsVideoUrl(post.id, m.id)
      window.open(localUrl, '_blank', 'noopener,noreferrer')
      return
    }

    // 2. 如果本地没有缓存，按原逻辑 fallback 到 CDN
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
    const offset = reset ? 0 : posts.value.length
    const resp = await api.listSnsTimeline({
      account: selectedAccount.value,
      limit: pageSize,
      offset
    })
    const items = resp?.timeline || []

    if (reset) {
      posts.value = items.filter(p => p.type !== 7)
      coverData.value = resp?.cover || null
    } else {
      posts.value = [...posts.value, ...items.filter(p => p.type !== 7)]
    }
    hasMore.value = !!resp?.hasMore
  } catch (e) {
    error.value = e?.message || '加载朋友圈失败'
  } finally {
    isLoading.value = false
  }
}


watch(
    () => selectedAccount.value,
    async (v, oldV) => {
      if (v && v !== oldV) {
        if (previewCtx.value) closeImagePreview()
        await loadSelfInfo()
        await loadPosts({ reset: true })
      }
    },
    { immediate: true }
)


onMounted(async () => {
  privacyStore.init()
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
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onGlobalKeyDown)
})

const getProxyExternalUrl = (url) => {
  // 目前难以计算enc，代理获取封面图（thumbnail）
  const u = String(url || '').trim()
  if (!u) return ''
  return `${mediaBase}/api/chat/media/proxy_image?url=${encodeURIComponent(u)}`
}


</script>
