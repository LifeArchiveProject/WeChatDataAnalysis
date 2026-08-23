<template>
  <div
    v-if="open"
    class="settings-dialog theme-scope fixed inset-0 z-[20000] flex items-center justify-center bg-black/40 px-2 py-2 backdrop-blur-md sm:px-4 sm:py-8"
    @click.self="handleClose"
  >
    <div class="settings-dialog-panel flex h-[80vh] min-h-[380px] w-full max-w-[880px] overflow-hidden rounded-[10px] border border-[#e2e2e2] bg-white shadow-2xl">
      <!-- Sidebar -->
      <aside class="hidden w-[160px] shrink-0 flex-col bg-[#fcfcfc] border-r border-[#eeeeee] sm:flex">
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

        <header class="flex h-12 shrink-0 items-center px-4 sm:px-6">
          <div class="flex items-center gap-1.5 text-[#111]">
            <svg class="h-[15px] w-[15px] text-[#666]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <h2 class="text-[13px] font-bold">{{ settingNavItems.find(i => i.key === activeSection)?.label || '设置' }}</h2>
          </div>
        </header>

        <div ref="contentScrollRef" class="scrollbar-custom flex-1 overflow-y-auto px-4 pb-8 pt-1 space-y-8 sm:px-6" @scroll="onContentScroll">
          
          <div v-if="!isDesktopEnv" class="rounded-[6px] border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] leading-relaxed text-amber-900">
            当前为浏览器环境：开机自启动/关闭窗口/更新 不可用；“启动偏好”可正常使用；“后端端口”会尝试同步重启本机后端到新端口。
          </div>

          <section ref="desktopSectionRef">
            <div class="mb-2.5 text-[12px] font-bold text-[#999] tracking-widest">桌面行为</div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-3">
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
                <ErrorNotice v-if="desktopAutoLaunchError" :message="desktopAutoLaunchError" compact manual class="mt-1.5 text-[11px] text-red-600" />
              </div>

              <div class="px-3.5 py-3">
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
                <ErrorNotice v-if="desktopCloseBehaviorError" :message="desktopCloseBehaviorError" compact manual class="mt-1.5 text-[11px] text-red-600" />
              </div>

              <div class="px-3.5 py-3">
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
                <ErrorNotice v-if="desktopBackendPortError" :message="desktopBackendPortError" compact manual class="mt-1.5 text-[11px] text-red-600" />
              </div>

              <div class="px-3.5 py-3">
                <div class="flex flex-col gap-2.5">
                  <div class="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="text-[13px] font-medium text-[#222]">output 目录</div>
                      <div class="mt-0.5 text-[11px] text-[#909090] break-words">
                        当前：{{ desktopOutputDirText }}
                        <span class="ml-1 text-[#666]">{{ desktopOutputDirIsDefault ? '（默认位置）' : '（自定义位置）' }}</span>
                      </div>
                      <div class="mt-0.5 text-[11px] text-[#909090] break-words">默认：{{ desktopOutputDirDefaultText }}</div>
                      <div v-if="desktopOutputDirPendingText" class="mt-0.5 text-[11px] text-amber-700 break-words">
                        待应用：{{ desktopOutputDirPendingText }}
                      </div>
                      <div v-if="desktopOutputDirUnavailableReason" class="mt-1 text-[11px] text-amber-700 break-words">
                        {{ desktopOutputDirUnavailableReason }}
                      </div>
                    </div>
                    <button
                      type="button"
                      class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="!isDesktopEnv || desktopOutputDirLoading || desktopOutputDirApplying"
                      @click="onDesktopOpenOutputDir"
                    >
                      打开当前 output
                    </button>
                  </div>
                  <div class="flex flex-col gap-1.5 sm:flex-row sm:items-center">
                    <input
                      v-model="desktopOutputDirInput"
                      type="text"
                      spellcheck="false"
                      class="min-w-0 flex-1 rounded-[6px] border border-[#e2e2e2] bg-white px-2.5 py-1.5 text-[12px] text-[#333] outline-none transition focus:border-[#07b75b] focus:ring-1 focus:ring-[#07b75b]/30"
                      :disabled="desktopOutputDirControlsDisabled"
                      :placeholder="desktopOutputDirCanChange ? '选择新的 output 目录' : '当前环境不支持修改 output 目录'"
                      @keyup.enter="onDesktopOutputDirApply"
                    />
                    <div class="flex shrink-0 items-center gap-1.5">
                      <button
                        type="button"
                        class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="desktopOutputDirControlsDisabled"
                        @click="onDesktopChooseOutputDir"
                      >
                        选择文件夹
                      </button>
                      <button
                        type="button"
                        class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="desktopOutputDirControlsDisabled"
                        @click="onDesktopOutputDirApply"
                      >
                        {{ desktopOutputDirApplying ? '迁移中...' : '应用' }}
                      </button>
                      <button
                        type="button"
                        class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="desktopOutputDirControlsDisabled"
                        @click="onDesktopOutputDirReset"
                      >
                        恢复默认
                      </button>
                    </div>
                  </div>
                  <div v-if="desktopOutputDirCanChange" class="text-[11px] text-[#909090]">
                    修改后会迁移整个 output 目录；如果目标目录已有内容，会先阻止并提示。
                  </div>
                  <div v-if="desktopOutputDirProgress" class="rounded-[6px] border border-[#d8efe2] bg-[#f4fbf7] px-2.5 py-2">
                    <div class="flex items-center justify-between gap-3 text-[11px] text-[#1b6b43]">
                      <div class="min-w-0 truncate">{{ desktopOutputDirProgressText }}</div>
                      <div class="shrink-0 tabular-nums">{{ desktopOutputDirProgressPercentText }}</div>
                    </div>
                    <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-[#dceee3]">
                      <div
                        class="h-full rounded-full bg-[#07b75b] transition-[width] duration-200 ease-out"
                        :class="desktopOutputDirProgressIndeterminate ? 'animate-pulse' : ''"
                        :style="{ width: desktopOutputDirProgressBarWidth }"
                      />
                    </div>
                    <div v-if="desktopOutputDirProgressDetail" class="mt-1 text-[10px] text-[#5d7a68] break-all">
                      {{ desktopOutputDirProgressDetail }}
                    </div>
                  </div>
                  <div v-if="desktopOutputDirMessage" class="rounded-[6px] border border-[#d8efe2] bg-[#f4fbf7] px-2.5 py-1.5 text-[11px] text-[#1b6b43] whitespace-pre-wrap">
                    {{ desktopOutputDirMessage }}
                  </div>
                </div>
                <ErrorNotice v-if="desktopOutputDirError" :message="desktopOutputDirError" compact manual class="mt-1.5 text-[11px] text-red-600" />
              </div>

              <div ref="desktopLogFileRef" class="px-3.5 py-3">
                <div class="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-[#222]">日志文件</div>
                    <div class="mt-0.5 text-[11px] text-[#909090] break-words">{{ desktopLogFileText }}</div>
                  </div>
                  <button
                    type="button"
                    class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="desktopLogFileLoading || desktopLogFileOpening"
                    @click="onOpenBackendLogFile"
                  >
                    {{ desktopLogFileOpening ? '打开中...' : '打开日志' }}
                  </button>
                </div>
                <ErrorNotice v-if="desktopLogFileError" :message="desktopLogFileError" compact manual class="mt-1.5 text-[11px] text-red-600" />
              </div>
            </div>
          </section>

          <section ref="voiceSectionRef">
            <div class="mb-2.5 text-[12px] font-bold tracking-widest text-[var(--app-text-muted)]">语音转文字</div>
            <div class="divide-y divide-[var(--app-border-soft)] overflow-hidden rounded-[10px] border border-[var(--app-border)] bg-[var(--app-surface-bg)]">
              <div class="px-3.5 py-3">
                <div class="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-[var(--app-text-primary)]">推理设备</div>
                    <div class="mt-0.5 text-[11px] leading-relaxed text-[var(--app-text-muted)]">CPU 兼容所有设备；NVIDIA GPU 使用 CUDA 加速，初始化失败会自动回退 CPU。</div>
                  </div>
                  <div class="flex w-full shrink-0 overflow-hidden rounded-[6px] border border-[var(--app-border)] bg-[var(--app-surface-bg)] sm:w-auto" role="radiogroup" aria-label="语音转文字推理设备">
                    <button
                      type="button"
                      role="radio"
                      :aria-checked="voiceDevicePreference === 'cpu'"
                      class="voice-setting-focus flex-1 px-2.5 py-1.5 text-[12px] transition disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
                      :class="voiceDevicePreference === 'cpu' ? 'bg-[var(--app-surface-muted)] text-[var(--app-accent)]' : 'text-[var(--app-text-secondary)] hover:bg-[var(--app-neutral-btn-hover)]'"
                      :disabled="voiceDeviceBusy || voiceDeviceLocked"
                      @click="setVoiceDevice('cpu')"
                    >
                      CPU
                    </button>
                    <button
                      type="button"
                      role="radio"
                      :aria-checked="voiceDevicePreference === 'cuda'"
                      class="voice-setting-focus flex-1 border-l border-[var(--app-border)] px-2.5 py-1.5 text-[12px] transition disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
                      :class="voiceDevicePreference === 'cuda' ? 'bg-[var(--app-surface-muted)] text-[var(--app-accent)]' : 'text-[var(--app-text-secondary)] hover:bg-[var(--app-neutral-btn-hover)]'"
                      :disabled="voiceDeviceBusy || voiceDeviceLocked || !voiceCudaAvailable"
                      :title="voiceCudaAvailable ? '使用 NVIDIA CUDA 加速' : (voiceCudaReason || '未检测到可用的 NVIDIA CUDA 设备')"
                      @click="setVoiceDevice('cuda')"
                    >
                      NVIDIA GPU
                    </button>
                  </div>
                </div>

                <div v-if="voiceStatusLoading" class="mt-2 text-[11px] text-[var(--app-text-muted)]">正在检测本地 Whisper 与 CUDA 状态...</div>
                <template v-else>
                  <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--app-text-secondary)]">
                    <span>已选：{{ voiceDeviceLabel }}</span>
                    <span>实际：{{ voiceActiveDeviceLabel }}</span>
                  </div>
                  <div v-if="voiceFallbackReason" class="mt-1 text-[11px] leading-relaxed text-[var(--app-text-secondary)]">
                    {{ voiceFallbackReason }}
                  </div>
                  <div v-if="voiceDeviceLocked" class="mt-1 text-[11px] leading-relaxed text-[var(--app-text-secondary)]">
                    推理设备由启动环境变量固定，界面中的选项不可修改。
                  </div>
                </template>
                <ErrorNotice v-if="voiceDeviceError" :message="voiceDeviceError" compact manual class="mt-1.5 text-[11px] text-[var(--danger-color)]" />
              </div>

              <div class="px-3.5 py-3">
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-[var(--app-text-primary)]">Whisper 模型</div>
                    <div class="mt-0.5 text-[11px] leading-relaxed text-[var(--app-text-muted)]">模型需先下载到本机，再选择用于后续语音识别；本应用下载的模型可随时删除。</div>
                  </div>
                  <span class="shrink-0 rounded-full bg-[var(--app-surface-muted)] px-2 py-1 text-[10px] text-[var(--app-text-secondary)]">当前：{{ voiceModelText }}</span>
                </div>

                <div v-if="voiceStatusLoading" class="mt-3 grid gap-2 sm:grid-cols-2" aria-label="正在读取模型列表">
                  <div v-for="index in 4" :key="index" class="h-[134px] rounded-[9px] bg-[var(--app-surface-muted)]" />
                </div>
                <div v-else-if="voiceModels.length" class="mt-3 grid gap-2.5 sm:grid-cols-2" role="list" aria-label="可用 Whisper 模型">
                  <article
                    v-for="model in voiceModels"
                    :key="model.id"
                    role="listitem"
                    class="flex min-h-[142px] min-w-0 flex-col rounded-[9px] border p-3 transition"
                    :class="model.selected ? 'border-[var(--app-accent)] bg-[var(--app-surface-soft)]' : 'border-[var(--app-border)] bg-[var(--app-surface-bg)] hover:border-[var(--app-accent)]'"
                    :data-voice-model="model.id"
                  >
                    <div class="flex items-start justify-between gap-2">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-1.5">
                          <span class="text-[13px] font-semibold text-[var(--app-text-primary)]">{{ model.name }}</span>
                          <span v-if="model.recommended" class="rounded-full bg-[var(--app-surface-muted)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--app-accent)]">推荐</span>
                          <span v-if="model.selected" class="rounded-full bg-[var(--app-surface-muted)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--app-accent)]">已选择</span>
                        </div>
                        <div class="mt-1 text-[10px] text-[var(--app-text-muted)]">{{ model.size }} · {{ model.speed }} · {{ model.quality }}</div>
                      </div>
                      <span class="shrink-0 text-[10px] font-medium" :class="voiceModelStateClass(model)">{{ voiceModelStateText(model) }}</span>
                    </div>

                    <div class="mt-1.5 line-clamp-2 text-[10px] leading-relaxed text-[var(--app-text-secondary)]">{{ model.description }}</div>
                    <div v-if="isVoiceModelDownloading(model)" class="mt-2" data-voice-model-progress>
                      <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-[10px] leading-relaxed">
                        <span class="text-[var(--app-text-secondary)]">{{ voiceModelDownloadStageText(model) }}</span>
                        <span class="tabular-nums text-[var(--app-accent)]">{{ voiceModelDownloadProgressText(model) }}</span>
                      </div>
                      <div
                        class="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--app-surface-muted)]"
                        role="progressbar"
                        :aria-label="`${model.name} 模型下载进度`"
                        aria-valuemin="0"
                        aria-valuemax="100"
                        :aria-valuenow="voiceModelDownloadPercent(model)"
                        :aria-valuetext="voiceModelDownloadProgressText(model)"
                      >
                        <div
                          class="h-full rounded-full bg-[var(--app-accent)] transition-[width] duration-200 ease-out"
                          :style="{ width: `${voiceModelDownloadPercent(model)}%` }"
                        />
                      </div>
                    </div>
                    <div v-if="model.downloadError" class="mt-1 text-[10px] leading-relaxed text-[var(--danger-color)]">{{ model.downloadError }}</div>
                    <div v-else-if="!model.downloaded && !isVoiceModelDownloading(model) && model.reason" class="mt-1 line-clamp-2 text-[10px] leading-relaxed text-[var(--app-text-muted)]">{{ model.reason }}</div>
                    <div v-else-if="model.downloaded && !model.deletable" class="mt-1 text-[10px] leading-relaxed text-[var(--app-text-secondary)]">共享缓存可直接使用，但不会由本应用删除。</div>

                    <div class="mt-auto flex flex-wrap items-center justify-end gap-1.5 pt-2">
                      <button
                        v-if="model.downloaded && !model.selected"
                        type="button"
                        class="voice-setting-focus rounded-[5px] border border-[var(--app-border)] bg-[var(--app-surface-bg)] px-2 py-1 text-[10px] font-medium text-[var(--app-accent)] transition hover:bg-[var(--app-neutral-btn-hover)] disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="voiceModelLocked || isVoiceModelActionBusy(model.id)"
                        :title="voiceModelLocked ? '模型由启动环境变量固定' : `选择 ${model.name}`"
                        @click="selectVoiceModel(model)"
                      >
                        {{ isVoiceModelActionBusy(model.id, 'select') ? '选择中...' : '选择' }}
                      </button>
                      <button
                        v-if="!model.downloaded && !isVoiceModelDeletePending(model.id)"
                        type="button"
                        class="voice-setting-focus whitespace-nowrap rounded-[5px] bg-[var(--app-accent)] px-2 py-1 text-[10px] font-medium text-white transition hover:bg-[var(--app-accent-hover)] disabled:cursor-not-allowed disabled:opacity-40"
                        :disabled="!model.downloadable || isVoiceModelDownloading(model) || isVoiceModelActionBusy(model.id)"
                        :title="model.downloadable ? `下载 ${model.name}` : (model.reason || '当前无法下载')"
                        @click="startVoiceModelDownload(model)"
                      >
                        {{ voiceModelDownloadButtonText(model) }}
                      </button>
                      <button
                        v-if="canDeleteVoiceModel(model)"
                        type="button"
                        class="voice-setting-focus rounded-[5px] border border-[var(--app-border)] px-2 py-1 text-[10px] text-[var(--danger-color)] transition hover:bg-[var(--app-neutral-btn-hover)] disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="isVoiceModelDeletePending(model.id)"
                        :title="isVoiceModelDownloading(model) || isVoiceModelActionBusy(model.id, 'download') ? `停止下载并删除 ${model.name}` : `删除本机上的 ${model.name}`"
                        @click="removeVoiceModel(model)"
                      >
                        {{ isVoiceModelDeletePending(model.id) ? '删除中...' : (isVoiceModelDownloading(model) || isVoiceModelActionBusy(model.id, 'download') ? '停止并删除' : '删除') }}
                      </button>
                    </div>
                  </article>
                </div>
                <div v-else-if="!voiceDeviceError" class="mt-3 rounded-[8px] bg-[var(--app-surface-soft)] px-3 py-4 text-center text-[11px] text-[var(--app-text-muted)]">后端未返回可用模型列表。</div>

                <div v-if="voiceModelLocked" class="mt-2 text-[11px] leading-relaxed text-[var(--app-text-secondary)]">模型由 WECHAT_TOOL_WHISPER_MODEL 环境变量固定，界面中不可切换。</div>
                <div v-if="voiceStatusReason" class="mt-2 text-[11px] leading-relaxed text-[var(--app-text-muted)]">{{ voiceStatusReason }}</div>
                <div v-if="voiceModelMessage" class="mt-2 text-[11px] text-[var(--app-accent)]">{{ voiceModelMessage }}</div>
                <ErrorNotice v-if="voiceModelError" :message="voiceModelError" compact manual class="mt-1.5 text-[11px] text-[var(--danger-color)]" />
              </div>

              <div class="px-3.5 py-3" data-testid="voice-transcript-global-delete">
                <div class="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-[var(--app-text-primary)]">本项目转写数据</div>
                    <div class="mt-0.5 text-[11px] leading-relaxed text-[var(--app-text-muted)]">
                      删除所有账号中由本项目 Whisper 生成的转写文字。微信原生转写、原始语音和模型都会保留。
                    </div>
                  </div>
                  <button
                    type="button"
                    class="voice-setting-focus shrink-0 rounded-[6px] border border-[var(--app-border)] px-3 py-1.5 text-[11px] font-medium text-[var(--danger-color)] transition hover:bg-[var(--app-neutral-btn-hover)] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="voiceTranscriptDeleteBusy"
                    :aria-busy="voiceTranscriptDeleteBusy"
                    @click="deleteAllProjectVoiceTranscripts"
                  >{{ voiceTranscriptDeleteBusy ? '正在删除…' : '删除全部本项目转写结果' }}</button>
                </div>
                <div v-if="voiceTranscriptDeleteMessage" class="mt-2 text-[11px] leading-relaxed text-[var(--app-accent)]" role="status">
                  {{ voiceTranscriptDeleteMessage }}
                </div>
                <div
                  v-if="voiceTranscriptDeleteWarning"
                  class="mt-2 text-[11px] leading-relaxed"
                  style="color: color-mix(in srgb, var(--warning-color) 70%, var(--app-text-primary));"
                  role="status"
                >
                  {{ voiceTranscriptDeleteWarning }}
                </div>
                <ErrorNotice v-if="voiceTranscriptDeleteError" :message="voiceTranscriptDeleteError" compact manual class="mt-1.5 text-[11px] text-[var(--danger-color)]" />
              </div>
            </div>
          </section>

          <section ref="mcpSectionRef">
            <div class="mb-2.5 text-[12px] font-bold text-[#999] tracking-widest">MCP 接入</div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-3">
                <div class="flex items-center justify-between gap-3">
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-[#222]">允许局域网接入 MCP</div>
                    <div class="mt-0.5 text-[11px] leading-relaxed text-[#909090]">开启后后端监听 0.0.0.0，同一局域网内的其他设备可通过接入提示词中的地址接入。</div>
                    <div class="mt-0.5 text-[11px] leading-relaxed text-[#909090] break-all">当前地址：{{ mcpEndpoint }}</div>
                    <div v-if="mcpLanAccessMessage" class="mt-1 text-[11px] leading-relaxed text-[#1b6b43]">{{ mcpLanAccessMessage }}</div>
                    <ErrorNotice v-if="mcpLanAccessError" :message="mcpLanAccessError" compact manual class="mt-1 text-[11px] leading-relaxed text-red-600" />
                  </div>
                  <button
                    type="button"
                    role="switch"
                    :aria-checked="mcpLanAccessEnabled"
                    class="settings-switch shrink-0"
                    :class="switchTrackClass(mcpLanAccessEnabled, mcpLanAccessLoading)"
                    :disabled="mcpLanAccessLoading"
                    @click="toggleMcpLanAccess"
                  >
                    <span class="settings-switch-thumb" :class="mcpLanAccessEnabled ? 'translate-x-[20px]' : 'translate-x-0'" />
                  </button>
                </div>
              </div>

              <div class="px-3.5 py-3">
                <div class="flex flex-col gap-2">
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="text-[13px] font-medium text-[#222]">MCP Token</div>
                      <div class="mt-0.5 text-[11px] leading-relaxed text-[#909090]">客户端请求 MCP 时使用 Bearer token。</div>
                      <ErrorNotice v-if="mcpTokenError" :message="mcpTokenError" compact manual class="mt-1 text-[11px] leading-relaxed text-red-600" />
                    </div>
                    <div class="flex shrink-0 gap-1.5">
                      <button
                        type="button"
                        class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9]"
                        :disabled="mcpTokenLoading || !mcpToken"
                        @click="copyMcpText('token', mcpToken)"
                      >
                        {{ mcpCopiedKey === 'token' ? '已复制' : (mcpTokenLoading ? '加载中...' : '复制 Token') }}
                      </button>
                      <button
                        type="button"
                        class="rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9]"
                        :disabled="mcpTokenLoading"
                        @click="resetMcpToken"
                      >
                        {{ mcpCopiedKey === 'token-reset' ? '已重置' : '重置' }}
                      </button>
                    </div>
                  </div>
                  <pre class="max-h-[92px] overflow-auto rounded-[6px] bg-[#f7f7f7] px-2.5 py-2 text-[11px] leading-relaxed text-[#333] scrollbar-custom whitespace-pre-wrap">{{ mcpTokenText }}</pre>
                </div>
              </div>

              <div class="px-3.5 py-3">
                <div class="flex flex-col gap-2">
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="text-[13px] font-medium text-[#222]">AI 接入提示词</div>
                      <div class="mt-0.5 text-[11px] leading-relaxed text-[#909090]">复制到 AI 客户端的系统提示词或连接说明里。</div>
                    </div>
                    <button
                      type="button"
                      class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9]"
                      @click="copyMcpText('ai-prompt', mcpAiPrompt)"
                    >
                      {{ mcpCopiedKey === 'ai-prompt' ? '已复制' : '复制提示词' }}
                    </button>
                  </div>
                  <pre class="max-h-[220px] overflow-auto rounded-[6px] bg-[#f7f7f7] px-2.5 py-2 text-[11px] leading-relaxed text-[#333] scrollbar-custom whitespace-pre-wrap">{{ mcpAiPrompt }}</pre>
                </div>
              </div>

              <div class="px-3.5 py-3">
                <div class="flex flex-col gap-2">
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="text-[13px] font-medium text-[#222]">Skill Markdown</div>
                      <div class="mt-0.5 text-[11px] leading-relaxed text-[#909090]">单独复制到 AI 客户端的 skill 或知识配置。</div>
                      <ErrorNotice v-if="mcpSkillBundleError" :message="mcpSkillBundleError" compact manual class="mt-1 text-[11px] leading-relaxed text-red-600" />
                    </div>
                    <button
                      type="button"
                      class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9]"
                      :disabled="mcpSkillBundleLoading"
                      @click="copyMcpText('skill', mcpSkillText)"
                    >
                      {{ mcpCopiedKey === 'skill' ? '已复制' : (mcpSkillBundleLoading ? '加载中...' : '复制 Skill') }}
                    </button>
                  </div>
                  <pre class="max-h-[420px] overflow-auto rounded-[6px] bg-[#f7f7f7] px-2.5 py-2 text-[11px] leading-relaxed text-[#333] scrollbar-custom whitespace-pre-wrap">{{ mcpSkillText }}</pre>
                </div>
              </div>
            </div>
          </section>

          <section ref="keysSectionRef">
            <div class="mb-2.5 flex items-center justify-between gap-3">
              <div class="text-[12px] font-bold text-[#999] tracking-widest">数据库与密钥</div>
              <div class="flex items-center gap-1.5">
                <select
                  v-if="keyAccountOptions.length > 1"
                  class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#333] outline-none transition focus:border-[#07b75b] focus:ring-1 focus:ring-[#07b75b]/30"
                  :value="keysAccount"
                  :disabled="keysLoading"
                  @change="onKeysAccountChange"
                >
                  <option v-for="acc in keyAccountOptions" :key="acc" :value="acc">{{ acc }}</option>
                </select>
                <button
                  type="button"
                  class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="keysLoading"
                  @click="refreshSavedKeys"
                >
                  {{ keysLoading ? '读取中...' : '刷新' }}
                </button>
              </div>
            </div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-2.5 text-[11px] leading-relaxed text-[#909090]">
                这些密钥由本机自动获取，仅保存在本地，用于解密数据库和图片。请妥善保管，不要分享给他人。
              </div>

              <div v-for="item in keyRows" :key="item.key" class="px-3.5 py-3">
                <div class="flex flex-col gap-2">
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5">
                        <span class="text-[13px] font-medium text-[#222]">{{ item.label }}</span>
                        <span
                          v-if="item.verified"
                          class="inline-flex items-center rounded-full bg-[#EAF8EF] px-1.5 py-0.5 text-[10px] font-medium text-[#078A45]"
                        >已校验</span>
                      </div>
                      <div class="mt-0.5 text-[11px] leading-relaxed text-[#909090]">{{ item.hint }}</div>
                    </div>
                    <button
                      type="button"
                      class="shrink-0 rounded-[6px] border border-[#e2e2e2] bg-white px-2 py-1 text-[12px] text-[#222] transition hover:bg-[#f9f9f9] disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="!item.value"
                      @click="copyMcpText(item.key, item.value)"
                    >
                      {{ mcpCopiedKey === item.key ? '已复制' : '复制' }}
                    </button>
                  </div>
                  <pre class="max-h-[80px] overflow-auto rounded-[6px] bg-[#f7f7f7] px-2.5 py-2 text-[11px] leading-relaxed text-[#333] scrollbar-custom whitespace-pre-wrap break-all">{{ item.value || (keysLoaded ? '未获取到' : '—') }}</pre>
                </div>
              </div>

              <div v-if="keysError" class="px-3.5 py-3">
                <ErrorNotice :message="keysError" compact manual class="text-[11px] text-red-600" />
              </div>
            </div>
          </section>

          <section ref="startupSectionRef">
            <div class="mb-2.5 text-[12px] font-bold text-[#999] tracking-widest">启动偏好</div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-3">
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
            </div>
          </section>

          <section ref="mediaSectionRef">
            <div class="mb-2.5 text-[12px] font-bold text-[#999] tracking-widest">聊天与媒体</div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-3">
                <div class="flex items-center justify-between gap-3">
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-[#222]">自动获取原图</div>
                    <div class="mt-0.5 text-[11px] text-[#909090]">本地缺原图时自动联网拉取原图（每账号每天最多 {{ cdnImageDailyLimit }} 张）。关闭后仅显示本地已有图片。</div>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    :aria-checked="cdnImageEnabled"
                    class="settings-switch shrink-0"
                    :class="switchTrackClass(cdnImageEnabled, cdnImageLoading)"
                    @click="toggleCdnImage"
                  >
                    <span class="settings-switch-thumb" :class="cdnImageEnabled ? 'translate-x-[20px]' : 'translate-x-0'" />
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section ref="updatesSectionRef">
            <div class="mb-2.5 text-[12px] font-bold text-[#999] tracking-widest">更新</div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-3">
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
                  <ErrorNotice
                    v-if="desktopUpdateLastCheckFailed"
                    :message="desktopUpdate.lastCheckMessage.value"
                    compact
                    manual
                  />
                  <template v-else>{{ desktopUpdate.lastCheckMessage.value }}</template>
                </div>
              </div>
            </div>
          </section>

          <section ref="snsSectionRef">
            <div class="mb-2.5 text-[12px] font-bold text-[#999] tracking-widest">朋友圈</div>
            <div class="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white divide-y divide-[#ececec]">
              <div class="px-3.5 py-3">
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
              </div>
            </div>
          </section>

        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, SNS_SETTING_USE_CACHE_KEY, readLocalBoolSetting, writeLocalBoolSetting } from '~/lib/desktop-settings'
import { readApiBaseOverride, writeApiBaseOverride } from '~/lib/api-settings'
import { invalidateApiBaseCache } from '~/composables/useApiBase'
import { reportServerErrorFromError } from '~/lib/server-error-logging'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { notifyProjectVoiceTranscriptsInvalidated } from '~/lib/voice-transcript-invalidation'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  focusTarget: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['close'])
const api = useApi()

const settingNavItems = [
  { key: 'desktop', label: '桌面行为', hint: '启动 / 关闭 / 端口' },
  { key: 'voice', label: '语音转文字', hint: 'CPU / NVIDIA GPU' },
  { key: 'mcp', label: 'MCP 接入', hint: '局域网 / Skill / 工具' },
  { key: 'keys', label: '数据库与密钥', hint: '密钥查看 / 复制' },
  { key: 'startup', label: '启动偏好', hint: '默认页面' },
  { key: 'media', label: '聊天与媒体', hint: '原图获取' },
  { key: 'updates', label: '更新', hint: '版本信息 / 检查更新' },
  { key: 'sns', label: '朋友圈', hint: '图片缓存策略' },
]

const activeSection = ref(settingNavItems[0].key)
const contentScrollRef = ref(null)
const desktopSectionRef = ref(null)
const desktopLogFileRef = ref(null)
const voiceSectionRef = ref(null)
const mcpSectionRef = ref(null)
const keysSectionRef = ref(null)
const startupSectionRef = ref(null)
const mediaSectionRef = ref(null)
const updatesSectionRef = ref(null)
const snsSectionRef = ref(null)

const isDesktopEnv = ref(false)
const desktopUpdate = useDesktopUpdate()

const desktopVersionText = computed(() => {
  if (!isDesktopEnv.value) return '仅桌面端可用'
  const v = String(desktopUpdate.currentVersion.value || '').trim()
  return v || '—'
})

const desktopDefaultToChatWhenData = ref(false)

const cdnImageEnabled = ref(false)
const cdnImageLoading = ref(false)
const cdnImageDailyLimit = ref(10)
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

const desktopOutputDir = ref('')
const desktopOutputDirDefault = ref('')
const desktopOutputDirInput = ref('')
const desktopOutputDirPending = ref('')
const desktopOutputDirLoading = ref(false)
const desktopOutputDirApplying = ref(false)
const desktopOutputDirError = ref('')
const desktopOutputDirMessage = ref('')
const desktopOutputDirIsDefault = ref(true)
const desktopOutputDirCanChange = ref(true)
const desktopOutputDirUnavailableReason = ref('')
const desktopOutputDirProgress = ref(null)
let removeDesktopOutputDirProgressListener = null
const desktopOutputDirText = computed(() => {
  if (!isDesktopEnv.value) return '仅桌面端可用'
  const v = String(desktopOutputDir.value || '').trim()
  return v || '—'
})
const desktopOutputDirDefaultText = computed(() => {
  if (!isDesktopEnv.value) return '仅桌面端可用'
  const v = String(desktopOutputDirDefault.value || '').trim()
  return v || '—'
})
const desktopOutputDirPendingText = computed(() => {
  const v = String(desktopOutputDirPending.value || '').trim()
  return v || ''
})
const desktopOutputDirProgressPercent = computed(() => {
  const n = Number(desktopOutputDirProgress.value?.percent || 0)
  if (!Number.isFinite(n) || n < 0) return 0
  return Math.max(0, Math.min(100, Math.round(n)))
})
const desktopOutputDirProgressPercentText = computed(() => `${desktopOutputDirProgressPercent.value}%`)
const desktopOutputDirProgressText = computed(() => {
  const text = String(desktopOutputDirProgress.value?.message || '').trim()
  return text || '正在迁移 output 目录'
})
const desktopOutputDirProgressIndeterminate = computed(() => {
  const stage = String(desktopOutputDirProgress.value?.stage || '').trim()
  return stage === 'preparing' || stage === 'scanning' || stage === 'rolling-back' || stage === 'restarting'
})
const desktopOutputDirProgressBarWidth = computed(() => {
  if (!desktopOutputDirProgress.value) return '0%'
  if (desktopOutputDirProgressIndeterminate.value) return '28%'
  return `${Math.max(6, desktopOutputDirProgressPercent.value)}%`
})
const desktopOutputDirProgressDetail = computed(() => {
  const progress = desktopOutputDirProgress.value
  if (!progress) return ''

  const parts = []
  const bytesTotal = Number(progress.bytesTotal || 0)
  const bytesTransferred = Number(progress.bytesTransferred || 0)
  const itemsTotal = Number(progress.itemsTotal || 0)
  const itemsTransferred = Number(progress.itemsTransferred || 0)

  if (bytesTotal > 0) {
    parts.push(`${formatBytes(bytesTransferred)} / ${formatBytes(bytesTotal)}`)
  } else if (itemsTotal > 0) {
    parts.push(`${Math.min(itemsTransferred, itemsTotal)} / ${itemsTotal} 项`)
  }

  const currentFile = String(progress.currentFile || '').trim()
  if (currentFile) {
    parts.push(currentFile)
  }

  return parts.join(' · ')
})
const desktopOutputDirControlsDisabled = computed(() => (
  !isDesktopEnv.value || !desktopOutputDirCanChange.value || desktopOutputDirLoading.value || desktopOutputDirApplying.value
))

const desktopLogFilePath = ref('')
const desktopLogFileLoading = ref(false)
const desktopLogFileOpening = ref(false)
const desktopLogFileError = ref('')
const desktopLogFileText = computed(() => {
  const v = String(desktopLogFilePath.value || '').trim()
  return v || '—'
})

// 数据库与图片密钥（展示 + 复制）
const chatAccountsStore = useChatAccountsStore()
const { accounts: keyAccounts, selectedAccount: keySelectedAccount } = storeToRefs(chatAccountsStore)
const keysAccount = ref('')
const keysLoading = ref(false)
const keysError = ref('')
const keysLoaded = ref(false)
const dbKey = ref('')
const imageXorKey = ref('')
const imageAesKey = ref('')
const imageKeyVerified = ref(false)

const keyAccountOptions = computed(() => {
  const list = Array.isArray(keyAccounts.value) ? keyAccounts.value : []
  return list.map((v) => String(v || '').trim()).filter(Boolean)
})

const keyRows = computed(() => [
  {
    key: 'db-key',
    label: '数据库密钥',
    hint: '解密微信数据库（SQLCipher）用的密钥。',
    value: dbKey.value,
    verified: false,
  },
  {
    key: 'image-xor-key',
    label: '图片 XOR 密钥',
    hint: '解密 .dat 图片第一层的单字节异或值。',
    value: imageXorKey.value,
    verified: false,
  },
  {
    key: 'image-aes-key',
    label: '图片 AES 密钥',
    hint: '解密 .dat 图片第二层的 AES 密钥。',
    value: imageAesKey.value,
    verified: imageKeyVerified.value && !!imageAesKey.value,
  },
])

const voiceStatusLoading = ref(false)
const voiceDeviceBusy = ref(false)
const voiceDeviceError = ref('')
const voiceDevicePreference = ref('cpu')
const voiceDeviceSource = ref('default')
const voiceActiveDevice = ref('')
const voiceModel = ref('medium')
const voiceModels = ref([])
const voiceModelSource = ref('default')
const voiceModelAction = ref({ id: '', type: '' })
const voiceModelDeletePendingIds = ref([])
const voiceModelError = ref('')
const voiceModelMessage = ref('')
const voiceTranscriptDeleteBusy = ref(false)
const voiceTranscriptDeleteError = ref('')
const voiceTranscriptDeleteMessage = ref('')
const voiceTranscriptDeleteWarning = ref('')
const voiceStatusReason = ref('')
const voiceCuda = ref(null)
const voiceFallbackReason = ref('')
let voiceModelDownloadTimer = null
const voiceModelDownloadGenerations = new Map()
const voiceModelDownloadStartPromises = new Map()
const voiceDeviceLocked = computed(() => voiceDeviceSource.value === 'env')
const voiceModelLocked = computed(() => voiceModelSource.value === 'env')
const voiceCudaAvailable = computed(() => !!voiceCuda.value?.available)
const voiceCudaReason = computed(() => String(voiceCuda.value?.reason || '').trim())
const voiceModelText = computed(() => String(voiceModel.value || 'medium').trim() || 'medium')
const voiceDeviceLabel = computed(() => voiceDevicePreference.value === 'cuda' ? 'NVIDIA GPU' : 'CPU')
const voiceCudaDeviceLabels = computed(() => {
  const devices = Array.isArray(voiceCuda.value?.devices) ? voiceCuda.value.devices : []
  return devices.map((item) => String(item?.name || '').trim()).filter(Boolean)
})
const voiceActiveDeviceLabel = computed(() => {
  if (voiceActiveDevice.value === 'cuda') return voiceCudaDeviceLabels.value.join('、') || 'NVIDIA GPU'
  if (voiceActiveDevice.value === 'cpu') return 'CPU'
  if (voiceDevicePreference.value === 'cuda') return voiceCudaDeviceLabels.value.join('、') || 'NVIDIA GPU'
  return 'CPU'
})

const mcpLanAccessEnabled = ref(false)
const mcpLanAccessLoading = ref(false)
const mcpLanAccessError = ref('')
const mcpLanAccessMessage = ref('')
const mcpToken = ref('')
const mcpTokenLoading = ref(false)
const mcpTokenError = ref('')
const mcpSkillBundleText = ref('')
const mcpSkillBundleLoading = ref(false)
const mcpSkillBundleError = ref('')
const mcpCopiedKey = ref('')
const mcpAccessHost = ref('')
const mcpAccessEndpoint = ref('')
let mcpCopiedTimer = null

const mcpPortText = computed(() => {
  const n = Number(String(desktopBackendPortInput.value || '').trim())
  if (Number.isInteger(n) && n >= 1 && n <= 65535) return String(n)
  return '10392'
})

const mcpEndpoint = computed(() => {
  const reported = String(mcpAccessEndpoint.value || '').trim()
  if (/^https?:\/\//i.test(reported)) return reported
  const reportedHost = String(mcpAccessHost.value || '').trim()
  if (reportedHost) return `http://${reportedHost}:${mcpPortText.value}/mcp`
  if (!process.client || typeof window === 'undefined') return `http://127.0.0.1:${mcpPortText.value}/mcp`
  const apiBase = useApiBase()
  if (/^https?:\/\//i.test(apiBase)) {
    try {
      const u = new URL(apiBase)
      return `${u.origin}/mcp`
    } catch {}
  }
  const protocol = window.location?.protocol === 'https:' ? 'https:' : 'http:'
  const host = String(window.location?.hostname || '127.0.0.1').trim() || '127.0.0.1'
  return `${protocol}//${host}:${mcpPortText.value}/mcp`
})

const applyMcpAccessInfo = (resp) => {
  if (!resp || typeof resp !== 'object') return
  const accessHost = String(resp.accessHost || resp.access_host || '').trim()
  const endpoint = String(resp.mcpEndpoint || resp.mcp_endpoint || '').trim()
  if (accessHost) mcpAccessHost.value = accessHost
  if (/^https?:\/\//i.test(endpoint)) mcpAccessEndpoint.value = endpoint
}

const mcpSkillFallback = [
  '# WeChat MCP Copilot',
  '',
  'Use WeChatDataAnalysis MCP like an investigator: start broad, resolve fuzzy targets, then fetch only the context needed to answer.',
  '',
  'Core rules:',
  '1. Start with initialize and tools/list.',
  '2. Prefer compact mobile facade tools before low-level tools.',
  '3. Keep limits small, page results, and expand only when needed.',
  '4. Use returned URLs for media and exports instead of inlining binary content.',
].join('\n')
const mcpAiPrompt = computed(() => [
  '你现在可以通过 WeChatDataAnalysis MCP 访问本机微信数据。',
  `MCP endpoint: ${mcpEndpoint.value}`,
  `Authorization: Bearer ${mcpToken.value || '<MCP_TOKEN>'}`,
  '',
  '接入要求：',
  '1. 使用 JSON-RPC 2.0 POST 到 MCP endpoint，Content-Type 为 application/json，并带上 Authorization Bearer token。',
  '2. 先调用 initialize，再用 tools/list 分页读取工具 schema。',
  '3. 工具调用使用 tools/call，优先读取 result.structuredContent。',
  '4. 不要一次性请求大结果；按下方 skill 的分页和上下文预算逐步扩展。',
  '5. 媒体、导出和 SSE 进度按返回 URL 在 App 侧加载，不要让模型内联二进制内容。',
].join('\n'))
const mcpSkillText = computed(() => mcpSkillBundleText.value || mcpSkillFallback)
const mcpTokenText = computed(() => mcpToken.value || '加载中...')

const switchTrackClass = (enabled, disabled = false) => {
  if (disabled) return enabled ? 'bg-[#07b75b] opacity-50 cursor-not-allowed' : 'bg-[#d0d0d0] opacity-50 cursor-not-allowed'
  return enabled ? 'bg-[#07b75b] hover:brightness-95' : 'bg-[#d0d0d0] hover:brightness-95'
}

const formatBytes = (value) => {
  const n = Number(value || 0)
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let next = n
  let unitIndex = 0
  while (next >= 1024 && unitIndex < units.length - 1) {
    next /= 1024
    unitIndex += 1
  }
  const digits = next >= 100 || unitIndex === 0 ? 0 : next >= 10 ? 1 : 2
  return `${next.toFixed(digits)} ${units[unitIndex]}`
}

const applyDesktopOutputDirProgress = (progress) => {
  if (!progress || progress.active === false) {
    desktopOutputDirProgress.value = null
    return
  }
  desktopOutputDirProgress.value = { ...progress }
}

const refreshDesktopOutputDirProgress = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.getOutputDirChangeProgress) return
  try {
    const progress = await window.wechatDesktop.getOutputDirChangeProgress()
    applyDesktopOutputDirProgress(progress)
  } catch {}
}

const sectionElements = computed(() => [
  { key: 'desktop', el: desktopSectionRef.value },
  { key: 'voice', el: voiceSectionRef.value },
  { key: 'mcp', el: mcpSectionRef.value },
  { key: 'keys', el: keysSectionRef.value },
  { key: 'startup', el: startupSectionRef.value },
  { key: 'media', el: mediaSectionRef.value },
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

const scrollToFocusTarget = async () => {
  const focusTarget = String(props.focusTarget || '').trim()
  if (focusTarget === 'voice') {
    await nextTick()
    scrollToSection('voice')
    return
  }
  if (focusTarget !== 'log-file') return
  await nextTick()
  activeSection.value = 'desktop'
  const scrollHost = contentScrollRef.value
  const target = desktopLogFileRef.value
  if (!scrollHost || !target) return
  const scrollRect = scrollHost.getBoundingClientRect()
  const targetRect = target.getBoundingClientRect()
  const targetTop = scrollHost.scrollTop + targetRect.top - scrollRect.top
  scrollHost.scrollTo({
    top: Math.max(0, targetTop - 18),
    behavior: 'smooth',
  })
}

const onContentScroll = () => {
  const scrollHost = contentScrollRef.value
  if (!scrollHost) return
  if (String(props.focusTarget || '').trim() === 'log-file' && desktopLogFileRef.value) {
    const scrollRect = scrollHost.getBoundingClientRect()
    const targetRect = desktopLogFileRef.value.getBoundingClientRect()
    const targetIsVisible = targetRect.bottom > scrollRect.top + 16
      && targetRect.top < scrollRect.bottom - 16
    if (targetIsVisible) {
      activeSection.value = 'desktop'
      return
    }
  }
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

const fetchAdminEndpoint = async (url, options = {}) => {
  const apiBase = useApiBase()
  try {
    return await $fetch(url, {
      baseURL: apiBase,
      ...options,
    })
  } catch (e) {
    await reportServerErrorFromError(e, {
      method: options?.method || 'GET',
      requestUrl: url,
      source: 'SettingsDialog',
      apiBase,
    })
    throw e
  }
}

const waitForBackendHealth = async (timeoutMs = 30_000) => {
  if (!process.client || typeof window === 'undefined') return
  const apiBase = useApiBase()
  const healthUrl = `${String(apiBase || '').replace(/\/api\/?$/, '')}/api/health`
  const startedAt = Date.now()
  while (true) {
    try {
      const r = await fetch(healthUrl, { method: 'GET' })
      if (r && r.status < 500) return
    } catch {}
    if (Date.now() - startedAt > timeoutMs) throw new Error(`后端启动超时：${healthUrl}`)
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
}

const normalizeVoiceModelDownloadPercent = (value) => {
  const percent = Number(value)
  return Number.isFinite(percent) ? Math.max(0, Math.min(100, Math.round(percent))) : 0
}

const normalizeVoiceModelDownloadBytes = (value) => {
  const bytes = Number(value)
  return Number.isFinite(bytes) ? Math.max(0, bytes) : 0
}

const isVoiceModelDeletePending = (modelId) => voiceModelDeletePendingIds.value.includes(String(modelId || '').trim())

const setVoiceModelDeletePending = (modelId, pending) => {
  const id = String(modelId || '').trim()
  if (!id) return
  const ids = new Set(voiceModelDeletePendingIds.value)
  if (pending) ids.add(id)
  else ids.delete(id)
  voiceModelDeletePendingIds.value = [...ids]
}

const voiceModelDownloadGeneration = (modelId) => voiceModelDownloadGenerations.get(String(modelId || '').trim()) || 0

const invalidateVoiceModelDownload = (modelId) => {
  const id = String(modelId || '').trim()
  const generation = voiceModelDownloadGeneration(id) + 1
  voiceModelDownloadGenerations.set(id, generation)
  return generation
}

const canDeleteVoiceModel = (model) => !!model?.id && (
  model.deletable
  || isVoiceModelDownloading(model)
  || isVoiceModelActionBusy(model.id, 'download')
  || isVoiceModelDeletePending(model.id)
)

const applyVoiceTranscriptionStatus = (status) => {
  if (!status || typeof status !== 'object') return
  const requestedDevice = String(status.requestedDevice || status.device || 'cpu').trim().toLowerCase()
  voiceDevicePreference.value = requestedDevice === 'cuda' ? 'cuda' : 'cpu'
  voiceDeviceSource.value = String(status.deviceSource || 'default').trim() || 'default'
  voiceActiveDevice.value = String(status.activeDevice || '').trim().toLowerCase()
  voiceModel.value = String(status.model || 'medium').trim() || 'medium'
  voiceModelSource.value = String(status.modelSettingSource || 'default').trim() || 'default'
  voiceModels.value = (Array.isArray(status.models) ? status.models : []).map((item) => {
    const id = String(item?.id || '').trim()
    const deleting = isVoiceModelDeletePending(id)
    const downloaded = !deleting && item?.downloaded === true
    let downloadStatus = String(item?.downloadStatus || 'idle').trim().toLowerCase()
    if (deleting) downloadStatus = 'idle'
    // A completed job describes the last download attempt, not the current files.
    if ((!downloaded && downloadStatus === 'done') || (downloaded && downloadStatus === 'error')) {
      downloadStatus = 'idle'
    }
    return {
      id,
      name: String(item?.name || id).trim() || id,
      size: String(item?.size || '大小未知').trim(),
      speed: String(item?.speed || '速度未知').trim(),
      quality: String(item?.quality || '质量未知').trim(),
      description: String(item?.description || '').trim(),
      recommended: item?.recommended === true,
      selected: item?.selected === true || id === voiceModel.value,
      downloaded,
      downloadable: item?.downloadable !== false,
      managed: item?.managed === true,
      deletable: item?.deletable !== false,
      source: String(item?.source || '').trim(),
      reason: String(item?.reason || '').trim(),
      downloadStatus,
      downloadError: downloadStatus === 'error' ? String(item?.downloadError || '').trim() : '',
      downloadJobId: ['queued', 'running'].includes(downloadStatus)
        ? String(item?.downloadJobId || '').trim()
        : '',
      downloadPercent: normalizeVoiceModelDownloadPercent(item?.downloadPercent),
      downloadedBytes: normalizeVoiceModelDownloadBytes(item?.downloadedBytes),
      totalBytes: normalizeVoiceModelDownloadBytes(item?.totalBytes),
      downloadStage: String(item?.downloadStage || '').trim(),
    }
  }).filter((item) => item.id)
  voiceStatusReason.value = String(status.reason || '').trim()
  voiceCuda.value = status.cuda && typeof status.cuda === 'object' ? status.cuda : null
  voiceFallbackReason.value = String(status.fallbackReason || '').trim()
  scheduleVoiceModelDownloadPolling()
}

const isVoiceModelDownloading = (model) => ['queued', 'running'].includes(String(model?.downloadStatus || '').toLowerCase())

const voiceModelDownloadPercent = (model) => normalizeVoiceModelDownloadPercent(model?.downloadPercent)

const voiceModelDownloadStageText = (model) => {
  if (String(model?.downloadStatus || '').toLowerCase() === 'queued') return '等待下载'
  const stage = String(model?.downloadStage || '').trim().toLowerCase()
  if (/prepar|metadata|resolv/.test(stage)) return '准备下载'
  if (/final|install|validat|verify/.test(stage)) return '正在校验模型'
  return '正在下载'
}

const voiceModelDownloadProgressText = (model) => {
  const percent = voiceModelDownloadPercent(model)
  const downloadedBytes = normalizeVoiceModelDownloadBytes(model?.downloadedBytes)
  const totalBytes = normalizeVoiceModelDownloadBytes(model?.totalBytes)
  if (totalBytes > 0) return `${percent}% · ${formatBytes(downloadedBytes)} / ${formatBytes(totalBytes)}`
  if (downloadedBytes > 0) return `${formatBytes(downloadedBytes)} 已下载`
  return voiceModelDownloadStageText(model)
}

const voiceModelDownloadButtonText = (model) => {
  if (isVoiceModelDownloading(model)) {
    const stage = voiceModelDownloadStageText(model)
    return normalizeVoiceModelDownloadBytes(model?.totalBytes) > 0
      ? `${stage} ${voiceModelDownloadPercent(model)}%`
      : stage
  }
  if (isVoiceModelActionBusy(model?.id, 'download')) return '准备下载...'
  return '下载'
}

const isVoiceModelActionBusy = (modelId, type = '') => {
  const action = voiceModelAction.value
  if (!type) return !!action.id
  return action.id === String(modelId || '') && action.type === type
}

const voiceModelStateText = (model) => {
  const status = String(model?.downloadStatus || '').toLowerCase()
  if (status === 'queued') return '等待下载'
  if (status === 'running') return `正在下载 ${voiceModelDownloadPercent(model)}%`
  if (model?.downloaded) return model?.source === 'external-cache' ? '共享缓存' : '已下载'
  if (status === 'error') return '下载失败'
  return model?.downloadable ? '未下载' : '不可用'
}

const voiceModelStateClass = (model) => {
  const status = String(model?.downloadStatus || '').toLowerCase()
  if (isVoiceModelDownloading(model) || model?.downloaded) return 'text-[var(--app-accent)]'
  if (status === 'error') return 'text-[var(--danger-color)]'
  return 'text-[var(--app-text-muted)]'
}

const updateVoiceModelDownload = (modelId, job) => {
  const id = String(modelId || '').trim()
  if (isVoiceModelDeletePending(id)) return
  const status = String(job?.status || 'idle').trim().toLowerCase()
  const active = ['queued', 'running'].includes(status)
  voiceModels.value = voiceModels.value.map((model) => model.id === id
    ? {
        ...model,
        downloadStatus: status,
        downloadError: String(job?.error || '').trim(),
        downloadJobId: active ? String(job?.jobId || model.downloadJobId || '').trim() : '',
        downloadPercent: normalizeVoiceModelDownloadPercent(job?.percent),
        downloadedBytes: normalizeVoiceModelDownloadBytes(job?.downloadedBytes),
        totalBytes: normalizeVoiceModelDownloadBytes(job?.totalBytes),
        downloadStage: String(job?.stage || '').trim(),
      }
    : model)
}

const clearVoiceModelDownloadState = (modelId) => {
  const id = String(modelId || '').trim()
  voiceModels.value = voiceModels.value.map((model) => model.id === id
    ? {
        ...model,
        downloaded: false,
        downloadStatus: 'idle',
        downloadError: '',
        downloadJobId: '',
        downloadPercent: 0,
        downloadedBytes: 0,
        totalBytes: 0,
        downloadStage: '',
      }
    : model)
}

const clearVoiceModelDownloadPolling = () => {
  if (!voiceModelDownloadTimer) return
  clearTimeout(voiceModelDownloadTimer)
  voiceModelDownloadTimer = null
}

const pollVoiceModelDownloads = async () => {
  const active = voiceModels.value.filter((model) => (
    isVoiceModelDownloading(model)
    && model.downloadJobId
    && !isVoiceModelDeletePending(model.id)
  ))
  if (!active.length) return

  let terminalJobSeen = false
  await Promise.all(active.map(async (model) => {
    const generation = voiceModelDownloadGeneration(model.id)
    try {
      const job = await api.getVoiceTranscriptionModelDownload(model.downloadJobId)
      if (generation !== voiceModelDownloadGeneration(model.id) || isVoiceModelDeletePending(model.id)) return
      updateVoiceModelDownload(model.id, job)
      terminalJobSeen ||= ['done', 'error'].includes(String(job?.status || '').toLowerCase())
    } catch (e) {
      if (generation !== voiceModelDownloadGeneration(model.id) || isVoiceModelDeletePending(model.id)) return
      const message = e?.message || `读取 ${model.name} 下载状态失败`
      voiceModelError.value = message
      updateVoiceModelDownload(model.id, { status: 'error', error: message })
    }
  }))

  if (terminalJobSeen) {
    try {
      applyVoiceTranscriptionStatus(await api.getVoiceTranscriptionStatus())
    } catch (e) {
      voiceModelError.value = e?.message || '刷新模型状态失败'
    }
  }
  scheduleVoiceModelDownloadPolling()
}

function scheduleVoiceModelDownloadPolling() {
  if (voiceModelDownloadTimer || !props.open) return
  if (!voiceModels.value.some((model) => (
    isVoiceModelDownloading(model)
    && model.downloadJobId
    && !isVoiceModelDeletePending(model.id)
  ))) return
  voiceModelDownloadTimer = setTimeout(async () => {
    voiceModelDownloadTimer = null
    await pollVoiceModelDownloads()
  }, 1000)
}

const startVoiceModelDownload = async (model) => {
  if (!model?.id || !model.downloadable || isVoiceModelDownloading(model) || isVoiceModelActionBusy(model.id)) return
  const generation = voiceModelDownloadGeneration(model.id)
  voiceModelAction.value = { id: model.id, type: 'download' }
  voiceModelError.value = ''
  voiceModelMessage.value = ''
  const startRequest = api.downloadVoiceTranscriptionModel(model.id)
  voiceModelDownloadStartPromises.set(model.id, startRequest)
  try {
    const job = await startRequest
    if (generation !== voiceModelDownloadGeneration(model.id) || isVoiceModelDeletePending(model.id)) return
    updateVoiceModelDownload(model.id, job)
    voiceModelMessage.value = `${model.name} 已加入下载队列。`
    scheduleVoiceModelDownloadPolling()
  } catch (e) {
    if (generation !== voiceModelDownloadGeneration(model.id) || isVoiceModelDeletePending(model.id)) return
    voiceModelError.value = e?.message || `下载 ${model.name} 失败`
  } finally {
    if (voiceModelDownloadStartPromises.get(model.id) === startRequest) {
      voiceModelDownloadStartPromises.delete(model.id)
    }
    if (isVoiceModelActionBusy(model.id, 'download')) voiceModelAction.value = { id: '', type: '' }
  }
}

const selectVoiceModel = async (model) => {
  if (!model?.id || !model.downloaded || model.selected || voiceModelLocked.value || isVoiceModelActionBusy(model.id)) return
  const generation = voiceModelDownloadGeneration(model.id)
  voiceModelAction.value = { id: model.id, type: 'select' }
  voiceModelError.value = ''
  voiceModelMessage.value = ''
  try {
    const resp = await api.setVoiceTranscriptionModel(model.id)
    if (generation !== voiceModelDownloadGeneration(model.id) || isVoiceModelDeletePending(model.id)) return
    applyVoiceTranscriptionStatus(resp?.configuration || resp)
  } catch (e) {
    if (generation !== voiceModelDownloadGeneration(model.id) || isVoiceModelDeletePending(model.id)) return
    voiceModelError.value = e?.message || `选择 ${model.name} 失败`
  } finally {
    if (isVoiceModelActionBusy(model.id, 'select')) voiceModelAction.value = { id: '', type: '' }
  }
}

const removeVoiceModel = async (model) => {
  if (!canDeleteVoiceModel(model) || isVoiceModelDeletePending(model.id)) return
  const stoppingDownload = isVoiceModelDownloading(model) || isVoiceModelActionBusy(model.id, 'download')
  const confirmMessage = stoppingDownload
    ? `确定停止 ${model.name} 模型的下载并删除已下载的临时文件吗？`
    : `确定删除本机上的 ${model.name} 模型吗？需要时可重新下载。`
  if (!window.confirm(confirmMessage)) return

  invalidateVoiceModelDownload(model.id)
  setVoiceModelDeletePending(model.id, true)
  voiceModelAction.value = { id: model.id, type: 'delete' }
  voiceModelError.value = ''
  voiceModelMessage.value = ''
  clearVoiceModelDownloadPolling()
  clearVoiceModelDownloadState(model.id)
  scheduleVoiceModelDownloadPolling()
  try {
    const pendingStart = voiceModelDownloadStartPromises.get(model.id)
    if (pendingStart) {
      try {
        await pendingStart
      } catch {}
    }
    const result = await api.deleteVoiceTranscriptionModel(model.id)
    try {
      applyVoiceTranscriptionStatus(await api.getVoiceTranscriptionStatus())
    } catch (e) {
      voiceModelError.value = e?.message || '模型已删除，但刷新模型状态失败'
    }
    const freedBytes = Number(result?.freedBytes || 0)
    voiceModelMessage.value = freedBytes > 0
      ? `已删除 ${model.name}，释放 ${formatBytes(freedBytes)}。`
      : `${model.name} 的本地缓存已清理。`
  } catch (e) {
    setVoiceModelDeletePending(model.id, false)
    try {
      applyVoiceTranscriptionStatus(await api.getVoiceTranscriptionStatus())
    } catch {}
    voiceModelError.value = e?.message || `删除 ${model.name} 失败`
  } finally {
    setVoiceModelDeletePending(model.id, false)
    if (isVoiceModelActionBusy(model.id, 'delete')) voiceModelAction.value = { id: '', type: '' }
    scheduleVoiceModelDownloadPolling()
  }
}

const voiceTranscriptDeleteErrorMessage = (error) => {
  const detail = error?.data?.detail || error?.detail
  const code = String(detail?.code || error?.code || '').trim().toLowerCase()
  const status = Number(error?.statusCode || error?.status || error?.response?.status || 0)
  if (code === 'batch_busy' || status === 409) {
    return '仍有账号正在批量转写，请先完成或取消后重试。'
  }
  if (detail && typeof detail === 'object') {
    return String(detail.message || '删除全部本项目转写结果失败')
  }
  return String(detail || error?.message || '删除全部本项目转写结果失败')
}

const deleteAllProjectVoiceTranscripts = async () => {
  if (voiceTranscriptDeleteBusy.value) return
  const confirmation = '此操作不可撤销：将删除所有账号中由本项目 Whisper 生成的全部转写文字。微信原生转写、原始语音和已下载模型都会保留。确定继续吗？'
  if (!window.confirm(confirmation)) return

  voiceTranscriptDeleteBusy.value = true
  voiceTranscriptDeleteError.value = ''
  voiceTranscriptDeleteMessage.value = ''
  voiceTranscriptDeleteWarning.value = ''
  try {
    const result = await api.deleteAllVoiceTranscriptionCache()
    notifyProjectVoiceTranscriptsInvalidated(result)

    const accountsScanned = Math.max(0, Number(result?.accountsScanned || 0))
    const accountsChanged = Math.max(0, Number(result?.accountsChanged || 0))
    const deletedMessages = Math.max(0, Number(result?.deletedMessages || 0))
    const failures = Array.isArray(result?.failures) ? result.failures.length : 0
    const summary = `已扫描 ${accountsScanned} 个账号，其中 ${accountsChanged} 个账号删除了 ${deletedMessages} 条本项目转写结果。`
    if (String(result?.status || '').toLowerCase() === 'partial' || failures > 0) {
      const failureSummary = failures > 0 ? `另有 ${failures} 个账号未能清理。` : '部分账号未能清理。'
      voiceTranscriptDeleteWarning.value = `部分清理完成：${summary}${failureSummary}微信原生转写、原始语音和模型均已保留。`
    } else {
      voiceTranscriptDeleteMessage.value = `${summary}微信原生转写、原始语音和模型均已保留。`
    }
  } catch (error) {
    voiceTranscriptDeleteError.value = voiceTranscriptDeleteErrorMessage(error)
  } finally {
    voiceTranscriptDeleteBusy.value = false
  }
}

const refreshVoiceTranscriptionStatus = async () => {
  if (!process.client || typeof window === 'undefined') return
  voiceStatusLoading.value = true
  voiceDeviceError.value = ''
  voiceModelError.value = ''
  try {
    applyVoiceTranscriptionStatus(await api.getVoiceTranscriptionStatus())
  } catch (e) {
    voiceDeviceError.value = e?.message || '读取语音转文字运行状态失败'
  } finally {
    voiceStatusLoading.value = false
  }
}

const setVoiceDevice = async (device) => {
  const next = String(device || '').trim().toLowerCase()
  if (!['cpu', 'cuda'].includes(next) || voiceDeviceBusy.value || voiceDeviceLocked.value) return
  if (next === 'cuda' && !voiceCudaAvailable.value) return

  voiceDeviceBusy.value = true
  voiceDeviceError.value = ''
  try {
    const resp = await api.setVoiceTranscriptionDevice(next)
    applyVoiceTranscriptionStatus(resp?.configuration || resp)
  } catch (e) {
    voiceDeviceError.value = e?.message || '设置语音转文字推理设备失败'
    await refreshVoiceTranscriptionStatus()
  } finally {
    voiceDeviceBusy.value = false
  }
}

const copyMcpText = async (key, text) => {
  if (!process.client || typeof window === 'undefined') return
  const value = String(text || '').trim()
  if (!value) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const el = document.createElement('textarea')
      el.value = value
      el.setAttribute('readonly', '')
      el.style.position = 'fixed'
      el.style.left = '-9999px'
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    mcpCopiedKey.value = key
    if (mcpCopiedTimer) clearTimeout(mcpCopiedTimer)
    mcpCopiedTimer = setTimeout(() => {
      if (mcpCopiedKey.value === key) mcpCopiedKey.value = ''
    }, 1600)
  } catch {}
}

const refreshSavedKeys = async () => {
  if (!process.client || typeof window === 'undefined') return
  keysLoading.value = true
  keysError.value = ''
  try {
    try {
      await chatAccountsStore.ensureLoaded?.()
    } catch {}
    const account = String(keysAccount.value || keySelectedAccount.value || '').trim()
    keysAccount.value = account
    const resp = await api.getSavedKeys(account ? { account } : {})
    const keys = (resp && resp.keys) || {}
    dbKey.value = String(keys.db_key || '').trim()
    imageXorKey.value = String(keys.image_xor_key || '').trim()
    imageAesKey.value = String(keys.image_aes_key || '').trim()
    imageKeyVerified.value = keys.image_key_verified === true
    keysLoaded.value = true
  } catch (e) {
    keysError.value = e?.message || '读取密钥失败'
  } finally {
    keysLoading.value = false
  }
}

const onKeysAccountChange = async (event) => {
  keysAccount.value = String(event?.target?.value || '').trim()
  await refreshSavedKeys()
}

const refreshMcpLanAccess = async () => {
  if (!process.client || typeof window === 'undefined') return
  mcpLanAccessLoading.value = true
  mcpLanAccessError.value = ''
  try {
    if (window.wechatDesktop?.getMcpLanAccess) {
      const resp = await window.wechatDesktop.getMcpLanAccess()
      mcpLanAccessEnabled.value = !!resp?.enabled
      applyMcpAccessInfo(resp)
      return
    }
    const resp = await fetchAdminEndpoint('/admin/mcp-access')
    mcpLanAccessEnabled.value = !!resp?.enabled
    applyMcpAccessInfo(resp)
  } catch (e) {
    mcpLanAccessError.value = e?.message || '读取 MCP 接入状态失败'
  } finally {
    mcpLanAccessLoading.value = false
  }
}

const refreshMcpToken = async () => {
  if (!process.client || typeof window === 'undefined') return
  mcpTokenLoading.value = true
  mcpTokenError.value = ''
  try {
    const resp = await fetchAdminEndpoint('/admin/mcp-token')
    const token = String(resp?.token || '').trim()
    if (!token) throw new Error('MCP token is empty')
    mcpToken.value = token
  } catch (e) {
    mcpTokenError.value = e?.message || '读取 MCP Token 失败'
  } finally {
    mcpTokenLoading.value = false
  }
}

const resetMcpToken = async () => {
  if (!process.client || typeof window === 'undefined') return
  mcpTokenLoading.value = true
  mcpTokenError.value = ''
  try {
    const resp = await fetchAdminEndpoint('/admin/mcp-token/reset', { method: 'POST' })
    const token = String(resp?.token || '').trim()
    if (!token) throw new Error('MCP token is empty')
    mcpToken.value = token
    mcpCopiedKey.value = 'token-reset'
    if (mcpCopiedTimer) clearTimeout(mcpCopiedTimer)
    mcpCopiedTimer = setTimeout(() => {
      if (mcpCopiedKey.value === 'token-reset') mcpCopiedKey.value = ''
    }, 1600)
    await refreshMcpSkillBundle()
  } catch (e) {
    mcpTokenError.value = e?.message || '重置 MCP Token 失败'
  } finally {
    mcpTokenLoading.value = false
  }
}

const refreshMcpSkillBundle = async () => {
  if (!process.client || typeof window === 'undefined') return
  mcpSkillBundleLoading.value = true
  mcpSkillBundleError.value = ''
  try {
    if (!mcpToken.value) await refreshMcpToken()
    const resp = await $fetch('/mcp/skill/bundle', {
      baseURL: mcpEndpoint.value.replace(/\/mcp$/, ''),
      headers: mcpToken.value ? { Authorization: `Bearer ${mcpToken.value}` } : {},
    })
    const bundleText = String(resp?.bundleText || '').trim()
    if (!bundleText) throw new Error('Skill bundle is empty')
    mcpSkillBundleText.value = bundleText
  } catch (e) {
    mcpSkillBundleError.value = e?.message || '读取 skill 失败，当前显示内置精简版'
    if (!mcpSkillBundleText.value) mcpSkillBundleText.value = ''
  } finally {
    mcpSkillBundleLoading.value = false
  }
}

const setMcpLanAccess = async (enabled) => {
  if (!process.client || typeof window === 'undefined') return
  mcpLanAccessLoading.value = true
  mcpLanAccessError.value = ''
  mcpLanAccessMessage.value = ''
  const previous = mcpLanAccessEnabled.value
  mcpLanAccessEnabled.value = !!enabled
  try {
    if (window.wechatDesktop?.setMcpLanAccess) {
      const resp = await window.wechatDesktop.setMcpLanAccess(!!enabled)
      mcpLanAccessEnabled.value = !!resp?.enabled
      applyMcpAccessInfo(resp)
      mcpLanAccessMessage.value = resp?.changed ? 'MCP 局域网接入已更新，后端已重启。' : 'MCP 局域网接入状态未变化。'
      await refreshMcpSkillBundle()
      return
    }

    const resp = await fetchAdminEndpoint('/admin/mcp-access', {
      method: 'POST',
      body: { enabled: !!enabled },
    })
    mcpLanAccessEnabled.value = !!resp?.enabled
    applyMcpAccessInfo(resp)
    mcpLanAccessMessage.value = resp?.changed ? 'MCP 局域网接入已更新，正在等待后端重启。' : 'MCP 局域网接入状态未变化。'
    if (resp?.changed) {
      await waitForBackendHealth(30_000)
      await refreshMcpLanAccess()
      mcpLanAccessMessage.value = 'MCP 局域网接入已更新，后端已恢复。'
    }
    await refreshMcpSkillBundle()
  } catch (e) {
    mcpLanAccessEnabled.value = previous
    mcpLanAccessError.value = e?.message || '设置 MCP 接入状态失败'
    await refreshMcpLanAccess()
  } finally {
    mcpLanAccessLoading.value = false
  }
}

const toggleMcpLanAccess = async () => {
  if (mcpLanAccessLoading.value) return
  await setMcpLanAccess(!mcpLanAccessEnabled.value)
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
      const resp = await fetchAdminEndpoint('/admin/port')
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

const refreshDesktopOutputDir = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.getOutputDir && !window.wechatDesktop?.getOutputDirInfo) return
  desktopOutputDirLoading.value = true
  desktopOutputDirError.value = ''
  try {
    if (window.wechatDesktop?.getOutputDirInfo) {
      const info = await window.wechatDesktop.getOutputDirInfo()
      desktopOutputDir.value = String(info?.path || '').trim()
      desktopOutputDirDefault.value = String(info?.defaultPath || '').trim()
      desktopOutputDirPending.value = String(info?.pendingPath || '').trim()
      desktopOutputDirIsDefault.value = !!info?.isDefault
      desktopOutputDirCanChange.value = info?.canChange !== false
      desktopOutputDirUnavailableReason.value = String(info?.changeUnavailableReason || '').trim()
      desktopOutputDirInput.value = desktopOutputDir.value || desktopOutputDirDefault.value
      if (info?.lastError) {
        desktopOutputDirError.value = String(info.lastError || '').trim()
      }
      return
    }

    const v = await window.wechatDesktop.getOutputDir()
    desktopOutputDir.value = String(v || '').trim()
    desktopOutputDirDefault.value = desktopOutputDir.value
    desktopOutputDirPending.value = ''
    desktopOutputDirIsDefault.value = true
    desktopOutputDirCanChange.value = false
    desktopOutputDirUnavailableReason.value = '当前桌面环境不支持修改 output 目录'
    desktopOutputDirInput.value = desktopOutputDir.value
  } catch (e) {
    desktopOutputDirError.value = e?.message || '读取 output 目录失败'
  } finally {
    desktopOutputDirLoading.value = false
  }
}

const onDesktopOpenOutputDir = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.openOutputDir) return
  desktopOutputDirLoading.value = true
  desktopOutputDirError.value = ''
  try {
    const res = await window.wechatDesktop.openOutputDir()
    if (res?.path) desktopOutputDir.value = String(res.path || '').trim()
  } catch (e) {
    desktopOutputDirError.value = e?.message || '打开 output 目录失败'
  } finally {
    desktopOutputDirLoading.value = false
  }
}

const onDesktopChooseOutputDir = async () => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.chooseDirectory) return
  desktopOutputDirError.value = ''
  desktopOutputDirMessage.value = ''
  try {
    const result = await window.wechatDesktop.chooseDirectory({ title: '选择新的 output 目录' })
    if (result && !result.canceled && Array.isArray(result.filePaths) && result.filePaths.length > 0) {
      desktopOutputDirInput.value = String(result.filePaths[0] || '').trim()
    }
  } catch (e) {
    desktopOutputDirError.value = e?.message || '选择 output 目录失败'
  }
}

const applyDesktopOutputDir = async (nextDir) => {
  if (!process.client || typeof window === 'undefined') return
  if (!window.wechatDesktop?.setOutputDir) {
    desktopOutputDirError.value = '当前桌面环境不支持修改 output 目录'
    return
  }
  if (!desktopOutputDirCanChange.value) {
    desktopOutputDirError.value = desktopOutputDirUnavailableReason.value || '当前环境不支持修改 output 目录'
    return
  }
  desktopOutputDirApplying.value = true
  desktopOutputDirError.value = ''
  desktopOutputDirMessage.value = ''
  desktopOutputDirProgress.value = null
  try {
    const res = await window.wechatDesktop.setOutputDir(String(nextDir ?? '').trim())
    if (res?.success === false) {
      desktopOutputDirError.value = String(res?.error || '修改 output 目录失败').trim()
      await refreshDesktopOutputDir()
      return
    }
    await refreshDesktopOutputDir()
    desktopOutputDirMessage.value = String(
      res?.message || (res?.changed === false ? 'output 目录未变化' : 'output 目录已更新')
    ).trim()
  } catch (e) {
    desktopOutputDirError.value = e?.message || '修改 output 目录失败'
    await refreshDesktopOutputDir()
  } finally {
    desktopOutputDirApplying.value = false
  }
}

const onDesktopOutputDirApply = async () => {
  await applyDesktopOutputDir(desktopOutputDirInput.value)
}

const onDesktopOutputDirReset = async () => {
  desktopOutputDirInput.value = desktopOutputDirDefault.value
  await applyDesktopOutputDir('')
}

const refreshBackendLogFileInfo = async () => {
  if (!process.client || typeof window === 'undefined') return
  desktopLogFileLoading.value = true
  desktopLogFileError.value = ''
  try {
    const resp = await fetchAdminEndpoint('/admin/log-file')
    desktopLogFilePath.value = String(resp?.path || '').trim()
  } catch (e) {
    desktopLogFileError.value = e?.message || '读取日志文件失败'
  } finally {
    desktopLogFileLoading.value = false
  }
}

const onOpenBackendLogFile = async () => {
  if (!process.client || typeof window === 'undefined') return
  desktopLogFileOpening.value = true
  desktopLogFileError.value = ''
  try {
    const resp = await fetchAdminEndpoint('/admin/log-file/open', { method: 'POST' })
    if (resp?.path) desktopLogFilePath.value = String(resp.path || '').trim()
  } catch (e) {
    desktopLogFileError.value = e?.message || '打开日志文件失败'
  } finally {
    desktopLogFileOpening.value = false
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

    let currentBackendPort = null
    try {
      const info = await fetchAdminEndpoint('/admin/port')
      const p = Number(info?.port)
      if (Number.isInteger(p) && p >= 1 && p <= 65535) currentBackendPort = p
    } catch {}
    const uiPort = (() => {
      const rawPort = String(window.location?.port || '').trim()
      if (rawPort) return Number(rawPort)
      return window.location?.protocol === 'https:' ? 443 : 80
    })()
    const isUiServedByBackend = !!(currentBackendPort && uiPort === currentBackendPort)

    await fetchAdminEndpoint('/admin/port', {
      method: 'POST',
      body: { port: n },
    })

    let protocol = String(window.location?.protocol || 'http:')
    if (protocol !== 'http:' && protocol !== 'https:') protocol = 'http:'
    const host = String(window.location?.hostname || '').trim() || '127.0.0.1'
    const nextOrigin = `${protocol}//${host}:${n}`
    writeApiBaseOverride(`${nextOrigin}/api`)
    invalidateApiBaseCache()

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

const toggleDesktopDefaultToChat = () => {
  const next = !desktopDefaultToChatWhenData.value
  desktopDefaultToChatWhenData.value = next
  writeLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, next)
}

const loadCdnImageStatus = async () => {
  try {
    const res = await api.getCdnImageStatus()
    cdnImageEnabled.value = res?.enabled === true
    const limit = Number(res?.dailyLimit)
    if (Number.isFinite(limit) && limit > 0) cdnImageDailyLimit.value = limit
  } catch {
    // 读取失败保持默认关闭
  }
}

const toggleCdnImage = async () => {
  if (cdnImageLoading.value) return
  const next = !cdnImageEnabled.value
  cdnImageLoading.value = true
  cdnImageEnabled.value = next
  try {
    const res = await api.toggleCdnImage(next)
    cdnImageEnabled.value = res?.enabled === true
  } catch {
    cdnImageEnabled.value = !next
  } finally {
    cdnImageLoading.value = false
  }
}

const toggleSnsUseCache = () => {
  const next = !snsUseCache.value
  snsUseCache.value = next
  writeLocalBoolSetting(SNS_SETTING_USE_CACHE_KEY, next)
}

const onDesktopCheckUpdates = async () => {
  await desktopUpdate.manualCheck()
}

const refreshSettingsDialogData = async () => {
  if (!process.client || typeof window === 'undefined') return

  const tasks = [
    refreshDesktopBackendPort(),
    refreshVoiceTranscriptionStatus(),
    refreshMcpLanAccess(),
    refreshMcpToken(),
    refreshBackendLogFileInfo(),
    refreshSavedKeys(),
  ]


  if (isDesktopEnv.value) {
    void desktopUpdate.initListeners()
    tasks.push(refreshDesktopAutoLaunch())
    tasks.push(refreshDesktopCloseBehavior())
    tasks.push(refreshDesktopOutputDir())
    tasks.push(refreshDesktopOutputDirProgress())
  }

  await Promise.allSettled(tasks)

  // skill bundle 依赖 token / access host；先让弹窗可交互，再后台补齐这块文本。
  void refreshMcpSkillBundle()
}

watch(() => props.open, async (isOpen) => {
  if (!isOpen) {
    clearVoiceModelDownloadPolling()
    return
  }
  await refreshSettingsDialogData()
  await scrollToFocusTarget()
}, { immediate: false })

watch(() => props.focusTarget, async () => {
  if (!props.open) return
  await scrollToFocusTarget()
})
const desktopUpdateLastCheckFailed = computed(() => /失败|错误|异常/.test(
  String(desktopUpdate.lastCheckMessage.value || '')
))

onMounted(async () => {
  if (process.client && typeof window !== 'undefined') {
    const isElectron = /electron/i.test(String(navigator.userAgent || ''))
    isDesktopEnv.value = isElectron && !!window.wechatDesktop
    window.addEventListener('keydown', onEscKeydown)
    if (window.wechatDesktop?.onOutputDirChangeProgress) {
      removeDesktopOutputDirProgressListener = window.wechatDesktop.onOutputDirChangeProgress((progress) => {
        applyDesktopOutputDirProgress(progress)
      })
    }
  }

  desktopDefaultToChatWhenData.value = readLocalBoolSetting(DESKTOP_SETTING_DEFAULT_TO_CHAT_KEY, false)
  snsUseCache.value = readLocalBoolSetting(SNS_SETTING_USE_CACHE_KEY, true)
  void loadCdnImageStatus()

  if (props.open) await refreshSettingsDialogData()

  await nextTick()
  onContentScroll()
})

onBeforeUnmount(() => {
  if (!process.client || typeof window === 'undefined') return
  window.removeEventListener('keydown', onEscKeydown)
  if (mcpCopiedTimer) {
    clearTimeout(mcpCopiedTimer)
    mcpCopiedTimer = null
  }
  clearVoiceModelDownloadPolling()
  if (typeof removeDesktopOutputDirProgressListener === 'function') {
    removeDesktopOutputDirProgressListener()
    removeDesktopOutputDirProgressListener = null
  }
})
</script>

<style scoped>
.voice-setting-focus:focus-visible {
  outline: 2px solid var(--app-accent);
  outline-offset: 2px;
}

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
