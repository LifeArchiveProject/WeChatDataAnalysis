<template>
  <div class="gameboy-menu select-none">
    <!-- 像素风格菜单框 -->
    <div class="gameboy-menu-box">
      <div class="gameboy-menu-title">SELECT THEME</div>
      <div class="gameboy-menu-items">
        <button
          v-for="t in themes"
          :key="t.value"
          class="gameboy-menu-item"
          :class="{ 'is-active': theme === t.value }"
          @click="selectTheme(t.value)"
        >
          <span class="gameboy-cursor">{{ theme === t.value ? '▶' : ' ' }}</span>
          <span class="gameboy-label">{{ t.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
const { theme, setTheme } = useWrappedTheme()

const themes = [
  { value: 'off', label: 'MODERN' },
  { value: 'gameboy', label: 'GAME BOY' },
  { value: 'win98', label: 'WIN98' }
]

const selectTheme = (value) => {
  setTheme(value)
}
</script>

<style scoped>
.gameboy-menu {
  font-family: 'Press Start 2P', 'Courier New', monospace;
  font-size: 8px;
  line-height: 1.5;
}

.gameboy-menu-box {
  background: #0f380f;
  border: 3px solid #306230;
  padding: 8px;
  box-shadow:
    inset 2px 2px 0 #9bbc0f,
    inset -2px -2px 0 #0f380f;
}

.gameboy-menu-title {
  color: #9bbc0f;
  text-align: center;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 2px dashed #306230;
}

.gameboy-menu-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.gameboy-menu-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  color: #9bbc0f;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.1s;
  font-family: inherit;
  font-size: inherit;
}

.gameboy-menu-item:hover {
  background: #306230;
}

.gameboy-menu-item.is-active {
  color: #8bac0f;
}

.gameboy-cursor {
  width: 10px;
  display: inline-block;
}

.gameboy-label {
  letter-spacing: 1px;
}
</style>
