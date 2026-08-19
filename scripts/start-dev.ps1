[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Get-ConfiguredPort {
    param(
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] [int] $Default
    )

    $raw = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Default
    }

    $port = 0
    if (-not [int]::TryParse($raw.Trim(), [ref] $port) -or $port -lt 1 -or $port -gt 65535) {
        throw "Invalid $Name value: $raw"
    }
    return $port
}

function Get-EndpointState {
    param([Parameter(Mandatory = $true)] [string] $Uri)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return [pscustomobject] @{
            Ready = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
            StatusCode = [int] $response.StatusCode
            Error = $null
        }
    } catch {
        return [pscustomobject] @{
            Ready = $false
            StatusCode = $null
            Error = $_.Exception.Message
        }
    }
}

function Get-ListeningProcessInfo {
    param([Parameter(Mandatory = $true)] [int] $Port)

    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($connection in $connections | Sort-Object OwningProcess -Unique) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
        [pscustomobject] @{
            Port = $Port
            ProcessId = $connection.OwningProcess
            Name = if ($process) { $process.Name } else { "unknown" }
            CommandLine = if ($process) { $process.CommandLine } else { $null }
        }
    }
}

function Invoke-WithEnvironment {
    param(
        [Parameter(Mandatory = $true)] [hashtable] $Values,
        [Parameter(Mandatory = $true)] [scriptblock] $Action
    )

    $previous = @{}
    foreach ($name in $Values.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, [string] $Values[$name], "Process")
    }

    try {
        & $Action
    } finally {
        foreach ($name in $Values.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
        }
    }
}

function Get-LogTail {
    param([Parameter(Mandatory = $true)] [string] $Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return "(log file is empty or not created yet)"
    }
    return ((Get-Content -LiteralPath $Path -Tail 30 -ErrorAction SilentlyContinue) -join [Environment]::NewLine)
}

function Wait-ForEndpoint {
    param(
        [Parameter(Mandatory = $true)] [string] $Label,
        [Parameter(Mandatory = $true)] [string] $Uri,
        [Parameter(Mandatory = $true)] [System.Diagnostics.Process] $Process,
        [Parameter(Mandatory = $true)] [string] $ErrorLog,
        [int] $TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            $tail = Get-LogTail -Path $ErrorLog
            throw "$Label exited before becoming ready (exit code $($Process.ExitCode)).`n$tail"
        }

        $state = Get-EndpointState -Uri $Uri
        if ($state.Ready) {
            return
        }
        Start-Sleep -Seconds 1
    }

    $tail = Get-LogTail -Path $ErrorLog
    throw "Timed out waiting for $Label at $Uri.`n$tail"
}

function Start-Backend {
    param(
        [Parameter(Mandatory = $true)] [string] $Python,
        [Parameter(Mandatory = $true)] [int] $Port,
        [Parameter(Mandatory = $true)] [string] $OutputPath,
        [Parameter(Mandatory = $true)] [string] $ErrorPath
    )

    $values = @{
        WECHAT_TOOL_HOST = "127.0.0.1"
        WECHAT_TOOL_PORT = [string] $Port
        PYTHONIOENCODING = "utf-8"
        PYTHONUNBUFFERED = "1"
    }
    $result = $null
    Invoke-WithEnvironment -Values $values -Action {
        $script:backendProcess = Start-Process -FilePath $Python `
            -ArgumentList @("-u", "main.py") `
            -WorkingDirectory $projectRoot `
            -RedirectStandardOutput $OutputPath `
            -RedirectStandardError $ErrorPath `
            -WindowStyle Hidden `
            -PassThru
    }
    return $script:backendProcess
}

function Start-Frontend {
    param(
        [Parameter(Mandatory = $true)] [string] $Npm,
        [Parameter(Mandatory = $true)] [int] $Port,
        [Parameter(Mandatory = $true)] [int] $BackendPort,
        [Parameter(Mandatory = $true)] [string] $OutputPath,
        [Parameter(Mandatory = $true)] [string] $ErrorPath
    )

    $values = @{
        NUXT_HOST = "127.0.0.1"
        NUXT_PORT = [string] $Port
        WECHAT_TOOL_PORT = [string] $BackendPort
    }
    Invoke-WithEnvironment -Values $values -Action {
        $script:frontendProcess = Start-Process -FilePath $Npm `
            -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1") `
            -WorkingDirectory (Join-Path $projectRoot "frontend") `
            -RedirectStandardOutput $OutputPath `
            -RedirectStandardError $ErrorPath `
            -WindowStyle Hidden `
            -PassThru
    }
    return $script:frontendProcess
}

try {
    $frontendPort = Get-ConfiguredPort -Name "NUXT_PORT" -Default 3000
    $backendPort = Get-ConfiguredPort -Name "WECHAT_TOOL_PORT" -Default 10392
    $frontendUrl = "http://127.0.0.1:$frontendPort/"
    $backendHealthUrl = "http://127.0.0.1:$backendPort/api/health"

    $python = Join-Path $projectRoot ".venv\Scripts\python.exe"
    $frontendDir = Join-Path $projectRoot "frontend"
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    $npm = if ($npmCommand) { $npmCommand.Source } else { $null }

    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Missing backend interpreter: $python. Run uv sync --no-editable first."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules") -PathType Container)) {
        throw "Missing frontend dependencies: $frontendDir\node_modules. Run npm install in frontend first."
    }
    if ([string]::IsNullOrWhiteSpace($npm) -or -not (Test-Path -LiteralPath $npm -PathType Leaf)) {
        throw "npm.cmd was not found on PATH. Install Node.js and reopen the terminal."
    }

    $logRoot = Join-Path ([Environment]::GetEnvironmentVariable("TEMP")) "WeChatDataAnalysis-dev"
    $runId = Get-Date -Format "yyyyMMdd-HHmmss"
    $runLogDir = Join-Path $logRoot $runId
    New-Item -ItemType Directory -Path $runLogDir -Force | Out-Null
    $backendOut = Join-Path $runLogDir "backend.stdout.log"
    $backendErr = Join-Path $runLogDir "backend.stderr.log"
    $frontendOut = Join-Path $runLogDir "frontend.stdout.log"
    $frontendErr = Join-Path $runLogDir "frontend.stderr.log"

    $sourceProbe = @(& $python -c "import json, sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd() / 'src')); import wechat_decrypt_tool; print(json.dumps(str(Path(wechat_decrypt_tool.__file__).resolve()), ensure_ascii=True))" 2>&1)
    $sourceExitCode = $LASTEXITCODE
    if ($sourceExitCode -ne 0) {
        throw "Unable to import workspace source with ${python}:`n$($sourceProbe -join [Environment]::NewLine)"
    }
    $sourcePath = (($sourceProbe | Select-Object -Last 1).ToString().Trim() | ConvertFrom-Json).ToString()
    $expectedSourceRoot = (Join-Path $projectRoot "src")
    if (-not $sourcePath.StartsWith($expectedSourceRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Python resolved wechat_decrypt_tool outside the workspace: $sourcePath"
    }

    Write-Host "WeChatDataAnalysis development launcher"
    Write-Host "Project: $projectRoot"
    Write-Host "Python:  $python"
    Write-Host "Source:  $sourcePath"
    Write-Host "Logs:    $runLogDir"

    $backendState = Get-EndpointState -Uri $backendHealthUrl
    $backendProcess = $null
    if ($backendState.Ready) {
        $backendListeners = @(Get-ListeningProcessInfo -Port $backendPort)
        $backendPids = if ($backendListeners.Count -gt 0) { ($backendListeners.ProcessId -join ", ") } else { "unknown" }
        Write-Host "Backend is already healthy at http://127.0.0.1:$backendPort (reusing PID $backendPids)."
    } else {
        $backendListeners = @(Get-ListeningProcessInfo -Port $backendPort)
        if ($backendListeners.Count -gt 0) {
            $details = ($backendListeners | ForEach-Object { "PID $($_.ProcessId) $($_.Name)" }) -join ", "
            throw "Backend port $backendPort is occupied but /api/health is not healthy ($details). No process was stopped."
        }
        $backendProcess = Start-Backend -Python $python -Port $backendPort -OutputPath $backendOut -ErrorPath $backendErr
        Write-Host "Started backend PID $($backendProcess.Id)."
        Wait-ForEndpoint -Label "backend" -Uri $backendHealthUrl -Process $backendProcess -ErrorLog $backendErr
        Write-Host "Backend is ready."
    }

    $frontendState = Get-EndpointState -Uri $frontendUrl
    $frontendProcess = $null
    if ($frontendState.Ready) {
        $frontendListeners = @(Get-ListeningProcessInfo -Port $frontendPort)
        $frontendPids = if ($frontendListeners.Count -gt 0) { ($frontendListeners.ProcessId -join ", ") } else { "unknown" }
        Write-Host "Frontend is already responding at $frontendUrl (reusing PID $frontendPids)."
    } else {
        $frontendListeners = @(Get-ListeningProcessInfo -Port $frontendPort)
        if ($frontendListeners.Count -gt 0) {
            $details = ($frontendListeners | ForEach-Object { "PID $($_.ProcessId) $($_.Name)" }) -join ", "
            throw "Frontend port $frontendPort is occupied but $frontendUrl is not ready ($details). No process was stopped."
        }
        $frontendProcess = Start-Frontend -Npm $npm -Port $frontendPort -BackendPort $backendPort -OutputPath $frontendOut -ErrorPath $frontendErr
        Write-Host "Started frontend PID $($frontendProcess.Id)."
        Wait-ForEndpoint -Label "frontend" -Uri $frontendUrl -Process $frontendProcess -ErrorLog $frontendErr
        Write-Host "Frontend is ready."
    }

    Write-Host ""
    Write-Host "Frontend:   $frontendUrl"
    Write-Host "Backend:    http://127.0.0.1:$backendPort"
    Write-Host "API docs:   http://127.0.0.1:$backendPort/docs"
    Write-Host "Health:     $backendHealthUrl"
    Write-Host "Log folder: $runLogDir"
    $openBrowser = [Environment]::GetEnvironmentVariable("WECHAT_TOOL_OPEN_BROWSER", "Process")
    if ($openBrowser -ne "0") {
        Start-Process -FilePath $frontendUrl | Out-Null
        Write-Host "Browser opened."
    }
    Write-Host ""
    Write-Host "No WeChat send or contact actions are performed by this launcher."
    Write-Host "Close this window only stops the launcher; use the recorded process IDs to manage processes started by this run."
} catch {
    Write-Error $_
    exit 1
}
