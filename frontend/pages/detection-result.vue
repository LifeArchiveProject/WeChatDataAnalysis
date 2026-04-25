<template>
  <div class="detection-result-page relative min-h-screen overflow-hidden px-3 py-4 text-[#000000e6] sm:px-5 sm:py-5">
    <div class="pointer-events-none absolute inset-0 bg-grid-pattern opacity-5"></div>
    <div class="pointer-events-none absolute left-20 top-20 h-72 w-72 rounded-full bg-[#07C160] opacity-5 blur-3xl"></div>
    <div class="pointer-events-none absolute right-20 top-40 h-96 w-96 rounded-full bg-[#10AEEF] opacity-5 blur-3xl"></div>
    <div class="pointer-events-none absolute -bottom-8 left-40 h-80 w-80 rounded-full bg-[#91D300] opacity-5 blur-3xl"></div>

    <main class="relative z-10 mx-auto w-full max-w-6xl">
      <div class="mb-3 flex flex-col gap-3 rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-4 backdrop-blur sm:p-5 lg:flex-row lg:items-start lg:justify-between">
        <div class="min-w-0">
          <p class="text-[12px] font-medium tracking-[0.16em] text-[#07C160]">本地检测</p>
          <h1 class="mt-1.5 text-[30px] font-semibold leading-tight tracking-[-0.04em] text-[#000000e6] sm:text-[38px]">
            {{ loading ? '正在检测微信数据' : detectionResult?.error ? '需要手动指定目录' : '找到可操作的微信账号' }}
          </h1>
          <p class="mt-2 max-w-3xl text-[14px] leading-6 text-[#6B7280]">
            {{ loading ? '正在检查微信安装信息、账号目录和数据库文件。' : detectionResult?.error ? '自动检测没有找到可用数据，可以在下方手动选择 xwechat_files 目录后重试。' : '选择要处理的账号进入解密提取。如果结果不完整，可以手动指定数据根目录后重新检测。' }}
          </p>
        </div>

        <NuxtLink
          to="/"
          class="inline-flex shrink-0 items-center rounded-lg border border-[#CFEEDB] bg-[#F7FDF9]/82 px-2.5 py-1.5 text-xs font-medium text-[#07C160] transition hover:border-[#CFEEDB] hover:bg-[#F7FDF9] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20"
        >
          <svg class="mr-1.5 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          返回首页
        </NuxtLink>
      </div>

      <div v-if="loading" class="flex min-h-[48vh] items-center justify-center">
        <div class="w-full max-w-3xl rounded-lg border border-[#DDF4E7] bg-[#F7FDF9]/76 p-4 backdrop-blur sm:p-5">
          <div class="flex flex-col gap-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#07C160]">
                  <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.5" class="opacity-20"></circle>
                    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"></path>
                  </svg>
                  <span>正在检测</span>
                </div>
                <h3 class="mt-2 text-[22px] font-semibold leading-tight tracking-[-0.03em] text-[#000000e6] sm:text-[28px]">
                  正在寻找可用的微信数据
                </h3>
                <p class="mt-1.5 max-w-2xl text-[14px] leading-6 text-[#6B7280]">
                  这一步会自动检查本机环境、匹配账号并统计数据库文件。检测期间请保持当前页面打开。
                </p>
              </div>
              <span class="hidden shrink-0 rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-medium text-[#07C160] sm:inline-flex">
                自动进行
              </span>
            </div>

            <div class="space-y-2.5 rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-3">
              <div class="h-2 overflow-hidden rounded-full border border-[#DDF4E7] bg-[#F7FCF8]/86">
                <div class="h-full w-1/2 rounded-full bg-[#07C160] animate-pulse"></div>
              </div>

              <div class="grid gap-2 sm:grid-cols-3">
                <div class="rounded-md border border-[#E1EFE5] bg-[#F7FCF8]/86 px-2.5 py-2.5">
                  <div class="flex items-center gap-2 text-[13px] font-medium text-[#000000e6]">
                    <span class="h-1.5 w-1.5 rounded-full bg-[#07C160]"></span>
                    <span>检查环境</span>
                  </div>
                  <p class="mt-1 text-[12px] leading-5 text-[#7F7F7F]">读取微信安装与数据目录</p>
                </div>

                <div class="rounded-md border border-[#E1EFE5] bg-[#F7FCF8]/86 px-2.5 py-2.5">
                  <div class="flex items-center gap-2 text-[13px] font-medium text-[#000000e6]">
                    <span class="h-1.5 w-1.5 rounded-full bg-[#07C160]"></span>
                    <span>匹配账号</span>
                  </div>
                  <p class="mt-1 text-[12px] leading-5 text-[#7F7F7F]">找到可操作的本地账号</p>
                </div>

                <div class="rounded-md border border-[#E1EFE5] bg-[#F7FCF8]/86 px-2.5 py-2.5">
                  <div class="flex items-center gap-2 text-[13px] font-medium text-[#000000e6]">
                    <span class="h-1.5 w-1.5 rounded-full bg-[#07C160]"></span>
                    <span>汇总数据</span>
                  </div>
                  <p class="mt-1 text-[12px] leading-5 text-[#7F7F7F]">整理后续解密所需信息</p>
                </div>
              </div>
            </div>

            <div class="flex flex-col gap-2 border-t border-[#DDF4E7] pt-3 text-[12px] leading-5 text-[#7F7F7F] sm:flex-row sm:items-center sm:justify-between">
              <span>如果等待时间较长，通常是本地文件较多或磁盘读取较慢。</span>
              <span class="font-medium text-[#07C160]">请稍候</span>
            </div>
          </div>
        </div>
      </div>

      <section v-else class="grid gap-4 lg:grid-cols-[0.82fr_1.18fr]">
        <aside class="space-y-3">
          <div
            v-if="detectionResult && !detectionResult.error"
            class="grid grid-cols-1 gap-2.5 sm:grid-cols-3 lg:grid-cols-3"
          >
            <div class="rounded-lg border border-[#CFEEDB] bg-[#EFFAF3]/82 p-3 backdrop-blur">
              <p class="text-[12px] font-medium text-[#5F6F66]">微信版本</p>
              <p class="mt-1.5 truncate text-[22px] font-semibold tracking-[-0.03em] text-[#000000e6]">{{ detectionResult.data?.wechat_version || '未知' }}</p>
            </div>
            <div class="rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-3 backdrop-blur">
              <p class="text-[12px] font-medium text-[#5F6F66]">检测账号</p>
              <p class="mt-1.5 text-[22px] font-semibold tracking-[-0.03em] text-[#000000e6]">{{ detectionResult.data?.total_accounts || 0 }} 个</p>
            </div>
            <div class="rounded-lg border border-[#CFEEDB] bg-[#F1FAF4]/82 p-3 backdrop-blur">
              <p class="text-[12px] font-medium text-[#5F6F66]">数据库文件</p>
              <p class="mt-1.5 text-[22px] font-semibold tracking-[-0.03em] text-[#000000e6]">{{ detectionResult.data?.total_databases || 0 }} 个</p>
            </div>
          </div>

          <div class="rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-4 backdrop-blur sm:p-5">
            <div class="flex items-center justify-between gap-2.5">
              <div>
                <div class="text-[15px] font-medium text-[#000000e6]">手动补充路径</div>
                <p class="mt-1 text-[12px] leading-5 text-[#7F7F7F]">自动检测不完整时，可以指定微信数据根目录重新扫描。</p>
              </div>
            </div>

            <div v-if="customPath" class="mt-3 rounded-md border border-[#E1EFE5] bg-[#F7FCF8]/86 px-2.5 py-2.5">
              <p class="text-[12px] font-medium text-[#5F6F66]">当前检测路径</p>
              <p class="mt-1 break-all font-mono text-[12px] leading-5 text-[#000000d9]">{{ customPath }}</p>
            </div>

            <button
              type="button"
              :disabled="loading"
              class="mt-3 inline-flex w-full items-center justify-center rounded-lg bg-[#07C160] px-3 py-2.5 text-sm font-medium text-white transition hover:bg-[#06AD56] focus:outline-none focus:ring-2 focus:ring-[#07C160]/25 disabled:opacity-50"
              @click="handlePickDirectory"
            >
              <svg v-if="!loading" class="mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <svg v-else class="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 48 48" aria-hidden="true">
                <circle class="opacity-20" cx="24" cy="24" r="18" stroke="currentColor" stroke-width="6"></circle>
                <circle cx="24" cy="24" r="18" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-dasharray="28 72" pathLength="100" transform="rotate(-90 24 24)"></circle>
              </svg>
              {{ loading ? '检测中...' : '选择 xwechat_files 目录' }}
            </button>
          </div>

          <div class="rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-4 backdrop-blur sm:p-5">
            <label for="wechatInstallPath" class="block text-[15px] font-medium text-[#000000e6]">
              微信安装目录
            </label>
            <p class="mt-1 text-[12px] leading-5 text-[#7F7F7F]">
              一键获取数据库密钥会优先使用这里的路径。
            </p>
            <input
              id="wechatInstallPath"
              v-model="wechatInstallPath"
              type="text"
              placeholder="例如: D:\Program Files\Tencent\WeChat 或 D:\Program Files\Tencent\WeChat\Weixin.exe"
              class="mt-3 w-full rounded-lg border border-[#DDEBE0] bg-[#F7FCF8]/86 px-3 py-2 font-mono text-[13px] text-[#000000d9] transition focus:border-[#07C160] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20"
              @blur="persistWechatInstallPath"
            />
            <button
              type="button"
              :disabled="isPickingWechatInstallPath"
              class="mt-2 inline-flex w-full items-center justify-center rounded-lg border border-[#DDEBE0] bg-[#F7FCF8]/86 px-3 py-2 text-sm font-medium text-[#4A4A4A] transition hover:bg-[#F1FAF4] focus:outline-none focus:ring-2 focus:ring-[#07C160]/15 disabled:cursor-wait disabled:opacity-50"
              @click="pickWechatInstallDirectory"
            >
              {{ isPickingWechatInstallPath ? '选择中...' : '选择微信目录' }}
            </button>
          </div>
        </aside>

        <div class="rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-4 backdrop-blur sm:p-5">
          <div v-if="detectionResult?.error" class="flex min-h-[340px] flex-col justify-between gap-4">
            <div>
              <div class="flex items-center gap-2 text-[13px] font-medium text-[#D64A4A]">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>未找到微信数据</span>
              </div>
              <h2 class="mt-3 text-[22px] font-semibold tracking-[-0.03em] text-[#000000e6] sm:text-[28px]">可以手动指定目录重试</h2>
              <p class="mt-2 text-[14px] leading-6 text-[#9C5F5F]">{{ detectionResult.error }}</p>
            </div>

            <div class="rounded-lg border border-[#F4D6D6] bg-[#FFF7F7] p-3 text-[13px] leading-6 text-[#9C5F5F]">
              请尝试选择微信数据根目录，通常名为 <span class="font-mono">xwechat_files</span>。
            </div>

            <button
              type="button"
              class="inline-flex w-full items-center justify-center rounded-lg bg-[#07C160] px-3 py-2.5 text-sm font-medium text-white transition hover:bg-[#06AD56] focus:outline-none focus:ring-2 focus:ring-[#07C160]/25"
              @click="handlePickDirectory"
            >
              重新选择目录
            </button>
          </div>

          <div v-else-if="detectionResult?.data?.accounts && detectionResult.data.accounts.length > 0" class="space-y-3">
            <div class="flex flex-col gap-2 border-b border-[#DDEBE0] pb-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 class="text-[22px] font-semibold tracking-[-0.03em] text-[#000000e6]">可操作的微信账号</h2>
                <p class="mt-1 text-[13px] leading-6 text-[#7F7F7F]">点击解密提取，会将该账号信息带入下一步。</p>
              </div>
              <span class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-medium text-[#07C160]">
                {{ sortedAccounts.length }} 个账号
              </span>
            </div>

            <div class="max-h-[460px] space-y-2.5 overflow-y-auto pr-1">
              <div
                v-for="(account, index) in sortedAccounts"
                :key="index"
                :class="[
                  'rounded-lg border p-3 transition',
                  isCurrentAccount(account.account_name)
                    ? 'border-[#AEE6C4] bg-[#EAF8EF]/86'
                    : 'border-[#E1EFE5] bg-[#F7FCF8]/86 hover:border-[#CFEEDB] hover:bg-[#F1FAF4]'
                ]"
              >
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div class="flex min-w-0 items-center gap-2.5">
                    <template v-if="isCurrentAccount(account.account_name) && currentAccountInfo?.avatar">
                      <img :src="currentAccountInfo.avatar" class="h-12 w-12 shrink-0 rounded-md border border-[#AEE6C4] bg-white object-cover" alt="" />
                    </template>
                    <template v-else>
                      <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86">
                        <span class="text-[17px] font-semibold text-[#07C160]">{{ account.account_name?.charAt(0)?.toUpperCase() || 'U' }}</span>
                      </div>
                    </template>

                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-2">
                        <template v-if="isCurrentAccount(account.account_name) && currentAccountInfo?.nickname">
                          <p class="truncate text-[18px] font-semibold tracking-[-0.03em] text-[#000000e6]">{{ currentAccountInfo.nickname }}</p>
                        </template>
                        <template v-else>
                          <p class="truncate text-[16px] font-semibold text-[#000000e6]">{{ account.account_name || '未知账户' }}</p>
                        </template>
                      </div>

                      <p v-if="isCurrentAccount(account.account_name) && currentAccountInfo?.nickname" class="mt-1 truncate font-mono text-[12px] text-[#7F7F7F]">
                        wxid: {{ account.account_name }}
                      </p>

                      <div class="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-[#7F7F7F]">
                        <span class="rounded-md border border-[#E1EFE5] bg-[#F4FAF6]/82 px-2 py-1">{{ account.database_count }} 个库文件</span>
                        <span v-if="isCurrentAccount(account.account_name)" class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2 py-1 font-medium text-[#07C160]">最近登录</span>
                        <span v-if="account.data_dir" class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2 py-1 text-[#07C160]">路径已确认</span>
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    class="inline-flex shrink-0 items-center justify-center rounded-lg bg-[#07C160] px-3 py-2 text-sm font-medium text-white transition hover:bg-[#06AD56] focus:outline-none focus:ring-2 focus:ring-[#07C160]/25"
                    @click="goToDecrypt(account)"
                  >
                    解密提取
                    <svg class="ml-1.5 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>

                <div v-if="account.data_dir" class="mt-3 border-t border-dashed border-[#DDEBE0] pt-2.5">
                  <p class="truncate font-mono text-[12px] text-[#7F7F7F]" :title="account.data_dir">
                    {{ account.data_dir }}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="flex min-h-[340px] flex-col items-center justify-center rounded-lg border border-[#DDEBE0] bg-[#F7FCF8]/86 p-5 text-center">
            <svg class="mb-3 h-10 w-10 text-[#9CA3AF]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p class="text-[18px] font-semibold tracking-[-0.03em] text-[#000000e6]">没有发现微信数据</p>
            <p class="mt-1.5 max-w-md text-[13px] leading-6 text-[#7F7F7F]">可以尝试手动指定 <span class="font-mono">xwechat_files</span> 文件夹后重新检测。</p>
          </div>
        </div>
      </section>
    </main>
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
