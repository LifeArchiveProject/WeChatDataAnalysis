# Windows 路径编码约定

中文路径必须在首次选择、保存配置、升级回填和迁移数据后保持原字符串。

- Electron 配置与 `output-location.path` 使用 UTF-8；PowerShell 读取时必须显式指定 `-Encoding UTF8`。
- 含中文的 Windows PowerShell 5.1 脚本源码保留 UTF-8 BOM。配置文件使用无 BOM 的 UTF-8，两者用途不同。
- NSIS 与 PowerShell 的路径返回值通过 UTF-16LE 文件及 `FileReadUTF16LE` 传递，不能把未经明确解码的标准输出直接当成路径。
- 不通过猜测编码、忽略解码错误或更改用户系统代码页来修复路径。

## 验证

在 Windows 上执行 `npm ci --ignore-scripts`（工作目录为 `desktop`），然后执行：

```powershell
node --test tests/desktop-settings.test.cjs tests/output-dir.test.cjs tests/installer-output-dir.test.cjs tests/installer-safety.test.cjs tests/installer-unicode-integration.test.cjs
```

真实 NSIS 测试使用 package-lock 锁定的 electron-builder 获取编译器，自动处理其缓存布局与 NSISDIR；获取或运行失败会使测试失败，Windows 上不会因缺少编译器而跳过。离线环境可通过 `NSIS_MAKENSIS` 指定完整编译器路径，并按需设置 `NSISDIR`。

测试覆盖中文、生僻字、emoji、空格、PowerShell 特殊符号、首次安装、已有配置升级、旧版 BOM 配置、旧配置迁移、恢复默认目录、重复回填保存，以及数据文件内容和卸载目录边界。

相关 PR 和 main 推送由 `Windows Installer Unicode` 工作流检查；Windows 发布流程也运行同一组测试，失败时不会继续发布。PR 检查是否强制阻止合并取决于仓库的分支保护设置。

2.3 和 2.4 曾包含相同的编码缺陷：首次选择中文目录可正确保存，但安装器再次读取时产生乱码。因此回归验证必须覆盖再次读取，不能只检查首次选择成功。
