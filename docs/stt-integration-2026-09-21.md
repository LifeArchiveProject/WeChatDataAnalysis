# 语音识别升级接入说明

2026-09-22：软件仅提供 Zipformer CTC、Qwen3-ASR 0.6B CPU、Turbo、Qwen3-ASR 0.6B GPU 四个选项，默认选择 CTC。此次未生成或替换正式安装包。

## 软件中的入口

在设置的“语音识别模型”中下载、选择模型；聊天页的语音转写侧栏使用同一组选项。Tiny、Base、Small、Medium、Large v3 和 Qwen 1.7B 已从列表及下载入口移除。未安装的运行组件会显示原因，不能误选成可用模型。

| 档位 | 选项 | 运行设备 |
| --- | --- | --- |
| 低配极速 | Zipformer CTC INT8 | CPU；中英文、无标点 |
| 中配质量优先 | Qwen3-ASR 0.6B ONNX INT4 | CPU；建议 16 GB 内存 |
| GPU 速度优先 | 原 Whisper Turbo | NVIDIA GPU，保留原 CPU 回退逻辑 |
| GPU 质量优先 | Qwen3-ASR 0.6B | NVIDIA GPU，需单独的 Qwen GPU 运行组件 |

CPU/GPU 版本是独立选项。选中新模型会设置匹配的设备；环境变量锁定设备时不会覆盖。Qwen GPU 失败会给出错误，不会悄悄切换另一模型。新后端单进程串行复用，避免批量并发创建多份模型；取消时终止工作进程，下一条任务可以重新加载。空闲 120 秒后进程自动释放。

此前验收的四个新模型和 Turbo 的文件已安装到 `%APPDATA%/wechat-data-analysis-desktop/voice_models/`，新模型复制前已校验固定版本的 SHA-256。停用模型的文件及历史转写不会自动删除。旧 Whisper CPU 配置读取时转到 CTC，CUDA 配置转到 Turbo；Qwen 1.7B 转到 0.6B GPU。界面显示迁移提示，用户可重新选择。迁移不改写原设置，环境变量固定的设备不会被覆盖；若与模型冲突，界面会提示选择匹配设备。

## 启动及构建

项目普通开发启动会安装 CPU 语音依赖。前端需要 Node 20.19+ 或 22.12+；本机系统 Node 18 太旧，本次测试和构建使用已存在的 Codex Node 运行时。使用符合版本要求的 Node 后，要启用本机已验证的 Qwen GPU，在仓库根目录运行：

```powershell
npm --prefix desktop run dev:gpu
```

本机不更改系统 Node 也可以这样启动：

```powershell
$env:WECHAT_TOOL_QWEN_GPU = '1'
& "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe" desktop/scripts/dev.cjs
```

也可以手动安装：

```powershell
uv sync --extra voice-transcription
# 需要 Qwen GPU 时加上该扩展；Windows 锁定官方 PyTorch CUDA 12.8 索引。
uv sync --extra voice-transcription --extra voice-transcription-gpu
```

`desktop` 的 `build:backend` 构建 CPU 版本，包含 sherpa-onnx 和新模型资产清单，排除 PyTorch/Transformers；`build:backend:gpu` 额外收集 Qwen GPU 组件。默认 `dist:win` 仍走 CPU 后端构建，不应据此宣称普通安装包已包含 Qwen GPU。完整 GPU 安装包需要沿用项目正式签名和原生核心构建流程，使用 GPU 后端构建产物。

## 文件及缓存

- `resources/voice_models.json` 固定 Hugging Face 仓库、revision、必要文件、大小和 SHA-256；下载后先校验，再原子发布。
- `asr_models.py` 定义模型目录及能力；`asr_backends.py` 提供三种后端；`asr_worker.py` 隔离模型、内存、取消和 CUDA 探测。
- 新模型缓存键包含模型 ID、revision、后端和缓存版本；旧 Whisper 缓存键保持原样，切换不会误用另一模型的文本。
- 推理只读取本地权重和音频，工作进程启用 Hugging Face 离线模式。Zipformer 最长 15 秒、Qwen 最长 25 秒分段，优先在低能量位置切分。
- Qwen ONNX 按实际 tokenizer 编码角色提示，避免社区示例的固定 token ID 不匹配；CPU 特征提取不依赖 PyTorch。
- Windows Whisper CUDA 可以复用已安装 PyTorch 中的 CUDA 12 DLL，解决只有系统 CUDA 13 时的依赖缺失。

## 初次接入验收（历史数据，包含现已停用的 1.7B）

通过项目正式 `VoiceTranscriptionService.transcribe_voice` 读取并解码 20 条真实 SILK，四模型共 80 次成功；写缓存和批量缓存查询均验证通过。缓存写入测试目录，没有改写原会话的转写缓存。音频总长 202.54 秒。

| 模型 | 20 条总耗时，含加载、解码和缓存 | 与微信机器参考的字符差异率 |
| --- | ---: | ---: |
| Zipformer CTC | 6.202 秒 | 10.58% |
| Qwen 0.6B CPU | 65.125 秒 | 4.47% |
| Qwen 0.6B GPU | 51.954 秒 | 3.53% |
| Qwen 1.7B GPU | 47.384 秒 | 2.82% |

本表是单轮完整链路验收，与之前仅计推理的双轮基准计时不同，不能混算加速倍数。微信机器转写未经人工校对，差异率不是人工标注准确率；低配最低硬件、方言、噪声和长录音仍需更大语料验证。

回归结果：后端 132 通过、1 跳过；前端语音组件 63 通过；设置契约与桌面启动契约 28 通过；前端 Nuxt 生产静态构建成功。真实工作进程取消后约 81 毫秒完成回收，再次识别成功；Turbo 实际 CUDA 推理成功。NumPy 声学特征与上游 PyTorch 版本比较，最大绝对误差小于 0.0001。

界面机械检查仅发现原有进度条的 width 动画告警，没有新增告警。后续启动真实 Electron 开发应用完成桌面验收：设置中选择 Zipformer，聊天消息实际转写并显示结果；批量扫描可以启动和取消；Qwen 1.7B GPU 同样在聊天页转写成功，来源提示显示正确模型。修正了聊天来源提示残留的 Whisper 专属文案。

运行中的应用 HTTP API 对四个新模型各处理 3 条真实语音，并逐条验证缓存命中、模型 ID 与 CPU/GPU 设备。另将原有 20 条 SILK 复制到隔离测试账号，使用正式批量管理器完整转写：20/20 成功、失败 0，配置并发 4 时实际限制为 1；再次扫描 20/20 命中缓存。真实账号的全库扫描仅验证启动和取消，没有等待全部历史语音完成。正式安装包及其冻结工作进程尚未完成验收。

私人音频、参考文本、逐条输出和测试数据库保存在被 Git 忽略的 `tmp/stt-benchmark-20260921/` 与 `tmp/stt-integration-20260921/`；本文不包含会话内容。

## 独立 PR 基线复验

PR 基于上游 `main` 的 `2646cfdf`，只移入本次语音升级。上游尚无开发分支上的导出语音选项，因此没有带入相关导出界面和导出状态改动。

独立工作区后端相关用例为 131 通过、1 跳过、1 失败；唯一失败是 `test_export_option_is_wired_from_dialog_to_backend`，其要求的 `exportTranscribeVoice` 控件在上游不存在。已从未修改的 `origin/main` 提取该测试及其全部输入文件，独立复现相同断言失败；本 PR 不修改这项测试。语音组件 63 项、设置与桌面启动契约 28 项均通过。使用符合前端版本要求的 Node 重新安装锁定依赖后，Nuxt 生产静态构建成功，预渲染 34 个路由。

## 四模型收敛验收（2026-09-22）

移除旧模型折叠入口，模型卡片改为用途及配置说明，不再使用本机测试数据作为产品文案。新增旧设置迁移、停用模型选择及下载拒绝、四项模型目录一致性回归。

独立 PR 工作区后端 152 项通过，另有 14 项子测试通过；原有导出控件契约失败仍可复现。设置及桌面契约 28 项通过，语音组件 63 项通过，Nuxt 静态构建成功。启动实际 Electron 应用检查四项卡片与说明；四个保留模型各完成两条真实语音的应用 HTTP 转写，并逐条验证缓存，旧六项选择接口均返回 invalid_model。
