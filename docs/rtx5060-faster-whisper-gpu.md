# RTX 5060 faster-whisper CUDA 验收说明

状态：实现完成，待 RTX 5060 实机验收。更新：2026-07-29。

## 适用范围

本项目的语音转文字使用 `faster-whisper` 和 CTranslate2，不使用 PyTorch。因此，同类 PyTorch 音色克隆项目采用的 `cu128` wheel 安装路线不能直接复制到这里；本说明只复用其 RTX 50 系显卡驱动、磁盘、模型缓存与验收原则。

默认设备是 CPU `int8`。在有 NVIDIA GPU 的机器上，设置页可选择 NVIDIA GPU；首次识别会使用 CUDA `float16` 加载模型。CUDA 探测或模型初始化失败时，会自动改用 CPU `int8`，不影响语音播放、聊天查看或导出任务。

## 服务器前置检查

先在目标机上执行只读检查：

```bash
nvidia-smi
python3 --version
ffmpeg -version
df -h
```

`nvidia-smi` 必须能列出 RTX 5060。若它不可用，先由服务器管理员修复 NVIDIA driver；不要通过反复重装 Python 包排查驱动问题。

本项目不需要安装 `torch`、`torchaudio` 或复用音色克隆项目的 wheelhouse。安装当前项目的语音依赖：

```bash
uv sync --no-editable --extra voice-transcription
```

当前锁定的 `CTranslate2 4.8.1` 在 Linux GPU 环境需要 NVIDIA driver、CUDA 12.x 和 cuDNN 9 运行库；PyTorch 的 `cu128` wheel 不会为 CTranslate2 提供这些库。先完成只读探测，再由服务器管理员或已获授权的维护人员按 CTranslate2 对应版本的官方安装说明补齐运行库。若采用 PyPI 的用户级 CUDA/cuDNN 包，也应只安装到本项目虚拟环境，并在启动后端的同一用户进程中设置其库路径；不要修改系统 `/usr`、全局 `LD_LIBRARY_PATH` 或共享 CUDA 安装。

## 模型准备

当前默认模型是 `Systran/faster-whisper-medium`，磁盘约 1.43 GiB。生产验收前应将模型放进目标机 Hugging Face 缓存，或将 `WECHAT_TOOL_WHISPER_MODEL` 指向完整的本地模型目录；默认禁止首次识别联网下载。

建议把缓存放在数据盘，例如：

```bash
export HF_HOME=/mnt/sdb/wechat-data-analysis/hf-cache
export WECHAT_TOOL_WHISPER_MODEL=medium
export WECHAT_TOOL_WHISPER_ALLOW_DOWNLOAD=0
```

如果缓存尚未准备好，可在已获联网许可的维护窗口临时把 `WECHAT_TOOL_WHISPER_ALLOW_DOWNLOAD=1`，完成下载后恢复为 `0`。模型与缓存目录包含本地运行资产，不要提交到 Git。

## CUDA 验收

启动后端后，先检查 CTranslate2 是否能识别 CUDA：

```bash
python - <<'PY'
import ctranslate2
print("cuda device count:", ctranslate2.get_cuda_device_count())
PY
```

期望设备数量大于零。然后打开应用的“设置 -> 语音转文字”：

1. 页面应显示检测到的 NVIDIA GPU；RTX 5060 名称会由 `nvidia-smi` 提供。
2. 选择“NVIDIA GPU”。该偏好会保存到应用 `output/runtime_settings.json`。
3. 对一条清晰中文微信语音点击“转文字”，或用同一会话开启“语音转文字”导出。
4. 重新打开设置页，确认“实际”显示为“NVIDIA GPU”。
5. 导出结果仍需包含可播放的 `media/voices/*.mp3` 与中文转写文本。

若 CUDA 探测通过但模型初始化失败，设置页会保留“NVIDIA GPU”为已选设备，并显示自动回退原因；“实际”应显示为 CPU。此时语音转写仍应成功，随后应记录 CTranslate2、NVIDIA driver 和 CUDA 运行库版本再排查。

## 配置优先级

推理设备优先级如下：

```text
WECHAT_TOOL_WHISPER_DEVICE 环境变量
> 设置页保存的设备偏好
> 默认 CPU
```

部署脚本若设置了 `WECHAT_TOOL_WHISPER_DEVICE`，界面会标记为“由启动环境变量固定”，避免用户误以为修改已生效。未设置该环境变量时，使用设置页选择 CPU 或 NVIDIA GPU。

## 验收记录

在 RTX 5060 服务器完成实测后，记录以下信息：

```text
nvidia-smi 的 GPU 名称、Driver Version、CUDA Version
Python / faster-whisper / CTranslate2 版本
CTranslate2 CUDA device count
设置页检测结果、已选设备、实际设备、是否发生回退
单条语音首次识别耗时与缓存后二次识别耗时
导出中的语音数量、成功/失败/缓存统计
```

不要为了制造回退场景而在共享服务器上卸载驱动、修改系统 CUDA、重启机器或停止他人进程。自动回退路径由本地单元测试覆盖；服务器只验证真实 NVIDIA GPU 成功路径。
