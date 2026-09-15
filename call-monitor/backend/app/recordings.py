"""Local storage of call audio, at four levels of granularity at once:

1. One continuous, directly-playable WAV per track per session -- listen back
   to the whole call.                                        (RECORD_LOCALLY)
2. One WAV per arriving chunk, written the instant it validates -- inspect the
   call while it is still in progress.                       (RECORD_CHUNKS)
3. One continuous WAV per track of only what the VAD kept -- hear exactly what
   the system considered to be the other party speaking.     (RECORD_SPEECH)
4. One WAV per analysis window -- the exact 64,600 samples the model scored,
   beside the JSON saying what it returned.                  (RECORD_WINDOWS)

Levels 3 and 4 are what make a verdict auditable: given a score you disagree
with, you can open the precise audio it came from and listen.

All four are on by default and independently switchable. Files land under
RECORDINGS_DIR (default "recordings", relative to wherever the backend runs):

    recordings/<session_id>/far.wav                   <- continuous
    recordings/<session_id>/near.wav
    recordings/<session_id>/far/chunk_0000.wav        <- per-chunk, real-time
    recordings/<session_id>/far/speech.wav            <- VAD-kept only
    recordings/<session_id>/far/windows/window_0000.wav
    ...
"""

import logging
import wave
from pathlib import Path

from app import config

logger = logging.getLogger("recordings")

RECORDINGS_DIR = config.RECORDINGS_DIR


def _write_wav(path: Path, sample_rate: int, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


class SessionRecorder:
    """Owns the open WAV writers for a single session.

    Continuous writers are opened lazily on a track's first write (so the real
    sample rate is known) and MUST be closed via close() -- the `wave` module
    only writes a correct RIFF header and data length on close, so an unclosed
    file is truncated and unplayable.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.enabled = config.RECORD_LOCALLY
        self.chunks_enabled = config.RECORD_CHUNKS
        self.speech_enabled = config.RECORD_SPEECH
        self.windows_enabled = config.RECORD_WINDOWS
        self._writers: dict[str, wave.Wave_write] = {}
        self._paths: dict[str, Path] = {}

    # -- raw capture -------------------------------------------------------

    def write_chunk(self, track: str, sequence: int, sample_rate: int, pcm: bytes) -> None:
        if not pcm:
            return
        if self.enabled:
            self._continuous(track, f"{track}.wav", sample_rate, pcm)
        if self.chunks_enabled:
            try:
                chunk_dir = RECORDINGS_DIR / self.session_id / track
                chunk_dir.mkdir(parents=True, exist_ok=True)
                _write_wav(chunk_dir / f"chunk_{sequence:04d}.wav", sample_rate, pcm)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to write per-chunk file for {track}#{sequence}: {e}")

    # -- analysis artifacts ------------------------------------------------

    def write_speech(self, track: str, sample_rate: int, pcm: bytes) -> None:
        """Append VAD-kept samples to <track>/speech.wav."""
        if not self.speech_enabled or not pcm:
            return
        self._continuous(f"{track}:speech", f"{track}/speech.wav", sample_rate, pcm)

    def write_window(self, track: str, index: int, sample_rate: int, pcm: bytes) -> None:
        """Write the exact samples handed to the model for one window."""
        if not self.windows_enabled or not pcm:
            return
        try:
            window_dir = RECORDINGS_DIR / self.session_id / track / "windows"
            window_dir.mkdir(parents=True, exist_ok=True)
            _write_wav(window_dir / f"window_{index:04d}.wav", sample_rate, pcm)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to write window file for {track}#{index}: {e}")

    # -- internals ---------------------------------------------------------

    def _continuous(self, key: str, relative: str, sample_rate: int, pcm: bytes) -> None:
        writer = self._writers.get(key)
        if writer is None:
            try:
                path = RECORDINGS_DIR / self.session_id / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                writer = wave.open(str(path), "wb")
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(sample_rate)
                self._writers[key] = writer
                self._paths[key] = path
                logger.info(f"Recording {key} for session {self.session_id} -> {path}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to open recording file {relative}: {e}")
                return
        try:
            writer.writeframes(pcm)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to write {key} audio to disk: {e}")

    def paths(self) -> dict:
        return {key: str(path) for key, path in self._paths.items()}

    def close(self) -> None:
        for key, writer in list(self._writers.items()):
            try:
                writer.close()
                logger.info(f"Closed recording: {self._paths.get(key)}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Error closing {key} recording: {e}")
        self._writers.clear()


if config.RECORD_LOCALLY or config.RECORD_CHUNKS or config.RECORD_SPEECH or config.RECORD_WINDOWS:
    logger.info(
        f"Local call recording enabled (continuous={config.RECORD_LOCALLY}, "
        f"per-chunk={config.RECORD_CHUNKS}, speech={config.RECORD_SPEECH}, "
        f"windows={config.RECORD_WINDOWS}) -> {RECORDINGS_DIR.resolve()}"
    )
