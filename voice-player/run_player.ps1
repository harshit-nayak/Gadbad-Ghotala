# Creates .venv on first run, installs requirements, then starts the player.
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$venv = Join-Path $here ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$marker = Join-Path $venv "installed.txt"

if (-not (Test-Path $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv $venv } else { & python -m venv $venv }
    if ($LASTEXITCODE -ne 0) { throw "Could not create a virtualenv - is Python 3.10+ installed?" }
}
if (-not (Test-Path $marker)) {
    & $python -m pip install -r (Join-Path $here "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Set-Content -Path $marker -Value (Get-Date -Format o) -Encoding utf8
}
& $python (Join-Path $here "player.py")
