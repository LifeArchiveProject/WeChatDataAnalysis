<template>
  <div class="h-screen flex overflow-hidden bg-white">
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