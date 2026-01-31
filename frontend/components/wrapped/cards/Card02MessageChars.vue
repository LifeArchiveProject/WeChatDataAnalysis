<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant">
    <template #narrative>
      <div class="mt-2 wrapped-body text-sm text-[#7F7F7F] leading-relaxed">
        <p>
          <template v-if="sentChars > 0">
            这一年，你在微信里敲下了
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(sentChars) }}</span>
            个字。
          </template>
          <template v-else>
            这一年，你还没有发出文字消息。
          </template>

          <template v-if="receivedChars > 0">
            你也收到了
            <span class="wrapped-number text-[#07C160] font-semibold">{{ formatInt(receivedChars) }}</span>
            个字。
          </template>
        </p>
      </div>
    </template>

    <MessageCharsChart :data="card.data || {}" />
  </WrappedCardShell>
</template>

<script setup>
import MessageCharsChart from '~/components/wrapped/visualizations/MessageCharsChart.vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})

const nfInt = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const formatInt = (n) => nfInt.format(Math.round(Number(n) || 0))

const sentChars = computed(() => Number(props.card?.data?.sentChars || 0))
const receivedChars = computed(() => Number(props.card?.data?.receivedChars || 0))
</script>

