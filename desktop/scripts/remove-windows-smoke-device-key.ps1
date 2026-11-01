[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Delete')]
    [string]$Action = 'Delete',

    [Parameter(Mandatory = $true)]
    [ValidateScript({
        if ($_ -cnotmatch '^LifeArchiveProject\.WeChatDB\.Native\.RealSmoke\.[0-9a-f]{32}$') {
            throw 'Smoke key name must use the exact lowercase acceptance prefix and suffix.'
        }
        return $true
    })]
    [string]$KeyName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$providers = @(
    'Microsoft Platform Crypto Provider',
    'Microsoft Software Key Storage Provider'
)

foreach ($providerName in $providers) {
    $provider = [Security.Cryptography.CngProvider]::new($providerName)
    if (-not [Security.Cryptography.CngKey]::Exists(
            $KeyName,
            $provider,
            [Security.Cryptography.CngKeyOpenOptions]::Silent
        )) {
        continue
    }

    $key = $null
    try {
        $key = [Security.Cryptography.CngKey]::Open(
            $KeyName,
            $provider,
            [Security.Cryptography.CngKeyOpenOptions]::Silent
        )
        $blob = $key.Export([Security.Cryptography.CngKeyBlobFormat]::EccPublicBlob)
        if ($blob.Length -ne 72 -or [BitConverter]::ToUInt32($blob, 4) -ne 32) {
            throw 'Smoke device key returned an invalid P-256 public blob.'
        }
        $domain = [Text.Encoding]::ASCII.GetBytes('WCE-DEVICE-ID-V1')
        $identityInput = [byte[]]::new($domain.Length + 64)
        [Array]::Copy($domain, 0, $identityInput, 0, $domain.Length)
        [Array]::Copy($blob, 8, $identityInput, $domain.Length, 64)
        $sha256 = [Security.Cryptography.SHA256]::Create()
        try {
            $deviceId = $sha256.ComputeHash($identityInput)
        } finally {
            $sha256.Dispose()
            [Array]::Clear($identityInput, 0, $identityInput.Length)
            [Array]::Clear($blob, 0, $blob.Length)
        }
        $deviceIdHex = ([BitConverter]::ToString($deviceId)).Replace('-', '').ToLowerInvariant()
        [Array]::Clear($deviceId, 0, $deviceId.Length)
        if ($Action -ceq 'Delete') {
            $key.Delete()
        }
        $key.Dispose()
        $key = $null

        [ordered]@{
            schemaVersion = 1
            action = $Action
            found = $true
            deleted = $Action -ceq 'Delete'
            provider = $providerName
            deviceIdHex = $deviceIdHex
        } | ConvertTo-Json -Compress
        return
    } finally {
        if ($null -ne $key) {
            $key.Dispose()
        }
    }
}

[ordered]@{
    schemaVersion = 1
    action = $Action
    found = $false
    deleted = $false
    provider = ''
    deviceIdHex = ''
} | ConvertTo-Json -Compress
