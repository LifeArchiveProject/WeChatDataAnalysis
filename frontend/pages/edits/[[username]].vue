<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <!-- 左侧：会话列表（与聊天页统一风格） -->
    <div class="edits-sidebar border-r border-gray-200 flex flex-col">
      <!-- 搜索栏区域 -->
      <div class="p-3 border-b border-gray-200" style="background-color: #F7F7F7">
        <div class="flex items-center gap-2">
          <div class="contact-search-wrapper flex-1">
            <svg class="contact-search-icon" fill="none" stroke="currentColor" viewBox="0 0 16 16">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
            </svg>
            <input
              type="text"
              placeholder="搜索修改记录"
              v-model="searchQuery"
              class="contact-search-input"
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
          <button
            class="w-8 h-8 flex items-center justify-center rounded-md text-gray-500 hover:text-gray-700 hover:bg-[#DEDEDE] transition-colors flex-shrink-0"
            type="button"
            :disabled="sessionsLoading || !selectedAccount"
            :class="sessionsLoading || !selectedAccount ? 'opacity-40 cursor-not-allowed' : ''"
            title="刷新"
            @click="loadSessions"
          >
            <svg class="w-4 h-4" :class="sessionsLoading ? 'animate-spin' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
          </button>
        </div>
        <div v-if="!selectedAccount" class="mt-1.5 text-xs text-gray-400">未选择账号</div>
        <div v-if="sessionsError" class="mt-2 text-xs text-red-500 whitespace-pre-wrap">{{ sessionsError }}</div>
      </div>

      <!-- 会话列表区域 -->
      <div class="flex-1 overflow-y-auto min-h-0">
        <!-- 骨架屏加载 -->
        <div v-if="sessionsLoading" class="px-3 py-4 h-full overflow-hidden">
          <div v-for="i in 10" :key="i" class="flex items-center space-x-3 h-[calc(70px/var(--dpr,1))]">
            <div class="w-[calc(45px/var(--dpr,1))] h-[calc(45px/var(--dpr,1))] rounded-md bg-gray-200 skeleton-pulse"></div>
            <div class="flex-1 space-y-2">
              <div class="h-3.5 bg-gray-200 rounded skeleton-pulse" :style="{ width: (55 + (i % 4) * 15) + 'px' }"></div>
              <div class="h-3 bg-gray-200 rounded skeleton-pulse" :style="{ width: (70 + (i % 3) * 20) + 'px' }"></div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else-if="!sessions.length" class="px-3 py-2 text-sm text-gray-500">暂无修改记录</div>

        <!-- 列表项（复用聊天页样式） -->
        <template v-else>
          <div
            v-for="s in filteredSessions"
            :key="s.username"
            class="px-3 cursor-pointer transition-colors duration-150 border-b border-gray-100 h-[calc(70px/var(--dpr,1))] flex items-center"
            :class="s.username === activeUsername
              ? 'bg-[#DEDEDE] hover:bg-[#d3d3d3]'
              : 'hover:bg-[#eaeaea]'"
            @click="selectSession(s.username)"
          >
            <div class="flex items-center space-x-3 w-full">
              <!-- 头像 -->
              <div class="relative flex-shrink-0">
                <div class="w-[calc(45px/var(--dpr,1))] h-[calc(45px/var(--dpr,1))] rounded-md overflow-hidden bg-gray-300">
                  <div v-if="s.avatar" class="w-full h-full">
                    <img :src="normalizeMaybeUrl(s.avatar)" :alt="s.name || s.username" class="w-full h-full object-cover" referrerpolicy="no-referrer" />
                  </div>
                  <div v-else class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                    :style="{ backgroundColor: '#4B5563' }">
                    {{ (s.name || s.username || '?').charAt(0) }}
                  </div>
                </div>
                <!-- 编辑数量红点 -->
                <span
                  v-if="s.editedCount > 0"
                  class="absolute z-10 -top-[calc(4px/var(--dpr,1))] -right-[calc(4px/var(--dpr,1))] min-w-[calc(18px/var(--dpr,1))] h-[calc(18px/var(--dpr,1))] px-1 flex items-center justify-center bg-[#ed4d4d] rounded-full text-white text-[10px] font-medium leading-none"
                >
                  {{ s.editedCount > 99 ? '99+' : s.editedCount }}
                </span>
              </div>

              <!-- 信息 -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between">
                  <h3 class="text-sm font-medium text-gray-900 truncate">{{ s.name || s.username }}</h3>
                  <div class="flex items-center flex-shrink-0 ml-2">
                    <span v-if="s.lastEditedAt" class="text-xs text-gray-500">{{ formatRelativeTime(s.lastEditedAt) }}</span>
                  </div>
                </div>
                <p class="text-xs text-gray-500 truncate mt-0.5 leading-tight">
                  {{ s.editedCount || 0 }} 条修改
                </p>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 右侧：diff 对比区 -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Header（与聊天页统一） -->
      <div class="chat-header">
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <h2 class="text-base font-medium text-gray-900 truncate">
            {{ activeSessionName }}
          </h2>
        </div>
        <div class="ml-auto flex items-center gap-2">
          <button
            v-if="activeUsername"
            class="header-btn-icon"
            type="button"
            :disabled="itemsLoading || resetting"
            :class="itemsLoading || resetting ? 'opacity-50 cursor-not-allowed' : ''"
            title="一键重置此会话"
            @click="onResetSessionClick"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 内容区 -->
      <div class="flex-1 overflow-y-auto" style="background-color: #EDEDED">
        <!-- 错误提示 -->
        <div v-if="itemsError" class="mx-5 mt-4 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3 whitespace-pre-wrap">{{ itemsError }}</div>

        <!-- 加载态 -->
        <div v-if="itemsLoading" class="px-5 py-6 space-y-5">
          <div v-for="i in 3" :key="i" class="bg-white rounded-xl overflow-hidden shadow-sm">
            <div class="h-10 bg-gray-50 border-b border-gray-100 skeleton-pulse"></div>
            <div class="grid grid-cols-2 divide-x divide-gray-100">
              <div class="p-4"><div class="h-16 bg-gray-100 rounded-lg skeleton-pulse"></div></div>
              <div class="p-4"><div class="h-16 bg-gray-100 rounded-lg skeleton-pulse"></div></div>
            </div>
          </div>
        </div>

        <!-- 未选会话 -->
        <div v-else-if="!activeUsername" class="flex flex-col items-center justify-center h-full">
          <div class="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mb-4">
            <svg class="w-10 h-10 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
            </svg>
          </div>
          <div class="text-sm text-gray-400">请从左侧选择一个会话</div>
        </div>

        <!-- 无记录 -->
        <div v-else-if="!items.length" class="flex flex-col items-center justify-center h-full">
          <div class="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-3">
            <svg class="w-8 h-8 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </div>
          <div class="text-sm text-gray-400">该会话暂无修改记录</div>
        </div>

        <!-- Diff 列表（无卡片包装，直接渲染在页面上） -->
        <div v-else class="edits-list">
          <div v-for="it in items" :key="it.messageId" class="edits-item">
            <!-- 时间分割线（聊天页风格居中） -->
            <div class="flex justify-center mb-4">
              <div class="px-3 py-1 text-xs text-[#9e9e9e]">
                <span v-if="it.lastEditedAt">{{ formatTime(it.lastEditedAt) }}</span>
                <span v-if="it.editCount"> · 编辑 {{ it.editCount }} 次</span>
              </div>
            </div>

            <!-- Side-by-side diff -->
            <div class="edits-diff-body">
              <!-- 左：原消息 -->
              <div class="edits-diff-pane">
                <EditedMessagePreview :message="it.original" />
              </div>

              <!-- 中间分割线 -->
              <div class="edits-diff-divider">
                <button
                  class="edits-divider-arrow"
                  type="button"
                  :disabled="resetting"
                  :class="resetting ? 'opacity-50 cursor-not-allowed' : ''"
                  title="重置此条"
                  @click="onResetMessageClick(it)"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M5 12h14" />
                    <path d="M12 5l7 7-7 7" />
                  </svg>
                </button>
              </div>

              <!-- 右：修改后 -->
              <div class="edits-diff-pane">
                <EditedMessagePreview :message="it.current" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 自定义确认/提示弹窗 -->
    <Teleport to="body">
      <Transition name="edits-dialog">
        <div v-if="dialogVisible" class="edits-dialog-overlay" @click.self="onDialogCancel">
          <div class="edits-dialog-card">
            <div class="edits-dialog-title">{{ dialogTitle }}</div>
            <div class="edits-dialog-msg">{{ dialogMessage }}</div>
            <div class="edits-dialog-actions">
              <button v-if="dialogShowCancel" class="edits-dialog-btn edits-dialog-cancel" @click="onDialogCancel">取消</button>
              <button class="edits-dialog-btn edits-dialog-confirm" @click="onDialogConfirm">确定</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import EditedMessagePreview from '~/components/EditedMessagePreview.vue'

const route = useRoute()

const chatAccounts = useChatAccountsStore()
const { selectedAccount } = storeToRefs(chatAccounts)

const searchQuery = ref('')

onMounted(async () => {
  await chatAccounts.ensureLoaded()
  await loadSessions()
})

watch(selectedAccount, async () => {
  await loadSessions()
})

const apiBase = useApiBase()

const normalizeMaybeUrl = (u) => {
  const raw = String(u || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw) || /^blob:/i.test(raw) || /^data:/i.test(raw)) return raw
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw
}

const formatTime = (ms) => {
  const v = Number(ms || 0)
  if (!v) return ''
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

const formatRelativeTime = (ms) => {
  const v = Number(ms || 0)
  if (!v) return ''
  try {
    const d = new Date(v)
    const now = new Date()
    const diff = now - d
    // 今天
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    // 昨天
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (d.toDateString() === yesterday.toDateString()) {
      return '昨天'
    }
    // 7 天内
    if (diff < 7 * 24 * 3600 * 1000) {
      const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
      return days[d.getDay()]
    }
    // 更早
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch {
    return String(v)
  }
}

const prettyJson = (obj) => {
  try {
    return JSON.stringify(obj ?? null, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

const sessions = ref([])
const sessionsLoading = ref(false)
const sessionsError = ref('')

const items = ref([])
const itemsLoading = ref(false)
const itemsError = ref('')
const resetting = ref(false)

const activeUsername = computed(() => String(route.params?.username || '').trim())
const activeSessionName = computed(() => {
  const uname = activeUsername.value
  if (!uname) return '修改记录'
  const s = sessions.value.find((x) => String(x?.username || '') === uname)
  return s?.name || s?.username || uname
})

// 搜索过滤
const filteredSessions = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter((s) => {
    const name = String(s.name || '').toLowerCase()
    const username = String(s.username || '').toLowerCase()
    return name.includes(q) || username.includes(q)
  })
})

const selectSession = async (username) => {
  const u = String(username || '').trim()
  if (!u) return
  await navigateTo(`/edits/${encodeURIComponent(u)}`)
}

const loadSessions = async () => {
  if (!process.client) return
  sessionsError.value = ''
  sessionsLoading.value = true

  try {
    if (!selectedAccount.value) {
      sessions.value = []
      return
    }
    const api = useApi()
    const resp = await api.listChatEditedSessions({ account: selectedAccount.value })
    sessions.value = Array.isArray(resp?.sessions) ? resp.sessions : []

    const current = activeUsername.value
    if (current) {
      const exists = sessions.value.some((s) => String(s?.username || '') === current)
      if (!exists && sessions.value.length) {
        await selectSession(sessions.value[0].username)
      }
      if (!exists && !sessions.value.length) {
        await navigateTo('/edits')
      }
    } else if (sessions.value.length) {
      await selectSession(sessions.value[0].username)
    }
  } catch (e) {
    sessions.value = []
    sessionsError.value = e?.message || '加载会话失败'
  } finally {
    sessionsLoading.value = false
  }
}

const loadItems = async () => {
  if (!process.client) return
  itemsError.value = ''
  itemsLoading.value = true

  try {
    const uname = activeUsername.value
    if (!selectedAccount.value || !uname) {
      items.value = []
      return
    }
    const api = useApi()
    const resp = await api.listChatEditedMessages({ account: selectedAccount.value, username: uname })
    items.value = Array.isArray(resp?.items) ? resp.items : []
  } catch (e) {
    items.value = []
    itemsError.value = e?.message || '加载修改记录失败'
  } finally {
    itemsLoading.value = false
  }
}

watch(activeUsername, async () => {
  await loadItems()
}, { immediate: true })

// ===== 自定义弹窗 =====
const dialogVisible = ref(false)
const dialogTitle = ref('')
const dialogMessage = ref('')
const dialogShowCancel = ref(true)
let dialogResolve = null

const showConfirm = (title, message) => {
  return new Promise((resolve) => {
    dialogTitle.value = title
    dialogMessage.value = message
    dialogShowCancel.value = true
    dialogResolve = resolve
    dialogVisible.value = true
  })
}

const showAlert = (title, message) => {
  return new Promise((resolve) => {
    dialogTitle.value = title
    dialogMessage.value = message || ''
    dialogShowCancel.value = false
    dialogResolve = resolve
    dialogVisible.value = true
  })
}

const onDialogConfirm = () => {
  dialogVisible.value = false
  dialogResolve?.(true)
  dialogResolve = null
}

const onDialogCancel = () => {
  dialogVisible.value = false
  dialogResolve?.(false)
  dialogResolve = null
}

const onResetMessageClick = async (it) => {
  if (!process.client) return
  if (!selectedAccount.value) return
  const uname = activeUsername.value
  if (!uname) return
  const mid = String(it?.messageId || '').trim()
  if (!mid) return
  const ok = await showConfirm('重置消息', '确认重置该条消息到首次快照吗？')
  if (!ok) return

  resetting.value = true
  try {
    const api = useApi()
    await api.resetChatEditedMessage({
      account: selectedAccount.value,
      session_id: uname,
      message_id: mid,
    })
    await loadSessions()
    await loadItems()
  } catch (e) {
    await showAlert('重置失败', e?.message || '请稍后重试')
  } finally {
    resetting.value = false
  }
}

const onResetSessionClick = async () => {
  if (!process.client) return
  if (!selectedAccount.value) return
  const uname = activeUsername.value
  if (!uname) return
  const ok = await showConfirm('重置会话', '确认重置该会话下全部修改记录吗？')
  if (!ok) return

  resetting.value = true
  try {
    const api = useApi()
    const resp = await api.resetChatEditedSession({
      account: selectedAccount.value,
      session_id: uname,
    })
    const restored = Number(resp?.restored || 0)
    const failed = Number(resp?.failed || 0)
    if (failed) {
      await showAlert('部分失败', `已恢复 ${restored} 条，失败 ${failed} 条（详情请查看控制台）`)
      // eslint-disable-next-line no-console
      console.error('reset_session failures:', resp?.failures || [])
    }
    await loadSessions()
    await loadItems()
  } catch (e) {
    await showAlert('重置失败', e?.message || '请稍后重试')
  } finally {
    resetting.value = false
  }
}

</script>

<style scoped>
/* ===== 左侧会话面板 ===== */
.edits-sidebar {
  width: var(--session-list-width, 280px);
  min-width: 240px;
  max-width: 360px;
  background-color: #F7F7F7;
}

/* ===== 右侧 Diff 列表 ===== */
.edits-list {
  padding: 8px 0;
}

.edits-item {
  padding: 8px 16px 16px;
  border-top: 1px solid #d6d6d6;
}

.edits-item:last-child {
  border-bottom: 1px solid #d6d6d6;
}

/* Side-by-side diff */
.edits-diff-body {
  display: flex;
  min-height: 60px;
}

.edits-diff-pane {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  max-height: 200px;
  overflow-y: auto;
}

.edits-diff-pane::-webkit-scrollbar {
  width: 4px;
}

.edits-diff-pane::-webkit-scrollbar-track {
  background: transparent;
}

.edits-diff-pane::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}

.edits-diff-pane::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

.edits-diff-pane::-webkit-scrollbar-button {
  display: none;
}

/* 中间分割线 */
.edits-diff-divider {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 24px;
  flex-shrink: 0;
  position: relative;
}

/* 虚线背景 */
.edits-diff-divider::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  border-left: none;
  background: linear-gradient(to bottom, transparent 0%, #07c160 15%, #07c160 85%, transparent 100%);
}

/* 箭头按钮 */
.edits-divider-arrow {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  background: #EDEDED;
  color: #07c160;
  cursor: pointer;
  transition: all 0.15s;
  padding: 0;
}

.edits-divider-arrow:hover:not(:disabled) {
  background: #e0f5e9;
  color: #059341;
}

@media (max-width: 768px) {
  .edits-diff-body {
    flex-direction: column;
  }
  .edits-diff-divider {
    flex-direction: row;
    width: auto;
    height: 24px;
  }
  .edits-diff-divider::before {
    top: 50%;
    bottom: auto;
    left: 0;
    right: 0;
    width: auto;
    height: 2px;
    transform: none;
    background: linear-gradient(to right, transparent 0%, #07c160 15%, #07c160 85%, transparent 100%);
  }
}
</style>

<!-- 弹窗样式需要非 scoped，因为 Teleport 把 DOM 移到了 body -->
<style>
.edits-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
}

.edits-dialog-card {
  background: #fff;
  border-radius: 12px;
  width: 320px;
  max-width: 90vw;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

.edits-dialog-title {
  font-size: 16px;
  font-weight: 600;
  color: #191919;
  text-align: center;
  padding: 24px 24px 8px;
}

.edits-dialog-msg {
  font-size: 14px;
  color: #666;
  text-align: center;
  padding: 0 24px 24px;
  line-height: 1.5;
}

.edits-dialog-actions {
  display: flex;
  border-top: 1px solid #eee;
}

.edits-dialog-btn {
  flex: 1;
  padding: 14px 0;
  font-size: 15px;
  border: none;
  background: none;
  cursor: pointer;
  transition: background 0.15s;
}

.edits-dialog-btn:active {
  background: #f5f5f5;
}

.edits-dialog-cancel {
  color: #666;
  border-right: 1px solid #eee;
}

.edits-dialog-confirm {
  color: #07c160;
  font-weight: 500;
}

/* 弹窗过渡动画 */
.edits-dialog-enter-active,
.edits-dialog-leave-active {
  transition: opacity 0.2s;
}

.edits-dialog-enter-active .edits-dialog-card,
.edits-dialog-leave-active .edits-dialog-card {
  transition: transform 0.2s;
}

.edits-dialog-enter-from,
.edits-dialog-leave-to {
  opacity: 0;
}

.edits-dialog-enter-from .edits-dialog-card {
  transform: scale(0.95);
}

.edits-dialog-leave-to .edits-dialog-card {
  transform: scale(0.95);
}
</style>
