const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("wechatDesktop", {
  minimize: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximize: () => ipcRenderer.invoke("window:toggleMaximize"),
  close: () => ipcRenderer.invoke("window:close"),
  isMaximized: () => ipcRenderer.invoke("window:isMaximized"),

  getAutoLaunch: () => ipcRenderer.invoke("app:getAutoLaunch"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("app:setAutoLaunch", !!enabled),

  getCloseBehavior: () => ipcRenderer.invoke("app:getCloseBehavior"),
  setCloseBehavior: (behavior) => ipcRenderer.invoke("app:setCloseBehavior", String(behavior || "")),
});
