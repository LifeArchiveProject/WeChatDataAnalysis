/* ════════════════════════════════════════════════════════════
   scenes / add-b.js — 消息补录 B（链接卡片 / 小程序卡片 / 视频号卡片 / 引用消息 / 合并聊天记录 / 通话记录 / 系统消息 / 拍一拍记录）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   世界观（本地存档类，八个场景共用一条故事线）：
   一气之下清空了和小满的聊天记录，事后想找回。能从备份恢复的恢复，恢复回来错乱的校订，
   恢复不了的就按截图、相册、账单一条条补回本地副本。全程只改自己电脑上的解密副本，
   **不回写微信，对方看不到**——所以每个场景都必须 kit.scenario(text, { local: true })，
   情境条会常驻一枚「本地副本 · 不回写微信」。这是「我」在整理自己的档案，人在操作是合理的，
   光标保留；但不要用 kit.workflow（那是真实动作类的演法）。

   文案边界：情境与结果只讲我这边的存档（「分享补回来了」「上下文接上」「那一天补回来了」），
   禁止出现「对方收到」「TA 就知道了」这类外部效果。会话名用私人称谓（小满 / 家人群 / 老同学 / 室友）。
   时长 4.5–7.5 秒，结尾用 kit.ok() 盖印章并停留 ≥0.9 秒。

   八个场景同一张脸（kit.insertFlow）：
   先演出缺口——那段对话还在，中间少了一块 → 光标到缺口那行下方，琥珀插槽线 + 「⊕ 补录」药丸
   → 点药丸 → 右侧补录抽屉（类型芯片高亮）→ 预览区里内容弹出 + 每个类型自己的 beat
   → 保存 → 抽屉收起 → 新行落进聊天（tag 补录）→ 印章 + 结果文案。

   注意：挂在 DOM 节点上的自定义句柄别撞 HTMLElement 原生属性名（title / name / id / hidden / dir / lang…），
   那些是字符串 setter，塞进去的元素会变成 "[object HTMLElement]"。
   ════════════════════════════════════════════════════════════ */

const pad2 = (n) => String(n).padStart(2, "0");
const mmss = (v) => { const s = Math.max(0, Math.round(v)); return `${pad2(Math.floor(s / 60))}:${pad2(s % 60)}`; };

/* 左右小抖：x ±amp 来回 n 次（拍一拍）。immediateRender:false——fromTo 挂在时间轴后段时默认仍会立刻渲染起始态，
   否则落地那行会先偏着 -amp 待到抖动开始 */
function shake(gsap, el, { n = 3, amp = 4, step = 0.06 } = {}) {
  const t = gsap.timeline();
  t.fromTo(el, { x: -amp }, { x: amp, duration: step, yoyo: true, repeat: n * 2 - 1, ease: "sine.inOut", immediateRender: false })
    .set(el, { x: 0 });
  return t;
}

/* 「新行落进聊天」在 flow 里的时刻：insertFlow 对 node 的入场 pop 是唯一一个目标是 node、有时长的直接子补间。
   从 flow 里找出来，而不是按 kit 内部节拍手算魔法数。 */
function landAt(flow) {
  const pop = flow.getChildren(false, true, false).find((t) => t.targets()[0] === flow.node && t.duration() > 0);
  return pop ? pop.startTime() : flow.duration() - 1.62;
}

const FLOW_AT = 0.25;   // 情境条先立住再动手：整段补录流程往后挪四分之一秒

/* 会话栏也换成私人语境：这是我自己的微信，不是工作号 */
const RAIL = ["家人群", "老同学", "室友"];

/* 公共编排：情境条 → 那段还在的对话 → insertFlow → 结果文案与印章同一拍；把 flow 交回去，让场景在尾巴上追加自己的收尾动作 */
function stage({ kit, tl }, { title = "小满", scene, result, from = "小满", av = "满", when, rows: mkRows, at, side, type, fields = [], build, beat, en }) {
  const chat = kit.chat({ title, railNames: RAIL });
  const strip = kit.scenario(scene, { local: true });
  const rows = mkRows(chat);
  const after = rows[at ?? rows.length - 1];
  const flow = kit.insertFlow(chat, { after, side, type, fields, build, beat, en });
  flow.comp.el.classList.add("pd-addb-sheet");   // 情境条占了顶端 22px，补录抽屉跟着下移，别压住情境
  // 落在左边的行是小满发的：抽屉里的「发送方」与新行头像都跟着改（addSys 自己再覆盖成「系统」）
  if (side === "l") {
    flow.comp.form.rows[0].value.textContent = from;
    if (flow.row) flow.row.av.textContent = av;
  }
  // 抽屉里的「时间」要落在这段对话那一天，别留 kit 的默认「昨天」，补的是哪一刻才说得清
  if (when) flow.comp.form.rows[1].value.textContent = when;
  // 值为空 / 被清空再打字的字段也保持一行高（12px 字 × 1.5 行高），mono 行也对齐，行高不跳
  flow.comp.form.rows.forEach((r) => { r.value.style.minHeight = "18px"; });
  tl.add(strip.in(), 0.05);
  tl.add(flow, FLOW_AT);
  const land = landAt(flow) + FLOW_AT;
  if (result) tl.add(strip.result(result), land + 0.4);   // 与 kit.ok() 印章同一拍
  return { chat, rows, flow, strip, land };
}

/* ── 链接卡片：当年分享的那篇文章，恢复回来时没了——标题一字字敲出来，摘要与缩略图跟着补齐 ── */
const LINK = { title: "你说过想去的那座城", desc: "存了两年的那篇游记" };
function addLink({ gsap, kit, tl }) {
  stage({ kit, tl }, {
    scene: "当年分享的那篇 · 记录里没了", result: "分享补回来了", when: "2 月 14 日 22:41",
    side: "r", type: "链接", en: "INSERT · LINK",
    rows: (chat) => [
      chat.time("2 月 14 日 22:40"),
      chat.row("l", "冬天说的那个地方叫什么来着", { av: "满" }),
      chat.row("r", "我给你发过一篇"),
    ],
    build(pv) {
      const c = kit.card.link(LINK);
      const ttl = c.querySelector(".pd-card__txt b");
      const desc = c.querySelector(".pd-card__txt i");
      const thumb = c.querySelector(".pd-card__thumb");
      if (!pv) return c;
      ttl.textContent = "";
      ttl.classList.add("pd-addb-caret");
      ttl.style.minHeight = "19px";
      gsap.set(desc, { opacity: 0 });
      gsap.set(thumb, { opacity: 0, scale: 0.6 });
      return Object.assign(c, { ttl, desc, thumb });
    },
    beat({ content }) {
      const t = gsap.timeline();
      t.add(kit.type(content.ttl, LINK.title, { cps: 16 }))
        .to(content.desc, { opacity: 1, duration: 0.25 }, ">+0.05")
        .to(content.thumb, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2)" }, "<")
        .to({}, { duration: 0.15 });
      return t;
    },
  });
  return tl;
}

/* ── 小程序卡片：那天一起下的那单，卡片缺了——先亮出宿主应用名，大图区标题乱码落定 ──
   预览区只有百来像素高：不整卡缩放（字会小于 9px），只把大图区砍矮。 */
function addMiniapp({ gsap, kit, tl }) {
  const ORDER = "生椰拿铁 × 2";
  stage({ kit, tl }, {
    scene: "一起下的那单 · 卡片缺了", result: "卡片补回原位", when: "3 月 8 日 19:26",
    at: 1, side: "l", type: "小程序", en: "INSERT · MINIAPP",
    rows: (chat) => [
      chat.time("3 月 8 日 19:26"),
      chat.row("l", "点好啦，还是老样子", { av: "满" }),
      chat.row("r", "好，我下楼等"),
    ],
    build(pv) {
      const c = kit.card.miniapp({ title: ORDER, app: "点单小程序" });
      const big = c.querySelector(".pd-card__big");
      big.style.height = pv ? "52px" : "76px";
      const bt = big.firstElementChild;
      const appEl = c.querySelector(".pd-card__apphead b");
      if (!pv) return c;
      bt.textContent = "";
      gsap.set(appEl, { opacity: 0, x: -6 });
      return Object.assign(c, { bt, appEl });
    },
    beat({ content }) {
      const t = gsap.timeline();
      t.to(content.appEl, { opacity: 1, x: 0, duration: 0.3, ease: "power2.out" })
        .add(kit.scramble(content.bt, ORDER, { duration: 0.6 }), ">-0.05")
        .to({}, { duration: 0.15 });
      return t;
    },
  });
  return tl;
}

/* ── 视频号卡片：TA 发过的那条视频号缺了——播放三角弹出，名称乱码落定（预览里竖版封面压矮，不缩放） ── */
function addChannels({ gsap, kit, tl }) {
  const NAME = "海边那天的日落";
  stage({ kit, tl }, {
    scene: "TA 发过的那条视频号 · 缺了", result: "卡片补回原位", when: "1 月 9 日 21:03",
    at: 1, side: "l", type: "视频号", en: "INSERT · CHANNELS",
    rows: (chat) => [
      chat.time("1 月 9 日 21:03"),
      chat.row("l", "这个你一定要看", { av: "满" }),
      chat.row("r", "看了，太好看了"),
    ],
    build(pv) {
      const c = kit.card.channels({ name: NAME });
      c.querySelector(".pd-card__portrait").style.height = pv ? "56px" : "92px";
      const play = c.querySelector(".pd-card__play");
      const nameEl = c.querySelector(".pd-card__txt b");
      if (!pv) return c;
      nameEl.textContent = "";
      nameEl.style.minHeight = "19px";
      gsap.set(play, { opacity: 0, scale: 0.3, transformOrigin: "50% 50%" });
      return Object.assign(c, { play, nameEl });
    },
    beat({ content }) {
      const t = gsap.timeline();
      t.fromTo(content.play, { opacity: 0, scale: 0.3, transformOrigin: "50% 50%" }, { opacity: 0.9, scale: 1, duration: 0.4, ease: "back.out(2.2)" })
        .add(kit.scramble(content.nameEl, NAME, { duration: 0.5 }), ">-0.15")
        .to({}, { duration: 0.15 });
      return t;
    },
  });
  return tl;
}

/* ── 引用消息：我那句还在，TA 引着它回的那句断了——补回带引用的回复，落地时被引用的原话跟着亮 ── */
function addQuote({ gsap, kit, tl }) {
  const ORIGIN = "周五我去接你";
  const QUOTE = `我：${ORIGIN}`, TEXT = "那我等你";
  const { rows, land } = stage({ kit, tl }, {
    scene: "上下文断了 · 缺引用那句", result: "上下文接上", when: "4 月 2 日 18:14",
    side: "l", type: "引用", en: "INSERT · QUOTE",
    fields: [["引用", QUOTE]],
    rows: (chat) => [
      chat.time("4 月 2 日 18:12"),
      chat.row("l", "周五几点下班", { av: "满" }),
      chat.row("r", ORIGIN),
    ],
    build(pv) {
      const w = kit.card.quote({ text: TEXT, quote: QUOTE, side: "l" });
      if (!pv) return w;
      // 引用块跟着整体一起弹出（先挂好关联），气泡从空到打字，不留空块时间
      w.bubble.textContent = "";
      w.bubble.classList.add("pd-addb-caret");
      w.bubble.style.minHeight = "32px";
      w.bubble.style.minWidth = "40px";
      return w;
    },
    beat({ content }) {
      const t = gsap.timeline();
      t.add(kit.type(content.bubble, TEXT, { cps: 14 }), 0.05)
        .to({}, { duration: 0.2 });
      return t;
    },
  });
  // 新行落下的同一刻，被引用的那条延期通知跟着亮：引用原文自动关联，前后文接上
  tl.add(kit.flash(rows[2].content, { color: "amber", duration: 0.7 }), land);
  return tl;
}

/* ── 合并聊天记录：那件事是在家人群里说定的，这边对话里没有——三行往来逐行滑入，页脚条数跟着数 ── */
function addMerged({ gsap, kit, tl }) {
  const LINES = ["妈妈：周末带小满回来吃饭吗", "我：我问问她", "妈妈：那我多买点菜"];
  stage({ kit, tl }, {
    scene: "另一段对话 · 想并进来", result: "记录合并完成", when: "5 月 6 日 20:16",
    side: "r", type: "聊天记录", en: "INSERT · MERGED",
    rows: (chat) => [
      chat.time("5 月 6 日 20:15"),
      chat.row("l", "周末回你家吃饭吗", { av: "满" }),
      chat.row("r", "我妈那边也说了这事"),
    ],
    build(pv) {
      const c = kit.card.merged({ title: "我和妈妈的聊天记录", lines: LINES });
      const lines = [...c.querySelectorAll(".pd-card__lines span")];
      const cnt = kit.h("i", "pd-addb-cnt", `· ${LINES.length} 条`);
      c.querySelector(".pd-card__foot").appendChild(cnt);
      if (!pv) return c;
      gsap.set(lines, { opacity: 0, x: -8 });
      cnt.textContent = "· 0 条";
      return Object.assign(c, { lines, cnt });
    },
    beat({ content }) {
      const t = gsap.timeline();
      t.to(content.lines, { opacity: 1, x: 0, duration: 0.3, stagger: 0.22, ease: "power2.out" }, 0)
        .add(kit.count(content.cnt, LINES.length, { duration: 0.74, fmt: (v) => `· ${Math.round(v)} 条` }), 0)
        .to({}, { duration: 0.15 });
      return t;
    },
  });
  return tl;
}

/* ── 通话记录：那晚说了三分多钟，记录里却没有这通——「时长」里敲 03:21，预览里的通话时长从 00:00 滚上去，听筒跟着抖 ── */
function addCall({ gsap, kit, tl }) {
  const DUR = "03:21", SECS = 3 * 60 + 21;
  stage({ kit, tl }, {
    scene: "那通 03:21 的电话 · 记录缺了", result: "通话补回来了", when: "3 月 21 日 23:44",
    at: 2, side: "l", type: "通话", en: "INSERT · CALL",
    fields: [["时长", "00:00", true]],
    rows: (chat) => [
      chat.time("3 月 21 日 23:40"),
      chat.row("l", "打给你说吧，打字说不清", { av: "满" }),
      chat.row("r", "好，我在"),
      chat.row("r", "挂了，早点睡"),
    ],
    build(pv) {
      const c = kit.card.call({ dur: pv ? "00:00" : DUR, video: false, side: "l" });
      return Object.assign(c, { ic: c.firstElementChild, txt: c.lastElementChild });
    },
    beat({ content, comp, cursor }) {
      const row = comp.form.rows[2];
      const t = gsap.timeline();
      t.add(cursor.to(row.value, { duration: 0.3, dx: -36 }), 0)
        .add(cursor.click(row.value, { press: false }), 0.3)
        .call(() => { row.classList.add("is-edit"); row.value.textContent = ""; }, [], 0.4)
        .add(kit.type(row.value, DUR, { cps: 12 }), 0.45)
        .add(kit.count(content.txt, SECS, { duration: 0.8, fmt: (v) => `通话时长 ${mmss(v)}` }), 0.7)
        .fromTo(content.ic, { rotate: 0, transformOrigin: "50% 50%" }, { rotate: 14, duration: 0.11, yoyo: true, repeat: 5, ease: "sine.inOut" }, 0.75)
        .set(content.ic, { rotate: 0 })
        .to({}, { duration: 0.1 }, 1.5);
      return t;
    },
  });
  return tl;
}

/* ── 系统消息：认识的那天在记录里查不到——居中灰字一字字敲出来，落在第一句话之前 ── */
const SYS_TEXT = "你已添加了小满，现在可以开始聊天了";
function addSys({ gsap, kit, tl }) {
  const { flow } = stage({ kit, tl }, {
    scene: "认识的那天 · 记录里查不到", result: "那一天补回来了", when: "2023 年 4 月 6 日",
    at: 0, side: "sys", type: "系统", en: "INSERT · SYSTEM",
    rows: (chat) => [
      chat.time("2023 年 4 月 6 日"),
      chat.row("l", "你好呀", { av: "满" }),
      chat.row("r", "你好，终于加上了"),
    ],
    build(pv) {
      const p = kit.h("p", "pd-sys", pv ? "" : SYS_TEXT);
      if (pv) { p.classList.add("pd-addb-caret"); p.style.minHeight = "17px"; }
      else p.classList.add("pd-addb-sysfit");   // 落地时的琥珀描边贴着文字，不横跨整行
      return p;
    },
    beat({ content }) {
      const t = gsap.timeline();
      t.add(kit.type(content, SYS_TEXT, { cps: 18 })).to({}, { duration: 0.15 });
      return t;
    },
  });
  flow.comp.form.rows[0].value.textContent = "系统";
  flow.gap.style.marginTop = "8px";   // 插槽线别紧贴时间标签
  return tl;
}

/* ── 拍一拍记录：那次拍一拍没落库，互动缺了一角——「拍谁」里敲「小满」，预览里的名字随即填上并左右抖；落进聊天再抖一次 ── */
function addPat({ gsap, kit, tl }) {
  const WHO = "小满";
  const { flow, land } = stage({ kit, tl }, {
    scene: "少了那次拍一拍", result: "互动还原", when: "6 月 1 日 08:13",
    side: "sys", type: "拍一拍", en: "INSERT · PAT",
    fields: [["拍谁", ""]],
    rows: (chat) => [
      chat.time("6 月 1 日 08:12"),
      chat.row("l", "起床啦", { av: "满" }),
      chat.row("r", "再睡五分钟"),
      chat.row("l", "不许", { av: "满" }),
    ],
    build(pv) {
      const p = kit.pat({ from: "我", to: pv ? "" : WHO });
      p.classList.add("pd-addb-pat");
      if (!pv) p.classList.add("pd-addb-sysfit");   // 同系统消息：描边与抖动都贴着文字
      return Object.assign(p, { who: p.querySelectorAll("b")[1] });
    },
    beat({ content, comp, cursor }) {
      const row = comp.form.rows[2];
      const t = gsap.timeline();
      t.add(cursor.to(row.value, { duration: 0.3, dx: -36 }), 0)
        .add(cursor.click(row.value, { press: false }), 0.3)
        .call(() => row.classList.add("is-edit"), [], 0.4)
        .add(kit.type(row.value, WHO, { cps: 8 }), 0.45)
        .call(() => { content.who.textContent = WHO; }, [], 0.72)
        .add(kit.pop(content.who, { y: 4, from: 0.5, duration: 0.28 }), 0.72)
        .add(shake(gsap, content), 0.95);
      return t;
    },
  });
  // 落进聊天后再抖一次（新行 pop 完、印章盖上之前）
  tl.add(shake(gsap, flow.node), land + 0.5);
  return tl;
}

export default {
  "add-link": addLink,
  "add-miniapp": addMiniapp,
  "add-channels": addChannels,
  "add-quote": addQuote,
  "add-merged": addMerged,
  "add-call": addCall,
  "add-sys": addSys,
  "add-pat": addPat,
};

// 本组专属的局部样式；引擎统一注入一次
export const css = `
.pd-addb-caret.is-typing::after {
  content: ""; display: inline-block; width: 1px; height: 0.95em; margin-left: 2px; vertical-align: -0.12em;
  background: var(--pd-amber); animation: pdBlink 0.9s steps(2) infinite;
}
.pd-addb-pat b { display: inline-block; min-width: 1em; text-align: center; }
.pd-addb-cnt { font-family: var(--pd-mono); font-size: 10px; letter-spacing: 0.08em; color: var(--pd-amber); }
/* 落地的系统行/拍一拍行：宽度贴文字（描边不横跨整行）并居中；选择器压过 .pd-root p { margin:0; padding:0 } */
.pd-root p.pd-addb-sysfit { width: fit-content; margin: 0 auto; align-self: center; padding: 0 8px; border-radius: 3px; }
/* 补录抽屉给顶端情境条让出 22px（.pd-sheet 是 top:0/bottom:0 的绝对定位） */
.pd-root .pd-addb-sheet { top: 22px; }
`;
