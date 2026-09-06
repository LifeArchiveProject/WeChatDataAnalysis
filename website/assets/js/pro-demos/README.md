# pro-demos — 高级版能力演示引擎

官网「高级版」幕与应用内「高级功能」弹窗共用的一套骨架屏动画：左边能力清单、右边舞台，自动逐项播放，点清单即切换。
调性沿用官网：近黑绿底、琥珀 = 写入动作、霓虹绿 = 成功落库、JetBrains Mono HUD、发丝线、扫描光。

```
catalog.js   43 项能力的唯一清单（key / name / caption / 分组），三处共用
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

约定：

- 场景签名 `({ gsap, kit, tl, root, reduced, item }) => tl`。**所有补间都挂到 `tl` 上**（`tl.add / tl.to / tl.call`），不要裸调 `gsap.to`，舞台切换时靠 kill(tl) 清场。
- 坐标系固定 640×400（`.pd-screen`），外层等比缩放；积木尺寸按这个坐标系写死。别让内容溢出（聊天列表区 `overflow: hidden`，塞太多行会被裁）。
- 时长 4–7 秒；节奏：0.3s 起手 → 动作 → 结果 → `kit.ok()` 印章停 0.9s。舞台播完再停 `hold` 秒切下一项。
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
- 通用：`kit.pop(el)` 入场、`kit.fade(el,{to})`、`kit.collapse(el)` 删除折叠、`kit.flash(el,{color:"amber"|"neon"|"red"})`、`kit.skel(w,h)` 骨架条、`kit.lines([w...])`、`kit.avatar(label, "me"|"them"|"muted")`、`kit.avatarGrid([...])`、`kit.icon(name)`、`kit.note(text)` 屏底注释、`kit.btn(text, tone, parent)`、`kit.h(tag, cls, text)`、`kit.rect(el)`

## 调试与截图

- lab 页：`python3 website/serve.py 4321` → `http://127.0.0.1:4321/dev/pro-lab.html?scene=<key>&only=1`；控制台 `__panel.select(key)` / `__panel.stage.seek(2.4)`
- 走片：`?scene=<key>&strip=1&frames=6` 一屏并排定格 6 个关键帧
- 无头截图：`node website/dev/shot.mjs <key1,key2|all> <outDir> [--frames=6]`，每个场景一张走片 PNG（用 Playwright 缓存里的 headless shell，约 1 秒一张）
