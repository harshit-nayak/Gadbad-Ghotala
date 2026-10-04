# Starts the Document Verification & Signing Pipeline server (docPipeline\, Flask server on http://127.0.0.1:8765).
# The frontend Vite dev server automatically proxies /api and /root_ca.pem to this service.

$ErrorActionPreference = "Stop"
$pipelineDir = Join-Path $PSScriptRoot "docPipeline"
Set-Location $pipelineDir

# Check if port 8765 is already in use
$existing = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $ownerPid = $existing[0].OwningProcess
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    $procDesc = if ($proc) { "$ownerPid, $($proc.ProcessName)" } else { "$ownerPid" }
    Write-Host ""
    Write-Host "WARNING: Something is already listening on port 8765 (PID $procDesc)." -ForegroundColor Yellow
    Write-Host "If this is an existing docPipeline server, you can stop it with: Stop-Process -Id $ownerPid -Force" -ForegroundColor Yellow
    Write-Host ""
}

$venvPython = Join-Path $pipelineDir ".venv\Scripts\python.exe"
if (-not (Test-Path (Join-Path $pipelineDir ".venv"))) {
    Write-Host "Creating virtual environment in docPipeline\.venv..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Installing/verifying docPipeline dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install -q -r requirements.txt

# Run migrations if docsign.db is not yet present
if (-not (Test-Path (Join-Path $pipelineDir "docsign.db"))) {
    Write-Host "Initializing database schema with Alembic..." -ForegroundColor Cyan
    $env:DOCSIGN_DATABASE_URL = "sqlite:///$($pipelineDir.Replace('\', '/'))/docsign.db"
    & $venvPython -m alembic upgrade head
}

Write-Host "Starting docPipeline server on http://127.0.0.1:8765..." -ForegroundColor Green
& $venvPython run_server.py
