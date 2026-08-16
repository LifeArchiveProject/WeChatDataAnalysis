<template>
  <div ref="rootEl" class="tf-root" :class="{ 'tf-root--voice': showVoiceCalls }">
    <!-- 玻璃背后的柔光色斑：给 liquid glass 一点可折射的颜色 -->
    <div class="tf-glow" aria-hidden="true"></div>

    <!-- ============ A. 文字账本（hero）：卡片标题拆进来当第一句话 ============ -->
    <section class="tf-hero">
      <h2 class="tf-q1 wrapped-title">{{ titleQ1 }}</h2>

      <div class="tf-big" aria-label="全年发送字数">
        <WrappedOdometer class="tf-big-num wrapped-number" :value="sentChars" :play="odoPlay" :duration="odoDuration" :stagger="odoStagger" ink />
        <span class="tf-big-unit">字</span>
      </div>

      <p class="tf-sent-cap wrapped-body">
        <template v-if="sentChars > 0">每一个，都是你亲手敲出来、想说给某个人听的。</template>
        <template v-else>今年还没有发出文字消息——键盘在等你。</template>
      </p>

      <!-- 第二问「够写一本书吗？」——用换算结果直接作答 -->
      <div v-if="sentBookText" class="tf-ask">
        <span class="tf-q2 wrapped-label">{{ titleQ2 }}</span>
        <span class="tf-bookline">{{ sentBookText }}</span>
      </div>

      <!-- 向你走来的字：一行元数据（对象在下方桌面上） -->
      <div v-if="receivedChars > 0" class="tf-meta">
        <span class="tf-meta-label wrapped-label">向你走来的字</span>
        <span class="tf-meta-num wrapped-number">{{ formatInt(receivedChars) }}</span>
        <span class="tf-meta-unit">字</span>
        <i class="tf-meta-sep" aria-hidden="true"></i>
        <span class="tf-meta-item">约 <b class="wrapped-number">{{ formatInt(a4Sheets) }}</b> 张 A4</span>
        <template v-if="a4HeightCm > 0">
          <i class="tf-meta-sep" aria-hidden="true"></i>
          <span class="tf-meta-item">
            堆起来 ≈ <b class="wrapped-number">{{ a4HeightDisplay }}</b> {{ a4HeightUnit }}<template v-if="a4ObjectText">，{{ a4ObjectText }}的高度</template>
          </span>
        </template>
      </div>
      <div v-else class="tf-meta tf-meta--empty">今年还没有收到文字消息。</div>
    </section>

    <!-- ============ A2. 桌面左手边：一本书 + 一摞纸 ============ -->
    <section v-if="sentChars > 0 || (receivedChars > 0 && a4HeightCm > 0)" class="tf-objs">
      <div
        v-if="sentChars > 0"
        ref="bookEl"
        class="book"
        :style="{ '--bt': `${bookThicknessPx}px` }"
        @pointermove="onBookPointerMove"
        @pointerleave="onBookPointerLeave"
      >
        <div class="book-shadow" aria-hidden="true"></div>
        <div ref="book3dEl" class="book-3d">
          <div class="book-face book-cover">
            <span class="book-frame" aria-hidden="true"></span>
            <svg class="book-emblem" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="10.4" fill="none" stroke="#DDBE7E" stroke-width="1.1" opacity="0.85" />
              <circle cx="12" cy="12" r="8.6" fill="none" stroke="#A98753" stroke-width="0.5" opacity="0.6" />
              <path
                d="M12 6.6c-3.2 0-5.7 2.1-5.7 4.7 0 1.5.83 2.8 2.1 3.66l-.5 1.9 2.2-1.2c.6.15 1.24.24 1.9.24 3.2 0 5.7-2.1 5.7-4.7s-2.5-4.6-5.7-4.6z"
                fill="#DDBE7E"
                opacity="0.9"
              />
            </svg>
            <span class="book-title">你说过的话</span>
            <span class="book-year wrapped-number">{{ yearText }}</span>
            <span class="book-author">著者 · 你</span>
            <span class="book-imprint">微信铸字车间 印行</span>
            <span ref="bookGlossEl" class="book-gloss" aria-hidden="true"></span>
          </div>
          <div class="book-face book-pages" aria-hidden="true"></div>
          <div class="book-face book-top" aria-hidden="true"></div>
          <div class="book-face book-spine" aria-hidden="true"></div>
          <div class="book-ribbon" aria-hidden="true"></div>
        </div>
        <div class="book-cap wrapped-label">{{ yearText }} 年初版 · 印数一册</div>
      </div>

      <!-- 收到的字打印出来就是这一摞 -->
      <div v-if="receivedChars > 0 && a4HeightCm > 0" class="ream" :style="{ '--rh': `${reamPx}px` }">
        <div ref="reamStackEl" class="ream-stack">
          <div class="ream-side"></div>
          <div class="ream-sheet ream-sheet--b" aria-hidden="true"></div>
          <div class="ream-sheet ream-sheet--a" aria-hidden="true"></div>
        </div>
        <div class="ream-cap wrapped-label">{{ formatInt(a4Sheets) }} 张 A4</div>
      </div>
    </section>

    <!-- ============ B. 说给你听：语音与通话（旧缓存无 voice/calls 字段时整区隐藏） ============ -->
    <div v-if="showVoiceCalls" class="voice-section">
      <div class="voice-header">
        <span class="voice-title wrapped-label">说给你听</span>
        <span class="voice-rule" aria-hidden="true"></span>
        <span class="voice-sub wrapped-label">语音与通话</span>
      </div>

      <!-- 一台「微信留言机」：这一年的语音与通话都住在这台桌面设备里 -->
      <div class="am" :class="{ 'am--paused': wavePaused, 'am--fast': amFast }">
        <div class="am-head">
          <span class="am-brand wrapped-label">微信留言机 · ANSWERING MACHINE</span>
          <i class="am-led" :class="{ 'am-led--on': amRecLed }" aria-hidden="true"></i>
          <i class="am-grille" aria-hidden="true"></i>
        </div>

        <!-- 液晶屏：通话账目 -->
        <div v-if="hasCalls" class="am-lcd">
          <div class="am-lcd-glass" aria-hidden="true"></div>
          <div class="am-lcd-row1">
            <span class="am-lcd-label wrapped-label">通话总时长</span>
            <span class="am-lcd-time wrapped-number">{{ callsDurationText }}</span>
          </div>
          <div class="am-lcd-row2 wrapped-number">
            <span>{{ formatInt(callsTotalCount) }} 通</span>
            <i aria-hidden="true"></i>
            <span>接通 {{ formatInt(callsConnectedCount) }}</span>
            <template v-if="callsMissedCount > 0">
              <i aria-hidden="true"></i>
              <span class="am-lcd-missed">未接 {{ formatInt(callsMissedCount) }}</span>
            </template>
          </div>
          <div v-if="callsVideoCount > 0 || callsVoiceCount > 0" class="am-lcd-row3">
            <span v-if="callsVideoCount > 0" class="am-kind">
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 3.5v-10l-4 3.5z" />
              </svg>
              视频 ×{{ formatInt(callsVideoCount) }}
            </span>
            <span v-if="callsVoiceCount > 0" class="am-kind">
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.21a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.61 21 3 13.39 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z" />
              </svg>
              语音 ×{{ formatInt(callsVoiceCount) }}
            </span>
          </div>
        </div>

        <!-- 磁带舱：一年的留言 -->
        <div v-if="hasVoice" class="am-tapebay">
          <div class="am-sides">
            <div class="am-side">
              <span class="am-side-tag wrapped-label">A面 · 你说的</span>
              <span v-if="voiceSentSeconds > 0" class="am-side-val wrapped-number">
                {{ voiceMainNumber }} {{ voiceMainUnit }} · {{ formatInt(voiceSentCount) }} 条
              </span>
              <span v-else class="am-side-val am-side-val--dim">今年你更多在听</span>
            </div>
            <i class="am-sides-rule" aria-hidden="true"></i>
            <div class="am-side">
              <span class="am-side-tag wrapped-label">B面 · 你听的</span>
              <span v-if="voiceReceivedCount > 0" class="am-side-val wrapped-number">
                {{ formatDurationShort(voiceReceivedSeconds) }} · {{ formatInt(voiceReceivedCount) }} 条
              </span>
              <span v-else class="am-side-val am-side-val--dim">还没有收到语音</span>
            </div>
          </div>
          <div class="am-window">
            <div class="tape-reel" :style="{ '--pack': sentPack }">
              <i class="tape-pack" aria-hidden="true"></i>
              <i class="tape-hub" aria-hidden="true"></i>
            </div>
            <div class="tape-band" aria-hidden="true"></div>
            <div class="tape-reel" :style="{ '--pack': recvPack }">
              <i class="tape-pack" aria-hidden="true"></i>
              <i class="tape-hub" aria-hidden="true"></i>
            </div>
          </div>
          <div class="am-strip">
            <span v-if="voiceSentSeconds > 0" class="am-strip-note wrapped-label">{{ voiceAnalogyText }}</span>
            <span v-if="longestVoice" class="am-strip-longest wrapped-label">
              最长一条 · {{ longestIsSent ? '发给' : '来自' }}
              <b class="wrapped-privacy-name">{{ longestVoiceName || '神秘好友' }}</b>
              · {{ longestSecondsText }}<template v-if="longestDateText"> · {{ longestDateText }}</template>
            </span>
          </div>
        </div>

        <!-- 走带键：可以按 -->
        <div class="am-controls" v-if="hasVoice">
          <button class="am-btn" type="button" aria-label="倒带" @pointerdown="amPress($event, 'rew')">
            <svg viewBox="0 0 14 8" fill="currentColor" aria-hidden="true"><path d="M7 0 1 4l6 4zM13 0 7 4l6 4z" /></svg>
          </button>
          <button class="am-btn" type="button" aria-label="播放" @pointerdown="amPress($event, 'play')">
            <svg viewBox="0 0 8 8" fill="currentColor" aria-hidden="true"><path d="M1 0l6 4-6 4z" /></svg>
          </button>
          <button class="am-btn" type="button" aria-label="快进" @pointerdown="amPress($event, 'ff')">
            <svg viewBox="0 0 14 8" fill="currentColor" aria-hidden="true"><path d="M1 0l6 4-6 4zM7 0l6 4-6 4z" /></svg>
          </button>
          <button class="am-btn am-btn--rec" type="button" aria-label="录音" @pointerdown="amPress($event, 'rec')">
            <svg viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3" fill="currentColor" /></svg>
          </button>
          <span class="am-controls-note wrapped-label">REW / PLAY / FF / REC</span>
        </div>

        <!-- 单键拨号：常联络的人压在相框位里 -->
        <div v-if="callsTopPartnerName || topSentPartnerName || topReceivedPartnerName" class="am-dial">
          <span class="am-dial-tag wrapped-label">单键拨号</span>
          <div class="am-dial-slots">
            <div v-if="callsTopPartnerName" class="am-slot">
              <span class="am-frame">
                <span class="v-avatar wrapped-privacy-avatar">
                  <img
                    v-if="callsTopAvatarUrl && callsTopAvatarOk"
                    :src="callsTopAvatarUrl"
                    :alt="callsTopPartnerName"
                    @error="callsTopAvatarOk = false"
                  />
                  <span v-else class="v-avatar__fb wrapped-number">{{ callsTopPartnerName[0] }}</span>
                </span>
              </span>
              <span class="am-slot-role wrapped-label">最常连线</span>
              <span class="am-slot-name wrapped-privacy-name">{{ callsTopPartnerName }}</span>
              <span v-if="callsTopPartnerCount > 0" class="am-slot-note wrapped-label">
                {{ formatInt(callsTopPartnerCount) }} 次<template v-if="callsTopPartnerDurText"> · {{ callsTopPartnerDurText }}</template>
              </span>
            </div>
            <div v-if="topSentPartnerName" class="am-slot">
              <span class="am-frame">
                <span class="v-avatar wrapped-privacy-avatar">
                  <img
                    v-if="topSentAvatarUrl && topSentAvatarOk"
                    :src="topSentAvatarUrl"
                    :alt="topSentPartnerName"
                    @error="topSentAvatarOk = false"
                  />
                  <span v-else class="v-avatar__fb wrapped-number">{{ topSentPartnerName[0] }}</span>
                </span>
              </span>
              <span class="am-slot-role wrapped-label">最常说给他听</span>
              <span class="am-slot-name wrapped-privacy-name">{{ topSentPartnerName }}</span>
            </div>
            <div v-if="topReceivedPartnerName" class="am-slot">
              <span class="am-frame">
                <span class="v-avatar wrapped-privacy-avatar">
                  <img
                    v-if="topReceivedAvatarUrl && topReceivedAvatarOk"
                    :src="topReceivedAvatarUrl"
                    :alt="topReceivedPartnerName"
                    @error="topReceivedAvatarOk = false"
                  />
                  <span v-else class="v-avatar__fb wrapped-number">{{ topReceivedPartnerName[0] }}</span>
                </span>
              </span>
              <span class="am-slot-role wrapped-label">最常听他说</span>
              <span class="am-slot-name wrapped-privacy-name">{{ topReceivedPartnerName }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ C. 键盘舞台 ============ -->
    <section class="tf-kb">
      <div class="kb-stage">
        <!-- 输入法候选条：一块液态玻璃，敲击在左边变成拼音，字数在右边滚动 -->
        <div ref="imeEl" class="ime-bar">
          <div class="ime-left">
            <span class="ime-caret" aria-hidden="true"></span>
            <span class="ime-py wrapped-number wrapped-privacy-message">{{ imePinyin }}</span>
            <transition name="cand">
              <div v-if="imeCands.length" class="ime-cands">
                <span
                  v-for="(c, i) in imeCands"
                  :key="`${c}-${i}`"
                  class="ime-cand wrapped-privacy-message"
                  :class="{ 'ime-cand--first': i === 0 }"
                ><i class="ime-cand-no wrapped-number">{{ i + 1 }}</i>{{ c }}</span>
              </div>
            </transition>
          </div>
          <div ref="hitsEl" class="ime-hits" aria-label="全年敲击次数">
            <WrappedOdometer class="ime-hits-num wrapped-number" :value="totalKeyHits" :play="odoPlay" :duration="odoDurationHits" :stagger="odoStagger" />
            <span class="ime-hits-unit wrapped-label">次敲击</span>
          </div>
        </div>

        <!-- 键盘主体：铝壳 + 可按压键帽（磨损即数据） -->
        <div ref="keyboardBodyEl" class="keyboard-body">
          <div v-for="(row, ri) in keyboardRows" :key="ri" :ref="(el) => setRowEl(el, ri)" class="kb-row">
            <div
              v-for="(key, ci) in row"
              :key="`${ri}-${ci}`"
              class="kb-key"
              :class="[`kb-w-${key.w || 1}`, { 'kb-space': key.isSpace, 'kb-func': key.isFunc }, getKeyClasses(key.code)]"
              :style="getKeyStyle(key.code)"
              :ref="(el) => setKeyEl(el, key.code)"
              @mouseenter="showKeyTip($event, key)"
              @mouseleave="hideKeyTip"
              @pointerdown="onKeyPointerDown($event, key)"
              @pointerup="hideKeyTipTouch"
              @pointercancel="hideKeyTipTouch"
            >
              <div class="kb-key-top">
                <span v-if="key.sub" class="kb-sub">{{ key.sub }}</span>
                <span v-if="key.label" class="kb-label" :class="{ 'kb-label-sm': key.isFunc }">{{ key.label }}</span>
                <div v-if="key.isSpace" class="kb-space-bar"></div>
              </div>
            </div>
          </div>

          <!-- 单键 HUD：玻璃小卡 -->
          <div v-if="keyTooltip" class="kb-hud" :style="{ left: `${keyTooltip.x}px`, top: `${keyTooltip.y}px` }">
            <div class="kb-hud-title">{{ keyTooltip.title }}</div>
            <div v-if="keyTooltip.meta" class="kb-hud-meta">{{ keyTooltip.meta }}</div>
          </div>

          <div class="keyboard-brand">微信机械键盘 · 手工敲字一年</div>
        </div>

        <!-- 底部：磨损注脚 + 年度键位领奖台 -->
        <div class="kb-foot">
          <div class="kb-note wrapped-label">答案都在这块键盘上——它替你记着每一次敲击 · 键帽的磨损就是证据 · 悬停单键可查明细</div>
          <div v-if="topWornKeys.length" class="podium">
            <div v-for="(k, i) in topWornKeys" :key="k.code" class="pd-item">
              <!-- 奖杯是复刻的新键帽：磨损留在键盘上，荣誉抛光后上台 -->
              <div class="kb-key pd-key" :class="{ 'pd-key--space': k.code === 'space' }">
                <div class="kb-key-top">
                  <div v-if="k.code === 'space'" class="kb-space-bar"></div>
                  <span v-else class="kb-label">{{ podiumLabel(k) }}</span>
                </div>
                <i class="pd-medal" :class="`pd-medal--${i}`"><b class="wrapped-number">{{ i + 1 }}</b></i>
              </div>
              <div class="pd-cap">
                <span class="pd-name">{{ k.name }}</span>
                <span class="pd-hits wrapped-label">{{ formatInt(k.hits) }} 次</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 粒子层：飞出的字母与入册的词 -->
    <div ref="fxEl" class="tf-fx" aria-hidden="true"></div>
  </div>
</template>

<script setup>
import { usePrivacyText } from '~/composables/usePrivacyText'
const { privacyMode } = usePrivacyText()
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useCountUp } from '~/composables/useCountUp'
import WrappedOdometer from '~/components/wrapped/shared/WrappedOdometer.vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  // 卡片标题（「你今年打了多少字？够写一本书吗？」）：拆成两问融进版面
  title: { type: String, default: '' },
  // deck 翻到本卡时置 true，首次为 true 触发入场编排；false 时暂停循环动画。
  isActive: { type: Boolean, default: true }
})

// 标题按问号拆两句；格式对不上时整句放在第一行兜底
const titleParts = computed(() => {
  const t = String(props.title || '').trim()
  const parts = t.split('？').map((x) => x.trim()).filter(Boolean)
  if (parts.length >= 2) return [`${parts[0]}？`, `${parts[1]}？`]
  return [t || '你今年打了多少字？', '够写一本书吗？']
})
const titleQ1 = computed(() => titleParts.value[0])
const titleQ2 = computed(() => titleParts.value[1])

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const reducedMotion = useReducedMotion()

/* 导出模式（页面级 provide）。为真期间这一页必须**立刻**是终态：
   大数滚完、书装订好、纸摞长齐、键帽磨损显影到位，而不是还在 2.4s 的入场编排里。
   为假时行为与导出功能存在之前一字不差。 */
const exportMode = inject('wrappedExportMode', ref(false))
// 里程表的滚轮时长：导出时置 0，读数在第一帧就落到目标位（stagger 同理）
const odoDuration = computed(() => (exportMode.value ? 0 : 1.5))
const odoDurationHits = computed(() => (exportMode.value ? 0 : 1.7))
const odoStagger = computed(() => (exportMode.value ? 0 : 0.055))

const sentChars = computed(() => Number(props.data?.sentChars || 0))
const receivedChars = computed(() => Number(props.data?.receivedChars || 0))
const yearText = computed(() => String(props.data?.year || new Date().getFullYear()))

const sentBookText = computed(() => props.data?.sentBook?.text || '')
const receivedA4 = computed(() => props.data?.receivedA4 || null)

// 大数滚轮统一开关：入场编排推到 true，翻走重置
const odoPlay = ref(false)

// ========== 书：厚度按字数装订 ==========

// 12px 起步，500 万字触顶 46px（对数刻度，几千字也能看出厚度）
const bookThicknessPx = computed(() => {
  const n = sentChars.value
  if (n <= 0) return 12
  return Math.round(12 + Math.min(1, Math.log1p(n) / Math.log1p(5_000_000)) * 34)
})

// ========== A4 纸摞 + 刻度尺 ==========

const a4Sheets = computed(() => Number(receivedA4.value?.a4?.sheets ?? 0))
const a4HeightCm = computed(() => Number(receivedA4.value?.a4?.heightCm ?? receivedA4.value?.heightCm ?? 0))
const a4ObjectText = computed(() => String(receivedA4.value?.object || '').trim())
const a4UseMeters = computed(() => a4HeightCm.value >= 100)
const a4HeightValue = computed(() => (a4UseMeters.value ? a4HeightCm.value / 100 : a4HeightCm.value))
const a4HeightUnit = computed(() => (a4UseMeters.value ? '米' : '厘米'))
// 对数刻度：几厘米到几十米都能看出高度差异
const reamPx = computed(() => {
  const cm = a4HeightCm.value
  if (cm <= 0) return 0
  return Math.round(14 + Math.min(1, Math.log1p(cm) / Math.log1p(500)) * 84)
})
const {
  display: a4HeightDisplay,
  value: a4HeightCurrent,
  play: playA4Height,
  finish: finishA4Height
} = useCountUp(
  () => a4HeightValue.value,
  { duration: 1.0, decimals: 1 }
)

// ========== 「说给你听」：voice / calls（字段缺失时整区隐藏） ==========

const voice = computed(() => (props.data?.voice && typeof props.data.voice === 'object' ? props.data.voice : null))
const calls = computed(() => (props.data?.calls && typeof props.data.calls === 'object' ? props.data.calls : null))

const voiceSentCount = computed(() => Number(voice.value?.sentCount || 0))
const voiceSentSeconds = computed(() => Number(voice.value?.sentSeconds || 0))
const voiceReceivedCount = computed(() => Number(voice.value?.receivedCount || 0))
const voiceReceivedSeconds = computed(() => Number(voice.value?.receivedSeconds || 0))

const hasVoice = computed(() =>
  voiceSentCount.value + voiceSentSeconds.value + voiceReceivedCount.value + voiceReceivedSeconds.value > 0
)
const hasCalls = computed(() => {
  const c = calls.value
  if (!c) return false
  return Number(c.totalCount || 0) > 0 || Number(c.totalSeconds || 0) > 0
})
const showVoiceCalls = computed(() => hasVoice.value || hasCalls.value)

// 大数字：满 1 分钟按分钟展示，否则按秒
const voiceMainIsMinutes = computed(() => voiceSentSeconds.value >= 60)
const voiceMainNumber = computed(() =>
  voiceMainIsMinutes.value ? Math.round(voiceSentSeconds.value / 60) : Math.round(voiceSentSeconds.value)
)
const voiceMainUnit = computed(() => (voiceMainIsMinutes.value ? '分钟' : '秒'))

// 磁带两只轮盘的带量：按说/听时长占比分配（0-1，钳在 0.12-0.88 保证都看得见）
const sentPack = computed(() => {
  const a = voiceSentSeconds.value
  const b = voiceReceivedSeconds.value
  if (a + b <= 0) return 0.35
  return Math.min(0.88, Math.max(0.12, a / (a + b)))
})
const recvPack = computed(() => 1 - sentPack.value)

const voiceAnalogyText = computed(() => {
  const m = voiceSentSeconds.value / 60
  if (m >= 110) {
    const n = Math.max(1, Math.round(m / 120))
    return n <= 1 ? '≈ 认认真真讲完一场电影' : `≈ ${n} 场电影的时长`
  }
  if (m >= 40) return `≈ ${Math.max(1, Math.round(m / 45))} 张专辑的时长`
  if (m >= 4) return `≈ ${Math.max(1, Math.round(m / 4))} 首歌的时长`
  return '每一秒都是心里话'
})

const formatDurationShort = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  if (s < 60) return `${s} 秒`
  return `${Math.round(s / 60)} 分钟`
}

const partnerName = (p) => String(p?.displayName || p?.maskedName || '').trim()
const topSentPartnerName = computed(() => partnerName(voice.value?.topSentPartner))
const topReceivedPartnerName = computed(() => partnerName(voice.value?.topReceivedPartner))

// 最长语音
const longestVoice = computed(() => {
  const l = voice.value?.longest
  if (!l || typeof l !== 'object') return null
  return Number(l.seconds || 0) > 0 ? l : null
})
const longestIsSent = computed(() => String(longestVoice.value?.direction || '') === 'sent')
const longestVoiceName = computed(() => partnerName(longestVoice.value))
const longestSecondsText = computed(() => `${Math.round(Number(longestVoice.value?.seconds || 0))}''`)
// 日期去掉年份（卡片本身就是年度的）：2025-08-30 → 08-30
const longestDateText = computed(() => {
  const d = String(longestVoice.value?.date || '').trim()
  return /^\d{4}-/.test(d) ? d.slice(5) : d
})

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
const longestAvatarUrl = computed(() => resolveMediaUrl(longestVoice.value?.avatarUrl))
const longestAvatarOk = ref(true)
watch(longestAvatarUrl, () => { longestAvatarOk.value = true })
const longestAvatarFallback = computed(() => {
  const s = longestVoiceName.value
  return s ? s[0] : '?'
})

// 语音双方 / 最常连线的人：头像
const topSentAvatarUrl = computed(() => resolveMediaUrl(voice.value?.topSentPartner?.avatarUrl))
const topSentAvatarOk = ref(true)
watch(topSentAvatarUrl, () => { topSentAvatarOk.value = true })

const topReceivedAvatarUrl = computed(() => resolveMediaUrl(voice.value?.topReceivedPartner?.avatarUrl))
const topReceivedAvatarOk = ref(true)
watch(topReceivedAvatarUrl, () => { topReceivedAvatarOk.value = true })

const callsTopAvatarUrl = computed(() => resolveMediaUrl(calls.value?.topPartner?.avatarUrl))
const callsTopAvatarOk = ref(true)
watch(callsTopAvatarUrl, () => { callsTopAvatarOk.value = true })

// 通话
const callsTotalCount = computed(() => Number(calls.value?.totalCount || 0))
const callsConnectedCount = computed(() => Number(calls.value?.connectedCount || 0))
const callsVideoCount = computed(() => Number(calls.value?.videoCount || 0))
const callsVoiceCount = computed(() => Number(calls.value?.voiceCount || 0))
const callsMissedCount = computed(() => Number(calls.value?.missedOrCanceledCount || 0))
const callsTopPartnerName = computed(() => partnerName(calls.value?.topPartner))
const callsTopPartnerCount = computed(() => Number(calls.value?.topPartner?.count || 0))

// 最常连线的人的累计时长：满 1 小时用「N 小时 M 分」，否则「N 分钟」
const callsTopPartnerDurText = computed(() => {
  const s = Math.max(0, Math.round(Number(calls.value?.topPartner?.seconds || 0)))
  if (s <= 0) return ''
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  if (h > 0) return `${h} 小时 ${m} 分`
  if (m > 0) return `${m} 分钟`
  return `${s} 秒`
})

// 液晶屏时长：有小时则 H:MM:SS，否则 MM:SS
const callsDurationText = computed(() => {
  const total = Math.max(0, Math.round(Number(calls.value?.totalSeconds || 0)))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
})

// ========== 留言机：走带键与指示灯 ==========

const amFast = ref(false)
const amRecLed = ref(false)
let amFastTimer = 0
let amLedTimer = 0

const amPress = (evt, kind) => {
  const el = evt?.currentTarget
  if (el) {
    el.classList.add('is-down')
    window.setTimeout(() => el.classList.remove('is-down'), 130)
  }
  if (kind === 'rec') {
    amRecLed.value = true
    if (amLedTimer) window.clearTimeout(amLedTimer)
    amLedTimer = window.setTimeout(() => { amRecLed.value = false; amLedTimer = 0 }, 900)
  } else {
    // 倒带/播放/快进都让轮盘转快一阵
    amFast.value = true
    if (amFastTimer) window.clearTimeout(amFastTimer)
    amFastTimer = window.setTimeout(() => { amFast.value = false; amFastTimer = 0 }, 1400)
  }
}

// 磁带轮盘转动：翻走本页或系统减弱动态时停转
const wavePaused = computed(() => !props.isActive || reducedMotion.value)

// ========== 键盘数据 ==========

// 从后端获取键盘统计数据
const keyboardData = computed(() => props.data?.keyboard || null)

// 总敲击次数（优先使用后端数据）
const totalKeyHits = computed(() => {
  // 注意：totalKeyHits 可能为 0（比如今年没发出文字消息），不能用 truthy 判断。
  const backend = Number(keyboardData.value?.totalKeyHits)
  if (Number.isFinite(backend)) return backend

  // 回退：粗略估算（仅基于"你发送的字"，假设拼音输入 + 一定比例空格）
  const letterHits = Math.round(sentChars.value * 2.8)
  return letterHits + Math.round(letterHits * 0.15)
})

// 获取各键的敲击次数（优先使用后端精确数据）
const keyHitsMap = computed(() => {
  const backendHits = keyboardData.value?.keyHits
  const backendSpace = Number(keyboardData.value?.spaceHits || 0)
  if (backendHits && typeof backendHits === 'object') {
    // 后端把空格次数单独放在 spaceHits，这里合并进 keyHitsMap 以便空格键也能显示磨损。
    return backendSpace > 0 ? { ...backendHits, space: backendSpace } : backendHits
  }

  // 回退：使用默认频率估算（仅基于"你发送的字"）
  const defaultFreq = {
    a: 0.121, i: 0.118, n: 0.098, e: 0.089, u: 0.082, g: 0.072, h: 0.065,
    o: 0.052, z: 0.048, s: 0.042, x: 0.038, y: 0.036, d: 0.032, l: 0.028,
    j: 0.026, b: 0.022, c: 0.020, w: 0.018, m: 0.016, f: 0.014, t: 0.012,
    r: 0.010, p: 0.009, k: 0.007, q: 0.005, v: 0.001,
  }
  const letterHits = Math.round(sentChars.value * 2.8)
  const spaceHits = Math.round(letterHits * 0.15)
  const result = {}
  for (const [k, freq] of Object.entries(defaultFreq)) {
    result[k] = Math.round(freq * letterHits)
  }
  if (spaceHits > 0) result.space = spaceHits
  return result
})

const maxKeyHits = computed(() => {
  const values = Object.values(keyHitsMap.value).map((v) => Number(v) || 0)
  return Math.max(...values, 1)
})

// 计算磨损程度（0-1），基于实际敲击次数
const getWear = (code) => {
  const k = code.toLowerCase()
  const hits = Number(keyHitsMap.value[k] || 0)
  if (!Number.isFinite(hits) || hits <= 0) return 0

  // 小数量级键（如数字/标点）容易"看起来没变化"，用对数缩放增强可视化差异。
  const ratio = Math.log1p(hits) / Math.log1p(maxKeyHits.value)
  return Math.min(1, Math.pow(ratio, 1.6))
}

// 磨损显影进度（0-1）：入场时由 gsap 从 0 推到 1，键帽从全新态过渡到目标磨损。
const wearReveal = ref(0)
// Level 8-10 的 clip-path 缺角/报废类在显影结束后统一切换，避免中途跳变。
const clipRevealed = ref(false)

const effectiveWear = (code) => getWear(code) * wearReveal.value

// ========== 10级磨损系统 ==========

// 磨损等级阈值
const LEVEL_THRESHOLDS = [0, 0.10, 0.20, 0.35, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]

// 获取磨损等级 (0-10)
const getWearLevel = (wear) => {
  if (wear === 0) return 0
  if (wear >= 1) return 10
  for (let i = 1; i < LEVEL_THRESHOLDS.length; i++) {
    if (wear <= LEVEL_THRESHOLDS[i]) return i
  }
  return 10
}

const LEVEL_NAMES = ['全新', '指纹油光', '涂层初磨', '涂层磨损', '涂层剥落', '表面凹陷', '细微裂纹', '网状龟裂', '缺角碎裂', '严重破损', '键帽报废']

// 获取当前等级内的进度 (0-1)，用于等级内平滑过渡
const getWearProgress = (wear) => {
  const level = getWearLevel(wear)
  if (level === 0 || level === 10) return 0
  const start = LEVEL_THRESHOLDS[level - 1]
  const end = LEVEL_THRESHOLDS[level]
  return (wear - start) / (end - start)
}

// 根据键码确定缺角/破碎方向 (用于 level 8-9)
const getBrokenCorner = (code) => {
  const hash = code.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)
  return ['tl', 'tr', 'bl', 'br'][hash % 4]
}

// 获取键的CSS类名
const getKeyClasses = (code) => {
  let level = getWearLevel(effectiveWear(code))
  if (!clipRevealed.value && level >= 8) level = 7
  const classes = [`kb-level-${level}`]
  if (level === 8) classes.push(`kb-broken-${getBrokenCorner(code)}`)
  if (level === 9) classes.push(`kb-shattered-${getBrokenCorner(code)}`)
  return classes.join(' ')
}

// 键盘布局
const keyboardRows = [
  [
    { code: '`', label: '`', sub: '~' }, { code: '1', label: '1', sub: '!' },
    { code: '2', label: '2', sub: '@' }, { code: '3', label: '3', sub: '#' },
    { code: '4', label: '4', sub: '$' }, { code: '5', label: '5', sub: '%' },
    { code: '6', label: '6', sub: '^' }, { code: '7', label: '7', sub: '&' },
    { code: '8', label: '8', sub: '*' }, { code: '9', label: '9', sub: '(' },
    { code: '0', label: '0', sub: ')' }, { code: '-', label: '-', sub: '_' },
    { code: '=', label: '=', sub: '+' }, { code: 'backspace', label: '⌫', w: 2, isFunc: true },
  ],
  [
    { code: 'tab', label: 'Tab', w: 1.5, isFunc: true },
    { code: 'q', label: 'Q' }, { code: 'w', label: 'W' }, { code: 'e', label: 'E' },
    { code: 'r', label: 'R' }, { code: 't', label: 'T' }, { code: 'y', label: 'Y' },
    { code: 'u', label: 'U' }, { code: 'i', label: 'I' }, { code: 'o', label: 'O' },
    { code: 'p', label: 'P' }, { code: '[', label: '[', sub: '{' },
    { code: ']', label: ']', sub: '}' }, { code: '\\', label: '\\', sub: '|', w: 1.5 },
  ],
  [
    { code: 'caps', label: 'Caps', w: 1.75, isFunc: true },
    { code: 'a', label: 'A' }, { code: 's', label: 'S' }, { code: 'd', label: 'D' },
    { code: 'f', label: 'F' }, { code: 'g', label: 'G' }, { code: 'h', label: 'H' },
    { code: 'j', label: 'J' }, { code: 'k', label: 'K' }, { code: 'l', label: 'L' },
    { code: ';', label: ';', sub: ':' }, { code: "'", label: "'", sub: '"' },
    { code: 'enter', label: 'Enter', w: 2.25, isFunc: true },
  ],
  [
    { code: 'shift', label: 'Shift', w: 2.25, isFunc: true },
    { code: 'z', label: 'Z' }, { code: 'x', label: 'X' }, { code: 'c', label: 'C' },
    { code: 'v', label: 'V' }, { code: 'b', label: 'B' }, { code: 'n', label: 'N' },
    { code: 'm', label: 'M' }, { code: ',', label: ',', sub: '<' },
    { code: '.', label: '.', sub: '>' }, { code: '/', label: '/', sub: '?' },
    { code: 'shift', label: 'Shift', w: 2.75, isFunc: true },
  ],
  [
    { code: 'ctrl', label: 'Ctrl', w: 1.25, isFunc: true },
    { code: 'alt', label: 'Alt', w: 1.25, isFunc: true },
    { code: 'space', label: '', w: 6.25, isSpace: true },
    { code: 'alt', label: 'Alt', w: 1.25, isFunc: true },
    { code: 'ctrl', label: 'Ctrl', w: 1.25, isFunc: true },
  ],
]

// 键帽磨损样式：统一输出 CSS 变量（--wear-opacity 等），由样式表消费；
// 显影动画只需推进 wearReveal，即可让所有键从全新态平滑过渡到目标等级。
// 材质叙事：全新 = 冷白 ABS，越敲越发黄发亮（真实键盘的老化方向）。
const getKeyStyle = (code) => {
  const w = effectiveWear(code)
  const level = getWearLevel(w)
  const progress = getWearProgress(w)

  // 等级对应的饱和度与亮度（色相固定在暖黄 46）
  const levelParams = [
    { s: 4, l: 97 },   // 0: 全新冷白
    { s: 10, l: 94 },  // 1: 指纹油光
    { s: 14, l: 91 },  // 2: 涂层初磨
    { s: 18, l: 87 },  // 3: 涂层磨损
    { s: 22, l: 82 },  // 4: 涂层剥落
    { s: 25, l: 78 },  // 5: 表面凹陷
    { s: 28, l: 73 },  // 6: 细微裂纹
    { s: 30, l: 69 },  // 7: 网状龟裂
    { s: 32, l: 65 },  // 8: 缺角碎裂
    { s: 34, l: 61 },  // 9: 严重破损
    { s: 8, l: 45 },   // 10: 完全报废（轴体底座）
  ]
  // 高光/凹陷深度、标签透明度/模糊度随等级变化
  const highlightLevels = [0.62, 0.52, 0.42, 0.34, 0.26, 0.2, 0.14, 0.09, 0.05, 0.02, 0]
  const depthLevels = [0.1, 0.12, 0.15, 0.18, 0.2, 0.24, 0.28, 0.32, 0.36, 0.4, 0.45]
  const opacityLevels = [1, 0.95, 0.88, 0.75, 0.55, 0.35, 0.18, 0.08, 0.03, 0.01, 0]
  const blurLevels = [0, 0.2, 0.4, 0.7, 1.0, 1.4, 1.8, 2.2, 2.6, 3.0, 3.5]

  // 等级内平滑插值
  const lerpLevel = (arr) => arr[level] + (arr[Math.min(level + 1, 10)] - arr[level]) * progress
  const current = levelParams[level]
  const next = levelParams[Math.min(level + 1, 10)]
  const sat = current.s + (next.s - current.s) * progress
  const baseL = current.l + (next.l - current.l) * progress

  return {
    '--key-bg': `hsl(46, ${sat}%, ${baseL}%)`,
    '--key-bg-dark': `hsl(46, ${sat}%, ${baseL - 5}%)`,
    '--key-border': `hsl(46, ${Math.max(0, sat - 4)}%, ${baseL - 17}%)`,
    '--key-side': `hsl(46, ${sat}%, ${baseL - 13}%)`,
    '--key-highlight': lerpLevel(highlightLevels).toFixed(3),
    '--key-depth': lerpLevel(depthLevels).toFixed(3),
    '--wear-opacity': lerpLevel(opacityLevels).toFixed(3),
    '--wear-blur': `${lerpLevel(blurLevels).toFixed(2)}px`,
  }
}

// ========== 单键 HUD 与 Top3 领奖台 ==========

const KEY_NAME_MAP = { space: '空格', enter: 'Enter', backspace: '退格', shift: 'Shift', tab: 'Tab', caps: 'Caps', ctrl: 'Ctrl', alt: 'Alt' }

// code → 全键盘敲击排名（仅统计有敲击的键）
const keyRankMap = computed(() => {
  const m = {}
  Object.entries(keyHitsMap.value)
    .map(([k, v]) => [k, Number(v) || 0])
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .forEach(([k], i) => { m[k] = i + 1 })
  return m
})

const topWornKeys = computed(() =>
  Object.entries(keyHitsMap.value)
    .map(([code, hits]) => ({ code, hits: Number(hits) || 0 }))
    .filter((x) => x.hits > 0)
    .sort((a, b) => b.hits - a.hits)
    .slice(0, 3)
    .map((x) => ({ ...x, name: KEY_NAME_MAP[x.code] || x.code.toUpperCase() }))
)

const podiumLabel = (k) => (k.code === 'space' ? '␣' : KEY_NAME_MAP[k.code] ? k.name : k.code.toUpperCase())

const keyTooltip = ref(null) // { title, meta, x, y }
const keyboardBodyEl = ref(null)

const showKeyTip = (evt, key) => {
  const body = keyboardBodyEl.value
  const target = evt?.currentTarget
  if (!body || !target) return
  const code = key.code.toLowerCase()
  const hits = Number(keyHitsMap.value[code] || 0)
  const rank = keyRankMap.value[code]
  const title = key.isSpace ? '空格键' : `${key.label || key.code} 键`
  const level = getWearLevel(getWear(code))
  const bodyRect = body.getBoundingClientRect()
  const keyRect = target.getBoundingClientRect()
  keyTooltip.value = {
    title: hits > 0 && rank ? `${title} · 敲击 ${formatInt(hits)} 次` : `${title} · 今年还没敲过`,
    meta: hits > 0 && rank ? `全键盘第 ${rank} · 磨损 Lv.${level} ${LEVEL_NAMES[level]}` : '',
    // 边缘键做水平钳制，避免 HUD 超出键盘
    x: Math.min(Math.max(keyRect.left - bodyRect.left + keyRect.width / 2, 78), bodyRect.width - 78),
    y: keyRect.top - bodyRect.top,
  }
}
const hideKeyTip = () => { keyTooltip.value = null }
const hideKeyTipTouch = (evt) => { if (evt?.pointerType !== 'mouse') hideKeyTip() }

// ========== 按压、粒子与输入法候选条 ==========

const rootEl = ref(null)
const fxEl = ref(null)
const imeEl = ref(null)
const hitsEl = ref(null)
const bookEl = ref(null)
const book3dEl = ref(null)
const bookGlossEl = ref(null)
const reamStackEl = ref(null)

// code → 键帽元素（Shift 等重复键存多个，取第一个）
const keyEls = {}
const setKeyEl = (el, code) => {
  if (!el) return
  const list = (keyEls[code] ||= [])
  if (!list.includes(el)) list.push(el)
}

// 卡包式悬浮：书跟着光标微倾（与下一张卡的词典同一手感）
const onBookPointerMove = (e) => {
  if (reducedMotion.value) return
  const el = bookEl.value
  const st = book3dEl.value
  if (!el || !st) return
  const r = el.getBoundingClientRect()
  if (!r.width || !r.height) return
  const nx = ((e.clientX - r.left) / r.width) * 2 - 1
  const ny = ((e.clientY - r.top) / r.height) * 2 - 1
  gsap.to(st, {
    rotationY: -20 + nx * 9,
    rotationX: 9 - ny * 7,
    duration: 0.45,
    ease: 'power2.out',
    overwrite: 'auto',
  })
}
const onBookPointerLeave = () => {
  const st = book3dEl.value
  if (!st) return
  gsap.to(st, { rotationY: -20, rotationX: 9, duration: 0.7, ease: 'power3.out', overwrite: 'auto', clearProps: 'transform' })
}

// FitScale 会整体缩放内容：把视口坐标换算回根元素的未缩放局部坐标
const getRelPoint = (el) => {
  const root = rootEl.value
  if (!root || !el) return null
  const rr = root.getBoundingClientRect()
  if (!rr.width || !root.offsetWidth) return null
  const scale = rr.width / root.offsetWidth
  const r = el.getBoundingClientRect()
  return {
    x: (r.left + r.width / 2 - rr.left) / scale,
    y: (r.top + r.height / 2 - rr.top) / scale,
  }
}

// 键帽上飞出一个字符
const spawnGlyph = (ch, point) => {
  const fx = fxEl.value
  if (!fx || !point || reducedMotion.value) return
  if (fx.childElementCount > 36) return
  const span = document.createElement('span')
  span.className = 'tf-glyph'
  span.textContent = ch
  span.style.left = `${point.x}px`
  span.style.top = `${point.y}px`
  fx.appendChild(span)
  gsap.fromTo(
    span,
    { x: 0, y: 0, opacity: 0.95, scale: 0.7, rotation: gsap.utils.random(-12, 12) },
    {
      x: gsap.utils.random(-18, 18),
      y: gsap.utils.random(-44, -70),
      opacity: 0,
      scale: gsap.utils.random(1.0, 1.25),
      duration: gsap.utils.random(0.7, 1.0),
      ease: 'power2.out',
      onComplete: () => span.remove(),
    }
  )
}

// 敲击计数器轻微一跳（不改数值，只报个到）
const pulseHits = () => {
  if (!hitsEl.value || reducedMotion.value) return
  gsap.fromTo(hitsEl.value, { scale: 1 }, { scale: 1.05, duration: 0.09, yoyo: true, repeat: 1, ease: 'power1.out', overwrite: 'auto' })
}

const labelForCode = (code) => {
  if (code === 'space') return '␣'
  if (code.length === 1) return code.toUpperCase()
  return KEY_NAME_MAP[code] || code
}

// 按下一颗键：视觉压下 + 字符飞出 + 计数器一跳
const pressKey = (code, { glyph = true } = {}) => {
  const el = keyEls[code]?.[0]
  if (!el) return
  el.classList.add('is-down')
  window.setTimeout(() => el.classList.remove('is-down'), 120)
  if (glyph) spawnGlyph(labelForCode(code), getRelPoint(el))
  pulseHits()
}

const onKeyPointerDown = (evt, key) => {
  showKeyTip(evt, key)
  pressKey(key.code, { glyph: true })
  userInterrupt()
}

// 物理键盘映射：翻到本卡时，你在真键盘上敲字，屏幕上的键盘跟着亮。
// 只映射字母/数字/标点——空格与方向键留给 deck 翻页。
const MIRRORABLE = new Set('abcdefghijklmnopqrstuvwxyz0123456789-=[]\\;\',./`'.split(''))
const isEditableTarget = (t) => {
  if (!t) return false
  const tag = String(t.tagName || '').toUpperCase()
  return tag === 'INPUT' || tag === 'TEXTAREA' || t.isContentEditable
}
const onWindowKeydown = (e) => {
  if (!props.isActive || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return
  if (isEditableTarget(e.target)) return
  const k = String(e.key || '').toLowerCase()
  if (!MIRRORABLE.has(k)) return
  pressKey(k, { glyph: true })
  userInterrupt()
}

// ========== 输入法小剧场：拼音 → 候选 → 入册 ==========

// 素材是你当年真实发出的短句（后端 typedPhrases 采样 + 拼音）；
// 旧缓存没有该字段时小剧场不开演，只留光标呼吸。
const typedPhrases = computed(() => {
  const arr = Array.isArray(props.data?.typedPhrases) ? props.data.typedPhrases : []
  return arr
    .map((p) => ({ word: String(p?.text || '').trim(), py: String(p?.pinyin || '').trim() }))
    .filter((p) => p.word && /^[a-z ]+$/.test(p.py))
})

const imePinyin = ref('')
const imeCands = ref([])

let vToken = 0
let vTimers = []
let vPhraseIdx = 0
let vOrder = []
let vPausedByUser = 0

const vClearTimers = () => {
  vTimers.forEach((t) => window.clearTimeout(t))
  vTimers = []
}
const vAfter = (ms, fn) => {
  const token = vToken
  const id = window.setTimeout(() => {
    if (token !== vToken) return
    fn()
  }, ms)
  vTimers.push(id)
}

// 提交的词飞进书里（没有书就飞向大数字）
const flyWordToBook = (word) => {
  const fx = fxEl.value
  const from = getRelPoint(imeEl.value)
  const targetEl = bookEl.value || rootEl.value?.querySelector('.tf-big')
  const to = getRelPoint(targetEl)
  if (!fx || !from || !to || reducedMotion.value) return
  const span = document.createElement('span')
  span.className = 'tf-word wrapped-privacy-message'
  span.textContent = word
  span.style.left = `${from.x - 120}px`
  span.style.top = `${from.y}px`
  fx.appendChild(span)
  const dx = to.x - (from.x - 120)
  const dy = to.y - from.y
  const tl = gsap.timeline({ onComplete: () => span.remove() })
  tl.fromTo(span, { x: 0, y: 0, opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.16, ease: 'power1.out' })
  tl.to(span, { x: dx, duration: 0.72, ease: 'power1.inOut' }, 0.18)
  tl.to(span, { y: dy - 60, duration: 0.34, ease: 'power2.out' }, 0.18)
  tl.to(span, { y: dy, duration: 0.38, ease: 'power2.in' }, 0.52)
  tl.to(span, { opacity: 0, scale: 0.5, duration: 0.18, ease: 'power1.in' }, 0.76)
  // 词落进书里，书轻轻一沉
  if (book3dEl.value) {
    tl.fromTo(book3dEl.value, { y: 0 }, { y: 2.5, duration: 0.12, yoyo: true, repeat: 1, ease: 'power1.inOut', overwrite: 'auto' }, 0.86)
  }
}

// 打一条短语：逐键敲拼音 → 亮候选 → 首选词入册
const vPlayPhrase = () => {
  const list = typedPhrases.value
  if (!list.length) return
  // 每轮洗一次顺序，随机但不重复
  if (!vOrder.length || vPhraseIdx >= vOrder.length) {
    vOrder = gsap.utils.shuffle(list.map((_, i) => i))
    vPhraseIdx = 0
  }
  const phrase = list[vOrder[vPhraseIdx] % list.length]
  vPhraseIdx += 1
  const letters = phrase.py.split('')
  // 隐私模式：文字由模糊层遮蔽；按键仍替换成随机键，防止按键亮起的顺序拼出句子
  const priv = privacyMode.value
  const LETTERS = 'abcdefghijklmnopqrstuvwxyz'
  let t = 0
  letters.forEach((ch) => {
    if (ch === ' ') {
      // 音节间隔：显示分词撇号，不敲键
      vAfter(t, () => { imePinyin.value += "'" })
      t += 70
      return
    }
    vAfter(t, () => {
      imePinyin.value += ch
      pressKey(priv ? LETTERS[Math.floor(Math.random() * 26)] : ch, { glyph: false })
    })
    t += Math.round(gsap.utils.random(88, 150))
  })
  vAfter(t + 240, () => { imeCands.value = [phrase.word] })
  vAfter(t + 900, () => {
    flyWordToBook(phrase.word)
    imePinyin.value = ''
    imeCands.value = []
  })
  vAfter(t + 900 + Math.round(gsap.utils.random(1600, 2400)), vPlayPhrase)
}

const startVignette = (delay = 0) => {
  if (!import.meta.client || reducedMotion.value) return
  if (totalKeyHits.value <= 0 || !typedPhrases.value.length) return
  vToken += 1
  vClearTimers()
  imePinyin.value = ''
  imeCands.value = []
  vAfter(delay, vPlayPhrase)
}

const stopVignette = () => {
  vToken += 1
  vClearTimers()
  imePinyin.value = ''
  imeCands.value = []
}

// 用户上手时，小剧场让位几秒
const userInterrupt = () => {
  if (reducedMotion.value) return
  const now = Date.now()
  if (now - vPausedByUser < 500) return
  vPausedByUser = now
  stopVignette()
  if (props.isActive) startVignette(3600)
}

// ========== 入场编排 ==========

const rowEls = []
const setRowEl = (el, ri) => { rowEls[ri] = el || null }

let hasEntered = false
let entranceTl = null

const finishAll = () => {
  wearReveal.value = 1
  clipRevealed.value = true
  odoPlay.value = true
  finishA4Height()
}

const buildTimeline = () => {
  const root = rootEl.value
  if (!root) {
    finishAll()
    return
  }
  const tl = gsap.timeline()

  // a. hero 文字组自下而上
  const heroBits = root.querySelectorAll('.tf-q1, .tf-big, .tf-sent-cap')
  if (heroBits.length) {
    tl.from(heroBits, { opacity: 0, y: 16, duration: 0.55, ease: 'power2.out', stagger: 0.09 }, 0.05)
  }
  // 大数滚轮开转
  tl.add(() => { odoPlay.value = true }, 0.3)

  // b. 换算成书的那行答案，等大数滚得差不多再浮现
  const answer = root.querySelector('.tf-ask')
  if (answer) {
    tl.from(answer, { opacity: 0, y: 10, duration: 0.45, ease: 'power2.out' }, 1.1)
  }

  // c. 书装订成册 + 封面扫过一道箔光
  if (bookEl.value) {
    tl.from(bookEl.value, { opacity: 0, y: 18, duration: 0.6, ease: 'power2.out' }, 0.55)
    if (bookGlossEl.value) {
      tl.fromTo(bookGlossEl.value, { xPercent: -160 }, { xPercent: 240, duration: 0.9, ease: 'power2.inOut' }, 1.35)
    }
  }

  // d. A4 纸摞长高 + 刻度尺读数
  if (reamStackEl.value) {
    tl.fromTo(reamStackEl.value, { scaleY: 0 }, { scaleY: 1, duration: 0.9, ease: 'power3.out' }, 0.7)
  }
  tl.add(() => { playA4Height() }, 0.75)
  const meta = root.querySelector('.tf-meta')
  if (meta) {
    tl.from(meta, { opacity: 0, y: 12, duration: 0.5, ease: 'power2.out' }, 0.62)
  }

  // e. 键盘从台面升起 + 按行波浪压下弹起
  const kbBody = keyboardBodyEl.value
  if (kbBody) {
    tl.from(kbBody, { opacity: 0, y: 26, duration: 0.65, ease: 'expo.out' }, 0.35)
  }
  rowEls.forEach((rowEl, ri) => {
    if (!rowEl || !rowEl.children?.length) return
    tl.to(rowEl.children, {
      y: 2,
      duration: 0.09,
      ease: 'power1.in',
      yoyo: true,
      repeat: 1,
      stagger: 0.018,
    }, 0.62 + ri * 0.1)
  })

  // f. 磨损显影：全新态 → 目标等级；结束后再切 Level 8-10 的 clip-path 类
  tl.to(wearReveal, { value: 1, duration: 1.2, ease: 'power1.inOut' }, 0.85)
  tl.add(() => { clipRevealed.value = true }, 2.1)

  // g. 玻璃候选条落下
  if (imeEl.value) {
    tl.from(imeEl.value, { opacity: 0, y: -14, duration: 0.5, ease: 'power2.out' }, 0.8)
  }

  // h. 底部注脚与领奖台
  const note = root.querySelector('.kb-note')
  if (note) tl.from(note, { opacity: 0, duration: 0.5 }, 1.8)
  const pods = root.querySelectorAll('.pd-item')
  if (pods.length) {
    tl.from(pods, { opacity: 0, y: 10, scale: 0.8, duration: 0.4, ease: 'back.out(2)', stagger: 0.12 }, 1.9)
  }

  // i. 留言机：整机落座，随后部件逐一亮起
  if (showVoiceCalls.value) {
    const am = root.querySelector('.am')
    if (am) {
      tl.from(am, { opacity: 0, y: 20, duration: 0.6, ease: 'expo.out' }, 0.5)
      const parts = am.querySelectorAll(':scope > *')
      if (parts.length) {
        tl.from(parts, { opacity: 0, y: 10, duration: 0.4, ease: 'power2.out', stagger: 0.09 }, 0.7)
      }
    }
  }

  // j. 入场收尾后，输入法小剧场开演
  tl.add(() => { startVignette(500) }, 2.3)

  entranceTl = tl
  if (!props.isActive) tl.pause()
}

/* 导出：入场直接落到终帧。
   已建过时间线就 progress(1) 把在飞的 from() 全部推到末尾（内联值落在自然值上，
   不留半透明残影）；没建过就等同 reduced 那条路——那些 from() 是唯一会动这些元素的东西，
   没建时元素本来就在终态。收尾 stopVignette()：输入法小剧场是无限循环的环境动效，
   导出要的是一张定得住的帧，不是一直在敲字的帧。 */
const settleEntranceInstant = () => {
  if (entranceStartTimer) { window.clearTimeout(entranceStartTimer); entranceStartTimer = 0 }
  if (entranceTl) entranceTl.progress(1)
  finishAll()
  stopVignette()
}

// 还原：把入场留下的终态收回未入场那一帧，下次翻到本页照旧从头演一遍
const primeForReplay = () => {
  if (entranceStartTimer) { window.clearTimeout(entranceStartTimer); entranceStartTimer = 0 }
  stopVignette()
  if (entranceTl) { entranceTl.kill(); entranceTl = null }
  odoPlay.value = false
  clipRevealed.value = false
  wearReveal.value = 0
  a4HeightCurrent.value = 0
  hasEntered = false
}

const playEntrance = () => {
  if (!import.meta.client) return
  hasEntered = true
  if (exportMode.value) {
    settleEntranceInstant()
    return
  }
  if (reducedMotion.value) {
    finishAll()
    return
  }
  // 已建过时间线则从头重播，否则等 DOM 就绪后构建
  if (entranceTl) {
    odoPlay.value = false
    clipRevealed.value = false
    stopVignette()
    entranceTl.restart()
    return
  }
  // 等 DOM 就绪后再采集动画目标
  nextTick(buildTimeline)
}

// 每次翻到本页都重播入场；进入后 450ms（deck 翻页落定）才开播，避免与翻页动画叠加掉帧；离开时暂停。
let entranceStartTimer = 0
watch(() => props.isActive, (active) => {
  if (typeof window !== 'undefined' && entranceStartTimer) {
    window.clearTimeout(entranceStartTimer)
    entranceStartTimer = 0
  }
  if (active) {
    // 导出模式与 reduced 走同一条：翻到本页立刻是终态，不等那 450ms + 2.4s 编排
    if (typeof window === 'undefined' || reducedMotion.value || exportMode.value) {
      playEntrance()
      return
    }
    entranceStartTimer = window.setTimeout(() => {
      entranceStartTimer = 0
      playEntrance()
    }, 450)
  } else {
    if (entranceTl) entranceTl.pause()
    stopVignette()
  }
}, { immediate: true })

/* 导出模式：进去立刻定格终帧，出来还原成进入导出前的样子。
   —— 还原必须真的还原：这一页的主体验是「大数滚出来 → 书装订 → 键盘升起 → 磨损显影」，
      导出一次回来若已经全部落定，这段揭晓就被剧透了。
   放在 isActive 那条 watch 之后，immediate 才能在「导出已经打开时才挂载」的情况下
   直接落到终帧。
   种子值不能等 watch 回调来填：isActive 那条 watch 的 immediate 先跑，
   它会在导出已开时直接把 hasEntered 置真，晚一步再拍快照就把「没入场过」记成了「入场过」。 */
let exportSnapshot = exportMode.value ? { hasEntered: false } : null

watch(exportMode, (on) => {
  if (!import.meta.client) return

  if (on) {
    if (exportSnapshot) return
    exportSnapshot = { hasEntered }
    if (props.isActive) playEntrance()
    return
  }

  const snap = exportSnapshot
  exportSnapshot = null
  if (!snap) return
  // 导出前用户已经看过入场了：保持终态，别把进度抹回去
  if (snap.hasEntered) return

  primeForReplay()
  // 用户正停在本页：按没进过导出时的路子重新演一遍
  if (props.isActive) {
    if (reducedMotion.value) playEntrance()
    else entranceStartTimer = window.setTimeout(() => {
      entranceStartTimer = 0
      playEntrance()
    }, 450)
  }
}, { immediate: true })

onMounted(() => {
  if (!import.meta.client) return
  window.addEventListener('keydown', onWindowKeydown)
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onWindowKeydown)
    if (entranceStartTimer) window.clearTimeout(entranceStartTimer)
    if (amFastTimer) window.clearTimeout(amFastTimer)
    if (amLedTimer) window.clearTimeout(amLedTimer)
  }
  stopVignette()
  if (entranceTl) { entranceTl.kill(); entranceTl = null }
})
</script>

<style scoped>
/* ============ 布局 ============ */

.tf-root {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1300px;
  margin: 0 auto;
  padding: 72px 48px 26px;
}

/* ============ 画幅重排：判据从「浏览器窗口」换成「舞台画幅档位」 ============
   deck 渲染在设计像素恒定的舞台盒里，@media 的宽度与版面宽度早已脱钩
   （竖幅舞台放在宽窗口里照样命中 min-width:1024）。以下一律挂 .wr-stage 的
   data-frame-tier。阅读顺序在所有画幅下恒定：
   里程表大数 → 3D 书 → A4 纸摞 → 玻璃输入法候选条 → 可敲击键盘 → 领奖台 → 留言机。 */

/* —— 16:9 / 4:3：三栏桌面（与原 @media(min-width:1024px) 逐条等价） —— */
[data-frame-tier="wide"] .tf-root--voice,
[data-frame-tier="landscape"] .tf-root--voice {
  display: grid;
  grid-template-columns: minmax(215px, 1fr) minmax(0, 2.4fr) minmax(330px, 1.6fr);
  grid-template-rows: auto 1fr;
  grid-template-areas:
    'hero hero voice'
    'objs kb   voice';
  column-gap: 44px;
  row-gap: 22px;
}
[data-frame-tier="wide"] .tf-root--voice > .tf-hero,
[data-frame-tier="landscape"] .tf-root--voice > .tf-hero { grid-area: hero; }
/* 桌面线：书纸、键盘、留言机三者底边共线 */
[data-frame-tier="wide"] .tf-root--voice > .tf-objs,
[data-frame-tier="landscape"] .tf-root--voice > .tf-objs { grid-area: objs; align-self: end; }
[data-frame-tier="wide"] .tf-root--voice > .tf-kb,
[data-frame-tier="landscape"] .tf-root--voice > .tf-kb { grid-area: kb; align-self: end; }
[data-frame-tier="wide"] .tf-root--voice > .voice-section,
[data-frame-tier="landscape"] .tf-root--voice > .voice-section {
  grid-area: voice;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

/* —— 9:16（900×1600）：重排 + 放大，不是把横幅整块缩下来 ——
   原来是单列四段纵向流（hero / 书纸 / 键盘 / 留言机），版面只占舞台 75%，
   上下各空 147 与 108，而字号最小到 6.5px —— 竖幅下等于看不见。
   ① 书与纸摞收进 hero 右手边并肩（原来独占一整行，白吃 184px 高度）；
   ② 上下内边距从 72/26 收到 6/12（那两条空带本来就没有内容）；
   ③ 省下来的高度全部还给字号与构件 —— 见文件末尾「tall 放大」整块。 */
[data-frame-tier="tall"] .tf-root {
  display: grid;
  max-width: none;
  /* 左栏 hero（大数与元数据要横向铺开），右栏 auto 由书+纸摞的实际宽度决定 */
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    'hero  objs'
    'kb    kb'
    'voice voice';
  column-gap: 24px;
  row-gap: 26px;
  padding: 6px 24px 12px;
}
[data-frame-tier="tall"] .tf-root > .tf-hero { grid-area: hero; }
[data-frame-tier="tall"] .tf-root > .tf-objs { grid-area: objs; align-self: end; justify-content: flex-end; }
[data-frame-tier="tall"] .tf-root > .tf-kb { grid-area: kb; }
[data-frame-tier="tall"] .tf-root > .voice-section { grid-area: voice; }

/* —— 3:4 / 4:5（1040×1386 / 1074×1342）：书纸挪到 hero 右手边并肩，
      其余仍是纵向流。单纯堆四段会到 ~1420px，超出 4:5 的 1342。 —— */
[data-frame-tier="portrait"] .tf-root {
  display: grid;
  /* 左栏 min 取 520px（≥ 键盘实体 518px）：kb/voice 两行横跨双栏，
     栅格在摊派跨栏项的 min-content 时只会喂给「内容驱动」的轨道；
     给左栏一个盖得住键盘的下限，就不存在待分摊的超出量，
     书纸那栏永远只有它自己的 224px，hero 也不会被反挤。 */
  grid-template-columns: minmax(520px, 1fr) auto;
  grid-template-areas:
    'hero  objs'
    'kb    kb'
    'voice voice';
  column-gap: 30px;
  row-gap: 18px;
}
[data-frame-tier="portrait"] .tf-root > .tf-hero { grid-area: hero; }
[data-frame-tier="portrait"] .tf-root > .tf-objs { grid-area: objs; align-self: end; }
[data-frame-tier="portrait"] .tf-root > .tf-kb { grid-area: kb; }
[data-frame-tier="portrait"] .tf-root > .voice-section { grid-area: voice; }

/* —— 1:1（1200×1200）：最扁的竖幅。纵向流需要 ~1230px，装不下，
      于是折成 2×2：上排 hero | 书纸，下排 键盘/领奖台 | 留言机。
      从左到右、从上到下读依旧是那七段的原顺序。
      ⚠️ 这里一度写过 `min-height: var(--stage-h)` 想把版面撑满画幅，两处反效果：
      ① 舞台高 1200，可用框只有 1176（外壳 .wr-shell-body 有 24px 上边距），
         min-height 让内容比框还高 → WrappedFitScale 整卡缩到 0.98，正是「靠缩小适配」；
      ② 第二行是 minmax(0,1fr) 且键盘 align-self:end，多出来的高度全灌进这一行，
         hero 与键盘之间实测裂开 452px 空带。
      版面自然高约 835，让 FitScale 居中留白即可 —— 16:9（733/876）、
      3:4（1266/1362）、9:16（1450/1576）本来也都是居中留白。 —— */
[data-frame-tier="square"] .tf-root {
  display: grid;
  grid-template-columns: minmax(520px, 1.5fr) minmax(330px, 1fr);
  grid-template-rows: auto auto;
  grid-template-areas:
    'hero objs'
    'kb   voice';
  column-gap: 40px;
  row-gap: 24px;
}
/* 没有语音/通话数据时右下角空着，键盘改为横跨整宽（左栏 min 同样要盖住键盘宽度） */
[data-frame-tier="square"] .tf-root:not(.tf-root--voice) {
  grid-template-columns: minmax(520px, 1fr) auto;
  grid-template-areas:
    'hero objs'
    'kb   kb';
}
[data-frame-tier="square"] .tf-root > .tf-hero { grid-area: hero; }
[data-frame-tier="square"] .tf-root > .tf-objs { grid-area: objs; align-self: end; }
[data-frame-tier="square"] .tf-root > .tf-kb { grid-area: kb; align-self: end; }
[data-frame-tier="square"] .tf-root > .voice-section {
  grid-area: voice;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

/* 竖幅整宽下留言机会被拉成一条 800px 的长条，不再像一台桌面设备：
   给它一个与 16:9 右栏相当的机身宽度并居中（只改排布，机身构件尺寸不变）。 */
[data-frame-tier="portrait"] .tf-root > .voice-section,
[data-frame-tier="tall"] .tf-root > .voice-section {
  width: 100%;
  max-width: 560px;
  margin-inline: auto;
}

/* 玻璃背后的柔光色斑 */
.tf-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background:
    radial-gradient(280px 180px at 30% 78%, rgba(7, 193, 96, 0.10), transparent 70%),
    radial-gradient(320px 200px at 74% 66%, rgba(110, 123, 217, 0.09), transparent 70%),
    radial-gradient(240px 160px at 56% 90%, rgba(232, 181, 74, 0.07), transparent 70%);
}

.tf-hero,
.voice-section,
.tf-kb {
  position: relative;
  z-index: 1;
}

/* 粒子层 */
.tf-fx {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 40;
}

.tf-fx :deep(.tf-glyph) {
  position: absolute;
  font-size: 16px;
  font-weight: 800;
  color: #07713e;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.75);
  will-change: transform, opacity;
}

.tf-fx :deep(.tf-word) {
  position: absolute;
  font-size: 15px;
  font-weight: 700;
  color: #0b3d26;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(7, 193, 96, 0.22);
  padding: 3px 10px;
  border-radius: 9px;
  box-shadow: 0 6px 16px rgba(20, 60, 35, 0.14);
  white-space: nowrap;
  will-change: transform, opacity;
}

/* ============ A. hero ============ */

.tf-q1 {
  font-size: 25px;
  line-height: 1.3;
  color: #000000e6;
}

.tf-big {
  margin-top: 12px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.tf-big-num {
  font-size: clamp(46px, calc(var(--svw) * 5.2), 66px);
  font-weight: 800;
  letter-spacing: -0.01em;
}

/* 字号挂在 --svw（宽度轴）上：竖幅舞台一变窄，里程表大数就跟着缩到 46-62px。
   构件尺寸必须是设计常量 → 竖幅一律钉死在 16:9 的计算值 66px。
   （wide=16*5.2=83.2、landscape=13.86*5.2=72，都被 clamp 压到 66，故不受影响。） */
[data-frame-tier="square"] .tf-big-num,
[data-frame-tier="portrait"] .tf-big-num,
[data-frame-tier="tall"] .tf-big-num {
  font-size: 66px;
}

.tf-big-unit {
  font-size: 19px;
  font-weight: 700;
  color: #0b3d26;
}

.tf-sent-cap {
  margin-top: 8px;
  font-size: 12.5px;
  color: rgba(0, 0, 0, 0.45);
}

/* 第二问 + 换算成书作答 */
.tf-ask {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.tf-q2 {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.4);
}

.tf-bookline {
  font-size: 16px;
  font-weight: 650;
  color: #07713e;
  letter-spacing: 0.01em;
}

/* 桌面左手边：书 + 纸摞（底边共线） */
.tf-objs {
  display: flex;
  align-items: flex-end;
  gap: 14px;
}

/* —— 一本书 —— */

.book {
  --bw: 118px;
  --bh: 134px;
  position: relative;
  width: calc(var(--bw) + 26px);
  flex-shrink: 0;
  perspective: 800px;
}

.book-shadow {
  position: absolute;
  left: 4%;
  right: 10%;
  bottom: 14px;
  height: 22px;
  border-radius: 50%;
  background: radial-gradient(50% 50% at 50% 50%, rgba(15, 45, 28, 0.30), transparent 72%);
  transform: translateY(8px);
}

.book-3d {
  position: relative;
  width: var(--bw);
  height: var(--bh);
  margin: 0 auto 18px;
  transform-style: preserve-3d;
  transform: rotateX(9deg) rotateY(-20deg);
}

.book-face {
  position: absolute;
}

/* 封面：墨绿细布纹 + 箔压工艺 */
.book-cover {
  inset: 0;
  transform: translateZ(calc(var(--bt) / 2));
  border-radius: 3px 7px 7px 3px;
  background:
    radial-gradient(130% 150% at 12% -8%, rgba(255, 255, 255, 0.15), transparent 42%),
    radial-gradient(90% 90% at 88% 108%, rgba(0, 0, 0, 0.22), transparent 55%),
    repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.03) 0 1px, transparent 1px 2px),
    repeating-linear-gradient(90deg, rgba(0, 0, 0, 0.05) 0 1px, transparent 1px 2px),
    linear-gradient(158deg, #1a5536 0%, #113e26 50%, #0b2e1b 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    inset -4px 0 10px rgba(0, 0, 0, 0.30),
    inset 2px 0 4px rgba(255, 255, 255, 0.05);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  /* 底部让给著者/印行两行，居中组整体上提，不再叠字 */
  padding-bottom: 34px;
  overflow: hidden;
}

/* 封面压凹双框：外框带 + 内圈箔线 */
.book-frame {
  position: absolute;
  inset: 7px;
  border: 1.2px solid rgba(217, 169, 78, 0.5);
  border-radius: 2px 5px 5px 2px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.4), 0 1px 0 rgba(255, 255, 255, 0.07);
  pointer-events: none;
}
.book-frame::after {
  content: '';
  position: absolute;
  inset: 3px;
  border: 0.5px solid rgba(217, 169, 78, 0.28);
  border-radius: 1px 3px 3px 1px;
}

/* 出版社徽记：箔压小章 */
.book-emblem {
  width: 19px;
  height: 19px;
  margin-bottom: 2px;
}

.book-title {
  font-family: 'Songti SC', 'STSong', 'SimSun', serif;
  font-size: 16.5px;
  font-weight: 700;
  letter-spacing: 0.24em;
  margin-right: -0.24em;
  background: linear-gradient(172deg, #FBEFCB 0%, #DDBE7E 30%, #A98753 54%, #F3E2B4 74%, #C9A968 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: 0 -0.5px 0 rgba(0, 0, 0, 0.42), 0 1px 0.5px rgba(255, 246, 214, 0.12);
}

.book-year {
  font-size: 10px;
  letter-spacing: 0.3em;
  margin-right: -0.3em;
  color: rgba(232, 181, 74, 0.78);
}

.book-author {
  position: absolute;
  bottom: 23px;
  font-size: 8.5px;
  letter-spacing: 0.28em;
  margin-right: -0.28em;
  color: rgba(232, 181, 74, 0.62);
}

/* 版权行：像压在封面最下缘的印厂小字 */
.book-imprint {
  position: absolute;
  bottom: 11px;
  font-size: 6.5px;
  letter-spacing: 0.24em;
  margin-right: -0.24em;
  color: rgba(232, 181, 74, 0.34);
}

/* 书签飘带：从书芯底部垂出 */
.book-ribbon {
  position: absolute;
  bottom: -13px;
  left: 26%;
  width: 9px;
  height: 20px;
  background: linear-gradient(180deg, #b23b2e 0%, #8f2a20 100%);
  clip-path: polygon(0 0, 100% 0, 100% 100%, 50% 82%, 0 100%);
  box-shadow: inset 0 2px 3px rgba(0, 0, 0, 0.25);
}

/* 掠过封面的箔光 */
.book-gloss {
  position: absolute;
  top: -20%;
  bottom: -20%;
  left: 0;
  width: 46%;
  background: linear-gradient(100deg, transparent 0%, rgba(255, 244, 214, 0.16) 45%, rgba(255, 255, 255, 0.05) 55%, transparent 100%);
  transform: translateX(-160%) skewX(-14deg);
  pointer-events: none;
}

/* 右侧书口：一页一页的纸 */
.book-pages {
  width: var(--bt);
  height: calc(100% - 6px);
  top: 3px;
  left: calc(50% - var(--bt) / 2);
  transform: rotateY(90deg) translateZ(calc(var(--bw) / 2 - 1px));
  background: repeating-linear-gradient(90deg, #fbf8f0 0 2px, #e8e2d2 2px 3px);
  border-radius: 0 2px 2px 0;
  box-shadow: inset 0 0 6px rgba(0, 0, 0, 0.12);
}

/* 顶面书口：刷金 */
.book-top {
  width: calc(100% - 4px);
  height: var(--bt);
  left: 2px;
  top: calc(50% - var(--bt) / 2);
  transform: rotateX(90deg) translateZ(calc(var(--bh) / 2));
  background:
    repeating-linear-gradient(0deg, rgba(120, 80, 20, 0.16) 0 1px, transparent 1px 2.5px),
    linear-gradient(90deg, #cfa552 0%, #ecd089 45%, #c99e48 100%);
  box-shadow: inset 0 0 5px rgba(0, 0, 0, 0.14);
}

/* 书脊（大角度下几乎看不见，补个色防穿帮） */
.book-spine {
  width: var(--bt);
  height: 100%;
  left: calc(50% - var(--bt) / 2);
  transform: rotateY(-90deg) translateZ(calc(var(--bw) / 2));
  background: linear-gradient(180deg, #0f3a25, #0a2b1a);
  border-radius: 3px 0 0 3px;
}

.book-cap {
  text-align: center;
  font-size: 9.5px;
  color: rgba(0, 0, 0, 0.35);
}

/* 向你走来的字：一行元数据 */
.tf-meta {
  margin-top: 16px;
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 10px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.5);
}

.tf-meta-label {
  font-size: 10.5px;
  color: rgba(0, 0, 0, 0.38);
}

.tf-meta-num {
  font-size: 20px;
  font-weight: 750;
  color: #141414;
  line-height: 1;
}

.tf-meta-unit {
  font-size: 11px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.5);
  margin-left: -4px;
}

.tf-meta-sep {
  width: 1px;
  height: 11px;
  background: rgba(0, 0, 0, 0.14);
  align-self: center;
}

.tf-meta-item b {
  font-weight: 700;
  color: #10241a;
}

.tf-meta--empty {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.38);
}

/* A4 纸摞：收到的字打印出来的样子 */
.ream {
  position: relative;
  width: 66px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.ream-stack {
  position: relative;
  width: 100%;
  height: var(--rh);
  transform-origin: bottom;
}

/* 纸摞侧面：一沓 A4 的横纹 */
.ream-side {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(180deg, #fdfcf8 0 2.5px, #e6e1d3 2.5px 3.5px);
  border: 1px solid rgba(0, 0, 0, 0.09);
  border-radius: 2px;
  box-shadow: 0 10px 22px rgba(30, 50, 35, 0.13);
}

/* 顶上两张翘起来的纸 */
.ream-sheet {
  position: absolute;
  left: -3px;
  right: -3px;
  height: 7px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.09);
  border-radius: 1.5px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.ream-sheet--a {
  top: -4px;
  transform: rotate(-1.6deg);
}

.ream-sheet--b {
  top: -1px;
  transform: rotate(1.1deg);
}

.ream-cap {
  margin-top: 7px;
  text-align: center;
  font-size: 9px;
  color: rgba(0, 0, 0, 0.35);
  white-space: nowrap;
}

/* ============ C. 键盘舞台 ============ */

.tf-kb {
  margin-top: 2px;
}

.kb-stage {
  width: fit-content;
  margin: 0 auto;
}

/* —— 输入法候选条：液态玻璃 —— */

.ime-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 12px;
  padding: 9px 14px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.66), rgba(255, 255, 255, 0.42));
  backdrop-filter: blur(16px) saturate(1.7);
  -webkit-backdrop-filter: blur(16px) saturate(1.7);
  border: 1px solid rgba(255, 255, 255, 0.75);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    inset 0 -6px 12px rgba(255, 255, 255, 0.18),
    0 10px 30px rgba(30, 60, 40, 0.12),
    0 2px 6px rgba(0, 0, 0, 0.05);
}

.ime-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 24px;
}

.ime-caret {
  width: 2px;
  height: 16px;
  border-radius: 1px;
  background: #07c160;
  flex-shrink: 0;
  animation: imeCaretBlink 1.1s steps(1) infinite;
}

@keyframes imeCaretBlink {
  0%, 55% { opacity: 1; }
  56%, 100% { opacity: 0; }
}

.ime-py {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #10241a;
  white-space: nowrap;
  min-height: 1em;
}

.ime-cands {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 6px;
}

.ime-cand {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12.5px;
  color: rgba(0, 0, 0, 0.6);
  padding: 3px 8px;
  border-radius: 8px;
  white-space: nowrap;
}

.ime-cand-no {
  font-size: 9px;
  opacity: 0.55;
  font-style: normal;
}

.ime-cand--first {
  background: #07c160;
  color: #ffffff;
  font-weight: 650;
  box-shadow: 0 3px 8px rgba(7, 193, 96, 0.35);
}

.ime-cand--first .ime-cand-no {
  opacity: 0.8;
}

.cand-enter-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.cand-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.cand-leave-active {
  transition: opacity 0.14s ease;
}
.cand-leave-to {
  opacity: 0;
}

.ime-hits {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-shrink: 0;
  transform-origin: center;
}

.ime-hits-num {
  font-size: 17px;
  font-weight: 750;
  color: #10241a;
}

.ime-hits-unit {
  font-size: 9.5px;
  color: rgba(0, 0, 0, 0.42);
}

/* —— 键盘实体：铝壳 —— */

.keyboard-body {
  /* 键位间距的唯一出处：行间 gap、行内 gap、宽键补偿公式共用这一个值。
     以前宽键公式里硬编码 3px，改一次间距要改八处，且各画幅无法一致。 */
  --kb-gap: 3px;
  border-radius: 16px;
  padding: 10px 12px 12px;
  position: relative;
  /* 行距用 gap 而非行的 margin：HUD（绝对定位）插入/移除时不影响 :last-child 匹配，高度恒定 */
  display: flex;
  flex-direction: column;
  gap: var(--kb-gap);
  background: linear-gradient(180deg, #f6f7f4 0%, #e7e9e3 58%, #dcdfd7 100%);
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    inset 0 -2px 3px rgba(0, 0, 0, 0.05),
    0 1.5px 0 1px #c6cabf,
    0 26px 48px -12px rgba(25, 60, 40, 0.28),
    0 6px 14px rgba(0, 0, 0, 0.07);
}

.kb-row {
  display: flex;
  justify-content: center;
  gap: var(--kb-gap, 3px);
}

/* 键帽。
   ⚠️ --unit / height 以前挂 @media(min-width:640px) 做 22↔30px 两档，判据是浏览器窗口，
   舞台化之后那个断点在任何画幅里都恒真（窗口永远宽于 640），等于只剩大档；
   而键帽是「构件尺寸」，本就该是设计常量。于是把 16:9 的大档提为唯一值，
   竖幅 900px 宽也放得下整排（键盘实体约 518px）。16:9 计算值不变。 */
.kb-key {
  --unit: 30px;
  height: 34px;
  width: var(--unit);
  position: relative;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}

/* 宽度变体：N 倍键位 + 被吞掉的 (N-1) 个间距 */
.kb-w-1 { width: var(--unit); }
.kb-w-1\.25 { width: calc(var(--unit) * 1.25 + var(--kb-gap, 3px) * 0.25); }
.kb-w-1\.5 { width: calc(var(--unit) * 1.5 + var(--kb-gap, 3px) * 0.5); }
.kb-w-1\.75 { width: calc(var(--unit) * 1.75 + var(--kb-gap, 3px) * 0.75); }
.kb-w-2 { width: calc(var(--unit) * 2 + var(--kb-gap, 3px)); }
.kb-w-2\.25 { width: calc(var(--unit) * 2.25 + var(--kb-gap, 3px) * 1.25); }
.kb-w-2\.75 { width: calc(var(--unit) * 2.75 + var(--kb-gap, 3px) * 1.75); }
.kb-w-6\.25 { width: calc(var(--unit) * 6.25 + var(--kb-gap, 3px) * 5.25); }

/* 键座（底部露出的侧壁） */
.kb-key::before {
  content: '';
  position: absolute;
  inset: 0;
  top: 2px;
  background: var(--key-side, #d4d4d8);
  border-radius: 5px;
}

/* 磨损样式由键帽上的 CSS 变量驱动（--key-highlight/--key-depth/--wear-opacity/--wear-blur） */
.kb-key-top {
  position: absolute;
  inset: 0;
  bottom: 2px;
  border-radius: 5px;
  border: 1px solid var(--key-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    radial-gradient(130% 86% at 50% 4%, rgba(255, 255, 255, 0.42), transparent 52%),
    linear-gradient(180deg, var(--key-bg) 0%, var(--key-bg-dark) 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, var(--key-highlight, 0.55)),
    inset 0 -1px 2px rgba(0, 0, 0, var(--key-depth, 0.12));
  transform: translateY(0);
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

/* 按压态：键帽压进键座 */
.kb-key.is-down .kb-key-top,
.kb-key:active .kb-key-top {
  transform: translateY(1.6px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, calc(var(--key-highlight, 0.55) * 0.5)),
    inset 0 2px 4px rgba(0, 0, 0, 0.16);
  transition-duration: 0.05s;
}

/* 键帽刻字同理：原 7↔8 / 10↔11 / 7↔8 两档也是窗口断点，统一取 16:9 的大档。 */
.kb-sub {
  font-size: 8px;
  line-height: 1;
  color: #666;
  margin-bottom: 1px;
  opacity: var(--wear-opacity, 1);
  filter: blur(var(--wear-blur, 0px));
}

.kb-label {
  font-size: 11px;
  font-weight: 500;
  color: #262626;
  line-height: 1;
  text-shadow: 0 1px 0 rgba(255,255,255,0.6);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
  opacity: var(--wear-opacity, 1);
  filter: blur(var(--wear-blur, 0px));
}

.kb-label-sm {
  font-size: 8px !important;
  font-weight: 400;
}

.kb-space-bar {
  width: 50%;
  height: 3px;
  background: rgba(0,0,0,0.12);
  border-radius: 2px;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.18);
}

/* 单键 HUD：深色玻璃小卡 */
.kb-hud {
  position: absolute;
  transform: translate(-50%, calc(-100% - 8px));
  background: linear-gradient(180deg, rgba(28, 33, 30, 0.88), rgba(16, 20, 18, 0.88));
  backdrop-filter: blur(12px) saturate(1.4);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
  color: #fff;
  padding: 7px 11px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  white-space: nowrap;
  pointer-events: none;
  z-index: 30;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 8px 20px rgba(0, 0, 0, 0.25);
}

.kb-hud-title {
  font-size: 11px;
  font-weight: 650;
  line-height: 1;
}

.kb-hud-meta {
  margin-top: 4px;
  font-size: 9.5px;
  line-height: 1;
  color: rgba(255, 255, 255, 0.62);
}

.keyboard-brand {
  @apply mt-2 text-center text-[8px] text-[#00000026] tracking-[0.18em] uppercase;
}

/* —— 底部注脚 + 领奖台 —— */

.kb-foot {
  margin-top: 9px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.kb-note {
  font-size: 9.5px;
  color: rgba(0, 0, 0, 0.32);
  max-width: 240px;
  line-height: 1.7;
}

.podium {
  display: flex;
  align-items: flex-end;
  gap: 20px;
}

.pd-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.pd-key {
  --unit: 42px;
  /* 奖杯复刻键帽：全新象牙白底 + 箔字，不吃磨损变量 */
  --key-bg: hsl(46, 8%, 97%);
  --key-bg-dark: hsl(46, 10%, 92%);
  --key-border: hsl(46, 10%, 76%);
  --key-side: hsl(46, 10%, 83%);
  --key-highlight: 0.62;
  --key-depth: 0.1;
  --wear-opacity: 1;
  --wear-blur: 0px;
  width: var(--unit);
  height: 46px;
  cursor: default;
}

.pd-key--space {
  --unit: 88px;
  width: var(--unit);
}

.pd-key .kb-label {
  font-size: 15px !important;
  font-weight: 700;
  background: linear-gradient(180deg, #c9a24e 0%, #a67c2c 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: none;
}

/* 名次徽章：金银铜小圆章 */
.pd-medal {
  position: absolute;
  top: -7px;
  right: -7px;
  width: 17px;
  height: 17px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
  border: 1px solid rgba(255, 255, 255, 0.55);
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.5);
}

.pd-medal b {
  font-size: 9px;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.3);
}

.pd-medal--0 { background: linear-gradient(160deg, #f0c86a, #d9a232 60%, #b47f1d); }
.pd-medal--1 { background: linear-gradient(160deg, #d8dde2, #b3bac2 60%, #8f979f); }
.pd-medal--2 { background: linear-gradient(160deg, #d8a06c, #b97e46 60%, #96602f); }

.pd-cap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.pd-name {
  font-size: 11px;
  font-weight: 650;
  color: #262626;
  line-height: 1;
}

.pd-hits {
  font-size: 9px;
  color: rgba(0, 0, 0, 0.4);
}

/* 竖幅：注脚与领奖台改上下排。
   （原判据是 @media(max-width:639px)，在舞台里永不触发；.tf-duo 那条是早已删掉的
   模块的残留选择器，一并清掉。） */
[data-frame-tier="square"] .kb-foot,
[data-frame-tier="portrait"] .kb-foot,
[data-frame-tier="tall"] .kb-foot {
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
[data-frame-tier="square"] .kb-note,
[data-frame-tier="portrait"] .kb-note,
[data-frame-tier="tall"] .kb-note {
  max-width: none;
  text-align: center;
}
/* 领奖台三座（空格键那座宽 88px）在窄栏里允许折行，不靠横滚 */
[data-frame-tier="square"] .podium,
[data-frame-tier="portrait"] .podium,
[data-frame-tier="tall"] .podium {
  flex-wrap: wrap;
  justify-content: center;
  row-gap: 14px;
}

/* ============ 「说给你听」语音与通话 ============ */

.voice-section {
  @apply mt-3;
  min-width: 0;
}

.voice-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.voice-rule {
  flex: 1;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.1);
  transform: translateY(-3px);
}
.voice-title {
  font-size: 12px;
  font-weight: 700;
  color: rgba(0,0,0,0.72);
}
.voice-sub {
  font-size: 10px;
  color: rgba(0,0,0,0.35);
}

/* ============ 微信留言机：与键盘同一产品线的桌面设备 ============ */

.am {
  position: relative;
  border-radius: 18px;
  width: 100%;
  margin-top: 10px;
  padding: 11px 14px 12px;
  background: linear-gradient(180deg, #f6f7f4 0%, #e7e9e3 58%, #dcdfd7 100%);
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    inset 0 -2px 3px rgba(0, 0, 0, 0.05),
    0 1.5px 0 1px #c6cabf,
    0 22px 44px -12px rgba(25, 60, 40, 0.26),
    0 5px 12px rgba(0, 0, 0, 0.06);
}

/* —— 机头：铭牌 + 录音灯 + 扬声孔 —— */

.am-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 2px;
}

.am-brand {
  font-size: 8px;
  color: rgba(0, 0, 0, 0.34);
  white-space: nowrap;
}

.am-led {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: radial-gradient(circle at 35% 30%, #d7d2c8, #a9a49a);
  box-shadow: inset 0 1px 1px rgba(0, 0, 0, 0.3);
  flex-shrink: 0;
}

.am-led--on {
  background: radial-gradient(circle at 35% 30%, #ff8a7c, #e5372a);
  box-shadow: 0 0 8px rgba(255, 90, 70, 0.7), inset 0 1px 1px rgba(0, 0, 0, 0.2);
}

/* 冲孔扬声网 */
.am-grille {
  margin-left: auto;
  width: 96px;
  height: 22px;
  background-image: radial-gradient(circle, rgba(0, 0, 0, 0.3) 1.05px, transparent 1.35px);
  background-size: 6px 5.5px;
  -webkit-mask-image: radial-gradient(70% 100% at 50% 50%, #000 55%, transparent 100%);
  mask-image: radial-gradient(70% 100% at 50% 50%, #000 55%, transparent 100%);
  opacity: 0.75;
}

/* —— 液晶屏：通话账目 —— */

.am-lcd {
  position: relative;
  margin-top: 9px;
  border-radius: 10px;
  padding: 8px 12px 9px;
  background: linear-gradient(180deg, #17211a 0%, #101812 100%);
  border: 1px solid rgba(0, 0, 0, 0.5);
  box-shadow:
    inset 0 3px 8px rgba(0, 0, 0, 0.65),
    0 1px 0 rgba(255, 255, 255, 0.7);
  overflow: hidden;
  color: #a7ecbc;
}

/* 屏面玻璃斜光 */
.am-lcd-glass {
  position: absolute;
  top: -40%;
  bottom: 30%;
  left: -10%;
  width: 45%;
  background: linear-gradient(100deg, transparent 0%, rgba(255, 255, 255, 0.06) 45%, transparent 100%);
  transform: skewX(-18deg);
  pointer-events: none;
}

.am-lcd-row1 {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.am-lcd-label {
  font-size: 8.5px;
  color: rgba(167, 236, 188, 0.55);
}

.am-lcd-time {
  font-size: 21px;
  font-weight: 700;
  font-family: ui-monospace, 'SF Mono', monospace;
  letter-spacing: 0.06em;
  line-height: 1;
  text-shadow: 0 0 8px rgba(110, 255, 170, 0.3);
}

.am-lcd-row2 {
  margin-top: 7px;
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 10.5px;
  font-weight: 600;
  font-family: ui-monospace, 'SF Mono', monospace;
  white-space: nowrap;
}

.am-lcd-row2 i {
  width: 1px;
  height: 9px;
  background: rgba(167, 236, 188, 0.25);
}

.am-lcd-missed {
  color: #ff9084;
  text-shadow: 0 0 7px rgba(255, 110, 95, 0.35);
}

.am-lcd-row3 {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 9.5px;
  color: rgba(167, 236, 188, 0.72);
  white-space: nowrap;
}

.am-kind {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-variant-numeric: tabular-nums;
}

.am-kind svg {
  width: 11px;
  height: 11px;
  opacity: 0.85;
}

/* —— 磁带舱 —— */

.am-tapebay {
  margin-top: 8px;
}

/* 机身丝印的 A/B 面账目 */
.am-sides {
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding: 0 2px 7px;
}

.am-sides-rule {
  width: 1px;
  background: rgba(0, 0, 0, 0.1);
}

.am-side {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.am-side-tag {
  font-size: 8.5px;
  color: rgba(0, 0, 0, 0.4);
  white-space: nowrap;
}

.am-side-val {
  font-size: 12.5px;
  font-weight: 700;
  color: #10241a;
  white-space: nowrap;
}

.am-side-val--dim {
  font-size: 10.5px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.4);
}

/* 磁带观察窗 */
.am-window {
  position: relative;
  height: 54px;
  border-radius: 9px;
  background: linear-gradient(180deg, #23271f 0%, #191c15 100%);
  border: 1px solid rgba(0, 0, 0, 0.4);
  box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.55), 0 1px 0 rgba(255, 255, 255, 0.6);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  overflow: hidden;
}

.tape-reel {
  position: relative;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* 带量盘：大小随说/听占比 */
.tape-pack {
  position: absolute;
  width: calc(20px + var(--pack, 0.5) * 22px);
  height: calc(20px + var(--pack, 0.5) * 22px);
  border-radius: 999px;
  background:
    repeating-radial-gradient(circle, rgba(255, 255, 255, 0.05) 0 1px, transparent 1px 3px),
    radial-gradient(circle, #2f2a24 0%, #171310 100%);
  box-shadow: 0 0 6px rgba(0, 0, 0, 0.6);
}

/* 齿轮轴心：转动 */
.tape-hub {
  position: relative;
  width: 17px;
  height: 17px;
  border-radius: 999px;
  background: repeating-conic-gradient(#f2f1ea 0deg 26deg, #b9beb4 26deg 60deg);
  box-shadow: inset 0 0 0 2.5px #e8e7df, inset 0 0 0 4px #7b8177;
  animation: tapeSpin 3.6s linear infinite;
}

.am--paused .tape-hub {
  animation-play-state: paused;
}

.am--fast .tape-hub {
  animation-duration: 0.85s;
}

@keyframes tapeSpin {
  to { transform: rotate(360deg); }
}

/* 两盘之间的走带 */
.tape-band {
  position: absolute;
  left: 36px;
  right: 36px;
  bottom: 9px;
  height: 3.5px;
  background: linear-gradient(180deg, #4a3f31, #2c251c);
  border-radius: 2px;
  opacity: 0.9;
}

/* 窗下小字：换算 + 年度最长一条 */
.am-strip {
  margin-top: 7px;
  padding: 0 2px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.am-strip-note {
  font-size: 9px;
  color: rgba(0, 0, 0, 0.38);
  white-space: nowrap;
}

.am-strip-longest {
  font-size: 9px;
  color: rgba(0, 0, 0, 0.44);
  white-space: nowrap;
}

.am-strip-longest b {
  font-weight: 650;
  color: #141414;
}

/* —— 走带键：同键帽工艺 —— */

.am-controls {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 7px;
}

.am-btn {
  width: 44px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid hsl(46, 10%, 76%);
  background:
    radial-gradient(130% 86% at 50% 4%, rgba(255, 255, 255, 0.42), transparent 52%),
    linear-gradient(180deg, hsl(46, 8%, 97%) 0%, hsl(46, 10%, 92%) 100%);
  box-shadow:
    0 2px 0 hsl(46, 10%, 83%),
    inset 0 1px 0 rgba(255, 255, 255, 0.62),
    inset 0 -1px 2px rgba(0, 0, 0, 0.1);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #4b4b45;
  cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
  -webkit-tap-highlight-color: transparent;
}

.am-btn svg {
  width: 12px;
  height: 8px;
}

.am-btn.is-down,
.am-btn:active {
  transform: translateY(1.5px);
  box-shadow:
    0 0.5px 0 hsl(46, 10%, 83%),
    inset 0 2px 4px rgba(0, 0, 0, 0.16);
}

.am-btn--rec {
  color: #c0392b;
}

.am-controls-note {
  margin-left: auto;
  font-size: 7.5px;
  color: rgba(0, 0, 0, 0.26);
  letter-spacing: 0.14em;
}

/* —— 单键拨号：相框位 —— */

.am-dial {
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px dashed rgba(0, 0, 0, 0.12);
}

.am-dial-tag {
  font-size: 8.5px;
  color: rgba(0, 0, 0, 0.36);
}

.am-dial-slots {
  margin-top: 8px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 12px;
}

.am-slot {
  width: 102px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  text-align: center;
}

/* 头像压在亚克力相框位里 */
.am-frame {
  position: relative;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(180deg, #fdfdfb, #ecebe4);
  border: 1px solid rgba(0, 0, 0, 0.12);
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.12), 0 1px 0 rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}

.am-frame::after {
  content: '';
  position: absolute;
  inset: 2px;
  border-radius: 8px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.4) 0%, transparent 42%);
  pointer-events: none;
}

.am-frame .v-avatar {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  box-shadow: none;
}

.am-slot-role {
  margin-top: 2px;
  font-size: 8px;
  color: rgba(0, 0, 0, 0.36);
  white-space: nowrap;
}

.am-slot-name {
  font-size: 11px;
  font-weight: 650;
  color: #141414;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.am-slot-note {
  font-size: 8.5px;
  line-height: 1.5;
  color: rgba(0, 0, 0, 0.4);
}

/* 圆头像（语音双方 / 年度最长 / 最常连线） */
.v-avatar {
  position: relative;
  width: 28px;
  height: 28px;
  border-radius: 9999px;
  overflow: hidden;
  flex-shrink: 0;
  background: #eef7ef;
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}
.v-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.v-avatar__fb {
  font-size: 12px;
  color: #07c160;
  user-select: none;
}

/* ============ 竖幅：留言机上的单行硬约束一律放开 ============
   横幅右栏有 ~385px 恒定宽度，竖幅里机身宽度改由画幅决定（1:1 约 426px、
   3:4/9:16 约 560px）。凡是「一行放不下就看不见」的写法（nowrap 撞上
   space-between 的兄弟、nowrap + overflow:hidden + ellipsis）在这里全部换成换行。
   —— 未接来电数、最长语音的对方昵称这类字段，宁可占两行也不能没有。 */

/* 液晶屏两行账目：通数/接通/未接、视频×N/语音×N */
[data-frame-tier="square"] .am-lcd-row2,
[data-frame-tier="portrait"] .am-lcd-row2,
[data-frame-tier="tall"] .am-lcd-row2,
[data-frame-tier="square"] .am-lcd-row3,
[data-frame-tier="portrait"] .am-lcd-row3,
[data-frame-tier="tall"] .am-lcd-row3 {
  flex-wrap: wrap;
  white-space: normal;
  row-gap: 4px;
}

/* 机头铭牌 / A·B 面账目 */
[data-frame-tier="square"] .am-brand,
[data-frame-tier="portrait"] .am-brand,
[data-frame-tier="tall"] .am-brand,
[data-frame-tier="square"] .am-side-tag,
[data-frame-tier="portrait"] .am-side-tag,
[data-frame-tier="tall"] .am-side-tag,
[data-frame-tier="square"] .am-side-val,
[data-frame-tier="portrait"] .am-side-val,
[data-frame-tier="tall"] .am-side-val {
  white-space: normal;
}

/* 窗下小字：换算 + 年度最长一条（含对方昵称） */
[data-frame-tier="square"] .am-strip-note,
[data-frame-tier="portrait"] .am-strip-note,
[data-frame-tier="tall"] .am-strip-note,
[data-frame-tier="square"] .am-strip-longest,
[data-frame-tier="portrait"] .am-strip-longest,
[data-frame-tier="tall"] .am-strip-longest {
  white-space: normal;
}

/* 单键拨号：三个相框位允许折行 */
[data-frame-tier="square"] .am-dial-slots,
[data-frame-tier="portrait"] .am-dial-slots,
[data-frame-tier="tall"] .am-dial-slots {
  flex-wrap: wrap;
  row-gap: 12px;
}

[data-frame-tier="square"] .am-slot-role,
[data-frame-tier="portrait"] .am-slot-role,
[data-frame-tier="tall"] .am-slot-role {
  white-space: normal;
}

/* 名字原本 nowrap + overflow:hidden + ellipsis，长昵称直接被截成「…」＝销毁数据 */
[data-frame-tier="square"] .am-slot-name,
[data-frame-tier="portrait"] .am-slot-name,
[data-frame-tier="tall"] .am-slot-name {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  overflow-wrap: anywhere;
  line-height: 1.35;
}

@media (prefers-reduced-motion: reduce) {
  .tape-hub { animation: none; }
  .ime-caret { animation: none; }
}

/* ========== 10级磨损视觉效果 ========== */

/* Level 1: 指纹油渍 - 中心淡淡油光 */
.kb-level-1 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 20%;
  background: radial-gradient(ellipse at center, rgba(255,255,255,0.15) 0%, transparent 70%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 2: 涂层初磨 - 边缘变薄 */
.kb-level-2 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 50%, rgba(180,160,140,0.12) 100%);
  pointer-events: none;
  border-radius: 4px;
}

/* Level 3: 涂层磨损 - 浅色磨痕纹理 */
.kb-level-3 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 30% 40%, rgba(160,140,120,0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 70% 60%, rgba(160,140,120,0.12) 0%, transparent 45%);
  pointer-events: none;
  border-radius: 4px;
}

/* Level 4: 涂层剥落 - 斑驳露底色 */
.kb-level-4 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 25% 35%, rgba(140,120,100,0.25) 0%, transparent 40%),
    radial-gradient(ellipse at 65% 55%, rgba(140,120,100,0.20) 0%, transparent 35%),
    radial-gradient(ellipse at 50% 70%, rgba(140,120,100,0.18) 0%, transparent 30%);
  pointer-events: none;
  border-radius: 4px;
}

/* Level 5: 表面凹陷 - 中心凹陷阴影 */
.kb-level-5 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.18),
    inset 0 -1px 2px rgba(0,0,0,0.24),
    inset 0 3px 6px rgba(0,0,0,0.15) !important;
}
.kb-level-5 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 15%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.12) 0%, transparent 70%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 6: 细微裂纹 - 边缘1-2条细裂纹 */
.kb-level-6 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.12),
    inset 0 -1px 2px rgba(0,0,0,0.28),
    inset 0 3px 8px rgba(0,0,0,0.18) !important;
}
.kb-level-6 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg,
      transparent 0%, transparent 72%,
      rgba(80,60,40,0.35) 72%, rgba(80,60,40,0.35) 73%,
      transparent 73%, transparent 100%
    ),
    linear-gradient(160deg,
      transparent 0%, transparent 78%,
      rgba(80,60,40,0.25) 78%, rgba(80,60,40,0.25) 79%,
      transparent 79%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
.kb-level-6 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 10%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.15) 0%, transparent 70%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 7: 网状龟裂 - 多条裂纹交叉 */
.kb-level-7 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.08),
    inset 0 -1px 2px rgba(0,0,0,0.32),
    inset 0 4px 10px rgba(0,0,0,0.22) !important;
}
.kb-level-7 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg,
      transparent 0%, transparent 25%,
      rgba(70,50,30,0.4) 25%, rgba(70,50,30,0.4) 26%,
      transparent 26%, transparent 65%,
      rgba(70,50,30,0.35) 65%, rgba(70,50,30,0.35) 66%,
      transparent 66%, transparent 100%
    ),
    linear-gradient(45deg,
      transparent 0%, transparent 35%,
      rgba(70,50,30,0.3) 35%, rgba(70,50,30,0.3) 36%,
      transparent 36%, transparent 70%,
      rgba(70,50,30,0.25) 70%, rgba(70,50,30,0.25) 71%,
      transparent 71%, transparent 100%
    ),
    linear-gradient(95deg,
      transparent 0%, transparent 40%,
      rgba(70,50,30,0.28) 40%, rgba(70,50,30,0.28) 41%,
      transparent 41%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
.kb-level-7 .kb-key-top::after {
  content: '';
  position: absolute;
  inset: 5%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.18) 0%, transparent 65%);
  pointer-events: none;
  border-radius: 50%;
}

/* Level 8: 缺角碎裂 - clip-path切割缺角 */
.kb-level-8 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.05),
    inset 0 -1px 2px rgba(0,0,0,0.36),
    inset 0 4px 12px rgba(0,0,0,0.25) !important;
}
.kb-level-8 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg,
      transparent 0%, transparent 20%,
      rgba(60,40,20,0.45) 20%, rgba(60,40,20,0.45) 21%,
      transparent 21%, transparent 55%,
      rgba(60,40,20,0.4) 55%, rgba(60,40,20,0.4) 56%,
      transparent 56%, transparent 100%
    ),
    linear-gradient(45deg,
      transparent 0%, transparent 30%,
      rgba(60,40,20,0.35) 30%, rgba(60,40,20,0.35) 31%,
      transparent 31%, transparent 65%,
      rgba(60,40,20,0.3) 65%, rgba(60,40,20,0.3) 66%,
      transparent 66%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
/* 缺角方向变体 */
.kb-broken-tl .kb-key-top {
  clip-path: polygon(18% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 22%);
}
.kb-broken-tr .kb-key-top {
  clip-path: polygon(0% 0%, 82% 0%, 100% 20%, 100% 100%, 0% 100%);
}
.kb-broken-bl .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 100%, 20% 100%, 0% 78%);
}
.kb-broken-br .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 80%, 82% 100%, 0% 100%);
}

/* Level 9: 严重破损 - 大面积不规则破碎 */
.kb-level-9 .kb-key-top {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.02),
    inset 0 -1px 2px rgba(0,0,0,0.40),
    inset 0 5px 14px rgba(0,0,0,0.30) !important;
}
.kb-level-9 .kb-key-top::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(125deg,
      transparent 0%, transparent 15%,
      rgba(50,30,10,0.5) 15%, rgba(50,30,10,0.5) 16%,
      transparent 16%, transparent 45%,
      rgba(50,30,10,0.45) 45%, rgba(50,30,10,0.45) 46%,
      transparent 46%, transparent 100%
    ),
    linear-gradient(55deg,
      transparent 0%, transparent 25%,
      rgba(50,30,10,0.4) 25%, rgba(50,30,10,0.4) 26%,
      transparent 26%, transparent 60%,
      rgba(50,30,10,0.35) 60%, rgba(50,30,10,0.35) 61%,
      transparent 61%, transparent 100%
    ),
    linear-gradient(170deg,
      transparent 0%, transparent 50%,
      rgba(50,30,10,0.38) 50%, rgba(50,30,10,0.38) 51%,
      transparent 51%, transparent 100%
    );
  pointer-events: none;
  border-radius: 4px;
  z-index: 2;
}
/* 严重破碎方向变体 */
.kb-shattered-tl .kb-key-top {
  clip-path: polygon(28% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 35%, 12% 18%);
}
.kb-shattered-tr .kb-key-top {
  clip-path: polygon(0% 0%, 72% 0%, 88% 15%, 100% 32%, 100% 100%, 0% 100%);
}
.kb-shattered-bl .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 100%, 30% 100%, 10% 82%, 0% 65%);
}
.kb-shattered-br .kb-key-top {
  clip-path: polygon(0% 0%, 100% 0%, 100% 68%, 90% 85%, 70% 100%, 0% 100%);
}

/* Level 10: 完全报废 - 键帽消失，显示轴体 */
.kb-level-10 .kb-key-top {
  opacity: 0 !important;
}
.kb-level-10::before {
  /* 轴座底座 - 深灰色凹槽 */
  background: linear-gradient(180deg, #3a3a3c 0%, #2c2c2e 100%) !important;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
}
.kb-level-10::after {
  content: '';
  position: absolute;
  /* 十字轴心居中（宽键也保持轴体原尺寸，不随键帽拉伸） */
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(40%, 13px);
  height: min(62%, 13px);
  /* Cherry MX 风格十字轴 */
  background:
    linear-gradient(90deg,
      transparent 0%, transparent 30%,
      #606065 30%, #707075 35%, #606065 40%,
      #555558 45%, #555558 55%,
      #606065 60%, #707075 65%, #606065 70%,
      transparent 70%, transparent 100%
    ),
    linear-gradient(0deg,
      transparent 0%, transparent 30%,
      #606065 30%, #707075 35%, #606065 40%,
      #555558 45%, #555558 55%,
      #606065 60%, #707075 65%, #606065 70%,
      transparent 70%, transparent 100%
    );
  border-radius: 1px;
  box-shadow:
    0 1px 2px rgba(0,0,0,0.4),
    inset 0 0 1px rgba(255,255,255,0.1);
  z-index: 1;
}

/* ============ 9:16（tall）放大：把重排省下的高度换成看得清的字号 ============
   判据只挂 tall —— wide / landscape / square / portrait 一个像素都不动。
   两条纪律：
   ① 字号一律绝对 px，不挂 cqh/vh —— 竖幅舞台变高不会二次放大；
   ② 下限统一 13px。原版里 6.5-9px 的丝印小字（书的版权行、留言机铭牌、
      走带键注脚、领奖台名次）在 9:16 下缩到人眼分辨不出，一律抬到 13px 以上。 */

/* —— hero：主问句、里程表大数、换算行 —— */
[data-frame-tier="tall"] .tf-q1 { font-size: 32px; }
[data-frame-tier="tall"] .tf-big { margin-top: 14px; gap: 12px; }
[data-frame-tier="tall"] .tf-big-num { font-size: 80px; }
[data-frame-tier="tall"] .tf-big-unit { font-size: 25px; }
[data-frame-tier="tall"] .tf-sent-cap { margin-top: 10px; font-size: 17px; }
[data-frame-tier="tall"] .tf-ask { margin-top: 15px; gap: 6px; }
[data-frame-tier="tall"] .tf-q2 { font-size: 15px; }
[data-frame-tier="tall"] .tf-bookline { font-size: 23px; }
[data-frame-tier="tall"] .tf-meta { margin-top: 16px; gap: 9px 13px; font-size: 17px; }
[data-frame-tier="tall"] .tf-meta-label { font-size: 15px; }
[data-frame-tier="tall"] .tf-meta-num { font-size: 28px; }
[data-frame-tier="tall"] .tf-meta-unit { font-size: 16px; margin-left: -5px; }
[data-frame-tier="tall"] .tf-meta-sep { height: 15px; }
[data-frame-tier="tall"] .tf-meta--empty { font-size: 16px; }

/* —— 书 + 纸摞：整体放大约 1.35 倍，封面小字同步抬到可读 —— */
[data-frame-tier="tall"] .tf-objs { gap: 18px; }
[data-frame-tier="tall"] .book { --bw: 158px; --bh: 180px; width: calc(var(--bw) + 30px); }
[data-frame-tier="tall"] .book-3d { margin-bottom: 20px; }
[data-frame-tier="tall"] .book-shadow { bottom: 18px; height: 28px; }
[data-frame-tier="tall"] .book-cover { gap: 8px; padding-bottom: 46px; }
[data-frame-tier="tall"] .book-frame { inset: 9px; }
[data-frame-tier="tall"] .book-emblem { width: 25px; height: 25px; }
[data-frame-tier="tall"] .book-title { font-size: 22px; }
[data-frame-tier="tall"] .book-year { font-size: 14px; }
[data-frame-tier="tall"] .book-author { bottom: 30px; font-size: 13px; letter-spacing: 0.2em; margin-right: -0.2em; }
/* 版权行原本 6.5px + 0.24em 字距：13px 下字距要收窄才放得进 158px 的封面 */
[data-frame-tier="tall"] .book-imprint { bottom: 11px; font-size: 13px; letter-spacing: 0.06em; margin-right: -0.06em; }
[data-frame-tier="tall"] .book-ribbon { bottom: -16px; width: 12px; height: 26px; }
[data-frame-tier="tall"] .book-cap { font-size: 14px; }
[data-frame-tier="tall"] .ream { width: 110px; }
[data-frame-tier="tall"] .ream-stack { height: calc(var(--rh) * 1.35); }
[data-frame-tier="tall"] .ream-sheet { height: 10px; }
/* 张数大到七位时 nowrap 会顶出纸摞宽度，竖幅放开换行 */
[data-frame-tier="tall"] .ream-cap { margin-top: 10px; font-size: 14px; white-space: normal; }

/* —— 输入法候选条 —— */
[data-frame-tier="tall"] .ime-bar { gap: 24px; margin-bottom: 22px; padding: 12px 18px; border-radius: 18px; }
[data-frame-tier="tall"] .ime-left { gap: 12px; min-height: 34px; }
[data-frame-tier="tall"] .ime-caret { width: 3px; height: 24px; }
[data-frame-tier="tall"] .ime-py { font-size: 20px; }
[data-frame-tier="tall"] .ime-cands { gap: 8px; margin-left: 8px; }
[data-frame-tier="tall"] .ime-cand { gap: 5px; padding: 4px 11px; border-radius: 11px; font-size: 18px; }
[data-frame-tier="tall"] .ime-cand-no { font-size: 13px; }
[data-frame-tier="tall"] .ime-hits { gap: 8px; }
[data-frame-tier="tall"] .ime-hits-num { font-size: 26px; }
[data-frame-tier="tall"] .ime-hits-unit { font-size: 14px; }

/* —— 键盘实体：键位 30→48px。竖幅列宽 852，整块键盘 15*48+14*4+26 = 802，放得下 ——
   （宽度公式见 .kb-w-* ：N*unit + (N-1)*gap，故 --kb-gap 也一并放大。） */
[data-frame-tier="tall"] .keyboard-body { --kb-gap: 4px; padding: 14px 16px 16px; border-radius: 22px; }
[data-frame-tier="tall"] .kb-key { --unit: 48px; height: 50px; }
[data-frame-tier="tall"] .kb-key::before { top: 3px; border-radius: 8px; }
[data-frame-tier="tall"] .kb-key-top { bottom: 3px; border-radius: 8px; }
[data-frame-tier="tall"] .kb-sub { font-size: 13px; margin-bottom: 2px; }
[data-frame-tier="tall"] .kb-label { font-size: 20px; }
[data-frame-tier="tall"] .kb-label-sm { font-size: 14px !important; }
[data-frame-tier="tall"] .kb-space-bar { height: 5px; }
[data-frame-tier="tall"] .keyboard-brand { margin-top: 12px; font-size: 13px; }
[data-frame-tier="tall"] .kb-hud-title { font-size: 16px; }
[data-frame-tier="tall"] .kb-hud-meta { font-size: 14px; }

/* —— 脚注 + 领奖台：竖幅列宽够宽（802），改回左右并排，省下一整段高度 —— */
[data-frame-tier="tall"] .kb-foot {
  flex-direction: row;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-top: 20px;
}
[data-frame-tier="tall"] .kb-note { max-width: 300px; text-align: left; font-size: 15px; line-height: 1.6; }
[data-frame-tier="tall"] .podium { gap: 26px; row-gap: 16px; }
[data-frame-tier="tall"] .pd-item { gap: 8px; }
/* .pd-key 的 --unit/height 特异性低于上面的 [tier] .kb-key，必须在这里重新钉一遍 */
[data-frame-tier="tall"] .pd-key { --unit: 58px; height: 62px; }
[data-frame-tier="tall"] .pd-key--space { --unit: 120px; width: var(--unit); }
[data-frame-tier="tall"] .pd-key .kb-label { font-size: 22px !important; }
[data-frame-tier="tall"] .pd-medal { top: -9px; right: -9px; width: 24px; height: 24px; }
[data-frame-tier="tall"] .pd-medal b { font-size: 13px; }
[data-frame-tier="tall"] .pd-name { font-size: 17px; }
[data-frame-tier="tall"] .pd-hits { font-size: 14px; }

/* —— 说给你听：留言机改双栏机身 ——
   竖幅整宽 852 下，单列机身按放大后的字号会长到 570+px，本卡装不下；
   液晶屏与走带键归左、磁带舱归右、单键拨号横跨整宽，
   阅读顺序仍是 通话账目 → 磁带 → 走带键 → 单键拨号。 */
[data-frame-tier="tall"] .tf-root > .voice-section { max-width: none; margin-inline: 0; margin-top: 0; }
[data-frame-tier="tall"] .voice-header { gap: 14px; }
[data-frame-tier="tall"] .voice-title { font-size: 18px; }
[data-frame-tier="tall"] .voice-sub { font-size: 14px; }
[data-frame-tier="tall"] .am {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 20px;
  row-gap: 10px;
  margin-top: 12px;
  padding: 14px 18px 16px;
  border-radius: 24px;
}
[data-frame-tier="tall"] .am > .am-head { grid-column: 1 / -1; }
[data-frame-tier="tall"] .am > .am-lcd { grid-column: 1; }
[data-frame-tier="tall"] .am > .am-tapebay { grid-column: 2; grid-row: span 2; }
[data-frame-tier="tall"] .am > .am-controls { grid-column: 1; align-self: start; }
[data-frame-tier="tall"] .am > .am-dial { grid-column: 1 / -1; }
/* 只有通话没有语音时右栏整个缺席，液晶屏改占满机身，免得半边空着 */
[data-frame-tier="tall"] .am:not(:has(.am-tapebay)) > .am-lcd { grid-column: 1 / -1; }

[data-frame-tier="tall"] .am-head { gap: 14px; }
[data-frame-tier="tall"] .am-brand { font-size: 13px; }
[data-frame-tier="tall"] .am-led { width: 9px; height: 9px; }
[data-frame-tier="tall"] .am-grille { width: 130px; height: 28px; background-size: 8px 7px; }
[data-frame-tier="tall"] .am-lcd { margin-top: 0; padding: 11px 16px 12px; border-radius: 14px; }
[data-frame-tier="tall"] .am-lcd-label { font-size: 13px; }
[data-frame-tier="tall"] .am-lcd-time { font-size: 30px; }
[data-frame-tier="tall"] .am-lcd-row2 { margin-top: 10px; gap: 12px; font-size: 16px; }
[data-frame-tier="tall"] .am-lcd-row2 i { height: 13px; }
[data-frame-tier="tall"] .am-lcd-row3 { margin-top: 9px; gap: 18px; font-size: 15px; }
[data-frame-tier="tall"] .am-kind svg { width: 16px; height: 16px; }
[data-frame-tier="tall"] .am-tapebay { margin-top: 0; }
[data-frame-tier="tall"] .am-sides { gap: 16px; padding: 0 2px 9px; }
[data-frame-tier="tall"] .am-side-tag { font-size: 13px; }
[data-frame-tier="tall"] .am-side-val { font-size: 18px; }
[data-frame-tier="tall"] .am-side-val--dim { font-size: 15px; }
[data-frame-tier="tall"] .am-window { height: 82px; padding: 0 20px; border-radius: 12px; }
[data-frame-tier="tall"] .tape-reel { width: 60px; height: 60px; }
[data-frame-tier="tall"] .tape-pack { width: calc(28px + var(--pack, 0.5) * 30px); height: calc(28px + var(--pack, 0.5) * 30px); }
[data-frame-tier="tall"] .tape-hub { width: 23px; height: 23px; }
[data-frame-tier="tall"] .tape-band { left: 46px; right: 46px; bottom: 12px; height: 5px; }
[data-frame-tier="tall"] .am-strip { margin-top: 10px; gap: 6px 14px; }
[data-frame-tier="tall"] .am-strip-note,
[data-frame-tier="tall"] .am-strip-longest { font-size: 13px; }
/* 走带键 + REW/PLAY/FF/REC 注脚在半幅栏里一行放不下，允许注脚落到第二行 */
[data-frame-tier="tall"] .am-controls { flex-wrap: wrap; gap: 10px; margin-top: 12px; }
[data-frame-tier="tall"] .am-btn { width: 56px; height: 34px; border-radius: 8px; }
[data-frame-tier="tall"] .am-btn svg { width: 16px; height: 11px; }
[data-frame-tier="tall"] .am-controls-note { font-size: 13px; letter-spacing: 0.1em; }
[data-frame-tier="tall"] .am-dial { margin-top: 4px; padding-top: 12px; }
[data-frame-tier="tall"] .am-dial-tag { font-size: 13px; }
[data-frame-tier="tall"] .am-dial-slots { margin-top: 18px; gap: 26px; }
[data-frame-tier="tall"] .am-slot { width: 152px; gap: 5px; }
[data-frame-tier="tall"] .am-frame { width: 58px; height: 58px; border-radius: 15px; }
[data-frame-tier="tall"] .am-frame .v-avatar { width: 47px; height: 47px; border-radius: 12px; }
[data-frame-tier="tall"] .am-slot-role { margin-top: 3px; font-size: 13px; }
[data-frame-tier="tall"] .am-slot-name { font-size: 18px; }
[data-frame-tier="tall"] .am-slot-note { font-size: 13px; }
[data-frame-tier="tall"] .v-avatar__fb { font-size: 17px; }

/* 飞出的字母/入册的词：键帽放大后原来的 15-16px 粒子显得像灰尘 */
[data-frame-tier="tall"] .tf-fx :deep(.tf-glyph) { font-size: 24px; }
[data-frame-tier="tall"] .tf-fx :deep(.tf-word) { font-size: 19px; padding: 4px 12px; border-radius: 11px; }

/* ============ 9:20（804×1788，手机满屏）：tall 档里更窄更高的那一支 ============
   它比 9:16 窄 96px、高 188px，tall 的规则会先全部吃到，再由本段覆写。
   本段所有选择器与 tall 段同特异性（0,2,0），靠「写在后面」生效 —— 不要往前挪。

   ① 【必修】键盘实体出画幅：tall 的 15*48 + 14*4 + 32 + 2 = 810，而 9:20 的列宽只有
      804-48 = 756。.kb-stage 是 width:fit-content，撑不下就整块溢出到画幅外
      （实测 .tf-root scrollWidth 834，键盘铭牌与领奖台第三名被画幅右缘切掉）。
      收键位到 45px、间距 3px、机身内边距 12px：15*45 + 14*3 + 24 + 2 = 743，落回 756 内。
   ② 【放大】多出来的 188px 高度：书与纸摞从 hero 右手边落到自己一行，hero 拿回整宽
      756（原来只有 416），大数、换算行、元数据行随之升档；书本身也放大一圈。
      这是重排换来的放大，不是把 row-gap 摊开。 */

/* —— 版式：hero 独占整宽，书纸自成一行 —— */
[data-frame="9:20"] .tf-root {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas:
    'hero'
    'objs'
    'kb'
    'voice';
  row-gap: 14px;
}
[data-frame="9:20"] .tf-root > .tf-objs { align-self: center; justify-content: center; }

/* —— hero：整宽之后关键读数整体升一档（大数 80 → 96） —— */
[data-frame="9:20"] .tf-q1 { font-size: 34px; }
[data-frame="9:20"] .tf-big { margin-top: 12px; gap: 14px; }
[data-frame="9:20"] .tf-big-num { font-size: 96px; }
[data-frame="9:20"] .tf-big-unit { font-size: 30px; }
[data-frame="9:20"] .tf-sent-cap { margin-top: 10px; font-size: 18px; }
[data-frame="9:20"] .tf-ask { margin-top: 14px; gap: 8px; }
[data-frame="9:20"] .tf-q2 { font-size: 16px; }
[data-frame="9:20"] .tf-bookline { font-size: 26px; }
[data-frame="9:20"] .tf-meta { margin-top: 16px; gap: 8px 16px; font-size: 18px; }
[data-frame="9:20"] .tf-meta-label { font-size: 16px; }
[data-frame="9:20"] .tf-meta-num { font-size: 31px; }
[data-frame="9:20"] .tf-meta-unit { font-size: 17px; margin-left: -6px; }
[data-frame="9:20"] .tf-meta-sep { height: 17px; }

/* —— 书 + 纸摞：独占一行，横向摊开并放大一圈 —— */
[data-frame="9:20"] .tf-objs { gap: 44px; }
[data-frame="9:20"] .book { --bw: 172px; --bh: 190px; width: calc(var(--bw) + 32px); }
[data-frame="9:20"] .book-3d { margin-bottom: 18px; }
[data-frame="9:20"] .book-shadow { bottom: 16px; height: 28px; }
[data-frame="9:20"] .book-cover { gap: 8px; padding-bottom: 48px; }
[data-frame="9:20"] .book-frame { inset: 10px; }
[data-frame="9:20"] .book-emblem { width: 27px; height: 27px; }
[data-frame="9:20"] .book-title { font-size: 24px; }
[data-frame="9:20"] .book-year { font-size: 15px; }
[data-frame="9:20"] .book-author { bottom: 32px; font-size: 14px; }
[data-frame="9:20"] .book-imprint { bottom: 12px; font-size: 13px; }
[data-frame="9:20"] .book-ribbon { bottom: -16px; width: 13px; height: 28px; }
[data-frame="9:20"] .book-cap { font-size: 15px; }
[data-frame="9:20"] .ream { width: 124px; }
[data-frame="9:20"] .ream-stack { height: calc(var(--rh) * 1.5); }
[data-frame="9:20"] .ream-sheet { height: 11px; }
[data-frame="9:20"] .ream-cap { margin-top: 8px; font-size: 15px; }

/* —— 输入法候选条：跟着窄下来的键盘走 —— */
[data-frame="9:20"] .ime-bar { gap: 18px; margin-bottom: 16px; padding: 12px 16px; }
[data-frame="9:20"] .ime-hits-num { font-size: 28px; }

/* —— 键盘实体：唯一的出画幅点。45 + 3 + 12 是 756 列宽下的上限组合 —— */
[data-frame="9:20"] .keyboard-body { --kb-gap: 3px; padding: 13px 12px 14px; }
[data-frame="9:20"] .kb-key { --unit: 45px; height: 46px; }
[data-frame="9:20"] .kb-label { font-size: 19px; }
/* 领奖台键帽是复刻的大号键，必须在 .kb-key 之后重新钉一遍（同特异性） */
[data-frame="9:20"] .pd-key { --unit: 58px; height: 62px; }
[data-frame="9:20"] .pd-key--space { --unit: 120px; width: var(--unit); }
[data-frame="9:20"] .pd-key .kb-label { font-size: 22px !important; }
[data-frame="9:20"] .kb-foot { margin-top: 18px; }

/* —— 说给你听：整宽 756 的机身，构件按 tall 档不再加码（高度已排满） —— */
[data-frame="9:20"] .am-window { height: 88px; }
[data-frame="9:20"] .tape-reel { width: 64px; height: 64px; }
[data-frame="9:20"] .tape-pack { width: calc(30px + var(--pack, 0.5) * 32px); height: calc(30px + var(--pack, 0.5) * 32px); }
[data-frame="9:20"] .tape-hub { width: 25px; height: 25px; }
[data-frame="9:20"] .am-controls { margin-top: 10px; }
[data-frame="9:20"] .am-dial-slots { margin-top: 14px; }
[data-frame="9:20"] .am-frame { width: 62px; height: 62px; border-radius: 16px; }
[data-frame="9:20"] .am-frame .v-avatar { width: 50px; height: 50px; border-radius: 13px; }
[data-frame="9:20"] .am-slot-name { font-size: 19px; }
[data-frame="9:20"] .v-avatar__fb { font-size: 18px; }
</style>
