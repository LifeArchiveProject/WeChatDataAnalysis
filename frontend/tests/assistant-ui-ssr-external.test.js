import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// 这个契约靠注释守不住，必须由测试守：
// @assistant-ui/tap 的 react-shim 会 `import ... from "react"`，而 react 只是它的可选 peer，
// 前端用 lib/assistant-ui-aliases.js 把 react 指到 standalone-shim。一旦这些包在 SSR 里被判为
// external，就交给 Node 原生加载，Node 解析不到 react，/chat/[username] 直接 500。
//
// 实测坑：写成正则（/^@assistant-ui\//）会静默失效 —— Nuxt 把用户提供的 RegExp 序列化成字符串，
// 于是它变成字面量 glob、永远匹配不上；同一条配置里 Nuxt 自带的条目仍然是 RegExp。所以这里
// 必须钉住「包名字符串」这种写法。
const configSource = readFileSync(resolve(process.cwd(), 'nuxt.config.ts'), 'utf8')

function readNoExternalEntries() {
  const match = configSource.match(/ssr:\s*\{\s*noExternal:\s*\[([^\]]*)\]/)
  expect(match, 'nuxt.config.ts 里必须有 vite.ssr.noExternal').not.toBeNull()
  return match[1]
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

describe('assistant-ui 的 SSR 内联契约', () => {
  it('noExternal 覆盖四个 assistant-ui 包，且写成包名字符串', () => {
    const entries = readNoExternalEntries()
    for (const name of ['@assistant-ui/core', '@assistant-ui/store', '@assistant-ui/tap', '@assistant-ui/vue']) {
      expect(entries, `${name} 必须出现在 noExternal 里`).toContain(`'${name}'`)
    }
  })

  it('noExternal 不允许出现正则字面量（RegExp 会被序列化成字符串而静默失效）', () => {
    const entries = readNoExternalEntries()
    const regexLike = entries.filter((entry) => entry.startsWith('/') || entry.startsWith('('))
    expect(regexLike, `noExternal 里不能写正则: ${regexLike.join(', ')}`).toEqual([])
  })

  it('react 仍然通过别名指向 standalone-shim（配合 noExternal 一起生效）', () => {
    const aliases = readFileSync(resolve(process.cwd(), 'lib/assistant-ui-aliases.js'), 'utf8')
    expect(aliases).toContain("^react$")
    expect(aliases).toContain('@assistant-ui/tap/standalone-shim')
  })
})
