<template>
  <div ref="cardRoot" class="h-full w-full">
    <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
      <template #narrative>
        <div class="mt-1 wrapped-body text-sm sm:text-base text-[#6F6F6F] leading-relaxed">
          <p class="whitespace-normal">
            <template v-for="(seg, idx) in narrativeSegments" :key="`n-${idx}`">
              <img
                v-if="seg.type === 'emoji'"
                :src="seg.src"
                class="inline-block align-[-0.18em] rounded-[3px] wx-inline-emoji"
                :style="{ width: `${seg.sizeEm}em`, height: `${seg.sizeEm}em` }"
                :alt="seg.alt || 'emoji'"
              />
              <img
                v-else-if="seg.type === 'sticker'"
                :src="seg.src"
                class="inline-block align-[-0.16em] rounded-[4px] wx-inline-emoji"
                :style="{ width: `${seg.sizeEm}em`, height: `${seg.sizeEm}em` }"
                :alt="seg.alt || 'sticker'"
              />
              <span
                v-else-if="seg.type === 'num'"
                class="wrapped-number text-[#07C160] font-semibold"
              >
                {{ seg.content }}
              </span>
              <span v-else>{{ seg.content }}</span>
            </template>
          </p>
        </div>
      </template>

      <div class="w-full -mt-1 sm:-mt-2">
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-2">
          <div class="lg:col-span-7 space-y-2 sm:space-y-2.5">
            <div class="rounded-2xl border border-[#EDEDED] bg-white/65 p-2.5 sm:p-3">
              <div class="wrapped-label text-xs text-[#00000066]">高频表情卡堆（Vue Bits）</div>
              <div v-if="stackCardsData.length > 0" class="mt-2">
                <div class="relative h-[9.4rem] sm:h-[9.8rem] rounded-xl overflow-visible">
                  <div class="absolute inset-0 flex items-center justify-center">
                    <Stack
                      :randomRotation="true"
                      :sensitivity="180"
                      :sendToBackOnClick="false"
                      :cardDimensions="stackCardDimensions"
                      :cardsData="stackCardsData"
                    />
                  </div>
                </div>

                <div class="mt-2 flex flex-col items-center justify-center text-center">
                  <div class="wrapped-number text-base text-[#07C160] font-semibold leading-tight">
                    {{ formatInt(Number(stackTopCount || 0)) }} 次
                  </div>

                  <div
                    class="mt-0.5 inline-flex items-center gap-1.5 rounded-md bg-[#00000008] px-1.5 py-1 max-w-full"
                    :title="heroStickerOwnerName ? `常发送给 ${heroStickerOwnerName}` : '常发送给：未知'"
                  >
                    <span class="w-4 h-4 rounded-md overflow-hidden bg-[#0000000d] flex items-center justify-center flex-shrink-0 wrapped-privacy-avatar">
                      <img
                        v-if="heroStickerOwnerAvatarUrl && avatarOk.topStickerOwner"
                        :src="heroStickerOwnerAvatarUrl"
                        class="w-full h-full object-cover"
                        alt="avatar"
                        @error="avatarOk.topStickerOwner = false"
                      />
                      <span v-else class="wrapped-number text-[10px] text-[#00000066]">
                        {{ avatarFallback(heroStickerOwnerName) }}
                      </span>
                    </span>
                    <span class="wrapped-body text-[11px] text-[#00000080] truncate">
                      常发送给 <span class="text-[#07C160] font-semibold wrapped-privacy-name">{{ heroStickerOwnerName || '未知' }}</span>
                    </span>
                  </div>

                  <div class="mt-1 wrapped-label text-[10px] text-[#00000055]">拖动表情卡片翻一翻</div>
                </div>
              </div>
              <div v-else class="mt-2 wrapped-body text-xs text-[#00000055]">
                暂无可展示的高频表情图片。
              </div>
            </div>

            <div class="rounded-2xl border border-[#EDEDED] bg-white/65 p-2.5 sm:p-3">
              <div class="flex items-center justify-between gap-3">
                <div class="wrapped-label text-xs text-[#00000066]">Emoji Top（小黄脸 + Unicode）</div>
                <div class="flex items-center gap-2 flex-shrink-0">
                  <span class="wrapped-label text-[10px] px-2 py-0.5 rounded-md border bg-[#07C160]/10 text-[#07C160] border-[#07C160]/25">
                    小黄脸
                  </span>
                  <span class="wrapped-label text-[10px] px-2 py-0.5 rounded-md border bg-[#0EA5E9]/10 text-[#0EA5E9] border-[#0EA5E9]/25">
                    Unicode
                  </span>
                </div>
              </div>

              <div v-if="emojiBubbleRows.length > 0" class="mt-2">
                <div class="grid grid-cols-4 sm:grid-cols-8 gap-2 sm:gap-2.5 place-items-end">
                  <div
                    v-for="row in emojiBubbleRows"
                    :key="row.id"
                    class="min-w-0 flex flex-col items-center gap-1"
                    :title="`${row.label} · ${formatInt(row.count)}次`"
                  >
                    <div
                      class="flex items-center justify-center rounded-full shadow-sm"
                      :class="row.kind === 'wechat' ? 'bg-[#07C160]/14' : 'bg-[#0EA5E9]/12'"
                      :style="{ width: `${row.size}px`, height: `${row.size}px` }"
                    >
                      <img
                        v-if="row.kind === 'wechat' && row.assetPath && emojiAssetOk[row.key] !== false"
                        :src="resolveEmojiAsset(row.assetPath)"
                        class="w-3/4 h-3/4 object-contain"
                        alt="emoji"
                        @error="emojiAssetOk[row.key] = false"
                      />
                      <span v-else class="text-xl leading-none">
                        {{ row.kind === 'unicode' ? row.label : '🙂' }}
                      </span>
                    </div>
                    <div
                      class="wrapped-number text-[10px] font-semibold leading-none"
                      :class="row.kind === 'wechat' ? 'text-[#07C160]' : 'text-[#0EA5E9]'"
                    >
                      {{ formatInt(row.count) }}
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="mt-2 wrapped-body text-xs text-[#00000066]">
                今年没有统计到可识别的 Emoji（小黄脸/Unicode）。
              </div>
            </div>
          </div>

          <div class="lg:col-span-5 h-full min-h-[20rem] sm:min-h-[21.5rem] rounded-2xl border border-[#EDEDED] bg-white/65 p-2.5 sm:p-3 relative overflow-hidden">
            <div class="relative z-[1] h-full flex flex-col">
              <div class="wrapped-label text-xs text-[#00000066]">斗图热力时段</div>
              <div class="mt-1 wrapped-body text-sm text-[#000000e6]">
                <template v-if="peakHour !== null && peakWeekdayName">
                  高峰在
                  <span class="wrapped-number text-[#07C160] font-semibold">{{ peakWeekdayName }} {{ peakHour }}:00</span>
                </template>
                <template v-else>
                  今年没有明显的斗图高峰时段
                </template>
              </div>

              <div class="mt-2.5 h-16 sm:h-20 flex items-end gap-[2px]">
                <div
                  v-for="item in hourBars"
                  :key="`hour-${item.hour}`"
                  class="flex-1 min-w-0 rounded-sm bg-[#07C160]/20"
                  :style="{ height: `${item.heightPct}%` }"
                  :title="`${item.hour}:00 · ${formatInt(item.count)}次`"
                />
              </div>
              <div class="mt-1.5 flex items-center justify-between wrapped-label text-[10px] text-[#00000055]">
                <span>00</span>
                <span>06</span>
                <span>12</span>
                <span>18</span>
                <span>23</span>
              </div>

              <div class="mt-3 rounded-xl border border-[#EDEDED] bg-white/60 p-2.5 flex-1 flex flex-col">
                <div class="wrapped-label text-[11px] text-[#00000066]">表情新鲜度</div>
                <div class="mt-2 grid grid-cols-1 gap-2.5">
                  <div class="rounded-lg bg-[#07C160]/10 px-3 py-2.5 flex items-center justify-between gap-3">
                    <div class="min-w-0">
                      <div class="wrapped-label text-[11px] text-[#00000066]">年度新解锁</div>
                      <div class="mt-1.5 wrapped-number text-lg text-[#07C160] font-semibold leading-tight">
                        {{ formatInt(newStickerCountThisYear) }}
                      </div>
                      <div class="wrapped-label text-[11px] text-[#00000055]">
                        占类型 {{ newStickerSharePct }}%
                      </div>
                    </div>
                    <div v-if="newStickerDecorDisplayItems.length > 0" class="grid grid-cols-3 gap-2 flex-shrink-0">
                      <div
                        v-for="item in newStickerDecorDisplayItems"
                        :key="`new-chip-${item.id}`"
                        class="w-11 h-11 sm:w-12 sm:h-12 rounded-[10px] overflow-hidden ring-1 ring-[#00000014] bg-white/60"
                      >
                        <img
                          v-if="item.src && stickerDecorOk[item.id] !== false"
                          :src="item.src"
                          class="w-full h-full object-cover"
                          alt=""
                          @error="stickerDecorOk[item.id] = false"
                        />
                      </div>
                    </div>
                  </div>

                  <div class="rounded-lg bg-[#0EA5E9]/10 px-3 py-2.5 flex items-center justify-between gap-3">
                    <div class="min-w-0">
                      <div class="wrapped-label text-[11px] text-[#00000066]">回温表情</div>
                      <div class="mt-1.5 wrapped-number text-lg text-[#0EA5E9] font-semibold leading-tight">
                        {{ formatInt(revivedStickerCount) }}
                      </div>
                      <div class="wrapped-label text-[11px] text-[#00000055] leading-tight">
                        间隔≥{{ formatInt(revivedMinGapDays) }}天，最长 {{ formatInt(revivedMaxGapDays) }} 天
                      </div>
                    </div>
                    <div v-if="revivedStickerDecorDisplayItems.length > 0" class="grid grid-cols-3 gap-2 flex-shrink-0">
                      <div
                        v-for="item in revivedStickerDecorDisplayItems"
                        :key="`rev-chip-${item.id}`"
                        class="w-11 h-11 sm:w-12 sm:h-12 rounded-[10px] overflow-hidden ring-1 ring-[#00000014] bg-white/60"
                      >
                        <img
                          v-if="item.src && stickerDecorOk[item.id] !== false"
                          :src="item.src"
                          class="w-full h-full object-cover"
                          alt=""
                          @error="stickerDecorOk[item.id] = false"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div class="mt-2 wrapped-body text-[11px] text-[#00000066]">
                  今年共用过 <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(uniqueStickerTypeCount) }}</span> 种表情，
                  回温占比 <span class="wrapped-number text-[#0EA5E9] font-semibold">{{ revivedStickerSharePct }}</span>%。
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </WrappedCardShell>

    <Teleport to="body">
      <div v-if="cursorFxEnabled && isCardVisible && cursorTrails.length > 0" class="emoji-cursor-layer" aria-hidden="true">
        <img
          v-for="item in cursorTrails"
          :key="item.id"
          class="emoji-cursor-item"
          :style="{
            left: `${item.x}px`,
            top: `${item.y}px`,
            width: `${item.size}px`,
            height: `${item.size}px`,
            '--drift-x': `${item.driftX}px`,
            '--drift-y': `${item.driftY}px`
          }"
          :src="item.src"
          alt=""
          draggable="false"
        />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Stack from '~/components/wrapped/shared/VueBitsStack.vue'
import WechatEmojiTable, { parseTextWithEmoji } from '~/utils/wechat-emojis'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

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
  if (raw.startsWith('/wxemoji/')) return raw
  if (raw.startsWith('/')) return raw
  return `/wxemoji/${raw}`
}

const resolveStickerUrl = (st) => {
  const remote = resolveMediaUrl(st?.emojiUrl, { backend: true })
  if (remote) return remote
  const asset = resolveEmojiAsset(st?.emojiAssetPath)
  return asset || ''
}

const splitTextByNumbers = (text) => {
  const raw = String(text || '')
  if (!raw) return []
  const parts = raw.split(/(\d[\d,.]*)/g)
  const out = []
  for (const p of parts) {
    if (!p) continue
    if (/^\d[\d,.]*$/.test(p)) out.push({ type: 'num', content: p })
    else out.push({ type: 'text', content: p })
  }
  return out
}

const appendParsedText = (segments, text) => {
  const parsed = parseTextWithEmoji(String(text || ''))
  for (const seg of parsed) {
    if (seg?.type === 'emoji' && seg.emojiSrc) {
      segments.push({
        type: 'emoji',
        src: resolveEmojiAsset(seg.emojiSrc),
        alt: seg.content || 'emoji',
        sizeEm: 1.12
      })
      continue
    }
    const inner = splitTextByNumbers(seg?.content || '')
    for (const x of inner) segments.push(x)
  }
}

const sentStickerCount = computed(() => Number(props.card?.data?.sentStickerCount || 0))
const stickerActiveDays = computed(() => Number(props.card?.data?.stickerActiveDays || 0))
const peakHour = computed(() => {
  const h = props.card?.data?.peakHour
  return Number.isFinite(Number(h)) ? Number(h) : null
})
const peakWeekdayName = computed(() => String(props.card?.data?.peakWeekdayName || '').trim())

const stickerPerActiveDayText = computed(() => {
  const v = Number(props.card?.data?.stickerPerActiveDay || 0)
  return Number.isFinite(v) ? v.toFixed(1) : '0.0'
})
const uniqueStickerTypeCount = computed(() => Number(props.card?.data?.uniqueStickerTypeCount || 0))
const newStickerCountThisYear = computed(() => Number(props.card?.data?.newStickerCountThisYear || 0))
const revivedStickerCount = computed(() => Number(props.card?.data?.revivedStickerCount || 0))
const revivedMinGapDays = computed(() => Number(props.card?.data?.revivedMinGapDays || 60))
const revivedMaxGapDays = computed(() => Number(props.card?.data?.revivedMaxGapDays || 0))
const newStickerSharePct = computed(() => {
  const v = Number(props.card?.data?.newStickerShare)
  if (Number.isFinite(v) && v >= 0) return Math.max(0, Math.min(100, Math.round(v * 100)))
  const total = Math.max(0, Number(uniqueStickerTypeCount.value || 0))
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((Number(newStickerCountThisYear.value || 0) / total) * 100)))
})
const revivedStickerSharePct = computed(() => {
  const v = Number(props.card?.data?.revivedStickerShare)
  if (Number.isFinite(v) && v >= 0) return Math.max(0, Math.min(100, Math.round(v * 100)))
  const total = Math.max(0, Number(uniqueStickerTypeCount.value || 0))
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((Number(revivedStickerCount.value || 0) / total) * 100)))
})
const newStickerSamples = computed(() => {
  const arr = props.card?.data?.newStickerSamples
  return Array.isArray(arr) ? arr : []
})
const revivedStickerSamples = computed(() => {
  const arr = props.card?.data?.revivedStickerSamples
  return Array.isArray(arr) ? arr : []
})

const buildDecorStickerItems = (rows, prefix) => {
  const out = []
  const seen = new Set()
  for (let idx = 0; idx < rows.length; idx += 1) {
    const st = rows[idx] || {}
    const rawId = String(st?.md5 || st?.emojiAssetPath || st?.emojiUrl || `${prefix}-${idx}`).trim()
    if (!rawId || seen.has(rawId)) continue
    seen.add(rawId)
    out.push({
      id: `${prefix}-${rawId}`,
      src: resolveStickerUrl(st),
      count: Math.max(0, Number(st?.count || 0)),
      gapDays: Math.max(0, Number(st?.gapDays || 0))
    })
    if (out.length >= 4) break
  }
  return out
}

const topStickers = computed(() => {
  const arr = props.card?.data?.topStickers
  return Array.isArray(arr) ? arr : []
})

const newStickerDecorItems = computed(() => buildDecorStickerItems(newStickerSamples.value, 'new'))
const revivedStickerDecorItems = computed(() => buildDecorStickerItems(revivedStickerSamples.value, 'revived'))
const topStickerDecorItems = computed(() => buildDecorStickerItems(topStickers.value, 'top'))
const toRenderableDecor = (items) => items.filter((x) => String(x?.src || '').trim())
const decorFallbackPool = computed(() => {
  const out = []
  const seen = new Set()
  for (const item of [
    ...toRenderableDecor(newStickerDecorItems.value),
    ...toRenderableDecor(revivedStickerDecorItems.value),
    ...toRenderableDecor(topStickerDecorItems.value)
  ]) {
    const key = String(item?.src || '').trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(item)
    if (out.length >= 6) break
  }
  return out
})
const newStickerDecorDisplayItems = computed(() => {
  const own = toRenderableDecor(newStickerDecorItems.value).slice(0, 3)
  if (own.length > 0) return own
  return decorFallbackPool.value.slice(0, 3)
})
const revivedStickerDecorDisplayItems = computed(() => {
  const own = toRenderableDecor(revivedStickerDecorItems.value).slice(0, 3)
  if (own.length > 0) return own
  const fallback = decorFallbackPool.value.slice(3, 6)
  return fallback.length > 0 ? fallback : decorFallbackPool.value.slice(0, 3)
})

const heroSticker = computed(() => {
  const arr = topStickers.value
  return Array.isArray(arr) && arr.length > 0 ? arr[0] : null
})

const heroStickerUrl = computed(() => resolveStickerUrl(heroSticker.value))
const heroStickerOwnerName = computed(() => String(heroSticker.value?.sampleDisplayName || heroSticker.value?.sampleUsername || '').trim())
const heroStickerOwnerAvatarUrl = computed(() => resolveMediaUrl(heroSticker.value?.sampleAvatarUrl, { backend: true }))

const stackCardDimensions = { width: 140, height: 140 }

const stackCardsData = computed(() => {
  const seen = new Set()
  const out = []
  for (const st of topStickers.value) {
    const key = String(st?.md5 || st?.emojiAssetPath || st?.emojiUrl || '').trim()
    if (!key || seen.has(key)) continue
    const src = resolveStickerUrl(st)
    if (!src) continue
    seen.add(key)
    out.push({ id: key, img: src })
    if (out.length >= 4) break
  }
  if (out.length > 0) return out
  return allWechatEmojiAssets.value.slice(0, 4).map((img, idx) => ({ id: `wx-${idx}`, img }))
})

const stackTopCount = computed(() => Number(heroSticker.value?.count || 0))

const hourBars = computed(() => {
  const raw = Array.isArray(props.card?.data?.stickerHourCounts) ? props.card.data.stickerHourCounts : []
  const counts = Array.from({ length: 24 }, (_, i) => Math.max(0, Number(raw[i] || 0)))
  const maxV = Math.max(1, ...counts)
  return counts.map((count, hour) => ({
    hour,
    count,
    heightPct: Math.max(8, Math.round((count / maxV) * 100))
  }))
})

const topTextEmojis = computed(() => {
  const arr = props.card?.data?.topTextEmojis
  return Array.isArray(arr) ? arr : []
})
const topWechatEmojis = computed(() => {
  const arr = props.card?.data?.topWechatEmojis
  return Array.isArray(arr) ? arr : []
})
const topUnicodeEmojis = computed(() => {
  const arr = props.card?.data?.topUnicodeEmojis
  return Array.isArray(arr) ? arr : []
})

const smallWechatEmojiChips = computed(() => {
  if (topWechatEmojis.value.length > 0) {
    return topWechatEmojis.value.map((x) => ({
      key: String(x?.key || ''),
      count: Number(x?.count || 0),
      assetPath: String(x?.assetPath || '')
    }))
  }
  return topTextEmojis.value.map((x) => ({
    key: String(x?.key || ''),
    count: Number(x?.count || 0),
    assetPath: String(x?.assetPath || '')
  }))
})

const emojiAssetOk = reactive({})
watch(
  smallWechatEmojiChips,
  (arr) => {
    for (const k of Object.keys(emojiAssetOk)) delete emojiAssetOk[k]
    if (!Array.isArray(arr)) return
    for (const em of arr) {
      const key = String(em?.key || '').trim()
      if (key) emojiAssetOk[key] = true
    }
  },
  { immediate: true }
)

const emojiChartRows = computed(() => {
  const wechat = smallWechatEmojiChips.value
    .slice(0, 4)
    .map((x, idx) => ({
      id: `w-${String(x?.key || idx)}`,
      kind: 'wechat',
      key: String(x?.key || idx),
      label: String(x?.key || '').trim() || '微信表情',
      count: Math.max(0, Number(x?.count || 0)),
      assetPath: String(x?.assetPath || '').trim()
    }))

  const unicode = topUnicodeEmojis.value
    .slice(0, 4)
    .map((x, idx) => ({
      id: `u-${String(x?.emoji || idx)}`,
      kind: 'unicode',
      key: String(x?.emoji || idx),
      label: String(x?.emoji || '').trim() || '😀',
      count: Math.max(0, Number(x?.count || 0)),
      assetPath: ''
    }))

  const rows = [...wechat, ...unicode].filter((x) => x.count > 0 && x.label)
  const maxV = Math.max(1, ...rows.map((x) => x.count))
  return rows
    .sort((a, b) => b.count - a.count)
    .map((x) => ({
      ...x,
      pct: Math.max(8, Math.round((x.count / maxV) * 100))
    }))
})

const emojiBubbleRows = computed(() => {
  const rows = emojiChartRows.value
  if (!rows.length) return []
  const maxV = Math.max(1, ...rows.map((x) => x.count))
  return rows.map((x) => {
    const ratio = Math.max(0, Math.min(1, x.count / maxV))
    const size = Math.round(32 + Math.sqrt(ratio) * 36)
    return { ...x, size: Math.max(28, Math.min(72, size)) }
  })
})

const stickerDecorOk = reactive({})
watch(
  () => [...newStickerDecorItems.value, ...revivedStickerDecorItems.value],
  (arr) => {
    for (const k of Object.keys(stickerDecorOk)) delete stickerDecorOk[k]
    if (!Array.isArray(arr)) return
    for (const x of arr) {
      const key = String(x?.id || '').trim()
      if (key) stickerDecorOk[key] = true
    }
  },
  { immediate: true }
)

const avatarOk = reactive({ topStickerOwner: true })
watch(heroStickerOwnerAvatarUrl, () => { avatarOk.topStickerOwner = true })

const avatarFallback = (name) => {
  const s = String(name || '').trim()
  return s ? s[0] : '?'
}

const narrativeSegments = computed(() => {
  const out = []

  if (sentStickerCount.value > 0) {
    appendParsedText(
      out,
      `这一年，你用 ${formatInt(sentStickerCount.value)} 张表情包把聊天变得更有温度；在 ${formatInt(
        stickerActiveDays.value
      )} 个活跃日里，日均 ${stickerPerActiveDayText.value} 张。`
    )
  } else {
    appendParsedText(out, '这一年你几乎没发过表情包。')
  }

  if (peakHour.value !== null && peakWeekdayName.value) {
    appendParsedText(out, `你最活跃的时刻是 ${peakWeekdayName.value} ${peakHour.value}:00。`)
  }

  let hasTail = false
  if (heroSticker.value) {
    appendParsedText(out, '年度 C 位表情是 ')
    if (heroStickerUrl.value) {
      out.push({ type: 'sticker', src: heroStickerUrl.value, alt: '年度 C 位表情', sizeEm: 1.22 })
    } else {
      appendParsedText(out, '（图片缺失）')
    }
    appendParsedText(out, `（${formatInt(Number(heroSticker.value?.count || 0))} 次）`)
    hasTail = true
  }

  const topWechat = topWechatEmojis.value[0]
  const topText = topTextEmojis.value[0]
  if (topWechat) {
    appendParsedText(out, `${hasTail ? '，' : ''}你最常用的小黄脸是 `)
    if (topWechat.assetPath) {
      out.push({
        type: 'emoji',
        src: resolveEmojiAsset(topWechat.assetPath),
        alt: topWechat.key || 'emoji',
        sizeEm: 1.16
      })
    } else {
      appendParsedText(out, topWechat.key || '')
    }
    appendParsedText(out, `（${formatInt(Number(topWechat.count || 0))} 次）`)
    hasTail = true
  } else if (topText) {
    appendParsedText(out, `${hasTail ? '，' : ''}在文字聊天里，你最常打的小黄脸是 `)
    if (topText.assetPath) {
      out.push({
        type: 'emoji',
        src: resolveEmojiAsset(topText.assetPath),
        alt: topText.key || 'emoji',
        sizeEm: 1.16
      })
    } else {
      appendParsedText(out, topText.key || '')
    }
    appendParsedText(out, `（${formatInt(Number(topText.count || 0))} 次）`)
    hasTail = true
  } else {
    appendParsedText(out, `${hasTail ? '，' : ''}今年没有命中可识别的小黄脸`)
    hasTail = true
  }

  const topUnicode = topUnicodeEmojis.value[0]
  if (topUnicode) {
    appendParsedText(
      out,
      `${hasTail ? '，' : ''}普通 Emoji 最常用 ${topUnicode.emoji}（${formatInt(Number(topUnicode.count || 0))} 次）。`
    )
  } else if (hasTail) {
    appendParsedText(out, '。')
  }
  return out
})

const cardRoot = ref(null)
const isCardVisible = ref(false)
const cursorTrails = ref([])
const cursorFxEnabled = ref(true)
const allWechatEmojiAssets = computed(() => {
  const values = Object.values(WechatEmojiTable || {})
  const uniq = new Set()
  for (const x of values) {
    const p = resolveEmojiAsset(String(x || '').trim())
    if (p) uniq.add(p)
  }
  return Array.from(uniq)
})

let trailSeq = 0
let lastSpawnAt = 0
let lastSpawnX = -9999
let lastSpawnY = -9999
const TRAIL_LIFETIME_MS = 780
const MIN_SPAWN_INTERVAL_MS = 28
const MIN_SPAWN_DISTANCE = 10
const MAX_TRAIL_COUNT = 32

const checkCardVisible = () => {
  if (!process.client) return false
  const rect = cardRoot.value?.getBoundingClientRect?.()
  if (!rect) return false
  const vh = window.innerHeight || 0
  const vw = window.innerWidth || 0
  return rect.bottom > vh * 0.12 && rect.top < vh * 0.88 && rect.right > 0 && rect.left < vw
}

const spawnCursorTrail = (x, y) => {
  const pool = allWechatEmojiAssets.value
  if (!pool.length) return
  const src = pool[Math.floor(Math.random() * pool.length)]
  const item = {
    id: ++trailSeq,
    x,
    y,
    src,
    size: 18 + Math.floor(Math.random() * 8),
    driftX: Math.round((Math.random() - 0.5) * 30),
    driftY: 20 + Math.floor(Math.random() * 20)
  }
  cursorTrails.value = [...cursorTrails.value.slice(-MAX_TRAIL_COUNT), item]
  setTimeout(() => {
    cursorTrails.value = cursorTrails.value.filter((t) => t.id !== item.id)
  }, TRAIL_LIFETIME_MS)
}

const onWindowPointerMove = (e) => {
  if (!process.client || !cursorFxEnabled.value) return
  if (e?.pointerType === 'touch') return
  const visible = checkCardVisible()
  isCardVisible.value = visible
  if (!visible) return

  const x = Number(e.clientX)
  const y = Number(e.clientY)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return

  const now = performance.now()
  const dx = x - lastSpawnX
  const dy = y - lastSpawnY
  const dist = Math.hypot(dx, dy)
  if ((now - lastSpawnAt) < MIN_SPAWN_INTERVAL_MS && dist < MIN_SPAWN_DISTANCE) return

  lastSpawnAt = now
  lastSpawnX = x
  lastSpawnY = y
  spawnCursorTrail(x, y)
}

const onWindowPointerLeave = () => {
  lastSpawnX = -9999
  lastSpawnY = -9999
}

onMounted(() => {
  if (!process.client) return
  try {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    cursorFxEnabled.value = !mq.matches
  } catch {
    cursorFxEnabled.value = true
  }
  isCardVisible.value = checkCardVisible()
  window.addEventListener('pointermove', onWindowPointerMove, { passive: true })
  window.addEventListener('pointerleave', onWindowPointerLeave, { passive: true })
})

onBeforeUnmount(() => {
  if (process.client) {
    window.removeEventListener('pointermove', onWindowPointerMove)
    window.removeEventListener('pointerleave', onWindowPointerLeave)
  }
  cursorTrails.value = []
})
</script>

<style scoped>
.wx-inline-emoji {
  object-fit: contain;
}

.emoji-cursor-layer {
  position: fixed;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 80;
}

.emoji-cursor-item {
  position: fixed;
  pointer-events: none;
  user-select: none;
  transform: translate(-50%, -50%);
  opacity: 0.94;
  animation: emoji-cursor-float 780ms ease-out forwards;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.18));
}

@keyframes emoji-cursor-float {
  0% {
    opacity: 0.94;
    transform: translate(-50%, -50%) scale(0.88);
  }
  100% {
    opacity: 0;
    transform: translate(calc(-50% + var(--drift-x)), calc(-50% - var(--drift-y))) scale(1.16);
  }
}
</style>
