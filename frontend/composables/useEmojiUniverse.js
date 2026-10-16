import { computed } from 'vue'
import { useApiBase } from '~/composables/useApiBase'

/**
 * 「你的表情包里藏了多少心情？」三种呈现方式（全息闪卡 / 街机斗图厅 / 扭蛋机）共用的数据层。
 *
 * 后端 card_04_emoji_universe 给出的字段散在好几个数组里（topStickers / newStickerSamples /
 * revivedStickerSamples / topWechatEmojis / topUnicodeEmojis），三个舞台都要「一张表情 = 一个可交互实体」，
 * 所以在这里统一成一份带稀有度、来源标记、图片地址的表情池。
 */

const WEEKDAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function formatInt(n) {
  return Math.round(Number(n) || 0).toLocaleString('zh-CN')
}

export function padNo(n, width = 2) {
  return String(Math.max(0, Math.round(Number(n) || 0))).padStart(width, '0')
}

// 稀有度按「牌组内名次」定，不按绝对比例。
// 用比例分档的话，高频表情往往全挤在同一档里（实测前几张都是 4.5%~10%，一水儿 SSR），
// 一副七张的牌就完全分不出层次了。真实卡包也是一包一张 C 位，按位次给才有开包的期待感。
export const RARITY_TIERS = [
  { code: 'UR', label: 'UR', name: '究极稀有', color: '#FFCE4A', glow: 'rgba(255,206,74,0.55)' },
  { code: 'SSR', label: 'SSR', name: '闪耀稀有', color: '#C08BFF', glow: 'rgba(192,139,255,0.5)' },
  { code: 'SR', label: 'SR', name: '超级稀有', color: '#6FB6FF', glow: 'rgba(111,182,255,0.45)' },
  { code: 'R', label: 'R', name: '稀有', color: '#4ADE80', glow: 'rgba(74,222,128,0.42)' }
]

const [UR, SSR, SR, R] = RARITY_TIERS

export function rarityForRank(rank) {
  const n = Math.max(1, Math.round(Number(rank) || 1))
  if (n === 1) return UR
  if (n === 2) return SSR
  if (n <= 4) return SR
  return R
}

export function useEmojiUniverse(props) {
  const apiBase = useApiBase()

  const resolveMediaUrl = (value, opts = { backend: false }) => {
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
    if (opts.backend) {
      const origin = apiBase.endsWith('/api') ? apiBase.slice(0, -4) : apiBase
      return `${origin}${raw.startsWith('/') ? '' : '/'}${raw}`
    }
    return raw.startsWith('/') ? raw : `/${raw}`
  }

  const resolveEmojiAsset = (value) => {
    const raw = String(value || '').trim()
    if (!raw) return ''
    if (/^https?:\/\//i.test(raw)) return raw
    if (raw.startsWith('/')) return raw
    return `/wxemoji/${raw}`
  }

  const resolveStickerUrl = (st) => {
    const remote = resolveMediaUrl(st?.emojiUrl, { backend: true })
    if (remote) return remote
    return resolveEmojiAsset(st?.emojiAssetPath)
  }

  const data = computed(() => props.card?.data || {})

  const year = computed(() => Number(data.value?.year) || 0)
  const sentStickerCount = computed(() => Math.max(0, Number(data.value?.sentStickerCount || 0)))
  const stickerActiveDays = computed(() => Math.max(0, Number(data.value?.stickerActiveDays || 0)))
  const stickerPerActiveDay = computed(() => {
    const v = Number(data.value?.stickerPerActiveDay || 0)
    return Number.isFinite(v) ? v : 0
  })
  const stickerSharePct = computed(() => {
    const v = Number(data.value?.stickerShareOfSentMessages || 0)
    return Math.max(0, Math.min(100, Math.round(v * 100)))
  })

  const uniqueTypeCount = computed(() => Math.max(0, Number(data.value?.uniqueStickerTypeCount || 0)))
  const newCount = computed(() => Math.max(0, Number(data.value?.newStickerCountThisYear || 0)))
  const revivedCount = computed(() => Math.max(0, Number(data.value?.revivedStickerCount || 0)))
  const revivedMinGapDays = computed(() => Math.max(0, Number(data.value?.revivedMinGapDays || 60)))
  const revivedMaxGapDays = computed(() => Math.max(0, Number(data.value?.revivedMaxGapDays || 0)))

  const sharePct = (explicit, part) => {
    const v = Number(explicit)
    if (Number.isFinite(v) && v >= 0) return Math.max(0, Math.min(100, Math.round(v * 100)))
    const total = uniqueTypeCount.value
    if (total <= 0) return 0
    return Math.max(0, Math.min(100, Math.round((Number(part || 0) / total) * 100)))
  }
  const newSharePct = computed(() => sharePct(data.value?.newStickerShare, newCount.value))
  const revivedSharePct = computed(() => sharePct(data.value?.revivedStickerShare, revivedCount.value))

  const peakHour = computed(() => {
    const h = data.value?.peakHour
    return Number.isFinite(Number(h)) ? Number(h) : null
  })
  const peakWeekday = computed(() => {
    const w = Number(data.value?.peakWeekday)
    return Number.isFinite(w) ? w : null
  })
  const peakWeekdayName = computed(() => {
    const s = String(data.value?.peakWeekdayName || '').trim()
    if (s) return s
    return peakWeekday.value !== null ? (WEEKDAY_CN[peakWeekday.value] || '') : ''
  })

  const hourCounts = computed(() => {
    const raw = Array.isArray(data.value?.stickerHourCounts) ? data.value.stickerHourCounts : []
    return Array.from({ length: 24 }, (_, i) => Math.max(0, Number(raw[i] || 0)))
  })
  const hourMax = computed(() => Math.max(1, ...hourCounts.value))

  const weekdayCounts = computed(() => {
    const raw = Array.isArray(data.value?.stickerWeekdayCounts) ? data.value.stickerWeekdayCounts : []
    return Array.from({ length: 7 }, (_, i) => Math.max(0, Number(raw[i] || 0)))
  })

  const persona = computed(() => {
    const p = data.value?.persona || {}
    return {
      code: String(p.code || ''),
      label: String(p.label || '').trim(),
      reason: String(p.reason || '').trim()
    }
  })

  const battlePartner = computed(() => {
    const b = data.value?.topBattlePartner || {}
    const name = String(b.displayName || b.maskedName || b.username || '').trim()
    const count = Math.max(0, Number(b.stickerCount || 0))
    if (!name || count <= 0) return null
    return { name, count, avatar: resolveMediaUrl(b.avatarUrl, { backend: true }) }
  })

  // ---------- 表情池 ----------
  // topStickers 是主池；newStickerSamples / revivedStickerSamples 补上「今年新解锁」「沉睡后回温」标记，
  // 它们和 topStickers 可能重合（同一张图），所以按 md5 合并而不是拼接。
  const rawList = (key) => (Array.isArray(data.value?.[key]) ? data.value[key] : [])

  const stickerPool = computed(() => {
    const byId = new Map()
    const order = []

    const ingest = (rows, flag) => {
      for (let i = 0; i < rows.length; i += 1) {
        const st = rows[i] || {}
        const src = resolveStickerUrl(st)
        if (!src) continue
        const id = String(st.md5 || st.emojiAssetPath || st.emojiUrl || `${flag}-${i}`).trim()
        if (!id) continue
        const prev = byId.get(id)
        if (prev) {
          if (flag) prev[flag] = true
          if (flag === 'revived') prev.gapDays = Math.max(prev.gapDays, Math.max(0, Number(st.gapDays || 0)))
          prev.count = Math.max(prev.count, Math.max(0, Number(st.count || 0)))
          continue
        }
        const item = {
          id,
          src,
          count: Math.max(0, Number(st.count || 0)),
          ratio: Math.max(0, Number(st.ratio || 0)),
          label: String(st.emojiLabel || '').trim(),
          ownerName: String(st.sampleDisplayName || st.sampleUsername || '').trim(),
          ownerAvatar: resolveMediaUrl(st.sampleAvatarUrl, { backend: true }),
          isNew: flag === 'new',
          revived: flag === 'revived',
          gapDays: flag === 'revived' ? Math.max(0, Number(st.gapDays || 0)) : 0
        }
        byId.set(id, item)
        order.push(id)
      }
    }

    ingest(rawList('topStickers'), '')
    ingest(rawList('newStickerSamples'), 'new')
    ingest(rawList('revivedStickerSamples'), 'revived')

    const total = sentStickerCount.value
    return order
      .map((id) => byId.get(id))
      .filter(Boolean)
      .map((item) => ({
        ...item,
        ratio: item.ratio > 0 ? item.ratio : (total > 0 ? item.count / total : 0)
      }))
      // 先按次数排定名次，再由名次决定稀有度
      .sort((a, b) => b.count - a.count)
      .map((item, idx) => ({ ...item, rank: idx + 1, rarity: rarityForRank(idx + 1) }))
  })

  const heroSticker = computed(() => stickerPool.value[0] || null)

  // 全年表情缩略图池：给「从所有表情里筛出年度卡」那段动画用。
  // 后端只给 md5/图片地址/次数，不含联系人，所以可以放心取到近百张。
  const poolThumbs = computed(() => {
    const seen = new Set()
    const out = []
    const ingest = (rows) => {
      for (const st of rows) {
        const src = resolveStickerUrl(st)
        if (!src || seen.has(src)) continue
        seen.add(src)
        out.push({ id: String(st?.md5 || src), src, count: Math.max(0, Number(st?.count || 0)) })
      }
    }
    ingest(rawList('stickerPoolSamples'))
    ingest(rawList('topStickers'))
    ingest(rawList('newStickerSamples'))
    ingest(rawList('revivedStickerSamples'))
    return out
  })

  const wechatEmojis = computed(() => {
    const rows = rawList('topWechatEmojis').length > 0 ? rawList('topWechatEmojis') : rawList('topTextEmojis')
    return rows
      .map((x, idx) => ({
        id: `wx-${String(x?.id ?? x?.key ?? idx)}`,
        label: String(x?.key || '').trim() || '微信表情',
        count: Math.max(0, Number(x?.count || 0)),
        src: resolveEmojiAsset(x?.assetPath)
      }))
      .filter((x) => x.count > 0)
  })

  const unicodeEmojis = computed(() =>
    rawList('topUnicodeEmojis')
      .map((x, idx) => ({
        id: `uni-${String(x?.emoji || idx)}`,
        label: String(x?.emoji || '').trim(),
        count: Math.max(0, Number(x?.count || 0))
      }))
      .filter((x) => x.count > 0 && x.label)
  )

  const hasData = computed(
    () => stickerPool.value.length > 0 || wechatEmojis.value.length > 0 || unicodeEmojis.value.length > 0
  )

  return {
    resolveMediaUrl,
    resolveEmojiAsset,
    year,
    sentStickerCount,
    stickerActiveDays,
    stickerPerActiveDay,
    stickerSharePct,
    uniqueTypeCount,
    newCount,
    newSharePct,
    revivedCount,
    revivedSharePct,
    revivedMinGapDays,
    revivedMaxGapDays,
    peakHour,
    peakWeekday,
    peakWeekdayName,
    poolThumbs,
    hourCounts,
    hourMax,
    weekdayCounts,
    persona,
    battlePartner,
    stickerPool,
    heroSticker,
    wechatEmojis,
    unicodeEmojis,
    hasData
  }
}
