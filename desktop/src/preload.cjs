const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("wechatDesktop", {
  // Marker used by the frontend to distinguish the Electron desktop shell from the pure web build.
  __brand: "WeChatDataAnalysisDesktop",
  minimize: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximize: () => ipcRenderer.invoke("window:toggleMaximize"),
  close: () => ipcRenderer.invoke("window:close"),
  isMaximized: () => ipcRenderer.invoke("window:isMaximized"),

  getAutoLaunch: () => ipcRenderer.invoke("app:getAutoLaunch"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("app:setAutoLaunch", !!enabled),

  getCloseBehavior: () => ipcRenderer.invoke("app:getCloseBehavior"),
  setCloseBehavior: (behavior) => ipcRenderer.invoke("app:setCloseBehavior", String(behavior || "")),

  getBackendPort: () => ipcRenderer.invoke("backend:getPort"),
  setBackendPort: (port) => ipcRenderer.invoke("backend:setPort", Number(port)),

  chooseDirectory: (options = {}) => ipcRenderer.invoke("dialog:chooseDirectory", options),

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
