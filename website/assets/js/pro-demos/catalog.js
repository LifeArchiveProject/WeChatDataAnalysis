/* ════════════════════════════════════════════════════════════
   pro-demos / catalog.js — 高级版 54 项能力的唯一清单
   官网首屏清单、官网首屏舞台、应用内「高级功能」弹窗都从这里取数据，
   每项四件套：name 做什么 / caption 怎么做 / use 用在什么场景 / need 为什么需要它。
   改一处三处同步。key 是场景文件的索引，别随手改。
   ════════════════════════════════════════════════════════════ */

export const PRO_GROUPS = [
  {
    key: "edit", label: "消息修改", tag: "EDIT", icon: "fa-pen",
    items: [
      { key: "edit-text", name: "修改文字消息", caption: "已发出的文字，原地改成你要的样子，直接落库。", use: "按截图核对", need: "恢复回来的那句话和截图对不上，改成原话" },
      { key: "edit-source", name: "编辑消息源码", caption: "打开消息的 XML 源码，逐字段手改。", use: "卡片修复", need: "恢复回来的链接卡片标题乱码，改源码让它可读" },
      { key: "edit-time", name: "修改时间", caption: "把消息时间改到任意时刻，时间轴随之重排。", use: "时间线校准", need: "从备份恢复的记录时间错乱，改回真实那天" },
      { key: "edit-fields", name: "字段编辑", caption: "local_id、type、status……底层字段全部可写。", use: "数据修复", need: "恢复回来的记录字段错位，底层逐项改回来" },
      { key: "edit-restore", name: "恢复原消息", caption: "改过头了？一键恢复到原始消息。", use: "一键回退", need: "改过头了，把原来那句原样还回来" },
      { key: "edit-fix-sender", name: "修复为我发送", caption: "归属错位的消息，一键修正为「我发送」。", use: "归属修正", need: "恢复的记录里，自己说的话挂在了对方名下" },
      { key: "edit-flip-sides", name: "反转微信气泡位置", caption: "整段对话左右互换，气泡与头像一起翻面。", use: "视角翻转", need: "从对方手机导出的那份，翻回自己的视角" },
      { key: "edit-delete-sys", name: "删除系统消息", caption: "撤回提示、系统提示，选中即删。", use: "导出前清理", need: "撤回与系统提示刷了一屏，留档前清干净" },
    ],
  },
  {
    key: "add", label: "消息补录", tag: "INSERT", icon: "fa-plus",
    items: [
      { key: "add-text", name: "文字", caption: "在任意位置补写一条文字消息。", use: "补回那句话", need: "一气之下清空了记录，按截图把那句话补回来" },
      { key: "add-image", name: "图片", caption: "补录一张图片消息，缩略图原样呈现。", use: "图还在相册", need: "照片还在相册里，把它放回当时的位置" },
      { key: "add-file", name: "文件", caption: "补录文件消息：文件名、大小、图标一应俱全。", use: "文件还在", need: "当时传的文件还在，补回它发出的那一刻" },
      { key: "add-voice", name: "语音", caption: "补录语音消息，带时长与声波图标。", use: "语音找回", need: "导出过的那条语音，补回它原来的位置" },
      { key: "add-video", name: "视频", caption: "补录视频消息，封面与时长齐备。", use: "视频找回", need: "视频还在，记录没了，把它补回时间线" },
      { key: "add-emoji", name: "表情", caption: "补录一枚表情包。", use: "语气还原", need: "补齐表情，当时的语气才对得上" },
      { key: "add-transfer", name: "转账记录", caption: "补录一条转账记录，金额与状态可定。", use: "转账补回", need: "转账在账单里查得到，记录里却没了" },
      { key: "add-redpacket", name: "红包记录", caption: "补录一条红包记录，祝福语随你写。", use: "红包补回", need: "那年的红包记录缺了一笔，按账单补齐" },
      { key: "add-location", name: "位置", caption: "补录位置消息：地名、详址、地图一并生成。", use: "地点补回", need: "第一次见面的位置补回来，这段才完整" },
      { key: "add-link", name: "链接卡片", caption: "补录链接卡片：标题、摘要、缩略图。", use: "分享补回", need: "当时分享的那篇文章，补回原来的位置" },
      { key: "add-miniapp", name: "小程序卡片", caption: "补录一张小程序卡片。", use: "卡片补回", need: "当时下单的小程序卡片，补回对话里" },
      { key: "add-channels", name: "视频号卡片", caption: "补录一张视频号卡片。", use: "卡片补回", need: "当时发的视频号卡片，补回原来的位置" },
      { key: "add-quote", name: "引用消息", caption: "补录带引用的消息，引用原文自动关联。", use: "上下文对齐", need: "补回带引用的那句，前后文才连得上" },
      { key: "add-merged", name: "合并聊天记录", caption: "补录一条「聊天记录」合并转发卡片。", use: "并入另一段", need: "把另一段对话作为聊天记录卡片并进来" },
      { key: "add-call", name: "通话记录", caption: "补录一条语音/视频通话记录及时长。", use: "通话补回", need: "那通电话的记录缺了，按时长补回来" },
      { key: "add-sys", name: "系统消息", caption: "补录一条居中的系统提示。", use: "补回那一天", need: "补回「你已添加对方」，认识的那天才在" },
      { key: "add-pat", name: "拍一拍记录", caption: "补录一条「拍了拍」记录。", use: "互动还原", need: "补回那次拍一拍，互动痕迹不缺角" },
    ],
  },
  {
    key: "action", label: "微信动作", tag: "SEND", icon: "fa-paper-plane",
    items: [
      { key: "send-text", name: "发送文字消息", caption: "在这里打字，微信那边真的发出去。", use: "客服自动回复", need: "客户半夜问价，规则命中先自动接住，人第二天跟进" },
      { key: "send-at", name: "发送群聊 @ 消息", caption: "群里 @ 指定成员，成员选择器与微信一致。", use: "群内派单", need: "工单来了，群里 @ 值班同事马上认领" },
      { key: "send-image", name: "发送图片消息", caption: "选一张图，经微信客户端真实发送。", use: "物料秒发", need: "客户要收款码，图片立刻发过去" },
      { key: "send-video", name: "发送视频消息", caption: "发送视频消息，走微信原生通道。", use: "教程分发", need: "操作视频一条条发给每个新客户" },
      { key: "send-emoji", name: "发送表情消息", caption: "发送一枚表情包。", use: "社群活跃", need: "群里冷场，发个表情把气氛接住" },
      { key: "send-file", name: "发送文件消息", caption: "选择本地文件，发送到当前微信会话。", use: "报价单直发", need: "PDF 报价单直接发出去，不用手动转发" },
      { key: "send-link", name: "发送链接卡片", caption: "填写链接信息，发送一张链接卡片。", use: "活动推送", need: "活动链接批量发给客户，一个都不漏" },
      { key: "send-voice", name: "发送语音消息", caption: "选择语音文件，支持 MP3 语音发送。", use: "语音通知", need: "录好的语音通知，逐个会话发出去" },
      { key: "send-pat", name: "发送拍一拍", caption: "隔空拍一拍对方。", use: "轻提醒", need: "不打扰地戳一下，比发消息更轻" },
      { key: "chat-mark-read", name: "会话标记已读", caption: "将当前会话标记为本地已读。", use: "红点清理", need: "本地未读红点清掉，不发已读回执" },
      { key: "chat-set-mute", name: "会话免打扰", caption: "用同一个开关打开或关闭会话免打扰。", use: "免打扰", need: "本地给广告群静音，正事不被淹没" },
    ],
  },
  {
    key: "moments", label: "朋友圈", tag: "MOMENTS", icon: "fa-camera",
    items: [
      { key: "sns-autorefresh", name: "自动后台刷新朋友圈", caption: "后台定时拉取朋友圈，新动态自动入库。", use: "客户动态监测", need: "后台定时刷，客户发的动态一条不漏" },
      { key: "sns-like", name: "朋友圈点赞", caption: "给任意一条朋友圈点赞。", use: "客情维护", need: "客户刚发新动态，第一时间点个赞" },
      { key: "sns-image-comment", name: "朋友圈图片评论", caption: "在朋友圈图片下留下评论。", use: "客情维护", need: "在客户的图片下留一句，比点赞更有温度" },
      { key: "sns-text-comment", name: "朋友圈文字评论", caption: "在朋友圈动态下留下文字评论。", use: "客情维护", need: "给客户的动态留一句评论，保持存在感" },
      { key: "sns-post", name: "发布朋友圈", caption: "文字加图片，直接发布一条朋友圈。", use: "定时发圈", need: "每天固定时段发一条产品动态" },
    ],
  },
  {
    key: "group", label: "群聊", tag: "GROUP", icon: "fa-users",
    items: [
      { key: "group-my-nick", name: "修改本人群昵称", caption: "修改自己在本群的昵称。", use: "群昵称规范", need: "进客户群统一改成「公司-姓名」" },
      { key: "group-notice", name: "发布群公告", caption: "发布群公告，全员 @ 提醒。", use: "全员通知", need: "活动通知发成群公告，全员都 @ 到" },
      { key: "group-create", name: "新建群聊", caption: "勾选联系人，新建一个群聊。", use: "开专属群", need: "新客户成交，马上拉一个专属服务群" },
      { key: "group-rename", name: "修改群名称", caption: "修改群名称，会话列表同步更新。", use: "群名规范", need: "客户群统一命名，一眼就能找到" },
      { key: "group-add-members", name: "拉好友进群", caption: "选择联系人并加入当前群聊。", use: "拉人支援", need: "问题超纲，把技术同事拉进客户群" },
      { key: "group-invite-members", name: "邀请群成员", caption: "向群成员发出邀请。", use: "邀请入群", need: "把名单里的人逐个邀请进群" },
      { key: "group-remove-members", name: "移除群成员", caption: "从群聊中移除指定成员。", use: "清退广告号", need: "群里混进广告号，直接移除" },
      { key: "group-leave", name: "退出群聊", caption: "退出当前群聊。", use: "退无效群", need: "结束的项目群，一个个退掉" },
    ],
  },
  {
    key: "contact", label: "联系人", tag: "CONTACT", icon: "fa-address-book",
    items: [
      { key: "contact-remark", name: "修改好友备注", caption: "修改好友备注，全局生效。", use: "备注规范化", need: "客户备注统一成「来源-姓名-需求」" },
      { key: "contact-accept", name: "同意好友请求", caption: "一键同意好友请求。", use: "自动通过好友", need: "投放来的客户加好友，自动通过不流失" },
      { key: "contact-delete", name: "删除好友", caption: "从联系人中删除好友。", use: "清理僵尸粉", need: "180 天零互动的号，命中规则就清掉" },
      { key: "contact-add", name: "添加好友", caption: "填写验证消息并发送好友请求。", use: "加回头客", need: "老客户名单，逐个发出好友申请" },
    ],
  },
  {
    key: "alert", label: "提醒", tag: "ALERT", icon: "fa-bell",
    items: [
      { key: "alert-keyword", name: "群聊/单聊关键词提醒", caption: "添加关键词，群聊与单聊新消息命中即刻提醒。", use: "盯单不漏", need: "「发票」「报价」一命中，立刻弹提醒" },
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
