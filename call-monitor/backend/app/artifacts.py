"""The forensic record for one session.

Everything the pipeline decided is written to disk as it happens, next to the
audio it decided it about: what arrived, what the VAD kept and dropped, which
samples were assembled into each analysis window, what the model returned for
it, and how the running risk moved. The point is that any verdict can be
traced back afterwards to the precise audio that produced it -- both to debug
the system and, in the deployment this is aimed at, to be able to justify
having flagged a real customer's call.

    recordings/<session_id>/
      session.json              config snapshot, model fingerprint, versions
      events.jsonl              every event, in order, with elapsed_ms
      verdicts.jsonl            one line per verdict emitted
      summary.json              written at session end
      far/segments.jsonl        VAD segments as they close
      far/windows/window_N.json provenance + model output per window

Writes are append-and-flush and every failure is swallowed with a warning: a
logging problem must never take down a live call.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from app import config

logger = logging.getLogger("artifacts")


class SessionArtifacts:
    """Append-only JSONL + JSON writers for one session. Thread-safe: the
    WebSocket event loop and the analysis worker both write here."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.enabled = config.WRITE_ARTIFACTS
        self.dir = config.RECORDINGS_DIR / session_id
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._files: dict[str, object] = {}
        self._counts: dict[str, int] = {}

        if self.enabled:
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Cannot create artifact dir {self.dir}: {e}; artifacts disabled")
                self.enabled = False

    # -- public ------------------------------------------------------------

    def event(self, kind: str, **fields) -> None:
        """One line on the session timeline. `kind` is the event type."""
        self._append("events.jsonl", {"kind": kind, **fields})

    def segment(self, track: str, segment: dict) -> None:
        self._append(f"{track}/segments.jsonl", segment)
        self.event("vad_segment", track=track, **segment)

    def verdict(self, verdict: dict) -> None:
        self._append("verdicts.jsonl", verdict)
        self.event("verdict", **{k: v for k, v in verdict.items() if k != "type"})

    def window(self, track: str, index: int, payload: dict) -> None:
        """Per-window sidecar, written beside window_NNNN.wav."""
        if not self.enabled:
            return
        path = self.dir / track / "windows" / f"window_{index:04d}.json"
        self._write_json(path, payload)

    def manifest(self, payload: dict) -> None:
        self._write_json(self.dir / "session.json", payload)

    def summary(self, payload: dict) -> None:
        self._write_json(self.dir / "summary.json", payload)

    def counts(self) -> dict:
        return dict(self._counts)

    def close(self) -> None:
        with self._lock:
            for name, handle in list(self._files.items()):
                try:
                    handle.close()
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Error closing artifact file {name}: {e}")
            self._files.clear()

    # -- internals ---------------------------------------------------------

    def _elapsed_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def _append(self, relative: str, record: dict) -> None:
        if not self.enabled:
            return
        line = {
            "ts": round(time.time(), 3),
            "elapsed_ms": self._elapsed_ms(),
            "session_id": self.session_id,
            **record,
        }
        with self._lock:
            handle = self._files.get(relative)
            if handle is None:
                path = self.dir / relative
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    handle = path.open("a", encoding="utf-8")
                    self._files[relative] = handle
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Cannot open {path}: {e}")
                    return
            try:
                handle.write(json.dumps(line, default=str) + "\n")
                # Flushed per line: a call that ends in a crash or a yanked
                # cable must still leave a complete, readable log behind.
                handle.flush()
                self._counts[relative] = self._counts.get(relative, 0) + 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Cannot write to {relative}: {e}")

    def _write_json(self, path: Path, payload: dict) -> None:
        if not self.enabled:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Cannot write {path}: {e}")
