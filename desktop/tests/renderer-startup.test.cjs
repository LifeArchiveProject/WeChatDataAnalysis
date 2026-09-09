const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { loadWithRedirect, isInternalRedirect } = require('../src/renderer-startup.cjs');

test('首次使用页跳转完成后不重新加载首页', async () => {
  const contents = new EventEmitter();
  contents.getURL = () => 'http://127.0.0.1:3000/agreement?redirect=/';
  let calls = 0;
  const win = { webContents: contents, loadURL: async () => {
    calls++;
    setImmediate(() => contents.emit('did-finish-load'));
    throw Object.assign(new Error('aborted'), { code: 'ERR_ABORTED' });
  } };
  await loadWithRedirect(win, 'http://127.0.0.1:3000/', 100);
  assert.equal(calls, 1);
  assert.equal(contents.listenerCount('did-finish-load'), 0);
});

test('跳转先完成后收到中止事件也视为成功', async () => {
  const contents = new EventEmitter();
  contents.getURL = () => 'http://localhost:3000/agreement';
  await loadWithRedirect({ webContents: contents, loadURL: async () => {
    contents.emit('did-finish-load');
    throw Object.assign(new Error('aborted'), { errno: -3 });
  } }, 'http://localhost:3000/', 10);
});

test('未完成、跨源和连接错误不会伪装成加载成功', async () => {
  for (const destination of ['http://localhost:3000/', 'https://example.com/agreement']) {
    const contents = new EventEmitter();
    contents.getURL = () => destination;
    await assert.rejects(loadWithRedirect({ webContents: contents, loadURL: async () => {
      contents.emit('did-finish-load');
      throw Object.assign(new Error('aborted'), { code: 'ERR_ABORTED' });
    } }, 'http://localhost:3000/', 10), /aborted/);
    assert.equal(contents.listenerCount('did-finish-load'), 0);
  }
  const contents = new EventEmitter();
  await assert.rejects(loadWithRedirect({ webContents: contents, loadURL: async () => {
    throw new Error('ERR_CONNECTION_REFUSED');
  } }, 'http://localhost:3000/'), /ERR_CONNECTION_REFUSED/);
});

test('打包页面只接受同一目录内的跳转', () => {
  const url = file => pathToFileURL(path.resolve('app', file)).href;
  assert.equal(isInternalRedirect(url('ui/index.html'), url('ui/agreement/index.html')), true);
  assert.equal(isInternalRedirect(url('ui/index.html'), url('secret.html')), false);
  assert.equal(isInternalRedirect(url('ui/index.html'), 'about:blank'), false);
});
