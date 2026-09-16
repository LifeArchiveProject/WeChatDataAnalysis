import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { parse } from '@vue/compiler-sfc'

const source = readFileSync(new URL('../pages/index.vue', import.meta.url), 'utf8')
const script = parse(source).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
const settings = readFileSync(new URL('../lib/desktop-settings.js', import.meta.url), 'utf8')
  .replace(/^export /gm, '')

const runStartup = async ({ stored = null, accounts = ['ready-account'], accepted = true, fails = false } = {}) => {
  let mounted
  let contextAvailable = true
  const paths = []
  const warnings = []
  const router = { replace: async path => paths.push(path) }
  const getRouter = () => {
    if (!contextAvailable) throw new Error('Nuxt 上下文不可用')
    return router
  }
  vm.runInNewContext(`${settings}\n${script}`, {
    process: { client: true }, window: {},
    localStorage: { getItem: () => stored },
    ref: value => ({ value }),
    onMounted: callback => { mounted = callback },
    useRouter: getRouter,
    navigateTo: path => getRouter().replace(path),
    isFirstUseAgreementAccepted: () => accepted,
    console: { warn: (...args) => warnings.push(args) },
    useApi: () => ({ listChatAccounts: async () => {
      await Promise.resolve()
      // 模拟异步请求结束后，组合式函数不再能获取组件上下文。
      contextAvailable = false
      if (fails) throw new Error('账号服务暂时不可用')
      return { accounts }
    } }),
  })
  await mounted()
  return { paths, warnings }
}

test('默认开启时，账号请求结束后仍能跳转到回看页', async () => {
  const result = await runStartup()
  assert.deepEqual(result.paths, ['/chat'])
  assert.equal(result.warnings.length, 0)
})

test('手动关闭、没有账号或未同意协议时不自动跳转', async () => {
  for (const options of [{ stored: 'false' }, { accounts: [] }, { accepted: false }]) {
    assert.deepEqual((await runStartup(options)).paths, [])
  }
})

test('账号请求失败时留在首页并记录原因', async () => {
  const result = await runStartup({ fails: true })
  assert.deepEqual(result.paths, [])
  assert.equal(result.warnings.length, 1)
})
