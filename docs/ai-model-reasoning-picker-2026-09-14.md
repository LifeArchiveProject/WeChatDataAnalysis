# 模型与思考强度单入口

输入框底部显示「模型 · 强度」。点击后打开绿色滑杆浮层；点击浮层中间的强度和模型名，在同一浮层进入模型列表，选好模型后返回滑杆。没有额外的标签切换栏。按后续反馈，浮层缩至约 240×89px、去掉闪电图标，定位到模型入口上方并覆盖输入框。保留服务分组、上游列表获取、手动模型 ID 与原有全局选择记忆。

## 能力与参数

- 读取 models.dev 的 `reasoning_options`，按服务、接口地址和精确模型 ID 匹配，保留该模型声明的档位顺序，不生成通用的五档。原生 SDK 供应商缺少 `api` 时使用官方入口匹配；同主机的 Coding Plan 采用最长接口路径匹配。
- 档位型显示离散滑杆；开关型显示关闭/开启；只有预算型时显示原生 Token 预算范围，受当前输出容量限制。只有 `reasoning=true` 或未知能力时显示说明，不展示假的滑杆。
- 模型配置中的手动等级优先；未知代理不直接继承同名官方模型的请求参数。已从代理上游获取的能力仍可使用。
- OpenAI 兼容的等级使用 `reasoning_effort`；Claude 使用 `output_config.effort` 或预算形式的 `thinking`；DeepSeek、MiMo、Kimi、智谱、火山使用 `thinking.type`；百炼、硅基流动使用 `enable_thinking` / `thinking_budget`；OpenRouter 使用 `reasoning`；Gemini 预算通过兼容 API 的 `extra_body.google.thinking_config` 传递。
- 切换模型会清除旧模型的显式强度参数。恢复默认会删除等级、开关和预算覆盖，不把默认伪装成中档。正在执行的任务使用原快照，新一轮采纳新选择。
- 获取上游列表后重新解析当前模型能力，避免早先的空缓存遮住后来补齐的档位。

## 接口

新增只读 `GET /api/ai/profiles/{id}/model-capabilities?model_id=...`，返回合并目录、上游、手动覆盖后的能力，不包含密钥。`selected-model` 与轮次输入增加可空的 `thinking_mode`、`thinking_budget`，继续兼容原 `reasoning_effort`。默认选项保留原响应结构。没有数据库迁移。

## 验证

前端累计 326 项 Vitest 回归通过；后端相关 92 项通过（最终新增的火山参数用例包含在其中）。覆盖 SDK 构造出的请求体、非法/冲突参数拦截、配置覆盖、原生供应商无 api 字段、代理与 Coding Plan 隔离、保存重启、运行中补充与下一轮快照；没有调用付费模型。

浏览器使用真实组件检查浅色/深色、440/320px 侧栏、360px 窗口，以及模型列表、滑杆键盘操作、默认恢复、焦点和菜单关闭。

重启前确认运行中/排队任务为 0。项目启动器 PID 38760；前端 3000、后端 10392 的健康检查均为 200，启动错误日志为空。真实已配置模型返回：deepseek-flash 为关闭与 low/high/max；mimo-v2.5 为开关。只读检查能力，不自动执行用户问题。

## 参考

- [models.dev 数据目录](https://models.dev/api.json)
- [models.dev 能力结构](https://github.com/anomalyco/models.dev#3a-reuse-model-metadata-with-base_model)
- [Claude effort](https://platform.claude.com/docs/en/build-with-claude/effort)、[扩展思考](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
- [DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)
- [Gemini OpenAI 兼容 API](https://ai.google.dev/gemini-api/docs/openai)
- [OpenRouter 推理参数](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [百炼思考参数](https://www.alibabacloud.com/help/en/model-studio/deep-thinking)
- [智谱思考参数](https://docs.bigmodel.cn/cn/guide/capabilities/thinking)
- [硅基流动推理参数](https://docs.siliconflow.cn/docs/userguide/capabilities/reasoning)
- [火山官方 Go SDK 请求类型](https://pkg.go.dev/github.com/volcengine/ark-runtime-go/arkruntime/model/chat)
