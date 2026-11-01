<template>
  <main
    ref="pageRef"
    class="first-use-page theme-scope theme-page"
    :class="{ 'annotations-ready': annotationsReady }"
    aria-labelledby="first-use-title"
  >
    <div class="first-use-layout">
      <header class="first-use-header">
        <div class="first-use-brand">
          <img src="/logo.png" alt="微信数据分析工具" class="first-use-logo" />
          <div class="first-use-heading-copy">
            <p class="first-use-eyebrow">开始使用前</p>
            <h1 id="first-use-title" ref="titleRef" tabindex="-1">使用须知与免责声明</h1>
          </div>
        </div>

        <div class="first-use-summary" aria-label="内容摘要">
          <span><strong>{{ documents[0].sections.length }}</strong> 条别踩坑</span>
          <span><strong>{{ documents[1].sections.length }}</strong> 条边界说明</span>
        </div>
      </header>

      <section class="first-use-documents" aria-label="完整使用须知与免责声明">
        <article
          v-for="(document, documentIndex) in documents"
          :key="document.id"
          class="first-use-document"
          :aria-labelledby="`first-use-${document.id}`"
        >
          <header class="first-use-document-header">
            <span class="first-use-document-index" aria-hidden="true">0{{ documentIndex + 1 }}</span>
            <div>
              <p>{{ document.shortTitle }}</p>
              <h2 :id="`first-use-${document.id}`">{{ document.title }}</h2>
              <p v-if="document.description" class="first-use-document-description">{{ document.description }}</p>
            </div>
          </header>

          <ol class="first-use-sections">
            <li v-for="(section, sectionIndex) in document.sections" :key="section.title">
              <span class="first-use-section-index" aria-hidden="true">{{ sectionIndex + 1 }}</span>
              <div class="first-use-section-copy">
                <h3>
                  <template
                    v-for="(part, partIndex) in section.heading"
                    :key="`${section.title}-${partIndex}`"
                  >
                    <span
                      v-if="part.annotation"
                      class="first-use-annotation"
                      :data-annotation="part.annotation"
                      :data-tone="part.tone"
                    >{{ part.text }}</span>
                    <span v-else>{{ part.text }}</span>
                  </template>
                </h3>
                <p
                  v-for="(paragraph, paragraphIndex) in section.paragraphs"
                  :key="paragraph"
                >
                  <component
                    :is="fragment.strong ? 'strong' : 'span'"
                    v-for="(fragment, fragmentIndex) in segmentParagraph(paragraph, section.emphasis)"
                    :key="`${section.title}-${paragraphIndex}-${fragmentIndex}`"
                    :class="{
                      'first-use-body-keyword': fragment.strong,
                      'first-use-body-marker': fragment.marker
                    }"
                    :data-tone="fragment.tone || undefined"
                  >{{ fragment.text }}</component>
                </p>
              </div>
            </li>
          </ol>

          <p v-if="document.confirmation" class="first-use-confirmation">
            {{ document.confirmation }}
          </p>
        </article>
      </section>

      <footer class="first-use-footer">
        <div class="first-use-footer-status" aria-live="polite">
          <span class="first-use-status-dot" :class="{ ready: canConfirm }" aria-hidden="true"></span>
          <p>{{ canConfirm ? '重点和边界都看完了，确认后开工。' : `请先读完关键内容，${remainingSeconds} 秒后可确认。` }}</p>
        </div>
        <button
          type="button"
          data-testid="first-use-confirm"
          :disabled="!canConfirm"
          @click="confirmAgreement"
        >
          <svg v-if="!canConfirm" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
            <circle cx="12" cy="12" r="9" stroke-width="1.8" />
            <path d="M12 7v5l3 2" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
            <path d="m5 12 4 4L19 6" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" />
          </svg>
          <span>{{ primaryLabel }}</span>
        </button>
      </footer>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  normalizeFirstUseRedirect,
  persistFirstUseAgreementAcceptance
} from '~/lib/first-use-agreement'

const COUNTDOWN_MILLISECONDS = 20_000

const documents = [
  {
    id: 'notice',
    shortTitle: '使用须知',
    title: '开始前请阅读使用须知',
    sections: [
      {
        title: '版本要求',
        heading: [
          { text: '只认 ' },
          { text: '微信 4.x', annotation: 'highlight', tone: 'yellow' },
          { text: '，程序暂不负责考古' }
        ],
        emphasis: [
          { text: '仅支持微信桌面端 4.x 版本', strong: true, marker: true, tone: 'yellow' }
        ],
        paragraphs: ['本项目目前仅支持微信桌面端 4.x 版本。使用较低版本时，请先将微信升级至受支持版本。']
      },
      {
        title: '密钥与账号、设备的关系',
        heading: [
          { text: '密钥有 ' },
          { text: '账号 + 当前设备', annotation: 'circle', tone: 'green' },
          { text: ' 双重户口本' }
        ],
        emphasis: [
          { text: '微信账号和当前设备', strong: true },
          { text: '不能相互替代或混用', strong: true, marker: true, tone: 'coral' }
        ],
        paragraphs: ['数据库密钥同时与微信账号和当前设备相关联。同一账号在不同设备上的密钥通常不同，不能相互替代或混用。']
      },
      {
        title: '登录要求',
        heading: [
          { text: '先登录，' },
          { text: '别让工具隔空算命' }
        ],
        emphasis: [
          { text: '至少在当前设备成功登录一次', strong: true },
          { text: '首次解密该账号前仍至少需要成功登录一次', strong: true }
        ],
        paragraphs: [
          '若账号从未在当前设备登录，本项目无法读取该设备上不存在的历史数据。首次准备数据时，请至少在当前设备成功登录一次；已经完成解密或导入的数据可以离线查看。',
          '即使当前设备上已经存在某个账号的历史数据目录，首次解密该账号前仍至少需要成功登录一次。仅发现历史文件，并不表示已经完成账号识别或具备可用的解密条件。'
        ]
      },
      {
        title: '保持单一微信实例',
        heading: [
          { text: '只开 ' },
          { text: '一个微信', annotation: 'box', tone: 'coral' },
          { text: '，分身先下班' }
        ],
        emphasis: [
          { text: '仅运行并登录一个微信实例', strong: true, marker: true, tone: 'coral' }
        ],
        paragraphs: ['开始检测和获取密钥前，请仅运行并登录一个微信实例。微信多开、切换账号或同时运行多个实例，可能造成进程识别错误、数据来源混淆、密钥获取失败或其他非预期结果。']
      },
      {
        title: 'Windows 密钥获取与安全提醒',
        heading: [
          { text: '内存扫描先上，' },
          { text: 'Hook', annotation: 'circle', tone: 'coral' },
          { text: ' 只当候补' }
        ],
        emphasis: [
          { text: '优先使用 V4 内存扫描', strong: true },
          { text: '才会询问是否改用 Hook', strong: true },
          { text: '本项目不作绝对保证', strong: true, marker: true, tone: 'coral' }
        ],
        paragraphs: [
          'Windows 端会优先使用 V4 内存扫描获取数据库密钥。该方式不执行 Hook，通常不会触发 Hook 相关的微信账号安全提醒；内存扫描失败时，系统才会询问是否改用 Hook。',
          'Hook 获取可能触发微信侧账号安全提醒。现有反馈显示，此类提醒可能延迟出现或集中触达，目前未观察到普遍导致封号的情况；但微信侧策略可能随时调整，本项目不作绝对保证。相关风险取决于微信客户端的检测策略，并非操作系统自身的安全警告。'
        ]
      },
      {
        title: '避免重复获取密钥',
        heading: [
          { text: '能用就别 ' },
          { text: '重复薅密钥', annotation: 'crossed-off', tone: 'coral' }
        ],
        emphasis: [
          { text: '妥善保存并优先复用', strong: true },
          { text: '请勿重复获取', strong: true }
        ],
        paragraphs: ['密钥获取成功后请妥善保存并优先复用。在微信未调整密钥机制、数据格式，且账号与设备环境未发生变化时，密钥通常可以持续使用。现有密钥仍有效时，请勿重复获取，以减少不必要的操作和潜在风险。']
      }
    ]
  },
  {
    id: 'disclaimer',
    shortTitle: '免责声明',
    title: '免责声明与使用确认',
    description: '这部分不吓人，只负责把边界说清楚，免得好奇心临时兼职律师。',
    sections: [
      {
        title: '项目性质',
        heading: [
          { text: '“' },
          { text: '非官方' },
          { text: '”不是谦虚，是事实' }
        ],
        emphasis: [
          { text: '非官方开源工具', strong: true }
        ],
        paragraphs: ['本项目为独立开发的非官方开源工具，与微信、腾讯及其关联主体不存在隶属、授权、合作或认可关系。相关产品名称和商标归其权利人所有。']
      },
      {
        title: '合法使用',
        heading: [
          { text: '本人或 ' },
          { text: '明确授权', annotation: 'highlight', tone: 'yellow' },
          { text: '，才有入场券' }
        ],
        emphasis: [
          { text: '本人合法持有、管理或已经取得明确授权访问的数据', strong: true, marker: true, tone: 'yellow' },
          { text: '遵守适用的法律法规', strong: true }
        ],
        paragraphs: ['本项目仅可用于处理您本人合法持有、管理或已经取得明确授权访问的数据。使用者应遵守适用的法律法规、软件许可协议、平台规则和隐私保护义务。']
      },
      {
        title: '兼容性与运行风险',
        heading: [
          { text: '不保未来兼容，' },
          { text: '软件没有水晶球' }
        ],
        emphasis: [
          { text: '不保证对未来微信版本持续兼容', strong: true, marker: true, tone: 'coral' }
        ],
        paragraphs: ['客户端版本变化、内存扫描、Hook、第三方组件及其他本地处理流程，可能导致账号提醒、功能失效、处理失败、文件异常或其他不可预期结果。本项目不保证对未来微信版本持续兼容。']
      },
      {
        title: '责任范围',
        heading: [
          { text: '风险 ' },
          { text: '由使用者自行承担' },
          { text: '，空气不背锅' }
        ],
        emphasis: [
          { text: '由使用者自行承担', strong: true, marker: true, tone: 'coral' }
        ],
        paragraphs: ['本项目按现状提供，不对功能的准确性、完整性、稳定性或持续可用性作出明示或默示保证。在适用法律允许的范围内，因使用、误用、版本不兼容、操作中断或第三方策略变化产生的损失和后果，由使用者自行承担。']
      }
    ],
    confirmation: '点击确认即表示您已完整阅读、理解并同意以上内容，并自愿继续使用本项目。'
  }
]

const segmentParagraph = (paragraph, emphasis = []) => {
  const source = String(paragraph || '')
  const ranges = emphasis
    .map((item, order) => {
      const start = source.indexOf(item.text)
      return start < 0 ? null : {
        item,
        order,
        start,
        end: start + item.text.length
      }
    })
    .filter(Boolean)
    .sort((left, right) => left.start - right.start || left.order - right.order)

  const fragments = []
  let cursor = 0
  for (const range of ranges) {
    if (range.start < cursor) continue
    if (range.start > cursor) fragments.push({ text: source.slice(cursor, range.start) })
    fragments.push({ ...range.item, text: source.slice(range.start, range.end) })
    cursor = range.end
  }
  if (cursor < source.length) fragments.push({ text: source.slice(cursor) })
  return fragments.length ? fragments : [{ text: source }]
}

const route = useRoute()
const remainingMilliseconds = ref(COUNTDOWN_MILLISECONDS)
const titleRef = ref(null)
const pageRef = ref(null)
const annotationsReady = ref(false)
let countdownTimer = null
let lastTickAt = 0
let annotationsDisposed = false
let roughAnnotations = []

const remainingSeconds = computed(() => Math.ceil(remainingMilliseconds.value / 1000))
const canConfirm = computed(() => remainingMilliseconds.value <= 0)
const primaryLabel = computed(() => {
  if (!canConfirm.value) return `请阅读（${remainingSeconds.value} 秒）`
  return '我已阅读全部内容并同意'
})

const stopCountdown = () => {
  if (countdownTimer !== null) window.clearInterval(countdownTimer)
  countdownTimer = null
}

const updateCountdown = () => {
  const now = window.performance.now()
  if (document.visibilityState === 'visible') {
    remainingMilliseconds.value = Math.max(0, remainingMilliseconds.value - (now - lastTickAt))
  }
  lastTickAt = now
  if (remainingMilliseconds.value <= 0) stopCountdown()
}

const startCountdown = () => {
  stopCountdown()
  remainingMilliseconds.value = COUNTDOWN_MILLISECONDS
  lastTickAt = window.performance.now()
  countdownTimer = window.setInterval(updateCountdown, 200)
}

const handleVisibilityChange = () => {
  lastTickAt = window.performance.now()
}

const removeRoughAnnotations = () => {
  for (const annotation of roughAnnotations) annotation.remove()
  roughAnnotations = []
  annotationsReady.value = false
}

const setupRoughAnnotations = async () => {
  try {
    const { annotate, annotationGroup } = await import('rough-notation')
    await nextTick()
    if (annotationsDisposed || !pageRef.value) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const styles = window.getComputedStyle(pageRef.value)
    const colorFor = (tone) => (
      styles.getPropertyValue(`--first-use-ink-${tone}`).trim() || '#07c160'
    )

    roughAnnotations = Array.from(
      pageRef.value.querySelectorAll('.first-use-annotation')
    ).map((element) => {
      const type = element.dataset.annotation || 'underline'
      const isOutline = type === 'circle' || type === 'box'
      return annotate(element, {
        type,
        color: colorFor(element.dataset.tone || 'green'),
        animate: !reducedMotion,
        animationDuration: 150,
        iterations: isOutline ? 2 : 1,
        multiline: true,
        padding: type === 'highlight' ? [0, 1] : [1, 3]
      })
    })

    annotationGroup(roughAnnotations).show()
    annotationsReady.value = true
  } catch {
    // Bold text and CSS marker strokes remain as the offline-safe fallback.
  }
}

const confirmAgreement = async () => {
  if (!canConfirm.value) return

  persistFirstUseAgreementAcceptance()
  document.documentElement.removeAttribute('data-first-use-route')
  document.documentElement.setAttribute('data-first-use-accepted', 'true')
  await navigateTo(normalizeFirstUseRedirect(route.query.redirect), { replace: true })
}

useHead({ title: '使用须知与免责声明 - 微信数据分析工具' })

onMounted(() => {
  pageRef.value?.setAttribute('data-first-use-mounted', 'true')
  document.addEventListener('visibilitychange', handleVisibilityChange)
  startCountdown()
  titleRef.value?.focus?.()
  void setupRoughAnnotations()
})

onBeforeUnmount(() => {
  pageRef.value?.removeAttribute('data-first-use-mounted')
  annotationsDisposed = true
  removeRoughAnnotations()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopCountdown()
})
</script>

<style scoped>
.first-use-page {
  --first-use-ink-yellow: #efc84a;
  --first-use-ink-green: #0d9f57;
  --first-use-ink-blue: #4776d0;
  --first-use-ink-coral: #db614f;
  box-sizing: border-box;
  height: 100%;
  min-height: 100%;
  overflow: auto;
  padding: clamp(14px, 2.2vh, 24px) clamp(20px, 3.6vw, 52px) clamp(12px, 1.8vh, 20px);
  background:
    radial-gradient(circle at 8% 0%, rgba(7, 193, 96, 0.08), transparent 27%),
    linear-gradient(180deg, #f8faf9 0%, #f1f5f2 100%);
  color: var(--app-text-primary, #191919);
}

.first-use-layout {
  display: grid;
  width: min(1480px, 100%);
  min-height: 100%;
  margin: 0 auto;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: clamp(12px, 1.8vh, 18px);
}

.first-use-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 28px;
  padding-bottom: clamp(10px, 1.5vh, 16px);
  border-bottom: 1px solid var(--app-border, #dfe6e1);
}

.first-use-brand {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 14px;
}

.first-use-logo {
  width: clamp(38px, 4vw, 48px);
  height: clamp(38px, 4vw, 48px);
  flex: 0 0 auto;
  object-fit: contain;
}

.first-use-heading-copy {
  min-width: 0;
}

.first-use-eyebrow {
  margin: 0 0 2px;
  color: var(--app-accent, #07c160);
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.14em;
}

.first-use-heading-copy h1 {
  margin: 0;
  outline: none;
  font-size: clamp(24px, 2.5vw, 32px);
  font-weight: 680;
  line-height: 1.2;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.first-use-summary {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  color: var(--app-text-secondary, #667069);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.first-use-summary span {
  padding: 0 14px;
  white-space: nowrap;
}

.first-use-summary span + span {
  border-left: 1px solid var(--app-border, #dfe6e1);
}

.first-use-summary strong {
  margin-right: 4px;
  color: var(--app-text-primary, #191919);
  font-size: 22px;
  font-weight: 680;
}

.first-use-documents {
  display: grid;
  min-height: 0;
  grid-template-columns: minmax(0, 1.28fr) minmax(0, 0.72fr);
}

.first-use-document {
  min-width: 0;
  padding-right: clamp(18px, 2.3vw, 34px);
}

.first-use-document + .first-use-document {
  padding-right: 0;
  padding-left: clamp(18px, 2.3vw, 34px);
  border-left: 1px solid var(--app-border, #dfe6e1);
}

.first-use-document-header {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  padding-bottom: clamp(7px, 1vh, 11px);
}

.first-use-document-index {
  padding-top: 1px;
  color: var(--app-accent, #07c160);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.first-use-document-header > div > p:first-child {
  margin: 0 0 1px;
  color: var(--app-accent, #07c160);
  font-size: 12.5px;
  font-weight: 650;
  letter-spacing: 0.1em;
}

.first-use-document-header h2 {
  margin: 0;
  font-size: clamp(18px, 1.65vw, 22px);
  font-weight: 650;
  line-height: 1.3;
  letter-spacing: -0.018em;
}

.first-use-document-description {
  margin: 3px 0 0;
  color: var(--app-text-muted, #7b847e);
  font-size: 13.25px;
  line-height: 1.45;
}

.first-use-sections {
  margin: 0;
  padding: 0;
  list-style: none;
}

.first-use-sections li {
  display: grid;
  grid-template-columns: 25px minmax(0, 1fr);
  gap: 9px;
  padding: clamp(5px, 0.85vh, 9px) 0;
  border-top: 1px solid var(--app-border-soft, #e6ebe7);
  break-inside: avoid;
}

.first-use-section-index {
  padding-top: 2px;
  color: #57a678;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}

.first-use-section-copy {
  min-width: 0;
}

.first-use-section-copy h3 {
  margin: 0 0 2px;
  font-family: "Segoe Print", "KaiTi", "STKaiti", "Microsoft YaHei", sans-serif;
  font-size: 15.5px;
  font-weight: 650;
  line-height: 1.4;
}

.first-use-annotation {
  --first-use-current-ink: var(--first-use-ink-green);
  position: relative;
  z-index: 1;
  display: inline;
  border-radius: 3px;
  padding: 0 0.04em;
  font-weight: 760;
}

.first-use-annotation[data-tone='yellow'] {
  --first-use-current-ink: var(--first-use-ink-yellow);
}

.first-use-annotation[data-tone='blue'] {
  --first-use-current-ink: var(--first-use-ink-blue);
}

.first-use-annotation[data-tone='coral'] {
  --first-use-current-ink: var(--first-use-ink-coral);
}

.first-use-annotation[data-annotation='highlight'] {
  background: linear-gradient(transparent 18%, rgba(239, 200, 74, 0.58) 18% 88%, transparent 88%);
}

.first-use-annotation[data-annotation='underline'] {
  text-decoration: underline wavy var(--first-use-current-ink) 1.5px;
  text-underline-offset: 2px;
}

.first-use-annotation[data-annotation='circle'],
.first-use-annotation[data-annotation='box'] {
  outline: 1.5px solid var(--first-use-current-ink);
  outline-offset: 1px;
}

.first-use-annotation[data-annotation='circle'] {
  border-radius: 50%;
}

.first-use-annotation[data-annotation='crossed-off'] {
  text-decoration: line-through var(--first-use-current-ink) 2px;
}

.annotations-ready .first-use-annotation {
  background: none;
  outline: 0;
  text-decoration: none;
}

.first-use-body-keyword {
  color: var(--app-text-primary, #191919);
  font-weight: 800;
}

.first-use-body-marker {
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
  border-radius: 2px;
  padding: 0 0.04em;
}

.first-use-body-marker[data-tone='yellow'] {
  background: linear-gradient(transparent 34%, rgba(239, 200, 74, 0.44) 34% 91%, transparent 91%);
}

.first-use-body-marker[data-tone='green'] {
  background: linear-gradient(transparent 34%, rgba(7, 193, 96, 0.23) 34% 91%, transparent 91%);
}

.first-use-body-marker[data-tone='coral'] {
  background: linear-gradient(transparent 34%, rgba(219, 97, 79, 0.25) 34% 91%, transparent 91%);
}

.first-use-section-copy p {
  margin: 0;
  color: var(--app-text-secondary, #5f6862);
  font-size: 14.25px;
  line-height: 1.48;
  text-wrap: pretty;
}

.first-use-section-copy p + p {
  margin-top: 2px;
}

.first-use-confirmation {
  margin: 7px 0 0 34px;
  padding: 7px 0 0 10px;
  border-top: 1px solid var(--app-border-soft, #e6ebe7);
  border-left: 2px solid #d79520;
  color: var(--app-text-secondary, #5f6862);
  font-size: 14px;
  line-height: 1.5;
}

.first-use-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding-top: clamp(9px, 1.3vh, 14px);
  border-top: 1px solid var(--app-border, #dfe6e1);
}

.first-use-footer-status {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
}

.first-use-footer-status p {
  margin: 0;
  color: var(--app-text-muted, #737d76);
  font-size: 13.5px;
  line-height: 1.45;
}

.first-use-status-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: #c58b26;
  box-shadow: 0 0 0 4px rgba(197, 139, 38, 0.12);
}

.first-use-status-dot.ready {
  background: var(--app-accent, #07c160);
  box-shadow: 0 0 0 4px rgba(7, 193, 96, 0.12);
}

.first-use-footer button {
  display: inline-flex;
  min-width: 218px;
  min-height: 38px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 0 20px;
  background: var(--app-accent, #07c160);
  color: #ffffff;
  font-size: 14.5px;
  font-weight: 650;
  line-height: 1;
  transition: transform 160ms ease, background-color 160ms ease, opacity 160ms ease;
}

.first-use-footer button:hover:not(:disabled) {
  background: #06ad56;
}

.first-use-footer button:active:not(:disabled) {
  transform: translateY(1px);
}

.first-use-footer button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(7, 193, 96, 0.24);
}

.first-use-footer button:disabled {
  cursor: not-allowed;
  background: #bdc7c0;
  opacity: 0.82;
}

.first-use-footer svg {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
}

html[data-theme='dark'] .first-use-page {
  --first-use-ink-yellow: #8f7a31;
  --first-use-ink-green: #58c989;
  --first-use-ink-blue: #78a4f4;
  --first-use-ink-coral: #ef8878;
  background:
    radial-gradient(circle at 8% 0%, rgba(62, 181, 117, 0.11), transparent 27%),
    linear-gradient(180deg, #171b19 0%, #111513 100%);
}

html[data-theme='dark'] .first-use-header,
html[data-theme='dark'] .first-use-document + .first-use-document,
html[data-theme='dark'] .first-use-footer {
  border-color: rgba(255, 255, 255, 0.12);
}

html[data-theme='dark'] .first-use-sections li,
html[data-theme='dark'] .first-use-confirmation {
  border-top-color: rgba(255, 255, 255, 0.09);
}

html[data-theme='dark'] .first-use-summary span + span {
  border-left-color: rgba(255, 255, 255, 0.12);
}

html[data-theme='dark'] .first-use-section-index {
  color: #75c596;
}

html[data-theme='dark'] .first-use-footer button:disabled {
  background: #4a544e;
  color: #aeb8b1;
}

@media (max-height: 840px) and (min-width: 901px) {
  .first-use-page {
    padding-top: 12px;
    padding-bottom: 9px;
  }

  .first-use-layout {
    gap: 10px;
  }

  .first-use-header {
    padding-bottom: 8px;
  }

  .first-use-document-header {
    padding-bottom: 6px;
  }

  .first-use-sections li {
    padding: 5px 0;
  }

  .first-use-footer {
    padding-top: 7px;
  }
}

@media (max-height: 720px) and (min-width: 901px) {
  .first-use-page {
    padding: 8px 24px 7px;
  }

  .first-use-layout {
    gap: 6px;
  }

  .first-use-header {
    gap: 20px;
    padding-bottom: 5px;
  }

  .first-use-logo {
    width: 38px;
    height: 38px;
  }

  .first-use-eyebrow {
    margin-bottom: 0;
    font-size: 11.5px;
  }

  .first-use-heading-copy h1 {
    font-size: 26px;
  }

  .first-use-document-description {
    display: none;
  }

  .first-use-summary {
    font-size: 13px;
  }

  .first-use-summary strong {
    font-size: 20px;
  }

  .first-use-document-header {
    grid-template-columns: 32px minmax(0, 1fr);
    gap: 8px;
    padding-bottom: 4px;
  }

  .first-use-document-header h2 {
    font-size: 18px;
  }

  .first-use-sections li {
    grid-template-columns: 24px minmax(0, 1fr);
    gap: 8px;
    padding: 3px 0;
  }

  .first-use-section-copy h3 {
    margin-bottom: 1px;
    font-size: 14.5px;
    line-height: 1.4;
  }

  .first-use-section-copy p {
    font-size: 13.5px;
    line-height: 1.42;
  }

  .first-use-confirmation {
    margin-top: 5px;
    margin-left: 29px;
    padding-top: 5px;
    font-size: 13px;
    line-height: 1.42;
  }

  .first-use-footer {
    padding-top: 5px;
  }

  .first-use-footer button {
    min-height: 38px;
  }
}

@media (max-width: 900px) {
  .first-use-page {
    height: auto;
    min-height: 100%;
    padding: 18px;
  }

  .first-use-layout {
    display: block;
  }

  .first-use-header {
    align-items: flex-start;
  }

  .first-use-summary {
    padding-top: 4px;
  }

  .first-use-documents {
    display: block;
    margin-top: 20px;
  }

  .first-use-document,
  .first-use-document + .first-use-document {
    padding: 0;
    border-left: 0;
  }

  .first-use-document + .first-use-document {
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid var(--app-border, #dfe6e1);
  }

  .first-use-footer {
    margin-top: 22px;
  }

  html[data-theme='dark'] .first-use-document + .first-use-document {
    border-top-color: rgba(255, 255, 255, 0.12);
  }
}

@media (max-width: 640px) {
  .first-use-header,
  .first-use-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .first-use-summary {
    justify-content: space-between;
  }

  .first-use-summary span {
    flex: 1 1 50%;
    padding: 0;
  }

  .first-use-summary span + span {
    padding-left: 14px;
  }

  .first-use-footer button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .first-use-footer button {
    transition: none;
  }
}
</style>
