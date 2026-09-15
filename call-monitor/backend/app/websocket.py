"""The /ws/audio endpoint: ingest chunks, analyse speech, emit verdicts.

Ingestion and analysis are deliberately separated. The WebSocket loop does only
cheap, bounded work -- validate, ack, write to disk -- and hands the audio to a
per-session background task, which runs VAD, window assembly and model
inference on a worker thread. Inference on a 1.36 GB model takes a few hundred
milliseconds; doing it inline would stall the event loop and, with it, every
ack and every other track, on a live call.

If analysis falls behind, the queue drops its OLDEST chunk rather than growing
without bound: on a live call, a stale verdict is worth less than a current
one. Recordings are written before queueing, so a drop never loses audio from
disk -- only from scoring -- and every drop is logged to events.jsonl.
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app import config, detector, model
from app.analysis import AnalysisWindow, TrackAnalyzer
from app.artifacts import SessionArtifacts
from app.audio import validate_pcm_chunk
from app.monitor import HUB
from app.models import (
    AudioChunkMetadata,
    ChunkAckMessage,
    ErrorMessage,
    SessionStartMessage,
    SessionSummaryMessage,
    VerdictMessage,
)
from app.recordings import RECORDINGS_DIR, SessionRecorder
from app.risk import RiskTracker
from app.vad import VoiceActivityDetector

logger = logging.getLogger("websocket_audio")
router = APIRouter()

# One worker: the big model saturates the cores it is given, so running two
# inferences at once on a laptop trades latency for nothing.
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")


class TrackState:
    def __init__(self):
        self.expected_sequence = 0
        self.total_chunks = 0
        self.total_bytes = 0


class SessionState:
    def __init__(self, session_id: str, sample_rate: int, channels: int,
                 encoding: str, source: str = ""):
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.encoding = encoding
        self.source = source
        self.started_at = time.time()

        self.tracks: dict[str, TrackState] = {"far": TrackState(), "near": TrackState()}
        self.pending_metadata: AudioChunkMetadata | None = None

        self.recorder = SessionRecorder(session_id)
        self.artifacts = SessionArtifacts(session_id)
        self.analyzers: dict[str, TrackAnalyzer] = {}
        self.risk: dict[str, RiskTracker] = {}

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.ANALYSIS_QUEUE_SIZE)
        self.worker: asyncio.Task | None = None
        self.dropped_chunks = 0
        self.finished = False

    # -- lazily built per-track state --------------------------------------

    def track(self, name: str) -> TrackState:
        return self.tracks.setdefault(name, TrackState())

    def analyzer(self, name: str) -> TrackAnalyzer:
        analyzer = self.analyzers.get(name)
        if analyzer is None:
            analyzer = TrackAnalyzer(name, VoiceActivityDetector())
            self.analyzers[name] = analyzer
            logger.info(f"[{self.session_id[:8]}] analysing '{name}' (VAD={analyzer.vad.backend_name})")
        return analyzer

    def risk_tracker(self, name: str) -> RiskTracker:
        return self.risk.setdefault(name, RiskTracker())

    # -- analysis (runs on the executor thread) ----------------------------

    def process_chunk(self, track: str, pcm: bytes) -> list[str]:
        """VAD -> speech accumulation -> windows -> scoring. Returns verdict JSON."""
        analyzer = self.analyzer(track)
        kept, segments, windows = analyzer.push_chunk(np.frombuffer(pcm, dtype="<i2"))
        return self._consume(track, kept, segments, windows)

    def flush_track(self, track: str) -> list[str]:
        """Settle the VAD at end of session and score any final full window."""
        analyzer = self.analyzers.get(track)
        if analyzer is None:
            return []
        kept, segments, windows = analyzer.flush()
        return self._consume(track, kept, segments, windows)

    def _consume(self, track, kept, segments, windows) -> list[str]:
        if kept:
            self.recorder.write_speech(
                track, config.SAMPLE_RATE, np.concatenate(kept).tobytes()
            )
        for segment in segments:
            self.artifacts.segment(track, segment.as_dict())
        return [self._score(track, window) for window in windows]

    def _score(self, track: str, window: AnalysisWindow) -> str:
        t0 = time.perf_counter()
        # Every loaded detector scores this window; the primary's result drives
        # the verdict and the risk, the others ride along under "secondary".
        result = detector.score_window(window.samples, window.real_samples)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        snapshot = self.risk_tracker(track).update(result["p_bonafide"])
        ranges = window.source_ranges

        # The exact audio the model saw, beside the exact numbers it returned.
        self.recorder.write_window(track, window.index, config.SAMPLE_RATE,
                                   window.samples.tobytes())
        self.artifacts.window(track, window.index, {
            "window": window.as_dict(),
            "result": result,
            "risk": snapshot,
            "latency_ms": latency_ms,
            "wav": f"{track}/windows/window_{window.index:04d}.wav",
        })

        verdict = VerdictMessage(
            session_id=self.session_id,
            track=track,
            sequence=window.index,
            score=result["p_spoof"],
            label=result["label"],
            detail=result["detail"],
            p_bonafide=result["p_bonafide"],
            p_spoof=result["p_spoof"],
            score_logprob=result.get("score_logprob"),
            detector=result["detector"],
            secondary=result.get("secondary"),
            session_risk=snapshot["session_risk"],
            risk_band=snapshot["risk_band"],
            recommendation=snapshot["recommendation"],
            speech_seconds=round(window.speech_seconds_total, 2),
            window_start_ms=ranges[0][0] if ranges else None,
            window_end_ms=ranges[-1][1] if ranges else None,
            spans_discontinuity=window.spans_discontinuity,
            padded=window.padded,
            latency_ms=latency_ms,
        )
        self.artifacts.verdict(verdict.model_dump())
        return verdict.model_dump_json()

    # -- queueing ----------------------------------------------------------

    def enqueue(self, track: str, sequence: int, pcm: bytes) -> None:
        try:
            self.queue.put_nowait((track, pcm))
            return
        except asyncio.QueueFull:
            pass
        try:
            self.queue.get_nowait()
            self.queue.task_done()
            self.dropped_chunks += 1
            logger.warning(
                f"[{self.session_id[:8]}] analysis backlog: dropped an older {track} chunk "
                f"(total dropped: {self.dropped_chunks}). Audio is still recorded to disk."
            )
            self.artifacts.event("analysis_backlog_drop", track=track, sequence=sequence,
                                 total_dropped=self.dropped_chunks)
        except asyncio.QueueEmpty:
            pass
        try:
            self.queue.put_nowait((track, pcm))
        except asyncio.QueueFull:
            pass

    def summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "source": self.source,
            "started_at": self.started_at,
            "ended_at": time.time(),
            "duration_s": round(time.time() - self.started_at, 2),
            "detector": detector.active_name(),
            "model": model.status(),
            "config": config.snapshot(),
            "chunks": {
                name: {"chunks": t.total_chunks, "bytes": t.total_bytes}
                for name, t in self.tracks.items()
            },
            "analysis": {name: a.stats() for name, a in self.analyzers.items()},
            "risk": {name: r.summary() for name, r in self.risk.items()},
            "dropped_chunks": self.dropped_chunks,
            "artifacts_dir": str((RECORDINGS_DIR / self.session_id).resolve()),
        }


# --------------------------------------------------------------------------- #
# background analysis worker
# --------------------------------------------------------------------------- #
async def _analysis_worker(session: SessionState, websocket: WebSocket) -> None:
    loop = asyncio.get_running_loop()
    while True:
        item = await session.queue.get()
        try:
            if item is None:
                return
            track, pcm = item
            try:
                messages = await loop.run_in_executor(
                    EXECUTOR, session.process_chunk, track, pcm
                )
            except Exception as e:  # noqa: BLE001
                logger.exception(f"Analysis failed for a {track} chunk: {e}")
                session.artifacts.event("analysis_error", track=track, error=str(e))
                continue
            for message in messages:
                await _send(websocket, message)
                await HUB.publish(message)
        finally:
            session.queue.task_done()


async def _send(websocket: WebSocket, text: str) -> bool:
    try:
        await websocket.send_text(text)
        return True
    except Exception:  # noqa: BLE001
        return False  # client already gone; teardown handles the rest


async def _finish(session: SessionState, websocket: WebSocket, reason: str) -> None:
    """Settle everything for a session exactly once: stop the worker, flush the
    VAD, score any final window, write the summary, close every file."""
    if session.finished:
        return
    session.finished = True

    if session.worker is not None:
        try:
            await asyncio.wait_for(session.queue.put(None), timeout=5.0)
            await asyncio.wait_for(session.worker, timeout=30.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            session.worker.cancel()
        except Exception:  # noqa: BLE001
            session.worker.cancel()

    loop = asyncio.get_running_loop()
    for track in list(session.analyzers):
        try:
            for message in await loop.run_in_executor(EXECUTOR, session.flush_track, track):
                await _send(websocket, message)
                await HUB.publish(message)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error flushing track {track}: {e}")

    summary = session.summary()
    summary["reason"] = reason
    session.artifacts.summary(summary)
    session.artifacts.event("session_end", reason=reason,
                            duration_s=summary["duration_s"],
                            dropped_chunks=session.dropped_chunks)

    summary_json = SessionSummaryMessage(
        session_id=session.session_id,
        detector=summary["detector"],
        tracks=summary["analysis"],
        risk=summary["risk"],
        artifacts_dir=summary["artifacts_dir"],
    ).model_dump_json()
    await _send(websocket, summary_json)
    await HUB.publish(summary_json)

    session.recorder.close()
    session.artifacts.close()

    logger.info(
        f"Session ended ({reason}): id={session.session_id}, "
        f"far_chunks={session.track('far').total_chunks}, "
        f"near_chunks={session.track('near').total_chunks}, "
        f"windows={ {k: v.windows_emitted for k, v in session.analyzers.items()} }, "
        f"artifacts={summary['artifacts_dir']}"
    )


# --------------------------------------------------------------------------- #
# endpoint
# --------------------------------------------------------------------------- #
@router.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    if config.AUTH_TOKEN:
        token = websocket.query_params.get("token")
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if token != config.AUTH_TOKEN:
            logger.warning("Rejected WebSocket connection: invalid or missing auth token")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return

    await websocket.accept()
    logger.info(f"WebSocket client connected: {websocket.client}")

    session: SessionState | None = None

    try:
        while True:
            message = await websocket.receive()
            msg_type = message.get("type")

            if msg_type == "websocket.disconnect":
                break

            if "text" in message:
                raw_text = message["text"]
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received: {raw_text[:100]}")
                    await websocket.send_text(ErrorMessage(message="Malformed JSON").model_dump_json())
                    continue

                msg_kind = data.get("type")

                if msg_kind == "session_start":
                    if session is not None:
                        await _finish(session, websocket, "superseded")
                    try:
                        start_msg = SessionStartMessage(**data)
                    except ValidationError as e:
                        logger.error(f"Invalid session_start: {e}")
                        await websocket.send_text(
                            ErrorMessage(message=f"Invalid session_start: {e}").model_dump_json()
                        )
                        continue

                    session = SessionState(
                        session_id=start_msg.session_id,
                        sample_rate=start_msg.sample_rate,
                        channels=start_msg.channels,
                        encoding=start_msg.encoding,
                        source=start_msg.source,
                    )
                    session.artifacts.manifest({
                        "session_id": session.session_id,
                        "started_at": session.started_at,
                        "source": start_msg.source,
                        "sample_rate": start_msg.sample_rate,
                        "channels": start_msg.channels,
                        "encoding": start_msg.encoding,
                        "client": str(websocket.client),
                        "detector": detector.active_name(),
                        "model": model.status(),
                        "config": config.snapshot(),
                    })
                    session.artifacts.event("session_start", source=start_msg.source,
                                            sample_rate=start_msg.sample_rate,
                                            detector=detector.active_name())
                    session.worker = asyncio.create_task(_analysis_worker(session, websocket))
                    await HUB.publish({
                        "type": "session_start",
                        "session_id": session.session_id,
                        "source": start_msg.source,
                        "started_at": session.started_at,
                        "detector": detector.active_name(),
                    })
                    logger.info(
                        f"Session started: id={session.session_id}, rate={session.sample_rate}Hz, "
                        f"source={start_msg.source}, detector={detector.active_name()}, "
                        f"scoring={sorted(config.DETECT_TRACKS)}"
                    )

                elif msg_kind == "audio_chunk":
                    if session is None:
                        await websocket.send_text(
                            ErrorMessage(message="session_start required before audio_chunk").model_dump_json()
                        )
                        continue
                    try:
                        session.pending_metadata = AudioChunkMetadata(**data)
                    except ValidationError as e:
                        # Pydantic's default error repr truncates long input values, which
                        # hides the actual malformed payload. Log the raw parsed dict in full
                        # (keys only, no audio bytes are ever in `data` -- it's the metadata
                        # frame) so a bad client message is diagnosable from this line alone.
                        logger.error(f"Invalid audio_chunk metadata: {e}\n  raw keys received: {list(data.keys())}\n  raw data: {data!r}")
                        await websocket.send_text(
                            ErrorMessage(
                                session_id=session.session_id,
                                message=f"Invalid audio_chunk metadata: {e}",
                            ).model_dump_json()
                        )

                elif msg_kind == "session_end":
                    if session is not None:
                        await _finish(session, websocket, "client_session_end")
                    session = None

                else:
                    logger.warning(f"Unknown message type: {msg_kind}")
                    await websocket.send_text(
                        ErrorMessage(message=f"Unknown message type: {msg_kind}").model_dump_json()
                    )

            elif "bytes" in message:
                raw_bytes = message["bytes"]
                if session is None or session.pending_metadata is None:
                    await websocket.send_text(
                        ErrorMessage(message="Binary audio frame received without metadata").model_dump_json()
                    )
                    continue

                metadata = session.pending_metadata
                session.pending_metadata = None
                track = session.track(metadata.track)

                try:
                    validate_pcm_chunk(raw_bytes, expected_size=metadata.payload_size)
                except ValueError as e:
                    logger.error(f"Chunk validation failed: {e}")
                    session.artifacts.event("chunk_invalid", track=metadata.track,
                                            sequence=metadata.sequence, error=str(e))
                    await websocket.send_text(
                        ErrorMessage(
                            session_id=session.session_id,
                            message=f"Audio payload validation error: {e}",
                        ).model_dump_json()
                    )
                    continue

                current_seq = metadata.sequence
                if current_seq == track.expected_sequence:
                    track.expected_sequence += 1
                elif current_seq > track.expected_sequence:
                    logger.warning(
                        f"[{metadata.track}] Sequence gap: expected {track.expected_sequence}, got {current_seq}"
                    )
                    session.artifacts.event("sequence_gap", track=metadata.track,
                                            expected=track.expected_sequence, got=current_seq)
                    track.expected_sequence = current_seq + 1
                else:
                    logger.warning(
                        f"[{metadata.track}] Duplicate/out-of-order: expected {track.expected_sequence}, got {current_seq}"
                    )
                    session.artifacts.event("sequence_out_of_order", track=metadata.track,
                                            expected=track.expected_sequence, got=current_seq)

                track.total_chunks += 1
                track.total_bytes += len(raw_bytes)

                # Recorded before queueing, so a later analysis drop can never
                # cost us the audio itself.
                session.recorder.write_chunk(metadata.track, metadata.sequence,
                                             metadata.sample_rate, raw_bytes)
                session.artifacts.event("chunk", track=metadata.track, sequence=metadata.sequence,
                                        bytes=len(raw_bytes), duration_ms=metadata.duration_ms,
                                        sample_rate=metadata.sample_rate)

                await websocket.send_text(
                    ChunkAckMessage(
                        session_id=session.session_id,
                        track=metadata.track,
                        sequence=metadata.sequence,
                    ).model_dump_json()
                )

                if metadata.track in config.DETECT_TRACKS:
                    session.enqueue(metadata.track, metadata.sequence, raw_bytes)

    except WebSocketDisconnect:
        if session:
            logger.info(f"Client disconnected during active session: id={session.session_id}")
            await _finish(session, websocket, "client_disconnected")
        else:
            logger.info("Client disconnected cleanly")
    except Exception as e:
        logger.exception(f"Unexpected error in WebSocket loop: {e}")
        if session:
            await _finish(session, websocket, f"server_error: {e}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    else:
        if session:
            await _finish(session, websocket, "connection_closed")
