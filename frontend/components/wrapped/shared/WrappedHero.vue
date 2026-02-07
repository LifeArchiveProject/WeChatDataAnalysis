<template>
  <div :class="rootClass">
    <div v-if="variant !== 'slide'" class="absolute inset-0 pointer-events-none">
      <div class="absolute -top-24 -left-24 w-80 h-80 bg-[#07C160] opacity-[0.08] rounded-full blur-3xl"></div>
      <div class="absolute -top-20 -right-20 w-96 h-96 bg-[#F2AA00] opacity-[0.07] rounded-full blur-3xl"></div>
      <div class="absolute -bottom-24 left-40 w-96 h-96 bg-[#10AEEF] opacity-[0.07] rounded-full blur-3xl"></div>
      <div class="absolute inset-0 bg-[linear-gradient(rgba(7,193,96,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(7,193,96,0.05)_1px,transparent_1px)] bg-[size:52px_52px] opacity-[0.35]"></div>
    </div>

    <div :class="innerClass">
      <template v-if="variant === 'slide'">
        <!-- Win98：封面也做成一个“窗口” -->
        <div v-if="isWin98" class="window h-full w-full flex flex-col overflow-hidden">
          <div class="title-bar">
            <div class="title-bar-text">
              <img class="title-bar-icon" src="/assets/images/windows-0.png" alt="" aria-hidden="true" />
              <span>WECHAT WRAPPED</span>
            </div>
            <div class="title-bar-controls" aria-hidden="true">
              <button type="button" aria-label="Minimize" tabindex="-1"></button>
              <button type="button" aria-label="Maximize" tabindex="-1"></button>
              <button type="button" aria-label="Close" tabindex="-1"></button>
            </div>
          </div>

          <div class="window-body flex-1 overflow-hidden">
            <div class="h-full flex flex-col justify-between">
              <div class="flex items-start justify-between gap-4">
                <div class="wrapped-label text-xs text-[#00000080]">
                  WECHAT WRAPPED
                </div>
                <div class="wrapped-body text-xs text-[#00000055]">
                  年度回望
                </div>
              </div>

              <div class="mt-10 sm:mt-14">
                <h1 class="wrapped-title text-3xl sm:text-5xl text-[#000000e6] leading-[1.05]">
                  {{ randomTitle.main }}
                  <span class="block mt-3 win98-hero-highlight">
                    {{ randomTitle.highlight }}
                  </span>
                </h1>

                <div class="mt-7 sm:mt-9 max-w-2xl">
                  <p class="wrapped-body text-base sm:text-lg text-[#00000080]">
                    {{ randomSubtitle }}
                  </p>
                </div>
              </div>

              <div class="pb-1">
                <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[#00000066]">
                  <!-- Intentionally left blank (avoid "feature bullet list" tone on the cover). -->
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 其他主题：保持原样 -->
        <div v-else class="h-full flex flex-col justify-between">
          <div class="flex items-start justify-between gap-4">
            <div class="wrapped-label text-xs text-[#00000080]">
              WECHAT WRAPPED
            </div>
            <div class="wrapped-body text-xs text-[#00000055]">
              年度回望
            </div>
          </div>

          <div class="mt-10 sm:mt-14">
            <h1 class="wrapped-title text-3xl sm:text-5xl text-[#000000e6] leading-[1.05]">
              {{ randomTitle.main }}
              <span class="block mt-3 text-[#07C160]">
                {{ randomTitle.highlight }}
              </span>
            </h1>

            <div class="mt-7 sm:mt-9 max-w-2xl">
              <p class="wrapped-body text-base sm:text-lg text-[#00000080]">
                {{ randomSubtitle }}
              </p>
            </div>
          </div>

          <div class="pb-1">
            <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[#00000066]">
              <!-- Intentionally left blank (avoid "feature bullet list" tone on the cover). -->
            </div>
          </div>
        </div>

        <div
          v-if="previewQuestions.length > 0 && (isGameboy || isModern)"
          class="pointer-events-none absolute bottom-0 right-0 hidden xl:flex items-end"
        >
          <div class="pointer-events-auto relative" :class="previewStageClass">
            <div class="relative" :class="previewViewportClass">
              <template v-if="isGameboy">
              <BitsCardSwap
                :width="previewCardWidth"
                :height="previewCardHeight"
                :delay="previewSwapDelay"
                :card-count="previewQuestions.length"
                :card-distance="previewCardDistance"
                :vertical-distance="previewVerticalDistance"
                :skew-amount="4"
                easing="elastic"
                :pause-on-hover="true"
              >
                <template
                  v-for="(previewItem, previewIndex) in previewQuestions"
                  :key="`preview-${previewItem.order}-${previewIndex}`"
                  v-slot:[`card-${previewIndex}`]
                >
                  <WrappedCardShell
                    :card-id="previewItem.order"
                    :title="previewItem.title"
                    variant="panel"
                    class="h-full w-full"
                  >
                    <div
                      class="flex h-[168px] items-center justify-center rounded-xl border border-dashed px-5"
                      :class="previewQuestionPanelClass"
                    >
                      <p class="wrapped-body text-lg leading-relaxed text-center" :class="previewQuestionClass">
                        {{ previewItem.question }}
                      </p>
                    </div>
                  </WrappedCardShell>
                </template>
              </BitsCardSwap>
              </template>

              <template v-else>
                <BitsGridMotion
                  :items="modernPreviewItems"
                  gradient-color="rgba(7, 193, 96, 0.24)"
                  :row-count="7"
                  :column-count="8"
                  :scroll-speed="42"
                  :base-offset-x="46"
                >
                  <template #item="{ item }">
                    <WrappedCardShell
                      :card-id="Number(item?.order || 0)"
                      :title="String(item?.title || '年度卡片')"
                      variant="panel"
                      class="h-full w-full preview-grid-shell"
                    >
                      <div class="preview-grid-body">
                        <div class="preview-grid-summary">
                          {{ String(item?.summary || '年度线索') }}
                        </div>
                        <p class="preview-grid-question">
                          {{ String(item?.question || '这一页会揭晓你的聊天答案。') }}
                        </p>
                        <div class="preview-grid-lines" aria-hidden="true">
                          <span></span>
                          <span></span>
                        </div>
                      </div>
                    </WrappedCardShell>
                  </template>
                </BitsGridMotion>
              </template>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="flex items-start justify-between gap-4">
          <div class="wrapped-label text-xs text-[#00000080]">
            WECHAT WRAPPED
          </div>
          <!-- 年份放到右上角（分享视图不包含账号信息） -->
          <span
            class="wrapped-label inline-flex items-center px-3 py-1 rounded-full text-xs bg-[#00000008] text-[#00000099] border border-[#00000010]"
          >
            {{ yearText }}
          </span>
        </div>

        <div class="mt-5 sm:mt-7 flex flex-col gap-2">
          <h1 class="wrapped-title text-3xl sm:text-4xl text-[#000000e6] leading-tight">
            聊天年度总结
          </h1>
          <p class="wrapped-body text-sm sm:text-base text-[#7F7F7F] max-w-2xl">
            从时间里回看你的聊天节奏。第一张卡：年度赛博作息表（24H x 7Days）。
          </p>
        </div>

        <!-- Badges intentionally removed: keep the hero more human and less "feature list". -->
      </template>
    </div>
  </div>
</template>

<script setup>
// 50 个主标题（主句 + 高亮句）
const TITLES = [
  { main: '把这一年的聊天', highlight: '轻轻翻一翻' },
  { main: '这一年', highlight: '谁陪你说了最多的话' },
  { main: '那些深夜的消息', highlight: '都去哪儿了' },
  { main: '一年的对话', highlight: '值得被温柔记住' },
  { main: '你的聊天记录里', highlight: '藏着这一年' },
  { main: '有些人', highlight: '一直在消息列表里陪着你' },
  { main: '翻开这一年的', highlight: '对话框' },
  { main: '这一年的问候', highlight: '都在这里了' },
  { main: '一年又一年', highlight: '聊天框里的人还在吗' },
  { main: '回头看看', highlight: '这一年你和谁聊得最多' },
  { main: '你今年说得最多的', highlight: '那个人是谁' },
  { main: '这一年', highlight: '你在深夜回复过谁' },
  { main: '你的消息', highlight: '都发给了谁' },
  { main: '谁在等你的消息', highlight: '你又在等谁的' },
  { main: '你有多久', highlight: '没和 TA 聊天了' },
  { main: '那个秒回你的人', highlight: '还在吗' },
  { main: '你置顶的人', highlight: '这一年变过吗' },
  { main: '最后一条消息', highlight: '是你发的还是 TA 发的' },
  { main: '你的「在吗」', highlight: '都发给了谁' },
  { main: '有没有一个人', highlight: '你想聊却没聊' },
  { main: '对话框里的', highlight: '四季' },
  { main: '字里行间', highlight: '这一年' },
  { main: '消息如潮水', highlight: '来了又退' },
  { main: '屏幕那头', highlight: '有人亮着灯' },
  { main: '打字的手指', highlight: '记得这一年' },
  { main: '时间会走', highlight: '对话会留下来' },
  { main: '每一条消息', highlight: '都是一次想起' },
  { main: '文字落下的地方', highlight: '有人在等' },
  { main: '那些发出去的字', highlight: '都有回响吗' },
  { main: '对话框亮起的', highlight: '瞬间' },
  { main: '这一年的', highlight: '「在吗」和「晚安」' },
  { main: '聊着聊着', highlight: '一年就过去了' },
  { main: '发出去的消息', highlight: '收到的回复' },
  { main: '那些秒回你的人', highlight: '和你秒回的人' },
  { main: '置顶的人', highlight: '还是那几个吗' },
  { main: '深夜的消息', highlight: '清晨的问候' },
  { main: '群聊里的热闹', highlight: '私聊里的安静' },
  { main: '表情包发了多少', highlight: '真心话说了几句' },
  { main: '已读不回的', highlight: '和秒回的' },
  { main: '消息免打扰的', highlight: '和置顶的' },
  { main: '总有人', highlight: '在消息那头' },
  { main: '每条消息背后', highlight: '都有一个想你的人' },
  { main: '感谢这一年', highlight: '愿意听你说话的人' },
  { main: '有人找你聊天', highlight: '是件幸运的事' },
  { main: '被回复的感觉', highlight: '叫做被在乎' },
  { main: '有些陪伴', highlight: '藏在对话框里' },
  { main: '谢谢那些', highlight: '愿意等你回复的人' },
  { main: '聊天这件小事', highlight: '其实是大事' },
  { main: '能说话的人', highlight: '都是重要的人' },
  { main: '这一年', highlight: '谢谢你们陪我聊天' },
]

// 50 个副标题
const SUBTITLES = [
  '有些问候写在对话框里，有些陪伴藏在深夜里。',
  '有些陪伴不说出口，但聊天记录都记得。',
  '凌晨三点的消息、周末的闲聊、节日的祝福——都在这里。',
  '一年的对话，浓缩成几张卡片，轻轻回看。',
  '有些人聊着聊着就淡了，有些人聊着聊着就近了。',
  '消息可以删除，但陪伴的时间删不掉。',
  '那些打出来又删掉的字，也算说过了。',
  '每一次「在吗」，都是一次想念。',
  '深夜的对话，往往最真。',
  '感谢每一个愿意听你说话的人。',
  '一年的时间，几张卡片，一些数字，一点回忆。',
  '深夜、清晨、周末、假期——你的聊天节奏，藏着生活的样子。',
  '数字不会说谎，时间不会忘记。',
  '365 天的对话，整理成几个瞬间。',
  '时间知道你和谁聊得最多。',
  '从时间维度，回看你的聊天节奏。',
  '把一年的对话，整理成可以回望的样子。',
  '时间会告诉你，谁一直都在。',
  '这一年的时间，都花在了谁身上。',
  '日历翻过去了，对话还留着。',
  '不读内容，只看时间。让数字告诉你，谁一直都在。',
  '我们只整理时间，不窥探秘密。这是属于你的一年。',
  '不翻聊天记录，只看时间留下的痕迹。',
  '这不是监控，是回望。这不是窥探，是整理。',
  '我们只看时间，不看内容。你的秘密，依然是秘密。',
  '不读取内容，只呈现时间的痕迹。',
  '你的对话内容我们不碰，只帮你数数时间。',
  '隐私是你的，回忆也是你的。',
  '内容属于你，我们只借用时间。',
  '安全地回望，温柔地整理。',
  '从时间里回看你的聊天节奏。',
  '一些数字，一点回忆。',
  '简单整理，安静回看。',
  '不多说，你自己看。',
  '数字背后，是你的生活。',
  '几张卡片，一年时光。',
  '安静地看看这一年。',
  '让数据说话。',
  '你的一年，你的节奏。',
  '回望，不打扰。',
  '早安、晚安、在吗、好的——这些小词，撑起了一整年。',
  '工作日的忙碌，周末的闲聊，都在这里了。',
  '有些群天天响，有些人很少聊，但都是生活的一部分。',
  '秒回的、已读不回的、消息免打扰的——都是你的选择。',
  '置顶的那几个人，大概就是最重要的人吧。',
  '表情包、语音、文字——你更喜欢哪种聊天方式？',
  '深夜还在聊的，大概都是真朋友。',
  '节日的群发祝福，和单独发的那条，不一样。',
  '有些对话很长，有些只有一个表情包，但都算聊过。',
  '聊天记录里，藏着你这一年的喜怒哀乐。',
]

// 随机选择 - 使用 useState 确保 SSR/CSR 一致，避免 hydration mismatch
const titleIndex = useState('wrapped-title-index', () => Math.floor(Math.random() * TITLES.length))
const subtitleIndex = useState('wrapped-subtitle-index', () => Math.floor(Math.random() * SUBTITLES.length))
const randomTitle = computed(() => TITLES[titleIndex.value])
const randomSubtitle = computed(() => SUBTITLES[subtitleIndex.value])

const PREVIEW_BY_KIND = {
  'global/overview': {
    summary: '年度全景',
    question: '这一年你最常把消息发给谁？'
  },
  'time/weekday_hour_heatmap': {
    summary: '聊天作息',
    question: '你是早八型还是夜猫子型聊天选手？'
  },
  'text/message_chars': {
    summary: '表达强度',
    question: '你这一年打出的字，能拼成几段故事？'
  },
  'chat/reply_speed': {
    summary: '回复速度',
    question: '谁是你愿意秒回的那个人？'
  }
}

const PREVIEW_FALLBACK_SUMMARY = '年度线索'
const PREVIEW_FALLBACK_QUESTION = '这一页会揭晓你的哪段聊天答案？'
const PREVIEW_BOOTSTRAP_ITEMS = [
  { summary: '年度全景', question: '这一年你最常把消息发给谁？' },
  { summary: '聊天作息', question: '你是「早八人」还是「夜猫子」？' },
  { summary: '表达强度', question: '你这一年打了多少字？' },
  { summary: '回复速度', question: '谁是你愿意秒回的那个人？' }
]

const resolvePreviewMeta = (kind, idx) => {
  const key = String(kind || '').trim()
  if (PREVIEW_BY_KIND[key]) return PREVIEW_BY_KIND[key]
  return {
    summary: PREVIEW_FALLBACK_SUMMARY,
    question: idx % 2 === 0
      ? '这一页会揭晓你聊天里的哪种习惯？'
      : '你猜这页的答案会指向谁和哪段时光？'
  }
}

const props = defineProps({
  year: { type: Number, required: true },
  variant: { type: String, default: 'panel' }, // 'panel' | 'slide'
  cardManifests: { type: Array, default: () => [] }
})

const { theme } = useWrappedTheme()
const isWin98 = computed(() => theme.value === 'win98')
const isGameboy = computed(() => theme.value === 'gameboy')
const isModern = computed(() => theme.value === 'off')

const previewQuestions = computed(() => {
  const manifests = Array.isArray(props.cardManifests) ? props.cardManifests : []
  if (!manifests.length) {
    return Array.from({ length: 8 }, (_, idx) => {
      const fallback = PREVIEW_BOOTSTRAP_ITEMS[idx % PREVIEW_BOOTSTRAP_ITEMS.length]
      return {
        order: idx + 1,
        title: `第 ${idx + 1} 张卡片`,
        summary: fallback.summary,
        question: fallback.question
      }
    })
  }

  return manifests.map((item, idx) => {
    const meta = resolvePreviewMeta(item?.kind, idx)
    return {
      order: idx + 1,
      title: String(item?.title || `第 ${idx + 1} 张卡片`),
      summary: meta.summary,
      question: meta.question
    }
  })
})

const previewSwapDelay = 4200
const previewCardWidth = 420
const previewCardHeight = 280

const modernPreviewItems = computed(() => {
  if (!previewQuestions.value.length) return []
  return previewQuestions.value.map((item) => ({
    order: item.order,
    title: item.title,
    summary: item.summary,
    question: item.question
  }))
})

const previewStageClass = computed(() => (
  isGameboy.value
    ? 'w-[500px] h-[360px] translate-x-24 -translate-y-8'
    : 'w-[620px] h-[420px] translate-x-32 -translate-y-10'
))

const previewViewportClass = computed(() => (
  isGameboy.value
    ? 'h-[340px] w-[460px]'
    : 'h-[390px] w-[580px]'
))

const previewCardDistance = computed(() => {
  const total = previewQuestions.value.length
  return total >= 9 ? 9 : total >= 7 ? 11 : total >= 5 ? 13 : 18
})

const previewVerticalDistance = computed(() => {
  const total = previewQuestions.value.length
  return total >= 9 ? 10 : total >= 7 ? 11 : total >= 5 ? 14 : 18
})

const previewQuestionClass = computed(() => {
  if (isWin98.value) return 'text-[#111111]'
  return 'text-[#1F2937]'
})

const previewQuestionPanelClass = computed(() => {
  if (isWin98.value) return 'border-[#B7B7B7] bg-[#FFFFFF]'
  return 'border-[#07C160]/30 bg-[#F7FFFB]'
})

const yearText = computed(() => `${props.year}年`)

const rootClass = computed(() => {
  const base = 'relative overflow-hidden'
  return props.variant === 'slide'
    ? `${base} h-full w-full`
    : `${base} rounded-2xl border border-[#EDEDED] bg-white`
})

const innerClass = computed(() => {
  if (props.variant !== 'slide') return 'relative px-6 py-7 sm:px-8 sm:py-9'
  if (isWin98.value) return 'relative h-full max-w-5xl mx-auto px-6 pt-2 pb-4 sm:px-8 sm:pt-3 sm:pb-6'
  return 'relative h-full max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12'
})
</script>

<style scoped>
/* Win98：封面标题的高亮句做成“选中/标题栏”感觉 */
.win98-hero-highlight {
  display: inline-block;
  padding: 2px 8px;
  background: #000080;
  color: #ffffff;
}

.preview-grid-shell {
  border-radius: 12px;
  box-shadow: 0 10px 24px rgba(7, 193, 96, 0.14);
  background: #f3fff8 !important;
  border-color: rgba(7, 193, 96, 0.24) !important;
}

.preview-grid-shell :deep(.wrapped-title) {
  font-size: 16px;
  line-height: 1.25;
}

.preview-grid-body {
  height: 96px;
  border-radius: 10px;
  border: 1px solid rgba(7, 193, 96, 0.2);
  background: rgba(243, 255, 248, 0.88);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 10px 12px;
}

.preview-grid-summary {
  font-size: 11px;
  line-height: 1;
  letter-spacing: 0.04em;
  color: #07c160;
  font-weight: 700;
}

.preview-grid-question {
  margin-top: 6px;
  color: #1f2937;
  font-size: 13px;
  line-height: 1.35;
  font-weight: 600;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.preview-grid-lines {
  margin-top: 6px;
  display: grid;
  gap: 5px;
}

.preview-grid-lines span {
  display: block;
  height: 5px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(7, 193, 96, 0.18), rgba(7, 193, 96, 0.08));
}

.preview-grid-lines span:last-child {
  width: 68%;
}
</style>
