param(
  [switch]$Debug
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$crate = Join-Path $repo 'native\wce_integrity'
$outDir = Join-Path $repo 'src\wechat_decrypt_tool\native'
$profile = if ($Debug) { 'debug' } else { 'release' }
$targetDir = Join-Path $crate 'target-package'
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  throw "未找到项目虚拟环境 Python：$python"
}
$args = @('build')
if (-not $Debug) { $args += '--release' }
$cargoCommand = Get-Command cargo -ErrorAction SilentlyContinue
$cargoExe = if ($cargoCommand) { $cargoCommand.Source } else { $null }
$localCargoHome = Join-Path $repo 'output\tools\cargo-home'
$localRustupHome = Join-Path $repo 'output\tools\rustup'
$localCargoExe = Join-Path $localCargoHome 'bin\cargo.exe'
if (-not $cargoExe -and (Test-Path -LiteralPath $localCargoExe)) {
  $cargoExe = $localCargoExe
}
if (-not $cargoExe) {
  throw '未找到 Cargo。请安装 Rust，或将项目隔离工具链放到 output\tools\cargo-home。'
}

$previousCargoHome = $env:CARGO_HOME
$previousRustupHome = $env:RUSTUP_HOME
$previousPyo3Python = $env:PYO3_PYTHON
Push-Location $crate
try {
  if ($cargoExe -eq $localCargoExe) {
    $env:CARGO_HOME = $localCargoHome
    $env:RUSTUP_HOME = $localRustupHome
  }
  $previousTargetDir = $env:CARGO_TARGET_DIR
  try {
    $env:CARGO_TARGET_DIR = $targetDir
    $env:PYO3_PYTHON = $python
    & $cargoExe @args
    if ($LASTEXITCODE -ne 0) {
      throw "cargo build failed with exit code $LASTEXITCODE"
    }
  } finally {
    $env:CARGO_TARGET_DIR = $previousTargetDir
  }
} finally {
  Pop-Location
  $env:CARGO_HOME = $previousCargoHome
  $env:RUSTUP_HOME = $previousRustupHome
  $env:PYO3_PYTHON = $previousPyo3Python
}

$dll = Join-Path $targetDir "$profile\wce_integrity.dll"
if (-not (Test-Path $dll)) {
  throw "未找到构建产物：$dll"
}
New-Item -ItemType Directory -Force $outDir | Out-Null
$pyd = Join-Path $outDir 'wce_integrity.pyd'
try {
  Copy-Item -Force $dll $pyd
} catch [System.IO.IOException] {
  throw '标准 wce_integrity.pyd 正被运行中的后端占用。请仅停止本项目后端后重新构建。'
}
Write-Host "wce_integrity.pyd -> $pyd"

$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = Join-Path $repo 'src'
  $preflightScript = @'
from pathlib import Path

from wechat_decrypt_tool.export_integrity import load_wce_integrity_native

native = load_wce_integrity_native()
css = native.export_css("chat")
compact = "".join(css.split())
expected = (Path.cwd() / "src" / "wechat_decrypt_tool" / "native" / "wce_integrity.pyd").resolve()
actual = Path(native.__file__).resolve()
assert actual == expected, f"loaded unexpected native module: {actual}"
assert ".wechat-voice-transcript" in css
assert ".wechat-voice-wrapper{display:flex;flex-direction:column" in compact
print(f"wce_integrity loaded from: {native.__file__}")
'@
  $preflightScript | & $python -
  if ($LASTEXITCODE -ne 0) {
    throw "wce_integrity CSS 预检失败，退出码：$LASTEXITCODE"
  }
} finally {
  $env:PYTHONPATH = $previousPythonPath
}
