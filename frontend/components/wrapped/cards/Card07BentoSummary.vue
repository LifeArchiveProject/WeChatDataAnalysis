<template>
  <WrappedCardShell
    :card-id="Number(card?.id || 7)"
    :title="String(card?.title || '便当总览：一屏看完这一年')"
    :narrative="String(card?.narrative || '')"
    :variant="variant"
    :wide="true"
    :hide-chrome="true"
    class="h-full w-full"
    >
      <div
        ref="stageRoot"
        class="bento-stage"
        :class="[variant === 'slide' ? 'is-slide' : 'is-panel', !isOk ? 'is-loading' : '']"
        :aria-busy="!isOk"
        :aria-label="!isOk ? '便当总览正在生成' : null"
      >
      <div v-if="isOk" class="bento-container">
        <!-- 1. 发送消息条数 -->
        <div class="bento-card card-messages group">
          <div class="aura bg-blue-400/20 w-[120%] h-[120%] -top-[60%] -left-[20%]"></div>
          <div class="content justify-between relative">
            <div class="card-title z-10">
              <span class="text-blue-500/80">✈</span>
              发送消息条数
            </div>

            <div
              class="absolute inset-x-0 bottom-0 h-1/2 flex items-end opacity-20 group-hover:opacity-40 transition-opacity z-0 pointer-events-none"
            >
              <svg viewBox="0 0 100 40" preserveAspectRatio="none" class="w-full h-full text-blue-500">
                <path
                  d="M0 40 L0 30 C20 30, 30 15, 50 20 C70 25, 80 5, 100 10 L100 40 Z"
                  fill="currentColor"
                ></path>
              </svg>
            </div>

            <div class="mt-auto flex flex-col z-10 shrink-0">
              <div class="flex items-baseline gap-1.5 mb-1">
                <span class="text-6xl font-black tracking-tighter">{{ formatInt(totalMessages) }}</span>
                <span class="text-lg text-gray-500 font-medium">条</span>
              </div>
              <div
                class="text-[0.65rem] sm:text-xs text-blue-600 font-medium bg-blue-500/10 self-start px-2 py-0.5 rounded-full border border-blue-500/20"
              >
                平均每天发送 <span>{{ formatInt(messagesPerDayRounded) }}</span> 条
              </div>
            </div>
            <div class="bento-watermark text-blue-500">✈</div>
          </div>
        </div>

        <!-- 2. 发送消息字数 -->
        <div class="bento-card card-words group">
          <div class="aura bg-emerald-400/20 w-[150%] h-[200%] -bottom-[100%] right-[0%]"></div>
          <div class="content justify-between overflow-hidden">
            <div class="card-title">
              <span class="text-emerald-500/80">✍</span>
              发送消息字数
            </div>
            <div class="mt-auto flex flex-col items-start min-h-0">
              <div class="flex items-baseline gap-1.5 min-h-0">
                <span class="text-6xl font-black tracking-tighter">{{ sentCharsWan }}</span>
                <span class="text-lg text-gray-500 font-medium">万字</span>
              </div>
              <div
                class="text-[0.7rem] sm:text-[0.8rem] md:text-xs text-emerald-700 font-medium bg-emerald-500/10 inline-flex items-center px-2 py-1 sm:px-2.5 sm:py-1.5 rounded-full mt-1 border border-emerald-500/20 max-w-full overflow-hidden shrink-0"
              >
                <span class="mr-1.5 sm:mr-2 shrink-0">📖</span>
                <span class="truncate">相当于写了一本《了不起的盖茨比》</span>
              </div>
            </div>
            <div class="bento-watermark text-emerald-500">✍</div>
          </div>
        </div>

        <!-- 3. 新加好友数量 -->
        <div class="bento-card card-friends group">
          <div class="aura bg-yellow-400/25 w-[150%] h-[150%] top-[20%] left-[20%]"></div>
          <div class="content justify-between h-full relative">
            <div class="card-title z-10">
              <span class="text-yellow-500/80">➕</span>
              新加好友
            </div>

            <div
              class="absolute inset-0 flex items-center justify-center opacity-10 group-hover:opacity-30 transition-opacity z-0 pointer-events-none"
            >
              <div class="grid grid-cols-3 gap-2 sm:gap-3 p-4">
                <div class="w-1.5 h-1.5 rounded-full bg-yellow-500"></div>
                <div class="w-2 h-2 rounded-full bg-yellow-500"></div>
                <div class="w-1 h-1 rounded-full bg-yellow-500"></div>
                <div class="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
                <div class="w-1.5 h-1.5 rounded-full bg-yellow-500"></div>
                <div class="w-3 h-3 rounded-full bg-yellow-500"></div>
                <div class="w-1 h-1 rounded-full bg-yellow-500"></div>
                <div class="w-2 h-2 rounded-full bg-yellow-500"></div>
                <div class="w-1.5 h-1.5 rounded-full bg-yellow-500"></div>
              </div>
            </div>

            <div class="mt-auto flex flex-col z-10 shrink-0 mb-1">
              <div class="flex items-baseline gap-1">
                <span class="text-4xl font-black tracking-tighter text-yellow-500">{{ formatInt(addedFriends) }}</span>
                <span class="text-sm text-gray-500 ml-1">位</span>
              </div>
              <div class="text-[0.6rem] sm:text-[0.65rem] text-yellow-600 font-medium mt-0.5">扩列了全新的生活圈</div>
            </div>
            <div class="bento-watermark text-yellow-500">➕</div>
          </div>
        </div>

        <!-- 4. 最常活跃时间 -->
        <div class="bento-card card-time group">
          <div class="aura bg-purple-400/20 w-full h-full -top-[30%] -right-[30%]"></div>
          <div class="content flex flex-col justify-between h-full">
            <div class="card-title">
              <span class="text-purple-500/80">🕒</span>
              最常活跃时间
            </div>
            <div class="mt-auto mb-1 z-10 shrink-0">
              <div class="text-3xl font-black tracking-tighter">{{ mostActiveHourLabel }}</div>
              <div class="text-[0.6rem] sm:text-[0.65rem] text-purple-600 mt-0.5 opacity-90 truncate">
                {{ mostActiveHourDesc }}
              </div>
            </div>
            <div
              class="flex items-end gap-1.5 h-6 sm:h-8 opacity-60 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-auto"
            >
              <div class="w-full bg-black/10 rounded-t-sm h-[20%]"></div>
              <div class="w-full bg-black/10 rounded-t-sm h-[40%]"></div>
              <div class="w-full bg-black/10 rounded-t-sm h-[60%]"></div>
              <div
                class="w-full bg-purple-500 rounded-t-sm h-[100%] relative shadow-[0_0_8px_rgba(168,85,247,0.4)]"
              >
                <div
                  class="absolute -top-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 bg-white rounded-full shadow-sm"
                ></div>
              </div>
              <div class="w-full bg-black/10 rounded-t-sm h-[60%]"></div>
              <div class="w-full bg-black/10 rounded-t-sm h-[30%]"></div>
            </div>
            <div class="bento-watermark text-purple-500">🕒</div>
          </div>
        </div>

        <!-- 5. 年度聊天搭子 -->
        <div class="bento-card card-partner group">
          <div class="aura bg-pink-400/20 w-[150%] h-[150%] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
          <!-- Floating Hearts Background -->
          <div class="absolute inset-0 overflow-hidden pointer-events-none z-0" aria-hidden="true">
            <i class="fa-solid fa-heart floating-heart text-pink-300" style="left: 10%; animation-delay: 0s; font-size: 1.2rem;"></i>
            <i class="fa-solid fa-heart floating-heart text-rose-300" style="left: 30%; animation-delay: 1.5s; font-size: 1.5rem;"></i>
            <i class="fa-solid fa-heart floating-heart text-pink-200" style="left: 70%; animation-delay: 2.5s; font-size: 1rem;"></i>
            <i class="fa-solid fa-heart floating-heart text-red-300" style="left: 85%; animation-delay: 0.5s; font-size: 1.3rem;"></i>
          </div>

          <div class="content flex flex-col h-full overflow-hidden relative z-10">
            <div class="card-title shrink-0 relative z-20">
              <i class="fa-solid fa-heart text-pink-500 animate-pulse"></i>
              年度聊天搭子
            </div>

            <div class="partner-split-layout mt-1 flex-1 flex flex-row items-stretch gap-3">
              <div class="partner-profile-zone flex flex-col items-center justify-center w-[35%] shrink-0">
                <div class="relative w-[4.5rem] h-[4.5rem] sm:w-[5.5rem] sm:h-[5.5rem] mb-2 shrink-0">
                  <div
                    class="absolute inset-[-8px] bg-gradient-to-tr from-pink-400 to-rose-300 rounded-full animate-pulse opacity-40 blur-lg"
                  ></div>

                  <template v-if="bestBuddyAvatarUrl && !broken.bestBuddy">
                    <img
                      :src="bestBuddyAvatarUrl"
                      class="w-full h-full rounded-full border-[3px] border-white object-cover relative z-10 shadow-lg bg-gray-50 filter drop-shadow-[0_4px_12px_rgba(244,114,182,0.3)] transition-transform duration-500 hover:scale-105 wrapped-privacy-avatar"
                      :alt="bestBuddyName"
                      @error="markBroken('bestBuddy')"
                    />
                  </template>
                  <template v-else>
                    <div
                      class="w-full h-full rounded-full border-[3px] border-white relative z-10 shadow-lg bg-gray-50 flex items-center justify-center font-black text-xl text-pink-600 wrapped-privacy-avatar"
                    >
                      {{ avatarFallback(bestBuddyName) }}
                    </div>
                  </template>

                  <div
                    class="absolute -bottom-1 left-1/2 -translate-x-1/2 bg-gradient-to-r from-yellow-400 to-amber-500 text-white text-[10px] sm:text-[11px] px-2.5 py-0.5 rounded-full z-20 shadow-md border-[1.5px] border-white whitespace-nowrap font-black tracking-tight"
                  >
                    <i class="fa-solid fa-crown text-[9px] mr-0.5"></i> MVP
                  </div>
                </div>

                <div class="text-lg sm:text-xl font-black tracking-tight text-gray-800 text-center truncate w-full px-1 wrapped-privacy-name">
                  {{ bestBuddyName }}
                </div>
              </div>

              <div class="partner-metrics-zone flex-1 flex flex-col justify-center gap-2">
                <!-- Strip 1: Volume -->
                <div
                  class="partner-metric-strip bg-white/40 p-2 rounded-xl flex items-center gap-2.5 shadow-sm border border-white/50"
                >
                  <div
                    class="partner-metric-icon bg-gradient-to-br from-blue-400 to-blue-500 text-white w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm"
                  >
                    <i class="fa-solid fa-message text-xs"></i>
                  </div>
                  <div class="flex flex-col">
                    <span class="text-[10px] text-gray-500 font-bold uppercase tracking-wider">总互动</span>
                    <div class="flex items-baseline gap-1 leading-none">
                      <span class="text-xl font-black text-gray-800 tracking-tight">{{ formatInt(bestBuddyTotal) }}</span>
                      <span class="text-[10px] font-bold text-gray-400">次</span>
                    </div>
                  </div>
                </div>

                <!-- Strip 2: Streak -->
                <div
                  class="partner-metric-strip bg-white/40 p-2 rounded-xl flex items-center gap-2.5 shadow-sm border border-white/50"
                >
                  <div
                    class="partner-metric-icon bg-gradient-to-br from-orange-400 to-amber-500 text-white w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm"
                  >
                    <i class="fa-solid fa-fire text-xs"></i>
                  </div>
                  <div class="flex flex-col">
                    <span class="text-[10px] text-gray-500 font-bold uppercase tracking-wider">最长连聊</span>
                    <div class="flex items-baseline gap-1 leading-none">
                      <span class="text-xl font-black text-gray-800 tracking-tight">{{ bestBuddyStreakDaysLabel }}</span>
                      <span class="text-[10px] font-bold text-gray-400">天</span>
                    </div>
                  </div>
                </div>

                <!-- Strip 3: Resonance -->
                <div
                  class="partner-metric-strip bg-white/40 p-2 rounded-xl flex items-center gap-2.5 shadow-sm border border-white/50"
                >
                  <div
                    class="partner-metric-icon bg-gradient-to-br from-emerald-400 to-teal-500 text-white w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm"
                  >
                    <i class="fa-solid fa-clock text-xs"></i>
                  </div>
                  <div class="flex flex-col">
                    <span class="text-[10px] text-gray-500 font-bold uppercase tracking-wider">同频时刻</span>
                    <div class="flex items-baseline gap-1 leading-none">
                      <span class="text-xl font-black text-emerald-600 tracking-tight">{{ bestBuddyPeakLabel }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 5.1 最爱聊的群聊 -->
        <div class="bento-card card-group group">
          <div class="aura bg-sky-400/20 w-[120%] h-[120%] -bottom-[20%] -right-[20%]"></div>
          <div class="content flex flex-col h-full overflow-hidden">
            <div class="card-title shrink-0">
              <span class="text-sky-500/80">👥</span>
              最爱群聊
            </div>
            <div class="flex-grow flex items-center gap-3 mt-1 px-1 sm:px-2 min-h-0">
              <div class="shrink-0">
                <template v-if="topGroupAvatarUrl && !broken.topGroup">
                  <img
                    class="w-16 h-16 sm:w-20 sm:h-20 rounded-full border-2 border-white shadow-sm ring-1 ring-sky-500/20 bg-gray-50 object-cover wrapped-privacy-avatar"
                    :src="topGroupAvatarUrl"
                    :alt="topGroupName"
                    @error="markBroken('topGroup')"
                  />
                </template>
                <template v-else>
                  <div
                    class="w-16 h-16 sm:w-20 sm:h-20 rounded-full border-2 border-white shadow-sm ring-1 ring-sky-500/20 bg-sky-100 flex items-center justify-center font-black text-sky-700 wrapped-privacy-avatar"
                  >
                    {{ avatarFallback(topGroupName) }}
                  </div>
                </template>
              </div>

              <div class="flex flex-col min-w-0 flex-1">
                <div class="text-base sm:text-lg font-black tracking-tight text-gray-800 w-full truncate wrapped-privacy-name">{{ topGroupName }}</div>
                <div
                  class="mt-1 text-[10px] sm:text-xs font-semibold text-sky-600 bg-sky-500/10 px-3 py-1 rounded-full border border-sky-500/10 inline-flex items-center gap-1.5 max-w-full truncate self-start"
                >
                  <span class="shrink-0">🔥</span>
                  <span class="truncate"
                    >全年发了 <span class="font-bold">{{ formatInt(topGroupMessages) }}</span> 条</span
                  >
                </div>
              </div>

              <div class="shrink-0">
                <div
                  class="group-share-ring w-14 h-14 sm:w-16 sm:h-16 rounded-full p-[3px] shadow-[0_12px_26px_rgba(14,165,233,0.14)]"
                  :style="{ '--p': String(topGroupSharePct) }"
                >
                  <div
                    class="w-full h-full rounded-full bg-white/70 border border-white/80 backdrop-blur-xl flex flex-col items-center justify-center text-center leading-none"
                  >
                    <div class="text-sm sm:text-base font-black text-sky-700 tracking-tight">{{ topGroupSharePct }}%</div>
                    <div class="text-[8px] sm:text-[9px] font-semibold text-sky-600/80 mt-0.5">占全年</div>
                  </div>
                </div>
                <div class="mt-1 text-[9px] sm:text-[10px] font-semibold text-sky-700/70 text-center whitespace-nowrap">
                  日均 {{ topGroupDailyLabel }} 条
                </div>
              </div>
            </div>
            <div class="bento-watermark text-sky-500">👥</div>
          </div>
        </div>

        <!-- 5.2 回复速度 -->
        <div class="bento-card card-speed group">
          <div class="aura bg-orange-400/20 w-[150%] h-[150%] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
          <div class="content flex flex-col h-full overflow-hidden">
            <div class="card-title shrink-0">
              <span class="text-orange-500/80">⏱</span>
              回复速度
            </div>

            <div class="reply-bento">
              <div class="reply-subcard large">
                <div class="subcard-title relative z-10">中位数 P50</div>
                <div class="subcard-value text-transparent bg-clip-text bg-gradient-to-r from-orange-500 to-amber-500 relative z-10">
                  {{ replyP50Label }}
                </div>
                <div class="reply-subcard-icon text-orange-400 drop-shadow-sm transition-all group-hover:scale-110">⚡</div>
              </div>

              <div class="reply-subcard">
                <div class="reply-subcard-icon text-emerald-500">🚀</div>
                <div class="subcard-title text-emerald-700/60 flex items-center gap-1 relative z-10">
                  <span class="bg-emerald-100 rounded-full w-3 h-3 flex items-center justify-center shrink-0">🚀</span>
                  秒回
                </div>
                <div class="flex items-center gap-2 mt-[2px] min-w-0 w-full overflow-hidden relative z-10">
                  <span class="subcard-value text-emerald-600 truncate max-w-[50%]">{{ fastestReplyLabel }}</span>
                  <div class="ml-auto shrink-0" :title="fastestContactName">
                    <template v-if="fastestAvatarUrl && !broken.fastestAvatar">
                      <img
                        class="w-7 h-7 rounded-full bg-white border border-emerald-500/20 shadow-sm object-cover wrapped-privacy-avatar"
                        :src="fastestAvatarUrl"
                        :alt="fastestContactName"
                        @error="markBroken('fastestAvatar')"
                      />
                    </template>
                    <template v-else>
                      <div
                        class="w-7 h-7 rounded-full bg-emerald-50 border border-emerald-500/15 shadow-sm flex items-center justify-center text-[11px] font-black text-emerald-700 wrapped-privacy-avatar"
                      >
                        {{ avatarFallback(fastestContactName) }}
                      </div>
                    </template>
                  </div>
                </div>
              </div>

              <div class="reply-subcard">
                <div class="reply-subcard-icon text-rose-500">🐌</div>
                <div class="subcard-title text-rose-700/60 flex items-center gap-1 relative z-10">
                  <span class="bg-rose-100 rounded-full w-3 h-3 flex items-center justify-center shrink-0">🐌</span>
                  意念
                </div>
                <div class="flex items-center gap-2 mt-[2px] min-w-0 w-full overflow-hidden relative z-10">
                  <span class="subcard-value text-rose-500 truncate max-w-[50%]">{{ slowestReplyLabel }}</span>
                  <div class="ml-auto shrink-0" :title="slowestContactName">
                    <template v-if="slowestAvatarUrl && !broken.slowestAvatar">
                      <img
                        class="w-7 h-7 rounded-full bg-white border border-rose-500/20 shadow-sm object-cover wrapped-privacy-avatar"
                        :src="slowestAvatarUrl"
                        :alt="slowestContactName"
                        @error="markBroken('slowestAvatar')"
                      />
                    </template>
                    <template v-else>
                      <div
                        class="w-7 h-7 rounded-full bg-rose-50 border border-rose-500/15 shadow-sm flex items-center justify-center text-[11px] font-black text-rose-700 wrapped-privacy-avatar"
                      >
                        {{ avatarFallback(slowestContactName) }}
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 6. 年度口头禅 -->
        <div class="bento-card card-catchphrase group">
          <div class="aura bg-indigo-400/20 w-40 h-40 -top-10 -left-10"></div>
          <div class="content flex flex-col h-full">
            <div class="card-title">
              <span class="text-indigo-500/80">❝</span>
              年度口头禅
            </div>
            <div class="flex-grow flex items-center justify-center">
              <div
                class="text-3xl font-black text-transparent text-gradient bg-gradient-to-br from-blue-500 to-indigo-600 transform group-hover:scale-110 transition-transform"
              >
                "{{ topPhraseWord }}"
              </div>
            </div>
            <div class="text-[10px] sm:text-xs text-indigo-600 mt-auto text-center bg-indigo-500/10 rounded-full py-0.5 sm:py-1">
              说了 <span>{{ formatInt(topPhraseCount) }}</span> 次
            </div>
            <div class="bento-watermark text-indigo-400">❝</div>
          </div>
        </div>

        <!-- 8. 最爱的表情包 -->
        <div class="bento-card card-sticker group">
          <div class="aura bg-orange-400/15 w-full h-[80%] bottom-0 right-0"></div>
          <div class="content flex flex-col items-center h-full overflow-hidden">
            <div class="card-title shrink-0 self-start w-full">
              <span class="text-orange-500/80">🖼</span>
              最爱表情包
            </div>
            <div class="flex-grow flex flex-col items-center justify-center min-h-0 relative">
              <div
                class="absolute w-32 h-32 rounded-full bg-gradient-to-br from-orange-300/20 via-amber-300/12 to-yellow-300/8 blur-2xl pointer-events-none"
              ></div>
              <div class="relative w-full h-full flex items-center justify-center p-2">
                <template v-if="topStickerUrl && !broken.topSticker">
                  <img
                    v-if="topStickerMode === 'img'"
                    :src="topStickerUrl"
                    class="relative z-10 w-full h-full object-contain rounded-2xl filter drop-shadow-[0_8px_24px_rgba(249,115,22,0.18)] group-hover:scale-[1.04] group-hover:-rotate-1 transition-transform duration-500 ease-out"
                    alt="Top sticker"
                    @error="onTopStickerImgError"
                  />
                  <video
                    v-else
                    :src="topStickerUrl"
                    class="relative z-10 w-full h-full object-contain rounded-2xl filter drop-shadow-[0_8px_24px_rgba(249,115,22,0.18)] group-hover:scale-[1.04] group-hover:-rotate-1 transition-transform duration-500 ease-out"
                    autoplay
                    loop
                    muted
                    playsinline
                    preload="auto"
                    @error="onTopStickerVideoError"
                  />
                </template>
                <template v-else>
                  <div class="relative z-10 text-6xl opacity-60 filter drop-shadow-[0_8px_24px_rgba(249,115,22,0.12)]">🧩</div>
                </template>
              </div>
            </div>
            <div class="shrink-0 flex flex-col items-center gap-1.5 pb-1">
              <div class="flex items-baseline gap-1">
                <span
                  class="text-3xl sm:text-4xl font-black tracking-tight text-transparent text-gradient bg-gradient-to-br from-orange-500 to-amber-500"
                >
                  {{ formatInt(sentStickerCount) }}
                </span>
                <span class="text-xs sm:text-sm text-gray-400 font-semibold">次发送</span>
              </div>
              <div
                class="text-[9px] sm:text-[10px] font-semibold text-orange-700/80 bg-orange-500/8 border border-orange-500/12 px-2.5 py-0.5 rounded-full whitespace-nowrap"
              >
                占全年消息的 {{ stickerShareText }}
              </div>
            </div>
            <div class="bento-watermark text-orange-400">🖼</div>
          </div>
        </div>

        <!-- 9. 最爱的emoji -->
        <div class="bento-card card-emoji group">
          <div class="aura bg-yellow-400/20 w-[150%] h-[150%] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
          <div class="content w-full h-full flex flex-col items-center overflow-hidden">
            <div class="card-title self-start w-full shrink-0">
              <span class="text-yellow-500/80">☺</span>
              最爱emoji
            </div>
            <div class="flex-grow flex items-center justify-center w-full relative min-h-0">
              <div
                class="absolute w-20 h-20 rounded-full bg-gradient-to-br from-yellow-300/25 via-amber-300/15 to-orange-300/10 blur-xl pointer-events-none"
              ></div>

              <span
                class="scattered-emoji text-3xl"
                style="--tx: -4rem; --ty: -2.5rem; --s: 0.8; --r: -15deg; animation-delay: 0.1s; --o: 0.6;"
                >😂</span
              >
              <span
                class="scattered-emoji text-4xl"
                style="--tx: 4.5rem; --ty: -1.5rem; --s: 0.6; --r: 25deg; animation-delay: 0.2s; --o: 0.5;"
                >🤣</span
              >
              <span
                class="scattered-emoji text-2xl"
                style="--tx: -3.5rem; --ty: 3rem; --s: 0.7; --r: 10deg; animation-delay: 0.15s; --o: 0.5;"
                >❤️</span
              >
              <span
                class="scattered-emoji text-3xl"
                style="--tx: 3rem; --ty: 3.5rem; --s: 0.9; --r: -20deg; animation-delay: 0.05s; --o: 0.7;"
                >😭</span
              >
              <span
                class="scattered-emoji text-4xl"
                style="--tx: -0.5rem; --ty: -4rem; --s: 0.5; --r: 45deg; animation-delay: 0.25s; --o: 0.3;"
                >🙏</span
              >
              <span
                class="scattered-emoji text-2xl"
                style="--tx: 1rem; --ty: 4rem; --s: 0.65; --r: -35deg; animation-delay: 0.3s; --o: 0.45;"
                >👍</span
              >

              <template v-if="topEmojiKind === 'wechat' && topEmojiAssetPath && !broken.topEmoji">
                <img
                  :src="topEmojiAssetPath"
                  :alt="topEmojiLabel"
                  class="w-16 h-16 sm:w-20 sm:h-20 object-contain filter drop-shadow-[0_4px_12px_rgba(250,204,21,0.35)] group-hover:scale-[1.12] group-hover:-rotate-6 transition-all duration-300 cursor-pointer z-10 relative"
                  @error="markBroken('topEmoji')"
                />
              </template>
              <template v-else>
                <span
                  class="text-5xl sm:text-6xl filter drop-shadow-[0_4px_12px_rgba(250,204,21,0.5)] group-hover:scale-[1.25] group-hover:-rotate-12 transition-all duration-300 cursor-pointer z-10 relative"
                >
                  {{ topEmojiLabel }}
                </span>
              </template>
            </div>
            <div
              class="text-[9px] sm:text-[10px] font-semibold text-yellow-700/80 bg-yellow-500/10 border border-yellow-500/15 px-2.5 py-0.5 rounded-full whitespace-nowrap shrink-0"
            >
              使用了 <span class="font-black">{{ formatInt(topEmojiCount) }}</span> 次
            </div>
            <div class="bento-watermark text-yellow-500">☺</div>
          </div>
        </div>

        <!-- 7. 月度最佳好友 -->
        <div class="bento-card card-monthly group">
          <div class="aura bg-teal-400/20 w-[150%] h-[150%] -bottom-[20%] -right-[20%]"></div>
          <div class="content flex flex-col h-full overflow-hidden">
            <div class="card-title shrink-0">
              <span class="text-teal-600/80">📅</span>
              月度最佳好友
            </div>

            <div v-if="showMonthlyHero" class="monthly-hero">
              <div class="monthly-avatar-lg">
                <template v-if="monthlyMvpAvatarUrl && !broken.monthlyMvp">
                  <img :src="monthlyMvpAvatarUrl" class="wrapped-privacy-avatar" alt="MVP" @error="markBroken('monthlyMvp')" />
                </template>
                <template v-else>
                  <div class="monthly-avatar-fallback-lg wrapped-privacy-avatar">{{ avatarFallback(monthlyMvpName) }}</div>
                </template>
              </div>

              <div class="monthly-hero-info">
                <span
                  class="text-2xl sm:text-3xl font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-br from-teal-600 to-emerald-500 leading-none truncate wrapped-privacy-name"
                >
                  {{ monthlyMvpName }}
                </span>
                <span
                  class="text-[9px] sm:text-[10px] font-semibold text-teal-700/70 bg-teal-500/10 border border-teal-500/15 px-2 py-0.5 rounded-full whitespace-nowrap w-fit"
                >
                  上榜 <span>{{ monthlyMvpMonths }}</span>/12 个月
                </span>
              </div>

              <div class="monthly-metrics">
                <div v-for="m in monthlyMvpMetrics" :key="m.key" class="monthly-metric-item">
                  <div class="monthly-metric-header">
                    <span>{{ m.label }}</span>
                    <span class="metric-val">{{ m.pct }}</span>
                  </div>
                  <div class="monthly-metric-bar">
                    <div class="monthly-metric-fill" :style="{ width: `${m.pct}%` }"></div>
                  </div>
                </div>
              </div>
            </div>

            <div class="monthly-grid shrink-0 mt-auto" :class="showMonthlyHero ? '' : 'expanded'">
              <div
                v-for="item in monthlyCells"
                :key="item.month"
                class="monthly-cell"
                :class="item._isMvp ? 'is-mvp' : ''"
                :style="item._cellStyle"
                :title="`${item.month}月 · ${item._nameLabel} · ${formatInt(item.messages)} 条`"
              >
                <template v-if="item._avatarUrl && !broken['m-' + item.month]">
                  <img
                    class="monthly-avatar-sm wrapped-privacy-avatar"
                    :src="item._avatarUrl"
                    :alt="item._nameLabel"
                    @error="markBroken('m-' + item.month)"
                  />
                </template>
                <template v-else>
                  <div class="monthly-avatar-fallback-sm wrapped-privacy-avatar" :style="{ background: item._avatarFallbackBg }">
                    {{ avatarFallback(item._nameLabel) }}
                  </div>
                </template>
                <div class="monthly-cell-month">{{ item.month }}月</div>
                <div v-if="!showMonthlyHero" class="monthly-cell-name wrapped-privacy-name">{{ item._nameLabel }}</div>
              </div>
            </div>
            <div class="bento-watermark text-teal-600">📅</div>
          </div>
        </div>

        <!-- 10. 年度热力图 -->
        <div class="bento-card card-heatmap group">
          <div class="aura bg-emerald-400/15 w-[50%] h-[150%] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
          <div class="content flex flex-col h-full min-h-0">
            <div class="flex items-center justify-between gap-2 z-10">
              <div class="card-title mb-0">
                <span class="text-emerald-500/80">🗓</span>
                活跃时段热力图
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <div class="heatmap-year-tag">{{ heatmapYearLabel }}</div>
                <div class="heatmap-max-label">{{ heatmapMaxLabel }}</div>
              </div>
            </div>

            <div class="heatmap-shell relative z-10">
              <div class="heatmap-main">
                <div class="heatmap-weekday-col">
                  <span v-for="(w, i) in weekdayLabels" :key="i">{{ w }}</span>
                </div>
                <div class="heatmap-grid" aria-label="24x7 聊天活跃热力图">
                  <button
                    v-for="cell in heatmapCells"
                    :key="cell.key"
                    type="button"
                    class="heatmap-cell"
                    :style="{ backgroundColor: cell.bg, opacity: cell.opacity }"
                    :title="cell.title"
                    :aria-label="cell.title"
                  />
                </div>
              </div>

              <div class="heatmap-hour-row mt-1">
                <span class="heatmap-hour-spacer"></span>
                <span v-for="h in hourLabelRow" :key="h.key" class="heatmap-hour-label">{{ h.label }}</span>
              </div>

              <div class="heatmap-legend mt-3 justify-end w-full">
                <div class="heatmap-legend-scale flex items-center gap-1">
                  <span class="text-[0.6rem] text-emerald-800/40 font-semibold mr-1">少</span>
                  <div
                    v-for="(c, i) in heatmapLegendColors"
                    :key="i"
                    class="heatmap-legend-dot"
                    :style="{ backgroundColor: c, opacity: 1 }"
                  ></div>
                  <span class="text-[0.6rem] text-emerald-800/80 font-bold ml-1">多</span>
                </div>
              </div>
            </div>

            <div class="bento-watermark text-emerald-500">🗓</div>
          </div>
        </div>
      </div>
      <template v-if="!isOk">
        <!-- Loading animation (Card07 only): move bento-summary.html loader in full -->
        <div class="packing-scene" aria-hidden="true">
          <div class="bento-loader-box">
            <!-- Slot 1: Yearly Summary (Big 2x2) -->
            <div class="bento-slot slot-1">
              <div class="memory-piece piece-1">
                <i
                  class="fa-solid fa-envelope-open-text"
                  style="font-size: 3.5rem; opacity: 0.9; margin-bottom: 0.5rem;"
                ></i>
                <div class="piece-bar long" style="height: 8px; opacity: 0.2; width: 60%; margin-bottom: 6px;"></div>
                <div class="piece-bar long" style="height: 8px; opacity: 0.2; width: 40%;"></div>
              </div>
            </div>

            <!-- Slot 2: Best Buddy (Small) -->
            <div class="bento-slot slot-2">
              <div class="memory-piece piece-2">
                <i class="fa-solid fa-heart" style="font-size: 2.5rem; opacity: 0.9;"></i>
              </div>
            </div>

            <!-- Slot 3: Time (Small) -->
            <div class="bento-slot slot-3">
              <div class="memory-piece piece-3">
                <i class="fa-solid fa-moon" style="font-size: 2.2rem; opacity: 0.9;"></i>
                <div class="piece-bar short" style="height: 6px; width: 20px; margin-top: 6px; opacity: 0.3;"></div>
              </div>
            </div>

            <!-- Slot 4: Group (Wide) -->
            <div class="bento-slot slot-4">
              <div class="memory-piece piece-4" style="flex-direction: row; gap: 1.5rem;">
                <i class="fa-solid fa-users" style="font-size: 2.2rem; opacity: 0.9;"></i>
                <div style="display: flex; gap: 4px;">
                  <div
                    style="width: 10px; height: 10px; border-radius: 50%; background: currentColor; opacity: 0.3;"
                  ></div>
                  <div
                    style="width: 10px; height: 10px; border-radius: 50%; background: currentColor; opacity: 0.3;"
                  ></div>
                  <div
                    style="width: 10px; height: 10px; border-radius: 50%; background: currentColor; opacity: 0.3;"
                  ></div>
                </div>
              </div>
            </div>

            <!-- Slot 5: Emoji (Small) -->
            <div class="bento-slot slot-5">
              <div class="memory-piece piece-5">
                <i class="fa-solid fa-face-laugh-squint" style="font-size: 2.5rem; opacity: 0.9;"></i>
              </div>
            </div>
          </div>
        </div>

        <div class="bento-loading-title"><span class="bento-loading-emoji">🍱</span>便当装盒中…</div>
        <div class="loader-text" aria-live="polite" :class="{ fade: funLoaderTextFading }">{{ funLoaderText }}</div>
        <div class="bento-loading-desc">
          <template v-if="cardStatus === 'idle'">翻到此页后开始聚合生成，首次加载可能稍久。</template>
          <template v-else-if="cardStatus === 'loading'">正在聚合各页数据，这一页会比其它页久一点点。</template>
          <template v-else-if="cardStatus === 'error'">生成失败，可以重试一次。</template>
          <template v-else>正在准备数据…</template>
        </div>

        <div v-if="cardStatus === 'error'" class="bento-loading-error">{{ cardErrorText }}</div>

        <div class="bento-loading-actions">
          <button v-if="canRetry" type="button" class="bento-loading-btn" @click="onRetry">重试</button>
        </div>
      </template>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

// Hide deck-level chrome (top-left nav + year selector) when this bento card is visible.
const deckChromeHidden = inject('deckChromeHidden', ref(false))
const retryFromDeck = inject('wrappedRetryCard', null)
const stageRoot = ref(null)
const isVisible = ref(false)
let io = null

const cardStatus = computed(() => String(props.card?.status || '').trim().toLowerCase())
const isOk = computed(() => cardStatus.value === 'ok')
const cardErrorText = computed(() => {
  const s = String(props.card?.error || '').trim()
  return s || '未知错误'
})
const canRetry = computed(() => typeof retryFromDeck === 'function' && (cardStatus.value === 'error' || cardStatus.value === 'idle'))
const onRetry = async () => {
  if (typeof retryFromDeck !== 'function') return
  try {
    await retryFromDeck(Number(props.card?.id || 7))
  } catch {
    // ignore
  }
}

const updateVisibility = (v) => {
  isVisible.value = !!v
  if (props.variant === 'slide') {
    deckChromeHidden.value = !!v
  }
}

watch(
  () => props.variant,
  () => {
    updateVisibility(isVisible.value)
  }
)

onMounted(() => {
  if (!import.meta.client) return

  if (typeof IntersectionObserver !== 'undefined' && stageRoot.value) {
    io = new IntersectionObserver(
      (entries) => {
        const ent = entries && entries[0]
        updateVisibility(!!ent?.isIntersecting && (ent.intersectionRatio || 0) >= 0.35)
      },
      { threshold: [0, 0.35, 0.6, 1] }
    )
    io.observe(stageRoot.value)
  } else {
    updateVisibility(true)
  }
})

onBeforeUnmount(() => {
  io?.disconnect?.()
  io = null
  // Ensure deck chrome restores when leaving this card.
  if (props.variant === 'slide') deckChromeHidden.value = false
})

const FUN_LOADER_TEXTS = [
  '正在回收年度碎片...',
  '为您精心装盘组合...',
  '封存三百六十五个日夜...',
  '年度便当即将完美出炉...'
]
const funLoaderText = ref(FUN_LOADER_TEXTS[0])
const funLoaderTextFading = ref(false)
let funLoaderTextIndex = 0
let funLoaderInterval = null
let funLoaderFadeTimer = null

const stopFunLoaderCycle = () => {
  if (funLoaderInterval) clearInterval(funLoaderInterval)
  funLoaderInterval = null
  if (funLoaderFadeTimer) clearTimeout(funLoaderFadeTimer)
  funLoaderFadeTimer = null
  funLoaderTextFading.value = false
  funLoaderTextIndex = 0
}

const startFunLoaderCycle = () => {
  stopFunLoaderCycle()
  funLoaderTextIndex = 0
  funLoaderText.value = FUN_LOADER_TEXTS[0]
  funLoaderInterval = setInterval(() => {
    funLoaderTextIndex = (funLoaderTextIndex + 1) % FUN_LOADER_TEXTS.length
    funLoaderTextFading.value = true
    if (funLoaderFadeTimer) clearTimeout(funLoaderFadeTimer)
    funLoaderFadeTimer = setTimeout(() => {
      funLoaderText.value = FUN_LOADER_TEXTS[funLoaderTextIndex]
      funLoaderTextFading.value = false
    }, 300)
  }, 1800)
}

const updateFunLoader = () => {
  if (!import.meta.client) return
  if (!isVisible.value) {
    stopFunLoaderCycle()
    funLoaderText.value = FUN_LOADER_TEXTS[0]
    return
  }

  if (cardStatus.value === 'ok') {
    stopFunLoaderCycle()
    funLoaderText.value = '打包完成！'
    return
  }

  if (cardStatus.value === 'error') {
    stopFunLoaderCycle()
    funLoaderText.value = '生成失败，可以重试一次。'
    return
  }

  if (!funLoaderInterval) startFunLoaderCycle()
}

watch([cardStatus, isVisible], updateFunLoader, { immediate: true })
onBeforeUnmount(() => {
  stopFunLoaderCycle()
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const snapshot = computed(() => {
  const s = props.card?.data?.snapshot
  return s && typeof s === 'object' ? s : {}
})

const year = computed(() => Number(snapshot.value?.year || new Date().getFullYear() - 1))

const totalMessages = computed(() => Number(snapshot.value?.totalMessages || 0))
const messagesPerDay = computed(() => Number(snapshot.value?.messagesPerDay || 0))
const messagesPerDayRounded = computed(() => Math.round(messagesPerDay.value || 0))

const sentChars = computed(() => Number(snapshot.value?.sentChars || 0))
const sentCharsWan = computed(() => Number((sentChars.value / 10000).toFixed(1)).toFixed(1))

const addedFriends = computed(() => Number(snapshot.value?.addedFriends || 0))

const pad2 = (n) => String(Math.max(0, Number(n) || 0)).padStart(2, '0')
const formatHour = (h) => `${pad2(h)}:00`
const daysInYear = (y) => {
  const yy = Number(y)
  const isLeap = yy % 4 === 0 && (yy % 100 !== 0 || yy % 400 === 0)
  return isLeap ? 366 : 365
}

const mostActiveHour = computed(() => {
  const n = Number(snapshot.value?.mostActiveHour)
  return Number.isFinite(n) && n >= 0 && n <= 23 ? n : null
})

const mostActiveHourLabel = computed(() => (mostActiveHour.value === null ? '--:--' : formatHour(mostActiveHour.value)))
const mostActiveHourDesc = computed(() => {
  const h = Number(mostActiveHour.value)
  if (!Number.isFinite(h)) return '聊天节奏稳定在线'
  if (h >= 5 && h <= 8) return '早起高效开聊模式'
  if (h >= 9 && h <= 12) return '白天沟通主力时段'
  if (h >= 13 && h <= 18) return '午后消息最活跃'
  if (h >= 19 && h <= 23) return '夜晚交流持续在线'
  return '深夜灵感爆棚的夜猫子'
})

const formatDurationZh = (seconds) => {
  if (seconds === null || seconds === undefined || seconds === '') return '--'
  const s = Math.round(Number(seconds))
  if (!Number.isFinite(s) || s < 0) return '--'
  if (s < 60) return `${s}秒`
  if (s < 3600) {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return sec > 0 ? `${m}分${sec}秒` : `${m}分`
  }
  if (s < 86400) {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return m > 0 ? `${h}小时${m}分` : `${h}小时`
  }
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  return h > 0 ? `${d}天${h}小时` : `${d}天`
}

const apiBase = useApiBase()

const resolveMediaUrl = (value, opts = { backend: false }) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^(data:|blob:)/i.test(raw)) return raw
  if (/^https?:\/\//i.test(raw)) {
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw.startsWith('/') ? raw : `/${raw}`
}

const broken = reactive({})
const markBroken = (key) => {
  broken[String(key || '')] = true
}

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  return s ? s[0] : '?'
}

const bestBuddy = computed(() => {
  const o = snapshot.value?.bestBuddy
  return o && typeof o === 'object' ? o : null
})
const bestBuddyName = computed(() => String(bestBuddy.value?.displayName || '').trim() || '--')
const bestBuddyAvatarUrl = computed(() => resolveMediaUrl(bestBuddy.value?.avatarUrl, { backend: true }))
const bestBuddyTotal = computed(() => Number(bestBuddy.value?.totalMessages || 0))
const bestBuddyStreakDays = computed(() => Number(bestBuddy.value?.longestStreakDays || 0))
const bestBuddyStreakDaysLabel = computed(() => (bestBuddyStreakDays.value > 0 ? formatInt(bestBuddyStreakDays.value) : '--'))
const bestBuddyPeakLabel = computed(() => {
  const s = String(bestBuddy.value?.peakHourLabel || '').trim()
  if (s) return s
  const ph = Number(bestBuddy.value?.peakHour)
  if (Number.isFinite(ph) && ph >= 0 && ph <= 23) return formatHour(ph)
  return '--:--'
})

const topGroup = computed(() => {
  const o = snapshot.value?.topGroup
  return o && typeof o === 'object' ? o : null
})
const topGroupName = computed(() => {
  if (!topGroup.value) return '暂无群聊'
  return String(topGroup.value?.displayName || '').trim() || '--'
})
const topGroupMessages = computed(() => Number(topGroup.value?.messages || 0))
const topGroupAvatarUrl = computed(() => resolveMediaUrl(topGroup.value?.avatarUrl, { backend: true }))
const topGroupSharePct = computed(() => {
  const total = totalMessages.value
  if (!(total > 0)) return 0
  const pct = Math.round((topGroupMessages.value / total) * 100)
  return Math.max(0, Math.min(100, pct))
})
const topGroupDailyLabel = computed(() => {
  const msg = topGroupMessages.value
  if (!(msg > 0)) return '--'
  return formatInt(Math.round(msg / Math.max(1, daysInYear(year.value))))
})

const replyStats = computed(() => {
  const o = snapshot.value?.replyStats
  return o && typeof o === 'object' ? o : null
})
const replyP50Label = computed(() => formatDurationZh(replyStats.value?.p50Seconds))

const fastest = computed(() => {
  const o = snapshot.value?.fastest
  return o && typeof o === 'object' ? o : null
})
const slowest = computed(() => {
  const o = snapshot.value?.slowest
  return o && typeof o === 'object' ? o : null
})
const fastestContactName = computed(() => String(fastest.value?.displayName || '').trim() || '暂无')
const slowestContactName = computed(() => String(slowest.value?.displayName || '').trim() || '暂无')
const fastestAvatarUrl = computed(() => resolveMediaUrl(fastest.value?.avatarUrl, { backend: true }))
const slowestAvatarUrl = computed(() => resolveMediaUrl(slowest.value?.avatarUrl, { backend: true }))
const fastestReplyLabel = computed(() => formatDurationZh(fastest.value?.seconds))
const slowestReplyLabel = computed(() => formatDurationZh(slowest.value?.seconds))

const topPhrase = computed(() => {
  const o = snapshot.value?.topPhrase
  if (!o || typeof o !== 'object') return null
  const phrase = String(o.phrase || o.word || '').trim()
  const count = Number(o.count || 0)
  return phrase ? { phrase, count: Number.isFinite(count) && count > 0 ? count : 0 } : null
})
const topPhraseWord = computed(() => topPhrase.value?.phrase || '--')
const topPhraseCount = computed(() => Number(topPhrase.value?.count || 0))

const sentStickerCount = computed(() => Number(snapshot.value?.sentStickerCount || 0))
// NOTE: topSticker.imageUrl may be either "/api/..." (backend) or "/wxemoji/..." (Nuxt public).
// resolveMediaUrl keeps them as same-origin paths (Nuxt devProxy / backend-mounted UI will handle `/api`).
const topStickerUrl = computed(() => resolveMediaUrl(snapshot.value?.topSticker?.imageUrl))
const stickerShareText = computed(() => {
  const total = Number(totalMessages.value || 0)
  const stickers = Number(sentStickerCount.value || 0)
  if (!(total > 0) || stickers <= 0) return '0%'
  const ratio = Math.max(0, Math.min(1, stickers / total))
  const pct = ratio * 100
  return pct >= 10 ? `${Math.round(pct)}%` : `${pct.toFixed(1)}%`
})

const topStickerMode = ref('img') // 'img' | 'video'
const onTopStickerImgError = () => {
  // Some WeChat stickers are returned as video/mp4; fall back to <video> first.
  if (topStickerMode.value !== 'video') {
    topStickerMode.value = 'video'
    return
  }
  markBroken('topSticker')
}
const onTopStickerVideoError = () => {
  markBroken('topSticker')
}
watch(
  topStickerUrl,
  () => {
    topStickerMode.value = 'img'
    broken.topSticker = false
  },
  { immediate: true }
)

const topUnicodeEmoji = computed(() => String(snapshot.value?.topUnicodeEmoji || '😀'))
const topUnicodeEmojiCount = computed(() => Number(snapshot.value?.topUnicodeEmojiCount || 0))

const topEmoji = computed(() => {
  const o = snapshot.value?.topEmoji
  return o && typeof o === 'object' ? o : null
})
const topEmojiKind = computed(() => String(topEmoji.value?.kind || '').trim())
const topEmojiLabel = computed(() => {
  if (topEmoji.value) {
    if (topEmojiKind.value === 'wechat') {
      const key = String(topEmoji.value?.key || '').trim()
      if (key) return key
    } else if (topEmojiKind.value === 'unicode') {
      const emo = String(topEmoji.value?.emoji || '').trim()
      if (emo) return emo
    }
  }
  return topUnicodeEmoji.value
})
const topEmojiCount = computed(() => {
  if (topEmoji.value) {
    const n = Number(topEmoji.value?.count || 0)
    return Number.isFinite(n) ? n : 0
  }
  return topUnicodeEmojiCount.value
})
const topEmojiAssetPath = computed(() => {
  if (!topEmoji.value || topEmojiKind.value !== 'wechat') return ''
  return resolveMediaUrl(topEmoji.value?.assetPath || '')
})
watch(
  topEmojiAssetPath,
  () => {
    broken.topEmoji = false
  },
  { immediate: true }
)

const rawMonthly = computed(() => (Array.isArray(snapshot.value?.monthlyBestBuddies) ? snapshot.value.monthlyBestBuddies : []))
const monthlyNormalized = computed(() => {
  const byMonth = new Map()
  for (const it of rawMonthly.value) {
    if (!it || typeof it !== 'object') continue
    const m = Number(it.month)
    if (!Number.isFinite(m) || m < 1 || m > 12) continue
    if (!byMonth.has(m)) byMonth.set(m, it)
  }
  return Array.from({ length: 12 }, (_, i) => {
    const m = i + 1
    return byMonth.get(m) || { month: m, displayName: '--', maskedName: '--', avatarUrl: '', messages: 0, metrics: null }
  })
})

const monthlyKey = (item) => {
  const name = String(item?.displayName || '').trim()
  return name && name !== '--' ? name : '--'
}

const monthlyCounts = computed(() => {
  const counts = new Map()
  for (const it of monthlyNormalized.value) {
    const k = monthlyKey(it)
    if (!k || k === '--') continue
    counts.set(k, (counts.get(k) || 0) + 1)
  }
  return counts
})

const monthlyMvpName = computed(() => {
  let bestName = '--'
  let bestCnt = 0
  for (const [k, v] of monthlyCounts.value.entries()) {
    if (v > bestCnt) {
      bestName = k
      bestCnt = v
    }
  }
  return bestName
})
const monthlyMvpMonths = computed(() => Number(monthlyCounts.value.get(monthlyMvpName.value) || 0))
const showMonthlyHero = computed(() => monthlyMvpMonths.value >= 3)

const monthlyMvpAvatarUrl = computed(() => {
  if (monthlyMvpName.value === '--') return ''
  const hit = monthlyNormalized.value.find((it) => monthlyKey(it) === monthlyMvpName.value && String(it?.avatarUrl || '').trim())
  return resolveMediaUrl(hit?.avatarUrl, { backend: true })
})

const monthlyMvpMetrics = computed(() => {
  if (!showMonthlyHero.value) return []
  const key = monthlyMvpName.value
  if (!key || key === '--') return []
  const items = monthlyNormalized.value.filter(
    (it) => monthlyKey(it) === key && it && typeof it.metrics === 'object' && it.metrics
  )
  if (items.length <= 0) return []

  const keys = [
    { key: 'interactionScore', label: '互动' },
    { key: 'speedScore', label: '速度' },
    { key: 'continuityScore', label: '连续' },
    { key: 'coverageScore', label: '覆盖' }
  ]
  return keys.map(({ key: k, label }) => {
    const avg = items.reduce((s, it) => s + Number(it.metrics?.[k] || 0), 0) / items.length
    const pct = Math.max(0, Math.min(100, Math.round(avg * 100)))
    return { key: k, label, pct }
  })
})

const buddyColors = [
  'hsl(174, 72%, 42%)',
  'hsl(25, 92%, 52%)',
  'hsl(262, 62%, 55%)',
  'hsl(340, 70%, 52%)',
  'hsl(210, 72%, 50%)',
  'hsl(45, 88%, 48%)'
]

const monthlyColorMap = computed(() => {
  const m = new Map()
  let idx = 0
  for (const it of monthlyNormalized.value) {
    const k = monthlyKey(it)
    if (!k || k === '--') continue
    if (!m.has(k)) {
      m.set(k, buddyColors[idx % buddyColors.length])
      idx += 1
    }
  }
  return m
})

const hsla = (hsl, a) => String(hsl || '').replace('hsl(', 'hsla(').replace(')', `, ${a})`)

const monthlyCells = computed(() => {
  const mvp = monthlyMvpName.value
  return monthlyNormalized.value.map((raw) => {
    const month = Number(raw.month || 0)
    const name = monthlyKey(raw)
    const color = monthlyColorMap.value.get(name)
    const bg = color ? hsla(color, 0.08) : 'rgba(0,0,0,0.03)'
    const avatarBg = color || 'linear-gradient(135deg, #2dd4bf, #34d399)'
    const avatarUrl = resolveMediaUrl(raw.avatarUrl, { backend: true })
    return {
      month,
      messages: Number(raw.messages || 0),
      _nameLabel: name,
      _isMvp: name !== '--' && name === mvp,
      _cellStyle: { background: bg, border: '1px solid rgba(255,255,255,0.55)' },
      _avatarFallbackBg: avatarBg,
      _avatarUrl: avatarUrl
    }
  })
})

const weekdayLabels = computed(() => {
  const xs = snapshot.value?.weekdayLabels
  return Array.isArray(xs) && xs.length === 7 ? xs.map((x) => String(x)) : ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
})

const heatmapMatrix = computed(() => {
  const m = snapshot.value?.weekdayHourMatrix
  if (!Array.isArray(m) || m.length !== 7) return Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0))
  return m.map((row) => {
    if (!Array.isArray(row) || row.length !== 24) return Array.from({ length: 24 }, () => 0)
    return row.map((v) => Number(v || 0))
  })
})

const heatmapMax = computed(() => {
  let max = 0
  for (const row of heatmapMatrix.value) {
    for (const v of row) max = Math.max(max, Number(v || 0))
  }
  return max
})

const heatColor = (value, max) => {
  const v = Number(value) || 0
  const m = Number(max) || 0
  if (!(v > 0) || !(m > 0)) return 'rgba(0,0,0,0.05)'
  const t = Math.max(0, Math.min(1, Math.sqrt(v / m)))
  const hue = 145 - 50 * t
  const sat = 70
  const light = 92 - 42 * t
  return `hsl(${hue.toFixed(1)} ${sat}% ${light.toFixed(1)}%)`
}

const heatmapCells = computed(() => {
  const max = Math.max(1, heatmapMax.value)
  const out = []
  for (let w = 0; w < 7; w += 1) {
    for (let h = 0; h < 24; h += 1) {
      const count = Number(heatmapMatrix.value[w]?.[h] || 0)
      const hourEnd = (h + 1) % 24
      const slot = `${weekdayLabels.value[w]} ${pad2(h)}:00-${pad2(hourEnd)}:00`
      const title = count > 0 ? `${slot}，发送 ${formatInt(count)} 条消息` : `${slot}，该时段几乎没有消息`
      out.push({
        key: `${w}-${h}`,
        title,
        bg: count > 0 ? heatColor(count, max) : 'rgba(7, 193, 96, 0.1)',
        opacity: count > 0 ? 0.95 : 0.72
      })
    }
  }
  return out
})

const hourLabelRow = computed(() => Array.from({ length: 24 }, (_, h) => ({ key: h, label: h % 3 === 0 ? pad2(h) : '' })))

const heatmapLegendColors = computed(() => {
  const max = Math.max(1, heatmapMax.value)
  const dots = 5
  return Array.from({ length: dots }, (_, i) => {
    const step = (i + 1) / dots
    const val = Math.max(1, step * max)
    return heatColor(val, max)
  })
})

const heatmapYearLabel = computed(() => `${year.value}年聚合`)
const heatmapMaxLabel = computed(() => (heatmapMax.value > 0 ? `最大 ${formatInt(heatmapMax.value)} 条` : '暂无数据'))
</script>

<style scoped>
.bento-stage {
  width: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: #1d1d1f;
  isolation: isolate;
}

.bento-stage.is-loading {
  justify-content: center;
  padding: 0 1.25rem 2rem;
  gap: 0.55rem;
  text-align: center;
}

/* Packing Memory Bento Loader Styles (ported from bento-summary.html) */
.packing-scene {
  position: relative;
  width: 300px;
  height: 300px;
  perspective: 800px;
  margin-bottom: 2.5rem;
  display: flex;
  justify-content: center;
  align-items: center;
}

.bento-loader-box {
  position: relative;
  width: 320px;
  height: 320px;
  background: #ffffff;
  border-radius: 32px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08);
  padding: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;
  gap: 12px;
}

.bento-slot {
  background: #f3f4f6;
  border-radius: 20px;
  position: relative;
  overflow: hidden;
  border: 2px dashed #e5e7eb;
}

.slot-1 {
  grid-column: 1 / span 2;
  grid-row: 1 / span 2;
}

.slot-2 {
  grid-column: 3 / span 1;
  grid-row: 1 / span 1;
}

.slot-3 {
  grid-column: 3 / span 1;
  grid-row: 2 / span 1;
}

.slot-4 {
  grid-column: 1 / span 2;
  grid-row: 3 / span 1;
}

.slot-5 {
  grid-column: 3 / span 1;
  grid-row: 3 / span 1;
}

.memory-piece {
  position: absolute;
  inset: 0;
  border-radius: 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  opacity: 0;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
  text-align: center;
  animation: smoothLoop 3.2s infinite;
}

@keyframes smoothLoop {
  0% {
    transform: scale(0.6) translateY(20px);
    opacity: 0;
    animation-timing-function: cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  15% {
    transform: scale(1.05) translateY(-5px);
    opacity: 1;
    animation-timing-function: ease-out;
  }

  20% {
    transform: scale(1) translateY(0);
    opacity: 1;
    animation-timing-function: linear;
  }

  65% {
    transform: scale(1) translateY(0);
    opacity: 1;
    animation-timing-function: ease-in;
  }

  80% {
    transform: scale(0.8) translateY(15px);
    opacity: 0;
    animation-timing-function: linear;
  }

  100% {
    transform: scale(0.6) translateY(20px);
    opacity: 0;
  }
}

.piece-1 {
  background: #3b82f6;
  color: #ffffff;
  padding: 1.5rem;
  align-items: flex-start;
  animation-delay: 0s;
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
}

.piece-2 {
  background: #ec4899;
  color: #ffffff;
  animation-delay: 0.2s;
  box-shadow: 0 4px 15px rgba(236, 72, 153, 0.4);
}

.piece-3 {
  background: #10b981;
  color: #ffffff;
  animation-delay: 0.4s;
  box-shadow: 0 4px 15px rgba(16, 185, 129, 0.4);
}

.piece-4 {
  background: #8b5cf6;
  color: #ffffff;
  flex-direction: row;
  gap: 1rem;
  animation-delay: 0.6s;
  box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
}

.piece-5 {
  background: #f97316;
  color: #ffffff;
  animation-delay: 0.8s;
  box-shadow: 0 4px 15px rgba(249, 115, 22, 0.4);
}

.piece-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.piece-bar {
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.4);
}

.piece-bar.short {
  width: 40%;
}

.piece-bar.long {
  width: 70%;
}

/* Ensure texts/buttons render above the loader box */
.bento-loading-title,
.loader-text,
.bento-loading-desc,
.bento-loading-error,
.bento-loading-actions {
  position: relative;
  z-index: 2;
}

@media (max-width: 420px) {
  .packing-scene {
    transform: scale(0.9);
    margin-bottom: 1.25rem;
  }
}

.bento-stage.is-slide {
  height: 100dvh;
  overflow: hidden;
}

.bento-stage.is-panel {
  height: auto;
  min-height: 0;
}

.bento-container {
  width: 100%;
  height: 100%;
  max-width: 1040px;
  max-height: 900px;
  padding: 1.25rem;
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  grid-template-rows: 0.8fr 0.8fr 1.1fr 0.6fr 1fr;
  gap: 0.9rem;
  box-sizing: border-box;
  grid-auto-flow: row dense;
}

.bento-loading-title {
  font-weight: 900;
  letter-spacing: -0.02em;
  font-size: 1.2rem;
  color: rgba(6, 95, 70, 0.92);
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.bento-loading-emoji {
  font-size: 1.25rem;
}

.bento-loading-desc {
  margin-top: 0.45rem;
  font-size: 0.9rem;
  color: rgba(15, 23, 42, 0.62);
  line-height: 1.5;
  max-width: min(560px, 100%);
}

.loader-text {
  margin-top: 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: rgba(15, 23, 42, 0.55);
  transition: opacity 0.35s ease, transform 0.35s ease;
}

.loader-text.fade {
  opacity: 0;
  transform: translateY(8px);
}

.bento-loading-error {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: rgba(220, 38, 38, 0.92);
  background: rgba(254, 226, 226, 0.65);
  border: 1px solid rgba(248, 113, 113, 0.22);
  padding: 0.65rem 0.85rem;
  border-radius: 1rem;
  text-align: left;
  white-space: pre-wrap;
}

.bento-loading-actions {
  margin-top: 0.85rem;
  display: flex;
  justify-content: center;
}

.bento-loading-btn {
  appearance: none;
  border: 0;
  cursor: pointer;
  padding: 0.6rem 1rem;
  border-radius: 999px;
  background: #07c160;
  color: white;
  font-weight: 800;
  font-size: 0.92rem;
  box-shadow: 0 10px 26px rgba(7, 193, 96, 0.25);
  transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.bento-loading-btn:hover {
  transform: translateY(-1px);
  background: #06ad56;
  box-shadow: 0 16px 34px rgba(7, 193, 96, 0.28);
}

.bento-card {
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: saturate(180%) blur(28px);
  -webkit-backdrop-filter: saturate(180%) blur(28px);
  border: 1px solid rgba(255, 255, 255, 0.55);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.75);
  border-radius: 2rem;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  opacity: 1;
  transition:
    transform 0.4s cubic-bezier(0.25, 1, 0.25, 1),
    background 0.4s ease,
    border-color 0.4s ease,
    box-shadow 0.4s ease,
    opacity 0.4s ease;
}

.bento-card:hover {
  transform: translate3d(0, -2px, 0) scale(1.015);
  background: rgba(255, 255, 255, 0.82);
  border-color: rgba(255, 255, 255, 1);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.09), inset 0 1px 0 rgba(255, 255, 255, 1);
  z-index: 10;
}

.aura {
  position: absolute;
  border-radius: 50%;
  filter: blur(50px);
  z-index: 0;
  pointer-events: none;
  opacity: 0.85;
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.bento-card:hover .aura {
  opacity: 1;
  transform: scale(1.05);
}

.bento-watermark {
  position: absolute;
  right: -0.75rem;
  bottom: -1rem;
  font-size: 6rem;
  opacity: 0.05;
  transform: rotate(-15deg);
  z-index: 0;
  pointer-events: none;
  transition: all 0.5s cubic-bezier(0.25, 1, 0.25, 1);
}

.bento-card:hover .bento-watermark {
  transform: rotate(-5deg) scale(1.15);
  opacity: 0.08;
}

.content {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.card-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #86868b;
  margin-bottom: 0.4rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  letter-spacing: -0.01em;
  flex-shrink: 0;
}

.card-messages {
  grid-column: 1 / span 2;
  grid-row: 1 / span 1;
  padding: 1.25rem;
}

.card-words {
  grid-column: 1 / span 2;
  grid-row: 2 / span 1;
  padding: 1.25rem;
}

.card-friends {
  grid-column: 8 / span 1;
  grid-row: 2 / span 1;
  padding: 1.05rem;
}

.card-time {
  grid-column: 6 / span 3;
  grid-row: 1 / span 1;
  padding: 1.05rem;
}

.card-partner {
  grid-column: 3 / span 3;
  grid-row: 1 / span 2;
  padding: 1.35rem;
}

.card-group {
  grid-column: 3 / span 3;
  grid-row: 5 / span 1;
  padding: 1.05rem;
}

.card-sticker {
  grid-column: 1 / span 2;
  grid-row: 3 / span 2;
  padding: 1.05rem;
}

.card-emoji {
  grid-column: 1 / span 2;
  grid-row: 5 / span 1;
  padding: 1.05rem;
  justify-content: center;
  align-items: center;
}

@keyframes stickerFlyOut {
  0% {
    transform: translate(-50%, -50%) scale(0) rotate(0deg);
    opacity: 0;
  }

  15% {
    opacity: 1;
  }

  100% {
    transform: translate(calc(-50% + var(--tx)), calc(-50% + var(--ty))) scale(var(--s)) rotate(var(--r));
    opacity: var(--o, 0.5);
  }
}

.scattered-emoji {
  position: absolute;
  top: 50%;
  left: 50%;
  font-size: 2.2rem;
  opacity: 0;
  pointer-events: none;
  z-index: 5;
  filter: drop-shadow(0 4px 12px rgba(250, 204, 21, 0.4));
  animation: stickerFlyOut 1.2s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
}

.group-share-ring {
  --p: 0;
  background: conic-gradient(rgba(14, 165, 233, 0.92) calc(var(--p) * 1%), rgba(14, 165, 233, 0.16) 0);
}

/* Floating Hearts Animation (Partner card) */
@keyframes floatUp {
  0% {
    transform: translateY(0) scale(0.8);
    opacity: 0;
  }

  10% {
    opacity: 0.4;
  }

  100% {
    transform: translateY(-120px) scale(1.1);
    opacity: 0;
  }
}

.floating-heart {
  display: inline-block;
  line-height: 1;
  position: absolute;
  animation: floatUp 5s infinite ease-in;
  opacity: 0;
  pointer-events: none;
}

.card-partner .content {
  z-index: 10;
}

.partner-split-layout {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  height: 100%;
  width: 100%;
  position: relative;
  z-index: 10;
}

@media (min-width: 640px) {
  .partner-split-layout {
    flex-direction: row;
    align-items: stretch;
  }
}

.partner-profile-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.5rem;
  flex: 1;
  min-width: 40%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0.1));
  border-radius: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.partner-metrics-zone {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  flex: 1.5;
  justify-content: center;
}

.partner-metric-strip {
  display: flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 0.85rem;
  padding: 0.45rem 0.6rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03), inset 0 1px 0 rgba(255, 255, 255, 1);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  width: 100%;
}

.partner-metric-strip:hover {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 1);
  background: rgba(255, 255, 255, 0.9);
}

.partner-metric-icon {
  width: 2rem;
  height: 2rem;
  border-radius: 0.6rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  margin-right: 0.6rem;
  font-size: 0.9rem;
}

.card-speed {
  grid-column: 6 / span 3;
  grid-row: 3 / span 1;
  padding: 0.75rem 0.95rem;
}

.card-speed .card-title {
  margin-bottom: 0.2rem;
}

.card-catchphrase {
  grid-column: 6 / span 2;
  grid-row: 2 / span 1;
  padding: 1.05rem;
}

.text-gradient {
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.reply-bento {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 0.35rem;
  flex: 1;
  min-height: 0;
  margin-top: 0.2rem;
}

.reply-subcard {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.7), rgba(245, 245, 245, 0.5));
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 0.65rem;
  padding: 0.25rem 0.4rem;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 1), 0 2px 8px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
  overflow: hidden;
  transition: all 0.3s ease;
  min-height: 0;
  min-width: 0;
}

.reply-subcard:hover {
  transform: translateY(-1px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 1), 0 4px 12px rgba(0, 0, 0, 0.05);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(250, 250, 250, 0.8));
}

.reply-subcard.large {
  grid-column: 1 / span 1;
  grid-row: 1 / span 2;
  padding: 0.4rem 0.6rem;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 0.3rem;
}

.reply-subcard .subcard-title {
  font-size: 0.55rem;
  font-weight: 600;
  color: rgba(17, 24, 39, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 0.1rem;
  z-index: 10;
}

.reply-subcard.large .subcard-title {
  font-size: 0.65rem;
  margin-bottom: 0.1rem;
}

.reply-subcard .subcard-value {
  font-size: 1.1rem;
  font-weight: 800;
  color: #1f2937;
  letter-spacing: -0.02em;
  line-height: 1.25;
  z-index: 10;
}

.reply-subcard.large .subcard-value {
  font-size: 1.7rem;
  line-height: 1.25;
  padding-bottom: 2px;
}

.reply-subcard-icon {
  position: absolute;
  right: -0.3rem;
  bottom: -0.3rem;
  font-size: 2.2rem;
  opacity: 0.08;
  transform: rotate(-15deg);
  z-index: 1;
}

.reply-subcard.large .reply-subcard-icon {
  right: -0.8rem;
  bottom: -0.8rem;
  font-size: 4rem;
}

.person-name {
  font-size: 0.7rem;
  font-weight: 600;
  color: #4b5563;
  max-width: 3.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-monthly {
  grid-column: 6 / span 3;
  grid-row: 4 / span 2;
  padding: 1.05rem;
}

.card-heatmap {
  grid-column: 3 / span 3;
  grid-row: 3 / span 2;
  padding: 0.95rem 1.05rem;
}

/* Monthly — Avatar Hero + 6×2 grid */
.monthly-hero {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  min-height: 0;
  flex: 1;
  padding: 0.15rem 0;
}

.monthly-avatar-lg {
  position: relative;
  width: 3.25rem;
  height: 3.25rem;
  flex-shrink: 0;
}

.monthly-avatar-lg img,
.monthly-avatar-lg .monthly-avatar-fallback-lg {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2.5px solid white;
  object-fit: cover;
  position: relative;
  z-index: 1;
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.2);
  background: #f3f4f6;
}

.monthly-avatar-fallback-lg {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.15rem;
  font-weight: 800;
  color: white;
  background: linear-gradient(135deg, #2dd4bf, #34d399) !important;
}

.monthly-hero-info {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
  flex: 1;
}

.monthly-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.2rem 0.45rem;
  margin-left: auto;
  flex: 1;
  max-width: 60%;
  flex-shrink: 0;
  align-self: center;
}

.monthly-metric-item {
  min-width: 0;
}

.monthly-metric-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.55rem;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.4);
  line-height: 1;
}

.monthly-metric-header .metric-val {
  font-weight: 700;
  font-size: 0.5rem;
  color: rgba(13, 148, 136, 0.7);
  font-variant-numeric: tabular-nums;
}

.monthly-metric-bar {
  margin-top: 0.15rem;
  height: 6px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

.monthly-metric-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2dd4bf, #34d399);
  opacity: 0.75;
  transition: width 0.6s cubic-bezier(0.25, 1, 0.25, 1);
}

.monthly-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 0.3rem;
}

.monthly-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.25rem 0.1rem;
  border-radius: 0.65rem;
  min-width: 0;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  cursor: default;
  position: relative;
  gap: 0.15rem;
}

.monthly-cell:hover {
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  z-index: 2;
}

.monthly-avatar-sm {
  width: 1.6rem;
  height: 1.6rem;
  border-radius: 50%;
  object-fit: cover;
  border: 1.5px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
  background: #f3f4f6;
}

.monthly-avatar-fallback-sm {
  width: 1.6rem;
  height: 1.6rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.55rem;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
  border: 1.5px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.monthly-cell-month {
  font-size: 0.55rem;
  font-weight: 600;
  line-height: 1;
  color: rgba(0, 0, 0, 0.38);
}

.monthly-cell.is-mvp .monthly-avatar-sm,
.monthly-cell.is-mvp .monthly-avatar-fallback-sm {
  box-shadow: 0 0 0 2px rgba(45, 212, 191, 0.6), 0 1px 4px rgba(0, 0, 0, 0.08);
}

.monthly-cell.is-mvp .monthly-cell-month {
  color: rgba(13, 148, 136, 0.85);
  font-weight: 700;
}

.monthly-grid.expanded {
  flex: 1;
  gap: 0.35rem;
  align-content: center;
}

.monthly-grid.expanded .monthly-cell {
  padding: 0.3rem 0.15rem;
  gap: 0.12rem;
}

.monthly-grid.expanded .monthly-avatar-sm,
.monthly-grid.expanded .monthly-avatar-fallback-sm {
  width: 1.85rem;
  height: 1.85rem;
  font-size: 0.6rem;
}

.monthly-grid.expanded .monthly-cell-name {
  font-size: 0.5rem;
  font-weight: 600;
  line-height: 1.2;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.6;
}

.monthly-grid.expanded .monthly-cell.is-mvp .monthly-cell-name {
  opacity: 0.85;
}

/* Heatmap — 24×7 */
.heatmap-year-tag {
  font-size: 0.65rem;
  line-height: 1;
  font-weight: 600;
  color: rgba(6, 95, 70, 0.78);
  background: rgba(16, 185, 129, 0.14);
  border: 1px solid rgba(16, 185, 129, 0.22);
  padding: 0.3rem 0.5rem;
  border-radius: 999px;
  letter-spacing: 0.01em;
}

.heatmap-max-label {
  font-size: 0.65rem;
  line-height: 1;
  font-weight: 600;
  color: rgba(6, 95, 70, 0.6);
}

.card-heatmap .heatmap-shell {
  margin-top: 0.42rem;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
}

.card-heatmap .heatmap-hour-row {
  display: grid;
  grid-template-columns: 2.05rem repeat(24, minmax(0, 1fr));
  gap: 1px;
  min-height: 0.9rem;
  align-items: end;
  user-select: none;
}

.card-heatmap .heatmap-hour-spacer {
  display: block;
}

.card-heatmap .heatmap-hour-label {
  font-size: 0.6rem;
  color: rgba(6, 95, 70, 0.58);
  font-weight: 600;
  text-align: center;
  white-space: nowrap;
  min-width: 0;
}

.card-heatmap .heatmap-main {
  display: grid;
  grid-template-columns: 2.05rem minmax(0, 1fr);
  gap: 0.25rem;
  min-height: 0;
  flex: 1;
  align-content: center;
}

.card-heatmap .heatmap-weekday-col {
  display: grid;
  grid-template-rows: repeat(7, auto);
  gap: 4px;
  justify-items: center;
  align-items: center;
  user-select: none;
}

.card-heatmap .heatmap-weekday-col span {
  font-size: 0.5rem;
  color: rgba(17, 24, 39, 0.44);
  font-weight: 500;
  line-height: 1;
}

.card-heatmap .heatmap-grid {
  display: grid;
  grid-template-columns: repeat(24, minmax(0, 1fr));
  grid-template-rows: repeat(7, auto);
  gap: 4px;
  min-height: 0;
}

.card-heatmap .heatmap-cell {
  appearance: none;
  -webkit-appearance: none;
  aspect-ratio: 1;
  border: 1px solid rgba(7, 193, 96, 0.1);
  border-radius: 2px;
  background: rgba(0, 0, 0, 0.05);
  transition: transform 0.16s ease, box-shadow 0.16s ease, opacity 0.16s ease;
  transform-origin: center;
  cursor: pointer;
  min-width: 0;
  min-height: 0;
  padding: 0;
}

.card-heatmap .heatmap-cell:hover {
  transform: scale(1.14);
  box-shadow: 0 6px 14px rgba(7, 193, 96, 0.28);
  z-index: 2;
  opacity: 1;
}

.card-heatmap .heatmap-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  user-select: none;
  color: rgba(17, 24, 39, 0.55);
  font-size: 0.74rem;
  font-weight: 500;
}

.card-heatmap .heatmap-legend-scale {
  display: flex;
  align-items: center;
  gap: 2px;
}

.card-heatmap .heatmap-legend-dot {
  width: 0.9rem;
  height: 0.35rem;
  border-radius: 999px;
  background: rgba(7, 193, 96, 0.18);
  border: 1px solid rgba(7, 193, 96, 0.14);
}

@media (max-width: 980px) {
  .bento-container {
    max-width: 100%;
    padding: 1rem;
    gap: 0.8rem;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-template-rows: none;
    grid-auto-rows: minmax(140px, auto);
  }

  .card-partner,
  .card-messages,
  .card-words,
  .card-time,
  .card-catchphrase,
  .card-group {
    grid-column: auto / span 3;
    grid-row: auto / span 1;
  }

  .card-speed {
    grid-column: auto / span 3;
    grid-row: auto / span 1;
    order: 12;
  }

  .card-heatmap {
    grid-column: auto / span 3;
    grid-row: auto / span 2;
    order: 10;
  }

  .card-monthly {
    grid-column: auto / span 3;
    grid-row: auto / span 2;
  }

  .card-sticker {
    grid-column: auto / span 2;
    grid-row: auto / span 2;
  }

  .card-emoji,
  .card-friends {
    grid-column: auto / span 2;
    grid-row: auto / span 1;
  }
}

@media (max-width: 820px) {
  .bento-stage.is-slide {
    overflow-y: auto;
    align-items: flex-start;
  }

  .bento-container {
    height: auto;
    max-height: none;
    min-height: 100vh;
    padding: 0.85rem;
    gap: 0.65rem;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-rows: none;
    grid-auto-rows: minmax(170px, auto);
  }

  .card-messages,
  .card-words,
  .card-partner,
  .card-group,
  .card-speed,
  .card-monthly,
  .card-heatmap {
    grid-column: auto / span 2;
    grid-row: auto / span 1;
  }

  .card-friends,
  .card-time,
  .card-catchphrase,
  .card-sticker,
  .card-emoji {
    grid-column: auto / span 1;
    grid-row: auto / span 1;
  }

  .card-heatmap .heatmap-shell {
    min-height: 0;
  }

  .partner-split-layout {
    flex-direction: column;
  }

  .partner-metric-strip {
    padding: 0.35rem 0.5rem;
  }

  .partner-metric-icon {
    width: 1.6rem;
    height: 1.6rem;
  }

  .reply-subcard {
    padding: 0.2rem 0.35rem;
    border-radius: 0.5rem;
  }

  .reply-subcard.large {
    padding: 0.2rem 0.45rem;
  }

  .reply-subcard .subcard-value {
    font-size: 0.8rem;
  }

  .reply-subcard.large .subcard-value {
    font-size: 1.25rem;
  }

  .reply-subcard .subcard-title {
    font-size: 0.45rem;
  }

  .reply-bento {
    gap: 0.25rem;
  }

  .monthly-grid {
    gap: 0.2rem;
  }

  .monthly-cell {
    padding: 0.15rem 0.05rem;
    border-radius: 0.5rem;
  }

  .monthly-cell-month {
    font-size: 0.45rem;
  }

  .monthly-avatar-sm,
  .monthly-avatar-fallback-sm {
    width: 1.35rem;
    height: 1.35rem;
    font-size: 0.45rem;
  }

  .monthly-avatar-lg {
    width: 2.5rem;
    height: 2.5rem;
  }

  .monthly-avatar-fallback-lg {
    font-size: 0.9rem;
  }

  .monthly-grid.expanded .monthly-avatar-sm,
  .monthly-grid.expanded .monthly-avatar-fallback-sm {
    width: 1.5rem;
    height: 1.5rem;
    font-size: 0.5rem;
  }

  .monthly-grid.expanded .monthly-cell-name {
    font-size: 0.42rem;
  }
}

@media (max-width: 480px) {
  .bento-container {
    padding: 0.65rem;
    gap: 0.55rem;
    grid-auto-rows: minmax(150px, auto);
  }

  .card-heatmap .heatmap-grid {
    gap: 2px;
  }
}

/* Additional safe-guards for smaller resolutions */
@media (max-height: 950px) {
  .bento-container {
    gap: 0.75rem;
    padding: 1rem;
  }

  .bento-card {
    border-radius: 1.25rem;
  }

  .card-title {
    font-size: 0.8rem;
    margin-bottom: 0.2rem;
  }

  .card-messages,
  .card-words {
    padding: 0.75rem 1rem;
  }

  .card-friends,
  .card-time,
  .card-catchphrase,
  .card-sticker,
  .card-emoji,
  .card-monthly,
  .card-heatmap {
    padding: 0.75rem;
  }

  .card-heatmap {
    padding: 0.88rem;
  }

  .card-partner {
    padding: 1rem;
  }

  .card-group,
  .card-speed {
    padding: 0.85rem;
  }

  .text-6xl {
    font-size: 2.5rem !important;
    line-height: 1;
  }

  .text-5xl {
    font-size: 2rem !important;
    line-height: 1;
  }

  .text-4xl {
    font-size: 1.75rem !important;
    line-height: 1;
  }

  .text-3xl {
    font-size: 1.5rem !important;
    line-height: 1;
  }

  .text-2xl {
    font-size: 1.25rem !important;
    line-height: 1;
  }

  .text-lg {
    font-size: 0.875rem !important;
  }

  .text-base {
    font-size: 0.8rem !important;
  }

  .text-sm {
    font-size: 0.75rem !important;
  }

  .text-xs {
    font-size: 0.65rem !important;
  }

  .w-32,
  .lg\:w-32,
  .w-28,
  .sm\:w-28,
  .w-24 {
    width: 4.5rem !important;
  }

  .h-32,
  .lg\:h-32,
  .h-28,
  .sm\:h-28,
  .h-24 {
    height: 4.5rem !important;
  }

  .w-10,
  .sm\:w-10,
  .w-8 {
    width: 1.75rem !important;
  }

  .h-10,
  .sm\:h-10,
  .h-8 {
    height: 1.75rem !important;
  }

  .card-heatmap .text-\[8px\],
  .card-heatmap .sm\:text-\[9px\] {
    font-size: 7px !important;
  }

  .heatmap-year-tag {
    font-size: 0.58rem;
    padding: 0.22rem 0.4rem;
  }

  .card-heatmap .heatmap-shell {
    border-radius: 0.95rem;
    padding: 0.45rem 0.5rem;
    gap: 0.3rem;
  }

  .card-heatmap .heatmap-hour-row {
    grid-template-columns: 1.45rem repeat(24, minmax(0, 1fr));
    gap: 1.5px;
  }

  .card-heatmap .heatmap-main {
    grid-template-columns: 1.45rem minmax(0, 1fr);
    gap: 0.25rem;
  }

  .card-heatmap .heatmap-hour-label,
  .card-heatmap .heatmap-weekday-col span {
    font-size: 0.5rem;
  }

  .card-heatmap .heatmap-legend {
    font-size: 0.56rem;
  }

  .card-heatmap .heatmap-legend-dot {
    width: 0.7rem;
    height: 0.34rem;
  }
}

@media (max-height: 750px) {
  .bento-container {
    gap: 0.5rem;
    padding: 0.5rem;
  }

  .bento-card {
    border-radius: 1rem;
  }

  .card-title {
    font-size: 0.7rem;
  }

  .card-messages,
  .card-words {
    padding: 0.5rem 0.75rem;
  }

  .card-friends,
  .card-time,
  .card-catchphrase,
  .card-sticker,
  .card-emoji,
  .card-monthly,
  .card-heatmap {
    padding: 0.5rem;
  }

  .card-heatmap {
    padding: 0.65rem;
  }

  .card-partner,
  .card-group,
  .card-speed {
    padding: 0.65rem;
  }

  .text-6xl {
    font-size: 2rem !important;
  }

  .text-5xl {
    font-size: 1.75rem !important;
  }

  .text-4xl {
    font-size: 1.5rem !important;
  }

  .text-3xl {
    font-size: 1.25rem !important;
  }

  .text-lg {
    font-size: 0.75rem !important;
  }

  .text-sm {
    font-size: 0.65rem !important;
  }

  .text-xs {
    font-size: 0.55rem !important;
  }

  .w-32,
  .lg\:w-32,
  .w-28,
  .sm\:w-28,
  .w-24 {
    width: 3.5rem !important;
  }

  .h-32,
  .lg\:h-32,
  .h-28,
  .sm\:h-28,
  .h-24 {
    height: 3.5rem !important;
  }

  .w-10,
  .sm\:w-10,
  .w-8 {
    width: 1.25rem !important;
  }

  .h-10,
  .sm\:h-10,
  .h-8 {
    height: 1.25rem !important;
  }

  .card-heatmap .heatmap-shell {
    border-radius: 0.8rem;
    padding: 0.3rem 0.36rem;
  }

  .card-heatmap .heatmap-hour-row {
    grid-template-columns: 1.2rem repeat(24, minmax(0, 1fr));
    gap: 1px;
  }

  .card-heatmap .heatmap-main {
    grid-template-columns: 1.2rem minmax(0, 1fr);
    gap: 0.2rem;
  }

  .card-heatmap .heatmap-hour-label,
  .card-heatmap .heatmap-weekday-col span,
  .card-heatmap .heatmap-legend {
    font-size: 0.45rem;
  }

  .card-heatmap .heatmap-legend-dot {
    width: 0.52rem;
    height: 0.24rem;
  }
}
</style>
