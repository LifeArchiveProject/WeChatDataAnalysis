# WeChatDataAnalysis 项目阶段总览

> 生成日期：2026-08-19
> 当前分支：`codex/voice-transcription-merged`
> 功能基线：`6a7fabd`（2026-08-14 的 PR #84 语音转写合并点）
> 上游状态：当前 `origin/main` 为 `156ae88`（2026-08-18），本分支落后 14 个提交
> 版本：2.0.11

---

## 1. 项目定位

WeChatDataAnalysis 是一个现代微信数据分析和本地聊天记录读取工具，具备以下能力：

- **微信数据库解密**：读取并解密微信本地 SQLCipher 数据库
- **聊天记录浏览**：按联系人查看完整聊天记录，支持图文、语音、视频、转账、引用等多种消息类型
- **媒体资源还原**：解密 `.dat` 图片、还原视频/语音，支持大图本地优先 + CDN 原图回源
- **本地语音转文字**：可选功能，使用 faster-whisper（CPU / NVIDIA GPU）将语音消息转为文字
- **数据导出**：HTML / JSON / TXT / Excel 多格式导出，带完整性封印（wce_integrity / native-core）
- **年度总结（Wrapped）**：生成个人年度聊天数据统计卡片
- **MCP 接入**：向 AI 客户端（如 Claude）暴露分析工具接口
- **跨平台桌面端**：Electron + Nuxt 前端 + Python FastAPI 后端，Windows / macOS

---

## 2. 技术架构

### 2.1 前端（`frontend/`）

- Nuxt 3 + Vue 3 + Tailwind CSS
- Pinia 状态管理，组件化聊天界面
- 关键模块：
  - `frontend/components/chat/`：聊天界面组件
  - `frontend/composables/chat/`：消息拉取、会话、导出逻辑
  - `frontend/lib/chat/`：消息规范化、图片分组、性能日志
  - `frontend/stores/`：实时聊天、主题等全局状态

### 2.2 后端（`src/wechat_decrypt_tool/`）

- Python 3.11 + FastAPI + uvicorn
- SQLCipher / WCDB 数据库处理
- 关键模块：
  - `routers/`：REST API 路由层
  - `voice_transcription.py`：语音转文字服务（faster-whisper）
  - `native_core_*.py`：受控原生 core 客户端（导出封印/加密、实时数据库读取）
  - `cdn_image_service.py`：CDN 原图下载
  - `macos_db_key_helper.py`：macOS 密钥捕获
  - `wechat_detection.py` / `key_*.py`：微信检测与数据库密钥

### 2.3 桌面端（`desktop/`）

- Electron 主进程 + 后端进程管理
- `src/main.cjs`：Electron 主逻辑 + 后端启动
- `scripts/build-backend.cjs`：PyInstaller 打包后端
- `scripts/*.cjs`：macOS 签名、Windows 私钥 PKI、native-core 打包等构建链脚本
- `tests/`：Node 单元测试

---

## 3. 核心功能详情

### 3.1 微信官方语音转写（新增，本次整合核心）

微信客户端自身会为语音消息生成转写文字，存储在消息记录的 `packed_info_data` 字段（protobuf 格式）中。

**实现：**
- `src/wechat_decrypt_tool/wechat_voice_transcript.py`（新增，171 行）
  - 手写 protobuf 解析器（无第三方依赖）
  - 解析顶层字段 5（length-delimited）→ 子字段 2（UTF-8 文本）
  - 对畸形、超长、损坏 payload 安全忽略（不抛异常）
- `src/wechat_decrypt_tool/routers/chat.py`
  - 3 处消息组装路径注入 `wechatTranscript` / `transcriptSource` 字段
  - 仅对 `local_type == 34`（语音消息）触发提取
- 前端展示（`MessageContent.vue`）
  - 有官方转写时显示「微信转写」标签 + 文字
  - 无官方转写时提示「微信转写尚未同步，请在微信中切换会话后刷新」
  - 官方转写与本地 Whisper 识别可并存显示

### 3.2 语音数据回退定位（本次增强）

当语音消息的 `server_id`（19 位大整数）查不到语音数据时，使用 `local_id + create_time` 组合进行安全回退。

**实现（`voice_transcription.py`）：**
- `load_voice_data(account_dir, server_id, local_id=None, create_time=None)`
- 查找优先级：静态库 `svr_id` 精确 → 实时库 `svr_id` 精确 → 静态库 `local_id+create_time` → 实时库 `local_id+create_time`
- 要求 `voice_data` 非空、**唯一候选**才返回；多条候选返回空（不猜测）
- 缓存 ID 在 `server_id` 为 0 时置空（不污染缓存）

**配套改动：**
- `routers/chat_media.py`：`VoiceTranscriptionRequest` 增加 `local_id`/`create_time` 字段，路由透传
- `useChatMessages.js`：请求转写时携带 `local_id`/`create_time`

### 3.3 本地 Whisper 语音转文字（上游已合入）

- faster-whisper + ctranslate2，CPU / CUDA 可选
- OpenCC 繁简转换
- CUDA 探测与自动 CPU 回退
- 转写结果按源数据哈希缓存
- RTX 5060 GPU 优化文档（`docs/rtx5060-faster-whisper-gpu.md`）

### 3.4 CDN 原图下载（上游已合入）

- 本地缺原图时，从消息 XML 提取 `cdnbigimgurl`（fileid）+ `aeskey`，从微信 CDN 拉取原图
- 每账号每天限 10 次（配额可配置）
- 设置页「自动获取原图」开关（`/api/system/cdn_image/toggle`）
- 用户点击「尝试加载大图」时 `fetch_remote=true` 强制回源

### 3.5 桌面启动 Unicode 路径修复（本次修复）

- `desktop/src/main.cjs`：`uv run` 增加 `--no-editable`
- 解决 Python 3.11 在含中文/Unicode 路径下 editable install `.pth` 解码失败问题
- 配套测试：`desktop/tests/backend-startup.test.cjs`

### 3.6 导出与完整性（上游原生 core）

- HTML 导出附带语音转写 CSS（`_VOICE_TRANSCRIPT_EXPORT_CSS`）
- wce_integrity 原生模块负责导出 CSS / 完整性记录 / 封印（`export_integrity.py`）
- native-core broker 提供导出解密加密、hanzi 文件封印、实时数据库读取授权
- 私有签名链：Windows private-PKI、macOS XKey

---

## 4. 本次整合改动清单

以下清单仅统计相对 `6a7fabd` 的功能源码、测试和开发启动脚本；不包含运行输出、依赖目录及其他本地辅助文件。共修改 **10 个文件**、新增 **3 个文件 + 1 个启动脚本**：

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/wechat_decrypt_tool/wechat_voice_transcript.py` | 新增 | 官方转写提取 |
| `tests/test_wechat_voice_transcript.py` | 新增 | 提取测试 |
| `tests/test_chat_wechat_voice_transcript_fields.py` | 新增 | 字段链路测试 |
| `src/wechat_decrypt_tool/routers/chat.py` | 修改 | 注入转写字段 ×3 |
| `src/wechat_decrypt_tool/voice_transcription.py` | 修改 | 回退定位 |
| `src/wechat_decrypt_tool/routers/chat_media.py` | 修改 | 请求透传 |
| `frontend/components/chat/MessageContent.vue` | 修改 | 转写 UI |
| `frontend/composables/chat/useChatMessages.js` | 修改 | 状态合并 + 字段 |
| `frontend/lib/chat/message-normalizer.js` | 修改 | 转写字段 + 合并函数 |
| `frontend/assets/css/chat.css` | 修改 | 转写样式 |
| `frontend/tests/voice-transcription-message.test.js` | 修改 | 测试同步 |
| `desktop/src/main.cjs` | 修改 | `--no-editable` |
| `desktop/tests/backend-startup.test.cjs` | 修改 | 启动断言 |
| `run_dev.cmd` | 新增 | 当前开发机的双击启动脚本（使用 `%~dp0` 定位项目，但 `uv`/Node 路径为当前机器专用） |

### 明确保留的上游内容（未覆盖）

- `desktop/scripts/build-backend.cjs`：`--collect-all faster_whisper/ctranslate2/av/opencc` + `runPackagedOpenccSmoke`
- `src/wechat_decrypt_tool/chat_export_service.py`：`_VOICE_TRANSCRIPT_EXPORT_CSS` 追加
- `frontend/composables/useApi.js`：已导出全部 4 个语音 API + 2 个 CDN API
- `uv.lock` / `frontend/package-lock.json`：以上游锁定为准
- 全部 native-core 基础设施、macOS 签名链、CDN 下载逻辑

---

## 5. 测试状态

| 测试集 | 结果 | 说明 |
|---|---|---|
| 桌面 `desktop/tests/backend-startup.test.cjs` | 5/5 通过 | 含 `--no-editable` 断言 |
| 前端 vitest | 11/11 通过 | 语音转写 UI 与状态 |
| 前端 node 测试（`*.test.mjs`） | 11/11 通过 | 图片分组、规范化 |
| 后端 `test_wechat_voice_transcript.py` | 3/3 通过 | 官方转写 payload 解析 |
| 后端 `test_chat_wechat_voice_transcript_fields.py` | 1/1 通过 | 字段链路 |
| 后端 `test_voice_transcription_contract.py` | 6/6 通过 | 契约 |
| 后端 `test_voice_transcription.py` | 21/21 通过 | 识别与缓存 |
| 后端 `test_voice_transcription_settings.py` | 8/8 通过 | 设置 API |
| `test_chat_export_html_format.py` | 7 失败 | 环境问题：缺 native-core broker 产物（`WCE_NATIVE_CORE_ARTIFACT_DIR`），与本次改动无关 |

---

## 6. 开发与运行指南

### 6.1 双击启动（推荐）

```text
运行项目根目录 run_dev.cmd
```

在当前开发机自动完成：PATH 注入 → 桌面 `npm run dev` → 前端 Nuxt (port 3000) → 后端 FastAPI (port 10392) → Electron 窗口。脚本中的 `uv` 和 Node 路径为当前机器专用，换机器或换安装位置前需要调整脚本。

### 6.2 手动启动

```powershell
# 终端 1：后端
cd <repo>
.venv\Scripts\python.exe main.py

# 终端 2：前端
cd frontend
npm run dev
```

### 6.3 测试命令

```powershell
# 桌面
cd desktop && node --test tests/backend-startup.test.cjs

# 前端
cd frontend && npx vitest run && node --test tests/*.test.mjs

# 后端（在 src 目录下）
.venv\Scripts\python.exe -m pytest ../tests/test_voice_transcription.py -v
```

---

## 7. 与上游的关系

- **上游** `LifeArchiveProject/WeChatDataAnalysis`：官方主线；本文档生成时为 `156ae88`
- **本分支** `codex/voice-transcription-merged`：以旧上游合并点 `6a7fabd` 为基础的本地独有增强，尚未合入当前官方主线
- 本地独有价值 = 微信官方转写提取 + 语音定位回退 + Unicode 路径修复
- 建议长期保持：以 `origin/main` 顶上的方式演进，本地增强以 PR 形式回馈上游

### 已知差距与风险

1. 当前分支比 `origin/main` 落后 14 个提交，尚未整合上游后续的原生微信转写、账号体验、实时同步和发布修复。
2. 导出 HTML 测试需配置 native-core 产物才能在无网络环境通过。
3. 真实微信数据库的官方转写提取尚未用真实数据回归（测试基于构造 protobuf）。
4. 语音文件回退定位仅做单测，未在真实缺失 `server_id` 场景端到端验证；该回退仅用于主动本地转写，语音播放仍按 `server_id` 查询。
5. 数据库读取异常当前会与“未找到语音数据”共用错误结果，排障时应结合后端日志区分数据确实缺失与访问失败。

---

## 8. 文件结构速览

```
WeChatDataAnalysis/
├── run_dev.cmd                      # 双击启动脚本
├── main.py                          # 后端入口
├── pyproject.toml                   # Python 依赖与构建
├── frontend/                        # Nuxt 前端
│   ├── composables/chat/            # 聊天逻辑
│   ├── lib/chat/                    # 消息规范化
│   └── components/chat/             # 聊天 UI
├── src/wechat_decrypt_tool/         # Python 后端
│   ├── routers/                     # API
│   ├── voice_transcription.py       # Whisper 转写
│   ├── wechat_voice_transcript.py   # 官方转写提取（新增）
│   └── native/                      # 原生库
├── desktop/                         # Electron 桌面端
│   ├── src/                         # 主进程与后端管理
│   ├── scripts/                     # 打包/签名脚本
│   └── tests/                       # Node 测试
├── tests/                           # Python 测试
├── native/                          # wce_integrity Rust 源码
├── docs/                            # 文档
└── website/                         # 官网
```
