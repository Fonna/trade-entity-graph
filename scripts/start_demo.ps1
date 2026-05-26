<#
.SYNOPSIS
Starts the local FastAPI and Streamlit demo stack.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1 -PrepareDemoData
#>

[CmdletBinding()]
param(
    [string]$DatabasePath = "data/processed/trade_entity_graph.db",
    [switch]$PrepareDemoData,
    [switch]$NoStart,
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([Parameter(Mandatory = $true)][string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return Join-Path $RepoRoot $PathValue
}

function Invoke-Uv {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & uv --cache-dir $UvCache @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv command failed: uv --cache-dir $UvCache $($Arguments -join ' ')"
    }
}

function Invoke-UvText {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & uv --cache-dir $UvCache @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv command failed: uv --cache-dir $UvCache $($Arguments -join ' ')"
    }

    return ($output -join "`n").Trim()
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$ComputerName,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $asyncResult = $client.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne(300)) {
            return $false
        }
        $client.EndConnect($asyncResult)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) {
            $client.Close()
        }
    }
}

function Get-ProcessTreeIds {
    param([Parameter(Mandatory = $true)][int]$RootProcessId)

    $ids = @($RootProcessId)
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $RootProcessId" `
        -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        $ids += Get-ProcessTreeIds -RootProcessId ([int]$child.ProcessId)
    }

    return $ids
}

function Test-ExpectedPythonCommand {
    param(
        [Parameter(Mandatory = $true)]$ProcessInfo,
        [Parameter(Mandatory = $true)][string[]]$ExpectedCommandFragments
    )

    $executableName = Split-Path -Leaf ([string]$ProcessInfo.ExecutablePath)
    if ($executableName -notin @("python.exe", "pythonw.exe")) {
        return $false
    }

    $commandLine = [string]$ProcessInfo.CommandLine
    foreach ($fragment in $ExpectedCommandFragments) {
        if ($commandLine -notlike "*$fragment*") {
            return $false
        }
    }

    return $true
}

function Test-ProcessTreeContainsCommand {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][string[]]$ExpectedCommandFragments
    )

    foreach ($processId in Get-ProcessTreeIds -RootProcessId $RootProcessId) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" `
            -ErrorAction SilentlyContinue
        if ($processInfo -and (Test-ExpectedPythonCommand `
                    -ProcessInfo $processInfo `
                    -ExpectedCommandFragments $ExpectedCommandFragments)) {
            return $true
        }
    }

    return $false
}

function Stop-ProcessTree {
    param([Parameter(Mandatory = $true)][int]$RootProcessId)

    $processIds = @(Get-ProcessTreeIds -RootProcessId $RootProcessId)
    [array]::Reverse($processIds)
    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-RecordedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$ExpectedCommandFragments
    )

    if (-not (Test-Path $PidFile)) {
        return
    }

    $rawPid = (Get-Content -Raw -Path $PidFile).Trim()
    if ($rawPid -match "^\d+$") {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $rawPid" `
            -ErrorAction SilentlyContinue
        if ($processInfo) {
            if (-not (Test-ProcessTreeContainsCommand `
                        -RootProcessId ([int]$rawPid) `
                        -ExpectedCommandFragments $ExpectedCommandFragments)) {
                Write-Warning "Ignoring stale or unsafe $Name PID file: $PidFile"
                Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
                return
            }

            Write-Host "Stopping previous $Name process: $rawPid"
            Stop-ProcessTree -RootProcessId ([int]$rawPid)
            Start-Sleep -Seconds 1
        }
    }

    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Set-ListeningPidFile {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string[]]$ExpectedCommandFragments
    )

    $connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return
    }

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" `
        -ErrorAction SilentlyContinue
    if ($processInfo -and (Test-ExpectedPythonCommand `
                -ProcessInfo $processInfo `
                -ExpectedCommandFragments $ExpectedCommandFragments)) {
        $connection.OwningProcess | Set-Content -Path $PidFile
    }
}

function Start-DemoProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$OutLog,
        [Parameter(Mandatory = $true)][string]$ErrLog,
        [Parameter(Mandatory = $true)][string]$PidFile
    )

    $process = Start-Process -FilePath $PythonExecutable `
        -ArgumentList $Arguments `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -WindowStyle Hidden `
        -PassThru
    $process.Id | Set-Content -Path $PidFile
    Write-Host "Started $Name process: $($process.Id)"
    return $process
}

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    return $false
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$UvCache = Join-Path $RepoRoot ".uv-cache"
$ResolvedDatabasePath = Resolve-RepoPath $DatabasePath
$DatabasePathForEnv = if ([System.IO.Path]::IsPathRooted($DatabasePath)) {
    $ResolvedDatabasePath
} else {
    $DatabasePath
}
$DatabaseDirectory = Split-Path -Parent $ResolvedDatabasePath
$LogDirectory = Join-Path $RepoRoot "data/processed/logs"

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path $DatabaseDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null

$env:TEG_APP_ENV = "local"
$env:TEG_DATABASE_PATH = $DatabasePathForEnv
$env:STREAMLIT_SERVER_HEADLESS = "true"
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Install uv first: https://docs.astral.sh/uv/"
}

if (-not $SkipSync) {
    Write-Host "Syncing Python dependencies..."
    Invoke-Uv -Arguments @("sync", "--extra", "dev")
}

$databaseExisted = Test-Path $ResolvedDatabasePath
Write-Host "Initializing database: $DatabasePathForEnv"
Invoke-Uv -Arguments @("run", "python", "scripts\init_db.py")

if ($PrepareDemoData -or -not $databaseExisted) {
    Write-Host "Preparing demo data from data/demo..."
    Invoke-Uv -Arguments @("run", "python", "scripts\generate_demo_data.py")
    Invoke-Uv -Arguments @("run", "python", "scripts\import_demo_data.py")
    Invoke-Uv -Arguments @("run", "python", "scripts\seed_demo_reviews.py")
} else {
    Write-Host "Database already exists; skipping demo import. Use -PrepareDemoData to import demo rows again."
}

if ($NoStart) {
    Write-Host "Setup finished; -NoStart was supplied, so services were not started."
    exit 0
}

$apiOutLog = Join-Path $LogDirectory "fastapi-api.log"
$apiErrLog = Join-Path $LogDirectory "fastapi-api.err.log"
$uiOutLog = Join-Path $LogDirectory "streamlit-ui.log"
$uiErrLog = Join-Path $LogDirectory "streamlit-ui.err.log"
$apiPidFile = Join-Path $LogDirectory "fastapi-api.pid"
$uiPidFile = Join-Path $LogDirectory "streamlit-ui.pid"
$apiUrl = "http://127.0.0.1:8000"
$uiUrl = "http://127.0.0.1:8501"

$PythonExecutable = Invoke-UvText -Arguments @("run", "python", "-c", "import sys; print(sys.executable)")
$apiArguments = @(
    "-m",
    "uvicorn",
    "trade_entity_graph.api.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000"
)
$uiArguments = @(
    "-m",
    "streamlit",
    "run",
    "src/trade_entity_graph/ui/streamlit_app.py",
    "--server.address",
    "127.0.0.1",
    "--server.port",
    "8501",
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false"
)

Stop-RecordedProcess -PidFile $apiPidFile `
    -Name "API" `
    -ExpectedCommandFragments @("uvicorn", "trade_entity_graph.api.main:app", "8000")
Stop-RecordedProcess -PidFile $uiPidFile `
    -Name "Streamlit" `
    -ExpectedCommandFragments @("streamlit", "streamlit_app.py", "8501")

if (Test-TcpPort -ComputerName "127.0.0.1" -Port 8000) {
    throw "Port 8000 is already in use by another process. Stop it, then run this script again."
}

if (Test-TcpPort -ComputerName "127.0.0.1" -Port 8501) {
    throw "Port 8501 is already in use by another process. Stop it, then run this script again."
}

$apiProcess = Start-DemoProcess -Name "API" `
    -Arguments $apiArguments `
    -OutLog $apiOutLog `
    -ErrLog $apiErrLog `
    -PidFile $apiPidFile
$uiProcess = Start-DemoProcess -Name "Streamlit" `
    -Arguments $uiArguments `
    -OutLog $uiOutLog `
    -ErrLog $uiErrLog `
    -PidFile $uiPidFile

$apiReady = Wait-HttpOk -Url "$apiUrl/health"
$uiReady = Wait-HttpOk -Url $uiUrl

if (-not $apiReady -or -not $uiReady) {
    Stop-ProcessTree -RootProcessId $apiProcess.Id
    Stop-ProcessTree -RootProcessId $uiProcess.Id
    Remove-Item -LiteralPath $apiPidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $uiPidFile -Force -ErrorAction SilentlyContinue
    Write-Warning "One or more services did not respond before the timeout. Check data/processed/logs/."
    exit 1
}

Set-ListeningPidFile -Port 8000 `
    -PidFile $apiPidFile `
    -ExpectedCommandFragments @("uvicorn", "trade_entity_graph.api.main:app", "8000")
Set-ListeningPidFile -Port 8501 `
    -PidFile $uiPidFile `
    -ExpectedCommandFragments @("streamlit", "streamlit_app.py", "8501")

Write-Host ""
Write-Host "Demo stack:"
Write-Host "  API:       $apiUrl"
Write-Host "  API docs:  $apiUrl/docs"
Write-Host "  Streamlit: $uiUrl"
Write-Host "  Database:  $DatabasePathForEnv"
Write-Host "  Demo CSVs: data/demo/"
Write-Host "  Logs:      data/processed/logs/"
