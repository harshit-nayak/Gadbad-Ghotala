# Convenience launcher so the capture client can be started from the project
# root, which is where a terminal opened on this workspace lands. The real
# script lives in "call-monitor\scripts\" and works from any directory --
# this just saves the cd.
#
#   .\run_client.ps1

& (Join-Path $PSScriptRoot "call-monitor\scripts\run_client.ps1") @args
