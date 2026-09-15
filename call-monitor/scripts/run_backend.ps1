Param(
    [int]$Port = 8000,
    # Auto-restart on code changes. Off by default: the backend loads a 1.36 GB
    # model at startup, and --reload pays that cost again on every file save.
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

# Refuse to start a second backend on the same port, no matter how it would
# have been launched (this script again, a VS Code Run/Debug button, a
# manually typed command...). Two servers racing for one port corrupts
# WebSocket traffic in confusing, intermittent ways.
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $ownerPid = $existing[0].OwningProcess
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    $procDesc = if ($proc) { "$ownerPid, $($proc.ProcessName)" } else { "$ownerPid" }
    Write-Host ""
    Write-Host "ERROR: Something is already listening on port $Port (PID $procDesc)." -ForegroundColor Red
    Write-Host "Starting a second backend here would corrupt traffic -- refusing to start." -ForegroundColor Red
    Write-Host "Stop the existing one first, e.g.:  Stop-Process -Id $ownerPid -Force" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
# `python -m pip`, never `pip.exe`: on Windows the Scripts\*.exe launchers bake
# in the venv's absolute path at creation time, so they break the moment the
# project folder is moved or renamed. python.exe keeps working, so this does too.
& ".\.venv\Scripts\python.exe" -m pip install -q -r requirements.txt

if (-not (Test-Path "models\silero_vad.onnx")) {
    Write-Host "Fetching the Silero VAD model (~2.2 MB, one time)..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" "scripts\fetch_silero.py"
}

# The detector (XLSR-Mamba, Indic fine-tune) needs PyTorch and its base model.
# If either step fails the backend still starts -- /health shows what loaded.
& ".\.venv\Scripts\python.exe" -m pip install -q -r requirements-antideepfake.txt
if (-not (Test-Path "models\xlsr-mamba\model_base.safetensors")) {
    Write-Host "Fetching the XLSR-Mamba base model (~1.28 GB, one time)..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" "scripts\fetch_xlsr_mamba.py"
}
# AntiDeepfake is off by default. Fetch it with scripts\fetch_antideepfake.py
# before adding it to DETECTORS for comparison.

Write-Host ""
Write-Host "Loading the 1.36 GB detection model (a few seconds warm, up to ~30s cold)." -ForegroundColor Cyan
Write-Host "Wait for 'Application startup complete', then start the client." -ForegroundColor Cyan
Write-Host ""

$env:PYTHONPATH = "."
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", $Port)
if ($Reload) { $uvicornArgs += "--reload" }
& ".\.venv\Scripts\python.exe" @uvicornArgs
