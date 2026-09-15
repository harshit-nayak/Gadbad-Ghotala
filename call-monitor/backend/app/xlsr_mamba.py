"""XLSR-Mamba with the Indic fine-tuned head.

Source: private repo harshit-nayak/Gadbad-Ghotala, branch XLSR_MAMBA_FINETUNED
(commit 27a1e33, Atharv Lamba, 2026-09-11). It fine-tunes the classification
head of XLSR-Mamba (Xiao & Das, arXiv:2411.10027) on Hindi / Bengali / Tamil
real speech (SPRINGLab/IndicVoices-R) and deepfakes (vdivyasharma/IndicSynth),
with half of training passed through WhatsApp-style Opus compression. Reported:
Indic held-out EER 0.31%, 99.69% accuracy on clean and WhatsApp-compressed audio
alike. The cost is catastrophic forgetting: ASVspoof5 EER rose from 2.77% to
21.28%, because only the head was retrained.

Weights = the base checkpoint AustinXiao/XLSR-Mamba-LA (MIT; 565 tensors: frozen
XLS-R backbone, LL + first_bn front-end, Mamba head) with its 129 conformer.*
tensors replaced by the branch's conformer_head_only.safetensors -- exactly how
the branch's load_model.py reconstructs model_indic_ft.safetensors. The backbone
and front-end are byte-identical between base and fine-tune, so VARIANT="base"
(no head file) gives the original ASVspoof-trained model on the same code.

Architecture: waveform -> XLS-R wav2vec 2.0 -> Linear(1024,144) ->
BatchNorm2d(1) -> SELU -> dual-column bidirectional Mamba (6 layers each way,
attention pooling) -> 2 logits, index 1 = bona fide. The Mamba head below is the
branch's pure-PyTorch implementation (MIT; no mamba_ssm CUDA kernels, so it runs
on CPU), vendored unchanged. The backbone loads through app/wav2vec2_port.py,
so fairseq is not needed.

Preprocessing matches the branch's evaluate_model.py exactly: float waveform in
[-1, 1] with NO normalisation, repeat-tiled or cropped to 66,800 samples
(4.175 s) -- the length both the base model and the fine-tune were trained on.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from functools import partial
from pathlib import Path

import numpy as np

from app import wav2vec2_port

logger = logging.getLogger("xlsr_mamba")

BASE_FILE = "model_base.safetensors"
HEAD_FILE = "conformer_head_only.safetensors"
BASE_ID = "AustinXiao/XLSR-Mamba-LA"
INPUT_SAMPLES = 66_800
INT16_SCALE = 32768.0
SSL_PREFIX = "ssl_model.model."
KNOWN_PREFIXES = (SSL_PREFIX, "LL.", "first_bn.", "conformer.")


class ModelUnavailable(RuntimeError):
    pass


def pad_or_trim(x: np.ndarray, cut: int = INPUT_SAMPLES) -> np.ndarray:
    """Repeat-tile short clips, crop long ones -- evaluate_model.py's pad_or_trim."""
    if len(x) >= cut:
        return x[:cut]
    return np.tile(x, int(cut / len(x)) + 1)[:cut]


def _build_head_classes():
    """The branch's pure-PyTorch Mamba head (evaluate_model.py, MIT), unchanged.
    Defined lazily so importing this module never requires torch."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    def selective_scan_ref(u, delta, A, B, C, D=None, z=None,
                           delta_bias=None, delta_softplus=False):
        dtype_in = u.dtype
        u = u.float()
        delta = delta.float()
        if delta_bias is not None:
            delta = delta + delta_bias[..., None].float()
        if delta_softplus:
            delta = F.softplus(delta)
        B_f = B.float()
        C_f = C.float()
        x = torch.zeros(u.shape[0], A.shape[0], A.shape[1], device=u.device, dtype=torch.float32)
        deltaA = torch.exp(torch.einsum('bdl,dn->bdln', delta, A.float()))
        deltaB_u = torch.einsum('bdl,bnl,bdl->bdln', delta, B_f, u)
        ys = []
        for t in range(u.shape[2]):
            x = deltaA[:, :, t] * x + deltaB_u[:, :, t]
            ys.append(torch.einsum('bdn,bn->bd', x, C_f[:, :, t]))
        y = torch.stack(ys, dim=2)
        out = y if D is None else y + u * D.float()[None, :, None]
        if z is not None:
            out = out * F.silu(z.float())
        return out.to(dtype_in)

    class RMSNorm(nn.Module):
        def __init__(self, d, eps=1e-5, **kwargs):
            super().__init__()
            self.eps = eps
            self.weight = nn.Parameter(torch.ones(d))

        def forward(self, x):
            ms = x.float().pow(2).mean(-1, keepdim=True)
            return (x.float() * (ms + self.eps).rsqrt()).to(x.dtype) * self.weight

    class Mamba(nn.Module):
        def __init__(self, d_model, d_state=16, d_conv=4, expand=2, dt_rank='auto',
                     conv_bias=True, bias=False, use_fast_path=False, layer_idx=None,
                     device=None, dtype=None):
            super().__init__()
            self.d_model = d_model
            self.d_inner = int(expand * d_model)
            self.d_state = d_state
            self.d_conv = d_conv
            self.dt_rank = math.ceil(d_model / 16) if dt_rank == 'auto' else dt_rank
            fkw = {'device': device, 'dtype': dtype}
            self.in_proj = nn.Linear(d_model, self.d_inner * 2, bias=bias, **fkw)
            self.conv1d = nn.Conv1d(self.d_inner, self.d_inner, kernel_size=d_conv,
                                    groups=self.d_inner, padding=d_conv - 1, bias=conv_bias, **fkw)
            self.x_proj = nn.Linear(self.d_inner, self.dt_rank + d_state * 2, bias=False, **fkw)
            self.dt_proj = nn.Linear(self.dt_rank, self.d_inner, bias=True, **fkw)
            self.A_log = nn.Parameter(torch.zeros(self.d_inner, d_state, **fkw))
            self.D = nn.Parameter(torch.ones(self.d_inner, **fkw))
            self.out_proj = nn.Linear(self.d_inner, d_model, bias=bias, **fkw)
            self.act = nn.SiLU()

        def forward(self, h, inference_params=None):
            B, L, _ = h.shape
            xz = self.in_proj(h).transpose(1, 2)
            x, z = xz.chunk(2, dim=1)
            x = self.act(self.conv1d(x)[..., :L])
            xd = self.x_proj(x.transpose(1, 2).reshape(B * L, self.d_inner))
            dt, Bm, Cm = torch.split(xd, [self.dt_rank, self.d_state, self.d_state], -1)
            dt = F.linear(dt, self.dt_proj.weight).reshape(B, L, self.d_inner).transpose(1, 2)
            Bm = Bm.reshape(B, L, self.d_state).transpose(1, 2)
            Cm = Cm.reshape(B, L, self.d_state).transpose(1, 2)
            A = -torch.exp(self.A_log.float())
            y = selective_scan_ref(x, dt, A, Bm, Cm, D=self.D, z=z,
                                   delta_bias=self.dt_proj.bias.float(), delta_softplus=True)
            return self.out_proj(y.transpose(1, 2))

    class Block(nn.Module):
        def __init__(self, dim, mixer_cls, norm_cls=nn.LayerNorm, **kw):
            super().__init__()
            self.mixer = mixer_cls(dim)
            self.norm = norm_cls(dim)

        def forward(self, h, residual=None, inference_params=None):
            residual = (h + residual) if residual is not None else h
            h = self.norm(residual.to(self.norm.weight.dtype))
            return self.mixer(h, inference_params=inference_params), residual

    def _make_block(d_model, rms_norm, norm_eps, layer_idx, device, dtype):
        fkw = {'device': device, 'dtype': dtype}
        mc = partial(Mamba, layer_idx=layer_idx, **fkw)
        nc = partial(RMSNorm if rms_norm else nn.LayerNorm, eps=norm_eps, **fkw)
        blk = Block(d_model, mc, norm_cls=nc)
        blk.layer_idx = layer_idx
        return blk

    class MixerModel(nn.Module):
        def __init__(self, d_model, n_layer, ssm_cfg=None, norm_epsilon=1e-5, rms_norm=False,
                     if_bidirectional=True, initializer_cfg=None, fused_add_norm=False,
                     residual_in_fp32=False, device=None, dtype=None):
            super().__init__()
            self.if_bidirectional = if_bidirectional
            fkw = {'device': device, 'dtype': dtype}
            blk = partial(_make_block, d_model, rms_norm, norm_epsilon, device=device, dtype=dtype)
            self.forward_layers = nn.ModuleList([blk(layer_idx=i) for i in range(n_layer)])
            self.backward_layers = nn.ModuleList([blk(layer_idx=i) for i in range(n_layer)])
            nc = RMSNorm if rms_norm else nn.LayerNorm
            self.norm_f = nc(d_model, eps=norm_epsilon, **fkw)
            self.f_attention_pool = nn.Linear(d_model, 1, **fkw)
            self.b_attention_pool = nn.Linear(d_model, 1, **fkw)
            self.LL = nn.Linear(d_model * 2, d_model, **fkw)
            self.dropout = nn.Dropout(p=0.1)
            self.classifier = nn.Linear(d_model, 2, **fkw)

        @staticmethod
        def _pool(pool, h):
            w = F.softmax(pool(h), dim=1)
            return (w.transpose(-1, -2) @ h).squeeze(-2)

        def _norm(self, _last_h, res, orig):
            r = (res + orig) if res is not None else orig
            return self.norm_f(r.to(self.norm_f.weight.dtype))

        def forward(self, x, inference_params=None):
            orig = self.dropout(x)
            if not self.if_bidirectional:
                h, res = orig, None
                for lyr in self.forward_layers:
                    h, res = lyr(h, res, inference_params)
                h = self._norm(h, res, orig)
                return self.classifier(self.dropout(self._pool(self.f_attention_pool, h)))
            fh, fr = orig, None
            for lyr in self.forward_layers:
                fh, fr = lyr(fh, fr, inference_params)
            bh, br = orig.flip([1]), None
            for lyr in self.backward_layers:
                bh, br = lyr(bh, br, inference_params)
            fh = self._norm(fh, fr, orig)
            bh = self._norm(bh, br, orig)
            fp = self._pool(self.f_attention_pool, fh)
            bp = self._pool(self.b_attention_pool, bh)
            return self.classifier(self.dropout(self.LL(torch.cat([fp, bp], dim=1))))

    return MixerModel


class XlsrMambaModel:
    """Int16 speech in, P(real) out. Tiles or crops to its own 66,800-sample input."""

    requires_fixed_length = False
    input_samples = INPUT_SAMPLES

    def __init__(self, model_dir: Path, variant: str = "indic", threads: int | None = None):
        try:
            import torch
            from safetensors import safe_open
            from safetensors.torch import load_file
        except ImportError as e:
            raise ModelUnavailable(
                f"XLSR-Mamba needs torch + transformers + safetensors ({e}). "
                f"Install with: pip install -r requirements-antideepfake.txt"
            ) from e
        if variant not in ("indic", "base"):
            raise ModelUnavailable(f"unknown XLSR-Mamba variant {variant!r} (indic | base)")

        model_dir = Path(model_dir)
        self.base_path = model_dir / BASE_FILE
        self.head_path = model_dir / HEAD_FILE if variant == "indic" else None
        if not self.base_path.is_file():
            raise ModelUnavailable(f"{self.base_path} not found. Run: python scripts/fetch_xlsr_mamba.py")
        if self.head_path is not None and not self.head_path.is_file():
            raise ModelUnavailable(
                f"{self.head_path} not found. It comes from the private repo "
                f"harshit-nayak/Gadbad-Ghotala, branch XLSR_MAMBA_FINETUNED, "
                f"release/xlsr-mamba-indic-ft-lite.zip"
            )
        if threads:
            torch.set_num_threads(threads)
        self._torch = torch
        self.variant = variant
        self.name = "xlsr-mamba" if variant == "indic" else "xlsr-mamba-base"

        t0 = time.perf_counter()
        state = load_file(str(self.base_path))
        if self.head_path is not None:
            # Overwrite the head, exactly as the branch's load_model.py does --
            # but refuse a head that doesn't cover the base head one-for-one.
            with safe_open(str(self.head_path), framework="pt") as f:
                head_keys = set(f.keys())
                base_head = {k for k in state if k.startswith("conformer.")}
                if head_keys != base_head:
                    raise ModelUnavailable(
                        f"head file does not match the base head: "
                        f"{len(base_head - head_keys)} missing, {len(head_keys - base_head)} extra"
                    )
                for key in head_keys:
                    tensor = f.get_tensor(key)
                    if tuple(tensor.shape) != tuple(state[key].shape):
                        raise ModelUnavailable(f"head tensor {key} has shape {tuple(tensor.shape)}, "
                                               f"base expects {tuple(state[key].shape)}")
                    state[key] = tensor
        stray = [k for k in state if not k.startswith(KNOWN_PREFIXES)]
        if stray:
            raise ModelUnavailable(f"unexpected tensors in checkpoint: {stray[:4]}")

        def part(prefix):
            return {k[len(prefix):]: v for k, v in state.items() if k.startswith(prefix)}

        try:
            self.backbone = wav2vec2_port.build(part(SSL_PREFIX))
        except (wav2vec2_port.PortError, ImportError) as e:
            raise ModelUnavailable(str(e)) from e

        nn = torch.nn
        self.LL = nn.Linear(1024, 144)
        self.LL.load_state_dict(part("LL."), strict=True)
        self.first_bn = nn.BatchNorm2d(num_features=1)
        self.first_bn.load_state_dict(part("first_bn."), strict=True)
        self.selu = nn.SELU(inplace=True)
        MixerModel = _build_head_classes()
        self.conformer = MixerModel(d_model=144, n_layer=6, rms_norm=True,
                                    residual_in_fp32=True, fused_add_norm=True)
        self.conformer.load_state_dict(part("conformer."), strict=True)
        for module in (self.LL, self.first_bn, self.conformer):
            module.eval()

        self.load_seconds = time.perf_counter() - t0
        self.n_weights = (len(self.backbone.state_dict()) + len(part("LL.")) + len(part("first_bn."))
                          + len(part("conformer.")))
        self.provider = f"torch-cpu ({torch.get_num_threads()} threads)"
        stat = self.base_path.stat()
        head_tag = f"+{HEAD_FILE}:{self.head_path.stat().st_size}" if self.head_path else ""
        self.fingerprint = f"{BASE_ID}:{stat.st_size}:{int(stat.st_mtime)}{head_tag}"
        self._lock = threading.Lock()

    def logits(self, samples_int16: np.ndarray) -> np.ndarray:
        """1-D int16 speech -> the model's 2 raw logits, [spoof, bona fide]."""
        torch = self._torch
        x = pad_or_trim(np.asarray(samples_int16, dtype=np.float32) / INT16_SCALE)
        with self._lock, torch.inference_mode():
            feat = self.backbone(torch.from_numpy(np.ascontiguousarray(x))[None, :]).last_hidden_state
            h = self.LL(feat)
            h = self.selu(self.first_bn(h.unsqueeze(1))).squeeze(1)
            return self.conformer(h)[0].numpy()

    def score(self, samples_int16: np.ndarray) -> tuple[float, float]:
        """1-D int16 speech of any length -> (P(real), bona-fide log-prob)."""
        out = self.logits(samples_int16).astype(np.float64)
        logp_real = out[1] - np.logaddexp(out[0], out[1])
        return float(np.exp(logp_real)), float(logp_real)

    def score_window(self, samples_int16: np.ndarray, real_samples: int | None = None):
        """Score a pipeline window on its real speech, tiled to 66,800 samples."""
        if real_samples:
            samples_int16 = samples_int16[:real_samples]
        return self.score(samples_int16)

    def warmup(self) -> float:
        t0 = time.perf_counter()
        self.score(np.zeros(INPUT_SAMPLES, dtype=np.int16))
        return time.perf_counter() - t0

    def info(self) -> dict:
        return {
            "detector": self.name,
            "variant": self.variant,
            "model_path": str(self.base_path) + (f" + {self.head_path.name}" if self.head_path else ""),
            "fingerprint": self.fingerprint,
            "provider": self.provider,
            "load_seconds": round(self.load_seconds, 2),
            "weights_loaded": self.n_weights,
            "input_samples": INPUT_SAMPLES,
            "license": "MIT; Indic head trained on IndicSynth (CC BY-NC 4.0)",
        }
