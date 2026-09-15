"""Accumulates resampled 16kHz mono PCM16 bytes into fixed-duration chunks,
per track, mirroring the Android app's AudioChunker.
"""

import io
import time
import threading

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2


class Chunk:
    __slots__ = ("track", "sequence", "timestamp_ms", "duration_ms", "payload")

    def __init__(self, track: str, sequence: int, timestamp_ms: int, duration_ms: int, payload: bytes):
        self.track = track
        self.sequence = sequence
        self.timestamp_ms = timestamp_ms
        self.duration_ms = duration_ms
        self.payload = payload


class TrackChunker:
    def __init__(self, track: str, chunk_seconds: float, on_chunk):
        self.track = track
        self.target_bytes = int(SAMPLE_RATE * BYTES_PER_SAMPLE * chunk_seconds)
        self.on_chunk = on_chunk
        self._buf = io.BytesIO()
        self._sequence = 0
        self._lock = threading.Lock()

    def add(self, pcm16_mono_16k: bytes):
        if not pcm16_mono_16k:
            return
        with self._lock:
            self._buf.write(pcm16_mono_16k)
            if self._buf.tell() < self.target_bytes:
                return
            all_bytes = self._buf.getvalue()
            while len(all_bytes) >= self.target_bytes:
                piece = all_bytes[: self.target_bytes]
                all_bytes = all_bytes[self.target_bytes :]
                chunk = Chunk(
                    track=self.track,
                    sequence=self._sequence,
                    timestamp_ms=int(time.time() * 1000),
                    duration_ms=int(len(piece) / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000),
                    payload=piece,
                )
                self._sequence += 1
                self.on_chunk(chunk)
            self._buf = io.BytesIO()
            self._buf.write(all_bytes)

    def flush(self):
        with self._lock:
            remaining = self._buf.getvalue()
            self._buf = io.BytesIO()
            if not remaining:
                return
            chunk = Chunk(
                track=self.track,
                sequence=self._sequence,
                timestamp_ms=int(time.time() * 1000),
                duration_ms=int(len(remaining) / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000),
                payload=remaining,
            )
            self._sequence += 1
            self.on_chunk(chunk)
