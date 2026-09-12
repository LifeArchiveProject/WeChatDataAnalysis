/* ════════════════════════════════════════════════════════════
   scenes / contact.js — 联系人（4 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   这一组是**真实动作类**（经微信客户端改联系人，对方看得到），所以：
   - 一律 kit.workflow([触发, (AI), 执行]) 立一条底轨，随剧情 flow.step(i) 逐步点亮；
   - 画面里**没有人**：不用 kit.cursor，没有点按钮、没有手打字，内容自己出现、自己执行；
   - 自动产生的东西挂小标（AI 生成 / 投放线索 / 规则自动执行），静止帧里也看得出不是人做的；
   - 不用 { local: true }（那是本地存档类的标）。
   情境条讲「什么条件触发了它」，strip.result() 讲「省了什么事」，配 kit.ok() 印章停 0.9s。

   统一叙事：使用者是做客户获取与维护的人——投放来的申请自动通过，备注按来源自动规范，
   僵尸粉按规则自动清，老客户名单逐个自动发申请。

   两张脸（都是自建布局根，必须带 pd-pushed 让出顶端 22px 情境条与底端 24px 工作流轨）：
   - 通讯录 .pd-contact：左 190px 名单（可带状态小字）+ 右侧资料卡（大头像 / 昵称 / 字段 / 附加块）
   - 新的朋友 .pd-contact-req：左 340px 申请列表 + 右侧空会话区，通过后聊天窗从右滑入
   ════════════════════════════════════════════════════════════ */

/* ── 通讯录/名单布局：rows 每行可给 note（状态小字）代替骨架条 ── */
function addressBook(kit, {
  head = "联系人资料",
  cap = null,
  rows = [],
  hero = { av: "王", nick: "王总" },
  fields = [],
  actions = [],
} = {}) {
  const el = kit.h("div", "pd-contact pd-pushed");

  // 左：名单
  const rail = kit.h("aside", "pd-contact__rail");
  const capEl = cap ? kit.h("p", "pd-contact__cap", cap) : null;
  if (capEl) rail.appendChild(capEl);
  rail.appendChild(kit.h("i", "pd-contact__search"));
  const list = kit.h("div", "pd-sessions");
  const rowEls = rows.map((o, i) => {
    const r = kit.h("div", "pd-sess" + (o.active ? " is-active" : ""));
    r.appendChild(kit.avatar(o.av ?? o.name[0], o.tone ?? (i % 2 ? "muted" : "them")));
    const txt = kit.h("div", "pd-sess__txt");
    const nameEl = kit.h("b", "", o.name);
    const noteEl = o.note != null
      ? kit.h("i", "pd-contact__note" + (o.noteCls ? " " + o.noteCls : ""), o.note)
      : kit.skel(46 + ((i * 17) % 30), 5);
    txt.append(nameEl, noteEl);
    r.appendChild(txt);
    list.appendChild(r);
    return Object.assign(r, { name: nameEl, note: noteEl });
  });
  rail.appendChild(list);
  el.appendChild(rail);

  // 右：资料卡
  const main = kit.h("div", "pd-contact__main");
  const headEl = kit.h("header", "pd-contact__head");
  headEl.append(kit.h("b", "", head), kit.icon("dots", "pd-ic pd-contact__more"));
  const card = kit.h("div", "pd-contact__card");
  const heroEl = kit.h("div", "pd-contact__hero");
  const heroTxt = kit.h("div", "pd-contact__hero-txt");
  const remarkBig = kit.h("b", "pd-contact__remark", "");
  const nick = kit.h("b", "pd-contact__name", hero.nick);
  heroTxt.append(remarkBig, nick);
  heroEl.append(kit.avatar(hero.av, "them"), heroTxt);
  card.appendChild(heroEl);
  const form = kit.form(fields, card);
  const actionRow = kit.h("div", "pd-contact__actions");
  const btns = actions.map(([t, tone]) => kit.btn(t, tone, actionRow));
  if (actions.length) card.appendChild(actionRow);
  main.append(headEl, card);
  el.appendChild(main);
  kit.mount(el);
  return { el, cap: capEl, main, card, hero: heroEl, heroTxt, rows: rowEls, first: rowEls[0], remarkBig, nick, form, actions: actionRow, btns };
}

/* ── 「自动」小徽标：贴在被自动改写的字段行右端，静止帧里也看得出不是人打的 ── */
function autoTag(kit, gsap, field, text, cls = "") {
  field.classList.add("is-auto");
  const tag = kit.tag(text, cls);
  field.appendChild(tag);
  gsap.set(tag, { opacity: 0 });
  return tag;
}

/* ═══════════════ contact-remark 修改好友备注 · 新好友通过就自动规范 ═══════════════ */
/* 新好友通过 → AI 按来源拼出「抖音-王总-询价」→ 自动写入资料卡与名单，全程没有人 */
function contactRemark({ gsap, kit, tl }) {
  const REMARK = "抖音-王总-询价";
  const { el, main, first, card, remarkBig, nick, form } = addressBook(kit, {
    cap: "客户名单 · 216 人",
    rows: [
      { name: "王总2", av: "王", tone: "them", note: "刚通过 · 待备注", noteCls: "is-warn", active: true },
      { name: "抖音-李姐-已成交", av: "李", tone: "muted", note: "备注已规范", noteCls: "is-done" },
      { name: "朋友圈-陈总-询价", av: "陈", tone: "them", note: "备注已规范", noteCls: "is-done" },
      { name: "展会-刘工-待跟进", av: "刘", tone: "muted", note: "备注已规范", noteCls: "is-done" },
      { name: "视频号-赵总-已成交", av: "赵", tone: "them", note: "备注已规范", noteCls: "is-done" },
    ],
    hero: { av: "王", nick: "王总2" },
    fields: [["备注", "王总2"], ["微信号", "wxid_wang0416", true], ["来源", "抖音 · 广告线索"]],
  });
  el.classList.add("pd-contact-remark");
  // 新好友通过之前右边没有资料可看：先摆一个空态，通过那一刻淡出让资料卡顶上
  const empty = kit.h("div", "pd-contact__empty");
  empty.append(kit.icon("user"), kit.h("span", "", "等待新好友"));
  main.appendChild(empty);
  // 命名规则常驻显示：备注不是随手编的，是这条规则拼出来的
  const rule = kit.h("div", "pd-contact-rule");
  rule.append(kit.icon("ai"), kit.h("span", "", "命名规则 · 来源-姓名-需求"));
  card.appendChild(rule);

  const strip = kit.scenario("投放广告来的好友申请 · 等通过");
  const flow = kit.workflow([
    { label: "新好友通过", icon: "user" },
    { label: "按来源生成备注", ai: true },
    { label: "自动写入", icon: "edit" },
  ]);
  const remark = form.rows[0];
  const tag = autoTag(kit, gsap, remark, "AI 生成");
  gsap.set(remarkBig, { display: "none" });
  gsap.set(first, { display: "none" });
  gsap.set(card, { opacity: 0 });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：名单顶上多出刚通过的这一位，资料卡跟着打开 */
    .add(flow.step(0), 0.8)
    .set(first, { display: "flex" }, 0.8)
    .add(kit.pop(first), 0.8)
    .add(strip.say("新好友刚通过 · 备注还是微信昵称"), 0.85)
    .to(card, { opacity: 1, duration: 0.35 }, 0.9)
    .to(empty, { opacity: 0, duration: 0.3 }, 0.9)
    .add(kit.flash(first, { color: "amber", duration: 0.7 }), 0.85)
    /* ② AI：读「来源 = 抖音 · 广告线索」，按规则拼出规范备注 */
    .add(flow.step(1), 2.0)
    .call(() => remark.classList.add("is-edit"), [], 2.05)
    .add(kit.pop(tag), 2.1)
    .add(kit.scramble(remark.value, REMARK, { duration: 1.0 }), 2.15)
    /* ③ 执行：自动写入——资料卡大字落定、原昵称缩成小字、名单那行同步改名 */
    .add(flow.step(2), 3.5)
    .call(() => remark.classList.remove("is-edit"), [], 3.5)
    .set(remarkBig, { display: "block" }, 3.55)
    .add(kit.pop(remarkBig), 3.55)
    .add(kit.scramble(remarkBig, REMARK, { duration: 0.45 }), 3.55)
    .call(() => nick.classList.add("is-sub"), [], 3.55)
    .call(() => {
      first.name.classList.add("pd-contact-hit");
      first.note.classList.remove("is-warn");
      first.note.classList.add("is-done");
    }, [], 3.8)
    .add(kit.scramble(first.name, REMARK, { duration: 0.55 }), 3.8)
    .add(kit.scramble(first.note, "备注已规范", { duration: 0.45 }), 3.8)
    .add(kit.flash(first, { color: "neon", duration: 0.7 }), 3.8)
    /* 结尾整体提前：走片第 5 帧就要能读到印章与结果，不能只落在最后一帧 */
    .add(flow.done(), 3.95)
    .add(kit.ok("已写入 · remark", { hold: 1.4 }), 4.05)
    .add(strip.result("备注已规范"), 4.05);
  return tl;
}

/* ── 「新的朋友」布局：左申请列表 + 右空会话区 ── */
function newFriends(kit) {
  const el = kit.h("div", "pd-contact-req pd-pushed");
  const pane = kit.h("div", "pd-contact-req__pane");
  const head = kit.h("header", "pd-contact-req__head");
  const badge = kit.h("i", "pd-contact-req__badge", "1");
  head.append(kit.h("b", "", "新的朋友"), badge);
  const list = kit.h("div", "pd-contact-req__list");
  const mk = (name, av, tone, msg, btnText, btnTone) => {
    const r = kit.h("div", "pd-contact-req__row");
    const txt = kit.h("div", "pd-contact-req__txt");
    const nameEl = kit.h("b", "", name);
    const msgEl = kit.h("i", "", msg);
    txt.append(nameEl, msgEl);
    r.append(kit.avatar(av, tone), txt);
    const btn = kit.btn(btnText, btnTone, r);
    list.appendChild(r);
    return Object.assign(r, { name: nameEl, msg: msgEl, btn });
  };
  const rows = [
    mk("李姐", "李", "muted", "看了直播，想了解下套餐", "已添加", "ghost"),
    mk("陈总", "陈", "them", "朋友圈广告点进来的", "已添加", "ghost"),
    mk("王总", "王", "them", "看到广告，想咨询报价", "待处理", "amber"),
  ];
  // 更早的请求：两行骨架，只为把列表撑成一页
  list.appendChild(kit.h("i", "pd-contact-req__divider mono", "更早 · EARLIER"));
  for (let i = 0; i < 2; i++) {
    const r = kit.h("div", "pd-contact-req__row pd-contact-req__row--skel");
    const txt = kit.h("div", "pd-contact-req__txt");
    txt.append(kit.skel(38 + i * 10, 7), kit.skel(96 - i * 18, 5));
    r.append(kit.avatar("", "muted"), txt);
    kit.btn("已添加", "ghost", r);
    list.appendChild(r);
  }
  pane.append(head, list);
  const empty = kit.h("div", "pd-contact-req__empty");
  empty.append(kit.icon("chat"), kit.h("span", "", "未选择会话"));
  el.append(pane, empty);
  // 右侧 300px 聊天窗容器，初始藏在屏幕外
  const wrap = kit.h("div", "pd-contact-req__chat");
  el.appendChild(wrap);
  kit.mount(el);
  return { el, badge, rows, empty, wrap };
}

/* ═══════════════ contact-accept 同意好友请求 · 投放线索自动通过 ═══════════════ */
/* 申请进来 → AI 读验证消息判成投放线索 → 自动通过 → 会话滑入，客户当场把话接上 */
function contactAccept({ gsap, kit, tl }) {
  const { badge, rows, empty, wrap } = newFriends(kit);
  const row = rows[2], accept = row.btn;
  const chat = kit.chat({ title: "王总", rail: false, parent: wrap });
  const sys = chat.sys("你已添加了王总，现在可以开始聊天了");
  const first = chat.row("l", "报价单方便发我一份吗", { av: "王" });
  const strip = kit.scenario("22:40 · 广告点进来的申请");
  const flow = kit.workflow([
    { label: "收到好友申请", icon: "user" },
    { label: "判定为投放线索", ai: true },
    { label: "自动通过", icon: "check" },
  ]);
  // 验证消息上横扫一道光 = AI 正在读它；判完在行里挂一枚「投放线索」小标
  const scan = kit.h("i", "pd-contact-scan");
  const beam = kit.h("b");
  scan.appendChild(beam);
  row.appendChild(scan);
  const lead = kit.tag("投放线索", "pd-tag--neon");
  row.insertBefore(lead, accept);

  gsap.set(wrap, { xPercent: 100 });
  gsap.set([sys, first, row], { display: "none" });
  gsap.set([lead, badge], { opacity: 0 });
  gsap.set(badge, { scale: 0 });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：一条新申请落进列表，角标从 0 冒出来 */
    .add(flow.step(0), 0.65)
    .set(row, { display: "flex" }, 0.65)
    .add(kit.pop(row), 0.65)
    .to(badge, { scale: 1, opacity: 1, duration: 0.32, ease: "back.out(2.4)" }, 0.75)
    /* ② AI：把验证消息读一遍——「想咨询报价」，判成投放来的线索 */
    .add(flow.step(1), 1.35)
    .fromTo(beam, { xPercent: -120 }, { xPercent: 320, duration: 0.7, ease: "none", immediateRender: false }, 1.35)
    .add(kit.flash(row.msg, { color: "amber", duration: 0.6 }), 1.45)
    .add(kit.pop(lead), 2.15)
    /* ③ 执行：没有人点「接受」，按钮自己落成「已添加」 */
    .add(flow.step(2), 2.6)
    .call(() => { accept.classList.remove("pd-btn--amber"); accept.classList.add("pd-btn--neon"); }, [], 2.6)
    .add(kit.scramble(accept, "已添加", { duration: 0.45 }), 2.6)
    .add(kit.flash(row, { color: "neon", duration: 0.7 }), 2.6)
    .to(badge, { scale: 0, opacity: 0, duration: 0.3, ease: "back.in(2)" }, 2.65)
    .call(() => row.classList.add("is-active"), [], 2.85)
    /* 会话从右滑入，客户当场把话接上：线索没在半夜流失 */
    .to(wrap, { xPercent: 0, duration: 0.45, ease: "power3.out" }, 2.9)
    .to(empty, { opacity: 0, duration: 0.3 }, 2.9)
    .set(sys, { display: "block" }, 3.2)
    .add(kit.pop(sys), 3.2)
    .set(first, { display: "flex" }, 3.7)
    .add(kit.pop(first), 3.7)
    .add(kit.flash(first.content, { color: "neon", duration: 0.7 }), 3.8)
    /* 印章压在聊天输入条上：先把它压暗，收尾画面里不留半露的「发送」 */
    .to(chat.input, { opacity: 0.25, duration: 0.3 }, 3.85)
    /* 结尾提前：第 5 帧就要看得到印章与结果 */
    .add(flow.done(), 4.05)
    .add(kit.ok("已通过", { en: "AUTO ACCEPTED", hold: 1.45 }), 4.15)
    .add(strip.result("已自动通过"), 4.15);
  return tl;
}

/* ── 清理详情面板：不是「请你确认」，是规则跑到这一步的执行详情 ──
   判据一条条列出来并逐条落成「命中」，底栏只有一条执行状态，没有让人点的按钮 */
function autoCleanSheet(kit, gsap, { title, text, rules = [], icon = "trash" }) {
  const sheet = kit.sheet({ title, cls: "pd-contact-confirm" });
  const body = kit.h("div", "pd-contact-confirm__body");
  body.append(kit.icon(icon), kit.h("p", "", text));
  sheet.body.appendChild(body);
  sheet.body.appendChild(kit.h("i", "pd-contact-demo mono", "演示环境 · 不改动真实数据"));
  sheet.body.appendChild(kit.h("i", "pd-contact-rules__k mono", "清理判据 · RULE"));
  const list = kit.h("div", "pd-contact-rules");
  const ruleRows = rules.map(([label, value]) => {
    const r = kit.h("div", "pd-contact-rules__r");
    const flag = kit.h("b", "pd-contact-rules__f");
    flag.append(kit.icon("check"), kit.h("span", "", "命中"));
    r.append(kit.h("i", "", label), kit.h("em", "", value), flag);
    list.appendChild(r);
    return Object.assign(r, { flag });
  });
  sheet.body.appendChild(list);
  sheet.cancel.remove();
  sheet.ok.remove();
  sheet.head.querySelector(".pd-sheet__x")?.remove();   // 规则自动执行：连关闭叉都不该留
  const status = kit.h("b", "pd-contact-auto");
  status.append(kit.icon("bolt"), kit.h("span", "", "规则自动执行"));
  sheet.foot.appendChild(status);
  return Object.assign(sheet, { status, ruleRows });
}

/* ═══════════════ contact-delete 删除好友 · 僵尸粉按规则批量清 ═══════════════ */
/* 每周扫一遍名单 → 180 天零互动这一轮命中 7 人 → 执行详情列出判据 → 批量清掉，216 人变 209 人。
   演的是「一批」不是「一个」：进度条跑到 7、名单里两行先后塌掉、人数直接掉 7。 */
function contactDelete({ gsap, kit, tl }) {
  const { first, rows, cap, card, hero, heroTxt, form } = addressBook(kit, {
    cap: "客户名单 · 216 人",
    rows: [
      { name: "抖音-孙先生-未回", av: "孙", tone: "them", note: "180 天无互动", noteCls: "is-warn", active: true },
      { name: "抖音-李姐-已成交", av: "李", tone: "muted", note: "今天有往来" },
      { name: "朋友圈-陈总-询价", av: "陈", tone: "them", note: "2 天前" },
      { name: "抖音-周女士-未回", av: "周", tone: "muted", note: "213 天无互动", noteCls: "is-warn" },
      { name: "视频号-赵总-已成交", av: "赵", tone: "them", note: "5 天前" },
    ],
    hero: { av: "孙", nick: "抖音-孙先生-未回" },
    fields: [["最后互动", "180 天前"], ["往来消息", "0 条"], ["来源", "抖音 · 广告线索"]],
  });
  const zombie = rows[3];   // 名单里第二个命中的号，和 first 一前一后塌掉，批量才看得见
  const hit = kit.tag("命中清理规则 · 7 人之一", "pd-tag--red");
  heroTxt.appendChild(hit);
  gsap.set(hit, { opacity: 0 });

  // 批量进度：这一轮不是删一个人，是 7 个号一起清
  const prog = kit.h("div", "pd-contact-prog pd-contact-prog--red");
  const progN = kit.h("b", "", "0");
  const progTxt = kit.h("span", "");
  progTxt.append("已清理 ", progN, " / 7");
  const bar = kit.h("i", "pd-contact-prog__bar");
  const fill = kit.h("b");
  bar.appendChild(fill);
  prog.append(kit.h("i", "pd-contact-prog__k", "BATCH"), progTxt, bar);
  card.appendChild(prog);
  gsap.set(fill, { scaleX: 0 });
  gsap.set(prog, { opacity: 0 });

  const strip = kit.scenario("僵尸粉清理规则 · 每周跑一次");
  const flow = kit.workflow([
    { label: "180 天零互动", icon: "clock" },
    { label: "本轮命中 7 人", icon: "users" },
    { label: "批量清理", icon: "trash" },
  ]);
  const sheet = autoCleanSheet(kit, gsap, {
    title: "自动清理 · 执行详情",
    text: "本轮命中 7 人，从名单中移除；示例：抖音-孙先生-未回 等。",
    rules: [["最后互动", "≥ 180 天"], ["往来消息", "0 条"], ["近 30 天朋友圈", "0 次互动"]],
  });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：两条判据同时亮起——最后互动 180 天前、往来消息 0 条 */
    .add(flow.step(0), 0.6)
    .add(kit.flash(form.rows[0], { color: "amber", duration: 0.7 }), 0.65)
    .add(kit.flash(form.rows[1], { color: "amber", duration: 0.7 }), 0.78)
    .add(kit.pop(hit), 0.95)
    .add(kit.flash(first.note, { color: "amber", duration: 0.7 }), 1.0)
    .add(kit.flash(zombie.note, { color: "amber", duration: 0.7 }), 1.1)
    /* 执行详情面板：三条判据一条条落成「命中」，底下只有一条执行状态 */
    .add(sheet.open(), 1.15);
  sheet.ruleRows.forEach((r, i) => {
    tl.call(() => r.classList.add("is-on"), [], 1.75 + i * 0.23)
      .add(kit.pop(r.flag, { y: 0, duration: 0.26 }), 1.75 + i * 0.23);
  });
  tl.add(flow.step(1), 1.75)
    .call(() => sheet.status.classList.add("is-on"), [], 2.5)
    .add(kit.flash(sheet.status, { color: "neon", duration: 0.7 }), 2.5)
    /* ② 执行：命中的行一行行红掉塌陷，进度跑到 7，人数与资料卡同步作废 */
    .add(flow.step(2), 2.95)
    .add(sheet.close(), 2.95)
    .add(kit.pop(prog), 3.25)
    .add(kit.flash(first, { color: "red", duration: 0.6 }), 3.35)
    .to(fill, { scaleX: 1, duration: 1.2, ease: "power1.inOut" }, 3.45)
    .add(kit.count(progN, 7, { duration: 1.2 }), 3.45)
    .add(kit.flash(zombie, { color: "red", duration: 0.6 }), 3.6)
    .add(kit.collapse(first), 3.75)
    .add(kit.collapse(zombie), 4.1)
    /* 只暗掉资料本身，批量进度要一直亮着 */
    .to([hero, form.el], { opacity: 0.22, duration: 0.4 }, 4.3)
    .add(kit.scramble(cap, "客户名单 · 209 人", { duration: 0.45 }), 4.4)
    .add(flow.done(), 4.7)
    .add(kit.ok("已清理 7 人", { en: "AUTO REMOVED", hold: 1.5 }), 4.8)
    .add(strip.result("7 个僵尸粉已清"), 4.8);
  return tl;
}

/* ═══════════════ contact-add 添加好友 · 导入名单逐个自动发申请 ═══════════════ */
/* 历史成交名单导入 38 人 → 验证消息按名单自动填 → 一个接一个发出去 */
function contactAdd({ gsap, kit, tl }) {
  const MSG = "王总您好，我是星辰科技小吴";
  const { el, rows, cap, card, form } = addressBook(kit, {
    head: "老客户名单",
    cap: "历史成交 · 38 人",
    rows: [
      { name: "王总（星辰采购）", av: "王", tone: "them", note: "待添加", noteCls: "is-warn", active: true },
      { name: "李姐（远航贸易）", av: "李", tone: "muted", note: "待添加", noteCls: "is-warn" },
      { name: "陈总（明德科技）", av: "陈", tone: "them", note: "待添加", noteCls: "is-warn" },
      { name: "刘工（中和电气）", av: "刘", tone: "muted", note: "待添加", noteCls: "is-warn" },
      { name: "赵总（安泰机械）", av: "赵", tone: "them", note: "待添加", noteCls: "is-warn" },
    ],
    hero: { av: "王", nick: "王总 · 星辰采购" },
    fields: [["微信号", "wxid_wang0416", true], ["验证消息", "—"]],
  });
  el.classList.add("pd-contact-add");
  const account = form.rows[0], message = form.rows[1];
  account.value.appendChild(kit.tag("来自名单"));
  const msgTag = autoTag(kit, gsap, message, "自动填充");

  // 批量进度：这不是发一条，是一张 38 人的名单在跑
  const prog = kit.h("div", "pd-contact-prog");
  const progN = kit.h("b", "", "0");
  const progTxt = kit.h("span", "");
  progTxt.append("已发出 ", progN, " / 38");
  const bar = kit.h("i", "pd-contact-prog__bar");
  const fill = kit.h("b");
  bar.appendChild(fill);
  prog.append(kit.h("i", "pd-contact-prog__k", "BATCH"), progTxt, bar);
  card.appendChild(prog);
  gsap.set(fill, { scaleX: 0 });

  // 预览：王总那边会收到什么（这是真实动作，对方看得到）
  const pv = kit.h("div", "pd-contact-pv");
  pv.appendChild(kit.h("i", "pd-contact-pv__hint", "对方将看到 · 好友申请"));
  const pvCard = kit.h("div", "pd-contact-pv__card");
  const pvTxt = kit.h("div", "pd-contact-pv__txt");
  const pvMsg = kit.h("i", "", "—");
  pvTxt.append(kit.h("b", "", "星辰科技小吴"), pvMsg);
  pvCard.append(kit.avatar("吴", "me"), pvTxt);
  pv.appendChild(pvCard);
  card.appendChild(pv);

  const strip = kit.scenario("历史订单导出 · 老客户要加回来");
  const flow = kit.workflow([
    { label: "名单导入 · 38 人", icon: "file" },
    { label: "逐个自动发申请", icon: "send" },
  ]);

  // 名单里的一行落成「申请已发出」
  const sent = (row, at) => {
    tl.call(() => { row.note.classList.remove("is-warn"); row.note.classList.add("is-done"); }, [], at)
      .add(kit.scramble(row.note, "申请已发出", { duration: 0.45 }), at)
      .add(kit.flash(row, { color: "neon", duration: 0.6 }), at);
  };

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：名单导进来了 */
    .add(flow.step(0), 0.7)
    .add(kit.flash(cap, { color: "amber", duration: 0.7 }), 0.75)
    .add(kit.flash(account, { color: "amber", duration: 0.6 }), 0.95)
    /* ② 执行：验证消息按名单自己填出来，没有人在打字 */
    .add(flow.step(1), 1.4)
    .call(() => { message.classList.add("is-edit"); message.value.textContent = ""; }, [], 1.4)
    .add(kit.pop(msgTag), 1.45)
    /* 乱码落定，不是逐字敲：一敲字就成了「人坐在这儿打」，和整组的自动叙事相反 */
    .add(kit.scramble(message.value, MSG, { duration: 0.95 }), 1.42)
    .call(() => message.classList.remove("is-edit"), [], 2.4)
    .add(kit.scramble(pvMsg, MSG, { duration: 0.5 }), 2.4)
    /* 一个接一个发出去，进度条与计数一路跑到 38 */
    .to(fill, { scaleX: 1, duration: 1.35, ease: "power1.inOut" }, 2.85)
    .add(kit.count(progN, 38, { duration: 1.35 }), 2.85);
  sent(rows[0], 2.9);
  sent(rows[1], 3.15);
  sent(rows[2], 3.4);
  sent(rows[3], 3.65);
  sent(rows[4], 3.9);
  tl.add(flow.done(), 4.15)
    .add(kit.ok("已发送", { en: "REQUESTS SENT", hold: 1.4 }), 4.25)
    .add(strip.result("申请已发出"), 4.25);
  return tl;
}

export default {
  "contact-remark": contactRemark,
  "contact-accept": contactAccept,
  "contact-delete": contactDelete,
  "contact-add": contactAdd,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* ── 通讯录/名单：左列表 + 右资料卡 ── */
.pd-contact { position: absolute; inset: 0; display: grid; grid-template-columns: 190px minmax(0, 1fr); }
.pd-contact__rail {
  border-right: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.015);
  padding: 10px 8px; display: flex; flex-direction: column; gap: 4px; min-width: 0; overflow: hidden;
}
.pd-root .pd-contact__cap {
  margin: 0 2px 7px; font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.2em;
  color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pd-contact__search { display: block; height: 20px; border-radius: 4px; background: var(--pd-skel); margin-bottom: 6px; flex: none; }
.pd-contact__rail .pd-sess { border-radius: 4px; }
.pd-contact__rail .pd-sess__txt b.mono { font-size: 10.5px; font-weight: 400; letter-spacing: 0.02em; color: var(--pd-dim); }
/* 名单行的状态小字：代替骨架条，交代「多久没互动 / 加回没有」 */
.pd-contact__note {
  font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.06em; color: var(--pd-faint);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pd-contact__note.is-warn { color: #d98a5a; }
.pd-contact__note.is-done { color: var(--pd-neon); opacity: 0.85; }
.pd-contact__main { position: relative; display: flex; flex-direction: column; min-width: 0; }
.pd-contact__head {
  height: 36px; flex: none; display: flex; align-items: center; justify-content: space-between; padding: 0 14px;
  border-bottom: 1px solid var(--pd-line); font-size: 13px; font-weight: 600;
}
.pd-contact__more { color: var(--pd-dim); }
.pd-contact__card { padding: 20px 28px 0; display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.pd-contact__hero { display: flex; align-items: center; gap: 14px; min-width: 0; }
.pd-contact__hero .pd-av { width: 56px; height: 56px; border-radius: 8px; font-size: 20px; }
.pd-contact__hero-txt { display: flex; flex-direction: column; justify-content: center; min-height: 56px; gap: 3px; min-width: 0; }
.pd-contact__hero-txt .pd-tag { align-self: flex-start; margin-left: 0; }
.pd-contact__remark, .pd-contact__name {
  font-size: 16px; font-weight: 700; line-height: 1.3; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pd-contact__remark { color: var(--pd-amber); text-shadow: 0 0 10px rgba(255, 194, 75, 0.35); }
.pd-contact__name { transition: font-size 0.3s, color 0.3s; }
.pd-contact__name.is-sub { font-size: 11px; font-weight: 400; color: var(--pd-dim); }
.pd-contact__name.is-sub::before { content: "昵称："; }
.pd-contact__actions { display: flex; justify-content: flex-end; gap: 8px; }
.pd-screen .pd-sess__txt b.pd-contact-hit { color: var(--pd-amber); text-shadow: 0 0 8px rgba(255, 194, 75, 0.4); }

/* 被自动改写的字段：标签 / 值 / 「AI 生成」小标三栏，小标不挤掉正文 */
.pd-contact .pd-field.is-auto { grid-template-columns: 92px minmax(0, 1fr) auto; }
.pd-contact .pd-field .pd-tag { flex: none; }

/* 命名规则常驻一行：备注不是随手编的 */
.pd-contact-rule {
  display: flex; align-items: center; gap: 6px; padding: 6px 9px; border-radius: 3px;
  border: 1px dashed rgba(255, 194, 75, 0.3); background: rgba(255, 194, 75, 0.05);
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.1em; color: var(--pd-dim); white-space: nowrap;
}
.pd-contact-rule .pd-ic { width: 12px; height: 12px; flex: none; color: var(--pd-amber); }

/* 批量进度：已发出 n / 38 + 一根霓虹进度条 */
.pd-contact-prog {
  display: flex; align-items: center; gap: 8px; min-width: 0;
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.1em; color: var(--pd-dim); white-space: nowrap;
}
.pd-contact-prog__k { flex: none; padding: 1px 5px 0; border-radius: 2px; letter-spacing: 0.2em; color: #04140b; background: var(--pd-neon); opacity: 0.86; }
.pd-contact-prog b { color: var(--pd-neon); font-weight: 600; }
.pd-contact-prog__bar { flex: 1 1 auto; min-width: 40px; height: 3px; border-radius: 2px; background: var(--pd-skel); overflow: hidden; }
.pd-contact-prog__bar b { display: block; width: 100%; height: 100%; transform-origin: 0 50%; background: var(--pd-neon); box-shadow: 0 0 8px rgba(61, 242, 141, 0.6); }
/* 清理是「减法」：同一条进度条换成红色，别和「加好友」的霓虹混在一起 */
.pd-contact-prog--red .pd-contact-prog__k { color: #1a0606; background: var(--pd-red); }
.pd-contact-prog--red b { color: var(--pd-red); }
.pd-contact-prog--red .pd-contact-prog__bar b { background: var(--pd-red); box-shadow: 0 0 8px rgba(255, 93, 93, 0.6); }

/* ── 新的朋友：左申请列表 + 右空会话区 / 滑入的聊天窗 ── */
.pd-contact-req { position: absolute; inset: 0; display: grid; grid-template-columns: 340px minmax(0, 1fr); }
.pd-contact-req__pane { border-right: 1px solid var(--pd-line); display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.pd-contact-req__head {
  height: 36px; flex: none; display: flex; align-items: center; gap: 8px; padding: 0 14px;
  border-bottom: 1px solid var(--pd-line); font-size: 13px; font-weight: 600;
}
.pd-contact-req__badge {
  min-width: 16px; height: 16px; padding: 0 5px; border-radius: 8px; display: grid; place-items: center;
  background: var(--pd-amber); color: #140d01; font-family: var(--pd-mono); font-size: 9.5px; font-weight: 600; line-height: 1;
}
.pd-contact-req__list { padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; overflow: hidden; }
.pd-contact-req__row {
  position: relative; display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 4px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid transparent;
}
.pd-contact-req__row.is-active { background: rgba(61, 242, 141, 0.06); border-color: rgba(61, 242, 141, 0.3); }
.pd-contact-req__txt { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pd-contact-req__txt b { font-size: 12px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-contact-req__txt i { font-size: 10.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 按钮不走 pd-btn 的 transition：琥珀→霓虹要在乱码落定那一刻切换，走片截图也才截得准 */
.pd-contact-req__row .pd-btn { min-width: 56px; flex: none; transition: none; }
.pd-contact-req__row .pd-tag { flex: none; margin-left: 0; }
.pd-contact-req__divider { display: block; font-size: 8.5px; letter-spacing: 0.22em; color: var(--pd-faint); padding: 8px 2px 2px; }
.pd-contact-req__row--skel { opacity: 0.55; }
.pd-contact-req__row--skel .pd-contact-req__txt { gap: 5px; }
.pd-contact-req__row--skel .pd-btn { opacity: 0.6; }
.pd-contact-req__empty {
  display: grid; place-items: center; align-content: center; gap: 8px;
  color: var(--pd-faint); font-size: 11px; letter-spacing: 0.1em;
}
.pd-contact-req__empty .pd-ic { width: 26px; height: 26px; opacity: 0.5; }
.pd-contact-req__chat {
  position: absolute; right: 0; top: 0; bottom: 0; width: 300px; z-index: 10; overflow: hidden;
  background: #0d1410; border-left: 1px solid var(--pd-line-strong); box-shadow: -20px 0 50px rgba(0, 0, 0, 0.5);
}
/* AI 读验证消息时横扫的一道光 */
.pd-contact-scan { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none; }
.pd-contact-scan b { position: absolute; top: 0; bottom: 0; left: 0; width: 38%; background: linear-gradient(90deg, transparent, rgba(61, 242, 141, 0.3), transparent); }

/* 清理详情：判据用红框摆出来；底栏只有一条执行状态，没有让人点的按钮 */
.pd-contact-confirm__body { display: flex; align-items: flex-start; gap: 10px; padding: 12px 10px; border: 1px solid rgba(255, 93, 93, 0.3); background: rgba(255, 93, 93, 0.06); border-radius: 4px; }
.pd-contact-confirm__body > .pd-ic { flex: none; width: 18px; height: 18px; color: var(--pd-red); }
.pd-contact-confirm__body p { margin: 0; color: var(--pd-ink); font-size: 11.5px; line-height: 1.6; }
.pd-contact-demo { font-size: 8.5px; letter-spacing: 0.2em; color: var(--pd-faint); }
.pd-contact-confirm .pd-sheet__foot { justify-content: flex-start; }
.pd-contact-auto {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 9px; border-radius: 3px;
  border: 1px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.03);
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.14em; color: var(--pd-faint);
  transition: color 0.25s, border-color 0.25s, background 0.25s;
}
.pd-contact-auto .pd-ic { width: 11px; height: 11px; flex: none; }
.pd-contact-auto.is-on { color: var(--pd-neon); border-color: rgba(61, 242, 141, 0.45); background: rgba(61, 242, 141, 0.09); }
/* 判据表：左字段 / 中取值 / 右「命中」，逐条亮起 */
.pd-contact-rules__k { display: block; font-size: 8.5px; letter-spacing: 0.2em; color: var(--pd-faint); margin-top: 2px; }
.pd-contact-rules { display: flex; flex-direction: column; gap: 5px; }
.pd-contact-rules__r {
  display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 8px;
  padding: 6px 9px; border-radius: 3px; border-left: 2px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.03);
  transition: border-color 0.25s, background 0.25s;
}
.pd-contact-rules__r i { font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.1em; color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-contact-rules__r em { font-size: 11px; font-style: normal; color: var(--pd-ink); white-space: nowrap; }
.pd-contact-rules__f { display: inline-flex; align-items: center; gap: 3px; font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.1em; color: var(--pd-red); opacity: 0; }
.pd-contact-rules__f .pd-ic { width: 10px; height: 10px; stroke-width: 2.4; }
.pd-contact-rules__r.is-on { border-left-color: var(--pd-red); background: rgba(255, 93, 93, 0.07); }

/* 添加好友：资料卡撑满整栏，预览框吃掉余下的高度 */
.pd-contact-add .pd-contact__card { flex: 1 1 auto; min-height: 0; padding-bottom: 16px; }
/* 名单还没跑到的联系人：右边先给一个空态 */
.pd-contact__empty {
  position: absolute; left: 0; right: 0; top: 36px; bottom: 0;
  display: grid; place-items: center; align-content: center; gap: 8px;
  color: var(--pd-faint); font-size: 11px; letter-spacing: 0.1em;
}
.pd-contact__empty .pd-ic { width: 26px; height: 26px; opacity: 0.5; }

/* 添加好友：申请在对方那边长什么样 */
.pd-contact-pv {
  position: relative; flex: 1 1 auto; min-height: 84px; display: flex; align-items: center; justify-content: center;
  border: 1px dashed var(--pd-line-strong); border-radius: 4px; background: rgba(255, 255, 255, 0.02);
}
.pd-contact-pv__hint {
  position: absolute; left: 9px; top: 7px; font-family: var(--pd-mono); font-size: 8.5px;
  letter-spacing: 0.18em; color: var(--pd-faint); white-space: nowrap;
}
.pd-contact-pv__card {
  display: flex; align-items: center; gap: 9px; padding: 9px 11px; border-radius: 4px; max-width: 94%; min-width: 0;
  background: rgba(255, 255, 255, 0.045); border: 1px solid var(--pd-line);
}
.pd-contact-pv__txt { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.pd-contact-pv__txt b { font-size: 11.5px; font-weight: 500; color: var(--pd-ink); white-space: nowrap; }
.pd-contact-pv__txt i { font-size: 10px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
`;
