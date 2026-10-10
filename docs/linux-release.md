# Linux 发布流程（x64）

Linux 与 Windows / macOS 一起发在同一个 tag Release 里，并且是**必需平台**：原生组件重建
失败时，`release.yml` 会直接失败，而不是静默少发一个平台。

Linux 与 Windows / macOS 走**同一条**原生组件路线：发版当下现产一份 source-public 原生核心，
所以不需要任何仓库变量 pin，也不需要额外 secret（只复用发版已有的
`WCE_NATIVE_CORE_PRODUCER_TOKEN`）。45 天有效期由「每次发版重建」自然续上。

产物形态刻意不做 AppImage / deb：Linux 走「用户级、免 root 的 `tar.gz` + `install.sh`」。

## 涉及的三个工作流

| 工作流 | 位置 | 作用 |
| --- | --- | --- |
| `linux-native-production.yml` | **WCDB**（私藏 producer 仓） | 被 `rebuild_wcdb_release.py` dispatch：构建 + 自检 + 把原生核心发成不可变 Release 资产 |
| `tools/rebuild_wcdb_release.py` | 本仓 | 发版当下 dispatch producer，等它跑完，按 Release 摘要下载并核对 45 天窗口 |
| `linux-private-build.yml` | 本仓 | 可复用构建：重建原生核心 → 校验 → 编译 integrity → `dist:linux` → 打包校验 → 上传 |
| `release.yml` | 本仓 | `push tag v*` 触发；`build-linux-x64` 调用上面的可复用工作流，`publish-release` 汇总三个平台 |

## 操作顺序

1. **配 producer**（WCDB 私藏仓，一次性）：

   - 仓库级 variable `WCE_ROOT_PUBLIC_KEY_HEX`：128 hex，P-256 **公钥**（不是私钥），
     与 macOS / Windows environment 里那把一致。
   - 其余什么都不用配：Linux 没有代码签名，不需要任何私钥 / 证书 / 时间戳 secret
     （Windows 的 PFX、macOS 的 P12 在 Linux 上都不存在）。

2. **发版**：推 tag `v*`。tag 必须在 `origin/main` 上。

   发版里 `build-linux-x64` 会自动 `tools/rebuild_wcdb_release.py --component linux-native`：
   dispatch WCDB 的 `Linux native production`，等它产出一份带唯一 build id 的不可变 Release，
   核对 Release target / 资产摘要 / 45 天窗口后才继续打包。

3. **本仓需要的唯一配置**：仓库级 secret `WCE_NATIVE_CORE_PRODUCER_TOKEN`
   （对 `2977094657/WCDB` 有 Actions read/write 与 Contents read）。Windows / macOS 发版
   已经在用同一个 secret，Linux 直接复用，**不需要新增任何配置**。

## 为什么可以不做代码签名

Linux 没有 Authenticode / codesign 的等价物，所以身份改成**内容哈希**，方向是单向的：

- broker 里编死了「随包 client 的哈希」；
- broker 自己的哈希由 manifest 声明、由安装方 pin。

`sha256(file) == pin(file)` 无解，所以「组件自带自身哈希」这种不可判定的方向被显式禁止：
`Test-LinuxNativeProductionArtifact.py` 与 `desktop/scripts/linux-native-core-packaging.cjs`
两头都断言了这一点。消费侧还会在打包后再哈希一次（`packaged ... differs from the reviewed
native artifact`），确保打包过程没有顺手重编。

导出完整性模块 `libwce_integrity.so` 由本仓在发布时用**一次性构建密钥**现编（语义等同于
官方的 `-GenerateEphemeralSigningKey`）：该密钥只用于导出物自身封签，权威封印是原生核心产出的
WES2 sidecar。之所以不在 producer 侧预编，是因为 `wce_integrity` 会把 Nuxt 的 CSS 编进去，
必须和当次 UI 构建同源。

## 会踩的坑

- **45 天有效期**：manifest 固定 45 天窗口。因为每次发版都重建，安装包自带的组件始终是
  当次构建；旧安装包到期后需要装新版本（与 Windows / macOS 同一行为）。
- **构建 ID 不可复用**：producer 在发布前会检查 `linux-native-<build-id>` 是否已存在，存在即拒绝。
- **校验失败就是失败**：`build-linux-x64` 不设 `continue-on-error`，`publish-release.needs` 包含它，
  所以重建失败 / 摘要不符 / 哈希漂移都会让 release 停在半路而不是发出去。
- **重跑要用新的 run attempt**：build id 由 WCDA 的 run id + attempt 派生，同一次发版重跑
  会拿到新 id，不会撞上已发布的 tag。
- **产物名不能重**：Linux 用 `SHA256SUMS-linux.txt` / `release-provenance-linux.json`，
  避免与 Windows 的 `SHA256SUMS.txt` / `release-provenance.json` 在 `merge-multiple` 下载时互相覆盖。
- **producer 不占用 Actions artifact 配额**：Linux producer 只发不可变 Release 资产，
  没有 `upload-artifact` 步骤，所以 artifact 配额爆掉不会影响发版。

## 桌面运行时的 Linux 判定（已修，别再回退）

`desktop/src/native-core-runtime.cjs` 现在完整支持 Linux 的 schema v4，规则和
Windows / macOS 对齐：

| 运行形态 | 接受的产物 | 说明 |
| --- | --- | --- |
| 打包（冻结） | production 或受限 source-public | 与 Windows 同一原则：发布工作流发的就是 source-public |
| 源码 checkout | 只接受受限 source-public | 与 macOS 同一原则（`dev-local` 不授权） |

Linux 没有代码签名，身份 = `linuxClientSha256` / `linuxBrokerSha256` 两组内容哈希
pin；`linuxHostVerification` 必须与 `sourceRuntime` 配对（源码分发 = 直接父进程，
其余 = 内容哈希 pin），且 Linux 清单不得夹带任何 Windows / macOS 的签名身份字段。
这四条在**两侧**都要成立，缺一就会出现「桌面放行、后端拒绝」的半可用状态：

- 桌面：`desktop/src/native-core-runtime.cjs` + `desktop/tests/native-core-runtime.test.cjs`
- 后端：`src/wechat_decrypt_tool/native_core_client.py` + `tests/test_linux_native_core_policy.py`

两条都被 `build-linux-x64` 当门禁跑，所以「能出包」和「能用」之间不再有缝。

## 还没做的验证

- **没有 GUI 冒烟**：Windows 有 `smoke:win`、macOS 有 `smoke:mac`，Linux 侧只有
  「打包产物上的原生核心策略判定」（`Verify the packaged Linux runtime` 步骤）加
  `install.sh` 的摘要校验，没有真的启动过界面。
- **Ubuntu 24.04 的沙箱限制**：用户级安装没法给 `chrome-sandbox` 置 setuid root，
  而 24.04 起 AppArmor 会限制非特权 user namespace —— 真机验证时若起不来，优先查
  这一条（需要 AppArmor profile 或 `--no-sandbox` 的取舍）。
- **`dev-local` 在 Linux 上不授权**：本地自建开发核心（`WCE_DEVELOPMENT_BUILD=ON`
  产出的 `linuxIntegrityMode: development` 清单）不会被后端接受，本地联调需要用
  producer 产的 source-public 产物（与 macOS 现状一致）。
