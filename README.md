# SIH — live synthetic-voice detection

Detects cloned / synthetic voices during a live call and raises a risk alert
before a sensitive action is taken. Background and scope: [docs/project-context.md](docs/project-context.md).

## Layout

```
.
├── call-monitor/          live detection system
│   ├── backend/           FastAPI service: VAD → windows → detector → risk verdicts (/ws/audio, /ws/monitor, /analyse)
│   ├── client/            Tk desktop app: captures WhatsApp call audio, streams it to the backend
│   ├── scripts/           run_backend.ps1 / run_client.ps1 (called by the root launchers)
│   └── README.md          full documentation for backend + client
├── frontend/              React + Vite dashboard (own git repo: Gadbad-Ghotala, branch `frontend`)
├── docPipeline/           Cryptographic document signing & verification engine (doc-verify branch)
├── deepfake/              XLSR-SLS ONNX model: preprocessing, inference, ASVspoof5 evaluation
├── voice-player/          "fake caller" app for a second machine (plays clips into VB-Cable)
├── docs/                  project context, how to run
├── data/                  local test clips (not committed)
├── run_backend.ps1        start the backend   (http://localhost:8000)
├── run_client.ps1         start the capture client
├── run_docpipeline.ps1    start the doc signing/verification service (http://127.0.0.1:8765)
└── run_frontend.ps1       start the dashboard (http://localhost:5173)
```

## Quick start

```powershell
.\run_backend.ps1      # terminal 1 — wait for "Application startup complete"
.\run_client.ps1       # terminal 2
.\run_docpipeline.ps1  # terminal 3 — starts document verification & signing service
.\run_frontend.ps1     # terminal 4 — starts dashboard UI
```

Details and troubleshooting: [docs/running.md](docs/running.md).

## Not in git

Model weights, datasets, virtualenvs and recorded calls are ignored (see `.gitignore`).
The launchers fetch Silero VAD and the XLSR-Mamba base model on first run; the
fine-tuned head (`conformer_head_only.safetensors`) comes from the private
`XLSR_MAMBA_FINETUNED` branch, and `deepfake/xlsr-sls.onnx` from Hugging Face
(command in [deepfake/README.md](deepfake/README.md)).
