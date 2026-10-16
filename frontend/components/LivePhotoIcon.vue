<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    version="1.1"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <!-- Keep the SVG identical to WeFlow/src/components/LivePhotoIcon.tsx for visual consistency -->
    <g stroke="none" stroke-width="1" fill="none" fill-rule="evenodd" stroke-linecap="round" stroke-linejoin="round">
      <g stroke="currentColor" stroke-width="2">
        <circle fill="currentColor" stroke="none" cx="12" cy="12" r="2.5" />
        <circle cx="12" cy="12" r="5.5" />
        <circle cx="12" cy="12" r="9" stroke-dasharray="1 3.7" />
      </g>
    </g>
  </svg>
</template>

<script setup>
defineProps({
  size: {
    type: [Number, String],
    default: 24
  }
})
</script>

