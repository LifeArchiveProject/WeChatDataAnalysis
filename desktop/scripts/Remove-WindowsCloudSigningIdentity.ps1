[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$outputFullPath = [IO.Path]::GetFullPath($OutputDirectory)
$statePath = Join-Path $outputFullPath 'windows-cloud-signing-state.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-Output 'No temporary cloud signing identity state was present.'
    return
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.schemaVersion -ne 1 -or
    $state.mode -notin @('client', 'producer') -or
    $null -eq $state.importedThumbprints) {
    throw 'Temporary cloud signing identity state is invalid.'
}

foreach ($rawThumbprint in @($state.importedThumbprints)) {
    $thumbprint = ([string]$rawThumbprint).Replace(' ', '').ToUpperInvariant()
    if ($thumbprint -cnotmatch '^[0-9A-F]{40}$') {
        throw 'Temporary cloud signing identity state contains an invalid thumbprint.'
    }
    $certificatePath = "Cert:\CurrentUser\My\$thumbprint"
    if (Test-Path -LiteralPath $certificatePath) {
        Remove-Item -LiteralPath $certificatePath -DeleteKey -Force
    }
    if (Test-Path -LiteralPath $certificatePath) {
        throw "Temporary cloud signing identity could not be removed: $thumbprint"
    }
}

foreach ($path in @(
        (Join-Path $outputFullPath 'client.pfx'),
        (Join-Path $outputFullPath 'broker.pfx'),
        (Join-Path $outputFullPath 'windows-private-pki-root.cer'),
        $statePath
    )) {
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Remove-Item -LiteralPath $path -Force
    }
}
if ((Test-Path -LiteralPath $outputFullPath -PathType Container) -and
    @(Get-ChildItem -LiteralPath $outputFullPath -Force).Count -eq 0) {
    Remove-Item -LiteralPath $outputFullPath -Force
}
Write-Output 'Removed temporary cloud signing certificates, keys, and staging files.'
