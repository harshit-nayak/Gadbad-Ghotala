$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$clientDir = Join-Path $root "client"
Set-Location $clientDir

# Refuse to start a second GUI instance, no matter how it would have been
# launched (this script again, a VS Code Run/Debug button, a manually typed
# command...). Matches on the script name, not the interpreter, so it
# catches a duplicate regardless of which Python launched it -- and matches
# on just "app.py" (not a full absolute path) since this script itself
# launches python.exe with a relative argument. A Windows venv's
# Scripts\python.exe is a launcher that spawns the real interpreter as a
# child process, so a single legitimate instance can show up as two
# python.exe rows here; that's fine -- any match at all means "already
# running", which is exactly what should block a second launch.
$existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*app.py*" }
if ($existing) {
    $match = $existing | Select-Object -First 1
    Write-Host ""
    Write-Host "ERROR: The desktop capture client already appears to be running (PID $($match.ProcessId))." -ForegroundColor Red
    Write-Host "Refusing to start a second copy -- close that window first, or:" -ForegroundColor Red
    Write-Host "  Stop-Process -Id $($match.ProcessId) -Force" -ForegroundColor Yellow
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
& ".\.venv\Scripts\python.exe" app.py
