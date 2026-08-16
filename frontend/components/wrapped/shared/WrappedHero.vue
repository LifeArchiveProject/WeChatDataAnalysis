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
        <div class="h-full flex flex-col justify-between hero-slide-col">
          <div class="flex items-start justify-between gap-4">
          </div>

          <div class="mt-10 sm:mt-14 hero-title-block">
            <h1 class="wrapped-title text-3xl sm:text-5xl text-[#000000e6] leading-[1.05] hero-title">
              {{ randomTitle.main }}
              <span class="block mt-3 text-[#07C160]">
                {{ randomTitle.highlight }}
              </span>
            </h1>

            <div class="mt-7 sm:mt-9 max-w-2xl hero-sub-wrap">
              <p class="wrapped-body text-base sm:text-lg text-[#00000080] hero-sub">
                {{ randomSubtitle }}
              </p>
            </div>
          </div>

          <div class="pb-1 hero-foot">
            <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[#00000066]">
              <!-- Intentionally left blank (avoid "feature bullet list" tone on the cover). -->
            </div>
          </div>
        </div>

        <div
          v-if="previewQuestions.length > 0"
          class="pointer-events-none absolute bottom-0 right-0 hidden xl:flex items-end hero-preview-wrap"
        >
          <div class="pointer-events-auto relative" :class="previewStageClass">
            <div class="relative" :class="previewViewportClass">
              <BitsGridMotion
                :items="modernPreviewItems"
                gradient-color="rgba(7, 193, 96, 0.24)"
                :row-count="previewRowCount"
                :column-count="previewColumnCount"
                :item-width="previewItemWidth"
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
import { useWrappedStage } from '~/composables/useWrappedStage'

const stage = useWrappedStage()

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
  },
  'chat/monthly_best_friends_wall': {
    summary: '月度好友墙',
    question: '每个月谁是你最有默契的聊天搭子？'
  },
  'emoji/annual_universe': {
    summary: '梗图年鉴',
    question: '你这一年最常丢出的表情包是哪张？'
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
  cardManifests: { type: Array, default: () => [] },
  // deck 契约：当前 slide 是否处于激活态（封面为 slide 0）
  isActive: { type: Boolean, default: true }
})

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
  'w-[620px] h-[420px] translate-x-32 -translate-y-24 hero-preview-stage'
))

const previewViewportClass = computed(() => (
  'h-[390px] w-[580px] hero-preview-viewport'
))

// 预告网格的行列数按画幅重排：竖幅里预告带更窄更高，于是「列数减少、行数增加」。
// 卡片本体尺寸（300×210）在所有画幅下不变——这里改的只是网格的流向，不是构件大小。
// wide/landscape 必须原样返回 7 / 8，16:9 逐像素零回归。
//
// 竖幅/方幅里卡片本体还要**放大**（300×210 → 460×344，见样式段），
// 于是这里同时给出 itemWidth：它是跑马灯的循环步进依据，必须跟卡宽一致，否则循环会错位。
//
// 列数还兼着两件事，取值不能随手拍：
//  1. 跑马灯循环周期 = 列数 ×（卡宽+12），必须盖住旋转 -15° 后的视口投影宽度，
//     否则循环到末尾时右侧会露白；
//  2. 相邻行的取卡步进 = 2×列数（对预告条数取模），步进和条数同余会让每行都从同一张开始，
//     一屏只剩两三种预告。当前 manifest 是 8 张，5/6 的步进（10/12）刚好把 8 张摊开；
//     4 列（步进 8）会让每行完全重复，绝对不能取。
// 行数按「卡更高之后仍要盖满旋转视口」重算：竖幅 460×344 卡的纵向步进是 356px。
const PREVIEW_GRID_BY_TIER = {
  wide: { rows: 7, columns: 8, itemWidth: 300 },
  landscape: { rows: 7, columns: 8, itemWidth: 300 },
  square: { rows: 5, columns: 5, itemWidth: 460 },
  portrait: { rows: 6, columns: 5, itemWidth: 460 },
  tall: { rows: 6, columns: 5, itemWidth: 460 }
}

const previewGrid = computed(() => (
  PREVIEW_GRID_BY_TIER[stage.tier.value] || PREVIEW_GRID_BY_TIER.wide
))

const previewRowCount = computed(() => previewGrid.value.rows)
const previewColumnCount = computed(() => previewGrid.value.columns)
const previewItemWidth = computed(() => previewGrid.value.itemWidth)

const yearText = computed(() => `${props.year}年`)

const rootClass = computed(() => {
  const base = 'relative overflow-hidden'
  return props.variant === 'slide'
    ? `${base} h-full w-full`
    : `${base} rounded-2xl border border-[#EDEDED] bg-white`
})

const innerClass = computed(() => {
  if (props.variant !== 'slide') return 'relative px-6 py-7 sm:px-8 sm:py-9'
  return 'relative h-full max-w-5xl mx-auto px-6 py-10 sm:px-8 sm:py-12 hero-slide-inner'
})
</script>

<style scoped>
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

/* ==========================================================================
   画幅重排（只写在 tier 前缀下；16:9 / 跟随窗口 = tier "wide" 一个像素都不动）

   横屏构图是「左中大标题 + 右下角倾斜预告面板」。竖幅里预告面板会被推出画幅右侧，
   6 条预告文本整体丢失，同时画面上方空一大片。这里把构图改成纵向编辑排版：
   标题组上移到上中部，预告网格铺成下半屏的整幅横向流（列数减少、行数增加）。
   字体层级、卡面样式、-15° 倾斜一律沿用横屏那套，只改位置与流向。
   ========================================================================== */

/* 1) 把随「浏览器窗口宽度」跳变的 sm: 断点值钉成设计常量。
   舞台是设计像素恒定盒，构件尺寸不该随窗口大小变——窄窗口下标题会掉到 30px、
   内边距掉到 24/40，下面的排布计算就全不成立了。取值 = 各自在 ≥640px 下的计算值。 */
[data-frame-tier="landscape"] .hero-slide-inner,
[data-frame-tier="square"] .hero-slide-inner,
[data-frame-tier="portrait"] .hero-slide-inner,
[data-frame-tier="tall"] .hero-slide-inner {
  padding-left: 32px;
  padding-right: 32px;
  padding-top: 48px;
  padding-bottom: 48px;
}

[data-frame-tier="landscape"] .hero-title {
  font-size: 48px;
}

[data-frame-tier="landscape"] .hero-sub {
  font-size: 18px;
  line-height: 28px;
}

[data-frame-tier="landscape"] .hero-sub-wrap,
[data-frame-tier="square"] .hero-sub-wrap,
[data-frame-tier="portrait"] .hero-sub-wrap,
[data-frame-tier="tall"] .hero-sub-wrap {
  margin-top: 36px;
}

/* 2) 预告网格在非 wide 画幅下一律参与排版。
   原来的 `hidden xl:flex` 挂的是浏览器窗口宽度：固定画幅时舞台会整体缩放，
   窗口 <1280px 就把整块预告网格 display:none 掉，6 条预告文本直接消失。 */
/* 16:9 也是「框定画幅」的一种：舞台宽恒为 1600，窗口再窄也不该把预告网格整块隐掉。
   只有「跟随窗口」（舞台=窗口）时 xl: 断点才是对的判断依据，那一档保持原样。 */
.wr-stage--framed .hero-preview-wrap,
[data-frame-tier="landscape"] .hero-preview-wrap,
[data-frame-tier="square"] .hero-preview-wrap,
[data-frame-tier="portrait"] .hero-preview-wrap,
[data-frame-tier="tall"] .hero-preview-wrap {
  display: flex;
}

/* 3) 竖幅 / 方幅：标题组顶部对齐并顶到画幅上沿，让出整个下半屏给预告带。
   以前把标题压到上中部（tall 是 margin-top 232），上面白着一大片、下面预告带也够不到底，
   文字实际只占画幅中段 75%。现在标题贴顶、预告带贴底，两头都吃满。 */
[data-frame-tier="square"] .hero-slide-col,
[data-frame-tier="portrait"] .hero-slide-col,
[data-frame-tier="tall"] .hero-slide-col {
  justify-content: flex-start;
}

/* 标题落点：上一轮为了提占幅把 margin-top 从 232 一刀砍到 36，结果标题贴到画幅顶上（距顶仅 84px / 5%）。
   改成按画幅高度约 12% 落位——标题仍在上三分之一（封面该有的位置），但不再顶天。
   数值与下面 .hero-preview-stage 的高度是一组：标题最坏三行时的底边必须留在预告带顶边之上。 */
[data-frame-tier="square"] .hero-title-block {
  margin-top: 96px;
}

[data-frame-tier="portrait"] .hero-title-block {
  margin-top: 118px;
}

[data-frame-tier="tall"] .hero-title-block {
  margin-top: 144px;
}

/* 3.1) 标题与副标题按画幅放大（不是缩放内容，是重新定字号）。
   取值卡在「最长的一句刚好不多折一行」上：
   tall 版心 836，88px 下每行 9.5 字，最长高亮句（11 字）折 2 行，全句最多 3 行；
   portrait 版心 976/1010、square 版心 1136，字更大反而每行装得下 11 字，最多 2 行。
   全是绝对 px，不挂高度轴单位，舞台变高不会再把字顶大。 */
[data-frame-tier="tall"] .hero-title {
  font-size: 88px;
}

[data-frame-tier="portrait"] .hero-title {
  font-size: 84px;
}

[data-frame-tier="square"] .hero-title {
  font-size: 80px;
}

[data-frame-tier="tall"] .hero-sub {
  font-size: 32px;
  line-height: 50px;
}

[data-frame-tier="portrait"] .hero-sub,
[data-frame-tier="square"] .hero-sub {
  font-size: 30px;
  line-height: 48px;
}

/* max-w-2xl（672）是横屏版心的一半，竖幅里会把 30px 的副标题挤成三行。放开到整幅版心。 */
[data-frame-tier="square"] .hero-sub-wrap,
[data-frame-tier="portrait"] .hero-sub-wrap,
[data-frame-tier="tall"] .hero-sub-wrap {
  max-width: none;
  margin-top: 40px;
}

/* 4) 预告网格：从「右下角浮块」改成「下半屏整幅带」。
   带子铺满内容列宽（1:1/3:4/4:5 = 1024，9:16 = 900），底部各留出与横屏同量级的余白，
   保证倾斜卡面与 6 条预告文本全部落在画幅内。 */
/* left/right 的负值 = 把版心（max-w-5xl，1024）撑回整幅画幅宽：
   1:1 是 1200 宽，版心只有 1024，预告带两侧各空 88px 的白，画面直接少掉一成。
   --svw 是舞台版的 1vw（= 设计宽/100），所以这条对任意画幅都成立：
   9:16（900）算出来是 0，3:4（1040）是 -8，1:1（1200）是 -88。标题仍留在版心里。 */
[data-frame-tier="square"] .hero-preview-wrap,
[data-frame-tier="portrait"] .hero-preview-wrap,
[data-frame-tier="tall"] .hero-preview-wrap {
  left: calc((100% - var(--svw, 16px) * 100) / 2);
  right: calc((100% - var(--svw, 16px) * 100) / 2);
  align-items: stretch;
}

[data-frame-tier="square"] .hero-preview-wrap,
[data-frame-tier="portrait"] .hero-preview-wrap,
[data-frame-tier="tall"] .hero-preview-wrap {
  bottom: 52px;
}

/* transform:none 抵掉横屏的 translate-x-32 / -translate-y-24（Tailwind 3 写在 transform 上） */
[data-frame-tier="square"] .hero-preview-stage,
[data-frame-tier="portrait"] .hero-preview-stage,
[data-frame-tier="tall"] .hero-preview-stage {
  width: 100%;
  transform: none;
}

/* 带高 = 画幅高 - 标题组占掉的高度 - 底部 52。
   标题组最坏情况（tall：3 行标题 + 2 行副标题）落到 515，square/portrait 落到 ~400，
   带子顶边分别取 548 / 430(4:5) / 436，留出余量，任何一条随机文案都不会压到卡面。 */
[data-frame-tier="square"] .hero-preview-stage {
  height: 660px;
}

[data-frame-tier="portrait"] .hero-preview-stage {
  height: 782px;
}

[data-frame-tier="tall"] .hero-preview-stage {
  height: 880px;
}

[data-frame-tier="square"] .hero-preview-viewport,
[data-frame-tier="portrait"] .hero-preview-viewport,
[data-frame-tier="tall"] .hero-preview-viewport {
  width: 100%;
  height: 100%;
}

/* 5) 预告卡本体在竖幅/方幅里整体放大：300×210 → 460×344。
   卡面文字原来是 16/13/11px，在 900 宽的舞台上换算过去只有指甲盖大，用户截图里
   抱怨的就是这一片。放大卡片是为了把字号抬到 26/24/18，而不是把字塞进原来的小卡。
   注意：这里改的是「本组件用到的那一份 BitsGridMotion 实例」，共享组件本身没动；
   itemWidth 同步由 PREVIEW_GRID_BY_TIER 传进去，跑马灯循环步进才对得上。 */
[data-frame-tier="square"] .hero-preview-viewport :deep(.bits-grid-motion-cell),
[data-frame-tier="portrait"] .hero-preview-viewport :deep(.bits-grid-motion-cell),
[data-frame-tier="tall"] .hero-preview-viewport :deep(.bits-grid-motion-cell) {
  min-width: 460px;
  height: 344px;
}

[data-frame-tier="square"] .preview-grid-shell :deep(.wrapped-title),
[data-frame-tier="portrait"] .preview-grid-shell :deep(.wrapped-title),
[data-frame-tier="tall"] .preview-grid-shell :deep(.wrapped-title) {
  font-size: 26px;
  line-height: 1.24;
}

[data-frame-tier="square"] .preview-grid-body,
[data-frame-tier="portrait"] .preview-grid-body,
[data-frame-tier="tall"] .preview-grid-body {
  height: 176px;
  border-radius: 14px;
  padding: 16px 18px;
}

[data-frame-tier="square"] .preview-grid-summary,
[data-frame-tier="portrait"] .preview-grid-summary,
[data-frame-tier="tall"] .preview-grid-summary {
  font-size: 18px;
}

/* 24px × 版心 376 = 每行 15.6 字，最长的一条预告问句 17 字正好两行，
   line-clamp:2 不会真的把字切掉。 */
[data-frame-tier="square"] .preview-grid-question,
[data-frame-tier="portrait"] .preview-grid-question,
[data-frame-tier="tall"] .preview-grid-question {
  margin-top: 10px;
  font-size: 24px;
  line-height: 1.35;
}

[data-frame-tier="square"] .preview-grid-lines,
[data-frame-tier="portrait"] .preview-grid-lines,
[data-frame-tier="tall"] .preview-grid-lines {
  margin-top: 10px;
  gap: 7px;
}

[data-frame-tier="square"] .preview-grid-lines span,
[data-frame-tier="portrait"] .preview-grid-lines span,
[data-frame-tier="tall"] .preview-grid-lines span {
  height: 8px;
}
</style>
