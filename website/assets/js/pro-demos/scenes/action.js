/* ════════════════════════════════════════════════════════════
   scenes / action.js — 微信动作（11 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4.5–7.5 秒，结尾用 kit.ok() 盖印章并停留 ≥0.9 秒。

   ── 这组的两个世界（别搞混）──
   ① 发送 9 项（文字 / @ / 图片 / 视频 / 表情 / 文件 / 链接 / 语音 / 拍一拍）是**经微信客户端的真实动作**：
      一律 kit.workflow 立一条底轨（触发 → 取件或 AI → 自动执行），全程**没有人在点**：
      不用 kit.cursor，内容自己出现、自己发出；自动产生的那条挂一枚 kit.tag，静止帧里也看得出不是手打的。
      核心表达仍是 kit.twin 双窗 + twin.fly：左窗是本应用，右窗是真实微信，光点飞过去 = 那边真的收到了。
   ② chat-mark-read / chat-set-mute 只写**本地解密副本**，单向、不回写微信：
      情境条必须 kit.scenario(text, { local: true })，画面里是人在整理自己的档案，光标操作是合理的。
   ════════════════════════════════════════════════════════════ */

/* ── 起手：情境条 + 双窗口 + 两边同一段业务上下文 ── */
function setup(kit, { title = "客户 · 王总", group = false, scenario = "", seed } = {}) {
  const twin = kit.twin({ title, group });
  const strip = kit.scenario(scenario);
  // 情境条右端的结果文案会被屏幕右上角的装饰角标（.pd-corner.tr，占 624–634）划穿：
  // 共用件只留了 11px 右内边距，本组统一让出 20px，最后一个字才读得全
  strip.classList.add("pd-action-strip");
  const run = (chat) => (seed ? seed(chat) || [] : []);
  return { twin, strip, appRows: run(twin.appChat), wxRows: run(twin.wxChat) };
}

/* 输入框的可视区域（.pd-chat__field）：field 本身是空的 em，量不到宽度 */
const fieldBox = (chat) => chat.field.parentElement;

/* 会话头右侧的批量进度小牌：一眼看出这不是发一条，是一批里的第 n 条 */
function headChip(kit, chat, text) {
  const el = kit.h("i", "pd-action-chip", text);
  chat.head.insertBefore(el, chat.more);
  return el;
}

/* ── 输入条上方的小面板：值班表 / 物料库 / 表情格共用一张脸（工作流自己弹开，没有人去点）── */
function popover(kit, gsap, host, cls = "", head = "") {
  const el = kit.h("div", `pd-action-pop ${cls}`);
  if (head) el.appendChild(kit.h("i", "pd-action-pop__h", head));
  host.appendChild(el);
  gsap.set(el, { opacity: 0, y: 6, scale: 0.96, transformOrigin: "0 100%" });
  return {
    el,
    open: () => gsap.to(el, { opacity: 1, y: 0, scale: 1, duration: 0.24, ease: "power3.out" }),
    close: () => gsap.to(el, { opacity: 0, y: 4, duration: 0.16, ease: "power2.in" }),
  };
}

/* ── 收款码：物料库里取的和微信里收到的用同一块料，静止帧里一眼认得出发的是什么 ── */
function qrTile(kit, cls = "") {
  const q = kit.h("i", `pd-action-qr ${cls}`);
  q.append(kit.h("b", "pd-action-qr__c tl"), kit.h("b", "pd-action-qr__c tr"), kit.h("b", "pd-action-qr__c bl"));
  return q;
}

/* ── 输入区里的附件小卡：缩略图 + 文件名 ── */
function attachment(kit, gsap, chat, { video = false, iconName, name = "IMG_2041.jpg" } = {}) {
  const el = kit.h("i", "pd-action-attach");
  const th = kit.h("b", "pd-action-attach__th");
  th.appendChild(kit.icon(iconName || (video ? "play" : "image")));
  el.append(th, kit.h("span", "pd-action-attach__n", name));
  fieldBox(chat).insertBefore(el, chat.field);
  gsap.set(el, { display: "none" });
  return el;
}

/* ── 触发：微信那边先来事（消息或系统提示），应用这边同步收到并命中规则 ── */
function trigger(kit, gsap, twin, { text, av = "王", name, sys = false, cls = "" } = {}) {
  const { appChat, wxChat } = twin;
  const mk = (chat) => {
    if (sys) {
      const p = kit.h("p", `pd-sys pd-action-tight ${cls}`, text);
      chat.list.appendChild(p);
      gsap.set(p, { display: "none" });
      return { node: p, hit: p, show: "block" };
    }
    const r = chat.row("l", text, { av, name });
    gsap.set(r, { display: "none" });
    return { node: r, hit: r.content, show: "flex" };
  };
  const a = mk(wxChat), b = mk(appChat);
  const t = gsap.timeline();
  t.set(a.node, { display: a.show }, 0)
    .add(kit.pop(a.node), 0)
    .add(twin.fly(wxChat.list, appChat.list, { duration: 0.5 }), 0.15)
    .set(b.node, { display: b.show }, 0.78)
    .add(kit.pop(b.node), 0.78)
    .add(kit.flash(b.hit, { color: "amber", duration: 0.5 }), 0.78);
  return t;
}

/* ── 取件：素材面板自己弹开 → 命中的那一件自己点亮 → 附件自己落进输入区（全程没有光标）── */
function fetchBeat(kit, gsap, { pop, target, attach, tail = 0.2 } = {}) {
  const b = gsap.timeline();
  b.add(pop.open(), 0)
    .call(() => target.classList.add("is-on"), [], 0.3)
    .add(kit.flash(target, { color: "amber", duration: 0.45 }), 0.3)
    .add(pop.close(), 0.95);
  if (attach) {
    b.set(attach, { display: "flex" }, 1)
      .add(kit.pop(attach, { duration: 0.32 }), 1);
  }
  b.to({}, { duration: tail }, 1.32);
  return b;
}

/* ── 自动执行：没有人按发送键，内容自己从左窗飞进微信，两边各落一条 ── */
function autoSend(kit, gsap, twin, { build, side = "r", name, attach, tag, clear } = {}) {
  const { appChat, wxChat } = twin;
  const mk = (chat) => {
    const content = build();
    if (side === "sys") { chat.list.appendChild(content); gsap.set(content, { display: "none" }); return content; }
    const r = chat.row(side, content, name ? { name } : {});
    gsap.set(r, { display: "none" });
    return r;
  };
  const rowApp = mk(appChat), rowWx = mk(wxChat);
  // 自动产生的那条挂个小标：静止帧里也看得出不是人手打的
  // sys 行（拍一拍）返回的就是那枚 <p>，直接往里挂，不然它会是全组唯一没标的一条
  if (tag) (side === "sys" ? rowApp : rowApp.body).appendChild(kit.tag(tag));
  const show = side === "sys" ? "block" : "flex";
  const t = gsap.timeline();
  if (attach) t.to(attach, { opacity: 0, duration: 0.14 }, 0).set(attach, { display: "none" }, 0.14);
  if (clear) t.call(clear, [], 0.16);
  t.set(rowApp, { display: show }, 0.2)
    .add(kit.pop(rowApp), 0.2)
    .add(twin.fly(rowApp, wxChat.list, { duration: 0.66 }), 0.3)
    .set(rowWx, { display: show }, 1.1)
    .add(kit.pop(rowWx), 1.1)
    .add(kit.flash(side === "sys" ? rowWx : rowWx.content, { color: "neon", duration: 0.7 }), 1.1);
  // arriveAt：微信那边真正收到的那一刻，收尾（结果文案 + 印章）要对着它落拍
  return Object.assign(t, { rowApp, rowWx, arriveAt: 1.1 });
}

/* ── 收尾：工作流收成已完成态 + 结果文案 + 印章，三样同一拍落在「微信那边收到」的瞬间 ──
   印章停留按落拍时刻算（至少 0.95s）：走片是按总时长六等分采样的，
   停留不到总长的 1/4，倒数第二帧就抓不到结果文案，收益帧只剩一张。 */
function finish(tl, kit, { strip, flow, at, result, stamp = "已自动发送", en = "AUTO · SENT" }) {
  const hold = Math.max(0.95, at / 3 + 0.15);
  tl.add(flow.done(), at)
    .add(kit.ok(stamp, { en, hold }), at)
    .add(strip.result(result), at);
  return at;
}

/* ── 三步工作流的统一编排：情境条 → 触发 → 取件 / AI → 自动执行 → 结果与印章同一拍 ──
   返回收尾那一拍的时刻（= 微信那边收到的瞬间），要补个尾（进度跳一格之类）的场景拿它对拍。 */
function compose(tl, kit, { strip, flow, trig, fetch, send, result, stamp, en, lightAt = 0.55 }) {
  const T = 0.45;
  tl.add(strip.in(), 0.05).add(flow.in(), 0.15);
  tl.add(trig, T).add(flow.step(0), T + lightAt);
  const f0 = Math.max(T + trig.duration(), T + lightAt + 0.3) + 0.2;
  tl.add(flow.step(1), f0).add(fetch, f0 + 0.1);
  const s0 = f0 + 0.1 + fetch.duration() + 0.15;
  tl.add(flow.step(2), s0).add(send, s0 + 0.1);
  return finish(tl, kit, { strip, flow, result, stamp, en, at: s0 + 0.1 + (send.arriveAt ?? send.duration() - 0.7) });
}

/* ═══════════════ send-text 发送文字消息 · 客服自动回复 ═══════════════ */
/* 半夜客户问价 → 规则命中，输入框自己把回复打出来（人没碰键盘）→ 发出去，客户当场收到 */
function sendText({ gsap, kit, tl }) {
  const ASK = "在吗？这款还有现货吗";
  const REPLY = "在的，现货充足，明早 9 点客服为您跟进";
  const { twin, strip } = setup(kit, {
    title: "客户 · 王总",
    scenario: "23:14 · 客户咨询进来了 · 无人值班",
    seed: (chat) => [chat.time("今天 23:14")],
  });
  const { appChat, wxChat } = twin;
  appChat.el.classList.add("pd-action-wrap");   // 自动回复正文比闲聊长，输入行放高一档让整句可读

  // 全程没有人：工作流轨说明这一条是怎么被触发、被生成、被发出的
  const flow = kit.workflow([
    { label: "新消息命中「现货」", icon: "bolt" },
    { label: "生成回复", ai: true },
    { label: "自动发送", icon: "send" },
  ]);

  // 客户的消息：微信那边先响，应用这边同步落一条
  const askWx = wxChat.row("l", ASK, { av: "王" });
  const askApp = appChat.row("l", ASK, { av: "王" });
  gsap.set([askWx, askApp], { display: "none" });

  const replyApp = appChat.row("r", REPLY);
  const replyWx = wxChat.row("r", REPLY);
  gsap.set([replyApp, replyWx], { display: "none" });
  // 自动发出的那条挂个「AI 自动回复」小标，静止帧里也看得出不是人手打的
  replyApp.body.appendChild(kit.tag("AI 自动回复"));

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 客户消息进来，触发节点点亮
    .set(askWx, { display: "flex" }, 0.5)
    .add(kit.pop(askWx), "<")
    .add(twin.fly(wxChat.list, appChat.list, { duration: 0.5 }), "<+0.15")
    .set(askApp, { display: "flex" }, ">-0.12")
    .add(kit.pop(askApp), "<")
    .add(flow.step(0), "<")
    .add(kit.flash(askApp.content, { color: "amber", duration: 0.5 }), "<")
    // ② AI 生成：输入框自己逐字打出，没有光标、没有点击
    .add(flow.step(1), ">+0.15")
    .add(kit.type(appChat.field, REPLY, { cps: 16 }), "<+0.1")
    // ③ 自动发送：没有人按发送键，光点直接飞去微信
    .add(flow.step(2), ">+0.1")
    .call(() => { appChat.field.textContent = ""; appChat.field.classList.remove("is-typing"); })
    .set(replyApp, { display: "flex" }, "<")
    .add(kit.pop(replyApp), "<")
    .add(twin.fly(replyApp, wxChat.list, { duration: 0.66 }), "<+0.1")
    .set(replyWx, { display: "flex" }, ">-0.12")
    .add(kit.pop(replyWx), "<")
    .add(kit.flash(replyWx.content, { color: "neon", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已自动发送", { en: "AUTO REPLY · SENT" }), ">-0.3")
    .add(strip.result("深夜也 2 秒接住，无人值守"), "<");
  return tl;
}

/* ═══════════════ send-at 发送群聊 @ 消息 · 群内派单 ═══════════════ */
/* 工单抛进值班群 → AI 查值班表判定负责人 → 自动 @ 出去，没人盯群也不会漏派 */
function sendAt({ gsap, kit, tl }) {
  const { twin, strip } = setup(kit, {
    title: "值班群", group: true,
    scenario: "10:26 · 值班群抛来一张工单",
    seed: (chat) => [chat.time("今天 10:26")],
  });
  const { appChat } = twin;
  appChat.el.classList.add("pd-action-wrap");   // 「@小王 工单 #2043 请认领」比输入框宽，折行显示别截尾
  const field = appChat.field;
  const mention = (t) => kit.h("span", "pd-action-at__m", t);

  const flow = kit.workflow([
    { label: "工单关键词命中", icon: "bolt" },
    { label: "判定负责人", ai: true },
    { label: "自动 @ 认领", icon: "at" },
  ]);

  // 值班表自己弹开，AI 判定出的那位自己点亮——没有人在挑
  const pop = popover(kit, gsap, appChat.main, "pd-action-at", "值班表 · 10:26");
  const items = [["小王", "今日值班"], ["小李", "休息"], ["老张", "外勤"]].map(([n, st], i) => {
    const it = kit.h("div", "pd-action-pop__it");
    it.append(kit.avatar(n[0], i % 2 ? "muted" : "them"), kit.h("span", "", n), kit.h("i", "pd-action-pop__st", st));
    pop.el.appendChild(it);
    return it;
  });

  const trig = trigger(kit, gsap, twin, { text: "工单 #2043 客户催发货", name: "客服中心", av: "服" });

  // AI 判定 + 输入框自己把 @ 和正文填好（点亮语义与物料 / 教程库共用一套 fetchBeat）
  const typed = kit.h("span", "", "");
  const fetch = fetchBeat(kit, gsap, { pop, target: items[0], tail: 0 });
  fetch.call(() => { field.replaceChildren(mention("@小王"), document.createTextNode(" "), typed); field.classList.add("is-typing"); }, [], 1.0)
    .add(kit.type(typed, "工单 #2043 请认领", { cps: 16, caret: false }), 1.05)
    .call(() => field.classList.remove("is-typing"), [], 1.75);

  const send = autoSend(kit, gsap, twin, {
    tag: "AI 自动派单",
    clear: () => { field.replaceChildren(); field.classList.remove("is-typing"); },
    build: () => {
      const b = kit.bubble("", "r");
      b.append(mention("@小王"), document.createTextNode(" 工单 #2043 请认领"));
      return b;
    },
  });

  compose(tl, kit, { strip, flow, trig, fetch, send, result: "值班同事已 @ 到", en: "AUTO @ · SENT" });
  return tl;
}

/* ═══════════════ send-image 发送图片消息 · 物料秒发 ═══════════════ */
/* 客户问「收款码」→ 工作流从物料库里取到那一张 → 自动发过去 */
function sendImage({ gsap, kit, tl }) {
  const { twin, strip } = setup(kit, {
    title: "客户 · 王总",
    scenario: "11:08 · 客户催着要收款码",
    seed: (chat) => [chat.time("今天 11:08")],
  });
  const { appChat } = twin;
  const flow = kit.workflow([
    { label: "客户问「收款码」", icon: "bolt" },
    { label: "匹配物料", icon: "image" },
    { label: "自动发送", icon: "send" },
  ]);

  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "物料库 · 命中「收款码」");
  const grid = kit.h("div", "pd-action-pick__grid");
  const thumbs = ["门店海报", "收款码", "产品图"].map((cap) => {
    const t = kit.h("i", "pd-action-thumb");
    // 收款码那一格画成真的码：光靠底下三行小字分不出取的是哪一张
    t.append(cap === "收款码" ? qrTile(kit, "pd-action-qr--sm") : kit.icon("image"), kit.h("b", "pd-action-thumb__cap", cap));
    grid.appendChild(t);
    return t;
  });
  pop.el.appendChild(grid);
  const attach = attachment(kit, gsap, appChat, { name: "收款码.png" });

  const trig = trigger(kit, gsap, twin, { text: "收款码发我一下", av: "王" });
  const fetch = fetchBeat(kit, gsap, { pop, target: thumbs[1], attach });
  // 发出去的那条也是同一块料：收益帧上客户拿到的是收款码，不是一张空白占位图
  const send = autoSend(kit, gsap, twin, {
    attach, tag: "自动发送",
    build: () => { const c = kit.card.image({ w: 104, hh: 76 }); c.replaceChildren(qrTile(kit)); return c; },
  });

  compose(tl, kit, { strip, flow, trig, fetch, send, result: "物料已送达", en: "AUTO · SENT" });
  return tl;
}

/* ═══════════════ send-video 发送视频消息 · 教程分发 ═══════════════ */
/* 新客户一进群就触发 → 取到那条操作教程 → 自动发出去，不用人守着迎新 */
function sendVideo({ gsap, kit, tl }) {
  const fmt = (v) => `迎新 ${Math.round(v)} / 12`;
  const { twin, strip } = setup(kit, {
    title: "新客户群", group: true,
    scenario: "09:41 · 新客户刚进群",
    seed: (chat) => [chat.time("今天 09:41")],
  });
  const { appChat } = twin;
  // 教程是「一条条发给每个新客户」：会话头挂个进度牌，一眼看出这是一批里的第 5 条
  const chip = headChip(kit, appChat, fmt(5));
  const flow = kit.workflow([
    { label: "新客户入群 · 5 / 12", icon: "bolt" },
    { label: "取操作教程", icon: "video" },
    { label: "自动发送", icon: "send" },
  ]);

  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "教程库 · 新客户必看");
  const grid = kit.h("div", "pd-action-pick__grid");
  const thumbs = [["功能总览", "0:21"], ["导出教程", "0:38"], ["进阶技巧", "1:02"]].map(([cap, d]) => {
    const t = kit.h("i", "pd-action-thumb pd-action-thumb--video");
    t.append(kit.icon("play", "pd-ic pd-action-thumb__play"), kit.h("b", "pd-action-thumb__dur", d), kit.h("b", "pd-action-thumb__cap", cap));
    grid.appendChild(t);
    return t;
  });
  pop.el.appendChild(grid);
  const attach = attachment(kit, gsap, appChat, { video: true, name: "导出教程.mp4" });

  const trig = trigger(kit, gsap, twin, { sys: true, text: "张先生 加入了群聊" });
  const fetch = fetchBeat(kit, gsap, { pop, target: thumbs[1], attach });
  const send = autoSend(kit, gsap, twin, { attach, tag: "自动发送", build: () => kit.card.video({ dur: "0:38" }) });

  const at = compose(tl, kit, { strip, flow, trig, fetch, send, result: "教程已发出", en: "AUTO · SENT" });
  // 这一位发完，迎新队列自己走到下一位
  tl.add(kit.count(chip, 6, { from: 5, duration: 0.45, fmt }), at)
    .add(kit.flash(chip, { color: "neon", duration: 0.6 }), at);
  return tl;
}

/* ═══════════════ send-emoji 发送表情消息 · 社群活跃 ═══════════════ */
// 表情格：三种图标混排、各自带一点歪斜与深浅，像一版真的贴纸；第 6 格（heart）是 AI 挑中的那一枚
const EMO_CELLS = [
  ["smile", -6, 0.85], ["heart", 5, 0.75], ["hand", -3, 1], ["smile", 7, 0.8],
  ["hand", -8, 0.9], ["heart", -4, 1], ["smile", 6, 0.7], ["hand", 4, 0.85],
];
const PICKED_EMO = 5;
const EMO_SCAN = [0, 3, 6, 1, 4];
function sendEmoji({ gsap, kit, tl }) {
  const quietFmt = (v) => `群里静默 ${Math.round(v)} 分钟`;
  const quiets = [];
  const { twin, strip } = setup(kit, {
    title: "客户群", group: true,
    scenario: "客户群冷场了",
    seed: (chat) => {
      const rows = [chat.time("今天 21:03"), chat.row("l", "今天的抽奖就到这啦", { name: "运营 阿明", av: "明" })];
      const quiet = kit.h("p", "pd-sys pd-action-quiet pd-action-tight", quietFmt(1));
      chat.list.appendChild(quiet);
      quiets.push(quiet);
      rows.push(quiet);
      return rows;
    },
  });
  const { appChat } = twin;
  const flow = kit.workflow([
    { label: "群内静默 3 分钟", icon: "clock" },
    { label: "挑一个表情", ai: true },
    { label: "自动发送", icon: "send" },
  ]);

  const pop = popover(kit, gsap, appChat.main, "pd-action-emo", "表情库");
  const grid = kit.h("div", "pd-action-emo__grid");
  const sticker = (name, rot, op = 1) => { const s = kit.icon(name); s.style.transform = `rotate(${rot}deg)`; s.style.opacity = op; return s; };
  const cells = EMO_CELLS.map(([name, rot, op]) => { const e = kit.h("i", ""); e.appendChild(sticker(name, rot, op)); grid.appendChild(e); return e; });
  pop.el.appendChild(grid);
  const [pickName, pickRot] = EMO_CELLS[PICKED_EMO];
  // AI 挑中的那一枚先在输入区露个脸，再自动发出去
  const attach = kit.h("i", "pd-action-attach pd-action-attach--emo");
  const th = kit.h("b", "pd-action-attach__th"); th.appendChild(sticker(pickName, pickRot));
  attach.append(th, kit.h("span", "pd-action-attach__n", "表情"));
  fieldBox(appChat).insertBefore(attach, appChat.field);
  gsap.set(attach, { display: "none" });

  // 触发：静默时间自己往上走，走到 3 分钟就命中
  const trig = gsap.timeline();
  quiets.forEach((q) => trig.add(kit.count(q, 3, { from: 1, duration: 0.85, fmt: quietFmt }), 0));
  trig.add(kit.flash(quiets[0], { color: "amber", duration: 0.5 }), 0.6);

  // AI 挑表情：格子被扫一遍，最后落在一枚上
  const fetch = gsap.timeline();
  fetch.add(pop.open(), 0);
  EMO_SCAN.forEach((k, i) => {
    fetch.call(() => { cells.forEach((c) => c.classList.remove("is-scan")); cells[k].classList.add("is-scan"); }, [], 0.28 + i * 0.1);
  });
  fetch.call(() => { cells.forEach((c) => c.classList.remove("is-scan")); cells[PICKED_EMO].classList.add("is-on"); }, [], 0.82)
    .add(kit.flash(cells[PICKED_EMO], { color: "amber", duration: 0.45 }), 0.82)
    .add(pop.close(), 1.35)
    .set(attach, { display: "flex" }, 1.4)
    .add(kit.pop(attach, { duration: 0.32 }), 1.4)
    .to({}, { duration: 0.18 }, 1.72);

  const send = autoSend(kit, gsap, twin, {
    attach, tag: "AI 自动发送",
    build: () => { const card = kit.card.emoji(); card.replaceChildren(sticker(pickName, pickRot)); return card; },
  });

  compose(tl, kit, { strip, flow, trig, fetch, send, result: "气氛接住了", en: "AUTO · SENT", lightAt: 0.9 });
  return tl;
}

/* ═══════════════ send-file 发送文件消息 · 报价单直发 ═══════════════ */
/* 客户催报价 → 工作流取最新那版报价单 → 自动发出去，不会误发旧版 */
function sendFile({ gsap, kit, tl }) {
  const NAME = "报价单 2026-09.pdf";
  const { twin, strip } = setup(kit, {
    title: "客户 · 王总",
    scenario: "16:52 · 客户催报价单",
    seed: (chat) => [chat.time("今天 16:52")],
  });
  const { appChat } = twin;
  const flow = kit.workflow([
    { label: "客户问「报价」", icon: "bolt" },
    { label: "取最新报价单", icon: "file" },
    { label: "自动发送", icon: "send" },
  ]);

  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "报价单目录 · 按版本");
  const list = kit.h("div", "pd-action-filelist pd-action-filelist--col");
  const rows = [[NAME, "最新"], ["报价单 2026-06.pdf", ""], ["报价单 2025-12.pdf", ""]].map(([n, badge]) => {
    const row = kit.h("i", "pd-action-thumb pd-action-file pd-action-file--row");
    row.append(kit.icon("file"), kit.h("b", "pd-action-file__name", n));
    if (badge) row.appendChild(kit.h("i", "pd-action-file__badge", badge));
    list.appendChild(row);
    return row;
  });
  pop.el.appendChild(list);
  const attach = attachment(kit, gsap, appChat, { iconName: "file", name: NAME });

  const trig = trigger(kit, gsap, twin, { text: "这批的报价发我一份，急", av: "王" });
  const fetch = fetchBeat(kit, gsap, { pop, target: rows[0], attach });
  const send = autoSend(kit, gsap, twin, { attach, tag: "自动发送", build: () => kit.card.file({ name: NAME, size: "1.2 MB" }) });

  compose(tl, kit, { strip, flow, trig, fetch, send, result: "报价单已送达", en: "AUTO · SENT" });
  return tl;
}

/* ═══════════════ send-link 发送链接卡片 · 活动推送 ═══════════════ */
/* 批量任务跑到第 3 位 → 取活动链接 → 自动发出，发完进度自己跳到第 4 位 */
function sendLink({ gsap, kit, tl }) {
  const fmt = (v) => `批量 ${Math.round(v)} / 28`;
  const URL = "wcda.app/act/618";
  const { twin, strip } = setup(kit, {
    title: "客户 · 王总",
    scenario: "活动推送 · 批量任务在跑",
    seed: (chat) => [chat.time("今天 09:12"), chat.row("l", "好的，我看看", { av: "王" })],
  });
  const { appChat } = twin;
  const chip = headChip(kit, appChat, fmt(3));
  const flow = kit.workflow([
    { label: "批量任务 3 / 28", icon: "bolt" },
    { label: "取活动链接", icon: "link" },
    { label: "逐个自动发送", icon: "send" },
  ]);

  // 触发：队列排到这一位，进度牌先亮一下
  const trig = gsap.timeline();
  trig.add(kit.flash(chip, { color: "amber", duration: 0.7 }), 0);

  // 取件：链接自己填进输入框，没有人在打字
  const fetch = gsap.timeline();
  fetch.add(kit.type(appChat.field, URL, { cps: 15 }), 0).to({}, { duration: 0.25 }, ">");

  const send = autoSend(kit, gsap, twin, {
    tag: "自动发送",
    clear: () => { appChat.field.textContent = ""; appChat.field.classList.remove("is-typing"); },
    build: () => kit.card.link({ title: "618 老客专享", desc: "下单立减 15%" }),
  });

  const at = compose(tl, kit, { strip, flow, trig, fetch, send, result: "活动链接已送达", en: "AUTO · SENT", lightAt: 0.35 });
  // 这一位推完，队列自己走到下一位——说明这是一批里的一条
  tl.add(kit.count(chip, 4, { from: 3, duration: 0.45, fmt }), at)
    .add(kit.flash(chip, { color: "neon", duration: 0.6 }), at);
  return tl;
}

/* ═══════════════ send-voice 发送语音消息 · 语音通知 ═══════════════ */
/* 批量任务跑到第 7 位 → 取那条语音通知 → 自动发出，进度跳到第 8 位 */
function sendVoice({ gsap, kit, tl }) {
  const fmt = (v) => `逐个 ${Math.round(v)} / 24`;
  const { twin, strip } = setup(kit, {
    title: "客户 · 王总",
    scenario: "语音通知 · 批量任务在跑",
    seed: (chat) => [chat.time("今天 18:30"), chat.row("l", "好的，等通知", { av: "王" })],
  });
  const { appChat } = twin;
  const chip = headChip(kit, appChat, fmt(7));
  const flow = kit.workflow([
    { label: "批量任务 7 / 24", icon: "bolt" },
    { label: "取语音通知", icon: "mic" },   // voice 图标的 getBBox 超出 24×24 viewBox 会被裁成一截小弧，轨上用 mic
    { label: "逐个自动发送", icon: "send" },
  ]);

  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "语音库 · 本次任务");
  const list = kit.h("div", "pd-action-filelist pd-action-filelist--col");
  const rows = [["发货通知.mp3", "本次"], ["到店提醒.mp3", ""], ["活动播报.mp3", ""]].map(([n, badge]) => {
    const row = kit.h("i", "pd-action-thumb pd-action-file pd-action-file--row");
    row.append(kit.icon("file"), kit.h("b", "pd-action-file__name", n));
    if (badge) row.appendChild(kit.h("i", "pd-action-file__badge", badge));
    list.appendChild(row);
    return row;
  });
  pop.el.appendChild(list);
  const attach = attachment(kit, gsap, appChat, { iconName: "file", name: "发货通知.mp3" });
  const convert = kit.h("div", "pd-action-convert");
  convert.append(kit.icon("mic"), kit.h("span", "", "转换为语音 · 示意"));
  appChat.main.appendChild(convert);
  gsap.set(convert, { opacity: 0, y: 4 });

  const trig = gsap.timeline();
  trig.add(kit.flash(chip, { color: "amber", duration: 0.7 }), 0);

  // MP3 取到手 → 转成语音再发：提示浮一会儿，走片里也抓得到
  const fetch = fetchBeat(kit, gsap, { pop, target: rows[0], attach, tail: 0.05 });
  fetch.to(convert, { opacity: 1, y: 0, duration: 0.25 }, 1.1)
    .to(convert, { opacity: 0, y: -3, duration: 0.2 }, 2.2);

  const send = autoSend(kit, gsap, twin, { attach, tag: "自动发送", build: () => kit.card.voice({ sec: 8, side: "r" }) });

  const at = compose(tl, kit, { strip, flow, trig, fetch, send, result: "语音通知已发出", en: "AUTO · SENT", lightAt: 0.35 });
  tl.add(kit.count(chip, 8, { from: 7, duration: 0.45, fmt }), at)
    .add(kit.flash(chip, { color: "neon", duration: 0.6 }), at);
  return tl;
}

/* ═══════════════ send-pat 发送拍一拍 · 轻提醒 ═══════════════ */
/* 合同发出去超 24 小时没回 → 工作流自动拍一拍，比再发一条消息轻 */
function sendPat({ gsap, kit, tl }) {
  const overdue = [];
  const { twin, strip, appRows, wxRows } = setup(kit, {
    title: "客户 · 王总",
    scenario: "合同发出去，一直没回音",
    seed: (chat) => {
      const rows = [
        chat.time("昨天 16:40"),
        chat.row("l", "收到，我看下", { av: "王" }),
        chat.row("r", "合同已发您邮箱，麻烦确认一下"),
      ];
      const mark = kit.h("p", "pd-sys pd-action-quiet pd-action-tight", "已过 24 小时 · 对方未回");
      chat.list.appendChild(mark);
      overdue.push(mark);
      rows.push(mark);
      return rows;
    },
  });
  const appAv = appRows[1].av, wxAv = wxRows[1].av;   // 客户那行的头像
  const flow = kit.workflow([
    { label: "超 24 小时未回", icon: "clock" },
    { label: "自动拍一拍", icon: "hand" },
  ]);

  const shake = (el) => gsap.to(el, { keyframes: [
    { x: -3, rotate: -9, duration: 0.07 }, { x: 3, rotate: 9, duration: 0.07 },
    { x: -3, rotate: -6, duration: 0.07 }, { x: 3, rotate: 6, duration: 0.07 },
    { x: -1.5, rotate: -3, duration: 0.07 }, { x: 0, rotate: 0, duration: 0.07 },
  ] });

  const send = autoSend(kit, gsap, twin, {
    side: "sys", tag: "自动拍一拍",
    // 「拍了拍」那行收紧到文字宽度，落库描边贴着字走，不横贯整个列表
    build: () => { const p = kit.pat({ from: "我", to: "王总" }); p.classList.add("pd-action-tight"); return p; },
  });

  const SEND_AT = 2.35;
  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    // ① 超时命中：那条「已过 24 小时」自己亮起来
    .add(kit.flash(overdue[0], { color: "amber", duration: 0.6 }), 0.5)
    .add(flow.step(0), 0.75)
    // ② 自动拍：应用这边先抖一下客户头像，拍一拍那行随即落进两边
    .add(flow.step(1), 1.8)
    .add(shake(appAv), 1.95)
    .add(send, SEND_AT)
    .add(shake(wxAv), SEND_AT + 1.12);
  finish(tl, kit, { strip, flow, at: SEND_AT + send.arriveAt, result: "已轻提醒", stamp: "已自动拍一拍", en: "AUTO PAT" });
  return tl;
}

/* ═══════════════ chat-mark-read 会话标记已读 · 红点清理 ═══════════════ */
/* 一屏红点堆着 → 处理完的那个会话按一下「标记已读」→ 红点清零 */
function markRead({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "客户 · 王总" });
  const strip = kit.scenario("48 条未读堆着", { local: true });
  strip.classList.add("pd-action-strip");
  chat.time("今天 14:02");
  chat.row("l", "这批还有现货吗？", { av: "王" });
  chat.row("r", "有的，现货充足");
  chat.row("l", "好，我这边下单了", { av: "王" });

  const session = chat.sessions[0];
  const badge = (el, text) => {
    el.classList.add("pd-action-sess");
    const b = kit.h("i", "pd-action-unread" + (text ? "" : " pd-action-unread--dot"), text);
    el.appendChild(b);
    return b;
  };
  const unread = badge(session, "48");
  // 旁边的会话也堆着红点：一眼看出红点是成片的，不是孤零零一个
  const dots = chat.sessions.slice(1, 3).map((sess) => badge(sess));
  const action = kit.h("b", "pd-action-state-btn", "标记已读");
  chat.head.appendChild(action);
  const c = kit.cursor();

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.25)
    // 先让「红点成片」这件事亮一下，再动手
    .add(kit.flash(unread, { color: "red", duration: 0.95 }), 0.3)
    .add(kit.flash(dots[0], { color: "red", duration: 0.8 }), 0.45)
    .add(kit.flash(dots[1], { color: "red", duration: 0.8 }), 0.6)
    .add(c.to(session, { duration: 0.5 }), 0.7)
    .add(c.click(session), ">")
    .to({}, { duration: 0.35 })
    .add(c.to(action, { duration: 0.45 }), ">")
    .add(c.click(action), ">")
    .to(unread, { opacity: 0, scale: 0.5, duration: 0.3, ease: "back.in(2)" }, ">-0.05")
    .add(kit.flash(session, { color: "neon", duration: 0.75 }), "<")
    // 印章停留 1.35s > 总长的 1/4：走片倒数两帧都要抓得到「红点清零」
    .add(kit.ok("已标记已读", { en: "READ", hold: 1.35 }), ">-0.1")
    .add(strip.result("红点清零"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ chat-set-mute 会话免打扰 · 广告群静音 ═══════════════ */
/* 广告一条接一条往里灌 → 同一个开关拨到免打扰 → 会话名旁挂上静音图标、计数由红转灰 */
function setMute({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "广告推广群", group: true });
  const strip = kit.scenario("广告群一直响", { local: true });
  strip.classList.add("pd-action-strip");
  chat.time("今天 15:20");
  chat.row("l", "【推广】今日特价，点击领券", { name: "推广助手", av: "推" });
  chat.row("l", "还有 3 个名额，速抢", { name: "推广助手", av: "推" });
  // 又来一条：证明这个群是真的在响
  const spam = chat.row("l", "最后 1 小时，别错过", { name: "推广助手", av: "推" });
  gsap.set(spam, { display: "none" });

  const session = chat.sessions[0];
  session.classList.add("pd-action-sess");
  const unread = kit.h("i", "pd-action-unread", "9");
  session.appendChild(unread);
  // 会话名旁的静音图标：先备好，拨开关那一刻才亮
  const bell = kit.h("i", "pd-action-mute");
  bell.appendChild(kit.icon("bell"));
  chat.head.insertBefore(bell, chat.more);
  gsap.set(bell, { opacity: 0, scale: 0.5 });
  const toggle = kit.h("b", "pd-action-state-btn", "开启免打扰");
  chat.head.appendChild(toggle);
  const c = kit.cursor();

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.25)
    .set(spam, { display: "flex" }, 0.4)
    .add(kit.pop(spam), "<")
    .add(kit.count(unread, 14, { from: 9, duration: 0.95 }), "<")
    .add(kit.flash(unread, { color: "red", duration: 0.95 }), "<")
    .add(c.to(session, { duration: 0.5 }), 1)
    .add(c.click(session), ">")
    .to({}, { duration: 0.3 })
    .add(c.to(toggle, { duration: 0.45 }), ">")
    .add(c.click(toggle), ">")
    .call(() => {
      toggle.textContent = "已免打扰";
      toggle.classList.add("is-on");
      unread.classList.add("is-mute");   // 微信里静音会话的计数是灰的，不再是红点
    }, [], "<+0.12")
    .to(bell, { opacity: 1, scale: 1, duration: 0.32, ease: "back.out(2.4)" }, "<")
    .add(kit.flash(session, { color: "neon", duration: 0.75 }), "<")
    .add(kit.ok("已开启免打扰", { en: "MUTED", hold: 1.35 }), ">-0.1")
    .add(strip.result("群已静音"), "<")
    .add(c.hide(), "<");
  return tl;
}

export default {
  "send-text": sendText,
  "send-at": sendAt,
  "send-image": sendImage,
  "send-video": sendVideo,
  "send-emoji": sendEmoji,
  "send-file": sendFile,
  "send-link": sendLink,
  "send-voice": sendVoice,
  "send-pat": sendPat,
  "chat-mark-read": markRead,
  "chat-set-mute": setMute,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* 双窗的高度全部由 pro-demos.css 的 .pd-screen.has-strip[.has-flow] > .pd-win 管
   （九个发送场景恒是 strip + flow → 354px）；本文件不要再自算一遍，会是条死规则 */

/* 情境条与屏幕四角的装饰角标划穿：角标（.pd-corner）是 .pd-screen 的兄弟、z-index 3，画在屏幕之上，
   且按未缩放的真实像素定位——走片三列并排时缩放 0.6，它在 640×400 坐标系里等比放大到 17px，
   顶端两枚正好压在左边的情境文案和右端的结果文案上（收益帧那个字读不出来）。
   挂了情境条就不画上面两枚，底下两枚保留；padding 是 :has 不可用时的 1:1 兜底。
   根因在共用件（pro-demos.css 的 .pd-corner / .pd-strip），所有挂情境条的组都会中招。 */
.pd-screen:has(.pd-action-strip) ~ .pd-corner.tl,
.pd-screen:has(.pd-action-strip) ~ .pd-corner.tr { opacity: 0; }
.pd-strip.pd-action-strip { padding-right: 20px; }

/* 系统提示行（拍一拍）里的自动小标：那行是 <p>，标要跟着文字走 */
.pd-action-tight .pd-tag { margin-left: 6px; vertical-align: middle; }

/* 收款码：物料库缩略图与发出去的那张用同一块料 */
.pd-action-qr {
  position: relative; display: block; width: 52px; height: 52px; flex: none; border-radius: 1px;
  background-color: #e8f0ea;
  background-image: repeating-conic-gradient(#0d1410 0 25%, #e8f0ea 0 50%);
  background-size: 8px 8px;
  box-shadow: 0 0 0 4px #e8f0ea;
}
.pd-action-qr__c { position: absolute; width: 14px; height: 14px; box-sizing: border-box; border: 3px solid #0d1410; background: #e8f0ea; }
.pd-action-qr__c::after { content: ""; position: absolute; inset: 1.5px; background: #0d1410; }
.pd-action-qr__c.tl { left: 1px; top: 1px; }
.pd-action-qr__c.tr { right: 1px; top: 1px; }
.pd-action-qr__c.bl { left: 1px; bottom: 1px; }
.pd-action-qr--sm { width: 24px; height: 24px; background-size: 4px 4px; margin-bottom: 11px; box-shadow: 0 0 0 2px #e8f0ea; }
.pd-action-qr--sm .pd-action-qr__c { width: 7px; height: 7px; border-width: 1.5px; }
.pd-action-qr--sm .pd-action-qr__c::after { inset: 1px; }

/* 输入条上方的小面板：工作流自己弹开的取件面板 */
.pd-action-pop {
  position: absolute; left: 12px; bottom: 60px; z-index: 20; padding: 6px;
  background: #131a16; border: 1px solid var(--pd-line-strong); border-radius: 5px;
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.6);
}
.pd-action-wrap .pd-action-pop { bottom: 76px; }
.pd-action-pop__h { display: block; font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.16em; color: var(--pd-faint); padding: 2px 4px 6px; white-space: nowrap; }
.pd-action-pop__it { display: flex; align-items: center; gap: 8px; min-width: 168px; padding: 4px 8px 4px 5px; border-radius: 3px; font-size: 11.5px; color: var(--pd-ink); white-space: nowrap; }
.pd-action-pop__it .pd-av { width: 20px; height: 20px; font-size: 9px; border-radius: 3px; }
.pd-action-pop__it.is-on { background: rgba(255, 194, 75, 0.14); color: var(--pd-amber); }
.pd-action-pop__st { margin-left: auto; flex: none; font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.06em; color: var(--pd-faint); }
.pd-action-pop__it.is-on .pd-action-pop__st { color: var(--pd-amber); }
.pd-action-at__m { color: var(--pd-blue); }

/* 正文比输入框宽的场景（自动回复、@ 派单）：输入行放高一档并允许折行，整句都要读得到 */
.pd-action-wrap .pd-chat__input { height: 68px; }
.pd-action-wrap .pd-chat__field { align-items: flex-start; padding-top: 5px; }
.pd-action-wrap .pd-chat__text { white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.4; }

/* 会话头右侧的批量进度小牌 */
.pd-action-chip {
  margin-left: auto; flex: none; padding: 2px 6px; border-radius: 3px;
  border: 1px solid var(--pd-line-strong); font-family: var(--pd-mono); font-style: normal;
  font-size: 9px; font-weight: 400; letter-spacing: 0.08em; color: var(--pd-dim); white-space: nowrap;
}

/* 取件面板里的物料 / 教程缩略图 */
.pd-action-pick__grid { display: flex; gap: 6px; padding: 0 2px 2px; }
.pd-action-thumb {
  position: relative; width: 64px; height: 46px; border-radius: 3px; flex: none;
  background: var(--pd-tile); border: 1px solid transparent; display: grid; place-items: center; color: var(--pd-faint);
}
.pd-action-thumb .pd-ic { width: 18px; height: 18px; }
.pd-action-thumb__play { color: var(--pd-ink); opacity: 0.85; }
.pd-action-thumb__dur { position: absolute; right: 4px; top: 2px; font-family: var(--pd-mono); font-weight: 400; font-size: 8.5px; letter-spacing: 0; color: var(--pd-ink); opacity: 0.75; }
.pd-action-thumb__cap {
  position: absolute; left: 0; right: 0; bottom: 0; padding: 2px 0 2px; text-align: center;
  font-family: var(--pd-mono); font-weight: 400; font-size: 8px; letter-spacing: 0.02em; color: var(--pd-dim);
  background: linear-gradient(rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.62) 55%);
}
.pd-action-thumb.is-on { border-color: var(--pd-amber); box-shadow: 0 0 0 2px rgba(255, 194, 75, 0.22); color: var(--pd-amber); }
.pd-action-thumb.is-on .pd-action-thumb__play { color: var(--pd-amber); opacity: 1; }
.pd-action-thumb.is-on .pd-action-thumb__cap { color: var(--pd-amber); }

/* 文件 / 语音目录：竖排一列，文件名要写得全，一眼看出取的是哪一版 */
.pd-action-filelist { display: flex; gap: 6px; padding: 0 2px 2px; }
.pd-action-filelist--col { flex-direction: column; gap: 4px; }
.pd-action-file { width: 80px; height: 52px; display: flex; flex-direction: column; gap: 3px; padding: 6px 4px 4px; }
.pd-action-file .pd-ic { width: 17px; height: 17px; }
.pd-action-file__name { max-width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--pd-mono); font-size: 8px; font-weight: 400; }
.pd-action-file--row {
  width: 190px; height: auto; flex-direction: row; align-items: center; gap: 7px; padding: 5px 8px;
  place-items: center start;
}
.pd-action-file--row .pd-action-file__name { max-width: 118px; font-size: 9px; color: var(--pd-ink); }
.pd-action-file--row .pd-ic { width: 14px; height: 14px; }
.pd-action-file__badge {
  margin-left: auto; flex: none; padding: 1px 4px 0; border-radius: 2px;
  border: 1px solid rgba(255, 194, 75, 0.5); font-family: var(--pd-mono); font-style: normal;
  font-size: 7.5px; letter-spacing: 0.06em; color: var(--pd-amber);
}

/* 表情格：AI 挑选时先扫一遍，再落在一枚上 */
.pd-action-emo__grid { display: grid; grid-template-columns: repeat(4, 30px); gap: 5px; padding: 0 2px 2px; }
.pd-action-emo__grid i { width: 30px; height: 30px; border-radius: 4px; display: grid; place-items: center; color: var(--pd-dim); background: rgba(255, 255, 255, 0.04); border: 1px solid transparent; }
.pd-action-emo__grid i .pd-ic { width: 17px; height: 17px; }
.pd-action-emo__grid i.is-scan { border-color: rgba(255, 194, 75, 0.3); background: rgba(255, 194, 75, 0.07); }
.pd-action-emo__grid i.is-on { color: var(--pd-amber); background: rgba(255, 194, 75, 0.12); border-color: rgba(255, 194, 75, 0.55); }
.pd-action-emo__grid i.is-on .pd-ic { opacity: 1 !important; }

/* 屏内的状态注记（静默计时 / 超时未回）：比系统提示还淡，收紧到文字宽度好让描边贴着字走 */
.pd-root .pd-action-quiet { color: var(--pd-faint); opacity: 0.8; font-size: 10px; letter-spacing: 0.1em; }
.pd-action-tight { align-self: center; width: max-content; max-width: 92%; padding: 1px 8px; border-radius: 3px; }

/* 输入区里的附件小卡 */
.pd-action-attach { display: flex; align-items: center; gap: 6px; flex: none; margin-right: 6px; max-width: 100%; }
.pd-action-attach__th {
  width: 40px; height: 28px; border-radius: 3px; flex: none; display: grid; place-items: center;
  background: var(--pd-tile); border: 1px solid rgba(255, 194, 75, 0.5); color: var(--pd-amber);
}
.pd-action-attach__th .pd-ic { width: 14px; height: 14px; }
.pd-action-attach__n { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.04em; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-action-attach--emo .pd-action-attach__th { width: 28px; background: rgba(255, 194, 75, 0.08); }
.pd-action-attach--emo .pd-action-attach__th .pd-ic { width: 16px; height: 16px; }

/* MP3 转换提示：仅表达产品流程，不展开底层实现；浮在输入条上方，别盖住已经取好的附件 */
.pd-action-convert {
  position: absolute; left: 12px; bottom: 60px; height: 26px; z-index: 6;
  display: inline-flex; width: max-content; align-items: center; gap: 7px; padding: 0 9px; border-radius: 3px;
  background: rgba(255, 194, 75, 0.08); border: 1px solid rgba(255, 194, 75, 0.35);
  font-size: 11px; color: var(--pd-ink); white-space: nowrap;
}
.pd-action-convert .pd-ic { width: 14px; height: 14px; color: var(--pd-amber); }

/* 会话状态：按钮在同一位置切换开 / 关（本地写入两项用）*/
.pd-action-state-btn { margin-left: auto; flex: none; padding: 4px 8px; border: 1px solid rgba(255, 194, 75, 0.45); border-radius: 3px; color: var(--pd-amber); font-size: 10px; font-weight: 500; white-space: nowrap; }
.pd-action-state-btn.is-on { border-color: rgba(61, 242, 141, 0.45); color: var(--pd-neon); background: rgba(61, 242, 141, 0.12); }
/* 未读数：脱离布局钉在会话行右端，会话名才有地方写全 */
.pd-action-sess { position: relative; }
.pd-action-sess .pd-action-unread {
  position: absolute; right: 6px; top: 12px; z-index: 2;
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 17px; height: 16px; padding: 0 4px; border-radius: 8px;
  background: var(--pd-red); color: #fff; font-family: var(--pd-mono); font-size: 9px; font-style: normal; letter-spacing: 0;
}
.pd-action-sess .pd-action-unread--dot { min-width: 8px; width: 8px; height: 8px; padding: 0; top: 16px; }
.pd-action-sess .pd-action-unread.is-mute { background: #46524a; color: var(--pd-dim); }
/* 会话名旁的静音图标：铃铛压一道斜杠，斜杠外描一圈底色才看得清 */
.pd-action-mute { position: relative; flex: none; display: inline-grid; place-items: center; width: 16px; height: 16px; margin-left: 8px; color: var(--pd-dim); }
.pd-action-mute .pd-ic { width: 15px; height: 15px; }
.pd-action-mute::after {
  content: ""; position: absolute; left: -1px; top: 7px; width: 18px; height: 1.5px; border-radius: 1px;
  background: currentColor; box-shadow: 0 -1.5px 0 0 #0d1410, 0 1.5px 0 0 #0d1410; transform: rotate(-42deg);
}
`;
