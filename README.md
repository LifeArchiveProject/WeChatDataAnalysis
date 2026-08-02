<p align="center">
    <img src="frontend/public/logo.png" alt="微信数据库解密工具" width="200" />
</p>

<div align="center">
    <h1>WeChatDataAnalysis - 微信数据库解密与分析工具</h1>
    <p>微信4.x数据解密并生成年度总结，高仿微信，支持实时更新，导出聊天记录，朋友圈等大量便捷功能</p>
    <p><b>特别致谢</b>：<a href="https://github.com/H3CoF6">H3CoF6</a>（密钥与朋友圈等核心内容的技术支持）、<a href="https://github.com/ycccccccy/echotrace">echotrace</a>、<a href="https://github.com/hicccc77/WeFlow">WeFlow</a>（本项目大量功能参考其实现）</p>
    <p>如需定制功能，请联系 QQ：2977094657。</p>
    <img src="https://img.shields.io/github/v/tag/LifeArchiveProject/WeChatDataAnalysis" alt="Version" />
    <img src="https://img.shields.io/github/stars/LifeArchiveProject/WeChatDataAnalysis" alt="Stars" />
    <img src="https://gh-down-badges.linkof.link/LifeArchiveProject/WeChatDataAnalysis" alt="Downloads" />
    <img src="https://img.shields.io/github/forks/LifeArchiveProject/WeChatDataAnalysis" alt="Forks" />
    <a href="https://qm.qq.com/q/VQEQ7PcGkk"><img src="https://img.shields.io/badge/QQ Group-WeChatDataAnalysis-12B7F5?logo=tencentqq&logoColor=white" alt="QQ Group" /></a>
    <img src="https://img.shields.io/badge/Python-3776AB?logo=Python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Vue.js-4FC08D?logo=Vue.js&logoColor=white" alt="Vue.js" />
    <img src="https://img.shields.io/badge/SQLite-003B57?logo=SQLite&logoColor=white" alt="SQLite" />
    <p>如果你需要 QQ 侧的数据解密、分析或年度总结类工具，欢迎体验 <a href="https://github.com/H3CoF6/WeQ">H3CoF6/WeQ</a>；WeQ 作者也是本项目开发成员之一</p>
</div>

## 年度总结

<table>
  <tr>
    <td align="center" colspan="2"><img src="frontend/public/style1.png" alt="年度总结 Modern" width="800"/></td>
  </tr>
  <tr>
    <td><img src="frontend/public/AnnualSummary1.png" alt="AnnualSummary 1" width="400"/></td>
    <td><img src="frontend/public/AnnualSummary2.png" alt="AnnualSummary 2" width="400"/></td>
  </tr>
  <tr>
    <td><img src="frontend/public/AnnualSummary3.png" alt="AnnualSummary 3" width="400"/></td>
    <td><img src="frontend/public/AnnualSummary4.gif" alt="AnnualSummary 4" width="400"/></td>
  </tr>
  <tr>
    <td><img src="frontend/public/AnnualSummary5.gif" alt="AnnualSummary 5" width="400"/></td>
    <td><img src="frontend/public/AnnualSummary6.png" alt="AnnualSummary 6" width="400"/></td>
  </tr>
  <tr>
    <td><img src="frontend/public/AnnualSummary7.png" alt="AnnualSummary 7" width="400"/></td>
    <td><img src="frontend/public/AnnualSummary8.png" alt="AnnualSummary 8" width="400"/></td>
  </tr>
</table>

## 界面预览

<table>
  <tr>
    <td align="center" colspan="2"><b>聊天记录页面</b>（支持多种消息类型展示，样式尽可能与微信保持一致）</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/message.png" alt="聊天记录页面" width="800"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>修改消息</b>（本地修改，支持恢复）</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/edit.gif" alt="修改消息" width="800"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>实时消息同步</b>（点击侧边栏闪电图标后，消息会自动刷新）</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/RealTimeMessages.gif" alt="实时消息同步" width="800"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>设置面板</b>（桌面行为、启动偏好、更新、朋友圈缓存策略）</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/setting.png" alt="设置面板" width="800"/></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>朋友圈</b>（支持查看用户之前朋友圈的背景图及时间；本地查看过的朋友圈即使后续不可见也可以查看）</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/sns.png" alt="朋友圈" width="800"/></td>
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
  <tr>
    <td align="center" colspan="2"><b>联系人导出</b></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="frontend/public/Contact.png" alt="联系人导出" width="800"/></td>
  </tr>
</table>

## 可导出的内容

| 内容 | 支持格式 | 导出范围 / 说明 |
| --- | --- | --- |
| 聊天记录 | HTML / JSON / TXT / Excel（ZIP） | 当前会话、自定义会话、全部会话、群聊或单聊；支持按消息类型和时间筛选 |
| 朋友圈 | HTML / JSON / TXT / Excel（ZIP） | 指定联系人或全部联系人 |
| 联系人 | HTML / JSON / TXT / Excel | 支持按联系人分类和关键词筛选，可选择是否包含头像链接 |
| 收藏 | HTML / JSON / TXT / Excel（ZIP） | 支持按收藏类型和关键词筛选 |
| 好友验证 | HTML / JSON / TXT / Excel | 支持按发起方向和关键词筛选 |
| 小程序 | HTML / JSON / TXT / Excel | 支持按关键词筛选 |
| 视频号直播 | HTML / JSON / TXT / Excel | 支持按直播类型和关键词筛选 |
| 转账与红包 | HTML / JSON / TXT / Excel | 支持按记录类型和关键词筛选 |
| 服务号记录 | HTML / JSON / TXT / Excel | 支持按服务号和记录类型导出 |
| 账号数据归档 | ZIP | 可选择导出数据库、资源文件或两者 |

> Excel 格式生成 `.xlsx` 文件；聊天记录、朋友圈和收藏会将对应格式文件与必要资源一起打包为 ZIP。

## Windows / macOS 兼容性

| 功能 | Windows | macOS |
| --- | --- | --- |
| 数据库密钥自动获取 | 支持 | 不提供；请用支持 Mac 的同类本地工具获取后手动填写 64 位密钥 |
| 数据库解密与离线分析 | 支持 | 支持 |
| 图片密钥内存扫描 | 支持 | 支持；首次使用可能需要授予辅助功能或管理员权限 |
| WCDB 实时消息、联系人和朋友圈 | 支持 | Apple Silicon 支持；Intel Mac 暂不支持实时 WCDB |
| 聊天、朋友圈、联系人、收藏等导出 | 支持 | 支持 |
| 账号全量归档 ZIP 导入与导出 | 支持 | 支持，并可与 Windows 双向迁移 |
| 微信进程大图 Hook | 支持 | 不提供，这是 Windows 专属能力 |

macOS 版本不会从微信进程提取数据库密钥。应用检测到 Mac 后只会显示获取方式提示；取得您本人账号的密钥并手动填写后，Apple Silicon Mac 上的数据库解密、实时消息、联系人、朋友圈、媒体、导出和迁移流程与 Windows 保持一致。

### 从 Windows 迁移到 Mac

1. 在 Windows 端打开全局导出，选择“账号数据归档”，同时包含数据库和资源文件。
2. 将生成的 `wechat_archive_*.zip` 传到 Mac，不要手动解压或修改归档内容。
3. 在 Mac 端进入“导入数据”，选择“账号归档 ZIP”，预览账号后确认导入。
4. 导入器会校验每个文件的 SHA-256；若本地已有同名账号，会在完整导入成功后保留旧目录备份。

已经由本项目解密并归档的数据，迁移后可直接离线查看；只有连接 Mac 上微信原始 WCDB 做实时读取时才需要手动填写数据库密钥。

## 加入群聊

也欢迎加入下方 QQ 群一起讨论。

<p align="center">
    <a href="https://qm.qq.com/q/VQEQ7PcGkk">
        <img src="frontend/public/QQImage_1770190010691_1103312318341691201.jpg" alt="WeChatDataAnalysis 加群二维码" width="360" />
    </a>
</p>

## 快速开始

### 1. 下载桌面安装包（推荐）

1. 打开 Release 页面（最新版）：https://github.com/LifeArchiveProject/WeChatDataAnalysis/releases/latest
2. Windows 下载 `Setup.exe`；macOS 15+ 的 Apple Silicon Mac 下载 `.dmg` 或 `mac.zip`
3. 安装完成后启动 `WeChatDataAnalysis`

> 如果 Windows 弹出“未知发布者/更多信息”等提示，请确认下载来源为本仓库 Release 后再选择“仍要运行”。
>
> macOS 首次打开若提示来源限制，请在“系统设置 → 隐私与安全性”中确认来自本仓库的应用。图片密钥扫描还可能需要授予终端或应用辅助功能权限。

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

#### 2.3 安装 WCDB 隔离运行时

实时聊天读取需要 Electron 隔离进程。全新克隆或 `desktop/package-lock.json` 更新后必须同步桌面端依赖：

```bash
cd desktop
npm ci
cd ..
```

#### 2.4 安装前端依赖

```bash
cd frontend
npm ci
```

#### 2.5 启动服务

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

#### 2.6 访问应用

- 前端界面: http://localhost:3000
- API服务(默认): http://localhost:10392 （可通过环境变量 WECHAT_TOOL_PORT 修改）
- API文档(默认): http://localhost:10392/docs

## MCP 服务

设置页中的“AI 接入提示词”会包含 endpoint 和 Bearer token，可直接复制给客户端作为接入指令。

## 打包为 EXE（Windows 桌面端）

本项目提供基于 Electron 的桌面端安装包（NSIS `Setup.exe`）。

```bash
# 1) 安装桌面端依赖
cd desktop
npm ci

# 2) 打包（会自动：nuxt generate -> 拷贝静态资源 -> PyInstaller 打包后端 -> electron-builder 生成安装包）
npm run dist
```

输出位置：`desktop/dist/WeChatDataAnalysis Setup <version>.exe`

## macOS 桌面端

公开发布流程目前仅生成 Windows 安装包。macOS 构建依赖未公开的完整性模块源码，维护者恢复受控源码后仍可在本地执行 `npm run dist:mac`；公共 GitHub Actions 不会尝试读取或发布该源码。

内置 Mac 原生资源的来源、哈希、修改内容和许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 安全说明

**重要提醒**:

1. **仅限个人使用**: 此工具仅用于解密您自己的微信数据
2. **密钥安全**: 请妥善保管您的解密密钥，不要泄露给他人
3. **数据隐私**: 解密后的数据包含个人隐私信息，请谨慎处理
4. **合法使用**: 请遵守相关法律法规，不得用于非法目的

## 免责声明

请在充分理解以下内容，并自愿承担相应责任的前提下使用本项目：

1. **项目性质**

   本项目为独立开发的非官方开源工具，与微信、腾讯及其关联主体不存在隶属、授权、合作或认可关系。相关产品名称和商标归其权利人所有。

2. **合法使用**

   本项目仅可用于处理使用者本人合法持有、管理或已经取得明确授权访问的数据。使用者应遵守适用的法律法规、软件许可协议、平台规则和隐私保护义务。

3. **数据与备份**

   使用过程可能涉及本地数据库、密钥、聊天记录、媒体文件、微信进程和系统接口。开始前请备份重要数据、密钥及配置，并自行负责密钥保管、数据安全和隐私保护。

4. **兼容性与运行风险**

   客户端版本变化、内存扫描、Hook、第三方组件及其他本地处理流程，可能导致账号提醒、功能失效、处理失败、文件异常或其他不可预期结果。本项目不保证对未来微信版本持续兼容。

5. **责任范围**

   本项目按现状提供，不对功能的准确性、完整性、稳定性或持续可用性作出明示或默示保证。在适用法律允许的范围内，因使用、误用、版本不兼容、操作中断或第三方策略变化产生的损失和后果，由使用者自行承担。

使用或继续使用本项目，即表示使用者已经阅读、理解并同意以上内容，并愿意对自己的操作及其结果负责。

## 致谢

1. **[echotrace](https://github.com/ycccccccy/echotrace)**
2. **[WeFlow](https://github.com/hicccc77/WeFlow)**
3. **[wx_key](https://github.com/ycccccccy/wx_key)** 
4. **[wechat-dump-rs](https://github.com/0xlane/wechat-dump-rs)** 
5. **[oh-my-wechat](https://github.com/chclt/oh-my-wechat)** 
6. **[vue3-wechat-tool](https://github.com/Ele-Cat/vue3-wechat-tool)** 
7. **[wx-dat](https://github.com/waaaaashi/wx-dat)**
8. **[Ritsu](https://xhslink.com/m/7YJUsd1sgyF)**
9. **[recarto404](https://github.com/recarto404)**

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LifeArchiveProject/WeChatDataAnalysis&type=Date)](https://www.star-history.com/#LifeArchiveProject/WeChatDataAnalysis&Date)

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。
