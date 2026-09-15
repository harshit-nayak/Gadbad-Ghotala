# Convenience launcher so the backend can be started from the project root,
# which is where a terminal opened on this workspace lands. The real script
# lives in "call-monitor\scripts\" and works from any directory -- this
# just saves the cd.
#
#   .\run_backend.ps1            start it
#   .\run_backend.ps1 -Port 9000 on a different port
#   .\run_backend.ps1 -Reload    auto-restart on code changes (reloads a 1.36 GB model)

& (Join-Path $PSScriptRoot "call-monitor\scripts\run_backend.ps1") @args
