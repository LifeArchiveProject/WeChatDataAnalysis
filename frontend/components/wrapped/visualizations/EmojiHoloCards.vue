<template>
  <div
    ref="rootEl"
    class="hc-root"
    :class="[
      `hc-root--${phase}`,
      ceremonyIdx >= 0 ? 'hc-root--stagelit' : '',
      chargeTier ? `hc-root--charge hc-root--charge-${chargeTier}` : ''
    ]"
    :style="{ '--hero': heroColor, '--heroGlow': heroGlow, '--cb': cardBackUri, '--grain': grain }"
  >
    <div class="hc-field" aria-hidden="true" />

    <div v-if="!hasData" class="hc-empty">
      <div class="hc-empty-box">
        <div class="wrapped-title text-base text-white/90">今年没开出几张表情卡</div>
        <div class="mt-1 wrapped-body text-sm text-white/45">聊天里几乎没有表情包，卡包是空的。</div>
      </div>
    </div>

    <template v-else>
      <!-- 卡包 → 卡组 -->
      <div
        ref="stageEl"
        class="hc-stage"
        data-deck-nodrag
        @pointerdown="onStagePointerDown"
        @pointermove="onStagePointerMove"
        @pointerup="onStagePointerUp"
        @pointercancel="onStagePointerUp"
        @pointerleave="onStageLeave"
      >
        <!-- 封装卡包：真 3D 物体，横向拖动撕开，撕口跟着手指走 -->
        <div
          v-if="packVisible"
          class="hc-pack3d"
          :class="{ 'hc-pack3d--out': packLeaving }"
          @pointerdown="onPackPointerDown"
        >
          <EmojiPack3D
            ref="pack3d"
            :year="year"
            :sent-count="sentStickerCount"
            :type-count="uniqueTypeCount"
            :card-count="cards.length"
            :hero-color="heroColor"
            :next-src="nextPeekSrc"
            :active="active"
            :reduced-motion="reducedMotion"
            @opened="onPackOpened"
          />

          <!-- 撕口指引：封条上已经印着「沿封口撕开」，这里只在犹豫时轻声补一句怎么撕 -->
          <div v-if="showGuide" class="hc-guide" aria-hidden="true">
            <span class="hc-guide-text wrapped-label">按住 · 向右拖</span>
          </div>
        </div>

        <!-- 点开卡片看详细叙事：平时卡面放不下的内容都在这里。
             teleport 到舞台 portal 而不是 body —— 舞台带 transform，是 fixed 后代的包含块，
             于是这一层自动铺满舞台盒并随舞台缩放，不会溢出信箱边界。 -->
        <Teleport :to="stage.portalTarget.value">
          <transition name="detail-fade">
            <div v-if="detail" class="hc-detail" :class="{ 'wrapped-privacy': privacyMode }" @click.self="detailIdx = -1">
              <div class="hc-detail-panel">
                <button type="button" class="hc-detail-close" @click="detailIdx = -1">✕</button>

                <div class="hc-detail-head">
                  <span class="hc-detail-tag wrapped-label" :style="{ '--rc': detail.rarity.color }">
                    {{ detail.rarity.label }}
                  </span>
                  <span class="hc-detail-kind wrapped-label">
                    {{ detail.kind === 'file' ? detail.title : `${detail.rarity.name} · ${padNo(detail.rank, 3)}/${uniqueTypeCount}` }}
                  </span>
                </div>

                <div class="hc-detail-body">
                  <!-- 表情卡：大图 + 叙事 -->
                  <template v-if="detail.kind !== 'file'">
                    <div class="hc-detail-art">
                      <img v-if="detail.src" :src="detail.src" alt="" draggable="false" class="wrapped-privacy-sticker" />
                    </div>
                    <div class="hc-detail-text">
                      <p class="hc-detail-lead wrapped-body">
                        这张表情你今年发了
                        <b class="wrapped-number">{{ fmt(detail.count) }}</b> 次，
                        占你全年表情量的 <b class="wrapped-number">{{ ratioText(detail) }}</b>，
                        在 <b class="wrapped-number">{{ uniqueTypeCount }}</b> 种表情里排第
                        <b class="wrapped-number">{{ detail.rank }}</b>。
                      </p>
                      <p v-if="detail.ownerName" class="hc-detail-lead wrapped-body">
                        它最常被你发给
                        <b class="wrapped-privacy-name">{{ detail.ownerName }}</b>。
                      </p>
                      <p class="hc-detail-lead wrapped-body">
                        <template v-if="detail.isNew">这是 <b>{{ year }}</b> 年才进你表情库的新面孔——卡面左下的「首刷」印记就是它。</template>
                        <template v-else-if="detail.revived">它沉睡了 <b class="wrapped-number">{{ fmt(detail.gapDays) }}</b> 天后又被你翻了出来，所以做成了复刻版：图不闪、其余闪。</template>
                        <template v-else>它是你表情库里的常驻选手，全年都在被使用。</template>
                      </p>
                    </div>
                  </template>

                  <!-- 能量卡：把所有小黄脸和 Emoji 都列出来 -->
                  <template v-else-if="detail.file === 'energy'">
                    <div class="hc-detail-text hc-detail-text--full">
                      <p class="hc-detail-lead wrapped-body">
                        除了表情包，你还在文字里按下了
                        <b class="wrapped-number">{{ fmt(energyTotal) }}</b> 次小黄脸和 Emoji，
                        占全年发言的 <b class="wrapped-number">{{ stickerSharePct }}%</b>。下面是全部。
                      </p>
                      <ul class="hc-detail-list">
                        <li v-for="e in allEmojiRows" :key="e.id">
                          <span class="hc-detail-glyph">
                            <img v-if="e.src" :src="e.src" alt="" class="wrapped-privacy-sticker" />
                            <span v-else>{{ e.label }}</span>
                          </span>
                          <span class="hc-detail-name wrapped-body">{{ e.label }}</span>
                          <span class="hc-detail-bar"><i :style="{ width: `${e.pct}%`, background: e.kind === 'uni' ? '#6FB6FF' : '#4ADE80' }" /></span>
                          <span class="hc-detail-num wrapped-number">{{ fmt(e.count) }}</span>
                        </li>
                      </ul>
                    </div>
                  </template>

                  <!-- 时段卡：24 小时 + 星期，都带具体数字 -->
                  <template v-else-if="detail.file === 'time'">
                    <div class="hc-detail-text hc-detail-text--full">
                      <p class="hc-detail-lead wrapped-body">
                        你在 <b class="wrapped-number">{{ fmt(stickerActiveDays) }}</b> 个日子里发过表情，
                        日均 <b class="wrapped-number">{{ perDayText }}</b> 张；
                        <template v-if="peakHour !== null">
                          最密集的时刻是 <b>{{ peakWeekdayName }} {{ pad(peakHour) }}:00</b>。
                        </template>
                      </p>
                      <div class="hc-detail-k wrapped-label">一天 24 小时</div>
                      <div class="hc-detail-hours">
                        <span v-for="(n, h) in hourCounts" :key="`dh${h}`" :class="{ 'is-peak': h === peakHour }">
                          <i :style="{ height: `${Math.max(4, Math.round((n / hourMax) * 100))}%` }" />
                          <em v-if="h % 3 === 0" class="wrapped-label">{{ h }}</em>
                        </span>
                      </div>
                      <div class="hc-detail-k wrapped-label">一周七天</div>
                      <ul class="hc-detail-list">
                        <li v-for="(n, w) in weekdayCounts" :key="`dw${w}`">
                          <span class="hc-detail-name wrapped-body">周{{ WEEK_SHORT[w] }}</span>
                          <span class="hc-detail-bar">
                            <i :style="{ width: `${Math.round((n / weekdayMax) * 100)}%`, background: w === peakWeekday ? '#FFCE4A' : '#4ADE80' }" />
                          </span>
                          <span class="hc-detail-num wrapped-number">{{ fmt(n) }}</span>
                        </li>
                      </ul>
                    </div>
                  </template>

                  <!-- 对手卡 -->
                  <template v-else>
                    <div class="hc-detail-art">
                      <img v-if="battlePartner?.avatar" :src="battlePartner.avatar" alt="" class="hc-detail-avatar wrapped-privacy-avatar" />
                    </div>
                    <div class="hc-detail-text">
                      <p class="hc-detail-lead wrapped-body">
                        <b class="wrapped-privacy-name">{{ battlePartner?.name }}</b>
                        是今年和你互甩表情最多的人，你朝 TA 发了
                        <b class="wrapped-number">{{ fmt(battlePartner?.count) }}</b> 张，
                        占你全年表情量的
                        <b class="wrapped-number">{{ rivalSharePct }}%</b>。
                      </p>
                      <p class="hc-detail-lead wrapped-body">
                        换句话说，你每发出 <b class="wrapped-number">{{ rivalEveryN }}</b> 张表情，就有一张是发给 TA 的。
                      </p>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </transition>
        </Teleport>

        <!-- 全年表情涌出：喷洒范围 = 舞台盒（画幅之内），不是浏览器窗口 -->
        <Teleport :to="stage.portalTarget.value">
          <div v-if="phase === 'pour'" class="hc-sift" :class="{ 'wrapped-privacy': privacyMode }" aria-hidden="true">
            <img
              v-for="t in siftThumbs"
              :key="t.id"
              :ref="(el) => registerThumb(t.id, el)"
              class="hc-thumb wrapped-privacy-sticker"
              :src="t.src"
              alt=""
              draggable="false"
            />
          </div>
        </Teleport>

        <!-- 年度卡池叠：倾泻散尽后，这叠真正的年度卡从撕开的袋口滑出来落在台面上；
             发牌一开始整副真卡原位接管，装饰叠同帧退场 -->
        <div
          v-if="phase === 'pour' || phase === 'draw'"
          ref="stackEl"
          class="hc-stack"
          :class="{ 'hc-stack--on': stackOn }"
          aria-hidden="true"
        >
          <div ref="stackPileEl" class="hc-stack-pile">
            <div
              v-for="nLayer in 6"
              v-show="nLayer <= stackLayers"
              :key="`sl-${nLayer}`"
              class="hc-stack-card"
              :class="{ 'is-top': nLayer === stackLayers && !deckUnder }"
              :style="{ '--i': nLayer }"
            />
            <span ref="stackFlashEl" class="hc-stack-flash" />
          </div>
          <span class="hc-stack-shadow" />
          <div class="hc-stack-label wrapped-label" :class="{ 'is-on': stackLabelOn }">
            年度卡池 · {{ cards.length }} 张
          </div>
        </div>

        <!-- 开卡期的舞台灯效：UR 蓄势漏光 / 翻开一瞬的全场曝光 / 稀有度色火花 -->
        <div v-if="leakOn" class="hc-leak" :style="{ '--rc': chargeColor }" aria-hidden="true" />
        <div v-show="phase === 'draw'" ref="sparkEl" class="hc-sparkbox" :style="{ '--rc': chargeColor }" aria-hidden="true" />
        <div v-show="phase === 'draw'" ref="flashEl" class="hc-flash" aria-hidden="true" />

        <!-- 翻开后的那句话 -->
        <div v-if="revealCap" class="hc-cap" :class="{ 'hc-cap--on': capOn }">
          <div class="hc-cap-t wrapped-title">{{ revealCap.title }}</div>
          <div class="hc-cap-l wrapped-body">{{ revealCap.line }}</div>
        </div>
        <div v-if="flipHint" class="hc-taphint wrapped-label" aria-hidden="true">轻点，翻开</div>

        <!-- 壁龛陈列墙：开卡期是暗着的空墙（空 C 位基座就是悬念），开完灯光亮起 -->
        <div
          class="hc-fan"
          :class="{ 'hc-fan--on': fanVisible, 'hc-fan--lit': phase === 'gallery' }"
          :style="{ '--cols': gridCols, '--heroCol': heroCol }"
        >
          <div
            v-for="(c, i) in cards"
            :key="c.id"
            class="hc-slot"
            :class="{
              'hc-slot--hero': i === heroIndex,
              'is-in': !!shown[c.id] || phase === 'gallery',
              'is-ceremony': i === ceremonyIdx
            }"
            :style="{ '--rc': c.rarity.color, '--rg': c.rarity.glow }"
            @click="onCardClick(i, $event)"
          >
            <span class="hc-niche" aria-hidden="true" />
            <!-- 入场动画单独占一层：扇形定位走 CSS transform，gsap 不会把它覆盖掉 -->
            <div :ref="(el) => registerCard(i, el)" class="hc-burst">
            <div
              class="hc-card"
              :class="[
                `hc-card--${c.rarity.code.toLowerCase()}`,
                { 'hc-card--focus': i === focus, 'hc-card--rv': c.revived }
              ]"
              :style="cardVars(i, c)"
              @pointermove="onCardPointerMove(i, $event)"
              @pointerleave="onCardPointerLeave(i)"
            >
              <div class="hc-face hc-face--front">
                <div class="hc-frame">
                  <header class="hc-head">
                    <span class="hc-rarity wrapped-label">{{ c.rarity.label }}</span>
                    <span v-if="c.kind === 'file'" class="hc-no wrapped-label">{{ c.title }}</span>
                    <span v-else class="hc-no wrapped-number">{{ padNo(c.rank, 3) }}/{{ uniqueTypeCount }}</span>
                  </header>

                  <!-- 表情卡 -->
                  <template v-if="c.kind !== 'file'">
                    <div class="hc-art">
                      <img
                        v-if="imgOk[c.id] !== false"
                        :src="c.src"
                        class="hc-art-img wrapped-privacy-sticker"
                        alt=""
                        draggable="false"
                        @error="imgOk[c.id] = false"
                      />
                      <span v-else class="hc-art-miss wrapped-label">图片已失效</span>
                    </div>

                    <!-- 首刷印记：位置照搬真实卡牌的 1st Edition（图窗下方靠左） -->
                    <div class="hc-marks">
                      <span v-if="c.isNew" class="hc-1st">
                        <i class="hc-1st-o">1</i>
                        <em class="wrapped-label">首刷</em>
                      </span>
                      <span v-else-if="c.revived" class="hc-rv-mark wrapped-label">★ 复刻版</span>
                    </div>

                    <div class="hc-plate">
                      <!-- 自定义表情多半没有名字，就用「常发给谁」当卡名，比「无名表情」有信息量 -->
                      <div class="hc-name wrapped-title">
                        <template v-if="c.label">{{ c.label }}</template>
                        <template v-else-if="c.ownerName">
                          常发给 <span class="wrapped-privacy-name">{{ c.ownerName }}</span>
                        </template>
                        <template v-else>{{ c.rarity.name }}</template>
                      </div>
                      <div class="hc-bar"><span class="hc-bar-fill" :style="{ width: `${barPct(c)}%` }" /></div>
                    </div>

                    <footer class="hc-foot">
                      <span class="hc-count wrapped-number">{{ fmt(c.count) }}</span>
                      <span class="hc-count-u wrapped-label">次</span>
                      <span class="hc-share wrapped-label">{{ c.slotNote || `占年度 ${ratioText(c)}` }}</span>
                    </footer>
                  </template>

                  <!-- 档案卡：和表情卡同一套框，只是画面换成数据 -->
                  <template v-else>
                    <!-- 档案卡也是「一张画 + 名条 + 底注」，和表情卡完全同构 -->
                    <div class="hc-art">
                      <!-- 能量卡：把最高频的小黄脸当元素符号放大 -->
                      <img
                        v-if="c.file === 'energy' && c.artSrc"
                        :src="c.artSrc"
                        class="hc-art-img"
                        alt=""
                        draggable="false"
                      />

                      <!-- 时段卡：24 小时表盘，刻度按热度深浅，指针指向高峰 -->
                      <svg v-else-if="c.file === 'time'" class="hc-dial" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="37" class="hc-dial-ring" />
                        <line
                          v-for="t in dialTicks"
                          :key="`d${t.h}`"
                          :x1="t.x1" :y1="t.y1" :x2="t.x2" :y2="t.y2"
                          class="hc-dial-tick"
                          :class="{ 'is-peak': t.h === peakHour }"
                          :style="{ opacity: t.o }"
                        />
                        <line
                          v-if="dialHand"
                          x1="50" y1="50" :x2="dialHand.x" :y2="dialHand.y"
                          class="hc-dial-hand"
                        />
                        <circle cx="50" cy="50" r="3.4" class="hc-dial-hub" />
                      </svg>

                      <!-- 对手卡：头像做成圆形肖像章 -->
                      <span v-else class="hc-portrait wrapped-privacy-avatar">
                        <img
                          v-if="battlePartner?.avatar && imgOk['bp'] !== false"
                          :src="battlePartner.avatar"
                          alt=""
                          @error="imgOk['bp'] = false"
                        />
                        <span v-else class="wrapped-number">{{ (battlePartner?.name || '?')[0] }}</span>
                      </span>
                    </div>

                    <div class="hc-plate">
                      <div class="hc-name wrapped-title">
                        <span v-if="c.file === 'rival'" class="wrapped-privacy-name">{{ c.headline }}</span>
                        <template v-else>{{ c.headline }}</template>
                      </div>
                      <div class="hc-bar"><span class="hc-bar-fill" :style="{ width: '100%' }" /></div>
                    </div>

                    <footer class="hc-foot">
                      <span class="hc-count wrapped-number">{{ c.stat }}</span>
                      <span class="hc-count-u wrapped-label">{{ c.statUnit }}</span>
                      <span class="hc-share wrapped-label">{{ c.note }}</span>
                    </footer>
                  </template>
                </div>

                <div class="hc-shine" aria-hidden="true" />
                <div class="hc-glare" aria-hidden="true" />
              </div>

              <!-- 卡背：表情卡翻过来看到的这一面，明细写在这儿 -->
              <div v-if="c.kind !== 'file'" class="hc-face hc-face--back">
                <div class="hc-back">
                  <header class="hc-back-head">
                    <span class="hc-back-tag wrapped-label">{{ c.rarity.label }}</span>
                    <span class="hc-back-no wrapped-number">{{ padNo(c.rank, 3) }}/{{ uniqueTypeCount }}</span>
                  </header>

                  <div class="hc-back-body">
                    <div class="hc-back-row">
                      <span class="hc-back-k wrapped-label">本年使用</span>
                      <span class="hc-back-v wrapped-number">{{ fmt(c.count) }} 次</span>
                    </div>
                    <div class="hc-back-row">
                      <span class="hc-back-k wrapped-label">占年度表情</span>
                      <span class="hc-back-v wrapped-number">{{ ratioText(c) }}</span>
                    </div>
                    <div class="hc-back-row">
                      <span class="hc-back-k wrapped-label">全年排名</span>
                      <span class="hc-back-v wrapped-number">第 {{ c.rank }} 位</span>
                    </div>
                    <div v-if="c.ownerName" class="hc-back-row">
                      <span class="hc-back-k wrapped-label">常发给</span>
                      <span class="hc-back-v wrapped-privacy-name">{{ c.ownerName }}</span>
                    </div>
                  </div>

                  <p class="hc-back-note wrapped-body">
                    <template v-if="c.isNew">{{ year }} 年才进你表情库的新面孔。</template>
                    <template v-else-if="c.revived">沉睡 {{ fmt(c.gapDays) }} 天后又被你翻了出来。</template>
                    <template v-else>你表情库里的常驻选手，全年都在用。</template>
                  </p>

                  <footer class="hc-back-foot wrapped-label">
                    WECHAT WRAPPED · {{ year }}
                  </footer>
                </div>
              </div>

              <!-- 开卡期的艺术卡背：雕纹版面，档案卡也有；陈列亮灯后退场，翻背才见数据 -->
              <div class="hc-face hc-face--cover">
                <span class="hc-cover-art" aria-hidden="true" />
                <header class="hc-cover-head">
                  <span class="hc-cover-tag wrapped-label" :style="{ color: c.rarity.color }">{{ c.rarity.label }}</span>
                  <span v-if="c.kind === 'file'" class="hc-cover-no wrapped-label">{{ c.title }}</span>
                  <span v-else class="hc-cover-no wrapped-number">{{ padNo(c.rank, 3) }}/{{ uniqueTypeCount }}</span>
                </header>
              </div>
            </div>
            </div>
          </div>
        </div>

        <!-- 铭牌：陈列灯亮起后落一行小字 -->
        <div class="hc-plaque" :class="{ 'hc-plaque--on': phase === 'gallery' }" aria-hidden="true">
          <span class="hc-plaque-rule" />
          <p class="hc-plaque-line wrapped-body">
            《{{ year }} 年度表情陈列》—— 有些话没打出来，都让它们替你说了。
          </p>
        </div>
      </div>

    </template>
  </div>
</template>

<script setup>
import { usePrivacyText } from '~/composables/usePrivacyText'
const { privacyMode } = usePrivacyText()
import { computed, inject, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { gsap } from 'gsap'
import EmojiPack3D from '~/components/wrapped/visualizations/EmojiPack3D.vue'
import { formatInt, padNo, rarityForRank, useEmojiUniverse } from '~/composables/useEmojiUniverse'
import { useWrappedStage } from '~/composables/useWrappedStage'

const stage = useWrappedStage()

const props = defineProps({
  card: { type: Object, required: true },
  active: { type: Boolean, default: true },
  reducedMotion: { type: Boolean, default: false }
})

const {
  year, sentStickerCount, uniqueTypeCount, newCount, newSharePct,
  revivedCount, revivedMaxGapDays, peakHour, peakWeekdayName,
  hourCounts, hourMax, battlePartner, stickerPool, poolThumbs,
  wechatEmojis, unicodeEmojis, hasData,
  stickerSharePct, weekdayCounts, peakWeekday,
  stickerActiveDays, stickerPerActiveDay
} = useEmojiUniverse(props)

const WEEK_SHORT = ['一', '二', '三', '四', '五', '六', '日']
const weekdayMax = computed(() => Math.max(1, ...weekdayCounts.value))


const fmt = formatInt
const pad = (n) => padNo(n)
// padNo 直接给模板用（收藏编号要三位）

// ---------- 卡背版面 ----------
// 双材质实体卡背：墨绿漆面（菱形涟漪暗纹）+ 实心金箔（宽框、装饰艺术角扇、八向短芒、
// 凿刻感金徽章，笑脸阴刻进金面——和卡包封面同一枚标）。发丝线全部弃用：细线在深底上只会读成网格纸。
// 生成一次 SVG data URI，多处共用：卡池叠顶牌、开卡期艺术卡背、数据卡背垫底、卡包袋口。
const cardBackDataUri = computed(() => {
  // 八向金短芒：实心小三角，不是线
  const rays = Array.from({ length: 8 }, (_, k) => {
    const a = (k / 8) * Math.PI * 2
    const c = Math.cos(a)
    const s = Math.sin(a)
    const tx = (31.5 + c * 17.4).toFixed(2)
    const ty = (42 + s * 17.4).toFixed(2)
    const bx = 31.5 + c * 13.8
    const by = 42 + s * 13.8
    const px = -s * 1.05
    const py = c * 1.05
    return `<path d="M${tx} ${ty} L${(bx + px).toFixed(2)} ${(by + py).toFixed(2)} L${(bx - px).toFixed(2)} ${(by - py).toFixed(2)} Z"/>`
  }).join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="630" height="880" viewBox="0 0 63 88">
<defs>
<radialGradient id="bg" cx="50%" cy="34%" r="95%">
<stop offset="0" stop-color="#143126"/><stop offset=".55" stop-color="#0B1E14"/><stop offset="1" stop-color="#06120C"/>
</radialGradient>
<linearGradient id="au" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#F7E3A8"/><stop offset=".45" stop-color="#E3BE6B"/><stop offset="1" stop-color="#A97F35"/>
</linearGradient>
<clipPath id="inner"><rect x="5" y="5" width="53" height="78" rx="1.8"/></clipPath>
<g id="cf">
<path d="M0 0 L8 0 L0 8 Z" fill="url(#au)"/>
<path d="M0 0 L5.2 0 L0 5.2 Z" fill="#0B1D14"/>
<path d="M0 0 L3 0 L0 3 Z" fill="url(#au)"/>
</g>
</defs>
<rect width="63" height="88" rx="4" fill="url(#bg)"/>
<g clip-path="url(#inner)">
<g transform="rotate(45 31.5 42)">
<rect x="0.5" y="11" width="62" height="62" rx="2" fill="#0D2318" stroke="#173627" stroke-width="0.25"/>
<rect x="8.5" y="19" width="46" height="46" rx="2" fill="#0B1F15" stroke="#173627" stroke-width="0.25"/>
<rect x="16.5" y="27" width="30" height="30" rx="1.5" fill="#0D2318" stroke="#173627" stroke-width="0.25"/>
<rect x="24.5" y="35" width="14" height="14" rx="1" fill="#0B1F15" stroke="#173627" stroke-width="0.25"/>
</g>
</g>
<rect x="2.6" y="2.6" width="57.8" height="82.8" rx="2.8" fill="none" stroke="url(#au)" stroke-width="1.5"/>
<rect x="5" y="5" width="53" height="78" rx="1.8" fill="none" stroke="#EFDFAF" stroke-opacity="0.38" stroke-width="0.3"/>
<use href="#cf" transform="translate(6 6)"/>
<use href="#cf" transform="translate(57 6) scale(-1 1)"/>
<use href="#cf" transform="translate(6 82) scale(1 -1)"/>
<use href="#cf" transform="translate(57 82) scale(-1 -1)"/>
<g fill="url(#au)" opacity="0.9">${rays}</g>
<g transform="rotate(45 31.5 42)">
<rect x="21.9" y="32.4" width="19.2" height="19.2" rx="1.4" fill="url(#au)" stroke="#7A5C1F" stroke-width="0.5"/>
<path d="M23.2 50.2 L23.2 33.7 L39.7 33.7" fill="none" stroke="#FBEFC4" stroke-width="0.5" stroke-opacity="0.85"/>
<path d="M39.8 33.8 L39.8 50.3 L23.3 50.3" fill="none" stroke="#6E5322" stroke-width="0.5" stroke-opacity="0.9"/>
<rect x="24.6" y="35.1" width="13.8" height="13.8" rx="0.9" fill="none" stroke="#8C6B26" stroke-width="0.32"/>
</g>
<circle cx="28.9" cy="40.7" r="1.12" fill="#11291B"/>
<circle cx="34.1" cy="40.7" r="1.12" fill="#11291B"/>
<circle cx="28.9" cy="40.45" r="1.12" fill="none" stroke="#FBEFC4" stroke-width="0.2" stroke-opacity="0.5"/>
<circle cx="34.1" cy="40.45" r="1.12" fill="none" stroke="#FBEFC4" stroke-width="0.2" stroke-opacity="0.5"/>
<path d="M27.7 44.5 Q31.5 47.8 35.3 44.5" fill="none" stroke="#11291B" stroke-width="1.12" stroke-linecap="round"/>
<path d="M27.7 44.15 Q31.5 47.45 35.3 44.15" fill="none" stroke="#FBEFC4" stroke-width="0.22" stroke-opacity="0.55"/>
<rect x="30.7" y="8.3" width="1.6" height="1.6" transform="rotate(45 31.5 9.1)" fill="url(#au)"/>
<rect x="21.5" y="8.85" width="6.5" height="0.5" rx="0.25" fill="url(#au)" opacity="0.65"/>
<rect x="35" y="8.85" width="6.5" height="0.5" rx="0.25" fill="url(#au)" opacity="0.65"/>
<rect x="30.7" y="74.9" width="1.6" height="1.6" transform="rotate(45 31.5 75.7)" fill="url(#au)"/>
<text x="31.5" y="80.4" text-anchor="middle" font-family="Menlo, SFMono-Regular, ui-monospace, monospace" font-size="2.6" letter-spacing="1.1" fill="#E9D9A8" fill-opacity="0.85">WECHAT WRAPPED</text>
<text x="31.5" y="83.9" text-anchor="middle" font-family="Menlo, SFMono-Regular, ui-monospace, monospace" font-size="1.9" letter-spacing="1.5" fill="#CBB877" fill-opacity="0.55">EMOJI PACK · ${year.value}</text>
</svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
})
const cardBackUri = computed(() => `url("${cardBackDataUri.value}")`)

// 印刷颗粒：一小片分形噪声，卡面和墙面都拿它当纸感/涂层的底
const GRAIN_URI = (() => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="180" height="180" filter="url(#n)" opacity="0.55"/></svg>'
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
})()
const grain = GRAIN_URI

const rootEl = ref(null)
const stageEl = ref(null)
const pack3d = ref(null)
const imgOk = reactive({})

// 表情卡：后端给的整个表情池全部发成卡（高频 + 今年新解锁 + 回温），一张不落。
// 稀有度只表示位次，「新解锁 / 回温」是另一条独立的维度，靠卡面角标区分。
const stickerCards = computed(() =>
  stickerPool.value.map((c) => ({
    ...c,
    rarity: rarityForRank(c.rank),
    slotNote: c.isNew
      ? `${year.value} 年新解锁`
      : (c.revived ? `沉睡 ${fmt(c.gapDays)} 天后回归` : '')
  }))
)

// 档案卡：小黄脸 / 出牌时段 / 年度对手 三张，和表情卡同一套卡框，
// 一起从卡包里发出来。之前把它们贴在屏幕底部，跟卡组毫无关系。
const FILE_TIER = { code: 'FILE', label: 'FILE', name: '年度档案', color: '#7FE3C0', glow: 'rgba(127,227,192,0.45)' }

// 24 小时表盘：每个钟点一根刻度，长短深浅按该时段热度；指针指向高峰
const dialTicks = computed(() =>
  hourCounts.value.map((v, h) => {
    const a = (h / 24) * Math.PI * 2 - Math.PI / 2
    const k = Math.max(0, Math.min(1, v / hourMax.value))
    const inner = 37 - (4 + k * 9)
    return {
      h,
      o: (0.22 + k * 0.78).toFixed(2),
      x1: (50 + Math.cos(a) * inner).toFixed(2),
      y1: (50 + Math.sin(a) * inner).toFixed(2),
      x2: (50 + Math.cos(a) * 37).toFixed(2),
      y2: (50 + Math.sin(a) * 37).toFixed(2)
    }
  })
)

const dialHand = computed(() => {
  if (peakHour.value === null) return null
  const a = (peakHour.value / 24) * Math.PI * 2 - Math.PI / 2
  return { x: (50 + Math.cos(a) * 25).toFixed(2), y: (50 + Math.sin(a) * 25).toFixed(2) }
})

const fileCards = computed(() => {
  const out = []
  if (energyChips.value.length) {
    out.push({
      id: 'file-energy', kind: 'file', file: 'energy', rarity: FILE_TIER,
      artSrc: wechatEmojis.value[0]?.src || '',
      title: '能量卡', headline: wechatEmojis.value[0]?.label || '小黄脸与 Emoji',
      stat: fmt(energyChips.value.reduce((a, x) => a + x.count, 0)), statUnit: '次',
      note: `占全年发言 ${stickerSharePct.value}%`,
      backText: '这一年你在文字里按下的小黄脸和 Emoji。'
    })
  }
  if (peakHour.value !== null || hourMax.value > 1) {
    out.push({
      id: 'file-time', kind: 'file', file: 'time', rarity: FILE_TIER,
      title: '时段卡', headline: peakWeekdayName.value ? `高峰 ${peakWeekdayName.value} ${pad(peakHour.value)}:00` : '出牌时段',
      stat: fmt(stickerActiveDays.value), statUnit: '个活跃日',
      note: `日均 ${perDayText.value} 张`,
      backText: '你一天里什么时候最爱发表情，一周里哪天最凶。'
    })
  }
  if (battlePartner.value) {
    out.push({
      id: 'file-rival', kind: 'file', file: 'rival', rarity: FILE_TIER,
      title: '对手卡', headline: battlePartner.value.name,
      stat: fmt(battlePartner.value.count), statUnit: '张对轰',
      note: '年度斗图搭档',
      backText: '这一年和你互甩表情最多的人。'
    })
  }
  return out
})

// 排布顺序决定扇形观感：C 位居中，名次越靠前离中心越近，向两侧分列；
// 档案卡放到最外端。之前直接顺排 + 环形偏移，档案卡会绕回到 C 位旁边，
// 把 4~12 名的高频表情全挤出可见范围。
const cards = computed(() => {
  const st = stickerCards.value
  if (!st.length) return [...fileCards.value]
  const left = []
  const right = []
  st.forEach((c, i) => {
    if (i === 0) return
    if (i % 2) right.push(c)
    else left.push(c)
  })
  const fl = fileCards.value
  const flLeft = fl.filter((_, i) => i % 2 === 1)
  const flRight = fl.filter((_, i) => i % 2 === 0)
  return [...flLeft.reverse(), ...left.reverse(), st[0], ...right, ...flRight]
})

// C 位在数组里的位置，扇形以它为中心
const heroIndex = computed(() => {
  const idx = cards.value.findIndex((c) => c.kind !== 'file' && c.rank === 1)
  return idx < 0 ? 0 : idx
})

// 袋口露出来的是整叠卡的卡背雕纹：压轴要留到最后亲手翻，露正面就剧透了
const nextPeekSrc = computed(() => cardBackDataUri.value)

const maxCount = computed(() => Math.max(1, ...stickerCards.value.map((c) => c.count)))
const barPct = (c) => Math.max(10, Math.round(((Number(c.count) || 0) / maxCount.value) * 100))
const ratioText = (c) => {
  const pct = (Number(c.ratio) || 0) * 100
  if (pct >= 1) return `${pct.toFixed(1)}%`
  if (pct > 0) return `${pct.toFixed(2)}%`
  return '—'
}
const perDayText = computed(() => {
  const v = Number(stickerPerActiveDay.value) || 0
  return v >= 10 ? v.toFixed(0) : v.toFixed(1)
})

// 小黄脸 + Unicode 混排成一条「能量符号」，按次数定大小
const energyChips = computed(() => {
  const rows = [
    ...wechatEmojis.value.slice(0, 5).map((x) => ({ ...x, kind: 'wx' })),
    ...unicodeEmojis.value.slice(0, 4).map((x) => ({ ...x, kind: 'uni', src: '' }))
  ].sort((a, b) => b.count - a.count).slice(0, 7)
  const max = Math.max(1, ...rows.map((x) => x.count))
  return rows.map((x) => ({ ...x, size: Math.round(22 + Math.sqrt(x.count / max) * 14) }))
})

// ---------- 开包 ----------
// sealed 待撕 → tearing 撕口跟手 → pour 全年表情倾泻、年度卡池凝聚 →
// draw 逐张开卡（普卡快发、前三名亲手翻）→ gallery 陈列柜
const phase = ref('sealed')
const focus = ref(0)
// 牌组就绪后把焦点落到 C 位上
watch(() => cards.value.length, () => {
  if (phase.value !== 'gallery') focus.value = Math.max(0, heroIndex.value)
}, { immediate: true })
const detailIdx = ref(-1)
// 翻到卡背的那一张（表情卡才翻；档案卡的明细是长列表和图表，卡背放不下，仍走浮层）
const flippedIdx = ref(-1)
const detail = computed(() => (detailIdx.value < 0 ? null : cards.value[detailIdx.value] || null))

// 能量卡详情：小黄脸 + Unicode 全部列出，这是卡面上放不下的部分
const allEmojiRows = computed(() => {
  const rows = [
    ...wechatEmojis.value.map((x) => ({ ...x, kind: 'wx' })),
    ...unicodeEmojis.value.map((x) => ({ ...x, kind: 'uni', src: '' }))
  ].sort((a, b) => b.count - a.count)
  const max = Math.max(1, ...rows.map((x) => x.count))
  return rows.map((x) => ({ ...x, pct: Math.max(3, Math.round((x.count / max) * 100)) }))
})
const energyTotal = computed(() => allEmojiRows.value.reduce((a, x) => a + x.count, 0))

const rivalSharePct = computed(() => {
  const total = sentStickerCount.value
  const c = battlePartner.value?.count || 0
  return total > 0 ? Math.max(1, Math.round((c / total) * 100)) : 0
})
const rivalEveryN = computed(() => {
  const c = battlePartner.value?.count || 0
  return c > 0 ? Math.max(1, Math.round(sentStickerCount.value / c)) : 0
})
// 卡包在倾泻期间必须留着当喷口，进入开卡阶段才收
const packVisible = computed(() => phase.value === 'sealed' || phase.value === 'tearing' || phase.value === 'pour')
// 倾泻收尾时先淡出卡包，再切阶段，免得它凭空消失
const packLeaving = ref(false)
// 开局只留卡包：卡池铭牌和称号等卡片落位后再出现
const chromeVisible = computed(() => phase.value === 'gallery')

const emit = defineEmits(['immersive'])
// 开局只留卡包：连外壳的标题和叙事一起收起来，落位后再放出来
watch(chromeVisible, (on) => emit('immersive', !on), { immediate: true })
// 壁龛墙从发牌阶段就在（暗着），开完灯光才亮起
const fanVisible = computed(() => phase.value === 'draw' || phase.value === 'gallery')
// 引导只在还没上手时出现，用户一碰就撤
const touched = ref(false)
const showGuide = computed(() => phase.value === 'sealed' && !touched.value && !props.reducedMotion)
const cardEls = new Map()
const registerCard = (i, el) => {
  if (el) cardEls.set(i, el)
  else cardEls.delete(i)
}

// C 位卡的稀有度色，开包的光晕/放射光都用它定调
const heroColor = computed(() => cards.value[0]?.rarity?.color || '#4ADE80')
const heroGlow = computed(() => cards.value[0]?.rarity?.glow || 'rgba(74,222,128,0.5)')

// ---------- ① 撕口跟手 ----------
// 撕口进度交给 3D 卡包自己（顶点级折边），这里只负责把手势换算成 0→1
let rip = 0
let tearDrag = null

const setRip = (v) => {
  rip = Math.max(0, Math.min(1, v))
  pack3d.value?.setRip?.(rip)
}

const onPackPointerDown = (e) => {
  if (props.reducedMotion) return
  if (phase.value !== 'sealed' && phase.value !== 'tearing') return
  e.preventDefault()
  e.stopPropagation()
  touched.value = true
  phase.value = 'tearing'

  const r = e.currentTarget?.getBoundingClientRect?.()
  tearDrag = {
    startX: e.clientX,
    // 卡包只占舞台中间一小条，用它的实际宽度换算手感才对。
    // 基准取短边：只挂高度轴的话，9:16 舞台上要横拖 600+px 才撕得开，而画面总共才 900 宽。
    width: Math.max(1, Math.min(r?.width || 400, r?.height || 400) * 0.42),
    base: rip,
    pointerId: e.pointerId
  }
  window.addEventListener('pointermove', onTearMove, { passive: false })
  window.addEventListener('pointerup', onTearEnd)
  window.addEventListener('pointercancel', onTearEnd)
}

const onTearMove = (e) => {
  if (!tearDrag || e.pointerId !== tearDrag.pointerId) return
  e.preventDefault()
  // 撕口只认横向位移，往回拖也能退回去
  setRip(tearDrag.base + (e.clientX - tearDrag.startX) / tearDrag.width)
  if (rip >= 1) finishTear()
}

const onTearEnd = () => {
  const wasDragging = !!tearDrag
  tearDrag = null
  window.removeEventListener('pointermove', onTearMove)
  window.removeEventListener('pointerup', onTearEnd)
  window.removeEventListener('pointercancel', onTearEnd)
  if (!wasDragging || phase.value !== 'tearing') return
  // 撕过一半就顺势撕完，没到就弹回去重来
  if (rip >= 0.34) finishTear()
  else {
    gsap.to({ v: rip }, { v: 0, duration: 0.3, ease: 'power2.out', onUpdate() { setRip(this.targets()[0].v) } })
    phase.value = 'sealed'
  }
}

// 撕到底：交给 3D 场跑爆光，同时整屏过曝一下
let finished = false
let openFallback = null
const finishTear = () => {
  if (finished) return
  finished = true
  pack3d.value?.autoOpen?.()
  // 标签页切到后台时 rAF 停摆、gsap 也跟着冻住，onComplete 可能永远不来。
  // setTimeout 在后台仍会走，用它兜底，保证卡片一定出得来。
  if (openFallback) clearTimeout(openFallback)
  openFallback = setTimeout(onPackOpened, 1600)
}

// 卡包开完 → 全年表情倾泻而出 → 年度卡池凝聚成叠 → 逐张开卡
const onPackOpened = () => {
  if (openFallback) { clearTimeout(openFallback); openFallback = null }
  if (phase.value !== 'sealed' && phase.value !== 'tearing') return
  if (props.reducedMotion || !poolThumbs.value.length) {
    skipToGallery()
    return
  }
  runPour()
}

// ---------- 倾泻：撕开的一瞬，全年表情从袋口涌出，年度卡池从中凝聚 ----------
const MAX_THUMBS = 44
const siftThumbs = ref([])
const thumbEls = new Map()
const registerThumb = (id, el) => {
  if (el) thumbEls.set(id, el)
  else thumbEls.delete(id)
}

// 卡池叠：倾泻散尽后，从撕开的袋口滑出来的那叠真卡
const stackEl = ref(null)
const stackPileEl = ref(null)
const stackFlashEl = ref(null)
const sparkEl = ref(null)
const flashEl = ref(null)
const stackOn = ref(false)
const stackLayers = ref(0)
const stackLabelOn = ref(false)
// 发牌开始后真卡压在垛上，装饰垛只当纸边底座，顶牌版面让位
const deckUnder = ref(false)

let parts = []
let pourTick = null
let pourFallback = null

const stopPourTick = () => {
  if (pourTick) gsap.ticker.remove(pourTick)
  pourTick = null
  parts = []
}

const clearFx = () => {
  if (sparkEl.value) sparkEl.value.textContent = ''
}

// 和开包同理：标签页切后台时 rAF 停摆、gsap 冻住，onComplete 可能永远不来。
// setTimeout 在后台照走，用它保证一定能走到开卡阶段。
const finishPour = () => {
  if (pourFallback) { clearTimeout(pourFallback); pourFallback = null }
  stopPourTick()
  if (phase.value !== 'pour') return
  siftThumbs.value = []
  thumbEls.clear()
  deckOut()
}

// 倾泻散尽 → 年度卡叠从袋口滑出来落到台面，卡包沉走退场。
// 卡包本来就是装卡的（3D 包口里一直露着牌），这一下只是把它倒出来。
const deckOut = () => {
  stackLayers.value = Math.min(6, Math.max(1, cards.value.length))
  stackOn.value = true
  packLeaving.value = true
  nextTick(() => {
    const pile = stackPileEl.value
    const st = stackEl.value
    const mouth = pack3d.value?.getMouth?.()
    if (pile && st && Number.isFinite(mouth?.left?.x) && Number.isFinite(mouth?.right?.x)) {
      const s = rectC(st)
      const mx = (mouth.left.x + mouth.right.x) / 2
      const my = (mouth.left.y + mouth.right.y) / 2
      // 从袋口滑出时立着（30°），落到台面放平回 9°——像把一叠牌倒在桌上
      gsap.fromTo(
        pile,
        { x: mx - s.x, y: my - s.y, scale: 0.82, rotation: -5, rotationX: 30, transformPerspective: 900, opacity: 0.4 },
        { x: 0, y: 0, scale: 1, rotation: 0, rotationX: 9, opacity: 1, duration: 0.8, ease: 'expo.out', clearProps: 'transform,opacity' }
      )
      // 落定那一下，叠缘闪一道边光
      if (stackFlashEl.value) {
        gsap.fromTo(stackFlashEl.value, { opacity: 0.9 }, { opacity: 0, duration: 0.5, delay: 0.6, ease: 'power2.out' })
      }
    }
    stackLabelOn.value = true
    setTimeout(() => {
      if (phase.value !== 'pour') return
      phase.value = 'draw'
      nextTick(() => runCeremony())
    }, 900)
  })
}

const runPour = async () => {
  phase.value = 'pour'
  stackOn.value = false
  stackLayers.value = 0
  stackLabelOn.value = false
  deckUnder.value = false
  await nextTick()
  // 喷洒铺满整个舞台盒（跟随窗口模式下即窗口）
  const m = stage.viewportSize()

  siftThumbs.value = poolThumbs.value.slice(0, MAX_THUMBS)
  await nextTick()
  const n = siftThumbs.value.length

  // 持续喷洒的时长：短促有力，最后一波出膛后再飞完自己的抛物线
  const EMIT_WINDOW = 2.3

  // 喷发原点＝3D 卡包真实的撕口线段（开包那一刻投影下来的左右两端）
  const mouth = pack3d.value?.getMouth?.()
  const mL = mouth?.left
  const mR = mouth?.right
  const hasMouth = Number.isFinite(mL?.x) && Number.isFinite(mR?.x)

  stopPourTick()
  if (pourFallback) clearTimeout(pourFallback)
  pourFallback = setTimeout(finishPour, (EMIT_WINDOW + 2.6) * 1000)

  // 成簇喷发：一波打出好几张，波与波之间留不等的间隔，
  // 像彩纸炮／撒钱那样一阵一阵，而不是均匀地一颗接一颗（那样会连成一条线）
  const times = []
  let clk = 0
  while (times.length < n) {
    const burst = 2 + Math.floor(Math.random() * 5)
    for (let k = 0; k < burst && times.length < n; k += 1) times.push(clk + Math.random() * 0.1)
    clk += 0.1 + Math.random() * 0.26
  }
  const span = Math.max(0.001, clk)
  for (let i = 0; i < times.length; i += 1) times[i] = (times[i] / span) * EMIT_WINDOW

  // 逐帧积分：喷泉弧线 + 空气阻尼，不撞墙、不弹跳，飞出画面就散
  const G = 2050          // 重力 px/s²
  const DRAG = 0.32       // 空气阻尼
  const r = Math.max(60, m.h * 0.0675)

  parts = siftThumbs.value.map((t, i) => {
    const rAng = Math.random()
    const rSpd = Math.random()
    // 角度分布往两侧推：均匀分布会让大多数几乎笔直向上，看着就挤在中间一柱
    const u = (rAng - 0.5) * 2
    const spread = Math.sign(u) * Math.pow(Math.abs(u), 0.6)
    const ang = -Math.PI / 2 + spread * 1.02 // ±58°
    const v0 = (0.92 + rSpd * 0.66) * Math.sqrt(m.h) * 32
    // 袋口是有宽度的：沿撕口线段随机取出膛点，而不是永远从同一个点冒
    const f = Math.random()
    return {
      el: thumbEls.get(t.id),
      t0: times[i],
      x: hasMouth ? mL.x + (mR.x - mL.x) * f : m.w / 2 + (f - 0.5) * m.w * 0.2,
      y: (hasMouth ? mL.y + (mR.y - mL.y) * f : m.h * 0.5) + (Math.random() - 0.5) * 8,
      vx: Math.cos(ang) * v0,
      vy: Math.sin(ang) * v0,
      rot: 0,
      spin: (Math.random() - 0.5) * 460,
      scale: 0,
      alpha: 0,
      lastAlpha: -1,
      state: 'wait',
      age: 0
    }
  }).filter((p) => p.el)

  let elapsed = 0
  pourTick = (_t, dtMs) => {
    const dt = Math.min(0.05, (dtMs || 16) / 1000)
    elapsed += dt
    let alive = 0

    for (const p of parts) {
      if (p.state === 'dead') continue
      if (p.state === 'wait') {
        if (elapsed < p.t0) { alive += 1; continue }
        p.state = 'fly'
      }
      alive += 1
      p.age += dt

      p.vy += G * dt
      p.vx -= p.vx * DRAG * dt
      p.x += p.vx * dt
      p.y += p.vy * dt
      p.rot += p.spin * dt

      // 出膛弹到本尺寸；飞了一阵或出画就淡出
      p.scale = Math.min(1, p.scale + dt * 7)
      const fading = p.age > 1.35 || p.y > m.h + r || p.x < -r * 2 || p.x > m.w + r * 2
      p.alpha = fading ? Math.max(0, p.alpha - dt * 2.4) : Math.min(1, p.alpha + dt * 8)
      if (fading && p.alpha <= 0) { p.state = 'dead'; p.el.style.opacity = '0'; continue }

      // opacity 只在真的变了才写，省掉大量无谓的样式失效
      if (Math.abs(p.alpha - p.lastAlpha) > 0.02) {
        p.el.style.opacity = String(p.alpha)
        p.lastAlpha = p.alpha
      }
      p.el.style.transform = `translate3d(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px, 0) rotate(${p.rot.toFixed(1)}deg) scale(${p.scale.toFixed(3)})`
    }

    if (alive === 0 && elapsed > EMIT_WINDOW) finishPour()
  }
  gsap.ticker.add(pourTick)
}

// ---------- ② 逐张开卡：普卡快发成墙，前三名亲手翻 ----------
// 壁龛墙从 draw 阶段就全部立着，空着的 C 位基座本身就是悬念；
// 卡落进壁龛才把 shown[id] 置真（CSS 控制 .hc-burst 显隐）。
const shown = reactive({})
const ceremonyIdx = ref(-1)     // 正在台面上的那张（控制聚光与 z 序）
const chargeTier = ref('')      // '' | 'sr' | 'ssr' | 'ur' 蓄势中的稀有度
const leakOn = ref(false)
const flipHint = ref(false)
const revealCap = ref(null)
const capOn = ref(false)

const chargeColor = computed(() => (ceremonyIdx.value >= 0 ? cards.value[ceremonyIdx.value]?.rarity?.color : '') || '#4ADE80')

// 亲手翻的前三张：位次 3 → 2 → 1，压轴永远是年度第一
const rareStages = computed(() =>
  cards.value
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.kind !== 'file' && c.rank <= 3)
    .sort((a, b) => b.c.rank - a.c.rank)
    .map(({ c, i }) => ({ i, tier: c.rank === 1 ? 'ur' : c.rank === 2 ? 'ssr' : 'sr' }))
)
const commonIdxList = computed(() =>
  cards.value.map((c, i) => ({ c, i })).filter(({ c }) => c.kind === 'file' || c.rank > 3).map(({ i }) => i)
)

// 翻开那一刻配的一句话：全部长在这张卡自己的数据上，不套辞藻
const capFor = (c, tier) => {
  const total = uniqueTypeCount.value
  const title = tier === 'ur' ? `年度本命 · ${padNo(1, 3)}/${total}` : `全年第 ${c.rank} 位 · ${padNo(c.rank, 3)}/${total}`
  const everyN = c.ratio > 0 ? Math.max(2, Math.round(1 / c.ratio)) : 0
  let line = ''
  if (c.isNew) line = `今年才进你的表情库，一来就站上第 ${c.rank}`
  else if (c.revived) line = `沉睡了 ${fmt(c.gapDays)} 天，翻出来还是老位置`
  else if (tier === 'ur' && c.ownerName) line = `${fmt(c.count)} 次里的大多数，都飞向了${privacyMode.value ? 'TA' : c.ownerName}`
  else if (tier === 'ur') line = `${fmt(c.count)} 次——你最顺手的那句话，其实是这张图`
  else if (c.ownerName) line = `发出的 ${fmt(c.count)} 次里，大多飞向了${privacyMode.value ? 'TA' : c.ownerName}`
  else if (everyN) line = `每发 ${everyN} 张表情，就有一张是它`
  else line = `这一年陪你出场 ${fmt(c.count)} 次`
  return { title, line }
}

// 等一次点按：翻卡必须亲手来；收卡给个自动兜底保持节奏
let advanceResolve = null
let hintTimer = null
let autoNextTimer = null
const waitTap = (autoSec = 0) =>
  new Promise((resolve) => {
    advanceResolve = resolve
    if (autoSec > 0) autoNextTimer = setTimeout(() => advance(), autoSec * 1000)
  })
const advance = () => {
  if (!advanceResolve) return
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null }
  if (hintTimer) { clearTimeout(hintTimer); hintTimer = null }
  flipHint.value = false
  const r = advanceResolve
  advanceResolve = null
  r()
}

let ceremonyToken = null
const sleep = (s) => new Promise((resolve) => setTimeout(resolve, s * 1000))
const tween = (target, vars, token) => new Promise((resolve) => {
  const t = gsap.to(target, { ...vars, onComplete: resolve, onInterrupt: resolve })
  token?.tweens?.push(t)
})

const rectC = (el) => {
  const r = el.getBoundingClientRect()
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height }
}

// 把某张卡摆到卡池叠位置所需的位移/缩放。
// 量的是槽位而不是卡本身：卡可能已经被 transform 摆去叠上了，槽位永远是原始坐标。
const stackDelta = (i) => {
  const burst = cardEls.get(i)
  const slot = burst?.parentElement
  if (!burst || !slot) return null
  const b = rectC(slot)
  const anchor = stackEl.value || stageEl.value
  if (!anchor || !b.w) return null
  const s = rectC(anchor)
  return { dx: s.x - b.x, dy: s.y - b.y, scale: Math.max(0.16, (stackEl.value ? s.w : 120) / b.w), b }
}

const cardInner = (i) => cardEls.get(i)?.querySelector?.('.hc-card') || null

// 发牌：先让整副真卡（含待翻的稀有卡）以卡背姿态叠上卡池位，装饰叠同帧退场——
// 从这一刻起桌上那叠就是真卡本体；然后普卡一张张飞进壁龛，半途翻正，像熟手发牌。
// 最后留在叠上的，就是还没翻的那几张稀有卡。
const dealCommons = (token) => new Promise((resolve) => {
  if (!cards.value.length) return resolve()
  cards.value.forEach((c, i) => {
    const burst = cardEls.get(i)
    const card = cardInner(i)
    const d = burst && card ? stackDelta(i) : null
    if (!d) { shown[c.id] = true; return }
    gsap.set(burst, { x: d.dx, y: d.dy, scale: d.scale, rotation: (Math.random() - 0.5) * 10 })
    gsap.set(card, { '--cflip': '180deg' })
    shown[c.id] = true
  })
  // 真卡压上来了：装饰垛退成纸边底座，随发牌逐层变薄
  deckUnder.value = true

  const list = commonIdxList.value
  if (!list.length) return resolve()
  const tl = gsap.timeline({ onComplete: resolve, onInterrupt: resolve })
  token.tweens.push(tl)
  const total = list.length
  list.forEach((i, j) => {
    const burst = cardEls.get(i)
    const card = cardInner(i)
    if (!burst || !card) return
    const slot = burst.parentElement
    const at = j * 0.09
    tl.set(slot, { zIndex: 40 }, at)
      .to(burst, { x: 0, y: 0, rotation: 0, duration: 0.58, ease: 'power3.out' }, at)
      .to(burst, { scale: 1.055, duration: 0.42, ease: 'power2.out' }, at)
      .to(burst, { scale: 1, duration: 0.2, ease: 'power2.inOut' }, at + 0.42)
      .to(card, { '--cflip': '0deg', duration: 0.5, ease: 'power2.inOut' }, at + 0.05)
      .set(burst, { clearProps: 'transform' }, at + 0.64)
      .set(card, { clearProps: '--cflip' }, at + 0.64)
      .set(slot, { clearProps: 'zIndex' }, at + 0.66)
      .call(() => {
        // 底座跟着变薄，但给还没翻的稀有卡留厚度：一张压轴一层
        const floorN = Math.min(6, rareStages.value.length)
        stackLayers.value = Math.max(floorN, Math.round(6 * (1 - (j + 1) / Math.max(1, total))))
      }, null, at + 0.12)
  })
})

// 翻开时的火花：几粒稀有度色的小箔片，不搞满屏彩带
const burstSparks = (tier) => {
  const host = sparkEl.value
  if (!host || props.reducedMotion) return
  const n = tier === 'ur' ? 18 : tier === 'ssr' ? 12 : 8
  const reach = tier === 'ur' ? 1 : 0.7
  for (let k = 0; k < n; k += 1) {
    const s = document.createElement('i')
    host.appendChild(s)
    const a = Math.random() * Math.PI * 2
    const dist = reach * (70 + Math.random() * 150)
    gsap.fromTo(
      s,
      { x: 0, y: 0, opacity: 1, scale: 0.5 + Math.random() * 0.9, rotation: Math.random() * 360 },
      { x: Math.cos(a) * dist, y: Math.sin(a) * dist * 0.85, opacity: 0, rotation: '+=140', duration: 0.85 + Math.random() * 0.5, ease: 'power3.out', delay: 0.34, onComplete: () => s.remove() }
    )
  }
}

// 前三张：浮上台面、蓄势、亲手翻开、看完再入龛
const revealRare = async ({ i, tier }, token, isLast) => {
  const burst = cardEls.get(i)
  const card = cardInner(i)
  const stage = stageEl.value
  const d = burst && card && stage ? stackDelta(i) : null
  if (!d) { shown[cards.value[i].id] = true; return }

  const sr = rectC(stage)
  // 台面位：比几何中心略高，给下方那句话留呼吸
  const targetH = sr.h * (tier === 'ur' ? 0.6 : 0.54)
  const scaleC = targetH / Math.max(1, d.b.h)
  const dxC = sr.x - d.b.x
  const dyC = sr.y - sr.h * 0.055 - d.b.y

  // 这张卡从发牌起就以卡背姿态待在叠上了，这里只重新钉一次位置防窗口变动
  gsap.set(burst, { x: d.dx, y: d.dy, scale: d.scale, rotation: (Math.random() - 0.5) * 8 })
  gsap.set(card, { '--cflip': '180deg' })
  shown[cards.value[i].id] = true
  ceremonyIdx.value = i
  stackLayers.value = Math.max(0, stackLayers.value - 1)

  // ① 浮上台面（仍是卡背）
  await tween(burst, { x: dxC, y: dyC, scale: scaleC, rotation: 0, duration: 0.62, ease: 'expo.out' }, token)
  if (token.dead) return

  // ② 蓄势：稀有度色的边缘光，越稀有蓄得越久；UR 全场调暗、背后漏光
  chargeTier.value = tier
  if (tier === 'ur') leakOn.value = true
  await sleep(tier === 'ur' ? 1.5 : tier === 'ssr' ? 1.05 : 0.75)
  if (token.dead) return

  // ③ 亲手翻：等点按，太久就轻声提示一下
  hintTimer = setTimeout(() => { flipHint.value = true }, 2000)
  await waitTap()
  if (token.dead) return

  // ④ 翻开 + 庆祝：箔面爆闪、火花，UR 追加一记全场曝光；游光环到此收工
  chargeTier.value = ''
  const flip = tween(card, { '--cflip': '0deg', duration: 0.74, ease: 'power4.inOut' }, token)
  gsap.fromTo(card, { '--holo-boost': 0 }, { '--holo-boost': 1, duration: 0.3, delay: 0.32, yoyo: true, repeat: 1, ease: 'power2.inOut' })
  burstSparks(tier)
  if (tier === 'ur' && flashEl.value) {
    gsap.fromTo(flashEl.value, { opacity: 0.42 }, { opacity: 0, duration: 0.9, ease: 'power2.out', delay: 0.3 })
  }
  await flip
  if (token.dead) return
  revealCap.value = capFor(cards.value[i], tier)
  capOn.value = true

  // ⑤ 看够为止：点一下收卡，不点 4 秒后自动
  await waitTap(4)
  if (token.dead) return
  capOn.value = false
  leakOn.value = false

  // ⑥ 入龛
  await tween(burst, { x: 0, y: 0, scale: 1, duration: 0.6, ease: 'expo.inOut' }, token)
  gsap.set(burst, { clearProps: 'transform' })
  gsap.set(card, { clearProps: '--cflip' })
  ceremonyIdx.value = -1
  revealCap.value = null
  if (!isLast) await sleep(0.12)
}

const openGallery = () => {
  phase.value = 'gallery'
  focus.value = Math.max(0, heroIndex.value)
}

const runCeremony = async () => {
  const token = { dead: false, tweens: [] }
  ceremonyToken = token
  await sleep(0.16)
  if (token.dead) return
  await dealCommons(token)
  if (token.dead) return
  const stages = rareStages.value
  for (let k = 0; k < stages.length; k += 1) {
    await revealRare(stages[k], token, k === stages.length - 1)
    if (token.dead) return
  }
  openGallery()
}

// 一键回到终局：熄屏、切页、reduced-motion 都走这条路
const skipToGallery = () => {
  if (ceremonyToken) {
    ceremonyToken.dead = true
    ceremonyToken.tweens.forEach((t) => t?.kill?.())
    ceremonyToken = null
  }
  if (advanceResolve) { const r = advanceResolve; advanceResolve = null; r() }
  if (hintTimer) { clearTimeout(hintTimer); hintTimer = null }
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null }
  if (pourFallback) { clearTimeout(pourFallback); pourFallback = null }
  stopPourTick()
  siftThumbs.value = []
  thumbEls.clear()
  clearFx()
  cards.value.forEach((c, i) => {
    shown[c.id] = true
    const b = cardEls.get(i)
    if (b) {
      gsap.killTweensOf(b)
      gsap.set(b, { clearProps: 'transform' })
      const inner = b.querySelector?.('.hc-card')
      if (inner) { gsap.killTweensOf(inner); gsap.set(inner, { clearProps: '--cflip' }) }
    }
  })
  flipHint.value = false
  revealCap.value = null
  capOn.value = false
  chargeTier.value = ''
  leakOn.value = false
  ceremonyIdx.value = -1
  packLeaving.value = true
  phase.value = 'gallery'
}

// ---------- 陈列墙格位 ----------
// C 位占 2×2，其余 1×1（所以格位数 = 张数 + 3）。
// 16:9 沿用「按张数推、保证两行」的原式，逐像素不变。
// 窄画幅下这条式子会一路撞到 10 列上限：9:16 里每格只剩 66px，--u 掉到 0.67px，
// 卡面上所有字（卡名/次数/占比）等于全糊掉——看得见轮廓但读不出内容。
// 换画幅只该改行列数、把卡放大，于是改成：在「行数放得下」的前提下取最少的列数
// （.hc-root 是 overflow:hidden，多一行就是把最下面一排整排切掉）。
const CARD_RATIO = 88 / 63    // 卡面比例，行高 = 卡宽 × 它

const wallBox = ref({ w: 0, h: 0, head: 0 })
let wallRo = null

const measureWall = () => {
  const el = rootEl.value
  if (!el || typeof window === 'undefined') return
  const head = parseFloat(window.getComputedStyle(el).getPropertyValue('--hc-head-h')) || 0
  const next = { w: el.clientWidth, h: el.clientHeight, head }
  const cur = wallBox.value
  if (Math.abs(cur.w - next.w) > 0.5 || Math.abs(cur.h - next.h) > 0.5 || Math.abs(cur.head - next.head) > 0.5) {
    wallBox.value = next
  }
}

onMounted(() => {
  if (!import.meta.client) return
  measureWall()
  nextTick(measureWall)
  if (typeof ResizeObserver === 'undefined' || !rootEl.value) return
  // 只观察根盒：列数不改变根盒尺寸，没有反馈回路
  wallRo = new ResizeObserver(measureWall)
  wallRo.observe(rootEl.value)
})

const gridCols = computed(() => {
  const n = cards.value.length + 3
  const legacy = Math.max(4, Math.min(10, Math.ceil(n / 2)))
  if (stage.tier.value === 'wide') return legacy
  const { w, h, head } = wallBox.value
  if (!w || !h) return legacy
  const cq = h / 100
  const gap = Math.max(9, 1.5 * cq)
  const padTop = Math.max(Math.min(128, Math.max(92, 13 * cq)), head)
  const padBottom = Math.max(10, 1.6 * cq)
  const availW = Math.max(1, w - gap * 2)
  const availH = Math.max(1, h - padTop - padBottom)
  // 从最少的列数往上找第一个「行数放得下」的解 —— 也就是这块墙上卡能做到的最大尺寸。
  // 原来的起点是 round(availW / CELL_PITCH)（把 16:9 的格宽当常量搬过来），
  // 结果 9:16 上一开口就是 5 列、卡宽 151px，比 16:9 的 185px 还小：画幅更窄、
  // 卡也更小，卡面上的名字和次数双重挤压。现在 9:16 落到 4 列 / 195px。
  // 0.985 是留给标题带高度抖动的余量：.hc-root 是 overflow:hidden，多一行就整排切掉。
  let cols = 2
  for (; cols < 12; cols += 1) {
    const cardW = (availW - (cols - 1) * gap) / cols
    const rows = Math.ceil(n / cols)
    if (rows * cardW * CARD_RATIO + (rows - 1) * gap <= availH * 0.985) break
  }
  return Math.min(cols, 12)
})
// C 位基座钉在墙面正中：auto-flow: dense 会把其余卡回填到两侧
const heroCol = computed(() => Math.max(1, Math.floor((gridCols.value - 2) / 2) + 1))

// ---------- 全息箔：指针驱动的 CSS 变量 ----------
const pointerVars = reactive({})

const cardVars = (i, c) => {
  const p = pointerVars[i] || { px: 50, py: 50, rx: 0, ry: 0, d: 0 }
  return {
    '--px': `${p.px}%`,
    '--py': `${p.py}%`,
    '--bgx': `${40 + p.px * 0.2}%`,
    '--bgy': `${40 + p.py * 0.2}%`,
    '--rx': `${p.rx}deg`,
    '--ry': `${p.ry}deg`,
    '--flip': i === flippedIdx.value ? '180deg' : '0deg',
    '--holo': String(i === focus.value ? Math.min(1, 0.42 + p.d * 0.6) : 0.22),
    '--rc': c.rarity.color,
    '--rg': c.rarity.glow
  }
}

const onCardPointerMove = (i, e) => {
  if (props.reducedMotion) return
  const el = e.currentTarget
  const r = el?.getBoundingClientRect?.()
  if (!r?.width || !r?.height) return
  const nx = (e.clientX - r.left) / r.width
  const ny = (e.clientY - r.top) / r.height
  const cx = nx - 0.5
  const cy = ny - 0.5
  pointerVars[i] = {
    px: Math.round(nx * 100),
    py: Math.round(ny * 100),
    rx: (-cy * 16).toFixed(2),
    ry: (cx * 18).toFixed(2),
    d: Math.min(1, Math.hypot(cx, cy) * 2)
  }
}

const onCardPointerLeave = (i) => {
  pointerVars[i] = { px: 50, py: 50, rx: 0, ry: 0, d: 0 }
}

// ---------- 交互：开卡期点按推进，陈列期点选翻看 ----------
const onCardClick = (i, e) => {
  if (dragMoved) return
  if (phase.value !== 'gallery') return
  e.stopPropagation()

  focus.value = i
  const c = cards.value[i]
  if (c && c.kind !== 'file') {
    flippedIdx.value = flippedIdx.value === i ? -1 : i
    detailIdx.value = -1
    return
  }
  flippedIdx.value = -1
  detailIdx.value = detailIdx.value === i ? -1 : i
}

let dragStartX = 0
let dragging = false
let dragMoved = false

const onStagePointerDown = (e) => {
  if (phase.value === 'draw') {
    advance()
    return
  }
  if (phase.value !== 'gallery') return
  dragging = true
  dragMoved = false
  dragStartX = e.clientX
}

const onStagePointerMove = (e) => {
  if (!dragging) return
  if (Math.abs(e.clientX - dragStartX) > 6) dragMoved = true
}

const onStagePointerUp = () => {
  dragging = false
  // 一帧后清标记，避免 pointerup 之后的 click 被误判成拖拽
  setTimeout(() => { dragMoved = false }, 0)
}

const onStageLeave = () => {
  dragging = false
  for (const k of Object.keys(pointerVars)) pointerVars[k] = { px: 50, py: 50, rx: 0, ry: 0, d: 0 }
}

// ---------- 生命周期 ----------
// 中途翻页离开：直接把牌全部落定，回来看到的是完整陈列而不是断掉的仪式
watch(() => props.active, (on) => {
  if (!on && (phase.value === 'pour' || phase.value === 'draw')) skipToGallery()
})

/* ── 导出模式：立刻呈现终态（陈列墙），退出时还原 ──
   闸门在本组件而不是父卡：父卡的 `immersive` 只是 chromeVisible 的只读镜像，
   推不动这里的 phase（sealed → tearing → pour → draw → gallery），
   而 `reducedMotion` 只在用户已经撕开卡包之后才短路到 skipToGallery——
   光挂 reduced 仍然是一个封着的卡包。所以直接 inject 那个开关：
   inject 跨层级生效，不需要父卡再把 prop 一路传下来。

   ⚠️ 还原必须真的还原：导出一次之后回去浏览，卡包应该仍是封着的。
   这一页的主体验就是「撕开 → 倾泻 → 发牌」的揭晓过程，被剧透就废了。 */
const exportMode = inject('wrappedExportMode', ref(false))
let exportSnapshot = null

const applyExportTerminal = () => {
  if (exportSnapshot === null) exportSnapshot = phase.value
  if (phase.value !== 'gallery') skipToGallery()
}

const applyExportRestore = () => {
  const snap = exportSnapshot
  exportSnapshot = null
  // 导出前用户就已经看到陈列墙了：保持现状，不要把人家的进度抹回去
  if (snap === null || snap === 'gallery') return
  // 否则退回封包态：撕口归零、卡片重新藏起来、引导手势重新出现
  cards.value.forEach((c) => { shown[c.id] = false })
  setRip(0)
  packLeaving.value = false
  flippedIdx.value = -1
  detailIdx.value = -1
  touched.value = false
  siftThumbs.value = []
  clearFx()
  phase.value = 'sealed'
  focus.value = Math.max(0, heroIndex.value)
}

watch(exportMode, (on) => {
  if (on) applyExportTerminal()
  else applyExportRestore()
}, { immediate: true })

onBeforeUnmount(() => {
  wallRo?.disconnect()
  wallRo = null
  if (ceremonyToken) {
    ceremonyToken.dead = true
    ceremonyToken.tweens.forEach((t) => t?.kill?.())
    ceremonyToken = null
  }
  if (advanceResolve) { const r = advanceResolve; advanceResolve = null; r() }
  if (hintTimer) clearTimeout(hintTimer)
  if (autoNextTimer) clearTimeout(autoNextTimer)
  if (pourFallback) clearTimeout(pourFallback)
  if (openFallback) clearTimeout(openFallback)
  stopPourTick()
  clearFx()
  window.removeEventListener('pointermove', onTearMove)
  window.removeEventListener('pointerup', onTearEnd)
  window.removeEventListener('pointercancel', onTearEnd)
})
</script>

<style scoped>
.hc-root {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  container-type: size;
  color: #E8F2EC;
  user-select: none;
}

/* 开卡区聚光：跟着 C 位卡的稀有度色微微染一层 */
.hc-field {
  position: absolute;
  inset: 0;
  background: radial-gradient(46% 44% at 50% 48%, color-mix(in srgb, var(--hero, #4ADE80) 10%, transparent), transparent 74%);
  transition: background 600ms ease;
}
/* 陈列灯亮起：墙面有了材质——顶部洗墙光、纵向明暗、四角收暗 */
.hc-root--gallery .hc-field {
  background:
    radial-gradient(120% 55% at 50% -12%, rgba(214, 240, 224, 0.07), transparent 60%),
    radial-gradient(46% 44% at 50% 48%, color-mix(in srgb, var(--hero, #4ADE80) 7%, transparent), transparent 74%),
    radial-gradient(130% 120% at 50% 50%, transparent 58%, rgba(0, 0, 0, 0.5) 100%),
    linear-gradient(180deg, #0C1712 0%, #071009 58%, #040906 100%);
}
/* 墙面颗粒：漆面质感，盖掉纯数字渐变的塑料感 */
.hc-root--gallery .hc-field::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: var(--grain);
  background-size: 180px 180px;
  mix-blend-mode: overlay;
  opacity: 0.5;
  pointer-events: none;
}

.hc-empty { position: absolute; inset: 0; display: grid; place-items: center; }
.hc-empty-box {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(8px);
  border-radius: 16px;
  padding: 20px 24px;
  text-align: center;
}

/* ---------- 舞台 ---------- */
.hc-stage {
  position: absolute;
  inset: 0;
  z-index: 40;
  touch-action: pan-y;
}
.hc-root--sealed .hc-stage,
.hc-root--tearing .hc-stage { cursor: grab; }
.hc-root--draw .hc-stage { cursor: pointer; }

/* ---------- 开包 ---------- */
.hc-pack3d {
  position: absolute;
  inset: 0;
  z-index: 40;
  cursor: grab;
  transition: opacity 420ms ease, transform 420ms ease;
}
.hc-pack3d:active { cursor: grabbing; }
.hc-pack3d--out {
  opacity: 0;
  transform: translateY(2.5cqh) scale(0.985);
  pointer-events: none;
}

/* 全年表情涌出层 */
.hc-sift { position: fixed; inset: 0; z-index: 9998; pointer-events: none; }
.hc-thumb {
  position: absolute;
  left: 0;
  top: 0;
  /* --su 是舞台的双轴基准标量：16:9 下恒等于 --svh（逐像素不变），
     竖幅下改由短边决定，免得一张缩略图被撑到 200+px */
  width: max(120px, calc(var(--su, 9px) * 13.5));
  height: max(120px, calc(var(--su, 9px) * 13.5));
  margin: max(-60px, calc(var(--su, 9px) * -6.75)) 0 0 max(-60px, calc(var(--su, 9px) * -6.75));
  object-fit: contain;
  opacity: 0;
  border-radius: 6px;
  will-change: transform, opacity;
  /* 不加 drop-shadow：近百个大元素每帧重栅格化，是这段最主要的卡顿来源 */
  contain: layout style paint;
}

/* 撕口指引：等人犹豫了两秒多才轻声出现的一句小字，位置在卡包下方 */
.hc-guide {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 50;
  transform: translate(-50%, calc(-50% + 24cqh));
  pointer-events: none;
  animation: hc-guide-in 1100ms ease 2800ms both;
}
@keyframes hc-guide-in { from { opacity: 0; } to { opacity: 1; } }
.hc-guide-text {
  /* 字号挂高度轴：竖幅下舞台变高反而会把它撑大。cqmin 在横幅里恒等于 cqh */
  font-size: max(10px, 1.15cqmin);
  letter-spacing: 0.3em;
  color: rgba(255, 255, 255, 0.44);
}

/* ---------- 年度卡池叠 ---------- */
.hc-stack {
  position: absolute;
  left: 50%;
  top: 55%;
  z-index: 45;
  width: min(18.5cqh, 148px);
  aspect-ratio: 63 / 88;
  transform: translate(-50%, -50%);
  pointer-events: none;
  opacity: 0;
  transition: opacity 320ms ease;
}
.hc-stack--on { opacity: 1; }
/* 叠下的光池：桌面上有一汪被卡照亮的光 */
.hc-stack::before {
  content: '';
  position: absolute;
  left: -42%;
  right: -42%;
  bottom: -6cqh;
  height: 9cqh;
  background: radial-gradient(50% 60% at 50% 42%, rgba(120, 235, 175, 0.08), transparent 76%);
}
/* 整垛带一点后仰透视：是搁在台面上的实体，不是贴在屏幕上的贴纸 */
.hc-stack-pile {
  position: absolute;
  inset: 0;
  transform: perspective(900px) rotateX(9deg);
  transform-origin: 50% 88%;
}
/* 垫底层 = 米白纸边：真卡垛的侧面就是纸色，一层层错缝叠出厚度 */
.hc-stack-card {
  position: absolute;
  inset: 0;
  border-radius: 10px;
  transform: translateY(calc((var(--i) - 1) * -3px)) rotate(calc((var(--i) - 3.5) * 0.9deg));
  background: linear-gradient(180deg, #EDE7D4 0%, #DAD2B9 55%, #B9B095 100%);
  box-shadow:
    0 1px 0 rgba(0, 0, 0, 0.32),
    inset 0 -1px 0 rgba(0, 0, 0, 0.16);
}
/* 顶牌：整张卡背版面压在纸垛上 */
.hc-stack-card.is-top {
  background-color: #0B1912;
  background-image: var(--cb);
  background-size: 100% 100%;
  box-shadow:
    0 2px 0 rgba(0, 0, 0, 0.3),
    0 12px 28px rgba(0, 0, 0, 0.55);
}
/* 箔光扫掠只走顶牌：光带隔两秒多掠过一次，像有人在灯下微微晃这叠卡 */
.hc-stack-card.is-top::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 10px;
  background: linear-gradient(115deg, transparent 32%, rgba(255, 255, 255, 0.22) 45%, rgba(245, 225, 160, 0.14) 52%, transparent 66%);
  background-size: 240% 100%;
  background-position: 120% 0;
  mix-blend-mode: screen;
  animation: hc-stack-sheen 2.8s ease-in-out infinite;
}
@keyframes hc-stack-sheen {
  0%, 52% { background-position: 120% 0; }
  88%, 100% { background-position: -60% 0; }
}
/* 叠落定时闪一道金边光 */
.hc-stack-flash {
  position: absolute;
  inset: -15px 0 0 0;
  border-radius: 10px;
  border: 1.5px solid rgba(250, 235, 190, 0.95);
  box-shadow: 0 0 14px rgba(240, 214, 140, 0.55);
  opacity: 0;
}
/* 落地接触阴影 */
.hc-stack-shadow {
  position: absolute;
  left: 4%;
  right: 4%;
  bottom: -2.6cqh;
  height: 2.6cqh;
  background: radial-gradient(50% 52% at 50% 50%, rgba(0, 0, 0, 0.6), transparent 74%);
}
.hc-stack-label {
  position: absolute;
  left: 50%;
  bottom: -4cqh;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: max(10px, 1.15cqmin);
  letter-spacing: 0.26em;
  color: rgba(255, 255, 255, 0.42);
  opacity: 0;
  transition: opacity 500ms ease;
}
.hc-stack-label.is-on { opacity: 1; }

/* ---------- 开卡舞台灯效 ---------- */
.hc-leak {
  position: absolute;
  left: 50%;
  top: 44.5%;
  z-index: 35;
  /* 挂高度轴的正方形：9:16 舞台上边长会变成一千多像素，把整面墙都罩住。
     cqmin 在横幅里恒等于 cqh（16:9 逐像素不变），竖幅里改由短边定。 */
  width: 88cqmin;
  height: 88cqmin;
  transform: translate(-50%, -50%);
  pointer-events: none;
  background: radial-gradient(closest-side, color-mix(in srgb, var(--rc, #FFCE4A) 26%, transparent), transparent 68%);
  animation: hc-leak-breathe 2.2s ease-in-out infinite;
}
@keyframes hc-leak-breathe {
  0%, 100% { opacity: 0.5; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.85; transform: translate(-50%, -50%) scale(1.07); }
}
.hc-flash {
  position: absolute;
  inset: 0;
  z-index: 96;
  background: #fff;
  opacity: 0;
  pointer-events: none;
  mix-blend-mode: screen;
}
.hc-sparkbox {
  position: absolute;
  left: 50%;
  top: 44.5%;
  z-index: 95;
  pointer-events: none;
}
.hc-sparkbox i {
  position: absolute;
  width: 5px;
  height: 14px;
  border-radius: 2px;
  background: linear-gradient(180deg, #fff, var(--rc, #4ADE80));
  box-shadow: 0 0 8px var(--rc, #4ADE80);
}

/* 翻开后的那句话 */
.hc-cap {
  position: absolute;
  left: 50%;
  bottom: 7cqh;
  transform: translate(-50%, 14px);
  z-index: 97;
  width: min(86%, 560px);
  text-align: center;
  opacity: 0;
  transition: opacity 480ms ease, transform 480ms cubic-bezier(0.22, 1, 0.36, 1);
  pointer-events: none;
}
.hc-cap--on { opacity: 1; transform: translate(-50%, 0); }
.hc-cap-t { font-size: max(13px, 1.9cqmin); letter-spacing: 0.18em; color: rgba(255, 255, 255, 0.92); }
.hc-cap-l { margin-top: 6px; font-size: max(11px, 1.5cqmin); line-height: 1.8; color: rgba(255, 255, 255, 0.55); }

.hc-taphint {
  position: absolute;
  left: 50%;
  bottom: 12cqh;
  transform: translateX(-50%);
  z-index: 97;
  font-size: max(10px, 1.2cqmin);
  letter-spacing: 0.3em;
  color: rgba(255, 255, 255, 0.5);
  animation: hc-hint-pulse 2s ease-in-out infinite;
  pointer-events: none;
}
@keyframes hc-hint-pulse {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 0.8; }
}

/* ---------- 壁龛陈列墙 ---------- */
.hc-fan {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(var(--cols, 8), minmax(0, 1fr));
  grid-auto-rows: min-content;
  grid-auto-flow: dense;
  align-content: center;
  justify-content: center;
  gap: max(9px, 1.5cqh);
  /* 顶部恒定预留标题带：发牌与陈列同一几何，谢幕时不再整体缩小。
     --hc-head-h 是外壳量出来的标题带实高（含 4px 顶偏移 + 10px 呼吸）；
     写死的 clamp 只够两行，长叙事/窄画幅下标题会直接压在顶排卡上。 */
  padding: max(clamp(92px, 13cqh, 128px), var(--hc-head-h, 0px)) max(9px, 1.5cqh) max(10px, 1.6cqh);
  opacity: 0;
  transition: opacity 380ms ease;
}
.hc-fan--on { opacity: 1; }
/* 开卡期间墙上的卡不接指针：整个舞台就是「点一下继续」 */
.hc-fan:not(.hc-fan--lit) .hc-slot { pointer-events: none; }
/* gsap 逐帧驱动 --cflip 时不能有 CSS transition 抢活，否则翻转拖泥带水 */
.hc-fan:not(.hc-fan--lit) .hc-card { transition: none; }

.hc-slot {
  position: relative;
  min-width: 0;
  cursor: pointer;
  /* --u = 卡宽的 1%，卡面上所有字号/间距都按它走 */
  --u: 1cqw;
  container-type: inline-size;
}
/* C 位占 2×2 并钉在正中列：格宽 2 份 + 间隙，长宽比正好还原成卡片比例 */
.hc-slot--hero { grid-column: var(--heroCol, 4) / span 2; grid-row: 1 / span 2; }

/* 卡未落位时只立着空壁龛 */
.hc-slot .hc-burst { visibility: hidden; }
.hc-slot.is-in .hc-burst { visibility: visible; }

/* 壁龛：一格凹进墙里的展位 */
.hc-niche {
  position: absolute;
  inset: calc(max(5px, 0.85cqh) * -1);
  border-radius: 13px;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.012) 34%, rgba(0, 0, 0, 0.34)),
    rgba(4, 10, 8, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.05);
  box-shadow:
    inset 0 10px 18px rgba(0, 0, 0, 0.42),
    inset 0 -1px 0 rgba(255, 255, 255, 0.04);
  opacity: 0.4;
  transition: opacity 700ms ease, box-shadow 400ms ease;
}
/* 龛顶光锥：稀有度色染一点，亮灯后才看得清 */
.hc-niche::before {
  content: '';
  position: absolute;
  inset: 0 8% auto 8%;
  height: 62%;
  clip-path: polygon(30% 0, 70% 0, 100% 100%, 0 100%);
  background: linear-gradient(180deg, color-mix(in srgb, var(--rc, #4ADE80) 24%, rgba(255, 255, 255, 0.14)), transparent 78%);
  opacity: 0;
  transition: opacity 900ms ease;
}
/* 玻璃层板：卡下方一条浅浅的反光 */
.hc-niche::after {
  content: '';
  position: absolute;
  left: 10%;
  right: 10%;
  bottom: max(2px, 0.4cqh);
  height: max(3px, 0.55cqh);
  border-radius: 999px;
  background: radial-gradient(50% 100% at 50% 0%, color-mix(in srgb, var(--rc, #4ADE80) 30%, rgba(255, 255, 255, 0.16)), transparent 78%);
  opacity: 0;
  transition: opacity 900ms ease;
}
.hc-fan--lit .hc-niche {
  opacity: 1;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.02) 30%, rgba(0, 0, 0, 0.42));
  border-color: rgba(255, 255, 255, 0.09);
  box-shadow:
    inset 0 12px 22px rgba(0, 0, 0, 0.5),
    inset 0 -9px 16px rgba(140, 240, 185, 0.045),
    inset 0 -1px 0 rgba(255, 255, 255, 0.05),
    0 1px 0 rgba(255, 255, 255, 0.03);
}
.hc-fan--lit .hc-niche::before { opacity: 0.65; }
.hc-fan--lit .hc-niche::after { opacity: 0.75; }
.hc-fan--lit .hc-slot:hover .hc-niche::before { opacity: 1; }
.hc-fan--lit .hc-slot:hover .hc-niche {
  box-shadow:
    inset 0 12px 22px rgba(0, 0, 0, 0.5),
    inset 0 0 24px color-mix(in srgb, var(--rc, #4ADE80) 14%, transparent);
}

/* C 位基座：空着的时候就比别的龛亮一线，留着悬念 */
.hc-slot--hero .hc-niche {
  border-color: color-mix(in srgb, #FFCE4A 26%, rgba(255, 255, 255, 0.06));
  box-shadow:
    inset 0 14px 26px rgba(0, 0, 0, 0.46),
    inset 0 0 30px rgba(255, 206, 74, 0.05);
}
/* 亮灯后 C 位是全场唯一的金座 */
.hc-fan--lit .hc-slot--hero .hc-niche {
  border-color: color-mix(in srgb, #FFCE4A 36%, rgba(255, 255, 255, 0.08));
  box-shadow:
    inset 0 14px 28px rgba(0, 0, 0, 0.52),
    inset 0 0 44px rgba(255, 206, 74, 0.09),
    0 0 30px rgba(255, 206, 74, 0.05);
}

/* ---------- 开卡蓄势 ---------- */
@property --sweep {
  syntax: '<angle>';
  inherits: false;
  initial-value: 0deg;
}
.hc-slot.is-ceremony { z-index: 90; }
.is-ceremony .hc-burst {
  filter: drop-shadow(0 20px 44px rgba(0, 0, 0, 0.62)) drop-shadow(0 0 28px var(--rg, rgba(74, 222, 128, 0.4)));
}
/* 台上有卡：其余全部退光 */
.hc-root--stagelit .hc-slot:not(.is-ceremony) .hc-burst {
  opacity: 0.15;
  filter: saturate(0.5) brightness(0.6);
  transition: opacity 450ms ease, filter 450ms ease;
}
.hc-root--stagelit .hc-niche { opacity: 0.1; }
.hc-root--stagelit .hc-stack { opacity: 0.22; }
.hc-root--stagelit .hc-field {
  background:
    radial-gradient(46% 44% at 50% 48%, color-mix(in srgb, var(--hero, #4ADE80) 5%, transparent), transparent 70%),
    rgba(0, 0, 0, 0.42);
}
/* 蓄势光环：沿卡缘跑的稀有度色游光，越稀有跑得越急 */
.hc-root--charge .is-ceremony .hc-card::after {
  content: '';
  position: absolute;
  inset: -5px;
  border-radius: 15px;
  padding: 3px;
  background: conic-gradient(
    from var(--sweep),
    transparent 0 8%,
    var(--rc, #4ADE80) 19%,
    #fff 23%,
    var(--rc, #4ADE80) 27%,
    transparent 38% 100%
  );
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask-composite: exclude;
  filter: drop-shadow(0 0 7px var(--rc, #4ADE80));
  animation: hc-sweep 1.3s linear infinite;
  pointer-events: none;
}
@keyframes hc-sweep { to { --sweep: 360deg; } }
.hc-root--charge-ssr .is-ceremony .hc-card::after { animation-duration: 1.05s; }
.hc-root--charge-ur .is-ceremony .hc-card::after { animation-duration: 0.78s; }

/* 蓄势时中央徽记位跟着呼吸：能量在里面攒着的意思 */
.hc-root--charge .is-ceremony .hc-face--cover::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 47.7%;
  width: 34%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%) rotate(45deg);
  border-radius: calc(var(--u) * 1.6);
  box-shadow:
    0 0 calc(var(--u) * 9) color-mix(in srgb, var(--rc, #4ADE80) 55%, transparent),
    inset 0 0 calc(var(--u) * 6) color-mix(in srgb, var(--rc, #4ADE80) 30%, transparent);
  animation: hc-medal-breathe 1.5s ease-in-out infinite;
  pointer-events: none;
}
@keyframes hc-medal-breathe {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.hc-burst {
  display: block;
  will-change: transform, opacity;
  /* 投影必须挂在这一层：和 preserve-3d 同元素时 filter 会把 3D 压平，卡背就翻不出来 */
  filter: drop-shadow(0 8px 14px rgba(0, 0, 0, 0.45));
  transition: filter 300ms ease;
}
.hc-slot:hover .hc-burst,
.hc-slot--focus .hc-burst { filter: drop-shadow(0 10px 18px rgba(0, 0, 0, 0.55)); }

.hc-card {
  position: relative;
  width: 100%;
  aspect-ratio: 63 / 88;
  border-radius: 11px;
  transform-style: preserve-3d;
  transform: perspective(1000px) rotateX(var(--rx, 0deg)) rotateY(calc(var(--ry, 0deg) + var(--flip, 0deg) + var(--cflip, 0deg)));
  transition: transform 620ms cubic-bezier(0.32, 0.72, 0, 1), box-shadow 300ms ease;
}
.hc-card--focus,
.hc-slot:hover .hc-card { z-index: 5; }
/* 辉光收小：便当格里每张卡都贴着格位边界，光晕一大就会被裁出一个硬矩形。
   放在外层，避免和卡片本体的 preserve-3d 冲突 */
.hc-slot:hover .hc-burst,
.hc-burst:has(.hc-card--focus) {
  filter: drop-shadow(0 10px 18px rgba(0, 0, 0, 0.55)) drop-shadow(0 0 8px var(--rg));
}

.hc-face {
  position: absolute;
  inset: 0;
  border-radius: 11px;
  overflow: hidden;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}
/* ───── 卡背：真实卡牌的背面——底纹 + 徽记 + 明细 ───── */
.hc-face--back {
  transform: rotateY(180deg);
}
/* 艺术卡背（开卡期）：雕纹版面盖在数据卡背上；陈列亮灯后退场，翻背才见明细 */
.hc-face--cover {
  transform: rotateY(180deg);
  background-color: #081209;
}
.hc-cover-art {
  position: absolute;
  inset: 0;
  background-image: var(--grain), var(--cb);
  background-size: 180px 180px, 100% 100%;
  background-blend-mode: overlay, normal;
}
.hc-cover-head {
  position: absolute;
  top: calc(var(--u) * 4.6);
  left: calc(var(--u) * 5.4);
  right: calc(var(--u) * 5.4);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hc-cover-tag {
  font-size: calc(var(--u) * 3.4);
  font-weight: 700;
  letter-spacing: 0.16em;
}
.hc-cover-no {
  font-size: calc(var(--u) * 3);
  letter-spacing: 0.1em;
  color: rgba(255, 255, 255, 0.52);
}
.hc-fan--lit .hc-face--cover { display: none; }

.hc-back {
  position: absolute;
  inset: 0;
  padding: calc(var(--u) * 3);
  display: flex;
  flex-direction: column;
  border-radius: 11px;
  border: 1px solid color-mix(in srgb, var(--rc) 46%, transparent);
  overflow: hidden;
  /* 数据卡背垫着同一张雕纹版面：压暗到刚好能透出纹样，行数据在上面照常可读 */
  background-image:
    radial-gradient(120% 88% at 26% 8%, color-mix(in srgb, var(--rc) 24%, transparent), transparent 58%),
    linear-gradient(rgba(10, 22, 15, 0.82), rgba(8, 18, 12, 0.9)),
    var(--cb);
  background-size: auto, auto, 100% 100%;
  background-color: #0A1712;
}

.hc-back-head {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: calc(var(--u) * 1.6);
  border-bottom: 1px solid color-mix(in srgb, var(--rc) 32%, transparent);
}
.hc-back-tag {
  font-size: calc(var(--u) * 3.4);
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--rc);
}
.hc-back-no {
  font-size: calc(var(--u) * 3.2);
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.46);
}

.hc-back-body {
  position: relative;
  margin-top: calc(var(--u) * 2.4);
  display: flex;
  flex-direction: column;
  gap: calc(var(--u) * 1.5);
}
.hc-back-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: calc(var(--u) * 1.5);
}
.hc-back-k {
  font-size: calc(var(--u) * 3);
  letter-spacing: 0.12em;
  color: rgba(255, 255, 255, 0.44);
  flex: none;
}
.hc-back-v {
  font-size: calc(var(--u) * 3.6);
  font-weight: 700;
  color: #EAF6EF;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hc-back-note {
  position: relative;
  margin-top: auto;
  font-size: calc(var(--u) * 2.9);
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.56);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.hc-back-foot {
  position: relative;
  margin-top: calc(var(--u) * 1.8);
  padding-top: calc(var(--u) * 1.4);
  border-top: 1px solid color-mix(in srgb, var(--rc) 24%, transparent);
  font-size: calc(var(--u) * 2.6);
  letter-spacing: 0.2em;
  color: rgba(255, 255, 255, 0.3);
  text-align: center;
}

.hc-frame {
  position: absolute;
  inset: 0;
  padding: calc(var(--u) * 3);
  display: flex;
  flex-direction: column;
  gap: calc(var(--u) * 2);
  /* 印刷卡的底子：稀有度色从左上打光、颗粒当纸感，不再是一片平涂 */
  background-image:
    var(--grain),
    radial-gradient(130% 100% at 18% 0%, color-mix(in srgb, var(--rc) 32%, transparent), transparent 54%),
    linear-gradient(160deg, color-mix(in srgb, var(--rc) 24%, #0D1F15) 0%, #0B1A12 44%, #060F0A 100%);
  background-size: 180px 180px, auto, auto;
  background-blend-mode: overlay, normal, normal;
  border: 1px solid color-mix(in srgb, var(--rc) 42%, rgba(255, 255, 255, 0.06));
  border-radius: 11px;
  /* 上缘受光、下缘背光、内里微微收暗：卡有了厚度 */
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.13),
    inset 0 -1.5px 0 rgba(0, 0, 0, 0.55),
    inset 0 0 calc(var(--u) * 8) rgba(0, 0, 0, 0.32);
}
/* 内圈箔线：框中框，实体卡都有的那条 trim */
.hc-frame::before {
  content: '';
  position: absolute;
  inset: calc(var(--u) * 1.5);
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--rc) 55%, rgba(255, 255, 255, 0.08));
  box-shadow:
    0 0 calc(var(--u) * 2.5) color-mix(in srgb, var(--rc) 22%, transparent),
    inset 0 0 calc(var(--u) * 3) rgba(0, 0, 0, 0.3);
  pointer-events: none;
}

.hc-head { position: relative; display: flex; align-items: center; justify-content: space-between; padding: 0 calc(var(--u) * 0.8); }
/* 稀有度章：金属浮雕小方章，不是平色贴纸 */
.hc-rarity {
  font-size: calc(var(--u) * 3.6);
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #08110D;
  background: linear-gradient(180deg, color-mix(in srgb, var(--rc) 88%, #fff) 0%, var(--rc) 52%, color-mix(in srgb, var(--rc) 72%, #000) 100%);
  border-radius: 3px;
  padding: calc(var(--u) * 0.8) calc(var(--u) * 2);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    inset 0 -1px 0 rgba(0, 0, 0, 0.35),
    0 1px 3px rgba(0, 0, 0, 0.45),
    0 0 10px var(--rg);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.25);
}
.hc-no {
  font-size: calc(var(--u) * 3.8);
  color: rgba(255, 255, 255, 0.45);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.6);
}

.hc-art {
  position: relative;
  flex: 1;
  min-height: 0;
  border-radius: calc(var(--u) * 2.2);
  background: linear-gradient(180deg, #FDFEFD 0%, #EDF3EF 74%, #DDE7E1 100%);
  display: grid;
  place-items: center;
  overflow: hidden;
  /* 画窗被卡框压住一圈：内嵌阴影让画真的「装」在卡里 */
  box-shadow:
    inset 0 2px 6px rgba(0, 0, 0, 0.26),
    inset 0 0 0 1px rgba(0, 0, 0, 0.14),
    0 1px 0 rgba(255, 255, 255, 0.07);
}
/* 画窗釉面：一道固定的斜向印刷光泽 */
.hc-art::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(118deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 36%);
  pointer-events: none;
}
/* 表情原图完整显示，不做裁切 */
.hc-art-img { max-width: 88%; max-height: 88%; object-fit: contain; }
.hc-art-miss { font-size: calc(var(--u) * 3.4); color: rgba(0, 0, 0, 0.35); }
.hc-marks {
  display: flex;
  align-items: center;
  min-height: calc(var(--u) * 5);
  padding: 0 calc(var(--u) * 0.8);
}
/* 首刷：圈 1 + 字，和真实卡牌的 1st Edition 一个位置、一个体量 */
.hc-1st { display: inline-flex; align-items: center; gap: calc(var(--u) * 1.2); }
.hc-1st-o {
  width: calc(var(--u) * 4.4);
  height: calc(var(--u) * 4.4);
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  display: grid;
  place-items: center;
  font-style: normal;
  font-size: calc(var(--u) * 2.8);
  font-weight: 700;
  color: rgba(255, 255, 255, 0.92);
}
.hc-1st em {
  font-style: normal;
  font-size: calc(var(--u) * 2.9);
  letter-spacing: 0.16em;
  color: rgba(255, 255, 255, 0.75);
}
.hc-rv-mark {
  font-size: calc(var(--u) * 2.9);
  letter-spacing: 0.14em;
  color: #93C9FF;
}

/* 名条：一块受光的浅浮雕铭牌带 */
.hc-plate {
  margin: 0 calc(var(--u) * 0.2);
  padding: calc(var(--u) * 1.4) calc(var(--u) * 1.6);
  border-radius: calc(var(--u) * 1.3);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.055), rgba(255, 255, 255, 0.012));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.09),
    inset 0 0 0 1px rgba(0, 0, 0, 0.28);
}
.hc-name {
  font-size: calc(var(--u) * 4.4);
  line-height: 1.25;
  color: #EAF6EF;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.55);
}
/* 进度条：开槽的凹轨 + 发光的填充 */
.hc-bar {
  margin-top: calc(var(--u) * 1.4);
  height: calc(var(--u) * 1);
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.5);
  box-shadow:
    inset 0 1px 2px rgba(0, 0, 0, 0.65),
    0 1px 0 rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.hc-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--rc) 78%, #fff) 0%, var(--rc) 60%);
  box-shadow: 0 0 8px var(--rg), inset 0 -1px 0 rgba(0, 0, 0, 0.3);
}

.hc-foot { display: flex; align-items: baseline; gap: calc(var(--u) * 1.2); padding: 0 calc(var(--u) * 0.8) calc(var(--u) * 0.4); }
/* 主数字箔压：从高光到本色到暗部的金属渐层 */
.hc-count {
  font-size: calc(var(--u) * 7);
  line-height: 1;
  font-weight: 600;
  background: linear-gradient(180deg, #FFFFFF -14%, var(--rc) 58%, color-mix(in srgb, var(--rc) 55%, #000) 108%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 1px 0 rgba(0, 0, 0, 0.45));
}
.hc-count-u { font-size: calc(var(--u) * 3.5); color: rgba(255, 255, 255, 0.5); text-shadow: 0 1px 0 rgba(0, 0, 0, 0.5); }
.hc-share { margin-left: auto; font-size: calc(var(--u) * 3.2); color: rgba(255, 255, 255, 0.38); text-shadow: 0 1px 0 rgba(0, 0, 0, 0.5); }

/* 全息箔层：pokemon-cards-css 那套 —— 彩虹重复渐变 + 斜纹金属，
   background-blend-mode 混出油膜，再 color-dodge 打到卡面上，位置随指针走 */
.hc-shine {
  position: absolute;
  inset: 0;
  border-radius: 11px;
  background-image:
    repeating-linear-gradient(0deg,
      rgb(255, 119, 115) calc(5% * 1),
      rgba(255, 237, 95, 1) calc(5% * 2),
      rgba(168, 255, 95, 1) calc(5% * 3),
      rgba(131, 255, 247, 1) calc(5% * 4),
      rgba(120, 148, 255, 1) calc(5% * 5),
      rgb(216, 117, 255) calc(5% * 6),
      rgb(255, 119, 115) calc(5% * 7)),
    repeating-linear-gradient(133deg,
      #0e152e 0%, hsl(180, 10%, 60%) 3.8%, hsl(180, 29%, 66%) 4.5%,
      hsl(180, 10%, 60%) 5.2%, #0e152e 10%, #0e152e 12%),
    radial-gradient(farthest-corner circle at var(--px, 50%) var(--py, 50%),
      rgba(0, 0, 0, 0.1) 12%, rgba(0, 0, 0, 0.15) 20%, rgba(0, 0, 0, 0.25) 120%);
  background-blend-mode: exclusion, hue, hard-light;
  background-size: 500% 500%, 300% 300%, 200% 200%;
  background-position: var(--bgx, 50%) var(--bgy, 50%), calc(var(--bgx, 50%) * 0.4) calc(var(--bgy, 50%) * 0.5), center;
  mix-blend-mode: color-dodge;
  filter: brightness(0.82) contrast(2.6) saturate(0.7);
  /* --holo-boost 由 C 位定妆那一下的 gsap 推上去，做一次箔面爆闪 */
  opacity: calc(var(--holo, 0.3) + var(--holo-boost, 0) * 0.55);
  pointer-events: none;
  transition: opacity 240ms ease;
}
/* R 卡不该跟 UR 一样闪 */
.hc-card--r .hc-shine { filter: brightness(0.6) contrast(2.1) saturate(0.5); }
/* Reverse holo：真实卡牌里「图不闪、其余闪」，用工艺区分复刻卡，而不是再贴一个标签 */
.hc-card--rv .hc-shine {
  -webkit-mask-image: linear-gradient(#000 0 17%, transparent 21% 63%, #000 67% 100%);
  mask-image: linear-gradient(#000 0 17%, transparent 21% 63%, #000 67% 100%);
}
.hc-card--sr .hc-shine { filter: brightness(0.7) contrast(2.3) saturate(0.6); }

.hc-glare {
  position: absolute;
  inset: 0;
  border-radius: 11px;
  background-image: radial-gradient(farthest-corner circle at var(--px, 50%) var(--py, 50%),
    rgba(255, 255, 255, 0.7) 10%, rgba(255, 255, 255, 0.5) 22%, rgba(0, 0, 0, 0.55) 92%);
  mix-blend-mode: overlay;
  filter: brightness(0.95) contrast(1.35);
  opacity: 0.55;
  pointer-events: none;
}

.hc-avatar {
  width: calc(var(--u, 2.68px) * 6.4);
  height: calc(var(--u, 2.68px) * 6.4);
  border-radius: 5px;
  overflow: hidden;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.1);
  font-size: calc(var(--u, 2.68px) * 3.2);
  color: rgba(255, 255, 255, 0.6);
}
.hc-avatar img { width: 100%; height: 100%; object-fit: cover; }
.hc-avatar--lg { width: max(26px, 3.6cqmin); height: max(26px, 3.6cqmin); border-radius: 8px; font-size: max(11px, 1.5cqmin); }

/* ---------- 底部条 ---------- */
/* ---------- 档案卡的卡面 ---------- */
/* 和表情卡同构：同一个浅色图窗，里面放一件插画，数据全部退到名条和底注。
   之前把图表直接塞进卡框，主体成了坐标轴和数字，和表情卡不是一个物种。 */

/* 时段卡：24 小时表盘 */
.hc-dial { width: 82%; height: 82%; }
.hc-dial-ring { fill: none; stroke: rgba(0, 0, 0, 0.1); stroke-width: 0.8; }
.hc-dial-tick { stroke: #2C3A52; stroke-width: 2.6; stroke-linecap: round; }
.hc-dial-tick.is-peak { stroke: var(--rc); stroke-width: 3.4; }
.hc-dial-hand { stroke: #16202E; stroke-width: 2.6; stroke-linecap: round; }
.hc-dial-hub { fill: #16202E; }

/* 对手卡：圆形肖像章 */
.hc-portrait {
  width: 72%;
  aspect-ratio: 1;
  border-radius: 999px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.06);
  box-shadow: 0 0 0 calc(var(--u) * 0.8) rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.5);
  font-size: calc(var(--u) * 18);
  color: rgba(0, 0, 0, 0.45);
}
.hc-portrait img { width: 100%; height: 100%; object-fit: cover; }

/* ---------- 卡片详情 ---------- */
.hc-detail {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  padding: calc(var(--svh) * 5) calc(var(--svw) * 4);
  background: rgba(4, 8, 18, 0.72);
  backdrop-filter: blur(14px);
}
.hc-detail-panel {
  position: relative;
  width: min(760px, 100%);
  max-height: calc(var(--svh) * 86);
  overflow: auto;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(160deg, #101A2C, #0A121F 60%, #070C16);
  box-shadow: 0 30px 70px rgba(0, 0, 0, 0.6);
  padding: clamp(18px, calc(var(--svh) * 3), 30px);
  color: #E8F0FA;
}
.hc-detail-close {
  position: absolute;
  top: 12px;
  right: 14px;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}
.hc-detail-close:hover { background: rgba(255, 255, 255, 0.16); color: #fff; }

.hc-detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: clamp(12px, calc(var(--svh) * 2), 20px); }
.hc-detail-tag {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #08111D;
  background: var(--rc, #4ADE80);
  border-radius: 4px;
  padding: 3px 8px;
}
.hc-detail-kind { font-size: 11px; letter-spacing: 0.16em; color: rgba(255, 255, 255, 0.42); }

.hc-detail-body { display: flex; gap: clamp(14px, calc(var(--svw) * 2.4), 26px); align-items: flex-start; }
.hc-detail-art {
  flex: 0 0 clamp(140px, calc(var(--svw) * 22), 220px);
  aspect-ratio: 1;
  border-radius: 12px;
  background: linear-gradient(180deg, #F6FAF7, #DFE9E3);
  display: grid;
  place-items: center;
  overflow: hidden;
}
.hc-detail-art img { max-width: 86%; max-height: 86%; object-fit: contain; }
.hc-detail-art .hc-detail-avatar { width: 100%; height: 100%; max-width: none; max-height: none; object-fit: cover; }

.hc-detail-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.hc-detail-text--full { flex-basis: 100%; }
.hc-detail-lead { font-size: clamp(13px, calc(var(--svh) * 1.6), 15px); line-height: 1.85; color: rgba(255, 255, 255, 0.74); }
.hc-detail-lead b { color: #fff; font-weight: 600; }
.hc-detail-k {
  margin-top: 6px;
  font-size: 10px;
  letter-spacing: 0.24em;
  color: rgba(255, 255, 255, 0.36);
}

.hc-detail-list { display: flex; flex-direction: column; gap: 7px; }
.hc-detail-list li { display: flex; align-items: center; gap: 10px; }
.hc-detail-glyph {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  font-size: 18px;
  line-height: 1;
}
.hc-detail-glyph img { width: 100%; height: 100%; object-fit: contain; }
.hc-detail-name { flex: 0 0 clamp(64px, calc(var(--svw) * 12), 120px); font-size: 12px; color: rgba(255, 255, 255, 0.66); }
.hc-detail-bar { flex: 1; height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
.hc-detail-bar i { display: block; height: 100%; border-radius: 3px; }
.hc-detail-num { flex: 0 0 56px; text-align: right; font-size: 12px; color: rgba(255, 255, 255, 0.8); }

.hc-detail-hours { display: flex; align-items: flex-end; gap: 3px; height: 68px; }
.hc-detail-hours span { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 3px; }
.hc-detail-hours i { display: block; width: 100%; border-radius: 2px; background: rgba(74, 222, 128, 0.45); }
.hc-detail-hours .is-peak i { background: #FFCE4A; }
.hc-detail-hours em { font-style: normal; font-size: 9px; color: rgba(255, 255, 255, 0.32); }

.detail-fade-enter-active, .detail-fade-leave-active { transition: opacity 220ms ease; }
.detail-fade-enter-active .hc-detail-panel { transition: transform 260ms cubic-bezier(0.22, 1, 0.36, 1); }
.detail-fade-enter-from, .detail-fade-leave-to { opacity: 0; }
.detail-fade-enter-from .hc-detail-panel { transform: translateY(16px) scale(0.97); }

/* ---------- 铭牌 ---------- */
.hc-plaque {
  position: absolute;
  left: 50%;
  bottom: max(6px, 0.9cqh);
  transform: translate(-50%, 10px);
  z-index: 70;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: max(5px, 0.75cqh);
  opacity: 0;
  transition: opacity 900ms ease 500ms, transform 900ms cubic-bezier(0.22, 1, 0.36, 1) 500ms;
  pointer-events: none;
}
.hc-plaque--on { opacity: 1; transform: translate(-50%, 0); }
.hc-plaque-rule {
  width: 9cqmin;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
}
.hc-plaque-line {
  font-size: max(10px, 1.3cqmin);
  letter-spacing: 0.14em;
  color: rgba(255, 255, 255, 0.5);
  white-space: nowrap;
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.65);
}

/* 竖幅下铭牌只有九百像素可用：放开 nowrap，宁可折成两行也不许被裁 */
[data-frame-tier="portrait"] .hc-plaque-line,
[data-frame-tier="tall"] .hc-plaque-line {
  white-space: normal;
  text-align: center;
  max-width: 92cqw;
  line-height: 1.5;
}

/* ══════════════ 竖幅重排 ══════════════
   舞台上这些小字原来一律挂 cqmin（= 竖幅里的短边 = 画幅宽）的 1.1~1.9%，
   在 1600 高的 9:16 上换算下来只有 10~17 设计像素，分享到手机上根本读不出来。
   竖幅统一改挂 cqw 并整体上调到 1.8~3.4%：字号只跟宽度轴走，舞台变高不会再
   把字撑大、把栏挤窄。横幅（wide）一律不进这一段，逐像素不变。 */
[data-frame-tier="portrait"] .hc-guide-text,
[data-frame-tier="tall"] .hc-guide-text { font-size: 2.2cqw; }

[data-frame-tier="portrait"] .hc-stack-label,
[data-frame-tier="tall"] .hc-stack-label { font-size: 1.8cqw; }

[data-frame-tier="portrait"] .hc-taphint,
[data-frame-tier="tall"] .hc-taphint { font-size: 2cqw; }

[data-frame-tier="portrait"] .hc-cap,
[data-frame-tier="tall"] .hc-cap { width: min(88cqw, 92%); }
[data-frame-tier="portrait"] .hc-cap-t,
[data-frame-tier="tall"] .hc-cap-t { font-size: 3.4cqw; }
[data-frame-tier="portrait"] .hc-cap-l,
[data-frame-tier="tall"] .hc-cap-l { margin-top: 1.2cqw; font-size: 2.4cqw; }

[data-frame-tier="portrait"] .hc-plaque-line,
[data-frame-tier="tall"] .hc-plaque-line { font-size: 2cqw; }
[data-frame-tier="portrait"] .hc-plaque-rule,
[data-frame-tier="tall"] .hc-plaque-rule { width: 14cqw; }

/* 撕口指引原来钉在中心下方 24cqh，卡包在竖幅里放大之后正好压在包身上；
   竖幅改成挂底边，落在卡包和画幅下沿之间的空带里 */
[data-frame-tier="portrait"] .hc-guide,
[data-frame-tier="tall"] .hc-guide {
  top: auto;
  bottom: max(24px, 4.5cqh);
  transform: translateX(-50%);
}

/* 空态（今年没几张表情）也别用 14/16px 的正文 */
[data-frame-tier="portrait"] .hc-empty-box,
[data-frame-tier="tall"] .hc-empty-box { padding: 3cqw 3.6cqw; }
[data-frame-tier="portrait"] .hc-empty-box > :first-child,
[data-frame-tier="tall"] .hc-empty-box > :first-child { font-size: 3.2cqw; }
[data-frame-tier="portrait"] .hc-empty-box > :last-child,
[data-frame-tier="tall"] .hc-empty-box > :last-child { font-size: 2.2cqw; }

/* ── 卡片详情浮层 ──
   这一层 teleport 到舞台 portal，不在 .hc-root 里，cq* 会掉到窗口去解析，
   所以尺寸一律走舞台自己的宽度轴单位 --svw（= 画幅设计宽 / 100）。
   原来的 11/12/13~15px 是按 1600 宽的横幅定的，搬到 900 宽的竖幅上等于对半糊。 */
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-panel {
  width: min(100%, calc(var(--svw) * 94));
  padding: calc(var(--svw) * 3.4);
}
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-close {
  width: calc(var(--svw) * 4.6);
  height: calc(var(--svw) * 4.6);
  font-size: calc(var(--svw) * 2);
}
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-tag {
  font-size: calc(var(--svw) * 1.9);
  padding: calc(var(--svw) * 0.5) calc(var(--svw) * 1.2);
}
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-kind { font-size: calc(var(--svw) * 1.9); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-lead { font-size: calc(var(--svw) * 2.4); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-k { font-size: calc(var(--svw) * 1.8); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-name {
  flex: 0 0 calc(var(--svw) * 16);
  font-size: calc(var(--svw) * 2.1);
}
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-num {
  flex: 0 0 calc(var(--svw) * 8);
  font-size: calc(var(--svw) * 2.1);
}
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-glyph {
  width: calc(var(--svw) * 4);
  height: calc(var(--svw) * 4);
  font-size: calc(var(--svw) * 2.8);
}
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-bar { height: calc(var(--svw) * 1); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-list { gap: calc(var(--svw) * 1.2); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-list li { gap: calc(var(--svw) * 1.4); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-hours { height: calc(var(--svw) * 11); }
[data-frame-tier]:not([data-frame-tier="wide"]) .hc-detail-hours em { font-size: calc(var(--svw) * 1.6); }
/* 竖幅里「大图在左、文字在右」只剩两条窄栏：改成上下堆叠，文字拿满整宽 */
[data-frame-tier="portrait"] .hc-detail-body,
[data-frame-tier="tall"] .hc-detail-body {
  flex-direction: column;
  align-items: center;
  gap: calc(var(--svw) * 2.6);
}
[data-frame-tier="portrait"] .hc-detail-art,
[data-frame-tier="tall"] .hc-detail-art { flex: 0 0 auto; width: calc(var(--svw) * 36); }
[data-frame-tier="portrait"] .hc-detail-text,
[data-frame-tier="tall"] .hc-detail-text { width: 100%; gap: calc(var(--svw) * 1.4); }

@media (prefers-reduced-motion: reduce) {
  .hc-pack-foil { animation: none; }
  .hc-slot, .hc-card { transition: none; }
  .hc-leak, .hc-taphint, .hc-card::after, .hc-face--cover::after, .hc-stack-card.is-top::before { animation: none; }
}
</style>
