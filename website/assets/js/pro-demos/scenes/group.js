/* ════════════════════════════════════════════════════════════
   scenes / group.js — 群聊（4 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入 / 已发布 / 已建群」印章并停留。

   共用手法：标题栏「···」→ 右侧「群信息」抽屉 → 点某一行进入编辑（is-edit）→
   打字 → 保存 → 抽屉收起（光标同步退场，结果成为唯一焦点）→ 聊天里对应文字乱码落定 → 印章。
   ════════════════════════════════════════════════════════════ */

/* ── 家人群：小王 / 我 / 阿明 三人往来，行带群昵称；会话栏第一条改成「家人群」跟标题对上。
      me：我方行的群昵称标签，与抽屉「我在本群的昵称」字段同值（wuko），改昵称时前后才对得上 ── */
function familyChat(kit, { rail = true, rows = 4, me = "wuko" } = {}) {
  const chat = kit.chat({ title: "家人群", group: true, rail });
  if (rail) {
    const names = ["家人群", "老地方", "同事", "小王"];
    chat.sessions.forEach((s, i) => {
      s.querySelector("b").textContent = names[i];
      s.querySelector(".pd-av").textContent = names[i][0];
    });
  }
  chat.time("今天 10:24");
  const all = [
    () => chat.row("l", "周六大家有空吗？", { name: "小王", av: "王" }),
    () => chat.row("r", "有，几点？", { name: me }),
    () => chat.row("l", "18 点，老地方", { name: "阿明", av: "明" }),
    () => chat.row("r", "行，到时见", { name: me }),
  ].slice(0, rows).map((mk) => mk());
  return { chat, rows: all, mine: all.filter((r) => r.classList.contains("pd-row--r")) };
}

/* ── 「群信息」抽屉：成员条 + 三行字段（群名称 / 我在本群的昵称 / 群公告）── */
function infoSheet(kit, { nick = "wuko", notice = "—" } = {}) {
  const sheet = kit.sheet({ title: "群信息", cls: "pd-group-sheet" });
  const members = kit.h("div", "pd-group-members");
  members.appendChild(kit.h("i", "pd-group-members__k", "成员 · 4"));
  members.append(kit.avatar("我", "me"), kit.avatar("王", "them"), kit.avatar("明", "muted"), kit.avatar("张", "them"));
  sheet.body.appendChild(members);
  const form = kit.form([["群名称", "家人群"], ["我在本群的昵称", nick], ["群公告", notice]], sheet.body);
  return { sheet, form, name: form.rows[0], nick: form.rows[1], notice: form.rows[2] };
}

/* ── 打字时光标「让开」的停靠点（懒取位置）：
      贴字段值的右端（短值用）；below=true 时停到字段右下角外侧（长值会填满一行，别压字）── */
function park(kit, field, { below = false } = {}) {
  return () => {
    const r = kit.rect(below ? field : field.value);
    return below ? { x: r.right - 16, y: r.bottom + 14 } : { x: r.right - 12, y: r.cy };
  };
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

/* ── 修改本人群昵称：群信息 → 昵称行 wuko 改成「小吴」→ 保存 → 聊天里我方两行的群昵称落定 ── */
function groupMyNick({ kit, tl }) {
  const { chat, mine } = familyChat(kit);
  const names = mine.map((r) => r.querySelector(".pd-row__name"));
  const { sheet, nick } = infoSheet(kit);
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.tap(chat.more), 0.3)
    .add(sheet.open(), ">-0.2")
    .add(c.to(nick.value, { duration: 0.45 }), ">-0.1")
    .add(c.click(nick), ">")
    .addLabel("edit", "<+0.08")
    .call(() => nick.classList.add("is-edit"), [], "edit")
    .add(c.to(park(kit, nick), { duration: 0.3 }), "edit+=0.15")   // 让开到字段右端，别压着正在打的字
    .add(kit.type(nick.value, "小吴", { cps: 4 }), "edit+=0.3")
    .add(c.to(sheet.ok, { duration: 0.45 }), ">+0.3")
    .add(c.click(sheet.ok), ">")
    .call(() => nick.classList.remove("is-edit"), [], "<+0.25")
    .add(sheet.close(), ">")
    .add(c.hide(), "<")                                              // 保存后光标退场，别停在「发送」上
    .call(() => names.forEach((n) => n.classList.add("pd-group-hit")), [], ">-0.05")
    .add(kit.scramble(names[0], "小吴", { duration: 0.5 }), ">")
    .add(kit.scramble(names[1], "小吴", { duration: 0.5 }), "<+0.1")
    .add(kit.ok("已写入", { en: "NICKNAME" }), ">+0.15");
  return tl;
}

/* ── 发布群公告：群信息 → 群公告行打字 → 按钮变「发布」→ 聊天顶部弹入置顶公告条，
      再以我的名义落一条「@所有人 + 正文」气泡（微信的真实表现），印章「已发布」── */
function groupNotice({ gsap, kit, tl }) {
  const { chat } = familyChat(kit, { rows: 2 });      // 留出公告条 + @所有人 气泡的位置
  const { sheet, notice } = infoSheet(kit);
  const text = "周六 18:00 家庭聚餐，老地方";
  notice.classList.add("pd-group-field--wrap");
  const bar = noticeBar(kit, text);
  chat.list.insertBefore(bar, chat.list.firstChild);
  gsap.set(bar, { display: "none" });
  const bub = kit.bubble("", "r");
  bub.innerHTML = `<b class="pd-group-at">@所有人</b> ${text}`;
  const at = chat.row("r", bub, { name: "wuko" });
  gsap.set(at, { display: "none" });
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.tap(chat.more), 0.3)
    .add(sheet.open(), ">-0.2")
    .add(c.to(notice.value, { duration: 0.45, dx: -30 }), ">-0.1")
    .add(c.click(notice), ">")
    .addLabel("edit", "<+0.08")
    .call(() => { notice.classList.add("is-edit"); sheet.ok.textContent = "发布"; }, [], "edit")
    .add(c.to(park(kit, notice, { below: true }), { duration: 0.3 }), "edit+=0.15")   // 公告会填满一行：让到字段右下角外侧
    .add(kit.type(notice.value, text, { cps: 18 }), "edit+=0.3")
    .add(c.to(sheet.ok, { duration: 0.45 }), ">+0.3")
    .add(c.click(sheet.ok), ">")
    .call(() => notice.classList.remove("is-edit"), [], "<+0.25")
    .add(sheet.close(), ">")
    .add(c.hide(), "<")                                              // 发布后光标退场，别停在「发送」上
    .set(bar, { display: "flex" }, ">-0.05")
    .add(kit.pop(bar), "<")
    .set(at, { display: "flex" }, "<+0.3")
    .add(kit.pop(at), "<")
    .add(kit.flash(at.content, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已发布", { en: "PUBLISHED" }), ">-0.3");
  return tl;
}

/* ── 新建群聊：会话栏「⊕」→ 勾选三位联系人 → 完成 → 会话栏冒出新群（闪一下）、标题落定、
      聊天只剩一条系统行，光标顺手点进输入框打个招呼：群已经能用了 ── */
function groupCreate({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方", cls: "pd-group-chat" });
  chat.seed(3);
  const btn = kit.h("b", "pd-group-new");
  btn.appendChild(kit.icon("plus"));
  kit.mount(btn, chat.rail);                          // 挂在会话栏里，贴着搜索条右侧，不靠硬编码坐标

  const names = ["小王", "阿明", "老张", "同事李"];
  const picker = kit.picker(names);
  // 勾选器靠 CSS translate(-50%,-50%) 居中；让 gsap 接管 transform，免得 pop/scale 把它挤走
  gsap.set(picker.el, { xPercent: -50, yPercent: -50, x: 0, y: 0, opacity: 0, scale: 0.94 });

  const groupName = "小王、阿明、老张";
  const sess = kit.h("div", "pd-sess pd-group-sess is-active");
  sess.appendChild(kit.avatarGrid(["我", "小", "阿", "老"]));
  const txt = kit.h("div", "pd-sess__txt");
  txt.append(kit.h("b", "", groupName), kit.skel(58, 5));
  sess.appendChild(txt);
  chat.rail.insertBefore(sess, chat.sessions[0]);
  gsap.set(sess, { display: "none" });
  const sys = kit.h("p", "pd-sys");
  sys.innerHTML = "你邀请<b>小王</b>、<b>阿明</b>、<b>老张</b>加入了群聊";
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.tap(btn), 0.3)
    .to(picker.el, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(1.6)" }, ">-0.2");
  [0, 1, 2].forEach((i) => {
    tl.add(c.to(picker.rows[i].box, { duration: 0.32, dx: 4 }), i === 0 ? ">-0.05" : ">+0.2")
      .add(c.click(picker.rows[i]), ">")
      .call(() => picker.check(i), [], "<+0.06");
  });
  tl.add(c.to(picker.done, { duration: 0.4 }), ">+0.3")
    .add(c.click(picker.done), ">")
    .to(picker.el, { opacity: 0, scale: 0.96, duration: 0.22 }, "<+0.2")
    .addLabel("made", ">")
    .call(() => chat.sessions[0].classList.remove("is-active"), [], "made")
    .set(sess, { display: "flex" }, "made")
    .add(kit.pop(sess), "made")
    .add(kit.flash(sess, { color: "amber", duration: 0.7 }), "made")
    .call(() => chat.list.replaceChildren(sys), [], "made")
    .add(kit.pop(sys), "made+=0.05")
    .call(() => chat.title.classList.add("pd-group-hit"), [], "made")
    .add(kit.scramble(chat.title, groupName, { duration: 0.55 }), "made")
    // 群建好了：光标点进输入框打个招呼（不发送），顺便把光标从勾选器原位带走。
    // 空输入框的 em 宽度为 0，直接指它会落在最左边被打出来的字压住：指到招呼语右侧一点的位置
    .add(c.to(() => { const r = kit.rect(chat.field.parentElement); return { x: r.x + 76, y: r.cy }; }, { duration: 0.45 }), "made+=0.1")
    .add(c.click(chat.field), ">")
    .add(kit.type(chat.field, "大家好👋", { cps: 10 }), ">-0.3")
    .add(kit.ok("已建群", { en: "CREATED" }), ">+0.1")
    .add(c.hide(), "<");
  return tl;
}

/* ── 修改群名称：群信息 → 群名称行改成「家人群 · 2026」→ 保存 → 标题与会话栏一起落定 ── */
function groupRename({ kit, tl }) {
  const { chat } = familyChat(kit);
  const sessName = chat.sessions[0].querySelector("b");
  const { sheet, name } = infoSheet(kit);
  const newName = "家人群 · 2026";
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.tap(chat.more), 0.3)
    .add(sheet.open(), ">-0.2")
    .add(c.to(name.value, { duration: 0.45 }), ">-0.1")
    .add(c.click(name), ">")
    .addLabel("edit", "<+0.08")
    .call(() => name.classList.add("is-edit"), [], "edit")
    .add(c.to(park(kit, name), { duration: 0.3 }), "edit+=0.15")   // 让开到字段右端，别压着正在打的字
    .add(kit.type(name.value, newName, { cps: 12 }), "edit+=0.3")
    .add(c.to(sheet.ok, { duration: 0.45 }), ">+0.3")
    .add(c.click(sheet.ok), ">")
    .call(() => name.classList.remove("is-edit"), [], "<+0.25")
    .add(sheet.close(), ">")
    .add(c.hide(), "<")                                              // 保存后光标退场，别停在「发送」上
    .call(() => { chat.title.classList.add("pd-group-hit"); sessName.classList.add("pd-group-hit"); }, [], ">-0.05")
    .add(kit.scramble(chat.title, newName, { duration: 0.55 }), ">")
    .add(kit.scramble(sessName, newName, { duration: 0.55 }), "<+0.12")
    .add(kit.flash(chat.sessions[0], { color: "amber", duration: 0.7 }), "<")
    .add(kit.ok("已写入", { en: "RENAMED" }), ">-0.1");
  return tl;
}

export default {
  "group-my-nick": groupMyNick,
  "group-notice": groupNotice,
  "group-create": groupCreate,
  "group-rename": groupRename,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* 被改动的文字：琥珀高亮（群昵称 / 标题 / 会话名） */
.pd-screen .pd-row__name.pd-group-hit,
.pd-screen .pd-chat__title.pd-group-hit,
.pd-screen .pd-sess__txt b.pd-group-hit { color: var(--pd-amber); text-shadow: 0 0 8px rgba(255, 194, 75, 0.4); }

/* 群信息抽屉：标签列窄一点，公告能一行放下；成员条 */
.pd-group-sheet .pd-field { grid-template-columns: 78px minmax(0, 1fr); gap: 8px; }
.pd-group-members { display: flex; align-items: center; gap: 6px; padding: 2px 0 4px; }
.pd-group-members .pd-av { width: 24px; height: 24px; font-size: 10px; border-radius: 3px; }
.pd-group-members__k { font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.2em; color: var(--pd-faint); margin-right: 6px; white-space: nowrap; }
.pd-group-field--wrap { align-items: start; }
.pd-group-field--wrap .pd-field__v { white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.4; align-items: flex-end; }

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

/* 新建群聊：搜索条右侧的「⊕」按钮（挂在会话栏里，贴右上角）；新会话行名字略小，八个字放得下 */
.pd-group-chat .pd-chat__rail { position: relative; }
.pd-group-chat .pd-chat__search { margin-right: 26px; }
.pd-group-new {
  position: absolute; right: 8px; top: 10px; width: 20px; height: 20px; border-radius: 4px;
  display: grid; place-items: center; color: var(--pd-amber);
  background: rgba(255, 194, 75, 0.1); border: 1px solid rgba(255, 194, 75, 0.45);
}
.pd-group-new .pd-ic { width: 11px; height: 11px; stroke-width: 2.2; }
.pd-group-new.is-press { background: rgba(255, 194, 75, 0.38); filter: none; }
.pd-group-sess { padding: 6px 2px 6px 4px; }
.pd-group-sess .pd-sess__txt b { font-size: 11px; }
`;
