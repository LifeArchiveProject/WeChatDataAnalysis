[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [ValidateSet('Client', 'Producer')]
    [string]$Mode = 'Client',

    [string]$GitHubOutputPath = $env:GITHUB_OUTPUT
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$codeSigningOid = '1.3.6.1.5.5.7.3.3'
$softwareProvider = 'Microsoft Software Key Storage Provider'
$storeLocation = 'Cert:\CurrentUser\My'
$importedThumbprints = [System.Collections.Generic.List[string]]::new()
$createdFiles = [System.Collections.Generic.List[string]]::new()
$completed = $false

function Get-RequiredEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = [string][Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Protected cloud signing input is missing: $Name"
    }
    return $value.Trim()
}

function Get-NormalizedHex {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][int]$Length,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $normalized = $Value.Replace(' ', '').ToUpperInvariant()
    if ($normalized -cnotmatch "^[0-9A-F]{$Length}$") {
        throw "$Name must contain exactly $Length hexadecimal characters."
    }
    return $normalized
}

function Get-HexSha256 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return -join ($sha256.ComputeHash($Bytes) | ForEach-Object {
            $_.ToString('X2')
        })
    } finally {
        $sha256.Dispose()
    }
}

function ConvertFrom-ProtectedBase64 {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Name
    )

    try {
        $bytes = [Convert]::FromBase64String(($Value -replace '\s', ''))
    } catch {
        throw "$Name is not valid base64."
    }
    if ($bytes.Length -eq 0) {
        throw "$Name decoded to an empty value."
    }
    return ,$bytes
}

function Get-BasicConstraints {
    param(
        [Parameter(Mandatory = $true)]
        [Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )

    $extension = @($Certificate.Extensions | Where-Object {
        $_.Oid.Value -ceq '2.5.29.19'
    })
    if ($extension.Count -ne 1) {
        throw 'Certificate must contain exactly one basic-constraints extension.'
    }
    $decoded = [Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new()
    $decoded.CopyFrom($extension[0])
    return $decoded
}

function Assert-PrivateRootCertificate {
    param(
        [Parameter(Mandatory = $true)]
        [Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    if ($Certificate.HasPrivateKey) {
        throw 'Cloud signing root input must contain only the public certificate.'
    }
    if ([Convert]::ToBase64String($Certificate.SubjectName.RawData) -cne
        [Convert]::ToBase64String($Certificate.IssuerName.RawData)) {
        throw 'Cloud signing root certificate must be self-issued.'
    }
    if (-not (Get-BasicConstraints $Certificate).CertificateAuthority) {
        throw 'Cloud signing root certificate must be a CA.'
    }
    if ((Get-HexSha256 $Certificate.RawData) -cne $ExpectedSha256) {
        throw 'Cloud signing root certificate does not match the protected SHA-256 pin.'
    }
    $now = Get-Date
    if ($now -lt $Certificate.NotBefore -or $now -gt $Certificate.NotAfter) {
        throw 'Cloud signing root certificate is not currently valid.'
    }
}

function Assert-ImportedCodeSigningCertificate {
    param(
        [Parameter(Mandatory = $true)]
        [Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [Parameter(Mandatory = $true)]
        [Security.Cryptography.X509Certificates.X509Certificate2]$Root,
        [Parameter(Mandatory = $true)][string]$ExpectedThumbprint,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$Role
    )

    if ($Certificate.Thumbprint.ToUpperInvariant() -cne $ExpectedThumbprint -or
        (Get-HexSha256 $Certificate.RawData) -cne $ExpectedSha256) {
        throw "$Role cloud signing certificate does not match its protected identity pins."
    }
    if (-not $Certificate.HasPrivateKey) {
        throw "$Role cloud signing certificate has no private key."
    }
    if ([Convert]::ToBase64String($Certificate.IssuerName.RawData) -cne
        [Convert]::ToBase64String($Root.SubjectName.RawData)) {
        throw "$Role cloud signing certificate is outside the protected private-PKI root."
    }
    if ((Get-BasicConstraints $Certificate).CertificateAuthority) {
        throw "$Role cloud signing certificate must not be a CA."
    }
    if ($Certificate.EnhancedKeyUsageList.ObjectId -notcontains $codeSigningOid) {
        throw "$Role cloud signing certificate lacks the code-signing EKU."
    }
    $now = Get-Date
    if ($now -lt $Certificate.NotBefore -or $now -gt $Certificate.NotAfter) {
        throw "$Role cloud signing certificate is not currently valid."
    }

    $privateKey = $null
    try {
        $privateKey = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey(
            $Certificate)
        if ($null -eq $privateKey) {
            $privateKey = [Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPrivateKey(
                $Certificate)
        }
        if ($null -eq $privateKey -or
            $privateKey.GetType().Name -notin @('RSACng', 'ECDsaCng')) {
            throw "$Role cloud signing certificate must use a Windows CNG private key."
        }
        if ($privateKey.Key.Provider.Provider -cne $softwareProvider) {
            throw "$Role cloud signing key must use $softwareProvider."
        }
        $exportPolicy = [string]$privateKey.Key.ExportPolicy
        if ($exportPolicy -match 'AllowExport|AllowPlaintextExport') {
            throw "$Role cloud signing key remained exportable after import: $exportPolicy"
        }
    } finally {
        if ($null -ne $privateKey) { $privateKey.Dispose() }
    }
}

function Import-CodeSigningRole {
    param(
        [Parameter(Mandatory = $true)][string]$Role,
        [Parameter(Mandatory = $true)][string]$PfxBase64Name,
        [Parameter(Mandatory = $true)][string]$PasswordName,
        [Parameter(Mandatory = $true)][string]$ThumbprintName,
        [Parameter(Mandatory = $true)][string]$SignerSha256Name,
        [Parameter(Mandatory = $true)]
        [Security.Cryptography.X509Certificates.X509Certificate2]$Root,
        [Parameter(Mandatory = $true)][string]$Directory
    )

    $expectedThumbprint = Get-NormalizedHex `
        (Get-RequiredEnvironmentValue $ThumbprintName) 40 $ThumbprintName
    $expectedSha256 = Get-NormalizedHex `
        (Get-RequiredEnvironmentValue $SignerSha256Name) 64 $SignerSha256Name
    $pfxPath = Join-Path $Directory ($Role.ToLowerInvariant() + '.pfx')
    [IO.File]::WriteAllBytes(
        $pfxPath,
        (ConvertFrom-ProtectedBase64 `
            (Get-RequiredEnvironmentValue $PfxBase64Name) $PfxBase64Name))
    [void]$createdFiles.Add($pfxPath)
    $password = ConvertTo-SecureString `
        (Get-RequiredEnvironmentValue $PasswordName) -AsPlainText -Force
    try {
        $imported = @(Import-PfxCertificate `
            -FilePath $pfxPath `
            -CertStoreLocation $storeLocation `
            -Password $password `
            -ErrorAction Stop)
    } finally {
        $password.Dispose()
        [IO.File]::Delete($pfxPath)
        [void]$createdFiles.Remove($pfxPath)
    }
    $leaf = @($imported | Where-Object {
        $_.Thumbprint.ToUpperInvariant() -ceq $expectedThumbprint
    })
    if ($leaf.Count -ne 1) {
        foreach ($certificate in $imported) {
            if (-not [string]::IsNullOrWhiteSpace($certificate.Thumbprint)) {
                [void]$importedThumbprints.Add($certificate.Thumbprint.ToUpperInvariant())
            }
        }
        throw "$Role cloud signing PFX did not import exactly the protected leaf identity."
    }
    foreach ($certificate in $imported) {
        if (-not [string]::IsNullOrWhiteSpace($certificate.Thumbprint)) {
            $thumbprint = $certificate.Thumbprint.ToUpperInvariant()
            if (-not $importedThumbprints.Contains($thumbprint)) {
                [void]$importedThumbprints.Add($thumbprint)
            }
        }
    }
    Assert-ImportedCodeSigningCertificate `
        $leaf[0] $Root $expectedThumbprint $expectedSha256 $Role
    return $expectedThumbprint
}

function Remove-ImportedCertificates {
    foreach ($thumbprint in @($importedThumbprints)) {
        $path = Join-Path $storeLocation $thumbprint
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -DeleteKey -Force -ErrorAction SilentlyContinue
        }
    }
}

$outputFullPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputFullPath) {
    if (@(Get-ChildItem -LiteralPath $outputFullPath -Force).Count -ne 0) {
        throw "Cloud signing staging directory is not empty: $outputFullPath"
    }
} else {
    New-Item -ItemType Directory -Path $outputFullPath | Out-Null
}

$root = $null
try {
    $rootSha256 = Get-NormalizedHex `
        (Get-RequiredEnvironmentValue 'WCE_WINDOWS_PRIVATE_ROOT_SHA256') `
        64 'WCE_WINDOWS_PRIVATE_ROOT_SHA256'
    $rootBytes = ConvertFrom-ProtectedBase64 `
        (Get-RequiredEnvironmentValue 'WCE_WINDOWS_PRIVATE_ROOT_CERT_BASE64') `
        'WCE_WINDOWS_PRIVATE_ROOT_CERT_BASE64'
    $root = [Security.Cryptography.X509Certificates.X509Certificate2]::new($rootBytes)
    Assert-PrivateRootCertificate $root $rootSha256
    $rootPath = Join-Path $outputFullPath 'windows-private-pki-root.cer'
    [IO.File]::WriteAllBytes($rootPath, $root.RawData)
    [void]$createdFiles.Add($rootPath)

    $clientThumbprint = Import-CodeSigningRole `
        'Client' `
        'WCE_WINDOWS_CLIENT_SIGNING_PFX_BASE64' `
        'WCE_WINDOWS_CLIENT_SIGNING_PFX_PASSWORD' `
        'WCE_WINDOWS_CLIENT_CERT_THUMBPRINT' `
        'WCE_WINDOWS_CLIENT_SIGNER_SHA256' `
        $root $outputFullPath

    $brokerThumbprint = ''
    if ($Mode -ceq 'Producer') {
        $brokerThumbprint = Import-CodeSigningRole `
            'Broker' `
            'WCE_WINDOWS_BROKER_SIGNING_PFX_BASE64' `
            'WCE_WINDOWS_BROKER_SIGNING_PFX_PASSWORD' `
            'WCE_WINDOWS_BROKER_CERT_THUMBPRINT' `
            'WCE_WINDOWS_BROKER_SIGNER_SHA256' `
            $root $outputFullPath
        if ($brokerThumbprint -ceq $clientThumbprint) {
            throw 'Cloud client and broker signing identities must be distinct.'
        }
    }

    $statePath = Join-Path $outputFullPath 'windows-cloud-signing-state.json'
    $state = [ordered]@{
        schemaVersion = 1
        mode = $Mode.ToLowerInvariant()
        rootCertificatePath = $rootPath
        importedThumbprints = @($importedThumbprints)
    }
    [IO.File]::WriteAllText(
        $statePath,
        ($state | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
    [void]$createdFiles.Add($statePath)

    if (-not [string]::IsNullOrWhiteSpace($GitHubOutputPath)) {
        "root-certificate-path=$rootPath" |
            Out-File -FilePath $GitHubOutputPath -Append -Encoding utf8
        "client-thumbprint=$clientThumbprint" |
            Out-File -FilePath $GitHubOutputPath -Append -Encoding utf8
        if (-not [string]::IsNullOrWhiteSpace($brokerThumbprint)) {
            "broker-thumbprint=$brokerThumbprint" |
                Out-File -FilePath $GitHubOutputPath -Append -Encoding utf8
        }
    }
    Write-Output "Imported protected cloud signing identity: mode=$Mode root=$rootSha256"
    $completed = $true
} finally {
    if ($null -ne $root) { $root.Dispose() }
    if (-not $completed) {
        Remove-ImportedCertificates
        foreach ($path in @($createdFiles)) {
            if ([IO.File]::Exists($path)) { [IO.File]::Delete($path) }
        }
    }
}
