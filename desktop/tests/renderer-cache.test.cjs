const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/main.cjs'), 'utf8');
const cacheCode = source.slice(source.indexOf('async function refreshRendererCacheForPackagedUi()'), source.indexOf('function parseEnvBool('));
function setup({ staticUi = '1', fail = false, previous = 'old' } = {}) {
  const calls = [], settings = { lastSeenUiBuildId: previous };
  const context = { app: { isPackaged: false }, process: { env: { WECHAT_TOOL_STATIC_UI: staticUi } },
    readPackagedUiBuildId: () => 'new', loadDesktopSettings: () => settings, desktopSettings: settings,
    persistDesktopSettings: () => calls.push('persist'), logMain: () => {},
    session: { defaultSession: { clearCache: async () => { calls.push('cache'); if (fail) throw new Error('locked'); },
      clearStorageData: async options => calls.push(options.storages) } } };
  vm.createContext(context); vm.runInContext(cacheCode, context);
  return { calls, settings, run: () => context.refreshRendererCacheForPackagedUi() };
}
test('静态开发重建后清理 HTTP 缓存，保留草稿和账号存储', async () => {
  const state = setup(); await state.run();
  assert.deepEqual(JSON.parse(JSON.stringify(state.calls)), ['cache', ['serviceworkers'], 'persist']);
  assert.equal(state.settings.lastSeenUiBuildId, 'new');
});
test('缓存清理失败时保留旧版本标记，下次启动仍可重试', async () => {
  const state = setup({ fail: true }); await state.run();
  assert.deepEqual(state.calls, ['cache']); assert.equal(state.settings.lastSeenUiBuildId, 'old');
});
test('相同构建和普通开发服务器不触发缓存清理', async () => {
  for (const options of [{ previous: 'new' }, { staticUi: '' }]) {
    const state = setup(options); await state.run(); assert.deepEqual(state.calls, []);
  }
});
