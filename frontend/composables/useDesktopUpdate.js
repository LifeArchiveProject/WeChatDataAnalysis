let listenersInitialized = false;
let removeListeners = [];

const getDesktopApi = () => {
  if (!process.client) return null;
  if (typeof window === "undefined") return null;
  return window?.wechatDesktop || null;
};

const isDesktopShell = () => !!getDesktopApi();

const isUpdaterSupported = () => {
  const api = getDesktopApi();
  if (!api) return false;

  // If the bridge exposes a brand marker, ensure it's our Electron shell.
  if (api.__brand && api.__brand !== "WeChatDataAnalysisDesktop") return false;

  // Require updater IPC to avoid showing update UI in the pure web build.
  return (
    typeof api.getVersion === "function" &&
    typeof api.checkForUpdates === "function" &&
    typeof api.downloadAndInstall === "function"
  );
};

export const useDesktopUpdate = () => {
  const info = useState("desktopUpdate.info", () => null);
  const open = useState("desktopUpdate.open", () => false);
  const isDownloading = useState("desktopUpdate.isDownloading", () => false);
  const readyToInstall = useState("desktopUpdate.readyToInstall", () => false);
  const progress = useState("desktopUpdate.progress", () => ({ percent: 0 }));
  const error = useState("desktopUpdate.error", () => "");
  const currentVersion = useState("desktopUpdate.currentVersion", () => "");

  const manualCheckLoading = useState("desktopUpdate.manualCheckLoading", () => false);
  const lastCheckMessage = useState("desktopUpdate.lastCheckMessage", () => "");
  const lastCheckAt = useState("desktopUpdate.lastCheckAt", () => 0);

  const setUpdateInfo = (payload) => {
    if (!payload) return;
    const version = String(payload?.version || "").trim();
    const releaseNotes = String(payload?.releaseNotes || "");
    if (!version) return;
    info.value = { version, releaseNotes };
    readyToInstall.value = false;
  };

  const dismiss = () => {
    open.value = false;
  };

  const refreshVersion = async () => {
    if (!isUpdaterSupported()) return "";
    try {
      const v = await getDesktopApi()?.getVersion?.();
      currentVersion.value = String(v || "");
      return currentVersion.value;
    } catch {
      return currentVersion.value || "";
    }
  };

  const initListeners = async () => {
    if (!isUpdaterSupported()) return;
    if (listenersInitialized) return;
    listenersInitialized = true;

    await refreshVersion();

    const unsubs = [];

    const unUpdate = window.wechatDesktop?.onUpdateAvailable?.((payload) => {
      error.value = "";
      isDownloading.value = false;
      readyToInstall.value = false;
      progress.value = { percent: 0 };
      setUpdateInfo(payload);
      open.value = true;
    });
    if (typeof unUpdate === "function") unsubs.push(unUpdate);

    const unProgress = window.wechatDesktop?.onDownloadProgress?.((p) => {
      progress.value = p || { percent: 0 };
      const percent = Number(progress.value?.percent || 0);
      if (Number.isFinite(percent) && percent > 0) {
        isDownloading.value = true;
      }
    });
    if (typeof unProgress === "function") unsubs.push(unProgress);

    const unDownloaded = window.wechatDesktop?.onUpdateDownloaded?.((payload) => {
      // Download finished. Keep the dialog open and let the user decide when to install.
      setUpdateInfo(payload || info.value || {});
      isDownloading.value = false;
      readyToInstall.value = true;
      progress.value = { ...(progress.value || {}), percent: 100 };
      open.value = true;
    });
    if (typeof unDownloaded === "function") unsubs.push(unDownloaded);

    const unError = window.wechatDesktop?.onUpdateError?.((payload) => {
      const msg = String(payload?.message || "");
      if (msg) error.value = msg;
      isDownloading.value = false;
      readyToInstall.value = false;
    });
    if (typeof unError === "function") unsubs.push(unError);

    removeListeners = unsubs;
  };

  const startUpdate = async () => {
    if (!isUpdaterSupported()) return;

    error.value = "";
    isDownloading.value = true;
    readyToInstall.value = false;
    progress.value = { percent: 0 };

    try {
      await getDesktopApi()?.downloadAndInstall?.();
    } catch (e) {
      const msg = e?.message || String(e);
      error.value = msg;
      isDownloading.value = false;
    }
  };

  const installUpdate = async () => {
    if (!isUpdaterSupported()) return;
    if (!getDesktopApi()?.installUpdate) return;

    error.value = "";
    try {
      await getDesktopApi()?.installUpdate?.();
    } catch (e) {
      const msg = e?.message || String(e);
      error.value = msg;
    }
  };

  const ignore = async () => {
    if (!isUpdaterSupported()) return;
    const version = String(info.value?.version || "").trim();
    if (!version) return;

    try {
      await getDesktopApi()?.ignoreUpdate?.(version);
    } catch (e) {
      const msg = e?.message || String(e);
      error.value = msg;
    } finally {
      // Hide the dialog locally; startup auto-check will also respect the ignore.
      open.value = false;
      info.value = null;
    }
  };

  const manualCheck = async () => {
    if (!isDesktopShell()) {
      lastCheckMessage.value = "仅桌面端可用。";
      return { hasUpdate: false };
    }
    if (!isUpdaterSupported()) {
      lastCheckMessage.value = "当前桌面端版本不支持自动更新。";
      return { hasUpdate: false };
    }

    manualCheckLoading.value = true;
    error.value = "";
    lastCheckMessage.value = "";

    try {
      await refreshVersion();

      const res = await getDesktopApi()?.checkForUpdates?.();
      lastCheckAt.value = Date.now();

      if (res?.enabled === false) {
        lastCheckMessage.value = "自动更新已禁用（仅打包版本可用）。";
        return res;
      }

      if (res?.error) {
        lastCheckMessage.value = `检查更新失败：${String(res.error)}`;
        return res;
      }

      if (res?.hasUpdate && res?.version) {
        setUpdateInfo({ version: res.version, releaseNotes: res.releaseNotes || "" });
        open.value = true;
        lastCheckMessage.value = `发现新版本：${String(res.version)}`;
        return res;
      }

      lastCheckMessage.value = "当前已是最新版本。";
      return res;
    } catch (e) {
      const msg = e?.message || String(e);
      lastCheckMessage.value = `检查更新失败：${msg}`;
      return { hasUpdate: false, error: msg };
    } finally {
      manualCheckLoading.value = false;
    }
  };

  const cleanup = () => {
    try {
      for (const fn of removeListeners) fn?.();
    } catch {}
    removeListeners = [];
    listenersInitialized = false;
  };

  return {
    info,
    open,
    isDownloading,
    readyToInstall,
    progress,
    error,
    currentVersion,
    manualCheckLoading,
    lastCheckMessage,
    lastCheckAt,
    initListeners,
    refreshVersion,
    manualCheck,
    startUpdate,
    installUpdate,
    ignore,
    dismiss,
    cleanup,
  };
};
