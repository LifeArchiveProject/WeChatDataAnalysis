<template>
  <div :class="rootClass">
    <SidebarRail v-if="showSidebar" />
    <div class="flex-1 flex flex-col min-h-0">
      <!-- Desktop titlebar lives above the page content (right column) -->
      <DesktopTitleBar v-if="showDesktopTitleBar" />
      <DataSourceFallbackBanner :status="selectedDataSourceStatus" />
      <div :class="contentClass">
        <NuxtPage />
      </div>
    </div>

    <SettingsDialog :open="settingsDialogOpen" @close="closeSettingsDialog" />

    <GuideDialog
      :open="noAccountGuideOpen"
      eyebrow="数据准备提示"
      title="还没有可查看的微信数据"
      description="当前没有已解密或已导入的账号。您仍然可以留在此页面，但聊天、联系人、朋友圈和其他记录暂时无法加载。"
      :details="[
        '首次使用可以先检测本机微信数据并完成数据库解密',
        '已有解密备份时，也可以从首页进入“导入备份”',
        '完成后再返回当前页面即可查看对应账号的数据'
      ]"
      note="这个提示不会强制跳转，选择“暂时留在此页”可以继续浏览当前界面。"
      primary-label="去检测解密"
      secondary-label="暂时留在此页"
      tone="info"
      @primary="goToAccountSetup"
      @secondary="dismissNoAccountGuide"
      @close="dismissNoAccountGuide"
    />

    <ClientOnly v-if="isDesktopUpdater">
      <DesktopUpdateDialog
        :open="desktopUpdate.open.value"
        :info="desktopUpdate.info.value"
        :is-downloading="desktopUpdate.isDownloading.value"
        :ready-to-install="desktopUpdate.readyToInstall.value"
        :progress="desktopUpdate.progress.value"
        :error="desktopUpdate.error.value"
        :has-ignore="true"
        @close="desktopUpdate.dismiss"
        @update="desktopUpdate.startUpdate"
        @install="desktopUpdate.installUpdate"
        @ignore="desktopUpdate.ignore"
      />
    </ClientOnly>
  </div>
</template>

<script setup>
import { useThemeStore } from '~/stores/theme'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

const route = useRoute()
const desktopUpdate = useDesktopUpdate()
const { open: settingsDialogOpen, closeDialog: closeSettingsDialog } = useSettingsDialog()
const themeStore = useThemeStore()
const chatAccounts = useChatAccountsStore()
const { selectedAccount, selectedDataSourceStatus } = storeToRefs(chatAccounts)
const noAccountGuideOpen = ref(false)

const accountDataRoutePrefixes = [
  '/chat',
  '/edits',
  '/sns',
  '/favorites',
  '/contacts',
  '/biz',
  '/mini-programs',
  '/finder',
  '/payments',
  '/revokes',
  '/wrapped'
]

const isAccountDataRoute = (path) => accountDataRoutePrefixes.some(
  (prefix) => path === prefix || path.startsWith(`${prefix}/`)
)

let accountGuideCheckToken = 0
const checkNoAccountGuide = async () => {
  if (!process.client) return

  const path = String(route.path || '')
  const token = ++accountGuideCheckToken
  if (!isAccountDataRoute(path)) {
    noAccountGuideOpen.value = false
    return
  }

  await chatAccounts.ensureLoaded()
  if (token !== accountGuideCheckToken || String(route.path || '') !== path) return
  noAccountGuideOpen.value = !String(selectedAccount.value || '').trim()
}

const dismissNoAccountGuide = () => {
  noAccountGuideOpen.value = false
}

const goToAccountSetup = async () => {
  noAccountGuideOpen.value = false
  await navigateTo('/detection-result')
}

watch(() => route.path, () => { void checkNoAccountGuide() }, { immediate: true })
watch(selectedAccount, (account) => {
  if (String(account || '').trim()) noAccountGuideOpen.value = false
})

if (process.client) {
  themeStore.init()
}

// In Electron the server/pre-render doesn't know about `window.wechatDesktop`.
// If we render different DOM on server vs client, Vue hydration will keep the
// server HTML (no patch) and the layout/CSS fixes won't apply reliably.
// So we detect desktop onMounted and update reactively.
const isDesktop = ref(false)
const isDesktopUpdater = ref(false)

const updateDprVar = () => {
  const dpr = window.devicePixelRatio || 1
  document.documentElement.style.setProperty('--dpr', String(dpr))
}

onMounted(() => {
  const isElectron = /electron/i.test(String(navigator.userAgent || ''))
  const api = window?.wechatDesktop
  isDesktop.value = isElectron && !!api
  const brandOk = !api?.__brand || api.__brand === 'WeChatDataAnalysisDesktop'
  isDesktopUpdater.value =
    isDesktop.value &&
    brandOk &&
    typeof api?.checkForUpdates === 'function' &&
    typeof api?.downloadAndInstall === 'function'
  updateDprVar()
  window.addEventListener('resize', updateDprVar)

  if (isDesktopUpdater.value) {
    void desktopUpdate.initListeners()
  }

  // Init global UI state.
  const privacy = usePrivacyStore()
  void chatAccounts.ensureLoaded()
  privacy.init()
  themeStore.init()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateDprVar)
})

const setupShellBackgroundRoutes = new Set([
  '/',
  '/import',
  '/decrypt',
  '/detection-result',
  '/decrypt-result'
])

const useSetupShellBackground = computed(() => {
  const path = String(route.path || '')
  return setupShellBackgroundRoutes.has(path)
})

const useWrappedShellBackground = computed(() => {
  const path = String(route.path || '')
  return path === '/wrapped' || path.startsWith('/wrapped/')
})

const rootClass = computed(() => {
  let base = 'theme-app-shell'
  if (useSetupShellBackground.value) {
    base += ' theme-app-shell-setup'
  } else if (useWrappedShellBackground.value) {
    base += ' theme-app-shell-wrapped'
  }
  return isDesktop.value
    ? `wechat-desktop h-screen flex overflow-hidden ${base}`
    : `h-screen flex overflow-hidden ${base}`
})

const contentClass = computed(() =>
  isDesktop.value
    ? 'wechat-desktop-content flex-1 overflow-auto min-h-0'
    : 'flex-1 overflow-auto min-h-0'
)

const showDesktopTitleBar = computed(() => isDesktop.value)

const showSidebar = computed(() => {
  const path = String(route.path || '')
  if (path === '/' || path === '/import') return false
  if (path === '/decrypt' || path === '/detection-result' || path === '/decrypt-result') return false
  return !(path === '/wrapped' || path.startsWith('/wrapped/'))
})
</script>

<style>
:root {
  --dpr: 1;
  /* Left sidebar rail (chat/sns): icon size + spacing */
  --sidebar-rail-step: 48px;
  --sidebar-rail-btn: 32px;
  --sidebar-rail-icon: 24px;
}

/* Electron 桌面端使用隐藏标题栏 + 原生窗口控制按钮 overlay。
 * 页面里如果继续用 Tailwind 的 h-screen/min-h-screen（100vh），会把标题栏高度叠加进去，从而出现外层滚动条。
 * 这里把 “screen” 在桌面端视为内容区高度（100%），让标题栏高度自然内嵌在布局里。 */
.wechat-desktop {
  --desktop-titlebar-height: 32px;
  --desktop-titlebar-btn-width: 46px;
}

/* 仅重解释页面根节点的 h-screen/min-h-screen，避免影响页面内其它布局。
 * 使用 100% 跟随 flex 内容区高度，避免 100vh/calc 在某些缩放比例下产生 1px 误差导致滚动条。 */
.wechat-desktop .wechat-desktop-content > .h-screen {
  height: 100%;
}

.wechat-desktop .wechat-desktop-content > .min-h-screen {
  min-height: 100%;
}

.theme-app-shell {
  background: var(--app-shell-bg);
}

.theme-app-shell-setup {
  background:
    radial-gradient(circle at top left, rgba(7, 193, 96, 0.08), transparent 32%),
    radial-gradient(circle at top right, rgba(16, 174, 239, 0.08), transparent 36%),
    linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 45%, #dcfce7 100%);
}

.theme-app-shell-wrapped {
  background: #F3FFF8;
}

html[data-theme='dark'] .theme-app-shell,
html[data-theme='dark'] .theme-app-shell-setup,
html[data-theme='dark'] .theme-app-shell-wrapped {
  background: var(--app-shell-bg);
}
</style>
