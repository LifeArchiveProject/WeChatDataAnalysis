<template>
  <div :class="rootClass">
    <SidebarRail v-if="showSidebar" />
    <div class="flex-1 flex flex-col min-h-0">
      <!-- Desktop titlebar lives above the page content (right column) -->
      <DesktopTitleBar />
      <div :class="contentClass">
        <NuxtPage />
      </div>
    </div>
  </div>
</template>

<script setup>
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { usePrivacyStore } from '~/stores/privacy'

const route = useRoute()

// In Electron the server/pre-render doesn't know about `window.wechatDesktop`.
// If we render different DOM on server vs client, Vue hydration will keep the
// server HTML (no patch) and the layout/CSS fixes won't apply reliably.
// So we detect desktop onMounted and update reactively.
const isDesktop = ref(false)

const updateDprVar = () => {
  const dpr = window.devicePixelRatio || 1
  document.documentElement.style.setProperty('--dpr', String(dpr))
}

onMounted(() => {
  isDesktop.value = !!window?.wechatDesktop
  updateDprVar()
  window.addEventListener('resize', updateDprVar)

  // Init global UI state.
  const chatAccounts = useChatAccountsStore()
  const privacy = usePrivacyStore()
  void chatAccounts.ensureLoaded()
  privacy.init()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateDprVar)
})

const rootClass = computed(() => {
  const base = 'bg-gradient-to-br from-green-50 via-emerald-50 to-green-100'
  return isDesktop.value
    ? `wechat-desktop h-screen flex overflow-hidden ${base}`
    : `h-screen flex overflow-hidden ${base}`
})

const contentClass = computed(() =>
  isDesktop.value
    ? 'wechat-desktop-content flex-1 overflow-auto min-h-0'
    : 'flex-1 overflow-auto min-h-0'
)

const showSidebar = computed(() => {
  const path = String(route.path || '')
  if (path === '/') return false
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

/* Electron 桌面端使用自绘标题栏（frame: false）。
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
</style>
