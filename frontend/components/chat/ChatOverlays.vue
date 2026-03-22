<template>
    <transition name="sidebar-slide">
      <div v-if="timeSidebarOpen" class="time-sidebar">
        <div class="time-sidebar-header">
          <div class="time-sidebar-title">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3M3 11h18" />
              <rect x="4" y="5" width="16" height="16" rx="2" ry="2" stroke-width="2" />
            </svg>
            <span>按日期定位</span>
          </div>
          <button
            type="button"
            class="time-sidebar-close"
            @click="closeTimeSidebar"
            title="关闭 (Esc)"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="time-sidebar-body">
          <div class="calendar-header">
            <button
              type="button"
              class="calendar-nav-btn"
              :disabled="timeSidebarLoading"
              title="上个月"
              @click="prevTimeSidebarMonth"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div class="calendar-month-label calendar-month-label-selects">
              <select
                v-model.number="timeSidebarYear"
                class="calendar-ym-select"
                :disabled="timeSidebarLoading"
                title="选择年份"
                @change="onTimeSidebarYearMonthChange"
              >
                <option v-for="y in timeSidebarYearOptions" :key="y" :value="y">
                  {{ y }}年
                </option>
              </select>
              <select
                v-model.number="timeSidebarMonth"
                class="calendar-ym-select"
                :disabled="timeSidebarLoading"
                title="选择月份"
                @change="onTimeSidebarYearMonthChange"
              >
                <option v-for="mm in 12" :key="mm" :value="mm">
                  {{ mm }}月
                </option>
              </select>
            </div>
            <button
              type="button"
              class="calendar-nav-btn"
              :disabled="timeSidebarLoading"
              title="下个月"
              @click="nextTimeSidebarMonth"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          <div v-if="timeSidebarError" class="time-sidebar-status time-sidebar-status-error">
            {{ timeSidebarError }}
          </div>
          <div v-else class="time-sidebar-status">
            <span v-if="timeSidebarLoading">加载中...</span>
            <span v-else>本月 {{ timeSidebarTotal }} 条消息，{{ timeSidebarActiveDays }} 天有聊天</span>
          </div>

          <div class="calendar-weekdays">
            <div v-for="w in timeSidebarWeekdays" :key="w" class="calendar-weekday">{{ w }}</div>
          </div>

          <div class="calendar-grid">
            <button
              v-for="cell in timeSidebarCalendarCells"
              :key="cell.key"
              type="button"
              class="calendar-day"
              :class="cell.className"
              :style="cell.style"
              :disabled="cell.disabled"
              :title="cell.title"
              @click="onTimeSidebarDayClick(cell)"
            >
              <span v-if="cell.day" class="calendar-day-number">{{ cell.day }}</span>
            </button>
          </div>

          <div class="time-sidebar-actions">
            <button
              type="button"
              class="time-sidebar-action-btn"
              :disabled="timeSidebarLoading || !selectedContact || isLoadingMessages"
              @click="jumpToConversationFirst"
              title="定位到会话最早消息附近"
            >
              跳转到顶部
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 右侧搜索侧边栏 -->
    <transition name="sidebar-slide">
      <div v-if="messageSearchOpen" class="search-sidebar">
          <!-- 侧边栏头部 -->
          <div class="search-sidebar-header">
            <div class="search-sidebar-title">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
              </svg>
              <span>搜索聊天记录</span>
            </div>
            <button
              type="button"
              class="search-sidebar-close"
              @click="closeMessageSearch"
              title="关闭搜索 (Esc)"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <!-- 搜索输入区域（整合所有筛选条件） -->
          <div class="search-sidebar-input-section">
            <!-- 第一行：范围 + 输入框 + 搜索按钮 -->
            <div class="search-input-combined" :class="{ 'search-input-combined-focused': searchInputFocused }">
              <!-- 左侧：范围切换 -->
              <div class="search-scope-inline">
                <button
                  type="button"
                  class="scope-inline-btn"
                  :class="{ 'scope-inline-btn-active': messageSearchScope === 'conversation' }"
                  :disabled="!selectedContact"
                  @click="messageSearchScope = 'conversation'"
                  title="当前会话"
                >
                  当前
                </button>
                <span class="scope-inline-divider">/</span>
                <button
                  type="button"
                  class="scope-inline-btn"
                  :class="{ 'scope-inline-btn-active': messageSearchScope === 'global' }"
                  @click="messageSearchScope = 'global'"
                  title="全部会话"
                >
                  全部
                </button>
              </div>

              <!-- 中间：搜索输入框 -->
              <input
                ref="messageSearchInputRef"
                v-model="messageSearchQuery"
                type="text"
                placeholder="输入关键词..."
                class="search-input-inline"
                :class="{ 'privacy-blur': privacyMode }"
                @focus="searchInputFocused = true"
                @blur="searchInputFocused = false"
                @keydown.enter.exact.prevent="runMessageSearch({ reset: true })"
                @keydown.enter.shift.prevent="onSearchPrev"
                @keydown.escape="closeMessageSearch"
              />

              <!-- 清除按钮 -->
                <button
                  v-if="messageSearchQuery"
                  type="button"
                  class="search-clear-inline"
                  @click="messageSearchQuery = ''; runMessageSearch({ reset: true })"
                >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>

              <!-- 搜索按钮 -->
              <button
                type="button"
                class="search-btn-inline"
                :disabled="messageSearchLoading"
                @click="runMessageSearch({ reset: true })"
              >
                <svg v-if="messageSearchLoading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                </svg>
              </button>
            </div>

            <!-- 第二行：筛选条件 -->
            <div class="search-filters-row">
              <!-- 时间范围 -->
              <select
                v-model="messageSearchRangeDays"
                class="search-filter-select search-filter-select-time"
                title="时间范围"
              >
                <option value="">不限时间</option>
                <option value="1">今天</option>
                <option value="3">最近3天</option>
                <option value="7">最近7天</option>
                <option value="30">最近30天</option>
                <option value="90">最近3个月</option>
                <option value="180">最近半年</option>
                <option value="365">最近1年</option>
                <option value="custom">自定义...</option>
              </select>

              <!-- 发送者筛选 -->
              <div ref="messageSearchSenderDropdownRef" class="relative flex-1">
                <button
                  type="button"
                  class="search-filter-select w-full flex items-center justify-between gap-1 disabled:opacity-60 disabled:cursor-not-allowed"
                  title="按发送者筛选"
                  :disabled="messageSearchSenderDisabled"
                  @click="toggleMessageSearchSenderDropdown"
                >
                    <span class="flex items-center gap-1 min-w-0">
                      <span class="w-4 h-4 rounded overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                        <img
                          v-if="messageSearchSelectedSenderInfo?.avatar"
                          :src="messageSearchSelectedSenderInfo.avatar"
                          alt=""
                          class="w-full h-full object-cover"
                        />
                        <span v-else class="w-full h-full flex items-center justify-center text-[9px] text-gray-500">
                          {{ messageSearchSelectedSenderInitial }}
                        </span>
                      </span>
                      <span class="truncate" :class="{ 'privacy-blur': privacyMode }">{{ messageSearchSenderLabel }}</span>
                    </span>
                    <svg class="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                    </svg>
                  </button>

                <div
                  v-if="messageSearchSenderDropdownOpen"
                  class="chat-overlay-dropdown absolute left-0 right-0 mt-1 rounded-md z-50 overflow-hidden"
                >
                  <div class="p-2 border-b border-gray-100">
                    <input
                      ref="messageSearchSenderDropdownInputRef"
                      v-model="messageSearchSenderDropdownQuery"
                      type="text"
                      placeholder="搜索发送者"
                      class="w-full text-xs px-2 py-1.5 bg-gray-50 border border-gray-200 rounded-md outline-none focus:border-[#03C160] focus:ring-1 focus:ring-[#03C160]/20"
                      :class="{ 'privacy-blur': privacyMode }"
                    />
                  </div>

                  <div class="max-h-64 overflow-y-auto">
                    <button
                      type="button"
                      class="chat-overlay-option w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs"
                      :class="!messageSearchSender ? 'chat-overlay-option--active' : ''"
                      @click="selectMessageSearchSender('')"
                    >
                      <span class="w-6 h-6 rounded-md overflow-hidden bg-gray-200 flex-shrink-0 flex items-center justify-center text-[10px] text-gray-500">
                        全
                      </span>
                      <span class="truncate">不限发送者</span>
                    </button>

                    <div v-if="messageSearchSenderLoading" class="px-2 py-3 text-xs text-gray-500">
                      加载中...
                    </div>
                    <div v-else-if="messageSearchSenderError" class="px-2 py-3 text-xs text-red-500 whitespace-pre-wrap">
                      {{ messageSearchSenderError }}
                    </div>
                    <div v-else-if="filteredMessageSearchSenderOptions.length === 0" class="px-2 py-3 text-xs text-gray-500">
                      {{ messageSearchScope === 'global' && String(messageSearchQuery || '').trim().length < 2 ? '请输入关键词后再筛选发送者' : '暂无发送者' }}
                    </div>
                    <template v-else>
                      <button
                        v-for="s in filteredMessageSearchSenderOptions"
                        :key="s.username"
                        type="button"
                        class="chat-overlay-option w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs"
                        :class="messageSearchSender === s.username ? 'chat-overlay-option--active' : ''"
                        @click="selectMessageSearchSender(s.username)"
                      >
                        <div class="w-6 h-6 rounded-md overflow-hidden bg-gray-300 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                          <img v-if="s.avatar" :src="s.avatar" :alt="(s.displayName || s.username) + '头像'" class="w-full h-full object-cover" />
                          <div v-else class="w-full h-full flex items-center justify-center text-white text-[10px] font-bold" style="background-color: #6B7280">
                            {{ String(s.displayName || s.username || '').charAt(0) }}
                          </div>
                        </div>
                        <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                          <div class="truncate text-gray-800">{{ s.displayName || s.username }}</div>
                          <div class="truncate text-[10px] text-gray-400">{{ s.username }}</div>
                        </div>
                        <div class="text-[10px] text-gray-400 flex-shrink-0">{{ formatCount(s.count) }}</div>
                      </button>
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <!-- 会话类型（仅全局搜索） -->
            <div v-if="messageSearchScope === 'global'" class="search-session-type-row">
              <button
                type="button"
                class="search-session-type-btn"
                :class="{ 'search-session-type-btn-active': !String(messageSearchSessionType || '').trim() }"
                @click="messageSearchSessionType = ''"
              >
                全部
              </button>
              <button
                type="button"
                class="search-session-type-btn"
                :class="{ 'search-session-type-btn-active': String(messageSearchSessionType || '') === 'group' }"
                @click="messageSearchSessionType = 'group'"
              >
                群聊
              </button>
              <button
                type="button"
                class="search-session-type-btn"
                :class="{ 'search-session-type-btn-active': String(messageSearchSessionType || '') === 'single' }"
                @click="messageSearchSessionType = 'single'"
              >
                单聊
              </button>
            </div>

            <!-- 自定义时间范围（当选择自定义时显示） -->
            <div v-if="messageSearchRangeDays === 'custom'" class="search-custom-date-row">
              <input
                v-model="messageSearchStartDate"
                type="date"
                class="search-date-input"
                title="开始日期"
              />
              <span class="search-date-separator">至</span>
              <input
                v-model="messageSearchEndDate"
                type="date"
                class="search-date-input"
                title="结束日期"
              />
            </div>
          </div>

          <!-- 搜索历史 -->
          <div v-if="!messageSearchQuery.trim() && searchHistory.length > 0" class="search-sidebar-history">
            <div class="sidebar-section-header">
              <span class="sidebar-section-title">搜索历史</span>
              <button type="button" class="sidebar-clear-btn" @click="clearSearchHistory">清空</button>
            </div>
            <div class="sidebar-history-list">
              <button
                v-for="(item, idx) in searchHistory"
                :key="idx"
                type="button"
                class="sidebar-history-item"
                :class="{ 'privacy-blur': privacyMode }"
                @click="applySearchHistory(item)"
              >
                <svg class="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span class="truncate">{{ item }}</span>
              </button>
            </div>
          </div>

          <!-- 搜索状态 -->
          <div class="search-sidebar-status">
            <div v-if="messageSearchError" class="sidebar-status-error">
              {{ messageSearchError }}
            </div>
            <div v-else-if="messageSearchQuery.trim()" class="sidebar-status-info">
              <div class="flex items-center justify-between gap-2">
                <div class="min-w-0">
                  <template v-if="messageSearchBackendStatus === 'index_building'">
                    正在建立索引
                    <span v-if="messageSearchIndexProgressText" class="sidebar-status-detail">（{{ messageSearchIndexProgressText }}）</span>
                  </template>
                  <template v-else>
                    找到 <strong>{{ messageSearchTotal }}</strong> 条结果
                  </template>
                </div>
                <button
                  type="button"
                  class="sidebar-index-btn"
                  :disabled="messageSearchIndexActionDisabled"
                  @click="onMessageSearchIndexAction"
                >
                  {{ messageSearchIndexActionText }}
                </button>
              </div>
              <div v-if="messageSearchBackendStatus !== 'index_building' && messageSearchIndexText" class="sidebar-status-detail mt-0.5">
                {{ messageSearchIndexText }}
              </div>
            </div>
          </div>

          <!-- 搜索结果列表 -->
          <div class="search-sidebar-results">
            <div v-if="messageSearchResults.length" class="sidebar-results-list">
              <div
                v-for="(hit, idx) in messageSearchResults"
                :key="hit.id + ':' + idx"
                class="sidebar-result-card"
                :class="{ 'sidebar-result-card-selected': idx === messageSearchSelectedIndex }"
                @click="onSearchHitClick(hit, idx)"
              >
                <div class="sidebar-result-row">
                  <div class="sidebar-result-avatar" :class="{ 'privacy-blur': privacyMode }">
                    <img
                      v-if="getMessageSearchHitAvatarUrl(hit)"
                      :src="getMessageSearchHitAvatarUrl(hit)"
                      :alt="getMessageSearchHitAvatarAlt(hit)"
                      class="w-full h-full object-cover"
                    />
                    <div v-else class="sidebar-result-avatar-fallback">
                      {{ getMessageSearchHitAvatarInitial(hit) }}
                    </div>
                  </div>
                  <div class="sidebar-result-body" :class="{ 'privacy-blur': privacyMode }">
                    <div class="sidebar-result-header">
                      <span v-if="messageSearchScope === 'global'" class="sidebar-result-contact">
                        {{ hit.conversationName || hit.username }}
                      </span>
                      <span class="sidebar-result-time">{{ formatMessageFullTime(hit.createTime) }}</span>
                    </div>
                    <div class="sidebar-result-sender">
                      {{ hit.senderDisplayName || hit.senderUsername || (hit.isSent ? '我' : '') }}
                    </div>
                    <div class="sidebar-result-content" v-html="highlightKeyword(hit.snippet || hit.content || hit.title || '', messageSearchQuery)"></div>
                  </div>
                </div>
              </div>

              <!-- 加载更多 -->
              <div v-if="messageSearchHasMore" class="sidebar-load-more">
                <button
                  type="button"
                  class="sidebar-load-more-btn"
                  :disabled="messageSearchLoading"
                  @click="loadMoreSearchResults"
                >
                  {{ messageSearchLoading ? '加载中...' : '加载更多' }}
                </button>
              </div>
            </div>

            <!-- 索引构建中 -->
            <div v-else-if="messageSearchQuery.trim() && !messageSearchLoading && !messageSearchError && messageSearchBackendStatus === 'index_building'" class="sidebar-empty-state">
              <svg class="sidebar-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div class="sidebar-empty-text">正在建立搜索索引</div>
              <div class="sidebar-empty-hint">首次建立索引会花一些时间，完成后会自动开始搜索</div>
              <div v-if="messageSearchIndexProgressText" class="sidebar-empty-hint mt-1">{{ messageSearchIndexProgressText }}</div>
            </div>

            <!-- 空状态 -->
            <div v-else-if="messageSearchQuery.trim() && !messageSearchLoading && !messageSearchError && messageSearchBackendStatus !== 'index_building' && messageSearchTotal === 0" class="sidebar-empty-state">
              <svg class="sidebar-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div class="sidebar-empty-text">未找到相关消息</div>
              <div class="sidebar-empty-hint">尝试调整关键词或过滤条件</div>
            </div>

            <!-- 初始提示 -->
            <div v-else-if="!messageSearchQuery.trim() && !searchHistory.length" class="sidebar-initial-state">
              <svg class="sidebar-initial-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
              </svg>
              <div class="sidebar-initial-text">输入关键词开始搜索</div>
              <div class="sidebar-initial-hint">
                <kbd>Enter</kbd> 下一条 · <kbd>Shift+Enter</kbd> 上一条
              </div>
            </div>
          </div>
        </div>
      </transition>

    <!-- 图片预览弹窗 (全局固定定位) -->
    <div v-if="previewImageUrl" 
      class="fixed inset-0 z-[13000] bg-black/90 flex items-center justify-center cursor-zoom-out"
      @click="closeImagePreview">
      <img :src="previewImageUrl" alt="预览" class="max-w-[90vw] max-h-[90vh] object-contain" @click.stop>
      <button 
        class="absolute top-4 right-4 text-white/80 hover:text-white p-2 rounded-full bg-black/30 hover:bg-black/50 transition-colors"
        @click="closeImagePreview">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- 视频预览弹窗 (全局固定定位) -->
    <div
      v-if="previewVideoUrl"
      class="fixed inset-0 z-[13000] bg-black/90 flex items-center justify-center"
      @click="closeVideoPreview"
    >
      <div class="relative max-w-[92vw] max-h-[92vh] flex flex-col items-center" @click.stop>
        <video
          :key="previewVideoUrl"
          :src="previewVideoUrl"
          :poster="previewVideoPosterUrl"
          class="max-w-[90vw] max-h-[90vh] object-contain"
          controls
          autoplay
          playsinline
          @error="onPreviewVideoError"
        ></video>
        <div
          v-if="previewVideoError"
          class="mt-3 text-xs text-red-200 whitespace-pre-wrap text-center max-w-[90vw]"
        >
          {{ previewVideoError }}
        </div>
      </div>
      <button
        class="absolute top-4 right-4 text-white/80 hover:text-white p-2 rounded-full bg-black/30 hover:bg-black/50 transition-colors"
        @click.stop="closeVideoPreview"
      >
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- 浮动窗口（可拖动）：合并消息 / 链接卡片 -->
    <div
      v-for="win in floatingWindows"
      :key="win.id"
      class="fixed"
      :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.zIndex }"
      @mousedown="focusFloatingWindow(win.id)"
    >
      <div
        class="chat-floating-window rounded-xl overflow-hidden flex flex-col"
        :style="{ width: win.width + 'px', height: win.height + 'px' }"
      >
        <div
          class="chat-floating-window__header px-3 py-2 flex items-center justify-between select-none cursor-move"
          @mousedown.stop="startFloatingWindowDrag(win.id, $event)"
          @touchstart.stop="startFloatingWindowDrag(win.id, $event)"
        >
          <div class="chat-floating-window__title text-sm truncate min-w-0">{{ win.title || (win.kind === 'link' ? '链接' : '聊天记录') }}</div>
          <button
            type="button"
            class="chat-floating-window__close p-2 rounded flex-shrink-0"
            @click.stop="closeFloatingWindow(win.id)"
            aria-label="关闭"
            title="关闭"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="chat-floating-window__body flex-1 overflow-auto">
          <!-- Chat history window -->
          <template v-if="win.kind === 'chatHistory'">
            <div v-if="win.loading" class="text-xs text-gray-500 text-center py-2">加载中...</div>
            <div v-if="!win.records || !win.records.length" class="text-sm text-gray-500 text-center py-10">
              没有可显示的聊天记录
            </div>
            <template v-else>
              <div
                v-for="(rec, idx) in win.records"
                :key="rec.id || idx"
                class="chat-floating-window__row px-4 py-3 flex gap-3"
              >
                <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                  <img
                    v-if="rec.senderAvatar"
                    :src="rec.senderAvatar"
                    alt="头像"
                    class="w-full h-full object-cover"
                    referrerpolicy="no-referrer"
                    loading="lazy"
                    decoding="async"
                  />
                  <div v-else class="w-full h-full flex items-center justify-center text-xs font-bold text-gray-600">
                    {{ (rec.senderDisplayName || rec.sourcename || '?').charAt(0) }}
                  </div>
                </div>

                <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                  <div class="flex items-start gap-2">
                    <div class="min-w-0 flex-1">
                      <div
                        v-if="win.info?.isChatRoom && (rec.senderDisplayName || rec.sourcename)"
                        class="text-xs text-gray-500 leading-none truncate mb-1"
                      >
                        {{ rec.senderDisplayName || rec.sourcename }}
                      </div>
                    </div>
                    <div v-if="rec.fullTime || rec.sourcetime" class="text-xs text-gray-400 flex-shrink-0 leading-none">
                      {{ rec.fullTime || rec.sourcetime }}
                    </div>
                  </div>

                  <div class="mt-1">
                    <!-- Nested chat history -->
                    <div
                      v-if="rec.renderType === 'chatHistory'"
                      class="wechat-chat-history-card wechat-special-card msg-radius cursor-pointer"
                      @click.stop="openNestedChatHistory(rec)"
                    >
                      <div class="wechat-chat-history-body">
                        <div class="wechat-chat-history-title">{{ rec.title || '聊天记录' }}</div>
                        <div class="wechat-chat-history-preview" v-if="getChatHistoryPreviewLines(rec).length">
                          <div
                            v-for="(line, lidx) in getChatHistoryPreviewLines(rec)"
                            :key="lidx"
                            class="wechat-chat-history-line"
                          >
                            {{ line }}
                          </div>
                        </div>
                      </div>
                      <div class="wechat-chat-history-bottom">
                        <span>聊天记录</span>
                      </div>
                    </div>

                    <!-- Link card -->
                    <div
                      v-else-if="rec.renderType === 'link'"
                      class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
                      @click.stop="openChatHistoryLinkWindow(rec)"
                      @contextmenu="openMediaContextMenu($event, rec, 'message')"
                    >
                      <div class="wechat-link-content">
                        <div class="wechat-link-title">{{ rec.title || rec.content || rec.url || '链接' }}</div>
                        <div v-if="rec.content || rec.preview" class="wechat-link-summary">
                          <div v-if="rec.content" class="wechat-link-desc">{{ rec.content }}</div>
                          <div v-if="rec.preview" class="wechat-link-thumb">
                            <img :src="rec.preview" :alt="rec.title || '链接预览'" class="wechat-link-thumb-img" referrerpolicy="no-referrer" loading="lazy" decoding="async" @error="onChatHistoryLinkPreviewError(rec)" />
                          </div>
                        </div>
                      </div>
                      <div class="wechat-link-from">
                        <div class="wechat-link-from-avatar" :style="rec._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                          <span v-if="(!rec.fromAvatar) || (!rec._fromAvatarImgOk)">{{ getChatHistoryLinkFromAvatarText(rec) || '\u200B' }}</span>
                          <img
                            v-if="rec.fromAvatar && !rec._fromAvatarImgError"
                            :src="rec.fromAvatar"
                            alt=""
                            class="wechat-link-from-avatar-img"
                            referrerpolicy="no-referrer"
                            loading="lazy"
                            decoding="async"
                            @load="onChatHistoryFromAvatarLoad(rec)"
                            @error="onChatHistoryFromAvatarError(rec)"
                          />
                        </div>
                        <div class="wechat-link-from-name">{{ getChatHistoryLinkFromText(rec) || '\u200B' }}</div>
                      </div>
                    </div>

                    <!-- Image -->
                    <div
                      v-else-if="rec.renderType === 'image'"
                      class="msg-radius overflow-hidden cursor-pointer inline-block"
                      @click="rec.imageUrl && openImagePreview(rec.imageUrl)"
                      @contextmenu="openMediaContextMenu($event, rec, 'image')"
                    >
                      <img
                        v-if="rec.imageUrl"
                        :src="rec.imageUrl"
                        alt="图片"
                        class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity"
                      />
                      <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[图片]' }}</div>
                    </div>

                    <!-- Emoji -->
                    <div
                      v-else-if="rec.renderType === 'emoji'"
                      class="inline-block"
                      @contextmenu="openMediaContextMenu($event, rec, 'emoji')"
                    >
                      <img v-if="rec.emojiUrl" :src="rec.emojiUrl" alt="表情" class="w-24 h-24 object-contain" />
                      <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[表情]' }}</div>
                    </div>

                    <!-- Video (fallback to thumbnail/play) -->
                    <div
                      v-else-if="rec.renderType === 'video'"
                      class="msg-radius overflow-hidden relative bg-black/5 inline-block"
                      @contextmenu="openMediaContextMenu($event, rec, 'video')"
                    >
                      <img
                        v-if="rec.videoThumbUrl && !rec._videoThumbError"
                        :src="rec.videoThumbUrl"
                        alt="视频"
                        class="block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover"
                        @error="onChatHistoryVideoThumbError(rec)"
                      />
                      <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[视频]' }}</div>
                      <button
                        v-if="rec.videoUrl"
                        type="button"
                        class="absolute inset-0 flex items-center justify-center"
                        @click.stop="openVideoPreview(rec.videoUrl, rec.videoThumbUrl)"
                      >
                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                      </button>
                      <div
                        v-if="rec.videoDuration"
                        class="absolute bottom-2 right-2 text-xs text-white bg-black/55 px-1.5 py-0.5 rounded"
                      >
                        {{ formatChatHistoryVideoDuration(rec.videoDuration) }}
                      </div>
                    </div>

                    <!-- Text / others -->
                    <div
                      v-else
                      class="text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                      @contextmenu="openMediaContextMenu($event, rec, 'message')"
                    >
                      <span v-for="(seg, sidx) in parseTextWithEmoji(rec.content)" :key="sidx">
                        <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                        <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </template>

          <!-- Link detail window -->
          <template v-else-if="win.kind === 'link'">
            <div class="p-4 space-y-3">
              <div
                class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
                @click.stop="win.url && openUrlInBrowser(win.url)"
                @contextmenu="openMediaContextMenu($event, win, 'message')"
              >
                <div class="wechat-link-content">
                  <div class="wechat-link-title">{{ win.title || win.url || '链接' }}</div>
                  <div v-if="win.content || win.preview" class="wechat-link-summary">
                    <div v-if="win.content" class="wechat-link-desc">{{ win.content }}</div>
                    <div v-if="win.preview" class="wechat-link-thumb">
                      <img :src="win.preview" :alt="win.title || '链接预览'" class="wechat-link-thumb-img" referrerpolicy="no-referrer" loading="lazy" decoding="async" @error="onChatHistoryLinkPreviewError(win)" />
                    </div>
                  </div>
                </div>
                <div class="wechat-link-from">
                  <div class="wechat-link-from-avatar" :style="win._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                    <span v-if="(!win.fromAvatar) || (!win._fromAvatarImgOk)">{{ getChatHistoryLinkFromAvatarText(win) || '\u200B' }}</span>
                    <img
                      v-if="win.fromAvatar && !win._fromAvatarImgError"
                      :src="win.fromAvatar"
                      alt=""
                      class="wechat-link-from-avatar-img"
                      referrerpolicy="no-referrer"
                      loading="lazy"
                      decoding="async"
                      @load="onChatHistoryFromAvatarLoad(win)"
                      @error="onChatHistoryFromAvatarError(win)"
                    />
                  </div>
                  <div class="wechat-link-from-name">{{ getChatHistoryLinkFromText(win) || '\u200B' }}</div>
                </div>
              </div>

              <div v-if="win.loading" class="text-xs text-gray-500">解析中...</div>
              <div v-if="win.url" class="text-xs text-gray-500 break-all">{{ win.url }}</div>
              <div class="flex gap-2">
                <button
                  class="px-3 py-1.5 text-sm rounded-md border border-gray-200 bg-white hover:bg-gray-50"
                  type="button"
                  :disabled="!win.url"
                  :class="!win.url ? 'opacity-50 cursor-not-allowed' : ''"
                  @click.stop="win.url && openUrlInBrowser(win.url)"
                >
                  在浏览器打开
                </button>
                <button
                  class="px-3 py-1.5 text-sm rounded-md border border-gray-200 bg-white hover:bg-gray-50"
                  type="button"
                  :disabled="!win.url"
                  :class="!win.url ? 'opacity-50 cursor-not-allowed' : ''"
                  @click.stop="win.url && copyTextToClipboard(win.url)"
                >
                  复制链接
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 合并转发聊天记录弹窗 -->
    <div
      v-if="chatHistoryModalVisible"
      class="chat-history-modal-overlay fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      @click="closeChatHistoryModal"
    >
      <div
        class="chat-history-modal-panel w-[92vw] max-w-[560px] max-h-[80vh] rounded-xl shadow-xl overflow-hidden flex flex-col"
        @click.stop
      >
        <div class="chat-history-modal-header px-4 py-3 border-b flex items-center justify-between">
          <div class="flex items-center gap-2 min-w-0">
            <button
              v-if="chatHistoryModalStack.length"
              type="button"
              class="chat-history-modal-icon-btn p-2 rounded flex-shrink-0"
              @click="goBackChatHistoryModal"
              aria-label="返回"
              title="返回"
            >
              <svg class="chat-history-modal-icon w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div class="chat-history-modal-title text-sm truncate">{{ chatHistoryModalTitle || '聊天记录' }}</div>
          </div>
          <button
            type="button"
            class="chat-history-modal-icon-btn p-2 rounded"
            @click="closeChatHistoryModal"
            aria-label="关闭"
            title="关闭"
          >
            <svg class="chat-history-modal-icon w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="chat-history-modal-body flex-1 overflow-auto">
          <div v-if="!chatHistoryModalRecords.length" class="chat-history-modal-empty text-sm text-center py-10">
            没有可显示的聊天记录
          </div>
          <template v-else>
            <div
              v-for="(rec, idx) in chatHistoryModalRecords"
              :key="rec.id || idx"
              class="chat-history-modal-row px-4 py-3 flex gap-3 border-b"
            >
              <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                <img
                  v-if="rec.senderAvatar"
                  :src="rec.senderAvatar"
                  alt="头像"
                  class="w-full h-full object-cover"
                  referrerpolicy="no-referrer"
                  loading="lazy"
                  decoding="async"
                />
                <div v-else class="w-full h-full flex items-center justify-center text-xs font-bold text-gray-600">
                  {{ (rec.senderDisplayName || rec.sourcename || '?').charAt(0) }}
                </div>
              </div>

              <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                <div class="flex items-start gap-2">
                  <div class="min-w-0 flex-1">
                    <div
                      v-if="chatHistoryModalInfo?.isChatRoom && (rec.senderDisplayName || rec.sourcename)"
                      class="chat-history-modal-sender text-xs leading-none truncate mb-1"
                    >
                      {{ rec.senderDisplayName || rec.sourcename }}
                    </div>
                  </div>
                  <div v-if="rec.fullTime || rec.sourcetime" class="chat-history-modal-time text-xs flex-shrink-0 leading-none">
                    {{ rec.fullTime || rec.sourcetime }}
                  </div>
                </div>

                  <div class="mt-1">
                  <!-- 合并转发聊天记录（Chat History） -->
                  <div
                    v-if="rec.renderType === 'chatHistory'"
                    class="wechat-chat-history-card wechat-special-card msg-radius cursor-pointer"
                    @click.stop="openNestedChatHistory(rec)"
                  >
                    <div class="wechat-chat-history-body">
                      <div class="wechat-chat-history-title">{{ rec.title || '聊天记录' }}</div>
                      <div class="wechat-chat-history-preview" v-if="getChatHistoryPreviewLines(rec).length">
                        <div
                          v-for="(line, lidx) in getChatHistoryPreviewLines(rec)"
                          :key="lidx"
                          class="wechat-chat-history-line"
                        >
                          {{ line }}
                        </div>
                      </div>
                    </div>
                    <div class="wechat-chat-history-bottom">
                      <span>聊天记录</span>
                    </div>
                  </div>

                  <!-- 链接卡片 -->
                  <div
                    v-else-if="rec.renderType === 'link'"
                    class="wechat-link-card wechat-special-card msg-radius cursor-pointer"
                    @click.stop="openChatHistoryLinkWindow(rec)"
                    @contextmenu="openMediaContextMenu($event, rec, 'message')"
                  >
                    <div class="wechat-link-content">
                      <div class="wechat-link-title">{{ rec.title || rec.content || rec.url || '链接' }}</div>
                      <div v-if="rec.content || rec.preview" class="wechat-link-summary">
                        <div v-if="rec.content" class="wechat-link-desc">{{ rec.content }}</div>
                        <div v-if="rec.preview" class="wechat-link-thumb">
                          <img :src="rec.preview" :alt="rec.title || '链接预览'" class="wechat-link-thumb-img" referrerpolicy="no-referrer" loading="lazy" decoding="async" @error="onChatHistoryLinkPreviewError(rec)" />
                        </div>
                      </div>
                    </div>
                    <div class="wechat-link-from">
                      <div class="wechat-link-from-avatar" :style="rec._fromAvatarImgOk ? { background: '#fff', color: 'transparent' } : null" aria-hidden="true">
                        <span v-if="(!rec.fromAvatar) || (!rec._fromAvatarImgOk)">{{ getChatHistoryLinkFromAvatarText(rec) || '\u200B' }}</span>
                        <img
                          v-if="rec.fromAvatar && !rec._fromAvatarImgError"
                          :src="rec.fromAvatar"
                          alt=""
                          class="wechat-link-from-avatar-img"
                          referrerpolicy="no-referrer"
                          loading="lazy"
                          decoding="async"
                          @load="onChatHistoryFromAvatarLoad(rec)"
                          @error="onChatHistoryFromAvatarError(rec)"
                        />
                      </div>
                      <div class="wechat-link-from-name">{{ getChatHistoryLinkFromText(rec) || '\u200B' }}</div>
                    </div>
                  </div>

                  <!-- 视频 -->
                  <div
                    v-else-if="rec.renderType === 'video'"
                    class="msg-radius overflow-hidden relative bg-black/5 inline-block"
                    @contextmenu="openMediaContextMenu($event, rec, 'video')"
                  >
                    <img
                      v-if="rec.videoThumbUrl && !rec._videoThumbError"
                      :src="rec.videoThumbUrl"
                      alt="视频"
                      class="block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover"
                      @error="onChatHistoryVideoThumbError(rec)"
                    />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[视频]' }}</div>

                    <button
                      v-if="rec.videoThumbUrl && rec.videoUrl"
                      type="button"
                      class="absolute inset-0 flex items-center justify-center"
                      @click.stop="openVideoPreview(rec.videoUrl, rec.videoThumbUrl)"
                    >
                      <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    </button>
                    <div class="absolute inset-0 flex items-center justify-center" v-else-if="rec.videoThumbUrl">
                      <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    </div>
                    <div
                      v-if="rec.videoDuration"
                      class="absolute bottom-2 right-2 text-xs text-white bg-black/55 px-1.5 py-0.5 rounded"
                    >
                      {{ formatChatHistoryVideoDuration(rec.videoDuration) }}
                    </div>
                  </div>

                  <!-- 图片 -->
                  <div
                    v-else-if="rec.renderType === 'image'"
                    class="msg-radius overflow-hidden cursor-pointer inline-block"
                    @click="rec.imageUrl && openImagePreview(rec.imageUrl)"
                    @contextmenu="openMediaContextMenu($event, rec, 'image')"
                  >
                    <img
                      v-if="rec.imageUrl"
                      :src="rec.imageUrl"
                      alt="图片"
                      class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity"
                    />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[图片]' }}</div>
                  </div>

                  <!-- 表情 -->
                  <div
                    v-else-if="rec.renderType === 'emoji'"
                    class="inline-block"
                    @contextmenu="openMediaContextMenu($event, rec, 'emoji')"
                  >
                    <img v-if="rec.emojiUrl" :src="rec.emojiUrl" alt="表情" class="w-24 h-24 object-contain" />
                    <div v-else class="px-3 py-2 text-sm text-gray-700">{{ rec.content || '[表情]' }}</div>
                  </div>

                  <!-- 引用（回复） -->
                  <div v-else-if="rec.renderType === 'quote'" class="max-w-[420px]">
                    <div
                      class="px-2 text-xs text-neutral-700 rounded max-w-[404px] flex items-center bg-[#e1e1e1] cursor-pointer select-none"
                      @click="openChatHistoryQuote(rec)"
                      @contextmenu="openMediaContextMenu($event, rec.quoteMedia || rec, rec.quote?.kind || 'message')"
                    >
                      <div class="w-10 h-10 rounded overflow-hidden bg-neutral-300 flex-shrink-0 mr-2">
                        <img
                          v-if="rec.quote?.thumbUrl && !rec._quoteThumbError"
                          :src="rec.quote.thumbUrl"
                          alt="引用"
                          class="w-full h-full object-cover"
                          @error="onChatHistoryQuoteThumbError(rec)"
                        />
                        <div v-else class="w-full h-full flex items-center justify-center text-[10px] text-neutral-600">
                          {{ rec.quote?.kind === 'video' ? '视频' : (rec.quote?.kind === 'image' ? '图片' : '表情') }}
                        </div>
                      </div>
                      <div class="min-w-0 flex-1 py-2">
                        <div class="line-clamp-2">
                          {{ rec.quote?.label || (rec.quote?.kind === 'video' ? '[视频]' : (rec.quote?.kind === 'image' ? '[图片]' : '[表情]')) }}
                        </div>
                      </div>
                      <div v-if="rec.quote?.kind === 'video' && rec.quote?.duration" class="ml-2 flex-shrink-0 text-[11px] text-neutral-600">
                        {{ formatChatHistoryVideoDuration(rec.quote.duration) }}
                      </div>
                    </div>

                    <div
                      class="mt-1 text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                      @contextmenu="openMediaContextMenu($event, rec, 'message')"
                    >
                      <span v-for="(seg, sidx) in parseTextWithEmoji(rec.content)" :key="sidx">
                        <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                        <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                      </span>
                    </div>
                  </div>

                  <!-- 文本/其它 -->
                  <div
                    v-else
                    class="text-sm text-gray-900 whitespace-pre-wrap break-words leading-relaxed"
                    @contextmenu="openMediaContextMenu($event, rec, 'message')"
                  >
                    <span v-for="(seg, sidx) in parseTextWithEmoji(rec.content)" :key="sidx">
                      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
                      <img v-else :src="seg.emojiSrc" :alt="seg.content" class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px">
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
      </div>

    <div
      v-if="contextMenu.visible"
      ref="contextMenuElement"
      class="chat-context-menu fixed z-[12000] max-h-[calc(100vh-16px)] overflow-y-auto rounded-md text-sm"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <button
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        @click="onCopyMessageTextClick"
      >
        复制文本
      </button>
      <button
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        @click="onCopyMessageJsonClick"
      >
        复制消息 JSON
      </button>
      <button
        v-if="contextMenu.message?.renderType === 'quote' && contextMenu.message?.quoteServerId"
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        @click="onLocateQuotedMessageClick"
      >
        定位引用消息
      </button>
      <button
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        :disabled="contextMenu.disabled"
        :class="contextMenu.disabled ? 'opacity-50 cursor-not-allowed' : ''"
        @click="onOpenFolderClick"
      >
        打开文件夹
      </button>

      <div class="border-t border-gray-200"></div>

      <button
        v-if="contextMenu.message?.id"
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        @click="onEditMessageClick"
      >
        {{ isLikelyTextMessage(contextMenu.message) ? '修改消息' : '编辑源码' }}
      </button>
      <button
        v-if="contextMenu.message?.id"
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        @click="onEditMessageFieldsClick"
      >
        字段编辑
      </button>
      <button
        v-if="contextMenu.editStatus?.modified"
        class="chat-context-menu__item block w-full text-left px-3 py-2 text-red-600"
        type="button"
        @click="onResetEditedMessageClick"
      >
        恢复原消息
      </button>
      <button
        v-if="contextMenu.message?.id"
        class="chat-context-menu__item block w-full text-left px-3 py-2"
        type="button"
        @click="onRepairMessageSenderAsMeClick"
      >
        修复为我发送
      </button>
      <button
        v-if="contextMenu.message?.id"
        class="chat-context-menu__item block w-full text-left px-3 py-2 text-orange-600"
        type="button"
        @click="onFlipWechatMessageDirectionClick"
      >
        反转微信气泡位置
      </button>
      <div v-if="contextMenu.editStatusLoading" class="px-3 py-2 text-xs text-gray-400">检查修改状态…</div>
    </div>

    <!-- 修改消息弹窗 -->
    <div v-if="messageEditModal.open" class="fixed inset-0 z-[11000] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeMessageEditModal"></div>
      <div class="chat-edit-modal relative w-[860px] max-w-[95vw] rounded-lg overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">{{ messageEditModal.mode === 'content' ? '修改消息' : '编辑源码' }}</div>
          <button class="ml-auto text-gray-400 hover:text-gray-600" type="button" @click="closeMessageEditModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-3">
          <div v-if="messageEditModal.error" class="text-sm text-red-600 whitespace-pre-wrap">{{ messageEditModal.error }}</div>
          <div v-if="messageEditModal.loading" class="text-sm text-gray-500">加载中…</div>

          <textarea
            v-model="messageEditModal.draft"
            class="w-full min-h-[240px] rounded-md border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#03C160]/20"
            :disabled="messageEditModal.loading || messageEditModal.saving"
            :placeholder="messageEditModal.mode === 'content' ? '请输入新的消息内容' : '请输入新的 message_content（可输入 0x... 写入 BLOB）'"
          ></textarea>

          <details v-if="messageEditModal.rawRow" class="text-xs">
            <summary class="cursor-pointer select-none text-gray-700 hover:text-gray-900">查看源消息（raw）</summary>
            <div class="mt-2 rounded border border-gray-200 bg-gray-50 p-2 overflow-auto">
              <pre class="text-[11px] leading-snug whitespace-pre-wrap break-words">{{ prettyJson(messageEditModal.rawRow) }}</pre>
            </div>
          </details>
        </div>

        <div class="px-5 py-3 border-t border-gray-200 flex items-center justify-end gap-2">
          <button class="text-sm px-4 py-2 rounded border border-gray-200 hover:bg-gray-50" type="button" @click="closeMessageEditModal">取消</button>
          <button
            class="text-sm px-4 py-2 rounded bg-[#03C160] text-white hover:bg-[#02ad55]"
            type="button"
            :disabled="messageEditModal.loading || messageEditModal.saving"
            :class="messageEditModal.loading || messageEditModal.saving ? 'opacity-60 cursor-not-allowed' : ''"
            @click="saveMessageEditModal"
          >
            保存
          </button>
        </div>
      </div>
    </div>

    <!-- 字段编辑弹窗 -->
    <div v-if="messageFieldsModal.open" class="fixed inset-0 z-[11000] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeMessageFieldsModal"></div>
      <div class="chat-edit-modal relative w-[920px] max-w-[95vw] rounded-lg overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">字段编辑</div>
          <button class="ml-auto text-gray-400 hover:text-gray-600" type="button" @click="closeMessageFieldsModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-3">
          <div v-if="messageFieldsModal.error" class="text-sm text-red-600 whitespace-pre-wrap">{{ messageFieldsModal.error }}</div>
          <div v-if="messageFieldsModal.loading" class="text-sm text-gray-500">加载中…</div>

          <div class="flex items-center gap-3">
            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input v-model="messageFieldsModal.unsafe" type="checkbox" class="rounded border-gray-300" />
              <span>我已知风险（允许修改 local_id / WCDB_CT / BLOB 等）</span>
            </label>
            <div class="text-xs text-gray-500">修改时间/类型会自动同步 message_resource 关键字段</div>
          </div>

          <textarea
            v-model="messageFieldsModal.editsJson"
            class="w-full min-h-[320px] rounded-md border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#03C160]/20"
            :disabled="messageFieldsModal.loading || messageFieldsModal.saving"
            placeholder='{ "message_content": "...", "create_time": 123 }'
          ></textarea>

          <details v-if="messageFieldsModal.rawRow" class="text-xs">
            <summary class="cursor-pointer select-none text-gray-700 hover:text-gray-900">查看源消息（raw）</summary>
            <div class="mt-2 rounded border border-gray-200 bg-gray-50 p-2 overflow-auto">
              <pre class="text-[11px] leading-snug whitespace-pre-wrap break-words">{{ prettyJson(messageFieldsModal.rawRow) }}</pre>
            </div>
          </details>
        </div>

        <div class="px-5 py-3 border-t border-gray-200 flex items-center justify-end gap-2">
          <button class="text-sm px-4 py-2 rounded border border-gray-200 hover:bg-gray-50" type="button" @click="closeMessageFieldsModal">取消</button>
          <button
            class="text-sm px-4 py-2 rounded bg-[#03C160] text-white hover:bg-[#02ad55]"
            type="button"
            :disabled="messageFieldsModal.loading || messageFieldsModal.saving"
            :class="messageFieldsModal.loading || messageFieldsModal.saving ? 'opacity-60 cursor-not-allowed' : ''"
            @click="saveMessageFieldsModal"
          >
            保存
          </button>
        </div>
      </div>
    </div>

    <!-- 导出弹窗 -->
    <div v-if="exportModalOpen" class="fixed inset-0 z-[11000] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="closeExportModal"></div>
      <div class="chat-export-modal relative w-[960px] max-w-[95vw] bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center">
          <div class="text-base font-medium text-gray-900">导出聊天记录（离线 ZIP）</div>
          <button class="ml-auto text-gray-400 hover:text-gray-700" type="button" @click="closeExportModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="p-5 max-h-[75vh] overflow-y-auto space-y-5">
          <div v-if="exportError" class="text-sm text-red-600 whitespace-pre-wrap">{{ exportError }}</div>
          <div v-if="privacyMode" class="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-md px-3 py-2">
            已开启隐私模式：导出将隐藏会话/用户名/内容，并且不会打包头像与媒体。
          </div>

          <div class="space-y-5">
            <div class="flex flex-wrap items-end gap-3 xl:flex-nowrap">
              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">范围</div>
                <div class="flex flex-wrap items-center gap-2 text-sm text-gray-700">
                  <button
                    type="button"
                    class="px-2.5 py-1 text-xs rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    :class="exportScope === 'current' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'"
                    :disabled="!selectedContact?.username"
                    @click="exportScope = 'current'"
                  >
                    当前会话
                  </button>
                  <button
                    type="button"
                    class="px-2.5 py-1 text-xs rounded-md border transition-colors"
                    :class="exportScope === 'selected' && exportListTab === 'all' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'"
                    @click="onExportBatchScopeClick('all')"
                  >
                    全部 {{ exportContactCounts.total }}
                  </button>
                  <button
                    type="button"
                    class="px-2.5 py-1 text-xs rounded-md border transition-colors"
                    :class="exportScope === 'selected' && exportListTab === 'groups' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'"
                    @click="onExportBatchScopeClick('groups')"
                  >
                    群聊 {{ exportContactCounts.groups }}
                  </button>
                  <button
                    type="button"
                    class="px-2.5 py-1 text-xs rounded-md border transition-colors"
                    :class="exportScope === 'selected' && exportListTab === 'singles' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'"
                    @click="onExportBatchScopeClick('singles')"
                  >
                    单聊 {{ exportContactCounts.singles }}
                  </button>
                </div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">格式</div>
                <div class="flex items-center gap-2 text-sm text-gray-700">
                  <label class="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border cursor-pointer transition-colors" :class="exportFormat === 'json' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="json" v-model="exportFormat" class="hidden" />
                    <span>JSON</span>
                  </label>
                  <label class="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border cursor-pointer transition-colors" :class="exportFormat === 'txt' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="txt" v-model="exportFormat" class="hidden" />
                    <span>TXT</span>
                  </label>
                  <label class="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border cursor-pointer transition-colors" :class="exportFormat === 'html' ? 'bg-[#03C160] text-white border-[#03C160]' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'">
                    <input type="radio" value="html" v-model="exportFormat" class="hidden" />
                    <span>HTML</span>
                  </label>
                </div>
              </div>

              <div class="flex-1 min-w-[280px]">
                <div class="text-sm font-medium text-gray-800 mb-2">时间范围（可选）</div>
                <div class="flex items-center gap-1.5 flex-wrap">
                  <input
                    v-model="exportStartLocal"
                    type="datetime-local"
                    class="px-2 py-1 text-xs rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                  <span class="text-gray-400">-</span>
                  <input
                    v-model="exportEndLocal"
                    type="datetime-local"
                    class="px-2 py-1 text-xs rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                </div>
              </div>
            </div>

            <div v-if="exportFormat === 'html'" class="mt-3">
              <div class="text-sm font-medium text-gray-800 mb-2">HTML 选项</div>
              <div class="p-3 bg-gray-50 rounded-md border border-gray-200">
                <label class="flex items-start gap-2 text-sm text-gray-700">
                  <input type="checkbox" v-model="exportDownloadRemoteMedia" :disabled="privacyMode" />
                  <span>允许联网下载链接/引用缩略图（提高离线完整性）</span>
                </label>
                <div class="mt-1 text-xs text-gray-500">
                  仅 HTML 生效；会在导出时尝试下载远程缩略图并写入 ZIP（已做安全限制）。隐私模式下自动忽略。
                </div>

                <div class="mt-3 flex flex-wrap items-center gap-3">
                  <div class="text-sm text-gray-700">每页消息数</div>
                  <input
                    v-model.number="exportHtmlPageSize"
                    type="number"
                    min="0"
                    step="100"
                    class="w-32 px-2.5 py-1.5 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  />
                  <div class="text-xs text-gray-500">推荐 1000；0=单文件（打开大聊天可能很卡）</div>
                </div>
              </div>
            </div>

            <div v-if="exportScope === 'selected'" class="mt-3">
              <div class="mb-2 text-xs text-gray-500">
                点击上方范围可筛选并默认全选当前结果，再次点击可取消全选；下方整行可点选会话
              </div>
              <div class="flex items-center gap-2 mb-2">
                <input
                  v-model="exportSearchQuery"
                  type="text"
                  placeholder="搜索会话（名称/username）"
                  class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                  :class="{ 'privacy-blur': privacyMode }"
                />
              </div>
              <div class="border border-gray-200 rounded-md max-h-56 overflow-y-auto">
                <label
                  v-for="c in exportFilteredContacts"
                  :key="c.username"
                  class="px-3 py-2 border-b border-gray-100 flex items-center gap-2 cursor-pointer transition-colors"
                  :class="isExportContactSelected(c.username) ? 'bg-[#03C160]/5 hover:bg-[#03C160]/10' : 'hover:bg-gray-50'"
                >
                  <input type="checkbox" :value="c.username" v-model="exportSelectedUsernames" class="cursor-pointer" />
                  <div class="w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0" :class="{ 'privacy-blur': privacyMode }">
                    <img v-if="c.avatar" :src="c.avatar" :alt="c.name + '头像'" class="w-full h-full object-cover" referrerpolicy="no-referrer" @error="onAvatarError($event, c)" />
                    <div v-else class="w-full h-full flex items-center justify-center text-xs font-bold text-gray-600">
                      {{ (c.name || c.username || '?').charAt(0) }}
                    </div>
                  </div>
                  <div class="min-w-0 flex-1" :class="{ 'privacy-blur': privacyMode }">
                    <div class="text-sm text-gray-800 truncate">
                      {{ c.name }}
                      <span class="text-xs text-gray-500">{{ c.isGroup ? '（群）' : '' }}</span>
                    </div>
                    <div class="text-xs text-gray-500 truncate">{{ c.username }}</div>
                  </div>
                </label>
                <div v-if="exportFilteredContacts.length === 0" class="px-3 py-3 text-sm text-gray-500">
                  无匹配会话
                </div>
              </div>
              <div class="mt-2 text-xs text-gray-500">
                已选 {{ exportSelectedUsernames.length }} 个会话
              </div>
            </div>

            <div>
              <div class="text-sm font-medium text-gray-800 mb-2">消息类型（导出内容）</div>
              <div class="mt-2 p-3 bg-gray-50 rounded-md border border-gray-200">
                <div class="flex items-center gap-2 mb-2">
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = exportMessageTypeOptions.map((x) => x.value)"
                  >
                    全选
                  </button>
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = ['voice']"
                  >
                    只语音
                  </button>
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = ['transfer']"
                  >
                    只转账
                  </button>
                  <button
                    type="button"
                    class="text-xs px-2 py-1 rounded border border-gray-200 bg-white hover:bg-gray-50"
                    @click="exportMessageTypes = ['redPacket']"
                  >
                    只红包
                  </button>
                  <div class="ml-auto text-xs text-gray-500">已选 {{ exportMessageTypes.length }} 项</div>
                </div>
                <div class="grid grid-cols-3 md:grid-cols-4 gap-2 text-sm text-gray-700">
                  <label v-for="opt in exportMessageTypeOptions" :key="opt.value" class="flex items-center gap-2">
                    <input type="checkbox" :value="opt.value" v-model="exportMessageTypes" />
                    <span>{{ opt.label }}</span>
                  </label>
                </div>
              </div>
              <div class="mt-1 text-xs text-gray-500">
                仅导出已勾选的消息类型；勾选图片/表情/视频/语音/文件时，会导出对应多媒体文件。
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">文件名（可选）</div>
                <input
                  v-model="exportFileName"
                  type="text"
                  placeholder="例如：我的微信导出_2025-12-23.zip"
                  class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#03C160]/30"
                />
                <div class="mt-1 text-xs text-gray-500">不填则自动生成</div>
              </div>

              <div>
                <div class="text-sm font-medium text-gray-800 mb-2">导出目录</div>
                <div class="flex items-center gap-2">
                  <div class="px-3 py-2 rounded-md border border-gray-200 bg-gray-50 text-xs break-all min-h-[38px] min-w-0 flex-1">
                    {{ exportFolder || '未选择' }}
                  </div>
                  <button
                    type="button"
                    class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                    @click="chooseExportFolder"
                  >
                    选择文件夹
                  </button>
                  <button
                    v-if="exportFolder"
                    type="button"
                    class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                    @click="exportFolder = ''; exportFolderHandle = null; exportSaveMsg = ''"
                  >
                    清空
                  </button>
                </div>
                <div class="mt-1 text-xs text-gray-500">桌面端与支持 File System Access API 的浏览器均可选择目录。</div>
              </div>
            </div>
          </div>

          <div v-if="exportJob" class="border border-gray-200 rounded-md bg-gray-50 p-4">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-gray-900">任务：{{ exportJob.exportId }}</div>
              <div class="text-xs text-gray-600">状态：{{ exportJob.status }}</div>
            </div>
            <div class="mt-2 text-xs text-gray-700 space-y-2">
              <div class="flex items-center justify-between">
                <div>会话：{{ exportJob.progress?.conversationsDone || 0 }}/{{ exportJob.progress?.conversationsTotal || 0 }}</div>
                <div class="text-gray-600">{{ exportOverallPercent }}%</div>
              </div>
              <div class="h-2 rounded-full bg-white border border-gray-200 overflow-hidden">
                <div
                  class="h-full bg-[#03C160] transition-all duration-300"
                  :style="{ width: exportOverallPercent + '%' }"
                ></div>
              </div>

              <div v-if="exportJob.status === 'running' && exportJob.progress?.currentConversationUsername" class="space-y-1">
                <div class="flex items-center justify-between gap-2">
                  <div class="truncate">
                    当前：{{ exportJob.progress?.currentConversationName || exportJob.progress?.currentConversationUsername }}
                    （{{ exportJob.progress?.currentConversationMessagesExported || 0 }}/{{ exportJob.progress?.currentConversationMessagesTotal || 0 }}）
                  </div>
                  <div class="text-gray-600">
                    <span v-if="exportCurrentPercent != null">{{ exportCurrentPercent }}%</span>
                    <span v-else>…</span>
                  </div>
                </div>
                <div class="h-2 rounded-full bg-white border border-gray-200 overflow-hidden">
                  <div
                    v-if="exportCurrentPercent != null"
                    class="h-full bg-sky-500 transition-all duration-300"
                    :style="{ width: exportCurrentPercent + '%' }"
                  ></div>
                  <div v-else class="h-full bg-sky-500/60 animate-pulse" style="width: 30%"></div>
                </div>
              </div>

              <div>消息：{{ exportJob.progress?.messagesExported || 0 }}；媒体：{{ exportJob.progress?.mediaCopied || 0 }}；缺失：{{ exportJob.progress?.mediaMissing || 0 }}</div>
            </div>

            <div class="mt-3 flex items-center gap-2">
              <button
                v-if="exportJob.status === 'done' && hasWebExportFolder"
                class="text-sm px-3 py-2 rounded-md bg-[#03C160] text-white hover:bg-[#02a650] disabled:opacity-60"
                type="button"
                :disabled="exportSaveBusy"
                @click="saveExportToSelectedFolder"
              >
                {{ exportSaveBusy ? '保存中...' : '保存到已选目录' }}
              </button>
              <a
                v-if="exportJob.status === 'done' && !hasWebExportFolder"
                class="text-sm px-3 py-2 rounded-md bg-[#03C160] text-white hover:bg-[#02a650]"
                :href="getExportDownloadUrl(exportJob.exportId)"
                target="_blank"
              >
                下载 ZIP
              </a>
              <button
                v-if="exportJob.status === 'running'"
                class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50"
                type="button"
                @click="cancelCurrentExport"
              >
                取消任务
              </button>
            </div>
            <div v-if="exportSaveMsg" class="mt-2 text-xs text-green-600 whitespace-pre-wrap">{{ exportSaveMsg }}</div>

            <div v-if="exportJob.status === 'error'" class="mt-2 text-sm text-red-600 whitespace-pre-wrap">
              {{ exportJob.error || '导出失败' }}
            </div>
          </div>
        </div>

        <div class="px-5 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
          <button class="text-sm px-3 py-2 rounded-md bg-white border border-gray-200 hover:bg-gray-50" type="button" @click="closeExportModal">
            关闭
          </button>
          <button
            class="text-sm px-3 py-2 rounded-md bg-[#03C160] text-white hover:bg-[#02a650] disabled:opacity-60"
            type="button"
            @click="startChatExport"
            :disabled="isExportCreating"
          >
            {{ isExportCreating ? '创建中...' : '开始导出' }}
          </button>
        </div>
      </div>
    </div>
</template>

<script>
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'ChatOverlays',
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    return { ...props.state }
  }
})
</script>
