"""Cutting model-ready analysis windows out of VAD-kept speech, one utterance at a time.

The model's input length is structural: exactly 64,600 samples (4.04 s). The
question is which 64,600 samples to hand it.

The unit here is the UTTERANCE: one continuous stretch of the far party speaking,
as delimited by the VAD (short pauses under VAD_MIN_SILENCE_MS stay inside it,
so a sentence isn't chopped mid-word). A window never spans two utterances.

  utterance >= one window   full windows slide through it at WINDOW_HOP_SAMPLES
                            while it is still being spoken, so a long sentence
                            is scored mid-sentence rather than after it ends.
                            When it ends, a final end-aligned window covers the
                            remainder if that remainder alone would qualify.
  floor <= utterance < one  a single window, tile-padded to 64,600 samples --
                            the padding the model card specifies for short
                            clips -- and flagged `padded`.
  utterance < floor         recorded to speech.wav, never scored.

Why not pool all speech into one buffer and cut windows from that? That is what
an earlier version did, and on real calls one window could join sentences spoken
up to 50 seconds apart; spliced windows also scored measurably worse than
unbroken ones. Per-utterance windows are each one real stretch of the call, and
cut inference roughly threefold -- which matters, since CPU inference averaged
2.2 s per window on a real call, slower than pooled windows arrived.

The cost is coverage: in quick back-and-forth much of the speech comes in bursts
under the floor. `stats()` reports exactly how much went unscored.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import numpy as np

from app import config
from app.vad import FRAME_SAMPLES, VoiceActivityDetector

logger = logging.getLogger("analysis")

WINDOW = config.WINDOW_SAMPLES
HOP = config.WINDOW_HOP_SAMPLES
# Shortest utterance that gets scored. Capped at one window: anything that long
# gets full, unpadded windows regardless of the floor.
FLOOR = max(FRAME_SAMPLES, min(WINDOW, int(config.UTTERANCE_MIN_SECONDS * config.SAMPLE_RATE)))


@dataclass
class AnalysisWindow:
    """Exactly the samples handed to the model, plus where they came from."""
    index: int
    track: str
    samples: np.ndarray                       # int16, exactly WINDOW
    source_ranges: list[tuple[int, int]]      # (start_ms, end_ms) on the call timeline
    speech_seconds_total: float               # speech accumulated on this track so far
    spans_discontinuity: bool                 # always False: windows never span a pause
    padded: bool = False                      # short utterance tile-padded up to WINDOW
    real_samples: int = WINDOW                # samples of actual speech before any padding
    utterance_index: int = 0                  # which utterance on this track it came from
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "track": self.track,
            "utterance_index": self.utterance_index,
            "n_samples": int(len(self.samples)),
            "real_samples": int(self.real_samples),
            "real_duration_s": round(self.real_samples / config.SAMPLE_RATE, 4),
            "padded": self.padded,
            "sample_rate": config.SAMPLE_RATE,
            "duration_s": round(len(self.samples) / config.SAMPLE_RATE, 4),
            "source_ranges_ms": [list(r) for r in self.source_ranges],
            "source_span_ms": (self.source_ranges[-1][1] - self.source_ranges[0][0])
                              if self.source_ranges else 0,
            "speech_seconds_total": round(self.speech_seconds_total, 3),
            "spans_discontinuity": self.spans_discontinuity,
            "created_at_ms": self.created_at_ms,
        }


class TrackAnalyzer:
    """VAD + per-utterance window cutting for one track."""

    def __init__(self, track: str, vad: VoiceActivityDetector | None = None):
        self.track = track
        self.vad = vad if vad is not None else VoiceActivityDetector()

        # The utterance in progress. Samples are held as a list of frames and
        # only concatenated when a window is actually cut, and trimmed after,
        # so a long monologue never costs more than about two windows of memory.
        self._utt: list[np.ndarray] = []
        self._utt_len = 0                 # samples in the utterance so far
        self._utt_origin = 0              # utterance offset of _utt's first held sample
        self._utt_start: int | None = None  # track-timeline sample where it began
        self._utt_last_frame: int | None = None
        self._utt_next = 0                # utterance offset where the next full window starts
        self._utt_index = 0

        self._window_index = 0
        self.total_frames = 0
        self.speech_frames = 0
        self.total_speech_samples = 0
        self.windows_emitted = 0
        self.padded_windows = 0
        self.utterances = 0
        self.utterances_scored = 0
        self.unscored_speech_samples = 0

    # -- public ------------------------------------------------------------

    @property
    def speech_seconds(self) -> float:
        return self.total_speech_samples / config.SAMPLE_RATE

    def push_chunk(self, pcm_int16: np.ndarray):
        """Feed one arrived chunk.

        Returns (kept_sample_arrays, segments, windows): the speech samples to
        append to speech.wav, any segments the gate closed, and any windows now
        ready to score.
        """
        decisions, segments = self.vad.process(pcm_int16)
        kept, windows = self._ingest(decisions)
        return kept, segments, windows

    def flush(self):
        """End of session: settle the gate and close the final utterance."""
        decisions, segments = self.vad.flush()
        kept, windows = self._ingest(decisions)
        windows += self._close_utterance()
        return kept, segments, windows

    # -- internals ---------------------------------------------------------

    def _ingest(self, decisions) -> tuple[list[np.ndarray], list[AnalysisWindow]]:
        kept_arrays: list[np.ndarray] = []
        windows: list[AnalysisWindow] = []

        for frame, kept in decisions:
            self.total_frames += 1
            if not kept:
                # The gate only drops frames outside a segment, and always drops
                # at least one between two segments -- so a dropped frame means
                # the utterance in progress has ended.
                windows += self._close_utterance()
                continue

            self.speech_frames += 1
            self.total_speech_samples += len(frame.samples)
            kept_arrays.append(frame.samples)

            # Safety net: a kept frame that doesn't continue the utterance starts
            # a new one, even if no dropped frame arrived between them.
            if self._utt_last_frame is not None and frame.index != self._utt_last_frame + 1:
                windows += self._close_utterance()
            if self._utt_start is None:
                self._utt_start = frame.index * FRAME_SAMPLES

            self._utt.append(frame.samples)
            self._utt_len += len(frame.samples)
            self._utt_last_frame = frame.index
            windows += self._emit_full_windows()

        return kept_arrays, windows

    def _held(self) -> np.ndarray:
        """The held samples of the utterance as one array (concatenated lazily)."""
        if len(self._utt) != 1:
            self._utt = [np.concatenate(self._utt) if self._utt else np.zeros(0, dtype=np.int16)]
        return self._utt[0]

    def _slice(self, offset: int, length: int) -> np.ndarray:
        """`length` samples starting at utterance offset `offset`."""
        start = offset - self._utt_origin
        return self._held()[start:start + length].copy()

    def _emit_full_windows(self) -> list[AnalysisWindow]:
        """Cut every full window the growing utterance now covers."""
        windows: list[AnalysisWindow] = []
        while self._utt_len >= self._utt_next + WINDOW:
            windows.append(self._make_window(self._slice(self._utt_next, WINDOW),
                                             self._utt_next, WINDOW, padded=False))
            self._utt_next += HOP
            # Keep one window of history behind the next start: enough for an
            # end-aligned final window, and no more.
            keep_from = max(0, self._utt_next - WINDOW)
            drop = keep_from - self._utt_origin
            if drop > 0:
                self._utt = [self._held()[drop:]]
                self._utt_origin = keep_from
        return windows

    def _close_utterance(self) -> list[AnalysisWindow]:
        if self._utt_start is None:
            return []  # already between utterances: most dropped frames land here

        windows: list[AnalysisWindow] = []
        length = self._utt_len
        self.utterances += 1

        if self._utt_next == 0:
            # Never reached a full window.
            if length >= FLOOR:
                speech = self._slice(0, length)
                tiled = np.tile(speech, math.ceil(WINDOW / length))[:WINDOW]
                windows.append(self._make_window(tiled, 0, length, padded=True))
                self.utterances_scored += 1
            else:
                self.unscored_speech_samples += length
        else:
            self.utterances_scored += 1
            covered_to = self._utt_next - HOP + WINDOW
            tail = length - covered_to
            if tail >= FLOOR:
                # The remainder is itself long enough to score: end-align a full
                # window on it rather than dropping a qualifying stretch.
                windows.append(self._make_window(self._slice(length - WINDOW, WINDOW),
                                                 length - WINDOW, WINDOW, padded=False))
            elif tail > 0:
                self.unscored_speech_samples += tail

        self._utt = []
        self._utt_len = 0
        self._utt_origin = 0
        self._utt_start = None
        self._utt_last_frame = None
        self._utt_next = 0
        self._utt_index += 1
        return windows

    def _make_window(self, samples: np.ndarray, offset: int, real: int,
                     padded: bool) -> AnalysisWindow:
        start = self._utt_start + offset
        window = AnalysisWindow(
            index=self._window_index,
            track=self.track,
            samples=samples,
            source_ranges=[(self._ms(start), self._ms(start + real))],
            speech_seconds_total=self.speech_seconds,
            spans_discontinuity=False,
            padded=padded,
            real_samples=real,
            utterance_index=self._utt_index,
        )
        self._window_index += 1
        self.windows_emitted += 1
        if padded:
            self.padded_windows += 1
        return window

    @staticmethod
    def _ms(n_samples: int) -> int:
        return round(n_samples * 1000 / config.SAMPLE_RATE)

    def stats(self) -> dict:
        speech = self.total_speech_samples
        return {
            "track": self.track,
            "vad_backend": self.vad.backend_name,
            "total_frames": self.total_frames,
            "speech_frames": self.speech_frames,
            "speech_ratio": round(self.speech_frames / self.total_frames, 4) if self.total_frames else 0.0,
            "speech_seconds": round(self.speech_seconds, 3),
            "utterances": self.utterances,
            "utterances_scored": self.utterances_scored,
            "windows_emitted": self.windows_emitted,
            "padded_windows": self.padded_windows,
            "unscored_speech_samples": self.unscored_speech_samples,
            "unscored_speech_seconds": round(self.unscored_speech_samples / config.SAMPLE_RATE, 3),
            "scored_speech_ratio": round(1 - self.unscored_speech_samples / speech, 4) if speech else 0.0,
            "utterance_min_seconds": round(FLOOR / config.SAMPLE_RATE, 3),
            "frame_samples": FRAME_SAMPLES,
        }
