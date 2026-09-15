"""Downmix to mono and resample to 16 kHz, without corrupting the signal.

This matters more here than it looks. The detector downstream works by
spotting *spectral artifacts* of speech synthesis, so any artifact this stage
introduces is an artifact the model may read as evidence of a deepfake.

The previous implementation resampled with bare `np.interp` and no anti-alias
filter. Capture devices are typically 48 kHz, so that is a 3x decimation with
no lowpass: every component between 8 kHz and 24 kHz folds straight back down
into the 0-8 kHz band the model examines. It also ran statelessly on each
~1024-frame device read -- about 47 times a second -- so every buffer boundary
put a small discontinuity into the stream as well.

`StreamingResampler` fixes both:

  * `scipy.signal.resample_poly` applies a proper polyphase FIR lowpass before
    decimating, so nothing folds back into the band.
  * Filter context and a sub-`down` sample remainder are carried between
    calls, so the output is bit-identical to resampling the whole stream in
    one go -- no per-buffer transient, and no sample-count drift over a call.

If scipy is unavailable it falls back to the old behaviour, but says so at
ERROR level: the pipeline still runs, and you are told the scores are not
trustworthy, rather than finding out later.
"""

import logging
import math

import numpy as np

logger = logging.getLogger("resample")

TARGET_RATE = 16000

try:
    from scipy.signal import resample_poly
    HAVE_SCIPY = True
except ImportError:  # pragma: no cover - depends on the environment
    resample_poly = None
    HAVE_SCIPY = False
    logger.error(
        "scipy is not installed, so audio will be resampled WITHOUT an anti-alias "
        "filter. Everything above 8 kHz will fold back into the band the detector "
        "analyses, and its scores will not be trustworthy. Fix with: "
        "pip install -r requirements.txt"
    )


def _decode(raw_bytes: bytes, in_channels: int) -> np.ndarray:
    """PCM16 bytes -> float32 mono samples."""
    arr = np.frombuffer(raw_bytes, dtype="<i2")
    if in_channels > 1:
        usable = (len(arr) // in_channels) * in_channels
        arr = arr[:usable].reshape(-1, in_channels).mean(axis=1)
    return arr.astype(np.float32)


def _encode(arr: np.ndarray) -> bytes:
    return np.clip(np.rint(arr), -32768, 32767).astype("<i2").tobytes()


class StreamingResampler:
    """Stateful mono/16 kHz conversion for one continuous audio stream.

    One instance per track, reused for the whole session -- the carried state
    is what makes consecutive buffers join seamlessly, so sharing an instance
    between two tracks (or reusing one across sessions) would splice unrelated
    audio together.
    """

    def __init__(self, in_rate: int, in_channels: int, out_rate: int = TARGET_RATE):
        self.in_rate = int(in_rate)
        self.in_channels = max(1, int(in_channels))
        self.out_rate = int(out_rate)
        self.passthrough = self.in_rate == self.out_rate

        g = math.gcd(self.in_rate, self.out_rate)
        self.up = self.out_rate // g
        self.down = self.in_rate // g

        # resample_poly's default FIR runs 10 * max(up, down) taps either side,
        # so each output sample depends on input BOTH before and after it. We
        # therefore hold `context` samples of history *and* delay output by the
        # same amount until the following buffer supplies the future context --
        # otherwise every buffer's last few samples taper into the zero-padding
        # scipy adds at the array edge. Rounded up to whole `down` steps so the
        # skipped output length is an exact integer.
        half = 10 * max(self.up, self.down)
        steps = math.ceil((half + 1) / self.down)
        self.context = steps * self.down          # input samples of context each side
        self._skip_out = steps * self.up          # = context * up / down, exactly

        # Input not yet emitted. The leading `context` samples are history for
        # the filter; at stream start there is none, so it begins as silence.
        self._buf = np.zeros(self.context, dtype=np.float32)

        self.quality = "anti-aliased" if (HAVE_SCIPY or self.passthrough) else "ALIASED (no scipy)"

    def process(self, raw_bytes: bytes) -> bytes:
        if not raw_bytes:
            return b""
        mono = _decode(raw_bytes, self.in_channels)
        if self.passthrough:
            return _encode(mono)
        if not HAVE_SCIPY:
            return _encode(self._legacy(mono))

        self._buf = np.concatenate([self._buf, mono])
        # Emit only the region that has full context on both sides, in whole
        # decimation steps -- so output length is exactly n * up / down and no
        # sample-count drift accumulates across a long call.
        n = ((len(self._buf) - 2 * self.context) // self.down) * self.down
        if n <= 0:
            return b""

        resampled = resample_poly(self._buf[:2 * self.context + n], self.up, self.down)
        out = resampled[self._skip_out:self._skip_out + (n * self.up) // self.down]
        # Advance past what we emitted, leaving its tail as the next left context.
        self._buf = self._buf[n:]
        return _encode(out)

    def flush(self) -> None:
        """Drop the unemitted tail at end of stream.

        It is at most `2 * context` input samples -- under 1.4 ms at 48 kHz --
        which cannot affect a 4 s analysis window. Emitting it would mean
        resampling against zero-padding and inventing a transient at the very
        end of the call, so it is discarded instead.
        """
        self._buf = np.zeros(self.context, dtype=np.float32)

    def _legacy(self, mono: np.ndarray) -> np.ndarray:
        """The old, aliasing conversion. Only reachable without scipy."""
        if len(mono) <= 1:
            return mono
        duration = len(mono) / float(self.in_rate)
        n_out = max(1, int(round(duration * self.out_rate)))
        x_old = np.linspace(0.0, duration, num=len(mono), endpoint=False)
        x_new = np.linspace(0.0, duration, num=n_out, endpoint=False)
        return np.interp(x_new, x_old, mono)


def to_mono16k_pcm16(raw_bytes: bytes, in_rate: int, in_channels: int) -> bytes:
    """One-shot conversion of a self-contained clip.

    Correct only for audio that starts and ends at the boundaries you pass in.
    For a continuous capture stream use StreamingResampler, which carries
    filter state between buffers.
    """
    return StreamingResampler(in_rate, in_channels).process(raw_bytes)
