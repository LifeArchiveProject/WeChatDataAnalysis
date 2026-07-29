<template>
  <WrappedCardShell
    :card-id="card.id"
    :title="card.title"
    :narrative="''"
    :variant="variant"
    :wide="true"
    :dark="variant === 'slide'"
    tone="terminal"
    :active="isActive"
    :class="{ 'card-anim-paused': animPaused }"
  >
    <!-- 报头：航司铭牌 + 年报关键口径（HUD 碎片式元数据） -->
    <template #narrative>
      <div class="mt-2 tm-line">
        <span class="tm-brand avio-mono">
          <svg class="tm-plane" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" transform="rotate(90 12 12)"/></svg>
          WX AIR · {{ yearLabel }} 关系航线年报
        </span>
        <template v-if="replyEvents > 0">
          <span class="tm-dot" aria-hidden="true"></span>
          <span class="tm-item wrapped-number">开通航线 <b>{{ formatInt(sentToContacts) }}</b> 条</span>
          <span class="tm-dot" aria-hidden="true"></span>
          <span class="tm-item wrapped-number">全年回复 <b>{{ formatInt(replyEvents) }}</b> 次</span>
        </template>
      </div>
      <p class="mt-2 wrapped-body text-sm sm:text-base text-[#FFFFFF73]">
        秒回从来不是手速——是你把一个人，排在了所有事情前面。
      </p>
    </template>

    <!-- 无可统计数据/索引未就绪：航班信息未发布 -->
    <div v-if="replyEvents <= 0" class="text-sm text-[#FFFFFF73]">
      <div class="rounded-xl border border-white/10 bg-white/[0.06] p-4">
        <div class="wrapped-label text-xs text-[#FFFFFF59] avio-mono">NO INFORMATION · 航班信息暂未发布</div>
        <div class="mt-2 wrapped-body text-sm text-[#FFFFFF73] leading-relaxed">
          <p>本页需要使用“消息搜索索引”来合并所有消息分片并计算回复耗时。</p>
          <p v-if="indexBuild && indexBuild.status === 'building'" class="mt-2">
            索引正在构建中：已索引
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(indexBuild.indexedMessages) }}</span>
            条消息。
            <span v-if="indexBuild.currentConversation" class="text-[#FFFFFF4D]">（当前：{{ indexBuild.currentConversation }}）</span>
          </p>
          <ErrorNotice
            v-else-if="indexBuild && indexBuild.status === 'error'"
            :message="`索引构建失败：${indexBuild.error || '未知错误'}`"
            compact
            class="mt-2 text-red-600"
          />
          <p v-if="!usedIndex" class="mt-2">
            你可以先在「聊天记录搜索」中构建索引（或调用后端接口
            <code class="px-1 py-0.5 bg-white/10 rounded">/api/chat/search-index/build</code>），
            然后回到这里点击左上角“强制刷新”或本页“重试”。
          </p>
        </div>
      </div>
    </div>

    <!-- 航站楼主厅 -->
    <div v-else class="w-full">
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <!-- ─────────── 值机柜台 ─────────── -->
        <div
          class="ck-rail w-full lg:col-span-3 flex flex-col items-center transition-transform duration-500 will-change-transform"
          :class="[leftRailClass, leftDocked ? 'ck-rail--docked' : '']"
        >
          <template v-if="bestBuddy">
            <div class="ck-sign avio-mono">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M2.5 19h19v2h-19v-2zm19.57-9.36c-.21-.8-1.04-1.28-1.84-1.06L14.92 10 8.46 3.98l-1.93.51 3.87 6.7-4.95 1.33-1.84-1.45-1.45.39 1.82 3.16.77 1.33 1.6-.43 5.31-1.42 4.35-1.16L21 11.49c.81-.23 1.28-1.05 1.07-1.85z"/></svg>
              值机 CHECK-IN
            </div>

            <!-- 证件照格 -->
            <div
              class="ck-photo mt-4"
              :class="{ 'ck-photo--live': phase === 'rolling' }"
              :title="phase === 'rolling' ? '点击跳过' : ''"
              @click="skipLottery"
            >
              <span class="ck-photo-frame wrapped-privacy-avatar">
                <i class="grain" aria-hidden="true"></i>
                <img
                  v-if="shownAvatarUrl && shownAvatarOk && phase !== 'idle'"
                  :src="shownAvatarUrl"
                  class="w-full h-full object-cover"
                  alt="avatar"
                  @error="onShownAvatarError"
                />
                <svg v-else-if="phase === 'idle'" class="ck-photo-holder" viewBox="0 0 48 48" aria-hidden="true">
                  <circle cx="24" cy="18" r="8" fill="currentColor" />
                  <path d="M8 42c1.8-9 8.2-13 16-13s14.2 4 16 13" fill="currentColor" />
                </svg>
                <span v-else class="wrapped-number text-3xl text-[#FFFFFF66]">{{ shownAvatarFallback }}</span>
              </span>
              <i class="ck-tick ck-tick--tl" aria-hidden="true"></i>
              <i class="ck-tick ck-tick--tr" aria-hidden="true"></i>
              <i class="ck-tick ck-tick--bl" aria-hidden="true"></i>
              <i class="ck-tick ck-tick--br" aria-hidden="true"></i>
            </div>

            <!-- 翻牌机名牌（摇号本体） -->
            <div
              class="mt-4 flap-housing wrapped-privacy-name"
              :class="phase === 'rolling' ? 'cursor-pointer' : ''"
              :title="phase === 'rolling' ? '点击跳过' : (shownDisplayName || '')"
              @click="skipLottery"
            >
              <i class="grain" aria-hidden="true"></i>
              <SplitFlapRow
                :text="flapText"
                :cell-count="9"
                :spinning="phase === 'rolling'"
                :paused="animPaused"
                :reduced="reducedMotion"
                :flip-ms="300"
                :spin-ms="150"
                :stagger-ms="55"
                size="lg"
                @settled="onFlapSettled"
              />
            </div>

            <div class="mt-5">
              <button
                v-if="phase === 'idle'"
                type="button"
                class="ck-btn"
                @click="startLottery"
              >
                谁坐进了你的头等舱？
              </button>
              <button
                v-else-if="phase === 'rolling'"
                type="button"
                class="ck-btn ck-btn--rolling"
                @click="skipLottery"
              >
                摇号中…点击跳过
              </button>
              <button
                v-else
                type="button"
                class="ck-btn ck-btn--ghost"
                @click="restart"
              >
                再摇一次
              </button>
            </div>
          </template>

          <!-- 极端兜底：有回复数据但没有搭子对象 -->
          <div v-else class="ck-sign ck-sign--rest avio-mono">值机柜台休息中 · 本年度暂无头等舱旅客</div>
        </div>

        <!-- ─────────── 头等舱登机牌 ─────────── -->
        <div v-if="passPrinted && bestBuddy" class="w-full lg:col-start-4 lg:col-span-4 lg:self-center flex justify-center">
            <div class="pass-printer">
              <i class="pass-slot" aria-hidden="true"></i>
              <div
                ref="passEl"
                class="pass"
                :class="{ 'pass--live': passTilt.live, 'pass--reduced': reducedMotion }"
                :style="passStyle"
                @pointermove="onPassMove"
                @pointerleave="onPassLeave"
              >
                <div class="pass-head">
                  <span class="pass-airline avio-mono">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" transform="rotate(90 12 12)"/></svg>
                    <i class="pass-foil">WX AIR</i>
                  </span>
                  <span class="pass-class"><i class="pass-foil avio-mono">FIRST CLASS</i><em>头等舱</em></span>
                </div>

                <div class="pass-route">
                  <span class="pass-port">
                    <b class="pass-port-code">你</b>
                    <i class="pass-port-sub avio-mono">ME</i>
                  </span>
                  <span class="pass-path" aria-hidden="true">
                    <svg class="pass-path-plane" viewBox="0 0 24 24"><path fill="currentColor" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" transform="rotate(90 12 12)"/></svg>
                  </span>
                  <span class="pass-port pass-port--to">
                    <span class="pass-port-ava wrapped-privacy-avatar">
                      <img
                        v-if="bestBuddyAvatarUrl && avatarOk.best"
                        :src="bestBuddyAvatarUrl"
                        alt="avatar"
                        @error="avatarOk.best = false"
                      />
                      <span v-else class="wrapped-number">{{ avatarFallback(bestBuddy?.displayName) }}</span>
                    </span>
                    <b class="pass-port-name wrapped-privacy-name" :title="bestBuddy?.displayName">{{ bestBuddy?.displayName }}</b>
                    <i class="pass-port-sub avio-mono">置顶关心</i>
                  </span>
                </div>

                <div class="pass-grid">
                  <span class="pass-field">
                    <i class="avio-mono">航班 FLIGHT</i>
                    <b class="wrapped-number">WX-{{ flightNo }}</b>
                    <em>往返回复 {{ formatInt(buddyReplyCount) }} 次</em>
                  </span>
                  <span class="pass-field">
                    <i class="avio-mono">登机口 GATE</i>
                    <b class="wrapped-number">{{ bestBuddy?.peakHourLabel || '—' }}</b>
                    <em>最常聊天时段</em>
                  </span>
                  <span class="pass-field">
                    <i class="avio-mono">连续通航 STREAK</i>
                    <b class="wrapped-number">{{ buddyStreakDays != null ? `${formatInt(buddyStreakDays)} 天` : '—' }}</b>
                    <em>最长连聊不断更</em>
                  </span>
                  <span class="pass-field">
                    <i class="avio-mono">出港 SENT</i>
                    <b class="wrapped-number">{{ formatInt(bestBuddy?.outgoingMessages || 0) }}</b>
                    <em>你发出的消息</em>
                  </span>
                  <span class="pass-field">
                    <i class="avio-mono">进港 RCVD</i>
                    <b class="wrapped-number">{{ formatInt(bestBuddy?.incomingMessages || 0) }}</b>
                    <em>TA 发来的消息</em>
                  </span>
                  <span class="pass-field">
                    <i class="avio-mono">平均响应 AVG</i>
                    <b class="wrapped-number">{{ formatDuration(buddyAvgReplySeconds) }}</b>
                    <em>你回 TA 的平均用时</em>
                  </span>
                </div>

                <p v-if="buddyFastest != null || buddySlowest != null" class="pass-speedline wrapped-body">
                  <template v-if="buddyFastest != null">你回 TA 最快只要 <b class="wrapped-number">{{ formatDuration(buddyFastest) }}</b><template v-if="buddySlowest == null">。</template></template>
                  <template v-if="buddyFastest != null && buddySlowest != null">；</template>
                  <template v-if="buddySlowest != null">最慢的一次，等了 <b class="wrapped-number pass-slow">{{ formatDuration(buddySlowest) }}</b>。</template>
                </p>

                <div class="pass-stub">
                  <span class="pass-stub-codes avio-mono">
                    <i>ETKT {{ yearLabel }}·{{ flightNo }}</i>
                    <i>SEAT 1A 置顶 · 全年有效</i>
                  </span>
                  <svg class="pass-barcode" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                    <rect v-for="(b, i) in barcodeBars" :key="i" :x="b.x" y="0" :width="b.w" height="100" fill="currentColor" />
                  </svg>
                </div>

                <i class="pass-grain" aria-hidden="true"></i>
                <i class="pass-sheen" aria-hidden="true"></i>

                <span v-if="stamped" class="pass-stamp" aria-hidden="true">
                  <i>秒回认证</i>
                  <em class="avio-mono">PRIORITY CARE · WX AIR</em>
                </span>

                <span class="pass-glare" aria-hidden="true"></span>
              </div>
            </div>
        </div>

        <!-- ─────────── 出港大屏 ─────────── -->
        <Transition name="brd-fade">
          <div v-if="boardOn" class="brd w-full lg:col-start-8 lg:col-span-5" :class="{ 'brd--intro': boardIntro }">
            <i class="grain" aria-hidden="true"></i>
            <i class="brd-glass" aria-hidden="true"></i>
            <div class="brd-top">
              <div class="brd-title avio-mono">
                年度航线 · TOP ROUTES
                <span class="brd-title-sub">全年往来消息累计</span>
              </div>
              <button
                v-if="raceFinished && raceDays > 0 && !reducedMotion"
                type="button"
                class="brd-replay avio-mono"
                title="重播全年"
                @click="replayRace"
              >↻ 重播</button>
              <div
                class="brd-clock avio-mono"
                :class="{ 'brd-clock--live': racePlaying }"
                :title="racePlaying ? '点击直达年终' : ''"
                @click="skipRace"
              >
                <i v-if="racePlaying" class="brd-live" aria-hidden="true"></i>
                {{ boardDateLabel }}
              </div>
            </div>

            <div class="brd-cols avio-mono">
              <span>#</span>
              <span></span>
              <span>旅客 PASSENGER</span>
              <span class="brd-num-h">出港</span>
              <span class="brd-num-h">进港</span>
              <span class="brd-num-h brd-num-h--total">里程 TOTAL</span>
            </div>

            <div v-if="raceItems.length === 0" class="brd-empty wrapped-body">暂无可展示的航线数据。</div>

            <TransitionGroup v-else name="brd" tag="div" class="brd-body">
              <div
                v-for="(item, idx) in raceItems"
                :key="item.username"
                class="brd-row"
                :class="{ 'brd-row--first': item.rank === 1 }"
                :style="{ '--rd': `${idx * 45}ms` }"
              >
                <span class="brd-rank avio-mono">{{ pad2(item.rank) }}</span>
                <span class="brd-ava wrapped-privacy-avatar">
                  <img
                    v-if="item.avatarUrl && avatarOk[item.username] !== false"
                    :src="item.avatarUrl"
                    alt="avatar"
                    @error="avatarOk[item.username] = false"
                  />
                  <span v-else class="brd-ava-fb wrapped-number">{{ avatarFallback(item.displayName) }}</span>
                </span>
                <span class="brd-name wrapped-privacy-name" :title="item.displayName">{{ item.displayName }}</span>
                <span class="brd-num avio-mono">{{ formatInt(item.outV) }}</span>
                <span class="brd-num brd-num--in avio-mono">{{ formatInt(item.inV) }}</span>
                <span class="brd-total avio-mono">
                  <OdometerNumber :value="item.value" :max-value="item.finalTotal" />
                </span>
              </div>
            </TransitionGroup>

            <div class="brd-note avio-mono">
              <i class="brd-dot brd-dot--g" aria-hidden="true"></i>出港 = 你发
              <i class="brd-dot brd-dot--a" aria-hidden="true"></i>进港 = 对方发
              <span class="brd-note-right">里程 = 双向合计</span>
            </div>
          </div>
        </Transition>
      </div>

      <!-- ─────────── 夜间停机坪：对置端头 + 塔台日志 + 05L/05R 双跑道 ─────────── -->
      <div
        v-if="initiativeVisible || noticesAny"
        class="apron mt-4"
        :class="[initiativeEntered ? 'init-entered' : '', reducedMotion ? 'init-reduced' : '']"
      >
        <div class="apron-row">
          <!-- 出发端头：你先开口 -->
          <div v-if="initiativeVisible" class="apr-end apr-end--dep">
            <div class="apr-word">
              <svg class="apr-ic" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M2.5 19h19v2h-19v-2zm19.57-9.36c-.21-.8-1.04-1.28-1.84-1.06L14.92 10 8.46 3.98l-1.93.51 3.87 6.7-4.95 1.33-1.84-1.45-1.45.39 1.82 3.16.77 1.33 1.6-.43 5.31-1.42 4.35-1.16L21 11.49c.81-.23 1.28-1.05 1.07-1.85z"/></svg>
              出发 <i class="avio-mono">DEPARTURES</i>
            </div>
            <div class="apr-num avio-mono wrapped-number">{{ meBigDisplay }}</div>
            <div class="apr-sub avio-mono">你先开口的对话 · 班次</div>
            <div class="apr-chips">
              <span
                v-for="p in topInitiatedByMe"
                :key="`dm-${p.username}`"
                class="apr-chip"
                :title="`你主动找 ${p.displayName} 开了 ${formatInt(p.count)} 次头`"
              >
                <span class="apr-chip-ava wrapped-privacy-avatar">
                  <img
                    v-if="resolveMediaUrl(p.avatarUrl) && avatarOk[p.username] !== false"
                    :src="resolveMediaUrl(p.avatarUrl)"
                    alt="avatar"
                    @error="avatarOk[p.username] = false"
                  />
                  <span v-else class="apr-chip-fb wrapped-number">{{ avatarFallback(p.displayName) }}</span>
                </span>
                <span class="apr-chip-name wrapped-privacy-name">{{ p.displayName }}</span>
                <b class="wrapped-number">{{ formatInt(p.count) }}</b>
              </span>
            </div>
          </div>

          <!-- 塔台日志：无框分栏 -->
          <div v-if="noticesAny" class="apr-log">
            <div class="apr-log-head avio-mono">塔台日志 · TOWER LOG</div>
            <template v-if="phase === 'revealed'">
              <div v-if="fastestReplySeconds != null" class="ntc" style="--nd: 80ms">
                <span class="ntc-tag ntc-tag--ok avio-mono">准点 ON&nbsp;TIME</span>
                <span class="ntc-body wrapped-body">
                  最快出港纪录 <b class="wrapped-number text-[#3EE58A]">{{ formatDuration(fastestReplySeconds) }}</b>
                  <template v-if="fastestContact">
                    · 收件人
                    <span class="ntc-chip" :title="fastestContact.displayName">
                      <span class="ntc-chip-ava wrapped-privacy-avatar">
                        <img
                          v-if="resolveMediaUrl(fastestContact.avatarUrl) && avatarOk[fastestContact.username] !== false"
                          :src="resolveMediaUrl(fastestContact.avatarUrl)"
                          alt="avatar"
                          @error="avatarOk[fastestContact.username] = false"
                        />
                        <span v-else class="wrapped-number">{{ avatarFallback(fastestContact.displayName) }}</span>
                      </span>
                      <b class="wrapped-privacy-name">{{ fastestContact.displayName }}</b>
                    </span>
                  </template>
                </span>
              </div>

              <div v-if="longestReplySeconds != null" class="ntc" style="--nd: 220ms">
                <span class="ntc-tag ntc-tag--delay avio-mono">延误 DELAYED</span>
                <span class="ntc-body wrapped-body">
                  最长延误 <b class="wrapped-number text-[#E8B54A]">{{ formatDuration(longestReplySeconds) }}</b>
                  · 让
                  <template v-if="slowestContact">
                    <span class="ntc-chip" :title="slowestContact.displayName">
                      <span class="ntc-chip-ava wrapped-privacy-avatar">
                        <img
                          v-if="resolveMediaUrl(slowestContact.avatarUrl) && avatarOk[slowestContact.username] !== false"
                          :src="resolveMediaUrl(slowestContact.avatarUrl)"
                          alt="avatar"
                          @error="avatarOk[slowestContact.username] = false"
                        />
                        <span v-else class="wrapped-number">{{ avatarFallback(slowestContact.displayName) }}</span>
                      </span>
                      <b class="wrapped-privacy-name">{{ slowestContact.displayName }}</b>
                    </span>
                  </template>
                  <template v-else>对方</template>
                  久等了<span class="ntc-soft">——好在 TA 没有取消这段行程</span>
                </span>
              </div>

              <div v-if="mutualFriend" class="ntc" style="--nd: 360ms">
                <span class="ntc-tag ntc-tag--duo avio-mono">对开 MUTUAL</span>
                <span class="ntc-body wrapped-body">
                  与
                  <span class="ntc-chip" :title="mutualFriend.displayName">
                    <span class="ntc-chip-ava wrapped-privacy-avatar">
                      <img
                        v-if="resolveMediaUrl(mutualFriend.avatarUrl) && avatarOk[mutualFriend.username] !== false"
                        :src="resolveMediaUrl(mutualFriend.avatarUrl)"
                        alt="avatar"
                        @error="avatarOk[mutualFriend.username] = false"
                      />
                      <span v-else class="wrapped-number">{{ avatarFallback(mutualFriend.displayName) }}</span>
                    </span>
                    <b class="wrapped-privacy-name">{{ mutualFriend.displayName }}</b>
                  </span>
                  对开 <b class="wrapped-number text-[#3EE58A]">{{ mutualSentDisplay }}</b>
                  <i class="ntc-swap avio-mono">⇌</i>
                  <b class="wrapped-number text-[#E8B54A]">{{ mutualRecvDisplay }}</b>
                  · 往来比 {{ mutualRatioText }} · 谁也没让谁多等
                </span>
              </div>
            </template>

            <div v-else class="ntc ntc-pending avio-mono">
              值机完成后开始记录<span class="ntc-caret"></span>
            </div>
          </div>

          <!-- 到达端头：TA 先开口 -->
          <div v-if="initiativeVisible" class="apr-end apr-end--arr">
            <div class="apr-word">
              <i class="avio-mono">ARRIVALS</i> 到达
              <svg class="apr-ic" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M2.5 19h19v2h-19v-2zm7.18-5.73l4.35 1.16 5.31 1.42c.8.21 1.62-.26 1.84-1.06.21-.8-.26-1.62-1.06-1.84l-5.31-1.42-2.76-9.02L10.12 2v8.28L5.15 8.95l-.93-2.32-1.45-.39v5.17l1.6.43 5.31 1.42z"/></svg>
            </div>
            <div class="apr-num avio-mono wrapped-number">{{ themBigDisplay }}</div>
            <div class="apr-sub avio-mono">TA 先来找你的对话 · 班次</div>
            <div class="apr-chips">
              <span
                v-for="p in topInitiatedToMe"
                :key="`da-${p.username}`"
                class="apr-chip"
                :title="`${p.displayName} 主动来找你 ${formatInt(p.count)} 次`"
              >
                <span class="apr-chip-ava wrapped-privacy-avatar">
                  <img
                    v-if="resolveMediaUrl(p.avatarUrl) && avatarOk[p.username] !== false"
                    :src="resolveMediaUrl(p.avatarUrl)"
                    alt="avatar"
                    @error="avatarOk[p.username] = false"
                  />
                  <span v-else class="apr-chip-fb wrapped-number">{{ avatarFallback(p.displayName) }}</span>
                </span>
                <span class="apr-chip-name wrapped-privacy-name">{{ p.displayName }}</span>
                <b class="wrapped-number">{{ formatInt(p.count) }}</b>
              </span>
            </div>
          </div>
        </div>

        <!-- RWY 05L · 谁先开口 -->
        <div v-if="initiativeVisible" class="rwy rwy--init">
          <div class="rwy-meta avio-mono">
            <b class="rwy-id">RWY 05L</b>
            <span class="rwy-name">谁先开口</span>
            <span class="rwy-cap wrapped-body">
              全年 <b class="wrapped-number">{{ convDisplay }}</b> 班对话 ·
              <b class="wrapped-number rwy-g">{{ rateDisplay }}%</b> 由你先开口
            </span>
          </div>
          <div class="rwy-strip" aria-hidden="true">
            <i class="grain" aria-hidden="true"></i>
            <i class="rwy-edge rwy-edge--t"></i>
            <i class="rwy-edge rwy-edge--b"></i>
            <i class="gauge-lamps gauge-lamps--glow"></i>
            <i class="gauge-lamps"></i>
            <span class="gauge-lights" :style="{ width: `${gaugePct}%` }">
              <i class="gauge-lamps gauge-lamps--me gauge-lamps--glow"></i>
              <i class="gauge-lamps gauge-lamps--me"></i>
            </span>
            <i class="gauge-beacon" :style="{ left: `${gaugePct}%` }"></i>
          </div>
        </div>

        <!-- RWY 05R · 回复速度（值机后亮灯） -->
        <div
          v-if="phase === 'revealed' && replyStatsData"
          class="rwy rwy--speed"
          :class="{ 'rw-on': runwayOn, 'rw-reduced': reducedMotion }"
        >
          <div class="rwy-meta avio-mono">
            <b class="rwy-id">RWY 05R</b>
            <span class="rwy-name">回复速度</span>
            <span class="rwy-cap wrapped-body">
              你一半的回复 <b class="wrapped-number rwy-g">{{ formatDuration(replyStatsData.p50) }}</b> 内离港 ·
              90% 不超过 <b class="wrapped-number rwy-a">{{ formatDuration(replyStatsData.p90) }}</b>
            </span>
          </div>
          <div class="rwy-strip rwy-strip--speed">
            <i class="grain" aria-hidden="true"></i>
            <i class="rwy-edge rwy-edge--t"></i>
            <i class="rwy-edge rwy-edge--b"></i>
            <i class="rw-threshold" aria-hidden="true"></i>
            <i class="rw-center" aria-hidden="true"></i>
            <span class="rw-marker rw-marker--p50" :style="{ left: `${p50MarkerPct}%` }">
              <svg class="rw-plane" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" transform="rotate(90 12 12)"/></svg>
              <em class="avio-mono">P50</em>
            </span>
            <span class="rw-marker rw-marker--p90" :style="{ left: '94%' }">
              <i class="rw-tick" aria-hidden="true"></i>
              <em class="avio-mono">P90</em>
            </span>
          </div>
        </div>
      </div>

      <p class="closer wrapped-body">—— 所有航线的终点，都是有人在等你 ——</p>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue'
import { gsap } from 'gsap'
import { useCountUp } from '~/composables/useCountUp'
import { useReducedMotion } from '~/composables/useReducedMotion'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  isActive: { type: Boolean, default: true }
})

const reducedMotion = useReducedMotion()

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))
const pad2 = (n) => String(n).padStart(2, '0')

// ---------------- Data (from backend) ----------------
const yearLabel = computed(() => Number(props.card?.data?.year || new Date().getFullYear()))
const replyEvents = computed(() => Number(props.card?.data?.replyEvents || 0))
const fastestReplySeconds = computed(() => props.card?.data?.fastestReplySeconds ?? null)
const longestReplySeconds = computed(() => props.card?.data?.longestReplySeconds ?? null)
const sentToContacts = computed(() => Number(props.card?.data?.sentToContacts || 0))

const bestBuddy = computed(() => {
  const o = props.card?.data?.bestBuddy
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const fastestContact = computed(() => {
  const o = props.card?.data?.fastest
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const slowestContact = computed(() => {
  const o = props.card?.data?.slowest
  return o && typeof o === 'object' && typeof o.displayName === 'string' ? o : null
})

const usedIndex = computed(() => !!props.card?.data?.settings?.usedIndex)
const indexBuild = computed(() => {
  const st = props.card?.data?.settings?.indexStatus
  const b = st?.index?.build
  if (!b || typeof b !== 'object') return null
  return {
    status: String(b.status || ''),
    indexedMessages: Number(b.indexedMessages || 0),
    currentConversation: String(b.currentConversation || ''),
    error: String(b.error || '')
  }
})

// 登机牌字段
const buddyReplyCount = computed(() => Number(bestBuddy.value?.replyCount || 0))
const flightNo = computed(() => String(Math.max(0, buddyReplyCount.value)).padStart(4, '0'))
const buddyAvgReplySeconds = computed(() => Math.round(Number(bestBuddy.value?.avgReplySeconds || 0)))
const buddyStreakDays = computed(() => {
  const v = Number(bestBuddy.value?.longestStreakDays)
  return Number.isFinite(v) && v > 0 ? v : null
})
const buddyFastest = computed(() => bestBuddy.value?.fastestReplySeconds ?? null)
const buddySlowest = computed(() => bestBuddy.value?.slowestReplySeconds ?? null)

const noticesAny = computed(() => (
  fastestReplySeconds.value != null || longestReplySeconds.value != null || !!mutualFriend.value
))

// 跑道：P50/P90 全局回复速度
const replyStatsData = computed(() => {
  const o = props.card?.data?.replyStats
  if (!o || typeof o !== 'object') return null
  const p50 = Number(o.p50Seconds)
  const p90 = Number(o.p90Seconds)
  if (!Number.isFinite(p50) || !Number.isFinite(p90) || p90 <= 0) return null
  return { p50: Math.max(0, p50), p90 }
})

const p50MarkerPct = computed(() => {
  const d = replyStatsData.value
  if (!d) return 0
  return Math.max(10, Math.min(78, (d.p50 / d.p90) * 94))
})

// ---------------- Media URL resolving ----------------
const apiBase = useApiBase()
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
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

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  return s ? s[0] : '?'
}

const avatarOk = reactive({ best: true })
const bestBuddyAvatarUrl = computed(() => resolveMediaUrl(bestBuddy.value?.avatarUrl))
watch(bestBuddyAvatarUrl, () => { avatarOk.best = true })

const resetAvatarOk = () => {
  for (const k of Object.keys(avatarOk)) delete avatarOk[k]
  avatarOk.best = true
}

const formatDuration = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  if (!Number.isFinite(s) || s <= 0) return '不到1秒'
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  const ss = s % 60
  if (m < 60) return ss ? `${m}分${ss}秒` : `${m}分钟`
  const h = Math.floor(m / 60)
  const mm = m % 60
  if (h < 24) return mm ? `${h}小时${mm}分钟` : `${h}小时`
  const d = Math.floor(h / 24)
  const hh = h % 24
  return hh ? `${d}天${hh}小时` : `${d}天`
}

// ---------------- 卡片激活/暂停（deck 翻页） ----------------
const animPaused = ref(false)
const hasEntered = ref(false)

// ---------------- 值机摇号（7s, ease-out slowdown） ----------------
const phase = ref('idle') // idle | rolling | revealed
const shownUser = ref(null)
const shownAvatarOk = ref(true)
const leftDocked = ref(false)
const boardOn = ref(false)
const boardIntro = ref(true)
const passPrinted = ref(false)
const stamped = ref(false)
const runwayOn = ref(false)

let lotteryTimer = null
let dockTimer = null
let printTimer = null
let stampTimer = null
let runwayTimer = null
let chartTimer = null
let raceStartTimer = null

const lotteryDurationMs = 7000
let lotteryStartedAt = 0
let lotteryPausedAt = null
let lotterySnapping = false
// 翻板落定后才继续揭晓编排；只消费一次
let pendingRevealSequence = false

const candidates = computed(() => {
  const allContacts = Array.isArray(props.card?.data?.allContacts) ? props.card.data.allContacts : []
  const topTotals = Array.isArray(props.card?.data?.topTotals) ? props.card.data.topTotals : []
  const seen = new Set()
  const out = []
  for (const x of [...allContacts, ...topTotals]) {
    if (x && typeof x === 'object' && typeof x.displayName === 'string' && !seen.has(x.username)) {
      seen.add(x.username)
      out.push(x)
    }
  }
  if (bestBuddy.value && !seen.has(bestBuddy.value.username)) {
    out.unshift(bestBuddy.value)
  }
  return out
})

const shownDisplayName = computed(() => {
  const o = shownUser.value
  const name = String(o?.displayName || o?.maskedName || '').trim()
  return name || ''
})

const flapText = computed(() => {
  if (phase.value === 'idle') return '？？？'
  return shownDisplayName.value || '…'
})

const shownAvatarUrl = computed(() => {
  const o = shownUser.value
  if (!o) return ''
  return resolveMediaUrl(o.avatarUrl)
})

const shownAvatarFallback = computed(() => avatarFallback(shownDisplayName.value))
const onShownAvatarError = () => { shownAvatarOk.value = false }

const pickRandomCandidate = (prevUsername) => {
  const pool = candidates.value
  if (!Array.isArray(pool) || pool.length === 0) return bestBuddy.value || null
  if (pool.length === 1) return pool[0]
  for (let i = 0; i < 6; i += 1) {
    const idx = Math.floor(Math.random() * pool.length)
    const c = pool[idx]
    if (c && c.username !== prevUsername) return c
  }
  return pool[Math.floor(Math.random() * pool.length)]
}

const clearTimers = () => {
  if (lotteryTimer) clearTimeout(lotteryTimer)
  lotteryTimer = null
  if (dockTimer) clearTimeout(dockTimer)
  dockTimer = null
  if (printTimer) clearTimeout(printTimer)
  printTimer = null
  if (stampTimer) clearTimeout(stampTimer)
  stampTimer = null
  if (runwayTimer) clearTimeout(runwayTimer)
  runwayTimer = null
  if (chartTimer) clearTimeout(chartTimer)
  chartTimer = null
  if (raceStartTimer) clearTimeout(raceStartTimer)
  raceStartTimer = null
  lotteryPausedAt = null
}

const leftRailClass = computed(() => {
  const shouldCenter = phase.value !== 'revealed' || !leftDocked.value
  return [
    'ease-[cubic-bezier(0.22,1,0.36,1)]',
    // 值机台占 12 栏中的 3 栏：右移 150% 自宽 ≈ 行中央；揭晓后归位左侧
    shouldCenter ? 'lg:translate-x-[150%]' : ''
  ]
})

const lotteryTick = () => {
  const now = performance.now()
  const elapsed = now - lotteryStartedAt
  const t = Math.max(0, Math.min(1, elapsed / lotteryDurationMs))

  const prev = String(shownUser.value?.username || '')
  let next = pickRandomCandidate(prev)
  const target = bestBuddy.value
  if (target && typeof target === 'object') {
    if (t >= 0.97) {
      next = target
    } else if (t >= 0.85) {
      const p = Math.max(0, Math.min(1, (t - 0.85) / 0.12))
      if (Math.random() < p) next = target
    }
  }
  shownUser.value = next
  shownAvatarOk.value = true

  if (t >= 1) {
    finishReveal()
    return
  }

  const minDelay = 90
  const maxDelay = 260
  const easeOutCubic = 1 - Math.pow(1 - t, 3)
  const delay = Math.round(minDelay + (maxDelay - minDelay) * easeOutCubic)
  lotteryTimer = setTimeout(lotteryTick, delay)
}

const resetRevealState = () => {
  leftDocked.value = false
  boardOn.value = false
  boardIntro.value = true
  passPrinted.value = false
  stamped.value = false
  runwayOn.value = false
  pendingRevealSequence = false
  passTilt.rx = 0
  passTilt.ry = 0
  passTilt.live = false
}

const startLottery = () => {
  clearTimers()
  resetAvatarOk()
  shownAvatarOk.value = true
  resetRevealState()
  lotterySnapping = false

  phase.value = 'rolling'
  raceReset()

  if (reducedMotion.value) {
    finishReveal()
    return
  }

  lotteryStartedAt = performance.now()
  lotteryTick()
}

const skipLottery = () => {
  if (phase.value !== 'rolling' || lotterySnapping) return
  if (lotteryTimer) { clearTimeout(lotteryTimer); lotteryTimer = null }
  lotterySnapping = true

  const target = bestBuddy.value
  let hop = 0
  const snap = () => {
    hop += 1
    if (hop >= 4) {
      finishReveal()
      return
    }
    const next = hop === 3 && target ? target : pickRandomCandidate(String(shownUser.value?.username || ''))
    if (next) {
      shownUser.value = next
      shownAvatarOk.value = true
    }
    lotteryTimer = setTimeout(snap, 220)
  }
  snap()
}

const finishReveal = () => {
  clearTimers()
  lotterySnapping = false
  phase.value = 'revealed'
  shownUser.value = bestBuddy.value || shownUser.value
  shownAvatarOk.value = true

  if (reducedMotion.value) {
    leftDocked.value = true
    passPrinted.value = true
    stamped.value = true
    runwayOn.value = true
    boardOn.value = true
    boardIntro.value = false
    startRace()
    return
  }

  // 等翻板逐格落定（SplitFlapRow emit settled）再继续编排
  pendingRevealSequence = true
}

// 翻板落定：靠泊左侧 → 打印登机牌 → 盖章 → 大屏上电 → 年度回放 → 跑道
const onFlapSettled = () => {
  if (!pendingRevealSequence) return
  pendingRevealSequence = false

  leftDocked.value = true
  printTimer = setTimeout(() => { passPrinted.value = true }, 160)
  chartTimer = setTimeout(() => { boardOn.value = true }, 520)
  stampTimer = setTimeout(() => { stamped.value = true }, 1150)
  raceStartTimer = setTimeout(() => {
    boardIntro.value = false
    startRace()
  }, 1250)
  runwayTimer = setTimeout(() => { runwayOn.value = true }, 1400)
}

const restart = () => {
  startLottery()
}

// ---------------- 登机牌 3D 倾斜 + 流光 ----------------
const passEl = ref(null)
const passTilt = reactive({ rx: 0, ry: 0, gx: 50, gy: 26, live: false })

const onPassMove = (e) => {
  if (reducedMotion.value) return
  const el = passEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const px = (e.clientX - rect.left) / rect.width - 0.5
  const py = (e.clientY - rect.top) / rect.height - 0.5
  passTilt.live = true
  passTilt.rx = (-py * 8).toFixed(2)
  passTilt.ry = (px * 10).toFixed(2)
  passTilt.gx = Math.round((px + 0.5) * 100)
  passTilt.gy = Math.round((py + 0.5) * 100)
}

const onPassLeave = () => {
  passTilt.live = false
  passTilt.rx = 0
  passTilt.ry = 0
  passTilt.gx = 50
  passTilt.gy = 26
}

const passStyle = computed(() => ({
  transform: `perspective(1100px) rotateX(${passTilt.rx}deg) rotateY(${passTilt.ry}deg)`,
  '--gx': `${passTilt.gx}%`,
  '--gy': `${passTilt.gy}%`
}))

// 条码：按 username+year 播种的伪随机竖条，纯装饰
const barcodeBars = computed(() => {
  const seedStr = `${String(bestBuddy.value?.username || 'wx')}-${yearLabel.value}`
  let h = 2166136261
  for (let i = 0; i < seedStr.length; i += 1) {
    h ^= seedStr.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  const rnd = () => {
    h ^= h << 13; h ^= h >>> 17; h ^= h << 5
    return ((h >>> 0) % 1000) / 1000
  }
  const bars = []
  let x = 0
  while (x < 98 && bars.length < 64) {
    const w = 0.7 + rnd() * 2.4
    bars.push({ x: Number(x.toFixed(2)), w: Number(w.toFixed(2)) })
    x += w + 0.5 + rnd() * 1.7
  }
  return bars
})

// ---------------- 出港大屏（gsap.ticker 按 elapsed 插值） ----------------
const MS_PER_DAY = 100

const race = computed(() => props.card?.data?.race || null)
const raceDays = computed(() => Math.max(0, Number(race.value?.days || 0)))
const raceSeriesRaw = computed(() => (Array.isArray(race.value?.series) ? race.value.series : []))
const topTotalsByUsername = computed(() => {
  const out = new Map()
  const arr = Array.isArray(props.card?.data?.topTotals) ? props.card.data.topTotals : []
  for (const x of arr) {
    if (!x || typeof x !== 'object') continue
    const username = String(x.username || '').trim()
    if (!username) continue
    out.set(username, {
      outgoingMessages: Math.max(0, Number(x.outgoingMessages || 0)),
      incomingMessages: Math.max(0, Number(x.incomingMessages || 0))
    })
  }
  return out
})

const raceSeries = computed(() => {
  const totalsByUsername = topTotalsByUsername.value
  return raceSeriesRaw.value
    .filter((x) => x && typeof x === 'object' && typeof x.username === 'string')
    .map((x) => {
      const username = String(x.username || '')
      const fallback = totalsByUsername.get(username)
      const outgoingMessages = Math.max(0, Number(x.outgoingMessages ?? fallback?.outgoingMessages ?? 0))
      const incomingMessages = Math.max(0, Number(x.incomingMessages ?? fallback?.incomingMessages ?? 0))

      let cumulativeCounts = Array.isArray(x.cumulativeCounts) ? x.cumulativeCounts.map((v) => Math.max(0, Number(v) || 0)) : []
      let cumulativeOutgoingCounts = Array.isArray(x.cumulativeOutgoingCounts) ? x.cumulativeOutgoingCounts.map((v) => Math.max(0, Number(v) || 0)) : []
      let cumulativeIncomingCounts = Array.isArray(x.cumulativeIncomingCounts) ? x.cumulativeIncomingCounts.map((v) => Math.max(0, Number(v) || 0)) : []

      if (cumulativeCounts.length === 0 && (cumulativeOutgoingCounts.length > 0 || cumulativeIncomingCounts.length > 0)) {
        const len = Math.max(cumulativeOutgoingCounts.length, cumulativeIncomingCounts.length)
        cumulativeCounts = Array.from({ length: len }, (_, i) => (
          Number(cumulativeOutgoingCounts[i] || 0) + Number(cumulativeIncomingCounts[i] || 0)
        ))
      }

      // 老缓存兼容：只有总曲线时按终值比例拆出出/进两条
      if (cumulativeCounts.length > 0 && (cumulativeOutgoingCounts.length === 0 || cumulativeIncomingCounts.length === 0)) {
        const splitBase = outgoingMessages + incomingMessages
        const outgoingRatio = splitBase > 0 ? outgoingMessages / splitBase : 0
        cumulativeOutgoingCounts = cumulativeCounts.map((v) => Math.max(0, Math.round((Number(v) || 0) * outgoingRatio)))
        cumulativeIncomingCounts = cumulativeCounts.map((v, i) => (
          Math.max(0, (Number(v) || 0) - Number(cumulativeOutgoingCounts[i] || 0))
        ))
      }

      const finalTotal = cumulativeCounts.length > 0
        ? cumulativeCounts[cumulativeCounts.length - 1]
        : outgoingMessages + incomingMessages

      return {
        username,
        displayName: String(x.displayName || x.maskedName || ''),
        avatarUrl: resolveMediaUrl(x.avatarUrl),
        cumulativeCounts,
        cumulativeOutgoingCounts,
        cumulativeIncomingCounts,
        finalTotal: Math.max(1, finalTotal)
      }
    })
})

// 无回放曲线时的静态终榜（topTotals 兜底）
const staticBoardItems = computed(() => {
  const arr = Array.isArray(props.card?.data?.topTotals) ? props.card.data.topTotals : []
  return arr
    .filter((x) => x && typeof x === 'object' && typeof x.username === 'string')
    .map((x) => {
      const outV = Math.max(0, Number(x.outgoingMessages || 0))
      const inV = Math.max(0, Number(x.incomingMessages || 0))
      const total = Math.max(0, Number(x.totalMessages || outV + inV))
      return {
        username: String(x.username || ''),
        displayName: String(x.displayName || x.maskedName || ''),
        avatarUrl: resolveMediaUrl(x.avatarUrl),
        value: total,
        outV,
        inV,
        finalTotal: Math.max(1, total)
      }
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
    .map((x, i) => ({ ...x, rank: i + 1 }))
})

const racePlaying = ref(false)
const raceSpeed = ref(1)
const raceStarted = ref(false)
const raceDay = ref(0)
const raceItems = shallowRef([])

let raceElapsedMs = 0
let raceLastTickAt = 0
let raceTickerOn = false
let raceOrder = null

const raceFinished = computed(() => raceStarted.value && (raceDays.value <= 0 || raceDay.value >= raceDays.value))

const raceDate = computed(() => {
  const y = yearLabel.value
  const step = Math.max(0, Math.min(Math.max(0, raceDays.value), Number(raceDay.value || 0)))
  if (step <= 0) return `${y}-01-01`
  const d = Math.max(0, Math.min(Math.max(0, raceDays.value - 1), step - 1))
  const dt = new Date(y, 0, 1 + d)
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`
})

const boardDateLabel = computed(() => {
  if (raceDays.value <= 0 || raceSeries.value.length === 0) return `${yearLabel.value} · 年终榜`
  if (raceFinished.value) return `${yearLabel.value} · 年终榜`
  if (!raceStarted.value || (!racePlaying.value && raceDay.value <= 0)) return `${yearLabel.value} · 年终榜`
  return raceDate.value
})

const raceValueAt = (arr, step) => {
  if (step <= 0 || !Array.isArray(arr) || arr.length === 0) return 0
  return Math.max(0, Number(arr[Math.min(step, arr.length) - 1] || 0))
}

const updateRaceFrame = (step) => {
  const list = raceSeries.value
  const n = list.length
  if (!n) {
    raceItems.value = staticBoardItems.value
    return
  }

  const values = new Array(n)
  for (let i = 0; i < n; i += 1) values[i] = raceValueAt(list[i].cumulativeCounts, step)

  const sortOrder = () => {
    raceOrder.sort((a, b) => (
      (values[b] - values[a]) || String(list[a].username).localeCompare(String(list[b].username))
    ))
  }

  if (!raceOrder || raceOrder.length !== n) {
    raceOrder = Array.from({ length: n }, (_, i) => i)
    sortOrder()
  } else {
    let ordered = true
    for (let i = 1; i < n; i += 1) {
      if (values[raceOrder[i - 1]] < values[raceOrder[i]]) { ordered = false; break }
    }
    if (!ordered) sortOrder()
  }

  const items = []
  for (let k = 0; k < raceOrder.length && items.length < 10; k += 1) {
    const i = raceOrder[k]
    const value = values[i]
    if (value <= 0) break
    const s = list[i]

    let outgoingV = raceValueAt(s.cumulativeOutgoingCounts, step)
    let incomingV = raceValueAt(s.cumulativeIncomingCounts, step)
    let splitTotal = outgoingV + incomingV
    if (splitTotal <= 0) {
      incomingV = value
      splitTotal = value
    } else if (splitTotal !== value) {
      const scale = value / splitTotal
      outgoingV = Math.max(0, Math.round(outgoingV * scale))
      incomingV = Math.max(0, value - outgoingV)
    }

    items.push({
      username: s.username,
      displayName: s.displayName,
      avatarUrl: s.avatarUrl,
      rank: items.length + 1,
      value,
      outV: outgoingV,
      inV: incomingV,
      finalTotal: s.finalTotal
    })
  }

  raceItems.value = items
}

const setRaceStep = (step) => {
  const s = Math.max(0, Math.min(raceDays.value, Math.round(Number(step) || 0)))
  raceDay.value = s
  updateRaceFrame(s)
}

const raceTick = () => {
  if (!racePlaying.value) return
  const now = performance.now()
  const delta = Math.max(0, now - raceLastTickAt)
  raceLastTickAt = now
  raceElapsedMs += delta * raceSpeed.value

  const step = Math.min(raceDays.value, Math.floor(raceElapsedMs / MS_PER_DAY))
  if (step !== raceDay.value) setRaceStep(step)
  if (step >= raceDays.value) {
    racePlaying.value = false
    stopRaceTicker()
  }
}

const startRaceTicker = () => {
  if (raceTickerOn) return
  raceLastTickAt = performance.now()
  gsap.ticker.add(raceTick)
  raceTickerOn = true
}

const stopRaceTicker = () => {
  if (!raceTickerOn) return
  gsap.ticker.remove(raceTick)
  raceTickerOn = false
}

const raceReset = () => {
  stopRaceTicker()
  racePlaying.value = false
  raceStarted.value = false
  raceSpeed.value = 1
  raceElapsedMs = 0
  raceOrder = null
  raceDay.value = 0
  raceItems.value = []
}

const startRace = () => {
  stopRaceTicker()
  raceStarted.value = true
  raceOrder = null
  raceElapsedMs = 0

  if (raceDays.value <= 0 || raceSeries.value.length === 0) {
    // 没有逐日曲线：直接亮年终榜
    racePlaying.value = false
    raceItems.value = staticBoardItems.value
    return
  }

  if (reducedMotion.value) {
    racePlaying.value = false
    setRaceStep(raceDays.value)
    return
  }

  setRaceStep(0)
  racePlaying.value = true
  if (props.isActive) startRaceTicker()
}

const replayRace = () => {
  if (raceDays.value <= 0 || raceSeries.value.length === 0) return
  startRace()
}

const skipRace = () => {
  if (!racePlaying.value) return
  racePlaying.value = false
  stopRaceTicker()
  setRaceStep(raceDays.value)
}

// 大屏上电前先亮出年终榜，回放时再从 0 起跑
watch(boardOn, (on) => {
  if (!on) return
  if (!raceStarted.value) {
    if (raceSeries.value.length > 0 && raceDays.value > 0) {
      raceOrder = null
      setRaceStep(raceDays.value)
    } else {
      raceItems.value = staticBoardItems.value
    }
  }
})

// ---------------- 航站公告带（出发/到达）入场 ----------------
const initiative = computed(() => {
  const o = props.card?.data?.initiative
  return o && typeof o === 'object' ? o : null
})
const initiativeVisible = computed(() => !!initiative.value && Number(initiative.value.conversationCount || 0) > 0)
const initiativeRate = computed(() => {
  const v = Number(initiative.value?.initiationRatePct)
  return Number.isFinite(v) ? v : null
})
const topInitiatedByMe = computed(() => (
  Array.isArray(initiative.value?.topInitiatedByMe)
    ? initiative.value.topInitiatedByMe.filter((x) => x && typeof x === 'object' && x.username).slice(0, 3)
    : []
))
const topInitiatedToMe = computed(() => (
  Array.isArray(initiative.value?.topInitiatedToMe)
    ? initiative.value.topInitiatedToMe.filter((x) => x && typeof x === 'object' && x.username).slice(0, 3)
    : []
))
const mutualFriend = computed(() => {
  const o = initiative.value?.mutualFriend
  return o && typeof o === 'object' && typeof o.username === 'string' ? o : null
})
const mutualRatioText = computed(() => {
  const r = Number(mutualFriend.value?.ratio)
  return Number.isFinite(r) ? r.toFixed(2) : ''
})

const gaugePct = computed(() => {
  const v = Number(initiativeRate.value)
  const pct = Number.isFinite(v) ? v : 50
  return Math.max(4, Math.min(96, pct))
})

const initiativeEntered = ref(false)

const { display: rateDisplay, restart: playRateCount } = useCountUp(
  () => Number(initiativeRate.value ?? 0),
  { duration: 1.4, decimals: 1 }
)
const { display: convDisplay, restart: playConvCount } = useCountUp(
  () => Number(initiative.value?.conversationCount || 0),
  { duration: 1.2 }
)
const { display: meBigDisplay, restart: playMeBig } = useCountUp(
  () => Number(initiative.value?.initiatedByMe || 0),
  { duration: 1.3, delay: 0.3 }
)
const { display: themBigDisplay, restart: playThemBig } = useCountUp(
  () => Number(initiative.value?.initiatedByOthers || 0),
  { duration: 1.3, delay: 0.3 }
)
const { display: mutualSentDisplay, restart: playMutualSent } = useCountUp(
  () => Number(mutualFriend.value?.sentCount || 0),
  { duration: 1.4, delay: 0.3 }
)
const { display: mutualRecvDisplay, restart: playMutualRecv } = useCountUp(
  () => Number(mutualFriend.value?.receivedCount || 0),
  { duration: 1.4, delay: 0.3 }
)

const playInitiativeIntro = () => {
  initiativeEntered.value = true
  playRateCount()
  playConvCount()
  playMeBig()
  playThemBig()
  playMutualSent()
  playMutualRecv()
}

// ---------------- 激活/暂停编排 ----------------
const pauseCardLoops = () => {
  animPaused.value = true
  if (phase.value === 'rolling' && lotteryPausedAt == null) {
    if (lotteryTimer) { clearTimeout(lotteryTimer); lotteryTimer = null }
    lotteryPausedAt = performance.now()
  }
  stopRaceTicker()
}

const resumeCardLoops = () => {
  animPaused.value = false
  if (phase.value === 'rolling' && lotteryPausedAt != null) {
    const pausedFor = performance.now() - lotteryPausedAt
    lotteryPausedAt = null
    if (lotterySnapping) {
      finishReveal()
    } else {
      lotteryStartedAt += pausedFor
      lotteryTick()
    }
  }
  if (racePlaying.value && !raceFinished.value) startRaceTicker()
}

let introStartTimer = 0
let introResetTimer = 0
watch(
  () => props.isActive,
  (active) => {
    if (typeof window !== 'undefined') {
      if (introStartTimer) { window.clearTimeout(introStartTimer); introStartTimer = 0 }
      if (introResetTimer) { window.clearTimeout(introResetTimer); introResetTimer = 0 }
    }
    if (active) {
      hasEntered.value = true
      resumeCardLoops()
      // 没有搭子对象时跳过值机，直接亮大屏
      if (!bestBuddy.value && replyEvents.value > 0 && phase.value === 'idle') {
        phase.value = 'revealed'
        leftDocked.value = true
        boardOn.value = true
        boardIntro.value = false
        runwayOn.value = true
        startRace()
      }
      if (typeof window === 'undefined' || reducedMotion.value) {
        playInitiativeIntro()
        return
      }
      if (initiativeEntered.value) return
      introStartTimer = window.setTimeout(() => {
        introStartTimer = 0
        playInitiativeIntro()
      }, 450)
    } else {
      pauseCardLoops()
      if (typeof window === 'undefined') return
      introResetTimer = window.setTimeout(() => {
        introResetTimer = 0
        initiativeEntered.value = false
      }, 750)
    }
  },
  { immediate: true }
)

// 后端数据更新（刷新/重试）时回到初始态
watch(
  () => props.card?.data,
  () => {
    clearTimers()
    resetAvatarOk()
    phase.value = 'idle'
    shownUser.value = null
    shownAvatarOk.value = true
    lotterySnapping = false
    resetRevealState()
    raceReset()
    initiativeEntered.value = false
    if (hasEntered.value) nextTick(() => playInitiativeIntro())
  }
)

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    if (introStartTimer) window.clearTimeout(introStartTimer)
    if (introResetTimer) window.clearTimeout(introResetTimer)
  }
  clearTimers()
  stopRaceTicker()
})
</script>

<style scoped>
/* ================= 通用 ================= */

.avio-mono {
  font-family: ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-variant-numeric: tabular-nums;
}

/* 通用材质颗粒：所有仪器表面共用一层细噪点 */
.grain {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNjAiIGhlaWdodD0iMTYwIj4KICA8ZmlsdGVyIGlkPSJuIj4KICAgIDxmZVR1cmJ1bGVuY2UgdHlwZT0iZnJhY3RhbE5vaXNlIiBiYXNlRnJlcXVlbmN5PSIwLjgiIG51bU9jdGF2ZXM9IjQiIHN0aXRjaFRpbGVzPSJzdGl0Y2giLz4KICAgIDxmZUNvbG9yTWF0cml4IHR5cGU9InNhdHVyYXRlIiB2YWx1ZXM9IjAiLz4KICA8L2ZpbHRlcj4KICA8cmVjdCB3aWR0aD0iMTYwIiBoZWlnaHQ9IjE2MCIgZmlsdGVyPSJ1cmwoI24pIiBvcGFjaXR5PSIwLjQ1Ii8+Cjwvc3ZnPg==");
  background-size: 160px 160px;
  mix-blend-mode: overlay;
  opacity: 0.22;
  pointer-events: none;
  z-index: 2;
}

/* ================= 报头铭牌 ================= */

.tm-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  font-size: 11px;
}

.tm-brand {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 6px;
  background: rgba(62, 229, 138, 0.1);
  color: #7BE3AC;
  letter-spacing: 0.12em;
  font-size: 10.5px;
  box-shadow: inset 0 0 0 1px rgba(62, 229, 138, 0.26);
  text-shadow: 0 0 8px rgba(123, 227, 172, 0.35);
}

.tm-plane {
  width: 12px;
  height: 12px;
  color: #3EE58A;
}

.tm-dot {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
}

.tm-item {
  color: rgba(255, 255, 255, 0.45);
  letter-spacing: 0.05em;
}

.tm-item b {
  color: #3EE58A;
  font-weight: 700;
  margin: 0 1px;
}

/* ================= 值机柜台 ================= */

.ck-rail {
  transition: transform 500ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.ck-sign {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 14px;
  border-radius: 8px;
  background: linear-gradient(160deg, #0B8F4C 0%, #067A43 100%);
  color: #ffffff;
  font-size: 11px;
  letter-spacing: 0.22em;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.22),
    0 6px 16px rgba(6, 122, 67, 0.28);
}

.ck-sign svg {
  width: 14px;
  height: 14px;
}

.ck-sign--rest {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.1em;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.1);
}

/* 证件照格：四角对位标 */
.ck-photo {
  position: relative;
  width: 86px;
  height: 86px;
  padding: 6px;
}

.ck-photo-frame {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0.05) 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.14),
    inset 0 0 0 1px rgba(255, 255, 255, 0.08),
    inset 0 -10px 18px rgba(0, 0, 0, 0.28),
    0 10px 26px rgba(0, 0, 0, 0.42);
}

.ck-photo--live .ck-photo-frame {
  cursor: pointer;
}

.ck-photo-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ck-photo-holder {
  width: 54%;
  height: 54%;
  color: rgba(255, 255, 255, 0.16);
}

.ck-tick {
  position: absolute;
  width: 12px;
  height: 12px;
  border-color: rgba(255, 255, 255, 0.4);
  border-style: solid;
  border-width: 0;
}

.ck-tick--tl { top: 0; left: 0; border-top-width: 1.5px; border-left-width: 1.5px; }
.ck-tick--tr { top: 0; right: 0; border-top-width: 1.5px; border-right-width: 1.5px; }
.ck-tick--bl { bottom: 0; left: 0; border-bottom-width: 1.5px; border-left-width: 1.5px; }
.ck-tick--br { bottom: 0; right: 0; border-bottom-width: 1.5px; border-right-width: 1.5px; }

.ck-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  padding: 9px 20px;
  border-radius: 12px;
  background: linear-gradient(180deg, #0BCE6B 0%, #07AC56 100%);
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-shadow: 0 1px 2px rgba(0, 60, 30, 0.35);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.35),
    inset 0 0 0 1px rgba(255, 255, 255, 0.08),
    0 2px 6px rgba(0, 0, 0, 0.4),
    0 10px 26px rgba(7, 193, 96, 0.28);
  transition: filter 180ms ease, transform 180ms ease, box-shadow 180ms ease !important;
}

.ck-btn:hover {
  filter: brightness(1.06);
  transform: translateY(-1px);
}

.ck-btn--rolling {
  background: rgba(7, 193, 96, 0.72);
}

.ck-btn--ghost {
  background: transparent;
  color: #07C160;
  border: 1px solid rgba(7, 193, 96, 0.4);
  box-shadow: none;
  padding: 8px 18px;
  font-size: 13px;
}

.ck-btn--ghost:hover {
  background: rgba(7, 193, 96, 0.08);
  transform: none;
}

/* ================= 登机牌 ================= */

.pass-printer {
  position: relative;
  width: min(100%, 344px);
  padding-top: 10px;
}

/* 打印槽 */
.pass-slot {
  position: absolute;
  top: 0;
  left: 6%;
  right: 6%;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #060908, #1E2422);
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.7), 0 1px 0 rgba(255, 255, 255, 0.12);
  z-index: 3;
}

.pass {
  position: relative;
  border-radius: 16px;
  padding: 15px 18px 0;
  overflow: hidden;
  color: #EFFFF4;
  background:
    radial-gradient(130% 100% at 14% -4%, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0) 48%),
    radial-gradient(120% 90% at 88% 112%, rgba(0, 0, 0, 0.24), rgba(0, 0, 0, 0) 52%),
    linear-gradient(155deg, #0C8A4C 0%, #087544 46%, #045530 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    inset 0 0 0 1px rgba(255, 255, 255, 0.06),
    0 2px 6px rgba(4, 60, 34, 0.18),
    0 22px 44px rgba(5, 80, 45, 0.28);
  /* 票根冲孔缺口；不支持 mask-composite 的环境优雅退化为无缺口 */
  -webkit-mask-image:
    radial-gradient(circle 8px at 0 calc(100% - 56px), transparent 7.5px, #000 8.5px),
    radial-gradient(circle 8px at 100% calc(100% - 56px), transparent 7.5px, #000 8.5px);
  -webkit-mask-composite: source-in;
  mask-image:
    radial-gradient(circle 8px at 0 calc(100% - 56px), transparent 7.5px, #000 8.5px),
    radial-gradient(circle 8px at 100% calc(100% - 56px), transparent 7.5px, #000 8.5px);
  mask-composite: intersect;
  transform-origin: 50% 0%;
  /* backwards：结束后交还 transform 给指针倾斜的 inline style（forwards 会把它永久盖住） */
  animation: pass-print 780ms cubic-bezier(0.2, 0.9, 0.3, 1.04) backwards;
  transition: transform 620ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 300ms ease !important;
  will-change: transform;
}

.pass--live {
  transition: transform 70ms linear, box-shadow 300ms ease !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    inset 0 0 0 1px rgba(255, 255, 255, 0.06),
    0 4px 10px rgba(4, 60, 34, 0.2),
    0 30px 60px rgba(5, 80, 45, 0.36);
}

/* 金箔发丝内框：只围绿色主区，到撕线为止 */
.pass::after {
  content: '';
  position: absolute;
  inset: 6px 6px 62px;
  border-radius: 11px 11px 4px 4px;
  border: 1px solid rgba(236, 209, 140, 0.26);
  pointer-events: none;
}

/* 金箔字：箔面渐变随倾斜（--gx）流动 */
.pass-foil {
  background-image: linear-gradient(105deg, #A87E2A 0%, #D9B863 26%, #F7E9B8 50%, #D9B863 74%, #A87E2A 100%);
  background-size: 240% 100%;
  background-position-x: var(--gx, 50%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.pass--reduced {
  animation: none;
}

@keyframes pass-print {
  0% {
    opacity: 0;
    transform: translateY(-46px) scaleY(0.88);
    clip-path: inset(0 0 100% 0 round 16px);
  }
  55% {
    opacity: 1;
    clip-path: inset(0 0 0% 0 round 16px);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scaleY(1);
    clip-path: inset(0 0 0% 0 round 16px);
  }
}

.pass-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pass-airline {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 750;
  letter-spacing: 0.26em;
}

.pass-airline svg {
  width: 15px;
  height: 15px;
  color: #E9CE85;
}

.pass-class {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3.5px 9px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.16);
  box-shadow: inset 0 0 0 1px rgba(236, 209, 140, 0.36);
}

.pass-class i {
  font-style: normal;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.18em;
}

.pass-class em {
  font-style: normal;
  font-size: 9px;
  letter-spacing: 0.12em;
  color: rgba(255, 255, 255, 0.72);
}

/* 航路：你 ✈ TA */
.pass-route {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}

.pass-port {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}

.pass-port--to {
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}

.pass-port-code {
  font-size: 30px;
  font-weight: 800;
  line-height: 1;
}

.pass-port-sub {
  font-size: 9px;
  letter-spacing: 0.22em;
  color: rgba(240, 224, 178, 0.62);
}

.pass-port-ava {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.4);
  font-size: 14px;
  color: rgba(255, 255, 255, 0.85);
}

.pass-port-ava img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.pass-port-name {
  max-width: 9.5em;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pass-port--to .pass-port-sub {
  width: 100%;
  text-align: right;
}

/* 航路虚线 + 小飞机 */
.pass-path {
  position: relative;
  flex: 1;
  height: 16px;
  min-width: 40px;
}

.pass-path::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  border-top: 1.5px dashed rgba(244, 232, 196, 0.42);
}

.pass-path-plane {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 15px;
  height: 15px;
  transform: translate(-50%, -50%);
  color: #F3E7C2;
}

/* 打印后小飞机沿航路滑入（一次性） */
.pass:not(.pass--reduced) .pass-path-plane {
  animation: pass-plane-cross 1.5s cubic-bezier(0.3, 0.7, 0.25, 1) 480ms both;
}

@keyframes pass-plane-cross {
  0% { transform: translate(-50%, -50%) translateX(-72px); opacity: 0; }
  18% { opacity: 1; }
  100% { transform: translate(-50%, -50%) translateX(0); opacity: 1; }
}

/* 字段矩阵 */
.pass-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 12px;
  margin-top: 14px;
}

.pass-field {
  display: flex;
  flex-direction: column;
  gap: 1.5px;
  min-width: 0;
}

.pass-field i {
  font-size: 8.5px;
  letter-spacing: 0.14em;
  color: rgba(240, 224, 178, 0.62);
  font-style: normal;
  white-space: nowrap;
}

.pass-field b {
  font-size: 15px;
  font-weight: 750;
  line-height: 1.15;
  white-space: nowrap;
}

.pass-field em {
  font-size: 9.5px;
  font-style: normal;
  color: rgba(255, 255, 255, 0.52);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pass-speedline {
  margin-top: 11px;
  font-size: 11px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.78);
  /* 折行均衡，避免「钟。」单字孤行 */
  text-wrap: balance;
}

/* ---------- 撕线票根 ---------- */
.pass-stub {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 56px;
  margin: 13px -18px 0;
  padding: 9px 16px 10px;
  background: linear-gradient(180deg, #FBF7EB 0%, #F2EBD9 100%);
}

/* 撕线冲孔点 */
.pass-stub::before {
  content: '';
  position: absolute;
  top: -1px;
  left: 12px;
  right: 12px;
  height: 2.5px;
  background-image: radial-gradient(circle 1.1px, rgba(20, 40, 28, 0.42) 1.05px, transparent 1.25px);
  background-size: 7px 2.5px;
  background-repeat: repeat-x;
}

.pass-stub-codes {
  display: flex;
  flex-direction: column;
  gap: 2.5px;
  flex-shrink: 0;
}

.pass-stub-codes i {
  font-style: normal;
  font-size: 8px;
  letter-spacing: 0.12em;
  color: rgba(30, 45, 30, 0.52);
  white-space: nowrap;
}

.pass-stub-codes i:first-child {
  font-size: 9.5px;
  font-weight: 700;
  color: rgba(30, 45, 30, 0.74);
}

/* 纸张噪点 + 箔面扫光 */
.pass-grain {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNjAiIGhlaWdodD0iMTYwIj4KICA8ZmlsdGVyIGlkPSJuIj4KICAgIDxmZVR1cmJ1bGVuY2UgdHlwZT0iZnJhY3RhbE5vaXNlIiBiYXNlRnJlcXVlbmN5PSIwLjgiIG51bU9jdGF2ZXM9IjQiIHN0aXRjaFRpbGVzPSJzdGl0Y2giLz4KICAgIDxmZUNvbG9yTWF0cml4IHR5cGU9InNhdHVyYXRlIiB2YWx1ZXM9IjAiLz4KICA8L2ZpbHRlcj4KICA8cmVjdCB3aWR0aD0iMTYwIiBoZWlnaHQ9IjE2MCIgZmlsdGVyPSJ1cmwoI24pIiBvcGFjaXR5PSIwLjQ1Ii8+Cjwvc3ZnPg==");
  background-size: 160px 160px;
  mix-blend-mode: overlay;
  opacity: 0.3;
  pointer-events: none;
  z-index: 2;
}

.pass-sheen {
  position: absolute;
  inset: -20%;
  background: linear-gradient(100deg, transparent 42%, rgba(255, 255, 255, 0.15) 50%, transparent 58%);
  transform: translateX(calc((var(--gx, 50%) - 50%) * 1.6));
  opacity: 0;
  transition: opacity 300ms ease !important;
  pointer-events: none;
  z-index: 2;
}

.pass--live .pass-sheen {
  opacity: 1;
  transition: none !important;
}

.pass-speedline b {
  color: #ffffff;
  font-weight: 700;
}

.pass-speedline .pass-slow {
  color: #FFD98A;
}

.pass-barcode {
  height: 32px;
  flex: 1;
  min-width: 0;
  color: #26301F;
  opacity: 0.9;
}

/* 印章 */
.pass-stamp {
  position: absolute;
  bottom: 8px;
  right: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 5px 9px;
  border: 2.5px solid rgba(199, 120, 0, 0.78);
  border-radius: 9px;
  color: rgba(178, 106, 0, 0.9);
  transform: rotate(-8deg);
  animation: stamp-in 480ms cubic-bezier(0.18, 1.6, 0.4, 1) both;
  pointer-events: none;
  z-index: 3;
}

.pass-stamp i {
  font-style: normal;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.28em;
  margin-right: -0.28em;
}

.pass-stamp em {
  font-style: normal;
  font-size: 7px;
  letter-spacing: 0.16em;
  opacity: 0.85;
}

@keyframes stamp-in {
  0% { opacity: 0; transform: rotate(-8deg) scale(1.9); }
  60% { opacity: 1; }
  100% { opacity: 0.94; transform: rotate(-8deg) scale(1); }
}

/* 流光 */
.pass-glare {
  position: absolute;
  inset: 0;
  border-radius: 16px;
  background: radial-gradient(
    58% 42% at var(--gx, 50%) var(--gy, 26%),
    rgba(255, 255, 255, 0.24),
    rgba(255, 255, 255, 0.05) 46%,
    rgba(255, 255, 255, 0) 72%
  );
  opacity: 0.5;
  transition: opacity 300ms ease !important;
  pointer-events: none;
  z-index: 2;
}

.pass--live .pass-glare {
  opacity: 0.9;
  transition: none !important;
}

.card-anim-paused .pass-path-plane,
.card-anim-paused .pass-stamp,
.card-anim-paused .pass {
  animation-play-state: paused;
}

/* ================= 回复跑道 ================= */


/* 跑道入口标线 */
.rw-threshold {
  position: absolute;
  left: 8px;
  top: 4px;
  bottom: 4px;
  width: 10px;
  background: repeating-linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.55) 0 2px,
    transparent 2px 5px
  );
  border-radius: 1px;
  opacity: 0.6;
}

/* 中心虚线 */
.rw-center {
  position: absolute;
  left: 26px;
  right: 10px;
  top: 50%;
  border-top: 2px dashed rgba(255, 255, 255, 0.28);
  transform: translateY(-50%);
}

.rw-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 0;
}

.rw-plane {
  position: absolute;
  top: 50%;
  left: 0;
  width: 17px;
  height: 17px;
  color: #3EE58A;
  filter: drop-shadow(0 0 6px rgba(62, 229, 138, 0.55));
  transform: translate(-50%, -50%);
  opacity: 0;
}

.rw-on .rw-plane {
  animation: rw-taxi 1.1s cubic-bezier(0.2, 0.7, 0.2, 1) 80ms both;
}

.rw-reduced .rw-plane,
.init-reduced .rw-plane {
  animation: none;
  opacity: 1;
}

@keyframes rw-taxi {
  0% { opacity: 0; transform: translate(-320%, -50%); }
  25% { opacity: 1; }
  100% { opacity: 1; transform: translate(-50%, -50%); }
}

.rw-tick {
  position: absolute;
  top: 5px;
  bottom: 5px;
  left: 0;
  width: 2px;
  transform: translateX(-50%);
  border-radius: 1px;
  background: #D98F00;
}

.rw-marker em {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  transform: translateX(-50%);
  font-size: 8px;
  font-style: normal;
  letter-spacing: 0.06em;
  white-space: nowrap;
  color: rgba(255, 255, 255, 0.5);
  opacity: 0;
}

.rw-marker--p50 em { color: #3EE58A; text-shadow: 0 0 8px rgba(62, 229, 138, 0.35); }
.rw-marker--p90 em { color: #E8B54A; transform: translateX(-96%); text-shadow: 0 0 8px rgba(232, 181, 74, 0.35); }

.rw-on .rw-marker em {
  animation: rw-label 500ms ease 700ms both;
}

.rw-reduced .rw-marker em {
  animation: none;
  opacity: 1;
}

@keyframes rw-label {
  from { opacity: 0; transform: translateX(-50%) translateY(3px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

.rw-on .rw-marker--p90 em {
  animation-name: rw-label-end;
}

@keyframes rw-label-end {
  from { opacity: 0; transform: translateX(-96%) translateY(3px); }
  to { opacity: 1; transform: translateX(-96%) translateY(0); }
}


/* ================= 出港大屏 ================= */

.brd-fade-enter-active,
.brd-fade-leave-active {
  transition: opacity 300ms ease, transform 300ms ease !important;
}

.brd-fade-enter-from,
.brd-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.brd {
  position: relative;
  border-radius: 18px;
  padding: 12px 12px 8px;
  background:
    radial-gradient(140% 100% at 50% -20%, rgba(120, 200, 160, 0.1), rgba(120, 200, 160, 0) 52%),
    linear-gradient(180deg, #171C1E 0%, #101416 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.12),
    inset 0 0 0 1px rgba(255, 255, 255, 0.07),
    inset 0 -16px 30px rgba(0, 0, 0, 0.32),
    0 0 0 1.5px rgba(0, 0, 0, 0.55),
    0 2px 0 1.5px rgba(255, 255, 255, 0.04),
    0 26px 50px rgba(0, 0, 0, 0.48);
}

/* 屏面玻璃：左上角一道斜向反光 */
.brd-glass {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(118deg, rgba(255, 255, 255, 0.055) 0%, rgba(255, 255, 255, 0) 30%);
  pointer-events: none;
  z-index: 2;
}

.brd-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brd-title {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  letter-spacing: 0.18em;
  color: #E8DFC8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brd-title-sub {
  margin-left: 8px;
  font-size: 9px;
  letter-spacing: 0.1em;
  color: rgba(232, 223, 200, 0.4);
}

.brd-clock {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.45);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  font-size: 11px;
  letter-spacing: 0.1em;
  color: #F2E9D4;
  text-shadow: 0 0 8px rgba(242, 233, 212, 0.28);
}

.brd-clock--live {
  cursor: pointer;
}

.brd-live {
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: #3EE58A;
  animation: brd-blink 1s steps(1) infinite;
}

@keyframes brd-blink {
  0%, 55% { opacity: 1; }
  56%, 100% { opacity: 0.25; }
}

.card-anim-paused .brd-live {
  animation-play-state: paused;
}

.brd-replay {
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 10px;
  letter-spacing: 0.12em;
  color: #3EE58A;
  background: rgba(62, 229, 138, 0.1);
  box-shadow: inset 0 0 0 1px rgba(62, 229, 138, 0.3);
  transition: background 160ms ease !important;
}

.brd-replay:hover {
  background: rgba(62, 229, 138, 0.2);
}

.brd-cols {
  display: grid;
  grid-template-columns: 22px 26px minmax(0, 1fr) 56px 56px 88px;
  gap: 7px;
  align-items: center;
  margin-top: 9px;
  padding: 0 8px 5px;
  font-size: 8.5px;
  letter-spacing: 0.14em;
  color: rgba(232, 223, 200, 0.42);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brd-num-h {
  text-align: right;
}

.brd-empty {
  padding: 18px 8px 14px;
  font-size: 12px;
  color: rgba(232, 223, 200, 0.5);
}

.brd-body {
  margin-top: 4px;
  /* 锁死 10 行高：回放中行数增减（含离场瞬间的第 11 行）都不改变面板高度，
     否则会推挤下方公告带并触发 FitScale 反复重缩放（页面抖动元凶） */
  height: 260px;
  overflow: hidden;
}

.brd-row {
  display: grid;
  grid-template-columns: 22px 26px minmax(0, 1fr) 56px 56px 88px;
  gap: 7px;
  align-items: center;
  height: 26px;
  padding: 0 8px;
  border-radius: 7px;
  position: relative;
}

/* 大屏上电：逐行亮起 */
.brd--intro .brd-row {
  animation: brd-in 460ms cubic-bezier(0.22, 1, 0.36, 1) var(--rd, 0ms) both;
}

@keyframes brd-in {
  from { opacity: 0; transform: translateY(7px); }
  to { opacity: 1; transform: translateY(0); }
}

.brd-row:hover {
  background: rgba(255, 255, 255, 0.05);
}

.brd-row--first .brd-rank,
.brd-row--first .brd-name {
  color: #3EE58A;
}

.brd-move {
  transition: transform 240ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.brd-enter-active {
  transition: opacity 260ms ease !important;
}

.brd-enter-from {
  opacity: 0;
}

/* 掉出榜的行立即消失，不占位（残留一帧就会把榜体撑高一行） */
.brd-leave-active {
  display: none !important;
}

.brd-rank {
  font-size: 10.5px;
  color: rgba(232, 223, 200, 0.5);
}

.brd-ava {
  width: 21px;
  height: 21px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.brd-ava img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.brd-ava-fb {
  font-size: 10px;
  color: rgba(232, 223, 200, 0.6);
}

.brd-name {
  font-size: 12px;
  color: #EDE7D6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brd-num {
  font-size: 11px;
  text-align: right;
  color: #57D68F;
  text-shadow: 0 0 9px rgba(87, 214, 143, 0.32);
}

.brd-num--in {
  color: #E8B54A;
  text-shadow: 0 0 9px rgba(232, 181, 74, 0.32);
}

.brd-total {
  display: flex;
  justify-content: flex-end;
  font-size: 13px;
  font-weight: 700;
  color: #F5EFE1;
  text-shadow: 0 0 10px rgba(245, 239, 225, 0.24);
}

.brd-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 6px 8px 3px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  font-size: 8.5px;
  letter-spacing: 0.12em;
  color: rgba(232, 223, 200, 0.4);
}

.brd-dot {
  width: 5px;
  height: 5px;
  border-radius: 999px;
}

.brd-dot--g { background: #3EE58A; }
.brd-dot--a { background: #E8B54A; margin-left: 8px; }

.brd-note-right {
  margin-left: auto;
}

/* 窄屏：收起出/进两列，只留里程合计，避免横向溢出 */
@media (max-width: 640px) {
  .brd-cols,
  .brd-row {
    grid-template-columns: 22px 26px minmax(0, 1fr) 88px;
  }

  .brd-cols .brd-num-h:not(.brd-num-h--total),
  .brd-row .brd-num {
    display: none;
  }
}

/* ================= 航站公告带 ================= */

/* ================= 夜间停机坪 ================= */

.apron-row {
  display: flex;
  align-items: flex-start;
  gap: 26px;
}

/* 端头：无容器的巨型发光读数 */
.apr-end {
  position: relative;
  flex: 0 0 auto;
  min-width: 172px;
  opacity: 0;
  transition: opacity 0.6s ease, transform 0.65s cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.apr-end--dep {
  transform: translateX(-18px);
}

.apr-end--arr {
  text-align: right;
  transform: translateX(18px);
  transition-delay: 100ms, 100ms !important;
}

.init-entered .apr-end {
  opacity: 1;
  transform: none;
}

/* 端头下方的地面光斑 */
.apr-end::after {
  content: '';
  position: absolute;
  left: 6%;
  right: 6%;
  bottom: -16px;
  height: 30px;
  filter: blur(12px);
  pointer-events: none;
  z-index: -1;
}

.apr-end--dep::after {
  background: radial-gradient(50% 100% at 50% 0%, rgba(11, 164, 87, 0.22), rgba(11, 164, 87, 0) 74%);
}

.apr-end--arr::after {
  background: radial-gradient(50% 100% at 50% 0%, rgba(217, 149, 0, 0.2), rgba(217, 149, 0, 0) 74%);
}

.apr-word {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 750;
  letter-spacing: 0.16em;
  color: rgba(255, 255, 255, 0.92);
}

.apr-end--arr .apr-word {
  justify-content: flex-end;
}

.apr-word i {
  font-style: normal;
  font-size: 8.5px;
  letter-spacing: 0.22em;
}

.apr-end--dep .apr-word i { color: rgba(62, 229, 138, 0.55); }
.apr-end--arr .apr-word i { color: rgba(242, 192, 99, 0.58); }

.apr-ic {
  width: 17px;
  height: 17px;
}

.apr-end--dep .apr-ic { color: #3EE58A; filter: drop-shadow(0 0 7px rgba(62, 229, 138, 0.55)); }
.apr-end--arr .apr-ic { color: #F2C063; filter: drop-shadow(0 0 7px rgba(242, 192, 99, 0.5)); }

/* 巨型读数：本区最大字号，端头对置 */
.apr-num {
  margin-top: 4px;
  font-size: clamp(32px, 3vw, 42px);
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0.01em;
}

.apr-end--dep .apr-num {
  color: #3EE58A;
  text-shadow: 0 0 26px rgba(62, 229, 138, 0.45), 0 0 5px rgba(62, 229, 138, 0.4);
}

.apr-end--arr .apr-num {
  color: #F2C063;
  text-shadow: 0 0 26px rgba(242, 192, 99, 0.42), 0 0 5px rgba(242, 192, 99, 0.38);
}

.apr-sub {
  margin-top: 4px;
  font-size: 8.5px;
  letter-spacing: 0.2em;
  color: rgba(255, 255, 255, 0.4);
}

.apr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 7px;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.5s ease 500ms, transform 0.5s ease 500ms !important;
}

.apr-end--arr .apr-chips {
  justify-content: flex-end;
}

.init-entered .apr-chips {
  opacity: 1;
  transform: none;
}

.apr-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2.5px 8px 2.5px 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.09), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.apr-chip-ava {
  width: 19px;
  height: 19px;
  border-radius: 999px;
  overflow: hidden;
  border: 1.5px solid rgba(255, 255, 255, 0.35);
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.apr-chip-ava img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.apr-chip-fb {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.6);
}

.apr-chip-name {
  max-width: 54px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.88);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.apr-chip b {
  font-size: 10.5px;
  font-weight: 700;
  color: #ffffff;
}

/* 塔台日志：发丝分栏，无框 */
.apr-log {
  flex: 1;
  min-width: 0;
  padding: 1px 20px 0;
  border-left: 1px solid rgba(255, 255, 255, 0.09);
  border-right: 1px solid rgba(255, 255, 255, 0.09);
}

.apr-log-head {
  font-size: 8.5px;
  letter-spacing: 0.22em;
  color: rgba(255, 255, 255, 0.36);
  margin-bottom: 7px;
}


/* 日志行：无框，逐条打出 */
.ntc {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  margin-top: 5px;
  animation: ntc-in 520ms cubic-bezier(0.22, 1, 0.36, 1) var(--nd, 0ms) both;
}

@keyframes ntc-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

.ntc-tag {
  flex-shrink: 0;
  margin-top: 1px;
  padding: 2.5px 7px;
  border-radius: 5px;
  font-size: 8.5px;
  letter-spacing: 0.1em;
  white-space: nowrap;
}

.ntc-tag--ok {
  color: #3EE58A;
  background: rgba(62, 229, 138, 0.12);
  box-shadow: inset 0 0 0 1px rgba(62, 229, 138, 0.3), 0 0 12px rgba(62, 229, 138, 0.14);
  text-shadow: 0 0 6px rgba(62, 229, 138, 0.4);
}

.ntc-tag--delay {
  color: #E8B54A;
  background: rgba(242, 170, 0, 0.13);
  box-shadow: inset 0 0 0 1px rgba(242, 170, 0, 0.32), 0 0 12px rgba(242, 170, 0, 0.13);
  text-shadow: 0 0 6px rgba(232, 181, 74, 0.4);
}

.ntc-tag--duo {
  color: #93A7E8;
  background: rgba(91, 111, 184, 0.18);
  box-shadow: inset 0 0 0 1px rgba(91, 111, 184, 0.4), 0 0 12px rgba(91, 111, 184, 0.16);
  text-shadow: 0 0 6px rgba(147, 167, 232, 0.4);
}

.ntc-body {
  font-size: 11px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.66);
  min-width: 0;
  /* 折行均衡，避免「程」类单字孤行 */
  text-wrap: balance;
}

.ntc-body b {
  font-weight: 700;
}

.ntc-soft {
  color: rgba(255, 255, 255, 0.35);
}

.ntc-swap {
  font-style: normal;
  margin: 0 1px;
  color: rgba(255, 255, 255, 0.35);
}

.ntc-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px 1px 2px;
  margin: 0 1px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.09);
  vertical-align: -4px;
}

.ntc-chip-ava {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.14);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 8px;
  color: rgba(255, 255, 255, 0.6);
  flex-shrink: 0;
}

.ntc-chip-ava img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ntc-chip b {
  max-width: 7em;
  font-size: 10.5px;
  font-weight: 650;
  color: rgba(255, 255, 255, 0.82);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ntc-pending {
  font-size: 10px;
  letter-spacing: 0.14em;
  color: rgba(255, 255, 255, 0.32);
}

.ntc-caret {
  display: inline-block;
  width: 0.55em;
  height: 1em;
  margin-left: 4px;
  vertical-align: -0.15em;
  background: rgba(62, 229, 138, 0.6);
  animation: ntc-blink 1s steps(1) infinite;
}

@keyframes ntc-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

.card-anim-paused .ntc-caret {
  animation-play-state: paused;
}

/* ================= 05L / 05R 双跑道 ================= */

.rwy {
  margin-top: 10px;
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.55s ease 260ms, transform 0.6s cubic-bezier(0.22, 1, 0.36, 1) 260ms !important;
}

.init-entered .rwy--init {
  opacity: 1;
  transform: none;
}

/* 05R 揭晓后才通电 */
.rwy--speed {
  margin-top: 7px;
  transition: none !important;
  animation: ntc-in 600ms cubic-bezier(0.22, 1, 0.36, 1) 150ms both;
  opacity: 1;
  transform: none;
}

.rwy-meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.rwy-id {
  flex-shrink: 0;
  padding: 1.5px 7px;
  border-radius: 4px;
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: #3EE58A;
  background: rgba(62, 229, 138, 0.1);
  box-shadow: inset 0 0 0 1px rgba(62, 229, 138, 0.28);
  text-shadow: 0 0 6px rgba(62, 229, 138, 0.4);
}

.rwy-name {
  font-size: 9.5px;
  letter-spacing: 0.24em;
  color: rgba(255, 255, 255, 0.5);
  white-space: nowrap;
}

.rwy-cap {
  margin-left: auto;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.48);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rwy-cap b {
  font-weight: 650;
}

.rwy-g {
  color: #3EE58A;
  text-shadow: 0 0 8px rgba(62, 229, 138, 0.35);
}

.rwy-a {
  color: #E8B54A;
  text-shadow: 0 0 8px rgba(232, 181, 74, 0.35);
}

/* 跑道条：沥青薄带 + 白色边线 */
.rwy-strip {
  position: relative;
  height: 18px;
  margin-top: 5px;
  border-radius: 6px;
  background: linear-gradient(180deg, #20262A 0%, #14181B 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.07),
    inset 0 0 0 1px rgba(255, 255, 255, 0.05),
    inset 0 4px 8px rgba(0, 0, 0, 0.35);
}

.rwy-edge {
  position: absolute;
  left: 5px;
  right: 5px;
  height: 1px;
  background: rgba(255, 255, 255, 0.12);
}

.rwy-edge--t { top: 3px; }
.rwy-edge--b { bottom: 3px; }

.gauge-lamps {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle 1.7px, #D99B2E 1.7px, transparent 2px);
  background-size: 14px 100%;
  background-position: 8px center;
  background-repeat: repeat-x;
}


.gauge-lamps--glow {
  filter: blur(4px);
  opacity: 0.9;
}

.gauge-lights {
  position: absolute;
  inset: 0 auto 0 0;
  overflow: hidden;
  transition: width 1s cubic-bezier(0.22, 1, 0.36, 1) 500ms !important;
}

.gauge-lights .gauge-lamps--me {
  background-image: radial-gradient(circle 1.7px, #3EE58A 1.7px, transparent 2px);
}

.gauge-beacon {
  position: absolute;
  top: 50%;
  width: 7px;
  height: 7px;
  border-radius: 2px;
  background: #EAFBF1;
  transform: translate(-50%, -50%) rotate(45deg);
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.35),
    0 0 12px 2px rgba(62, 229, 138, 0.55);
  transition: left 1s cubic-bezier(0.22, 1, 0.36, 1) 500ms !important;
}


.gauge-cap b {
  font-weight: 650;
}

/* 尾声 */
.closer {
  margin-top: 9px;
  text-align: center;
  font-size: 11px;
  letter-spacing: 0.32em;
  color: rgba(255, 255, 255, 0.3);
}

/* 翻牌机匣：把散装格子装进一台机器 */
.flap-housing {
  position: relative;
  padding: 9px 12px;
  border-radius: 13px;
  background: linear-gradient(180deg, #191F21 0%, #101415 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.09),
    inset 0 0 0 1px rgba(255, 255, 255, 0.06),
    inset 0 -10px 18px rgba(0, 0, 0, 0.42),
    0 2px 5px rgba(0, 0, 0, 0.5),
    0 14px 30px rgba(0, 0, 0, 0.4);
}

/* 机匣两侧固定螺丝 */
.flap-housing::before,
.flap-housing::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 4px;
  height: 4px;
  border-radius: 999px;
  transform: translateY(-50%);
  background: radial-gradient(circle at 35% 30%, #6B7573, #23292B 70%);
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.6), inset 0 0 1px rgba(0, 0, 0, 0.8);
}

.flap-housing::before { left: 4.5px; }
.flap-housing::after { right: 4.5px; }

/* 停靠后：翻牌机与证件照收紧到窄柜台内 */
.ck-rail--docked :deep(.sf-row) {
  --sf-w: 28px;
  --sf-h: 38px;
  --sf-fs: 17px;
  --sf-r: 5px;
  gap: 4px;
}

.ck-rail--docked .ck-photo {
  width: 74px;
  height: 74px;
}

/* 减少动态效果 */
.init-reduced .apr-end,
.init-reduced .apr-chips,
.init-reduced .rwy {
  transition: none !important;
  opacity: 1;
  transform: none;
}

.init-reduced .ntc,
.init-reduced .rwy--speed {
  animation: none;
  opacity: 1;
  transform: none;
}
</style>
