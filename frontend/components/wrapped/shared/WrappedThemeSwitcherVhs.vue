<template>
  <div class="vhs-panel select-none">
    <!-- VHS 风格物理按钮组 -->
    <div class="vhs-button-group">
      <button
        v-for="t in themes"
        :key="t.value"
        class="vhs-button"
        :class="{ 'is-active': theme === t.value, 'is-pressed': pressedKey === t.value }"
        @mousedown="pressButton(t.value)"
        @mouseup="releaseButton"
        @mouseleave="releaseButton"
        @click="setTheme(t.value)"
      >
        <span class="vhs-button-face">{{ t.label }}</span>
        <span class="vhs-led" :class="{ 'is-on': theme === t.value }"></span>
      </button>
    </div>
  </div>
</template>

<script setup>
const { theme, setTheme } = useWrappedTheme()

const themes = [
  { value: 'off', label: 'MOD' },
  { value: 'gameboy', label: 'GB' },
  { value: 'dos', label: 'DOS' },
  { value: 'vhs', label: 'VHS' }
]

const pressedKey = ref(null)

const pressButton = (value) => {
  pressedKey.value = value
}

const releaseButton = () => {
  pressedKey.value = null
}
</script>

<style scoped>
.vhs-panel {
  font-family: 'Arial', 'Helvetica', sans-serif;
}

.vhs-button-group {
  display: flex;
  gap: 6px;
  padding: 8px 10px;
  background: linear-gradient(180deg, #2a2a3e 0%, #1a1a2e 100%);
  border-radius: 4px;
  border: 1px solid #3a3a5e;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.1),
    0 2px 4px rgba(0,0,0,0.3);
}

.vhs-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
}

.vhs-button-face {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 24px;
  font-size: 9px;
  font-weight: bold;
  letter-spacing: 0.5px;
  color: #cccccc;
  background: linear-gradient(180deg, #4a4a5e 0%, #2a2a3e 50%, #3a3a4e 100%);
  border: 1px solid #5a5a7e;
  border-radius: 3px;
  box-shadow:
    0 2px 0 #1a1a2e,
    inset 0 1px 0 rgba(255,255,255,0.2);
  transition: all 0.05s;
}

.vhs-button:hover .vhs-button-face {
  background: linear-gradient(180deg, #5a5a6e 0%, #3a3a4e 50%, #4a4a5e 100%);
}

.vhs-button.is-pressed .vhs-button-face,
.vhs-button:active .vhs-button-face {
  transform: translateY(2px);
  box-shadow:
    0 0 0 #1a1a2e,
    inset 0 1px 2px rgba(0,0,0,0.3);
  background: linear-gradient(180deg, #3a3a4e 0%, #2a2a3e 50%, #3a3a4e 100%);
}

.vhs-button.is-active .vhs-button-face {
  background: linear-gradient(135deg, #e94560 0%, #c73e54 50%, #0f3460 100%);
  color: #ffffff;
  border-color: #e94560;
}

.vhs-led {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  transition: all 0.2s;
}

.vhs-led.is-on {
  background: #ff3333;
  border-color: #ff6666;
  box-shadow:
    0 0 4px #ff3333,
    0 0 8px #ff3333,
    0 0 12px rgba(255,51,51,0.5);
}
</style>
