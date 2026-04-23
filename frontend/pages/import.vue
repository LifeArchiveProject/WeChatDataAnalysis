<template>
  <div class="import-page min-h-screen relative overflow-hidden">
    <div class="absolute inset-0 bg-grid-pattern opacity-5 pointer-events-none"></div>

    <div class="relative z-10 mx-auto flex min-h-screen w-full max-w-3xl items-center justify-center px-4 py-6 sm:px-6 sm:py-8">
      <div class="w-full rounded-[28px] border border-[#EDEDED] bg-white/92 backdrop-blur-sm">
        <div class="px-5 py-5 sm:px-7 sm:py-7">
          <div class="mb-5 flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#07C160]/10 text-[#07C160]">
                <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </div>
              <div class="min-w-0">
                <p class="text-[11px] uppercase tracking-[0.12em] text-[#7F7F7F]">Import backup</p>
                <h1 class="mt-1 text-[24px] font-semibold leading-none text-[#000000e6]">数据导入</h1>
                <p class="mt-2 text-sm text-[#7F7F7F]">导入已解密的微信备份目录，确认账号后即可写入当前工具。</p>
              </div>
            </div>

            <NuxtLink
              to="/"
              class="inline-flex shrink-0 items-center rounded-lg px-3 py-1.5 text-xs font-medium text-[#07C160] transition-colors hover:bg-[#F3FBF6] hover:text-[#06AD56]"
            >
              <svg class="mr-1 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              返回首页
            </NuxtLink>
          </div>

          <div class="mb-5 rounded-[22px] border border-[#E8EFE8] bg-[#F8FBF8] px-4 py-4">
            <div class="flex items-center gap-2 text-[13px] font-semibold text-[#000000d9]">
              <svg class="h-4 w-4 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>目录要求</span>
            </div>
            <div class="mt-3 grid gap-2 sm:grid-cols-3">
              <div class="rounded-2xl border border-white bg-white/80 px-3 py-3">
                <p class="text-[11px] uppercase tracking-[0.08em] text-[#7F7F7F]">Target</p>
                <p class="mt-1 text-sm leading-6 text-[#000000d9]">请选择 `output / wxid_xxxxx` 这一层目录。</p>
              </div>
              <div class="rounded-2xl border border-white bg-white/80 px-3 py-3">
                <p class="text-[11px] uppercase tracking-[0.08em] text-[#7F7F7F]">Database</p>
                <p class="mt-1 text-sm leading-6 text-[#000000d9]">目录内需要包含 `databases/`，用于存放 `.db` 文件。</p>
              </div>
              <div class="rounded-2xl border border-white bg-white/80 px-3 py-3">
                <p class="text-[11px] uppercase tracking-[0.08em] text-[#7F7F7F]">Account</p>
                <p class="mt-1 text-sm leading-6 text-[#000000d9]">`account.json` 会作为账号识别与信息校验依据。</p>
              </div>
            </div>
          </div>

          <div v-if="!importPreview && !importError && !importing" class="animate-fade-in">
            <div
              class="group cursor-pointer rounded-[24px] border border-dashed border-[#D8E5DA] bg-[#FCFDFC] px-6 py-10 text-center transition-colors duration-200 hover:border-[#07C160] hover:bg-white"
              @click="handlePickDirectory"
            >
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-[#07C160] ring-1 ring-[#EDEDED]">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
              </div>
              <h3 class="mt-4 text-lg font-semibold text-[#000000e6]">选择解密备份目录</h3>
              <p class="mt-2 text-sm text-[#7F7F7F]">建议直接选择 `wxid_xxxxx` 层级，减少后续校验失败。</p>
              <div class="mt-5 inline-flex items-center rounded-full bg-[#07C160] px-4 py-2 text-sm font-medium text-white transition-colors duration-200 group-hover:bg-[#06AD56]">
                点击开始选择
              </div>
              <p class="mt-4 text-xs text-[#A3A3A3]">桌面端优先使用系统目录选择器，异常时会自动回退到手动输入。</p>
            </div>
          </div>

          <div v-if="importing" class="animate-fade-in">
            <div class="rounded-[24px] border border-[#EDEDED] bg-[#FCFDFC] px-5 py-8 sm:px-6">
              <div class="mx-auto flex w-fit items-center gap-2 rounded-full bg-[#07C160]/10 px-3 py-1 text-xs font-medium text-[#07C160]">
                <span class="inline-flex h-2 w-2 rounded-full bg-current animate-pulse"></span>
                正在导入
              </div>

              <div class="mt-5 text-center">
                <p class="text-xl font-semibold text-[#000000e6]">{{ importMessage }}</p>
                <p class="mt-2 text-sm text-[#7F7F7F]">请保持程序运行，导入完成后会自动进入聊天页面。</p>
              </div>

              <div class="mt-6 overflow-hidden rounded-full bg-[#EDF3EE]">
                <div
                  class="h-2 rounded-full bg-[#07C160] transition-all duration-500"
                  :style="{ width: `${Math.min(Math.max(importProgress, 0), 100)}%` }"
                ></div>
              </div>

              <div class="mt-3 flex items-center justify-between text-xs text-[#7F7F7F]">
                <span>已连接导入任务</span>
                <span>{{ importProgress }}%</span>
              </div>
            </div>
          </div>

          <div v-if="importPreview && !importing" class="animate-fade-in space-y-4">
            <div class="rounded-[24px] border border-[#EDEDED] bg-[#FCFDFC] px-5 py-5 sm:px-6">
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex min-w-0 items-center gap-4">
                  <div class="h-16 w-16 shrink-0 overflow-hidden rounded-2xl border border-[#EDEDED] bg-white">
                    <img :src="importPreview.avatar_url || '/Contact.png'" class="h-full w-full object-cover" alt="Avatar" />
                  </div>

                  <div class="min-w-0">
                    <p class="text-[11px] uppercase tracking-[0.12em] text-[#7F7F7F]">Detected account</p>
                    <div class="mt-1 truncate text-xl font-semibold text-[#000000e6]">{{ importPreview.nick || '未命名账号' }}</div>
                    <div class="mt-2 inline-flex max-w-full items-center rounded-full border border-[#EDEDED] bg-white px-3 py-1 text-xs font-mono text-[#7F7F7F]">
                      <span class="truncate">{{ importPreview.username }}</span>
                    </div>
                  </div>
                </div>

                <div class="inline-flex w-fit items-center rounded-full bg-[#07C160]/10 px-3 py-1 text-xs font-medium text-[#07C160]">
                  可导入
                </div>
              </div>

              <div v-if="selectedImportPath" class="mt-4 rounded-[18px] border border-[#EDEDED] bg-white px-3 py-3">
                <p class="text-[11px] uppercase tracking-[0.12em] text-[#7F7F7F]">Import path</p>
                <p class="mt-1 break-all text-sm text-[#000000d9]">{{ selectedImportPath }}</p>
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <span class="inline-flex items-center gap-2 rounded-full border border-[#EDEDED] bg-white px-3 py-1.5 text-xs text-[#4A4A4A]">
                  <span class="h-2 w-2 rounded-full bg-[#07C160]"></span>
                  数据库已就绪
                </span>
                <span class="inline-flex items-center gap-2 rounded-full border border-[#EDEDED] bg-white px-3 py-1.5 text-xs text-[#4A4A4A]">
                  <span class="h-2 w-2 rounded-full" :class="importPreview.has_resource ? 'bg-[#07C160]' : 'bg-[#C9D2CB]'"></span>
                  资源文件{{ importPreview.has_resource ? '已发现' : '未发现' }}
                </span>
              </div>
            </div>

            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
              <button
                class="inline-flex items-center justify-center rounded-2xl border border-[#E2E2E2] bg-white px-4 py-3 text-sm font-medium text-[#4A4A4A] transition-colors hover:bg-[#F8F8F8]"
                @click="handlePickDirectory"
              >
                重新选择目录
              </button>
              <button
                :disabled="importing"
                class="inline-flex items-center justify-center rounded-2xl bg-[#07C160] px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-[#06AD56] disabled:cursor-not-allowed disabled:bg-[#8FD9AE]"
                @click="confirmImport"
              >
                确认导入此账号
              </button>
            </div>
          </div>

          <div v-if="importError && !importing" class="animate-fade-in space-y-4">
            <div class="rounded-[22px] border border-[#F4D6D6] bg-[#FFF7F7] px-5 py-5">
              <div class="flex items-start gap-3">
                <div class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-[#E05A5A] ring-1 ring-[#F0D7D7]">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div class="min-w-0">
                  <p class="text-base font-semibold text-[#B64545]">导入失败</p>
                  <p class="mt-1 text-sm leading-6 text-[#9C5F5F]">{{ importError }}</p>
                </div>
              </div>

              <div v-if="selectedImportPath" class="mt-4 rounded-[18px] border border-[#F1E3E3] bg-white/80 px-3 py-3">
                <p class="text-[11px] uppercase tracking-[0.12em] text-[#B26B6B]">Current path</p>
                <p class="mt-1 break-all text-sm text-[#7A4B4B]">{{ selectedImportPath }}</p>
              </div>
            </div>

            <button
              class="inline-flex w-full items-center justify-center rounded-2xl border border-[#E2E2E2] bg-white px-4 py-3 text-sm font-medium text-[#4A4A4A] transition-colors hover:bg-[#F8F8F8]"
              @click="retryPickDirectory"
            >
              重新选择目录
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onUnmounted, ref } from 'vue'
import { useApi } from '~/composables/useApi'
import { useApiBase } from '~/composables/useApiBase'

const importing = ref(false)
const importProgress = ref(0)
const importMessage = ref('正在准备...')
const importPreview = ref(null)
const importError = ref('')
const selectedImportPath = ref('')

let eventSource = null

const closeEventSource = () => {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

onUnmounted(() => {
  closeEventSource()
})

const isDesktopShell = () => {
  if (!process.client || typeof window === 'undefined') return false
  return !!window.wechatDesktop?.__brand
}

const resetImport = () => {
  closeEventSource()
  importPreview.value = null
  importError.value = ''
  selectedImportPath.value = ''
  importing.value = false
  importProgress.value = 0
  importMessage.value = '正在准备...'
}

const { importDecryptedPreview, pickSystemDirectory } = useApi()
const apiBase = useApiBase()

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
    const isOk = window.confirm(`你选择的目录为：
${path}

该目录似乎不符合 "wxid_xxxxx" 的格式。确定要继续吗？`)
    if (!isOk) return
  }

  selectedImportPath.value = path
  importError.value = ''
  importPreview.value = null

  try {
    importPreview.value = await importDecryptedPreview({ import_path: path })
  } catch (e) {
    importError.value = e.message || '目录格式不正确，请确保包含 databases 目录和 account.json'
  }
}

const retryPickDirectory = async () => {
  resetImport()
  await handlePickDirectory()
}

const confirmImport = async () => {
  if (!selectedImportPath.value) return

  importing.value = true
  importError.value = ''
  importProgress.value = 0
  importMessage.value = '启动导入程序...'

  const url = new URL(`${apiBase.replace(/\/$/, '')}/import_decrypted`, window.location.origin)
  url.searchParams.set('import_path', selectedImportPath.value)

  closeEventSource()
  eventSource = new EventSource(url.toString())

  eventSource.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data)

      if (data.type === 'progress') {
        importProgress.value = data.percent || 0
        importMessage.value = data.message || '正在处理...'
      } else if (data.type === 'complete') {
        importProgress.value = 100
        importMessage.value = '导入完成！'
        closeEventSource()

        setTimeout(async () => {
          await navigateTo('/chat')
        }, 1000)
      } else if (data.type === 'error') {
        importError.value = data.message || '导入失败'
        importing.value = false
        closeEventSource()
      }
    } catch (e) {
      console.error('解析 SSE 数据失败:', e)
    }
  }

  eventSource.onerror = (e) => {
    console.error('EventSource 错误:', e)
    importError.value = '与服务器连接断开或发生错误'
    importing.value = false
    closeEventSource()
  }
}
</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.35s ease-out;
}

.bg-grid-pattern {
  background-image:
    linear-gradient(rgba(7, 193, 96, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(7, 193, 96, 0.08) 1px, transparent 1px);
  background-size: 32px 32px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
