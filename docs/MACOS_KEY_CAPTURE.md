# macOS 登录期密钥捕获与恢复

仅处理使用者本人有权访问的本机微信数据。临时签名和调试可能触发微信或 macOS 的安全保护，不能保证零风险或所有版本都能成功。重要数据应先备份。

## 本次集成范围

本分支基于上游 main 合并捕获修复，不替换上游默认受控 helper，不修改其下载、完整性校验、签名策略或 Windows 流程。主界面的本机调试仍是用户明确同意后的实验性兜底；独立工具源码位于 `macos-key-extractor/`，与主程序复用同一组捕获/恢复模块。没有加入私人聊天页面、AI、媒体下载或存储配置。

## 捕获过程

1. 从用户选择的活动账号 `db_storage` 中读取消息库和会话库首页，进行同账号绑定。账号目录无需以 `wxid_` 开头；不以旧密钥缓存代替本次捕获。
2. 验证腾讯官方微信身份，建立本机 APFS 写时复制恢复副本和持久备份。事务记录版本、build、CDHash、临时签名身份及事务 ID；同用户、同安装路径跨进程互斥。
3. 临时调试签名后，先让用户完整登录并进入聊天页，预检实际已加载的捕获位置。预检失败时恢复，不要求继续退出账号。
4. 用户在未监测时退出账号，然后启动监测、完成管理员授权。只有本次事务和目标进程的就绪标记有效；显示“监测已就绪”后才重新登录。
5. LLDB 观察 `CCKeyDerivationPBKDF` 和经过模块 UUID/可执行地址验证的 PBKDF 导入桩，读取当前调用中的候选参数。参数形状用于诊断，数据库盐匹配及双库首页 HMAC 才是验真条件。模块 UUID 不匹配时不会套用其他版本偏移。
6. 256000 轮调用可能提供原始 passphrase；2 轮 HMAC 派生调用也可产生候选，但其中的 password 可能只是单库派生密钥。只有同时通过消息库及会话库校验的候选才可作为账号密钥；不能把一次 rounds=2 命中等同于成功。
7. 捕获后关闭本次临时微信，复核候选并恢复本次原版。核对恢复版本、build、CDHash，不将任意腾讯签名版本当成正确恢复；发现外部替换或更新时不覆盖，保留恢复资产并报错。
8. 主程序额外执行现有的完整实时数据库校验，再保存并返回明文密钥到本机输入框，保持现有操作习惯。独立工具也在账号校验及恢复通过后写入当前用户的 `~/.wcdb-key-tool/wechat-passphrase.json`（私有权限），支持用户主动复制。状态轮询、日志、URL 和公开仓库不包含密钥、数据库内容或本地恢复路径。

捕获后的计划关闭不等同于意外崩溃。页面持续显示捕获、复验、恢复阶段，仅在最终请求确认后显示完成；不能仅凭窗口消失或进度标记判断成功。

## 兼容与故障诊断

- 预检及捕获使用同一方案。macOS 27 优先软件 LLDB；原生失败只在确认清理安全时回退。用户取消授权不会触发另一轮自动授权。
- helper 被系统终止或无法确认调试状态清理时，不在同一目标进程继续切换方案，先结束事务恢复。
- 原生超时可记录当前系统及微信构建的方案偏好，下一次新事务改用 LLDB，不在已经错过登录时机后原地重复等待。
- LLDB 提前结束时回收输入保活与超时监护子进程，避免输出管道被计时器占用导致结果继续等满超时；真实超时保护保留。
- 记录有界参数形状计数、退出码/信号和阶段，不记录候选字节或盐值。未出现崩溃报告并不能证明是微信主动退出。
- 旧就绪/已捕获文件不能驱动新事务；捕获后的就绪标记不能再次提示登录。恢复失败保留错误与恢复资产，不误报成功。

## 独立工具的手动启动

独立工具调用 `prepare_capture` 时选择 `defer_launch=True`，主程序原有启动方式不变。

准备完成后停在 `awaiting_manual_launch`。用户点击“显示微信窗口”，必要时自行在系统设置确认单应用安全授权，再点击“我已手动打开，检查启动”。工具检查事务归属、应用身份及稳定 PID 后才允许预检。

“打开系统设置”只打开设置应用，不代点允许，不移除隔离属性，不关闭 SIP/Gatekeeper。恶意软件警告或没有允许入口时，应取消并恢复，不保证系统一定放行。单应用授权不是 Apple 公证。参考：[Apple 安全打开应用说明](https://support.apple.com/en-gb/102445)。

独立工具在等待用户操作时以单线程后台检查进程；启动退出或 PID 更换会触发已有恢复路径，同事务仅自动尝试一次。忙碌、关闭或陈旧检查结果不能启动重复恢复。

## 验证边界

2026-09-05，使用者反馈在其 Apple Silicon Mac 的微信 **4.1.7** 上，独立工具 1.1.11 完成密钥获取并正常恢复官方版本。这是用户实测反馈，不代表其他机器、4.1.12/4.1.13、所有 macOS 版本均已验证，也不将其他用户的报错全部标记为解决。

自动化回归使用合成数据库首页、伪 LLDB/进程和假 UI，不启动微信、不读取真实密钥。公开分支与上游接口对齐后另行执行回归。运行示例（Python 环境需安装项目依赖和 pytest）：

```bash
PYTHONPATH=src python -B -m pytest -q -p no:cacheprovider \
  tests/test_macos_capture_backend_routing.py tests/test_macos_capture_diagnostics.py \
  tests/test_macos_capture_validation.py tests/test_macos_restore_identity.py \
  tests/test_macos_lldb_breakpoint_plan.py tests/test_macos_capture_api_progress.py \
  tests/test_macos_inplace_capture.py tests/test_macos_clone_capture.py \
  tests/test_macos_db_key_capture.py tests/test_macos_platform_support.py \
  tests/test_standalone_macos_key_extractor.py tests/test_macos_native_capture_source.py \
  tests/test_macos_capture_phases.py tests/test_macos_lldb_command_lifecycle.py \
  tests/test_macos_prepared_lifecycle.py tests/test_macos_manual_launch.py \
  -k 'not private_snapshot_replaces_external_xwechat_symlink and not force_clone_preserves_nested_symlink_without_following_it'
node --test tests/macos-capture-progress.test.mjs
git diff --check
```

上述两项 APFS 实盘克隆测试因沙盒环境排除，不计作通过。模拟测试不能替代其他版本的真实登录验证。发布源码不包含构建机器的证书、偏好设置、日志、数据库、密钥或安装产物。

## 实现索引

- `macos_db_key_capture.py`：启动/退出、LLDB 命令生命周期及签名恢复。
- `macos_clone_capture.py`：断点计划、预检、候选及退出诊断。
- `macos_inplace_capture.py`：安装事务、方案选择、阶段状态与原样恢复。
- `macos_capture_validation.py`：只读双库首页快照及候选验真。
- `macos_native_capture.py`、`native/macos/source/wcdb_native_capture.c`：原生调度、清理及非敏感阶段标记。
- `routers/keys.py`：保持上游本机访问限制、并发控制、独立线程及结果校验。
- `frontend/lib/macos-capture-progress.js`、`frontend/pages/decrypt.vue`：事务绑定的持续进度和登录指引。
- `macos-key-extractor/`：复用上述模块的可选独立工具及构建/隐私审计脚本。
