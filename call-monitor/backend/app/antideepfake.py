"""AntiDeepfake MMS-300M -- a detector trained on far more varied audio.

Why it exists: XLSR-SLS is trained only on ASVspoof 2019 LA (clean, dry, read
English) and flags every real caller we have recorded as synthetic -- including
the tester's own voice on a laptop mic. AntiDeepfake (NII, 2025) was
post-trained on ~74,000 hours in 100+ languages (56k h genuine, 18k h with
synthesis, vocoding, restoration and neural-codec artifacts) and reports 1.23%
EER zero-shot on In-the-Wild for its largest variant. The MMS-300M variant is
used here: the same size as XLSR-SLS, so it can keep up on CPU, with a backbone
pretrained on 1,000+ languages. Weights: CC BY-NC-SA 4.0 (research/education).

Running it without fairseq: the published inference code builds the network
with fairseq, which does not install cleanly on Python 3.12 / Windows. The
backbone is loaded through app/wav2vec2_port.py instead (shared with
XLSR-Mamba), followed by mean pooling over time and one Linear(1024, 2).

Preprocessing, per the model card: 16 kHz mono, then zero-mean / unit-variance
over the whole clip (layer_norm without affine). Input may be any length, so a
short utterance is scored on its real speech, never on a tile-padded window.
Output: softmax over two classes, index 1 = real -- the same polarity as XLSR-SLS.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import numpy as np

from app import wav2vec2_port

logger = logging.getLogger("antideepfake")

MODEL_ID = "nii-yamagishilab/mms-300m-anti-deepfake"
WEIGHTS_FILE = "model.safetensors"
INT16_SCALE = 32768.0
SSL_PREFIX = "m_ssl.model."
HEAD_PREFIX = "proj_fc."


class ModelUnavailable(RuntimeError):
    pass


class AntiDeepfakeModel:
    """Int16 speech in, P(real) out. Accepts any length."""

    name = "antideepfake"
    requires_fixed_length = False

    def __init__(self, model_dir: Path, threads: int | None = None):
        try:
            import torch
            from safetensors.torch import load_file
        except ImportError as e:
            raise ModelUnavailable(
                f"AntiDeepfake needs torch + transformers + safetensors ({e}). "
                f"Install with: pip install -r requirements-antideepfake.txt"
            ) from e

        self.path = Path(model_dir) / WEIGHTS_FILE
        if not self.path.is_file():
            raise ModelUnavailable(
                f"{self.path} not found. Run: python scripts/fetch_antideepfake.py"
            )
        if threads:
            torch.set_num_threads(threads)
        self._torch = torch

        t0 = time.perf_counter()
        state = load_file(str(self.path))
        stray = [k for k in state if not k.startswith((SSL_PREFIX, HEAD_PREFIX))]
        if stray:
            raise ModelUnavailable(f"unexpected tensors in checkpoint: {stray[:4]}")

        try:
            self.ssl = wav2vec2_port.build(
                {k[len(SSL_PREFIX):]: v for k, v in state.items() if k.startswith(SSL_PREFIX)}
            )
        except (wav2vec2_port.PortError, ImportError) as e:
            raise ModelUnavailable(str(e)) from e

        self.head = torch.nn.Linear(1024, 2)
        self.head.load_state_dict(
            {k[len(HEAD_PREFIX):]: v for k, v in state.items() if k.startswith(HEAD_PREFIX)},
            strict=True,
        )
        self.head.eval()

        self.load_seconds = time.perf_counter() - t0
        self.n_weights = len(self.ssl.state_dict()) + 2
        self.provider = f"torch-cpu ({torch.get_num_threads()} threads)"
        stat = self.path.stat()
        self.fingerprint = f"{MODEL_ID}:{stat.st_size}:{int(stat.st_mtime)}"
        # Serialised like XLSR-SLS: concurrent big-model inference on a laptop
        # thrashes cores rather than adding throughput.
        self._lock = threading.Lock()

    def score(self, samples_int16: np.ndarray) -> tuple[float, float]:
        """1-D int16 speech of any length -> (P(real), bona-fide log-prob)."""
        torch = self._torch
        x = torch.from_numpy(np.asarray(samples_int16, dtype=np.float32) / INT16_SCALE)
        x = torch.nn.functional.layer_norm(x, x.shape)
        with self._lock, torch.inference_mode():
            hidden = self.ssl(x[None, :]).last_hidden_state   # [1, T, 1024]
            logits = self.head(hidden.mean(dim=1))             # [1, 2]
            logp = torch.log_softmax(logits, dim=-1)[0]
        return float(logp[1].exp()), float(logp[1])

    def score_window(self, samples_int16: np.ndarray, real_samples: int | None = None):
        """Score a pipeline window on its real speech only, dropping any padding."""
        if real_samples:
            samples_int16 = samples_int16[:real_samples]
        return self.score(samples_int16)

    def warmup(self) -> float:
        t0 = time.perf_counter()
        self.score(np.zeros(64_600, dtype=np.int16))
        return time.perf_counter() - t0

    def info(self) -> dict:
        return {
            "detector": self.name,
            "model_path": str(self.path),
            "fingerprint": self.fingerprint,
            "provider": self.provider,
            "load_seconds": round(self.load_seconds, 2),
            "weights_loaded": self.n_weights,
            "license": "CC BY-NC-SA 4.0",
        }
