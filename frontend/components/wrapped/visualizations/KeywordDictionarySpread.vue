<template>
  <div ref="rootEl" class="kd-root">
    <!-- 空状态 -->
    <div v-if="!hasEntries" class="kd-empty">
      <div class="kd-empty-card">
        <div class="wrapped-title text-base text-[#000000e6]">暂无常用语</div>
        <div class="mt-1 wrapped-body text-sm text-[#7F7F7F]">这一年你还没有足够的重复短句来立词条。</div>
      </div>
    </div>

    <div
      v-else
      ref="stageEl"
      class="kd-stage"
      data-deck-nodrag
      :class="{ 'kd-stage--rm': reducedMotion, 'kd-stage--paused': paused }"
    >
      <div class="kd-fit" :style="fitStyle">
        <!-- 版式修饰类：中缝是竖是横、词头侧标在右还是在下，都跟着算出来的版式走，
             不跟画幅 tier 绑死（同一档画幅换了尺寸也可能换版式）。16:9 两个类都不挂。 -->
        <div
          class="kd-spread"
          :class="{
            'kd-spread--in': entered,
            'kd-spread--stack': layout.mode === 'stack',
            'kd-spread--sideunder': layout.headSideW === 0
          }"
          :style="spreadStyle"
        >
          <!-- ── 纸面层 ── -->
          <div class="kd-paper" aria-hidden="true" />
          <div class="kd-sweep" aria-hidden="true" />
          <div class="kd-bow kd-bow--t" aria-hidden="true" />
          <div class="kd-bow kd-bow--b" aria-hidden="true" />
          <div class="kd-edge kd-edge--l" aria-hidden="true" />
          <div class="kd-edge kd-edge--r" aria-hidden="true" />

          <!-- ══════════ 左页：词条 ══════════ -->
          <div
            ref="leafEl"
            class="kd-leaf"
            :class="{ 'kd-leaf--flipping': flipping }"
          >
            <div class="kd-rhead">
              <span class="kd-rh-a">微 信 年 度 词 典</span>
              <span class="kd-rh-b">{{ yearCn }}年版 · 正编</span>
            </div>
            <div class="kd-rule kd-rule--a" />

            <!-- 词头：字号按字数收缩，基线固定，长短句都立在同一条线上 -->
            <div class="kd-hw" @dblclick="toggleExpanded">
              <span
                class="kd-hw-word wrapped-privacy-keyword"
                :style="{ fontSize: headFontSize + 'px' }"
              >{{ current.word }}</span>
              <span class="kd-hw-side">
                <span class="kd-chip">〔{{ current.kindLabel }}〕</span>
                <span class="kd-charcount kd-num">{{ current.charCount }} 字</span>
              </span>
            </div>

            <div class="kd-metaline">
              〔口头禅〕· 本年 <span class="kd-num">{{ fmt(current.count) }}</span> 例
              · 平均 <span class="kd-num">{{ current.avgDays }}</span> 天一次
              · 排名 <span class="kd-num">{{ pad2(current.rank) }}</span> / <span class="kd-num">{{ pad2(entries.length) }}</span>
            </div>
            <div class="kd-rule kd-rule--b" />

            <!-- 义项：全部由真实数据写成，不编释义 -->
            <div class="kd-def">
              <span class="kd-def-no">1</span><span class="kd-def-body">{{ current.gloss }}</span>
            </div>

            <div class="kd-seclabel">
              <span class="kd-seclabel-a">书 证</span>
              <span class="kd-seclabel-b">
                引自本年聊天记录，一字未改<template v-if="citeTotal > shownCites.length"> · 共 {{ citeTotal }} 条</template>
              </span>
            </div>
            <div class="kd-rule kd-rule--c" />

            <div class="kd-cites" :class="{ 'kd-cites--expanded': expanded }">
              <div
                v-for="(c, i) in shownCites"
                :key="`${current.word}-${flipSeq}-${i}`"
                class="kd-cite"
                :class="{ 'kd-cite--dim': focusedCite >= 0 && focusedCite !== i, 'kd-cite--on': focusedCite === i }"
                role="button"
                tabindex="0"
                @click="focusCite(i)"
                @keydown.enter.prevent="focusCite(i)"
                @keydown.space.prevent="focusCite(i)"
              >
                <span class="kd-cno kd-num">{{ i + 1 }}</span>
                <span class="kd-cq wrapped-privacy-message">
                  <span class="kd-qm">「</span><template
                    v-for="(seg, si) in c.tokens"
                    :key="`${i}-${si}`"
                  ><b v-if="seg.type === 'hl'">{{ seg.content }}</b><img
                    v-else-if="seg.type === 'emoji'"
                    :src="seg.emojiSrc"
                    :alt="seg.content"
                    class="kd-emoji"
                  /><template v-else>{{ seg.content }}</template></template><span class="kd-qm">」</span>
                </span>
              </div>
            </div>

            <!-- 没有真的相关词目时，这条栏线连同「参见」一起收掉，不留孤线 -->
            <div v-if="seeAlso.length > 0" class="kd-rule kd-rule--d" />
            <div v-if="seeAlso.length > 0" class="kd-see">
              <span class="kd-see-a">参 见</span>
              <span class="kd-see-b">
                <template v-for="(s, i) in seeAlso" :key="s.word">
                  <span
                    class="kd-see-w wrapped-privacy-keyword"
                    role="button"
                    tabindex="0"
                    @click="selectByWord(s.word)"
                    @keydown.enter.prevent="selectByWord(s.word)"
                  >{{ s.word }}</span><span v-if="i < seeAlso.length - 1" class="kd-see-sep">　·　</span>
                </template>
              </span>
            </div>

            <div class="kd-folio kd-folio--l kd-num">{{ pad2(current.rank * 2 - 1) }}</div>
            <div class="kd-catch">词目索引</div>
          </div>

          <div class="kd-gutter" aria-hidden="true" />

          <!-- ══════════ 右页：词目索引 ══════════ -->
          <div class="kd-page-r">
            <div class="kd-rhead kd-rhead--r">
              <span class="kd-rh-a">词 目 索 引</span>
              <span class="kd-rh-b wrapped-privacy-keyword">{{ runningHead }}</span>
            </div>
            <div class="kd-rule kd-rule--r kd-rule--ar" />

            <!-- 篇题与小序：卡片的标题和那句「抄经」都印在书里 -->
            <div v-if="title" class="kd-booktitle">{{ title }}</div>
            <p class="kd-preface">
              一遍又一遍写同一句话，在中文里从来不叫无聊，叫抄经。这一年你抄了
              <span class="kd-num kd-em">{{ fmt(matchedCandidates) }}</span> 遍，落在
              <span class="kd-num kd-em">{{ fmt(uniquePhrases) }}</span> 句不同的话上<template v-if="entries.length > 0">；最勤的一句「<span class="kd-em wrapped-privacy-keyword">{{ entries[0].word }}</span>」，抄了 <span class="kd-num kd-em">{{ fmt(entries[0].count) }}</span> 遍</template>。
            </p>

            <div class="kd-fanli">
              <span class="kd-fanli-t">凡例</span>一、词目按本年例数降序排列。　二、朱色者为本年词首，即{{ leafSideCn }}所立之词条。
            </div>

            <div class="kd-idx">
              <div v-for="(col, ci) in indexColumns" :key="`col${ci}`" class="kd-col">
                <div class="kd-chead">
                  <span class="kd-chead-a">词目</span>
                  <span class="kd-chead-b">本年例数</span>
                </div>
                <div
                  v-for="e in col"
                  :key="e.word"
                  class="kd-row"
                  :class="{ 'kd-row--cur': e.word === current.word }"
                  role="button"
                  tabindex="0"
                  :aria-label="`${e.word}，本年 ${e.count} 例`"
                  @click="selectByWord(e.word)"
                  @keydown.enter.prevent="selectByWord(e.word)"
                  @keydown.space.prevent="selectByWord(e.word)"
                >
                  <span class="kd-w wrapped-privacy-keyword">{{ e.word }}</span>
                  <span class="kd-ld" />
                  <span class="kd-ct kd-num">{{ fmt(e.count) }}</span>
                </div>
              </div>
            </div>

            <div class="kd-rule kd-rule--r kd-rule--er" />
            <div class="kd-colophon">
              本词典收录短句 <span class="kd-num">{{ fmt(matchedCandidates) }}</span> 条，去重词目
              <span class="kd-num">{{ fmt(uniquePhrases) }}</span>，其中 <span class="kd-num">{{ entries.length }}</span> 条入正编。
            </div>
            <div class="kd-folio kd-folio--r kd-num">{{ pad2(current.rank * 2) }}</div>
          </div>

          <!-- ══════════ 玻璃取词镜 ══════════ -->
          <div
            v-if="!reducedMotion"
            ref="lensEl"
            class="kd-lens"
            :class="{ 'kd-lens--drag': lensDragging }"
            :style="lensStyle"
            role="slider"
            tabindex="0"
            :aria-label="`取词镜，当前 ${current.word}`"
            :aria-valuetext="current.word"
            @pointerdown="onLensDown"
            @keydown.down.prevent="step(1)"
            @keydown.up.prevent="step(-1)"
          >
            <!-- 镜下：把镜圈覆盖到的词目按鱼眼剖面重排放大，字是真的 DOM 文字，不糊 -->
            <div class="kd-lens-mag">
              <div
                v-for="r in lensRows"
                :key="`lr-${r.word}`"
                class="kd-row kd-lrow"
                :class="{ 'kd-row--cur': r.word === current.word }"
                :style="r.style"
              >
                <span class="kd-w wrapped-privacy-keyword">{{ r.word }}</span>
                <span class="kd-ld" />
                <span class="kd-ct kd-num">{{ fmt(r.count) }}</span>
              </div>
            </div>
            <span class="kd-lens-body" aria-hidden="true" />
            <span class="kd-lens-caustic" aria-hidden="true" />
            <span class="kd-lens-chroma" aria-hidden="true" />
            <span class="kd-lens-spec" aria-hidden="true" />
          </div>

          <div class="kd-vignette" aria-hidden="true" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'
import { parseTextWithEmoji } from '~/lib/wechat-emojis'
import { useWrappedStage } from '~/composables/useWrappedStage'
import { ENTRY_CAP, buildDictionaryLayout } from '~/lib/wrapped-dictionary-layout'

const props = defineProps({
  keywords: { type: Array, default: () => [] }, // [{word,count,weight}]
  examples: { type: Array, default: () => [] }, // [{word,count,messages:[]}]
  topKeyword: { type: Object, default: null },
  year: { type: Number, default: 0 },
  meta: { type: Object, default: () => ({}) },
  // 卡片标题印在右页的篇题上——这张卡不在书外面显示任何标题
  title: { type: String, default: '' },
  reducedMotion: { type: Boolean, default: false },
  paused: { type: Boolean, default: false }
})

// ── 设计栅格：按画幅**换画布**，而不是把同一张跨页缩小 ──
// 舞台面积恒定（≈1.44M px²）⇒ 同样的字号在每个画幅里都装得下，只要把版式换掉。
// 版式本身由 lib/wrapped-dictionary-layout.js 从画布宽高推出来（纯几何、有 node 测试兜底），
// 这里只负责「画布多大」和「把算出来的数发给 CSS」。
const stage = useWrappedStage()

// 画布必须跟舞台**同比**，否则 fitScale 会在卡内再套一层信箱边 —— 那等于「缩小适配」。
// wide 保持 1600×900 常量（16:9 与「跟随窗口」逐像素零回归）；
// 其余档位直接取该画幅的设计盒，做到零信箱（3:4 是 1040×1386、4:5 是 1074×1342，
// 写死一张 900×1600 会在这两档各留 10%/13% 的空边）。
const CANVAS = { wide: { w: 1600, h: 900 } }

const tierName = computed(() => stage.tier.value || 'wide')
const canvas = computed(() => {
  if (tierName.value === 'wide') return CANVAS.wide
  const d = stage.design.value
  const w = Number(d?.w) > 0 ? Number(d.w) : 1600
  const h = Number(d?.h) > 0 ? Number(d.h) : 900
  return { w, h }
})
const DW = computed(() => canvas.value.w)
const DH = computed(() => canvas.value.h)

// ── 版口 / 索引栅格 / 取词镜：一套几何，一个真值源 ──
// 每个数都由 buildDictionaryLayout(画布宽, 画布高) 现算：版心、栏数、每栏行数、
// 书证条数、释义行数……没有任何一档是硬写的常量，所以换画布不会有词条被排到版口外。
// rowGeometry、lensRows、nearestRow、拖拽 clamp、词头字号全部读 layout.*，
// CSS 侧由下面的 spreadStyle 把同一批数字以 --kd-* 变量下发到 .kd-spread，两边绝不会走散。
// 16:9 的画布恒为 1600×900 ⇒ 算出来逐字段等于改动前写死的那套绝对定位
//（tests/wrapped-dictionary-layout.test.mjs 里对着 WIDE_BASELINE 逐字段断言）。
const layout = computed(() => buildDictionaryLayout(DW.value, DH.value))

// 同一批几何数字下发给 CSS。16:9（含「跟随窗口」）的既有声明不读这些变量，所以下发本身无副作用。
const spreadStyle = computed(() => {
  const L = layout.value
  const px = (n) => `${n}px`
  return {
    '--kd-pw': px(L.pw),
    '--kd-leaf-x': px(L.leafX),
    '--kd-leaf-y': px(L.leafY),
    '--kd-leaf-h': px(L.leafH),
    '--kd-pr-x': px(L.prX),
    '--kd-pr-y': px(L.prY),
    '--kd-pr-h': px(L.prH),
    '--kd-gutter-x': px(L.gutterX),
    '--kd-gutter-y': px(L.gutterY),
    '--kd-gutter-w': px(L.gutterW),
    '--kd-gutter-h': px(L.gutterH),
    '--kd-gutter-line': px(L.gutterLine),
    '--kd-t-rhead': px(L.tRhead),
    '--kd-t-rule-a': px(L.tRuleA),
    '--kd-t-hw': px(L.tHw),
    '--kd-h-hw': px(L.hHw),
    '--kd-t-meta': px(L.tMeta),
    '--kd-t-rule-b': px(L.tRuleB),
    '--kd-t-def': px(L.tDef),
    '--kd-t-seclabel': px(L.tSeclabel),
    '--kd-t-rule-c': px(L.tRuleC),
    '--kd-t-cites': px(L.tCites),
    '--kd-h-cites': px(L.hCites),
    '--kd-t-rule-d': px(L.tRuleD),
    '--kd-t-see': px(L.tSee),
    '--kd-t-folio': px(L.tFolio),
    '--kd-t-rule-ar': px(L.tRuleAR),
    '--kd-t-btitle': px(L.tBookTitle),
    '--kd-t-preface': px(L.tPreface),
    '--kd-t-fanli': px(L.tFanli),
    '--kd-t-idx': px(L.tIdx),
    '--kd-t-rule-er': px(L.tRuleE),
    '--kd-t-colophon': px(L.tColophon),
    '--kd-t-folio-r': px(L.tFolioR),
    '--kd-col-w': px(L.colW),
    '--kd-col-gap': px(L.colGap),
    '--kd-word-max': px(L.wordMaxW),
    '--kd-cite-max': px(L.citeMaxW),
    // 截断行数也是算出来的：页越高，释义 / 书证 / 小序放开得越多（只放开，不收紧）
    '--kd-def-lines': String(L.defLines),
    '--kd-cite-lines': String(L.citeLines),
    '--kd-preface-lines': String(L.prefaceLines)
  }
})

const nf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const fmt = (n) => nf.format(Math.round(Number(n) || 0))
const pad2 = (n) => String(Math.max(0, Math.round(Number(n) || 0))).padStart(2, '0')
const clamp = (v, a, b) => Math.min(Math.max(v, a), b)

const rootEl = ref(null)
const stageEl = ref(null)
const leafEl = ref(null)
const lensEl = ref(null)

/* 导出模式（页面级 provide）。为真期间跨页必须**立刻**是终态：词头、释义、书证、
   取词镜全部就位，而不是还在那 1.4s 的 fromTo 里。
   ⚠️ 不能借 props.reducedMotion 这条现成通路：reduced 的模板里
   `v-if="!reducedMotion"` 会把整个「玻璃取词镜」拿掉——那是这一页的招牌构件，
   导出图少了它就废了。所以单独走 exportMode 分支，只跳过动画、不动结构。 */
const exportMode = inject('wrappedExportMode', ref(false))

const entered = ref(false)
const flipping = ref(false)
const flipSeq = ref(0)
const expanded = ref(false)
const focusedCite = ref(-1)

// ── 数据整形 ──
const CJK_RE = /[^\x00-\xff]/

const visualUnits = (s) => Array.from(String(s || ''))
  .reduce((acc, ch) => acc + (CJK_RE.test(ch) ? 1 : 0.55), 0)

// 只按字数分类，不臆测词性
const kindLabel = (word) => {
  const n = Array.from(String(word || '')).filter((c) => !/\s/.test(c)).length
  if (n <= 2) return '词'
  if (n <= 6) return '短语'
  return '句'
}

const matchedCandidates = computed(() => Number(props.meta?.matchedCandidates || 0))
const uniquePhrases = computed(() => Number(props.meta?.uniquePhrases || 0))

const entries = computed(() => {
  const xs = (Array.isArray(props.keywords) ? props.keywords : [])
    .map((x) => ({
      word: String(x?.word || '').trim(),
      count: Number(x?.count || 0)
    }))
    .filter((x) => x.word && Number.isFinite(x.count) && x.count > 0)
  xs.sort((a, b) => (b.count - a.count) || a.word.localeCompare(b.word))

  const total = matchedCandidates.value
  // 正编容量与版式引擎共用一个常量：版口按 ENTRY_CAP 条排，词目再少也不重排
  return xs.slice(0, ENTRY_CAP).map((x, i) => {
    const avg = x.count > 0 ? 365 / x.count : 0
    const avgDays = avg >= 10 ? String(Math.round(avg)) : avg.toFixed(1)
    const share = total > 0 ? (x.count / total) * 100 : 0
    const chars = Array.from(x.word).length

    // 释义只由真实数据写成
    const bits = []
    if (i === 0 && uniquePhrases.value > 0) {
      bits.push(`本年共 ${fmt(x.count)} 例，为全部 ${fmt(uniquePhrases.value)} 个词目之首`)
    } else {
      bits.push(`本年共 ${fmt(x.count)} 例，在全部 ${fmt(uniquePhrases.value || 0)} 个词目中列第 ${i + 1} 位`)
    }
    if (share >= 0.01) bits.push(`占本年全部短句的 ${share < 1 ? share.toFixed(2) : share.toFixed(1)}%`)
    bits.push(`平均 ${avgDays} 天出现一次`)

    return {
      word: x.word,
      count: x.count,
      rank: i + 1,
      avgDays,
      charCount: chars,
      kindLabel: kindLabel(x.word),
      units: visualUnits(x.word),
      gloss: bits.join('；') + '。'
    }
  })
})

const hasEntries = computed(() => entries.value.length > 0)

const examplesMap = computed(() => {
  const out = new Map()
  for (const x of (Array.isArray(props.examples) ? props.examples : [])) {
    const w = String(x?.word || '').trim()
    if (!w) continue
    const msgs = (Array.isArray(x?.messages) ? x.messages : [])
      .map((m) => String(m || '').trim())
      .filter(Boolean)
    out.set(w, msgs.slice(0, 10))
  }
  return out
})

// ── 当前词条 ──
const currentIndex = ref(0)
const current = computed(() => entries.value[currentIndex.value] || entries.value[0] || {
  word: '', count: 0, rank: 1, avgDays: '0', charCount: 0, kindLabel: '词', units: 1, gloss: ''
})

// 词头必须一行放下，且右边要给〔词类〕与字数标注留出位置，否则长句会把侧标顶进中缝。
// 1:1 下侧标改叠到词下面（headSideW/headGap = 0），可用宽度反而比 16:9 更大。
const headFontSize = computed(() => {
  const L = layout.value
  const u = Math.max(1, current.value.units || 1)
  const avail = L.pw - L.headSideW - L.headGap
  return Math.round(clamp(avail / (u * 1.04), 32, 150))
})

const tokenize = (raw, word) => {
  const segs = parseTextWithEmoji(String(raw || ''))
  const list = (Array.isArray(segs) && segs.length > 0) ? segs : [{ type: 'text', content: String(raw || '') }]
  const w = String(word || '')
  const out = []
  for (const seg of list) {
    if (seg.type !== 'text' || !w) { out.push(seg); continue }
    let rest = String(seg.content || '')
    while (rest.length > 0) {
      const idx = rest.indexOf(w)
      if (idx < 0) { out.push({ type: 'text', content: rest }); break }
      if (idx > 0) out.push({ type: 'text', content: rest.slice(0, idx) })
      out.push({ type: 'hl', content: w })
      rest = rest.slice(idx + w.length)
    }
  }
  return out
}

const citePool = computed(() => {
  const pool = examplesMap.value.get(current.value.word) || []
  // 后端没给到原话时，退回短语本身（绝不编造聊天原文）
  return pool.length > 0 ? pool : [current.value.word].filter(Boolean)
})
const citeTotal = computed(() => citePool.value.length)
const shownCites = computed(() => {
  // 竖幅里书证区高出一大截，就多引几条真话把版口填满（citeSlots 下限恒为 3 = 16:9 基线），
  // 而不是把三条书证的字号拉大——补白只能用真数据补。
  const slots = Math.max(3, layout.value.citeSlots || 3)
  const n = expanded.value ? citePool.value.length : Math.min(slots, citePool.value.length)
  return citePool.value.slice(0, n).map((m) => ({ tokens: tokenize(m, current.value.word) }))
})

// 参见：只列真的有关系的词目（共享 ≥2 字的子串），没有就不显示这一行
const seeAlso = computed(() => {
  const cur = current.value.word
  if (!cur) return []
  const curChars = Array.from(cur)
  const grams = new Set()
  for (let i = 0; i < curChars.length - 1; i += 1) grams.add(curChars.slice(i, i + 2).join(''))
  const out = []
  for (const e of entries.value) {
    if (e.word === cur) continue
    for (const g of grams) {
      if (e.word.includes(g)) { out.push(e); break }
    }
    if (out.length >= 3) break
  }
  return out
})

const yearCn = computed(() => {
  const y = String(props.year || '')
  const map = { 0: '〇', 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九' }
  return y ? Array.from(y).map((c) => map[c] ?? c).join('') : ''
})

// ── 索引：栏数由版式引擎按「可用高度装得下几行」定（16:9/4:3/1:1/3:4/4:5 两栏、9:16 经折装三栏），
//         ENTRY_CAP 条词目在任何画幅下都一次排完，不分页、不砍词条 ──
const indexColumns = computed(() => {
  const xs = entries.value
  const n = Math.max(1, layout.value.cols)
  const per = Math.max(1, Math.ceil(xs.length / n))
  const out = []
  for (let i = 0; i < n; i += 1) out.push(xs.slice(i * per, (i + 1) * per))
  return out
})

// 凡例里指路的那半句：左右跨页说「左页」，经折装说「上页」
const leafSideCn = computed(() => (layout.value.mode === 'stack' ? '上页' : '左页'))

const runningHead = computed(() => {
  const xs = entries.value
  if (xs.length === 0) return ''
  return `${xs[0].word} — ${xs[xs.length - 1].word}`
})

// 每条词目在设计坐标里的中心（镜片折射与吸附都用它）
const rowGeometry = computed(() => {
  const L = layout.value
  const out = []
  indexColumns.value.forEach((col, ci) => {
    const x = L.idxLeft + ci * (L.colW + L.colGap)
    col.forEach((e, ri) => {
      out.push({
        word: e.word,
        count: e.count,
        col: ci,
        x,
        cy: L.idxTop + L.headH + ri * L.rowH + L.rowH / 2
      })
    })
  })
  return out
})

// ── 取词镜 ──
// 镜片必须留在索引册页的版口里，且整圈都得在画布内（不然 .kd-spread 的
// overflow:hidden 会把镜圈切掉半个）。16:9 下这两条护栏恒不生效，clamp 结果与改动前逐值相同。
// ⚠️ 护栏要写在 lensX/lensY 之前：首帧的初值也必须过一遍 clamp。
// 经折装的第一栏左边缘只离画布 46px，直接用「栏左 + 36」当初值会让镜圈探出画布 2px，
// 而 placeLens 要等到 onMounted 才纠正。
const clampLensX = (x) => {
  const L = layout.value
  const lo = Math.max(L.idxLeft + L.lensAnchorX - L.lensPadX, L.lensR + 8)
  const hi = Math.min(
    L.idxLeft + (L.cols - 1) * (L.colW + L.colGap) + L.lensAnchorX + L.lensPadX,
    DW.value - L.lensR - 8
  )
  return clamp(x, Math.min(lo, hi), Math.max(lo, hi))
}

const clampLensY = (y) => {
  const L = layout.value
  const lo = Math.max(L.idxTop + L.lensPadY, L.lensR + 8)
  const hi = Math.min(
    L.idxTop + L.headH + L.lensRows * L.rowH + L.lensPadY,
    DH.value - L.lensR - 8
  )
  return clamp(y, Math.min(lo, hi), Math.max(lo, hi))
}

const lensX = ref(clampLensX(layout.value.idxLeft + layout.value.lensAnchorX))
const lensY = ref(clampLensY(layout.value.idxTop + layout.value.headH + layout.value.rowH / 2))
const lensDragging = ref(false)

const lensStyle = computed(() => ({
  left: `${lensX.value - layout.value.lensR}px`,
  top: `${lensY.value - layout.value.lensR}px`
}))

// 不带动画地把镜片直接落到某个词目上（首帧 / 数据换了 / 换画幅）
const placeLens = (word) => {
  const g = rowGeometry.value.find((r) => r.word === word)
  if (!g) return
  lensX.value = clampLensX(g.x + layout.value.lensAnchorX)
  lensY.value = clampLensY(g.cy)
}

// 镜下：只取镜圈压着的那一栏。凸透镜是把镜心的东西「推开」而不是压紧，
// 所以逐行按放大后的真实行高从镜心向外累加排布——这样中心几行永远不会叠字。
const lensRows = computed(() => {
  const L = layout.value
  const cx = lensX.value
  const cy = lensY.value

  const near = []
  for (const g of rowGeometry.value) {
    if (Math.abs((g.x + L.lensAnchorX) - cx) > L.colW * 0.92) continue
    const dy = g.cy - cy
    if (Math.abs(dy) > L.lensR * 1.6) continue
    const t = clamp(dy / L.lensR, -1, 1)
    const bulge = Math.pow(Math.max(0, 1 - t * t), 1.05)
    near.push({ g, dy, bulge, scale: 1 + 0.52 * bulge })
  }
  if (near.length === 0) return []

  near.sort((a, b) => a.dy - b.dy)
  // 以离镜心最近的一行为锚，向上向下各自累加半行高
  let pivot = 0
  for (let i = 1; i < near.length; i += 1) {
    if (Math.abs(near[i].dy) < Math.abs(near[pivot].dy)) pivot = i
  }
  const y = new Array(near.length)
  y[pivot] = near[pivot].dy * 0.35 // 锚行也略向镜心靠一点，避免镜子看起来「粘」在行上
  for (let i = pivot + 1; i < near.length; i += 1) {
    y[i] = y[i - 1] + (L.rowH * near[i - 1].scale + L.rowH * near[i].scale) / 2 * 1.02
  }
  for (let i = pivot - 1; i >= 0; i -= 1) {
    y[i] = y[i + 1] - (L.rowH * near[i + 1].scale + L.rowH * near[i].scale) / 2 * 1.02
  }

  const rows = []
  near.forEach((n, i) => {
    if (Math.abs(y[i]) > L.lensR * 1.12) return
    rows.push({
      word: n.g.word,
      count: n.g.count,
      style: {
        left: `${n.g.x - (cx - L.lensR)}px`,
        top: `${L.lensR + y[i] - L.rowH / 2}px`,
        width: `${L.colW}px`,
        transform: `scale(${n.scale.toFixed(3)})`,
        transformOrigin: `${(cx - n.g.x).toFixed(1)}px 50%`,
        opacity: String(clamp(0.42 + n.bulge * 0.68, 0, 1))
      }
    })
  })
  return rows
})

const nearestRow = (x, y) => {
  const L = layout.value
  let best = null
  let bestD = Infinity
  for (const g of rowGeometry.value) {
    const dx = (g.x + L.lensAnchorX) - x
    const dy = g.cy - y
    // 纵向权重更大：镜片在一栏里上下扫是主要动作
    const d = (dx * dx) * 0.25 + dy * dy
    if (d < bestD) { bestD = d; best = g }
  }
  return best
}

// ── 选择与翻页 ──
let flipTl = null

const goToIndex = (i, { moveLens = true } = {}) => {
  const n = entries.value.length
  if (n === 0) return
  const next = ((i % n) + n) % n
  if (next === currentIndex.value) return
  currentIndex.value = next
  expanded.value = false
  focusedCite.value = -1
  flipSeq.value += 1
  if (moveLens) snapLensTo(entries.value[next].word)
  playFlip()
}

const selectByWord = (word) => {
  const i = entries.value.findIndex((e) => e.word === word)
  if (i >= 0) goToIndex(i)
}

const step = (dir) => goToIndex(currentIndex.value + dir)

const snapLensTo = (word) => {
  const g = rowGeometry.value.find((r) => r.word === word)
  if (!g) return
  const tx = clampLensX(g.x + layout.value.lensAnchorX)
  const ty = clampLensY(g.cy)
  if (props.reducedMotion || exportMode.value) {
    lensX.value = tx
    lensY.value = ty
    return
  }
  gsap.to({ x: lensX.value, y: lensY.value }, {
    x: tx,
    y: ty,
    duration: 0.44,
    ease: 'power3.out',
    onUpdate () {
      lensX.value = this.targets()[0].x
      lensY.value = this.targets()[0].y
    }
  })
}

const playFlip = () => {
  if (props.reducedMotion || exportMode.value || !leafEl.value) return
  if (flipTl) { try { flipTl.kill() } catch {} }
  flipping.value = true
  flipTl = gsap.timeline({ onComplete: () => { flipping.value = false } })
  // 铰链在中缝上：左右跨页绕右边缘转，经折装绕册页下缘翻
  const stacked = layout.value.mode === 'stack'
  flipTl.fromTo(leafEl.value,
    stacked ? { rotateX: 9, transformOrigin: '50% 100%' } : { rotateY: -9, transformOrigin: '100% 50%' },
    stacked
      ? { rotateX: 0, duration: 0.52, ease: 'power3.out', clearProps: 'transform' }
      : { rotateY: 0, duration: 0.52, ease: 'power3.out', clearProps: 'transform' })
  const q = leafEl.value.querySelectorAll('.kd-hw-word, .kd-metaline, .kd-def, .kd-cite, .kd-see')
  flipTl.fromTo(q,
    { opacity: 0, y: 10 },
    { opacity: 1, y: 0, duration: 0.4, stagger: 0.045, ease: 'power2.out', clearProps: 'opacity,transform' },
    0.06)
}

const toggleExpanded = () => {
  if (citeTotal.value <= shownCites.value.length && !expanded.value) return
  expanded.value = !expanded.value
  focusedCite.value = -1
}

const focusCite = (i) => {
  focusedCite.value = focusedCite.value === i ? -1 : i
}

// ── 指针：坐标要穿过 FitScale 的缩放换算回设计空间 ──
const designPoint = (e) => {
  const el = stageEl.value
  if (!el) return { x: 0, y: 0 }
  const rect = el.getBoundingClientRect()
  const s = fitScale.value || 1
  const offX = (rect.width - DW.value * s) / 2
  const offY = (rect.height - DH.value * s) / 2
  return {
    x: (e.clientX - rect.left - offX) / s,
    y: (e.clientY - rect.top - offY) / s
  }
}

let lensDrag = null

const onLensDown = (e) => {
  if (props.reducedMotion) return
  e.preventDefault()
  const p = designPoint(e)
  lensDrag = { id: e.pointerId, dx: lensX.value - p.x, dy: lensY.value - p.y, moved: false }
  lensDragging.value = true
  window.addEventListener('pointermove', onLensMove)
  window.addEventListener('pointerup', onLensUp)
  window.addEventListener('pointercancel', onLensUp)
}

const onLensMove = (e) => {
  if (!lensDrag || e.pointerId !== lensDrag.id) return
  const p = designPoint(e)
  const nx = p.x + lensDrag.dx
  const ny = p.y + lensDrag.dy
  if (Math.hypot(nx - lensX.value, ny - lensY.value) > 1) lensDrag.moved = true
  // 限制在索引册页的版口内，镜片不许跑到词条页去
  lensX.value = clampLensX(nx)
  lensY.value = clampLensY(ny)
}

const onLensUp = () => {
  if (!lensDrag) return
  const moved = lensDrag.moved
  lensDrag = null
  lensDragging.value = false
  window.removeEventListener('pointermove', onLensMove)
  window.removeEventListener('pointerup', onLensUp)
  window.removeEventListener('pointercancel', onLensUp)
  if (!moved) return
  const g = nearestRow(lensX.value, lensY.value)
  if (g) selectByWord(g.word)
}

// ── 整幅缩放 ──
const fitScale = ref(1)
const fitStyle = computed(() => ({
  width: `${DW.value}px`,
  height: `${DH.value}px`,
  transform: `scale(${fitScale.value})`
}))

let ro = null
const measure = () => {
  const el = stageEl.value
  if (!el) return
  const w = el.clientWidth
  const h = el.clientHeight
  if (!w || !h) return
  // 留一点版口余量，别让书顶到窗口两边被切掉
  fitScale.value = Math.min(w / DW.value, h / DH.value) * 0.94
}

// ── 入场 ──
// 在飞的入场补间：导出要跳终帧时逐条 progress(1)，让各自的 clearProps 照常收尾，
// 不留半透明 / 半位移的内联残值（killTweensOf 会把元素按死在中途那一帧）。
let entryTweens = []

const playEntrance = () => {
  entered.value = true
  entryTweens = []
  // 导出模式：跨页第一帧就是终态；元素的终值本来就是 CSS 自然值，不建补间即是落定
  if (props.reducedMotion || exportMode.value || !leafEl.value) return
  const word = leafEl.value.querySelector('.kd-hw-word')
  if (word) {
    entryTweens.push(gsap.fromTo(word,
      { opacity: 0, y: 22, letterSpacing: '0.02em' },
      { opacity: 1, y: 0, letterSpacing: '-0.045em', duration: 0.86, ease: 'power3.out', delay: 0.22, clearProps: 'letterSpacing' }))
  }
  const q = leafEl.value.querySelectorAll('.kd-metaline, .kd-def, .kd-cite, .kd-see')
  entryTweens.push(gsap.fromTo(q,
    { opacity: 0, y: 12 },
    { opacity: 1, y: 0, duration: 0.6, stagger: 0.07, ease: 'power2.out', delay: 0.4, clearProps: 'opacity,transform' }))
  if (lensEl.value) {
    entryTweens.push(gsap.fromTo(lensEl.value,
      { opacity: 0, scale: 0.82 },
      { opacity: 1, scale: 1, duration: 0.7, ease: 'back.out(1.6)', delay: 0.72, clearProps: 'transform' }))
  }
}

/* 导出模式：把在飞的入场 / 翻页 / 镜片补间全部推到末尾。
   还原不用管：合上词典由 Card06 负责，那会把本组件整个卸掉；
   用户下次点开是一次全新挂载，onMounted 照旧从头演一遍入场。 */
watch(exportMode, (on) => {
  if (!import.meta.client || !on) return
  entryTweens.forEach((t) => { try { t.progress(1) } catch {} })
  entryTweens = []
  if (flipTl) { try { flipTl.progress(1) } catch {} }
  entered.value = true
  placeLens(entries.value[currentIndex.value]?.word)
})

onMounted(() => {
  if (!import.meta.client) return
  measure()
  if (typeof ResizeObserver !== 'undefined' && stageEl.value) {
    ro = new ResizeObserver(measure)
    ro.observe(stageEl.value)
  }
  if (hasEntries.value) {
    const w = String(props.topKeyword?.word || entries.value[0]?.word || '')
    const i = entries.value.findIndex((e) => e.word === w)
    currentIndex.value = i >= 0 ? i : 0
    placeLens(entries.value[currentIndex.value]?.word)
  }
  playEntrance()
})

watch(() => entries.value.map((e) => e.word).join('|'), () => {
  if (!import.meta.client || !hasEntries.value) return
  const w = String(props.topKeyword?.word || entries.value[0]?.word || '')
  const i = entries.value.findIndex((e) => e.word === w)
  currentIndex.value = i >= 0 ? i : 0
  expanded.value = false
  focusedCite.value = -1
  placeLens(entries.value[currentIndex.value]?.word)
})

// 换画幅 = 换画布 + 换栅格：镜片的旧坐标属于上一套版式，必须就地重新落位，
// 顺手重测一次 fitScale（新画布的宽高比变了）。
watch(layout, () => {
  if (!import.meta.client) return
  measure()
  placeLens(entries.value[currentIndex.value]?.word)
})

onBeforeUnmount(() => {
  ro?.disconnect?.()
  ro = null
  if (flipTl) { try { flipTl.kill() } catch {} }
  flipTl = null
  gsap.killTweensOf(leafEl.value)
  gsap.killTweensOf(lensEl.value)
  window.removeEventListener('pointermove', onLensMove)
  window.removeEventListener('pointerup', onLensUp)
  window.removeEventListener('pointercancel', onLensUp)
})
</script>

<style scoped>
.kd-root {
  position: relative;
  width: 100%;
  height: 100%;
}

.kd-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.kd-empty-card {
  border-radius: 10px;
  border: 1px solid #EDEDED;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(8px);
  padding: 16px 20px;
  text-align: center;
}

.kd-stage {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  touch-action: none;
}

.kd-fit {
  position: relative;
  flex: none;
  transform-origin: 50% 50%;
}

.kd-spread {
  --p-paper: #FAF9F6;
  --p-ink: #1A1611;
  --p-ink2: #4B4337;
  --p-ink3: #7B7264;
  --p-ink4: #A69B8A;
  --p-rule: rgba(92, 78, 56, 0.22);
  --p-red: #A8412C;
  position: absolute;
  inset: 0;
  border-radius: 10px;
  overflow: hidden;
  background: var(--p-paper);
  color: var(--p-ink);
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
  box-shadow:
    0 2px 4px rgba(84, 70, 48, 0.06),
    0 10px 22px rgba(84, 70, 48, 0.07),
    0 26px 54px rgba(84, 70, 48, 0.06),
    0 0 0 1px rgba(92, 78, 56, 0.07);
}

/* ── 纸面 ── */
.kd-paper {
  position: absolute;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(120% 90% at 22% 12%, #FEFDFA 0%, rgba(254, 253, 250, 0) 55%),
    radial-gradient(100% 80% at 84% 92%, rgba(238, 232, 220, 0.75) 0%, rgba(238, 232, 220, 0) 60%),
    linear-gradient(178deg, #FBFAF7 0%, #F7F5F0 100%);
}

.kd-sweep {
  position: absolute;
  top: -12%;
  bottom: -12%;
  left: -40%;
  right: -40%;
  z-index: 1;
  pointer-events: none;
  background: linear-gradient(101deg,
    rgba(255, 255, 255, 0) 34%,
    rgba(255, 255, 255, 0.62) 47%,
    rgba(255, 251, 240, 0.34) 55%,
    rgba(255, 255, 255, 0) 66%);
  opacity: 0.34;
  animation: kd-sweep 40s ease-in-out infinite alternate;
}

@keyframes kd-sweep {
  from { transform: translate3d(-16%, 0, 0); }
  to { transform: translate3d(16%, 0, 0); }
}

.kd-bow {
  position: absolute;
  left: 0;
  right: 0;
  height: 72px;
  z-index: 1;
  pointer-events: none;
}
.kd-bow--t { top: 0; background: linear-gradient(180deg, rgba(92, 78, 56, 0.055), rgba(92, 78, 56, 0)); }
.kd-bow--b { bottom: 0; background: linear-gradient(0deg, rgba(92, 78, 56, 0.07), rgba(92, 78, 56, 0)); }

.kd-gutter {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 742px;
  width: 116px;
  z-index: 3;
  pointer-events: none;
  background: linear-gradient(90deg,
    rgba(88, 74, 52, 0) 0%,
    rgba(88, 74, 52, 0.035) 30%,
    rgba(88, 74, 52, 0.10) 48%,
    rgba(88, 74, 52, 0.115) 50%,
    rgba(88, 74, 52, 0.035) 70%,
    rgba(88, 74, 52, 0) 100%);
}

.kd-gutter::after {
  content: '';
  position: absolute;
  left: 58px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(180deg, rgba(88, 74, 52, 0.05), rgba(88, 74, 52, 0.24) 22%, rgba(88, 74, 52, 0.24) 78%, rgba(88, 74, 52, 0.05));
}

.kd-edge {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 26px;
  z-index: 1;
  pointer-events: none;
}
.kd-edge--l {
  left: 0;
  background:
    repeating-linear-gradient(90deg, rgba(92, 78, 56, 0.10) 0 1px, rgba(92, 78, 56, 0) 1px 5px),
    linear-gradient(90deg, rgba(92, 78, 56, 0.16), rgba(92, 78, 56, 0.02) 62%, rgba(92, 78, 56, 0));
}
.kd-edge--r {
  right: 0;
  background:
    repeating-linear-gradient(270deg, rgba(92, 78, 56, 0.10) 0 1px, rgba(92, 78, 56, 0) 1px 5px),
    linear-gradient(270deg, rgba(92, 78, 56, 0.16), rgba(92, 78, 56, 0.02) 62%, rgba(92, 78, 56, 0));
}

.kd-vignette {
  position: absolute;
  inset: 0;
  z-index: 9;
  pointer-events: none;
  background: radial-gradient(128% 104% at 50% 44%, rgba(0, 0, 0, 0) 56%, rgba(74, 62, 42, 0.075) 100%);
}

/* ── 版口通用 ── */
.kd-leaf,
.kd-page-r {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 580px;
  z-index: 4;
}
.kd-leaf { left: 132px; will-change: transform; }
.kd-page-r { left: 888px; }

.kd-rule {
  position: absolute;
  left: 0;
  width: 580px;
  height: 1px;
  background: linear-gradient(90deg, var(--p-rule), rgba(92, 78, 56, 0.10) 88%, rgba(92, 78, 56, 0));
}

/* 栏线的纵坐标原本写在模板的行内 style 上，行内样式没法被画幅重排覆盖，
   所以改成类。取值与原行内样式逐像素相同：a 82 / b 360 / c 522 / d 780（左页），
   ar 82 / er 780（右页）。 */
.kd-rule--a,
.kd-rule--ar { top: 82px; }
.kd-rule--b { top: 360px; }
.kd-rule--c { top: 522px; }
.kd-rule--d,
.kd-rule--er { top: 780px; }

.kd-num { font-variant-numeric: tabular-nums; letter-spacing: 0.01em; }

.kd-rhead {
  position: absolute;
  left: 0;
  top: 56px;
  width: 580px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 11px;
  color: var(--p-ink4);
}
.kd-rh-a { letter-spacing: 0.34em; font-weight: 600; color: var(--p-ink3); }
.kd-rh-b {
  letter-spacing: 0.08em;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 左页：词条 ── */
.kd-hw {
  position: absolute;
  left: 0;
  top: 132px;
  width: 580px;
  height: 176px;
  display: flex;
  align-items: flex-end;
  gap: 24px;
  cursor: default;
  user-select: none;
}

.kd-hw-word {
  font-weight: 700;
  line-height: 0.95;
  letter-spacing: -0.045em;
  color: #14110C;
  white-space: nowrap;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55), 0 1px 2px rgba(70, 58, 40, 0.10);
}

.kd-hw-side {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding-bottom: 10px;
  flex: none;
}
.kd-chip { font-size: 17px; letter-spacing: 0.02em; color: var(--p-ink2); font-weight: 500; }
.kd-charcount { font-size: 16px; color: var(--p-ink3); }

.kd-metaline {
  position: absolute;
  left: 0;
  top: 328px;
  width: 580px;
  font-size: 13px;
  letter-spacing: 0.075em;
  color: var(--p-ink2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kd-def {
  position: absolute;
  left: 0;
  top: 384px;
  width: 580px;
  font-size: 19px;
  line-height: 1.76;
  color: #2A241C;
  letter-spacing: 0.005em;
  display: flex;
  gap: 12px;
}
.kd-def-no { color: var(--p-red); font-weight: 700; letter-spacing: 0.02em; flex: none; }
.kd-def-body {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kd-seclabel {
  position: absolute;
  left: 0;
  /* 同上：原来是模板里的行内 style="top: 500px" */
  top: 500px;
  width: 580px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.kd-seclabel-a { font-size: 11px; font-weight: 700; letter-spacing: 0.34em; color: var(--p-ink3); }
.kd-seclabel-b { font-size: 11px; letter-spacing: 0.06em; color: var(--p-ink4); }

.kd-cites {
  position: absolute;
  left: 0;
  top: 548px;
  width: 580px;
  max-height: 216px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  transform-origin: 4% 40%;
  animation: kd-ken 14s ease-in-out infinite alternate;
}

.kd-cites--expanded {
  gap: 12px;
  overflow-y: auto;
  animation: none;
  padding-right: 8px;
  scrollbar-width: thin;
}

@keyframes kd-ken {
  from { transform: scale(1) translate3d(0, 0, 0); }
  to { transform: scale(1.014) translate3d(-3px, -4px, 0); }
}

.kd-cite {
  display: flex;
  align-items: flex-start;
  gap: 15px;
  cursor: pointer;
  transition: opacity 260ms ease, transform 260ms cubic-bezier(0.32, 0.72, 0, 1);
  outline: none;
}
.kd-cite--dim { opacity: 0.34; }
.kd-cite--on { transform: translateX(-6px); }

.kd-cno {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  margin-top: 7px;
  border: 1px solid rgba(92, 78, 56, 0.30);
  color: var(--p-ink3);
  font-size: 10.5px;
  line-height: 1;
}

.kd-cq {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 18px;
  line-height: 1.64;
  color: #241E17;
  letter-spacing: 0.004em;
  max-width: 548px;
}
.kd-cq b { color: var(--p-red); font-weight: 600; }
.kd-qm { color: var(--p-ink4); }

.kd-emoji {
  display: inline-block;
  width: 1.05em;
  height: 1.05em;
  vertical-align: text-bottom;
  margin: 0 1px;
}

.kd-see {
  position: absolute;
  left: 0;
  top: 796px;
  width: 580px;
  display: flex;
  align-items: baseline;
  gap: 20px;
}
.kd-see-a { font-size: 11px; font-weight: 700; letter-spacing: 0.34em; color: var(--p-ink3); flex: none; }
.kd-see-b {
  font-size: 13px;
  letter-spacing: 0.04em;
  color: var(--p-ink2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kd-see-w { cursor: pointer; border-bottom: 1px solid transparent; transition: border-color 160ms ease, color 160ms ease; }
.kd-see-w:hover, .kd-see-w:focus-visible { color: var(--p-red); border-bottom-color: rgba(168, 65, 44, 0.4); outline: none; }
.kd-see-sep { color: var(--p-ink4); }

.kd-folio {
  position: absolute;
  top: 842px;
  font-size: 12px;
  letter-spacing: 0.14em;
  color: var(--p-ink4);
}
.kd-folio--l { left: 0; }
.kd-folio--r { left: 0; width: 580px; text-align: right; }

.kd-catch {
  position: absolute;
  left: 0;
  top: 842px;
  width: 580px;
  text-align: right;
  font-size: 11px;
  letter-spacing: 0.22em;
  color: var(--p-ink4);
}

/* 翻页角 */
.kd-leaf--flipping { will-change: transform, opacity; }

/* ── 右页：索引 ── */
.kd-booktitle {
  position: absolute;
  left: 0;
  top: 116px;
  width: 580px;
  font-size: 25px;
  font-weight: 700;
  line-height: 1.5;
  letter-spacing: 0.01em;
  color: #14110C;
}

.kd-preface {
  position: absolute;
  left: 0;
  top: 158px;
  width: 580px;
  margin: 0;
  font-size: 13.5px;
  line-height: 1.78;
  color: var(--p-ink2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.kd-em { color: var(--p-red); font-weight: 600; }

.kd-fanli {
  position: absolute;
  left: 0;
  top: 214px;
  width: 580px;
  font-size: 11px;
  line-height: 1.8;
  color: var(--p-ink3);
  letter-spacing: 0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kd-fanli-t { font-weight: 700; letter-spacing: 0.24em; color: var(--p-ink2); margin-right: 10px; }

.kd-idx {
  position: absolute;
  left: 0;
  top: 250px;
  width: 580px;
  display: flex;
  gap: 36px;
}
.kd-col { width: 272px; flex: none; }

.kd-chead {
  position: relative;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  height: 24px;
  margin-bottom: 34px;
}
.kd-chead::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, var(--p-rule), rgba(92, 78, 56, 0.10) 88%, rgba(92, 78, 56, 0));
}
.kd-chead-a, .kd-chead-b { font-size: 10px; letter-spacing: 0.22em; color: var(--p-ink4); font-weight: 600; }

.kd-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  height: 28px;
  line-height: 28px;
  font-size: 13px;
  cursor: pointer;
  outline: none;
  transition: color 160ms ease;
}
.kd-row:hover .kd-w,
.kd-row:focus-visible .kd-w { color: var(--p-red); }

.kd-w {
  color: var(--p-ink);
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.01em;
}
.kd-ld {
  flex: 1 1 auto;
  min-width: 14px;
  height: 1.4px;
  align-self: flex-end;
  margin-bottom: 8px;
  background-image: linear-gradient(90deg, rgba(120, 106, 84, 0.42) 1.4px, rgba(0, 0, 0, 0) 1.4px);
  background-size: 6px 1.4px;
  background-repeat: repeat-x;
}
.kd-ct { flex: none; min-width: 30px; text-align: right; font-size: 12.5px; color: var(--p-ink2); }
.kd-row--cur .kd-w { color: var(--p-red); font-weight: 600; }
.kd-row--cur .kd-ct { color: var(--p-red); font-weight: 600; }

.kd-colophon {
  position: absolute;
  left: 0;
  top: 796px;
  width: 580px;
  font-size: 12px;
  letter-spacing: 0.045em;
  color: var(--p-ink3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 玻璃取词镜 ── */
.kd-lens {
  position: absolute;
  width: 168px;
  height: 168px;
  border-radius: 50%;
  overflow: hidden;
  z-index: 6;
  cursor: grab;
  outline: none;
  background:
    radial-gradient(70% 70% at 42% 34%, rgba(255, 253, 246, 0.50), rgba(255, 253, 246, 0) 74%),
    radial-gradient(circle at 50% 50%, rgba(150, 132, 102, 0) 56%, rgba(150, 132, 102, 0.10) 84%, rgba(112, 94, 66, 0.22) 100%),
    linear-gradient(154deg, #FBFAF6 0%, #F6F4EE 100%);
  box-shadow:
    0 2px 3px rgba(84, 70, 48, 0.075),
    0 6px 12px rgba(84, 70, 48, 0.075),
    0 14px 26px rgba(84, 70, 48, 0.07),
    0 26px 46px rgba(84, 70, 48, 0.055),
    0 46px 78px rgba(84, 70, 48, 0.05),
    0 0 0 0.5px rgba(92, 78, 56, 0.42);
  transition: box-shadow 200ms ease;
}
.kd-lens--drag { cursor: grabbing; }
.kd-lens:focus-visible { box-shadow: 0 0 0 3px rgba(168, 65, 44, 0.35), 0 26px 46px rgba(84, 70, 48, 0.10); }

.kd-lens-mag {
  position: absolute;
  inset: 0;
  -webkit-mask-image: radial-gradient(circle at 50% 50%, #000 82%, rgba(0, 0, 0, 0.62) 93%, rgba(0, 0, 0, 0.16) 98%, rgba(0, 0, 0, 0) 100%);
  mask-image: radial-gradient(circle at 50% 50%, #000 82%, rgba(0, 0, 0, 0.62) 93%, rgba(0, 0, 0, 0.16) 98%, rgba(0, 0, 0, 0) 100%);
}

.kd-lrow {
  position: absolute;
  cursor: inherit;
  text-shadow: -0.35px 0 rgba(72, 140, 230, 0.34), 0.35px 0 rgba(226, 132, 66, 0.34);
}
.kd-lens .kd-ld {
  background-image: linear-gradient(90deg, rgba(120, 106, 84, 0.58) 1.4px, rgba(0, 0, 0, 0) 1.4px);
}

.kd-lens-body {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  background: radial-gradient(70% 70% at 33% 25%, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0) 58%);
  box-shadow:
    inset 0 0 0 0.5px rgba(255, 255, 255, 0.92),
    inset 0 1.5px 2px rgba(255, 255, 255, 0.75),
    inset 0 -1.5px 2px rgba(255, 255, 255, 0.45),
    inset 8px 10px 24px rgba(255, 255, 255, 0.26),
    inset -10px -12px 28px rgba(92, 78, 56, 0.09),
    inset 0 0 30px rgba(92, 78, 56, 0.05);
}

.kd-lens-caustic {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  background: radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0) 0 74%, rgba(255, 252, 242, 0.95) 86%, rgba(255, 255, 255, 0) 95%);
  -webkit-mask-image: conic-gradient(from 38deg, #000 0deg, #000 60deg, rgba(0, 0, 0, 0) 98deg, rgba(0, 0, 0, 0) 360deg);
  mask-image: conic-gradient(from 38deg, #000 0deg, #000 60deg, rgba(0, 0, 0, 0) 98deg, rgba(0, 0, 0, 0) 360deg);
  filter: blur(2.5px);
}

.kd-lens-chroma {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  background: conic-gradient(from 196deg,
    rgba(78, 144, 232, 0.46) 0deg,
    rgba(78, 144, 232, 0.10) 46deg,
    rgba(255, 255, 255, 0) 108deg,
    rgba(255, 255, 255, 0) 214deg,
    rgba(228, 132, 64, 0.14) 286deg,
    rgba(228, 132, 64, 0.48) 346deg,
    rgba(78, 144, 232, 0.46) 360deg);
  -webkit-mask-image: radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0) 83%, #000 93%, #000 100%);
  mask-image: radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0) 83%, #000 93%, #000 100%);
  animation: kd-rim 7s ease-in-out infinite alternate;
}
@keyframes kd-rim { from { opacity: 0.62; } to { opacity: 1; } }

.kd-lens-spec {
  position: absolute;
  left: 22px;
  top: 17px;
  width: 60px;
  height: 26px;
  border-radius: 50%;
  pointer-events: none;
  background: linear-gradient(158deg, rgba(255, 255, 255, 0.85), rgba(255, 255, 255, 0.10) 58%, rgba(255, 255, 255, 0));
  filter: blur(2.5px);
  transform: rotate(-13deg);
  animation: kd-spec 9s ease-in-out infinite alternate;
}
@keyframes kd-spec {
  from { transform: rotate(-13deg) translate3d(0, 0, 0); opacity: 0.8; }
  to { transform: rotate(-13deg) translate3d(7px, 5px, 0); opacity: 1; }
}

/* 翻走这一页时停掉常驻动效，不空转 */
.kd-stage--paused .kd-sweep,
.kd-stage--paused .kd-cites,
.kd-stage--paused .kd-lens-chroma,
.kd-stage--paused .kd-lens-spec { animation-play-state: paused; }

.kd-stage--rm .kd-sweep,
.kd-stage--rm .kd-cites,
.kd-stage--rm .kd-lens-chroma,
.kd-stage--rm .kd-lens-spec { animation: none; }

@media (prefers-reduced-motion: reduce) {
  .kd-sweep, .kd-cites, .kd-lens-chroma, .kd-lens-spec { animation: none; }
  .kd-cite { transition: none; }
}

/* ============================================================================
   画幅重排 · 非 16:9 四档
   landscape 1386×1040 / square 1200×1200 / portrait 1040×1386 · 1074×1342 / tall 900×1600

   ⚠️ landscape（4:3）必须在这张名单里：它的画布是 1386×1040，而上面那套原始声明是
   按 1600×900 写死的（右页 left:888 + width:580 = 1468），照抄过去右页会被裁掉 82px，
   连第二栏的例数都在画布外面。

   面积恒定 ⇒ 同一套字号、行高、镜片直径在每个画幅里都装得下，换的只是版式：
     landscape / square / portrait  左右跨页：版心与中缝按画布宽度重算
                      （1386 宽仍是 580 版心；1200/1074/1040 宽收到 516/453/436）。
                      版心窄于 560 时，词头的〔词类〕与字数从词的右边挪到词的下面，
                      于是词头可用宽度反而与 16:9 的 438 持平甚至更大。
     tall             左右跨页 → 上下叠页（经折装）：上册页立词条，中缝转成横向折痕带，
                      下册页排索引；32 条词目由 2 栏 × 16 行转成 3 栏 × 11 行，一次排完。
   版式（跨页 / 经折装）不由 tier 决定，而由画布算出来，所以这里凡是跟版式有关的
   声明一律挂 .kd-spread--stack / .kd-spread--sideunder 这两个修饰类；
   16:9 两个类都不挂，也不读任何 --kd-* 变量，逐像素零回归。
   所有几何量由 lib/wrapped-dictionary-layout.js 算出、经 .kd-spread 上的 --kd-* 变量下发，
   这里只负责「谁读哪个变量」——CSS 与取词镜的光学共用同一个真值源。
   ========================================================================== */

/* ---------- 两张册页的位置与开本 ---------- */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-leaf {
  left: var(--kd-leaf-x);
  top: var(--kd-leaf-y);
  bottom: auto;
  height: var(--kd-leaf-h);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-page-r {
  left: var(--kd-pr-x);
  top: var(--kd-pr-y);
  bottom: auto;
  height: var(--kd-pr-h);
}

/* 版心宽度：原版所有写死的 580px 一起改口径。
   ⚠️ 这里必须把选择器一条条摊开写：Vue 的 scoped 改写在「末尾复合选择器是 :is()」时
   会把 [data-v] 塞进最前面那个 :is()（即挂到 .wr-stage 上），规则会永远不命中。 */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-leaf,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-page-r,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rhead,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-hw,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-metaline,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-def,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-seclabel,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-cites,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-see,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-folio--r,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-catch,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-booktitle,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-preface,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-fanli,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-idx,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-colophon {
  width: var(--kd-pw);
}

/* ---------- 词条页（16:9 的左页 / 经折装的上册页） ---------- */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rhead { top: var(--kd-t-rhead); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule--a { top: var(--kd-t-rule-a); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule--b { top: var(--kd-t-rule-b); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule--c { top: var(--kd-t-rule-c); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule--d { top: var(--kd-t-rule-d); }

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-hw {
  top: var(--kd-t-hw);
  height: var(--kd-h-hw);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-metaline { top: var(--kd-t-meta); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-def { top: var(--kd-t-def); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-seclabel { top: var(--kd-t-seclabel); }

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-cites {
  top: var(--kd-t-cites);
  max-height: var(--kd-h-cites);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-see { top: var(--kd-t-see); }

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-folio--l,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-catch {
  top: var(--kd-t-folio);
}

/* ---------- 索引页（16:9 的右页 / 经折装的下册页） ---------- */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule--ar { top: var(--kd-t-rule-ar); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rule--er { top: var(--kd-t-rule-er); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-booktitle { top: var(--kd-t-btitle); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-preface { top: var(--kd-t-preface); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-fanli { top: var(--kd-t-fanli); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-colophon { top: var(--kd-t-colophon); }
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-folio--r { top: var(--kd-t-folio-r); }

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-idx {
  top: var(--kd-t-idx);
  gap: var(--kd-col-gap);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-col {
  width: var(--kd-col-w);
}

/* ---------- 放开 16:9 里为了保住栏宽而设的截断（行高/字号一律不动） ---------- */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rh-b {
  max-width: calc(var(--kd-pw) - 200px);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rh-b,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-metaline,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-fanli,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-colophon,
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-see-b {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-w {
  max-width: var(--kd-word-max);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-cq {
  max-width: var(--kd-cite-max);
}

/* ---------- 截断行数：一律读算出来的行数，只放开不收紧 ----------
   页越高，释义 / 书证 / 小序能给的行数越多；16:9 不读这些变量，仍是 3 / 2 / 2 行。 */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-def-body {
  -webkit-line-clamp: var(--kd-def-lines);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-cq {
  -webkit-line-clamp: var(--kd-cite-lines);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-preface {
  -webkit-line-clamp: var(--kd-preface-lines);
}

/* ---------- 左右跨页：中缝仍是竖的，位置与宽度按画布重算 ---------- */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-gutter {
  left: var(--kd-gutter-x);
  width: var(--kd-gutter-w);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-gutter::after {
  left: var(--kd-gutter-line);
}

/* ---------- 版心窄于 560：词头的〔词类〕与字数改叠在词下面 ----------
   挂类而不是挂档位：1:1、3:4、4:5 都会走到这一支，将来画布再变也不用改选择器。
   词头盒的高度（--kd-h-hw）已经把多出来的这一行算进去了。 */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-spread--sideunder .kd-hw {
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 12px;
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-spread--sideunder .kd-hw-side {
  padding-bottom: 0;
}

/* ============================================================================
   竖幅 / 方幅的正文字号（square · portrait · tall）

   这一档画布短边只有 900~1200，成品是给手机看的：16:9 那套 10 / 10.5 / 11px 的
   小字换算到竖幅成品里只剩四五个屏幕像素，读不出来。所以这里**只提字号**，
   不动任何一个由 lib/wrapped-dictionary-layout.js 算出来的几何量：
     · .kd-chead 盒高恒 24 + 34 = IDX_HEAD_H(58)，字长大不撑高；
     · .kd-row 行高恒 28（line-height 28px），16px 的词目仍是一行一格；
     · 凡例 / 小序的行高增量（各 ≤ 3px）落在版式引擎预留的 8~16px 行间距里。
   16:9 与 4:3（landscape）不挂这一段，字号一个都不动。
   ========================================================================== */
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-chead-a,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-chead-b {
  font-size: 12.5px;
}

:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-rhead,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-seclabel-a,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-seclabel-b,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-see-a,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-catch,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-fanli {
  font-size: 12.5px;
}

:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-folio,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-colophon {
  font-size: 13px;
}

/* 书证序号：圈随字长大，圈在 .kd-cite 里是 flex-start 对齐的小件，不影响行高 */
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-cno {
  width: 20px;
  height: 20px;
  margin-top: 6px;
  font-size: 12.5px;
}

/* 索引正文：这一页 32 行词目就是版面的主体，字号定这一幅读不读得下去 */
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-row {
  font-size: 16px;
}
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-ct {
  font-size: 16px;
  min-width: 38px;
}

:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-metaline,
:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-see-b {
  font-size: 15px;
}

:is([data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-preface {
  font-size: 15px;
}

/* ---------- 经折装（上下叠页）：中缝转成横向折痕带 ---------- */
:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-spread--stack .kd-gutter {
  left: var(--kd-gutter-x);
  top: var(--kd-gutter-y);
  bottom: auto;
  width: var(--kd-gutter-w);
  height: var(--kd-gutter-h);
  background: linear-gradient(180deg,
    rgba(88, 74, 52, 0) 0%,
    rgba(88, 74, 52, 0.035) 30%,
    rgba(88, 74, 52, 0.10) 48%,
    rgba(88, 74, 52, 0.115) 50%,
    rgba(88, 74, 52, 0.035) 70%,
    rgba(88, 74, 52, 0) 100%);
}

:is([data-frame-tier="landscape"], [data-frame-tier="square"], [data-frame-tier="portrait"], [data-frame-tier="tall"]) .kd-spread--stack .kd-gutter::after {
  left: 0;
  top: var(--kd-gutter-line);
  bottom: auto;
  width: 100%;
  height: 1px;
  background: linear-gradient(90deg, rgba(88, 74, 52, 0.05), rgba(88, 74, 52, 0.24) 22%, rgba(88, 74, 52, 0.24) 78%, rgba(88, 74, 52, 0.05));
}
</style>
