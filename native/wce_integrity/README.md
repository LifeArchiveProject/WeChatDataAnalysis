# wce_integrity

Python HTML 导出完整性组件的原生扩展源码。发布包只需要携带编译后的 `wce_integrity.pyd`，不要把本目录随用户版一起分发。

构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_wce_integrity.ps1
```

生产构建可以通过环境变量注入签名私钥：

```powershell
$env:WCE_SIGNING_KEY_HEX = "<32-byte-p256-private-key-hex>"
powershell -ExecutionPolicy Bypass -File .\tools\build_wce_integrity.ps1
```
