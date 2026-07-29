<template>
  <main class="first-use-page">
    <section class="first-use-panel" aria-labelledby="first-use-title">
      <header class="first-use-header">
        <div class="first-use-brand">
          <img src="/logo.png" alt="微信数据分析工具" class="first-use-logo" />
          <div class="first-use-heading-copy">
            <div class="first-use-meta">
              <span>开始使用前</span>
              <span>第 {{ stepIndex + 1 }} 步，共 {{ documents.length }} 步</span>
            </div>
            <h1 id="first-use-title" ref="titleRef" tabindex="-1">{{ currentDocument.title }}</h1>
            <p>{{ currentDocument.description }}</p>
          </div>
        </div>

        <div class="first-use-progress" aria-label="阅读进度">
          <span
            v-for="(document, index) in documents"
            :key="document.id"
            :class="{ active: index === stepIndex, complete: index < stepIndex }"
            :aria-current="index === stepIndex ? 'step' : undefined"
          >
            <i aria-hidden="true">{{ index + 1 }}</i>
            {{ document.shortTitle }}
          </span>
        </div>
      </header>

      <div ref="contentRef" class="first-use-content" tabindex="0">
        <ol class="first-use-sections">
          <li v-for="(section, index) in currentDocument.sections" :key="section.title">
            <span class="first-use-section-index" aria-hidden="true">{{ index + 1 }}</span>
            <div>
              <h2>{{ section.title }}</h2>
              <p v-for="paragraph in section.paragraphs" :key="paragraph">{{ paragraph }}</p>
            </div>
          </li>
        </ol>

        <p v-if="currentDocument.confirmation" class="first-use-confirmation">
          {{ currentDocument.confirmation }}
        </p>
      </div>

      <footer class="first-use-footer">
        <p aria-live="polite">
          {{ canConfirm ? '已完成本页阅读计时，可以继续。' : `请继续阅读，${remainingSeconds} 秒后可确认。` }}
        </p>
        <button
          type="button"
          data-testid="first-use-confirm"
          :disabled="!canConfirm"
          @click="confirmCurrentDocument"
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
    </section>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  normalizeFirstUseRedirect,
  persistFirstUseAgreementAcceptance
} from '~/lib/first-use-agreement'

const COUNTDOWN_MILLISECONDS = 10_000

const documents = [
  {
    id: 'notice',
    shortTitle: '使用须知',
    title: '开始前请阅读使用须知',
    description: '为确保数据识别、密钥处理和后续功能正常运行，请在继续前确认以下事项。',
    sections: [
      {
        title: '版本要求',
        paragraphs: ['本项目目前仅支持微信桌面端 4.x 版本。使用较低版本时，请先将微信升级至受支持版本。']
      },
      {
        title: '密钥与账号、设备的关系',
        paragraphs: ['数据库密钥同时与微信账号和当前设备相关联。同一账号在不同设备上的密钥通常不同，不能相互替代或混用。']
      },
      {
        title: '登录要求',
        paragraphs: [
          '若账号从未在当前设备登录，本项目无法读取该设备上不存在的历史数据。首次准备数据时，请至少在当前设备成功登录一次；已经完成解密或导入的数据可以离线查看。',
          '即使当前设备上已经存在某个账号的历史数据目录，首次解密该账号前仍至少需要成功登录一次。仅发现历史文件，并不表示已经完成账号识别或具备可用的解密条件。'
        ]
      },
      {
        title: '保持单一微信实例',
        paragraphs: ['开始检测和获取密钥前，请仅运行并登录一个微信实例。微信多开、切换账号或同时运行多个实例，可能造成进程识别错误、数据来源混淆、密钥获取失败或其他非预期结果。']
      },
      {
        title: 'Windows 密钥获取与安全提醒',
        paragraphs: [
          'Windows 端会优先使用 V4 内存扫描获取数据库密钥。该方式不执行 Hook，通常不会触发 Hook 相关的微信账号安全提醒；内存扫描失败时，系统才会询问是否改用 Hook。',
          'Hook 获取可能触发微信侧账号安全提醒。现有反馈显示，此类提醒可能延迟出现或集中触达，目前未观察到普遍导致封号的情况；但微信侧策略可能随时调整，本项目不作绝对保证。相关风险取决于微信客户端的检测策略，并非操作系统自身的安全警告。'
        ]
      },
      {
        title: 'macOS 平台说明',
        paragraphs: ['macOS 版不提供数据库密钥获取。请使用支持 macOS 的同类本地工具取得密钥后手动填写；图片密钥仍可按页面提示获取。填写数据库密钥后，除平台专属能力外，实时消息等功能与 Windows 端基本一致。']
      },
      {
        title: '避免重复获取密钥',
        paragraphs: ['密钥获取成功后请妥善保存并优先复用。在微信未调整密钥机制、数据格式，且账号与设备环境未发生变化时，密钥通常可以持续使用。现有密钥仍有效时，请勿重复获取，以减少不必要的操作和潜在风险。']
      }
    ]
  },
  {
    id: 'disclaimer',
    shortTitle: '免责声明',
    title: '免责声明与使用确认',
    description: '请在充分理解以下内容，并自愿承担相应责任的前提下使用本项目。',
    sections: [
      {
        title: '项目性质',
        paragraphs: ['本项目为独立开发的非官方开源工具，与微信、腾讯及其关联主体不存在隶属、授权、合作或认可关系。相关产品名称和商标归其权利人所有。']
      },
      {
        title: '合法使用',
        paragraphs: ['本项目仅可用于处理您本人合法持有、管理或已经取得明确授权访问的数据。使用者应遵守适用的法律法规、软件许可协议、平台规则和隐私保护义务。']
      },
      {
        title: '数据与备份',
        paragraphs: ['使用过程可能涉及本地数据库、密钥、聊天记录、媒体文件、微信进程和系统接口。开始前请备份重要数据、密钥及配置，并自行负责密钥保管、数据安全和隐私保护。']
      },
      {
        title: '兼容性与运行风险',
        paragraphs: ['客户端版本变化、内存扫描、Hook、第三方组件及其他本地处理流程，可能导致账号提醒、功能失效、处理失败、文件异常或其他不可预期结果。本项目不保证对未来微信版本持续兼容。']
      },
      {
        title: '责任范围',
        paragraphs: ['本项目按现状提供，不对功能的准确性、完整性、稳定性或持续可用性作出明示或默示保证。在适用法律允许的范围内，因使用、误用、版本不兼容、操作中断或第三方策略变化产生的损失和后果，由使用者自行承担。']
      }
    ],
    confirmation: '点击确认即表示您已完整阅读、理解并同意以上内容，并自愿继续使用本项目。'
  }
]

const route = useRoute()
const stepIndex = ref(0)
const remainingMilliseconds = ref(COUNTDOWN_MILLISECONDS)
const titleRef = ref(null)
const contentRef = ref(null)
let countdownTimer = null
let lastTickAt = 0

const currentDocument = computed(() => documents[stepIndex.value])
const remainingSeconds = computed(() => Math.ceil(remainingMilliseconds.value / 1000))
const canConfirm = computed(() => remainingMilliseconds.value <= 0)
const primaryLabel = computed(() => {
  if (!canConfirm.value) return `请阅读（${remainingSeconds.value} 秒）`
  return stepIndex.value === documents.length - 1 ? '我已阅读并同意，开始使用' : '我已阅读，继续'
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

const confirmCurrentDocument = async () => {
  if (!canConfirm.value) return

  if (stepIndex.value < documents.length - 1) {
    stepIndex.value += 1
    startCountdown()
    await nextTick()
    contentRef.value?.scrollTo?.({ top: 0 })
    titleRef.value?.focus?.()
    return
  }

  persistFirstUseAgreementAcceptance()
  await navigateTo(normalizeFirstUseRedirect(route.query.redirect), { replace: true })
}

useHead({ title: '使用须知与免责声明 - 微信数据分析工具' })

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  startCountdown()
  titleRef.value?.focus?.()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopCountdown()
})
</script>

<style scoped>
.first-use-page {
  display: grid;
  min-height: 100%;
  place-items: center;
  padding: 20px;
  background: #f2f4f3;
  color: var(--app-text-primary, #191919);
}

.first-use-panel {
  display: flex;
  width: min(760px, 100%);
  max-height: calc(100vh - 40px);
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--app-border, #e7e7e7);
  border-radius: 8px;
  background: var(--app-surface-bg, #ffffff);
  box-shadow: 0 18px 50px rgba(18, 32, 24, 0.14);
}

.first-use-header {
  flex: 0 0 auto;
  padding: 24px 28px 18px;
  border-bottom: 1px solid var(--app-border-soft, #ececec);
}

.first-use-brand {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.first-use-logo {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  object-fit: contain;
}

.first-use-heading-copy {
  min-width: 0;
  flex: 1;
}

.first-use-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--app-accent, #07c160);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.4;
}

.first-use-heading-copy h1 {
  margin: 5px 0 0;
  outline: none;
  font-size: 22px;
  font-weight: 650;
  line-height: 1.4;
  letter-spacing: 0;
}

.first-use-heading-copy > p {
  margin: 7px 0 0;
  color: var(--app-text-secondary, #5f5f5f);
  font-size: 14px;
  line-height: 1.7;
}

.first-use-progress {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 18px;
}

.first-use-progress span {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  border-top: 3px solid var(--app-border, #e7e7e7);
  padding-top: 8px;
  color: var(--app-text-muted, #909090);
  font-size: 12px;
  line-height: 1.4;
}

.first-use-progress span.active,
.first-use-progress span.complete {
  border-color: var(--app-accent, #07c160);
  color: var(--app-text-primary, #191919);
}

.first-use-progress i {
  display: grid;
  width: 20px;
  height: 20px;
  flex: 0 0 20px;
  place-items: center;
  border-radius: 50%;
  background: var(--app-surface-muted, #f3f3f3);
  color: inherit;
  font-style: normal;
  font-weight: 650;
}

.first-use-progress span.active i,
.first-use-progress span.complete i {
  background: rgba(7, 193, 96, 0.12);
  color: var(--app-accent, #07c160);
}

.first-use-content {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 6px 28px 20px;
  outline: none;
}

.first-use-content:focus-visible {
  box-shadow: inset 0 0 0 2px rgba(7, 193, 96, 0.2);
}

.first-use-sections {
  margin: 0;
  padding: 0;
  list-style: none;
}

.first-use-sections li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 12px;
  padding: 16px 0;
  border-bottom: 1px solid var(--app-border-soft, #ececec);
}

.first-use-section-index {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 50%;
  background: var(--app-surface-muted, #f3f3f3);
  color: var(--app-text-secondary, #5f5f5f);
  font-size: 12px;
  font-weight: 650;
}

.first-use-sections h2 {
  margin: 1px 0 5px;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.5;
  letter-spacing: 0;
}

.first-use-sections p {
  margin: 0;
  color: var(--app-text-secondary, #5f5f5f);
  font-size: 13px;
  line-height: 1.75;
}

.first-use-sections p + p {
  margin-top: 7px;
}

.first-use-confirmation {
  margin: 18px 0 0;
  padding: 12px 14px;
  border-left: 3px solid #d79520;
  background: rgba(215, 149, 32, 0.08);
  color: var(--app-text-secondary, #5f5f5f);
  font-size: 13px;
  line-height: 1.7;
}

.first-use-footer {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 28px;
  border-top: 1px solid var(--app-border-soft, #ececec);
  background: var(--app-surface-soft, #f7f7f7);
}

.first-use-footer p {
  margin: 0;
  color: var(--app-text-muted, #909090);
  font-size: 12px;
  line-height: 1.5;
}

.first-use-footer button {
  display: inline-flex;
  min-width: 210px;
  min-height: 42px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--app-accent, #07c160);
  border-radius: 7px;
  padding: 9px 16px;
  background: var(--app-accent, #07c160);
  color: #ffffff;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.4;
  transition: background-color 160ms ease, border-color 160ms ease, opacity 160ms ease;
}

.first-use-footer button:hover:not(:disabled) {
  border-color: var(--app-accent-hover, #06ad56);
  background: var(--app-accent-hover, #06ad56);
}

.first-use-footer button:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.32);
  outline-offset: 2px;
}

.first-use-footer button:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.first-use-footer svg {
  width: 17px;
  height: 17px;
  flex: 0 0 17px;
}

@media (max-width: 640px) {
  .first-use-page {
    place-items: stretch;
    padding: 0;
  }

  .first-use-panel {
    width: 100%;
    max-height: 100vh;
    min-height: 100%;
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .first-use-header {
    padding: 20px 18px 16px;
  }

  .first-use-logo {
    width: 42px;
    height: 42px;
    flex-basis: 42px;
  }

  .first-use-meta {
    align-items: flex-start;
    flex-direction: column;
    gap: 3px;
  }

  .first-use-heading-copy h1 {
    font-size: 19px;
  }

  .first-use-content {
    padding: 4px 18px 18px;
  }

  .first-use-footer {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
    padding: 14px 18px max(14px, env(safe-area-inset-bottom));
  }

  .first-use-footer button {
    width: 100%;
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .first-use-footer button {
    transition: none;
  }
}
</style>
