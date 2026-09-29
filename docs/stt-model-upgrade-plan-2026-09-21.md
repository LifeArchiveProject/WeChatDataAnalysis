# 本地语音转文字模型升级方案

日期：2026-09-21。状态：已接入四个新模型及模型管理界面，完成本机真实 SILK 的正式服务验收；用户原有模型选择未自动更改。落地方式与验收范围见 [接入说明](stt-integration-2026-09-21.md)，选型实测证据见 [本机测试报告](stt-benchmark-2026-09-21.md)。20 条机器参考样本不能代替发布前的人工准确率验收。下文的硬件自动推荐和更广语料验收属于后续目标，首版提供手动选型。

## 目标与结论

面向微信短语音，提供低配 CPU、主流 CPU、NVIDIA GPU 三档能力。新增 Zipformer 和 Qwen3-ASR，同时保留实测表现突出的 Whisper Turbo；用户已选模型不自动更换。

初版“所有档位换新”的方案经实测后调整：低配主推 Zipformer CTC，主流 CPU 增加 Qwen ONNX，GPU 将速度优先和质量优先分开。Transducer 在本次样本上比 CTC 更慢、与微信转写的差异更多，暂不单列为更高档。Qwen 0.6B 的 CPU/GPU 版本属于不同运行配置。

已确认的本机取舍：CTC 约 2.74 秒处理 202.54 秒语音；Qwen CPU 约 61.59 秒，比 Medium CPU 快约 2.66 倍，但峰值进程内存约 3.65 GiB；GPU Turbo 约 7.87 秒，Qwen 0.6B 约 38.57 秒，因此 Qwen 不能直接接替 Turbo 的极速定位。差异率只代表与微信机器转写的一致程度。

所有硬件建议都是待验收目标，不是已验证的最低配置。权重文件大小不等于运行内存，量化位数也不代表整条推理链都采用该精度。

## 模型与原有档位对应

| 新选项 | 对应旧选项 | 模型来源与版本 | 运行方式 | 已核实的主要文件大小 | 验收目标设备 |
| --- | --- | --- | --- | --- | --- |
| 低配极速 | Tiny、Base 的优先新候选；Small 保留兼容 | pkufool/zipformer-small，CTC INT8 | CPU，sherpa-onnx，必须增加分段 | ctc.int8.onnx 约 28.7 MB，另加词表 | 4–8 GB 内存、低功耗/老款 CPU 仍需另测 |
| CPU 质量优先 | Medium 的新候选 | andrewleech/qwen3-asr-0.6b-onnx，INT4 变体 | CPU，ONNX Runtime | 指定推理文件合计约 2.03 GB | 优先 16 GB 内存；本机进程峰值约 3.65 GiB |
| GPU 极速 | Turbo 保留 | faster-whisper-large-v3-turbo | CUDA，CTranslate2 FP16 | model.bin 约 1.62 GB，另加配置和词表 | 本机 12 GB 显存已测；更低显存仍需测 |
| GPU 质量优先 | 新增选项 | Qwen/Qwen3-ASR-0.6B-hf | CUDA，PyTorch / Transformers BF16 | model.safetensors 约 1.56 GB，另加配置和词表 | 本机分配显存峰值约 1.67 GiB；不是系统最低配置保证 |
| GPU 质量优先大模型 | Large v3 的新候选 | Qwen/Qwen3-ASR-1.7B-hf | CUDA，PyTorch / Transformers BF16 | model.safetensors 约 4.08 GB，另加配置和词表 | 本机分配显存峰值约 4.01 GiB，预留显存另算 |

大小按十进制 MB/GB 表示，只包含所列权重及文件；不包含推理运行库。CPU 两档不应依赖 PyTorch 或 CUDA。Qwen GPU 档精度依据设备能力验证 BF16/FP16，不能沿用 CTranslate2 的 compute_type 逻辑。Zipformer Transducer 保留研究记录，不作为首批必上的独立档位。

### 选型依据和边界

- [Zipformer Small 模型卡](https://huggingface.co/pkufool/zipformer-small)提供中英文 CTC 和 Transducer 两种解码头；[文件列表](https://huggingface.co/pkufool/zipformer-small/tree/main)包含 INT8 文件。模型卡上 Transducer 在列出的测试集上比 CTC 更准确，但没有证明其在本项目中一定快于 Whisper。CTC 作为最低资源档、Transducer 作为均衡档，是待实测的工程选型。
- 该 Zipformer 仓库建立于 2026-06-25，属于近期发布的模型资产；Zipformer 架构本身来自 2023 年，不能宣称是 2026 年新发明的架构。供应方[部署说明](https://pkufool.github.io/zipformer/en/deployment/)推荐 sherpa-onnx，但必须验证这里的具体导出文件和所锁定版本相容。
- [Qwen 0.6B ONNX](https://huggingface.co/andrewleech/qwen3-asr-0.6b-onnx)是社区导出；INT4 主要用于解码器，编码器仍为 FP32。选用它是为了评估 CPU 上的资源与精度折中，不能将其他导出版本的性能数据直接套用。
- [Qwen 0.6B HF](https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf)和[1.7B HF](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf)是官方 Transformers 原生版本；Qwen3-ASR 属于 2026 年模型系列，HF 原生仓库于 2026 年 6 月建立。模型卡要求 Transformers >= 5.13.0。
- Zipformer 低配档先按中英文能力展示；不能承诺 Qwen 同等的方言、多语言和热词能力。低配档标点需要单独评估，首版允许提供无标点文本，不能为了补标点默认加载大型语言模型。
- 不将 SenseVoiceSmall 或 BELLE 作为本次“新模型”主线：它们仍可用作评测对照，但原始模型属于 2024 年。Fun-ASR-Nano、FireRedASR2 作为后续中文专项候选，首版避免引入更多推理框架。

## 默认推荐规则

1. 新安装首次打开模型设置时，根据可用内存、CPU、GPU 能力推荐一个档位，用户点击下载后才下载资产。机器总内存不能单独决定推荐结果。
2. 低配优先验证“低配极速”CTC。首版不把 Qwen 作为所有机器统一默认，也不按模型文件体积推算运行内存。
3. 16 GB CPU 机器提供“CPU 质量优先”，展示本机测试环境、耗时和内存；不能把 5600X 的速度直接套用到低功耗 CPU。
4. GPU 可用时保留 Turbo 极速路径；Qwen 作为质量优先的可选路径，说明其标准 Transformers 运行方式在本机更慢。显存不足时减小并发、分段或提示切换已安装的较小模型。
5. Qwen 0.6B 的 CPU/GPU 版本在界面中说明为同系列不同运行方式。模型卡不使用“最高准确率”等未经项目评测支持的绝对标签。

## 项目改造范围

当前 voice_transcription.py 将目录校验、WhisperModel 加载、transcribe 参数和 CPU 回退都绑定到 faster-whisper；模型列表有 Tiny、Base、Small、Medium、Large v3、Turbo 六项。pyproject.toml 已包含 onnxruntime 和 tokenizers，但没有 Qwen 所需的 PyTorch / Transformers。

### 一、推理接口

提取独立 ASR 后端接口：load、transcribe、unload、capabilities。统一输出文本、时长、检测语言（允许未知）、实际模型标识、后端版本、实际设备和耗时。

- 保留 WhisperBackend 处理旧模型。
- 增加 ZipformerBackend：CTC 和 Transducer 共用模型管理，分别使用正确的特征提取及解码器。
- 增加 QwenOnnxBackend：处理音频特征、提示词、KV cache、逐步解码和取消；不能只调用 ONNX 文件一次就当作完整识别。
- 增加 QwenTransformersBackend：按官方 HF 接口加载 0.6B / 1.7B，关闭训练行为，规范输出中的语言标记和文本。

微信 SILK 解码、任务排队、进度、转写缓存及前端结果展示继续复用。音频统一到后端要求的单声道 16 kHz 格式，各后端的特征提取不可混用。

### 二、模型资产与配置

将固定 Whisper 文件白名单改为逐模型清单，字段至少包括 modelId、backend、repoId、revision、files、文件哈希、量化方式、支持设备和语言。

建议新 ID：zipformer-small-ctc-int8、zipformer-small-rnnt-int8、qwen3-asr-06b-onnx-int4、qwen3-asr-06b-hf、qwen3-asr-17b-hf。

- 精确下载指定变体所需文件，禁止整仓下载不同精度和训练检查点。
- 下载完成校验后再原子发布目录，继续支持取消、重试、删除和占用保护。
- 新增通用 ASR 配置；兼容旧 WECHAT_TOOL_WHISPER_* 环境变量，旧变量仍指向旧后端，不暗中重解释。
- 模型 ID、版本和量化变体参与缓存身份；不能把原来的 medium ID 指向 Qwen 后继续读取 Whisper 结果。
- 旧缓存和模型不删除。已安装旧模型可在“旧版模型”区域查看、使用和主动移除。

### 三、低配运行与 GPU 依赖

- CPU 默认一次只识别一条，线程数从 2 开始按设备调整，避免与任务并发相乘造成过载。
- 采用独立推理进程，任务间复用模型；空闲后卸载，取消或异常时可终止工作进程释放内存。
- 音频分段并限制输出长度，测试静音、尾音、重复输出和跨段文字拼接。
- GPU 推理依赖按需安装或作为独立运行包发布；普通 CPU 安装包不强制包含 PyTorch/CUDA。
- 当前 CTranslate2 的 CUDA 探测不能证明 PyTorch CUDA 可用；各后端分别探测。
- GPU 故障不能直接沿用当前“同模型 CPU int8”回退逻辑。只在事先允许且模型已安装时切换明确的 CPU 档，并显示实际使用模型；否则提供可操作错误，不自动下载另一个大模型。
- Windows 为第一验收平台；macOS/Linux 的轮子、算子兼容和打包分别验证。项目 macOS ONNX Runtime 版本不同，不能按 Windows 测试结果宣称全平台可用。

## 实施顺序与验收

### 第一步：最小评测，确定名单

独立评测入口已实现为 `tools/benchmark_stt_local.py`，在固定版本上进行 20 条真实语音初筛。具体结果及限制见测试报告；以下更大规模人工评测仍是发布前的下一阶段。

测试集至少覆盖 100 条、3–60 秒的短语音：普通话、带口音普通话、中英混合、方言、嘈杂、近静音、人名数字和语速较快的内容。公共样本可先跑；微信样本在明确选定范围后本地处理。

记录中文 CER、英文 WER、人名/数字错误、无语音误识别、冷启动、热启动 p50/p95 延迟、峰值进程树内存、显存、取消耗时和长批次内存增长。标点单独评价。资源分档不等于质量严格单调，跨模型质量必须由同一套数据确认。

建议发布门槛：低配档在目标机与现有相应档比较不明显降低准确率，同时降低占用或耗时；Qwen 中高档在主要中文场景体现可量化收益。达不到条件的候选不作为新默认。4 GB 极低配必须单独测试，不能以 8 GB 结果代替。

### 第二步：上线低配 CPU 档

完成后端接口、Zipformer CTC、模型下载管理和原有设置兼容。修复较长输入的分段问题，再覆盖低配基本需求；Transducer 暂不作为首版必需项。

### 第三步：上线 Qwen CPU/GPU

验证 Qwen ONNX INT4 中文量化退化、Windows 算子兼容和实际内存；再加入官方 HF 0.6B/1.7B GPU 档及可选运行包。若社区 ONNX 版本不通过，保留 Zipformer 默认，不发布未经验证的 CPU Qwen。

### 第四步：迁移展示与发布

设置页按实测价值展示配置、实际模型名、下载大小、语言和建议设备。Turbo 保留在主要选项中；其他原模型保留兼容入口。已选模型继续生效，升级仅提示可选的新档位，避免为了凑齐档位强行增加模型。

必要回归：完全离线、损坏/中断下载、模型删除与正在推理冲突、取消、切换模型、缓存隔离、GPU 不可用/显存不足、旧配置启动、桌面打包启动。验收完成后才把“候选”改为“正式推荐”。

## 调研版本记录

以下为本次核查到的 HF revision，仅供实施评测锁定与复现；发布前需要按验收版本生成完整文件清单与哈希。

| 仓库 | revision |
| --- | --- |
| pkufool/zipformer-small | e1764e4e54504721900d1e6b99c746e7331980af |
| andrewleech/qwen3-asr-0.6b-onnx | 4fc24a1402e74db89c4d2ef256875e71680128c4 |
| Qwen/Qwen3-ASR-0.6B-hf | 7f1569a48a89f3e3f4dc3a5c9d28bddd903bc76c |
| Qwen/Qwen3-ASR-1.7B-hf | bcd2b5b7f32b480ab5790554cfa8347f246a14f3 |
