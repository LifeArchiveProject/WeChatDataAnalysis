/* ════════════════════════════════════════════════════════════
   scenes / moments.js — 朋友圈（4 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。
   时长 4–7 秒，结尾用 kit.ok() 盖「已写入 / 已发送」印章并停留。

   这组统一用 kit.feed() 朋友圈信息流（两条种子帖）：
   自动刷新 → 打开开关后头部刷新图标自转、新帖从顶上落下来；
   点赞 / 图片评论 → 帖子上的动作真的写进去；发布 → 相机 → 抽屉 → 新帖落到最前。
   ════════════════════════════════════════════════════════════ */

const nameOf = (post) => post.querySelector(".pd-post__name");

/* ── 起手：信息流 + 两条种子帖；fade 给会溢出的场景在列表底部加一层渐隐 ── */
function mkFeed(kit, { fade = false } = {}) {
  const feed = kit.feed({ cls: "pd-moments-feed" + (fade ? " pd-moments-feed--fade" : "") });
  const posts = feed.seed(2);
  return { feed, posts };
}

/* ── 预建（display:none）的新帖从顶部撑开落入，旧帖被顺势压下去 ── */
function dropIn(gsap, post) {
  const t = gsap.timeline();
  t.set(post, { display: "flex", overflow: "hidden" })
    .from(post, { height: 0, marginBottom: -14, opacity: 0, y: -18, duration: 0.55, ease: "power3.out", immediateRender: false })
    .set(post, { clearProps: "height,overflow,transform,opacity,marginBottom" });
  return t;
}

/* ── 名字旁弹出一枚小标签（NEW） ── */
function popTag(gsap, kit, post, text, cls) {
  const tag = kit.tag(text, cls);
  nameOf(post).appendChild(tag);
  gsap.set(tag, { opacity: 0, scale: 0.5 });
  return gsap.to(tag, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(3)" });
}

/* ── 帖子「··」旁的动作小面板：♡ 赞 | 评论，贴在按钮左侧 ── */
function actPanel(kit, gsap, anchor) {
  const el = kit.h("div", "pd-moments-act");
  const mk = (ic, label) => { const it = kit.h("b", "pd-moments-act__it"); it.append(kit.icon(ic), kit.h("span", "", label)); el.appendChild(it); return it; };
  const items = [mk("heart", "赞"), mk("comment", "评论")];
  kit.mount(el);
  gsap.set(el, { opacity: 0 });
  const place = () => {
    const r = kit.rect(anchor);
    gsap.set(el, { x: r.x - el.offsetWidth - 6, y: r.cy - el.offsetHeight / 2 });
  };
  return {
    el, items,
    open(d = 0.22) { const t = gsap.timeline(); t.call(place).fromTo(el, { opacity: 0, scale: 0.9, transformOrigin: "100% 50%" }, { opacity: 1, scale: 1, duration: d, ease: "power3.out" }); return t; },
    close(d = 0.18) { return gsap.to(el, { opacity: 0, duration: d }); },
    hover(i) { items.forEach((x, k) => x.classList.toggle("is-hover", k === i)); },
  };
}

/* ── 图片查看层：半透明黑底 + 从缩略图放大的图块 + 底部评论条 ── */
function viewer(kit, gsap, tile, idx, total) {
  const el = kit.h("div", "pd-moments-viewer");
  const hud = kit.h("i", "pd-moments-viewer__hud", `IMG ${idx} / ${total}`);
  const img = kit.h("div", "pd-moments-viewer__img");
  img.appendChild(kit.icon("image"));
  const bar = kit.h("div", "pd-moments-viewer__bar");
  const field = kit.h("span", "pd-moments-viewer__field");
  const ph = kit.h("em", "pd-moments-viewer__ph", "评论…");
  const text = kit.h("span", "pd-moments-viewer__t");
  field.append(ph, text, kit.h("i", "pd-caret"));
  const send = kit.h("b", "pd-btn pd-btn--amber", "发送");
  bar.append(field, send);
  el.append(hud, img, bar);
  kit.mount(el);
  gsap.set(el, { opacity: 0 });
  return {
    el, img, bar, field, ph, text, send,
    open() {
      const t = gsap.timeline();
      t.to(el, { opacity: 1, duration: 0.3 }, 0)
        // 图块从被点的那格飞到正中放大
        .fromTo(img,
          { x: () => kit.rect(tile).cx - kit.rect(img).cx, y: () => kit.rect(tile).cy - kit.rect(img).cy, scale: 60 / 220, opacity: 0.4 },
          { x: 0, y: 0, scale: 1, opacity: 1, duration: 0.5, ease: "power3.out", immediateRender: false }, 0);
      return t;
    },
    close() { const t = gsap.timeline(); t.to(el, { opacity: 0, duration: 0.3 }).set(el, { display: "none" }); return t; },
  };
}

/* ═══════════════ sns-autorefresh 自动后台刷新朋友圈 ═══════════════
   打开「AUTO REFRESH」开关 → 头部刷新图标自转 → 新帖从顶上落下、旧帖下移、NEW 标签 →
   再转一圈、再来一条 → 印章「已入库 · +2」。光标只碰一次开关，之后全程不用管。 */
function autoRefresh({ gsap, kit, tl }) {
  const { feed } = mkFeed(kit, { fade: true });

  // 头部：刷新图标 + 计数角标，挨着相机
  const tools = kit.h("span", "pd-moments-tools");
  const rf = kit.h("i", "pd-moments-refresh");
  rf.appendChild(kit.icon("refresh"));
  const badge = kit.h("b", "pd-moments-badge", "+1");
  tools.append(rf, feed.camera, badge);
  feed.head.appendChild(tools);
  gsap.set(badge, { opacity: 0, scale: 0.4 });

  // 头部里的注释 + 开关：放在标题和工具之间（不压列表，新帖的 flash 框从它下方开始）
  const note = kit.note("", feed.head);
  note.classList.add("pd-moments-note");
  const sw = kit.h("i", "pd-moments-switch");
  sw.appendChild(kit.h("b"));
  note.append(kit.h("span", "", "AUTO REFRESH · 每 5 分钟"), sw);
  feed.head.insertBefore(note, tools);

  // 两条新帖预建、藏起来；后建的在最上（最新的最先看到）；作者别跟种子帖撞名
  const p1 = feed.post({ name: "老张", text: "今天的日落。", imgs: 2, time: "刚刚", top: true });
  const p2 = feed.post({ name: "小李", text: "下班。", imgs: 0, time: "刚刚", top: true });
  p2.av.textContent = "李";
  gsap.set([p1, p2], { display: "none" });

  const spin = () => {
    const t = gsap.timeline();
    t.call(() => rf.classList.add("is-spin"))
      .to(rf, { rotate: "+=360", duration: 0.7, ease: "power2.inOut" })
      .call(() => rf.classList.remove("is-spin"));
    return t;
  };
  const bump = (n) => {
    const t = gsap.timeline();
    t.call(() => { badge.textContent = "+" + n; })
      .fromTo(badge, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(3)", immediateRender: false });
    return t;
  };
  const arrive = (post, n) => {
    const t = gsap.timeline();
    t.add(dropIn(gsap, post), 0)
      .add(popTag(gsap, kit, post, "NEW", "pd-tag--neon"), 0.35)
      .add(kit.flash(post, { color: "neon", duration: 0.6 }), 0.35)
      .add(bump(n), 0.35);
    return t;
  };
  const c = kit.cursor();
  // 光标只碰一次开关：移过去 → 点 → 开关亮 → 退到右下 → 立刻隐身，之后全程后台自动跑
  // （用绝对位置编，别让零时长 call 把后面的 ">" 锚点拽到点击中途）
  const tap = gsap.timeline();
  tap.add(c.to(sw, { duration: 0.55 }), 0)
    .add(c.click(sw), 0.55)
    .call(() => sw.classList.add("is-on"), [], 0.67)
    .add(c.to({ x: 560, y: 360 }, { duration: 0.45 }), 1.05)
    .add(c.hide(), 1.5);

  tl.add(kit.fade(note), 0.2)
    .add(c.show(), 0.25)
    .add(tap, 0.35)
    .add(spin(), "<+0.8")
    .add(arrive(p1, 1), ">-0.15")
    .add(spin(), ">+0.35")
    .add(arrive(p2, 2), ">-0.15")
    .add(kit.ok("已入库 · +2", { en: "SYNCED" }), ">+0.1");
  return tl;
}

/* ═══════════════ sns-like 朋友圈点赞 ═══════════════
   点第一条帖子的「··」→ 弹出「♡ 赞 | 评论」→ 点赞 → 面板收起、点赞栏出现、
   心形弹一下变琥珀、名字打出「我」→ 印章「已点赞」。 */
function like({ gsap, kit, tl }) {
  const { posts } = mkFeed(kit);
  const post = posts[0];
  const c = kit.cursor();
  const act = actPanel(kit, gsap, post.more);
  // 心形图标包一层，好做弹跳
  const heart = post.likeRow.firstElementChild;
  const hw = kit.h("i", "pd-moments-heart");
  post.likeRow.insertBefore(hw, heart);
  hw.appendChild(heart);

  tl.add(c.show(), 0.2)
    .add(c.tap(post.more), 0.35)
    .add(act.open(), ">-0.1")
    .add(c.to(act.items[0], { duration: 0.35 }), ">+0.1")
    .call(() => act.hover(0))
    .add(c.click(act.items[0]), ">+0.15")
    .add(act.close(), ">-0.15")
    .add(c.hide(), "<")                                             // 点完就退场，点赞栏成为唯一焦点
    .set(post.social, { display: "flex" })
    .set(post.likeRow, { display: "flex" })
    .add(kit.pop(post.social), "<")
    .call(() => post.likeRow.classList.add("is-on"), [], "<+0.1")
    .fromTo(hw, { scale: 0.2 }, { scale: 1, duration: 0.55, ease: "back.out(4)", immediateRender: false }, "<")
    .add(kit.type(post.likeNames, "我", { cps: 6, caret: false }), "<+0.15")
    .add(kit.flash(post.social, { color: "amber", duration: 0.7 }), "<")
    .add(kit.ok("已点赞", { en: "LIKED" }), ">+0.3");
  return tl;
}

/* ═══════════════ sns-image-comment 朋友圈图片评论 ═══════════════
   点第一条帖子的第 2 张图 → 查看层：图放大 + 底部评论条 → 点评论条打字「这张拍得好」→
   点发送 → 查看层淡出 → 帖子下方出现「我：这张拍得好」、那张图闪一下 → 印章「已评论」。 */
function imageComment({ gsap, kit, tl }) {
  const { posts } = mkFeed(kit);
  const post = posts[0];
  const tile = post.tiles[1];
  const c = kit.cursor();
  const v = viewer(kit, gsap, tile, 2, post.tiles.length);
  // 落到帖子下的那行评论，预建藏起
  const line = kit.h("p", "");
  line.append(kit.h("b", "", "我"), "：这张拍得好");
  post.cmtBox.appendChild(line);
  gsap.set(line, { display: "none" });

  tl.add(c.show(), 0.2)
    .add(c.tap(tile), 0.35)
    .add(v.open(), ">-0.2")
    .add(c.to(v.field, { duration: 0.45, dx: -40 }), ">")
    .add(c.click(v.bar), ">")
    .call(() => v.bar.classList.add("is-edit"), [], "<+0.1")
    .set(v.ph, { display: "none" }, "<")
    .add(kit.type(v.text, "这张拍得好", { cps: 12 }), "<+0.1")
    .add(c.to(v.send, { duration: 0.35 }), ">+0.2")
    .add(c.click(v.send), ">")
    .add(v.close(), ">-0.1")
    .add(c.hide(), "<")                                             // 查看层淡出时光标一起退场，别悬在帖子空白处
    .set(post.social, { display: "flex" })
    .set(line, { display: "block" }, "<")
    .add(kit.pop(post.social), "<")
    .add(kit.flash(tile, { color: "amber", duration: 0.7 }), "<")
    .add(kit.flash(post.social, { color: "amber", duration: 0.7 }), "<")
    .add(kit.ok("已评论", { en: "COMMENTED" }), ">-0.1");
  return tl;
}

/* ═══════════════ sns-post 发布朋友圈 ═══════════════
   点头部相机 → 抽屉「发表朋友圈」滑入：文本区 + ⊕ 图片格 → 打字「周末，老地方。」→
   点 ⊕ 两张图弹入 → 点「发表」→ 抽屉收起 → 新帖落到最前 → 印章「已发布」。 */
function postMoment({ gsap, kit, tl }) {
  const { feed } = mkFeed(kit, { fade: true });
  const c = kit.cursor();
  const sheet = kit.sheet({ title: "发表朋友圈" });
  sheet.ok.textContent = "发表";

  // 多行文本区
  const ta = kit.h("div", "pd-moments-ta");
  const ph = kit.h("em", "pd-moments-ta__ph", "这一刻的想法…");
  const line = kit.h("div", "pd-moments-ta__line");
  const txt = kit.h("span", "pd-moments-ta__t");
  line.append(txt, kit.h("i", "pd-caret"));
  ta.append(ph, line);
  // 图片格：两张待弹入的骨架图 + ⊕
  const grid = kit.h("div", "pd-moments-grid");
  const add = kit.h("i", "pd-moments-add");
  add.appendChild(kit.icon("plus"));
  const tiles = [0, 1].map(() => { const t = kit.h("i", "pd-post__img"); t.appendChild(kit.icon("image")); gsap.set(t, { display: "none" }); return t; });
  grid.append(...tiles, add);
  sheet.body.append(ta, grid);
  kit.form([["谁可以看", "公开"], ["所在位置", "不显示"]], sheet.body);

  // 发出去之后落到最前的新帖，预建藏起
  const np = feed.post({ name: "我", text: "周末，老地方。", imgs: 2, time: "刚刚", top: true });
  np.av.className = "pd-av pd-av--me";
  gsap.set(np, { display: "none" });

  tl.add(c.show(), 0.2)
    .add(c.tap(feed.camera), 0.3)
    .add(sheet.open(), ">-0.15")
    .add(c.to(ta, { duration: 0.4 }), ">")
    .add(c.click(ta), ">")
    .call(() => ta.classList.add("is-edit"), [], "<+0.1")
    .set(ph, { display: "none" }, "<")
    .add(kit.type(txt, "周末，老地方。", { cps: 14 }), "<+0.1")
    .add(c.to(add, { duration: 0.35 }), ">+0.1")
    .add(c.click(add), ">")
    .set(tiles, { display: "grid" }, ">-0.3")
    .fromTo(tiles, { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(2)", stagger: 0.1, immediateRender: false }, "<")
    .add(c.to(sheet.ok, { duration: 0.4 }), ">+0.05")
    .add(c.click(sheet.ok), ">")
    // 抽屉要在按钮亮过 is-press 之后再收：锚在 click 上；零时长 call 放它后面用 "<" 搭车，
    // 否则下一个 ">" 会取 call 的位置，抽屉就抢在点击前滑走
    .call(() => ta.classList.remove("is-edit"), [], ">-0.15")
    .add(sheet.close(), "<")
    .add(c.hide(), "<")                                             // 发出去就退场，新帖落下成为唯一焦点
    .add(dropIn(gsap, np), ">-0.1")
    .add(kit.flash(np, { color: "amber", duration: 0.7 }), "<+0.25")
    .add(kit.ok("已发布", { en: "POSTED" }), ">-0.25");
  return tl;
}

export default {
  "sns-autorefresh": autoRefresh,
  "sns-like": like,
  "sns-image-comment": imageComment,
  "sns-post": postMoment,
};

// 本组专属的局部样式；统一注入一次
export const css = `
/* 会溢出的信息流：底部渐隐，让被裁的旧帖读成「下面还有」 */
.pd-moments-feed--fade .pd-feed__list {
  -webkit-mask-image: linear-gradient(#000 82%, transparent 100%);
  mask-image: linear-gradient(#000 82%, transparent 100%);
}

/* 头部：刷新图标 + 角标 */
.pd-moments-tools { position: relative; display: flex; align-items: center; gap: 12px; }
.pd-moments-refresh { display: grid; place-items: center; width: 18px; height: 18px; color: var(--pd-dim); }
.pd-moments-refresh.is-spin { color: var(--pd-amber); }
/* kit 的 .pd-feed__head .pd-ic 直接命中 svg，得比它更具体才能让自转时真的变琥珀 */
.pd-root .pd-feed__head .pd-moments-refresh.is-spin .pd-ic { color: var(--pd-amber); }
.pd-moments-badge {
  position: absolute; left: 11px; top: -9px; min-width: 14px; padding: 0 4px; border-radius: 7px; text-align: center;
  font-family: var(--pd-mono); font-weight: 600; font-size: 9px; line-height: 1.5; letter-spacing: 0.04em; white-space: nowrap;
  background: var(--pd-amber); color: #140d01;
}

/* 头部里的注释 + 开关：从 .pd-note 的绝对定位改成头部 flex 的一员，靠右贴着工具组 */
.pd-root .pd-moments-note {
  position: static; transform: none; margin: 0 12px 0 auto; padding: 0; border: 0; background: none;
  display: flex; align-items: center; gap: 8px; font-weight: 400;
}
.pd-moments-switch {
  position: relative; width: 22px; height: 12px; border-radius: 6px; flex: none;
  border: 1px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.04);
  transition: background 0.25s, border-color 0.25s;
}
.pd-moments-switch b { position: absolute; left: 2px; top: 2px; width: 6px; height: 6px; border-radius: 50%; background: var(--pd-dim); transition: transform 0.25s, background 0.25s; }
.pd-moments-switch.is-on { background: var(--pd-amber); border-color: var(--pd-amber); box-shadow: 0 0 10px rgba(255, 194, 75, 0.45); }
.pd-moments-switch.is-on b { transform: translateX(10px); background: #140d01; }

/* 「··」旁的动作面板 */
.pd-moments-act {
  position: absolute; left: 0; top: 0; z-index: 20; display: flex;
  background: #131a16; border: 1px solid var(--pd-line-strong); border-radius: 4px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.55);
}
.pd-moments-act__it { display: flex; align-items: center; gap: 5px; padding: 5px 11px; font-size: 11.5px; font-weight: 400; color: var(--pd-ink); white-space: nowrap; }
.pd-moments-act__it + .pd-moments-act__it { border-left: 1px solid var(--pd-line); }
.pd-moments-act__it .pd-ic { width: 12px; height: 12px; color: var(--pd-dim); }
.pd-moments-act__it.is-hover { background: rgba(255, 194, 75, 0.14); color: var(--pd-amber); }
.pd-moments-act__it.is-hover .pd-ic { color: var(--pd-amber); }
.pd-moments-heart { display: inline-flex; flex: none; }
.pd-root .pd-post__likes.is-on .pd-moments-heart { color: var(--pd-amber); }
.pd-root .pd-post__likes.is-on .pd-moments-heart .pd-ic { fill: var(--pd-amber); }

/* 图片查看层 */
.pd-moments-viewer {
  position: absolute; inset: 0; z-index: 20; pointer-events: none;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px;
  background: rgba(4, 7, 5, 0.9);
}
/* HUD 落到头部以下（头部 36px），别跟透出来的相机图标叠在一起；再垫一块实底 */
.pd-moments-viewer__hud {
  position: absolute; right: 16px; top: 46px; padding: 2px 6px; border-radius: 2px;
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.24em; color: var(--pd-dim); background: rgba(4, 7, 5, 0.95);
}
.pd-moments-viewer__img {
  width: 220px; height: 160px; border-radius: 4px; display: grid; place-items: center; color: var(--pd-faint);
  background: var(--pd-tile); border: 1px solid var(--pd-line-strong); box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}
.pd-moments-viewer__img .pd-ic { width: 36px; height: 36px; }
.pd-moments-viewer__bar {
  display: flex; align-items: center; gap: 8px; width: 300px; padding: 5px 5px 5px 12px;
  border: 1px solid var(--pd-line-strong); border-radius: 20px; background: rgba(20, 27, 23, 0.96);
}
.pd-moments-viewer__bar .pd-btn { padding: 4px 12px; border-radius: 14px; }
.pd-moments-viewer__field { flex: 1 1 auto; min-width: 0; display: flex; align-items: center; min-height: 22px; font-size: 12px; color: var(--pd-ink); }
.pd-moments-viewer__ph { color: var(--pd-faint); }

/* 发表抽屉：文本区 + 图片格 */
.pd-moments-ta {
  position: relative; height: 64px; flex: none; padding: 8px 10px; border-radius: 4px;
  border: 1px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.03); font-size: 12.5px; color: var(--pd-ink);
}
.pd-moments-ta__ph { position: absolute; left: 10px; top: 8px; color: var(--pd-faint); }
.pd-moments-ta__line { display: flex; align-items: center; min-height: 18px; }
.pd-moments-grid { display: grid; grid-template-columns: repeat(3, 60px); gap: 4px; flex: none; }
.pd-moments-add { width: 60px; height: 60px; border: 1px dashed var(--pd-line-strong); border-radius: 2px; display: grid; place-items: center; color: var(--pd-dim); }
.pd-moments-add .pd-ic { width: 16px; height: 16px; }
.pd-moments-add.is-press { border-color: var(--pd-amber); color: var(--pd-amber); filter: none; }
`;
