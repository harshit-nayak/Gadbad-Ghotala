"""POST /analyse: score a recording with exactly the pipeline a live call gets.

The body is raw PCM16 mono at 16 kHz, little-endian -- the same format as a
/ws/audio chunk. The web frontend decodes whatever the user drops (mp3, m4a,
ogg, wav...) with the browser's own decoder and resamples before uploading, so
the backend needs no audio codecs and no multipart parser.

The audio is fed through a fresh TrackAnalyzer in 2 s chunks, as if it were
arriving on a call: the same Silero VAD, the same per-utterance windows, the
same detector and the same RiskTracker. So a file and a live call with the
same speech get the same verdict.

The response is NDJSON, one event per line, streamed as work happens -- a long
recording takes about a second per window on CPU, and the page shows windows as
they are scored instead of waiting on one silent request:

    {"type": "start", "name", "duration_ms", "detector"}
    {"type": "progress", "processed_ms"}
    {"type": "window", "index", "start_ms", "end_ms", "label", "p_bonafide", ...}
    {"type": "summary", "segments": [...], "analysis": {...}, "risk": {...}}
    {"type": "error", "message"}              instead of summary, if it fails

Inference shares the single analysis worker with live calls, so checking a
file during a call slows that call's verdicts rather than competing for cores.
Nothing is written to disk.
"""

import asyncio
import json
import logging

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app import config, detector
from app.analysis import AnalysisWindow, TrackAnalyzer
from app.risk import RiskTracker
from app.vad import VoiceActivityDetector
from app.websocket import EXECUTOR

logger = logging.getLogger("file_analysis")
router = APIRouter()

MAX_SECONDS = 30 * 60
CHUNK_SAMPLES = 2 * config.SAMPLE_RATE


def _line(event: dict) -> str:
    return json.dumps(event) + "\n"


def _ms(n_samples: int) -> int:
    return round(n_samples * 1000 / config.SAMPLE_RATE)


@router.post("/analyse")
async def analyse_audio(request: Request, name: str = "upload"):
    if config.AUTH_TOKEN:
        token = request.query_params.get("token")
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if token != config.AUTH_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.body()
    if not body or len(body) % config.BYTES_PER_SAMPLE:
        raise HTTPException(status_code=400,
                            detail="Body must be PCM16 mono 16 kHz audio (a whole number of samples)")
    if len(body) > MAX_SECONDS * config.SAMPLE_RATE * config.BYTES_PER_SAMPLE:
        raise HTTPException(status_code=413, detail=f"Recordings are limited to {MAX_SECONDS // 60} minutes")

    pcm = np.frombuffer(body, dtype="<i2")
    logger.info(f"Analysing upload '{name}': {len(pcm) / config.SAMPLE_RATE:.1f}s")
    return StreamingResponse(_stream(pcm, name), media_type="application/x-ndjson")


async def _stream(pcm: np.ndarray, name: str):
    loop = asyncio.get_running_loop()
    analyzer = TrackAnalyzer("far", VoiceActivityDetector())
    tracker = RiskTracker()
    segments: list[dict] = []
    duration_ms = _ms(len(pcm))

    async def score(window: AnalysisWindow) -> dict:
        result = await loop.run_in_executor(
            EXECUTOR, detector.score_window, window.samples, window.real_samples
        )
        snapshot = tracker.update(result["p_bonafide"])
        start_ms, end_ms = window.source_ranges[0] if window.source_ranges else (0, 0)
        return {
            "type": "window",
            "index": window.index,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "padded": window.padded,
            "label": result["label"],
            "p_bonafide": result["p_bonafide"],
            "p_spoof": result["p_spoof"],
            "detector": result.get("detector"),
            "detail": result.get("detail"),
            "latency_ms": result.get("latency_ms"),
            "session_risk": snapshot["session_risk"],
            "risk_band": snapshot["risk_band"],
        }

    yield _line({"type": "start", "name": name, "duration_ms": duration_ms,
                 "detector": detector.active_name()})
    try:
        for offset in range(0, len(pcm), CHUNK_SAMPLES):
            _, new_segments, windows = await loop.run_in_executor(
                EXECUTOR, analyzer.push_chunk, pcm[offset:offset + CHUNK_SAMPLES]
            )
            segments += [s.as_dict() for s in new_segments]
            for window in windows:
                yield _line(await score(window))
            yield _line({"type": "progress",
                         "processed_ms": min(duration_ms, _ms(offset + CHUNK_SAMPLES))})

        _, new_segments, windows = await loop.run_in_executor(EXECUTOR, analyzer.flush)
        segments += [s.as_dict() for s in new_segments]
        for window in windows:
            yield _line(await score(window))

        yield _line({
            "type": "summary",
            "segments": segments,
            "analysis": analyzer.stats(),
            "risk": tracker.summary(),
        })
        logger.info(f"Upload '{name}' done: {analyzer.windows_emitted} windows, "
                    f"band={tracker.band}, risk={tracker.risk:.2f}")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Analysis of upload '{name}' failed: {e}")
        yield _line({"type": "error", "message": f"Analysis failed: {e}"})
