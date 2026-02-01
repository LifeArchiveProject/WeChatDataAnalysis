<template>
  <div class="win98-taskbar" @wheel.stop.prevent>
    <button
      type="button"
      class="win98-start"
      aria-label="Start"
      :aria-pressed="startPressed ? 'true' : 'false'"
      @mousedown="startPressed = true"
      @mouseup="startPressed = false"
      @mouseleave="startPressed = false"
    >
      <img class="win98-start__icon" src="/assets/images/windows-0.png" alt="" aria-hidden="true" />
      <span class="win98-start__text">Start</span>
    </button>

    <div class="win98-taskbar__divider" aria-hidden="true"></div>

    <button
      type="button"
      class="win98-task"
      :title="title"
      tabindex="-1"
      aria-label="Active window"
    >
      {{ title }}
    </button>

    <div class="win98-taskbar__spacer" aria-hidden="true"></div>

    <div class="win98-tray" aria-label="System tray">
      <div class="win98-tray__clock" :title="timeText">
        {{ timeText }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  title: { type: String, default: 'WeChat Wrapped' }
})

const startPressed = ref(false)
const timeText = ref('--:--')
let timer = null

const formatWin98Time = (d) => {
  try {
    // Win98 screenshot style: 12-hour + AM/PM
    return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(d)
  } catch {
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  }
}

const updateClock = () => { timeText.value = formatWin98Time(new Date()) }

onMounted(() => {
  updateClock()
  timer = setInterval(updateClock, 30_000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  timer = null
})
</script>

<style scoped>
.win98-taskbar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  background: #c0c0c0;
  border-top: 2px solid #ffffff;
  z-index: 40;
}

.win98-start {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px 0 8px;
  font-weight: 700;
}

.win98-start__icon {
  width: 16px;
  height: 16px;
  image-rendering: pixelated;
}

.win98-start__text {
  line-height: 1;
}

.win98-taskbar__divider {
  width: 2px;
  height: 28px;
  background: #808080;
  box-shadow: 1px 0 0 #ffffff;
}

.win98-task {
  height: 30px;
  min-width: 160px;
  max-width: 56vw;
  padding: 0 10px;
  font-weight: 400;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.win98-task {
  /* Active window task button: depressed + dither fill (Win95-ish) */
  background: var(--win98-dither) !important;
  box-shadow: none !important;
  border-top: 1px solid var(--win98-dkshadow) !important;
  border-left: 1px solid var(--win98-dkshadow) !important;
  border-right: 1px solid var(--win98-hi) !important;
  border-bottom: 1px solid var(--win98-hi) !important;
}

.win98-start[aria-pressed="true"] {
  /* Start button pressed: depressed + dither */
  background: var(--win98-dither) !important;
  box-shadow: none !important;
  border-top: 1px solid var(--win98-dkshadow) !important;
  border-left: 1px solid var(--win98-dkshadow) !important;
  border-right: 1px solid var(--win98-hi) !important;
  border-bottom: 1px solid var(--win98-hi) !important;
}

.win98-taskbar__spacer {
  flex: 1;
}

.win98-tray {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 8px;
  background: #c0c0c0;
  border-top: 1px solid var(--win98-shadow);
  border-left: 1px solid var(--win98-shadow);
  border-right: 1px solid var(--win98-hi);
  border-bottom: 1px solid var(--win98-hi);
}

.win98-tray__clock {
  font-size: 11px;
  color: #000000;
  line-height: 1;
  white-space: nowrap;
}
</style>
