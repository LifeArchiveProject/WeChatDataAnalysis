<template>
  <div class="records-page records-page--finder">
    <div class="records-page__scroll">
      <main class="records-page__frame">
        <header class="records-masthead">
          <div class="records-masthead__identity">
            <div class="records-masthead__title-group">
              <h1>视频号直播</h1>
              <span class="records-masthead__count">共<strong>{{ total }}</strong>条直播记录</span>
            </div>
          </div>

          <div class="records-masthead__actions">
            <label class="records-search">
              <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
              <input
                v-model="keyword"
                type="search"
                aria-label="搜索视频号直播"
                placeholder="搜索视频号或直播编号"
                autocomplete="off"
              />
              <button
                v-if="keyword"
                type="button"
                class="records-search__clear"
                title="清空搜索"
                aria-label="清空搜索"
                @click="keyword = ''"
              >
                <i class="fa-solid fa-xmark" aria-hidden="true"></i>
              </button>
            </label>
            <button type="button" class="records-icon-button" title="导出视频号直播" aria-label="导出视频号直播" @click="exportDialogOpen = true">
              <i class="fa-solid fa-file-export" aria-hidden="true"></i>
            </button>
            <button
              type="button"
              class="records-icon-button"
              :title="loading ? '正在刷新' : '刷新直播记录'"
              :aria-label="loading ? '正在刷新' : '刷新直播记录'"
              :disabled="loading"
              @click="loadItems({ force: true })"
            >
              <i class="fa-solid fa-arrow-rotate-right" :class="{ 'fa-spin': loading }" aria-hidden="true"></i>
            </button>
          </div>
        </header>

        <section class="records-body" aria-label="视频号直播列表">
          <div class="finder-overview">
            <div class="finder-overview__heading">
              <div class="records-section-title">全部直播</div>
              <div class="records-section-meta">已显示 {{ items.length }} 条</div>
            </div>
            <dl class="finder-metrics">
              <div class="finder-metric">
                <dt>直播中</dt>
                <dd>{{ visibleLiveTotal }}</dd>
              </div>
              <div class="finder-metric">
                <dt>可回放</dt>
                <dd>{{ visibleReplayTotal }}</dd>
              </div>
              <div class="finder-metric">
                <dt>可直接打开</dt>
                <dd>{{ openableTotal }}</dd>
              </div>
            </dl>
          </div>

          <div v-if="loading && !items.length" class="records-state records-state--loading" role="status" aria-live="polite">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-arrow-rotate-right fa-spin"></i></span>
              <div class="records-state__title">正在加载直播记录</div>
              <div class="records-state__text">请稍候</div>
            </div>
          </div>
          <div v-else-if="error" class="records-state records-state--error" role="alert">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-triangle-exclamation"></i></span>
              <div class="records-state__title">加载失败</div>
              <div class="records-state__text">{{ error }}</div>
            </div>
          </div>
          <div v-else-if="!items.length" class="records-state">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-video"></i></span>
              <div class="records-state__title">暂无直播记录</div>
              <div class="records-state__text">当前账号下没有匹配的视频号直播记录</div>
            </div>
          </div>
          <div v-else class="finder-film">
            <article
              v-for="item in items"
              :key="recordKey(item)"
              class="finder-entry"
              :class="{ 'finder-entry--openable': !!liveJumpUrl(item) }"
              :title="liveJumpUrl(item) ? `打开${recordTitle(item)}的直播页面` : `${liveStatusText(item) || '直播状态未记录'}，没有可打开的链接`"
              :role="liveJumpUrl(item) ? 'link' : undefined"
              :tabindex="liveJumpUrl(item) ? 0 : undefined"
              @click="openLive(item)"
              @keydown.enter="openLive(item)"
              @keydown.space.prevent="openLive(item)"
            >
              <div class="finder-entry__visual" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="finderVisualUrl(item) && !visualBroken[finderVisualKey(item)]"
                  :src="finderVisualUrl(item)"
                  :alt="`${recordTitle(item)}图片`"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                  @error="markFinderVisualBroken(item)"
                />
                <i v-else class="fa-solid fa-video" aria-hidden="true"></i>
              </div>
              <div class="finder-entry__content" :class="{ 'privacy-blur': privacyMode }">
                <div class="finder-entry__title-row">
                  <div class="finder-entry__title" :title="recordRawTitle(item)">{{ recordTitle(item) }}</div>
                  <span v-if="isPaidLive(item)" class="finder-entry__paid">付费</span>
                </div>
                <p class="finder-entry__description">{{ recordSubtitle(item) || '直播简介未记录' }}</p>
                <div class="finder-entry__meta">
                  <i class="fa-solid fa-hashtag" aria-hidden="true"></i>
                  <span>{{ recordIdentifier(item) }}</span>
                </div>
              </div>
              <div class="finder-entry__status" :class="`finder-entry__status--${liveStatusTone(item)}`">
                {{ liveStatusText(item) || '状态未记录' }}
              </div>
              <a
                v-if="liveJumpUrl(item)"
                class="finder-entry__action"
                :href="liveJumpUrl(item)"
                target="_blank"
                rel="noreferrer"
                title="打开直播页面"
                aria-label="打开直播页面"
                @click.stop
              >
                <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>
              </a>
              <span v-else class="finder-entry__unavailable" title="没有可打开的直播链接" aria-label="没有可打开的直播链接">
                <i class="fa-solid fa-link-slash" aria-hidden="true"></i>
              </span>
            </article>
          </div>

          <button v-if="hasMore" type="button" class="records-more" :disabled="loading" @click="loadItems({ append: true })">
            <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
            <span>{{ loading ? '正在载入' : `继续载入 ${items.length} / ${total}` }}</span>
          </button>
        </section>
      </main>
    </div>
    <RecordExportDialog
      :open="exportDialogOpen"
      dataset="finder"
      title="视频号直播"
      :account="selectedAccount || ''"
      :query="keyword"
      :type-options="finderExportTypes"
      @close="exportDialogOpen = false"
    />
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

useHead({ title: '视频号直播 - 微信数据分析助手' })

const api = useApi()
const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)
const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const keyword = ref('')
const items = ref([])
const total = ref(0)
const openableTotal = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
const exportDialogOpen = ref(false)
const finderExportTypes = [
  { value: 'live', label: '直播记录', icon: 'fa-tower-broadcast' },
]
const PAGE_SIZE = 80
let requestId = 0
let keywordTimer = null
const visualBroken = reactive({})

const visibleLiveTotal = computed(() => items.value.filter((item) => Number(item?.liveStatus) === 1).length)
const visibleReplayTotal = computed(() => items.value.filter((item) => Number(item?.liveStatus) === 2 && Number(item?.replayStatus) === 1).length)

const recordKey = (item) => `live-${item.finderLiveId}-${item.finderUsername || item.finderExportId || ''}`

const recordContact = (item) => {
  return item?.contact && typeof item.contact === 'object' ? item.contact : null
}

const looksLikeRawId = (value) => {
  const text = String(value || '').trim()
  return !!(
    text.startsWith('wxid_')
    || text.startsWith('v2_')
    || text.endsWith('@finder')
    || text.endsWith('@chatroom')
    || /^\d{5,}@chatroom$/i.test(text)
  )
}

const identityDisplayName = (contact, fallback = '未知视频号') => {
  const c = contact && typeof contact === 'object' ? contact : {}
  const rawUsername = String(c.username || '').trim()
  for (const value of [c.displayName, c.name, c.nickname, c.remark]) {
    const text = String(value || '').trim()
    if (text && text !== rawUsername && !looksLikeRawId(text)) return text
  }
  const fb = String(fallback || '').trim()
  return fb && !looksLikeRawId(fb) ? fb : '未知视频号'
}

const identityAvatar = (contact) => String(contact?.avatar || contact?.avatarUrl || '').trim()

const liveJumpUrl = (item) => String(item?.liveUrl || item?.jumpUrl || '').trim()

const openLive = (item) => {
  const url = liveJumpUrl(item)
  if (!url || !process.client || typeof window === 'undefined') return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const recordTitle = (item) => identityDisplayName(recordContact(item), item.finderUsername || '未知视频号')

const recordRawTitle = (item) => {
  const raw = item.finderUsername || item.finderExportId || ''
  return raw ? `${recordTitle(item)} · ${raw}` : recordTitle(item)
}

const liveStatusText = (item) => {
  if (Number(item?.liveStatus) === 1) return '直播中'
  if (Number(item?.liveStatus) === 2) {
    return Number(item?.replayStatus) === 1 ? '回放' : '已结束'
  }
  return ''
}

const liveStatusTone = (item) => {
  if (Number(item?.liveStatus) === 1) return 'live'
  if (Number(item?.replayStatus) === 1) return 'replay'
  return 'ended'
}

const isKnownLiveRecord = (item) => {
  return [1, 2].includes(Number(item?.liveStatus))
}

const isPaidLive = (item) => Number(item?.chargeFlag || 0) > 0

const recordSubtitle = (item) => {
  const desc = String(item?.description || item?.liveInfo?.desc || item?.contact?.description || '').trim()
  if (desc) return desc
  if (liveJumpUrl(item)) return '已保存直播页面'
  return liveStatusText(item) || ''
}

const recordIdentifier = (item) => {
  const value = String(item?.finderLiveId || item?.liveInfo?.objectId || '').trim()
  return value ? `直播编号 ${value}` : '直播编号未记录'
}

const finderVisualUrl = (item) => {
  return String(identityAvatar(recordContact(item)) || item?.coverUrl || item?.liveInfo?.coverUrl || '').trim()
}

const finderVisualKey = (item) => `${selectedAccount.value || ''}::${recordKey(item)}::${finderVisualUrl(item)}`

const markFinderVisualBroken = (item) => {
  const key = finderVisualKey(item)
  if (key) visualBroken[key] = true
}

const resetItems = () => {
  items.value = []
  total.value = 0
  openableTotal.value = 0
  hasMore.value = false
  error.value = ''
}

const loadItems = async (options = {}) => {
  await chatAccounts.ensureLoaded()
  if (!selectedAccount.value) {
    requestId += 1
    resetItems()
    error.value = '未找到可用账号，先完成检测或导入。'
    return
  }

  const append = !!options.append
  const rid = ++requestId
  loading.value = true
  error.value = ''
  try {
    const resp = await api.listFinderRecords({
      account: selectedAccount.value,
      q: keyword.value || '',
      limit: PAGE_SIZE,
      offset: append ? items.value.length : 0,
    })
    if (rid !== requestId) return
    const next = Array.isArray(resp?.items) ? resp.items.filter(isKnownLiveRecord) : []
    items.value = append ? [...items.value, ...next] : next
    total.value = Number(resp?.total || 0)
    openableTotal.value = Number(resp?.openableTotal || 0)
    hasMore.value = !!resp?.hasMore
  } catch (e) {
    if (rid === requestId) {
      if (!append) resetItems()
      error.value = e?.message || '加载视频号数据失败'
    }
  } finally {
    if (rid === requestId) loading.value = false
  }
}

watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => { void loadItems() }, 250)
})

watch(() => selectedAccount.value, () => { void loadItems() })

onMounted(async () => {
  privacyStore.init()
  await chatAccounts.ensureLoaded()
  await loadItems()
})

onBeforeUnmount(() => {
  if (keywordTimer) clearTimeout(keywordTimer)
})
</script>
