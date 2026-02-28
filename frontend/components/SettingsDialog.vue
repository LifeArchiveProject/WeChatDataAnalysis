<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 px-4 py-4 backdrop-blur-md sm:py-8"
    @click.self="handleClose"
  >
    <div class="flex h-[80vh] min-h-[380px] w-full max-w-[760px] overflow-hidden rounded-[10px] border border-[#e2e2e2] bg-white shadow-2xl">
      <!-- Sidebar -->
      <aside class="flex w-[180px] shrink-0 flex-col bg-[#fcfcfc] border-r border-[#eeeeee]">
        <div class="mt-4 mb-2 flex items-center px-4 gap-2">
          <div class="flex h-6 w-6 items-center justify-center rounded-[5px] bg-[#e7f5ee] text-[#07b75b]">
            <svg class="h-[15px] w-[15px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <span class="text-[14px] font-bold text-[#1f1f1f]">设置</span>
        </div>

        <div class="flex-1 space-y-0.5 px-3 py-2 overflow-y-auto scrollbar-custom">
          <button
            v-for="item in settingNavItems"
            :key="item.key"
            type="button"
            class="group flex w-full flex-col items-start rounded-[6px] px-3 py-1.5 text-left transition select-none"
            :class="activeSection === item.key ? 'bg-white shadow-sm ring-1 ring-[#e5e5e5]' : 'hover:bg-[#f0f0f0]/60'"
            @click="scrollToSection(item.key)"
          >
            <div class="text-[12px] font-medium" :class="activeSection === item.key ? 'text-[#111]' : 'text-[#777] group-hover:text-[#333]'">
              {{ item.label }}
            </div>
          </button>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="relative flex min-w-0 flex-1 flex-col bg-white">
        <button
          type="button"
          class="absolute right-3 top-3 z-10 flex h-6 w-6 items-center justify-center rounded-md text-[#888] transition hover:bg-[#f2f2f2] hover:text-[#222]"
          title="关闭设置"
          @click="handleClose"
        >
          <svg class="h-[14px] w-[14px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>

        <header class="flex h-12 shrink-0 items-center px-6">
          <div class="flex items-center gap-1.5 text-[#111]">
            <svg class="h-[15px] w-[15px] text-[#666]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <h2 class="text-[13px] font-bold">{{ settingNavItems.find(i => i.key === activeSection)?.label || '设置' }}</h2>
          </div>
        </header>

        <div ref="contentScrollRef" class="scrollbar-custom flex-1 overflow-y-auto px-6 pb-8 pt-1 space-y-8" @scroll="onContentScroll">
          
          <div v-if="!isDesktopEnv" class="rounded-[6px] border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] leading-relaxed text-amber-900">
            当前为浏览器环境：开机自启动/关闭窗口/更新 不可用；“启动偏好”可正常使用；“后端端口”会尝试同步重启本机后端到新端口。
          </div>

          <section ref="desktopSectionRef">
            <div class="mb-3 text-[12px] font-bold text-[#999] tracking-widest">桌面行为</div>
            
            <div class="space-y-3">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[13px] font-medium text-[#222]">开机自启动</div>
                  <div class="mt-0.5 text-[11px] text-[#909090]">系统登录后自动启动桌面端应用</div>
                </div>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="desktopAutoLaunch"
                  class="settings-switch shrink-0"
                  :class="switchTrackClass(desktopAutoLaunch, !isDesktopEnv || desktopAutoLaunchLoading)"
                  :disabled="!isDesktopEnv || desktopAutoLaunchLoading"
                  @click="toggleDesktopAutoLaunch"
                >
                  <span class="settings-switch-thumb" :class="desktopAutoLaunch ? 'translate-x-[20px]' : 'translate-x-0'" />
                </button>
              </div>
              <div v-if="desktopAutoLaunchError" class="text-xs text-red-600 whitespace-pre-wrap -mt-2">
                {{ desktopAutoLaunchError }}
              </div>

              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[13px] font-medium text-[#222]">关闭窗口行为</div>
                  <div class="mt-0.5 text-[11px] text-[#909090]">点击关闭按钮时：默认最小化到托盘</div>
                </div>
                <select
                  class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#333] outline-none transition focus:border-[#07b75b] focus:ring-1 focus:ring-[#07b75b]/30"
                  :disabled="!isDesktopEnv || desktopCloseBehaviorLoading"
                  :value="desktopCloseBehavior"
                  @change="onDesktopCloseBehaviorChange"
                >
                  <option value="tray">最小化到托盘</option>
                  <option value="exit">直接退出</option>
                </select>
              </div>
              <div v-if="desktopCloseBehaviorError" class="text-xs text-red-600 whitespace-pre-wrap -mt-2">
                {{ desktopCloseBehaviorError }}
              </div>

              <div class="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                <div class="min-w-0 flex-1">
                  <div class="text-[13px] font-medium text-[#222]">后端端口</div>
                  <div class="mt-0.5 text-[11px] text-[#909090]">桌面端：重启内置后端并刷新；网页端：尝试切换端口</div>
                </div>
                <div class="flex shrink-0 items-center gap-1.5">
                  <input
                    v-model="desktopBackendPortInput"
                    type="number"
                    min="1"
                    max="65535"
                    class="w-16 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-center text-[12px] tabular-nums text-[#333] outline-none transition focus:border-[#07b75b] focus:ring-1 focus:ring-[#07b75b]/30"
                    :disabled="desktopBackendPortLoading || desktopBackendPortApplying"
                    @keyup.enter="onDesktopBackendPortApply"
                  />
                  <button
                    type="button"
                    class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="desktopBackendPortLoading || desktopBackendPortApplying"
                    @click="onDesktopBackendPortApply"
                  >
                    {{ desktopBackendPortApplying ? '...' : '应用' }}
                  </button>
                  <button
                    type="button"
                    class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="desktopBackendPortLoading || desktopBackendPortApplying"
                    @click="onDesktopBackendPortReset"
                  >
                    恢复默认
                  </button>
                </div>
              </div>
              <div v-if="desktopBackendPortError" class="text-xs text-red-600 whitespace-pre-wrap -mt-1.5">
                {{ desktopBackendPortError }}
              </div>
            </div>
          </section>

          <section ref="startupSectionRef">
            <div class="mb-3 text-[12px] font-bold text-[#999] tracking-widest">启动偏好</div>
            
            <div class="space-y-3">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[13px] font-medium text-[#222]">启动后自动开启实时获取</div>
                  <div class="mt-0.5 text-[11px] text-[#909090]">进入聊天页后自动打开“实时开关”</div>
                </div>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="desktopAutoRealtime"
                  class="settings-switch shrink-0"
                  :class="switchTrackClass(desktopAutoRealtime)"
                  @click="toggleDesktopAutoRealtime"
                >
                  <span class="settings-switch-thumb" :class="desktopAutoRealtime ? 'translate-x-[20px]' : 'translate-x-0'" />
                </button>
              </div>

              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[13px] font-medium text-[#222]">有数据时默认进入聊天页</div>
                  <div class="mt-0.5 text-[11px] text-[#909090]">有已解密账号时，打开应用跳转到 /chat</div>
                </div>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="desktopDefaultToChatWhenData"
                  class="settings-switch shrink-0"
                  :class="switchTrackClass(desktopDefaultToChatWhenData)"
                  @click="toggleDesktopDefaultToChat"
                >
                  <span class="settings-switch-thumb" :class="desktopDefaultToChatWhenData ? 'translate-x-[20px]' : 'translate-x-0'" />
                </button>
              </div>
            </div>
          </section>

          <section ref="updatesSectionRef">
            <div class="mb-3 text-[12px] font-bold text-[#999] tracking-widest">更新</div>
            
            <div class="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0 flex-1">
                <div class="text-[13px] font-medium text-[#222]">当前版本</div>
                <div class="mt-0.5 text-[11px] text-[#909090]">{{ desktopVersionText }}</div>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-[#fafafa] px-2.5 py-1 text-[12px] text-[#222] transition hover:bg-[#f0f0f0] disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="!isDesktopEnv || desktopUpdate.manualCheckLoading.value"
                @click="onDesktopCheckUpdates"
              >
                {{ desktopUpdate.manualCheckLoading.value ? '检查中...' : '检查桌面版更新' }}
              </button>
            </div>
            <div v-if="desktopUpdate.lastCheckMessage.value" class="mt-2 rounded-[6px] bg-[#f9f9f9] border border-[#eee] px-2.5 py-1.5 text-[11px] text-[#666] whitespace-pre-wrap break-words">
              {{ desktopUpdate.lastCheckMessage.value }}
            </div>
          </section>

          <section ref="snsSectionRef">
            <div class="mb-3 text-[12px] font-bold text-[#999] tracking-widest">朋友圈</div>
            
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="text-[13px] font-medium text-[#222]">朋友圈图片使用缓存</div>
                <div class="mt-0.5 text-[11px] text-[#909090]">开启：下载解密失败时回退本地缓存（默认）；关闭：始终重新下载</div>
              </div>
              <button
                type="button"
                role="switch"
                :aria-checked="snsUseCache"
                class="settings-switch shrink-0"
                :class="switchTrackClass(snsUseCache)"
                @click="toggleSnsUseCache"
              >
                <span class="settings-switch-thumb" :class="snsUseCache ? 'translate-x-[20px]' : 'translate-x-0'" />
              </button>
            </div>
          </section>

        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { DESKTOP_SETTING_AUTO_REALTIME_KEY, DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, SNS_SETTING_USE_CACHE_KEY, readLocalBoolSetting, writeLocalBoolSetting } from '~/utils/desktop-settings'
import { readApiBaseOverride, writeApiBaseOverride } from '~/utils/api-settings'

defineProps({
  open: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

const settingNavItems = [
  { key: 'desktop', label: '桌面行为', hint: '启动 / 关闭 / 端口' },
  { key: 'startup', label: '启动偏好', hint: '自动实时 / 默认页面' },
  { key: 'updates', label: '更新', hint: '版本信息 / 检查更新' },
  { key: 'sns', label: '朋友圈', hint: '图片缓存策略' },
]

const activeSection = ref(settingNavItems[0].key)
const contentScrollRef = ref(null)
const desktopSectionRef = ref(null)
const startupSectionRef = ref(null)
const updatesSectionRef = ref(null)
const snsSectionRef = ref(null)

const isDesktopEnv = ref(false)
const desktopUpdate = useDesktopUpdate()

const desktopVersionText = computed(() => {
  if (!isDesktopEnv.value) return '仅桌面端可用'
  const v = String(desktopUpdate.currentVersion.value || '').trim()
  return v || '—'
})

const desktopAutoRealtime = ref(false)
const desktopDefaultToChatWhenData = ref(false)
const snsUseCache = ref(true)

const desktopAutoLaunch = ref(false)
const desktopAutoLaunchLoading = ref(false)
const desktopAutoLaunchError = ref('')

const desktopCloseBehavior = ref('tray')
const desktopCloseBehaviorLoading = ref(false)
const desktopCloseBehaviorError = ref('')

const desktopBackendPortInput = ref('')
const desktopBackendPortLoading = ref(false)
const desktopBackendPortApplying = ref(false)
const desktopBackendPortError = ref('')
const desktopBackendPortDefault = ref(10392)

const switchTrackClass = (enabled, disabled = false) => {
  if (disabled) return enabled ? 'bg-[#07b75b] opacity-50 cursor-not-allowed' : 'bg-[#d0d0d0] opacity-50 cursor-not-allowed'
  return enabled ? 'bg-[#07b75b] hover:brightness-95' : 'bg-[#d0d0d0] hover:brightness-95'
}

const sectionElements = computed(() => [
  { key: 'desktop', el: desktopSectionRef.value },
  { key: 'startup', el: startupSectionRef.value },
  { key: 'updates', el: updatesSectionRef.value },
  { key: 'sns', el: snsSectionRef.value },
])

const scrollToSection = (key) => {
  const scrollHost = contentScrollRef.value
  const target = sectionElements.value.find((item) => item.key === key)?.el
  activeSection.value = key
  if (!scrollHost || !target) return
  scrollHost.scrollTo({
    top: Math.max(0, target.offsetTop - 10),
    behavior: 'smooth',
  })
}

const onContentScroll = () => {
  const scrollHost = contentScrollRef.value
  if (!scrollHost) return
  const position = scrollHost.scrollTop + 120
  let current = settingNavItems[0].key
  for (const section of sectionElements.value) {
    if (!section.el) continue
    if (section.el.offsetTop <= position) current = section.key
  }
  activeSection.value = current
}

const handleClose = () => {
  emit('close')
}

const onEscKeydown = (event) => {
  if (event?.key !== 'Escape') return
  event.preventDefault()
  handleClose()
}

const refreshDesktopAutoLaunch = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.getAutoLaunch) return
  desktopAutoLaunchLoading.value = true
  desktopAutoLaunchError.value = ''
  try {
    desktopAutoLaunch.value = !!(await window.wechatDesktop.getAutoLaunch())
  } catch (e) {
    desktopAutoLaunchError.value = e?.message || '读取开机自启动状态失败'
  } finally {
    desktopAutoLaunchLoading.value = false
  }
}

const setDesktopAutoLaunch = async (enabled) => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.setAutoLaunch) return
  desktopAutoLaunchLoading.value = true
  desktopAutoLaunchError.value = ''
  try {
    desktopAutoLaunch.value = !!(await window.wechatDesktop.setAutoLaunch(!!enabled))
  } catch (e) {
    desktopAutoLaunchError.value = e?.message || '设置开机自启动失败'
    await refreshDesktopAutoLaunch()
  } finally {
    desktopAutoLaunchLoading.value = false
  }
}

const refreshDesktopCloseBehavior = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.getCloseBehavior) return
  desktopCloseBehaviorLoading.value = true
  desktopCloseBehaviorError.value = ''
  try {
    const v = await window.wechatDesktop.getCloseBehavior()
    desktopCloseBehavior.value = String(v || '').toLowerCase() === 'exit' ? 'exit' : 'tray'
  } catch (e) {
    desktopCloseBehaviorError.value = e?.message || '读取关闭窗口行为失败'
  } finally {
    desktopCloseBehaviorLoading.value = false
  }
}

const setDesktopCloseBehavior = async (behavior) => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.setCloseBehavior) return
  const desired = String(behavior || '').toLowerCase() === 'exit' ? 'exit' : 'tray'
  desktopCloseBehaviorLoading.value = true
  desktopCloseBehaviorError.value = ''
  try {
    const v = await window.wechatDesktop.setCloseBehavior(desired)
    desktopCloseBehavior.value = String(v || '').toLowerCase() === 'exit' ? 'exit' : 'tray'
  } catch (e) {
    desktopCloseBehaviorError.value = e?.message || '设置关闭窗口行为失败'
    await refreshDesktopCloseBehavior()
  } finally {
    desktopCloseBehaviorLoading.value = false
  }
}

const refreshDesktopBackendPort = async () => {
  if (!process.client || typeof window === 'undefined') return
  desktopBackendPortLoading.value = true
  desktopBackendPortError.value = ''
  try {
    if (window.wechatDesktop?.getBackendPort) {
      const v = await window.wechatDesktop.getBackendPort()
      const n = Number(v)
      if (Number.isInteger(n) && n >= 1 && n <= 65535) {
        desktopBackendPortInput.value = String(n)
        return
      }
    }

    try {
      const apiBase = useApiBase()
      const resp = await $fetch('/admin/port', { baseURL: apiBase })
      const n = Number(resp?.port)
      const d = Number(resp?.default_port)
      if (Number.isInteger(d) && d >= 1 && d <= 65535) desktopBackendPortDefault.value = d
      if (Number.isInteger(n) && n >= 1 && n <= 65535) {
        desktopBackendPortInput.value = String(n)
        return
      }
    } catch {}

    let detectedPort = null
    const override = readApiBaseOverride()
    if (override && /^https?:\/\//i.test(override)) {
      try {
        const u = new URL(override)
        const n = Number(u.port)
        if (Number.isInteger(n) && n >= 1 && n <= 65535) detectedPort = n
      } catch {}
    }
    if (!desktopBackendPortInput.value) desktopBackendPortInput.value = String(detectedPort ?? 10392)
  } catch (e) {
    desktopBackendPortError.value = e?.message || '读取后端端口失败'
  } finally {
    desktopBackendPortLoading.value = false
  }
}

const applyDesktopBackendPort = async () => {
  if (!process.client || typeof window === 'undefined') return
  const raw = String(desktopBackendPortInput.value || '').trim()
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 1 || n > 65535) {
    desktopBackendPortError.value = '端口无效：请输入 1-65535 的整数'
    return
  }
  desktopBackendPortApplying.value = true
  desktopBackendPortError.value = ''
  try {
    if (window.wechatDesktop?.setBackendPort) {
      await window.wechatDesktop.setBackendPort(n)
      return
    }

    const currentApiBase = useApiBase()
    let currentBackendPort = null
    try {
      const info = await $fetch('/admin/port', { baseURL: currentApiBase })
      const p = Number(info?.port)
      if (Number.isInteger(p) && p >= 1 && p <= 65535) currentBackendPort = p
    } catch {}
    const uiPort = (() => {
      const rawPort = String(window.location?.port || '').trim()
      if (rawPort) return Number(rawPort)
      return window.location?.protocol === 'https:' ? 443 : 80
    })()
    const isUiServedByBackend = !!(currentBackendPort && uiPort === currentBackendPort)

    await $fetch('/admin/port', {
      baseURL: currentApiBase,
      method: 'POST',
      body: { port: n },
    })

    let protocol = String(window.location?.protocol || 'http:')
    if (protocol !== 'http:' && protocol !== 'https:') protocol = 'http:'
    const host = String(window.location?.hostname || '').trim() || '127.0.0.1'
    const nextOrigin = `${protocol}//${host}:${n}`
    writeApiBaseOverride(`${nextOrigin}/api`)

    const waitForHealth = async (healthUrl, timeoutMs = 30_000) => {
      const startedAt = Date.now()
      while (true) {
        try {
          const r = await fetch(healthUrl, { method: 'GET' })
          if (r && r.status < 500) return
        } catch {}
        if (Date.now() - startedAt > timeoutMs) throw new Error(`后端启动超时：${healthUrl}`)
        await new Promise((r) => setTimeout(r, 300))
      }
    }
    await waitForHealth(`${nextOrigin}/api/health`, 30_000)

    if (isUiServedByBackend) {
      const nextUrl = new URL(window.location.href)
      nextUrl.port = String(n)
      window.location.href = nextUrl.toString()
      return
    }

    try {
      window.location.reload()
    } catch {}
  } catch (e) {
    desktopBackendPortError.value = e?.message || '设置后端端口失败（若为网页端，请确认后端为本机启动且允许重启）'
    await refreshDesktopBackendPort()
  } finally {
    desktopBackendPortApplying.value = false
  }
}

const toggleDesktopAutoLaunch = async () => {
  if (!isDesktopEnv.value || desktopAutoLaunchLoading.value) return
  await setDesktopAutoLaunch(!desktopAutoLaunch.value)
}

const onDesktopCloseBehaviorChange = async (ev) => {
  const v = String(ev?.target?.value || '').trim()
  await setDesktopCloseBehavior(v)
}

const onDesktopBackendPortApply = async () => {
  await applyDesktopBackendPort()
}

const onDesktopBackendPortReset = async () => {
  desktopBackendPortInput.value = String(desktopBackendPortDefault.value || 10392)
  await applyDesktopBackendPort()
}

const toggleDesktopAutoRealtime = () => {
  const next = !desktopAutoRealtime.value
  desktopAutoRealtime.value = next
  writeLocalBoolSetting(DESKTOP_SETTING_AUTO_REALTIME_KEY, next)
}

const toggleDesktopDefaultToChat = () => {
  const next = !desktopDefaultToChatWhenData.value
  desktopDefaultToChatWhenData.value = next
  writeLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, next)
}

const toggleSnsUseCache = () => {
  const next = !snsUseCache.value
  snsUseCache.value = next
  writeLocalBoolSetting(SNS_SETTING_USE_CACHE_KEY, next)
}

const onDesktopCheckUpdates = async () => {
  await desktopUpdate.manualCheck()
}

onMounted(async () => {
  if (process.client && typeof window !== 'undefined') {
    const isElectron = /electron/i.test(String(navigator.userAgent || ''))
    isDesktopEnv.value = isElectron && !!window.wechatDesktop
    window.addEventListener('keydown', onEscKeydown)
  }

  desktopAutoRealtime.value = readLocalBoolSetting(DESKTOP_SETTING_AUTO_REALTIME_KEY, false)
  desktopDefaultToChatWhenData.value = readLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, false)
  snsUseCache.value = readLocalBoolSetting(SNS_SETTING_USE_CACHE_KEY, true)

  await refreshDesktopBackendPort()
  if (isDesktopEnv.value) {
    void desktopUpdate.initListeners()
    await refreshDesktopAutoLaunch()
    await refreshDesktopCloseBehavior()
  }

  await nextTick()
  onContentScroll()
})

onBeforeUnmount(() => {
  if (!process.client || typeof window === 'undefined') return
  window.removeEventListener('keydown', onEscKeydown)
})
</script>

<style scoped>
.settings-switch {
  width: 44px;
  height: 24px;
  border-radius: 999px;
  padding: 2px;
  transition: background-color 0.16s ease, opacity 0.16s ease, filter 0.16s ease;
}

.settings-switch-thumb {
  display: block;
  height: 20px;
  width: 20px;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.24);
  transition: transform 0.16s ease;
}

/* 自定义右侧滚动条 */
.scrollbar-custom::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-custom::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-custom::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 8px;
}
.scrollbar-custom::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}
</style>
