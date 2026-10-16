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
async function loadWithRedirect(win, url, timeoutMs = 5000, navigationTimeoutMs = 60000) {
  const contents = win.webContents;
  let finished = false;
  let disposed = false;
  let resolveFinished;
  let timer;
  let deadlineTimer;
  const completion = new Promise(resolve => { resolveFinished = resolve; });
  const onFinish = () => {
    if (isInternalRedirect(url, contents.getURL())) {
      finished = true;
      resolveFinished(true);
    }
  };
  contents.on('did-finish-load', onFinish);
  const navigate = async () => {
    try {
      await win.loadURL(url);
    } catch (error) {
      if (disposed) throw error;
      if (error?.code !== 'ERR_ABORTED' && error?.errno !== -3) throw error;
      if (finished) return;
      timer = setTimeout(() => resolveFinished(false), timeoutMs);
      if (!await completion) throw error;
    }
  };
  const deadline = new Promise((_, reject) => {
    deadlineTimer = setTimeout(() => {
      // loadURL 自身可能一直不返回；重试循环外的计时不能中断这种挂起。
      const error = Object.assign(new Error(`页面加载超时：${url}`), { code: 'ERR_NAVIGATION_TIMEOUT' });
      reject(error);
      try { if (!contents.isDestroyed?.()) contents.stop?.(); } catch {}
    }, Math.max(1, navigationTimeoutMs));
  });
  try {
    await Promise.race([navigate(), deadline]);
  } finally {
    disposed = true;
    clearTimeout(deadlineTimer);
    clearTimeout(timer);
    resolveFinished(false);
    contents.removeListener('did-finish-load', onFinish);
  }
}

function resolveDesktopUiUrl({ startUrl, backendUrl, isPackaged, staticUi }) {
  // 静态模式跟随已经就绪的后端端口，不继承失效的开发服务器地址。
  if (staticUi) return backendUrl;
  const explicit = String(startUrl || '').trim();
  return explicit || (isPackaged ? backendUrl : 'http://localhost:3000');
}

module.exports = { loadWithRedirect, isInternalRedirect, resolveDesktopUiUrl };
