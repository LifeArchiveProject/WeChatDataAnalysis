param(
  [switch]$Debug,
  [switch]$GenerateEphemeralSigningKey
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$crate = Join-Path $repo 'native\wce_integrity'
$outDir = Join-Path $repo 'src\wechat_decrypt_tool\native'
$profile = if ($Debug) { 'debug' } else { 'release' }
$targetDir = Join-Path $crate 'target-package'
$cargoArgs = @('build')
if (-not $Debug) { $cargoArgs += '--release' }

$providedSigningKey = [string]$env:WCE_SIGNING_KEY_HEX
if ($GenerateEphemeralSigningKey -and -not [string]::IsNullOrWhiteSpace($providedSigningKey)) {
  throw '不能同时设置 WCE_SIGNING_KEY_HEX 和 -GenerateEphemeralSigningKey。'
}
if (-not $GenerateEphemeralSigningKey -and [string]::IsNullOrWhiteSpace($providedSigningKey)) {
  throw '缺少 WCE_SIGNING_KEY_HEX。请注入新的 P-256 私钥，或显式使用 -GenerateEphemeralSigningKey。'
}

$previousSigningKey = $env:WCE_SIGNING_KEY_HEX
$ephemeralKeyBytes = $null
$ephemeralEcdsa = $null
if ($GenerateEphemeralSigningKey) {
  $ephemeralEcdsa = [System.Security.Cryptography.ECDsa]::Create(
    [System.Security.Cryptography.ECCurve+NamedCurves]::nistP256
  )
  $ephemeralKeyBytes = $ephemeralEcdsa.ExportParameters($true).D
  $env:WCE_SIGNING_KEY_HEX = ([BitConverter]::ToString($ephemeralKeyBytes)).Replace('-', '').ToLowerInvariant()
}

try {
  Push-Location $crate
  try {
    $previousTargetDir = $env:CARGO_TARGET_DIR
    try {
      $env:CARGO_TARGET_DIR = $targetDir
      cargo @cargoArgs
      if ($LASTEXITCODE -ne 0) {
        throw "cargo build failed with exit code $LASTEXITCODE"
      }
    } finally {
      $env:CARGO_TARGET_DIR = $previousTargetDir
    }
  } finally {
    Pop-Location
  }
} finally {
  $env:WCE_SIGNING_KEY_HEX = $previousSigningKey
  if ($null -ne $ephemeralKeyBytes) {
    [Array]::Clear($ephemeralKeyBytes, 0, $ephemeralKeyBytes.Length)
  }
  if ($null -ne $ephemeralEcdsa) {
    $ephemeralEcdsa.Dispose()
  }
}

$dll = Join-Path $targetDir "$profile\wce_integrity.dll"
if (-not (Test-Path $dll)) {
  throw "未找到构建产物：$dll"
}
New-Item -ItemType Directory -Force $outDir | Out-Null
$pyd = Join-Path $outDir 'wce_integrity.pyd'
Copy-Item -Force $dll $pyd
$artifactHash = (Get-FileHash -LiteralPath $pyd -Algorithm SHA256).Hash
Write-Host "wce_integrity.pyd -> $pyd"
Write-Host "SHA256: $artifactHash"
