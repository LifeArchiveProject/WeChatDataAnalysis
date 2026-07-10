<template>
  <div class="records-page records-page--payments">
    <div class="records-page__scroll">
      <main class="records-page__frame">
        <header class="records-masthead">
          <div class="records-masthead__identity">
            <div class="records-masthead__title-group">
              <h1>转账与红包</h1>
              <span class="records-masthead__count">共<strong>{{ total }}</strong>笔记录</span>
            </div>
          </div>

          <div class="records-masthead__actions">
            <label class="records-search">
              <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
              <input
                v-model="keyword"
                type="search"
                aria-label="搜索转账和红包记录"
                placeholder="搜索会话、付款方或收款方"
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
              :title="loading ? '正在刷新' : '刷新转账记录'"
              :aria-label="loading ? '正在刷新' : '刷新转账记录'"
              :disabled="loading"
              @click="loadItems({ force: true })"
            >
              <i class="fa-solid fa-arrow-rotate-right" :class="{ 'fa-spin': loading }" aria-hidden="true"></i>
            </button>
          </div>
        </header>

        <section class="records-body" aria-label="转账与红包列表">
          <div class="payments-toolbar">
            <div class="payments-filter" role="group" aria-label="记录类型">
              <button
                v-for="option in kindOptions"
                :key="option.value"
                type="button"
                :class="{ 'is-active': kindFilter === option.value }"
                :aria-pressed="kindFilter === option.value"
                @click="kindFilter = option.value"
              >
                <i :class="['fa-solid', option.icon]" aria-hidden="true"></i>
                <span>{{ option.label }}</span>
              </button>
            </div>

            <dl class="payments-stats">
              <div class="payments-stat">
                <dt>转账</dt>
                <dd>{{ Number(stats.transferCount || 0) }}</dd>
              </div>
              <div class="payments-stat">
                <dt>红包</dt>
                <dd>{{ Number(stats.redPacketCount || 0) }}</dd>
              </div>
              <div class="payments-stat">
                <dt>当前载入</dt>
                <dd>{{ items.length }}</dd>
              </div>
            </dl>
          </div>

          <div v-if="loading && !items.length" class="records-state records-state--loading" role="status" aria-live="polite">
            <div class="records-state__inner">
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-arrow-rotate-right fa-spin"></i></span>
              <div class="records-state__title">正在加载转账记录</div>
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
              <span class="records-state__icon" aria-hidden="true"><i class="fa-solid fa-wallet"></i></span>
              <div class="records-state__title">暂无转账记录</div>
              <div class="records-state__text">当前账号下没有匹配的转账或红包数据</div>
            </div>
          </div>
          <div v-else class="ledger">
            <article
              v-for="item in items"
              :key="recordKey(item)"
              class="ledger-row"
              :class="{ 'ledger-row--disabled': !chatUsername(item) }"
              :role="chatUsername(item) ? 'link' : undefined"
              :tabindex="chatUsername(item) ? 0 : undefined"
              :title="chatUsername(item) ? `打开${recordTitle(item)}的会话` : '该记录没有可打开的会话'"
              @click="openChatByUsername(chatUsername(item))"
              @keydown.enter="openChatByUsername(chatUsername(item))"
              @keydown.space.prevent="openChatByUsername(chatUsername(item))"
            >
              <div class="ledger-row__avatar" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="identityAvatar(recordContact(item)) && !avatarBroken[avatarBrokenKey(recordContact(item), recordKey(item))]"
                  :src="identityAvatar(recordContact(item))"
                  :alt="`${recordTitle(item)}头像`"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                  @error="markAvatarBroken(recordContact(item), recordKey(item))"
                />
                <div v-else class="ledger-row__avatar-fallback">
                  {{ identityFallback(recordTitle(item), recordContact(item)?.isGroup) }}
                </div>
              </div>

              <div class="ledger-row__content" :class="{ 'privacy-blur': privacyMode }">
                <div class="ledger-row__head">
                  <div class="ledger-row__title" :title="recordRawTitle(item)">{{ recordTitle(item) }}</div>
                </div>
                <div v-if="item.kind === 'transfer'" class="ledger-route">
                  <span class="ledger-route__item">
                    <span class="ledger-route__label">付款</span>{{ participantName(item.payerContact, item.payPayer, '未知付款方') }}
                  </span>
                  <i class="fa-solid fa-arrow-right-long" aria-hidden="true"></i>
                  <span class="ledger-route__item">
                    <span class="ledger-route__label">收款</span>{{ participantName(item.receiverContact, item.payReceiver, '未知收款方') }}
                  </span>
                </div>
                <div v-else class="ledger-route">
                  <span class="ledger-route__item">
                    <span class="ledger-route__label">发送</span>{{ participantName(item.senderContact, item.senderUserName, '未知发送人') }}
                  </span>
                </div>
                <div class="ledger-row__meta">
                  <time :datetime="recordDateTime(item)">
                    <i class="fa-regular fa-clock" aria-hidden="true"></i>{{ recordTimeText(item) }}
                  </time>
                  <span v-if="transferMemoText(item)">
                    <i class="fa-regular fa-note-sticky" aria-hidden="true"></i>{{ transferMemoText(item) }}
                  </span>
                  <template v-if="item.kind === 'redpacket'">
                    <span>红包类型 {{ numericFieldText(item.hbType) }}</span>
                    <span>领取状态 {{ numericFieldText(item.receiveStatus) }}</span>
                  </template>
                </div>
              </div>
              <div
                class="ledger-row__amount"
                :class="{
                  'ledger-row__amount--red': item.kind === 'redpacket' && hasParsedAmount(item),
                  'ledger-row__amount--muted': !hasParsedAmount(item),
                  'privacy-blur': privacyMode,
                }"
              >
                {{ recordAmountDisplay(item) }}
              </div>
              <span class="ledger-row__arrow" aria-hidden="true"><i class="fa-solid fa-chevron-right"></i></span>
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

useHead({ title: '转账与红包 - 微信数据分析助手' })

const api = useApi()
const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)
const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const kindOptions = [
  { label: '全部', value: 'all', icon: 'fa-list-ul' },
  { label: '转账', value: 'transfer', icon: 'fa-arrow-right-arrow-left' },
  { label: '红包', value: 'redpacket', icon: 'fa-envelope-open-text' },
]

const keyword = ref('')
const kindFilter = ref('all')
const items = ref([])
const total = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
const stats = ref({})
const PAGE_SIZE = 80
let requestId = 0
let keywordTimer = null
const avatarBroken = reactive({})

const recordKey = (item) => item.kind === 'transfer'
  ? `transfer-${item.transferId}-${item.messageServerId}`
  : `redpacket-${item.sendId}-${item.messageServerId}`

const recordContact = (item) => {
  return item?.sessionContact && typeof item.sessionContact === 'object' ? item.sessionContact : null
}

const looksLikeRawId = (value) => {
  const text = String(value || '').trim()
  return !!(text.startsWith('wxid_') || text.endsWith('@chatroom') || /^\d{5,}@chatroom$/i.test(text))
}

const identityDisplayName = (contact, fallback = '未知会话') => {
  const c = contact && typeof contact === 'object' ? contact : {}
  const rawUsername = String(c.username || '').trim()
  for (const value of [c.displayName, c.name, c.nickname, c.remark]) {
    const text = String(value || '').trim()
    if (text && text !== rawUsername && !looksLikeRawId(text)) return text
  }
  const fb = String(fallback || '').trim()
  if (fb && !looksLikeRawId(fb)) return fb
  return c.isGroup ? '未知群聊' : '未知会话'
}

const identityAvatar = (contact) => String(contact?.avatar || contact?.avatarUrl || '').trim()

const avatarBrokenKey = (contact, fallback = '') => {
  return `${selectedAccount.value || ''}::${contact?.username || fallback || ''}`
}

const markAvatarBroken = (contact, fallback = '') => {
  const key = avatarBrokenKey(contact, fallback)
  if (key) avatarBroken[key] = true
}

const identityFallback = (name, isGroup = false) => {
  if (isGroup) return '群'
  const text = String(name || '').trim()
  return text ? text.charAt(0) : '会'
}

const participantName = (contact, raw, fallback) => {
  return identityDisplayName(contact, raw || fallback)
}

const recordAmountText = (item) => {
  const value = String(item?.amountText || item?.amount || item?.message?.amountText || item?.message?.amount || '').trim()
  if (!value) return ''
  if (/^[¥￥]/.test(value)) return value.replace(/^￥/, '¥')
  return `¥${value}`
}

const redPacketAmountText = (item) => {
  const reason = String(item?.amountUnavailableReason || '').trim()
  if (reason) return '库中没有金额字段'
  return '金额未保存'
}

const hasParsedAmount = (item) => !!recordAmountText(item)

const recordAmountDisplay = (item) => {
  const amount = recordAmountText(item)
  if (amount) return amount
  return item?.kind === 'redpacket' ? redPacketAmountText(item) : '金额未解析'
}

const transferMemoText = (item) => {
  const value = String(item?.transferMemo || item?.message?.transferMemo || '').trim()
  if (!value) return ''
  if (value === '微信转账') return ''
  if (value === recordAmountText(item)) return ''
  return value
}

const chatUsername = (item) => String(item?.sessionName || item?.senderUserName || '').trim()

const openChatByUsername = (username) => {
  const u = String(username || '').trim()
  if (!u) return
  void navigateTo(`/chat/${encodeURIComponent(u)}`)
}

const recordTitle = (item) => item.kind === 'transfer'
  ? identityDisplayName(recordContact(item), item.sessionName || '未知会话')
  : identityDisplayName(recordContact(item), item.sessionName || item.senderUserName || '未知红包会话')

const recordRawTitle = (item) => {
  const raw = item.sessionName || item.senderUserName || ''
  return raw ? `${recordTitle(item)} · ${raw}` : recordTitle(item)
}

const numericFieldText = (value) => {
  if (value === null || value === undefined || value === '') return '未记录'
  return String(value)
}

const recordTimeText = (item) => {
  return String(item?.beginTransferTimeText || item?.lastUpdateTimeText || '').trim() || '时间未记录'
}

const recordDateTime = (item) => {
  const value = Number(item?.beginTransferTime || item?.lastUpdateTime || 0)
  if (!Number.isFinite(value) || value <= 0) return undefined
  try {
    return new Date(value * 1000).toISOString()
  } catch {
    return undefined
  }
}

const resetItems = () => {
  items.value = []
  total.value = 0
  hasMore.value = false
  stats.value = {}
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
    const resp = await api.listPaymentRecords({
      account: selectedAccount.value,
      q: keyword.value || '',
      kind: kindFilter.value,
      limit: PAGE_SIZE,
      offset: append ? items.value.length : 0,
    })
    if (rid !== requestId) return
    const next = Array.isArray(resp?.items) ? resp.items : []
    items.value = append ? [...items.value, ...next] : next
    total.value = Number(resp?.total || 0)
    hasMore.value = !!resp?.hasMore
    stats.value = resp?.stats || {}
  } catch (e) {
    if (rid === requestId) {
      if (!append) resetItems()
      error.value = e?.message || '加载转账与红包数据失败'
    }
  } finally {
    if (rid === requestId) loading.value = false
  }
}

watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => { void loadItems() }, 250)
})

watch(kindFilter, () => { void loadItems() })
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
