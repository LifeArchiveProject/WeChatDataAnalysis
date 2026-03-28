<template>
  <div class="h-full min-h-0 flex overflow-hidden bg-white">
    <div class="flex-1 min-w-0">
      <BizMessages />
    </div>
  </div>
</template>

<script setup>

import BizMessages from "../components/BizMessages.vue";

useHead({
  title: '服务号消息 - WeChatDataAnalysis'
})
</script>
