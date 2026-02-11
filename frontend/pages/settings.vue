<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #EDEDED">
    <div class="flex-1 flex flex-col min-h-0" style="background-color: #EDEDED">
      <div class="flex-1 min-h-0 overflow-auto p-6">
        <div class="max-w-3xl mx-auto">
          <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <div class="px-5 py-4 border-b border-gray-200 bg-[#F7F7F7]">
              <div class="text-lg font-semibold text-gray-900">设置</div>
              <div class="text-sm text-gray-500 mt-1">桌面端相关行为与启动偏好</div>
            </div>

            <div class="p-5 space-y-5">
              <div v-if="!isDesktopEnv" class="rounded-md border border-amber-200 bg-amber-50 text-amber-900 px-3 py-2 text-xs leading-5">
                当前为浏览器环境：“桌面行为”分组仅桌面端可用；“启动偏好”分组可正常使用。
              </div>

              <div class="rounded-lg border border-gray-200">
                <div class="px-4 py-3 border-b border-gray-200 bg-gray-50">
                  <div class="text-sm font-medium text-gray-900">桌面行为</div>
                </div>
                <div class="px-4 py-3 space-y-4">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0">
                      <div class="text-sm font-medium text-gray-900">开机自启动</div>
                      <div class="text-xs text-gray-500">系统登录后自动启动桌面端</div>
                    </div>
                    <input
                      type="checkbox"
                      class="h-4 w-4"
                      :checked="desktopAutoLaunch"
                      :disabled="!isDesktopEnv || desktopAutoLaunchLoading"
                      @change="onDesktopAutoLaunchToggle"
                    />
                  </div>
                  <div v-if="desktopAutoLaunchError" class="text-xs text-red-600 whitespace-pre-wrap">
                    {{ desktopAutoLaunchError }}
                  </div>

                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0">
                      <div class="text-sm font-medium text-gray-900">关闭窗口行为</div>
                      <div class="text-xs text-gray-500">点击关闭按钮时：默认最小化到托盘</div>
                    </div>
                    <select
                      class="text-sm px-2 py-1 rounded-md border border-gray-200 bg-white"
                      :disabled="!isDesktopEnv || desktopCloseBehaviorLoading"
                      :value="desktopCloseBehavior"
                      @change="onDesktopCloseBehaviorChange"
                    >
                      <option value="tray">最小化到托盘</option>
                      <option value="exit">直接退出</option>
                    </select>
                  </div>
                  <div v-if="desktopCloseBehaviorError" class="text-xs text-red-600 whitespace-pre-wrap">
                    {{ desktopCloseBehaviorError }}
                  </div>
                </div>
              </div>

              <div class="rounded-lg border border-gray-200">
                <div class="px-4 py-3 border-b border-gray-200 bg-gray-50">
                  <div class="text-sm font-medium text-gray-900">启动偏好</div>
                </div>
                <div class="px-4 py-3 space-y-4">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0">
                      <div class="text-sm font-medium text-gray-900">启动后自动开启实时获取</div>
                      <div class="text-xs text-gray-500">进入聊天页后自动打开“实时开关”（默认关闭）</div>
                    </div>
                    <input
                      type="checkbox"
                      class="h-4 w-4"
                      :checked="desktopAutoRealtime"
                      @change="onDesktopAutoRealtimeToggle"
                    />
                  </div>

                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0">
                      <div class="text-sm font-medium text-gray-900">有数据时默认进入聊天页</div>
                      <div class="text-xs text-gray-500">有已解密账号时，打开应用默认跳转到 /chat（默认关闭）</div>
                    </div>
                    <input
                      type="checkbox"
                      class="h-4 w-4"
                      :checked="desktopDefaultToChatWhenData"
                      @change="onDesktopDefaultToChatToggle"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { DESKTOP_SETTING_AUTO_REALTIME_KEY, DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, readLocalBoolSetting, writeLocalBoolSetting } from '~/utils/desktop-settings'

useHead({ title: '设置 - 微信数据分析助手' })

const isDesktopEnv = ref(false)

const desktopAutoRealtime = ref(false)
const desktopDefaultToChatWhenData = ref(false)

const desktopAutoLaunch = ref(false)
const desktopAutoLaunchLoading = ref(false)
const desktopAutoLaunchError = ref('')

const desktopCloseBehavior = ref('tray')
const desktopCloseBehaviorLoading = ref(false)
const desktopCloseBehaviorError = ref('')

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

const onDesktopAutoLaunchToggle = async (ev) => {
  const checked = !!ev?.target?.checked
  await setDesktopAutoLaunch(checked)
}

const onDesktopCloseBehaviorChange = async (ev) => {
  const v = String(ev?.target?.value || '').trim()
  await setDesktopCloseBehavior(v)
}

const onDesktopAutoRealtimeToggle = (ev) => {
  const checked = !!ev?.target?.checked
  desktopAutoRealtime.value = checked
  writeLocalBoolSetting(DESKTOP_SETTING_AUTO_REALTIME_KEY, checked)
}

const onDesktopDefaultToChatToggle = (ev) => {
  const checked = !!ev?.target?.checked
  desktopDefaultToChatWhenData.value = checked
  writeLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, checked)
}

onMounted(async () => {
  if (process.client && typeof window !== 'undefined') {
    isDesktopEnv.value = !!window.wechatDesktop
  }

  desktopAutoRealtime.value = readLocalBoolSetting(DESKTOP_SETTING_AUTO_REALTIME_KEY, false)
  desktopDefaultToChatWhenData.value = readLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, false)

  if (isDesktopEnv.value) {
    await refreshDesktopAutoLaunch()
    await refreshDesktopCloseBehavior()
  }
})
</script>
