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

function parseVersionTuple(rawVersion) {
  const nums = String(rawVersion || "")
    .split(/[^\d]+/)
    .map((x) => Number.parseInt(x, 10))
    .filter((n) => Number.isInteger(n) && n >= 0);
  while (nums.length < 4) nums.push(0);
  return nums.slice(0, 4);
}

function buildVersionInfoText(versionTuple, versionDot) {
  const [a, b, c, d] = versionTuple;
  return `# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(${a}, ${b}, ${c}, ${d}),
    prodvers=(${a}, ${b}, ${c}, ${d}),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [StringStruct('CompanyName', 'LifeArchiveProject'),
        StringStruct('FileDescription', 'WeFlow'),
        StringStruct('FileVersion', '${versionDot}'),
        StringStruct('InternalName', 'weflow'),
        StringStruct('LegalCopyright', 'github.com/hicccc77/WeFlow'),
        StringStruct('OriginalFilename', 'weflow.exe'),
        StringStruct('ProductName', 'WeFlow'),
        StringStruct('ProductVersion', '${versionDot}')])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
`;
}

const nativeDir = path.join(repoRoot, "src", "wechat_decrypt_tool", "native");
const addData = `${nativeDir};wechat_decrypt_tool/native`;
const projectToml = path.join(repoRoot, "pyproject.toml");

const desktopPackageJsonPath = path.join(repoRoot, "desktop", "package.json");
let desktopVersion = "1.3.0";
try {
  const pkg = JSON.parse(fs.readFileSync(desktopPackageJsonPath, { encoding: "utf8" }));
  const v = String(pkg?.version || "").trim();
  if (v) desktopVersion = v;
} catch {}
const versionTuple = parseVersionTuple(desktopVersion);
const versionDot = versionTuple.join(".");
const versionFilePath = path.join(workDir, "weflow-version.txt");
fs.writeFileSync(versionFilePath, buildVersionInfoText(versionTuple, versionDot), { encoding: "utf8" });

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
  "--version-file",
  versionFilePath,
  "--add-data",
  addData,
  entry,
];

const r = spawnSync("uv", args, { cwd: repoRoot, stdio: "inherit" });
if ((r.status ?? 1) !== 0) {
  process.exit(r.status ?? 1);
}

// Keep a stable external native folder for packaged runtime to avoid relying on
// onefile temp extraction paths when wcdb_api.dll performs environment checks.
const packagedNativeDir = path.join(distDir, "native");
try {
  fs.rmSync(packagedNativeDir, { recursive: true, force: true });
} catch {}
fs.mkdirSync(packagedNativeDir, { recursive: true });

for (const name of fs.readdirSync(nativeDir)) {
  const src = path.join(nativeDir, name);
  const dst = path.join(packagedNativeDir, name);
  try {
    if (fs.statSync(src).isFile()) {
      fs.copyFileSync(src, dst);
    }
  } catch {}
}

// Provide the project marker next to packaged backend resources.
if (fs.existsSync(projectToml)) {
  try {
    fs.copyFileSync(projectToml, path.join(distDir, "pyproject.toml"));
  } catch {}
}

process.exit(0);

