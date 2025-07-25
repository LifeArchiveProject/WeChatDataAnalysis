<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden">
    <!-- 渐变背景 - 与首页保持一致 -->
    <div class="absolute inset-0 bg-gradient-to-br from-[#F7F7F7] via-[#e6f7f0] to-[#F7F7F7]"></div>
    
    <!-- 装饰性圆形渐变 -->
    <div class="absolute top-1/4 -left-32 w-96 h-96 bg-gradient-to-br from-[#07C160] to-[#91D300] opacity-10 rounded-full blur-3xl"></div>
    <div class="absolute bottom-1/4 -right-32 w-96 h-96 bg-gradient-to-br from-[#10AEEF] to-[#07C160] opacity-10 rounded-full blur-3xl"></div>
    
    <!-- 返回按钮 -->
    <NuxtLink to="/" class="absolute top-8 left-8 text-gray-600 hover:text-gray-900 transition-colors p-2 hover:bg-white/50 rounded-lg">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
      </svg>
    </NuxtLink>
    
    <!-- 主要内容区域 -->
    <div class="relative z-10 text-center max-w-2xl mx-auto px-6">
      <!-- 未检测状态 -->
      <div v-if="!detectionResult && !loading" class="animate-fade-in">
        <div class="mb-8">
          <div class="inline-flex items-center justify-center w-24 h-24 bg-gradient-to-br from-green-400 to-green-600 rounded-2xl shadow-lg mb-6">
            <svg class="w-14 h-14 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
          </div>
          <h1 class="text-3xl font-bold text-gray-800 mb-3">微信检测</h1>
          <p class="text-lg text-gray-600 mb-8">扫描系统中的微信安装信息和数据库文件</p>
        </div>
        
        <button 
          @click="startDetection" 
          class="group inline-flex items-center px-10 py-4 bg-gradient-to-r from-green-500 to-green-600 text-white rounded-xl text-lg font-semibold shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200"
        >
          <svg class="w-6 h-6 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
          </svg>
          开始检测
        </button>
      </div>
      
      <!-- 检测中状态 -->
      <div v-if="loading" class="animate-fade-in">
        <div class="mb-8">
          <div class="relative inline-block mb-6">
            <div class="w-24 h-24 bg-gradient-to-br from-green-400 to-green-600 rounded-2xl shadow-lg flex items-center justify-center">
              <svg class="w-14 h-14 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
              </svg>
            </div>
            <div class="absolute inset-0 w-24 h-24 rounded-2xl border-4 border-green-300 border-t-green-600 animate-spin"></div>
          </div>
          <h2 class="text-2xl font-bold text-gray-800 mb-3">正在检测中...</h2>
          <p class="text-gray-600">请稍候，正在扫描您的系统</p>
        </div>
      </div>
      
      <!-- 检测结果 -->
      <transition name="slide-fade">
        <div v-if="detectionResult" class="animate-fade-in">
          <div class="mb-8">
            <div class="inline-flex items-center justify-center w-24 h-24 bg-gradient-to-br from-green-400 to-green-600 rounded-2xl shadow-lg mb-6">
              <svg class="w-14 h-14 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
            </div>
            <h2 class="text-3xl font-bold text-gray-800 mb-3">检测完成</h2>
            <p class="text-lg text-gray-600">发现 <span class="font-semibold text-green-600">{{ detectionResult.statistics.total_user_accounts }}</span> 个微信账户</p>
          </div>
          
          <!-- 结果卡片 -->
          <div class="bg-white/80 backdrop-blur-sm rounded-2xl shadow-lg p-6 mb-6 text-left">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div class="text-center">
                <div class="text-3xl font-bold text-green-600 mb-1">{{ detectionResult.statistics.total_user_accounts }}</div>
                <div class="text-sm text-gray-600">账户数量</div>
              </div>
              <div class="text-center">
                <div class="text-3xl font-bold text-blue-600 mb-1">{{ detectionResult.statistics.total_databases }}</div>
                <div class="text-sm text-gray-600">数据库文件</div>
              </div>
              <div class="text-center">
                <div class="text-xl font-semibold text-gray-800 mb-1">{{ detectionResult.data.wechat_version || '未知' }}</div>
                <div class="text-sm text-gray-600">微信版本</div>
              </div>
            </div>
            
            <!-- 账户列表 -->
            <div v-if="detectionResult.data.user_accounts.length > 0" class="space-y-3">
              <h3 class="text-sm font-semibold text-gray-700 mb-2">检测到的账户：</h3>
              <div v-for="(account, index) in detectionResult.data.user_accounts.slice(0, 3)" :key="index" 
                   class="bg-gray-50 rounded-lg p-3 text-sm">
                <div class="flex items-center justify-between">
                  <span class="font-medium text-gray-800">{{ account.wxid }}</span>
                  <button @click="copyText(account.db_storage_path)" class="text-gray-400 hover:text-green-600 transition-colors">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                    </svg>
                  </button>
                </div>
              </div>
              <p v-if="detectionResult.data.user_accounts.length > 3" class="text-xs text-gray-500 text-center">
                还有 {{ detectionResult.data.user_accounts.length - 3 }} 个账户...
              </p>
            </div>
          </div>
          
          <!-- 操作按钮 -->
          <div class="flex flex-col sm:flex-row gap-4 justify-center">
            <NuxtLink to="/decrypt" 
              class="group inline-flex items-center justify-center px-8 py-3 bg-gradient-to-r from-green-500 to-green-600 text-white rounded-xl text-base font-semibold shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200">
              <svg class="w-5 h-5 mr-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
              </svg>
              前往解密
              <svg class="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
            </NuxtLink>
            
            <button @click="resetDetection" 
              class="inline-flex items-center justify-center px-8 py-3 bg-white text-gray-700 border border-gray-300 rounded-xl text-base font-medium hover:bg-gray-50 transition-colors">
              重新检测
            </button>
          </div>
        </div>
      </transition>
      
      <!-- 错误提示 -->
      <transition name="fade">
        <div v-if="error" class="absolute bottom-8 left-1/2 transform -translate-x-1/2 bg-red-50 text-red-600 px-6 py-3 rounded-lg shadow-lg animate-shake">
          <div class="flex items-center">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            {{ error }}
          </div>
        </div>
      </transition>
    </div>
    
    <!-- 网格背景装饰 -->
    <svg class="absolute inset-0 w-full h-full opacity-50" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
          <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(0,0,0,0.03)" stroke-width="1"/>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#grid)" />
    </svg>
  </div>
</template>

<style scoped>
/* 动画效果 */
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

@keyframes slide-fade {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes shake {
  0%, 100% { transform: translateX(-50%); }
  10%, 30%, 50%, 70%, 90% { transform: translateX(calc(-50% - 5px)); }
  20%, 40%, 60%, 80% { transform: translateX(calc(-50% + 5px)); }
}

.animate-fade-in {
  animation: fade-in 0.8s ease-out;
}

.slide-fade-enter-active {
  animation: slide-fade 0.5s ease-out;
}

.animate-shake {
  animation: shake 0.5s ease-in-out;
}

/* 页面过渡动画 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>

<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '~/composables/useApi'

const { detectWechat } = useApi()

const loading = ref(false)
const error = ref('')
const detectionResult = ref(null)

// 页面加载时检查是否有存储的检测结果
onMounted(() => {
  // 确保在客户端环境执行
  if (process.client && typeof window !== 'undefined') {
    const storedResult = sessionStorage.getItem('detectionResult')
    if (storedResult) {
      try {
        detectionResult.value = JSON.parse(storedResult)
        sessionStorage.removeItem('detectionResult') // 清除存储的结果
      } catch (err) {
        console.error('解析存储的检测结果失败:', err)
      }
    }
  }
})

// 开始检测
const startDetection = async () => {
  loading.value = true
  error.value = ''
  detectionResult.value = null
  
  try {
    const result = await detectWechat()
    if (result.status === 'success') {
      detectionResult.value = result
    } else {
      error.value = result.error || '检测失败，请重试'
    }
  } catch (err) {
    error.value = err.message || '检测过程中发生错误'
  } finally {
    loading.value = false
  }
}

// 重置检测
const resetDetection = () => {
  detectionResult.value = null
  error.value = ''
}

// 复制文本到剪贴板
const copyText = async (text) => {
  if (!text) return
  
  try {
    await navigator.clipboard.writeText(text)
    // 可以添加一个提示
  } catch (err) {
    console.error('复制失败:', err)
  }
}
</script>