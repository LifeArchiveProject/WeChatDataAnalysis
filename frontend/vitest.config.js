import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: [
      { find: '~', replacement: fileURLToPath(new URL('.', import.meta.url)) },
      { find: '@', replacement: fileURLToPath(new URL('.', import.meta.url)) },
    ]
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.test.js'],
    server: {
      deps: {
        inline: ['@assistant-ui/core', '@assistant-ui/store', '@assistant-ui/tap', '@assistant-ui/vue']
      }
    }
  }
})
