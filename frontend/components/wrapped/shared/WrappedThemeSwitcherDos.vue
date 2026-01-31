<template>
  <div class="dos-menu select-none">
    <!-- DOS 风格功能键菜单栏 -->
    <div class="dos-menu-bar">
      <button
        v-for="(t, idx) in themes"
        :key="t.value"
        class="dos-menu-item"
        :class="{ 'is-active': theme === t.value }"
        @click="setTheme(t.value)"
      >
        <span class="dos-fkey">F{{ idx + 1 }}</span>
        <span class="dos-label">{{ t.label }}</span>
      </button>
    </div>
    <!-- 状态提示 -->
    <div class="dos-status">
      Press F1-F4 to switch theme
    </div>
  </div>
</template>

<script setup>
const { theme, setTheme } = useWrappedTheme()

const themes = [
  { value: 'off', label: 'Modern' },
  { value: 'gameboy', label: 'GameBoy' },
  { value: 'dos', label: 'DOS' },
  { value: 'vhs', label: 'VHS' }
]
</script>

<style scoped>
.dos-menu {
  font-family: 'Courier New', 'Consolas', monospace;
  font-size: 11px;
}

.dos-menu-bar {
  display: flex;
  background: #000000;
  border: 1px solid #33ff33;
  overflow: hidden;
}

.dos-menu-item {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  background: #000000;
  color: #33ff33;
  border: none;
  border-right: 1px solid #1a5c1a;
  cursor: pointer;
  text-shadow: 0 0 5px #33ff33;
  transition: all 0.1s;
  font-family: inherit;
  font-size: inherit;
}

.dos-menu-item:last-child {
  border-right: none;
}

.dos-menu-item:hover {
  background: #0a1a0a;
}

.dos-menu-item.is-active {
  background: #33ff33;
  color: #000000;
  text-shadow: none;
}

.dos-fkey {
  font-weight: bold;
  padding: 1px 3px;
  background: #1a5c1a;
  color: #33ff33;
  font-size: 9px;
}

.dos-menu-item.is-active .dos-fkey {
  background: #000000;
  color: #33ff33;
}

.dos-label {
  letter-spacing: 0.5px;
}

.dos-status {
  margin-top: 4px;
  color: #1a5c1a;
  font-size: 9px;
  text-shadow: 0 0 3px #1a5c1a;
}
</style>
