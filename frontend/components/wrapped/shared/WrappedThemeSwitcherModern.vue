<template>
  <div class="flex items-center gap-2">
    <span class="text-xs text-[#00000099]">Theme</span>
    <div class="inline-flex rounded-lg border border-[#EDEDED] overflow-hidden">
      <button
        v-for="t in themes"
        :key="t.value"
        class="px-3 py-1.5 text-xs wrapped-label transition-colors"
        :class="[
          theme === t.value
            ? 'bg-[#07C160] text-white'
            : 'bg-white text-[#333] hover:bg-[#F5F5F5]'
        ]"
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
