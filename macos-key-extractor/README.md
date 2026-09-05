# WeData 密钥提取器（macOS）

这是一个面向普通 Mac 用户、独立且完全在本机运行的工具。它不读取其他应用的设置，也不预设任何用户名、磁盘或网络存储路径，只负责：

- 自动发现微信账号与可校验数据库；
- 强制执行一次全新捕获，不使用开始前已有的密钥缓存；
- 在明确确认后临时重签默认路径微信并使用 LLDB 捕获本次登录产生的 passphrase；
- 使用所选数据库校验密钥，并恢复腾讯原签名微信；
- 将验证后的密钥保存到当前用户的 `~/.wcdb-key-tool/wechat-passphrase.json`，并支持复制。

工具没有联网、更新或遥测功能。仅用于处理使用者本人有权访问的本机微信数据。

## 使用

1. 将 `WeDataKeyExtractor.app` 放到 `/Applications`。
2. 在“系统设置 → 隐私与安全性 → 完全磁盘访问权限”中启用它，然后完全退出并重新打开。
3. 工具会扫描常见微信数据目录；也可以手动选择微信数据库和临时工作目录，然后点击“检查环境并开始”。
4. 准备完成后点击“显示微信窗口”；如有系统安全提示，由本人决定是否在系统设置中确认。点击“我已手动打开，检查启动”，再依次完成：登录临时微信 → 检查断点 → 退出账号 → 启动监测并授权 → 等待“监测已就绪” → 重新登录同一账号。
5. 成功或取消后，工具会恢复腾讯原签名微信；成功时可以复制密钥或打开缓存位置。

## 构建

在仓库根目录准备好 `.venv` 后运行：

```bash
./macos-key-extractor/build-macos.sh
```

产物位于 `macos-key-extractor/dist/`，文件名会包含当前构建机器的原生架构。默认使用 ad-hoc 签名，适合本人测试；其他用户首次打开时需要按 macOS 提示确认，并单独授予完全磁盘访问权限。

需要让源码构建在升级后继续沿用 macOS 隐私授权时，应显式使用钥匙串中已有的固定签名身份，不要在每次构建时生成新证书。例如：

```bash
WEDATA_CODESIGN_IDENTITY="Your Existing Code Signing Identity" \
./macos-key-extractor/build-macos.sh
```

本地自签名证书只适用于创建它的 Mac，不能作为公共 Release 的发布证书，也不会被打进安装包。

面向公众提供顺畅安装体验时，应使用自己的 Apple Developer ID Application 证书并完成 Apple 公证：

```bash
WEDATA_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
WEDATA_NOTARY_PROFILE="your-notary-profile" \
./macos-key-extractor/build-macos.sh
```

构建会强制执行发布审计，发现用户主目录绝对路径、数据库、日志、偏好设置或密钥缓存文件时会终止，不会生成最终安装包。

## 兼容性与隐私

- 当前密钥捕获仅支持 Apple Silicon Mac；构建脚本能生成 Intel 原生产物不代表 LLDB 捕获流程已经兼容 Intel。
- 默认识别当前微信沙盒目录以及若干旧版常见目录，多账号会分别列出；扫描不到时可手动选择任一加密微信数据库。
- 微信 4.x 必须使用 `Documents/app_data/xwechat_files` 下的活动数据库；工具不会退回同账号的旧 `Documents/xwechat_files` 副本，避免用错误 salt 拒绝正确候选密钥。
- 工作文件位于当前登录用户自己的 `~/Library/Application Support/WeDataKeyExtractor/`，不会引用构建者的目录。
- 密钥只在提取成功并校验后写入当前用户的 `~/.wcdb-key-tool/wechat-passphrase.json`；安装包不包含任何聊天数据库、日志、偏好设置或密钥。
- 工具不联网、不上传聊天数据，也没有更新、广告或遥测模块。

集成范围、状态机、安全恢复及验证边界见 [macOS 捕获说明](../docs/MACOS_KEY_CAPTURE.md)。本工具的源码不包含本地证书；临时微信签名与工具自身的发布签名是两回事，不能替代 Apple 公证或保证所有微信版本兼容。
