<template>
    <div
      class="session-list-panel border-r flex flex-col min-h-0 shrink-0 relative"
      :style="{ '--session-list-width': sessionListWidth + 'px' }"
    >
      <!-- 拖动调整会话列表宽度 -->
      <div
        class="session-list-resizer"
        :class="{ 'session-list-resizer-active': sessionListResizing }"
        title="拖动调整会话列表宽度"
        @pointerdown="onSessionListResizerPointerDown"
        @dblclick="resetSessionListWidth"
      />
      <!-- 聊天列表 -->
      <div class="h-full flex flex-col min-h-0">
        <!-- 搜索栏 -->
        <div class="session-list-search p-3 border-b">
          <div class="flex items-center gap-2">
            <div ref="searchInputWrapperRef" class="contact-search-wrapper flex-1">
              <svg class="contact-search-icon" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
              </svg>
              <input
                type="text"
                placeholder="搜索联系人"
                v-model="searchQuery"
                class="contact-search-input"
                :class="{ 'privacy-blur': privacyMode }"
                @focus="openGeneralSearchPanel"
                @blur="scheduleCloseGeneralSearchPanel"
              >
              <button
                v-if="searchQuery"
                type="button"
                class="contact-search-clear"
                @click="searchQuery = ''"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>
            </div>

            <select
              v-if="showSearchAccountSwitcher"
              v-model="selectedAccount"
              @change="onAccountChange"
              class="account-select"
            >
              <option v-if="!availableAccounts.length" disabled value="">{{ chatAccounts.loading ? '加载中...' : (chatAccounts.error || '无账号') }}</option>
              <option v-for="acc in availableAccounts" :key="acc" :value="acc">{{ acc }}</option>
            </select>
          </div>
        </div>

        <!-- 联系人列表 -->
        <div class="session-list-scroll flex-1 overflow-y-auto min-h-0">
          <div v-if="isLoadingContacts" class="px-3 py-4 h-full overflow-hidden">
            <div v-for="i in 15" :key="i" class="flex items-center space-x-3 h-[calc(80px/var(--dpr))]">
              <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md bg-gray-200 skeleton-pulse"></div>
              <div class="flex-1 space-y-2">
                <div class="h-3.5 bg-gray-200 rounded skeleton-pulse" :style="{ width: (60 + (i % 4) * 15) + 'px' }"></div>
                <div class="h-3 bg-gray-200 rounded skeleton-pulse" :style="{ width: (80 + (i % 3) * 20) + 'px' }"></div>
              </div>
            </div>
          </div>
          <div v-else-if="contactsError" class="session-list-status px-3 py-2 text-sm text-red-500 whitespace-pre-wrap">
            {{ contactsError }}
          </div>
          <div v-else-if="contacts.length === 0" class="session-list-status px-3 py-2 text-sm">
            暂无会话
          </div>
          <div v-else class="pb-4">
            <div v-for="contact in filteredContacts" :key="contact.id"
              class="session-list-item px-3 cursor-pointer transition-colors duration-150 h-[calc(80px/var(--dpr))] flex items-center"
              :class="{
                'session-list-item--top': contact.isTop,
                'session-list-item--selected': selectedContact?.id === contact.id
              }"
              @click="selectContact(contact)">
              <div class="flex items-center space-x-3 w-full">
                <!-- 联系人头像 -->
                <div class="relative flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                  <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md overflow-hidden bg-gray-300">
                    <div v-if="contact.avatar" class="w-full h-full">
                      <img :src="contact.avatar" :alt="contact.name" class="w-full h-full object-cover" loading="lazy" referrerpolicy="no-referrer" @error="onAvatarError($event, contact)">
                    </div>
                    <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                      :style="{ backgroundColor: contact.avatarColor || '#4B5563' }">
                      {{ contact.name.charAt(0) }}
                    </div>
                  </div>
                  <span
                    v-if="contact.unreadCount > 0"
                    class="absolute z-10 -top-[calc(4px/var(--dpr))] -right-[calc(4px/var(--dpr))] w-[calc(10px/var(--dpr))] h-[calc(10px/var(--dpr))] bg-[#ed4d4d] rounded-full"
                  ></span>
                </div>
                
                <!-- 联系人信息 -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between">
                    <h3 class="session-list-item-name text-sm truncate" :class="{ 'privacy-blur': privacyMode }">{{ contact.name }}</h3>
                    <div class="flex items-center flex-shrink-0 ml-2">
                      <span class="session-list-item-time text-xs">{{ contact.lastMessageTime }}</span>
                    </div>
                  </div>
                  <p class="session-list-item-preview text-xs truncate mt-0.5 leading-tight" :class="{ 'privacy-blur': privacyMode }">
                    <span
                      v-for="(seg, idx) in parseTextWithEmoji(
                        (contact.unreadCount > 0 ? `[${contact.unreadCount > 99 ? '99+' : contact.unreadCount}条] ` : '') +
                        String(contact.lastMessage || '')
                      )"
                      :key="idx"
                    >
                      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                      <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" />
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 样式展示列表已移除 -->
    </div>

    <Teleport to="body">
      <div
        v-if="generalSearchPanelOpen"
        class="general-search-panel fixed z-[140] overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_18px_45px_rgba(15,23,42,0.16)]"
        :style="generalSearchPanelStyle"
        @mousedown.prevent
      >
        <div class="flex items-center justify-between gap-3 border-b border-[#f0f2f5] px-4 py-3">
          <div class="min-w-0">
            <div class="truncate text-[13px] font-semibold text-[#111827]">搜索相关记录</div>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-md px-2 py-1 text-[12px] text-[#07C160] transition hover:bg-[#f0fdf4] disabled:opacity-60"
            :disabled="generalSearchLoading"
            @click="loadGeneralSearchRecords({ force: true })"
          >
            {{ generalSearchLoading ? '刷新中' : '刷新' }}
          </button>
        </div>

        <div class="flex gap-1 border-b border-[#f0f2f5] bg-[#fafafa] px-3 py-2">
          <button
            v-for="tab in generalSearchSourceTabs"
            :key="tab.key"
            type="button"
            class="flex min-w-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition"
            :class="generalSearchActiveSource === tab.key ? 'bg-white text-[#07C160] shadow-sm ring-1 ring-[#d9fbe6]' : 'text-[#6b7280] hover:bg-white hover:text-[#111827]'"
            @click="generalSearchActiveSource = tab.key"
          >
            <span>{{ tab.label }}</span>
            <span
              class="rounded-full px-1.5 py-0.5 text-[10px] tabular-nums"
              :class="generalSearchActiveSource === tab.key ? 'bg-[#ecfff5] text-[#047857]' : 'bg-[#f1f5f9] text-[#64748b]'"
            >
              {{ generalSearchSourceCounts[tab.key] || 0 }}
            </span>
          </button>
        </div>

        <div class="max-h-[340px] overflow-y-auto py-1">
          <div v-if="generalSearchLoading && !generalSearchRecords.length" class="px-4 py-4 text-[13px] text-[#6b7280]">
            正在读取搜索记录…
          </div>
          <div v-else-if="generalSearchError" class="px-4 py-3 text-[13px] leading-5 text-[#b91c1c]">
            {{ generalSearchError }}
          </div>
          <div v-else-if="!filteredGeneralSearchRecords.length" class="px-4 py-4 text-[13px] text-[#6b7280]">
            暂无匹配记录
          </div>
          <template v-else>
            <button
              v-for="item in filteredGeneralSearchRecords"
              :key="`${item.source}-${item.keyword}-${item.timestamp}-${item.username || ''}`"
              type="button"
              class="grid w-full grid-cols-[minmax(0,1fr)_118px] items-center gap-3 px-4 py-2.5 text-left transition hover:bg-[#f7fdf9]"
              @click="selectGeneralSearchRecord(item)"
            >
              <span class="flex min-w-0 items-center gap-2">
                <span
                  v-if="isGeneralChatSearchRecord(item)"
                  class="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#e5e7eb] text-[12px] font-semibold text-white"
                  :style="{ backgroundColor: generalSearchAvatar(item) ? '#e5e7eb' : generalSearchAvatarColor(item) }"
                >
                  <img
                    v-if="generalSearchAvatar(item)"
                    :src="generalSearchAvatar(item)"
                    :alt="generalSearchAvatarAlt(item)"
                    class="h-full w-full object-cover"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    @error="onGeneralSearchAvatarError($event, item)"
                  >
                  <span v-else>{{ generalSearchAvatarFallback(item) }}</span>
                </span>
                <span class="min-w-0">
                  <span class="block truncate text-[13px] text-[#111827]">{{ item.keyword || '（空关键词）' }}</span>
                  <span
                    v-if="generalSearchSubtitle(item)"
                    class="mt-0.5 block truncate text-[11px] text-[#9ca3af]"
                    :title="generalSearchSubtitleTitle(item)"
                  >
                    {{ generalSearchSubtitle(item) }}
                  </span>
                </span>
              </span>
              <span class="shrink-0 text-right text-[11px] text-[#9ca3af]">{{ item.timeText || '—' }}</span>
            </button>
          </template>
        </div>
      </div>
    </Teleport>
</template>

<script>
import { computed, defineComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useApi } from '~/composables/useApi'

export default defineComponent({
  name: 'SessionListPanel',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    const api = useApi()
    const generalSearchPanelOpen = ref(false)
    const generalSearchLoading = ref(false)
    const generalSearchError = ref('')
    const generalSearchRecords = ref([])
    const generalSearchLoadedAccount = ref('')
    const generalSearchPanelStyle = ref({})
    const generalSearchBrokenAvatarKeys = ref(new Set())
    const searchInputWrapperRef = ref(null)
    let closePanelTimer = null

    const PANEL_MIN_WIDTH = 360
    const PANEL_WIDTH = 460
    const PANEL_MAX_WIDTH = 520
    const PANEL_VIEWPORT_MARGIN = 16
    const PANEL_GAP = 8
    const generalSearchActiveSource = ref('聊天搜索')
    const generalSearchSourceTabs = [
      { key: '聊天搜索', label: '聊天搜索' },
      { key: '品牌搜索', label: '品牌搜索' },
      { key: '网页搜索', label: '网页搜索' }
    ]

    const currentAccount = () => String(props.state?.selectedAccount?.value || '').trim()
    const normalizeUsername = (value) => String(value || '').trim().toLowerCase()
    const isUsefulResolvedName = (name, username) => {
      const n = String(name || '').trim()
      const u = String(username || '').trim()
      return !!n && (!u || n.toLowerCase() !== u.toLowerCase())
    }

    const contactByUsername = computed(() => {
      const out = new Map()
      for (const contact of Array.isArray(props.state?.contacts?.value) ? props.state.contacts.value : []) {
        const username = normalizeUsername(contact?.username || contact?.id)
        if (!username) continue
        out.set(username, contact)
      }
      return out
    })

    const updateGeneralSearchPanelPosition = () => {
      if (typeof window === 'undefined') return
      const anchorEl = searchInputWrapperRef.value
      if (!anchorEl || typeof anchorEl.getBoundingClientRect !== 'function') return

      const rect = anchorEl.getBoundingClientRect()
      const viewportWidth = Math.max(window.innerWidth || 0, 320)
      const maxUsableWidth = Math.max(viewportWidth - PANEL_VIEWPORT_MARGIN * 2, 280)
      const preferredWidth = Math.min(PANEL_WIDTH, PANEL_MAX_WIDTH, maxUsableWidth)
      const minWidth = Math.min(PANEL_MIN_WIDTH, maxUsableWidth)
      let width = Math.max(minWidth, preferredWidth)
      width = Math.min(width, maxUsableWidth)

      let left = rect.left
      const maxLeft = viewportWidth - PANEL_VIEWPORT_MARGIN - width
      if (left > maxLeft) {
        left = Math.max(PANEL_VIEWPORT_MARGIN, maxLeft)
      }

      generalSearchPanelStyle.value = {
        left: `${Math.round(left)}px`,
        top: `${Math.round(rect.bottom + PANEL_GAP)}px`,
        width: `${Math.round(width)}px`,
      }
    }

    const generalSearchSourceCounts = computed(() => {
      const out = {}
      for (const tab of generalSearchSourceTabs) out[tab.key] = 0
      for (const item of Array.isArray(generalSearchRecords.value) ? generalSearchRecords.value : []) {
        const source = String(item?.source || '')
        out[source] = (out[source] || 0) + 1
      }
      return out
    })

    const filteredGeneralSearchRecords = computed(() => {
      const keyword = String(props.state?.searchQuery?.value || '').trim().toLowerCase()
      const rows = Array.isArray(generalSearchRecords.value) ? generalSearchRecords.value : []
      const source = String(generalSearchActiveSource.value || '')
      const scopedRows = source ? rows.filter((item) => String(item?.source || '') === source) : rows
      if (!keyword) return scopedRows.slice(0, 12)
      return scopedRows
        .filter((item) => {
          const resolved = resolveGeneralSearchContact(item)
          const summary = item?.summaryText || item?.payloadSummary?.summaryText || ''
          const hay = `${item?.keyword || ''} ${item?.source || ''} ${item?.username || ''} ${resolved?.name || ''} ${summary}`.toLowerCase()
          return hay.includes(keyword)
        })
        .slice(0, 12)
    })

    const generalSearchBadgeClass = (source) => {
      if (source === '聊天搜索') return 'bg-[#eff6ff] text-[#1d4ed8]'
      if (source === '品牌搜索') return 'bg-[#fff7ed] text-[#c2410c]'
      return 'bg-[#f0fdf4] text-[#047857]'
    }

    const generalSearchSubtitle = (item) => {
      const source = String(item?.source || '')
      if (source === '聊天搜索') {
        const username = String(item?.username || '').trim()
        const resolved = resolveGeneralSearchContact(item)
        if (resolved?.hasResolvedName && resolved?.name) {
          return `${resolved.isGroup ? '群聊' : '会话'}：${resolved.name}`
        }
        return username ? `${username.includes('@chatroom') ? '群聊ID' : '会话ID'}：${username}` : ''
      }

      return ''
    }

    const generalSearchSubtitleTitle = (item) => {
      const source = String(item?.source || '')
      if (source === '聊天搜索') {
        const username = String(item?.username || '').trim()
        const resolved = resolveGeneralSearchContact(item)
        if (resolved?.hasResolvedName && resolved?.name && username) {
          return `${resolved.name} · ${username}`
        }
        return username
      }
      return ''
    }

    const resolveGeneralSearchContact = (item) => {
      const username = normalizeUsername(item?.username)
      if (!username) return null
      const contact = contactByUsername.value.get(username)
      const backend = (item?.contact && typeof item.contact === 'object') ? item.contact : {}
      const rawUsername = String(
        contact?.username || contact?.id || backend?.username || item?.username || ''
      ).trim()
      const candidates = [
        contact?.name,
        contact?.displayName,
        backend?.displayName,
        backend?.name,
        backend?.nickname,
        backend?.remark,
      ]
      const resolvedName = candidates.map((value) => String(value || '').trim()).find((value) => {
        return isUsefulResolvedName(value, rawUsername)
      })
      const fallbackName = String(candidates.find((value) => String(value || '').trim()) || rawUsername).trim()
      const avatar = String(contact?.avatar || backend?.avatar || backend?.avatarUrl || '').trim()
      const isGroup = !!contact?.isGroup || !!backend?.isGroup || rawUsername.includes('@chatroom')
      return {
        name: resolvedName || fallbackName || rawUsername,
        username: rawUsername,
        avatar,
        isGroup,
        hasResolvedName: !!resolvedName || !!backend?.hasResolvedName
      }
    }

    const isGeneralChatSearchRecord = (item) => String(item?.source || '') === '聊天搜索'

    const generalSearchAvatarKey = (item) => {
      return `${item?.source || ''}::${item?.username || ''}::${item?.timestamp || ''}`
    }

    const generalSearchAvatar = (item) => {
      if (!isGeneralChatSearchRecord(item)) return ''
      const key = generalSearchAvatarKey(item)
      if (generalSearchBrokenAvatarKeys.value.has(key)) return ''
      const resolved = resolveGeneralSearchContact(item)
      return String(resolved?.avatar || '').trim()
    }

    const generalSearchAvatarFallback = (item) => {
      const resolved = resolveGeneralSearchContact(item)
      if (resolved?.isGroup) return '群'
      const name = String(resolved?.name || item?.keyword || '').trim()
      return name ? name.charAt(0) : '会'
    }

    const generalSearchAvatarAlt = (item) => {
      const resolved = resolveGeneralSearchContact(item)
      return String(resolved?.name || item?.keyword || 'avatar')
    }

    const generalSearchAvatarColor = (item) => {
      const resolved = resolveGeneralSearchContact(item)
      return resolved?.isGroup ? '#07C160' : '#64748b'
    }

    const onGeneralSearchAvatarError = (event, item) => {
      try { event?.target && (event.target.style.display = 'none') } catch {}
      const key = generalSearchAvatarKey(item)
      const next = new Set(generalSearchBrokenAvatarKeys.value)
      next.add(key)
      generalSearchBrokenAvatarKeys.value = next
    }

    const syncActiveGeneralSearchSource = () => {
      const counts = generalSearchSourceCounts.value || {}
      if (counts[generalSearchActiveSource.value] > 0) return
      const next = generalSearchSourceTabs.find((tab) => counts[tab.key] > 0)
      if (next) generalSearchActiveSource.value = next.key
    }

    const loadGeneralSearchRecords = async (options = {}) => {
      const account = currentAccount()
      if (!account) {
        generalSearchRecords.value = []
        generalSearchLoadedAccount.value = ''
        generalSearchError.value = '未找到可用账号，先完成检测或导入。'
        return
      }
      if (!options.force && generalSearchLoadedAccount.value === account && generalSearchRecords.value.length) return

      generalSearchLoading.value = true
      generalSearchError.value = ''
      try {
        const resp = await api.listGeneralSearchRecords({ account, limit: 50 })
        generalSearchRecords.value = Array.isArray(resp?.items) ? resp.items : []
        generalSearchBrokenAvatarKeys.value = new Set()
        generalSearchLoadedAccount.value = account
        syncActiveGeneralSearchSource()
      } catch (e) {
        generalSearchRecords.value = []
        generalSearchLoadedAccount.value = ''
        generalSearchError.value = e?.message || '读取搜索记录失败'
      } finally {
        generalSearchLoading.value = false
      }
    }

    const openGeneralSearchPanel = async () => {
      if (closePanelTimer) clearTimeout(closePanelTimer)
      generalSearchPanelOpen.value = true
      await nextTick()
      updateGeneralSearchPanelPosition()
      await loadGeneralSearchRecords()
    }

    const scheduleCloseGeneralSearchPanel = () => {
      if (closePanelTimer) clearTimeout(closePanelTimer)
      closePanelTimer = setTimeout(() => {
        generalSearchPanelOpen.value = false
      }, 140)
    }

    const selectGeneralSearchRecord = (item) => {
      if (isGeneralChatSearchRecord(item)) {
        const username = String(item?.username || item?.contact?.username || '').trim()
        if (username) {
          const resolved = resolveGeneralSearchContact(item) || {}
          const existing = contactByUsername.value.get(normalizeUsername(username))
          const targetContact = existing || {
            id: username,
            username,
            name: String(resolved?.name || item?.keyword || username).trim(),
            avatar: String(resolved?.avatar || '').trim() || null,
            avatarColor: resolved?.isGroup ? '#07C160' : '#4B5563',
            lastMessage: '',
            lastMessageTime: '',
            unreadCount: 0,
            isGroup: !!resolved?.isGroup || username.includes('@chatroom'),
            isTop: false
          }
          if (typeof props.state?.selectContact === 'function') {
            void props.state.selectContact(targetContact, { reason: 'general-search-record' })
          } else {
            void navigateTo(`/chat/${encodeURIComponent(username)}`)
          }
          generalSearchPanelOpen.value = false
          return
        }
      }
      const keyword = String(item?.keyword || '').trim()
      if (keyword && props.state?.searchQuery) {
        props.state.searchQuery.value = keyword
      }
      generalSearchPanelOpen.value = false
    }

    watch(
      () => currentAccount(),
      () => {
        generalSearchRecords.value = []
        generalSearchBrokenAvatarKeys.value = new Set()
        generalSearchLoadedAccount.value = ''
        if (generalSearchPanelOpen.value) {
          void loadGeneralSearchRecords({ force: true })
        }
      }
    )

    watch(
      () => props.state?.sessionListWidth?.value,
      () => {
        if (!generalSearchPanelOpen.value) return
        void nextTick(() => {
          updateGeneralSearchPanelPosition()
        })
      }
    )

    const onWindowResize = () => {
      if (!generalSearchPanelOpen.value) return
      updateGeneralSearchPanelPosition()
    }

    onMounted(() => {
      if (typeof window === 'undefined') return
      window.addEventListener('resize', onWindowResize)
      window.addEventListener('scroll', onWindowResize, true)
    })

    onBeforeUnmount(() => {
      if (closePanelTimer) clearTimeout(closePanelTimer)
      if (typeof window !== 'undefined') {
        window.removeEventListener('resize', onWindowResize)
        window.removeEventListener('scroll', onWindowResize, true)
      }
    })

    return {
      ...props.state,
      generalSearchPanelOpen,
      generalSearchLoading,
      generalSearchError,
      generalSearchRecords,
      generalSearchPanelStyle,
      searchInputWrapperRef,
      generalSearchActiveSource,
      generalSearchSourceTabs,
      generalSearchSourceCounts,
      filteredGeneralSearchRecords,
      generalSearchBadgeClass,
      generalSearchSubtitle,
      generalSearchSubtitleTitle,
      isGeneralChatSearchRecord,
      generalSearchAvatar,
      generalSearchAvatarFallback,
      generalSearchAvatarAlt,
      generalSearchAvatarColor,
      onGeneralSearchAvatarError,
      loadGeneralSearchRecords,
      openGeneralSearchPanel,
      scheduleCloseGeneralSearchPanel,
      selectGeneralSearchRecord
    }
  }
})
</script>
