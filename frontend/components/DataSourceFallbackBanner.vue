<template>
  <section
    v-if="status?.fallbackActive"
    class="data-source-fallback-banner"
    role="status"
    aria-live="polite"
  >
    <div class="data-source-fallback-banner__inner">
      <span class="data-source-fallback-banner__indicator" aria-hidden="true"></span>
      <p>{{ displayMessage }}</p>
    </div>
  </section>
</template>

<script setup>
const props = defineProps({
  status: {
    type: Object,
    default: null,
  },
})

const displayMessage = computed(() => {
  const message = String(props.status?.message || '').trim()
  if (message) return message

  const reason = String(props.status?.reason || '').trim()
  const reasonText = reason ? `：${reason}` : ''
  const retryAfter = Number(props.status?.retryAfterSeconds || 0)
  const retryText = retryAfter > 0 ? ` 约 ${Math.floor(retryAfter)} 秒后可再次尝试实时连接。` : ''
  return `实时更新暂时不可用${reasonText}。当前显示已解密数据库快照，期间的新消息不会自动更新。${retryText}`
})
</script>

<style scoped>
.data-source-fallback-banner {
  flex: 0 0 auto;
  width: 100%;
  border-bottom: 1px solid #f1d39a;
  background: #fff8e8;
  color: #744610;
}

.data-source-fallback-banner__inner {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 9px;
  padding: 8px 16px;
  font-size: 12px;
  line-height: 1.55;
}

.data-source-fallback-banner__inner p {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.data-source-fallback-banner__indicator {
  width: 7px;
  height: 7px;
  margin-top: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #c87912;
  box-shadow: 0 0 0 3px rgba(200, 121, 18, 0.14);
}

:global(html[data-theme='dark']) .data-source-fallback-banner {
  border-bottom-color: #654d2e;
  background: #33291d;
  color: #f2d29f;
}

:global(html[data-theme='dark']) .data-source-fallback-banner__indicator {
  background: #e0a24a;
  box-shadow: 0 0 0 3px rgba(224, 162, 74, 0.16);
}

@media (max-width: 640px) {
  .data-source-fallback-banner__inner {
    padding: 8px 12px;
  }
}
</style>
