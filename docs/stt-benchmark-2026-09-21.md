# 本机 STT 模型对照测试（2026-09-21）

已完成 12 个运行配置。样本为项目已有的 20 条真实微信语音，共 202.54 秒、5 个会话。

## 对升级方案的修订

- **低配：优先 Zipformer CTC INT8。** 本批语音约 2.74 秒，Tiny 约 22.17 秒，快约 8.1 倍；与微信转写的差异率从 26.44% 降至 10.22%。CTC 进程峰值约 390 MiB，比 Tiny 的 279 MiB 高，不能宣称内存也更省。
- **主流 CPU：Qwen3-ASR 0.6B ONNX INT4 值得接入。** 约 61.59 秒，相比 Medium CPU 的 163.63 秒快约 2.66 倍，差异率从 8.11% 降至 4.35%；代价是进程峰值从约 1.63 GiB 增至 3.65 GiB。建议先面向 16 GB 内存设备，4 GB 老电脑不以它作为默认。
- **GPU：保留 Turbo 极速选项，增加 Qwen 质量优先选项。** Qwen 0.6B 为 38.57 秒、差异率 3.64%；1.7B 为 44.16 秒、2.94%；Turbo 为 7.87 秒、6.82%；原 Large v3 为 20.51 秒、6.93%。标准 Transformers 路径没有带来 GPU 提速，1.7B 是本批样本与参考最接近的配置，但耗时约为 Large v3 的 2.15 倍。
- **不单列 Transducer 均衡档。** 本批结果 3.61 秒、差异率 11.16%，没有体现相对 CTC 的价值。20 条样本不足以判定它在其他数据上一定较差。
- 这些结果足以调整工程接入顺序，不能证明真实准确率已经提升。下一步需要听原音校对参考，以及在真实低配设备上验收；当前只有本机 CPU 路径测试。

## 方法与适用边界

- 本机：Windows、Ryzen 5 5600X（6 核 12 线程）、32 GB 内存、RTX 4070 SUPER 12 GB，驱动 596.49。
- 从 828 条已有微信转写的候选中，以固定种子 20260921 抽取。按 0.8–3、3–8、8–20、20–60 秒各选五条；实际最长时长见本地清单。仅有转写的语音会入选，存在选择偏差。
- 统一解码为 16 kHz 单声道，所有模型使用完全相同的 WAV；音频和文本未发送到外部 ASR 服务。
- 每模型独立进程、CPU 4 线程、单条串行，预热一条后随机顺序运行两轮。耗时是两轮热运行均值，包含特征提取和识别，不含 SILK 解码、下载、模型加载及应用界面开销。
- 指定推理引擎使用 4 个 CPU 线程；这不等同于模拟低端 CPU，也不保证第三方库与整台电脑总共只有 4 个线程。部分测试期间后台仍在下载权重，速度作为本机初筛结果。
- 原 Whisper 参数沿用项目：中文、beam_size=5、vad_filter=True、condition_on_previous_text=False。Qwen 指定中文、贪心解码；各模型按对应部署路径运行，并非相同架构/解码算法的微基准。
- 差异率采用字符编辑距离 / 参考字符数；统一简繁、全半角、大小写，去空白和标点。参考是未人工校对的微信机器转写，因此该数值不能当作真实错误率，更不能用 100% 减去它声称准确率。
- 不提供低配 CPU 的外推保证：本机仅在 CPU 路径上测试，并非 N100 或 4 GB 老电脑实测。样本量不足以证明所有方言、噪声和人名场景的整体提升。
- 进程内存是 50 ms 采样的峰值工作集，包含推理库。Qwen 显存为 PyTorch 分配峰值；该值不等于整张显卡占用，不能与未测得显存的数据直接比较。
- 测试用 faster-whisper 1.2.1 与项目一致；测试 CTranslate2 为 4.8.2，项目原环境为 4.8.1。其他依赖和模型 revision 已留档；因此这是沿用项目参数的独立环境对照，并非原应用端到端计时。

## 实测汇总

| 配置 | 203 秒音频耗时 | RTF↓ | 单条 P95 | 与微信转写差异率↓ | 峰值进程内存 | Qwen 分配显存峰值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-tiny-cpu | 22.17 s | 0.109 | 5.11 s | 26.44% | 279 MiB | 未测 |
| whisper-base-cpu | 21.95 s | 0.108 | 1.83 s | 17.04% | 407 MiB | 未测 |
| whisper-small-cpu | 57.80 s | 0.285 | 5.29 s | 10.58% | 593 MiB | 未测 |
| whisper-medium-cpu | 163.63 s | 0.808 | 13.75 s | 8.11% | 1674 MiB | 未测 |
| zipformer-ctc | 2.74 s | 0.014 | 0.34 s | 10.22% | 390 MiB | 未测 |
| zipformer-rnnt | 3.61 s | 0.018 | 0.43 s | 11.16% | 420 MiB | 未测 |
| qwen-onnx-cpu | 61.59 s | 0.304 | 7.87 s | 4.35% | 3737 MiB | 未测 |
| whisper-medium-cuda | 13.66 s | 0.067 | 1.52 s | 10.22% | 1607 MiB | 未测 |
| whisper-turbo-cuda | 7.87 s | 0.039 | 0.80 s | 6.82% | 1676 MiB | 未测 |
| whisper-large-v3-cuda | 20.51 s | 0.101 | 2.42 s | 6.93% | 3082 MiB | 未测 |
| qwen-06-cuda | 38.57 s | 0.190 | 4.61 s | 3.64% | 2401 MiB | 1.67 GiB |
| qwen-17-cuda | 44.16 s | 0.218 | 5.16 s | 2.94% | 4800 MiB | 4.01 GiB |

RTF = 识别耗时 / 音频时长，越低越快。不同模型资源档位不代表质量必然单调上升。

每轮使用相同的随机顺序策略。差异率按第一轮输出计算；Tiny、Base 在两轮中分别有 2 条、1 条输出变化，其余配置是否变化可查原始记录。

## 部署中发现的问题

- Zipformer 的原始 ONNX 文件直接处理约 22 秒样本时，CTC 和 Transducer 均出现 Reshape 维度错误；两份原始失败日志保留在测试目录。表中结果是增加最多 15 秒、末段低能量切分后的配置，不能把它描述成无改动即可替换。
- Qwen ONNX 上游示例硬编码的 system/user token ID 与下载模型的分词器不一致。测试入口改为用实际分词器编码提示模板；参考文本没有进入提示词。
- ONNX CPU 候选是社区导出，官方 HF GPU 候选是另一套转换/运行路径，量化和预处理差异需要随发布版本固定。
- Qwen CPU 特征提取与上游 PyTorch 实现做了同一条音频的数值核对：最大绝对差约 4.86e-5、平均绝对差约 3.28e-7；这验证了实现一致性，不等于量化质量验证。

## 冷启动参考

| 配置 | 加载阶段（含库导入） | 首条推理 |
| --- | ---: | ---: |
| whisper-tiny-cpu | 2.37 s | 1.43 s |
| whisper-base-cpu | 0.51 s | 6.21 s |
| whisper-small-cpu | 1.22 s | 1.83 s |
| whisper-medium-cpu | 3.13 s | 5.44 s |
| zipformer-ctc | 0.99 s | 0.02 s |
| zipformer-rnnt | 0.98 s | 0.05 s |
| qwen-onnx-cpu | 8.07 s | 2.49 s |
| whisper-medium-cuda | 2.11 s | 0.77 s |
| whisper-turbo-cuda | 2.16 s | 0.55 s |
| whisper-large-v3-cuda | 3.42 s | 0.71 s |
| qwen-06-cuda | 9.76 s | 1.24 s |
| qwen-17-cuda | 13.30 s | 1.07 s |

首条采用同一短语音；未清空 Windows 文件缓存，因此不能视作重启电脑后的磁盘冷启动。

## 复现与证据

- 入口：`tools/benchmark_stt_local.py`。测试资产、环境版本、模型 revision、逐条结果位于 `tmp/stt-benchmark-20260921/`。
- `summary.json` 不含聊天原文；`manifest.private.json`、`results/*.private.json` 和 `review.private.html` 含本地语音或转写，不纳入公开报告。
- 抽样清单记录 WAV 的 SHA-256；全部 20 条音频、10 组模型资产的大小及 LFS 哈希已重新核对。12 个运行配置共 480 条推理记录，通过独立动态规划编辑距离复算；记录见 `verification.json`。
- `model-lock.json` 记录实际下载的仓库、revision 和文件清单；`requirements-lock.txt` 留存测试环境依赖。项目 Turbo 的原仓库地址当前重定向至 `dropbox-dash/faster-whisper-large-v3-turbo`，测试使用该重定向目标。
- 当前应用模型设置和项目主虚拟环境未更改；测试依赖安装在独立虚拟环境。

```powershell
tmp/stt-benchmark-20260921/venv/Scripts/python.exe tools/benchmark_stt_local.py --root tmp/stt-benchmark-20260921 --model qwen-06-cuda
```
