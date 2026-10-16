/* ════════════════════════════════════════════════════════════
   scenes / automation.js — 自动化任务（3 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   ⚠️ 官网的 gsap 是 UMD 全局、应用里是 npm import：场景里要用 gsap 只能从入参取，
      绝不能写 window.gsap 或裸 gsap 标识符。

   这三项都是**真实动作类**（经微信客户端发出去，对方看得到），所以：
   - 一律 kit.workflow([触发, …, 执行]) 立一条底轨，随剧情 flow.step(i) 逐步点亮；
   - 情境条不带 { local: true }；
   - 画面里**没有人**：不用 kit.cursor，不点按钮、不手打字。写进字段、发出去的文字
     一律 kit.scramble 落定；只有「AI 拟稿面板里那句还没发出去的草稿」才用打字机。

   这一组自己的一张脸（和群聊的浮层面板、联系人的通讯录都不一样）：
   **任务台** .pd-auto —— 左 218px 是一张常驻的「任务卡」（任务名 / 状态药丸 / 读数 /
   编号条目 + 自动打勾），右侧是任务作用的那个工作区（收件人队列 / 聊天窗 / 朋友圈）。
   任务卡从头到尾都在，进度、剩余、每一条的结果都写在上面——因为这一组卖的就是
   「任务在替你跑，而且你随时看得见它跑到哪」。
   颜色沿用全局令牌：琥珀 = 正在写入 / 正在发，霓虹 = 已落定，mono 读数走 JetBrains Mono。

   分寸（这三项最容易翻车的地方）：
   - 群发演的是「名单与话提前编好，到点按节奏一条条发」，不是「一键批量」；
   - 新好友接待的触发是「好友关系已经建立」，画面里不做任何「加好友」的动作；
   - 跟圈只碰命中规则的动态，屏幕上留一条明确「命中屏蔽词 · 不跟发」的动态作对照。
   ════════════════════════════════════════════════════════════ */

const pad2 = (n) => String(n).padStart(2, "0");
const hhmmss = (v) => { const s = Math.max(0, Math.round(v)); return `${pad2(Math.floor(s / 3600) % 24)}:${pad2(Math.floor(s / 60) % 60)}:${pad2(s % 60)}`; };
const mmss = (v) => { const s = Math.max(0, Math.round(v)); return `${pad2(Math.floor(s / 60))}:${pad2(s % 60)}`; };

/* ── 任务台：左任务卡 + 右工作区。自建布局根 → pd-pushed（让出顶端情境条与底端工作流轨）── */
function taskBoard(kit, { kicker = "TASK", title = "" } = {}) {
  const el = kit.h("div", "pd-auto pd-pushed");
  const aside = kit.h("aside", "pd-auto__aside");
  const head = kit.h("div", "pd-auto__head");
  head.append(kit.h("i", "pd-auto__k", kicker), kit.h("b", "pd-auto__title", title));
  aside.appendChild(head);
  const main = kit.h("div", "pd-auto__main");
  el.append(aside, main);
  kit.mount(el);
  return { aside, main };
}

/* ── 状态药丸：任务此刻处在哪一档（等待 → 执行中 n/N → 已完成）。
      它同时交代「计划、暂停、继续都在你手里」——任务是有档位的，不是一按到底 ── */
function statePill(kit, gsap, parent, text) {
  const el = kit.h("b", "pd-auto-state", text);
  parent.appendChild(el);
  return Object.assign(el, {
    // txt 给数组时按节点拼（「发送中 <n> / 36」：n 由 countTo 匀速滚动，与进度条同速同 ease）
    to(txt, tone = "run") {
      const t = gsap.timeline();
      t.call(() => {
        if (Array.isArray(txt)) { el.textContent = ""; el.append(...txt); } else el.textContent = txt;
        el.classList.remove("is-run", "is-done");
        if (tone) el.classList.add("is-" + tone);
      }).fromTo(el, { scale: 0.9, opacity: 0.45 }, { scale: 1, opacity: 1, duration: 0.26, ease: "back.out(2.4)", immediateRender: false });
      return t;
    },
  });
}

/* ── 大读数：时钟 / 倒计时，mono 琥珀 ── */
function readout(kit, parent, { label = "", value = "" } = {}) {
  const el = kit.h("div", "pd-auto-read");
  const v = kit.h("b", "pd-auto-read__v", value);
  el.append(kit.h("i", "pd-auto-read__l", label), v);
  parent.appendChild(el);
  return Object.assign(el, { value: v });
}

/* ── 一行说明：左 mono 标签，右取值 ── */
function metaRow(kit, parent, label, value) {
  const r = kit.h("div", "pd-auto-meta");
  const v = kit.h("b", "", value);
  r.append(kit.h("i", "", label), v);
  parent.appendChild(r);
  return Object.assign(r, { value: v });
}

/* ── 任务条目：[序号][名称][状态牌][✓] + 一行取值（可带 ON 开关小牌）。
      三个场景共用同一张条目脸：备注/标签/欢迎语、文字/图片、点赞/评论/跟发 ── */
function taskItem(kit, gsap, parent, { n, label, value = "", badge = null, sw = false, icon = null } = {}) {
  const el = kit.h("div", "pd-auto-item");
  const head = kit.h("div", "pd-auto-item__h");
  head.append(kit.h("i", "pd-auto-item__n", String(n)), kit.h("i", "pd-auto-item__l", label));
  const badgeEl = badge ? kit.h("b", "pd-auto-item__b", badge) : null;
  if (badgeEl) head.appendChild(badgeEl);
  const check = kit.h("i", "pd-auto-item__c");
  check.appendChild(kit.icon("check"));
  head.appendChild(check);
  const line = kit.h("div", "pd-auto-item__v");
  if (icon) line.appendChild(kit.icon(icon));
  const v = kit.h("b", "pd-auto-item__t", value);
  line.appendChild(v);
  if (sw) line.appendChild(kit.h("i", "pd-auto-sw", "ON"));
  el.append(head, line);
  parent.appendChild(el);
  gsap.set(check, { opacity: 0.28, scale: 1 });
  return Object.assign(el, { value: v, line, check, badge: badgeEl });
}

/* 条目进入「正在做」：左边竖线转琥珀 */
function itemRun(gsap, item, text) {
  const t = gsap.timeline();
  t.call(() => {
    item.classList.add("is-run");
    item.classList.remove("is-done");
    if (text && item.badge) { item.badge.textContent = text; item.badge.classList.add("is-run"); }
  }).fromTo(item, { x: -3 }, { x: 0, duration: 0.22, ease: "power2.out", immediateRender: false });
  return t;
}

/* 条目落定：竖线转霓虹 + ✓ 自己打上（没有人来点它） */
function itemDone(gsap, item, text) {
  const t = gsap.timeline();
  t.call(() => {
    item.classList.remove("is-run");
    item.classList.add("is-done");
    if (text && item.badge) { item.badge.textContent = text; item.badge.classList.remove("is-run"); item.badge.classList.add("is-done"); }
  }).fromTo(item.check, { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(3)", immediateRender: false }, 0);
  return t;
}

/* ── 进度：已发出 n / N + 一根霓虹条；bare 只留那根条（读数由状态药丸自己带）── */
function progress(kit, gsap, parent, { label = "已发出", total = 36, bare = false } = {}) {
  const el = kit.h("div", "pd-auto-prog");
  const num = kit.h("b", "", "0");
  if (!bare) {
    const top = kit.h("div", "pd-auto-prog__t");
    const txt = kit.h("span", "");
    txt.append(label + " ", num, ` / ${total}`);
    top.append(txt, kit.h("i", "pd-auto-prog__k", "TASK"));
    el.appendChild(top);
  }
  const bar = kit.h("i", "pd-auto-prog__bar");
  const fill = kit.h("b");
  bar.appendChild(fill);
  el.appendChild(bar);
  parent.appendChild(el);
  gsap.set(fill, { scaleX: 0 });
  return Object.assign(el, { num, fill, bar });
}

/* ── 一条 mono 注释：说明这台任务的边界（不是按钮，虚线框 + 灰字）── */
function ruleNote(kit, parent, text, iconName = "clock") {
  const el = kit.h("div", "pd-auto-note");
  el.append(kit.icon(iconName), kit.h("span", "", text));
  parent.appendChild(el);
  return el;
}

/* ── 小节标题 ── */
const sectionK = (kit, parent, text) => { const e = kit.h("i", "pd-auto-k", text); parent.appendChild(e); return e; };

/* ── 匀速数字滚表：kit.count 是 power2.out（前快后慢），和进度条对不上——
      任务类要的是「一条条按节奏发」，读数必须跟进度条同速，所以自己挂一条 tl.to ── */
function countTo(tl, kit, el, to, { at = 0, duration = 1.5, from = 0 } = {}) {
  const o = { v: from };
  tl.to(o, {
    v: to, duration: kit.reduced ? 0.01 : duration, ease: "power1.inOut",
    onUpdate: () => { el.textContent = String(Math.round(o.v)); },
  }, at);
}

/* ── 收件人队列（群发专用的右侧工作区）：一人一行，预览位落下这次发出去的内容 + 小勾 ── */
function queueList(kit, gsap, parent, { title = "", right = "", people = [], tail = "" } = {}) {
  const el = kit.h("div", "pd-auto-q");
  const head = kit.h("header", "pd-auto-q__h");
  head.append(kit.h("i", "", title), kit.h("i", "", right));
  const list = kit.h("div", "pd-auto-q__l");
  const rows = people.map(([name, av], i) => {
    const r = kit.h("div", "pd-auto-q__r");
    r.appendChild(kit.avatar(av, i % 2 ? "them" : "muted"));
    const t = kit.h("div", "pd-auto-q__t");
    const prev = kit.h("i", "", "—");
    t.append(kit.h("b", "", name), prev);
    const state = kit.h("b", "pd-auto-q__s", "排队中");
    const check = kit.h("i", "pd-auto-q__c");
    check.appendChild(kit.icon("check"));
    r.append(t, state, check);
    list.appendChild(r);
    gsap.set(check, { opacity: 0, scale: 0.3 });
    return Object.assign(r, { prev, state, check });
  });
  const tailEl = kit.h("p", "pd-auto-q__tail", tail);
  list.appendChild(tailEl);
  el.append(head, list);
  parent.appendChild(el);
  return { el, head, rows, tail: tailEl };
}

/* ═══════════════ automation-broadcast 定时群发任务 ═══════════════
   story：保单缴费日前七天要提醒一批人——下班前把名单和话编好，到点一条条发出去。
   flow：选定收件人 → 编排文字与图片 → 按计划逐条发出。
   演法：任务卡上的时钟自己走到 20:30，内容队列（一条文字 + 一张图）亮起，
   右侧收件人一个接一个落下这条消息并打勾，进度 0 → 36；
   状态药丸走「等待 20:30 → 发送中 12 / 36 → 已完成 36 / 36」，
   卡底一条 mono 注释说明任务由你启动、可暂停可继续。 */
function broadcast({ gsap, kit, tl, reduced }) {
  const TEXT = "保单 9 月 20 日缴费到期";
  const PREV = "[图片] " + TEXT;
  const { aside, main } = taskBoard(kit, { kicker: "TASK · 定时群发", title: "保单缴费提醒" });

  const pill = statePill(kit, gsap, aside, "等待 20:30");
  // 药丸里那个会滚的数字：由 countTo 匀速滚动，与进度条同时长、同 ease，读数和条走得一样快
  const pillNum = kit.h("b", "pd-auto-state__n", "0");
  const prog = progress(kit, gsap, aside, { bare: true });
  const clock = readout(kit, aside, { label: "发送时间 · 今天", value: "20:29:52" });
  metaRow(kit, aside, "发送节奏", "每条间隔 8 秒");
  sectionK(kit, aside, "内容队列 · QUEUE");
  const qText = taskItem(kit, gsap, aside, { n: 1, label: "文字", value: TEXT, badge: "已编排" });
  const qImg = taskItem(kit, gsap, aside, { n: 2, label: "图片", value: "缴费指引.png", badge: "已编排", icon: "image" });
  ruleNote(kit, aside, "任务由你启动 · 可暂停 / 可继续");

  const queue = queueList(kit, gsap, main, {
    title: "收件人队列 · 36 人", right: "PLAN 20:30",
    people: [["王女士", "王"], ["李先生", "李"], ["陈女士", "陈"], ["刘先生", "刘"]],
    tail: "…其余 32 位按节奏排队中",
  });

  const strip = kit.scenario("缴费日前 7 天 · 36 位要提醒");
  const flow = kit.workflow([
    { label: "任务到点 20:30", icon: "clock" },
    { label: "选定收件人 36", icon: "users" },
    { label: "编排文字与图片", icon: "image" },
    { label: "按计划逐条发出", icon: "send" },
  ]);

  // 一位收件人：状态牌翻面 → 预览位落下这次发出去的内容 → 打勾
  const send = (row, at) => {
    tl.call(() => { row.state.textContent = "发送中"; row.state.classList.add("is-run"); row.classList.add("is-run"); }, [], at)
      .add(kit.scramble(row.prev, PREV, { duration: 0.4 }), at + 0.04)
      .call(() => {
        row.state.textContent = "已发出";
        row.state.classList.remove("is-run");
        row.state.classList.add("is-done");
        row.classList.remove("is-run");
        row.classList.add("is-done");
      }, [], at + 0.44)
      .fromTo(row.check, { scale: 0.3, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.28, ease: "back.out(3)", immediateRender: false }, at + 0.44)
      .add(kit.flash(row, { color: "neon", duration: 0.5 }), at + 0.44);
  };

  const clk = { v: 20 * 3600 + 29 * 60 + 52 };
  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：时钟自己走到 20:30，没有人守在这儿按 */
    .add(flow.step(0), 0.5)
    .to(clk, {
      v: 20 * 3600 + 30 * 60, duration: reduced ? 0.01 : 1.0, ease: "none",
      onUpdate: () => { clock.value.textContent = hhmmss(clk.v); },
    }, 0.5)
    .add(kit.flash(clock, { color: "amber", duration: 0.6 }), 1.5)
    .add(strip.say("20:30 到点 · 任务自动开始"), 1.55)
    /* ② 下班前选好的名单就位 */
    .add(flow.step(1), 1.65)
    .add(kit.flash(queue.head, { color: "amber", duration: 0.6 }), 1.7);
  queue.rows.forEach((r, i) => tl.add(kit.flash(r, { color: "amber", duration: 0.5 }), 1.72 + i * 0.09));
  tl
    /* ③ 下班前编好的两条内容被取出来：一条文字 + 一张图 */
    .add(flow.step(2), 2.25)
    .add(itemRun(gsap, qText, "发送中"), 2.3)
    .add(kit.flash(qText, { color: "amber", duration: 0.5 }), 2.32)
    .add(itemRun(gsap, qImg, "发送中"), 2.5)
    .add(kit.flash(qImg, { color: "amber", duration: 0.5 }), 2.52)
    /* ④ 按节奏一条条发出去：每个会话落一条、打一个勾，进度一路跑到 36 */
    .add(flow.step(3), 2.8)
    .to(prog.fill, { scaleX: 1, duration: 1.6, ease: "power1.inOut" }, 2.85)
    .add(pill.to(["发送中 ", pillNum, " / 36"], "run"), 2.86);
  countTo(tl, kit, pillNum, 36, { at: 2.88, duration: 1.6 });
  send(queue.rows[0], 2.85);
  send(queue.rows[1], 3.2);
  send(queue.rows[2], 3.55);
  send(queue.rows[3], 3.9);
  tl.add(itemDone(gsap, qText, "已送出"), 4.3)
    .add(itemDone(gsap, qImg, "已送出"), 4.4)
    .add(pill.to("已完成 36 / 36", "done"), 4.5)
    /* 结尾整体提前：走片第 5 帧就要读得到印章与结果 */
    .add(flow.done(), 4.6)
    .add(kit.ok("已逐条发出", { en: "BROADCAST SENT", hold: 1.4 }), 4.7)
    .add(strip.result("36 条已逐条发出"), 4.7);
  return tl;
}

/* ═══════════════ automation-onboarding 新好友自动处理 ═══════════════
   story：家长在门店台卡前扫码、手指刚点下添加的那二十秒，是他唯一一次等着你说话。
   flow：好友关系建立 → 写入备注与标签 → 发出欢迎语。
   演法：聊天窗先落一条系统行（关系已经建立，画面里不做任何「加好友」动作），
   任务卡上二十秒倒数一直在走，三件事逐行自己打勾：备注落定、两枚标签叠上、
   欢迎语落进聊天并挂「自动欢迎语」。
   与 contact-remark 的区别：那边只改一个备注，这边是三件一次做完，还赶在二十秒里。 */
function onboarding({ gsap, kit, tl, reduced }) {
  const NICK = "妈妈爱宝贝";
  const REMARK = "地推-张妈妈-小四";
  const HELLO = "张妈妈您好，我是小四老师，试听课时间稍后发您";
  const { aside, main } = taskBoard(kit, { kicker: "TASK · 新好友接待", title: "门店台卡 · 接待" });

  const pill = statePill(kit, gsap, aside, "等待新好友");
  const cd = readout(kit, aside, { label: "他等着你说话", value: "00:20" });
  cd.classList.add("pd-auto-read--cd");

  const iRemark = taskItem(kit, gsap, aside, { n: 1, label: "备注", value: "—", badge: "待写入" });
  const iLabel = taskItem(kit, gsap, aside, { n: 2, label: "标签", value: "", badge: "待写入" });
  const chips = kit.h("div", "pd-auto-chips");
  const chipEls = ["渠道-地推-9月场", "待邀约试听"].map((w) => { const c = kit.h("i", "pd-auto-chip", w); chips.appendChild(c); return c; });
  iLabel.line.replaceChildren(chips);
  gsap.set(chipEls, { opacity: 0, scale: 0.6 });
  const iHello = taskItem(kit, gsap, aside, { n: 3, label: "欢迎语", value: "按配置 · 1 条", badge: "待发出" });
  ruleNote(kit, aside, "只接待开启后新建立的好友", "bolt");

  const chat = kit.chat({ title: NICK, rail: false, parent: main, cls: "pd-auto-chat" });
  // 没有人坐在这儿打字：把「发送」键换成一条执行状态，输入条上不留任何可点的东西
  const run = kit.h("b", "pd-auto-run", "自动接待 · 无人工");
  chat.send.replaceWith(run);
  const sys = chat.sys(`你已添加了${NICK}，现在可以开始聊天了`);
  const bub = kit.bubble("", "r");
  const row = chat.row("r", bub);
  row.body.appendChild(kit.tag("自动欢迎语"));
  gsap.set([sys, row], { display: "none" });

  const strip = kit.scenario("门店台卡扫码 · 好友关系刚建立");
  const flow = kit.workflow([
    { label: "好友关系建立", icon: "user" },
    { label: "写入备注与标签", icon: "edit" },
    { label: "发出欢迎语", icon: "send" },
  ]);

  const clk = { v: 20 };
  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：关系已经建立（系统行落地），二十秒的接待窗口开始倒数 */
    .add(flow.step(0), 0.4)
    .set(sys, { display: "block" }, 0.4)
    .add(kit.pop(sys), 0.4)
    .add(kit.flash(sys, { color: "amber", duration: 0.6 }), 0.45)
    .add(pill.to("接待中 · 3 件", "run"), 0.6)
    .to(clk, {
      v: 4, duration: reduced ? 0.01 : 3.6, ease: "none",
      onUpdate: () => { cd.value.textContent = mmss(clk.v); },
    }, 0.6)
    .add(strip.say("这二十秒他唯一一次等着你"), 1.0)
    /* ② 备注与标签一次写完：备注落定，聊天窗标题跟着改，两枚标签叠上去 */
    .add(flow.step(1), 1.4)
    .add(itemRun(gsap, iRemark, "写入中"), 1.45)
    .add(kit.scramble(iRemark.value, REMARK, { duration: 0.7 }), 1.5)
    .call(() => chat.title.classList.add("pd-auto-hit"), [], 1.9)
    .add(kit.scramble(chat.title, REMARK, { duration: 0.5 }), 1.9)
    .add(itemDone(gsap, iRemark, "已写入"), 2.3)
    .add(itemRun(gsap, iLabel, "写入中"), 2.4)
    .fromTo(chipEls[0], { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.6)", immediateRender: false }, 2.5)
    .fromTo(chipEls[1], { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.6)", immediateRender: false }, 2.7)
    .add(itemDone(gsap, iLabel, "已叠 2 枚"), 2.95)
    /* ③ 第一句话自己发出去：气泡落进聊天，挂「自动欢迎语」 */
    .add(flow.step(2), 3.1)
    .add(itemRun(gsap, iHello, "发送中"), 3.15)
    .set(row, { display: "flex" }, 3.25)
    .add(kit.pop(row), 3.25)
    .add(kit.scramble(bub, HELLO, { duration: 0.7 }), 3.3)
    .add(kit.flash(bub, { color: "neon", duration: 0.7 }), 4.0)
    .add(itemDone(gsap, iHello, "已发出"), 4.05)
    .add(pill.to("已接待 · 3 / 3", "done"), 4.2)
    /* 印章压在输入条上：先把它压暗，收尾画面里不留半露的执行状态条 */
    .to(chat.input, { opacity: 0.26, duration: 0.3 }, 4.25)
    .add(flow.done(), 4.35)
    .add(kit.ok("已接待", { en: "ONBOARDED", hold: 1.4 }), 4.45)
    .add(strip.result("二十秒内接上话"), 4.45);
  return tl;
}

/* ── 朋友圈跟圈任务 ──
      跟圈 = 别人发一条，我这边按规则跟着发一条同样的内容；顺带把该点的赞、该留的评论做掉。
      三项动作分别开关：点赞（按来源名单）、评论（按关键词）、跟发（按来源 + 屏蔽词）。
      屏蔽词是这一项的要害：命中「抽奖 / 转发 / 砍价」的动态，一个字都不跟发。 ── */
function momentsFollow({ gsap, kit, tl }) {
  const SAY = "恭喜到货，随时招呼我";
  const MATERIAL = "9 月新品到店，前 50 位到店有礼。";
  const { aside, main } = taskBoard(kit, { kicker: "TASK · 跟圈维护", title: "今天的跟圈" });

  const pill = statePill(kit, gsap, aside, "14 条新动态待跟");
  const prog = progress(kit, gsap, aside, { label: "已跟", total: 14 });

  const iLike = taskItem(kit, gsap, aside, { n: 1, label: "点赞", value: "来源 = 客户名单", badge: "待执行", sw: true });
  const iCmt = taskItem(kit, gsap, aside, { n: 2, label: "评论", value: "关键词 开业 / 到货", badge: "待执行", sw: true });
  // 评论的草稿行：按规则拟好再发，所以这里（也只有这里）允许打字机
  const draft = kit.h("div", "pd-auto-draft");
  const dTxt = kit.h("span", "pd-auto-draft__t", "");
  draft.append(kit.h("i", "pd-auto-draft__k", "AI"), dTxt, kit.h("i", "pd-caret"));
  iCmt.appendChild(draft);
  gsap.set(draft, { display: "none", opacity: 0 });
  const iRepost = taskItem(kit, gsap, aside, { n: 3, label: "跟发", value: "来源 = 品牌素材 · 原样发一条", badge: "待执行", sw: true });
  // 屏蔽词挂在跟发规则底下：跟圈最怕跟错，先说清哪些一律不发
  const block = kit.h("div", "pd-auto-block");
  const blockHit = kit.h("b", "pd-auto-block__n", "");
  block.append(kit.h("i", "pd-auto-block__k", "屏蔽词"), kit.h("span", "", "抽奖 / 转发 / 砍价"), blockHit);
  iRepost.appendChild(block);
  ruleNote(kit, aside, "三项分别开关 · 命中屏蔽词的一条都不发", "bolt");

  const feed = kit.feed({ parent: main, cls: "pd-auto-feed" });
  const mk = ({ name, av, text, imgs, time, tone }) => {
    const p = feed.post({ name, text, imgs, time });
    p.av.textContent = av;
    if (tone) p.av.className = `pd-av pd-av--${tone}`;
    // 时间挪到名字后面、收掉整条 meta：四条动态才塞得下一屏
    const nameEl = p.querySelector(".pd-post__name");
    p.time.classList.add("pd-auto-when");
    nameEl.appendChild(p.time);
    gsap.set(p.meta, { display: "none" });
    return Object.assign(p, { nameEl });
  };
  const pGoods = mk({ name: "客户 · 李姐", av: "李", text: "这批货已经到店了。", imgs: 0, time: "20 分钟前" });
  const pBrand = mk({ name: "星辰总部 · 品牌素材", av: "星", text: MATERIAL, imgs: 2, time: "1 小时前" });
  const pAd = mk({ name: "同城优惠速递", av: "同", text: "转发本条抽奖，人人有份。", imgs: 0, time: "1 小时前" });
  // 跟发出去的那一条：我自己的动态，内容与品牌素材一模一样，就压在原动态下面
  const pMine = mk({ name: "我", av: "我", text: MATERIAL, imgs: 2, time: "刚刚", tone: "me" });
  feed.list.insertBefore(pMine, pAd);
  pMine.classList.add("pd-auto-mine");
  gsap.set(pMine, { display: "none" });
  pMine.nameEl.appendChild(kit.tag("跟发 · 与品牌素材同样内容"));

  const hitTag = (post, text, cls) => { const t = kit.tag(text, cls); post.nameEl.appendChild(t); gsap.set(t, { opacity: 0, scale: 0.6 }); return t; };
  const tGoods = hitTag(pGoods, "命中 · 到货");
  const tBrand = hitTag(pBrand, "命中 · 品牌素材");
  const tSkip = hitTag(pAd, "命中屏蔽词 抽奖 · 不跟发", "pd-auto-tag--off");

  // 李姐这条：先点赞（心形包一层好做弹跳，点赞名里落「我」），再评论
  const heart = pGoods.likeRow.firstElementChild;
  const hw = kit.h("i", "pd-auto-heart");
  pGoods.likeRow.insertBefore(hw, heart);
  hw.appendChild(heart);
  pGoods.likeRow.appendChild(kit.tag("按规则点赞"));
  const line = kit.h("p", "");
  line.append(kit.h("b", "", "我"), "：" + SAY);
  line.appendChild(kit.tag("AI 自动"));
  pGoods.cmtBox.appendChild(line);
  gsap.set(line, { display: "none" });

  const strip = kit.scenario("品牌素材要原样跟发 · 客户动态要接住");
  const flow = kit.workflow([
    { label: "按关键词筛动态", icon: "bolt" },
    { label: "点赞 / 评论", ai: true },
    { label: "跟发同样内容", icon: "send" },
  ]);

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 三条规则各自亮一下，屏蔽词也在这一拍立住 */
    .add(flow.step(0), 0.55)
    .add(kit.flash(iLike, { color: "amber", duration: 0.5 }), 0.6)
    .add(kit.flash(iCmt, { color: "amber", duration: 0.5 }), 0.76)
    .add(kit.flash(iRepost, { color: "amber", duration: 0.5 }), 0.92)
    .add(kit.flash(block, { color: "red", duration: 0.6 }), 1.08)
    /* ② 命中判定：客户动态与品牌素材命中，抽奖那条命中屏蔽词，明确不跟发 */
    .fromTo(tGoods, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.6)", immediateRender: false }, 1.5)
    .add(kit.flash(pGoods.text, { color: "amber", duration: 0.5 }), 1.5)
    .fromTo(tBrand, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.6)", immediateRender: false }, 1.72)
    .add(kit.flash(pBrand.text, { color: "amber", duration: 0.5 }), 1.72)
    .fromTo(tSkip, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "power2.out", immediateRender: false }, 1.98)
    .to(pAd, { opacity: 0.4, duration: 0.35 }, 2.02)
    .add(kit.scramble(blockHit, "已跳过 2 条", { duration: 0.4 }), 2.05)
    /* ③ 三项动作各走各的：点赞 → 评论（先拟稿再发） → 跟发同样内容 */
    .add(flow.step(1), 2.35)
    .to(prog.fill, { scaleX: 1, duration: 2.2, ease: "power1.inOut" }, 2.4)
    .add(itemRun(gsap, iLike, "执行中"), 2.4)
    .set(pGoods.social, { display: "flex" }, 2.5)
    .set(pGoods.likeRow, { display: "flex" }, 2.5)
    .add(kit.pop(pGoods.social), 2.5)
    .call(() => pGoods.likeRow.classList.add("is-on"), [], 2.6)
    .fromTo(hw, { scale: 0.2 }, { scale: 1, duration: 0.55, ease: "back.out(4)", immediateRender: false }, 2.6)
    .add(kit.scramble(pGoods.likeNames, "我", { duration: 0.4 }), 2.7)
    .add(itemDone(gsap, iLike, "已点赞 1"), 2.95)
    /* 评论：先在卡上按规则拟好那句话（唯一允许打字机的地方），再落到动态下面 */
    .add(itemRun(gsap, iCmt, "拟稿中"), 3.0)
    .set(draft, { display: "flex" }, 3.05)
    .to(draft, { opacity: 1, duration: 0.25 }, 3.05)
    .add(kit.type(dTxt, SAY, { cps: 22 }), 3.15)
    .set(line, { display: "block" }, 3.7)
    .add(kit.pop(line), 3.7)
    .add(kit.flash(pGoods.social, { color: "neon", duration: 0.6 }), 3.72)
    .add(itemDone(gsap, iCmt, "已评论 1"), 3.9)
    /* 跟发：我这边自己发一条，内容与品牌素材一模一样，就落在原动态下面 */
    .add(itemRun(gsap, iRepost, "跟发中"), 4.0)
    .set(pMine, { display: "flex" }, 4.15)
    .add(kit.pop(pMine), 4.15)
    .add(kit.flash(pMine.text, { color: "neon", duration: 0.7 }), 4.2)
    .add(itemDone(gsap, iRepost, "已跟发 3"), 4.5)
    .add(pill.to("今天的跟圈已跟完", "done"), 4.6)
    .add(flow.done(), 4.75)
    .add(kit.ok("已按规则跟完", { en: "FOLLOWED", hold: 1.4 }), 4.85)
    .add(strip.result("跟发 3 条 · 屏蔽词那 2 条没发"), 4.85);
  // 读数与进度条同速：跟到最后一项（跟发）落定那一刻才满 14
  countTo(tl, kit, prog.num, 14, { at: 2.4, duration: 2.2 });
  return tl;
}

export default {
  "automation-broadcast": broadcast,
  "automation-onboarding": onboarding,
  "automation-moments-follow": momentsFollow,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* ── 任务台：左 218px 任务卡 + 右工作区（自建布局根，必须 position:absolute; inset:0）── */
.pd-auto { position: absolute; inset: 0; display: grid; grid-template-columns: 218px minmax(0, 1fr); }
.pd-auto__aside {
  border-right: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.015);
  padding: 10px 10px 11px; display: flex; flex-direction: column; gap: 8px; min-width: 0; overflow: hidden;
}
.pd-auto__main { position: relative; min-width: 0; min-height: 0; overflow: hidden; }
.pd-auto__head { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.pd-auto__k { font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.2em; color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-auto__title { font-size: 13px; font-weight: 600; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-auto-k { font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.2em; color: var(--pd-faint); margin-top: 1px; white-space: nowrap; }

/* 状态药丸：任务此刻在哪一档（等待 → 执行中 → 已完成） */
.pd-auto-state {
  align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; max-width: 100%;
  padding: 3px 10px 2px; border-radius: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-family: var(--pd-mono); font-size: 9.5px; font-weight: 500; letter-spacing: 0.1em;
  border: 1px solid var(--pd-line-strong); color: var(--pd-dim); background: rgba(255, 255, 255, 0.04);
}
.pd-auto-state::before { content: ""; flex: none; width: 5px; height: 5px; border-radius: 50%; background: var(--pd-faint); }
.pd-auto-state.is-run { border-color: rgba(255, 194, 75, 0.55); color: var(--pd-amber); background: rgba(255, 194, 75, 0.1); }
.pd-auto-state.is-run::before { background: var(--pd-amber); box-shadow: 0 0 8px rgba(255, 194, 75, 0.8); }
.pd-auto-state.is-done { border-color: rgba(61, 242, 141, 0.5); color: var(--pd-neon); background: rgba(61, 242, 141, 0.1); }
.pd-auto-state.is-done::before { background: var(--pd-neon); box-shadow: 0 0 8px rgba(61, 242, 141, 0.8); }
/* 药丸里那个会滚的数字：给它一个固定宽度，别让整条药丸随位数抖动 */
.pd-auto-state__n { display: inline-block; min-width: 2ch; text-align: right; font-weight: 600; }

/* 大读数：时钟 / 倒计时 */
.pd-auto-read {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 5px 9px 4px;
  border-radius: 3px; border: 1px solid rgba(255, 194, 75, 0.28); background: rgba(255, 194, 75, 0.06);
}
.pd-auto-read__l { font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.12em; color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-auto-read__v { flex: none; font-family: var(--pd-mono); font-size: 14px; font-weight: 600; letter-spacing: 0.06em; color: var(--pd-amber); text-shadow: 0 0 12px rgba(255, 194, 75, 0.35); }
.pd-auto-read--cd .pd-auto-read__v { font-size: 15px; }

/* 一行说明 */
.pd-auto-meta {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 4px 8px; border-radius: 3px; background: rgba(255, 255, 255, 0.03);
}
.pd-auto-meta i { font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.14em; color: var(--pd-faint); white-space: nowrap; }
.pd-auto-meta b { font-size: 11px; font-weight: 500; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 任务条目：编号 + 名称 + 状态牌 + ✓，下面一行取值 */
.pd-auto-item {
  display: flex; flex-direction: column; gap: 5px; padding: 6px 8px 7px;
  border-radius: 3px; border: 1px solid var(--pd-line); border-left: 2px solid var(--pd-line-strong);
  background: rgba(255, 255, 255, 0.03); min-width: 0;
  transition: border-color 0.25s, background 0.25s;
}
.pd-auto-item.is-run { border-left-color: var(--pd-amber); background: rgba(255, 194, 75, 0.07); }
.pd-auto-item.is-done { border-left-color: var(--pd-neon); background: rgba(61, 242, 141, 0.05); }
.pd-auto-item__h { display: flex; align-items: center; gap: 6px; min-width: 0; }
.pd-auto-item__n {
  flex: none; width: 13px; height: 13px; border-radius: 2px; display: grid; place-items: center;
  font-family: var(--pd-mono); font-size: 8px; font-weight: 700; color: #140d01; background: rgba(255, 194, 75, 0.75);
}
.pd-auto-item__l { flex: 1 1 auto; font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.16em; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-auto-item__b {
  flex: none; font-family: var(--pd-mono); font-size: 8.5px; font-weight: 500; letter-spacing: 0.08em;
  padding: 1px 5px 0; border-radius: 2px; white-space: nowrap;
  border: 1px solid var(--pd-line-strong); color: var(--pd-faint);
}
.pd-auto-item__b.is-run { border-color: rgba(255, 194, 75, 0.6); color: var(--pd-amber); background: rgba(255, 194, 75, 0.12); }
.pd-auto-item__b.is-done { border-color: rgba(61, 242, 141, 0.5); color: var(--pd-neon); background: rgba(61, 242, 141, 0.12); }
.pd-auto-item__c { flex: none; display: grid; place-items: center; width: 12px; height: 12px; color: var(--pd-line-strong); }
.pd-auto-item__c .pd-ic { width: 11px; height: 11px; stroke-width: 2.6; }
.pd-auto-item.is-done .pd-auto-item__c { color: var(--pd-neon); }
.pd-auto-item__v { display: flex; align-items: center; gap: 5px; min-width: 0; }
.pd-auto-item__v > .pd-ic { flex: none; width: 12px; height: 12px; color: var(--pd-dim); }
.pd-auto-item__t { flex: 1 1 auto; font-size: 11px; font-weight: 400; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-auto-item.is-run .pd-auto-item__t { color: var(--pd-amber); }
.pd-auto-sw {
  flex: none; font-family: var(--pd-mono); font-size: 8px; font-weight: 700; letter-spacing: 0.14em;
  padding: 1px 4px 0; border-radius: 2px; color: var(--pd-neon); border: 1px solid rgba(61, 242, 141, 0.45); background: rgba(61, 242, 141, 0.1);
}

/* 标签芯片（新好友接待：两枚叠上去） */
.pd-auto-chips { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
.pd-auto-chip {
  font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.04em; padding: 1px 6px 0; border-radius: 2px; white-space: nowrap;
  border: 1px solid rgba(255, 194, 75, 0.5); color: var(--pd-amber); background: rgba(255, 194, 75, 0.1);
}

/* 评论草稿行：按规则拟好再发，整组里唯一带光标的地方 */
.pd-auto-draft {
  display: flex; align-items: center; gap: 5px; min-width: 0; margin-top: 1px; padding: 3px 6px;
  border-radius: 3px; border: 1px dashed rgba(255, 194, 75, 0.42); background: rgba(255, 194, 75, 0.05);
}
.pd-auto-draft__k { flex: none; font-family: var(--pd-mono); font-size: 8px; font-weight: 700; letter-spacing: 0.1em; padding: 1px 4px 0; border-radius: 2px; color: #140d01; background: var(--pd-amber); }
.pd-auto-draft__t { min-width: 0; font-size: 11px; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 任务边界注释：虚线框 + 灰字，一眼看得出不是按钮 */
.pd-auto-note {
  margin-top: auto; display: flex; align-items: center; gap: 6px; padding: 4px 7px; border-radius: 3px;
  border: 1px dashed var(--pd-line-strong); background: rgba(255, 255, 255, 0.02);
  font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.1em; color: var(--pd-faint); white-space: nowrap; overflow: hidden;
}
.pd-auto-note .pd-ic { flex: none; width: 11px; height: 11px; }

/* 进度：已发出 n / N + 霓虹条 */
.pd-auto-prog { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.pd-auto-prog__t { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.1em; color: var(--pd-dim); white-space: nowrap; }
.pd-auto-prog__t b { color: var(--pd-neon); font-weight: 600; }
.pd-auto-prog__k { flex: none; padding: 1px 5px 0; border-radius: 2px; letter-spacing: 0.2em; font-size: 8.5px; color: #04140b; background: var(--pd-neon); opacity: 0.86; }
.pd-auto-prog__bar { display: block; height: 3px; border-radius: 2px; background: var(--pd-skel); overflow: hidden; }
.pd-auto-prog__bar b { display: block; width: 100%; height: 100%; transform-origin: 0 50%; background: var(--pd-neon); box-shadow: 0 0 8px rgba(61, 242, 141, 0.6); }

/* ── 收件人队列（定时群发的右侧工作区）── */
.pd-auto-q { position: absolute; inset: 0; display: flex; flex-direction: column; min-height: 0; }
.pd-auto-q__h {
  height: 32px; flex: none; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 14px;
  border-bottom: 1px solid var(--pd-line); font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.18em; color: var(--pd-faint);
}
.pd-auto-q__l { flex: 1 1 auto; min-height: 0; padding: 10px 12px; display: flex; flex-direction: column; gap: 5px; overflow: hidden; }
.pd-auto-q__r {
  display: flex; align-items: center; gap: 9px; padding: 5px 9px; border-radius: 4px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid transparent; transition: border-color 0.25s, background 0.25s;
}
.pd-auto-q__r.is-run { border-color: rgba(255, 194, 75, 0.34); background: rgba(255, 194, 75, 0.06); }
.pd-auto-q__r.is-done { border-color: rgba(61, 242, 141, 0.26); background: rgba(61, 242, 141, 0.05); }
.pd-auto-q__r .pd-av { width: 26px; height: 26px; font-size: 11px; }
.pd-auto-q__t { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pd-auto-q__t b { font-size: 11.5px; font-weight: 500; color: var(--pd-ink); white-space: nowrap; }
.pd-auto-q__t i { font-size: 10.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-auto-q__s {
  flex: none; font-family: var(--pd-mono); font-size: 9px; font-weight: 500; letter-spacing: 0.08em;
  padding: 2px 6px 1px; border-radius: 2px; white-space: nowrap;
  border: 1px solid var(--pd-line-strong); color: var(--pd-faint);
}
.pd-auto-q__s.is-run { border-color: rgba(255, 194, 75, 0.6); color: var(--pd-amber); background: rgba(255, 194, 75, 0.12); }
.pd-auto-q__s.is-done { border-color: rgba(61, 242, 141, 0.5); color: var(--pd-neon); background: rgba(61, 242, 141, 0.12); }
.pd-auto-q__c { flex: none; display: grid; place-items: center; width: 13px; height: 13px; color: var(--pd-neon); }
.pd-auto-q__c .pd-ic { width: 12px; height: 12px; stroke-width: 2.6; }
.pd-root .pd-auto-q__tail { margin: 3px 2px 0; font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.12em; color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ── 新好友接待：聊天窗贴在右栏里，标题被自动改写时转琥珀 ── */
.pd-screen .pd-auto-chat .pd-chat__title.pd-auto-hit { color: var(--pd-amber); text-shadow: 0 0 8px rgba(255, 194, 75, 0.4); }
/* 系统行收窄到文字宽度居中，kit.flash 的光环才不会横贯整行 */
.pd-auto-chat .pd-sys { align-self: center; max-width: 92%; }
/* 输入条上「发送」键的位置：换成一条执行状态，画面里没有任何可点的东西 */
.pd-auto-run {
  display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
  font-family: var(--pd-mono); font-size: 9.5px; font-weight: 400; letter-spacing: 0.12em; color: var(--pd-amber);
}
.pd-auto-run::before { content: ""; flex: none; width: 5px; height: 5px; border-radius: 50%; background: var(--pd-amber); box-shadow: 0 0 8px rgba(255, 194, 75, 0.8); }

/* ── 跟圈：信息流贴在右栏里，时间挪到名字后面（收掉 meta 行才塞得下四条）── */
.pd-auto-feed .pd-feed__list { padding: 10px 14px; gap: 10px; }
.pd-screen .pd-auto-feed .pd-post__name { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.pd-auto-when { font-size: 10px; font-weight: 400; color: var(--pd-faint); }
.pd-auto-feed .pd-post__name .pd-tag { margin-left: 0; }
/* 点赞栏/评论栏收窄到内容宽度：一条点赞不该拉成一根横贯整条动态的空灰带 */
.pd-auto-feed .pd-post__social { align-self: flex-start; max-width: 100%; }
/* 命中屏蔽词的那条：灰掉，一眼看出它被规则挡下、不跟发 */
.pd-auto-tag--off { border-color: var(--pd-line-strong); color: var(--pd-faint); }
.pd-auto-heart { display: inline-flex; flex: none; }
.pd-root .pd-auto-feed .pd-post__likes.is-on .pd-auto-heart { color: var(--pd-amber); }
.pd-root .pd-auto-feed .pd-post__likes.is-on .pd-auto-heart .pd-ic { fill: var(--pd-amber); }

/* 跟发规则底下的屏蔽词行：跟圈最怕跟错，哪些一律不发得写在规则上 */
.pd-auto-block {
  display: flex; align-items: center; gap: 6px; margin-top: 5px; padding: 3px 6px;
  border: 1px solid rgba(255, 93, 93, 0.32); border-radius: 3px;
  font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.06em; color: var(--pd-dim);
  white-space: nowrap; overflow: hidden;
}
.pd-auto-block__k { flex: none; font-style: normal; color: var(--pd-red); letter-spacing: 0.14em; }
.pd-auto-block__n { margin-left: auto; font-weight: 400; color: var(--pd-red); }
/* 跟发出去的那一条是我自己的动态：左边一道霓虹边，和被跟的原动态区分开 */
.pd-auto-mine { border-left: 2px solid var(--pd-neon); padding-left: 8px; margin-left: -10px; }
`;
