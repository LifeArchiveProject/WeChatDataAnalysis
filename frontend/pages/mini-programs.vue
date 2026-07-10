<template>
  <div class="records-page records-page--mini">
    <div class="records-page__scroll">
      <main class="records-page__frame">
        <header class="records-masthead">
          <div class="records-masthead__identity">
            <div class="records-masthead__title-group">
              <h1>小程序</h1>
              <span class="records-masthead__count">共<strong>{{ total }}</strong>个小程序</span>
            </div>
          </div>

          <div class="records-masthead__actions">
            <label class="records-search">
              <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
              <input
                v-model="keyword"
                type="search"
                aria-label="搜索小程序"
                placeholder="搜索小程序或入口标题"
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
            <button
              type="button"
              class="records-icon-button"
              :title="loading ? '正在刷新' : '刷新小程序'"
              :aria-label="loading ? '正在刷新' : '刷新小程序'"
              :disabled="loading"
              @click="loadItems({ force: true })"
            >
              <i class="fa-solid fa-arrow-rotate-right" :class="{ 'fa-spin': loading }" aria-hidden="true"></i>
            </button>
          </div>
        </header>

        <section class="records-body" aria-label="小程序列表">
          <div class="mini-index-heading">
            <div class="records-section-title">全部小程序</div>
            <div class="records-section-meta">已显示 {{ items.length }} 个</div>
          </div>

          <div v-if="loading && !items.length" class="records-state records-state--loading" role="status" aria-live="polite">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-arrow-rotate-right fa-spin"></i></span>
              <div class="records-state__title">正在加载小程序</div>
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
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-cube"></i></span>
              <div class="records-state__title">暂无小程序记录</div>
              <div class="records-state__text">当前账号下没有匹配的小程序数据</div>
            </div>
          </div>
          <div v-else class="mini-index">
            <article v-for="(item, index) in items" :key="item.userName || index" class="mini-entry">
              <div class="mini-entry__icon">
                <img
                  v-if="item.brandIconUrl && !iconBroken[miniIconKey(item)]"
                  :src="item.brandIconUrl"
                  :alt="`${displayTitle(item)}图标`"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                  @error="markMiniIconBroken(item)"
                />
                <i v-else class="fa-solid fa-cube" aria-hidden="true"></i>
              </div>
              <div class="mini-entry__content" :class="{ 'privacy-blur': privacyMode }">
                <div class="mini-entry__head">
                  <div class="mini-entry__title">{{ displayTitle(item) }}</div>
                  <time class="mini-entry__time">{{ item.lastUpdateText || '时间未记录' }}</time>
                </div>
                <p v-if="registerSummary(item)" class="mini-entry__summary">{{ registerSummary(item) }}</p>
                <div v-if="categoryTags(item).length || secondaryTitles(item).length" class="mini-entry__meta">
                  <div v-if="categoryTags(item).length" class="mini-entry__meta-line">
                    <i class="fa-solid fa-tag" aria-hidden="true"></i>
                    <span>{{ categoryTags(item).join(' · ') }}</span>
                  </div>
                  <div v-if="secondaryTitles(item).length" class="mini-entry__meta-line mini-entry__meta-line--plain">
                    <span>{{ secondaryTitles(item).join(' · ') }}</span>
                  </div>
                </div>
              </div>
            </article>
          </div>

          <button v-if="hasMore" type="button" class="records-more" :disabled="loading" @click="loadItems({ append: true })">
            <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
            <span>{{ loading ? '正在载入' : `继续载入 ${items.length} / ${total}` }}</span>
          </button>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

useHead({ title: '小程序 - 微信数据分析助手' })

const api = useApi()
const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)
const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const keyword = ref('')
const items = ref([])
const total = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
const PAGE_SIZE = 80
let requestId = 0
let keywordTimer = null
const iconBroken = reactive({})

const entryTitles = (item) => {
  const titles = Array.isArray(item?.titles) ? item.titles : []
  const fromSummary = [
    ...(Array.isArray(item?.summary?.bindEntries) ? item.summary.bindEntries : []),
    ...(Array.isArray(item?.summary?.wxaEntries) ? item.summary.wxaEntries : []),
  ].map((entry) => entry?.title).filter(Boolean)
  return [...new Set([...titles, ...fromSummary].map((x) => String(x || '').trim()).filter(Boolean))]
}

const displayTitle = (item) => {
  const title = entryTitles(item)[0]
  if (title) return title
  const registerBody = String(item?.summary?.registerBody || '').trim()
  return registerBody || '未命名小程序'
}

const secondaryTitles = (item) => {
  const primary = displayTitle(item)
  return entryTitles(item).filter((title) => title !== primary)
}

const registerSummary = (item) => {
  const text = String(item?.summary?.registerBody || '').trim()
  return text && text !== displayTitle(item) ? text : ''
}

const categoryTags = (item) => {
  const rows = Array.isArray(item?.summary?.categories) ? item.summary.categories : []
  return rows
    .map((row) => {
      if (typeof row === 'string') return row
      const first = String(row?.first || '').trim()
      const second = String(row?.second || '').trim()
      return [first, second].filter(Boolean).join(' / ')
    })
    .map((x) => String(x || '').trim())
    .filter(Boolean)
}

const miniIconKey = (item) => `${selectedAccount.value || ''}::${item?.userName || item?.brandIconUrl || ''}`

const markMiniIconBroken = (item) => {
  const key = miniIconKey(item)
  if (key) iconBroken[key] = true
}

const resetItems = () => {
  items.value = []
  total.value = 0
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
    const resp = await api.listMiniPrograms({
      account: selectedAccount.value,
      q: keyword.value || '',
      limit: PAGE_SIZE,
      offset: append ? items.value.length : 0,
    })
    if (rid !== requestId) return
    const next = Array.isArray(resp?.items) ? resp.items : []
    items.value = append ? [...items.value, ...next] : next
    total.value = Number(resp?.total || 0)
    hasMore.value = !!resp?.hasMore
  } catch (e) {
    if (rid === requestId) {
      if (!append) items.value = []
      total.value = append ? total.value : 0
      hasMore.value = false
      error.value = e?.message || '加载小程序数据失败'
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
