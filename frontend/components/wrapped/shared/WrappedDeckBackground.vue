<template>
  <!-- Shared backdrop for all "Wrapped" slides (keeps cover + cards visually consistent). -->
  <div class="absolute inset-0 pointer-events-none select-none z-0" aria-hidden="true">
    <!-- Soft color blobs (brand + warm highlights) -->
    <div class="absolute -top-24 -left-24 w-80 h-80 bg-[#07C160] opacity-[0.08] rounded-full blur-3xl"></div>
    <div class="absolute -top-24 -right-24 w-96 h-96 bg-[#F2AA00] opacity-[0.06] rounded-full blur-3xl"></div>
    <div class="absolute -bottom-28 left-40 w-[28rem] h-[28rem] bg-[#10AEEF] opacity-[0.06] rounded-full blur-3xl"></div>

    <!-- Subtle grid for "data / report" vibe -->
    <div
      class="absolute inset-0 bg-[linear-gradient(rgba(7,193,96,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(7,193,96,0.05)_1px,transparent_1px)] bg-[size:52px_52px] opacity-[0.28]"
    ></div>

    <!-- Grain/noise: adds texture without changing the base color -->
    <div class="absolute inset-0 wrapped-noise opacity-[0.06]"></div>

    <!-- Gentle vignette so typography stays readable on textured bg -->
    <div class="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-white/50 to-transparent"></div>
    <div class="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-white/40 to-transparent"></div>
  </div>
</template>

