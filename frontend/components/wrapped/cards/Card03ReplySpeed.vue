<template>
  <WrappedCardShell
    :card-id="card.id"
    :title="card.title"
    :narrative="''"
    :variant="variant"
    :class="{ 'card-anim-paused': animPaused }"
  >
    <!-- 子描述：仅在揭晓后出现，并使用“打字机”效果逐段输出 -->
    <template #narrative>
      <div v-if="phase === 'revealed'" class="mt-2 wrapped-body text-sm sm:text-base text-[#7F7F7F] leading-relaxed">
        <p class="whitespace-pre-wrap">
          <template v-for="(seg, i) in segments" :key="`${seg.type}-${i}`">
            <template v-if="seg.type === 'buddy'">
              <span
                v-if="isSegVisible(i)"
                class="inline-flex items-center gap-2 align-bottom px-1.5 py-0.5 rounded-lg bg-[#00000008]"
                :title="bestBuddy?.displayName || ''"
              >
                <span class="w-5 h-5 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                  <img
                    v-if="bestBuddyAvatarUrl && avatarOk.best"
                    :src="bestBuddyAvatarUrl"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk.best = false"
                  />
                  <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                    {{ avatarFallback(bestBuddy?.displayName) }}
                  </span>
                </span>
                <span class="wrapped-body text-sm text-[#000000e6] max-w-[12rem] truncate wrapped-privacy-name">
                  {{ bestBuddy?.displayName || '' }}
                </span>
              </span>
            </template>

            <template v-else-if="seg.type === 'contact'">
              <span
                v-if="isSegVisible(i)"
                class="inline-flex items-center gap-1.5 align-bottom px-1.5 py-0.5 rounded-lg bg-[#00000008]"
                :title="seg.contact?.displayName || ''"
              >
                <span class="w-4 h-4 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                  <img
                    v-if="resolveMediaUrl(seg.contact?.avatarUrl) && avatarOk[seg.contact?.username] !== false"
                    :src="resolveMediaUrl(seg.contact?.avatarUrl)"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk[seg.contact?.username] = false"
                  />
                  <span v-else class="wrapped-number text-[9px] text-[#00000066]">
                    {{ avatarFallback(seg.contact?.displayName) }}
                  </span>
                </span>
                <span class="wrapped-body text-sm text-[#000000e6] max-w-[8rem] truncate wrapped-privacy-name">
                  {{ seg.contact?.displayName || '' }}
                </span>
              </span>
            </template>

            <template v-else>
              <span
                v-if="seg.type === 'num'"
                class="wrapped-number text-[#07C160] font-semibold"
              >
                {{ segTextShown(i) }}
              </span>
              <span v-else>{{ segTextShown(i) }}</span>
            </template>
          </template>

          <span v-if="typingActive" class="type-caret" aria-hidden="true"></span>
        </p>
      </div>
    </template>

    <!-- 无可统计数据/索引未就绪：保留原来的引导与进度展示 -->
    <div v-if="replyEvents <= 0" class="text-sm text-[#7F7F7F]">
      <div class="rounded-xl border border-[#EDEDED] bg-white/60 p-4">
        <div class="wrapped-label text-xs text-[#00000066]">如何生成本页数据</div>
        <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
          <p>本页需要使用“消息搜索索引”来合并所有消息分片并计算回复耗时。</p>
          <p v-if="indexBuild && indexBuild.status === 'building'" class="mt-2">
            索引正在构建中：已索引
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(indexBuild.indexedMessages) }}</span>
            条消息。
            <span v-if="indexBuild.currentConversation" class="text-[#00000055]">（当前：{{ indexBuild.currentConversation }}）</span>
          </p>
          <ErrorNotice
            v-else-if="indexBuild && indexBuild.status === 'error'"
            :message="`索引构建失败：${indexBuild.error || '未知错误'}`"
            compact
            class="mt-2 text-red-600"
          />
          <p v-if="!usedIndex" class="mt-2">
            你可以先在「聊天记录搜索」中构建索引（或调用后端接口
            <code class="px-1 py-0.5 bg-[#00000008] rounded">/api/chat/search-index/build</code>），
            然后回到这里点击左上角“强制刷新”或本页“重试”。
          </p>
        </div>
      </div>
    </div>

    <!-- 主内容：抽奖揭晓 + 右侧年度 Top10 总消息 bar race + 「谁先开口」 -->
    <div v-else class="w-full">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
        <!-- Left: 抽奖区 -->
        <div
          class="reply-buddy-rail flex flex-col items-center justify-center transition-transform duration-500 will-change-transform"
          :class="leftRailClass"
        >
          <div class="wrapped-label text-xs text-[#00000066]">最佳聊天搭子</div>

          <div
            class="mt-4 w-28 h-28 sm:w-32 sm:h-32 rounded-2xl border border-[#EDEDED] bg-white/60 overflow-hidden flex items-center justify-center"
            :class="phase === 'rolling' ? 'cursor-pointer' : ''"
            :title="phase === 'rolling' ? '点击跳过' : ''"
            @click="skipLottery"
          >
            <img
              v-if="shownAvatarUrl && shownAvatarOk"
              :src="shownAvatarUrl"
              class="w-full h-full object-cover wrapped-privacy-avatar"
              alt="avatar"
              @error="onShownAvatarError"
            />
            <img
              v-else-if="phase === 'idle'"
              src="/assets/images/LuckyBlock.png"
              class="w-full h-full object-contain"
              alt="Lucky Block"
            />
            <div
              v-else
              class="w-full h-full flex items-center justify-center wrapped-privacy-avatar"
            >
              <span class="wrapped-number text-3xl text-[#00000066]">
                {{ shownAvatarFallback }}
              </span>
            </div>
          </div>

          <div class="mt-4 min-h-[1.75rem] wrapped-body text-base text-[#000000e6] max-w-[18rem] truncate wrapped-privacy-name" :title="shownDisplayName">
            {{ shownDisplayName }}
          </div>

          <div class="mt-5">
            <button
              v-if="phase === 'idle'"
              type="button"
              class="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-[#07C160] text-white text-sm sm:text-base wrapped-label hover:bg-[#06AD56] transition shadow-sm"
              @click="startLottery"
            >
              今年谁是你的最佳聊天搭子呢？
            </button>

            <button
              v-else-if="phase === 'rolling'"
              type="button"
              class="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-[#07C160]/70 text-white text-sm sm:text-base wrapped-label"
              @click="skipLottery"
            >
              生成中…点击跳过
            </button>

            <button
              v-else
              type="button"
              class="inline-flex items-center justify-center px-4 py-2 rounded-xl bg-transparent border border-[#07C160]/35 text-[#07C160] text-sm wrapped-label hover:bg-[#07C160]/10 transition"
              @click="restart"
            >
              再看一次
            </button>
          </div>

          <!-- 搭子小档案：揭晓后 3D 翻牌 -->
          <div v-if="phase === 'revealed' && buddyBadges.length" class="mt-6 w-full max-w-[20rem]">
            <div class="grid grid-cols-2 gap-2">
              <div v-for="(bg, idx) in buddyBadges" :key="bg.key" class="badge-flip">
                <div
                  class="badge-inner rounded-xl border border-[#EDEDED] bg-white/70 px-3 py-2.5"
                  :class="{ 'badge-shown': badgesFlipped, 'badge-reduced': reducedMotion }"
                  :style="{ '--flip-delay': `${idx * 120}ms` }"
                >
                  <div class="badge-face">
                    <div class="wrapped-label text-[10px] text-[#00000055]">{{ bg.label }}</div>
                    <div class="mt-0.5 wrapped-number text-sm text-[#000000e6] font-semibold">{{ bg.value }}</div>
                  </div>
                  <div class="badge-face badge-back rounded-xl" aria-hidden="true"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- 回复速度 P50/P90 速度条 -->
          <div v-if="phase === 'revealed' && replyStatsData" class="mt-5 w-full max-w-[20rem]">
            <div class="wrapped-label text-[10px] text-[#00000055]">回复速度分布</div>
            <div class="relative mt-2 h-2 rounded-full bg-[#00000008]">
              <div
                class="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-[#07C160] to-[#F2AA00]"
                :style="{ width: `${speedBarPct}%` }"
              />
              <div class="speed-marker" :style="{ left: `${p50MarkerPct}%`, opacity: speedBarProgress }">
                <span class="speed-marker-label">P50 · {{ formatDuration(replyStatsData.p50) }}</span>
              </div>
              <div class="speed-marker speed-marker-end" :style="{ left: '100%', opacity: speedBarProgress }">
                <span class="speed-marker-label">P90 · {{ formatDuration(replyStatsData.p90) }}</span>
              </div>
            </div>
            <p class="mt-6 wrapped-body text-xs text-[#7F7F7F]">
              你一半的回复在
              <span class="wrapped-number text-[#07C160] font-semibold">{{ formatDuration(replyStatsData.p50) }}</span>
              内发出，90% 不超过
              <span class="wrapped-number text-[#F2AA00] font-semibold">{{ formatDuration(replyStatsData.p90) }}</span>
            </p>
          </div>
        </div>

        <!-- Right: bar race（揭晓后出现） -->
        <Transition name="chart-fade">
          <div v-if="showChart" class="w-full">
            <div
              class="rounded-2xl border border-[#EDEDED] bg-white/60 p-4 sm:p-5"
            >
              <div class="flex items-center justify-between gap-4">
                <div>
                  <div class="wrapped-label text-xs text-[#00000066]">年度聊天排行（我发 + 对方）</div>
                  <div class="wrapped-body text-sm text-[#000000e6] mt-1">
                    <span class="wrapped-number text-[#07C160] font-semibold">{{ raceDate }}</span>
                    <span class="text-[#00000055]"> · {{ raceSpeed }}x</span>
                  </div>
                </div>
                <div class="flex items-center gap-3 text-[11px] text-[#00000066] shrink-0">
                  <span class="inline-flex items-center gap-1">
                    <span class="w-2 h-2 rounded-full bg-[#07C160]"></span>
                    我发
                  </span>
                  <span class="inline-flex items-center gap-1">
                    <span class="w-2 h-2 rounded-full bg-[#F2AA00]"></span>
                    对方
                  </span>
                </div>
              </div>

              <div v-if="raceDay > 0 && raceItems.length === 0" class="mt-4 wrapped-body text-sm text-[#7F7F7F]">
                暂无可展示的排行榜数据。
              </div>

              <div v-else class="race-scroll mt-4 max-h-[24rem] overflow-y-auto overflow-x-hidden pr-1">
                <TransitionGroup
                  name="race"
                  tag="div"
                  class="space-y-2"
                >
                  <div
                    v-for="item in raceItems"
                    :key="item.username"
                    class="race-row flex items-center gap-3"
                  >
                  <div class="w-6 text-right wrapped-label text-[11px] text-[#00000055]">
                    {{ item.rank }}
                  </div>

                  <div
                    class="w-7 h-7 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar"
                  >
                    <img
                      v-if="item.avatarUrl && avatarOk[item.username] !== false"
                      :src="item.avatarUrl"
                      class="w-full h-full object-cover"
                      alt="avatar"
                      @error="avatarOk[item.username] = false"
                    />
                    <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                      {{ avatarFallback(item.displayName) }}
                    </span>
                  </div>

                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-3">
                      <div class="min-w-0">
                        <div class="wrapped-body text-[#000000e6] text-sm truncate wrapped-privacy-name" :title="item.displayName">
                          {{ item.displayName }}
                        </div>
                      </div>
                      <div class="wrapped-number text-xs text-[#00000080] font-semibold">
                        {{ formatInt(item.value) }}
                      </div>
                    </div>
                    <div class="mt-1 h-2 rounded-full bg-[#00000008] overflow-hidden">
                      <div
                        class="race-bar-fill h-full rounded-full overflow-hidden flex"
                        :style="{ width: `${item.pct}%` }"
                      >
                        <div
                          class="race-bar race-bar-outgoing h-full"
                          :style="{ width: `${item.outgoingPartPct}%` }"
                        />
                        <div
                          class="race-bar race-bar-incoming h-full"
                          :style="{ width: `${item.incomingPartPct}%` }"
                        />
                      </div>
                    </div>
                  </div>
                  </div>
                </TransitionGroup>
              </div>

              <!-- 迷你播放器：暂停/继续、倍速、按天拖动 -->
              <div v-if="raceStarted && raceDays > 0" class="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  class="race-ctrl"
                  @click="toggleRacePlay"
                >
                  {{ raceFinished ? '重播' : (racePlaying ? '暂停' : '继续') }}
                </button>
                <button
                  type="button"
                  class="race-ctrl"
                  @click="toggleRaceSpeed"
                >
                  {{ raceSpeed }}x
                </button>
                <input
                  type="range"
                  class="race-range flex-1 accent-[#07C160]"
                  min="0"
                  :max="raceDays"
                  step="1"
                  :value="raceDay"
                  aria-label="按天拖动进度"
                  @input="onRaceScrub"
                />
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- 谁先开口（initiative 缺失/为空时整区隐藏） -->
      <div
        v-if="initiativeVisible"
        class="mt-8"
        :class="[initiativeEntered ? 'init-entered' : '', reducedMotion ? 'init-reduced' : '']"
      >
        <div class="rounded-2xl border border-[#EDEDED] bg-white/60 p-4 sm:p-5">
          <div class="wrapped-label text-xs text-[#00000066]">谁先开口</div>

          <div class="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            <!-- 主动率半环仪表 -->
            <div class="flex flex-col items-center">
              <div class="relative w-44">
                <svg viewBox="0 0 120 66" class="w-full h-auto" aria-hidden="true">
                  <path
                    d="M 10 60 A 50 50 0 0 1 110 60"
                    fill="none"
                    stroke="#00000010"
                    stroke-width="10"
                    stroke-linecap="round"
                  />
                  <path
                    d="M 10 60 A 50 50 0 0 1 110 60"
                    fill="none"
                    stroke="#07C160"
                    stroke-width="10"
                    stroke-linecap="round"
                    :stroke-dasharray="GAUGE_LEN"
                    :stroke-dashoffset="gaugeOffset"
                  />
                </svg>
                <div class="absolute inset-x-0 bottom-0 text-center">
                  <span class="wrapped-number text-2xl text-[#07C160] font-semibold">{{ rateDisplay }}</span>
                  <span class="wrapped-number text-sm text-[#07C160] font-semibold">%</span>
                </div>
              </div>
              <div class="mt-2 wrapped-body text-xs text-[#7F7F7F] text-center">
                全年
                <span class="wrapped-number text-[#07C160] font-semibold">{{ convDisplay }}</span>
                次对话，由你先开口的占比
              </div>
              <div class="mt-1 wrapped-body text-[11px] text-[#00000055] text-center">
                你先开口 {{ formatInt(initiative?.initiatedByMe) }} 次 · 对方先开口 {{ formatInt(initiative?.initiatedByOthers) }} 次
              </div>
            </div>

            <!-- 你最常主动找的 -->
            <div>
              <div class="wrapped-label text-[11px] text-[#00000055]">你最常主动找的</div>
              <div class="mt-2 space-y-2">
                <div
                  v-for="(p, idx) in topInitiatedByMe"
                  :key="`byme-${p.username}`"
                  class="init-slide flex items-center gap-3"
                  :style="{ '--slide-delay': `${200 + idx * 90}ms` }"
                >
                  <div class="w-7 h-7 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                    <img
                      v-if="resolveMediaUrl(p.avatarUrl) && avatarOk[p.username] !== false"
                      :src="resolveMediaUrl(p.avatarUrl)"
                      class="w-full h-full object-cover"
                      alt="avatar"
                      @error="avatarOk[p.username] = false"
                    />
                    <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                      {{ avatarFallback(p.displayName) }}
                    </span>
                  </div>
                  <div class="min-w-0 flex-1 wrapped-body text-sm text-[#000000e6] truncate wrapped-privacy-name" :title="p.displayName">
                    {{ p.displayName }}
                  </div>
                  <div class="wrapped-number text-xs text-[#07C160] font-semibold shrink-0">
                    {{ formatInt(p.count) }} 次
                  </div>
                </div>
                <div v-if="topInitiatedByMe.length === 0" class="wrapped-body text-xs text-[#00000055]">
                  今年你还没有主动开启过对话。
                </div>
              </div>
            </div>

            <!-- 最常来找你的 -->
            <div>
              <div class="wrapped-label text-[11px] text-[#00000055]">最常来找你的</div>
              <div class="mt-2 space-y-2">
                <div
                  v-for="(p, idx) in topInitiatedToMe"
                  :key="`tome-${p.username}`"
                  class="init-slide init-slide-right flex items-center gap-3"
                  :style="{ '--slide-delay': `${200 + idx * 90}ms` }"
                >
                  <div class="w-7 h-7 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                    <img
                      v-if="resolveMediaUrl(p.avatarUrl) && avatarOk[p.username] !== false"
                      :src="resolveMediaUrl(p.avatarUrl)"
                      class="w-full h-full object-cover"
                      alt="avatar"
                      @error="avatarOk[p.username] = false"
                    />
                    <span v-else class="wrapped-number text-[11px] text-[#00000066]">
                      {{ avatarFallback(p.displayName) }}
                    </span>
                  </div>
                  <div class="min-w-0 flex-1 wrapped-body text-sm text-[#000000e6] truncate wrapped-privacy-name" :title="p.displayName">
                    {{ p.displayName }}
                  </div>
                  <div class="wrapped-number text-xs text-[#F2AA00] font-semibold shrink-0">
                    {{ formatInt(p.count) }} 次
                  </div>
                </div>
                <div v-if="topInitiatedToMe.length === 0" class="wrapped-body text-xs text-[#00000055]">
                  今年还没有人主动来找你开启对话。
                </div>
              </div>
            </div>
          </div>

          <!-- 压轴：势均力敌 -->
          <div v-if="mutualFriend" class="mt-6 pt-5 border-t border-[#F3F3F3]">
            <div class="wrapped-label text-xs text-[#00000066] text-center">势均力敌</div>
            <div class="mt-3 flex items-center justify-center gap-3 sm:gap-5">
              <div class="text-right shrink-0">
                <div class="wrapped-label text-[11px] text-[#00000055]">你发出</div>
                <div class="wrapped-number text-xl text-[#07C160] font-semibold">
                  {{ mutualSentDisplay }} <span class="text-xs">条</span>
                </div>
              </div>

              <div class="flex flex-col items-center w-40 sm:w-56">
                <div class="w-9 h-9 rounded-lg overflow-hidden bg-[#0000000d] flex items-center justify-center wrapped-privacy-avatar">
                  <img
                    v-if="resolveMediaUrl(mutualFriend.avatarUrl) && avatarOk[mutualFriend.username] !== false"
                    :src="resolveMediaUrl(mutualFriend.avatarUrl)"
                    class="w-full h-full object-cover"
                    alt="avatar"
                    @error="avatarOk[mutualFriend.username] = false"
                  />
                  <span v-else class="wrapped-number text-sm text-[#00000066]">
                    {{ avatarFallback(mutualFriend.displayName) }}
                  </span>
                </div>
                <div class="mt-1 max-w-full wrapped-body text-xs text-[#000000e6] truncate wrapped-privacy-name" :title="mutualFriend.displayName">
                  {{ mutualFriend.displayName }}
                </div>
                <!-- 两端相向延伸、中点汇合 -->
                <svg viewBox="0 0 200 12" class="w-full h-3 mt-2" aria-hidden="true">
                  <path
                    d="M 0 6 L 100 6"
                    fill="none"
                    stroke="#07C160"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-dasharray="100"
                    :stroke-dashoffset="100 * (1 - mutualProgress)"
                  />
                  <path
                    d="M 200 6 L 100 6"
                    fill="none"
                    stroke="#F2AA00"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-dasharray="100"
                    :stroke-dashoffset="100 * (1 - mutualProgress)"
                  />
                  <circle
                    cx="100"
                    cy="6"
                    r="4"
                    fill="#07C160"
                    class="mutual-dot"
                    :class="{ 'mutual-dot-met': mutualMet }"
                  />
                </svg>
              </div>

              <div class="text-left shrink-0">
                <div class="wrapped-label text-[11px] text-[#00000055]">TA 发来</div>
                <div class="wrapped-number text-xl text-[#F2AA00] font-semibold">
                  {{ mutualRecvDisplay }} <span class="text-xs">条</span>
                </div>
              </div>
            </div>
            <div class="mt-2 text-center wrapped-body text-xs text-[#7F7F7F]">
              你和
              <span class="wrapped-privacy-name">{{ mutualFriend.displayName }}</span>
              的往来比 {{ mutualRatioText }}，是今年聊得最势均力敌的一对
            </div>
          </div>
        </div>
      </div>
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

// Data (from backend)
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

// Media URL resolving (same behavior as other wrapped components)
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

// ---------------- 卡片激活/暂停（deck 翻页） ----------------
// isActive=false 时暂停本卡所有循环动画；首次变为 true 时播放入场动画（只播一次）。
const animPaused = ref(false)
const hasEntered = ref(false)

// ---------------- Lottery (7s, ease-out slowdown) ----------------
const phase = ref('idle') // idle | rolling | revealed
const shownUser = ref(null) // current candidate object
const shownAvatarOk = ref(true)
const leftDocked = ref(false) // center -> left after reveal (lg)
const showChart = ref(false) // shown after the left block docks
let lotteryTimer = null
let typingTimer = null
let dockTimer = null
let chartTimer = null
let badgeTimer = null

const lotteryDurationMs = 7000
let lotteryStartedAt = 0
// 暂停（deck 翻走）时记录时间点，恢复时把暂停时长补偿回 startedAt。
let lotteryPausedAt = null
let lotterySnapping = false

const candidates = computed(() => {
  // Prefer allContacts (all contacts from contact.db) for more variety in lottery animation
  const allContacts = Array.isArray(props.card?.data?.allContacts) ? props.card.data.allContacts : []
  const topTotals = Array.isArray(props.card?.data?.topTotals) ? props.card.data.topTotals : []

  // Merge allContacts and topTotals, deduplicate by username
  const seen = new Set()
  const out = []

  for (const x of [...allContacts, ...topTotals]) {
    if (x && typeof x === 'object' && typeof x.displayName === 'string' && !seen.has(x.username)) {
      seen.add(x.username)
      out.push(x)
    }
  }

  // Ensure bestBuddy is in candidate pool
  if (bestBuddy.value && !seen.has(bestBuddy.value.username)) {
    out.unshift(bestBuddy.value)
  }

  return out
})

const shownDisplayName = computed(() => {
  if (phase.value === 'idle') return '点击按钮揭晓'
  const o = shownUser.value
  const name = String(o?.displayName || o?.maskedName || '').trim()
  return name || '…'
})

const shownAvatarUrl = computed(() => {
  const o = shownUser.value
  if (!o) return ''
  return resolveMediaUrl(o.avatarUrl)
})

const shownAvatarFallback = computed(() => (
  phase.value === 'idle' ? '?' : avatarFallback(shownDisplayName.value)
))
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
  if (typingTimer) clearTimeout(typingTimer)
  typingTimer = null
  if (dockTimer) clearTimeout(dockTimer)
  dockTimer = null
  if (chartTimer) clearTimeout(chartTimer)
  chartTimer = null
  if (badgeTimer) clearTimeout(badgeTimer)
  badgeTimer = null
  lotteryPausedAt = null
}

const leftRailClass = computed(() => {
  const shouldCenter = phase.value !== 'revealed' || !leftDocked.value
  return [
    'ease-[cubic-bezier(0.22,1,0.36,1)]',
    shouldCenter ? 'lg:translate-x-1/2' : ''
  ]
})

const lotteryTick = () => {
  const now = performance.now()
  const elapsed = now - lotteryStartedAt
  const t = Math.max(0, Math.min(1, elapsed / lotteryDurationMs))

  const prev = String(shownUser.value?.username || '')
  let next = pickRandomCandidate(prev)
  const target = bestBuddy.value
  // Near the end, gradually "stick" to the final result to create a smooth slow-stop feeling.
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

  // Ease-out: slow down near the end to build suspense.
  const minDelay = 60
  const maxDelay = 220
  const easeOutCubic = 1 - Math.pow(1 - t, 3)
  const delay = Math.round(minDelay + (maxDelay - minDelay) * easeOutCubic)
  lotteryTimer = setTimeout(lotteryTick, delay)
}

const startLottery = () => {
  clearTimers()
  resetAvatarOk()
  shownAvatarOk.value = true
  leftDocked.value = false
  showChart.value = false
  badgesFlipped.value = false
  lotterySnapping = false

  phase.value = 'rolling'
  typingReset()
  raceReset()

  if (reducedMotion.value) {
    // 减少动态效果：跳过悬念滚动，直接揭晓。
    finishReveal()
    return
  }

  lotteryStartedAt = performance.now()
  lotteryTick()
}

// 滚动期间点击跳过：清掉剩余定时器链，直接播放最后 600ms 吸附段。
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
    // 前两跳继续随机换人，第三跳落到最终结果，制造“吸附”手感。
    const next = hop === 3 && target ? target : pickRandomCandidate(String(shownUser.value?.username || ''))
    if (next) {
      shownUser.value = next
      shownAvatarOk.value = true
    }
    lotteryTimer = setTimeout(snap, 200)
  }
  snap()
}

const finishReveal = () => {
  clearTimers()
  lotterySnapping = false
  phase.value = 'revealed'
  shownUser.value = bestBuddy.value || shownUser.value
  shownAvatarOk.value = true

  // Start the narrative right away; dock left, then show the chart.
  startTypewriter()

  if (reducedMotion.value) {
    leftDocked.value = true
    showChart.value = true
    badgesFlipped.value = true
    playSpeedBar()
    startRace()
    return
  }

  leftDocked.value = false
  showChart.value = false
  badgesFlipped.value = false

  const settleMs = 240
  const slideMs = 520
  dockTimer = setTimeout(() => { leftDocked.value = true }, settleMs)
  badgeTimer = setTimeout(() => {
    badgesFlipped.value = true
    playSpeedBar()
  }, settleMs + 200)
  chartTimer = setTimeout(() => {
    showChart.value = true
    startRace()
  }, settleMs + slideMs)
}

const restart = () => {
  // Keep UX simple: replay the same reveal, but still run the suspense animation.
  startLottery()
}

// ---------------- Typewriter narrative ----------------
const typedSegIdx = ref(0)
const typedCharIdx = ref(0)
const typingActive = ref(false)

const formatDuration = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  if (!Number.isFinite(s) || s <= 0) return '0秒'
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

const segments = computed(() => {
  const buddy = bestBuddy.value
  if (!buddy) return []

  const outMsg = Number(buddy.outgoingMessages || 0)
  const inMsg = Number(buddy.incomingMessages || 0)
  const replyCount = Number(buddy.replyCount || 0)
  const avgReply = Math.round(Number(buddy.avgReplySeconds || 0))
  const fastest = fastestReplySeconds.value
  const longest = longestReplySeconds.value

  const segs = [
    { type: 'text', text: '今年你总共给 ' },
    { type: 'num', text: formatInt(sentToContacts.value) },
    { type: 'text', text: ' 人发送过消息，其中给 ' },
    { type: 'buddy' },
    { type: 'text', text: ' 发送了 ' },
    { type: 'num', text: formatInt(outMsg) },
    { type: 'text', text: ' 条消息，收到了 ' },
    { type: 'num', text: formatInt(inMsg) },
    { type: 'text', text: ' 条消息。' },
    { type: 'text', text: '你们之间统计到 ' },
    { type: 'num', text: formatInt(replyCount) },
    { type: 'text', text: ' 次回复，平均每条回复用时 ' },
    { type: 'num', text: formatDuration(avgReply) },
    { type: 'text', text: '。' }
  ]

  if (fastest != null) {
    segs.push({ type: 'text', text: '今年你最快一次只用了 ' })
    segs.push({ type: 'num', text: formatDuration(fastest) })
    segs.push({ type: 'text', text: ' 就回了' })
    if (fastestContact.value) {
      segs.push({ type: 'contact', contact: fastestContact.value })
    }
    segs.push({ type: 'text', text: '的消息；' })
  }
  if (longest != null) {
    segs.push({ type: 'text', text: '最长一次让' })
    if (slowestContact.value) {
      segs.push({ type: 'contact', contact: slowestContact.value })
    } else {
      segs.push({ type: 'text', text: '对方' })
    }
    segs.push({ type: 'text', text: '等了 ' })
    segs.push({ type: 'num', text: formatDuration(longest) })
    segs.push({ type: 'text', text: '。' })
  }
  return segs
})

const typingReset = () => {
  typedSegIdx.value = 0
  typedCharIdx.value = 0
  typingActive.value = false
}

const isSegVisible = (i) => {
  const segType = segments.value[i]?.type
  return i < typedSegIdx.value || (i === typedSegIdx.value && (segType === 'buddy' || segType === 'contact'))
}

const segTextShown = (i) => {
  const seg = segments.value[i]
  if (!seg || seg.type === 'buddy') return ''

  if (i < typedSegIdx.value) return String(seg.text || '')
  if (i > typedSegIdx.value) return ''
  return String(seg.text || '').slice(0, Math.max(0, typedCharIdx.value))
}

const startTypewriter = () => {
  typingReset()

  if (reducedMotion.value) {
    // 减少动态效果：直接完整呈现文案。
    typedSegIdx.value = segments.value.length
    return
  }

  typingActive.value = true

  const charDelay = 26
  const segPause = 140

  const step = () => {
    const seg = segments.value[typedSegIdx.value]
    if (!seg) {
      typingActive.value = false
      typingTimer = null
      return
    }

    if (seg.type === 'buddy') {
      // Show the buddy tag as a whole, then continue.
      typedSegIdx.value += 1
      typedCharIdx.value = 0
      typingTimer = setTimeout(step, segPause)
      return
    }

    const txt = String(seg.text || '')
    typedCharIdx.value += 1
    if (typedCharIdx.value >= txt.length) {
      typedSegIdx.value += 1
      typedCharIdx.value = 0
      typingTimer = setTimeout(step, segPause)
      return
    }

    typingTimer = setTimeout(step, charDelay)
  }

  step()
}

// ---------------- Bar race（gsap.ticker 按 elapsed 插值，后台标签页不漂移） ----------------
const MS_PER_DAY = 100 // 1x 速度下 0.1 秒/天

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
  // Pre-resolve avatar URLs once to avoid doing it in tight animation loops.
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

      // Backward compatibility for old caches: split total curve using final in/out ratio.
      if (cumulativeCounts.length > 0 && (cumulativeOutgoingCounts.length === 0 || cumulativeIncomingCounts.length === 0)) {
        const splitBase = outgoingMessages + incomingMessages
        const outgoingRatio = splitBase > 0 ? outgoingMessages / splitBase : 0
        cumulativeOutgoingCounts = cumulativeCounts.map((v) => Math.max(0, Math.round((Number(v) || 0) * outgoingRatio)))
        cumulativeIncomingCounts = cumulativeCounts.map((v, i) => (
          Math.max(0, (Number(v) || 0) - Number(cumulativeOutgoingCounts[i] || 0))
        ))
      }

      return {
        username,
        displayName: String(x.displayName || x.maskedName || ''),
        avatarUrl: resolveMediaUrl(x.avatarUrl),
        cumulativeCounts,
        cumulativeOutgoingCounts,
        cumulativeIncomingCounts
      }
    })
})

const racePlaying = ref(false)
const raceSpeed = ref(1) // 1x / 2x
const raceStarted = ref(false)
const raceDay = ref(0)
const raceItems = shallowRef([])

let raceElapsedMs = 0
let raceLastTickAt = 0
let raceTickerOn = false
// 预排序的 series 下标（按当前值降序）；累计值单调递增，仅相邻位次逆序时才重排。
let raceOrder = null

const raceFinished = computed(() => raceStarted.value && raceDays.value > 0 && raceDay.value >= raceDays.value)

const pad2 = (n) => String(n).padStart(2, '0')
const raceDate = computed(() => {
  const y = Number(race.value?.year || props.card?.data?.year || new Date().getFullYear())
  const step = Math.max(0, Math.min(Math.max(0, raceDays.value), Number(raceDay.value || 0)))
  if (step <= 0) return `${y} 开局`
  const d = Math.max(0, Math.min(Math.max(0, raceDays.value - 1), step - 1))
  const dt = new Date(y, 0, 1 + d)
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`
})

const raceValueAt = (arr, step) => {
  if (step <= 0 || !Array.isArray(arr) || arr.length === 0) return 0
  return Math.max(0, Number(arr[Math.min(step, arr.length) - 1] || 0))
}

const updateRaceFrame = (step) => {
  const list = raceSeries.value
  const n = list.length
  if (!n) {
    raceItems.value = []
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
  const maxV = Math.max(1, values[raceOrder[0]] || 0)
  for (let k = 0; k < raceOrder.length && items.length < 10; k += 1) {
    const i = raceOrder[k]
    const value = values[i]
    if (value <= 0) break // 降序排列，后面全是 0
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
      splitTotal = outgoingV + incomingV
    }

    const outgoingPartPct = splitTotal > 0
      ? Math.max(0, Math.min(100, Math.round((outgoingV / splitTotal) * 100)))
      : 0

    items.push({
      username: s.username,
      displayName: s.displayName,
      avatarUrl: s.avatarUrl,
      rank: items.length + 1,
      value,
      pct: Math.max(0, Math.min(100, Math.round((value / maxV) * 100))),
      outgoingPartPct,
      incomingPartPct: splitTotal > 0 ? 100 - outgoingPartPct : 0
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
  if (!race.value || raceDays.value <= 0 || raceSeries.value.length === 0) return
  stopRaceTicker()
  raceStarted.value = true
  raceOrder = null
  raceElapsedMs = 0

  if (reducedMotion.value) {
    // 减少动态效果：直接呈现终局排行。
    racePlaying.value = false
    setRaceStep(raceDays.value)
    return
  }

  setRaceStep(0)
  racePlaying.value = true
  if (props.isActive) startRaceTicker()
}

const toggleRacePlay = () => {
  if (raceFinished.value) {
    // 重播
    raceElapsedMs = 0
    setRaceStep(0)
    racePlaying.value = true
    if (props.isActive) startRaceTicker()
    return
  }
  racePlaying.value = !racePlaying.value
  if (racePlaying.value) {
    if (props.isActive) startRaceTicker()
  } else {
    stopRaceTicker()
  }
}

const toggleRaceSpeed = () => {
  raceSpeed.value = raceSpeed.value === 1 ? 2 : 1
}

const onRaceScrub = (e) => {
  const v = Math.max(0, Math.min(raceDays.value, Math.round(Number(e?.target?.value) || 0)))
  raceElapsedMs = v * MS_PER_DAY
  setRaceStep(v)
}

// ---------------- 「谁先开口」入场动画 ----------------
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

const GAUGE_LEN = 157.1 // 半环弧长（r=50 的半圆，π·50）
const gaugeOffset = ref(GAUGE_LEN)
const initiativeEntered = ref(false)
const mutualProgress = ref(0)
const mutualMet = computed(() => mutualProgress.value >= 0.999)

let gaugeTween = null
let mutualTween = null
let speedBarTween = null

const { display: rateDisplay, play: playRateCount } = useCountUp(
  () => Number(initiativeRate.value ?? 0),
  { duration: 1.4, decimals: 1 }
)
const { display: convDisplay, play: playConvCount } = useCountUp(
  () => Number(initiative.value?.conversationCount || 0),
  { duration: 1.2 }
)
const { display: mutualSentDisplay, play: playMutualSent } = useCountUp(
  () => Number(mutualFriend.value?.sentCount || 0),
  { duration: 1.4, delay: 0.3 }
)
const { display: mutualRecvDisplay, play: playMutualRecv } = useCountUp(
  () => Number(mutualFriend.value?.receivedCount || 0),
  { duration: 1.4, delay: 0.3 }
)

const killIntroTweens = () => {
  if (gaugeTween) { gaugeTween.kill(); gaugeTween = null }
  if (mutualTween) { mutualTween.kill(); mutualTween = null }
  if (speedBarTween) { speedBarTween.kill(); speedBarTween = null }
}

const playInitiativeIntro = () => {
  initiativeEntered.value = true
  if (gaugeTween) { gaugeTween.kill(); gaugeTween = null }
  if (mutualTween) { mutualTween.kill(); mutualTween = null }

  const rate = Math.max(0, Math.min(100, Number(initiativeRate.value ?? 0)))
  const gaugeTarget = GAUGE_LEN * (1 - rate / 100)

  playRateCount()
  playConvCount()
  playMutualSent()
  playMutualRecv()

  if (reducedMotion.value) {
    gaugeOffset.value = gaugeTarget
    mutualProgress.value = 1
    return
  }

  gaugeOffset.value = GAUGE_LEN
  const g = { v: GAUGE_LEN }
  gaugeTween = gsap.to(g, {
    v: gaugeTarget,
    duration: 1.4,
    ease: 'power2.out',
    onUpdate: () => { gaugeOffset.value = g.v },
    onComplete: () => { gaugeTween = null }
  })

  mutualProgress.value = 0
  const m = { v: 0 }
  mutualTween = gsap.to(m, {
    v: 1,
    duration: 0.9,
    delay: 0.5,
    ease: 'power2.inOut',
    onUpdate: () => { mutualProgress.value = m.v },
    onComplete: () => { mutualTween = null }
  })
}

// ---------------- bestBuddy 徽章 + replyStats 速度条 ----------------
const badgesFlipped = ref(false)
const buddyBadges = computed(() => {
  const b = bestBuddy.value
  if (!b) return []
  const out = []
  const streak = Number(b.longestStreakDays)
  if (Number.isFinite(streak) && streak > 0) {
    out.push({ key: 'streak', label: '最长连聊', value: `${formatInt(streak)} 天` })
  }
  const peak = String(b.peakHourLabel || '').trim()
  if (peak) {
    out.push({ key: 'peak', label: '最常聊天时段', value: peak })
  }
  if (b.fastestReplySeconds != null) {
    out.push({ key: 'fastest', label: '你回 TA 最快', value: formatDuration(b.fastestReplySeconds) })
  }
  if (b.slowestReplySeconds != null) {
    out.push({ key: 'slowest', label: '你回 TA 最慢', value: formatDuration(b.slowestReplySeconds) })
  }
  return out
})

const speedBarProgress = ref(0)
const speedBarPct = computed(() => Math.max(0, Math.min(100, speedBarProgress.value * 100)))
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
  return Math.max(4, Math.min(96, (d.p50 / d.p90) * 100))
})

const playSpeedBar = () => {
  if (!replyStatsData.value) return
  if (speedBarTween) { speedBarTween.kill(); speedBarTween = null }
  if (reducedMotion.value) {
    speedBarProgress.value = 1
    return
  }
  speedBarProgress.value = 0
  const o = { v: 0 }
  speedBarTween = gsap.to(o, {
    v: 1,
    duration: 0.9,
    ease: 'power2.out',
    onUpdate: () => { speedBarProgress.value = o.v },
    onComplete: () => { speedBarTween = null }
  })
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

watch(
  () => props.isActive,
  (active) => {
    if (active) {
      if (!hasEntered.value) {
        hasEntered.value = true
        playInitiativeIntro()
      }
      resumeCardLoops()
    } else {
      pauseCardLoops()
    }
  },
  { immediate: true }
)

// Keep state stable when backend card updates (e.g., refresh/retry).
watch(
  () => props.card?.data,
  () => {
    clearTimers()
    killIntroTweens()
    resetAvatarOk()
    phase.value = 'idle'
    shownUser.value = null
    shownAvatarOk.value = true
    leftDocked.value = false
    showChart.value = false
    badgesFlipped.value = false
    lotterySnapping = false
    speedBarProgress.value = 0
    typingReset()
    raceReset()
    initiativeEntered.value = false
    gaugeOffset.value = GAUGE_LEN
    mutualProgress.value = 0
    if (hasEntered.value) nextTick(() => playInitiativeIntro())
  }
)

onBeforeUnmount(() => {
  clearTimers()
  stopRaceTicker()
  killIntroTweens()
})
</script>

<style scoped>
.type-caret {
  display: inline-block;
  width: 0.6ch;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.12em;
  background: rgba(7, 193, 96, 0.85);
  animation: caret-blink 1s steps(1) infinite;
}

@keyframes caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

/* deck 翻走本卡时暂停无限循环的 CSS 动画 */
.card-anim-paused .type-caret {
  animation-play-state: paused;
}

.chart-fade-enter-active,
.chart-fade-leave-active {
  transition: opacity 240ms ease, transform 240ms ease !important;
}
.chart-fade-enter-from,
.chart-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.reply-buddy-rail {
  /* DOS theme sets `transition: text-shadow ... !important` on `*` (global).
     Use an explicit transition here so the rail slide stays smooth in all themes. */
  transition: transform 500ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.race-scroll {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.race-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.race-move {
  transition: transform 350ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.race-bar-fill {
  transition: width 120ms linear !important;
}

.race-bar {
  transition: width 120ms linear !important;
}

.race-bar-outgoing {
  background: #07c160;
}

.race-bar-incoming {
  background: #f2aa00;
}

.race-ctrl {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  padding: 0.25rem 0.6rem;
  border-radius: 0.5rem;
  border: 1px solid rgba(7, 193, 96, 0.35);
  color: #07c160;
  font-size: 12px;
  line-height: 1.4;
  transition: background-color 150ms ease;
}

.race-ctrl:hover {
  background: rgba(7, 193, 96, 0.1);
}

.race-range {
  height: 4px;
  cursor: pointer;
}

/* 「谁先开口」双栏列表滑入（同 DOS 主题原因，transition 需 !important） */
.init-slide {
  opacity: 0;
  transform: translateX(-14px);
  transition: opacity 480ms ease, transform 480ms cubic-bezier(0.22, 1, 0.36, 1) !important;
  transition-delay: var(--slide-delay, 0ms) !important;
}

.init-slide.init-slide-right {
  transform: translateX(14px);
}

.init-entered .init-slide {
  opacity: 1;
  transform: translateX(0);
}

.init-reduced .init-slide {
  transition: none !important;
}

/* 势均力敌：两线中点汇合后小圆点弹出 */
.mutual-dot {
  transform-box: fill-box;
  transform-origin: center;
  transform: scale(0);
  transition: transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1) !important;
}

.mutual-dot.mutual-dot-met {
  transform: scale(1);
}

.init-reduced .mutual-dot {
  transition: none !important;
}

/* bestBuddy 徽章 3D 翻牌 */
.badge-flip {
  perspective: 640px;
}

.badge-inner {
  position: relative;
  transform-style: preserve-3d;
  transform: rotateY(180deg);
  transition: transform 520ms cubic-bezier(0.22, 1, 0.36, 1) !important;
  transition-delay: var(--flip-delay, 0ms) !important;
}

.badge-inner.badge-shown {
  transform: rotateY(0deg);
}

.badge-inner.badge-reduced {
  transition: none !important;
}

.badge-face {
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.badge-back {
  position: absolute;
  inset: 0;
  transform: rotateY(180deg);
  background: linear-gradient(135deg, rgba(7, 193, 96, 0.16), rgba(7, 193, 96, 0.04));
}

/* P50/P90 速度条标记 */
.speed-marker {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 2px;
  border-radius: 1px;
  background: rgba(0, 0, 0, 0.28);
  transform: translateX(-50%);
}

.speed-marker-label {
  position: absolute;
  top: 100%;
  left: 50%;
  margin-top: 4px;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: 10px;
  color: rgba(0, 0, 0, 0.45);
}

.speed-marker-end .speed-marker-label {
  transform: translateX(-90%);
}
</style>
