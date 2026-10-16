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
    <!-- ⚠️ 这里以前用的是 Tailwind 的 sm:/lg:/2xl: 断点，判的是**浏览器窗口宽度**。
         画幅框定之后那是错的对象：9:16 舞台可以在 2560px 宽的窗口里，于是 2xl:px-40
         从两侧各吃掉 160px（900px 宽的舞台被吃掉 36%），而窗口被拖窄时又会突然掉档。
         现在一律按**画幅档位**给常量内边距——同一个画幅，无论窗口多大，版心恒定。 -->
    <div class="wr-shell relative h-full flex flex-col" :class="shellClass">
        <div v-if="!hideChrome" class="flex items-start justify-between gap-4">
          <div>
            <h2 class="wr-shell-title wrapped-title" :class="dark ? 'text-[#F3F8F4]' : 'text-[#000000e6]'">{{ title }}</h2>
            <!-- 卡片大多会覆盖这个插槽，里面用的是 Tailwind 的 text-sm/text-base（rem 基准），
                 CSS 变量管不到。用 zoom 缩放整棵子树：它参与布局（不像 transform 那样只做视觉变换），
                 rem 字号也一起放大；--wf-text 为 1 时是空操作，16:9 逐像素零回归。 -->
            <div class="wr-shell-narrative-slot">
              <slot name="narrative">
                <p
                  v-if="narrative"
                  class="wr-shell-narrative mt-3 wrapped-body max-w-2xl whitespace-pre-wrap"
                  :class="dark ? 'text-[#FFFFFF73]' : 'text-[#7F7F7F]'"
                >
                  {{ narrative }}
                </p>
              </slot>
            </div>
          </div>
          <slot name="badge" />
        </div>

        <!-- min-h-0 让 flex 子项可收缩，FitScale 在可用高度内等比缩放，保证一屏放下。
             bleed 模式跳过 FitScale：内容自行 absolute inset-0 铺满，可用高度变化（如顶部横幅）时不缩放不留缝 -->
        <div class="wr-shell-body flex-1 min-h-0 relative" :class="hideChrome ? '' : (compact ? 'is-compact' : '')">
          <slot v-if="bleed" />
          <WrappedFitScale v-else class="relative">
            <slot />
          </WrappedFitScale>
        </div>
    </div>
  </section>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
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

const shellClass = computed(() => {
  if (props.hideChrome) return ''
  return [props.wide ? 'wr-shell--wide' : 'wr-shell--narrow', props.compact ? 'is-compact' : '']
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
/* ── 版心：按画幅档位给常量，不再随浏览器窗口跳档 ──
   wide 的取值等于旧代码在 ≥1536px 窗口（2xl，桌面绝大多数情况）下的计算值，
   所以 16:9 / 跟随窗口的观感与改造前一致。 */
.wr-shell--wide {
  padding: 96px 160px 56px;   /* = pt-24 / 2xl:px-40 / pb-14 */
}

.wr-shell--narrow {
  max-width: 64rem;           /* = max-w-5xl，与改造前一致 */
  margin-inline: auto;
  padding: 48px 32px;         /* = sm:px-8 sm:py-12 */
}

/* 字号乘 --wf-text：让文字占画幅宽度的比例在各画幅恒定。
   16:9 下 --wf-text = 1，取值与旧的 sm:text-3xl / sm:text-base 逐像素相同。 */
.wr-shell-title { font-size: calc(30px * var(--wf-title, 1)); line-height: 1.25; }
.wr-shell.is-compact .wr-shell-title { font-size: calc(20px * var(--wf-title, 1)); }
.wr-shell-narrative { font-size: 16px; line-height: 1.8; }
/* 整棵叙事子树按画幅放大（含卡片自己用 Tailwind rem 字号写的段落） */
.wr-shell-narrative-slot { zoom: var(--wf-text, 1); }

/* ⚠️ 这两条必须挂在 .wr-shell-- 后代上：hideChrome 时 shellClass 为空，
   页头整块不存在，内容区的上边距原本就是 0。写成无条件的 `.wr-shell-body{margin-top:24px}`
   会给 hide-chrome 的卡（C2 打字 / C6 口头禅）凭空加 24px，
   既让 16:9 的画面整体下移 12px，又把框定画幅里的 FitScale 从 1 压到 0.986——那就是「靠缩小适配」。 */
.wr-shell--wide > .wr-shell-body,
.wr-shell--narrow > .wr-shell-body { margin-top: 24px; }        /* = sm:mt-6 */
.wr-shell--wide > .wr-shell-body.is-compact,
.wr-shell--narrow > .wr-shell-body.is-compact { margin-top: 12px; }  /* = sm:mt-3 */

/* 竖幅/方幅：舞台窄了，版心跟着收，把宽度还给内容（字号一律不动）。
   数值按各档设计宽的 ~7% 取，与 wide 的 160/1600=10% 同一套比例语言但更省。 */
/* 窄画幅把左右留白压到最小：画面就那么宽，边距吃掉的每一像素都是内容的。
   顶部留白按 --wf-text 一起长，页头字变大了才不会顶到画幅上沿。 */
[data-frame-tier="landscape"] .wr-shell--wide { padding: calc(72px * var(--wf-text, 1)) 72px 44px; }
[data-frame-tier="square"] .wr-shell--wide { padding: calc(66px * var(--wf-text, 1)) 44px 38px; }
[data-frame-tier="portrait"] .wr-shell--wide { padding: calc(60px * var(--wf-text, 1)) 32px 32px; }
[data-frame-tier="tall"] .wr-shell--wide { padding: calc(54px * var(--wf-text, 1)) 24px 28px; }

[data-frame-tier="square"] .wr-shell--narrow,
[data-frame-tier="portrait"] .wr-shell--narrow,
[data-frame-tier="tall"] .wr-shell--narrow { max-width: none; padding: 44px 32px; }

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
