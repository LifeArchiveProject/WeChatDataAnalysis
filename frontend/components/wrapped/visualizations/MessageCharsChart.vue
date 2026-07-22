<template>
  <div ref="rootEl" class="w-full">
    <!-- 聊天气泡区域 -->
    <div class="rounded-2xl border border-[#00000010] bg-[#F5F5F5] p-3 sm:p-4">
      <div class="flex flex-col gap-3">
        <!-- Received (left) -->
        <div class="flex items-start gap-2">
          <div class="avatar-box bg-white">
            <svg viewBox="0 0 24 24" class="w-4 h-4" fill="none" stroke="#07C160" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M8 3h10a2 2 0 0 1 2 2v14H6V5a2 2 0 0 1 2-2z" />
              <path d="M6 7H4a2 2 0 0 0-2 2v10h4" />
            </svg>
          </div>
          <div class="px-3 py-2 text-sm max-w-[85%] relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-white text-gray-800 bubble-tail-l">
            <div class="wrapped-label text-xs text-[#00000066]">你收到的字</div>
            <div class="mt-0.5 wrapped-number text-xl sm:text-2xl text-[#000000e6]">
              {{ formatInt(receivedChars) }}
            </div>
            <div class="mt-1 wrapped-body text-xs text-[#7F7F7F]">
              <template v-if="receivedA4Text">{{ receivedA4Text }}</template>
              <template v-else-if="receivedChars > 0">这么多字，都是别人认真对你的回应。</template>
              <template v-else>今年还没有收到文字消息。</template>
            </div>
            <div v-if="receivedA4 && receivedA4.a4 && receivedA4.a4.sheets > 0" class="mt-1 text-[10px] text-[#00000055] wrapped-label">
              约 {{ formatInt(receivedA4.a4.sheets) }} 张 A4
            </div>
            <!-- A4 纸堆叠高度：高度柱 + count-up 标签 -->
            <div v-if="a4HeightCm > 0" class="a4-compare">
              <div class="a4-col">
                <div ref="a4BarEl" class="a4-col-fill" :style="{ height: `${a4BarPx}px` }"></div>
              </div>
              <div class="wrapped-label text-[10px] text-[#00000066]">
                叠起来 ≈ <span class="wrapped-number text-[#07C160]">{{ a4HeightDisplay }}</span> {{ a4HeightUnit }}
              </div>
            </div>
          </div>
        </div>

        <!-- Sent (right) -->
        <div class="flex items-start gap-2 justify-end">
          <div class="px-3 py-2 text-sm max-w-[85%] relative msg-bubble whitespace-pre-wrap break-words leading-relaxed bg-[#95EC69] text-black bubble-tail-r">
            <div class="wrapped-label text-xs text-[#00000080] text-right">你发送的字</div>
            <div class="mt-0.5 wrapped-number text-xl sm:text-2xl text-[#000000e6] text-right">
              {{ formatInt(sentChars) }}
            </div>
            <div class="mt-1 wrapped-body text-xs text-[#00000099] text-right">
              <template v-if="sentBookText">{{ sentBookText }}</template>
              <template v-else-if="sentChars > 0">这么多字，是你打出的每一次认真。</template>
              <template v-else>今年还没有文字消息。</template>
            </div>
          </div>
          <div class="avatar-box bg-[#95EC69]">
            <svg viewBox="0 0 24 24" class="w-4 h-4" fill="none" stroke="#1f2d1f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- 键盘磨损可视化 -->
    <div class="keyboard-outer">
      <div class="keyboard-inner">
        <!-- 顶部信息 -->
        <div class="keyboard-header">
          <div class="keyboard-dots">
            <span class="dot dot-red"></span>
            <span class="dot dot-yellow"></span>
            <span class="dot dot-green"></span>
          </div>
          <div class="keyboard-hint">键帽磨损程度反映你的打字频率</div>
          <div class="keyboard-stats">{{ totalHitsDisplay }} 次敲击</div>
        </div>

        <!-- 键盘主体 -->
        <div ref="keyboardBodyEl" class="keyboard-body">
          <div v-for="(row, ri) in keyboardRows" :key="ri" :ref="(el) => setRowEl(el, ri)" class="kb-row">
            <div
              v-for="(key, ci) in row"
              :key="`${ri}-${ci}`"
              class="kb-key"
              :class="[`kb-w-${key.w || 1}`, { 'kb-space': key.isSpace, 'kb-func': key.isFunc }, getKeyClasses(key.code)]"
              :style="getKeyStyle(key.code)"
              @mouseenter="showKeyTip($event, key)"
              @mouseleave="hideKeyTip"
              @pointerdown="showKeyTip($event, key)"
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

          <!-- 单键 tooltip -->
          <div v-if="keyTooltip" class="kb-tooltip" :style="{ left: `${keyTooltip.x}px`, top: `${keyTooltip.y}px` }">
            {{ keyTooltip.text }}
          </div>
        </div>

        <!-- Top3 磨损键徽章 -->
        <div v-if="topWornKeys.length" class="kb-top-badges">
          <div v-for="(k, i) in topWornKeys" :key="k.code" class="kb-top-badge">
            <span class="kb-top-rank wrapped-number">{{ i + 1 }}</span>
            <span class="kb-top-name wrapped-number">{{ k.name }}</span>
            <span class="kb-top-hits wrapped-label">{{ formatInt(k.hits) }} 次</span>
          </div>
        </div>

        <!-- 底部品牌 -->
        <div class="keyboard-brand">微信机械键盘</div>
      </div>
    </div>

    <!-- 「说给你听」语音与通话（旧缓存无 voice/calls 字段时整区隐藏） -->
    <div v-if="showVoiceCalls" class="voice-outer">
      <div class="voice-header">
        <span class="voice-title wrapped-label">说给你听</span>
        <span class="voice-sub wrapped-label">语音与通话</span>
      </div>

      <div class="voice-grid" :class="{ 'voice-grid-2': hasVoice && hasCalls }">
        <!-- 语音消息 -->
        <div v-if="hasVoice" class="voice-block">
          <template v-if="voiceSentSeconds > 0">
            <div class="voice-big">
              <span class="wrapped-number voice-big-num">{{ voiceNumDisplay }}</span>
              <span class="voice-big-unit wrapped-label">{{ voiceMainUnit }}语音</span>
            </div>
            <div class="voice-analogy wrapped-body">{{ voiceAnalogyText }}</div>
          </template>
          <div v-else class="voice-analogy wrapped-body">
            今年你更多在听<template v-if="topReceivedPartnerName">，最常听 <span class="wrapped-privacy-name text-[#07C160]">{{ topReceivedPartnerName }}</span> 说话</template>。
          </div>

          <div class="voice-wave" :class="{ 'wave-paused': wavePaused }" aria-hidden="true">
            <span v-for="i in 24" :key="i" :style="waveBarStyle(i)"></span>
          </div>

          <div class="voice-meta wrapped-label">
            发出 {{ formatInt(voiceSentCount) }} 条<template v-if="voiceReceivedCount > 0"> · 收到 {{ formatInt(voiceReceivedCount) }} 条 / {{ formatDurationShort(voiceReceivedSeconds) }}</template>
          </div>
          <div v-if="topSentPartnerName" class="voice-meta wrapped-label">
            最常说给 <span class="wrapped-privacy-name text-[#07C160]">{{ topSentPartnerName }}</span> 听
          </div>

          <!-- 年度最长语音：微信绿气泡复刻 -->
          <div v-if="longestVoice" class="voice-longest">
            <div class="voice-longest-head wrapped-label">
              年度最长语音 · {{ longestIsSent ? '发给' : '来自' }}
              <span class="wrapped-privacy-name">{{ longestVoiceName || '神秘好友' }}</span>
              <template v-if="longestVoice.date"> · {{ longestVoice.date }}</template>
            </div>
            <div class="flex items-center gap-2" :class="{ 'flex-row-reverse': longestIsSent }">
              <div class="avatar-box overflow-hidden wrapped-privacy-avatar" :class="longestIsSent ? 'bg-[#95EC69]' : 'bg-white'">
                <img
                  v-if="longestAvatarUrl && longestAvatarOk"
                  :src="longestAvatarUrl"
                  class="w-full h-full object-cover"
                  alt="avatar"
                  @error="longestAvatarOk = false"
                />
                <span v-else class="wrapped-number text-sm text-[#07C160] select-none">{{ longestAvatarFallback }}</span>
              </div>
              <div
                class="voice-bubble"
                :class="longestIsSent ? 'voice-bubble-sent' : 'voice-bubble-recv'"
                :style="{ width: longestBubbleWidth }"
              >
                <svg viewBox="0 0 12 12" class="voice-play" :class="{ 'voice-play-sent': longestIsSent }" aria-hidden="true">
                  <path d="M3 2l7 4-7 4z" fill="currentColor" />
                </svg>
                <span class="voice-dur wrapped-number">{{ longestSecondsText }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 通话 -->
        <div v-if="hasCalls" class="voice-block">
          <div class="voice-meta wrapped-label">通话总时长</div>
          <div class="flip-clock">
            <span
              v-for="(ch, i) in callsDurationDigits"
              :key="i"
              :class="ch === ':' ? 'flip-sep' : 'flip-digit'"
            >{{ ch }}</span>
          </div>
          <div class="voice-meta wrapped-label">
            全年 {{ formatInt(callsTotalCount) }} 通 · 接通 {{ formatInt(callsConnectedCount) }} 通
            <span v-if="callsMissedCount > 0" class="call-missed-badge wrapped-number">未接通 {{ formatInt(callsMissedCount) }}</span>
          </div>

          <!-- 视频 / 语音次数对比 -->
          <div class="call-bars">
            <div class="call-bar-row">
              <span class="call-bar-name wrapped-label">视频</span>
              <div class="call-bar-track">
                <div class="call-bar-fill call-bar-video" :style="{ width: `${callBarPct(callsVideoCount)}%` }"></div>
              </div>
              <span class="call-bar-count wrapped-number">{{ formatInt(callsVideoCount) }}</span>
            </div>
            <div class="call-bar-row">
              <span class="call-bar-name wrapped-label">语音</span>
              <div class="call-bar-track">
                <div class="call-bar-fill call-bar-voice" :style="{ width: `${callBarPct(callsVoiceCount)}%` }"></div>
              </div>
              <span class="call-bar-count wrapped-number">{{ formatInt(callsVoiceCount) }}</span>
            </div>
          </div>

          <div v-if="callsTopPartnerName" class="voice-meta wrapped-label">
            最常连线 <span class="wrapped-privacy-name text-[#07C160]">{{ callsTopPartnerName }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { gsap } from 'gsap'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useCountUp } from '~/composables/useCountUp'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  // deck 翻到本卡时置 true，首次为 true 触发入场编排；false 时暂停循环动画。
  isActive: { type: Boolean, default: true }
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const reducedMotion = useReducedMotion()

const sentChars = computed(() => Number(props.data?.sentChars || 0))
const receivedChars = computed(() => Number(props.data?.receivedChars || 0))

const sentBookText = computed(() => props.data?.sentBook?.text || '')
const receivedA4 = computed(() => props.data?.receivedA4 || null)
const receivedA4Text = computed(() => receivedA4.value?.text || '')

// ========== A4 纸高度对比 ==========

const a4HeightCm = computed(() => Number(receivedA4.value?.a4?.heightCm ?? receivedA4.value?.heightCm ?? 0))
const a4UseMeters = computed(() => a4HeightCm.value >= 100)
const a4HeightValue = computed(() => (a4UseMeters.value ? a4HeightCm.value / 100 : a4HeightCm.value))
const a4HeightUnit = computed(() => (a4UseMeters.value ? '米' : '厘米'))
// 对数刻度：几厘米到几米都能看出柱高差异
const a4BarPx = computed(() => {
  const cm = a4HeightCm.value
  if (cm <= 0) return 0
  return Math.round(6 + Math.min(1, Math.log1p(cm) / Math.log1p(500)) * 42)
})
const { display: a4HeightDisplay, play: playA4Height, finish: finishA4Height } = useCountUp(
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
const { display: voiceNumDisplay, play: playVoiceNum, finish: finishVoiceNum } = useCountUp(
  () => voiceMainNumber.value,
  { duration: 1.2, delay: 0.1 }
)

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
// 气泡宽度随时长增长（微信同款观感），60 秒封顶
const longestBubbleWidth = computed(() => {
  const s = Number(longestVoice.value?.seconds || 0)
  return `${Math.round(35 + Math.min(1, s / 60) * 55)}%`
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

// 通话
const callsTotalCount = computed(() => Number(calls.value?.totalCount || 0))
const callsConnectedCount = computed(() => Number(calls.value?.connectedCount || 0))
const callsVideoCount = computed(() => Number(calls.value?.videoCount || 0))
const callsVoiceCount = computed(() => Number(calls.value?.voiceCount || 0))
const callsMissedCount = computed(() => Number(calls.value?.missedOrCanceledCount || 0))
const callsTopPartnerName = computed(() => partnerName(calls.value?.topPartner))

// 翻牌数字：有小时则 H:MM:SS，否则 MM:SS
const callsDurationDigits = computed(() => {
  const total = Math.max(0, Math.round(Number(calls.value?.totalSeconds || 0)))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n) => String(n).padStart(2, '0')
  const str = h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
  return str.split('')
})

const callBarPct = (n) => {
  const mx = Math.max(callsVideoCount.value, callsVoiceCount.value, 1)
  return Math.max(4, Math.round((Number(n) || 0) / mx * 100))
}

// 声波条：固定伪随机高度序列，避免每次渲染跳变
const WAVE_HEIGHTS = [0.35, 0.65, 0.5, 0.9, 0.45, 0.75, 0.6, 1, 0.5, 0.8, 0.4, 0.7, 0.55, 0.85, 0.45, 0.95, 0.6, 0.75, 0.4, 0.65, 0.5, 0.85, 0.45, 0.6]
const waveBarStyle = (i) => ({
  '--wave-h': WAVE_HEIGHTS[(i - 1) % WAVE_HEIGHTS.length],
  animationDelay: `${((i - 1) % 8) * -0.11}s`
})
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

const { display: totalHitsDisplay, play: playTotalHits, finish: finishTotalHits } = useCountUp(
  () => totalKeyHits.value,
  { duration: 1.4 }
)

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
const getKeyStyle = (code) => {
  const w = effectiveWear(code)
  const level = getWearLevel(w)
  const progress = getWearProgress(w)

  // 等级对应的基础亮度和饱和度
  const levelParams = [
    { l: 94, s: 8 },   // 0: 全新
    { l: 92, s: 12 },  // 1: 指纹油渍
    { l: 89, s: 16 },  // 2: 涂层初磨
    { l: 85, s: 20 },  // 3: 涂层磨损
    { l: 80, s: 24 },  // 4: 涂层剥落
    { l: 76, s: 26 },  // 5: 表面凹陷
    { l: 72, s: 28 },  // 6: 细微裂纹
    { l: 68, s: 30 },  // 7: 网状龟裂
    { l: 64, s: 32 },  // 8: 缺角碎裂
    { l: 60, s: 34 },  // 9: 严重破损
    { l: 45, s: 10 },  // 10: 完全报废（轴体底座）
  ]
  // 高光/凹陷深度、标签透明度/模糊度随等级变化
  const highlightLevels = [0.55, 0.48, 0.40, 0.32, 0.24, 0.18, 0.12, 0.08, 0.05, 0.02, 0]
  const depthLevels = [0.12, 0.14, 0.16, 0.18, 0.20, 0.24, 0.28, 0.32, 0.36, 0.40, 0.45]
  const opacityLevels = [1, 0.95, 0.88, 0.75, 0.55, 0.35, 0.18, 0.08, 0.03, 0.01, 0]
  const blurLevels = [0, 0.2, 0.4, 0.7, 1.0, 1.4, 1.8, 2.2, 2.6, 3.0, 3.5]

  // 等级内平滑插值
  const lerpLevel = (arr) => arr[level] + (arr[Math.min(level + 1, 10)] - arr[level]) * progress
  const current = levelParams[level]
  const next = levelParams[Math.min(level + 1, 10)]
  const baseL = current.l + (next.l - current.l) * progress
  const sat = current.s + (next.s - current.s) * progress

  return {
    '--key-bg': `hsl(40, ${sat}%, ${baseL}%)`,
    '--key-bg-dark': `hsl(40, ${sat}%, ${baseL - 6}%)`,
    '--key-border': `hsl(40, ${Math.max(0, sat - 2)}%, ${baseL - 18}%)`,
    '--key-highlight': lerpLevel(highlightLevels).toFixed(3),
    '--key-depth': lerpLevel(depthLevels).toFixed(3),
    '--wear-opacity': lerpLevel(opacityLevels).toFixed(3),
    '--wear-blur': `${lerpLevel(blurLevels).toFixed(2)}px`,
  }
}

// ========== 单键 tooltip 与 Top3 徽章 ==========

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

const keyTooltip = ref(null) // { text, x, y }
const keyboardBodyEl = ref(null)

const showKeyTip = (evt, key) => {
  const body = keyboardBodyEl.value
  const target = evt?.currentTarget
  if (!body || !target) return
  const code = key.code.toLowerCase()
  const hits = Number(keyHitsMap.value[code] || 0)
  const rank = keyRankMap.value[code]
  const title = key.isSpace ? '空格键' : `${key.label || key.code} 键`
  const bodyRect = body.getBoundingClientRect()
  const keyRect = target.getBoundingClientRect()
  keyTooltip.value = {
    text: hits > 0 && rank
      ? `${title} · 敲击 ${formatInt(hits)} 次 · 全键盘第 ${rank}`
      : `${title} · 今年还没敲过`,
    // 边缘键做水平钳制，避免 tooltip 超出键盘
    x: Math.min(Math.max(keyRect.left - bodyRect.left + keyRect.width / 2, 64), bodyRect.width - 64),
    y: keyRect.top - bodyRect.top,
  }
}
const hideKeyTip = () => { keyTooltip.value = null }
const hideKeyTipTouch = (evt) => { if (evt?.pointerType !== 'mouse') hideKeyTip() }

// ========== 入场编排 ==========

const rootEl = ref(null)
const a4BarEl = ref(null)
const rowEls = []
const setRowEl = (el, ri) => { rowEls[ri] = el || null }

let hasEntered = false
let entranceTl = null

const finishAll = () => {
  wearReveal.value = 1
  clipRevealed.value = true
  finishTotalHits()
  finishVoiceNum()
  finishA4Height()
}

const buildTimeline = () => {
  const root = rootEl.value
  if (!root) {
    finishAll()
    return
  }
  const tl = gsap.timeline()

  // a. 键盘按行波浪「压下弹起」
  rowEls.forEach((rowEl, ri) => {
    if (!rowEl || !rowEl.children?.length) return
    tl.to(rowEl.children, {
      y: 2,
      duration: 0.09,
      ease: 'power1.in',
      yoyo: true,
      repeat: 1,
      stagger: 0.018,
    }, 0.05 + ri * 0.11)
  })

  // b. 磨损显影：全新态 → 目标等级；结束后再切 Level 8-10 的 clip-path 类
  tl.to(wearReveal, { value: 1, duration: 1.2, ease: 'power1.inOut' }, 0.35)
  tl.add(() => { clipRevealed.value = true }, 1.58)

  // c. 总敲击数 count-up
  tl.add(() => { playTotalHits() }, 0.4)

  // Top3 磨损键徽章依次弹入
  const badges = root.querySelectorAll('.kb-top-badge')
  if (badges.length) {
    tl.from(badges, { opacity: 0, scale: 0.6, y: 6, duration: 0.4, ease: 'back.out(2)', stagger: 0.12 }, 1.65)
  }

  // A4 高度柱 + count-up 标签
  if (a4BarEl.value) {
    tl.fromTo(a4BarEl.value, { scaleY: 0 }, { scaleY: 1, duration: 0.9, ease: 'power2.out' }, 0.55)
    tl.add(() => { playA4Height() }, 0.55)
  }

  // 「说给你听」区
  if (showVoiceCalls.value) {
    tl.add(() => { playVoiceNum() }, 0.5)
    const longest = root.querySelector('.voice-longest')
    if (longest) tl.from(longest, { opacity: 0, y: 10, duration: 0.5, ease: 'power2.out' }, 0.8)
    const flips = root.querySelectorAll('.flip-digit, .flip-sep')
    if (flips.length) {
      tl.from(flips, { rotationX: -90, opacity: 0, duration: 0.5, ease: 'back.out(1.6)', stagger: 0.06, transformOrigin: '50% 50% -12px' }, 0.9)
    }
    const fills = root.querySelectorAll('.call-bar-fill')
    if (fills.length) {
      tl.fromTo(fills, { scaleX: 0 }, { scaleX: 1, duration: 0.7, ease: 'power2.out', stagger: 0.15, transformOrigin: 'left center' }, 1.2)
    }
    const missed = root.querySelector('.call-missed-badge')
    if (missed) tl.from(missed, { opacity: 0, scale: 0.6, duration: 0.35, ease: 'back.out(2)' }, 1.9)
  }

  entranceTl = tl
  if (!props.isActive) tl.pause()
}

const playEntrance = () => {
  if (hasEntered || !import.meta.client) return
  hasEntered = true
  if (reducedMotion.value) {
    finishAll()
    return
  }
  // 等 DOM 就绪后再采集动画目标
  nextTick(buildTimeline)
}

watch(() => props.isActive, (active) => {
  if (active) {
    if (!hasEntered) playEntrance()
    else if (entranceTl && entranceTl.progress() < 1) entranceTl.play()
  } else if (entranceTl) {
    entranceTl.pause()
  }
}, { immediate: true })

onBeforeUnmount(() => {
  if (entranceTl) { entranceTl.kill(); entranceTl = null }
})
</script>

<style scoped>
/* 头像 */
.avatar-box {
  @apply w-8 h-8 rounded-lg border border-[#00000010] flex items-center justify-center flex-shrink-0;
}

/* A4 纸堆叠高度对比 */
.a4-compare {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-top: 6px;
}
.a4-col {
  width: 14px;
  display: flex;
  align-items: flex-end;
}
.a4-col-fill {
  width: 100%;
  border-radius: 2px 2px 0 0;
  /* 横纹模拟一叠 A4 纸的侧面 */
  background: repeating-linear-gradient(180deg, #ffffff 0px, #ffffff 2px, #e5e2da 2px, #e5e2da 3px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  transform-origin: bottom;
}

/* 键盘外框 */
.keyboard-outer {
  @apply mt-3 rounded-2xl p-1;
  /* Needed for ::before/::after overlays (scanlines, speaker grill, etc.) */
  position: relative;
  isolation: isolate;
  background: linear-gradient(145deg, #ffffff, #e8e8e8);
  border: 1px solid rgba(0,0,0,0.06);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}

.keyboard-inner {
  @apply rounded-xl p-3;
  background: linear-gradient(180deg, #fbfbfb, #f0f0f0);
  border: 1px solid rgba(0,0,0,0.06);
}

.keyboard-header {
  @apply relative flex items-center justify-between mb-2 px-1;
}

.keyboard-dots {
  @apply flex items-center gap-1.5;
}
.dot {
  @apply w-2 h-2 rounded-full;
}
.dot-red { background: #ff5f57; }
.dot-yellow { background: #febc2e; }
.dot-green { background: #28c840; }

.keyboard-hint {
  @apply absolute left-1/2 -translate-x-1/2 text-[9px] text-[#00000055];
}

.keyboard-stats {
  @apply text-[10px] text-[#00000066] tracking-wider;
  font-family: ui-monospace, monospace;
}

.keyboard-body {
  @apply rounded-lg p-2;
  position: relative;
  background: #f4f4f5;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.12);
}

.kb-row {
  @apply flex justify-center gap-[3px] mb-[3px];
}
.kb-row:last-child {
  @apply mb-0;
}

/* 键帽 */
.kb-key {
  --unit: 22px;
  height: 26px;
  width: var(--unit);
  position: relative;
}
@media (min-width: 640px) {
  .kb-key {
    --unit: 28px;
    height: 32px;
  }
}

/* 宽度变体 */
.kb-w-1 { width: var(--unit); }
.kb-w-1\.25 { width: calc(var(--unit) * 1.25 + 3px * 0.25); }
.kb-w-1\.5 { width: calc(var(--unit) * 1.5 + 3px * 0.5); }
.kb-w-1\.75 { width: calc(var(--unit) * 1.75 + 3px * 0.75); }
.kb-w-2 { width: calc(var(--unit) * 2 + 3px); }
.kb-w-2\.25 { width: calc(var(--unit) * 2.25 + 3px * 1.25); }
.kb-w-2\.75 { width: calc(var(--unit) * 2.75 + 3px * 1.75); }
.kb-w-6\.25 { width: calc(var(--unit) * 6.25 + 3px * 5.25); }

.kb-key::before {
  content: '';
  position: absolute;
  inset: 0;
  top: 2px;
  background: #d4d4d8;
  border-radius: 4px;
}

/* 磨损样式由键帽上的 CSS 变量驱动（--key-highlight/--key-depth/--wear-opacity/--wear-blur） */
.kb-key-top {
  position: absolute;
  inset: 0;
  bottom: 2px;
  border-radius: 4px;
  border: 1px solid var(--key-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(180deg, var(--key-bg) 0%, var(--key-bg-dark) 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, var(--key-highlight, 0.55)),
    inset 0 -1px 2px rgba(0, 0, 0, var(--key-depth, 0.12));
}

.kb-sub {
  font-size: 7px;
  line-height: 1;
  color: #666;
  margin-bottom: 1px;
  opacity: var(--wear-opacity, 1);
  filter: blur(var(--wear-blur, 0px));
}
@media (min-width: 640px) {
  .kb-sub {
    font-size: 8px;
  }
}

.kb-label {
  font-size: 10px;
  font-weight: 500;
  color: #262626;
  line-height: 1;
  text-shadow: 0 1px 0 rgba(255,255,255,0.6);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
  opacity: var(--wear-opacity, 1);
  filter: blur(var(--wear-blur, 0px));
}
@media (min-width: 640px) {
  .kb-label {
    font-size: 11px;
  }
}

.kb-label-sm {
  font-size: 7px !important;
  font-weight: 400;
}
@media (min-width: 640px) {
  .kb-label-sm {
    font-size: 8px !important;
  }
}

.kb-space-bar {
  width: 50%;
  height: 3px;
  background: rgba(0,0,0,0.12);
  border-radius: 2px;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.18);
}

/* 单键 tooltip */
.kb-tooltip {
  position: absolute;
  transform: translate(-50%, calc(-100% - 6px));
  background: rgba(20, 20, 22, 0.92);
  color: #fff;
  font-size: 10px;
  line-height: 1;
  padding: 5px 8px;
  border-radius: 6px;
  white-space: nowrap;
  pointer-events: none;
  z-index: 30;
  box-shadow: 0 4px 12px rgba(0,0,0,0.18);
}

/* Top3 磨损键徽章 */
.kb-top-badges {
  display: flex;
  justify-content: center;
  gap: 6px;
  margin-top: 8px;
}
.kb-top-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid rgba(0,0,0,0.06);
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  font-size: 10px;
}
.kb-top-rank {
  width: 13px;
  height: 13px;
  border-radius: 999px;
  background: #07C160;
  color: #fff;
  font-size: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.kb-top-name { color: #262626; font-weight: 600; }
.kb-top-hits { color: rgba(0,0,0,0.45); }

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
    /* 主裂纹 - 从右上角延伸 */
    linear-gradient(135deg,
      transparent 0%, transparent 72%,
      rgba(80,60,40,0.35) 72%, rgba(80,60,40,0.35) 73%,
      transparent 73%, transparent 100%
    ),
    /* 细小分支 */
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
    /* 主裂纹 - 对角线 */
    linear-gradient(135deg,
      transparent 0%, transparent 25%,
      rgba(70,50,30,0.4) 25%, rgba(70,50,30,0.4) 26%,
      transparent 26%, transparent 65%,
      rgba(70,50,30,0.35) 65%, rgba(70,50,30,0.35) 66%,
      transparent 66%, transparent 100%
    ),
    /* 交叉裂纹 */
    linear-gradient(45deg,
      transparent 0%, transparent 35%,
      rgba(70,50,30,0.3) 35%, rgba(70,50,30,0.3) 36%,
      transparent 36%, transparent 70%,
      rgba(70,50,30,0.25) 70%, rgba(70,50,30,0.25) 71%,
      transparent 71%, transparent 100%
    ),
    /* 横向裂纹 */
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
  /* 十字轴心居中 */
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 40%;
  height: 40%;
  /* Cherry MX 风格十字轴 */
  background:
    /* 横向 */
    linear-gradient(90deg,
      transparent 0%, transparent 30%,
      #606065 30%, #707075 35%, #606065 40%,
      #555558 45%, #555558 55%,
      #606065 60%, #707075 65%, #606065 70%,
      transparent 70%, transparent 100%
    ),
    /* 纵向 */
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

.keyboard-brand {
  @apply mt-2 text-center text-[8px] text-[#00000025] tracking-[0.15em] uppercase;
}

/* ========== 「说给你听」语音与通话 ========== */

.voice-outer {
  @apply mt-3 rounded-2xl border border-[#00000010] bg-[#F5F5F5] p-3 sm:p-4;
}

.voice-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.voice-title {
  font-size: 12px;
  font-weight: 600;
  color: rgba(0,0,0,0.7);
}
.voice-sub {
  font-size: 10px;
  color: rgba(0,0,0,0.35);
}

.voice-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  margin-top: 8px;
}
@media (min-width: 640px) {
  .voice-grid-2 {
    grid-template-columns: 1fr 1fr;
  }
}

.voice-block {
  background: #fff;
  border: 1px solid rgba(0,0,0,0.05);
  border-radius: 12px;
  padding: 10px 12px;
}

.voice-big {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.voice-big-num {
  font-size: 28px;
  line-height: 1.1;
  color: #07C160;
}
.voice-big-unit {
  font-size: 11px;
  color: rgba(0,0,0,0.45);
}
.voice-analogy {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(0,0,0,0.5);
}

/* 声波条 */
.voice-wave {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 22px;
  margin-top: 6px;
}
.voice-wave span {
  width: 3px;
  border-radius: 2px;
  background: #07C160;
  opacity: 0.75;
  height: calc(22px * var(--wave-h, 0.5));
  transform-origin: center;
  animation: voiceWave 1.1s ease-in-out infinite;
}
.wave-paused span {
  animation-play-state: paused;
}
@keyframes voiceWave {
  0%, 100% { transform: scaleY(0.45); }
  50% { transform: scaleY(1); }
}
@media (prefers-reduced-motion: reduce) {
  .voice-wave span { animation: none; }
}

.voice-meta {
  margin-top: 6px;
  font-size: 10px;
  color: rgba(0,0,0,0.45);
}

/* 年度最长语音气泡 */
.voice-longest {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(0,0,0,0.08);
}
.voice-longest-head {
  font-size: 10px;
  color: rgba(0,0,0,0.45);
  margin-bottom: 6px;
}
.voice-bubble {
  position: relative;
  height: 34px;
  min-width: 72px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  padding: 0 10px;
}
.voice-bubble-recv {
  background: #fff;
  border: 1px solid rgba(0,0,0,0.08);
}
.voice-bubble-sent {
  background: #95EC69;
  justify-content: flex-end;
}
.voice-play {
  width: 12px;
  height: 12px;
  color: #07C160;
}
.voice-play-sent {
  color: rgba(0,0,0,0.7);
  transform: scaleX(-1);
}
/* 「60''」时长角标 */
.voice-dur {
  position: absolute;
  top: -7px;
  right: -6px;
  font-size: 9px;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 999px;
  background: #fff;
  color: #07C160;
  border: 1px solid rgba(7,193,96,0.25);
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* 通话总时长翻牌数字 */
.flip-clock {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-top: 4px;
  perspective: 300px;
}
.flip-digit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 30px;
  border-radius: 5px;
  background: linear-gradient(180deg, #3a3a3c 0%, #2c2c2e 48%, #1f1f21 52%, #2c2c2e 100%);
  color: #fff;
  font-family: ui-monospace, monospace;
  font-size: 16px;
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.08);
  position: relative;
  backface-visibility: hidden;
}
.flip-digit::after {
  content: '';
  position: absolute;
  left: 2px;
  right: 2px;
  top: 50%;
  height: 1px;
  background: rgba(0,0,0,0.4);
}
.flip-sep {
  color: rgba(0,0,0,0.35);
  font-family: ui-monospace, monospace;
  font-weight: 700;
}

/* 视频/语音次数对比双条 */
.call-bars {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.call-bar-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.call-bar-name {
  width: 26px;
  flex-shrink: 0;
  font-size: 10px;
  color: rgba(0,0,0,0.5);
}
.call-bar-track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.05);
  overflow: hidden;
}
.call-bar-fill {
  height: 100%;
  border-radius: 999px;
  transform-origin: left center;
}
.call-bar-video { background: #10AEFF; }
.call-bar-voice { background: #07C160; }
.call-bar-count {
  width: 34px;
  flex-shrink: 0;
  text-align: right;
  font-size: 10px;
  color: rgba(0,0,0,0.6);
}

/* 未接通角标 */
.call-missed-badge {
  display: inline-block;
  margin-left: 4px;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 9px;
  line-height: 1;
  color: #FA5151;
  background: rgba(250,81,81,0.1);
}
</style>
