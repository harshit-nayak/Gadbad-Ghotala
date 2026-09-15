# Running it

Two commands, two terminals. Both work from the `sih deepfake` root
(where a terminal on this workspace opens by default).

```powershell
.\run_backend.ps1     # terminal 1 - wait for "Application startup complete"
```
```powershell
.\run_client.ps1      # terminal 2
```

Confirm the fine-tuned model came up, not a fallback:

```powershell
curl http://localhost:8000/health
# {"status":"ok","detector":"xlsr-mamba",...,"detectors":[{"name":"xlsr-mamba","state":"ready"}]}
```

`detector` must say `xlsr-mamba` — the Indic fine-tuned XLSR-Mamba. If it says
`placeholder`, the model didn't load (its `detail` says why) and the verdicts
mean nothing.

## Notes

- The `.ps1` needs a `.\` prefix or a path PowerShell can resolve. Running
  `scripts\run_client.ps1` from the wrong folder gives the misleading error
  `The module 'scripts' could not be loaded`.
- These root launchers just forward to `call-monitor\scripts\`. Either
  location works; the real scripts are cwd-independent.

## Without placing a call

```powershell
cd call-monitor\backend
.\.venv\Scripts\python scripts\simulate_call.py <audio file>   # replay through the live pipeline
.\.venv\Scripts\python scripts\verify_pipeline.py              # 13/13 self-checks
```

Full documentation: `call-monitor\README.md`
