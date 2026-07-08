param(
  [switch]$Debug
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$crate = Join-Path $repo 'native\wce_integrity'
$outDir = Join-Path $repo 'src\wechat_decrypt_tool\native'
$profile = if ($Debug) { 'debug' } else { 'release' }
$args = @('build')
if (-not $Debug) { $args += '--release' }

Push-Location $crate
try {
  cargo @args
  if ($LASTEXITCODE -ne 0) {
    throw "cargo build failed with exit code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

$dll = Join-Path $crate "target\$profile\wce_integrity.dll"
if (-not (Test-Path $dll)) {
  throw "未找到构建产物：$dll"
}
New-Item -ItemType Directory -Force $outDir | Out-Null
$pyd = Join-Path $outDir 'wce_integrity.pyd'
Copy-Item -Force $dll $pyd
Write-Host "wce_integrity.pyd -> $pyd"
