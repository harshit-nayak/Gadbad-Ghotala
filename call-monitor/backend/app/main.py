import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, detector, model, vad
from app.file_analysis import router as file_analysis_router
from app.models import HealthResponse
from app.monitor import router as monitor_router
from app.websocket import EXECUTOR, router as websocket_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Each detector is ~1.3 GB. Load them once here, at startup, rather than on
    # first use -- a call that has already started is the worst possible moment
    # to spend seconds loading a model.
    model.load()
    for entry in model.status()["detectors"]:
        reason = f" ({entry['detail']})" if entry.get("detail") else ""
        logger.info(f"Detector {entry['name']}: {entry['state']}{reason}")
    logger.info(f"Primary detector (drives the verdict): {detector.active_name()}")
    if detector.active_name() == detector.PLACEHOLDER_NAME:
        logger.warning(
            "Running on the PLACEHOLDER heuristic -- verdicts are NOT real "
            "deepfake detection. See /health for why."
        )
    yield
    EXECUTOR.shutdown(wait=False, cancel_futures=True)


app = FastAPI(
    title="Call Deepfake Screening Backend",
    description=(
        "Receives far/near PCM audio chunks from the desktop capture client, "
        "isolates the far party's speech with VAD, and scores each utterance "
        "with XLSR-Mamba (Indic fine-tune) as primary, plus AntiDeepfake and "
        "XLSR-SLS for comparison."
    ),
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Reports which detectors are actually live, so a fallback is visible
    rather than something you discover later."""
    info = model.status()
    return HealthResponse(
        status="ok",
        detector=detector.active_name(),
        model_state=info["state"],
        model_path=info.get("model_path"),
        provider=info.get("provider"),
        vad_backend=vad.active_backend_name(),
        detail=info.get("detail"),
        detectors=[
            {k: entry[k] for k in ("name", "state", "detail", "provider", "model_path", "license")
             if entry.get(k) is not None}
            for entry in info["detectors"]
        ],
    )


@app.get("/config")
async def effective_config():
    """The full effective configuration, as snapshotted into every session."""
    return config.snapshot()


app.include_router(websocket_router)
app.include_router(monitor_router)
app.include_router(file_analysis_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=config.RELOAD)
