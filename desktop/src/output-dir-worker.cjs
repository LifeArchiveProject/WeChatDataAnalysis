const { parentPort, workerData } = require("worker_threads");
const { migrateOutputDirectory, rollbackOutputDirectoryChange } = require("./output-dir.cjs");

function serializeError(err) {
  return {
    message: err?.message || String(err),
    stack: err?.stack ? String(err.stack) : "",
  };
}

function createProgressPoster() {
  let lastStage = "";
  let lastPercent = -1;
  let lastSentAt = 0;

  return (progress) => {
    const stage = String(progress?.stage || "");
    const percent = Number(progress?.percent || 0);
    const now = Date.now();
    const shouldSend =
      stage !== lastStage ||
      percent >= 100 ||
      percent <= 0 ||
      percent >= lastPercent + 1 ||
      now - lastSentAt >= 120;

    if (!shouldSend) return;

    lastStage = stage;
    lastPercent = percent;
    lastSentAt = now;
    parentPort?.postMessage({ type: "progress", progress });
  };
}

async function main() {
  const action = String(workerData?.action || "migrate");
  const payload = workerData?.payload && typeof workerData.payload === "object" ? workerData.payload : {};

  if (action === "migrate") {
    const result = await migrateOutputDirectory({
      ...payload,
      onProgress: createProgressPoster(),
    });
    parentPort?.postMessage({ type: "result", result });
    return;
  }

  if (action === "rollback") {
    parentPort?.postMessage({
      type: "progress",
      progress: {
        stage: "rolling-back",
        message: "迁移失败，正在回滚 output 目录",
        percent: 99,
        bytesTransferred: 0,
        bytesTotal: 0,
        itemsTransferred: 0,
        itemsTotal: 0,
        currentFile: "",
      },
    });
    rollbackOutputDirectoryChange(payload);
    parentPort?.postMessage({ type: "result", result: { success: true } });
    return;
  }

  throw new Error(`不支持的 output 目录 worker 动作：${action}`);
}

main().catch((err) => {
  parentPort?.postMessage({ type: "error", error: serializeError(err) });
  process.exitCode = 1;
});
