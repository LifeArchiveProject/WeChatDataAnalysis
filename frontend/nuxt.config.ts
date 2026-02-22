// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },

  runtimeConfig: {
    public: {
      // Full API base, including `/api` when needed.
      // Example: `NUXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api`
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
    },
  },
  
  // 配置前端开发服务器端口
  devServer: {
    port: 3000
  },
  
  // 配置API代理，解决跨域问题
  nitro: {
    devProxy: {
      '/api': {
        // `h3` strips the matched prefix (`/api`) before calling the middleware,
        // so the proxy target must include `/api` to preserve backend routes.
        target: 'http://127.0.0.1:8000/api',
        changeOrigin: true
      }
    }
  },
  
  // 应用配置
  app: {
    head: {
      title: '微信数据库解密工具',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: '微信4.x版本数据库解密工具' }
      ],
      link: [
        { rel: 'icon', type: 'image/png', href: '/logo.png' },
        { rel: 'stylesheet', href: 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css' }
      ]
    }
  },
  
  // 模块配置
  modules: [
    '@nuxtjs/tailwindcss',
    '@pinia/nuxt'
  ],

  // 启用组件自动导入
  components: [
    { path: '~/components', pathPrefix: false }
  ],
  
  // Tailwind配置
  tailwindcss: {
    cssPath: ['~/assets/css/tailwind.css', { injectPosition: "first" }],
    configPath: 'tailwind.config',
    exposeConfig: {
      level: 2
    },
    config: {},
    viewer: true
  }
})
