$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$node = Join-Path $root ".tools\node-v22.14.0-win-x64\node.exe"
$vite = Join-Path $frontend "node_modules\vite\bin\vite.js"
$runDirectory = Join-Path $root ".run"
$stateFile = Join-Path $runDirectory "skywatch.json"

function Test-TcpPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-ListeningProcessId([int]$Port) {
    $connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) { return [int]$connection.OwningProcess }
    return 0
}

function Wait-ForUrl([string]$Url, [int]$Seconds = 45) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Timed out waiting for $Url"
}

foreach ($required in @($python, $node, $vite, (Join-Path $backend ".env"))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required file: $required"
    }
}

New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null

Write-Host "Starting PostgreSQL..."
& docker compose -f (Join-Path $root "docker-compose.yml") up -d postgres
if ($LASTEXITCODE -ne 0) { throw "Docker Compose could not start PostgreSQL." }

$databaseDeadline = (Get-Date).AddSeconds(45)
while (-not (Test-TcpPort 5433)) {
    if ((Get-Date) -ge $databaseDeadline) { throw "PostgreSQL did not become ready on port 5433." }
    Start-Sleep -Milliseconds 500
}

Write-Host "Applying database updates..."
Push-Location $backend
try {
    & $python -m scripts.add_position_ground_status
    if ($LASTEXITCODE -ne 0) { throw "Position schema update failed." }
    & $python -m scripts.add_geofences
    if ($LASTEXITCODE -ne 0) { throw "Geofence schema update failed." }
} finally {
    Pop-Location
}

$backendProcess = $null
$frontendProcess = $null

if (-not (Test-TcpPort 8000)) {
    $backendProcess = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDirectory "backend.log") -RedirectStandardError (Join-Path $runDirectory "backend-error.log")
} else {
    Write-Host "Backend port 8000 is already in use; checking the existing service."
}

try {
    Wait-ForUrl "http://127.0.0.1:8000/"

    if (-not (Test-TcpPort 5173)) {
        $frontendProcess = Start-Process -FilePath $node -ArgumentList @($vite, "--host", "127.0.0.1", "--port", "5173", "--strictPort") -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDirectory "frontend.log") -RedirectStandardError (Join-Path $runDirectory "frontend-error.log")
    } else {
        Write-Host "Frontend port 5173 is already in use; checking the existing service."
    }

    Wait-ForUrl "http://127.0.0.1:5173/"
} catch {
    if ($backendProcess) { Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($frontendProcess) { Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue }
    throw
}

@{
    backend_pid = if ($backendProcess) { $backendProcess.Id } else { Get-ListeningProcessId 8000 }
    frontend_pid = if ($frontendProcess) { $frontendProcess.Id } else { Get-ListeningProcessId 5173 }
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $stateFile

Write-Host ""
Write-Host "SkyWatch is ready: http://127.0.0.1:5173"
Write-Host "API documentation: http://127.0.0.1:8000/docs"
Write-Host "Logs: $runDirectory"
