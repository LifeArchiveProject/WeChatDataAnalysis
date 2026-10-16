/* ════════════════════════════════════════════════════════════
   scenes / moments.js — 朋友圈（5 项）
   每个场景：({ gsap, kit, tl, root, reduced, item }) => 把动画编进 tl（可返回 tl）。
   约定：所有补间都挂在 tl 上（不要裸调 gsap.to），舞台切换时靠 kill(tl) 清场。

   这五项都是经微信客户端的**真实动作**（对方看得见），不是本地存档——
   所以一律不加 { local: true }，并且统一演成「工作流自动触发」：
   每个场景底部一条 kit.workflow（触发条件 → AI 处理 → 自动执行）随剧情逐节点亮，
   全程没有光标、没有人点按钮：内容自己出现、自己发出去，自动产生的那条挂「AI」小标。
   情境条讲「什么条件触发了它」，结尾 strip.result() 讲「省了什么事 / 没漏什么」。

   信息流里的人保持客户语境（客户 · 王总 / 李姐 / 陈总 / 赵总），动态是开业 / 到货 / 乔迁这类业务动向。
   五条动作路径刻意各不相同：定时拉取 / AI 判定后点赞 / 图片查看层里评论 / 动态下方内联评论 / 定时发布抽屉。
   时长 4.5–7.5 秒，结尾用 kit.ok() 盖印章并停留 ≥0.9 秒。
   ════════════════════════════════════════════════════════════ */

const nameOf = (post) => post.querySelector(".pd-post__name");

/* 倒计时 / 时钟读数 */
const pad = (n) => String(n).padStart(2, "0");
const mmss = (v) => { const s = Math.max(0, Math.round(v)); return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`; };
const hms = (v) => { const s = Math.max(0, Math.round(v)); return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`; };

/* ── 信息流里的客户动态：谁 / 发了什么 / 多久之前 ── */
const CUSTOMERS = {
  li: { name: "客户 · 李姐", av: "李" },
  chen: { name: "客户 · 陈总", av: "陈" },
  wang: { name: "客户 · 王总", av: "王" },
  zhao: { name: "客户 · 赵总", av: "赵" },
};

/* ── 起手：信息流 + 几条客户动态；fade 给会溢出的场景在列表底部加一层渐隐 ── */
function mkFeed(kit, { fade = false, posts = [] } = {}) {
  const feed = kit.feed({ cls: "pd-moments-feed" + (fade ? " pd-moments-feed--fade" : "") });
  const made = posts.map((p) => addPost(feed, p));
  return { feed, posts: made };
}

/* ── 一条客户动态：who 给头像和名字，其余照 kit.feed().post 的参数 ── */
function addPost(feed, { who, text, imgs = 0, time = "1 小时前", top = false }) {
  const p = feed.post({ name: who.name, text, imgs, time, top });
  p.av.textContent = who.av;
  return p;
}

/* ── 预建（display:none）的新帖从顶部撑开落入，旧帖被顺势压下去 ── */
function dropIn(gsap, post) {
  const t = gsap.timeline();
  t.set(post, { display: "flex", overflow: "hidden" })
    .from(post, { height: 0, marginBottom: -14, opacity: 0, y: -18, duration: 0.55, ease: "power3.out", immediateRender: false })
    .set(post, { clearProps: "height,overflow,transform,opacity,marginBottom" });
  return t;
}

/* ── 名字旁弹出一枚小标签（NEW / 定时发布） ── */
function popTag(gsap, kit, post, text, cls) {
  const tag = kit.tag(text, cls);
  nameOf(post).appendChild(tag);
  gsap.set(tag, { opacity: 0, scale: 0.5 });
  return gsap.to(tag, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(3)" });
}

/* ── AI 徽标：自动产生的内容边上挂一枚，静止帧里也看得出不是人手打的 ── */
const aiBadge = (kit, text = "AI") => kit.h("i", "pd-moments-ai", text);

/* ── 扫描线：一道琥珀光扫过某块内容，表示「AI 正在读它」 ── */
function scanner(kit, gsap, host) {
  host.classList.add("pd-moments-scanhost");
  const el = kit.h("i", "pd-moments-scan");
  host.appendChild(el);
  gsap.set(el, { opacity: 0 });
  return {
    el,
    run(d = 0.8) {
      const t = gsap.timeline();
      t.set(el, { opacity: 1, y: 0 })
        .to(el, { y: () => Math.max(0, kit.rect(host).h - 2), duration: d, ease: "none" })
        .to(el, { opacity: 0, duration: 0.18 });
      return t;
    },
  };
}

/* ── 状态药丸：评论条右端的「生成中 → 已发送」，代替人手点的发送键 ── */
function statePill(kit, gsap, text = "生成中") {
  const el = kit.h("b", "pd-moments-state", text);
  return Object.assign(el, {
    to(txt, on = false) {
      const t = gsap.timeline();
      t.call(() => { el.textContent = txt; el.classList.toggle("is-on", on); })
        .fromTo(el, { scale: 0.9, opacity: 0.45 }, { scale: 1, opacity: 1, duration: 0.26, ease: "back.out(2.4)" });
      return t;
    },
  });
}

/* ── 图片查看层：半透明黑底 + 从缩略图放大的图块 + AI 认出的标签 + 底部评论条 ── */
function viewer(kit, gsap, tile, idx, total, tags = []) {
  const el = kit.h("div", "pd-moments-viewer");
  const hud = kit.h("i", "pd-moments-viewer__hud", `IMG ${idx} / ${total}`);
  const img = kit.h("div", "pd-moments-viewer__img");
  img.appendChild(kit.icon("image"));
  const chips = kit.h("div", "pd-moments-viewer__chips");
  const chipEls = tags.map((t) => { const c = kit.h("i", "pd-moments-chip", t); chips.appendChild(c); return c; });
  gsap.set(chipEls, { opacity: 0, scale: 0.6 });
  const bar = kit.h("div", "pd-moments-viewer__bar");
  const field = kit.h("span", "pd-moments-viewer__field");
  const ph = kit.h("em", "pd-moments-viewer__ph", "等待生成…");
  const text = kit.h("span", "pd-moments-viewer__t");
  field.append(ph, text, kit.h("i", "pd-caret"));
  const state = statePill(kit, gsap, "生成中");
  bar.append(aiBadge(kit), field, state);
  el.append(hud, img, chips, bar);
  kit.mount(el);
  gsap.set(el, { opacity: 0 });
  return {
    el, img, chips, chipEls, bar, field, ph, text, state,
    open() {
      const t = gsap.timeline();
      t.to(el, { opacity: 1, duration: 0.3 }, 0)
        // 图块从那格缩略图飞到正中放大（没有人点它，是工作流把它翻开的）
        .fromTo(img,
          { x: () => kit.rect(tile).cx - kit.rect(img).cx, y: () => kit.rect(tile).cy - kit.rect(img).cy, scale: 60 / 220, opacity: 0.4 },
          { x: 0, y: 0, scale: 1, opacity: 1, duration: 0.5, ease: "power3.out", immediateRender: false }, 0);
      return t;
    },
    tagsIn(d = 0.3) {
      return gsap.to(chipEls, { opacity: 1, scale: 1, duration: d, ease: "back.out(2.6)", stagger: 0.09 });
    },
    close() { const t = gsap.timeline(); t.to(el, { opacity: 0, duration: 0.3 }).set(el, { display: "none" }); return t; },
  };
}

/* ── 落在动态下方的那行评论：「我：…」+ AI 小标 ── */
function commentLine(kit, gsap, post, say) {
  const line = kit.h("p", "");
  line.append(kit.h("b", "", "我"), "：" + say);
  line.appendChild(kit.tag("AI 自动"));
  post.cmtBox.appendChild(line);
  gsap.set(line, { display: "none" });
  return line;
}

/* ═══════════════ sns-autorefresh 自动后台刷新朋友圈 ═══════════════
   工作流：每 5 分钟 → 自动拉取 → 入库。
   头部的倒计时自己走到 00:00，刷新图标转一圈，客户的新动态自己落进信息流盖 NEW；
   走完两轮 → 「2 条新动态入库」。全程没人在守着。 */
function autoRefresh({ gsap, kit, tl }) {
  const { feed } = mkFeed(kit, {
    fade: true,
    posts: [
      { who: CUSTOMERS.li, text: "这批老客户回购，谢谢一直支持。", imgs: 0, time: "2 小时前" },
      { who: CUSTOMERS.chen, text: "仓库到货了，都已经上架。", imgs: 2, time: "昨天" },
    ],
  });
  const strip = kit.scenario("客户随时在发 · 没人守着");
  const flow = kit.workflow([
    { label: "每 5 分钟", icon: "clock" },
    { label: "自动拉取", icon: "refresh" },
    { label: "入库", icon: "check" },
  ]);

  // 头部：刷新图标 + 计数角标，挨着相机
  const tools = kit.h("span", "pd-moments-tools");
  const rf = kit.h("i", "pd-moments-refresh");
  rf.appendChild(kit.icon("refresh"));
  const badge = kit.h("b", "pd-moments-badge", "+1");
  tools.append(rf, feed.camera, badge);
  feed.head.appendChild(tools);
  gsap.set(badge, { opacity: 0, scale: 0.4 });

  // 头部里的定时读数：AUTO PULL 05:00 自己往下走（不是开关，没有人去拨）
  const note = kit.note("", feed.head);
  note.classList.add("pd-moments-note");
  const timer = kit.h("b", "pd-moments-timer", "05:00");
  note.append(kit.h("span", "", "AUTO PULL"), timer);
  feed.head.insertBefore(note, tools);

  // 两条客户新动态预建、藏起来；后建的在最上（最新的最先看到）
  const p1 = addPost(feed, { who: CUSTOMERS.zhao, text: "店里招店长两名，有合适的推荐给我。", imgs: 0, time: "刚刚", top: true });
  const p2 = addPost(feed, { who: CUSTOMERS.wang, text: "新店下周开业，欢迎来捧场。", imgs: 2, time: "刚刚", top: true });
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
      .fromTo(badge, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(3)", immediateRender: false }, 0);
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

  tl.add(strip.in(), 0.1)
    .add(flow.in(), "<+0.1")
    .add(kit.fade(note), "<")
    .add(flow.step(0), 0.45)
    .add(kit.count(timer, 0, { from: 300, duration: 1, fmt: mmss }), "<")
    .add(kit.flash(timer, { color: "amber", duration: 0.4 }), ">-0.05")
    .add(flow.step(1), "<")
    .add(spin(), "<")
    .add(arrive(p1, 1), ">-0.15")
    .call(() => { timer.textContent = "05:00"; }, [], ">")
    .add(kit.count(timer, 0, { from: 300, duration: 0.9, fmt: mmss }), ">+0.2")
    .add(spin(), ">-0.12")
    .add(arrive(p2, 2), ">-0.15")
    .add(flow.step(2), ">-0.25")
    .add(kit.ok("已入库 · +2", { en: "AUTO SYNCED" }), ">+0.05")
    .add(flow.done(), "<")
    .add(strip.result("2 条新动态入库"), "<");
  return tl;
}

/* ═══════════════ sns-like 朋友圈点赞 ═══════════════
   工作流：客户发了新动态 → AI 判定值得互动 → 自动点赞。
   新动态自己落进来 → 一道扫描线扫过 → 「值得互动」→ 点赞栏自己亮起、名字自己写上「我」。 */
function like({ gsap, kit, tl }) {
  const { feed } = mkFeed(kit, {
    fade: true,
    posts: [
      { who: CUSTOMERS.li, text: "这批老客户回购，谢谢一直支持。", imgs: 0, time: "2 小时前" },
      { who: CUSTOMERS.chen, text: "仓库到货了，都已经上架。", imgs: 2, time: "昨天" },
    ],
  });
  const strip = kit.scenario("客户刚发了新动态 · 没人盯着");
  const flow = kit.workflow([
    { label: "客户发了新动态", icon: "bolt" },
    { label: "判定值得互动", ai: true },
    { label: "自动点赞", icon: "heart" },
  ]);

  const post = addPost(feed, { who: CUSTOMERS.wang, text: "新店下周开业，欢迎新老客户来捧场。", imgs: 2, time: "刚刚", top: true });
  gsap.set(post, { display: "none" });

  const scan = scanner(kit, gsap, post.body);
  // AI 的判定结果贴在这条动态的时间行上
  const verdict = kit.h("i", "pd-moments-verdict");
  verdict.append(aiBadge(kit), kit.h("span", "", "值得互动"));
  post.meta.insertBefore(verdict, post.more);
  gsap.set(verdict, { opacity: 0 });

  // 心形图标包一层，好做弹跳
  const heart = post.likeRow.firstElementChild;
  const hw = kit.h("i", "pd-moments-heart");
  post.likeRow.insertBefore(hw, heart);
  hw.appendChild(heart);
  post.likeRow.appendChild(kit.tag("AI 自动"));

  tl.add(strip.in(), 0.1)
    .add(flow.in(), "<+0.1")
    .add(dropIn(gsap, post), 0.5)
    .add(popTag(gsap, kit, post, "NEW", "pd-tag--neon"), ">-0.2")
    .add(flow.step(0), "<")
    .add(flow.step(1), ">+0.2")
    .add(scan.run(0.85), "<")
    .add(kit.pop(verdict, { y: 0, from: 0.6, duration: 0.34 }), ">-0.12")
    .add(flow.step(2), ">+0.35")
    .set(post.social, { display: "flex" }, "<")
    .set(post.likeRow, { display: "flex" }, "<")
    .add(kit.pop(post.social), "<")
    .call(() => post.likeRow.classList.add("is-on"), [], "<+0.1")
    .fromTo(hw, { scale: 0.2 }, { scale: 1, duration: 0.55, ease: "back.out(4)", immediateRender: false }, "<")
    .add(kit.type(post.likeNames, "我", { cps: 5, caret: false }), "<+0.15")
    .add(kit.flash(post.social, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已自动点赞", { en: "AUTO LIKED" }), ">+0.25")
    .add(flow.done(), "<")
    .add(strip.result("已第一时间点赞"), "<");
  return tl;
}

/* ═══════════════ sns-image-comment 朋友圈图片评论 ═══════════════
   工作流：客户发了带图动态 → AI 生成图片评论 → 自动评论。
   路径特征：走**图片查看层**——图自己翻开、被扫一遍、认出「门店/开业/花篮」，
   评论对着那张照片写出来，没有人点输入框。 */
function imageComment({ gsap, kit, tl }) {
  const { posts } = mkFeed(kit, {
    fade: true,
    posts: [
      { who: CUSTOMERS.wang, text: "新店装修完了，下周正式开业。", imgs: 3, time: "5 分钟前" },
      { who: CUSTOMERS.li, text: "这批老客户回购，谢谢一直支持。", imgs: 0, time: "2 小时前" },
    ],
  });
  const strip = kit.scenario("客户发了带图动态");
  const flow = kit.workflow([
    { label: "客户发了带图动态", icon: "image" },
    { label: "生成图片评论", ai: true },
    { label: "自动评论", icon: "comment" },
  ]);
  const post = posts[0];
  const tile = post.tiles[1];
  const say = "开业大吉，回头给您送套样品";
  const v = viewer(kit, gsap, tile, 2, post.tiles.length, ["门店", "开业", "花篮"]);
  const scan = scanner(kit, gsap, v.img);
  const line = commentLine(kit, gsap, post, say);

  tl.add(strip.in(), 0.1)
    .add(flow.in(), "<+0.1")
    .add(flow.step(0), 0.45)
    .add(kit.flash(post.grid, { color: "amber", duration: 0.5 }), "<")
    .add(v.open(), ">-0.15")
    .add(flow.step(1), "<+0.3")
    .add(scan.run(0.8), "<+0.1")
    .add(v.tagsIn(), ">-0.3")
    .set(v.ph, { display: "none" }, ">-0.1")
    .add(kit.type(v.text, say, { cps: 15 }), "<")
    .add(flow.step(2), ">+0.2")
    .add(v.state.to("已发送", true), "<")
    .add(kit.flash(v.bar, { color: "neon", duration: 0.55 }), "<")
    .add(v.close(), ">+0.2")
    .set(post.social, { display: "flex" }, "<")
    .set(line, { display: "block" }, "<")
    .add(kit.pop(post.social), "<")
    .add(kit.flash(post.social, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已自动评论", { en: "AUTO COMMENT · IMAGE" }), ">-0.05")
    .add(flow.done(), "<")
    .add(strip.result("评论已送达"), "<");
  return tl;
}

/* ═══════════════ sns-text-comment 朋友圈文字评论 ═══════════════
   工作流：客户发了纯文字动态 → AI 生成评论 → 自动评论。
   路径特征：不碰图片——AI 直接在正文里划出关键词「搬到城东新址」判成乔迁，
   评论条从这条动态**下方内联**长出来，字自己写完自己发。 */
function textComment({ gsap, kit, tl }) {
  const { feed } = mkFeed(kit, {
    fade: true,
    posts: [{ who: CUSTOMERS.chen, text: "仓库到货了，都已经上架。", imgs: 2, time: "昨天" }],
  });
  const strip = kit.scenario("客户发了纯文字动态");
  const flow = kit.workflow([
    { label: "客户发了纯文字动态", icon: "chat" },
    { label: "生成评论", ai: true },
    { label: "自动评论", icon: "comment" },
  ]);
  const post = addPost(feed, { who: CUSTOMERS.li, text: "", imgs: 0, time: "10 分钟前", top: true });
  const say = "恭喜乔迁，改天过去拜访";

  // 正文里的关键词单独包一层：AI 判定那一拍它会亮成琥珀
  const mark = kit.h("em", "pd-moments-mark", "搬到城东新址");
  post.text.replaceChildren(document.createTextNode("仓库"), mark, document.createTextNode("了，欢迎来看货。"));

  // 时间行上的识别结果
  const kw = kit.h("i", "pd-moments-verdict");
  kw.append(aiBadge(kit), kit.h("span", "", "乔迁"));
  post.meta.insertBefore(kw, post.more);
  gsap.set(kw, { opacity: 0 });

  // 动态下方内联长出来的评论条：AI 徽标 + 正文 + 状态药丸（没有发送键，因为没有人点）
  const bar = kit.h("div", "pd-moments-commentbar");
  const field = kit.h("span", "pd-moments-commentbar__field");
  const ph = kit.h("em", "pd-moments-commentbar__ph", "等待生成…");
  const text = kit.h("span", "pd-moments-commentbar__text");
  field.append(ph, text, kit.h("i", "pd-caret"));
  const state = statePill(kit, gsap, "生成中");
  bar.append(aiBadge(kit), field, state);
  post.body.insertBefore(bar, post.social);
  gsap.set(bar, { display: "none", opacity: 0 });

  const line = commentLine(kit, gsap, post, say);

  tl.add(strip.in(), 0.1)
    .add(flow.in(), "<+0.1")
    .add(flow.step(0), 0.45)
    .add(kit.flash(post.text, { color: "amber", duration: 0.5 }), "<")
    .add(flow.step(1), ">+0.15")
    .call(() => mark.classList.add("is-on"), [], "<")
    .add(kit.pop(kw, { y: 0, from: 0.6, duration: 0.34 }), "<+0.15")
    .set(bar, { display: "flex" }, ">+0.15")
    .add(kit.pop(bar, { y: -6 }), "<")
    .set(ph, { display: "none" }, ">-0.05")
    .add(kit.type(text, say, { cps: 15 }), "<")
    .add(flow.step(2), ">+0.2")
    .add(state.to("已发送", true), "<")
    .add(kit.flash(bar, { color: "neon", duration: 0.5 }), "<")
    .to(bar, { opacity: 0, duration: 0.25 }, ">-0.05")
    .set(bar, { display: "none" }, ">")
    .set(post.social, { display: "flex" }, ">-0.05")
    .set(line, { display: "block" }, "<")
    .add(kit.pop(post.social), "<")
    .add(kit.flash(post.social, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已自动评论", { en: "AUTO COMMENT" }), ">-0.05")
    .add(flow.done(), "<")
    .add(strip.result("评论已送达"), "<");
  return tl;
}

/* ═══════════════ sns-post 发布朋友圈 ═══════════════
   工作流：每天 10:00 → 取今日素材 → 自动发布。
   时钟自己走到 10:00:00，素材库里的文案和两张图自己填进发表面板，到点自己发出去。 */
function postMoment({ gsap, kit, tl }) {
  const { feed } = mkFeed(kit, {
    fade: true,
    posts: [
      { who: CUSTOMERS.wang, text: "新店下周开业，欢迎来捧场。", imgs: 2, time: "1 小时前" },
      { who: CUSTOMERS.li, text: "这批老客户回购，谢谢一直支持。", imgs: 0, time: "2 小时前" },
    ],
  });
  const strip = kit.scenario("每天 10:00 · 到点没人记得发");
  const flow = kit.workflow([
    { label: "每天 10:00", icon: "clock" },
    { label: "取今日素材", icon: "image" },
    { label: "自动发布", icon: "send" },
  ]);
  const copy = "春季新款到店，欢迎来看";

  const sheet = kit.sheet({ title: "定时任务 · 发表朋友圈" });
  sheet.cancel.remove();
  sheet.ok.textContent = "自动发表";
  sheet.ok.prepend(kit.icon("bolt"));
  const clock = kit.h("b", "pd-moments-clock", "09:59:57");
  sheet.foot.insertBefore(clock, sheet.ok);

  // 素材来源：这条不是人写的，是从素材库取的
  const src = kit.h("div", "pd-moments-src");
  src.append(kit.h("i", "pd-moments-src__l", "素材库"), kit.h("i", "pd-moments-chip", "春季新款 · 文案"), kit.h("i", "pd-moments-chip", "门店实拍 ×2"));
  gsap.set(src, { opacity: 0 });

  // 多行文本区
  const ta = kit.h("div", "pd-moments-ta");
  const ph = kit.h("em", "pd-moments-ta__ph", "等待素材…");
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
  sheet.body.append(src, ta, grid);
  kit.form([["谁可以看", "公开"], ["任务", "每天 10:00 自动发布"]], sheet.body);

  // 发出去之后落到最前的新帖，预建藏起
  const np = feed.post({ name: "我 · 门店", text: copy, imgs: 2, time: "刚刚", top: true });
  np.av.className = "pd-av pd-av--me";
  np.av.textContent = "我";
  gsap.set(np, { display: "none" });

  tl.add(strip.in(), 0.1)
    .add(flow.in(), "<+0.1")
    .add(sheet.open(), 0.35)
    .add(flow.step(0), "<+0.15")
    .add(kit.count(clock, 10 * 3600, { from: 10 * 3600 - 3, duration: 0.9, fmt: hms }), "<")
    .add(kit.flash(clock, { color: "amber", duration: 0.45 }), ">-0.05")
    .add(flow.step(1), "<")
    .add(kit.fade(src), "<")
    .call(() => ta.classList.add("is-edit"), [], "<")
    .set(ph, { display: "none" }, "<")
    .add(kit.type(txt, copy, { cps: 15 }), "<+0.15")
    .set(tiles, { display: "grid" }, ">+0.05")
    .fromTo(tiles, { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(2)", stagger: 0.1, immediateRender: false }, "<")
    .add(flow.step(2), ">+0.25")
    .call(() => ta.classList.remove("is-edit"), [], "<")
    .add(kit.flash(sheet.ok, { color: "neon", duration: 0.5 }), "<")
    .add(sheet.close(), ">-0.15")
    .add(dropIn(gsap, np), ">-0.2")
    .add(popTag(gsap, kit, np, "定时发布"), ">-0.25")
    .add(kit.flash(np, { color: "neon", duration: 0.7 }), "<")
    .add(kit.ok("已自动发布", { en: "AUTO POSTED" }), ">-0.05")
    .add(flow.done(), "<")
    .add(strip.result("朋友圈已发布"), "<");
  return tl;
}

export default {
  "sns-autorefresh": autoRefresh,
  "sns-like": like,
  "sns-image-comment": imageComment,
  "sns-text-comment": textComment,
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

/* 头部里的定时读数：从 .pd-note 的绝对定位改成头部 flex 的一员，靠右贴着工具组 */
.pd-root .pd-moments-note {
  position: static; transform: none; margin: 0 12px 0 auto; padding: 0; border: 0; background: none;
  display: flex; align-items: center; gap: 7px; font-weight: 400;
}
.pd-moments-timer {
  font-family: var(--pd-mono); font-size: 10px; letter-spacing: 0.1em; color: var(--pd-amber);
  padding: 2px 6px 1px; border-radius: 2px; border: 1px solid rgba(255, 194, 75, 0.4); background: rgba(255, 194, 75, 0.08);
}

/* AI 徽标：自动产生的内容边上都挂一枚 */
.pd-moments-ai {
  flex: none; font-family: var(--pd-mono); font-size: 8px; font-weight: 700; letter-spacing: 0.1em;
  padding: 2px 4px 1px; border-radius: 2px; color: #140d01; background: var(--pd-amber);
}

/* 状态药丸：代替人手点的「发送」键 */
.pd-moments-state {
  flex: none; font-family: var(--pd-mono); font-size: 9px; font-weight: 500; letter-spacing: 0.1em;
  padding: 4px 9px 3px; border-radius: 12px; white-space: nowrap;
  border: 1px solid var(--pd-line-strong); color: var(--pd-dim); background: rgba(255, 255, 255, 0.04);
}
.pd-moments-state.is-on { border-color: rgba(61, 242, 141, 0.55); color: var(--pd-neon); background: rgba(61, 242, 141, 0.12); }

/* 扫描线：AI 正在读这块内容 */
.pd-moments-scanhost { position: relative; }
.pd-moments-scan {
  position: absolute; left: -4px; right: -4px; top: 0; height: 2px; z-index: 3; pointer-events: none;
  background: linear-gradient(90deg, transparent, var(--pd-amber), transparent);
  box-shadow: 0 0 12px rgba(255, 194, 75, 0.75);
}

/* AI 判定结果：贴在动态的时间行上 */
/* 时间行是 space-between 的，margin-right:auto 让判定结果紧贴时间，不飘在正中 */
.pd-moments-verdict {
  display: inline-flex; align-items: center; gap: 5px; flex: none; margin: 0 auto 0 8px;
  padding: 2px 8px 2px 3px; border-radius: 11px; font-size: 10px; letter-spacing: 0.02em;
  border: 1px solid rgba(255, 194, 75, 0.45); background: rgba(255, 194, 75, 0.1); color: var(--pd-amber);
}
/* 正文里被 AI 划出来的关键词 */
.pd-moments-mark { border-bottom: 1px dashed transparent; transition: color 0.25s, border-color 0.25s; }
.pd-moments-mark.is-on { color: var(--pd-amber); border-bottom-color: rgba(255, 194, 75, 0.7); }

.pd-moments-heart { display: inline-flex; flex: none; }
.pd-root .pd-post__likes.is-on .pd-moments-heart { color: var(--pd-amber); }
.pd-root .pd-post__likes.is-on .pd-moments-heart .pd-ic { fill: var(--pd-amber); }

/* 内联评论条：从动态下方长出来，字自己写完自己发 */
.pd-moments-commentbar { display: flex; align-items: center; gap: 7px; margin-top: 3px; padding: 4px 4px 4px 7px; border: 1px solid var(--pd-line-strong); border-radius: 16px; background: rgba(20, 27, 23, 0.96); }
.pd-moments-commentbar__field { display: flex; align-items: center; min-width: 0; flex: 1 1 auto; color: var(--pd-ink); font-size: 11.5px; }
.pd-moments-commentbar__ph { color: var(--pd-faint); }

/* 图片查看层 */
.pd-moments-viewer {
  position: absolute; inset: 0; z-index: 20; pointer-events: none;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
  background: rgba(4, 7, 5, 0.9);
}
/* 情境条与工作流轨要全程可见：查看层夹在两者之间 */
.pd-screen.has-strip .pd-moments-viewer { top: 22px; }
.pd-screen.has-flow .pd-moments-viewer { bottom: 24px; }
/* HUD 落到头部以下（头部 36px），别跟透出来的相机图标叠在一起；再垫一块实底 */
.pd-moments-viewer__hud {
  position: absolute; right: 16px; top: 24px; padding: 2px 6px; border-radius: 2px;
  font-family: var(--pd-mono); font-size: 9.5px; letter-spacing: 0.24em; color: var(--pd-dim); background: rgba(4, 7, 5, 0.95);
}
.pd-moments-viewer__img {
  width: 220px; height: 148px; border-radius: 4px; display: grid; place-items: center; color: var(--pd-faint);
  background: var(--pd-tile); border: 1px solid var(--pd-line-strong); box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}
.pd-moments-viewer__img .pd-ic { width: 36px; height: 36px; }
.pd-moments-viewer__chips { display: flex; gap: 6px; }
.pd-moments-chip {
  padding: 2px 8px 1px; border-radius: 10px; font-size: 10px; letter-spacing: 0.04em;
  border: 1px solid rgba(255, 194, 75, 0.4); color: var(--pd-amber); background: rgba(255, 194, 75, 0.08);
}
.pd-moments-viewer__bar {
  display: flex; align-items: center; gap: 8px; width: 340px; padding: 5px 5px 5px 8px;
  border: 1px solid var(--pd-line-strong); border-radius: 20px; background: rgba(20, 27, 23, 0.96);
}
.pd-moments-viewer__field { flex: 1 1 auto; min-width: 0; display: flex; align-items: center; min-height: 22px; font-size: 12px; color: var(--pd-ink); }
.pd-moments-viewer__ph { color: var(--pd-faint); }

/* 发表抽屉：素材来源 + 文本区 + 图片格 + 定时读数 */
.pd-moments-src { display: flex; align-items: center; gap: 6px; flex: none; }
.pd-moments-src__l { font-family: var(--pd-mono); font-size: 9px; letter-spacing: 0.18em; color: var(--pd-faint); }
.pd-moments-ta {
  position: relative; height: 60px; flex: none; padding: 8px 10px; border-radius: 4px;
  border: 1px solid var(--pd-line-strong); background: rgba(255, 255, 255, 0.03); font-size: 12.5px; color: var(--pd-ink);
}
.pd-moments-ta__ph { position: absolute; left: 10px; top: 8px; color: var(--pd-faint); }
.pd-moments-ta__line { display: flex; align-items: center; min-height: 18px; }
.pd-moments-grid { display: grid; grid-template-columns: repeat(3, 60px); gap: 4px; flex: none; }
.pd-moments-add { width: 60px; height: 60px; border: 1px dashed var(--pd-line-strong); border-radius: 2px; display: grid; place-items: center; color: var(--pd-dim); }
.pd-moments-add .pd-ic { width: 16px; height: 16px; }
.pd-moments-clock {
  margin-right: auto; align-self: center; font-family: var(--pd-mono); font-size: 10.5px; letter-spacing: 0.12em;
  color: var(--pd-amber); padding: 3px 7px 2px; border-radius: 2px;
  border: 1px solid rgba(255, 194, 75, 0.4); background: rgba(255, 194, 75, 0.08);
}
.pd-root .pd-sheet__foot .pd-btn .pd-ic { width: 12px; height: 12px; }
`;
