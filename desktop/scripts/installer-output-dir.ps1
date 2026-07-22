param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Read', 'Write', 'RemoveLegacyLinks', 'DeleteCustom')]
    [string] $Mode,
    [string] $DefaultSettingsPath = '',
    [string] $DefaultOutputPath = '',
    [string] $LegacySettingsPath1 = '',
    [string] $LegacySettingsPath2 = '',
    [string] $SelectedOutputPath = '',
    [string] $CandidateLinkPath1 = '',
    [string] $CandidateLinkPath2 = '',
    [string] $PathFile = '',
    [string] $LegacyOutputPath1 = '',
    [string] $LegacyOutputPath2 = ''
)

$ErrorActionPreference = 'Stop'

function Get-SettingsCandidates {
    @($DefaultSettingsPath, $LegacySettingsPath1, $LegacySettingsPath2) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
}

function Assert-RequiredPath([string] $Value, [string] $Name) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required"
    }
}

function Get-InstallerOutputDirectory {
    Assert-RequiredPath $DefaultSettingsPath 'DefaultSettingsPath'
    Assert-RequiredPath $DefaultOutputPath 'DefaultOutputPath'
    $result = $DefaultOutputPath
    foreach ($candidate in Get-SettingsCandidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        try {
            $json = Get-Content -LiteralPath $candidate -Raw | ConvertFrom-Json
            if ($null -eq $json) {
                continue
            }

            $pendingProperty = $json.PSObject.Properties['pendingOutputDir']
            if ($null -ne $pendingProperty -and $null -ne $pendingProperty.Value) {
                $value = [string] $pendingProperty.Value
                $result = if ([string]::IsNullOrWhiteSpace($value)) {
                    $DefaultOutputPath
                } else {
                    $value.Trim()
                }
                break
            }

            $value = [string] $json.outputDir
            $result = if ([string]::IsNullOrWhiteSpace($value)) {
                $DefaultOutputPath
            } else {
                $value.Trim()
            }
            # The first valid settings file is authoritative even when it uses
            # the default output directory. Do not revive a stale legacy value.
            break
        } catch {
            continue
        }
    }

    return $result
}

function Read-InstallerOutputDirectory {
    $result = Get-InstallerOutputDirectory
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::Write($result)
}

function ConvertTo-NormalizedFullPath([string] $Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Value.Trim())
        $root = [System.IO.Path]::GetPathRoot($fullPath)
        while (
            $fullPath.Length -gt $root.Length -and
            ($fullPath.EndsWith('\') -or $fullPath.EndsWith('/'))
        ) {
            $fullPath = $fullPath.Substring(0, $fullPath.Length - 1)
        }
        return $fullPath
    } catch {
        return $null
    }
}

function Test-PathsOverlap([string] $Left, [string] $Right) {
    $leftPath = ConvertTo-NormalizedFullPath $Left
    $rightPath = ConvertTo-NormalizedFullPath $Right
    if ($null -eq $leftPath -or $null -eq $rightPath) {
        return $false
    }

    if ([string]::Equals($leftPath, $rightPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    $separator = [System.IO.Path]::DirectorySeparatorChar
    return $leftPath.StartsWith(
        $rightPath + $separator,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or $rightPath.StartsWith(
        $leftPath + $separator,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Remove-InstallerLegacyOutputLinks {
    $configuredOutput = Get-InstallerOutputDirectory
    $configuredPath = ConvertTo-NormalizedFullPath $configuredOutput

    $candidates = @($CandidateLinkPath1, $CandidateLinkPath2) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
    foreach ($candidate in $candidates) {
        $candidatePath = ConvertTo-NormalizedFullPath $candidate
        if ($null -eq $candidatePath) {
            continue
        }

        try {
            $item = Get-Item -LiteralPath $candidatePath -Force -ErrorAction Stop
        } catch {
            continue
        }
        if (
            -not $item.PSIsContainer -or
            ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0
        ) {
            # Never remove a real directory or an object whose link target cannot
            # be inspected. This cleanup is only for known legacy junctions.
            continue
        }

        # Compare normalized lexical paths. The junction target commonly is the
        # default AppData output directory, so physical-target equality alone is
        # not a reason to preserve the obsolete install-directory link.
        if (-not (Test-PathsOverlap $candidatePath $configuredPath)) {
            [System.IO.Directory]::Delete($candidatePath, $false)
        }
    }
}

function Write-InstallerOutputDirectory {
    Assert-RequiredPath $DefaultSettingsPath 'DefaultSettingsPath'
    Assert-RequiredPath $DefaultOutputPath 'DefaultOutputPath'
    $selected = if ([string]::IsNullOrWhiteSpace($SelectedOutputPath)) {
        $DefaultOutputPath
    } else {
        $SelectedOutputPath.Trim()
    }
    $pending = if ([string]::Equals(
        $selected,
        $DefaultOutputPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        ''
    } else {
        $selected
    }

    $obj = @{}
    foreach ($candidate in Get-SettingsCandidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        try {
            $existing = Get-Content -LiteralPath $candidate -Raw | ConvertFrom-Json
            if ($null -eq $existing) {
                continue
            }
            $existing.PSObject.Properties | ForEach-Object {
                $obj[$_.Name] = $_.Value
            }
            break
        } catch {
            continue
        }
    }

    $obj['pendingOutputDir'] = $pending
    $targetPath = [System.IO.Path]::GetFullPath($DefaultSettingsPath)
    $dir = Split-Path -Parent $targetPath
    [System.IO.Directory]::CreateDirectory($dir) | Out-Null
    $json = [PSCustomObject] $obj | ConvertTo-Json -Depth 10
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $tempPath = Join-Path $dir (
        '.' + [System.IO.Path]::GetFileName($targetPath) + '.tmp-' + [System.Guid]::NewGuid().ToString('N')
    )
    $backupPath = $tempPath + '.backup'
    $stream = $null
    try {
        $bytes = $utf8NoBom.GetBytes($json)
        $stream = New-Object System.IO.FileStream(
            $tempPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None,
            4096,
            [System.IO.FileOptions]::WriteThrough
        )
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose()
        $stream = $null

        if ([System.IO.File]::Exists($targetPath)) {
            [System.IO.File]::Replace($tempPath, $targetPath, $backupPath, $true)
            [System.IO.File]::Delete($backupPath)
        } else {
            [System.IO.File]::Move($tempPath, $targetPath)
        }
    } finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        if ([System.IO.File]::Exists($tempPath)) {
            [System.IO.File]::Delete($tempPath)
        }
        if ([System.IO.File]::Exists($backupPath)) {
            [System.IO.File]::Delete($backupPath)
        }
    }
}

function Remove-InstallerCustomOutputDirectory {
    Assert-RequiredPath $DefaultOutputPath 'DefaultOutputPath'
    if ([string]::IsNullOrWhiteSpace($PathFile) -or -not (Test-Path -LiteralPath $PathFile)) {
        return
    }

    $target = (Get-Content -LiteralPath $PathFile -Raw).Trim()
    $defaults = @($DefaultOutputPath, $LegacyOutputPath1, $LegacyOutputPath2) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $isDefault = $false
    foreach ($defaultPath in $defaults) {
        if ([string]::Equals($target, $defaultPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            $isDefault = $true
            break
        }
    }

    if (-not $isDefault -and -not [string]::IsNullOrWhiteSpace($target) -and (Test-Path -LiteralPath $target)) {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    switch ($Mode) {
        'Read' { Read-InstallerOutputDirectory }
        'Write' { Write-InstallerOutputDirectory }
        'RemoveLegacyLinks' { Remove-InstallerLegacyOutputLinks }
        'DeleteCustom' { Remove-InstallerCustomOutputDirectory }
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
