# Starts the GG web frontend (frontend\, Vite dev server on http://localhost:5173).
# It connects to the backend's live feed at ws://localhost:8000/ws/monitor;
# start .\run_backend.ps1 first to see real verdicts, otherwise it runs the
# simulated demo. Override the feed with $env:VITE_DETECTION_WS.

$frontend = Join-Path $PSScriptRoot "frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    npm --prefix $frontend install --no-audit --no-fund
}
npm --prefix $frontend run dev
