const path = require('node:path');
const { fileURLToPath } = require('node:url');

function isInternalRedirect(start, destination) {
  try {
    const from = new URL(start), to = new URL(destination);
    if (from.href === to.href) return false;
    if (['http:', 'https:'].includes(from.protocol)) return from.origin === to.origin;
    if (from.protocol !== 'file:' || to.protocol !== 'file:') return false;
    const relative = path.relative(path.dirname(fileURLToPath(from)), fileURLToPath(to));
    return !path.isAbsolute(relative) && relative !== '..' && !relative.startsWith(`..${path.sep}`);
  } catch { return false; }
}

// 首次使用页会中止初始导航；仅在同源目标实际完成加载后接受该跳转。
async function loadWithRedirect(win, url, timeoutMs = 5000) {
  const contents = win.webContents;
  let finished = false;
  let resolveFinished;
  let timer;
  const completion = new Promise(resolve => { resolveFinished = resolve; });
  const onFinish = () => {
    if (isInternalRedirect(url, contents.getURL())) {
      finished = true;
      resolveFinished(true);
    }
  };
  contents.on('did-finish-load', onFinish);
  try {
    await win.loadURL(url);
  } catch (error) {
    if (error?.code !== 'ERR_ABORTED' && error?.errno !== -3) throw error;
    if (finished) return;
    timer = setTimeout(() => resolveFinished(false), timeoutMs);
    if (!await completion) throw error;
  } finally {
    clearTimeout(timer);
    contents.removeListener('did-finish-load', onFinish);
  }
}

module.exports = { loadWithRedirect, isInternalRedirect };
