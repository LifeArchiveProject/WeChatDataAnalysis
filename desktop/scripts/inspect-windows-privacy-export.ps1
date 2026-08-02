[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [string]$SensitiveValuesPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolved = (Resolve-Path -LiteralPath $ArchivePath).Path
$sensitiveValues = @()
if (-not [string]::IsNullOrWhiteSpace($SensitiveValuesPath)) {
    $sensitiveFile = Get-Item -LiteralPath (Resolve-Path -LiteralPath $SensitiveValuesPath).Path
    if ($sensitiveFile.Length -le 0 -or $sensitiveFile.Length -gt 64KB) {
        throw 'Privacy export sensitive-value probe has an invalid size.'
    }
    $probe = Get-Content -LiteralPath $sensitiveFile.FullName -Raw | ConvertFrom-Json
    if ($null -eq $probe -or $probe -is [Array] -or $probe.schemaVersion -ne 1) {
        throw 'Privacy export sensitive-value probe is malformed.'
    }
    $sensitiveValues = @($probe.values)
    if ($sensitiveValues.Count -lt 1 -or $sensitiveValues.Count -gt 32) {
        throw 'Privacy export sensitive-value probe count is invalid.'
    }
    foreach ($value in $sensitiveValues) {
        if ($value -isnot [string] -or $value.Length -lt 3 -or $value.Length -gt 4096) {
            throw 'Privacy export sensitive-value probe contains an invalid value.'
        }
    }
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($resolved)
try {
    [int64]$totalBytes = 0
    foreach ($entry in @($archive.Entries)) {
        $name = [string]$entry.FullName
        if ([string]::IsNullOrWhiteSpace($name) -or
            $name.Contains('\') -or
            $name.StartsWith('/') -or
            $name.Contains(':')) {
            throw 'Privacy export contains a non-canonical entry name.'
        }
        $segments = @($name.Split('/') | Where-Object { $_ -ne '' })
        if ($segments.Count -eq 0 -or @($segments | Where-Object { $_ -eq '..' }).Count -gt 0) {
            throw 'Privacy export contains an unsafe entry name.'
        }
        $totalBytes += [int64]$entry.Length
        if ($entry.Length -lt 0 -or $entry.Length -gt 32MB -or $totalBytes -gt 128MB) {
            throw 'Privacy export exceeds the inspection size limit.'
        }
        $lowerName = $name.ToLowerInvariant()
        if ($lowerName.StartsWith('media/') -or $lowerName.Contains('/media/')) {
            throw 'Privacy export unexpectedly contains media.'
        }
        foreach ($value in $sensitiveValues) {
            if ($name.IndexOf($value, [StringComparison]::Ordinal) -ge 0) {
                throw 'Privacy export entry name contains a sensitive value.'
            }
        }
    }

    function Read-EntryBytes {
        param(
            [Parameter(Mandatory = $true)][string]$Name,
            [Parameter(Mandatory = $true)][int64]$MaximumBytes
        )

        $entries = @($archive.Entries | Where-Object FullName -CEQ $Name)
        if ($entries.Count -ne 1) {
            throw "Privacy export must contain exactly one $Name entry."
        }
        $entry = $entries[0]
        if ($entry.Length -le 0 -or $entry.Length -gt $MaximumBytes) {
            throw "Privacy export entry has an invalid size: $Name"
        }
        $stream = $entry.Open()
        try {
            $memory = [IO.MemoryStream]::new()
            try {
                $stream.CopyTo($memory)
                return $memory.ToArray()
            } finally {
                $memory.Dispose()
            }
        } finally {
            $stream.Dispose()
        }
    }

    function Read-JsonEntry {
        param([Parameter(Mandatory = $true)][string]$Name)
        $bytes = Read-EntryBytes $Name (4 * 1024 * 1024)
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
        $value = $text | ConvertFrom-Json
        if ($null -eq $value -or $value -is [Array]) {
            throw "Privacy export JSON root must be an object: $Name"
        }
        return $value
    }

    $manifest = Read-JsonEntry 'manifest.json'
    $report = Read-JsonEntry 'report.json'
    $nativeManifest = Read-EntryBytes '_integrity/manifest.json' (8 * 1024 * 1024)
    $nativeSignature = Read-EntryBytes '_integrity/signature.wes' 4096
    $accounts = @($manifest.accountsAvailable)

    if ($manifest.account -cne 'hidden' -or
        $report.account -cne 'hidden' -or
        $manifest.options.privacyMode -ne $true -or
        $manifest.options.includeMedia -ne $false -or
        $accounts.Count -ne 0) {
        throw 'Privacy export metadata is not fully redacted.'
    }
    if ($nativeSignature.Length -lt 4 -or
        [Text.Encoding]::ASCII.GetString($nativeSignature, 0, 4) -cne 'WES1') {
        throw 'Privacy export does not contain a WES1 signature.'
    }

    if ($sensitiveValues.Count -gt 0) {
        $strictUtf8 = [Text.UTF8Encoding]::new($false, $true)
        foreach ($entry in @($archive.Entries | Where-Object { -not $_.FullName.EndsWith('/') })) {
            if ($entry.Length -eq 0) {
                continue
            }
            $stream = $entry.Open()
            try {
                $memory = [IO.MemoryStream]::new()
                try {
                    $stream.CopyTo($memory)
                    try {
                        $text = $strictUtf8.GetString($memory.ToArray())
                    } catch [Text.DecoderFallbackException] {
                        continue
                    }
                } finally {
                    $memory.Dispose()
                }
            } finally {
                $stream.Dispose()
            }
            foreach ($value in $sensitiveValues) {
                if ($text.IndexOf($value, [StringComparison]::Ordinal) -ge 0) {
                    throw 'Privacy export text entry contains a sensitive value.'
                }
            }
        }
    }

    [ordered]@{
        schemaVersion = 1
        entryCount = @($archive.Entries).Count
        privacyMode = $true
        accountRedacted = $true
        accountsAvailableCount = 0
        nativeManifestBytes = $nativeManifest.Length
        wes1Bytes = $nativeSignature.Length
        wes1Present = $true
        mediaEntriesPresent = $false
        sensitiveValuesChecked = $sensitiveValues.Count
    } | ConvertTo-Json -Compress
} finally {
    $archive.Dispose()
}
