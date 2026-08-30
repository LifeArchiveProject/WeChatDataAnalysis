"use strict";

const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const {
  SendFlashMsg,
  createFlashFileset,
  stageFlashFileset,
  uploadFlashMainFiles,
} = require("./qq-flash-transfer.cjs");

const PROJECT_GROUP_IDS = ["1076587085", "1081108335"];
const GROUP_LIST_ENDPOINT = "https://qun.qq.com/cgi-bin/qun_mgr/get_group_list";
const NATIVE_SHA256 = "701240919DD7881195DCB3B99EE4F4ECACCB03A3F91349BF163313133ADC09F8";
const ISSUE_MODULES = new Set([
  "安装或启动",
  "微信与账号检测",
  "密钥获取或数据库解密",
  "聊天记录",
  "图片、视频或语音",
  "导入或导出",
  "其他",
]);

function resolveNativeAddonPath({ isPackaged = false, resourcesPath = "" } = {}) {
  const override = String(process.env.WDA_QQ_FEEDBACK_NATIVE_PATH || "").trim();
  const candidates = [
    override,
    isPackaged && resourcesPath
      ? path.join(resourcesPath, "qq-feedback", "win32-x64", "nt_helper.node")
      : "",
    path.join(__dirname, "..", "resources", "qq-feedback", "win32-x64", "nt_helper.node"),
  ].filter(Boolean);
  const hit = candidates.find((candidate) => fs.existsSync(candidate));
  if (!hit) throw new Error("QQ 反馈组件缺失，请重新安装桌面端。");
  return path.resolve(hit);
}

function readSourceRevision(repoRoot) {
  if (!repoRoot) return "";
  try {
    const result = spawnSync("git", ["rev-parse", "HEAD"], {
      cwd: repoRoot,
      encoding: "utf8",
      windowsHide: true,
      timeout: 3000,
    });
    const revision = String(result.stdout || "").trim();
    return /^[0-9a-f]{40}$/i.test(revision) ? revision : "";
  } catch {
    return "";
  }
}

function maskUin(value) {
  const uin = String(value || "").trim();
  if (uin.length <= 5) return "已登录";
  return `${uin.slice(0, 3)}***${uin.slice(-2)}`;
}

function computeBkn(skey) {
  let hash = 5381;
  for (const char of skey) hash += (hash << 5) + char.charCodeAt(0);
  return hash & 0x7fffffff;
}

async function detectProjectGroup(nt, pid, uin) {
  const probe = nt.probePtLoginPort(pid);
  if (!probe?.success || !probe.port) throw new Error(`无法检测 QQ 项目群：${probe?.msg || "pt_login 不可用"}`);
  const skeyResult = await nt.ptFetchSkey(probe.port, uin);
  const pskeyResult = await nt.ptFetchPskey(probe.port, uin, "qun.qq.com");
  if (!skeyResult?.success || !skeyResult.skey || !pskeyResult?.success || !pskeyResult.pskey) {
    throw new Error(`无法检测 QQ 项目群：${skeyResult?.msg || pskeyResult?.msg || "登录票据不可用"}`);
  }
  const cookie = [
    `uin=o${uin}`,
    `skey=${skeyResult.skey}`,
    `p_uin=o${uin}`,
    `p_skey=${pskeyResult.pskey}`,
  ].join("; ");
  const response = await fetch(GROUP_LIST_ENDPOINT, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
      cookie,
      referer: "https://qun.qq.com/member.html",
    },
    body: new URLSearchParams({ bkn: String(computeBkn(skeyResult.skey)) }),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`无法检测 QQ 项目群：HTTP ${response.status}`);
  const payload = await response.json();
  if (Number(payload?.ec ?? -1) !== 0) throw new Error(`无法检测 QQ 项目群：接口返回 ${payload?.ec ?? "未知错误"}`);
  const groups = ["create", "join", "manage"].flatMap((key) => Array.isArray(payload[key]) ? payload[key] : []);
  for (const groupId of PROJECT_GROUP_IDS) {
    const group = groups.find((item) => String(item?.gc ?? item?.group_code ?? item?.gid ?? "") === groupId);
    if (group) return { found: true, groupId, name: String(group.gn || group.group_name || groupId) };
  }
  return {
    found: false,
    groupId: "",
    name: "",
    reason: `未检测到已加入的 WeChatDataAnalysis 项目群，请先加入 ${PROJECT_GROUP_IDS.join(" 或 ")}。`,
  };
}

function newestLogUnder(root, acceptName = () => true) {
  if (!root || !fs.existsSync(root)) return "";
  let newest = null;
  const walk = (dir, depth) => {
    if (depth > 6) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath, depth + 1);
      } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".log") && acceptName(entry.name)) {
        try {
          const mtime = fs.statSync(fullPath).mtimeMs;
          if (!newest || mtime > newest.mtime) newest = { path: fullPath, mtime };
        } catch {}
      }
    }
  };
  walk(root, 0);
  return newest?.path || "";
}

function feedbackLogPaths(outputDir, userDataDir) {
  const candidates = [
    newestLogUnder(path.join(outputDir, "logs"), (name) => /_wechat_tool\.log$/i.test(name)),
    path.join(userDataDir, "desktop-main.log"),
    path.join(userDataDir, "backend-stdio.log"),
    path.join(userDataDir, "renderer-console.log"),
    path.join(userDataDir, "renderer-debug.log"),
  ];
  const seen = new Set();
  return candidates.filter((candidate) => {
    if (!candidate || !fs.existsSync(candidate)) return false;
    const resolved = path.resolve(candidate).toLowerCase();
    if (seen.has(resolved)) return false;
    seen.add(resolved);
    try {
      return fs.statSync(candidate).isFile() && fs.statSync(candidate).size > 0;
    } catch {
      return false;
    }
  });
}

function renderIssueMarkdown({ feedback, environment, logNames = [] }) {
  const screenshotLines = feedback.screenshotNames?.length
    ? [feedback.screenshots || "已附加剪贴板截图。", ...feedback.screenshotNames.map((name) => `- ${name}`)]
    : [feedback.screenshots || "未提供。"];
  return [
    `# [Bug] ${feedback.title}`,
    "",
    "感谢反馈。请上传问题发生前后至少 1 分钟的完整日志，不要只填写最后一行错误。",
    "",
    "默认日志位置：",
    "- Windows：`%APPDATA%\\wechat-data-analysis-desktop\\output\\logs\\YYYY\\MM\\DD\\DD_wechat_tool.log`",
    "- macOS：`~/Library/Application Support/wechat-data-analysis-desktop/output/logs/YYYY/MM/DD/DD_wechat_tool.log`",
    "- 也可在应用内通过“设置 → 桌面行为 → 日志文件 → 打开日志”定位。",
    "",
    "上传前请删除数据库密钥、聊天内容及其他敏感信息；不要上传微信数据库。",
    "",
    "## 运行方式",
    environment.runMode,
    "",
    "## 安装包版本或源码提交 Hash",
    environment.versionReference,
    "",
    "## 系统与架构",
    environment.system,
    "",
    "## 微信版本",
    feedback.wechatVersion,
    "",
    "## 出错功能",
    feedback.module,
    "",
    "## 问题发生时间",
    feedback.occurredAt,
    "",
    "## 问题描述",
    feedback.description,
    "",
    "## 复现步骤",
    feedback.steps,
    "",
    "## 预期结果",
    feedback.expected,
    "",
    "## 实际结果",
    feedback.actual,
    "",
    "## 完整日志",
    "以下日志已随 QQ 闪传附加：",
    ...logNames.map((name) => `- ${name}`),
    "",
    "## 截图或录屏",
    ...screenshotLines,
    "",
    "## 提交确认",
    "- [x] 我已搜索现有 Issue，未发现相同问题。",
    "- [x] 我已上传问题对应时段的完整日志。",
    "- [x] 我没有上传数据库、密钥或未脱敏的聊天内容。",
    "",
  ].join("\n");
}

function createFeedbackBundle({ feedback, environment, outputDir, userDataDir }) {
  if (!outputDir || !userDataDir) throw new Error("无法定位应用日志目录。");
  const logs = feedbackLogPaths(outputDir, userDataDir);
  if (logs.length === 0) throw new Error("未找到可发送的应用日志，请先复现问题后再试。");

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const folder = path.join(outputDir, "feedback", `bug-${stamp}`);
  fs.mkdirSync(folder, { recursive: true });
  const copiedLogs = logs.map((source, index) => {
    const destination = path.join(folder, `${String(index + 1).padStart(2, "0")}-${path.basename(source)}`);
    fs.copyFileSync(source, destination);
    return destination;
  });
  const copiedScreenshots = feedback.screenshotFiles.map((item, index) => {
    const destination = path.join(folder, `screenshot-${String(index + 1).padStart(2, "0")}.${item.extension}`);
    fs.writeFileSync(destination, item.bytes);
    return destination;
  });
  const issuePath = path.join(folder, "issue.md");
  fs.writeFileSync(
    issuePath,
    renderIssueMarkdown({
      feedback: { ...feedback, screenshotNames: copiedScreenshots.map((file) => path.basename(file)) },
      environment,
      logNames: copiedLogs.map((file) => path.basename(file)),
    }),
    "utf8",
  );
  return { folder, files: [issuePath, ...copiedLogs, ...copiedScreenshots] };
}

function normalizeFeedbackInput(rawInput) {
  const input = rawInput && typeof rawInput === "object" ? rawInput : {};
  const required = (key, label, maxLength = 20_000) => {
    const value = String(input[key] || "").trim();
    if (!value) throw new Error(`请填写${label}。`);
    if (value.length > maxLength) throw new Error(`${label}内容过长。`);
    return value;
  };
  const title = required("title", "问题标题", 200);
  const module = required("module", "出错功能", 50);
  if (!ISSUE_MODULES.has(module)) throw new Error("请选择有效的出错功能。");
  const confirmations = input.confirmations && typeof input.confirmations === "object"
    ? input.confirmations
    : {};
  if (
    confirmations.duplicateSearch !== true
    || confirmations.logsAttached !== true
    || confirmations.sensitiveDataRemoved !== true
  ) {
    throw new Error("请完成全部提交确认。");
  }
  const screenshotFiles = Array.isArray(input.screenshotFiles) ? input.screenshotFiles : [];
  if (screenshotFiles.length > 5) throw new Error("最多粘贴 5 张截图。");
  let screenshotBytes = 0;
  const normalizedScreenshots = screenshotFiles.map((item) => {
    const mimeType = String(item?.mimeType || "").toLowerCase();
    const extension = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" }[mimeType];
    if (!extension) throw new Error("截图仅支持 PNG、JPEG 或 WebP。");
    if (!(item?.bytes instanceof Uint8Array) && !(item?.bytes instanceof ArrayBuffer)) {
      throw new Error("截图数据格式无效。");
    }
    const bytes = Buffer.from(item.bytes instanceof ArrayBuffer ? new Uint8Array(item.bytes) : item.bytes);
    if (bytes.length === 0 || bytes.length > 10 * 1024 * 1024) throw new Error("单张截图必须小于 10 MB。");
    const validSignature =
      (extension === "png" && bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])))
      || (extension === "jpg" && bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff)
      || (extension === "webp" && bytes.length >= 12 && bytes.toString("ascii", 0, 4) === "RIFF" && bytes.toString("ascii", 8, 12) === "WEBP");
    if (!validSignature) throw new Error("截图文件内容与图片类型不匹配。");
    screenshotBytes += bytes.length;
    return { mimeType, extension, bytes };
  });
  if (screenshotBytes > 30 * 1024 * 1024) throw new Error("截图总大小不能超过 30 MB。");
  return {
    title,
    wechatVersion: required("wechatVersion", "微信版本", 100),
    module,
    occurredAt: required("occurredAt", "问题发生时间", 200),
    description: required("description", "问题描述"),
    steps: required("steps", "复现步骤"),
    expected: required("expected", "预期结果"),
    actual: required("actual", "实际结果"),
    screenshots: String(input.screenshots || "").trim().slice(0, 20_000),
    screenshotFiles: normalizedScreenshots,
  };
}

function createQqFeedbackService({
  appVersion = "",
  isPackaged = false,
  resourcesPath = "",
  repoRoot = "",
  logPath = "",
  userDataDir = "",
  getOutputDir = () => "",
  platform = process.platform,
  arch = process.arch,
  requireNative = require,
} = {}) {
  let native = null;
  let injectedKey = "";
  let injectionPromise = null;
  let sending = false;

  const environment = () => {
    const revision = isPackaged ? "" : readSourceRevision(repoRoot);
    return {
      runMode: isPackaged ? "GitHub Release 安装包" : "源码运行",
      versionReference: revision || String(appVersion || "未知"),
      appVersion: String(appVersion || "未知"),
      system: `${os.type()} ${os.release()} ${arch}`,
      occurredAt: new Date().toISOString(),
    };
  };

  const loadNative = () => {
    if (native) return native;
    if (platform !== "win32" || arch !== "x64") {
      throw new Error("QQ 群反馈目前仅支持 Windows x64 桌面端。");
    }
    const nativePath = resolveNativeAddonPath({ isPackaged, resourcesPath });
    const digest = crypto.createHash("sha256").update(fs.readFileSync(nativePath)).digest("hex").toUpperCase();
    if (digest !== NATIVE_SHA256) throw new Error("QQ 反馈组件完整性校验失败。");

    const loaded = requireNative(nativePath);
    const required = [
      "getInitStatus",
      "getQqProcesses",
      "probeQqLoginInfo",
      "probePtLoginPort",
      "ptFetchSkey",
      "ptFetchPskey",
      "injectAndGetStatusEmbedded",
      "sendOidbPacket",
    ];
    if (required.some((name) => typeof loaded?.[name] !== "function")) {
      throw new Error("QQ 反馈组件接口不完整。");
    }
    if (Number(loaded.getInitStatus()) !== 0) throw new Error("QQ 反馈组件初始化失败。");
    if (logPath && typeof loaded.setLogPath === "function") {
      fs.mkdirSync(path.dirname(logPath), { recursive: true });
      loaded.setLogPath(logPath);
    }
    native = loaded;
    return native;
  };

  const resolveLoggedInQq = () => {
    const nt = loadNative();
    const candidates = nt
      .getQqProcesses()
      .map((pid) => {
        try {
          return { pid: Number(pid), info: nt.probeQqLoginInfo(Number(pid)) };
        } catch {
          return null;
        }
      })
      .filter((item) => item?.info?.loggedIn && String(item.info.uin || "").trim());
    if (candidates.length === 0) throw new Error("未检测到已登录的 QQ，请先打开并登录 QQ。");
    if (candidates.length > 1) throw new Error("检测到多个已登录 QQ，无法安全确定发送账号。");
    return candidates[0];
  };

  const getStatus = () => {
    try {
      const { pid, info } = resolveLoggedInQq();
      return { supported: true, online: true, pid, accountHint: maskUin(info.uin) };
    } catch (error) {
      return {
        supported: platform === "win32" && arch === "x64",
        online: false,
        pid: null,
        accountHint: "",
        reason: error?.message || String(error),
      };
    }
  };

  const ensureInjected = async (pid, uin) => {
    const key = `${pid}:${uin}`;
    if (injectedKey === key) return;
    if (!injectionPromise) {
      // ponytail: process-local cache only; persist it if desktop restarts prove re-injection unsafe.
      injectionPromise = Promise.resolve(loadNative().injectAndGetStatusEmbedded(pid, uin))
        .then((status) => {
          if (!status?.loggedIn || String(status.uin || "") !== String(uin)) {
            throw new Error("QQ Hook 未绑定到检测到的登录账号。");
          }
          injectedKey = key;
        })
        .finally(() => {
          injectionPromise = null;
        });
    }
    await injectionPromise;
  };

  const send = async (rawInput) => {
    const feedback = normalizeFeedbackInput(rawInput);
    if (sending) throw new Error("问题反馈正在发送，请稍候。");

    sending = true;
    try {
      const nt = loadNative();
      const { pid, info } = resolveLoggedInQq();
      const projectGroup = await detectProjectGroup(nt, pid, String(info.uin));
      if (!projectGroup.found) throw new Error(projectGroup.reason);
      await ensureInjected(pid, String(info.uin));

      const env = environment();
      if (env.runMode === "源码运行" && !/^[0-9a-f]{40}$/i.test(env.versionReference)) {
        throw new Error("无法读取当前源码提交 Hash，暂不能发送反馈。");
      }
      const bundle = createFeedbackBundle({
        feedback,
        environment: env,
        outputDir: String(getOutputDir() || ""),
        userDataDir,
      });
      const pending = await createFlashFileset(
        nt,
        pid,
        bundle.files.map((file) => ({ path: file })),
        {
          name: `[Bug] ${feedback.title}`,
          uploader: {
            uin: String(info.uin),
            nickname: String(info.nickName || ""),
            uid: "",
          },
        },
      );
      await stageFlashFileset(nt, pid, pending);
      await SendFlashMsg.invoke(nt, pid, {
        filesetUuid: pending.filesetUuid,
        groupId: Number(projectGroup.groupId),
      });
      try {
        await uploadFlashMainFiles(nt, pid, pending);
      } catch (error) {
        throw new Error(`群消息已创建，但日志上传失败：${error?.message || String(error)}`);
      }
      return {
        status: "uploaded",
        groupId: projectGroup.groupId,
        fileCount: bundle.files.length,
        folder: bundle.folder,
      };
    } finally {
      sending = false;
    }
  };

  return {
    getInfo: async () => {
      const logs = feedbackLogPaths(String(getOutputDir() || ""), userDataDir);
      const qq = getStatus();
      let projectGroup = { found: false, groupId: "", name: "", reason: qq.reason || "未检测到已登录 QQ。" };
      if (qq.online) {
        try {
          const { pid, info } = resolveLoggedInQq();
          projectGroup = await detectProjectGroup(loadNative(), pid, String(info.uin));
        } catch (error) {
          projectGroup = { found: false, groupId: "", name: "", reason: error?.message || String(error) };
        }
      }
      return {
        environment: environment(),
        qq,
        projectGroup,
        logs: { count: logs.length, names: logs.map((file) => path.basename(file)) },
      };
    },
    getStatus,
    send,
  };
}

function runSelfTest() {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "wda-qq-feedback-"));
  try {
    const outputDir = path.join(temp, "output");
    const userDataDir = path.join(temp, "user-data");
    fs.mkdirSync(path.join(outputDir, "logs"), { recursive: true });
    fs.mkdirSync(userDataDir, { recursive: true });
    fs.writeFileSync(path.join(outputDir, "logs", "29_wechat_tool.log"), "backend log\n");
    fs.writeFileSync(path.join(userDataDir, "desktop-main.log"), "desktop log\n");
    const fullInput = {
      title: "测试标题",
      wechatVersion: "4.1.13.12",
      module: "聊天记录",
      occurredAt: "2026-08-29 20:00（UTC+8）",
      description: "打开聊天后显示异常。",
      steps: "1. 打开聊天\n2. 点击消息",
      expected: "正常显示。",
      actual: "显示错误文本。",
      screenshots: "未提供截图。",
      screenshotFiles: [{
        mimeType: "image/png",
        bytes: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]),
      }],
      confirmations: {
        duplicateSearch: true,
        logsAttached: true,
        sensitiveDataRemoved: true,
      },
    };
    const bundle = createFeedbackBundle({
      feedback: normalizeFeedbackInput(fullInput),
      environment: {
        runMode: "源码运行",
        versionReference: "a".repeat(40),
        system: "Windows_NT test x64",
        occurredAt: "2026-08-29T00:00:00.000Z",
      },
      outputDir,
      userDataDir,
    });
    if (bundle.files.length !== 4) throw new Error("feedback bundle did not include issue.md, logs and screenshot");
    const markdown = fs.readFileSync(bundle.files[0], "utf8");
    const headings = [
      "运行方式", "安装包版本或源码提交 Hash", "系统与架构", "微信版本", "出错功能",
      "问题发生时间", "问题描述", "复现步骤", "预期结果", "实际结果", "完整日志", "截图或录屏", "提交确认",
    ];
    if (headings.some((heading) => !markdown.includes(`## ${heading}`)) || (markdown.match(/- \[x\]/g) || []).length !== 3) {
      throw new Error("feedback markdown is incomplete");
    }
    for (const invalid of [
      { ...fullInput, steps: "" },
      { ...fullInput, confirmations: { ...fullInput.confirmations, duplicateSearch: "true" } },
    ]) {
      let rejected = false;
      try { normalizeFeedbackInput(invalid); } catch { rejected = true; }
      if (!rejected) throw new Error("invalid feedback input was accepted");
    }
    process.stdout.write("qq-feedback self-test: ok\n");
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

if (require.main === module && process.argv.includes("--self-test")) runSelfTest();

module.exports = {
  NATIVE_SHA256,
  PROJECT_GROUP_IDS,
  createFeedbackBundle,
  createQqFeedbackService,
  renderIssueMarkdown,
  resolveNativeAddonPath,
  runSelfTest,
};
