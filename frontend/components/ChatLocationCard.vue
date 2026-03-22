<template>
  <div
    class="wechat-location-card-wrap"
    :class="isSent ? 'wechat-location-card-wrap--sent' : 'wechat-location-card-wrap--received'"
  >
    <div
      class="wechat-location-card"
      :class="{ 'wechat-location-card--sent': isSent }"
      role="button"
      tabindex="0"
      @click="openLocation"
      @keydown.enter.prevent="openLocation"
      @keydown.space.prevent="openLocation"
    >
      <div class="wechat-location-card__text">
        <div class="wechat-location-card__title">{{ primaryText }}</div>
        <div v-if="secondaryText" class="wechat-location-card__subtitle">{{ secondaryText }}</div>
      </div>

      <div class="wechat-location-card__map" :class="{ 'wechat-location-card__map--placeholder': !mapTileUrl }">
        <img
          v-if="mapTileUrl"
          :src="mapTileUrl"
          alt="地图预览"
          class="wechat-location-card__map-image"
          loading="lazy"
          referrerpolicy="no-referrer"
        >
        <div class="wechat-location-card__map-overlay"></div>
        <div class="wechat-location-card__pin" :style="markerStyle" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 22s7-5.82 7-12a7 7 0 1 0-14 0c0 6.18 7 12 7 12Z" fill="#22c55e" />
            <circle cx="12" cy="10" r="3.2" fill="#ffffff" />
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  message: { type: Object, default: () => ({}) },
})

const TILE_SIZE = 256
const MAP_ZOOM = 15

const cleanText = (value) => String(value || '').replace(/\s+/g, ' ').trim()

const toFiniteNumber = (value) => {
  const num = Number.parseFloat(String(value ?? '').trim())
  return Number.isFinite(num) ? num : null
}

const latitude = computed(() => {
  const num = toFiniteNumber(props.message?.locationLat)
  return num != null && Math.abs(num) <= 90 ? num : null
})

const longitude = computed(() => {
  const num = toFiniteNumber(props.message?.locationLng)
  return num != null && Math.abs(num) <= 180 ? num : null
})

const primaryText = computed(() => {
  return cleanText(
    props.message?.locationPoiname
    || props.message?.title
    || props.message?.content
    || '位置'
  ) || '位置'
})

const secondaryText = computed(() => {
  const label = cleanText(props.message?.locationLabel)
  return label && label !== primaryText.value ? label : ''
})

const isSent = computed(() => !!props.message?.isSent)

const mapTileMeta = computed(() => {
  const lat = latitude.value
  const lng = longitude.value
  if (lat == null || lng == null) return null

  const scale = Math.pow(2, MAP_ZOOM)
  const worldX = ((lng + 180) / 360) * scale * TILE_SIZE
  const latRad = (lat * Math.PI) / 180
  const worldY = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * scale * TILE_SIZE
  const tileX = Math.floor(worldX / TILE_SIZE)
  const tileY = Math.floor(worldY / TILE_SIZE)
  const offsetX = worldX - tileX * TILE_SIZE
  const offsetY = worldY - tileY * TILE_SIZE

  return {
    tileX,
    tileY,
    left: `${(offsetX / TILE_SIZE) * 100}%`,
    top: `${(offsetY / TILE_SIZE) * 100}%`,
  }
})

const mapTileUrl = computed(() => {
  const meta = mapTileMeta.value
  if (!meta) return ''
  return `https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x=${meta.tileX}&y=${meta.tileY}&z=${MAP_ZOOM}`
})

const markerStyle = computed(() => {
  const meta = mapTileMeta.value
  return {
    left: meta?.left || '50%',
    top: meta?.top || '50%',
  }
})

const mapLink = computed(() => {
  const name = encodeURIComponent(primaryText.value || secondaryText.value || '位置')
  const lat = latitude.value
  const lng = longitude.value
  if (lat != null && lng != null) {
    return `https://uri.amap.com/marker?position=${lng},${lat}&name=${name}`
  }
  if (name) return `https://uri.amap.com/search?keyword=${name}`
  return ''
})

const openLocation = () => {
  if (!process.client) return
  const href = mapLink.value
  if (!href) return
  window.open(href, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.wechat-location-card-wrap {
  --location-card-bg: var(--chat-bubble-received);
  --location-card-text: var(--chat-bubble-received-text);
  --location-card-muted: var(--chat-sender-name);
  position: relative;
  display: inline-block;
}

.wechat-location-card-wrap--sent {
  --location-card-bg: var(--chat-bubble-sent);
  --location-card-text: var(--chat-bubble-sent-text);
  --location-card-muted: rgba(255, 255, 255, 0.78);
}

.wechat-location-card-wrap--received::before,
.wechat-location-card-wrap--sent::after {
  content: '';
  position: absolute;
  top: 12px;
  width: 12px;
  height: 12px;
  background: var(--location-card-bg);
  transform: rotate(45deg);
  border-radius: 2px;
}

.wechat-location-card-wrap--received::before {
  left: -4px;
}

.wechat-location-card-wrap--sent::after {
  right: -4px;
}

.wechat-location-card {
  width: 208px;
  overflow: hidden;
  border-radius: var(--message-radius);
  border: none;
  background: var(--location-card-bg);
  box-shadow: none;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.wechat-location-card--sent {
  background: var(--location-card-bg);
}

.wechat-location-card__text {
  padding: 10px 12px 8px;
  background: var(--location-card-bg);
}

.wechat-location-card--sent .wechat-location-card__text {
  background: var(--location-card-bg);
}

.wechat-location-card__title {
  color: var(--location-card-text);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.wechat-location-card__subtitle {
  margin-top: 4px;
  color: var(--location-card-muted);
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wechat-location-card--sent .wechat-location-card__subtitle {
  color: var(--location-card-muted);
}

.wechat-location-card__map {
  position: relative;
  height: 98px;
  overflow: hidden;
  background:
    linear-gradient(0deg, rgba(255, 255, 255, 0.3), rgba(255, 255, 255, 0.3)),
    linear-gradient(135deg, #d7eef5 0%, #f6f8fb 45%, #ece7cf 100%);
}

.wechat-location-card__map--placeholder::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(90deg, rgba(255,255,255,0.65) 0 8%, transparent 8% 34%, rgba(255,255,255,0.65) 34% 42%, transparent 42% 100%),
    linear-gradient(0deg, rgba(255,255,255,0.7) 0 10%, transparent 10% 38%, rgba(255,255,255,0.7) 38% 46%, transparent 46% 100%);
  opacity: 0.65;
}

.wechat-location-card__map-image,
.wechat-location-card__map-overlay {
  position: absolute;
  inset: 0;
}

.wechat-location-card__map-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.wechat-location-card__map-overlay {
  background: linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 38%, rgba(17,24,39,0.06) 100%);
}

.wechat-location-card__pin {
  position: absolute;
  width: 22px;
  height: 22px;
  transform: translate(-50%, -92%);
  filter: drop-shadow(0 4px 8px rgba(34, 197, 94, 0.28));
}

.wechat-location-card__pin svg {
  display: block;
  width: 100%;
  height: 100%;
}

html[data-theme='dark'] .wechat-location-card-wrap {
  --location-card-bg: var(--merged-history-bg);
  --location-card-text: var(--merged-history-title);
  --location-card-muted: var(--merged-history-preview);
}
</style>
