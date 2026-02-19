<template>
  <div class="w-full">
    <AnnualCalendarHeatmap
      :year="year"
      :daily-counts="annualDailyCounts"
      :days="daysInYear"
      :highlights="annualHighlights"
    />
  </div>
</template>

<script setup>
import AnnualCalendarHeatmap from '~/components/wrapped/visualizations/AnnualCalendarHeatmap.vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) }
})

const year = computed(() => {
  const v = props.data?.annualHeatmap?.year ?? props.data?.year ?? new Date().getFullYear()
  const y = Number(v)
  return Number.isFinite(y) ? y : new Date().getFullYear()
})

const daysInYear = computed(() => {
  const d = Number(props.data?.annualHeatmap?.days || 0)
  if (Number.isFinite(d) && d > 0) return d
  const y = Number(year.value)
  const isLeap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)
  return isLeap ? 366 : 365
})

const annualDailyCounts = computed(() => {
  const a = props.data?.annualHeatmap
  const arr = a?.dailyCounts
  return Array.isArray(arr) ? arr : []
})

const annualHighlights = computed(() => {
  const a = props.data?.annualHeatmap
  const hs = a?.highlights
  return Array.isArray(hs) ? hs : []
})
</script>
