<template>
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="card.narrative" :variant="variant">
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
