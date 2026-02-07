<template>
  <component :is="themeSwitcherComponent" />
</template>

<script setup>
const { theme } = useWrappedTheme()

// 根据当前主题动态选择对应的切换器组件
const themeSwitcherComponent = computed(() => {
  const map = {
    off: resolveComponent('WrappedThemeSwitcherModern'),
    gameboy: resolveComponent('WrappedThemeSwitcherGameboy'),
    win98: resolveComponent('WrappedThemeSwitcherWin98')
  }
  return map[theme.value] || map.off
})
</script>
