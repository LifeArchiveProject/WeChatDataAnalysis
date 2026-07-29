import { computed, reactive } from 'vue'
import { storeToRefs } from 'pinia'
import { usePrivacyStore } from '~/stores/privacy'

/**
 * 「陪你走过每个月的人」三种呈现方式共用的数据层：
 * 补齐 12 个月、按夺月数分配陪伴色、算出年度守护者与连续陪伴段，
 * 并把头像预载成 HTMLImageElement（粒子方案需要读像素，所以统一走这里）。
 */

// 暗色舞台上的陪伴色：按“陪你的月数”从多到少分配
export const COMPANION_PALETTE = [
  '#4ADE80', '#F0906A', '#7BA7F0', '#E8C25C',
  '#B48CF0', '#54C3D9', '#F07BA0', '#A8C46A'
]
export const QUIET_COLOR = '#6F7C76'

export const MONTH_EN = [
  'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
  'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'
]
export const MONTH_CN = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']

export function mod12(i) {
  return ((Math.round(i) % 12) + 12) % 12
}

export function formatInt(n) {
  return Math.round(Number(n) || 0).toLocaleString('zh-CN')
}

export function formatReply(sec) {
  const s = Number(sec) || 0
  if (s <= 0) return '—'
  if (s < 60) return `${Math.round(s)} 秒`
  if (s < 3600) return `${(s / 60).toFixed(1)} 分钟`
  return `${(s / 3600).toFixed(1)} 小时`
}

export function useMonthlyCompanions(props) {
  const privacyStore = usePrivacyStore()
  const { privacyMode } = storeToRefs(privacyStore)
  const apiBase = useApiBase()

  const monthItems = computed(() => {
    const byMonth = new Map()
    for (const x of (Array.isArray(props.months) ? props.months : [])) {
      const m = Number(x?.month)
      if (Number.isFinite(m) && m >= 1 && m <= 12) byMonth.set(m, x)
    }
    const out = []
    for (let m = 1; m <= 12; m += 1) out.push(byMonth.get(m) || { month: m, winner: null, metrics: null, raw: null })
    return out
  })

  const hasData = computed(() => monthItems.value.some((it) => it?.winner || Number(it?.raw?.totalMessages || 0) > 0))

  const colorByUser = computed(() => {
    const counts = new Map()
    for (const it of monthItems.value) {
      const u = String(it?.winner?.username || '')
      if (!u) continue
      counts.set(u, (counts.get(u) || 0) + 1)
    }
    const ordered = [...counts.entries()].sort((a, b) => (b[1] - a[1]) || String(a[0]).localeCompare(String(b[0])))
    const map = new Map()
    ordered.forEach(([u], i) => map.set(u, COMPANION_PALETTE[i % COMPANION_PALETTE.length]))
    return map
  })

  const colorOfIndex = (i) => {
    const u = String(monthItems.value[mod12(i)]?.winner?.username || '')
    return (u && colorByUser.value.get(u)) || QUIET_COLOR
  }

  // 隐私模式下一律用后端给的脱敏名，画进 canvas 的文字也就跟着脱敏了
  const nameOfIndex = (i) => {
    const w = monthItems.value[mod12(i)]?.winner
    if (!w) return ''
    return String(w.displayName || w.maskedName || '••')
  }

  const champion = computed(() => {
    const c = props.summary?.topChampion
    if (!c || !c.displayName || Number(c.monthsWon || 0) < 2) return null
    return c
  })

  const championName = computed(() => {
    const c = champion.value
    if (!c) return ''
    return String(c.displayName || c.maskedName || '••')
  })

  const championColor = computed(() => {
    const u = String(champion.value?.username || '')
    return (u && colorByUser.value.get(u)) || COMPANION_PALETTE[0]
  })

  // 守护者的主场月（羁绊最高的那一个月）——入场动画的落点
  const championHomeIndex = computed(() => {
    const u = String(champion.value?.username || '')
    let best = -1
    let bestScore = -1
    monthItems.value.forEach((it, i) => {
      if (u && String(it?.winner?.username || '') !== u) return
      const s = Number(it?.winner?.score100 || 0)
      if (s > bestScore) {
        bestScore = s
        best = i
      }
    })
    if (best >= 0) return best
    const firstFilled = monthItems.value.findIndex((it) => it?.winner)
    return firstFilled >= 0 ? firstFilled : 0
  })

  // 连续几个月是同一个人 = 一段陪伴
  const runs = computed(() => {
    const out = []
    let run = null
    monthItems.value.forEach((it, i) => {
      const u = String(it?.winner?.username || '')
      if (run && run.username === u) {
        run.end = i
        run.count += 1
        return
      }
      run = {
        start: i,
        end: i,
        count: 1,
        username: u,
        displayName: nameOfIndex(i),
        color: u ? (colorByUser.value.get(u) || COMPANION_PALETTE[0]) : QUIET_COLOR
      }
      out.push(run)
    })
    return out
  })

  const quoteOfIndex = (i) => {
    const item = monthItems.value[mod12(i)]
    if (!item?.winner) return '大家都在忙自己的事，微信安静得能听见回声'
    const m = item.metrics || {}
    const entries = [
      ['interaction', Number(m.interactionScore || 0)],
      ['speed', Number(m.speedScore || 0)],
      ['continuity', Number(m.continuityScore || 0)],
      ['coverage', Number(m.coverageScore || 0)]
    ].sort((a, b) => b[1] - a[1])
    const top = entries[0][0]
    if (top === 'speed') return '消息一来一回，谁都没让谁久等'
    if (top === 'continuity') return '几乎每天都能聊上几句'
    if (top === 'coverage') return '从清晨到深夜，都有 TA 的消息'
    return '你来我往，话题就没断过'
  }

  const statsOfIndex = (i) => {
    const raw = monthItems.value[mod12(i)]?.raw || {}
    return [
      [formatInt(raw.totalMessages), '条消息'],
      [formatInt(raw.interaction), '次一来一回'],
      [formatInt(raw.activeDays), '天有 TA 在'],
      [formatReply(raw.avgReplySecondsCapped), '平均回你']
    ]
  }

  // ---------- 头像 ----------
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

  const avatars = reactive({})   // index -> HTMLImageElement | null

  const preloadAvatars = () => {
    const jobs = monthItems.value.map((it, i) => {
      const url = it?.winner ? resolveMediaUrl(it.winner.avatarUrl) : ''
      if (!url) {
        avatars[i] = null
        return Promise.resolve()
      }
      return new Promise((resolve) => {
        const img = new Image()
        img.crossOrigin = 'anonymous'
        img.onload = () => { avatars[i] = img; resolve() }
        img.onerror = () => { avatars[i] = null; resolve() }
        img.src = url
      })
    })
    return Promise.all(jobs)
  }

  return {
    privacyMode,
    monthItems,
    hasData,
    colorOfIndex,
    nameOfIndex,
    champion,
    championName,
    championColor,
    championHomeIndex,
    runs,
    quoteOfIndex,
    statsOfIndex,
    avatars,
    preloadAvatars
  }
}
