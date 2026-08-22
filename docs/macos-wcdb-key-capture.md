# macOS Apple Silicon WCDB 密钥捕获（Draft）

> 仅用于处理当前用户本人拥有或已获明确授权的本机微信数据。本流程需要用户亲自在手机端确认登录；不会绕过登录、联网传输密钥或长期注入微信进程。

## 本 Draft 的边界

本次提交只增加可审查的 Python 后端状态机、数据库验真、恢复逻辑、测试和发布审计脚本。它暂不替换现有的 macOS 受限原生 helper，也不把 LLDB 路径接成默认 UI 流程。维护者确认接口和恢复边界后，再单独提交 API/UI 接线，避免一次 PR 同时改变两套获取方式。

核心文件：

- `macos_db_key_capture.py`：腾讯签名识别、备份、临时签名、LLDB 调用、密钥格式及数据库验真；
- `macos_clone_capture.py`：APFS 写时复制隔离方案、断点预检、salt 匹配和兼容 UUID 表；
- `macos_inplace_capture.py`：可恢复的原路径临时重签事务和重启恢复；
- `macos_db_key_discovery.py`：只接受能通过所选数据库首页 HMAC 校验的本地候选。

## 安全状态机

1. 规范化并锁定明确的 `/Applications/WeChat.app`，验证 bundle identifier、腾讯 Team ID、深度签名和版本。
2. 读取所选账号的加密数据库首页；拒绝明文 SQLite、短文件和不可读文件。
3. 在任何改动前创建并验证官方微信恢复归档，再将本机恢复状态以 `0600` 原子写入磁盘。
4. 只对一次捕获所需的临时实例进行调试签名。先登录进入聊天页，再短暂附加做断点预检并立即分离。
5. 用户在未监测状态退出账号；正式监测开始后重新登录同一账号。
6. 通用路径只接受两种经过验证的 WCDB 参数形状：`rounds=256000` 时 salt 必须等于目标数据库 salt；`rounds=2` 时 salt 必须等于目标数据库 salt 逐字节异或 `0x3A` 后的 HMAC salt。其他轮数一律拒绝。已知版本还可使用按模块 UUID 明确登记的内部返回点，未知 UUID 不猜偏移。
7. 32 字节候选必须通过目标数据库首页 HMAC 校验才会保存，缓存目录和文件分别使用 `0700`、`0600`。
8. LLDB 在 `process continue` 返回后记录隔离微信的 PID、进程状态、退出码和不超过 240 字符的退出原因；副本提前退出时立即返回专用诊断，不继续等待为普通超时。
9. 成功、取消、超时或异常都进入同一恢复路径；恢复后再次执行腾讯签名和版本校验，最后才删除恢复状态。

## 源码复现

前提：Apple Silicon Mac、Xcode Command Line Tools、腾讯官方签名微信，以及运行 Python/桌面应用的完全磁盘访问权限。下面的路径均为示例，不能直接复制真实密钥、账号名或聊天数据库到 Issue/PR。

先运行不接触真实微信的回归测试：

```bash
python -m pytest -q \
  tests/test_macos_db_key_capture.py \
  tests/test_macos_clone_capture.py \
  tests/test_macos_inplace_capture.py \
  tests/test_macos_db_key_discovery.py \
  tests/test_macos_key_capture_release_audit.py
```

真实端到端验证采用显式的三阶段调用，便于 UI 在每一步向用户确认：

```python
from pathlib import Path

from wechat_decrypt_tool.macos_db_key_capture import (
    capture_prepared_macos_passphrase,
    cleanup_macos_passphrase_capture,
    prepare_macos_passphrase_capture,
    preflight_prepared_macos_passphrase,
)

wechat = Path("/Applications/WeChat.app")
backup_root = Path("/path/to/private/recovery-directory")
probe_db = Path("/path/to/active/app_data/xwechat_files/account/db_storage/message/message_0.db")

try:
    prepare_macos_passphrase_capture(wechat, backup_root=backup_root)
    # 用户登录临时微信并进入聊天页后：
    preflight_prepared_macos_passphrase(wechat, backup_root=backup_root)
    # 用户先退出账号；监测开始后再重新登录同一账号：
    result = capture_prepared_macos_passphrase(
        wechat,
        backup_root=backup_root,
        probe_db_path=probe_db,
    )
    assert result["official_wechat_verified"] is True
finally:
    # 可以重复调用；显式取消和异常退出也使用此恢复入口。
    cleanup_macos_passphrase_capture(wechat, backup_root=backup_root)
```

结束后必须验证官方微信：

```bash
codesign --verify --deep --strict --verbose=2 /Applications/WeChat.app
codesign -dv --verbose=4 /Applications/WeChat.app 2>&1 \
  | grep -E '^(Identifier|TeamIdentifier|Authority)='
```

期望结果包含 `Identifier=com.tencent.xinWeChat`、`TeamIdentifier=5A4RE8SF68`，且深度签名验证成功。

## 发布审计

对解压后的 `.app` 和最终 `.zip` 都运行：

```bash
python tools/audit_macos_key_capture_release.py \
  /path/to/WeChatDataAnalysis.app \
  /path/to/WeChatDataAnalysis-mac-arm64.zip
```

审计会拒绝数据库、日志、偏好、密钥缓存、`.env`、构建者主目录绝对路径及当前构建用户名。证书与私钥不属于源码或运行时资源，也不得加入安装包。

## 当前兼容性

- 已验证：Apple Silicon、微信 4.1.12（build 269341）、活动 `Documents/app_data/xwechat_files` 数据库；
- 社区实测反馈：微信 4.1.13（build 269578）出现 `rounds=2` 的页 HMAC 子密钥派生调用，其 32 字节 password 可作为数据库主密钥候选；本实现仅在 HMAC salt 精确对应目标库且候选通过该库首页 HMAC 时接受；
- 同一社区环境报告隔离副本在手机确认登录后静默退出。当前修复增加退出状态诊断，但尚未在该机器上证明副本登录问题已经消失；
- 未验证：Intel Mac、微信 4.1.13 build 269578 的完整 clone 成功路径、未来微信版本、多套并行安装；
- 已知内部返回点仅按 Mach-O UUID 精确启用；版本未知时只保留系统 PBKDF2 路径并返回明确诊断；
- 断点预检不通过时流程必须停止，不能要求用户继续退出账号。
