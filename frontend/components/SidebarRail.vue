<template>
  <div
    class="sidebar-rail border-r flex flex-col"
  >
    <div
      v-if="isMacosDesktop"
      class="macos-sidebar-titlebar-spacer"
      aria-hidden="true"
    />
    <div class="flex-1 flex flex-col justify-start pt-0 gap-0">
      <!-- Avatar -->
      <div class="w-full h-[60px] flex items-center justify-center">
        <button
          type="button"
          class="group relative w-[40px] h-[40px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0 ring-1 ring-transparent transition hover:ring-[#07b75b]/40"
          :title="avatarButtonTitle"
          @click="openAccountDialog"
        >
          <img v-if="selfAvatarUrl" :src="selfAvatarUrl" alt="avatar" class="w-full h-full object-cover" />
          <div
            v-else
            class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
            :style="{ backgroundColor: '#4B5563' }"
          >
            我
          </div>
        </button>
      </div>

      <!-- Chat -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="聊天"
        @click="goChat"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isChatRoute }">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Edits -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="修改记录"
        @click="goEdits"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isEditsRoute }">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Moments -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="朋友圈"
        @click="goSns"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isSnsRoute }">
            <svg
              class="w-full h-full"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="14.31" y1="8" x2="20.05" y2="17.94" />
              <line x1="9.69" y1="8" x2="21.17" y2="8" />
              <line x1="7.38" y1="12" x2="13.12" y2="2.06" />
              <line x1="9.69" y1="16" x2="3.95" y2="6.06" />
              <line x1="14.31" y1="16" x2="2.83" y2="16" />
              <line x1="16.62" y1="12" x2="10.88" y2="21.94" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Favorites -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="收藏"
        @click="goFavorites"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isFavoritesRoute }">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M6.5 4.5A2.5 2.5 0 0 1 9 2h6a2.5 2.5 0 0 1 2.5 2.5V21L12 17.5 6.5 21V4.5Z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Contacts -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="联系人"
        @click="goContacts"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isContactsRoute }">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
              <circle cx="10" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
        </div>
      </div>

      <div
          class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="服务号"
          @click="goBiz"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isBizRoute }">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M11 5L6 9H2v6h4l5 4V5z"></path>
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            </svg>
          </div>
        </div>
      </div>

      <!-- Mini Programs -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="小程序"
        @click="goMiniPrograms"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon sidebar-rail-icon-mini-program w-[20px] h-[20px]" :class="{ 'sidebar-rail-icon-active': isMiniProgramsRoute }">
            <svg class="w-full h-full" viewBox="0 0 1025 1024" fill="currentColor" aria-hidden="true">
              <path d="M740.672 37.504c156.352 0 283.52 115.584 283.52 258.496 0 44.416-13.056 87.872-36.608 127.04-35.648 57.216-92.672 99.584-161.664 119.744a161.408 161.408 0 0 1-45.184 7.36 52.8 52.8 0 0 1-53.76-52.928c0-29.76 23.68-52.864 53.76-52.864 2.112 0 6.528 0 11.904-2.048 46.336-12.8 82.944-39.168 103.424-74.24 13.952-22.144 20.48-46.72 20.48-72.064 0-83.84-78.72-152.512-174.72-152.512a197.76 197.76 0 0 0-94.72 24.32c-50.816 28.544-80.896 76.16-80.896 128.192v443.904c0 89.984-50.752 172.672-134.848 219.328-45.184 25.408-96 38.272-147.712 38.272-156.288 0-283.52-115.648-283.52-258.56 0-44.352 13.12-87.872 36.608-127.04 35.648-57.216 92.736-99.584 161.664-119.68 19.328-5.312 32.384-7.36 45.184-7.36 30.272 0 53.824 23.36 53.824 52.864a52.8 52.8 0 0 1-53.76 52.928c-2.176 0-6.592 0-11.904 2.048-46.4 13.76-82.944 40.32-103.424 74.176-14.016 22.208-20.48 46.72-20.48 72.128 0 83.84 78.72 152.448 175.616 152.448a197.76 197.76 0 0 0 94.784-24.256c50.752-28.608 80.832-76.224 80.832-128.192V296.192c0-89.984 50.752-172.608 134.848-219.328a283.52 283.52 0 0 1 146.752-39.36z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Finder / Live -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="视频号 / 直播"
        @click="goFinder"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isFinderRoute }">
            <svg class="w-full h-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="5" width="14" height="14" rx="2" />
              <path d="M17 9l4-2v10l-4-2" />
              <path d="M8.5 9.2v5.6L13 12l-4.5-2.8Z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Payments -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="转账 / 红包"
        @click="goPayments"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[18px] h-[18px]" :class="{ 'sidebar-rail-icon-active': isPaymentsRoute }">
            <svg class="w-full h-full" viewBox="0 0 1109 1024" fill="currentColor" aria-hidden="true">
              <path d="M391.183105 392.073178H42.628017a18.472141 18.472141 0 0 1-14.209339-30.976359l330.651321-355.233477a18.472141 18.472141 0 0 1 31.971013 12.646311v227.349426a18.472141 18.472141 0 0 0 18.472141 18.330047H1089.856308a18.614234 18.614234 0 0 1 18.472141 18.472141v90.93977a18.472141 18.472141 0 0 1-18.472141 18.472141H391.183105z m325.962239 239.853644H1065.700432a18.472141 18.472141 0 0 1 14.209339 30.976359l-330.367134 355.233477a18.472141 18.472141 0 0 1-31.971013-12.646311V778.851388a18.472141 18.472141 0 0 0-18.472141-18.472141H18.472141a18.472141 18.472141 0 0 1-18.472141-18.472141v-91.650237a18.472141 18.472141 0 0 1 18.472141-18.47214h698.673203z" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Wrapped -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="年度总结"
        @click="goWrapped"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': isWrappedRoute }">
            <svg
              class="w-full h-full"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <rect x="4" y="5" width="16" height="15" rx="2" />
              <path d="M8 3v4" />
              <path d="M16 3v4" />
              <path d="M4 9h16" />
              <path d="M8.5 15l2-2 1.5 1.5 3-3" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Export -->
      <div
        v-if="showGlobalExportEntry"
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        title="导出"
        @click="openExportDialog"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <div class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': exportDialogOpen }">
            <svg
              class="w-full h-full"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M12 3v11" />
              <path d="M7.5 10.5L12 15l4.5-4.5" />
              <path d="M4 19h16" />
            </svg>
          </div>
        </div>
      </div>

      <!-- ImgHelper (Auto download large images) -->
      <div
        v-if="imgHelperSupported"
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center group"
        :class="imgHelperBusy ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'"
        :title="imgHelperTitle"
        @click="toggleImgHelper"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <svg
            class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]"
            :class="{ 'sidebar-rail-icon-active': imgHelperEnabled }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
            <path d="M12 9v5m-2-2l2 2 2-2" />
          </svg>
        </div>
      </div>

      <!-- Privacy -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        @click="privacyStore.toggle"
        :title="privacyMode ? '关闭隐私模式' : '开启隐私模式'"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <svg class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': privacyMode }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path v-if="privacyMode" stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
            <path v-else stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
            <circle v-if="!privacyMode" cx="12" cy="12" r="3" />
          </svg>
        </div>
      </div>

      <!-- Theme -->
      <div
        class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
        :title="themeStore.isDark ? '切换浅色模式' : '切换深色模式'"
        @click="themeStore.toggle"
      >
        <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
          <svg
            v-if="themeStore.isDark"
            class="sidebar-rail-icon sidebar-rail-icon-active w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="4.5" />
            <path d="M12 2.5v2.2M12 19.3v2.2M4.93 4.93l1.56 1.56M17.51 17.51l1.56 1.56M2.5 12h2.2M19.3 12h2.2M4.93 19.07l1.56-1.56M17.51 6.49l1.56-1.56" />
          </svg>
          <svg
            v-else
            class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M21 12.79A9 9 0 1 1 11.21 3c-.08.5-.12 1.01-.12 1.54a8.25 8.25 0 0 0 8.37 8.25c.52 0 1.03-.04 1.54-.12Z" />
          </svg>
        </div>
      </div>

      <div class="mt-auto">
        <!-- Guide -->
        <div
          class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          title="引导页"
          @click="goGuide"
        >
          <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
            <svg class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M3 10.5L12 3l9 7.5" />
              <path d="M5 9.5V20h14V9.5" />
              <path d="M10 20v-6h4v6" />
            </svg>
          </div>
        </div>

        <!-- Settings -->
        <div
          class="sidebar-rail-action w-full h-[var(--sidebar-rail-step)] flex items-center justify-center cursor-pointer group"
          @click="goSettings"
          title="设置"
        >
          <div class="sidebar-rail-plate w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md flex items-center justify-center transition-colors bg-transparent">
            <svg class="sidebar-rail-icon w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)]" :class="{ 'sidebar-rail-icon-active': settingsDialogOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div
    v-if="accountDialogOpen"
    class="account-info-dialog fixed inset-0 z-[130] flex items-center justify-center bg-black/35 px-4"
    @click.self="closeAccountDialog"
  >
    <div class="account-info-dialog-panel w-full max-w-[520px] overflow-hidden rounded-[12px] border border-[#e7e7e7] bg-white shadow-2xl">
      <div class="flex items-center justify-between border-b border-[#efefef] px-4 py-3">
        <div class="text-[14px] font-semibold text-[#222]">账号切换</div>
        <button
          type="button"
          class="flex h-7 w-7 items-center justify-center rounded-md text-[#888] transition hover:bg-[#f2f2f2] hover:text-[#222]"
          title="关闭"
          :disabled="accountDeleteLoading"
          @click="closeAccountDialog"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      <div class="space-y-3 px-4 py-4">
        <div class="rounded-[10px] border border-[#ededed] bg-[#fafafa] p-2">
          <div class="mb-2 flex items-center justify-between px-1">
            <div class="text-[12px] font-medium text-[#444]">可切换账号</div>
            <button
              type="button"
              class="text-[11px] text-[#07b75b] hover:text-[#04994c] disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="chatAccounts.loading"
              @click="refreshSwitchableAccounts"
            >
              {{ chatAccounts.loading ? '刷新中...' : '刷新' }}
            </button>
          </div>

          <div v-if="chatAccounts.loading && !switchableAccountItems.length" class="px-1 py-2 text-[12px] text-[#7a7a7a]">
            正在加载可切换账号...
          </div>
          <div v-else-if="!switchableAccountItems.length" class="space-y-1 px-1 py-2">
            <div class="text-[12px] text-[#666]">暂无可切换账号</div>
            <div class="text-[11px] leading-relaxed text-[#8a8a8a]">
              只有已经获取并保存“数据库密钥 + 图片密钥”的账号会出现在这里。
            </div>
            <ErrorNotice v-if="chatAccounts.error" :message="chatAccounts.error" compact class="text-[11px] text-red-600" />
          </div>
          <div v-else class="max-h-[260px] space-y-1 overflow-y-auto pr-1">
            <button
              v-for="item in switchableAccountItems"
              :key="item.account"
              type="button"
              class="flex w-full items-center gap-3 rounded-[8px] border px-2.5 py-2 text-left transition"
              :class="item.active ? 'border-[#07b75b]/45 bg-[#ecfff5]' : 'border-transparent bg-white hover:border-[#e4e4e4] hover:bg-[#f7f7f7]'"
              :disabled="accountDeleteLoading"
              @click="selectAccountFromDialog(item.account)"
            >
              <div class="h-[38px] w-[38px] shrink-0 overflow-hidden rounded-md bg-gray-300">
                <img
                  v-if="item.avatarUrl && !accountAvatarBroken[item.account]"
                  :src="item.avatarUrl"
                  alt="avatar"
                  class="h-full w-full object-cover"
                  loading="lazy"
                  @error="markAccountAvatarBroken(item.account)"
                />
                <div
                  v-else
                  class="flex h-full w-full items-center justify-center text-xs font-bold text-white"
                  :style="{ backgroundColor: '#4B5563' }"
                >
                  {{ accountFallbackText(item.account) }}
                </div>
              </div>
              <div class="min-w-0 flex-1">
                <div class="truncate text-[13px] font-semibold text-[#222]">{{ item.account }}</div>
              </div>
              <div class="flex shrink-0 items-center gap-1">
                <span class="rounded-full bg-[#eefbf4] px-1.5 py-0.5 text-[10px] font-medium text-[#07964c]">DB</span>
                <span class="rounded-full bg-[#eefbf4] px-1.5 py-0.5 text-[10px] font-medium text-[#07964c]">图片</span>
              </div>
            </button>
          </div>
        </div>

        <div v-if="accountInfoLoading" class="text-[12px] text-[#7a7a7a]">正在加载账号信息...</div>
        <template v-else>
          <div class="flex items-center gap-3">
            <div class="w-[42px] h-[42px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">
              <img v-if="selfAvatarUrl" :src="selfAvatarUrl" alt="avatar" class="w-full h-full object-cover" />
              <div
                v-else
                class="w-full h-full flex items-center justify-center text-white text-xs font-bold"
                :style="{ backgroundColor: '#4B5563' }"
              >
                我
              </div>
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate text-[14px] font-semibold text-[#222]">{{ selectedAccount || '未选择账号' }}</div>
              <div class="mt-0.5 text-[11px] text-[#8a8a8a]">账号标识（wxid）</div>
            </div>
          </div>

            <div class="rounded-[8px] border border-[#ededed] bg-[#fafafa] px-3 py-2 text-[12px] text-[#5f5f5f] space-y-1.5">
            <div class="flex items-start justify-between gap-3">
              <span class="text-[#8a8a8a] shrink-0">本地解密库数量</span>
              <span class="font-medium text-[#333]">{{ accountInfo?.database_count ?? '—' }}</span>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-[#8a8a8a] shrink-0">数据目录</span>
              <span class="break-all text-right text-[#444]">{{ accountDataPath }}</span>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-[#8a8a8a] shrink-0">最近会话库更新时间</span>
              <span class="text-[#444]">{{ sessionUpdatedAtText }}</span>
            </div>
          </div>
        </template>

        <div class="rounded-[8px] border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
          仅删除本项目中的该账号解析数据/缓存/编辑记录，不会删除微信客户端中的任何聊天内容或账号数据。
        </div>

        <button
          type="button"
          class="w-full rounded-[8px] border border-red-200 bg-red-50 px-3 py-2 text-[12px] font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!selectedAccount || accountDeleteLoading"
          @click="deleteCurrentAccountData"
        >
          {{ accountDeleteLoading ? '删除中...' : '删除当前账号的项目数据' }}
        </button>
        <div class="text-[11px] text-[#8a8a8a]">删除成功后将自动返回引导页。</div>

        <ErrorNotice v-if="accountInfoError" :message="accountInfoError" compact class="text-[11px] text-red-600" />
        <ErrorNotice v-if="accountDeleteError" :message="accountDeleteError" compact class="text-[11px] text-red-600" />
      </div>
    </div>
  </div>

  <GlobalExportDialog v-if="showGlobalExportEntry" :open="exportDialogOpen" @close="closeExportDialog" />
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useChatAccountsStore } from '~/stores/chatAccounts'
import { useImgHelperStore } from '~/stores/imgHelper'
import { usePrivacyStore } from '~/stores/privacy'
import { useThemeStore } from '~/stores/theme'
import { withErrorLogGuidance } from '~/composables/useErrorNotice'

const route = useRoute()

const chatAccounts = useChatAccountsStore()
const {
  selectedAccount,
  switchableAccounts,
} = storeToRefs(chatAccounts)

const privacyStore = usePrivacyStore()
const { privacyMode } = storeToRefs(privacyStore)

const themeStore = useThemeStore()
themeStore.init()

const imgHelperStore = useImgHelperStore()
const { enabled: imgHelperEnabled, supported: imgHelperSupported, checking: imgHelperChecking, toggling: imgHelperToggling, error: imgHelperError } = storeToRefs(imgHelperStore)

const { open: settingsDialogOpen, openDialog: openSettingsDialog } = useSettingsDialog()
const { getChatAccountInfo, deleteChatAccount } = useApi()

const showGlobalExportEntry = true
const accountDialogOpen = ref(false)
const exportDialogOpen = ref(false)
const accountInfoLoading = ref(false)
const accountInfoError = ref('')
const accountInfo = ref(null)
const accountDeleteLoading = ref(false)
const accountDeleteError = ref('')
const accountInfoApiUnsupported = ref(false)
const deleteAccountApiUnsupported = ref(false)
const accountAvatarBroken = ref({})
const isMacosDesktop = ref(false)

const normalizeAccountName = (value) => String(value || '').trim()

const accountDataPath = computed(() => {
  const info = accountInfo.value || {}
  return String(
    info.dataSourcePath
    || info.dbStoragePath
    || info.wxidDir
    || info.path
    || (selectedAccount.value ? `output/databases/${selectedAccount.value}` : '—')
  )
})

const avatarButtonTitle = computed(() => {
  const count = Array.isArray(switchableAccounts.value) ? switchableAccounts.value.length : 0
  if (count > 1) return '切换账号'
  return '账号信息'
})

const accountAvatarUrl = (account) => {
  const acc = normalizeAccountName(account)
  if (!acc) return ''
  return `${apiBase}/chat/avatar?account=${encodeURIComponent(acc)}&username=${encodeURIComponent(acc)}`
}

const accountFallbackText = (account) => {
  const value = normalizeAccountName(account)
  if (!value) return '我'
  return value.slice(0, 1).toUpperCase()
}

const switchableAccountItems = computed(() => {
  const list = Array.isArray(switchableAccounts.value) ? switchableAccounts.value : []
  return list
    .map((account) => normalizeAccountName(account))
    .filter(Boolean)
    .map((account) => {
      return {
        account,
        active: account === normalizeAccountName(selectedAccount.value),
        avatarUrl: accountAvatarUrl(account),
      }
    })
})

const markAccountAvatarBroken = (account) => {
  const acc = normalizeAccountName(account)
  if (!acc) return
  accountAvatarBroken.value = { ...accountAvatarBroken.value, [acc]: true }
}

const sessionUpdatedAtText = computed(() => {
  const ts = Number(accountInfo.value?.session_updated_at || 0)
  if (!Number.isFinite(ts) || ts <= 0) return '—'
  try {
    return new Date(ts * 1000).toLocaleString('zh-CN')
  } catch {
    return '—'
  }
})

const isNotFoundError = (error) => {
  const status = Number(
    error?.statusCode
    ?? error?.status
    ?? error?.response?.status
    ?? error?.data?.statusCode
    ?? 0
  )
  return status === 404
}

const loadAccountInfoByDesktopBridge = async (account) => {
  if (!process.client || typeof window === 'undefined') return null
  if (!window.wechatDesktop?.getAccountInfo) return null
  const res = await window.wechatDesktop.getAccountInfo(account)
  return res && typeof res === 'object' ? res : null
}

const loadAccountInfo = async () => {
  accountInfoLoading.value = true
  accountInfoError.value = ''
  const account = String(selectedAccount.value || '').trim()
  if (!account) {
    accountInfo.value = null
    accountInfoLoading.value = false
    return
  }
  try {
    let lastError = null
    if (!accountInfoApiUnsupported.value) {
      try {
        const res = await getChatAccountInfo({ account })
        if (res?.status !== 'success') {
          throw new Error(res?.message || '读取账号信息失败')
        }
        accountInfo.value = res
        return
      } catch (e) {
        lastError = e
        if (isNotFoundError(e)) {
          accountInfoApiUnsupported.value = true
        }
      }
    }

    try {
      const fallback = await loadAccountInfoByDesktopBridge(account)
      if (fallback?.status === 'success') {
        accountInfo.value = fallback
        accountInfoError.value = ''
        return
      }
      if (fallback && fallback?.status && fallback.status !== 'success') {
        lastError = new Error(fallback?.message || '读取账号信息失败')
      } else if (!lastError) {
        lastError = new Error('读取账号信息失败')
      }
    } catch (fallbackErr) {
      if (!lastError) {
        lastError = fallbackErr
      }
    }

    accountInfo.value = null
    accountInfoError.value = lastError?.message || '读取账号信息失败'
  } finally {
    accountInfoLoading.value = false
  }
}

const deleteAccountDataByDesktopBridge = async (account) => {
  if (!process.client || typeof window === 'undefined') return null
  if (!window.wechatDesktop?.deleteAccountData) return null
  const res = await window.wechatDesktop.deleteAccountData(account)
  return res && typeof res === 'object' ? res : { status: 'success' }
}

const openAccountDialog = async () => {
  accountDialogOpen.value = true
  accountDeleteError.value = ''
  await loadAccountInfo()
}

const openExportDialog = () => {
  exportDialogOpen.value = true
}

const closeAccountDialog = () => {
  if (accountDeleteLoading.value) return
  accountDialogOpen.value = false
}

const closeExportDialog = () => {
  exportDialogOpen.value = false
}

watch(selectedAccount, () => {
  if (!accountDialogOpen.value) return
  void loadAccountInfo()
})

onMounted(async () => {
  isMacosDesktop.value = window?.wechatDesktop?.platform === 'darwin'
  await chatAccounts.ensureLoaded()
  if (process.client && typeof window !== 'undefined') {
    window.addEventListener('keydown', onWindowKeydown)
  }
})

onBeforeUnmount(() => {
  if (!process.client || typeof window === 'undefined') return
  window.removeEventListener('keydown', onWindowKeydown)
})

const apiBase = useApiBase()

const selfAvatarUrl = computed(() => {
  const acc = String(selectedAccount.value || '').trim()
  if (!acc) return ''
  return accountAvatarUrl(acc)
})

const refreshSwitchableAccounts = async () => {
  await chatAccounts.ensureLoaded({ force: true })
}

const selectAccountFromDialog = async (account) => {
  const next = normalizeAccountName(account)
  if (!next || accountDeleteLoading.value) return
  if (next === normalizeAccountName(selectedAccount.value)) return

  accountInfoError.value = ''
  accountDeleteError.value = ''
  accountInfo.value = null
  chatAccounts.setSelectedAccount(next)
}

const isChatRoute = computed(() => route.path?.startsWith('/chat'))
const isEditsRoute = computed(() => route.path?.startsWith('/edits'))
const isSnsRoute = computed(() => route.path?.startsWith('/sns'))
const isFavoritesRoute = computed(() => route.path?.startsWith('/favorites'))
const isContactsRoute = computed(() => route.path?.startsWith('/contacts'))
const isBizRoute = computed(() => route.path?.startsWith('/biz')) // 新增
const isMiniProgramsRoute = computed(() => route.path?.startsWith('/mini-programs'))
const isFinderRoute = computed(() => route.path?.startsWith('/finder'))
const isPaymentsRoute = computed(() => route.path?.startsWith('/payments'))
const isWrappedRoute = computed(() => route.path?.startsWith('/wrapped'))

const goChat = async () => { await navigateTo('/chat') }
const goEdits = async () => { await navigateTo('/edits') }
const goSns = async () => { await navigateTo('/sns') }
const goFavorites = async () => { await navigateTo('/favorites') }
const goContacts = async () => { await navigateTo('/contacts') }
const goBiz = async () => { await navigateTo('/biz') }
const goMiniPrograms = async () => { await navigateTo('/mini-programs') }
const goFinder = async () => { await navigateTo('/finder') }
const goPayments = async () => { await navigateTo('/payments') }
const goWrapped = async () => { await navigateTo('/wrapped') }
const goGuide = async () => { await navigateTo('/') }
const goSettings = () => { openSettingsDialog() }

const onWindowKeydown = (event) => {
  if (event?.key !== 'Escape') return
  if (exportDialogOpen.value) {
    return
  }
  event.preventDefault()
  if (accountDialogOpen.value) {
    closeAccountDialog()
  }
}

const deleteCurrentAccountData = async () => {
  const account = String(selectedAccount.value || '').trim()
  if (!account || accountDeleteLoading.value) return

  if (process.client && typeof window !== 'undefined') {
    const confirmed = window.confirm(
      '将删除当前账号在本项目中的数据（解析缓存、编辑记录、导出缓存等），不会删除微信客户端内容。确认删除吗？'
    )
    if (!confirmed) return
  }

  accountDeleteLoading.value = true
  accountDeleteError.value = ''
  try {
    let deleted = false
    let lastError = null

    if (!deleteAccountApiUnsupported.value) {
      try {
        const apiRes = await deleteChatAccount({ account })
        if (apiRes?.status && apiRes.status !== 'success') {
          throw new Error(apiRes?.message || '删除账号数据失败')
        }
        deleted = true
      } catch (apiErr) {
        lastError = apiErr
        if (isNotFoundError(apiErr)) {
          deleteAccountApiUnsupported.value = true
        }
      }
    }

    if (!deleted) {
      const desktopRes = await deleteAccountDataByDesktopBridge(account)
      if (!desktopRes) {
        throw lastError || new Error('删除账号数据失败')
      }
      if (desktopRes?.status && desktopRes.status !== 'success') {
        throw new Error(desktopRes?.message || '删除账号数据失败')
      }
    }

    accountDialogOpen.value = false
    await chatAccounts.ensureLoaded({ force: true })
    await navigateTo('/')
  } catch (e) {
    accountDeleteError.value = e?.message || '删除账号数据失败'
  } finally {
    accountDeleteLoading.value = false
  }
}

const imgHelperBusy = computed(() => !!imgHelperChecking.value || !!imgHelperToggling.value)

const imgHelperTitle = computed(() => {
  if (imgHelperEnabled.value) return '关闭自动下载大图'
  return imgHelperError.value ? withErrorLogGuidance(imgHelperError.value) : '开启自动下载大图'
})

const toggleImgHelper = async () => {
  if (imgHelperBusy.value) return
  await imgHelperStore.toggle()
}
</script>

<style scoped>
.sidebar-rail {
  width: 60px;
  min-width: 60px;
  max-width: 60px;
  background-color: var(--sidebar-rail-bg);
  border-color: var(--sidebar-rail-border);
  overflow-y: auto;
  scrollbar-width: none;
}

.macos-sidebar-titlebar-spacer {
  width: 100%;
  height: var(--desktop-titlebar-height, 32px);
  min-height: var(--desktop-titlebar-height, 32px);
  -webkit-app-region: drag;
}

.sidebar-rail::-webkit-scrollbar {
  display: none;
}

.sidebar-rail-plate {
  transition: background-color 0.15s ease;
}

.sidebar-rail-action:hover .sidebar-rail-plate {
  background-color: var(--sidebar-rail-hover);
}

.sidebar-rail-icon {
  color: var(--sidebar-rail-icon-color);
  transition: color 0.15s ease;
}

.sidebar-rail-icon-active {
  color: var(--sidebar-rail-icon-active-color);
}

</style>
