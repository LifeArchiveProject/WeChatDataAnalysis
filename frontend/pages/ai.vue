<template>
  <div class="ai-preview theme-scope">
    <aside class="ai-preview-history" aria-label="AI 对话历史">
      <div class="ai-preview-tabs">
        <button type="button" class="is-active" @click="openAdvancedFeaturesDialog">对话</button>
        <button type="button" @click="openAdvancedFeaturesDialog">任务</button>
      </div>
      <div class="ai-preview-history-head">
        <button type="button" class="ai-preview-search" @click="openAdvancedFeaturesDialog">
          <Search :size="14" aria-hidden="true" />搜索对话
        </button>
        <button type="button" class="ai-preview-icon" title="新对话" aria-label="新对话" @click="openAdvancedFeaturesDialog">
          <SquarePen :size="17" aria-hidden="true" />
        </button>
      </div>
      <div class="ai-preview-history-list scrollbar-custom">
        <p>还没有对话</p>
      </div>
    </aside>

    <main class="ai-preview-main">
      <header class="ai-preview-head">
        <h1>新对话</h1>
        <span class="ai-preview-badge">高级版功能</span>
        <button type="button" class="ai-preview-icon" title="AI 设置" aria-label="AI 设置" @click="openAdvancedFeaturesDialog">
          <SlidersHorizontal :size="18" aria-hidden="true" />
        </button>
      </header>

      <div class="ai-preview-welcome scrollbar-custom">
        <div class="ai-preview-column">
          <h2>想了解聊天记录里的什么？</h2>
          <form class="ai-preview-composer" @submit.prevent="openAdvancedFeaturesDialog">
            <textarea
              rows="3"
              placeholder="问问你的聊天记录，回答会注明出自哪条消息"
              aria-label="向 AI 提问"
              @keydown.enter.exact.prevent="openAdvancedFeaturesDialog"
            />
            <div class="ai-preview-toolbar">
              <div class="ai-preview-tools">
                <button type="button" class="ai-preview-scope" @click="openAdvancedFeaturesDialog">
                  <Globe :size="14" aria-hidden="true" />全部聊天<ChevronDown :size="12" aria-hidden="true" />
                </button>
                <button type="button" class="ai-preview-icon" title="提到某个聊天" aria-label="插入联系人或群聊" @click="openAdvancedFeaturesDialog">
                  <AtSign :size="16" aria-hidden="true" />
                </button>
                <button type="button" class="ai-preview-summary" @click="openAdvancedFeaturesDialog">
                  <WandSparkles :size="15" aria-hidden="true" />总结
                </button>
              </div>
              <div class="ai-preview-tools">
                <button type="button" class="ai-preview-model" @click="openAdvancedFeaturesDialog">
                  选择模型<ChevronDown :size="12" aria-hidden="true" />
                </button>
                <button type="submit" class="ai-preview-send" title="发送（Enter）" aria-label="发送问题">
                  <ArrowUp :size="17" :stroke-width="2.2" aria-hidden="true" />
                </button>
              </div>
            </div>
          </form>

          <ul class="ai-preview-suggestions" aria-label="试试这样问">
            <li v-for="question in questions" :key="question">
              <button type="button" @click="openAdvancedFeaturesDialog">
                <Search :size="15" aria-hidden="true" />
                <span class="ai-preview-question">{{ question }}</span>
                <span class="ai-preview-question-scope"><Globe :size="13" aria-hidden="true" />全部聊天</span>
              </button>
            </li>
          </ul>
          <p class="ai-preview-note">高级版 AI 助手 · 聊天问答、内容总结与消息出处</p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ArrowUp, AtSign, ChevronDown, Globe, Search, SlidersHorizontal, SquarePen, WandSparkles } from '@lucide/vue'

useHead({ title: 'AI 助手 - 微信数据分析助手' })

const { openDialog: openAdvancedFeaturesDialog } = useAdvancedFeaturesDialog()
const questions = [
  '总结最近一周的聊天重点',
  '找找聊天里提到的待办事项',
  '最近有哪些重要约定？',
  '帮我回顾一段聊天的来龙去脉',
]
</script>

<style scoped>
.ai-preview { display: flex; width: 100%; height: 100%; min-height: 0; overflow: hidden; background: var(--app-surface-bg); color: var(--app-text-primary); font-size: 14px; }
.ai-preview button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; }
.ai-preview button:focus-visible { outline: 2px solid var(--app-accent); outline-offset: 2px; }
.ai-preview-history { display: flex; flex: 0 0 252px; flex-direction: column; min-height: 0; border-right: 1px solid var(--app-border); background: var(--app-surface-soft); }
.ai-preview-tabs { display: flex; gap: 4px; padding: 12px; border-bottom: 1px solid var(--app-border); }
.ai-preview-tabs button { flex: 1; height: 32px; border-radius: 6px; color: var(--app-text-muted); font-size: 13px; }
.ai-preview-tabs button.is-active { background: var(--app-surface-bg); color: var(--app-text-primary); box-shadow: 0 1px 3px rgb(0 0 0 / .06); }
.ai-preview-history-head { display: flex; align-items: center; gap: 6px; padding: 12px; }
.ai-preview .ai-preview-search { flex: 1; justify-content: flex-start; height: 32px; padding: 0 10px; border-radius: 6px; background: var(--app-surface-muted); color: var(--app-text-muted); font-size: 12px; }
.ai-preview .ai-preview-icon { flex: none; width: 30px; height: 30px; border-radius: 6px; color: var(--app-text-secondary); }
.ai-preview-icon:hover, .ai-preview-model:hover, .ai-preview-summary:hover { background: var(--app-neutral-btn-hover); }
.ai-preview-history-list { flex: 1; min-height: 0; overflow-y: auto; padding: 18px 12px; color: var(--app-text-muted); font-size: 12px; text-align: center; }
.ai-preview-main { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; }
.ai-preview-head { display: flex; flex: none; align-items: center; gap: 10px; height: 56px; padding: 0 22px; border-bottom: 1px solid var(--app-border-soft); }
.ai-preview-head h1 { margin: 0; color: var(--app-text-secondary); font-size: 14px; font-weight: 500; }
.ai-preview-head > button { margin-left: auto; }
.ai-preview-badge { border: 1px solid var(--app-border); border-radius: 4px; padding: 2px 6px; color: var(--app-text-muted); font-size: 11px; }
.ai-preview-welcome { display: flex; flex: 1; justify-content: center; min-height: 0; overflow-y: auto; padding: clamp(48px, 18vh, 160px) 24px 48px; }
.ai-preview-column { width: 100%; max-width: 760px; }
.ai-preview-column h2 { margin: 0 0 20px; font-size: 24px; font-weight: 600; line-height: 1.35; }
.ai-preview-composer { overflow: hidden; border: 1px solid var(--app-input-border); border-radius: 8px; background: var(--app-input-bg); }
.ai-preview-composer:focus-within { border-color: var(--app-accent); }
.ai-preview-composer textarea { display: block; width: 100%; min-height: 86px; resize: vertical; padding: 14px 16px 4px; border: 0; outline: 0; background: transparent; color: inherit; font: inherit; line-height: 22px; }
.ai-preview-composer textarea::placeholder { color: var(--app-text-muted); }
.ai-preview-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 10px 10px; }
.ai-preview-tools { display: flex; align-items: center; gap: 4px; min-width: 0; }
.ai-preview .ai-preview-scope { height: 26px; padding: 0 7px; border: 1px solid var(--app-border); border-radius: 6px; color: var(--app-text-secondary); font-size: 12px; white-space: nowrap; }
.ai-preview .ai-preview-summary, .ai-preview .ai-preview-model { height: 28px; padding: 0 7px; border-radius: 6px; color: var(--app-text-secondary); font-size: 12px; white-space: nowrap; }
.ai-preview .ai-preview-send { flex: none; width: 30px; height: 30px; margin-left: 2px; border-radius: 6px; background: var(--app-accent); color: white; }
.ai-preview-send:hover { background: var(--app-accent-hover); }
.ai-preview-suggestions { margin: 20px 0 0; padding: 0; list-style: none; }
.ai-preview-suggestions li { border-bottom: 1px solid var(--app-border-soft); }
.ai-preview-suggestions li:first-child { border-top: 1px solid var(--app-border-soft); }
.ai-preview-suggestions button { width: 100%; min-height: 46px; padding: 8px; text-align: left; }
.ai-preview-suggestions button:hover { background: var(--app-surface-soft); }
.ai-preview-suggestions svg { flex: none; color: var(--app-text-muted); }
.ai-preview-question { flex: 1; min-width: 0; }
.ai-preview-question-scope { display: inline-flex; flex: none; align-items: center; gap: 6px; margin-left: 12px; color: var(--app-text-muted); font-size: 12px; }
.ai-preview-note { margin: 18px 0 0; color: var(--app-text-muted); font-size: 12px; text-align: center; }
@media (max-width: 760px) { .ai-preview-history { flex-basis: 190px; } .ai-preview-welcome { padding: 48px 18px 32px; } .ai-preview-column h2 { font-size: 21px; } .ai-preview-question-scope { display: none; } }
@media (max-width: 560px) { .ai-preview-history { display: none; } .ai-preview-head { padding: 0 16px; } .ai-preview-summary { display: none !important; } }
</style>
