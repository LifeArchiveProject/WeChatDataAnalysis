/* ════════════════════════════════════════════════════════════
   scenes / edit.js — 消息修改（8 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入」印章并停留。
   统一起手：kit.chat({ title: "老地方" }) + chat.seed(3)，右键目标气泡弹 kit.menu。
   ════════════════════════════════════════════════════════════ */

// 示范场景：右键气泡 → 菜单选「修改」→ 原地改字 → 保存 → 落库印章
function editText({ kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  const target = rows[2].content;           // 「刚落地，还是老地方见」
  const c = kit.cursor();
  const menu = kit.menu([{ icon: "edit", label: "修改文字" }, { icon: "code", label: "编辑源码" }, { icon: "clock", label: "修改时间" }, { icon: "trash", label: "删除", danger: true }], { at: target, dx: 14, dy: 6 });

  tl.add(c.show(), 0.2)
    .add(c.tap(target), 0.3)
    .add(menu.open(), ">-0.05")
    .add(c.to(menu.items[0], { duration: 0.35 }), ">")
    .call(() => menu.hover(0))
    .add(c.click(menu.items[0]), ">")
    .add(menu.close(), ">")
    .call(() => target.classList.add("is-edit"))
    .add(kit.type(target, "刚落地，改在咖啡馆见 ☕", { cps: 14 }), ">+0.1")
    .add(c.to(chat.send, { duration: 0.4 }), ">+0.2")
    .add(c.click(chat.send), ">")
    .call(() => { target.classList.remove("is-edit"); target.appendChild(kit.tag("已修改")); })
    .add(kit.flash(target, { color: "amber", duration: 0.6 }), "<")
    .add(kit.ok("已写入 message_0.db"), ">-0.2")
    .add(c.hide(), "<");
  return tl;
}

/* ───────────────────────── 本组共用的小工具 ───────────────────────── */

// 右键菜单条目（与示范一致；各场景只是 hover 的那一项不同）
const MI = {
  text: { icon: "edit", label: "修改文字" },
  source: { icon: "code", label: "编辑源码" },
  time: { icon: "clock", label: "修改时间" },
  fields: { icon: "key", label: "字段编辑" },
  restore: { icon: "undo", label: "恢复原消息" },
  fix: { icon: "user", label: "修复为我发送" },
  del: { icon: "trash", label: "删除", danger: true },
};

// 「右键气泡 → 菜单弹出 → 光标滑到某项 → 点击 → 菜单收起」整段；返回 timeline（挂到 tl 上）
// hide: 菜单收起的同时把光标藏掉——点完菜单就没光标的事了，让结果动画成为唯一焦点
function rightClick({ gsap, kit, c, target, items, pick, dx = 14, dy = 6, hide = false }) {
  const menu = kit.menu(items, { at: target, dx, dy });
  const t = gsap.timeline();
  t.add(c.tap(target))
    .add(menu.open(), ">-0.05")
    .add(c.to(menu.items[pick], { duration: 0.35 }), ">")
    .call(() => menu.hover(pick))
    .add(c.click(menu.items[pick]), ">")
    .add(menu.close(), ">-0.2");
  if (hide) t.add(c.hide(), "<");
  return Object.assign(t, { menu });
}

// 表单某行：光标点过去 → 高亮 → 清空并闪光标 → 打出新值
function retype({ kit, c, field, text }) {
  const t = kit.gsap.timeline();
  t.add(c.to(field.value, { duration: 0.25 }))
    .add(c.click(field))
    .call(() => { field.classList.add("is-edit"); field.value.textContent = ""; field.value.classList.add("is-typing"); }, [], ">-0.25")
    .to({}, { duration: 0.12 })
    .add(kit.type(field.value, text, { cps: 8 }));
  return t;
}

// 一行气泡「翻到对面」：原行钉在原位淡出并向新方向位移，对面预建的同文气泡（display none）从另一侧滑入接管位置
function crossSwap({ gsap, kit, chat, row, side, text }) {
  const twin = chat.rowAt(row, side, text);
  gsap.set(twin, { display: "none", opacity: 0 });   // 先隐身：display 打开到 fromTo 起跑之间有 0.12s，别让它整个闪一下
  const dir = side === "r" ? 1 : -1;
  const t = gsap.timeline();
  t.call(() => {
      // 原行脱离文档流钉在原位，对面那行接管布局位置，列表不跳
      const top = row.offsetTop, left = row.offsetLeft, width = row.offsetWidth;
      gsap.set(row, { position: "absolute", top, left, width, zIndex: 2 });
      gsap.set(twin, { display: "flex" });
    })
    .to(row, { x: 48 * dir, opacity: 0, duration: 0.32, ease: "power2.in" })
    .fromTo(twin, { x: -48 * dir, opacity: 0 }, { x: 0, opacity: 1, duration: 0.42, ease: "power3.out", immediateRender: false }, "<+0.12")
    .set(row, { display: "none" })
    .add(kit.flash(twin.content, { color: "neon", duration: 0.7 }), "<-0.25");
  return Object.assign(t, { twin });
}

// 系统行删除：淡出 → 高度折到 0 并吃掉列表 gap → 下方行顺滑上移
function collapseSys(gsap, chat, el) {
  const gap = () => parseFloat(getComputedStyle(chat.list).rowGap) || 10;
  const t = gsap.timeline();
  t.set(el, { overflow: "hidden" })
    .to(el, { opacity: 0, x: -12, duration: 0.2, ease: "power2.in" })
    .to(el, { height: 0, paddingTop: 0, paddingBottom: 0, marginTop: () => -gap(), duration: 0.3, ease: "power2.inOut" })
    .set(el, { display: "none" });
  return t;
}

/* ───────────────────────── 场景 ───────────────────────── */

// 编辑消息源码：右键 → 编辑源码 → 抽屉里的 XML 改 <title> → 保存 → 气泡落定成新文案
function editSource({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  const target = rows[2].content;           // 「刚落地，还是老地方见」
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.time, MI.del], pick: 1 });
  const sheet = kit.sheet({ title: "消息源码" });
  const code = kit.code(["<msg>", " <appmsg>", "  <title>刚落地，还是老地方见</title>", "  <type>1</type>", " </appmsg>", "</msg>"], sheet.body);
  sheet.body.appendChild(kit.h("p", "pd-edit-meta mono", "message_0.db · local_id 10392"));
  const ln = code.lines[2], span = ln.lastElementChild;

  tl.add(c.show(), 0.2)
    .add(rc, 0.3)
    .add(sheet.open(), ">-0.1")
    .add(c.to(ln, { duration: 0.4 }), ">-0.1")
    .add(c.click(ln), ">")
    .call(() => ln.classList.add("is-edit"), [], ">-0.25")
    .add(kit.scramble(span, "  <title>刚落地，改在咖啡馆见</title>", { duration: 0.7 }), ">")
    .add(c.to(sheet.ok, { duration: 0.4 }), ">+0.05")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">-0.15")
    .add(c.to(target, { duration: 0.35, dy: 18 }), "<")   // 抽屉滑走时光标跟到气泡下沿，别压在「发送」上
    .call(() => target.classList.add("is-edit"), [], ">-0.1")
    .add(kit.scramble(target, "刚落地，改在咖啡馆见", { duration: 0.5 }), ">")
    .call(() => { target.classList.remove("is-edit"); target.appendChild(kit.tag("已修改")); })
    .add(kit.flash(target, { color: "amber", duration: 0.6 }), "<")
    .add(kit.ok("已写入 · XML", { en: "SOURCE WRITTEN" }), ">-0.2")
    .add(c.hide(), "<");
  return tl;
}

// 修改时间：右键 → 修改时间 → 小抽屉里改时间 → 保存 → 时间标签改写，这一行滑到列表最下（时间轴重排）
function editTime({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  const row = rows[2], target = row.content, after = rows[3];
  const tlabel = kit.h("p", "pd-time", "昨天 21:52");      // 这一行自己的时间标签
  chat.list.insertBefore(tlabel, row);
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.time, MI.del], pick: 2 });
  const sheet = kit.sheet({ title: "修改时间", cls: "pd-edit-sheet--sm" });
  const form = kit.form([["display_time", "昨天 21:52", true], ["create_time", "1725540451", true]], sheet.body);
  const fTime = form.rows[0], fEpoch = form.rows[1];
  sheet.body.appendChild(kit.h("p", "pd-edit-meta mono", "改完即按时间重排"));
  const gap = () => parseFloat(getComputedStyle(chat.list).rowGap) || 10;
  const m = { down: 0, up: 0 };

  tl.add(c.show(), 0.2)
    .add(rc, 0.3)
    .add(sheet.open(), ">-0.1")
    .add(c.to(fTime.value, { duration: 0.4 }), ">-0.1")
    .add(c.click(fTime), ">")
    .call(() => fTime.classList.add("is-edit"), [], ">-0.25")
    .add(kit.scramble(fTime.value, "今天 09:12", { duration: 0.6 }), ">")
    .call(() => fEpoch.classList.add("is-edit"), [], "<+0.15")       // 时间戳跟着改：这一行也点亮
    .add(kit.count(fEpoch.value, 1725581251, { from: 1725540451, duration: 0.5 }), "<")
    .add(c.to(sheet.ok, { duration: 0.35 }), ">")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">-0.15")
    .add(c.hide(), "<")                                             // 保存后光标退场，重排成为唯一焦点
    .add(kit.scramble(tlabel, "今天 09:12", { duration: 0.45 }), ">-0.1")
    .add(kit.flash(target, { color: "amber", duration: 0.6 }), "<")
    // 时间轴重排：这一行（连同它的时间标签）滑到最下，原来在它下面的那行顶上来
    .call(() => { m.down = kit.rect(after).h + gap(); m.up = kit.rect(after).y - kit.rect(tlabel).y; }, [], "<+0.4")
    .to([tlabel, row], { y: () => m.down, duration: 0.6, ease: "power3.inOut" })
    .to(after, { y: () => -m.up, duration: 0.6, ease: "power3.inOut" }, "<")
    .call(() => { chat.list.append(tlabel, row); gsap.set([tlabel, row, after], { clearProps: "transform" }); })
    .add(kit.ok("已写入 · create_time", { en: "WRITTEN" }), ">-0.2");
  return tl;
}

// 字段编辑：右键 → 字段编辑 → 抽屉里五个底层字段，改 status 与 is_sender → 保存 → 气泡按新字段翻到我这边
function editFields({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  const row = rows[3], target = row.content;   // 「好，就这么定了」（左侧，is_sender=0）
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.fields, MI.del], pick: 2 });
  const sheet = kit.sheet({ title: "字段编辑", cls: "pd-edit-sheet--sm" });
  const form = kit.form([["local_id", "10392", true], ["create_time", "1725540451", true], ["type", "1", true], ["status", "2", true], ["is_sender", "0", true]], sheet.body);
  const fStatus = form.rows[3], fSender = form.rows[4];
  const sw = crossSwap({ gsap, kit, chat, row, side: "r", text: "好，就这么定了" });
  // 翻过去的气泡上回显改过的两个字段——让人看到「status」这种底层字段也真的写进去了
  const echo = [kit.tag("status=4"), kit.tag("is_sender=1")];
  sw.twin.content.append(...echo);
  gsap.set(echo, { opacity: 0 });

  tl.add(c.show(), 0.2)
    .add(rc, 0.3)
    .add(sheet.open(), ">-0.1")
    .add(retype({ kit, c, field: fStatus, text: "4" }), ">-0.1")
    .add(retype({ kit, c, field: fSender, text: "1" }), ">-0.2")
    .add(c.to(sheet.ok, { duration: 0.3 }), ">")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">-0.15")
    .add(c.hide(), "<")                                             // 保存后光标退场，翻面成为唯一焦点
    .add(sw, ">-0.1")
    .fromTo(echo, { opacity: 0, y: 4, scale: 0.9 }, { opacity: 1, y: 0, scale: 1, duration: 0.3, stagger: 0.12, ease: "back.out(1.8)", immediateRender: false }, ">-0.5")
    .add(kit.ok("已写入 · 2 字段", { en: "2 FIELDS WRITTEN" }), ">-0.15");
  return tl;
}

// 恢复原消息：起手已是改过的文案并带「已修改」→ 右键 → 恢复原消息 → 文案落定回原句，标签缩没
function editRestore({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  const target = rows[2].content;
  const txt = kit.h("span", "", "刚落地，改在咖啡馆见");
  const tag = kit.tag("已修改");
  target.replaceChildren(txt, tag);
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.restore, MI.del], pick: 2, hide: true });

  tl.add(c.show(), 0.2)
    .add(c.to(tag, { duration: 0.5, dy: 14 }), 0.3)        // 先停到「已修改」标签下：交代这条改过头了
    .add(kit.flash(target, { color: "amber", duration: 0.5 }), ">-0.1")
    .to({}, { duration: 0.3 }, "<")
    .add(rc, ">")
    .call(() => target.classList.add("is-edit"), [], ">-0.1")
    .add(kit.scramble(txt, "刚落地，还是老地方见", { duration: 0.65 }), ">")
    // 标签缩没：锁成单行再收窄，否则收窄途中「已修改」会折成两行把气泡撑高
    .set(tag, { overflow: "hidden", whiteSpace: "nowrap", width: () => kit.rect(tag).w }, "<+0.25")
    .to(tag, { width: 0, paddingLeft: 0, paddingRight: 0, marginLeft: 0, borderLeftWidth: 0, borderRightWidth: 0, opacity: 0, duration: 0.35, ease: "power2.in" }, "<")
    .set(tag, { display: "none" })
    .call(() => target.classList.remove("is-edit"))
    .add(kit.flash(target, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已恢复", { en: "RESTORED" }), ">-0.3");
  return tl;
}

// 修复为我发送：一句明显是我说的却挂在对方那边 → 右键 → 修复为我发送 → 整行翻到右边，头像变「我」
function editFixSender({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  chat.seed(3);
  const row = chat.row("l", "我到家了");
  const target = row.content;
  target.appendChild(kit.tag("归属错位", "pd-tag--red"));
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.fix, MI.time, MI.del], pick: 1, hide: true });
  const sw = crossSwap({ gsap, kit, chat, row, side: "r", text: "我到家了" });

  tl.add(c.show(), 0.2)
    .add(c.to(target, { duration: 0.5, dy: 12 }), 0.3)     // 先停在挂错的那句上
    .add(kit.flash(target, { color: "red", duration: 0.6 }), ">-0.1")
    .add(rc, ">-0.35")
    .add(sw, ">-0.05")
    .add(kit.ok("已修正 · is_sender=1", { en: "FIXED" }), ">-0.2");
  return tl;
}

// 反转微信气泡位置：标题栏「···」→ 反转气泡位置 → 全部行左右互换，头像「我」「友」互换
function editFlipSides({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  rows.push(chat.row("r", "好，路上小心"));
  const msgs = rows.filter((r) => r.classList.contains("pd-row"));
  const c = kit.cursor();
  const menu = kit.menu([{ icon: "user", label: "聊天信息" }, { icon: "swap", label: "反转气泡位置" }, { icon: "file", label: "导出记录" }, { icon: "trash", label: "清空聊天", danger: true }], { at: chat.more, dx: -8, dy: 12 });   // 右缘对齐「···」往下落，像真的下拉菜单，少压首行气泡
  // 每行离场时朝它将要去的那边滑，翻面后再从另一侧滑进来，方向连贯
  const out = (r) => (r.classList.contains("pd-row--r") ? -40 : 40);
  const flip = (r) => {
    const toR = !r.classList.contains("pd-row--r");
    r.classList.toggle("pd-row--r", toR); r.classList.toggle("pd-row--l", !toR);
    r.av.textContent = toR ? "我" : "友";
    r.av.classList.toggle("pd-av--me", toR); r.av.classList.toggle("pd-av--them", !toR);
    r.content.classList.toggle("pd-bub--r", toR); r.content.classList.toggle("pd-bub--l", !toR);
  };

  tl.add(c.show(), 0.2)
    .add(c.tap(chat.more), 0.3)
    .add(menu.open(), ">-0.05")
    .add(c.to(menu.items[1], { duration: 0.35 }), ">")
    .call(() => menu.hover(1))
    .add(c.click(menu.items[1]), ">")
    .add(menu.close(), ">-0.2")
    .add(c.hide(), "<")                                             // 点完就退场，翻面成为唯一焦点
    .to(msgs, { x: (i, el) => out(el), opacity: 0, duration: 0.28, ease: "power2.in", stagger: 0.07 }, ">-0.1")
    .call(() => msgs.forEach(flip))
    .fromTo(msgs, { x: (i, el) => out(el), opacity: 0 }, { x: 0, opacity: 1, duration: 0.36, ease: "power3.out", stagger: 0.07, immediateRender: false })
    .add(kit.flash(msgs[msgs.length - 1].content, { color: "neon", duration: 0.6 }), ">-0.2")
    .add(kit.ok(`已反转 · ${msgs.length} 条`, { en: "FLIPPED" }), ">-0.3");
  return tl;
}

// 删除系统消息：两条系统提示，逐条右键 → 删除系统消息 → 折叠消失、下方行上移 → 红色印章
function editDeleteSys({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  const rows = chat.seed(3);
  // 第一条塞在左侧气泡「好，就这么定了」上方：右键菜单往右下落，正好落在空处，不压任何气泡
  const sys1 = chat.sys("你撤回了一条消息");
  sys1.classList.add("pd-edit-sys");
  chat.list.insertBefore(sys1, rows[3]);
  const sys2 = chat.sys("对方开启了朋友验证");
  sys2.classList.add("pd-edit-sys");
  const c = kit.cursor();
  const items = [MI.source, MI.time, { icon: "trash", label: "删除系统消息", danger: true }];
  const m1 = kit.menu(items, { at: sys1, dx: 42, dy: 10 });   // 往右让开，不压到下面居中的第二条系统行
  const m2 = kit.menu(items, { at: sys2, dx: 10, dy: 8 });

  // 红框一直亮到点下「删除系统消息」为止（flash 时长盖过整段菜单操作），目标行不失焦。
  // 注意 flash 拉长后它就是时间轴最长的那条，后面的 .call 必须显式给 ">"，否则会被排到 flash 结束处。
  tl.add(c.show(), 0.2)
    .add(c.to(sys1, { duration: 0.5 }), 0.3)
    .add(kit.flash(sys1, { color: "red", duration: 1.6 }), ">-0.15")
    .add(c.click(sys1), "<+0.25")
    .add(m1.open(), ">-0.05")
    .add(c.to(m1.items[2], { duration: 0.35 }), ">")
    .call(() => m1.hover(2), [], ">")
    .add(c.click(m1.items[2]), ">")
    .add(m1.close(), ">-0.2")
    .add(collapseSys(gsap, chat, sys1), ">-0.1")
    // 第二条：同样的动作，快版
    .add(c.to(sys2, { duration: 0.4 }), ">-0.1")
    .add(kit.flash(sys2, { color: "red", duration: 1.35 }), ">-0.1")
    .add(c.click(sys2), "<+0.15")
    .add(m2.open(0.16), ">-0.05")
    .add(c.to(m2.items[2], { duration: 0.28 }), ">")
    .call(() => m2.hover(2), [], ">")
    .add(c.click(m2.items[2]), ">")
    .add(m2.close(0.12), ">-0.25")
    .add(c.hide(), "<")
    .add(collapseSys(gsap, chat, sys2), ">-0.1");
  // 红色印章：kit.stamp 建元素后加 pd-stamp--red，入场手法与 kit.ok 一致
  const st = kit.stamp("已删除 · 2 条", { en: "DELETED" });
  st.classList.add("pd-stamp--red");
  tl.fromTo(st, { opacity: 0, scale: 1.5, rotate: -6 }, { opacity: 1, scale: 1, rotate: -3, duration: 0.32, ease: "power4.out", immediateRender: false }, ">-0.1")
    .to({}, { duration: 0.9 });
  return tl;
}

export default {
  "edit-text": editText,
  "edit-source": editSource,
  "edit-time": editTime,
  "edit-fields": editFields,
  "edit-restore": editRestore,
  "edit-fix-sender": editFixSender,
  "edit-flip-sides": editFlipSides,
  "edit-delete-sys": editDeleteSys,
};

// 本组专属的局部样式；统一注入一次
export const css = `
.pd-sheet.pd-edit-sheet--sm { width: 256px; top: 44px; bottom: auto; border: 1px solid var(--pd-line-strong); border-right: 0; border-radius: 6px 0 0 6px; box-shadow: -16px 12px 40px rgba(0, 0, 0, 0.5); }
.pd-root .pd-edit-meta { font-size: 9px; letter-spacing: 0.16em; color: var(--pd-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-root .pd-edit-sys { width: fit-content; margin: 0 auto; padding: 1px 8px; border-radius: 3px; color: var(--pd-dim); }
`;
