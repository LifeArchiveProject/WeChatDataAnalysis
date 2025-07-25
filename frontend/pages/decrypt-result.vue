<template>
  <div class="min-h-screen relative overflow-hidden flex items-center justify-center">
    <!-- 网格背景 -->
    <div class="absolute inset-0 bg-grid-pattern opacity-5 pointer-events-none"></div>
    
    <!-- 装饰元素 -->
    <div class="absolute top-20 left-20 w-72 h-72 bg-[#07C160] opacity-5 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute top-40 right-20 w-96 h-96 bg-[#10AEEF] opacity-5 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-8 left-40 w-80 h-80 bg-[#91D300] opacity-5 rounded-full blur-3xl pointer-events-none"></div>
    
    <!-- 主要内容 -->
    <div class="relative z-10 w-full max-w-4xl mx-auto px-4">
      <!-- 成功卡片 -->
      <div class="bg-white rounded-2xl border border-[#EDEDED] p-8 text-center">
        <!-- 成功图标 -->
        <div class="mb-4">
          <div class="w-20 h-20 bg-[#07C160]/10 rounded-full flex items-center justify-center mx-auto">
            <svg class="w-10 h-10 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
            </svg>
          </div>
        </div>
        
        <!-- 标题 -->
        <h2 class="text-2xl font-bold text-[#000000e6] mb-6">解密完成！</h2>
        
        <!-- 统计信息 -->
        <div class="flex justify-center gap-8 mb-6">
          <div>
            <div class="text-3xl font-bold text-[#10AEEF]">{{ decryptResult?.total_databases || 0 }}</div>
            <div class="text-sm text-[#7F7F7F]">总数据库</div>
          </div>
          <div class="border-l border-[#EDEDED]"></div>
          <div>
            <div class="text-3xl font-bold text-[#07C160]">{{ decryptResult?.success_count || 0 }}</div>
            <div class="text-sm text-[#7F7F7F]">成功解密</div>
          </div>
          <div class="border-l border-[#EDEDED]"></div>
          <div>
            <div class="text-3xl font-bold text-[#FA5151]">{{ decryptResult?.failure_count || 0 }}</div>
            <div class="text-sm text-[#7F7F7F]">解密失败</div>
          </div>
        </div>
        
        <!-- 输出目录 -->
        <div class="bg-gray-50 rounded-lg p-4 mb-6">
          <div class="flex items-center justify-center">
            <svg class="w-5 h-5 text-[#7F7F7F] mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
            </svg>
            <span class="text-sm text-[#7F7F7F] mr-2">输出目录：</span>
            <code class="bg-white px-3 py-1 rounded text-sm font-mono text-[#000000e6] border border-[#EDEDED]">
              {{ decryptResult?.output_directory || '-' }}
            </code>
            <button v-if="decryptResult?.output_directory" 
              @click="copyPath"
              class="ml-2 text-[#07C160] hover:text-[#06AD56] transition-colors group relative"
              :title="copyTooltip">
              <svg v-if="!copied" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
              </svg>
              <svg v-else class="w-5 h-5 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
              </svg>
              <!-- 复制成功提示 -->
              <span v-if="copied" class="absolute -top-8 left-1/2 transform -translate-x-1/2 bg-[#07C160] text-white text-xs px-2 py-1 rounded whitespace-nowrap">
                已复制
              </span>
            </button>
          </div>
        </div>
        
        <!-- 提示信息 -->
        <p class="text-sm text-[#7F7F7F] mb-6">
          解密后的数据库文件已保存，您可以使用SQLite工具查看
        </p>
        
        <!-- 操作按钮 -->
        <div class="flex justify-center gap-4">
          <NuxtLink to="/decrypt" 
            class="inline-flex items-center px-6 py-3 bg-[#07C160] text-white rounded-lg font-medium hover:bg-[#06AD56] transition-all duration-200">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
            继续解密
          </NuxtLink>
          <a href="https://sqlitebrowser.org/" target="_blank" 
            class="inline-flex items-center px-6 py-3 bg-white text-[#07C160] border border-[#07C160] rounded-lg font-medium hover:bg-gray-50 transition-all duration-200">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            下载SQLite Browser
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const decryptResult = ref(null)
const copied = ref(false)
const copyTooltip = ref('复制路径')

// 复制路径
const copyPath = async () => {
  if (!decryptResult.value?.output_directory) return
  
  try {
    // 获取用户文件夹路径
    // 如果有多个账户，显示基础路径
    // 如果只有一个账户，可以显示具体到账户的路径
    let pathToCopy = decryptResult.value.output_directory
    
    // 如果只解密了一个账户的数据，且有账户结果信息
    if (decryptResult.value.account_results) {
      const accounts = Object.keys(decryptResult.value.account_results)
      if (accounts.length === 1) {
        // 如果只有一个账户，直接显示该账户的输出目录
        const accountName = accounts[0]
        pathToCopy = `${pathToCopy}\\${accountName}`
      }
    }
    
    await navigator.clipboard.writeText(pathToCopy)
    copied.value = true
    copyTooltip.value = '已复制'
    
    // 2秒后重置状态
    setTimeout(() => {
      copied.value = false
      copyTooltip.value = '复制路径'
    }, 2000)
  } catch (err) {
    console.error('复制失败:', err)
  }
}

// 页面加载时获取解密结果
onMounted(() => {
  // 从sessionStorage获取解密结果
  if (process.client && typeof window !== 'undefined') {
    const result = sessionStorage.getItem('decryptResult')
    if (result) {
      try {
        decryptResult.value = JSON.parse(result)
        // 清除sessionStorage
        sessionStorage.removeItem('decryptResult')
      } catch (e) {
        console.error('解析解密结果失败:', e)
      }
    }
  }
  
  // 如果没有解密结果，重定向到解密页面
  if (!decryptResult.value) {
    navigateTo('/decrypt')
  }
})
</script>

<style scoped>
/* 网格背景 */
.bg-grid-pattern {
  background-image: 
    linear-gradient(rgba(7, 193, 96, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(7, 193, 96, 0.1) 1px, transparent 1px);
  background-size: 50px 50px;
}
</style>