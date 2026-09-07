/* ════════════════════════════════════════════════════════════
   pro-demos / catalog.js — 高级版 54 项能力的唯一清单
   官网首屏清单、官网高级版幕、应用内「高级功能」弹窗都从这里取数据，
   改一处三处同步。key 是场景文件的索引，别随手改。
   ════════════════════════════════════════════════════════════ */

export const PRO_GROUPS = [
  {
    key: "edit", label: "消息修改", tag: "EDIT", icon: "fa-pen",
    items: [
      { key: "edit-text", name: "修改文字消息", caption: "已发出的文字，原地改成你要的样子，直接落库。" },
      { key: "edit-source", name: "编辑消息源码", caption: "打开消息的 XML 源码，逐字段手改。" },
      { key: "edit-time", name: "修改时间", caption: "把消息时间改到任意时刻，时间轴随之重排。" },
      { key: "edit-fields", name: "字段编辑", caption: "local_id、type、status……底层字段全部可写。" },
      { key: "edit-restore", name: "恢复原消息", caption: "改过头了？一键恢复到原始消息。" },
      { key: "edit-fix-sender", name: "修复为我发送", caption: "归属错位的消息，一键修正为「我发送」。" },
      { key: "edit-flip-sides", name: "反转微信气泡位置", caption: "整段对话左右互换，气泡与头像一起翻面。" },
      { key: "edit-delete-sys", name: "删除系统消息", caption: "撤回提示、系统提示，选中即删。" },
    ],
  },
  {
    key: "add", label: "消息补录", tag: "INSERT", icon: "fa-plus",
    items: [
      { key: "add-text", name: "文字", caption: "在任意位置补写一条文字消息。" },
      { key: "add-image", name: "图片", caption: "补录一张图片消息，缩略图原样呈现。" },
      { key: "add-file", name: "文件", caption: "补录文件消息：文件名、大小、图标一应俱全。" },
      { key: "add-voice", name: "语音", caption: "补录语音消息，带时长与声波图标。" },
      { key: "add-video", name: "视频", caption: "补录视频消息，封面与时长齐备。" },
      { key: "add-emoji", name: "表情", caption: "补录一枚表情包。" },
      { key: "add-transfer", name: "转账记录", caption: "补录一条转账记录，金额与状态可定。" },
      { key: "add-redpacket", name: "红包记录", caption: "补录一条红包记录，祝福语随你写。" },
      { key: "add-location", name: "位置", caption: "补录位置消息：地名、详址、地图一并生成。" },
      { key: "add-link", name: "链接卡片", caption: "补录链接卡片：标题、摘要、缩略图。" },
      { key: "add-miniapp", name: "小程序卡片", caption: "补录一张小程序卡片。" },
      { key: "add-channels", name: "视频号卡片", caption: "补录一张视频号卡片。" },
      { key: "add-quote", name: "引用消息", caption: "补录带引用的消息，引用原文自动关联。" },
      { key: "add-merged", name: "合并聊天记录", caption: "补录一条「聊天记录」合并转发卡片。" },
      { key: "add-call", name: "通话记录", caption: "补录一条语音/视频通话记录及时长。" },
      { key: "add-sys", name: "系统消息", caption: "补录一条居中的系统提示。" },
      { key: "add-pat", name: "拍一拍记录", caption: "补录一条「拍了拍」记录。" },
    ],
  },
  {
    key: "action", label: "微信动作", tag: "SEND", icon: "fa-paper-plane",
    items: [
      { key: "send-text", name: "发送文字消息", caption: "在这里打字，微信那边真的发出去。" },
      { key: "send-at", name: "发送群聊 @ 消息", caption: "群里 @ 指定成员，成员选择器与微信一致。" },
      { key: "send-image", name: "发送图片消息", caption: "选一张图，经微信客户端真实发送。" },
      { key: "send-video", name: "发送视频消息", caption: "发送视频消息，走微信原生通道。" },
      { key: "send-emoji", name: "发送表情消息", caption: "发送一枚表情包。" },
      { key: "send-file", name: "发送文件消息", caption: "选择本地文件，发送到当前微信会话。" },
      { key: "send-link", name: "发送链接卡片", caption: "填写链接信息，发送一张链接卡片。" },
      { key: "send-voice", name: "发送语音消息", caption: "选择语音文件，支持 MP3 语音发送。" },
      { key: "send-pat", name: "发送拍一拍", caption: "隔空拍一拍对方。" },
      { key: "chat-mark-read", name: "会话标记已读", caption: "将当前会话标记为本地已读。" },
      { key: "chat-set-mute", name: "会话免打扰", caption: "用同一个开关打开或关闭会话免打扰。" },
    ],
  },
  {
    key: "moments", label: "朋友圈", tag: "MOMENTS", icon: "fa-camera",
    items: [
      { key: "sns-autorefresh", name: "自动后台刷新朋友圈", caption: "后台定时拉取朋友圈，新动态自动入库。" },
      { key: "sns-like", name: "朋友圈点赞", caption: "给任意一条朋友圈点赞。" },
      { key: "sns-image-comment", name: "朋友圈图片评论", caption: "在朋友圈图片下留下评论。" },
      { key: "sns-text-comment", name: "朋友圈文字评论", caption: "在朋友圈动态下留下文字评论。" },
      { key: "sns-post", name: "发布朋友圈", caption: "文字加图片，直接发布一条朋友圈。" },
    ],
  },
  {
    key: "group", label: "群聊", tag: "GROUP", icon: "fa-users",
    items: [
      { key: "group-my-nick", name: "修改本人群昵称", caption: "修改自己在本群的昵称。" },
      { key: "group-notice", name: "发布群公告", caption: "发布群公告，全员 @ 提醒。" },
      { key: "group-create", name: "新建群聊", caption: "勾选联系人，新建一个群聊。" },
      { key: "group-rename", name: "修改群名称", caption: "修改群名称，会话列表同步更新。" },
      { key: "group-add-members", name: "拉好友进群", caption: "选择联系人并加入当前群聊。" },
      { key: "group-invite-members", name: "邀请群成员", caption: "向群成员发出邀请。" },
      { key: "group-remove-members", name: "移除群成员", caption: "从群聊中移除指定成员。" },
      { key: "group-leave", name: "退出群聊", caption: "退出当前群聊。" },
    ],
  },
  {
    key: "contact", label: "联系人", tag: "CONTACT", icon: "fa-address-book",
    items: [
      { key: "contact-remark", name: "修改好友备注", caption: "修改好友备注，全局生效。" },
      { key: "contact-accept", name: "同意好友请求", caption: "一键同意好友请求。" },
      { key: "contact-delete", name: "删除好友", caption: "从联系人中删除好友。" },
      { key: "contact-add", name: "添加好友", caption: "填写验证消息并发送好友请求。" },
    ],
  },
  {
    key: "alert", label: "提醒", tag: "ALERT", icon: "fa-bell",
    items: [
      { key: "alert-keyword", name: "群聊/单聊关键词提醒", caption: "添加关键词，群聊与单聊新消息命中即刻提醒。" },
    ],
  },
];

// 每项就地补上所属分组与全局序号（1 起）；PRO_ITEMS 与分组里的是同一批对象
let _n = 0;
for (const g of PRO_GROUPS) for (const it of g.items) Object.assign(it, { index: ++_n, group: g.key, groupLabel: g.label, groupTag: g.tag });
export const PRO_ITEMS = PRO_GROUPS.flatMap((g) => g.items);

export const PRO_TOTAL = PRO_ITEMS.length;

export const PRO_BY_KEY = Object.fromEntries(PRO_ITEMS.map((it) => [it.key, it]));

// 官网首屏六栏清单沿用的五模块视图：群聊 / 联系人 / 提醒 合并成一栏
export const PRO_HERO_MODULES = (() => {
  const merged = { name: "群聊、联系人与提醒", items: [] };
  const out = [];
  for (const g of PRO_GROUPS) {
    if (g.key === "group" || g.key === "contact" || g.key === "alert") merged.items.push(...g.items);
    else out.push({ name: g.label, items: [...g.items] });
  }
  out.push(merged);
  return out;
})();
