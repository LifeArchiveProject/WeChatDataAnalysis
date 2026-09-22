# 演示数据库种子脚本

`tools/seed_demo_database.py` 生成一个**完全虚构、但真实经过微信 4.x WCDB 加密**的演示账号，
用于开发、回归测试、文档截图与演示视频。

## 为什么需要它

项目里已有的 `tools/seed_ai_acceptance.py` 生成的是**明文 SQLite**，只覆盖 AI 验收这一条链路。
但在以下场景里，明文库不够用：

- 验证「密钥 -> 逐页 HMAC 校验 -> 解密 -> 解析 -> 展示」的完整链路；
- 排查解密失败时，需要一个**格式正确、内容已知**的对照样本；
- 贡献者本地没有微信环境，或不愿意用真实聊天记录做调试；
- 文档、官网、演示视频需要可以公开的素材。

真实聊天记录包含隐私，不适合进入任何公开产物；明文库又无法覆盖解密链路。
本脚本填补的正是这个空档：**格式与真实库一致，内容 100% 虚构**。

## 生成的内容

```
output/demo/
├── demo_keys.json                 # 演示密钥（account -> key/display_name/alias）
└── databases/
    └── wxid_demo_2026/
        └── db_storage/
            ├── message/message_0.db   # 加密，5 个会话共 29 条消息
            └── contact/contact.db     # 加密，6 个联系人 / 1 个群
```

覆盖的消息类型：文字（`1`）、链接卡片与转账卡片（`49`，含 `refermsg` 引用结构）、
系统消息（`10000`）、表情（`47`）、语音占位（`34`）。

结构上的两点刻意设计：

1. **`Name2Id` 不包含账号本人** —— 真实微信如此。账号本人由「出现在全部单聊表中的
   `real_sender_id`」判定；如果把自己的行写进 `Name2Id`，会话列表会多出一条自己和自己聊天的记录。
2. **昵称全部带「示例」标记，域名统一 `example.com`，群号使用 `10000000001@chatroom`** ——
   确保任何截图或导出产物都能被一眼识别为虚构数据。

## 用法

```bash
# 生成到 output/demo（已被 /output/ 规则忽略，不会进入版本库）
python tools/seed_demo_database.py

# 生成后用项目自身的扫描与解密器做端到端自校验
python tools/seed_demo_database.py --check

# 指定输出目录
python tools/seed_demo_database.py --output /tmp/demo-account
```

`--check` 会调用 `scan_account_databases_from_path` 与 `decrypt_wechat_databases`，
逐页验证 HMAC、检查解密后 `PRAGMA integrity_check` 是否为 `ok`、以及 `Name2Id` / `Contact`
表是否存在。自校验通过时输出类似：

```
自校验通过：扫描到 5 个数据库，成功解密 2/2 个
```

## 加密格式

脚本实现的是 `wechat_decrypt._decrypt_page` 的**逆过程**，参数直接从上游模块导入而非硬编码，
因此上游调整页格式时脚本会跟着一起变：

| 项 | 值 |
| --- | --- |
| 页大小 | 4096 字节 |
| 密钥派生 | PBKDF2-HMAC-SHA512，256000 轮，32 字节 |
| mac 密钥 | PBKDF2-HMAC-SHA512(enc_key, salt ^ 0x3A, 2 轮) |
| 每页布局 | `ciphertext + iv(16) + hmac(64)`，第 1 页前加 16 字节 salt |
| HMAC 覆盖 | 密文 + IV + 小端页码（SHA-512） |
| 每页预留 | 80 字节（= IV 16 + HMAC 64） |

明文库在加密前需要「每页预留 80 字节」的页面布局，这一步容易出错：仅靠
`PRAGMA user_version` 让 SQLite 落盘文件头是不够的，还必须把 page1 btree 头里
「cell 内容区起始」（文件偏移 `100 + 5`）从 4096 改成 4016，否则 SQLite 会按原始
页头计算空闲空间并报 `database integrity check: database disk image is malformed`。

## 回归保护

`tests/test_seed_demo_database.py` 守护「演示数据与真实解密链路一致」这一契约：
逐页比对 HMAC 与 `_compute_page_hmac` 的结果、验证解密后是合法 SQLite、
校验 `Name2Id` 不含本人、并确认昵称都带虚构标记。

## 安全边界

- 脚本只写 `--output` 指定的目录，**不读取、不修改**任何真实微信目录。
- 演示密钥是固定常量（`sha256("wechat-data-analysis-demo-key")`），公开无风险；
  它只用于打开本脚本自己生成的样本库。
