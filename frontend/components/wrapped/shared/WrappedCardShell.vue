<template>
  <div v-if="variant === 'panel'" class="bg-white rounded-2xl border border-[#EDEDED] overflow-hidden">
    <div class="px-6 py-5 border-b border-[#F3F3F3]">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="wrapped-title text-xl text-[#000000e6]">{{ title }}</h2>
          <slot name="narrative">
            <p v-if="narrative" class="mt-2 wrapped-body text-sm text-[#7F7F7F] whitespace-pre-wrap">
              {{ narrative }}
            </p>
          </slot>
        </div>
        <slot name="badge" />
      </div>
    </div>
    <div class="px-6 py-6">
      <slot />
    </div>
  </div>

  <!-- Slide 模式：单张卡片占据全页面，背景由外层（年度总结）统一控制 -->
  <section v-else class="relative h-full w-full overflow-hidden">
    <!-- 影院底：铺满整张 slide，标题和内容都在同一片暗场里 -->
    <div v-if="dark" class="wrapped-stage-dark" :class="`wrapped-stage-dark--${tone}`" aria-hidden="true" />
    <WrappedCinemaOverlay v-if="dark" :grain="0.05" />
    <div
      class="relative h-full flex flex-col"
      :class="hideChrome ? '' : (wide
        ? 'px-10 pt-20 pb-12 sm:px-14 sm:pt-24 sm:pb-14 lg:px-20 xl:px-20 2xl:px-40'
        : 'max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12')"
    >
        <div v-if="!hideChrome" class="flex items-start justify-between gap-4">
          <div>
            <h2
              class="wrapped-title"
              :class="[compact ? 'text-lg sm:text-xl' : 'text-2xl sm:text-3xl', dark ? 'text-[#F3F8F4]' : 'text-[#000000e6]']"
            >{{ title }}</h2>
            <slot name="narrative">
              <p
                v-if="narrative"
                class="mt-3 wrapped-body text-sm sm:text-base max-w-2xl whitespace-pre-wrap"
                :class="dark ? 'text-[#FFFFFF73]' : 'text-[#7F7F7F]'"
              >
                {{ narrative }}
              </p>
            </slot>
          </div>
          <slot name="badge" />
        </div>

        <!-- min-h-0 让 flex 子项可收缩，FitScale 在可用高度内等比缩放，保证一屏放下。
             bleed 模式跳过 FitScale：内容自行 absolute inset-0 铺满，可用高度变化（如顶部横幅）时不缩放不留缝 -->
        <div class="flex-1 min-h-0 relative" :class="hideChrome ? '' : (compact ? 'mt-2 sm:mt-3' : 'mt-4 sm:mt-6')">
          <slot v-if="bleed" />
          <WrappedFitScale v-else class="relative">
            <slot />
          </WrappedFitScale>
        </div>
    </div>
  </section>
</template>

<script setup>
import { inject, onBeforeUnmount, ref, watch } from 'vue'
import WrappedFitScale from '~/components/wrapped/shared/WrappedFitScale.vue'
import WrappedCinemaOverlay from '~/components/wrapped/shared/WrappedCinemaOverlay.vue'

const props = defineProps({
  cardId: { type: Number, required: true },
  title: { type: String, required: true },
  narrative: { type: String, default: '' },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  // Slide 模式下是否取消 max-width 限制（让内容直接铺满页面宽度）。
  // 用于需要横向展示的可视化（如年度日历热力图）。
  wide: { type: Boolean, default: false },
  // 隐藏标题/叙事区域（如关键词卡片 storm 阶段沉浸模式）。
  hideChrome: { type: Boolean, default: false },
  // 满幅模式：slot 不经过 FitScale，由卡片自己 absolute inset-0 铺满（作息卡的全出血天空）。
  bleed: { type: Boolean, default: false },
  // 影院模式：内容区铺一层满幅深色影院底（页头仍留在浅色底上，如年度台历）。
  dark: { type: Boolean, default: false },
  // 暗场配色：'cinema' 暖绿影厅（海报长廊）/ 'foil' 冷蓝开卡桌（表情卡包）
  tone: { type: String, default: 'cinema' },
  // 本卡是否正处在 deck 的当前页（决定要不要把顶栏也切成浅色）
  active: { type: Boolean, default: false },
  // 紧凑页头：标题降一级、留白收紧，把高度让给主视觉（口头禅卡的词典要占满画面）
  compact: { type: Boolean, default: false }
})

// 影院卡翻到台前时，把 deck 顶栏与底色一起压暗；翻走再交还
const deckDark = inject('deckDark', ref(false))
let claimed = false

const syncDeckTone = () => {
  const want = props.variant === 'slide' && props.dark && props.active
  if (want === claimed) return
  claimed = want
  deckDark.value = want
}

watch(() => [props.variant, props.dark, props.active], syncDeckTone, { immediate: true })

onBeforeUnmount(() => {
  if (claimed) deckDark.value = false
})
</script>

<style scoped>
/* 暗场底：铺满整张 slide */
.wrapped-stage-dark {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

/* 影厅：暖绿聚光，给电影海报长廊 */
.wrapped-stage-dark--cinema {
  background:
    radial-gradient(64% 62% at 50% 46%, rgba(150, 226, 186, 0.12), rgba(150, 226, 186, 0) 70%),
    radial-gradient(94% 58% at 50% 106%, rgba(4, 8, 7, 0.92), rgba(4, 8, 7, 0) 74%),
    linear-gradient(180deg, #101A16 0%, #0C1410 46%, #070C0A 100%);
}

/* 夜航航站楼：绿黑夜空 + 停机坪远灯 + 地平线跑道灯带 + 边缘暗角，
   与影厅（中央聚光）/开卡桌（冷蓝射灯）拉开距离 */
.wrapped-stage-dark--terminal {
  background:
    radial-gradient(circle 52px at 79% 26%, rgba(232, 181, 74, 0.05), rgba(232, 181, 74, 0) 72%),
    radial-gradient(circle 68px at 10% 20%, rgba(150, 200, 235, 0.04), rgba(150, 200, 235, 0) 72%),
    radial-gradient(circle 40px at 91% 58%, rgba(62, 229, 138, 0.05), rgba(62, 229, 138, 0) 72%),
    radial-gradient(140% 110% at 50% 38%, rgba(0, 0, 0, 0) 56%, rgba(0, 0, 0, 0.42) 100%),
    radial-gradient(72% 46% at 50% 108%, rgba(62, 229, 138, 0.12), rgba(62, 229, 138, 0) 72%),
    radial-gradient(52% 38% at 84% -8%, rgba(120, 180, 150, 0.07), rgba(120, 180, 150, 0) 70%),
    linear-gradient(180deg, #0B1210 0%, #08100C 52%, #040906 100%);
}

/* 打磨过的航站楼地面：底部一条微弱反光带 */
.wrapped-stage-dark--terminal::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 24%;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0) 0%, rgba(214, 255, 231, 0.025) 34%, rgba(0, 0, 0, 0.3) 100%);
}

/* 开卡桌：冷蓝夜色 + 桌面射灯 + 卡垫网点，和影厅拉开距离 */
.wrapped-stage-dark--foil {
  background:
    radial-gradient(46% 40% at 50% 40%, rgba(150, 180, 255, 0.16), rgba(150, 180, 255, 0) 72%),
    radial-gradient(70% 44% at 50% 96%, rgba(120, 200, 255, 0.07), rgba(120, 200, 255, 0) 76%),
    radial-gradient(120% 86% at 50% 50%, rgba(0, 0, 0, 0) 44%, rgba(0, 0, 0, 0.62) 100%),
    linear-gradient(180deg, #0B1020 0%, #080C18 48%, #04060D 100%);
}
/* 网点卡垫：极淡，只在近处才看得出纹理 */
.wrapped-stage-dark--foil::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: radial-gradient(58% 52% at 50% 46%, #000 0%, transparent 78%);
  -webkit-mask-image: radial-gradient(58% 52% at 50% 46%, #000 0%, transparent 78%);
}
</style>
