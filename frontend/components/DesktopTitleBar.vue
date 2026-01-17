<template>
  <div v-if="isDesktop" class="desktop-titlebar" @dblclick="toggleMaximize">
    <div class="flex-1" />

    <div class="desktop-titlebar-controls">
      <button
        class="desktop-titlebar-btn"
        type="button"
        aria-label="最小化"
        title="最小化"
        @click="minimize"
      >
        <span class="desktop-titlebar-icon desktop-titlebar-icon-minimize" />
      </button>

      <button
        class="desktop-titlebar-btn"
        type="button"
        aria-label="最大化"
        title="最大化"
        @click="toggleMaximize"
      >
        <span class="desktop-titlebar-icon desktop-titlebar-icon-maximize" />
      </button>

      <button
        class="desktop-titlebar-btn desktop-titlebar-btn-close"
        type="button"
        aria-label="关闭"
        title="关闭"
        @click="closeWindow"
      >
        <span class="desktop-titlebar-icon desktop-titlebar-icon-close" />
      </button>
    </div>
  </div>
</template>

<script setup>
// Keep SSR/client initial DOM consistent; enable desktop titlebar after mount.
const isDesktop = ref(false)

onMounted(() => {
  isDesktop.value = !!window?.wechatDesktop
})

const minimize = () => {
  window.wechatDesktop?.minimize?.()
}

const toggleMaximize = () => {
  window.wechatDesktop?.toggleMaximize?.()
}

const closeWindow = () => {
  window.wechatDesktop?.close?.()
}
</script>

<style scoped>
.desktop-titlebar {
  height: var(--desktop-titlebar-height, 32px);
  background: #ededed;
  display: flex;
  align-items: stretch;
  flex-shrink: 0;

  /* Allow dragging the window from the title bar area */
  -webkit-app-region: drag;
  user-select: none;
}

.desktop-titlebar-controls {
  display: flex;
  align-items: stretch;

  /* Ensure buttons remain clickable */
  -webkit-app-region: no-drag;
}

.desktop-titlebar-btn {
  width: var(--desktop-titlebar-btn-width, 46px);
  height: var(--desktop-titlebar-height, 32px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 0;
  padding: 0;
  margin: 0;
  cursor: default;
}

.desktop-titlebar-btn:hover {
  background: rgba(0, 0, 0, 0.06);
}

.desktop-titlebar-btn:active {
  background: rgba(0, 0, 0, 0.1);
}

.desktop-titlebar-btn-close:hover {
  background: #e81123;
}

.desktop-titlebar-btn-close:active {
  background: #c50f1f;
}

.desktop-titlebar-icon {
  display: inline-block;
  width: 12px;
  height: 12px;
  position: relative;
}

.desktop-titlebar-icon-minimize::before {
  content: "";
  position: absolute;
  left: 1px;
  right: 1px;
  /* Optical centering: the glyph was anchored to the bottom, so it looked low. */
  top: 5px;
  height: 1px;
  background: #111;
}

.desktop-titlebar-icon-maximize::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 2px;
  right: 2px;
  bottom: 2px;
  border: 1px solid #111;
  box-sizing: border-box;
}

.desktop-titlebar-icon-close::before,
.desktop-titlebar-icon-close::after {
  content: "";
  position: absolute;
  left: 1px;
  right: 1px;
  top: 50%;
  height: 1px;
  background: #111;
  transform-origin: center;
}

.desktop-titlebar-icon-close::before {
  transform: translateY(-50%) rotate(45deg);
}

.desktop-titlebar-icon-close::after {
  transform: translateY(-50%) rotate(-45deg);
}

.desktop-titlebar-btn-close:hover .desktop-titlebar-icon-close::before,
.desktop-titlebar-btn-close:hover .desktop-titlebar-icon-close::after {
  background: #fff;
}
</style>
