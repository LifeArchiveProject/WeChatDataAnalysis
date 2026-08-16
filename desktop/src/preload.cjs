const { contextBridge, ipcRenderer } = require("electron");

function sendDebugLog(scope, message, details) {
  try {
    ipcRenderer.send("debug:log", {
      scope: String(scope || "renderer"),
      message: String(message || ""),
      details: details == null ? {} : details,
      url: typeof location !== "undefined" ? String(location.href || "") : "",
    });
  } catch {}
}

sendDebugLog("preload", "script-start", {
  userAgent: typeof navigator !== "undefined" ? String(navigator.userAgent || "") : "",
});

if (typeof document !== "undefined") {
  document.addEventListener("readystatechange", () => {
    sendDebugLog("preload", "document-readystate", {
      readyState: String(document.readyState || ""),
    });
  });
}

if (typeof window !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => {
    sendDebugLog("preload", "dom-content-loaded");
  });

  window.addEventListener("load", () => {
    sendDebugLog("preload", "window-load");
  });

  window.addEventListener("error", (event) => {
    sendDebugLog("preload", "window-error", {
      message: String(event?.message || ""),
      filename: String(event?.filename || ""),
      lineno: Number(event?.lineno || 0),
      colno: Number(event?.colno || 0),
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event?.reason;
    sendDebugLog("preload", "window-unhandledrejection", {
      reason:
        reason instanceof Error
          ? {
              name: String(reason.name || "Error"),
              message: String(reason.message || ""),
              stack: String(reason.stack || ""),
            }
          : String(reason || ""),
    });
  });

  window.setTimeout(() => {
    sendDebugLog("preload", "set-timeout-0");
  }, 0);
}

contextBridge.exposeInMainWorld("wechatDesktop", {
  // Marker used by the frontend to distinguish the Electron desktop shell from the pure web build.
  __brand: "WeChatDataAnalysisDesktop",
  platform: process.platform,
  windowControlsMode: "overlay",
  minimize: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximize: () => ipcRenderer.invoke("window:toggleMaximize"),
  close: () => ipcRenderer.invoke("window:close"),
  isMaximized: () => ipcRenderer.invoke("window:isMaximized"),
  setTitleBarTheme: (theme) => ipcRenderer.invoke("window:setTitleBarTheme", String(theme || "")),
  isDebugEnabled: () => ipcRenderer.invoke("app:isDebugEnabled"),
  logDebug: (scope, message, details = {}) => sendDebugLog(scope, message, details),

  getAutoLaunch: () => ipcRenderer.invoke("app:getAutoLaunch"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("app:setAutoLaunch", !!enabled),

  getCloseBehavior: () => ipcRenderer.invoke("app:getCloseBehavior"),
  setCloseBehavior: (behavior) => ipcRenderer.invoke("app:setCloseBehavior", String(behavior || "")),

  getBackendPort: () => ipcRenderer.invoke("backend:getPort"),
  setBackendPort: (port) => ipcRenderer.invoke("backend:setPort", Number(port)),
  getMcpLanAccess: () => ipcRenderer.invoke("backend:getMcpLanAccess"),
  setMcpLanAccess: (enabled) => ipcRenderer.invoke("backend:setMcpLanAccess", !!enabled),

  chooseDirectory: (options = {}) => ipcRenderer.invoke("dialog:chooseDirectory", options),
  chooseArchive: (options = {}) => ipcRenderer.invoke("dialog:chooseArchive", options),

  // Data/output folder helpers
  getOutputDirInfo: () => ipcRenderer.invoke("app:getOutputDirInfo"),
  getOutputDir: () => ipcRenderer.invoke("app:getOutputDir"),
  getOutputDirChangeProgress: () => ipcRenderer.invoke("app:getOutputDirChangeProgress"),
  setOutputDir: (dir) => ipcRenderer.invoke("app:setOutputDir", String(dir ?? "")),
  openOutputDir: () => ipcRenderer.invoke("app:openOutputDir"),

  // 年度总结分享出图：按屏幕矩形 + 目标倍率截取当前画面，存进 output/年度总结/
  captureRegion: (options = {}) =>
    ipcRenderer.invoke("app:captureRegion", {
      x: Number(options?.x) || 0,
      y: Number(options?.y) || 0,
      width: Number(options?.width) || 0,
      height: Number(options?.height) || 0,
      scale: Number(options?.scale) || 1,
      outWidth: Number(options?.outWidth) || 0,
      outHeight: Number(options?.outHeight) || 0,
      name: String(options?.name ?? ""),
    }),
  // 年度总结批量导出：begin 建临时目录 → 逐页 capture 进去 → finish 打成 zip 存到
  // output/年度总结/。中途报错或用户取消要调 abort 把临时目录清掉。
  wrappedBatchBegin: (options = {}) =>
    ipcRenderer.invoke("app:wrappedBatchBegin", {
      label: String(options?.label ?? ""),
    }),
  wrappedBatchCapture: (options = {}) =>
    ipcRenderer.invoke("app:wrappedBatchCapture", {
      batchId: String(options?.batchId ?? ""),
      index: Number(options?.index) || 0,
      name: String(options?.name ?? ""),
      x: Number(options?.x) || 0,
      y: Number(options?.y) || 0,
      width: Number(options?.width) || 0,
      height: Number(options?.height) || 0,
      scale: Number(options?.scale) || 1,
      outWidth: Number(options?.outWidth) || 0,
      outHeight: Number(options?.outHeight) || 0,
    }),
  wrappedBatchFinish: (options = {}) =>
    ipcRenderer.invoke("app:wrappedBatchFinish", {
      batchId: String(options?.batchId ?? ""),
      zipName: String(options?.zipName ?? ""),
    }),
  wrappedBatchAbort: (options = {}) =>
    ipcRenderer.invoke("app:wrappedBatchAbort", {
      batchId: String(options?.batchId ?? ""),
    }),

  openExternalUrl: (url) => ipcRenderer.invoke("app:openExternalUrl", String(url ?? "")),
  getAccountInfo: (account) => ipcRenderer.invoke("app:getAccountInfo", String(account || "")),
  deleteAccountData: (account) => ipcRenderer.invoke("app:deleteAccountData", String(account || "")),
  onOutputDirChangeProgress: (callback) => {
    const handler = (_event, progress) => callback(progress);
    ipcRenderer.on("app:outputDirChangeProgress", handler);
    return () => ipcRenderer.removeListener("app:outputDirChangeProgress", handler);
  },

  // Auto update
  getVersion: () => ipcRenderer.invoke("app:getVersion"),
  checkForUpdates: () => ipcRenderer.invoke("app:checkForUpdates"),
  downloadAndInstall: () => ipcRenderer.invoke("app:downloadAndInstall"),
  installUpdate: () => ipcRenderer.invoke("app:installUpdate"),
  ignoreUpdate: (version) => ipcRenderer.invoke("app:ignoreUpdate", String(version || "")),
  onDownloadProgress: (callback) => {
    const handler = (_event, progress) => callback(progress);
    ipcRenderer.on("app:downloadProgress", handler);
    return () => ipcRenderer.removeListener("app:downloadProgress", handler);
  },
  onUpdateAvailable: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on("app:updateAvailable", handler);
    return () => ipcRenderer.removeListener("app:updateAvailable", handler);
  },
  onUpdateDownloaded: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on("app:updateDownloaded", handler);
    return () => ipcRenderer.removeListener("app:updateDownloaded", handler);
  },
  onUpdateError: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on("app:updateError", handler);
    return () => ipcRenderer.removeListener("app:updateError", handler);
  },
});
