[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Preflight', 'Sign', 'Verify', 'CacheIssuer', 'TrustProbe')]
    [string]$Action,
    [string]$Path,
    [string]$CertificateThumbprint,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedSignerSha256,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedRootSha256,
    [Parameter(Mandatory = $true)]
    [string]$PrivateRootCertificatePath,
    [string]$TimestampUrl,
    [string]$SignToolPath,
    [ValidateSet('tpm', 'software-ksp')]
    [string]$SigningAssurance = 'tpm',
    [string]$Description = 'WeChatDataAnalysis'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ('WdaPrivatePki.NativeMethods' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace WdaPrivatePki
{
    public static class NativeMethods
    {
        public const int CertEUntrustedRoot = unchecked((int)0x800B0109);

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct WinTrustFileInfo
        {
            public uint cbStruct;
            [MarshalAs(UnmanagedType.LPWStr)] public string pcwszFilePath;
            public IntPtr hFile;
            public IntPtr pgKnownSubject;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct WinTrustData
        {
            public uint cbStruct;
            public IntPtr pPolicyCallbackData;
            public IntPtr pSIPClientData;
            public uint dwUIChoice;
            public uint fdwRevocationChecks;
            public uint dwUnionChoice;
            public IntPtr pFile;
            public uint dwStateAction;
            public IntPtr hWVTStateData;
            public IntPtr pwszURLReference;
            public uint dwProvFlags;
            public uint dwUIContext;
            public IntPtr pSignatureSettings;
        }

        [DllImport("wintrust.dll", ExactSpelling = true, SetLastError = true)]
        private static extern int WinVerifyTrust(
            IntPtr hwnd,
            [In] ref Guid actionId,
            [In] ref WinTrustData trustData);

        public static int VerifyEmbeddedSignature(string path)
        {
            var fileInfo = new WinTrustFileInfo {
                cbStruct = (uint)Marshal.SizeOf(typeof(WinTrustFileInfo)),
                pcwszFilePath = path,
                hFile = IntPtr.Zero,
                pgKnownSubject = IntPtr.Zero
            };
            IntPtr fileInfoPointer = Marshal.AllocHGlobal(Marshal.SizeOf(fileInfo));
            try {
                Marshal.StructureToPtr(fileInfo, fileInfoPointer, false);
                var trustData = new WinTrustData {
                    cbStruct = (uint)Marshal.SizeOf(typeof(WinTrustData)),
                    dwUIChoice = 2,
                    fdwRevocationChecks = 1,
                    dwUnionChoice = 1,
                    pFile = fileInfoPointer,
                    dwStateAction = 0,
                    dwProvFlags = 0x80,
                    dwUIContext = 0
                };
                var actionId = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
                return WinVerifyTrust(IntPtr.Zero, ref actionId, ref trustData);
            }
            finally {
                Marshal.DestroyStructure(fileInfoPointer, typeof(WinTrustFileInfo));
                Marshal.FreeHGlobal(fileInfoPointer);
            }
        }
    }
}
'@
}

function Get-CertificateSha256 {
    param([Parameter(Mandatory = $true)][byte[]]$RawData)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return -join ($sha256.ComputeHash($RawData) | ForEach-Object { $_.ToString('X2') })
    } finally {
        $sha256.Dispose()
    }
}

function Format-HResult {
    param([Parameter(Mandatory = $true)][int]$Value)
    $unsigned = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$Value), 0)
    return '0x{0:X8}' -f $unsigned
}

function Compare-DistinguishedName {
    param(
        [Parameter(Mandatory = $true)]$Left,
        [Parameter(Mandatory = $true)]$Right
    )
    return [Convert]::ToBase64String($Left.RawData) -ceq [Convert]::ToBase64String($Right.RawData)
}

function Get-RootCertificate {
    $resolved = (Resolve-Path -LiteralPath $PrivateRootCertificatePath).Path
    $root = New-Object Security.Cryptography.X509Certificates.X509Certificate2($resolved)
    $actualRootSha256 = Get-CertificateSha256 $root.RawData
    if ($actualRootSha256 -cne $ExpectedRootSha256.ToUpperInvariant()) {
        throw "Private-PKI root certificate does not match the expected SHA-256 pin: $resolved"
    }
    if (-not (Compare-DistinguishedName $root.SubjectName $root.IssuerName)) {
        throw "Private-PKI root certificate must be self-issued: $resolved"
    }
    $basicConstraints = $root.Extensions | Where-Object {
        $_.Oid.Value -eq '2.5.29.19'
    } | Select-Object -First 1
    if ($null -eq $basicConstraints) {
        throw "Private-PKI root certificate lacks basic constraints: $resolved"
    }
    $decodedConstraints = New-Object `
        Security.Cryptography.X509Certificates.X509BasicConstraintsExtension(
            $basicConstraints,
            $basicConstraints.Critical
        )
    if (-not $decodedConstraints.CertificateAuthority) {
        throw "Private-PKI root certificate is not a CA: $resolved"
    }
    $now = Get-Date
    if ($now -lt $root.NotBefore -or $now -gt $root.NotAfter) {
        throw "Private-PKI root certificate is not currently valid: $resolved"
    }
    $keyUsage = $root.Extensions | Where-Object {
        $_.Oid.Value -eq '2.5.29.15'
    } | Select-Object -First 1
    if ($null -ne $keyUsage) {
        $decodedKeyUsage = New-Object `
            Security.Cryptography.X509Certificates.X509KeyUsageExtension(
                $keyUsage,
                $keyUsage.Critical
            )
        if (($decodedKeyUsage.KeyUsages -band
            [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyCertSign) -eq 0) {
            throw "Private-PKI root certificate lacks keyCertSign usage: $resolved"
        }
    }
    foreach ($storeLocation in @(
        'Cert:\CurrentUser\Root',
        'Cert:\LocalMachine\Root',
        'Cert:\CurrentUser\TrustedPublisher',
        'Cert:\LocalMachine\TrustedPublisher'
    )) {
        $trusted = Get-ChildItem -LiteralPath $storeLocation -ErrorAction SilentlyContinue |
            Where-Object { (Get-CertificateSha256 $_.RawData) -ceq $actualRootSha256 } |
            Select-Object -First 1
        if ($null -ne $trusted) {
            throw "Private-PKI root must not be installed in a Windows trust store: $storeLocation"
        }
    }
    return [ordered]@{ Certificate = $root; Path = $resolved; Sha256 = $actualRootSha256 }
}

function Add-PrivatePkiIssuerCertificate {
    param([Parameter(Mandatory = $true)]$Root)

    $storePath = "Cert:\CurrentUser\CA\$($Root.Certificate.Thumbprint)"
    if (Test-Path -LiteralPath $storePath) {
        $existing = Get-Item -LiteralPath $storePath
        if ((Get-CertificateSha256 $existing.RawData) -cne $Root.Sha256 -or
            $existing.HasPrivateKey) {
            throw 'CurrentUser issuer cache contains a conflicting private-PKI root.'
        }
        return $false
    }
    $imported = Import-Certificate `
        -FilePath $Root.Path `
        -CertStoreLocation 'Cert:\CurrentUser\CA'
    if ($null -eq $imported -or
        $imported.Thumbprint -cne $Root.Certificate.Thumbprint -or
        $imported.HasPrivateKey -or
        (Get-CertificateSha256 $imported.RawData) -cne $Root.Sha256) {
        throw 'Unable to cache the exact public private-PKI issuer certificate.'
    }
    return $true
}

function Remove-PrivatePkiIssuerCertificate {
    param([Parameter(Mandatory = $true)]$Root)

    $storePath = "Cert:\CurrentUser\CA\$($Root.Certificate.Thumbprint)"
    if (Test-Path -LiteralPath $storePath) {
        $existing = Get-Item -LiteralPath $storePath
        if ((Get-CertificateSha256 $existing.RawData) -cne $Root.Sha256 -or
            $existing.HasPrivateKey) {
            throw 'Refusing to remove a conflicting CurrentUser issuer certificate.'
        }
        Remove-Item -LiteralPath $storePath -Force
    }
}

function Assert-CodeSigningLeaf {
    param(
        [Parameter(Mandatory = $true)]$Certificate,
        [Parameter(Mandatory = $true)]$Root
    )
    $actualSigner = Get-CertificateSha256 $Certificate.RawData
    if ($actualSigner -cne $ExpectedSignerSha256.ToUpperInvariant()) {
        throw 'Code-signing certificate does not match the expected SHA-256 leaf pin.'
    }
    if (Compare-DistinguishedName $Certificate.SubjectName $Certificate.IssuerName) {
        throw 'Private-PKI code-signing leaf must not be self-issued.'
    }
    if (-not (Compare-DistinguishedName $Certificate.IssuerName $Root.Certificate.SubjectName)) {
        throw 'Private-PKI code-signing leaf is not issued by the pinned root subject.'
    }
    $codeSigningEku = '1.3.6.1.5.5.7.3.3'
    if ($Certificate.EnhancedKeyUsageList.ObjectId -notcontains $codeSigningEku) {
        throw 'Private-PKI leaf lacks the code-signing EKU.'
    }
    $constraints = $Certificate.Extensions | Where-Object {
        $_.Oid.Value -eq '2.5.29.19'
    } | Select-Object -First 1
    if ($null -ne $constraints) {
        $decoded = New-Object Security.Cryptography.X509Certificates.X509BasicConstraintsExtension(
            $constraints,
            $constraints.Critical
        )
        if ($decoded.CertificateAuthority) {
            throw 'Private-PKI code-signing leaf must not be a CA.'
        }
    }
    return $actualSigner
}

function Get-CurrentUserSigningCertificate {
    param(
        [Parameter(Mandatory = $true)][string]$Thumbprint,
        [Parameter(Mandatory = $true)]$Root,
        [Parameter(Mandatory = $true)]
        [ValidateSet('tpm', 'software-ksp')]
        [string]$Assurance
    )

    $normalizedThumbprint = $Thumbprint.Replace(' ', '').ToUpperInvariant()
    if ($normalizedThumbprint -notmatch '^[0-9A-F]{40}$') {
        throw 'WCE_WINDOWS_CLIENT_CERT_THUMBPRINT must contain exactly 40 hexadecimal characters.'
    }
    $certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$normalizedThumbprint" -ErrorAction Stop
    if (-not $certificate.HasPrivateKey) {
        throw 'The CurrentUser code-signing certificate does not have a private key.'
    }
    [void](Assert-CodeSigningLeaf $certificate $Root)
    $now = Get-Date
    if ($now -lt $certificate.NotBefore -or $now -gt $certificate.NotAfter) {
        throw 'The CurrentUser code-signing certificate is not currently valid.'
    }

    $privateKey = $null
    try {
        $privateKey = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
        if ($null -eq $privateKey) {
            $privateKey = [Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPrivateKey($certificate)
        }
        if ($null -eq $privateKey -or $privateKey.GetType().Name -notin @('RSACng', 'ECDsaCng')) {
            throw 'The code-signing private key must be a Windows CNG key.'
        }
        $provider = $privateKey.Key.Provider.Provider
        $expectedProvider = if ($Assurance -ceq 'tpm') {
            'Microsoft Platform Crypto Provider'
        } else {
            'Microsoft Software Key Storage Provider'
        }
        if ($provider -cne $expectedProvider) {
            throw "The code-signing key provider does not match assurance '$Assurance' (expected: $expectedProvider; actual: $provider)."
        }
        $exportPolicy = [string]$privateKey.Key.ExportPolicy
        if ($exportPolicy -match 'AllowExport|AllowPlaintextExport') {
            throw "The code-signing key permits export: $exportPolicy"
        }
        return [ordered]@{
            Certificate = $certificate
            Assurance = $Assurance
            Provider = $provider
            ExportPolicy = $exportPolicy
            Thumbprint = $normalizedThumbprint
        }
    } finally {
        if ($null -ne $privateKey) { $privateKey.Dispose() }
    }
}

function Resolve-SignTool {
    if (-not [string]::IsNullOrWhiteSpace($SignToolPath)) {
        return (Resolve-Path -LiteralPath $SignToolPath).Path
    }
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $candidate = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -Recurse `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($null -eq $candidate) {
        throw 'signtool.exe was not found. Install the Windows SDK or set WCE_SIGNTOOL_PATH.'
    }
    return $candidate.FullName
}

function Get-EmbeddedAuthenticodeEvidence {
    param([Parameter(Mandatory = $true)][string]$FilePath)

    try {
        Add-Type -AssemblyName System.Security.Cryptography.Pkcs -ErrorAction Stop
    } catch {
        Add-Type -AssemblyName System.Security -ErrorAction Stop
    }
    $stream = [IO.File]::Open($FilePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $reader = New-Object IO.BinaryReader($stream)
    try {
        if ($stream.Length -lt 256) { throw 'Signed PE file is too small.' }
        $stream.Position = 0x3c
        $peOffset = $reader.ReadUInt32()
        if ($peOffset -gt $stream.Length - 256) { throw 'Signed PE header offset is invalid.' }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) { throw 'Signed file is not a PE image.' }
        [void]$reader.ReadBytes(20)
        $optionalHeaderStart = $stream.Position
        $magic = $reader.ReadUInt16()
        $dataDirectoryStart = switch ($magic) {
            0x10b { $optionalHeaderStart + 96 }
            0x20b { $optionalHeaderStart + 112 }
            default { throw 'Signed PE optional-header magic is unsupported.' }
        }
        $stream.Position = $dataDirectoryStart + (4 * 8)
        $certificateOffset = $reader.ReadUInt32()
        $certificateSize = $reader.ReadUInt32()
        if ($certificateOffset -eq 0 -or $certificateSize -lt 8 -or
            $certificateOffset + $certificateSize -gt $stream.Length) {
            throw 'Signed PE certificate table is missing or invalid.'
        }
        $stream.Position = $certificateOffset
        $certificateLength = $reader.ReadUInt32()
        [void]$reader.ReadUInt16()
        $certificateType = $reader.ReadUInt16()
        if ($certificateType -ne 2 -or $certificateLength -lt 8 -or
            $certificateLength -gt $certificateSize) {
            throw 'Signed PE does not contain a valid PKCS#7 WIN_CERTIFICATE.'
        }
        $encodedCms = $reader.ReadBytes([int]$certificateLength - 8)
        $cms = New-Object Security.Cryptography.Pkcs.SignedCms
        $cms.Decode($encodedCms)
        if ($cms.SignerInfos.Count -lt 1) { throw 'Authenticode CMS has no signer.' }
        $rfc3161Oid = '1.3.6.1.4.1.311.3.3.1'
        $timestampAttribute = $cms.SignerInfos[0].UnsignedAttributes |
            Where-Object { $_.Oid.Value -eq $rfc3161Oid -and $_.Values.Count -gt 0 } |
            Select-Object -First 1
        if ($null -eq $timestampAttribute) {
            throw 'Authenticode signature lacks an RFC3161 timestamp attribute.'
        }
        $timestampCms = New-Object Security.Cryptography.Pkcs.SignedCms
        $timestampCms.Decode($timestampAttribute.Values[0].RawData)
        $timestampCms.CheckSignature($true)
        if ($timestampCms.SignerInfos.Count -lt 1 -or
            $null -eq $timestampCms.SignerInfos[0].Certificate) {
            throw 'RFC3161 timestamp token has no signing certificate.'
        }
        return [ordered]@{
            SignerCertificate = $cms.SignerInfos[0].Certificate
            TimestampCertificate = $timestampCms.SignerInfos[0].Certificate
        }
    } finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Invoke-FreshWinVerifyTrust {
    param([Parameter(Mandatory = $true)][string]$FilePath)

    if ([string]::IsNullOrWhiteSpace($PSCommandPath)) {
        throw 'Private-PKI trust verification requires a script file entry point.'
    }
    $powerShell = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $powerShell -PathType Leaf)) {
        throw 'Unable to locate Windows PowerShell for the isolated trust probe.'
    }
    $arguments = @(
        '-NoLogo',
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath,
        '-Action', 'TrustProbe',
        '-Path', (Resolve-Path -LiteralPath $FilePath).Path,
        '-ExpectedSignerSha256', $ExpectedSignerSha256,
        '-ExpectedRootSha256', $ExpectedRootSha256,
        '-PrivateRootCertificatePath', (Resolve-Path -LiteralPath $PrivateRootCertificatePath).Path
    )
    $output = @(& $powerShell @arguments 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $details = ($output | Out-String).Trim()
        throw "Fresh private-PKI trust probe failed with exit code $exitCode`: $details"
    }
    try {
        $evidence = ($output | Out-String).Trim() | ConvertFrom-Json
    } catch {
        throw 'Fresh private-PKI trust probe returned malformed evidence.'
    }
    if ($null -eq $evidence -or $evidence.path -cne
        (Resolve-Path -LiteralPath $FilePath).Path -or
        $evidence.trustResult -isnot [int]) {
        throw 'Fresh private-PKI trust probe returned inconsistent evidence.'
    }
    return [int]$evidence.trustResult
}

function Assert-PrivatePkiSignature {
    param([Parameter(Mandatory = $true)][string]$FilePath, [Parameter(Mandatory = $true)]$Root)

    $resolved = (Resolve-Path -LiteralPath $FilePath).Path
    # WinVerifyTrust's chain engine can retain CERT_E_CHAINING when the public
    # issuer is added after this process starts. A fresh child sees the exact
    # CurrentUser\CA state while the parent retains deterministic cleanup.
    $trustResult = Invoke-FreshWinVerifyTrust $resolved
    if ($trustResult -ne [WdaPrivatePki.NativeMethods]::CertEUntrustedRoot) {
        $actualHex = Format-HResult $trustResult
        throw "Private-PKI Authenticode result was $actualHex instead of 0x800B0109: $resolved"
    }
    $embedded = Get-EmbeddedAuthenticodeEvidence $resolved
    $actualSigner = Assert-CodeSigningLeaf $embedded.SignerCertificate $Root
    $timestampEku = '1.3.6.1.5.5.7.3.8'
    if ($embedded.TimestampCertificate.EnhancedKeyUsageList.ObjectId -notcontains $timestampEku) {
        throw "Timestamp certificate lacks the timestamping EKU: $resolved"
    }
    return [ordered]@{
        path = $resolved
        signerSha256 = $actualSigner
        rootSha256 = $Root.Sha256
        timestampCertificateSha256 = Get-CertificateSha256 $embedded.TimestampCertificate.RawData
        trustResult = Format-HResult $trustResult
    }
}

function Invoke-VerifiedTimestampedSign {
    param(
        [Parameter(Mandatory = $true)][string]$SignTool,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)]$Root,
        [ValidateRange(1, 5)][int]$MaximumAttempts = 5
    )

    $unsignedBackup = "$Target.wda-unsigned"
    $workingTarget = "$Target.wda-signing$([IO.Path]::GetExtension($Target))"
    foreach ($temporaryPath in @($unsignedBackup, $workingTarget)) {
        if ([IO.File]::Exists($temporaryPath)) {
            throw "Refusing to overwrite a stale signing file: $temporaryPath"
        }
    }
    [IO.File]::Copy($Target, $unsignedBackup, $false)
    $signed = $false
    $lastFailure = 'unknown signing failure'
    try {
        for ($attempt = 1; $attempt -le $MaximumAttempts; $attempt++) {
            [IO.File]::Copy($unsignedBackup, $workingTarget, $true)
            $attemptArguments = [string[]]$Arguments.Clone()
            if ($attemptArguments.Count -eq 0 -or
                $attemptArguments[$attemptArguments.Count - 1] -cne $Target) {
                throw 'Signing arguments do not end with the expected target.'
            }
            $attemptArguments[$attemptArguments.Count - 1] = $workingTarget
            & $SignTool @attemptArguments | Out-Host
            if ($LASTEXITCODE -eq 0) {
                try {
                    Assert-PrivatePkiSignature $workingTarget $Root | Out-Null
                    for ($copyAttempt = 1; $copyAttempt -le 20; $copyAttempt++) {
                        try {
                            [IO.File]::Copy($workingTarget, $Target, $true)
                            $evidence = Assert-PrivatePkiSignature $Target $Root
                            $signed = $true
                            return $evidence
                        } catch {
                            $lastFailure = $_.Exception.Message
                            if ($copyAttempt -lt 20) {
                                Start-Sleep -Milliseconds 250
                            }
                        }
                    }
                } catch {
                    $lastFailure = $_.Exception.Message
                }
            } else {
                $lastFailure = "signtool.exe exited with code $LASTEXITCODE"
            }
            if ($attempt -lt $MaximumAttempts) {
                Start-Sleep -Seconds (2 * $attempt)
            }
        }
        throw "Timestamped signing failed after $MaximumAttempts clean attempts: $lastFailure"
    } finally {
        if (-not $signed -and [IO.File]::Exists($unsignedBackup)) {
            [IO.File]::Copy($unsignedBackup, $Target, $true)
        }
        if ([IO.File]::Exists($unsignedBackup)) {
            [IO.File]::Delete($unsignedBackup)
        }
        if ([IO.File]::Exists($workingTarget)) {
            [IO.File]::Delete($workingTarget)
        }
    }
}

$ExpectedSignerSha256 = $ExpectedSignerSha256.ToUpperInvariant()
$ExpectedRootSha256 = $ExpectedRootSha256.ToUpperInvariant()
$rootEvidence = Get-RootCertificate

if ($Action -eq 'TrustProbe') {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'TrustProbe requires -Path.' }
    $resolvedProbe = (Resolve-Path -LiteralPath $Path).Path
    $probeResult = [WdaPrivatePki.NativeMethods]::VerifyEmbeddedSignature($resolvedProbe)
    [ordered]@{
        path = $resolvedProbe
        trustResult = [int]$probeResult
        trustResultHex = Format-HResult $probeResult
    } | ConvertTo-Json -Compress
    exit 0
}

if ($Action -eq 'CacheIssuer') {
    $added = Add-PrivatePkiIssuerCertificate $rootEvidence
    [ordered]@{
        rootSha256 = $rootEvidence.Sha256
        issuerStore = 'CurrentUser\CA'
        newlyAdded = $added
        trustedRootInstalled = $false
    } | ConvertTo-Json -Compress
    exit 0
}

$signingMutex = $null
$signingMutexAcquired = $false
$issuerWasAdded = $false
try {
    if ($Action -eq 'Sign') {
        $signingMutex = [Threading.Mutex]::new(
            $false,
            'Local\LifeArchiveProject.WDA.PrivatePki.Signing.v1'
        )
        try {
            $signingMutexAcquired = $signingMutex.WaitOne([TimeSpan]::FromMinutes(5))
        } catch [Threading.AbandonedMutexException] {
            $signingMutexAcquired = $true
        }
        if (-not $signingMutexAcquired) {
            throw 'Timed out waiting for the private-PKI signing lock.'
        }
    }

    if ($Action -in @('Verify', 'Sign')) {
        # CurrentUser\CA is an issuer cache, not a trust anchor. Windows needs the
        # public self-issued certificate there to distinguish an exact untrusted
        # chain from an incomplete chain; Root and TrustedPublisher stay untouched.
        $issuerWasAdded = Add-PrivatePkiIssuerCertificate $rootEvidence
    }

    if ($Action -eq 'Verify') {
        if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Verify requires -Path.' }
        $evidence = Assert-PrivatePkiSignature $Path $rootEvidence
        $evidence | ConvertTo-Json -Compress
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
        throw "$Action requires -CertificateThumbprint."
    }
    if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
        throw "$Action requires -TimestampUrl."
    }
    $timestampUri = [uri]$TimestampUrl
    if (-not $timestampUri.IsAbsoluteUri -or
        $timestampUri.Scheme -notin @('http', 'https') -or
        -not [string]::IsNullOrEmpty($timestampUri.UserInfo)) {
        throw 'TimestampUrl must be an absolute HTTP(S) URL without credentials.'
    }
    $signingIdentity = Get-CurrentUserSigningCertificate `
        $CertificateThumbprint $rootEvidence $SigningAssurance
    $resolvedSignTool = Resolve-SignTool

    if ($Action -eq 'Preflight') {
        [ordered]@{
            certificateSha256 = $ExpectedSignerSha256
            rootSha256 = $rootEvidence.Sha256
            keyAssurance = $signingIdentity.Assurance
            keyProvider = $signingIdentity.Provider
            keyExportPolicy = $signingIdentity.ExportPolicy
            signTool = $resolvedSignTool
            rootInstalledAsTrusted = $false
        } | ConvertTo-Json -Compress
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Sign requires -Path.' }
    $resolvedTarget = (Resolve-Path -LiteralPath $Path).Path
    $targetName = [IO.Path]::GetFileName($resolvedTarget).ToLowerInvariant()
    if ($targetName -in @('wechatdb_client.dll', 'wechatdb_broker.exe')) {
        throw "Refusing to alter producer-owned native artifact: $targetName"
    }
    $signArguments = @(
        'sign',
        '/sha1', $signingIdentity.Thumbprint,
        '/s', 'My',
        '/fd', 'SHA256',
        '/tr', $timestampUri.AbsoluteUri,
        '/td', 'SHA256',
        '/ac', $rootEvidence.Path,
        '/d', $Description,
        $resolvedTarget
    )
    $signedEvidence = Invoke-VerifiedTimestampedSign `
        $resolvedSignTool $signArguments $resolvedTarget $rootEvidence
    $signedEvidence | ConvertTo-Json -Compress
} finally {
    try {
        if ($issuerWasAdded) {
            Remove-PrivatePkiIssuerCertificate $rootEvidence
        }
    } finally {
        try {
            if ($signingMutexAcquired) {
                $signingMutex.ReleaseMutex()
            }
        } finally {
            if ($null -ne $signingMutex) {
                $signingMutex.Dispose()
            }
        }
    }
}
