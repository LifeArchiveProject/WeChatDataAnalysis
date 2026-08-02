[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CredentialPath,
    [Parameter(Mandatory = $true)][string]$DeviceIdHex,
    [Parameter(Mandatory = $true)][string]$BuildId,
    [Parameter(Mandatory = $true)][string]$ServiceUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($DeviceIdHex -cnotmatch '^[0-9a-f]{64}$') {
    throw 'Smoke device ID is malformed.'
}
if ($BuildId -cnotmatch '^[A-Za-z0-9._-]{8,128}$') {
    throw 'Native build ID is malformed.'
}
if ($ServiceUrl -cne 'https://license.fqyw.love/v1/leases') {
    throw 'Unexpected native license service URL.'
}

$resolvedPath = (Resolve-Path -LiteralPath $CredentialPath).Path
$encoded = [IO.File]::ReadAllBytes($resolvedPath)
$magic = [Text.Encoding]::ASCII.GetBytes('WCEDC001')
if ($encoded.Length -le $magic.Length -or $encoded.Length -gt 16384) {
    throw 'Native device credential file is invalid.'
}
for ($index = 0; $index -lt $magic.Length; $index++) {
    if ($encoded[$index] -ne $magic[$index]) {
        throw 'Native device credential file is invalid.'
    }
}

function Convert-HexBytes {
    param([Parameter(Mandatory = $true)][string]$Value)

    $bytes = [byte[]]::new($Value.Length / 2)
    for ($index = 0; $index -lt $bytes.Length; $index++) {
        $bytes[$index] = [Convert]::ToByte($Value.Substring($index * 2, 2), 16)
    }
    return $bytes
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][byte[]]$Value)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($Value))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}

$deviceId = Convert-HexBytes -Value $DeviceIdHex
$buildBytes = [Text.Encoding]::UTF8.GetBytes($BuildId)
$buildDigestBytes = Convert-HexBytes -Value (Get-Sha256Hex -Value $buildBytes)
$service = [Text.Encoding]::ASCII.GetBytes($ServiceUrl)
$domain = [Text.Encoding]::ASCII.GetBytes("WeChatDataAnalysis/native-core/device-credential/v2`0")
$length = [BitConverter]::GetBytes([Net.IPAddress]::HostToNetworkOrder([int]$service.Length))
$entropyStream = [IO.MemoryStream]::new()
try {
    $entropyStream.Write($domain, 0, $domain.Length)
    $entropyStream.Write($deviceId, 0, $deviceId.Length)
    $entropyStream.Write($buildDigestBytes, 0, $buildDigestBytes.Length)
    $entropyStream.Write($length, 0, $length.Length)
    $entropyStream.Write($service, 0, $service.Length)
    $entropyInput = $entropyStream.ToArray()
} finally {
    $entropyStream.Dispose()
}
$entropyHash = [Security.Cryptography.SHA256]::Create()
try {
    $entropy = $entropyHash.ComputeHash($entropyInput)
} finally {
    $entropyHash.Dispose()
}

$protected = [byte[]]::new($encoded.Length - $magic.Length)
[Array]::Copy($encoded, $magic.Length, $protected, 0, $protected.Length)
Add-Type -AssemblyName System.Security
$plaintext = [Security.Cryptography.ProtectedData]::Unprotect(
    $protected,
    $entropy,
    [Security.Cryptography.DataProtectionScope]::CurrentUser
)
try {
    if ($plaintext.Length -le 0 -or $plaintext.Length -gt 8192) {
        throw 'Native device credential plaintext is invalid.'
    }
    $payload = [Text.Encoding]::UTF8.GetString($plaintext) | ConvertFrom-Json
    $properties = @($payload.PSObject.Properties.Name | Sort-Object)
    if ($payload.schemaVersion -ne 2 -or
        ($properties -join ',') -cne 'credential,leaseBase64,schemaVersion') {
        throw 'Native device credential record is invalid.'
    }
    $credential = [string]$payload.credential
    if ($credential -cne $credential.Trim() -or
        $credential.Length -lt 32 -or
        $credential.Length -gt 4096 -or
        $credential -cmatch '[^\x21-\x7e]') {
        throw 'Native device credential token is invalid.'
    }
    $credentialBytes = [Text.Encoding]::ASCII.GetBytes($credential)
    try {
        $lease = [Convert]::FromBase64String([string]$payload.leaseBase64)
        try {
            if ($lease.Length -ne 224 -or
                [Convert]::ToBase64String($lease) -cne [string]$payload.leaseBase64) {
                throw 'Native cached lease is invalid.'
            }
            [pscustomobject]@{
                schemaVersion = 2
                credentialSha256 = Get-Sha256Hex -Value $credentialBytes
                leaseSha256 = Get-Sha256Hex -Value $lease
                protectedFileSha256 = Get-Sha256Hex -Value $encoded
            } | ConvertTo-Json -Compress
        } finally {
            if ($null -ne $lease) {
                [Array]::Clear($lease, 0, $lease.Length)
            }
        }
    } finally {
        [Array]::Clear($credentialBytes, 0, $credentialBytes.Length)
    }
} finally {
    foreach ($buffer in @($plaintext, $protected, $entropy, $entropyInput, $encoded)) {
        if ($null -ne $buffer) {
            [Array]::Clear($buffer, 0, $buffer.Length)
        }
    }
}
