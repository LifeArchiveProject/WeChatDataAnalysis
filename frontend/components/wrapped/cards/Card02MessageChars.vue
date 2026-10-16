<template>
  <!-- slide 模式隐藏外壳标题：两句题词拆进可视化本体（hero 首行 / 书本引题 / 键盘脚注），高度全部让给内容 -->
  <WrappedCardShell
    :card-id="card.id"
    :title="card.title"
    :narrative="''"
    :variant="variant"
    :hide-chrome="variant === 'slide'"
  >
    <template #narrative>
      <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
        <p>答案都在这块键盘上——它替你记着每一次敲击。</p>
      </div>
    </template>

    <MessageCharsChart :data="card.data || {}" :title="card.title" :is-active="isActive" />
  </WrappedCardShell>
</template>

<script setup>
import MessageCharsChart from '~/components/wrapped/visualizations/MessageCharsChart.vue'

defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  // deck 翻到本页时置 true，首次为 true 触发入场动画；false 时暂停循环动画。
  isActive: { type: Boolean, default: true }
})
</script>
