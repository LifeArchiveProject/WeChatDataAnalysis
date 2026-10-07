# AI 日志与上线排障

AI 总结、提醒、Agent、本地检索、前端请求和桌面通知的运行诊断写入现有应用日志。默认 INFO 只记录关键节点；逐页、逐段、逐批等正常细节降为 DEBUG，减少长期使用的日志体积。此策略只作用于 AI 诊断入口，不改变其他模块、根 logger 或文件 handler 的日志级别。

## 日志位置与格式

位置仍是当前 output 下的 `logs/YYYY/MM/DD/DD_wechat_tool.log`，可通过应用的“打开当前日志”打开。连续运行跨零点后，第一条记录切换至当天文件；打开日志时也会检查日期。切换 output 目录、删除后重建目录无需重启。没有新增大小限额、保留天数或自动清理。

```text
2026-09-09 10:00:00 | INFO | wechat_decrypt_tool.ai.diagnostics | [ai.model.call.finished] 模型调用：步骤结束；运行诊断 {"trace_id":"…","task_id":"…","call_id":"…","status":"success","duration_ms":1200,"usage_known":true}
```

关键业务步骤产生 `.started` 与 `.finished`；异常退出记录 `.failed` 或 `.interrupted`。`finished` 表示函数已经返回，应结合 `status` 与最终 `terminal` / `task.state` 判断业务结果，不能仅凭函数返回认定任务成功。下方事件清单同时包含 INFO 关键事件和 DEBUG 详细事件，不代表默认会全部写入文件。

默认记录范围：

- 保留任务创建、状态变化、执行结束、取消与恢复、配置修改、服务启停、每次模型请求开始和结束（含用量、耗时）、Agent 工具动作，以及通知显示/点击/ACK、SSE 断线与恢复。
- 保留所有显式 WARNING/ERROR、带异常或失败元数据的事件；详细步骤失败也不会被降级。重复后台故障沿用首次及每分钟汇总。
- 正常消息读取、附件页、分析段、推理批次、事务包装、缓存、规则未触发、预算逐次消耗、首个流式字符及正常页面导航只记 DEBUG。
- 索引已提交检查点、模型下载进度、GPU 下载进度按任务及本次执行分别限频，首次立即记录，之后每分钟最多一条 INFO；中间进度仍可在 DEBUG 查看。完成和异常不受此限频影响。

临时排查细节时可使用项目原有 DEBUG 配置。开启 DEBUG 后仍执行同样的脱敏规则，但详细日志会增多，排查后应恢复 INFO。没有自动清理机制，关键日志也会随任务数、模型调用数和使用天数累积，不保证固定总大小。

关联字段：

| 字段 | 用途 |
| --- | --- |
| `trace_id` | 串联请求、任务和后台处理；新任务保存到 SQLite，恢复沿用 |
| `operation_id` / `parent_operation_id` | 单个步骤及其调用关系 |
| `execution_id` | 每次实际执行生成新值；继续处理保持任务 ID，同时区分本次执行 |
| `task_id` / `run_id` / `thread_id` | 总结或索引任务、Agent 运行、对话 |
| `rule_id` / `profile_id` / `version` / `scope_revision` | 规则、配置、补充要求与授权范围版本 |
| `call_id` | 与 SQLite usage 记录 ID 相同；重试的每次请求分别记录 |
| `diagnostic_id` | 关联失败记录；HTTP 错误也在 `X-WCDA-AI-Diagnostic` 响应头提供 |

异步代码通过 ContextVar 传递关联信息，专用读取线程池显式复制上下文。下载和推理子进程仅通过 Pipe 传回元数据，由父进程写文件。旧记录没有关联字段时按未知处理，不补造历史用量。

## 功能与事件索引

下表事件均带 `ai.` 前缀；完整步骤的 started/finished/failed 后缀省略。

| 功能 | 主要事件与信息 |
| --- | --- |
| 配置、默认模型、连接测试 | `profile.saved/deleted/defaults.saved/connection.*`：变更字段名、模型、协议、版本和图片能力 |
| 模型列表 | `model.catalog`、`model.catalog.page.*`：分页结果数量、HTTP 状态及耗时 |
| 模型请求 | `model.call.started/acquired/first_token/finished/attempt_failed/validation/retry/compatibility`：排队、请求和首次输出耗时，每次用量、校验和失败分类 |
| 总结创建、固定读取范围 | `summary.task.created`、`summary.conversation.read.*`、`summary.graph_read`：任务 ID、开始/截止时间、范围模式、会话数量及读取结果 |
| 分段、合并、引用、总览 | `summary.segment.*`、`summary.merge.*`、`summary.graph_analyze/graph_overview`：分段数、层级、缓存复用、引用校验和失败会话 |
| 规则、提醒、取消和恢复 | `summary.run_rule`、`summary.rule.skipped`、`summary.retry.scheduled/requested`、`summary.pause_rule`、`summary.alert.matches`、`summary.cancel_task`、`summary.execution.resume`、`summary.task.state` |
| 检查点 | `summary.rule.checkpoint.committed`、`agent.analysis.checkpoint.committed`、`index.checkpoint.committed`：仅在对应事务成功返回后输出 |
| 图片与附件 | `media.resolve_media/enrich/located/cache/page.*/failed`：格式、大小、每页处理与缓存，缺失、加密、损坏、超限或缺少视觉模型等固定原因分类 |
| Agent 多轮、授权、工具 | `agent.submit/input.accepted/request.reused/scope.applied/input.superseded`、`agent.execute_tool`、`agent.tool.action/cache/data_source.failed`：请求去重、版本、范围、动作、返回数量与缓存 |
| 大范围分析 | `agent.context.*`、`agent.analysis.segment/coverage/checkpoint.*`、`agent.merge.segment.*`：背景压缩、每页读取、分段发现、合并、疑点核查与资料分页 |
| Agent 额度和终态 | `agent.budget.consumed/paused`、`agent.context.reduced`、`agent.run.terminal`、`agent.execution.failed`：消费计数、预算缩小、停止原因与保留资料数量 |
| 模型下载与离线导入 | `download.start/run/state/progress/file.*/retry/process.*/import.*`、`model.file.verify.*`：文件、固定版本、已有字节、重试等待、校验与加载测试 |
| GPU 组件 | `gpu.component.detected/file.*/package.install.*/install/failed`、`background.failure`：支持情况、组件文件校验、安装及检测失败 |
| 推理与 CPU 回退 | `inference.encode/process.*/batch.finished/cpu.fallback`：实际设备、运行库版本、批次大小、子进程 PID/退出码及回退原因 |
| 建立/恢复索引 | `search.build/resume/run`、`index.page.*/batch.*/commit/checkpoint.committed`：读取范围、动态批次、复用数量、推理和提交游标 |
| 智能搜索和分页 | `search.hybrid/recall.finished/ticket.hit/ticket.expired/keyword.fallback`：关键词/语义召回数、票据命中、设备及降级原因 |
| 存储、后台循环 | `storage.transaction.failed`、`index.transaction.rolled_back`、`background.failure/recovered`：错误类型、系统/SQLite 错误码、合并次数与持续时间 |
| 服务启停与恢复 | `lifecycle.*`、`runtime.component`、`storage.usage.recovered`、`agent.runs.recovered`、各服务 `start/stop/purge_account` |
| 前端请求和 SSE | `client.request.failed`、`client.sse.open/disconnected/recovered/invalid`、`client.response.stale` |
| 原文与通知导航 | `client.source.ready/failed`、`client.navigation.started/finished/failed` |
| 桌面通知 | `client.notification.requested/shown/failed/clicked/ack/ack_failed/duplicate/unsupported` |
| 上报链路 | `client.transport.dropped`；后端离线时桌面 `desktop-main.log` 中的 `[ai.diagnostic.undelivered]` |

关键步骤使用 INFO；兼容切换、可恢复失败和降级使用 WARNING；最终失败、存储异常和后台异常使用 ERROR。重复后台故障首次立即记录，之后每分钟汇总，恢复时补齐被合并次数。下载内部仍每 5 秒采集诊断进度，INFO 文件每分钟最多记录一次，阶段变化和文件完成立即记录。流式回答默认记录请求开始和结束，首次输出仅记 DEBUG，不逐字记录。SSE 心跳、无变化的轮询和组件渲染不记录。

## 如何排查

先取得任务/运行 ID 或接口响应头中的 trace/diagnostic ID，在当前及前一天日志中搜索。例如 PowerShell 安装了 rg 时：

```powershell
rg '任务或运行ID' 'D:\实际output目录\logs'
```

按问题定位：

1. **没有执行**：查 `task.created` / `input.accepted` / `search.build`、规则配置和 `background.failure`。需要追踪未触发原因时临时开启 DEBUG，查看 `rule.skipped` 的 `active_task`、`revision_changed`、`no_new_messages`、`below_threshold`。
2. **一直等待**：模型有 `call.started` 无 finished 表示尚未完成，完成记录中的 queue_ms/request_ms 可区分排队和请求耗时；实时区分两者需开启 DEBUG 查看 acquired。下载查看 retry 的等待秒数；索引查看最近一分钟的 checkpoint.committed 和任务终态。详细 page/batch/commit 仅在 DEBUG 下可见。
3. **回答失败**：从 `agent.run.terminal`、`summary.task.state` 或 `http.rejected/failed` 沿 trace 查 `call_id`。检查鉴权、限流、超时、无效 JSON、引用失败、上下文不足及兼容切换；`usage_known=false` 表示未知，不能按零费用理解。修复后继续，比较新旧 `execution_id` 与缓存事件。
4. **语义降级**：查 `search.keyword.fallback`。`scope_not_indexed` 表示索引未覆盖；`semantic_failed` 继续追踪 inference/process 错误。`inference.cpu.fallback` 表示当前批次改用 CPU；结合后续 checkpoint.committed 和 search.run.finished 的状态确认恢复结果，批次详情需开启 DEBUG。
5. **通知未出现**：先查后端 `summary.notify` 和通知事件，再按 task_id 查 requested → shown 或 failed/unsupported。ACK 只代表客户端已处理投递，**不能证明系统显示成功或用户已看到**；用户点击有单独 clicked。后端离线时看 desktop-main.log，导航失败再查 navigation/source 事件。
6. **恢复后看似重复处理**：任务 ID 应相同、执行 ID 不同。缓存事件不是新模型调用；检查点只有 committed 才算推进。回滚、部分附件失败和未完成分页会保留游标，恢复重读是预期行为。

## 内容边界和客户端入口

不记录密钥、正文、问题、检索词、提示词、模型回答、通知正文、Base64、签名下载地址、请求体或完整任务/timeline。异常仅保留类型、固定分类、HTTP/系统错误码和文件/函数/行号，不输出异常消息、源码行及局部变量。开启 DEBUG 同样受此限制；SDK 原始请求日志被过滤，AI 上下文中的旧模块自由文本也转换为安全诊断。

`POST /api/ai/diagnostics/events` 只接受本机请求、固定事件及白名单字段，每批最多 50 条、64 KiB，不接受任意日志文本。客户端按秒批量发送，队列最多 500 条，最多尝试 4 次；首次发送失败给桌面日志兜底，溢出明确计数。上报使用独立传输，不进入请求错误上报链，避免递归。

AI 普通请求使用 `X-WCDA-AI-Trace` 请求/响应头，保留 Agent 原有 request_id 的业务去重用途。浏览器原生 EventSource 无法设置自定义请求头，使用经过校验的 `ai_trace` 随机编号关联 SSE，服务端仍返回 trace 响应头。

Agent 进度使用单条长连接：事件写入 SQLite 后通过进程内条件变量立即唤醒订阅者，SQLite 同时保留 `Last-Event-ID` / `after` 断线重放能力；空闲连接每 15 秒发送一次注释心跳，不再按 100ms 查询事件表。前端首次进入时读取一次运行快照，连接正常后仅合并 SSE 增量和终态快照；只有自动重连、事件版本跳跃或 SSE 断线时才读取权威快照，断线期间启用有限的保底轮询。

## 验证与限制

新增回归覆盖并发上下文和线程池、恢复执行 ID、HTTP 本机限制/体积/白名单、INFO/DEBUG/SDK/异常栈的敏感哨兵、跨天并发写入、重复初始化、目录重建、output 切换、模型错误与重试、流式日志条数、索引回滚、前端队列/SSE、通知阶段和桌面离线兜底。

`tools/benchmark_ai_logging.py --messages 100000 --output tmp/ai-key-logging-benchmark.json` 沿用现有合成 SQLite 消息场景，比较日志关闭和开启。收敛前记录 576 条、168370 字节；当前 INFO 策略记录 1 条已提交检查点、371 字节，日志体积降低约 99.8%。本轮索引耗时不足一分钟，因此未触发第二次进度记录；更慢的任务会每分钟记录进度。这个基准直接调用读取和提交方法，不包含完整任务启停、网络模型请求、真实 GPU 推理和桌面通知，不能将 371 字节当成全部 AI 使用的体积上限。（该基准脚本已从仓库删除，可从 git 历史取回。）

本轮日志关闭/开启的读取及事务提交耗时为 44.323 → 33.482 秒，机器负载与缓存影响明显，不能将负增幅解释为日志带来加速或承诺固定开销。结果文件独立写到指定路径，不写入生产业务日志。新增回归还验证连续一千轮正常细节不写 INFO、异常仍可见、DEBUG 仍脱敏、进度按任务/执行限频，以及其他模块共享文件 handler 时 INFO/DEBUG 不受影响。

当前环境的联系人导出脱敏测试依赖未安装的原生 broker，属于既有环境阻塞；AI 日志测试不依赖此组件。真实断网、GPU 驱动崩溃和各操作系统通知中心显示仍应在对应发布机器上做最终联调。
