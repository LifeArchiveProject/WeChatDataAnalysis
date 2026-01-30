<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="card.narrative" :variant="variant">
    <template #badge>
      <span class="inline-flex items-center px-3 py-1 rounded-full text-xs bg-[#07C160]/10 text-[#07C160] border border-[#07C160]/20">
        作息规律
      </span>
    </template>

    <WeekdayHourHeatmap
      :weekday-labels="card.data?.weekdayLabels"
      :hour-labels="card.data?.hourLabels"
      :matrix="card.data?.matrix"
      :total-messages="card.data?.totalMessages || 0"
    />
  </WrappedCardShell>
</template>

<script setup>
defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' } // 'panel' | 'slide'
})
</script>
