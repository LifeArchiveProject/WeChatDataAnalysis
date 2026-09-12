/* ════════════════════════════════════════════════════════════
   scenes / contact.js — 联系人（4 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   这一组只演示公开页面里的联系人界面：所有内容都是虚构的本地 DOM，
   不调用接口、不读写真实联系人。需要用户确认的步骤用光标和同一枚按钮表达，
   结果只描述画面里可见的状态。

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

/* ═══════════════ contact-remark 修改联系人备注 · 模板填充 ═══════════════ */
/* 选中联系人 → 按模板填充备注 → 更新当前资料卡，不描述对方可见性 */
function contactRemark({ gsap, kit, tl }) {
  const REMARK = "来源-林墨-咨询";
  const { el, main, first, card, remarkBig, nick, form } = addressBook(kit, {
    cap: "联系人示例 · 5 人",
    rows: [
      { name: "林墨", av: "林", tone: "them", note: "待规范", noteCls: "is-warn", active: true },
      { name: "周岚", av: "周", tone: "muted", note: "备注已规范", noteCls: "is-done" },
      { name: "阿柚", av: "柚", tone: "them", note: "备注已规范", noteCls: "is-done" },
      { name: "顾言", av: "顾", tone: "muted", note: "备注已规范", noteCls: "is-done" },
      { name: "沈乔", av: "沈", tone: "them", note: "备注已规范", noteCls: "is-done" },
    ],
    hero: { av: "林", nick: "林墨" },
    fields: [["备注", "林墨"], ["微信号", "limo_demo_0416", true], ["来源", "公开示例"]],
  });
  el.classList.add("pd-contact-remark");
  // 资料卡先保持空态，选中联系人后再展示
  const empty = kit.h("div", "pd-contact__empty");
  empty.append(kit.icon("user"), kit.h("span", "", "等待新好友"));
  main.appendChild(empty);
  // 命名规则常驻显示：备注按模板拼出
  const rule = kit.h("div", "pd-contact-rule");
  rule.append(kit.icon("edit"), kit.h("span", "", "备注模板 · 来源-姓名-需求"));
  card.appendChild(rule);

  const strip = kit.scenario("联系人资料 · 备注需要统一");
  const flow = kit.workflow([
    { label: "选中联系人", icon: "user" },
    { label: "按模板填充", icon: "edit" },
    { label: "更新资料", icon: "check" },
  ]);
  const remark = form.rows[0];
  const tag = autoTag(kit, gsap, remark, "模板填充");
  gsap.set(remarkBig, { display: "none" });
  gsap.set(first, { display: "none" });
  gsap.set(card, { opacity: 0 });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    /* ① 触发：名单顶上多出刚通过的这一位，资料卡跟着打开 */
    .add(flow.step(0), 0.8)
    .set(first, { display: "flex" }, 0.8)
    .add(kit.pop(first), 0.8)
    .add(strip.say("选中联系人 · 备注还是微信昵称"), 0.85)
    .to(card, { opacity: 1, duration: 0.35 }, 0.9)
    .to(empty, { opacity: 0, duration: 0.3 }, 0.9)
    .add(kit.flash(first, { color: "amber", duration: 0.7 }), 0.85)
    /* ② 按模板：读取来源和昵称，拼出规范备注 */
    .add(flow.step(1), 2.0)
    .call(() => remark.classList.add("is-edit"), [], 2.05)
    .add(kit.pop(tag), 2.1)
    .add(kit.scramble(remark.value, REMARK, { duration: 1.0 }), 2.15)
    /* ③ 更新资料：资料卡大字落定、原昵称缩成小字、名单那行同步改名 */
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
    .add(kit.ok("已更新备注", { en: "PROFILE UPDATED", hold: 1.4 }), 4.05)
    .add(strip.result("备注已规范 · 仅当前资料"), 4.05);
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
    mk("周岚", "周", "muted", "想和你交换联系方式", "已同意", "ghost"),
    mk("阿柚", "柚", "them", "方便认识一下吗", "已同意", "ghost"),
    mk("林墨", "林", "them", "你好，想和你交流一下", "同意申请", "amber"),
  ];
  // 更早的请求：两行骨架，只为把列表撑成一页
  list.appendChild(kit.h("i", "pd-contact-req__divider mono", "更早 · EARLIER"));
  for (let i = 0; i < 2; i++) {
    const r = kit.h("div", "pd-contact-req__row pd-contact-req__row--skel");
    const txt = kit.h("div", "pd-contact-req__txt");
    txt.append(kit.skel(38 + i * 10, 7), kit.skel(96 - i * 18, 5));
    r.append(kit.avatar("", "muted"), txt);
    kit.btn("已同意", "ghost", r);
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

/* ═══════════════ contact-accept 同意联系人申请 · 单个确认 ═══════════════ */
/* 选中一条申请 → 同一枚按钮确认同意 → 联系人资料关系更新 */
function contactAccept({ gsap, kit, tl }) {
  const { badge, rows, empty, wrap } = newFriends(kit);
  const row = rows[2], accept = row.btn;
  const chat = kit.chat({ title: "林墨", rail: false, parent: wrap });
  const sys = chat.sys("你已同意林墨的申请，现在可以开始聊天了");
  const first = chat.row("l", "你好，很高兴认识你", { av: "林" });
  const strip = kit.scenario("新的朋友 · 选中一条申请");
  const c = kit.cursor({ x: 300, y: 220 });
  const relation = kit.tag("联系人关系已更新", "pd-tag--neon");
  row.insertBefore(relation, accept);

  gsap.set(wrap, { xPercent: 100 });
  gsap.set([sys, first, row], { display: "none" });
  gsap.set([relation, badge], { opacity: 0 });
  gsap.set(badge, { scale: 0 });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    /* ① 选中一条申请 */
    .set(row, { display: "flex" }, 0.65)
    .add(kit.pop(row), 0.65)
    .to(badge, { scale: 1, opacity: 1, duration: 0.32, ease: "back.out(2.4)" }, 0.75)
    .add(c.to(row, { duration: 0.55 }), 0.9)
    .add(c.click(row), ">")
    .call(() => row.classList.add("is-active"), [], ">")
    .add(kit.flash(row, { color: "amber", duration: 0.55 }), ">")
    /* ② 同一枚按钮先进入确认态，再完成同意 */
    .add(c.to(accept, { duration: 0.45 }), ">+0.15")
    .add(c.click(accept), ">")
    .add(kit.scramble(accept, "确认同意", { duration: 0.4 }), ">")
    .add(c.click(accept), ">+0.1")
    .call(() => { accept.classList.remove("pd-btn--amber"); accept.classList.add("pd-btn--neon"); }, [], ">")
    .add(kit.scramble(accept, "已同意", { duration: 0.4 }), ">")
    .add(kit.pop(relation), "<")
    .add(kit.flash(row, { color: "neon", duration: 0.65 }), "<")
    .to(badge, { scale: 0, opacity: 0, duration: 0.3, ease: "back.in(2)" }, ">-0.1")
    /* ③ 关系更新后再显示会话 */
    .to(wrap, { xPercent: 0, duration: 0.45, ease: "power3.out" }, ">-0.1")
    .to(empty, { opacity: 0, duration: 0.3 }, "<")
    .set(sys, { display: "block" }, ">-0.05")
    .add(kit.pop(sys), ">")
    .set(first, { display: "flex" }, ">+0.25")
    .add(kit.pop(first), ">")
    .add(kit.flash(first.content, { color: "neon", duration: 0.65 }), "<")
    .to(chat.input, { opacity: 0.25, duration: 0.3 }, ">-0.1")
    .add(kit.ok("已同意", { en: "CONFIRMED", hold: 1.35 }), ">-0.25")
    .add(strip.result("联系人关系已更新"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ contact-delete 删除联系人 · 选定后确认 ═══════════════ */
function contactDelete({ gsap, kit, tl }) {
  const { el, first, rows, card, hero, form, btns } = addressBook(kit, {
    head: "联系人资料",
    cap: "联系人示例 · 3 人",
    rows: [
      { name: "周岚", av: "周", tone: "them", note: "可选", noteCls: "is-warn" },
      { name: "林墨", av: "林", tone: "muted", note: "保留" },
      { name: "阿柚", av: "柚", tone: "them", note: "保留" },
    ],
    hero: { av: "周", nick: "周岚" },
    fields: [["备注", "旧同学"], ["当前状态", "联系人"], ["来源", "公开示例"]],
    actions: [["确认删除", "red"]],
  });
  el.classList.add("pd-contact-delete");
  const selected = first;
  const confirm = btns[0];
  card.appendChild(kit.h("i", "pd-contact-delete__hint", "演示环境 · 选定联系人后确认"));
  const strip = kit.scenario("通讯录 · 选定一位联系人后确认");
  const c = kit.cursor({ x: 300, y: 220 });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    .add(c.to(selected, { duration: 0.55 }), 0.65)
    .add(c.click(selected), ">")
    .call(() => {
      rows.forEach((r) => r.classList.remove("is-active"));
      selected.classList.add("is-active");
      selected.note.textContent = "已选中";
      selected.note.classList.remove("is-warn");
      selected.note.classList.add("is-done");
    }, [], ">")
    .add(kit.flash(selected, { color: "amber", duration: 0.6 }), ">")
    .add(c.to(confirm, { duration: 0.45 }), ">+0.15")
    .add(c.click(confirm), ">")
    .call(() => {
      confirm.classList.remove("pd-btn--red");
      confirm.classList.add("pd-btn--neon");
      confirm.textContent = "已删除";
      form.rows[1].value.textContent = "已删除";
    }, [], ">")
    .add(kit.flash(selected, { color: "red", duration: 0.6 }), "<")
    .add(kit.collapse(selected), ">+0.1")
    .to([hero, form.el], { opacity: 0.28, duration: 0.35 }, ">-0.1")
    .add(kit.ok("已删除", { en: "CONFIRMED", hold: 1.25 }), ">-0.2")
    .add(strip.result("选定联系人已删除"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ contact-add 添加联系人 · 单个申请待通过 ═══════════════ */
function contactAdd({ gsap, kit, tl }) {
  const MSG = "你好，想和你认识一下";
  const { el, first, rows, card, form, btns } = addressBook(kit, {
    head: "联系人资料",
    cap: "已选联系人 · 1 人",
    rows: [
      { name: "林墨", av: "林", tone: "them", note: "已选中", noteCls: "is-done", active: true },
    ],
    hero: { av: "林", nick: "林墨" },
    fields: [["微信号", "limo_demo_2048", true], ["验证消息", "—"], ["当前状态", "未发申请"]],
    actions: [["发送申请", "amber"]],
  });
  el.classList.add("pd-contact-add");
  const account = form.rows[0], message = form.rows[1], status = form.rows[2];
  const apply = btns[0];
  card.appendChild(kit.h("i", "pd-contact-add__hint", "仅发出申请 · 不自动成为好友"));
  const strip = kit.scenario("已选中一位联系人 · 填写验证消息");
  const c = kit.cursor({ x: 300, y: 220 });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    .add(c.to(first, { duration: 0.5 }), 0.65)
    .add(c.click(first), ">")
    .add(kit.flash(account, { color: "amber", duration: 0.55 }), ">")
    .add(c.to(message.value, { duration: 0.45 }), ">+0.15")
    .add(c.click(message.value), ">")
    .call(() => { message.classList.add("is-edit"); message.value.textContent = ""; }, [], ">")
    .add(kit.type(message.value, MSG, { cps: 15 }), ">")
    .call(() => message.classList.remove("is-edit"), [], ">")
    .add(c.to(apply, { duration: 0.45 }), ">+0.15")
    .add(c.click(apply), ">")
    .call(() => {
      apply.classList.remove("pd-btn--amber");
      apply.classList.add("pd-btn--neon");
      apply.textContent = "申请待通过";
      status.value.textContent = "申请待通过";
      rows[0].note.textContent = "申请待通过";
    }, [], ">")
    .add(kit.flash(first, { color: "neon", duration: 0.65 }), "<")
    .add(kit.ok("申请待通过", { en: "PENDING", hold: 1.25 }), ">-0.2")
    .add(strip.result("等待对方通过 · 不自动成为好友"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ── 标签选择器：完整集合始终在抽屉内可见 ── */
function labelChoices(kit, labels, selected = []) {
  const el = kit.h("div", "pd-contact-label-choices");
  const rows = labels.map((label) => {
    const row = kit.h("div", "pd-contact-label-choice");
    const box = kit.h("i", "pd-contact-label-choice__box");
    box.appendChild(kit.icon("check"));
    row.append(box, kit.h("span", "", label));
    if (selected.includes(label)) row.classList.add("is-on");
    el.appendChild(row);
    return Object.assign(row, { box, label });
  });
  return { el, rows };
}

/* ═══════════════ contact-create-label 新建标签 ═══════════════ */
function contactCreateLabel({ gsap, kit, tl }) {
  const { el, card, btns } = addressBook(kit, {
    head: "标签管理",
    cap: "联系人示例 · 3 人",
    rows: [
      { name: "林墨", av: "林", tone: "them", note: "客户", active: true },
      { name: "周岚", av: "周", tone: "muted", note: "待跟进" },
      { name: "阿柚", av: "柚", tone: "them", note: "客户" },
    ],
    hero: { av: "林", nick: "林墨" },
    fields: [["当前标签", "客户"], ["备注", "公开示例"], ["来源", "本地资料"]],
    actions: [["新建标签", "amber"]],
  });
  el.classList.add("pd-contact-create-label");
  const labelBox = kit.h("section", "pd-contact-create-label__box");
  labelBox.appendChild(kit.h("b", "pd-contact-create-label__title", "标签列表"));
  const labels = kit.chips(["客户", "待跟进"], { parent: labelBox });
  const created = labels.add("近期活动", { hidden: true });
  card.appendChild(labelBox);
  const create = btns[0];
  const sheet = kit.sheet({ title: "新建标签", cls: "pd-contact-create-label__sheet" });
  const name = kit.form([["标签名称", "—"]], sheet.body).rows[0];
  sheet.ok.textContent = "创建标签";
  const strip = kit.scenario("联系人整理 · 需要新增一个标签");
  const c = kit.cursor({ x: 300, y: 220 });
  gsap.set(created, { display: "none" });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    .add(c.to(create, { duration: 0.5 }), 0.65)
    .add(c.click(create), ">")
    .add(sheet.open(), ">-0.05")
    .add(c.to(name.value, { duration: 0.45 }), "<+0.15")
    .add(c.click(name.value), ">")
    .call(() => name.value.textContent = "", [], ">")
    .add(kit.type(name.value, "近期活动", { cps: 16 }), ">")
    .add(c.to(sheet.ok, { duration: 0.45 }), ">+0.15")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">")
    .set(created, { display: "inline-block" }, ">-0.05")
    .add(kit.pop(created), ">")
    .call(() => {
      create.classList.remove("pd-btn--amber");
      create.classList.add("pd-btn--neon");
      create.textContent = "已创建";
    }, [], ">")
    .add(kit.flash(labelBox, { color: "neon", duration: 0.65 }), "<")
    .add(kit.ok("标签已创建", { en: "LABEL CREATED", hold: 1.2 }), ">-0.2")
    .add(strip.result("标签列表已更新"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ contact-set-labels 给联系人设置标签 ═══════════════ */
function contactSetLabels({ gsap, kit, tl }) {
  const { el, card, btns } = addressBook(kit, {
    head: "联系人标签",
    cap: "联系人示例 · 3 人",
    rows: [
      { name: "林墨", av: "林", tone: "them", note: "已选中", noteCls: "is-done", active: true },
      { name: "周岚", av: "周", tone: "muted", note: "客户" },
      { name: "阿柚", av: "柚", tone: "them", note: "待跟进" },
    ],
    hero: { av: "林", nick: "林墨" },
    fields: [["备注", "林墨"], ["当前标签", "客户"], ["来源", "本地资料"]],
    actions: [["管理标签", "amber"]],
  });
  el.classList.add("pd-contact-set-labels");
  const current = kit.h("section", "pd-contact-set-labels__current");
  current.appendChild(kit.h("b", "pd-contact-set-labels__title", "当前标签"));
  const chips = kit.chips(["客户"], { parent: current });
  const added = chips.add("近期活动", { hidden: true });
  current.appendChild(kit.h("i", "pd-contact-set-labels__keep", "保留原标签，可继续新增"));
  card.appendChild(current);
  const manage = btns[0];
  const sheet = kit.sheet({ title: "选择标签", cls: "pd-contact-set-labels__sheet" });
  sheet.body.appendChild(kit.h("i", "pd-contact-set-labels__all", "完整集合 · 4 个标签"));
  const choices = labelChoices(kit, ["客户", "待跟进", "近期活动", "已成交"], ["客户"]);
  sheet.body.appendChild(choices.el);
  sheet.ok.textContent = "保存标签";
  const strip = kit.scenario("联系人整理 · 保留原标签并新增");
  const c = kit.cursor({ x: 300, y: 220 });
  gsap.set(added, { display: "none" });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    .add(c.to(manage, { duration: 0.5 }), 0.65)
    .add(c.click(manage), ">")
    .add(sheet.open(), ">-0.05")
    .add(kit.pop(choices.el), ">+0.15")
    .add(c.to(choices.rows[2], { duration: 0.45 }), ">+0.15")
    .add(c.click(choices.rows[2]), ">")
    .call(() => choices.rows[2].classList.add("is-on"), [], ">")
    .add(kit.flash(choices.rows[2], { color: "amber", duration: 0.55 }), "<")
    .add(c.to(sheet.ok, { duration: 0.45 }), ">+0.15")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">")
    .set(added, { display: "inline-block" }, ">-0.05")
    .add(kit.pop(added), ">")
    .call(() => {
      manage.classList.remove("pd-btn--amber");
      manage.classList.add("pd-btn--neon");
      manage.textContent = "已保存";
    }, [], ">")
    .add(kit.flash(current, { color: "neon", duration: 0.65 }), "<")
    .add(kit.ok("标签已更新", { en: "LABELS UPDATED", hold: 1.2 }), ">-0.2")
    .add(strip.result("保留「客户」 · 新增「近期活动」"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ contact-search 联系人查询 · 只展示结果 ═══════════════ */
function contactSearch({ gsap, kit, tl }) {
  const PHONE = "138****2048";
  const RESULT_WX = "limo_demo";
  const el = kit.h("div", "pd-contact-search pd-pushed");
  const formPane = kit.h("section", "pd-contact-search__form");
  const formHead = kit.h("header", "pd-contact-search__head");
  formHead.append(kit.icon("key"), kit.h("b", "", "联系人查询"));
  formPane.appendChild(formHead);
  const form = kit.form([["手机号 / 微信号", "—", true]], formPane);
  formPane.appendChild(kit.h("i", "pd-contact-search__hint", "脱敏示例 · 仅用于展示查询结果"));
  const query = kit.btn("查询", "amber", formPane);
  const resultPane = kit.h("section", "pd-contact-search__result");
  resultPane.appendChild(kit.h("b", "pd-contact-search__result-title", "查询结果"));
  const empty = kit.h("div", "pd-contact-search__empty", "等待查询");
  resultPane.appendChild(empty);
  const result = kit.h("article", "pd-contact-search__card");
  const resultText = kit.h("div", "pd-contact-search__card-text");
  const resultName = kit.h("b", "", "柯然（示例）");
  const resultPhone = kit.h("i", "", PHONE);
  const resultWxid = kit.h("i", "", `微信号示例 · ${RESULT_WX}`);
  resultText.append(resultName, resultPhone, resultWxid, kit.tag("仅展示 · 不自动加人", "pd-tag--neon"));
  result.append(kit.avatar("柯", "them"), resultText);
  resultPane.appendChild(result);
  el.append(formPane, resultPane);
  kit.mount(el);
  const strip = kit.scenario("联系人查询 · 输入脱敏示例");
  const c = kit.cursor({ x: 300, y: 220 });
  gsap.set(result, { display: "none" });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    .add(c.to(form.rows[0].value, { duration: 0.45 }), 0.65)
    .add(c.click(form.rows[0].value), ">")
    .add(kit.type(form.rows[0].value, PHONE, { cps: 18 }), ">")
    .add(c.to(query, { duration: 0.45 }), ">+0.15")
    .add(c.click(query), ">")
    .call(() => {
      query.classList.remove("pd-btn--amber");
      query.classList.add("pd-btn--neon");
      query.textContent = "已查询";
    }, [], ">")
    .to(empty, { opacity: 0, duration: 0.25 }, ">")
    .set(result, { display: "flex" }, ">-0.05")
    .add(kit.pop(result), ">")
    .add(kit.flash(result, { color: "neon", duration: 0.65 }), "<")
    .add(kit.ok("仅展示结果", { en: "VIEW ONLY", hold: 1.2 }), ">-0.2")
    .add(strip.result("结果已展示 · 未发起申请"), "<")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ contact-insights 联系人变化 · 本地快照周期 ═══════════════ */
function contactInsights({ gsap, kit, tl }) {
  const el = kit.h("div", "pd-contact-insights pd-pushed");
  const head = kit.h("header", "pd-contact-insights__head");
  head.append(kit.h("b", "", "联系人变化记录"));
  const period = kit.btn("本周快照", "amber", head);
  head.appendChild(kit.tag("本地快照", "pd-tag--neon"));
  const list = kit.h("div", "pd-contact-insights__list");
  const count = kit.h("i", "pd-contact-insights__count", "本周 · 2 条变化");
  list.appendChild(count);
  const makeRow = (who, change, value, time) => {
    const row = kit.h("div", "pd-contact-insights__row");
    row.appendChild(kit.avatar(who[0], "muted"));
    const text = kit.h("div", "pd-contact-insights__row-text");
    const whoEl = kit.h("b", "", who);
    const changeEl = kit.h("span", "", change);
    const valueEl = kit.h("i", "", value);
    const timeEl = kit.h("em", "", time);
    text.append(whoEl, changeEl, valueEl, timeEl);
    row.appendChild(text);
    list.appendChild(row);
    return Object.assign(row, { whoEl, changeEl, valueEl, timeEl });
  };
  const rowA = makeRow("林墨", "新增标签", "近期活动", "本地记录");
  const rowB = makeRow("周岚", "备注更新", "来源-周岚-咨询", "本地记录");
  el.append(head, list);
  kit.mount(el);
  const strip = kit.scenario("联系人页 · 查看本地快照变化", { local: true });
  const c = kit.cursor({ x: 300, y: 220 });

  tl.add(strip.in(), 0.05)
    .add(c.show(), 0.35)
    .add(kit.pop(rowA), 0.65)
    .add(kit.pop(rowB), 0.85)
    .add(c.to(period, { duration: 0.5 }), 1.35)
    .add(c.click(period), ">")
    .call(() => {
      period.classList.remove("pd-btn--amber");
      period.classList.add("pd-btn--neon");
      period.textContent = "上周快照";
      count.textContent = "上周 · 2 条变化";
    }, [], ">")
    .add(kit.scramble(rowA.changeEl, "移除标签", { duration: 0.35 }), ">")
    .add(kit.scramble(rowA.valueEl, "待跟进", { duration: 0.35 }), "<")
    .add(kit.scramble(rowB.changeEl, "备注更新", { duration: 0.35 }), ">")
    .add(kit.scramble(rowB.valueEl, "来源-周岚-咨询", { duration: 0.35 }), "<")
    .add(kit.flash(list, { color: "neon", duration: 0.65 }), ">+0.1")
    .add(kit.ok("快照已切换", { en: "LOCAL SNAPSHOT", hold: 1.2 }), ">-0.2")
    .add(strip.result("仅展示本地快照变化"), "<")
    .add(c.hide(), "<");
  return tl;
}

export default {
  "contact-remark": contactRemark,
  "contact-accept": contactAccept,
  "contact-delete": contactDelete,
  "contact-add": contactAdd,
  "contact-create-label": contactCreateLabel,
  "contact-set-labels": contactSetLabels,
  "contact-search": contactSearch,
  "contact-insights": contactInsights,
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

/* 被模板填充的字段：标签 / 值 / 小标三栏，小标不挤掉正文 */
.pd-contact .pd-field.is-auto { grid-template-columns: 92px minmax(0, 1fr) auto; }
.pd-contact .pd-field .pd-tag { flex: none; }

/* 命名规则常驻一行：备注不是随手编的 */
.pd-contact-rule {
  display: flex; align-items: center; gap: 6px; padding: 6px 9px; border-radius: 3px;
  border: 1px dashed rgba(255, 194, 75, 0.3); background: rgba(255, 194, 75, 0.05);
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.1em; color: var(--pd-dim); white-space: nowrap;
}
.pd-contact-rule .pd-ic { width: 12px; height: 12px; flex: none; color: var(--pd-amber); }

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
/* 添加联系人：资料卡撑满整栏 */
.pd-contact-add .pd-contact__card { flex: 1 1 auto; min-height: 0; padding-bottom: 16px; }
/* 名单还没跑到的联系人：右边先给一个空态 */
.pd-contact__empty {
  position: absolute; left: 0; right: 0; top: 36px; bottom: 0;
  display: grid; place-items: center; align-content: center; gap: 8px;
  color: var(--pd-faint); font-size: 11px; letter-spacing: 0.1em;
}
.pd-contact__empty .pd-ic { width: 26px; height: 26px; opacity: 0.5; }

/* ── 标签页：列表出现、保留原标签与新增标签 ── */
.pd-contact-create-label .pd-contact__card,
.pd-contact-set-labels .pd-contact__card { gap: 10px; }
.pd-contact-create-label__box,
.pd-contact-set-labels__current {
  display: flex; flex-direction: column; gap: 7px; padding: 9px 10px; border-radius: 4px;
  border: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.025);
}
.pd-contact-create-label__title,
.pd-contact-set-labels__title { font-size: 10px; letter-spacing: 0.16em; color: var(--pd-dim); }
.pd-contact-create-label__box .pd-chips,
.pd-contact-set-labels__current .pd-chips { gap: 5px; min-height: 18px; }
.pd-contact-create-label__box .pd-chip,
.pd-contact-set-labels__current .pd-chip { margin: 0; }
.pd-contact-set-labels__keep,
.pd-contact-set-labels__all {
  font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.08em; color: var(--pd-faint);
}
.pd-contact-label-choices { display: flex; flex-direction: column; gap: 6px; }
.pd-contact-label-choice {
  display: flex; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 3px;
  border: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.025); color: var(--pd-dim);
  font-size: 11px; transition: border-color 0.2s, background 0.2s, color 0.2s;
}
.pd-contact-label-choice__box {
  width: 14px; height: 14px; display: grid; place-items: center; border: 1px solid var(--pd-line-strong);
  border-radius: 2px; color: transparent;
}
.pd-contact-label-choice__box .pd-ic { width: 11px; height: 11px; }
.pd-contact-label-choice.is-on { border-color: rgba(61, 242, 141, 0.4); background: rgba(61, 242, 141, 0.07); color: var(--pd-ink); }
.pd-contact-label-choice.is-on .pd-contact-label-choice__box { border-color: var(--pd-neon); color: var(--pd-neon); }
.pd-contact-create-label__sheet .pd-form,
.pd-contact-set-labels__sheet .pd-form { gap: 6px; }

/* ── 查询页：脱敏字段与仅展示结果 ── */
.pd-contact-search { position: absolute; inset: 0; display: grid; grid-template-columns: 250px minmax(0, 1fr); background: rgba(255, 255, 255, 0.012); }
.pd-contact-search__form { display: flex; flex-direction: column; gap: 12px; padding: 18px 16px; border-right: 1px solid var(--pd-line); }
.pd-contact-search__head { display: flex; align-items: center; gap: 7px; font-size: 13px; }
.pd-contact-search__head .pd-ic { width: 15px; height: 15px; color: var(--pd-amber); }
.pd-contact-search__form .pd-form { gap: 7px; }
.pd-contact-search__form .pd-field { grid-template-columns: 96px minmax(0, 1fr); }
.pd-contact-search__hint { margin-top: auto; font-family: var(--pd-mono); font-size: 8.5px; line-height: 1.6; letter-spacing: 0.08em; color: var(--pd-faint); }
.pd-contact-search__form > .pd-btn { align-self: flex-end; }
.pd-contact-search__result { position: relative; padding: 18px 22px; }
.pd-contact-search__result-title { display: block; font-size: 12px; letter-spacing: 0.12em; color: var(--pd-dim); }
.pd-contact-search__empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--pd-faint); font-family: var(--pd-mono); font-size: 10px; letter-spacing: 0.16em; }
.pd-contact-search__card { position: absolute; left: 22px; right: 22px; top: 92px; display: flex; align-items: center; gap: 13px; padding: 15px 16px; border: 1px solid rgba(61, 242, 141, 0.25); border-radius: 5px; background: rgba(61, 242, 141, 0.045); }
.pd-contact-search__card > .pd-av { width: 44px; height: 44px; font-size: 17px; }
.pd-contact-search__card-text { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; min-width: 0; }
.pd-contact-search__card-text > b { font-size: 14px; color: var(--pd-ink); }
.pd-contact-search__card-text > i { font-family: var(--pd-mono); font-size: 10px; letter-spacing: 0.05em; color: var(--pd-dim); }
.pd-contact-search__card-text > .pd-tag { margin: 3px 0 0; }

/* ── 变化记录：只在两个本地快照之间切换 ── */
.pd-contact-insights { position: absolute; inset: 0; padding: 18px 26px; background: rgba(255, 255, 255, 0.012); }
.pd-contact-insights__head { display: flex; align-items: center; gap: 10px; height: 34px; border-bottom: 1px solid var(--pd-line); }
.pd-contact-insights__head > b { margin-right: auto; font-size: 13px; }
.pd-contact-insights__head > .pd-tag { margin: 0; }
.pd-contact-insights__list { display: flex; flex-direction: column; gap: 8px; max-width: 470px; padding-top: 18px; overflow: hidden; }
.pd-contact-insights__count { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.14em; color: var(--pd-faint); }
.pd-contact-insights__row { display: flex; align-items: center; gap: 11px; padding: 11px 13px; border: 1px solid var(--pd-line); border-radius: 4px; background: rgba(255, 255, 255, 0.025); }
.pd-contact-insights__row > .pd-av { width: 34px; height: 34px; font-size: 13px; }
.pd-contact-insights__row-text { display: grid; grid-template-columns: 68px 78px minmax(0, 1fr); align-items: center; gap: 5px 10px; min-width: 0; flex: 1; }
.pd-contact-insights__row-text > b { font-size: 11.5px; color: var(--pd-ink); }
.pd-contact-insights__row-text > span { font-size: 10px; color: var(--pd-amber); }
.pd-contact-insights__row-text > i { font-family: var(--pd-mono); font-size: 9.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-contact-insights__row-text > em { grid-column: 1 / -1; font-family: var(--pd-mono); font-size: 8px; letter-spacing: 0.1em; color: var(--pd-faint); }

/* ── 单按钮状态与说明 ── */
.pd-contact-delete__hint,
.pd-contact-add__hint { font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.12em; color: var(--pd-faint); }
.pd-contact-delete .pd-contact__actions .pd-btn,
.pd-contact-add .pd-contact__actions .pd-btn { min-width: 94px; }

`;
