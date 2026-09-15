"""Process-wide handles on the detectors, loaded once at startup.

The detectors available, selected and ordered by DETECTORS (app/config.py):

  xlsr-mamba       XLSR-Mamba with the Indic fine-tuned head -- trained on
                   Hindi/Bengali/Tamil deepfakes incl. WhatsApp-compressed audio.
                   PyTorch. See app/xlsr_mamba.py.
  xlsr-mamba-base  the same network without the Indic head (ASVspoof-trained).
  antideepfake     AntiDeepfake MMS-300M, post-trained on ~74,000 hours in 100+
                   languages. PyTorch. See app/antideepfake.py.
  xlsr-sls         the original XLS-R + SLS model trained on ASVspoof 2019 LA,
                   run via ONNX Runtime from ../../deepfake.

The first detector in DETECTORS that loads is the PRIMARY: it produces the
verdict and drives session risk. Any others score the same window and are
logged beside it, so the models can be compared on identical audio from real
calls without changing what the user is shown.

Each model is loaded exactly once, at startup -- they are ~1.3 GB each, and a
call that has already started is the worst moment to pay for that.

Loading is fail-soft per detector: a missing file or package disables that one
detector with a recorded reason. If none load, the backend runs on the
placeholder heuristic, and /health says so.

No inference code is duplicated for XLSR-SLS: deepfake/xlsr_sls_infer.py's
Detector is imported and used as-is, so live and offline scores stay identical.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

import numpy as np

from app import config

logger = logging.getLogger("model")

# int16 -> float32. Matches soundfile's own scaling (dtype="float32" divides by
# 32768), which is what preprocess.load() uses -- so a clip scored through this
# live path and through the offline CLI reach the model as identical arrays.
INT16_SCALE = 32768.0


class ModelUnavailable(RuntimeError):
    pass


class XlsrSlsModel:
    """Thin adapter: int16 analysis windows in, P(bona fide) out."""

    name = "xlsr-sls"
    requires_fixed_length = True

    def __init__(self, onnx_path: Path, code_dir: Path, provider: str = "cpu",
                 threads: int | None = None):
        code = str(code_dir)
        if code not in sys.path:
            # xlsr_sls_infer.py does `from preprocess import ...`, so its own
            # directory has to be importable as a top-level location.
            sys.path.insert(0, code)
        try:
            from xlsr_sls_infer import Detector
        except ImportError as e:
            raise ModelUnavailable(
                f"could not import the detector from {code_dir}: {e}. "
                f"Set MODEL_CODE_DIR to the folder holding xlsr_sls_infer.py and preprocess.py."
            ) from e

        t0 = time.perf_counter()
        self._detector = Detector(onnx_path, provider=provider, threads=threads)
        self.load_seconds = time.perf_counter() - t0
        self.provider = self._detector.provider
        self.path = Path(onnx_path)
        # Cheap provenance for the session manifest. A sha256 of 1.36 GB would
        # add seconds to startup for no benefit over size+mtime here.
        stat = self.path.stat()
        self.fingerprint = f"{self.path.name}:{stat.st_size}:{int(stat.st_mtime)}"

        # ONNX Runtime is thread-safe for run(), but every call is serialised
        # through one executor worker anyway -- concurrent big-model inference
        # on a laptop thrashes cores rather than adding throughput.
        self._lock = threading.Lock()

    def warmup(self) -> float:
        """One inference on silence so the first real verdict isn't the one
        that pays for lazy graph initialisation."""
        t0 = time.perf_counter()
        self.score(np.zeros((1, config.WINDOW_SAMPLES), dtype=np.int16))
        return time.perf_counter() - t0

    def score(self, windows_int16: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(N, 64600) int16 -> (P(bona fide), bona-fide log-prob), each (N,)."""
        arr = np.asarray(windows_int16)
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.shape[-1] != config.WINDOW_SAMPLES:
            raise ValueError(
                f"model needs exactly {config.WINDOW_SAMPLES} samples per window, "
                f"got {arr.shape[-1]}"
            )
        as_float = arr.astype(np.float32) / INT16_SCALE
        with self._lock:
            return self._detector.score_windows(as_float)

    def score_window(self, samples_int16: np.ndarray,
                     real_samples: int | None = None) -> tuple[float, float]:
        """Score one pipeline window. XLSR-SLS needs exactly 64,600 samples, so
        a short utterance is scored on its tile-padded window."""
        probs, logprobs = self.score(np.asarray(samples_int16)[None, :])
        return float(probs[0]), float(logprobs[0])

    def info(self) -> dict:
        return {
            "detector": self.name,
            "model_path": str(self.path),
            "fingerprint": self.fingerprint,
            "provider": self.provider,
            "load_seconds": round(self.load_seconds, 2),
            "window_samples": config.WINDOW_SAMPLES,
        }


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def _build_xlsr():
    if not config.MODEL_PATH.is_file():
        raise ModelUnavailable(
            f"{config.MODEL_PATH} not found. Set MODEL_PATH, or download it with: "
            f'python -c "from huggingface_hub import hf_hub_download as d; '
            f"d('SpeechAntiSpoofingBenchmarks/XLSR-SLS','xlsr-sls.onnx',local_dir='.')\""
        )
    return XlsrSlsModel(config.MODEL_PATH, config.MODEL_CODE_DIR,
                        provider=config.MODEL_PROVIDER, threads=config.MODEL_THREADS)


def _build_antideepfake():
    from app.antideepfake import AntiDeepfakeModel

    return AntiDeepfakeModel(config.ANTIDEEPFAKE_PATH, threads=config.MODEL_THREADS)


def _build_xlsr_mamba(variant: str):
    from app.xlsr_mamba import XlsrMambaModel

    return XlsrMambaModel(config.XLSR_MAMBA_PATH, variant=variant, threads=config.MODEL_THREADS)


_BUILDERS = {
    "xlsr-mamba": lambda: _build_xlsr_mamba("indic"),
    "xlsr-mamba-base": lambda: _build_xlsr_mamba("base"),
    "antideepfake": _build_antideepfake,
    "xlsr-sls": _build_xlsr,
}

_models: dict[str, object] = {}
_statuses: dict[str, dict] = {}
_load_lock = threading.Lock()
_loaded = False


def load():
    """Load every configured detector once. Never raises: a failure is recorded
    against that detector, and the backend carries on with whatever loaded.
    Returns the primary detector, or None if none loaded."""
    global _loaded

    with _load_lock:
        if _loaded:
            return get()
        _loaded = True

        if not config.MODEL_ENABLED:
            for name in config.DETECTORS:
                _statuses[name] = {"state": "disabled", "detail": "MODEL_ENABLED=false"}
            logger.warning("Real detectors disabled (MODEL_ENABLED=false); using the placeholder heuristic")
            return None

        for name in config.DETECTORS:
            builder = _BUILDERS.get(name)
            if builder is None:
                _statuses[name] = {"state": "error",
                                   "detail": f"unknown detector; choose from {sorted(_BUILDERS)}"}
                logger.error(f"Unknown detector '{name}' in DETECTORS; skipping it")
                continue
            logger.info(f"Loading detector '{name}'...")
            try:
                loaded = builder()
                warm = loaded.warmup()
            except Exception as e:  # noqa: BLE001
                _statuses[name] = {"state": "unavailable", "detail": str(e)}
                logger.error(f"Detector '{name}' unavailable -- continuing without it: {e}")
                continue
            _models[name] = loaded
            _statuses[name] = {"state": "ready", "detail": None}
            logger.info(f"Detector '{name}' ready: {loaded.provider}, "
                        f"load {loaded.load_seconds:.1f}s, warmup {warm:.2f}s")

        primary = get()
        if primary is None:
            logger.error("No detector loaded -- running on the PLACEHOLDER heuristic. See /health.")
        return primary


def get(name: str | None = None):
    """A loaded detector by name, or the primary if no name is given."""
    if name is not None:
        return _models.get(name)
    return next((_models[n] for n in config.DETECTORS if n in _models), None)


def get_all() -> list:
    """Every loaded detector, primary first."""
    return [_models[n] for n in config.DETECTORS if n in _models]


def status() -> dict:
    detectors = []
    for name in config.DETECTORS:
        entry = {"name": name, **_statuses.get(name, {"state": "not_loaded", "detail": None})}
        if name in _models:
            entry.update(_models[name].info())
        detectors.append(entry)

    primary = get()
    if primary is not None:
        info = {"state": "ready", "detail": None, **primary.info()}
    else:
        reasons = "; ".join(f"{d['name']}: {d.get('detail')}" for d in detectors) \
            or "no detectors configured"
        state = "disabled" if not config.MODEL_ENABLED else ("unavailable" if _loaded else "not_loaded")
        info = {"state": state, "detail": reasons, "detector": "placeholder", "model_path": None}
    info["detectors"] = detectors
    return info
