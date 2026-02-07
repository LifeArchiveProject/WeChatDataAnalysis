<template>
  <div class="win98-switcher select-none">
    <span class="win98-switcher__label">Theme</span>

    <div class="win98-switcher__group" role="group" aria-label="Theme switcher">
      <button
        v-for="t in themes"
        :key="t.value"
        type="button"
        class="win98-switcher__btn"
        :class="{ 'is-active': theme === t.value }"
        @click="setTheme(t.value)"
      >
        {{ t.label }}
      </button>
    </div>
  </div>
</template>

<script setup>
const { theme, setTheme } = useWrappedTheme()

const themes = [
  { value: 'off', label: 'Modern' },
  { value: 'gameboy', label: 'Game Boy' },
  { value: 'win98', label: 'Win98' }
]
</script>

<style scoped>
.win98-switcher {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.win98-switcher__label {
  color: rgba(0, 0, 0, 0.75);
}

/* Bevel group container */
.win98-switcher__group {
  display: inline-flex;
  align-items: stretch;
  padding: 2px;
  background: #c0c0c0;
  border: 1px solid #808080;
  box-shadow:
    inset 1px 1px 0 #ffffff,
    inset -1px -1px 0 #000000;
}

.win98-switcher__btn {
  padding: 4px 10px;
  background: #c0c0c0;
  color: #000000;
  border: 1px solid transparent;
  cursor: pointer;
  font: inherit;
  line-height: 1;
}

.win98-switcher__btn:hover {
  filter: brightness(1.03);
}

.win98-switcher__btn.is-active {
  background: #000080 !important;
  color: #ffffff !important;
  border-color: #000080 !important;
}
</style>
