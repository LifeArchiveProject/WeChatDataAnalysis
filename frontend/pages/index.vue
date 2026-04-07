<template>
  <div class="landing-page min-h-screen flex items-center justify-center relative overflow-hidden">
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

        <button @click="handleImportClick" 
          class="group inline-flex items-center px-12 py-4 bg-white text-[#91D300] border border-[#91D300] rounded-lg text-lg font-medium hover:bg-[#F7F7F7] transform hover:scale-105 transition-all duration-200">
          <svg class="w-6 h-6 mr-3 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
          </svg>
          <span>数据导入</span>
        </button>
        
        <NuxtLink to="/chat" 
          class="group inline-flex items-center px-12 py-4 bg-white text-[#10AEEF] border border-[#10AEEF] rounded-lg text-lg font-medium hover:bg-[#F7F7F7] transform hover:scale-105 transition-all duration-200">
          <svg class="w-6 h-6 mr-3 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 10h8M8 14h5M4 6h16v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6z"/>
          </svg>
          <span>聊天预览</span>
        </NuxtLink>
      </div>
    </div>

    <!-- 导入预览对话框 -->
    <transition name="fade">
      <div v-if="showImportModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
        <div class="bg-white rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-slide-up">
          <div class="p-8">
            <h3 class="text-xl font-bold text-gray-900 mb-6 flex items-center">
              <svg class="w-6 h-6 mr-2 text-[#91D300]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              确认导入账号
            </h3>
            
            <div v-if="importPreview" class="flex flex-col items-center mb-8">
              <div class="w-24 h-24 rounded-full overflow-hidden border-4 border-[#F7F7F7] shadow-sm mb-4">
                <img :src="importPreview.avatar_url || '/Contact.png'" class="w-full h-full object-cover" alt="头像">
              </div>
              <div class="text-center">
                <div class="text-lg font-bold text-gray-900">{{ importPreview.nick }}</div>
                <div class="text-sm text-gray-500 font-mono mt-1">{{ importPreview.username }}</div>
              </div>
              
              <div class="mt-6 w-full bg-gray-50 rounded-xl p-4 text-sm text-gray-600 space-y-2">
                <div class="flex justify-between items-center">
                  <span>包含数据库</span>
                  <span class="text-[#07C160] font-medium">是</span>
                </div>
                <div class="flex justify-between items-center">
                  <span>包含资源文件</span>
                  <span :class="importPreview.has_resource ? 'text-[#07C160]' : 'text-gray-400'" class="font-medium">
                    {{ importPreview.has_resource ? '是' : '否' }}
                  </span>
                </div>
              </div>
            </div>

            <div v-if="importError" class="mb-6 p-4 bg-red-50 border border-red-100 rounded-xl flex items-start">
              <svg class="w-5 h-5 text-red-500 mr-2 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <span class="text-sm text-red-600">{{ importError }}</span>
            </div>

            <div class="flex gap-4">
              <button @click="showImportModal = false" 
                class="flex-1 px-6 py-3 border border-gray-200 text-gray-600 rounded-xl font-medium hover:bg-gray-50 transition-colors">
                取消
              </button>
              <button @click="confirmImport" :disabled="importing"
                class="flex-1 px-6 py-3 bg-[#91D300] text-white rounded-xl font-medium hover:bg-[#82BD00] disabled:opacity-50 transition-colors flex items-center justify-center">
                <svg v-if="importing" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                确认导入
              </button>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '~/composables/useApi'
import { DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, readLocalBoolSetting } from '~/lib/desktop-settings'

const { listChatAccounts, importDecryptedPreview, importDecrypted } = useApi()

// 导入相关
const showImportModal = ref(false)
const importing = ref(false)
const importPreview = ref(null)
const importError = ref('')
const selectedImportPath = ref('')

onMounted(async () => {
  if (!process.client || typeof window === 'undefined') return

  const enabled = readLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, false)
  if (!enabled) return

  try {
    const resp = await listChatAccounts()
    const accounts = resp?.accounts || []
    if (accounts.length) {
      await navigateTo('/chat', { replace: true })
    }
  } catch {}
})

const isDesktopShell = () => {
  if (!process.client || typeof window === 'undefined') return false
  return !!window.wechatDesktop?.__brand
}

// 导入点击
const handleImportClick = async () => {
  let path = ''
  
  if (isDesktopShell()) {
    try {
      const res = await window.wechatDesktop.chooseDirectory({
        title: '选择解密数据所在目录'
      })
      if (!res || res.canceled || !res.filePaths?.length) return
      path = res.filePaths[0]
    } catch (e) {
      console.error('选择目录失败:', e)
      return
    }
  } else {
    // 网页版演示，弹出提示让输入（通常在本地开发使用）
    path = window.prompt('请输入已解密目录的绝对路径:')
    if (!path) return
  }

  selectedImportPath.value = path
  importError.value = ''
  importPreview.value = null
  showImportModal.value = true
  
  try {
    const res = await importDecryptedPreview({ import_path: path })
    importPreview.value = res
  } catch (e) {
    importError.value = e.message || '目录格式不正确，请确保包含 databases 目录和 account.json'
  }
}

// 确认导入
const confirmImport = async () => {
  if (!selectedImportPath.value) return
  
  importing.value = true
  importError.value = ''
  
  try {
    const res = await importDecrypted({ import_path: selectedImportPath.value })
    if (res.status === 'success') {
      // 导入成功后，可以跳转到聊天界面
      await navigateTo('/chat')
    } else {
      importError.value = res.message || '导入失败'
    }
  } catch (e) {
    importError.value = e.message || '导入过程中发生错误'
  } finally {
    importing.value = false
  }
}

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
