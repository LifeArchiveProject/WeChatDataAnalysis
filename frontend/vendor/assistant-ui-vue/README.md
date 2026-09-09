# assistant-ui Vue 官方源码快照

上游仓库：https://github.com/assistant-ui/assistant-ui

固定提交：`3a45a01c0d6141102638ecd4f32d1af4d01fb510`，目录 `packages/vue/src`。

引入日期：2026-09-09。许可证见 [LICENSE](./LICENSE)。原说明见 [UPSTREAM-README.md](./UPSTREAM-README.md)。

上游 Vue 包目前为 `private: true`、版本 `0.0.0`，尚未发布到 npm。本目录保存未修改的官方运行时源码（不含上游测试），通过本地 `file:` 依赖供 Nuxt/Vite 编译，避免安装时追踪浮动分支。`package.json` 是本项目的适配清单：入口指向源码，并固定匹配的 core、store 和 tap 版本。

应用使用官方 external-store 接口连接已有后端；输入区、引用、工具详情和会话持久化沿用现有实现。共享运行时中的 React 导入按官方方式映射到 tap 的 standalone shim，无 React 渲染器。映射集中在 `frontend/lib/assistant-ui-aliases.js`，供开发、构建和测试复用。

升级时应同时核对官方源码和 core/store/tap 版本，运行消息增量更新、会话切换、停止/继续、滚动、SSR 和生产构建验证。正式包发布后可移除本快照、改用固定版本的 npm 依赖。
