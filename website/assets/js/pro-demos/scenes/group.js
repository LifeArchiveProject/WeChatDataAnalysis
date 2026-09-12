/* ════════════════════════════════════════════════════════════
   scenes / group.js — 群聊（8 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   这一组是**真实动作**（经微信客户端生效，群成员都看得到），不是本地副本，
   所以绝不能挂 { local: true }。

   演法统一：**没有人在操作**。每个场景底下立一条 kit.workflow（触发 → AI/规则 → 自动执行），
   节点随剧情逐步点亮；全程不用 kit.cursor，不点菜单、不点按钮、不手打字——
   内容自己出现、自己发出，右上角一张 autoPanel 是工作流的工作台（它没有按钮，因为没人来点）。
   自动产生的内容挂「自动发布 / 自动」小标，静止帧里也看得出不是人手打的。

   场景取自 catalog：进客户群自动规范身份、排期到点自动发公告、合同签了自动开服务群、
   新群自动套命名规则、提到技术问题自动拉值班、名单没进群的逐个自动邀请、
   命中广告关键词自动清退、项目结项自动退群。
   情境条讲「什么条件触发了它」，结尾 strip.result() 讲「省了什么事」，与印章同一拍。
   时长 4.5–7.5 秒，印章停留 ≥0.9 秒。
   ════════════════════════════════════════════════════════════ */

const ME = "星辰科技-小吴";   // 规范之后的群昵称：公司-姓名

/* ── 客户服务群骨架：会话栏名字与标题对上；消息贴着输入条堆叠（pd-group-bottom），
      右上角的自动化面板才压不住最新那几条。
      cls pd-group-c 把会话栏加宽到 182px——业务群名比私人群名长，别被截成省略号 ── */
function clientChat(kit, { title = "星辰科技客户群", rail = true, rails, rows = 3, lines, time = "今天 14:02", group = true } = {}) {
  const chat = kit.chat({ title, group, rail, cls: "pd-group-c" });
  if (rail) {
    const names = rails || [title, "王总", "订单群", "李经理"];
    chat.sessions.forEach((s, i) => {
      s.querySelector("b").textContent = names[i];
      s.querySelector(".pd-av").textContent = names[i][0];
    });
  }
  chat.list.classList.add("pd-group-bottom");
  chat.time(time);
  const src = lines || [
    ["l", "方案什么时候能给我？", { name: "王总", av: "王" }],
    ["l", "我这边先同步排期", { name: "李经理", av: "李" }],
  ];
  const all = src.slice(0, rows).map(([side, text, opt]) => chat.row(side, text, opt));
  return { chat, rows: all };
}

/* ── 自动化面板：右上角的一张浮层卡，工作流的「工作台」。
      头部一枚 mono 小牌说明这一步是规则还是 AI；卡上没有任何按钮——因为没有人来点 ── */
function autoPanel(kit, gsap, { kicker = "AUTO", title = "", cls = "" } = {}) {
  const el = kit.h("div", `pd-group-auto ${cls}`);
  const head = kit.h("div", "pd-group-auto__h");
  head.append(kit.h("i", "pd-group-auto__k", kicker), kit.h("b", "", title));
  const body = kit.h("div", "pd-group-auto__b");
  el.append(head, body);
  kit.mount(el);
  gsap.set(el, { opacity: 0, y: 8, scale: 0.96, transformOrigin: "100% 0%" });
  return Object.assign(el, {
    body,
    in(d = 0.32) { return gsap.to(el, { opacity: 1, y: 0, scale: 1, duration: d, ease: "back.out(1.6)" }); },
    out(d = 0.26) { return gsap.to(el, { opacity: 0, y: -6, duration: d, ease: "power2.in" }); },
  });
}

/* ── 规则块：上面一行 mono 模板，下面「→ 生成结果」（结果由 kit.type 打出来）── */
function ruleBlock(kit, pattern, parent) {
  const el = kit.h("div", "pd-group-rule");
  el.appendChild(kit.h("i", "pd-group-rule__p", pattern));
  const r = kit.h("div", "pd-group-rule__r");
  const v = kit.h("b", "pd-group-rule__v", "");
  r.append(kit.h("span", "pd-group-rule__a", "→"), v);
  el.appendChild(r);
  parent.appendChild(el);
  return Object.assign(el, { value: v });
}

/* ── 名单：一人一行（头像 + 姓名/身份 + 右侧状态牌）。建群 / 邀请 / 值班匹配共用 ── */
function roster(kit, people, parent) {
  const el = kit.h("div", "pd-group-roster");
  const rows = people.map(([name, org, badge, tone = ""]) => {
    const r = kit.h("div", "pd-group-roster__r");
    r.appendChild(kit.avatar(name[0], tone === "off" ? "muted" : "them"));
    const t = kit.h("div", "pd-group-roster__t");
    t.append(kit.h("b", "", name), kit.h("i", "", org));
    r.appendChild(t);
    const b = kit.h("b", "pd-group-inv" + (tone ? ` is-${tone}` : ""), badge);
    r.appendChild(b);
    el.appendChild(r);
    return Object.assign(r, { badge: b });
  });
  parent.appendChild(el);
  return { el, rows };
}

/* 状态牌翻面：文字换掉 + 轻微弹一下（tone: sent 琥珀待确认 / done 霓虹已完成 / off 灰） */
function setBadge(gsap, kit, row, text, tone = "done") {
  const t = gsap.timeline();
  t.call(() => {
    row.badge.textContent = text;
    row.badge.className = `pd-group-inv is-${tone}`;
    row.classList.add(`is-${tone}`);
  }).fromTo(row.badge, { scale: 0.88 }, { scale: 1, duration: 0.24, ease: "back.out(2.6)" });
  return t;
}

/* ── 勾选清单（退群前检查）：一行一条，逐条打勾 ── */
function checkList(kit, items, parent) {
  const el = kit.h("div", "pd-group-check");
  const rows = items.map((txt) => {
    const r = kit.h("div", "pd-group-check__r");
    r.append(kit.icon("check"), kit.h("span", "", txt));
    el.appendChild(r);
    return r;
  });
  parent.appendChild(el);
  return { el, rows };
}

const tick = (gsap, row) => {
  const t = gsap.timeline();
  t.call(() => row.classList.add("is-on")).fromTo(row, { x: -4 }, { x: 0, duration: 0.22, ease: "power2.out" });
  return t;
};

/* ── 群信息抽屉（自动打开，脚上不是按钮而是一条「工作流执行中」状态）── */
function infoSheet(kit, { title = "群信息", fields = [], count = 5, avs = ["我", "王", "李", "陈"] } = {}) {
  const sheet = kit.sheet({ title, cls: "pd-group-sheet pd-pushed" });
  const members = kit.h("div", "pd-group-members");
  const countEl = kit.h("i", "pd-group-members__k", `成员 · ${count}`);
  members.appendChild(countEl);
  avs.forEach((a, i) => members.appendChild(kit.avatar(a, i === 0 ? "me" : i % 2 ? "them" : "muted")));
  sheet.body.appendChild(members);
  const form = kit.form(fields, sheet.body);
  // 没有人来点「保存」：把按钮换成一条自动执行状态
  const run = kit.h("i", "pd-group-run", "工作流执行中 · 无人工");
  sheet.foot.replaceChildren(run);
  return { sheet, form, members, countEl, run, rows: form.rows };
}

/* ── 事件通知：外部系统把条件送进来（合同已签 / 排期到点 / 项目结项）── */
function eventToast(kit, { title, body }) {
  const t = kit.toast({ title, body, app: "WORKFLOW · 自动触发", width: 236 });
  t.el.classList.add("pd-group-toast");
  return t;
}

/* ── 会话头右侧的小牌（「默认群名」这类待办标记）── */
function headChip(kit, chat, text) {
  const el = kit.h("i", "pd-group-chip", text);
  chat.head.insertBefore(el, chat.more);
  return el;
}

/* ── 置顶公告条：左侧琥珀竖线 + 「群公告」小标 + 正文 ── */
function noticeBar(kit, text) {
  const el = kit.h("div", "pd-group-notice");
  el.appendChild(kit.icon("bell"));
  const t = kit.h("div", "pd-group-notice__txt");
  t.append(kit.h("i", "pd-group-notice__k", "群公告 · NOTICE"), kit.h("b", "pd-group-notice__t", text));
  el.appendChild(t);
  return el;
}

/* ── 聊天里的系统行（预建 + 先藏起来）：结果落定时再 pop 出来 ── */
function hiddenSys(gsap, kit, chat, html) {
  const p = kit.h("p", "pd-sys pd-group-sysline");
  p.innerHTML = html;
  chat.list.appendChild(p);
  gsap.set(p, { display: "none" });
  return p;
}

/* 预建 + 先藏起来的聊天行 */
function hiddenRow(gsap, chat, side, content, opts) {
  const r = chat.row(side, content, opts);
  gsap.set(r, { display: "none" });
  return r;
}

/* ───────────────────────── 场景 ───────────────────────── */

/* ── 修改本人群昵称 ──
      触发：被拉进一个新的客户群（系统行落地）。
      规则：{公司}-{姓名} 模板生成「星辰科技-小吴」。
      执行：群信息里「我在本群的昵称」自己改掉 → 昵称已规范 ── */
function groupMyNick({ gsap, kit, tl }) {
  const { chat } = clientChat(kit, {
    rows: 2,
    lines: [
      ["l", "方案什么时候能给我？", { name: "王总", av: "王" }],
      ["l", "我这边先同步排期", { name: "李经理", av: "李" }],
    ],
  });
  const strip = kit.scenario("刚被拉进新客户群 · 昵称还是网名");
  const flow = kit.workflow([
    { label: "加入新客户群", icon: "users" },
    { label: "按模板生成昵称", icon: "code" },
    { label: "自动改昵称", icon: "edit" },
  ]);
  const joinSys = hiddenSys(gsap, kit, chat, "你加入了群聊<b>星辰科技客户群</b>");
  const { sheet, rows, run } = infoSheet(kit, {
    fields: [["群名称", "星辰科技客户群"], ["我在本群的昵称", "追风少年"]],
  });
  const nick = rows[1];
  const ruleWrap = kit.h("div", "pd-group-inline");
  ruleWrap.appendChild(kit.h("i", "pd-group-inline__k", "命名模板 · RULE"));
  sheet.body.appendChild(ruleWrap);
  const rule = ruleBlock(kit, "{公司}-{姓名}", ruleWrap);
  gsap.set(ruleWrap, { opacity: 0, y: 6 });
  const doneSys = hiddenSys(gsap, kit, chat, "群昵称已自动改为<b>星辰科技-小吴</b>");

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 被拉进群：系统行落地，触发节点点亮
    .set(joinSys, { display: "block" }, 0.55)
    .add(kit.pop(joinSys), "<")
    .add(flow.step(0), "<")
    .add(kit.flash(joinSys, { color: "amber", duration: 0.5 }), "<")
    // ② 群信息自己弹开，模板自己生成昵称（没有光标、没有点击）
    .add(sheet.open(), ">+0.1")
    .add(flow.step(1), "<+0.2")
    .to(ruleWrap, { opacity: 1, y: 0, duration: 0.28 }, "<")
    .add(kit.type(rule.value, ME, { cps: 9 }), ">-0.05")
    // ③ 昵称字段自己改掉
    .add(flow.step(2), ">+0.2")
    .call(() => nick.classList.add("is-edit"), [], "<")
    .add(kit.scramble(nick.value, ME, { duration: 0.55 }), "<+0.05")
    .add(kit.flash(nick, { color: "amber", duration: 0.6 }), "<")
    .call(() => { run.textContent = "已完成 · 无人工"; run.classList.add("is-done"); }, [], ">+0.1")
    .add(sheet.close(), ">+0.25")
    .set(doneSys, { display: "block" }, ">-0.15")
    .add(kit.pop(doneSys), "<")
    .add(kit.flash(doneSys, { color: "neon", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已改昵称", { en: "NICKNAME" }), ">-0.35")
    .add(strip.result("昵称已规范"), "<");
  return tl;
}

/* ── 发布群公告 ──
      触发：运营排期到点（发布会前 24 小时）。
      AI：把排期写成一条群公告。
      执行：自动发布置顶公告 + 一条 @所有人 → 全员已 @ 到 ── */
function groupNotice({ gsap, kit, tl }) {
  const TEXT = "周六 10:00 新品发布会，请准时参加";
  // 只留一条上下文：置顶公告条 + @所有人 那条都要落进来，多一行就把公告条挤出可视区
  const { chat } = clientChat(kit, {
    rows: 1,
    lines: [["l", "发布会到底几点？群里刷过去了", { name: "王总", av: "王" }]],
  });
  const strip = kit.scenario("排期到点 · 通知要全员看到");
  const flow = kit.workflow([
    { label: "活动排期到点", icon: "clock" },
    { label: "生成公告", ai: true },
    { label: "自动发布并 @所有人", icon: "at" },
  ]);
  const toast = eventToast(kit, { title: "运营排期", body: "周六 10:00 新品发布会 · 提前通知" });
  const panel = autoPanel(kit, gsap, { kicker: "AI", title: "公告拟稿" });
  const draft = kit.h("p", "pd-group-draft", "");
  panel.body.appendChild(draft);
  panel.body.appendChild(kit.h("i", "pd-group-inline__k", "提醒方式 · @所有人"));

  const bar = noticeBar(kit, TEXT);
  chat.list.insertBefore(bar, chat.list.firstChild);
  gsap.set(bar, { display: "none" });
  const bub = kit.bubble("", "r");
  bub.innerHTML = `<b class="pd-group-at">@所有人</b> ${TEXT}`;
  const at = hiddenRow(gsap, chat, "r", bub, { name: ME });
  at.body.appendChild(kit.tag("自动发布"));

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 排期系统把条件送进来
    .add(toast.show(), 0.5)
    .add(flow.step(0), "<+0.1")
    // ② AI 拟稿：通知先退场（同在右上角，两块面板不叠），字自己出现在拟稿卡上
    .add(toast.hide(), ">+0.75")
    .add(panel.in(), ">-0.05")
    .add(flow.step(1), "<")
    .add(kit.type(draft, TEXT, { cps: 13 }), "<+0.15")
    // ③ 自动发布：置顶公告条 + 一条 @所有人
    .add(flow.step(2), ">+0.3")
    .add(panel.out(), "<+0.1")
    .set(bar, { display: "flex" }, ">-0.1")
    .add(kit.pop(bar), "<")
    .set(at, { display: "flex" }, "<+0.3")
    .add(kit.pop(at), "<")
    .add(kit.flash(at.content, { color: "neon", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已发布", { en: "PUBLISHED" }), ">-0.35")
    .add(strip.result("全员已 @ 到"), "<");
  return tl;
}

/* ── 新建群聊 ──
      触发：合同状态翻成「已签」。
      组建：按角色把客户方与我方的人凑齐。
      执行：自动建群，会话栏顶上多一个服务群 → 服务群已建 ── */
function groupCreate({ gsap, kit, tl }) {
  const NEW = "星辰科技 · 服务群";
  const { chat } = clientChat(kit, {
    title: "客户 · 王总",
    group: false,
    rails: ["客户 · 王总", "星辰科技客户群", "李经理", "订单群"],
    time: "今天 15:40",
    rows: 2,
    lines: [
      ["l", "合同我签好了，款今天打", { av: "王" }],
      ["l", "后续谁跟我对接？", { av: "王" }],
    ],
  });
  const strip = kit.scenario("合同状态 = 已签");
  const flow = kit.workflow([
    { label: "合同状态 = 已签", icon: "check" },
    { label: "组建成员", icon: "users" },
    { label: "自动建群", icon: "plus" },
  ]);
  const toast = eventToast(kit, { title: "合同系统", body: "合同 #2043 · 星辰科技 已签署" });
  const panel = autoPanel(kit, gsap, { kicker: "ROSTER", title: "服务群成员" });
  const list = roster(kit, [
    ["王总", "客户 · 决策人", "待拉入"],
    ["李经理", "客户 · 对接人", "待拉入"],
    ["张工", "我方 · 技术", "待拉入"],
  ], panel.body);

  const sess = kit.h("div", "pd-sess pd-group-sess is-active");
  sess.appendChild(kit.avatarGrid(["我", "王", "李", "张"]));
  const txt = kit.h("div", "pd-sess__txt");
  txt.append(kit.h("b", "", NEW), kit.skel(58, 5));
  sess.appendChild(txt);
  chat.rail.insertBefore(sess, chat.sessions[0]);
  gsap.set(sess, { display: "none" });
  const sys = kit.h("p", "pd-sys pd-group-sysline");
  sys.innerHTML = "群聊已创建，已邀请<b>王总</b>、<b>李经理</b>、<b>张工</b>加入";

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 合同系统把条件送进来
    .add(toast.show(), 0.5)
    .add(flow.step(0), "<+0.1")
    // ② 成员自己按角色凑齐（没有勾选器、没有人点「完成」）；通知先退场，两块面板不叠
    .add(toast.hide(), ">+0.7")
    .add(panel.in(), ">-0.05")
    .add(flow.step(1), "<");
  list.rows.forEach((r, i) => tl.add(setBadge(gsap, kit, r, "已选", "done"), i === 0 ? ">+0.15" : ">+0.24"));
  tl
    // ③ 群自己建好：会话栏顶上多一个，标题落定，系统行成立
    .add(flow.step(2), ">+0.3")
    .add(panel.out(), "<+0.1")
    .addLabel("made", ">-0.05")
    .call(() => chat.sessions[0].classList.remove("is-active"), [], "made")
    .set(sess, { display: "flex" }, "made")
    .add(kit.pop(sess), "made")
    .add(kit.flash(sess, { color: "amber", duration: 0.7 }), "made")
    .call(() => { chat.list.replaceChildren(sys); chat.list.classList.remove("pd-group-bottom"); chat.list.classList.add("pd-group-emptied"); }, [], "made")
    .add(kit.pop(sys), "made+=0.08")
    .call(() => chat.title.classList.add("pd-group-hit"), [], "made")
    .add(kit.scramble(chat.title, NEW, { duration: 0.55 }), "made")
    .add(kit.flash(sys, { color: "neon", duration: 0.7 }), "made+=0.5")
    .add(flow.done(), "<")
    .add(kit.ok("已建群", { en: "CREATED" }), ">-0.3")
    .add(strip.result("服务群已建"), "<");
  return tl;
}

/* ── 修改群名称 ──
      触发：新群还挂着默认群名「王总、李经理」。
      规则：{客户公司} × {群类型}。
      执行：标题与会话栏一起改掉 → 群名已规范 ── */
function groupRename({ gsap, kit, tl }) {
  const OLD = "王总、李经理";
  const NEW = "星辰科技 × 客户服务群";
  const { chat } = clientChat(kit, {
    title: OLD,
    rails: [OLD, "星辰科技客户群", "李经理", "订单群"],
    rows: 2,
    lines: [
      ["l", "这么多群，哪个是我们的？", { name: "王总", av: "王" }],
      ["l", "我也老找错群", { name: "李经理", av: "李" }],
    ],
  });
  const sessName = chat.sessions[0].querySelector("b");
  const strip = kit.scenario("新群还挂着默认群名");
  const flow = kit.workflow([
    { label: "新群待命名", icon: "bolt" },
    { label: "套用命名规则", icon: "code" },
    { label: "自动改名", icon: "edit" },
  ]);
  const chip = headChip(kit, chat, "默认群名");
  gsap.set(chip, { opacity: 0, scale: 0.9 });
  const panel = autoPanel(kit, gsap, { kicker: "RULE", title: "群名规则" });
  const rule = ruleBlock(kit, "{客户公司} × {群类型}", panel.body);
  const sys = hiddenSys(gsap, kit, chat, `群名称已自动改为<b>${NEW}</b>`);

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 待办被识别出来：标题旁挂一枚「默认群名」
    .to(chip, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2)" }, 0.55)
    .add(flow.step(0), "<")
    .add(kit.flash(chip, { color: "amber", duration: 0.5 }), "<")
    // ② 规则自己算出新群名
    .add(panel.in(), ">+0.4")
    .add(flow.step(1), "<")
    .add(kit.type(rule.value, NEW, { cps: 10 }), "<+0.2")
    // ③ 标题与会话栏一起落定
    .add(flow.step(2), ">+0.45")
    .add(panel.out(), "<+0.1")
    .call(() => { chat.title.classList.add("pd-group-hit"); sessName.classList.add("pd-group-hit"); }, [], ">-0.1")
    .add(kit.scramble(chat.title, NEW, { duration: 0.55 }), ">-0.05")
    .add(kit.scramble(sessName, NEW, { duration: 0.55 }), "<+0.12")
    .add(kit.flash(chat.sessions[0], { color: "amber", duration: 0.7 }), "<")
    .to(chip, { opacity: 0, scale: 0.9, duration: 0.25 }, "<+0.3")
    .set(sys, { display: "block" }, ">-0.15")
    .add(kit.pop(sys), "<")
    .add(kit.flash(sys, { color: "neon", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已改名", { en: "RENAMED" }), ">-0.35")
    .add(strip.result("群名已规范"), "<");
  return tl;
}

/* ── 拉好友进群 ──
      触发：客户在群里提到技术问题。
      AI：在值班表里匹配今天的值班技术。
      执行：直接把人拉进群，他立刻在群里接话 → 技术已进群。
      与「邀请群成员」的区别：这里是一步拉进来，人当场就在群里说话了 ── */
function groupAddMembers({ gsap, kit, tl }) {
  const { chat } = clientChat(kit, {
    rows: 1,
    lines: [["l", "今天的对接单我发群里了", { name: "李经理", av: "李" }]],
  });
  const strip = kit.scenario("群里提到技术问题 · 无人接");
  const flow = kit.workflow([
    { label: "群内提到技术问题", icon: "bolt" },
    { label: "匹配值班技术", ai: true },
    { label: "自动拉进群", icon: "users" },
  ]);
  const ask = hiddenRow(gsap, chat, "l", "接口一直报错，你们看下", { name: "王总", av: "王" });
  const panel = autoPanel(kit, gsap, { kicker: "AI", title: "值班匹配" });
  const list = roster(kit, [
    ["张工", "技术 · 今日值班", "匹配中"],
    ["陈会计", "财务 · 不相关", "—", "off"],
    ["赵主管", "采购 · 不相关", "—", "off"],
  ], panel.body);
  const sys = hiddenSys(gsap, kit, chat, "工作流已把<b>张工</b>拉进群聊");
  const reply = hiddenRow(gsap, chat, "l", "我看下日志，5 分钟内回", { name: "张工", av: "张" });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 客户的问题进来，规则命中
    .set(ask, { display: "flex" }, 0.5)
    .add(kit.pop(ask), "<")
    .add(flow.step(0), "<")
    .add(kit.flash(ask.content, { color: "amber", duration: 0.6 }), "<")
    // ② AI 在值班表里挑人
    .add(panel.in(), ">+0.2")
    .add(flow.step(1), "<")
    .add(setBadge(gsap, kit, list.rows[0], "今日值班", "done"), ">+0.45")
    .add(kit.flash(list.rows[0], { color: "neon", duration: 0.6 }), "<")
    // ③ 直接拉进群，人当场接话
    .add(flow.step(2), ">+0.3")
    .add(panel.out(), "<+0.1")
    .set(sys, { display: "block" }, ">-0.1")
    .add(kit.pop(sys), "<")
    .set(reply, { display: "flex" }, ">+0.15")
    .add(kit.pop(reply), "<")
    .add(kit.flash(reply.content, { color: "neon", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已入群", { en: "MEMBER ADDED" }), ">-0.35")
    .add(strip.result("技术已进群"), "<");
  return tl;
}

/* ── 邀请群成员 ──
      触发：名单比群成员多，还有人没进群。
      执行：按名单逐个发邀请，状态停在「已邀请 · 待确认」→ 邀请已发出。
      与「拉好友进群」的区别：这里谁也没进群，等的是对方点确认 ── */
function groupInviteMembers({ gsap, kit, tl }) {
  const { chat } = clientChat(kit, {
    rows: 2,
    lines: [
      ["l", "财务和采购也拉进来吧", { name: "王总", av: "王" }],
      ["l", "名单我早上发过了", { name: "李经理", av: "李" }],
    ],
  });
  const strip = kit.scenario("名单 4 人 · 群里只有 2 个");
  const flow = kit.workflow([
    { label: "名单里还有人没进群", icon: "users" },
    { label: "逐个自动邀请", icon: "send" },
  ]);
  const panel = autoPanel(kit, gsap, { kicker: "ROSTER", title: "入群名单 · 4" });
  const list = roster(kit, [
    ["王总", "客户 · 决策人", "已在群", "off"],
    ["李经理", "客户 · 对接人", "已在群", "off"],
    ["陈会计", "财务 · 未加入", "待邀请"],
    ["赵主管", "采购 · 未加入", "待邀请"],
  ], panel.body);
  const sys = hiddenSys(gsap, kit, chat, '已向<b>陈会计</b>、<b>赵主管</b>发出入群邀请<i class="pd-tag">等待对方确认</i>');

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 名单和群成员一比，缺两个
    .add(panel.in(), 0.5)
    .add(flow.step(0), "<")
    .add(kit.flash(list.rows[2], { color: "amber", duration: 0.55 }), ">+0.1")
    .add(kit.flash(list.rows[3], { color: "amber", duration: 0.55 }), "<+0.12")
    // ② 一人一封，逐个发出去；状态停在「已邀请」而不是「已进群」
    .add(flow.step(1), ">+0.15")
    .add(setBadge(gsap, kit, list.rows[2], "邀请中", "sent"), "<+0.1")
    .add(setBadge(gsap, kit, list.rows[2], "已邀请", "sent"), ">+0.35")
    .add(setBadge(gsap, kit, list.rows[3], "邀请中", "sent"), ">+0.1")
    .add(setBadge(gsap, kit, list.rows[3], "已邀请", "sent"), ">+0.35")
    .add(panel.out(), ">+0.35")
    .set(sys, { display: "block" }, ">-0.1")
    .add(kit.pop(sys), "<")
    .add(kit.flash(sys, { color: "amber", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已发出", { en: "INVITE SENT" }), ">-0.35")
    .add(strip.result("邀请已发出"), "<");
  return tl;
}

/* ── 移除群成员 ──
      触发：一条消息命中广告关键词。
      AI：判定为广告推广。
      执行：把这个号移出群聊，广告行折叠消失 → 广告号已清退 ── */
function groupRemoveMembers({ gsap, kit, tl }) {
  const { chat } = clientChat(kit, {
    rows: 1,
    lines: [["l", "群里怎么天天发广告？", { name: "王总", av: "王" }]],
  });
  const strip = kit.scenario("客户群里混进广告号");
  const flow = kit.workflow([
    { label: "命中广告关键词", icon: "bolt" },
    { label: "判定为广告", ai: true },
    { label: "自动移除", icon: "trash" },
  ]);
  const ad = hiddenRow(gsap, chat, "l", "【广告】加我领优惠券，日结佣金", { name: "优惠券小助手", av: "优" });
  const panel = autoPanel(kit, gsap, { kicker: "AI", title: "广告判定" });
  const words = ["领优惠券", "日结佣金", "加我"];
  const chips = kit.chips([], { parent: panel.body });
  const chipEls = words.map((w) => { const c = chips.add(w); c.classList.add("pd-chip--dim"); return c; });
  const verdict = kit.h("div", "pd-group-verdict");
  verdict.append(kit.h("i", "", "广告推广"), kit.h("b", "", "置信度 98%"));
  panel.body.appendChild(verdict);
  gsap.set(verdict, { opacity: 0, y: 5 });
  const sys = hiddenSys(gsap, kit, chat, "工作流已将<b>优惠券小助手</b>移出群聊");

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 广告消息进来，关键词命中
    .set(ad, { display: "flex" }, 0.5)
    .add(kit.pop(ad), "<")
    .add(flow.step(0), "<")
    .add(kit.flash(ad.content, { color: "amber", duration: 0.6 }), "<")
    // ② AI 逐个点亮命中的词，给出判定
    .add(panel.in(), ">+0.3")
    .add(flow.step(1), "<");
  chipEls.forEach((c, i) => tl.add(kit.pop(c, { y: 4 }), i === 0 ? "<+0.2" : ">-0.14").call(() => c.classList.add("is-hit"), [], ">-0.1"));
  tl.to(verdict, { opacity: 1, y: 0, duration: 0.32 }, ">+0.05")
    // ③ 广告号被移出，那条广告从群里消失
    .add(flow.step(2), ">+0.45")
    .add(panel.out(), "<+0.1")
    .add(kit.flash(ad.content, { color: "red", duration: 0.5 }), "<")
    .set(ad, { overflow: "hidden" }, ">-0.1")
    .add(kit.collapse(ad), "<")
    .set(sys, { display: "block" }, ">-0.1")
    .add(kit.pop(sys), "<")
    .add(kit.flash(sys, { color: "neon", duration: 0.7 }), "<")
    .add(flow.done(), "<")
    .add(kit.ok("已清退", { en: "REMOVED" }), ">-0.35")
    .add(strip.result("广告号已清退"), "<");
  return tl;
}

/* ── 退出群聊 ──
      触发：项目看板把状态翻成「已结项」。
      执行：退群前先自查（没人 @ 我、记录已归档），然后自己退掉 → 已退出 ── */
function groupLeave({ gsap, kit, tl }) {
  const TITLE = "星辰科技 Q3 项目群";
  const { chat } = clientChat(kit, {
    title: TITLE,
    rails: [TITLE, "星辰科技客户群", "王总", "李经理"],
    time: "今天 18:20",
    rows: 2,
    lines: [
      ["l", "Q3 项目已验收结项", { name: "李经理", av: "李" }],
      ["l", "感谢各位配合", { name: "王总", av: "王" }],
    ],
  });
  const strip = kit.scenario("项目结项 · 群留着只会天天弹");
  const flow = kit.workflow([
    { label: "项目状态 = 已结项", icon: "check" },
    { label: "自动退群", icon: "undo" },
  ]);
  const toast = eventToast(kit, { title: "项目看板", body: "Q3 项目 #08 · 验收通过，已结项" });
  const panel = autoPanel(kit, gsap, { kicker: "CHECK", title: "退群前自查" });
  const checks = checkList(kit, ["没有 @ 我的未读", "聊天记录已归档", "无待办事项"], panel.body);
  const left = kit.h("p", "pd-sys pd-group-left");
  left.innerHTML = `你已退出<b>${TITLE}</b>`;

  tl.add(strip.in(), 0.05)
    .add(flow.in(), "<+0.1")
    // ① 项目看板把条件送进来
    .add(toast.show(), 0.5)
    .add(flow.step(0), "<+0.1")
    // ② 退群前自查：通知先退场（同在右上角），三条自己打勾
    .add(toast.hide(), ">+0.75")
    .add(panel.in(), ">-0.05")
    .add(flow.step(1), "<");
  checks.rows.forEach((r, i) => tl.add(tick(gsap, r), i === 0 ? ">-0.05" : ">+0.24"));
  tl.add(panel.out(), ">+0.35")
    // ③ 会话从列表里消失，聊天区只剩一行「你已退出」
    .set(chat.sessions[0], { overflow: "hidden" }, ">-0.15")
    .add(kit.collapse(chat.sessions[0]), "<")
    .call(() => {
      chat.sessions[0].classList.remove("is-active");
      chat.sessions[1].classList.add("is-active");
      chat.list.classList.remove("pd-group-bottom");
      chat.list.classList.add("pd-group-emptied");
      chat.list.replaceChildren(left);
    }, [], ">-0.1")
    .add(kit.pop(left), "<")
    .to([chat.head, chat.input], { opacity: 0.32, duration: 0.35 }, "<")
    .add(flow.done(), "<")
    .add(kit.ok("已退出群聊", { en: "LEFT GROUP" }), ">-0.15")
    .add(strip.result("已退出"), "<");
  return tl;
}

export default {
  "group-my-nick": groupMyNick,
  "group-notice": groupNotice,
  "group-create": groupCreate,
  "group-rename": groupRename,
  "group-add-members": groupAddMembers,
  "group-invite-members": groupInviteMembers,
  "group-remove-members": groupRemoveMembers,
  "group-leave": groupLeave,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* 被改动的文字：琥珀高亮（群标题 / 会话名） */
.pd-screen .pd-chat__title.pd-group-hit,
.pd-screen .pd-sess__txt b.pd-group-hit { color: var(--pd-amber); text-shadow: 0 0 8px rgba(255, 194, 75, 0.4); }

/* 业务群名比私人群名长：会话栏加宽 + 字号收一档，「星辰科技 × 客户服务群」不被截断 */
.pd-screen .pd-chat.pd-group-c { grid-template-columns: 182px minmax(0, 1fr); }
.pd-screen .pd-group-c .pd-sess__txt b { font-size: 10.5px; }
/* 消息贴着输入条堆叠：右上角的自动化面板压不到最新那几条 */
.pd-screen .pd-chat__list.pd-group-bottom { justify-content: flex-end; }

/* 会话头右侧的待办小牌（「默认群名」） */
.pd-group-chip {
  font-family: var(--pd-mono); font-style: normal; font-size: 9px; letter-spacing: 0.12em;
  padding: 2px 6px 1px; margin-left: auto; margin-right: 9px; border-radius: 2px; white-space: nowrap;
  color: var(--pd-amber); background: rgba(255, 194, 75, 0.1); border: 1px solid rgba(255, 194, 75, 0.45);
}

/* ── 自动化面板：工作流的工作台，右上角浮层；没有按钮，因为没有人来点 ── */
.pd-group-auto {
  position: absolute; right: 14px; top: 44px; z-index: 22; width: 218px;
  background: #0f1612; border: 1px solid var(--pd-line-strong); border-radius: 5px;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.6); overflow: hidden;
}
.pd-group-auto__h { display: flex; align-items: center; gap: 7px; padding: 7px 10px; border-bottom: 1px solid var(--pd-line); }
.pd-group-auto__k {
  flex: none; font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; font-weight: 700; letter-spacing: 0.14em;
  padding: 2px 5px 1px; border-radius: 2px; color: #140d01; background: var(--pd-amber);
}
.pd-group-auto__h b { font-size: 11.5px; font-weight: 500; color: var(--pd-ink); white-space: nowrap; }
.pd-group-auto__b { padding: 9px 10px 10px; display: flex; flex-direction: column; gap: 7px; }

/* 规则块：mono 模板 → 生成结果 */
.pd-group-rule { display: flex; flex-direction: column; gap: 5px; }
.pd-group-rule__p {
  font-family: var(--pd-mono); font-style: normal; font-size: 10px; letter-spacing: 0.04em; color: var(--pd-dim);
  padding: 4px 7px; border-radius: 3px; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--pd-line);
}
.pd-group-rule__r { display: flex; align-items: center; gap: 6px; min-height: 16px; }
.pd-group-rule__a { flex: none; font-size: 11px; color: var(--pd-faint); }
.pd-group-rule__v { font-size: 12px; font-weight: 500; color: var(--pd-amber); }
.pd-group-rule__v.is-typing::after {
  content: ""; display: inline-block; width: 1px; height: 12px; background: var(--pd-amber);
  margin-left: 1px; vertical-align: -2px; animation: pdBlink 0.9s steps(2) infinite;
}

/* AI 拟稿正文 */
.pd-root .pd-group-draft { margin: 0; font-size: 11.5px; line-height: 1.55; color: var(--pd-ink); min-height: 34px; }
.pd-group-draft.is-typing::after {
  content: ""; display: inline-block; width: 1px; height: 12px; background: var(--pd-amber);
  margin-left: 1px; vertical-align: -2px; animation: pdBlink 0.9s steps(2) infinite;
}
.pd-group-inline { display: flex; flex-direction: column; gap: 6px; }
.pd-group-inline__k { font-family: var(--pd-mono); font-style: normal; font-size: 9.5px; letter-spacing: 0.16em; color: var(--pd-faint); }

/* AI 判定结论 */
.pd-group-verdict {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 5px 8px; border-radius: 3px;
  background: rgba(255, 93, 93, 0.08); border: 1px solid rgba(255, 93, 93, 0.4);
}
.pd-group-verdict i { font-style: normal; font-size: 11.5px; color: var(--pd-red); }
.pd-group-verdict b { font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.1em; color: var(--pd-red); opacity: 0.85; }

/* 名单：一人一行，右侧状态牌（待邀请 → 已邀请 / 已选 / 已在群） */
.pd-group-roster { display: flex; flex-direction: column; gap: 5px; }
.pd-group-roster__r {
  display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 3px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid transparent;
}
.pd-group-roster__r .pd-av { width: 22px; height: 22px; font-size: 9.5px; border-radius: 3px; flex: none; }
.pd-group-roster__t { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1 1 auto; }
.pd-group-roster__t b { font-size: 11.5px; font-weight: 500; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-group-roster__t i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.08em; color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-group-inv {
  flex: none; font-family: var(--pd-mono); font-size: 9px; font-weight: 500; letter-spacing: 0.08em;
  padding: 2px 6px 1px; border-radius: 2px; white-space: nowrap;
  color: var(--pd-amber); background: rgba(255, 194, 75, 0.1); border: 1px solid rgba(255, 194, 75, 0.45);
}
.pd-group-inv.is-off { color: var(--pd-faint); background: transparent; border-color: var(--pd-line); }
.pd-group-inv.is-sent { color: var(--pd-amber); background: rgba(255, 194, 75, 0.16); border-color: rgba(255, 194, 75, 0.7); }
.pd-group-inv.is-done { color: var(--pd-neon); background: rgba(61, 242, 141, 0.12); border-color: rgba(61, 242, 141, 0.5); }
.pd-group-roster__r.is-done { border-color: rgba(61, 242, 141, 0.28); background: rgba(61, 242, 141, 0.05); }
.pd-group-roster__r.is-sent { border-color: rgba(255, 194, 75, 0.28); background: rgba(255, 194, 75, 0.05); }

/* 退群前自查：三条逐条打勾 */
.pd-group-check { display: flex; flex-direction: column; gap: 6px; }
.pd-group-check__r { display: flex; align-items: center; gap: 7px; font-size: 11px; color: var(--pd-faint); }
.pd-group-check__r .pd-ic { width: 12px; height: 12px; flex: none; color: var(--pd-line-strong); stroke-width: 2.4; }
.pd-group-check__r.is-on { color: var(--pd-ink); }
.pd-group-check__r.is-on .pd-ic { color: var(--pd-neon); }

/* 群信息抽屉：标签列窄一点；脚上不是按钮，是一条「工作流执行中」 */
.pd-group-sheet .pd-field { grid-template-columns: 92px minmax(0, 1fr); gap: 8px; }
.pd-group-members { display: flex; align-items: center; gap: 6px; padding: 2px 0 4px; }
.pd-group-members .pd-av { width: 24px; height: 24px; font-size: 10px; border-radius: 3px; }
.pd-group-members__k { font-family: var(--pd-mono); font-style: normal; font-size: 9.5px; letter-spacing: 0.2em; color: var(--pd-faint); margin-right: 6px; white-space: nowrap; }
.pd-group-run {
  display: flex; align-items: center; gap: 6px; font-family: var(--pd-mono); font-style: normal;
  font-size: 9.5px; letter-spacing: 0.12em; color: var(--pd-amber);
}
.pd-group-run::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--pd-amber); box-shadow: 0 0 8px rgba(255, 194, 75, 0.8); }
.pd-group-run.is-done { color: var(--pd-neon); }
.pd-group-run.is-done::before { background: var(--pd-neon); box-shadow: 0 0 8px rgba(61, 242, 141, 0.8); }

/* 事件通知：情境条占了顶端 22px，通知条跟着往下让 */
.pd-screen.has-strip .pd-group-toast { top: 32px; }

/* 置顶公告条：左侧琥珀竖线 + 小标 + 正文 */
.pd-group-notice {
  display: flex; align-items: flex-start; gap: 8px; padding: 6px 10px 7px 9px; border-radius: 3px;
  background: rgba(255, 194, 75, 0.06); border: 1px solid rgba(255, 194, 75, 0.26); border-left: 2px solid var(--pd-amber);
}
.pd-group-notice .pd-ic { width: 13px; height: 13px; color: var(--pd-amber); margin-top: 2px; }
.pd-group-notice__txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pd-group-notice__k { font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.2em; color: var(--pd-amber); }
.pd-group-notice__t { font-size: 11.5px; font-weight: 500; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 公告气泡里的「@所有人」：琥珀提亮 */
.pd-screen .pd-group-at { color: var(--pd-amber); font-weight: 600; }

/* 新建群聊：会话栏顶上多出来的那一条 */
.pd-group-sess { padding: 6px 2px 6px 4px; }

/* 系统行：收窄到文字宽度居中，kit.flash 的光环才不会横贯整行 */
.pd-group-sysline { align-self: center; max-width: 92%; }

/* 退群之后：聊天区只剩一行「你已退出」，居中 */
.pd-group-emptied { justify-content: center; }
.pd-screen .pd-group-left b { color: var(--pd-amber); font-weight: 500; }
`;
