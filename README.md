<p align="center">
    <img src="frontend/public/logo.png" alt="微信数据库解密工具" width="200" />
</p>

<div align="center">
    <h1>WeChatDataAnalysis - 微信数据库解密与分析工具</h1>
    <p>一个专门用于微信4.x版本数据库解密的工具（支持聊天记录实时更新）</p>
    <p><b>特别致谢</b>：<a href="https://github.com/H3CoF6">H3CoF6</a>（密钥与朋友圈等核心内容的技术支持）、<a href="https://github.com/ycccccccy/echotrace">echotrace</a>、<a href="https://github.com/hicccc77/WeFlow">WeFlow</a>（本项目大量功能参考其实现）</p>
    <img src="https://img.shields.io/github/v/tag/LifeArchiveProject/WeChatDataAnalysis" alt="Version" />
    <img src="https://img.shields.io/github/stars/LifeArchiveProject/WeChatDataAnalysis" alt="Stars" />
    <img src="https://gh-down-badges.linkof.link/LifeArchiveProject/WeChatDataAnalysis" alt="Downloads" />
    <img src="https://img.shields.io/github/forks/LifeArchiveProject/WeChatDataAnalysis" alt="Forks" />
    <a href="https://qm.qq.com/q/VQEQ7PcGkk"><img src="https://img.shields.io/badge/QQ%20Group-WeChatDataAnalysis-12B7F5?logo=tencentqq&logoColor=white" alt="QQ Group" /></a>
    <img src="https://img.shields.io/badge/Python-3776AB?logo=Python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Vue.js-4FC08D?logo=Vue.js&logoColor=white" alt="Vue.js" />
    <img src="https://img.shields.io/badge/SQLite-003B57?logo=SQLite&logoColor=white" alt="SQLite" />
</div>

## 界面预览

<table>
  <tr>
    <td align="center"><b>首页</b></td>
    <td align="center"><b>检测页面</b></td>
  </tr>
  <tr>
    <td><img src="frontend/public/home.png" alt="首页" width="400"/></td>
    <td><img src="frontend/public/detection.png" alt="微信检测页面" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>解密页面</b></td>
    <td align="center"><b>图片密钥（填写）</b></td>
  </tr>
  <tr>
    <td><img src="frontend/public/decrypt.png" alt="数据库解密页面" width="400"/></td>
    <td><img src="frontend/public/imageAES.png" alt="图片密钥（填写）" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>图片解密页面</b></td>
    <td align="center"><b>解密成功页面</b></td>
  </tr>
  <tr>
    <td><img src="frontend/public/imageSucces.png" alt="图片解密页面" width="400"/></td>
    <td><img src="frontend/public/success.png" alt="解密成功页面" width="400"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>聊天记录页面</b></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/message.png" alt="聊天记录页面" width="800"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>聊天记录搜索</b></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/search.png" alt="聊天记录搜索" width="800"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>聊天记录导出</b></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/export.png" alt="聊天记录导出" width="800"/></td>
  </tr>
</table>

## 年度总结

> ⚠️ **提醒**：年度总结目前还不是最终版本，后续还会增加新总结或新内容。

也欢迎加入下方 QQ 群一起讨论。

<table>
  <tr>
    <td align="center"><img src="frontend/public/style1.png" alt="年度总结 Modern"/></td>
  </tr>
</table>

## 加入群聊

<p align="center">
    <a href="https://qm.qq.com/q/VQEQ7PcGkk">
        <img src="frontend/public/QQImage_1770190010691_1103312318341691201.jpg" alt="WeChatDataAnalysis 加群二维码" width="360" />
    </a>
</p>

## 快速开始

### 1. 下载并安装 EXE（Windows，推荐）

1. 打开 Release 页面（最新版）：https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/latest
2. 下载 `WeChatDataAnalysis.Setup.<version>.exe` 并运行安装
3. 安装完成后启动 `WeChatDataAnalysis`

> 如果 Windows 弹出“未知发布者/更多信息”等提示，请确认下载来源为本仓库 Release 后再选择“仍要运行”。

### 2. 从源码运行（开发者/高级用户）

#### 2.1 克隆项目

```bash
git clone https://github.com/LifeArchiveProject/WeChatDataAnalysis.git
cd WeChatDataAnalysis
```

#### 2.2 安装后端依赖

```bash
# 使用uv (推荐)
uv sync
```

#### 2.3 安装前端依赖

```bash
cd frontend
npm install
```

#### 2.4 启动服务

#### 启动后端API服务
```bash
# 在项目根目录
uv run main.py
```

#### 启动前端开发服务器
```bash
# 在frontend目录
cd frontend
npm run dev
```

#### 2.5 访问应用

- 前端界面: http://localhost:3000
- API服务: http://localhost:8000
- API文档: http://localhost:8000/docs

## 打包为 EXE（Windows 桌面端）

本项目提供基于 Electron 的桌面端安装包（NSIS `Setup.exe`）。

```bash
# 1) 安装桌面端依赖
cd desktop
npm install

# 2) 打包（会自动：nuxt generate -> 拷贝静态资源 -> PyInstaller 打包后端 -> electron-builder 生成安装包）
npm run dist
```

输出位置：`desktop/dist/WeChatDataAnalysis Setup <version>.exe`

## 使用指南

### 获取解密密钥

在使用本工具之前，您需要先获取微信数据库的解密密钥。推荐使用以下工具：

**wx_key** (推荐)
   - 项目地址: https://github.com/ycccccccy/wx_key
   - 支持获取微信 4.x 数据库密钥

## 安全说明

**重要提醒**:

1. **仅限个人使用**: 此工具仅用于解密您自己的微信数据
2. **密钥安全**: 请妥善保管您的解密密钥，不要泄露给他人
3. **数据隐私**: 解密后的数据包含个人隐私信息，请谨慎处理
4. **合法使用**: 请遵守相关法律法规，不得用于非法目的

## 致谢

本项目的开发过程中参考了以下优秀的开源项目和资源：

1. **[echotrace](https://github.com/ycccccccy/echotrace)** - 微信数据解析/取证工具
   - 本项目大量功能参考并复用其实现思路，提供了重要技术支持

2. **[WeFlow](https://github.com/hicccc77/WeFlow)** - 微信数据分析工具
   - 提供了重要的功能参考和技术支持

3. **[wx_key](https://github.com/ycccccccy/wx_key)** - 微信数据库与图片密钥提取工具
   - 支持获取微信 4.x 数据库密钥与缓存图片密钥
   - 本项目推荐使用此工具获取密钥

4. **[wechat-dump-rs](https://github.com/0xlane/wechat-dump-rs)** - Rust实现的微信数据库解密工具
   - 提供了SQLCipher 4.0解密的正确实现参考
   - 本项目的HMAC验证和页面处理逻辑基于此项目的实现

5. **[oh-my-wechat](https://github.com/chclt/oh-my-wechat)** - 微信聊天记录查看工具
   - 提供了优秀的聊天记录界面设计参考
   - 本项目的聊天界面风格参考了此项目的实现

6. **[vue3-wechat-tool](https://github.com/Ele-Cat/vue3-wechat-tool)** - 微信聊天记录工具（Vue3）
   - 提供了聊天记录展示与交互的实现参考

7. **[wx-dat](https://github.com/waaaaashi/wx-dat)** - 微信图片密钥获取工具
   - 实现真正的无头获取图片密钥，不再依赖扫描微信内存与点击朋友圈大图

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LifeArchiveProject/WeChatDataAnalysis&type=Date)](https://www.star-history.com/#LifeArchiveProject/WeChatDataAnalysis&Date)

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

---

**免责声明**: 本工具仅供学习研究使用，使用者需自行承担使用风险。开发者不对因使用本工具造成的任何损失负责。

