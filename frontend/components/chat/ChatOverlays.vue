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
              <span v-if="cell.day" class="calendar-day-count">{{ cell.countText }}</span>
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
              @click="closeMessageSearch('close-button')"
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
                @keydown.enter.exact.prevent="runMessageSearch({ reset: true, source: 'input-enter' })"
                @keydown.enter.shift.prevent="onSearchPrev"
                @keydown.escape="closeMessageSearch('input-escape')"
              />

              <!-- 清除按钮 -->
                <button
                  v-if="messageSearchQuery"
                  type="button"
                  class="search-clear-inline"
                  @click="messageSearchQuery = ''; runMessageSearch({ reset: true, source: 'clear-button' })"
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
                @click="runMessageSearch({ reset: true, source: 'search-button' })"
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
                  @mousedown.stop
                  @click.stop.prevent="toggleMessageSearchSenderDropdown"
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
                      @mousedown.stop
                      @click.stop.prevent="selectMessageSearchSender('')"
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
                      暂无发送者
                    </div>
                    <template v-else>
                      <button
                        v-for="s in filteredMessageSearchSenderOptions"
                        :key="s.username"
                        type="button"
                        class="chat-overlay-option w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs"
                        :class="messageSearchSender === s.username ? 'chat-overlay-option--active' : ''"
                        @mousedown.stop
                        @click.stop.prevent="selectMessageSearchSender(s.username)"
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
                @pointerdown="onSearchHitPointerDown(hit, idx, $event)"
                @click.capture="onSearchHitClickCapture(hit, idx, $event)"
                @click="onSearchHitClick(hit, idx, $event)"
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
                    <button
                      v-if="hit.senderUsername"
                      type="button"
                      class="sidebar-result-sender sidebar-result-sender-clickable"
                      title="按此发送者筛选"
                      @mousedown.stop
                      @click.stop.prevent="onSearchResultSenderClick(hit, $event)"
                    >
                      {{ hit.senderDisplayName || hit.senderUsername || (hit.isSent ? '我' : '') }}
                    </button>
                    <div v-else class="sidebar-result-sender">
                      {{ hit.isSent ? '我' : '' }}
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
      class="fixed inset-0 z-[13000] bg-black/90 flex items-center justify-center cursor-zoom-out overflow-hidden"
      title="滚轮缩放图片，双击重置"
      @click="closeImagePreview"
      @wheel.prevent.stop="onPreviewImageWheel"
    >
      <div
        class="relative max-w-[96vw] max-h-[96vh] flex items-center justify-center cursor-default"
        @click.stop
      >
        <img
          :src="previewImageUrl"
          alt="预览"
          class="max-w-[90vw] max-h-[90vh] object-contain select-none transition-transform duration-100 ease-out"
          :style="previewImageTransformStyle"
          draggable="false"
          @dblclick.stop="resetPreviewImageTransform"
        >
      </div>

      <button
        v-if="canSwitchPreviewImage"
        type="button"
        class="absolute left-4 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/35 text-white/85 shadow-lg transition hover:bg-black/55 hover:text-white"
        title="上一张"
        @click.stop="showPrevPreviewImage"
      >
        <svg class="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <button
        v-if="canSwitchPreviewImage"
        type="button"
        class="absolute right-4 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/35 text-white/85 shadow-lg transition hover:bg-black/55 hover:text-white"
        title="下一张"
        @click.stop="showNextPreviewImage"
      >
        <svg class="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <div
        class="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-full bg-black/45 px-2 py-1.5 text-white/90 shadow-lg backdrop-blur"
        @click.stop
      >
        <span
          v-if="previewImageCounterText"
          class="min-w-[48px] px-2 text-center text-[12px] tabular-nums text-white/80"
        >
          {{ previewImageCounterText }}
        </span>
        <div v-if="previewImageCounterText" class="mx-1 h-5 w-px bg-white/20"></div>
        <button
          type="button"
          class="rounded-full px-2.5 py-1 text-[13px] hover:bg-white/15 transition-colors disabled:opacity-40"
          :disabled="previewImageScale <= 0.201"
          title="缩小（也可向下滚轮）"
          @click="zoomPreviewImageOut"
        >
          -
        </button>
        <button
          type="button"
          class="min-w-[56px] rounded-full px-2.5 py-1 text-[12px] tabular-nums hover:bg-white/15 transition-colors"
          title="重置缩放和旋转（也可双击图片）"
          @click="resetPreviewImageTransform"
        >
          {{ previewImageScaleText }}
        </button>
        <button
          type="button"
          class="rounded-full px-2.5 py-1 text-[13px] hover:bg-white/15 transition-colors disabled:opacity-40"
          :disabled="previewImageScale >= 7.999"
          title="放大（也可向上滚轮）"
          @click="zoomPreviewImageIn"
        >
          +
        </button>
        <div class="mx-1 h-5 w-px bg-white/20"></div>
        <button
          type="button"
          class="rounded-full p-1.5 hover:bg-white/15 transition-colors"
          title="逆时针旋转"
          @click="rotatePreviewImageLeft"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 7v6h6" />
            <path d="M5.6 13A7 7 0 1 0 8 5.1" />
          </svg>
        </button>
        <button
          type="button"
          class="rounded-full p-1.5 hover:bg-white/15 transition-colors"
          title="顺时针旋转"
          @click="rotatePreviewImageRight"
        >
          <svg class="w-4 h-4 scale-x-[-1]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 7v6h6" />
            <path d="M5.6 13A7 7 0 1 0 8 5.1" />
          </svg>
        </button>
      </div>

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

    <ChatHistoryFloatingWindows :state="state" />

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
                      v-if="rec.videoUrl"
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
                    :class="rec.emojiUrl ? 'cursor-pointer' : ''"
                    @click="rec.emojiUrl && openImagePreview(rec.emojiUrl)"
                    @contextmenu="openMediaContextMenu($event, rec, 'emoji')"
                  >
                    <img v-if="rec.emojiUrl" :src="rec.emojiUrl" alt="表情" class="w-24 h-24 object-contain hover:opacity-90 transition-opacity" />
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
    <ChatExportDialog v-if="exportModalOpen" :state="state" />
</template>

<script>
import { computed, defineComponent, ref, watch } from 'vue'
import ChatExportDialog from '~/components/chat/ChatExportDialog.vue'
import ChatHistoryFloatingWindows from '~/components/chat/ChatHistoryFloatingWindows.vue'

const PREVIEW_IMAGE_MIN_SCALE = 0.2
const PREVIEW_IMAGE_MAX_SCALE = 8
const PREVIEW_IMAGE_WHEEL_STEP = 1.12

const clampPreviewImageScale = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return 1
  return Math.min(PREVIEW_IMAGE_MAX_SCALE, Math.max(PREVIEW_IMAGE_MIN_SCALE, n))
}

const readMaybeRef = (value) => {
  if (value && typeof value === 'object' && 'value' in value) return value.value
  return value
}

export default defineComponent({
  name: 'ChatOverlays',
  components: { ChatExportDialog, ChatHistoryFloatingWindows },
  props: {
    state: { type: Object, required: true }
  },
  setup(props) {
    const previewImageScale = ref(1)
    const previewImageRotation = ref(0)

    const resetPreviewImageTransform = () => {
      previewImageScale.value = 1
      previewImageRotation.value = 0
    }

    const setPreviewImageScale = (value) => {
      previewImageScale.value = Number(clampPreviewImageScale(value).toFixed(3))
    }

    const zoomPreviewImageBy = (factor) => {
      setPreviewImageScale(previewImageScale.value * Number(factor || 1))
    }

    const zoomPreviewImageIn = () => {
      zoomPreviewImageBy(PREVIEW_IMAGE_WHEEL_STEP)
    }

    const zoomPreviewImageOut = () => {
      zoomPreviewImageBy(1 / PREVIEW_IMAGE_WHEEL_STEP)
    }

    const onPreviewImageWheel = (event) => {
      const deltaY = Number(event?.deltaY || 0)
      if (!deltaY) return

      const direction = deltaY < 0 ? 1 : -1
      const steps = Math.min(4, Math.max(1, Math.abs(deltaY) / 120))
      zoomPreviewImageBy(Math.pow(PREVIEW_IMAGE_WHEEL_STEP, direction * steps))
    }

    const rotatePreviewImageLeft = () => {
      previewImageRotation.value = (previewImageRotation.value - 90) % 360
    }

    const rotatePreviewImageRight = () => {
      previewImageRotation.value = (previewImageRotation.value + 90) % 360
    }

    const previewImageTransformStyle = computed(() => ({
      transform: `rotate(${previewImageRotation.value}deg) scale(${previewImageScale.value})`,
      transformOrigin: 'center center'
    }))

    const previewImageScaleText = computed(() => `${Math.round(previewImageScale.value * 100)}%`)

    watch(
      () => readMaybeRef(props.state.previewImageUrl),
      () => {
        resetPreviewImageTransform()
      }
    )

    return {
      ...props.state,
      previewImageScale,
      previewImageRotation,
      previewImageTransformStyle,
      previewImageScaleText,
      resetPreviewImageTransform,
      zoomPreviewImageIn,
      zoomPreviewImageOut,
      onPreviewImageWheel,
      rotatePreviewImageLeft,
      rotatePreviewImageRight,
    }
  }
})
</script>
