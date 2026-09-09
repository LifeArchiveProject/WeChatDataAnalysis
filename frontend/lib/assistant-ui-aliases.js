// 官方 Vue 预览版通过无界面的 tap shim 运行共享状态，不加载 React 渲染器。
export const assistantUiAliases = [
  { find: /^react\/compiler-runtime$/, replacement: '@assistant-ui/tap/standalone-shim/compiler-runtime' },
  { find: /^react\/jsx-runtime$/, replacement: '@assistant-ui/tap/standalone-shim/jsx-runtime' },
  { find: /^react\/jsx-dev-runtime$/, replacement: '@assistant-ui/tap/standalone-shim/jsx-dev-runtime' },
  { find: /^react$/, replacement: '@assistant-ui/tap/standalone-shim' },
]
