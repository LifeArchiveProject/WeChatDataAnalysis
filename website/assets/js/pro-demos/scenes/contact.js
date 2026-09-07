/* ════════════════════════════════════════════════════════════
   scenes / contact.js — 联系人（4 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入 / 已同意」印章并停留。

   两张脸：
   - 通讯录：左 190px 联系人列表（搜索条 + 5 行）+ 右侧资料卡（大头像 / 昵称 / 字段表单 / 按钮行）
   - 新的朋友：左 340px 请求列表（3 行，各带验证消息与按钮）+ 右侧空会话区，同意后聊天窗从右滑入
   ════════════════════════════════════════════════════════════ */

/* ── 通讯录布局：返回列表行、资料卡各个可动的元素 ── */
function addressBook(kit) {
  const el = kit.h("div", "pd-contact");
  // 左：搜索骨架条 + 5 行联系人；第一行是还没备注的「wxid_laodifang」
  const rail = kit.h("aside", "pd-contact__rail");
  rail.appendChild(kit.h("i", "pd-contact__search"));
  const list = kit.sessions(["wxid_laodifang", "小王", "阿明", "老张", { name: "家人群", grid: ["我", "王", "明", "张"] }], { parent: rail });
  const first = list.rows[0];
  first.classList.add("is-active");
  first.name.classList.add("mono");
  const av0 = first.querySelector(".pd-av");
  av0.textContent = "友";
  av0.classList.remove("pd-av--muted"); av0.classList.add("pd-av--them");
  el.appendChild(rail);

  // 右：资料卡
  const main = kit.h("div", "pd-contact__main");
  const head = kit.h("header", "pd-contact__head");
  head.append(kit.h("b", "", "联系人资料"), kit.icon("dots", "pd-ic pd-contact__more"));
  const card = kit.h("div", "pd-contact__card");
  const hero = kit.h("div", "pd-contact__hero");
  const big = kit.avatar("友", "them");
  const heroTxt = kit.h("div", "pd-contact__hero-txt");
  const remarkBig = kit.h("b", "pd-contact__remark", "");
  const nick = kit.h("b", "pd-contact__name", "老地方");
  heroTxt.append(remarkBig, nick);
  hero.append(big, heroTxt);
  card.appendChild(hero);
  const form = kit.form([["备注", "—"], ["微信号", "wxid_laodifang", true], ["来源", "通过手机号添加"]], card);
  const actions = kit.h("div", "pd-contact__actions");
  const msgBtn = kit.btn("发消息", "ghost", actions);
  const save = kit.btn("保存", "amber", actions);
  card.appendChild(actions);
  main.append(head, card);
  el.appendChild(main);
  kit.mount(el);
  return { el, list, first, remarkBig, nick, form, remark: form.rows[0], msgBtn, save, actions };
}

/* ── 修改好友备注：点「备注」行 → 打字 → 保存 → 列表名字落定、资料卡冒出备注名大字 → 印章 ── */
function contactRemark({ gsap, kit, tl }) {
  const { first, remarkBig, nick, form, remark, save } = addressBook(kit);
  const text = "阿福（大学室友）";
  gsap.set(save, { opacity: 0 });                    // 占位不显示，进入编辑才冒出来
  gsap.set(remarkBig, { display: "none" });
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.to(remark.value, { duration: 0.55 }), 0.3)
    .add(c.click(remark), ">")
    .addLabel("edit", "<+0.08")
    .call(() => { remark.classList.add("is-edit"); remark.value.textContent = ""; remark.value.classList.add("is-typing"); }, [], "edit")
    .add(kit.pop(save), "edit")
    .add(c.to(form.el, { duration: 0.4, dx: 60, dy: 92 }), "edit+=0.15")   // 鼠标让开字段
    .add(kit.type(remark.value, text, { cps: 8 }), "edit+=0.3")
    .add(c.to(save, { duration: 0.45 }), ">+0.3")
    .add(c.click(save), ">")
    .call(() => remark.classList.remove("is-edit"), [], "<+0.25")
    .to(save, { opacity: 0, duration: 0.25 }, "<+0.1")
    // 资料卡：备注名大字冒出来，原昵称缩成下面一行小字
    .set(remarkBig, { display: "block" }, ">-0.05")
    .add(kit.pop(remarkBig), "<")
    .add(kit.scramble(remarkBig, text, { duration: 0.45 }), "<")
    .call(() => nick.classList.add("is-sub"), [], "<")
    // 列表：第一行名字乱码落定成备注名（全局生效）
    .call(() => { first.name.classList.remove("mono"); first.name.classList.add("pd-contact-hit"); }, [], "<+0.2")
    .add(kit.scramble(first.name, text, { duration: 0.55 }), "<")
    .add(kit.flash(first, { color: "amber", duration: 0.7 }), "<")
    .add(kit.ok("已写入 · remark"), ">+0.15")
    .add(c.hide(), "<");
  return tl;
}

/* ── 「新的朋友」布局：左请求列表 + 右空会话区 ── */
function newFriends(kit) {
  const el = kit.h("div", "pd-contact-req");
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
    mk("小王", "王", "muted", "我是小王，通过一下", "已添加", "ghost"),
    mk("老张", "张", "them", "老张，之前一起打球的", "已添加", "ghost"),
    mk("阿明", "明", "them", "我是阿明，加个好友", "接受", "amber"),
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

/* ── 同意好友请求：光标点「接受」→ 按钮落定成「已添加」并转霓虹 → 右侧滑入与阿明的聊天窗 → 印章 ── */
function contactAccept({ gsap, kit, tl }) {
  const { badge, rows, empty, wrap } = newFriends(kit);
  const row = rows[2], accept = row.btn;
  const chat = kit.chat({ title: "阿明", rail: false, parent: wrap });
  const sys = chat.sys("你已添加了阿明，现在可以开始聊天了");
  gsap.set(wrap, { xPercent: 100 });
  gsap.set(sys, { display: "none" });
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.to(row.msg, { duration: 0.5, dy: 2 }), 0.35)         // 先停在验证消息上看一眼
    .to({}, { duration: 0.3 })
    .add(c.to(accept, { duration: 0.4 }), ">")
    .add(c.click(accept), ">")
    .call(() => { accept.classList.remove("pd-btn--amber"); accept.classList.add("pd-btn--neon"); }, [], "<+0.12")
    .add(kit.scramble(accept, "已添加", { duration: 0.45 }), "<")
    .add(kit.flash(row, { color: "neon", duration: 0.7 }), "<")
    .to(badge, { scale: 0, opacity: 0, duration: 0.3, ease: "back.in(2)" }, "<")
    .call(() => row.classList.add("is-active"), [], ">-0.1")
    // 让「已添加」被看清，再从右侧滑入聊天窗，空态淡出
    .to(wrap, { xPercent: 0, duration: 0.5, ease: "power3.out" }, ">+0.2")
    .to(empty, { opacity: 0, duration: 0.3 }, "<")
    .set(sys, { display: "block" }, ">-0.05")
    .add(kit.pop(sys), "<")
    .to({}, { duration: 0.3 })
    .add(c.to(chat.field, { duration: 0.45, dx: 24 }), ">")      // 光标落到输入框：现在可以聊了
    .call(() => chat.field.classList.add("is-typing"))
    .add(kit.ok("已同意", { en: "ACCEPTED" }), ">+0.45")
    .add(c.hide(), "<");
  return tl;
}

/* ── 破坏性联系人操作：菜单后再进入确认面板，结果保留为演示状态 ── */
function contactConfirmSheet(kit, { title, text, confirm, icon = "trash" }) {
  const sheet = kit.sheet({ title, cls: "pd-contact-confirm" });
  const body = kit.h("div", "pd-contact-confirm__body");
  body.append(kit.icon(icon), kit.h("p", "", text));
  sheet.body.appendChild(body);
  sheet.cancel.textContent = "取消";
  sheet.ok.textContent = confirm;
  sheet.ok.classList.remove("pd-btn--amber");
  sheet.ok.classList.add("pd-btn--red");
  return sheet;
}

function contactDelete({ kit, tl }) {
  const { first } = addressBook(kit);
  const menu = kit.menu([
    { icon: "user", label: "查看资料" },
    { icon: "trash", label: "删除联系人", danger: true },
  ], { at: first, dx: 14, dy: 8 });
  const sheet = contactConfirmSheet(kit, {
    title: "删除联系人",
    text: "将删除「老地方」。请先确认，此处仅展示操作步骤。",
    confirm: "确认删除",
  });
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.tap(first), 0.3)
    .add(menu.open(), ">-0.05")
    .add(c.to(menu.items[1], { duration: 0.4 }), "<+0.1")
    .add(c.click(menu.items[1]), ">")
    .add(menu.close(), ">")
    .add(sheet.open(), ">-0.05")
    .add(c.to(sheet.ok, { duration: 0.4 }), "<+0.2")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">")
    .add(kit.flash(first, { color: "red", duration: 0.7 }), ">-0.05")
    .add(kit.collapse(first), ">")
    .add(kit.ok("已删除 · 演示", { en: "DELETED DEMO" }), ">-0.1")
    .add(c.hide(), "<");
  return tl;
}

function contactAdd({ kit, tl }) {
  const { actions } = addressBook(kit);
  const addBtn = kit.btn("添加朋友", "amber", actions);
  const sheet = kit.sheet({ title: "添加好友", cls: "pd-contact-add-sheet" });
  const form = kit.form([
    ["微信号", "oldfriend2026", true],
    ["验证消息", "你好，我是老朋友"],
  ], sheet.body);
  sheet.ok.textContent = "发送请求";
  const c = kit.cursor();
  const account = form.rows[0], message = form.rows[1];

  tl.add(c.show(), 0.2)
    .add(c.tap(addBtn), 0.3)
    .add(sheet.open(), ">-0.05")
    .add(c.to(account.value, { duration: 0.4 }), "<+0.15")
    .add(c.click(account), ">")
    .call(() => account.classList.add("is-edit"), [], "<+0.05")
    .add(kit.type(account.value, "oldfriend2026", { cps: 12 }), ">+0.2")
    .call(() => account.classList.remove("is-edit"), [], "<")
    .add(c.to(message.value, { duration: 0.4 }), ">+0.15")
    .add(c.click(message), ">")
    .call(() => message.classList.add("is-edit"), [], "<+0.05")
    .add(kit.type(message.value, "你好，我是老朋友", { cps: 14 }), ">+0.2")
    .call(() => message.classList.remove("is-edit"), [], "<")
    .add(c.to(sheet.ok, { duration: 0.4 }), ">+0.25")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">")
    .call(() => {
      addBtn.textContent = "已发送";
      addBtn.classList.remove("pd-btn--amber");
      addBtn.classList.add("pd-btn--neon");
    }, [], ">-0.05")
    .add(kit.flash(addBtn, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("请求已发送 · 演示", { en: "REQUEST DEMO" }), ">-0.1")
    .add(c.hide(), "<");
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
/* ── 通讯录：左列表 + 右资料卡 ── */
.pd-contact { position: absolute; inset: 0; display: grid; grid-template-columns: 190px minmax(0, 1fr); }
.pd-contact__rail {
  border-right: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.015);
  padding: 10px 8px; display: flex; flex-direction: column; gap: 4px; min-width: 0; overflow: hidden;
}
.pd-contact__search { display: block; height: 20px; border-radius: 4px; background: var(--pd-skel); margin-bottom: 6px; flex: none; }
.pd-contact__rail .pd-sess { border-radius: 4px; }
.pd-contact__rail .pd-sess__txt b.mono { font-size: 10.5px; font-weight: 400; letter-spacing: 0.02em; color: var(--pd-dim); }
.pd-contact__main { position: relative; display: flex; flex-direction: column; min-width: 0; }
.pd-contact__head {
  height: 36px; flex: none; display: flex; align-items: center; justify-content: space-between; padding: 0 14px;
  border-bottom: 1px solid var(--pd-line); font-size: 13px; font-weight: 600;
}
.pd-contact__more { color: var(--pd-dim); }
.pd-contact__card { padding: 26px 28px 0; display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.pd-contact__hero { display: flex; align-items: center; gap: 14px; min-width: 0; }
.pd-contact__hero .pd-av { width: 56px; height: 56px; border-radius: 8px; font-size: 20px; }
.pd-contact__hero-txt { display: flex; flex-direction: column; justify-content: center; height: 56px; gap: 3px; min-width: 0; }
.pd-contact__remark, .pd-contact__name {
  font-size: 16px; font-weight: 700; line-height: 1.3; color: var(--pd-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pd-contact__remark { color: var(--pd-amber); text-shadow: 0 0 10px rgba(255, 194, 75, 0.35); }
.pd-contact__name { transition: font-size 0.3s, color 0.3s; }
.pd-contact__name.is-sub { font-size: 11px; font-weight: 400; color: var(--pd-dim); }
.pd-contact__name.is-sub::before { content: "昵称："; }
.pd-contact__actions { display: flex; justify-content: flex-end; gap: 8px; }
.pd-screen .pd-sess__txt b.pd-contact-hit { color: var(--pd-amber); text-shadow: 0 0 8px rgba(255, 194, 75, 0.4); }

/* ── 新的朋友：左请求列表 + 右空会话区 / 滑入的聊天窗 ── */
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
  display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 4px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid transparent;
}
.pd-contact-req__row.is-active { background: rgba(61, 242, 141, 0.06); border-color: rgba(61, 242, 141, 0.3); }
.pd-contact-req__txt { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pd-contact-req__txt b { font-size: 12px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-contact-req__txt i { font-size: 10.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 按钮不走 pd-btn 的 transition：琥珀→霓虹要在乱码落定那一刻切换，走片截图也才截得准 */
.pd-contact-req__row .pd-btn { min-width: 56px; flex: none; transition: none; }
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

/* 联系人确认：动作按钮使用红色，结果保留为静态演示 */
.pd-contact-confirm__body { display: flex; align-items: flex-start; gap: 10px; padding: 12px 10px; border: 1px solid rgba(255, 93, 93, 0.3); background: rgba(255, 93, 93, 0.06); border-radius: 4px; }
.pd-contact-confirm__body > .pd-ic { flex: none; width: 18px; height: 18px; color: var(--pd-red); }
.pd-contact-confirm__body p { margin: 0; color: var(--pd-ink); font-size: 11.5px; line-height: 1.6; }
.pd-contact-confirm .pd-sheet__foot .pd-btn--red { color: var(--pd-red); }
`;
