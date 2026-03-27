<template>
  <div class="biz-page h-screen flex overflow-hidden" style="background-color: var(--app-shell-bg)">

    <div :class="['w-[300px] lg:w-[320px] border-r flex flex-col flex-shrink-0 z-10', isDark ? 'bg-[#1e1e1e] border-[#333]' : 'bg-white border-gray-200']">
      <div class="p-3 border-b" :class="isDark ? 'border-[#333]' : 'border-gray-200'" style="background-color: var(--app-surface-muted)">
        <div class="contact-search-wrapper flex-1">
          <input
              v-model="searchQuery"
              type="text"
              class="contact-search-input"
              placeholder="搜索服务号"
          />
        </div>
      </div>

      <div class="flex-1 overflow-y-auto min-h-0">
        <div v-if="loadingAccounts" class="flex justify-center py-4">
          <span class="text-sm" :class="isDark ? 'text-gray-500' : 'text-gray-400'">加载中...</span>
        </div>
        <div v-else>
          <div
              v-for="item in filteredAccounts"
              :key="item.username"
              @click="selectAccount(item)"
              class="flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors border-b"
              :class="[
                isDark ? 'border-[#333]' : 'border-gray-50',
                selectedAccount?.username === item.username
                  ? (isDark ? 'bg-[#333]' : 'bg-[#E5E5E5]') // 选中状态
                  : item.username === 'gh_3dfda90e39d6'
                    ? (isDark ? 'bg-[#2a2a2a] hover:bg-[#333]' : 'bg-[#F2F2F2] hover:bg-[#EAEAEA]') // 微信支付专门的底色
                    : (isDark ? 'hover:bg-[#252525]' : 'hover:bg-gray-50') // 普通悬浮色
              ]"
          >
            <img v-if="item.avatar" :src="api.getBizProxyImageUrl(item.avatar)" :class="['w-10 h-10 rounded-md object-cover flex-shrink-0', isDark ? 'bg-[#333]' : 'bg-gray-200']" alt=""/>
            <div v-else class="w-10 h-10 rounded-md bg-[#03C160] text-white flex items-center justify-center text-lg font-medium flex-shrink-0 shadow-sm">
              {{ (item.name || item.username).charAt(0).toUpperCase() }}
            </div>

            <div class="flex-1 min-w-0 flex flex-col justify-center gap-0.5">
              <div class="flex justify-between items-center">
                <h3 class="text-sm truncate" :class="isDark ? 'text-gray-100' : 'text-gray-900'">{{ item.name || item.username }}</h3>
                <span v-if="item.formatted_last_time" class="text-[11px] flex-shrink-0 ml-2" :class="isDark ? 'text-gray-500' : 'text-gray-400'">
                  {{ item.formatted_last_time }}
                </span>
              </div>

              <div
                  class="text-[10px] px-1.5 py-0.5 rounded w-max mt-0.5"
                  :class="[
                      item.type === 1 ? (isDark ? 'text-[#03C160] bg-[#03C160]/20' : 'text-[#03C160] bg-[#03C160]/10') : // 服务号
                      item.type === 0 ? (isDark ? 'text-blue-400 bg-blue-900/40' : 'text-blue-500 bg-blue-50') :         // 公众号
                      item.type === 2 ? (isDark ? 'text-orange-400 bg-orange-900/40' : 'text-orange-500 bg-orange-50') : // 企业号
                                        (isDark ? 'text-gray-400 bg-gray-700/50' : 'text-gray-400 bg-gray-100')          // 未知
                  ]"
              >
                {{ {1: '服务号', 0: '公众号', 2: '企业号', 3: '未知'}[item.type] || '未知' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="flex-1 flex flex-col min-h-0 min-w-0" :class="isDark ? 'bg-[#121212]' : 'bg-[#F5F5F5]'">
      <div v-if="selectedAccount" class="flex-1 flex flex-col min-h-0 relative">
        <div class="h-14 border-b flex items-center px-5 shrink-0 z-10" :class="isDark ? 'bg-[#121212] border-[#333]' : 'bg-[#F5F5F5] border-gray-200'">
          <h2 class="text-base" :class="isDark ? 'text-gray-100' : 'text-gray-900'">{{ selectedAccount.name }}</h2>
        </div>

        <div class="flex-1 overflow-y-auto px-4 py-6 flex flex-col-reverse" @scroll="handleScroll" ref="messageListRef">
          <div v-if="!hasMore" class="text-center text-xs py-4 w-full" :class="isDark ? 'text-gray-500' : 'text-gray-400'">没有更多消息了</div>
          <div v-if="loadingMessages" class="text-center text-xs py-4 w-full" :class="isDark ? 'text-gray-500' : 'text-gray-400'">正在加载...</div>

          <div class="w-full max-w-[400px] mx-auto flex flex-col-reverse gap-6">
            <div v-for="msg in messages" :key="msg.local_id" class="w-full">

              <div v-if="selectedAccount.username === 'gh_3dfda90e39d6'" class="rounded-xl shadow-sm p-5 border" :class="isDark ? 'bg-[#1e1e1e] border-[#333]' : 'bg-white border-gray-100'">
                <div class="flex items-center text-sm mb-5" :class="isDark ? 'text-gray-400' : 'text-gray-500'">
                  <img v-if="msg.merchant_icon" :src="api.getBizProxyImageUrl(msg.merchant_icon)" class="w-6 h-6 rounded-full mr-2 object-cover"  alt=""/>
                  <div v-else class="w-6 h-6 rounded-full mr-2 flex items-center justify-center" :class="isDark ? 'bg-green-900/40 text-green-400' : 'bg-green-100 text-green-600'">¥</div>
                  <span>{{ msg.merchant_name || '微信支付' }}</span>
                </div>
                <div class="text-center mb-6">
                  <h3 class="text-[22px] font-medium mb-1" :class="isDark ? 'text-gray-100' : 'text-gray-900'">{{ msg.title }}</h3>
                </div>
                <div class="text-[13px] whitespace-pre-wrap leading-relaxed" :class="isDark ? 'text-gray-400' : 'text-gray-500'">
                  {{ msg.description }}
                </div>
                <div class="mt-4 pt-3 border-t text-[12px] text-right" :class="isDark ? 'border-[#333] text-gray-500' : 'border-gray-100 text-gray-400'">
                  {{ msg.formatted_time }}
                </div>
              </div>

              <div v-else class="rounded-xl shadow-sm overflow-hidden border" :class="isDark ? 'bg-[#1e1e1e] border-[#333]' : 'bg-white border-gray-100'">
                <a :href="msg.url" target="_blank" class="block relative group cursor-pointer">
                  <img :src="msg.cover ? api.getBizProxyImageUrl(msg.cover) : defaultImage" :class="['w-full h-[180px] object-cover', isDark ? 'bg-[#333]' : 'bg-gray-100']"  alt=""/>
                  <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3 pt-8">
                    <h3 class="text-white text-[15px] font-medium leading-snug line-clamp-2 group-hover:underline">
                      {{ msg.title }}
                    </h3>
                  </div>
                </a>

                <div v-if="msg.des" class="px-4 py-3 text-[13px] border-b" :class="isDark ? 'text-gray-400 border-[#333]' : 'text-gray-500 border-gray-50'">
                  {{ msg.des }}
                </div>

                <div v-if="msg.content_list && msg.content_list.length > 1" class="flex flex-col">
                  <a
                      v-for="(item, idx) in msg.content_list.slice(1)"
                      :key="idx"
                      :href="item.url"
                      target="_blank"
                      class="flex items-center justify-between p-3 border-t hover:bg-opacity-50 cursor-pointer group"
                      :class="isDark ? 'border-[#333] hover:bg-[#252525]' : 'border-gray-100 hover:bg-gray-50'"
                  >
                    <span class="text-[14px] leading-snug line-clamp-2 pr-3 group-hover:underline" :class="isDark ? 'text-gray-200' : 'text-gray-800'">
                      {{ item.title }}
                    </span>
                    <img :src="item.cover ? api.getBizProxyImageUrl(item.cover) : defaultImage" :class="['w-12 h-12 rounded object-cover flex-shrink-0 border', isDark ? 'bg-[#333] border-[#444]' : 'bg-gray-100 border-gray-100']"  alt=""/>
                  </a>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>

      <div v-else class="flex-1 flex items-center justify-center">
        <div class="text-center">
          <div class="w-20 h-20 mx-auto mb-5 rounded-2xl flex items-center justify-center" :class="isDark ? 'bg-[#2a2a2a]' : 'bg-gray-200/50'">
            <svg class="w-10 h-10" :class="isDark ? 'text-gray-600' : 'text-gray-400'" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5L18.5 7H20" />
            </svg>
          </div>
          <p class="text-sm" :class="isDark ? 'text-gray-500' : 'text-gray-400'">请选择一个服务号查看消息</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

import { useApi } from '~/composables/useApi'
const api = useApi()

import { storeToRefs } from 'pinia'
import { useThemeStore } from '~/stores/theme'

const accounts = ref([])
const loadingAccounts = ref(false)
const searchQuery = ref('')
const selectedAccount = ref(null)

const themeStore = useThemeStore()
const { isDark } = storeToRefs(themeStore)
const messages = ref([])
const loadingMessages = ref(false)
const offset = ref(0)
const limit = 20
const hasMore = ref(true)

const messageListRef = ref(null)

// 默认占位图
// const defaultAvatar = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgdmlld0JveD0iMCAwIDQwIDQwIj48cmVjdCB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIGZpbGw9IiNlNWU3ZWIiLz48L3N2Zz4='
const defaultImage = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MDAiIGhlaWdodD0iMTgwIj48cmVjdCB3aWR0aD0iNDAwIiBoZWlnaHQ9IjE4MCIgZmlsbD0iI2Y1ZjVmNSIvPjwvc3ZnPg=='

const fetchAccounts = async () => {
  loadingAccounts.value = true
  try {
    const res = await api.listBizAccounts()
    if (res && res.data) {
      accounts.value = res.data
    }
  } catch (err) {
    console.error('获取服务号失败:', err)
  } finally {
    loadingAccounts.value = false
  }
}

// 搜索过滤
const filteredAccounts = computed(() => {
  if (!searchQuery.value) return accounts.value
  const q = searchQuery.value.toLowerCase()
  return accounts.value.filter(a =>
      (a.name && a.name.toLowerCase().includes(q)) ||
      (a.username && a.username.toLowerCase().includes(q))
  )
})

// 点击选择服务号
const selectAccount = (account) => {
  if (selectedAccount.value?.username === account.username) return
  selectedAccount.value = account

  // 重置消息状态
  messages.value = []
  offset.value = 0
  hasMore.value = true

  loadMessages()
}

// 加载消息
const loadMessages = async () => {
  if (loadingMessages.value || !hasMore.value || !selectedAccount.value) return

  loadingMessages.value = true
  try {
    const username = selectedAccount.value.username
    const params = { username, offset: offset.value, limit }

    let res
    if (username === 'gh_3dfda90e39d6') {
      res = await api.listBizPayRecords(params)
    } else {
      res = await api.listBizMessages(params)
    }

    if (res && res.data) {
      if (res.data.length < limit) {
        hasMore.value = false
      }
      // 追加数据
      messages.value.push(...res.data)
      offset.value += limit
    }
  } catch (err) {
    console.error('加载消息失败:', err)
  } finally {
    loadingMessages.value = false
  }
}

// 向上滚动加载逻辑
// 因为容器设置了 flex-col-reverse，所以 scrollTop 越靠近负值(或0取决于浏览器)越是到了历史消息端
// 但比较通用兼容的做法是监听 scroll，距离顶部或底部小于阈值时触发
const handleScroll = (e) => {
  const target = e.target
  // 针对 flex-col-reverse: 滚动到底部实际上是视觉上的最上方(历史消息)
  // 当 scrollHeight - Math.abs(scrollTop) - clientHeight < 50 时加载
  if (target.scrollHeight - Math.abs(target.scrollTop) - target.clientHeight < 50) {
    loadMessages()
  }
}

onMounted(() => {
  fetchAccounts()
})
</script>

<style scoped>
/* 隐藏滚动条但允许滚动（可选） */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}
.overflow-y-auto::-webkit-scrollbar-track {
  background: transparent;
}
.overflow-y-auto::-webkit-scrollbar-thumb {
  background-color: rgba(0,0,0,0.1);
  border-radius: 10px;
}
</style>