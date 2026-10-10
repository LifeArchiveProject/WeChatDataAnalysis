"use strict";

// 把 electron-builder 的 Linux 解包产物（dist/linux-unpacked）打成「一键安装」素材：
//
//   dist/WeChatDataAnalysis-<version>-linux-x86_64.tar.gz   负载
//   dist/install.sh                                         一键安装/卸载脚本（内嵌负载 SHA-256）
//   dist/SHA256SUMS.txt                                     给人工核对用
//
// 刻意不做 AppImage / deb：作者的分发形态只有 Windows 安装包与 macOS dmg，
// Linux 走「用户级、免 root 的 tar.gz + install.sh」这条路。

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const desktopRoot = path.resolve(__dirname, "..");
const DEFAULT_PAYLOAD_DIR = path.join(desktopRoot, "dist", "linux-unpacked");
const DEFAULT_OUTPUT_DIR = path.join(desktopRoot, "dist");
const TEMPLATE_PATH = path.join(__dirname, "linux-installer-template.sh");
const ICON_SOURCE = path.join(desktopRoot, "src", "icon.png");
const ICON_NAME = "wechat-data-analysis.png";
const ARCH = "x86_64";

function readPackageMetadata() {
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8")
  );
  const productName = String(packageJson.build?.productName || packageJson.name || "").trim();
  const version = String(packageJson.version || "").trim();
  const executableName = String(packageJson.build?.linux?.executableName || "").trim();
  if (!productName || !version || !executableName) {
    throw new Error(
      "package.json must declare build.productName, version and build.linux.executableName"
    );
  }
  return { productName, version, executableName };
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function runTarCreate(payloadDir, archivePath) {
  // 用系统 tar 而不是 Node 第三方库：保留权限位/符号链接，且 CI 与本机一致。
  const result = spawnSync("tar", ["-czf", archivePath, "-C", payloadDir, "."], {
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if ((result.status ?? 1) !== 0) {
    throw new Error(`tar failed with exit code ${result.status}`);
  }
}

function renderInstallerTemplate({ productName, version, executableName, payloadName, sha256 }) {
  const template = fs.readFileSync(TEMPLATE_PATH, "utf8");
  const replacements = {
    "@@PRODUCT@@": productName,
    "@@VERSION@@": version,
    "@@ARCH@@": ARCH,
    "@@EXECUTABLE@@": executableName,
    "@@PAYLOAD@@": payloadName,
    "@@SHA256@@": sha256,
  };
  let rendered = template;
  for (const [token, value] of Object.entries(replacements)) {
    rendered = rendered.split(token).join(value);
  }
  const leftover = rendered.match(/@@[A-Z_]+@@/);
  if (leftover) throw new Error(`installer template still contains ${leftover[0]}`);
  return rendered;
}

function buildLinuxInstaller({
  payloadDir = DEFAULT_PAYLOAD_DIR,
  outputDir = DEFAULT_OUTPUT_DIR,
  metadata = readPackageMetadata(),
  skipArchive = false,
} = {}) {
  const { productName, version, executableName } = metadata;
  const payloadStat = (() => {
    try {
      return fs.statSync(payloadDir);
    } catch {
      throw new Error(`Linux payload directory not found: ${payloadDir}`);
    }
  })();
  if (!payloadStat.isDirectory()) {
    throw new Error(`Linux payload is not a directory: ${payloadDir}`);
  }
  const executable = path.join(payloadDir, executableName);
  try {
    const stat = fs.statSync(executable);
    if (!stat.isFile()) throw new Error("not a file");
  } catch {
    throw new Error(
      `Linux payload is missing the application executable: ${executable}. ` +
        "Run `npm run dist:linux` first."
    );
  }

  // 桌面项要用的图标随包一起走，避免安装后引用仓库里的路径。
  const iconDestination = path.join(payloadDir, "resources", ICON_NAME);
  fs.mkdirSync(path.dirname(iconDestination), { recursive: true });
  fs.copyFileSync(ICON_SOURCE, iconDestination);

  fs.mkdirSync(outputDir, { recursive: true });
  const payloadName = `${productName}-${version}-linux-${ARCH}.tar.gz`;
  const archivePath = path.join(outputDir, payloadName);
  if (!skipArchive) {
    fs.rmSync(archivePath, { force: true });
    runTarCreate(payloadDir, archivePath);
  }
  if (!fs.existsSync(archivePath)) {
    throw new Error(`Linux payload archive was not produced: ${archivePath}`);
  }
  const digest = sha256File(archivePath);

  const installerPath = path.join(outputDir, "install.sh");
  fs.writeFileSync(
    installerPath,
    renderInstallerTemplate({
      productName,
      version,
      executableName,
      payloadName,
      sha256: digest,
    }),
    { mode: 0o755 }
  );
  fs.chmodSync(installerPath, 0o755);

  const checksumsPath = path.join(outputDir, "SHA256SUMS.txt");
  fs.writeFileSync(
    checksumsPath,
    `${digest}  ${payloadName}\n${sha256File(installerPath)}  install.sh\n`
  );

  return { archivePath, installerPath, checksumsPath, payloadName, sha256: digest };
}

function parseCliArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--payload-dir") options.payloadDir = path.resolve(argv[++index]);
    else if (argument === "--output-dir") options.outputDir = path.resolve(argv[++index]);
    else if (argument === "--skip-archive") options.skipArchive = true;
    else if (argument === "--help" || argument === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${argument}`);
  }
  return options;
}

function main(argv = process.argv.slice(2)) {
  const options = parseCliArguments(argv);
  if (options.help) {
    process.stdout.write(
      "Usage: node scripts/build-linux-installer.cjs [--payload-dir DIR] [--output-dir DIR] [--skip-archive]\n"
    );
    return 0;
  }
  const result = buildLinuxInstaller(options);
  process.stdout.write(`Linux payload: ${result.archivePath}\n`);
  process.stdout.write(`Installer:     ${result.installerPath}\n`);
  process.stdout.write(`SHA-256:       ${result.sha256}\n`);
  return 0;
}

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (error) {
    process.stderr.write(`${error?.message || error}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  ARCH,
  buildLinuxInstaller,
  parseCliArguments,
  readPackageMetadata,
  renderInstallerTemplate,
};
