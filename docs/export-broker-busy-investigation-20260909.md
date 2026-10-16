# 导出完成后 native broker BUSY：定位与复现

## 结论

导出在写完消息后生成完整性签名，调用 `seal_export_manifest()`。原实现要求
`managed_native_core_operation(export_only=True)`，会将已运行的数据库 broker
停掉并切换为仅导出模式。只要另一个线程还有数据库查询等 native 操作，
`ensure_native_core_broker()` 就会抛出 BUSY，整个导出因此失败。

这是进程模式切换与并发操作的兼容性问题。失败发生在真正调用 native 签名接口之前，
与导出的附件内容无关；关闭媒体导出也不能解决。

## 日志证据

输入：用户提供的 `08_wechat_tool.log`。该文件追加了多个启动周期，不能只根据首行版本归因。

| 日志行 | 时间（2026-09-08） | 事实 |
| --- | --- | --- |
| 5 | 13:55:57 | 启动版本为 2.3.0 |
| 29 | 13:59:51 | 随后启动版本为 2.4.0 |
| 840 | 14:07:16 | 87 条消息、2 个媒体写完后 BUSY，与截图对应 |
| 941 | 14:09:59 | 只导出文本、关闭媒体后仍然 BUSY |
| 1431 | 14:12:15 | 再次导出失败，同一错误 |
| 1467 | 14:14:22 | 重新启动 2.4.0 |
| 1989 | 14:16:13 | 重启后 105 条消息、4 个媒体写完，再次 BUSY |

四次异常均为 `BUSY with 1 active operation(s); cannot switch to export-only mode.`。
调用链为：`ChatExportManager._run_job` → `write_zip_integrity_sidecars` →
`seal_entries` → `seal_export_manifest` → `managed_native_core_operation` →
`ensure_native_core_broker`。

界面 100% 对应会话处理已经完成；完整性签名和最终发布仍在后面执行，所以会出现
“100% 后失败”。该问题不需要旧进程残留即可触发，重启不会改变这一调用关系。

## 版本差异与回退解释

上游发版顺序为 [2.2.1](https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/tag/v2.2.1)
→ [2.3.0](https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/tag/v2.3.0)
→ [2.4.0](https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/tag/v2.4.0)。
日志能确认失败发生在 2.4.0；用户实际回退的版本尚未直接确认。

比较这些标签，`native_core_broker.py`、`native_core_export.py`、`export_integrity.py`
的相关逻辑没有变化，但 2.4.0 新增了两项关键改动：

- `ccf73c4`：增加实时消息 SSE 接口。全账号模式每轮调用 native 会话查询，结束后只等待 5 毫秒。
- `72a5d35`：前端从 `/chat/realtime/stream` 改连
  `/chat/realtime/messages?...&interval_ms=5`，并固定使用全账号范围。

对应代码为 `frontend/stores/chatRealtime.js` 的 `openStream()`，以及
`routers/chat_realtime_sse.py` 的轮询循环。查询通过 `native_core_realtime._query_once()`
持有数据库操作租约。这里的 5 毫秒是每轮完成后的等待时间，并非查询固定每秒执行 200 次。

**代码支持的推断：** 新的高频查询显著增加签名与数据库操作重叠的机会，放大了既有缺陷。
重启后恢复实时连接会再次触发；回退 2.3.0 则恢复旧的实时更新方式。这与用户反馈相符。
现有日志只记录活跃操作数量，没有记录具体持有者或 SSE 连接状态，因此尚不能把四次失败
全部断言为该轮询线程所致，也不能据此声称 2.3.0 在其他并发场景下绝不会失败。

## 复现与修复

回归测试：`tests/test_native_core_export_integration.py::test_zip_seal_reuses_database_broker`。
它使用独立后台线程持有真实 Python broker 租约，通过事件固定并发时序；主线程写入
87 条测试消息后走真实 ZIP 完整性调用链。进程对象和 wechatdb 签名、加密接口使用测试替身。

修改前，持有一个数据库租约的场景在同一行抛出与用户完全相同的 BUSY。
修改后，忙碌和空闲数据库模式均可完成 ZIP 签名、导出加密；签名异常也不会泄漏租约。
另有解密回归覆盖后台数据库操作仍在执行时的成功与 native 异常两条路径，
确认失败不发布结果、临时文件被清理、源文件保留且不误释放数据库租约。

修复在 `managed_native_core_operation()` 增加 `prefer_export_only`：

- 已有存活 broker 时复用其模式，不为签名、加密、解密强制重启。
- 无存活 broker 时仍启动仅导出模式，不要求存在数据库目录。
- 模式选择与租约获取共用锁；严格 `export_only=True` 的原有检查保留。
- 原有 native 签名及授权校验保留，不跳过签名或吞掉错误。

验证命令（仓库根目录下，`--basetemp` 应选择新的测试目录）：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_native_core_broker_lifecycle.py tests/test_native_core_export_integration.py tests/test_chat_export_cancel_responsiveness.py tests/test_native_core_voice_asr.py tests/test_native_core_realtime.py -q --basetemp tmp/pytest-export-busy-check
```

结果：85 passed，4 subtests passed。

再次复核时，将 Git HEAD 中未修改的两个业务文件加载到独立临时目录，运行同一组
“后台数据库占用时签名 / 解密”用例：两个用例均在原模式切换检查处抛出与用户一致的 BUSY。
加载当前修复后，这两个用例通过，完整相关测试集再次得到 85 passed、4 subtests passed。
对照过程没有回退或覆盖工作区源码。

本机没有 `wechatdb_broker.exe`，额外运行 `tests/test_export_integrity.py` 时，
5 项依赖真实 native 签名的用例因组件缺失失败。当前完成的是代码调用链和确定性并发复现，
尚未完成用户数据库、发布版 native 组件和桌面界面的端到端复测。发布前应使用正式组件，
开启实时消息后重复验证 TXT/HTML ZIP 导出、签名有效性及导出后的实时读取。
