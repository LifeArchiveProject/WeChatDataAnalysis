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

const integrityManifest = path.join(repoRoot, "native", "wce_integrity", "Cargo.toml");
const integrityTargetDir = path.join(repoRoot, "native", "wce_integrity", "target", "release");
let integrityNativeBinary = null;
if (process.platform === "darwin" || process.platform === "linux") {
  const fileName = process.platform === "darwin" ? "libwce_integrity.dylib" : "libwce_integrity.so";
  const nativeBuild = spawnSync(
    "cargo",
    ["build", "--manifest-path", integrityManifest, "--release"],
    {
      cwd: repoRoot,
      env: {
        ...process.env,
        WCE_UI_PUBLIC_DIR: path.join(repoRoot, "frontend", ".output", "public"),
      },
      stdio: "inherit",
    }
  );
  if ((nativeBuild.status ?? 1) !== 0) {
    console.error("Failed to build the wce_integrity module for this platform.");
    process.exit(nativeBuild.status ?? 1);
  }
  integrityNativeBinary = path.join(integrityTargetDir, fileName);
  if (!fs.existsSync(integrityNativeBinary)) {
    console.error(`wce_integrity build completed without expected artifact: ${integrityNativeBinary}`);
    process.exit(1);
  }
}

const integrityPreflight = spawnSync(
  "uv",
  [
    "run",
    "python",
    "-c",
    [
      "from wechat_decrypt_tool.export_integrity import load_wce_integrity_native",
      "w=load_wce_integrity_native()",
      "required=('chat','sns','records-project','records-generic','contacts')",
      "assert all(w.export_css(kind).strip() for kind in required)",
      "assert callable(w.record_file) and callable(w.seal_export)",
    ].join(";"),
  ],
  {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: [path.join(repoRoot, "src"), process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
    },
    stdio: "inherit",
  }
);
if ((integrityPreflight.status ?? 1) !== 0) {
  console.error("wce_integrity runtime is missing or stale. Rebuild or restore the platform implementation before packaging.");
  process.exit(integrityPreflight.status ?? 1);
}

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
        StringStruct('FileDescription', 'WeChatDataAnalysis Backend'),
        StringStruct('FileVersion', '${versionDot}'),
        StringStruct('InternalName', 'wechat-backend'),
        StringStruct('LegalCopyright', 'LifeArchiveProject'),
        StringStruct('OriginalFilename', 'wechat-backend.exe'),
        StringStruct('ProductName', 'WeChatDataAnalysis'),
        StringStruct('ProductVersion', '${versionDot}')])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
`;
}

function pyInstallerAddData(sourcePath, targetPath) {
  return `${sourcePath}${path.delimiter}${targetPath}`;
}

const nativeDir = path.join(repoRoot, "src", "wechat_decrypt_tool", "native");
const runtimeNativeDir = path.join(repoRoot, "desktop", "build", "native-runtime");
const skillDir = path.join(repoRoot, "skills", "wechat-mcp-copilot");
const projectToml = path.join(repoRoot, "pyproject.toml");
const thirdPartyNotices = path.join(repoRoot, "THIRD_PARTY_NOTICES.md");

fs.rmSync(runtimeNativeDir, { recursive: true, force: true });
fs.mkdirSync(runtimeNativeDir, { recursive: true });

const wasmDir = path.join(nativeDir, "weflow_wasm");
if (fs.existsSync(wasmDir)) {
  fs.cpSync(wasmDir, path.join(runtimeNativeDir, "weflow_wasm"), { recursive: true, force: true });
}

if (process.platform === "win32") {
  for (const item of fs.readdirSync(nativeDir, { withFileTypes: true })) {
    if (!item.isFile() || !/\.(dll|pyd)$/i.test(item.name)) continue;
    fs.copyFileSync(path.join(nativeDir, item.name), path.join(runtimeNativeDir, item.name));
  }
} else if (process.platform === "darwin") {
  fs.cpSync(path.join(nativeDir, "macos"), path.join(runtimeNativeDir, "macos"), {
    recursive: true,
    force: true,
  });
  const imageScanHelper = path.join(runtimeNativeDir, "macos", "universal", "image_scan_helper");
  if (!fs.existsSync(imageScanHelper)) {
    console.error(`Missing macOS image scan helper: ${imageScanHelper}`);
    process.exit(1);
  }
  fs.chmodSync(imageScanHelper, 0o755);
}

const desktopPackageJsonPath = path.join(repoRoot, "desktop", "package.json");
let desktopVersion = "1.3.0";
try {
  const pkg = JSON.parse(fs.readFileSync(desktopPackageJsonPath, { encoding: "utf8" }));
  const v = String(pkg?.version || "").trim();
  if (v) desktopVersion = v;
} catch {}
const versionTuple = parseVersionTuple(desktopVersion);
const versionDot = versionTuple.join(".");
const versionFilePath = path.join(workDir, "wechat-data-analysis-version.txt");
if (process.platform === "win32") {
  fs.writeFileSync(versionFilePath, buildVersionInfoText(versionTuple, versionDot), { encoding: "utf8" });
}

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
  pyInstallerAddData(runtimeNativeDir, "wechat_decrypt_tool/native"),
  "--add-data",
  pyInstallerAddData(skillDir, "skills/wechat-mcp-copilot"),
  entry,
];

if (process.platform === "win32") {
  args.splice(args.length - 1, 0,
    "--version-file", versionFilePath,
    "--hidden-import", "wechat_decrypt_tool.key_v4",
    "--hidden-import", "yara"
  );
}
if (integrityNativeBinary) {
  args.splice(
    args.length - 1,
    0,
    "--add-binary",
    pyInstallerAddData(integrityNativeBinary, "wechat_decrypt_tool/native")
  );
}

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

fs.cpSync(runtimeNativeDir, packagedNativeDir, { recursive: true, force: true });
if (integrityNativeBinary) {
  fs.copyFileSync(integrityNativeBinary, path.join(packagedNativeDir, path.basename(integrityNativeBinary)));
}

// Provide the project marker next to packaged backend resources.
if (fs.existsSync(projectToml)) {
  try {
    fs.copyFileSync(projectToml, path.join(distDir, "pyproject.toml"));
  } catch {}
}
if (fs.existsSync(thirdPartyNotices)) {
  try {
    fs.copyFileSync(thirdPartyNotices, path.join(distDir, "THIRD_PARTY_NOTICES.md"));
  } catch {}
}

process.exit(0);
