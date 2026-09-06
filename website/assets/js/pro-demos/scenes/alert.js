/* ════════════════════════════════════════════════════════════
   scenes / alert.js — 提醒（1 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖印章并停留。
   布局：左 230px 是「关键词提醒」设置面板（本文件自建 pd-alert-*），右侧是一张群聊窗。
   ════════════════════════════════════════════════════════════ */

// 群聊/单聊关键词提醒：面板里打字加一个关键词「发票」→ 右边群聊实时涌入三条消息，每条都被扫一遍
// → 第三条命中「发票」亮起 → 一粒光点飞回芯片、芯片点亮 → 面板记下这次命中 → 右上滑入系统通知 → 印章
function alertKeyword({ gsap, kit, tl }) {
  const h = kit.h;

  /* ── 布局：左面板 + 右群聊 ── */
  const wrap = kit.mount(h("div", "pd-alert"));
  const panel = h("aside", "pd-alert-panel");
  const chatHost = h("div", "pd-alert-chat");
  wrap.append(panel, chatHost);

  // 面板头
  const head = h("div", "pd-alert-panel__head");
  const title = h("b", "pd-alert-panel__t");
  title.append(kit.icon("bell"), h("span", "", "关键词提醒"));
  head.append(h("i", "pd-alert-panel__k", "KEYWORD · ALERT"), title);
  panel.appendChild(head);

  // 关键词芯片区 + 输入条（骨架占位 + 琥珀光标）+「添加」小按钮
  panel.appendChild(h("p", "pd-alert-label", "关键词"));
  const chips = kit.chips(["报销"], { parent: panel });
  const chipNew = chips.add("发票");            // 预建，添加时再弹入
  gsap.set(chipNew, { display: "none" });
  const inputRow = h("div", "pd-alert-input");
  const box = h("span", "pd-alert-input__box");
  const ph = kit.skel(64, 6);                   // 输入条里的占位骨架
  const em = h("em", "pd-alert-input__text");
  box.append(ph, em, h("i", "pd-caret"));
  const addBtn = h("b", "pd-btn pd-btn--amber pd-alert-add");
  addBtn.append(kit.icon("plus"), h("span", "", "添加"));
  inputRow.append(box, addBtn);
  panel.appendChild(inputRow);

  // 监听范围：群聊 + 单聊，两行都已勾上
  panel.appendChild(h("p", "pd-alert-label", "监听范围"));
  const scope = h("div", "pd-alert-scope");
  const scopeRow = (av, name) => {
    const r = h("div", "pd-alert-scope__row");
    const ck = h("i", "pd-check is-on");
    ck.appendChild(kit.icon("check"));
    r.append(av, h("b", "", name), kit.skel(60, 5), ck);
    scope.appendChild(r);
    return r;
  };
  scopeRow(kit.avatar("群", "muted"), "群聊");
  scopeRow(kit.avatar("友", "them"), "单聊");
  panel.appendChild(scope);

  // 命中记录：起手一行「暂无命中」，命中后落成真实记录
  panel.appendChild(h("p", "pd-alert-label", "命中记录"));
  const log = h("div", "pd-alert-log");
  const logRow = h("div", "pd-alert-log__row");
  const logKw = h("b", "", "");
  const logTxt = h("em", "", "暂无命中");
  logRow.append(logKw, logTxt);
  log.appendChild(logRow);
  panel.appendChild(log);

  // 面板底部的实时状态行
  const live = h("p", "pd-alert-live");
  live.append(h("i"), h("span", "", "实时检测 · 群聊 + 单聊"));
  panel.appendChild(live);

  /* ── 右侧群聊：时间行 + 一条旧消息；标题旁挂 LIVE 标 ── */
  const chat = kit.chat({ title: "同事", group: true, rail: false, parent: chatHost });
  chat.title.appendChild(kit.tag("LIVE", "pd-tag--neon pd-alert-livetag"));
  chat.time("今天 14:02");
  chat.row("l", "周报下班前发群里", { name: "小王", av: "王" });

  // 预建三条实时消息（display none）；每条气泡里放一道扫描光，表示「每条新消息都被检测一遍」
  const withScan = (bub) => { const s = h("i", "pd-alert-scan"); const b = h("b"); s.appendChild(b); bub.appendChild(s); return b; };
  const mk = (name, av, content) => { const r = chat.row("l", content, { name, av }); gsap.set(r, { display: "none" }); return r; };
  const r1 = mk("小王", "王", "会议改到三点"), beam1 = withScan(r1.content);
  const r2 = mk("阿明", "明", "午饭吃啥"), beam2 = withScan(r2.content);
  const bub3 = kit.bubble("", "l");
  const mark = h("mark", "pd-alert-hit", "发票");
  bub3.append(mark, "开好了，明天给你");
  const r3 = mk("老张", "张", bub3), beam3 = withScan(bub3);

  /* ── 通知、光点、光标 ── */
  const toast = kit.toast({ title: "关键词命中：发票", body: "", app: "WeChatDataAnalysis · 系统通知" });
  toast.el.classList.add("pd-alert-toast");
  toast.body.append("同事 · 老张：", h("mark", "", "发票"), "开好了，明天给你");
  const spark = kit.mount(h("i", "pd-alert-spark"));
  gsap.set(spark, { opacity: 0 });
  const c = kit.cursor();
  const R = kit.rect;

  // 一条消息实时弹入：显示 → 弹入 → 扫描光横扫一遍
  const incoming = (row, beam, at) => {
    tl.set(row, { display: "flex" }, at)
      .add(kit.pop(row), at)
      .fromTo(beam, { xPercent: -120 }, { xPercent: 320, duration: 0.3, ease: "none", immediateRender: false }, at + 0.12);
  };

  /* ── 第一段：在面板里添加关键词「发票」 ── */
  tl.add(c.show(), 0.2)
    .add(c.to(box, { duration: 0.5, dx: 22 }), 0.3)       // 落在输入条右半空处，别压住光标和正在打的字
    .add(c.click(box), 0.8)
    .call(() => { box.classList.add("is-focus"); em.classList.add("is-typing"); }, [], 0.85)
    .set(ph, { display: "none" }, 0.85)
    .add(kit.type(em, "发票", { cps: 5 }), 1.05)
    .call(() => em.classList.add("is-typing"), [], 1.46)      // 打完字光标继续闪，直到点「添加」
    .add(c.to(addBtn, { duration: 0.35 }), 1.7)
    .add(c.click(addBtn), 2.05)
    .call(() => { em.textContent = ""; em.classList.remove("is-typing"); box.classList.remove("is-focus"); }, [], 2.15)
    .set(ph, { display: "block" }, 2.15)
    .set(chipNew, { display: "inline-block" }, 2.15)
    .add(kit.pop(chipNew), 2.15)
    .add(kit.flash(chipNew, { color: "amber", duration: 0.5 }), 2.15)
    .add(c.hide(), 2.6);                                       // 点完「添加」就退场：后面全是系统自己在干活

  /* ── 第二段：群聊实时涌入，每 0.55s 一条 ── */
  incoming(r1, beam1, 2.75);
  incoming(r2, beam2, 3.3);
  incoming(r3, beam3, 3.85);

  /* ── 第三段：命中 → 光点飞回芯片 → 记录 → 通知 → 印章 ── */
  tl.fromTo(mark, { backgroundColor: "rgba(255,194,75,0)", color: "#e9f1eb" }, { backgroundColor: "#ffc24b", color: "#140d01", duration: 0.22, immediateRender: false }, 4.22)
    .add(kit.flash(bub3, { color: "amber", duration: 1.0 }), 4.22)
    .set(spark, { x: () => R(mark).cx, y: () => R(mark).cy, opacity: 1, scale: 0.6 }, 4.35)
    .to(spark, { x: () => R(chipNew).cx, y: () => R(chipNew).cy, scale: 1, duration: 0.45, ease: "power2.inOut" }, 4.36)
    .to(spark, { opacity: 0, scale: 2.2, duration: 0.2 }, 4.81)
    .call(() => chipNew.classList.add("is-hit"), [], 4.78)
    .fromTo(chipNew, { scale: 1 }, { scale: 1.22, duration: 0.16, yoyo: true, repeat: 1, ease: "power2.out", immediateRender: false }, 4.78)
    .add(kit.flash(chipNew, { color: "amber", duration: 0.9 }), 4.78)
    .call(() => { logRow.classList.add("is-on"); logKw.textContent = "发票"; }, [], 4.9)
    .add(kit.scramble(logTxt, "· 同事 · 老张 · 刚刚", { duration: 0.5 }), 4.9)
    .add(toast.show(), 4.9)
    .add(kit.ok("已提醒", { en: "ALERTED", hold: 1.05 }), 5.3);
  return tl;
}

export default {
  "alert-keyword": alertKeyword,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* 布局：左面板 230px，右侧群聊占满 */
.pd-alert { position: absolute; inset: 0; display: grid; grid-template-columns: 230px minmax(0, 1fr); }
.pd-alert-chat { position: relative; min-width: 0; }

/* 设置面板 */
.pd-alert-panel {
  position: relative; padding: 14px 16px; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column;
  border-right: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.015);
}
.pd-alert-panel__k { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.24em; color: var(--pd-faint); }
.pd-alert-panel__t { display: flex; align-items: center; gap: 6px; margin-top: 3px; font-size: 13.5px; font-weight: 600; color: var(--pd-ink); }
.pd-alert-panel__t .pd-ic { width: 14px; height: 14px; color: var(--pd-amber); }
.pd-root .pd-alert-label { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.2em; color: var(--pd-faint); margin: 14px 0 7px; }

/* 输入条：骨架占位 + 琥珀光标；聚焦时琥珀描边 */
.pd-alert-input { display: flex; align-items: center; gap: 6px; margin-top: 9px; }
.pd-alert-input__box {
  flex: 1 1 auto; min-width: 0; height: 26px; display: flex; align-items: center; padding: 0 8px;
  border: 1px solid var(--pd-line-strong); border-radius: 3px; background: rgba(255, 255, 255, 0.03);
  font-size: 12px; color: var(--pd-ink); transition: border-color 0.2s, box-shadow 0.2s;
}
.pd-alert-input__box.is-focus { border-color: rgba(255, 194, 75, 0.65); box-shadow: 0 0 0 3px rgba(255, 194, 75, 0.12); }
.pd-alert-input__box.is-press { filter: none; }
.pd-alert-input__text { white-space: nowrap; overflow: hidden; }
.pd-btn.pd-alert-add { flex: none; height: 26px; padding: 0 9px; gap: 3px; font-size: 10.5px; }
.pd-alert-add .pd-ic { width: 10px; height: 10px; stroke-width: 2.4; }

/* 监听范围两行 */
.pd-alert-scope { display: flex; flex-direction: column; gap: 4px; }
.pd-alert-scope__row {
  display: flex; align-items: center; gap: 8px; padding: 3px 6px; border-radius: 3px;
  background: rgba(255, 255, 255, 0.03); font-size: 11.5px;
}
.pd-alert-scope__row .pd-av { width: 22px; height: 22px; font-size: 9px; border-radius: 3px; }
.pd-alert-scope__row > b { font-weight: 500; white-space: nowrap; }
.pd-alert-scope__row .pd-skel { flex: 1 1 auto; min-width: 0; }

/* 命中记录：起手一行灰字，命中后琥珀左线 + 关键词亮起 */
.pd-alert-log { display: flex; flex-direction: column; gap: 4px; }
.pd-alert-log__row {
  display: flex; align-items: center; gap: 0; height: 22px; padding: 0 8px; border-radius: 3px;
  border-left: 2px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.03);
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.04em; color: var(--pd-faint); white-space: nowrap; overflow: hidden;
  transition: border-color 0.25s, background 0.25s, color 0.25s;
}
.pd-alert-log__row b { color: var(--pd-amber); font-weight: 600; }
.pd-alert-log__row.is-on { border-left-color: var(--pd-amber); background: rgba(255, 194, 75, 0.07); color: var(--pd-dim); }
.pd-alert-log__row.is-on b { margin-right: 5px; }   /* flex 子项会吃掉行首空格，用外边距隔开关键词与后文 */

/* 面板底部实时状态：绿点呼吸 */
.pd-root .pd-alert-live {
  position: absolute; left: 16px; bottom: 14px; display: flex; align-items: center; gap: 6px;
  font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.16em; color: var(--pd-dim); white-space: nowrap;
}
.pd-alert-live i { width: 6px; height: 6px; border-radius: 50%; background: var(--pd-neon); box-shadow: 0 0 8px rgba(61, 242, 141, 0.7); animation: pdAlertPulse 1.4s ease-in-out infinite; }

/* 群聊标题旁的 LIVE 标 */
.pd-tag.pd-alert-livetag { display: inline-flex; align-items: center; gap: 4px; font-weight: 500; }
.pd-alert-livetag::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--pd-neon); box-shadow: 0 0 6px rgba(61, 242, 141, 0.8); animation: pdAlertPulse 1.4s ease-in-out infinite; }

/* 气泡里的扫描光（每条新消息扫一遍）与命中词 */
.pd-alert-scan { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none; }
.pd-alert-scan b { position: absolute; top: 0; bottom: 0; left: 0; width: 45%; background: linear-gradient(90deg, transparent, rgba(61, 242, 141, 0.3), transparent); }
.pd-screen mark.pd-alert-hit { background: transparent; color: inherit; padding: 0 2px; margin: 0 -1px; border-radius: 2px; font-weight: 500; }

/* 命中 → 芯片的琥珀光点 */
.pd-alert-spark {
  position: absolute; left: 0; top: 0; z-index: 55; width: 9px; height: 9px; margin: -4.5px 0 0 -4.5px; border-radius: 50%;
  background: var(--pd-amber); box-shadow: 0 0 12px 4px rgba(255, 194, 75, 0.6); pointer-events: none;
}

/* 通知稍宽一点，正文一行放得下；下移到聊天标题栏之下，像盖在消息列表上的系统通知而不是撞在窗口边框上；正文里的关键词琥珀 */
.pd-toast.pd-alert-toast { width: 252px; top: 42px; }
.pd-alert-toast mark { background: transparent; color: var(--pd-amber); font-weight: 600; }

@keyframes pdAlertPulse { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) { .pd-alert-live i, .pd-alert-livetag::before { animation: none; } }
`;
