<template>
  <!--
    末页《一屏全览 · 亲和版》＋ 玻璃工坊层（2026-07-28 应用户要求加回交互与点缀）
    设计纪律（锁死，改动前先看这里）：
      · 本页不画自己的不透明底：deck 共用的 WrappedDeckBackground（光斑 + 网格 + 噪点）
        直接透上来 —— 磨砂玻璃（backdrop-filter）糊的就是它，别再往块底下加不透明色
      · 无 WebGL、无 canvas、无 rAF 循环（指针跟随只在 pointermove 里 rAF 批一帧，无常驻循环）
      · 无任何点击展开 / 键盘导航 / 提示引导元素
      · 悬停两件事：① 就地换读数（块内本来就有的那一行读数换成当前格子的明细，
        移开换回；绝不新增浮层 / tooltip，读数行一律 nowrap + ellipsis，块高不许跳）
        ② 材质响应（光标处玻璃反光 + 边框光晕 + ≤2.4° 倾斜），全部走 CSS 变量
      · 点缀铁律：**块里不放任何大面积 SVG 水印**——细线雕纹和实体浮雕两版
        都做过、都被用户点名「太廉价」摘除（2026-07-28）。允许的点缀只有
        实体小构件（键帽 / 金冠 / 奖牌 / 箔章 / 托盘槽 / 月亮流星）与光效
        （扫光 / 呼吸 / 活版年份）。装饰一律进 .deco（inset:0 + overflow:hidden，
        pointer-events:none），绝不用会撑大 scrollWidth 的 translate 常驻位移
        （流星只许往左下飞——scrollWidth 只量右/下溢出）
      · 琥珀只许出现在 ≤28px 的构件上（王冠 / 奖牌 / 声波 / 发丝线可以，大面积雕纹不行）
      · 全版不写 title 属性；alt 一律写死不含 PII
      · 隐私节点整体淡入，绝不逐字拆分（逐字 blur 会在字与字之间留清晰缝隙，拼起来仍认得出来）
      · 强调色只用 deck 已有的 5 支：#07C160 / #F2AA00 / #9FB0DA / #95EC69 / #FFE9A3
  -->
  <div v-if="isOk" ref="stageEl" class="wrap-final">
    <div ref="sheetEl" class="sheet-final" :class="{ 'is-intro': introRunning }">
      <!-- ═══════════ A1 全年总量 ═══════════ -->
      <section class="blk blk--qty b-a1" aria-labelledby="k-a1">
        <div class="head-line">
          <div class="kicker" id="k-a1">全年发出</div>
          <div v-if="sentToContacts > 0" class="kicker kicker--r">发给 {{ fmt(sentToContacts) }} 个人</div>
        </div>
        <div class="mega-row">
          <span class="mega wrapped-number">{{ cuTotal.display.value }}</span>
          <span class="mega-unit">条</span>
        </div>
        <p class="line one">{{ a1Line }}<span class="whisper">一来一回之间，一年就这样过完了。</span></p>
        <div class="mgrid mgrid--inline mgrid--push">
          <div class="inset mcell">
            <span class="dt">活跃</span>
            <span class="dd wrapped-number">{{ fmt(activeDays) }} 天</span>
          </div>
          <div class="inset mcell">
            <span class="dt">最长连续</span>
            <span class="dd wrapped-number">{{ fmt(streakDays) }} 天</span>
          </div>
          <div class="inset mcell">
            <span class="dt">新朋友</span>
            <span class="dd wrapped-number">{{ fmt(addedFriends) }} 位</span>
          </div>
          <div class="inset mcell">
            <span class="dt">图片视频</span>
            <span class="dd wrapped-number">{{ fmt(sentMediaCount) }} 条</span>
          </div>
        </div>
        <div v-if="streakRange" class="foot-note streak-range">最长的那一段：{{ streakRange }}</div>
      </section>

      <!-- ═══════════ A2 365 天年历 ═══════════ -->
      <section class="blk b-a2" aria-labelledby="k-a2">
        <!-- 缓慢扫过年历的一道光：背景位移实现，不用 transform，不撑 scrollWidth -->
        <div class="deco" aria-hidden="true"><i class="yr-shine"></i></div>
        <div class="head-line">
          <div class="kicker" id="k-a2">{{ year }} 年的 365 天</div>
          <div class="ghost-year">{{ year }}</div>
        </div>
        <template v-if="hasYearGrid">
          <div class="yr-months">
            <span v-for="m in 12" :key="m">{{ m }}月</span>
          </div>
          <div class="yr-body">
            <div class="yr-week">
              <span>一</span><span></span><span>三</span><span></span><span>五</span><span></span><span></span>
            </div>
            <!-- 367 个格子不各绑一个 handler：容器上一个 pointerover 事件委托，从 data-d 取第几天 -->
            <div
              class="yr-grid"
              role="img"
              :aria-label="yrGridLabel"
              @pointerover="onYearOver"
              @pointerleave="clearYearHover"
              @pointercancel="clearYearHover"
            >
              <i
                v-for="c in yearCells"
                :key="c.k"
                class="yr-cell"
                :class="[`lv${c.lv}`, { 'is-peak': c.peak }]"
                :data-d="c.d"
                aria-hidden="true"
              ></i>
            </div>
          </div>
          <div class="yr-legend">
            <span class="lg">少</span>
            <i class="lgc lv0"></i><i class="lgc lv1"></i><i class="lgc lv2"></i><i class="lgc lv3"></i><i class="lgc lv4"></i>
            <span class="lg">多</span>
            <!-- 就地读数：悬停某一天换成那天的明细，移开换回全年结论 -->
            <span class="lg lg-read">{{ yearReadout }}</span>
          </div>
        </template>
        <div v-else class="void-line">今年还没排出完整的一年。</div>
      </section>

      <!-- ═══════════ A3 最疯的一天 ═══════════ -->
      <section class="blk b-a3" aria-labelledby="k-a3">
        <div class="head-line">
          <div class="kicker" id="k-a3">最疯的一天</div>
          <!-- 日期挪到报头右侧：省下一整行，留给下面那条 24 小时跨度尺 -->
          <div v-if="hasPeakDay" class="kicker kicker--r">{{ peakDateText }} · {{ peakWeekday }}</div>
        </div>
        <template v-if="hasPeakDay">
          <div class="big-row">
            <span class="big wrapped-number">{{ cuPeak.display.value }}</span>
            <span class="big-unit">条</span>
            <span v-if="peakMultiple > 0" class="tag tag--qty">日均的 {{ peakMultiple }} 倍</span>
            <span v-if="peakShare" class="tag tag--time">占全年 {{ peakShare }}%</span>
          </div>
          <div v-if="peakContact" class="who-row">
            <span class="av av24">
              <img
                v-if="peakContactAvatar"
                class="wrapped-privacy-avatar"
                :src="peakContactAvatar"
                alt="联系人头像"
                draggable="false"
              />
              <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(peakContact.displayName) }}</span>
            </span>
            <span class="nm one wrapped-privacy-name">{{ peakContact.displayName }}</span>
            <span class="dd">{{ fmt(peakContact.messages) }} 条</span>
          </div>
          <!-- 那天的 24 小时跨度尺：把「第一句 → 最后一句」画成一段，块中部不再空着 -->
          <div v-if="peakSpan" class="a3-span">
            <i class="span-track">
              <b class="span-fill" :style="{ left: peakSpan.left + '%', width: peakSpan.width + '%' }"></b>
            </i>
            <div class="span-cap">
              <span class="dt">00:00</span>
              <span class="dt one span-cap-m">{{ peakSpanText }}</span>
              <span class="dt">24:00</span>
            </div>
          </div>
          <div class="quote-2">
            <div class="inset quo">
              <div class="dt">那天的第一句 {{ peakDay.firstTime }}</div>
              <div class="qt two wrapped-privacy-message">{{ peakDay.firstText }}</div>
            </div>
            <div class="inset quo">
              <div class="dt">那天的最后一句 {{ peakDay.lastTime }}</div>
              <div class="qt two wrapped-privacy-message">{{ peakDay.lastText }}</div>
            </div>
          </div>
        </template>
        <div v-else class="void-line">今年每天都差不多。</div>
      </section>

      <!-- ═══════════ B1 年度搭子 ═══════════ -->
      <section class="blk blk--ppl b-b1" aria-labelledby="k-b1">
        <div class="head-line">
          <div class="kicker" id="k-b1">年度搭子</div>
          <div v-if="hasBuddy" class="kicker kicker--r whisper-r">今年话最多的一对</div>
        </div>
        <template v-if="hasBuddy">
          <div class="who-row buddy-top">
            <span class="av av48 av--ring">
              <img
                v-if="buddyAvatar"
                class="wrapped-privacy-avatar"
                :src="buddyAvatar"
                alt="联系人头像"
                draggable="false"
              />
              <span v-else class="av-ini wrapped-privacy-avatar">{{ buddyInitial }}</span>
            </span>
            <span class="nm nm-2 wrapped-privacy-name">{{ buddyName }}</span>
          </div>
          <div class="big-row">
            <span class="big wrapped-number">{{ cuBuddy.display.value }}</span>
            <span class="big-unit">条</span>
          </div>
          <i class="duo-bar" :style="{ '--out': buddyOutPct + '%' }"></i>
          <div class="duo-legend">
            <span>你发 <b class="wrapped-number">{{ fmt(buddyOut) }}</b></span>
            <span>TA 发 <b class="wrapped-number">{{ fmt(buddyIn) }}</b></span>
          </div>
          <div class="mgrid mgrid--inline" :class="buddyReplyCount > 0 ? 'mgrid--3' : ''">
            <div class="inset mcell">
              <span class="dt">连续</span>
              <span class="dd wrapped-number">{{ fmt(buddyStreak) }} 天</span>
            </div>
            <div class="inset mcell">
              <span class="dt">常在</span>
              <span class="dd wrapped-number">{{ buddyPeakLabel }}</span>
            </div>
            <div v-if="buddyReplyCount > 0" class="inset mcell">
              <span class="dt">接话</span>
              <span class="dd wrapped-number">{{ fmt(buddyReplyCount) }} 次</span>
            </div>
          </div>
          <!-- 平均值挪到 D1 的共用刻度上当参照，这里只留两端极值，避免同一句话印两遍 -->
          <div class="foot-note buddy-extremes">最快 {{ buddyFastText }} 回 · 最慢等了 {{ buddySlowText }}</div>
        </template>
        <div v-else class="void-line">今年的消息分得很散，没有特别集中的一个人。</div>
      </section>

      <!-- ═══════════ B2 十二个月的主演 ═══════════ -->
      <section class="blk blk--ppl b-b2" aria-labelledby="k-b2">
        <div class="head-line">
          <div class="kicker" id="k-b2">十二个月的主演</div>
          <div v-if="monthsWithWinner > 0" class="kicker kicker--r">12 个月里有 {{ monthsWithWinner }} 个月排上了主演</div>
        </div>
        <!-- 12 个月同样走事件委托：从 data-i 取第几个月 -->
        <div
          v-if="monthsWithWinner > 0"
          class="mo-row"
          @pointerover="onMonthOver"
          @pointerleave="clearMonthHover"
          @pointercancel="clearMonthHover"
        >
          <div v-for="(m, mi) in monthly" :key="m.month" class="mo" :data-i="mi">
            <span class="mo-m">{{ m.month }}月</span>
            <span class="av mo-av" :class="{ 'av--ring': isChampMonth(m) }">
              <img
                v-if="monthAvatar(m)"
                class="wrapped-privacy-avatar"
                :src="monthAvatar(m)"
                alt="联系人头像"
                draggable="false"
              />
              <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(m.displayName) }}</span>
            </span>
            <span class="nm mo-nm one wrapped-privacy-name">{{ shortName(m.displayName) }}</span>
            <!-- 月度消息量条：让这一排从「头像列表」变成有起伏的年历 -->
            <i class="mo-bar" :class="{ 'is-hot': isHotMonth(m) }">
              <b :style="{ width: monthPct(m) + '%' }"></b>
            </i>
          </div>
        </div>
        <div v-if="champion" class="inset champ">
          <span class="champ-avw">
            <!-- 12 个月里赢得最多的人：一顶 14px 的金冠浮雕（渐变金 + 冠底座 + 高光），琥珀构件尺寸红线之内 -->
            <svg class="crown" viewBox="0 0 20 14" aria-hidden="true">
              <defs>
                <linearGradient id="c7crown" x1="0%" y1="0%" x2="30%" y2="100%">
                  <stop offset="0%" stop-color="#FFE9A3" />
                  <stop offset="48%" stop-color="#F2AA00" />
                  <stop offset="100%" stop-color="#B87F05" />
                </linearGradient>
              </defs>
              <path d="M2 12 L1.4 4.6 L6 8 L10 1.6 L14 8 L18.6 4.6 L18 12 Z" fill="url(#c7crown)" />
              <rect x="2" y="10.6" width="16" height="2.2" rx="1" fill="#B87F05" />
              <circle cx="1.6" cy="3.4" r="1.15" fill="url(#c7crown)" />
              <circle cx="10" cy="1.4" r="1.15" fill="url(#c7crown)" />
              <circle cx="18.4" cy="3.4" r="1.15" fill="url(#c7crown)" />
              <path d="M3.2 10.2 L2.9 6.4" stroke="#FFF6D8" stroke-width="0.8" stroke-linecap="round" opacity="0.8" />
              <circle cx="9.6" cy="1.1" r="0.4" fill="#FFFFFF" opacity="0.9" />
            </svg>
            <span class="av av26">
              <img
                v-if="championAvatar"
                class="wrapped-privacy-avatar"
                :src="championAvatar"
                alt="联系人头像"
                draggable="false"
              />
              <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(champion.displayName) }}</span>
            </span>
          </span>
          <span class="champ-t">年度主演 <b class="wrapped-privacy-name">{{ champion.displayName }}</b> · {{ champion.monthsWon }} 个月</span>
          <!-- 就地读数：悬停某个月的量条换成那个月的主演与条数 -->
          <span v-if="monthReadout" class="dt champ-r one">
            {{ monthReadout.month }}月 · <b v-if="monthReadout.name" class="wrapped-privacy-name">{{ monthReadout.name }}</b><template v-else>没有主演</template><template v-if="monthReadout.count > 0"> · {{ fmt(monthReadout.count) }} 条</template>
          </span>
          <span v-else-if="hottestMonth" class="dt champ-r one">最热 {{ hottestMonth.month }} 月 · {{ fmt(hottestMonth.messages) }} 条</span>
        </div>
        <div v-else class="foot-note one">
          <template v-if="monthReadout">{{ monthReadout.month }}月 · <b v-if="monthReadout.name" class="wrapped-privacy-name">{{ monthReadout.name }}</b><template v-else>没有主演</template><template v-if="monthReadout.count > 0"> · {{ fmt(monthReadout.count) }} 条</template></template>
          <template v-else>十二个月里，每个月的名字都不一样。</template>
        </div>
      </section>

      <!-- ═══════════ B3 深夜 ═══════════ -->
      <section class="blk blk--night b-b3" aria-labelledby="k-b3">
        <!-- 星空层：只画光，不含任何人的信息，隐私永远只走 CSS 一条路径。
             sky-drift 比 sky 四边各大 12px，指针视差只在这层内位移，块的 scrollWidth 不受影响；
             流星固定往左下飞（scrollWidth 只量右/下溢出，往左飞怎么飞都安全）。 -->
        <div v-if="hasNight" class="sky" aria-hidden="true">
          <div class="sky-drift">
            <i v-for="(st, i) in nightStars" :key="i" class="star" :style="st"></i>
            <svg class="moon" viewBox="0 0 36 36">
              <circle class="moon-halo" cx="18" cy="18" r="16" />
              <path class="moon-body" d="M23.5 5.5 a13.5 13.5 0 1 0 7 21.5 a11 11 0 0 1 -7 -21.5 Z" />
            </svg>
            <i v-if="!reduced" class="shoot"></i>
          </div>
        </div>
        <div class="kicker" id="k-b3">深夜</div>
        <template v-if="hasNight">
          <div v-if="nightPartner" class="who-row">
            <span class="av av36">
              <img
                v-if="nightPartnerAvatar"
                class="wrapped-privacy-avatar"
                :src="nightPartnerAvatar"
                alt="联系人头像"
                draggable="false"
              />
              <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(nightPartner.displayName) }}</span>
            </span>
            <span class="col">
              <span class="nm one wrapped-privacy-name">{{ nightPartner.displayName }}</span>
              <span class="dt">陪你点亮 {{ nightShare }}% 的深夜</span>
            </span>
          </div>
          <div class="mgrid mgrid--inline">
            <div class="inset mcell mcell--wide">
              <span class="dt">0–6 点共</span>
              <span class="dd wrapped-number">{{ fmt(nightTotal) }} 条</span>
            </div>
            <div class="inset mcell">
              <span class="dt">你发出</span>
              <span class="dd wrapped-number">{{ fmt(myNightMessages) }} 条</span>
            </div>
            <div class="inset mcell">
              <span class="dt">对方发出</span>
              <span class="dd wrapped-number">{{ fmt(othersNightMessages) }} 条</span>
            </div>
          </div>
          <template v-if="night">
            <div class="dt night-when" :class="{ 'night-when--mine': night.fromMe }">
              {{ night.date }} {{ night.time }}，<span :class="{ 'wrapped-privacy-name': nightSpeakerIsName }">{{ nightSpeaker }}</span>说：
            </div>
            <div class="bubble two wrapped-privacy-message" :class="{ 'bubble--mine': night.fromMe }">{{ night.content }}</div>
          </template>
        </template>
        <div v-else class="void-line">今年你几乎不在深夜说话。</div>
      </section>

      <!-- ═══════════ C1 作息切片 ═══════════ -->
      <section class="blk blk--time b-c1" aria-labelledby="k-c1">
        <div class="head-line">
          <div class="kicker" id="k-c1">作息切片</div>
          <!-- 年度人格只在页脚出现一次：它是由回复速度/深夜占比等多个维度合出来的，
               不是这一块的产物，两处都挂会变成重复标签。
               下面这一行是本块的读数位：四个指标行不动，悬停明细就地换在这里。 -->
          <div v-if="matrixTotal > 0" class="kicker kicker--r">{{ matrixReadout }}</div>
        </div>
        <template v-if="matrixTotal > 0">
          <div class="hh-body">
            <div class="hh-week">
              <span v-for="(w, i) in weekdayLabels" :key="i">{{ w }}</span>
            </div>
            <!-- 168 个格子同样只有一个 handler：容器委托，从 data-i 反算「周几 × 第几个钟点」 -->
            <div
              class="hh-grid"
              role="img"
              :aria-label="hhGridLabel"
              @pointerover="onMatrixOver"
              @pointerleave="clearMatrixHover"
              @pointercancel="clearMatrixHover"
            >
              <i
                v-for="(lv, i) in matrixCells"
                :key="i"
                class="hh-cell"
                :class="`lv${lv}`"
                :data-i="i"
                aria-hidden="true"
              ></i>
            </div>
          </div>
          <div class="hh-axis">
            <span v-for="h in HOUR_AXIS" :key="h">{{ h }}</span>
          </div>
          <div class="rhythm-metrics">
            <div><span class="dt">最常亮起</span><span class="dd">{{ mostActiveWeekdayName }} {{ pad2(mostActiveHour) }}:00</span></div>
            <div><span class="dt">最安静</span><span class="dd">{{ pad2(quietHour) }}:00 · 仅 {{ fmt(quietCount) }} 条</span></div>
            <div><span class="dt">深夜指数</span><span class="dd">{{ nightPct }}%</span></div>
            <div><span class="dt">工作日 : 周末</span><span class="dd">{{ weekendRatio }} : 1</span></div>
          </div>
        </template>
        <div v-else class="void-line">今年的消息太少，排不出作息。</div>
      </section>

      <!-- ═══════════ C2 你说的话 ═══════════ -->
      <section class="blk blk--qty b-c2" aria-labelledby="k-c2">
        <div class="kicker" id="k-c2">你说的话</div>
        <div class="big-row">
          <span class="big wrapped-number">{{ cuChars.display.value }}</span>
          <span class="big-unit">个字</span>
          <!-- 书名接在数字同一行：省下一整行留给下面的 A4 / 最长语音 -->
          <span class="big-lead one">{{ charsLine }}</span>
          <!-- 常按的键靠这一行右端：同样的字，改印成三枚可以按下去的小键帽 -->
          <span v-if="topKeys.length" class="big-tail big-tail--keys">常按
            <kbd v-for="k in topKeys" :key="String(k?.key)" class="keycap"><span>{{ k.key }}</span></kbd>
          </span>
        </div>
        <div class="mgrid mgrid--inline">
          <div class="inset mcell">
            <span class="dt">收到</span>
            <span class="dd wrapped-number">{{ fmt(receivedChars) }} 字</span>
          </div>
          <div class="inset mcell">
            <span class="dt">敲了</span>
            <span class="dd wrapped-number">{{ fmt(keyHits) }} 次</span>
          </div>
          <!-- 语音：发出 / 收到 两侧都要有，缺一侧就只留有数的那一侧 -->
          <div v-if="voiceSentCount > 0" class="inset mcell">
            <span class="dt">语音发出</span>
            <span class="dd wrapped-number">{{ fmt(voiceSentCount) }} 条 · {{ voiceSentDur }}</span>
          </div>
          <div v-if="voiceRecvCount > 0" class="inset mcell">
            <span class="dt">语音收到</span>
            <span class="dd wrapped-number">{{ fmt(voiceRecvCount) }} 条 · {{ voiceRecvDur }}</span>
          </div>
          <div v-if="hasCalls" class="inset mcell">
            <span class="dt">通话</span>
            <span class="dd wrapped-number">{{ callsDurText }}</span>
          </div>
          <div v-if="callsAnswerText" class="inset mcell">
            <span class="dt">{{ callsAnswerLabel }}</span>
            <span class="dd wrapped-number">{{ callsAnswerText }}</span>
          </div>
        </div>
        <!-- 两条脚注并成一行：左边 A4 换算，右边语音/通话，中间由 space-between 撑开，不挨着 -->
        <div v-if="c2Foot || receivedA4Text || voiceLongest" class="c2-foot foot-split">
          <span v-if="receivedA4Text" class="foot-note one">{{ receivedA4Text }}</span>
          <span v-if="c2Foot || voiceLongest" class="foot-note one foot-r">
            <template v-if="c2Foot">{{ c2Foot }}</template>
            <template v-if="voiceLongest">
              <template v-if="c2Foot"> · </template>最长一条语音 {{ voiceLongestDur }}<template v-if="voiceLongest.name">，{{ voiceLongest.lead }} <b class="wrapped-privacy-name">{{ voiceLongest.name }}</b></template><template v-if="voiceLongest.date"> · {{ voiceLongest.date }}</template>
            </template>
          </span>
        </div>
      </section>

      <!-- ═══════════ C3 年度口头禅 ═══════════ -->
      <section class="blk blk--ppl b-c3" aria-labelledby="k-c3">
        <div class="kicker" id="k-c3">年度口头禅</div>
        <template v-if="heroWord">
          <div class="quote-hero">
            <span class="qm">“</span><span class="qw one wrapped-privacy-keyword">{{ heroWord }}</span>
          </div>
          <div class="big-row">
            <span class="big-lead">说了</span>
            <span class="big wrapped-number">{{ cuKeyword.display.value }}</span>
            <span class="big-unit">次</span>
          </div>
          <!-- 口头禅总量条：八句话各占多宽，一眼看出「ok」把其余压得多扁 -->
          <div
            v-if="kwStack.length"
            class="kw-stack"
            role="img"
            :aria-label="kwStackLabel"
            @pointerover="onKwOver"
            @pointerleave="clearKwHover"
            @pointercancel="clearKwHover"
          >
            <i
              v-for="(s, si) in kwStack"
              :key="s.k"
              class="kw-seg"
              :class="s.hero ? 'kw-hero' : 'kw-t' + s.tier"
              :style="{ width: s.pct + '%' }"
              :data-i="si"
              aria-hidden="true"
            ></i>
          </div>
          <div class="chips">
            <span v-for="k in kwChips" :key="k.word" class="chip" :class="'kw-t' + k.tier">
              <b class="wrapped-privacy-keyword">{{ k.word }}</b> {{ fmt(k.count) }}
            </span>
          </div>
          <!-- 就地读数：悬停总量条的某一段换成那个词的次数 -->
          <div v-if="kwFoot || kwStack.length" class="foot-note one kw-read">
            <template v-if="kwReadout">「<b class="wrapped-privacy-keyword">{{ kwReadout.word }}</b>」× {{ fmt(kwReadout.count) }} 次</template>
            <template v-else>{{ kwFoot }}</template>
          </div>
        </template>
        <div v-else class="void-line">你没有固定的口头禅，每句都重新想过。</div>
      </section>

      <!-- ═══════════ D1 回复速度 ═══════════ -->
      <section class="blk blk--time b-d1" aria-labelledby="k-d1">
        <div class="kicker" id="k-d1">回复速度</div>
        <!-- 一条共用刻度（0 → 九成）：一半落在它真实的位置上，
             两个分位数不再是两个互不相干的大数；极值行接在同一把尺子下面。 -->
        <template v-if="replyStats">
          <div class="big-row">
            <span class="big-lead">一半的消息，你在</span>
            <span class="big wrapped-number">{{ p50Text }}</span>
            <span class="big-unit">内就回了</span>
          </div>
          <div class="rs-scale">
            <i class="rs-track">
              <b class="rs-fill" :style="{ width: p50Pct + '%' }"></b>
              <b class="rs-pin" :style="{ left: p50Pct + '%' }"></b>
            </i>
            <div class="rs-marks">
              <span class="dt">一半 {{ p50Text }}</span>
              <span v-if="buddyAvgText2" class="dt one rs-mark-m">和 <b class="wrapped-privacy-name">{{ buddyName }}</b> 平均 {{ buddyAvgText2 }}</span>
              <span class="dt">九成 {{ p90Text }}</span>
            </div>
          </div>
          <!-- 两端极值各占一格：标签单独一行，块的下半不再是一片白 -->
          <div class="d1-ext">
            <div class="inset d1-ex">
              <span class="dt">最快回给</span>
              <span class="who-row">
                <span class="av av22">
                  <img
                    v-if="fastestAvatar"
                    class="wrapped-privacy-avatar"
                    :src="fastestAvatar"
                    alt="联系人头像"
                    draggable="false"
                  />
                  <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(fastest?.displayName) }}</span>
                </span>
                <span class="nm one wrapped-privacy-name">{{ fastest?.displayName || '——' }}</span>
                <span class="dd">{{ fastestText }}</span>
              </span>
            </div>
            <div class="inset d1-ex">
              <span class="dt">最慢让 TA 等了</span>
              <span class="who-row">
                <span class="av av22">
                  <img
                    v-if="slowestAvatar"
                    class="wrapped-privacy-avatar"
                    :src="slowestAvatar"
                    alt="联系人头像"
                    draggable="false"
                  />
                  <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(slowest?.displayName) }}</span>
                </span>
                <span class="nm one wrapped-privacy-name">{{ slowest?.displayName || '——' }}</span>
                <span class="dd">{{ slowestText }}</span>
              </span>
            </div>
          </div>
          <div class="foot-note serif-note one">等得再久的那一句，最后也回上了。</div>
        </template>
        <div v-else class="void-line">样本太少，算不出你的回复节奏。</div>
      </section>

      <!-- ═══════════ D2 谁先开口 ═══════════ -->
      <section class="blk b-d2" aria-labelledby="k-d2">
        <div class="head-line">
          <div class="kicker" id="k-d2">谁先开口</div>
          <div v-if="hasInitiative" class="kicker kicker--r">全年 {{ fmt(convCount) }} 次对话<template v-if="convPerDay"> · 每天 {{ convPerDay }} 次</template></div>
        </div>
        <template v-if="hasInitiative">
          <div class="big-row">
            <span class="big wrapped-number">{{ cuInit.display.value }}</span>
            <span class="big-unit">%</span>
            <span class="big-lead">的对话由你先开口</span>
          </div>
          <i class="split-bar" :style="{ '--p': initRatePct + '%' }"></i>
          <div class="duo-legend">
            <span>你先 <b class="wrapped-number">{{ fmt(initByMe) }}</b> 次</span>
            <span>TA 先 <b class="wrapped-number">{{ fmt(initByOthers) }}</b> 次</span>
          </div>
          <!-- 两列头像：主动往外找的人 / 主动找上门的人，正好把下半块填满 -->
          <div v-if="hasInitDuo" class="init-duo" :class="{ 'init-duo--solo': initDuoSolo }">
            <div v-if="initTopByMe.length" class="inset init-col">
              <div class="dt">你最常主动找</div>
              <div v-for="p in initTopByMe" :key="p.k" class="who-row init-row">
                <span class="av av22">
                  <img
                    v-if="p.avatar"
                    class="wrapped-privacy-avatar"
                    :src="p.avatar"
                    alt="联系人头像"
                    draggable="false"
                  />
                  <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(p.name) }}</span>
                </span>
                <span class="nm one wrapped-privacy-name">{{ p.name }}</span>
                <span class="dd wrapped-number">{{ fmt(p.count) }}</span>
              </div>
            </div>
            <div v-if="initTopToMe.length" class="inset init-col">
              <div class="dt">最常主动来找你</div>
              <div v-for="p in initTopToMe" :key="p.k" class="who-row init-row">
                <span class="av av22">
                  <img
                    v-if="p.avatar"
                    class="wrapped-privacy-avatar"
                    :src="p.avatar"
                    alt="联系人头像"
                    draggable="false"
                  />
                  <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(p.name) }}</span>
                </span>
                <span class="nm one wrapped-privacy-name">{{ p.name }}</span>
                <span class="dd wrapped-number">{{ fmt(p.count) }}</span>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="void-line">今年的对话不多。</div>
      </section>

      <!-- ═══════════ D4 年度聊天排行 ═══════════ -->
      <section class="blk blk--ppl b-rank" aria-labelledby="k-d4">
        <div class="head-line">
          <div class="kicker" id="k-d4">年度聊天排行</div>
          <!-- 就地读数：悬停某一行，图例换成那个人的往来拆分 -->
          <div v-if="rankList.length" class="rank-legend">
            <span v-if="rankReadout" class="lg lg-read"><b class="wrapped-privacy-name">{{ rankReadout.name }}</b> · 你发 {{ fmt(rankReadout.out) }} · TA 发 {{ fmt(rankReadout.inc) }}</span>
            <template v-else>
              <i class="lgc lgc--out"></i><span class="lg">你发</span>
              <i class="lgc lgc--in"></i><span class="lg">TA 发</span>
            </template>
          </div>
        </div>
        <div
          v-if="rankList.length"
          class="rank-list"
          @pointerover="onRankOver"
          @pointerleave="clearRankHover"
          @pointercancel="clearRankHover"
        >
          <div v-for="(r, ri) in rankList" :key="r.k" class="rank-item" :data-i="ri">
            <div class="who-row">
              <span class="rk">{{ r.rank }}</span>
              <span class="av av22">
                <img
                  v-if="r.avatar"
                  class="wrapped-privacy-avatar"
                  :src="r.avatar"
                  alt="联系人头像"
                  draggable="false"
                />
                <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(r.name) }}</span>
              </span>
              <span class="nm one wrapped-privacy-name">{{ r.name }}</span>
              <span class="dd rk-total wrapped-number">{{ fmt(r.total) }}</span>
            </div>
            <i v-if="r.hasSplit" class="duo-bar duo-bar--thin" :style="{ '--out': r.outPct + '%', '--w': r.widthPct + '%' }"></i>
          </div>
        </div>
        <div v-else class="void-line">今年的消息分得很散，排不出前三。</div>
      </section>

      <!-- ═══════════ D3 表情宇宙 ═══════════ -->
      <section class="blk blk--ppl b-d3" aria-labelledby="k-d3">
        <div class="kicker" id="k-d3">表情宇宙</div>
        <template v-if="sentStickerCount > 0">
          <div class="d3-row">
            <div class="d3-l">
              <div class="pic-frame">
                <!-- 部分微信表情包实际是 video/mp4，img → video 双降级不能去掉 -->
                <img
                  v-if="stickerUrl && !stickerFailed"
                  class="pic-img"
                  :src="stickerUrl"
                  alt="表情包"
                  draggable="false"
                  @error="stickerFailed = true"
                />
                <video
                  v-else-if="stickerUrl && stickerFailed"
                  class="pic-img"
                  :src="stickerUrl"
                  autoplay
                  loop
                  muted
                  playsinline
                ></video>
                <span v-else class="pic-void" aria-hidden="true"></span>
              </div>
              <div class="dt">{{ fmt(stickerCount) }} 次</div>
            </div>
            <!-- 三竖排改 2×2：图能放大，也腾出「翻旧表情」那一行 -->
            <div class="d3-m">
              <div class="inset mcell">
                <span class="dt">甩出</span>
                <span class="dd wrapped-number">{{ cuSticker.display.value }} 张</span>
              </div>
              <div class="inset mcell">
                <span class="dt">攒下</span>
                <span class="dd wrapped-number">{{ fmt(uniqueStickerTypes) }} 种</span>
              </div>
              <div class="inset mcell">
                <span class="dt">日均</span>
                <span class="dd wrapped-number">{{ stickerPerDay }} 张</span>
              </div>
              <div v-if="stickerActiveDays > 0" class="inset mcell">
                <span class="dt">出没</span>
                <span class="dd wrapped-number">{{ fmt(stickerActiveDays) }} 天</span>
              </div>
            </div>
          </div>
          <div v-if="stickerThumbs.length" class="thumbs">
            <span v-for="(t, i) in stickerThumbs" :key="i" class="thumb-pair">
              <span class="thumb"><img :src="t.url" alt="表情包" draggable="false" /></span>
              <span v-if="t.count > 0" class="dt">×{{ fmt(t.count) }}</span>
            </span>
          </div>
          <div class="d3-foot">
            <!-- 两条脚注并成一行，复刻那条靠右端 -->
            <div class="foot-split">
              <span class="foot-note one">新入库 {{ fmt(newStickerCount) }} 张 · 占全年发言 {{ stickerShare }}%</span>
              <span v-if="revivedText" class="foot-note one foot-r">{{ revivedText }}</span>
            </div>
            <div class="d3-tail">
              <span v-if="stickerPeakText" class="dt one">最密集 {{ stickerPeakText }}</span>
              <span v-if="emojiTop.length" class="emo-pair">
                <span v-for="(e, i) in emojiTop" :key="i" class="emo-row">
                  <img v-if="e.asset" class="emo emo--img" :src="e.asset" alt="表情" draggable="false" />
                  <span v-else class="emo">{{ e.glyph }}</span>
                  <span class="dt">×{{ fmt(e.count) }}</span>
                </span>
              </span>
            </div>
          </div>
        </template>
        <div v-else class="void-line">你很少用表情包，话都自己说完了。</div>
      </section>

      <!-- ═══════════ E1 还有这些人 ═══════════ -->
      <section v-if="peopleSlots.length >= 2" class="blk blk--slim b-people" aria-labelledby="k-e1">
        <div class="kicker ppl-kicker" id="k-e1">还有这些人</div>
        <div class="ppl-row" :class="{ 'is-sparse': peopleSlots.length < 5 }">
          <div v-for="p in peopleSlots" :key="p.key" class="ppl-chip">
            <span class="av av28 av--ring">
              <img
                v-if="p.avatar"
                class="wrapped-privacy-avatar"
                :src="p.avatar"
                :alt="p.isGroup ? '群头像' : '联系人头像'"
                draggable="false"
              />
              <span v-else class="av-ini wrapped-privacy-avatar">{{ firstChar(p.name) }}</span>
            </span>
            <span class="col">
              <span class="nm one wrapped-privacy-name">{{ p.name }}</span>
              <span class="dt one">{{ p.label }} {{ p.value }}</span>
            </span>
          </div>
        </div>
      </section>

      <!-- ═══════════ 页脚：年度地平线 ═══════════ -->
      <footer class="blk blk--slim b-foot">
        <div class="foot-end">
          <i class="dot dot--qty"></i>
          <span class="dt" v-if="firstSentText">第一条 · {{ firstSentText }}</span>
        </div>
        <i class="foot-line"></i>
        <div class="foot-mid">
          <span class="tag tag--qty">{{ persona }}</span>
          <span class="dt">没有哪种聊法是错的。</span>
        </div>
        <i class="foot-line"></i>
        <div class="foot-end foot-end--r">
          <span class="dt" v-if="lastSentText">最后一条 · {{ lastSentText }}</span>
          <i class="dot dot--time"></i>
        </div>
      </footer>
    </div>
  </div>

  <!-- 未就绪：card 7 要先把 card 0/1/2/3/4/5 各 build 一遍再聚合，
       生成时间显著长于其它页，用户一定会看到这一屏，所以它也得是这一版的一部分。 -->
  <div v-else class="wrap-final wrap-final--wait" :aria-busy="String(!isError)">
    <!-- 骨架用的就是最终版面本身的网格：让人看见这一页正在被一块块拼出来，
         而不是盯着一个转圈。块的位置、比例、圆角与成品完全一致，数据到位后原位替换。 -->
    <div class="sheet-final sheet-skeleton" aria-hidden="true">
      <div
        v-for="(b, i) in SKELETON_BLOCKS"
        :key="b"
        class="blk sk"
        :class="b"
        :style="{ '--sk-i': i }"
      ></div>
    </div>
    <div class="wait-box">
      <div class="wait-line" aria-live="polite">{{ waitText }}</div>
      <div class="wait-sub">{{ waitSub }}</div>
      <button v-if="canRetry" type="button" class="wait-retry" @click="onRetry">重新生成</button>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'
import { useReducedMotion } from '~/composables/useReducedMotion'
import { useCountUp } from '~/composables/useCountUp'
import { useApiBase } from '~/composables/useApiBase'

const props = defineProps({
  card: { type: Object, required: true },
  isActive: { type: Boolean, default: true },
  variant: { type: String, default: 'slide' }
})

const reduced = useReducedMotion()
const apiBase = useApiBase()

/* ───────────────────────────────────────────
   与 deck 的接口：状态 / 重试 / 顶栏
   ─────────────────────────────────────────── */
const cardStatus = computed(() => String(props.card?.status || '').trim().toLowerCase())
const isOk = computed(() => cardStatus.value === 'ok')
const isError = computed(() => cardStatus.value === 'error')

const retryFromDeck = inject('wrappedRetryCard', null)
const canRetry = computed(() => typeof retryFromDeck === 'function' && (isError.value || cardStatus.value === 'idle'))
const onRetry = async () => {
  if (typeof retryFromDeck !== 'function') return
  try { await retryFromDeck(Number(props.card?.id || 7)) } catch { /* deck 自己会把错误画出来 */ }
}

const waitText = computed(() => {
  if (isError.value) return '这一页没生成出来。'
  if (cardStatus.value === 'idle') return '等着汇总。'
  return '正在把前面几页汇总起来…'
})
const waitSub = computed(() => {
  if (isError.value) return String(props.card?.error || '未知错误')
  if (cardStatus.value === 'idle') return '翻到这一页才开始算。'
  return '这一页要把前面所有数据重算一遍，比别页慢一点。'
})

// 顶栏：本页是浅色满幅版面，只需要顶栏让位，不再把 deck 压暗（不 inject deckDark）。
// deckChromeHidden 是无引用计数的共享状态，离场/卸载必须原样交还，否则别的卡顶栏会永久消失。
const deckChromeHidden = inject('deckChromeHidden', ref(false))
let claimedDeck = false

const syncDeck = () => {
  const want = props.variant === 'slide' && props.isActive
  if (want === claimedDeck) return
  claimedDeck = want
  deckChromeHidden.value = want
}

const releaseDeck = () => {
  if (!claimedDeck) return
  claimedDeck = false
  deckChromeHidden.value = false
}

watch(() => [props.variant, props.isActive], syncDeck, { immediate: true })

/* ───────────────────────────────────────────
   媒体地址：qpic / qlogo 防盗链必须走后端代理，直连必 403
   ─────────────────────────────────────────── */
const resolveMediaUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^(data:|blob:)/i.test(raw)) return raw
  if (/^https?:\/\//i.test(raw)) {
    try {
      const host = new URL(raw).hostname.toLowerCase()
      if (host.endsWith('.qpic.cn') || host.endsWith('.qlogo.cn')) {
        return `${apiBase}/chat/media/proxy_image?url=${encodeURIComponent(raw)}`
      }
    } catch {}
    return raw
  }
  if (/^\/api\//i.test(raw)) return `${apiBase}${raw.slice(4)}`
  return raw.startsWith('/') ? raw : `/${raw}`
}

/* ───────────────────────────────────────────
   基础工具
   ─────────────────────────────────────────── */
const snap = computed(() => props.card?.data?.snapshot || {})

const num = (v, d = 0) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : d
}
const fmt = (v) => num(v).toLocaleString('zh-CN')
const pad2 = (n) => String(num(n)).padStart(2, '0')
const firstChar = (s) => {
  const t = String(s || '').trim()
  return t ? Array.from(t)[0] : '·'
}
const shortName = (s) => {
  const arr = Array.from(String(s || '').trim())
  if (!arr.length) return '—'
  return arr.length > 3 ? arr.slice(0, 3).join('') : arr.join('')
}

/* 时长措辞：秒 → 中文 */
const formatDurationZh = (seconds) => {
  const s = Math.max(0, Math.round(num(seconds)))
  if (!s) return '0 秒'
  if (s < 60) return `${s} 秒`
  if (s < 3600) return `${Math.round(s / 60)} 分钟`
  if (s < 86400) return `${(s / 3600).toFixed(s < 36000 ? 1 : 0)} 小时`
  return `${Math.round(s / 86400)} 天`
}

// `2025-08-19` → `8月19日`；识别不了就原样返回
const mdText = (v) => {
  const t = String(v || '').trim()
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(t)
  return m ? `${Number(m[2])}月${Number(m[3])}日` : t
}

/* ───────────────────────────────────────────
   顶层数据
   ─────────────────────────────────────────── */
const year = computed(() => num(snap.value.year, new Date().getFullYear()))
const totalMessages = computed(() => num(snap.value.totalMessages))
const messagesPerDay = computed(() => num(snap.value.messagesPerDay))
const activeDays = computed(() => num(snap.value.activeDays))
const addedFriends = computed(() => num(snap.value.addedFriends))
const sentChars = computed(() => num(snap.value.sentChars))
const receivedChars = computed(() => num(snap.value.receivedChars))
const sentMediaCount = computed(() => num(snap.value.sentMediaCount))
const sentToContacts = computed(() => num(snap.value.sentToContacts))
const sentStickerCount = computed(() => num(snap.value.sentStickerCount))
const mostActiveHour = computed(() => num(snap.value.mostActiveHour))
const mostActiveWeekdayName = computed(() => snap.value.mostActiveWeekdayName || '—')

const perDayText = computed(() => {
  const v = messagesPerDay.value
  return v >= 100 ? fmt(Math.round(v)) : v.toFixed(1)
})
const a1Line = computed(() => (totalMessages.value > 0 ? `平均每天 ${perDayText.value} 条。` : '今年的消息不多。'))

/* ───────── A2 / A1：365 天年历与最长连续 ───────── */
const dailyCounts = computed(() => {
  const arr = snap.value.annualHeatmap?.dailyCounts
  return Array.isArray(arr) ? arr : []
})
const hasYearGrid = computed(() => dailyCounts.value.length > 0)
// 色阶用分位数而不是绝对峰值：峰值日往往是平日的十几倍，
// 拿它当分母会把 364 天全压到最浅一档，整张年历看不出季节。
const yearThresholds = computed(() => {
  const vals = dailyCounts.value.map((v) => num(v)).filter((v) => v > 0).sort((a, b) => a - b)
  if (!vals.length) return [1, 2, 3, 4]
  const at = (p) => vals[Math.min(vals.length - 1, Math.floor(vals.length * p))]
  return [at(0.25), at(0.5), at(0.75), at(0.92)]
})

// 年历第一格落在星期几（周一 = 0）
const yearFirstDow = computed(() => {
  const d = new Date(year.value, 0, 1)
  return (d.getDay() + 6) % 7
})
const dayLabel = (doy) => {
  const d = new Date(year.value, 0, 1 + num(doy))
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

const peakDoy = computed(() => {
  const hs = snap.value.annualHeatmap?.highlights
  if (Array.isArray(hs)) {
    for (const h of hs) {
      if (h && String(h.key || '') === 'sent_messages_max') return num(h.doy, -1)
    }
  }
  let idx = -1
  let best = -1
  dailyCounts.value.forEach((v, i) => { if (num(v) > best) { best = num(v); idx = i } })
  return idx
})

const yearLevel = (v) => {
  const n = num(v)
  if (!n) return 0
  const t = yearThresholds.value
  if (n <= t[0]) return 1
  if (n <= t[1]) return 2
  if (n <= t[2]) return 3
  return 4
}
// d = 第几天（0 起）；开头的对齐空格没有 d，属性不渲染，也就悬停不到
const yearCells = computed(() => {
  const out = []
  const pad = yearFirstDow.value
  for (let i = 0; i < pad; i += 1) out.push({ k: `p${i}`, lv: -1, peak: false, d: null })
  dailyCounts.value.forEach((v, i) => out.push({ k: `d${i}`, lv: yearLevel(v), peak: i === peakDoy.value, d: i }))
  return out
})

const longestStreak = computed(() => {
  const arr = dailyCounts.value
  let best = { days: 0, s: 0, e: 0 }
  let cur = 0
  for (let i = 0; i < arr.length; i += 1) {
    if (num(arr[i]) > 0) {
      cur += 1
      if (cur > best.days) best = { days: cur, s: i - cur + 1, e: i }
    } else cur = 0
  }
  return best
})
const streakDays = computed(() => longestStreak.value.days)
const streakRange = computed(() => (streakDays.value > 1 ? `${dayLabel(longestStreak.value.s)}–${dayLabel(longestStreak.value.e)}` : ''))

/* ───────── A3 最疯的一天 ───────── */
const peakDay = computed(() => snap.value.peakDay || null)
const hasPeakDay = computed(() => !!(peakDay.value && num(peakDay.value.count) > 0))
const peakCount = computed(() => num(peakDay.value?.count))
const peakMultiple = computed(() => num(peakDay.value?.multiple))
const peakDateText = computed(() => mdText(peakDay.value?.date))
const peakWeekday = computed(() => peakDay.value?.weekdayName || '')
const peakContact = computed(() => peakDay.value?.topContact || null)
const peakContactAvatar = computed(() => resolveMediaUrl(peakContact.value?.avatarUrl))
// 那天占全年多少：前端自己算，后端没这个字段
const peakShare = computed(() => {
  if (totalMessages.value <= 0 || peakCount.value <= 0) return ''
  const p = (peakCount.value / totalMessages.value) * 100
  return p >= 10 ? String(Math.round(p)) : p.toFixed(1)
})
// `08:14` → 分钟数；识别不了返回 -1
const hhmmToMin = (v) => {
  const m = /^(\d{1,2}):(\d{2})/.exec(String(v || '').trim())
  if (!m) return -1
  const h = Number(m[1])
  const mi = Number(m[2])
  return h >= 0 && h <= 24 && mi >= 0 && mi < 60 ? h * 60 + mi : -1
}
const peakSpan = computed(() => {
  const a = hhmmToMin(peakDay.value?.firstTime)
  const b = hhmmToMin(peakDay.value?.lastTime)
  if (a < 0 || b < 0 || b < a) return null
  return {
    left: +((a / 1440) * 100).toFixed(2),
    width: +(Math.max(1.5, ((b - a) / 1440) * 100)).toFixed(2),
    mins: b - a
  }
})
const peakSpanText = computed(() => {
  const s = peakSpan.value
  if (!s) return ''
  const h = Math.floor(s.mins / 60)
  const m = s.mins % 60
  const dur = h > 0 ? `${h} 小时${m > 0 ? ` ${m} 分` : ''}` : `${m} 分`
  return `第一句到最后一句 · ${dur}`
})

/* ───────── B1 年度搭子 ───────── */
const bestBuddy = computed(() => snap.value.bestBuddy || null)
const hasBuddy = computed(() => !!(bestBuddy.value && bestBuddy.value.displayName))
const buddyName = computed(() => bestBuddy.value?.displayName || '——')
const buddyInitial = computed(() => firstChar(bestBuddy.value?.displayName))
const buddyAvatar = computed(() => resolveMediaUrl(bestBuddy.value?.avatarUrl))
const buddyMessages = computed(() => num(bestBuddy.value?.totalMessages))
const buddyOut = computed(() => num(bestBuddy.value?.outgoingMessages))
const buddyIn = computed(() => num(bestBuddy.value?.incomingMessages))
const buddyOutPct = computed(() => {
  const t = buddyOut.value + buddyIn.value
  return t > 0 ? +((buddyOut.value / t) * 100).toFixed(1) : 50
})
const buddyStreak = computed(() => num(bestBuddy.value?.longestStreakDays))
const buddyPeakLabel = computed(() =>
  bestBuddy.value?.peakHourLabel || (bestBuddy.value ? `${pad2(bestBuddy.value.peakHour)}:00` : '—')
)
const buddyReplyCount = computed(() => num(bestBuddy.value?.replyCount))
const buddyAvgText = computed(() => formatDurationZh(bestBuddy.value?.avgReplySeconds))
const buddyFastText = computed(() => formatDurationZh(bestBuddy.value?.fastestReplySeconds))
const buddySlowText = computed(() => formatDurationZh(bestBuddy.value?.slowestReplySeconds))

/* ───────── B2 十二个月的主演 ───────── */
const monthly = computed(() => {
  const arr = snap.value.monthlyBestBuddies
  if (Array.isArray(arr) && arr.length) return arr
  return Array.from({ length: 12 }, (_, i) => ({ month: i + 1, displayName: '', avatarUrl: '', messages: 0 }))
})
const monthAvatar = (m) => resolveMediaUrl(m?.avatarUrl)
// 月度消息量：归一化成头像下面那条极细的量条，缺字段就是 0 宽（不是 NaN）
const monthMax = computed(() => {
  let mx = 0
  for (const m of monthly.value) if (num(m?.messages) > mx) mx = num(m.messages)
  return mx
})
const monthPct = (m) => {
  const v = num(m?.messages)
  if (v <= 0 || monthMax.value <= 0) return 0
  return +(Math.max(7, (v / monthMax.value) * 100)).toFixed(1)
}
const hottestMonth = computed(() => {
  let best = null
  for (const m of monthly.value) if (num(m?.messages) > num(best?.messages)) best = m
  return best && num(best.messages) > 0 ? best : null
})
const isHotMonth = (m) => !!hottestMonth.value && num(m?.month) === num(hottestMonth.value.month)
const monthlySummary = computed(() => snap.value.monthlySummary || null)
const monthsWithWinner = computed(() => {
  const v = num(monthlySummary.value?.monthsWithWinner)
  if (v > 0) return v
  return monthly.value.filter((m) => String(m.displayName || '').trim()).length
})
// 后端没给 topChampion 时按出现次数自行推一个，保证桂冠条不空着
const championFallback = computed(() => {
  const tally = new Map()
  for (const m of monthly.value) {
    const n = String(m.displayName || '').trim()
    if (!n) continue
    tally.set(n, (tally.get(n) || 0) + 1)
  }
  let name = ''
  let won = 0
  for (const [k, v] of tally) if (v > won) { won = v; name = k }
  if (won < 2) return null
  const hit = monthly.value.find((m) => String(m.displayName || '').trim() === name)
  return { displayName: name, monthsWon: won, avatarUrl: hit?.avatarUrl || '' }
})
const champion = computed(() => {
  const c = monthlySummary.value?.topChampion
  if (c && String(c.displayName || '').trim()) return c
  return championFallback.value
})
const championAvatar = computed(() => {
  const direct = resolveMediaUrl(champion.value?.avatarUrl)
  if (direct) return direct
  const hit = monthly.value.find((m) => String(m.displayName || '') === String(champion.value?.displayName || ''))
  return resolveMediaUrl(hit?.avatarUrl)
})
const isChampMonth = (m) => {
  const c = String(champion.value?.displayName || '').trim()
  return !!c && String(m?.displayName || '').trim() === c
}

/* ───────── B3 深夜 ─────────
   latestMoment.direction 决定这句话署谁的名 —— sent 是你自己说的，received 才是对方说的。
   署错人比不显示更糟，所以这里不做任何猜测。 */
const nightRaw = computed(() => snap.value.nightCompanion || null)
const nightPartner = computed(() => nightRaw.value?.partner || null)
const nightPartnerAvatar = computed(() => resolveMediaUrl(nightPartner.value?.avatarUrl))
const nightTotal = computed(() => num(nightRaw.value?.nightMessagesTotal))
const myNightMessages = computed(() => num(nightRaw.value?.myNightMessages))
const night = computed(() => {
  const m = nightRaw.value?.latestMoment
  const content = String(m?.content || '').trim()
  if (!content) return null
  return {
    date: mdText(m.date),
    time: String(m.time || '').trim(),
    content,
    fromMe: String(m.direction || '') === 'sent'
  }
})
const hasNight = computed(() => !!(night.value || nightPartner.value || nightTotal.value > 0))

/* 夜空星点：算法与 Card01「赛博作息」的 nightStars 完全一致（同一套视觉语言，
   同一份数据永远得到同一片星空，翻来翻去不会跳）。星数随深夜消息量增减。 */
const nightStars = computed(() => {
  const total = nightTotal.value
  let count = 10
  if (total >= 1000) count = 26
  else if (total >= 300) count = 20
  else if (total >= 100) count = 15
  else if (total >= 20) count = 12

  let seed = ((total + 7) * 2654435761) % 2147483647
  if (seed <= 0) seed = 12345
  const rand = () => {
    seed = (seed * 48271) % 2147483647
    return seed / 2147483647
  }
  const stars = []
  for (let i = 0; i < count; i += 1) {
    const size = 1.2 + rand() * 1.7
    stars.push({
      left: `${(rand() * 94 + 3).toFixed(2)}%`,
      top: `${(rand() * 78 + 3).toFixed(2)}%`,
      width: `${size.toFixed(1)}px`,
      height: `${size.toFixed(1)}px`,
      animationDelay: `${(rand() * 2.4).toFixed(2)}s`,
      animationDuration: `${(2 + rand() * 2).toFixed(2)}s`
    })
  }
  return stars
})
const nightSpeaker = computed(() => (night.value?.fromMe ? '你' : (nightPartner.value?.displayName || '对方')))
const nightSpeakerIsName = computed(() => !!night.value && !night.value.fromMe && !!nightPartner.value?.displayName)
const nightShare = computed(() => {
  const p = num(nightPartner.value?.sharePct)
  return p > 0 ? p : 0
})
// 「对方发出」只做减法，减不出正数就当 0，绝不出现负数
const othersNightMessages = computed(() => Math.max(0, nightTotal.value - myNightMessages.value))

/* ───────── C1 作息切片 ───────── */
const weekdayLabels = computed(() => snap.value.weekdayLabels || ['周一', '周二', '周三', '周四', '周五', '周六', '周日'])
const matrix = computed(() => {
  const m = snap.value.weekdayHourMatrix
  if (Array.isArray(m) && m.length === 7) return m
  return Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0))
})
const hourTotals = computed(() => {
  const out = Array.from({ length: 24 }, () => 0)
  for (const row of matrix.value) for (let h = 0; h < 24; h += 1) out[h] += num(row?.[h])
  return out
})
const weekdayTotals = computed(() => matrix.value.map((row) => (Array.isArray(row) ? row.reduce((a, b) => a + num(b), 0) : 0)))
const matrixMax = computed(() => {
  let mx = 1
  for (const row of matrix.value) for (const v of (row || [])) if (num(v) > mx) mx = num(v)
  return mx
})
const matrixTotal = computed(() => weekdayTotals.value.reduce((a, b) => a + b, 0))
const matrixLevel = (v) => {
  const n = num(v)
  if (!n) return 0
  const t = Math.pow(n / matrixMax.value, 0.72)
  if (t < 0.22) return 1
  if (t < 0.45) return 2
  if (t < 0.72) return 3
  return 4
}
const matrixCells = computed(() => {
  const out = []
  for (let w = 0; w < 7; w += 1) for (let h = 0; h < 24; h += 1) out.push(matrixLevel(matrix.value[w]?.[h]))
  return out
})
const HOUR_AXIS = ['00', '03', '06', '09', '12', '15', '18', '21']
const quietHour = computed(() => {
  let idx = 0
  let best = Infinity
  hourTotals.value.forEach((v, i) => { if (v < best) { best = v; idx = i } })
  return idx
})
const quietCount = computed(() => num(hourTotals.value[quietHour.value]))
const nightPct = computed(() => {
  if (!matrixTotal.value) return 0
  let late = 0
  for (const row of matrix.value) for (let h = 0; h <= 5; h += 1) late += num(row?.[h])
  return +((late / matrixTotal.value) * 100).toFixed(1)
})
const weekendRatio = computed(() => {
  const t = weekdayTotals.value
  if (t.length < 7) return '—'
  const wd = (t[0] + t[1] + t[2] + t[3] + t[4]) / 5
  const we = (t[5] + t[6]) / 2
  if (!we) return '—'
  return (wd / we).toFixed(2)
})

/* ───────── 年度聊天人格：四条二元轴 → 16 选 1，全部中性或褒义 ───────── */
const PERSONAS = [
  '定点长谈', '随手就回', '白日回音', '轮流应答',
  '深夜专线', '夜里搭话', '不打烊的人', '值夜的手',
  '慢火长信', '想好再说', '错峰对谈', '安静在场',
  '写给一个人', '夜半回信', '晚到的长句', '各自安好'
]
const replyStats = computed(() => snap.value.replyStats || null)
const p50 = computed(() => num(replyStats.value?.p50Seconds))
const p90 = computed(() => num(replyStats.value?.p90Seconds))
const persona = computed(() => {
  const fast = replyStats.value && p50.value > 0 && p50.value <= 180 ? 1 : 0
  const isNight = nightPct.value >= 12 ? 1 : 0
  const focused = totalMessages.value > 0 && buddyMessages.value / totalMessages.value >= 0.25 ? 1 : 0
  const wordy = totalMessages.value > 0 && sentChars.value / totalMessages.value >= 12 ? 1 : 0
  return PERSONAS[fast * 8 + isNight * 4 + focused * 2 + wordy]
})

/* ───────── C2 你说的话 ─────────
   刻意排除《小王子》：中译本 2 万 / 3 万 / 5.4 万三种说法，会被懂行的用户抓错。
   禁止换算成绕地球圈数 / 楼层高度 / 电影部数 —— 用户无法验证的类比读起来就是营销话术。
   书名档位以后端 sentBook 为准，下面这把梯子只在缺字段时兜底。 */
const TEXT_SCALE_LADDER = [
  { name: '《道德经》', chars: 5162 },
  { name: '《论语》', chars: 11750 },
  { name: '《了不起的盖茨比》', chars: 80000 },
  { name: '《活着》', chars: 92288 },
  { name: '《围城》', chars: 217000 },
  { name: '《红楼梦》', chars: 730000 }
]
const describeCharScale = (chars) => {
  const n = num(chars)
  if (n <= 0) return ''
  if (n < TEXT_SCALE_LADDER[0].chars * 0.8) {
    const essays = Math.round(n / 800)
    return essays >= 2 ? `约 ${essays} 篇高考作文的长度` : ''
  }
  for (let i = TEXT_SCALE_LADDER.length - 1; i >= 0; i -= 1) {
    const it = TEXT_SCALE_LADDER[i]
    const r = n / it.chars
    if (r >= 0.8 && r <= 3.5) return r < 1.2 ? `差不多一本${it.name}` : `约 ${r.toFixed(1)} 本${it.name}`
  }
  return ''
}
const charsLine = computed(() => {
  if (sentChars.value <= 0) return '今年你几乎没打过字。'
  const t = String(snap.value.sentBook?.text || '').trim()
  if (t) return t
  return describeCharScale(sentChars.value) || `一年下来 ${fmt(sentChars.value)} 个字。`
})
const keyboard = computed(() => snap.value.keyboard || null)
const keyHits = computed(() => num(keyboard.value?.totalKeyHits))
const topKeys = computed(() => {
  const arr = keyboard.value?.topKeys
  if (!Array.isArray(arr)) return []
  return arr.filter((k) => String(k?.key || '').trim()).slice(0, 3)
})
const voice = computed(() => snap.value.voice || null)
const voiceSentCount = computed(() => num(voice.value?.sentCount))
const voiceSentDur = computed(() => formatDurationZh(voice.value?.sentSeconds))
// 收到的语音：后端后补的字段，缺失时整格不渲染，不要印 0 条
const voiceRecvCount = computed(() => num(voice.value?.receivedCount))
const voiceRecvDur = computed(() => formatDurationZh(voice.value?.receivedSeconds))
// 年度最长的一条语音：方向决定措辞（发给 / 来自），名字在模板里单独挂隐私类
const voiceLongest = computed(() => {
  const v = voice.value?.longest
  const s = num(v?.seconds)
  if (!v || s <= 0) return null
  return {
    seconds: s,
    name: String(v.displayName || '').trim(),
    date: mdText(v.date),
    lead: String(v.direction || '') === 'sent' ? '发给' : '来自'
  }
})
const voiceLongestDur = computed(() => formatDurationZh(voiceLongest.value?.seconds))
// 收到的字换算成 A4：优先用后端拆好的份数 / 高度，缺了才退回整句
const receivedA4 = computed(() => snap.value.receivedA4 || null)
const receivedA4Text = computed(() => {
  const sheets = num(receivedA4.value?.a4?.sheets)
  const h = String(receivedA4.value?.a4?.heightText || '').trim()
  if (sheets > 0) return h ? `收到的字够印 ${fmt(sheets)} 张 A4 · 摞起来 ${h}` : `收到的字够印 ${fmt(sheets)} 张 A4`
  const t = String(receivedA4.value?.text || '').trim()
  return t ? `收到的字 · ${t}` : ''
})
const calls = computed(() => snap.value.calls || null)
const callsTotalCount = computed(() => num(calls.value?.totalCount))
const callsConnected = computed(() => num(calls.value?.connectedCount))
const callsMissed = computed(() => num(calls.value?.missedOrCanceledCount))
const hasCalls = computed(() => callsTotalCount.value > 0 || num(calls.value?.totalSeconds) > 0)
// 通话总时长走中文时长，不要 H:MM:SS —— 「15:00:00」会被读成一个钟点，而不是「打了 15 小时」
const callsHMS = computed(() => formatDurationZh(num(calls.value?.totalSeconds)))
const callsDurText = computed(() => {
  const parts = [callsHMS.value]
  if (callsTotalCount.value > 0) parts.push(`${fmt(callsTotalCount.value)} 通`)
  return parts.join(' · ')
})
// 「接通 / 未接」两个数各自可能缺席：只印真的有的那一侧，标签跟着变
const callsAnswerLabel = computed(() => {
  if (callsConnected.value > 0 && callsMissed.value > 0) return '接通 / 未接'
  if (callsConnected.value > 0) return '接通'
  return callsMissed.value > 0 ? '未接' : ''
})
const callsAnswerText = computed(() => {
  const c = callsConnected.value
  const m = callsMissed.value
  if (c > 0 && m > 0) return `${fmt(c)} · ${fmt(m)}`
  if (c > 0) return `${fmt(c)} 通`
  return m > 0 ? `${fmt(m)} 通` : ''
})
const c2Foot = computed(() => {
  const parts = []
  const video = num(calls.value?.videoCount)
  const audio = num(calls.value?.voiceCount)
  if (video > 0 || audio > 0) parts.push(`视频 ${fmt(video)} / 语音 ${fmt(audio)}`)
  return parts.join(' · ')
})

/* ───────── C3 年度口头禅 ─────────
   口径统一走 card_06 的 topKeyword（deck 里被大书特书的那一个），topPhrase 仅作 fallback。 */
const topKeyword = computed(() => snap.value.topKeyword || null)
const topPhrase = computed(() => snap.value.topPhrase || null)
const heroWord = computed(() => String(topKeyword.value?.word || topPhrase.value?.phrase || '').trim())
const heroCount = computed(() => num(topKeyword.value?.count ?? topPhrase.value?.count))
const kwRest = computed(() => {
  const arr = Array.isArray(snap.value.keywords) ? snap.value.keywords : []
  return arr
    .filter((k) => k && String(k.word || '').trim() && String(k.word) !== heroWord.value)
    .slice(0, 7)
    .map((k) => ({ word: String(k.word), count: num(k.count) }))
})
// 同一色相的 3 档：按次数相对最高的那一条分层，chips 不再是一片同色
const kwCeil = computed(() => {
  let mx = 0
  for (const k of kwRest.value) if (k.count > mx) mx = k.count
  return mx
})
const kwTier = (c) => {
  if (kwCeil.value <= 0) return 0
  const r = num(c) / kwCeil.value
  if (r >= 0.6) return 2
  return r >= 0.3 ? 1 : 0
}
const kwChips = computed(() => kwRest.value.map((k) => ({ ...k, tier: kwTier(k.count) })))
// 总量条：口头禅各占多宽，同一套 3 档配色
const kwStack = computed(() => {
  const rows = []
  if (heroWord.value && heroCount.value > 0) rows.push({ word: heroWord.value, count: heroCount.value, hero: true })
  for (const k of kwRest.value) if (k.count > 0) rows.push({ word: k.word, count: k.count, hero: false })
  const total = rows.reduce((a, b) => a + b.count, 0)
  if (total <= 0 || rows.length < 2) return []
  return rows.map((r, i) => ({
    k: `${i}-${r.word}`,
    hero: r.hero,
    word: r.word,
    count: r.count,
    tier: kwTier(r.count),
    pct: +((r.count / total) * 100).toFixed(2)
  }))
})
const kwFoot = computed(() => {
  const meta = snap.value.keywordMeta
  const matched = num(meta?.matchedCandidates)
  const uniq = num(meta?.uniquePhrases)
  if (!matched || !uniq) return ''
  return `${fmt(matched)} 句短表达里，${fmt(uniq)} 句成了你的口头禅`
})

/* ───────── D1 回复速度 ───────── */
const p50Text = computed(() => (replyStats.value ? formatDurationZh(p50.value) : '—'))
const p90Text = computed(() => (replyStats.value ? formatDurationZh(p90.value) : '—'))
const p50Pct = computed(() => (p90.value > 0 ? Math.max(4, Math.min(100, (p50.value / p90.value) * 100)).toFixed(1) : 100))
const fastest = computed(() => snap.value.fastest || null)
const slowest = computed(() => snap.value.slowest || null)
const fastestAvatar = computed(() => resolveMediaUrl(fastest.value?.avatarUrl))
const slowestAvatar = computed(() => resolveMediaUrl(slowest.value?.avatarUrl))
const fastestText = computed(() => formatDurationZh(fastest.value?.seconds))
const slowestText = computed(() => formatDurationZh(slowest.value?.seconds))
// 尺子上的第三个参照点：和年度搭子之间的平均间隔（缺字段就不画这一格）
const buddyAvgText2 = computed(() => (
  hasBuddy.value && num(bestBuddy.value?.avgReplySeconds) > 0 ? buddyAvgText.value : ''
))

/* ───────── D2 谁先开口 ───────── */
const initiative = computed(() => snap.value.initiative || null)
const convCount = computed(() => num(initiative.value?.conversationCount))
const hasInitiative = computed(() => convCount.value > 0)
const initByMe = computed(() => num(initiative.value?.initiatedByMe))
const initByOthers = computed(() => num(initiative.value?.initiatedByOthers))
const initRatePct = computed(() => num(initiative.value?.initiationRatePct))
// 分母与 messagesPerDay 口径一致：都按活跃天算，缺活跃天才退回 365
const convPerDay = computed(() => {
  if (convCount.value <= 0) return ''
  const days = activeDays.value > 0 ? activeDays.value : 365
  const v = convCount.value / days
  return v >= 10 ? String(Math.round(v)) : v.toFixed(1)
})
// 主动的两个方向各取前两名：空名字整条丢掉，不留占位
const initTop = (arr) => (Array.isArray(arr) ? arr : [])
  .filter((p) => String(p?.displayName || '').trim())
  .slice(0, 2)
  .map((p, i) => ({
    k: `i${i}-${p.displayName}`,
    name: String(p.displayName).trim(),
    avatar: resolveMediaUrl(p.avatarUrl),
    count: num(p.count)
  }))
const initTopByMe = computed(() => initTop(initiative.value?.topInitiatedByMe))
const initTopToMe = computed(() => initTop(initiative.value?.topInitiatedToMe))
const hasInitDuo = computed(() => initTopByMe.value.length > 0 || initTopToMe.value.length > 0)
// 只有一侧有数据时收成一列，免得又出现「左边有内容右边没有」
const initDuoSolo = computed(() => initTopByMe.value.length === 0 || initTopToMe.value.length === 0)

/* ───────── D3 表情宇宙 ───────── */
const topSticker = computed(() => snap.value.topSticker || null)
const stickerUrl = computed(() => resolveMediaUrl(topSticker.value?.imageUrl))
const stickerCount = computed(() => num(topSticker.value?.count))
const stickerFailed = ref(false)
const stickerThumbs = computed(() => {
  const arr = snap.value.topStickerThumbs
  if (!Array.isArray(arr)) return []
  // 左图右字：次数本来就在数据里，只画图等于白扔掉一半信息
  return arr
    .map((t) => ({ url: resolveMediaUrl(t?.emojiUrl || t?.imageUrl), count: num(t?.count) }))
    .filter((t) => t.url)
    .slice(0, 5)
})
const uniqueStickerTypes = computed(() => num(snap.value.uniqueStickerTypeCount))
const stickerPerDay = computed(() => {
  const v = num(snap.value.stickerPerActiveDay)
  return v >= 10 ? Math.round(v) : v.toFixed(1)
})
// 后端给的是 0–1 的比例，不是百分数：直接印会变成「0.10037801389456477%」
const stickerShare = computed(() => {
  const r = num(snap.value.stickerShareOfSentMessages)
  const pct = r <= 1 ? r * 100 : r
  return pct >= 10 ? String(Math.round(pct)) : pct.toFixed(1)
})
const newStickerCount = computed(() => num(snap.value.newStickerCountThisYear))
const stickerActiveDays = computed(() => num(snap.value.stickerActiveDays))
// 沉睡后被翻出来的老表情：只有真的有才出这一行
const revivedCount = computed(() => num(snap.value.revivedStickerCount))
const revivedGapDays = computed(() => num(snap.value.revivedMaxGapDays))
const revivedText = computed(() => {
  if (revivedCount.value <= 0) return ''
  const head = `有 ${fmt(revivedCount.value)} 张沉睡后又被翻出来`
  return revivedGapDays.value > 0 ? `${head} · 最久隔了 ${fmt(revivedGapDays.value)} 天` : head
})
// 表情最密集的时刻：星期与钟点各自缺失都要能单独降级
const stickerPeakWeekday = computed(() => String(snap.value.stickerPeakWeekdayName || '').trim())
const stickerPeakHour = computed(() => {
  const n = Number(snap.value.stickerPeakHour)
  return Number.isFinite(n) && n >= 0 && n <= 23 ? n : -1
})
const stickerPeakText = computed(() => {
  const parts = []
  if (stickerPeakWeekday.value) parts.push(stickerPeakWeekday.value)
  if (stickerPeakHour.value >= 0) parts.push(`${pad2(stickerPeakHour.value)}:00`)
  return parts.join(' ')
})

/* 年度表情：微信表情走 assetPath 图片，Unicode 表情走字形。
   图与次数必须同源 —— 混着取会印出「😋 × 662」这种张冠李戴的读数。 */
const topEmoji = computed(() => snap.value.topEmoji || null)
const emojiAsset = computed(() => {
  const p = String(topEmoji.value?.assetPath || '').trim()
  return p ? resolveMediaUrl(p) : ''
})
const emojiGlyph = computed(() => {
  if (emojiAsset.value) return ''
  const own = String(topEmoji.value?.emoji || '').trim()
  return own || String(snap.value.topUnicodeEmoji || '').trim()
})
const emojiCount = computed(() => {
  if (emojiAsset.value || topEmoji.value?.emoji) return num(topEmoji.value?.count)
  return num(snap.value.topUnicodeEmojiCount)
})
const hasEmoji = computed(() => (!!emojiAsset.value || !!emojiGlyph.value) && emojiCount.value > 0)
// 系统 Unicode 表情是另一份统计，与微信表情不是同一个榜；两个都在时并排显示
const uniEmoji = computed(() => String(snap.value.topUnicodeEmoji || '').trim())
const uniEmojiCount = computed(() => num(snap.value.topUnicodeEmojiCount))
const hasUniEmoji = computed(() => !!uniEmoji.value && uniEmojiCount.value > 0 && uniEmoji.value !== emojiGlyph.value)

/* 右下角并排的前 5 个表情：后端 topEmojis 已按次数排好并跨类目去重。
   缺字段时退回旧的「微信 Top1 + Unicode Top1」两枚，保证老缓存也不空。 */
const emojiTop = computed(() => {
  const arr = snap.value.topEmojis
  if (Array.isArray(arr) && arr.length) {
    return arr
      .map((e) => {
        const asset = String(e?.assetPath || '').trim()
        const glyph = String(e?.emoji || '').trim()
        return {
          asset: asset ? resolveMediaUrl(asset) : '',
          glyph: asset ? '' : glyph,
          count: num(e?.count)
        }
      })
      .filter((e) => (e.asset || e.glyph) && e.count > 0)
      .slice(0, 5)
  }
  const out = []
  if (hasEmoji.value) out.push({ asset: emojiAsset.value, glyph: emojiGlyph.value, count: emojiCount.value })
  if (hasUniEmoji.value) out.push({ asset: '', glyph: uniEmoji.value, count: uniEmojiCount.value })
  return out
})

/* ───────── D4 年度聊天排行：前 5 名 + 双色往来条 ───────── */
const rankList = computed(() => {
  const arr = snap.value.topTotals
  if (!Array.isArray(arr)) return []
  const rows = []
  for (const it of arr) {
    const name = String(it?.displayName || '').trim()
    if (!name) continue
    const out = num(it.outgoingMessages)
    const inc = num(it.incomingMessages)
    const sum = out + inc
    const total = num(it.totalMessages) || sum
    if (total <= 0) continue
    rows.push({
      k: `r${rows.length}`,
      rank: rows.length + 1,
      name,
      avatar: resolveMediaUrl(it.avatarUrl),
      total,
      out,
      inc,
      hasSplit: sum > 0,
      outPct: sum > 0 ? +((out / sum) * 100).toFixed(1) : 50
    })
    if (rows.length >= 5) break
  }
  // 条长按第一名归一：第二三名短一截才读得出量级差
  const top = rows.length ? rows[0].total : 0
  return rows.map((r) => ({ ...r, widthPct: top > 0 ? Math.max(12, (r.total / top) * 100).toFixed(1) : 100 }))
})

/* ───────── E1 还有这些人：空槽跳过，实有 < 2 人整条隐藏 ───────── */
const peopleSlots = computed(() => {
  const out = []
  const push = (key, label, src, value, isGroup = false) => {
    const name = String(src?.displayName || '').trim()
    if (!name) return
    out.push({ key, label, name, value, isGroup, avatar: resolveMediaUrl(src?.avatarUrl) })
  }
  const topContact = snap.value.topContact
  push('contact', '最常联系', topContact, `${fmt(topContact?.messages)} 条`)
  const topGroup = snap.value.topGroup
  push('group', '最活跃群聊', topGroup, `${fmt(topGroup?.messages)} 条`, true)
  const cp = calls.value?.topPartner
  push('call', '最常连线', cp, `${fmt(cp?.count)} 通 · ${formatDurationZh(cp?.seconds)}`)
  const vp = voice.value?.topSentPartner
  push('voice', '最常说给 TA 听', vp, `${fmt(vp?.count)} 条`)
  const vr = voice.value?.topReceivedPartner
  push('voice-in', '最常听 TA 说', vr, `${fmt(vr?.count)} 条`)
  const bp = snap.value.topBattlePartner
  push('battle', '斗图对手', bp, `${fmt(bp?.stickerCount)} 张`)
  const mf = initiative.value?.mutualFriend
  push('mutual', '势均力敌', mf, `${fmt(mf?.sentCount)} : ${fmt(mf?.receivedCount)}`)
  return out
})

/* ───────── 页脚：年度地平线 ───────── */
const firstSentText = computed(() => {
  const v = snap.value.yearFirstSent
  const d = mdText(v?.date)
  if (!d) return ''
  return `${d} ${String(v?.time || '').trim()}`.trim()
})
const lastSentText = computed(() => {
  const v = snap.value.yearLastSent
  const d = mdText(v?.date)
  if (!d) return ''
  return `${d} ${String(v?.time || '').trim()}`.trim()
})

/* ───────────────────────────────────────────
   悬停就地读数
   ─────────────────────────────────────────────
   范式：每块本来就有的那一行读数，悬停时换成当前格子的明细，移开换回默认。
   不做浮层 —— 没有 z-index、不遮别的内容、不需要跟随光标。
   事件机制：容器上一个 pointerover 做委托（367 + 168 + 12 + 5 + 8 = 560 个图元，
   逐个绑 handler 会白白多出几百个监听器）；pointer 事件而不是 mouseenter，
   触摸设备上点一下同样出读数。
   刻意不做交互的三处：D1 回复速度刻度、D2 谁先开口进度条、A3 24 小时跨度尺 ——
   它们的数值本来就印在紧挨着的那一行里，悬停不产生任何新信息。
   ─────────────────────────────────────────── */
const yearHover = ref(-1)
const matrixHover = ref(-1)
const monthHover = ref(-1)
const rankHover = ref(-1)
const kwHover = ref(-1)

// 委托取索引：命中不了图元就返回 -1（调用方会保留上一个值，
// 免得指针扫过格子之间那 2px 缝隙时读数闪一下默认文案）
const hoverIndexFrom = (ev, selector, key) => {
  const t = ev?.target
  const el = t && typeof t.closest === 'function' ? t.closest(selector) : null
  if (!el) return -1
  const raw = el.dataset?.[key]
  if (raw == null || raw === '') return -1
  const n = Number(raw)
  return Number.isInteger(n) && n >= 0 ? n : -1
}

const onYearOver = (ev) => {
  const i = hoverIndexFrom(ev, '.yr-cell', 'd')
  if (i >= 0) yearHover.value = i
}
const clearYearHover = () => { yearHover.value = -1 }

const onMatrixOver = (ev) => {
  const i = hoverIndexFrom(ev, '.hh-cell', 'i')
  if (i >= 0) matrixHover.value = i
}
const clearMatrixHover = () => { matrixHover.value = -1 }

const onMonthOver = (ev) => {
  const i = hoverIndexFrom(ev, '.mo', 'i')
  if (i >= 0) monthHover.value = i
}
const clearMonthHover = () => { monthHover.value = -1 }

const onRankOver = (ev) => {
  const i = hoverIndexFrom(ev, '.rank-item', 'i')
  if (i >= 0) rankHover.value = i
}
const clearRankHover = () => { rankHover.value = -1 }

const onKwOver = (ev) => {
  const i = hoverIndexFrom(ev, '.kw-seg', 'i')
  if (i >= 0) kwHover.value = i
}
const clearKwHover = () => { kwHover.value = -1 }

const resetHovers = () => {
  yearHover.value = -1
  matrixHover.value = -1
  monthHover.value = -1
  rankHover.value = -1
  kwHover.value = -1
}

/* A2 年历：悬停 → 那一天；默认 → 全年结论 */
const yearReadout = computed(() => {
  const i = yearHover.value
  if (i >= 0 && i < dailyCounts.value.length) {
    const n = num(dailyCounts.value[i])
    return n > 0 ? `${dayLabel(i)} · ${fmt(n)} 条` : `${dayLabel(i)} · 没有消息`
  }
  return `全年活跃 ${fmt(activeDays.value)} 天 · 最高一天 ${fmt(peakCount.value)} 条`
})
// 格子本身 aria-hidden，概括挂在容器上：367 个格子都进 Tab 序等于让人按几百次
const yrGridLabel = computed(
  () => `${year.value} 年逐日消息量热力图，全年活跃 ${fmt(activeDays.value)} 天，最高一天 ${fmt(peakCount.value)} 条`
)

/* C1 作息切片：悬停 → 那个「周几 × 钟点」；默认 → 矩阵总量（四个指标行不动） */
const matrixReadout = computed(() => {
  const i = matrixHover.value
  if (i >= 0 && i < 168) {
    const w = Math.floor(i / 24)
    const h = i % 24
    const n = num(matrix.value[w]?.[h])
    const wd = weekdayLabels.value[w] || `周${w + 1}`
    return n > 0 ? `${wd} ${pad2(h)}:00 · ${fmt(n)} 条` : `${wd} ${pad2(h)}:00 · 几乎没有消息`
  }
  return `一周 168 格 · 共 ${fmt(matrixTotal.value)} 条`
})
const hhGridLabel = computed(
  () => `一周 7 天 × 24 小时的消息密度矩阵，最常亮起 ${mostActiveWeekdayName.value} ${pad2(mostActiveHour.value)}:00`
)

/* B2 十二个月的主演：悬停 → 那个月的主演与条数 */
const monthReadout = computed(() => {
  const i = monthHover.value
  const m = i >= 0 ? monthly.value[i] : null
  if (!m) return null
  return {
    month: num(m.month) || i + 1,
    name: String(m.displayName || '').trim(),
    count: num(m.messages)
  }
})

/* D4 年度聊天排行：悬停 → 那个人的往来拆分 */
const rankReadout = computed(() => {
  const i = rankHover.value
  const r = i >= 0 ? rankList.value[i] : null
  return r ? { name: r.name, out: r.out, inc: r.inc } : null
})

/* C3 年度口头禅：悬停 → 那一段是哪个词、说了多少次 */
const kwReadout = computed(() => {
  const i = kwHover.value
  const s = i >= 0 ? kwStack.value[i] : null
  return s && s.word ? { word: s.word, count: s.count } : null
})
const kwStackLabel = computed(() => `口头禅总量条，共 ${kwStack.value.length} 个词`)

/* ───────────────────────────────────────────
   数字滚动（tabular-nums 由全局 .wrapped-number 提供，
   不加它 count-up 会逐帧抖宽撑破临界格子）
   ─────────────────────────────────────────── */
const cuTotal = useCountUp(() => totalMessages.value, { duration: 1.4 })
const cuPeak = useCountUp(() => peakCount.value, { duration: 1.2 })
const cuBuddy = useCountUp(() => buddyMessages.value, { duration: 1.2 })
const cuChars = useCountUp(() => sentChars.value, { duration: 1.2 })
const cuSticker = useCountUp(() => sentStickerCount.value, { duration: 1.2 })
const cuKeyword = useCountUp(() => heroCount.value, { duration: 1.1 })
const cuInit = useCountUp(() => initRatePct.value, { duration: 1.1, decimals: 1 })
const countUps = [cuTotal, cuPeak, cuBuddy, cuChars, cuSticker, cuKeyword, cuInit]

/* ───────────────────────────────────────────
   入场编排：只动 opacity / transform / filter，零 fly-in
   ─────────────────────────────────────────── */
const stageEl = ref(null)
const sheetEl = ref(null)
const introRunning = ref(false)
let introTl = null
let enterTimer = null
let leaveTimer = null

// 骨架块：与成品同名同位，直接复用最终版面的 grid-area
const SKELETON_BLOCKS = [
  'b-a1', 'b-a2', 'b-a3', 'b-b1', 'b-b2', 'b-b3',
  'b-c1', 'b-c2', 'b-c3', 'b-d1', 'b-d2', 'b-rank', 'b-d3', 'b-people', 'b-foot'
]

const BLOCK_ORDER = ['.b-a1', '.b-a2', '.b-a3', '.b-b1', '.b-b2', '.b-b3', '.b-c1', '.b-c2', '.b-c3', '.b-d1', '.b-d2', '.b-rank', '.b-d3', '.b-people']
const q = (sel) => (sheetEl.value ? Array.from(sheetEl.value.querySelectorAll(sel)) : [])
const blockEls = () => (sheetEl.value ? BLOCK_ORDER.map((s) => sheetEl.value.querySelector(s)).filter(Boolean) : [])
const FX_SEL = '.yr-cell, .hh-cell, .mo-av, .ppl-chip, .bubble, .rs-pin, .crown'
// 所有量条从 0 拉满：duo-bar（含 --thin）/ 开口占比 / 回复尺 / 口头禅堆叠 / 24h 跨度 / 月度小条
const BAR_SEL = '.duo-bar, .split-bar, .rs-fill, .kw-stack, .span-fill, .mo-bar b'

/* ───────────────────────────────────────────
   玻璃材质的指针响应：反光 / 边框光晕 / ≤2.4° 倾斜 / 夜空视差
   ─────────────────────────────────────────────
   sheet 上一个 pointermove 委托，rAF 里每帧最多写一次 CSS 变量——
   没有常驻循环，指针不动就一行代码都不跑。写的是块上的
   --mx/--my（反光圆心）、--rx/--ry（倾斜角）、--px/--py（归一化偏移，夜空视差用）。 */
let litEl = null
let moveRaf = 0
let lastMove = null

const clearLit = () => {
  if (moveRaf) { cancelAnimationFrame(moveRaf); moveRaf = 0 }
  lastMove = null
  if (!litEl) return
  litEl.classList.remove('is-lit')
  for (const p of ['--mx', '--my', '--rx', '--ry', '--px', '--py']) litEl.style.removeProperty(p)
  litEl = null
}

const applyPointer = () => {
  moveRaf = 0
  const ev = lastMove
  if (!ev || reduced.value || introRunning.value) return
  const blk = ev.target && typeof ev.target.closest === 'function' ? ev.target.closest('.blk') : null
  if (blk !== litEl) {
    if (litEl) {
      litEl.classList.remove('is-lit')
      for (const p of ['--mx', '--my', '--rx', '--ry', '--px', '--py']) litEl.style.removeProperty(p)
    }
    litEl = blk
    if (blk) blk.classList.add('is-lit')
  }
  if (!blk) return
  const r = blk.getBoundingClientRect()
  if (!r.width || !r.height) return
  const x = ev.clientX - r.left
  const y = ev.clientY - r.top
  const nx = Math.max(-0.5, Math.min(0.5, x / r.width - 0.5))
  const ny = Math.max(-0.5, Math.min(0.5, y / r.height - 0.5))
  blk.style.setProperty('--mx', `${x.toFixed(1)}px`)
  blk.style.setProperty('--my', `${y.toFixed(1)}px`)
  blk.style.setProperty('--rx', `${(ny * -2.4).toFixed(2)}deg`)
  blk.style.setProperty('--ry', `${(nx * 2.8).toFixed(2)}deg`)
  blk.style.setProperty('--px', nx.toFixed(3))
  blk.style.setProperty('--py', ny.toFixed(3))
}

const onSheetMove = (ev) => {
  lastMove = ev
  if (!moveRaf) moveRaf = requestAnimationFrame(applyPointer)
}

function primeInitialState () {
  if (!sheetEl.value) return
  introRunning.value = true
  clearLit()
  if (reduced.value) {
    gsap.set(blockEls(), { clearProps: 'opacity,filter,transform' })
    gsap.set(q('.b-foot'), { clearProps: 'opacity' })
    gsap.set(q(FX_SEL), { clearProps: 'opacity,transform' })
    gsap.set(q(BAR_SEL), { clearProps: 'transform' })
    gsap.set(sheetEl.value, { opacity: 0 })
    return
  }
  gsap.set(sheetEl.value, { opacity: 1 })
  gsap.set(blockEls(), { opacity: 0 })
  gsap.set(q('.b-foot'), { opacity: 0 })
  gsap.set(q(FX_SEL), { opacity: 0 })
  gsap.set(q(BAR_SEL), { scaleX: 0, transformOrigin: '0 50%' })
}

function playIntro () {
  introTl?.kill()
  if (!sheetEl.value) return

  if (reduced.value) {
    countUps.forEach((c) => c.finish())
    introTl = gsap.timeline({ onComplete: () => { introRunning.value = false } })
    introTl.fromTo(sheetEl.value, { opacity: 0 }, { opacity: 1, duration: 0.18, ease: 'power1.out' })
    return
  }

  const blocks = blockEls()
  const tl = gsap.timeline({
    onComplete: () => {
      // 交回 CSS：残留的内联值会把块级 transition（含悬停倾斜）压死
      gsap.set(blocks, { clearProps: 'opacity,filter,transform' })
      gsap.set(q('.b-foot'), { clearProps: 'opacity' })
      gsap.set(q(FX_SEL), { clearProps: 'opacity,transform' })
      gsap.set(q(BAR_SEL), { clearProps: 'transform' })
      introRunning.value = false
    }
  })
  introTl = tl

  tl.fromTo(blocks, {
    opacity: 0,
    scale: 0.985,
    filter: 'blur(4px)'
  }, {
    opacity: 1,
    scale: 1,
    filter: 'blur(0px)',
    duration: 0.26,
    ease: 'power2.out',
    stagger: 0.028,
    force3D: true
  }, 0)

  tl.to(q('.b-foot'), { opacity: 1, duration: 0.24, ease: 'power2.out' }, 0.34)

  tl.add(() => countUps.forEach((c) => c.restart()), 0.42)

  // 量条自绘：所有横条从左端拉满，节奏跟在块显形之后
  tl.to(q(BAR_SEL), { scaleX: 1, duration: 0.6, ease: 'power3.inOut', stagger: 0.018 }, 0.52)
  tl.to(q('.rs-pin, .crown'), { opacity: 1, duration: 0.3, ease: 'power1.out' }, 1.05)

  tl.to(q('.yr-cell'), {
    opacity: 1,
    duration: 0.22,
    ease: 'power1.out',
    stagger: { grid: [53, 7], from: [0, 0], each: 0.0016 }
  }, 0.5)

  tl.fromTo(q('.hh-cell'), {
    opacity: 0,
    scale: 0.42
  }, {
    opacity: 1,
    scale: 1,
    duration: 0.26,
    ease: 'power2.out',
    stagger: { grid: [7, 24], from: [0, 0], each: 0.005 }
  }, 0.62)

  tl.fromTo(q('.mo-av'), {
    opacity: 0,
    scale: 0.9
  }, {
    opacity: 1,
    scale: 1,
    duration: 0.24,
    ease: 'power2.out',
    stagger: 0.026
  }, 0.74)

  tl.to(q('.ppl-chip'), { opacity: 1, duration: 0.22, ease: 'power1.out', stagger: 0.04 }, 0.88)

  // 深夜气泡：整块淡入，绝不逐字 —— 逐字 blur 会在字与字之间留清晰缝隙，等于隐私失效
  tl.fromTo(q('.bubble'), {
    opacity: 0,
    scale: 0.96
  }, {
    opacity: 1,
    scale: 1,
    duration: 0.3,
    ease: 'power2.out'
  }, 1.0)
}

/* ───────────────────────────────────────────
   生命周期
   ─────────────────────────────────────────── */
function start () {
  clearTimeout(enterTimer)
  clearTimeout(leaveTimer)
  // deck 翻页是 700ms 的 CSS transform 过渡，且 isActive 在过渡「开始」那一刻就变 true
  enterTimer = setTimeout(() => {
    primeInitialState()
    playIntro()
  }, reduced.value ? 160 : 700)
}

function stopAll () {
  clearTimeout(enterTimer)
  clearTimeout(leaveTimer)
  introTl?.kill()
  introTl = null
  introRunning.value = false
}

// 版面是 v-if="isOk" 的：数据晚到时 mount 那一刻 stageEl 还不存在，
// 所以初始化必须等版面真的进 DOM 之后再跑一次，不能只挂在 onMounted 上。
let stageInited = false

const initStage = async () => {
  if (stageInited || !isOk.value) return
  await nextTick()
  if (!stageEl.value) return
  stageInited = true
  if (sheetEl.value) {
    sheetEl.value.addEventListener('pointermove', onSheetMove, { passive: true })
    sheetEl.value.addEventListener('pointerleave', clearLit, { passive: true })
    sheetEl.value.addEventListener('pointercancel', clearLit, { passive: true })
  }
  primeInitialState()
  if (props.isActive) start()
}

const teardownStage = () => {
  // 悬停读数先复位：否则翻走 / 重试后读数会停在最后碰过的那个格子上
  resetHovers()
  clearLit()
  if (!stageInited) return
  stageInited = false
  if (sheetEl.value) {
    sheetEl.value.removeEventListener('pointermove', onSheetMove)
    sheetEl.value.removeEventListener('pointerleave', clearLit)
    sheetEl.value.removeEventListener('pointercancel', clearLit)
  }
  stopAll()
}

onMounted(initStage)

// 重试成功 / 数据晚到：ok 后补一次初始化；退回非 ok（重试中）先把上一版彻底拆掉
watch(isOk, (ok) => {
  if (ok) initStage()
  else teardownStage()
})

onBeforeUnmount(() => {
  teardownStage()
  releaseDeck()
})

watch(() => props.isActive, (v) => {
  if (v) {
    if (!stageInited) { initStage(); return }
    start()
  } else {
    clearTimeout(enterTimer)
    resetHovers()
    // 翻走过程中内容不能消失：等过渡走完再复位
    leaveTimer = setTimeout(() => { stopAll(); primeInitialState() }, 750)
  }
})
</script>

<style scoped>
/* ══════════ 令牌 · 暖纸体系 ══════════
   来源：Card03ReplySpeed 的绿墨投影 + Card01CyberSchedule 的奶油黄 / 长春花蓝
       + WrappedDeckBackground 的 #F3FFF8 底
   本页不画不透明底：deck 背景层透上来，只加一层暖光罩。 */
.wrap-final {
  /* ── 1 表面 ── */
  --wash-a: rgba(7, 193, 96, 0.045);
  --wash-b: rgba(242, 170, 0, 0.042);
  --wash-c: rgba(124, 143, 203, 0.042);
  --wash-veil: rgba(255, 255, 255, 0.34);

  --surface-card: rgba(255, 255, 255, 0.72);
  --surface-inset: rgba(11, 61, 38, 0.045);
  --surface-inset-2: rgba(11, 61, 38, 0.075);
  --surface-hairline: rgba(31, 66, 50, 0.07);

  --stroke-card: rgba(31, 66, 50, 0.10);
  --stroke-inset: rgba(31, 66, 50, 0.06);


  /* ── 2 文字 ── */
  --ink-0: #22332B;
  --ink-1: #52655C;
  --ink-2: #606F68;
  --ink-on-bubble: #0B3D26;
  --ink-on-cream: #22332B;

  /* ── 3 强调色：1 主 + 2 辅，按数字的语义单位分组 ── */
  --qty: #07C160;
  --qty-deep: #06AD56;
  --qty-ink: #07713E;
  --qty-tint: rgba(7, 193, 96, 0.10);
  --qty-tint-2: rgba(7, 193, 96, 0.055);
  --qty-soft: #95EC69;

  --time: #5B6FB8;
  --time-soft: #9FB0DA;
  --time-pale: #B9C4E4;
  --time-ink: #3F4F92;
  --time-tint: rgba(124, 143, 203, 0.12);
  --time-tint-2: rgba(124, 143, 203, 0.06);

  --ppl: #F2AA00;
  --ppl-cream: #FFE9A3;
  --ppl-ink: #96590A;
  --ppl-tint: rgba(242, 170, 0, 0.10);
  --ppl-tint-2: rgba(242, 170, 0, 0.05);

  /* ── 4 圆角 ── */
  /* 圆角：对齐 shadcn 的尺度（--radius: .5rem，lg 8 / md 6 / sm 4），
     只有头像和圆点保持整圆——那是形状不是圆角。 */
  --r-card: 6px;
  --r-group: 5px;
  --r-inner: 4px;
  --r-bar: 3px;
  --r-tag: 4px;
  --r-cell: 2px;
  --r-pill: 999px;

  /* ── 5 节奏 ──
     px 地板压到中文可读的硬底线（正文 11 / 标签 9 / 数字 12），
     再让 cqh 系数在 700px 可用高度上自然落到这条线附近：
     这样矮窗只是「字变小」，不再需要靠藏内容来防裁切。 */
  --gap: max(5px, 0.72cqh);
  --pad-card: max(6px, 0.78cqh) max(9px, 0.7cqw);
  --pad-inner: max(3px, 0.42cqh) max(6px, 0.45cqw);
  --lh-body: 1.4;
  --lh-tight: 1.25;
  --ls-label: 0.06em;
  --ls-num: -0.012em;

  --fs-mega: max(20px, 3.3cqh);
  --fs-big: max(14px, 2.25cqh);
  --fs-mid: max(13px, 1.85cqh);
  --fs-quote: max(14px, 1.95cqh);
  --fs-num: max(12px, 1.6cqh);
  --fs-name: max(11px, 1.5cqh);
  --fs-body: max(11px, 1.5cqh);
  --fs-label: max(9px, 1.25cqh);

  --serif: 'Songti SC', 'STSong', 'SimSun', 'Source Han Serif SC', 'Noto Serif SC', serif;
  --sans: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text',
    'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --spring: cubic-bezier(0.34, 1.3, 0.55, 1);

  /* ── 6 玻璃材质 ──
     磨砂玻璃三件套：backdrop 毛化、顶缘 1px 白高光（specular）、贴地柔影。
     影子刻意压得很低——浅色纸面上影子一重就成了 SaaS 卡片。 */
  --glass-blur: 14px;
  --specular: inset 0 1px 0 rgba(255, 255, 255, 0.85), inset 0 0 0 1px rgba(255, 255, 255, 0.2);
  --shadow-rest: 0 1px 1.5px rgba(11, 61, 38, 0.05), 0 8px 22px -12px rgba(11, 61, 38, 0.13);
  --shadow-lift: 0 2px 3px rgba(11, 61, 38, 0.06), 0 18px 40px -16px rgba(11, 61, 38, 0.22);
  --glint: rgba(7, 193, 96, 0.4);

  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  container-type: size;
  container-name: stage;
  color: var(--ink-0);
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased;
  /* 半透明：deck 的绿/琥珀/蓝光斑 + 52px 网格 + 噪点从下面透上来 */
  background:
    radial-gradient(44% 36% at 14% 6%, var(--wash-a), transparent 72%),
    radial-gradient(40% 32% at 88% 4%, var(--wash-b), transparent 74%),
    radial-gradient(48% 40% at 80% 98%, var(--wash-c), transparent 76%),
    var(--wash-veil);
}

/* ══════════ 版面 ══════════ */
.sheet-final {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  /* deck 顶栏在本页是隐藏的，上 padding 不必让位 */
  padding: max(12px, 1.6cqh) max(16px, 1.2cqw) max(9px, 1.2cqh);
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-template-rows:
    repeat(12, minmax(0, 1fr))    /* 1–12 四条 3 行带 */
    minmax(0, auto)               /* 13   人物带（整条隐藏时塌陷为 0） */
    auto;                         /* 14   页脚 */
  gap: var(--gap);
  isolation: isolate;
}

.b-people { grid-area: 13 / 1 / 14 / 13; }
.b-foot { grid-area: 14 / 1 / 15 / 13; }

/* 带 A：这一年有多少话 */
.b-a1 { grid-area: 1 / 1 / 4 / 4; }
.b-a2 { grid-area: 1 / 4 / 4 / 9; }
.b-a3 { grid-area: 1 / 9 / 4 / 13; }
/* 带 B：陪着你的人 */
.b-b1 { grid-area: 4 / 1 / 7 / 4; }
.b-b2 { grid-area: 4 / 4 / 7 / 10; }
.b-b3 { grid-area: 4 / 10 / 7 / 13; }
/* 带 C：作息与表达 */
.b-c1 { grid-area: 7 / 1 / 10 / 6; }
.b-c2 { grid-area: 7 / 6 / 10 / 10; }
.b-c3 { grid-area: 7 / 10 / 10 / 13; }
/* 带 D：四块等宽 */
.b-d1 { grid-area: 10 / 1 / 13 / 4; }
.b-d2 { grid-area: 10 / 4 / 13 / 7; }
.b-rank { grid-area: 10 / 7 / 13 / 10; }
.b-d3 { grid-area: 10 / 10 / 13 / 13; }

/* ══════════ 卡片基类：磨砂玻璃 ══════════ */
.blk {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  padding: var(--pad-card);
  border-radius: var(--r-card);
  background: var(--surface-card);
  border: 1px solid var(--stroke-card);
  /* deck 的光斑 / 网格 / 噪点从块底下糊过来——这就是「不画自己的不透明底」的回报 */
  backdrop-filter: blur(var(--glass-blur)) saturate(1.35);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.35);
  box-shadow: var(--specular), var(--shadow-rest);
  transform: perspective(1100px) rotateX(var(--rx, 0deg)) rotateY(var(--ry, 0deg));
  transition: transform 0.32s var(--spring), box-shadow 0.32s var(--ease-out);
}
.blk--qty { --glint: rgba(7, 193, 96, 0.5); background: linear-gradient(180deg, var(--qty-tint-2), transparent 58%), var(--surface-card); }
.blk--time { --glint: rgba(91, 111, 184, 0.48); background: linear-gradient(180deg, var(--time-tint-2), transparent 58%), var(--surface-card); }
.blk--ppl { --glint: rgba(242, 170, 0, 0.42); background: linear-gradient(180deg, var(--ppl-tint-2), transparent 58%), var(--surface-card); }
/* 窄块保护：圆角降一级 */
.blk--slim { border-radius: var(--r-group); padding: max(5px, 0.6cqh) max(11px, 0.8cqw); }

/* ── 分层：点缀在 0，正文在 1，玻璃前表面的反光在 3 ——
   反光必须压在墨上面才像玻璃，压在墨下面就成了底纹 ── */
.blk > .deco { z-index: 0; }
.blk > *:not(.deco):not(.sky) { position: relative; z-index: 1; }

/* ── 指针落在块上：光标处一圈边框光晕（1px 环，mask 抠出来）+ 玻璃反光 + 微倾斜 ── */
.blk:not(.sk)::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: radial-gradient(240px circle at var(--mx, 50%) var(--my, 40%), var(--glint), transparent 72%);
  -webkit-mask-image: linear-gradient(#000 0 0), linear-gradient(#000 0 0);
  -webkit-mask-clip: content-box, border-box;
  -webkit-mask-composite: xor;
  mask-image: linear-gradient(#000 0 0), linear-gradient(#000 0 0);
  mask-clip: content-box, border-box;
  mask-composite: exclude;
  opacity: 0;
  transition: opacity 0.4s var(--ease-out);
  pointer-events: none;
  z-index: 3;
}
.blk:not(.sk)::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(
    320px circle at var(--mx, 50%) var(--my, 30%),
    rgba(255, 255, 255, 0.34),
    rgba(255, 255, 255, 0.05) 46%,
    transparent 70%
  );
  opacity: 0;
  transition: opacity 0.45s var(--ease-out);
  pointer-events: none;
  z-index: 3;
}
.blk.is-lit {
  transform: perspective(1100px) rotateX(var(--rx, 0deg)) rotateY(var(--ry, 0deg)) translateY(-1.5px) scale(1.006);
  box-shadow: var(--specular), var(--shadow-lift);
  will-change: transform;
}
.blk.is-lit::before,
.blk.is-lit::after { opacity: 1; }
/* 夜块的反光换成月光，白色反光会把星空洗灰 */
.blk--night { --glint: rgba(255, 233, 163, 0.36); }
.blk--night::after {
  background: radial-gradient(
    300px circle at var(--mx, 50%) var(--my, 30%),
    rgba(185, 205, 255, 0.13),
    transparent 62%
  );
}

.sheet-final.is-intro .blk { transition: none; }
/* 入场时 gsap 每帧写内联 transform，CSS 过渡会跟它抢同一个属性 */
.sheet-final.is-intro .yr-cell,
.sheet-final.is-intro .hh-cell,
.sheet-final.is-intro .mo-av,
.sheet-final.is-intro .rank-item { transition: none; }

/* ══════════ 通用排字 ══════════ */
.kicker {
  font-size: var(--fs-label);
  font-weight: 600;
  letter-spacing: var(--ls-label);
  color: var(--ink-2);
  line-height: var(--lh-tight);
  flex: none;
  margin-bottom: max(3px, 0.4cqh);
}
.kicker--r { font-weight: 500; text-align: right; margin-bottom: 0; }
.head-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  flex: none;
  margin-bottom: max(3px, 0.4cqh);
  min-width: 0;
}
.head-line .kicker { margin-bottom: 0; min-width: 0; }
.head-line .kicker--r { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.line {
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--ink-1);
  flex: none;
  min-width: 0;
}
.dt {
  font-size: var(--fs-label);
  font-weight: 500;
  letter-spacing: var(--ls-label);
  color: var(--ink-2);
  line-height: var(--lh-tight);
}
.dd {
  font-size: var(--fs-num);
  font-weight: 600;
  letter-spacing: var(--ls-num);
  color: var(--ink-0);
  line-height: var(--lh-tight);
}
.nm {
  font-size: var(--fs-name);
  font-weight: 500;
  color: var(--ink-0);
  line-height: var(--lh-tight);
  min-width: 0;
}
.nm-2 {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.foot-note {
  margin-top: auto;
  padding-top: max(2px, 0.25cqh);
  font-size: var(--fs-label);
  color: var(--ink-2);
  line-height: var(--lh-tight);
  flex: none;
}
.void-line {
  margin: auto 0;
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--ink-2);
}
.one { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.two {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.col { display: flex; flex-direction: column; min-width: 0; gap: 1px; }

.mega {
  font-size: var(--fs-mega);
  font-weight: 600;
  letter-spacing: var(--ls-num);
  line-height: 1.12;
  color: var(--qty-ink);
}
.mega-row { display: flex; align-items: baseline; gap: 5px; flex: none; }
.mega-unit { font-size: var(--fs-label); letter-spacing: 0.24em; color: var(--ink-2); }

.big-row { display: flex; align-items: baseline; gap: 5px; flex: none; flex-wrap: wrap; }
.big {
  font-size: var(--fs-big);
  font-weight: 600;
  letter-spacing: var(--ls-num);
  line-height: 1.15;
  color: var(--qty-ink);
}
.big-unit { font-size: var(--fs-label); color: var(--ink-2); }
.big-lead { font-size: var(--fs-num); color: var(--ink-1); }
.mid {
  font-size: var(--fs-mid);
  font-weight: 600;
  letter-spacing: var(--ls-num);
  line-height: 1.1;
  color: var(--time-ink);
}
.blk--time .big { color: var(--time-ink); }
.blk--ppl .big { color: var(--ppl-ink); }
/* 大数换渐变墨：上浅下深，像油墨压进纸里；color 保留作为不支持时的兜底 */
.mega,
.big {
  background: linear-gradient(180deg, var(--num-hi, #10AC63) 0%, var(--num-lo, #05673A) 92%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.blk--time .big { --num-hi: #6076C2; --num-lo: #36427F; }
.blk--ppl .big { --num-hi: #B06E0C; --num-lo: #7A4708; }

.inset {
  border-radius: var(--r-inner);
  background: var(--surface-inset);
  padding: var(--pad-inner);
  min-width: 0;
}
.tag {
  border-radius: var(--r-tag);
  padding: 1px 7px;
  font-size: var(--fs-label);
  font-weight: 500;
  letter-spacing: var(--ls-label);
  line-height: 1.5;
  white-space: nowrap;
  flex: none;
}
.tag--qty { background: var(--qty-tint); color: var(--qty-ink); }
.tag--time { background: var(--time-tint); color: var(--time-ink); }

/* 头像：一律 contain，禁止 cover */
.av {
  flex: none;
  border-radius: var(--r-pill);
  overflow: hidden;
  background: var(--surface-inset-2);
  display: grid;
  place-items: center;
}
.av img { width: 100%; height: 100%; object-fit: contain; display: block; }
.av-ini {
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--ink-2);
  line-height: 1;
}
.av--ring { box-shadow: 0 0 0 2px var(--ppl-cream), 0 0 0 3px rgba(242, 170, 0, 0.28); }
.av22 { width: max(16px, 2.0cqh); height: max(16px, 2.0cqh); }
.av24 { width: max(20px, 2.5cqh); height: max(20px, 2.5cqh); }
.av26 { width: max(21px, 2.6cqh); height: max(21px, 2.6cqh); }
.av28 { width: max(24px, 2.9cqh); height: max(24px, 2.9cqh); }
.av36 { width: max(28px, 3.6cqh); height: max(28px, 3.6cqh); }
.av48 { width: max(30px, 4.0cqh); height: max(30px, 4.0cqh); }

.who-row { display: flex; align-items: center; gap: max(5px, 0.45cqw); min-width: 0; flex: none; }
.who-row .nm { flex: 0 1 auto; }
.who-row .dd { flex: none; }

.mgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: max(3px, 0.3cqh) max(4px, 0.32cqw);
  flex: none;
  margin-top: max(3px, 0.35cqh);
}
.mgrid--push { margin-top: auto; }
.mgrid--3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.mcell { display: flex; flex-direction: column; gap: 0; justify-content: center; }
/* 单行条：标签与值同一行，比两行格省掉近一半高度 */
.mgrid--inline .mcell {
  flex-direction: row;
  align-items: baseline;
  gap: 0.4em;
  justify-content: flex-start;
}
.mgrid--inline .dt { flex: none; }
.mcell--wide { grid-column: span 2; }
.mcell .dd { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.streak-range { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ══════════ A2 · 365 天年历 ══════════ */
.ghost-year {
  font-size: var(--fs-big);
  font-weight: 600;
  color: var(--ink-2);
  opacity: 0.28;
  letter-spacing: 0.04em;
  flex: none;
}
.yr-months {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  font-size: var(--fs-label);
  color: var(--ink-2);
  line-height: 1.25;
  flex: none;
  padding-left: max(13px, 1cqw);
}
.yr-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  gap: max(3px, 0.25cqw);
  align-items: stretch;
  padding: max(2px, 0.3cqh) 0;
}
.yr-week {
  flex: none;
  align-self: center;
  width: max(10px, 0.8cqw);
  display: grid;
  grid-template-rows: repeat(7, max(7px, 1.15cqh));
  font-size: max(9px, 1.1cqh);
  color: var(--ink-2);
  line-height: 1;
  align-items: center;
}
.yr-grid {
  flex: 1 1 auto;
  min-width: 0;
  align-self: center;
  display: grid;
  grid-template-columns: repeat(53, minmax(0, 1fr));
  grid-template-rows: repeat(7, max(7px, 1.15cqh));
  grid-auto-flow: column;
  gap: 2px;
}
.yr-cell { border-radius: var(--r-cell); display: block; }
/* 最疯那天的格子微微搏动：影子在呼吸，不占布局 */
.yr-cell.is-peak {
  box-shadow: 0 0 0 1.5px var(--ppl);
  animation: peak-pulse 3.2s ease-in-out infinite;
}
@keyframes peak-pulse {
  0%, 100% { box-shadow: 0 0 0 1.5px var(--ppl); }
  50% { box-shadow: 0 0 0 1.5px var(--ppl), 0 0 9px 2px rgba(242, 170, 0, 0.55); }
}
/* 悬停反馈：描边 + 微微放大。用 outline 不用 border/box-shadow ——
   outline 不占布局，也不违反「本页不加投影」那条。开头对齐用的空格没有 data-d，碰不到。 */
.yr-cell[data-d] { transition: transform 0.12s var(--ease-out); }
.yr-cell[data-d]:hover {
  position: relative;
  z-index: 2;
  transform: scale(1.65);
  outline: 1.5px solid var(--qty-ink);
}
.lv-1 { background: transparent; }
.yr-cell.lv0, .lgc.lv0 { background: rgba(11, 61, 38, 0.05); }
.yr-cell.lv1, .lgc.lv1 { background: rgba(7, 193, 96, 0.22); }
.yr-cell.lv2, .lgc.lv2 { background: rgba(7, 193, 96, 0.42); }
.yr-cell.lv3, .lgc.lv3 { background: rgba(7, 193, 96, 0.62); }
.yr-cell.lv4, .lgc.lv4 { background: #07C160; }
.yr-legend {
  display: flex;
  align-items: center;
  gap: 3px;
  flex: none;
  padding-top: max(2px, 0.3cqh);
}
.lg { font-size: var(--fs-label); color: var(--ink-2); line-height: 1.3; }
.lg-read { margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lgc { width: max(7px, 0.55cqh); height: max(7px, 0.55cqh); border-radius: var(--r-cell); display: block; }

/* ══════════ A3 · 最疯的一天 ══════════ */
/* 24 小时跨度尺：整条轨是一整天，填色段是「第一句 → 最后一句」 */
.a3-span { flex: none; margin-top: max(4px, 0.5cqh); min-width: 0; }
.span-track {
  position: relative;
  display: block;
  height: 6px;
  border-radius: var(--r-bar);
  background: var(--surface-inset-2);
  overflow: hidden;
}
.span-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--time-soft), var(--qty));
}
.span-cap {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: max(4px, 0.35cqw);
  padding-top: 2px;
  min-width: 0;
}
.span-cap > .dt { flex: none; }
.span-cap-m { flex: 0 1 auto; min-width: 0; text-align: center; }

.quote-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: max(5px, 0.4cqw);
  margin-top: auto;
  flex: none;
  min-width: 0;
}
.quo { border-radius: var(--r-group); display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.qt { font-size: var(--fs-body); color: var(--ink-0); line-height: var(--lh-tight); }

/* ══════════ B1 · 年度搭子 ══════════ */
.buddy-top { margin-bottom: max(2px, 0.25cqh); }
.duo-bar {
  display: block;
  height: 6px;
  border-radius: var(--r-bar);
  flex: none;
  margin-top: max(3px, 0.35cqh);
  background: linear-gradient(90deg, var(--qty) 0 var(--out), var(--time-soft) var(--out) 100%);
}
.duo-legend {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-size: var(--fs-label);
  color: var(--ink-1);
  line-height: var(--lh-tight);
  padding-top: 1px;
  flex: none;
}
.duo-legend b { font-weight: 600; color: var(--ink-0); }

/* ══════════ B2 · 十二个月的主演 ══════════ */
.mo-row {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: max(4px, 0.4cqw);
  align-content: center;
}
.mo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: max(3px, 0.32cqh);
  min-width: 0;
}
.mo-m { font-size: var(--fs-label); color: var(--ink-2); line-height: 1.2; }
.mo-av { width: max(30px, 4.0cqh); height: max(30px, 4.0cqh); }
.mo-nm { max-width: 100%; text-align: center; }
/* 月度量条：绿=量，最热的那个月满色，其余压淡 */
.mo-bar {
  align-self: stretch;
  display: block;
  height: 3px;
  border-radius: var(--r-bar);
  background: var(--surface-inset-2);
  overflow: hidden;
  margin-top: 1px;
}
.mo-bar b { display: block; height: 100%; border-radius: inherit; background: var(--qty); opacity: 0.5; }
.mo-bar.is-hot b { opacity: 1; }
/* 悬停反馈：量条描边 + 满色，月份标签压深，全是不占布局的属性 */
.mo:hover .mo-bar { outline: 1px solid var(--qty-ink); }
.mo:hover .mo-bar b { opacity: 1; }
.mo:hover .mo-m { color: var(--ink-0); }
.champ {
  display: flex;
  align-items: center;
  gap: max(5px, 0.45cqw);
  border-radius: var(--r-group);
  flex: none;
  margin-top: max(4px, 0.5cqh);
  min-width: 0;
}
.champ-t {
  font-size: var(--fs-label);
  color: var(--ink-1);
  line-height: var(--lh-tight);
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.champ-t b { font-weight: 600; color: var(--ink-0); }
/* 桂冠条右端补一句量条的读数，那一排才有解释；
   它同时是本块的悬停读数位，所以要能被 .one 收成一行，不许把桂冠条顶出去 */
.champ-r { margin-left: auto; flex: 0 1 auto; min-width: 0; max-width: 66%; }
.champ-r b { font-weight: 600; color: var(--ink-0); }

/* ══════════ B3 · 深夜 ══════════ */
.night-when {
  margin-top: max(5px, 0.6cqh);
  flex: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 全版唯一一次 --qty-soft：deck 的招牌语汇 */
.bubble {
  margin-top: max(3px, 0.35cqh);
  flex: none;
  /* 随内容收窄，不撑满整行；对方说的靠左、自己说的靠右，与微信气泡方向一致 */
  align-self: flex-start;
  max-width: 92%;
  width: fit-content;
  background: var(--qty-soft);
  color: var(--ink-on-bubble);
  border-radius: 5px 5px 5px 2px;
  padding: max(4px, 0.5cqh) max(8px, 0.6cqw);
  font-size: var(--fs-body);
  line-height: var(--lh-tight);
  transform-origin: 0 100%;
}
.bubble--mine {
  align-self: flex-end;
  border-radius: 5px 5px 2px 5px;
  transform-origin: 100% 100%;
}
/* 自己说的那条，署名行也跟着靠右，读起来是一句完整的「谁在什么时候说了什么」 */
.night-when--mine { align-self: flex-end; }
/* 深夜块头像放大：这一块内容少，让人像撑起高度 */
.b-b3 .av36 { width: max(40px, 5.2cqh); height: max(40px, 5.2cqh); }

/* ══════════ 夜空底（视觉语言取自 Card01「赛博作息」的夜空，保持 deck 内一致） ══════════
   整块转暗，所以块内的墨色令牌必须整套反过来，否则深色底上还是深色字＝全瞎。 */
.blk--night {
  --ink-0: #f2f5fb;
  --ink-1: #b9c4e4;
  --ink-2: #9fb0da;
  --surface-inset: rgba(255, 255, 255, 0.09);
  --surface-inset-2: rgba(255, 255, 255, 0.14);
  --stroke-card: rgba(159, 176, 218, 0.22);
  border-color: var(--stroke-card);
  background:
    radial-gradient(circle at 86% 12%, rgba(255, 233, 163, 0.1), transparent 42%),
    linear-gradient(180deg, #0a1030 0%, #141f45 44%, #1d2c56 76%, #23345f 100%);
  isolation: isolate;
}
.blk--night > *:not(.sky) { position: relative; z-index: 1; }

.sky {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  border-radius: inherit;
}
/* 视差层：四边各大 12px，指针推它反向漂移时不露底；
   位移只发生在这层，块本身的 scrollWidth 不受影响 */
.sky-drift {
  /* 左/上多出 12px 供反向漂移；右/下只留 2px —— scrollWidth 只量右/下溢出，
     压在 PROBE 的 3px 门槛之内 */
  position: absolute;
  top: -12px;
  left: -12px;
  right: -2px;
  bottom: -2px;
  transform: translate3d(calc(var(--px, 0) * -9px), calc(var(--py, 0) * -7px), 0);
  transition: transform 0.3s var(--ease-out);
}
.star {
  position: absolute;
  border-radius: 9999px;
  background: #ffffff;
  opacity: 0.7;
  animation: night-twinkle 2.8s ease-in-out infinite;
}
@keyframes night-twinkle {
  0%, 100% { transform: scale(0.8); filter: brightness(0.7); }
  50% { transform: scale(1.15); filter: brightness(1.3); }
}
/* 一弯月亮：晕圈 + 微微呼吸的月体 */
.moon {
  position: absolute;
  top: 13%;
  right: 8%;
  width: max(26px, 3.4cqh);
  height: max(26px, 3.4cqh);
}
.moon-halo { fill: rgba(255, 233, 163, 0.09); }
.moon-body {
  fill: rgba(255, 233, 163, 0.82);
  filter: drop-shadow(0 0 6px rgba(255, 233, 163, 0.4));
  animation: moon-breathe 6.5s ease-in-out infinite;
}
@keyframes moon-breathe {
  0%, 100% { opacity: 0.82; }
  50% { opacity: 1; }
}
/* 流星：每 9.5s 划一次，固定往左下飞（scrollWidth 只量右/下溢出，往左飞怎么飞都安全） */
.shoot {
  position: absolute;
  top: 15%;
  right: 5%;
  width: 66px;
  height: 1.5px;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.95));
  transform: rotate(160deg);
  opacity: 0;
  animation: shoot-fly 9.5s linear infinite;
  animation-delay: 3.4s;
}
@keyframes shoot-fly {
  0%, 90% { opacity: 0; transform: rotate(160deg) translateX(0); }
  91.6% { opacity: 0.85; }
  96% { opacity: 0; transform: rotate(160deg) translateX(132px); }
  100% { opacity: 0; transform: rotate(160deg) translateX(132px); }
}
/* 夜里头像的暖环换成月光白，琥珀在深蓝上会脏 */
.blk--night .av--ring { box-shadow: 0 0 0 2px rgba(255, 233, 163, 0.55); }

/* ══════════ C1 · 作息切片 ══════════ */
.hh-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  gap: max(4px, 0.3cqw);
  align-items: stretch;
}
.hh-week {
  flex: none;
  width: max(20px, 1.7cqw);
  display: grid;
  grid-template-rows: repeat(7, minmax(0, 1fr));
  align-items: center;
  font-size: max(9px, 1.1cqh);
  color: var(--ink-2);
  line-height: 1;
}
.hh-grid {
  flex: 1 1 auto;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(24, minmax(0, 1fr));
  grid-template-rows: repeat(7, minmax(0, 1fr));
  gap: max(2px, 0.2cqw);
}
.hh-cell { border-radius: var(--r-cell); display: block; transition: transform 0.12s var(--ease-out); }
.hh-cell:hover {
  position: relative;
  z-index: 2;
  transform: scale(1.4);
  outline: 1.5px solid var(--time-ink);
}
.hh-cell.lv0 { background: rgba(11, 61, 38, 0.05); }
.hh-cell.lv1 { background: rgba(124, 143, 203, 0.28); }
.hh-cell.lv2 { background: rgba(124, 143, 203, 0.5); }
.hh-cell.lv3 { background: rgba(124, 143, 203, 0.72); }
.hh-cell.lv4 { background: #5B6FB8; }
.hh-axis {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  font-size: var(--fs-label);
  color: var(--ink-2);
  line-height: 1.3;
  flex: none;
  padding-top: 1px;
  padding-left: calc(max(20px, 1.7cqw) + max(4px, 0.3cqw));
}
.rhythm-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: max(2px, 0.25cqh) max(5px, 0.45cqw);
  flex: none;
  margin-top: max(3px, 0.4cqh);
}
.rhythm-metrics > div {
  display: flex;
  align-items: baseline;
  gap: 0.4em;
  min-width: 0;
}
.rhythm-metrics .dd {
  font-size: var(--fs-label);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ══════════ C2 · 你说的话 ══════════ */
/* 两行脚注共用一个「贴底」容器：单独给每行 margin-top:auto 会把它们拆散 */
.c2-foot { margin-top: auto; padding-top: max(2px, 0.25cqh); flex: none; min-width: 0; }
/* 左右两段脚注同处一行，中间由 space-between 撑开，不会挨在一起 */
.foot-split {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: max(10px, 1.1cqw);
  min-width: 0;
}
.foot-split > .foot-note { margin-top: 0; padding-top: 0; min-width: 0; }
/* 右段本来就挂着 .one，但 flex:none 让它永远不收缩 —— 高一点的窗口里
   字号跟着 cqh 涨上去，省略号就永远轮不到，直接被块的 overflow 切掉。
   允许收缩，挤不下时按预期出省略号。 */
.foot-r { flex: 0 1 auto; min-width: 0; text-align: right; }
.c2-foot .foot-note { margin-top: 0; padding-top: 0; }
/* 大数行右端的小字：靠右、不参与换行 */
.big-tail {
  margin-left: auto;
  flex: none;
  font-size: var(--fs-label);
  color: var(--ink-2);
  white-space: nowrap;
  letter-spacing: var(--ls-label);
}
.c2-foot b { font-weight: 600; color: var(--ink-1); }

/* ══════════ C3 · 年度口头禅 ══════════ */
.quote-hero {
  display: flex;
  align-items: baseline;
  gap: 2px;
  flex: none;
  min-width: 0;
  margin-bottom: 1px;
}
.qm { font-family: var(--serif); font-size: var(--fs-quote); color: var(--ink-2); line-height: 1.5; align-self: flex-start; }
.qw {
  font-family: var(--serif);
  font-size: var(--fs-quote);
  color: var(--ink-0);
  line-height: 1.25;
  min-width: 0;
}
/* 口头禅总量条：hero 满色，其余按 3 档递减，和下面 chips 的底色一一对应 */
/* 分隔用 border 不用 gap：gap 会累加在百分比宽度之外，把整条挤出容器 */
.kw-stack {
  display: flex;
  height: 6px;
  border-radius: var(--r-bar);
  overflow: hidden;
  background: var(--surface-inset-2);
  flex: none;
  margin-top: max(4px, 0.5cqh);
}
.kw-seg {
  display: block;
  height: 100%;
  flex: none;
  min-width: 2px;
  box-sizing: border-box;
  border-right: 1px solid var(--wash-veil);
}
.kw-seg:last-child { border-right: none; }
/* 悬停反馈：描边画在段内（外描边会被 .kw-stack 的 overflow:hidden 切掉） */
.kw-seg:hover { outline: 1.5px solid var(--ppl-ink); outline-offset: -1.5px; }
.kw-seg.kw-hero { background: var(--ppl); }
.kw-seg.kw-t2 { background: rgba(242, 170, 0, 0.66); }
.kw-seg.kw-t1 { background: rgba(242, 170, 0, 0.42); }
.kw-seg.kw-t0 { background: rgba(242, 170, 0, 0.22); }

/* 读数位：kwFoot 可能为空，留一行高度占位，悬停换文案时块高不动 */
.kw-read { min-height: calc(var(--fs-label) * var(--lh-tight)); }
.kw-read b { font-weight: 600; color: var(--ink-1); }
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: max(4px, 0.5cqh);
  overflow: hidden;
  align-content: center;
  flex: 1 1 auto;
  min-height: 0;
}
.chip {
  border-radius: var(--r-tag);
  background: var(--ppl-tint);
  color: var(--ppl-ink);
  font-size: var(--fs-label);
  line-height: 1.4;
  padding: 1px 6px;
  box-shadow: none;
  white-space: nowrap;
}
.chip.kw-t2 { background: rgba(242, 170, 0, 0.22); }
.chip.kw-t1 { background: var(--ppl-tint); }
.chip.kw-t0 { background: var(--ppl-tint-2); color: var(--ink-1); }
.chip b { font-weight: 600; }

/* ══════════ D1 · 回复速度 ══════════ */
/* 整块由一个大数领衔，下面接一把 0 → 九成 的共用尺子 */
/* 尺子占住大数与极值格之间的整段：余量匀到它上下两侧，不堆成一块死白 */
.rs-scale {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  margin-top: max(4px, 0.5cqh);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.rs-track {
  position: relative;
  display: block;
  height: 8px;
  border-radius: var(--r-bar);
  background: var(--surface-inset-2);
  overflow: hidden;
}
.rs-fill { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--qty), var(--time)); }
.rs-pin {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  border-radius: 1px;
  background: var(--time-ink);
  transform: translateX(-1px);
}
.rs-marks {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: max(4px, 0.35cqw);
  padding-top: 2px;
  min-width: 0;
}
.rs-marks > .dt { flex: none; }
.rs-mark-m { flex: 0 1 auto; min-width: 0; text-align: center; }
.rs-mark-m b { font-weight: 600; color: var(--ink-1); }
/* 极值格贴底，中间只留一条发丝线 */
.d1-ext {
  margin-top: auto;
  padding-top: max(4px, 0.5cqh);
  display: flex;
  flex-direction: column;
  gap: max(3px, 0.35cqh);
  flex: none;
  min-width: 0;
}
.d1-ex { display: flex; flex-direction: column; gap: 1px; border-radius: var(--r-inner); }
.d1-ex .who-row { min-width: 0; }
.d1-ext .dd { margin-left: auto; flex: none; }

/* ══════════ D2 · 谁先开口 ══════════ */
.split-bar {
  display: block;
  height: 8px;
  border-radius: var(--r-bar);
  flex: none;
  margin-top: max(5px, 0.6cqh);
  background: linear-gradient(90deg, var(--qty) 0 var(--p), var(--surface-inset-2) var(--p) 100%);
}
/* 两列头像：左边是你追出去的，右边是找上门的 */
.init-duo {
  margin-top: auto;
  padding-top: max(4px, 0.5cqh);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: max(3px, 0.3cqh) max(5px, 0.4cqw);
  flex: none;
  min-width: 0;
}
.init-duo--solo { grid-template-columns: minmax(0, 1fr); }
.init-col {
  display: flex;
  flex-direction: column;
  gap: max(2px, 0.28cqh);
  min-width: 0;
  border-radius: var(--r-inner);
}
.init-row .dd { margin-left: auto; flex: none; }

/* ══════════ D3 · 表情宇宙 ══════════ */
.d3-row {
  flex: none;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: max(6px, 0.5cqw);
  align-items: stretch;
}
/* 左列与右侧 2×2 等高并顶对齐：原来两边各自居中，「158 次」和网格行对不上 */
.d3-l { display: flex; flex-direction: column; align-items: center; gap: 2px; justify-content: center; }
.pic-frame {
  width: max(38px, 5.0cqh);
  height: max(38px, 5.0cqh);
  border-radius: var(--r-group);
  background: var(--surface-inset);
  display: grid;
  place-items: center;
  overflow: hidden;
}
.pic-img { width: 100%; height: 100%; object-fit: contain; display: block; }
.pic-void { width: 40%; height: 40%; border-radius: var(--r-inner); background: var(--surface-inset-2); display: block; }
/* 2×2：读数不再排成一条长竖列，图也能跟着放大 */
.d3-m {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: max(2px, 0.25cqh) max(4px, 0.32cqw);
  align-content: center;
  min-width: 0;
}
.d3-m .mcell {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 0.4em;
  justify-content: flex-start;
  border-radius: var(--r-inner);
}
.d3-m .dt { flex: none; }
/* 缩略图行：吃掉块里剩下的高度，五格均分整行 —— 否则底下空一截很怪 */
.thumbs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  /* 给一个确定高度而不是 flex-grow：拉伸 + aspect-ratio 会互相推算出比容器更高的方盒 */
  flex: none;
  height: max(28px, 4.6cqh);
  /* 容器高度确定后才能 stretch：align-items:center 时行高按内容算，
     子元素的 height:100% 变成循环引用，会退回图片的固有尺寸把行撑破。 */
  align-items: stretch;
  grid-auto-rows: 100%;
  gap: max(4px, 0.4cqw);
  margin-top: max(3px, 0.35cqh);
  min-width: 0;
  min-height: 0;
}
.thumb-pair {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  height: 100%;
}
/* 每格约 61px：图占方形，剩下的必须留够「×141」四个字符，否则次数会被吃掉 */
.thumb-pair .dt {
  white-space: nowrap;
  flex: none;
  font-size: max(9px, 1.02cqh);
  letter-spacing: -0.01em;
}
/* 图随行高长大：宽度跟着高度走（而不是反过来），否则 aspect-ratio 会算出比格子更高的盒子 */
.thumb {
  height: 100%;
  width: auto;
  aspect-ratio: 1;
  flex: none;
  max-width: 56%;
  border-radius: var(--r-inner);
  background: var(--surface-inset);
  overflow: hidden;
  display: grid;
  place-items: center;
  flex: none;
}
.thumb img { width: 100%; height: 100%; object-fit: contain; display: block; }
.d3-foot { margin-top: auto; padding-top: max(2px, 0.25cqh); flex: none; min-width: 0; }
.d3-foot .foot-note { margin-top: 0; padding-top: 0; }
.d3-tail {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: max(5px, 0.4cqw);
  min-width: 0;
  padding-top: 1px;
}
.d3-tail .dt { min-width: 0; }
.emo-pair { display: flex; align-items: baseline; gap: max(6px, 0.5cqw); flex: none; }
.emo-row { display: flex; align-items: baseline; gap: 3px; flex: none; }
.emo { font-size: max(13px, 1.75cqh); line-height: 1.1; }
.emo--img {
  width: max(13px, 1.75cqh);
  height: max(13px, 1.75cqh);
  object-fit: contain;
  display: block;
  align-self: center;
}

/* ══════════ D4 · 年度聊天排行 ══════════ */
/* 图例同时是本块的读数位：两种文案高度一致，
   align-self:center 让它退出 head-line 的基线组 —— 否则「色块 + 字」与「纯字」
   两种状态基线不同，行高会跳一两像素。 */
.rank-legend {
  display: flex;
  align-items: center;
  gap: 3px;
  flex: 0 1 auto;
  min-width: 0;
  align-self: center;
  min-height: calc(var(--fs-label) * 1.3);
}
.rank-legend .lg { margin-right: 4px; }
.rank-legend .lg-read { margin-right: 0; max-width: 100%; }
.rank-legend b { font-weight: 600; color: var(--ink-0); }
.lgc--out { background: var(--qty); }
.lgc--in { background: var(--time-soft); }
.rank-list {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: max(4px, 0.5cqh);
}
/* 悬停反馈：整行铺一层底色。只改 background，不加 padding/margin ——
   往外撑会让 .rank-list 的 scrollWidth 超出 clientWidth，被裁切检测当成溢出。 */
.rank-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  border-radius: var(--r-inner);
  transition: background 0.12s var(--ease-out);
}
.rank-item:hover { background: var(--surface-inset); }
.rk {
  flex: none;
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--ppl-ink);
  line-height: 1;
  width: 1em;
  text-align: center;
}
.rk-total { margin-left: auto; }
.duo-bar--thin { height: 4px; margin-top: 0; width: var(--w, 100%); }

/* ══════════ E1 · 人物带 ══════════ */
.b-people { flex-direction: row; align-items: center; gap: max(9px, 0.7cqw); min-height: max(36px, 4.8cqh); }
.ppl-kicker { margin-bottom: 0; flex: none; }
.ppl-row {
  flex: 1 1 auto;
  min-width: 0;
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  justify-content: space-between;
  gap: max(6px, 0.6cqw);
}
.ppl-row.is-sparse { justify-content: space-around; }
.ppl-chip { display: flex; align-items: center; gap: max(5px, 0.4cqw); min-width: 0; }

/* ══════════ 页脚 · 年度地平线 ══════════ */
.b-foot { flex-direction: row; align-items: center; gap: max(6px, 0.5cqw); }
.foot-end { display: flex; align-items: center; gap: 5px; flex: none; min-width: 0; }
.foot-end--r { justify-content: flex-end; }
.foot-end .dt { white-space: nowrap; }
.foot-mid { display: flex; align-items: center; gap: 6px; flex: none; }
.foot-line { flex: 1 1 auto; height: 1px; background: var(--surface-hairline); display: block; min-width: 0; }
.dot { width: 5px; height: 5px; border-radius: var(--r-pill); display: block; flex: none; }
.dot--qty { background: var(--qty); }
.dot--time { background: var(--time); }

/* ══════════ 玻璃工坊层：点缀 / 批注 / 微动 ══════════
   2026-07-28 定版：大面积 SVG 水印装饰做过两版（细线雕纹 → 实体浮雕），
   都被用户点名「太廉价」后整层摘除——**别再往块里放任何 SVG 水印**。
   留下来的点缀只有实体小构件与光效：键帽 / 金冠 / 奖牌 / 箔章 / 托盘槽 /
   月亮流星 / 扫光 / 活版年份，外加材质与指针光效本身。 */
.deco {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  border-radius: inherit;
}

/* A2 年历上缓慢扫过的一道光：背景位移，不用 transform */
.yr-shine {
  position: absolute;
  inset: 0;
  display: block;
  background-image: linear-gradient(
    105deg,
    transparent 42%,
    rgba(7, 193, 96, 0.07) 50%,
    rgba(255, 233, 163, 0.05) 56%,
    transparent 64%
  );
  background-size: 300% 100%;
  background-repeat: no-repeat;
  background-position: 140% 0;
  animation: yr-sweep 9s ease-in-out infinite;
  animation-delay: 2s;
}
@keyframes yr-sweep {
  0% { background-position: 140% 0; }
  46%, 100% { background-position: -40% 0; }
}
/* 幽灵年份：活版压进纸里（letterpress），不再是描边线稿 */
.ghost-year {
  color: rgba(34, 51, 43, 0.12);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.85), 0 -1px 0 rgba(11, 61, 38, 0.07);
  opacity: 1;
}

/* B2 桂冠行：琥珀微光呼吸 + 14px 小金冠
   champ 不许 overflow:hidden —— 王冠悬在头像上方 8px，会被裁 */
.champ::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(80% 140% at 10% 50%, rgba(242, 170, 0, 0.13), transparent 62%);
  animation: champ-breathe 5s ease-in-out infinite;
  pointer-events: none;
}
@keyframes champ-breathe {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}
.champ-avw { position: relative; flex: none; display: grid; place-items: center; }
.crown {
  position: absolute;
  top: max(-8px, -1cqh);
  left: -7px;
  width: max(13px, 1.7cqh);
  height: auto;
  transform: rotate(-24deg);
  filter: drop-shadow(0 1px 1px rgba(150, 89, 10, 0.35));
  z-index: 1;
}

/* C2 键帽：常按的三个键印成能按下去的小键帽 */
.big-tail--keys { display: inline-flex; align-items: center; gap: 3px; }
.keycap {
  display: inline-grid;
  place-items: center;
  min-width: max(14px, 1.9cqh);
  height: max(14px, 1.9cqh);
  padding: 0 3px;
  border-radius: 3px;
  background: linear-gradient(180deg, #ffffff, #f0f4f1);
  border: 1px solid rgba(31, 66, 50, 0.16);
  box-shadow: 0 1.5px 0 rgba(31, 66, 50, 0.2), inset 0 1px 0 #ffffff;
  font-family: var(--sans);
  /* 9px 是全版小字硬底线，键帽也不例外 */
  font-size: max(9px, 1.05cqh);
  font-weight: 600;
  color: var(--ink-1);
  line-height: 1;
  transition: transform 0.12s var(--ease-out), box-shadow 0.12s var(--ease-out);
}
.keycap:hover {
  transform: translateY(1.5px);
  box-shadow: 0 0 0 rgba(31, 66, 50, 0.2), inset 0 1px 0 #ffffff;
}

/* D4 榜首奖牌：13px 金箔小圆章，其余名次保持素字 */
.rank-item:first-child .rk {
  width: max(13px, 1.7cqh);
  height: max(13px, 1.7cqh);
  border-radius: 999px;
  background: radial-gradient(120% 120% at 30% 22%, #ffe9a3 0%, #f2aa00 48%, #c88a06 100%);
  color: #ffffff;
  display: grid;
  place-items: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    inset 0 -1px 1px rgba(150, 89, 10, 0.5),
    0 1px 2px rgba(150, 89, 10, 0.3);
  font-size: max(9px, 1.05cqh);
  line-height: 1;
  text-shadow: 0 0.5px 0 rgba(150, 89, 10, 0.6);
}

/* E1 压凹小托盘：每个人躺在一格压进玻璃的浅槽里（实体构造，替换掉被否的细线） */
.ppl-chip {
  padding: 2px 7px;
  border-radius: var(--r-inner);
  background: rgba(11, 61, 38, 0.035);
  box-shadow:
    inset 0 1px 1.5px rgba(11, 61, 38, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.75);
}

/* ── 批注与耳语：衬线小字，琥珀墨 ── */
.whisper {
  font-family: var(--serif);
  color: var(--ink-2);
  opacity: 0.9;
  margin-left: 0.55em;
  font-size: 0.95em;
}
.whisper-r { font-family: var(--serif); font-weight: 500; letter-spacing: 0.02em; }
.serif-note {
  font-family: var(--serif);
  color: var(--ppl-ink);
  opacity: 0.6;
  letter-spacing: 0.04em;
}

/* ── 悬停微动：头像轻轻凑近，表情歪头，词条抬一下 ── */
.mo-av, .ppl-chip .av, .init-row .av, .rank-item .av, .thumb, .chip {
  transition: transform 0.2s var(--spring);
}
.mo:hover .mo-av { transform: scale(1.12); }
.ppl-chip:hover .av { transform: scale(1.1); }
.init-row:hover .av,
.rank-item:hover .av { transform: scale(1.08); }
.thumb-pair:hover .thumb { transform: rotate(-6deg) scale(1.08); }
.chip:hover { transform: translateY(-1px); }

/* ── 页脚：地平线两端染上晨昏，人格章压成箔印 ── */
.b-foot .foot-line:first-of-type {
  background: linear-gradient(90deg, rgba(7, 193, 96, 0.45), rgba(31, 66, 50, 0.06));
}
.b-foot .foot-line:last-of-type {
  background: linear-gradient(90deg, rgba(31, 66, 50, 0.06), rgba(91, 111, 184, 0.5));
}
.foot-mid .tag--qty {
  background: linear-gradient(160deg, #0cd26e 0%, #07b85b 55%, #05934a 100%);
  color: #ffffff;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    inset 0 -1px 1px rgba(4, 90, 46, 0.5),
    0 1px 3px rgba(7, 113, 62, 0.3);
  text-shadow: 0 0.5px 0 rgba(4, 90, 46, 0.45);
  letter-spacing: 0.1em;
}

/* ══════════ 等待 / 错误屏 ══════════ */
.wrap-final--wait { position: relative; }
/* 骨架层：铺满、走同一套网格；文案浮在正中 */
.sheet-skeleton { position: absolute; inset: 0; }
.sk {
  /* 比成品更淡：是「还没印上去」的位置，不是内容 */
  background: rgba(11, 61, 38, 0.035);
  border-color: rgba(31, 66, 50, 0.07);
  overflow: hidden;
  opacity: 0;
  animation: sk-in 0.5s var(--ease-out) forwards;
  animation-delay: calc(var(--sk-i, 0) * 45ms);
}
/* 一道极缓的扫光从左到右走过整版，像正在被逐块点亮 */
/* 扫光用 background-position 推，不用 transform：
   位移的伪元素即使被 overflow:hidden 裁掉，仍会把父级 scrollWidth 撑大。 */
.sk::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: linear-gradient(
    100deg,
    transparent 32%,
    rgba(7, 193, 96, 0.10) 48%,
    rgba(242, 170, 0, 0.07) 57%,
    transparent 73%
  );
  background-size: 240% 100%;
  background-repeat: no-repeat;
  background-position: 130% 0;
  animation: sk-sweep 2.6s ease-in-out infinite;
  animation-delay: calc(var(--sk-i, 0) * 45ms);
}
@keyframes sk-in {
  from { opacity: 0; transform: scale(0.985); }
  to { opacity: 1; transform: none; }
}
@keyframes sk-sweep {
  0% { background-position: 130% 0; }
  55%, 100% { background-position: -30% 0; }
}
.wait-box {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
  /* 压一层纸底，保证文字压在骨架上仍读得清 */
  background: rgba(250, 253, 251, 0.92);
  border: 1px solid var(--stroke-card);
  border-radius: var(--r-card);
  padding: max(14px, 1.8cqh) max(20px, 1.8cqw);
}
.wait-box { display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; }
@keyframes haloBreath {
  0%, 100% { opacity: 0.5; transform: scale(0.94); }
  50% { opacity: 1; transform: scale(1.04); }
}
.wait-line { font-size: max(15px, 1.9cqh); font-weight: 600; color: var(--ink-0); }
.wait-sub { font-size: max(12px, 1.4cqh); color: var(--ink-2); max-width: 30em; line-height: var(--lh-body); }
.wait-retry {
  margin-top: 6px;
  border-radius: var(--r-pill);
  background: var(--qty);
  color: #fff;
  font-size: max(12px, 1.4cqh);
  font-weight: 500;
  padding: 7px 18px;
  border: none;
  cursor: pointer;
  transition: background 0.2s var(--ease-out);
}
.wait-retry:hover { background: var(--qty-deep); }

/* ══════════ 响应式：容器查询（根已 container-type: size） ══════════ */

/* 矮窗只收「间距」，不藏内容：
   字号靠上面的 max(px, cqh) 自己缩，藏内容是这一页最不能做的事。 */
@container stage (max-height: 800px) {
  .sheet-final {
    --gap: max(4px, 0.62cqh);
    --pad-card: max(5px, 0.7cqh) max(8px, 0.62cqw);
    --pad-inner: max(3px, 0.38cqh) max(6px, 0.42cqw);
  }
}

@container stage (max-height: 700px) {
  .sheet-final {
    --gap: 4px;
    --pad-card: 4px max(7px, 0.55cqw);
    --pad-inner: 2px 5px;
  }
  .sheet-final { padding: 9px max(14px, 1.1cqw) 7px; }
}

/* 980 宽 —— 桌面窗口被拖窄的兜底态，明确放弃「一屏」承诺 */
@container stage (max-width: 1080px) {
  .sheet-final {
    grid-template-columns: repeat(8, minmax(0, 1fr));
    grid-template-rows: repeat(7, minmax(150px, auto)) minmax(0, auto) auto;
    height: auto;
    min-height: 100%;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .b-a1 { grid-area: 1 / 1 / 2 / 5; }
  .b-a2 { grid-area: 1 / 5 / 2 / 9; }
  .b-a3 { grid-area: 2 / 1 / 3 / 5; }
  .b-b1 { grid-area: 2 / 5 / 3 / 9; }
  .b-b2 { grid-area: 3 / 1 / 4 / 9; }
  .b-b3 { grid-area: 4 / 1 / 5 / 5; }
  .b-c3 { grid-area: 4 / 5 / 5 / 9; }
  .b-c1 { grid-area: 5 / 1 / 6 / 5; }
  .b-c2 { grid-area: 5 / 5 / 6 / 9; }
  .b-d1 { grid-area: 6 / 1 / 7 / 5; }
  .b-d2 { grid-area: 6 / 5 / 7 / 9; }
  .b-rank { grid-area: 7 / 1 / 8 / 5; }
  .b-d3 { grid-area: 7 / 5 / 8 / 9; }
  .b-people { grid-area: 8 / 1 / 9 / 9; }
  .b-foot { grid-area: 9 / 1 / 10 / 9; }
  /* 窄栏里一行塞不下四个读数，退回两列 */
  .b-c1 .rhythm-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* 820 宽 —— 纵向单列 */
@container stage (max-width: 880px) {
  .sheet-final {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    grid-template-rows: auto;
    grid-auto-rows: minmax(140px, auto);
  }
  .sheet-final > * { grid-area: auto / 1 / auto / 5 !important; }
  .b-a2 .yr-grid { grid-template-columns: repeat(27, minmax(0, 1fr)); grid-template-rows: repeat(14, minmax(0, 1fr)); }
  .ppl-row { grid-auto-flow: row; grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (prefers-reduced-motion: reduce) {
  .star { animation: none; }
  .sk { animation: none; opacity: 1; }
  .sk::after { animation: none; opacity: 0; }
  .wrap-final * { animation: none !important; transition: none !important; }
  /* `*` 选不到伪元素：呼吸 / 反光这几只单独点名 */
  .champ::after,
  .blk:not(.sk)::before,
  .blk:not(.sk)::after { animation: none !important; transition: none !important; }
  .blk { transform: none; }
  /* 悬停反馈只留描边，去掉格子的缩放 */
  .yr-cell[data-d]:hover,
  .hh-cell:hover { transform: none; }
}
</style>
