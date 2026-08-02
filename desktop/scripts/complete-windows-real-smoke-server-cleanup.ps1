[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CleanupRecordPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$SshHost,
    [Parameter(Mandatory = $true)][string]$SshKeyPath,
    [Parameter(Mandatory = $true)][string]$RemoteCliPath,
    [Parameter(Mandatory = $true)][string]$RemoteDatabasePath,
    [string]$Actor = 'wda.release.acceptance',
    [string]$Reason = 'real-database-smoke-cleanup'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SshHost -cnotmatch '^[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+$') {
    throw 'SSH host must use the exact user@host form.'
}
if ($Actor -cnotmatch '^[A-Za-z0-9._-]{3,64}$') {
    throw 'Cleanup actor contains unsupported characters.'
}
if ($Reason -cnotmatch '^[A-Za-z0-9._-]{3,128}$') {
    throw 'Cleanup reason contains unsupported characters.'
}
foreach ($remotePath in @($RemoteCliPath, $RemoteDatabasePath)) {
    if ($remotePath -cnotmatch '^/[A-Za-z0-9_./-]+$' -or
        $remotePath -cmatch '(^|/)\.\.(/|$)' -or
        $remotePath -cmatch '//') {
        throw 'Remote administration paths must be normalized absolute Unix paths.'
    }
}

$cleanupPath = (Resolve-Path -LiteralPath $CleanupRecordPath).Path
$keyPath = (Resolve-Path -LiteralPath $SshKeyPath).Path
$receiptPath = [IO.Path]::GetFullPath($ReceiptPath)
if (-not [IO.Path]::IsPathRooted($ReceiptPath)) {
    throw 'Cleanup receipt path must be absolute.'
}
if ($cleanupPath -ceq $receiptPath) {
    throw 'Cleanup record and receipt paths must differ.'
}
if (Test-Path -LiteralPath $receiptPath) {
    throw 'Cleanup receipt already exists.'
}

$cleanup = Get-Content -LiteralPath $cleanupPath -Raw | ConvertFrom-Json
if ($cleanup.schemaVersion -ne 1 -or
    $cleanup.localDeviceKeyDeleted -ne $true -or
    $cleanup.serverSeatCleanupPending -ne $true) {
    throw 'Local smoke cleanup record is not ready for server unbind.'
}
$deviceId = [string]$cleanup.deviceIdHex
if ($deviceId -cnotmatch '^[0-9a-f]{64}$') {
    throw 'Smoke cleanup device ID is malformed.'
}
$cleanupHash = (Get-FileHash -LiteralPath $cleanupPath -Algorithm SHA256).Hash

$sshArguments = @(
    '-o', 'BatchMode=yes',
    '-o', 'ConnectTimeout=10',
    '-o', 'ConnectionAttempts=1',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-i', $keyPath,
    $SshHost
)
$remoteCli = @(
    'sudo', '-u', 'wcl-license',
    $RemoteCliPath,
    '--database', $RemoteDatabasePath
)

function Invoke-RemoteJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    foreach ($item in $Arguments) {
        if ($item -cnotmatch '^[A-Za-z0-9_./:-]+$') {
            throw 'Remote administration argument contains unsupported characters.'
        }
    }
    $remoteCommand = $Arguments -join ' '
    $output = & ssh @sshArguments $remoteCommand 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Remote license administration command failed.'
    }
    try {
        return ($output -join "`n") | ConvertFrom-Json
    } catch {
        throw 'Remote license administration returned invalid JSON.'
    }
}

$licenseResponse = Invoke-RemoteJson -Arguments ($remoteCli + @('license-list'))
$licenses = @($licenseResponse | ForEach-Object { $_ })
$bindingMatches = @()
foreach ($license in $licenses) {
    $licenseId = [string]$license.licenseId
    if ($licenseId -cnotmatch
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') {
        throw 'Remote authorization ID is malformed.'
    }
    $deviceResponse = Invoke-RemoteJson -Arguments (
        $remoteCli + @('device-list', $licenseId)
    )
    $devices = @($deviceResponse | ForEach-Object { $_ })
    foreach ($device in $devices) {
        if ([string]$device.hex -ceq $deviceId) {
            $bindingMatches += [pscustomobject]@{
                LicenseId = $licenseId
                RevokedAt = $device.revokedAt
            }
        }
    }
}
$response = $null
$targetLicenseId = ''
$recoveredFromAudit = $false
if ($bindingMatches.Count -gt 1) {
    throw "Expected at most one server binding for this smoke device; found $($bindingMatches.Count)."
}
if ($bindingMatches.Count -eq 1) {
    if ($null -ne $bindingMatches[0].RevokedAt) {
        throw 'Smoke device is already revoked; audited unbind is not applicable.'
    }
    $targetLicenseId = $bindingMatches[0].LicenseId
    $response = Invoke-RemoteJson -Arguments (
        $remoteCli + @(
            'device-unbind',
            $targetLicenseId,
            $deviceId,
            '--actor',
            $Actor,
            '--reason',
            $Reason
        )
    )
} else {
    $auditMatches = @()
    foreach ($license in $licenses) {
        $licenseId = [string]$license.licenseId
        $audit = Invoke-RemoteJson -Arguments (
            $remoteCli + @('audit-list', $licenseId, '--limit', '1000')
        )
        foreach ($event in $audit.events) {
            if ($event.eventType -ceq 'device_unbound' -and
                [string]$event.deviceId -ceq $deviceId -and
                [string]$event.actor -ceq $Actor -and
                [string]$event.reason -ceq $Reason) {
                $auditMatches += [pscustomobject]@{
                    LicenseId = $licenseId
                    Event = $event
                }
            }
        }
    }
    if ($auditMatches.Count -ne 1) {
        throw "No binding exists and the exact cleanup audit count is $($auditMatches.Count), expected 1."
    }
    $targetLicenseId = $auditMatches[0].LicenseId
    $event = $auditMatches[0].Event
    $response = [pscustomobject]@{
        unbound = $true
        deviceId = $deviceId
        licenseId = $targetLicenseId
        auditEventId = $event.id
        credentialsRevoked = $event.details.credentialsRevoked
        challengesInvalidated = $event.details.challengesInvalidated
        enrollmentChallengesInvalidated = (
            $event.details.enrollmentChallengesInvalidated
        )
        startupBindingsDeleted = $event.details.startupBindingsDeleted
        controlledDistributionsUnbound = (
            $event.details.controlledDistributionsUnbound
        )
    }
    $recoveredFromAudit = $true
}
if ($response.unbound -ne $true -or
    [string]$response.deviceId -cne $deviceId -or
    [string]$response.licenseId -cne $targetLicenseId) {
    throw 'Server did not confirm the exact smoke-device unbind.'
}
if ([int]$response.controlledDistributionsUnbound -ne 1) {
    throw 'Server did not release exactly one controlled distribution binding.'
}

$afterResponse = Invoke-RemoteJson -Arguments (
    $remoteCli + @('device-list', $targetLicenseId)
)
$afterDevices = @($afterResponse | ForEach-Object { $_ })
$afterMatches = @(
    $afterDevices | Where-Object { [string]$_.hex -ceq $deviceId }
)
if ($afterMatches.Count -ne 0) {
    throw 'Smoke device binding remained after server unbind.'
}

$auditEventId = [int64]$response.auditEventId
if ($auditEventId -le 0) {
    throw 'Server unbind returned an invalid audit event ID.'
}
$matchedBindingsBefore = if ($recoveredFromAudit) { 0 } else { 1 }
$receipt = [ordered]@{
    schemaVersion = 1
    buildId = [string]$cleanup.buildId
    cleanedAtUtc = [DateTime]::UtcNow.ToString('o')
    actor = $Actor
    reason = $Reason
    cleanupRecordSha256 = $cleanupHash
    matchedBindingsBefore = $matchedBindingsBefore
    matchedBindingsAfter = 0
    unbound = $true
    credentialsRevoked = [int]$response.credentialsRevoked
    challengesInvalidated = [int]$response.challengesInvalidated
    enrollmentChallengesInvalidated = [int]$response.enrollmentChallengesInvalidated
    startupBindingsDeleted = [int]$response.startupBindingsDeleted
    controlledDistributionsUnbound = (
        [int]$response.controlledDistributionsUnbound
    )
    remoteAuditEventId = $auditEventId
    recoveredFromAudit = $recoveredFromAudit
    sensitiveCleanupRecordDeleted = $true
}

$receiptDirectory = Split-Path -Parent $receiptPath
[IO.Directory]::CreateDirectory($receiptDirectory) | Out-Null
$preparedPath = "$receiptPath.$PID.prepared"
$cleanupDeleted = $false
try {
    $json = $receipt | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText(
        $preparedPath,
        "$json`n",
        [Text.UTF8Encoding]::new($false)
    )
    Remove-Item -LiteralPath $cleanupPath -Force
    $cleanupDeleted = $true
    Move-Item -LiteralPath $preparedPath -Destination $receiptPath
} finally {
    if (-not $cleanupDeleted) {
        Remove-Item -LiteralPath $preparedPath -Force -ErrorAction SilentlyContinue
    }
}

[ordered]@{
    schemaVersion = 1
    unbound = $true
    matchedBindingsBefore = $matchedBindingsBefore
    matchedBindingsAfter = 0
    auditRecorded = $true
    recoveredFromAudit = $recoveredFromAudit
    controlledDistributionsUnbound = (
        [int]$response.controlledDistributionsUnbound
    )
    sensitiveCleanupRecordDeleted = -not (Test-Path -LiteralPath $cleanupPath)
    receiptSha256 = (Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash
} | ConvertTo-Json -Compress
