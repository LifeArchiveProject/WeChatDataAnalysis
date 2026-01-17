const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..", "..");
const entry = path.join(repoRoot, "src", "wechat_decrypt_tool", "backend_entry.py");

const distDir = path.join(repoRoot, "desktop", "resources", "backend");
const workDir = path.join(repoRoot, "desktop", "build", "pyinstaller");
const specDir = path.join(repoRoot, "desktop", "build", "pyinstaller-spec");

fs.mkdirSync(distDir, { recursive: true });
fs.mkdirSync(workDir, { recursive: true });
fs.mkdirSync(specDir, { recursive: true });

const nativeDir = path.join(repoRoot, "src", "wechat_decrypt_tool", "native");
const addData = `${nativeDir};wechat_decrypt_tool/native`;

const args = [
  "run",
  "pyinstaller",
  "--noconfirm",
  "--clean",
  "--name",
  "wechat-backend",
  "--onefile",
  "--distpath",
  distDir,
  "--workpath",
  workDir,
  "--specpath",
  specDir,
  "--add-data",
  addData,
  entry,
];

const r = spawnSync("uv", args, { cwd: repoRoot, stdio: "inherit" });
process.exit(r.status ?? 1);

