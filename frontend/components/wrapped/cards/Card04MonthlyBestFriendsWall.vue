<template>
  <!-- slide 走 bleed：长廊是 WebGL，落进 FitScale 的 transform:scale 子树里会被整层重采样，
       12 张海报上的片名/演职员表首当其冲。bleed 之后画布直接吃 shell 的 flex 槽位。 -->
  <WrappedCardShell :card-id="card.id" :title="card.title" :narrative="''" :variant="variant" :wide="true" :dark="variant === 'slide'"
    :bleed="variant === 'slide'" :active="isActive">
    <template #narrative>
      <div
        class="mt-3 wrapped-body text-sm sm:text-base leading-relaxed"
        :class="variant === 'slide' ? 'text-[#FFFFFF73]' : 'text-[#7F7F7F]'"
      >
        <p>
          <template v-if="champion">
            十二个月，十二张海报——每张的主演，是那个月陪你最多的人。其中
            <span class="font-medium wrapped-privacy-name" :class="variant === 'slide' ? 'text-[#4ADE80]' : 'text-[#07C160]'">{{ champion.displayName }}</span> 一个人就主演了
            <span class="font-medium" :class="variant === 'slide' ? 'text-[#4ADE80]' : 'text-[#07C160]'">{{ champion.monthsWon }}</span> 部。
          </template>
          <template v-else-if="monthsWithWinner > 0">
            十二个月，十二张海报——其中
            <span class="font-medium" :class="variant === 'slide' ? 'text-[#4ADE80]' : 'text-[#07C160]'">{{ monthsWithWinner }}</span> 张排上了主演。
          </template>
          <template v-else>
            今年还没有足够的聊天互动数据来评选每月最佳好友。
          </template>
        </p>
      </div>
    </template>

    <!-- slide：高度还给 shell 的 flex 槽位（定高盒在竖幅下要么被 max-h 卡死、要么撑爆）；
         panel 仍是文档流里的一块，保留原来的定高 -->
    <div class="w-full" :class="variant === 'slide' ? 'absolute inset-0 flex flex-col' : ''">
      <div
        class="relative w-full"
        :class="variant === 'slide' ? 'flex-1 min-h-0' : 'h-[calc(var(--svh)*68)] min-h-[430px] max-h-[780px]'"
      >
        <MonthlyCompanionPosters
          :months="card.data?.months || []"
          :summary="card.data?.summary || null"
          :year="Number(card.data?.year) || 0"
          :active="isActive"
        />
      </div>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed } from 'vue'
import MonthlyCompanionPosters from '~/components/wrapped/visualizations/MonthlyCompanionPosters.vue'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  // deck 翻到本页时为 true：镜头从长廊深处横移过来，停在年度主演那张海报；翻走时暂停渲染
  isActive: { type: Boolean, default: true }
})

const monthsWithWinner = computed(() => Number(props.card?.data?.summary?.monthsWithWinner || 0))

const champion = computed(() => {
  const c = props.card?.data?.summary?.topChampion
  if (!c || !c.displayName || Number(c.monthsWon || 0) < 2) return null
  return c
})
</script>
