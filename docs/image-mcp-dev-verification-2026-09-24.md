# MCP 历史图片 dev 验证（2026-09-24）

## 运行环境

- 使用 Node 24.21.0 执行 `desktop/scripts/dev.cjs`，启动 Nuxt、Electron 和 Python 源码后端。
- 前端 `http://127.0.0.1:3000`，后端 `http://127.0.0.1:10392`。
- 系统默认 Node 18 启动失败；改用本机已有 Node 24，并补齐前端缺失依赖后启动成功。没有修改依赖清单或锁文件。
- `/api/health` 返回 healthy，聊天页 HTTP 200；原生桌面确认聊天记录、图片筛选、图片查看器均正常显示。

## 自动化验证

运行以下测试：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_mcp_router.py tests/test_chat_media_image_cache_upgrade.py tests/test_chat_large_image_frontend.py tests/test_chat_media_file_id_scope.py tests/test_chat_image_group_info.py -q
```

结果：62 passed，145 subtests passed。

覆盖 MCP 参数声明、默认高清优先、显式关闭参数、转发图片定位参数，以及 MCP 调用到图片接口的补图链路。远程成功下载、额度不足、限流、账号冻结与远端失败等自动化场景使用模拟服务响应。

## 真实 dev 服务验证

通过运行中服务的 MCP 读取真实历史图片消息，再调用图片链接工具并下载、解码返回文件。没有调用 AI 模型。

| 样本 | 返回像素尺寸 | HTTP |
| --- | --- | --- |
| 实时数据库中的历史图片 1 | 1722 × 1169 | 200 |
| 实时数据库中的历史图片 2 | 872 × 1577 | 200 |
| 实时数据库中的历史图片 3 | 938 × 1502 | 200 |
| 解密快照中的历史图片 1 | 800 × 548 | 200 |
| 解密快照中的历史图片 2 | 238 × 274 | 200 |
| 解密快照中的历史图片 3 | 319 × 268 | 200 |

前三张确认外部 MCP 读取未被限制为缩略图，也没有走内置 AI 的 1600 像素压缩函数。小尺寸样本只能证明当前可读取该尺寸文件，不能据此宣称它们是高清原图。

对另一张本地只有 210 × 118 图片的群聊历史消息，实际设置 `fetch_remote=true`。后端成功获取 CDN token 并触发远程请求，最终返回 HTTP 404：`Large image not found locally or via CDN.`。该样本的真实远程原图下载未成功，不能把模拟下载测试等同于真实原图恢复成功。

## 结论

MCP 参数修复、本地大图读取、dev 桌面显示及自动化回归通过。真实旧图片的远程补图链路已触发，但所测缺图样本未恢复原图；不承诺所有历史图片均可恢复高清。
