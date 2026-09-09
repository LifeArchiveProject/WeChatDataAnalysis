/* ════════════════════════════════════════════════════════════
   scenes / edit.js — 消息修改（8 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   本组是「只写本地解密副本」的能力：单向、不回写微信，对方永远看不到。
   所以每个场景都必须 kit.scenario(text, { local: true })，情境条上常驻「本地副本 · 不回写微信」。
   世界观（全组统一）：一气之下清空了和 TA 的聊天记录，事后想找回——
   能从备份恢复的恢复，恢复回来错乱的校订，恢复不了的按截图、相册、账单一条条补回本地副本。
   会话与文案一律私人语境（小满 / 家人群 / 老同学 / 室友），情境与结果只讲我这边的存档，
   不许出现「对方收到」「TA 就知道了」这类外部效果；也不要 kit.workflow（这是人在整理自己的档案）。
   时长 4.5–7.5 秒，结尾用 kit.ok() 盖印章并停留。统一起手：kit.chat() + 右键目标气泡弹 kit.menu。
   ════════════════════════════════════════════════════════════ */

/* ───────────────────────── 本组共用的私人语境 ───────────────────────── */

// 会话是「小满」，侧栏是自己的几个常用会话——本地存档类一律私人语境，不要客户/报价/合同
const HER = "小满";
const AV = "满";
const RAIL = ["家人群", "老同学", "室友"];
const myChat = (kit) => kit.chat({ title: HER, railNames: RAIL });

// 示范场景（场景优先的范本）：恢复回来的那句话和截图对不上 → 原地改回原话 → 本地存档与截图一致
function editText({ kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("按截图核对 · 这句话改错了", { local: true });
  chat.time("2024-08-09 21:40");
  chat.row("l", "你上次说几号来", { av: AV });
  const mine = chat.row("r", "我十九号下午两点到");        // 恢复回来的版本，和截图差了一个字
  chat.row("l", "好，九号那天我去接你", { av: AV });        // 下一句坐实了原话是「九号」
  const target = mine.content;
  const c = kit.cursor();
  const menu = kit.menu([{ icon: "edit", label: "修改文字" }, { icon: "code", label: "编辑源码" }, { icon: "clock", label: "修改时间" }, { icon: "trash", label: "删除", danger: true }], { at: target, dx: 14, dy: 6 });

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(c.tap(target), 0.35)
    .add(menu.open(), ">-0.05")
    .add(c.to(menu.items[0], { duration: 0.35 }), ">")
    .call(() => menu.hover(0))
    .add(c.click(menu.items[0]), ">")
    .add(menu.close(), ">")
    .call(() => target.classList.add("is-edit"))
    .add(kit.type(target, "我九号下午两点到", { cps: 12 }), ">+0.1")
    .add(c.to(chat.send, { duration: 0.4 }), ">+0.2")
    .add(c.click(chat.send), ">")
    .call(() => { target.classList.remove("is-edit"); target.appendChild(kit.tag("已修改")); })
    .add(kit.flash(target, { color: "amber", duration: 0.6 }), "<")
    .add(kit.ok("已写入 message_0.db"), ">-0.2")
    .add(strip.result("和截图对上了"), "<")
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

// 编辑消息源码：恢复回来的那张歌曲链接卡片标题成了乱码 → 右键编辑源码 → XML 的 <title> 改回原话 → 卡片标题重新可读
function editSource({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("恢复回来的卡片标题乱码", { local: true });
  chat.time("2023-07-08 21:14");
  chat.row("l", "上次你发我的那首歌", { av: AV });
  const card = kit.card.link({ title: "锟斤拷锟侥筹拷锟斤拷", desc: "单曲 · 3 分 42 秒" });
  card.querySelector(".pd-card__foot").textContent = "网易云音乐";   // link 卡片的页脚默认写死「公众号 · 文章」，这里换成真正的来源
  const row = chat.row("r", card);
  chat.row("l", "就是它，循环了一晚上", { av: AV });
  const title = card.querySelector(".pd-card__txt b");
  const target = row.content;
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.time, MI.del], pick: 1 });
  const sheet = kit.sheet({ title: "消息源码 · XML" });
  const code = kit.code([
    "<appmsg>",
    " <title>锟斤拷锟侥筹拷锟斤拷</title>",
    " <des>单曲 · 3 分 42 秒</des>",
    " <url>music.163.com/s/2023</url>",
    " <type>3</type>",
    "</appmsg>",
  ], sheet.body);
  sheet.body.appendChild(kit.h("p", "pd-edit-meta mono", "message_0.db · local_id 20871"));
  const ln = code.lines[1], span = ln.lastElementChild;

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(c.to(title, { duration: 0.4, dy: 12 }), 0.35)       // 先停在乱码标题上：交代问题出在哪
    .add(kit.flash(card, { color: "red", duration: 0.5 }), ">-0.1")
    .add(rc, ">-0.25")
    .add(sheet.open(), ">-0.1")
    .add(c.to(ln, { duration: 0.4 }), ">-0.1")
    .add(c.click(ln), ">")
    .call(() => ln.classList.add("is-edit"), [], ">-0.25")
    .add(kit.scramble(span, " <title>那年我们一起听的歌</title>", { duration: 0.6 }), ">")
    .add(c.to(sheet.ok, { duration: 0.4 }), ">+0.05")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">-0.15")
    .add(c.hide(), "<")                                       // 抽屉滑走后光标退场，卡片落定成为唯一焦点
    .call(() => card.classList.add("is-edit"), [], ">-0.1")
    .add(kit.scramble(title, "那年我们一起听的歌", { duration: 0.5 }), ">")
    .call(() => card.classList.remove("is-edit"))
    .add(kit.flash(card, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已写入 · XML", { en: "SOURCE WRITTEN" }), ">-0.3")
    .add(strip.result("卡片标题恢复可读"), "<");
  return tl;
}

// 修改时间：从备份恢复回来的这条时间戳是 0，被排到了整段最前 → 改回真实那天 → 这一行滑回它本该在的位置
function editTime({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("从备份恢复 · 时间戳错乱", { local: true });
  // 时间戳 0 的那条按序排在最前：恢复时丢字段的典型症状，一眼能看出它站错了地方
  const tlabel = kit.h("p", "pd-time pd-edit-tlabel", "1970-01-01 08:00");
  tlabel.appendChild(kit.tag("时间戳 = 0", "pd-tag--red"));
  chat.list.appendChild(tlabel);
  const row = chat.row("r", "刚到，路上下了好大的雨");
  // 下面这三行才是它真正的上下文：改完时间后，它要滑到这三行之后
  const head = chat.time("2024-05-20 22:36");
  const ask = chat.row("l", "到家了吗", { av: AV });
  const after = chat.row("l", "雨下这么大，路上慢一点", { av: AV });
  const target = row.content;
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.time, MI.del], pick: 2 });
  const sheet = kit.sheet({ title: "修改时间", cls: "pd-edit-sheet--sm" });
  const form = kit.form([["display_time", "1970-01-01 08:00", true], ["create_time", "0", true]], sheet.body);
  const fTime = form.rows[0], fEpoch = form.rows[1];
  sheet.body.appendChild(kit.h("p", "pd-edit-meta mono", "改完即按时间重排"));
  const gap = () => parseFloat(getComputedStyle(chat.list).rowGap) || 10;
  const m = { down: 0, up: 0 };

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(kit.flash(tlabel, { color: "red", duration: 0.7 }), 0.3)
    .add(rc, ">-0.35")
    .add(sheet.open(), ">-0.1")
    .add(c.to(fTime.value, { duration: 0.4 }), ">-0.1")
    .add(c.click(fTime), ">")
    .call(() => fTime.classList.add("is-edit"), [], ">-0.25")
    .add(kit.scramble(fTime.value, "2024-05-20 22:41", { duration: 0.6 }), ">")
    .call(() => fEpoch.classList.add("is-edit"), [], "<+0.15")       // 时间戳跟着改：这一行也点亮
    .add(kit.count(fEpoch.value, 1716216060, { from: 0, duration: 0.6 }), "<")
    .add(c.to(sheet.ok, { duration: 0.35 }), ">")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">-0.15")
    .add(c.hide(), "<")                                             // 保存后光标退场，重排成为唯一焦点
    .add(kit.scramble(tlabel, "2024-05-20 22:41", { duration: 0.45 }), ">-0.1")
    .add(kit.flash(target, { color: "amber", duration: 0.6 }), "<")
    // 时间轴重排：这一行（连同它的时间标签）从最前滑到最后，它上面压着的三行整体顶上来
    .call(() => {
      const g = gap();
      const hA = kit.rect(row).y + kit.rect(row).h - kit.rect(tlabel).y;       // 错位那一段的高度
      const hB = kit.rect(after).y + kit.rect(after).h - kit.rect(head).y;     // 它要越过的三行
      m.down = hB + g; m.up = hA + g;
    }, [], "<+0.4")
    .to([tlabel, row], { y: () => m.down, duration: 0.6, ease: "power3.inOut" })
    .to([head, ask, after], { y: () => -m.up, duration: 0.6, ease: "power3.inOut" }, "<")
    .call(() => { chat.list.append(tlabel, row); gsap.set([tlabel, row, head, ask, after], { clearProps: "transform" }); })
    .add(kit.ok("已写入 · create_time", { en: "WRITTEN" }), ">-0.2")
    .add(strip.result("时间线按真实顺序重排"), "<");
  return tl;
}

// 字段编辑：恢复回来这条明明是我说的，status 与 is_sender 却错了 → 抽屉里逐项改回 → 气泡按新字段翻到我这边
function editFields({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("恢复的记录 · 字段错位", { local: true });
  chat.time("2024-11-03 19:08");
  chat.row("l", "周末回家吃饭吗", { av: AV });
  const row = chat.row("l", "回，我周六下午到", { av: AV });   // 我说的话，却带着 is_sender=0
  const target = row.content;
  target.appendChild(kit.tag("字段错位", "pd-tag--red"));
  chat.row("l", "那我提前买菜", { av: AV });
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.fields, MI.del], pick: 2 });
  const sheet = kit.sheet({ title: "字段编辑", cls: "pd-edit-sheet--sm" });
  const form = kit.form([["local_id", "20871", true], ["create_time", "1730632080", true], ["type", "1", true], ["status", "2", true], ["is_sender", "0", true]], sheet.body);
  const fStatus = form.rows[3], fSender = form.rows[4];
  const sw = crossSwap({ gsap, kit, chat, row, side: "r", text: "回，我周六下午到" });
  // 翻过去的气泡上回显改过的两个字段——让人看到「status」这种底层字段也真的写进去了。
  // 建场时先不挂：标签即使 opacity:0 也照样占宽度，会把正在横穿的气泡撑成一条空壳。翻面收尾再 append。
  const echo = [kit.tag("status=4"), kit.tag("is_sender=1")];

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(rc, 0.35)
    .add(sheet.open(), ">-0.1")
    .add(retype({ kit, c, field: fStatus, text: "4" }), ">-0.1")
    .add(retype({ kit, c, field: fSender, text: "1" }), ">-0.2")
    .add(c.to(sheet.ok, { duration: 0.3 }), ">")
    .add(c.click(sheet.ok), ">")
    .add(sheet.close(), ">-0.15")
    .add(c.hide(), "<")                                             // 保存后光标退场，翻面成为唯一焦点
    .add(sw, ">-0.1")
    .call(() => { sw.twin.content.append(...echo); gsap.set(echo, { opacity: 0, y: 4, scale: 0.9 }); }, [], ">-0.45")
    .fromTo(echo, { opacity: 0, y: 4, scale: 0.9 }, { opacity: 1, y: 0, scale: 1, duration: 0.3, stagger: 0.12, ease: "back.out(1.8)", immediateRender: false }, ">")
    .add(kit.ok("已写入 · 2 字段", { en: "2 FIELDS WRITTEN" }), ">-0.15")
    .add(strip.result("2 个字段已修正"), "<");
  return tl;
}

// 恢复原消息：跨年那句被我改成了客套话，想要回原话 → 右键恢复原消息 → 原文一字不差地回来
function editRestore({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("改过头了 · 要原话", { local: true });
  chat.time("2024-12-31 23:58");
  chat.row("l", "还有两分钟就跨年了", { av: AV });
  const row = chat.row("r", "");
  const target = row.content;
  const txt = kit.h("span", "", "新年快乐");     // 被改过头的版本
  const tag = kit.tag("已修改");
  target.replaceChildren(txt, tag);
  chat.row("l", "我也是", { av: AV });
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.source, MI.restore, MI.del], pick: 2, hide: true });

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(c.to(tag, { duration: 0.5, dy: 14 }), 0.35)       // 先停到「已修改」标签下：交代这条被我改过头了
    .add(kit.flash(target, { color: "amber", duration: 0.5 }), ">-0.1")
    .to({}, { duration: 0.3 }, "<")
    .add(rc, ">")
    .call(() => target.classList.add("is-edit"), [], ">-0.1")
    .add(kit.scramble(txt, "明年这天，还是我们俩", { duration: 0.65 }), ">")
    // 标签缩没：锁成单行再收窄，否则收窄途中「已修改」会折成两行把气泡撑高
    .set(tag, { overflow: "hidden", whiteSpace: "nowrap", width: () => kit.rect(tag).w }, "<+0.25")
    .to(tag, { width: 0, paddingLeft: 0, paddingRight: 0, marginLeft: 0, borderLeftWidth: 0, borderRightWidth: 0, opacity: 0, duration: 0.35, ease: "power2.in" }, "<")
    .set(tag, { display: "none" })
    .call(() => target.classList.remove("is-edit"))
    .add(kit.flash(target, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已恢复原文", { en: "RESTORED" }), ">-0.3")
    .add(strip.result("原来那句还回来了"), "<");
  return tl;
}

// 修复为我发送：恢复回来的记录里，明明是我说的话挂在了 TA 那一侧 → 右键修复为我发送 → 整行翻回我这边
function editFixSender({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("恢复的记录 · 归属错乱", { local: true });
  chat.time("2025-03-02 08:12");
  chat.row("l", "今天几点的高铁", { av: AV });
  const row = chat.row("l", "我订了下午三点那班", { av: AV });   // 明显是我说的，却挂在 TA 那侧
  const target = row.content;
  target.appendChild(kit.tag("归属错位", "pd-tag--red"));
  chat.row("l", "那我去站里等你", { av: AV });
  const c = kit.cursor();
  const rc = rightClick({ gsap, kit, c, target, items: [MI.text, MI.fix, MI.time, MI.del], pick: 1, hide: true });
  const sw = crossSwap({ gsap, kit, chat, row, side: "r", text: "我订了下午三点那班" });

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(c.to(target, { duration: 0.5, dy: 12 }), 0.35)    // 先停在挂错的那句上
    .add(kit.flash(target, { color: "red", duration: 0.6 }), ">-0.1")
    .add(rc, ">-0.35")
    .add(sw, ">-0.05")
    .add(kit.ok("已修正 · is_sender=1", { en: "FIXED" }), ">-0.2")
    .add(strip.result("归属回到我这边"), "<");
  return tl;
}

// 反转微信气泡位置：这份是从 TA 手机上导出的，TA 在右我在左 → 标题栏「···」→ 反转 → 整段翻成我的视角
function editFlipSides({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("从 TA 手机导出的那份", { local: true });
  chat.time("2025-01-11 19:20");
  const msgs = [
    chat.row("r", "我到楼下了", { av: AV }),          // 导出自 TA 手机：TA 自己在右侧
    chat.row("l", "马上下来", { av: "我" }),
    chat.row("r", "外面在下雨，带伞了吗", { av: AV }),
    chat.row("l", "带了，你等我一分钟", { av: "我" }),
  ];
  const c = kit.cursor();
  const menu = kit.menu([{ icon: "user", label: "聊天信息" }, { icon: "swap", label: "反转气泡位置" }, { icon: "file", label: "导出记录" }, { icon: "trash", label: "删除会话", danger: true }], { at: chat.more, dx: -8, dy: 12 });   // 右缘对齐「···」往下落，像真的下拉菜单，少压首行气泡
  // 每行离场时朝它将要去的那边滑，翻面后再从另一侧滑进来，方向连贯
  const out = (r) => (r.classList.contains("pd-row--r") ? -40 : 40);
  const flip = (r) => {
    const toR = !r.classList.contains("pd-row--r");
    r.classList.toggle("pd-row--r", toR); r.classList.toggle("pd-row--l", !toR);
    r.av.textContent = toR ? "我" : AV;
    r.av.classList.toggle("pd-av--me", toR); r.av.classList.toggle("pd-av--them", !toR);
    r.content.classList.toggle("pd-bub--r", toR); r.content.classList.toggle("pd-bub--l", !toR);
  };

  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(c.tap(chat.more), 0.35)
    .add(menu.open(), ">-0.05")
    .add(c.to(menu.items[1], { duration: 0.35 }), ">")
    .call(() => menu.hover(1))
    .add(c.click(menu.items[1]), ">")
    .add(menu.close(), ">-0.2")
    .add(c.hide(), "<");                                            // 点完就退场，翻面成为唯一焦点
  // 逐行翻：出场与入场咬合（下一行开始退场时，上一行已经从对面滑回来了），
  // 别等四行全退完再整体滑回——那 0.5s 屏幕是空的，看着像「记录被清空了」而不是「左右互换」。
  msgs.forEach((r, i) => {
    const o = out(r);                                               // 离场方向＝它现在这一侧；翻面后正好从 -o 那边进来
    tl.to(r, { x: o, opacity: 0, duration: 0.2, ease: "power2.in", onComplete: () => flip(r) }, i ? ">-0.16" : ">-0.05")
      .fromTo(r, { x: -o, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3, ease: "power3.out", immediateRender: false }, ">-0.02");
  });
  tl.add(kit.flash(msgs[msgs.length - 1].content, { color: "neon", duration: 0.6 }), ">-0.2")
    .add(kit.ok(`已反转 · ${msgs.length} 条`, { en: "FLIPPED" }), ">-0.3")
    .add(strip.result("已翻成我的视角"), "<");
  return tl;
}

// 删除系统消息：把这段找回来的对话导成纪念册之前，两条撤回提示逐条清掉 → 导出稿只剩我们说过的话
function editDeleteSys({ gsap, kit, tl }) {
  const chat = myChat(kit);
  const strip = kit.scenario("导出纪念册前 · 清系统提示", { local: true });
  chat.time("2025-06-18 20:30");
  chat.row("l", "第一次见面那天你迟到了", { av: AV });
  // 撤回提示前后刷了三条，其中两条还挨在一起：先把挨着的两条一并选中删掉，剩下那条再单独清
  const sys1 = chat.sys("小满撤回了一条消息");
  const sys2 = chat.sys("你撤回了一条消息");
  chat.row("r", "我记得明明是你迟到");
  const sys3 = chat.sys("小满撤回了一条消息");
  chat.row("l", "好好好，是我", { av: AV });
  [sys1, sys2, sys3].forEach((s) => s.classList.add("pd-edit-sys"));
  const c = kit.cursor();
  const items = [MI.source, MI.time, { icon: "trash", label: "删除系统消息", danger: true }];
  // 往左让足余量：菜单右缘要离居中的系统行有肉眼可见的间隙，也别压住左侧气泡
  const m1 = kit.menu([MI.source, MI.time, { icon: "trash", label: "删除这 2 条", danger: true }], { at: sys1, dx: -196, dy: 10 });
  const m2 = kit.menu(items, { at: sys3, dx: 42, dy: 8 });

  // 红框一直亮到点下「删除系统消息」为止（flash 时长盖过整段菜单操作），目标行不失焦。
  // 注意 flash 拉长后它就是时间轴最长的那条，后面的 .call 必须显式给 ">"，否则会被排到 flash 结束处。
  tl.add(strip.in(), 0.1)
    .add(c.show(), 0.25)
    .add(c.to(sys1, { duration: 0.5 }), 0.35)
    .add(kit.flash(sys1, { color: "red", duration: 1.5 }), ">-0.15")
    .add(kit.flash(sys2, { color: "red", duration: 1.5 }), "<")     // 挨着的两条一起亮红框＝一起选中
    .add(c.click(sys1), "<+0.25")
    .add(m1.open(), ">-0.05")
    .add(c.to(m1.items[2], { duration: 0.35 }), ">")
    .call(() => m1.hover(2), [], ">")
    .add(c.click(m1.items[2]), ">")
    .add(m1.close(), ">-0.2")
    .add(collapseSys(gsap, chat, sys1), ">-0.1")
    .add(collapseSys(gsap, chat, sys2), "<+0.06")                   // 两条一起折掉，下面的行顺势顶上来
    // 剩下那条：同样的动作，快版
    .add(c.to(sys3, { duration: 0.4 }), ">-0.1")
    .add(kit.flash(sys3, { color: "red", duration: 1.35 }), ">-0.1")
    .add(c.click(sys3), "<+0.15")
    .add(m2.open(0.16), ">-0.05")
    .add(c.to(m2.items[2], { duration: 0.28 }), ">")
    .call(() => m2.hover(2), [], ">")
    .add(c.click(m2.items[2]), ">")
    .add(m2.close(0.12), ">-0.25")
    .add(c.hide(), "<")
    .add(collapseSys(gsap, chat, sys3), ">-0.1");
  // 红色印章：kit.stamp 建元素后加 pd-stamp--red，入场手法与 kit.ok 一致
  const st = kit.stamp("已删除 · 3 条", { en: "DELETED" });
  st.classList.add("pd-stamp--red");
  tl.fromTo(st, { opacity: 0, scale: 1.5, rotate: -6 }, { opacity: 1, scale: 1, rotate: -3, duration: 0.32, ease: "power4.out", immediateRender: false }, ">-0.1")
    .add(strip.result("导出稿干净了"), "<")
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
/* 错乱的时间标签：收成小药丸，红框才贴着它而不是横穿整行 */
.pd-root .pd-edit-tlabel { width: fit-content; margin: 0 auto; padding: 2px 8px; border-radius: 3px; }
`;
