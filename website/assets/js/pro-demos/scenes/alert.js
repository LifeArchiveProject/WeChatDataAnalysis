/* ════════════════════════════════════════════════════════════
   scenes / alert.js — 提醒（1 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   这一项是**真实动作类**里最纯粹的自动监测：全程没有人——关键词早就配好了，
   底下一条 kit.workflow（新消息 → AI 关键词匹配 → 命中即提醒）随剧情逐步点亮，
   画面里只有消息自己涌进来、自己被扫、自己命中、自己弹提醒。不用 kit.cursor。
   情境条先立「盯单 · 群里消息刷得快」，结尾 strip.result("命中即刻提醒") + kit.ok() 印章停 0.9s。
   布局：左 230px 是「关键词提醒」设置面板（本文件自建 pd-alert-*），右侧是客户群聊窗。
   自建布局根 .pd-alert 必须带 pd-pushed，让出顶端 22px 情境条与底端 24px 工作流轨。
   ════════════════════════════════════════════════════════════ */

// 群聊/单聊关键词提醒：「报价」「发票」早已在监听 → 客户群消息连着涌进来，每条被扫一遍 →
// 第三条命中「发票」高亮 → 光点飞回芯片点亮 → 命中记录落定 → 右上滑入系统通知 → 印章
function alertKeyword({ gsap, kit, tl }) {
  const h = kit.h;

  /* ── 布局：左面板 + 右群聊（情境条 22px 在上、工作流轨 24px 在下，根容器自己让开） ── */
  const wrap = kit.mount(h("div", "pd-alert pd-pushed"));
  const panel = h("aside", "pd-alert-panel");
  const chatHost = h("div", "pd-alert-chat");
  wrap.append(panel, chatHost);
  const strip = kit.scenario("盯单 · 群里消息刷得快");
  const flow = kit.workflow([
    { label: "新消息", icon: "chat" },
    { label: "关键词匹配", ai: true },
    { label: "命中即提醒", icon: "bell" },
  ]);

  // 面板头
  const head = h("div", "pd-alert-panel__head");
  const title = h("b", "pd-alert-panel__t");
  title.append(kit.icon("bell"), h("span", "", "关键词提醒"));
  head.append(h("i", "pd-alert-panel__k", "KEYWORD · ALERT"), title);
  panel.appendChild(head);

  // 关键词：两个词早就在监听里了，没人现场去加
  panel.appendChild(h("p", "pd-alert-label", "关键词"));
  const chips = kit.chips(["报价", "发票"], { parent: panel });
  const chipHit = chips.rows[1];
  const chipMore = chips.add("+ 关键词");
  chipMore.classList.add("pd-chip--dim");

  // 监听范围：客户群 + 单聊，两行都已勾上
  panel.appendChild(h("p", "pd-alert-label", "监听范围"));
  const scope = h("div", "pd-alert-scope");
  const scopeRow = (av, name) => {
    const r = h("div", "pd-alert-scope__row");
    const ck = h("i", "pd-check is-on");
    ck.appendChild(kit.icon("check"));
    r.append(av, h("b", "", name), kit.skel(52, 5), ck);
    scope.appendChild(r);
    return r;
  };
  scopeRow(kit.avatar("群", "muted"), "客户群");
  scopeRow(kit.avatar("客", "them"), "单聊");
  panel.appendChild(scope);

  // 命中记录：上面一条是昨天的旧命中，下面这条留给这一次
  panel.appendChild(h("p", "pd-alert-label", "命中记录"));
  const log = h("div", "pd-alert-log");
  const past = h("div", "pd-alert-log__row is-past");
  past.append(h("b", "", "报价"), h("em", "", "· 客户群 · 李姐 · 昨天"));
  const logRow = h("div", "pd-alert-log__row");
  const logKw = h("b", "", "");
  const logTxt = h("em", "", "等待命中");
  logRow.append(logKw, logTxt);
  log.append(past, logRow);
  panel.appendChild(log);

  // 提醒方式：命中之后往哪儿送，三条都已开
  panel.appendChild(h("p", "pd-alert-label", "提醒方式"));
  const ways = h("div", "pd-alert-ways");
  ["系统通知", "声音", "置顶"].forEach((w) => {
    const c = h("i", "pd-alert-way");
    c.append(kit.icon("check"), h("span", "", w));
    ways.appendChild(c);
  });
  panel.appendChild(ways);

  // 面板底部的实时状态行
  const live = h("p", "pd-alert-live");
  live.append(h("i"), h("span", "", "实时检测 · 群聊 + 单聊"));
  panel.appendChild(live);

  /* ── 右侧客户群：时间行 + 一条旧消息；标题旁挂 LIVE 标 ── */
  const chat = kit.chat({ title: "星辰项目客户群", group: true, rail: false, parent: chatHost });
  chat.title.appendChild(kit.tag("LIVE", "pd-tag--neon pd-alert-livetag"));
  chat.time("今天 14:02");
  chat.row("l", "报价单收到了，我看下", { name: "王总", av: "王" });

  // 预建三条实时消息（display none）；每条气泡里放一道扫描光，表示「每条新消息都被检测一遍」
  const withScan = (bub) => { const s = h("i", "pd-alert-scan"); const b = h("b"); s.appendChild(b); bub.appendChild(s); return b; };
  const mk = (name, av, content) => { const r = chat.row("l", content, { name, av }); gsap.set(r, { display: "none" }); return r; };
  const r1 = mk("李姐", "李", "样品明天能到吗"), beam1 = withScan(r1.content);
  const r2 = mk("王总", "王", "合同我发你邮箱了"), beam2 = withScan(r2.content);
  const bub3 = kit.bubble("", "l");
  const mark = h("mark", "pd-alert-hit", "发票");
  bub3.append(mark, "抬头发我一下，今天要开");
  const r3 = mk("陈会计", "陈", bub3), beam3 = withScan(bub3);

  /* ── 通知与光点（没有光标：这一段没有人参与） ── */
  const toast = kit.toast({ title: "关键词命中：发票", body: "", app: "WeChatDataAnalysis · 系统通知" });
  toast.el.classList.add("pd-alert-toast");
  toast.body.append("客户群 · 陈会计：", h("mark", "", "发票"), "抬头发我一下");
  const spark = kit.mount(h("i", "pd-alert-spark"));
  gsap.set(spark, { opacity: 0 });
  const R = kit.rect;

  // 一条消息实时弹入：显示 → 弹入 → 扫描光横扫一遍
  const incoming = (row, beam, at) => {
    tl.set(row, { display: "flex" }, at)
      .add(kit.pop(row), at)
      .fromTo(beam, { xPercent: -120 }, { xPercent: 320, duration: 0.35, ease: "none", immediateRender: false }, at + 0.12);
  };

  /* ── 第一段：情境条 + 工作流轨立住，说明这一切是规则在跑 ── */
  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15);

  /* ── 第二段：客户群实时涌入，每条都被扫一遍 ── */
  tl.add(flow.step(0), 1.0);
  incoming(r1, beam1, 1.0);
  tl.add(flow.step(1), 1.25);
  incoming(r2, beam2, 1.65);
  incoming(r3, beam3, 2.3);

  /* ── 第三段：命中 → 光点飞回芯片 → 记录 → 通知 → 印章 ── */
  tl.fromTo(mark, { backgroundColor: "rgba(255,194,75,0)", color: "#e9f1eb" }, { backgroundColor: "#ffc24b", color: "#140d01", duration: 0.22, immediateRender: false }, 2.75)
    .add(kit.flash(bub3, { color: "amber", duration: 1.0 }), 2.75)
    .set(spark, { x: () => R(mark).cx, y: () => R(mark).cy, opacity: 1, scale: 0.6 }, 2.9)
    .to(spark, { x: () => R(chipHit).cx, y: () => R(chipHit).cy, scale: 1, duration: 0.45, ease: "power2.inOut" }, 2.91)
    .to(spark, { opacity: 0, scale: 2.2, duration: 0.2 }, 3.36)
    .call(() => chipHit.classList.add("is-hit"), [], 3.33)
    .fromTo(chipHit, { scale: 1 }, { scale: 1.22, duration: 0.16, yoyo: true, repeat: 1, ease: "power2.out", immediateRender: false }, 3.33)
    .add(kit.flash(chipHit, { color: "amber", duration: 0.9 }), 3.33)
    .add(flow.step(2), 3.45)
    .call(() => { logRow.classList.add("is-on"); logKw.textContent = "发票"; }, [], 3.45)
    .add(kit.scramble(logTxt, "· 客户群 · 陈会计 · 刚刚", { duration: 0.5 }), 3.45)
    .add(toast.show(), 3.45)
    /* 收尾这一拍把输入条压暗：印章正好压在「发送」上，半露一截按钮既脏又像在等人点 */
    .to(chat.input, { opacity: 0.25, duration: 0.3 }, 3.9)
    .add(flow.done(), 3.95)
    .add(kit.ok("已提醒", { en: "AUTO ALERTED", hold: 1.05 }), 4.0)
    .add(strip.result("命中即刻提醒"), 4.0);
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
/* 群里消息一直在涌：列表贴底排，最新几条永远完整可见，旧的从上边被顶出视野 */
.pd-alert-chat .pd-chat__list { justify-content: flex-end; }
.pd-alert-chat .pd-row, .pd-alert-chat .pd-time { flex: none; }

/* 设置面板 */
.pd-alert-panel {
  position: relative; padding: 10px 14px; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column;
  border-right: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.015);
}
.pd-alert-panel__k { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.24em; color: var(--pd-faint); }
.pd-alert-panel__t { display: flex; align-items: center; gap: 6px; margin-top: 3px; font-size: 13.5px; font-weight: 600; color: var(--pd-ink); }
.pd-alert-panel__t .pd-ic { width: 14px; height: 14px; color: var(--pd-amber); }
.pd-root .pd-alert-label { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.2em; color: var(--pd-faint); margin: 9px 0 6px; }

/* 监听范围两行 */
.pd-alert-scope { display: flex; flex-direction: column; gap: 4px; }
.pd-alert-scope__row {
  display: flex; align-items: center; gap: 8px; padding: 3px 6px; border-radius: 3px;
  background: rgba(255, 255, 255, 0.03); font-size: 11.5px;
}
.pd-alert-scope__row .pd-av { width: 22px; height: 22px; font-size: 9px; border-radius: 3px; }
.pd-alert-scope__row > b { font-weight: 500; white-space: nowrap; }
.pd-alert-scope__row .pd-skel { flex: 1 1 auto; min-width: 0; }

/* 命中记录：上一条是昨天的旧命中，下一条命中后琥珀左线 + 关键词亮起 */
.pd-alert-log { display: flex; flex-direction: column; gap: 4px; }
.pd-alert-log__row {
  display: flex; align-items: center; gap: 0; height: 22px; flex: none; padding: 0 8px; border-radius: 3px;
  border-left: 2px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.03);
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.04em; color: var(--pd-faint); white-space: nowrap; overflow: hidden;
  transition: border-color 0.25s, background 0.25s, color 0.25s;
}
.pd-alert-log__row b { color: var(--pd-amber); font-weight: 600; }
.pd-alert-log__row.is-past { opacity: 0.5; }
.pd-alert-log__row.is-past b { margin-right: 5px; }
.pd-alert-log__row.is-on { border-left-color: var(--pd-amber); background: rgba(255, 194, 75, 0.07); color: var(--pd-dim); }
.pd-alert-log__row.is-on b { margin-right: 5px; }   /* flex 子项会吃掉行首空格，用外边距隔开关键词与后文 */

/* 提醒方式：命中之后往哪儿送 */
/* margin-bottom 是硬间距：面板一塞满，下面那行的 margin-top:auto 就会被压成 0 */
.pd-alert-ways { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
.pd-alert-way {
  display: inline-flex; align-items: center; gap: 3px; padding: 2px 6px 1px; border-radius: 2px;
  border: 1px solid rgba(61, 242, 141, 0.3); background: rgba(61, 242, 141, 0.06);
  font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.08em; color: var(--pd-neon); white-space: nowrap;
}
.pd-alert-way .pd-ic { width: 9px; height: 9px; stroke-width: 2.6; }

/* 面板底部实时状态：绿点呼吸 */
/* 贴面板底部：margin-top:auto 顶到底，别用 absolute——上面加了「提醒方式」就会撞上 */
.pd-root .pd-alert-live {
  margin: auto 0 1px; display: flex; align-items: center; gap: 6px;
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

/* 通知稍宽一点，正文一行放得下；下移到（已被情境条下推的）聊天标题栏之下；正文里的关键词琥珀 */
.pd-toast.pd-alert-toast { width: 252px; top: 64px; }
.pd-alert-toast mark { background: transparent; color: var(--pd-amber); font-weight: 600; }

@keyframes pdAlertPulse { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) { .pd-alert-live i, .pd-alert-livetag::before { animation: none; } }
`;
