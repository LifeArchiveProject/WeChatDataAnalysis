<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden">
    <!-- 网格背景 -->
    <div class="absolute inset-0 bg-grid-pattern opacity-5"></div>
    
    <!-- 装饰元素 -->
    <div class="absolute top-20 left-20 w-72 h-72 bg-[#07C160] opacity-5 rounded-full blur-3xl"></div>
    <div class="absolute top-40 right-20 w-96 h-96 bg-[#10AEEF] opacity-5 rounded-full blur-3xl"></div>
    <div class="absolute -bottom-8 left-40 w-80 h-80 bg-[#91D300] opacity-5 rounded-full blur-3xl"></div>
    
    <!-- 主要内容区域 -->
    <div class="relative z-10 text-center">
      <!-- Logo和标题部分 -->
      <div class="mb-12 animate-fade-in">
        <!-- Logo -->
        <div class="flex justify-center mb-8">
          <img src="/logo.png" alt="微信解密助手Logo" class="w-48 h-48 object-contain">
        </div>
        
        <h1 class="text-5xl font-bold text-[#000000e6] mb-4">
          <span class="bg-gradient-to-r from-[#07C160] to-[#10AEEF] bg-clip-text text-transparent">微信</span>
          <span class="text-[#000000e6]">解密助手</span>
        </h1>
        <p class="text-xl text-[#7F7F7F] font-normal">轻松解锁你的聊天记录</p>
      </div>
      
      <!-- 主要按钮 -->
      <div class="flex flex-col sm:flex-row gap-4 justify-center animate-slide-up">
        <button @click="startDetection" 
          class="group inline-flex items-center px-12 py-4 bg-[#07C160] text-white rounded-lg text-lg font-medium hover:bg-[#06AD56] transform hover:scale-105 transition-all duration-200">
          <svg class="w-6 h-6 mr-3 group-hover:rotate-12 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>
          <span>开始检测</span>
        </button>
        
        <NuxtLink to="/decrypt" 
          class="group inline-flex items-center px-12 py-4 bg-white text-[#07C160] border border-[#07C160] rounded-lg text-lg font-medium hover:bg-[#F7F7F7] transform hover:scale-105 transition-all duration-200">
          <svg class="w-6 h-6 mr-3 group-hover:-rotate-12 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z"/>
          </svg>
          <span>直接解密</span>
        </NuxtLink>
        
        <NuxtLink to="/chat" 
          class="group inline-flex items-center px-12 py-4 bg-white text-[#10AEEF] border border-[#10AEEF] rounded-lg text-lg font-medium hover:bg-[#F7F7F7] transform hover:scale-105 transition-all duration-200">
          <svg class="w-6 h-6 mr-3 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 10h8M8 14h5M4 6h16v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6z"/>
          </svg>
          <span>聊天预览</span>
        </NuxtLink>

        <NuxtLink to="/wrapped" 
          class="group inline-flex items-center px-12 py-4 bg-white text-[#B37800] border border-[#F2AA00] rounded-lg text-lg font-medium hover:bg-[#F7F7F7] transform hover:scale-105 transition-all duration-200">
          <svg class="w-6 h-6 mr-3 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <rect x="4" y="4" width="16" height="16" rx="2" stroke-width="2.5" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 16v-5" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 16v-8" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M16 16v-3" />
          </svg>
          <span>年度总结</span>
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useApi } from '~/composables/useApi'
import { DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, readLocalBoolSetting } from '~/utils/desktop-settings'

onMounted(async () => {
  if (!process.client || typeof window === 'undefined') return

  const enabled = readLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, false)
  if (!enabled) return

  try {
    const api = useApi()
    const resp = await api.listChatAccounts()
    const accounts = resp?.accounts || []
    if (accounts.length) {
      await navigateTo('/chat', { replace: true })
    }
  } catch {}
})

// 开始检测并跳转到结果页面
const startDetection = async () => {
  // 直接跳转到检测结果页面，让该页面处理检测
  await navigateTo('/detection-result')
}
</script>

<style scoped>
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fade-in 0.8s ease-out;
}

.animate-slide-up {
  animation: slide-up 0.8s ease-out 0.3s both;
}

/* 网格背景 */
.bg-grid-pattern {
  background-image: 
    linear-gradient(rgba(7, 193, 96, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(7, 193, 96, 0.1) 1px, transparent 1px);
  background-size: 50px 50px;
}
</style>
