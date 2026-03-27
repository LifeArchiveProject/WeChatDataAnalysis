<template>
  <div class="biz-page h-screen flex overflow-hidden" style="background-color: var(--app-shell-bg)">

    <div class="w-[300px] lg:w-[320px] bg-white border-r border-gray-200 flex flex-col flex-shrink-0 z-10">
      <div class="p-3 border-b border-gray-200" style="background-color: var(--app-surface-muted)">
        <div class="contact-search-wrapper flex-1">
          <svg class="contact-search-icon" fill="none" stroke="currentColor" viewBox="0 0 16 16">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />
          </svg>
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
          <span class="text-sm text-gray-400">加载中...</span>
        </div>
        <div v-else>
          <div
              v-for="item in filteredAccounts"
              :key="item.username"
              @click="selectAccount(item)"
              class="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
              :class="{ 'bg-[#F2F2F2]': selectedAccount?.username === item.username }"
          >
            <img
                :src="item.avatar || defaultAvatar"
                class="w-10 h-10 rounded-md object-cover bg-gray-200 flex-shrink-0"
                @error="(e) => e.target.src = defaultAvatar"
             alt=""/>
            <div class="flex-1 min-w-0">
              <h3 class="text-sm text-gray-900 truncate">{{ item.name || item.username }}</h3>
            </div>
            <div v-if="item.username === 'gh_3dfda90e39d6'" class="text-xs text-[#03C160] bg-[#03C160]/10 px-1.5 py-0.5 rounded">
              官方
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="flex-1 flex flex-col min-h-0 min-w-0 bg-[#F5F5F5]">
      <div v-if="selectedAccount" class="flex-1 flex flex-col min-h-0 relative">
        <div class="h-14 border-b border-gray-200 bg-[#F5F5F5] flex items-center px-5 shrink-0 z-10">
          <h2 class="text-base text-gray-900">{{ selectedAccount.name }}</h2>
        </div>

        <div
            class="flex-1 overflow-y-auto px-4 py-6 flex flex-col-reverse"
            @scroll="handleScroll"
            ref="messageListRef"
        >
          <div v-if="!hasMore" class="text-center text-xs text-gray-400 py-4 w-full">没有更多消息了</div>
          <div v-if="loadingMessages" class="text-center text-xs text-gray-400 py-4 w-full">正在加载...</div>

          <div class="w-full max-w-[400px] mx-auto flex flex-col-reverse gap-6">
            <div v-for="msg in messages" :key="msg.local_id" class="w-full">

              <div v-if="selectedAccount.username === 'gh_3dfda90e39d6'" class="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
                <div class="flex items-center text-gray-500 text-sm mb-5">
                  <img v-if="msg.merchant_icon" :src="msg.merchant_icon" class="w-6 h-6 rounded-full mr-2 object-cover"  alt=""/>
                  <div v-else class="w-6 h-6 rounded-full mr-2 bg-green-100 flex items-center justify-center text-green-600">¥</div>
                  <span>{{ msg.merchant_name || '微信支付' }}</span>
                </div>
                <div class="text-center mb-6">
                  <h3 class="text-[22px] font-medium text-gray-900 mb-1">{{ msg.title }}</h3>
                </div>
                <div class="text-[13px] text-gray-500 whitespace-pre-wrap leading-relaxed">
                  {{ msg.description }}
                </div>
                <div class="mt-4 pt-3 border-t border-gray-100 text-[12px] text-gray-400 text-right">
                  {{ msg.formatted_time }}
                </div>
              </div>

              <div v-else class="bg-white rounded-xl shadow-sm overflow-hidden border border-gray-100">
                <a :href="msg.url" target="_blank" class="block relative group cursor-pointer">
                  <img :src="msg.cover || defaultImage" class="w-full h-[180px] object-cover bg-gray-100"  alt=""/>
                  <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3 pt-8">
                    <h3 class="text-white text-[15px] font-medium leading-snug line-clamp-2 group-hover:underline">
                      {{ msg.title }}
                    </h3>
                  </div>
                </a>

                <div v-if="msg.des" class="px-4 py-3 text-[13px] text-gray-500 border-b border-gray-50">
                  {{ msg.des }}
                </div>

                <div v-if="msg.content_list && msg.content_list.length > 0" class="flex flex-col">
                  <a
                      v-for="(item, idx) in msg.content_list"
                      :key="idx"
                      :href="item.url"
                      target="_blank"
                      class="flex items-center justify-between p-3 border-t border-gray-100 hover:bg-gray-50 cursor-pointer group"
                  >
                    <span class="text-[14px] text-gray-800 leading-snug line-clamp-2 pr-3 group-hover:underline">
                      {{ item.title }}
                    </span>
                    <img :src="item.cover" class="w-12 h-12 rounded object-cover flex-shrink-0 bg-gray-100 border border-gray-100"  alt=""/>
                  </a>
                </div>
              </div>

            </div>
          </div>
        </div>

      </div>

      <div v-else class="flex-1 flex items-center justify-center">
        <div class="text-center">
          <div class="w-20 h-20 mx-auto mb-5 rounded-2xl bg-gray-200/50 flex items-center justify-center">
            <svg class="w-10 h-10 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5L18.5 7H20" />
            </svg>
          </div>
          <p class="text-sm text-gray-400">请选择一个服务号查看消息</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

// 状态
const accounts = ref([])
const loadingAccounts = ref(false)
const searchQuery = ref('')
const selectedAccount = ref(null)

const messages = ref([])
const loadingMessages = ref(false)
const offset = ref(0)
const limit = 20
const hasMore = ref(true)

const messageListRef = ref(null)

// 默认占位图
const defaultAvatar = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgdmlld0JveD0iMCAwIDQwIDQwIj48cmVjdCB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIGZpbGw9IiNlNWU3ZWIiLz48L3N2Zz4='
const defaultImage = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MDAiIGhlaWdodD0iMTgwIj48cmVjdCB3aWR0aD0iNDAwIiBoZWlnaHQ9IjE4MCIgZmlsbD0iI2Y1ZjVmNSIvPjwvc3ZnPg=='

// 获取账号列表，并将微信支付置顶
const fetchAccounts = async () => {
  loadingAccounts.value = true
  try {
    const res = await api.listBizAccounts()
    if (res && res.data) {
      // 提取微信支付
      const payAccount = res.data.find(a => a.username === 'gh_3dfda90e39d6')
      const otherAccounts = res.data.filter(a => a.username !== 'gh_3dfda90e39d6')

      const sortedList = []
      if (payAccount) {
        // 如果后端没有返回名字，可以手动补齐
        payAccount.name = '微信支付'
        sortedList.push(payAccount)
      } else {
        // 如果后端列表里没有，但你想强行显示，也可以造一个假的
        sortedList.push({ username: 'gh_3dfda90e39d6', name: '微信支付', avatar: '' })
      }

      accounts.value = [...sortedList, ...otherAccounts]
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