<template>
  <WrappedCardShell
    :card-id="card.id"
    :title="card.title"
    :narrative="''"
    :variant="variant"
    :wide="true"
    :dark="variant === 'slide'"
    tone="foil"
    :hide-chrome="variant === 'slide' ? true : immersive"
    :active="isActive"
  >
    <template #narrative>
      <div
        class="mt-3 wrapped-body text-sm sm:text-base leading-relaxed max-w-3xl"
        :class="variant === 'slide' ? 'text-[#FFFFFF73]' : 'text-[#7F7F7F]'"
      >
        <p class="whitespace-normal">
          <template v-for="(seg, idx) in narrativeSegments" :key="`n-${idx}`">
            <img
              v-if="seg.type === 'emoji'"
              :src="seg.src"
              class="inline-block align-[-0.18em] rounded-[3px] object-contain"
              :style="{ width: `${seg.sizeEm}em`, height: `${seg.sizeEm}em` }"
              :alt="seg.alt || 'emoji'"
            />
            <span v-else-if="seg.type === 'num'" class="wrapped-number font-semibold" :class="accentClass">
              {{ seg.content }}
            </span>
            <span v-else>{{ seg.content }}</span>
          </template>
        </p>
      </div>
    </template>

    <div class="w-full">
      <div
        class="relative w-full"
        :class="variant === 'slide' ? 'h-[88vh] min-h-[520px]' : 'h-[66vh] min-h-[420px] max-h-[760px]'"
      >
        <!-- slide 模式：标题住在舞台里，出现/退场只做淡入淡出，舞台从不改尺寸 -->
        <transition name="hc-head">
          <div v-if="variant === 'slide' && !immersive" class="hc-stage-head">
            <h2 class="wrapped-title text-2xl sm:text-3xl text-[#F3F8F4]">{{ card.title }}</h2>
            <p class="mt-3 wrapped-body text-sm sm:text-base leading-relaxed max-w-3xl text-[#FFFFFF73]">
              <template v-for="(seg, idx) in narrativeSegments" :key="`sh-${idx}`">
                <img
                  v-if="seg.type === 'emoji'"
                  :src="seg.src"
                  class="inline-block align-[-0.18em] rounded-[3px] object-contain"
                  :style="{ width: `${seg.sizeEm}em`, height: `${seg.sizeEm}em` }"
                  :alt="seg.alt || 'emoji'"
                />
                <span v-else-if="seg.type === 'num'" class="wrapped-number font-semibold text-[#4ADE80]">{{ seg.content }}</span>
                <span v-else>{{ seg.content }}</span>
              </template>
            </p>
          </div>
        </transition>
        <EmojiHoloCards
          :card="card"
          :active="isActive"
          :reduced-motion="reducedMotion"
          @immersive="immersive = $event"
        />
      </div>
    </div>
  </WrappedCardShell>
</template>

<script setup>
import { computed, ref } from 'vue'
import EmojiHoloCards from '~/components/wrapped/visualizations/EmojiHoloCards.vue'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { formatInt, useEmojiUniverse } from '~/composables/useEmojiUniverse'
import { parseTextWithEmoji } from '~/lib/wechat-emojis'

const props = defineProps({
  card: { type: Object, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  isActive: { type: Boolean, default: true }
})

const reducedMotion = useReducedMotion()
// 开包/喷洒期间外壳的标题与叙事一起隐去，画面上只剩卡包
const immersive = ref(false)

const {
  resolveEmojiAsset, sentStickerCount, stickerActiveDays, stickerPerActiveDay,
  uniqueTypeCount, wechatEmojis
} = useEmojiUniverse(props)

const accentClass = computed(() => (props.variant === 'slide' ? 'text-[#4ADE80]' : 'text-[#07C160]'))

// ---------- 叙事 ----------
// 卡组已经把明细讲完了，这里只留一句定调 + 关键数字，避免又变成说明书
const splitByNumbers = (text) => {
  const raw = String(text || '')
  if (!raw) return []
  return raw
    .split(/(\d[\d,.]*)/g)
    .filter(Boolean)
    .map((p) => (/^\d[\d,.]*$/.test(p) ? { type: 'num', content: p } : { type: 'text', content: p }))
}

const pushText = (out, text) => {
  for (const seg of parseTextWithEmoji(String(text || ''))) {
    if (seg?.type === 'emoji' && seg.emojiSrc) {
      out.push({ type: 'emoji', src: resolveEmojiAsset(seg.emojiSrc), alt: seg.content || 'emoji', sizeEm: 1.12 })
      continue
    }
    out.push(...splitByNumbers(seg?.content || ''))
  }
}

const perDayText = computed(() => {
  const v = Number(stickerPerActiveDay.value) || 0
  return v >= 10 ? v.toFixed(0) : v.toFixed(1)
})

const narrativeSegments = computed(() => {
  const out = []
  if (sentStickerCount.value <= 0 && uniqueTypeCount.value <= 0) {
    pushText(out, '这一年你几乎没用表情说过话。')
    return out
  }

  pushText(
    out,
    `这一年你甩出 ${formatInt(sentStickerCount.value)} 张表情包，攒下 ${formatInt(uniqueTypeCount.value)} 种表情`
  )
  if (stickerActiveDays.value > 0) {
    pushText(out, `，${formatInt(stickerActiveDays.value)} 个日子里日均 ${perDayText.value} 张`)
  }
  const topWx = wechatEmojis.value[0]
  if (topWx?.src) {
    pushText(out, '，小黄脸里 ')
    out.push({ type: 'emoji', src: topWx.src, alt: topWx.label, sizeEm: 1.16 })
    pushText(out, ` 按了 ${formatInt(topWx.count)} 次`)
  }
  pushText(out, '。')
  return out
})
</script>

<style scoped>
/* 舞台内标题：浮在表情墙预留的顶部空带上 */
.hc-stage-head {
  position: absolute;
  top: 4px;
  left: 10px;
  right: 10px;
  z-index: 30;
  pointer-events: none;
}

.hc-head-enter-active,
.hc-head-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.hc-head-enter-from,
.hc-head-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
