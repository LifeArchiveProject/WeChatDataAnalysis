[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RootCertificatePath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-F]{64}$')]
    [string]$ExpectedRootSha256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolved = (Resolve-Path -LiteralPath $RootCertificatePath).Path
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolved).Hash
if ($actualHash -cne $ExpectedRootSha256) {
    throw 'Private-PKI issuer cleanup certificate does not match the pinned root.'
}

$root = [Security.Cryptography.X509Certificates.X509Certificate2]::new($resolved)
$rootThumbprint = $root.Thumbprint
$store = [Security.Cryptography.X509Certificates.X509Store]::new(
    'CA',
    [Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
try {
    $store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $matches = @($store.Certificates | Where-Object { $_.Thumbprint -ceq $rootThumbprint })
    if ($matches.Count -gt 1) {
        throw 'CurrentUser issuer cache contains duplicate pinned roots.'
    }
    if ($matches.Count -eq 1) {
        $sha256 = [Security.Cryptography.SHA256]::Create()
        try {
            $cachedHash = ([BitConverter]::ToString(
                $sha256.ComputeHash($matches[0].RawData)
            )).Replace('-', '')
        } finally {
            $sha256.Dispose()
        }
        if ($cachedHash -cne $ExpectedRootSha256) {
            throw 'CurrentUser issuer cache thumbprint maps to unexpected certificate bytes.'
        }
        $store.Remove($matches[0])
    }
} finally {
    $store.Close()
    $root.Dispose()
}

$verify = [Security.Cryptography.X509Certificates.X509Store]::new(
    'CA',
    [Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
try {
    $verify.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
    $remaining = @($verify.Certificates | Where-Object {
        $_.Thumbprint -ceq $rootThumbprint
    }).Count
} finally {
    $verify.Close()
}
if ($remaining -ne 0) {
    throw 'Pinned private-PKI issuer remained cached after cleanup.'
}

[ordered]@{
    schemaVersion = 1
    removed = $matches.Count -eq 1
    issuerStore = 'CurrentUser\CA'
    remaining = 0
} | ConvertTo-Json -Compress
