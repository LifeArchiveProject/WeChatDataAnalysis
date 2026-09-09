import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'
import { assistantUiAliases } from './lib/assistant-ui-aliases'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: [
      ...assistantUiAliases,
      { find: '~', replacement: fileURLToPath(new URL('.', import.meta.url)) },
      { find: '@', replacement: fileURLToPath(new URL('.', import.meta.url)) },
    ]
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.test.js']
  }
})
