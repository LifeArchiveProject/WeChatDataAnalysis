// 独立组件验收入口；只使用样例数据，不代替真实 Electron 或模型验收。
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss(), {
    name: 'synthetic-media-acceptance',
    configureServer(server) {
      // 头像样式验收复用仓库图片，不请求真实联系人资料。
      server.middlewares.use('/api/chat/avatar', (req, res) => {
        if (!req.url.includes('acceptance=logo')) { res.statusCode = 404; res.end(); return }
        res.writeHead(302, { Location: '/logo.png' }); res.end()
      })
      server.middlewares.use('/api/chat/media/image', (req, res) => {
        if (!req.url.includes('acceptance=diagram')) { res.statusCode = 404; res.end(); return }
        res.setHeader('Content-Type', 'image/svg+xml')
        res.end('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="#f2f8f4"/><text x="60" y="80" font-size="32" fill="#203a30">图片查看器验收 · 模拟排期</text><path d="M80 250H700" stroke="#168d59" stroke-width="8"/><g fill="#168d59"><circle cx="150" cy="250" r="20"/><circle cx="400" cy="250" r="20"/><circle cx="650" cy="250" r="20"/></g><g font-size="24"><text x="100" y="320">准备</text><text x="350" y="320">开发</text><text x="600" y="320">验收</text></g></svg>')
      })
    },
  }],
  resolve: { alias: { '~': fileURLToPath(new URL('.', import.meta.url)), '@': fileURLToPath(new URL('.', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 3050, strictPort: true },
})
