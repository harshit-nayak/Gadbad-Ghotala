"""WebSocket protocol messages for the desktop call-audio streaming pipeline.

Two logical audio tracks share one session:
  - "far"  = the other party's voice (captured via system-output loopback
             while a WhatsApp Desktop call is active) -- this is the track
             the deepfake detector analyzes.
  - "near" = the local user's own microphone.

Wire format: JSON text frames for control/metadata, followed by a single raw
binary WebSocket frame (PCM16 mono, 16 kHz little-endian) for each audio_chunk.

Note the asymmetry between chunks and verdicts: the client sends fixed-duration
chunks, but verdicts are NOT one-per-chunk. The backend runs VAD, cuts windows
out of individual utterances of the far party actually speaking, and emits one
verdict per window -- so verdicts arrive on the pace of the conversation, not
the pace of the clock. `sequence` on a verdict is therefore a window index,
unrelated to any chunk sequence.
"""

from typing import Literal, Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    detector: str = "unknown"            # the primary: produces the verdict
    model_state: str = "not_loaded"
    model_path: Optional[str] = None
    provider: Optional[str] = None
    vad_backend: Optional[str] = None
    detail: Optional[str] = None
    detectors: Optional[list] = None     # every configured detector and its state


Track = Literal["far", "near"]


class SessionStartMessage(BaseModel):
    type: Literal["session_start"] = "session_start"
    session_id: str
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    source: str = "whatsapp_desktop"


class AudioChunkMetadata(BaseModel):
    type: Literal["audio_chunk"] = "audio_chunk"
    session_id: str
    track: Track
    sequence: int
    timestamp: int
    duration_ms: int = 2000
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    payload_size: int


class ChunkAckMessage(BaseModel):
    type: Literal["chunk_ack"] = "chunk_ack"
    session_id: str
    track: Track
    sequence: int


class VerdictMessage(BaseModel):
    """Server -> client detection result for one analysis window.

    `label` is one of likely_real / uncertain / likely_synthetic -- three bands,
    because asserting "deepfake" about a genuine caller is expensive, so the
    middle band asks for verification instead (see app/risk.py).

    `score` is P(spoof), kept as the headline number so a higher value always
    means more concerning; `p_bonafide` is the model's native output. Both come
    from the primary detector; `secondary` holds the same window scored by any
    other loaded detector, for comparison only.
    """
    type: Literal["verdict"] = "verdict"
    session_id: str
    track: Track
    sequence: int                      # window index on this track
    score: float                       # P(spoof), 0..1
    label: str
    detail: Optional[str] = None

    p_bonafide: Optional[float] = None
    p_spoof: Optional[float] = None
    score_logprob: Optional[float] = None
    detector: Optional[str] = None
    secondary: Optional[list] = None   # other detectors on the same window

    # Session-level running risk, so the client can show a live meter without
    # having to aggregate verdicts itself.
    session_risk: Optional[float] = None
    risk_band: Optional[str] = None
    recommendation: Optional[str] = None

    # Provenance: what this verdict was actually computed from.
    speech_seconds: Optional[float] = None
    window_start_ms: Optional[int] = None
    window_end_ms: Optional[int] = None
    spans_discontinuity: Optional[bool] = None
    padded: Optional[bool] = None      # short utterance tile-padded to window length
    latency_ms: Optional[float] = None


class SessionSummaryMessage(BaseModel):
    """Server -> client wrap-up, sent when a session ends."""
    type: Literal["session_summary"] = "session_summary"
    session_id: str
    detector: str
    tracks: dict
    risk: dict
    artifacts_dir: Optional[str] = None


class SessionEndMessage(BaseModel):
    type: Literal["session_end"] = "session_end"
    session_id: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    session_id: Optional[str] = None
    message: str
