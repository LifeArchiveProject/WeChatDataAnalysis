# pro-demos — 高级版能力演示引擎

官网「高级版」幕与应用内「高级功能」弹窗共用的一套骨架屏动画：左边能力清单、右边舞台，自动逐项播放，点清单即切换。
调性沿用官网：近黑绿底、琥珀 = 写入动作、霓虹绿 = 成功落库、JetBrains Mono HUD、发丝线、扫描光。

```
catalog.js   54 项能力的唯一清单（key / name 做什么 / caption 怎么做 / use 什么场景 / need 为什么需要 / 分组），三处共用
kit.js       骨架屏积木（聊天窗、气泡、卡片、光标、菜单、抽屉、表单、代码、印章、通知、朋友圈、会话列表、勾选器、芯片）
stage.js     舞台 + 清单 + 面板（createProStage / createProList / createProPanel）
index.js     对外入口：createProPanel(host, { gsap, ... })；汇总 scenes/*.js
scenes/      每个分组一个文件，导出 { [key]: sceneFn } 与 css 字符串
../css/pro-demos.css   全部样式，令牌都挂在 .pd-root 上，不依赖宿主 :root
```

## 接入

```js
// 官网（gsap 是 UMD 全局）
import { createProPanel } from "./pro-demos/index.js";
const panel = createProPanel(hostEl, { gsap: window.gsap });
panel.setActive(false); // 滚离视口时静默；页面隐藏由引擎自己监听
panel.select("send-text"); // 外部切换
panel.destroy();

// 应用（Nuxt，gsap 走 npm）
import { gsap } from "gsap";
import { createProPanel } from "@website/js/pro-demos/index.js";
import "@website/css/pro-demos.css";
```

`createProPanel` 参数：`gsap`（必填）、`start`（起始 key）、`hold`（播完停留秒数，默认 0.9）、`autoplay`（默认 true）、`loopOne`（单场景循环）、`speed`、`reduced`（减少动效）、`onChange(item)`。

清单栏数：宿主给 `.pd-root` 设 `--pd-list-cols: 2`。面板宽度 ≤ 720px 时自动上下堆叠（容器查询）。

## 写一个场景

```js
function sendText({ kit, tl }) {
  const chat = kit.chat({ title: "老地方" });   // 640×400 的场景屏里放一张聊天窗
  chat.seed(3);                                  // 三条默认往来
  const c = kit.cursor();                        // 白点 + 琥珀环
  tl.add(c.show(), 0.2)
    .add(c.tap(chat.field), 0.3)                 // 移动过去 + 点击波纹
    .add(kit.type(chat.field, "到楼下了", { cps: 14 }))
    .add(c.tap(chat.send), ">+0.2")
    .call(() => chat.row("r", "到楼下了"))
    .add(kit.ok("已发送", { en: "SENT" }), ">")
    .add(c.hide(), "<");
  return tl;
}
export default { "send-text": sendText };
export const css = ``;   // 本组局部样式（可空），引擎注入一次
```

### 场景优先（最重要的一条）

观众看的是**为什么要用它**，不是操作步骤。只演「右键→改字→保存」，看完仍然一头雾水。所以每个场景必须回答三件事：

1. **此刻发生了什么**（情境）：`kit.scenario(...)` 在屏幕顶端立一条情境条，开场 `strip.in()` 滑入。真实动作类写业务时刻（`kit.scenario("23:14 · 客户咨询进来了")`）；本地存档类写自己的整理现场，且必须带 `{ local: true }`（`kit.scenario("按截图核对 · 这句话改错了", { local: true })`）。
2. **谁在做、做了什么**（操作）：对话内容、人名、日期一律换成该场景真实会出现的东西——**但两类的取材不通用**。真实动作类用业务对象：客户「王总」「报价单」「工单 #2043」，不要「老地方 / 友 / 我」这种没头没尾的闲聊；本地存档类用私人往来：会话「小满」、侧栏「家人群 / 老同学 / 室友」、带年份的日期（`chat.time("2024-08-09 21:40")`），**不许**出现客户 / 报价 / 单价 / 合同 / 订单群这类 B2B 内容。
3. **所以呢**（结果）：结尾 `strip.result(...)` 在情境条右端亮出结果，与 `kit.ok()` 印章同一拍。真实动作类给业务结果（「客户 2 秒内收到回复」）；本地存档类只给本地结果（「和截图对上了」「时间线补齐了」）。

场景取自 catalog.js 每项的 `use`（场景标签）与 `need`（为什么需要），舞台 HUD 会把这两句常驻显示——动画演的必须**就是这一个场景**，别自己另编一个。

**本地写入 vs 真实动作（不许搞混）**：消息修改（8）、消息补录（17）、会话标记已读、会话免打扰这 27 项**只写本地解密副本，单向、不回写微信，对方永远看不到**；其余 27 项（发送类、朋友圈、群聊、联系人）才是经微信客户端的真实操作。
前者一律 `kit.scenario(text, { local: true })`，情境条上会常驻一枚「本地副本 · 不回写微信」——画面演的是一场真实对话，不点明就会被读成「对方也看到了」。
文案同理：本地类的情境与结果只能讲**我这边的存档**（「和截图对上了」「时间线补齐了」「这段记忆完整了」），**不许**出现「对方收到」「客户看到了」「TA 就知道了」「与对方一致」。
本地类的统一世界观：**一气之下清空了和 TA 的聊天记录，事后想找回**——能从备份恢复的恢复，恢复回来错乱的校订，恢复不了的按截图、相册、账单一条条补回本地副本。

两类还有各自的**演法**，别搞混：

| | 本地存档类（27） | 真实动作类（27） |
| --- | --- | --- |
| 语境 | 私人：误删后找回、校订自己的副本；会话「小满」+ `railNames: ["家人群", "老同学", "室友"]` | 业务：客服值班、社群运营、获客维护；客户「王总」「报价单」「工单 #2043」 |
| 谁在操作 | **我**在整理自己的档案，光标点击是合理的 | **没有人**——工作流自动触发，不许出现「人点按钮」 |
| 必用积木 | `kit.scenario(text, { local: true })` | `kit.workflow([触发, AI, 执行])` + `flow.step(i)` |
| 禁用 | `kit.workflow` | `{ local: true }`、`kit.cursor` 的点击动作 |

```js
// 真实动作类：一条工作流轨说明「是规则和 AI 在跑，不是人在点」
const flow = kit.workflow([
  { label: "新消息命中「现货」", icon: "bolt" },  // 触发
  { label: "生成回复", ai: true },                // AI 节点，自带 AI 徽标
  { label: "自动发送", icon: "send" },            // 执行
]);
tl.add(flow.in(), "<+0.1").add(flow.step(0), ...).add(flow.step(1), ...).add(flow.done(), ...);
```
工作流轨占屏幕底端 24px（与情境条的顶端 22px 对称），已知布局根自动收高、印章自动上移；自建布局根加 `pd-pushed`。

```js
// 真实动作类：业务语境 + 工作流轨，结果讲对外效果
function sendText({ kit, tl }) {
  const twin = kit.twin({ title: "客户 · 王总" });
  const strip = kit.scenario("23:14 · 客户咨询进来了");
  tl.add(strip.in(), 0.1)
    .add(/* …工作流逐步点亮… */)
    .add(strip.result("客户 2 秒内收到回复"), ">-0.3");
}

// 本地存档类：私人语境 + { local: true }，结果只讲我这边的存档，光标是「我」在整理
function editText({ kit, tl }) {
  const chat = kit.chat({ title: "小满", railNames: ["家人群", "老同学", "室友"] });
  const strip = kit.scenario("按截图核对 · 这句话改错了", { local: true });
  chat.time("2024-08-09 21:40");
  tl.add(strip.in(), 0.1)
    .add(/* …右键改字、写回本地副本… */)
    .add(strip.result("和截图对上了"), ">-0.3");
}
```

约定：

- 场景签名 `({ gsap, kit, tl, root, reduced, item }) => tl`。**所有补间都挂到 `tl` 上**（`tl.add / tl.to / tl.call`），不要裸调 `gsap.to`，舞台切换时靠 kill(tl) 清场。
- 坐标系固定 640×400（`.pd-screen`），外层等比缩放；积木尺寸按这个坐标系写死。别让内容溢出（聊天列表区 `overflow: hidden`，塞太多行会被裁）。
- 时长 4.5–7.5 秒；节奏：情境条滑入 → 动作 → 结果（`strip.result` + `kit.ok()` 印章停 0.9s）。舞台播完再停 `hold` 秒切下一项。
- 情境条占屏幕顶端 22px，已知布局根（`.pd-chat` / `.pd-feed` / `.pd-win`）会自动下推；自建布局根请加 `pd-pushed` 类。
- 需要目标位置的补间（光标 `c.to(el)`、菜单 `kit.menu(items, { at: el })`）都是**懒取位置**：在补间开始那一刻才量 DOM，所以先 `tl.call` 把元素加进 DOM 再让光标过去是安全的。
- 文字动画：`kit.type(el, text)` 打字机、`kit.scramble(el, text)` 乱码落定、`kit.count(el, n)` 数字滚表。
- 局部样式写进本文件 `css` 字符串，类名以 `pd-<group>-` 前缀，别改 kit.js / pro-demos.css / stage.js。
- 减少动效：`reduced` 为真时打字/乱码瞬时完成，不必额外处理。
- GSAP 定位：不带 position 的 `tl.call()` 落在**时间轴末尾**而不是上一条之后——同一时间轴里只要有拉长的 flash/hold，后面的步骤就会整体后移；步骤要显式给 `">"` / `"<"`。
- 样式特异性：`.pd-root p { margin:0 }` 是 (0,1,1)，场景局部类 `.pd-xxx` (0,1,0) 盖不过它，用 `<p>` 做局部元素时写成 `.pd-root .pd-xxx`。
- 走片截图（strip）会冻结 CSS transition，类切换后的颜色立刻可见；真实播放里 .pd-btn/.pd-field 有 0.2s 过渡。

## 积木速查（kit.js）

- 光标 `kit.cursor({x,y})` → `show/hide/to(target,{duration,dx,dy})/click(target)/tap(target)/dbl(target)`
- 聊天窗 `kit.chat({ title, rail=true, group=false })` → `{ el, rail, sessions[], head, title, more, list, input, field, tools, send, row(side, content|text, {name, av}), time(t), sys(t), seed(n) }`；`row` 返回 `.pd-row`，带 `av / body / content`
- 气泡 `kit.bubble(text, side)`；系统行 `kit.sys(text, parent)`；拍一拍 `kit.pat({from,to}, parent)`；标签 `kit.tag("已修改")`
- 卡片 `kit.card.image() / video({dur}) / file({name,size}) / voice({sec,side}) / emoji() / transfer({amount,note}) / redpacket({text}) / location({name,addr}) / link({title,desc}) / miniapp({title,app}) / channels({name}) / quote({text,quote,side}) / merged({title,lines}) / call({dur,video,side})`
- 菜单 `kit.menu([...labels | {icon,label,danger}], { at, dx, dy })` → `open/close/hover(i)/items[]`
- 抽屉 `kit.sheet({ title })` → `{ el, body, ok, cancel, open(), close() }`；表单 `kit.form([[label, value, mono?]], parent)` → `{ rows[] }`（行有 `label/value`，`is-edit` 类高亮）；代码块 `kit.code(lines, parent)` → `{ lines[] }`（行加 `is-edit`）
- 印章 `kit.ok("已写入", { en: "WRITTEN", hold })` 返回 timeline；`kit.stamp(text)` 只建元素
- 通知 `kit.toast({ title, body, app })` → `show/hide`
- 朋友圈 `kit.feed()` → `{ head, camera, list, post({name,text,imgs,time,likes,comments,top}), seed(n) }`；post 带 `text / grid / tiles[] / more / social / likeRow / likeNames / cmtBox`
- 会话列表 `kit.sessions(names, { parent })` → `{ rows[], add(name|{name,grid:[...]}, {top}) }`
- 勾选器 `kit.picker(names)` → `{ rows[], done, check(i, on) }`；芯片 `kit.chips(words)` → `{ rows[], add(w) }`
- 窗口 `kit.window({ title, kind: "app"|"wechat" })` → `{ el, bar, body, title }`
- **补录三件套**：`chat.rowAt(refRow, side, content, opts)` 在某行之后插入一行；`kit.gap(chat, refRow)` 在某行之后放一条琥珀插槽线 + 「⊕ 补录」药丸（初始 opacity 0，自己 fade 进来，带 `pill`）；`kit.compose({ type: "图片", fields: [[label, value]] })` 打开补录抽屉（类型芯片行 + 发送方/时间字段 + 预览区 `preview` + 「保存」`ok`），预览区里 `preview.appendChild(kit.card.image())` 即可
- **整段流程（优先用）**：`kit.insertFlow(chat, { after: row, side: "r"|"l"|"sys", type: "图片", fields, build(previewMode) => node, beat({content, comp, cursor}) => tween, stamp, en, name })` 一次编好「插槽出现 → 点补录 → 抽屉预览 → 保存 → 新行落进聊天 → 印章」整段，返回 timeline（挂到 tl 上：`tl.add(kit.insertFlow(...), 0)`）；`kit.sendFlow(twin, { beat({cursor, appChat, wxChat}) => tween, build(where) => node, side, stamp, en, noSendButton })` 编好「左窗操作 → 点发送 → 光点飞到微信窗 → 两边落一条 → 印章」整段
- **双窗口飞送**：`kit.twin({ title, group })` → `{ app, wx, appChat, wxChat, fly(fromEl, toEl) }`：左 330px 是本应用、右 296px 是微信客户端，两边各一张无会话栏聊天窗；`fly()` 返回一粒琥珀光点从 A 飞到 B 的 timeline，发送类场景统一用它表达「这边点发送，微信那边真的收到」
- 工作流轨 `kit.workflow(steps, { title })` → `{ in(d), step(i, d), done(d), nodes }`；steps 项形如 `{ label, ai, icon }`（`ai:true` 挂 AI 徽标）
- 情境条 `kit.scenario(text, { local })` → `{ in(d), result(txt, d), say(txt, d), text, out }`（`say` 中途改写情境文案）
- 通用：`kit.pop(el)` 入场、`kit.fade(el,{to})`、`kit.collapse(el)` 删除折叠、`kit.flash(el,{color:"amber"|"neon"|"red"})`、`kit.skel(w,h)` 骨架条、`kit.lines([w...])`、`kit.avatar(label, "me"|"them"|"muted")`、`kit.avatarGrid([...])`、`kit.icon(name)`、`kit.note(text)` 屏底注释、`kit.btn(text, tone, parent)`、`kit.h(tag, cls, text)`、`kit.rect(el)`

## 调试与截图

- lab 页：`python3 website/serve.py 4321` → `http://127.0.0.1:4321/dev/pro-lab.html?scene=<key>&only=1`；控制台 `__panel.select(key)` / `__panel.stage.seek(2.4)`
- 走片：`?scene=<key>&strip=1&frames=6` 一屏并排定格 6 个关键帧
- 无头截图：`node website/dev/shot.mjs <key1,key2|all> <outDir> [--frames=6]`，每个场景一张走片 PNG（用 Playwright 缓存里的 headless shell，约 1 秒一张）
