/* ════════════════════════════════════════════════════════════
   scenes / action.js — 微信动作（11 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入 / 已发送」印章并停留。

   这组的核心表达：在本应用（左窗）里操作，微信客户端（右窗）呈现对应结果。
   发送类统一用 kit.twin 双窗口 + kit.sendFlow 编排；会话状态类使用同一个控件切换状态。
   ════════════════════════════════════════════════════════════ */

const AT_NAMES = ["小王", "阿明", "老张"];

/* 光标起点：落在左窗输入条附近，别从微信窗的「发送」键上滑进来 */
const CURSOR_AT = { x: 200, y: 360 };

/* ── 起手：双窗口 + 两边同一段聊天（各两条）；群聊里对方行带名字，自己的气泡不带（与微信一致） ── */
function setup(kit, { title = "老地方", group = false } = {}) {
  const twin = kit.twin({ title, group });
  const seed = (chat) => {
    if (!group) return chat.seed(2);
    const rows = [chat.time()];
    rows.push(chat.row("l", "周末回家吃饭吗", { name: "阿明", av: "明" }));
    rows.push(chat.row("r", "回，六点到家"));
    return rows;
  };
  return { twin, appRows: seed(twin.appChat), wxRows: seed(twin.wxChat) };
}

/* 输入框的可视区域（.pd-chat__field）：field 本身是空的 em，量不到宽度 */
const fieldBox = (chat) => chat.field.parentElement;

/* 打字期间光标挪到输入行下沿偏右，别压住正在打出来的字 */
const parkCursor = (cursor, chat, duration = 0.3) => cursor.to(fieldBox(chat), { dx: 64, dy: 14, duration });

/* ── 输入条上方的小面板：成员选择 / 选图 / 表情格共用一张脸 ── */
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

/* ── 选图 / 选视频 / 选表情之后：点下去面板就收、附件同时上输入区，光标不在空处多停，再交给 sendFlow 点发送 ── */
function pickBeat(kit, gsap, { cursor, icon, pop, target, attach }) {
  const b = gsap.timeline();
  b.add(cursor.tap(icon, { duration: 0.5 }))
    .add(pop.open(), ">-0.2")
    .add(cursor.to(target, { duration: 0.4 }), ">-0.05")
    .call(() => target.classList.add("is-on"))
    .add(cursor.click(target), ">")
    .add(pop.close(), ">-0.35");
  if (attach) {
    b.set(attach, { display: "flex" }, "<")
      .add(kit.pop(attach, { duration: 0.32 }), "<");
  }
  return b;
}

/* 点「发送」那一刻把输入区的附件收掉。
   sendFlow 里：beat 从 0.3 起，结束后 +0.15 光标出发、0.45 到达「发送」并点击 → 点击起点 = 0.3 + beat + 0.6 */
function clearAttachOnSend(flow, gsap, attach, beat) {
  const at = 0.3 + beat.duration() + 0.6;
  flow.to(attach, { opacity: 0, duration: 0.12 }, at).set(attach, { display: "none" }, at + 0.12);
}

/* ═══════════════ send-text 发送文字消息 ═══════════════ */
function sendText({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const text = "到楼下了，下来吧";
  const c = kit.cursor(CURSOR_AT);
  const flow = kit.sendFlow(twin, {
    c,
    beat: ({ cursor }) => {
      const b = gsap.timeline();
      // 点在输入框左沿，打字一开始光标就挪开，让打出来的字完整可见
      b.add(cursor.tap(fieldBox(appChat), { duration: 0.5, dx: -58 }))
        .add(parkCursor(cursor, appChat), ">-0.15")
        .add(kit.type(appChat.field, text, { cps: 13 }), "<")
        .to({}, { duration: 0.1 });
      return b;
    },
    build: () => kit.bubble(text, "r"),
  });
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-at 发送群聊 @ 消息 ═══════════════ */
function sendAt({ gsap, kit, tl }) {
  const { twin } = setup(kit, { title: "家人群", group: true });
  const { appChat } = twin;
  const field = appChat.field;
  const mention = (t) => kit.h("span", "pd-action-at__m", t);

  // 成员选择面板：打「@」时弹在输入条上方
  const pop = popover(kit, gsap, appChat.main, "pd-action-at", "选择提醒的人");
  const items = AT_NAMES.map((n, i) => {
    const it = kit.h("div", "pd-action-pop__it");
    it.append(kit.avatar(n[0], i % 2 ? "muted" : "them"), kit.h("span", "", n));
    pop.el.appendChild(it);
    return it;
  });

  const c = kit.cursor(CURSOR_AT);
  const flow = kit.sendFlow(twin, {
    c,
    beat: ({ cursor }) => {
      const typed = kit.h("span", "", "");
      const b = gsap.timeline();
      b.add(cursor.tap(fieldBox(appChat), { duration: 0.45, dx: -58 }))
        .add(kit.type(field, "@", { cps: 10 }), ">-0.15")
        .add(pop.open(), ">")
        .add(cursor.to(items[0], { duration: 0.4 }), ">-0.05")
        .call(() => items[0].classList.add("is-hover"))
        .add(cursor.click(items[0]), ">")
        .add(pop.close(), ">-0.25")
        // 输入框里的「@」变成蓝色的「@小王 」，接着继续打正文；光标同时从面板位置回到输入行下沿
        .call(() => { field.replaceChildren(mention("@小王"), document.createTextNode(" "), typed); field.classList.add("is-typing"); })
        .add(parkCursor(cursor, appChat, 0.35), ">")
        .add(kit.type(typed, "记得带伞", { cps: 12, caret: false }), "<+0.05")
        .call(() => field.classList.remove("is-typing"))
        .to({}, { duration: 0.1 });
      return b;
    },
    build: () => {
      const bub = kit.bubble("", "r");
      bub.append(mention("@小王"), document.createTextNode(" 记得带伞"));
      return bub;
    },
  });
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-image 发送图片消息 ═══════════════ */
function sendImage({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const icon = appChat.tools.children[1];
  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "选择图片");
  const grid = kit.h("div", "pd-action-pick__grid");
  const thumbs = [0, 1, 2].map(() => { const t = kit.h("i", "pd-action-thumb"); t.appendChild(kit.icon("image")); grid.appendChild(t); return t; });
  pop.el.appendChild(grid);
  const attach = attachment(kit, gsap, appChat, { name: "IMG_2041.jpg" });

  const c = kit.cursor(CURSOR_AT);
  const beat = pickBeat(kit, gsap, { cursor: c, icon, pop, target: thumbs[1], attach });
  const flow = kit.sendFlow(twin, { c, beat: () => beat, build: () => kit.card.image({ w: 110, hh: 80 }) });
  clearAttachOnSend(flow, gsap, attach, beat);
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-video 发送视频消息 ═══════════════ */
function sendVideo({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const icon = appChat.tools.children[1];
  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "选择视频");
  const grid = kit.h("div", "pd-action-pick__grid");
  const durs = ["0:21", "0:08", "1:02"];
  const thumbs = durs.map((d) => {
    const t = kit.h("i", "pd-action-thumb pd-action-thumb--video");
    t.append(kit.icon("play", "pd-ic pd-action-thumb__play"), kit.h("b", "pd-action-thumb__dur", d));
    grid.appendChild(t);
    return t;
  });
  pop.el.appendChild(grid);
  // 时长已经在缩略图和视频卡上各出现一次，输入区只放文件名，免得被截成半截
  const attach = attachment(kit, gsap, appChat, { video: true, name: "VID_0917.mp4" });

  const c = kit.cursor(CURSOR_AT);
  const beat = pickBeat(kit, gsap, { cursor: c, icon, pop, target: thumbs[1], attach });
  const flow = kit.sendFlow(twin, { c, beat: () => beat, build: () => kit.card.video({ dur: "0:08" }) });
  clearAttachOnSend(flow, gsap, attach, beat);
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-emoji 发送表情消息 ═══════════════ */
// 表情格：三种图标混排、各自带一点歪斜与深浅，像一版真的贴纸；第 6 格（heart）是要发出去的那一枚
const EMO_CELLS = [
  ["smile", -6, 0.85], ["heart", 5, 0.75], ["hand", -3, 1], ["smile", 7, 0.8],
  ["hand", -8, 0.9], ["heart", -4, 1], ["smile", 6, 0.7], ["hand", 4, 0.85],
];
const PICKED_EMO = 5;
function sendEmoji({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const icon = appChat.tools.children[0];
  const pop = popover(kit, gsap, appChat.main, "pd-action-emo", "表情");
  const grid = kit.h("div", "pd-action-emo__grid");
  const sticker = (name, rot, op = 1) => { const s = kit.icon(name); s.style.transform = `rotate(${rot}deg)`; s.style.opacity = op; return s; };
  const cells = EMO_CELLS.map(([name, rot, op]) => { const e = kit.h("i", ""); e.appendChild(sticker(name, rot, op)); grid.appendChild(e); return e; });
  pop.el.appendChild(grid);
  const [pickName, pickRot] = EMO_CELLS[PICKED_EMO];
  // 选中的那一枚先在输入区露个脸，再点发送
  const attach = kit.h("i", "pd-action-attach pd-action-attach--emo");
  const th = kit.h("b", "pd-action-attach__th"); th.appendChild(sticker(pickName, pickRot));
  attach.append(th, kit.h("span", "pd-action-attach__n", "表情"));
  fieldBox(appChat).insertBefore(attach, appChat.field);
  gsap.set(attach, { display: "none" });

  const c = kit.cursor(CURSOR_AT);
  const beat = pickBeat(kit, gsap, { cursor: c, icon, pop, target: cells[PICKED_EMO], attach });
  const flow = kit.sendFlow(twin, {
    c, beat: () => beat,
    // 发出去的表情卡就是选中的那一枚
    build: () => { const card = kit.card.emoji(); card.replaceChildren(sticker(pickName, pickRot)); return card; },
  });
  clearAttachOnSend(flow, gsap, attach, beat);
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-file 发送文件消息 ═══════════════ */
function sendFile({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const icon = appChat.tools.children[2];
  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "选择文件");
  const files = ["会议纪要.pdf", "项目清单.xlsx", "资料.zip"];
  const list = kit.h("div", "pd-action-filelist");
  const rows = files.map((name) => {
    const row = kit.h("i", "pd-action-thumb pd-action-file");
    row.append(kit.icon("file"), kit.h("b", "pd-action-file__name", name));
    list.appendChild(row);
    return row;
  });
  pop.el.appendChild(list);
  const name = files[0];
  const attach = attachment(kit, gsap, appChat, { iconName: "file", name });
  const c = kit.cursor(CURSOR_AT);
  const beat = pickBeat(kit, gsap, {
    cursor: c, icon, pop, target: rows[0], attach,
  });
  const flow = kit.sendFlow(twin, {
    c, beat: () => beat,
    stamp: "演示 · 已发送", en: "DEMO · SENT",
    build: () => kit.card.file({ name, size: "2.4 MB" }),
  });
  clearAttachOnSend(flow, gsap, attach, beat);
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-link 发送链接卡片 ═══════════════ */
function sendLink({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const url = "https://example.com";
  const title = "周末活动详情";
  const desc = "点击查看活动安排";
  const c = kit.cursor(CURSOR_AT);
  const flow = kit.sendFlow(twin, {
    c,
    stamp: "演示 · 已发送", en: "DEMO · SENT",
    beat: ({ cursor }) => {
      const b = gsap.timeline();
      b.add(cursor.tap(fieldBox(appChat), { duration: 0.5, dx: -58 }))
        .add(parkCursor(cursor, appChat), ">-0.15")
        .add(kit.type(appChat.field, url, { cps: 12 }), "<")
        .to({}, { duration: 0.35 });
      return b;
    },
    build: () => kit.card.link({ title, desc }),
  });
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-voice 发送语音消息 ═══════════════ */
function sendVoice({ gsap, kit, tl }) {
  const { twin } = setup(kit);
  const { appChat } = twin;
  const icon = appChat.tools.children[2];
  const pop = popover(kit, gsap, appChat.main, "pd-action-pick", "选择语音");
  const paths = ["问候.mp3", "会议录音.mp3", "提醒.mp3"];
  const list = kit.h("div", "pd-action-filelist");
  const rows = paths.map((name) => {
    const row = kit.h("i", "pd-action-thumb pd-action-file");
    row.append(kit.icon("file"), kit.h("b", "pd-action-file__name", name));
    list.appendChild(row);
    return row;
  });
  pop.el.appendChild(list);
  const attach = attachment(kit, gsap, appChat, {
    iconName: "file", name: paths[0],
  });
  const convert = kit.h("div", "pd-action-convert");
  convert.append(kit.icon("voice"), kit.h("span", "", "转换为语音 · 示意"));
  appChat.main.appendChild(convert);
  gsap.set(convert, { opacity: 0, y: 4 });
  const c = kit.cursor(CURSOR_AT);
  const beat = pickBeat(kit, gsap, {
    cursor: c, icon, pop, target: rows[0], attach,
  });
  beat.to(convert, { opacity: 1, y: 0, duration: 0.25 }, ">+0.1")
    .to({}, { duration: 0.55 })
    .to(convert, { opacity: 0, y: -3, duration: 0.2 }, ">-0.05");

  const flow = kit.sendFlow(twin, {
    c, beat: () => beat,
    stamp: "演示 · 已发送", en: "DEMO · SENT",
    build: () => kit.card.voice({ sec: 3, side: "r" }),
  });
  clearAttachOnSend(flow, gsap, attach, beat);
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ send-pat 发送拍一拍 ═══════════════ */
function sendPat({ gsap, kit, tl }) {
  const { twin, appRows, wxRows } = setup(kit);
  const appAv = appRows[1].av, wxAv = wxRows[1].av;   // 对方那行的头像
  const c = kit.cursor(CURSOR_AT);
  const shake = (el) => gsap.to(el, { keyframes: [
    { x: -3, rotate: -9, duration: 0.07 }, { x: 3, rotate: 9, duration: 0.07 },
    { x: -3, rotate: -6, duration: 0.07 }, { x: 3, rotate: 6, duration: 0.07 },
    { x: -1.5, rotate: -3, duration: 0.07 }, { x: 0, rotate: 0, duration: 0.07 },
  ] });

  // 双击头像 → 头像抖动，抖动尾巴直接接上「拍了拍」那行弹出，中间不留光标死停
  const beat = gsap.timeline();
  beat.add(c.dbl(appAv, { duration: 0.6 }))
    .add(shake(appAv), ">-0.3")
    .to({}, { duration: 0.1 });

  const flow = kit.sendFlow(twin, {
    c, beat: () => beat, side: "sys", noSendButton: true,
    // 「拍了拍」那行收紧到文字宽度，落库描边贴着字走，不横贯整个列表
    build: () => { const p = kit.pat({ from: "我", to: "友" }); p.classList.add("pd-action-pat"); return p; },
  });
  // 右窗那条「拍了拍」落下的同时，微信那边的头像也抖一下
  flow.add(shake(wxAv), 0.3 + beat.duration() + 1.05);
  tl.add(flow, 0);
  return tl;
}

/* ═══════════════ chat-mark-read 会话标记已读 ═══════════════ */
function markRead({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  chat.seed(3);
  const session = chat.sessions[0];
  const unread = kit.h("i", "pd-action-unread", "3");
  session.querySelector(".pd-sess__txt").appendChild(unread);
  const action = kit.h("b", "pd-action-state-btn", "标记已读");
  chat.head.appendChild(action);
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.to(session, { duration: 0.45 }), 0.35)
    .add(c.click(session), ">")
    .add(c.to(action, { duration: 0.4 }), ">+0.15")
    .add(c.click(action), ">")
    .to(unread, { opacity: 0, scale: 0.5, duration: 0.3, ease: "back.in(2)" }, ">-0.05")
    .add(kit.flash(session, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("演示 · 本地已读", { en: "DEMO · READ LOCAL" }), ">-0.1")
    .add(c.hide(), "<");
  return tl;
}

/* ═══════════════ chat-set-mute 会话免打扰 ═══════════════ */
function setMute({ gsap, kit, tl }) {
  const chat = kit.chat({ title: "老地方" });
  chat.seed(2);
  const session = chat.sessions[0];
  const status = kit.h("i", "pd-action-state", "免打扰：关闭");
  session.querySelector(".pd-sess__txt").appendChild(status);
  const toggle = kit.h("b", "pd-action-state-btn", "开启免打扰");
  chat.head.appendChild(toggle);
  const c = kit.cursor();

  tl.add(c.show(), 0.2)
    .add(c.to(session, { duration: 0.45 }), 0.35)
    .add(c.click(session), ">")
    .add(c.to(toggle, { duration: 0.4 }), ">+0.15")
    .add(c.click(toggle), ">")
    .call(() => {
      toggle.textContent = "关闭免打扰";
      toggle.classList.add("is-on");
      status.textContent = "免打扰：开启";
    }, [], "<+0.12")
    .add(kit.flash(status, { color: "amber", duration: 0.7 }), "<")
    .add(kit.ok("演示 · 已开启", { en: "DEMO · MUTE ON" }), ">-0.1")
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
/* 输入条上方的小面板 */
.pd-action-pop {
  position: absolute; left: 12px; bottom: 60px; z-index: 20; padding: 6px;
  background: #131a16; border: 1px solid var(--pd-line-strong); border-radius: 5px;
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.6);
}
.pd-action-pop__h { display: block; font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.16em; color: var(--pd-faint); padding: 2px 4px 6px; white-space: nowrap; }
.pd-action-pop__it { display: flex; align-items: center; gap: 8px; min-width: 124px; padding: 4px 8px 4px 5px; border-radius: 3px; font-size: 11.5px; color: var(--pd-ink); white-space: nowrap; }
.pd-action-pop__it .pd-av { width: 20px; height: 20px; font-size: 9px; border-radius: 3px; }
.pd-action-pop__it.is-hover { background: rgba(255, 194, 75, 0.14); color: var(--pd-amber); }
.pd-action-at__m { color: var(--pd-blue); }

/* 选图 / 选视频 */
.pd-action-pick__grid { display: flex; gap: 6px; padding: 0 2px 2px; }
.pd-action-thumb {
  position: relative; width: 64px; height: 44px; border-radius: 3px; flex: none;
  background: var(--pd-tile); border: 1px solid transparent; display: grid; place-items: center; color: var(--pd-faint);
}
.pd-action-thumb .pd-ic { width: 18px; height: 18px; }
.pd-action-thumb__play { color: var(--pd-ink); opacity: 0.85; }
.pd-action-thumb__dur { position: absolute; right: 4px; bottom: 2px; font-family: var(--pd-mono); font-weight: 400; font-size: 9px; letter-spacing: 0; color: var(--pd-ink); opacity: 0.8; }
.pd-action-thumb.is-on { border-color: var(--pd-amber); box-shadow: 0 0 0 2px rgba(255, 194, 75, 0.22); color: var(--pd-amber); }
.pd-action-thumb.is-on .pd-action-thumb__play { color: var(--pd-amber); opacity: 1; }
.pd-action-filelist { display: flex; gap: 6px; padding: 0 2px 2px; }
.pd-action-file { width: 78px; height: 52px; display: flex; flex-direction: column; gap: 3px; padding: 6px 4px 4px; }
.pd-action-file .pd-ic { width: 17px; height: 17px; }
.pd-action-file__name { max-width: 68px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--pd-mono); font-size: 8px; font-weight: 400; }

/* 表情格 */
.pd-action-emo__grid { display: grid; grid-template-columns: repeat(4, 30px); gap: 5px; padding: 0 2px 2px; }
.pd-action-emo__grid i { width: 30px; height: 30px; border-radius: 4px; display: grid; place-items: center; color: var(--pd-dim); background: rgba(255, 255, 255, 0.04); border: 1px solid transparent; }
.pd-action-emo__grid i .pd-ic { width: 17px; height: 17px; }
.pd-action-emo__grid i.is-on { color: var(--pd-amber); background: rgba(255, 194, 75, 0.12); border-color: rgba(255, 194, 75, 0.55); }
.pd-action-emo__grid i.is-on .pd-ic { opacity: 1 !important; }

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

/* MP3 转换提示：仅表达产品流程，不展开底层实现 */
.pd-action-convert {
  position: absolute; left: 106px; right: 66px; bottom: 13px; height: 28px; z-index: 6;
  display: flex; align-items: center; gap: 7px; padding: 0 8px; border-radius: 3px;
  background: rgba(255, 194, 75, 0.08); border: 1px solid rgba(255, 194, 75, 0.35);
  font-size: 11px; color: var(--pd-ink); white-space: nowrap;
}
.pd-action-convert .pd-ic { width: 14px; height: 14px; color: var(--pd-amber); }

/* 会话状态：按钮在同一位置切换开 / 关，列表副标题只作当前状态提示 */
.pd-action-state-btn { margin-left: auto; flex: none; padding: 4px 8px; border: 1px solid rgba(255, 194, 75, 0.45); border-radius: 3px; color: var(--pd-amber); font-size: 10px; font-weight: 500; white-space: nowrap; }
.pd-action-state-btn.is-on { border-color: rgba(61, 242, 141, 0.45); color: var(--pd-neon); background: rgba(61, 242, 141, 0.12); }
.pd-action-unread { display: inline-flex; align-items: center; justify-content: center; width: 15px; height: 15px; margin-left: 2px; border-radius: 50%; background: var(--pd-red); color: #fff; font-family: var(--pd-mono); font-size: 8px; font-style: normal; }
.pd-action-state { color: var(--pd-faint); font-family: var(--pd-mono); font-size: 8px; font-style: normal; }

/* 拍一拍那行：收紧到文字宽度，落库描边贴着字走 */
.pd-action-pat { align-self: center; width: max-content; padding: 1px 8px; border-radius: 3px; }
`;
