# macOS 数据库密钥组件交付边界

WCDA 公开仓库只保留最小进程调用、完整性验证和打包逻辑，不包含密钥捕获或在线校验实现。核心实现由 Producer 仓库构建为签名的 Universal2 `wda_xkey_helper`，再由受保护的 GitHub Actions Environment 按精确 run、revision、build ID 和证书叶指纹装入 macOS 应用。

## 运行链路

1. WCDA 验证 Producer 的 manifest、trust、provenance、SHA-256、45 天有效期、Universal2 架构及 helper 代码签名。
2. WCDA 只向 helper 传入目标微信 PID 和本次操作超时；stdin 关闭，不参与 helper 内部状态机。
3. helper 在私有实现中自行完成调用方、目标进程和在线策略校验。公开 WCDA 不包含服务地址或内部通信细节。
4. helper 最多执行一次密钥获取；成功时 stdout 只返回一行 64 位小写十六进制结果，失败时不返回密钥数据。断连、取消或超时会终止 helper。

实际内存读取仍在用户 Mac 本地执行；在线服务不接收微信进程内存、数据库或数据库密钥。私有实现细节不会进入公开 WCDA 源码和公开构建元数据。

## 私有构建 Environment

手动运行 `.github/workflows/macos-private-build.yml`，Environment 名为 `macos-private-pki-production`。配置以下 Variables：

- `WCE_MACOS_XKEY_ARTIFACT_REPOSITORY`
- `WCE_MACOS_XKEY_ARTIFACT_RUN_ID`
- `WCE_MACOS_XKEY_SOURCE_REVISION`
- `WCE_MACOS_XKEY_BUILD_ID`
- `WCE_MACOS_KEY_HELPER_SIGNER_SHA256`
- `WCE_MACOS_WCDA_HOST_SIGNER_SHA256`
- `WCE_MACOS_WCDA_HOST_SIGNING_IDENTITY`

配置以下 Secrets：

- `WCE_MACOS_PRODUCER_READ_TOKEN`：只读 Producer Actions artifact。
- `WCE_MACOS_WCDA_HOST_P12_BASE64`：持久 host leaf 私钥与证书链的 P12（Base64）。
- `WCE_MACOS_WCDA_HOST_P12_PASSWORD`
- `WCE_MACOS_SELF_SIGNED_ROOT_CERT_BASE64`：同一离线 root 的**公开 DER 证书**；root 私钥不得上传 GitHub、服务器或用户安装包。

上述 `WCE_MACOS_WCDA_HOST_*`、`WCE_MACOS_KEY_HELPER_SIGNER_SHA256` 名称是 Producer 与 WCDA 的固定交付契约，不使用省略 `WCDA` 或改写 `KEY_HELPER` 的别名。

workflow 只允许从 `main` 的精确 `github.sha` 手动运行。它会先验证 P12 中只有 host leaf 与同一个公开 root，校验 CA/leaf 约束、唯一 code-signing EKU、Organization 和 host leaf pin，再把 P12 和 root 导入临时 keychain。构建保留 Producer helper 的独立签名，验证 app/backend 的 identifier、叶证书和精确 designated requirement，然后仅上传私有 Actions artifact；不会创建 GitHub Release。任务结束后临时 keychain、P12 和 root 文件都会清理。

免费自签模式不会公证或 stapling，用户首次启动可能看到 Gatekeeper 警告。正式发布前仍必须在真实 Apple Silicon Mac、已登录微信和真实在线授权服务上完成一次端到端获取；Windows CI 不能替代这项验收。
