/* ════════════════════════════════════════════════════════════
   scenes / add-b.js — 消息补录 B（链接卡片 / 小程序卡片 / 视频号卡片 / 引用消息 / 合并聊天记录 / 通话记录 / 系统消息 / 拍一拍记录）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入」印章并停留。

   八个场景同一张脸（kit.insertFlow）：
   种子对话 → 光标到某行下方，琥珀插槽线 + 「⊕ 补录」药丸 → 点药丸 → 右侧补录抽屉（类型芯片高亮）
   → 预览区里内容弹出 + 每个类型自己的 beat → 保存 → 抽屉收起 → 新行落进聊天（tag 补录）→ 印章「已写入」。

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

/* 公共编排：种子对话 → insertFlow 挂到 tl → 把 flow 交回去，让场景在尾巴上追加自己的收尾动作 */
function stage({ kit, tl }, { title = "老地方", seed = 3, at, side, type, fields = [], build, beat, en, setup }) {
  const chat = kit.chat({ title });
  const rows = chat.seed(seed);
  if (setup) setup(chat, rows);
  const after = rows[at ?? rows.length - 1];
  const flow = kit.insertFlow(chat, { after, side, type, fields, build, beat, en });
  // 落在左边的行是对方发的：抽屉里的「发送方」跟着改（与 add-a 对齐；addSys 自己再覆盖成「系统」）
  if (side === "l") flow.comp.form.rows[0].value.textContent = "友";
  // 值为空 / 被清空再打字的字段也保持一行高（12px 字 × 1.5 行高），mono 行也对齐，行高不跳
  flow.comp.form.rows.forEach((r) => { r.value.style.minHeight = "18px"; });
  tl.add(flow, 0);
  return { chat, rows, flow, land: landAt(flow) };
}

/* ── 链接卡片：标题一字字敲出来，摘要与缩略图跟着补齐 ── */
const LINK = { title: "这几年谢谢你，真的", desc: "一段被完整找回的对话" };
function addLink({ gsap, kit, tl }) {
  stage({ kit, tl }, {
    seed: 3, side: "r", type: "链接", en: "INSERT · LINK",
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

/* ── 小程序卡片：先亮出宿主应用名，大图区标题乱码落定 ──
   预览区只有 ~118px 高：不整卡缩放（字会小于 9px），只把大图区砍到 60px。 */
function addMiniapp({ gsap, kit, tl }) {
  const TITLE = "点单小程序";
  stage({ kit, tl }, {
    seed: 2, side: "l", type: "小程序", en: "INSERT · MINIAPP",
    build(pv) {
      const c = kit.card.miniapp({ title: TITLE, app: "咖啡屋" });
      const big = c.querySelector(".pd-card__big");
      big.style.height = pv ? "60px" : "84px";
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
        .add(kit.scramble(content.bt, TITLE, { duration: 0.6 }), ">-0.05")
        .to({}, { duration: 0.15 });
      return t;
    },
  });
  return tl;
}

/* ── 视频号卡片：播放三角弹出，名称乱码落定（预览里竖版封面压到 58px，不缩放） ── */
function addChannels({ gsap, kit, tl }) {
  const NAME = "城市漫游记";
  stage({ kit, tl }, {
    seed: 2, side: "r", type: "视频号", en: "INSERT · CHANNELS",
    build(pv) {
      const c = kit.card.channels({ name: NAME });
      c.querySelector(".pd-card__portrait").style.height = pv ? "58px" : "92px";
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

/* ── 引用消息：友的气泡带着「我」那句的引用块弹出来，正文随即打出；落进聊天时被引用的原消息也亮一下 ── */
function addQuote({ gsap, kit, tl }) {
  const QUOTE = "我：刚落地，还是老地方见", TEXT = "就这么定了";
  const { rows, land } = stage({ kit, tl }, {
    seed: 2, side: "l", type: "引用", en: "INSERT · QUOTE",
    fields: [["引用", QUOTE]],
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
  // 新行落下的同一刻，被引用的原消息「刚落地，还是老地方见」跟着亮：引用原文自动关联
  tl.add(kit.flash(rows[2].content, { color: "amber", duration: 0.7 }), land);
  return tl;
}

/* ── 合并聊天记录：三行记录逐行滑入，页脚条数（琥珀读数）跟着数 ── */
function addMerged({ gsap, kit, tl }) {
  const LINES = ["友：到了跟我说一声", "我：刚落地，还是老地方见", "友：好，就这么定了"];
  stage({ kit, tl }, {
    seed: 2, side: "r", type: "聊天记录", en: "INSERT · MERGED",
    build(pv) {
      const c = kit.card.merged({ title: "我和友的聊天记录", lines: LINES });
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

/* ── 通话记录：插在两句话中间；先在「时长」里敲 03:21，预览里的通话时长才从 00:00 滚上去，听筒跟着抖 ── */
function addCall({ gsap, kit, tl }) {
  const DUR = "03:21", SECS = 3 * 60 + 21;
  stage({ kit, tl }, {
    seed: 3, at: 1, side: "l", type: "通话", en: "INSERT · CALL",
    fields: [["时长", "00:00", true]],
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

/* ── 系统消息：居中灰字一字字敲出来，落在会话最前面 ── */
const SYS_TEXT = "你已添加了小王，现在可以开始聊天了";
function addSys({ gsap, kit, tl }) {
  const { flow } = stage({ kit, tl }, {
    title: "小王", seed: 3, at: 0, side: "sys", type: "系统", en: "INSERT · SYSTEM",
    setup(chat) { chat.sessions.forEach((s, i) => s.classList.toggle("is-active", i === 3)); },
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

/* ── 拍一拍记录：在「拍谁」里敲一个「友」，预览里的「」随即填上并左右抖；落进聊天再抖一次 ── */
function addPat({ gsap, kit, tl }) {
  const { flow, land } = stage({ kit, tl }, {
    seed: 3, side: "sys", type: "拍一拍", en: "INSERT · PAT",
    fields: [["拍谁", ""]],
    build(pv) {
      const p = kit.pat({ from: "我", to: pv ? "" : "友" });
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
        .add(kit.type(row.value, "友", { cps: 8 }), 0.45)
        .call(() => { content.who.textContent = "友"; }, [], 0.62)
        .add(kit.pop(content.who, { y: 4, from: 0.5, duration: 0.28 }), 0.62)
        .add(shake(gsap, content), 0.85);
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
`;
