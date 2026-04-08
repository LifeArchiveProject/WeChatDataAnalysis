<template>
  <div class="import-page min-h-screen flex items-center justify-center py-8">
    
    <div class="max-w-2xl mx-auto px-6 w-full">
      <div class="bg-white rounded-3xl border border-[#EDEDED] shadow-sm overflow-hidden">
        <div class="p-8 md:p-12">
          <!-- 标题部分 -->
          <div class="flex items-center mb-8">
            <div class="w-14 h-14 bg-[#91D300] rounded-2xl flex items-center justify-center mr-5 shadow-sm">
              <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
            </div>
            <div>
              <h2 class="text-2xl font-bold text-[#000000e6]">数据导入</h2>
              <p class="text-[#7F7F7F] mt-1">导入已解密的数据库备份目录</p>
            </div>
          </div>

          <div class="bg-blue-50 border border-blue-100 rounded-2xl p-6 mb-8">
            <h3 class="text-blue-800 font-bold mb-3 flex items-center">
              <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              标准目录结构要求
            </h3>
            <ul class="text-sm text-blue-700 space-y-2 list-disc list-inside opacity-90">
              <li><strong>预期目标：</strong>请选择形如 <strong>/output/wxid_xxxxx/</strong> 这一级目录</li>
              <li><strong>databases/</strong> 目录：存放扁平化的 .db 文件</li>
              <li><strong>account.json</strong> 文件：系统会自动生成</li>
            </ul>
          </div>

          <!-- 初始状态：选择目录 -->
          <div v-if="!importPreview && !importError" class="flex flex-col items-center justify-center py-12 border-2 border-dashed border-[#EDEDED] rounded-3xl hover:border-[#91D300] transition-colors cursor-pointer group" @click="handlePickDirectory">
            <div class="w-20 h-20 bg-gray-50 rounded-full flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
              <svg class="w-10 h-10 text-gray-400 group-hover:text-[#91D300]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
              </svg>
            </div>
            <div class="text-[#000000e6] font-medium text-lg">点击选择备份目录</div>
            <p class="text-[#7F7F7F] text-sm mt-2">支持原生目录选择器</p>
          </div>

          <!-- 预览状态：显示账号信息 -->
          <div v-if="importPreview" class="animate-fade-in">
            <div class="flex flex-col items-center py-8 bg-[#FBFBFB] rounded-3xl border border-[#EDEDED] mb-8">
              <div class="w-28 h-28 rounded-full overflow-hidden border-4 border-white shadow-md mb-5">
                <img :src="importPreview.avatar_url || '/Contact.png'" class="w-full h-full object-cover" alt="头像">
              </div>
              <div class="text-center">
                <div class="text-xl font-bold text-gray-900">{{ importPreview.nick }}</div>
                <div class="text-sm text-gray-500 font-mono mt-1 bg-white px-3 py-1 rounded-full border border-[#EDEDED] inline-block">{{ importPreview.username }}</div>
              </div>
              
              <div class="mt-8 flex gap-6">
                <div class="flex items-center text-sm text-gray-600">
                  <div class="w-2 h-2 rounded-full bg-[#07C160] mr-2"></div>
                  数据库已就绪
                </div>
                <div class="flex items-center text-sm text-gray-600">
                  <div class="w-2 h-2 rounded-full mr-2" :class="importPreview.has_resource ? 'bg-[#07C160]' : 'bg-gray-300'"></div>
                  资源文件{{ importPreview.has_resource ? '已发现' : '未发现' }}
                </div>
              </div>
            </div>

            <div class="flex gap-4">
              <button @click="resetImport" 
                class="flex-1 px-8 py-4 border border-[#EDEDED] text-gray-600 rounded-2xl font-bold hover:bg-gray-50 transition-all">
                重新选择
              </button>
              <button @click="confirmImport" :disabled="importing"
                class="flex-[2] px-8 py-4 bg-[#91D300] text-white rounded-2xl font-bold hover:bg-[#82BD00] shadow-lg shadow-[#91D300]/20 disabled:opacity-50 transition-all flex items-center justify-center transform hover:scale-[1.02] active:scale-[0.98]">
                <svg v-if="importing" class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span v-if="!importing">确认导入此账号</span>
                <span v-else>正在导入数据...</span>
              </button>
            </div>
          </div>

          <!-- 错误状态 -->
          <div v-if="importError" class="animate-fade-in">
            <div class="p-6 bg-red-50 border border-red-100 rounded-2xl flex items-start mb-8">
              <svg class="w-6 h-6 text-red-500 mr-3 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div>
                <p class="font-bold text-red-800 mb-1">目录校验失败</p>
                <p class="text-sm text-red-600">{{ importError }}</p>
              </div>
            </div>
            <button @click="resetImport" 
              class="w-full px-8 py-4 bg-white border border-[#EDEDED] text-[#07C160] rounded-2xl font-bold hover:bg-gray-50 transition-all flex items-center justify-center">
              <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              重新选择目录
            </button>
          </div>

          <!-- 返回首页 -->
          <div class="mt-12 text-center">
            <NuxtLink to="/" class="text-[#7F7F7F] hover:text-[#07C160] text-sm transition-colors inline-flex items-center">
              <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/>
              </svg>
              返回首页
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {ref} from 'vue'
import {useApi} from '~/composables/useApi'

const importing = ref(false)
const importPreview = ref(null)
const importError = ref('')
const selectedImportPath = ref('')

const isDesktopShell = () => {
  if (!process.client || typeof window === 'undefined') return false
  return !!window.wechatDesktop?.__brand
}

const resetImport = () => {
  importPreview.value = null
  importError.value = ''
  selectedImportPath.value = ''
}

const { importDecryptedPreview, importDecrypted, pickSystemDirectory } = useApi()

const handlePickDirectory = async () => {
  let path = ''

  if (isDesktopShell()) {
    try {
      const res = await window.wechatDesktop.chooseDirectory({
        title: '请选择解密输出目录 (如: output/wxid_xxxxx)'
      })
      if (!res || res.canceled || !res.filePaths?.length) return
      path = res.filePaths[0]
    } catch (e) {
      console.error('选择目录失败:', e)
      return
    }
  } else {
    try {
      const res = await pickSystemDirectory({ title: '请选择解密输出目录 (需选到 wxid_xxx 层级)' })
      if (!res || !res.path) return
      path = res.path
    } catch (e) {
      console.error('唤起目录选择器失败:', e)
      path = window.prompt('无法唤起选择器，请输入已解密目录的绝对路径:')
      if (!path) return
    }
  }

  if (path && !path.includes('wxid_')) {
    const isOk = window.confirm(`你选择的目录为：\n${path}\n\n该目录似乎不符合 "wxid_xxxxx" 的格式。确定要继续吗？`)
    if (!isOk) return
  }

  selectedImportPath.value = path
  importError.value = ''
  importPreview.value = null

  try {
    importPreview.value = await importDecryptedPreview({import_path: path})
  } catch (e) {
    importError.value = e.message || '目录格式不正确，请确保包含 databases 目录和 account.json'
  }
}

const confirmImport = async () => {
  if (!selectedImportPath.value) return
  
  importing.value = true
  importError.value = ''
  
  try {
    const res = await importDecrypted({ import_path: selectedImportPath.value })
    if (res.status === 'success') {
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
</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
