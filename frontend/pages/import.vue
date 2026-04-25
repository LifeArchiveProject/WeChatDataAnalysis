<template>
  <div class="import-page relative min-h-screen overflow-hidden px-4 py-5 text-[#000000e6] sm:px-6 sm:py-5">
    <div class="pointer-events-none absolute inset-0 bg-grid-pattern opacity-5"></div>
    <div class="pointer-events-none absolute left-20 top-20 h-72 w-72 rounded-full bg-[#07C160] opacity-5 blur-3xl"></div>
    <div class="pointer-events-none absolute right-20 top-40 h-96 w-96 rounded-full bg-[#10AEEF] opacity-5 blur-3xl"></div>
    <div class="pointer-events-none absolute -bottom-8 left-40 h-80 w-80 rounded-full bg-[#91D300] opacity-5 blur-3xl"></div>

    <main class="relative z-10 mx-auto flex min-h-[calc(100vh-40px)] w-full max-w-6xl flex-col justify-start">
      <div class="mb-4 flex items-start justify-between gap-4 rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-5 backdrop-blur">
        <div class="min-w-0">
          <p class="text-[12px] font-medium tracking-[0.16em] text-[#07C160]">导入备份</p>
          <h1 class="mt-2 text-[30px] font-semibold leading-tight tracking-[-0.04em] text-[#000000e6] sm:text-[38px]">
            接入已准备好的本地数据
          </h1>
          <p class="mt-3 max-w-2xl text-[14px] leading-7 text-[#6B7280]">
            选择已解密的微信备份目录，先检查账号与文件结构，确认后再导入到本地数据区。
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

      <section class="grid gap-5 lg:grid-cols-[0.82fr_1.18fr]">
        <aside class="space-y-4">
          <div class="rounded-lg border border-[#CFEEDB] bg-[#EFFAF3]/82 p-5 backdrop-blur">
            <div class="flex items-center gap-2 text-[15px] font-medium text-[#000000e6]">
              <svg class="h-5 w-5 text-[#07C160]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <span>选择哪个目录</span>
            </div>
            <p class="mt-3 text-[13px] leading-6 text-[#6B7280]">
              建议直接选择账号目录。如果是 wxdump 导出，且 output 下只有一个账号，也可以选择 output 根目录。
            </p>
            <div class="mt-4 flex flex-wrap gap-2">
              <span class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-mono text-[#4A4A4A]">wxid_xxxxx/</span>
              <span class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-mono text-[#4A4A4A]">databases/</span>
              <span class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-mono text-[#4A4A4A]">database/</span>
              <span class="rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-mono text-[#4A4A4A]">media/</span>
            </div>
          </div>

          <div class="rounded-lg border border-[#CFEEDB] bg-[#F1FAF4]/82 p-5 backdrop-blur">
            <div class="text-[15px] font-medium text-[#000000e6]">导入流程</div>
            <div class="mt-4 space-y-3">
              <div class="flex gap-3">
                <span class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[#CFEEDB] text-[11px] font-medium text-[#07C160]">1</span>
                <div>
                  <div class="text-[13px] font-medium text-[#000000d9]">选择目录</div>
                  <p class="mt-2 text-[12px] leading-5 text-[#7F7F7F]">使用系统目录选择器定位备份。</p>
                </div>
              </div>
              <div class="flex gap-3">
                <span class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[#CFEEDB] text-[11px] font-medium text-[#07C160]">2</span>
                <div>
                  <div class="text-[13px] font-medium text-[#000000d9]">预览确认</div>
                  <p class="mt-2 text-[12px] leading-5 text-[#7F7F7F]">先识别账号、数据库和资源文件。</p>
                </div>
              </div>
              <div class="flex gap-3">
                <span class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[#CFEEDB] text-[11px] font-medium text-[#07C160]">3</span>
                <div>
                  <div class="text-[13px] font-medium text-[#000000d9]">执行导入</div>
                  <p class="mt-2 text-[12px] leading-5 text-[#7F7F7F]">如果账号已存在，会先备份旧数据。</p>
                </div>
              </div>
            </div>
          </div>

          <div class="rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-4 text-[12px] leading-6 text-[#5F6F66] backdrop-blur">
            <span class="font-medium text-[#2F6F4A]">提示：</span>
            导入会复制数据到应用的本地数据区，不会直接在原备份目录上修改。
          </div>
        </aside>

        <div class="rounded-lg border border-[#DDEBE0] bg-[#F4FAF6]/82 p-5 backdrop-blur">
          <div v-if="!importPreview && !importError && !importing && !importComplete" class="animate-fade-in">
            <div class="flex min-h-[340px] flex-col justify-between gap-5">
              <div>
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#07C160]">
                  <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  <span>第一步</span>
                </div>
                <h2 class="mt-4 text-[24px] font-semibold tracking-[-0.03em] text-[#000000e6] sm:text-[30px]">选择备份目录</h2>
                <p class="mt-3 max-w-xl text-[14px] leading-7 text-[#6B7280]">
                  点击下方按钮后，选择已解密的账号目录。系统会先做结构检查，不会立即导入。
                </p>
              </div>

              <button
                type="button"
                class="group flex min-h-[132px] cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-[#BFE6CF] bg-[#F3FFF8] px-5 py-6 text-center transition hover:border-[#07C160] hover:bg-[#EFFAF3] focus:outline-none focus:ring-2 focus:ring-[#07C160]/20"
                @click="handlePickDirectory"
              >
                <svg class="h-8 w-8 text-[#07C160] transition group-hover:-translate-y-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                <span class="mt-4 text-[15px] font-medium text-[#000000e6]">打开目录选择器</span>
                <span class="mt-2 text-[12px] leading-5 text-[#7F7F7F]">建议选到 wxid_xxxxx 账号层级</span>
              </button>
            </div>
          </div>

          <div v-if="importing" class="animate-fade-in">
            <div class="flex min-h-[340px] flex-col justify-between gap-5">
              <div>
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#07C160]">
                  <span class="h-2 w-2 rounded-full bg-[#07C160] animate-pulse"></span>
                  <span>正在导入</span>
                </div>
                <h2 class="mt-4 text-[24px] font-semibold tracking-[-0.03em] text-[#000000e6] sm:text-[30px]">{{ importMessage }}</h2>
                <p class="mt-3 text-[14px] leading-7 text-[#6B7280]">请保持程序运行，导入完成后可以进入聊天页面查看。</p>
              </div>

              <div class="rounded-lg border border-[#CFEEDB] bg-[#EAF8EF]/82 p-4 sm:p-5">
                <div class="h-2 overflow-hidden rounded-full border border-[#DDF4E7] bg-[#F7FCF8]/86">
                  <div
                    class="h-full rounded-full bg-[#07C160] transition-all duration-500"
                    :style="{ width: `${Math.min(Math.max(importProgress, 0), 100)}%` }"
                  ></div>
                </div>
                <div class="mt-2 flex items-center justify-between text-[12px] text-[#7F7F7F]">
                  <span>已连接导入任务</span>
                  <span class="font-medium text-[#07C160]">{{ importProgress }}%</span>
                </div>
              </div>

              <button
                type="button"
                class="inline-flex w-full items-center justify-center rounded-lg border border-[#F0D7D7] bg-[#FFF7F7]/76 px-4 py-3 text-sm font-medium text-[#D64A4A] transition hover:bg-[#FFF7F7] focus:outline-none focus:ring-2 focus:ring-[#D64A4A]/15"
                @click="cancelImport"
              >
                取消导入
              </button>
            </div>
          </div>

          <div v-if="importComplete && !importing" class="animate-fade-in">
            <div class="flex min-h-[340px] flex-col justify-between gap-5">
              <div>
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#07C160]">
                  <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  <span>导入完成</span>
                </div>
                <h2 class="mt-4 text-[24px] font-semibold tracking-[-0.03em] text-[#000000e6] sm:text-[30px]">数据已就绪</h2>
                <p class="mt-3 text-[14px] leading-7 text-[#6B7280]">{{ importComplete.message || '账号数据已成功导入。' }}</p>
              </div>

              <div class="rounded-lg border border-[#CFEEDB] bg-[#EAF8EF]/82 p-3 text-sm">
                <div class="flex items-center justify-between gap-2.5">
                  <span class="text-[#7F7F7F]">账号</span>
                  <span class="min-w-0 truncate font-mono text-xs text-[#000000d9]">{{ importComplete.account }}</span>
                </div>
                <div v-if="importComplete.backup_dir" class="mt-2 flex items-start justify-between gap-2.5 border-t border-[#DDF4E7] pt-2.5">
                  <span class="shrink-0 text-[#7F7F7F]">旧数据备份</span>
                  <span class="min-w-0 break-all text-right text-xs text-[#000000d9]">{{ importComplete.backup_dir }}</span>
                </div>
              </div>

              <div class="grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  class="inline-flex items-center justify-center rounded-lg border border-[#DDEBE0] bg-[#F7FCF8]/86 px-4 py-3 text-sm font-medium text-[#4A4A4A] transition hover:bg-[#F1FAF4] focus:outline-none focus:ring-2 focus:ring-[#07C160]/15"
                  @click="retryPickDirectory"
                >
                  继续导入
                </button>
                <button
                  type="button"
                  class="inline-flex items-center justify-center rounded-lg bg-[#07C160] px-4 py-3 text-sm font-medium text-white transition hover:bg-[#06AD56] focus:outline-none focus:ring-2 focus:ring-[#07C160]/25"
                  @click="navigateTo('/chat')"
                >
                  进入聊天页面
                </button>
              </div>
            </div>
          </div>

          <div v-if="importPreview && !importing && !importComplete" class="animate-fade-in space-y-3">
            <div class="rounded-lg border border-[#CFEEDB] bg-[#EAF8EF]/82 p-4 sm:p-5">
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex min-w-0 items-center gap-3">
                  <img :src="importPreview.avatar_url || '/Contact.png'" class="h-16 w-16 shrink-0 rounded-md border border-[#EDEDED] bg-white object-cover" alt="头像" />
                  <div class="min-w-0">
                    <p class="text-[12px] font-medium tracking-[0.12em] text-[#07C160]">检测到的账号</p>
                    <div class="mt-1 truncate text-[24px] font-semibold tracking-[-0.03em] text-[#000000e6]">{{ importPreview.nick || '未命名账号' }}</div>
                    <div class="mt-1.5 truncate font-mono text-[12px] text-[#7F7F7F]">{{ importPreview.username }}</div>
                  </div>
                </div>
                <span class="inline-flex w-fit rounded-md border border-[#CFEEDB] bg-[#F4FBF6]/86 px-2.5 py-1 text-[12px] font-medium text-[#07C160]">可导入</span>
              </div>

              <div v-if="selectedImportPath" class="mt-4 rounded-md border border-[#E1EFE5] bg-[#F7FCF8]/86 px-3 py-3">
                <p class="text-[12px] font-medium text-[#7F7F7F]">导入路径</p>
                <p class="mt-1 break-all text-[13px] leading-6 text-[#000000d9]">{{ selectedImportPath }}</p>
              </div>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
              <div class="rounded-lg border border-[#E1EFE5] bg-[#F7FCF8]/86 p-4">
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#000000e6]">
                  <span class="h-2 w-2 rounded-full bg-[#07C160]"></span>
                  <span>数据库</span>
                </div>
                <p class="mt-2 text-[12px] leading-5 text-[#7F7F7F]">已检测到可导入的数据库文件。</p>
              </div>
              <div class="rounded-lg border border-[#E1EFE5] bg-[#F7FCF8]/86 p-4">
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#000000e6]">
                  <span class="h-2 w-2 rounded-full" :class="importPreview.has_resource ? 'bg-[#07C160]' : 'bg-[#C9D2CB]'"></span>
                  <span>资源文件</span>
                </div>
                <p class="mt-2 text-[12px] leading-5 text-[#7F7F7F]">{{ importPreview.has_resource ? '已发现图片、视频等资源文件。' : '未发现资源文件，仍可导入数据库。' }}</p>
              </div>
            </div>

            <div v-if="importPreview.source_overlaps_target" class="rounded-lg border border-[#F4D6D6] bg-[#FFF7F7] p-4 text-[13px] leading-6 text-[#9C5F5F]">
              导入源目录与目标数据目录相同或相互包含，请重新选择外部备份目录。
            </div>
            <div v-else-if="importPreview.target_exists" class="rounded-lg border border-[#CFEEDB] bg-[#F1FAF4] p-4 text-[13px] leading-6 text-[#5F6F66]">
              该账号在本地已存在。确认导入时会先备份旧目录，再写入新数据。
            </div>

            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
              <button
                type="button"
                class="inline-flex items-center justify-center rounded-lg border border-[#DDEBE0] bg-[#F7FCF8]/86 px-4 py-3 text-sm font-medium text-[#4A4A4A] transition hover:bg-[#F1FAF4] focus:outline-none focus:ring-2 focus:ring-[#07C160]/15"
                @click="handlePickDirectory"
              >
                重新选择
              </button>
              <button
                type="button"
                :disabled="importing || importPreview?.source_overlaps_target"
                class="inline-flex items-center justify-center rounded-lg bg-[#07C160] px-4 py-3 text-sm font-medium text-white transition hover:bg-[#06AD56] focus:outline-none focus:ring-2 focus:ring-[#07C160]/25 disabled:cursor-not-allowed disabled:bg-[#8FD9AE]"
                @click="confirmImport"
              >
                确认导入此账号
              </button>
            </div>
          </div>

          <div v-if="importError && !importing" class="animate-fade-in">
            <div class="flex min-h-[340px] flex-col justify-between gap-5">
              <div>
                <div class="flex items-center gap-2 text-[13px] font-medium text-[#D64A4A]">
                  <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>导入失败</span>
                </div>
                <h2 class="mt-4 text-[24px] font-semibold tracking-[-0.03em] text-[#000000e6] sm:text-[30px]">目录暂时无法识别</h2>
                <p class="mt-2 text-[14px] leading-6 text-[#9C5F5F]">{{ importError }}</p>
              </div>

              <div v-if="selectedImportPath" class="rounded-lg border border-[#F1E3E3] bg-[#FFF7F7] px-2.5 py-2.5">
                <p class="text-[12px] font-medium text-[#B26B6B]">当前路径</p>
                <p class="mt-1 break-all text-[13px] leading-6 text-[#7A4B4B]">{{ selectedImportPath }}</p>
              </div>

              <button
                type="button"
                class="inline-flex w-full items-center justify-center rounded-lg border border-[#DDEBE0] bg-[#F7FCF8]/86 px-4 py-3 text-sm font-medium text-[#4A4A4A] transition hover:bg-[#F1FAF4] focus:outline-none focus:ring-2 focus:ring-[#07C160]/15"
                @click="retryPickDirectory"
              >
                重新选择目录
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
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
const importComplete = ref(null)
const selectedImportPath = ref('')
const importJobId = ref('')

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
  importComplete.value = null
  importError.value = ''
  selectedImportPath.value = ''
  importing.value = false
  importProgress.value = 0
  importMessage.value = '正在准备...'
  importJobId.value = ''
}

const { importDecryptedPreview, pickSystemDirectory } = useApi()
const apiBase = useApiBase()
const handlePickDirectory = async () => {
  let path = ''

  if (isDesktopShell()) {
    try {
      const res = await window.wechatDesktop.chooseDirectory({
        title: '请选择解密输出目录 (如: output/wxid_xxxxx 或单账号 output)'
      })
      if (!res || res.canceled || !res.filePaths?.length) return
      path = res.filePaths[0]
    } catch (e) {
      console.error('选择目录失败:', e)
      return
    }
  } else {
    try {
      const res = await pickSystemDirectory({ title: '请选择解密输出目录 (建议选到 wxid_xxx 层级)' })
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

该目录似乎不是 "wxid_xxxxx" 账号目录。如果这是 wxdump 的单账号 output 根目录，可以继续。确定要继续吗？`)
    if (!isOk) return
  }

  selectedImportPath.value = path
  importError.value = ''
  importPreview.value = null

  try {
    importPreview.value = await importDecryptedPreview({ import_path: path })
  } catch (e) {
    importError.value = e.message || '目录格式不正确，请确保包含 databases/database 目录；wxdump 格式可不含 account.json'
  }
}

const retryPickDirectory = async () => {
  resetImport()
  await handlePickDirectory()
}

const makeImportJobId = () => {
  const randomPart = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `import-${randomPart}`
}

const cancelImport = async () => {
  const jobId = importJobId.value
  closeEventSource()
  importing.value = false
  importProgress.value = 0
  importMessage.value = '正在准备...'
  importComplete.value = null
  importError.value = ''

  if (!jobId) return
  try {
    const url = new URL(`${apiBase.replace(/\/$/, '')}/import_decrypted/cancel`, window.location.origin)
    url.searchParams.set('job_id', jobId)
    await fetch(url.toString(), { method: 'POST' })
  } catch (e) {
    console.error('取消导入失败:', e)
  } finally {
    importJobId.value = ''
  }
}


const confirmImport = async () => {
  if (!selectedImportPath.value) return

  if (importPreview.value?.source_overlaps_target) {
    importError.value = '导入源目录与目标数据目录相同或相互包含，请重新选择外部备份目录。'
    return
  }

  if (importPreview.value?.target_exists) {
    const ok = window.confirm(`当前账号已存在：${importPreview.value.username}

继续导入会先自动备份旧目录，然后导入新数据。
旧数据库数量：${importPreview.value.existing_db_count || 0}
新数据库数量：${importPreview.value.incoming_db_count || 0}

确定继续吗？`)
    if (!ok) return
  }

  importing.value = true

  importComplete.value = null
  importError.value = ''
  importProgress.value = 0
  importMessage.value = '启动导入程序...'
  importJobId.value = makeImportJobId()

  const url = new URL(`${apiBase.replace(/\/$/, '')}/import_decrypted`, window.location.origin)
  url.searchParams.set('import_path', selectedImportPath.value)
  url.searchParams.set('job_id', importJobId.value)

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
        importComplete.value = data
        importError.value = ''
        importing.value = false
        closeEventSource()
        importJobId.value = ''
      } else if (data.type === 'error') {
        importError.value = data.message || '导入失败'
        importComplete.value = null
        importing.value = false
        closeEventSource()
        importJobId.value = ''
      }
    } catch (e) {
      console.error('解析 SSE 数据失败:', e)
    }
  }

  eventSource.onerror = (e) => {
    console.error('EventSource 错误:', e)
    if (!importing.value) {
      closeEventSource()
      return
    }
    importComplete.value = null
    importError.value = '与服务器连接断开或发生错误'
    importing.value = false
    closeEventSource()
    importJobId.value = ''
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
