$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$stateFile = Join-Path $root ".run\skywatch.json"

if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    foreach ($processId in @($state.backend_pid, $state.frontend_pid)) {
        if ($processId -and $processId -gt 0) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $stateFile -Force
}

& docker compose -f (Join-Path $root "docker-compose.yml") stop
if ($LASTEXITCODE -ne 0) { throw "Docker Compose could not stop the services." }

Write-Host "SkyWatch services stopped. Database data was preserved."
