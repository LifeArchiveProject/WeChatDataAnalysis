/* scenes / automation.js — 自动化工作流（3 项） */

function surface(kit, variant, title, eyebrow) {
  const el = kit.h("section", `pd-automation pd-automation--${variant} pd-pushed`);
  const head = kit.h("header", "pd-automation__head");
  const titleBox = kit.h("div", "pd-automation__title");
  titleBox.append(kit.h("b", "", title), kit.h("i", "pd-automation__eyebrow", eyebrow));
  const state = kit.h("i", "pd-automation__state", "待配置");
  head.append(titleBox, state);
  const body = kit.h("div", "pd-automation__body");
  el.append(head, body);
  kit.mount(el);
  return { el, head, body, state };
}

function pane(kit, parent, title, meta, cls = "") {
  const el = kit.h("section", `pd-automation__pane ${cls}`);
  const head = kit.h("header", "pd-automation__pane-head");
  head.append(kit.h("b", "", title), kit.h("i", "pd-automation__pane-meta", meta));
  const body = kit.h("div", "pd-automation__pane-body");
  el.append(head, body);
  parent.appendChild(el);
  return { el, head, body };
}

function field(kit, parent, label, value, cls = "") {
  const el = kit.h("div", `pd-automation__field ${cls}`);
  const k = kit.h("i", "pd-automation__field-label", label);
  const v = kit.h("b", "pd-automation__field-value", value);
  el.append(k, v);
  parent.appendChild(el);
  return Object.assign(el, { label: k, value: v });
}

function miniRow(kit, parent, iconName, title, detail) {
  const el = kit.h("div", "pd-automation__mini-row");
  const ic = kit.h("i", "pd-automation__mini-icon");
  ic.appendChild(kit.icon(iconName, "pd-ic pd-automation__mini-svg"));
  const txt = kit.h("span", "pd-automation__mini-text");
  txt.append(kit.h("b", "", title), kit.h("i", "", detail));
  el.append(ic, txt);
  parent.appendChild(el);
  return Object.assign(el, { ic, txt });
}

function setToggle(btn, label, on) {
  btn.textContent = `${label} · ${on ? "开启" : "关闭"}`;
  btn.classList.toggle("pd-btn--neon", on);
  btn.classList.toggle("pd-btn--ghost", !on);
  btn.classList.toggle("is-on", on);
}

function queueRow(kit, parent, { iconName, title, detail, result }) {
  const el = kit.h("div", "pd-automation__queue-row");
  const ic = kit.h("i", "pd-automation__queue-icon");
  ic.appendChild(kit.icon(iconName, "pd-ic"));
  const text = kit.h("div", "pd-automation__queue-text");
  text.append(kit.h("b", "", title), kit.h("i", "", detail));
  const status = kit.h("b", "pd-automation__queue-status", "排队中");
  el.append(ic, text, status);
  parent.appendChild(el);
  return Object.assign(el, { ic, text, status, result });
}

function processRow(kit, parent, iconName, label, value) {
  const el = kit.h("div", "pd-automation__process-row");
  const ic = kit.h("i", "pd-automation__process-icon");
  ic.appendChild(kit.icon(iconName, "pd-ic"));
  const text = kit.h("div", "pd-automation__process-text");
  text.append(kit.h("b", "", label), kit.h("i", "", value));
  const status = kit.h("b", "pd-automation__process-status", "等待事件");
  el.append(ic, text, status);
  parent.appendChild(el);
  return Object.assign(el, { ic, text, status, value: text.children[1] });
}

function resultStatus(row, text, cls) {
  row.status.textContent = text;
  row.status.className = `pd-automation__queue-status ${cls}`;
}

function processStatus(row, text, cls) {
  row.status.textContent = text;
  row.status.className = `pd-automation__process-status ${cls}`;
}

/* 选联系人 → 编排文字/图片 → 保存草稿 → 启动并暂停/继续一批调用。 */
function automationBroadcast({ kit, tl }) {
  const strip = kit.scenario("广播任务 · 按计划调用");
  const flow = kit.workflow([
    { label: "选联系人", icon: "users" },
    { label: "编排队列", icon: "edit" },
    { label: "保存草稿", icon: "file" },
    { label: "启动 / 暂停", icon: "play" },
  ], { title: "AUTOMATION" });
  const ui = surface(kit, "broadcast", "批量广播", "QUEUE / LOCAL DEMO");
  const config = pane(kit, ui.body, "任务配置", "BROADCAST");
  const queue = pane(kit, ui.body, "调用队列", "6 ITEMS");

  const pick = kit.h("div", "pd-automation__pick");
  pick.append(kit.avatarGrid(["王", "李", "陈", "赵"]));
  const pickText = kit.h("div", "pd-automation__pick-text");
  pickText.append(kit.h("b", "", "客户联系人"), kit.h("i", "", "4 人 · 已选"));
  pick.appendChild(pickText);
  config.body.appendChild(pick);
  field(kit, config.body, "发送时间", "今天 09:30", "pd-automation__field--schedule");
  const contentTitle = kit.h("i", "pd-automation__section-label", "内容队列");
  config.body.appendChild(contentTitle);
  const contentList = kit.h("div", "pd-automation__mini-list");
  miniRow(kit, contentList, "chat", "文字", "早安提醒");
  miniRow(kit, contentList, "image", "图片", "本周活动图");
  config.body.appendChild(contentList);
  const rule = kit.h("i", "pd-automation__guard", "每项单独记录 · 不等同于送达");
  config.body.appendChild(rule);

  const actions = kit.h("div", "pd-automation__actions");
  const saveBtn = kit.btn("保存草稿", "ghost", actions);
  const startBtn = kit.btn("启动任务", "amber", actions);
  const pauseBtn = kit.btn("暂停任务", "ghost", actions);
  gsap.set(pauseBtn, { display: "none" });
  config.body.appendChild(actions);

  const queueTop = kit.h("div", "pd-automation__queue-top");
  const queueLabel = kit.h("i", "", "逐项结果");
  const counter = kit.h("b", "pd-automation__counter", "0 / 6");
  queueTop.append(queueLabel, counter);
  queue.body.appendChild(queueTop);
  const viewport = kit.h("div", "pd-automation__queue-viewport");
  const queueList = kit.h("div", "pd-automation__queue-list");
  viewport.appendChild(queueList);
  queue.body.appendChild(viewport);
  const rows = [
    queueRow(kit, queueList, { iconName: "chat", title: "王总 · 文字", detail: "早安提醒", result: "调用完成" }),
    queueRow(kit, queueList, { iconName: "image", title: "李姐 · 图片", detail: "本周活动图", result: "待确认" }),
    queueRow(kit, queueList, { iconName: "chat", title: "陈总 · 文字", detail: "早安提醒", result: "调用完成" }),
    queueRow(kit, queueList, { iconName: "image", title: "赵总 · 图片", detail: "本周活动图", result: "待确认" }),
    queueRow(kit, queueList, { iconName: "chat", title: "林姐 · 文字", detail: "早安提醒", result: "调用完成" }),
    queueRow(kit, queueList, { iconName: "image", title: "周姐 · 图片", detail: "本周活动图", result: "待确认" }),
  ];
  gsap.set(rows, { opacity: 0, y: 8 });
  const queueFoot = kit.h("i", "pd-automation__queue-foot", "调用完成 / 待确认");
  queue.body.appendChild(queueFoot);

  const showRow = (row, index, at) => {
    tl.call(() => resultStatus(row, row.result, row.result === "待确认" ? "is-pending" : "is-done"), [], at)
      .add(kit.pop(row), at)
      .add(kit.flash(row, { color: row.result === "待确认" ? "amber" : "neon", duration: 0.42 }), at + 0.1)
      .add(kit.count(counter, index + 1, { from: index, duration: 0.28, fmt: (v) => `${Math.round(v)} / 6` }), at);
  };

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    .add(kit.pop(config.el), 0.25)
    .add(kit.pop(queue.el), 0.3)
    .add(flow.step(0), 0.7)
    .add(kit.flash(pick, { color: "amber", duration: 0.55 }), 0.78)
    .add(flow.step(1), 1.35)
    .add(kit.flash(contentList, { color: "amber", duration: 0.55 }), 1.45)
    .add(flow.step(2), 2.05)
    .add(kit.flash(saveBtn, { color: "amber", duration: 0.42 }), 2.12)
    .call(() => {
      saveBtn.textContent = "草稿已保存";
      saveBtn.classList.remove("pd-btn--ghost");
      saveBtn.classList.add("pd-btn--neon");
      ui.state.textContent = "草稿已保存";
    }, [], 2.45)
    .add(flow.step(3), 2.82)
    .call(() => {
      startBtn.style.display = "none";
      pauseBtn.style.display = "inline-flex";
      ui.state.textContent = "执行中";
    }, [], 2.9)
    .add(kit.flash(pauseBtn, { color: "amber", duration: 0.42 }), 3.0);

  showRow(rows[0], 0, 3.25);
  showRow(rows[1], 1, 3.7);
  tl.call(() => {
    pauseBtn.textContent = "继续任务";
    pauseBtn.classList.remove("pd-btn--ghost");
    pauseBtn.classList.add("pd-btn--amber");
    ui.state.textContent = "已暂停 · 等待继续";
  }, [], 4.12)
    .add(kit.flash(pauseBtn, { color: "amber", duration: 0.35 }), 4.12)
    .call(() => {
      pauseBtn.textContent = "暂停任务";
      ui.state.textContent = "执行中";
    }, [], 4.52);
  showRow(rows[2], 2, 4.6);
  showRow(rows[3], 3, 4.92);
  tl.to(queueList, { y: -44, duration: 0.52, ease: "power2.inOut" }, 5.02);
  showRow(rows[4], 4, 5.18);
  showRow(rows[5], 5, 5.42);
  tl.add(flow.done(), 5.62)
    .call(() => { ui.state.textContent = "调用完成 · 待确认"; }, [], 5.62)
    .add(kit.ok("调用完成", { en: "CALL COMPLETED", hold: 0.9 }), 5.68)
    .add(strip.result("3 项调用完成 · 3 项待确认"), 5.68);
  return tl;
}

/* 新好友已通过事件 → 套用备注/标签配置 → 调用欢迎消息；不替用户审批好友。 */
function automationOnboarding({ gsap, kit, tl }) {
  const strip = kit.scenario("新好友已通过事件 · 按配置处理");
  const flow = kit.workflow([
    { label: "已通过事件", icon: "user" },
    { label: "应用备注模板", icon: "edit" },
    { label: "标签 + 欢迎", icon: "send" },
  ], { title: "AUTOMATION" });
  const ui = surface(kit, "onboarding", "新好友处理", "EVENT / LOCAL DEMO");
  const config = pane(kit, ui.body, "处理配置", "NEW FRIEND");
  const eventPane = pane(kit, ui.body, "新好友事件", "PASSED EVENT");

  const toggleBox = kit.h("div", "pd-automation__toggle-box");
  const toggle = kit.btn("新好友处理 · 关闭", "ghost", toggleBox);
  const toggleHint = kit.h("i", "pd-automation__toggle-hint", "默认关闭 · 仅新通过事件");
  toggleBox.appendChild(toggleHint);
  config.body.appendChild(toggleBox);
  field(kit, config.body, "备注模板", "来源-姓名-需求");
  field(kit, config.body, "标签", "广告线索");
  field(kit, config.body, "欢迎消息", "你好，欢迎了解本次活动");
  const guard = kit.h("i", "pd-automation__guard", "不自动审批好友 · 不处理历史联系人");
  config.body.appendChild(guard);

  const event = kit.h("article", "pd-automation__event");
  const eventAv = kit.avatar("林", "them");
  const eventText = kit.h("div", "pd-automation__event-text");
  eventText.append(kit.h("b", "", "林姐"), kit.h("i", "", "广告咨询 · 新好友已通过"));
  const eventBadge = kit.h("b", "pd-automation__event-badge", "已通过");
  event.append(eventAv, eventText, eventBadge);
  eventPane.body.appendChild(event);
  gsap.set(event, { opacity: 0, y: 8 });
  const eventHint = kit.h("i", "pd-automation__event-hint", "前置事件：好友已通过");
  eventPane.body.appendChild(eventHint);

  const processTitle = kit.h("i", "pd-automation__section-label", "按开启配置处理");
  eventPane.body.appendChild(processTitle);
  const processList = kit.h("div", "pd-automation__process-list");
  const remark = processRow(kit, processList, "edit", "备注", "林姐");
  const tag = processRow(kit, processList, "key", "标签", "广告线索");
  const welcome = processRow(kit, processList, "send", "欢迎消息", "你好，欢迎了解本次活动");
  eventPane.body.appendChild(processList);
  const processFoot = kit.h("i", "pd-automation__queue-foot", "欢迎消息 · 调用完成 / 待确认");
  eventPane.body.appendChild(processFoot);
  gsap.set([remark, tag, welcome], { opacity: 0, y: 6 });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    .add(kit.pop(config.el), 0.25)
    .add(kit.pop(eventPane.el), 0.3)
    .call(() => {
      setToggle(toggle, "新好友处理", true);
      ui.state.textContent = "配置已开启";
    }, [], 0.78)
    .add(kit.flash(toggle, { color: "neon", duration: 0.45 }), 0.78)
    .add(flow.step(0), 1.02)
    .add(kit.pop(event), 1.22)
    .add(kit.flash(event, { color: "amber", duration: 0.55 }), 1.34)
    .add(strip.say("好友已通过 · 开始套用处理配置"), 1.4)
    .add(flow.step(1), 1.92)
    .call(() => processStatus(remark, "已写入", "is-done"), [], 2.08)
    .add(kit.pop(remark), 2.08)
    .add(kit.scramble(remark.value, "林姐-套餐咨询", { duration: 0.55 }), 2.12)
    .add(kit.flash(remark, { color: "neon", duration: 0.45 }), 2.16)
    .add(flow.step(2), 2.92)
    .call(() => processStatus(tag, "已写入", "is-done"), [], 3.08)
    .add(kit.pop(tag), 3.08)
    .add(kit.flash(tag, { color: "neon", duration: 0.45 }), 3.16)
    .call(() => processStatus(welcome, "调用完成 · 待确认", "is-pending"), [], 3.78)
    .add(kit.pop(welcome), 3.78)
    .add(kit.flash(welcome, { color: "amber", duration: 0.55 }), 3.88)
    .add(flow.done(), 4.55)
    .call(() => { ui.state.textContent = "欢迎调用完成 · 待确认"; }, [], 4.55)
    .add(kit.ok("调用完成", { en: "CALL COMPLETED", hold: 0.95 }), 4.62)
    .add(strip.result("欢迎消息已调用 · 待确认"), 4.62);
  return tl;
}

/* 规则来源/关键词 → 独立开关 → 新动态命中 → 仅生成待处理记录。 */
function automationMomentsFollow({ gsap, kit, tl }) {
  const strip = kit.scenario("跟圈规则 · 仅处理新动态");
  const flow = kit.workflow([
    { label: "读取新动态", icon: "bolt" },
    { label: "关键词命中", icon: "key" },
    { label: "生成待处理记录", icon: "clock" },
  ], { title: "AUTOMATION" });
  const ui = surface(kit, "moments", "朋友圈跟发规则", "RULE / LOCAL DEMO");
  const config = pane(kit, ui.body, "规则配置", "MOMENTS");
  const momentPane = pane(kit, ui.body, "新动态", "LIVE INPUT");

  field(kit, config.body, "规则来源", "客户朋友圈");
  const keywordTitle = kit.h("i", "pd-automation__section-label", "关键词");
  config.body.appendChild(keywordTitle);
  const chips = kit.chips(["开业", "上新", "活动"], { parent: config.body });
  chips.el.classList.add("pd-automation__chips");
  const switchTitle = kit.h("i", "pd-automation__section-label", "独立跟发开关");
  config.body.appendChild(switchTitle);
  const switches = kit.h("div", "pd-automation__switches");
  const likeToggle = kit.btn("点赞跟发 · 关闭", "ghost", switches);
  const commentToggle = kit.btn("评论跟发 · 关闭", "ghost", switches);
  config.body.appendChild(switches);
  const guard = kit.h("i", "pd-automation__guard", "默认关闭 · 按开启选项处理");
  config.body.appendChild(guard);
  const history = kit.h("i", "pd-automation__history", "仅新动态 · 不追溯历史");
  config.body.appendChild(history);

  const post = kit.h("article", "pd-automation__post");
  const postAv = kit.avatar("周", "them");
  const postBody = kit.h("div", "pd-automation__post-body");
  const postMeta = kit.h("div", "pd-automation__post-meta");
  postMeta.append(kit.h("b", "", "客户 · 周姐"), kit.h("i", "", "刚刚 · 新动态"));
  const postText = kit.h("p", "pd-automation__post-text", "新店开业啦，欢迎来看看本周新品");
  const postImage = kit.h("i", "pd-automation__post-image");
  postImage.appendChild(kit.icon("image", "pd-ic"));
  const match = kit.h("b", "pd-automation__match", "关键词命中");
  postBody.append(postMeta, postText, postImage, match);
  post.append(postAv, postBody);
  momentPane.body.appendChild(post);
  gsap.set(post, { opacity: 0, y: 8 });

  const record = kit.h("div", "pd-automation__record");
  const recordHead = kit.h("div", "pd-automation__record-head");
  recordHead.append(kit.h("b", "", "待处理记录"), kit.h("i", "", "新动态 · 1 条"));
  const recordRows = ["点赞跟发", "评论跟发"].map((label) => {
    const row = kit.h("div", "pd-automation__record-row");
    row.append(kit.icon("clock", "pd-ic"), kit.h("span", "", label), kit.h("b", "", "待处理"));
    record.appendChild(row);
    return row;
  });
  record.appendChild(recordHead);
  // 头部放回首位，列表仍保持短而可读。
  record.insertBefore(recordHead, record.firstChild);
  momentPane.body.appendChild(record);
  gsap.set(record, { opacity: 0, y: 8 });

  tl.add(strip.in(), 0.05)
    .add(flow.in(), 0.15)
    .add(kit.pop(config.el), 0.25)
    .add(kit.pop(momentPane.el), 0.3)
    .call(() => setToggle(likeToggle, "点赞跟发", true), [], 0.72)
    .add(kit.flash(likeToggle, { color: "neon", duration: 0.4 }), 0.72)
    .call(() => setToggle(commentToggle, "评论跟发", true), [], 1.02)
    .add(kit.flash(commentToggle, { color: "neon", duration: 0.4 }), 1.02)
    .add(flow.step(0), 0.82)
    .add(kit.pop(post), 1.42)
    .add(kit.flash(post, { color: "amber", duration: 0.55 }), 1.54)
    .add(flow.step(1), 2.02)
    .call(() => chips.rows[0].classList.add("is-hit"), [], 2.18)
    .add(kit.flash(chips.rows[0], { color: "amber", duration: 0.45 }), 2.18)
    .call(() => {
      match.textContent = "命中 · 关键词「开业」";
      match.style.display = "inline-flex";
    }, [], 2.52)
    .add(kit.pop(match), 2.52)
    .add(flow.step(2), 3.02)
    .add(kit.pop(record), 3.26)
    .add(kit.flash(record, { color: "amber", duration: 0.58 }), 3.38)
    .add(flow.done(), 4.42)
    .call(() => { ui.state.textContent = "待处理记录 · 按开启选项"; }, [], 4.42)
    .add(kit.ok("待处理", { en: "PENDING RECORD", hold: 1.05 }), 4.5)
    .add(strip.result("待处理记录 · 按开启选项"), 4.5);
  return tl;
}

export default {
  "automation-broadcast": automationBroadcast,
  "automation-onboarding": automationOnboarding,
  "automation-moments-follow": automationMomentsFollow,
};

export const css = `
.pd-automation {
  position: absolute; inset: 0; display: flex; flex-direction: column; min-width: 0; min-height: 0;
  overflow: hidden; color: var(--pd-ink); background: linear-gradient(135deg, rgba(61, 242, 141, 0.035), transparent 48%);
}
.pd-automation__head {
  height: 34px; flex: none; display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 0 13px; border-bottom: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.018);
}
.pd-automation__title { display: flex; align-items: baseline; gap: 9px; min-width: 0; }
.pd-automation__title b { font-size: 13px; font-weight: 600; white-space: nowrap; }
.pd-automation__eyebrow,
.pd-automation__state,
.pd-automation__pane-meta,
.pd-automation__guard,
.pd-automation__history,
.pd-automation__event-hint,
.pd-automation__queue-foot {
  font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.14em; color: var(--pd-faint);
}
.pd-automation__eyebrow { white-space: nowrap; }
.pd-automation__state { flex: none; color: var(--pd-amber); white-space: nowrap; }
.pd-automation__body {
  flex: 1 1 auto; min-height: 0; display: grid; gap: 9px; padding: 8px 10px 10px; overflow: hidden;
}
.pd-automation--broadcast .pd-automation__body { grid-template-columns: 218px minmax(0, 1fr); }
.pd-automation--onboarding .pd-automation__body { grid-template-columns: 244px minmax(0, 1fr); }
.pd-automation--moments .pd-automation__body { grid-template-columns: 226px minmax(0, 1fr); }
.pd-automation__pane {
  min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
  border: 1px solid var(--pd-line); border-radius: 4px; background: rgba(7, 11, 9, 0.42);
}
.pd-automation__pane-head {
  height: 31px; flex: none; display: flex; align-items: center; justify-content: space-between; gap: 7px;
  padding: 0 10px; border-bottom: 1px solid var(--pd-line); background: rgba(255, 255, 255, 0.018);
}
.pd-automation__pane-head b { font-size: 11.5px; font-weight: 600; white-space: nowrap; }
.pd-automation__pane-meta { white-space: nowrap; }
.pd-automation__pane-body { flex: 1 1 auto; min-height: 0; padding: 10px; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
.pd-automation__field {
  display: grid; grid-template-columns: 68px minmax(0, 1fr); align-items: center; gap: 8px;
  min-height: 28px; padding: 5px 7px; border: 1px solid transparent; border-radius: 3px; background: rgba(255, 255, 255, 0.035);
}
.pd-automation__field-label { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.1em; color: var(--pd-faint); white-space: nowrap; }
.pd-automation__field-value { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10.5px; font-weight: 400; color: var(--pd-ink); }
.pd-automation__field--schedule .pd-automation__field-value { color: var(--pd-amber); font-family: var(--pd-mono); }
.pd-automation__pick { display: flex; align-items: center; gap: 9px; padding: 6px 7px; border: 1px solid rgba(255, 194, 75, 0.26); border-radius: 3px; background: rgba(255, 194, 75, 0.06); }
.pd-automation__pick .pd-av { width: 31px; height: 31px; font-size: 9px; }
.pd-automation__pick-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.pd-automation__pick-text b { font-size: 10.5px; font-weight: 500; white-space: nowrap; }
.pd-automation__pick-text i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.1em; color: var(--pd-amber); white-space: nowrap; }
.pd-automation__section-label { display: block; margin-top: 1px; font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.18em; color: var(--pd-faint); }
.pd-automation__mini-list { display: flex; flex-direction: column; gap: 5px; }
.pd-automation__mini-row { display: flex; align-items: center; gap: 7px; min-height: 29px; padding: 4px 7px; border: 1px solid var(--pd-line); border-radius: 3px; background: rgba(255, 255, 255, 0.025); }
.pd-automation__mini-icon { width: 20px; height: 20px; flex: none; display: grid; place-items: center; border-radius: 3px; color: var(--pd-amber); background: rgba(255, 194, 75, 0.09); }
.pd-automation__mini-svg { width: 13px; height: 13px; }
.pd-automation__mini-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pd-automation__mini-text b { font-size: 10px; font-weight: 500; white-space: nowrap; }
.pd-automation__mini-text i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-automation__guard { display: block; margin-top: auto; line-height: 1.45; color: var(--pd-dim); letter-spacing: 0.08em; }
.pd-automation__actions { display: flex; align-items: center; gap: 6px; margin-top: 1px; }
.pd-automation__actions .pd-btn { padding-left: 8px; padding-right: 8px; font-size: 9.5px; }
.pd-automation__queue-top { display: flex; align-items: center; justify-content: space-between; padding-bottom: 1px; font-family: var(--pd-mono); font-size: 8.5px; letter-spacing: 0.14em; color: var(--pd-faint); }
.pd-automation__counter { color: var(--pd-neon); font-weight: 600; }
.pd-automation__queue-viewport { flex: 1 1 auto; min-height: 0; overflow: hidden; }
.pd-automation__queue-list { display: flex; flex-direction: column; gap: 5px; }
.pd-automation__queue-row { display: grid; grid-template-columns: 24px minmax(0, 1fr) auto; align-items: center; gap: 7px; min-height: 31px; padding: 4px 7px; border: 1px solid var(--pd-line); border-radius: 3px; background: rgba(255, 255, 255, 0.025); }
.pd-automation__queue-icon { width: 20px; height: 20px; display: grid; place-items: center; border-radius: 3px; color: var(--pd-dim); background: rgba(255, 255, 255, 0.04); }
.pd-automation__queue-icon .pd-ic { width: 12px; height: 12px; }
.pd-automation__queue-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pd-automation__queue-text b { font-size: 10.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-automation__queue-text i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; color: var(--pd-dim); white-space: nowrap; }
.pd-automation__queue-status { font-family: var(--pd-mono); font-size: 8.5px; font-weight: 500; letter-spacing: 0.04em; color: var(--pd-faint); white-space: nowrap; }
.pd-automation__queue-status.is-done { color: var(--pd-neon); }
.pd-automation__queue-status.is-pending { color: var(--pd-amber); }
.pd-root .pd-automation__queue-foot { display: block; padding-top: 2px; color: var(--pd-dim); }

.pd-automation__toggle-box { display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--pd-line); border-radius: 3px; background: rgba(255, 255, 255, 0.025); }
.pd-automation__toggle-box .pd-btn { align-self: flex-start; }
.pd-automation__toggle-hint { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; letter-spacing: 0.08em; color: var(--pd-faint); }
.pd-automation__event { display: flex; align-items: center; gap: 8px; padding: 8px; border: 1px solid rgba(61, 242, 141, 0.28); border-radius: 3px; background: rgba(61, 242, 141, 0.06); }
.pd-automation__event .pd-av { width: 30px; height: 30px; font-size: 10px; }
.pd-automation__event-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1 1 auto; }
.pd-automation__event-text b { font-size: 11px; font-weight: 500; white-space: nowrap; }
.pd-automation__event-text i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-automation__event-badge { flex: none; padding: 3px 5px 2px; border-radius: 2px; color: #04140b; background: var(--pd-neon); font-family: var(--pd-mono); font-size: 8px; letter-spacing: 0.08em; }
.pd-root .pd-automation__event-hint { display: block; line-height: 1.4; letter-spacing: 0.08em; }
.pd-automation__process-list { display: flex; flex-direction: column; gap: 5px; min-height: 0; }
.pd-automation__process-row { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto; align-items: center; gap: 7px; min-height: 34px; padding: 5px 7px; border: 1px solid var(--pd-line); border-radius: 3px; background: rgba(255, 255, 255, 0.025); }
.pd-automation__process-icon { width: 19px; height: 19px; display: grid; place-items: center; border-radius: 3px; color: var(--pd-amber); background: rgba(255, 194, 75, 0.09); }
.pd-automation__process-icon .pd-ic { width: 12px; height: 12px; }
.pd-automation__process-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pd-automation__process-text b { font-size: 10px; font-weight: 500; white-space: nowrap; }
.pd-automation__process-text i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; color: var(--pd-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-automation__process-status { font-family: var(--pd-mono); font-size: 8px; letter-spacing: 0.02em; color: var(--pd-faint); white-space: nowrap; }
.pd-automation__process-status.is-done { color: var(--pd-neon); }
.pd-automation__process-status.is-pending { color: var(--pd-amber); }

.pd-automation__chips { min-height: 22px; }
.pd-automation__chips .pd-chip { font-size: 9px; padding: 2px 7px; }
.pd-automation__switches { display: flex; flex-direction: column; gap: 6px; }
.pd-automation__switches .pd-btn { justify-content: flex-start; width: 100%; font-size: 9.5px; }
.pd-root .pd-automation__history { display: block; color: var(--pd-dim); letter-spacing: 0.08em; }
.pd-automation__post { display: flex; gap: 9px; padding: 9px; border: 1px solid var(--pd-line); border-radius: 4px; background: rgba(255, 255, 255, 0.035); }
.pd-automation__post > .pd-av { width: 30px; height: 30px; font-size: 10px; }
.pd-automation__post-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.pd-automation__post-meta { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
.pd-automation__post-meta b { font-size: 11px; font-weight: 500; color: var(--pd-blue); white-space: nowrap; }
.pd-automation__post-meta i { font-family: var(--pd-mono); font-style: normal; font-size: 8px; color: var(--pd-faint); white-space: nowrap; }
.pd-root .pd-automation__post-text { margin: 0; font-size: 10.5px; line-height: 1.5; color: var(--pd-ink); }
.pd-automation__post-image { width: 84px; height: 48px; display: grid; place-items: center; color: var(--pd-faint); border-radius: 3px; background: var(--pd-tile); }
.pd-automation__post-image .pd-ic { width: 18px; height: 18px; }
.pd-automation__match { display: none; align-self: flex-start; padding: 3px 6px 2px; border: 1px solid rgba(255, 194, 75, 0.4); border-radius: 2px; color: var(--pd-amber); background: rgba(255, 194, 75, 0.08); font-family: var(--pd-mono); font-size: 8.5px; font-weight: 500; letter-spacing: 0.06em; white-space: nowrap; }
.pd-automation__record { margin-top: auto; display: flex; flex-direction: column; gap: 5px; padding: 8px; border: 1px solid rgba(255, 194, 75, 0.3); border-radius: 4px; background: rgba(255, 194, 75, 0.055); }
.pd-automation__record-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-bottom: 4px; border-bottom: 1px solid rgba(255, 194, 75, 0.18); }
.pd-automation__record-head b { font-size: 10.5px; font-weight: 600; }
.pd-automation__record-head i { font-family: var(--pd-mono); font-style: normal; font-size: 8.5px; color: var(--pd-amber); white-space: nowrap; }
.pd-automation__record-row { display: grid; grid-template-columns: 15px minmax(0, 1fr) auto; align-items: center; gap: 6px; min-height: 22px; }
.pd-automation__record-row > .pd-ic { width: 12px; height: 12px; color: var(--pd-amber); }
.pd-automation__record-row span { font-size: 9.5px; color: var(--pd-ink); }
.pd-automation__record-row b { font-family: var(--pd-mono); font-size: 8.5px; font-weight: 500; color: var(--pd-amber); }
`;
