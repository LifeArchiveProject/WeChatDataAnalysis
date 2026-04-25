<template>
  <div class="landing-page relative h-full min-h-0 overflow-hidden px-4 py-6 text-[#000000e6] sm:px-6 sm:py-8">
    <div class="pointer-events-none absolute inset-0 bg-grid-pattern opacity-5"></div>
    <div class="pointer-events-none absolute left-20 top-20 h-72 w-72 rounded-full bg-[#07C160] opacity-5 blur-3xl"></div>
    <div class="pointer-events-none absolute right-20 top-40 h-96 w-96 rounded-full bg-[#10AEEF] opacity-5 blur-3xl"></div>
    <div class="pointer-events-none absolute -bottom-8 left-40 h-80 w-80 rounded-full bg-[#91D300] opacity-5 blur-3xl"></div>

    <main class="relative z-10 mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col justify-center">
      <section class="space-y-5">
        <div class="flex flex-col gap-5 rounded-lg border border-[#EDEDED] bg-white/78 p-6 backdrop-blur sm:p-8 lg:flex-row lg:items-center lg:justify-between">
          <div class="flex items-start gap-4 text-left">
            <img src="/logo.png" alt="微信解密助手Logo" class="h-16 w-16 shrink-0 object-contain" />
            <div>
              <p class="text-[13px] font-medium tracking-[0.16em] text-[#07C160]">本地整理·安心备份</p>
              <h1 class="mt-3 text-[34px] font-semibold leading-tight tracking-[-0.04em] text-[#000000e6] sm:text-[46px]">
                把微信记录留在本地
              </h1>
              <p class="mt-3 max-w-2xl text-[15px] leading-7 text-[#6B7280]">
                从检测开始，再查看聊天、导入备份或导出归档。
              </p>
            </div>
          </div>

          <button
            type="button"
            class="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[#07C160] px-6 py-3 text-[14px] font-medium text-white transition hover:bg-[#06AD56] focus:outline-none focus:ring-2 focus:ring-[#07C160]/25"
            @click="startDetection"
          >
            <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span>开始检测</span>
          </button>
        </div>

        <div class="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
          <button
            type="button"
            class="group min-h-[300px] rounded-lg border border-[#CFEEDB] bg-[#F3FFF8] p-6 text-left transition hover:border-[#AEE6C4] hover:bg-[#EFFAF3] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20 sm:p-8"
            @click="startDetection"
          >
            <div class="flex h-full flex-col justify-between gap-8">
              <div>
                <div class="flex items-center gap-3 text-[#07C160]">
                  <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <span class="text-[13px] font-medium">推荐第一步</span>
                </div>
                <h2 class="mt-5 text-[28px] font-semibold tracking-[-0.03em] text-[#000000e6] sm:text-[36px]">检测本机微信数据</h2>
                <p class="mt-3 max-w-xl text-[14px] leading-7 text-[#6B7280]">
                  找到可用账号、数据库文件和本地路径，后续查看、解密和归档都从这里开始。
                </p>
              </div>

              <div class="flex items-center justify-between border-t border-[#DDF4E7] pt-5">
                <span class="text-[13px] font-medium text-[#07C160]">开始检测</span>
                <svg class="h-5 w-5 text-[#07C160] transition group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </div>
          </button>

          <div class="grid gap-4">
            <NuxtLink
              to="/import"
              class="group rounded-lg border border-[#EDEDED] bg-white/72 p-5 text-left transition hover:border-[#CFEEDB] hover:bg-[#F7FDF9] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20"
            >
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div class="flex items-center gap-2 text-[15px] font-medium text-[#000000e6]">
                    <svg class="h-5 w-5 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>导入备份</span>
                  </div>
                  <p class="mt-2 text-[13px] leading-6 text-[#7F7F7F]">接入已准备好的本地备份目录。</p>
                </div>
                <svg class="mt-1 h-4 w-4 shrink-0 text-[#A1A1AA] transition group-hover:translate-x-0.5 group-hover:text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </NuxtLink>

            <button
              type="button"
              class="group rounded-lg border border-[#EDEDED] bg-white/72 p-5 text-left transition hover:border-[#CFEEDB] hover:bg-[#F7FDF9] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20"
              @click="openExportDialog"
            >
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div class="flex items-center gap-2 text-[15px] font-medium text-[#000000e6]">
                    <svg class="h-5 w-5 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v11" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7.5 10.5L12 15l4.5-4.5" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 19h16" />
                    </svg>
                    <span>导出归档</span>
                  </div>
                  <p class="mt-2 text-[13px] leading-6 text-[#7F7F7F]">打包当前账号的数据库和资源文件。</p>
                </div>
                <svg class="mt-1 h-4 w-4 shrink-0 text-[#A1A1AA] transition group-hover:translate-x-0.5 group-hover:text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>

            <NuxtLink
              to="/chat"
              class="group rounded-lg border border-[#EDEDED] bg-white/72 p-5 text-left transition hover:border-[#CFEEDB] hover:bg-[#F7FDF9] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20"
            >
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div class="flex items-center gap-2 text-[15px] font-medium text-[#000000e6]">
                    <svg class="h-5 w-5 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h8M8 14h5M4 6h16v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
                    </svg>
                    <span>回看聊天</span>
                  </div>
                  <p class="mt-2 text-[13px] leading-6 text-[#7F7F7F]">查看会话、搜索片段，找到需要的内容。</p>
                </div>
                <svg class="mt-1 h-4 w-4 shrink-0 text-[#A1A1AA] transition group-hover:translate-x-0.5 group-hover:text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </NuxtLink>
          </div>
        </div>
      </section>
    </main>

    <GlobalExportDialog :open="exportDialogOpen" @close="closeExportDialog" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useApi } from '~/composables/useApi'
import { DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, readLocalBoolSetting } from '~/lib/desktop-settings'

const { listChatAccounts } = useApi()
const exportDialogOpen = ref(false)

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

const openExportDialog = () => {
  exportDialogOpen.value = true
}

const closeExportDialog = () => {
  exportDialogOpen.value = false
}

const startDetection = async () => {
  await navigateTo('/detection-result')
}
</script>

<style scoped>
.bg-grid-pattern {
  background-image:
    linear-gradient(rgba(7, 193, 96, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(7, 193, 96, 0.1) 1px, transparent 1px);
  background-size: 50px 50px;
}
</style>
