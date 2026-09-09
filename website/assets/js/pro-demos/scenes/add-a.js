/* ════════════════════════════════════════════════════════════
   scenes / add-a.js — 消息补录 A（文字 / 图片 / 文件 / 语音 / 视频 / 表情 / 转账记录 / 红包记录 / 位置）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   本组属于「本地写入」：只改自己电脑上的解密副本，单向、不回写微信，对方永远看不到。
   所以九个场景共用同一个私人语境——一气之下清空了和 TA 的聊天记录，事后想找回：
   能从备份恢复的恢复，恢复不了的按截图、相册、账单一条条补回本地副本。
   会话名用私人称谓（小满 / 家人群 / 老同学 / 室友），情境与结果只讲「我这边的存档」，
   不许出现「对方收到」「TA 就知道了」这类外部效果；一律 kit.scenario(text, { local: true })。
   这是「我」在整理自己的档案，人在操作是合理的：保留光标，不用 kit.workflow。

   两条铺上下文的死规矩（不守就会被读成「对方也收到了」）：
   · 缺口后面绝不留对方的确认（「收到了」「我这就过去」）——补进去的这条只在本地，谁也没看见；
     要么把缺口放在末尾，要么让缺口后那句出自「我」。
   · 至少留一条左侧（小满）气泡在 ref 之前：补录抽屉会盖住右半屏，全是右侧行的话抽屉一开画面就空了。

   手法不变，先让观众看见缺口：
   ① 情境条点明缺了什么；② 聊天里铺一段接不上的上下文（我问了没有回答、道了谢却没有红包）；
   ③ 缺口那一行是琥珀插槽线 +「⊕ 补录」+ 一行「缺 1 条」小注，补完插槽整条收起；
   ④ 结尾 strip.result() 给存档结果（时间线补齐 / 照片归位 / 这段记忆完整了），与印章同一拍。

   九个场景同一张脸（kit.insertFlow）：
   缺口插槽 → 点药丸 → 抽屉滑入（类型芯片命中）→ 预览区弹出内容 → beat（每种类型一个小动作）
   → 保存 → 抽屉收起 → 新行落进聊天（tag 补录）→ 印章 + 存档结果。
   build(previewMode) 会被调两次（预览一次、真插入一次），每次都返回全新节点。
   ════════════════════════════════════════════════════════════ */

const NBSP = " ";
const WHO = "小满";                    // 关系亲近的人，不必点明关系
const RAIL = ["家人群", "老同学", "室友"];
const TEXT_LINE = "到家了，记得吃饭";
const RP_LINE = "生日快乐";
const FILE_NAME = "毕业照原图.zip";
const LOC_NAME = "城南书店";
const LOC_ADDR = "文昌街 12 号";

/* 数字类滚表的格式器 */
const fmtMB = (v) => `${v.toFixed(1)} MB`;
const fmtKB = (v) => `${v.toFixed(1)} KB`;
const fmtSec = (v) => `${Math.round(v)}″`;
const fmtYuan = (v) => `¥${v.toFixed(2)}`;

/* 一个只在预览区用的竖排容器：卡片 + 一行 mono 小注 */
const stack = (kit, ...children) => { const w = kit.h("div", "pd-adda-stack"); w.append(...children); return w; };

/* ───────────────────────── 九个场景：情境 + 缺口上下文 + build/beat ───────────────────────── */

const TYPES = {
  /* 文字 · 清空后按截图补：我问了、我也接着往下说，中间 TA 那句没了 */
  "add-text": {
    type: "文字", side: "l", en: "INSERT · TEXT", fields: [["内容", ""]],
    when: "3 月 12 日 22:11",
    scene: "清空后按截图补 · 缺 TA 那句",
    hole: "缺 1 条",
    result: "时间线补齐",
    rows(kit, chat) {
      chat.time("3 月 12 日 22:08");
      chat.row("l", "刚上车，路上有点堵", { av: "小" });   // 左侧留一条：抽屉盖住右半屏时画面仍有上下文
      const ref = chat.row("r", "到家跟我说一声");
      chat.row("r", "那早点睡，明天见");
      return ref;
    },
    build(kit, pv, side) {
      const b = kit.bubble(pv ? "" : TEXT_LINE, side);
      if (pv) b.classList.add("pd-adda-empty");
      return b;
    },
    beat({ gsap, kit, content, comp }) {
      const field = comp.form.rows[2];
      const t = gsap.timeline();
      t.call(() => field.classList.add("is-edit"))
        .add(kit.type(field.value, TEXT_LINE, { cps: 12 }), 0.08)
        .add(kit.type(content, TEXT_LINE, { cps: 12, caret: false }), "<")
        .to({}, { duration: 0.2 });
      return t;
    },
  },

  /* 图片 · 照片还在相册：那张晚霞还躺在相册里，记录里那一条没了 */
  "add-image": {
    type: "图片", side: "l", en: "INSERT · IMAGE",
    when: "5 月 2 日 18:21",
    scene: "照片还在相册 · 记录里没了",
    hole: "缺 1 张图",
    result: "照片归位",
    rows(kit, chat) {
      chat.time("5 月 2 日 18:20");
      const ref = chat.row("l", "今天的晚霞", { av: "小" });
      chat.row("r", "好看，我存下来了");
      return ref;
    },
    build(kit, pv) {
      const card = kit.card.image();
      if (!pv) return card;
      const ic = card.querySelector(".pd-ic");
      const shine = kit.h("i", "pd-adda-shine");
      card.appendChild(shine);
      kit.gsap.set(ic, { opacity: 0.12, scale: 0.7 });
      kit.gsap.set(shine, { xPercent: -110 });
      const meta = kit.h("i", "pd-adda-meta mono");
      meta.append(kit.h("span", "", "IMG_0502.jpg · "), kit.h("b", "", "0.0 MB"));
      kit.gsap.set(meta, { opacity: 0 });
      return stack(kit, card, meta);
    },
    beat({ gsap, kit, content }) {
      const ic = content.querySelector(".pd-card .pd-ic");
      const shine = content.querySelector(".pd-adda-shine");
      const meta = content.querySelector(".pd-adda-meta");
      const size = meta.querySelector("b");
      const t = gsap.timeline();
      t.to(shine, { xPercent: 110, duration: 0.5, ease: "power1.inOut" })
        .to(ic, { opacity: 1, scale: 1, duration: 0.4, ease: "back.out(2.2)" }, ">-0.15")
        .to(meta, { opacity: 1, duration: 0.2 }, "<")
        .add(kit.count(size, 1.2, { duration: 0.5, fmt: fmtMB }), "<");
      return t;
    },
  },

  /* 文件 · 文件还在电脑：TA 传来的毕业照压缩包还在我硬盘上，收到它的那一刻没了 */
  "add-file": {
    type: "文件", side: "l", en: "INSERT · FILE",
    when: "6 月 20 日 21:12",
    scene: "文件还在电脑 · 记录缺一条",
    hole: "缺 1 个文件",
    result: "文件回到时间线",
    rows(kit, chat) {
      chat.time("6 月 20 日 21:10");
      const ref = chat.row("l", "毕业照原图我打包好了", { av: "小" });
      chat.row("r", "收到了，我存起来");            // 缺口后只留「我」这边的话，不让对方替本地写入背书
      return ref;
    },
    build(kit, pv) {
      const c = kit.card.file({ name: FILE_NAME, size: "486.2 KB" });
      if (pv) { const [b, i] = c.querySelectorAll(".pd-card__txt > *"); b.textContent = NBSP; i.textContent = NBSP; }
      return c;
    },
    beat({ gsap, kit, content }) {
      const [name, size] = content.querySelectorAll(".pd-card__txt > *");
      const fic = content.querySelector(".pd-card__fic");
      const t = gsap.timeline();
      t.add(kit.scramble(name, FILE_NAME, { duration: 0.6 }))
        .add(kit.count(size, 486.2, { duration: 0.45, fmt: fmtKB }), ">-0.2")
        .fromTo(fic, { scale: 0.85 }, { scale: 1, duration: 0.35, ease: "back.out(3)", immediateRender: false }, "<");
      return t;
    },
  },

  /* 语音 · 语音导出过：那条唱歌的语音早导出成文件了，位置还空着 */
  "add-voice": {
    type: "语音", side: "l", en: "INSERT · VOICE",
    when: "12 月 31 日 23:41",          // 字段里给可解析的时刻，「跨年夜」留给时间分割线
    scene: "语音导出过 · 待归位",
    hole: "缺 1 条语音",
    result: "语音归位",
    rows(kit, chat) {
      chat.time("跨年夜 23:40");
      chat.row("l", "刚练完这段", { av: "小" });   // 左侧留一条：抽屉盖住右半屏时画面仍有上下文
      const ref = chat.row("r", "唱两句我听听");
      chat.row("r", "好听，再来一遍");
      return ref;
    },
    build(kit, pv, side) { return kit.card.voice({ sec: pv ? 0 : 12, side }); },
    beat({ gsap, kit, content }) {
      const sec = content.querySelector("span");
      const t = gsap.timeline();
      t.add(kit.count(sec, 12, { duration: 0.9, fmt: fmtSec }))
        .fromTo(sec, { scale: 1 }, { scale: 1.18, duration: 0.14, yoyo: true, repeat: 1, ease: "power1.inOut", immediateRender: false }, ">-0.1");
      return t;
    },
  },

  /* 视频 · 视频还在：TA 拍猫那段视频还存在本地，记录丢了 */
  "add-video": {
    type: "视频", side: "l", en: "INSERT · VIDEO",
    when: "4 月 8 日 20:15",
    scene: "视频还在 · 记录丢了",
    hole: "缺 1 段视频",
    result: "视频归位",
    rows(kit, chat) {
      chat.time("4 月 8 日 20:14");
      chat.row("l", "你猜我回家看到什么", { av: "小" });
      const ref = chat.row("r", "猫又拆家了？");
      chat.row("r", "笑死，它还挺得意");          // 缺口后只留「我」的反应
      return ref;
    },
    build(kit, pv) {
      const c = kit.card.video({ dur: "0:48" });
      if (pv) {
        c.querySelector(".pd-card__dur").textContent = "0:00";
        kit.gsap.set(c.querySelector(".pd-card__play"), { scale: 0.4, opacity: 0 });
      }
      return c;
    },
    beat({ gsap, kit, content }) {
      const play = content.querySelector(".pd-card__play");
      const dur = content.querySelector(".pd-card__dur");
      const t = gsap.timeline();
      t.to(play, { scale: 1, opacity: 0.9, duration: 0.45, ease: "back.out(2.4)" })
        .add(kit.scramble(dur, "0:48", { duration: 0.6, chars: "0123456789" }), "<+0.1");
      return t;
    },
  },

  /* 表情 · 语气不对：只剩一句「行吧」，跟着的那个笑脸没了，读起来像生气 */
  "add-emoji": {
    type: "表情", side: "l", en: "INSERT · EMOJI",
    when: "3 月 20 日 09:33",
    scene: "少了表情 · 语气不对",
    hole: "缺 1 个表情",
    result: "语气还原",
    rows(kit, chat) {
      chat.time("3 月 20 日 09:32");
      chat.row("r", "那我周末去找你");
      const ref = chat.row("l", "行吧", { av: "小" });
      return ref;
    },
    build(kit, pv) {
      const card = kit.card.emoji();
      if (!pv) return card;
      kit.gsap.set(card, { scale: 0.5, rotate: -16, opacity: 0.4 });
      return stack(kit, card);
    },
    beat({ gsap, kit, content }) {
      const card = content.querySelector(".pd-card");
      const t = gsap.timeline();
      t.to(card, { scale: 1, rotate: 0, opacity: 1, duration: 0.55, ease: "back.out(2.8)" })
        .add(kit.flash(card, { color: "amber", duration: 0.6 }), ">-0.3")
        .to(card.querySelector(".pd-ic"), { rotate: 12, duration: 0.12, yoyo: true, repeat: 3, ease: "power1.inOut" }, "<");
      return t;
    },
  },

  /* 转账记录 · 账单查得到：那趟旅行的机票钱账单上有，记录里少这一笔 */
  "add-transfer": {
    type: "转账", side: "r", en: "INSERT · TRANSFER", fields: [["状态", "已完成"]],   // 只描述本地这条记录，不写「已收款」
    when: "2 月 14 日 21:02",
    scene: "账单里查得到 · 记录里没了",
    hole: "缺 1 笔 ¥520",
    result: "这笔对上了",
    rows(kit, chat) {
      chat.time("2 月 14 日 21:00");
      chat.row("l", "票我先垫上了", { av: "小" });
      const ref = chat.row("r", "机票钱转你了");   // 缺口落在末尾，后面不留对方的收讫回话
      return ref;
    },
    build(kit, pv) { return kit.card.transfer({ amount: pv ? "¥0.00" : "¥520.00", note: "机票钱" }); },
    beat({ gsap, kit, content }) {
      const amount = content.querySelector(".pd-card__main b");
      const t = gsap.timeline();
      t.add(kit.count(amount, 520, { duration: 0.9, fmt: fmtYuan }))
        .fromTo(amount, { scale: 1 }, { scale: 1.08, duration: 0.14, yoyo: true, repeat: 1, ease: "power1.inOut", immediateRender: false, transformOrigin: "0 50%" }, ">-0.1");
      return t;
    },
  },

  /* 红包记录 · 那年的生日红包：零点那个红包不在记录里，我道的谢就接不上了 */
  "add-redpacket": {
    type: "红包", side: "l", en: "INSERT · REDPACKET",
    when: "10 月 9 日 00:01",           // 字段里给可解析的时刻，「去年」留给时间分割线
    scene: "那年的生日红包 · 记录缺了",
    hole: "缺 1 个红包",
    result: "红包补回来了",
    rows(kit, chat) {
      chat.time("去年 10 月 9 日 00:00");
      const ref = chat.row("l", "零点了，接住", { av: "小" });
      chat.row("r", "收到啦，谢谢你");
      return ref;
    },
    build(kit, pv) {
      const c = kit.card.redpacket({ text: pv ? NBSP : RP_LINE });
      if (pv) c.classList.add("pd-adda-rp");
      return c;
    },
    beat({ gsap, kit, content }) {
      const b = content.querySelector(".pd-card__main b");
      const t = gsap.timeline();
      t.add(kit.type(b, RP_LINE, { cps: 12 }), 0.05)
        .to({}, { duration: 0.15 });
      return t;
    },
  },

  /* 位置 · 第一次见面的地方：约在哪儿的那条位置没了，这段就缺了一块 */
  "add-location": {
    type: "位置", side: "r", en: "INSERT · LOCATION",
    when: "11 月 3 日 15:23",
    scene: "第一次见面的地方 · 位置缺了",
    hole: "缺 1 条位置",
    result: "这段记忆完整了",
    rows(kit, chat) {
      chat.time("11 月 3 日 15:22");
      chat.row("l", "在哪儿见？", { av: "小" });
      const ref = chat.row("r", "我发你定位");    // 缺口落在末尾，后面不留对方「我这就过去」
      return ref;
    },
    build(kit, pv) {
      const c = kit.card.location({ name: LOC_NAME, addr: LOC_ADDR });
      if (!pv) return c;
      const map = c.querySelector(".pd-card__map");
      const pin = map.querySelector(".pd-ic");
      const ring = kit.h("i", "pd-adda-ring");
      map.appendChild(ring);
      kit.gsap.set(pin, { y: -16, opacity: 0 });
      kit.gsap.set(ring, { scale: 0.2, opacity: 0 });
      c.querySelector(".pd-card__txt i").textContent = NBSP;
      return c;
    },
    beat({ gsap, kit, content }) {
      const pin = content.querySelector(".pd-card__map .pd-ic");
      const ring = content.querySelector(".pd-adda-ring");
      const addr = content.querySelector(".pd-card__txt i");
      const t = gsap.timeline();
      t.to(pin, { y: 0, opacity: 1, duration: 0.5, ease: "back.out(2.4)" })
        .fromTo(ring, { scale: 0.2, opacity: 0.9 }, { scale: 1, opacity: 0, duration: 0.55, ease: "power2.out", immediateRender: false }, ">-0.15")
        .add(kit.scramble(addr, LOC_ADDR, { duration: 0.5 }), "<-0.2");
      return t;
    },
  },
};

/* ───────────────────────── 工厂：同一张脸 ───────────────────────── */

const FLOW_START = 0.15;   // 补录整段在 tl 上的起点：让情境条先滑入半拍
const RESULT_LEAD = 1.8;   // 存档结果提前于整段结束的秒数：印章前半拍就亮出来，别只在最后一瞬出现

function make(key) {
  const spec = TYPES[key];
  return ({ gsap, kit, tl }) => {
    const chat = kit.chat({ title: WHO, railNames: RAIL });
    const strip = kit.scenario(spec.scene, { local: true });
    const after = spec.rows(kit, chat);         // 铺一段接不上的上下文，返回缺口前的那一行

    const flow = kit.insertFlow(chat, {
      after,
      side: spec.side,
      type: spec.type,
      fields: spec.fields || [],
      build: (pv) => spec.build(kit, pv, spec.side),
      beat: (ctx) => spec.beat({ gsap, kit, ...ctx }),
      stamp: "已写入",
      en: spec.en,
    });

    // 缺口标注：把「缺 1 条」写在插槽线下面，补完随插槽一起收起
    flow.gap.classList.add("pd-add-hole");
    flow.gap.appendChild(kit.h("i", "pd-add-void", spec.hole));
    // 抽屉里的发送方 / 时间跟着场景走；补录进来的那一行头像也得是同一个人
    flow.comp.form.rows[0].value.textContent = spec.side === "l" ? WHO : "我";
    flow.comp.form.rows[1].value.textContent = spec.when;
    if (spec.side === "l" && flow.row) flow.row.av.textContent = WHO[0];

    tl.add(strip.in(), 0.1)
      .add(flow, FLOW_START)
      .add(strip.result(spec.result), FLOW_START + flow.duration() - RESULT_LEAD);
    return tl;
  };
}

export default Object.fromEntries(Object.keys(TYPES).map((k) => [k, make(k)]));

// 本组专属的局部样式；统一注入一次
export const css = `
.pd-adda-stack { display: flex; flex-direction: column; align-items: center; gap: 7px; max-width: 100%; }
.pd-adda-meta { font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.12em; color: var(--pd-dim); white-space: nowrap; }
.pd-adda-meta b { color: var(--pd-amber); font-weight: 500; }
.pd-adda-shine { position: absolute; inset: 0; pointer-events: none; background: linear-gradient(100deg, transparent 28%, rgba(233, 241, 235, 0.18) 50%, transparent 72%); }
.pd-adda-empty { min-width: 46px; min-height: 32px; }
.pd-adda-ring { position: absolute; left: 50%; top: calc(50% + 8px); width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%; border: 1.5px solid var(--pd-red); pointer-events: none; }
.pd-adda-rp .pd-card__main b.is-typing::after { content: ""; display: inline-block; width: 1px; height: 12px; margin-left: 2px; vertical-align: -1px; background: #fff; animation: pdBlink 0.9s steps(2) infinite; }
/* 缺口插槽：比默认插槽高一点，线下面写清「这里缺了什么」，补完整条收起 */
.pd-add-hole { height: 20px; flex: none; }
.pd-add-void {
  position: absolute; left: 50%; top: 8px; transform: translateX(-50%);
  font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.12em; line-height: 1;
  color: rgba(255, 194, 75, 0.66); white-space: nowrap;
}
`;
