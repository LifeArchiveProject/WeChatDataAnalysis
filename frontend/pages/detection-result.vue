<template>
  <div class="detection-result-page min-h-screen relative overflow-hidden">
    <!-- 网格背景 -->
    <div class="absolute inset-0 bg-grid-pattern opacity-5 pointer-events-none"></div>
    
    <!-- 装饰元素 -->
    <div class="absolute top-20 left-20 w-72 h-72 bg-[#07C160] opacity-5 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute top-40 right-20 w-96 h-96 bg-[#10AEEF] opacity-5 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-8 left-40 w-80 h-80 bg-[#91D300] opacity-5 rounded-full blur-3xl pointer-events-none"></div>
    
    <!-- 主要内容 -->
    <div class="relative z-10 w-full max-w-5xl mx-auto px-4 sm:px-5 py-6 sm:py-8 animate-fade-in">
      <!-- 顶部操作栏 -->
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-[22px] font-bold leading-none">
            <span class="bg-gradient-to-r from-[#07C160] to-[#10AEEF] bg-clip-text text-transparent">检测结果</span>
          </h2>
        </div>
        <NuxtLink to="/" 
          class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs text-[#07C160] hover:text-[#06AD56] hover:bg-white/80 font-medium transition-colors">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/>
          </svg>
          返回首页
        </NuxtLink>
      </div>

      <div
        v-if="detectionResult && !loading && !detectionResult.error"
        class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 mb-4"
      >
        <div class="bg-white/90 backdrop-blur rounded-xl px-4 py-3 border border-[#EDEDED]">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-[11px] tracking-[0.08em] uppercase text-[#7F7F7F]">微信版本</p>
              <p class="mt-1 text-lg font-semibold text-[#000000e6] truncate">{{ detectionResult.data?.wechat_version || '未知' }}</p>
            </div>
            <div class="w-9 h-9 shrink-0 bg-[#07C160]/10 rounded-lg flex items-center justify-center">
              <svg class="w-[18px] h-[18px] text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
            </div>
          </div>
        </div>

        <div class="bg-white/90 backdrop-blur rounded-xl px-4 py-3 border border-[#EDEDED]">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-[11px] tracking-[0.08em] uppercase text-[#7F7F7F]">检测账号</p>
              <p class="mt-1 text-lg font-semibold text-[#000000e6]">{{ detectionResult.data?.total_accounts || 0 }} 个</p>
            </div>
            <div class="w-9 h-9 shrink-0 bg-[#10AEEF]/10 rounded-lg flex items-center justify-center">
              <svg class="w-[18px] h-[18px] text-[#10AEEF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283-.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/>
              </svg>
            </div>
          </div>
        </div>

        <div class="bg-white/90 backdrop-blur rounded-xl px-4 py-3 border border-[#EDEDED]">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-[11px] tracking-[0.08em] uppercase text-[#7F7F7F]">数据库文件</p>
              <p class="mt-1 text-lg font-semibold text-[#000000e6]">{{ detectionResult.data?.total_databases || 0 }} 个</p>
            </div>
            <div class="w-9 h-9 shrink-0 bg-[#91D300]/10 rounded-lg flex items-center justify-center">
              <svg class="w-[18px] h-[18px] text-[#91D300]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"/>
              </svg>
            </div>
          </div>
        </div>
      </div>

      <!-- 第一步检测：数据目录与微信安装目录都在这里设置 -->
      <div v-if="!loading" class="bg-white/90 backdrop-blur rounded-xl p-3.5 md:p-4 border border-[#EDEDED] mb-4 space-y-3">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h3 class="text-[13px] font-semibold text-[#000000e6] flex items-center">
              未找到想要的账号？
<!--            <span class="ml-2 px-2 py-0.5 bg-gray-100 text-gray-500 rounded text-xs font-normal">深度检测兜底</span>-->
            </h3>
            <p class="text-[11px] text-[#7F7F7F] mt-1">
              <span v-if="customPath">当前指定检测路径：<span class="font-mono bg-gray-50 px-1 rounded text-[#000000e6]">{{ customPath }}</span></span>
              <span v-else>如果自动检测漏了，您可以手动指定微信数据根目录 (通常名为 xwechat_files) 让系统重新扫描。</span>
            </p>
          </div>
          <button @click="handlePickDirectory" :disabled="loading"
                  class="shrink-0 px-4 py-2.5 bg-[#07C160] text-white rounded-xl text-xs font-medium hover:bg-[#06AD56] focus:ring-2 focus:ring-[#07C160] focus:ring-offset-1 disabled:opacity-50 transition-all duration-200 flex items-center justify-center">
            <svg v-if="!loading" class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
            </svg>
            <svg v-else class="w-4 h-4 mr-2 animate-spin" fill="none" viewBox="0 0 48 48" aria-hidden="true">
              <circle class="opacity-20" cx="24" cy="24" r="18" stroke="currentColor" stroke-width="6"></circle>
              <circle
                cx="24"
                cy="24"
                r="18"
                stroke="currentColor"
                stroke-width="6"
                stroke-linecap="round"
                stroke-dasharray="28 72"
                pathLength="100"
                transform="rotate(-90 24 24)"
              ></circle>
            </svg>
            {{ loading ? '检测中...' : '手动选择目录检测' }}
          </button>
        </div>

        <div class="pt-3 border-t border-[#F3F3F3]">
          <label for="wechatInstallPath" class="block text-[13px] font-medium text-[#000000e6] mb-2">
            微信安装目录（第一步先填这里）
          </label>
          <div class="flex flex-col lg:flex-row gap-3">
            <input
              id="wechatInstallPath"
              v-model="wechatInstallPath"
              type="text"
              placeholder="例如: D:\Program Files\Tencent\WeChat 或 D:\Program Files\Tencent\WeChat\Weixin.exe"
              class="flex-1 px-4 py-2.5 bg-white border border-[#EDEDED] rounded-lg font-mono text-[13px] focus:outline-none focus:ring-2 focus:ring-[#07C160] focus:border-transparent transition-all duration-200"
              @blur="persistWechatInstallPath"
            />
            <button
              type="button"
              @click="pickWechatInstallDirectory"
              :disabled="isPickingWechatInstallPath"
              class="shrink-0 px-4 py-2.5 bg-white border border-[#EDEDED] text-[#000000e6] rounded-xl text-xs font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-wait transition-all duration-200"
            >
              {{ isPickingWechatInstallPath ? '选择中...' : '选择微信目录' }}
            </button>
          </div>
          <p class="text-[11px] text-[#7F7F7F] mt-2">
            一键获取数据库密钥会优先使用这里填写的路径。支持填写安装目录，也支持直接填写 <span class="font-mono">Weixin.exe</span> / <span class="font-mono">WeChat.exe</span> 路径。
          </p>
        </div>
      </div>
      
      <!-- 主内容区域 -->
      <div :class="loading ? 'flex min-h-[52vh] items-center justify-center' : ''">
        <!-- 检测中状态 -->
        <div v-if="loading" class="w-full max-w-3xl rounded-[24px] border border-[#EDEDED] bg-white/92 px-5 py-6 sm:px-8 sm:py-7">
          <div class="flex flex-col items-center text-center">
            <div class="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-[#07C160]/10">
              <span class="absolute inset-0 rounded-2xl border border-[#07C160]/10"></span>
              <svg class="h-5 w-5 animate-spin text-[#07C160]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.5" class="opacity-20"></circle>
                <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"></path>
              </svg>
            </div>

            <div class="mt-4 flex flex-wrap items-center justify-center gap-2">
              <span class="inline-flex items-center rounded-full bg-[#07C160]/10 px-2.5 py-1 text-[11px] font-medium text-[#07C160]">
                检测中
              </span>
              <span class="text-[11px] text-[#7F7F7F]">正在自动读取本机微信环境</span>
            </div>

            <h3 class="mt-3 text-[20px] font-semibold text-[#000000e6] leading-tight">正在检查账号与数据库文件</h3>
            <p class="mt-2 max-w-[560px] text-[13px] leading-6 text-[#7F7F7F]">
              会依次确认微信安装信息、最近登录账号以及可用数据库，通常几秒内完成。
            </p>

            <div class="mt-5 h-1.5 w-full max-w-[620px] overflow-hidden rounded-full bg-[#F3F4F6]">
              <div class="h-full w-2/5 rounded-full bg-gradient-to-r from-[#07C160] via-[#34D17A] to-[#8CE0AF] animate-pulse"></div>
            </div>

            <div class="mt-5 flex flex-wrap items-center justify-center gap-2.5">
              <div class="inline-flex items-center gap-2 rounded-full border border-[#EDEDED] bg-[#FAFAFA] px-3 py-2 text-[12px] text-[#000000d9]">
                <span class="h-2 w-2 rounded-full bg-[#07C160] animate-pulse"></span>
                <span>安装信息</span>
              </div>
              <div class="inline-flex items-center gap-2 rounded-full border border-[#EDEDED] bg-[#FAFAFA] px-3 py-2 text-[12px] text-[#000000d9]">
                <span class="h-2 w-2 rounded-full bg-[#07C160] animate-pulse"></span>
                <span>账号匹配</span>
              </div>
              <div class="inline-flex items-center gap-2 rounded-full border border-[#EDEDED] bg-[#FAFAFA] px-3 py-2 text-[12px] text-[#000000d9]">
                <span class="h-2 w-2 rounded-full bg-[#07C160] animate-pulse"></span>
                <span>数据库汇总</span>
              </div>
            </div>
          </div>
        </div>

        <!-- detection result content -->
        <div v-if="detectionResult && !loading">
          <!-- 错误信息 -->
          <div v-if="detectionResult.error" class="bg-red-50 rounded-2xl border border-red-100 p-6">
            <div class="flex items-center">
              <svg class="w-8 h-8 text-red-500 mr-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div>
                <p class="text-lg font-bold text-red-800">未找到微信数据</p>
                <p class="text-red-600 mt-1 text-sm">{{ detectionResult.error }}</p>
              </div>
            </div>
          </div>
          
          <!-- 成功结果 -->
          <div v-else class="space-y-3">
            <!-- 账户列表 -->
            <div v-if="detectionResult.data?.accounts && detectionResult.data.accounts.length > 0"
                 class="bg-white/92 backdrop-blur rounded-2xl border border-[#EDEDED] overflow-hidden">
              <div class="px-4 py-3 border-b border-[#EDEDED] bg-[#fafafa] flex items-center justify-between">
                <h3 class="text-[15px] font-semibold text-[#000000e6]">可操作的微信账户</h3>
                <span class="text-[11px] text-gray-500">点击解密即可提取数据</span>
              </div>
              <div class="divide-y divide-[#EDEDED] max-h-[420px] overflow-y-auto">
                <div v-for="(account, index) in sortedAccounts" :key="index"
                     :class="['px-4 py-3.5 transition-all duration-200 relative overflow-hidden', isCurrentAccount(account.account_name) ? 'bg-[#07C160]/5 border border-[#07C160]/20' : 'hover:bg-[#F9F9F9]']">

                  <div v-if="isCurrentAccount(account.account_name)" class="absolute top-0 right-0 bg-gradient-to-l from-[#07C160]/20 to-transparent px-3 py-1 rounded-bl-xl flex items-center">
    <span class="text-xs text-[#07C160] font-bold flex items-center">
      <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
      最近登录账户
    </span>
                  </div>

                  <div class="flex items-center justify-between gap-3 mt-1">
                    <div class="flex-1">
                      <div class="flex items-center">
                        <template v-if="isCurrentAccount(account.account_name) && currentAccountInfo?.avatar">
                          <img :src="currentAccountInfo.avatar" class="w-12 h-12 rounded-xl border-2 border-[#07C160]/30 mr-3 object-cover bg-white"  alt=""/>
                        </template>
                        <template v-else>
                          <div class="w-12 h-12 bg-gradient-to-br from-[#07C160]/10 to-[#91D300]/10 rounded-xl flex items-center justify-center mr-3">
                            <span class="text-[#07C160] font-bold text-lg">{{ account.account_name?.charAt(0)?.toUpperCase() || 'U' }}</span>
                          </div>
                        </template>

                        <div>
                          <div class="flex flex-col">
                            <template v-if="isCurrentAccount(account.account_name) && currentAccountInfo?.nickname">
                              <p class="text-lg font-bold text-[#000000e6] leading-tight">{{ currentAccountInfo.nickname }}</p>
                              <p class="text-[11px] text-[#7F7F7F] mt-0.5 font-mono">wxid: {{ account.account_name }}</p>
                            </template>
                            <template v-else>
                              <p class="text-[15px] font-semibold text-[#000000e6]">{{ account.account_name || '未知账户' }}</p>
                            </template>
                          </div>

                          <div class="flex items-center mt-1.5 space-x-3 text-[12px] text-[#7F7F7F]">
            <span class="flex items-center">
              <svg class="w-4 h-4 mr-1 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"/>
              </svg>
              {{ account.database_count }} 个库文件
            </span>
                            <span v-if="account.data_dir" class="flex items-center">
              <svg class="w-4 h-4 mr-1 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
              </svg>
              路径已确认
            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <button @click="goToDecrypt(account)"
                            class="inline-flex items-center px-4 py-2 bg-[#07C160] text-white rounded-lg font-semibold hover:bg-[#06AD56] hover:-translate-y-0.5 transition-all duration-200 text-xs shrink-0 z-10">
                      解密提取
                      <svg class="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                      </svg>
                    </button>
                  </div>

                  <div class="mt-3 pt-2.5 border-t border-dashed border-gray-200 text-sm text-gray-400">
                    <p v-if="account.data_dir" class="font-mono text-[11px] truncate" title="复制路径">
                      📂 {{ account.data_dir }}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <!-- 无账户提示 -->
            <div v-else class="bg-white rounded-2xl p-8 text-center border border-[#EDEDED]">
              <svg class="w-12 h-12 mx-auto text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <p class="text-base text-[#000000e6] font-medium">没有在这台设备上发现微信数据</p>
              <p class="text-sm text-gray-500 mt-2">您可以尝试通过上方的按钮手动指定 "xwechat_files" 文件夹路径。</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {computed, onMounted, ref} from 'vue'
import {useApi} from '~/composables/useApi'
import {normalizeWechatInstallPath, readStoredWechatInstallPath, writeStoredWechatInstallPath} from '~/lib/wechat-install-path'
import {useAppStore} from '~/stores/app'

const { detectWechat, pickSystemDirectory } = useApi()
const appStore = useAppStore()
const loading = ref(false)
const detectionResult = ref(null)
const customPath = ref('')
const wechatInstallPath = ref('')
const isPickingWechatInstallPath = ref(false)
const STORAGE_KEY = 'wechat_data_root_path'

const isDesktopShell = () => {
  if (!process.client || typeof window === 'undefined') return false
  return !!window.wechatDesktop?.__brand
}

// 唤起目录选择器并自动检测
const handlePickDirectory = async () => {
  let path = ''

  if (isDesktopShell()) {
    try {
      const res = await window.wechatDesktop.chooseDirectory({
        title: '请选择微信数据根目录 (通常名为 xwechat_files)'
      })
      if (!res || res.canceled || !res.filePaths?.length) return
      path = res.filePaths[0]
    } catch (e) {
      console.error('桌面端选择目录失败:', e)
      return
    }
  } else {
    try {
      const res = await pickSystemDirectory({
        title: '请选择微信数据根目录 (通常名为 xwechat_files)'
      })
      if (!res || !res.path) return // 用户取消
      path = res.path
    } catch (e) {
      console.error('通过API唤起系统目录选择器失败:', e)
      path = window.prompt('无法直接唤起窗口，请输入 xwechat_files 目录的绝对路径:')
      if (!path) return
    }
  }

  if (path) {
    customPath.value = path
    // 选完后立刻启动重新检测
    startDetection()
  }
}

const persistWechatInstallPath = () => {
  const normalized = normalizeWechatInstallPath(wechatInstallPath.value)
  wechatInstallPath.value = normalized
  writeStoredWechatInstallPath(normalized)
}

const pickWechatInstallDirectory = async () => {
  if (isPickingWechatInstallPath.value) return
  isPickingWechatInstallPath.value = true

  try {
    let path = ''

    if (isDesktopShell()) {
      const res = await window.wechatDesktop.chooseDirectory({
        title: '请选择微信安装目录'
      })
      if (!res || res.canceled || !res.filePaths?.length) return
      path = res.filePaths[0]
    } else {
      try {
        const res = await pickSystemDirectory({
          title: '请选择微信安装目录',
          initial_dir: normalizeWechatInstallPath(wechatInstallPath.value)
        })
        if (!res || !res.path) return
        path = res.path
      } catch (e) {
        console.error('通过API唤起微信安装目录选择器失败:', e)
        path = window.prompt('无法直接唤起窗口，请输入微信安装目录或 Weixin.exe / WeChat.exe 的绝对路径:')
        if (!path) return
      }
    }

    const normalized = normalizeWechatInstallPath(path)
    if (!normalized) return
    wechatInstallPath.value = normalized
    persistWechatInstallPath()
  } catch (e) {
    console.error('选择微信安装目录失败:', e)
  } finally {
    isPickingWechatInstallPath.value = false
  }
}

// 计算属性：将当前登录账号排在第一位
const sortedAccounts = computed(() => {
  if (!detectionResult.value?.data?.accounts) return []
  const accounts = [...detectionResult.value.data.accounts]

  const current = detectionResult.value.data?.current_account
  const currentTargetName = current?.matched_folder || current?.current_account

  if (!currentTargetName) return accounts

  // 置顶最近登录账号
  return accounts.sort((a, b) => {
    if (a.account_name === currentTargetName) return -1
    if (b.account_name === currentTargetName) return 1
    return 0
  })
})


const currentAccountInfo = computed(() => {
  return detectionResult.value?.data?.current_account || null
})

// 开始检测
const startDetection = async () => {
  loading.value = true
  
  try {
    const params = {}
    if (customPath.value && customPath.value.trim()) {
      params.data_root_path = customPath.value.trim()
    }
    
    // 检测微信安装信息
    let result = await detectWechat(params)

    // 如果用户提供/缓存的路径不可用，自动回退到“自动检测”
    const hasCustomPath = !!(params.data_root_path && String(params.data_root_path).trim())
    const accounts0 = Array.isArray(result?.data?.accounts) ? result.data.accounts : []

    if (hasCustomPath && (result?.status !== 'success' || accounts0.length === 0)) {
      try {
        const fallback = await detectWechat({})
        const accounts1 = Array.isArray(fallback?.data?.accounts) ? fallback.data.accounts : []
        if (fallback?.status === 'success' && accounts1.length > 0) {
          result = fallback
          if (process.client) {
            try {
              localStorage.removeItem(STORAGE_KEY)
            } catch {}
          }
          customPath.value = ''
        }
      } catch {}
    }

    detectionResult.value = result

    if (result.status === 'success') {
      const current = result?.data?.current_account || null
      if (current) {
        appStore.setCurrentAccount(current)
      }

      if (process.client) {
        try {
          let toSave = String(customPath.value || '').trim()
          if (!toSave) {
            const accounts = Array.isArray(result?.data?.accounts) ? result.data.accounts : []
            for (const acc of accounts) {
              const dataDir = String(acc?.data_dir || '').trim()
              if (!dataDir) continue
              toSave = dataDir.replace(/[\\/][^\\/]+$/, '')
              if (toSave) break
            }
          }
          if (toSave) {
            localStorage.setItem(STORAGE_KEY, toSave)
            customPath.value = toSave
          }
        } catch {}
      }
    }
  } catch (err) {
    console.error('检测过程中发生错误:', err)
    detectionResult.value = {
      status: 'error',
      error: err.message || '未在常规路径下扫描到您的微信数据。'
    }
  } finally {
    loading.value = false
  }
}

// 跳转到解密页面并传递账户信息
const goToDecrypt = (account) => {
  persistWechatInstallPath()

  if (process.client && typeof window !== 'undefined') {
    sessionStorage.setItem('selectedAccount', JSON.stringify({
      account_name: account.account_name,
      data_dir: account.data_dir,
      database_count: account.database_count,
      databases: account.databases
    }))
  }
  navigateTo('/decrypt')
}

// 判断是否为当前登录账号
const isCurrentAccount = (accountName) => {
  if (!detectionResult.value?.data?.current_account) {
    return false
  }
  const current = detectionResult.value.data.current_account
  // 支持严格匹配或通过后缀兼容的匹配
  return accountName === current.matched_folder || accountName === current.current_account
}

// 页面加载时自动检测
onMounted(() => {
  if (process.client) {
    try {
      const saved = String(localStorage.getItem(STORAGE_KEY) || '').trim()
      if (saved) customPath.value = saved
    } catch {}
    wechatInstallPath.value = readStoredWechatInstallPath()
  }
  startDetection()
})
</script>
